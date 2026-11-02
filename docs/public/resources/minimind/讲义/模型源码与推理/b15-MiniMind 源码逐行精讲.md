# MiniMind 源码逐行精讲


>
> 对应源码：`a9075589-bab4-4214-8785-854c6b00eed6.py`
>
> 本讲义不按“从第 1 行机械念到最后一行”的方式讲，而是始终抓住一条主线：**一个 token 编号进入模型以后，到底依次经过谁、变成什么 shape、为什么要调用下一个函数，最后怎样变成 Loss 或下一个 token。** 在每个模块内部，再回到源码顺序逐行拆解。

---

<a id="origin-11"></a>
## 1. 在看任何一行代码以前：先把 839 行压缩成一张图

这份文件看起来有很多函数和类，但真正的数据主线只有一条：

```text
Token ID
   ↓
Embedding
   ↓
MiniMindBlock × N
   ├─ RMSNorm
   ├─ Attention
   │   ├─ Q/K/V Linear
   │   ├─ Q/K RMSNorm
   │   ├─ RoPE
   │   ├─ KV Cache
   │   ├─ GQA / repeat_kv
   │   ├─ QK^T / sqrt(D)
   │   ├─ Causal Mask
   │   ├─ Softmax
   │   └─ × V
   ├─ Residual
   ├─ RMSNorm
   ├─ FFN / MoE
   └─ Residual
   ↓
Final RMSNorm
   ↓
LM Head
   ↓
Vocabulary Logits
   ├─ 训练：Shift → Cross Entropy → Loss
   └─ 推理：Temperature/Top-k/Top-p → 选一个 token → 下一轮
```

<a id="origin-46"></a>
### 1.1 真正的“俄罗斯套娃”关系

```text
MiniMindForCausalLM               完整语言模型
│
├── MiniMindModel                Transformer 主干
│   │
│   ├── Embedding
│   ├── MiniMindBlock × N
│   │   ├── Attention
│   │   │   ├── RMSNorm(Q/K)
│   │   │   ├── RoPE
│   │   │   └── repeat_kv
│   │   ├── RMSNorm
│   │   └── FeedForward / MOEFeedForward
│   └── Final RMSNorm
│
├── lm_head                      H → V
├── forward()                    一次完整前向
└── generate()                   反复调用 forward() 逐 token 生成
```

所以以后看到一个陌生函数，不要马上把它当成一个新的大知识点。例如：

```text
precompute_freqs_cis
```

不要想成“文件里又出现一个新模型”，而应该定位成：

```text
Attention
└─ RoPE
   └─ 预先生成 cos/sin 表
```

看到：

```text
repeat_kv
```

应该想到：

```text
Attention
└─ GQA
   └─ 把较少的 KV Head 扩到 Query Head 数量
```

看到：

```text
generate
```

应该想到：

```text
generate 并不是另一套 Transformer
而是在循环调用同一个 forward
```

---

<a id="origin-111"></a>
## 2. 全程只追踪一个教学样本

为了让整个文件不散掉，我们规定一套很小的模型：

```python
cfg = MiniMindConfig(
    hidden_size=8,
    num_hidden_layers=2,
    num_attention_heads=2,
    num_key_value_heads=1,
    vocab_size=16,
    intermediate_size=12,
    max_position_embeddings=32,
)
```

记号：

```text
B   = batch size               = 1
T   = 本轮输入 token 数         = 3 或 4
S   = 历史缓存长度 + T
H   = hidden size              = 8
V   = vocabulary size          = 16
Nq  = Query Head 数            = 2
Nkv = Key/Value Head 数        = 1
D   = head_dim                 = 4
I   = FFN intermediate size    = 12
```

假设输入：

```python
input_ids = torch.tensor([[1, 5, 7]])
```

其 shape 是：

```text
[1, 3]
```

含义不是“一个三维向量”，而是：

```text
1 条序列
每条序列 3 个 token
token 编号分别为 1、5、7
```

进入 Embedding 后：

```text
[1,3]
   ↓
[1,3,8]
```

经过两个 Block，shape 仍然是：

```text
[1,3,8]
```

经过 `lm_head`：

```text
[1,3,8]
   ↓
[1,3,16]
```

意思是：

```text
3 个位置
每个位置
都对 16 个候选 token 打一个分数
```

这套数字会贯穿整份讲义。

---

<a id="origin-195"></a>
## 3. 阅读源码前必须掌握的三个层次

读这种文件时，每一行至少有三层含义。

<a id="origin-199"></a>
### 3.1 Python 层

例如：

```python
self.q_proj = nn.Linear(...)
```

先要知道：

- `self` 是什么；
- `.q_proj` 是实例属性；
- `=` 是把对象的引用赋给属性；
- `nn.Linear(...)` 是创建一个对象；
- `...` 里的参数何时求值。

<a id="origin-215"></a>
### 3.2 PyTorch 层

还要知道：

```python
nn.Linear(8, 8, bias=False)
```

会创建可训练参数：

```text
weight.shape = [8,8]
```

调用：

```python
y = layer(x)
```

才真正发生矩阵运算。

<a id="origin-237"></a>
### 3.3 Transformer 层

最后才是：

> 为什么这里需要一个 8→8 的 Linear？

因为我们的示例中：

```text
Nq = 2
D  = 4
Nq × D = 8
```

所以这是在给两个 Query Head 一次性产生 `2×4=8` 个 Q 特征。

**后面所有代码都按这三个层次讲。**

---

<a id="origin-257"></a>
## 4. `__init__` 和 `forward`：分清“造机器”和“开机器”

这是理解 PyTorch 源码最重要的前置知识。

看一个最小类：

```python
class TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(3, 2)

    def forward(self, x):
        return self.linear(x)
```

创建：

```python
model = TinyModel()
```

此时执行的是：

```text
__init__
```

它只是：

```text
创建 Linear
创建权重
把 Linear 挂到 self.linear
```

还没有任何输入经过模型。

直到：

```python
x = torch.randn(1, 3)
y = model(x)
```

PyTorch 的 `nn.Module.__call__` 才进一步调用：

```python
model.forward(x)
```

因此可以牢牢记：

```text
__init__ = 造机器
forward  = 开机器
```

MiniMind 全文件也是如此。

---

<a id="origin-319"></a>
## 5. 第一部分：文件开头与所有 import —— 每一个名字到底从哪里来

源码第 1～6 行首先给出了文件自己的阅读约定。这里最重要的是：

```text
B,T,S,H,V,Nq,Nkv,D,I,E,K
```

后面所有 shape 都会使用这些符号。

<a id="origin-329"></a>
### 5.1 `import math, torch, torch.nn.functional as F`

原代码：

```python
import math, torch, torch.nn.functional as F
```

这一行实际上等价于三行：

```python
import math
import torch
import torch.nn.functional as F
```

<a id="origin-345"></a>
#### 5.1.1 `math` 从哪里来

`math` 是 Python 标准库。

不需要：

```bash
pip install math
```

最小例子：

```python
import math

print(math.sqrt(16))
print(math.pi)
print(math.ceil(3.2))
print(math.floor(3.8))
print(math.log(10))
```

输出大致为：

```text
4.0
3.1415926...
4
3
2.302585...
```

本文件中的用途包括：

```python
math.pi
math.ceil(...)
math.log(...)
math.floor(...)
math.sqrt(self.head_dim)
```

特别是 Attention：

```python
scores = (Q @ K.transpose(-2, -1)) / math.sqrt(self.head_dim)
```

这里就是经典：

```math
QK^T / \sqrt{D}
```

<a id="origin-399"></a>
#### 5.1.2 `torch` 从哪里来

`torch` 是 PyTorch 顶层包，不是 Python 标准库。

概念上安装：

```bash
pip install torch
```

实际 GPU 环境通常需要选择与 CUDA 匹配的版本。

最小例子：

```python
import torch

x = torch.tensor([
    [1.0, 2.0],
    [3.0, 4.0],
])

print(x)
print(x.shape)
```

得到：

```text
tensor([[1., 2.],
        [3., 4.]])

torch.Size([2, 2])
```

为什么深度学习不用普通 Python `list` 就够了？

因为 Tensor 还提供：

```text
矩阵运算
GPU
自动求导
dtype
广播
高性能 kernel
```

最小自动求导例子：

```python
x = torch.tensor([2.0], requires_grad=True)
y = x ** 2
y.backward()
print(x.grad)
```

因为：

```math
y=x^2,
\qquad
\frac{dy}{dx}=2x
```

在 `x=2` 时：

```text
x.grad = 4
```

这就是 Transformer 参数最终能被反向传播更新的基础。

<a id="origin-472"></a>
#### 5.1.3 `torch.nn.functional as F`

完整名字：

```python
torch.nn.functional
```

作者把它起别名：

```python
F
```

所以：

```python
F.softmax(x, dim=-1)
```

本质就是：

```python
torch.nn.functional.softmax(x, dim=-1)
```

最小例子：

```python
import torch
import torch.nn.functional as F

x = torch.tensor([1.0, 2.0, 3.0])
p = F.softmax(x, dim=0)
print(p)
```

大约：

```text
tensor([0.0900, 0.2447, 0.6652])
```

本文件主要使用：

```text
F.softmax
F.scaled_dot_product_attention
F.cross_entropy
F.one_hot
```

<a id="origin-524"></a>
#### 5.1.4 为什么有 `nn.Softmax` 还需要 `F.softmax`

两种都能做 Softmax：

```python
softmax = nn.Softmax(dim=-1)
y = softmax(x)
```

或者：

```python
y = F.softmax(x, dim=-1)
```

对于没有可训练参数、只是一次函数计算的操作，源码里经常直接使用 `F.xxx`。

---

<a id="origin-543"></a>
### 5.2 `from torch import nn`

原代码：

```python
from torch import nn
```

意思是：

> 从 `torch` 包中把 `nn` 这个名字直接导入当前文件。

于是以后可以写：

```python
nn.Linear
```

而不必每次写：

```python
torch.nn.Linear
```

二者指向同一套模块。

<a id="origin-569"></a>
#### 5.2.1 `torch.nn` 可以理解成什么

可以把它看成 PyTorch 的“神经网络积木箱”：

```text
nn.Module
nn.Linear
nn.Embedding
nn.Dropout
nn.ModuleList
nn.Parameter
```

后面这个文件几乎所有可训练组件都来自这里。

<a id="origin-584"></a>
#### 5.2.2 最小 `nn.Linear` 例子

```python
from torch import nn
import torch

layer = nn.Linear(3, 2, bias=False)

x = torch.tensor([[1.0, 2.0, 3.0]])
y = layer(x)

print(x.shape)  # [1,3]
print(y.shape)  # [1,2]
```

数学上：

```math
y=xW^T+b
```

如果 `bias=False`：

```math
y=xW^T
```

假设：

```text
x = [1,2,3]

W =
[1,0,0]
[0,1,1]
```

则：

```text
y0 = 1×1 + 2×0 + 3×0 = 1
y1 = 1×0 + 2×1 + 3×1 = 5
```

所以：

```text
y=[1,5]
```

后面的 Q/K/V 投影本质全部是 Linear。

---

<a id="origin-638"></a>
### 5.3 `from transformers.activations import ACT2FN`

`transformers` 是 Hugging Face Transformers 第三方包。

概念安装：

```bash
pip install transformers
```

`activations` 是该包中的一个模块；`ACT2FN` 可以理解成：

```text
激活函数名字 → 真正可调用函数
```

例如概念上类似：

```python
{
    "relu": relu_function,
    "silu": silu_function,
    ...
}
```

本文件稍后会写：

```python
self.act_fn = ACT2FN[config.hidden_act]
```

如果：

```python
config.hidden_act == "silu"
```

那么运行时就取得 SiLU 对应的函数。

为什么配置里保存字符串，而不是直接保存 Python 函数？

因为配置经常需要保存成 JSON：

```json
{
  "hidden_act": "silu"
}
```

字符串很容易序列化；运行时再查表即可。

---

<a id="origin-692"></a>
### 5.4 `PreTrainedModel, GenerationMixin, PretrainedConfig`

原代码：

```python
from transformers import PreTrainedModel, GenerationMixin, PretrainedConfig
```

这三个更多属于“框架接口”，不是 Attention 数学本身。

<a id="origin-702"></a>
#### 5.4.1 `PretrainedConfig`

后面：

```python
class MiniMindConfig(PretrainedConfig):
```

说明 MiniMind 的配置类继承 Hugging Face 配置基类。

最小 Python 继承：

```python
class Animal:
    def speak(self):
        print("animal")

class Dog(Animal):
    pass

Dog().speak()
```

`Dog` 自己没写 `speak`，但继承了父类的能力。

<a id="origin-727"></a>
#### 5.4.2 `PreTrainedModel`

后面：

```python
class MiniMindForCausalLM(PreTrainedModel, GenerationMixin):
```

`PreTrainedModel` 帮模型接入 Transformers 的配置、权重初始化、保存/加载等基础框架。

<a id="origin-737"></a>
#### 5.4.3 `GenerationMixin`

它提供生成相关框架能力。不过本文件自己定义了一个 `generate()`，因此需要区分：

```text
Hugging Face 自带生成体系
≠
本文件下面自己实现的 generate 细节
```

---

<a id="origin-749"></a>
### 5.5 `MoeCausalLMOutputWithPast`

原代码：

```python
from transformers.modeling_outputs import MoeCausalLMOutputWithPast
```

拆名字：

```text
Moe
CausalLM
Output
WithPast
```

`CausalLM`：因果语言模型，即根据过去预测下一个 token。

`WithPast`：输出中可以携带历史缓存 `past_key_values`。

它的作用是让代码最后可以写：

```python
outputs = model(...)

outputs.loss
outputs.logits
outputs.past_key_values
```

而不是只能记：

```text
outputs[0] 是谁
outputs[1] 是谁
outputs[2] 是谁
```

---

<a id="origin-790"></a>
## 6. `MiniMindConfig`：模型真正创建之前，先写一张“建筑图纸”

源码位置：约 L20～L136。

<a id="origin-794"></a>
### 6.1 `class MiniMindConfig(PretrainedConfig):`

```python
class MiniMindConfig(PretrainedConfig):
```

Python：定义新类 `MiniMindConfig`，继承 `PretrainedConfig`。

Transformer：这个类不做 Attention，也没有模型权重；它只是保存：

```text
模型多宽
模型多深
多少头
词表多大
RoPE 多长
是否使用 MoE
……
```

可以把它理解为：

```text
Config = 建筑图纸
Model  = 真正盖出来的楼
```

---

<a id="origin-823"></a>
### 6.2 `model_type = "minimind"`

```python
model_type = "minimind"
```

这是类属性。

最小例子：

```python
class Student:
    school = "ZJU"

print(Student.school)
s = Student()
print(s.school)
```

`model_type` 主要给框架一个模型类型标识，本身不会创建模型，也不会自动完成所有 Auto 类注册。

---

<a id="origin-846"></a>
### 6.3 `def __init__(..., **kwargs)`

```python
def __init__(self, hidden_size=768, num_hidden_layers=8, use_moe=False, **kwargs):
```

这里同时出现：

```text
self
默认参数
布尔值
**kwargs
```

<a id="origin-861"></a>
#### 6.3.1 `self`

代表“当前这个实例”。

例如：

```python
cfg = MiniMindConfig()
```

执行 `__init__` 时，`self` 就指向这个刚创建的 `cfg` 对象。

<a id="origin-873"></a>
#### 6.3.2 默认参数

如果：

```python
MiniMindConfig()
```

就使用：

```text
hidden_size=768
num_hidden_layers=8
use_moe=False
```

如果：

```python
MiniMindConfig(hidden_size=8)
```

就覆盖默认 `768`。

<a id="origin-897"></a>
#### 6.3.3 `**kwargs`

最小例子：

```python
def show(**kwargs):
    print(kwargs)

show(a=1, b=2)
```

得到：

```python
{'a': 1, 'b': 2}
```

所以配置中大量其他选项都可以从 `kwargs` 中取。

---

<a id="origin-918"></a>
### 6.4 `super().__init__(**kwargs)`

```python
super().__init__(**kwargs)
```

`super()` 表示访问父类。

这里相当于：

> 先把额外配置交给 `PretrainedConfig` 的初始化逻辑处理，再设置 MiniMind 自己的字段。

最小例子：

```python
class A:
    def __init__(self):
        print("A init")

class B(A):
    def __init__(self):
        super().__init__()
        print("B init")

B()
```

输出：

```text
A init
B init
```

---

<a id="origin-954"></a>
### 6.5 三个最核心的字段

```python
self.hidden_size = hidden_size
self.num_hidden_layers = num_hidden_layers
self.use_moe = use_moe
```

<a id="origin-962"></a>
#### 6.5.1 `hidden_size`

我们教学例子设：

```text
H=8
```

表示一个 token 在 Block 之间传递时由 8 个数表示。

不是说 token 本身只有 8 种含义，而是模型当前使用一个 8 维连续向量承载它的表示。

<a id="origin-974"></a>
#### 6.5.2 `num_hidden_layers`

例如：

```text
2
```

就是后面创建：

```text
Block 0
Block 1
```

两个彼此独立参数的 Transformer Block。

<a id="origin-991"></a>
#### 6.5.3 `use_moe`

```text
False → 普通 FeedForward
True  → MOEFeedForward
```

第一次学主线时建议先保持 `False`。

---

<a id="origin-1002"></a>
### 6.6 `self.dropout = kwargs.get("dropout", 0.0)`

```python
self.dropout = kwargs.get("dropout", 0.0)
```

先讲 Python `dict.get`：

```python
d = {"name": "Tom"}

print(d.get("name", "Unknown"))  # Tom
print(d.get("age", 18))          # 18
```

所以：

```python
MiniMindConfig(dropout=0.1)
```

会得到：

```text
self.dropout = 0.1
```

未传则：

```text
0.0
```

Dropout 的具体层后面在 Attention、Embedding 中才真正创建和执行。

---

<a id="origin-1039"></a>
### 6.7 `vocab_size`

```python
self.vocab_size = kwargs.get("vocab_size", 6400)
```

`V` 表示词表大小。

教学例子：

```text
V=16
```

于是合法 token ID：

```text
0~15
```

Embedding 会建立：

```text
[16,8]
```

的表；LM Head 最后也会给：

```text
16 个候选 token
```

分别打分。

---

<a id="origin-1075"></a>
### 6.8 BOS / EOS

```python
self.bos_token_id = kwargs.get("bos_token_id", 1)
self.eos_token_id = kwargs.get("eos_token_id", 2)
```

`BOS`：Beginning Of Sequence。

`EOS`：End Of Sequence。

注意：这里只是**保存编号**。

它不会偷偷把 BOS 自动插入 `input_ids`，也不会因为看到 EOS 自动终止 `forward()`。

后面的自定义 `generate()` 才会显式检查 `eos_token_id`。

---

<a id="origin-1094"></a>
### 6.9 `flash_attn`

```python
self.flash_attn = kwargs.get("flash_attn", True)
```

这里只保存一个开关。

它并不意味着：

```text
True → 一定用了某个特定 FlashAttention kernel
```

后面 Attention 还会检查：

```python
hasattr(torch.nn.functional, 'scaled_dot_product_attention')
```

并受输入条件影响。

---

<a id="origin-1118"></a>
### 6.10 Query Head 与 KV Head

```python
self.num_attention_heads = kwargs.get("num_attention_heads", 8)
self.num_key_value_heads = kwargs.get("num_key_value_heads", 4)
```

教学例子：

```text
Nq  = 2
Nkv = 1
```

意思是：

```text
2 个 Query Head
共享 1 个 KV Head
```

因此这是 GQA。

对比：

```text
Nq=Nkv → 普通多头形式
Nkv=1  → 更接近 MQA
1<Nkv<Nq → GQA
```

---

<a id="origin-1151"></a>
### 6.11 `head_dim`

```python
self.head_dim = kwargs.get(
    "head_dim",
    self.hidden_size // self.num_attention_heads
)
```

`//` 是整数除法。

例子：

```python
8 // 2
```

得到：

```text
4
```

所以教学配置：

```text
H=8
Nq=2
D=4
```

要注意源码允许显式传 `head_dim`，所以并不是数学上强制要求：

```text
Nq×D = H
```

默认情况下是，但显式配置后可以不同，最后 `o_proj` 会再投影回 H。

---

<a id="origin-1192"></a>
### 6.12 激活函数

```python
self.hidden_act = kwargs.get("hidden_act", 'silu')
```

这里只保存字符串：

```text
"silu"
```

到 `FeedForward.__init__` 时才通过：

```python
ACT2FN[config.hidden_act]
```

找到真正函数。

SiLU：

```math
\mathrm{SiLU}(x)=x\sigma(x)
```

例如：

```text
x=2
sigmoid(2)≈0.8808
SiLU(2)≈1.7616
```

---

<a id="origin-1228"></a>
### 6.13 `intermediate_size`

```python
self.intermediate_size = kwargs.get(
    "intermediate_size",
    math.ceil(hidden_size * math.pi / 64) * 64
)
```

如果调用者明确：

```python
intermediate_size=12
```

教学模型就直接用 12。

如果不传，会执行默认公式。

逐步拆开：

假设：

```text
hidden_size=768
```

先：

```text
768 × π ≈ 2412.74
```

再：

```text
2412.74 / 64 ≈ 37.699
```

`ceil` 向上取整：

```text
38
```

再乘 64：

```text
2432
```

所以默认 FFN 中间宽度约为：

```text
I=2432
```

---

<a id="origin-1287"></a>
### 6.14 最大位置数与 RMSNorm eps

```python
self.max_position_embeddings = kwargs.get("max_position_embeddings", 32768)
self.rms_norm_eps = kwargs.get("rms_norm_eps", 1e-6)
```

`max_position_embeddings` 决定预先生成多少个 RoPE 位置。

教学设置：

```text
32
```

则预计算位置：

```text
0~31
```

`eps`：

```text
1e-6 = 0.000001
```

用于避免 RMSNorm 分母出现除零问题。

---

<a id="origin-1318"></a>
### 6.15 `rope_theta`

```python
self.rope_theta = kwargs.get("rope_theta", 1e6)
```

即：

```text
1,000,000
```

它控制 RoPE 不同维度的角频率分布。

注意这里是配置参数，真正的频率计算要到：

```python
precompute_freqs_cis(...)
```

才发生。

---

<a id="origin-1342"></a>
### 6.16 `tie_word_embeddings`

```python
self.tie_word_embeddings = kwargs.get("tie_word_embeddings", True)
```

如果开启，后面会让：

```text
输入 Embedding 权重
和
输出 LM Head 权重
```

引用同一个参数。

不是“初始化时复制一份相同数值”，而是后面真正指向同一个 `Parameter`。

---

<a id="origin-1362"></a>
### 6.17 RoPE scaling / YaRN 风格配置

```python
self.inference_rope_scaling = kwargs.get("inference_rope_scaling", False)
```

关闭时：

```python
self.rope_scaling = None
```

开启时构造字典：

```python
{
    "beta_fast": 32,
    "beta_slow": 1,
    "factor": 16,
    "original_max_position_embeddings": 2048,
    "attention_factor": 1.0,
    "type": "yarn"
}
```

第一次讲主线只需要知道：

> 普通 RoPE 的频率在长上下文扩展时可能需要调整，这个字典保存调整所需参数。

具体数学到 `precompute_freqs_cis` 再讲。

---

<a id="origin-1395"></a>
### 6.18 MoE 参数

```python
self.num_experts = kwargs.get("num_experts", 4)
self.num_experts_per_tok = kwargs.get("num_experts_per_tok", 1)
self.moe_intermediate_size = kwargs.get("moe_intermediate_size", self.intermediate_size)
self.norm_topk_prob = kwargs.get("norm_topk_prob", True)
self.router_aux_loss_coef = kwargs.get("router_aux_loss_coef", 5e-4)
```

先形成概念：

```text
E = 专家总数
K = 每个 token 实际选几个专家
```

例如：

```text
E=4
K=2
```

意思不是整批只运行两个专家，而是：

> 每一个 token 都独立选择自己的 Top-2 Expert。

`5e-4`：

```text
0.0005
```

用于 MoE 路由辅助损失系数。

---

<a id="origin-1433"></a>
## 7. 到这里到底发生了什么？Config 完成，但模型还没计算任何 token


执行：

```python
cfg = MiniMindConfig(
    hidden_size=8,
    num_hidden_layers=2,
    num_attention_heads=2,
    num_key_value_heads=1,
    vocab_size=16,
    intermediate_size=12,
    max_position_embeddings=32,
)
```

此时只得到类似：

```text
cfg.hidden_size = 8
cfg.num_hidden_layers = 2
cfg.num_attention_heads = 2
cfg.num_key_value_heads = 1
cfg.vocab_size = 16
...
```

还没有：

```text
Q 矩阵
K 矩阵
V 矩阵
Attention Score
Loss
```

甚至连 `nn.Linear` 权重都还没有由这个 Config 自己创建。

下一章开始才进入真正的网络组件。

---

<a id="origin-1478"></a>
## 8. `RMSNorm`：第一个真正会处理 Tensor 的网络组件

到这里，`MiniMindConfig` 只是在保存“图纸”。现在开始出现第一个真正的 `nn.Module`：

```python
class RMSNorm(torch.nn.Module):
```

先不要急着看公式。先回答四个问题：

```text
它是谁？       一个 PyTorch 网络模块
输入是什么？   Tensor，例如 [B,T,H]
输出是什么？   与输入 shape 完全相同的 Tensor
有没有参数？   有，一个可训练的 weight
改变什么？     改变数值尺度，不改变 token 数、hidden size 或维度数量
```

源码位置：约 L139～L178。

---

<a id="origin-1500"></a>
### 8.1 `class RMSNorm(torch.nn.Module)`：为什么必须继承 `Module`

原代码：

```python
class RMSNorm(torch.nn.Module):
```

前面我们已经：

```python
import torch
```

因此：

```python
torch.nn.Module
```

就是 PyTorch 所有神经网络层最常见的父类。

也可以写成：

```python
from torch import nn

class RMSNorm(nn.Module):
    ...
```

两种写法本质相同。

为什么不写普通 Python 类？

因为继承 `nn.Module` 后，PyTorch 才能自动管理：

```text
可训练参数 Parameter
子模块 Module
.to("cuda")
.train() / .eval()
.state_dict()
参数递归保存与加载
```

最小例子：

```python
import torch
from torch import nn

class MyLayer(nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = nn.Parameter(torch.tensor([2.0]))

    def forward(self, x):
        return x * self.weight

layer = MyLayer()
print(list(layer.parameters()))
```

PyTorch 会发现：

```text
weight 是需要训练的参数
```

如果只是普通属性：

