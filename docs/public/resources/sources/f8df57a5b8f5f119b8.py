# 全参数监督微调：输入完整对话，仅在 Dataset 标记的 assistant 区域计算监督损失。
# 【与 train_pretrain.py 的核心区别】Pretrain 学习普通文本的下一个 token；本文件只学习 assistant 回复区域。
# 【差异位置】重点查看 SFTDataset、训练超参数、from_weight 和 accumulation_steps。
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
import torch.distributed as dist
from contextlib import nullcontext
from torch import optim, nn
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, DistributedSampler
from model.model_minimind import MiniMindConfig
from dataset.lm_dataset import SFTDataset
from trainer.trainer_utils import get_lr, Logger, is_main_process, lm_checkpoint, init_distributed_mode, setup_seed, init_model, SkipBatchSampler

warnings.filterwarnings('ignore')


# 按 assistant 标签做一轮全参数微调；批量张量为 [B,T]，监督移位由模型负责。
# 本函数使用入口初始化的模型、优化器、args 等外部对象；start_step 用于续训批次编号。
def train_epoch(epoch, loader, iters, start_step=0, wandb=None):
    start_time = time.time()
    last_step = start_step
    for step, (input_ids, labels) in enumerate(loader, start=start_step + 1):
        '''【从自然语言到这里的 input_ids、labels：一个完整样例】
        假设本批只有一条对话，即 batch_size=1，max_length=26。
        原始自然语言是：
            user：请介绍你自己
            assistant：你好，我是 MiniMind，很高兴帮助你。

        假设本次未添加 system，且已移除空 think 块，模板文本为：

            <|im_start|>user
            请介绍你自己<|im_end|>
            <|im_start|>assistant
            你好，我是 MiniMind，很高兴帮助你。<|im_end|>

        为方便手算，假设 token ID 如下（不是实际词表的分词结果）：
            <|im_start|>=1，<|im_end|>=2，换行=3，user=4，assistant=5，PAD=0。
            用户正文：请=10、介绍=11、你自己=12。
            助手正文：你好=20、，=21、我是=22、MiniMind=23、
                      很高兴=24、帮助=25、你=26、。=27。

        SFTDataset 已经完成编码、补齐和标签生成，DataLoader 再增加批次维度。
        因此循环取到的不是字符串，而是下面两个 torch.long（int64）张量：

            input_ids = tensor([
                [
                    1, 4, 3, 10, 11, 12, 2, 3,
                    1, 5, 3, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
                    0, 0, 0, 0
                ]
            ])

            labels = tensor([
                [
                    -100, -100, -100, -100, -100, -100, -100, -100,
                    -100, -100, -100, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
                    -100, -100, -100, -100
                ]
            ])

        两者形状都是 [1,26]，即 [批次中的样本数, 每条样本的 token 数]。
        内层列表按消息分行只是为了阅读，这些行仍属于同一条样本。
        若 batch_size=2，则外层会有两条这样的样本，形状为 [2,26]。

        对照同一条样本的位置：
            0～7：用户消息，input_ids 保留问题，labels 全为 -100。
            8～10：assistant 消息头，input_ids 保留角色，labels 为 -100。
            11～19：回答正文，两者都是 [20,21,22,23,21,24,25,26,27]。
            20～21：回答结束标记和换行，两者都是 [2,3]。
            22～25：PAD，input_ids 为 0，labels 为 -100。
        -100 表示忽略该目标的损失，不表示把用户问题从模型输入中删除。
        labels 此时还没有移位；后面的 model(input_ids, labels=labels)
        在内部对齐下一 token 目标，例如位置 10 的输出预测 labels[0,11]=20（你好）。
        '''
        input_ids = input_ids.to(args.device)
        labels = labels.to(args.device)
        last_step = step
        lr = get_lr(epoch * iters + step, args.epochs * iters, args.learning_rate)
        # 优化器可能有多个参数组；逐组赋学习率，使所有组遵循当前调度。
        for param_group in optimizer.param_groups:
            param_group['lr'] = lr

        with autocast_ctx:
            res = model(input_ids, labels=labels)
            loss = res.loss + res.aux_loss
            # 梯度会跨多个小批累积，先除以累积步数以控制一个完整更新窗口的梯度尺度。
            loss = loss / args.accumulation_steps
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
            current_aux_loss = res.aux_loss.item() if res.aux_loss is not None else 0.0
            current_logits_loss = current_loss - current_aux_loss
            current_lr = optimizer.param_groups[-1]['lr']
            eta_min = spend_time / max(step - start_step, 1) * (iters - step) // 60
            Logger(f'Epoch:[{epoch + 1}/{args.epochs}]({step}/{iters}), loss: {current_loss:.4f}, logits_loss: {current_logits_loss:.4f}, aux_loss: {current_aux_loss:.4f}, lr: {current_lr:.8f}, epoch_time: {eta_min:.1f}min')
            if wandb: wandb.log({"loss": current_loss, "logits_loss": current_logits_loss, "aux_loss": current_aux_loss, "learning_rate": current_lr, "epoch_time": eta_min})

        if (step % args.save_interval == 0 or step == iters) and is_main_process():
            model.eval()
            moe_suffix = '_moe' if lm_config.use_moe else ''
            ckp = f'{args.save_dir}/{args.save_weight}_{lm_config.hidden_size}{moe_suffix}.pth'
            raw_model = model.module if isinstance(model, DistributedDataParallel) else model
            # torch.compile 可能包裹原模型；取 _orig_mod 保持导出权重的键名与普通模型一致。
            raw_model = getattr(raw_model, '_orig_mod', raw_model)
            state_dict = raw_model.state_dict()
            # PyTorch：save 将对象序列化；这里保存 state_dict 等状态，恢复时仍需用匹配的模型配置构建网络。
            torch.save({k: v.half().cpu() for k, v in state_dict.items()}, ckp)
            lm_checkpoint(lm_config, weight=args.save_weight, model=model, optimizer=optimizer, 
                         epoch=epoch, step=step, wandb=wandb, save_dir='../checkpoints', scaler=scaler)
            model.train()
            del state_dict

        del input_ids, labels, res, loss

    # 处理末尾不足一个完整累积窗口的梯度；沿用原有缩放系数，并未按尾部实际批数重新归一化。
    if last_step > start_step and last_step % args.accumulation_steps != 0:
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)


