# 数据入口：将 JSONL 文本/对话转换为预训练、SFT、DPO 或在线强化学习样本。
# 注意：预训练/SFT 返回未移位标签，由模型移位；DPO 在数据集内完成 x/y 移位。
# 将原始文本、对话或偏好数据转换成各训练阶段需要的样本。
# Pretrain / SFT 返回 token 张量和标签；DPO 返回偏好对及掩码；
# RLAIF / AgentRL 返回生成所需的提示词或消息，由训练端继续处理。
from torch.utils.data import Dataset
import torch
import json
import os
import random
from datasets import load_dataset, Features, Sequence, Value
# 关闭 tokenizer 内部的并行处理，避免与数据加载进程的并行机制叠加。
# 关闭 tokenizer 自身线程并行，减少与 DataLoader 多进程同时使用时的资源争用。
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# 按概率补充 system 消息；带工具定义的对话保持其原有系统上下文。
def pre_processing_chat(conversations, add_system_ratio=0.2):
    # conversations 是非空的消息列表，每条消息包含 role、content 等字段。
    # tool use 数据完整保留不做处理
    if any(conv.get('tools') for conv in conversations): return conversations

    # 为普通对话准备多种中英文系统提示词，增加训练时的提示词多样性。
    SYSTEM_PROMPTS = [
        "你是一个知识丰富的AI，尽力为用户提供准确的信息。",
        "你是minimind，一个小巧但有用的语言模型。",
        "你是一个专业的AI助手，请提供有价值的回答。",
        "你是minimind，请尽力帮助用户解决问题。",
        "你是一个可靠的AI，请给出准确的回答。",
        "You are a helpful AI assistant.",
        "You are minimind, a lightweight intelligent assistant.",
        "You are a friendly chatbot. Please answer the user's questions carefully.",
        "You are a knowledgeable AI. Try your best to provide accurate information.",
        "You are minimind, a small but useful language model."
    ]
    # 首条消息不是 system 时，按 add_system_ratio 的概率补充一条。
    # 列表拼接产生新列表，不直接向原始 conversations 中插入消息。
    if conversations[0].get('role') != 'system':
        if random.random() < add_system_ratio:
            return [{'role': 'system', 'content': random.choice(SYSTEM_PROMPTS)}] + conversations
    return conversations

# 按概率保留空 think 块，为普通回答构造带/不带空思考标签的训练样本。
def post_processing_chat(prompt_content, empty_think_ratio=0.2):
    # empty_think_ratio 控制空思考块的保留概率；这里只匹配下方的固定格式。
    # 默认以 80% 的概率移除空思考标签；有实际思考内容的块不受影响。
    if '<think>\n\n</think>\n\n' in prompt_content and random.random() > empty_think_ratio:
        prompt_content = prompt_content.replace('<think>\n\n</think>\n\n', '')
    return prompt_content

