import os
import sys

__package__ = "trainer"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import datasets
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

'''
【语句示例：warnings.filterwarnings('ignore')】
输入：warnings 当前的警告过滤器。执行后一般警告被忽略，例如某些弃用提示不再显示；异常仍然会抛出，训练错误不会因此自动修复。
'''
warnings.filterwarnings('ignore')


# 统计重复 n-gram 占比并限制最大扣分，降低重复生成获得的奖励。
'''
注意这里和model.generate中的重复惩罚不同：generate中是直接在采样时对重复的token进行惩罚，用的是
【rep_penalty 函数：输入文本 → 重复 n-gram 比例 → 扣分】
输入：text="a b a b a"，n=3，cap=0.5。
第 1 步：正则得到 toks=["a","b","a","b","a"]。
第 2 步：滑动长度 3 的窗口，grams=[("a","b","a"),("b","a","b"),("a","b","a")]。
第 3 步：总数 3、去重后 2，重复数量为 1，原始扣分=1*0.5*2/3≈0.3333。
第 4 步：与 cap=0.5 取较小值，输出约 0.3333。
若输入只有 "a b"，凑不出 3-gram，返回 0.0。
这些是正则切出来的词/标点，不是模型 tokenizer 的 token；连续中文可能被视为一个词段。
'''
def rep_penalty(text, n=3, cap=0.5):
    # 计算一段文本的“重复惩罚分数”。文本里重复出现的连续词组越多，返回值越接近 cap，默认最高为 0.5。
    '''
        【语句示例：toks】
        输入 text="A b a b a"。步骤：lower 得到 "a b a b a"，正则选择连续词字符或单个非空白标点。输出 toks=["a","b","a","b","a"]；"Hello, world!" 则得到 ["hello",",","world","!"]。
        \w+|[^\w\s] 可以理解为：
        1. \w+       ：匹配连续的单词字符，例如 hello、world
        2. |         ：表示“或者”
        3. [^\w\s]   ：匹配既不是单词字符、也不是空白字符的字符，
                    通常就是 , ! ? . 等标点符号

        例如：
        text = "Hello, world!"

        先执行：
        text.lower()
        得到：
        "hello, world!"

        然后 re.findall(...) 会匹配：
        hello  -> \w+
        ,      -> [^\w\s]
        world  -> \w+
        !      -> [^\w\s]

        空格不会被匹配。

        最终：
        toks = ["hello", ",", "world", "!"]
    '''
    toks = re.findall(r"\w+|[^\w\s]", text.lower()) #text = "Hello, world!" toks = ["hello", ",", "world", "!"]
    '''
    【语句示例：grams】
    输入 toks=["a","b","a","b","a"]、n=3。range(5-3+1) 给出 0,1,2；切片并转 tuple，输出 [("a","b","a"),("b","a","b"),("a","b","a")]。tuple 可被 set 去重。
    '''
    grams = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    '''
    【语句示例：return min(cap, (len(grams) - len(set(grams))) * cap * 2 / len(grams)) if grams else 0.0】
    输入 3 个 grams，其中 2 个唯一。先计算 (3-2)*0.5*2/3=1/3，再 min(0.5,1/3)，返回约 0.3333。若 grams=[]，条件表达式直接返回 0.0，避免除以 0。
    '''
    return min(cap, (len(grams) - len(set(grams))) * cap * 2 / len(grams)) if grams else 0.0
    # len(grams) - len(set(grams))grams 总数：4 去重后数量：3 重复数量：4 - 3 = 1

# 自定义的Critic模型，继承自MiniMindLM
# 在 MiniMind 隐藏状态上增加标量价值头，为每个 token 位置预测未来回报。
'''
【CriticModel 类：每个序列位置输出一个未来回报估计】
输入配置例：hidden_size=64、num_hidden_layers=1；输入 ids 的形状为 [2,6]。
第 1 步：父类创建语言模型骨干及 lm_head，再额外创建 Linear(64,1) 的 value_head。
第 2 步：forward 用骨干得到 [2,6,64] 隐藏状态，再执行本文件显式写出的 norm。
第 3 步：每个位置映射到 1 个数，[2,6,64]→[2,6,1]→[2,6]。
示例输出可为 [[0.0,0.1,0.2,0.4,0.7,0.0],[0.0,0.0,0.1,0.3,0.5,0.0]]；数值是假设。
这些价值用于 GAE 和 Critic 回归，不是外部奖励模型的回答质量评分。
代码实际是“增加 value_head”：没有删除或替换继承来的 lm_head，只是不在此 forward 使用它。
'''
class CriticModel(MiniMindForCausalLM):
    # 先构建因果语言模型，再增加从 hidden_size 到 1 的价值预测头。
    '''
    【CriticModel.__init__ 示例】输入 params=MiniMindConfig(hidden_size=64,num_hidden_layers=1)。先由父类建立骨干，再新增权重 [1,64]、偏置 [1] 的价值头。构造表达式返回 Critic 实例；__init__ 本身返回 None，不在这里加载训练权重。
    '''
    def __init__(self, params):
        '''
        【语句示例：super().__init__(params)】
        输入 params.hidden_size=64。super().__init__(params) 调用 MiniMindForCausalLM 构造函数，建立 self.model 和 self.lm_head。输出副作用：这些子模块已注册，尚未创建下面的 value_head。
        '''
        super().__init__(params)
        # 新增输出单一价值的 value_head；继承的 lm_head 仍保留，但此 forward 不使用它。
        '''
        【语句示例：self.value_head】
        输入 H=64。nn.Linear(64,1) 创建 64 个权重及 1 个偏置，赋给 self.value_head；对一个 h 向量计算 w·h+b。假设只 w[0]=0.5、b=0.1、h[0]=2 且其余项为 0，则输出 1.1。
        '''
        self.value_head = nn.Linear(params.hidden_size, 1)

    # 将 [B,T,H] 隐藏状态映射为 [B,T,1]，去掉末尾单例维得到价值 [B,T]。
    '''
    【CriticModel.forward 示例：输入 token → 每位置价值】
    输入 input_ids=[[11,12,21,2]]，attention_mask=[[1,1,1,1]]，H=64。
    第 1 步：骨干返回 (hidden,缓存,aux_loss)，hidden 形状 [1,4,64]。
    第 2 步：本实现再次调用 self.model.norm；骨干内部已经 norm 过，这里确实又做了一次。
    第 3 步：假设再次归一化后，每个位置向量的第一个分量为 [0.2,0.4,0.6,0.8]，
    且价值头只 w[0]=0.5、b=0.1，则每位置结果为 [0.2,0.3,0.4,0.5]。
    输出 tensor([[0.2,0.3,0.4,0.5]])，形状 [1,4]；这里不计算语言模型交叉熵。
    上述隐藏向量和权重是计算假设，不是由 token 编号直接推导的真实模型输出。
    '''
    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        # 使用基础模型获取隐藏状态
        '''
        【语句示例：outputs】
        输入 ids 为 [1,4]。self.model 是骨干，输出 tuple；outputs[0] 是 [1,4,64] 隐藏状态，后两项为缓存与 MoE 辅助损失。kwargs 中的额外参数继续传给骨干。
        '''
        outputs = self.model(input_ids=input_ids, attention_mask=attention_mask, **kwargs)
        '''
        【语句示例：hidden_states】
        输入 outputs[0] 形状 [1,4,64]。再次用 RMSNorm 对每个位置的 64 维向量归一化，输出形状不变。手算小向量 [3,4]、缩放权重为 1、忽略 eps 时，除以 sqrt((9+16)/2)，约得 [0.8485,1.1314]；真实骨干输出此前已经归一化过。
        '''
        hidden_states = self.model.norm(outputs[0])#再做一次最后的 RMSNorm 归一化
        # 使用value_head获取价值估计
        '''
        【语句示例：values】
        输入 hidden_states=[1,4,64]。Linear 输出 [1,4,1]；例如末维标量依次为 0.2,0.3,0.4,0.5。squeeze(-1) 去掉最后的 1，得到 values=[[0.2,0.3,0.4,0.5]]，形状 [1,4]，保留批次维。
        '''
        values = self.value_head(hidden_states).squeeze(-1)
        '''
        【语句示例：return values】
        输入 values=tensor([[0.2,0.3,0.4,0.5]])。直接返回整个 [1,4] 张量；调用方稍后按 logp_pos 挑出用于各回答 token 的状态价值。
        '''
        return values


