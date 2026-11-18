"""最小奖励模型：MiniMind 骨干 + 标量评分头，单卡/CPU、FP32 教学实现。

在 minimind 目录运行（路径默认相对于项目根，不依赖启动位置）：
  python trainer/train_reward.py --data_path dataset/dpo.jsonl
  python trainer/train_reward.py --from_weight none --hidden_size 64 --num_hidden_layers 1 --data_path dataset/reward_demo.jsonl --max_steps 2
  python trainer/train_reward.py --score_checkpoint out/reward_64.pth --prompt "1+1等于几？" --response "等于2。"

正式训练默认加载 out/full_sft_768.pth；模型尺寸必须与 SFT 权重一致。
--from_weight none 仅适合演示流程，不代表已经有可靠的奖励信号。
数据与 DPO 相同：每行包含 chosen/rejected 两份完整对话，历史相同，最终回答不同。
RM 不需要移位的 next-token 标签或参考模型；目标是 -log sigmoid(r_chosen-r_rejected)。
保存文件包含模型配置和权重，可用于评分，但不是现有 PPO 的 AutoModel 目录格式。
训练输出的 accuracy 是当前训练批次的偏好排序准确率，不代表验证集表现。
"""

# 阅读约定：B=偏好对数量，N=2B=实际输入序列数，T=本批最长序列长度，H=隐藏维度。
# 数据流：JSONL 偏好对 → 消息模板 → token 编号 → 补齐组批 → 骨干表示 → 标量评分
#         → 比较 chosen/rejected 分数 → 偏好损失 → 反向传播 → 保存模型。
# 与预训练的区别：预训练为每个位置预测下一个 token；这里为一整段对话输出一个分数。
# 与 DPO 的联系：原始偏好数据相同，但这里显式训练评分模型，不计算策略/参考模型的概率比。
# 下方示例中的 token 编号、隐藏向量和分数均为教学示意，并非 tokenizer 的真实输出。

# argparse 解析启动参数；Path 处理文件路径；os/sys 配置环境变量和模块搜索路径。
import argparse
import os
from pathlib import Path
import sys

# __file__ 是本脚本路径；parents[0] 是 trainer，parents[1] 是内层 minimind 项目根。
# 因此默认数据、分词器和权重路径不随启动目录变化；手动传入的相对路径仍相对当前工作目录。
ROOT = Path(__file__).resolve().parents[1]
# 放在搜索路径开头，使直接运行 trainer/train_reward.py 时也能找到项目中的 model 包。
sys.path.insert(0, str(ROOT))
# setdefault 只在变量尚未设置时写入，避免覆盖使用者已指定的 tokenizer 并行策略。
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import datasets  # Windows 下先于 torch 导入，沿用仓库的 DLL 加载顺序。
import torch
# nn 提供可训练网络层；F 提供 logsigmoid 等无须实例化的数学运算。
from torch import nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer

# 使用输出隐藏状态的 MiniMindModel 骨干，不创建输出词表 logits 的语言模型头。
from model.model_minimind import MiniMindConfig, MiniMindModel


# 将完整消息列表转成一维 token 编号列表；训练和单条评分共用这个入口。
'''
【encode_messages：示例输入 → 逐步处理 → 输出】
输入：messages = [{"role":"user","content":"1+1?"},
                   {"role":"assistant","content":"2"}]，以及项目的 tokenizer。
第 1 步：apply_chat_template 按 role 添加角色标记和分隔符。
  把模板文本简写成 "<用户>1+1?<结束><助手>2<结束>"；这只是结构示意，
  真实文本以 tokenizer 的 chat_template 为准，不是这里手工拼接的字符串。
第 2 步：tokenize=False 使模板返回字符串；add_generation_prompt=False
  表示回答已经存在，不在末尾再追加一个待生成回答的 assistant 前缀。
第 3 步：tokenizer(text, add_special_tokens=False) 编码整个字符串。
  假设完整编码结果为 [1,10,20,2]；这里压缩成 4 个假想 token 便于手算。
第 4 步：从编码结果字典中取出 input_ids。
输出：[1,10,20,2]，类型 list[int]；没有批次维、padding、标签或奖励分数。
  本例编号不是实际 tokenizer 的编码结果；真实 token 数也不等于汉字数。
'''
def encode_messages(tokenizer, messages):
    """训练和推理使用完全相同的模板，不随机增删 thinking 标签。"""
    # 例如 messages=[user("1+1?"), assistant("2")]
    # 先经模板变成带角色分隔符的聊天文本，再编码成 [1, 10, 11, 2, ...]。
    # tokenize=False：这里只渲染字符串，下一步才分词。
    # add_generation_prompt=False：回答已经在 messages 中，不追加待生成回答的 assistant 前缀。
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False
    )
    # 模板已安排聊天所需的特殊标记，add_special_tokens=False 避免分词时重复添加。
    # 返回 Python list[int]，暂不补齐、不截断；完整 token 长度交给数据集检查。
    return tokenizer(text, add_special_tokens=False)["input_ids"]