# 预训练：每条样本包含 text 字段，学习根据已有文本预测下一个 token。
# 读取 text 样本并补 BOS/EOS/PAD，返回固定长度的一维 input_ids 和 labels。
class PretrainDataset(Dataset):
    # 记录 tokenizer/最大长度，并通过 datasets 加载 JSON 文本样本。
    def __init__(self, data_path, tokenizer, max_length=512):
        super().__init__()
        self.tokenizer = tokenizer
        self.max_length = max_length
        # 通过 Hugging Face Datasets 读取 JSON / JSONL，并作为训练集访问。
        self.samples = load_dataset('json', data_files=data_path, split='train')

    # 返回数据集样本数量，供 len(dataset)、采样器和 DataLoader 使用。
    def __len__(self):  # 样本条数，不是单条文本的 token 数
        return len(self.samples)

    # 读取一条 text，截断并补齐到 max_length，复制标签后屏蔽 PAD；返回两个 [T] LongTensor。
    def __getitem__(self, index):  # 取出第 index 条 JSON 数据
        sample = self.samples[index]
        # 编码正文，预留两个位置给 BOS / EOS；关闭 tokenizer 自动添加特殊标记。
        tokens = self.tokenizer(str(sample['text']), add_special_tokens=False, max_length=self.max_length - 2, truncation=True).input_ids
        # 补bos和eos标记，并填充到最大长度
        tokens = [self.tokenizer.bos_token_id] + tokens + [self.tokenizer.eos_token_id]
        input_ids = tokens + [self.tokenizer.pad_token_id] * (self.max_length - len(tokens))
        # token ID 使用 long 类型；单条样本的形状为 [max_length]。
        # torch.long 即 int64，适用于 Embedding 查表和类别标签；单条 [T] 样本经组批成为 [B,T]。
        input_ids = torch.tensor(input_ids, dtype=torch.long)
        # 生成标签，pad部分为-100，表示不计算损失
        # clone 拷贝存储，因此把 labels 的 PAD 改成 -100 不会破坏输入 token ID。
        labels = input_ids.clone()
        labels[input_ids == self.tokenizer.pad_token_id] = -100
        # 此处 input_ids 与 labels 位置相同；模型计算损失时再做下一 token 的错位对齐。
        return input_ids, labels


# 监督微调（SFT）：输入包含完整对话，只为 assistant 回复区间构造有效标签。
# 读取多轮对话，把用户、系统和填充位置从监督损失中排除，学习 assistant 回答。
class SFTDataset(Dataset):
    # 声明对话字段类型并加载样本，预先编码 assistant 起始标记和消息结束标记。
    def __init__(self, jsonl_path, tokenizer, max_length=1024):
        super().__init__()
        self.tokenizer = tokenizer
        self.max_length = max_length
        # 显式指定消息字段类型；工具定义和工具调用以 JSON 字符串形式读取。
        # 显式声明可选对话字段为字符串；tools/tool_calls 的 JSON 字符串在构造模板前还原。
        features = Features({'conversations': [{'role': Value('string'), 'content': Value('string'), 'reasoning_content': Value('string'), 'tools': Value('string'), 'tool_calls': Value('string')}]})
        self.samples = load_dataset('json', data_files=jsonl_path, split='train', features=features)
        # 这两个变量都是 token ID 列表：分别匹配 assistant 消息头和消息结束标记。
        # 它们包含角色名或换行，不等同于单个 bos_token_id / eos_token_id。
        self.bos_id = tokenizer(f'{tokenizer.bos_token}assistant\n', add_special_tokens=False).input_ids
        self.eos_id = tokenizer(f'{tokenizer.eos_token}\n', add_special_tokens=False).input_ids

    # 返回数据集样本数量，供 len(dataset)、采样器和 DataLoader 使用。
    def __len__(self):
        return len(self.samples)

    # 将结构化消息渲染成分词器的聊天模板，保留本训练阶段需要的角色边界。
    def create_chat_prompt(self, conversations):
        # 把结构化消息渲染成模型使用的对话文本，并解析模板需要的工具信息。
        messages = []
        tools = None
        for message in conversations:
            # 浅拷贝消息，避免下方替换 tool_calls 时改动原始样本的字段。
            message = dict(message)
            # 当前消息是 system 消息，并且定义了可用工具，则读取工具定义。
            if message.get("role") == "system" and message.get("tools"):
                tools = json.loads(message["tools"]) if isinstance(message["tools"], str) else message["tools"]
            if message.get("tool_calls") and isinstance(message["tool_calls"], str):
                # json.loads() 把 JSON 字符串转换成模板可访问的 Python 列表或字典。
                message["tool_calls"] = json.loads(message["tool_calls"])
            messages.append(message)
        # 返回字符串；样本已有 assistant 回复，因此不额外添加待生成的回复前缀。
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
            tools=tools
        )

    # 扫描 assistant 开始/结束标记，把回答区域的 token 复制到标签，其余保持 -100。
    def generate_labels(self, input_ids):
        # -100 是交叉熵损失的忽略值；先屏蔽所有位置，再开放 assistant 回复区间。
        labels = [-100] * len(input_ids)
        i = 0
        while i < len(input_ids):
            # 用完整的 token 序列匹配消息头，跳过角色标记本身，从回复正文开始监督。
            if input_ids[i:i + len(self.bos_id)] == self.bos_id:
                start = i + len(self.bos_id)
                end = start
                # 不断向后寻找当前 assistant 回复的结束标记。
                while end < len(input_ids):
                    if input_ids[end:end + len(self.eos_id)] == self.eos_id:
                        break
                    end += 1
                # 包含结束标记及其换行，让模型也学习结束回复；上限不超过 max_length。
                # 若没有找到结束标记，扫描会延伸到输入末尾，不能据此保证 padding 被屏蔽。
                # 把回答结束标记也作为监督目标，让模型学习何时停止；被截断的回答最多监督到 max_length。
                for j in range(start, min(end + len(self.eos_id), self.max_length)):
                    # 将回复区间的 token 复制为目标标签；其余位置保持 -100，不计算损失。
                    labels[j] = input_ids[j]
                # 跳过已处理的回复，继续寻找下一轮 assistant 消息。
                i = end + len(self.eos_id) if end < len(input_ids) else len(input_ids)
            else:
                i += 1
        return labels

    # 预处理对话、应用模板并编码补齐，返回 [T] token 和仅保留 assistant 区域的标签。
    def __getitem__(self, index):
        sample = self.samples[index]
        # 按概率补充系统提示词，应用对话模板，再处理空思考块。
        conversations = pre_processing_chat(sample['conversations'])
        prompt = self.create_chat_prompt(conversations)
        prompt = post_processing_chat(prompt)
        # 截断过长对话，并在右侧补齐到固定长度，便于 DataLoader 组成批次。
        input_ids = self.tokenizer(prompt).input_ids[:self.max_length]
        input_ids += [self.tokenizer.pad_token_id] * (self.max_length - len(input_ids))
        labels = self.generate_labels(input_ids)
        # 以下调试代码展示 input_ids[t] 对应 labels[t + 1] 的预测关系。
        # # === 调试打印 ===
        # print(f"\n--- Sample {index} ---")
        # for i, (x, y) in enumerate(zip(input_ids[:-1], labels[1:])):
        #     print(f"{i:3d}: X={self.tokenizer.decode([x])!r:16s} ---> Y={self.tokenizer.decode([input_ids[i+1]])!r:16s} label={y}")
        # # ================
        # 两个张量的形状均为 [max_length]；与预训练一样，由模型内部完成标签移位。
        return torch.tensor(input_ids, dtype=torch.long), torch.tensor(labels, dtype=torch.long)


