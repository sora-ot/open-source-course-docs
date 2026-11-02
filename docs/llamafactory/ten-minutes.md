---
title: "十分钟理解核心实现"
description: "llamafactory · 课堂主线 · 课程讲义"
project: "llamafactory"
sourcePath: "LLaMAFactory_10分钟项目讲义.md"
originalUrl: "/originals/llamafactory/ten-minutes.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

> **阅读提示：**原稿开头以 SFT + LoRA 的调用链引入，后半段重点展开 Full SFT。阅读时请区分两条微调分支；本站保留原稿内容。

# LLaMA-Factory 核心实现

这一节我们不讲：

```bash
llamafactory-cli train xxx.yaml
```

而是打开框架内部，看：

> **LLaMA-Factory 收到“SFT + LoRA”以后，到底执行了哪些 Python 代码？**

我们只追最简单的一条主线：

```text
SFT
+
LoRA
```

整个调用链可以先记成：

```text
run_exp()
   ↓
_training_function()
   ↓
run_sft()
   ↓
load_model()
   ↓
init_adapter()
   ↓
_setup_lora_tuning()
   ↓
LoraConfig(...)
   ↓
get_peft_model()
   ↓
Trainer(...)
   ↓
trainer.train()
```

---

## 1. 第一层：先决定到底训练什么

LLaMA-Factory 最上层有一个类似“总调度器”的东西。

真正代码非常复杂，我们把核心压缩成：

```python
def train(finetuning_args):

    if finetuning_args.stage == "pt":
        run_pt()

    elif finetuning_args.stage == "sft":
        run_sft()

    elif finetuning_args.stage == "rm":
        run_rm()

    elif finetuning_args.stage == "ppo":
        run_ppo()

    elif finetuning_args.stage == "dpo":
        run_dpo()
```

假设配置中：

```python
stage = "sft"
```

那么：

```python
run_sft()
```

被执行。

所以第一层其实没有什么神秘的。

本质就是：

```text
用户配置
   ↓
if / elif
   ↓
选择对应训练算法
```

例如：

```text
stage = sft

↓

进入 SFT workflow
```


---

## 2. 第一个重要部分：数据适配

假设我们自己的数据长这样：

```json
{
    "instruction": "1+1等于多少？",
    "output": "2"
}
```

另外一个数据集可能长这样：

```json
{
    "prompt": "1+1等于多少？",
    "response": "2"
}
```

还有一种：

```json
{
    "messages": [
        {
            "role": "user",
            "content": "1+1等于多少？"
        },
        {
            "role": "assistant",
            "content": "2"
        }
    ]
}
```

如果后面的训练代码分别处理这三种格式，会非常麻烦。

所以 LLaMA-Factory 首先做：

```text
各种不同 Dataset
        ↓
    数据适配器
        ↓
统一内部格式
```

可以把它理解成：

```python
def convert_example(example):

    prompt = [
        {
            "role": "user",
            "content": example["instruction"]
        }
    ]

    response = [
        {
            "role": "assistant",
            "content": example["output"]
        }
    ]

    return {
        "_prompt": prompt,
        "_response": response
    }
```

于是：

```json
{
    "instruction": "1+1等于多少？",
    "output": "2"
}
```

变成：

```python
_prompt = [
    {
        "role": "user",
        "content": "1+1等于多少？"
    }
]

_response = [
    {
        "role": "assistant",
        "content": "2"
    }
]
```

这就是一种非常典型的：

> **Adapter 思想。**

外面的数据可以千奇百怪，

但是到了框架内部：

```text
统一格式
```

后面的代码就完全不用关心原始数据是什么样。

---

## 3. LLaMA-Factory 真正的数据 Loader

当前 LLaMA-Factory 加载数据以后，会调用：

```python
align_dataset(...)
```

把数据转成框架内部统一格式。

大致可以理解成：

```python
dataset = load_dataset(...)

dataset = align_dataset(
    dataset,
    dataset_attr,
    ...
)
```

所以：

```text
load_dataset()
```

负责：

```text
把文件读进来
```

而：

```text
align_dataset()
```

负责：

```text
把不同数据格式统一起来
```

