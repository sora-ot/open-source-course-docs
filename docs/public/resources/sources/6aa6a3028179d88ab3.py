# PPO 在线强化学习：采样回答 → 计算奖励和 GAE → 多轮更新 Actor/Critic → 保存权重。
# B=提示数量，P=提示长度，R=回答长度；old 为采样时策略，ref 为冻结参考策略。
import os
import sys

__package__ = "trainer"
# 直接运行子目录脚本时将项目根加入模块搜索路径，以便导入 model、dataset、trainer。
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import datasets  # noqa: F401  # Windows pyarrow/torch DLL conflict workaround (issue #771)
import argparse
import math
import re
import warnings
import torch
import torch.distributed as dist
import torch.nn.functional as F
from contextlib import nullcontext
from torch import optim, nn
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, DistributedSampler
from torch.nn.utils import clip_grad_norm_
from torch.optim.lr_scheduler import CosineAnnealingLR
from model.model_minimind import MiniMindConfig, MiniMindForCausalLM
from dataset.lm_dataset import RLAIFDataset
from trainer.trainer_utils import Logger, is_main_process, lm_checkpoint, init_distributed_mode, setup_seed, SkipBatchSampler, init_model, LMForRewardModel
from trainer.rollout_engine import create_rollout_engine

warnings.filterwarnings('ignore')

# 用于计算文本中的 n-gram 重复惩罚。
# 不同的 n-gram 如下：
# - 1-gram：单个词，如 ("我",)、("喜欢",)
# - 2-gram：连续两个词，如 ("我", "喜欢")
# - 3-gram：连续三个词，如 ("我", "喜欢", "吃")
# 连续出现的相同词组越多，惩罚越大；默认最大惩罚是 0.5。
# 默认检查连续 3 个 token 组成的词组，也就是 trigram。
# toks = ["a", "b", "c", "a", "b", "c"]
# grams = [
#     ("a", "b", "c"),
#     ("b", "c", "a"),
#     ("c", "a", "b"),
#     ("a", "b", "c")
# ]
# text = "a b c a b c"
# len(grams) = 4
# len(set(grams)) = 3
# (4 - 3) * 0.5 * 2 / 4
# = 0.25
def rep_penalty(text, n=3, cap=0.5):
    toks = re.findall(r"\w+|[^\w\s]", text.lower())#text = "Hello, world!" toks = ["hello", ",", "world", "!"]
    grams = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    return min(cap, (len(grams) - len(set(grams))) * cap * 2 / len(grams)) if grams else 0.0

# 自定义的Critic模型，继承自MiniMindLM
# 在 MiniMind 隐藏状态上增加标量价值头，为每个 token 位置预测未来回报。
# advantage = 实际回报 - Critic预测价值
# 例如实际回报是 0.9，Critic 预测为 0.6：
# advantage = 0.9 - 0.6 = 0.3
# 说明生成结果比预期好，PPO 会提高相关 token 的生成概率。
# 如果实际回报为 0.2：
# advantage = 0.2 - 0.6 = -0.4
# 说明结果比预期差，PPO 会降低相关 token 的生成概率。
# 需要区分两类模型：
# - Reward Model：给完整回答打分，表示回答实际有多好。
# - Critic Model：预测生成到当前 token 时，未来大约能得到多少奖励。
class CriticModel(MiniMindForCausalLM):    
    def __init__(self, params):
        super().__init__(params)
        # 例如：params.hidden_size = 512
        # 普通语言模型会把每个 token 的 512 维隐藏状态映射到整个词表：
        # 512维隐藏状态 → 词表中每个token的概率
        # Critic 则将其映射成一个数：
        # 512维隐藏状态 → 1个价值分数
        self.value_head = nn.Linear(params.hidden_size, 1)

    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        # input_ids.shape = [2, 10]
        # 表示批次里有 2 个样本，每个样本 10 个 token。若隐藏维度是 512：
        # outputs[0].shape == [2, 10, 512]
        # 然后进行归一化：
        # hidden_states = self.model.norm(outputs[0])
        # 形状仍然是：[2, 10, 512]
        # 价值头对每个 token 分别计算一个标量：
        # values.shape == [2, 10, 1]
        # values = values.squeeze(-1)
        # 删除最后一个大小为 1 的维度：
        # values.shape == [2, 10]
        outputs = self.model(input_ids=input_ids, attention_mask=attention_mask, **kwargs)
        hidden_states = self.model.norm(outputs[0])
        values = self.value_head(hidden_states).squeeze(-1)
        return values


# 回答打分器。它给每条模型回答计算一个总奖励，
# PPO再根据奖励调整模型：高分回答的生成概率提高，低分回答的生成概率降低。
# 总奖励
# = 长度奖励
# + thinking 格式奖励
# - 重复惩罚
# + 奖励模型评分
# 例子:
# 假设prompt=
# <|im_start|>system
# 你是一个AI助手。<|im_end|>
# <|im_start|>user
# 2+3等于多少？<|im_end|>
# <|im_start|>assistant
# messages = [
#     {"role": "system", "content": "你是一个AI助手。"},
#     {"role": "user", "content": "2+3等于多少？"}
# ]
# 1、长度奖励检查的是整个 response 的字符数：
# rewards[i] += 0.5 if 20 <= len(response.strip()) <= 800 else -0.5
# 例如回答有 100 个字符：
# 长度奖励 = +0.5
# 只有 10 个字符或超过 800 个字符：
# 长度奖励 = -0.5
# 2、思考内容奖励检查的是 response 中是否包含 '</think>' 标签：
# 如果思考部分长度在 20～300 字符：思考长度奖励 = +1.0否则-0.5
# 3、重复惩罚为 0.2：
# 4、调用奖励模型评分

# 最终返回一个 [B] 张量：如:
# tensor([2.95, -0.80])
# 其中每个数字对应一条回答。
def calculate_rewards(prompts, responses, reward_model):
    # 给每条模型回答打“总奖励分”，供 PPO / GRPO 等强化学习训练使用。
    rewards = torch.zeros(len(responses), device=args.device)#rewards.shape == [回答数量]

    # PyTorch：no_grad 中的运算不建立反向图，用于参考模型/采样以节省显存；不会自动切换 eval 模式。
    with torch.no_grad():
        reward_model_scores = []
        for i, (prompt, response) in enumerate(zip(prompts, responses)):
            pattern = r"<\|im_start\|>(system|user|assistant)\s+(.*?)<\|im_end\|>"
            matches = re.findall(pattern, prompt, re.DOTALL)
            messages = [{"role": role, "content": content.strip()} for role, content in matches]
            answer = response
            # 1、长度奖励
            rewards[i] += 0.5 if 20 <= len(response.strip()) <= 800 else -0.5
            # 2、思考内容奖励
            if '</think>' in response:
                thinking_content, answer_content = response.split('</think>', 1)
                rewards[i] += 1.0 if 20 <= len(thinking_content.strip()) <= 300 else -0.5
                rewards[i] += 0.25 if response.count('</think>') == 1 else -0.25
                answer = answer_content.strip()
            # 3、重复惩罚
            rewards[i] -= rep_penalty(answer)
            # 4、调用奖励模型评分
            score = reward_model.get_score(messages, answer)
            reward_model_scores.append(score)

        reward_model_scores = torch.tensor(reward_model_scores, device=args.device)
        rewards += reward_model_scores

    return rewards