# 直接偏好优化（DPO）：每条样本提供更受偏好的 chosen 和较不受偏好的 rejected 对话。
# 读取 chosen/rejected 成对对话，返回各自移位后的输入、标签和回答掩码。
class DPODataset(Dataset):
    # 确定填充 token 和回答边界标记，加载包含 chosen/rejected 的偏好样本。
    def __init__(self, file_path, tokenizer, max_length=4096):
        super().__init__()
        self.tokenizer = tokenizer
        self.max_length = max_length
        # 保存备用填充值；下方实际 padding 由 tokenizer 自身的配置完成。
        self.padding = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0
        # 与 SFT 一样，使用包含角色名、换行的 token 序列定位回复边界。
        self.bos_id = tokenizer(f'{tokenizer.bos_token}assistant\n', add_special_tokens=False).input_ids
        self.eos_id = tokenizer(f'{tokenizer.eos_token}\n', add_special_tokens=False).input_ids
        self.samples = load_dataset('json', data_files=file_path, split='train')

    # 返回数据集样本数量，供 len(dataset)、采样器和 DataLoader 使用。
    def __len__(self):
        return len(self.samples)

    # 分别编码偏好/拒绝回答，切出 x=tokens[:-1]、y=tokens[1:] 和对应目标掩码。
    def __getitem__(self, index):
        sample = self.samples[index]
        # 两个字段都是消息列表，通常包含相同的问题上下文以及不同的 assistant 回复。
        chosen = sample['chosen']  # 是一个 list，里面包含若干 {role, content}
        rejected = sample['rejected']  # 同上
        chosen_prompt = self.tokenizer.apply_chat_template(
            chosen, tokenize=False, add_generation_prompt=False
        )
        chosen_prompt = post_processing_chat(chosen_prompt)

        rejected_prompt = self.tokenizer.apply_chat_template(
            rejected, tokenize=False, add_generation_prompt=False
        )
        rejected_prompt = post_processing_chat(rejected_prompt)
        # 分别编码两段对话，并截断或补齐到 max_length。
        chosen_encoding = self.tokenizer(
            chosen_prompt, truncation=True, max_length=self.max_length, padding='max_length'
        )
        rejected_encoding = self.tokenizer(
            rejected_prompt, truncation=True, max_length=self.max_length, padding='max_length'
        )

        chosen_input_ids = chosen_encoding['input_ids']
        chosen_loss_mask = self.generate_loss_mask(chosen_input_ids)

        rejected_input_ids = rejected_encoding['input_ids']
        rejected_loss_mask = self.generate_loss_mask(rejected_input_ids)
        # 在数据集内完成下一 token 对齐：x 去掉最后一项，y 去掉第一项。
        # 例如 [a, b, c] -> x=[a, b]、y=[b, c]；mask 与目标 y 同步去掉第一项。
        # DPO 在此处完成一位移位，训练脚本取 logits 与 y 配对时不能再重复移位。
        x_chosen = torch.tensor(chosen_input_ids[:-1], dtype=torch.long)
        y_chosen = torch.tensor(chosen_input_ids[1:], dtype=torch.long)
        mask_chosen = torch.tensor(chosen_loss_mask[1:], dtype=torch.long)
        x_rejected = torch.tensor(rejected_input_ids[:-1], dtype=torch.long)
        y_rejected = torch.tensor(rejected_input_ids[1:], dtype=torch.long)
        mask_rejected = torch.tensor(rejected_loss_mask[1:], dtype=torch.long)

        # 六个张量均为 [max_length - 1]；训练端按 mask 汇总回复 token 的对数概率。
        return {
            'x_chosen': x_chosen,
            'y_chosen': y_chosen,
            'mask_chosen': mask_chosen,
            'x_rejected': x_rejected,
            'y_rejected': y_rejected,
            'mask_rejected': mask_rejected
        }

    # 扫描 assistant 回答及结束标记，返回与输入等长的 0/1 掩码，供 DPO 汇总有效 log 概率。
    def generate_loss_mask(self, input_ids):
        # 这是损失掩码，不是 attention mask：0 表示不计分，1 表示计入回复概率。
        loss_mask = [0] * len(input_ids)
        i = 0
        while i < len(input_ids):
            # 找到 assistant 消息头后，从正文起向后寻找结束标记。
            if input_ids[i:i + len(self.bos_id)] == self.bos_id:
                start = i + len(self.bos_id)
                end = start
                while end < len(input_ids):
                    if input_ids[end:end + len(self.eos_id)] == self.eos_id:
                        break
                    end += 1
                # 将正文和结束标记设为 1；缺少结束标记时会一直覆盖到输入末尾。
                for j in range(start, min(end + len(self.eos_id), self.max_length)):
                    loss_mask[j] = 1
                # 一条样本可能有多轮 assistant 回复，继续扫描后续消息。
                i = end + len(self.eos_id) if end < len(input_ids) else len(input_ids)
            else:
                i += 1
        return loss_mask