```python
self.weight = torch.tensor([2.0])
```

它就不是自动注册的 `Parameter`。

---

<a id="origin-1580"></a>
### 8.2 `__init__(self, dim, eps)`：造一台 RMSNorm 机器

源码：

```python
def __init__(self, dim: int, eps: float = 1e-5):
    super().__init__()
    self.eps = eps
    self.weight = nn.Parameter(torch.ones(dim))
```

逐行拆。

<a id="origin-1593"></a>
#### 8.2.1 第 1 行：

```python
def __init__(self, dim: int, eps: float = 1e-5):
```

`dim: int` 是类型提示：

```text
dim 期望是整数
```

它不会自动强制检查。

例如：

```python
RMSNorm(dim=8)
```

表示最后一个特征维有 8 个数。

`eps: float = 1e-5`：

```text
默认 eps = 0.00001
```

为什么需要 eps？

RMSNorm 分母含：

```math
\sqrt{\mathrm{mean}(x^2)+\epsilon}
```

如果输入全为 0：

```text
x = [0,0,0,0]
```

那么：

```text
mean(x²) = 0
```

若没有 eps：

```text
1 / sqrt(0)
```

会出问题。

加一个极小正数就是为了数值稳定。

---

<a id="origin-1653"></a>
#### 8.2.2 第 2 行：

```python
super().__init__()
```

它调用父类 `nn.Module` 的初始化逻辑。

可以概括为：

> 我先把 PyTorch 的“模块管理系统”初始化好，随后才能安全注册参数和子模块。

如果一个 `nn.Module` 子类忘记正确调用父类初始化，后续：

```python
self.weight = nn.Parameter(...)
```

等模块注册逻辑就可能失败。

---

<a id="origin-1675"></a>
#### 8.2.3 第 3 行：

```python
self.eps = eps
```

这里没有创建 Tensor。

只是把传进来的普通 Python 浮点数保存到对象里。

例如：

```python
norm = RMSNorm(8, eps=1e-6)
```

之后：

```python
norm.eps
```

就是：

```text
0.000001
```

它不是需要训练的参数。

---

<a id="origin-1707"></a>
#### 8.2.4 第 4 行：

```python
self.weight = nn.Parameter(torch.ones(dim))
```

这一行要拆成三层。

第一层：

```python
torch.ones(dim)
```

例如：

```python
torch.ones(4)
```

得到：

```text
tensor([1., 1., 1., 1.])
```

shape：

```text
[4]
```

第二层：

```python
nn.Parameter(...)
```

告诉 PyTorch：

> 这不是普通 Tensor，这是一个需要优化器训练的模型参数。

第三层：

```python
self.weight = ...
```

把它注册到当前 RMSNorm 模块下。

于是：

```python
norm = RMSNorm(4)
```

初始：

```text
norm.weight = [1,1,1,1]
```

训练后可能变成：

```text
[0.91, 1.08, 0.73, 1.21]
```

这意味着：

> RMSNorm 不仅把整体尺度规范化，还允许每个 hidden dimension 再学习自己的缩放程度。

---

<a id="origin-1781"></a>
### 8.3 `norm(self, x)`：先只做“纯归一化”

源码：

```python
def norm(self, x):
    return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
```

这一行包含多个链式调用，可以逐步展开。

不要一口气读。

把：

```python
x.pow(2).mean(-1, keepdim=True)
```

拆成：

```python
x2 = x.pow(2)
mean_x2 = x2.mean(-1, keepdim=True)
```

再把完整代码改写为教学版：

```python
x2 = x.pow(2)
mean_x2 = x2.mean(dim=-1, keepdim=True)
denominator_inv = torch.rsqrt(mean_x2 + self.eps)
out = x * denominator_inv
return out
```

现在逐步看。

<a id="origin-1819"></a>
#### 8.3.1 `x.pow(2)`

逐元素平方。

若：

```text
x = [3,4]
```

得到：

```text
[9,16]
```

---

<a id="origin-1837"></a>
#### 8.3.2 `.mean(-1, keepdim=True)`

`-1` 表示最后一维。

如果：

```text
x.shape = [B,T,H]
```

那么：

```python
x.mean(-1)
```

就是沿 `H` 求平均。

这意味着：

> 每一个 token 独立归一化自己的 H 个特征。

例如：

```text
x.shape = [2,3,8]
```

共有：

```text
2 × 3 = 6 个 token 表示
```

每一个 token 都各自用自己的 8 个数求 RMS。

为什么 `keepdim=True`？

如果：

```text
x = [[3,4]]
shape = [1,2]
```

`mean(-1, keepdim=False)`：

```text
shape = [1]
```

`mean(-1, keepdim=True)`：

```text
shape = [1,1]
```

保留最后这个长度为 1 的维度，后面广播乘法会非常自然。

---

<a id="origin-1898"></a>
#### 8.3.3 `+ self.eps`

若：

```text
mean(x²)=12.5
```

则：

```text
12.5 + 0.00001
```

几乎不影响正常数值，但防止极端情况下分母为 0。

---

<a id="origin-1916"></a>
#### 8.3.4 `torch.rsqrt(...)`

`rsqrt` = reciprocal square root：

```math
\operatorname{rsqrt}(a)=\frac{1}{\sqrt{a}}
```

所以：

```python
torch.rsqrt(torch.tensor([4.0]))
```

结果：

```text
0.5
```

对于 `[3,4]`：

```text
mean(x²) = 12.5
sqrt(12.5) ≈ 3.5355
1 / 3.5355 ≈ 0.28284
```

于是：

```text
[3,4] × 0.28284
≈
[0.8485,1.1314]
```

---

<a id="origin-1954"></a>
### 8.4 为什么这个乘法能广播？

假设：

```text
x.shape = [1,3,4]
```

三个 token：

```text
Token 0: [a,b,c,d]
Token 1: [e,f,g,h]
Token 2: [i,j,k,l]
```

算完均方值并 `keepdim=True` 后：

```text
scale.shape = [1,3,1]
```

大概像：

```text
[[[s0],
  [s1],
  [s2]]]
```

与：

```text
[1,3,4]
```

相乘时，最后那个 `1` 自动广播成 `4`：

```text
Token 0 四个维度都乘 s0
Token 1 四个维度都乘 s1
Token 2 四个维度都乘 s2
```

这就是广播。

---

<a id="origin-2002"></a>
### 8.5 `forward(self, x)`：为什么先 `.float()` 再 `.type_as(x)`

源码：

```python
def forward(self, x):
    return (self.weight * self.norm(x.float())).type_as(x)
```

拆开：

```python
x_fp32 = x.float()
x_norm = self.norm(x_fp32)
x_scaled = self.weight * x_norm
out = x_scaled.type_as(x)
return out
```

<a id="origin-2021"></a>
#### 8.5.1 `x.float()`

无论输入原来是：

```text
FP16
BF16
```

这里先转成 FP32 做 RMS 相关计算。

原因：

```text
平方
求平均
开平方倒数
```

都属于比较容易受数值精度影响的操作。

因此常见做法是内部提高精度。

---

<a id="origin-2046"></a>
#### 8.5.2 `self.weight * x_norm`

若：

```text
x_norm.shape = [B,T,H]
weight.shape = [H]
```

PyTorch 会把 `[H]` 广播到所有 batch 和 token。

也就是：

```text
同一个第 0 hidden dimension
在所有 token 上都乘 weight[0]

同一个第 1 hidden dimension
在所有 token 上都乘 weight[1]
...
```

注意：

> 每个 token 的 RMS 尺度是自己计算的，但可学习的 `weight` 是整个模型共享的一组 H 维参数。

---

<a id="origin-2074"></a>
#### 8.5.3 `.type_as(x)`

意思是：

> 把结果转回与原输入 `x` 相同的数据类型。

例如：

```python
x.dtype == torch.float16
```

那么最终：

```text
out.dtype == torch.float16
```

这样后续 Transformer 的混合精度计算不会因为 RMSNorm 永久变成 FP32。

---

<a id="origin-2096"></a>
### 8.6 把 RMSNorm 完整跑一遍

```python
import torch
from torch import nn

class RMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-5):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def norm(self, x):
        return x * torch.rsqrt(
            x.pow(2).mean(-1, keepdim=True) + self.eps
        )

    def forward(self, x):
        return (
            self.weight * self.norm(x.float())
        ).type_as(x)

norm = RMSNorm(2)
x = torch.tensor([[3.0, 4.0]])
print(norm(x))
```

初始 `weight=[1,1]`，结果约：

```text
[[0.8485, 1.1314]]
```

如果人为改成：

```python
norm.weight.data = torch.tensor([2.0, 0.5])
```

则输出约：

```text
[[1.6970, 0.5657]]
```

---

<a id="origin-2143"></a>
### 8.7 RMSNorm 在整个文件里到底出现在哪里？

它不是只出现一次。

<a id="origin-2147"></a>
#### 8.7.1 第一类：Block 级归一化

`MiniMindBlock` 中：

```python
self.input_layernorm = RMSNorm(config.hidden_size, ...)
self.post_attention_layernorm = RMSNorm(config.hidden_size, ...)
```

shape：

```text
[B,T,H] → [B,T,H]
```

<a id="origin-2162"></a>
#### 8.7.2 第二类：Attention 内部 Q/K 归一化

```python
self.q_norm = RMSNorm(self.head_dim, ...)
self.k_norm = RMSNorm(self.head_dim, ...)
```

shape：

```text
Q: [B,T,Nq,D] → [B,T,Nq,D]
K: [B,T,Nkv,D] → [B,T,Nkv,D]
```

此时 RMSNorm 只看最后的：

```text
D
```

也就是每个 Attention Head 内部独立归一化。

<a id="origin-2184"></a>
#### 8.7.3 第三类：主模型最后一次归一化

```python
self.norm = RMSNorm(config.hidden_size, ...)
```

在全部 Block 结束后再做一次。

---

<a id="origin-2194"></a>
### 8.8 如果删掉 RMSNorm 会怎样？

从 Python 语法上，当然可以重新设计一个没有 Norm 的模型。

但在这份模型设计里，它承担的是：

```text
控制中间激活的数值尺度
↓
降低深层堆叠时数值越来越大/越来越小的风险
↓
让 Attention 和 FFN 更容易稳定训练
```

所以不能简单把：

```python
self.input_layernorm(hidden_states)
```

删掉，同时还声称“模型结构没有变化”。

那已经是在改网络架构。

---

<a id="origin-2220"></a>
## 9. `precompute_freqs_cis()`：RoPE 还没旋转 Q/K，先把整张 cos/sin 表算出来

接下来出现的是一个普通 Python 函数：

```python
def precompute_freqs_cis(...):
```

它不是 `nn.Module`。

为什么？

因为它没有需要训练的参数，也不是一个网络层。

它主要做一件事：

> 给位置 `0,1,2,...` 提前计算 RoPE 会用到的 cos/sin 数值表。

先看输入输出：

```text
输入：
D = head_dim
end = 最大位置数
rope_base = 频率基数
rope_scaling = 可选长上下文缩放配置

输出：
freqs_cos: [end,D]
freqs_sin: [end,D]
```

例如：

```python
cos, sin = precompute_freqs_cis(
    dim=4,
    end=3,
    rope_base=10000
)
```

会为位置：

```text
0,1,2
```

各准备 4 个 cos 和 4 个 sin 值。

---

<a id="origin-2272"></a>
### 9.1 函数签名逐项解释

源码：

```python
def precompute_freqs_cis(
    dim: int,
    end: int = int(32 * 1024),
    rope_base: float = 1e6,
    rope_scaling: dict = None
):
```

<a id="origin-2285"></a>
#### 9.1.1 `dim: int`

就是单个 Attention Head 的维度：

```text
D
```

这份实现要求 D 最好是偶数，因为后面需要成对旋转。

<a id="origin-2295"></a>
#### 9.1.2 `end = int(32 * 1024)`

先算：

```text
32 × 1024 = 32768
```

所以默认提前算 32768 个位置。

32K是minimind实现选择的默认最大上下文规模，是模型能力、显存占用和实际使用场景之间的工程折中。

`int(...)` 在这里结果本来就是整数，主要是把类型意图写清楚。

<a id="origin-2309"></a>
#### 9.1.3 `rope_base: float = 1e6`

`1e6`：

```text
1 × 10^6 = 1,000,000
```

它控制不同维度对应的旋转频率分布。

<a id="origin-2319"></a>
#### 9.1.4 `rope_scaling: dict = None`

默认：

```text
None
```

表示不做额外长上下文频率缩放。

如果给字典，则后面读取：

```text
factor
beta_fast
beta_slow
original_max_position_embeddings
attention_factor
```

---

<a id="origin-2341"></a>
### 9.2 第一条真正计算频率的代码

源码：

```python
freqs, attn_factor = (
    1.0 / (
        rope_base ** (
            torch.arange(0, dim, 2)[: (dim // 2)].float() / dim
        )
    ),
    1.0
)
```

原文件中的这一行可以拆开分析。

```python
indices = torch.arange(0, dim, 2)
indices = indices[: dim // 2]
indices = indices.float()
exponent = indices / dim
powers = rope_base ** exponent
freqs = 1.0 / powers
attn_factor = 1.0
```

---

<a id="origin-2370"></a>
#### 9.2.1 `torch.arange(0, dim, 2)`

类似 Python：

```python
range(0, dim, 2)
```

但是返回 Tensor。

例如：

```python
torch.arange(0, 8, 2)
```

得到：

```text
[0,2,4,6]
```

为什么步长是 2？

因为 RoPE 把特征两两配对做二维旋转。

如果：

```text
D=8
```

一共有：

```text
D/2 = 4 组旋转频率
```

---

<a id="origin-2410"></a>
#### 9.2.2 `[: (dim // 2)]`

`//` 是整数除法。

例如：

```text
8 // 2 = 4
```

所以只保留前 `D/2` 个频率索引。

对于正常偶数 D，`arange(0,D,2)` 本身已经正好产生 D/2 个元素，这个切片更多是把预期边界写明确。

---

<a id="origin-2426"></a>
#### 9.2.3 `.float()`

把整数索引转换成浮点数。

因为下面要做：

```python
indices / dim
```

并参与指数运算。

---

<a id="origin-2440"></a>
### 9.3 用 `D=4, base=10000` 手算

```text
indices = [0,2]
```

除以 D=4：

```text
[0/4, 2/4]
=
[0,0.5]
```

于是：

```text
base ** exponent
=
[10000^0, 10000^0.5]
=
[1,100]
```

取倒数：

```text
freqs = [1,0.01]
```

含义：

```text
第 1 对特征旋转得很快
第 2 对特征旋转得很慢
```

因此 RoPE 不是所有 hidden dimension 都用同一个角速度。

---

<a id="origin-2481"></a>
### 9.4 `if rope_scaling is not None`

源码：

```python
if rope_scaling is not None:
```

Python 里的 `is not None` 是判断对象是不是 `None`。

不要简单写成：

```python
if rope_scaling:
```

两者意义并不完全相同。

例如空字典：

```python
{}
```

是 Falsey，但它并不是 `None`。

这里源码明确判断：

> 调用者到底有没有传缩放配置对象。

---

<a id="origin-2513"></a>
### 9.5 一次取出五个 YaRN 风格参数

源码：

```python
orig_max, factor, beta_fast, beta_slow, attn_factor = (
    rope_scaling.get("original_max_position_embeddings", 2048),
    rope_scaling.get("factor", 16),
    rope_scaling.get("beta_fast", 32.0),
    rope_scaling.get("beta_slow", 1.0),
    rope_scaling.get("attention_factor", 1.0)
)
```

这是 Python 的：

```text
tuple unpacking
元组解包
```

例如：

```python
a, b = (10, 20)
```

得到：

```text
a=10
b=20
```

这里右侧依次算出五个值，再按顺序给五个变量。

`dict.get()` 前面已经讲过：

```python
d.get("key", 默认值)
```

如果 key 存在就用配置值，不存在就用默认值。

---

<a id="origin-2559"></a>
### 9.6 `if end / orig_max > 1.0`

源码：

```python
if end / orig_max > 1.0:
```

例如：

```text
end = 32768
orig_max = 2048
```

则：

```text
32768 / 2048 = 16
```

大于 1，说明：

> 当前预计算的位置范围超过了原始上下文窗口，需要进入缩放逻辑。

如果：

```text
end = 1024
orig_max = 2048
```

则：

```text
0.5
```

不进入缩放。

注意源码这里判断的是：

```text
预计算表长 end
```

而不是这一次 forward 实际输入了多少 token。

---

<a id="origin-2609"></a>
### 9.7 `lambda b: ...` 是什么？

源码：

```python
inv_dim = lambda b: (
    dim * math.log(orig_max / (b * 2 * math.pi))
) / (
    2 * math.log(rope_base)
)
```

`lambda` 是 Python 的匿名函数。

最简单：

```python
square = lambda x: x * x
print(square(3))
```

输出：

```text
9
```

等价于：

```python
def square(x):
    return x * x
```

所以这里也可以改写成：

```python
def inv_dim(b):
    return (
        dim * math.log(orig_max / (b * 2 * math.pi))
    ) / (
        2 * math.log(rope_base)
    )
```

这里的目标是：

> 根据“在原始上下文中大约转 b 圈”的条件，反推出频率索引边界。

这段 YaRN 代码计算的是：哪些频率维度该保留、哪些该缩慢、哪些处于过渡带。

---

<a id="origin-2662"></a>
### 9.8 `math.log`、`math.pi`、`floor`、`ceil`

源码：

```python
low = max(math.floor(inv_dim(beta_fast)), 0)
high = min(math.ceil(inv_dim(beta_slow)), dim // 2 - 1)
```

<a id="origin-2671"></a>
#### 9.8.1 `math.log(x)`

自然对数：

```math
\ln x
```

<a id="origin-2679"></a>
#### 9.8.2 `math.pi`

圆周率：

```text
3.1415926...
```

<a id="origin-2687"></a>
#### 9.8.3 `math.floor(x)`

向下取整：

```text
floor(2.9) = 2
```

<a id="origin-2695"></a>
#### 9.8.4 `math.ceil(x)`

向上取整：

```text
ceil(2.1) = 3
```

<a id="origin-2703"></a>
#### 9.8.5 `max(...,0)`

保证 `low` 不小于 0。

<a id="origin-2707"></a>
#### 9.8.6 `min(..., dim//2-1)`

保证 `high` 不超出频率索引范围。

---

<a id="origin-2713"></a>
### 9.9 构造 `ramp`

源码：

```python
ramp = torch.clamp(
    (
        torch.arange(dim // 2, device=freqs.device).float() - low
    ) / max(high - low, 0.001),
    0,
    1
)
```

拆开：

```python
idx = torch.arange(dim // 2, device=freqs.device).float()
num = idx - low
den = max(high - low, 0.001)
ramp = num / den
ramp = torch.clamp(ramp, 0, 1)
```

<a id="origin-2737"></a>
#### 9.9.1 `device=freqs.device`

这是很重要的工程细节。

如果 `freqs` 在 GPU：

```text
cuda:0
```

那么新创建的 `idx` 也直接放 GPU。

否则 CPU Tensor 和 GPU Tensor 直接计算会报 device mismatch。

<a id="origin-2751"></a>
#### 9.9.2 `torch.clamp(x,0,1)`

把小于 0 的变成 0，大于 1 的变成 1。

例如：

```text
[-0.5, 0.2, 0.8, 1.7]
```

变成：

```text
[0,0.2,0.8,1]
```

所以 `ramp` 就形成一个：

```text
0 → 过渡值 → 1
```

的平滑带。

---

<a id="origin-2777"></a>
### 9.10 真正修改频率

源码：

```python
freqs = freqs * (1 - ramp + ramp / factor)
```

看三个极端情况。

<a id="origin-2787"></a>
#### 9.10.1 `ramp=0`

```text
1 - 0 + 0/factor = 1
```

所以：

```text
freq 不变
```

<a id="origin-2799"></a>
#### 9.10.2 `ramp=1`

```text
1 - 1 + 1/factor
=
1/factor
```

所以：

```text
freq → freq/factor
```

例如 factor=16：

```text
0.01 → 0.000625
```

<a id="origin-2819"></a>
#### 9.10.3 `ramp=0.5`

```text
1 - 0.5 + 0.5/16
=
0.53125
```

所以处于过渡区，不是突然切换。

---

<a id="origin-2831"></a>
### 9.11 创建位置编号 `t`

源码：

```python
t = torch.arange(end, device=freqs.device)
```

如果：

```text
end=3
```

得到：

```text
[0,1,2]
```

它就是绝对位置编号。

---

<a id="origin-2855"></a>
### 9.12 `torch.outer(t, freqs)`：一次生成所有“位置 × 频率”的角度

源码：

```python
freqs = torch.outer(t, freqs).float()
```

这里注意：

> 变量名 `freqs` 被复用了。

在这一行之前：

```text
freqs = [D/2] 的角频率
```

这一行之后：

```text
freqs = [end,D/2] 的角度表
```

`torch.outer(a,b)` 是外积。

若：

```text
t = [0,1,2]
freq = [1,0.01]
```

得到：

```text
[
 [0×1, 0×0.01],
 [1×1, 1×0.01],
 [2×1, 2×0.01]
]
```

即：

```text
[
 [0,0],
 [1,0.01],
 [2,0.02]
]
```

shape：

```text
[3,2]
```

---

<a id="origin-2916"></a>
### 9.13 为什么 cos/sin 要 `cat` 两遍？

源码：

```python
freqs_cos = torch.cat(
    [torch.cos(freqs), torch.cos(freqs)],
    dim=-1
) * attn_factor

freqs_sin = torch.cat(
    [torch.sin(freqs), torch.sin(freqs)],
    dim=-1
) * attn_factor
```

如果：

```text
freqs.shape = [end,D/2]
```

`cos(freqs)` 还是：

```text
[end,D/2]
```

沿最后一维拼两份：

```text
[end,D]
```

例如 D=4：

```text
原始两个角： [θ0, θ1]

cos 后：      [cosθ0, cosθ1]
复制拼接：    [cosθ0, cosθ1, cosθ0, cosθ1]
```

为什么顺序是这样？

因为本文件后面的 `rotate_half()` 配对方式是：

```text
前半维度
和
后半维度
```

例如：

```text
[x0,x1,x2,x3]
```

配对：

```text
(x0,x2)
(x1,x3)
```

因此：

```text
维 0 和维 2 用 θ0
维 1 和维 3 用 θ1
```

恰好需要：

```text
[θ0,θ1,θ0,θ1]
```

---

<a id="origin-2997"></a>
### 9.14 `return freqs_cos, freqs_sin`

源码：

```python
return freqs_cos, freqs_sin
```

Python 实际返回一个 tuple：

```text
(cos_tensor, sin_tensor)
```

所以外面可以：

```python
freqs_cos, freqs_sin = precompute_freqs_cis(...)
```

一次接收两个 Tensor。

---

<a id="origin-3021"></a>
### 9.15 一个最小完整例子

```python
cos, sin = precompute_freqs_cis(
    dim=4,
    end=3,
    rope_base=10000,
    rope_scaling=None
)

print(cos.shape)
print(sin.shape)
```

得到：

```text
[3,4]
[3,4]
```

第 0 个位置：

```text
角度都是 0
cos=1
sin=0
```

所以第 0 个位置不会发生旋转。

---

<a id="origin-3054"></a>
### 9.16 这张表什么时候创建？

不是每次 Attention 都重新计算。

后面 `MiniMindModel.__init__()` 会：

```python
freqs_cos, freqs_sin = precompute_freqs_cis(...)
```

然后：

```python
self.register_buffer("freqs_cos", ...)
self.register_buffer("freqs_sin", ...)
```

于是整台模型共享一张预计算位置表。

每次 forward 只切自己需要的：

```python
self.freqs_cos[start_pos:start_pos + seq_length]
```

这就是“precompute”的意义：

> 三角函数提前算一次，运行时按位置查表。

---

<a id="origin-3085"></a>
## 10. `apply_rotary_pos_emb()`：真正把 RoPE 旋转施加到 Q 和 K

前一章只是造了两张表：

```text
cos[position, dimension]
sin[position, dimension]
```

还没有真正改变 Q、K。

现在才进入：

```python
def apply_rotary_pos_emb(q, k, cos, sin, unsqueeze_dim=1):
```

输入：

```text
q:   [B,T,Nq,D]
k:   [B,T,Nkv,D]
cos: [T,D]
sin: [T,D]
```

输出：

```text
q_embed: 与 q 同 shape
k_embed: 与 k 同 shape
```

Value 不进入这个函数。

---

<a id="origin-3122"></a>
### 10.1 为什么只旋转 Q 和 K，不旋转 V？

在 Attention 中：

```math
\text{score}_{ij}=Q_iK_j^T
```

位置关系主要通过 Q/K 点积影响“我应该关注谁”。

而 V 是：

> 被选中以后真正汇总的内容。

所以本实现只给 Q/K 加 RoPE。

---

<a id="origin-3140"></a>
### 10.2 内部函数 `rotate_half`

源码：

```python
def rotate_half(x):
    return torch.cat(
        (
            -x[..., x.shape[-1] // 2:],
            x[..., : x.shape[-1] // 2]
        ),
        dim=-1
    )
```

原源码压成一行，教学必须拆开。

假设：

```text
x = [1,2,3,4]
```

`x.shape[-1]`：

```text
4
```

`4 // 2`：

```text
2
```

第一片：

```python
x[..., 2:]
```

得到：

```text
[3,4]
```

前面负号：

```text
[-3,-4]
```

第二片：

```python
x[..., :2]
```

得到：

```text
[1,2]
```

`torch.cat(..., dim=-1)`：

```text
[-3,-4,1,2]
```

也就是：

```text
[x0,x1,x2,x3]
      ↓
[-x2,-x3,x0,x1]
```

这恰好构成二维旋转公式中的“与 sin 相乘的那一部分”。

---

<a id="origin-3223"></a>
### 10.3 `...` 到底是什么？

这个符号表示省略前面的维度。

```python
x[..., 2:]
```

`...` 是 Ellipsis。

意思：

> 前面有多少维我都不管，全部保留，只对最后一维切片。

例如：

```text
x.shape = [2,3,4,8]
```

```python
x[..., 4:]
```

等价于：

```python
x[:, :, :, 4:]
```

这样函数不需要提前知道 x 是二维、三维还是四维。

---

<a id="origin-3257"></a>
### 10.4 第一条旋转公式

源码：

```python
q_embed = (
    (q * cos.unsqueeze(unsqueeze_dim))
    +
    (rotate_half(q) * sin.unsqueeze(unsqueeze_dim))
).to(q.dtype)
```

数学形式：

```math
q' = q\cos\theta + \operatorname{rotate\_half}(q)\sin\theta
```

