# 训练公共设施：随机种子、分布式初始化、学习率、模型加载、检查点与断点续训采样。
"""
训练工具函数集合
"""
import os
import sys
__package__ = "trainer"
# 直接运行子目录脚本时将项目根加入模块搜索路径，以便导入 model、dataset、trainer。
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import random
import math
import numpy as np
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import Sampler
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification
from model.model_minimind import MiniMindForCausalLM

# 统计总参数并按配置估算 MoE 每个 token 激活的参数量，结果单位为百万。
def get_model_params(model, config):
    total = sum(p.numel() for p in model.parameters()) / 1e6
    n_routed = getattr(config, 'n_routed_experts', getattr(config, 'num_experts', 0))
    n_active = getattr(config, 'num_experts_per_tok', 0)
    n_shared = getattr(config, 'n_shared_experts', 0)
    expert = sum(p.numel() for n, p in model.named_parameters() if 'mlp.experts.0.' in n) / 1e6
    shared_expert = sum(p.numel() for n, p in model.named_parameters() if 'mlp.shared_experts.0.' in n) / 1e6
    base = total - (expert * n_routed) - (shared_expert * n_shared)
    active = base + (expert * n_active) + (shared_expert * n_shared)
    if active < total: Logger(f'Model Params: {total:.2f}M-A{active:.2f}M')
    else: Logger(f'Model Params: {total:.2f}M')


# 单进程直接返回 True；分布式环境只让全局 rank 0 负责日志和文件输出。
def is_main_process():
    return not dist.is_initialized() or dist.get_rank() == 0


# 在主进程输出日志，避免多卡训练重复打印。
def Logger(content):
    if is_main_process():
        print(content)


# 按训练进度计算余弦衰减：从 lr 降到 0.1*lr；此公式不包含 warmup。
def get_lr(current_step, total_steps, lr):
    return lr*(0.1 + 0.45*(1 + math.cos(math.pi * current_step / total_steps)))


# 读取 torchrun 设置的 RANK/LOCAL_RANK，建立 NCCL 通信组并绑定本进程 GPU。
'''作用示例：
直接运行 python train_pretrain.py 时，没有 RANK 环境变量，
os.environ.get("RANK", -1) 返回 -1，函数返回 0，使用单卡训练。
使用 torchrun --nproc_per_node=2 启动时，torchrun 会为每个进程设置 RANK 和 LOCAL_RANK：
RANK 用于标识进程在整个分布式任务中的编号，LOCAL_RANK 用于标识进程使用本机的哪张 GPU。
dist.init_process_group(backend="nccl") 建立 GPU 之间的通信组，
torch.cuda.set_device(local_rank) 则让当前进程只使用对应的 GPU。
'''
def init_distributed_mode():
    '''这一行的判断过程：
    os.environ 是系统环境变量字典；get("RANK", -1) 表示读取 RANK，找不到时使用默认值 -1。
    直接运行 python train_pretrain.py 时，RANK 不存在：
    get(...) -> -1，int(-1) == -1 -> True，于是 return 0，不初始化 DDP。
    使用 torchrun --nproc_per_node=2 启动时，RANK 会是 "0" 或 "1"：
    int("0") == -1 和 int("1") == -1 都是 False，于是继续初始化多卡通信。
    '''
    if int(os.environ.get("RANK", -1)) == -1:
        return 0  # 非DDP模式

    # PyTorch distributed：初始化进程间通信；NCCL 用于 GPU 集合通信，依赖启动器提供 rank/world_size 等配置。
    dist.init_process_group(backend="nccl")
    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    return local_rank


# 同步 Python、NumPy、PyTorch 随机种子，并设置 cuDNN 确定性选项以便复现实验。
def setup_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    # PyTorch：cuDNN deterministic 选择确定性算法；这不是所有 GPU 算子或跨设备完全一致的保证。
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

