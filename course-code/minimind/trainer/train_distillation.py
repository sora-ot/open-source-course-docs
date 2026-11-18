# 知识蒸馏：学生学习硬标签交叉熵与教师软分布，alpha 是硬标签损失的权重。
import os
import sys

__package__ = "trainer"
# 直接运行子目录脚本时将项目根加入模块搜索路径，以便导入 model、dataset、trainer。
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import datasets  # noqa: F401  # Windows pyarrow/torch DLL conflict workaround (issue #771)
import argparse
import time
import warnings
import torch
import torch.nn.functional as F
import torch.distributed as dist
from contextlib import nullcontext
from torch import optim
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, DistributedSampler
from model.model_minimind import MiniMindConfig
from dataset.lm_dataset import SFTDataset
from trainer.trainer_utils import get_lr, Logger, is_main_process, lm_checkpoint, init_distributed_mode, setup_seed, init_model, SkipBatchSampler

warnings.filterwarnings('ignore')


# 计算 KL(教师分布 || 学生分布) 并乘 temperature²；输入的词表列需对应相同 token。
def distillation_loss(student_logits, teacher_logits, temperature=1.0, reduction='batchmean'):
    # PyTorch：no_grad 中的运算不建立反向图，用于参考模型/采样以节省显存；不会自动切换 eval 模式。
    with torch.no_grad():
        # PyTorch：detach 切断此张量的梯度历史，但仍可能共享存储；需要独立副本时再 clone()。
        teacher_probs = F.softmax(teacher_logits / temperature, dim=-1).detach()#得到教师的概率分布，且不计算教师梯度。

    student_log_probs = F.log_softmax(student_logits / temperature, dim=-1)#得到学生的 log 概率，保留梯度。

    # PyTorch：kl_div 的 input 是 log 概率，默认 target 是概率；batchmean 将各项之和除以第一维长度。
    # 本函数调用时第一维是筛选后的有效 token 数，因此相当于按有效 token 平均 KL。
    kl = F.kl_div(
        student_log_probs,
        teacher_probs,
        reduction=reduction
    )
    return (temperature ** 2) * kl