# 逐条合并长度/思考格式奖励、重复扣分与奖励模型得分，输出 [B]。
'''
【calculate_rewards 函数：规则分 + 外部模型分】
输入：prompts 中每条为聊天模板字符串；responses 为相同长度的生成回答列表；reward_model 为评分器。
单条手算：response="hello world"，没有 </think>，字符数 11，小于 20，长度分=-0.5。
正则只有两个词，默认 n=3 无法组成 n-gram，重复扣分=0。假设奖励模型返回 1.2，最终奖励=0.7。
步骤：创建零向量 → 从 prompt 提取历史 → 长度/思考格式加分 → 重复扣分 → 加外部模型分。
输出 torch.tensor([0.7])，形状 [1]；B 条回答输出 [B]，不会在这里训练评分模型。
若包含 </think>，思考长度检查用分割点之前的原始字符串，可能含 <think> 标记；不是只数纯思考文字。
总奖励不再截断到 [-3,3]：那个范围是外部包装器对模型分的限制，随后还会叠加规则分。
'''
def calculate_rewards(prompts, responses, reward_model):
    # 给每条模型回答打“总奖励分”，供 PPO / GRPO 等强化学习训练使用。
    '''
    【语句示例：rewards】
    输入 responses=["hello world","another answer"]，len=2。创建 rewards=tensor([0.,0.]) 并放到 args.device，形状 [2]；每个位置累计一条回答的奖励。
    '''
    rewards = torch.zeros(len(responses), device=args.device)#rewards.shape == [回答数量]

    # PyTorch：no_grad 中的运算不建立反向图，用于参考模型/采样以节省显存；不会自动切换 eval 模式。
    '''
    【语句示例：with torch.no_grad():】
    输入当前生成文本。进入 no_grad 后，里面评分计算不构建梯度图；例如模型分 1.2 被当成固定奖励，不从奖励函数反传到外部评分器。
    '''
    with torch.no_grad():
        '''
        【语句示例：reward_model_scores】
        输入：还没有计算外部模型分。建立空列表 []；若随后两条回答得到 1.2 和 -0.3，列表会依次变为 [1.2]、[1.2,-0.3]。
        '''
        reward_model_scores = []
        '''
        【语句示例：for i, (prompt, response) in enumerate(zip(prompts, responses)):】
        输入两个 prompt 与两个 response。zip 配对后 enumerate 给出 (0,(p0,r0))、(1,(p1,r1))；每次 i 对应 rewards[i]。两列表应等长，zip 会按较短一边结束。
        '''
        for i, (prompt, response) in enumerate(zip(prompts, responses)):
            '''
            【语句示例：pattern】
            输入示例是含 <|im_start|>user 和 <|im_end|> 的提示词。这个正则定义两个捕获组：role 和 content；只匹配带完整结束标记的 system/user/assistant 消息，末尾未闭合的生成前缀不会匹配。
            '''
            pattern = r"<\|im_start\|>(system|user|assistant)\s+(.*?)<\|im_end\|>"
            # (system|user|assistant)  # 第 1 组：role
            # (.*?)                    # 第 2 组：content
            '''
            【语句示例：matches】
            输入 prompt 的原始文本如下（每条内容末尾都有一个空格）：
            <|im_start|>system
             你是一位数学老师。 <|im_end|>
            <|im_start|>user
             1+1? <|im_end|>
            <|im_start|>assistant
             2。 <|im_end|>
            <|im_start|>user
             那么 2+3 呢？ <|im_end|>
            <|im_start|>assistant

            re.findall 按原文顺序提取每条完整消息的两个捕获组，得到：
            matches = [
                ("system", "你是一位数学老师。 "),
                ("user", "1+1? "),
                ("assistant", "2。 "),
                ("user", "那么 2+3 呢？ "),
            ]
            role 后面的换行和内容开头的空格被正则中的 \s+ 消耗，内容末尾的空格仍保留。
            re.DOTALL 让 .*? 也能匹配内容内部的换行，支持一条消息包含多行文本。
            最后一行是等待模型续写的 assistant 前缀，没有 <|im_end|>，因此不会被提取。
            '''
            matches = re.findall(pattern, prompt, re.DOTALL)#用正则表达式从 prompt 中找出 system、user、assistant 消息。
            '''
            【语句示例：messages】
            输入多轮对话：
            matches = [
                ("system", "你是一位数学老师。 "),
                ("user", "1+1? "),
                ("assistant", "2。 "),
                ("user", "那么 2+3 呢？ "),
            ]
            遍历时，把每个二元组拆成 role 和 content，保留消息的角色和先后顺序，
            用 content.strip() 去掉每条内容两端的空白，并转成统一的字典格式：
            messages = [
                {"role": "system", "content": "你是一位数学老师。"},
                {"role": "user", "content": "1+1?"},
                {"role": "assistant", "content": "2。"},
                {"role": "user", "content": "那么 2+3 呢？"},
            ]
            这样一行列表推导式就能整理整段对话，无需为每条消息分别写转换代码。
            '''
            messages = [{"role": role, "content": content.strip()} for role, content in matches]
            '''
            【语句示例：answer】
            输入 response="hello world"。先令 answer 等于完整回答；只有后面确实发现 </think> 时，answer 才会改成标签之后的最终答案。
            '''
            answer = response
            # 1、长度奖励
            '''
            【语句示例：rewards[i]】
            输入 response="hello world"，strip 后长度 11，不在 [20,800] 内，rewards[i] 从 0 变 -0.5。若长度为 25，则加 0.5。这里按 Python 字符串长度计数，不按模型 token 数。
            '''
            rewards[i] += 0.5 if 20 <= len(response.strip()) <= 800 else -0.5#若回答去掉前后空格后的长度在 20 到 800 字符之间：奖励 +0.5
            # 2、思考内容奖励
            '''
            【语句示例：if '</think>' in response:】
            输入 response="<think>检查计算</think>答案是2"，包含闭合标签，进入分支；"hello world" 不包含，跳过思考格式奖励。
            '''
            if '</think>' in response:
                '''
                【语句示例：(thinking_content, answer_content)】
                输入 "<think>检查计算</think>答案是2"。只在第一个 </think> 处分割，得到 thinking_content="<think>检查计算"、answer_content="答案是2"。后续若还有闭合标签，不会在这一步继续分割。
                '''
                thinking_content, answer_content = response.split('</think>', 1)
                '''
                【语句示例：rewards[i]】
                输入 thinking_content="<think>检查计算"，长度 11，其中标签占 7 个字符、中文占 4 个字符，小于 20，所以加 -0.5。若 strip 后长度为 30，则加 1.0；代码没有先移除 <think>。
                '''
                rewards[i] += 1.0 if 20 <= len(thinking_content.strip()) <= 300 else -0.5#思考过程长度在 20 到 300 字符：奖励 +1.0，否则：惩罚 -0.5
                '''
                【语句示例：rewards[i]】
                输入只有一个 </think>，count=1，奖励再加 0.25；若存在两个则加 -0.25。这个检查只数闭合标签，不校验整段 XML 或开放标签是否完整。
                '''
                rewards[i] += 0.25 if response.count('</think>') == 1 else -0.25#检查结束标签是否恰好出现一次：刚好 1 次：+0.25
                '''
                【语句示例：answer】
                输入 answer_content="  答案是2  "，strip 后得到 answer="答案是2"。后面的重复扣分和外部评分只看此最终答案，思考部分不再传入它们。
                '''
                answer = answer_content.strip()#后面评分和重复检测只使用真正展示给用户的最终回答，不把思考过程算进去。
            # 3、重复惩罚
            '''
            【语句示例：rewards[i]】
            输入 answer="a b a b a"，rep_penalty≈0.3333。若当前规则奖励为 0.5，则减后约为 0.1667；若没有重复则减 0，不改变原值。
            '''
            rewards[i] -= rep_penalty(answer)
            # 4、调用奖励模型评分
            '''
            【语句示例：score】
            输入 messages=[{"role":"user","content":"1+1?"}]、answer="2"。调用已加载评分器的包装接口；假设输出 score=1.2。这是模型推理输出，不是本句根据答案文字直接写死的分数。
            '''
            score = reward_model.get_score(messages, answer)
            '''
            【语句示例：reward_model_scores.append(score)】
            输入列表此前为 []、score=1.2。append 后得到 [1.2]；下一条若为 -0.3，则变成 [1.2,-0.3]，顺序与 rewards 相同。
            '''
            reward_model_scores.append(score)

        '''
        【语句示例：reward_model_scores】
        输入 Python 列表 [1.2,-0.3]。torch.tensor 将其变成设备上的 [2] 浮点张量，之后可与规则奖励逐元素相加。
        '''
        reward_model_scores = torch.tensor(reward_model_scores, device=args.device)
        '''
        【语句示例：rewards】
        输入规则分 [-0.5,0.5]、模型分 [1.2,-0.3]。相同下标相加，rewards 更新为 [0.7,0.2]，不在这里再次截断总分。
        '''
        rewards += reward_model_scores#把奖励模型分数加到前面的规则奖励中。

    '''
    【语句示例：return rewards】
    输入累计完毕的 rewards=[0.7,0.2]。返回形状 [2] 的张量；后续 PPO 会将每条回答的序列级奖励放到末尾有效回答 token 上。
    '''
    return rewards