# 传入 model 时保存权重和续训状态；否则读取续训文件，不存在时返回 None。
# 先写 .tmp 再替换目标文件；续训状态包含优化器等，但不保存尚未提交的累积梯度。
def lm_checkpoint(lm_config, weight='full_sft', model=None, optimizer=None, epoch=0, step=0, wandb=None, save_dir='../checkpoints', **kwargs):
    os.makedirs(save_dir, exist_ok=True)
    moe_path = '_moe' if lm_config.use_moe else ''
    ckp_path = f'{save_dir}/{weight}_{lm_config.hidden_size}{moe_path}.pth'
    resume_path = f'{save_dir}/{weight}_{lm_config.hidden_size}{moe_path}_resume.pth'

    if model is not None: # 保存模式
        raw_model = model.module if isinstance(model, DistributedDataParallel) else model
        # torch.compile 可能包裹原模型；取 _orig_mod 保持导出权重的键名与普通模型一致。
        raw_model = getattr(raw_model, '_orig_mod', raw_model)
        state_dict = raw_model.state_dict()
        # 保存的是 CPU FP16 副本；训练进程中的原参数设备/精度不会因这些转换而整体改变。
        state_dict = {k: v.half().cpu() for k, v in state_dict.items()}
        ckp_tmp = ckp_path + '.tmp'
        # PyTorch：save 将对象序列化；这里保存 state_dict 等状态，恢复时仍需用匹配的模型配置构建网络。
        torch.save(state_dict, ckp_tmp)
        os.replace(ckp_tmp, ckp_path)
        wandb_id = None
        if wandb:
            if hasattr(wandb, 'get_run'):
                run = wandb.get_run()
                wandb_id = getattr(run, 'id', None) if run else None
            else:
                wandb_id = getattr(wandb, 'id', None)

        # 除模型外还保存优化器动量、epoch/step、world_size 和日志任务 ID；额外状态由 kwargs 带入。
        resume_data = {
            'model': state_dict,
            'optimizer': optimizer.state_dict(),
            'epoch': epoch,
            'step': step,
            'world_size': dist.get_world_size() if dist.is_initialized() else 1,
            'wandb_id': wandb_id
        }
        '''作用示例：
        kwargs={'scaler': scaler, 'extra_step': 10} 时，
        scaler 具有 state_dict()，因此保存为 resume_data['scaler'] = scaler.state_dict()；
        extra_step 没有 state_dict()，因此直接保存为 resume_data['extra_step'] = 10。
        如果 value 是 DDP 或 torch.compile 包装的模型，还要先取出原始模型再保存参数。
        '''
        for key, value in kwargs.items():
            if value is not None:
                if hasattr(value, 'state_dict'):
                    raw_value = value.module if isinstance(value, DistributedDataParallel) else value
                    raw_value = getattr(raw_value, '_orig_mod', raw_value)
                    resume_data[key] = raw_value.state_dict()
                else:
                    resume_data[key] = value

        resume_tmp = resume_path + '.tmp'
        torch.save(resume_data, resume_tmp)
        os.replace(resume_tmp, resume_path)
        del state_dict, resume_data
        # PyTorch：empty_cache 释放缓存分配器中未占用的显存，不会释放仍被张量引用的显存。
        torch.cuda.empty_cache()
    else:  # 加载模式
        if os.path.exists(resume_path):
            # PyTorch：load 读取序列化对象；map_location 指定张量加载设备，CPU 加载可避免先占用 GPU 显存。
            ckp_data = torch.load(resume_path, map_location='cpu')
            saved_ws = ckp_data.get('world_size', 1)
            current_ws = dist.get_world_size() if dist.is_initialized() else 1
            # GPU 数量变化时按 world_size 比例近似换算已消费的批次进度，不保证重放出完全相同的样本顺序。
            if saved_ws != current_ws:
                ckp_data['step'] = ckp_data['step'] * saved_ws // current_ws
                Logger(f'GPU数量变化({saved_ws}→{current_ws})，step已自动转换为{ckp_data["step"]}')
            return ckp_data
        return None


