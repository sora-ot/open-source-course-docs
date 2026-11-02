# LLaMAFactory 源码讲解提纲与关键代码


> 重点：PT、SFT、RM、DPO、KTO、PPO 的训练原理与代码实现，模型加载，Full/Freeze/LoRA，多模态处理，Gradio WebUI，以及完整训练链路。

---

# 第一部分：项目总览

## 一、目标



1. 一条训练命令如何进入 LLaMAFactory，并最终调用 `Trainer.train()`？
2. PT、SFT、RM、DPO、KTO、PPO 分别使用什么数据、优化什么目标？
3. 同一个模型如何切换 Full、Freeze、LoRA 三种微调方式？
4. 图片、视频、音频如何进入语言模型的训练 batch？
5. Gradio WebUI 如何把页面配置转换成真正的训练进程？


---

## 二、

| 内容 | 讲解重点 |
|---|---|
| 项目定位与总训练链 | LLaMAFactory 是训练编排框架，不是重新实现 Transformer |
| PT | 连续文本、packing、next-token prediction |
| SFT | 对话模板、prompt mask、只训练 assistant 回答 |
| RM | 成对偏好数据、Value Head、pairwise ranking loss |
| DPO | policy/reference log-ratio、直接偏好优化 |
| KTO | 单条好坏反馈、KL 基线、非配对偏好数据 |
| PPO | 在线生成、Reward Model、Value Head、裁剪更新 |
| 模型加载与微调 | AutoModel、Full、Freeze、LoRA |
| 多模态 | MM Plugin、Processor、占位符、多模态 Collator |
| Gradio WebUI | 组件、事件、子进程、日志监控 |
| 总结 | 两条对齐路线和统一代码骨架 |


---

## 三、项目整体结构



```text
src/llamafactory/
├── cli.py                       # 命令行入口
├── launcher.py                  # train、webui、chat 等命令分发
├── hparams/                     # 参数定义和解析
├── data/
│   ├── loader.py                # 统一数据集入口
│   ├── template.py              # 对话模板
│   ├── mm_plugin.py             # 多模态模型适配
│   ├── collator.py              # batch 组装
│   └── processor/
│       ├── pretrain.py          # PT 数据处理
│       ├── supervised.py        # SFT 数据处理
│       ├── pairwise.py          # RM/DPO 成对偏好数据
│       ├── feedback.py          # KTO 好坏反馈数据
│       └── unsupervised.py      # PPO 等无标准回答数据
├── model/
│   ├── loader.py                # tokenizer、processor、model 加载
│   ├── adapter.py               # Full、Freeze、LoRA
│   └── patcher.py               # 模型兼容性修补
├── train/
│   ├── tuner.py                 # 所有训练阶段的总调度入口
│   ├── pt/
│   ├── sft/
│   ├── rm/
│   ├── dpo/
│   ├── kto/
│   └── ppo/
└── webui/
    ├── interface.py             # Gradio Blocks 页面
    ├── engine.py                # WebUI 控制中心
    ├── runner.py                # 启动/监控训练进程
    └── components/              # Train、Eval、Chat、Export 页面组件
```

### 3.1 总训练链路

```text
CLI 命令 / WebUI 配置
        ↓
get_train_args
拆分 ModelArguments、DataArguments、TrainingArguments、FinetuningArguments
        ↓
run_exp → _training_function
        ↓
根据 stage 分发到 run_pt / run_sft / run_rm / run_dpo / run_kto / run_ppo
        ↓
load_tokenizer + get_template + get_dataset + load_model
        ↓
DatasetProcessor → DataCollator → Custom Trainer
        ↓
trainer.train()
        ↓
checkpoint、adapter/value head、metrics、trainer state、loss 曲线
```

### 3.2 两种入口：CLI 与 WebUI

上图第一行的“CLI 命令 / WebUI 配置”并不是抽象概念，而是两种进入**同一条训练链路**的实际操作方式。

#### A. CLI 入口：从终端启动 YAML 配置

先进入项目目录并激活已安装 LlamaFactory 的 Python/Conda 环境：

```powershell
cd D:\study\Python_Project\selfstudy\27llamafactory\LlamaFactory
conda activate llamafactory  # 环境名称以本机实际名称为准
```

然后执行训练命令：

```powershell
llamafactory-cli train examples/train_lora/qwen3_lora_sft.yaml
```

其中三部分的含义是：

| 部分 | 含义 |
|---|---|
| `llamafactory-cli` | 项目安装时注册的命令行程序，进入 `src/llamafactory/launcher.py`。 |
| `train` | 告诉 `launcher.py` 进入训练分支；`sft` 也是 `stage=sft` 时的等价训练命令。 |
| `examples/...yaml` | 训练配置文件。模型、数据、LoRA、学习率等字段都在这里。 |

例如一个最小 LoRA SFT 配置的关键字段为：

```yaml
### model
model_name_or_path: Qwen/Qwen3-8B
flash_attn: fa2

### method
stage: sft
finetuning_type: lora
lora_target: all

### dataset
dataset: alpaca_en_demo
template: qwen3

### train
per_device_train_batch_size: 2
gradient_accumulation_steps: 8
learning_rate: 5.0e-5
bf16: true
output_dir: saves/qwen3-lora-sft
```

执行后，命令行的调用链是：

```text
llamafactory-cli train config.yaml
    ↓
launcher.py 根据 "train" 分发
    ↓
train.tuner.run_exp(config.yaml)
    ↓
get_train_args(config.yaml)
    ↓
run_pt / run_sft / run_rm / run_dpo / run_kto / run_ppo
```

#### B. WebUI 入口：从浏览器填写同一份训练参数

启动网页界面：

```powershell
llamafactory-cli webui
```

终端会打印访问地址，通常是：

```text
http://127.0.0.1:7860
```

浏览器打开该地址后，在页面顶部选择模型、模板、微调方式；在 **Train** 页选择数据集、LoRA 参数、batch size、学习率和输出目录，最后点击 **Start**。

WebUI 控件和 YAML 字段是一一对应的：

| WebUI 位置 | 页面字段 | 对应 YAML/训练参数 |
|---|---|---|
| 顶部公共设置 | Model path | `model_name_or_path` |
| 顶部公共设置 | Finetuning type | `finetuning_type` |
| 顶部公共设置 | Booster → `flashattn2` | `flash_attn: fa2` |
| Train | Training stage | `stage` |
| Train | Dataset | `dataset` |
| Train | Cutoff length | `cutoff_len` |
| Train | Batch size | `per_device_train_batch_size` |
| Train | Gradient accumulation steps | `gradient_accumulation_steps` |
| Train | Learning rate | `learning_rate` |
| Train | Compute type → `bf16` | `bf16: true` |
| Train → LoRA | LoRA rank | `lora_rank` |
| Train → LoRA | LoRA target → `all` | `lora_target: all` |
| Train | Output dir | `output_dir` |

WebUI 的 **Preview command** 按钮可以先生成等价命令，便于核对网页配置；而点击 **Start** 后，WebUI 并不在 Gradio 进程内直接训练，而是执行：

```text
页面控件
  ↓
Runner._parse_train_args：控件值 → 参数字典
  ↓
save_cmd(args)：保存为配置文件
  ↓
Popen(["llamafactory-cli", "train", "config.yaml"])
  ↓
与 CLI 启动完全相同的 tuner/workflow/Trainer 链路
```

训练总入口在 [`src/llamafactory/train/tuner.py`](src/llamafactory/train/tuner.py)：

```python
def _training_function(config):
    model_args, data_args, training_args, finetuning_args, generating_args = get_train_args(args)

    if finetuning_args.stage == "pt":
        run_pt(...)
    elif finetuning_args.stage == "sft":
        run_sft(...)
    elif finetuning_args.stage == "rm":
        run_rm(...)
    elif finetuning_args.stage == "ppo":
        run_ppo(...)
    elif finetuning_args.stage == "dpo":
        run_dpo(...)
    elif finetuning_args.stage == "kto":
        run_kto(...)
```

这段代码说明：六种训练共享外围基础设施，主要差异集中在数据处理器、Collator、模型头和 Trainer 的 loss 中。

---

## 四、六种训练方法总览

| 阶段 | 数据形式 | 训练信号 | 是否需要参考模型 | 是否需要 RM | 主要目的 |
|---|---|---|---:|---:|---|
| PT | 原始连续文本 | 下一个 token | 否 | 否 | 学习语言与领域知识 |
| SFT | prompt + 标准回答 | answer token 标签 | 否 | 否 | 学习指令遵循和回答格式 |
| RM | prompt + chosen/rejected | 回答排序 | 否 | 自己就是 RM | 学会给回答打分 |
| DPO | prompt + chosen/rejected | 相对偏好 | 需要 | 否 | 直接把偏好写入语言模型 |
| KTO | prompt + 好/坏单条回答 | desirable 标签 | 需要 | 否 | 使用非配对反馈做对齐 |
| PPO | prompt + 在线生成 | 标量 reward 与 advantage | 需要 | 需要 | 最大化奖励模型评分 |

两条典型对齐路线：

```text
传统 RLHF：PT → SFT → RM → PPO

直接偏好：PT → SFT → DPO / KTO
```

---

# 第二部分：训练原理与代码实现

## 一、PT：Pre-Training / Continued Pre-Training

### 1.1 PT 解决什么问题
![alt text](.\images\image.png)
PT 的数据通常是书籍、网页、论文或某个领域的大规模无标注文本。它不要求“问题—答案”结构，而是**让模型根据前文预测下一个 token**。

例如：

```text
糖尿病是一组以高血糖为特征的代谢性疾病。
```

Token 化后：

```text
[BOS, 糖尿病, 是, 一组, 以, 高血糖, 为, 特征, ..., EOS]
```

这里展示的是便于人阅读的 **token 片段**，还不是模型真正接收的数值输入。完整过程还包括“编码”和“向量化”：

```text
原始文本
  ↓ Tokenize（切分）
[BOS, 糖尿病, 是, 一组, ... , EOS]
  ↓ Encode（查询 tokenizer 词表）
[1, 34567, 1024, 25678, ... , 2]     # input_ids，示例编号；真实编号由模型词表决定
  ↓ Embedding（查询可训练的词向量表）
[[0.12, -0.38, ...], [...], ...]     # 每个 token ID 变成一个 hidden_size 维向量
  ↓
Transformer + LM Head
  ↓
每个位置“下一个 token”的概率分布
```

因此要区分三个概念：

| 名称 | 结果 | 是否直接送给 Transformer |
|---|---|---|
| Tokenize（分词） | `糖尿病`、`高血糖` 等 token 片段 | 否，只是中间语义表示。 |
| Encode（编码） | `[1, 34567, 1024, ...]` 等 `input_ids` 整数 | 是，作为模型输入的离散索引。 |
| Embedding（嵌入） | 每个 ID 对应的浮点向量 | 是，Transformer 实际计算的向量输入。 |

`BOS`和`EOS`也是特殊 token；编码后同样是词表中的整数 ID。不同模型使用不同 tokenizer，所以“糖尿病”可能被切成一个 token，也可能被切成多个子词/字节 token，ID 也不会相同。

训练目标：

$$
\mathcal{L}_{PT}
=
-\sum_{t=1}^{T}\log p_\theta(x_t\mid x_{<t})
$$

也就是：

```text
输入：     [BOS, 我, 爱, 学习]
目标：           [我, 爱, 学习, EOS]
```

流程
```
原始数据集样本
↓
messages[0]["content"]
↓
普通 Python 字符串
↓
tokenizer(...)
↓
input_ids、attention_mask 等整数列表
↓
DataCollator 拼 batch、补齐
↓
PyTorch Tensor
↓
模型 Embedding 层查表
↓
浮点向量
↓
Transformer
```

### 1.2 PT 完整代码链

先建立总览：后面的数据处理、packing、labels、loss 和评估，都是这条调用链中的一个环节。

```text
run_exp
  ↓ stage="pt"
run_pt
  ↓
load_tokenizer
  ↓
get_template_and_fix_tokenizer
  ↓
get_dataset(stage="pt")
  ↓
PretrainDatasetProcessor
  ↓
DataCollatorForLanguageModeling(mlm=False)
  ↓
CustomTrainer.train()
```

关键文件：

- [`src/llamafactory/train/pt/workflow.py`](src/llamafactory/train/pt/workflow.py)：PT 工作流。
- [`src/llamafactory/data/processor/pretrain.py`](src/llamafactory/data/processor/pretrain.py)：文本拼接、截断和 packing。
- [`src/llamafactory/train/pt/trainer.py`](src/llamafactory/train/pt/trainer.py)：自定义优化器、调度器、FP8、BAdam 等扩展。

### 1.3 PT 数据处理

入口：[`src/llamafactory/data/processor/pretrain.py`](src/llamafactory/data/processor/pretrain.py)

首先取出文本并补 EOS：

```python
text_examples = [
    messages[0]["content"] + eos_token
    for messages in examples["_prompt"]
]
```

未开启 packing 时，每条文本独立 tokenize 和截断：

```python
result = self.tokenizer(
    text_examples,
    add_special_tokens=False,
    truncation=True,
    max_length=self.data_args.cutoff_len,
)
```

这种方式简单，但短样本需要大量 padding。

### 1.4 PT Packing

`packing=True`的目标是把许多长短不一的PT文档尽可能装满固定长度的训练 block，减少`<pad>`浪费。它的完整流程是：

```text
每篇原始文本
  ↓ 在结尾追加 EOS
逐篇 tokenize 为 token IDs
  ↓ 首尾拼接为一条连续 token 流
按 cutoff_len（即 block_size）切成等长 block
  ↓
每个 block 成为一条 PT 训练样本
```

#### Step 1：每篇文档追加`EOS`

在[`pretrain.py`](src/llamafactory/data/processor/pretrain.py) 中，先取出每篇原始文本并在尾部添加结束token：

```python
eos_token = "<|end_of_text|>" if self.data_args.template == "llama3" else self.tokenizer.eos_token
text_examples = [messages[0]["content"] + eos_token for messages in examples["_prompt"]]
```

概念上，三篇文档变成：

```text
doc_1：t₁, t₂, ..., t₁₂, EOS
doc_2：t₁₃, t₁₄, ..., t₂₀, EOS
doc_3：t₂₁, t₂₂, ..., t₃₀, EOS
```

`EOS`让模型知道“上一篇文档在这里结束”。后续训练块可以跨文档边界，但模型会在边界位置见到这个明确的分隔token。

#### Step 2：分别编码，再拼接为连续 token 流

首先对每篇文档分别tokenize；此处不截断，也不让tokenizer自动添加额外特殊 token：

```python
tokenized_examples = self.tokenizer(text_examples, add_special_tokens=False)
concatenated_examples = {
    k: list(chain(*tokenized_examples[k]))
    for k in tokenized_examples.keys()
}
```

拼接后的`input_ids`可以理解为：

```text
[t₁ ... t₁₂, EOS, t₁₃ ... t₂₀, EOS, t₂₁ ... t₃₀, EOS, ...]
       └─ doc_1 ─┘  └─ doc_2 ─┘  └─ doc_3 ─┘
```

#### Step 3：仅保留完整block，再定长切块

`block_size`就是配置里的`cutoff_len`，例如 2048。源码会先向下取整，只保留能凑成完整 block 的 token 数：

```python
total_length = len(concatenated_examples["input_ids"])
block_size = self.data_args.cutoff_len
total_length = (total_length // block_size) * block_size
```

然后按 `cutoff_len` 切成固定长度 block：

```python
result = {
    k: [t[i : i + block_size] for i in range(0, total_length, block_size)]
    for k, t in concatenated_examples.items()
}
```

例如 `cutoff_len=8` 时：

```text
拼接后的 token 流：
[t₁, t₂, t₃, EOS, t₄, t₅, EOS, t₆, t₇, t₈, t₉, EOS, t₁₀, t₁₁, t₁₂, ...]

                ↓ 按每 8 个 token 切分

chunk 0：[t₁, t₂, t₃, EOS, t₄, t₅, EOS, t₆]
chunk 1：[t₇, t₈, t₉, EOS, t₁₀, t₁₁, t₁₂, ...]
```

如果最后剩余的 token 数少于 8：

```text
尾部：[tₓ, tᵧ, EOS]  # 不足一个完整 chunk
```

该尾部不会被 padding 成长度 8，而是会被丢弃。因此每个留下的 chunk 都是等长的：

```text
[batch_size, cutoff_len]
```

> 严格说，`preprocess_dataset` 是按数据集map的一个batch调用的，所以这里的“尾部丢弃”发生在每个预处理batch的末尾；它不是把整个语料库先汇总成唯一一条全局长流再只丢弃一次。

#### Step 4：可能在每个block首位补`BOS`

对设置了 `tokenizer.add_bos_token=True` 的 tokenizer，LlamaFactory 会将每个 packed block 的第一个 token 替换为 `BOS`：

```python
for i in range(len(result["input_ids"])):
    result["input_ids"][i][0] = self.tokenizer.bos_token_id
```

因此`BOS`是否出现取决于tokenizer配置；不是所有PT模型都会自动加入它。

#### Packing与padding的关系

| 场景 | 是否跨文档/样本拼接 | 是否通常需要padding |
|---|---|---|
| PT，`packing=true` | 会，以 `EOS` 分隔 | 基本不需要 |
| PT，`packing=false` | 不会 | 通常需要 |
| SFT，`packing=false` | 不会 | 通常需要 |
| SFT，`packing=true` | 可以，但必须保留每段prompt/answer的label mask| 通常较少需要 |

Packing的优点是减少padding、提高有效token比例和GPU利用率。它不表示“PT永远不需要padding”，而是表示 **启用 PT packing 后，完整 block 几乎不需要 padding**。

### 1.5 PT 标签在哪里构造

PT workflow 使用 Hugging Face 的语言模型 Collator：

```python
data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False,
)
```

`mlm=False`不用Masked Language Modeling，而是做Causal/Next-token Language Modeling。

#### 1.5.1 Processor 和 Collator 为什么都要用 tokenizer？

两者职责不同，**并没有把同一段中文重复分词两次**：

```text
PretrainDatasetProcessor：一条文本 → 一条已编码样本
DataCollator：多条已编码样本 → 一个等长的 PyTorch batch
```

在 `PretrainDatasetProcessor` 中，tokenizer 的输入是字符串列表。当前 PT 代码先为每一条文本手动补 `eos_token`，再关闭 tokenizer 自动添加特殊 token：

```python
text_examples = [
    messages[0]["content"] + eos_token
    for messages in examples["_prompt"]
]

result = tokenizer(
    text_examples,
    add_special_tokens=False,
    truncation=True,
    max_length=cutoff_len,
)
```

例如（ID 仅为示意，实际值由具体模型词表决定）：

```text
Tokenizer 输入：
["糖尿病是一种疾病。<eos>", "高血糖需要及时处理。<eos>"]

Tokenizer 输出（Dataset 中每条样本的字段）：
{
  "input_ids": [
    [34567, 1024, 25678, 2],
    [56789, 67890, 23456, 78901, 13, 2]
  ],
  "attention_mask": [
    [1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1]
  ]
}
```

这里为了突出后续 padding，刻意让样本 A 长度为 4、样本 B 长度为 6；ID 仅为示意，实际模型的切分结果和 ID 值由其 tokenizer 决定。这里完成的是：**文本 → token 片段 → 词表 ID (`input_ids`)**。模型不会直接接收“糖尿病”这几个汉字；之后它会使用 Embedding 表把每个整数 ID 查询成一个浮点向量，才进入 Transformer。

`DataCollatorForLanguageModeling`的输入则已经是多条`input_ids`，例如：

```text
沿用上一节 tokenizer 的输出：
样本 A：{"input_ids": [34567, 1024, 25678, 2]}
样本 B：{"input_ids": [56789, 67890, 23456, 78901, 13, 2]}
```

它再次持有 tokenizer，主要是为了读取`pad_token_id`、`padding_side`等配置，并调用`tokenizer.pad(...)`把不同长度样本补成规则矩阵；不是重新执行中文分词和ID编码：

```text
Collator 输出：
input_ids =
[
  [34567, 1024, 25678,    2, <PAD>, <PAD>],
  [56789, 67890, 23456, 78901,    13,     2]
]

attention_mask =
[
  [1, 1, 1, 1, 0, 0],
  [1, 1, 1, 1, 1, 1]
]
```

`<PAD>`表示tokenizer所定义的padding token；它实际对应哪个整数ID，由具体模型的tokenizer决定。

开启`packing=True`后，Processor 已将文本拼接并切为相同长度的block，Collator通常几乎不需padding；但仍负责把多条样本堆叠为Tensor并构造训练标签。

#### 1.5.2 `labels = input_ids.clone()` 为什么能训练下一个 token？

当`mlm=False`时，Collator 近似执行：

```python
labels = input_ids.clone()
```

它还会把`labels`中对应`PAD`的位置改为`-100`，使其不参与 loss：

```text
沿用样本 A：
input_ids = [34567, 1024, 25678, 2, <PAD>, <PAD>]
labels    = [34567, 1024, 25678, 2, -100,  -100]
```

`clone()`只是复制出一份可独立修改的目标序列。真正的“预测下一个 token”发生在Causal Language Model的loss计算中：logits 和 labels会错开一位。

```text
完整序列：          [BOS, 糖尿病, 是, 疾病, EOS]

当前位置模型可见：   [BOS]             [BOS, 糖尿病]      [BOS, 糖尿病, 是]  ...
要求预测的标签：      糖尿病             是                 疾病              EOS
```

近似等价的内部计算为：

```python
shift_logits = logits[:, :-1, :]  # 每个位置预测“下一个 token”的分数
shift_labels = labels[:, 1:]      # 丢弃第一个标签，向左错开一位
loss = cross_entropy(shift_logits, shift_labels, ignore_index=-100)
```

因此`labels`最初与`input_ids`相同并不等于泄露答案：因果注意力掩码保证模型在当前位置看不到未来token；训练时只是将当前位置的预测与真实的下一个token比较。

> 注：当前PT Processor显式补的是`EOS`，并使用 `add_special_tokens=False`。上面展示`BOS`的序列仅用于解释“错一位”的概念；不能把`BOS`当作这段PT代码必然自动加入的token。

#### 1.5.3 PT 与 SFT：同样预测下一个 token，label mask 不同

PT和SFT最终都会把 `input_ids`、`labels` 送入同一种 Causal Language Model，并采用同样的“一位错位 + cross entropy”机制。两者在**进入模型后的监督信号**上，最关键的区别是：SFT是否屏蔽了prompt token。

```text
PT（连续文本预训练）：
input_ids: [t₀, t₁, t₂, ..., tₙ]
labels:    [t₀, t₁, t₂, ..., tₙ]       ← 整段有效token都计算loss

SFT（指令微调）：
input_ids: [<bos>, p₁, ..., pₖ, r₁, ..., rₘ, <eos>]
                     └─ prompt ─┘  └─ response ─┘
labels:    [-100,  -100, ..., -100, r₁, ..., rₘ, <eos>]
                                             ← 仅response计算loss
```

其中：

- `p₁ ... pₖ`：system、user 问题、角色标记等 prompt token；
- `r₁ ... rₘ`：assistant 的标准回答 token；
- `-100`：PyTorch 交叉熵的 `ignore_index`，代表该位置不产生loss和梯度；
- `<bos>`、`<eos>` 是否存在，以及实际token长什么样，取决于模型tokenizer与对话模板。上图只是结构示意。

