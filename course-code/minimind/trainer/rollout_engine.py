# 在线采样接口：统一本地 PyTorch 与远端 SGLang 的 token、旧策略概率和有效位置掩码。
# 采样结果用于构造训练目标；策略更新时还需重新前向计算带梯度的 log 概率。
"""
# 如果使用sglang加速，需通过以下命令首先启动（transformers格式）模型：
python -m sglang.launch_server --model-path ./minimind-3 --attention-backend triton --host 0.0.0.0 --port 8998
"""
'''
【语句示例：import os】
使用示例：os.path.abspath("./sglang_ckpt") 把共享权重目录变成绝对路径。本句只导入路径工具，不创建目录或写文件。
'''
import os
'''
【语句示例：import sys】
使用示例：直接运行 trainer 下的脚本时，需要修改 sys.path 才能找到项目包。本句导入 sys，稍后添加项目根路径。
'''
import sys

'''
【语句示例：__package__】
输入：此文件所在包为 trainer。赋值后 __package__="trainer"，声明包上下文，不会更改磁盘目录。
'''
__package__ = "trainer"
# 直接运行子目录脚本时将项目根加入模块搜索路径，以便导入 model、dataset、trainer。
'''
【语句示例：sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))】
输入例：__file__=/project/minimind/trainer/rollout_engine.py。dirname 得到 trainer，join(..) 指向上一级，abspath 得到项目根，再 append 到 sys.path，使项目模块可被导入。
'''
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

'''
【语句示例：import requests】
使用示例：requests.post("http://localhost:8998/generate",json=payload) 可向服务请求生成。本句只导入 HTTP 库，不发出网络请求。
'''
import requests
'''
【语句示例：import torch】
使用示例：torch.tensor([[1,2]]) 创建 [1,2] 张量。导入 PyTorch，用于 token 编号、概率、掩码与权重操作。
'''
import torch
'''
【语句示例：import torch.distributed as dist】
使用示例：普通单进程 dist.is_initialized() 为 False；多卡初始化后可调用 dist.broadcast 同步状态。这里只建立模块别名。
'''
import torch.distributed as dist
'''
【语句示例：from abc import ABC, abstractmethod】
使用示例：继承 ABC 并用 abstractmethod 标记 rollout，可要求具体引擎实现该方法。导入后只提供定义工具，不创建引擎。
'''
from abc import ABC, abstractmethod
'''
【语句示例：from contextlib import nullcontext】
使用示例：未传 autocast_ctx 时，with nullcontext(): 正常执行代码，不切换精度。导入空上下文管理器供本地采样使用。
'''
from contextlib import nullcontext
'''
【语句示例：from dataclasses import dataclass】
使用示例：@dataclass 自动为 RolloutResult 生成按字段赋值的构造方法和可读的 repr；它不会计算 logp 或验证张量形状。
'''
from dataclasses import dataclass
'''
【语句示例：from typing import List, Optional, Tuple】
使用示例：List[str] 描述回答文本列表，Optional[Tensor] 表示可传张量或 None；Tuple 在当前文件中没有实际使用。类型标注不是运行时自动转换。
'''
from typing import List, Optional, Tuple
'''
【语句示例：from torch import Tensor】
使用示例：input_ids: Tensor 提示调用者传入 PyTorch 张量。这里只引入类型名，input_ids 的值由调用方提供。
'''
from torch import Tensor
'''
【语句示例：from torch.nn.parallel import DistributedDataParallel】
使用示例：若 policy_model 为 DDP 包装，policy_model.module 是内部模型。本句导入用于 isinstance 判断的类，不初始化分布式进程组。
'''
from torch.nn.parallel import DistributedDataParallel
'''
【语句示例：from transformers import AutoTokenizer】
使用示例：AutoTokenizer.from_pretrained("../model") 加载本地分词器。这里只导入类，SGLang 引擎构造时才实际加载。
'''
from transformers import AutoTokenizer


# ===== 计算每个 token 的 logprob =====
# 返回末尾 n_keep 个目标 token 的 log 概率 [B,n_keep]；预测位置比目标位置提前 1。
# 函数自身不关闭梯度，调用方可在训练时求导、在采样时使用 no_grad。
'''
【compute_per_token_logps：完整序列 → 回答中每个 token 的 log 概率】
输入：input_ids=[[1,3,1,2]]，形状 [1,4]；n_keep=2，表示只评估末尾回答 [1,2]；词表大小 V=4。
第 1 步：请求模型只返回最后 n_keep+1=3 个位置的 logits，即原序列位置 1、2、3。
第 2 步：删掉最后一个预测位置，留下位置 1、2，它们恰好预测位置 2、3 的目标 token 1、2。
第 3 步：假设这两个位置 logits 分别是 [0,ln(2),0,0] 和 [0,0,ln(3),0]。
第一行 softmax=[1/5,2/5,1/5,1/5]；第二行=[1/6,1/6,3/6,1/6]。
第 4 步：按真实目标编号 1、2 取对应概率，得到 [0.4,0.5]，再取自然对数。
输出 tensor([[-0.9162907,-0.6931472]])，形状 [1,2]；不是每个位置的整个词表分布。
实现实际用 log_softmax 再 gather，避免先 softmax 再 log 的数值问题。
约定有效 n_keep 不超过可对齐的后续 token 数；正常完整序列至少有一个提示 token。
本函数不自动 no_grad；外层若允许梯度，输出可用于反传；本地 rollout 则在 no_grad 内调用它。
'''
def compute_per_token_logps(model, input_ids: Tensor, n_keep: int, attention_mask: Optional[Tensor] = None) -> Tensor:
    '''
    【语句示例：if n_keep <= 0:】
    输入 n_keep=0，不需要评估任何回答 token，条件成立，进入空结果分支；n_keep=2 则继续正常前向。
    '''
    if n_keep <= 0:
        '''
        【语句示例：return input_ids.new_empty((input_ids.size(0), 0), dtype=torch.float32)】
        输入 input_ids 形状 [2,4]、n_keep=0。new_empty((2,0),dtype=float32) 返回同设备的 [2,0] 空张量，没有元素，也不会调用模型；不是一个填满随机值的非空结果。
        '''
        return input_ids.new_empty((input_ids.size(0), 0), dtype=torch.float32)
    '''
    【语句示例：unwrapped】
    输入模型被 DDP 包装时取 model.module，普通模型直接保留。输出 unwrapped 与原模型共享参数，不是另外复制了一份旧策略。
    '''
    unwrapped = model.module if isinstance(model, DistributedDataParallel) else model
    # PyTorch：inference_mode 创建的张量受自动求导限制；在该模式外 detach().clone() 可得到独立普通张量。
    # PyTorch：detach 切断此张量的梯度历史，但仍可能共享存储；需要独立副本时再 clone()。
    '''
    【语句示例：input_ids】
    输入 input_ids 若来自 inference_mode，is_inference() 为 True，则 detach().clone() 在通常的非 inference 上下文中得到普通独立张量；否则复用原输入。本句不冻结模型参数，若外层仍在 inference_mode 则 clone 仍受该模式控制。
    '''
    input_ids = input_ids.detach().clone() if input_ids.is_inference() else input_ids
    # 保留 n_keep+1 个预测位置，再去掉最后一个位置，与末尾 n_keep 个真实 token 对齐。
    '''
    【语句示例：logits】
    输入 ids=[[1,3,1,2]]、n_keep=2。logits_to_keep=3 让模型只投影最后三处隐藏状态，输出 [1,3,4]。
    [:, :-1, :] 去掉最后一处，得到 [1,2,4]；最后一处预测的是当前序列之外的新 token，没有对应标签。
    留下的位置分别预测末尾 [1,2]，所以要先多保留一个位置，而不能直接只取最后 n_keep 个 logits。
    '''
    logits = unwrapped(input_ids, attention_mask=attention_mask, logits_to_keep=n_keep + 1).logits[:, :-1, :]
    '''
    【语句示例：per_token_logps】
    输入：尚未处理任何样本行。建立 per_token_logps=[]；每处理一行加入一个长度 R 的张量，最后沿批次维 stack。
    '''
    per_token_logps = []
    '''
    【语句示例：for logits_row, ids_row in zip(logits, input_ids[:, -n_keep:]):】
    输入 logits=[B,R,V]、input_ids[:, -n_keep:]=[B,R]。zip 同时遍历两者的批次行；B=1 时拿到 logits_row=[2,4]、ids_row=[1,2]，两个目标依次对应两行 logits。
    '''
    for logits_row, ids_row in zip(logits, input_ids[:, -n_keep:]):
        '''
        【语句示例：ids_row】
        输入当前行 ids_row=[1,2]。若仍是 inference 张量则 detach().clone()，通常得到可被 autograd 保存作索引的独立普通张量；否则原样使用，编号及形状 [2] 不变。
        '''
        ids_row = ids_row.detach().clone() if ids_row.is_inference() else ids_row
        # gather 沿词表轴读取 ids_row 指定的 token：[R,V] 与 [R,1] 索引得到 [R,1]，再压成 [R]。
        '''
        【语句示例：per_token_logps.append(torch.gather(logits_row.log_softmax(dim=-1), 1, ids_row.unsqueeze(1)).squeeze(1))】
        输入 logits_row=[[0,ln(2),0,0],[0,0,ln(3),0]]，ids_row=[1,2]。
        第 1 步：log_softmax(dim=-1) 得 [2,4] 的 log 概率表。
        第 2 步：ids_row.unsqueeze(1)=[[1],[2]]，形状 [2,1]。
        第 3 步：gather(...,dim=1) 在第一行选第 1 列、第二行选第 2 列，得到 [[ln(0.4)],[ln(0.5)]]。
        第 4 步：squeeze(1) 变成 [-0.9162907,-0.6931472]；append 后列表中增加这一条样本结果。
        '''
        per_token_logps.append(
            torch.gather(logits_row.log_softmax(dim=-1), 1, ids_row.unsqueeze(1)).squeeze(1)
        )
    '''
    【语句示例：return torch.stack(per_token_logps)】
    输入 per_token_logps=[tensor([-0.9163,-0.6931]),tensor([-0.4,-0.2])]。stack 默认 dim=0，输出 [[-0.9163,-0.6931],[-0.4,-0.2]]，形状 [2,2]；不会把两条回答拼成一条长序列。
    '''
    return torch.stack(per_token_logps)