# B = Batch Size，一个批次中的样本数量
# R = Response Length，补齐后的回答 token 长度
# labels [B,S-1]：完整序列的 next-token 目标，用来取实际 token 的 log 概率。
# resp_labels [B,R]：回答 token ID（含回答侧 PAD），用来查找 EOS。
# resp_idx [1,R]：回答内部的列号 0..R-1，可广播到整个 batch。
# logp_pos [B,R]：每个回答 token 在移位后 logits/labels 中对应的预测位置。
# resp_pad_mask [B,R]：回答中的真实 token 为 True，PAD 为 False。
# resp_lengths [B]：每条回答截至首个 EOS（含 EOS）的有效长度。
# valid_resp [B]：每条样本是否至少包含一个真实回答 token。
# eos_mask [B,R]：真实回答位置中哪些 token 是 EOS。
# has_eos [B]：每条回答是否包含 EOS；eos_pos [B] 是首个 EOS 的下标。
# resp_policy_mask [B,R]：Actor 策略损失参与位置；排除 PAD 和首个 EOS 之后的 token。
# resp_value_mask [B,R]：Critic 价值损失参与位置；当前是 resp_policy_mask 的副本。

# Prompt
#   ↓
# Actor 生成回答，并记录生成时的 old_logp
#   ↓
# Reward Model 给整条回答打分
#   ↓
# Critic + GAE 把整条奖励转换为每个 token 的 advantage
#   ↓
# PPO 更新 Actor，Value Loss 更新 Critic

# 对象	作用
# actor_model：当前正在训练的语言模型
# old_resp_logp：Actor 生成这批回答时的概率快照
# ref_model：冻结的 SFT 模型，防止 Actor 偏离太远
# critic_model：预测每个生成位置未来能获得多少奖励
# reward_model：给完整回答打最终质量分

# 1、假设 PAD=0、EOS=2，batch 中有两条长度不同的样本：
# prompt_tokens = [[10, 11, 12], [20, 21]]
# response_tokens = [[51, 52, EOS], [61, 62, 63, 64, EOS]]
# prompt_lens = [3, 2]
# 2、rollout：以下是 SGLang 去掉 prompt 左侧 PAD 后的布局；完整序列和回答在右侧补 PAD。
# gen_out = tensor([
#     [10, 11, 12, 51, 52,  2, 0, 0],
#     [20, 21, 61, 62, 63, 64, 2, 0]
# ])
# completion_ids = tensor([
#     [51, 52,  2,  0,  0],
#     [61, 62, 63, 64,  2]
# ])
# old_resp_logp = tensor([
#     [-1.2, -0.8, -0.3,  0.0,  0.0],
#     [-1.1, -0.9, -0.7, -0.4, -0.2]
# ])
# 3、reward阶段：每条完整回答得到一个总奖励，还不是逐 token 奖励。
# rewards = tensor([2.0, 1.5])
# 4、注意力掩码
# 1：真实 token，模型可以关注
# 0：PAD 补齐位置，模型应该忽略
# gen_out = tensor([
#     [10, 11, 12, 51, 52,  2, 0, 0],
#     [20, 21, 61, 62, 63, 64, 2, 0]
# ])
# full_mask = tensor([
#     [1, 1, 1, 1, 1, 1, 0, 0],
#     [1, 1, 1, 1, 1, 1, 1, 0]
# ])
# 5、对齐回答 token
# （1）labels
# labels = gen_out[:, 1:].clone()
# labels = [
#     [11, 12, 51, 52, EOS, PAD, PAD],
#     [21, 61, 62, 63, 64, EOS, PAD]
# ]
# （2）resp_labels 回答 token ID和resp_idx 回答内部位置
# resp_labels = completion_ids
# resp_labels = [
#     [51, 52, EOS, PAD, PAD],
#     [61, 62, 63, 64, EOS]
# ]
# resp_labels.size(1) == 5
# resp_idx = torch.arange(5).unsqueeze(0)
# resp_idx = [[0, 1, 2, 3, 4]]
# 表示回答内部的第 0、1、2、3、4 个位置。因为形状是 [1,5]，后续可以广播到两条样本。
# （3）logp_pos 回答 token 对应的模型预测位置
# logp_pos = prompt_lens.unsqueeze(1) - 1 + resp_idx
# prompt_lens = [3, 2]
# prompt_lens.unsqueeze(1) = [
#     [3],
#     [2]
# ]
# 广播计算：
# logp_pos = [
#     [3 - 1 + 0, 3 - 1 + 1, ..., 3 - 1 + 4],
#     [2 - 1 + 0, 2 - 1 + 1, ..., 2 - 1 + 4]
# ]

# logp_pos = [
#     [2, 3, 4, 5, 6],
#     [1, 2, 3, 4, 5]
# ]
# （4）排除回答中的 PAD
# resp_pad_mask = rollout_result.completion_mask.to(args.device).bool()
# resp_pad_mask = [
#     [True, True, True, False, False],
#     [True, True, True, True,  True]
# ]
# True：真实回答 token
# False：补齐的 PAD
# （5）计算非 PAD 长度
# resp_lengths = [3, 5]
# valid_resp   = [True, True] valid_resp 表示每条样本是否至少生成了一个有效 token，主要用于防止给空回答错误地放置奖励。
# （6）找到第一个 EOS
# has_eos = [True, True]
# eos_pos = [2, 4]
# （7）构造最终 PPO mask
# resp_policy_mask = [
#     [1, 1, 1, 0, 0],
#     [1, 1, 1, 1, 1]
# ]
# 6、advantage阶段
# （1）critic模型计算values
# + 把整条回答的奖励放到最后一个有效 token
# + 用 GAE 从后向前计算 advantage 和 return
# B = 2
# R = 5
# rewards = [2.0, 1.5]