这是 LLaMA-Factory 很重要的一层。

---

## 4. 第二个重要部分：Template

现在数据已经统一成：

```text
User:
1+1等于多少？

Assistant:
2
```

但是不同大模型真正需要的输入格式不同。

**例如某个 Chat Model 可能要求：**

```text
<|im_start|>user
1+1等于多少？
<|im_end|>

<|im_start|>assistant
2
<|im_end|>
```

**这种格式，换个其他模型可能要求的格式又不一样。**

因此：

```text
统一消息格式
    ↓
Template
    ↓
具体模型的对话格式
```

所以 Template 本质也是一种：

> **模型输入适配器。**

它让上面的数据处理代码不用关心：

```text
Qwen怎么写
Llama怎么写
Gemma怎么写
```

---

## 5. 第三个重要部分：构造 input_ids 和 labels

这一步是真正和 SFT 原理接上的地方。

假设：

```text
User:
1+1等于多少？

Assistant:
2
```

经过 Template + Tokenizer 后，假设：

```python
source_ids = [
    10,
    11,
    12,
    13,
    14
]
```

代表：

```text
用户问题
```

而：

```python
target_ids = [
    20,
    21
]
```

代表：

```text
Assistant: 2
```

那么：

```python
input_ids = (
    source_ids
    +
    target_ids
)
```

得到：

```python
input_ids = [
    10, 11, 12, 13, 14,
    20, 21
]
```

---

## 6. labels 怎么处理？

普通 SFT 最关键的一步：

```python
source_label = [
    -100,
    -100,
    -100,
    -100,
    -100
]

target_label = [
    20,
    21
]
```

最后：

```python
labels = (
    source_label
    +
    target_label
)
```

得到：

```python
labels = [
    -100, -100, -100, -100, -100,
    20, 21
]
```

其中：

```text
-100
```

表示：

> 这个 Token 不参与 Cross Entropy Loss。

所以：

```text
用户问题
↓
参与 Forward
↓
但是不计算 Loss


Assistant 回答
↓
参与 Forward
↓
计算 Loss
```

LLaMA-Factory 当前的 `SupervisedDatasetProcessor` 基本就是这样做：

```python
if train_on_prompt:
    source_label = source_ids
else:
    source_label = [IGNORE_INDEX] * source_len

target_label = target_ids

input_ids += source_ids + target_ids
labels += source_label + target_label
```

所以这几行代码，其实就是：

> **SFT 最核心的数据构造过程。**

---

## 7. 处理完成以后是什么样？

最终 Dataset 中每条数据大致变成：

```python
{
    "input_ids": [
        10, 11, 12, 13, 14,
        20, 21
    ],

    "attention_mask": [
        1, 1, 1, 1, 1,
        1, 1
    ],

    "labels": [
        -100, -100, -100, -100, -100,
        20, 21
    ]
}
```

这时候已经完全可以交给 Transformer 训练了。

---

## 8. 第四个重要部分：加载模型

接下来：

```python
model = load_model(...)
```

可以简化理解成：

```python
from transformers import AutoModelForCausalLM


def load_model(model_name):

    model = (
        AutoModelForCausalLM
        .from_pretrained(model_name)
    )

    return model
```

所以：

```text
LLaMA-Factory
```

并没有自己重新写：

```text
Attention
RMSNorm
FFN
RoPE
```

这些还是：

```text
Transformers
```

里面的模型实现。

---

## 9. 那 adapter.py 是干什么的？

加载完模型以后，LLaMA-Factory 会调用：

```python
init_adapter(...)
```

这个名字容易让人误会：

> 是不是一定会给模型插一个 Adapter？

不是。

这里的 Adapter 更应该理解为：

> **“微调方式适配器”。**

它负责判断：

```text
你到底想怎么训练这个模型？
```

最核心的代码可以缩成：

```python
def init_adapter(
    model,
    finetuning_type
):

    if finetuning_type == "full":

        setup_full_tuning(model)

    elif finetuning_type == "freeze":

        setup_freeze_tuning(model)

    elif finetuning_type == "lora":

        setup_lora_tuning(model)

    return model
```

所以：

```text
                    init_adapter
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
        Full           Freeze          LoRA
```

