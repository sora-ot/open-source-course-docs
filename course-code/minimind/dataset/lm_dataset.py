# 数据入口：将 JSONL 文本/对话转换为预训练、SFT、DPO 或在线强化学习样本。
# 注意：预训练/SFT 返回未移位标签，由模型移位；DPO 在数据集内完成 x/y 移位。
# 将原始文本、对话或偏好数据转换成各训练阶段需要的样本。
# Pretrain / SFT 返回 token 张量和标签；DPO 返回偏好对及掩码；
# RLAIF / AgentRL 返回生成所需的提示词或消息，由训练端继续处理。
from sympy import python
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
    '''
    【为什么按概率补充 system？】
    让训练数据同时包含有/无 system 的输入，并用不同通用提示词增加表达多样性，
    帮助模型适应不同对话形式，减少对固定开场提示词的依赖。
    带工具定义的对话保留原样，避免干扰工具规则与示范调用之间的对应关系；
    普通对话若首条已有 system 也保持原样，仅对无工具定义且首条非 system 的对话按概率补充。

    【例子：按概率给对话补充一条 system 消息】
    system 表示对助手行为的整体要求，例如“你是一个专业的 AI 助手”。
    user 是用户发来的问题，assistant 是数据中已有的示范回答。
    本函数接收消息列表，返回处理后的消息列表；此时还不渲染模板或分词。

    1. 输入一段没有 system 的普通对话

        conversations = [
            {
                "role": "user",
                "content": "你好，你叫什么名字？"
            },
            {
                "role": "assistant",
                "content": "你好，我叫 MiniMind。"
            }
        ]

        result = pre_processing_chat(conversations, add_system_ratio=0.2)

    2. 假设本次 random.random() 返回 0.1

    首先检查所有消息：没有非空 tools 字段，因此继续处理普通对话。
    第一条消息的 role 是 user，不是 system，所以进行概率判断。
    因为 0.1 < 0.2，触发添加；假设 random.choice(SYSTEM_PROMPTS)
    选中“你是minimind，一个小巧但有用的语言模型。”，返回：

        [
            {
                "role": "system",
                "content": "你是minimind，一个小巧但有用的语言模型。"
            },
            {
                "role": "user",
                "content": "你好，你叫什么名字？"
            },
            {
                "role": "assistant",
                "content": "你好，我叫 MiniMind。"
            }
        ]

    返回的列表有三条消息，但它们仍属于同一条对话样本。
    [system消息] + conversations 会创建新列表，不向原列表插入元素；
    因此原 conversations 仍有两条消息。原有消息字典没有被深拷贝。

    3. 假设本次 random.random() 返回 0.7

    因为 0.7 < 0.2 不成立，不补 system，直接返回原来的两条消息列表。
    0.2 表示每次符合条件的调用有 20% 概率添加，不保证每五次恰好添加一次。
    对没有工具定义且首条不是 system 的对话：
        add_system_ratio=0.0 -> 不添加 system。
        add_system_ratio=1.0 -> 总会添加 system，但提示词仍是随机选择的。

    4. 如果输入已经以 system 开头

        conversations = [
            {
                "role": "system",
                "content": "请用简短的中文回答。"
            },
            {
                "role": "user",
                "content": "什么是机器学习？"
            },
            {
                "role": "assistant",
                "content": "机器学习是让计算机从数据中学习规律的方法。"
            }
        ]

    conversations[0].get("role") == "system"，所以直接返回原列表，
    保留“请用简短的中文回答。”，不会替换它，也不会再补一条 system。
    这里检查的是第一条消息，并不是查找列表中任意位置的 system。

    5. 如果任意一条消息带有非空 tools 字段

    例如输入包含下面这条 system 消息（Python 写法）：

        {
            "role": "system",
            "content": "可以调用工具查询天气。",
            "tools": """
            [
                {
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "city": {
                                    "type": "string"
                                }
                            }
                        }
                    }
                }
            ]
            """
        }

    tools 的值是一个非空字符串，any(...) 判断为 True，函数立即返回原列表，
    即使 add_system_ratio=1.0，也不会添加提示词，以保留工具对话的原有上下文。
    三双引号用于展示 Python 多行字符串；实际写入 JSONL 时用 json.dumps
    序列化样本，转义内部双引号和换行。本函数不会解析这个工具 JSON 字符串。
    注意：判断依据是 tools 值的真假，不是 JSON 解析后的工具数量；
    字符串 "[]" 也是非空字符串，会触发直接返回；只有 tool_calls 不会触发此分支。

    输入约定：conversations 必须是非空消息列表，否则访问 conversations[0]
    会报 IndexError。输出仍是消息列表，后续由 create_chat_prompt 渲染聊天文本。
    '''
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
    '''
    【函数作用：按概率移除对话文本中的空思考块】
    输入 prompt_content：聊天模板已经生成的完整字符串，不是消息列表。
    输出：处理后的字符串，后续再交给 tokenizer 编码。
    empty_think_ratio 表示空思考块的保留概率，默认 0.2，约有 20% 保留、80% 移除。
    这样可以让普通回答的训练文本同时包含带空 think 标签和不带空标签的形式。
    本函数不会生成思考内容，也不会删除有实际内容的思考块。

    【为什么要移除空思考块？】
    空 think 块只有标签和换行，没有实际思考内容。在当前 SFT 实现中，
    assistant 区域里的这些标签和换行也会成为训练目标。
    移除它们，可以让模型学习直接从回答正文开始，减少空标签占用的 token；
    少量保留，则让训练数据同时包含带空标签和直接回答这两种格式。
    例如，原来要学习输出“空 think 块 + 你好！”，移除后只需学习输出“你好！”。
    非空思考块包含实际示范内容，因此保留。本操作调整的是回答的文本格式，
    删除空标签本身不等于删除推理知识，也不能据此判断模型推理能力的变化。

    一、输入样例：模板为 Hi / Hello 对话添加了空 think 块

    打印 prompt_content，可以看到：

        <|im_start|>user
        Hi<|im_end|>
        <|im_start|>assistant
        <think>

        </think>

        Hello<|im_end|>

    上面的缩进仅用于文档展示；实际文本不带展示用缩进。
    空块的精确字符串是 '<think>\\n\\n</think>\\n\\n'，其中 \\n 表示换行。
    即 <think> 后有两个换行，</think> 后也有两个换行。

        result = post_processing_chat(prompt_content, empty_think_ratio=0.2)

    二、例 1：假设 random.random() 返回 0.7，移除空块

    1. in 检查发现输入包含上述精确格式的空 think 块。
    2. 0.7 > 0.2 成立，进入 if 分支。
    3. replace(空块, '') 将匹配到的完整空块替换为空字符串。
    4. 返回的 result 打印后为：

        <|im_start|>user
        Hi<|im_end|>
        <|im_start|>assistant
        Hello<|im_end|>

    user 问题、assistant 正文和消息边界都保留，只移除了空块及其指定换行。
    Python 字符串不可变，replace 返回新字符串；调用者需要使用返回值，
    例如 __getitem__ 中的 prompt = post_processing_chat(prompt)。

    三、例 2：同样的输入，假设 random.random() 返回 0.1，保留空块

    0.1 > 0.2 不成立，不执行 replace，返回原字符串。
    输出与第一部分的输入完全相同，Hello 前仍有空 think 块。
    条件用的是 >，所以若随机值恰好等于 0.2，也会保留。
    这是每次符合条件的调用进行一次随机判断，不保证每五次恰好保留一次。

    四、例 3：有实际思考内容，不会删除

    输入：

        <|im_start|>assistant
        <think>
        用户在打招呼，我也礼貌回应。
        </think>

        Hello<|im_end|>

    这段文本没有精确匹配的空块，所以直接原样返回，输出为：

        <|im_start|>assistant
        <think>
        用户在打招呼，我也礼貌回应。
        </think>

        Hello<|im_end|>

    由于 and 的短路求值，左边的 in 判断为假时，不会调用 random.random()。
    完全没有 think 标签的输入，也同样原样返回。

    五、两个容易忽略的细节

    1. 只匹配固定字符串，不会解析标签或自动忽略空白差异。
       例如 '<think></think>'，或者标签之间只有一个换行、含有空格，
       都不等于这里指定的空块，因此不会被这一条 replace 删除。

    2. 一次调用只做一次随机判断，replace 默认替换所有匹配项。
       如果一段多轮对话中有两个精确匹配的空块，且随机判断触发移除，
       两个都会删除；若未触发，两个都会保留，不是每个空块分别抽一次随机数。
       同一段文本中的非空思考块仍保持原样。

    在 SFT 数据处理中的位置：
        消息列表 -> create_chat_prompt 生成对话文本
                 -> 本函数处理空 think 块
                 -> tokenizer 编码 -> 截断、补齐和生成 labels。
    '''
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
        ''' 加载预训练数据集。

            这里使用 Hugging Face datasets 的 load_dataset()，
            从 JSON 文件中读取数据，并加载 train 部分。

            例如 data_path = "pretrain_dataset.jsonl"

            文件内容可以是：

            {"text": "人工智能正在快速发展。"}
            {"text": "Transformer 是目前大语言模型常用的基础架构。"}
            {"text": "预训练的目标是让模型学习语言中的统计规律和知识。"}

            加载之后：

            self.samples[0]
            # {"text": "人工智能正在快速发展。"}

            self.samples[1]
            # {"text": "Transformer 是目前大语言模型常用的基础架构。"}

            self.samples[2]
            # {"text": "预训练的目标是让模型学习语言中的统计规律和知识。"}

            也就是说，self.samples 可以理解为一个预训练文本数据集，
            后续会把其中的 text 取出来，再经过 tokenizer 转换成 token，
            用于训练语言模型预测下一个 token。
        '''
        self.samples = load_dataset('json', data_files=data_path, split='train')

    # 返回数据集样本数量，供 len(dataset)、采样器和 DataLoader 使用。
    def __len__(self):  # 样本条数，不是单条文本的 token 数
        return len(self.samples)

    # 读取一条 text，截断并补齐到 max_length，复制标签后屏蔽 PAD；返回两个 [T] LongTensor。
    ''' 完整例子：

    假设：
        self.max_length = 8
        bos_token_id = 1
        eos_token_id = 2
        pad_token_id = 0

    数据集中的一条数据为：

        {
            "text": "I love AI"
        }

    并假设 tokenizer 的编码结果为：

        "I"    -> 10
        "love" -> 11
        "AI"   -> 12

    那么整个 __getitem__ 的处理过程如下：

    1. 取出第 index 条数据

        sample = self.samples[index]

    得到：

        sample = {
            "text": "I love AI"
        }


    2. 对正文进行 tokenizer 编码

        tokens = self.tokenizer(
            "I love AI",
            add_special_tokens=False,
            max_length=self.max_length - 2,
            truncation=True
        ).input_ids

    得到：

        tokens = [10, 11, 12]

    这里设置：

        add_special_tokens=False

    是因为 BOS 和 EOS 后面会手动添加。

    又因为：

        self.max_length = 8

    需要给 BOS 和 EOS 各预留一个位置，所以正文最多只能有：

        8 - 2 = 6

    个 token。

    如果正文超过 6 个 token，
    truncation=True 会自动截断。


    3. 在正文前后加入 BOS 和 EOS

        tokens = [BOS] + tokens + [EOS]

    得到：

        [1, 10, 11, 12, 2]

    对应：

        BOS   I   love   AI   EOS
        1   10    11    12    2


    4. 使用 PAD 补齐到 max_length

    当前长度为：

        len(tokens) = 5

    而最大长度是：

        max_length = 8

    所以需要补：

        8 - 5 = 3

    个 PAD。

    最终：

        input_ids =
        [1, 10, 11, 12, 2, 0, 0, 0]

    对应：

        BOS   I   love   AI   EOS   PAD   PAD   PAD
        1   10    11    12    2     0     0     0

    这样做是为了让不同长度的文本都变成统一长度，
    方便 DataLoader 组成形状为 [B, T] 的 batch。


    5. 转换为 torch.long 类型的 Tensor

    得到：

        input_ids =
        tensor([1, 10, 11, 12, 2, 0, 0, 0])

    torch.long 即 int64。

    因为这些数字表示的是 token 在词表中的编号，
    后续需要用于 Embedding 查表，所以必须使用整数类型。

    单条样本的形状为：

        [T]

    例如：

        [8]

    经过 DataLoader 组成 batch 后，
    如果 batch_size = 4，则形状会变为：

        [4, 8]

    即：

        [B, T]


    6. 复制 input_ids 生成 labels

        labels = input_ids.clone()

    此时：

        input_ids =
        [1, 10, 11, 12, 2, 0, 0, 0]

        labels =
        [1, 10, 11, 12, 2, 0, 0, 0]

    这里使用 clone() 是为了让 labels 和 input_ids
    拥有独立的存储空间。

    后面修改 labels 时，
    不会影响真正送入模型的 input_ids。


    7. 将 labels 中 PAD 对应的位置改为 -100

    原来的 labels：

        [1, 10, 11, 12, 2, 0, 0, 0]

    修改后：

        [1, 10, 11, 12, 2, -100, -100, -100]

    原因是 PyTorch 的 CrossEntropyLoss 默认：

        ignore_index = -100

    因此 label 为 -100 的位置不会参与 Loss 计算。

    也就是说，PAD 只是为了补齐长度，
    模型不需要学习去预测 PAD。


    8. 最终返回

        input_ids =
        [1, 10, 11, 12, 2, 0, 0, 0]

        labels =
        [1, 10, 11, 12, 2, -100, -100, -100]


    需要特别注意：

    此时 input_ids 和 labels 看起来几乎是一样的，
    并没有在 Dataset 中直接做“错位”。

    真正计算 Causal Language Model 的 Loss 时，
    模型内部通常会再进行一位错位，例如：

        shift_logits = logits[..., :-1, :]
        shift_labels = labels[..., 1:]

    因此真正训练的目标实际上是：

        BOS  -> I
        I    -> love
        love -> AI
        AI   -> EOS

    也就是大语言模型最核心的：

        Next Token Prediction
        下一 Token 预测


    整个数据变化过程可以概括为：

        {"text": "I love AI"}

                ↓

            "I love AI"

                ↓ tokenizer

            [10, 11, 12]

                ↓ 加 BOS / EOS

            [1, 10, 11, 12, 2]

                ↓ PAD 到 max_length=8

    input_ids:
            [1, 10, 11, 12, 2, 0, 0, 0]

                ↓ clone

    labels:
            [1, 10, 11, 12, 2, 0, 0, 0]

                ↓ PAD 改为 -100

    labels:
            [1, 10, 11, 12, 2, -100, -100, -100]

                ↓ 模型内部错位计算 Loss

            BOS  -> I
            I    -> love
            love -> AI
            AI   -> EOS
    '''
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
    '''
    【先理解 user 和 assistant：谁在说话？】
    user 表示用户发来的消息，例如问题、要求或补充信息。
    assistant 表示 AI 助手的回复；在 SFT 数据中，它是事先准备好的示范回答。
    例如一段对话：

        用户（user）：你好，你叫什么名字？
        助手（assistant）：你好，我叫 MiniMind。

    存成一条训练样本时，对应为：

        {
            "conversations": [
                {
                    "role": "user",
                    "content": "你好，你叫什么名字？"
                },
                {
                    "role": "assistant",
                    "content": "你好，我叫 MiniMind。"
                }
            ]
        }

    role 回答“谁在说话”，content 回答“说了什么”。
    上面的两条消息合起来是一条对话样本，不是两条训练样本。
    训练时，user 和 assistant 的文本都会放进 input_ids；
    labels 只保留 assistant 回复区间及其结束标记，其余位置设为 -100。
    也就是让模型学习：看到“你好，你叫什么名字？”后，如何逐 token 回答
    “你好，我叫 MiniMind。”，而不把用户的问题本身作为要学习生成的目标。
    虽然训练输入包含示范回答，因果注意力仍保证每个位置只能看到当前位置
    及之前的内容；预测下一个回答 token 时，看不到那个 token 及后续内容。
    实际聊天时，用户提供 user 消息，模型接着生成 assistant 回复。

    【贯穿下面五个函数的教学约定】
    与上面的 PretrainDataset 一样，用假设的 token ID 手工展示数据变化。
    这些数字不是实际分词结果；真实分词可能把一个词拆成多个 token。
    假设编码：<|im_start|>=1，<|im_end|>=2，PAD=0，换行 \\n=3，
              user=4，assistant=5，Hi=10，Hello=11，Bye=12，Goodbye=13。
    主例使用 max_length=16，对话为 user: Hi -> assistant: Hello。
    主例还假设预处理没有随机添加 system，后处理移除了空 think 块，
    且 tokenizer(prompt) 不额外添加特殊 token；从而可以手算完整序列。
    实际训练以传入 tokenizer 的配置、模板和随机处理结果为准。
    '''

    # 声明对话字段类型并加载样本，预先编码 assistant 起始标记和消息结束标记。
    def __init__(self, jsonl_path, tokenizer, max_length=1024):
        '''
        【例 1：创建数据集对象】
        假设 sft_demo.jsonl 有两条样本，下面为便于阅读展开显示。
        实际 JSONL 文件中，每条完整样本仍应存为一行。
        按当前SFTDataset的Features中的定义，样本最外层只有 conversations 一个字段。
        第一条样本：
        {
            "conversations": [
                {
                    "role": "user",
                    "content": "Hi"
                },
                {
                    "role": "assistant",
                    "content": "Hello"
                }
            ]
        }

        第二条样本：
        {
            "conversations": [
                {
                    "role": "user",
                    "content": "Bye"
                },
                {
                    "role": "assistant",
                    "content": "Goodbye"
                }
            ]
        }

        调用：dataset = SFTDataset("sft_demo.jsonl", tokenizer, max_length=16)
        1. super().__init__() 初始化父类，保存 tokenizer 和最大序列长度 16。
        2. features 规定 conversations 是消息列表，每条消息有五个字符串字段。
           role 表示角色，content 表示正文，reasoning_content 表示思考内容；
           tools / tool_calls 存放工具定义 / 工具调用的 JSON 字符串。
           上面省略的可选字段在按该 schema 加载后可为 None（JSON 中为 null）。
           例如第一条消息可读作：
           {
               "role": "user",
               "content": "Hi",
               "reasoning_content": None,
               "tools": None,
               "tool_calls": None
           }
        3. load_dataset 后 self.samples 包含两条样本；不是四条消息各算一条。
           self.samples[0]["conversations"][1]["content"] == "Hello"。
           split="train" 指读取该文件形成的 train split，不会在这里自动划分验证集。
        4. 按类开头的假设编码，预先计算两个用于匹配边界的列表：
           self.bos_id = tokenizer("<|im_start|>assistant\\n", ...).input_ids
                       = [1, 5, 3]
           self.eos_id = tokenizer("<|im_end|>\\n", ...).input_ids = [2, 3]
           add_special_tokens=False 避免编码这些标记时再自动添加额外标记。
           bos_id 包含 assistant 角色，所以 user 消息头 [1, 4, 3] 不会匹配。
           因为这里的 bos_id 专门定位需要监督的 assistant 回答起点；user 问题只作为输入上下文，不作为预测目标，所以不把 user 放进这个匹配序列。
        此函数完成对象初始化；尚未把每条对话转换成训练张量。

        假设编码：<|im_start|>=1，<|im_end|>=2，PAD=0，换行 \\n=3，
              user=4，assistant=5，Hi=10，Hello=11，Bye=12，Goodbye=13。

        '''
        super().__init__()
        self.tokenizer = tokenizer
        self.max_length = max_length
        # 显式指定消息字段类型；工具定义和工具调用以 JSON 字符串形式读取。
        # 显式声明可选对话字段为字符串；tools/tool_calls 的 JSON 字符串在构造模板前还原。
        '''
        【Features 类的具体用法：声明数据的结构和类型】
        Features 来自 Hugging Face datasets，可以理解为数据集的“字段类型表”。
        它描述每条样本有哪些字段、各字段是什么类型，本身不读取 JSON 文件，
        也不负责分词、添加聊天标记或生成 labels。

        1. 最简单的例子：声明普通字段

            simple_features = Features({
                "text": Value("string"),
                "score": Value("float32"),
                "count": Value("int64"),
                "enabled": Value("bool")
            })

            一条与之对应的数据：
            {
                "text": "你好",
                "score": 0.9,
                "count": 2,
                "enabled": True
            }

        字典的键是字段名；Value(...) 声明单个值的类型。
        例如 Value("string") 表示字符串，Value("int64") 表示 64 位整数。
        上面是 Python 字典；若写成 JSON，True 应写成 true。

        2. 当前 SFT 数据：一个字段里放多条消息

            features = Features({
                "conversations": [
                    {
                        "role": Value("string"),
                        "content": Value("string"),
                        "reasoning_content": Value("string"),
                        "tools": Value("string"),
                        "tool_calls": Value("string")
                    }
                ]
            })

        从外到内理解：
            Features({...})       -> 描述一条样本的所有字段。
            "conversations": [...] -> conversations 的值是消息列表。
            [{...}]               -> 列表中每个元素都是按同一结构组织的消息字典。
            "role": Value(...)    -> 消息字典中的 role 字段是字符串。

        类型声明里的列表只有一个字典，是在描述“每个元素的格式”，
        并不是限制一条对话只能有一条消息；实际列表可以包含多轮对话。
        注意这里使用的是“字典组成的列表”，后续代码才能逐条读取消息，
        如 conversations[0]["role"]。不要随意换成 Sequence({...})：
        datasets 的 Sequence 包裹字典时有转换为“列表组成的字典”的特殊行为，
        数据结构可能不再符合这里逐条遍历消息的预期。

        3. 与这份类型声明对应的一条完整样本（Python 写法）

            {
                "conversations": [
                    {
                        "role": "user",
                        "content": "你好",
                        "reasoning_content": None,
                        "tools": None,
                        "tool_calls": None
                    },
                    {
                        "role": "assistant",
                        "content": "你好，有什么可以帮你？",
                        "reasoning_content": None,
                        "tools": None,
                        "tool_calls": None
                    }
                ]
            }

        None 表示该字段没有值，存到 JSONL 中应写成 null。
        Value("string") 描述非空值的类型，并不表示每个字段都必须有非空文本。
        没有思考内容或工具信息时，可以用 null 表示；它不同于字符串 "null"。

        4. 把类型表交给 load_dataset，才开始按该结构读取数据

            samples = load_dataset(
                "json",
                data_files="sft_demo.jsonl",
                split="train",
                features=features
            )

            samples.features
                -> 查看加载后的字段结构和类型。
            samples[0]["conversations"][0]["role"]
                -> "user"
            samples[0]["conversations"][1]["content"]
                -> "你好，有什么可以帮你？"

        不传 features 时，加载器通常会根据数据推断类型；这里显式声明，
        是为了让可选字段也按预期类型读取，例如前面的样本没有工具信息，
        后面的样本才出现工具字符串时，仍有明确的字段类型约定。
        这并不意味着任意输入都能自动修复：不兼容的结构仍可能导致加载失败。

        5. 为什么 tools / tool_calls 也声明为 string？

        当前文件约定：这两个字段先保存为 JSON 字符串，而不是直接嵌套列表。
        例如加载后的 Python 消息字典里可以有下面的字段片段，
        用三双引号展示包含换行的 JSON 字符串：

            "tool_calls": """
            [
                {
                    "name": "weather",
                    "arguments": {
                        "city": "北京"
                    }
                }
            ]
            """

        此时字段的值是 str；三双引号里面的内容才是 JSON 文本。
        三双引号是 Python 字符串写法，不是 JSON 本身的语法。
        写入 JSONL 时，应用 json.dumps(sample, ensure_ascii=False) 序列化
        整条样本，让它正确转义工具字符串内部的双引号。
        create_chat_prompt 随后调用 json.loads(message["tool_calls"])，
        才会得到下面的 Python 列表，供聊天模板访问：

            [
                {
                    "name": "weather",
                    "arguments": {
                        "city": "北京"
                    }
                }
            ]

        Features 不会替你执行这个 JSON 字符串解析步骤。

        最后注意：Value("string") 只规定 role 的类型，不会检查角色名是否合法。
        "user" 和 "assistant" 都符合字符串类型；即使误写成 "assistent"，
        也不能指望 Features 发现拼写错误，仍需数据本身遵守聊天模板的角色约定。
        '''
        features = Features({'conversations': [{'role': Value('string'), 'content': Value('string'), 'reasoning_content': Value('string'), 'tools': Value('string'), 'tool_calls': Value('string')}]})
        self.samples = load_dataset('json', data_files=jsonl_path, split='train', features=features)
        # 这两个变量都是 token ID 列表：分别匹配 assistant 消息头和消息结束标记。
        # 它们包含角色名或换行，不等同于单个 bos_token_id / eos_token_id。
        self.bos_id = tokenizer(f'{tokenizer.bos_token}assistant\n', add_special_tokens=False).input_ids
        self.eos_id = tokenizer(f'{tokenizer.eos_token}\n', add_special_tokens=False).input_ids

    # 返回数据集样本数量，供 len(dataset)、采样器和 DataLoader 使用。
    def __len__(self):
        '''
        【例 2：查询样本数】
        沿用上面有两行 JSONL 的文件：len(dataset) 调用这里，返回 2。
        dataset[0] 取 Hi / Hello 对话，dataset[1] 取 Bye / Goodbye 对话。
        即使一条样本包含十轮对话，仍只算一条样本；max_length=16 也不影响计数。
        例如 DataLoader(dataset, batch_size=2, shuffle=False) 会组成一个批次，
        其中 input_ids 和 labels 的形状分别为 [2, 16]。
        '''
        return len(self.samples)

    # 将结构化消息渲染成分词器的聊天模板，保留本训练阶段需要的角色边界。
    def create_chat_prompt(self, conversations):
        '''
        【create_chat_prompt：把消息列表转换成模型约定的对话文本】
        输入 conversations：一条样本中的消息列表，每条消息描述角色、正文等信息。
        输出 prompt：一个字符串，包含角色标记、消息正文和结束标记。
        函数先整理工具信息，再调用 tokenizer.apply_chat_template 按聊天模板排版。
        它不生成新回答、不执行工具、不分词，也不生成 labels。

        一、【例 3A：普通对话的完整输入和输出】

        1. 输入样例（省略值为 None 的可选字段）

            conversations = [
                {
                    "role": "user",
                    "content": "Hi"
                },
                {
                    "role": "assistant",
                    "content": "Hello"
                }
            ]

            prompt = dataset.create_chat_prompt(conversations)

        2. 函数内部怎样处理这个输入？

            messages = []：准备一个消息列表。
            tools = None：默认没有可用工具定义。
            for 循环：依次取出 user 和 assistant 消息。
            message = dict(message)：浅拷贝当前消息的字典。
            两条消息都没有工具信息，因此直接追加到 messages。
            最后把 messages 和 tools=None 传给 apply_chat_template。

        apply_chat_template 相当于“对话排版器”，按 tokenizer.chat_template
        规定的格式，写出谁在说话、正文从哪里开始、消息在哪里结束。
        本项目模板保存在 model/tokenizer_config.json；换用其他模板，输出格式可能不同。

        3. 输出样例：print(prompt) 的效果

            <|im_start|>user
            Hi<|im_end|>
            <|im_start|>assistant
            <think>

            </think>

            Hello<|im_end|>

        这是一个完整字符串，不是两条字符串，也不是 token ID 列表。
        上面的缩进仅用于文档展示；实际文本不带这些展示用缩进，末尾还有一个换行。

        逐段对应输入：
            <|im_start|>user      -> 第一条消息的开始标记和 role，随后换行。
            Hi                   -> 第一条消息的 content。
            <|im_end|>           -> 第一条消息结束，随后换行。
            <|im_start|>assistant -> 第二条消息的开始标记和 role，随后换行。
            <think>...</think>   -> 当前模板插入的思考区域。
            Hello                -> 第二条消息中已有的 content，不是此函数生成的答案。
            <|im_end|>           -> 第二条消息结束，随后换行。

        本例没有 reasoning_content，所以思考区域为空。若 assistant 消息中有
        reasoning_content="先打招呼"，输出中的 assistant 部分会变成：

            <|im_start|>assistant
            <think>
            先打招呼
            </think>

            Hello<|im_end|>

        空 think 块的随机移除由后续 post_processing_chat 完成，不在此函数中执行。
        非空思考内容不会被该空块后处理移除。

        一（补充）、把真实模板拿出来，逐句看 apply 的过程

        下面是从 model/tokenizer_config.json 的 chat_template 字段提取的完整模板。
        它使用 Jinja 模板语法，不是 Python 函数；apply_chat_template 会把 messages、
        tools、add_generation_prompt 等值交给模板，再把模板输出拼接成字符串。
        这里展示的是 JSON 解码后的模板文本；配置文件中还会有 JSON 层面的转义。

        先认识几种语法：
            {% ... %}：条件、循环、变量赋值等控制语句，本身不输出文本。
            {{ ... }}：计算表达式，并把结果写入最终文本。
            {%- / {{-：去掉该模板标记前面的空白，避免模板排版缩进混入输出。
            message.role：读取消息字典的 role；message.content 同理。
            is string：检查是否为字符串；set：设置模板局部变量。
            | tojson：把 Python 对象转换为 JSON 文本。
            loop.first / loop.last：当前是否为这次循环的第一项 / 最后一项。
            字符串中的反斜杠 n 表示输出换行；加号用于拼接字符串。

        【当前完整模板原文】
            {%- if tools %}
                {{- '<|im_start|>system\\n' }}
                {%- if messages[0].role == 'system' %}
                    {{- messages[0].content + '\\n\\n' }}
                {%- endif %}
                {{- "# Tools\\n\\nYou may call one or more functions to assist with the user query.\\n\\nYou are provided with function signatures within <tools></tools> XML tags:\\n<tools>" }}
                {%- for tool in tools %}
                    {{- "\\n" }}
                    {{- tool | tojson }}
                {%- endfor %}
                {{- "\\n</tools>\\n\\nFor each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:\\n<tool_call>\\n{\\"name\\": <function-name>, \\"arguments\\": <args-json-object>}\\n</tool_call><|im_end|>\\n" }}
            {%- else %}
                {%- if messages[0].role == 'system' %}
                    {{- '<|im_start|>system\\n' + messages[0].content + '<|im_end|>\\n' }}
                {%- endif %}
            {%- endif %}
            {%- set ns = namespace(multi_step_tool=true, last_query_index=messages|length - 1) %}
            {%- for message in messages[::-1] %}
                {%- set index = (messages|length - 1) - loop.index0 %}
                {%- if ns.multi_step_tool and message.role == "user" and message.content is string and not(message.content.startswith('<tool_response>') and message.content.endswith('</tool_response>')) %}
                    {%- set ns.multi_step_tool = false %}
                    {%- set ns.last_query_index = index %}
                {%- endif %}
            {%- endfor %}
            {%- for message in messages %}
                {%- if message.content is string %}
                    {%- set content = message.content %}
                {%- else %}
                    {%- set content = '' %}
                {%- endif %}
                {%- if (message.role == "user") or (message.role == "system" and not loop.first) %}
                    {{- '<|im_start|>' + message.role + '\\n' + content + '<|im_end|>' + '\\n' }}
                {%- elif message.role == "assistant" %}
                    {%- set reasoning_content = '' %}
                    {%- if message.reasoning_content is string %}
                        {%- set reasoning_content = message.reasoning_content %}
                    {%- else %}
                        {%- if '</think>' in content %}
                            {%- set reasoning_content = content.split('</think>')[0].rstrip('\\n').split('<think>')[-1].lstrip('\\n') %}
                            {%- set content = content.split('</think>')[-1].lstrip('\\n') %}
                        {%- endif %}
                    {%- endif %}
                    {%- if true %}
                        {{- '<|im_start|>' + message.role + '\\n<think>\\n' + reasoning_content.strip('\\n') + '\\n</think>\\n\\n' + content.lstrip('\\n') }}
                    {%- endif %}
                    {%- if message.tool_calls %}
                        {%- for tool_call in message.tool_calls %}
                            {%- if (loop.first and content) or (not loop.first) %}
                                {{- '\\n' }}
                            {%- endif %}
                            {%- if tool_call.function %}
                                {%- set tool_call = tool_call.function %}
                            {%- endif %}
                            {{- '<tool_call>\\n{"name": "' }}
                            {{- tool_call.name }}
                            {{- '", "arguments": ' }}
                            {%- if tool_call.arguments is string %}
                                {{- tool_call.arguments }}
                            {%- else %}
                                {{- tool_call.arguments | tojson }}
                            {%- endif %}
                            {{- '}\\n</tool_call>' }}
                        {%- endfor %}
                    {%- endif %}
                    {{- '<|im_end|>\\n' }}
                {%- elif message.role == "tool" %}
                    {%- if loop.first or (messages[loop.index0 - 1].role != "tool") %}
                        {{- '<|im_start|>user' }}
                    {%- endif %}
                    {{- '\\n<tool_response>\\n' }}
                    {{- content }}
                    {{- '\\n</tool_response>' }}
                    {%- if loop.last or (messages[loop.index0 + 1].role != "tool") %}
                        {{- '<|im_end|>\\n' }}
                    {%- endif %}
                {%- endif %}
            {%- endfor %}
            {%- if add_generation_prompt %}
                {{- '<|im_start|>assistant\\n' }}
                {%- if open_thinking is defined and open_thinking is true %}
                    {{- '<think>\\n' }}
                {%- else %}
                    {{- '<think>\\n\\n</think>\\n\\n' }}
                {%- endif %}
            {%- endif %}

        【把例 3A 的输入代入上面的真实模板】

        调用等价于把以下值交给模板渲染（这里说明数据流，不是替换实际库实现）：
            messages = 前面例 3A 的 Hi / Hello 消息列表
            tools = None
            add_generation_prompt = False

        第 1 步：处理模板开头的 system / tools 区域。
            if tools：None 为假，进入 else。
            if messages[0].role == 'system'：第一条是 user，为假。
            这一部分输出空字符串，不会凭空插入 system。

        第 2 步：倒序扫描 messages，设置 ns.last_query_index。
            先看到 assistant，再看到 user，记录最后一条普通用户消息的下标 0。
            这些 set 操作不输出任何文本。
            当前模板后面的 assistant 分支使用 if true，并没有用这个下标筛选回答，
            所以不要把这段扫描理解为“只渲染最后一轮回答”。

        第 3 步：正序循环，处理第一条 user 消息。
            message.content 是字符串，因此 content = "Hi"。
            message.role == "user" 成立，执行 user 分支的输出表达式。
            把 role 替换为 user、content 替换为 Hi，得到：

                <|im_start|>user
                Hi<|im_end|>

        第 4 步：处理第二条 assistant 消息。
            content = "Hello"，进入 assistant 分支。
            reasoning_content 先设为空字符串；输入没有提供思考内容，
            Hello 中也没有 </think>，所以 reasoning_content 仍为空。
            if true 总是成立：拼接 assistant 头、think 开关标签和 Hello。
            没有 tool_calls，所以跳过工具调用循环，再追加消息结束标记，得到：

                <|im_start|>assistant
                <think>

                </think>

                Hello<|im_end|>

            reasoning_content 为空，但模板明确输出了 think 标签前后的换行，
            因而留下空 think 块。这就是本例中空块的实际来源。

        第 5 步：检查模板末尾的 if add_generation_prompt。
            本次为 False，不追加任何内容。
            把第 3、4 步输出按顺序拼起来，就是前面 print(prompt) 的完整结果。
            tokenize=False 让 apply_chat_template 在此返回文本，不继续转成 token ID。

        【同一模板的两个变化】
            如果 assistant 提供 reasoning_content="先打招呼"，第 4 步直接读取它，
            把文字填到 think 标签中；其余角色边界和 Hello 正文不变。
            如果只传 user 消息且 add_generation_prompt=True，第 4 步不会发生，
            第 5 步则补 assistant 消息头和默认空 think 块，等待模型续写正文。

        【工具样例怎样走模板？】
            对下面例 3B 的输入，先由 Python 循环把工具 JSON 字符串解析为列表。
            if tools 为真：模板输出 system 头、原 system 正文、工具使用说明，
            并通过 for tool in tools 和 tool | tojson 写入每个工具定义。
            正序处理消息时，首条 system 不会再输出一遍；user 仍走 user 分支。
            assistant 的 tool_calls 非空，所以遍历调用，取出 tool_call.function，
            输出 name，再将 arguments 字典经 tojson 写进 <tool_call> 区域。
            这解释了下面样例中的工具定义和具体调用各自出现在哪里。


        二、【例 3B：带工具信息时，输入怎样转换？】

        1. 输入样例

        下面是 Python 消息列表。tools 和 tool_calls 用三双引号表示 JSON 字符串，
        不是直接存放的 Python 列表。写入 JSONL 时需用 json.dumps 序列化整条样本。

            conversations = [
                {
                    "role": "system",
                    "content": "可以查询天气。",
                    "tools": """
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": "weather",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "city": {
                                            "type": "string"
                                        }
                                    },
                                    "required": [
                                        "city"
                                    ]
                                }
                            }
                        }
                    ]
                    """
                },
                {
                    "role": "user",
                    "content": "北京天气怎么样？"
                },
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": """
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": "weather",
                                "arguments": {
                                    "city": "北京"
                                }
                            }
                        }
                    ]
                    """
                }
            ]

        2. 函数内部处理

            system 消息：json.loads(message["tools"]) 把工具 JSON 字符串解析成列表，
                         保存到局部变量 tools，稍后作为 tools=tools 传给模板。
            user 消息：没有工具字段，直接加入 messages。
            assistant 消息：把副本中的 tool_calls 字符串替换成解析后的列表。

        浅拷贝使替换只发生在新消息字典上，原 conversations 中的字段仍为字符串。
        如果工具字段原本已是列表，则相应的 isinstance(..., str) 检查避免重复解析。
        tools 描述“可用什么工具”；tool_calls 描述“这条回答具体调用什么、参数是什么”。

        3. 输出样例（展示关键部分）

        完整输出的 system 段会包含原 system 正文、工具使用说明和 <tools> 定义区域。
        为突出角色与工具调用的关系，下面省略 system 段中的详细工具说明和定义，
        并把工具调用 JSON 展开排版；实际模板输出的 JSON 空白可能不同。

            <|im_start|>system
            可以查询天气。

            ……工具使用说明和 <tools> 定义区域，此处省略……
            <|im_end|>
            <|im_start|>user
            北京天气怎么样？<|im_end|>
            <|im_start|>assistant
            <think>

            </think>

            <tool_call>
            {
                "name": "weather",
                "arguments": {
                    "city": "北京"
                }
            }
            </tool_call><|im_end|>

        输出中的 weather 调用来自输入的 tool_calls；此函数不会真的查询天气。
        如果消息列表中还有 role="tool" 的工具返回，当前模板会把它包装成
        user 区域内的 <tool_response> 文本；工具结果不属于 assistant 监督区间。

        三、最后这次 apply_chat_template 调用的参数是什么意思？

            self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
                tools=tools
            )

        messages：整理后的消息列表，按原有顺序交给模板处理。

        tokenize=False：只排版成字符串，本次不分词。
            后续还要处理空 think 块，所以这里保留文本；之后 __getitem__ 才调用
            self.tokenizer(prompt).input_ids，把文本变成 token ID。

        add_generation_prompt=False：不在末尾额外追加等待生成的 assistant 开头。
            SFT 样本已经有示范回答，输出在已有回答结束处结束即可。
            这个参数不删除已有回答，也不控制是否计算标签或损失。
            对比推理场景：如果输入只有例 3A 的 user 消息，按当前模板输出如下。

            False：
                <|im_start|>user
                Hi<|im_end|>

            True（未额外设置 open_thinking 时）：
                <|im_start|>user
                Hi<|im_end|>
                <|im_start|>assistant
                <think>

                </think>

            True 追加的是助手开头，提示模型接下来续写回答；此时没有 Hello，
            也没有新回答的结束标记。真正生成答案要由后续模型调用完成。

        tools=tools：把局部变量 tools 中的工具定义列表交给模板。
            左边是参数名，右边是变量名。为 None 时不加工具说明；
            为工具列表时，当前模板把定义和使用说明写进 system 文本。

        四、返回后如何用于 SFT 训练？

            conversations
                -> 本函数整理消息并应用聊天模板
                -> prompt 字符串
                -> post_processing_chat 处理空 think 块
                -> tokenizer 编码、截断和补 PAD
                -> generate_labels 匹配 assistant 消息头，设置监督标签
                -> 返回 input_ids 和 labels 两个张量

        模板提供角色边界，generate_labels 利用这些边界定位 assistant 回答。
        本函数负责构造对话文本；把非回答位置设为 -100 是后续标签函数的工作。
        '''
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
        '''
        【本函数的输入和输出】
        输入 input_ids：已经编码、截断并补齐的 token ID 列表，正常调用时长度为 max_length。
        输出 labels：等长列表；assistant 正文及结束标记保留原 token ID，其余位置为 -100。
        函数不会修改 input_ids，也不会在这里把 labels 向左或向右移动。

        下面改用正文更长的教学例子，便于看清回答区间；不是前面 Hi / Hello 主例的编码。
        所有 ID 和分词方式均为假设，真实分词以 tokenizer 为准。
            消息开始=1，消息结束=2，换行=3，user=4，assistant=5，PAD=0。
            bos_id=[1,5,3]，表示 assistant 消息头；eos_id=[2,3]，表示结束标记及换行。
            用户正文“请介绍你自己”：假设分成 请=10、介绍=11、你自己=12。
            助手正文“你好，我是 MiniMind，很高兴帮助你。”：
                假设分成 你好=20、，=21、我是=22、MiniMind=23、，=21、
                         很高兴=24、帮助=25、你=26、。=27，共 9 个 token。
            以下均假设已移除空 think 块，且没有额外 system 消息。

        【例 4A：单轮对话，完整保留较长的回答】

        对话内容：
            user：请介绍你自己
            assistant：你好，我是 MiniMind，很高兴帮助你。
        设置 max_length=26。

        明确的输入（一个列表，按消息和 PAD 分行展示）：

            input_ids = [
                1, 4, 3, 10, 11, 12, 2, 3,
                1, 5, 3, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
                0, 0, 0, 0
            ]

        按位置解释输入：
            位置 0～2   ：[1,4,3]，user 消息头。
            位置 3～5   ：[10,11,12]，用户正文“请介绍你自己”。
            位置 6～7   ：[2,3]，user 结束标记和换行。
            位置 8～10  ：[1,5,3]，assistant 消息头。
            位置 11～19 ：[20,21,22,23,21,24,25,26,27]，9 个回答正文 token。
            位置 20～21 ：[2,3]，assistant 结束标记和换行。
            位置 22～25 ：[0,0,0,0]，补齐用 PAD。

        处理过程：
            1. labels 初始化为 26 个 -100。
            2. i 从 0 开始逐位置扫描，在 i=8 时匹配到完整的 [1,5,3]。
            3. start=8+3=11，跳过 assistant 消息头，指向正文第一个 token“你好”。
            4. end 从 11 开始向后找；经过全部 9 个正文 token，在 end=20 找到 [2,3]。
            5. range(11, min(20+2,26)) = range(11,22)。
               注意 range 不含右端点：实际复制位置 11～21，共 11 个 token，
               即 9 个正文 token + 结束标记 + 换行。
            6. i 更新为 22，继续扫描剩余 PAD；它们不匹配 assistant 头。

        明确的输出（同样长 26，换行分组与输入对应）：

            labels = [
                -100, -100, -100, -100, -100, -100, -100, -100,
                -100, -100, -100, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
                -100, -100, -100, -100
            ]

        所以最终 labels[11:22] == input_ids[11:22]，其余位置全是 -100。
        用户正文仍存在于 input_ids 中供模型读取，只是不作为标签中的预测目标。
        模型之后移位计算损失：位置 10 的输出预测 labels[11]=20（你好），
        位置 11 的输出预测 labels[12]=21（逗号），依次学习整个回答和结束标记。

        【例 4B：两轮对话，分别保留两段回答】

        第一轮沿用例 4A；再追加第二轮：
            user：你能做什么？
            assistant：我可以回答问题，也可以帮助你学习。
        新增假设编码：
            用户正文：[30,31,32]，分别表示“你能”“做什么”“？”。
            助手正文：[40,41,42,21,43,25,26,44,27]，分别表示
                      “我可以”“回答”“问题”“，”“也可以”“帮助”“你”“学习”“。”。
        设置 max_length=44；两轮各 22 个 token，刚好填满，不需要 PAD。

        明确的输入（每两行是一轮对话）：

            input_ids = [
                1, 4, 3, 10, 11, 12, 2, 3,
                1, 5, 3, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
                1, 4, 3, 30, 31, 32, 2, 3,
                1, 5, 3, 40, 41, 42, 21, 43, 25, 26, 44, 27, 2, 3
            ]

        第一段回答：i=8，start=11，end=20，复制位置 11～21。
        处理完第一段后，i=22，继续越过第二轮 user 消息。
        第二段回答：i=30，start=33，end=42，复制位置 33～43。

        明确的输出：

            labels = [
                -100, -100, -100, -100, -100, -100, -100, -100,
                -100, -100, -100, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
                -100, -100, -100, -100, -100, -100, -100, -100,
                -100, -100, -100, 40, 41, 42, 21, 43, 25, 26, 44, 27, 2, 3
            ]

        两轮回答都参与监督，并非只学习最后一轮。
        如果 assistant 正文还含非空思考或工具调用，其 token 也在回答区间内，会被复制。

        【例 4C：回答中途被截断，与缺少结束标记的异常情况】

        情况一：正常按 max_length=17 截断例 4A。
        原序列只保留位置 0～16；回答只剩“你好，我是 MiniMind，很高兴”，
        后面的“帮助你。”和结束标记都已截掉，且当前长度已达 17，不补 PAD。

        明确的输入：

            input_ids = [
                1, 4, 3, 10, 11, 12, 2, 3,
                1, 5, 3, 20, 21, 22, 23, 21, 24
            ]

        start=11；找不到完整 [2,3]，end 最终等于输入长度 17。
        range(11, min(17+2,17)) = range(11,17)，只复制仍存在的 6 个正文 token。

        明确的输出：

            labels = [
                -100, -100, -100, -100, -100, -100, -100, -100,
                -100, -100, -100, 20, 21, 22, 23, 21, 24
            ]

        函数不会自动补回结束标记，也不会监督已截掉的内容。
        若截断后完全没有可监督的 assistant 正文或结束标记，则可能返回全 -100。

        情况二：异常输入缺少回答结束标记，却已经补 PAD 到 max_length=24。
        这里用于说明边界行为；正常模板会给完整 assistant 消息添加结束标记。

        明确的输入：

            input_ids = [
                1, 4, 3, 10, 11, 12, 2, 3,
                1, 5, 3, 20, 21, 22, 23, 21, 24, 25, 26, 27,
                0, 0, 0, 0
            ]

        start=11；没有找到结束标记，end 最终为 24。
        代码复制位置 11～23，没有单独判断 PAD，因此实际输出为：

            labels = [
                -100, -100, -100, -100, -100, -100, -100, -100,
                -100, -100, -100, 20, 21, 22, 23, 21, 24, 25, 26, 27,
                0, 0, 0, 0
            ]

        注意末尾是 0，不是 -100：这些 PAD 在该异常情况下也被当作监督目标。
        因此 PAD 保持 -100 依赖正常的回答边界匹配，此实现没有额外的 PAD 屏蔽步骤。
        正常由 __getitem__ 调用时 len(input_ids)==max_length；如果单独调用时传入
        更短、缺少结束标记的列表，复制上限还可能超过实际列表长度，导致 IndexError。
        '''
        # -100 是交叉熵损失的忽略值；先屏蔽所有位置，再开放 assistant 回复区间。
        labels = [-100] * len(input_ids)
        i = 0
        '''
        【下面逐行跟踪同一个例 4A】
        max_length=26，bos_id=[1,5,3]，eos_id=[2,3]。
        input_ids = [
            1, 4, 3, 10, 11, 12, 2, 3,
            1, 5, 3, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
            0, 0, 0, 0
        ]
        当前 labels 是 26 个 -100，i=0。
        变量分工：i 找回答头，start 记正文起点，end 找结束标记，j 逐个复制标签。
        注意：这些变量是列表下标，不是 token ID；例如 i=8 时 input_ids[i]=1。
        '''
        while i < len(input_ids):
            '''
            ① while：只要 i < 26，就继续扫描。
            第一次 i=0，条件为真；之后 i=1、2……也会进入循环。
            处理完回答后会直接跳到 i=22；扫描到 i=26 时退出。
            '''
            # 用完整的 token 序列匹配消息头，跳过角色标记本身，从回复正文开始监督。
            if input_ids[i:i + len(self.bos_id)] == self.bos_id:
                '''
                ② if：每次取从 i 开始的 3 个 token，与 [1,5,3] 整体比较。
                切片右端不包含在内，例如 [0:3] 取位置 0、1、2。
                外层循环依次检查的结果是：
                    i=0 -> input_ids[0:3]  = [1,4,3]   -> 不匹配，走下方 else。
                    i=1 -> input_ids[1:4]  = [4,3,10]  -> 不匹配。
                    i=2 -> input_ids[2:5]  = [3,10,11] -> 不匹配。
                    i=3 -> input_ids[3:6]  = [10,11,12]-> 不匹配。
                    i=4 -> input_ids[4:7]  = [11,12,2] -> 不匹配。
                    i=5 -> input_ids[5:8]  = [12,2,3]  -> 不匹配。
                    i=6 -> input_ids[6:9]  = [2,3,1]   -> 不匹配。
                    i=7 -> input_ids[7:10] = [3,1,5]   -> 不匹配。
                    i=8 -> input_ids[8:11] = [1,5,3]   -> 匹配，执行下面的赋值。
                所以不是看到消息开始 token 1 就认作回答，还必须匹配 assistant 和换行。
                '''
                start = i + len(self.bos_id)
                '''
                ③ start = 8 + 3 = 11。
                位置 8、9、10 是 assistant 头，跳过它们；
                位置 11 的 token 20（“你好”）才是回答正文的开始。
                '''
                end = start
                '''
                ④ end = 11。让结束边界的搜索从正文起点开始。
                start 固定保持 11，接下来只有 end 向后移动；此时 i 仍为 8。
                '''
                # 不断向后寻找当前 assistant 回复的结束标记。
                while end < len(input_ids):
                    '''
                    ⑤ 内层 while：当前 11 < 26，从位置 11 开始寻找结束标记。
                    内层循环专门找当前回答的结尾，不会推进外层的 i。
                    '''
                    if input_ids[end:end + len(self.eos_id)] == self.eos_id:
                        '''
                        ⑥ 每次检查从 end 开始的 2 个 token 是否等于 [2,3]：
                            end=11 -> [20,21]，不匹配。
                            end=12 -> [21,22]，不匹配。
                            end=13 -> [22,23]，不匹配。
                            end=14 -> [23,21]，不匹配。
                            end=15 -> [21,24]，不匹配。
                            end=16 -> [24,25]，不匹配。
                            end=17 -> [25,26]，不匹配。
                            end=18 -> [26,27]，不匹配。
                            end=19 -> [27,2]，不匹配。
                            end=20 -> [2,3]，匹配，执行 break。
                        此时 end 指向结束标记的起点，不是最后一个正文 token。
                        '''
                        break
                    '''
                    ⑦ 未匹配时执行 end += 1：11 -> 12 -> …… -> 20。
                    end=20 匹配后，break 直接退出最近的内层 while，
                    因此这次不再执行 end += 1；退出后 end 保持 20。
                    break 不会退出外层 while，也不会直接返回 labels。
                    '''
                    end += 1
                # 包含结束标记及其换行，让模型也学习结束回复；上限不超过 max_length。
                # 若没有找到结束标记，扫描会延伸到输入末尾，不能据此保证 padding 被屏蔽。
                # 把回答结束标记也作为监督目标，让模型学习何时停止；被截断的回答最多监督到 max_length。
                for j in range(start, min(end + len(self.eos_id), self.max_length)):
                    '''
                    ⑧ 代入得到 range(11, min(20+2,26))，即 range(11,22)。
                    j 依次为 11、12、……、21，不包含 22。
                    end+2 将位置 20 的结束标记和位置 21 的换行也包含进来。
                    '''
                    # 将回复区间的 token 复制为目标标签；其余位置保持 -100，不计算损失。
                    labels[j] = input_ids[j]
                    '''
                    ⑨ 上面一行在每次 for 循环中复制一个目标：
                        j=11 -> labels[11] = input_ids[11] = 20（你好）
                        j=12 -> labels[12] = input_ids[12] = 21（，）
                        j=13 -> labels[13] = input_ids[13] = 22（我是）
                        j=14 -> labels[14] = input_ids[14] = 23（MiniMind）
                        j=15 -> labels[15] = input_ids[15] = 21（，）
                        j=16 -> labels[16] = input_ids[16] = 24（很高兴）
                        j=17 -> labels[17] = input_ids[17] = 25（帮助）
                        j=18 -> labels[18] = input_ids[18] = 26（你）
                        j=19 -> labels[19] = input_ids[19] = 27（。）
                        j=20 -> labels[20] = input_ids[20] = 2（结束标记）
                        j=21 -> labels[21] = input_ids[21] = 3（换行）
                    labels 的其他位置没有被赋值，仍然是初始化时的 -100。
                    复制前后 input_ids 完全不变。
                    '''
                # 跳过已处理的回复，继续寻找下一轮 assistant 消息。
                i = end + len(self.eos_id) if end < len(input_ids) else len(input_ids)
                '''
                ⑩ 条件 20 < 26 成立，所以 i = 20+2 = 22。
                回答正文和结束标记已处理完，外层下一次从位置 22 开始，
                不必重新扫描位置 9～21。
                若没找到结束标记，end 会等于 len(input_ids)，走 else 将 i 设到末尾。
                '''
            else:
                '''
                ⑪ 这个 else 对应外层的“是否匹配 assistant 头”。
                开始时 i=0～7 不匹配，每次由下面的 i += 1 前进一步，最终走到 i=8。
                处理完回答后，剩余位置的检查结果为：
                    i=22 -> input_ids[22:25] = [0,0,0] -> 不匹配，i 变为 23。
                    i=23 -> input_ids[23:26] = [0,0,0] -> 不匹配，i 变为 24。
                    i=24 -> input_ids[24:27] = [0,0]   -> 不匹配，i 变为 25。
                    i=25 -> input_ids[25:28] = [0]     -> 不匹配，i 变为 26。
                Python 切片的右端越过末尾时只返回现有元素，这里不会因切片越界报错。
                '''
                i += 1
        '''
        ⑫ i=26 时，外层 while 的 26 < 26 为假，执行下面的 return。
        最终返回值为：
            labels = [
                -100, -100, -100, -100, -100, -100, -100, -100,
                -100, -100, -100, 20, 21, 22, 23, 21, 24, 25, 26, 27, 2, 3,
                -100, -100, -100, -100
            ]
        共 26 项：前 11 项忽略，接着 11 项监督回答及结束标记，最后 4 项忽略 PAD。
        '''
        return labels

    # 预处理对话、应用模板并编码补齐，返回 [T] token 和仅保留 assistant 区域的标签。
    def __getitem__(self, index):
        '''
        【例 5：dataset[0] 的完整数据流】
        1. 读取 self.samples[0]，得到 conversations 为 Hi / Hello 的样本。

           sample = self.samples[0]

           得到下面的 Python 字典（加载后的空字段用 None 表示）：

           {
               "conversations": [
                   {
                       "role": "user",
                       "content": "Hi",
                       "reasoning_content": None,
                       "tools": None,
                       "tool_calls": None
                   },
                   {
                       "role": "assistant",
                       "content": "Hello",
                       "reasoning_content": None,
                       "tools": None,
                       "tool_calls": None
                   }
               ]
           }

           sample 是整条样本的字典；sample['conversations'] 才是消息列表。
           sample['conversations'][0]['content'] 为 "Hi"，
           sample['conversations'][1]['content'] 为 "Hello"。
           下一步把这个包含两条消息的列表传给 pre_processing_chat。

        2. pre_processing_chat 默认对无 system 的普通对话以 20% 概率补 system。
           本次假设没有补充，因此消息列表仍为 [user: Hi, assistant: Hello]。
           若补充，system 文本也会进入输入、占用长度，但正常边界下不作为标签目标。
        3. create_chat_prompt 按例 3A 渲染带角色标记和空 think 块的字符串。
        4. post_processing_chat 默认以 80% 概率移除指定格式的空 think 块；
           本次假设移除，prompt 变为下面两个相邻字符串拼接的结果：
           "<|im_start|>user\\nHi<|im_end|>\\n"
           "<|im_start|>assistant\\nHello<|im_end|>\\n"
           因此同一个 index 多次读取，可能因随机预处理/后处理得到不同文本。
        5. tokenizer(prompt).input_ids 按假设得到 12 个 token：
           [1,4,3,10,2,3,1,5,3,11,2,3]

           【为什么第 4 步有两条消息，第 5 步却只有一个列表？】
           两条消息都还在，没有删掉其中一句。第 4 步展示的两个相邻字符串，
           表示同一个完整 prompt 的前后两段，不是分别送入模型的两个样本。
           tokenizer 对整个 prompt 编码，把两条消息按顺序放入一个 token 列表。
           “一个列表”表示一条对话序列，不表示里面只有一句话。

           按本例假设的 token ID，逐段对应如下：

               第一条消息（user）：
                   <|im_start|>user\\nHi<|im_end|>\\n
                   [1, 4, 3, 10, 2, 3]

                   1  -> <|im_start|>，消息开始
                   4  -> user，用户角色
                   3  -> 换行，角色头结束
                   10 -> Hi，用户正文
                   2  -> <|im_end|>，消息结束
                   3  -> 换行

               第二条消息（assistant）：
                   <|im_start|>assistant\\nHello<|im_end|>\\n
                   [1, 5, 3, 11, 2, 3]

                   1  -> <|im_start|>，消息开始
                   5  -> assistant，助手角色
                   3  -> 换行，角色头结束
                   11 -> Hello，助手正文
                   2  -> <|im_end|>，消息结束
                   3  -> 换行

               两段在同一个列表中连续排列：
                   [1, 4, 3, 10, 2, 3,  1, 5, 3, 11, 2, 3]
                    └── user 的 6 个 ─┘  └─ assistant 的 6 个 ─┘

           因此总长度是 6 + 6 = 12，Hi 对应的 10 和 Hello 对应的 11 都保留了。
           角色和结束标记也编码在序列里，用于区分两条消息的边界。
           这里按消息拆开只是为了讲解；实际代码直接编码完整 prompt，
           不会先分别编码再手动拼接。真实分词粒度以 tokenizer 的结果为准。

           [:16] 保留全部；若编码后有 20 个 token，则只保留前 16 个。
           本例只有 12 个 token，小于 max_length=16，所以这一步没有截掉任何消息；
           下一步只是再补 4 个 PAD。截断按 token 数进行，不按句子数或消息条数进行。
           与 PretrainDataset 预留 BOS/EOS 位置不同，此处直接截断整个模板序列，
           所以末尾的回答或消息结束标记都可能被截掉。
        6. 补 16-12=4 个 PAD，得到 input_ids：
           [1,4,3,10,2,3,1,5,3,11,2,3,0,0,0,0]
        7. generate_labels 按例 4A 生成：
           [-100,-100,-100,-100,-100,-100,-100,-100,-100,11,2,3,
            -100,-100,-100,-100]
        8. 返回 (torch.tensor(input_ids, dtype=torch.long),
                 torch.tensor(labels, dtype=torch.long))。
           两者都是 int64，形状各为 [16]；取两个样本组批后各为 [2,16]。
           本函数返回两个张量，不返回 attention_mask，也不在这里计算 loss。
        
        【标签为什么与 input_ids 同位置，却能训练“预测下一个 token”？】
        数据集返回未移位的 labels；模型内部使用 logits[..., :-1, :]
        对齐 labels[..., 1:]，所以位置 t 的输出预测位置 t+1 的 token。
        在本例中，真正有监督的三项是：
        t=8：看到完整 user 消息和 assistant 消息头 -> labels[9]=11（Hello）。
        t=9：再看到 Hello                       -> labels[10]=2（结束标记）。
        t=10：再看到结束标记                    -> labels[11]=3（换行）。
        t=11：下一个位置为 PAD，labels[12]=-100，因此忽略该项损失。
        “看到”指当前位置及之前的整个上下文，不是只用当前位置的一个 token。
        PretrainDataset 通常监督所有非 PAD 文本目标；这里通过 labels 掩码，
        只让 assistant 回复及其结束标记成为训练目标，用户问题仍作为输入上下文。
        '''
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