# S=8（完整序列长度）
# gen_out = [
#     [10, 11, 12, 51, 52, EOS, PAD, PAD],
#     [20, 21, 61, 62, 63, 64, EOS, PAD]
# ]
# resp_value_mask = [
#     [1, 1, 1, 0, 0],
#     [1, 1, 1, 1, 1]
# ]
# values_seq.shape == [2, 8]
# 假设 Critic 的预测结果是：
# values_seq = [
#     [0.05, 0.10, 0.20, 0.40, 0.30, 0.25, 0.15, 0.00],
#     [0.04, 0.10, 0.20, 0.35, 0.45, 0.50, 0.55, 0.00]
# ]
# values_seq[0].gather([2, 3, 4, 5, 6])
# 取出：
# [0.20, 0.40, 0.30, 0.25, 0.15]
# 再乘：
# resp_value_mask[0] = [1, 1, 1, 0, 0]
# old_resp_values[0] = [
#     0.20 * 1,
#     0.40 * 1,
#     0.30 * 1,
#     0.25 * 0,
#     0.15 * 0
# ]
# Critic 为完整序列的每个位置预测一个价值。
# old_resp_values = [
#     [0.20, 0.40, 0.30, 0.00, 0.00],
#     [0.10, 0.20, 0.35, 0.45, 0.50]
# ]
# （2）计算参考模型的 token 概率
# ref_logits = ref_model(
#     input_ids=gen_out,
#     attention_mask=full_mask
# ).logits[:, :-1]
# ref_logits.shape == [B, S-1, vocab_size]；每个 [b,t,:] 是对整个词表的原始分数。
# 先用一个 vocab_size=5 的位置完整展示 log_softmax：
# one_ref_logits = [1.0, 2.0, 0.0, 3.0, -1.0]
# logsumexp(one_ref_logits) ≈ 3.452
# one_all_ref_logp = one_ref_logits - 3.452
#                    ≈ [-2.452, -1.452, -3.452, -0.452, -4.452]
# 对应概率约为 [0.086, 0.234, 0.032, 0.636, 0.012]，总和为 1。
# 若这个位置的 label=3，gather 就选择词表下标 3 的 -0.452。
# 对完整 batch 沿最后一个“词表维”做同样转换：
# all_ref_logp = F.log_softmax(ref_logits, dim=-1)
# all_ref_logp.shape == [B, S-1, vocab_size]
# 为使当前两条样本也有可复算的数字，假设 vocab_size=100，并假设每个 labels token 的概率为：
# selected_ref_prob = [
#     [0.60, 0.50, 0.40, 0.30, 0.20, 0.10, 0.05],
#     [0.55, 0.45, 0.35, 0.25, 0.20, 0.15, 0.05]
# ]
# 可以构造一组具体 ref_logits：目标 token 的 logit=ln(p)，其余 99 个 token 的
# logit=ln((1-p)/99)。这样 exp 后总和恰好为 p+99*((1-p)/99)=1，
# 所以 log_softmax 后的 all_ref_logp 与这组 ref_logits 数值相同。
# 例如 [样本0,位置2] 的 label=51、p=0.40：
# ref_logits[0,2,51] = ln(0.40) ≈ -0.916
# ref_logits[0,2,k]  = ln(0.60/99) ≈ -5.106（所有 k != 51）
# all_ref_logp[0,2,51] ≈ -0.916，其余 99 项均约为 -5.106。
# labels.shape == [2,7]，增加一个末维后才能作为词表轴的 gather 索引：
# labels.unsqueeze(-1) = [
#     [[11], [12], [51], [52], [2], [0], [0]],
#     [[21], [61], [62], [63], [64], [2], [0]]
# ]  # shape=[2,7,1]
# gather(dim=2, ...) 对每个 [b,t] 都执行：
# selected_ref_logp[b,t,0] = all_ref_logp[b,t,labels[b,t]]
# 因此它从每个长度为 100 的词表向量中只取 labels 指定的那一项：
# selected_ref_logp = all_ref_logp.gather(2, labels.unsqueeze(-1)).squeeze(-1)
# gather 后先得到 [2,7,1]；squeeze(-1) 只删除末尾大小为 1 的维度，得到 [2,7]。
# selected_ref_logp = log(selected_ref_prob) ≈ [
#     [-0.511, -0.693, -0.916, -1.204, -1.609, -2.303, -2.996],
#     [-0.598, -0.799, -1.050, -1.386, -1.609, -1.897, -2.996]
# ]
# ref_resp_logp = selected_ref_logp.gather(1, logp_pos)
# ref_resp_logp.shape == [B, R]  # [2,5]
# 按 logp_pos=[[2,3,4,5,6],[1,2,3,4,5]] 取回答位置：
# ref_resp_logp ≈ [
#     [-0.916, -1.204, -1.609, -2.303, -2.996],
#     [-0.799, -1.050, -1.386, -1.609, -1.897]
# ]
# 第 1 条最后两个数对应 PAD，后续乘 resp_policy_mask 时会被忽略。
# （3）计算优势函数和回报
# 先创建全零的逐 token 奖励：
# token_rewards = [
#     [0, 0, 0, 0, 0],
#     [0, 0, 0, 0, 0]
# ]
# 回答长度为：
# resp_lengths = [3, 5]
# 因此最后一个有效位置是：
# last_idx = resp_lengths - 1
#          = [2, 4]
# 这段高级索引：
# token_rewards[
#     torch.arange(B)[valid_resp],
#     last_idx[valid_resp]
# ] += rewards[valid_resp]
# 等价于：
# token_rewards[0, 2] += 2.0
# token_rewards[1, 4] += 1.5
# 所以：
# token_rewards = [
#     [0, 0, 2.0, 0, 0],
#     [0, 0, 0, 0, 1.5]
# ]
# 奖励模型只给完整回答一个分数，因此先把这个分数放在最后一个有效 token，再由 GAE 向前传播。
# (4)GAE 从后向前传播奖励
# gen_len = old_resp_values.size(1)  # 5
# lastgaelam = torch.zeros(B)        # [0, 0]
# advs_rev = []
# 公式是：
# δₜ = rₜ + γVₜ₊₁ - Vₜ
# Aₜ = δₜ + γλAₜ₊₁
# 默认：
# gamma = 1.0
# lam = 0.95
# 以第一条回答为例：
# rewards = [0, 0, 2.0, 0, 0]
# values  = [0.2, 0.4, 0.3, 0, 0]
# 从后向前计算：
# t=4：A₄ = 0
# t=3：A₃ = 0
# t=2：δ₂ = 2.0 - 0.3 = 1.7
#      A₂ = 1.7

# t=1：δ₁ = 0.3 - 0.4 = -0.1
#      A₁ = -0.1 + 0.95×1.7 = 1.515

# t=0：δ₀ = 0.4 - 0.2 = 0.2
#      A₀ = 0.2 + 0.95×1.515 = 1.63925
# 得到：
# advantages[0] = [1.63925, 1.515, 1.7, 0, 0]
# 这就是最终奖励从最后一个 token 向前传播的过程。
# 因为循环是倒序追加：
# advs_rev = [A4, A3, A2, A1, A0]
# 所以最后要反转：
# advantages = torch.stack(advs_rev[::-1], dim=1)
# 恢复为：
# [A0, A1, A2, A3, A4]
# 计算 Critic 的目标值
# returns = advantages + old_resp_values
# 第一条样本：
# returns[0] = [
#     1.63925 + 0.20,
#     1.515   + 0.40,
#     1.7     + 0.30,
#     0,
#     0
# ]

# returns[0] = [1.83925, 1.915, 2.0, 0, 0]
# 两者用途不同：
# advantages：Actor 的学习信号
# returns：Critic 应该逼近的目标值
# (6). 标准化 advantage
# 先只用有效位置计算均值：
# adv_mean = (
#     advantages * resp_policy_mask
# ).sum() / resp_policy_mask.sum()
# 再计算方差：
# adv_var = (
#     (advantages - adv_mean) ** 2
#     * resp_policy_mask
# ).sum() / resp_policy_mask.sum()
# 最后标准化：
# advantages = (
#     (advantages - adv_mean)
#     / sqrt(adv_var + 1e-8)
#     * resp_policy_mask
# )
# 代码用：
# torch.rsqrt(adv_var + 1e-8)
# 等价于：
# 1 / torch.sqrt(adv_var + 1e-8)
# 标准化后：
# - 高于 batch 平均水平的 token，advantage 为正。
# - 低于 batch 平均水平的 token，advantage 为负。
# - PAD 和 EOS 后的位置乘 mask 后变成 0。
# - returns 不标准化，仍作为 Critic 的原始训练目标。
# 7、update
# 变量	含义	是否更新
# old_resp_logp	rollout 生成回答时的 Actor 概率快照	固定
# mb_resp_logp	当前 Actor 重新计算的概率	有梯度
# ref_resp_logp	冻结 SFT 参考模型的概率	固定
# (1) Mini-batch 和重复更新
# B = 2
# args.mini_batch_size = 1
# mb_size = 1
# b_inds = [1, 0]  # 假设随机结果
# 循环会依次训练样本 1 和样本 0。ppo_update_iters=2 表示同一批回答最多重复训练两轮，每轮重新打乱。
# M：当前 mini-batch 样本数
# S：完整序列宽度
# R：回答宽度
# V：词表大小