以一条指令数据为例：

```text
用户：什么是糖尿病？
助手：糖尿病是一种以高血糖为特征的代谢性疾病。
```

经过 SFT 模板编码后，模型的输入可理解为：

```text
input_ids：
[系统/角色标记, 用户, 什么是糖尿病, ？, 助手, 糖尿病是一种..., EOS]

labels：
[-100,        -100, -100,          -100, -100, 糖尿病是一种..., EOS]
```

这意味着SFT并不训练模型去“复述用户的问题”；它训练模型在看到prompt后，提升生成正确assistant回答的概率。

| 对比维度 | PT | SFT |
|---|---|---|
| 原始数据 | 书籍、网页、论文、领域文本等连续文本 | prompt + 标准assistant回答的对话数据 |
| `input_ids` | 文本token序列 | 按对话模板拼接的prompt + response token 序列 |
| `labels` | 通常复制全部`input_ids`，仅忽略padding | prompt位置为 `-100`，仅回答位置保留真实token ID |
| 哪些token计算loss | 全部有效文本token | 仅assistant response token |
| 希望模型学到什么 | 语言规律、事实知识、领域分布 | 指令遵循、回答格式、任务行为 |

因此，“两阶段在数据/loss 层面的唯一差异是 prompt mask”只适用于**已经完成数据格式化和token编码之后的因果LM监督张量**。在更上游，PT 与 SFT 还存在原始数据形式、对话模板、样本边界和 packing 策略等重要差异。

### 1.6 从logits到参数更新

到这一步，DataCollator已经产生一个batch，例如：

```text
input_ids      shape: [B, T]
attention_mask shape: [B, T]
labels         shape: [B, T]
```

其中`B`是 batch size，`T`是序列长度。模型接收`input_ids`后，会先经 Embedding 和多层 Transformer，最后由LM Head输出：

$$
\text{logits}\in\mathbb{R}^{B\times T\times V}
$$

`V`是词表大小。也就是说，batch中每条序列的每个位置都会得到一个长度为`V`的向量：

```text
logits[b, t] = [-0.2, 1.8, 0.5, ..., 3.2, ..., -1.0]  # shape: [V]
```

这个向量的每一项是“词表中某个token作为下一个token的原始得分”，还不是概率；它可以为负，也不要求总和为1。

#### 1.6.1 logits 如何变成“正确 token 的 loss”

从数学上说，位置 `t` 的logits会经 softmax 变成概率分布：

$$
p_t=\operatorname{softmax}(\text{logits}_t),\qquad
p_{t,i}=\frac{\exp(\text{logits}_{t,i})}{\sum_j\exp(\text{logits}_{t,j})}
$$

如果真实的下一个token ID是 `k_t`，那么该位置的交叉熵为：

$$
\mathcal{L}_t=-\log p_t[k_t]
$$

这里的下标必须先分清：

| 符号 | 含义 |
|---|---|
| $t$ | 序列中的当前位置。 |
| $V$ | 词表大小，即当前位置可选的 token 总数。 |
| $i$ 或 $j$ | 词表中任意一个候选 token 的 ID；求和符号 $\sum_j$ 表示枚举词表中所有候选 ID。 |
| $k_t$ | 位置 $t$ 的**真实目标 token ID**，由 `labels` 给出。 |
| $z_{t,i}$ | 位置 $t$ 对候选 token $i$ 的 logit；$z_{t,k_t}$ 就是对真实 token 的那一个 logit。 |

例如，假设词表只有 5 个 token，当前位置真实目标是 ID 为 3 的 token：

```text
候选 token ID：     0      1      2      3      4
logits[t]：       0.2   -0.1    1.3    2.0   -0.4
                                      ↑
                               k_t = 3，真实 token

z_{t,k_t} = z_{t,3} = 2.0
```

因此 softmax 的分子只取真实 token 的分数 $e^{z_{t,k_t}}=e^{z_{t,3}}$，而分母 $\sum_j e^{z_{t,j}}$ 要累加 0 到 4 的所有候选 token 分数。

直觉上：模型给正确 token 的概率越接近 1，loss 越接近 0；给正确 token 的概率越小，loss 越大。

```text
logits[t]                         → softmax 后的概率
[-0.2, 1.8, 0.5, ..., 3.2, ...]  → [0.01, 0.08, 0.02, ..., 0.45, ...]
                                                        ↑
                                      真实 token 的 ID 为 k_t，概率为 0.45

该位置 loss = -log(0.45)
```

将 softmax 概率代入单个 token 的 loss，可以把它完全写成 logits 的函数：

$$
\mathcal{L}_t
=
-\log\frac{e^{z_{t,k_t}}}{\sum_j e^{z_{t,j}}}
=
-z_{t,k_t}+\log\sum_j e^{z_{t,j}}
$$

其中 $z_{t,i}=\text{logits}_{t,i}$。这个展开式把“正确 token 的分数”与“整个词表所有 token 的分数”直接联系起来，也是后面求梯度的起点。

数学推导中可以把 `labels` 看成 $V$ 维 one-hot 向量；但代码里不会真的创建 one-hot 矩阵，而是只存一个整数 token ID。`torch.nn.functional.cross_entropy` 会根据该 ID 取出正确类别对应的 log probability，因此显存和计算更高效。

实际训练也不需要先手写 `softmax(logits)`：`cross_entropy` 内部融合了 `log_softmax + NLLLoss`，直接接收原始 logits 能避免数值溢出。

#### 1.6.2 因果错位、`-100` 与 batch 平均 loss

对 Causal LM，位置 `t` 的输出预测的是位置 `t+1` 的 token。因此先按前面 `1.5.2` 的逻辑错开 logits 和 labels，再计算交叉熵。概念代码为：

```python
shift_logits = logits[:, :-1, :]  # [B, T-1, V]
shift_labels = labels[:, 1:]      # [B, T-1]

loss = F.cross_entropy(
    shift_logits.reshape(-1, vocab_size),
    shift_labels.reshape(-1),
    ignore_index=-100,
)
```

`labels=-100` 的位置会被 `ignore_index=-100` 排除。PT中它通常是 padding；SFT中它还包括prompt。因此最终 loss 是**所有有效 next-token 位置**的平均，而非简单地对batch中每一个`B×T`位置平均：

$$
\mathcal{L}
=
-\frac{1}{|\Omega|}
\sum_{(b,t)\in\Omega}
\log p_\theta\left(k_{b,t}\mid x_{b,<t}\right)
$$

$$
\Omega
$$ 
是未被 `-100` 屏蔽的有效token位置集合。

当前Transformers版本的实现与上面“切掉最后一个logits”的伪代码略有不同：它会在labels右侧补一个 `-100` 后右移labels，保留全部logits；最后一个logits对应 `-100`，同样不参与loss，数学效果相同。具体实现在 `transformers/loss/loss_utils.py` 的 `ForCausalLMLoss`。

#### 1.6.3 loss 如何变成梯度

loss 是一个标量，也是反向传播的起点。自动求导会应用链式法则，从 LM Head 一直向前计算每个可训练参数的偏导数：

```text
loss
  ↓ backward（链式法则）
LM Head
  ↓
最后一层 Transformer Block
  ↓
中间 Transformer Blocks
  ↓
Embedding / 可训练 Adapter
  ↓
每个可训练参数 W 得到 W.grad
```

对单个位置的 logits，交叉熵有一个很重要的局部梯度形式：

$$
\frac{\partial\mathcal{L}_t}{\partial\text{logits}_{t,i}}
=p_{t,i}-\mathbb{1}[i=k_t]
$$

它由上一节的展开式直接求导得到。对词表中任意第 $i$ 个 logit $z_{t,i}$：

$$
\frac{\partial\mathcal{L}_t}{\partial z_{t,i}}
=
-\mathbb{1}[i=k_t]
+
\frac{e^{z_{t,i}}}{\sum_j e^{z_{t,j}}}
$$

后半部分正是 softmax 概率 $p_{t,i}$，所以：

$$
\frac{\partial\mathcal{L}_t}{\partial\text{logits}_{t,i}}
=p_{t,i}-\mathbb{1}[i=k_t]
$$

$\mathbb{1}[i=k_t]$ 是指示函数。“$i=k_t$”的意思是：**当前正在求导的候选 token ID $i$，是否正好等于真实目标 token ID $k_t$**。相等时指示函数为 1，不相等时为 0。沿用上面的例子，$k_t=3$：

```text
i = 0、1、2、4：i ≠ k_t，因此 𝟙[i = k_t] = 0
i = 3：          i = k_t，因此 𝟙[i = k_t] = 1
```

若对整个 batch 的平均 loss 求导，以上单 token 梯度还会整体除以有效 token 数 $|\Omega|$。

这表示：正确 token 的预测概率若不够高，梯度会推动它的 logit 上升；错误 token 概率过高时，梯度会推动它们的 logit 下降。后续链式法则再把这个误差信号传回所有前面的矩阵参数。

#### 1.6.4 学习率调度：Warmup + Cosine Decay

`W.grad` 只给出更新方向；学习率 `lr` 决定每一步沿该方向走多远。学习率过大容易跨过较优位置，过小则收敛很慢。

若配置为：

```yaml
learning_rate: 1.0e-4
lr_scheduler_type: cosine
warmup_ratio: 0.03
```

则训练进度大致是：
![alt text](./images/image-4.png)
```text
lr
│       peak_lr
│      /─────────\
│     /           \    cosine decay
│    /             \____ end_lr（接近 0）
└───┴──────────────────────── step
    warmup（前 3% steps）
```

- **Warmup**：前 `warmup_ratio × 总更新步数` 内，学习率从接近 0 升至 `learning_rate`，避免刚开始梯度和优化器状态都不稳定时更新过猛。
- **Cosine Decay**：之后按余弦曲线逐渐降低学习率，让后期更新更细。`1%～3%` 是常见 warmup 起点，不是固定规则。

这不是 `load_model()` 中的逻辑。`CustomTrainer.create_scheduler()` 会先调用 `create_custom_scheduler(...)` 处理 `warmup_stable_decay` 等 LLaMAFactory 扩展，再由 Transformers 父类按 `lr_scheduler_type` 创建普通调度器；因此只有设置 `lr_scheduler_type: cosine` 才会使用 cosine。

在 LlamaFactory 的 PT 流程里，训练由：

```python
train_result = trainer.train(...)
```

启动，位置在 [`src/llamafactory/train/pt/workflow.py`](src/llamafactory/train/pt/workflow.py)。`CustomTrainer` 继承 Hugging Face `Trainer`；实际训练循环使用 Accelerate 执行近似以下步骤：

```python
outputs = model(**batch)       # batch 中有 labels，因此模型返回 loss
loss = outputs.loss
accelerator.backward(loss)     # 计算并累积各参数的 .grad

# 达到 gradient_accumulation_steps 后才真正更新
optimizer.step()               # 例如 AdamW 利用 grad 更新可训练参数
lr_scheduler.step()            # 按训练进度更新学习率
optimizer.zero_grad()          # 清空本轮已使用的梯度
```

对应的 `CustomTrainer` 定义在 [`src/llamafactory/train/pt/trainer.py`](src/llamafactory/train/pt/trainer.py)，它会创建 LlamaFactory 支持的自定义 optimizer/scheduler；默认训练循环和 `backward/step` 位于 Transformers 的 `Trainer` 中。

#### 1.6.5 Full、LoRA 与参数更新的区别

从 `loss → gradient → optimizer.step()` 的数学流程看，Full Fine-Tuning 与 LoRA 没有区别；区别在于哪些参数允许拥有梯度并被 optimizer 更新：

| 微调方式 | 反向传播会经过 | 实际被更新的参数 |
|---|---|---|
| Full | 整个模型 | 所有（或几乎所有）原模型权重 |
| Freeze | 整个前向图 | 仅指定的未冻结层 |
| LoRA | 原模型层与 LoRA 支路 | LoRA 的低秩矩阵 `A/B`，原权重 `W` 冻结 |

所以 LoRA 的省显存关键在于：冻结的原始权重不需要保存 optimizer 状态和参数梯度；但前向计算仍然需要经过这些原始权重，误差信号也需要穿过相应计算图才能更新 LoRA 支路。

### 1.7 PT 怎么评估

#### 1.7.1 公式中的 L（eval_loss）是什么

公式里的 L 不是一个需要配置的超参数，也不是单个样本的 loss，而是模型在**验证集有效 token 上的平均负对数似然**，在代码输出中对应 `eval_loss`。

设验证集中第 b 条序列为：

$$
x^{(b)}_1,x^{(b)}_2,\ldots,x^{(b)}_{T_b}
$$

因果语言模型使用前面的 token 预测当前 token：

$$
p_\theta\!\left(x^{(b)}_t\mid x^{(b)}_{<t}\right)
$$

单个 token 的损失是：

$$
\ell_{b,t}
=
-\log p_\theta\!\left(x^{(b)}_t\mid x^{(b)}_{<t}\right)
$$

验证集损失可写成：

$$
\mathcal{L}_{eval}
=
-\frac{1}{N}
\sum_{(b,t)\in\Omega}
\log p_\theta\!\left(x^{(b)}_t\mid x^{(b)}_{<t}\right)
$$

每个符号的含义如下：

| 符号 | 含义 |
|---|---|
| `θ` | 当前模型的可训练参数 |
| `b` | 验证集中的第 b 条序列 |
| `t` | 序列中的 token 位置 |
| `x_t^(b)` | 第 b 条序列在位置 t 的真实 token |
| `x_<t^(b)` | 第 b 条序列在位置 t 之前的所有 token |
| `p_θ(x_t given x_<t)` | 模型根据前文分配给正确 token 的概率；`given` 表示“条件为” |
| `Ω` | 所有真正参与 loss 的位置集合，不包括 padding 和标签为 `-100` 的位置 |
| `N = size(Ω)` | 集合 Ω 中元素的数量，也就是参与计算的有效 next-token 标签数量 |
| `log` | 自然对数，因此 loss 的单位可以理解为 nat/token |

所以，`L_eval` 的计算过程可以概括为：

```text
每个位置输出 vocabulary logits
        ↓ softmax
得到正确 token 的概率 p
        ↓ -log(p)
得到每个有效 token 的负对数似然
        ↓ 对有效位置求平均
得到 eval_loss，也就是公式中的 L
```

#### 1.7.2 `eval_loss` 是怎么得到的

LLaMAFactory 的 [`CustomTrainer.compute_loss()`](src/llamafactory/train/pt/trainer.py) 没有重新实现 PT 损失：

```python
@override
def compute_loss(self, model, inputs, *args, **kwargs):
    return super().compute_loss(model, inputs, *args, **kwargs)
```

因此实际调用链是：

```text
验证集样本
  ↓ DataCollatorForLanguageModeling
input_ids、attention_mask、labels
  ↓ CustomTrainer.compute_loss
Transformers Trainer.compute_loss
  ↓ model(**inputs)
具体 CausalLM 的 forward(labels=labels)
  ↓ causal shift + CrossEntropyLoss
每个 batch 的 loss
  ↓ trainer.evaluate()
聚合为 metrics["eval_loss"]
```

PT 工作流中的实际评估入口是：

```python
if training_args.do_eval:
    metrics = trainer.evaluate(metric_key_prefix="eval")
```

这里得到的 `metrics["eval_loss"]` 就是 PPL 公式中的 L。在常见的 PT packing 或等长 block 场景下，可以直接理解为所有验证 token 的平均负对数似然；如果验证 batch 中的有效长度差异很大，精确的跨 batch 聚合细节以当前 Transformers 版本的 `Trainer` 实现为准。

#### 1.7.3 为什么 PPL = exp(L_eval)

LLaMAFactory 根据验证集 loss 计算困惑度：

$$
\operatorname{PPL}
=e^{\mathcal{L}_{eval}}
$$

把 `L_eval` 的定义代入，可以得到：

$$
\begin{aligned}
\operatorname{PPL}
&=
\exp\left(-\frac{1}{N}\sum_{i=1}^{N}\log p_i\right)\\
&=
\left(\prod_{i=1}^{N}\frac{1}{p_i}\right)^{\frac{1}{N}}
\end{aligned}
$$

其中 `p_i` 是模型在第 i 个有效位置分配给正确 token 的概率。因此 PPL 是“正确 token 概率倒数的几何平均”，可以粗略理解为模型在每一步面临的有效选择数量。

例如：

```text
eval_loss = ln(4) ≈ 1.386
PPL       = exp(1.386) ≈ 4
```

这表示正确 token 的几何平均概率约为 `1/4 = 0.25`，而不是说模型每次真的只在四个 token 中选择。

#### 1.7.4 如何直观理解 PPL 与 loss
| 平均 loss（自然对数） | PPL = `exp(loss)` | 直觉解释 |
|---:|---:|---|
| 0.0 | 1.0 | 完美预测；对真实开放文本几乎不可能。 |
| 0.5 | 1.65 | 对正确 token 的几何平均概率约为 0.61。 |
| 1.0 | 2.72 | 等效于约 2～3 个候选中的不确定性。 |
| 2.0 | 7.39 | 等效于约 7 个候选中的不确定性。 |
| 3.0 | 20.09 | 等效于约 20 个候选中的不确定性。 |
| 4.0 | 54.60 | 等效于约 55 个候选中的不确定性。 |
| 10.0 | 22026.47 | 对真实 token 的平均概率极低，接近随机预测。 |

如果在完整词表大小为 $V$ 的所有 token 上严格均匀猜测，则 PPL 为 $V$。不过真实模型的词表通常是子词/字节词表，且评估时会受 tokenizer、文本领域、序列切分和 label mask 影响，因此不能把不同模型、不同数据或不同模板的 PPL 数值直接横向比较。


#### 1.7.5 如何阅读训练与验证 loss 曲线

每个训练 step 的 `loss` 是当前 batch 上的交叉熵，受 batch 数据、长度、随机顺序和 dropout 影响，因此会有噪声；`eval_loss` 才是在固定验证集上定期聚合得到的指标。健康训练最重要的是看**一段时间内的趋势**，而不是要求每一个 step 都下降。

| 观察到的现象 | 常见含义 | 建议 |
|---|---|---|
| train loss 总体下降，eval loss 也下降后趋于平缓 | 正常收敛 | 继续训练，结合下游验证决定何时停止。 |
| train loss 持续下降，eval loss 连续多次上升 | 可能过拟合或训练/验证分布不同 | 选择较早 checkpoint，减少 epoch，增加数据或正则化。 |
| 偶发单个 spike，随后恢复 | 某个 batch 较难、长度变化或正常随机波动 | 先观察，不必立刻停止。 |
| 反复大幅震荡、loss 变成 `NaN`/`inf` | 学习率过高、数值精度溢出、坏数据或实现问题 | 检查数据、学习率、BF16/FP16、梯度裁剪和日志。 |
| loss 长期几乎不下降且处于高位 | 学习率过小、标签/mask/模板错误、可训练参数设置不当或数据不匹配 | 先用少量数据过拟合测试，再检查配置。 |

“前期快速下降、后期逐渐变平”是常见形态，但不是固定规律；从什么数值开始、每 step 波动多少、何时进入平台期，都不能脱离模型是否已预训练、数据质量、batch size、学习率、阶段（PT/SFT）和训练时长单独判断。

#### 1.7.6 PPL 的代码到底在哪里

真正的换算代码位于 [`src/llamafactory/train/pt/workflow.py`](src/llamafactory/train/pt/workflow.py)：

```python
metrics = trainer.evaluate(metric_key_prefix="eval")

try:
    perplexity = math.exp(metrics["eval_loss"])
except OverflowError:
    perplexity = float("inf")

metrics["eval_perplexity"] = perplexity
trainer.log_metrics("eval", metrics)
trainer.save_metrics("eval", metrics)
```

如果配置了多个验证集，代码会分别读取：

```python
metrics[f"eval_{key}_loss"]
```

并生成：

```python
metrics[f"eval_{key}_perplexity"]
```

完整源码分工如下：

| 作用 | 代码位置 |
|---|---|
| 从训练集切分验证集 | [`src/llamafactory/data/data_utils.py`](src/llamafactory/data/data_utils.py) 中的 `split_dataset()` |
| PT 文本 token 化与 packing | [`src/llamafactory/data/processor/pretrain.py`](src/llamafactory/data/processor/pretrain.py) |
| 创建 labels、屏蔽 padding | Transformers 的 `DataCollatorForLanguageModeling`，在 PT workflow 中实例化 |
| 调用模型计算 loss | [`src/llamafactory/train/pt/trainer.py`](src/llamafactory/train/pt/trainer.py) 的 `compute_loss()`，继续调用父类 Trainer |
| causal shift 与交叉熵 | Transformers 中具体 `AutoModelForCausalLM` 对应模型的 `forward()`/Causal LM loss |
| `eval_loss` 聚合 | Transformers 的 `Trainer.evaluate()` |
| `eval_loss → PPL` | [`src/llamafactory/train/pt/workflow.py`](src/llamafactory/train/pt/workflow.py) 的 `math.exp(...)` |

#### 1.7.7 如何启用 PT 验证

可以从训练数据中切出 10% 作为验证集：

```yaml
stage: pt
do_train: true
do_eval: true
val_size: 0.1
per_device_eval_batch_size: 2
```

也可以使用 `eval_dataset` 指定独立验证集，但 `eval_dataset` 和 `val_size` 不能同时设置。评估结果会包含类似：

```text
eval_loss: 2.30
eval_perplexity: 9.97
```

PPL 越低，说明模型对该验证文本的 next-token 预测越好。不过比较 PPL 时必须尽量使用相同的验证集、Tokenizer、文本预处理方法和序列切分方式。PPL 下降也不一定等价于指令遵循、事实正确性或问答能力提升，这些能力还需要下游任务评测。

### 1.8 预训练后的Base Model：会续写，不等于可靠对话

PT 完成后得到的是**Base Model（基础模型）**。它在任意位置做的核心计算仍只有一件事：根据已有 token，为“下一个 token”给出概率分布。

```text
已有上下文 token
  ↓
Base Model 输出下一个 token 的 logits
  ↓
推理策略（greedy / top-k / top-p / temperature 等）选择一个 token
  ↓
将选中的 token 追加到上下文末尾
  ↓
重复，直到 EOS 或达到最大长度
```

从 logits 中选择下一个 token 的 greedy、top-k、top-p、temperature、beam search 等策略属于**推理阶段**；它们通常不改变模型参数，也不是 PT 的训练目标。

#### 1.9.1 Base Model 擅长什么

| 能力 | 为什么可能做到 | 示例 |
|---|---|---|
| 文本续写 | PT 直接训练 next-token prediction。 | `The capital of France is` → 续写 `Paris ...`。 |
| 语言规律与领域知识 | 从大规模文本中学习词、句子、事实和表达的统计关联。 | 根据医学文本续写疾病定义或常见描述。 |
| 模仿已有格式 | 若上下文提供了格式，模型会把它当作续写模式。 | `Q: ... A: ...` 后，可能继续生成一个 Q/A。 |
| In-Context Learning | prompt 中给出 few-shot 示例，模型可在本次上下文中模仿输入输出映射。 | `apple → pomme; bread → pain; cat →` 续写 `chat`。 |