# 对齐师生预测位置，仅在有效监督 token 上蒸馏；教师冻结，学生保留梯度。
# 本函数使用入口初始化的模型、优化器、args 等外部对象；start_step 用于续训批次编号。
def train_epoch(epoch, loader, iters, teacher_model, lm_config_student, start_step=0, wandb=None, alpha=0.0, temperature=1.0):
    start_time = time.time()
    last_step = start_step
    
    if teacher_model is not None:
        teacher_model.eval()
        # PyTorch：requires_grad_(False) 冻结参数梯度；eval() 只改变 Dropout 等层的行为，两者用途不同。
        teacher_model.requires_grad_(False)

    for step, (input_ids, labels) in enumerate(loader, start=start_step + 1):
        last_step = step
        input_ids = input_ids.to(args.device)
        labels = labels.to(args.device)
        loss_mask = (labels[..., 1:] != -100).float()
        lr = get_lr(epoch * iters + step, args.epochs * iters, args.learning_rate)
        # 优化器可能有多个参数组；逐组赋学习率，使所有组遵循当前调度。
        for param_group in optimizer.param_groups:
            param_group['lr'] = lr

        # 前向传播（学生模型）
        with autocast_ctx:
            res = model(input_ids)
            # PyTorch：切片/转置可能产生非连续布局；contiguous() 在需要时复制，使后续 view 可按目标形状解释内存。
            student_logits = res.logits[..., :-1, :].contiguous()

        # 教师模型前向传播（只在eval & no_grad）
        if teacher_model is not None:
            with torch.no_grad():
                teacher_logits = teacher_model(input_ids).logits[..., :-1, :].contiguous()
                vocab_size_student = student_logits.size(-1)
                # 这里仅裁剪教师词表列，不做 token 重映射；要求师生相同 ID 对应相同 token。
                teacher_logits = teacher_logits[..., :vocab_size_student]

        # ========== 计算损失 ==========
        # 1) Ground-Truth CE Loss
        shift_labels = labels[..., 1:].contiguous()
        loss_mask_flat = loss_mask.view(-1)
        # PyTorch：cross_entropy 接收未做 softmax 的分数和整型类别标签；ignore_index=-100 可排除无监督位置。
        ce_loss = F.cross_entropy(
            student_logits.view(-1, student_logits.size(-1)),
            shift_labels.view(-1),
            ignore_index=-100,
            reduction='none'
        )
        ce_loss_raw = torch.sum(ce_loss * loss_mask_flat) / (loss_mask_flat.sum() + 1e-8)
        if lm_config_student.use_moe: ce_loss = ce_loss_raw + res.aux_loss
        else: ce_loss = ce_loss_raw

        # 2) Distillation Loss
        if teacher_model is not None:
            # 布尔索引只保留有监督标签的位置，师生输入因此为 [有效token数,V]。
            distill_loss = distillation_loss(
                student_logits.view(-1, student_logits.size(-1))[loss_mask_flat == 1],
                teacher_logits.view(-1, teacher_logits.size(-1))[loss_mask_flat == 1],
                temperature=temperature
            )
        else:
            distill_loss = torch.tensor(0.0, device=args.device)

        # 3) 总损失 = alpha * CE + (1-alpha) * Distill
        # 总损失 = alpha×硬标签损失 + (1-alpha)×蒸馏损失；alpha=0 时只学习教师分布。
        loss = (alpha * ce_loss + (1 - alpha) * distill_loss) / args.accumulation_steps

        # PyTorch AMP：先放大 loss 再 backward，缓解 FP16 小梯度下溢；backward 把梯度累加到 .grad。
        scaler.scale(loss).backward()

        if step % args.accumulation_steps == 0:
            # PyTorch AMP：裁剪前先 unscale_ 还原梯度；每次优化器更新仅应对同一优化器还原一次。
            scaler.unscale_(optimizer)
            # PyTorch：clip_grad_norm_ 按参数梯度的整体范数原地缩放，限制过大的更新；返回裁剪前范数。
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            # PyTorch AMP：scaler.step 在梯度有限时执行 optimizer.step，检测到 inf/NaN 时跳过；随后 update 调整缩放因子。
            scaler.step(optimizer)
            scaler.update()
            # PyTorch：zero_grad(set_to_none=True) 将梯度引用设为 None；下一次 backward 重新建立梯度，适合累积窗口结束后调用。
            optimizer.zero_grad(set_to_none=True)

        # 按间隔及本轮最后一批记录训练指标；item() 将单元素张量转为 Python 数值。
        if step % args.log_interval == 0 or step == iters:
            spend_time = time.time() - start_time
            current_loss = loss.item() * args.accumulation_steps
            current_ce_loss = ce_loss_raw.item()
            current_aux_loss = res.aux_loss.item() if lm_config_student.use_moe else 0.0
            current_lr = optimizer.param_groups[-1]['lr']
            eta_min = spend_time / max(step - start_step, 1) * (iters - step) // 60
            
            Logger(f'Epoch:[{epoch + 1}/{args.epochs}]({step}/{iters}), loss: {current_loss:.4f}, ce: {current_ce_loss:.4f}, aux_loss: {current_aux_loss:.4f}, distill: {distill_loss.item():.4f}, learning_rate: {current_lr:.8f}, epoch_time: {eta_min:.3f}min')
            
            if wandb:
                wandb.log({
                    "loss": current_loss,
                    "ce_loss": current_ce_loss,
                    "aux_loss": current_aux_loss,
                    "distill_loss": distill_loss.item() if teacher_model is not None else 0.0,
                    "learning_rate": current_lr,
                    "epoch_time": eta_min
                })

        if (step % args.save_interval == 0 or step == iters) and is_main_process():
            model.eval()
            moe_suffix = '_moe' if lm_config_student.use_moe else ''
            ckp = f'{args.save_dir}/{args.save_weight}_{lm_config_student.hidden_size}{moe_suffix}.pth'
            raw_model = model.module if isinstance(model, DistributedDataParallel) else model
            # torch.compile 可能包裹原模型；取 _orig_mod 保持导出权重的键名与普通模型一致。
            raw_model = getattr(raw_model, '_orig_mod', raw_model)
            state_dict = raw_model.state_dict()
            # PyTorch：save 将对象序列化；这里保存 state_dict 等状态，恢复时仍需用匹配的模型配置构建网络。
            torch.save({k: v.half().cpu() for k, v in state_dict.items()}, ckp)
            lm_checkpoint(lm_config_student, weight=args.save_weight, model=model, optimizer=optimizer, scaler=scaler, epoch=epoch, step=step, wandb=wandb, save_dir='../checkpoints')
            model.train()
            del state_dict

        del input_ids, labels, loss_mask, res, student_logits, ce_loss, distill_loss, loss

    # 处理末尾不足一个完整累积窗口的梯度；沿用原有缩放系数，并未按尾部实际批数重新归一化。
    if last_step > start_step and last_step % args.accumulation_steps != 0:
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)