如果只看一组二维坐标：

```text
(x,y)
```

标准旋转是：

```text
x' = x cosθ - y sinθ
y' = x sinθ + y cosθ
```

本实现只是把很多二维配对一次并行完成。

---

<a id="origin-3292"></a>
### 10.5 为什么 `cos.unsqueeze(1)`？

默认：

```python
unsqueeze_dim=1
```

所以：

```python
cos.unsqueeze(1)
```

假设：

```text
cos.shape = [T,D]
```

插入一个维度后：

```text
[T,1,D]
```

而 q：

```text
[B,T,Nq,D]
```

在广播语义下，相当于把 cos 看成：

```text
[1,T,1,D]
```

于是：

```text
同一个位置 t 的 cos/sin
广播给：
- 所有 batch
- 所有 head
```

但是不同 token 位置使用不同的 cos/sin。

---

<a id="origin-3343"></a>
### 10.6 用一个极端角度手算

假设：

```text
q = [1,2,3,4]
```

为了方便，假设两组角都是：

```text
θ = π/2
```

所以：

```text
cos = [0,0,0,0]
sin = [1,1,1,1]
```

前面算过：

```text
rotate_half(q)
=
[-3,-4,1,2]
```

于是：

```text
q*cos = [0,0,0,0]
```

```text
rotate_half(q)*sin
=
[-3,-4,1,2]
```

相加：

```text
q'=[-3,-4,1,2]
```

这就是一次 90° 旋转。

---

<a id="origin-3394"></a>
### 10.7 Key 完全相同

源码：

```python
k_embed = (
    (k * cos.unsqueeze(unsqueeze_dim))
    +
    (rotate_half(k) * sin.unsqueeze(unsqueeze_dim))
).to(k.dtype)
```

只是把 q 换成 k。

注意 Q 和 K 的 head 数可以不同：

```text
Q: Nq
K: Nkv
```

因为 cos/sin 在 head 维本来就是 1，能够广播到任意 head 数。

---

<a id="origin-3419"></a>
### 10.8 `.to(q.dtype)` 与 `.type_as(x)` 的关系

这里：

```python
.to(q.dtype)
```

意思是只指定数据类型转换为 q 的 dtype。

前面 RMSNorm：

```python
.type_as(x)
```

也是恢复成和 x 同类型。

在这段代码里，两者目的类似：

> 防止中间运算因为 cos/sin 的 dtype 让最终 Q/K 类型发生意外变化。

---

<a id="origin-3443"></a>
### 10.9 `return q_embed, k_embed`

外面调用：

```python
xq, xk = apply_rotary_pos_emb(xq, xk, cos, sin)
```

于是原来的：

```text
xq
xk
```

被替换成：

```text
带位置旋转后的 xq
带位置旋转后的 xk
```

shape 一点不变。

---

<a id="origin-3469"></a>
## 11. `repeat_kv()`：GQA 为什么能让多个 Query Head 共用一组 K/V

源码：

```python
def repeat_kv(x: torch.Tensor, n_rep: int) -> torch.Tensor:
    bs, slen, num_key_value_heads, head_dim = x.shape
    if n_rep == 1:
        return x
    return (
        x[:, :, :, None, :]
        .expand(bs, slen, num_key_value_heads, n_rep, head_dim)
        .reshape(bs, slen, num_key_value_heads * n_rep, head_dim)
    )
```

这个函数非常短，但里面包含：

```text
type hint
shape 解包
早返回
None 插轴
expand
reshape
GQA 的实际 head 对齐
```

非常值得逐行讲。

---

<a id="origin-3501"></a>
### 11.1 函数签名里的类型提示

```python
x: torch.Tensor
```

表示期望 x 是 Tensor。

```python
n_rep: int
```

期望是整数。

```python
-> torch.Tensor
```

表示预期返回 Tensor。

这些是类型注解，不是运行时的强制类型转换。

---

<a id="origin-3525"></a>
### 11.2 `bs, slen, num_key_value_heads, head_dim = x.shape`

假设：

```text
x.shape = [2,3,4,8]
```

那么 Python 解包：

```text
bs = 2
slen = 3
num_key_value_heads = 4
head_dim = 8
```

这里要求 x 恰好是四维。

在本文件中，repeat 之前 K/V 的布局是：

```text
[B,S,Nkv,D]
```

所以四个变量分别就是：

```text
B
S
Nkv
D
```

---

<a id="origin-3561"></a>
### 11.3 `if n_rep == 1: return x`

这是典型的“early return”。

如果 Query Head 数和 KV Head 数一样：

```text
Nq = Nkv
```

那么：

```text
n_rep = Nq // Nkv = 1
```

根本不需要复制。

直接返回原 x。

这样既更快，也避免无意义 reshape。

---

<a id="origin-3585"></a>
### 11.4 `x[:, :, :, None, :]`：第一次看到 None 插轴

假设：

```text
x.shape = [1,3,2,4]
```

其中：

```text
1 个 batch
3 个 token
2 个 KV head
每头 4 维
```

现在：

```python
x[:, :, :, None, :]
```

在第 4 个位置插一个新轴：

```text
[1,3,2,1,4]
```

这里的 `None` 可以理解为：

```python
torch.unsqueeze(x, dim=3)
```

类似效果。

为什么要插这一维？

因为接下来要在这个新维度上“把每个 KV Head 复制 n_rep 份”。

---

<a id="origin-3628"></a>
### 11.5 `.expand(...)`：广播视图，不是简单 `repeat`

```python
.expand(
    bs,
    slen,
    num_key_value_heads,
    n_rep,
    head_dim
)
```

如果：

```text
原 shape = [1,3,2,1,4]
n_rep = 2
```

expand 后：

```text
[1,3,2,2,4]
```

概念上：

```text
KV head A → A,A
KV head B → B,B
```

`expand` 常常利用 stride/broadcast 创建视图，不一定立即真的复制所有数据。

这一点和：

```python
repeat(...)
```

不同，`repeat` 通常真正重复数据。

不过后面再 `reshape`，根据内存布局可能产生实际拷贝。

---

<a id="origin-3674"></a>
### 11.6 `.reshape(...)`：把“KV Head × 复制槽位”合并

当前：

```text
[B,S,Nkv,n_rep,D]
```

reshape 为：

```text
[B,S,Nkv*n_rep,D]
```

例如：

```text
[B,S,2,2,D]
```

变：

```text
[B,S,4,D]
```

head 顺序是：

```text
[A,A,B,B]
```

而不是：

```text
[A,B,A,B]
```

这点特别重要，因为 Query Heads 也按组对应它们。

---

<a id="origin-3716"></a>
### 11.7 用 GQA 的真实数字串起来

假设：

```text
Nq = 8
Nkv = 4
```

那么：

```python
n_rep = Nq // Nkv
```

得到：

```text
2
```

原始 K：

```text
K0 K1 K2 K3
```

repeat 后：

```text
K0 K0 K1 K1 K2 K2 K3 K3
```

对应 Query：

```text
Q0 Q1 Q2 Q3 Q4 Q5 Q6 Q7
```

配对：

```text
Q0,Q1 共用 K0/V0
Q2,Q3 共用 K1/V1
Q4,Q5 共用 K2/V2
Q6,Q7 共用 K3/V3
```

这就是 Grouped Query Attention 的“组”。

---

<a id="origin-3768"></a>
### 11.8 训练时 repeat 会不会让共享的 K/V 无法反向传播？

不会。

虽然前向看起来：

```text
K0 → K0,K0
```

但它们都来自同一个原始 K0。

反向传播时：

```text
来自 Q0 路径的梯度
+
来自 Q1 路径的梯度
```

都会累积回原来的 K0 计算路径。

所以：

> “共享 K/V”不是停止训练，而是多个 Query Head 对同一份 K/V 参数产生共同梯度贡献。

---

<a id="origin-3796"></a>
## 12. 到这里先停一下：四个“小零件”已经准备好

现在我们已经认识了：

```text
RMSNorm
    控制最后一维的数值尺度

precompute_freqs_cis
    提前生成 RoPE cos/sin 表

apply_rotary_pos_emb
    真正把 RoPE 加到 Q/K

repeat_kv
    把少量 KV Head 展开到 Query Head 数
```

`Attention` 中会用到以下组件：

```python
self.q_norm(...)
apply_rotary_pos_emb(...)
repeat_kv(...)
```

就不会再觉得这是三个突然出现的新黑盒。

下一章开始，我们把这些零件真正装进一台 Attention 机器。

<a id="origin-3826"></a>
## 13. `Attention`：把 Q/K/V、RoPE、GQA、Mask、Softmax、KV Cache 全部拼起来

现在终于进入整个文件最核心的模块之一：

```python
class Attention(nn.Module):
```

先不要看细节，先把它的“任务合同”写清楚。

输入：

```text
x: [B,T,H]
```

输出：

```text
output: [B,T,H]
past_kv: 可选的 (K,V)
```

也就是说：

> Attention 可以把每个 token 当前的 H 维表示，变成“已经从可见上下文读取信息之后”的 H 维表示。

内部会经历：

```text
[B,T,H]
   │
   ├─ q_proj → [B,T,Nq*D] → [B,T,Nq,D]
   ├─ k_proj → [B,T,Nkv*D] → [B,T,Nkv,D]
   └─ v_proj → [B,T,Nkv*D] → [B,T,Nkv,D]

Q/K → RMSNorm
Q/K → RoPE
K/V → 与历史 cache 拼接
K/V → repeat_kv
Q/K/V → transpose
QK^T / sqrt(D)
→ causal mask / padding mask
→ softmax
→ @ V
→ 多头合并
→ o_proj
→ [B,T,H]
```

这一章一定要把“创建机器”和“运行机器”分开讲：

```text
Attention.__init__   = 把所有子层装好
Attention.forward    = 真正让 x 流过这些子层
```

---

<a id="origin-3885"></a>
### 13.1 `class Attention(nn.Module)`

这和前面的 RMSNorm 一样，表示 Attention 是一个 PyTorch 模块。

它里面还会包含很多子模块：

```text
q_proj
k_proj
v_proj
o_proj
q_norm
k_norm
attn_dropout
resid_dropout
```

只要这些东西赋给：

```python
self.xxx
```

而且本身是 `nn.Module`，PyTorch 就会把它们注册成当前 Attention 的子模块。

因此以后：

```python
model.parameters()
```

能够递归找到所有 Q/K/V/O 的权重。

---

<a id="origin-3920"></a>
### 13.2 `Attention.__init__(config)`：先读取配置

源码：

```python
def __init__(self, config: MiniMindConfig):
    super().__init__()
```

这里的：

```python
config: MiniMindConfig
```

只是类型提示，告诉读者：

> 这个参数预期是 MiniMindConfig 对象。

比如：

```python
cfg = MiniMindConfig(
    hidden_size=8,
    num_attention_heads=2,
    num_key_value_heads=1,
    head_dim=4
)
attn = Attention(cfg)
```

这一步只是在“造 Attention”，没有输入 token。

---

<a id="origin-3955"></a>
### 13.3 KV Head 数的兼容逻辑

源码：

```python
self.num_key_value_heads = (
    config.num_attention_heads
    if config.num_key_value_heads is None
    else config.num_key_value_heads
)
```

这是 Python 的条件表达式：

```python
A if condition else B
```

最简单例子：

```python
age = 20
label = "adult" if age >= 18 else "child"
```

这里的逻辑是：

```text
如果 config.num_key_value_heads == None
    那就让 Nkv = Nq
否则
    使用显式配置的 Nkv
```

为什么这样设计？

因为：

```text
Nkv = Nq
```

时，就是普通多头注意力风格，不需要共享 KV。

而：

```text
Nkv < Nq
```

时，才是 GQA/MQA 风格。

---

<a id="origin-4009"></a>
### 13.4 保存 Query Head、KV Head

源码：

```python
self.n_local_heads = config.num_attention_heads
self.n_local_kv_heads = self.num_key_value_heads
```

例如：

```text
Nq = 8
Nkv = 4
```

那么：

```text
self.n_local_heads = 8
self.n_local_kv_heads = 4
```

这里变量名里虽然有 `local`，但本文件并没有在此处实现 tensor parallel 的“本卡局部 head 划分”。

可以把它单纯理解为本模块当前使用的 head 数。

---

<a id="origin-4038"></a>
### 13.5 `n_rep`：每个 KV Head 被多少个 Query Head 共用

源码：

```python
self.n_rep = self.n_local_heads // self.n_local_kv_heads
```

例如：

```text
8 // 4 = 2
```

所以：

```text
每个 KV Head 服务 2 个 Query Head
```

如果：

```text
Nq=8
Nkv=1
```

则：

```text
n_rep = 8
```

所有 8 个 Query Head 共用一组 KV，这就更接近 MQA。

这也说明一个隐含要求：

```text
Nq 应该能被 Nkv 整除
```

否则整数除法会产生不完整分组。

---

<a id="origin-4083"></a>
### 13.6 `head_dim`

源码：

```python
self.head_dim = config.head_dim
```

这是每个注意力头的维度 D。

例如：

```text
H=4096
Nq=32
```

常见：

```text
D=128
```

因为：

```text
32 × 128 = 4096
```

但这份代码允许显式设置 `head_dim`，所以不强制：

```text
Nq*D == H
```

即使不等，最后：

```python
self.o_proj
```

仍会把 `Nq*D` 投影回 H。

---

<a id="origin-4128"></a>
### 13.7 `self.is_causal = True`

```python
self.is_causal = True
```

非常重要。

它说明这是：

```text
Causal Self-Attention
```

位置 t 只能看：

```text
0 ... t
```

不能看：

```text
t+1 ... future
```

例如四个 token：

```text
BOS   I   love   AI
```

可见关系：

```text
BOS   ✓  ×  ×  ×
I     ✓  ✓  ×  ×
love  ✓  ✓  ✓  ×
AI    ✓  ✓  ✓  ✓
```

这正是后面 causal mask 要实现的规则。

---

<a id="origin-4173"></a>
### 13.8 `q_proj`：H 维 hidden state 如何变成多头 Query

源码：

```python
self.q_proj = nn.Linear(
    config.hidden_size,
    config.num_attention_heads * self.head_dim,
    bias=False
)
```

假设教学配置：

```text
H=8
Nq=2
D=4
```

输出宽度：

```text
Nq×D = 2×4 = 8
```

因此：

```text
q_proj: 8 → 8
```

输入：

```text
x.shape = [1,3,8]
```

经过 Linear：

```text
xq.shape = [1,3,8]
```

注意这时候还是：

```text
[1,3,Nq*D]
```

并没有真的出现一个独立的 head 轴。

后面才会：

```python
.view(1,3,2,4)
```

变成：

```text
[1,3,2,4]
```

---

<a id="origin-4239"></a>
### 13.9 `bias=False` 是什么意思？

普通 Linear：

```math
y=xW^T+b
```

但：

```python
bias=False
```

表示不创建 b。

于是只有：

```math
y=xW^T
```

如果：

```python
layer = nn.Linear(8, 8, bias=False)
```

那么参数只有：

```text
weight.shape = [8,8]
```

没有：

```text
bias.shape = [8]
```

---

<a id="origin-4281"></a>
### 13.10 `k_proj`、`v_proj`：为什么输出比 Q 小？

源码：

```python
self.k_proj = nn.Linear(
    config.hidden_size,
    self.num_key_value_heads * self.head_dim,
    bias=False
)

self.v_proj = nn.Linear(
    config.hidden_size,
    self.num_key_value_heads * self.head_dim,
    bias=False
)
```

教学配置：

```text
H=8
Nq=2
Nkv=1
D=4
```

那么：

```text
q_proj: 8 → 8
k_proj: 8 → 4
v_proj: 8 → 4
```

所以：

```text
Q 有两个 head
K/V 只有一个 head
```

为什么这么做？

核心是节约：

```text
K/V 投影参数
+
推理时 KV Cache 大小
```

尤其 KV Cache 与：

```text
Nkv
```

成正比。

---

<a id="origin-4343"></a>
### 13.11 `o_proj`：多头结果重新映射回 H

源码：

```python
self.o_proj = nn.Linear(
    config.num_attention_heads * self.head_dim,
    config.hidden_size,
    bias=False
)
```

输入宽度：

```text
Nq×D
```

输出宽度：

```text
H
```

教学配置：

```text
2×4 = 8
```

所以：

```text
8 → 8
```

大型例子：

```text
Nq=32
D=128
H=4096
```

也是：

```text
4096 → 4096
```

但概念上这不是“什么都没做”。

它仍然有一个可学习矩阵：

```text
W_O
```

负责让各个 head 拼接后的信息重新混合。

---

<a id="origin-4405"></a>
### 13.12 `q_norm` 和 `k_norm`

源码：

```python
self.q_norm = RMSNorm(
    self.head_dim,
    eps=config.rms_norm_eps
)

self.k_norm = RMSNorm(
    self.head_dim,
    eps=config.rms_norm_eps
)
```

这里特别注意：

```text
dim = head_dim = D
```

不是 H。

所以如果 Q：

```text
[B,T,Nq,D]
```

RMSNorm 总是沿最后一维 D。

每个：

```text
batch × token × head
```

组合都自己算一个 RMS。

另外：

```text
q_norm 和 k_norm 不共享 weight
```

因为它们是两个独立 RMSNorm 实例。

---

<a id="origin-4455"></a>
### 13.13 两个 Dropout

源码：

```python
self.attn_dropout = nn.Dropout(config.dropout)
self.resid_dropout = nn.Dropout(config.dropout)
self.dropout = config.dropout
```

<a id="origin-4465"></a>
#### 13.13.1 `attn_dropout`

作用在：

```text
softmax 后的注意力权重
```

<a id="origin-4473"></a>
#### 13.13.2 `resid_dropout`

作用在：

```text
Attention 输出经过 o_proj 以后
```

<a id="origin-4481"></a>
#### 13.13.3 `self.dropout`

这里只保存概率值，例如：

```text
0.1
```

因为后面的 SDPA API 需要直接传：

```python
dropout_p=...
```

而不是传一个 `nn.Dropout` 对象。

---

<a id="origin-4499"></a>
### 13.14 Dropout 最小例子

```python
m = nn.Dropout(p=0.5)
x = torch.ones(10)

m.train()
print(m(x))
```

训练模式下一部分元素随机变 0。

切换：

```python
m.eval()
```

再调用：

```python
m(x)
```

不会随机丢弃。

所以：

```text
model.eval()
```

对生成非常重要。

---

<a id="origin-4535"></a>
### 13.15 `self.flash`：这里的名字不要误解成“必然使用 FlashAttention”

源码：

```python
self.flash = (
    hasattr(torch.nn.functional, 'scaled_dot_product_attention')
    and config.flash_attn
)
```

先拆：

```python
hasattr(obj, "name")
```

意思：

> obj 上有没有名为 name 的属性。

例如：

```python
hasattr(torch.nn.functional, "softmax")
```

通常：

```text
True
```

这里检查：

```text
当前 PyTorch 是否提供 scaled_dot_product_attention
```

同时还要求：

```text
config.flash_attn == True
```

只有两个条件都满足：

```text
self.flash = True
```

但这个变量名只是作者的命名。

真正调用的是 PyTorch：

```python
F.scaled_dot_product_attention
```

底层究竟选择哪种 kernel，取决于 PyTorch、硬件、dtype、shape 等运行条件。

因此不能简单理解为：

> `self.flash=True` 就一定在用某个特定 FlashAttention 实现。

---

<a id="origin-4602"></a>
## 14. `Attention.forward()`：真正让一批 token 通过 Attention

现在进入最重要的执行函数：

```python
def forward(
    self,
    x,
    position_embeddings,
    past_key_value=None,
    use_cache=False,
    attention_mask=None
):
```

先把每个参数翻译成人话。

```text
x
    当前这次新输入 token 的 hidden states
    shape [B,T,H]

position_embeddings
    这 T 个位置对应的 cos/sin

past_key_value
    本层历史 K/V；第一次推理通常是 None

use_cache
    是否把更新后的 K/V 返回给外层保存

attention_mask
    哪些 Key 位置有效，哪些是 padding
```

非常重要：

> 每一层 Attention 都有自己独立的 KV Cache。

不能把第 0 层的 K/V 给第 1 层用。

---

<a id="origin-4645"></a>
### 14.1 `bsz, seq_len, _ = x.shape`

源码：

```python
bsz, seq_len, _ = x.shape
```

假设：

```text
x.shape = [2,3,8]
```

那么：

```text
bsz = 2
seq_len = 3
_ = 8
```

Python 里 `_` 并不是特殊关键字，只是约定俗成表示：

> 这个值接到了，但后面我不打算用。

所以相当于：

```python
bsz, seq_len, hidden_size = x.shape
```

只是 hidden_size 后面不需要。

---

<a id="origin-4681"></a>
### 14.2 一次得到 Q/K/V

源码：

```python
xq, xk, xv = self.q_proj(x), self.k_proj(x), self.v_proj(x)
```

这是 Python 的多变量赋值。

展开如下：

```python
xq = self.q_proj(x)
xk = self.k_proj(x)
xv = self.v_proj(x)
```

教学配置：

```text
x:  [1,3,8]
Q:  [1,3,8]
K:  [1,3,4]
V:  [1,3,4]
```

此时：

```text
Q/K/V 都只是 Linear 输出
```

还没有：

```text
拆头
RoPE
Attention Score
```

---

<a id="origin-4724"></a>
### 14.3 `.view(...)`：真正出现 head 轴

源码：

```python
xq = xq.view(
    bsz,
    seq_len,
    self.n_local_heads,
    self.head_dim
)
```

教学配置：

```text
[1,3,8]
→
[1,3,2,4]
```

假设某个 token 的 Q 是：

```text
[a,b,c,d,e,f,g,h]
```

重新解释为：

```text
Head 0 = [a,b,c,d]
Head 1 = [e,f,g,h]
```

`.view()` 主要改变 shape 的解释方式，不做一个新的神经网络投影。

所以“每个 head 有独立信息”来源于前面的可训练 Q 投影矩阵学会把不同特征放到不同分块，而不是 `view()` 本身创造语义。

---

<a id="origin-4764"></a>
### 14.4 K/V 同样拆头

```python
xk = xk.view(
    bsz,
    seq_len,
    self.n_local_kv_heads,
    self.head_dim
)

xv = xv.view(
    bsz,
    seq_len,
    self.n_local_kv_heads,
    self.head_dim
)
```

教学配置：

```text
K: [1,3,4] → [1,3,1,4]
V: [1,3,4] → [1,3,1,4]
```

所以现在终于能清楚看到：

```text
Q 有 2 个 Head
K/V 只有 1 个 Head
```

---

<a id="origin-4798"></a>
### 14.5 Q/K RMSNorm

源码：

```python
xq, xk = self.q_norm(xq), self.k_norm(xk)
```

展开：

```python
xq = self.q_norm(xq)
xk = self.k_norm(xk)
```

shape 不变：

```text
Q: [B,T,Nq,D]
K: [B,T,Nkv,D]
```

只是每个 head 内部 D 个值的尺度被规范化。

V 不做这一步。

---

<a id="origin-4826"></a>
### 14.6 `cos, sin = position_embeddings`

外层传进来的是一个 tuple：

```text
(cos_tensor, sin_tensor)
```

于是 Python 解包：

```python
cos, sin = position_embeddings
```

假设本次 T=3：

```text
cos: [3,D]
sin: [3,D]
```

如果这是缓存后的单 token 续写：

```text
T=1
```

可能只切位置 3：

```text
cos: [1,D]
sin: [1,D]
```

---

<a id="origin-4862"></a>
### 14.7 真正应用 RoPE

源码：

```python
xq, xk = apply_rotary_pos_emb(xq, xk, cos, sin)
```

我们已经讲过这个函数。

关键一句：

> 这里只旋转“本轮新算出来”的 Q/K。

如果有历史 KV Cache，历史 K 在它第一次生成时已经根据当时绝对位置旋转过了。

所以绝对不能每轮把历史 K 再旋转一遍。

---

<a id="origin-4882"></a>
### 14.8 KV Cache：历史 K/V 与新 K/V 拼接

源码：

```python
if past_key_value is not None:
    xk = torch.cat([past_key_value[0], xk], dim=1)
    xv = torch.cat([past_key_value[1], xv], dim=1)
```

先理解 `past_key_value` 的结构：

```text
past_key_value
=
(
    past_K,
    past_V
)
```

所以：

```python
past_key_value[0]
```

是历史 K。

```python
past_key_value[1]
```

是历史 V。

---

<a id="origin-4919"></a>
### 14.9 `torch.cat(..., dim=1)` 为什么是 dim=1？

缓存前的布局：

```text
[B,S,Nkv,D]
```

第 1 维是：

```text
sequence length
```

所以历史：

```text
past_K: [1,3,1,4]
```

本轮新 token：

```text
new_K:  [1,1,1,4]
```

沿 dim=1 拼：

```text
[1,4,1,4]
```

直观：

```text
[K1,K5,K7] + [K9]
=
[K1,K5,K7,K9]
```

V 同理。

---

<a id="origin-4963"></a>
### 14.10 为什么缓存 K/V，不缓存历史 Q？

这一行代码就是最直接的证据。

新 token 需要计算：

```text
Q_new @ [K_old, K_new]^T
```

然后：

```text
weights @ [V_old, V_new]
```

本轮根本没有用到：

```text
Q_old
```

历史 Q 的任务是：

> 当它还是“新 token”的那一轮，决定那个位置应该关注谁。

到了下一轮，新增加的是另一个 Query，所以历史 Q 不再产生新的计算价值。

---

<a id="origin-4993"></a>
### 14.11 `past_kv = (xk, xv) if use_cache else None`

源码：

```python
past_kv = (xk, xv) if use_cache else None
```

这又是条件表达式。

如果：

```text
use_cache=True
```

就返回：

```text
(K,V)
```

否则：

```text
None
```

特别注意顺序：

> 这里保存 cache 时，K/V 还没有经过 `repeat_kv()`。

这非常合理。

如果 Nkv=4、Nq=32，没必要把 K/V 先重复成 32 个头再存。

否则缓存空间直接膨胀 8 倍。

所以缓存保存：

```text
原始 Nkv 头
```

真正计算 Attention 时临时 repeat。

---

<a id="origin-5041"></a>
### 14.12 一行里做了三件事：transpose + repeat_kv

源码：

```python
xq, xk, xv = (
    xq.transpose(1, 2),
    repeat_kv(xk, self.n_rep).transpose(1, 2),
    repeat_kv(xv, self.n_rep).transpose(1, 2)
)
```

教学必须拆成：

```python
xq = xq.transpose(1, 2)

xk = repeat_kv(xk, self.n_rep)
xk = xk.transpose(1, 2)

xv = repeat_kv(xv, self.n_rep)
xv = xv.transpose(1, 2)
```