In-Context Learning 不会更新参数；示例只是作为当前上下文的一部分，影响后续 token 的概率。

#### 1.9.2 Base Model 不保证什么

Base Model 并非“完全不能回答问题”，因为预训练语料可能已经包含问答、说明文或网页对话格式；但它**没有被专门优化为稳定地服从用户意图和聊天角色**。因此下面能力可能偶尔表现出来，却不可靠：

| 不保证的能力 | 常见问题 |
|---|---|
| 指令遵循 | 给出“翻译这句话”的提示后，可能继续补写更多指令、示例或原文，而不稳定地产出翻译。 |
| `user` / `assistant` 角色边界 | 可能继续生成用户消息，或混淆角色和轮次。 |
| 多轮对话一致性 | 没有专门学过对话模板、上下文角色和回答边界。 |
| 安全拒答与偏好对齐 | 没有明确训练“何时拒绝、如何拒绝、哪种回答更有帮助”。 |
| 稳定的结构化输出 | 仅靠提示可模仿 JSON、表格等格式，但不保证每次合法；通常还需 SFT、约束解码或校验重试。 |

因此下面两句话要区分：

```text
Base Model 可以“看起来像在回答问题”
≠
Base Model 被可靠训练成遵循指令的聊天助手
```

#### 1.9.3 从 Base Model 到 Chat / Instruct Model

```text
Base Model
  ↓ SFT：用 prompt → 标准 assistant response 学习角色、格式和任务行为
Instruct / Chat Model
  ↓ 偏好对齐（DPO、KTO、RM + PPO 等）：让更有帮助、安全、符合偏好的回答概率更高
Aligned Chat Model
```

SFT 主要解决“用户给出这类 prompt 时，assistant 应如何回答”；DPO、KTO、RM/PPO 等偏好对齐方法进一步解决“多个可能回答中，哪些更符合人类偏好”。这正是后续 SFT、RM、DPO、KTO 与 PPO 章节要展开的内容。

---

## 二、SFT：Supervised Fine-Tuning

### 2.1 SFT 解决什么问题
![alt text](.\images\image-1.png)
SFT 使用人工或强模型生成的“指令—标准回答”数据，让模型学会聊天格式和按要求回答。

```json
{
  "instruction": "解释什么是梯度下降",
  "output": "梯度下降是一种沿损失函数下降方向更新参数的方法。"
}
```

经过对话模板渲染后，实际输入类似：

```text
<system>你是一个有帮助的助手</system>
<user>解释什么是梯度下降</user>
<assistant>梯度下降是一种……</assistant>
```

#### 2.1.1 SFT 数据如何塑造能力

模型不会从一个抽象的“能力开关”中学习指令遵循或安全性；这些能力必须以输入—目标输出、偏好对或奖励信号的形式出现在训练数据和目标函数中。

| 希望获得的能力 | 行为示例 | 数据中通常如何体现 | 主要训练阶段 |
|---|---|---|---|
| 指令遵循 | 用户说“翻译这句话”，模型直接给出译文，而不是继续补写更多指令。 | 大量 `instruction/prompt → output/response` 样本；response 是对指令的直接完成。 | SFT |
| 格式输出 | 要列表就列点；要求 JSON 就给合法 JSON；要求代码就输出代码块。 | response 中明确包含目标格式；数据覆盖各种格式要求与对应答案。 | SFT；高可靠场景还需约束解码/校验 |
| 多轮一致性 | 后一轮能正确引用前文内容，理解“它”指代什么。 | 带 `system/user/assistant` 角色的多轮 message 列表；训练时将历史轮次作为上下文。ShareGPT、WildChat 等可提供原始多轮语料，但通常仍需清洗和筛选。 | SFT |
| 有害请求的拒答 | 用户请求制造危险物品时，模型拒绝并给出安全替代帮助。 | 包含有害 prompt → 安全拒答的 SFT 样本；更常见的是 chosen（安全、有帮助）/rejected（有害或不当）偏好对。 | 安全 SFT + 偏好对齐 |
| 推理风格 / CoT | 面对复杂问题先展示或内部完成分步推理，再给最终答案。 | 带推理过程和最终答案的 reasoning 数据，或带可验证结果的任务数据。是否向用户展示推理过程还取决于模型模板和产品策略。 | SFT；也可结合 RL/可验证奖励 |
| 风格与语气 | 客服式礼貌、专家式严谨、角色扮演人设等。 | 同类 prompt 配上目标风格的 response，通常也会通过 system prompt 标注角色约束。 | SFT |

需要区分“数据中出现过某种模式”和“模型能在所有场景可靠执行该模式”：前者是学习信号的来源，后者还取决于数据质量与覆盖度、模型容量、训练强度、推理模板，以及是否进行了偏好和安全对齐。

### 2.2 SFT 与 PT 的关键区别

SFT 中 prompt 通常只提供上下文，不参与 loss：

```text
input_ids = [system tokens, user tokens, assistant tokens]
labels    = [-100,         -100,        assistant tokens]
```

其中 `-100` 是 `IGNORE_INDEX`，交叉熵会忽略这些位置。

目标函数：

$$
\mathcal{L}_{SFT}
=
-\sum_{t\in\text{assistant answer}}
\log p_\theta(y_t\mid x,y_{<t})
$$

#### 2.2.1 为什么 SFT 的学习率通常比从头预训练小

SFT 不是从随机权重开始，而是在已经完成预训练的 Base Model 上做任务行为的定向调整。模型已有通用语言能力和大量知识；SFT 数据量通常更小、分布也更窄，因此更新过猛可能让模型过度偏向 SFT 数据分布，造成通用能力下降、输出模板化或灾难性遗忘。

不过“PT 的学习率一定比 SFT 大一个量级”不是普适定律：从头预训练、继续预训练（continued pre-training）、全参数 SFT 和 LoRA SFT 的可用学习率范围不同，且都会随 batch size、训练步数、模型大小和数据质量变化。

| 场景 | 参数初始状态 | 常见学习率倾向 | 原因 |
|---|---|---|---|
| 从头预训练 | 随机初始化 | 通常较大，但需要长 warmup | 参数要先从随机状态形成基本语言能力。 |
| 继续预训练（PT） | 已训练 Base Model | 通常小于从头预训练，具体取决于领域偏移和训练 token 数 | 既要吸收领域文本，也要尽量保留原有能力。 |
| 全参数 SFT | 已训练 Base Model | 通常较小，例如常从 `1e-6`～`2e-5` 量级试起 | 所有原参数都会更新，较大步长更容易破坏已有分布。 |
| LoRA SFT | Base Model 冻结，只训练 Adapter | 往往可更大，例如常从 `5e-5`～`2e-4` 量级试起 | 可训练参数较少，Adapter 通常需要更积极地适应任务。 |

一个常见的全参数 SFT 起点可以是：

```yaml
learning_rate: 1.0e-5
lr_scheduler_type: cosine
warmup_ratio: 0.03
```

而 LoRA SFT 可从更高学习率开始试验，例如：

```yaml
finetuning_type: lora
learning_rate: 1.0e-4
lr_scheduler_type: cosine
warmup_ratio: 0.03
```

这些只是起点，不是固定配方。实际应优先观察验证 loss、任务指标和生成样本：学习率过高时常见 loss 剧烈震荡、生成质量退化或过拟合；过低时 loss 长期下降很慢。`warmup` 用于让学习率从较小值平稳升至峰值，`cosine` 等调度器再让后期学习率逐渐降低。

### 2.3 数据处理与对话模板：LlamaFactory 如何把对话变成训练样本

SFT 原始数据只是字段和角色的结构化描述，模型并不能直接理解“谁在说话”。LlamaFactory 的核心工作是：**先把不同来源的数据统一为内部消息格式，再按当前模型匹配的 Template 渲染为 token IDs，最后只把 assistant 的目标 token 放进 labels。**

```text
原始 JSON / JSONL / Hub Dataset
  ↓ dataset_info.json 定义字段和角色名称
AlpacaDatasetConverter / SharegptDatasetConverter / OpenAIDatasetConverter
  ↓ 统一内部格式：_prompt、_response、_system、_tools、媒体字段
Template（由 template 参数或 tokenizer.chat_template 选择）
  ↓ Formatter 按角色拼接 + tokenizer 编码
SupervisedDatasetProcessor
  ↓ source_ids、target_ids → input_ids、labels
SFTDataCollator
  ↓ padding / 多模态张量 / attention mask
Trainer
```

#### 2.3.1 原始 SFT 数据可以长什么样

最常见的单轮 Alpaca 格式：

```json
{
  "instruction": "什么是大语言模型？",
  "input": "请用一句话回答。",
  "output": "大语言模型是基于大规模文本训练、能够预测和生成文本的神经网络模型。"
}
```

多轮 ShareGPT 风格：

```json
{
  "conversations": [
    {"from": "human", "value": "你好"},
    {"from": "gpt", "value": "你好！有什么可以帮助你？"},
    {"from": "human", "value": "推荐一本深度学习入门书。"},
    {"from": "gpt", "value": "可以从《动手学深度学习》开始。"}
  ]
}
```

也可以是 OpenAI 风格的 `messages`：

```json
{
  "messages": [
    {"role": "system", "content": "你是一个简洁的助手。"},
    {"role": "user", "content": "1 + 1 等于多少？"},
    {"role": "assistant", "content": "2"}
  ]
}
```

它们字段不同，但 LlamaFactory 不要求你先手工改成同一种 JSON；需要在 `dataset_info.json` 中声明格式、列名与角色 tag。例如本地 ShareGPT 文件可登记为：

```json
{
  "my_chat": {
    "file_name": "my_chat.json",
    "formatting": "sharegpt",
    "columns": {"messages": "conversations"},
    "tags": {
      "role_tag": "from",
      "content_tag": "value",
      "user_tag": "human",
      "assistant_tag": "gpt"
    }
  }
}
```

相关字段由 [`src/llamafactory/data/parser.py`](src/llamafactory/data/parser.py) 的 `DatasetAttr` 读取；示例配置可见 [`data/dataset_info.json`](data/dataset_info.json)。

#### 2.3.2 先统一数据格式

[`src/llamafactory/data/converter.py`](src/llamafactory/data/converter.py) 根据 `formatting` 选择不同 Converter：

| 原始格式 | Converter | 主要工作 |
|---|---|---|
| `alpaca` | `AlpacaDatasetConverter` | 将 `instruction` 与可选 `input` 合并为 user 内容；将 `output` 变为 assistant response；可读取 `history`。 |
| `sharegpt` | `SharegptDatasetConverter` | 将 `from/value` 等自定义角色字段映射为内部 `user/assistant/system/observation/function`；检查角色是否交替。 |
| `openai` | `OpenAIDatasetConverter` | 读取 `messages` 中的 `role/content` 结构，并转换为相同的内部角色表示。 |

无论原始格式如何，转换后的单条样本都接近：

```python
{
    "_prompt": [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "1 + 1 等于多少？"}
    ],
    "_response": [{"role": "assistant", "content": "2"}],
    "_system": "你是一个简洁的助手。",
    "_tools": "",
    "_images": null,
    "_videos": null,
    "_audios": null
}
```

这一步由 `align_dataset()` 完成。对于普通 SFT，最后一条 assistant 消息被视为 `_response`，此前所有轮次是 `_prompt`。因此后续训练代码只需要处理一套标准字段。

#### 2.3.3 Template：角色结构如何变成模型实际看见的文本

`template` 必须与底座模型训练时使用的聊天格式相匹配；把 Qwen、Llama、Gemma 等模型强行套同一个模板，角色边界 token 不匹配，训练和推理效果都会受影响。

模板选择入口是 [`get_template_and_fix_tokenizer()`](src/llamafactory/data/template.py)：

```text
YAML 中指定 template
  ↓
从 TEMPLATES 注册表取对应 Template

未指定 template
  ↓
尝试解析 tokenizer 自带的 chat_template
  ↓
仍没有时使用 empty Template
```

例如当前仓库的 `chatml` 模板在 [`template.py`](src/llamafactory/data/template.py) 中注册（搜索 `name="chatml"`），核心 slot 为：

```python
register_template(
    name="chatml",
    format_user=StringFormatter(slots=["<|im_start|>user\n{{content}}<|im_end|>\n<|im_start|>assistant\n"]),
    format_assistant=StringFormatter(slots=["{{content}}<|im_end|>\n"]),
    format_system=StringFormatter(slots=["<|im_start|>system\n{{content}}<|im_end|>\n"]),
    format_observation=StringFormatter(slots=["<|im_start|>tool\n{{content}}<|im_end|>\n<|im_start|>assistant\n"]),
    stop_words=["<|im_end|>", "<|im_start|>"],
    replace_eos=True,
    replace_jinja_template=True,
)
```

将上面的单轮对话渲染后，概念上是：

```text
<|im_start|>system
你是一个简洁的助手。<|im_end|>
<|im_start|>user
1 + 1 等于多少？<|im_end|>
<|im_start|>assistant
2<|im_end|>
```

`{{content}}` 是由 `Formatter.apply()` 替换的占位符。Template 并不只处理 `user/assistant/system`：还定义了 function、observation/tool、默认 system、停止词、思考标记、EOS 行为和多模态 Plugin 等模型差异。

`<|im_start|>`、`<|im_end|>` 这类标记只有在当前 tokenizer 词表中被注册为特殊 token 时，才通常对应单个 token ID；LlamaFactory 不假设任意字符串都只占一个 ID，而是通过 `tokenizer.encode(...)` 或 `convert_tokens_to_ids(...)` 转为实际 ID。`fix_special_tokens()` 会处理 EOS、PAD 和 stop words；若确实新增了词表 token，必须同时考虑 `resize_vocab: true`。

#### 2.3.4 从 Template 到 `source_ids` / `target_ids`

这一步涉及两个核心位置：

| 代码 | 位置 | 职责 |
|---|---|---|
| `Template.encode_multiturn()` | [`template.py`](src/llamafactory/data/template.py)（搜索 `def encode_multiturn`） | 调用模板渲染，并把多轮消息拆成每轮的 `(source_ids, target_ids)`。 |
| `Template._encode()` | [`template.py`](src/llamafactory/data/template.py)（搜索 `def _encode`） | 按角色选择 Formatter，将 system/user/assistant 等内容真正转换成 token IDs。 |
| `SupervisedDatasetProcessor._encode_data_example()` | [`supervised.py`](src/llamafactory/data/processor/supervised.py)（搜索 `def _encode_data_example`） | 接收标准化消息，调用 `encode_multiturn()`，再构造最终的 `input_ids` 与 `labels`。 |
| `SupervisedDatasetProcessor.preprocess_dataset()` | [`supervised.py`](src/llamafactory/data/processor/supervised.py)（搜索 `def preprocess_dataset`） | 对数据集的每条样本调用 `_encode_data_example()`，写出可供 Trainer 使用的列。 |

下面沿用 ChatML 的“`1 + 1 等于多少？ → 2`”例子，完整走一遍。为避免伪造某个模型的真实词表编号，下文将 `id(...)` 表示“该文本片段经当前 tokenizer 编码后得到的一个或多个 ID”。

**输入 `_encode_data_example()` 前：**

```python
prompt = [
    {"role": "user", "content": "1 + 1 等于多少？"},
]
response = [
    {"role": "assistant", "content": "2"},
]
system = "你是一个简洁的助手。"
tools = ""
```

注意：对**同一条样本**，`preprocess_dataset()` 只调用一次 `_encode_data_example()`；下面的“第 1～4 步”是在拆解这**同一次函数调用的内部过程**，不是重复调用该函数。

**第 1 步（函数内部）：合并消息并调用 Template。** 其关键调用是：

```python
messages = self.template.mm_plugin.process_messages(
    prompt + response, images, videos, audios, self.processor
)

encoded_pairs = self.template.encode_multiturn(
    self.tokenizer, messages, system, tools, discarding_history_cot
)
```

纯文本样本中 `process_messages()` 基本保持消息不变；多模态样本才会在这里插入图像/视频/音频占位符。

**第 2 步：`Template._encode()` 按角色渲染。** 简化后的关键源码逻辑是：

```python
if i == 0:
    elements += self.format_prefix.apply()
    if system or tools:
        elements += self.format_system.apply(content=system + tool_text)

if message["role"] == Role.USER:
    elements += self.format_user.apply(content=message["content"], idx=str(i // 2))
elif message["role"] == Role.ASSISTANT:
    elements += self.format_assistant.apply(content=message["content"])

encoded_messages.append(self._convert_elements_to_ids(tokenizer, elements))
```

对于这条单轮消息，ChatML 的 `format_user` 本身会在 user 内容后附加 assistant 的起始标记。因此 `_encode()` 得到两段，而不是只得到一整条无法区分边界的长字符串：

```text
encoded_messages[0] 对应 source 文本：
<|im_start|>system\n
你是一个简洁的助手。<|im_end|>\n
<|im_start|>user\n
1 + 1 等于多少？<|im_end|>\n
<|im_start|>assistant\n

encoded_messages[1] 对应 target 文本：
2<|im_end|>\n
```

编码后可写为：

```text
encoded_messages[0] = source_ids = [
  id("<|im_start|>"), id("system"), id("\n"),
  id("你是一个简洁的助手。"), id("<|im_end|>"), id("\n"),
  id("<|im_start|>"), id("user"), id("\n"),
  id("1 + 1 等于多少？"), id("<|im_end|>"), id("\n"),
  id("<|im_start|>"), id("assistant"), id("\n")
]

encoded_messages[1] = target_ids = [
  id("2"), id("<|im_end|>"), id("\n")
]
```

这里一个 `id("文本")` 可能展开为多个整数；只有已注册的特殊 token（例如某模型词表中的 `<|im_start|>`）通常才会是一个 ID。

**第 3 步：`encode_multiturn()` 配对。** 它的核心实现很短：

```python
encoded_messages = self._encode(tokenizer, messages, system, tools)
return [(encoded_messages[i], encoded_messages[i + 1]) for i in range(0, len(encoded_messages), 2)]
```

所以这个单轮例子返回：

```python
encoded_pairs = [(source_ids, target_ids)]
```

多轮时则返回多个 pair；每个 pair 的 source 都是该轮 user 侧模板片段，target 是紧随其后的 assistant 侧模板片段。`SupervisedDatasetProcessor` 再按原始轮次把它们拼回一条训练序列。

**第 4 步（仍在同一次函数调用内）：根据 `source_ids` / `target_ids` 构造可训练的 labels。** 默认设置 `train_on_prompt=False`、`mask_history=False` 时，关键代码逻辑是：

```python
source_label = [IGNORE_INDEX] * source_len
target_label = target_ids

input_ids += source_ids + target_ids
labels += source_label + target_label
```

因此最终逐位置对齐为：

```text
input_ids: [system/user/assistant 起始段的所有 ID,  id("2"), id("<|im_end|>"), id("\n")]
labels:    [-100, -100, ... , -100,              id("2"), id("<|im_end|>"), id("\n")]
                                                    └──── assistant target ────┘
```

这就是“模型看见完整 system + user + assistant 起始标记，但只因生成 `2<|im_end|>` 而得到 loss”的具体含义。下一节的 Label Mask 会进一步说明 `train_on_prompt`、`mask_history` 和截断时如何改变这个规则。

#### 2.3.5 自定义业务模板的原则

LlamaFactory 的模板并非只靠字符串常量：每个 Template 由 `format_user`、`format_assistant`、`format_system` 等 Formatter 组合而成，模板注册接口是 `register_template(...)`。需要支持新的模型聊天格式时，可在 [`template.py`](src/llamafactory/data/template.py) 中按其官方 token/角色边界注册 Template；若 tokenizer 自带标准 `chat_template`，也可让 LlamaFactory 自动解析。

优先使用与底座模型原生格式一致的 Template，而不是为业务场景随意发明新的 role token。业务身份、语气、固定规则等通常更适合作为 system 内容或 SFT 数据的一部分；新增模型未见过的特殊 token 会带来词表扩展、初始化和推理兼容性问题。

#### 2.3.6 Tokenizer 特殊 token、词表扩展与 `resize_vocab`

预训练 tokenizer 面向纯文本，词表里没有 <|im_start|> / <|im_end|>、没有"角色"概念。SFT 阶段往 tokenizer 里加新的特殊 token，分两类。



##### LlamaFactory 实际的 token 修正与加载顺序

训练入口 [`src/llamafactory/train/tuner.py`](src/llamafactory/train/tuner.py) 的顺序刻意是：

```text
load_tokenizer(model_args)
    ↓
patch_tokenizer(tokenizer, model_args)       # 处理 add_tokens / add_special_tokens
    ↓
get_template_and_fix_tokenizer(tokenizer, data_args)
    ↓
template.fix_special_tokens(tokenizer)       # EOS、PAD、模板 stop words
    ↓
load_model(tokenizer, model_args, ...)       # 必须在 tokenizer 修正之后
    ↓
Template._convert_elements_to_ids(...)       # 数据处理时真正编码为 input_ids
```


`Template.fix_special_tokens()` 的三种常见结果如下：

| 情况 | 实际动作 | 词表是否变大 | 是否需要 `resize_vocab` |
|---|---|---:|---:|
| tokenizer 已有正确的 EOS / stop words | 仅复用已有 ID | 否 | 否 |
| 没有 PAD | `tokenizer.pad_token = tokenizer.eos_token`，让 PAD 复用 EOS 的 ID | 否 | 否 |
| 模板要求的 EOS 或 stop word 不在词表 | 调用 `tokenizer.add_special_tokens(...)` 注册新 ID | 是 | 是 |

第二行很容易误解：LlamaFactory 常见的 “Add pad token” 日志并不一定真的新增词表行；这里通常只是把 `pad_token` **别名**设为现有 EOS token。

##### 真正想新增业务 token 时

例如确实需要模型把 `<|product_id|>` 当作固定结构标记，而它又不在底座词表中，可在训练配置中显式写：

```yaml
add_special_tokens: "<|product_id|>,<|order_id|>"
init_special_tokens: noise_init       # 默认：旧 embedding 均值附近加噪声
# 也可用 new_special_tokens_config + desc_init，按文字描述初始化
```

对应的 [`patch_tokenizer()`](src/llamafactory/model/patcher.py) 会执行：

```python
num_added = tokenizer.add_tokens(
    new_tokens=model_args.add_special_tokens,
    special_tokens=True,
)
if num_added > 0 and not model_args.resize_vocab:
    model_args.resize_vocab = True
```

也就是说，**通过 `add_special_tokens` 参数新增且确实新增成功时，当前 LlamaFactory 会自动把 `resize_vocab` 改为 `True`。** 但 Template 在 `fix_special_tokens()` 中发现缺失 EOS/stop word 时，只能发出“请确保 `resize_vocab=True`”的警告；因为它只拿到了 tokenizer，不能直接修改 `model_args`。看到这类警告时应在 YAML 中显式加入：

```yaml
resize_vocab: true
```

##### `resize_vocab` 到底修改了模型哪里

`load_model()` 随后调用 [`patch_model()`](src/llamafactory/model/patcher.py)，当 `model_args.resize_vocab=True` 时再调用 [`resize_embedding_layer()`](src/llamafactory/model/model_utils/embedding.py)：