# ===== Rollout 结果 =====
# 采样结果容器；output_ids 包含提示，completion_ids 仅含续写，mask 标出续写有效位置。
'''
【RolloutResult 数据类：六个字段如何一起表示一次采样结果】
输入示例（本地后端，PAD=0，EOS=2，B=2、P=3、R=3）：
result=RolloutResult(
    output_ids=tensor([[0,11,12,21,2,2],[13,14,15,31,32,2]]),
    completion_ids=tensor([[21,2,2],[31,32,2]]),
    per_token_logps=tensor([[-0.7,-0.2,-2.0],[-0.4,-0.8,-0.1]]),
    completions=["答案一","答案二"],
    prompt_lens=tensor([3,3]),
    completion_mask=tensor([[1,1,1],[1,1,1]]))
步骤：dataclass 生成的 __init__ 将六个参数赋给六个同名属性，不重新生成或分词。
输出：result 是对象；result.output_ids 取到 [2,6] 完整序列，result.completions 取到两条文字。
编号、解码文字和概率为教学假设，不是实际模型记录；六个字段的构造方式由后端决定。
本地提前结束行继续填 EOS，completion_mask 全 1；后续 PPO 才排除第一个 EOS 后的位置。
SGLang 会去掉提示左 PAD 再右补齐，prompt_lens 可变，completion_mask 明确标出回答长度。
'''
@dataclass
class RolloutResult:
    '''
    【语句示例：output_ids】
    字段示例：output_ids=[[0,11,12,21,2,2],[13,14,15,31,32,2]]，形状 [2,6]。包含提示和生成回答；Tensor 标注本身不创建张量。
    '''
    output_ids: Tensor
    '''
    【语句示例：completion_ids】
    字段示例：completion_ids=[[21,2,2],[31,32,2]]，形状 [2,3]。只有回答部分；不要把它与完整 output_ids 混用来计算提示偏移。
    '''
    completion_ids: Tensor
    '''
    【语句示例：per_token_logps】
    字段示例：per_token_logps=[[-0.7,-0.2,-2.0],[-0.4,-0.8,-0.1]]，形状 [2,3]。每个数对应同位置回答 token 的 log 概率，不是奖励分数。
    '''
    per_token_logps: Tensor
    '''
    【语句示例：completions】
    字段示例：completions=["答案一","答案二"]，是长度 2 的 Python 字符串列表。用于奖励评分和调试；不能把字符串长度直接当成 token 数。
    '''
    completions: List[str]
    '''
    【语句示例：prompt_lens】
    字段示例：本地 prompt_lens=[3,3] 表示补齐后的提示宽度；SGLang 对同一组输入可为 [2,3]，表示去 PAD 后各题提示长度。它用于确定回答的起始位置。
    '''
    prompt_lens: Tensor
    '''
    【语句示例：completion_mask】
    字段示例：本地 completion_mask=[[1,1,1],[1,1,1]]；远端变长回答可为 [[1,1,0],[1,1,1]]。不能仅凭这个字段名就假设所有后端都会屏蔽 EOS 后的位置。
    '''
    completion_mask: Tensor


# ===== Rollout 引擎抽象基类 =====
# 采样后端抽象接口；子类必须实现生成轨迹与更新策略两个操作。
'''
【RolloutEngine 抽象类示例】输入想创建一个统一采样器。直接 RolloutEngine() 会因 rollout/update_policy 仍为抽象方法而失败；具体子类实现两个方法后才可实例化。训练端只需调用 engine.rollout(...)，输出统一的 RolloutResult，而无须知道后端使用本地模型还是 HTTP。
'''
class RolloutEngine(ABC):
    '''
    【语句示例：tokenizer】
    输入：抽象基类尚未绑定分词器。类属性 tokenizer=None；Torch/SGLang 构造函数随后各自设置实例的 self.tokenizer，不是此处加载模型文件。
    '''
    tokenizer = None
    
    # 按提示采样多个回答，返回完整 token、回答 token、旧策略 log 概率和有效位置等信息。
    '''
    【抽象 rollout 方法示例】约定输入 prompt_ids=[B,P]、attention_mask=[B,P]、每题采样数 G、最大新增长度。子类应返回共 B*G 条结果，例如 B=2、G=3 时 completion_ids 第一维为 6。本方法只定义接口，没有生成步骤；实际输出由子类实现。
    '''
    @abstractmethod
    def rollout(self, prompt_ids: Tensor, attention_mask: Tensor, num_generations: int, max_new_tokens: int, temperature: float = 0.8) -> RolloutResult:
        '''
        【语句示例：pass】
        输入：抽象方法体若被显式调用，pass 什么也不做，隐式返回 None。正常流程调用子类覆盖的方法；不能依赖这里得到 RolloutResult。
        '''
        pass
    
    # 让采样引擎使用更新后的策略：本地替换引用，远端则导出权重并通知服务加载。
    '''
    【抽象 update_policy 方法示例】输入训练更新后的 Actor。接口要求引擎切换到当前策略；本地实现更换对象引用，SGLang 实现导出权重并请求远端加载。基类本身不执行同步，也不规定必须返回同一类型。
    '''
    @abstractmethod
    def update_policy(self, model: torch.nn.Module):
        '''
        【语句示例：pass】
        输入：抽象更新方法被显式调用。pass 只占位，返回 None，无文件写入或模型更新；必须由具体后端实现。
        '''
        pass