---

<a id="origin-5067"></a>
### 14.13 `transpose(1,2)` 到底交换什么？

Q 原来：

```text
[B,T,Nq,D]
```

交换维 1 和维 2：

```text
[B,Nq,T,D]
```

为什么？

因为接下来矩阵乘法希望每个 head 独立进行：

```text
Q_head: [T,D]
K_head: [S,D]
```

这样：

```text
Q @ K^T
```

自然得到：

```text
[T,S]
```

所以把 head 放到 sequence 前面，会非常方便。

---

<a id="origin-5106"></a>
### 14.14 K/V repeat 后的 shape

假设首次输入：

```text
B=1
T=S=3
Nq=2
Nkv=1
D=4
```

原始：

```text
K: [1,3,1,4]
V: [1,3,1,4]
```

repeat 2 份：

```text
[1,3,2,4]
```

transpose：

```text
[1,2,3,4]
```

于是最终：

```text
Q: [1,2,3,4]
K: [1,2,3,4]
V: [1,2,3,4]
```

每个 Query Head 现在都有对应的 K/V 可算。

---

<a id="origin-5149"></a>
### 14.15 为什么有两条 Attention 路径？

源码：

```python
if self.flash and ...:
    output = F.scaled_dot_product_attention(...)
else:
    ...手动计算...
```

这不是两个不同理论。

两条都在做同一类事情：

```math
\operatorname{softmax}\left(\frac{QK^T}{\sqrt D}+mask\right)V
```

区别只是：

```text
一条交给 PyTorch 的 SDPA 高层接口
另一条把 score、mask、softmax、@V 显式写出来
```

可以对照手动实现与 SDPA 的计算过程。

---

<a id="origin-5179"></a>
### 14.16 SDPA 分支的条件逐项解释

源码条件：

```python
if (
    self.flash
    and (seq_len > 1)
    and (not self.is_causal or past_key_value is None)
    and (
        attention_mask is None
        or torch.all(attention_mask == 1)
    )
):
```

逐项看。

<a id="origin-5197"></a>
#### 14.16.1 条件 1：`self.flash`

当前 PyTorch 有 SDPA，并且配置允许。

<a id="origin-5201"></a>
#### 14.16.2 条件 2：`seq_len > 1`

当前一次至少有两个新 token。

单 token 解码通常走手动路径。

<a id="origin-5207"></a>
#### 14.16.3 条件 3：

```python
not self.is_causal or past_key_value is None
```

本模型 `is_causal=True`，所以实际要求：

```text
past_key_value is None
```

也就是首次整段输入时可以走这条简单 causal SDPA 路径。

<a id="origin-5221"></a>
#### 14.16.4 条件 4：

```python
attention_mask is None
or
torch.all(attention_mask == 1)
```

如果有 padding 需要额外屏蔽，则不走这里。

---

<a id="origin-5233"></a>
### 14.17 `torch.all(attention_mask == 1)`

例如：

```text
mask = [1,1,1]
```

`mask == 1`：

```text
[True,True,True]
```

`torch.all(...)`：

```text
True
```

但：

```text
[1,1,0]
```

变：

```text
[True,True,False]
```

all：

```text
False
```

说明存在 padding。

---

<a id="origin-5275"></a>
### 14.18 `F.scaled_dot_product_attention(...)`

源码：

```python
output = F.scaled_dot_product_attention(
    xq,
    xk,
    xv,
    dropout_p=self.dropout if self.training else 0.0,
    is_causal=self.is_causal
)
```

这一个 API 内部负责：

```text
QK^T
除 sqrt(D)
因果 mask
softmax
dropout
乘 V
```

输入：

```text
Q: [B,Nq,T,D]
K: [B,Nq,S,D]
V: [B,Nq,S,D]
```

输出：

```text
[B,Nq,T,D]
```

---

<a id="origin-5316"></a>
### 14.19 `self.training` 是哪里来的？

`nn.Module` 自带：

```text
self.training
```

调用：

```python
model.train()
```

则：

```text
self.training=True
```

调用：

```python
model.eval()
```

则：

```text
self.training=False
```

所以：

```python
self.dropout if self.training else 0.0
```

表示：

```text
训练：使用配置 dropout
推理：dropout_p=0
```

---

<a id="origin-5363"></a>
### 14.20 手动 Attention 路径：先算 score

源码：

```python
scores = (
    xq @ xk.transpose(-2, -1)
) / math.sqrt(self.head_dim)
```

先看：

```python
xk.transpose(-2,-1)
```

如果：

```text
K: [B,Nq,S,D]
```

交换最后两维：

```text
[B,Nq,D,S]
```

于是：

```text
Q: [B,Nq,T,D]
K^T:[B,Nq,D,S]
```

矩阵乘：

```text
[B,Nq,T,S]
```

也就是每一个：

```text
batch × head
```

都有一个：

```text
T × S
```

Attention Score 矩阵。

---

<a id="origin-5420"></a>
### 14.21 `@` 是矩阵乘法，不是逐元素乘法

Python/PyTorch：

```python
A @ B
```

等价于矩阵乘语义。

而：

```python
A * B
```

是逐元素乘法。

这是后面 FFN 里非常容易混淆的一点。

Attention：

```text
Q @ K^T
```

FFN gate：

```text
act(gate) * up
```

两个完全不同。

---

<a id="origin-5456"></a>
### 14.22 为什么除以 `sqrt(head_dim)`？

```python
math.sqrt(self.head_dim)
```

例如：

```text
D=4 → sqrt(D)=2
D=128 → sqrt(D)≈11.31
```

Q/K 维度越大，点积累加的项越多，数值通常容易变大。

除以：

```math
\sqrt D
```

控制 score 的尺度，避免 softmax 过早过尖。

---

<a id="origin-5481"></a>
### 14.23 因果 Mask：为什么只处理最后 `seq_len` 列？

源码：

```python
if self.is_causal:
    scores[:, :, :, -seq_len:] += torch.full(
        (seq_len, seq_len),
        float("-inf"),
        device=scores.device
    ).triu(1)
```

这是整个缓存逻辑里很漂亮的一行。

先看没有历史 cache：

```text
S=T=3
```

最后 `seq_len=3` 列就是全部列。

创建：

```python
torch.full((3,3), -inf)
```

得到：

```text
[-inf -inf -inf]
[-inf -inf -inf]
[-inf -inf -inf]
```

`.triu(1)`：

只保留主对角线以上：

```text
[0    -inf -inf]
[0     0   -inf]
[0     0    0  ]
```

加到 score 后：

```text
未来位置变成 -inf
```

softmax 后概率就是 0。

---

<a id="origin-5538"></a>
### 14.24 `.triu(1)` 是什么？

`triu` = upper triangular。

例如：

```python
x = torch.ones(3,3)
print(x.triu(1))
```

得到：

```text
0 1 1
0 0 1
0 0 0
```

参数 `1` 表示：

> 从主对角线的上一条对角线开始保留。

所以自己位置不屏蔽，只屏蔽未来。

---

<a id="origin-5565"></a>
### 14.25 有 cache 时为什么历史列不需要 causal mask？

假设历史 3 个 token，新输入 2 个 token。

那么：

```text
S=5
T=2
scores.shape=[B,Nq,2,5]
```

列：

```text
历史0 历史1 历史2 新0 新1
```

对于两个新 Query：

```text
新0 可以看全部历史 + 自己，但不能看新1
新1 可以看全部历史 + 新0 + 自己
```

所以历史前三列全部合法，不需要屏蔽。

只需要对最后 T=2 列做：

```text
[0  -inf]
[0   0  ]
```

这正是：

```python
scores[:, :, :, -seq_len:]
```

只取最后的新 token 区域的原因。

---

<a id="origin-5609"></a>
### 14.26 Padding Mask

源码：

```python
if attention_mask is not None:
    scores += (
        1.0
        - attention_mask.unsqueeze(1).unsqueeze(2)
    ) * -1e9
```

假设：

```text
attention_mask = [[1,1,0]]
```

shape：

```text
[B,S] = [1,3]
```

第一次：

```python
unsqueeze(1)
```

变：

```text
[1,1,3]
```

第二次：

```python
unsqueeze(2)
```

变：

```text
[1,1,1,3]
```

然后广播到：

```text
[B,Nq,T,S]
```

---

<a id="origin-5665"></a>
### 14.27 为什么是 `(1-mask)*-1e9`？

mask：

```text
[1,1,0]
```

`1-mask`：

```text
[0,0,1]
```

乘：

```text
-1e9
```

得到：

```text
[0,0,-1000000000]
```

加到 score：

```text
有效位置：不变
padding：极大负数
```

softmax 后 padding 概率接近 0。

注意：

> 这主要是在屏蔽 Key 列，不是把“padding Query 行”自动清零。

这是理解 attention_mask 很重要的细节。

---

<a id="origin-5708"></a>
### 14.28 Softmax 与 Value 汇总

源码：

```python
output = self.attn_dropout(
    F.softmax(
        scores.float(),
        dim=-1
    ).type_as(xq)
) @ xv
```

教学版拆成：

```python
scores_fp32 = scores.float()
weights = F.softmax(scores_fp32, dim=-1)
weights = weights.type_as(xq)
weights = self.attn_dropout(weights)
output = weights @ xv
```

---

<a id="origin-5733"></a>
### 14.29 `dim=-1`：沿谁做 Softmax？

score：

```text
[B,Nq,T,S]
```

最后一维 S 表示：

```text
当前 Query 能看的所有 Key 位置
```

所以对每一个 Query：

```text
S 个分数 → S 个概率
```

并满足：

```text
这些概率之和 = 1
```

例如：

```text
scores = [2,1,0]
```

softmax 约：

```text
[0.665,0.245,0.090]
```

意思：

```text
当前 Query
从三个 Value 中分别读 66.5%、24.5%、9.0%
```

---

<a id="origin-5780"></a>
### 14.30 为什么 Softmax 先 `.float()`？

同 RMSNorm 类似。

softmax 包含：

```text
指数
求和
归一化
```

对数值精度比较敏感。

所以先 FP32：

```python
scores.float()
```

算完后再：

```python
.type_as(xq)
```

恢复 Q 的 dtype。

---

<a id="origin-5810"></a>
### 14.31 `weights @ xv` 到底算什么？

shape：

```text
weights: [B,Nq,T,S]
V:       [B,Nq,S,D]
```

矩阵乘：

```text
[B,Nq,T,D]
```

对某一个 Query：

```math
O_i=\sum_j\alpha_{ij}V_j
```

例如：

```text
alpha = [0.7,0.2,0.1]
```

三个 Value：

```text
V1=[1,0]
V2=[0,2]
V3=[3,1]
```

输出：

```text
0.7*[1,0]
+
0.2*[0,2]
+
0.1*[3,1]
```

得到：

```text
[1.0,0.5]
```

这才是 Attention 真正“从上下文读取内容”的动作。

---

<a id="origin-5865"></a>
### 14.32 多头重新合并

源码：

```python
output = output.transpose(1, 2).reshape(
    bsz,
    seq_len,
    -1
)
```

原来：

```text
[B,Nq,T,D]
```

transpose：

```text
[B,T,Nq,D]
```

reshape：

```text
[B,T,Nq*D]
```

例如：

```text
[1,3,2,4]
→
[1,3,8]
```

`-1` 的意思：

> 这一维请 PyTorch 根据总元素数自动推导。

不是“倒数第一维”。

---

<a id="origin-5911"></a>
### 14.33 `o_proj` + `resid_dropout`

源码：

```python
output = self.resid_dropout(
    self.o_proj(output)
)
```

顺序：

```text
concat heads
↓
o_proj
↓
Dropout
```

最终：

```text
[B,T,H]
```

这很关键，因为 Block 外面要：

```python
hidden_states += residual
```

残差相加要求两边 shape 一致。

---

<a id="origin-5947"></a>
### 14.34 `return output, past_kv`

源码：

```python
return output, past_kv
```

因此 Attention 一次 forward 返回两个东西：

```text
1. 当前 token 的 Attention 输出 [B,T,H]
2. 更新后的本层 KV cache 或 None
```

外面的 Block 会：

```python
hidden_states, present_key_value = self.self_attn(...)
```

分别接住。

---

<a id="origin-5972"></a>
### 14.35 把首次输入的完整 shape 流程跑一遍

教学配置：

```text
B=1
T=3
H=8
Nq=2
Nkv=1
D=4
```

输入：

```text
x = [1,3,8]
```

Q/K/V 投影：

```text
Q [1,3,8]
K [1,3,4]
V [1,3,4]
```

拆头：

```text
Q [1,3,2,4]
K [1,3,1,4]
V [1,3,1,4]
```

Q/K Norm + RoPE：

```text
shape 不变
```

保存 cache：

```text
K/V [1,3,1,4]
```

repeat KV：

```text
K/V [1,3,2,4]
```

transpose：

```text
Q/K/V [1,2,3,4]
```

score：

```text
[1,2,3,3]
```

softmax@V：

```text
[1,2,3,4]
```

transpose+concat：

```text
[1,3,8]
```

o_proj：

```text
[1,3,8]
```

所以 Attention 前后：

```text
[B,T,H]
→
[B,T,H]
```

中间却完成了全部上下文交换。

---

<a id="origin-6067"></a>
### 14.36 缓存后单 token 续写的完整 shape

已有历史 3 个 token：

```text
past_K/V = [1,3,1,4]
```

本轮只输入新 token：

```text
x=[1,1,8]
T=1
```

新 Q/K/V：

```text
Q [1,1,2,4]
K [1,1,1,4]
V [1,1,1,4]
```

K/V 与历史拼：

```text
[1,4,1,4]
```

保存新 cache：

```text
长度 4
```

repeat + transpose：

```text
Q [1,2,1,4]
K [1,2,4,4]
V [1,2,4,4]
```

score：

```text
[1,2,1,4]
```

解释：

> 两个 Query Head，各自只有 1 个新 Query；这个 Query 可以对 4 个历史/当前 Key 打分。

最后输出：

```text
[1,1,8]
```

这就是 KV Cache 为什么让生成从“每轮重算整个序列”变成“每轮只处理新增 token”。

---

<a id="origin-6130"></a>
### 14.37 Attention 这一章最终应该记住的代码骨架

把工程细节全部拿掉，只剩：

```python
def attention(x, past_kv=None):
    Q = q_proj(x)
    K = k_proj(x)
    V = v_proj(x)

    Q = split_heads(Q)
    K = split_heads(K)
    V = split_heads(V)

    Q = q_norm(Q)
    K = k_norm(K)

    Q, K = rope(Q, K)

    if past_kv is not None:
        K = cat(past_K, K)
        V = cat(past_V, V)

    cache = (K, V)

    K = repeat_kv(K)
    V = repeat_kv(V)

    score = Q @ K.T / sqrt(D)
    score = causal_mask(score)
    weight = softmax(score)
    out = weight @ V

    out = concat_heads(out)
    out = o_proj(out)

    return out, cache
```



<a id="origin-6172"></a>
## 15. `FeedForward`：Attention 开完会以后，每个 token 自己做一次非线性加工

Attention 负责：

```text
不同 token 之间交换信息
```

FeedForward 负责：

```text
每个 token 独立处理自己的 hidden features
```

所以它不会在时间维 T 上做 token-to-token 混合。

输入输出：

```text
[B,T,H] → [B,T,H]
```

中间暂时扩展为：

```text
[B,T,I]
```

这份实现是门控 FFN，形式可以写成：

```math
\operatorname{FFN}(x)
=
W_{down}
\left(
\operatorname{SiLU}(W_{gate}x)
\odot
(W_{up}x)
\right)
```

其中 `⊙` 是逐元素乘法。

---

<a id="origin-6217"></a>
### 15.1 构造函数

源码：

```python
class FeedForward(nn.Module):
    def __init__(self, config: MiniMindConfig, intermediate_size: int = None):
        super().__init__()
        intermediate_size = intermediate_size or config.intermediate_size
        self.gate_proj = nn.Linear(config.hidden_size, intermediate_size, bias=False)
        self.down_proj = nn.Linear(intermediate_size, config.hidden_size, bias=False)
        self.up_proj = nn.Linear(config.hidden_size, intermediate_size, bias=False)
        self.act_fn = ACT2FN[config.hidden_act]
```

---

<a id="origin-6234"></a>
### 15.2 `intermediate_size = intermediate_size or config.intermediate_size`

这里用了 Python 的 `or` 返回值语义。

最简单：

```python
x = None or 12
```

得到：

```text
12
```

```python
x = 16 or 12
```

得到：

```text
16
```

所以这里表示：

```text
如果调用者显式传 intermediate_size
    用传入值
否则
    用 config.intermediate_size
```

注意：

```text
0
```

也是 Falsey，因此传 0 也会回退到配置值。

不过中间维本来也应当是正整数。

---

<a id="origin-6281"></a>
### 15.3 `gate_proj`

```python
self.gate_proj = nn.Linear(
    config.hidden_size,
    intermediate_size,
    bias=False
)
```

例如：

```text
H=8
I=12
```

则：

```text
8 → 12
```

输入：

```text
[B,T,8]
```

输出：

```text
[B,T,12]
```

这条分支随后会过激活函数。

---

<a id="origin-6320"></a>
### 15.4 `up_proj`

```python
self.up_proj = nn.Linear(
    config.hidden_size,
    intermediate_size,
    bias=False
)
```

也是：

```text
H → I
```

但它有自己独立的权重矩阵。

所以：

```text
gate_proj(x)
```

和：

```text
up_proj(x)
```

虽然 shape 一样，数值和语义完全不同。

---

<a id="origin-6354"></a>
### 15.5 `down_proj`

```python
self.down_proj = nn.Linear(
    intermediate_size,
    config.hidden_size,
    bias=False
)
```

把中间宽度：

```text
I
```

重新投影回：

```text
H
```

因为最终还要和残差相加。

---

<a id="origin-6380"></a>
### 15.6 `ACT2FN[config.hidden_act]`

```python
self.act_fn = ACT2FN[config.hidden_act]
```

假设：

```text
config.hidden_act = "silu"
```

就相当于：

```text
从 ACT2FN 中找到 SiLU 对应函数
```

后面：

```python
self.act_fn(tensor)
```

才真正执行激活。

---

<a id="origin-6408"></a>
### 15.7 `FeedForward.forward()`：一行里面其实有五步

源码：

```python
def forward(self, x):
    return self.down_proj(
        self.act_fn(self.gate_proj(x)) * self.up_proj(x)
    )
```

教学版：

```python
gate = self.gate_proj(x)
gate = self.act_fn(gate)
up = self.up_proj(x)
merged = gate * up
out = self.down_proj(merged)
return out
```

---

<a id="origin-6432"></a>
### 15.8 `*` 是逐元素乘，不是矩阵乘

假设中间只有 2 维：

```text
gate = [0,2]
up   = [3,4]
```

SiLU：

```text
SiLU(0)=0
SiLU(2)≈1.7616
```

所以：

```text
activated_gate=[0,1.7616]
```

逐元素乘：

```text
[0×3, 1.7616×4]
=
[0,7.0464]
```

这一步可以理解为：

> gate 分支决定各个中间特征“通过多少”，up 分支提供被调节的内容。

注意 gate 并不是概率：

```text
不需要加起来等于 1
```

---

<a id="origin-6474"></a>
### 15.9 SiLU 是什么？

```math
\operatorname{SiLU}(x)=x\sigma(x)
```

其中：

```math
\sigma(x)=\frac{1}{1+e^{-x}}
```

例如：

```text
x=2
sigmoid(2)≈0.8808
SiLU(2)≈1.7616
```

与 ReLU：

```text
max(0,x)
```

相比，SiLU 是平滑的非线性函数。

---

<a id="origin-6504"></a>
### 15.10 FFN 的完整 shape 链

教学配置：

```text
B=1
T=3
H=8
I=12
```

输入：

```text
[1,3,8]
```

两条支路：

```text
gate_proj → [1,3,12]
up_proj   → [1,3,12]
```

SiLU 不改 shape：

```text
[1,3,12]
```

逐元素相乘：

```text
[1,3,12]
```

`down_proj`：

```text
[1,3,8]
```

所以：

```text
FFN 前后 H 不变
```

---

<a id="origin-6554"></a>
### 15.11 为什么说 FFN 不交换 token 信息？

Linear 只作用最后一维。

如果：

```text
x.shape=[B,T,H]
```

那么它相当于对每一个：

```text
x[b,t,:]
```

使用同一套权重矩阵。

不会把：

```text
t=0
```

的数据直接拿去跟：

```text
t=1
```

矩阵相乘。

因此：

```text
Attention = 跨 token 混合
FFN       = token 内部特征变换
```

---

<a id="origin-6595"></a>
## 16. `MOEFeedForward`：不是每个 token 都经过同一个 FFN，而是先选专家

如果：

```text
config.use_moe=False
```

模型使用普通 `FeedForward`。

如果：

```text
config.use_moe=True
```

则每个 Block 使用：

```python
MOEFeedForward
```

先记住最核心结构：

```text
每个 token
   │
   ▼
Router / Gate
   │
   ├─ 给 Expert 0 打分
   ├─ 给 Expert 1 打分
   ├─ 给 Expert 2 打分
   └─ 给 Expert 3 打分
   │
   ▼
选择 Top-K
   │
   ├─ Expert a
   └─ Expert b
   │
   ▼
按路由权重加权求和
```

这里每个 Expert 本质上就是一个独立 `FeedForward`。

---

<a id="origin-6644"></a>
### 16.1 `self.config = config`

源码：

```python
self.config = config
```

为什么 FeedForward 没保存整个 config，而 MoE 保存了？

因为 `MOEFeedForward.forward()` 运行时还需要读取：

```text
num_experts_per_tok
norm_topk_prob
router_aux_loss_coef
num_experts
```

所以直接把完整配置对象保存下来最方便。

---

<a id="origin-6667"></a>
### 16.2 Router：`H → E`

源码：

```python
self.gate = nn.Linear(
    config.hidden_size,
    config.num_experts,
    bias=False
)
```

如果：

```text
H=8
E=4
```

那么：

```text
8 → 4
```

每一个 token 的 H 维 hidden state 会产生 4 个专家分数。

例如：

```text
[2.1, 0.4, -0.2, 1.7]
```

这 4 个数分别对应 Expert 0～3。

---

<a id="origin-6704"></a>
### 16.3 `nn.ModuleList([...])`

源码：

```python
self.experts = nn.ModuleList([
    FeedForward(
        config,
        intermediate_size=config.moe_intermediate_size
    )
    for _ in range(config.num_experts)
])
```

这一行包含两个新知识。

<a id="origin-6720"></a>
#### 16.3.1 List comprehension

普通写法：

```python
lst = []
for i in range(4):
    lst.append(i * 2)
```

可以写成：

```python
lst = [i * 2 for i in range(4)]
```

这里：

```python
[
    FeedForward(...)
    for _ in range(E)
]
```

就是创建 E 个 FeedForward 对象。

<a id="origin-6747"></a>
#### 16.3.2 为什么不能只用普通 list？

如果把子模块放普通 Python list：

```python
self.experts = [FeedForward(...), ...]
```

PyTorch 不一定能像 `ModuleList` 那样完整递归注册其中所有子模块。

而：

```python
nn.ModuleList
```

会明确告诉 PyTorch：

> 这里是一组需要统一管理的神经网络子模块。

这样：

```text
.to(device)
state_dict()
parameters()
```

都会递归处理所有专家。

---

<a id="origin-6779"></a>
### 16.4 专家之间共享参数吗？

不会。

每次：

```python
FeedForward(...)
```

都会新建：

```text
gate_proj
up_proj
down_proj
```

所以：

```text
Expert 0
Expert 1
Expert 2
Expert 3
```

拥有不同参数。

---

<a id="origin-6810"></a>
### 16.5 `self.act_fn` 在这里其实没有直接使用

源码：

```python
self.act_fn = ACT2FN[config.hidden_act]
```

但当前 `MOEFeedForward.forward()` 没有直接调用它。

真正激活发生在：

```text
每个 Expert 自己的 FeedForward.forward()
```

所以这一属性在当前实现中属于“保存了但没有直接使用”。

读源码时看到一个属性，不要默认它一定会在当前类 forward 中用到；应当搜索引用。

---

<a id="origin-6832"></a>
## 17. `MOEFeedForward.forward()`：逐 token 路由

源码开始：

```python
batch_size, seq_len, hidden_dim = x.shape
x_flat = x.view(-1, hidden_dim)
```

假设：

```text
B=2
T=3
H=8
```

原输入：

```text
[2,3,8]
```

`view(-1,8)`：

```text
[6,8]
```

这里：

```text
N = B*T = 6
```

也就是把所有 batch 里的 token 暂时排成一张二维表：

```text
Token 0 → 一行
Token 1 → 一行
...
Token 5 → 一行
```

为什么？

因为 Router 和 Expert 分发都更容易按“token 行”处理。

---

<a id="origin-6882"></a>
### 17.1 Router 分数与 Softmax

```python
scores = F.softmax(
    self.gate(x_flat),
    dim=-1
)
```

先：

```text
x_flat [N,H]
↓ gate
[N,E]
```

再对 E 维 softmax：

```text
每个 token 对所有 Expert 的概率和为 1
```

例如：

```text
Token 0:
[0.60, 0.30, 0.10]

Token 1:
[0.20, 0.30, 0.50]
```

---

<a id="origin-6917"></a>
### 17.2 `torch.topk`

源码：

```python
topk_weight, topk_idx = torch.topk(
    scores,
    k=self.config.num_experts_per_tok,
    dim=-1,
    sorted=False
)
```

如果：

```text
scores=[0.6,0.3,0.1]
K=2
```

得到概念上：

```text
topk_weight=[0.6,0.3]
topk_idx=[0,1]
```

其中：

```text
weight = 概率值
idx    = 专家编号
```

为什么 `sorted=False`？

表示：

> 只要求找出 top-k，不保证返回的这 K 个槽位按概率从大到小排列。

后续代码也不依赖槽位顺序。

---

<a id="origin-6961"></a>
### 17.3 重新归一化 Top-K 概率

源码：

```python
if self.config.norm_topk_prob:
    topk_weight = topk_weight / (
        topk_weight.sum(dim=-1, keepdim=True) + 1e-20
    )
```

例如原始 softmax：

```text
[0.6,0.3,0.1]
```

选前两项：

```text
[0.6,0.3]
```

它们加起来：

```text
0.9
```

重新归一化：

```text
[0.6/0.9, 0.3/0.9]
=
[2/3,1/3]
```

于是被丢掉的专家不再占总概率质量。

`1e-20` 是极小稳定项，避免分母意外成为 0。