# 创建训练模型和分词器；from_weight="none" 时随机初始化，否则按文件名读取已有权重。
def init_model(lm_config, from_weight='pretrain', tokenizer_path='../model', save_dir='../out', device='cuda'):
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
    model = MiniMindForCausalLM(lm_config)

    if from_weight!= 'none':
        moe_suffix = '_moe' if lm_config.use_moe else ''
        weight_path = f'{save_dir}/{from_weight}_{lm_config.hidden_size}{moe_suffix}.pth'
        weights = torch.load(weight_path, map_location=device)
        # PyTorch：load_state_dict 按参数/缓冲区名字恢复状态；strict=False 允许缺失/额外键，但不忽略同名张量形状不匹配。
        model.load_state_dict(weights, strict=False)

    get_model_params(model, lm_config) # 统计模型总参数量
    Logger(f'Trainable Params: {sum(p.numel() for p in model.parameters() if p.requires_grad) / 1e6:.3f}M')
    return model.to(device), tokenizer


# 将样本索引组成批次并跳过已训练批次；最后不完整的一批仍会保留。
class SkipBatchSampler(Sampler):
    # 保存底层样本索引源、每批大小，以及需要跳过的完整批次数。
    def __init__(self, sampler, batch_size, skip_batches=0):
        self.sampler = sampler
        self.batch_size = batch_size
        self.skip_batches = skip_batches

    # 消费 sampler 的索引并组批，跳过 skip_batches 个完整批次后开始 yield。
    def __iter__(self):
        batch = []
        skipped = 0
        for idx in self.sampler:
            batch.append(idx)
            if len(batch) == self.batch_size:
                if skipped < self.skip_batches:
                    skipped += 1
                    batch = []
                    continue
                yield batch
                batch = []
        if len(batch) > 0 and skipped >= self.skip_batches:
            yield batch

    # 返回跳过续训批次后剩余的批次数。
    def __len__(self):
        total_batches = (len(self.sampler) + self.batch_size - 1) // self.batch_size
        return max(0, total_batches - self.skip_batches)