# 每个 Dataset 样本是一对回答；一行 JSONL 包含 chosen/rejected 两份完整对话。
# chosen 表示标注者更偏好的回答，不要求 rejected 完全错误，也不要求提供数值分数。
'''
【RewardDataset 类：从偏好文件到可组批的数据集】
输入：假设 demo.jsonl 只有一对数据（实际写文件时整对放在同一行）：
  {"chosen":[{"role":"user","content":"1+1?"},
             {"role":"assistant","content":"2"}],
   "rejected":[{"role":"user","content":"1+1?"},
               {"role":"assistant","content":"5"}]}。
调用：ds = RewardDataset("demo.jsonl", tokenizer, max_length=8)。
第 1 步：__init__ 读文件，检查两个回答共享同一段历史。
第 2 步：假设编码得到 chosen=[1,10,20,2]、rejected=[1,10,21,2]。
第 3 步：长度都为 4 且不超过 8；答案非空，编码不同，保留这一对。
第 4 步：ds[0] 返回 {"chosen_ids":[1,10,20,2],
                     "rejected_ids":[1,10,21,2], "keep":True}。
第 5 步：ds.collate([ds[0]]) 将这一对变成两条输入：
  ids=tensor([[1,10,20,2],[1,10,21,2]])，mask=tensor([[1,1,1,1],[1,1,1,1]])。
输出：构造表达式返回数据集对象 ds，len(ds)=1；组批时另返回两个 [2,4] 张量。
  因此“创建对象”“按索引取一对”“将多对组批”是三个不同阶段。
'''
class RewardDataset(Dataset):
    """复用 DPO 原始数据，保留完整序列；不复用 DPODataset 的 x/y 移位。"""

    '''
    【RewardDataset.__init__：加载 → 编码 → 过滤 → 保存成员变量】
    输入：path="demo.jsonl"、max_length=5、max_samples=3，原文件有 4 对。
      假设 tokenizer.pad_token_id=0；前三对结构合法，分词后分别是：
      第 0 对 c=[1,10,20,2]，r=[1,10,21,2]；
      第 1 对 c=[1,11,22,23,24,2]，r=[1,11,25,2]；
      第 2 对 c=[1,12,26,2]，r=[1,12,26,2]。
    第 1 步：load_dataset 读到 4 对，select(range(min(3,4))) 选前 3 对。
    第 2 步：map 对三行调用 encode_pair，得到 keep=[True,False,False]。
      第 1 对 chosen 长度 6 超限；第 2 对两份编码完全相同。
    第 3 步：remove_columns 去掉原始文本列，留下 chosen_ids/rejected_ids/keep。
    第 4 步：filter 只保留第 0 对，self.samples 从 3 行变成 1 行。
    第 5 步：打印“偏好对: 保留 1/3，过滤 2 条”；分母是选取后的 3，不是原始 4。
    第 6 步：设置 self.pad_id=0，供后面的 collate 填充使用。
    输出/副作用：self.samples 保存一对编码，self.pad_id 保存补齐编号。
      __init__ 隐式返回 None；RewardDataset(...) 构造表达式的结果才是实例。
    边界：若三对全部被过滤，抛出 ValueError，不继续训练一个空数据集。
    '''
    def __init__(self, path, tokenizer, max_length=1024, max_samples=None):
        # Hugging Face datasets 负责读取 JSONL，并以表格形式存储样本。
        # split="train" 只是取这个文件对应的数据分区，不会自动划分训练集和验证集。
        samples = datasets.load_dataset("json", data_files=str(path), split="train")
        if max_samples is not None:
            # 取原文件前 N 条而非随机 N 条；min 防止所取数量超过实际样本数。
            samples = samples.select(range(min(max_samples, len(samples))))

        # map 默认逐条调用此函数；闭包可以直接使用外层 tokenizer 和 max_length。
        # index 为从 0 开始的行索引，用于错误定位。结构错误直接报错，长度等问题稍后过滤。
        '''
        【encode_pair：检查并编码一对回答】
        输入：index=0，外层 max_length=5；sample 为：
          {"chosen":[{"role":"user","content":"1+1?"},
                     {"role":"assistant","content":"2"}],
           "rejected":[{"role":"user","content":"1+1?"},
                       {"role":"assistant","content":"5"}]}。
        第 1 步：两个字段都是长度 2 的列表，每条消息含字符串 role/content。
        第 2 步：检查两份列表的最后一条，role 均为 assistant。
        第 3 步：chosen[:-1] 和 rejected[:-1] 都只含 user 的“1+1?”，上下文相同。
        第 4 步：假设 encode_messages 得到 c=[1,10,20,2]、r=[1,10,21,2]。
        第 5 步：长度 4<=5、答案非空、c!=r，所有条件成立，keep=True。
        输出：{"chosen_ids":[1,10,20,2], "rejected_ids":[1,10,21,2], "keep":True}。
        分支 A：若 max_length=3，仍返回完整编码，但 keep=False，外层 filter 再删除。
        分支 B：若 rejected 问题改成“2+2?”，第 3 步抛 ValueError，不返回字典。
          这是 __init__ 内的局部函数，由 map 调用，不能写成 ds.encode_pair(...)。
        '''
        def encode_pair(sample, index):
            chosen, rejected = sample["chosen"], sample["rejected"]
            for messages in (chosen, rejected):
                # 至少包含上下文和末尾回答；支持 system 消息及多轮历史，不限于两条消息。
                if not isinstance(messages, list) or len(messages) < 2:
                    raise ValueError(f"样本 {index}: chosen/rejected 必须是含上下文和回答的消息列表")
                # any：只要有一条消息不符合结构就报错；or 短路避免对非字典调用 .get。
                if any(not isinstance(m, dict) or not isinstance(m.get("content"), str)
                       or not isinstance(m.get("role"), str) for m in messages):
                    raise ValueError(f"样本 {index}: 每条消息必须包含字符串 role 和 content")
                # 本实现比较两份对话的最后一个 assistant 回答。
                if messages[-1]["role"] != "assistant":
                    raise ValueError(f"样本 {index}: 最后一条消息必须是 assistant 回答")
            # [:-1] 去掉末尾答案，只留下共同历史；两边必须是在回答同一个问题。
            # 例如 [user("1+1?"), assistant("2")] 和 [user("1+1?"), assistant("5")]。
            # 对多轮数据，之前的 assistant 消息也属于共同历史，不能随意更换。
            if chosen[:-1] != rejected[:-1]:
                raise ValueError(f"样本 {index}: 两个回答必须对应相同的对话上下文")
            c = encode_messages(tokenizer, chosen)
            r = encode_messages(tokenizer, rejected)
            # 保留完整回答；过滤过长、空回答以及分词后完全相同的偏好对。
            # max_length 限制的是“模板 + 全部历史 + 最终回答”的总 token 数，不是回答字数。
            # 若只截断尾部，可能把两个不同答案截成同一个输入，却仍要求模型给出不同分数。
            # 因此任意一边超长就过滤整对；空答案和完全相同的输入也不提供有效偏好监督。
            keep = (0 < len(c) <= max_length and 0 < len(r) <= max_length
                    and bool(chosen[-1]["content"].strip())
                    and bool(rejected[-1]["content"].strip()) and c != r)
            return {"chosen_ids": c, "rejected_ids": r, "keep": keep}

        total = len(samples)
        # with_indices=True 把行索引传入 encode_pair；remove_columns 去掉原始文本列。
        # map 后每行只剩 chosen_ids、rejected_ids、keep，后面的训练不必反复渲染和分词。
        samples = samples.map(encode_pair, with_indices=True,
                              remove_columns=samples.column_names)
        # filter 只保留 keep 为 True 的行；日志中的 total 是应用 max_samples 后的数量。
        self.samples = samples.filter(lambda sample: sample["keep"])
        print(f"偏好对: 保留 {len(self.samples)}/{total}，过滤 {total - len(self.samples)} 条")
        if not len(self.samples):
            raise ValueError("没有可训练样本，请检查数据或增大 --max_seq_len")
        # 补齐只是为了让变长序列组成矩形张量；哪些位置是真实输入由独立 mask 指明。
        self.pad_id = tokenizer.pad_token_id
        if self.pad_id is None:
            # 没有专用 PAD 时用 EOS 的编号填空位，不代表这些空位是回答中的真实结束符。
            self.pad_id = tokenizer.eos_token_id
        if self.pad_id is None:
            raise ValueError("tokenizer 必须提供 pad_token_id 或 eos_token_id")

    '''
    【__len__：按偏好对计数】
    输入：假设 ds.samples 中保存 3 行过滤后的编码；调用 n=len(ds)。
    第 1 步：Python 将 len(ds) 转为调用 ds.__len__()。
    第 2 步：访问 self.samples，向底层数据集查询行数，得到 3。
    输出：整数 3。虽然总共有 6 个回答，但这里按“对”计数，不返回 6。
    '''
    def __len__(self):
        # 返回有效偏好对数量；不是 token 数，也不是前向时的 2B 条序列数。
        return len(self.samples)

    '''
    【__getitem__：取出指定的一对编码】
    输入：index=1；假设 ds.samples 的第 1 行是：
      {"chosen_ids":[1,12,22,2], "rejected_ids":[1,12,23,24,2], "keep":True}。
    第 1 步：调用 ds[1]，Python 自动进入 ds.__getitem__(1)。
    第 2 步：self.samples[1] 按从 0 开始的索引取第二行，整理成字典。
    输出：上面的字典；两个 ids 仍是长度 4、5 的列表，没有补齐，也没有计算分数。
      keep=True 是初始化过滤后留下的字段，此处不会重新检查或分词。
    '''
    def __getitem__(self, index):
        # 返回一行字典；chosen_ids/rejected_ids 仍是可变长度列表，交给 collate 组批。
        return self.samples[index]

    # DataLoader 收集 B 个样本后调用此方法，将两组变长列表变成 [2B,T] 张量。
    # collate的意思是“收集、整理、组合”，这里是把多条变长序列补齐成矩形张量。
    '''
    【collate：手算两对数据的组批结果】
    输入：self.pad_id=0，batch=[
      {"chosen_ids":[1,10,2],    "rejected_ids":[1,11,12,2], "keep":True},
      {"chosen_ids":[1,20,21,2], "rejected_ids":[1,22,2],    "keep":True}
    ]，B=2；这些编号专用于演示变长序列，不是上面文字的实际编码。
    第 1 步：先取所有 chosen，再取所有 rejected，排列为 [c0,c1,r0,r1]：
      [[1,10,2], [1,20,21,2], [1,11,12,2], [1,22,2]]。
    第 2 步：长度为 [3,4,4,3]，width=4，总行数为 2B=4。
    第 3 步：创建全为 PAD=0 的 ids 和全为 0 的 mask，形状都是 [4,4]。
    第 4 步：逐行写入 token，同时把真实位置(不是PAD的位置）的 mask 改为 1：
      ids = [[1,10, 2,0],     mask = [[1,1,1,0],
             [1,20,21,2],             [1,1,1,1],
             [1,11,12,2],             [1,1,1,1],
             [1,22, 2,0]]             [1,1,1,0]]。
    输出：(ids,mask)，两个 torch.long 类型的 [4,4] 张量。
      若后续 scores=[0.8,0.6,0.1,-0.2]，chunk(2) 得到 chosen=[0.8,0.6]、
      rejected=[0.1,-0.2]，相同下标仍然对应原来同一对数据。
    '''
    def collate(self, batch):
        # 前 B 条 chosen，后 B 条 rejected，动态右侧补齐到本批最长序列。
        # 例：B=2，两对数据为 (c0,r0)、(c1,r1)。列表推导先遍历 key，再遍历样本：
        #     sequences = [c0, c1, r0, r1]，不是 [c0, r0, c1, r1]。
        # 这个顺序必须与训练端 scores.chunk(2) 一致，才能保证 c0 与 r0 成对比较。
        sequences = [row[key] for key in ("chosen_ids", "rejected_ids") for row in batch]
        # 只补到当前批次的最长序列，而不是全部补到 max_length，可减少无效计算。
        width = max(map(len, sequences))
        # torch.full 创建全为 pad_id 的 [2B,T] 张量；long 整数类型用于词向量索引。
        ids = torch.full((len(sequences), width), self.pad_id, dtype=torch.long)
        # zeros_like 复制 ids 的形状和类型，初始 mask 全为 0，表示全部是补齐位置。
        mask = torch.zeros_like(ids)
        for i, sequence in enumerate(sequences):
            # 真实 token 放在每行左侧，对应 mask 改为 1；右侧保留 PAD 和 0。
            ids[i, :len(sequence)] = torch.tensor(sequence)
            mask[i, :len(sequence)] = 1
        # 显式长度掩码：即使 pad_id == eos_id，也不会误屏蔽真实 EOS。
        # 例如 pad_id=2、真实序列=[1,10,2]、T=5：
        #     ids  = [1,10,2,2,2]
        #     mask = [1, 1,1,0,0]，不能用 ids != pad_id 来生成 mask。
        # mask 覆盖历史和回答的所有真实 token；它不是 DPO/SFT 中只挑选答案的 loss_mask。
        return ids, mask