---

<a id="origin-7004"></a>
### 17.4 `torch.zeros_like(x_flat)`

源码：

```python
y = torch.zeros_like(x_flat)
```

如果：

```text
x_flat.shape=[N,H]
```

那么：

```text
y.shape=[N,H]
```

而且：

```text
dtype 相同
device 相同
```

初始全部为 0。

为什么？

因为接下来各专家的贡献会不断：

```text
加到 y 对应 token 行
```

---

<a id="origin-7043"></a>
### 17.5 `for i, expert in enumerate(self.experts)`

`enumerate` 最小例子：

```python
names = ["A", "B", "C"]
for i, name in enumerate(names):
    print(i, name)
```

输出：

```text
0 A
1 B
2 C
```

所以：

```python
for i, expert in enumerate(self.experts):
```

同时拿到：

```text
i = 专家编号
expert = 专家模块对象
```

---

<a id="origin-7076"></a>
### 17.6 `mask = (topk_idx == i)`

假设：

```text
topk_idx =
[
 [0,1],
 [2,1]
]
```

当前：

```text
i=1
```

则：

```text
topk_idx == 1
```

得到布尔矩阵：

```text
[
 [False, True],
 [False, True]
]
```

含义：

```text
Token0 的第2个 top-k 槽位选了 Expert1
Token1 的第2个 top-k 槽位也选了 Expert1
```

---

<a id="origin-7118"></a>
### 17.7 `if mask.any()`

```python
mask.any()
```

只要 mask 中有至少一个 True，就返回 True。

所以：

```text
当前专家至少被一个 token 选中
```

才真正执行专家计算。

如果完全没人选，就避免无意义地跑整个 FFN。

---

<a id="origin-7138"></a>
### 17.8 `mask.any(dim=-1)`

继续刚才：

```text
mask =
[
 [False,True],
 [False,True]
]
```

沿最后一维 K 合并：

```text
[True,True]
```

意思：

```text
Token0 用了当前专家
Token1 也用了当前专家
```

如果：

```text
[
 [True,False],
 [False,False]
]
```

则：

```text
[True,False]
```

---

<a id="origin-7180"></a>
### 17.9 `.nonzero().flatten()`

源码：

```python
token_idx = mask.any(dim=-1).nonzero().flatten()
```

假设：

```text
[False, True, False, True]
```

`.nonzero()` 找 True 的位置：

```text
[[1],
 [3]]
```

shape：

```text
[2,1]
```

`.flatten()`：

```text
[1,3]
```

于是：

```text
当前 Expert 只需要处理 token 行 1 和 3
```

---

<a id="origin-7221"></a>
### 17.10 `topk_weight[mask]`

源码：

```python
weight = topk_weight[mask].view(-1, 1)
```

这是布尔索引。

假设：

```text
topk_weight=
[
 [0.7,0.3],
 [0.625,0.375]
]
```

当前 Expert1 的 mask：

```text
[
 [False,True],
 [False,True]
]
```

取出：

```text
[0.3,0.375]
```

`.view(-1,1)`：

```text
[
 [0.3],
 [0.375]
]
```

为什么变成 `[M,1]`？

因为专家输出：

```text
[M,H]
```

权重：

```text
[M,1]
```

可以广播成：

```text
每个 token 的整个 H 维输出都乘同一个路由权重
```

---

<a id="origin-7287"></a>
### 17.11 `expert(x_flat[token_idx])`

如果当前专家只被 M 个 token 选中：

```text
x_flat[token_idx]
→ [M,H]
```

然后只把这些 token 送进这个专家 FFN。

不是让所有 N 个 token 都运行每一个专家。

这就是稀疏 MoE 节省计算的关键。

---

<a id="origin-7304"></a>
### 17.12 `index_add_`：把专家输出加回原 token 行

源码：

```python
y.index_add_(
    0,
    token_idx,
    (
        expert(x_flat[token_idx]) * weight
    ).to(y.dtype)
)
```

这是 MoE 最难读的一行之一。

先举最简单例子。

```python
y = torch.zeros(4,2)
index = torch.tensor([1,3])
source = torch.tensor([
    [10.,20.],
    [30.,40.]
])

y.index_add_(0, index, source)
```

结果：

```text
row0 [0,0]
row1 [10,20]
row2 [0,0]
row3 [30,40]
```

如果后面又往 row1 加一次：

```text
会累加，不是覆盖
```

这正适合 MoE，因为同一个 token 会被 K 个专家贡献。

---

<a id="origin-7352"></a>
### 17.13 为什么必须“加”而不是赋值？

如果 Token0 选：

```text
Expert0 权重 2/3
Expert1 权重 1/3
```

那么最终：

```math
y_0=\frac23E_0(x_0)+\frac13E_1(x_0)
```

所以：

```text
第一次 expert0 加进去
第二次 expert1 再加进去
```

必须累加。

---

<a id="origin-7378"></a>
### 17.14 `elif self.training`：没人选这个 Expert，为什么还碰一下参数？

源码：

```python
elif self.training:
    y[0, 0] += 0 * sum(p.sum() for p in expert.parameters())
```

数值上：

```text
加的是 0
```

所以输出不变。

但计算图里仍然把：

```text
当前 expert 的参数
```

通过一个乘 0 的路径连进来。

这常用于减轻某些分布式训练场景对“未使用参数”的处理问题。

---

<a id="origin-7407"></a>
### 17.15 `sum(p.sum() for p in expert.parameters())`

这又有 generator expression。

```python
for p in expert.parameters()
```

遍历专家全部参数。

```python
p.sum()
```

每个参数 Tensor 求和成标量。

外面 Python `sum(...)` 再把所有标量加起来。

最后：

```python
0 * ...
```

数值恒为 0，但保留计算图连接。

---

<a id="origin-7435"></a>
### 17.16 MoE 辅助损失：为什么需要负载均衡

如果 Router 总是把所有 token 都送给 Expert0：

```text
Expert0 爆满
Expert1/2/3 几乎不用
```

那么 MoE 的专家容量就浪费了。

所以训练时常加入一个辅助目标，鼓励路由更均衡。

源码：

```python
if self.training and self.config.router_aux_loss_coef > 0:
```

两个条件：

```text
训练模式
并且辅助损失系数 > 0
```

---

<a id="origin-7463"></a>
### 17.17 `F.one_hot(topk_idx, num_experts)`

假设：

```text
topk_idx=
[
 [0,1],
 [2,1]
]
```

E=3。

one-hot 后 shape：

```text
[N,K,E] = [2,2,3]
```

可以理解为：

```text
Token0 slot0 → [1,0,0]
Token0 slot1 → [0,1,0]
Token1 slot0 → [0,0,1]
Token1 slot1 → [0,1,0]
```

`.float()` 把整数 0/1 转成浮点，方便后续平均。

---

<a id="origin-7496"></a>
### 17.18 `.mean(0)`

源码：

```python
load = F.one_hot(...).float().mean(0)
```

沿第 0 维 N 个 token 求平均。

结果 shape：

```text
[K,E]
```

表示：

> 每个 top-k 槽位中，各 Expert 被选中的比例。

---

<a id="origin-7518"></a>
### 17.19 `scores.mean(0)`

`scores`：

```text
[N,E]
```

沿 token 平均：

```text
[E]
```

表示：

```text
Router 平均给每个 Expert 多少概率质量
```

---

<a id="origin-7540"></a>
### 17.20 aux_loss 公式

源码：

```python
self.aux_loss = (
    load * scores.mean(0)
).sum() * self.config.num_experts * self.config.router_aux_loss_coef
```

按原文件示例：

```text
load=
[[0.5,0,0.5],
 [0,1,0]]

scores.mean(0)=[0.4,0.3,0.3]
```

广播相乘并求和：

```text
0.5×0.4 + 0×0.3 + 0.5×0.3
+
0×0.4 + 1×0.3 + 0×0.3
=
0.65
```

E=3：

```text
0.65×3=1.95
```

系数：

```text
0.0005
```

最终：

```text
0.000975
```

注意本文件最后只是把 `aux_loss` 返回出去，并没有在 `MiniMindForCausalLM.forward()` 中自动：

```text
loss = CE + aux_loss
```

训练脚本如果需要，应当自己决定怎么合并。

---

<a id="origin-7598"></a>
### 17.21 非训练模式的 aux_loss

源码：

```python
self.aux_loss = scores.new_zeros(1).squeeze()
```

`new_zeros(1)`：

```text
创建一个与 scores 同 dtype、同 device 的 [1] 零 Tensor
```

`.squeeze()`：

```text
[1] → 标量 Tensor shape []
```

所以返回的是 Tensor 0，不是 Python 整数 0。

这对 device/dtype 一致性更友好。

---

<a id="origin-7624"></a>
### 17.22 最后恢复 [B,T,H]

```python
return y.view(batch_size, seq_len, hidden_dim)
```

前面：

```text
[B,T,H]
→
[N,H]
```

现在恢复：

```text
[N,H]
→
[B,T,H]
```

MoE 对外接口因此与普通 FeedForward 完全一致。

这就是为什么 Block 可以写：

```python
self.mlp = FeedForward(...) if not use_moe else MOEFeedForward(...)
```

而不用为两种情况写两个不同 forward。

---

<a id="origin-7658"></a>
## 18. `MiniMindBlock`：终于把 Attention 和 FFN 装成一层 Transformer

现在前面所有零件开始真正组装。

Block 构造：

```python
class MiniMindBlock(nn.Module):
    def __init__(self, layer_id: int, config: MiniMindConfig):
        super().__init__()
        self.self_attn = Attention(config)
        self.input_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.post_attention_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.mlp = FeedForward(config) if not config.use_moe else MOEFeedForward(config)
```

核心结构只有：

```text
RMSNorm
Attention
Residual
RMSNorm
FFN/MoE
Residual
```

---

<a id="origin-7687"></a>
### 18.1 `layer_id` 为什么传进来了却没保存？

函数签名：

```python
def __init__(self, layer_id: int, config: MiniMindConfig):
```

但内部没有：

```python
self.layer_id = layer_id
```

说明当前实现中：

```text
layer_id 只是接口保留/调用时传入
但本类当前逻辑并不使用它
```

读源码时很重要的一条原则：

> 参数写在函数签名里，不代表它一定影响计算；要继续看函数体。

---

<a id="origin-7714"></a>
### 18.2 `self.self_attn = Attention(config)`

这一步是真正创建当前 Block 自己的 Attention 参数。

如果模型有 8 层：

```text
Block0.Attention
Block1.Attention
...
Block7.Attention
```

是 8 套独立权重。

不会默认共享 Q/K/V/O 参数。

---

<a id="origin-7733"></a>
### 18.3 两个 RMSNorm 为什么不共享？

```python
self.input_layernorm = RMSNorm(H)
self.post_attention_layernorm = RMSNorm(H)
```

它们分别位于：

```text
Attention 前
FFN 前
```

都有自己独立的 H 维 `weight`。

不能因为都是 RMSNorm 就认为参数相同。

---

<a id="origin-7753"></a>
### 18.4 条件表达式选择普通 FFN 还是 MoE

```python
self.mlp = (
    FeedForward(config)
    if not config.use_moe
    else MOEFeedForward(config)
)
```

如果：

```text
use_moe=False
```

创建：

```text
FeedForward
```

如果：

```text
use_moe=True
```

创建：

```text
MOEFeedForward
```

但二者接口都保证：

```text
[B,T,H] → [B,T,H]
```

所以 Block.forward 无需知道里面具体是哪一种。

这就是良好的“接口一致性”。

---

<a id="origin-7799"></a>
## 19. `MiniMindBlock.forward()`：两次 Pre-Norm + 两次 Residual

完整源码骨架：

```python
def forward(...):
    residual = hidden_states

    hidden_states, present_key_value = self.self_attn(
        self.input_layernorm(hidden_states),
        position_embeddings,
        past_key_value,
        use_cache,
        attention_mask
    )

    hidden_states += residual

    hidden_states = hidden_states + self.mlp(
        self.post_attention_layernorm(hidden_states)
    )

    return hidden_states, present_key_value
```

把它压缩成数学故事：

```text
h1 = h0 + Attention(Norm1(h0))

h2 = h1 + FFN(Norm2(h1))
```

这就是一整个 Transformer Block。

---

<a id="origin-7836"></a>
### 19.1 `residual = hidden_states` 是 clone 吗？

不是。

这只是：

```text
让 residual 和 hidden_states 暂时引用同一个 Tensor 对象
```

没有：

```python
hidden_states.clone()
```

不过下一步：

```python
hidden_states, present_key_value = self.self_attn(...)
```

会让 `hidden_states` 变量重新绑定到 Attention 返回的新 Tensor。

因此 `residual` 仍指向原来的输入 Tensor。

---

<a id="origin-7864"></a>
### 19.2 为什么先 Norm 再 Attention？

```python
self.self_attn(
    self.input_layernorm(hidden_states),
    ...
)
```

说明结构是：

```text
Norm → Attention → Residual
```

也就是 Pre-Norm。

不是：

```text
Attention → Residual → Norm
```

两种都曾出现在不同 Transformer 架构里，但这份代码明确是 Pre-Norm 风格。

---

<a id="origin-7891"></a>
### 19.3 位置参数为什么没有写名字？

调用：

```python
self.self_attn(
    self.input_layernorm(hidden_states),
    position_embeddings,
    past_key_value,
    use_cache,
    attention_mask
)
```

这里后四个是位置参数。

它们依次对应函数签名：

```python
def forward(
    self,
    x,
    position_embeddings,
    past_key_value=None,
    use_cache=False,
    attention_mask=None
)
```

所以必须严格按顺序。

后面主模型调用 Block 时，为了更清楚，会使用：

```python
past_key_value=past_key_value
use_cache=use_cache
attention_mask=attention_mask
```

这种关键字参数。

---

<a id="origin-7934"></a>
### 19.4 第一次残差相加

源码：

```python
hidden_states += residual
```

假设一个 token：

```text
原输入 residual = [1.0,2.0]
Attention 输出 = [0.1,0.2]
```

相加：

```text
[1.1,2.2]
```

直观理解：

```text
原来的信息
+
从上下文读到的新信息
```

---

<a id="origin-7965"></a>
### 19.5 `+=` 是原地操作意味什么？

`hidden_states += residual` 通常会尝试原地更新左侧 Tensor。

与：

```python
hidden_states = hidden_states + residual
```

在对象/内存语义上并不总是完全相同。

不过这里关注模型数学结构即可：

```text
Attention 输出 + 原输入
```

如果以后排查 autograd 的原地修改错误，才需要特别关注 inplace 语义。

---

<a id="origin-7987"></a>
### 19.6 第二次：Norm → MLP → Residual

源码：

```python
hidden_states = hidden_states + self.mlp(
    self.post_attention_layernorm(hidden_states)
)
```

教学版：

```python
residual2 = hidden_states
normalized = self.post_attention_layernorm(hidden_states)
ffn_out = self.mlp(normalized)
hidden_states = residual2 + ffn_out
```

假设：

```text
第一次残差后 h1=[1.1,2.2]
FFN 输出=[0.3,-0.2]
```

最终：

```text
h2=[1.4,2.0]
```

---

<a id="origin-8021"></a>
### 19.7 为什么 FFN 不返回 KV Cache？

因为 KV Cache 只来自 Self-Attention 的：

```text
K
V
```

FFN 只是逐 token 特征变换，没有历史 Key/Value 概念。

所以 Block 返回：

```python
return hidden_states, present_key_value
```

其中：

```text
present_key_value
```

完全由当前层 Attention 产生。

---

<a id="origin-8048"></a>
### 19.8 一个 Block 的完整 shape 不变量

输入：

```text
[B,T,H]
```

Norm：

```text
[B,T,H]
```

Attention：

```text
[B,T,H]
```

Residual：

```text
[B,T,H]
```

Norm：

```text
[B,T,H]
```

FFN：

```text
[B,T,H]
```

Residual：

```text
[B,T,H]
```

所以整个 Block 的“接口合同”很简单：

```text
[B,T,H] → [B,T,H]
```

真正变化的是：

```text
数值内容 / 语义表示
```

而不是外部 shape。

---

<a id="origin-8108"></a>
### 19.9 到这里，把一个 Block 压缩成两行

这段源码可以概括为：

```python
x = x + Attention(RMSNorm(x))
x = x + FFN(RMSNorm(x))
```

如果 `use_moe=True`：

```python
x = x + Attention(RMSNorm(x))
x = x + MoE(RMSNorm(x))
```

下一章我们不再研究单层内部，而是把很多个 Block 堆起来形成完整 Transformer 主干。


<a id="origin-8127"></a>
## 20. `MiniMindModel`：把 Embedding、N 个 Block、最终 Norm 组装成 Transformer 主干

前面我们一直在研究“一层内部”。

现在进入：

```python
class MiniMindModel(nn.Module):
```

它的职责可以压缩成一句话：

> 把整数 token ID 变成最终上下文化 hidden states。

注意：

```text
MiniMindModel 还不是完整语言模型
```

它没有负责：

```text
H → Vocabulary logits
CrossEntropy Loss
generate 采样
```

它只做 Transformer backbone。

整体：

```text
input_ids [B,T]
    │
    ▼
Embedding
    │
    ▼
[B,T,H]
    │
    ▼
Block 0
    │
    ▼
Block 1
    │
   ...
    │
    ▼
Block N-1
    │
    ▼
Final RMSNorm
    │
    ▼
hidden_states [B,T,H]
```

---

<a id="origin-8188"></a>
### 20.1 保存配置

源码：

```python
self.config = config
```

为什么要保存？

后面 `forward()` 中若需要重建 RoPE 表，会用到：

```text
config.head_dim
config.max_position_embeddings
config.rope_theta
config.rope_scaling
```

所以不能只在构造时临时读取完就丢掉。

---

<a id="origin-8211"></a>
### 20.2 一行保存两个属性

源码：

```python
self.vocab_size, self.num_hidden_layers = (
    config.vocab_size,
    config.num_hidden_layers
)
```

Python 元组解包。

等价于：

```python
self.vocab_size = config.vocab_size
self.num_hidden_layers = config.num_hidden_layers
```

---

<a id="origin-8233"></a>
### 20.3 `nn.Embedding(V,H)`：token ID 真正变成向量

源码：

```python
self.embed_tokens = nn.Embedding(
    config.vocab_size,
    config.hidden_size
)
```

例如：

```text
V=16
H=8
```

Embedding 内部有一个可训练参数表：

```text
weight.shape = [16,8]
```

可以想成：

```text
Token 0 → 第 0 行 8 个数
Token 1 → 第 1 行 8 个数
...
Token 15 → 第 15 行 8 个数
```

输入：

```python
input_ids = torch.tensor([[1,5,7]])
```

shape：

```text
[1,3]
```

输出：

```python
x = self.embed_tokens(input_ids)
```

shape：

```text
[1,3,8]
```

---

<a id="origin-8292"></a>
### 20.4 Embedding 不是 one-hot 后再显式矩阵乘吗？

数学上可以理解为类似：

```text
one-hot(token_id) @ W_embedding
```

但工程实现不会真的创建一个 V 维 one-hot 向量再乘矩阵。

`nn.Embedding` 本质更像：

> 按整数索引直接查参数矩阵对应行。

所以 token 5：

```text
取 weight[5]
```

效率更高。

---

<a id="origin-8316"></a>
### 20.5 输入 Dropout

源码：

```python
self.dropout = nn.Dropout(config.dropout)
```

它将在：

```text
Embedding 输出之后
```

使用。

若：

```text
dropout=0
```

训练时也不会丢任何元素。

---

<a id="origin-8342"></a>
### 20.6 `ModuleList` 创建 N 个独立 Block

源码：

```python
self.layers = nn.ModuleList([
    MiniMindBlock(l, config)
    for l in range(self.num_hidden_layers)
])
```

如果：

```text
num_hidden_layers=3
```

就相当于：

```python
self.layers = nn.ModuleList([
    MiniMindBlock(0, config),
    MiniMindBlock(1, config),
    MiniMindBlock(2, config),
])
```

每调用一次：

```python
MiniMindBlock(...)
```

都会创建一套新的：

```text
Attention 参数
Norm 参数
FFN/MoE 参数
```

所以各层默认不共享权重。

---

<a id="origin-8387"></a>
### 20.7 `range(self.num_hidden_layers)`

最简单：

```python
list(range(3))
```

得到：

```text
[0,1,2]
```

因此 `l` 依次是：

```text
0,1,...,N-1
```

虽然当前 `MiniMindBlock.__init__` 没实际使用 layer_id，但调用接口还是传了进去。

---

<a id="origin-8411"></a>
### 20.8 主干末尾的 RMSNorm

源码：

```python
self.norm = RMSNorm(
    config.hidden_size,
    eps=config.rms_norm_eps
)
```

全部 Block 结束后：

```text
[B,T,H]
```

再进行最后一次 H 维归一化。

---

<a id="origin-8432"></a>
### 20.9 在模型创建时预计算整张 RoPE 表

源码：

```python
freqs_cos, freqs_sin = precompute_freqs_cis(
    dim=config.head_dim,
    end=config.max_position_embeddings,
    rope_base=config.rope_theta,
    rope_scaling=config.rope_scaling
)
```

例如：

```text
D=4
max_position_embeddings=32
```

得到：

```text
freqs_cos [32,4]
freqs_sin [32,4]
```

注意：

> 不是每一层各算一张。

位置编码规则相同，所以整台主干共享这两张表。

---

<a id="origin-8467"></a>
### 20.10 `register_buffer`：不是 Parameter，但要跟模型一起移动设备

源码：

```python
self.register_buffer(
    "freqs_cos",
    freqs_cos,
    persistent=False
)

self.register_buffer(
    "freqs_sin",
    freqs_sin,
    persistent=False
)
```

这是非常值得讲的 PyTorch 概念。

模型中的 Tensor 大致可以分：

```text
Parameter
    需要梯度训练

Buffer
    不训练，但属于模型状态/计算需要

普通临时 Tensor
    只是某次 forward 的中间变量
```

RoPE 的 cos/sin 表：

```text
不需要梯度
```

所以不应该是 Parameter。

但我们又希望：

```python
model.to("cuda")
```

时它们也自动移动到 GPU。

于是很适合注册成 buffer。

---

<a id="origin-8520"></a>
### 20.11 `persistent=False` 是什么意思？

默认 buffer 可能会进入：

```python
state_dict()
```

但这里：

```python
persistent=False
```

表示：

> 这个 buffer 可以跟设备移动，但不需要保存进模型 state_dict。

原因也很自然：

```text
cos/sin 可以根据 config 随时重新计算
```

没有必要让 checkpoint 再存一大份可重建表。

---

<a id="origin-8548"></a>
## 21. `MiniMindModel.forward()`：token ID 开始真正走过所有层

函数签名：

```python
def forward(
    self,
    input_ids,
    attention_mask=None,
    past_key_values=None,
    use_cache=False,
    **kwargs
):
```

这里要注意名字：

```text
past_key_value   单数
```

前面 Attention/Block 指的是“一层”的 K/V。

这里：

```text
past_key_values  复数
```

指的是：

```text
所有层的 cache 列表
```

概念结构：

```text
past_key_values = [
    (K_layer0, V_layer0),
    (K_layer1, V_layer1),
    ...
]
```

---

<a id="origin-8595"></a>
### 21.1 `batch_size, seq_length = input_ids.shape`

输入 token ID 是二维：

```text
[B,T]
```

例如：

```python
input_ids = [[1,5,7]]
```

shape：

```text
[1,3]
```

得到：

```text
batch_size=1
seq_length=3
```

当前函数后面实际上没有直接使用 `batch_size`，但保留下来也有利于表达输入语义。

---

<a id="origin-8626"></a>
### 21.2 `hasattr(past_key_values, 'layers')`

源码：

```python
if hasattr(past_key_values, 'layers'):
    past_key_values = None
```

这是一段兼容处理。

如果调用方传入某种具有：

```text
.layers
```

属性的缓存对象，本实现当前并没有把它转换成自己的列表格式，而是直接清空：

```text
None
```

所以这份讲义中我们始终使用本文件自己返回的：

```text
list[(K,V),...]
```

来理解缓存。

---

<a id="origin-8659"></a>
### 21.3 `past_key_values = past_key_values or [None] * len(self.layers)`

这一行非常 Python。

如果：

```text
past_key_values is None
```

或是空列表等 Falsey 值，则右侧生效：

```python
[None] * len(self.layers)
```

例如两层：

```text
[None, None]
```

表示：

```text
Layer0 没历史 cache
Layer1 没历史 cache
```

如果已经传入非空缓存列表，则保留原值。

---

<a id="origin-8692"></a>
### 21.4 `[None] * N`

最简单：

```python
[None] * 3
```

得到：

```text
[None,None,None]
```

因为 None 是不可变单例，这里不存在像“多个可变 list 引用同一对象”那类陷阱。

---

<a id="origin-8710"></a>
### 21.5 `start_pos`：本轮新 token 的绝对起始位置

源码：

```python
start_pos = (
    past_key_values[0][0].shape[1]
    if past_key_values[0] is not None
    else 0
)
```

为什么只看第 0 层？

正常情况下：

```text
所有层的 cache 序列长度应该一致
```

所以第 0 层就足够得到历史 token 数。

---

<a id="origin-8734"></a>
### 21.6 第一次输入

```text
past_key_values[0] = None
```

于是：

```text
start_pos=0
```

如果本轮 T=3：

```text
位置 = 0,1,2
```

---

<a id="origin-8754"></a>
### 21.7 缓存后续写

假设第 0 层历史 K：

```text
shape = [1,3,Nkv,D]
```

`shape[1]`：

```text
3
```

所以：

```text
start_pos=3
```

本轮一个新 token 的位置就是：

```text
3
```

这正是 RoPE 必须知道的信息。

---

<a id="origin-8784"></a>
### 21.8 Embedding 真正执行

源码：

```python
hidden_states = self.dropout(
    self.embed_tokens(input_ids)
)
```

拆开：

```python
hidden_states = self.embed_tokens(input_ids)
hidden_states = self.dropout(hidden_states)
```

shape：

```text
[B,T]
↓ Embedding
[B,T,H]
↓ Dropout
[B,T,H]
```

从这一刻开始：

```text
整数 token ID
```

已经变成：

```text
浮点 hidden states
```

后续所有 Transformer 计算都处理 hidden states，而不是直接处理 token 编号。

---

<a id="origin-8827"></a>
### 21.9 为什么检查 `self.freqs_cos[0,0] == 0`

源码：

```python
if self.freqs_cos[0, 0] == 0:
```

正常普通 RoPE：

```text
位置0角度=0
cos(0)=1
```

所以：

```text
freqs_cos[0,0]
```