# 包装外部奖励模型和分词器，提供对话回答评分接口。
class LMForRewardModel:
    # 按路径加载支持 get_score 的模型与 tokenizer，再迁移到指定设备并切换评估模式。
    def __init__(self, model_path, device="cuda", dtype=torch.float16):
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(model_path, torch_dtype=dtype, trust_remote_code=True)
        self.model = self.model.to(device).eval()
        self.device = device

    # 将历史和当前回答整理成评分消息，调用奖励模型并将分数截断到 [-3,3]。
    '''
    【get_score：多轮对话如何整理后交给奖励模型评分】

    示例输入：
        messages = [
            {"role": "user", "content": "我有三个苹果。"},
            {"role": "assistant", "content": "好的，你有三个苹果。"},
            {"role": "user", "content": "再买两个，一共有几个？"}
        ]
        response = "一共有五个苹果，因为3+2=5。"
    调用：reward = reward_model.get_score(messages, response)。
    messages 是生成回答前的上下文，最后一条约定为当前问题；新生成的回答单独传入 response。
    不要把 response 追加到 messages 后再调用，否则它会被误当成 last_query。

    第 1 步：messages[:-1] 去掉最后的当前问题，只取前两条历史消息。
        列表推导把每条历史消息写成“角色: 内容”：
            ["user: 我有三个苹果。", "assistant: 好的，你有三个苹果。"]
        join 用换行连接它们，因此 history_text 是下面这个字符串：
            user: 我有三个苹果。
            assistant: 好的，你有三个苹果。
        这里不会删除原始 messages 的元素，只是读取一个切片。

    第 2 步：messages[-1]['content'] 取出当前问题。
        last_query = "再买两个，一共有几个？"
        注意：这里直接取最后一条的 content，不会检查其 role 是否为 user。

    第 3 步：本例 history_text 非空，拼接“历史 + 说明文字 + 当前问题”。
        message_context 的完整文本是：
            user: 我有三个苹果。
            assistant: 好的，你有三个苹果。
            以上是对话历史。我的新问题是：
            再买两个，一共有几个？
        这一步把多轮历史压成一段 user 文本；原历史中的角色名保留为文本里的标签，
        不再作为多个独立的 role 字段传给外部奖励模型。

    第 4 步：将拼好的上下文与待评分回答组成恰好两条消息。
        eval_messages = [
            {"role": "user", "content": message_context},
            {"role": "assistant", "content": "一共有五个苹果，因为3+2=5。"}
        ]
        第一条告诉评分模型“历史和问题是什么”，第二条告诉它“要评价的回答是什么”。

    第 5 步：调用外部奖励模型自身的评分接口。
        score = self.model.get_score(self.tokenizer, eval_messages)
        self.model 是已加载的奖励模型，这里只请求它给分，不在此处训练它。
        假设这一次得到 score=4.2；这是为了演示截断而假设的分数，
        并不表示这段回答实际一定得到 4.2，也不是用字符串规则直接算出 4.2。
        @torch.no_grad() 使调用过程不记录用于反向传播的梯度图。

    第 6 步：执行 max(min(score, 3.0), -3.0)，把分数限制在 [-3,3]。
        本例 score=4.2：先 min(4.2,3.0)=3.0，再 max(3.0,-3.0)=3.0。
        若 score=-4.5：先 min(-4.5,3.0)=-4.5，再 max(-4.5,-3.0)=-3.0。
        若 score=1.2：先 min(1.2,3.0)=1.2，再 max(1.2,-3.0)=1.2。
    示例输出：本例最终返回 3.0；函数返回的是一个评分值，不是 eval_messages。
              这个操作只是截断，区间内分数保持原值，不是归一化或转换成概率。

    单轮分支：若 messages=[{"role":"user","content":"1+1等于几？"}]，response="等于2。"，
        messages[:-1] 是空列表，join 得到 history_text=""；
        last_query="1+1等于几？"，message_context 直接取 last_query，不添加历史说明。
        送入外部评分模型的是：
            [{"role":"user","content":"1+1等于几？"},
             {"role":"assistant","content":"等于2。"}]
        评分与截断步骤不变。
    空列表分支：若 messages=[]，history_text、last_query、message_context 都为空字符串；
                此包装函数仍把空 user 内容和 response 交给外部模型，评分是否可用取决于模型。
    '''
    @torch.no_grad()
    def get_score(self, messages, response):
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages[:-1]])
        last_query = messages[-1]['content'] if messages else ""
        message_context = f"{history_text}\n以上是对话历史。我的新问题是：\n{last_query}" if history_text else last_query
        '''
        这里本质上是把多轮历史压成一段 user 文本，原历史中的角色名保留为文本里的标签，
        不再作为多个独立的 role 字段传给外部奖励模型。
        举例：
        messages = [
            {"role": "user", "content": "我有三个苹果。"},
            {"role": "assistant", "content": "好的，你有三个苹果。"},
            {"role": "user", "content": "再买两个，一共有几个？"}
        ]
        则eval_messages = [
            {"role": "user", "content": "user: 我有三个苹果。\nassistant: 好的，你有三个苹果。\n以上是对话历史。我的新问题是：\n再买两个，一共有几个？"},
            {"role": "assistant", "content": "一共有五个苹果，因为3+2=5。"}
        ]
        '''
        eval_messages = [
            {"role": "user", "content": message_context},
            {"role": "assistant", "content": response}
        ]
        # 调用外部奖励模型自身的评分接口，得到一个浮点数 score。
        score = self.model.get_score(self.tokenizer, eval_messages)
        # 通过 max(min(score, 3.0), -3.0) 将分数限制在 [-3,3] 区间内。
        return max(min(score, 3.0), -3.0)