# 奖励模型把“问题/历史 + 完整回答”映射成一个实数；分数越高表示模型越偏好。
# 同一个模型分别给 chosen 和 rejected 打分，没有两套独立的评分网络。
'''
【MiniMindRewardModel 类：一段对话怎样得到一个分数】
输入配置：cfg=MiniMindConfig(hidden_size=4, num_hidden_layers=1,
  num_attention_heads=2, num_key_value_heads=1, vocab_size=32,
  max_position_embeddings=16, use_moe=False)。
  这是手算用的小模型，直接在 Python 中构造；命令行默认 8 个头，示例命令用 H=64。
第 1 步：rm=MiniMindRewardModel(cfg)，创建一个骨干和一个 Linear(4,1) 评分头。
第 2 步：输入 ids=tensor([[1,10,2]])、mask=tensor([[1,1,1]])，形状为 [1,3]。
第 3 步：调用 scores,aux=rm(ids,mask)，实际进入 forward，得到 hidden 的形状 [1,3,4]。
第 4 步：假设最后一个 token 的表示为 [2,0,0,0]，评分头权重为 [0.5,-0.5,0.25,0]。
  这些向量是为讲解指定的假设值，不是随机初始化模型一定会产生的值。
第 5 步：取这个末尾表示与权重做点积：2*0.5+0*(-0.5)+0*0.25+0*0=1。
输出：构造调用得到 rm 对象；前向调用得到 (tensor([1.0]), tensor(0.0))。
  scores 的形状为 [1]；稠密模型 aux=0；它没有返回词表概率，也没有生成新回答。
'''
class MiniMindRewardModel(nn.Module):
    '''
    【MiniMindRewardModel.__init__：从配置创建可训练参数】
    输入：上面的小配置 cfg，H=4、层数=1、词表大小=32、最大位置数=16。
    第 1 步：super().__init__() 初始化 PyTorch 模块的参数和子模块注册机制。
    第 2 步：self.config=cfg，保留结构配置以便后续保存和检查长度。
    第 3 步：MiniMindModel(cfg) 创建骨干，其中词向量表形状为 [32,4]，有 1 个 Block。
    第 4 步：Linear(4,1,bias=False) 创建形状 [1,4] 的权重，不创建 bias 参数。
    第 5 步：normal_ 原地填充评分头，例如一次抽样可能近似 [0.01,-0.02,0.005,0.03]。
      这里只说明分布，不能由 cfg 直接推出这些随机数；实际值受随机状态影响。
    输出/副作用：self.model 和 self.reward_head 注册为子模块，默认参数可训练。
      state_dict 的键含 model.embed_tokens.weight、各层权重、reward_head.weight 等。
      __init__ 返回 None；此处没有读入 SFT 权重，SFT 初始化由 main 随后完成。
    '''
    def __init__(self, config):
        # 初始化 nn.Module 后，赋给 self 的子模块会自动注册，纳入 parameters/state_dict。
        super().__init__()
        self.config = config
        # 骨干输出每个 token 的 H 维上下文表示，而不是词表上的生成概率。
        self.model = MiniMindModel(config)
        # Linear(H,1) 的权重形状为 [1,H]，将一句话的表示压成一个标量。
        # bias=False：省略所有样本共享的常数偏置；这种偏置在 chosen-rejected 中会抵消。
        self.reward_head = nn.Linear(config.hidden_size, 1, bias=False)
        # 评分头没有可直接复用的 SFT 权重，因此用均值 0、标准差 0.02 的正态分布初始化。
        nn.init.normal_(self.reward_head.weight, mean=0.0, std=0.02)

    # 输入 input_ids、attention_mask 都是 [N,T]；输出 scores 为 [N]，aux_loss 为标量。
    # 训练时 N=2B；get_score 对单条回答评分时 N=1。
    '''
    【forward：末尾定位 → 提取向量 → 线性评分的完整手算】
    输入：N=2、T=4、H=4，使用上面的 4 维配置；
      input_ids      = tensor([[1,10,2,0], [1,20,21,2]])，形状 [2,4]；
      attention_mask = tensor([[1, 1,1,0], [1, 1, 1,1]])，形状 [2,4]。
    第 1 步：骨干计算 hidden，形状 [2,4,4]；假设最终归一化后的 hidden 为：
      第 0 条：[[1,0,0,0], [0,1,0,0], [2,0,0,0], [9,9,9,9]]；
      第 1 条：[[1,0,0,0], [0,1,0,0], [0,0,1,0], [0,2,0,0]]。
      这些是本步骤的教学输入假设，不是凭 token 编号就能推算出的真实骨干输出。
      第 0 条末尾 [9,9,9,9] 是 padding 位置的示意值，不应被选作整句表示。
    第 2 步：attention_mask.sum(dim=1)=[3,4]，减 1 得到 last=[2,3]。
    第 3 步：arange(2)=[0,1]，配对索引选 hidden[0,2] 与 hidden[1,3]，得到：
      final_hidden=[[2,0,0,0],[0,2,0,0]]，形状 [2,4]。
    第 4 步：假设 reward_head.weight=[[0.5,-0.5,0.25,0]]，形状 [1,4]。
      第一行点积：2*0.5 + 0*(-0.5) + 0*0.25 + 0*0 = 1；
      第二行点积：0*0.5 + 2*(-0.5) + 0*0.25 + 0*0 = -1。
    第 5 步：Linear 输出 [[1],[-1]]，形状 [2,1]；squeeze(-1) 变成 [1,-1]。
    输出：(scores,aux_loss)=(tensor([1.0,-1.0]), tensor(0.0))，本例为非 MoE。
      若这两行依次是同一对的 chosen/rejected，则分差为 2，偏好损失约 0.1269；
      但 forward 只返回分数和辅助损失，偏好损失由 main 的训练循环计算。
    '''
    def forward(self, input_ids, attention_mask):
        # hidden: [N,T,H]；中间的 _ 接收未使用的 KV 缓存；aux_loss 是 MoE 辅助损失。
        # 非 MoE 的普通稠密模型中 aux_loss 为 0。
        hidden, _, aux_loss = self.model(input_ids, attention_mask=attention_mask)
        # 右侧 padding：最后一个真实 token 已通过因果注意力看到完整上下文和回答。
        # 例如 mask=[[1,1,1,0,0],[1,1,1,1,1]]，真实长度为 [3,5]，末尾下标为 [2,4]。
        # 这里要求每行至少有一个真实 token，且使用右侧 padding；不能直接套用左侧 padding。
        '''
        【last = attention_mask.sum(dim=1) - 1：找到每条输入最后一个有效 token 的下标】

        第 1 步：先看两条长度不同的输入。
            第一条：[A, B, C]，有 3 个 token。
            第二条：[D, E, F, G, H]，有 5 个 token。
        A～H 只是 token 的示意名字，实际 input_ids 中保存的是整数编号。
        为了组成同一个矩形张量，把短的那条在右侧补齐：
            第一条：[A, B, C, PAD, PAD]
            第二条：[D, E, F, G,   H  ]
        PAD 是补齐用的占位符，不属于原始输入；补在右边就叫“右侧 padding”。

        第 2 步：用 attention_mask 标出真实位置。
            1 表示有效 token，0 表示补齐的 PAD：
            attention_mask = tensor([
                [1, 1, 1, 0, 0],
                [1, 1, 1, 1, 1]
            ])
        形状是 [2,5]：2 条输入，每条补齐后有 5 个位置。

        第 3 步：sum(dim=1) 沿着每一行的 token 位置求和。
            第一行：1+1+1+0+0 = 3
            第二行：1+1+1+1+1 = 5
            attention_mask.sum(dim=1) = tensor([3,5])
        得到的是每条输入的有效长度，而不是位置下标。
        这里 dim=0 是批次维，dim=1 是 token 位置维；指定 dim=1 就把每行求和成一个数。

        第 4 步：长度减 1，得到从 0 开始的最后一个有效位置下标。
            下标：    0  1  2   3    4
            第一条： [A, B, C, PAD, PAD]  → C 的下标是 2，即 3-1。
            第二条： [D, E, F, G,   H  ]  → H 的下标是 4，即 5-1。
            last = tensor([3,5]) - 1 = tensor([2,4])
        输出 last 的形状为 [2]：每条输入各对应一个下标。

        第 5 步：下一行代码按这些下标取隐藏向量。
            torch.arange(hidden.size(0)) = tensor([0,1])
            hidden[[0,1], [2,4]] 表示分别取：
                hidden[0,2]：第一条输入 C 位置的隐藏向量；
                hidden[1,4]：第二条输入 H 位置的隐藏向量。
        若 hidden 的形状是 [2,5,H]，取出的 final_hidden 就是 [2,H]。
        取的是对应位置的 H 维隐藏向量，不是 token 编号本身。
        因果注意力让一个位置可以利用此前的内容：
            A 位置可利用 A；B 位置可利用 A、B；C 位置可利用 A、B、C。
        因而最后一个有效位置可以结合整段输入的信息，再交给评分头计算整句分数。

        为什么不能直接用于左侧 padding？
            下标：    0    1   2  3  4
            输入：  [PAD, PAD, A, B, C]
            mask：  [ 0,   0,  1, 1, 1]
        求和减一还是 3-1=2，但 C 的真实下标是 4，公式就选错了位置。
        所以本公式要求有效位置从下标 0 开始连续排列、PAD 全放在右侧，且至少有一个有效 token。
        '''
        last = attention_mask.sum(dim=1) - 1
        # arange(N)=[0,1,...,N-1] 与 last 配对索引：取 hidden[0,last[0]] 等。
        # 结果 final_hidden 为 [N,H]；它可能对应模板末尾的分隔符，不一定是答案最后一个字。
        final_hidden = hidden[torch.arange(hidden.size(0), device=hidden.device), last]
        # [N,H] → Linear → [N,1] → squeeze(-1) → [N]。
        # 只去掉最后一维，单条输入时仍保留 [1] 的批次维；分数没有 sigmoid，也不限于 [0,1]。
        scores = self.reward_head(final_hidden).squeeze(-1)
        return scores, aux_loss

    # no_grad 让评分过程不构建反向图，减少开销；它不会自动把模型切成 eval 模式。
    '''
    【get_score：把原始文字变成一个 Python 分数】
    输入：rm 位于 CPU，调用前 rm.training=True；messages 为：
      [{"role":"user","content":"1+1?"}, {"role":"assistant","content":"2"}]。
    调用：score=rm.get_score(tokenizer,messages)，无须调用者自己构造张量。
    第 1 步：假设 encode_messages 得到 [1,10,20,2]，长度 4<=模型位置容量 16。
    第 2 步：读取参数设备 cpu，创建 input_ids=tensor([[1,10,20,2]])，形状 [1,4]。
    第 3 步：保存 was_training=True，再 eval() 暂时进入评估模式。
    第 4 步：ones_like 构造 mask=[[1,1,1,1]]，交给 forward。
    第 5 步：假设末尾表示为 [2,0,0,0]，头权重为 [0.5,-0.5,0.25,0]，
      则 forward 得到 scores=tensor([1.0])；item() 将其转为 Python float 1.0。
    第 6 步：返回前 finally 执行 train(True)，恢复调用前的模式。
    输出：1.0；rm.training 又为 True，参数没有更新，也没有构建训练反向图。
    分支：若调用前本来为 eval，则最终恢复 False；若输入超过位置容量则抛 ValueError。
      这个 1.0 是假设权重下的原始分数，不能解读为“正确率 100%”。
    '''
    @torch.no_grad()
    def get_score(self, tokenizer, messages):
        """messages 为含最终 assistant 回答的完整消息列表，返回未校准的原始分数。"""
        ids = encode_messages(tokenizer, messages)
        # 推理时检查模型的位置容量；这与训练的数据过滤阈值 max_seq_len 是两个概念。
        # 未超过位置容量并不保证模型在远长于训练样本的输入上仍能可靠评分。
        if not ids or len(ids) > self.config.max_position_embeddings:
            raise ValueError("输入为空或超过模型位置长度限制")
        # 从第一个参数读取模型当前设备，保证输入张量与模型位于同一 CPU/GPU。
        device = next(self.parameters()).device
        # [ids] 增加批次维：[T] → [1,T]，这样可复用与批量训练相同的 forward。
        input_ids = torch.tensor([ids], dtype=torch.long, device=device)
        # 保存原模式；eval 关闭 Dropout 等层的训练行为，但不会永久冻结模型参数。
        was_training = self.training
        self.eval()
        try:
            # 单条输入不需要补齐PAD，因此 attention_mask 全为 1；这里不使用 MoE 辅助损失。
            scores, _ = self(input_ids, torch.ones_like(input_ids))
            # item() 把单元素张量转成 Python float，便于打印或作为外部奖励使用。
            return scores.item()
        finally:
            # 无论正常返回还是推理报错，都恢复调用前的 train/eval 状态。
            self.train(was_training)