我们这里只看：

```text
Full
```

---

## 10. Full SFT 的 Adapter 实现其实非常简单

当前源码中对应：

```python
_setup_full_tuning(...)
```

把工程细节去掉以后，可以理解成：

```python
def setup_full_tuning(model):

    for name, param in model.named_parameters():

        param.requires_grad = True
```

意思非常简单：

> **原模型所有参数都参与反向传播。**

例如：

```text
Embedding        ✓ 更新

Attention
├── W_Q          ✓ 更新
├── W_K          ✓ 更新
├── W_V          ✓ 更新
└── W_O          ✓ 更新

FFN
├── W_gate       ✓ 更新
├── W_up         ✓ 更新
└── W_down       ✓ 更新

RMSNorm          ✓ 更新

LM Head          ✓ 更新
```

这就是：

```text
Full Fine-tuning
```

---

## 11. LLaMA-Factory 真正源码稍微多做一点事情

真实代码大致是：

```python
def _setup_full_tuning(
    model,
    finetuning_args,
    is_trainable,
    cast_trainable_params_to_fp32,
):

    if not is_trainable:
        return

    forbidden_modules = (
        get_forbidden_modules(
            model.config,
            finetuning_args
        )
    )

    for name, param in (
        model.named_parameters()
    ):

        if not any(
            module in name
            for module
            in forbidden_modules
        ):

            if cast_trainable_params_to_fp32:

                param.data = (
                    param.data.to(
                        torch.float32
                    )
                )

        else:

            param.requires_grad_(False)
```

这段代码看起来复杂，

其实就两个意思。

---

## 12. 第一件事：大部分参数都训练

普通 Full SFT：

```text
Transformer 原来的参数
```

本来就是：

```python
requires_grad = True
```

所以甚至不用重新写：

```python
param.requires_grad = True
```

只要：

> **不要把它们 freeze 掉就可以。**

这也是为什么真正的 `_setup_full_tuning()` 看起来反而很短。

---

## 13. 第二件事：特殊模块可以冻结

例如某些多模态模型可能有：

```text
Vision Encoder
Projector
Language Model
```

如果配置要求某个部分不要训练：

```python
param.requires_grad_(False)
```

所以真实逻辑其实是：

```text
遍历模型全部参数

        ↓

这个模块允许 Full SFT？
       /       \
      是        否
      ↓         ↓
   保持训练     Freeze
```

---

## 14. 第三件事：必要时把训练参数转成 FP32

代码里面还有：

```python
param.data = param.data.to(
    torch.float32
)
```

这是工程实现中的稳定性处理。

所以可以把 Full Adapter 简化成：

```python
def setup_full_tuning(model):

    for name, param in model.named_parameters():

        if should_train(name):

            param.requires_grad = True

            param.data = (
                param.data.float()
            )

        else:

            param.requires_grad = False
```

这基本就是 Full Fine-tuning Adapter 的核心思想。

---

## 15. 为什么这也叫“Adapter”？

因为：

```text
模型本身
```

是不知道：

```text
我要 Full Fine-tuning

我要 Freeze Fine-tuning

我要 LoRA
```

这些事情的。

所以 LLaMA-Factory 在模型外面增加了一层：

```text
               Model
                 ↑
                 │
              Adapter
                 ↑
                 │
          Finetuning Config
```

配置说：

```text
full
```

Adapter 就把模型变成：

```text
全部参数可训练
```

配置说：

```text
freeze
```

Adapter 就把模型变成：

```text
只有部分参数可训练
```

这是一种非常典型的：

> **统一接口 + 不同实现**

的框架设计。

**也就是：不管是什么模型，只要做SFT，都是这么一套操作，LLaMAFactory主要是做通用适配。**

---

## 16. 最后：Trainer

现在我们已经有：

```text
Dataset
✓

input_ids
✓

labels
✓

Model
✓

所有参数可训练
✓
```

然后：

```python
trainer = CustomSeq2SeqTrainer(
    model=model,
    train_dataset=train_dataset,
    data_collator=data_collator
)
```

最后：

```python
trainer.train()
```

---

## 17. Trainer 底层还是最普通的 PyTorch