```text
tokenizer:          原词表 V  →  V + k
input embedding:    [V, d]   →  [V + k, d]
lm_head（若未共享）: [V, d]   →  [V + k, d]
```

实现实际调用 `model.resize_token_embeddings(len(tokenizer), pad_to_multiple_of=64, ...)`，因此物理矩阵行数有时会为了硬件对齐向上补到 64 的倍数；不要机械地认为一定恰好是 `V+k`。新 token 的 input embedding，以及未与 input embedding 共享时的 output embedding，都会初始化。默认 `noise_init` 是在旧词向量均值附近加入小噪声；`new_special_tokens_config` 配合 `desc_init` / `desc_init_w_noise` 则可依据 token 的文字描述做语义初始化。

若使用 LoRA，新增 token 不能只靠 LoRA 的线性层来学习：新 embedding 行也必须可训练、可保存。当前 [`src/llamafactory/model/adapter.py`](src/llamafactory/model/adapter.py) 会在 `resize_vocab=True` 且未手工指定 `additional_target` 时，把 input/output embedding 加入 `modules_to_save`。量化模型则不能安全地 resize embedding，LlamaFactory 会直接拒绝这类组合。

最后，业务 token 不应该为了“看起来结构化”而滥加。产品 ID、订单号等若只是变量内容，放在正常文本或 JSON 字段中往往更合适；只有它真的是模型需要反复识别、生成、并承担控制语义的**固定边界标记**时，才值得扩词表，并要让训练数据的 assistant 目标中充分出现它。

### 2.4 Label Mask

默认不训练 prompt：

```python
if self.data_args.train_on_prompt:
    source_label = source_ids
else:
    source_label = [IGNORE_INDEX] * source_len

target_label = target_ids
```

最终：

```python
input_ids += source_ids + target_ids
labels += source_label + target_label
```

两个重要参数：

- `train_on_prompt=True`：system/user token 也计算 loss。
- `mask_history=True`：多轮对话中只训练最后一轮回答，历史回答只作为上下文。

### 2.5 SFT Collator

Workflow 创建：

```python
data_collator = SFTDataCollatorWith4DAttentionMask(
    template=template,
    model=model,
    label_pad_token_id=IGNORE_INDEX,
    block_diag_attn=model_args.block_diag_attn,
    neat_packing=data_args.neat_packing,
    **tokenizer_module,
)
```

它负责：

- batch padding；
- label padding；
- 多模态输入合并；
- packing 场景的块对角 attention mask；
- 某些视觉模型的位置编码。

### 2.6 `CustomSeq2SeqTrainer`：只看它额外改了什么

[`trainer.py`](src/llamafactory/train/sft/trainer.py) 继承 `Seq2SeqTrainer`，并没有重写普通 SFT 的 loss。`-100` labels 已由 `SupervisedDatasetProcessor` 构造；普通情况直接交还父类：

```python
def compute_loss(self, model, inputs, *args, **kwargs):
    if self.finetuning_args.use_asft_loss:
        ...  # 仅 ASFT 有额外 reference model loss
    else:
        return super().compute_loss(model, inputs, *args, **kwargs)
```

#### 2.6.1 生成式评估

当 `predict_with_generate=true` 时，验证集的 `input_ids` 只保留 prompt，参考答案位于 `labels`；`prediction_step()` 再调用父类生成。父类返回 `[prompt, 模型续写]`，LlamaFactory 用 PAD 覆盖前面的 prompt，使后续 decode / 指标只看到续写：

```python
if self.args.predict_with_generate:
    labels = inputs.pop("labels", None)
loss, generated_tokens, _ = super().prediction_step(...)
if generated_tokens is not None and self.args.predict_with_generate:
    generated_tokens[:, : inputs["input_ids"].size(-1)] = self.processing_class.pad_token_id
```

#### 2.6.2 `do_predict` 保存结果

`save_predictions()` 会将不能 decode 的 `-100` 先换成 PAD，再把 prompt、预测和参考答案写入：

```text
output_dir/generated_predictions.jsonl
{"prompt": "...", "predict": "模型续写", "label": "参考回答"}
```

训练异常时，先看这个文件，比只看 `eval_loss` 更直观。

### 2.7 SFT 完整代码链

```text
run_sft
  ↓
load_tokenizer + load processor
  ↓
get_template_and_fix_tokenizer
  ↓
get_dataset(stage="sft")
  ↓
SupervisedDatasetProcessor
  ↓
SFTDataCollatorWith4DAttentionMask
  ↓
CustomSeq2SeqTrainer
  ↓
train / evaluate / predict
```

关键文件：

- [`src/llamafactory/train/sft/workflow.py`](src/llamafactory/train/sft/workflow.py)：SFT 工作流。
- [`src/llamafactory/data/processor/supervised.py`](src/llamafactory/data/processor/supervised.py)：输入和 label 构造。
- [`src/llamafactory/data/collator.py`](src/llamafactory/data/collator.py)：多模态、packing、padding。
- [`src/llamafactory/train/sft/trainer.py`](src/llamafactory/train/sft/trainer.py)：训练、生成式评估、预测保存。

### 2.8 SFT 一句话总结

> PT 让模型学习整段文本分布；SFT 把 prompt 当条件，只重点学习 assistant 应该怎样回答。

---

## 三、RM：Reward Model


### 3.1 RM 为什么需要单独介绍

传统 RLHF 路线是：

```text
PT → SFT → RM → PPO
```

RM 的任务不是生成回答，而是给回答打分：

$$
r_\phi(x,y)\in\mathbb{R}
$$

对于人类更喜欢的回答，应满足：

$$
r_\phi(x,y_{chosen})
>
r_\phi(x,y_{rejected})
$$

### 3.2 RM 数据格式

RM 使用 pairwise 偏好数据：

```json
{
  "prompt": "如何礼貌拒绝加班？",
  "chosen": "我愿意配合紧急任务，但今晚已有安排……",
  "rejected": "我不加班，别找我。"
}
```

RM 与 DPO 共用 `PairwiseDatasetProcessor`：

```text
chosen_input_ids   = prompt_ids + chosen_ids
chosen_labels      = [-100 ... -100] + chosen_ids

rejected_input_ids = prompt_ids + rejected_ids
rejected_labels    = [-100 ... -100] + rejected_ids
```

入口：[`src/llamafactory/data/processor/pairwise.py`](src/llamafactory/data/processor/pairwise.py)

### 3.3 RM 模型结构

RM 是“Transformer 骨干 + Value Head”：

```text
prompt + response
        ↓
Transformer hidden states
        ↓
Value Head：Linear(hidden_size, 1)
        ↓
每个 token 的 value
        ↓
最后一个有效 token 的 value
        ↓
整条回答的 reward score
```

RM Workflow 中调用 LLaMAFactory 的统一模型加载入口：

```python
model = load_model(
    tokenizer,
    model_args,
    finetuning_args,
    training_args.do_train,
    add_valuehead=True,
)
```

这里的 `add_valuehead=True` 只是向 `load_model()` 传入一个开关，含义是：“最终返回的模型必须带 Value Head”。这一层是**调用者**，还没有直接创建 Value Head。

进入 [`src/llamafactory/model/loader.py`](src/llamafactory/model/loader.py) 后，`load_model()` 会先完成普通模型加载和 Adapter 初始化：

```python
# 1. 加载普通语言模型
model = load_class.from_pretrained(**init_kwargs)

# 2. 根据 finetuning_type 处理 Full、Freeze 或 LoRA
model = init_adapter(
    config,
    model,
    model_args,
    finetuning_args,
    is_trainable,
)
```

然后看到 `add_valuehead=True`，才执行真正的 Value Head 包装：

```python
if add_valuehead:
    model = AutoModelForCausalLMWithValueHead.from_pretrained(model)
    patch_valuehead_model(model)

    vhead_params = load_valuehead_params(vhead_path, model_args)
    if vhead_params is not None:
        model.load_state_dict(vhead_params, strict=False)
```

因此截图中的两段代码不是两次重复加载，也不是两种可选方案，而是同一次调用的外层和内层：

| 代码 | 所在层次 | 作用 |
|---|---|---|
| `load_model(..., add_valuehead=True)` | RM workflow，调用层 | 提出“加载完整可训练模型，并且需要 Value Head”的要求 |
| `AutoModelForCausalLMWithValueHead.from_pretrained(model)` | model loader，实现层 | 把已经加载并处理好 Adapter 的普通语言模型包装成带 Value Head 的 TRL 模型 |

这里 `from_pretrained(model)` 的参数是**已经加载好的模型对象**，而不是模型路径，所以通常不会重新下载或再加载一遍基座模型。包装后的结构为：

```text
AutoModelForCausalLMWithValueHead
├── pretrained_model：原来的 Causal LM，可能已经带 LoRA Adapter
└── v_head：Linear(hidden_size, 1)
```

完整调用关系是：

```text
run_rm()
  ↓
load_model(..., add_valuehead=True)        # LLaMAFactory 统一入口
  ↓
AutoModelForCausalLM.from_pretrained(...)  # 加载基座语言模型
  ↓
init_adapter(...)                          # Full / Freeze / LoRA
  ↓
AutoModelForCausalLMWithValueHead
    .from_pretrained(model)                # TRL 包装并增加 v_head
  ↓
加载已有 v_head 权重；若没有则使用新初始化的 Value Head
  ↓
返回“语言模型 + Value Head”给 PairwiseTrainer
```

如果 `add_valuehead=False`，`load_model()` 会跳过包装，返回普通语言模型，这适用于 PT、SFT、DPO 等不需要 value 输出的阶段。

### 3.4 `r_chosen` 和 `r_rejected` 是怎么得到的

它们是**同一个 Reward Model 对两条回答计算出的标量分数**：

```text
输入 1：同一个 prompt + chosen 回答
        ↓ 同一个 Transformer + 同一个 Value Head
输出：r_chosen

输入 2：同一个 prompt + rejected 回答
        ↓ 同一个 Transformer + 同一个 Value Head
输出：r_rejected
```

需要明确区分：

- `chosen/rejected` 是数据集提供的人类偏好标签；
- `r_chosen/r_rejected` 是 Reward Model 根据当前参数预测出来的分数；
- 它们不是 token 概率，也不是人工直接写入数据集的分数；
- 它们可以是任意实数，不要求位于 0～1，重点是两者的相对大小。

#### 3.4.1 从 hidden state 到标量 reward

设 `x` 是 prompt，`y_chosen` 和 `y_rejected` 是两条回答。Reward Model 分别编码：

$$
x\oplus y_{chosen}
\qquad\text{和}\qquad
x\oplus y_{rejected}
$$

其中 `⊕` 表示把 prompt 和回答按照对话模板拼接起来。Transformer 为每个 token 产生 hidden state，Value Head 再把 hidden state 从 `hidden_size` 维压缩成一个标量：

$$
v_t=\mathbf w_v^\top\mathbf h_t+b_v
$$

最后取两条序列最后一个有效 token 的 value：

$$
r_{chosen}
=
\mathbf w_v^\top
\mathbf h_{last}(x\oplus y_{chosen})
+b_v
$$

$$
r_{rejected}
=
\mathbf w_v^\top
\mathbf h_{last}(x\oplus y_{rejected})
+b_v
$$

符号含义：

| 符号 | 含义 |
|---|---|
| `h_last` | Transformer 在最后一个有效 token 位置输出的 hidden state |
| `w_v、b_v` | Value Head 的可训练权重和偏置 |
| `r_chosen` | 模型对 chosen 回答预测的整体质量分数 |
| `r_rejected` | 模型对 rejected 回答预测的整体质量分数 |
![alt text](.\images\image-2.png)
#### 3.4.2 源码中如何计算

`PairwiseDataCollatorWithPadding` 会把 batch 排成：

```text
前 B 条：prompt + chosen
后 B 条：prompt + rejected
```

[`PairwiseTrainer.compute_loss()`](src/llamafactory/train/rm/trainer.py) 先让带 Value Head 的模型为每个 token 输出一个 value：

```python
_, _, values = model(
    **inputs,
    output_hidden_states=True,
    return_dict=True,
    use_cache=False,
)

# values 的形状约为 [2 * batch_size, sequence_length]
```

然后把前后两半拆成 chosen 和 rejected：

```python
batch_size = inputs["input_ids"].size(0) // 2

chosen_masks, rejected_masks = torch.split(
    inputs["attention_mask"], batch_size, dim=0
)
chosen_rewards, rejected_rewards = torch.split(
    values, batch_size, dim=0
)
```

这里源码中的 `chosen_rewards` 和 `rejected_rewards` 仍然是**每个 token 一个 value 的序列**，还不是最终公式里的标量 reward。代码再根据 `attention_mask` 找到最后一个非 padding token：

```python
chosen_scores = chosen_rewards.gather(
    dim=-1,
    index=(chosen_masks.sum(dim=-1, keepdim=True) - 1),
)
rejected_scores = rejected_rewards.gather(
    dim=-1,
    index=(rejected_masks.sum(dim=-1, keepdim=True) - 1),
)

chosen_scores = chosen_scores.squeeze()
rejected_scores = rejected_scores.squeeze()
```

因此数学符号与代码变量的对应关系是：

```text
r_chosen   = chosen_scores
r_rejected = rejected_scores
```

之所以取最后一个有效 token，是因为因果注意力下，该位置的 hidden state 已经看过完整的 `prompt + response`，可以用来表示整条回答。padding 位置不包含真实内容，所以必须通过 `attention_mask` 排除。

### 3.5 RM 损失函数

本节公式里的 `r_chosen` 和 `r_rejected`，就是上一节得到的 `chosen_scores` 和 `rejected_scores`。代码使用 pairwise ranking loss：

$$
\mathcal{L}_{RM}
=
-\log\sigma
\left(
r_{chosen}-r_{rejected}
\right)
$$

对应源码：

```python
loss = -torch.nn.functional.logsigmoid(
    chosen_scores.float() - rejected_scores.float()
).mean()
```

它只约束相对排序，并不要求 reward 具有统一的绝对尺度。因此 `chosen=-0.2`、`rejected=-1.7` 也是正确排序。

### 3.6 RM 评估指标

主要指标是：

