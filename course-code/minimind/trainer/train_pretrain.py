# 预训练入口：用普通文本学习下一个 token；填充标签为 -100，其余位置参与语言模型损失。
import os
import sys

# 直接运行本脚本时，将项目根目录加入模块搜索路径，便于导入 model、dataset 和 trainer。
__package__ = "trainer"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 提前导入 datasets，规避 Windows 下 pyarrow 与 torch 的 DLL 加载冲突。
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
from dataset.lm_dataset import PretrainDataset
from trainer.trainer_utils import get_lr, Logger, is_main_process, lm_checkpoint, init_distributed_mode, setup_seed, init_model, SkipBatchSampler

warnings.filterwarnings('ignore')

# 每个批次执行：前向传播 → 计算损失 → 反向传播；累积指定批次数后更新参数。
# epoch 从 0 开始；iters 是本轮的总批次数（包括续训时跳过的批次）。
# start_step 表示本轮已完成的批次数；args、model、optimizer 等由下方主程序初始化。
# 训练一个 epoch：前向计算语言模型与 MoE 损失，梯度累积后更新参数，并记录/保存进度。
# 本函数使用入口初始化的模型、优化器、args 等外部对象；start_step 用于续训批次编号。
def train_epoch(epoch, loader, iters, start_step=0, wandb=None):
    # 续训时只统计本次运行的耗时，用于估算当前 epoch 的剩余时间。
    start_time = time.time()
    # loader 可能为空；记录实际处理到的批次，避免在没有新梯度时执行末尾更新。
    last_step = start_step
    # step 按数据批次计数，不是优化器更新次数；续训时接着原来的批次编号计数。
    for step, (input_ids, labels) in enumerate(loader, start=start_step + 1):
        # 将输入 token 和监督标签移到当前进程使用的 CPU/GPU。
        '''数据形状回顾：
        DataLoader 取出的 input_ids 可能是：
        tensor([[1, 10, 11, 2, 0, 0, 0, 0],
            [1, 20, 21, 22, 2, 0, 0, 0],
            [1, 30, 31, 2, 0, 0, 0, 0]])，形状为 [3, 8]。
        对应的 labels 可能是：
        tensor([[1, 10, 11, 2, -100, -100, -100, -100],
            [1, 20, 21, 22, 2, -100, -100, -100],
            [1, 30, 31, 2, -100, -100, -100, -100]])，形状同样为 [3, 8]。
        .to(args.device) 只负责把张量从 CPU 搬到 args.device 指定的设备，
        例如 cuda:0；数据内容和形状仍然不变，之后才能与同一设备上的模型计算。
        '''
        input_ids = input_ids.to(args.device)
        labels = labels.to(args.device)
        last_step = step
        # 按全局批次进度做余弦衰减，学习率逐渐降至初始值的 10%，并更新所有参数组。
        lr = get_lr(epoch * iters + step, args.epochs * iters, args.learning_rate)
        '''param_group['lr'] 的作用：
            如果本次计算得到 lr = 0.0001，optimizer.param_groups 中有两个参数组，
            那么循环会依次执行：
            第 1 组：param_group['lr'] = 0.0001
            第 2 组：param_group['lr'] = 0.0001
            这样无论优化器包含一组还是多组模型参数，所有参数组都会使用当前批次的学习率。
            本项目通常只有一个参数组，但保留循环可以兼容为不同参数设置不同初始学习率的情况。
        '''
        for param_group in optimizer.param_groups:
            param_group['lr'] = lr
        # autocast 为适合的运算选择 FP16/BF16，部分需要数值稳定性的运算使用 FP32。
        # CPU 分支使用空上下文，不在这里启用自动混合精度。
        with autocast_ctx:
            
            res = model(input_ids, labels=labels)  # 前向传播，并由模型内部计算主损失。
            # res.loss 是语言模型交叉熵，训练模型预测下一个 token。
            # res.aux_loss 是 MoE 的辅助正则项：根据专家的实际命中率和路由概率，
            # 约束 token 不要长期集中到少数专家，避免专家负载失衡；非 MoE 时为 0。
            # 它不是另一批数据的损失，而是当前批次前向计算产生的额外训练目标。
            loss = res.loss + res.aux_loss
            # 总损失的梯度同时包含主损失和 aux_loss 的梯度：
            #   d(loss)/d(parameter) = d(res.loss)/d(parameter) + d(res.aux_loss)/d(parameter)
            # 梯度累积时每个小批次都除以 accumulation_steps，防止梯度过大导致更新幅度过大
            # 更新一次时，梯度规模近似等于这些小批次损失梯度的平均值，而不是简单放大 N 倍。
            # 因此 aux_loss 也会按同样比例参与累计，不会绕过梯度累积单独更新参数。
            loss = loss / args.accumulation_steps

        # backward 会将梯度累加到参数的 .grad 中；PyTorch 默认不会覆盖已有梯度，
        # 因此这里连续执行多个小批次的 backward 就实现了梯度累计，此处尚不更新参数。
        # 每个小批次都会累加主损失和 aux_loss 共同产生的梯度。
        # 启用 GradScaler 时先放大损失，减轻 FP16 小梯度下溢；禁用时等同于普通反向传播。
        # PyTorch AMP：先放大 loss 再 backward，缓解 FP16 小梯度下溢；backward 把梯度累加到 .grad。
        scaler.scale(loss).backward()

        # 每达到一个累积边界才更新一次参数，从而用多个小批次模拟较大的批次。
        # accumulation_steps=8 时，前 8 次 backward 的梯度会保留在 .grad 中，
        # 第 8 次才执行 step；zero_grad 清空 .grad 后，才开始下一轮累计。
        if step % args.accumulation_steps == 0:
            # 此时 .grad 中是 accumulation_steps 个小批次的平均梯度，
            # 其中既有语言模型目标的梯度，也有 MoE 负载均衡 aux_loss 的梯度。
            # 先还原真实梯度，再按所有参数梯度的整体 L2 范数裁剪。
            # PyTorch AMP：裁剪前先 unscale_ 还原梯度；每次优化器更新仅应对同一优化器还原一次。
            scaler.unscale_(optimizer)
            # 范数超过 grad_clip 时按比例缩小梯度，限制单次更新的幅度。
            # PyTorch：clip_grad_norm_ 按参数梯度的整体范数原地缩放，限制过大的更新；返回裁剪前范数。
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)

            # 调用优化器更新参数；启用缩放时，若检测到 inf/nan 梯度则跳过此次更新。
            # PyTorch AMP：scaler.step 在梯度有限时执行 optimizer.step，检测到 inf/NaN 时跳过；随后 update 调整缩放因子。
            scaler.step(optimizer) # 有了这个就不需要 optimizer.step() 了
            scaler.update()  # 根据溢出情况调整下一次使用的缩放因子（仅启用时生效）。

            # PyTorch：zero_grad(set_to_none=True) 将梯度引用设为 None；下一次 backward 重新建立梯度，适合累积窗口结束后调用。如果整句不写，下一次 backward() 会继续把新梯度累加到旧梯度上，结果是梯度越来越大，模型更新幅度异常，可能导致训练不稳定、损失发散，甚至出现 NaN。当前代码使用梯度累积，因此只应在完成一组累积后清零：
            optimizer.zero_grad(set_to_none=True)  # 释放梯度引用，开始下一组累积。

        # 定期记录当前批次的损失（不是整轮平均值），并在本轮最后一个批次记录一次。
        if step % args.log_interval == 0 or step == iters:
            spend_time = time.time() - start_time
            # 还原除以 accumulation_steps 之前的损失，便于直接观察训练指标。
            current_loss = loss.item() * args.accumulation_steps
            current_aux_loss = res.aux_loss.item() if res.aux_loss is not None else 0.0
            current_logits_loss = current_loss - current_aux_loss
            current_lr = optimizer.param_groups[-1]['lr']
            # 已运行批次的平均耗时 × 剩余批次数，换算为剩余分钟数。
            eta_min = spend_time / max(step - start_step, 1) * (iters - step) // 60
            Logger(f'Epoch:[{epoch + 1}/{args.epochs}]({step}/{iters}), loss: {current_loss:.4f}, logits_loss: {current_logits_loss:.4f}, aux_loss: {current_aux_loss:.4f}, lr: {current_lr:.8f}, epoch_time: {eta_min:.1f}min')
            if wandb: wandb.log({"loss": current_loss, "logits_loss": current_logits_loss, "aux_loss": current_aux_loss, "learning_rate": current_lr, "epoch_time": eta_min})
        # 只由主进程写文件，避免多个分布式进程同时覆盖同一份权重。
        if (step % args.save_interval == 0 or step == iters) and is_main_process():
            '''model.eval() 的作用：
                保存模型前调用 model.eval()，假设模型中有 Dropout，评估模式会关闭随机丢弃，
                使保存前的验证或推理结果保持稳定；如果模型中有 BatchNorm（Transformer中通常没有），评估模式会使用训练阶段
                保存的均值和方差，不再用当前批次更新统计量。保存完成后再调用 model.train()，恢复 Dropout，
                并让 BatchNorm 继续使用当前训练批次更新统计量。
            '''
            model.eval()
            moe_suffix = '_moe' if lm_config.use_moe else ''
            ckp = f'{args.save_dir}/{args.save_weight}_{lm_config.hidden_size}{moe_suffix}.pth'
            # 依次取出 DDP 和 torch.compile 包装下的原始模型，保持权重键名一致。
            '''model.module 的作用：
            这里的 module 不是 Python 的模块文件，而是 DistributedDataParallel 对象保存的属性，
            它指向被 DDP 包装的原始神经网络模型。
            单卡时：model = 原始模型，所以 raw_model = model；
            多卡时：model = DistributedDataParallel(原始模型)，其中 model.module = 原始模型，
            所以 raw_model = model.module，取出内部模型后再保存参数。
            '''
            raw_model = model.module if isinstance(model, DistributedDataParallel) else model

            '''getattr(raw_model, '_orig_mod', raw_model) 的作用：
            getattr(raw_model, '_orig_mod', raw_model) 的意思是：尝试读取 raw_model._orig_mod；
            如果启用了 torch.compile，编译包装对象通常有 _orig_mod 属性，结果会取出编译前的原始模型；
            如果没有启用 torch.compile，找不到 _orig_mod，就返回第三个参数 raw_model 本身。
            例如：compiled_model._orig_mod = original_model 时，结果是 original_model；
            raw_model 没有 _orig_mod 时，结果仍然是 raw_model。
            '''
            raw_model = getattr(raw_model, '_orig_mod', raw_model)

            state_dict = raw_model.state_dict()
            # 导出 CPU 上的 FP16 权重以减小文件；不会将训练中的模型本身改为 FP16。
            # PyTorch：save 将对象序列化；这里保存 state_dict 等状态，恢复时仍需用匹配的模型配置构建网络。
            '''v.half() 的作用：
            假设 state_dict 中某个权重 v 原本是 FP32，每个数占 4 字节，
            v.half() 会将它转换成 FP16，每个数占 2 字节；例如 1 GB 的 FP32 权重，
            导出后通常约占 0.5 GB。这里转换的是即将保存的副本，训练中的 raw_model 不会被改成 FP16。
            '''
            torch.save({k: v.half().cpu() for k, v in state_dict.items()}, ckp)
            # 另存用于续训的检查点，包含模型、优化器、缩放器和 epoch/step 等状态。
            # 检查点不保存累积中尚未用于更新参数的 .grad。
            lm_checkpoint(lm_config, weight=args.save_weight, model=model, optimizer=optimizer, scaler=scaler, epoch=epoch, step=step, wandb=wandb, save_dir='../checkpoints') # 保存模型权重和续训状态
            model.train()
            del state_dict

        del input_ids, labels, res, loss  # 释放本批次变量的引用，便于回收不再使用的内存。

    # 本轮批次数不能整除累积步数时，将末尾尚未提交的梯度再更新一次。
    # 此处沿用前面的损失缩放比例；尾部不足一组时不会按实际批次数重新归一化。
    # 这次更新发生在循环内的末批保存之后，不会触发再次保存。
    if last_step > start_step and last_step % args.accumulation_steps != 0:
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)