理论上应为 1（考虑当前 attention_factor 默认也是 1）。

如果它变成 0，作者把它当成某种“位置表异常/需要重建”的触发标志。

注意：

> 这并不是一个完整的通用校验机制，只检查一个元素。

读源码时应当按“当前代码实际做什么”理解，而不要额外想象它验证了整张表。

---

<a id="origin-8860"></a>
### 21.10 重新计算位置表

如果触发：

```python
freqs_cos, freqs_sin = precompute_freqs_cis(...)
```

然后：

```python
self.freqs_cos, self.freqs_sin = (
    freqs_cos.to(hidden_states.device),
    freqs_sin.to(hidden_states.device)
)
```

<a id="origin-8877"></a>
#### 21.10.1 `.to(hidden_states.device)`

如果 hidden states 在：

```text
cuda:0
```

则新算出来默认 CPU 的位置表要移到同一设备。

否则：

```text
CPU Tensor × CUDA Tensor
```

会报错。

---

<a id="origin-8897"></a>
### 21.11 切出“本轮真正需要的位置”

源码：

```python
position_embeddings = (
    self.freqs_cos[
        start_pos:start_pos + seq_length
    ],
    self.freqs_sin[
        start_pos:start_pos + seq_length
    ]
)
```

第一次：

```text
start_pos=0
T=3
```

切：

```text
[0:3]
```

也就是位置：

```text
0,1,2
```

缓存后：

```text
start_pos=3
T=1
```

切：

```text
[3:4]
```

只取位置 3。

这就把 KV Cache 和 RoPE 的绝对位置完整对上了。

---

<a id="origin-8950"></a>
### 21.12 `presents = []`

创建一个普通空 Python list。

后面每一层处理完，都会：

```python
presents.append(present)
```

最后得到：

```text
[
 cache_layer0,
 cache_layer1,
 ...
]
```

这就是下一轮传回来的：

```text
past_key_values
```

---

<a id="origin-8978"></a>
### 21.13 `zip(self.layers, past_key_values)`

源码：

```python
for layer, past_key_value in zip(
    self.layers,
    past_key_values
):
```

`zip` 最简单例子：

```python
A = ["a","b","c"]
B = [1,2,3]

for x,y in zip(A,B):
    print(x,y)
```

输出：

```text
a 1
b 2
c 3
```

这里就是：

```text
Layer0 ↔ Cache0
Layer1 ↔ Cache1
...
```

注意 Python `zip` 会以较短的序列为准停止。

所以如果调用方错误地只传了部分层缓存：

```text
可能导致后面的层根本不循环
```

这份代码没有在这里额外做长度断言，因此调用者应保证缓存列表长度正确。

---

<a id="origin-9027"></a>
### 21.14 调用当前 Block

源码：

```python
hidden_states, present = layer(
    hidden_states,
    position_embeddings,
    past_key_value=past_key_value,
    use_cache=use_cache,
    attention_mask=attention_mask
)
```

第一次循环：

```text
hidden_states = Embedding 输出
```

第二层开始：

```text
hidden_states = 上一层 Block 输出
```

所以数据流：

```text
Embedding
→ Layer0
→ Layer1
→ Layer2
→ ...
```

不是多层并行。

---

<a id="origin-9067"></a>
### 21.15 为什么所有层共享同一段 `position_embeddings`？

因为 token 的绝对位置不因 Transformer 层数而改变。

例如新 token 位于位置 3：

```text
Layer0 中它还是位置3
Layer1 中它还是位置3
...
```

所以所有层可以使用同一段：

```text
cos[3], sin[3]
```

但各层 Q/K 内容不同，所以旋转后的结果仍不同。

---

<a id="origin-9089"></a>
### 21.16 为什么每层的 `past_key_value` 又不同？

因为每层 hidden state 不同。

第 0 层的 K：

```text
由第0层输入投影得到
```

第 1 层的 K：

```text
由第0层输出经过第1层 K 投影得到
```

所以各层 cache 必须分开保存。

结构：

```text
Layer0: K0_history, V0_history
Layer1: K1_history, V1_history
...
```

绝对不能只保存“一份全模型 K/V”。

---

<a id="origin-9119"></a>
### 21.17 `presents.append(present)`

如果：

```text
use_cache=True
```

每个 `present` 是：

```text
(K,V)
```

如果：

```text
use_cache=False
```

Attention 返回：

```text
None
```

但这里仍然 append。

所以最终：

```text
presents
```

长度仍然等于层数，只是元素可能全部为 None。

---

<a id="origin-9157"></a>
### 21.18 全部层后 Final Norm

```python
hidden_states = self.norm(hidden_states)
```

shape：

```text
[B,T,H]
```

不变。

到这里主干处理完成。

---

<a id="origin-9175"></a>
### 21.19 汇总各层 MoE 辅助损失

源码：

```python
aux_loss = sum(
    [
        l.mlp.aux_loss
        for l in self.layers
        if isinstance(l.mlp, MOEFeedForward)
    ],
    hidden_states.new_zeros(1).squeeze()
)
```

这一行包含三个知识点：

```text
isinstance
带条件的 list comprehension
sum 的 start 参数
```

---

<a id="origin-9200"></a>
### 21.20 `isinstance(obj, Class)`

最简单：

```python
isinstance(3, int)
```

得到：

```text
True
```

这里：

```python
isinstance(l.mlp, MOEFeedForward)
```

只挑出：

```text
mlp 真的是 MoE 的层
```

普通 FeedForward 层没有 `aux_loss` 属性，不应该去访问。

---

<a id="origin-9230"></a>
### 21.21 带 if 的列表推导式

```python
[
    l.mlp.aux_loss
    for l in self.layers
    if isinstance(l.mlp, MOEFeedForward)
]
```

相当于：

```python
losses = []
for l in self.layers:
    if isinstance(l.mlp, MOEFeedForward):
        losses.append(l.mlp.aux_loss)
```

---

<a id="origin-9251"></a>
### 21.22 `sum(iterable, start)`

Python：

```python
sum([1,2,3], 10)
```

得到：

```text
16
```

这里 start 是：

```python
hidden_states.new_zeros(1).squeeze()
```

也就是与 hidden_states 同 device/dtype 的 0 标量 Tensor。

为什么不直接用默认 Python 整数 0？

因为这样即使没有 MoE 层，也能保证：

```text
aux_loss 是 Tensor
并且 device/dtype 合适
```

---

<a id="origin-9284"></a>
### 21.23 `return hidden_states, presents, aux_loss`

到这里 `MiniMindModel` 返回：

```text
hidden_states
    [B,T,H]

presents
    每一层的 KV cache / None

aux_loss
    MoE 辅助损失标量
```

特别注意：

```text
这里没有 logits
没有 CrossEntropy
```

所以 `MiniMindModel` 只是 backbone。

---

<a id="origin-9310"></a>
### 21.24 首次输入完整追踪

假设：

```text
input_ids=[[1,5,7]]
B=1,T=3,H=8
layers=2
Nkv=1,D=4
use_cache=True
```

步骤：

```text
input_ids
[1,3]

↓ Embedding

hidden_states
[1,3,8]

↓ Layer0

hidden_states
[1,3,8]
cache0 K/V
[1,3,1,4]

↓ Layer1

hidden_states
[1,3,8]
cache1 K/V
[1,3,1,4]

↓ Final RMSNorm

hidden_states
[1,3,8]
```

返回：

```text
presents = [
    (K0,V0),
    (K1,V1)
]
```

---

<a id="origin-9364"></a>
### 21.25 缓存后单 token 续写

下一轮只输入：

```text
[[9]]
```

shape：

```text
[1,1]
```

历史长度：

```text
start_pos=3
```

Embedding：

```text
[1,1,8]
```

RoPE 切：

```text
position 3
```

Layer0：

```text
输入新 token [1,1,8]
+
Layer0 历史 KV 长3
→ cache 长4
```

Layer1 同理。

最终只返回：

```text
新 token 的 hidden state [1,1,8]
```

不会重复返回前三个 token 的 hidden states。

---

<a id="origin-9417"></a>
## 22. `MiniMindForCausalLM`：在 Transformer 主干上再加“词表预测头”

现在进入最外层：

```python
class MiniMindForCausalLM(
    PreTrainedModel,
    GenerationMixin
):
```

这是用户真正更常直接实例化和调用的完整语言模型。

它在：

```text
MiniMindModel
```

上再增加：

```text
lm_head
loss
自定义 generate
```

整体：

```text
input_ids
   ↓
MiniMindModel
   ↓
hidden_states [B,T,H]
   ↓
lm_head
   ↓
logits [B,T,V]
   ↓
训练：CrossEntropy
或
生成：选下一个 token
```

---

<a id="origin-9464"></a>
### 22.1 `config_class = MiniMindConfig`

源码：

```python
config_class = MiniMindConfig
```

这是类属性。

作用是告诉 Transformers 框架：

> 这个模型对应的配置类型是 MiniMindConfig。

注意这里只是声明关联，不代表自动完成所有 AutoModel 注册流程。

---

<a id="origin-9482"></a>
### 22.2 `_tied_weights_keys`

源码：

```python
_tied_weights_keys = {
    "lm_head.weight": "model.embed_tokens.weight"
}
```

这是一个字典。

表达：

```text
输出 lm_head 的 weight
和
输入 embedding 的 weight
存在共享关系
```

后面构造函数还会显式真正赋成同一个 Parameter。

---

<a id="origin-9507"></a>
### 22.3 构造函数参数默认 `config=None`

```python
def __init__(self, config: MiniMindConfig = None):
```

允许：

```python
model = MiniMindForCausalLM()
```

也允许：

```python
model = MiniMindForCausalLM(cfg)
```

---

<a id="origin-9527"></a>
### 22.4 `self.config = config or MiniMindConfig()`

如果调用者没传：

```text
config=None
```

就创建默认：

```python
MiniMindConfig()
```

如果传了 cfg，就使用它。

---

<a id="origin-9545"></a>
### 22.5 为什么这里 `super().__init__(self.config)` 带参数？

源码：

```python
super().__init__(self.config)
```

父类是：

```text
PreTrainedModel
```

它的初始化需要 config 对象。

这和普通 `nn.Module` 的：

```python
super().__init__()
```

不同。

所以不要机械记忆“super 永远不传参数”。

应该看父类构造函数接口。

---

<a id="origin-9575"></a>
### 22.6 创建主干

```python
self.model = MiniMindModel(self.config)
```

现在完整模型内部出现：

```text
model.model.embed_tokens
model.model.layers
model.model.norm
```

注意属性名有点绕：

```text
最外层变量可能叫 model
它里面又有 self.model
```

比如：

```python
lm = MiniMindForCausalLM(cfg)
```

则：

```python
lm.model
```

才是 `MiniMindModel` 主干。

---

<a id="origin-9612"></a>
### 22.7 `lm_head = nn.Linear(H,V,bias=False)`

源码：

```python
self.lm_head = nn.Linear(
    self.config.hidden_size,
    self.config.vocab_size,
    bias=False
)
```

如果：

```text
H=8
V=16
```

就是：

```text
8 → 16
```

对于每一个 token hidden state：

```text
8 个特征
↓
16 个候选 token 分数
```

所以：

```text
[B,T,8]
→
[B,T,16]
```

这 16 个数叫：

```text
logits
```

还不是概率。

---

<a id="origin-9663"></a>
### 22.8 Weight Tying：输入词向量表和输出词表头共用参数

源码：

```python
if self.config.tie_word_embeddings:
    self.model.embed_tokens.weight = self.lm_head.weight
```

这是“同一个 Parameter 对象”，不是复制一次数值。

可以做最小实验：

```python
print(
    self.model.embed_tokens.weight
    is
    self.lm_head.weight
)
```

开启后应该是同一引用。

---

<a id="origin-9688"></a>
### 22.9 为什么 shape 恰好能共享？

Embedding 参数：

```text
[V,H]
```

Linear(H→V) 的 weight：

```text
[V,H]
```

shape 完全一致。

输入时：

```text
根据 token id 取某一行
```

输出时：

```text
hidden state 与每一行做点积得到词表分数
```

所以同一张矩阵可以承担两种角色。

---

<a id="origin-9720"></a>
### 22.10 `self.post_init()`

源码：

```python
self.post_init()
```

这是 Transformers `PreTrainedModel` 框架提供的构造收尾逻辑之一。

它通常与：

```text
权重初始化
框架内部初始化流程
```

有关。

教学重点不是背 `post_init` 内部实现，而是知道：

> `MiniMindForCausalLM` 不只是裸 `nn.Module`，它还接入了 Transformers 的 PreTrainedModel 生命周期。

---

<a id="origin-9745"></a>
## 23. `MiniMindForCausalLM.forward()`：完整的一次训练/推理前向

函数签名：

```python
def forward(
    self,
    input_ids,
    attention_mask=None,
    past_key_values=None,
    use_cache=False,
    logits_to_keep=0,
    labels=None,
    **kwargs
):
```

这个函数是整个文件最重要的“总入口”之一。

它做三件事：

```text
1. 调 MiniMindModel 得 hidden states
2. 调 lm_head 得 logits
3. 如果有 labels，计算 next-token CrossEntropy
```

---

<a id="origin-9774"></a>
### 23.1 先调用主干

源码：

```python
hidden_states, past_key_values, aux_loss = self.model(
    input_ids,
    attention_mask,
    past_key_values,
    use_cache,
    **kwargs
)
```

这里 `self.model(...)` 之所以可以像函数一样调用，是因为它继承 `nn.Module`。

PyTorch 会走：

```text
Module.__call__
→ forward(...)
```

所以：

```python
self.model(...)
```

最终执行的是：

```python
MiniMindModel.forward(...)
```

---

<a id="origin-9811"></a>
### 23.2 为什么一般不手动写 `self.model.forward(...)`？

PyTorch 推荐：

```python
self.model(...)
```

因为 `nn.Module.__call__` 周围还会处理 hooks、autocast 等模块机制。

直接调用 `.forward()` 可能绕开这些框架行为。

---

<a id="origin-9825"></a>
### 23.3 `logits_to_keep`：为什么生成时可以只投影最后几个位置

源码：

```python
slice_indices = (
    slice(-logits_to_keep, None)
    if isinstance(logits_to_keep, int)
    else logits_to_keep
)
```

这里先认识：

```python
slice(start, stop)
```

例如：

```python
x[-1:]
```

可以表示为：

```python
x[slice(-1, None)]
```

---

<a id="origin-9857"></a>
### 23.4 `logits_to_keep=1`

```python
slice(-1, None)
```

表示：

```text
只取最后一个位置
```

于是：

```text
hidden_states [B,T,H]
↓ 只取最后位置
[B,1,H]
↓ lm_head
[B,1,V]
```

生成时通常只需要最后位置预测“下一个 token”，所以能省输出投影计算。

---

<a id="origin-9883"></a>
### 23.5 为什么 `logits_to_keep=0` 反而是保留全部？

Python 中：

```text
-0 == 0
```

所以：

```python
slice(-0, None)
```

等价于：

```python
slice(0, None)
```

也就是：

```text
从第0位置取到末尾
```

因此这里巧妙地让默认 0 表示“全部保留”。

---

<a id="origin-9913"></a>
### 23.6 非整数时按原样作为索引

```python
else logits_to_keep
```

说明作者也允许调用方传某种可用于：

```python
hidden_states[:, slice_indices, :]
```

的索引对象。

但常规教学场景只关注整数 0 或 1 即可。

---

<a id="origin-9931"></a>
### 23.7 `lm_head` 真正得到 logits

源码：

```python
logits = self.lm_head(
    hidden_states[:, slice_indices, :]
)
```

例如：

```text
hidden_states [1,4,8]
V=16
logits_to_keep=0
```

则：

```text
logits [1,4,16]
```

每个位置都有 16 个词表候选分数。

---

<a id="origin-9959"></a>
### 23.8 `loss = None`

```python
loss = None
```

先默认：

```text
这次没有监督损失
```

为什么不是 0？

因为：

```text
None = 没有计算 loss
0    = 计算过，而且结果恰好是 0
```

语义不同。

推理通常不传 labels，所以返回 `loss=None`。

---

<a id="origin-9986"></a>
### 23.9 `if labels is not None`

特别注意：

这份实现不是：

```python
if self.training:
```

才算 loss。

而是：

```text
只要 labels 被提供
就计算 loss
```

所以即使：

```python
model.eval()
```

但传了 labels，仍会计算交叉熵。

反过来即使：

```python
model.train()
```

但没传 labels，loss 仍是 None。

---

<a id="origin-10023"></a>
### 23.10 自回归训练最关键的 shift

源码：

```python
x, y = (
    logits[..., :-1, :].contiguous(),
    labels[..., 1:].contiguous()
)
```

这就是 next-token training 的核心。

假设：

```text
input_ids = labels = [1,5,7,2]
```

logits 有 4 个位置：

```text
logit0
logit1
logit2
logit3
```

`logits[..., :-1, :]`：

```text
只取 logit0,1,2
```

`labels[..., 1:]`：

```text
只取 5,7,2
```

配对：

```text
logit0 → label5
logit1 → label7
logit2 → label2
```

也就是：

```text
看 [1]       预测 5
看 [1,5]     预测 7
看 [1,5,7]   预测 2
```

最后位置 logit3 没有“输入内部的下一个 token”作为标签，所以不参与这次 loss。

---

<a id="origin-10083"></a>
### 23.11 `...` 在这里再次出现

```python
logits[..., :-1, :]
```

logits 常见：

```text
[B,T,V]
```

所以等价于：

```python
logits[:, :-1, :]
```

保留：

```text
所有 batch
除了最后一个 token 位置
所有 vocab 维
```

labels：

```python
labels[..., 1:]
```

常见等价：

```python
labels[:, 1:]
```

---

<a id="origin-10123"></a>
### 23.12 `.contiguous()` 为什么出现？

切片、transpose 等操作可能产生非连续内存布局的 Tensor view。

后面马上要：

```python
.view(...)
```

而 `.view()` 对内存连续性要求比较严格。

所以：

```python
.contiguous()
```

确保得到连续布局，方便后续 flatten。

核心关系如下：

> 切片后为了安全 `view()`，作者先把 Tensor 整理成连续内存。

---

<a id="origin-10149"></a>
### 23.13 `x.view(-1, x.size(-1))`

这里：

```text
x.shape=[B,T-1,V]
```

`x.size(-1)`：

```text
V
```

所以：

```python
x.view(-1, V)
```

变成：

```text
[B*(T-1), V]
```

也就是把所有 batch、所有训练位置合并成一张：

```text
N 个样本 × V 个类别分数
```

的二维表。

---

<a id="origin-10185"></a>
### 23.14 `y.view(-1)`

labels：

```text
[B,T-1]
```

flatten 成：

```text
[B*(T-1)]
```

每一项就是对应样本的正确 token ID。

---

<a id="origin-10203"></a>
### 23.15 `F.cross_entropy(...)`

源码：

```python
loss = F.cross_entropy(
    x.view(-1, x.size(-1)),
    y.view(-1),
    ignore_index=-100
)
```

输入要求：

```text
logits: [N,V]
target: [N]
```

其中 target 每个元素是：

```text
0～V-1 的正确类别编号
```

例如某位置词表概率正确 token 是 7。

CrossEntropy 会鼓励：

```text
logit[7] 相对其他候选更大
```

---

<a id="origin-10238"></a>
### 23.16 `ignore_index=-100`

如果某个 label 是：

```text
-100
```

该位置不计入 loss。

例如：

```text
labels=[-100,-100,7,2]
```

shift 后目标：

```text
[-100,7,2]
```

第一个位置忽略，只监督后两个。

注意：

> label=-100 只是“不算这个位置的 loss”，并不代表输入 token 从模型上下文中消失。

只要它仍在 `input_ids` 且 attention mask 允许，模型仍然能读取它。

---

<a id="origin-10270"></a>
### 23.17 一个最简单的 CrossEntropy 数值例子

假设某位置正确 token 概率：

```text
0.5
```

负对数似然：

```math
-\log(0.5)\approx0.6931
```

如果三个有效位置正确概率都恰好 0.5，默认 mean reduction 的平均 loss 仍约：

```text
0.6931
```

---

<a id="origin-10292"></a>
### 23.18 `MoeCausalLMOutputWithPast(...)`

源码：

```python
return MoeCausalLMOutputWithPast(
    loss=loss,
    aux_loss=aux_loss,
    logits=logits,
    past_key_values=past_key_values,
    hidden_states=hidden_states
)
```

不是简单 tuple，而是带字段名的输出对象。

外面可以：

```python
outputs = model(...)

outputs.loss
outputs.logits
outputs.past_key_values
outputs.hidden_states
outputs.aux_loss
```

这样比：

```python
outputs[0]
outputs[1]
```

可读性高很多。

---

<a id="origin-10331"></a>
### 23.19 一个完整训练 forward 的故事

假设：

```python
input_ids = torch.tensor([[1,5,7,2]])
labels = input_ids.clone()
```

教学配置：

```text
B=1,T=4,H=8,V=16,layers=2
```

第一步：主干

```text
[1,4]
→ Embedding
[1,4,8]
→ 2个Block
[1,4,8]
→ Final Norm
[1,4,8]
```

第二步：lm_head

```text
[1,4,8]
→
[1,4,16]
```

第三步：shift

```text
logits[:, :-1, :]
→ [1,3,16]

labels[:,1:]
→ [1,3]
```

第四步：flatten

```text
[3,16]
[3]
```

第五步：CrossEntropy

```text
3 个 next-token 目标求平均损失
```

这就是“一次 forward 为什么可以同时训练多个位置”。

---

<a id="origin-10393"></a>
### 23.20 到这里训练故事已经闭环

如果只做训练，这份文件的核心故事已经完整：

```text
Token IDs
→ Embedding
→ N×Transformer Block
→ Final Norm
→ LM Head
→ Logits
→ Shift
→ CrossEntropy
→ Loss
```

下一章 `generate()` 并没有发明一个新的 Transformer。

它做的事情是：

> 反复调用我们刚刚讲完的 `forward()`，每一轮只选出一个新的 token，再把它接回序列继续。


<a id="origin-10416"></a>
## 24. `generate()`：不是另一个模型，而是“反复调用 forward + 每轮追加一个 token”

现在进入文件最后一个大函数：

```python
@torch.inference_mode()
def generate(...):
```

先把最重要的误区消掉：

> `generate()` 并没有再实现一套 Attention、FFN 或 Transformer。

真正的神经网络计算仍然是：

```python
self.forward(...)
```

`generate()` 负责的是外层控制逻辑：

```text
已有 token
   ↓
forward
   ↓
最后位置 logits
   ↓
temperature / penalty / top-k / top-p
   ↓
选 1 个 token
   ↓
拼到 input_ids 后面
   ↓
下一轮
```

如果开启 KV Cache：

```text
第一轮：整段 prompt 进 forward
后续轮：只把“尚未缓存的新后缀”送进 forward
```

---

<a id="origin-10462"></a>
### 24.1 装饰器：`@torch.inference_mode()`

源码：

```python
@torch.inference_mode()
```

这是 Python decorator。

可以把：

```python
@decorator
def f():
    ...
```

粗略理解为：

```python
f = decorator(f)
```

这里 `torch.inference_mode()` 表示：

> 调用整个 generate 期间关闭梯度记录和训练反向图相关开销。

因为生成只做推理，不需要：

```text
backward()
grad
optimizer.step()
```

---

<a id="origin-10500"></a>
### 24.2 `inference_mode()` 不等于 `eval()`

这是非常重要的区别。

`inference_mode()`：

```text
关闭梯度相关机制
```

`model.eval()`：

```text
把 Dropout 等模块切到评估行为
```

所以源码注释强调：

> `generate()` 自己不会自动调用 `eval()`。

正确使用通常应先：

```python
model.eval()
result = model.generate(...)
```

否则模型仍可能处于 training mode，Dropout 行为仍是训练态。

---

<a id="origin-10531"></a>
### 24.3 generate 的全部参数先翻译成人话

函数：

```python
def generate(
    self,
    inputs=None,
    attention_mask=None,
    max_new_tokens=8192,
    temperature=0.85,
    top_p=0.85,
    top_k=50,
    eos_token_id=2,
    streamer=None,
    use_cache=True,
    num_return_sequences=1,
    do_sample=True,
    repetition_penalty=1.0,
    **kwargs
):
```

对应：

```text
inputs
    初始 token IDs

attention_mask
    哪些上下文位置有效

max_new_tokens
    最多新增多少 token

temperature
    logits 温度缩放

top_p
    nucleus sampling 阈值

top_k
    最多保留高分候选

eos_token_id
    结束 token

streamer
    流式输出接收器

use_cache
    是否启用 KV Cache

num_return_sequences
    把输入复制多少份进行生成

do_sample
    True=按概率采样
    False=argmax 贪心

repetition_penalty
    对已经出现过的 token 降低分数

**kwargs
    其它参数，例如 input_ids、past_key_values、logits_to_keep、return_kv
```

---

<a id="origin-10600"></a>
### 24.4 第一行：优先从 kwargs 取 `input_ids`

源码：

```python
input_ids = kwargs.pop("input_ids", inputs).repeat(
    num_return_sequences,
    1
)
```

这行至少要拆成三个知识点。

---

<a id="origin-10615"></a>
### 24.5 `dict.pop(key, default)`

最小例子：

```python
d = {"a": 10, "b": 20}
x = d.pop("a", 0)
```

得到：

```text
x=10
```

而 d 变成：

```text
{"b":20}
```

也就是说 `pop` 不仅取值，还从字典删除。

如果 key 不存在：

```python
d.pop("c", 99)
```

得到默认：

```text
99
```

这里：

```python
kwargs.pop("input_ids", inputs)
```

表示：

```text
如果 kwargs 里显式有 input_ids
    优先用它，并从 kwargs 删除
否则
    使用 inputs
```

为什么删除？

因为后面：

```python
self.forward(..., **kwargs)
```

不希望 `input_ids` 又通过 kwargs 重复传一次。

---

<a id="origin-10677"></a>
### 24.6 `.repeat(num_return_sequences, 1)`

假设：

```text
input_ids = [[1,5,7]]
shape=[1,3]
```

如果：

```text
num_return_sequences=2
```

则：

```python
.repeat(2,1)
```

得到：

```text
[
 [1,5,7],
 [1,5,7]
]
```

shape：

```text
[2,3]
```

如果原 batch 有 A/B 两条：

```text
[A,B]
```

`repeat(2,1)` 的顺序是：

```text
[A,B,A,B]
```

不是：

```text
[A,A,B,B]
```

---

<a id="origin-10733"></a>
### 24.7 为什么复制输入不一定得到不同结果？

如果：

```text
do_sample=False
```