# mb_values_seq   [M,S]
# mb_resp_values  [M,R]
# res.logits       [M,S,V]
# mb_resp_logp     [M,R]
# log_ratio        [M,R]
# ratio            [M,R]
# （2）重新计算当前 Actor 的回答概率
#  mb_resp_logp = F.log_softmax(res.logits[:, :-1], dim=-1)
# .gather(2, labels[inds].unsqueeze(-1))
# .squeeze(-1).gather(1, logp_pos[inds])
# 这行连续完成四步。假设当前 mini-batch 只有第 1 条样本：
# gen_out[0]      = [10, 11, 12, 51, 52, EOS, PAD, PAD]
# labels[0]       = [11, 12, 51, 52, EOS, PAD, PAD]
# logp_pos[0]     = [2, 3, 4, 5, 6]
#
# 第一步：res.logits[:, :-1]
# 假设 res.logits.shape=[1,8,100]，分别表示 M=1、S=8、V=100。
# 去掉最后一个没有 next-token 目标的位置后，形状变为 [1,7,100]。
# 对齐关系为：logits 位置 0..6 分别预测 labels 中的
# [11, 12, 51, 52, EOS, PAD, PAD]。
#
# 第二步：F.log_softmax(..., dim=-1)
# 在每个位置的 100 个词表分数上计算 log 概率，形状仍为 [1,7,100]。
# 用 vocab_size=5 的单个位置演示：
# logits = [1.0, 2.0, 0.0, 3.0, -1.0]
# log_softmax(logits) ≈ [-2.452, -1.452, -3.452, -0.452, -4.452]
# 对应概率约为 [0.086, 0.234, 0.032, 0.636, 0.012]。
#
# 第三步：gather(2, labels[inds].unsqueeze(-1)).squeeze(-1)
# labels[inds].shape=[1,7]，unsqueeze(-1) 后为：
# [[[11], [12], [51], [52], [2], [0], [0]]]  # shape=[1,7,1]
# gather(dim=2) 把这些 token ID 当作词表下标，对每个位置执行：
# target_logp[0,t,0] = all_logp[0,t,labels[0,t]]
# 假设取出的实际 next-token logp 为：
# [[[-0.40],[-0.65],[-0.90],[-1.10],[-1.50],[-2.00],[-2.50]]]
# gather 后形状为 [1,7,1]；squeeze(-1) 删除末尾单维，得到：
# full_target_logp = [[-0.40,-0.65,-0.90,-1.10,-1.50,-2.00,-2.50]]  # [1,7]
#
# 第四步：gather(1, logp_pos[inds])
# logp_pos[inds]=[[2,3,4,5,6]]，沿序列维只取回答对应的位置：
# mb_resp_logp = [[-0.90,-1.10,-1.50,-2.00,-2.50]]  # [M,R]=[1,5]
# 对应 token 是 [51,52,EOS,PAD,PAD]；后续 resp_policy_mask=[1,1,1,0,0]
# 会排除最后两个 PAD，真正参与 PPO loss 的是 [-0.90,-1.10,-1.50]。
# 它们对应的当前 Actor 概率约为：
# exp(-0.90)=0.407，exp(-1.10)=0.333，exp(-1.50)=0.223。
# mb_resp_logp 保留梯度，PPO loss 会通过它反向更新 Actor。

# （3）概率比和 PPO 裁剪
# 假设一个 token：
# old_logp = -1.2
# new_logp = -1.0
# 那么：
# log_ratio = -1.0 - (-1.2)
#           = 0.2