if __name__ == "__main__":
    # 命令行参数覆盖默认配置；下方 ../out、../dataset 等相对路径以运行时工作目录为准。
    parser = argparse.ArgumentParser(description="MiniMind Pretraining")
    # 输出位置与训练规模：batch_size 是每个进程每次读取的样本数。
    parser.add_argument("--save_dir", type=str, default="../out", help="模型保存目录")
    parser.add_argument('--save_weight', default='pretrain', type=str, help="保存权重的前缀名")
    parser.add_argument("--epochs", type=int, default=2, help="训练轮数")
    parser.add_argument("--batch_size", type=int, default=32, help="batch size")
    parser.add_argument("--learning_rate", type=float, default=5e-4, help="初始学习率")
    # 设备与精度；num_workers 实际控制 DataLoader 的数据加载子进程数，0 表示主进程加载。
    parser.add_argument("--device", type=str, default="cuda:0" if torch.cuda.is_available() else "cpu", help="训练设备")
    parser.add_argument("--dtype", type=str, default="bfloat16", help="混合精度类型")
    parser.add_argument("--num_workers", type=int, default=8, help="数据加载线程数")
    # 每 accumulation_steps 个小批次才更新一次参数；期间多次 backward 的梯度保留在参数 .grad 中并自动相加。
    # 例如设为 8 时，约用 8 个 batch 的平均梯度模拟一个更大的 batch；有效批量约为
    # batch_size × accumulation_steps × 进程数（完整累积窗口时）。
    parser.add_argument("--accumulation_steps", type=int, default=8, help="梯度累积步数")
    parser.add_argument("--grad_clip", type=float, default=1.0, help="梯度裁剪阈值")
    # 日志和保存间隔均以数据批次为单位，而不是以优化器更新次数为单位。
    parser.add_argument("--log_interval", type=int, default=100, help="日志打印间隔")
    parser.add_argument("--save_interval", type=int, default=1000, help="模型保存间隔")
    # 模型结构与输入长度：hidden_size 是 token 的隐藏向量维度，max_seq_len 以 token 计数。
    parser.add_argument('--hidden_size', default=768, type=int, help="隐藏层维度")
    parser.add_argument('--num_hidden_layers', default=8, type=int, help="隐藏层数量")
    parser.add_argument('--max_seq_len', default=340, type=int, help="训练的最大截断长度（中文1token≈1.5~1.7字符）")
    parser.add_argument('--use_moe', default=0, type=int, choices=[0, 1], help="是否使用MoE架构（0=否，1=是）")
    parser.add_argument("--data_path", type=str, default="../dataset/pretrain_t2t_mini.jsonl", help="预训练数据路径")
    # from_weight 只指定初始模型权重；from_resume 尝试恢复包含训练进度的检查点。
    parser.add_argument('--from_weight', default='none', type=str, help="基于哪个权重训练，为none则从头开始")
    parser.add_argument('--from_resume', default=0, type=int, choices=[0, 1], help="是否自动检测&续训（0=否，1=是）")
    parser.add_argument("--use_wandb", action="store_true", help="是否使用wandb")
    parser.add_argument("--wandb_project", type=str, default="MiniMind-Pretrain", help="wandb项目名")
    parser.add_argument("--use_compile", default=0, type=int, choices=[0, 1], help="是否使用torch.compile加速（0=否，1=是）")
    args = parser.parse_args()

    # ========== 1. 初始化环境和随机种子 ==========
    # 分布式启动时初始化进程组，并让每个进程使用本机对应编号的 GPU。
    local_rank = init_distributed_mode()
    if dist.is_initialized(): args.device = f"cuda:{local_rank}"
    # 用进程rank区分随机种子；相同启动配置下保持随机过程可复现。
    setup_seed(42 + (dist.get_rank() if dist.is_initialized() else 0))
    
    # ========== 2. 配置目录、模型参数、检查ckp ==========
    os.makedirs(args.save_dir, exist_ok=True)
    lm_config = MiniMindConfig(hidden_size=args.hidden_size, num_hidden_layers=args.num_hidden_layers, use_moe=bool(args.use_moe))
    # 未传入 model 时 lm_checkpoint 执行读取；找不到检查点时返回 None。
    ckp_data = lm_checkpoint(lm_config, weight=args.save_weight, save_dir='../checkpoints') if args.from_resume==1 else None # 有之前的检查点就续训，没有就从头开始
    
    # ========== 3. 设置混合精度 ==========
    device_type = "cuda" if "cuda" in args.device else "cpu"
    dtype = torch.bfloat16 if args.dtype == "bfloat16" else torch.float16
    # nullcontext 是一个空上下文管理器：进入和退出 with 代码块时都不执行额外操作，
    # 相当于给不需要特殊处理的 CPU 分支提供一个占位对象，让 CPU/GPU 共用 train_epoch 中的 with 写法。
    # PyTorch AMP：autocast 为运算选择适合的精度，不等于把所有张量永久改为半精度。
    # 这里沿用原 CUDA AMP 写法；新版统一接口为 torch.amp.autocast("cuda", dtype=...)。
    '''具体例子：
        nullcontext() 可以理解为“什么也不做”的 with 上下文：
        with nullcontext():
            result = model(input_ids, labels=labels)
        执行前后不会自动改变数据类型、开启混合精度或释放资源，只是让这段代码正常执行。
        当 device_type == "cpu" 时，autocast_ctx = nullcontext()，with autocast_ctx: 不改变运算精度；
        当 device_type == "cuda" 且 dtype 为 torch.bfloat16 时，使用 BF16 自动混合精度；
        当 device_type == "cuda" 且 dtype 为 torch.float16 时，使用 FP16 自动混合精度。
        因此 train_epoch 可以统一写成 with autocast_ctx:，不需要分别编写 CPU 和 GPU 两套代码。
    '''
    autocast_ctx = nullcontext() if device_type == "cpu" else torch.amp.autocast('cuda',dtype=dtype)
    
    # ========== 4. 配wandb ==========
    # Wandb（全称 Weights & Biases）是一个用于机器学习和深度学习的实验跟踪与可视化平台。它可以帮助开发者记录模型训练过程中的超参数、损失函数（Loss）和准确率（Accuracy）等指标.
    wandb = None
    if args.use_wandb and is_main_process():
        # 参数沿用 wandb 命名，实际使用 SwanLab；仅主进程创建和记录实验。
        import swanlab as wandb
        # 检查点中有实验 ID 时，继续写入同一次实验的记录。
        wandb_id = ckp_data.get('wandb_id') if ckp_data else None
        resume = 'must' if wandb_id else None
        wandb_run_name = f"MiniMind-Pretrain-Epoch-{args.epochs}-BatchSize-{args.batch_size}-LearningRate-{args.learning_rate}"
        wandb.init(project=args.wandb_project, name=wandb_run_name, id=wandb_id, resume=resume)
    
    # ========== 5. 定义模型、数据、优化器 ==========
    # 创建模型和 tokenizer；from_weight 不为 none 时，加载指定的初始权重。
    model, tokenizer = init_model(lm_config, args.from_weight, device=args.device)
    # 数据集读取 JSONL 的 text 字段，分词后添加 BOS/EOS，并截断或补齐到 max_seq_len。
    # input_ids 与 labels 形状均为 [批次大小, 序列长度]；labels 的 PAD 位置设为 -100。
    # 数据集不移动标签：模型内部用前一位置的输出预测后一位置的标签，并忽略 -100。
    '''返回结果示例：
        假设 JSONL 中第 0 条数据是 {"text": "I love AI"}，max_seq_len=8，
        tokenizer 编码后得到 [10, 11, 12]，并假设 BOS=1、EOS=2、PAD=0。
        train_ds[0] 会返回：
        input_ids = tensor([1, 10, 11, 12, 2, 0, 0, 0])
        labels    = tensor([1, 10, 11, 12, 2, -100, -100, -100])
        其中 input_ids 是模型输入，labels 是监督目标；-100 对应 PAD，计算 Loss 时会被忽略。
        单条样本形状为 [T]，经过 DataLoader 组成 batch 后，例如 batch_size=4，形状为 [4, 8]，
        也就是 [B, T]，随后传给 model(input_ids, labels=labels)。
    '''
    train_ds = PretrainDataset(args.data_path, tokenizer, max_length=args.max_seq_len)
    # 分布式采样器为各进程分配样本索引；单进程的随机索引在每轮训练前生成。
    # PyTorch：DistributedSampler 按 rank 分配样本索引；每轮 set_epoch(epoch) 更新一致的随机排列。
    # 例如，如果当前进程是 rank 0，它会负责读取数据集中索引为 0, 3, 6, ... 的样本。
    '''dist.is_initialized() 的作用：
        dist.is_initialized() 会返回当前进程组是否已经初始化完成：
        1. 单卡直接运行时，返回 False，train_sampler 被设置为 None，后面使用随机生成的 indices。
        2. 使用 torchrun 启动多卡训练并完成初始化时，返回 True，创建 DistributedSampler，
            每个 GPU 只读取自己负责的那部分数据，避免多个 GPU 重复读取相同样本。
     '''
    train_sampler = DistributedSampler(train_ds) if dist.is_initialized() else None
    # 仅 FP16 开启梯度缩放；BF16 的指数范围较大，这里不启用缩放。
    # PyTorch AMP：GradScaler 管理动态损失缩放；这里仅在 float16 下启用，bfloat16 分支禁用。
    # 新版统一接口为 torch.amp.GradScaler("cuda", enabled=...)。
    scaler = torch.amp.GradScaler(enabled=(args.dtype == 'float16'))
    # AdamW 维护参数的一阶/二阶矩估计，并使用解耦的权重衰减。
    optimizer = optim.AdamW(model.parameters(), lr=args.learning_rate)
    
    # ========== 6. 从ckp恢复状态 ==========
    start_epoch, start_step = 0, 0
    if ckp_data:
        # 续训权重覆盖初始化权重；同时恢复优化器与缩放器状态，而不只是模型参数。
        # PyTorch：load_state_dict 按参数/缓冲区名字恢复状态；strict=False 允许缺失/额外键，但不忽略同名张量形状不匹配。
        model.load_state_dict(ckp_data['model'])
        optimizer.load_state_dict(ckp_data['optimizer'])
        scaler.load_state_dict(ckp_data['scaler'])
        start_epoch = ckp_data['epoch'] # 续训时从上次保存的 epoch 开始；如果保存时 epoch=0，下一轮仍是 epoch=0。
        start_step = ckp_data.get('step', 0)
    
    # ========== 7. 编译和分布式包装 ==========
    # 先恢复原始模型的权重再包装，避免包装引入的键名前缀影响加载。
    if args.use_compile == 1:
        # torch.compile 是可选的性能优化：捕获并优化模型计算图，可能融合算子、减少 GPU 调用并提高吞吐量。
        # 它不是训练必需步骤；首次运行有编译开销，动态控制流或环境不兼容时可能编译中断。
        # 不启用时训练逻辑和模型结果不受影响，调试阶段通常保持关闭。
        model = torch.compile(model)
        Logger('torch.compile enabled')
    if dist.is_initialized():
        # DDP 在反向传播时同步各进程梯度，使各 GPU 上的模型保持一致。
        # PyTorch DDP：每个进程包装一份模型，在常规 DDP 前向/反向路径中同步梯度；数据切分由 sampler 负责。
        model = DistributedDataParallel(model, device_ids=[local_rank])
    
    # ========== 8. 开始训练 ==========
    for epoch in range(start_epoch, args.epochs):
        # 更新分布式采样器的 epoch，让不同轮次使用不同的打乱顺序。
        '''设置 DistributedSampler 当前的 epoch。
        
                    作用：
                    在分布式训练中，DistributedSampler 会负责：
                    1. 对整个数据集进行随机打乱；
                    2. 再把不同的数据分给不同 GPU。
        
                    set_epoch(epoch) 会把当前 epoch 编号加入随机种子的计算中，
                    从而保证每个 epoch 的数据顺序都不一样。
        
                    例如数据集：
                    [0, 1, 2, 3, 4, 5, 6, 7]
        
                    epoch = 0 时，可能打乱为：
                    [3, 0, 7, 2, 5, 1, 6, 4]
        
                    如果有 2 张 GPU，则可能分成：
                    GPU 0: [3, 7, 5, 6]
                    GPU 1: [0, 2, 1, 4]
        
                    epoch = 1 时，重新打乱为：
                    [6, 3, 0, 7, 2, 1, 5, 4]
        
                    再分成：
                    GPU 0: [6, 0, 2, 5]
                    GPU 1: [3, 7, 1, 4]
        
                    如果不调用 set_epoch(epoch)，
                    即使设置了 shuffle=True，不同 epoch 也可能使用相同的打乱顺序。
        '''
        train_sampler and train_sampler.set_epoch(epoch)
        # 用 epoch 固定本轮随机种子；单进程续训时可重建同一轮的样本排列。
        # PyTorch：randperm(n) 产生 0..n-1 的随机无重复排列，常用于打乱样本或 mini-batch 顺序。
        '''具体例子：
            假设 len(train_ds) == 6，样本下标是 [0, 1, 2, 3, 4, 5]，
            torch.randperm(6) 可能生成 tensor([3, 0, 5, 1, 4, 2])，
            再通过 .tolist() 转成 Python 列表：indices = [3, 0, 5, 1, 4, 2]。
            这个列表包含每个样本下标且没有重复，只是顺序被随机打乱；
            后面的 SkipBatchSampler 会按照这个顺序取样并组成训练批次。
        '''
        setup_seed(42 + epoch)
        indices = torch.randperm(len(train_ds)).tolist()
        # 只在恢复的第一轮跳过已经处理的批次，后续 epoch 从头读取。
        skip = start_step if (epoch == start_epoch and start_step > 0) else 0
        # 先对样本索引分批，再跳过 skip 个批次；跳过的批次无需加载和分词。
        # 默认保留末尾不足 batch_size 的一批样本。
        '''SkipBatchSampler 的作用：
        indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]，batch_size = 3，skip = 1 时，
        SkipBatchSampler 会先组成 [0, 1, 2]、[3, 4, 5]、[6, 7, 8]、[9] 四个批次，
        然后跳过第 1 个批次，DataLoader 实际只读取 [3, 4, 5]、[6, 7, 8]、[9]。
        续训时这样可以跳过已经训练过的批次，避免重复训练。分布式训练时，
        train_sampler 提供的每个进程专属索引会代替上面的 indices。
        '''
        batch_sampler = SkipBatchSampler(train_sampler or indices, args.batch_size, skip)
        # pin_memory 使用锁页内存，有助于向 GPU 传输数据；批次大小由 batch_sampler 决定。
        # PyTorch：DataLoader 从 Dataset 取样并组批；batch_sampler 已决定批次，pin_memory 可使 CPU 数据使用锁页内存。
        '''DataLoader 的作用：
            DataLoader 是一个可以逐批读取数据的对象：它根据 batch_sampler 提供的索引，
            从 train_ds 取出样本，再把多条样本分别整理成 input_ids 和 labels 批量张量。
            例如 batch_sampler 返回 [3, 4, 5]，假设：
            train_ds[3] = (tensor([1, 10, 11, 2, 0, 0, 0, 0]), tensor([1, 10, 11, 2, -100, -100, -100, -100]))
            train_ds[4] = (tensor([1, 20, 21, 22, 2, 0, 0, 0]), tensor([1, 20, 21, 22, 2, -100, -100, -100]))
            train_ds[5] = (tensor([1, 30, 31, 2, 0, 0, 0, 0]), tensor([1, 30, 31, 2, -100, -100, -100, -100]))
            DataLoader 会把它们整理成：input_ids.shape = [3, 8]，labels.shape = [3, 8]，
            其中 [3, 8] 的具体形状就是 3 行 8 列：
            input_ids = tensor([
                [1, 10, 11, 2,  0,    0,    0,    0],
                [1, 20, 21, 22, 2,    0,    0,    0],
                [1, 30, 31, 2,  0,    0,    0,    0]
            ])
            labels = tensor([
                [1, 10, 11, 2,  -100, -100, -100, -100],
                [1, 20, 21, 22, 2,  -100, -100, -100],
                [1, 30, 31, 2,  -100, -100, -100, -100]
            ])
            3 行表示 3 条样本，8 列表示每条样本的 8 个 token 位置；
            labels 与 input_ids 形状相同，但 PAD 位置的值为 -100，不参与 Loss 计算。
            然后 for step, (input_ids, labels) in enumerate(loader) 就能一次得到这两个批量张量，
            供 train_epoch 中的 model(input_ids, labels=labels) 使用。
            num_workers=args.num_workers 表示使用多个子进程并行准备数据，
            pin_memory=True 表示将 CPU 张量放入锁页内存，便于更快传输到 GPU。
        '''
        loader = DataLoader(train_ds, batch_sampler=batch_sampler, num_workers=args.num_workers, pin_memory=True)
        if skip > 0: 
            Logger(f'Epoch [{epoch + 1}/{args.epochs}]: 跳过前{start_step}个step，从step {start_step + 1}开始')
            # len(loader) 只包含剩余批次，加回 skip 才是完整轮次的长度，供学习率和日志使用。
            train_epoch(epoch, loader, len(loader) + skip, start_step, wandb)
        else:
            train_epoch(epoch, loader, len(loader), 0, wandb)
    
    # ========== 9. 清理分布进程 ==========
    if dist.is_initialized():
        # 等待所有进程完成训练后，再释放分布式通信资源。
        # PyTorch：barrier 等待所有进程到达同步点；所有 rank 都应参与，不能只在主进程调用。
        '''DataLoader 的作用：
            假设有 GPU 0 和 GPU 1 两个训练进程：
            1. GPU 0 先训练结束时，会停在 dist.barrier() 这里等待。
            2. GPU 1 训练结束并执行到同一个 barrier 后，两个进程才会同时继续执行。
            3. 两个进程都通过 barrier 后，再调用 dist.destroy_process_group()，
            统一销毁进程之间的通信组，避免某个进程提前退出导致其他进程通信异常。
        '''
        dist.barrier()
        # PyTorch：训练结束后销毁通信组，释放分布式后端资源。
        dist.destroy_process_group()