# 读取本脚本导出的奖励模型：先恢复结构，再加载骨干及评分头，最后迁移到目标设备。
'''
【load_reward_model：从文件恢复同一套评分参数】
输入：path="out/reward_demo.pth"、device="cpu"；假设文件由 save_reward_model 保存，
      内含 H=4、1 层、2 个注意力头、1 个 KV 头、词表 32、位置容量 16 的完整配置，
      以及完整骨干权重和 reward_head.weight=[[0.5,-0.5,0.25,0]]。
第 1 步：torch.load 将文件读到 CPU，得到含 config、model 两个字段的字典。
第 2 步：MiniMindConfig(**checkpoint["config"]) 恢复模型结构配置。
第 3 步：MiniMindRewardModel(config) 创建同样结构的网络；此时参数还是新初始化的。
第 4 步：load_state_dict 把 checkpoint["model"] 的全部参数复制进新网络，
        覆盖刚初始化的值，评分头也恢复为 [[0.5,-0.5,0.25,0]]。
第 5 步：to("cpu") 确定运行设备，eval() 设置评估模式。
输出：一个 MiniMindRewardModel 实例，model.training=False，参数在 CPU 上。
验证思路：若保存前模型在 eval 模式对 ids/mask 输出 [1,-1]，恢复后的模型使用
          相同输入和相同计算设置，也应得到相同分数（浮点比较允许微小误差）。
错误分支：若文件缺少 reward_head.weight，strict=True 会报错；不会静默留下随机评分头。
'''
def load_reward_model(path, device="cpu"):
    # map_location="cpu" 避免一读取就占用保存时的 GPU；weights_only=True 使用受限加载方式。
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    # ** 把配置字典展开为关键字参数，恢复训练时的 hidden_size、层数、MoE 等配置。
    config = MiniMindConfig(**checkpoint["config"])
    model = MiniMindRewardModel(config)
    # strict=True 核对键名；形状不匹配也会报错，防止遗漏评分头或加载到错误架构。
    model.load_state_dict(checkpoint["model"], strict=True)
    return model.to(device).eval()