# Actor 生成回答
# → Reward Model 给回答打分
# → Critic 判断“这个回答是否比预期更好”
# → PPO 让 Actor 更倾向生成高奖励回答
# → 同时限制 Actor 不要偏离原模型太远
# 一轮 PPO：固定采样时的旧策略/价值，计算 GAE 后多次小批更新；参考策略约束另加到损失。
# 本函数使用入口初始化的模型、优化器、args 等外部对象；start_step 用于续训批次编号。
'''
【ppo_train_epoch：一批生成数据如何更新 Actor 和 Critic】
输入：epoch=0、start_step=0、loader 每批 2 个 prompt；rollout_engine 生成，ref_model 固定，reward_model 评分。
另外依赖主入口建立的全局 actor_model、critic_model、tokenizer、args、优化器、autocast_ctx、lm_config。
贯穿下面张量注释的示例：B=2、补齐后 P=3、R=3，假设 PAD=0、EOS=2。
提示 ids=[[0,11,12],[13,14,15]]，左侧补齐 mask=[[0,1,1],[1,1,1]]。
假设 torch 引擎生成 completion_ids=[[21,2,2],[31,32,2]]，第一条结束后继续填 EOS，
完整 gen_out=[[0,11,12,21,2,2],[13,14,15,31,32,2]]，prompt_lens=[3,3]。
当前 torch 引擎返回的 completion_mask 全为 1，之后由本函数找第一个 EOS 来排除它之后的位置。
SGLang 引擎会去掉提示的左 PAD，按样本返回自己的 prompt_lens 和 completion_mask；不能混用两种排布。
上面的 token 和生成结果只用于示意，不是实际 tokenizer 或模型的固定输出。

第 1 步：编码、采样，保存旧策略回答 logp；假设外部总奖励为 [1,2]。
第 2 步：定位回答 token 的预测位置 logp_pos=[[2,3,4],[2,3,4]]；最终回答 mask=[[1,1,0],[1,1,1]]。
第 3 步：Critic 为这些位置给旧价值，假设 old_resp_values=[[0.2,0.4,0],[0.1,0.3,0.5]]。
第 4 步：末尾奖励变成 [[0,1,0],[0,0,2]]；gamma=1、lambda=0.95 时倒推 GAE：
advantages=[[0.77,0.6,0],[1.74375,1.625,1.5]]，
returns=[[0.97,1,0],[1.84375,1.925,2]]；returns 在优势标准化之前计算。
第 5 步：只按有效位置计算优势均值和方差；打乱样本切 mini-batch，重新算当前 Actor/Critic。
第 6 步：用新旧概率比做 PPO 裁剪；另加参考模型 KL 和 Critic 回归损失，再反传和优化。
第 7 步：统计日志，在保存间隔同步采样策略并保存 Actor 与续训状态。
输出：函数隐式返回 None；副作用是参数、优化器/调度器状态、日志和权重文件发生更新。
旧策略 old 与参考策略 ref 不同：old 固定本次采样概率；ref 是作为长期约束的冻结参考模型。
Critic 是每位置未来回报估计器；reward_model 是外部回答评分器，本函数不训练 reward_model。
'''
def ppo_train_epoch(epoch, loader, iters, rollout_engine, ref_model, actor_scheduler, critic_scheduler, reward_model, start_step=0, wandb=None):
    '''
    【语句示例：actor_model.train()】
    输入 Actor 可能在上次保存后处于 eval。train() 将其切到训练模式，例如启用非零 Dropout；不会自动清梯度，也不等于执行一次参数更新。
    '''
    actor_model.train()
    '''
    【语句示例：critic_model.train()】
    输入 Critic 网络。train() 设置训练行为；例如 dropout=0 时数值上没有随机丢弃，但 training 标志仍变成 True。
    '''
    critic_model.train()
    '''
    【语句示例：grad_accum_step】
    输入：新一轮 ppo_train_epoch 开始。令 grad_accum_step=0；每个 mini-batch 反传后加 1，用余数决定何时更新。此计数器在这个函数内跨 rollout 批次累计。
    '''
    grad_accum_step = 0

    '''
    【语句示例：for step, batch in enumerate(loader, start=start_step + 1):】
    输入 start_step=2、loader 还有两批。enumerate(...,start=3) 依次给出 step=3、4；batch 例如 {"prompt":[p0,p1],"answer":["",""]}。编号延续已跳过的批次，不是从 0 重新计数。
    '''
    # 这里需要注意模型更新的频率，old policy是每个batch开始前的policy，critic也是每个batch开始前的critic，后续的ppo update是用当前的policy和critic去更新参数
    # 所以训练是以一个batch为单位的，old policy和critic在一个batch中是不会更新的，只有在下一个batch开始前才会更新
    for step, batch in enumerate(loader, start=start_step + 1):
        # 1、编码
        '''
        【语句示例：prompts】
        输入 batch={"prompt":["问题一的聊天前缀","问题二的聊天前缀"],"answer":["",""]}。取出 prompts，为长度 B=2 的字符串列表；不使用空 answer 作为训练答案。
        '''
        prompts = batch["prompt"]  # list[str], length B
        '''
        【语句示例：enc】
        输入两条提示，假设有效 token 分别为 [11,12]、[13,14,15]，max_seq_len 足够。
        步骤：tokenizer 编码，padding_side="left" 左补齐，再搬到 args.device。
        输出 enc.input_ids=[[0,11,12],[13,14,15]]，enc.attention_mask=[[0,1,1],[1,1,1]]，均为 [2,3]。
        若提示过长，truncation=True 按 tokenizer 的截断配置限制到 max_seq_len；这里不指定截断方向。
        '''
        enc = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=args.max_seq_len,
                        padding_side="left").to(args.device)  # input_ids: [B, P], attention_mask: [B, P]
        # 2、rollout:生成回答：
        '''
        【语句示例：rollout_result】
        对应源码：trainer/rollout_engine.py 中的 RolloutResult 数据类和 TorchRolloutEngine.rollout。
        这里先按默认的 torch 后端展示完整结果，再说明 SGLang 的差异。

        第 1 步：调用时传入两条已经分词、左侧补齐的提示。
            prompt_ids = tensor([
                [ 0,11,12],
                [13,14,15]
            ])
            attention_mask = tensor([
                [0,1,1],
                [1,1,1]
            ])
        本例假设 PAD=0、EOS=2，B=2、补齐后的提示宽度 P=3；num_generations=1。
        max_new_tokens 假设为 3，temperature=0.8。编号和下方分数用于教学，非真实采样记录。

        第 2 步：引擎调用 model.generate，每个提示各生成一条回答。
            假设第 1 轮生成：[21,31]，两条都未结束。
            假设第 2 轮生成：[ 2,32]，第一条遇到 EOS=2，第二条继续。
            假设第 3 轮生成：[ 2, 2]，全部结束。
        注意：model/model_minimind.py 的 generate 对已经 finished 的行继续填 EOS，
              因此第一条回答尾部是 [21,2,2]，不是 [21,2,0]。
        返回的完整序列仍包含输入提示，故 output_ids 是 [2,P+R]=[2,6]。

        第 3 步：引擎令 prompt_len=prompt_ids.size(1)=3，
                再取 output_ids[:,3:]，分离出 [2,3] 的 completion_ids。
        第 4 步：compute_per_token_logps 重新前向评估完整序列，
                为每个回答 token 提取原模型的 log 概率，得到 [2,3] 的 per_token_logps。
                例如假设第一条依次为 [-0.7,-0.2,-2.0]，第二条为 [-0.4,-0.8,-0.1]。
                第一条第三个 EOS 虽是结束后填入的，也会在此处被计算一个模型 logp；
                它不等于填充操作本身的概率，后续 PPO 会将这个位置屏蔽。
        第 5 步：batch_decode(...,skip_special_tokens=True) 解码回答，跳过 EOS 等特殊标记。
                为阅读方便，假设本例解码文本为 ["答案一","答案二"]；
                这不表示项目真实 tokenizer 的 21 号 token 一定对应“答案一”。
        第 6 步：源码用 new_full 填出 prompt_lens=[3,3]，用 new_ones 构造全 1 的回答掩码。

        最终示例结果（tensor 均在运行设备上，这里省略 device、dtype 和 grad 等显示信息）：
            rollout_result = RolloutResult(
                output_ids=tensor([
                    [ 0,11,12,21, 2,2],
                    [13,14,15,31,32,2]
                ]),                              # [B,P+R] = [2,6]
                completion_ids=tensor([
                    [21, 2,2],
                    [31,32,2]
                ]),                              # [B,R] = [2,3]
                per_token_logps=tensor([
                    [-0.7,-0.2,-2.0],
                    [-0.4,-0.8,-0.1]
                ]),                              # [B,R] = [2,3]，浮点数
                completions=["答案一","答案二"],  # 长度 B=2 的字符串列表
                prompt_lens=tensor([3,3]),        # [B] = [2]，包含提示左侧补齐宽度
                completion_mask=tensor([
                    [1,1,1],
                    [1,1,1]
                ])                               # [B,R] = [2,3]，torch 后端实际返回全 1
            )

        这是带属性的数据类对象，不是字典：
            rollout_result.output_ids       → 取完整 token 序列；
            rollout_result.completions      → 取回答文本；
            rollout_result.per_token_logps  → 取本批固定的旧策略 logp。
        后面的 PPO 找到每行第一个 EOS：下标分别是 [1,2]，包含 EOS 的有效长度为 [2,3]，
        最终 resp_policy_mask 才变成 [[1,1,0],[1,1,1]]，排除第一条重复填入的 EOS。
        输入 attention_mask 管提示词；返回的 completion_mask 管回答；两者不能混淆。

        后端差异：若 SGLang 对同样两题实际返回回答 [21,2] 和 [31,32,2]，
                  它先去掉提示的左 PAD，再拼接并在右侧补齐，可能得到：
            output_ids=[[11,12,21,2,0,0],[13,14,15,31,32,2]]，
            completion_ids=[[21,2,0],[31,32,2]]，prompt_lens=[2,3]，
            completion_mask=[[1,1,0],[1,1,1]]。
        SGLang 的 logp 来自服务返回，并在补齐位置填 0；不能直接套用上述本地 logp 数值。
        具体字段结构相同，但提示位置、补齐方式和 logp 来源取决于所选引擎。

        这是采样阶段，不执行 optimizer.step。temperature 影响生成，
        本地后端返回的 logp 则来自额外的原模型前向，不是直接读取温度变换后的采样概率。
        '''
        rollout_result = rollout_engine.rollout(
            prompt_ids=enc.input_ids,
            attention_mask=enc.attention_mask,
            num_generations=1,
            max_new_tokens=args.max_gen_len,
            temperature=0.8,
        )
        '''
        【语句示例：gen_out】
        输入 rollout_result.output_ids。示例取出 gen_out=[[0,11,12,21,2,2],[13,14,15,31,32,2]]，形状 [2,6]；前 3 列为补齐提示，后 3 列为回答。此处是取字段，不重新生成。
        '''
        gen_out = rollout_result.output_ids# prompt + response 的完整 token
        '''
        【语句示例：completion_ids】
        输入 rollout_result.completion_ids。取出 completion_ids=[[21,2,2],[31,32,2]]，形状 [2,3]；这里只有回答 token，后面的 EOS 定位会用到它。
        '''
        completion_ids = rollout_result.completion_ids# 只包含 response 的 token
        '''
        【语句示例：prompt_lens】
        输入本例 torch 后端的 prompt_lens=[3,3]。to 迁移设备，值不变。这是含左 PAD 的提示宽度 P，而不是第一题真实非 PAD 长度 2；SGLang 的逐条长度可以不同。
        '''
        prompt_lens = rollout_result.prompt_lens.to(args.device)# 回答起始位置 [B]；torch 后端为含左侧补齐的提示宽度
        '''
        【语句示例：responses_text】
        输入 rollout_result.completions，例如 ["答案一","答案二"]。取出 responses_text 供规则奖励及评分器使用；special tokens 的解码处理由 rollout 后端决定。
        '''
        responses_text = rollout_result.completions # 解码后的回答文本列表
        '''
        【语句示例：old_resp_logp】
        输入旧策略逐 token logp，例如 [[-0.7,-0.2,-2.0],[-0.4,-0.8,-0.1]]，形状 [2,3]。迁移后保存到 old_resp_logp；即使 Actor 后续更新，这批旧值也不跟着重算。最后的无效位置稍后被 mask 排除。
        '''
        old_resp_logp = rollout_result.per_token_logps.to(args.device)
        # 3、reward阶段：对回答打奖励分
        '''
        【语句示例：rewards】
        输入 prompts 和生成文本，调用 calculate_rewards。假设综合规则及评分器后得到 [1.0,2.0]，rewards 形状 [2]；它是每条回答一个分数，不是每 token 一个分数。
        '''
        rewards = calculate_rewards(prompts, responses_text, reward_model)  # [B]

        '''
        【语句示例：if args.debug_mode and is_main_process() and (step % args.debug_interval == 0):】
        输入 debug_mode=True、当前为主进程、step=20、debug_interval=20。20%20=0，进入调试输出；若任一条件不满足就跳过，不改变奖励或参数。
        '''
        if args.debug_mode and is_main_process() and step % args.debug_interval == 0:
            '''
            【语句示例：for i in range(len(prompts)):】
            输入 len(prompts)=2。循环 i=0、1，分别打印两条采样轨迹；此 i 只是本批中的样本编号。
            '''
            for i in range(len(prompts)):
                '''
                【语句示例：Logger(f'[DEBUG] step={step}, sample[{i}]')】
                输入 step=20、i=0。终端打印 [DEBUG] step=20, sample[0]，没有函数返回值供训练使用。
                '''
                Logger(f"[DEBUG] step={step}, sample[{i}]")
                '''
                【语句示例：Logger('-' * 100)】
                输入 "-" 重复 100 次。Logger 打印分隔线，便于区分样本；不会修改张量。
                '''
                Logger('-'*100)
                '''
                【语句示例：Logger(f"{'=' * 30} [DEBUG] sample[{i}] CONTEXT_BEGIN {'=' * 30}")】
                输入 i=0。构造两侧各 30 个等号的 CONTEXT_BEGIN 标记，提示接下来打印的是该样本的输入上下文。
                '''
                Logger(f"{'=' * 30} [DEBUG] sample[{i}] CONTEXT_BEGIN {'=' * 30}")
                '''
                【语句示例：Logger(prompts[i])】
                输入 prompts[0]="问题一的聊天前缀"。原样打印完整提示字符串；它不是生成的回答。
                '''
                Logger(prompts[i])
                '''
                【语句示例：Logger(f"{'=' * 31} [DEBUG] sample[{i}] CONTEXT_END {'=' * 31}")】
                输入 i=0。打印 CONTEXT_END 及等号分隔，标记上面的上下文已结束。
                '''
                Logger(f"{'=' * 31} [DEBUG] sample[{i}] CONTEXT_END {'=' * 31}")
                '''
                【语句示例：Logger(f'[DEBUG] prompt_len={prompt_lens[i].item()}, response_len={len(responses_text[i])}')】
                输入 prompt_lens[0]=3、responses_text[0]="答案一"。日志显示 prompt_len=3、response_len=3；前者是 token 位置长度，后者是 Python 字符串字符数，单位不相同。
                '''
                Logger(f"[DEBUG] prompt_len={prompt_lens[i].item()}, response_len={len(responses_text[i])}")
                '''
                【语句示例：Logger(f"{'=' * 28} [DEBUG] sample[{i}] RESPONSE_BEGIN {'=' * 28}")】
                输入 i=0。打印 RESPONSE_BEGIN，下面开始显示生成回答。
                '''
                Logger(f"{'=' * 28} [DEBUG] sample[{i}] RESPONSE_BEGIN {'=' * 28}")
                '''
                【语句示例：Logger(responses_text[i])】
                输入 responses_text[0]="答案一"。原样打印这条生成文本，便于观察重复、格式和回答内容。
                '''
                Logger(responses_text[i])
                '''
                【语句示例：Logger(f"{'=' * 29} [DEBUG] sample[{i}] RESPONSE_END {'=' * 29}")】
                输入 i=0。打印 RESPONSE_END，结束该条回答的日志区域。
                '''
                Logger(f"{'=' * 29} [DEBUG] sample[{i}] RESPONSE_END {'=' * 29}")
                '''
                【语句示例：Logger(f'[DEBUG] reward={rewards[i].item():.4f}')】
                输入 rewards[0]=tensor(1.0)。item() 取出标量，格式化为 [DEBUG] reward=1.0000。
                '''
                Logger(f"[DEBUG] reward={rewards[i].item():.4f}")
                '''
                【语句示例：Logger('=' * 100)】
                输入 "=" 重复 100 次。打印本条样本的结束分隔线，不产生梯度或数据变化。
                '''
                Logger('='*100)

        '''
        【贯穿示例：完整序列、回答位置与训练掩码】
        【先看结论】
        这一段围绕回答长度和 EOS 的计算，最终就是为了得到 resp_policy_mask：
        告诉 PPO 哪些回答 token 参与训练，哪些位置应当排除。
        本例要解决的是：回答已经结束，但为了让批次等长，后面又补了多个 EOS；
        只保留第一个 EOS，后面的重复 EOS 不参与训练。注意，这段代码不会阻止生成多个 EOS，
        而是在训练时把首个 EOS 后的位置屏蔽掉，同时排除生成掩码标为无效的位置。

        例如 EOS=2：
        回答 token：       [21,  2,  2]
        含义：             [回答内容, 结束标记, 补齐用的重复结束标记]
        resp_policy_mask： [ 1,  1,  0]
        结果：token 21 和首个 EOS 参与训练，最后的重复 EOS 不参与。
        若回答为 [31,32,2]，则掩码为 [1,1,1]，三个位置都参与训练。
        下面按代码顺序分析这个掩码如何一步步算出来。
        以下用列表展示张量数值，位置编号从 0 开始。假设使用 torch 后端，
        tokenizer.pad_token_id=0，tokenizer.eos_token_id=2，
        args.device=gen_out.device="cuda:0"，所有张量均在该设备上。

        1. 输入：两条提示，每条占 3 列，回答也补齐为 3 列。
        原始数据是两条提示文本，先由 tokenizer 编码，再交给 rollout 生成回答。
        为便于手算，假设提示 A 编码为 [11,12]，提示 B 编码为 [13,14,15]。
        这些编号只是教学假设，不代表真实 tokenizer 对某段文字的固定编码。
        每个编号表示一个 token（可能是字、词或片段），不能当成 token 的文字含义。
        prompts = ["提示文本A", "提示文本B"]  # 提示文本的示意
        批量输入必须等宽，最长提示有 3 个 token，因此第一条在左边补 PAD=0：

        prompt_ids = [[0,11,12], [13,14,15]]
        attention_mask = [[0,1,1], [1,1,1]]  # 提示中的真实 token 为 1，左侧 PAD 为 0

        本例每条提示只生成一个回答。模型逐步生成：
        提示 A -> token 21 -> EOS=2，表示回答结束，真实回答为 [21,2]；
        提示 B -> token 31 -> token 32 -> EOS=2，真实回答为 [31,32,2]。
        torch 后端在等待第二条生成结束时，给已结束的第一条继续填 EOS，
        于是批量回答为 [[21,2,2],[31,32,2]]，其中第一条最后的 2 只是占位。
        将每条补齐后的提示与回答沿序列维拼接，便得到下面的 gen_out。
        prompt_lens = [3,3]                  # [2]，含左侧 PAD 的提示宽度
        prompt_lens 来自 prompt_ids.size(1)=3，后端为每条样本填入这个宽度。
        它表示回答在完整序列中从第几列开始，不是每条提示的非 PAD token 数 [2,3]。
        gen_out = [                         # [2,6]，提示 + 回答
            [ 0,11,12,21, 2,2],
            [13,14,15,31,32,2],
        ]
        # 列编号： 0   1   2 | 3   4   5
        # 第一条：PAD 11  12 | 21 EOS EOS（最后一个 EOS 是补齐占位）
        # 第二条：13  14  15 | 31  32 EOS
        completion_ids = [                  # [2,3]，只含回答
            [21, 2,2],
            [31,32,2],
        ]
        rollout_result.completion_mask = [  # [2,3]，本例 torch 后端返回全 1
            [1,1,1],
            [1,1,1],
        ]
        该后端用 new_ones 创建 completion_mask，而不是逐个判断 token 是否有效，
        所以第一条最后的占位 EOS 也得到 1，需要本段后续计算继续排除。

        2. 完整序列掩码与下一 token 标签：
        full_mask 是完整序列的 attention_mask，供模型前向时识别 PAD 位置。
        对 gen_out 每个元素判断 !=0：第一行只有开头的 0 得到 False，
        其他元素都得到 True；long() 将 False/True 转为整数 0/1。
        full_mask = [                       # [2,6]，int64，gen_out != PAD 后转 long
            [0,1,1,1,1,1],
            [1,1,1,1,1,1],
        ]
        labels = [                          # [2,5]，gen_out[:,1:] 的独立副本
            [11,12,21, 2,2],
            [14,15,31,32,2],
        ]
        labels 是“下一个 token”的目标编号：[:,1:] 去掉每行第 0 列，clone 创建副本。
        第一行 [0,11,12,21,2,2] -> [11,12,21,2,2]，第二行同理。
        模型在当前位置预测下一位置，所以 labels 与 logits[:,:-1] 对齐：
        读到第一行第 2 列的 token 12 后，第 2 列输出用于预测第 3 列的 token 21。
        full_mask 仅排除 PAD=0，尚未排除第一条末尾的重复 EOS。

        3. 回答标签与预测位置：
        B 统计提示条数：len(prompts)=2，后续按这两条样本分别计算奖励和损失。
        resp_labels 只保留**回答目标**，直接引用 rollout 给出的 completion_ids，
        不含提示 token；这一步赋值没有复制张量。
        B = 2                               # len(prompts)，批次大小
        resp_labels = [                     # [2,3]，与 completion_ids 是同一张量
            [21, 2,2],
            [31,32,2],
        ]
        resp_idx = [[0,1,2]]                 # [1,3]，回答内部位置
        回答宽度 resp_labels.size(1)=3，arange(3) 产生 [0,1,2]，
        unsqueeze(0) 变成一行，便于与两条样本各自的长度广播计算。

        ⭐️⭐️⭐️
        logp_pos = [                        # [2,3]，预测回答 token 的状态位置
            [2,3,4],
            [2,3,4],
        ] **表示回答在完整序列中对应的logits位置**。

        计算：prompt_lens.unsqueeze(1)-1 = [[2],[2]]，广播加上 [[0,1,2]]。
        回答在完整序列的第 3、4、5 列，其预测来自第 2、3、4 列。
        一般公式：回答内部第 j 个 token 位于 prompt_lens[i]+j，
        预测它的状态位于 prompt_lens[i]+j-1，因此 logp_pos 要减 1。
        例如第一条 j=0：3+0-1=2；j=1：3+1-1=3；j=2：3+2-1=4。
        后续用这些位置提取回答 token 的 log probability 和生成前状态的价值。

        4. 逐条回答：哪些位置可用？回答在哪里结束？
        这一小段先接收生成代码返回的回答掩码，再查找首个 EOS，把它的位置换成保留长度。
        先记住本例的回答 token 和位置：
        回答内部位置 j：  0   1   2
        第一条回答：     21   2   2   -> 最后一个 2 是补齐占位
        第二条回答：     31  32   2
        EOS=2 表示“模型结束回答”。训练时保留首个 EOS，因为模型也要学习何时停止。

        （1）resp_pad_mask = rollout_result.completion_mask.to(args.device).bool()
        意义：接收生成代码返回的回答掩码，并转成布尔值。
        这里“后端”指负责生成回答的 rollout 实现，本例是 rollout_engine.py 中的 torch 实现。
        每条回答的每个位置都有一个布尔值，True 表示后端标为可用，False 表示排除。
        它是后端提供的初步筛选结果，还不是最终参与训练的位置。
        来源：rollout_result.completion_mask.to(args.device).bool()。
        to 将数据移到训练设备；bool 将 1 转为 True、0 转为 False。
        本例 torch 后端的 completion_mask 全为 1，所以结果为：
        resp_pad_mask = [                    # [2,3]，每行一条回答，每列一个回答位置
            [True, True, True],
            [True, True, True],
        ]
        第一条最后的占位 EOS 也被标为 True，因此还要查找首个 EOS 来进一步排除。

        （2）resp_lengths = resp_pad_mask.sum(dim=1)
        意义：先统计生成代码的回答掩码中，每条回答有几个 True。
        这是每条回答的长度计数，每条回答对应一个整数，而不是每个位置一个值。
        来源：resp_pad_mask.sum(dim=1)，按行把 True 当作 1、False 当作 0 相加。
        第一条：1+1+1=3；第二条：1+1+1=3。
        resp_lengths = [3,3]                 # [2]，暂时包含第一条的占位 EOS

        （3）valid_resp = resp_lengths > 0
        意义：判断每条回答是否非空，即生成代码的掩码是否至少包含一个 True。
        每条回答对应一个布尔值。后面放置末尾奖励时，用它排除空回答。
        它只判断回答是否非空，不判断回答是否正确、质量是否好。
        来源：resp_lengths > 0，即 [3>0,3>0]。
        valid_resp = [True,True]              # [2]，本例两条回答都非空

        （4）eos_mask = resp_labels.eq(tokenizer.eos_token_id) & resp_pad_mask
        意义：逐个位置检查是否为 EOS，并排除生成代码的掩码标为 False 的位置。
        每个位置一个布尔值，True 表示“这里是 EOS，并且后端把这个位置标为可用”。
        它用于寻找结束标记，不能直接当作训练掩码，因为普通回答 token 在这里是 False。
        来源：resp_labels.eq(2) & resp_pad_mask，其中 resp_labels 是回答 token 编号。
        第一条 [21,2,2] 与 2 比较 -> [False,True,True]；
        第二条 [31,32,2] 与 2 比较 -> [False,False,True]。
        再与全 True 的 resp_pad_mask 相与，结果不变：
        eos_mask = [                         # [2,3]
            [False, True,  True],
            [False, False, True],
        ]

        （5）has_eos = eos_mask.any(dim=1)
        意义：把每个位置的检查结果汇总为“这条回答有没有 EOS”。
        每条回答对应一个布尔值，用来决定是否需要按 EOS 截断长度。
        来源：eos_mask.any(dim=1)，检查每行是否至少有一个 True。
        两行都存在 True，所以：
        has_eos = [True,True]                 # [2]

        （6）eos_pos = torch.argmax(eos_mask.int(), dim=1)
        意义：找到首个 EOS 在回答内部的位置。
        每条回答对应一个位置编号，从 0 开始；它是位置，不是 token 编号，也不是长度。
        来源：torch.argmax(eos_mask.int(), dim=1)。
        先转整数得 [[0,1,1],[0,0,1]]，再找每行最大值第一次出现的位置。
        第一行首个 1 在位置 1，第二行首个 1 在位置 2，所以：
        eos_pos = [1,2]                       # [2]
        如果某行没有 EOS，全 0 的 argmax 也会返回 0，因此必须用 has_eos 判断这个位置是否可信。

        （7）resp_lengths = torch.where(has_eos, eos_pos + 1, resp_lengths).long().clamp(min=1)
        意义：把首个 EOS 的位置换成包含它的回答长度，更新原来的 resp_lengths。
        这是对同一个长度变量的更新，接下来用它划定参与训练的范围。
        来源：where(has_eos, eos_pos+1, 原 resp_lengths)。
        有 EOS 就选择 EOS 的位置加 1，没有 EOS 就保留后端给出的原长度。
        第一条 EOS 在位置 1，保留位置 0、1，共 1+1=2 个 token；
        第二条 EOS 在位置 2，保留位置 0、1、2，共 2+1=3 个 token。
        resp_lengths = [2,3]                 # [2]，含首个 EOS，排除它之后的占位
        long() 转成整数，clamp(min=1) 把最小值限制为 1，以避免后续末尾索引出现负数。
        这不会让空回答变成有效回答：valid_resp 仍为 False，后端掩码也仍会排除空位置。

        5. 最终决定哪些回答 token 参与训练
        （8）resp_policy_mask = ((resp_idx < resp_lengths.unsqueeze(1)) & resp_pad_mask).float()
        意义：把每条回答的保留长度转换为每个位置的 1/0，供 Actor 策略训练使用。
        每个位置一个数值，1.0 表示参与，0.0 表示排除。
        目标是保留真实回答和首个 EOS，排除后端标为无效的位置以及首个 EOS 后的位置。
        来源：((resp_idx < resp_lengths.unsqueeze(1)) & resp_pad_mask).float()。
        resp_idx=[[0,1,2]] 是回答内部位置，resp_lengths=[2,3] 是刚算出的保留长度。
        unsqueeze(1) 将长度变为 [[2],[3]]，让每条回答的所有位置与自己的长度比较：
        第一条：[0<2,1<2,2<2] -> [True,True,False]；
        第二条：[0<3,1<3,2<3] -> [True,True,True]。
        再与 resp_pad_mask 相与：一个位置必须同时满足“在保留长度内”和“后端标为可用”。
        本例后端掩码全 True，所以结果不变；float() 把 True/False 转为 1.0/0.0：
        resp_policy_mask = [                 # [2,3]，float32
            [1.,1.,0.],                      # token 21、首个 EOS 参与，重复 EOS 排除
            [1.,1.,1.],                      # token 31、32、首个 EOS 都参与
        ]
        后续用它筛选策略损失并统计有效 token；被标为 0 的占位不计入损失。

        （9）resp_value_mask = resp_policy_mask.clone()
        意义：复制同一组有效位置，供 Critic 价值训练使用。
        Actor 学习如何生成回答，Critic 学习评价生成各个 token 前的状态。
        本代码让两者使用相同的有效回答位置，所以直接复制策略掩码：
        来源：resp_policy_mask.clone()，数值相同，但创建独立存储。
        
        ⭐️⭐️⭐️也就是根据：
        completion_ids = [                  # [2,3]，只含回答
                    [21, 2,2],
                    [31,32,2],
                ]

        ⭐️⭐️⭐️得到：
        resp_value_mask = [                  # [2,3]，float32
            [1.,1.,0.],
            [1.,1.,1.],
        ]
        它筛选的是与这些回答 token 对应的价值损失；第一条占位对应的价值也不参与训练。
        '''
        full_mask = (gen_out != tokenizer.pad_token_id).long()
        labels = gen_out[:, 1:].clone()
        B = len(prompts)
        resp_labels = completion_ids
        resp_idx = torch.arange(resp_labels.size(1), device=gen_out.device).unsqueeze(0)
        logp_pos = prompt_lens.unsqueeze(1) - 1 + resp_idx
        resp_pad_mask = rollout_result.completion_mask.to(args.device).bool()
        resp_lengths = resp_pad_mask.sum(dim=1)
        valid_resp = resp_lengths > 0
        eos_mask = resp_labels.eq(tokenizer.eos_token_id) & resp_pad_mask
        has_eos = eos_mask.any(dim=1)
        eos_pos = torch.argmax(eos_mask.int(), dim=1)
        resp_lengths = torch.where(has_eos, eos_pos + 1, resp_lengths).long().clamp(min=1)
        resp_policy_mask = ((resp_idx < resp_lengths.unsqueeze(1)) & resp_pad_mask).float()
        resp_value_mask = resp_policy_mask.clone()
        # 4、advantage 阶段
        '''
        【语句示例：with torch.no_grad():】
        输入已生成的固定 token 序列。进入 no_grad，下面得到的旧价值、参考 logp、GAE 和 returns 都作为训练目标，不建立反向图；更新阶段会重新前向计算有梯度的当前预测。
        '''
        with torch.no_grad():  # Rollout阶段只需推理获取old_logp和old_values，切断梯度省显存
            # （1）critic模型计算values
            '''
            【语句示例：critic_for_rollout】
            输入 critic_model。如果被 DDP 包装，取 .module；普通单卡模型直接使用自身。输出 critic_for_rollout 引用，不复制参数，也不创建另一份 Critic。
            '''
            critic_for_rollout = critic_model.module if isinstance(critic_model, DistributedDataParallel) else critic_model
            '''
            【语句示例：values_seq】
            输入 gen_out/full_mask 形状 [2,6]。Critic 为每个位置输出价值，假设 values_seq=[[0,0,0.2,0.4,0.7,0],[0,0,0.1,0.3,0.5,0]]，形状 [2,6]。其中将由 logp_pos 选择预测回答 token 前的状态。
            '''
            values_seq = critic_for_rollout(input_ids=gen_out, attention_mask=full_mask)#Critic 为完整序列预测价值
            # PyTorch：gather(dim,index) 沿指定轴按整型索引取值，输出形状与 index 一致；可用于选择词表项或序列位置。
            '''
            【语句示例：old_resp_values】
            输入上述 values_seq、logp_pos=[[2,3,4],[2,3,4]]。gather(1,...) 得 [[0.2,0.4,0.7],[0.1,0.3,0.5]]；乘 mask=[[1,1,0],[1,1,1]]，输出 old_resp_values=[[0.2,0.4,0],[0.1,0.3,0.5]]。
            ⭐️️这一句只取了回答部分的value，后续PPO训练时会用到。
            '''
            old_resp_values = values_seq.gather(1, logp_pos) * resp_value_mask # 只取回答 token 的价值
            # （2）计算参考模型的 token 概率
            '''
            【语句示例：ref_resp_logp】
            输入完整 ids=[2,6]，参考模型 logits=[2,6,V]，labels=[2,5]。
            第 1 步：[:, :-1] 去掉最后一个无后续标签的预测位置，logits 变成 [2,5,V]。
            第 2 步：log_softmax(dim=-1) 将每个位置词表分数转为 log 概率；例如目标 token 概率 0.2，对数约 -1.6094。
            第 3 步：labels.unsqueeze(-1)=[2,5,1]，gather(2,...) 取实际下一 token 的 logp；squeeze 后 [2,5]。
            第 4 步：按 logp_pos 在序列维 gather，只留回答部分，输出 ref_resp_logp=[2,3]。
            这是参考策略的评分，不是这批旧策略 logp；两者即使初始权重相同，也有不同用途。
            ⭐️这一段和rollout函数中取old model的log probability一模一样，只不过只取了回答部分的log probability，后续PPO训练时会用到。
            '''
            ref_resp_logp = F.log_softmax(ref_model(input_ids=gen_out, attention_mask=full_mask).logits[:, :-1], dim=-1).gather(2, labels.unsqueeze(-1)).squeeze(-1).gather(1, logp_pos) # 后面PPO训练用到的，这段暂时没用到
            # （3）计算优势函数和回报
            '''
            【语句示例：token_rewards】
            输入 old_resp_logp=[2,3]。zeros_like 创建同形状、同设备、同 dtype 的 token_rewards=[[0,0,0],[0,0,0]]；稍后只在每条末尾放序列级奖励。
            '''
            token_rewards = torch.zeros_like(old_resp_logp)
            '''
            【语句示例：last_idx】
            输入 EOS 截断后的 resp_lengths=[2,3]。减 1 得 last_idx=[1,2]，是回答内部的最后有效下标，不是 gen_out 中的全序列下标。
            '''
            last_idx = resp_lengths - 1  # [B]
            # 把序列级外部奖励放到最后一个有效回答 token，后续 GAE 再将信号向前传播。
            '''
            【语句示例：token_rewards[torch.arange(B, device=args.device)[valid_resp], last_idx[valid_resp]]】
            【结论】把“整条回答的外部评分”加到该回答最后一个有效 token 的奖励上。
            每条回答只加一次，既不加到所有 token 上，也不加到补齐占位上。
            后续 GAE 会利用这个末尾奖励计算前面各个生成步骤的优势。

            1. 完整输入（沿用上面的两条回答，EOS=2）：
            B = 2                                 # 两条回答，对应矩阵的两行
            resp_labels = [                       # 列编号是回答内部位置 0、1、2
                [21,  2, 2],                      # 最后一个 2 是占位，不能放奖励
                [31, 32, 2],
            ]
            resp_lengths = [2,3]                  # 截断到首个 EOS 后的有效 token 个数
            last_idx = resp_lengths - 1 = [1,2]   # 最后有效 token 的列下标（从 0 开始）
            valid_resp = [True,True]               # 两条回答都非空，可以接收奖励
            rewards = [1.0,2.0]                    # 外部评分：第一条得 1 分，第二条得 2 分
            token_rewards = [                     # 初始每个回答位置的奖励都是 0
                [0.,0.,0.],
                [0.,0.,0.],
            ]

            2. 先确定要修改的行（哪条回答）：
            torch.arange(B, device=args.device) -> [0,1]
            再用 valid_resp 筛选 -> [0,1][True,True] -> [0,1]。
            所以要给第 0 行和第 1 行加奖励。

            3. 再确定每行要修改的列（该回答最后一个有效 token）：
            last_idx[valid_resp] -> [1,2][True,True] -> [1,2]。
            第 0 行最后有效位置是列 1（首个 EOS），第 1 行是列 2（首个 EOS）。
            行索引 [0,1] 和列索引 [1,2] 按对应元素配对，选中 (0,1)、(1,2)，
            即 token_rewards[0,1] 和 token_rewards[1,2]，不是选一个 2×2 的子矩阵。

            4. 筛选相应奖励，并逐项累加：
            rewards[valid_resp] -> [1.0,2.0]。
            因此原语句在本例中等价于：
            token_rewards[0,1] += 1.0             # 第一条回答的首个 EOS：0+1=1
            token_rewards[1,2] += 2.0             # 第二条回答的首个 EOS：0+2=2
            注意 += 是在原值上加，不是覆盖；本例原值恰好都是 0。

            5. 最终输出：
            token_rewards = [                     # [2,3]，每个回答 token 对应一个奖励
                [0.,1.,0.],                       # 第一条的占位位置仍为 0
                [0.,0.,2.],
            ]
            ⭐️ 因为GAE是从后向前计算优势，所以只在最后一个有效 token 上放奖励，token_reward初始值是r_t，不是最终的回报或优势，后面还要r_t - V_t + gamma * A_(t+1)计算优势。
            
            普通 token 此时的直接奖励为 0，不表示它们没有训练信号；后续 GAE
            会结合奖励、价值估计和折扣，计算每个有效回答位置的优势与回报。
            如果某条回答为空，valid_resp 对应位置为 False，行索引、列索引、rewards
            会同时排除这条回答，整行保持不变，不会因占位下标而错误加上奖励。
            '''
            token_rewards[torch.arange(B, device=args.device)[valid_resp], last_idx[valid_resp]] += rewards[valid_resp]  # 末尾加外部奖励

            '''
            【完整示例：由末尾奖励倒推优势，再计算回报和标准化优势】
            结论：把整条回答的末尾奖励转成每个生成步骤的训练信号。
            advantages 给 Actor 使用，表示生成这一步比 Critic 原先预计的好多少；
            returns 给 Critic 使用，是它要学习预测的目标回报。
            最后只标准化 advantages，returns 保留原来的奖励尺度。

            1. 完整输入与含义（沿用前面的两条回答）
            回答位置：          0   1   2
            第一条回答：       21 EOS EOS占位
            第二条回答：       31  32 EOS
            B = 2                       # 两条回答，矩阵每行对应一条回答
            args.gamma = 1.0            # 奖励折扣，本例不随距离衰减
            args.lam = 0.95             # 控制后续 TD 误差传回当前步骤的权重
            token_rewards = [           # 外部评分 1、2 已加到各自首个 EOS 位置
                [0.,1.,0.],
                [0.,0.,2.],
            ]
            old_resp_values = [         # 生成各个回答 token 前，Critic 对未来回报的旧估计
                [0.2,0.4,0.0],          # 第一条最后的占位已乘掩码置零
                [0.1,0.3,0.5],
            ]
            例如 0.2：生成 token 21 前，Critic 预计后续回报是 0.2。
            这些数来自 Critic 的前向输出，再按 logp_pos 取出并乘价值掩码，
            不是由 token 编号计算出来的；这里假设数值如上，便于手算。
            resp_policy_mask = [        # 前面根据首个 EOS 得到的有效训练位置
                [1.,1.,0.],
                [1.,1.,1.],
            ]
            gen_len = old_resp_values.size(1) = 3  # 补齐后的回答宽度
            lastgaelam = [0.,0.]         # 每条回答的优势递推缓存，初始末尾之后的优势为 0
            advs_rev = []               # 按 t=2,1,0 保存优势向量的列表

            2. 为什么从后向前算？
            对当前位置 t，记 V=old_resp_values[:,t]，r=token_rewards[:,t]。
            nv 是下一位置的旧价值；最后一列没有下一列，代码取 0。
            delta = r + gamma*nv - V：用当前奖励和下一状态价值修正原估计（TD 误差）。
            A_t = delta + gamma*lam*A_(t+1)：把后续步骤的误差也传回来，得到 GAE 优势。
            因为当前优势依赖下一位置的优势，所以先算 t=2，再算 t=1，最后算 t=0。
            更新前 lastgaelam 保存 A_(t+1)，更新后保存 A_t。
            下列每个向量的第一个数属于第一条回答，第二个数属于第二条。

            3. t=2：第一条是占位，第二条是 EOS
            r=[0.,2.]，V=[0.,0.5]，nv=0.0，更新前 lastgaelam=[0.,0.]。
            delta = [0.,2.] + 1*0 - [0.,0.5] = [0.,1.5]。
            lastgaelam = [0.,1.5] + 1*0.95*[0.,0.] = [0.,1.5]。
            append 后 advs_rev = [[0.,1.5]]。
            第二条末尾实际奖励 2，比原估计 0.5 多 1.5，因此该步优势为 1.5。

            4. t=1：第一条是 EOS，第二条是 token 32
            r=[1.,0.]，V=[0.4,0.3]，nv=old_resp_values[:,2]=[0.,0.5]。
            delta = [1.,0.] + [0.,0.5] - [0.4,0.3] = [0.6,0.2]。
            lastgaelam = [0.6,0.2] + 0.95*[0.,1.5] = [0.6,1.625]。
            append 后 advs_rev = [[0.,1.5],[0.6,1.625]]。
            第一条末尾优势为 1-0.4=0.6；第二条将 EOS 的优势传回 token 32。

            5. t=0：token 21 和 token 31
            r=[0.,0.]，V=[0.2,0.1]，nv=old_resp_values[:,1]=[0.4,0.3]。
            delta = [0.,0.] + [0.4,0.3] - [0.2,0.1] = [0.2,0.2]。
            lastgaelam = [0.2,0.2] + 0.95*[0.6,1.625] = [0.77,1.74375]。
            append 后 advs_rev = [[0.,1.5],[0.6,1.625],[0.77,1.74375]]。
            虽然两个 token 的直接奖励都是 0，后续奖励传回来，使它们也有训练信号。

            6. 恢复时间顺序，得到优势矩阵与回报矩阵
            advs_rev[::-1] 将倒序 t=2,1,0 变为 t=0,1,2；
            stack(dim=1) 将每个时刻的两条回答向量放成一列：
            advantages = [              # [2,3]，尚未标准化
                [0.77,    0.6,  0.],
                [1.74375,1.625,1.5],
            ]
            returns = advantages + old_resp_values，逐元素相加：
            第一行：[0.77+0.2, 0.6+0.4, 0+0]；
            第二行：[1.74375+0.1, 1.625+0.3, 1.5+0.5]。
            returns = [                 # [2,3]，Critic 要学习的目标回报
                [0.97,    1.0,  0.],
                [1.84375,1.925,2.0],
            ]
            例如第一条开头原估计为 0.2，加上优势修正 0.77，学习目标就是 0.97。
            lambda=0.95 混合了价值估计与后续奖励，returns 不必每列都等于末尾评分。

            7. 只用有效位置计算均值、方差，再标准化 advantages
            目的：把本批有效优势调整为均值约 0、方差约 1，供 Actor 更新使用。
            mask 排除第一条占位，剩下 [0.77,0.6,1.74375,1.625,1.5]，共 5 个值。
            adv_mean = (advantages*mask).sum()/mask.sum()
                     = (0.77+0.6+1.74375+1.625+1.5)/5 = 1.24775。
            adv_var 是这 5 个值与均值之差的平方的平均值：
                    = ((0.77-1.24775)^2 + (0.6-1.24775)^2
                       + (1.74375-1.24775)^2 + (1.625-1.24775)^2
                       + (1.5-1.24775)^2)/5 = 0.21995775。
            每个优势减均值，再除以 sqrt(adv_var+1e-8)，最后乘 mask：
            advantages 最终约为 [
                [-1.01866,-1.38114,0.],
                [ 1.05758, 0.80438,0.53785],
            ]。
            rsqrt(x)=1/sqrt(x)；1e-8 防止方差为 0 时除以 0，
            mask.sum().clamp(min=1) 防止全无效时计算均值、方差的分母为 0。
            标准化后的负数表示低于本批优势的平均水平，不代表外部评分为负。
            占位最后乘 mask 变为 0；returns 在标准化前已经创建，其数值保持不变。
            '''
            gen_len = old_resp_values.size(1)
            lastgaelam = torch.zeros(B, device=args.device)
            advs_rev = []
            for t in reversed(range(gen_len)):
                nv = old_resp_values[:, t + 1] if t < gen_len - 1 else 0.0
                delta = token_rewards[:, t] + args.gamma * nv - old_resp_values[:, t]
                lastgaelam = delta + args.gamma * args.lam * lastgaelam
                advs_rev.append(lastgaelam)
            advantages = torch.stack(advs_rev[::-1], dim=1)
            returns = advantages + old_resp_values # 这个是 Critic 要学习的目标回报，也就是以后训练的时候，期待 Critic 应该预测的回报
            adv_mean = (advantages * resp_policy_mask).sum() / resp_policy_mask.sum().clamp(min=1)
            adv_var = ((advantages - adv_mean) ** 2 * resp_policy_mask).sum() / resp_policy_mask.sum().clamp(min=1)
            advantages = (advantages - adv_mean) * torch.rsqrt(adv_var + 1e-8) * resp_policy_mask
        # 5、update阶段：用同一批已生成回答，反复训练 Actor 和 Critic 几轮，但限制每次更新不能变化太大。
        '''
        【完整示例：用同一批回答更新 Actor 和 Critic】
        结论：回答已经生成，不再重新采样。当前 Actor 重新计算这些 token 的概率，
        与采样时的旧概率比较，算出 PPO 策略损失；当前 Critic 重新预测价值，
        与固定 returns 比较，算出价值损失。两种损失反传，再由各自优化器更新参数。
        下面沿着执行顺序推导一个完整例子。模型前向数值是假设输入，不是由 token ID 手算得到。

        1. 本批数据及参数
        B=2，gen_out=[[0,11,12,21,2,2],[13,14,15,31,32,2]]。
        full_mask=[[0,1,1,1,1,1],[1,1,1,1,1,1]]。
        labels=[[11,12,21,2,2],[14,15,31,32,2]]，logp_pos=[[2,3,4],[2,3,4]]。
        old_resp_values=[[0.2,0.4,0],[0.1,0.3,0.5]]。
        returns=[[0.97,1.0,0],[1.84375,1.925,2.0]]，是前面 GAE 算好的固定 Critic 目标。
        advantages≈[[-1.01866,-1.38114,0],[1.05758,0.80438,0.53785]]，已标准化。
        resp_policy_mask=resp_value_mask=[[1,1,0],[1,1,1]]。
        假设采样旧策略与参考策略的回答 logp 均为：
        old_resp_logp=ref_resp_logp=[[-1,-1,-1],[-1,-1,-1]]。
        args.mini_batch_size=1，ppo_update_iters=1，accumulation_steps=2，
        clip_epsilon=0.2，cliprange_value=0.2，kl_coef=0.02，vf_coef=0.5，
        early_stop_kl=0.25，grad_clip=1，debug_log_ratio=True，use_moe=False。
        本例单卡、主进程，grad_accum_step 初始为 0，优化器梯度初始为空。

        2. 初始化与切分样本
        mb_size=max(1,min(1,2))=1：每次前向只处理一条回答。
        stop_ppo=False：暂不早停。
        policy_loss_sum=value_loss_sum=kl_sum=kl_ref_sum=clipfrac_sum=aux_loss_sum=0.0：
        分别累计策略损失、价值损失、新旧策略偏离、参考策略偏离、裁剪比例和辅助损失的日志数值。
        log_count=0：已统计 mini-batch 的次数，用于最后求日志平均值。
        actor_unwrapped、critic_unwrapped：单卡直接引用当前模型；DDP 时取 .module，
        它们共享原模型参数，并不是复制或冻结的模型。
        for ppo_epoch in range(1)：只执行 ppo_epoch=0。
        if stop_ppo: break：本例 False，所以继续。
        b_inds=randperm(2)：假设结果 [1,0]，只打乱样本，不打乱回答内部 token。
        for i in range(0,2,1)：先 i=0，再 i=1。
        inds=b_inds[i:i+1]：第一次 inds=[1]，第二次 inds=[0]。
        所有数据都使用同一个 inds，确保回答、旧概率、优势、回报和掩码属于同一条样本。

        3. 第一次 mini-batch：inds=[1]，处理第二条回答 [31,32,EOS]
        mb_values_seq=critic_unwrapped(gen_out[inds],full_mask[inds])：
        输入完整序列 [[13,14,15,31,32,2]]，假设当前 Critic 输出 [[0,0,0.2,0.4,0.6,0]]。
        mb_resp_values=mb_values_seq.gather(1,logp_pos[inds])：
        取第 2、3、4 列，得到 [[0.2,0.4,0.6]]，表示生成各回答 token 前的当前价值。
        这次前向保留梯度，后面才能训练 Critic。

        with autocast_ctx：使用配置的混合精度上下文，仍保留梯度。
        res=actor_unwrapped(...)：当前 Actor 评估完整序列，返回 logits，形状 [1,6,V]，
        V 是词表大小；这里是 forward，不是 generate。
        aux_loss=0：本例未开启 MoE；开启时用 res.aux_loss 作为路由辅助损失。
        mb_resp_logp 的连续操作：
        res.logits[:,:-1] -> [1,5,V]，去掉没有下一 token 标签的末尾预测；
        log_softmax(dim=-1) -> 每个位置词表上各 token 的 log 概率；
        gather(2,labels[inds].unsqueeze(-1)) -> 取真实下一 token 的 log 概率；
        squeeze(-1) -> [1,5]；gather(1,[[2,3,4]]) -> 只取三个回答 token 的 log 概率。
        假设结果 mb_resp_logp=[[-0.737635736,-1,-1]]。
        exp(-0.737635736)≈0.47824，exp(-1)≈0.36788，第一位置新概率是旧概率的 1.3 倍。

        4. 新旧概率变化、诊断与早停
        log_ratio=mb_resp_logp-old_resp_logp[inds]=[[ln(1.3),0,0]]≈[[0.262364264,0,0]]。
        首轮首个 mini-batch 满足 debug 分支：
        _lr=log_ratio.detach()：取不参与反传的诊断数据；
        _m=mask.bool()=[[True,True,True]]，_m.any()=True；
        _lrv=_lr[_m]=[0.262364264,0,0]：只统计有效位置。
        Logger 输出 max|lr|≈0.262364、mean|lr|≈0.087455、ratio_max=1.3、ratio_min=1，
        并输出当前模型的 dropout 与 training 状态。
        approx_kl=(0.5*log_ratio^2*mask).sum()/mask.sum()
                 =0.5*(ln(1.3)^2+0+0)/3≈0.01147250。
        它是当前策略相对采样旧策略的偏离诊断，数值越大代表本次变化越大。
        approx_kl_val=approx_kl.detach().clone()：独立副本，用于早停和日志。
        dist.is_initialized()=False：本例跳过通信；多卡则 all_reduce(AVG)，统一早停依据。
        if approx_kl_val>0.25：不成立，因此 stop_ppo 仍为 False。

        5. 计算 Actor 的策略损失（仍是同一个 mini-batch）
        ratio=exp(log_ratio)=[[1.3,1,1]]：每个已采样 token 的新概率/旧概率。
        clipfrac：判断 abs(ratio-1)>0.2 得 [True,False,False]，
        乘 mask 再平均，clipfrac=1/3≈0.333333，表示三分之一有效位置超出裁剪范围。
        d=ref_resp_logp[inds]-mb_resp_logp=[-ln(1.3),0,0]。
        kl_ref_penalty=mean(exp(d)-d-1)
                      =(1/1.3+ln(1.3)-1)/3≈0.01053168。
        它约束当前 Actor 相对固定参考模型的偏离，与上面比较采样旧策略的 approx_kl 用途不同。
        policy_loss 的裁剪计算，使用优势 [1.05758,0.80438,0.53785]：
        原负目标 -A*ratio=[-1.374854,-0.80438,-0.53785]；
        clamp(ratio,0.8,1.2)=[1.2,1,1]，裁剪负目标=[-1.269096,-0.80438,-0.53785]；
        逐项 max 取较大者，再按有效位置平均：
        (-1.269096-0.80438-0.53785)/3≈-0.870442。
        加参考惩罚 0.02*0.01053168≈0.00021063，policy_loss≈-0.87023137。
        最小化这个负目标等价于提高收益；损失可以为负。裁剪限制损失的激励，
        并不是强制把模型的真实 ratio 改成 [0.8,1.2] 内的数。

        6. 计算 Critic 的价值损失
        当前价值=[0.2,0.4,0.6]，旧价值=[0.1,0.3,0.5]，目标=[1.84375,1.925,2.0]。
        当前价值都在旧价值±0.2 的区间内，因此 clamp 后仍为 [0.2,0.4,0.6]。
        两条误差分支相同，max 结果就是当前误差平方：
        value_loss=0.5*((0.2-1.84375)^2+(0.4-1.925)^2+(0.6-2)^2)/3
                  =1.16458984375。
        若当前价值超过裁剪区间，则要比较原预测和裁剪预测的误差平方，取较大者。
        kl=approx_kl_val；kl_ref=kl_ref_penalty.detach()：用于日志记录。

        7. 总损失、反传与第一次梯度累积
        stop_ppo=False，因此 loss=(policy_loss+0.5*value_loss+aux_loss)/2
                                      ≈(-0.87023137+0.58229492)/2=-0.14396822。
        除 2 是因为希望两个 mini-batch 的梯度累积后形成平均贡献。
        loss.backward()：计算并累加 Actor、Critic 参数的梯度，此时还没有更新参数。
        *_sum += 对应指标.item()：取 Python 数值累加日志，不保留这些日志的计算图。
        此时各累计量为 -0.87023137、1.16458984、0.01147250、0.01053168、1/3、0。
        log_count 从 0 到 1，grad_accum_step 从 0 到 1。
        1%2!=0，所以暂不执行优化器更新，梯度保留到下一次 backward。

        8. 第二次 mini-batch：inds=[0]，处理第一条回答 [21,EOS,EOS占位]
        为说明累积流程，假设本次 Actor 回答 logp=[-1,-1,-1]，Critic 取出的价值=[0.2,0.4,0]。
        此时 log_ratio=[0,0,0]，ratio=[1,1,1]，approx_kl=kl_ref_penalty=clipfrac=0。
        i=1 不进入首个 mini-batch 的 debug 分支。
        mask=[1,1,0]，只使用前两列；第三列占位不计入损失或统计。
        policy_loss=(-(-1.01866)-(-1.38114))/2=1.1999。
        value_loss=0.5*((0.2-0.97)^2+(0.4-1.0)^2)/2=0.238225。
        loss=(1.1999+0.5*0.238225)/2=0.65950625。
        backward 将这次梯度加到上次梯度上，log_count=2，grad_accum_step=2。
        日志累计：policy_loss_sum≈0.32966863，value_loss_sum≈1.40281484，
        kl_sum≈0.01147250，kl_ref_sum≈0.01053168，clipfrac_sum≈0.333333，aux_loss_sum=0。
        后续按 log_count=2 求日志平均；这是 mini-batch 平均，不是重新按总 token 数加权。

        9. 累积满两次，实际更新参数
        if grad_accum_step%2==0：2%2=0，进入更新分支。
        clip_grad_norm_(actor_model.parameters(),1)：限制 Actor 的累计梯度整体范数；
        clip_grad_norm_(critic_model.parameters(),1)：单独限制 Critic 的梯度范数。
        例如 Actor 范数为 2，会大约缩小一半；Critic 范数为 0.6，则基本不缩放。
        actor_optimizer.step()、critic_optimizer.step()：分别用梯度更新各自参数。
        具体参数变化还依赖网络导数、学习率、优化器动量与权重衰减，不能仅由损失数值推出。
        actor_scheduler.step()、critic_scheduler.step()：各推进一次学习率计划，供下次更新使用。
        actor_optimizer.zero_grad()、critic_optimizer.zero_grad()：清除已用过的梯度，开始新的累积窗口。
        grad_accum_step 仍为 2，代码不在这里把计数器归零。

        10. 同一流程的早停分支
        若某次 approx_kl_val>early_stop_kl，则设置 stop_ppo=True。
        当次和本轮后续 mini-batch 将总损失乘 0，但仍执行 backward 和统计；
        到下一次 ppo_epoch 开头才 break，不是在阈值判断处立即跳出 mini-batch 循环。
        乘 0 只使本次梯度贡献为零；已有累计梯度、优化器动量和权重衰减仍可能使 step 改变参数。
        '''
        mb_size = max(1, min(args.mini_batch_size, B))
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
            if stop_ppo:
                break
            b_inds = torch.randperm(B, device=args.device)
            for i in range(0, B, mb_size):
                inds = b_inds[i:i + mb_size]
                mb_values_seq = critic_unwrapped(input_ids=gen_out[inds], attention_mask=full_mask[inds]) # 需要注意的是从上面的for循环开始这个critic就已经是训练过的了，所以这里的mb_values_seq是训练过的critic的输出，和上面计算advantages时的old_resp_values是不同的；同理，下面的mb_resp_logp也是训练过的actor的输出，和上面计算log_ratio时的old_resp_logp是不同的
                mb_resp_values = mb_values_seq.gather(1, logp_pos[inds]) # 新Critic的value
                with autocast_ctx:
                    res = actor_unwrapped(input_ids=gen_out[inds], attention_mask=full_mask[inds])
                    aux_loss = res.aux_loss if lm_config.use_moe else torch.tensor(0.0, device=args.device)
                    mb_resp_logp = F.log_softmax(res.logits[:, :-1], dim=-1).gather(2, labels[inds].unsqueeze(-1)).squeeze(-1).gather(1, logp_pos[inds]) # 新Actor的logp
                log_ratio = mb_resp_logp - old_resp_logp[inds]
                if args.debug_log_ratio and ppo_epoch == 0 and i == 0 and is_main_process():
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
                approx_kl = (0.5 * (log_ratio ** 2) * resp_policy_mask[inds]).sum() / resp_policy_mask[inds].sum().clamp(min=1)
                approx_kl_val = approx_kl.detach().clone()
                if dist.is_initialized():
                    dist.all_reduce(approx_kl_val, op=dist.ReduceOp.AVG)
                if approx_kl_val > args.early_stop_kl:
                    stop_ppo = True
                ratio = torch.exp(log_ratio)
                clipfrac = ((((ratio - 1.0).abs() > args.clip_epsilon).float() * resp_policy_mask[inds]).sum()
                            / resp_policy_mask[inds].sum().clamp(min=1)) # 用于统计的指标 看22讲义的29条
                kl_ref_penalty = ((torch.exp(ref_resp_logp[inds] - mb_resp_logp) - (ref_resp_logp[inds] - mb_resp_logp) - 1.0) # kl divergence penalty from the reference model，看19讲义的45条：Reference KL Penalty
                                  * resp_policy_mask[inds]).sum() / resp_policy_mask[inds].sum().clamp(min=1)
                '''
                【policy_loss：对有效回答 Token 求经验平均，用来估计 PPO 公式中的期望】
                
                1. 对应的公式是什么？
                   PPO 要最大化：
                       E_t[min(ratio_t * A_t, clip(ratio_t, 1-eps, 1+eps) * A_t)]
                
                   优化器执行梯度下降，所以代码最小化它的负数，并加入参考 KL 惩罚：
                       policy_loss
                       = 有效 Token 上的平均 {-min(ratio * A, clip(ratio) * A)}
                         + kl_coef * kl_ref_penalty
                
                   因为 -min(x, y) = max(-x, -y)，所以这里写成 torch.max。
                   torch.max 在这里逐元素比较两个张量，不是在整条回答中只挑一个最大值。
                
                2. “期望”具体是怎样算出来的？
                   当前 mini-batch 是旧 Policy 采样数据的一部分，inds 选出其中的 sample。
                   这行代码对它们的有效回答 Token 求平均，得到 E_t 的有限样本估计。
                   它不是精确枚举所有可能轨迹后算出的理论期望，而是这批样本的经验平均。
                
                   假设当前 mini-batch 有两条 sample，回答补齐后的宽度都是 3：
                       advantages[inds] = [
                           [ 2.0, -1.0, 0.0],
                           [ 1.0, -2.0, 0.5],
                       ]
                       ratio = [
                           [1.5, 0.6, 1.0],
                           [0.9, 1.4, 1.1],
                       ]
                       ⭐️resp_policy_mask[inds] = [
                           [1., 1., 0.],   # sample 0 的最后一列是补齐位置
                           [1., 1., 1.],
                       ]
                
                   以下是便于手算的示例数值。advantages 已经提前算好，在本批更新中固定；
                   ratio 由当前 Actor 的新 logp 与保存的 old logp 计算，每次 Forward 重算。
                
                3. 先逐 Token 算 PPO Clip Loss。
                   取 clip_epsilon = 0.2，把 ratio 裁剪到 [0.8, 1.2]：
                       clipped_ratio = [
                           [1.2, 0.8, 1.0],
                           [0.9, 1.2, 1.1],
                       ]
                
                   原始分支 -A * ratio：
                       [
                           [-3.0,  0.6, 0.0],
                           [-0.9,  2.8, -0.55],
                       ]
                
                   裁剪分支 -A * clipped_ratio：
                       [
                           [-2.4,  0.8, 0.0],
                           [-0.9,  2.4, -0.55],
                       ]
                
                   torch.max 逐元素取两者中较大的损失：
                       token_loss = [
                           [-2.4,  0.8, 0.0],
                           [-0.9,  2.8, -0.55],
                       ]
                
                   例如 A=2、ratio=1.5，取 max(-3.0, -2.4)=-2.4；
                   A=-2、ratio=1.4，取 max(2.8, 2.4)=2.8。
                   因此正、负 Advantage 都要按两条分支比较，不能直接把所有 ratio 裁剪后相乘。
                
                4. 乘 mask，再除以有效 Token 数，就是这里的经验平均。
                   mask 为 0 的补齐位置不贡献分子，也不计入分母；Prompt 不在这个回答损失区域中。
                       ⭐️分子 = -2.4 + 0.8 + (-0.9) + 2.8 + (-0.55) = -0.25
                       ⭐️分母 = resp_policy_mask[inds].sum() = 2 + 3 = 5
                       平均 Clip Loss = -0.25 / 5 = -0.05
                
                   所以它是“所有有效 Token 等权”的平均，不是先对两条 sample 各求平均再除以 2。
                   两条回答长度不同：这里 sample 0 占 2/5，sample 1 占 3/5。
                   clamp(min=1) 用于避免没有有效 Token 时除以 0，不改变本例分母 5。
                
                5. 最后加上已经求过有效 Token 平均的参考 KL 惩罚。
                   假设上一行计算的 kl_ref_penalty=0.1，kl_coef=0.02：
                       policy_loss = -0.05 + 0.02 * 0.1 = -0.048
                
                   kl_ref_penalty 本身已经是平均值，不需要再除以 5。
                   这行最终得到一个标量 Actor 损失；值为负是允许的。
                   后面还会合并 Value Loss 等项，再 backward() 求梯度、optimizer.step() 更新参数。
                
                结论：这里用当前 mini-batch 的有效回答 Token 经验平均来估计 PPO 目标中的期望，
                      再加参考 KL 惩罚。它是 Actor 的 policy_loss，还不是包含 Critic 的最终总 loss。
                '''
                policy_loss = ((torch.max(-advantages[inds] * ratio,
                                          -advantages[inds] * torch.clamp(ratio, 1.0 - args.clip_epsilon, 1.0 + args.clip_epsilon))
                               * resp_policy_mask[inds]).sum() / resp_policy_mask[inds].sum().clamp(min=1)
                               + args.kl_coef * kl_ref_penalty)
                value_loss = 0.5 * (torch.max((mb_resp_values - returns[inds]) ** 2,
                                              (torch.clamp(mb_resp_values, old_resp_values[inds] - args.cliprange_value,
                                                           old_resp_values[inds] + args.cliprange_value) - returns[inds]) ** 2)
                                    * resp_value_mask[inds]).sum() / resp_value_mask[inds].sum().clamp(min=1)
                kl = approx_kl_val
                kl_ref = kl_ref_penalty.detach()
                if stop_ppo:
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
                # 注意更新频率，每个mini-batch都累积梯度，只有当累积次数达到accumulation_steps时才更新参数。
                # 更新次数受到args.ppo_update_iters、B/args.mini_batch_size和args.accumulation_steps的共同影响。
                if grad_accum_step % args.accumulation_steps == 0:
                    clip_grad_norm_(actor_model.parameters(), args.grad_clip)
                    clip_grad_norm_(critic_model.parameters(), args.grad_clip)
                    actor_optimizer.step()
                    critic_optimizer.step()
                    actor_scheduler.step()
                    critic_scheduler.step()
                    actor_optimizer.zero_grad()
                    critic_optimizer.zero_grad()

        '''
        【语句示例：if grad_accum_step % args.accumulation_steps != 0:】
        输入 accumulation_steps=2、grad_accum_step=3。余数 1 非零，执行一次尾部更新，处理尚未提交的梯度。
        实际代码在每个 rollout 批次末尾检查，且尾部更新后不把 grad_accum_step 归零。
        因此跨批时计数与清空后的梯度窗口可能不完全对齐；尾部 loss 仍除原 accumulation_steps，未按不足窗口重新缩放。
        这里如实说明现有行为，不把它说成已修正的梯度累积实现；默认 accumulation_steps=1 不进入此分支。
        '''
        if grad_accum_step % args.accumulation_steps != 0:
            '''
            【语句示例：clip_grad_norm_(actor_model.parameters(), args.grad_clip)】
            输入 Actor 的已累计梯度，假设整体 L2 范数为 2、grad_clip=1。按约 1/2 的比例缩小全部梯度，限制范数；不修改 Actor 参数值，参数更新由下一句 optimizer.step 完成。
            '''
            clip_grad_norm_(actor_model.parameters(), args.grad_clip)
            '''
            【语句示例：clip_grad_norm_(critic_model.parameters(), args.grad_clip)】
            输入 Critic 的已累计梯度，假设整体范数 0.6、grad_clip=1。因为未超阈值，基本不缩放；Critic 与 Actor 分别裁剪，不将两者梯度混成一个范数。
            '''
            clip_grad_norm_(critic_model.parameters(), args.grad_clip)
            '''
            【语句示例：actor_optimizer.step()】
            输入 Actor 参数、当前 .grad 和 AdamW 的历史动量。step 更新 Actor 权重；例如某个参数的变化由梯度、学习率、动量及权重衰减共同决定，不能只用一项奖励推断。这里不清空梯度。
            '''
            actor_optimizer.step()
            '''
            【语句示例：critic_optimizer.step()】
            输入 Critic 参数及价值损失梯度。critic_optimizer.step 更新其参数，让价值预测向固定 returns 的回归目标学习；不更新外部奖励模型。
            '''
            critic_optimizer.step()
            '''
            【语句示例：actor_scheduler.step()】
            输入 Actor 调度器已推进 9 次。本次 step 推进到第 10 次，根据主入口的余弦曲线设置优化器学习率，供下一次参数更新使用；不是按 token 数或 rollout 条数推进。
            '''
            actor_scheduler.step()
            '''
            【语句示例：critic_scheduler.step()】
            输入 Critic 学习率调度器。推进一次自己的余弦计划；它可以和 Actor 有不同初始学习率，例如 5e-7 与 3e-7，不会共享同一优化器。
            '''
            critic_scheduler.step()
            '''
            【语句示例：actor_optimizer.zero_grad()】
            输入 Actor 刚用于 step 的累计 .grad。zero_grad 清除旧梯度，下一次 backward 从新的累积窗口开始；没有在此处重置 grad_accum_step 计数器。
            '''
            actor_optimizer.zero_grad()
            '''
            【语句示例：critic_optimizer.zero_grad()】
            输入 Critic 刚用过的梯度。zero_grad 清除，避免下一轮继续叠加已用于更新的梯度；网络参数和优化器动量仍保留。
            '''
            critic_optimizer.zero_grad()
        
        '''
        【语句示例：if step % args.save_interval == 0 or step == iters:】
        输入 save_interval=10。step=10 或 step==iters 时满足条件，下面让采样引擎使用当前 Actor；step=3 且不是末批则跳过这个显式同步调用。
        '''
        if step % args.save_interval == 0 or step == iters:
            '''
            【语句示例：rollout_engine.update_policy(actor_model)】
            输入更新后的 actor_model。torch 后端 update_policy 设置策略对象引用；SGLang 后端导出并通知服务更新。它不是重新生成本批数据。本地后端可能一直共享同一个参数对象，因此不应说跳过调用就必然仍在使用旧权重。
            '''
            rollout_engine.update_policy(actor_model)

        '''
        【语句示例：if is_main_process():】
        输入单进程时 is_main_process()=True，进入汇总打印；分布式通常只有 rank 0 进入。下面这些均值主要来自本 rank 的统计，并没有对所有指标做全局样本加权归约。
        '''
        if is_main_process():
            '''
            【语句示例：critic_loss_val】
            输入 value_loss_sum=0.8、log_count=2。critic_loss_val=0.4；若 count=0，max(...,1) 防止除零。这是 mini-batch 指标的平均，不按每批 token 数重新加权。
            '''
            critic_loss_val = value_loss_sum / max(log_count, 1)
            '''
            【语句示例：reward_val】
            输入 rewards=[1,2]。mean=1.5，再 item() 转成 Python 数 reward_val=1.5，用于本批采样质量日志。
            '''
            reward_val = rewards.mean().item()
            '''
            【语句示例：approx_kl_val】
            输入 kl_sum=0.04、log_count=2，得到 approx_kl_val=0.02。这里变量被重新赋为日志均值，不再是某次 early-stop 判断使用的张量。
            '''
            approx_kl_val = kl_sum / max(log_count, 1)
            '''
            【语句示例：kl_ref_val】
            输入 kl_ref_sum=0.01、log_count=2，得到 kl_ref_val=0.005，表示记录的参考策略偏离指标均值。
            '''
            kl_ref_val = kl_ref_sum / max(log_count, 1)
            '''
            【语句示例：clipfrac_val】
            输入 clipfrac_sum=1.0、log_count=2，得到 clipfrac_val=0.5；表示记录的裁剪比例平均值，不是把所有 token 重新合并统计。
            '''
            clipfrac_val = clipfrac_sum / max(log_count, 1)
            '''
            【语句示例：avg_len_val】
            输入 resp_lengths=[2,3]。先转 float，再 mean 和 item，得到 avg_len_val=2.5；此处长度包括第一个 EOS，和 debug 打印的字符数不同。
            '''
            avg_len_val = resp_lengths.float().mean().item()
            '''
            【语句示例：(actor_lr, critic_lr)】
            输入 Actor 优化器第 0 组 lr=3e-7、Critic 第 0 组 lr=5e-7。分别读出 actor_lr、critic_lr；若调度器已推进，读到的就是调度后的当前值。
            '''
            actor_lr, critic_lr = actor_optimizer.param_groups[0]['lr'], critic_optimizer.param_groups[0]['lr']

            '''
            【语句示例：if wandb is not None:】
            输入 wandb=None 时跳过远程指标记录；若主入口已初始化兼容的 swanlab/wandb 对象则进入。名字叫 wandb 不代表此处一定导入官方 wandb 包。
            '''
            if wandb is not None:
                '''
                【语句示例：wandb.log({'reward': reward_val, 'kl_ref': kl_ref_val, 'approx_kl': approx_kl_val, 'clipfrac': clipfrac_val, '】
                输入本批 reward_val=1.5、critic_loss_val=0.4、avg_len_val=2.5 等。构造指标字典并调用 log，提交一次记录；不把完整生成文本或模型参数放进这个字典。
                '''
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

            '''
            【语句示例：Logger(f'Epoch:[{epoch + 1}/{args.epochs}]({step}/{iters}), Reward: {reward_val:.4f}, KL_ref: {kl_ref_val:.4f}】
            输入 epoch=0、args.epochs=1、step=10、iters=100，打印 Epoch:[1/1](10/100) 及奖励/KL/长度/学习率。epoch+1 只为显示从 1 开始，不改变训练循环索引。
            '''
            Logger(f"Epoch:[{epoch + 1}/{args.epochs}]({step}/{iters}), "
                   f"Reward: {reward_val:.4f}, KL_ref: {kl_ref_val:.4f}, Approx KL: {approx_kl_val:.4f}, "
                   f"ClipFrac: {clipfrac_val:.4f}, Critic Loss: {critic_loss_val:.4f}, "
                   f"Avg Response Len: {avg_len_val:.2f}, Actor LR: {actor_lr:.8f}, Critic LR: {critic_lr:.8f}")

        '''
        【语句示例：if (step % args.save_interval == 0 or step == iters) and is_main_process():】
        输入 save_interval=10、step=10 且主进程，进入保存；若非主进程则不写文件，避免多个进程覆盖同一路径。最后 step==iters 也会保存。
        '''
        if (step % args.save_interval == 0 or step == iters) and is_main_process():
            '''
            【语句示例：actor_model.eval()】
            输入训练模式的 Actor。eval() 切换为评估行为，例如关闭 Dropout；保存参数本身不需要做前向，此处主要改变模式标志，保存后会 train() 恢复。
            '''
            actor_model.eval()
            '''
            【语句示例：moe_suffix】
            输入 lm_config.use_moe=True 得 moe_suffix="_moe"；False 得空字符串。后面据此区分两类默认文件名。
            '''
            moe_suffix = '_moe' if lm_config.use_moe else ''
            '''
            【语句示例：ckp】
            输入 save_dir="../out"、save_weight="ppo_actor"、hidden_size=768、moe_suffix=""。拼出 ckp="../out/ppo_actor_768.pth"；MoE 时文件名含 _moe。
            '''
            ckp = f'{args.save_dir}/{args.save_weight}_{lm_config.hidden_size}{moe_suffix}.pth'
            '''
            【语句示例：raw_actor】
            输入可能包着 DDP 的 Actor。取 .module 或自身，得到 raw_actor，避免导出权重键带不必要的 DDP 前缀。
            '''
            raw_actor = actor_model.module if isinstance(actor_model, DistributedDataParallel) else actor_model
            '''
            【语句示例：raw_actor】
            输入 raw_actor 若为 torch.compile 包装，getattr 找到 _orig_mod 并取出原网络；没有该字段则保留自身。这是解除包装引用，不是复制或重新初始化参数。
            '''
            raw_actor = getattr(raw_actor, '_orig_mod', raw_actor)
            '''
            【语句示例：actor_state】
            输入原始 Actor。state_dict 返回参数和持久化缓冲区的映射，例如包含 model.embed_tokens.weight 和 lm_head.weight；它不是一批训练数据，也不含优化器动量。
            '''
            actor_state = raw_actor.state_dict()
            # PyTorch：save 将对象序列化；这里保存 state_dict 等状态，恢复时仍需用匹配的模型配置构建网络。
            '''
            【语句示例：torch.save({k: v.half().cpu() for k, v in actor_state.items()}, ckp)】
            输入一个 FP32 参数张量，例如 [0.123456,0.5]。half() 转 FP16 可能产生舍入，cpu() 转 CPU，按原键名打包保存到 ckp。训练中 Actor 本身并未被整体转成 FP16 或 CPU。
            '''
            torch.save({k: v.half().cpu() for k, v in actor_state.items()}, ckp)
            
            # 使用 lm_checkpoint 保存完整状态（包括 critic）
            '''
            【语句示例：lm_checkpoint(lm_config, weight=args.save_weight, model=actor_model, optimizer=actor_optimizer, epoch=epoch, s】
            输入当前 Actor/Critic、两个优化器、两个调度器，以及 epoch=0、step=10。lm_checkpoint 写 ../checkpoints 下的权重和续训状态，包含传入的 Critic 等额外状态；不同于上一句只导出 Actor state_dict。
            '''
            lm_checkpoint(lm_config, weight=args.save_weight, model=actor_model, optimizer=actor_optimizer, 
                         epoch=epoch, step=step, wandb=wandb, save_dir='../checkpoints',
                         scheduler=actor_scheduler, critic_model=critic_model, 
                         critic_optimizer=critic_optimizer, critic_scheduler=critic_scheduler)
            '''
            【语句示例：actor_model.train()】
            输入保存后的 Actor 当前处于 eval。train() 恢复训练模式，供下一批使用；不会重建优化器或重置已经学到的参数。
            '''
            actor_model.train()
            '''
            【语句示例：del actor_state】
            输入 actor_state 这个局部映射引用。del 删除引用，方便释放导出相关临时对象；不会删除磁盘检查点，也不会删除 raw_actor 的实际参数。
            '''
            del actor_state

        '''
        【语句示例：del enc, gen_out, completion_ids, responses_text, rewards, full_mask, values_seq, advantages】
        输入本批编码、完整生成序列、奖励和优势等局部变量。del 清掉这些名字的引用；无其他引用的张量存储可被回收，CUDA 分配器仍可能缓存显存，不保证系统监视器立刻显示显存下降。
        '''
        del enc, gen_out, completion_ids, responses_text, rewards, full_mask, values_seq, advantages
        '''
        【语句示例：del labels, resp_labels, resp_idx, resp_pad_mask, valid_resp, eos_mask, has_eos, eos_pos, resp_lengths, resp_p】
        输入本批标签、位置索引、掩码、旧/参考 logp 等中间对象。删除这些局部引用，让下一个 rollout 批次重新建立它们；没有删除 tokenizer 或模型。
        '''
        del labels, resp_labels, resp_idx, resp_pad_mask, valid_resp, eos_mask, has_eos, eos_pos, resp_lengths, resp_policy_mask, resp_value_mask, old_resp_logp, ref_resp_logp
        '''
        【语句示例：del kl, kl_ref, policy_loss, value_loss, loss, token_rewards, returns, old_resp_values, prompt_lens, logp_pos】
        输入本批损失、回报、旧价值及位置索引。删除局部引用，结束当前批次的收尾；函数走完所有 loader 批次后隐式返回 None。
        '''
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
    # 示例输出：{"prompt": P, "answer": ""}，其中 P 的完整内容是：
    #         <|im_start|>system
    #         请简短回答。<|im_end|>
    #         <|im_start|>user
    #         1+1等于几？<|im_end|>
    #         <|im_start|>assistant
    #         <think>
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