# ratio = exp(0.2)
#       ≈ 1.221
# 表示当前 Actor 给这个 token 的概率是旧 Actor 的 1.221 倍。
# advantage = 0.8
# clip_epsilon = 0.2
# 未裁剪收益：
# 0.8 * 1.221 = 0.977
# 裁剪后：
# 0.8 * 1.2 = 0.960
# PPO 采用较保守的 0.960，防止一次把概率提高太多。代码写成：
# max(-原收益, -裁剪收益)
# 是因为优化器在最小化 loss，数学上等价于最大化：
# min(原收益, 裁剪收益)
# （4）算kl,如果超过阈值就停止训练
# 旧策略 KL：
# approx_kl = 0.5 * log_ratio**2
#           = 0.5 * 0.2**2
#           = 0.02
# 它衡量当前 Actor 离本次 rollout 的旧 Actor 多远，只用于监控和提前停止。
# （5）参考模型 KL，假设：
# ref_logp = -1.1
# new_logp = -1.0
# d = ref_logp - new_logp = -0.1
# 则：
# exp(d) - d - 1
# = exp(-0.1) + 0.1 - 1
# ≈ 0.00484
# 它限制 Actor 偏离冻结 SFT 模型，并实际加入 policy_loss。
# clipfrac 则统计多少有效 token 的 ratio 超过 [0.8, 1.2]。上面的 1.221 已经超出，所以这个 token 会计入。
# 5. Critic 的 Value clipping
# 假设：
# old_value = 0.3
# new_value = 0.9
# return     = 1.0
# cliprange_value = 0.2
# 新值最多允许从 0.3 移到：
# clipped_value = 0.5
# 两个误差：
# 未裁剪误差 = (0.9 - 1.0)**2 = 0.01
# 裁剪误差   = (0.5 - 1.0)**2 = 0.25
# 代码取较大值：
# value_loss = 0.5 * 0.25 = 0.125
# 这样 Critic 不能靠一次大幅跳动轻易降低 loss。
# 最终损失：
# loss = (
#     policy_loss
#     + args.vf_coef * value_loss
#     + aux_loss
# ) / args.accumulation_steps
def ppo_train_epoch(epoch, loader, iters, rollout_engine, ref_model, actor_scheduler, critic_scheduler, reward_model, start_step=0, wandb=None):
    actor_model.train()
    critic_model.train()
    grad_accum_step = 0

    for step, batch in enumerate(loader, start=start_step + 1):
        # ================1、编码======================
        prompts = batch["prompt"]  # list[str], length B
        enc = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=args.max_seq_len,
                        padding_side="left").to(args.device)  # input_ids: [B, P], attention_mask: [B, P]
        # =================2、rollout:生成回答：=============
        rollout_result = rollout_engine.rollout(
            prompt_ids=enc.input_ids,
            attention_mask=enc.attention_mask,
            num_generations=1,
            max_new_tokens=args.max_gen_len,
            temperature=0.8,
        )
        gen_out = rollout_result.output_ids# prompt + response 的完整 token
        completion_ids = rollout_result.completion_ids# 只包含 response 的 token
        prompt_lens = rollout_result.prompt_lens.to(args.device)# 每条样本的提示 token 长度 [B]
        responses_text = rollout_result.completions # 解码后的回答文本列表
        old_resp_logp = rollout_result.per_token_logps.to(args.device)
        # =================3、reward阶段：对回答打奖励分==============
        rewards = calculate_rewards(prompts, responses_text, reward_model)  # [B]

        if args.debug_mode and is_main_process() and step % args.debug_interval == 0:
            for i in range(len(prompts)):
                Logger(f"[DEBUG] step={step}, sample[{i}]")
                Logger('-'*100)
                Logger(f"{'=' * 30} [DEBUG] sample[{i}] CONTEXT_BEGIN {'=' * 30}")
                Logger(prompts[i])
                Logger(f"{'=' * 31} [DEBUG] sample[{i}] CONTEXT_END {'=' * 31}")
                Logger(f"[DEBUG] prompt_len={prompt_lens[i].item()}, response_len={len(responses_text[i])}")
                Logger(f"{'=' * 28} [DEBUG] sample[{i}] RESPONSE_BEGIN {'=' * 28}")
                Logger(responses_text[i])
                Logger(f"{'=' * 29} [DEBUG] sample[{i}] RESPONSE_END {'=' * 29}")
                Logger(f"[DEBUG] reward={rewards[i].item():.4f}")
                Logger('='*100)
        # =================4、注意力掩码======================
        full_mask = (gen_out != tokenizer.pad_token_id).long()  # [B, P+R] .long() 是 PyTorch 张量的类型转换，表示转成 torch.int64（64 位整数）。
        # =================5、对齐回答 token================
        labels = gen_out[:, 1:].clone()  # [B, P+R-1] 语言模型预测“下一个 token”，所以标签要向左移动一格。
        B = len(prompts)#当前 batch 中有多少条 prompt。
        resp_labels = completion_ids#completion_ids 只包含模型生成的回答部分，不含 prompt。
        resp_idx = torch.arange(resp_labels.size(1), device=gen_out.device).unsqueeze(0)#创建回答内部的位置编号。
        # 目标 token 在 prompt_len+j 位置，其预测来自 prompt_len+j-1；按每条提示长度构造索引。
        logp_pos = prompt_lens.unsqueeze(1) - 1 + resp_idx
        # prompt_lens = [3, 2]
        # resp_idx = [[0, 1, 2, 3, 4]]
        # logp_pos = [[2, 3, 4, 5, 6], [1, 2, 3, 4, 5]]
        # 第 1 条在 labels 的位置 [2,3,4,5,6] 取出 [51,52,EOS,PAD,PAD]。
        # 第 2 条在 labels 的位置 [1,2,3,4,5] 取出 [61,62,63,64,EOS]。
        resp_pad_mask = rollout_result.completion_mask.to(args.device).bool()#这是回答的 PAD 掩码。
        # 第 1 条： [51, 52, EOS, PAD, PAD]
        # 第 2 条： [61, 62, 63, 64, EOS]
        # resp_pad_mask = [
        #     [True, True, True, False, False],
        #     [True, True, True, True, True]
        # ]
        resp_lengths = resp_pad_mask.sum(dim=1); valid_resp = resp_lengths > 0; eos_mask = resp_labels.eq(tokenizer.eos_token_id) & resp_pad_mask
        # 计算每条回答未补齐前的真实长度。resp_lengths = [3, 5]
        has_eos = eos_mask.any(dim=1); eos_pos = torch.argmax(eos_mask.int(), dim=1)
        # 每条回答是否出现 EOS
        resp_lengths = torch.where(has_eos, eos_pos + 1, resp_lengths).long().clamp(min=1)
        # 如果找到 EOS，就把真实回答长度截断到 EOS 为止，并且包含 EOS 本身。如果没有 EOS，则保持原本的非 PAD 长度。
        resp_policy_mask = ((resp_idx < resp_lengths.unsqueeze(1)) & resp_pad_mask).float()
        # 这是 PPO 的最终回答掩码。
        # resp_policy_mask = [
        #     [1, 1, 1, 0, 0],
        #     [1, 1, 1, 1, 1]
        # ]
        resp_value_mask = resp_policy_mask.clone()#当前代码让 Critic 的价值损失和 Actor 的策略损失使用相同 mask。
        # =================6、advantage 阶段======================
        with torch.no_grad():  # Rollout阶段只需推理获取old_logp和old_values，切断梯度省显存
            # （1）critic模型计算values
            critic_for_rollout = critic_model.module if isinstance(critic_model, DistributedDataParallel) else critic_model
            values_seq = critic_for_rollout(input_ids=gen_out, attention_mask=full_mask)#Critic 为完整序列预测价值
            # PyTorch：gather(dim,index) 沿指定轴按整型索引取值，输出形状与 index 一致；可用于选择词表项或序列位置。
            old_resp_values = values_seq.gather(1, logp_pos) * resp_value_mask#只取回答 token 的价值
            # （2）计算参考模型的 token 概率
            ref_resp_logp = F.log_softmax(ref_model(input_ids=gen_out, attention_mask=full_mask).logits[:, :-1], dim=-1).gather(2, labels.unsqueeze(-1)).squeeze(-1).gather(1, logp_pos)
            # （3）计算优势函数和回报
            token_rewards = torch.zeros_like(old_resp_logp)
            last_idx = resp_lengths - 1  # [B]
            # 把序列级外部奖励放到最后一个有效回答 token，后续 GAE 再将信号向前传播。
            token_rewards[torch.arange(B, device=args.device)[valid_resp], last_idx[valid_resp]] += rewards[valid_resp]  # 末尾加外部奖励

            gen_len = old_resp_values.size(1); lastgaelam = torch.zeros(B, device=args.device); advs_rev = []
            # GAE 从后向前递推：delta=r+gamma*V_next-V；优势=delta+gamma*lambda*后续优势。
            for t in reversed(range(gen_len)):
                nv = old_resp_values[:, t + 1] if t < gen_len - 1 else 0.0#下一个 token 位置的旧价值预测
                delta = token_rewards[:, t] + args.gamma * nv - old_resp_values[:, t]
                lastgaelam = delta + args.gamma * args.lam * lastgaelam
                advs_rev.append(lastgaelam)
            advantages = torch.stack(advs_rev[::-1], dim=1)  # [B, R] 把倒序算出的每个 token advantage 重新排回正常顺序
            returns = advantages + old_resp_values  # [B, R]#得到 Critic 应该学习的目标值 returns

            adv_mean = (advantages * resp_policy_mask).sum() / resp_policy_mask.sum().clamp(min=1)
            adv_var = ((advantages - adv_mean) ** 2 * resp_policy_mask).sum() / resp_policy_mask.sum().clamp(min=1)
            # PyTorch：rsqrt(x)=1/sqrt(x)；在均方值后加 eps，避免分母为 0 并改善数值稳定性。
            advantages = (advantages - adv_mean) * torch.rsqrt(adv_var + 1e-8) * resp_policy_mask
        # =================7、update阶段：用同一批已生成回答，反复训练 Actor 和 Critic 几轮，但限制每次更新不能变化太大。===========
        mb_size = max(1, min(args.mini_batch_size, B))#设置 mini-batch 大小
        stop_ppo = False
        policy_loss_sum = 0.0
        value_loss_sum = 0.0
        kl_sum = 0.0
        kl_ref_sum = 0.0
        clipfrac_sum = 0.0
        aux_loss_sum = 0.0
        log_count = 0
        actor_unwrapped = actor_model.module if isinstance(actor_model, DistributedDataParallel) else actor_model
        critic_unwrapped = critic_model.module if isinstance(critic_model, DistributedDataParallel) else critic_model
        for ppo_epoch in range(args.ppo_update_iters):
            # 达到早停条件后退出后续更新轮；当前批仍按下方分支构造零损失反向路径。
            if stop_ppo:
                break
            # PyTorch：randperm(n) 产生 0..n-1 的随机无重复排列，常用于打乱样本或 mini-batch 顺序。
            b_inds = torch.randperm(B, device=args.device)#随机打乱 batch 样本顺序。
            for i in range(0, B, mb_size):#将打乱后的数据切成 mini-batch。
                inds = b_inds[i:i + mb_size]
                # （1）重新计算当前 Critic 的价值
                mb_values_seq = critic_unwrapped(input_ids=gen_out[inds], attention_mask=full_mask[inds])
                mb_resp_values = mb_values_seq.gather(1, logp_pos[inds])
                # （2）重新计算当前 Actor 的回答概率
                with autocast_ctx:
                    # inds 选择当前 mini-batch；若 M=len(inds)，则输入形状为 [M,S]。
                    res = actor_unwrapped(input_ids=gen_out[inds], attention_mask=full_mask[inds])
                    # res.logits: [M,S,V]，每个序列位置都有 V 个词表原始分数。
                    # MoE 使用 aux_loss 平衡专家负载；普通稠密模型没有该项，取设备上的标量 0。
                    aux_loss = res.aux_loss if lm_config.use_moe else torch.tensor(0.0, device=args.device)
                    mb_resp_logp = F.log_softmax(res.logits[:, :-1], dim=-1).gather(2, labels[inds].unsqueeze(-1)).squeeze(-1).gather(1, logp_pos[inds])
                # （3）新旧 Actor 的概率变化
                log_ratio = mb_resp_logp - old_resp_logp[inds]

                # 可开关的诊断：观察首轮首个 minibatch 的 mb 与 old logp 差异。
                if args.debug_log_ratio and ppo_epoch == 0 and i == 0 and is_main_process():
                    # PyTorch：detach 切断此张量的梯度历史，但仍可能共享存储；需要独立副本时再 clone()。
                    _lr = log_ratio.detach()
                    _m = resp_policy_mask[inds].bool()
                    if _m.any():
                        _lrv = _lr[_m]
                        Logger(f"[DBG log_ratio] step={step} max|lr|={_lrv.abs().max().item():.6e} "
                               f"mean|lr|={_lrv.abs().mean().item():.6e} "
                               f"ratio_max={torch.exp(_lrv).max().item():.6f} "
                               f"ratio_min={torch.exp(_lrv).min().item():.6f} "
                               f"dropout={getattr(lm_config, 'dropout', None)} "
                               f"training={actor_unwrapped.training}")
                #（4）算kl,如果超过阈值就停止训练
                approx_kl = (0.5 * (log_ratio ** 2) * resp_policy_mask[inds]).sum() / resp_policy_mask[inds].sum().clamp(min=1)
                
                # 同步各卡的 approx_kl，防止某卡 break 而其它卡继续导致 DDP 死锁
                approx_kl_val = approx_kl.detach().clone()
                if dist.is_initialized():
                    # PyTorch：all_reduce 原地归约所有进程的张量；各 rank 必须按一致顺序调用相同集合通信。
                    dist.all_reduce(approx_kl_val, op=dist.ReduceOp.AVG)
                    
                if approx_kl_val > args.early_stop_kl:
                    stop_ppo = True
                #（5）计算clipfrac、kl和loss
                # exp(logπ_new−logπ_old) 得到新旧动作概率比，用于 PPO 重要性加权。
                ratio = torch.exp(log_ratio)
                clipfrac = ((((ratio - 1.0).abs() > args.clip_epsilon).float() * resp_policy_mask[inds]).sum()
                            / resp_policy_mask[inds].sum().clamp(min=1))
                kl_ref_penalty = ((torch.exp(ref_resp_logp[inds] - mb_resp_logp) - (ref_resp_logp[inds] - mb_resp_logp) - 1.0)
                                  * resp_policy_mask[inds]).sum() / resp_policy_mask[inds].sum().clamp(min=1)
                # 最小化负收益，因此使用 max(负的原目标,负的裁剪目标)，等价于最大化 PPO 的 min 目标。
                policy_loss = ((torch.max(-advantages[inds] * ratio,
                                          -advantages[inds] * torch.clamp(ratio, 1.0 - args.clip_epsilon, 1.0 + args.clip_epsilon))
                               * resp_policy_mask[inds]).sum() / resp_policy_mask[inds].sum().clamp(min=1)
                               + args.kl_coef * kl_ref_penalty)
                # 比较原价值预测与相对旧预测裁剪后的误差，取较大者，限制 Critic 单次改动。
                value_loss = 0.5 * (torch.max((mb_resp_values - returns[inds]) ** 2,
                                              (torch.clamp(mb_resp_values, old_resp_values[inds] - args.cliprange_value,
                                                           old_resp_values[inds] + args.cliprange_value) - returns[inds]) ** 2)
                                    * resp_value_mask[inds]).sum() / resp_value_mask[inds].sum().clamp(min=1)

                kl = approx_kl_val
                kl_ref = kl_ref_penalty.detach()

                # 早停时必须保证 forward-backward 闭环，故只截断 loss 不中断 DDP 通信
                if stop_ppo:
                    # 乘 0 保留计算图路径但使其梯度贡献为 0，配合原有更新控制流程。
                    loss = (policy_loss + args.vf_coef * value_loss + aux_loss) * 0.0
                else:
                    loss = (policy_loss + args.vf_coef * value_loss + aux_loss) / args.accumulation_steps
                
                loss.backward()

                policy_loss_sum += policy_loss.item()
                value_loss_sum += value_loss.item()
                kl_sum += kl.item()
                kl_ref_sum += kl_ref.item()
                clipfrac_sum += clipfrac.item()
                aux_loss_sum += aux_loss.item()
                log_count += 1

                grad_accum_step += 1

                if grad_accum_step % args.accumulation_steps == 0:
                    # PyTorch：clip_grad_norm_ 按参数梯度的整体范数原地缩放，限制过大的更新；返回裁剪前范数。
                    clip_grad_norm_(actor_model.parameters(), args.grad_clip)
                    clip_grad_norm_(critic_model.parameters(), args.grad_clip)
                    actor_optimizer.step()
                    critic_optimizer.step()
                    actor_scheduler.step()
                    critic_scheduler.step()
                    actor_optimizer.zero_grad()
                    critic_optimizer.zero_grad()

        if grad_accum_step % args.accumulation_steps != 0:
            clip_grad_norm_(actor_model.parameters(), args.grad_clip)
            clip_grad_norm_(critic_model.parameters(), args.grad_clip)
            actor_optimizer.step()
            critic_optimizer.step()
            actor_scheduler.step()
            critic_scheduler.step()
            actor_optimizer.zero_grad()
            critic_optimizer.zero_grad()
        
        if step % args.save_interval == 0 or step == iters: rollout_engine.update_policy(actor_model)

        if is_main_process():
            critic_loss_val = value_loss_sum / max(log_count, 1)
            reward_val = rewards.mean().item()
            approx_kl_val = kl_sum / max(log_count, 1)
            kl_ref_val = kl_ref_sum / max(log_count, 1)
            clipfrac_val = clipfrac_sum / max(log_count, 1)
            avg_len_val = resp_lengths.float().mean().item()
            actor_lr, critic_lr = actor_optimizer.param_groups[0]['lr'], critic_optimizer.param_groups[0]['lr']

            if wandb is not None:
                wandb.log({
                    "reward": reward_val,
                    "kl_ref": kl_ref_val,
                    "approx_kl": approx_kl_val,
                    "clipfrac": clipfrac_val,
                    "critic_loss": critic_loss_val,
                    "avg_response_len": avg_len_val,
                    "actor_lr": actor_lr,
                    "critic_lr": critic_lr,
                })

            Logger(f"Epoch:[{epoch + 1}/{args.epochs}]({step}/{iters}), "
                   f"Reward: {reward_val:.4f}, KL_ref: {kl_ref_val:.4f}, Approx KL: {approx_kl_val:.4f}, "
                   f"ClipFrac: {clipfrac_val:.4f}, Critic Loss: {critic_loss_val:.4f}, "
                   f"Avg Response Len: {avg_len_val:.2f}, Actor LR: {actor_lr:.8f}, Critic LR: {critic_lr:.8f}")

        if (step % args.save_interval == 0 or step == iters) and is_main_process():
            actor_model.eval()
            moe_suffix = '_moe' if lm_config.use_moe else ''
            ckp = f'{args.save_dir}/{args.save_weight}_{lm_config.hidden_size}{moe_suffix}.pth'
            raw_actor = actor_model.module if isinstance(actor_model, DistributedDataParallel) else actor_model
            raw_actor = getattr(raw_actor, '_orig_mod', raw_actor)
            actor_state = raw_actor.state_dict()
            # PyTorch：save 将对象序列化；这里保存 state_dict 等状态，恢复时仍需用匹配的模型配置构建网络。
            torch.save({k: v.half().cpu() for k, v in actor_state.items()}, ckp)
            
            # 使用 lm_checkpoint 保存完整状态（包括 critic）
            lm_checkpoint(lm_config, weight=args.save_weight, model=actor_model, optimizer=actor_optimizer, 
                         epoch=epoch, step=step, wandb=wandb, save_dir='../checkpoints',
                         scheduler=actor_scheduler, critic_model=critic_model, 
                         critic_optimizer=critic_optimizer, critic_scheduler=critic_scheduler)
            actor_model.train()
            del actor_state

        del enc, gen_out, completion_ids, responses_text, rewards, full_mask, values_seq, advantages
        del labels, resp_labels, resp_idx, resp_pad_mask, valid_resp, eos_mask, has_eos, eos_pos, resp_lengths, resp_policy_mask, resp_value_mask, old_resp_logp, ref_resp_logp
        del kl, kl_ref, policy_loss, value_loss, loss, token_rewards, returns, old_resp_values, prompt_lens, logp_pos