# ===== PyTorch 原生推理引擎 =====
# 直接使用训练进程内的 PyTorch 模型生成，并额外前向获取逐 token log 概率。
'''
【TorchRolloutEngine 类示例：训练进程内生成并评分】
输入：已有 Actor、对应 tokenizer、device="cpu"、autocast_ctx=None。
第 1 步：engine=TorchRolloutEngine(actor,tokenizer,"cpu")，只保存引用，不加载第二份网络。
第 2 步：传入提示 [[0,11,12],[13,14,15]] 和 mask=[[0,1,1],[1,1,1]]，每题生成 1 条。
第 3 步：假设生成 [[21,2,2],[31,32,2]]，拼回提示得 [2,6] 完整序列。
第 4 步：额外前向提取 [2,3] 原模型 logp，解码文本并封装六个字段。
输出：RolloutResult；训练端以后用当前 Actor 的新 logp 与这里保存的旧 logp 比较。
'''
class TorchRolloutEngine(RolloutEngine):
    # 保存策略模型、分词器、设备及可选 autocast 上下文，供本地生成调用。
    '''
    【TorchRolloutEngine.__init__ 示例】输入 actor 对象、tokenizer、"cpu"、None。依次保存到四个属性；输出是初始化好的 engine，__init__ 返回 None。不执行 .to(device)、eval、generate 或权重复制，模型与输入的实际设备由调用方安排。
    '''
    def __init__(self, policy_model: torch.nn.Module, tokenizer, device: str = "cuda", autocast_ctx=None):
        '''
        【语句示例：self.policy_model】
        输入 policy_model=actor。self.policy_model 保存对同一个对象的引用，Actor 若被优化器原地更新，共享引用可直接看到新参数。
        '''
        self.policy_model = policy_model
        '''
        【语句示例：self.tokenizer】
        输入与 Actor 匹配的 tokenizer。保存到 self.tokenizer，后面读取 pad/eos 编号并 batch_decode，不在此处重新训练分词器。
        '''
        self.tokenizer = tokenizer
        '''
        【语句示例：self.device】
        输入 device="cuda:0"，保存为 self.device。当前 rollout 方法并不使用该字符串自动移动输入或模型，因此这不是一次 .to("cuda:0")。
        '''
        self.device = device
        '''
        【语句示例：self.autocast_ctx】
        输入 autocast_ctx=None 则存 None；若调用方传入混合精度上下文则保存该对象，生成时进入它。此句尚未切换精度。
        '''
        self.autocast_ctx = autocast_ctx
    
    # 按提示采样多个回答，返回完整 token、回答 token、旧策略 log 概率和有效位置等信息。
    '''
    【TorchRolloutEngine.rollout：提示 → generate → 旧概率 → 完整结果】
    输入 prompt_ids=[[0,11,12],[13,14,15]]，attention_mask=[[0,1,1],[1,1,1]]，G=1、max_new_tokens=3。
    步骤 1：解包 DDP，在 no_grad 和可选 autocast 中调用 generate。
    步骤 2：假设新增 token=[[21,2,2],[31,32,2]]；第一条先遇 EOS 后继续填 EOS，第二条第三步结束。
    步骤 3：取 P=3，切掉完整序列的前 3 列，取得回答 [2,3]。
    步骤 4：再前向得到每个回答 token 的 logp，例如 [[-0.7,-0.2,-2.0],[-0.4,-0.8,-0.1]]。
    步骤 5：假设解码为 ["答案一","答案二"]，返回 RolloutResult：
    output_ids=[[0,11,12,21,2,2],[13,14,15,31,32,2]]，completion_ids=[[21,2,2],[31,32,2]]，
    per_token_logps=上述 [2,3] 张量，completions=上述文本，prompt_lens=[3,3]，completion_mask 全 1。
    数值和文字仅为示例。no_grad 不自动 eval，因此模型模式沿用调用前状态；旧 logp 来自原模型分布，
    不是温度及其它采样过滤后的概率。PPO 随后根据第一个 EOS 再确定有效回答 mask。
    '''
    def rollout(self, prompt_ids: Tensor, attention_mask: Tensor, num_generations: int, max_new_tokens: int, temperature: float = 0.8) -> RolloutResult:
        '''
        【语句示例：model】
        输入 self.policy_model 被 DDP 包装则取 .module，否则直接使用本身。generate 调用解包后的模型，不创建网络副本。
        '''
        model = self.policy_model.module if isinstance(self.policy_model, DistributedDataParallel) else self.policy_model
        '''
        【语句示例：ctx】
        输入 self.autocast_ctx=None，选择 nullcontext()；如果已有上下文，则使用原对象。输出 ctx 可用于 with，控制生成和随后的概率前向精度。
        '''
        ctx = self.autocast_ctx if self.autocast_ctx else nullcontext()
        # PyTorch：no_grad 中的运算不建立反向图，用于参考模型/采样以节省显存；不会自动切换 eval 模式。
        '''
        【语句示例：with torch.no_grad(), ctx:】
        输入既有提示和模型。进入 torch.no_grad() 禁用梯度记录，再进入 ctx；不会因此自动关闭 Dropout，也不保证输入一定变成普通非 inference 张量。
        '''
        with torch.no_grad(), ctx:
            '''
            【语句示例：output_ids】
            输入 B=2、num_generations=2 时，repeat_interleave(dim=0) 将提示按 [p0,p0,p1,p1] 排列，
            mask 同顺序复制，形状由 [2,P] 变 [4,P]。所以 generate 的 num_return_sequences 保持 1，避免重复扩增。
            假设 G=1、本例 P=3、生成 3 个 token，output_ids=[[0,11,12,21,2,2],[13,14,15,31,32,2]]。
            do_sample=True 使用随机采样，temperature=0.8 影响候选分布；max_new_tokens 是上限，遇全批结束可提前停。
            MiniMind 的 generate 会给已结束行继续填 EOS；传入 pad_token_id 不代表它一定用 PAD 填这些位置。
            clone 创建独立结果张量；这里位于 no_grad 而非 inference_mode，通常也解除 generate 内 inference 张量的限制。
            '''
            output_ids = model.generate(
                input_ids=prompt_ids.repeat_interleave(num_generations, dim=0),
                attention_mask=attention_mask.repeat_interleave(num_generations, dim=0),
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=temperature,
                num_return_sequences=1,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            ).clone()  # [B*num_gen, P+R]
            '''
            【语句示例：prompt_len】
            输入 prompt_ids 形状 [2,3]。size(1)=3，prompt_len 取补齐后的宽度，包括第一条左侧的 PAD；不是第一条真实提示长度 2。
            '''
            prompt_len = prompt_ids.size(1)
            '''
            【语句示例：completion_ids】
            输入 output_ids 第一行 [0,11,12,21,2,2]、prompt_len=3。[:,3:] 得 [21,2,2]；完整 completion_ids=[[21,2,2],[31,32,2]]，形状 [2,3]。
            '''
            completion_ids = output_ids[:, prompt_len:]  # [B*num_gen, R]
            # 这里重新评估生成序列的原始模型 log 概率，并非直接读取温度/top-p 过滤后的采样概率。
            '''
            【语句示例：full_mask】
            输入 PAD=0、output_ids=[[0,11,12,21,2,2],[13,14,15,31,32,2]]。!=0 后转 long 得 [[0,1,1,1,1,1],[1,1,1,1,1,1]]。此实现按编号识别 PAD，假设 PAD 与 EOS 可区分；它不会排除重复的 EOS。
            '''
            full_mask = (output_ids != self.tokenizer.pad_token_id).long()
            '''
            【语句示例：per_token_logps】
            输入完整 [2,6] 序列和回答宽度 3。compute_per_token_logps 保留 4 个预测位置再去尾，提取末尾 3 个真实 token 的原模型 logp，输出 [2,3]；这里不套用 temperature=0.8。
            '''
            per_token_logps = compute_per_token_logps(self.policy_model, output_ids, completion_ids.size(1), attention_mask=full_mask)
        '''
        【语句示例：completions】
        输入 completion_ids=[[21,2,2],[31,32,2]]。batch_decode 跳过 EOS 等特殊 token，假设得到 ["答案一","答案二"]。这是假想编号与文字的对应，不声称真实 tokenizer 的 21 就是“答案一”。
        '''
        completions = self.tokenizer.batch_decode(completion_ids, skip_special_tokens=True)
        '''
        【语句示例：return RolloutResult(output_ids, completion_ids, per_token_logps, completions, prompt_ids.new_full((output_ids】
        输入上面生成的四个结果。再用 prompt_ids.new_full((2,),3) 创建 prompt_lens=[3,3]，
        用 attention_mask.new_ones(2,3) 创建 completion_mask=[[1,1,1],[1,1,1]]，保持对应设备和整数类型。
        六个参数按数据类字段顺序传入，输出 RolloutResult 对象。
        第一条实际有效回答 [21,2] 只有两个 token，但此处 mask 仍全 1；PPO 会再排除第一个 EOS 之后的列。
        '''
        return RolloutResult(output_ids, completion_ids, per_token_logps, completions,
                             prompt_ids.new_full((output_ids.size(0),), prompt_len),
                             attention_mask.new_ones(output_ids.size(0), completion_ids.size(1)))
    
    # 让采样引擎使用更新后的策略：本地替换引用，远端则导出权重并通知服务加载。
    '''
    【TorchRolloutEngine.update_policy 示例】输入一个更新后的 model_B，而当前 self.policy_model 指向 model_A。调用后 self.policy_model 指向 model_B，下一次 rollout 使用它；输出 None。若本来就是同一对象，则只是重复赋同一引用，不涉及磁盘或 HTTP。
    '''
    def update_policy(self, model: torch.nn.Module):
        '''
        【语句示例：self.policy_model】
        输入 model=model_B。将 self.policy_model 的引用改为 model_B；不复制 state_dict、不清理梯度，也不自动移动设备或切换 train/eval 模式。
        '''
        self.policy_model = model