把 Hugging Face Trainer 的大量工程代码拿掉，

本质就是：

```python
for batch in dataloader:

    outputs = model(
        input_ids=batch["input_ids"],
        attention_mask=
            batch["attention_mask"],
        labels=batch["labels"]
    )

    loss = outputs.loss

    loss.backward()

    optimizer.step()

    optimizer.zero_grad()
```

所以模型：

```text
Forward
```

得到：

```text
Logits
```

根据：

```text
labels
```

计算：

```text
Cross Entropy Loss
```

然后：

```text
Loss
 ↓
Backward
 ↓
所有 Transformer 参数得到梯度
 ↓
Optimizer.step()
 ↓
更新整个模型
```

---

## 18. 用一条数据把整个过程串起来

原始数据：

```json
{
    "instruction": "1+1等于多少？",
    "output": "2"
}
```

---

### Step 1：数据 Adapter

转换为：

```text
User:
1+1等于多少？

Assistant:
2
```

---

### Step 2：Template

例如：

```text
<user>
1+1等于多少？
<assistant>
2
```

---

### Step 3：Tokenizer

得到：

```python
input_ids = [
    10, 11, 12, 13, 14,
    20, 21
]
```

---

### Step 4：构造 Labels

```python
labels = [
    -100, -100, -100, -100, -100,
    20, 21
]
```

---

### Step 5：加载模型

```python
model = (
    AutoModelForCausalLM
    .from_pretrained(...)
)
```

---

### Step 6：Full Adapter

```python
model = init_adapter(
    model,
    finetuning_type="full"
)
```

内部相当于：

```python
for param in model.parameters():

    param.requires_grad = True
```

---

### Step 7：Trainer

```python
trainer.train()
```

---

### Step 8：真正训练

```text
input_ids
   ↓
Transformer
   ↓
预测 Assistant 的 Token
   ↓
Cross Entropy Loss
   ↓
Backward
   ↓
整个 Transformer 更新
```

---

## 19. 一张图记住 LLaMA-Factory

```text
                原始数据
                    │
                    ▼
            ┌───────────────┐
            │ Data Adapter  │
            └───────────────┘
                    │
             统一消息格式
                    │
                    ▼
            ┌───────────────┐
            │   Template    │
            └───────────────┘
                    │
            模型对话格式
                    │
                    ▼
               Tokenizer
                    │
                    ▼
          input_ids / labels
                    │
                    ▼
             load_model()
                    │
                    ▼
        AutoModelForCausalLM
                    │
                    ▼
            init_adapter()
                    │
                    │ full
                    ▼
         _setup_full_tuning()
                    │
                    ▼
          全模型参数参与训练
                    │
                    ▼
                 Trainer
                    │
                    ▼
           Forward → Loss
                    │
                    ▼
                 Backward
                    │
                    ▼
           Optimizer.step()
                    │
                    ▼
             更新整个模型
```

---

## 20. 最后总结

如果只讲 LLaMA-Factory 最核心的三个地方，可以讲：

```text
① Data Adapter

各种数据
↓
统一数据格式
```

```text
② Model Adapter

Full / Freeze / LoRA
↓
统一成一个可训练 Model
```

```text
③ Trainer

Model + Dataset
↓
Forward
↓
Loss
↓
Backward
↓
Update
```

其中对于最普通的：

```text
Full SFT
```

**Model Adapter 根本没有什么复杂算法。**

核心甚至可以压缩成：

```python
def init_adapter(model, type):

    if type == "full":

        for param in model.parameters():

            param.requires_grad = True

    return model
```

然后训练依然是最普通的：

```python
outputs = model(
    input_ids=input_ids,
    labels=labels
)

loss = outputs.loss

loss.backward()

optimizer.step()
```

所以理解 LLaMA-Factory 的关键不是觉得它重新实现了大模型训练，而是：

> **它通过 Adapter、Template、Processor、Trainer 等模块，把不同的数据、不同的模型和不同的训练方式统一到了同一套训练流水线中。**

最核心的一句话：

$$
\boxed{
\text{LLaMA-Factory}
=
\text{把不同输入“适配”成统一训练流程}
}
$$