# 原始对话：
# conversations = [
#     {"role": "user", "content": "2 + 3 等于多少？"},
#     {"role": "assistant", "content": "等于 5。"}
# ]
# conversations = pre_processing_chat(conversations)不负责分词或截断，主要用于随机补充 system 消息。
# [
#     {
#         "role": "system",
#         "content": "你是一个专业的AI助手，请提供有价值的回答。"
#     },
#     {"role": "user", "content": "2 + 3 等于多少？"},
#     {"role": "assistant", "content": "等于 5。"}
# ]
# random.random() 会生成一个 [0, 1) 范围内的随机小数，例如：0.37
# use_thinking = random.random() < self.thinking_ratio
# 假设self.thinking_ratio = 0.5，0.37 < 0.5  # True，所以use_thinking = True
# 当前样本开启 thinking 模式。
# AI 反馈强化学习（RLAIF）：提供待续写的对话提示词，回复由训练期间的模型生成。
# 为 PPO/GRPO 提供待续写的 prompt；回答由在线采样生成。
class RLAIFDataset(Dataset):
    def __init__(self, jsonl_path, tokenizer, max_length=1024, thinking_ratio=0.5):
        super().__init__()
        self.tokenizer = tokenizer
        # 此类保存 max_length，但这里返回字符串，不在数据集中编码或截断。
        self.max_length = max_length
        self.thinking_ratio = thinking_ratio  # 按概率开启 thinking
        self.samples = load_dataset('json', data_files=jsonl_path, split='train')
        self.bos_id = tokenizer(f'{tokenizer.bos_token}assistant', add_special_tokens=False).input_ids
        self.eos_id = tokenizer(f'{tokenizer.eos_token}', add_special_tokens=False).input_ids

    # 返回数据集样本数量，供 len(dataset)、采样器和 DataLoader 使用。
    def __len__(self):
        return len(self.samples)

    # 将结构化消息渲染成分词器的聊天模板，保留本训练阶段需要的角色边界。
    def create_chat_prompt(self, conversations):
        conversations = pre_processing_chat(conversations)
        use_thinking = random.random() < self.thinking_ratio
        return self.tokenizer.apply_chat_template(
            conversations[:-1],
            tokenize=False,
            open_thinking=use_thinking,
            add_generation_prompt=True
        )
    def __getitem__(self, index):
        sample = self.samples[index]
        prompt = self.create_chat_prompt(sample['conversations'])

        return {
            'prompt': prompt,
            'answer': ""
        }