# ===== SGLang HTTP API 推理引擎 =====
# 通过 HTTP 调用外部推理服务；训练机和服务必须能够访问约定的权重目录。
'''
【SGLangRolloutEngine 类：把生成工作交给独立服务】
输入 base_url="http://localhost:8998"、model_path="../model"、shared_ckpt_path="./sglang_ckpt"。
步骤 1：构造时保存连接配置，并加载与服务匹配的 tokenizer；不会在这里启动服务器或加载服务端模型。
步骤 2：rollout 去掉提示左 PAD，将 token 列表通过 /generate 发送给已运行的服务。
步骤 3：解析返回 token/logp，按右侧补齐构造统一的 RolloutResult，供 PPO/GRPO 使用。
步骤 4：Actor 更新后调用 update_policy，导出当前权重，再通知服务从共享路径重新加载。
输出是可调用的引擎对象。与本地后端相比，生成与训练处于不同进程或机器，必须实际完成权重同步。
以下 HTTP 字段按当前仓库代码展示，不保证所有服务版本都用同一格式。
'''
class SGLangRolloutEngine(RolloutEngine):
    # 保存服务地址、共享权重目录与请求超时，并加载与服务模型匹配的 tokenizer。
    '''
    【SGLangRolloutEngine.__init__ 示例】输入 base_url="http://localhost:8998/"、model_path="../model"、shared_ckpt_path="./sglang_ckpt"、timeout=120。先去掉 URL 尾斜杠，再保存目录和超时，加载 tokenizer，最后令 self.http=requests。输出初始化实例；构造函数返回 None，没有发送生成请求。
    '''
    def __init__(self, base_url: str, model_path: str, shared_ckpt_path: str = "./sglang_ckpt", timeout: int = 120):
        '''
        【语句示例：self.base_url】
        输入 "http://localhost:8998/"，rstrip("/") 去掉末尾斜杠，保存为 "http://localhost:8998"。后面拼 /generate 时不会产生双斜杠。
        '''
        self.base_url = base_url.rstrip('/')
        '''
        【语句示例：self.shared_ckpt_path】
        输入 shared_ckpt_path="./sglang_ckpt"。保存路径字符串，稍后导出权重时使用；此处不建目录，也不证明远端能访问该目录。
        '''
        self.shared_ckpt_path = shared_ckpt_path
        '''
        【语句示例：self.timeout】
        输入 timeout=120，保存这个数值。之后 HTTP 调用把它作为 requests 的 timeout 参数；不是生成 token 数，也不是全训练任务的超时。
        '''
        self.timeout = timeout
        '''
        【语句示例：self.tokenizer】
        输入 model_path="../model"。AutoTokenizer 根据该目录配置加载 tokenizer；trust_remote_code=True 允许模型提供的自定义实现。这与加载 Actor 权重、启动 SGLang 服务器是不同的步骤。
        '''
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        '''
        【语句示例：self.http】
        输入 requests 模块，赋给 self.http。后续 self.http.post/get 就是在使用 requests；也便于验证时替换成不发网络的测试对象。
        '''
        self.http = requests
    
    # 按提示采样多个回答，返回完整 token、回答 token、旧策略 log 概率和有效位置等信息。
    '''
    【SGLangRolloutEngine.rollout：请求数据 → 服务结果 → 六字段输出】
    输入 prompt_ids=[[0,11,12],[13,14,15]]、mask=[[0,1,1],[1,1,1]]，G=1、PAD=0、EOS=2。
    第 1 步：去 PAD 后提示列表为 [[11,12],[13,14,15]]，随请求发到 /generate。
    第 2 步：假设服务返回两条记录（简化字段示例）：
      [{"meta_info":{"output_ids":[21,2],"output_token_logprobs":[[-0.7,21],[-0.2,2]]}},
       {"meta_info":{"output_ids":[31,32,2],"output_token_logprobs":[-0.4,-0.8,-0.1]}}]
    第 3 步：提取回答与每 token logp；多元素列表只取第 0 项作为 logp。
    第 4 步：拼回提示，原始完整序列为 [[11,12,21,2],[13,14,15,31,32,2]]。
    第 5 步：最长回答宽度为 3，最长提示为 3，完整补齐宽度为 6。
    输出 RolloutResult 的六字段为：
      output_ids=[[11,12,21,2,0,0],[13,14,15,31,32,2]]，
      completion_ids=[[21,2,0],[31,32,2]]，
      per_token_logps=[[-0.7,-0.2,0],[-0.4,-0.8,-0.1]]，
      completions=["答案一","答案二"]（假想解码文本），
      prompt_lens=[2,3]，completion_mask=[[1,1,0],[1,1,1]]。
    数组实际为设备上的张量，只有 completions 是文本列表。这里 logp 来自服务，不在本地重算；
    长度对齐时补的 0 只是占位，不能解读为这个位置的真实生成概率等于 1。
    '''
    def rollout(self, prompt_ids: Tensor, attention_mask: Tensor, num_generations: int, max_new_tokens: int, temperature: float = 0.8) -> RolloutResult:
        # 去除左侧 padding tokens，只保留有效 token
        '''
        【语句示例：input_ids_list】
        输入：尚未去除提示补齐。创建 input_ids_list=[]，准备按样本收集有效 token 列表。
        '''
        input_ids_list = []
        '''
        【语句示例：for ids, mask in zip(prompt_ids, attention_mask):】
        输入 ids 两行 [[0,11,12],[13,14,15]] 和对应 mask。zip 每次取同一行 ids/mask，先处理第一题，再处理第二题。
        '''
        for ids, mask in zip(prompt_ids, attention_mask):
            # 发送远端前先去掉左侧 PAD，因此返回的 prompt_lens 可随样本变化。
            '''
            【语句示例：valid_ids】
            输入 ids=[0,11,12]、mask=[0,1,1]。mask.bool()=[False,True,True]，布尔索引选择 [11,12]，tolist 转成 Python 列表。第二行得到 [13,14,15]。
            '''
            valid_ids = ids[mask.bool()].tolist()
            '''
            【语句示例：input_ids_list.append(valid_ids)】
            输入此前 input_ids_list=[]、valid_ids=[11,12]。append 后是 [[11,12]]；再处理第二题后是 [[11,12],[13,14,15]]，允许各行长度不同。
            '''
            input_ids_list.append(valid_ids)
        '''
        【语句示例：all_input_ids】
        输入两条提示 p0=[11,12]、p1=[13,14,15]，num_generations=2。外层先遍历提示、内层重复，得到 [p0,p0,p1,p1]；G=1 时仍是两行。这个顺序必须与服务返回结果一致。
        '''
        all_input_ids = [ids for ids in input_ids_list for _ in range(num_generations)]
        
        '''
        【语句示例：payload】
        输入 all_input_ids=[[11,12],[13,14,15]]、temperature=0.8、max_new_tokens=3、EOS=2。
        输出请求字典：{"input_ids":[[11,12],[13,14,15]],
        "sampling_params":{"temperature":0.8,"max_new_tokens":3,"stop_token_ids":[2]},"return_logprob":True}。
        本句只构造数据，不发送请求。代码用 eos_token_id 的真假判断：若为 None 或 0，就会写空列表 []。
        '''
        payload = {
            "input_ids": all_input_ids,
            "sampling_params": {
                "temperature": temperature,
                "max_new_tokens": max_new_tokens,
                "stop_token_ids": [self.tokenizer.eos_token_id] if self.tokenizer.eos_token_id else [],
            },
            "return_logprob": True,
        }
        
        '''
        【语句示例：resp】
        输入 URL="http://localhost:8998" 和 payload 字典。POST 到 /generate，json=payload 自动按 JSON 序列化，返回 Response 对象 resp；需要服务已运行。连接失败或超时会抛异常。
        '''
        resp = self.http.post(f"{self.base_url}/generate", json=payload, timeout=self.timeout)
        '''
        【语句示例：resp.raise_for_status()】
        输入 resp.status_code=200，raise_for_status 正常返回 None；若是 500 等 HTTP 错误则抛异常，后续解析不再执行。本方法不在这里捕获异常。
        '''
        resp.raise_for_status()
        
        '''
        【语句示例：results】
        输入 HTTP 响应正文为 JSON。resp.json() 解码成列表或字典，例如两条 meta_info 记录；若正文不是合法 JSON，会抛解码异常，不会自动修复。
        '''
        results = resp.json()
        '''
        【语句示例：if not isinstance(results, list):】
        输入 results 是单条字典而不是 list，条件成立，需要统一包装成列表；若已经是两条记录的列表就跳过。
        '''
        if not isinstance(results, list):
            '''
            【语句示例：results】
            输入 results={"meta_info":{...}}。包装后为 [{"meta_info":{...}}]，后面的 enumerate 无论单条还是多条都可按样本遍历。
            '''
            results = [results]
        
        '''
        【语句示例：(all_output_ids, all_completion_ids, all_logprobs)】
        输入：尚未处理返回记录。分别创建 all_output_ids=[]、all_completion_ids=[]、all_logprobs=[]；它们是三个独立列表，用于完整序列、回答、概率。
        '''
        all_output_ids, all_completion_ids, all_logprobs = [], [], []
        '''
        【语句示例：completions】
        输入：尚未解码回答。创建 completions=[]；后面按服务返回顺序追加字符串，保持与 token 行对应。
        '''
        completions = []
        
        '''
        【语句示例：for i, result in enumerate(results):】
        输入两条服务记录。enumerate 给出 i=0、1；代码用同一个 i 访问 all_input_ids[i]，因此假定服务返回数量及顺序与请求对应，未额外按请求 ID 重新排序。
        '''
        for i, result in enumerate(results):
            '''
            【语句示例：meta】
            输入 result={"meta_info":{"output_ids":[21,2]}}，取出内部字典。若没有 meta_info，得到默认 {}，供后面字段回退使用。
            '''
            meta = result.get("meta_info", {})
            '''
            【语句示例：completion_ids】
            输入 meta 中有 output_ids=[21,2]，优先取它；若 meta 缺此键，再取 result 顶层 output_ids；两处都缺则得到 []。get 的默认值只用于缺键，不会把已有的 None 自动换成列表。
            '''
            completion_ids = meta.get("output_ids", result.get("output_ids", []))
            '''
            【语句示例：raw_logprobs】
            输入 meta["output_token_logprobs"]=[[-0.7,21],[-0.2,2]]，取出整个列表。缺此字段得到 []，后面可能按回答长度补 0；当前代码只从 meta 取这一字段。
            '''
            raw_logprobs = meta.get("output_token_logprobs", [])
            
            '''
            【语句示例：logprobs】
            输入原始概率条目尚未转换。建立 logprobs=[]，之后逐项提取浮点值，不把 token 编号一起放进去。
            '''
            logprobs = []
            '''
            【语句示例：for item in raw_logprobs:】
            输入 raw_logprobs=[[-0.7,21],[-0.2,2]]，循环先取第一项再取第二项；另一个可接受示例是 [-0.7,-0.2]，每项直接为数值。
            '''
            for item in raw_logprobs:
                '''
                【语句示例：if isinstance(item, (list, tuple)) and len(item) >= 1:】
                输入 item=[-0.7,21]，是长度至少 1 的列表，条件 True；输入 -0.7 不满足，进入后面的数值类型分支。
                '''
                if isinstance(item, (list, tuple)) and len(item) >= 1:
                    '''
                    【语句示例：logprobs.append(item[0])】
                    输入 item=[-0.7,21]。只 append item[0]，logprobs 从 [] 变 [-0.7]；21 是附带的 token 信息，不作为概率追加。
                    '''
                    logprobs.append(item[0])
                else:
                    '''
                    【语句示例：if isinstance(item, (int, float)):】
                    输入 item=-0.2，是 float，条件成立；若是字符串或空列表，这两个条件都不成立，该条目被忽略。这里只解析类型，不验证数值是否真是合法 logp。
                    '''
                    if isinstance(item, (int, float)):
                        '''
                        【语句示例：logprobs.append(item)】
                        输入 logprobs=[-0.7]、item=-0.2。直接追加后得到 [-0.7,-0.2]，长度与两个回答 token 对齐。
                        '''
                        logprobs.append(item)
            
            # 兼容服务返回长度差异：缺少的前缀概率补 0，过长则取尾部；补值只是对齐占位。
            '''
            【语句示例：if len(logprobs) < len(completion_ids):】
            输入 completion_ids=[21,2]、logprobs=[-0.2]，1<2 成立，进入前补零分支；长度已相同则不需要这一步。
            '''
            if len(logprobs) < len(completion_ids):
                '''
                【语句示例：logprobs】
                输入回答长度 2、现有 logp 长度 1。差为 1，构造 [0.0]+[-0.2]，输出 [0.0,-0.2]。这里补在前面，不是在末尾；0 是对齐占位，不是重新计算出的 token 概率。
                '''
                logprobs = [0.0] * (len(completion_ids) - len(logprobs)) + logprobs
            else:
                '''
                【语句示例：if len(logprobs) > len(completion_ids):】
                输入 completion_ids=[21,2]、logprobs=[-9,-0.7,-0.2]，3>2 成立，进入截短分支；这是前一个 if 的 elif，不会与短缺分支同时执行。
                '''
                if len(logprobs) > len(completion_ids):
                    '''
                    【语句示例：logprobs】
                    输入多余 logprobs=[-9,-0.7,-0.2]，取末尾 2 项得 [-0.7,-0.2]。若 completion_ids=[]，直接设 []，避免 [-0:] 意外保留整个列表。
                    '''
                    logprobs = logprobs[-len(completion_ids):] if completion_ids else []
            '''
            【语句示例：prompt】
            输入 i=0、all_input_ids=[[11,12],[13,14,15]]。取 prompt=[11,12]，这是去掉左 PAD 后的原提示，不是生成的回答。
            '''
            prompt = all_input_ids[i]
            '''
            【语句示例：full_output】
            输入 prompt=[11,12]、completion_ids=[21,2]。Python 列表相加得到 full_output=[11,12,21,2]；不是逐元素数值相加。
            '''
            full_output = prompt + completion_ids
            '''
            【语句示例：all_output_ids.append(full_output)】
            输入 full_output=[11,12,21,2]。追加后 all_output_ids 第一行保存完整序列；第二条稍后可更长，此刻还没有补齐成张量。
            '''
            all_output_ids.append(full_output)
            '''
            【语句示例：all_completion_ids.append(completion_ids)】
            输入 completion_ids=[21,2]。追加后 all_completion_ids=[[21,2]]，第二条加入后为 [[21,2],[31,32,2]]。
            '''
            all_completion_ids.append(completion_ids)
            '''
            【语句示例：all_logprobs.append(logprobs)】
            输入对齐后的 logprobs=[-0.7,-0.2]。追加后第一行概率确定；第二条加入后可为 [[-0.7,-0.2],[-0.4,-0.8,-0.1]]。
            '''
            all_logprobs.append(logprobs)
            '''
            【语句示例：completions.append(self.tokenizer.decode(completion_ids, skip_special_tokens=True))】
            输入 completion_ids=[21,2]。decode 跳过特殊标记，假设文字为“答案一”，加入 completions。此文本映射仅为演示，实际取决于加载的 tokenizer。
            '''
            completions.append(self.tokenizer.decode(completion_ids, skip_special_tokens=True))
        
        '''
        【语句示例：device】
        输入 prompt_ids 位于 cuda:0，device 取 torch.device("cuda:0")；后面用这个设备创建输出张量。本次 HTTP 返回先是 Python 数据，并不自动驻留 GPU。
        '''
        device = prompt_ids.device
        '''
        【语句示例：max_comp_len】
        输入回答长度分别是 2、3，内层 max=3，外层 max(1,3)=3。若记录存在但所有回答为空，最小宽度设为 1；若整个结果列表为空，内层 max 仍会报错，并未被外层 max 修复。
        '''
        max_comp_len = max(1, max(len(ids) for ids in all_completion_ids))
        '''
        【语句示例：max_out_len】
        输入去 PAD 后提示长度为 [2,3]，max_comp_len=3。最大提示长 3 加最大回答长 3，max_out_len=6。即使最长提示和最长回答来自不同样本，这里仍按两者之和分配宽度。
        '''
        max_out_len = max(len(ids) for ids in all_input_ids) + max_comp_len
        
        # 把变长列表右侧补齐到统一长度，再构造设备上的二维张量。
        '''
        【局部 pad_to_tensor：变长列表 → 右侧补齐的张量】
        输入 seqs=[[21,2],[31,32,2]]、max_len=3、pad_val=0，外层 device="cpu"。
        步骤 1：第一行差 3-2=1，追加一个 0，得到 [21,2,0]；第二行差 0，保持 [31,32,2]。
        步骤 2：torch.tensor 将矩形列表变成设备上的 [2,3] 张量，整数输入通常为 int64。
        输出 tensor([[21,2,0],[31,32,2]])。若输入为概率浮点列表、pad_val=0.0，则得到浮点张量。
        它是 rollout 内部函数，不能直接调用 engine.pad_to_tensor；依赖外层 device。
        调用方保证 max_len 足够，本函数不截短过长行；若各行仍不等长，建张量会失败。
        '''
        def pad_to_tensor(seqs, max_len, pad_val=0):
            '''
            【语句示例：return torch.tensor([s + [pad_val] * (max_len - len(s)) for s in seqs], device=device)】
            输入 seqs=[[21,2],[31,32,2]]、max_len=3。列表推导逐行计算缺少位置并补 pad_val，得到 [[21,2,0],[31,32,2]]，随后在外层指定设备上转为张量并返回。
            '''
            return torch.tensor([s + [pad_val] * (max_len - len(s)) for s in seqs], device=device)
        
        '''
        【语句示例：pad_id】
        输入 tokenizer.pad_token_id=0，保存 pad_id=0。后面用它补 token 序列；该 tokenizer 需要提供可用于张量构造的 PAD 编号，本句没有 None 回退逻辑。
        '''
        pad_id = self.tokenizer.pad_token_id
        '''
        【语句示例：return RolloutResult(output_ids=pad_to_tensor(all_output_ids, max_out_len, pad_val=pad_id), completion_ids=pad】
        输入 all_output_ids=[[11,12,21,2],[13,14,15,31,32,2]]、回答 [[21,2],[31,32,2]]。
        步骤 1：完整序列补到 6 列，得 [[11,12,21,2,0,0],[13,14,15,31,32,2]]。
        步骤 2：回答补到 3 列，得 [[21,2,0],[31,32,2]]；概率用 0.0 补到相同宽度。
        步骤 3：prompt_lens 按每条去 PAD 后提示计数，得到 [2,3]。
        步骤 4：回答真实部分填 1、补齐部分填 0，得到 completion_mask=[[1,1,0],[1,1,1]]。
        输出包含上述张量及 completions 文本列表的 RolloutResult；与本地后端保持相同字段名。
        '''
        return RolloutResult(
            output_ids=pad_to_tensor(all_output_ids, max_out_len, pad_val=pad_id),
            completion_ids=pad_to_tensor(all_completion_ids, max_comp_len, pad_val=pad_id),
            per_token_logps=pad_to_tensor(all_logprobs, max_comp_len, pad_val=0.0),
            completions=completions,
            prompt_lens=torch.tensor([len(ids) for ids in all_input_ids], device=device),
            completion_mask=torch.tensor([[1] * len(ids) + [0] * (max_comp_len - len(ids)) for ids in all_completion_ids], device=device),
        )
    
    # 让采样引擎使用更新后的策略：本地替换引用，远端则导出权重并通知服务加载。
    '''
    【SGLangRolloutEngine.update_policy：训练权重怎样同步到远端】
    输入：刚更新的 Actor、共享目录 ./sglang_ckpt，服务监听 http://localhost:8998。
    第 1 步：单进程或 rank 0 解包模型，将权重转 CPU FP16，导出配置/权重与 tokenizer。
    第 2 步：POST /update_weights_from_disk，提交 {"model_path":共享目录的绝对路径}。
    第 3 步：假设 HTTP 状态为 200，令 ok=True；非 200 或导出/请求异常则置 False。
    第 4 步：多卡时 rank 0 广播 1/0，所有 rank 等待 barrier，统一知道是否成功。
    输出：成功返回 True；失败在同步后抛 RuntimeError，不是返回 False 继续训练。
    这个方法不上传权重字节，只发送目录路径，服务必须能访问该路径及其中最新导出文件。
    '''
    def update_policy(self, model: torch.nn.Module):
        '''
        【语句示例：ok】
        输入：本次同步刚开始。ok=True 是初始状态，不代表已经收到远端确认；主进程完成导出和请求后会按结果覆盖它。
        '''
        ok = True
        '''
        【语句示例：if not dist.is_initialized() or dist.get_rank() == 0:】
        输入未初始化分布式，左条件 True，当前进程导出；若已初始化，仅 rank 0 导出，rank 1 等其它进程跳过，稍后接收广播。or 短路避免未初始化时调用 get_rank。
        '''
        if not dist.is_initialized() or dist.get_rank() == 0:
            '''
            【语句示例：try:】
            输入：开始文件导出与 HTTP 更新流程。try 捕获其内部的 Exception，例如磁盘写入失败或连接超时，进入下面异常分支打印并置 ok=False。
            '''
            try:
                '''
                【语句示例：unwrapped】
                输入 DDP 包装 Actor 时取 .module，否则用自身。输出 unwrapped 与训练网络共享参数，只是去掉一层包装。
                '''
                unwrapped = model.module if isinstance(model, DistributedDataParallel) else model
                '''
                【语句示例：unwrapped】
                输入模型还被 torch.compile 包装时，getattr 取 _orig_mod；否则回退到原对象。这样调用 save_pretrained 的是实际网络，而不是编译包装层。
                '''
                unwrapped = getattr(unwrapped, '_orig_mod', unwrapped)
                # 把当前策略导出到约定的共享目录，远端 update_weights_from_disk 必须能读到同一路径。
                '''
                【语句示例：abs_path】
                输入共享目录 ./sglang_ckpt，假设当前工作目录 /work。abspath 得到 /work/sglang_ckpt，用于写文件和请求服务加载；这只是路径解析，不会自动让另一台机器共享目录。
                '''
                abs_path = os.path.abspath(self.shared_ckpt_path)
                '''
                【语句示例：state_dict】
                输入 FP32 权重字典，例如某参数 [0.123456,0.5]。逐项 detach 断开梯度，half 转 FP16，cpu 转到 CPU，形成导出字典。FP16 会有舍入，原训练模型参数仍留在原设备和精度。
                '''
                state_dict = {k: v.detach().half().cpu() for k, v in unwrapped.state_dict().items()}
                '''
                【语句示例：unwrapped.save_pretrained(abs_path, state_dict=state_dict, safe_serialization=False)】
                输入 abs_path 和刚得到的 state_dict。save_pretrained 导出可加载的模型配置与权重；safe_serialization=False 请求非 safetensors 的保存方式。具体文件组织由模型/Transformers 实现决定，不在此处硬编码。
                '''
                unwrapped.save_pretrained(abs_path, state_dict=state_dict, safe_serialization=False)
                '''
                【语句示例：self.tokenizer.save_pretrained(abs_path)】
                输入同一 abs_path。tokenizer.save_pretrained 将分词器配置和所需词表资源保存到该目录；远端需用与训练匹配的 token 编码。
                '''
                self.tokenizer.save_pretrained(abs_path)
                '''
                【语句示例：resp】
                输入 abs_path=/work/sglang_ckpt。POST 到 /update_weights_from_disk，请求 JSON 为 {"model_path":"/work/sglang_ckpt"}。这里只传路径字符串，不把 state_dict 放进 HTTP JSON。
                '''
                resp = self.http.post(f"{self.base_url}/update_weights_from_disk", json={"model_path": abs_path}, timeout=self.timeout)
                '''
                【语句示例：if resp.status_code != 200:】
                输入 resp.status_code=500，!=200 为 True，进入告警输出；200 则跳过这条打印。此处按是否恰好 200 判断成功。
                '''
                if resp.status_code != 200:
                    '''
                    【语句示例：print(f'[SGLANG WARNING] update_weights 失败: {resp.status_code}, {resp.text}')】
                    输入状态 500、响应正文为服务错误说明。打印 [SGLANG WARNING] update_weights 失败 及状态/正文，便于定位加载失败；下一句仍会设置 ok=False。
                    '''
                    print(f"[SGLANG WARNING] update_weights 失败: {resp.status_code}, {resp.text}")
                '''
                【语句示例：ok】
                输入 resp.status_code=200，则 ok=True；若 500 则 ok=False。当前代码不另外检查 JSON 内的成功字段，只按 HTTP 状态判断。
                '''
                ok = resp.status_code == 200
            except Exception as e:
                '''
                【语句示例：print(f'[SGLANG WARNING] update_weights 异常: {e}')】
                输入异常 e，例如 ConnectionError。except Exception 分支打印错误内容，说明导出或请求过程中失败；此打印本身不会重新尝试。
                '''
                print(f"[SGLANG WARNING] update_weights 异常: {e}")
                '''
                【语句示例：ok】
                输入已发生异常。将 ok=False，后面通过广播让其它 rank 得知失败，并统一抛出 RuntimeError。
                '''
                ok = False
        '''
        【语句示例：if dist.is_initialized():】
        输入单进程未初始化，跳过广播；多进程组已初始化则所有 rank 都进入此分支，不能只由 rank 0 执行。
        '''
        if dist.is_initialized():
            '''
            【语句示例：ok_t】
            输入 ok=True→int(ok)=1，False→0；在 model 第一个参数所在设备上创建标量 ok_t。这样集合通信使用一个设备匹配的状态张量。
            '''
            ok_t = torch.tensor(int(ok), device=next(model.parameters()).device)
            # PyTorch：broadcast 将 src 进程的张量发给其余进程；这里同步远端权重更新的成功状态。
            # PyTorch：barrier 等待所有进程到达同步点；所有 rank 都应参与，不能只在主进程调用。
            '''
            【语句示例：dist.broadcast(ok_t, src=0)】
            输入 rank 0 的 ok_t=0，而 rank 1 初值可能仍为 1。broadcast(src=0) 后两者都变成 0，统一采用主进程的实际同步结果。
            '''
            dist.broadcast(ok_t, src=0)
            '''
            【语句示例：dist.barrier()】
            输入所有 rank 正在完成同步流程。barrier 等待各进程都到达这个位置，再一起继续，不产生新的评分或模型参数。
            '''
            dist.barrier()
            '''
            【语句示例：ok】
            输入广播后的 ok_t=tensor(0)。item() 取数字 0，bool 转为 False；tensor(1) 则恢复 True，供下面的失败判断使用。
            '''
            ok = bool(ok_t.item())
        '''
        【语句示例：if not ok:】
        输入 ok=False，not ok 为 True，进入错误分支；ok=True 则跳过并返回成功。
        '''
        if not ok:
            '''
            【语句示例：raise RuntimeError('SGLang update_policy failed')】
            输入同步失败标记。抛 RuntimeError("SGLang update_policy failed")，阻止调用方把这次同步当作成功；不会执行下面 return ok。
            '''
            raise RuntimeError("SGLang update_policy failed")
        '''
        【语句示例：return ok】
        输入 ok=True，返回 Python 布尔值 True。False 情况已在上一分支抛异常，因此正常返回路径只表示成功。
        '''
        return ok
    
    # 请求远端清理推理缓存，返回 HTTP 状态是否为 200。
    '''
    【flush_cache 示例】输入已有的远端引擎；调用 engine.flush_cache() 无需额外参数。步骤：POST /flush_cache，超时参数为 30，再比较状态码。HTTP 200 返回 True，非 200 返回 False；连接异常会向外抛出，不像 health 那样捕获。
    '''
    def flush_cache(self) -> bool:
        '''
        【语句示例：resp】
        输入 base_url="http://localhost:8998"。POST 到 /flush_cache，timeout=30，得到 resp。这里不发送 prompt 或权重；只是请求服务清理其缓存。
        '''
        resp = self.http.post(f"{self.base_url}/flush_cache", timeout=30)
        '''
        【语句示例：return resp.status_code == 200】
        输入 resp.status_code=200 返回 True；503 返回 False。只比较 HTTP 状态，不解析响应体，也不等于在本地执行 torch.cuda.empty_cache。
        '''
        return resp.status_code == 200
    
    # 探测远端服务健康状态；请求异常或非 200 响应返回 False。
    '''
    【health 示例】输入已有引擎，调用 engine.health()。步骤：GET /health，超时参数 5；200 返回 True、非 200 返回 False，发生连接/超时等异常也返回 False。因此它可用于探测服务是否可联系，但不验证模型回答质量。
    '''
    def health(self) -> bool:
        '''
        【语句示例：try:】
        输入：准备健康检查。进入 try，让后面的请求异常或属性访问异常走 except 分支，调用方通常得到 False 而不是连接异常。
        '''
        try:
            '''
            【语句示例：resp】
            输入 base_url="http://localhost:8998"。GET /health，timeout=5。返回 resp 后继续检查状态；如果请求失败，直接跳到 except。
            '''
            resp = self.http.get(f"{self.base_url}/health", timeout=5)
            '''
            【语句示例：return resp.status_code == 200】
            输入健康接口 HTTP 200，返回 True；如果是 404 或 503，返回 False。此处没有调用 raise_for_status，不需要靠异常来表示 HTTP 非 200。
            '''
            return resp.status_code == 200
        except:
            '''
            【语句示例：return False】
            输入 GET 过程中抛出异常。裸 except 捕获后返回 False；它实际比 except Exception 捕获范围更宽，并不只限于网络错误。
            '''
            return False