# 保存“结构配置 + 参数”，用于重新加载评分；未保存优化器、训练步数和随机数状态。
# 因而这是模型导出文件，不是完整断点续训文件；tokenizer 仍使用单独的 tokenizer_path。
'''
【save_reward_model：把配置与参数导出为文件】
输入：model 为 H=4 的奖励模型，path="out/reward_demo.pth"；假设模型位于 GPU，
      reward_head.weight=[[0.5,-0.5,0.25,0]]，还有完整的骨干参数。
第 1 步：Path(path) 构造路径对象，mkdir 确保 out 目录存在。
第 2 步：with_suffix(".pth.tmp") 得到临时路径 out/reward_demo.pth.tmp。
第 3 步：config.to_dict() 收集 H、层数、头数、词表大小等完整结构配置。
第 4 步：遍历 state_dict，对每个张量执行 detach().cpu()，组成待写入的参数字典。
        例如 reward_head.weight 被保存成 CPU 上的 [[0.5,-0.5,0.25,0]]；
        model.embed_tokens.weight 等全部骨干权重也会一并保存。
第 5 步：torch.save 写入临时文件，内容结构可概括为：
        {"config": 完整配置字典, "model": 完整权重字典}。
        这里的“完整”不能省略：只存一个评分头并不足以重新构造同一个奖励模型。
第 6 步：temporary.replace(path) 将临时文件替换为正式文件。
输出/副作用：磁盘上出现 out/reward_demo.pth；函数本身隐式返回 None。
            原模型仍在原设备上，参数值和 train/eval 模式不因保存而改变。
后续使用：loaded=load_reward_model("out/reward_demo.pth") 可恢复模型；
          但文件没有优化器、步数和随机数状态，因此不用于精确恢复中断的训练过程。
'''
def save_reward_model(model, path):
    path = Path(path)
    # parents=True 递归建立所需父目录；exist_ok=True 允许目录已存在。
    path.parent.mkdir(parents=True, exist_ok=True)
    # 先写 reward_768.pth.tmp，再替换正式文件，减少写入中断直接损坏原有正式文件的机会。
    temporary = path.with_suffix(path.suffix + ".tmp")
    # state_dict 包含已注册参数/持久化缓冲区；detach 断开梯度关系，cpu 转到 CPU 后序列化。
    # 这不会将训练中的模型搬离 GPU；也不调用 half()，这里保存的是 FP32 权重。
    torch.save({"config": model.config.to_dict(),
                "model": {k: v.detach().cpu() for k, v in model.state_dict().items()}}, temporary)
    temporary.replace(path)