if __name__ == "__main__":
    # 命令行参数集中定义训练/推理的路径、模型规模和运行选项，下方 parse_args 读取实际值。
    parser = argparse.ArgumentParser(description="MiniMind PPO (Proximal Policy Optimization)")
    parser.add_argument("--save_dir", type=str, default="../out", help="模型保存目录")
    parser.add_argument('--save_weight', default='ppo_actor', type=str, help="保存权重的前缀名")
    parser.add_argument("--epochs", type=int, default=1, help="训练轮数")
    parser.add_argument("--batch_size", type=int, default=2, help="batch size")
    parser.add_argument("--learning_rate", type=float, default=3e-7, help="Actor学习率")
    parser.add_argument("--critic_learning_rate", type=float, default=5e-7, help="Critic学习率")
    parser.add_argument("--device", type=str, default="cuda:0" if torch.cuda.is_available() else "cpu", help="训练设备")
    parser.add_argument("--dtype", type=str, default="bfloat16", help="混合精度类型")
    parser.add_argument("--num_workers", type=int, default=8, help="数据加载线程数")
    parser.add_argument("--accumulation_steps", type=int, default=1, help="梯度累积步数")
    parser.add_argument("--grad_clip", type=float, default=1.0, help="梯度裁剪阈值")
    parser.add_argument("--log_interval", type=int, default=1, help="日志打印间隔")
    parser.add_argument("--save_interval", type=int, default=10, help="模型保存间隔")
    parser.add_argument('--hidden_size', default=768, type=int, help="隐藏层维度")
    parser.add_argument('--num_hidden_layers', default=8, type=int, help="隐藏层数量")
    parser.add_argument('--use_moe', default=0, type=int, choices=[0, 1], help="是否使用MoE架构（0=否，1=是）")
    parser.add_argument('--max_seq_len', default=768, type=int, help="Prompt最大长度")
    parser.add_argument("--max_gen_len", type=int, default=1024, help="生成的最大长度")
    parser.add_argument("--data_path", type=str, default="../dataset/rlaif.jsonl", help="RLAIF数据路径")
    parser.add_argument("--clip_epsilon", type=float, default=0.2, help="PPO裁剪参数")
    parser.add_argument("--vf_coef", type=float, default=0.5, help="Value function系数")
    parser.add_argument("--kl_coef", type=float, default=0.02, help="KL散度惩罚系数")
    parser.add_argument("--gamma", type=float, default=1.0, help="GAE折扣因子")
    parser.add_argument("--lam", type=float, default=0.95, help="GAE lambda参数")
    parser.add_argument("--cliprange_value", type=float, default=0.2, help="Value function裁剪范围")
    parser.add_argument("--ppo_update_iters", type=int, default=2, help="同一批rollout重复更新次数")
    parser.add_argument("--early_stop_kl", type=float, default=0.25, help="PPO early stop 的 KL 阈值")
    parser.add_argument("--mini_batch_size", type=int, default=2, help="PPO每次更新的minibatch大小")
    parser.add_argument('--from_weight', default='full_sft', type=str, help="基于哪个权重训练")
    parser.add_argument("--reward_model_path", type=str, default="../../internlm2-1_8b-reward", help="Reward模型路径")
    parser.add_argument('--from_resume', default=0, type=int, choices=[0, 1], help="是否自动检测&续训（0=否，1=是）")
    parser.add_argument("--use_wandb", action="store_true", help="是否使用wandb")
    parser.add_argument("--wandb_project", type=str, default="MiniMind-PPO", help="wandb项目名")
    parser.add_argument("--use_compile", default=0, type=int, choices=[0, 1], help="是否使用torch.compile加速（0=否，1=是）")
    parser.add_argument("--debug_mode", action="store_true", help="是否打印训练调试采样")
    parser.add_argument("--debug_interval", type=int, default=20, help="debug模式下每隔多少step打印一次采样")
    parser.add_argument("--debug_log_ratio", action="store_true", help="打印首轮首个minibatch的log_ratio差异量级，用于核查ratio≈1是否成立")
    parser.add_argument("--thinking_ratio", type=float, default=0.9, help="按概率开启thinking（0.0~1.0）")
    parser.add_argument("--rollout_engine", type=str, default="torch", choices=["torch", "sglang"], help="rollout引擎类型")
    parser.add_argument("--sglang_base_url", type=str, default="http://localhost:8998", help="SGLang服务器URL")
    parser.add_argument("--sglang_model_path", type=str, default="../model", help="SGLang tokenizer路径")
    parser.add_argument("--sglang_shared_path", type=str, default="./sglang_ckpt_ppo", help="SGLang共享存储路径")
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
    autocast_ctx = nullcontext() if device_type == "cpu" else torch.cuda.amp.autocast(dtype=dtype)
    
    # ========== 4. 配wandb ==========
    wandb = None
    if args.use_wandb and is_main_process():
        import swanlab as wandb
        wandb_id = ckp_data.get('wandb_id') if ckp_data else None
        resume = 'must' if wandb_id else None
        wandb_run_name = f"MiniMind-PPO-Epoch-{args.epochs}-BS-{args.batch_size}-LR-{args.learning_rate}"
        wandb.init(project=args.wandb_project, name=wandb_run_name, id=wandb_id, resume=resume)
    
    # ========== 5. 初始化模型和数据 ==========
    base_weight = args.from_weight
    # Actor模型
    actor_model, tokenizer = init_model(lm_config, base_weight, device=args.device)
    ref_model, _ = init_model(lm_config, base_weight, device=args.device)
    # PyTorch：requires_grad_(False) 冻结参数梯度；eval() 只改变 Dropout 等层的行为，两者用途不同。
    ref_model = ref_model.eval().requires_grad_(False)
    moe_suffix = '_moe' if lm_config.use_moe else ''
    ckp = f'{args.save_dir}/{base_weight}_{lm_config.hidden_size}{moe_suffix}.pth'
    # PyTorch：load 读取序列化对象；map_location 指定张量加载设备，CPU 加载可避免先占用 GPU 显存。
    state_dict = torch.load(ckp, map_location=args.device)
    critic_model = CriticModel(lm_config)
    # PyTorch：load_state_dict 按参数/缓冲区名字恢复状态；strict=False 允许缺失/额外键，但不忽略同名张量形状不匹配。
    critic_model.load_state_dict(state_dict, strict=False)
    critic_model = critic_model.to(args.device)
    reward_model = LMForRewardModel(args.reward_model_path, device=args.device, dtype=torch.float16)
    # Rollout引擎
    rollout_engine = create_rollout_engine(
        engine_type=args.rollout_engine,
        policy_model=actor_model,
        tokenizer=tokenizer,
        device=args.device,
        autocast_ctx=autocast_ctx,
        sglang_base_url=args.sglang_base_url,
        sglang_model_path=args.sglang_model_path,
        sglang_shared_path=args.sglang_shared_path,
    )
    train_ds = RLAIFDataset(args.data_path, tokenizer, max_length=(args.max_seq_len + args.max_gen_len), thinking_ratio=args.thinking_ratio)
    # PyTorch：DistributedSampler 按 rank 分配样本索引；每轮 set_epoch(epoch) 更新一致的随机排列。
    train_sampler = DistributedSampler(train_ds) if dist.is_initialized() else None
    actor_optimizer = optim.AdamW(actor_model.parameters(), lr=args.learning_rate)
    critic_optimizer = optim.AdamW(critic_model.parameters(), lr=args.critic_learning_rate)
    # PyTorch：DataLoader 从 Dataset 取样并组批；batch_sampler 已决定批次，pin_memory 可使 CPU 数据使用锁页内存。
    loader_for_count = DataLoader(train_ds, batch_size=args.batch_size, sampler=train_sampler)
    iters = len(loader_for_count)
    mb_factor = max(1, math.ceil(args.batch_size / args.mini_batch_size))
    total_optimizer_steps = math.ceil(iters * args.epochs * args.ppo_update_iters * mb_factor / args.accumulation_steps)
    actor_scheduler = CosineAnnealingLR(actor_optimizer, T_max=total_optimizer_steps, eta_min=args.learning_rate / 10)
    critic_scheduler = CosineAnnealingLR(critic_optimizer, T_max=total_optimizer_steps, eta_min=args.critic_learning_rate / 10)

    start_epoch, start_step = 0, 0
    # 恢复模型、优化器等状态及 epoch/step；只加载模型权重不能恢复优化器历史。
    if ckp_data:
        actor_model.load_state_dict(ckp_data['model'])
        critic_model.load_state_dict(ckp_data['critic_model'])
        actor_optimizer.load_state_dict(ckp_data['optimizer'])
        critic_optimizer.load_state_dict(ckp_data['critic_optimizer'])
        actor_scheduler.load_state_dict(ckp_data['scheduler'])
        critic_scheduler.load_state_dict(ckp_data['critic_scheduler'])
        start_epoch = ckp_data['epoch']
        start_step = ckp_data.get('step', 0)
    
    # ========== 7. 编译和分布式包装 ==========
    if args.use_compile == 1:
        # PyTorch：compile 捕获并优化可编译的计算图；首次执行有编译成本，动态 Python 控制流可能导致图中断。
        actor_model = torch.compile(actor_model)
        Logger('torch.compile enabled')
        rollout_engine.update_policy(actor_model)
    if dist.is_initialized():
        # PyTorch DDP：每个进程包装一份模型，在常规 DDP 前向/反向路径中同步梯度；数据切分由 sampler 负责。
        actor_model = DistributedDataParallel(actor_model, device_ids=[local_rank])
        critic_model = DistributedDataParallel(critic_model, device_ids=[local_rank])
    rollout_engine.update_policy(actor_model)
    
    # ========== 8. 开始训练 ==========
    for epoch in range(start_epoch, args.epochs):
        train_sampler and train_sampler.set_epoch(epoch)
        setup_seed(42 + epoch); indices = torch.randperm(len(train_ds)).tolist()
        # skip 以批次计数；SkipBatchSampler 负责跳过索引，start_step 则维持日志和学习率的批次进度。
        skip = start_step if (epoch == start_epoch and start_step > 0) else 0
        batch_sampler = SkipBatchSampler(train_sampler or indices, args.batch_size, skip)
        loader = DataLoader(train_ds, batch_sampler=batch_sampler, num_workers=args.num_workers, pin_memory=True)
        if skip > 0: 
            Logger(f'Epoch [{epoch + 1}/{args.epochs}]: 跳过前{start_step}个step，从step {start_step + 1}开始')
            ppo_train_epoch(epoch, loader, len(loader) + skip, rollout_engine, ref_model, actor_scheduler, critic_scheduler, reward_model, start_step, wandb)
        else:
            ppo_train_epoch(epoch, loader, len(loader), rollout_engine, ref_model, actor_scheduler, critic_scheduler, reward_model, 0, wandb)
    
    # ========== 9. 清理分布进程 ==========
    if dist.is_initialized():
        # PyTorch：barrier 等待所有进程到达同步点；所有 rank 都应参与，不能只在主进程调用。
        dist.barrier()
        # PyTorch：训练结束后销毁通信组，释放分布式后端资源。
        dist.destroy_process_group()