# ===== 工厂函数 =====
# 根据 engine_type 构造本地或远端采样器，未知类型直接报错。
'''
【create_rollout_engine 工厂函数：字符串配置 → 具体引擎对象】
示例 A 输入 engine_type="torch"、policy_model=actor、tokenizer=t、device="cpu"。
步骤：命中 torch 分支，把四个本地参数传入 TorchRolloutEngine，输出本地引擎对象。
示例 B 输入 engine_type="sglang"、sglang_base_url="http://localhost:8998"、
sglang_model_path="../model"、sglang_shared_path="./sglang_ckpt"。
步骤：命中 sglang 分支，把三个远端参数传给构造函数，输出 HTTP 引擎对象。
示例 C 输入 engine_type="unknown"，两个分支都不命中，抛 ValueError。
调用者必须给选中分支提供可用对象/路径；默认 None 是参数占位，并不会自动初始化 Actor。
特别是 sglang_shared_path 默认 None 会被显式传下去，不会自动使用子类的默认共享目录字符串。
'''
def create_rollout_engine(
    engine_type: str = "torch",
    policy_model: torch.nn.Module = None,
    tokenizer = None,
    device: str = "cuda",
    autocast_ctx = None,
    sglang_base_url: str = None,
    sglang_model_path: str = None,
    sglang_shared_path: str = None,
) -> RolloutEngine:
    '''
    【语句示例：if engine_type == 'torch':】
    输入 engine_type="torch"，条件 True，选择本地引擎；若为 "sglang" 则进入后面的 elif。比较区分大小写，"Torch" 不等于 "torch"。
    '''
    if engine_type == "torch":
        '''
        【语句示例：return TorchRolloutEngine(policy_model, tokenizer, device, autocast_ctx)】
        输入 actor、tokenizer、device="cpu"、autocast_ctx=None。构造并返回 TorchRolloutEngine，结束工厂函数；这一步本身不执行 generate。
        '''
        return TorchRolloutEngine(policy_model, tokenizer, device, autocast_ctx)
    else:
        '''
        【语句示例：if engine_type == 'sglang':】
        输入 engine_type="sglang"，在未命中 torch 的前提下条件为 True。选择远端 HTTP 引擎，后面的 else 处理其它未知字符串。
        '''
        if engine_type == "sglang":
            '''
            【语句示例：return SGLangRolloutEngine(sglang_base_url, sglang_model_path, sglang_shared_path)】
            输入服务 URL、分词器目录和共享目录。构造 SGLangRolloutEngine 并返回；其构造函数会加载 tokenizer，但不会自动启动服务器或发送采样请求。
            '''
            return SGLangRolloutEngine(sglang_base_url, sglang_model_path, sglang_shared_path)
        else:
            '''
            【语句示例：raise ValueError(f'不支持的引擎类型: {engine_type}')】
            输入 engine_type="unknown"。抛 ValueError，消息为“不支持的引擎类型: unknown”；不回退到 torch，也不返回 None。
            '''
            raise ValueError(f"不支持的引擎类型: {engine_type}")