if __name__ == "__main__":
    # 模拟用moe模型蒸馏dense模型，也可以用更大teacher_hidden_size模型蒸馏更小student_hidden_size的
    parser = argparse.ArgumentParser(description="MiniMind Knowledge Distillation")
    parser.add_argument("--save_dir", type=str, default="../out", help="模型保存目录")
    parser.add_argument('--save_weight', default='full_dist', type=str, help="保存权重的前缀名")
    parser.add_argument("--epochs", type=int, default=6, help="训练轮数")
    parser.add_argument("--batch_size", type=int, default=32, help="batch size")
    parser.add_argument("--learning_rate", type=float, default=5e-6, help="初始学习率")
    parser.add_argument("--device", type=str, default="cuda:0" if torch.cuda.is_available() else "cpu", help="训练设备")
    parser.add_argument("--dtype", type=str, default="bfloat16", help="混合精度类型")
    parser.add_argument("--num_workers", type=int, default=8, help="数据加载线程数")
    parser.add_argument("--accumulation_steps", type=int, default=1, help="梯度累积步数")
    parser.add_argument("--grad_clip", type=float, default=1.0, help="梯度裁剪阈值")
    parser.add_argument("--log_interval", type=int, default=100, help="日志打印间隔")
    parser.add_argument("--save_interval", type=int, default=100, help="模型保存间隔")
    parser.add_argument("--max_seq_len", type=int, default=340, help="训练的最大截断长度（中文1token≈1.5~1.7字符）")
    parser.add_argument("--data_path", type=str, default="../dataset/sft_t2t_mini.jsonl", help="训练数据路径")
    parser.add_argument('--student_hidden_size', default=768, type=int, help="学生模型隐藏层维度")
    parser.add_argument('--student_num_layers', default=8, type=int, help="学生模型隐藏层数量")
    parser.add_argument('--teacher_hidden_size', default=768, type=int, help="教师模型隐藏层维度")
    parser.add_argument('--teacher_num_layers', default=8, type=int, help="教师模型隐藏层数量")
    parser.add_argument('--student_use_moe', default=0, type=int, choices=[0, 1], help="学生模型是否使用MoE（0=否，1=是）")
    parser.add_argument('--teacher_use_moe', default=1, type=int, choices=[0, 1], help="教师模型是否使用MoE（0=否，1=是）")
    parser.add_argument('--from_student_weight', default='full_sft', type=str, help="学生模型基于哪个权重")
    parser.add_argument('--from_teacher_weight', default='full_sft', type=str, help="教师模型基于哪个权重")
    parser.add_argument('--from_resume', default=0, type=int, choices=[0, 1], help="是否自动检测&续训（0=否，1=是）")
    parser.add_argument('--alpha', default=0.5, type=float, help="CE损失权重，总损失=alpha*CE+(1-alpha)*KL")
    parser.add_argument('--temperature', default=1.5, type=float, help="蒸馏温度（推荐范围1.0-2.0）")
    parser.add_argument("--use_wandb", action="store_true", help="是否使用wandb")
    parser.add_argument("--wandb_project", type=str, default="MiniMind-Distillation", help="wandb项目名")
    parser.add_argument("--use_compile", default=0, type=int, choices=[0, 1], help="是否使用torch.compile加速（0=否，1=是）")
    args = parser.parse_args()

    # ========== 1. 初始化环境和随机种子 ==========
    local_rank = init_distributed_mode()
    if dist.is_initialized(): args.device = f"cuda:{local_rank}"
    setup_seed(42 + (dist.get_rank() if dist.is_initialized() else 0))
    
    # ========== 2. 配置目录、模型参数、检查ckp ==========
    os.makedirs(args.save_dir, exist_ok=True)
    lm_config_student = MiniMindConfig(hidden_size=args.student_hidden_size, num_hidden_layers=args.student_num_layers, use_moe=bool(args.student_use_moe))
    lm_config_teacher = MiniMindConfig(hidden_size=args.teacher_hidden_size, num_hidden_layers=args.teacher_num_layers, use_moe=bool(args.teacher_use_moe))
    # 仅当开启 from_resume 时读取完整续训状态；from_weight 则用于选择初始权重。
    ckp_data = lm_checkpoint(lm_config_student, weight=args.save_weight, save_dir='../checkpoints') if args.from_resume==1 else None
    
    # ========== 3. 设置混合精度 ==========
    device_type = "cuda" if "cuda" in args.device else "cpu"
    dtype = torch.bfloat16 if args.dtype == "bfloat16" else torch.float16
    # PyTorch AMP：autocast 为运算选择适合的精度，不等于把所有张量永久改为半精度。
    # 这里沿用原 CUDA AMP 写法；新版统一接口为 torch.amp.autocast("cuda", dtype=...)。
    autocast_ctx = nullcontext() if device_type == "cpu" else torch.cuda.amp.autocast(dtype=dtype)
    
    # ========== 4. 配wandb ==========
    wandb = None
    if args.use_wandb and is_main_process():
        import swanlab as wandb
        wandb_id = ckp_data.get('wandb_id') if ckp_data else None
        resume = 'must' if wandb_id else None
        wandb_run_name = f"MiniMind-Distill-S{args.student_hidden_size}T{args.teacher_hidden_size}-Epoch-{args.epochs}-BS-{args.batch_size}-LR-{args.learning_rate}"
        wandb.init(project=args.wandb_project, name=wandb_run_name, id=wandb_id, resume=resume)
    
    # ========== 5. 定义学生和教师模型 ==========
    model, tokenizer = init_model(lm_config_student, args.from_student_weight, device=args.device)
    Logger(f'学生模型总参数量：{sum(p.numel() for p in model.parameters()) / 1e6:.3f} M')
    teacher_model, _ = init_model(lm_config_teacher, args.from_teacher_weight, device=args.device)
    teacher_model.eval()
    teacher_model.requires_grad_(False)
    Logger(f'教师模型总参数量：{sum(p.numel() for p in teacher_model.parameters()) / 1e6:.3f} M')
    train_ds = SFTDataset(args.data_path, tokenizer, max_length=args.max_seq_len)
    # PyTorch：DistributedSampler 按 rank 分配样本索引；每轮 set_epoch(epoch) 更新一致的随机排列。
    train_sampler = DistributedSampler(train_ds) if dist.is_initialized() else None
    # PyTorch AMP：GradScaler 管理动态损失缩放；这里仅在 float16 下启用，bfloat16 分支禁用。
    # 新版统一接口为 torch.amp.GradScaler("cuda", enabled=...)。
    scaler = torch.cuda.amp.GradScaler(enabled=(args.dtype == 'float16'))
    optimizer = optim.AdamW(model.parameters(), lr=args.learning_rate)
    
    # ========== 6. 从ckp恢复状态 ==========
    start_epoch, start_step = 0, 0
    if ckp_data:
        # PyTorch：load_state_dict 按参数/缓冲区名字恢复状态；strict=False 允许缺失/额外键，但不忽略同名张量形状不匹配。
        model.load_state_dict(ckp_data['model'])
        optimizer.load_state_dict(ckp_data['optimizer'])
        scaler.load_state_dict(ckp_data['scaler'])
        start_epoch = ckp_data['epoch']
        start_step = ckp_data.get('step', 0)
    
    # ========== 7. 编译和分布式包装 ==========
    if args.use_compile == 1:
        # PyTorch：compile 捕获并优化可编译的计算图；首次执行有编译成本，动态 Python 控制流可能导致图中断。
        model = torch.compile(model)
        Logger('torch.compile enabled')
    if dist.is_initialized():
        # PyTorch DDP：每个进程包装一份模型，在常规 DDP 前向/反向路径中同步梯度；数据切分由 sampler 负责。
        model = DistributedDataParallel(model, device_ids=[local_rank])
    
    # ========== 8. 开始训练 ==========
    for epoch in range(start_epoch, args.epochs):
        train_sampler and train_sampler.set_epoch(epoch)
        # PyTorch：randperm(n) 产生 0..n-1 的随机无重复排列，常用于打乱样本或 mini-batch 顺序。
        setup_seed(42 + epoch); indices = torch.randperm(len(train_ds)).tolist()
        skip = start_step if (epoch == start_epoch and start_step > 0) else 0
        batch_sampler = SkipBatchSampler(train_sampler or indices, args.batch_size, skip)
        # PyTorch：DataLoader 从 Dataset 取样并组批；batch_sampler 已决定批次，pin_memory 可使 CPU 数据使用锁页内存。
        loader = DataLoader(train_ds, batch_sampler=batch_sampler, num_workers=args.num_workers, pin_memory=True)
        if skip > 0: 
            Logger(f'Epoch [{epoch + 1}/{args.epochs}]: 跳过前{start_step}个step，从step {start_step + 1}开始')
            train_epoch(epoch, loader, len(loader) + skip, teacher_model, lm_config_student, start_step, wandb, args.alpha, args.temperature)
        else:
            train_epoch(epoch, loader, len(loader), teacher_model, lm_config_student, 0, wandb, args.alpha, args.temperature)
    
    # ========== 9. 清理分布进程 ==========
    if dist.is_initialized():
        # PyTorch：barrier 等待所有进程到达同步点；所有 rank 都应参与，不能只在主进程调用。
        dist.barrier()
        # PyTorch：训练结束后销毁通信组，释放分布式后端资源。
        dist.destroy_process_group()