# 程序入口：解析参数 → 选择评分/训练分支 → 初始化模型和数据 → 优化参数 → 导出权重。
'''
【main：把数据、评分、偏好损失、梯度更新和保存串起来】
示例 A 的输入：在内层 minimind 目录执行下面这一条完整命令：
  python trainer/train_reward.py --from_weight none --hidden_size 64 --num_hidden_layers 1 --data_path dataset/reward_demo.jsonl --batch_size 2 --max_steps 1 --device cpu
  main 没有显式函数参数；它通过 argparse 读取命令行，通过文件路径读取数据和分词器。

第 1 步：解析得到 hidden_size=64、num_hidden_layers=1、batch_size=2、max_steps=1，
        from_weight="none"、device="cpu"，其余参数取默认值。
第 2 步：固定随机种子并加载 tokenizer；没有 score_checkpoint，所以进入训练分支。
第 3 步：创建 64 维、1 层的奖励模型；from_weight="none"，故不加载 SFT 参数。
        若改用默认 full_sft，则读取匹配尺寸的 SFT 文件，只加载 model.* 骨干权重。
第 4 步：演示文件有 4 对；假设均通过过滤，DataLoader 每批取 2 对，共可产生 2 批。
        shuffle 会打乱对的顺序；为手算，假设本批取到的序列长度为 [3,4,4,3]。
第 5 步：collate 排列为 [c0,c1,r0,r1]，构造 ids/mask，形状都是 [4,4]。
第 6 步：前向得到 hidden=[4,4,64]，选末尾状态变成 [4,64]，评分头输出 [4]。
        假设 scores=[1.0,0.0,-1.0,1.0]，aux_loss=0；这些分数只是手算示例，
        不是承诺随机模型执行上述命令时会输出这些数值。
第 7 步：scores.chunk(2) 得到 chosen=[1,0]、rejected=[-1,1]。
        两个分差为 [2,-1]，模型预测 chosen 更优的概率约为 [0.8808,0.2689]。
第 8 步：逐对计算负对数损失：[0.126928,1.313262]；
        ranking_loss=(0.126928+1.313262)/2≈0.720095；加上 aux_loss=0，loss 不变。
第 9 步：zero_grad 清空旧梯度，backward 沿两个回答的评分链路计算梯度。
        对每对分差 Δ，批平均损失的导数为 (sigmoid(Δ)-1)/2，
        因此本例 dL/dchosen≈[-0.059601,-0.365529]，
        dL/drejected≈[0.059601,0.365529]；它们再经评分头传回骨干。
        这是对输出分数的导数，不是完整参数梯度；参数梯度还取决于隐藏状态等中间量。
第 10 步：裁剪参数梯度的整体范数，再由 AdamW 更新参数，step 从 0 变为 1。
         更新后的具体权重还取决于实际参数、梯度和优化器状态，不能仅凭 loss 数值推出。
第 11 步：打印这批更新前的指标：accuracy=0.5，chosen 均值=0.5，rejected 均值=0。
         示例日志为：epoch=1 step=1 loss=0.7201 ranking_loss=0.7201 accuracy=0.500 chosen=0.500 rejected=0.000
第 12 步：达到 max_steps=1，退出内层循环，保存 out/reward_64.pth，再退出外层循环。
输出/副作用：生成奖励模型文件并打印日志；main 本身返回 None，不返回模型实例。

示例 B 的输入：使用刚保存的文件执行下面这一条命令：
  python trainer/train_reward.py --score_checkpoint out/reward_64.pth --prompt "1+1等于几？" --response "等于2。" --device cpu
第 1 步：加载 tokenizer，发现 score_checkpoint 已指定，进入评分分支。
第 2 步：从文件恢复模型结构和权重；这里用的是检查点的 H=64，而非命令行默认 H=768。
第 3 步：把 prompt/response 组成 user/assistant 消息列表，调用 get_score。
第 4 步：假设实际返回 0.25，打印 reward = 0.250000，然后 return。
输出/副作用：终端上一个分数，main 返回 None；此分支不读取偏好数据、不执行参数更新。
'''
def main():
    # ========== 1. 解析参数并准备分词器 ==========
    # __doc__ 是文件开头的说明文字；RawDescriptionHelpFormatter 保留其中的命令排版。
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # 数据与权重路径：默认读取 DPO 数据；init_checkpoint 可直接指定已有 SFT 的 .pth 文件。
    parser.add_argument("--data_path", default=str(ROOT / "dataset/dpo.jsonl"))
    parser.add_argument("--tokenizer_path", default=str(ROOT / "model"))
    parser.add_argument("--from_weight", default="full_sft", help="SFT 权重前缀；none 表示随机初始化")
    parser.add_argument("--init_checkpoint", help="显式指定 SFT state_dict 的 .pth 路径")
    parser.add_argument("--save_path", help="默认保存为项目 out/reward_<hidden_size>[_moe].pth")
    # 模型结构参数必须匹配 SFT 骨干；评分模式会改用检查点里保存的结构配置。
    parser.add_argument("--hidden_size", type=int, default=768)
    parser.add_argument("--num_hidden_layers", type=int, default=8)
    parser.add_argument("--use_moe", action="store_true")
    # batch_size 以偏好对计数；max_seq_len 是整段序列的 token 长度上限，超限整对过滤。
    parser.add_argument("--max_seq_len", type=int, default=1024)
    parser.add_argument("--batch_size", type=int, default=2, help="每批偏好对数量，实际前向序列数为两倍")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning_rate", type=float, default=1e-5)
    # max_steps 限制全部 epoch 合计的更新次数；max_samples 则在分词前限制原始样本数量。
    parser.add_argument("--max_steps", type=int, help="最多更新次数，用于快速验证流程")
    parser.add_argument("--max_samples", type=int, help="只读取前 N 条数据用于教学实验")
    parser.add_argument("--log_interval", type=int, default=10)
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    # 传入 score_checkpoint 就只加载打分；prompt/response 是这一模式下的单轮对话输入。
    parser.add_argument("--score_checkpoint", help="指定训练好的 RM 文件，进入评分模式")
    parser.add_argument("--prompt", default="1+1等于几？")
    parser.add_argument("--response", default="等于2。")
    args = parser.parse_args()
    # 可选参数未传时是 None；一旦显式指定，数量和学习率都要求大于 0。
    for name in ("hidden_size", "num_hidden_layers", "max_seq_len", "batch_size", "epochs",
                 "learning_rate", "log_interval", "max_steps", "max_samples"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            parser.error(f"--{name} 必须大于 0")
    # 固定 PyTorch 随机种子，便于重复教学实验；不保证跨设备、跨版本逐位一致。
    torch.manual_seed(42)
    # 同一个 tokenizer 必须用于训练和评分，否则相同文字可能被映射成不同 token 编号。
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_path)

    # ========== 2. 单条评分分支 ==========
    if args.score_checkpoint:
        model = load_reward_model(args.score_checkpoint, args.device)
        messages = [{"role": "user", "content": args.prompt},
                    {"role": "assistant", "content": args.response}]
        print(f"reward = {model.get_score(tokenizer, messages):.6f}")
        # 完成评分后退出，不再加载偏好数据，也不会创建优化器。
        return

    # ========== 3. 创建奖励模型，并用 SFT 参数初始化骨干 ==========
    # 默认 8 个 attention heads，每头维度为偶数（RoPE 的要求）。
    # 所以 hidden_size / 8 要是偶数，即 hidden_size 必须能被 16 整除。
    if args.hidden_size % 16:
        parser.error("--hidden_size 必须是 16 的倍数")
    config = MiniMindConfig(hidden_size=args.hidden_size, num_hidden_layers=args.num_hidden_layers,
                           use_moe=args.use_moe)
    if args.max_seq_len > config.max_position_embeddings:
        parser.error("--max_seq_len 超过模型位置长度限制")
    model = MiniMindRewardModel(config)
    # MoE 与稠密模型使用不同默认文件名，避免默认导出路径混在一起。
    suffix = "_moe" if args.use_moe else ""
    if args.init_checkpoint or args.from_weight != "none":
        # 显式 init_checkpoint 优先；否则按前缀、隐藏维度和 MoE 后缀拼出默认 SFT 路径。
        path = args.init_checkpoint or ROOT / "out" / f"{args.from_weight}_{args.hidden_size}{suffix}.pth"
        if not Path(path).is_file():
            parser.error(f"找不到 SFT 权重 {path}；请提供 --init_checkpoint，或用 --from_weight none 演示")
        weights = torch.load(path, map_location="cpu", weights_only=True)
        # 仅加载骨干；严格核对全部骨干参数，语言模型 lm_head 不用于奖励评分。
        # 例：SFT 的 "model.embed_tokens.weight" → 骨干自己的 "embed_tokens.weight"。
        # k[len("model."):] 去掉前缀，是因为加载目标 model.model 已经是骨干这一层。
        # lm_head.weight 不满足 startswith("model.")，因此不会被加载进评分头。
        backbone = {k[len("model."):]: v for k, v in weights.items() if k.startswith("model.")}
        model.model.load_state_dict(backbone, strict=True)
        print(f"已加载 SFT 骨干: {path}；reward_head 随机初始化")
    else:
        print("演示模式：骨干和评分头均随机初始化")

    # ========== 4. 数据组批及优化器 ==========
    train_data = RewardDataset(args.data_path, tokenizer, args.max_seq_len, args.max_samples)
    # shuffle=True 每次遍历时打乱偏好对顺序，但不会拆散同一对 chosen/rejected。
    # collate_fn 使用上面定义的动态补齐；num_workers=0 表示主进程取数，便于 Windows 调试。
    # 未设置 drop_last，最后不足 batch_size 的偏好对仍参与训练。
    loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=True,
                        collate_fn=train_data.collate, num_workers=0)
    # to 移动参数到设备；train 设置训练模式。本脚本不启用 autocast/GradScaler，使用 FP32。
    model.to(args.device).train()
    # parameters() 包括骨干与评分头，均参与优化；本脚本没有冻结骨干，也没有学习率调度。
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    # ========== 5. 逐批训练：评分 → 比较偏好 → 反传 → 更新 ==========
    # 一批执行一次 optimizer.step，没有梯度累积；step 是跨 epoch 的总更新次数。
    step = 0
    for epoch in range(args.epochs):
        '''
        【for input_ids, mask in loader：一次循环拿到什么数据？】

        第 1 步：假设 batch_size=2，DataLoader 本次取到两对偏好数据。
            第 0 对：chosen_ids=[1,10,2]，rejected_ids=[1,11,12,2]。
            第 1 对：chosen_ids=[1,20,21,2]，rejected_ids=[1,22,2]。
        每个列表代表“聊天模板 + 对话历史 + 该回答”的完整 token 编码。
        这里用短整数列表演示组批，不能据此推断实际文字的 token 编号。
        一对含 chosen/rejected 两条序列，所以 batch_size=2 实际送入模型的是 4 条序列。

        第 2 步：DataLoader 调用 train_data.collate，把两对样本整理成矩形张量。
            先放所有 chosen，再放所有 rejected，行顺序为 [c0,c1,r0,r1]。
            四条长度为 [3,4,4,3]，本批最长为 4；假设 pad_id=0，在右侧补齐。

        第 3 步：collate 返回 (ids, mask)，for 循环自动将这两个值拆开：
            input_ids 接收 ids，mask 接收 mask。
            input_ids = tensor([
                [1,10, 2,0],    # 第 0 对 chosen，最后的 0 是 PAD
                [1,20,21,2],    # 第 1 对 chosen，没有 PAD
                [1,11,12,2],    # 第 0 对 rejected，没有 PAD
                [1,22, 2,0]     # 第 1 对 rejected，最后的 0 是 PAD
            ])
            mask = tensor([
                [1,1,1,0],
                [1,1,1,1],
                [1,1,1,1],
                [1,1,1,0]
            ])
        两个张量都是 torch.long，形状为 [4,4]，也就是 [2B,T]：
            2B=4 是本批序列数量；T=4 是补齐后的序列长度。
        input_ids 告诉模型“每个位置是什么 token”；mask 告诉模型“哪些位置有效”。
        mask 的 1 表示真实输入、0 表示补齐位置，不表示回答正确或错误。
        chosen 和 rejected 的真实 token 都标 1；共同的问题和历史也标 1。

        第 4 步：循环体将两个张量搬到 args.device，数值和形状不变，再一起传给模型。
            本例 mask.sum(dim=1)=[3,4,4,3]，减 1 得 last=[2,3,3,2]。
            模型据此为每行取最后一个有效位置的隐藏向量，再计算一个奖励分数。
            假设 scores=[0.8,0.6,0.1,-0.2]，scores.chunk(2) 得到：
                chosen=[0.8,0.6]，rejected=[0.1,-0.2]。
            比较的是 0.8 与 0.1、0.6 与 -0.2，仍是原来的两对回答。

        输出理解：for 的每次迭代拿到的是“一整个批次的两个张量”，不是单个 token，
                  也不是 input_ids 为 chosen、mask 为 rejected。
        下一批会重新组批，T 可以不同；最后一批不足两对时，第一维也可能小于 4。
        '''
        for input_ids, mask in loader:
            # input_ids/mask: [2B,T]。to 只迁移设备，不改变 token 编号、形状或掩码含义。
            input_ids, mask = input_ids.to(args.device), mask.to(args.device)
            # 调用 nn.Module 会进入 forward；scores=[c0,c1,...,r0,r1,...]，形状为 [2B]。
            scores, aux_loss = model(input_ids, mask)
            # chunk(2) 默认沿第 0 维切成两半；chosen、rejected 各为 [B]，相同下标是一对。
            chosen, rejected = scores.chunk(2)
            # Bradley–Terry 偏好模型：P(chosen 胜出) = sigmoid(r_chosen - r_rejected)。
            # 不需要人工提供绝对分数；梯度同时更新评分头和 MiniMind 骨干。
            '''
            【损失示例】一对样本 chosen=2、rejected=0：
              分差 Δ=2，sigmoid(Δ)≈0.881，-log(0.881)≈0.127，排序正确且损失较小。
            若 chosen=0、rejected=2：Δ=-2，胜出概率≈0.119，损失≈2.127，惩罚较大。
            两者相等时损失≈0.693；mean() 对本批 B 个偏好对求平均，不对 token 求平均。
            对单对损失，dL/dΔ=sigmoid(Δ)-1：梯度下降倾向增大 chosen-rejected 的差值。
            两边分数由共享参数产生，因此单次更新不保证每个样本分数都独立升/降。
            F.logsigmoid 比先算 sigmoid 再 log 更数值稳定；float() 明确使用 FP32 算损失。
            监督只约束相对分差，不给出绝对分数标尺；分数为负不直接等于回答“差”。
            '''
            ranking_loss = -F.logsigmoid(chosen.float() - rejected.float()).mean()
            # MoE 时加上专家路由的负载均衡辅助项；稠密模型的 aux_loss 为 0。
            # 它来自同一批前向计算，与 ranking_loss 共同影响骨干梯度。
            loss = ranking_loss + aux_loss
            # 清除上一批梯度；set_to_none=True 释放梯度引用，让本次 backward 重新创建梯度。
            # 本脚本不做梯度累积，所以每个批次都要清零，不能将旧梯度一直保留下来。
            optimizer.zero_grad(set_to_none=True)
            # backward 只计算并写入参数的 .grad，还未更新参数值；两边评分都保留梯度链路。
            loss.backward()
            # 对所有参数梯度的整体 L2 范数裁剪，上限为 1.0；裁剪梯度，不是裁剪奖励分数。
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            # AdamW 根据梯度、动量及权重衰减更新骨干和评分头的参数。
            optimizer.step()
            step += 1
            # ========== 6. 打印训练指标，并检查提前停止条件 ==========
            if step == 1 or step % args.log_interval == 0:
                # 例：chosen=[2,0]、rejected=[0,1]，比较结果为 [True,False]，accuracy=0.5。
                # 相等不算排序正确；这是当前训练批次的比例，不是 epoch 平均或验证集结果。
                # 使用的是本次参数更新前的前向分数，没有在 step 后重新评分。
                accuracy = (chosen > rejected).float().mean().item()
                # item() 转成 Python 标量；chosen/rejected 日志分别是本批两组原始分数均值。
                print(f"epoch={epoch + 1} step={step} loss={loss.item():.4f} "
                      f"ranking_loss={ranking_loss.item():.4f} accuracy={accuracy:.3f} "
                      f"chosen={chosen.mean().item():.3f} rejected={rejected.mean().item():.3f}")
            if args.max_steps is not None and step >= args.max_steps:
                # 先退出内层批次循环，随后仍会执行下面的保存，避免丢失最后一次更新。
                break
        # ========== 7. 本轮结束（或达到 max_steps）后保存模型 ==========
        # 每轮写同一路径，保留最近一次导出；保存的是 optimizer.step 后的最新参数。
        path = args.save_path or ROOT / "out" / f"reward_{args.hidden_size}{suffix}.pth"
        save_reward_model(model, path)
        print(f"已保存奖励模型: {path}")
        if args.max_steps is not None and step >= args.max_steps:
            # 再退出外层 epoch 循环；否则只退出内层会在下一轮继续训练。
            break


# 直接运行本文件时启动 main；被其他脚本 import 时只提供数据集、模型和加载函数。
if __name__ == "__main__":
    main()