而模型处于 `eval()`：

```text
相同输入
→ 相同 logits
→ 同一个 argmax
```

两份通常会生成完全一样。

要产生不同序列通常需要：

```text
采样随机性
```

或者其它扰动。

---

<a id="origin-10761"></a>
### 24.8 attention_mask 同样复制

源码：

```python
attention_mask = (
    attention_mask.repeat(num_return_sequences, 1)
    if attention_mask is not None
    else None
)
```

如果输入复制了两份，mask 也必须按完全相同顺序复制。

否则：

```text
第 i 行 input
```

和：

```text
第 i 行 mask
```

会错位。

---

<a id="origin-10791"></a>
### 24.9 取外部 cache

源码：

```python
past_key_values = kwargs.pop(
    "past_key_values",
    None
)
```

如果调用者想“从已有 KV Cache 继续生成”，可以通过 kwargs 传入。

同样使用 `pop` 删除，避免后面重复传参。

---

<a id="origin-10808"></a>
### 24.10 `finished`：每一行是不是已经生成 EOS

源码：

```python
finished = torch.zeros(
    input_ids.shape[0],
    dtype=torch.bool,
    device=input_ids.device
)
```

假设当前 batch 复制后有 3 行：

```text
input_ids.shape[0] = 3
```

得到：

```text
[False,False,False]
```

dtype：

```text
bool
```

device 与 input 一致。

它用于记录：

```text
第0条是否结束
第1条是否结束
第2条是否结束
```

---

<a id="origin-10850"></a>
### 24.11 streamer 先接收 prompt

源码：

```python
if streamer:
    streamer.put(input_ids.cpu())
```

如果调用方没有传 streamer：

```text
None → 不执行
```

如果传了对象，就调用它的：

```python
put(...)
```

<a id="origin-10871"></a>
#### 24.11.1 为什么 `.cpu()`？

streamer 往往负责：

```text
token 解码
终端/界面显示
```

通常不需要 GPU Tensor。

所以先移回 CPU。

具体 streamer 如何显示文字，不属于这个文件实现。

---

<a id="origin-10888"></a>
### 24.12 生成循环

源码：

```python
for _ in range(max_new_tokens):
```

如果：

```text
max_new_tokens=5
```

最多执行 5 轮。

每一轮最多为 batch 中每一行追加：

```text
1 个 token
```

所以这是：

```text
新增 token 数上限
```

不是总序列长度上限。

如果 prompt 已经 100 token：

```text
max_new_tokens=20
```

最多返回：

```text
120 token
```

当然也可能因为 EOS 提前停止。

---

<a id="origin-10934"></a>
### 24.13 `past_len`：现在有多少 token 已经存在于 cache 中

源码：

```python
past_len = (
    past_key_values[0][0].shape[1]
    if past_key_values
    else 0
)
```

第一次：

```text
past_key_values=None
```

所以：

```text
past_len=0
```

如果 cache 已有前三个 token：

```text
K_layer0.shape=[B,3,Nkv,D]
```

则：

```text
past_len=3
```

---

<a id="origin-10972"></a>
### 24.14 `if past_key_values` 与 `is not None` 的区别

这里使用：

```python
if past_key_values
```

Python 会做 truth-value 判断。

```text
None → False
空 list → False
非空 list → True
```

所以空 list 也会当成“没有 cache”。

---

<a id="origin-10992"></a>
### 24.15 generate 最核心的一行：只把未缓存后缀送进 forward

源码：

```python
outputs = self.forward(
    input_ids[:, past_len:],
    attention_mask,
    past_key_values,
    use_cache=use_cache,
    **kwargs
)
```

这一行就是 KV Cache 在外层生成循环里的关键。

---

<a id="origin-11010"></a>
### 24.16 第一轮

初始：

```text
input_ids=[[1,5,7]]
past_len=0
```

切片：

```python
input_ids[:,0:]
```

还是：

```text
[[1,5,7]]
```

所以第一轮整段 prompt 进入 forward。

这会建立：

```text
1,5,7
```

所有层的 K/V Cache。

---

<a id="origin-11043"></a>
### 24.17 第二轮

假设第一轮生成 9，完整 `input_ids` 已变：

```text
[[1,5,7,9]]
```

但是 cache 长度还是 3，因为 9 是第一轮 forward 结束以后才选出来的。

所以：

```text
past_len=3
```

切：

```python
input_ids[:,3:]
```

得到：

```text
[[9]]
```

于是第二轮只把 9 送入 forward。

同时传入：

```text
1,5,7 的历史 KV
```

Attention 内部再拼成：

```text
K1,K5,K7,K9
V1,V5,V7,V9
```

---

<a id="origin-11088"></a>
### 24.18 为什么 `attention_mask` 不是也切成后缀？

源码传的是完整：

```python
attention_mask
```

而不是：

```python
attention_mask[:, past_len:]
```

因为 Attention 的 Key 长度：

```text
S = 历史 + 当前
```

padding mask 必须覆盖所有 Key 位置。

所以即使 forward 只收到 1 个新 token，mask 仍需描述整个上下文。

---

<a id="origin-11114"></a>
### 24.19 forward 以后先扩展 mask

源码：

```python
attention_mask = (
    torch.cat([
        attention_mask,
        attention_mask.new_ones(
            attention_mask.shape[0],
            1
        )
    ], -1)
    if attention_mask is not None
    else None
)
```

为什么是 forward 后？

因为这一轮 forward 对应的上下文长度还是“当前已有 input_ids”。

马上要追加一个新 token，所以为“下一轮”提前把 mask 加一列 1。

---

<a id="origin-11140"></a>
### 24.20 `attention_mask.new_ones(...)`

如果 mask：

```text
dtype=int64
device=cuda:0
```

`new_ones` 创建的新 Tensor 自动跟随：

```text
dtype
device
```

假设：

```text
mask shape=[2,4]
```

创建：

```text
[2,1]
```

全 1。

再 cat：

```text
[2,5]
```

新增 token 默认认为是有效位置。

---

<a id="origin-11180"></a>
### 24.21 只取最后位置 logits

源码：

```python
logits = outputs.logits[:, -1, :] / temperature
```

假设：

```text
outputs.logits=[B,T,V]
```

`[:, -1, :]`：

```text
取所有 batch
取最后一个 token 位置
取全部 vocab
```

得到：

```text
[B,V]
```

为什么只要最后位置？

因为我们这一轮只需要回答：

> 当前完整上下文之后，下一个 token 是谁？

以前位置的预测已经没有新的用途。

---

<a id="origin-11218"></a>
### 24.22 Temperature：除，不是乘

```python
logits = logits / temperature
```

假设：

```text
logits=[2,1,0]
```

<a id="origin-11230"></a>
#### 24.22.1 temperature=0.5

```text
[4,2,0]
```

softmax 更尖锐，更偏向最高项。

<a id="origin-11238"></a>
#### 24.22.2 temperature=2

```text
[1,0.5,0]
```

softmax 更平坦，更随机。

所以：

```text
T < 1 → 更确定
T > 1 → 更发散
```

温度应为正数。

特别注意：

如果最后 `do_sample=False` 用 argmax，正温度缩放并不会改变候选排序，因此通常不会改变 argmax 结果。

---

<a id="origin-11261"></a>
### 24.23 Repetition Penalty 分支

源码：

```python
if repetition_penalty != 1.0:
```

当：

```text
penalty=1
```

完全跳过。

否则对每一行 batch 分别处理。

---

<a id="origin-11281"></a>
### 24.24 为什么 `for i in range(input_ids.shape[0])`

每条样本历史出现过的 token 不同。

所以必须逐行找：

```text
这一条自己出现过哪些 token
```

不能全 batch 共用一组。

---

<a id="origin-11295"></a>
### 24.25 `torch.unique(input_ids[i])`

源码：

```python
seen = torch.unique(input_ids[i])
```

假设某行：

```text
[1,5,7,5,5,9]
```

unique 后：

```text
[1,5,7,9]
```

所以 token 5 即使出现 3 次，在这一轮 penalty 中也只处理一次。

---

<a id="origin-11319"></a>
### 24.26 高级索引 `logits[i, seen]`

如果：

```text
seen=[1,5,7,9]
```

则：

```python
score = logits[i, seen]
```

一次取出当前样本词表中这些 token 的分数。

---

<a id="origin-11337"></a>
### 24.27 `torch.where`：正 logits 和负 logits 为什么处理不同？

源码：

```python
logits[i, seen] = torch.where(
    score > 0,
    score / repetition_penalty,
    score * repetition_penalty
)
```

`torch.where(condition, A, B)`：

```text
condition=True → 取 A
condition=False → 取 B
```

假设 penalty=1.2。

正分数：

```text
6 → 6/1.2 = 5
```

分数下降。

负分数：

```text
-2 → -2×1.2=-2.4
```

也变得更低。

所以无论正负，出现过的 token 都被压低。

---

<a id="origin-11378"></a>
### 24.28 Top-K：只保留分数最高的一批候选

源码：

```python
if top_k > 0:
    logits[
        logits < torch.topk(logits, top_k)[0][..., -1, None]
    ] = -float('inf')
```

这是又一条应该拆开的代码。

```python
top_values = torch.topk(logits, top_k)[0]
threshold = top_values[..., -1, None]
mask = logits < threshold
logits[mask] = -float("inf")
```

---

<a id="origin-11400"></a>
### 24.29 `torch.topk(...)[0]`

`torch.topk` 返回：

```text
(values, indices)
```

`[0]` 取 values。

例如：

```text
logits=[8,6,1,0]
k=2
```

values：

```text
[8,6]
```

---

<a id="origin-11425"></a>
### 24.30 `[..., -1, None]`

从 top-k values 中取最后一个，也就是第 k 大值：

```text
6
```

`None` 再保留一个长度为 1 的维度，方便与整个 `[B,V]` logits 广播比较。

所以 threshold：

```text
[B,1]
```

---

<a id="origin-11443"></a>
### 24.31 布尔索引直接写回 `-inf`

```python
logits[logits < threshold] = -float('inf')
```

例如：

```text
[8,6,1,0]
```

阈值 6：

```text
[8,6,-inf,-inf]
```

softmax 后：

```text
-inf → 概率 0
```

注意边界：

```text
小于 threshold 才删除
```

如果多个候选恰好与第 k 大分数同分，可能保留超过 k 个。

---

<a id="origin-11477"></a>
### 24.32 Top-P：按累计概率保留最小高概率集合

源码：

```python
if top_p < 1.0:
```

`top_p=1`：

```text
不做 nucleus 过滤
```

`top_p<1`：

```text
按概率累计到阈值附近，只保留高概率头部候选
```

---

<a id="origin-11499"></a>
### 24.33 先排序

源码：

```python
sorted_logits, sorted_indices = torch.sort(
    logits,
    descending=True
)
```

假设原词表编号：

```text
id0  id1  id2  id3
1.0  8.0  0.0  6.0
```

排序后 values：

```text
[8,6,1,0]
```

indices：

```text
[1,3,0,2]
```

indices 非常重要，因为最后要还原到原词表位置。

---

<a id="origin-11533"></a>
### 24.34 `softmax → cumsum → > top_p`

源码：

```python
mask = torch.cumsum(
    torch.softmax(sorted_logits, dim=-1),
    dim=-1
) > top_p
```

假设排序后概率：

```text
[0.60,0.25,0.10,0.05]
```

累计：

```text
[0.60,0.85,0.95,1.00]
```

如果：

```text
top_p=0.8
```

比较 `> 0.8`：

```text
[False,True,True,True]
```

如果直接按这个 mask 删除，会只保留第一项 0.60，总概率还没达到 0.8。

所以后面还要右移 mask。

---

<a id="origin-11574"></a>
### 24.35 mask 右移：保留“第一个越界候选”

源码：

```python
mask[..., 1:], mask[..., 0] = (
    mask[..., :-1].clone(),
    0
)
```

原：

```text
[F,T,T,T]
```

右移后：

```text
[F,F,T,T]
```

所以保留前两项：

```text
0.60 + 0.25 = 0.85
```

这才形成累计概率至少跨过 p 的候选集合。

---

<a id="origin-11607"></a>
### 24.36 为什么 `.clone()`？

因为左侧和右侧都是同一个 Tensor 的重叠切片。

如果不 clone，原地写入可能影响随后还要读取的源数据。

`clone()` 先复制右侧旧值，避免重叠赋值冲突。

---

<a id="origin-11617"></a>
### 24.37 `mask[...,0] = 0`

强制第一项永远不删。

即使数值/阈值有极端情况，也至少保留一个候选，避免所有 logits 都变 `-inf`。

---

<a id="origin-11625"></a>
### 24.38 `scatter`：排序后的 mask 如何还原回原 token ID

源码：

```python
logits[
    mask.scatter(1, sorted_indices, mask)
] = -float('inf')
```

这是 top-p 最难理解的一行。

排序空间里的 mask：

```text
第0名是否删
第1名是否删
第2名是否删
...
```

但原 logits 是按：

```text
词表 token id 0,1,2,...
```

排列。

所以必须根据：

```text
sorted_indices
```

把“排名位置上的删除标记”散射回原 token id 位置。

`scatter` 就是在做这个还原。

---

<a id="origin-11666"></a>
### 24.39 一个简化 scatter 例子

假设：

```text
sorted_indices=[1,3,0,2]
```

排序后的删除 mask：

```text
[False,False,True,True]
```

意思：

```text
排名0 token id1 保留
排名1 token id3 保留
排名2 token id0 删除
排名3 token id2 删除
```

还原到 token id 顺序：

```text
id0 True
id1 False
id2 True
id3 False
```

于是原 logits 中：

```text
id0/id2 → -inf
id1/id3 → 保留
```

---

<a id="origin-11707"></a>
### 24.40 采样还是贪心

源码：

```python
next_token = (
    torch.multinomial(
        torch.softmax(logits, dim=-1),
        num_samples=1
    )
    if do_sample
    else torch.argmax(
        logits,
        dim=-1,
        keepdim=True
    )
)
```

---

<a id="origin-11728"></a>
### 24.41 `do_sample=True`

先：

```python
torch.softmax(logits, dim=-1)
```

得到概率。

再：

```python
torch.multinomial(..., num_samples=1)
```

按概率抽一个类别编号。

例如：

```text
[0.7,0.2,0.1]
```

不是永远选第 0 项，而是：

```text
约 70% 机会选0
约 20% 机会选1
约 10% 机会选2
```

返回 shape：

```text
[B,1]
```

---

<a id="origin-11768"></a>
### 24.42 `do_sample=False`

```python
torch.argmax(
    logits,
    dim=-1,
    keepdim=True
)
```

选择最大分数位置。

`keepdim=True` 保证结果：

```text
[B,1]
```

而不是：

```text
[B]
```

这样后面更方便沿序列维拼接。

---

<a id="origin-11796"></a>
### 24.43 已结束序列强制继续填 EOS

源码：

```python
if eos_token_id is not None:
    next_token = torch.where(
        finished.unsqueeze(-1),
        next_token.new_full(
            (next_token.shape[0], 1),
            eos_token_id
        ),
        next_token
    )
```

假设：

```text
finished=[True,False]
```

`unsqueeze(-1)`：

```text
[[True],
 [False]]
```

如果模型本轮原本抽到：

```text
[[7],
 [10]]
```

第一条已经结束，所以强制替换成：

```text
[[EOS],
 [10]]
```

---

<a id="origin-11841"></a>
### 24.44 `next_token.new_full(...)`

创建 shape：

```text
[B,1]
```

全部填：

```text
eos_token_id
```

并继承 next_token 的 device/dtype。

---

<a id="origin-11859"></a>
### 24.45 追加新 token

源码：

```python
input_ids = torch.cat(
    [input_ids, next_token],
    dim=-1
)
```

例如：

```text
input_ids=[1,5,7]
next_token=[9]
```

得到：

```text
[1,5,7,9]
```

shape：

```text
[B,L] + [B,1]
→ [B,L+1]
```

这是自回归生成最直观的一步：

> 刚预测出来的 token，成为下一轮上下文的一部分。

---

<a id="origin-11896"></a>
### 24.46 更新 KV Cache

源码：

```python
past_key_values = (
    outputs.past_key_values
    if use_cache
    else None
)
```

如果缓存开启：

```text
使用这一轮 forward 返回的新缓存
```

否则：

```text
清成 None
```

下一轮：

```text
past_len=0
```

于是整个 input_ids 会重新进入 forward。

这就是 `use_cache=False` 时为什么计算更重。

---

<a id="origin-11932"></a>
### 24.47 一个很容易混淆的细节：刚生成的 token 此刻还不在 cache 里

第一轮 forward 输入：

```text
[1,5,7]
```

所以 cache 里是：

```text
1,5,7
```

然后才从 logits 选择：

```text
9
```

因此循环末尾：

```text
input_ids=[1,5,7,9]
```

但 cache 长度仍是：

```text
3
```

第二轮才把：

```text
9
```

送进 forward，从而写入 cache。

这解释了为什么代码可以用：

```python
input_ids[:, past_len:]
```

自动找到“还没缓存的尾巴”。

---

<a id="origin-11982"></a>
### 24.48 streamer 每轮接收新 token

```python
if streamer:
    streamer.put(next_token.cpu())
```

所以：

```text
开始时 put(prompt)
每轮 put(next_token)
最后 end()
```

streamer 就能边生成边显示。

---

<a id="origin-12001"></a>
### 24.49 更新 `finished`

源码：

```python
finished |= next_token.squeeze(-1).eq(eos_token_id)
```

拆开。

<a id="origin-12011"></a>
#### 24.49.1 `next_token.squeeze(-1)`

```text
[B,1] → [B]
```

<a id="origin-12017"></a>
#### 24.49.2 `.eq(eos_token_id)`

逐元素比较。

例如：

```text
next_token=[2,10]
eos=2
```

得到：

```text
[True,False]
```

<a id="origin-12034"></a>
#### 24.49.3 `|=`

布尔 OR 后写回。

假设之前：

```text
finished=[True,False]
```

本轮：

```text
is_eos=[False,True]
```

则：

```text
finished=[True,True]
```

一旦结束，后面不会恢复成 False。

---

<a id="origin-12060"></a>
### 24.50 `finished.all()`

源码：

```python
if finished.all():
    break
```

如果 batch 所有行都是 True：

```text
全部生成结束
```

直接 `break` 跳出 for 循环。

如果只有一部分结束：

```text
循环继续
```

已结束行会在下一轮被强制继续填 EOS，以维持 batch Tensor 的统一长度。

---

<a id="origin-12087"></a>
### 24.51 为什么不用 PAD 填结束后的行？

因为当前实现明确写的是：

```text
EOS
```

不是：

```text
pad_token_id
```

所以先结束的样本最终可能：

```text
... EOS EOS EOS
```

直到整个 batch 都停止。

这是“这份源码实际做法”，不是所有生成框架必须如此。

---

<a id="origin-12113"></a>
### 24.52 `eos_token_id=None`

如果调用者传：

```text
None
```

那么：

```text
不执行 finished 更新
不按 EOS 提前停止
```

只会跑到：

```text
max_new_tokens
```

上限。

当前实现接受的是单个 EOS 编号，不是多 EOS 列表逻辑。

---

<a id="origin-12140"></a>
### 24.53 循环结束后的 `streamer.end()`

```python
if streamer:
    streamer.end()
```

通知 streamer：

```text
生成结束，可以刷新缓冲、完成显示
```

具体行为由 streamer 自己定义。

---

<a id="origin-12157"></a>
### 24.54 `return_kv`：可选返回最终缓存

源码：

```python
if kwargs.get("return_kv"):
    return {
        'generated_ids': input_ids,
        'past_kv': past_key_values
    }
```

`kwargs.get("return_kv")`：

```text
没传 → None → False
传 True → 进入
```

返回一个 Python dict：

```text
{
  generated_ids: 完整序列,
  past_kv: 最后 cache
}
```

---

<a id="origin-12187"></a>
### 24.55 默认返回完整 token IDs

```python
return input_ids
```

假设 prompt：

```text
[1,5,7]
```

新增：

```text
[9,10,2]
```

最终：

```text
[1,5,7,9,10,2]
```

所以返回中包含：

```text
原 prompt + 新生成
```

如果只要新生成部分，调用方自己切：

```python
result[:, prompt_length:]
```

例如：

```python
result[:, 3:]
```

得到：

```text
[9,10,2]
```

---

<a id="origin-12237"></a>
## 25. 用一个完整三轮例子把 generate 从头跑到尾

现在不要再看零散行，真正跑一次。

假设：

```text
prompt = [1,5,7]
EOS = 2
use_cache=True
do_sample=False
```

假设模型三轮选择：

```text
9 → 10 → 2
```

---

<a id="origin-12258"></a>
### 25.1 第 0 时刻

```text
input_ids=[1,5,7]
past_key_values=None
finished=[False]
```

---

<a id="origin-12268"></a>
### 25.2 第 1 轮

```text
past_len=0
```

送入 forward：

```text
[1,5,7]
```

主干内部：

```text
Embedding
→ 所有 Block
→ 建立 1/5/7 的每层 KV Cache
```

最后位置 logits：

```text
预测 token 9
```

拼接：

```text
input_ids=[1,5,7,9]
```

缓存：

```text
长度=3
```

为什么不是 4？

因为 9 还没进 forward。

---

<a id="origin-12312"></a>
### 25.3 第 2 轮

```text
past_len=3
```

切：

```text
input_ids[:,3:]
=
[9]
```

forward 收到：

```text
新 token 9
+
前三个 token 的每层 KV Cache
```

Attention 内：

```text
K_old(3)+K9 → 长4
V_old(3)+V9 → 长4
```

最后位置 logits 预测：

```text
10
```

拼：

```text
[1,5,7,9,10]
```

cache 长：

```text
4
```

因为 10 还没进 forward。

---

<a id="origin-12363"></a>
### 25.4 第 3 轮

```text
past_len=4
```

只送：

```text
[10]
```

cache 更新到长度 5。

预测：

```text
2 = EOS
```

拼：

```text
[1,5,7,9,10,2]
```

`finished=True`。

`finished.all()`：

```text
True
```

break。

注意最后返回时：

```text
cache 长度=5
```

最后新选出的 EOS=2 还没有经过 forward，所以它不在 cache 中。

---

<a id="origin-12409"></a>
## 26. `use_cache=False` 时故事怎么变化？

第一轮：

```text
[1,5,7]
```

预测 9。

第二轮因为：

```text
past_key_values=None
past_len=0
```

所以整个：

```text
[1,5,7,9]
```

重新进入 forward。

第三轮：

```text
[1,5,7,9,10]
```

又全部重算。

所以：

```text
算法逻辑仍然正确
```

但计算量越来越大。

KV Cache 的本质就是：

> 把历史 K/V 留下来，使历史 token 不需要重复经过 K/V 投影和历史 Attention 计算。

---

<a id="origin-12456"></a>
## 27. 整个 839 行文件的最终调用栈

到这里可以把整个文件真正压缩成一个“运行时调用图”。

训练：

```text
用户调用
MiniMindForCausalLM(...)
      │
      ▼
MiniMindForCausalLM.forward
      │
      ├─ MiniMindModel.forward
      │      │
      │      ├─ Embedding
      │      │
      │      ├─ for 每个 MiniMindBlock
      │      │      │
      │      │      ├─ RMSNorm
      │      │      ├─ Attention.forward
      │      │      │      ├─ q_proj / k_proj / v_proj
      │      │      │      ├─ q_norm / k_norm
      │      │      │      ├─ apply_rotary_pos_emb
      │      │      │      ├─ KV Cache cat
      │      │      │      ├─ repeat_kv
      │      │      │      ├─ QK^T / sqrt(D)
      │      │      │      ├─ mask
      │      │      │      ├─ softmax
      │      │      │      ├─ @ V
      │      │      │      └─ o_proj
      │      │      │
      │      │      ├─ Residual
      │      │      ├─ RMSNorm
      │      │      ├─ FeedForward / MoE
      │      │      └─ Residual
      │      │
      │      └─ Final RMSNorm
      │
      ├─ lm_head
      ├─ shift logits / labels
      └─ CrossEntropy
```

生成：

```text
MiniMindForCausalLM.generate
      │
      ├─ 第1轮：完整 prompt → forward
      │
      ├─ logits 后处理
      │    ├─ temperature
      │    ├─ repetition penalty
      │    ├─ top-k
      │    └─ top-p
      │
      ├─ sample / argmax
      ├─ append next token
      ├─ 保存 KV Cache
      │
      ├─ 第2轮：仅未缓存后缀 → forward
      ├─ ...
      └─ EOS / max_new_tokens 停止
```

---

<a id="origin-12524"></a>
## 28. 把所有主要 Tensor shape 放到一张总表

下面用统一符号：

```text
B   batch size
T   本轮新输入长度
S   历史长度 + T
H   hidden size
V   vocab size
Nq  Query head 数
Nkv KV head 数
D   head dim
I   FFN intermediate size
E   Expert 数
K   每 token 选择的 Expert 数
```

| 位置 | Shape |
|---|---|
| `input_ids` | `[B,T]` |
| Embedding 后 | `[B,T,H]` |
| `q_proj` 后 | `[B,T,Nq*D]` |
| `k_proj/v_proj` 后 | `[B,T,Nkv*D]` |
| Q 拆头 | `[B,T,Nq,D]` |
| K/V 拆头 | `[B,T,Nkv,D]` |
| 历史 K/V 拼接后 | `[B,S,Nkv,D]` |
| repeat K/V | `[B,S,Nq,D]` |
| transpose Q | `[B,Nq,T,D]` |
| transpose K/V | `[B,Nq,S,D]` |
| Attention scores | `[B,Nq,T,S]` |
| softmax@V | `[B,Nq,T,D]` |
| concat heads | `[B,T,Nq*D]` |
| `o_proj` | `[B,T,H]` |
| FFN gate/up | `[B,T,I]` |
| FFN down | `[B,T,H]` |
| Final hidden states | `[B,T,H]` |
| LM logits | `[B,T,V]` |
| 训练 shift logits | `[B,T-1,V]` |
| 训练 shift labels | `[B,T-1]` |
| CE 展平 logits | `[B*(T-1),V]` |
| CE 展平 labels | `[B*(T-1)]` |
| MoE router scores | `[B*T,E]` |
| MoE top-k idx/weight | `[B*T,K]` |

---

<a id="origin-12571"></a>
## 29. Python/PyTorch 语法总复习：读这份源码必须会认的写法


<a id="origin-12575"></a>
### 29.1 `self.xxx`

```text
当前对象的属性
```

<a id="origin-12581"></a>
### 29.2 `super().__init__()`

```text
调用父类构造函数
```

<a id="origin-12587"></a>
### 29.3 `**kwargs`