# AI 反馈强化学习（RLAIF）：提供待续写的对话提示词，回复由训练期间的模型生成。
# 为 PPO/GRPO 提供待续写的 prompt；回答由在线采样生成。
'''
【RLAIFDataset 类：把已有对话变成“让模型重新回答”的提示词】
示例输入：假设 rlaif_demo.jsonl 有一条样本，内容如下（实际 JSONL 中写在同一行）：
    {"conversations": [
        {"role": "system", "content": "请简短回答。"},
        {"role": "user", "content": "1+1等于几？"},
        {"role": "assistant", "content": "等于2。"}
    ]}
调用：ds = RLAIFDataset("rlaif_demo.jsonl", tokenizer, thinking_ratio=1.0)。

第 1 步：构造 ds，读取文件，将这一行保存为 self.samples 中的一条记录。
第 2 步：调用 ds[0]，进入 __getitem__，取出 conversations 消息列表。
第 3 步：create_chat_prompt 先进行预处理。首条已经是 system，因此不随机补 system。
第 4 步：thinking_ratio=1.0，使 use_thinking=True；截取 conversations[:-1]，
        去掉原有答案“等于2。”，只把 system 和 user 两条消息送给聊天模板。
第 5 步：模板在提示词末尾添加 assistant 角色前缀和开放的 <think> 标签，
        告诉后续生成模型从这里继续，而不是把数据中的原答案当成训练标签。

示例输出：ds 是数据集对象，len(ds)=1；item=ds[0] 则得到：
    {"prompt": 下方所示的完整字符串, "answer": ""}
    <|im_start|>system
    请简短回答。<|im_end|>
    <|im_start|>user
    1+1等于几？<|im_end|>
    <|im_start|>assistant
    <think>

这里使用当前项目 tokenizer 的模板；字符串在最后的 <think> 后还有一个换行。

后续过程：PPO/GRPO 训练端把 prompt 分词、补齐和截断，再由策略模型生成新回答，
          然后用奖励规则或奖励模型评分；这些工作不在 RLAIFDataset 中执行。
数据区别：这里每条只有 conversations，不需要 RM/DPO 数据中的 chosen/rejected 对。
          answer="" 是接口占位，不表示要求模型生成空答案，也不是人为标注的奖励。
'''
class RLAIFDataset(Dataset):
    # 加载对话样本并保存思考模式概率；实际 token 长度截断由训练端处理。
    '''
    【RLAIFDataset.__init__：读取对话并记录配置】
    示例输入：jsonl_path="rlaif_demo.jsonl"，文件有两条记录：
        第 0 条 conversations=[system("请简短回答。"), user("1+1等于几？"), assistant("等于2。")]
        第 1 条 conversations=[user("你好"), assistant("你好，有什么可以帮你？")]
    上面的 role("内容") 是消息字典的简写，实际文件使用 {"role":..., "content":...}。
    其他参数：tokenizer=当前项目分词器，max_length=8，thinking_ratio=0.5。

    第 1 步：super().__init__() 初始化 Dataset 基类。
    第 2 步：将 tokenizer、8、0.5 分别保存到 self.tokenizer、self.max_length、
            self.thinking_ratio，供后面的处理访问。
    第 3 步：load_dataset('json', ..., split='train') 读入两条记录，
            self.samples 的行数变成 2；这里没有自动划出验证集，也没有过滤样本。
    第 4 步：拼出 tokenizer.bos_token + 'assistant'，当前字符串为：
            '<|im_start|>assistant'（注意这里没有角色后的换行）。
            使用当前项目 tokenizer 编码得到 self.bos_id=[1,1388,570,811]。
    第 5 步：编码 tokenizer.eos_token，即 '<|im_end|>'，得到 self.eos_id=[2]。
            这些编号取决于 tokenizer，上述具体值来自当前项目的分词器。

    输出/副作用：self.samples 保存两条原始对话，配置及 bos_id/eos_id 已写入实例。
                __init__ 本身返回 None；RLAIFDataset(...) 构造表达式返回 ds 实例。
    注意：此时没有生成 prompt，也没有对完整样本做 token 编码。
          max_length=8 仅被保存，不会在此处截断对话或保证后续 prompt 只有 8 个 token。
          bos_id/eos_id 虽然被计算并保存，但本类后面的三个方法没有使用它们。
    '''
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
    '''
    【RLAIFDataset.__len__：查询对话样本数量】
    示例输入：假设 ds.samples 中有两行，第 0 行含 3 条消息，第 1 行含 2 条消息。
    调用：count=len(ds)。
    第 1 步：Python 自动调用 ds.__len__()。
    第 2 步：len(self.samples) 统计数据集行数，得到 2。
    示例输出：整数 2；这里按“对话样本”计数，不按消息总数返回 5，也不统计 token 数。
              调用 len 不渲染模板、不生成回答，也不会消耗 thinking 模式的随机数。
    '''
    def __len__(self):
        return len(self.samples)

    # 将结构化消息渲染成分词器的聊天模板，保留本训练阶段需要的角色边界。
    '''
    【RLAIFDataset.create_chat_prompt：预处理 → 去掉旧答案 → 拼接待生成前缀】
    示例输入：self.thinking_ratio=0.5；conversations 为：
        [
            {"role": "system", "content": "请简短回答。"},
            {"role": "user", "content": "1+1等于几？"},
            {"role": "assistant", "content": "等于2。"}
        ]

    第 1 步：pre_processing_chat 检查首条已经是 system，直接保留原消息列表。
            在这个无工具的示例中，预处理不会再抽取“是否补 system”的随机数。
    第 2 步：假设接下来的 random.random() 返回 0.3。
            0.3 < thinking_ratio=0.5 成立，因此 use_thinking=True。
    第 3 步：conversations[:-1] 得到前两条消息，移除旧答案“等于2。”。
            这是切片产生的新列表，不是从原始样本里永久删除最后一条消息。
    第 4 步：调用 apply_chat_template，并设置：
            tokenize=False：返回字符串，而不是 token 编号；
            open_thinking=True：在待生成回答开头保留开放的思考标签；
            add_generation_prompt=True：在历史后添加 assistant 角色前缀。
    示例输出：下面的一个完整字符串（开头没有排版缩进，末尾含一个换行）：
        <|im_start|>system
        请简短回答。<|im_end|>
        <|im_start|>user
        1+1等于几？<|im_end|>
        <|im_start|>assistant
        <think>
    输出中没有“等于2。”；未来回答的内容由在线生成决定。

    分支 A：仍是同样输入，若第 2 步随机数是 0.8，则 0.8<0.5 不成立。
            system/user 部分相同，但当前 tokenizer 会把末尾改成下面这些内容：
        <|im_start|>assistant
        <think>

        </think>

    精确的末尾结构：assistant 后换行，<think> 后两个换行，</think> 后两个换行。
    因此 open_thinking=False 在当前模板下是“预填一个空且闭合的思考块”，
    并不是完全不出现 think 标签；模型从闭合块之后继续生成。

    分支 B：若输入只有 [user("1+1等于几？"), assistant("等于2。") ]，
            预处理默认先以 0.2 的概率补 system。假设这次判断抽到 0.1，
            并随机选中“你是一个专业的AI助手，请提供有价值的回答。”，
            列表就变成 [新增 system, 原 user, 原 assistant]。
            随后另一次 random.random() 才决定 thinking 模式；假设返回 0.8，
            use_thinking=False，再去掉末尾答案，输出“新增 system + user + 闭合思考前缀”。
            两处概率判断用途不同，不应把它们当成同一个随机判断。

    多轮情况：输入 [user1, assistant1, user2, assistant2]，切片后保留前三条，
              assistant1 是历史的一部分；只移除最后的 assistant2。
    输入约定：列表非空、最后一条是待重新生成的旧答案。本方法不会验证末尾角色，
              如果误传以 user 结尾的列表，它也会将最后一个问题切掉。
    '''
    def create_chat_prompt(self, conversations):
        conversations = pre_processing_chat(conversations)
        # 每次取样独立决定是否开启思考模式，由聊天模板解释 open_thinking 参数。
        # 随机选择是否预填充开放的 think 标签；只渲染历史，留给在线策略生成新的回答。
        use_thinking = random.random() < self.thinking_ratio
        # 约定最后一条消息为原有答案：去掉它，只保留上下文供模型重新生成。
        # add_generation_prompt=True 在末尾添加 assistant 生成前缀。
        return self.tokenizer.apply_chat_template(
            conversations[:-1],
            tokenize=False,
            open_thinking=use_thinking,
            add_generation_prompt=True
        )
    # 返回待续写提示和空 answer 占位；这里不把离线答案当作本轮训练目标。
    '''
    【RLAIFDataset.__getitem__：按索引取得训练端需要的 prompt/answer 字典】
    示例输入：index=0、self.thinking_ratio=1.0；self.samples[0] 为：
        {"conversations": [
            {"role": "system", "content": "请简短回答。"},
            {"role": "user", "content": "1+1等于几？"},
            {"role": "assistant", "content": "等于2。"}
        ]}
    调用：item=ds[0]。
    第 1 步：Python 调用 __getitem__(0)，self.samples[0] 返回上面的样本字典。
    第 2 步：sample['conversations'] 取出三条消息，不是直接拿到问题字符串。
    第 3 步：交给 create_chat_prompt；保留已有 system，去掉末尾旧答案，
            thinking_ratio=1.0 使当前模板在最后加入开放的 <think> 标签。
    第 4 步：将返回的 prompt 字符串与固定占位 answer="" 组成字典。
    示例输出：{"prompt": P, "answer": ""}，其中 P 的完整内容是：
        <|im_start|>system
        请简短回答。<|im_end|>
        <|im_start|>user
        1+1等于几？<|im_end|>
        <|im_start|>assistant
        <think>
    P 的最后还有一个换行；返回值不含 token 张量、监督标签或奖励分数。

    后续组批示例：若 DataLoader 一次取到 ds[0]、ds[1]，默认组批可得到：
        {"prompt": [P0,P1], "answer": ["",""]}。
    PPO 再对 batch['prompt'] 分词，而不是用这里的 answer 字段作为真实答案训练。
    随机性：默认 thinking_ratio=0.5，且无 system 时还可能随机补 system，
            所以反复 ds[0] 的 prompt 可能不同；索引相同并不保证提示词逐字相同。
    '''
    def __getitem__(self, index):
        sample = self.samples[index]
        prompt = self.create_chat_prompt(sample['conversations'])

        # answer 当前固定为空字符串，是返回格式中的占位字段，不是样本里的标准答案。
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