if __name__ == "__main__":
    # 命令行参数集中定义训练/推理的路径、模型规模和运行选项，下方 parse_args 读取实际值。
    parser = argparse.ArgumentParser(description="MiniMind Full SFT")
    parser.add_argument("--save_dir", type=str, default="../out", help="模型保存目录")
    parser.add_argument('--save_weight', default='full_sft', type=str, help="保存权重的前缀名")
    parser.add_argument("--epochs", type=int, default=2, help="训练轮数")
    # 【与 Pretrain 不同】SFT 默认 batch 更小、学习率更低，避免破坏预训练得到的语言能力。
    parser.add_argument("--batch_size", type=int, default=16, help="batch size")
    parser.add_argument("--learning_rate", type=float, default=1e-5, help="初始学习率")
    parser.add_argument("--device", type=str, default="cuda:0" if torch.cuda.is_available() else "cpu", help="训练设备")
    parser.add_argument("--dtype", type=str, default="bfloat16", help="混合精度类型")
    parser.add_argument("--num_workers", type=int, default=8, help="数据加载线程数")
    # 【与 Pretrain 不同】Pretrain 默认值为 8；SFT 默认值为 1，即不进行跨 batch 梯度累积。
    parser.add_argument("--accumulation_steps", type=int, default=1, help="梯度累积步数")
    parser.add_argument("--grad_clip", type=float, default=1.0, help="梯度裁剪阈值")
    parser.add_argument("--log_interval", type=int, default=100, help="日志打印间隔")
    parser.add_argument("--save_interval", type=int, default=1000, help="模型保存间隔")
    parser.add_argument('--hidden_size', default=768, type=int, help="隐藏层维度")
    parser.add_argument('--num_hidden_layers', default=8, type=int, help="隐藏层数量")
    # 【与 Pretrain 不同】SFT 对话通常比预训练单段文本更长，默认最大长度为 768，而 Pretrain 为 340。
    parser.add_argument('--max_seq_len', default=768, type=int, help="训练的最大截断长度（中文1token≈1.5~1.7字符）")
    parser.add_argument('--use_moe', default=0, type=int, choices=[0, 1], help="是否使用MoE架构（0=否，1=是）")
    parser.add_argument("--data_path", type=str, default="../dataset/sft_t2t_mini.jsonl", help="训练数据路径")
    # 【与 Pretrain 不同】SFT 默认加载 pretrain 权重，在预训练模型基础上继续学习对话回答。
    parser.add_argument('--from_weight', default='pretrain', type=str, help="基于哪个权重训练，为none则不基于任何权重训练")
    parser.add_argument('--from_resume', default=0, type=int, choices=[0, 1], help="是否自动检测&续训（0=否，1=是）")
    parser.add_argument("--use_wandb", action="store_true", help="是否使用wandb")
    parser.add_argument("--wandb_project", type=str, default="MiniMind-Full-SFT", help="wandb项目名")
    parser.add_argument("--use_compile", default=0, type=int, choices=[0, 1], help="是否使用torch.compile加速（0=否，1=是）")
    args = parser.parse_args()

    # ========== 1. 初始化环境和随机种子 ==========
    local_rank = init_distributed_mode()
    if dist.is_initialized(): args.device = f"cuda:{local_rank}"
    setup_seed(42 + (dist.get_rank() if dist.is_initialized() else 0))
    
    # ========== 2. 配置目录、模型参数、检查ckp ==========
    os.makedirs(args.save_dir, exist_ok=True)
    lm_config = MiniMindConfig(hidden_size=args.hidden_size, num_hidden_layers=args.num_hidden_layers, use_moe=bool(args.use_moe))
    # 仅当开启 from_resume 时读取完整续训状态；from_weight 则用于选择初始权重。
    ckp_data = lm_checkpoint(lm_config, weight=args.save_weight, save_dir='../checkpoints') if args.from_resume==1 else None
    
    # ========== 3. 设置混合精度 ==========
    device_type = "cuda" if "cuda" in args.device else "cpu"
    dtype = torch.bfloat16 if args.dtype == "bfloat16" else torch.float16
    # PyTorch AMP：autocast 为运算选择适合的精度，不等于把所有张量永久改为半精度。
    # 这里沿用原 CUDA AMP 写法；新版统一接口为 torch.amp.autocast("cuda", dtype=...)。
    autocast_ctx = nullcontext() if device_type == "cpu" else torch.amp.autocast('cuda', dtype=dtype)
    
    # ========== 4. 配wandb ==========
    wandb = None
    if args.use_wandb and is_main_process():
        import swanlab as wandb
        wandb_id = ckp_data.get('wandb_id') if ckp_data else None
        resume = 'must' if wandb_id else None
        wandb_run_name = f"MiniMind-Full-SFT-Epoch-{args.epochs}-BatchSize-{args.batch_size}-LearningRate-{args.learning_rate}"
        wandb.init(project=args.wandb_project, name=wandb_run_name, id=wandb_id, resume=resume)
    
    # ========== 5. 定义模型、数据、优化器 ==========
    model, tokenizer = init_model(lm_config, args.from_weight, device=args.device)
    # 【与 Pretrain 不同的数据】SFTDataset 读取 conversations 多轮对话，labels 只保留 assistant 回复；
    # 用户问题、system 内容和 PAD 位置为 -100，不参与交叉熵损失。
    train_ds = SFTDataset(args.data_path, tokenizer, max_length=args.max_seq_len)
    # PyTorch：DistributedSampler 按 rank 分配样本索引；每轮 set_epoch(epoch) 更新一致的随机排列。
    train_sampler = DistributedSampler(train_ds) if dist.is_initialized() else None
    # PyTorch AMP：GradScaler 管理动态损失缩放；这里仅在 float16 下启用，bfloat16 分支禁用。
    # 新版统一接口为 torch.amp.GradScaler("cuda", enabled=...)。
    scaler = torch.amp.GradScaler('cuda', enabled=(args.dtype == 'float16'))
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
        # 非分布式训练时 train_sampler 为 None；分布式训练时通知采样器切换本轮随机顺序。set_epoch(epoch) 的作用是让 DistributedSampler 在每个 epoch 使用不同的随机顺序，同时保证所有进程按照一致的规则划分数据。否则每轮可能都使用相同的样本顺序，导致数据打乱失效。
        if train_sampler is not None:
            train_sampler.set_epoch(epoch)
        # PyTorch：randperm(n) 产生 0..n-1 的随机无重复排列，常用于打乱样本或 mini-batch 顺序。
        setup_seed(42 + epoch); indices = torch.randperm(len(train_ds)).tolist()
        skip = start_step if (epoch == start_epoch and start_step > 0) else 0
        batch_sampler = SkipBatchSampler(train_sampler or indices, args.batch_size, skip)
        # PyTorch：DataLoader 从 Dataset 取样并组批；batch_sampler 已决定批次，pin_memory 可使 CPU 数据使用锁页内存。
        loader = DataLoader(train_ds, batch_sampler=batch_sampler, num_workers=args.num_workers, pin_memory=True)
        if skip > 0: 
            Logger(f'Epoch [{epoch + 1}/{args.epochs}]: 跳过前{start_step}个step，从step {start_step + 1}开始')
            train_epoch(epoch, loader, len(loader) + skip, start_step, wandb)
        else:
            train_epoch(epoch, loader, len(loader), 0, wandb)
    
    # ========== 9. 清理分布进程 ==========
    if dist.is_initialized():
        # PyTorch：barrier 等待所有进程到达同步点；所有 rank 都应参与，不能只在主进程调用。
        dist.barrier()
        # PyTorch：训练结束后销毁通信组，释放分布式后端资源。
        dist.destroy_process_group()