```text
额外关键字参数打包成 dict
```

<a id="origin-12593"></a>
### 29.4 `dict.get(k, default)`

```text
有 k 用值；没有用 default
```

<a id="origin-12599"></a>
### 29.5 `dict.pop(k, default)`

```text
取值，同时从 dict 删除
```

<a id="origin-12605"></a>
### 29.6 `A if cond else B`

```text
条件表达式
```

<a id="origin-12611"></a>
### 29.7 `a,b = ...`

```text
元组/序列解包
```

<a id="origin-12617"></a>
### 29.8 `_`

```text
普通变量名；惯例表示“接住但不用”
```

<a id="origin-12623"></a>
### 29.9 `...`

```text
Ellipsis：前面的维度全部保留
```

<a id="origin-12629"></a>
### 29.10 `None` 出现在索引中

```python
x[:, None, :]
```

表示插入新维度。

<a id="origin-12637"></a>
### 29.11 `-1` 出现在索引

```python
x[-1]
```

表示最后一个。

<a id="origin-12645"></a>
### 29.12 `-1` 出现在 reshape/view

```python
x.view(-1,H)
```

表示该维自动推导。

<a id="origin-12653"></a>
### 29.13 `@`

```text
矩阵乘法
```

<a id="origin-12659"></a>
### 29.14 `*`

```text
逐元素乘法（Tensor 情况）
```

<a id="origin-12665"></a>
### 29.15 `.transpose(a,b)`

```text
交换两个维度
```

<a id="origin-12671"></a>
### 29.16 `.view()` / `.reshape()`

```text
重解释/改变 shape；不代表新的神经网络计算
```

<a id="origin-12677"></a>
### 29.17 `.unsqueeze(dim)`

```text
插入长度为1的维度
```

<a id="origin-12683"></a>
### 29.18 `.squeeze(dim)`

```text
去掉长度为1的维度
```

<a id="origin-12689"></a>
### 29.19 `.expand()`

```text
利用广播语义扩展视图
```

<a id="origin-12695"></a>
### 29.20 `.repeat()`

```text
按指定次数重复数据
```

<a id="origin-12701"></a>
### 29.21 `.contiguous()`

```text
把 Tensor 整理成连续内存布局，方便 view 等操作
```

<a id="origin-12707"></a>
### 29.22 `.type_as(x)`

```text
转换到与 x 相同 dtype
```

<a id="origin-12713"></a>
### 29.23 `.to(device)`

```text
移动设备/转换类型等
```

<a id="origin-12719"></a>
### 29.24 `.new_ones()` / `.new_zeros()` / `.new_full()`

```text
从现有 Tensor 派生同 device/dtype 的新 Tensor
```

<a id="origin-12725"></a>
### 29.25 `.any()` / `.all()`

```text
是否至少一个 True / 是否全部 True
```

<a id="origin-12731"></a>
### 29.26 `.nonzero()`

```text
找非零/True 的索引
```

<a id="origin-12737"></a>
### 29.27 `.flatten()`

```text
拉平成一维或指定范围维度
```

<a id="origin-12743"></a>
### 29.28 `torch.cat`

```text
沿现有维度拼接
```

<a id="origin-12749"></a>
### 29.29 `torch.topk`

```text
找最大的 k 项及其索引
```

<a id="origin-12755"></a>
### 29.30 `torch.sort`

```text
排序，同时返回原索引
```

<a id="origin-12761"></a>
### 29.31 `torch.cumsum`

```text
累积和
```

<a id="origin-12767"></a>
### 29.32 `scatter`

```text
根据 index 把值/标记散射回指定位置
```

<a id="origin-12773"></a>
### 29.33 `index_add_`

```text
按索引把 source 累加到目标行
```

<a id="origin-12779"></a>
### 29.34 `_` 结尾的方法

例如：

```python
index_add_
```

PyTorch 惯例通常表示：

```text
in-place 原地修改
```

---

<a id="origin-12795"></a>
## 30. 最后再把这份文件讲成“一条 token 的旅行”

假设输入：

```text
[BOS, I, love, AI]
```

经过 tokenizer 后假设：

```text
[1,5,7,2]
```

<a id="origin-12809"></a>
### 30.1 第一步：Embedding

```text
四个整数编号
→
四个 H 维向量
```

<a id="origin-12817"></a>
### 30.2 第二步：第一个 Block

每个 token 先 RMSNorm。

然后 Q/K/V 投影：

```text
当前 token 想查什么 → Q
其它位置用什么匹配 → K
匹配后真正读取什么 → V
```

Q/K 加 RoPE：

```text
让匹配关系知道 token 的位置
```

GQA：

```text
多个 Query Head 共享较少 K/V Head
```

Score：

```text
QK^T / sqrt(D)
```

Mask：

```text
不许偷看未来
```

Softmax：

```text
把可见位置变成权重
```

乘 V：

```text
按权重把上下文内容读进来
```

Residual：

```text
原信息 + 上下文新信息
```

FFN：

```text
每个 token 自己非线性加工
```

再次 Residual。

<a id="origin-12879"></a>
### 30.3 第三步：后续 Block

同样结构继续做，但输入已经不是最初词向量，而是上一层理解后的表示。

<a id="origin-12883"></a>
### 30.4 第四步：Final Norm

得到：

```text
最终 [B,T,H] hidden states
```

<a id="origin-12891"></a>
### 30.5 第五步：LM Head

每个位置：

```text
H → V
```

变成对整个词表的候选分数。

<a id="origin-12901"></a>
### 30.6 第六步：训练

```text
位置0预测token1
位置1预测token2
位置2预测token3
```

shift 后计算 CrossEntropy。

<a id="origin-12911"></a>
### 30.7 第七步：生成

只取最后位置 logits：

```text
temperature
→ repetition penalty
→ top-k
→ top-p
→ sample/argmax
```

选一个 token，接回序列，再来一轮。

KV Cache 让后续轮不需要重复计算全部历史 K/V。

---

<a id="origin-12929"></a>
## 31. 源码阅读顺序

不要从 L1 到 L839 一口气线性读。

建议：

```text
第一遍：只看结构
MiniMindForCausalLM
→ MiniMindModel
→ MiniMindBlock
→ Attention / FeedForward

第二遍：看完整 forward 数据流
input_ids
→ hidden_states
→ logits
→ loss

第三遍：深入 Attention
Q/K/V
→ RoPE
→ GQA
→ Mask
→ Softmax
→ V

第四遍：看 KV Cache + generate

第五遍：再看 MoE / YaRN / SDPA 等增强功能

第六遍：回到源码原顺序，从 L1 到 L839 检查是否每一行都知道属于哪一层
```


---

<a id="origin-12967"></a>
## 32. 源码模块与讲义章节对照表

| 原源码区域 | 讲义对应 |
|---|---|
| 文件头 import | 第 4 章 |
| `MiniMindConfig` | 第 5～6 章 |
| `RMSNorm` | 第 7 章 |
| `precompute_freqs_cis` | 第 8 章 |
| `apply_rotary_pos_emb` | [`apply_rotary_pos_emb()`：真正把 RoPE 旋转施加到 Q 和 K](../../%E8%AE%B2%E4%B9%89/%E6%A8%A1%E5%9E%8B%E6%BA%90%E7%A0%81%E4%B8%8E%E6%8E%A8%E7%90%86/b15-MiniMind%20%E6%BA%90%E7%A0%81%E9%80%90%E8%A1%8C%E7%B2%BE%E8%AE%B2.md#origin-3085) |
| `repeat_kv` | [`repeat_kv()`：GQA 为什么能让多个 Query Head 共用一组 K/V](../../%E8%AE%B2%E4%B9%89/%E6%A8%A1%E5%9E%8B%E6%BA%90%E7%A0%81%E4%B8%8E%E6%8E%A8%E7%90%86/b15-MiniMind%20%E6%BA%90%E7%A0%81%E9%80%90%E8%A1%8C%E7%B2%BE%E8%AE%B2.md#origin-3469) |
| `Attention.__init__` | [`Attention`：把 Q/K/V、RoPE、GQA、Mask、Softmax、KV Cache 全部拼起来](../../%E8%AE%B2%E4%B9%89/%E6%A8%A1%E5%9E%8B%E6%BA%90%E7%A0%81%E4%B8%8E%E6%8E%A8%E7%90%86/b15-MiniMind%20%E6%BA%90%E7%A0%81%E9%80%90%E8%A1%8C%E7%B2%BE%E8%AE%B2.md#origin-3826) |
| `Attention.forward` | [`Attention.forward()`：真正让一批 token 通过 Attention](../../%E8%AE%B2%E4%B9%89/%E6%A8%A1%E5%9E%8B%E6%BA%90%E7%A0%81%E4%B8%8E%E6%8E%A8%E7%90%86/b15-MiniMind%20%E6%BA%90%E7%A0%81%E9%80%90%E8%A1%8C%E7%B2%BE%E8%AE%B2.md#origin-4602) |
| `FeedForward` | [`FeedForward`：Attention 开完会以后，每个 token 自己做一次非线性加工](../../%E8%AE%B2%E4%B9%89/%E6%A8%A1%E5%9E%8B%E6%BA%90%E7%A0%81%E4%B8%8E%E6%8E%A8%E7%90%86/b15-MiniMind%20%E6%BA%90%E7%A0%81%E9%80%90%E8%A1%8C%E7%B2%BE%E8%AE%B2.md#origin-6172) |
| `MOEFeedForward` | 第 15～16 章 |
| `MiniMindBlock` | 第 17～18 章 |
| `MiniMindModel` | 第 19～20 章 |
| `MiniMindForCausalLM.__init__` | [`MiniMindForCausalLM`：在 Transformer 主干上再加“词表预测头”](../../%E8%AE%B2%E4%B9%89/%E6%A8%A1%E5%9E%8B%E6%BA%90%E7%A0%81%E4%B8%8E%E6%8E%A8%E7%90%86/b15-MiniMind%20%E6%BA%90%E7%A0%81%E9%80%90%E8%A1%8C%E7%B2%BE%E8%AE%B2.md#origin-9417) |
| `MiniMindForCausalLM.forward` | [`MiniMindForCausalLM.forward()`：完整的一次训练/推理前向](../../%E8%AE%B2%E4%B9%89/%E6%A8%A1%E5%9E%8B%E6%BA%90%E7%A0%81%E4%B8%8E%E6%8E%A8%E7%90%86/b15-MiniMind%20%E6%BA%90%E7%A0%81%E9%80%90%E8%A1%8C%E7%B2%BE%E8%AE%B2.md#origin-9745) |
| `generate` | 第 23～25 章 |
| 全局串联 | 第 26～31 章 |

---

<a id="origin-12990"></a>
## 33. 模型核心数据流

完整模型的数据流可以概括为以下代码：

```python
# token ids → embeddings
x = embedding(input_ids)

# N transformer blocks
for block in blocks:
    residual = x
    q = q_proj(norm1(x))
    k = k_proj(norm1(x))
    v = v_proj(norm1(x))

    q, k = rope(q, k)
    k, v = cat_past_kv(k, v)
    k, v = repeat_gqa_kv(k, v)

    score = q @ k.transpose(-2, -1) / sqrt(head_dim)
    score = causal_mask(score)
    weight = softmax(score)
    attn_out = weight @ v
    x = residual + o_proj(concat_heads(attn_out))

    residual = x
    x = residual + ffn(norm2(x))

# hidden states → vocabulary logits
x = final_norm(x)
logits = lm_head(x)

# train
loss = cross_entropy(logits[:, :-1], labels[:, 1:])

# generate
while not finished:
    logits = forward(uncached_suffix, past_kv).logits[:, -1]
    next_token = choose(logits)
    input_ids = cat(input_ids, next_token)
```


---

<a id="origin-13036"></a>
## 34. 一句话总结整份讲义

这份代码表面上是很多类、很多函数、很多 PyTorch API；但它们并不是互相独立的知识点。

它们从始至终都围绕同一条数据流服务：

```text
token ID
→ Embedding
→ 多层 Transformer
→ hidden state
→ vocabulary logits
→ Loss 或 Next Token
```

`RMSNorm`、RoPE、GQA、KV Cache、MoE、Top-K、Top-P 都只是这条主线上的具体机制。

真正学会阅读大型模型源码的关键不是“记住每一行”，而是同时拥有两种视角：

```text
宏观：我现在位于整条故事的哪一步？
微观：这一行 Python/PyTorch 到底对 Tensor 做了什么？
```

只要这两个视角能随时切换，再长的大模型实现也可以一层一层拆开。

---

<a id="origin-13064"></a>
## 35. RoPE 详解：`rotate_half` 为什么等价于旋转矩阵？为什么 1 和 3 是一组？（重点）

<a id="origin-13066"></a>
## 36. 核心结论

**有关系，而且这段代码实际上就是把熟悉的二维旋转矩阵拆开来计算了。**

标准二维旋转矩阵是：

\[
\boxed{
R(\theta)=
\begin{bmatrix}
\cos\theta&-\sin\theta\\
\sin\theta&\cos\theta
\end{bmatrix}
}
\]

对于二维向量 \(x=(a,b)^T\)，矩阵乘法可以改写为：

\[
\boxed{
R(\theta)x
=\underbrace{\begin{bmatrix}a\\b\end{bmatrix}\cos\theta}_{\text{原向量乘 cos}}
+\underbrace{\begin{bmatrix}-b\\a\end{bmatrix}\sin\theta}_{\text{交换位置、加负号，再乘 sin}}
}
\]

这里的 \((-b,a)\) 就是 `rotate_half` 要完成的操作。因此：

```python
q_embed = q * cos + rotate_half(q) * sin
```

**本质上就是二维旋转矩阵的乘法，只不过通过逐元素乘法和加法实现。**

下面从最简单的二维数值例子开始，再解释四维向量为什么将 `(1,3)` 配为一组，以及位置编码在哪里体现。

---

<a id="origin-13104"></a>
## 37. 最简单的二维旋转：将 (1,2) 旋转 90°

设：

\[
x=\begin{bmatrix}1\\2\end{bmatrix},\qquad\theta=90^\circ
\]

因为 \(\cos90^\circ=0\)、\(\sin90^\circ=1\)，所以：

\[
\begin{aligned}
x'&=\begin{bmatrix}0&-1\\1&0\end{bmatrix}
\begin{bmatrix}1\\2\end{bmatrix}\\[4pt]
&=\boxed{\begin{bmatrix}-2\\1\end{bmatrix}}
\end{aligned}
\]

这意味着 `(1,2)` 逆时针旋转 90° 后成为 `(-2,1)`。

<a id="origin-13124"></a>
### 37.1 为什么能拆成 `cos` 和 `sin` 两部分？

先将标准矩阵乘法展开：

\[
\begin{bmatrix}
\cos\theta&-\sin\theta\\
\sin\theta&\cos\theta
\end{bmatrix}
\begin{bmatrix}a\\b\end{bmatrix}
=
\begin{bmatrix}
a\cos\theta-b\sin\theta\\
a\sin\theta+b\cos\theta
\end{bmatrix}
\]

对结果按 \(\cos\theta\)、\(\sin\theta\) 拆项：

\[
\begin{aligned}
R(\theta)x
&=\begin{bmatrix}a\cos\theta\\b\cos\theta\end{bmatrix}
+\begin{bmatrix}-b\sin\theta\\a\sin\theta\end{bmatrix}\\[4pt]
&=x\cos\theta+
\underbrace{\begin{bmatrix}-b\\a\end{bmatrix}}_{\operatorname{rotate\_half}(x)}\sin\theta
\end{aligned}
\]

其中：

- `x * cos` 负责旋转矩阵中的两个 \(\cos\theta\)；
- `rotate_half(x)` 把 `(a,b)` 变成 `(-b,a)`，负责交换元素并提供负号；
- `rotate_half(x) * sin` 负责两个 \(\sin\theta\)；
- 两项相加，就实现了整个旋转矩阵的乘法。

<a id="origin-13160"></a>
### 37.2 用具体数字验证拆分公式

输入 \(x=(1,2)\)，旋转 \(90^\circ\)：

第一部分：

\[
x\cos90^\circ=
\begin{bmatrix}1\\2\end{bmatrix}\times0
=\begin{bmatrix}0\\0\end{bmatrix}
\]

第二部分：

\[
\operatorname{rotate\_half}(x)\sin90^\circ
=\begin{bmatrix}-2\\1\end{bmatrix}\times1
=\begin{bmatrix}-2\\1\end{bmatrix}
\]

相加：

\[
\boxed{x'=\begin{bmatrix}0\\0\end{bmatrix}+
\begin{bmatrix}-2\\1\end{bmatrix}=
\begin{bmatrix}-2\\1\end{bmatrix}}
\]

**和直接用旋转矩阵算出的结果完全一致。**

---

<a id="origin-13192"></a>
## 38. 回到实际代码：`rotate_half` 怎么操作高维向量？

MiniMind 中的代码是：

```python
def rotate_half(x):
    return torch.cat((
        -x[..., x.shape[-1] // 2:],
         x[..., :x.shape[-1] // 2]
    ), dim=-1)
```

`...` 表示保留前面的任意维度；`x.shape[-1]` 是最后一维的长度。函数**只处理最后一维**。

假设最后一维长度为 4：

```python
q = torch.tensor([1., 2., 3., 4.])
```

首先从中间切开：

```text
q                 = [ 1,  2 |  3,  4 ]
前半部分           = [ 1,  2 ]
后半部分           = [ 3,  4 ]
后半部分取负       = [-3, -4 ]
拼接               = [-3, -4,  1,  2 ]
```

因此：

\[
\boxed{\operatorname{rotate\_half}([1,2,3,4])=[-3,-4,1,2]}
\]

这并不是把整个四维向量当成一个二维向量，而是**在四维向量内部组成两组二维向量，分别旋转**。

---

<a id="origin-13232"></a>
## 39. 为什么 1 和 3 是一组，而不是 1 和 2？

因为这里采用的是 **前后两半配对（Half-Split）** 的维度排列方式。

```text
下标（从 1 开始）：  1   2   3   4
q：                [1,  2,  3,  4]
                    │   │   │   │
配对：              └───────┘   │    第 1 维 ↔ 第 3 维
                        └───────┘    第 2 维 ↔ 第 4 维
```

即：

- 第一组二维向量：`(1,3)`；
- 第二组二维向量：`(2,4)`。

这个结论并不是凭空规定的，可以直接从乘法结果看出来。

假设两组分别旋转 \(\theta_1,\theta_2\)，令：

\[
\begin{aligned}
c_1&=\cos\theta_1,&s_1&=\sin\theta_1\\
c_2&=\cos\theta_2,&s_2&=\sin\theta_2
\end{aligned}
\]

为了让每一组的两个分量使用同样的角度，需要：

\[
\cos=[c_1,c_2,c_1,c_2]
\]

\[
\sin=[s_1,s_2,s_1,s_2]
\]

注意：**第 1、3 维使用相同的 \(c_1,s_1\)，第 2、4 维使用相同的 \(c_2,s_2\)。**

代入代码：

\[
\begin{aligned}
q_{\mathrm{embed}}
&=[1,2,3,4]\odot[c_1,c_2,c_1,c_2]\\
&\quad+[-3,-4,1,2]\odot[s_1,s_2,s_1,s_2]\\
&=[c_1-3s_1,\;2c_2-4s_2,\;3c_1+s_1,\;4c_2+2s_2]
\end{aligned}
\]

其中 \(\odot\) 表示逐元素相乘。

<a id="origin-13285"></a>
### 39.1 单独抽取第 1、3 维

\[
\boxed{
\begin{bmatrix}q'_1\\q'_3\end{bmatrix}
=\begin{bmatrix}c_1&-s_1\\s_1&c_1\end{bmatrix}
\begin{bmatrix}1\\3\end{bmatrix}
}
\]

所以 `(1,3)` 正在一起做标准二维旋转。

<a id="origin-13297"></a>
### 39.2 单独抽取第 2、4 维

\[
\boxed{
\begin{bmatrix}q'_2\\q'_4\end{bmatrix}
=\begin{bmatrix}c_2&-s_2\\s_2&c_2\end{bmatrix}
\begin{bmatrix}2\\4\end{bmatrix}
}
\]

所以 `(2,4)` 也正在一起做标准二维旋转。

**结论：1 和 3 配对并非它们的数字有什么特殊关系，只是这段代码的维度布局决定它们组成同一个二维旋转组。**

---

<a id="origin-13313"></a>
## 40. 一个完整的四维数值例子

仍然取：

\[
q=[1,2,3,4]
\]

设第一组 `(1,3)` 旋转 \(90^\circ\)，第二组 `(2,4)` 旋转 \(0^\circ\)。

于是：

\[
\cos=[0,1,0,1],\qquad\sin=[1,0,1,0]
\]

第一部分：

\[
q\odot\cos
=[1,2,3,4]\odot[0,1,0,1]=[0,2,0,4]
\]

第二部分：

\[
\operatorname{rotate\_half}(q)\odot\sin
=[-3,-4,1,2]\odot[1,0,1,0]=[-3,0,1,0]
\]

相加：

\[
\boxed{q_{\mathrm{embed}}=[-3,2,1,4]}
\]

拆回两组看：

- `(1,3)` 经 \(90^\circ\) 旋转得到 `(-3,1)`；
- `(2,4)` 经 \(0^\circ\) 旋转仍为 `(2,4)`。

也可以写成一个四维矩阵：

\[
\begin{bmatrix}
0&0&-1&0\\
0&1&0&0\\
1&0&0&0\\
0&0&0&1
\end{bmatrix}
\begin{bmatrix}1\\2\\3\\4\end{bmatrix}
=\begin{bmatrix}-3\\2\\1\\4\end{bmatrix}
\]

可见原来的二维旋转矩阵没有消失，只是在高维空间中作用于多组二维子空间。

---

<a id="origin-13371"></a>
## 41. 能不能改成 (1,2)、(3,4) 配对？

**完全可以。** RoPE 常见两种实现方式：

| 维度布局 | 第 1 组 | 第 2 组 | 实现思路 |
|---|---|---|---|
| 前后两半配对（Half-Split） | `(1,3)` | `(2,4)` | 前半维与后半维对应配对，`rotate_half` |
| 相邻配对（Interleaved） | `(1,2)` | `(3,4)` | 每两个相邻维度为一组，交换组内位置并取负 |

例如相邻配对的四维旋转辅助函数会产生：

```text
输入：                 [ 1,  2,  3,  4 ]
相邻配对旋转辅助结果： [-2,  1, -4,  3 ]
```

二者都能实现 RoPE，但需保证 **Q、K 使用相同的维度排列，且 cos/sin 频率排列与之匹配**。已训练好的模型不能直接替换配对方案而不处理权重布局。

---

<a id="origin-13391"></a>
## 42. 这和 RoPE 的 token 位置 m、n 有什么关系？

先区分两个概念：

1. **维度配对：** 第 1、3 维或第 2、4 维被放在一起，决定“谁和谁旋转”。
2. **token 位置：** 第 \(m\) 个 token 对应的旋转角度是多少，决定“旋转多少”。

对位置 \(m\)、旋转组 \(i\)，RoPE 的角度一般写为：

\[
\boxed{\phi_{m,i}=m\omega_i}
\]

其中 \(\omega_i\) 是该组的旋转频率。于是：

\[
\cos_{m,i}=\cos(m\omega_i),\qquad
\sin_{m,i}=\sin(m\omega_i)
\]

用一个**人为设定的示例频率** \(\omega_1=30^\circ\)（每个位置转 30°）来说明：

| Token 位置 m | 角度 mω₁ | cos | sin |
|---|---:|---:|---:|
| 0 | 0° | 1 | 0 |
| 1 | 30° | 0.866 | 0.500 |
| 2 | 60° | 0.500 | 0.866 |
| 3 | 90° | 0 | 1 |

同一个二维输入向量 `(1,0)`：

- 位置 0：旋转 0°，得到 `(1,0)`；
- 位置 1：旋转 30°，约为 `(0.866,0.500)`；
- 位置 3：旋转 90°，得到 `(0,1)`。

注意，真实 RoPE 使用的频率不是所有维度都固定 30°，这里仅用于演示位置如何进入公式。

当位置 \(m\) 的 Q 和位置 \(n\) 的 K 做点积时，对同一个旋转组：

\[
\begin{aligned}
(R(m\omega_i)q)^T(R(n\omega_i)k)
&=q^TR(m\omega_i)^TR(n\omega_i)k\\
&=\boxed{q^TR((n-m)\omega_i)k}
\end{aligned}
\]

所以注意力分数能够体现它们的**相对位置差** \(n-m\)。

---

<a id="origin-13442"></a>
## 43. 把完整的 Q、K 代码串起来看

```python
def rotate_half(x):
    return torch.cat(
        (-x[..., x.shape[-1] // 2:],
          x[..., :x.shape[-1] // 2]),
        dim=-1,
    )

q_embed = (
    q * cos.unsqueeze(unsqueeze_dim)
    + rotate_half(q) * sin.unsqueeze(unsqueeze_dim)
).to(q.dtype)

k_embed = (
    k * cos.unsqueeze(unsqueeze_dim)
    + rotate_half(k) * sin.unsqueeze(unsqueeze_dim)
).to(k.dtype)

return q_embed, k_embed
```

逐部分理解：

- `q`、`k`：每个 token 在各个 Attention Head 上的 Query、Key 向量。
- `cos`、`sin`：**此前已经按 token 位置和旋转频率算好的值**；不是这里才计算位置。
- `rotate_half(q)`、`rotate_half(k)`：完成 \((a,b)\mapsto(-b,a)\) 这种分组操作。
- `q * cos + rotate_half(q) * sin`：完成 Q 的分组旋转。
- `k * cos + rotate_half(k) * sin`：同理完成 K 的分组旋转。
- `unsqueeze(unsqueeze_dim)`：插入一个维度以便广播到各个 Attention Head，**它本身不计算或决定位置**。
- `.to(q.dtype)` / `.to(k.dtype)`：将计算结果转回 Q、K 原来的数据类型。
- `return q_embed, k_embed`：返回已经加入 RoPE 位置信息的 Q、K。

**注意：**一般不对 V 应用 RoPE；标准 RoPE 主要旋转 Q 与 K，使注意力点积包含相对位置信息。

---

<a id="origin-13480"></a>
## 44. 一句话总结

**`rotate_half` 负责构造每组二维向量的 `(-b,a)`，`q * cos + rotate_half(q) * sin` 与标准的 `[[cos,-sin],[sin,cos]]` 矩阵乘法完全等价；而在当前 Half-Split 代码中，四维向量 `[1,2,3,4]` 的配对是 `(1,3)` 和 `(2,4)`，token 位置再通过不同的 `cos/sin` 决定旋转角度。**