$$
\operatorname{accuracy}
=
\frac{\#(r_{chosen}>r_{rejected})}{N}
$$

这里的 `#` 表示“满足条件的样本数量”，不是 Python 中的注释符号。具体来说：

```text
#(r_chosen > r_rejected)
= 在全部偏好样本对中，chosen 分数高于 rejected 分数的样本对数量
```

其中（两个分数的计算过程见 3.4）：

- `r_chosen`：`prompt + chosen` 经过 Reward Model 后，最后一个有效 token 的 `chosen_scores`；
- `r_rejected`：`prompt + rejected` 经过同一个 Reward Model 后，最后一个有效 token 的 `rejected_scores`；
- `N`：参与评估的偏好样本对总数；
- `#(...)`：括号内条件成立的样本对数量。

例如，验证集一共有 100 对回答，其中 82 对满足 `r_chosen > r_rejected`：

$$
\operatorname{accuracy}
=
\frac{82}{100}
=
0.82
$$

也就是 RM 偏好排序准确率为 82%。

更标准、也更容易解释的指示函数写法是：

$$
\operatorname{accuracy}
=
\frac{1}{N}
\sum_{i=1}^{N}
\mathbf{1}\left[
r_{chosen}^{(i)}>r_{rejected}^{(i)}
\right]
$$

指示函数在条件成立时取 1，不成立时取 0；把所有 0 和 1 相加，就等于 `#(...)` 的计数结果。

实现位于 [`src/llamafactory/train/rm/metric.py`](src/llamafactory/train/rm/metric.py)。

### 3.7 RM 完整代码链

```text
run_exp
  ↓ stage="rm"
run_rm
  ↓
PairwiseDatasetProcessor
  ↓
load_model(add_valuehead=True)
  ↓
PairwiseDataCollatorWithPadding
  ↓
PairwiseTrainer.compute_loss
  ↓
保存模型/Adapter + Value Head
```

关键文件：

- [`src/llamafactory/train/rm/workflow.py`](src/llamafactory/train/rm/workflow.py)：RM 工作流。
- [`src/llamafactory/train/rm/trainer.py`](src/llamafactory/train/rm/trainer.py)：序列评分和 pairwise loss。
- [`src/llamafactory/train/rm/metric.py`](src/llamafactory/train/rm/metric.py)：偏好排序准确率。
- [`src/llamafactory/model/model_utils/valuehead.py`](src/llamafactory/model/model_utils/valuehead.py)：Value Head 权重处理。

### 3.8 RM 一句话总结

> RM 不负责生成答案，而是学习人类更喜欢哪一个答案，并把偏好压缩成 PPO 可以使用的标量 reward。

---


## 四、DPO：Direct Preference Optimization
### P.S.RL与LLM的映射

把强化学习概念映射到 LLM 时，一条完整 response 就是一条轨迹：

你输入：
```
法国的首都是
```
模型不会直接先决定输出“巴黎”，而是先给词表里的候选打分、变成概率：
```
巴黎：90%
伦敦： 3%
北京： 0.1%
其他：……
```
| RL 概念 | LLM 中对应什么 |
|---|---|
| 状态 $s_t$ | 当前已写的文本，比如“法国的首都是” |
| 动作 $a_t$ | 第 $t$ 步采样出的 token，下一个候选词，比如“巴黎” |
| 策略 $\pi_\theta(a_t\mid s_t)$ | 模型看到当前已写出的内容后，选择下一个词 aₜ 的概率，此时模型给“巴黎”的概率，例如 90%。 |
| 轨迹 $\tau$ | 一整条生成 response |
| reward $r$ | RM 对整条 response 的分数，加上逐 token 的 KL 惩罚 |

### 4.1 DPO 的目标

DPO 也使用：

```text
prompt + chosen + rejected
```

但它不先训练 RM，而是直接更新语言模型，使 chosen 相对 rejected 的概率更高。

#### 4.1.1 从 probability 到 log probability

语言模型在每个位置先输出一组 `logits`。假设词表大小为 V，当前位置第 i 个 token 的 logit 是 `z_i`，经过 softmax 后才得到概率：

$$
p_i
=
\frac{e^{z_i}}
{\sum_{j=1}^{V}e^{z_j}}
$$

如果当前位置的正确 token 是 `y_t`，那么：

```text
probability     = p(y_t)          模型给正确 token 的概率
log probability = log(p(y_t))    对这个概率取自然对数
```

概率和 log probability 的对应关系如下：

| probability | log probability | 含义 |
|---:|---:|---|
| `1.0` | `0` | 模型把全部概率都给了该 token |
| `0.8` | `-0.223` | 模型认为该 token 很可能出现 |
| `0.1` | `-2.303` | 模型认为该 token 出现的可能性较低 |
| `0.01` | `-4.605` | 模型认为该 token 很不可能出现 |

因为概率范围是 0～1，所以它的自然对数小于等于 0。**log probability 越接近 0，原始概率越大**；例如 `-2` 大于 `-8`，因此 `-2` 表示模型认为该 token 更可能出现。

#### 4.1.2 一整条回答的 log probability

对于 prompt `x` 和回答：

$$
y=(y_1,y_2,\ldots,y_T)
$$

自回归语言模型给整条回答的概率是每个 token 条件概率的乘积：

$$
\pi_\theta(y\mid x)
=
\prod_{t=1}^{T}
p_\theta(y_t\mid x,y_{<t})
$$

对乘积取对数后，乘法变成加法：

$$
\log\pi_\theta(y\mid x)
=
\sum_{t=1}^{T}
\log p_\theta(y_t\mid x,y_{<t})
$$

这就是 DPO 代码中的 `chosen_logps` 或 `rejected_logps`：模型对整条 chosen/rejected 回答中所有有效 token 的 log probability 求和。

例如，一条回答只有三个 token，模型分配给正确 token 的概率分别是：

```text
token 1：p = 0.5，log(p) = -0.693
token 2：p = 0.2，log(p) = -1.609
token 3：p = 0.1，log(p) = -2.303
```

则整条回答的概率和 log probability 分别为：

$$
\pi_\theta(y\mid x)
=0.5\times0.2\times0.1
=0.01
$$

$$
\log\pi_\theta(y\mid x)
=-0.693-1.609-2.303
=-4.605
$$

反过来使用 `exp(-4.605)`，可以还原得到约 `0.01`。

#### 4.1.3 为什么代码不直接使用 probability

使用 log probability 有三个主要原因：

1. 一条回答可能有几百个 token，许多小概率连续相乘会非常接近 0，容易发生浮点数下溢；对数求和更稳定。
2. 概率的乘法变成 log probability 的加法，整条回答的分数更容易计算。
3. DPO 需要计算策略模型相对参考模型的概率比，对数可以把除法变成减法：

$$
\log
\frac{\pi_\theta(y\mid x)}
{\pi_{ref}(y\mid x)}
=
\log\pi_\theta(y\mid x)
-
\log\pi_{ref}(y\mid x)
$$

#### 4.1.4 LLaMAFactory 在哪里计算 log probability

核心实现位于 [`src/llamafactory/train/trainer_utils.py`](src/llamafactory/train/trainer_utils.py) 的 `get_batch_logps()`：

```python
# 做 causal shift：位置 t 的 logits 预测位置 t+1 的 label
labels = labels[:, 1:].clone()
logits = logits[:, :-1, :]

# prompt、padding 等被标成 label_pad_token_id 的位置不参与计算
# label_pad_token_id 在这里默认是 -100
loss_mask = labels != label_pad_token_id
labels[labels == label_pad_token_id] = 0  # 临时 dummy token，后面会被 mask 清除

# log_softmax：把 logits 转成词表中每个 token 的 log probability
# gather：只取真实 label 对应的那一个 log probability
per_token_logps = torch.gather(
    logits.log_softmax(-1),
    dim=2,
    index=labels.unsqueeze(2),
).squeeze(2)

# 对回答的有效 token 求和，得到每条回答的 sequence log probability
logps = (per_token_logps * loss_mask).sum(-1)
```

对应的数据形状是：

```text
logits           [batch_size, sequence_length, vocab_size]
labels           [batch_size, sequence_length]
per_token_logps  [batch_size, sequence_length - 1]
logps            [batch_size]
```

由于 prompt 对应的 labels 被设置为 `-100`，所以这里计算的是“给定 prompt 后，模型生成回答 token 的 log probability”，不会把 prompt 本身计入回答分数。

标准 DPO 对有效 token 的 log probability 求和，因此长回答的数值通常更加负。LLaMAFactory 在 `pref_loss` 为 `ipo`、`orpo` 或 `simpo` 时会再除以有效 token 数，改用每 token 平均 log probability。

#### 4.1.5 log probability、RM score 和 DPO reward 的区别

| 名称 | 谁计算 | 表示什么 |
|---|---|---|
| `log probability` | 普通语言模型的 logits 经过 `log_softmax` | 模型认为某个 token 或整条回答出现的可能性 |
| `r_chosen/r_rejected`（RM） | Transformer hidden state 经过 Value Head | Reward Model 预测的回答质量分数 |
| DPO 隐式 reward | `beta × (policy_logp - reference_logp)` | 当前策略相对参考模型对某条回答提升或降低了多少 |

因此，DPO 中的 `chosen_logps` 不是“chosen 的人工得分”，也不是 RM 的输出；它只是语言模型自身认为 chosen 回答有多大可能出现。

#### 4.1.6 log probability 如何进入 DPO 公式

定义当前策略的偏好差：

$$
\Delta_\theta
=
\log\pi_\theta(y_c|x)
-
\log\pi_\theta(y_r|x)
$$

参考模型的偏好差：

$$
\Delta_{ref}
=
\log\pi_{ref}(y_c|x)
-
\log\pi_{ref}(y_r|x)
$$

DPO 损失：

$$
\mathcal{L}_{DPO}
=
-\log\sigma\left[
\beta(\Delta_\theta-\Delta_{ref})
\right]
$$

直觉是：当前模型相对于参考模型，应该更明显地偏好 chosen。

公式中的符号含义如下：

| 符号 | 含义 |
|---|---|
| `x` | prompt |
| `y_c` | 数据集中的 chosen 回答 |
| `y_r` | 数据集中的 rejected 回答 |
| `π_θ` | 当前正在训练的 Policy Model |
| `π_ref` | 冻结的 Reference Model |
| `log π_θ(y_c given x)` | 当前策略对 chosen 回答的 sequence log probability |
| `Δ_θ` | 当前策略对 chosen 和 rejected 的 log probability 差 |
| `Δ_ref` | 参考模型对 chosen 和 rejected 的 log probability 差 |
| `β` | `pref_beta`，缩放偏好差并控制相对参考模型的约束尺度 |
| `σ` | sigmoid 函数，把偏好差映射到 0～1 |

当 `Δ_θ - Δ_ref > 0` 时，说明当前策略比参考模型更偏好 chosen，DPO loss 会变小。

### 4.2 DPO 数据处理

DPO 与 RM 共用 [`pairwise.py`](src/llamafactory/data/processor/pairwise.py)。

这是一个很适合现场说明的设计：

```text
数据格式相同：prompt + chosen + rejected

RM：把两条回答映射成两个 scalar score
DPO：计算两条回答在语言模型下的 sequence log probability
```

DPO workflow 中调用 `get_dataset(..., stage="rm")`，就是为了复用成对偏好数据格式。

### 4.3 一次前向同时计算 chosen/rejected

Collator 将 chosen 和 rejected 沿 batch 维拼接，Trainer 只执行一次模型前向：

```python
labels = batch.pop("labels")
all_logits = model(
    **batch,
    return_dict=True,
    use_cache=False,
).logits.to(torch.float32)

all_logps, valid_length = get_batch_logps(
    logits=all_logits,
    labels=labels,
)
```

再切回两部分：

```python
batch_size = batch["input_ids"].size(0) // 2
chosen_logps, rejected_logps = all_logps.split(batch_size, dim=0)
```

实现：[`src/llamafactory/train/dpo/trainer.py`](src/llamafactory/train/dpo/trainer.py) 中的 `concatenated_forward`。

### 4.4 Reference Model

Trainer 还会计算冻结参考模型的 log probability：

```python
reference_chosen_logps, reference_rejected_logps = \
    self.compute_reference_log_probs(model, batch)
```

LoRA 场景可以不用额外复制一份完整模型，而是临时关闭 Adapter：

```python
ref_model = model
ref_context = self.accelerator.unwrap_model(model).disable_adapter()
```

于是：

```text
Policy Model    = 基座模型 + 正在训练的 LoRA
Reference Model = 同一个基座模型，但关闭 LoRA
```

### 4.5 DPO Loss 与扩展

统一偏好损失入口：

```python
losses, chosen_rewards, rejected_rewards = self.compute_preference_loss(
    policy_chosen_logps,
    policy_rejected_logps,
    reference_chosen_logps,
    reference_rejected_logps,
)
```

当前 Trainer 还支持：

- 标准 sigmoid DPO；
- hinge；
- IPO；
- ORPO；
- SimPO；
- 可选 BCO 混合损失；
- 可选 SFT loss 混合，避免偏好训练损害基础生成能力。

### 4.6 DPO 监控指标

这些指标不是 BLEU、ROUGE 一类最终能力评测，而是用来回答训练过程中的三个问题：

1. 模型是否已经学会“chosen 应该优于 rejected”？
2. 偏好差距是通过提高 chosen，还是通过压低 rejected 得到的？
3. 模型是否为了拉开偏好差距而把回答的整体概率压得过低？

#### 4.6.1 先定义指标使用的量

对一个偏好样本 `(x, y_chosen, y_rejected)`，定义策略模型和参考模型的回答 log probability：

$$
\ell_{\theta,c}=\log\pi_\theta(y_c\mid x),
\qquad
\ell_{\theta,r}=\log\pi_\theta(y_r\mid x)
$$

$$
\ell_{ref,c}=\log\pi_{ref}(y_c\mid x),
\qquad
\ell_{ref,r}=\log\pi_{ref}(y_r\mid x)
$$

其中标准 DPO 的一条回答的 sequence log probability 是回答 token 的 log probability 之和：

$$
\log\pi_\theta(y\mid x)
=
\sum_{t=1}^{T_y}
\log p_\theta(y_t\mid x,y_{<t})
$$

DPO 的“隐式 reward”不是 Reward Model 输出的分数，而是策略模型相对参考模型的 log probability 变化：

$$
r_c
=
\beta\left(\ell_{\theta,c}-\ell_{ref,c}\right)
$$

$$
r_r
=
\beta\left(\ell_{\theta,r}-\ell_{ref,r}\right)
$$

二者之差为：

$$
m=r_c-r_r
=
\beta\left[
(\ell_{\theta,c}-\ell_{\theta,r})
-(\ell_{ref,c}-\ell_{ref,r})
\right]
$$

这个 margin `m` 正是标准 DPO 损失送入 sigmoid 的偏好差距：

$$
\mathcal L_{DPO}=-\log\sigma(m)
$$

#### 4.6.2 每个指标分别用来做什么
```
r_chosen   = RM(prompt + chosen)
r_rejected = RM(prompt + rejected)
```
| 指标 | 代码中的计算 | 用途和观察方法 |
|---|---|---|
| `rewards/chosen` | `mean(r_chosen)` | 观察策略模型相对参考模型是否提高了 chosen 的概率。大于 0 表示总体上比参考模型更支持 chosen；通常希望稳定或上升。 |
| `rewards/rejected` | `mean(r_rejected)` | 观察策略模型相对参考模型如何对待 rejected。通常希望它低于 chosen，训练中下降很常见。 |
| `rewards/accuracies` | `count(r_chosen > r_rejected) / B` | 当前 batch 中隐式 reward 排序正确的样本比例，范围为 0～1；B 是该 batch 的偏好样本对数量。 |
| `rewards/margins` | `mean(r_chosen - r_rejected)` | 衡量 chosen 与 rejected 平均拉开多大差距。大于 0 表示平均排序方向正确；比 accuracy 更能反映差距大小。 |
| `logps/chosen` | `mean(policy_chosen_logps)` | 策略模型给 chosen 回答的平均 sequence log probability，用于检查模型是否在保持或提高优质回答的概率。 |
| `logps/rejected` | `mean(policy_rejected_logps)` | 策略模型给 rejected 回答的平均 sequence log probability，用于检查模型是否在压低较差回答的概率。 |

`log probability` 通常小于等于 0，数值越接近 0，表示模型认为该回答越可能。例如 `-8` 比 `-15` 的概率更高。

需要特别注意：

- `rewards/chosen` 和 `rewards/rejected` 是**相对参考模型的隐式 reward**，不是 RM 打出的绝对质量分数。
- 标准 DPO 默认使用回答 token log probability 的总和，所以回答越长，`logps/*` 往往越负；不能脱离长度直接比较不同数据集的数值。
- 本项目在 `pref_loss` 为 `ipo`、`orpo` 或 `simpo` 时，会除以有效回答长度，使用平均 token log probability。
- `pref_beta` 会直接缩放 reward 和 margin。因此不同 beta 的两次实验不能只根据 reward 绝对值判断优劣。
- `rewards/accuracies` 只是偏好对上的排序准确率，不代表事实正确率、问答准确率或人工评测胜率。


### 4.7 DPO 完整代码链

```text
run_dpo
  ↓
get_dataset(stage="rm")
  ↓
PairwiseDatasetProcessor
  ↓
Policy Model + Reference Model
  ↓
PairwiseDataCollatorWithPadding
  ↓
CustomDPOTrainer.concatenated_forward
  ↓
policy/ref 的 chosen/rejected logps
  ↓
DPO loss
```

关键文件：

- [`src/llamafactory/train/dpo/workflow.py`](src/llamafactory/train/dpo/workflow.py)：DPO 工作流。
- [`src/llamafactory/train/dpo/trainer.py`](src/llamafactory/train/dpo/trainer.py)：log probability、reference model 和偏好损失。
- [`src/llamafactory/data/processor/pairwise.py`](src/llamafactory/data/processor/pairwise.py)：成对偏好数据。


---

## 五、KTO：Kahneman-Tversky Optimization

### 5.1 KTO 与 DPO 的区别

DPO 需要同一 prompt 下的一对回答：

```text
A 比 B 好
```

KTO 允许单条回答只有好坏标签：

```text
A 是好回答
```

或者：

```text
B 是坏回答
```

因此 KTO 适合点赞/点踩、审核通过/拒绝等真实反馈数据。

### 5.2 KTO 的基本量

同样比较策略模型和参考模型：

$$
r_\theta(x,y)
=
\beta\left[
\log\pi_\theta(y|x)
-
\log\pi_{ref}(y|x)
\right]
$$

训练目标是：

- desirable 回答的隐式 reward 应高；
- undesirable 回答的隐式 reward 应低；
- KL 基线限制模型偏离参考策略。

### 5.3 KTO 数据处理

入口：[`src/llamafactory/data/processor/feedback.py`](src/llamafactory/data/processor/feedback.py)

代码先判断样本类型：

```python
if response[0]["content"]:
    kto_tag = True
    messages = prompt + [response[0]]
else:
    kto_tag = False
    messages = prompt + [response[1]]
```

最终输出：

```python
model_inputs["input_ids"].append(input_ids)
model_inputs["labels"].append(labels)
model_inputs["kl_input_ids"].append(kl_input_ids)
model_inputs["kl_labels"].append(kl_labels)
model_inputs["kto_tags"].append(kto_tag)
```

字段含义：

- `input_ids/labels`：真正的好或坏回答；
- `kto_tags`：该回答是否 desirable；
- `kl_input_ids/kl_labels`：估计 KL 基线的辅助样本。

### 5.4 KL 样本怎么构造

代码把 batch 内的回答错位一位：

```python
kl_response = [examples["_response"][-1]] + examples["_response"][:-1]
```

这样可以在当前 batch 内构造 prompt 与 response 的错配组合，用来估计策略与参考模型之间的 KL，而不需要额外准备 KL 数据集。

### 5.5 KTO Trainer

当前样本和 KL 样本分别前向：

```python
target_logits, target_logps, target_logps_avg = self.forward(model, batch)

with torch.no_grad():
    _, kl_logps, _ = self.forward(model, batch, prefix="kl_")
```

然后根据标签分成好坏样本：

```python
chosen_logps = target_logps[batch["kto_tags"]]
rejected_logps = target_logps[~batch["kto_tags"]]
```

这里的 chosen/rejected 表示 batch 中 desirable/undesirable 的两个集合，并不要求一一配对。

最终调用 TRL 的 KTO loss：

```python
losses, chosen_rewards, rejected_rewards, kl = self.kto_loss(
    policy_chosen_logps,
    policy_rejected_logps,
    policy_kl_logps,
    reference_chosen_logps,
    reference_rejected_logps,
    reference_kl_logps,
)
```

### 5.6 KTO 完整代码链

```text
run_kto
  ↓
get_dataset(stage="kto")
  ↓
FeedbackDatasetProcessor
构造 input、KL input 和 kto_tags
  ↓
KTODataCollatorWithPadding
  ↓
Policy Model + Reference Model
  ↓
CustomKTOTrainer
  ↓
desirable loss + undesirable loss + KL baseline
```

关键文件：

- [`src/llamafactory/train/kto/workflow.py`](src/llamafactory/train/kto/workflow.py)：KTO 工作流。
- [`src/llamafactory/data/processor/feedback.py`](src/llamafactory/data/processor/feedback.py)：单条好坏反馈和 KL 样本。
- [`src/llamafactory/train/kto/trainer.py`](src/llamafactory/train/kto/trainer.py)：前向、参考概率和 KTO loss。
- [`src/llamafactory/data/collator.py`](src/llamafactory/data/collator.py)：`KTODataCollatorWithPadding`。

### 5.7 KTO 一句话总结

> DPO 做“同题两个回答谁更好”的排序；KTO 接受“这一条是好还是坏”的反馈，标注成本更低，但相对比较信息更弱。

---

## 六、PPO：Proximal Policy Optimization

### 6.1 PPO 是真正的在线强化学习闭环

SFT 给的是“面对这个 prompt，示范回答应该写成什么样”的逐 token 目标；它并不天然提供“另一个回答为什么更差”的相对信号，也不适合所有没有唯一标准答案的目标。比如帮助性、风格、安全边界或回答整体质量，往往更容易判断两个回答谁更好，或给整条回答一个分数。

这不表示 SFT 没有负面能力：拒答样本同样可以放进 SFT。区别在于，单条 SFT 样本只要求模型模仿一个 target；它不会像 chosen/rejected 偏好对或 reward 一样，**直接比较**两个候选回答。因而 SFT 后的偏好对齐有两条路线：`DPO / KTO` 直接利用偏好数据更新语言模型；传统 RLHF 则训练 RM，再用 PPO 根据在线生成的回答优化策略。

```text
prompt
  ↓
Policy Model 在线生成 response
  ↓
Reward Model 给 response 打分
  ↓
Reference Model 计算 KL 约束
  ↓
Value Head 估计每个状态的价值
  ↓
计算 return 和 advantage
  ↓
PPO clipped objective 更新 Policy 和 Value Head
```

```
                         Prompt
                           │
                           ▼
                    ┌─────────────┐
                    │ Policy Model│
                    │   self.model│
                    └──────┬──────┘
                           │
                        generate
                           │
                           ▼
                        Response
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
          ▼                ▼                 ▼
     Reward Model      Policy Model      Ref Model
          │                │                 │
          ▼                ▼                 ▼
       reward         logprob/value        ref_logprob
          │                │                 │
          └────────────────┼─────────────────┘
                           ▼
                       PPO Loss
                           │
                           ▼
                    backward/update
                           │
                           ▼
                    新的 Policy Model

```

与 DPO/KTO 的最大不同：PPO 训练时会使用当前模型在线生成回答，因此训练数据分布会随着策略变化。

### 6.2 PPO 中的模型
![alt text](./images/image-3.png)
PPO 有 actor、critic、RM、reference 四个**角色**，但不一定有四份独立的模型权重。PPO workflow 的加载代码是：

```python
# src/llamafactory/train/ppo/workflow.py
model = load_model(..., add_valuehead=True)
ref_model = create_ref_model(..., add_valuehead=True)
reward_model = create_reward_model(model, model_args, finetuning_args)
```

其中第一行返回的是一个 `AutoModelForCausalLMWithValueHead`：同一份 Transformer 骨干同时服务于 actor 和 critic。

| 角色 | 在 LlamaFactory 中是什么 | 从哪里来 | 训练？ | 在 PPO loop 中做什么 |
|---|---|---|---:|---|
| actor / policy | `model.pretrained_model` 的 LM Head | `model_name_or_path`，通常指 SFT checkpoint | 是 | rollout 逐 token 生成 response；update 时提高/降低已生成 token 的概率。 |
| critic / value | 同一个 `model` 的 `v_head` | PPO 时附加的标量头；通常是新初始化，若 checkpoint 自带 v_head 才会加载 | 是 | 为每个 token 状态输出 $V(s_t)$，供 GAE / value loss 使用。 |
| RM | 完整 RM，或同一底座上切换到 reward LoRA/OFT adapter，或外部 API | RM 阶段训练所得的偏好打分器 | 否 | 对完整 response 给最终质量分数。 |
| reference / ref | 独立冻结副本；LoRA 且未显式设置 `ref_model` 时可临时关闭 policy adapter 复用底座 | 通常是 PPO 开始前的 SFT / 基座策略 | 否 | 给生成 token 的 logprob 基准，构造 KL 惩罚，防止策略长期漂移。 |


| 要训练谁           | 需要什么目标  |含义|
| -------------- | ------- |---|
| Actor / Policy | $$A_t$$|告诉 Actor 这个动作好不好|
| Value / Critic | $$R_t$$ |告诉 Value 模型你应该预测多少|

```
reward
   ↓
结合 Value
   ↓
计算 GAE
   ↓
得到 A_t
  /    \
 /      \
Actor   R_t = A_t + V_t
更新       ↓
        Value更新
```

#### 6.2.1 Old Policy 到底是什么

Old Policy 可以翻译为“旧策略”或“行为策略”。它表示：**生成当前这批 response 时，Policy Model 尚未更新前的状态**。

它不是另一个长期训练的模型，也通常不需要在显存中额外复制一份 `old_model`。实现时只要把更新前对已生成 token 的 log probability 保存下来，就足以代表旧策略：

```text
当前 Policy（参数 θ_old）
  ↓ 根据 prompt 生成一批 response
  ↓ 记录每个生成 token 的 old_logprobs
固定这批 response、reward、advantage 和 old_logprobs
  ↓
对同一批数据执行若干轮 PPO 更新
  ↓
Policy 参数变为 θ_new，但 old_logprobs 始终不变
```

在下一批 rollout 开始时，刚更新完的 Policy 又会成为下一批数据的 Old Policy。因此 Old Policy 是一个**随 rollout 不断刷新的短期快照**。

#### 6.2.2 为什么需要 Old Policy

设：

```text
s_t = prompt + 已经生成的前缀 token
a_t = 在位置 t 实际生成的 token
```

生成这批数据时，旧策略给该 token 的概率为：

$$
\pi_{old}(a_t\mid s_t)
$$

参数更新后，当前 Policy 对同一个 token 重新计算概率：

$$
\pi_\theta(a_t\mid s_t)
$$

二者的概率比率是：

$$
r_t(\theta)
=
\frac{\pi_\theta(a_t\mid s_t)}
{\pi_{old}(a_t\mid s_t)}
$$

代码不会先把 log probability 还原成两个极小概率再相除，而是使用：

$$
r_t(\theta)
=
\exp\left[
\log\pi_\theta(a_t\mid s_t)
-
\log\pi_{old}(a_t\mid s_t)
\right]
$$

这个比率表示新策略相对生成数据时的旧策略改变了多少：

| ratio | 含义 |
|---:|---|
| `1.0` | 新旧策略给该 token 的概率相同 |
| `1.2` | 新策略的概率是旧策略的 1.2 倍 |
| `0.8` | 新策略的概率是旧策略的 0.8 倍 |
| `2.0` | 新策略把概率提高到旧策略的 2 倍，变化可能过大 |

PPO 会同时计算原始 ratio 分支和 `clip(ratio, 1-epsilon, 1+epsilon)` 分支，再根据 advantage 取更保守的目标。例如 `epsilon=0.2` 时，裁剪分支把 ratio 限制在 `[0.8, 1.2]`；具体裁剪哪一侧取决于 advantage 的正负，但总体目的都是阻止一次更新获得过大的额外收益。

#### 6.2.3 Old Policy 和 Reference Model 有什么区别

这两个都“不训练”，但用途完全不同：

| 对比项 | Old Policy | Reference Model |
|---|---|---|
| 来源 | 当前 Policy 在本批 rollout 开始时的状态 | 通常是冻结的 SFT/基座策略 |
| 是否需要独立模型对象 | 通常不需要，缓存 `old_logprobs` 即可 | 需要固定参考行为；LoRA 时可通过关闭 Adapter 得到 |
| 生命周期 | 只固定当前一批 rollout 和对应的 PPO 更新阶段 | 通常在整个 PPO 训练过程中固定 |
| 是否随训练刷新 | 每批 rollout 都刷新 | 不刷新 |
| 比较对象 | 新 Policy 与生成当前数据时的 Policy | Policy 与原始参考策略 |
| 主要作用 | clipped objective，限制本轮参数更新幅度 | KL penalty，防止长期偏离语言模型能力 |

一句话区分：

```text
Old Policy：别让“这一次更新”走得太远。
Reference Model：别让“整个 PPO 训练”偏离原模型太远。
```

#### 6.2.4 LLaMAFactory 中 Old Policy 在哪里

[`src/llamafactory/train/ppo/trainer.py`](src/llamafactory/train/ppo/trainer.py) 的外层循环先生成回答并取得 RM reward：

```python
mini_batch_queries, mini_batch_responses = self.get_inputs(mini_batch)
mini_batch_rewards = self.get_rewards(
    mini_batch_queries,
    mini_batch_responses,
)

stats = self.step(queries, responses, rewards)
```

这里的 `self.step()` 继承自 TRL 的 `PPOTrainer`。它会先调用 LLaMAFactory 重写的 `batched_forward_pass()`，取得更新前的 `logprobs` 和 `values`：

```python
logits, _, values = model(
    **input_kwargs,
    return_dict=True,
    use_cache=False,
)

logprobs = logprobs_from_logits(
    logits[:, :-1, :],
    input_ids[:, 1:],
)
```

TRL `PPOTrainer.step()` 的等价核心过程可以概括为：

```python
# 更新前计算一次并固定：代表 Old Policy
with torch.no_grad():
    old_logprobs, _, old_values, masks = self.batched_forward_pass(...)

# 同一批 rollout 可以重复训练 ppo_epochs 次
for _ in range(ppo_epochs):
    new_logprobs, _, new_values, _ = self.batched_forward_pass(...)

    ratio = torch.exp(new_logprobs - old_logprobs)
    clipped_ratio = torch.clamp(ratio, 1.0 - epsilon, 1.0 + epsilon)
    policy_loss = clipped_policy_objective(ratio, clipped_ratio, advantages)

    optimizer.zero_grad()
    policy_loss.backward()
    optimizer.step()
```

因此在这个项目里搜索不到单独的 `old_model = load_model(...)` 是正常的：**Old Policy 主要以固定的 `old_logprobs` 张量存在，核心更新逻辑位于依赖库 TRL 的 `PPOTrainer.step()` 中。**

### 6.3 Reward 与 Value/Critic 的区别


```text
Reward Model：
“这整条回答最后有多好？”

Policy 的 Value Head：
“生成到当前 token 时，预计最终能获得多少回报？”
```

| 对比 | RM 的 Value Head | PPO Policy 的 Value Head |
|---|---|---|
| 主要输出 | 完整回答的 scalar reward | 各 token 状态的 value |
| 使用位置 | 通常取最后有效 token | 用于 advantage 估计 |
| 训练阶段 | RM 阶段 | PPO 阶段 |

虽然代码都使用 `AutoModelForCausalLMWithValueHead`，但两者语义不同。

### 6.4 Advantage

#### 6.4.1 简化公式中每个符号是什么

可以先用下面的简化形式理解 Advantage：

$$
A_t=R_t-V_\phi(s_t)
$$

| 符号 | 含义 |
|---|---|
| `t` | 回答中第 t 个生成 token 的位置，不是全局训练 step |
| `s_t` | 生成第 t 个 token 前的状态，即 `prompt + 已生成的前 t-1 个 token` |
| `V_φ(s_t)` | Policy 模型的 Value Head 对状态 `s_t` 预测的未来回报 |
| `φ` | Value 函数的参数，主要指 Value Head 参数；共享骨干的可训练参数也会影响 hidden state |
| `R_t` | PPOTrainer 根据 token rewards、Value 预测和 GAE 计算出的 return 目标；不是任何模型直接输出的 |
| `A_t` | Advantage，实际回报目标比 Value Head 预期高出或低了多少 |


```text
A_t > 0：这个位置生成的 token 带来的结果比预期好
         → PPO 倾向提高该 token 的生成概率

A_t < 0：这个位置生成的 token 带来的结果比预期差
         → PPO 倾向降低该 token 的生成概率

A_t ≈ 0：实际结果与 Value Head 的预期接近
         → 该 token 不需要很大的策略更新
```


#### 6.4.3 实际使用 GAE 计算 Advantage

PPO 通常不直接使用完整的 Monte Carlo return，而是先计算一步 TD error：

$$
\delta_t
=
r_t^{token}
+\gamma V_\phi(s_{t+1})
-V_\phi(s_t)
$$

再从后往前递推 GAE：

$$
A_t^{GAE}
=
\delta_t
+\gamma\lambda_{GAE}A_{t+1}^{GAE}
$$

展开后相当于：

$$
A_t^{GAE}
=
\delta_t
+\gamma\lambda_{GAE}\delta_{t+1}
+(\gamma\lambda_{GAE})^2\delta_{t+2}
+\cdots
$$

符号含义：

| 符号 | 含义 |
|---|---|
| `δ_t` | 一步 TD error：即时 reward 加下一状态价值，与当前价值预测之差 |
| `γ` | discount factor，控制未来 reward 的折扣程度 |
| `λ_GAE` | GAE 系数，控制偏差与方差的折中 |
| `A_t^GAE` | 实际送入 PPO policy loss 的 advantage 估计 |

直觉上：

- `λ_GAE` 较小，更依赖 Value Head 的短期预测，方差较低但偏差可能较大；
- `λ_GAE` 较大，更充分利用后续真实 reward，偏差较小但方差可能增大；
- GAE 计算出的 Value Head 训练目标通常为 `returns = advantages + values`。

`γ` 和 `λ_GAE` 由兼容版本的 TRL `PPOConfig` 提供；当前 LLaMAFactory 的 `FinetuningArguments` 没有单独暴露同名 YAML 字段，而是使用 TRL 配置的默认值。

#### 6.4.4 对应代码在哪里

LLaMAFactory 在 [`src/llamafactory/train/ppo/trainer.py`](src/llamafactory/train/ppo/trainer.py) 的 `batched_forward_pass()` 中取得 Policy 的 token log probability 和 Value Head 输出：

```python
logits, _, values = model(
    **input_kwargs,
    return_dict=True,
    use_cache=False,
)

logprobs = logprobs_from_logits(
    logits[:, :-1, :],
    input_ids[:, 1:],
)
```

同一文件的 `ppo_train()` 调用：

```python
stats = self.step(queries, responses, rewards)
```

`self.step()` 来自兼容版本的 TRL `PPOTrainer`。其 reward shaping 与 GAE 核心逻辑可以概括为：

```python
# 1. 每个 token 的 KL 惩罚
kl = logprobs - ref_logprobs
token_rewards = -kl_coef * kl

# 2. 最后一个有效 token 加上 Reward Model 的整句分数
token_rewards[:, last_response_index] += rm_scores

# 3. 从后向前计算 GAE
last_gae = 0
advantages_reversed = []

for t in reversed(range(response_length)):
    next_value = values[:, t + 1] if t < response_length - 1 else 0.0
    delta = token_rewards[:, t] + gamma * next_value - values[:, t]
    last_gae = delta + gamma * gae_lambda * last_gae
    advantages_reversed.append(last_gae)

advantages = reverse_and_stack(advantages_reversed)
returns = advantages + values
```

接下来：

```text
advantages → PPO clipped policy loss，更新 Policy
returns    → Value loss 的监督目标，更新 Value Head
```


### 6.5 PPO 裁剪目标

新旧策略概率比：

$$
r_t(\theta)
=
\frac{\pi_\theta(a_t|s_t)}{\pi_{old}(a_t|s_t)}
$$

PPO 核心目标：

$$
\mathcal{L}_{clip}
=
-\min\left(
r_tA_t,
\operatorname{clip}(r_t,1-\epsilon,1+\epsilon)A_t
\right)
$$

Clip 的作用是防止单次更新过大。即使某个回答 reward 很高，也不允许策略概率一步变化过猛。

### 6.6 KL 约束

为了防止模型只迎合 Reward Model 而破坏语言能力，PPO 还约束策略不要远离参考模型：

$$
R_{total}
=
R_{RM}
-
\lambda\operatorname{KL}(\pi_\theta||\pi_{ref})
$$

可以解释为：

```text
Reward Model：拉着模型朝高分方向走。
Reference Model：像锚一样防止模型走得过远。
```

### 6.7 PPO 主循环

核心入口：[`src/llamafactory/train/ppo/trainer.py`](src/llamafactory/train/ppo/trainer.py) 的 `ppo_train`。

主要步骤：

```text
读取一批 prompts
  ↓
get_inputs：Policy 生成 responses
  ↓
get_rewards：RM 打分
  ↓
batched_forward_pass：取得 logprobs 和 values
  ↓
TRL PPO step：计算 advantage、clip loss、value loss、KL
  ↓
optimizer.step
```

关键方法：

- `ppo_train`：整个训练循环；
- `get_inputs`：根据 prompt 生成回答；
- `get_rewards`：调用完整 RM、Adapter RM 或 API RM；
- `batched_forward_pass`：计算 log probability、logits、values 和 mask。

### 6.8 Reward Model 的三种加载方式

`create_reward_model` 支持：

1. `reward_model_type="full"`：单独加载完整 RM，最直观但显存占用大。
2. `reward_model_type="lora"`：在同一基座模型上切换 Policy Adapter 与 Reward Adapter。
3. `reward_model_type="api"`：把回答发送给外部服务获取 reward。

相关实现：

- [`src/llamafactory/train/trainer_utils.py`](src/llamafactory/train/trainer_utils.py) 的 `create_reward_model`。
- [`src/llamafactory/train/ppo/ppo_utils.py`](src/llamafactory/train/ppo/ppo_utils.py) 的 `replace_model`。
- [`src/llamafactory/train/ppo/trainer.py`](src/llamafactory/train/ppo/trainer.py) 的 `get_rewards`。

### 6.9 PPO 一句话总结

> PPO 让当前策略在线生成回答，再利用 RM、Reference Model 和 Value Head 把标量偏好转成稳定的策略梯度，因此能力强但计算成本和工程复杂度最高。

---

## 七、六种训练方法的最终对比

```text
PT：
“阅读更多领域文本，学习这个领域的语言和知识。”

SFT：
“面对这种问题，按照标准答案的方式回答。”

RM：
“学习判断哪一个回答更好，并输出分数。”

DPO：
“同一个问题，让 chosen 的相对概率超过 rejected。”

KTO：
“根据单条好/坏标签，提高好回答、压低坏回答。”

PPO：
“自己生成回答，由 RM 打分，再朝高奖励方向更新。”
```

RM、DPO、PPO 的差异尤其值得强调：

| 对比 | RM | DPO | PPO |
|---|---|---|---|
| 输入 | chosen/rejected | chosen/rejected | prompt + 在线生成 |
| 最终训练对象 | 打分模型 | 语言模型 | 语言模型 |
| 是否显式输出 reward | 是 | 否 | 使用 RM 输出 |
| 是否需要在线生成 | 否 | 否 | 是 |
| 复杂度 | 中 | 中 | 高 |

---

# 第三部分：模型加载与微调方式

## 一、模型加载链路

模型加载集中在 [`src/llamafactory/model/loader.py`](src/llamafactory/model/loader.py)。

总体流程：

```text
模型路径
  ↓
AutoTokenizer + AutoProcessor
  ↓
AutoConfig
  ↓
patch_config
设置 dtype、attention、量化、RoPE、device map 等
  ↓
根据 config 选择 AutoModel 类
  ↓
from_pretrained / from_config
  ↓
patch_model
  ↓
init_adapter：Full / Freeze / LoRA
  ↓
可选 AutoModelForCausalLMWithValueHead
  ↓
model.train() / model.eval()
```

### 1.1 Tokenizer 与 Processor

```python
tokenizer = AutoTokenizer.from_pretrained(
    model_args.model_name_or_path,
    use_fast=model_args.use_fast_tokenizer,
    split_special_tokens=model_args.split_special_tokens,
    padding_side="right",
    **init_kwargs,
)
```

然后尝试加载：

```python
processor = AutoProcessor.from_pretrained(...)
```

Tokenizer 处理文本；Processor 处理图像、视频和音频。纯文本模型可能没有 Processor。

### 1.2 根据 config 自动选择模型类

```python
if type(config) in AutoModelForImageTextToText._model_mapping.keys():
    load_class = AutoModelForImageTextToText
elif type(config) in AutoModelForSeq2SeqLM._model_mapping.keys():
    load_class = AutoModelForSeq2SeqLM
elif type(config) in AutoModelForTextToWaveform._model_mapping.keys():
    load_class = AutoModelForTextToWaveform
else:
    load_class = AutoModelForCausalLM
```

最后：

```python
model = load_class.from_pretrained(**init_kwargs)
```

这让上层训练 workflow 不必为每个模型编写一套加载代码。

### 1.3 Adapter 初始化

```python
model = init_adapter(
    config,
    model,
    model_args,
    finetuning_args,
    is_trainable,
)
```

入口：[`src/llamafactory/model/adapter.py`](src/llamafactory/model/adapter.py)

---

## 二、Full、Freeze、LoRA

### 2.1 Full Fine-Tuning

原理：允许绝大多数原始参数参与反向传播。

```text
W ← W - η∇W L
```

代码：

```python
if finetuning_args.finetuning_type == "full":
    _setup_full_tuning(...)
```

`_setup_full_tuning` 不需要给普通参数插入新结构，因为预训练模型参数默认可训练；它主要负责：

- 根据多模态配置冻结禁止训练的模块；
- 必要时将可训练参数上转为 FP32。

优缺点：

| 优点 | 缺点 |
|---|---|
| 表达能力强，所有层都能适应任务 | 显存占用最大 |
| 上限通常较高 | 优化器状态和梯度成本大 |
| 不需要 Adapter 结构 | 每个任务都要保存完整模型 |

### 2.2 Freeze Fine-Tuning

原理：冻结大部分参数，只训练指定层或模块。

代码入口：`_setup_freeze_tuning`。

层选择逻辑：

```python
if freeze_trainable_layers > 0:
    # 训练最后 N 层
    trainable_layer_ids = range(num_layers - N, num_layers)
else:
    # 训练最前面的 N 层
    trainable_layer_ids = range(N)
```

随后遍历所有参数：

```python
for name, param in model.named_parameters():
    if name 匹配允许训练的层或模块:
        保持可训练
    else:
        param.requires_grad_(False)
```

Freeze 可细分：

- 训练最后若干 Transformer blocks；
- 只训练指定模块，例如 attention 或 MLP；
- 额外训练 embedding、lm_head；
- 多模态模型中选择是否训练 projector、vision tower、language model。

### 2.3 LoRA

LoRA 冻结原始权重 $W$，为线性层添加低秩增量：

$$
W'=W+\Delta W
$$

$$
\Delta W=\frac{\alpha}{r}BA
$$

其中：

$$
A\in\mathbb{R}^{r\times d_{in}},\quad
B\in\mathbb{R}^{d_{out}\times r}
$$

且：

$$
r\ll\min(d_{in},d_{out})
$$

前向传播可以写成：

$$
y=Wx+\frac{\alpha}{r}BAx
$$

训练时只更新 $A$、$B$，原始 $W$ 保持冻结。

### 2.4 LoRA 代码实现

入口：`_setup_lora_tuning`。

首先确定目标模块：

```python
if lora_target == ["all"]:
    target_modules = find_all_linear_modules(model, freeze_vision_tower)
else:
    target_modules = finetuning_args.lora_target
```

然后构造 PEFT 配置：

```python
peft_kwargs = {
    "r": finetuning_args.lora_rank,
    "target_modules": target_modules,
    "lora_alpha": finetuning_args.lora_alpha,
    "lora_dropout": finetuning_args.lora_dropout,
    "use_rslora": finetuning_args.use_rslora,
    "use_dora": finetuning_args.use_dora,
    "modules_to_save": finetuning_args.additional_target,
}

peft_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    inference_mode=False,
    **peft_kwargs,
)

model = get_peft_model(model, peft_config)
```

也就是由 PEFT 将目标 `Linear` 层替换/包装成带 LoRA 分支的模块。

### 2.5 Adapter 加载、继续训练与合并

如果配置多个 Adapter：

```text
[Adapter A, Adapter B, Adapter C]
```

普通情况下可以：

```text
A、B merge 到基座模型
C 作为最后一个 Adapter 继续训练
```

关键操作：

```python
model = PeftModel.from_pretrained(model, adapter)
model = model.merge_and_unload()
```

量化模型、DeepSpeed ZeRO-3、Unsloth 等场景存在合并限制，代码会只允许单个 Adapter 或采取专门加载路径。

### 2.6 QLoRA

QLoRA 可以概括为：

```text
量化后的冻结基座模型 + 可训练 LoRA Adapter
```

经典 QLoRA 指 **4-bit 量化基座 + LoRA**；LLaMAFactory 的同一条加载链也支持 8-bit 量化。量化的是冻结基座，LoRA 参数通常保持更高精度。

#### 量化实际发生在哪里

不是 `init_adapter()` 把一个已加载的模型“再量化”。`load_model()` 中是两步接力：

```text
1. patch_config(...)
   └─ configure_quantization(...)
      └─ 根据 quantization_bit 写入 init_kwargs["quantization_config"]
         例如 BitsAndBytesConfig(load_in_4bit=True, ...)

2. load_class.from_pretrained(**init_kwargs)
   └─ Transformers / bitsandbytes 按该配置加载 4-bit/8-bit 的基座权重
```

例如训练参数为：

```yaml
quantization_bit: 4
quantization_method: bnb
quantization_type: nf4
double_quantization: true
finetuning_type: lora
```

模型完成第 2 步后才进入 `init_adapter()`：它检查量化模型只能用 LoRA/OFT 类参数高效微调，然后把可训练 Adapter 挂到**已经量化**的基座上，并不负责量化本身。对应实现见 [loader.py](src/llamafactory/model/loader.py)、[patcher.py](src/llamafactory/model/patcher.py) 的 `patch_config()` 与 [quantization.py](src/llamafactory/model/model_utils/quantization.py) 的 `configure_quantization()`。

### 2.7 三种方式对比

| 方法 | 更新参数 | 显存 | 保存结果 | 适合场景 |
|---|---|---:|---|---|
| Full | 几乎全部原始权重 | 最高 | 完整模型 | 数据充分、追求上限 |
| Freeze | 指定层/模块 | 中等 | 通常是完整或部分权重 | 只希望调整部分层 |
| LoRA | 新增低秩矩阵 | 最低 | 小型 Adapter | 单卡、多任务、快速实验 |

---

# 第四部分：多模态处理

## 一、多模态数据链路

LLaMAFactory 并不把图片简单变成普通文本。完整链路是：

```text
原始 messages + images/videos/audios
        ↓
MM Plugin
校验数量、尺寸规整、视频抽帧、插入模型专属占位符
        ↓
Template
渲染 system/user/assistant 角色格式
        ↓
Tokenizer
文本与多模态占位符转成 token IDs
        ↓
Processor
图片/视频/音频转成 pixel_values、grid、sizes 等张量
        ↓
MultiModalDataCollator
合并 batch，处理 padding、位置编码、cross-attention mask
        ↓
多模态模型 forward
```

### 1.1 MMPluginMixin

入口：[`src/llamafactory/data/mm_plugin.py`](src/llamafactory/data/mm_plugin.py)

公共能力包括：

- `_validate_input`：检查模型和 Processor 是否支持当前模态；
- `_validate_messages`：检查消息中占位符数量与素材数量；
- `_preprocess_image`：图片格式和尺寸处理；
- `_regularize_images`：统一图片输入；
- `_regularize_videos`：视频解码、采样和尺寸处理；
- `_regularize_audios`：音频统一处理；
- `_get_mm_inputs`：调用 Processor 得到多模态张量。

### 1.2 Plugin 接口

每种多模态模型主要实现：

```python
process_messages(...)
process_token_ids(...)
get_mm_inputs(...)
```

例如 `Qwen2VLPlugin`、`LlavaPlugin`、`MllamaPlugin` 会根据各自模型约定：

- 插入不同的 image/video token；
- 计算视觉 token 数量；
- 处理 image grid；
- 构造 token type IDs 或 cross-attention mask；
- 适配各自 Processor 的参数名。

### 1.3 多模态数据何时进入 SFT

SFT 数据处理器先执行：

```python
messages = self.template.mm_plugin.process_messages(...)
```

它负责修改“文本消息表示”。

随后执行：

```python
input_ids, labels = self.template.mm_plugin.process_token_ids(...)
```

它负责调整 token 级表示。

最后 Collator 执行 `get_mm_inputs`，真正把图片等素材转换成模型 forward 所需的张量。

#### 一个单图样本如何变化（以 Qwen2-VL 为例）

原始数据里，文本和图片路径是两条字段：

```python
prompt = [{"role": "user", "content": "<image>这是什么动物？"}]
response = [{"role": "assistant", "content": "一只猫。"}]
images = ["cat.jpg"]
```

**第 1 步：`process_messages` 替换文本里的 `<image>`。** 假设图片经 Processor 预处理后得到 `image_grid_thw = [1, 28, 28]`，且 `merge_size = 2`，则图像位置需要的视觉 token 数是 `1 × 28 × 28 ÷ 2² = 196`（仅为示意；真实数量随图片尺寸变化）：

```text
<image>这是什么动物？
    ↓
<|vision_start|><|image_pad|> × 196 <|vision_end|>这是什么动物？
```

这里的 196 个 `<|image_pad|>` 只是在**文本序列里预留视觉位置**，并不包含猫的像素信息。

**第 2 步：模板编码并构造 labels。** `encode_multiturn` 将上面的消息变为 token ID；默认 `train_on_prompt=False`，所以 user 文本、角色 token 和图像占位 token 都不参与 loss：

```text
input_ids = [user/role IDs, vision_start_id, image_pad_id × 196,
             vision_end_id, “这是什么动物？”的 IDs, assistant/role IDs,
             “一只猫。”的 IDs, eos_id]

labels    = [-100, ..., -100,                         # 整个 prompt（含图像占位）
             “一只猫。”的 IDs, eos_id]                 # 只训练 assistant 回复
```

`process_token_ids` 在所有模型上都会被调用；本例 Qwen2-VL 的主要变化已经在第 1 步完成，它通常不额外改动这段 ID。其他模型插件才可能在此插入或调整特殊 token ID。

**第 3 步：Collator 处理真实图片。** 样本中的 `images = ["cat.jpg"]` 会被收集。对这个 Qwen2-VL 示例，`get_mm_inputs(...)` 调用图像 Processor 后，先返回一个独立的字典：

```python
mm_inputs = {
    # 每个原始视觉 patch 的归一化像素；patch_dim 由视觉模型的 patch 配置决定
    "pixel_values": FloatTensor[784, patch_dim],

    # 每张图片的时间、高、宽网格；此处 1 × 28 × 28 = 784 个原始 patch
    "image_grid_thw": LongTensor([[1, 28, 28]]),
}
```

其中 `pixel_values` 是 `cat.jpg` 经过 resize、归一化和切 patch 后的数值，不是原始图片文件；`image_grid_thw` 告诉模型这些 patch 如何排成网格。由于 `merge_size=2`，4 个原始 patch 合并为 1 个语言侧视觉位置，所以 `784 ÷ 4 = 196`，正好对应第 1 步文本里的 196 个 `<|image_pad|>`。

随后 Collator 会先对 `input_ids / labels / attention_mask` 做 padding，必要时补 `position_ids`、`token_type_ids` 等，再执行：

```python
features.update(mm_inputs)
```

因此真正送进 `model(**batch)` 的结果是：

```text
input_ids / labels / attention_mask        # 文本序列，含 196 个图像位置
pixel_values                               # 784 个原始 patch 的像素表示（示意）
image_grid_thw = [[1, 28, 28]]             # 这 784 个 patch 的网格
```

模型 forward 时，视觉编码器读取 `pixel_values`、按网格合并为视觉特征，再按 `input_ids` 中的图像占位位置把它们接入语言模型。也就是说：**占位 token 决定图像特征放在哪里；`pixel_values` 才是图片内容；两者都不会成为要预测的 label。** 不同模型的 `get_mm_inputs()` 返回键会不同，例如 Mllama 还会有 `aspect_ratio_ids`、`cross_attention_mask`；插件负责屏蔽这种差异。

### 1.4 多模态模型的冻结控制

WebUI 和参数中提供：

```text
freeze_vision_tower
freeze_multi_modal_projector
freeze_language_model
```

典型组合：

| 目标 | vision tower | projector | language model |
|---|---:|---:|---:|
| 只训练对齐层 | 冻结 | 训练 | 冻结 |
| 调整语言能力 | 冻结 | 可训练 | 训练/LoRA |
| 全面多模态微调 | 训练 | 训练 | 训练 |

### 1.5 多模态一句话总结

> MM Plugin 屏蔽不同模型的占位符和视觉 token 差异，Processor 产生视觉/音频张量，Collator 最终把文本与多模态特征组装成同一个 batch。

---

# 第五部分：Gradio WebUI

## 一、WebUI 总体架构

```text
interface.py：创建页面
       ↓
components/*.py：创建具体控件
       ↓
Manager：维护 elem_id ↔ Gradio Component 映射
       ↓
Engine：组合 Manager、Runner、ChatModel
       ↓
Runner：解析参数、启动进程、监控日志
```

### 1.1 页面构建

入口：[`src/llamafactory/webui/interface.py`](src/llamafactory/webui/interface.py)

```python
with gr.Blocks(title=f"LLaMA Factory ({hostname})", css=CSS) as demo:
    engine.manager.add_elems("top", create_top())

    with gr.Tab("Train"):
        engine.manager.add_elems("train", create_train_tab(engine))

    with gr.Tab("Evaluate & Predict"):
        engine.manager.add_elems("eval", create_eval_tab(engine))

    with gr.Tab("Chat"):
        engine.manager.add_elems("infer", create_infer_tab(engine))

    with gr.Tab("Export"):
        engine.manager.add_elems("export", create_export_tab(engine))
```

### 1.2 训练页面控件

入口：[`src/llamafactory/webui/components/train.py`](src/llamafactory/webui/components/train.py)

页面包含：

- stage 和数据集；
- learning rate、epoch、batch size、gradient accumulation；
- Full/Freeze/LoRA 参数；
- DPO/KTO/PPO 偏好参数；
- 多模态冻结和像素参数；
- DeepSpeed 配置；
- 开始、停止、预览命令、保存参数；
- 日志、进度条、loss 图。

### 1.3 Gradio 事件绑定

```python
cmd_preview_btn.click(
    engine.runner.preview_train,
    input_elems,
    output_elems,
)

start_btn.click(
    engine.runner.run_train,
    input_elems,
    output_elems,
)

stop_btn.click(engine.runner.set_abort)
```

Gradio 组件本身不执行训练，它只是把当前组件值传给 Runner。

### 1.4 参数解析与启动子进程

入口：[`src/llamafactory/webui/runner.py`](src/llamafactory/webui/runner.py)

`_parse_train_args` 将页面控件转换为训练字典，例如：

```text
top.model_path           → model_name_or_path
train.training_stage     → stage
top.finetuning_type      → finetuning_type
train.dataset            → dataset
train.learning_rate      → learning_rate
```

然后 `_launch` 保存配置，并启动命令行训练：

```python
self.trainer = Popen(
    ["llamafactory-cli", "train", save_cmd(args)],
    env=env,
    stdout=webui_log,
    stderr=webui_log,
    text=True,
)
```

这里没有 `shell=True`，可以避免把用户输入直接交给 shell 解析。

### 1.5 训练监控

`monitor()` 循环完成：

```text
读取 trainer 日志
  ↓
计算当前进度
  ↓
生成 loss 曲线
  ↓
yield Gradio 组件更新字典
  ↓
检查子进程是否结束
```

因此 WebUI 与训练核心解耦：

```text
WebUI 负责交互和进程管理
CLI/Trainer 负责真正训练
```

### 1.6 WebUI 一句话总结

> Gradio 页面收集参数，Runner 把参数保存为配置并调用 `llamafactory-cli train`，随后轮询日志，把训练进度和 loss 曲线持续返回页面。

---

# 第六部分：把所有模块串成一条链

## 一、从点击“开始训练”到参数更新

```text
1. 用户在 WebUI 选择：
   stage=sft、finetuning_type=lora、dataset=xxx
                         ↓
2. start_btn.click 触发 Runner.run_train
                         ↓
3. Runner._parse_train_args 把控件值变成参数字典
                         ↓
4. Runner._launch 保存 YAML，启动：
   llamafactory-cli train config.yaml
                         ↓
5. cli.main → launcher.launch → train.tuner.run_exp
                         ↓
6. get_train_args 将配置拆成五类 dataclass 参数
                         ↓
7. _training_function 根据 stage 调用 run_sft
                         ↓
8. load_tokenizer，同时尝试加载 AutoProcessor
                         ↓
9. get_template_and_fix_tokenizer 取得聊天模板
                         ↓
10. get_dataset 读取、转换、切分、map/tokenize
                         ↓
11. load_model 加载基座模型并执行 init_adapter
                         ↓
12. init_adapter 插入 LoRA，只保留 Adapter 参数可训练
                         ↓
13. SFTDataCollator 进行 padding、多模态处理和 batch 组装
                         ↓
14. CustomSeq2SeqTrainer.train
                         ↓
15. forward → logits → masked cross entropy
                         ↓
16. backward → optimizer.step → scheduler.step
                         ↓
17. callback 写 trainer_log.jsonl 和 checkpoint
                         ↓
18. WebUI monitor 读取日志并更新进度条、loss 图
```

这条链路是整场源码介绍最重要的部分。前面讲的所有模块都可以挂回这条主线上。

---

## 二、建议现场展示的关键代码

如果只能展示 12 个位置，优先选择：

1. [`src/llamafactory/train/tuner.py`](src/llamafactory/train/tuner.py)：六种 stage 的总分发。
2. [`src/llamafactory/data/loader.py`](src/llamafactory/data/loader.py)：stage 到数据处理器的映射。
3. [`src/llamafactory/data/processor/pretrain.py`](src/llamafactory/data/processor/pretrain.py)：PT packing。
4. [`src/llamafactory/data/processor/supervised.py`](src/llamafactory/data/processor/supervised.py)：SFT label mask。
5. [`src/llamafactory/train/rm/trainer.py`](src/llamafactory/train/rm/trainer.py)：RM pairwise loss。
6. [`src/llamafactory/train/dpo/trainer.py`](src/llamafactory/train/dpo/trainer.py)：chosen/rejected log probability 和 DPO loss。
7. [`src/llamafactory/data/processor/feedback.py`](src/llamafactory/data/processor/feedback.py)：KTO tags 与 KL 样本。
8. [`src/llamafactory/train/ppo/trainer.py`](src/llamafactory/train/ppo/trainer.py)：PPO 在线训练循环。
9. [`src/llamafactory/model/loader.py`](src/llamafactory/model/loader.py)：模型类选择和 Value Head。
10. [`src/llamafactory/model/adapter.py`](src/llamafactory/model/adapter.py)：Full/Freeze/LoRA。
11. [`src/llamafactory/data/mm_plugin.py`](src/llamafactory/data/mm_plugin.py)：多模态 Plugin。
12. [`src/llamafactory/webui/runner.py`](src/llamafactory/webui/runner.py)：WebUI 启动训练子进程。


# 附录 A：LLaMAFactory 训练参数详解

## A.1 参数是如何进入训练代码的

LLaMAFactory 的参数定义集中在 [`src/llamafactory/hparams`](src/llamafactory/hparams) 中。一次训练配置最终会被解析成五组对象：

| 参数对象 | 源码 | 主要职责 |
|---|---|---|
| `ModelArguments` | [`model_args.py`](src/llamafactory/hparams/model_args.py) | 模型、Tokenizer、量化、多模态 Processor、推理和导出 |
| `DataArguments` | [`data_args.py`](src/llamafactory/hparams/data_args.py) | 数据集、模板、截断、packing 和数据预处理 |
| `TrainingArguments` | [`training_args.py`](src/llamafactory/hparams/training_args.py) | batch、学习率、epoch、日志、保存、评估和分布式训练 |
| `FinetuningArguments` | [`finetuning_args.py`](src/llamafactory/hparams/finetuning_args.py) | stage、Full/Freeze/LoRA、DPO/KTO/PPO 和优化算法 |
| `GeneratingArguments` | [`generating_args.py`](src/llamafactory/hparams/generating_args.py) | 推理、生成式评估和 PPO 在线生成参数 |

训练入口中：

```python
model_args, data_args, training_args, finetuning_args, generating_args = get_train_args(args)
```

相同的 YAML 字段会根据字段名自动分配到对应 dataclass。例如：

```yaml
model_name_or_path: Qwen/Qwen3-4B-Instruct-2507  # ModelArguments
dataset: alpaca_en_demo                          # DataArguments
learning_rate: 1.0e-4                           # TrainingArguments
finetuning_type: lora                           # FinetuningArguments
max_new_tokens: 512                             # GeneratingArguments
```

参数来源可以是：

```text
YAML/JSON 配置文件
CLI 参数
WebUI 控件
```

它们最终都会进入相同的 `get_train_args`，所以 WebUI 训练和命令行训练没有两套不同的核心逻辑。

---

## A.2 最核心的任务选择参数

| 参数 | 默认值 | 可选值 | 功能 |
|---|---:|---|---|
| `stage` | `sft` | `pt/sft/rm/ppo/dpo/kto` | 选择训练阶段，决定数据处理器、workflow 和 Trainer |
| `do_train` | 通常配置为 `true` | 布尔值 | 是否执行 `trainer.train()` |
| `do_eval` | `false` | 布尔值 | 是否在验证集上执行 evaluate |
| `do_predict` | `false` | 布尔值 | 是否生成并保存预测结果 |
| `finetuning_type` | `lora` | `full/freeze/lora/oft` | 决定哪些模型参数参与训练 |
| `model_name_or_path` | 无，必填 | 本地路径或 Hub ID | 基座模型、Tokenizer 和 Processor 的来源 |
| `dataset` | 无 | 数据集名，多个用逗号分隔 | 训练数据集，对应 `dataset_info.json` 中的注册名 |
| `template` | `None` | 如 `llama3`、`qwen3` | 决定 system/user/assistant 如何渲染成 prompt |
| `output_dir` | Transformers 默认值 | 目录 | checkpoint、日志、指标和最终权重的保存位置 |

最小训练配置通常至少需要：

```yaml
model_name_or_path: 模型路径
stage: sft
do_train: true
finetuning_type: lora
dataset: 数据集名称
template: 模型对应模板
output_dir: 输出路径
```

---

## A.3 模型与 Tokenizer 参数

### A.3.1 基础加载参数

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `model_name_or_path` | 必填 | 本地模型目录或 Hugging Face/ModelScope 模型 ID |
| `adapter_name_or_path` | `None` | 要加载的 LoRA/OFT Adapter；多个路径用逗号分隔，可用于合并或继续训练 |
| `adapter_folder` | `None` | Adapter 位于仓库子目录时指定子目录 |
| `cache_dir` | `None` | 下载模型与 Tokenizer 的缓存目录 |
| `model_revision` | `main` | Hub 的 branch、tag 或 commit，复现实验时建议固定 commit |
| `hf_hub_token` | `None` | Hugging Face 私有或受限模型访问令牌 |
| `ms_hub_token` | `None` | ModelScope 访问令牌 |
| `om_hub_token` | `None` | OpenMind/Modelers Hub 访问令牌 |
| `trust_remote_code` | `false` | 是否执行模型仓库提供的自定义 Python 代码；只对可信仓库开启 |
| `low_cpu_mem_usage` | `true` | 使用低 CPU 峰值内存方式加载权重 |
| `train_from_scratch` | `false` | `true` 时只按 config 随机初始化，不加载预训练权重 |
| `print_param_status` | `false` | 打印每个参数的 dtype、device 和 `requires_grad`，适合验证 Freeze/LoRA |

### A.3.2 Tokenizer 与词表参数

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `use_fast_tokenizer` | `true` | 优先使用 Rust `tokenizers` 实现，通常更快 |
| `split_special_tokens` | `false` | 是否允许特殊 token 被继续拆分，通常保持 `false` |
| `resize_vocab` | `false` | 新增 token 后调整 input embedding 和 lm_head 大小 |
| `add_tokens` | `None` | 增加普通 token，多个使用逗号分隔 |
| `add_special_tokens` | `None` | 增加不可被普通规则拆分的特殊 token |
| `new_special_tokens_config` | `None` | 用 YAML 描述新特殊 token 的语义，用于语义初始化 |
| `init_special_tokens` | `noise_init` | 新 token 初始化方式：噪声、描述语义、描述语义加噪声 |

使用 `resize_vocab` 时需要注意：

```text
Tokenizer 词表增大
        ↓
model input_embeddings 和 lm_head 必须同步扩容
        ↓
LoRA 训练时这些层可能需要放入 additional_target
```

代码会在需要时把 embedding/lm_head 加到 `modules_to_save`，否则新 token 对应权重不会被 Adapter checkpoint 保存。

### A.3.3 注意力、长上下文和性能参数

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `rope_scaling` | `None` | RoPE 扩展策略，如 `linear/dynamic/yarn/llama3`，用于延长上下文 |
| `flash_attn` | `auto` | 选择 attention 实现，FlashAttention 可降低显存、提高速度 |
| `shift_attn` | `false` | 启用 LongLoRA 的 Shift Short Attention |
| `disable_gradient_checkpointing` | `false` | 是否关闭框架默认使用的梯度检查点；关闭检查点会更快但更耗显存 |
| `use_reentrant_gc` | `true` | 选择 reentrant gradient checkpointing 实现 |
| `use_unsloth` | `false` | 使用 Unsloth 优化的模型/LoRA 加载与训练路径 |
| `use_unsloth_gc` | `false` | 使用 Unsloth 风格 gradient checkpointing |
| `enable_liger_kernel` | `false` | 启用 Liger Kernel 融合算子，提高训练性能 |
| `use_v1_kernels` | `false` | 启用项目新内核接口，属于较新的实验路径 |
| `upcast_layernorm` | `false` | 将 LayerNorm 权重升为 FP32，提高数值稳定性但增加部分开销 |
| `upcast_lmhead_output` | `false` | 将 lm_head 输出升为 FP32，降低低精度 logits 数值误差 |
| `moe_aux_loss_coef` | `None` | MoE router 辅助均衡损失系数，避免专家负载过度集中 |
| `mixture_of_depths` | `None` | `convert` 将普通模型转 MoD，`load` 加载已有 MoD 模型 |

`rope_scaling` 并不自动让模型真正掌握长上下文，它只是修改位置编码范围；训练数据长度、显存和模型原始能力仍然重要。

### A.3.4 代码派生参数

下面这些字段由框架计算，通常不要在 YAML 中手工填写：

| 参数 | 来源 | 作用 |
|---|---|---|
| `compute_dtype` | 从 `bf16/fp16` 等推导 | 模型前向计算 dtype |
| `device_map` | 从训练/推理模式和分布式环境推导 | 模型设备放置 |
| `model_max_length` | 从 `cutoff_len` 等推导 | 模型输入最大长度 |
| `block_diag_attn` | 从 `neat_packing` 推导 | 是否使用块对角 attention mask |

---

## A.4 量化参数

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `quantization_method` | `bnb` | 在线量化后端，如 bitsandbytes、HQQ、EETQ |
| `quantization_bit` | `None` | 模型在线量化位数，常用 `4` 或 `8`；不填表示不量化 |
| `quantization_type` | `nf4` | bitsandbytes 4-bit 数据类型，`nf4` 通常比 `fp4` 更适合正态分布权重 |
| `double_quantization` | `true` | 对量化常数再次量化，进一步节约显存 |
| `quantization_device_map` | `None` | 推理量化模型的设备映射，`auto` 可自动分配 |

典型 QLoRA：

```yaml
finetuning_type: lora
quantization_bit: 4
quantization_method: bnb
quantization_type: nf4
double_quantization: true
```

关键限制：

```text
在线量化模型通常只能训练 LoRA/OFT Adapter，
不能按普通 Full/Freeze 方式直接更新量化权重。
```

---

## A.5 数据参数

参数定义：[`src/llamafactory/hparams/data_args.py`](src/llamafactory/hparams/data_args.py)

### A.5.1 数据来源与模板

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `dataset` | `None` | 训练数据集名称，多个使用逗号分隔 |
| `eval_dataset` | `None` | 独立验证数据集名称；设置后不能同时使用 `val_size` 切分 |
| `dataset_dir` | `data` | `dataset_info.json` 和本地数据文件所在目录 |
| `media_dir` | `dataset_dir` | 图片、视频、音频素材的根目录 |
| `template` | `None` | 对话模板，必须与模型使用的 chat template 匹配 |
| `default_system` | `None` | 覆盖模板默认 system prompt |
| `tool_format` | `None` | 函数调用/工具调用数据使用的工具描述格式 |
| `enable_thinking` | `true` | 对推理模型启用 thinking 模式 |
| `preserve_thinking` | `false` | 多轮历史中是否保留此前的 thinking 内容 |

模板选错的后果通常不是程序报错，而是模型训练时学到错误的角色 token 和结束 token，因此 `template` 是最需要核对的参数之一。

### A.5.2 长度、标签与 Packing

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `cutoff_len` | `2048` | tokenize 后单条样本最大长度，越大显存越高 |
| `train_on_prompt` | `false` | `true` 时 prompt token 也参与 SFT loss |
| `mask_history` | `false` | `true` 时多轮 SFT 只训练最后一轮回答 |
| `ignore_pad_token_for_loss` | `true` | 将 padding label 替换为 `IGNORE_INDEX`，不计算 loss |
| `packing` | `None` | 将多个短样本组合成定长序列；PT 会自动启用 |
| `neat_packing` | `false` | 使用块对角 attention，避免 packed 子样本相互注意 |

约束关系：

- `mask_history` 与 `train_on_prompt` 不能同时开启。
- `neat_packing=true` 会自动令 `packing=true`。
- Packing 打开后，框架会对有效长度进行内部调整。

`cutoff_len` 对普通全注意力的主要影响近似为：

$$
\text{attention memory}\propto L^2
$$

序列长度从 2048 增加到 4096，attention 相关中间量理论上可能接近 4 倍，因此不能只看模型参数量估计显存。

### A.5.3 数据混合与预处理

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `mix_strategy` | `concat` | 多数据集混合策略：直接拼接或不同形式的 interleave |
| `interleave_probs` | `None` | 多数据集交错采样概率，数量必须与数据集数量一致 |
| `streaming` | `false` | 流式读取数据，适合超大或远程数据集 |
| `buffer_size` | `16384` | Streaming 模式随机采样缓冲区大小 |
| `overwrite_cache` | `false` | 忽略旧 tokenized cache 并重新预处理 |
| `preprocessing_batch_size` | `1000` | 一次交给 dataset map 的样本数，不等于训练 batch size |
| `preprocessing_num_workers` | `None` | tokenize/map 的并行进程数 |
| `max_samples` | `None` | 每个数据集最多取多少条，适合调试小跑 |
| `tokenized_path` | `None` | 保存或加载预 tokenized 数据，减少重复预处理 |
| `data_shared_file_system` | `false` | 多节点是否共享数据文件系统，影响主进程优先执行范围 |

Streaming 限制：

- `streaming=true` 时不能使用 `max_samples`；
- 流式模式下 `val_size` 应使用整数条数，而不是小数比例。

### A.5.4 验证集参数

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `val_size` | `0.0` | 从训练集划分验证集；小于 1 表示比例，大于等于 1 表示条数 |
| `eval_dataset` | `None` | 使用独立验证集；与非零 `val_size` 互斥 |
| `eval_on_each_dataset` | `false` | 多个验证数据集是否分别计算指标 |
| `eval_num_beams` | `None` | 生成式评估的 beam 数，传给 `model.generate` |

---

## A.6 通用训练参数

`TrainingArguments` 继承 Transformers 的 `Seq2SeqTrainingArguments`，所以大量参数由 Transformers 提供，LLaMAFactory 直接复用。

### A.6.1 Batch 与训练步数

| 参数 | 功能与影响 |
|---|---|
| `per_device_train_batch_size` | 每张 GPU 每次前向的训练样本数，直接影响显存 |
| `per_device_eval_batch_size` | 每张 GPU 的评估 batch size |
| `gradient_accumulation_steps` | 累积多少次前向/反向后再执行一次 optimizer step |
| `num_train_epochs` | 完整遍历训练数据的次数 |
| `max_steps` | 指定优化器最大步数；大于 0 时通常覆盖 epoch 计算 |
| `dataloader_num_workers` | DataLoader 子进程数量，提高数据读取速度 |
| `dataloader_pin_memory` | 是否固定 CPU 内存，通常有利于 CPU→GPU 传输 |
| `seed` | 数据打乱和模型训练随机种子 |
| `data_seed` | 单独控制数据采样随机性 |

有效全局 batch size：

$$
B_{effective}
=
B_{device}
\times
N_{GPU}
\times
N_{accumulation}
$$

例如：

```yaml
per_device_train_batch_size: 2
gradient_accumulation_steps: 8
```

使用 4 张 GPU 时：

```text
有效 batch size = 2 × 8 × 4 = 64
```

`gradient_accumulation_steps` 能减少单次显存，但不能减少完成相同 token 数所需的总计算量。

### A.6.2 优化器与学习率

| 参数 | 功能与影响 |
|---|---|
| `learning_rate` | 初始/峰值学习率，是最重要的优化参数之一 |
| `optim` | 优化器名称，如 `adamw_torch`、8-bit AdamW 等 |
| `weight_decay` | 权重衰减，通常不作用于 bias 和 LayerNorm |
| `adam_beta1` | Adam 一阶动量系数 |
| `adam_beta2` | Adam 二阶动量系数 |
| `adam_epsilon` | Adam 数值稳定项 |
| `max_grad_norm` | 梯度裁剪阈值，抑制梯度爆炸；`0` 通常表示不裁剪 |
| `lr_scheduler_type` | 学习率调度器，如 `cosine/linear/constant` |
| `warmup_ratio` | 总训练步数中 warmup 所占比例 |
| `warmup_steps` | 固定 warmup 步数；设置后通常比 ratio 更直接 |

经验上：

```text
Full 微调学习率通常较小，例如 1e-5 量级；
LoRA 可使用更大学习率，例如 1e-4 量级；
DPO/KTO 常比 SFT 更保守，例如 5e-6～数十微量级。
```

这些只是常见起点，模型大小、数据量、batch size 和任务都会影响最佳值。

### A.6.3 精度与显存

| 参数 | 功能与影响 |
|---|---|
| `bf16` | 使用 BF16 混合精度，动态范围大，现代 GPU 上通常优先 |
| `fp16` | 使用 FP16 混合精度，兼容较旧 GPU但更容易溢出 |
| `pure_bf16` | 全程纯 BF16，不使用 AMP；更省部分转换但数值风险更高 |
| `tf32` | Ampere 及更新 GPU 上允许 FP32 矩阵乘使用 TF32 加速 |
| `gradient_checkpointing` | 不保存全部激活，反向时重算，以计算时间换显存 |
| `fp8` | 使用 FP8 混合精度，需要合适的硬件和后端 |
| `fp8_backend` | `auto/torchao/te/msamp`，选择 FP8 实现 |

不要同时开启不兼容的精度模式。常见配置是二选一：

```yaml
bf16: true
fp16: false
```

### A.6.4 日志、评估和保存

| 参数 | 功能与影响 |
|---|---|
| `logging_steps` | 每多少步记录一次训练日志 |
| `logging_strategy` | 按 `steps/epoch/no` 记录日志 |
| `eval_strategy` | 按 `steps/epoch/no` 执行验证 |
| `eval_steps` | `eval_strategy=steps` 时的验证间隔 |
| `save_strategy` | 按 `steps/epoch/no` 保存 checkpoint |
| `save_steps` | `save_strategy=steps` 时的保存间隔 |
| `save_total_limit` | 最多保留多少个 checkpoint，防止磁盘被占满 |
| `resume_from_checkpoint` | 从指定 checkpoint 恢复模型、优化器、调度器和 Trainer 状态 |
| `load_best_model_at_end` | 训练结束时恢复验证指标最好的 checkpoint |
| `metric_for_best_model` | 判断最佳 checkpoint 的指标名称 |
| `greater_is_better` | 指标越大是否越好；loss 应设为 `false` |
| `report_to` | 日志平台，如 TensorBoard、WandB、SwanLab 等 |
| `run_name` | 实验名称 |
| `plot_loss` | LLaMAFactory 是否额外生成 loss 曲线图 |
| `include_effective_tokens_per_second` | 统计每秒有效训练 token 数 |

若使用：

```yaml
load_best_model_at_end: true
```

需要确保评估与保存策略兼容，通常令 `eval_strategy`、`save_strategy` 都为 `steps`，并合理设置间隔。

### A.6.5 生成式评估

| 参数 | 功能与影响 |
|---|---|
| `predict_with_generate` | SFT 评估时调用 `model.generate`，用于文本级指标 |
| `generation_max_length` | 评估生成的最大总长度 |
| `generation_num_beams` | 评估生成的 beam 数 |
| `compute_accuracy` | 不生成文本时计算 token-level accuracy |

`predict_with_generate=true` 通常明显慢于只计算 loss，因为它需要自回归生成。

### A.6.6 分布式参数

| 参数 | 功能与影响 |
|---|---|
| `deepspeed` | DeepSpeed JSON 路径，常用于 ZeRO-2/ZeRO-3 |
| `fsdp` | Transformers/Accelerate FSDP 配置 |
| `ddp_timeout` | 分布式进程组超时时间，模型加载慢时可调大 |
| `ddp_find_unused_parameters` | DDP 是否查找未参与前向的参数；LoRA 常需特别处理 |
| `local_rank` | 启动器注入的本地进程编号，通常不手填 |
| `ray_num_workers` | Ray 训练 worker 数量，默认 1 |
| `ray_init_kwargs` | 传给 `ray.init` 的额外参数 |

---

## A.7 Full、Freeze、LoRA 参数

### A.7.1 公共微调参数

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `finetuning_type` | `lora` | `full/freeze/lora/oft` |
| `pure_bf16` | `false` | 训练参数是否保持纯 BF16 |
| `disable_shuffling` | `false` | 禁止训练集打乱，主要用于可复现或特殊顺序数据 |
| `early_stopping_steps` | `None` | 指标连续多少次评估不提升后提前停止 |
| `use_llama_pro` | `false` | 只训练 LLaMA-Pro 扩展 block |

### A.7.2 Freeze 参数

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `freeze_trainable_layers` | `2` | 正数训练最后 N 层，负数训练最前 N 层 |
| `freeze_trainable_modules` | `all` | 选中层内训练哪些子模块，多个用逗号分隔 |
| `freeze_extra_modules` | `None` | 额外开放非 Transformer block 模块，如 embedding/lm_head |

例子：

```yaml
finetuning_type: freeze
freeze_trainable_layers: 4
freeze_trainable_modules: all
freeze_extra_modules: lm_head
```

表示训练最后 4 个 block 的全部子模块，同时训练 `lm_head`。

### A.7.3 LoRA 参数

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `lora_rank` | `8` | 低秩维度 $r$；越大容量越强，参数和显存也越多 |
| `lora_alpha` | `2 × rank` | LoRA 缩放系数，实际缩放通常为 $\alpha/r$ |
| `lora_dropout` | `0.0` | LoRA 分支 dropout，数据少时可适当增加 |
| `lora_target` | `all` | 插入 LoRA 的目标模块；`all` 自动选择线性层 |
| `additional_target` | `None` | LoRA 外还需完整训练和保存的模块 |
| `create_new_adapter` | `false` | 已加载 Adapter 时是否再创建新的随机 Adapter |
| `loraplus_lr_ratio` | `None` | LoRA+ 中 $lr_B/lr_A$ 的比例 |
| `loraplus_lr_embedding` | `1e-6` | LoRA embedding 层学习率 |
| `use_rslora` | `false` | 使用 Rank-Stabilized LoRA 缩放 |
| `use_dora` | `false` | 使用 Weight-Decomposed LoRA |
| `pissa_init` | `false` | 使用 PiSSA 初始化 Adapter |
| `pissa_iter` | `16` | PiSSA FSVD 迭代次数，`-1` 表示不用快速近似 |
| `pissa_convert` | `false` | 训练后将 PiSSA 转换成普通 LoRA Adapter |

典型配置：

```yaml
finetuning_type: lora
lora_target: all
lora_rank: 8
lora_alpha: 16
lora_dropout: 0.0
```

`lora_target` 常见精确写法可能包含：

```text
q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj
```

具体模块名必须与模型 `named_modules()` 一致，因此跨模型复制配置时要核对名称。

---

## A.8 RM、DPO、KTO、PPO 参数

### A.8.1 通用偏好参数

| 参数 | 默认值 | 使用阶段 | 功能 |
|---|---:|---|---|
| `pref_beta` | `0.1` | DPO/KTO 等 | 偏好损失强度及相对参考模型的约束尺度 |
| `pref_ftx` | `0.0` | DPO/KTO | 混合 SFT loss 的系数，减轻偏好训练造成的能力退化 |
| `ref_model` | `None` | DPO/KTO/PPO | 独立参考模型路径；为空时 LoRA 场景可关闭 Adapter 使用基座 |
| `ref_model_adapters` | `None` | DPO/KTO/PPO | 参考模型 Adapter 路径 |
| `ref_model_quantization_bit` | `None` | DPO/KTO/PPO | 参考模型量化位数，用于降低显存 |

`pref_beta` 不是普通学习率：

- 值较大时，概率差对 loss 的影响更强；
- 值较小时，偏好更新通常更温和；
- 最佳值依赖 loss 类型、数据质量和模型规模。

### A.8.2 RM 参数

RM 没有独立的 `rm_beta`。其关键配置是：

```yaml
stage: rm
dataset: 偏好数据集
finetuning_type: lora
```

`add_valuehead=True` 由 `run_rm` 自动传入，不需要在 YAML 手工设置。

常见 RM 配置：

```yaml
model_name_or_path: 基座或SFT模型
stage: rm
do_train: true
finetuning_type: lora
dataset: 偏好数据集
template: 模型模板
cutoff_len: 2048
lora_target: all
output_dir: saves/model/lora/rm
per_device_train_batch_size: 1
gradient_accumulation_steps: 8
learning_rate: 1.0e-4
num_train_epochs: 3
bf16: true
```

### A.8.3 DPO 参数

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `pref_loss` | `sigmoid` | `sigmoid/hinge/ipo/kto_pair/orpo/simpo` |
| `pref_beta` | `0.1` | 偏好损失尺度 |
| `pref_ftx` | `0.0` | chosen 回答 SFT loss 的混合权重 |
| `pref_bco_weight` | `0.0` | BCO loss 的混合系数 |
| `dpo_label_smoothing` | `0.0` | cDPO 标签平滑，范围应在 0～0.5 |
| `simpo_gamma` | `0.5` | SimPO 目标 reward margin |
| `ld_alpha` | `None` | LD-DPO 中冗长 token log-probability 的权重控制 |

典型 DPO：

```yaml
stage: dpo
pref_loss: sigmoid
pref_beta: 0.1
pref_ftx: 0.0
```

如果：

```yaml
pref_loss: orpo
```

Trainer 会走 ORPO 分支；ORPO 自带 chosen 的 SFT 项和 odds-ratio 偏好项，通常不使用标准 DPO reference loss。

### A.8.4 KTO 参数

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `pref_beta` | `0.1` | 策略/reference log-ratio 缩放 |
| `kto_chosen_weight` | `1.0` | desirable 样本损失权重 |
| `kto_rejected_weight` | `1.0` | undesirable 样本损失权重 |
| `pref_ftx` | `0.0` | 可选 desirable 样本 SFT loss |
| `ref_model` | `None` | 参考模型路径 |

当好坏样本数量明显不平衡时，可调整：

```yaml
kto_chosen_weight: 1.0
kto_rejected_weight: 2.0
```

但它不能替代数据层面的质量检查和合理采样。

### A.8.5 PPO 参数

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `ppo_buffer_size` | `1` | 一个 PPO 优化阶段中经验缓冲包含的 mini-batch 数 |
| `ppo_epochs` | `4` | 同一批经验重复优化的轮数；越大利用更充分但更容易过拟合旧经验 |
| `ppo_score_norm` | `false` | 对 RM score 做运行归一化 |
| `ppo_whiten_rewards` | `false` | 计算 advantage 前白化 reward |
| `ppo_target` | `6.0` | 自适应 KL 控制的目标 KL |
| `reward_model` | `None` | RM checkpoint、Adapter 路径或 API 地址 |
| `reward_model_type` | `lora` | `lora/full/api`，决定 RM 的使用方式 |
| `reward_model_adapters` | `None` | 完整 RM 还需要额外 Adapter 时指定 |
| `reward_model_quantization_bit` | `None` | 独立 RM 的量化位数 |
| `ref_model` | `None` | PPO 参考模型路径 |

PPO 必须重点核对：

```yaml
stage: ppo
reward_model: saves/model/lora/rm
reward_model_type: lora
```

约束：LoRA Reward Model 只适用于 LoRA PPO；如果 Policy 使用 Full/Freeze 微调，应使用完整 RM 或 API RM。

---

## A.9 多模态参数

### A.9.1 图像、视频、音频预处理

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `image_max_pixels` | `768×768` | 图片最大像素数；越大视觉 token 和显存通常越多 |
| `image_min_pixels` | `32×32` | 图片最小像素数，过小图片可能上采样 |
| `image_do_pan_and_scan` | `false` | Gemma 3 的 pan-and-scan 图像处理 |
| `crop_to_patches` | `false` | InternVL 等模型是否把图片裁成多个 patch |
| `video_max_pixels` | `256×256` | 每帧最大像素数 |
| `video_min_pixels` | `16×16` | 每帧最小像素数 |
| `video_fps` | `2.0` | 每秒采样帧数 |
| `video_maxlen` | `128` | 单视频最多采样帧数 |
| `use_audio_in_video` | `false` | 视频模型是否同时使用视频音轨 |
| `audio_sampling_rate` | `16000` | 音频重采样率 |

视频训练的输入规模同时受以下参数影响：

$$
\text{visual workload}
\propto
\text{frames}
\times
\text{pixels per frame}
$$

因此显存不足时，应同时考虑降低 `video_fps`、`video_maxlen` 和 `video_max_pixels`。

### A.9.2 多模态模块冻结

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `freeze_vision_tower` | `true` | 冻结视觉编码器 |
| `freeze_multi_modal_projector` | `true` | 冻结视觉特征到语言空间的 projector |
| `freeze_language_model` | `false` | 冻结语言模型部分 |

几个典型组合：

```yaml
# 只训练 projector
freeze_vision_tower: true
freeze_multi_modal_projector: false
freeze_language_model: true
```

```yaml
# 冻结视觉塔，对语言模型做 LoRA
freeze_vision_tower: true
freeze_multi_modal_projector: true
freeze_language_model: false
finetuning_type: lora
```

---

## A.10 生成参数

参数定义：[`src/llamafactory/hparams/generating_args.py`](src/llamafactory/hparams/generating_args.py)

| 参数 | 默认值 | 功能与影响 |
|---|---:|---|
| `do_sample` | `true` | 是否随机采样；`false` 时通常使用 greedy/beam search |
| `temperature` | `0.95` | 缩放 logits；低值更确定，高值更多样 |
| `top_p` | `0.7` | nucleus sampling，只保留累计概率达到阈值的最小 token 集合 |
| `top_k` | `50` | 只保留概率最高的 K 个 token |
| `num_beams` | `1` | Beam Search 宽度；1 表示不使用 beam search |
| `max_length` | `1024` | prompt + response 的最大总长度；会被有效的 `max_new_tokens` 覆盖 |
| `max_new_tokens` | `1024` | 最多新生成多少 token，不包含 prompt 长度 |
| `repetition_penalty` | `1.0` | 重复惩罚，1.0 表示不惩罚 |
| `length_penalty` | `1.0` | Beam Search 的长度惩罚 |
| `skip_special_tokens` | `true` | decode 时移除特殊 token |

参数关系：

- `temperature/top_p/top_k` 主要在 `do_sample=true` 时有效；
- `num_beams>1` 开启 Beam Search，会增加生成时间和显存；
- `max_new_tokens>0` 时，代码会删除 `max_length`，避免两个长度参数冲突；
- PPO 的在线回答也会受到这些生成参数影响，进而改变 reward 数据分布。

---

## A.11 高级优化参数

这些参数不是本次一小时汇报的主线，可以作为老师追问时的补充。

### A.11.1 GaLore

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `use_galore` | `false` | 启用低秩梯度投影，降低优化器内存 |
| `galore_target` | `all` | 应用 GaLore 的目标模块 |
| `galore_rank` | `16` | 梯度投影秩 |
| `galore_update_interval` | `200` | 更新投影矩阵的步数间隔 |
| `galore_scale` | `2.0` | 梯度投影缩放 |
| `galore_proj_type` | `std` | 投影类型 |
| `galore_layerwise` | `false` | 分层更新，进一步节省内存 |

### A.11.2 APOLLO

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `use_apollo` | `false` | 启用 APOLLO 优化器 |
| `apollo_target` | `all` | 目标模块 |
| `apollo_rank` | `16` | 低秩维度 |
| `apollo_update_interval` | `200` | 投影更新间隔 |
| `apollo_scale` | `32.0` | 缩放系数 |
| `apollo_proj` | `random` | `svd/random` 投影算法 |
| `apollo_proj_type` | `std` | 投影方向类型 |
| `apollo_scale_type` | `channel` | channel 或 tensor 级缩放 |
| `apollo_layerwise` | `false` | 是否逐层更新 |

### A.11.3 BAdam

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `use_badam` | `false` | 启用 Block-wise Adam |
| `badam_mode` | `layer` | 按层或按参数比例更新 |
| `badam_start_block` | `None` | 起始 block 编号 |
| `badam_switch_mode` | `ascending` | block 选择顺序 |
| `badam_switch_interval` | `50` | 每多少步切换可训练 block |
| `badam_update_ratio` | `0.05` | ratio 模式每次更新参数比例 |
| `badam_mask_mode` | `adjacent` | 连续或分散选取参数 |
| `badam_verbose` | `0` | 调试输出详细程度 |

### A.11.4 OFT

OFT 与 LoRA 一样属于参数高效微调，但它通过正交变换约束更新。当前代码支持以下参数：

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `finetuning_type` | `lora` | 设为 `oft` 后进入 OFT Adapter 路径 |
| `oft_rank` | `0` | OFT 低秩维度；与 block size 的具体约束由 PEFT 处理 |
| `oft_block_size` | `32` | OFT block 大小 |
| `oft_target` | `all` | 应用 OFT 的目标模块 |
| `module_dropout` | `0.0` | OFT 模块 dropout |
| `additional_target` | `None` | OFT 之外需要训练并保存的完整模块 |
| `create_new_adapter` | `false` | 是否在已有 Adapter 基础上新建 Adapter |

### A.11.5 可选训练损失和优化器

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `use_dft_loss` | `false` | SFT 中启用 DFT loss |
| `use_asft_loss` | `false` | SFT 中启用 ASFT loss，并创建/使用参考模型 |
| `asft_alpha` | `0.1` | ASFT 自适应权重的指数/强度参数 |
| `use_eaft_loss` | `false` | SFT 中启用 EAFT loss |
| `eaft_alpha` | `1.0` | EAFT 自适应权重强度 |
| `use_adam_mini` | `false` | 使用 Adam-mini 优化器以降低优化器状态成本 |
| `use_muon` | `false` | 对适合的矩阵参数使用 Muon 优化器 |

这些属于扩展实验能力。介绍源码主干时说明“Trainer 可以通过 `finetuning_args` 切换附加 loss 和自定义 optimizer”即可，不必在一小时内展开公式。

### A.11.6 特殊分布式训练后端

| 参数 | 默认值 | 功能与限制 |
|---|---:|---|
| `use_mca` | `false` | 使用 Megatron Core Adapter 路径，可用于项目支持的 PT/SFT/DPO 场景 |
| `use_hyper_parallel` | `false` | 使用 HyperParallel 的 FSDP/TP 后端，只支持 PT/SFT Full 微调 |
| `hyper_parallel_args` | `None` | HyperParallel 策略 JSON，如 TP 大小和参数 dtype |
| `hyper_parallel_cp_size` | `1` | Context Parallel 大小 |
| `ray_num_workers` | `1` | Ray 分布式 worker 数 |
| `ray_init_kwargs` | `None` | 传给 `ray.init` 的 JSON 参数 |
| `master_addr` | `None` | 分布式主节点地址 |
| `master_port` | `None` | 分布式主节点端口 |

`tuner.py` 会先检查这些特殊后端，再进入普通 `run_pt/run_sft/run_dpo`，因此它们改变的是训练执行后端，而不是数据任务本身。

### A.11.7 KTransformers 参数

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `use_kt` | `false` | 使用 KTransformers AMX MoE SFT/LoRA 路径 |
| `kt_weight_path` | `None` | 预量化 INT8 expert `.kt` 权重路径 |
| `kt_expert_checkpoint_path` | `None` | 用于在线转换的 expert checkpoint |
| `kt_use_lora_experts` | `None` | 是否使用 GPU 侧 LoRA Experts |
| `kt_lora_expert_num` | `None` | GPU 侧 LoRA Expert 数量 |
| `kt_lora_expert_intermediate_size` | `None` | LoRA Expert 中间层维度 |

KTransformers 是特定 MoE/硬件优化路径，不应当作为普通模型训练的默认配置。

### A.11.8 实验记录和性能分析

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `use_swanlab` | `false` | 启用 SwanLab 实验跟踪 |
| `swanlab_project` | `llamafactory` | 项目名称 |
| `swanlab_run_name` | `None` | 当前实验名称 |
| `swanlab_workspace` | `None` | 工作空间 |
| `swanlab_mode` | `cloud` | 云端或本地模式 |
| `enable_torch_profiler` | `false` | 启用 PyTorch Profiler |
| `profiler_output_dir` | `None` | trace 输出目录 |
| `profiler_wait_steps` | `1` | 每个 profiling 周期等待步数 |
| `profiler_warmup_steps` | `1` | 预热步数 |
| `profiler_active_steps` | `1` | 实际记录步数 |
| `profiler_repeat` | `1` | profiling 周期重复次数 |
| `profile_modules` | `None` | 用通配符指定需要测时的模块 |

---

## A.12 推理与导出参数

### A.12.1 推理后端

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `infer_backend` | `huggingface` | 推理后端，可选择 Hugging Face、vLLM、SGLang |
| `infer_dtype` | `auto` | 推理权重/激活 dtype |
| `use_kv_cache` | `true` | 自回归生成时复用历史 K/V，显著提高速度 |
| `offload_folder` | `offload` | CPU/磁盘 offload 路径 |
| `vllm_maxlen` | `4096` | vLLM 最大 prompt+response 长度 |
| `vllm_gpu_util` | `0.7` | vLLM 可使用的 GPU 显存比例 |
| `vllm_enforce_eager` | `false` | `true` 时关闭 CUDA Graph，兼容性更好但可能更慢 |
| `vllm_max_lora_rank` | `32` | vLLM 支持的 LoRA 最大 rank |
| `sglang_maxlen` | `4096` | SGLang 最大序列长度 |
| `sglang_mem_fraction` | `0.7` | SGLang 使用的显存比例 |
| `sglang_tp_size` | `-1` | SGLang Tensor Parallel 大小，负值表示自动/默认 |

### A.12.2 模型导出

| 参数 | 默认值 | 功能 |
|---|---:|---|
| `export_dir` | `None` | 合并/导出后的模型目录，导出时必填 |
| `export_size` | `5` | 每个权重 shard 的最大 GB 数 |
| `export_device` | `cpu` | 在 CPU 或自动选择设备上执行合并/导出 |
| `export_quantization_bit` | `None` | 导出时量化位数 |
| `export_quantization_dataset` | `None` | 导出量化校准数据；启用量化时必填 |
| `export_quantization_nsamples` | `128` | 校准样本数 |
| `export_quantization_maxlen` | `1024` | 校准输入最大长度 |
| `export_legacy_format` | `false` | 保存 `.bin` 而不是 `.safetensors` |
| `export_hub_model_id` | `None` | 导出后推送到 Hub 的仓库名称 |

---

## A.13 每个训练阶段最应该讲的参数

| 阶段 | 核心参数 | 为什么重要 |
|---|---|---|
| PT | `stage=pt`、`dataset`、`cutoff_len`、`packing` | 控制连续文本如何拼接及训练长度 |
| SFT | `stage=sft`、`template`、`train_on_prompt`、`mask_history` | 决定对话格式和哪些 token 计算 loss |
| RM | `stage=rm`、偏好数据、`finetuning_type` | 自动添加 Value Head，学习 chosen/rejected 排序 |
| DPO | `pref_loss`、`pref_beta`、`pref_ftx`、`ref_model` | 决定偏好损失、强度及参考策略 |
| KTO | `pref_beta`、`kto_chosen_weight`、`kto_rejected_weight` | 控制好坏反馈的损失权重 |
| PPO | `reward_model`、`reward_model_type`、`ppo_epochs`、`ppo_target` | 决定奖励来源、经验复用和 KL 控制 |
| Full | `finetuning_type=full`、较小 `learning_rate` | 所有原始权重更新，稳定性要求更高 |
| Freeze | `freeze_trainable_layers/modules` | 精确决定开放哪些原始参数 |
| LoRA | `lora_rank/alpha/target/dropout` | 决定 Adapter 容量、位置和正则化 |

---

## A.14 参数之间最重要的联动关系

### 1. 显存由模型、batch 和序列长度共同决定

```text
显存压力 ≈ 模型权重
         + 梯度
         + 优化器状态
         + batch × sequence length 的激活
         + attention 中间量
```

显存不足时通常依次尝试：

1. 降低 `per_device_train_batch_size`；
2. 增大 `gradient_accumulation_steps` 保持有效 batch；
3. 降低 `cutoff_len`；
4. 开启 `gradient_checkpointing`；
5. 使用 LoRA；
6. 使用 4-bit QLoRA；
7. 使用 DeepSpeed/FSDP 等分布式切分。

### 2. `template` 必须匹配模型

```text
错误 template
→ 错误角色 token/EOS
→ label 边界和推理格式不一致
→ 模型看似收敛但对话效果异常
```

### 3. `packing` 与 attention 隔离

普通 packing 提高利用率，但子样本可能看到前一条样本。`neat_packing` 使用块对角 mask，使 packed 子样本在 attention 上相互隔离。

### 4. LoRA rank、alpha 和学习率

- `rank` 控制容量；
- `alpha/rank` 控制 LoRA 分支缩放；
- `learning_rate` 控制参数更新步长；
- 三者作用不同，不应只通过放大 alpha 替代学习率调节。

### 5. DPO 的 beta 与 reference model

`pref_beta` 作用在 policy/reference 的 log-ratio 上。参考模型定义“更新前的基准行为”，beta 决定偏好差进入 sigmoid 的尺度。

### 6. PPO 的生成参数也是训练参数

PPO 中 `temperature/top_p/max_new_tokens` 会改变在线 response 分布，从而改变 RM score、KL 和 advantage，因此它们不只是推理展示参数。

---

## A.15 参数排错清单

训练前建议按顺序检查：

1. `model_name_or_path` 是否指向正确的基座/SFT checkpoint；
2. `stage` 与数据格式是否一致；
3. `template` 是否与模型系列匹配；
4. `finetuning_type` 是否符合显存预算；
5. LoRA 的 `lora_target` 是否能匹配真实模块名；
6. `cutoff_len` 与显存是否匹配；
7. 有效 batch size 是否按 GPU 数和梯度累积正确计算；
8. `bf16/fp16` 是否符合当前硬件；
9. `eval_dataset` 与 `val_size` 是否互斥；
10. DPO/KTO 是否提供可用 reference model 或可关闭 Adapter 的基座；
11. PPO 是否提供正确类型的 Reward Model；
12. 多模态素材路径和 `media_dir` 是否正确；
13. 输出目录、保存间隔和磁盘容量是否合理；
14. 首次训练先用 `max_samples` 小规模跑通完整链路。

用于检查实际哪些参数可训练：

```yaml
print_param_status: true
```

用于快速验证数据：

```yaml
max_samples: 32
num_train_epochs: 1
logging_steps: 1
```