# 工具调用强化学习：保留结构化 messages、工具定义 tools 和用于评估的真值 gt。
# 为工具强化学习提供消息列表、工具 schema 与标准结果 gt。
class AgentRLDataset(Dataset):
    # 逐行加载 JSONL，保留原始消息和工具字段供在线多轮交互使用。
    def __init__(self, jsonl_path, tokenizer, max_length=1024):
        super().__init__()
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.samples = []
        # JSONL 的每一行是一个独立样本；直接解析以保留工具和 gt 的嵌套结构。
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                self.samples.append(json.loads(line.strip()))

    # 返回数据集样本数量，供 len(dataset)、采样器和 DataLoader 使用。
    def __len__(self):
        return len(self.samples)

    # 提取 system 消息中的 tools，并移除最后一条答案消息，供 Agent 重新采样。
    def parse_conversations(self, conversations):
        # 从 system 消息中提取工具定义；没有工具时保持 None。
        messages = []
        tools = None
        for message in conversations:
            # 复制每条消息，构造独立的消息列表供训练端使用。
            message = dict(message)
            if message.get("role") == "system" and message.get("tools"):
                tools = json.loads(message["tools"]) if isinstance(message["tools"], str) else message["tools"]
            messages.append(message)
        # 同样约定最后一条消息为已有答案，移除后交给模型在工具交互中重新生成。
        return messages[:-1], tools

    # 返回待交互消息、工具定义及标准结果；变长结构交给自定义 collate_fn 处理。
    def __getitem__(self, index):
        sample = self.samples[index]
        messages, tools = self.parse_conversations(sample['conversations'])
        # 返回原始结构；聊天模板、token 编码和长度控制由训练端处理，gt 原样保留。
        return {'messages': messages, 'tools': tools, 'gt': sample['gt']}


if __name__ == "__main__":
    pass
