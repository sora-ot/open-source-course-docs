# Reward Model 训练代码


可以搜索“重点”以查看核心内容。

---

<a id="origin-7"></a>
## 1. 先用一句话说清楚：这个程序到底在干什么？

我们先不要看代码。

假设现在有这样一条数据：

```text
问题：
1 + 1 等于几？

回答 A：
等于 2。

回答 B：
等于 5。
```

人工标注告诉我们：

```text
回答 A 更好
回答 B 更差
```

那么 Reward Model 要学习的是：

\[
R(\text{问题 + 回答A})
>
R(\text{问题 + 回答B})
\]

例如训练以后可能得到：

```text
回答 A：reward = 2.3
回答 B：reward = -0.7
```

注意：

**我们并没有告诉模型 A 应该是 2.3 分，B 应该是 -0.7 分。**

我们只告诉它：

```text
A > B
```

所以 Reward Model 学习的是：

> **相对偏好关系。**

而不是绝对分数。

---

<a id="origin-64"></a>
## 2. 整个文件的核心流程

整个程序可以压缩成：

```text
chosen 对话
rejected 对话
        │
        ▼
Chat Template
        │
        ▼
Tokenizer
        │
        ▼
Token IDs
        │
        ▼
Padding + Attention Mask
        │
        ▼
MiniMind Transformer
        │
        ▼
每个 Token 的 Hidden State
        │
        ▼
取最后一个真实 Token 的 Hidden State
        │
        ▼
Linear(H → 1)
        │
        ▼
Reward Score
        │
        ├─────────────┐
        ▼             ▼
r_chosen          r_rejected
        │             │
        └──────┬──────┘
               ▼
      Δ = r_chosen-r_rejected
               │
               ▼
         sigmoid(Δ)
               │
               ▼
-log sigmoid(Δ)
               │
               ▼
           backward
               │
               ▼
更新 Reward Head
+
更新整个 MiniMind Backbone
```

这个实现和 SFT 最大的区别是：

```text
SFT：

每一个 token
   ↓
预测下一个 token
   ↓
CrossEntropy Loss
```

Reward Model：

```text
整段 Prompt + Response
        ↓
一个标量 Reward
        ↓
chosen 与 rejected 比大小
```

---

<a id="origin-146"></a>
## 3. 第一部分：代码里所有重要的外部库调用

---

<a id="origin-150"></a>
## 4. `pathlib.Path`

代码：

```python
from pathlib import Path
```

---

<a id="origin-160"></a>
### 4.1 `Path(__file__)`

```python
Path(__file__)
```

`__file__` 表示：

```text
当前 Python 文件自己的路径
```

例如：

```text
D:/minimind/trainer/train_reward.py
```

于是：

```python
Path(__file__)
```

会把普通字符串路径转换成一个：

```text
Path 对象
```

方便后面操作。

---

<a id="origin-194"></a>
### 4.2 `.resolve()`

```python
Path(__file__).resolve()
```

作用：

> 得到这个文件的绝对路径。

例如：

```text
trainer/train_reward.py
```

可能变成：

```text
D:/project/minimind/trainer/train_reward.py
```

---

<a id="origin-218"></a>
### 4.3 `.parents`

```python
Path(__file__).resolve().parents[1]
```

假设：

```text
D:/project/minimind/trainer/train_reward.py
```

那么：

```text
parents[0]
=
D:/project/minimind/trainer
```

```text
parents[1]
=
D:/project/minimind
```

于是代码：

```python
ROOT = Path(__file__).resolve().parents[1]
```

得到项目根目录。

程序因此不需要依赖：

```text
你当前在哪个目录执行 Python
```

来寻找默认模型和数据。



---

<a id="origin-264"></a>
### 4.4 `.is_file()`

```python
Path(path).is_file()
```

检查：

```text
这个路径是不是一个真实存在的文件
```

Reward Model 加载 SFT 权重之前会检查：

```python
if not Path(path).is_file():
```

防止：

```text
文件根本不存在
```

却继续调用 `torch.load()`。

---

<a id="origin-292"></a>
### 4.5 `.parent.mkdir()`

```python
path.parent.mkdir(
    parents=True,
    exist_ok=True
)
```

假设：

```text
path = out/reward_768.pth
```

那么：

```text
path.parent
=
out
```

`.mkdir()`：

```text
创建目录
```

其中：

```text
parents=True
```

意味着父目录不存在也一起建立。

```text
exist_ok=True
```

意味着：

```text
目录已经存在也不要报错
```

---

<a id="origin-341"></a>
### 4.6 `.with_suffix()`

```python
temporary = path.with_suffix(
    path.suffix + ".tmp"
)
```

例如：

```text
reward_768.pth
```

变成：

```text
reward_768.pth.tmp
```

程序先保存临时文件，再替换正式文件。

---

<a id="origin-365"></a>
### 4.7 `.replace()`

```python
temporary.replace(path)
```

把：

```text
reward_768.pth.tmp
```

替换成：

```text
reward_768.pth
```

这样做比直接往正式文件覆盖稍微安全一些。

---

<a id="origin-387"></a>
## 5. `sys.path.insert`

```python
sys.path.insert(0, str(ROOT))
```

Python import 时会去：

```python
sys.path
```

里面的目录寻找模块。

例如程序需要：

```python
from model.model_minimind import MiniMindConfig
```

但当前运行的是：

```text
trainer/train_reward.py
```

所以这里人为把：

```text
MiniMind 项目根目录
```

插入搜索路径最前面。

---

<a id="origin-423"></a>
## 6. `os.environ.setdefault`

```python
os.environ.setdefault(
    "TOKENIZERS_PARALLELISM",
    "false"
)
```

作用：

如果：

```text
TOKENIZERS_PARALLELISM
```

这个环境变量还没有设置，那么设置成：

```text
false
```

但如果用户本来就设置过：

```text
不会覆盖。
```

与：

```python
os.environ["TOKENIZERS_PARALLELISM"] = "false"
```

的区别就在这里。

---

<a id="origin-462"></a>
## 7. Hugging Face `datasets`

```python
import datasets
```

这是数据处理库。

---

<a id="origin-472"></a>
### 7.1 `datasets.load_dataset`

```python
samples = datasets.load_dataset(
    "json",
    data_files=str(path),
    split="train"
)
```

意思：

```text
读取 JSON / JSONL 文件
```

假设文件：

```json
{
  "chosen": [...],
  "rejected": [...]
}
```

每一行就是一条偏好对。

这里：

```python
split="train"
```

并不是说：

```text
自动把数据切成训练集和验证集。
```

只是：

> 把这个 JSON 文件加载成名字为 `train` 的 Dataset。

代码本身也明确指出这里没有自动划分验证集。

---

<a id="origin-519"></a>
## 8. Dataset 的 `.select()`

```python
samples.select(
    range(min(max_samples, len(samples)))
)
```

例如数据有：

```text
10000 条
```

而：

```text
max_samples = 100
```

那么：

```text
只取前 100 条。
```

注意：

> 不是随机抽 100 条。

而是：

```text
0 ~ 99
```

---

<a id="origin-557"></a>
## 9. Dataset 的 `.map()`

```python
samples.map(
    encode_pair,
    with_indices=True,
    remove_columns=samples.column_names
)
```

可以理解成：

```text
对 Dataset 每一行执行一次 encode_pair()
```

例如：

```text
原来的第 0 行
    ↓
encode_pair(sample0, 0)

原来的第 1 行
    ↓
encode_pair(sample1, 1)
```

---

<a id="origin-587"></a>
### 9.1 `with_indices=True`

意味着：

```python
encode_pair(sample, index)
```

除了样本本身，还会得到：

```text
index
```

这样报错的时候能够说：

```text
样本 357 出错
```

---

<a id="origin-609"></a>
### 9.2 `remove_columns=...`

处理完成之后，把：

```text
原始 chosen/rejected 文本
```

删除。

只留下：

```text
chosen_ids
rejected_ids
keep
```

这样后面每一个 epoch 不需要重复 Tokenize。

---

<a id="origin-631"></a>
## 10. Dataset 的 `.filter()`

```python
samples.filter(
    lambda sample: sample["keep"]
)
```

只保留：

```text
keep == True
```

的样本。

例如：

```text
样本 0 keep=True
样本 1 keep=False
样本 2 keep=True
```

最后留下：

```text
样本 0
样本 2
```

整个 `RewardDataset` 在初始化阶段已经完成了加载、编码和过滤。

---

<a id="origin-666"></a>
## 11. Hugging Face `AutoTokenizer`

```python
from transformers import AutoTokenizer
```

---

<a id="origin-674"></a>
### 11.1 `AutoTokenizer.from_pretrained`

```python
tokenizer = AutoTokenizer.from_pretrained(
    args.tokenizer_path
)
```

作用：

> 从指定目录加载 Tokenizer。

里面通常包括：

```text
词表
tokenizer 配置
特殊 token
Chat Template
```

Reward Model 训练和推理必须使用相同 Tokenizer。

否则：

```text
"你好"
```

训练时可能编码：

```text
[123, 456]
```

推理时却可能变成：

```text
[888, 999]
```

模型当然就不认识了。

---

<a id="origin-719"></a>
## 12. `tokenizer.apply_chat_template()`

代码：

```python
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=False
)
```

假设：

```python
messages = [
    {
        "role": "user",
        "content": "1+1?"
    },
    {
        "role": "assistant",
        "content": "2"
    }
]
```

原始数据只是一个 Python List。

Chat Template 可能把它变成类似：

```text
<user>
1+1?
</user>
<assistant>
2
</assistant>
```

真正模板取决于 MiniMind Tokenizer。

---

<a id="origin-763"></a>
### 12.1 `tokenize=False`

意味着：

```text
这里只负责套模板
```

先返回：

```text
字符串
```

而不是立即返回 Token IDs。

---

<a id="origin-781"></a>
### 12.2 `add_generation_prompt=False`

这个非常重要。

因为当前数据已经包含：

```text
assistant 的完整答案
```

所以不能再加：

```text
<assistant>
```

作为“等待模型生成答案”的提示。

这不是生成任务。

这是：

```text
给完整回答打分。
```

---

<a id="origin-809"></a>
## 13. `tokenizer(...)`

```python
tokenizer(
    text,
    add_special_tokens=False
)["input_ids"]
```

作用：

```text
文字
 ↓
Token ID
```

例如教学上假设：

```text
"<user>1+1?</user><assistant>2</assistant>"
```

变成：

```text
[1, 10, 20, 2]
```

之所以：

```python
add_special_tokens=False
```

是因为：

```text
Chat Template 已经负责加入需要的特殊标记
```

避免 Tokenizer 再重复加入一次。

这一过程正是文件中的 `encode_messages()`。

---

<a id="origin-856"></a>
## 14. PyTorch `Dataset`

```python
from torch.utils.data import Dataset
```

然后：

```python
class RewardDataset(Dataset):
```

继承 PyTorch Dataset 后，一般至少实现：

```python
__len__()
__getitem__()
```

---

<a id="origin-877"></a>
### 14.1 `__len__()`

```python
def __len__(self):
    return len(self.samples)
```

于是：

```python
len(dataset)
```

就知道：

```text
有多少个偏好对。
```

注意：

如果有：

```text
1000 个 chosen
1000 个 rejected
```

这里：

```text
len(dataset)=1000
```

而不是 2000。

因为单位是：

```text
偏好对。
```

---

<a id="origin-921"></a>
### 14.2 `__getitem__()`

```python
def __getitem__(self, index):
    return self.samples[index]
```

因此：

```python
dataset[7]
```

得到：

```python
{
    "chosen_ids": ...,
    "rejected_ids": ...
}
```

---

<a id="origin-945"></a>
## 15. `DataLoader`

```python
from torch.utils.data import DataLoader
```

使用：

```python
loader = DataLoader(
    train_data,
    batch_size=args.batch_size,
    shuffle=True,
    collate_fn=train_data.collate,
    num_workers=0
)
```

作用：

> 自动从 Dataset 中一批一批取数据。

---

<a id="origin-969"></a>
### 15.1 `batch_size`

这里尤其容易误解。

假设：

```text
batch_size = 2
```

不是：

```text
2 条序列
```

而是：

```text
2 对偏好数据
```

也就是：

```text
2 个 chosen
+
2 个 rejected

= 4 条真正进入 Transformer 的序列
```

所以：

\[
N=2B
\]

---

<a id="origin-1009"></a>
### 15.2 `shuffle=True`

每个 epoch：

```text
打乱偏好对的顺序
```

但是不会把：

```text
chosen
rejected
```

拆散。

---

<a id="origin-1028"></a>
### 15.3 `collate_fn`

```python
collate_fn=train_data.collate
```

表示：

> 一个 batch 拿出来以后，不使用 PyTorch 默认组批，而使用程序自己定义的 `collate()`。

原因是：

```text
不同回答 Token 长度不同。
```

必须 Padding。

---

<a id="origin-1048"></a>
### 15.4 `num_workers=0`

表示：

```text
主进程自己读取数据。
```

教学和 Windows 调试比较简单。

---

<a id="origin-1060"></a>
## 16. `torch.tensor`

```python
torch.tensor(sequence)
```

把：

```python
[1, 10, 20, 2]
```

这种 Python List 转成 Tensor：

```text
tensor([1,10,20,2])
```

另外：

```python
torch.tensor(
    [ids],
    dtype=torch.long,
    device=device
)
```

会增加 Batch 维：

```text
[T]
↓
[1,T]
```

---

<a id="origin-1098"></a>
## 17. `torch.full`

```python
ids = torch.full(
    (len(sequences), width),
    self.pad_id,
    dtype=torch.long
)
```

作用：

创建一个指定形状、所有元素都等于某个数的 Tensor。

例如：

```python
torch.full(
    (4, 5),
    0
)
```

得到：

```text
[
 [0,0,0,0,0],
 [0,0,0,0,0],
 [0,0,0,0,0],
 [0,0,0,0,0]
]
```

这里用来：

```text
先创建全部是 PAD 的 Token 矩阵。
```

---

<a id="origin-1140"></a>
## 18. `torch.zeros_like`

```python
mask = torch.zeros_like(ids)
```

表示：

```text
创建一个和 ids
形状一样
dtype 一样
device 一样
```

但元素全部为：

```text
0
```

于是最开始：

```text
所有位置都假设是 Padding。
```

然后真实 Token 的位置改成：

```text
1
```

---

<a id="origin-1175"></a>
## 19. Padding 的实际例子（重点）

假设两对数据：

```text
c0 = [1,10,2]

c1 = [1,20,21,2]

r0 = [1,11,12,2]

r1 = [1,22,2]
```

程序先排列：

```text
[c0,c1,r0,r1]
```

而不是：

```text
[c0,r0,c1,r1]
```

然后最长：

```text
T=4
```

得到：

```text
input_ids =

[
 [1,10, 2,0],
 [1,20,21,2],
 [1,11,12,2],
 [1,22, 2,0]
]
```

Attention Mask：

```text
[
 [1,1,1,0],
 [1,1,1,1],
 [1,1,1,1],
 [1,1,1,0]
]
```

这一点非常重要，因为后面：

```python
scores.chunk(2)
```

正是依赖这个排列方式恢复：

```text
chosen
rejected
```

两组。

---

<a id="origin-1248"></a>
## 20. 为什么不能写成：

```python
mask = ids != pad_id
```

假设：

```text
EOS ID = 2
PAD ID = 2
```

真实数据：

```text
[1,10,2]
```

Padding 后：

```text
[1,10,2,2,2]
```

如果：

```python
ids != 2
```

就会得到：

```text
[1,1,0,0,0]
```

但第三个：

```text
2
```

其实是真正的 EOS。

正确应该：

```text
[1,1,1,0,0]
```

所以这里单独记录真实长度，而不是靠 Token ID 判断。

---

<a id="origin-1303"></a>
## 21. `nn.Module`

```python
class MiniMindRewardModel(nn.Module):
```

PyTorch 中所有神经网络模型基本都继承：

```python
nn.Module
```

它负责：

```text
参数注册
子模块注册
state_dict
to(device)
train()
eval()
parameters()
反向传播结构管理
```

---

<a id="origin-1330"></a>
## 22. `super().__init__()`

```python
super().__init__()
```

初始化：

```text
nn.Module
```

的内部机制。

否则：

```python
self.model = ...
self.reward_head = ...
```

这些子模块就不能正确注册。

---

<a id="origin-1355"></a>
## 23. `nn.Linear`

Reward Head：

```python
self.reward_head = nn.Linear(
    config.hidden_size,
    1,
    bias=False
)
```

假设：

```text
H = 768
```

那么输入：

\[
h\in \mathbb R^{768}
\]

权重：

\[
W_r\in \mathbb R^{1\times768}
\]

输出：

\[
r=W_rh
\]

只有：

```text
1 个数字。
```

这就是 Reward。

---

<a id="origin-1401"></a>
## 24. 为什么 `bias=False`？

如果有 bias：

\[
r_c=W h_c+b
\]

\[
r_r=W h_r+b
\]

训练真正关心：

\[
r_c-r_r
\]

代进去：

\[
(W h_c+b)-(W h_r+b)
\]

得到：

\[
W h_c-W h_r
\]

`b` 完全抵消。

所以共享的常数 bias 对 Pairwise Loss 没什么作用。

---

<a id="origin-1437"></a>
## 25. `nn.init.normal_`

```python
nn.init.normal_(
    self.reward_head.weight,
    mean=0.0,
    std=0.02
)
```

意思是：

Reward Head 的初始参数从：

\[
\mathcal N(0,0.02^2)
\]

随机生成。

例如可能是：

```text
[
 0.013,
-0.021,
 0.004,
...
]
```

为什么评分头随机？

因为 SFT 原来的模型只有：

```text
Language Model Head
H → Vocabulary
```

并没有：

```text
Reward Head
H → 1
```

所以：

```text
Backbone 可以继承 SFT
Reward Head 必须新建
```

文件就是这么实现的。

---

<a id="origin-1495"></a>
## 26. `torch.arange`

代码：

```python
torch.arange(
    hidden.size(0),
    device=hidden.device
)
```

假设：

```text
N=4
```

得到：

```text
[0,1,2,3]
```

用来配合：

```text
每条序列自己的最后真实位置
```

取 Hidden State。

---

<a id="origin-1528"></a>
## 27. Tensor `.sum(dim=1)`（重点）

```python
last = attention_mask.sum(dim=1) - 1
```

例如：

```text
mask =

[
 [1,1,1,0],
 [1,1,1,1]
]
```

求和：

```text
[3,4]
```

减一：

```text
[2,3]
```

也就是：

```text
第 0 条最后 Token 在位置 2
第 1 条最后 Token 在位置 3
```

---

<a id="origin-1566"></a>
## 28. `.size(0)`

```python
hidden.size(0)
```

如果：

```text
hidden.shape = [4,10,768]
```

那么：

```text
hidden.size(0)=4
```

即：

```text
Batch 维度。
```

---

<a id="origin-1592"></a>
## 29. 高级索引（重点）

```python
final_hidden = hidden[
    torch.arange(hidden.size(0)),
    last
]
```

假设：

```text
last=[2,3]
```

实际上取：

```text
hidden[0,2]
hidden[1,3]
```

得到：

```text
[N,H]
```

---

<a id="origin-1622"></a>
## 30. 为什么只取最后一个 Token？（重点）

这是 Reward Model 非常重要的一步。

假设文本：

```text
用户：1+1？
助手：2。<EOS>
```

Decoder-only Transformer 的因果注意力意味着最后一个位置：

```text
<EOS>
```

可以 Attention 到：

```text
用户：
1
+
1
？
助手：
2
。
```

也就是说：

```text
最后 Token 的 Hidden State
```

已经综合了：

> 前面整段 Prompt + Response 的信息。

所以可以拿：

\[
h_{\text{last}}
\]

作为：

```text
整句话的表示
```

再：

\[
r=W_rh_{\text{last}}
\]

得到 Reward。

文件中特别使用 attention mask 寻找最后一个**真实 Token**，而不是直接 `hidden[:, -1]`，因为 Batch 中可能存在右侧 Padding。

---

<a id="origin-1686"></a>
## 31. `.squeeze(-1)`（重点）

Linear 输出：

```text
[N,1]
```

例如：

```text
[
 [2.1],
 [-0.7],
 [1.3],
 [0.2]
]
```

调用：

```python
.squeeze(-1)
```

变成：

```text
[N]
```

：

```text
[2.1,-0.7,1.3,0.2]
```

注意：

```python
squeeze(-1)
```

只删除最后那个长度为 1 的维度。

即使 N=1：

```text
[1,1]
→
[1]
```

不会变成 0 维 Tensor。

---

<a id="origin-1743"></a>
## 32. `@torch.no_grad()`

```python
@torch.no_grad()
def get_score(...):
```

表示执行这个函数时：

```text
不记录反向传播计算图。
```

因为这里只是：

```text
评分
```

不训练。

因此：

```text
显存占用更少
速度更快
```

但注意：

> `no_grad()` 不等于 `eval()`。

---

<a id="origin-1777"></a>
## 33. `.eval()`

```python
self.eval()
```

将模型切换到：

```text
evaluation mode
```

例如关闭：

```text
Dropout
```

等训练行为。

---

<a id="origin-1799"></a>
## 34. `.train()`

```python
model.train()
```

设置：

```text
training mode
```

而：

```python
model.train(False)
```

本质上接近：

```python
model.eval()
```

代码中评分完成以后：

```python
self.train(was_training)
```

恢复调用 `get_score()` 之前的状态。

---

<a id="origin-1833"></a>
## 35. `torch.ones_like`

评分时只有一条完整序列，没有 Padding：

```python
torch.ones_like(input_ids)
```

例如：

```text
input_ids =
[[1,10,20,2]]
```

生成：

```text
mask =
[[1,1,1,1]]
```

表示：

```text
四个位置都是真实 Token。
```

---

<a id="origin-1863"></a>
## 36. `.item()`

```python
scores.item()
```

假设：

```text
tensor([1.257])
```

转换为 Python：

```text
1.257
```

这样方便：

```text
打印
传给外部程序
```

文件中的评分模式就是这样返回单个 Python Reward。

---

<a id="origin-1892"></a>
## 37. `torch.load`

```python
torch.load(
    path,
    map_location="cpu",
    weights_only=True
)
```

作用：

```text
从磁盘读取 PyTorch 权重。
```

---

<a id="origin-1910"></a>
### 37.1 `map_location="cpu"`

即使这个模型当初保存在：

```text
GPU
```

也先：

```text
加载到 CPU。
```

避免一读文件立刻占 GPU。

---

<a id="origin-1928"></a>
### 37.2 `weights_only=True`

使用限制更严格的权重加载模式。

主要用于：

```text
加载模型权重和简单数据结构。
```

---

<a id="origin-1940"></a>
## 38. `.load_state_dict()`

```python
model.load_state_dict(
    checkpoint["model"],
    strict=True
)
```

把：

```text
checkpoint 中保存的参数
```

复制到：

```text
当前新创建的网络。
```

---

<a id="origin-1963"></a>
### 38.1 `strict=True`

要求：

```text
参数名字全部匹配
参数形状全部匹配
```

例如模型期望：

```text
reward_head.weight
```

checkpoint 没有：

```text
直接报错。
```

而不是偷偷留下随机参数。

---

<a id="origin-1988"></a>
## 39. `.state_dict()`

```python
model.state_dict()
```

得到：

```text
模型所有注册参数
+
持久 Buffer
```

例如：

```text
model.embed_tokens.weight

model.layers.0.self_attn.q_proj.weight

...

reward_head.weight
```

---

<a id="origin-2016"></a>
## 40. `.detach()`

```python
v.detach()
```

意思：

> 把这个 Tensor 从当前计算图中分离。

保存模型时当然没必要保留：

```text
它是由哪个计算产生的
```

这种梯度关系。

---

<a id="origin-2036"></a>
## 41. `.cpu()`

```python
v.detach().cpu()
```

把参数复制/移动到：

```text
CPU Tensor
```

再保存。

注意：

这并不会把：

```text
正在训练的原模型
```

永久搬到 CPU。

只是保存用的 Tensor 变成 CPU 版本。

---

<a id="origin-2064"></a>
## 42. `torch.save`

```python
torch.save(
    {
        "config": ...,
        "model": ...
    },
    temporary
)
```

将 Python 对象保存为：

```text
.pth
```

文件。

这个程序保存：

```text
模型结构 Config
+
模型权重
```

但不保存：

```text
Optimizer
step
epoch
随机数状态
```

所以这是：

```text
模型导出
```

不是严格意义的：

```text
断点续训 checkpoint。
```

保存函数的具体实现见文件。

---

<a id="origin-2117"></a>
## 43. `.to(device)`

例如：

```python
model.to("cuda:0")
```

把：

```text
模型参数
```

搬到 GPU。

类似：

```python
input_ids.to("cuda:0")
```

把输入搬到 GPU。

非常重要：

```text
模型和输入必须在同一设备。
```

---

<a id="origin-2149"></a>
## 44. `argparse.ArgumentParser`

```python
parser = argparse.ArgumentParser(...)
```

创建：

```text
命令行参数解析器。
```

于是可以运行：

```bash
python train_reward.py \
    --batch_size 4 \
    --learning_rate 1e-5
```

---

<a id="origin-2171"></a>
## 45. `.add_argument()`

例如：

```python
parser.add_argument(
    "--batch_size",
    type=int,
    default=2
)
```

意味着：

```text
允许用户传 --batch_size
```

类型：

```text
int
```

默认：

```text
2
```

---

<a id="origin-2203"></a>
## 46. `action="store_true"`

```python
parser.add_argument(
    "--use_moe",
    action="store_true"
)
```

如果不写：

```text
use_moe=False
```

如果命令：

```bash
--use_moe
```

那么：

```text
use_moe=True
```

不需要写：

```bash
--use_moe true
```

---

<a id="origin-2238"></a>
## 47. `.parse_args()`

```python
args = parser.parse_args()
```

真正解析命令行。

然后：

```python
args.batch_size
args.learning_rate
args.hidden_size
```

就能直接访问。

---

<a id="origin-2258"></a>
## 48. `.error()`

```python
parser.error(...)
```

用于：

```text
参数非法时立即终止程序
```

例如：

```text
hidden_size 不是 16 的倍数。
```

---

<a id="origin-2278"></a>
## 49. `torch.cuda.is_available()`

```python
torch.cuda.is_available()
```

检查当前 PyTorch 能不能使用：

```text
CUDA GPU。
```

于是默认：

```python
"cuda:0"
```

或者：

```python
"cpu"
```

---

<a id="origin-2304"></a>
## 50. `torch.manual_seed`

```python
torch.manual_seed(42)
```

固定：

```text
PyTorch 随机数种子。
```

例如影响：

```text
Reward Head 随机初始化
DataLoader shuffle
```

等随机过程。

但不能保证：

```text
所有硬件
所有 CUDA 版本
所有 PyTorch 版本
```

完全逐 bit 一致。

---

<a id="origin-2337"></a>
## 51. `torch.optim.AdamW`

```python
optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=args.learning_rate
)
```

创建 AdamW 优化器。

关键是：

```python
model.parameters()
```

这里包括：

```text
MiniMind Backbone
+
Reward Head
```

所以这个程序：

> **不是只训练 Reward Head。**

而是：

> **整个 MiniMind + Reward Head 一起 Fine-tune。**



---

<a id="origin-2374"></a>
## 52. `model.parameters()`

遍历模型里所有：

```text
requires_grad=True
```

的参数。

因为这里没有冻结 Backbone，所以包括：

```text
Embedding
Q/K/V
Attention
FFN
Norm
Reward Head
...
```

---

<a id="origin-2398"></a>
## 53. Tensor `.chunk(2)`（重点）

代码：

```python
chosen, rejected = scores.chunk(2)
```

假设：

```text
scores =

[
 c0,
 c1,
 c2,
 r0,
 r1,
 r2
]
```

调用：

```python
chunk(2)
```

沿第 0 维平均切成：

```text
chosen =
[c0,c1,c2]

rejected =
[r0,r1,r2]
```

前面 `collate()` 为什么一定组织成：

```text
所有 chosen
+
所有 rejected
```

现在就明白了。

---

<a id="origin-2449"></a>
## 54. `.float()`

```python
chosen.float()
```

明确把 Tensor 转成：

```text
FP32
```

这里 Ranking Loss 用 FP32 计算。

而整个脚本本来也没有：

```text
autocast
GradScaler
```

所以这是一个非常纯粹的：

```text
FP32 教学实现。
```

---

<a id="origin-2478"></a>
## 55. `F.logsigmoid()`（重点）

核心来了：

```python
F.logsigmoid(
    chosen - rejected
)
```

先定义：

\[
\Delta=r_c-r_r
\]

sigmoid：

\[
\sigma(\Delta)
=
\frac{1}{1+e^{-\Delta}}
\]

然后：

\[
\log\sigma(\Delta)
\]

`logsigmoid()` 直接把两步合起来。

比：

```python
torch.log(torch.sigmoid(x))
```

数值更稳定。

---

<a id="origin-2520"></a>
## 56. `.mean()`

```python
.mean()
```

把整个 Batch：

```text
B 个偏好对的 Loss
```

求平均。

注意：

不是：

```text
对 Token 求平均。
```

Reward Model 一个偏好对只产生：

```text
一个 Pairwise Loss。
```

---

<a id="origin-2550"></a>
## 57. `optimizer.zero_grad(set_to_none=True)`

在 PyTorch 中：

```text
gradient 默认是累积的。
```

例如：

第一批：

\[
g_1
\]

第二次 backward 如果不清：

\[
g_1+g_2
\]

但这个程序不做梯度累积。

所以每个 Batch：

```python
optimizer.zero_grad()
```

先把旧梯度清掉。

---

<a id="origin-2584"></a>
### 57.1 `set_to_none=True`

不是把：

```text
.grad = 0
```

而是：

```text
.grad = None
```

下一次 backward 再新建梯度。

---

<a id="origin-2602"></a>
## 58. `loss.backward()`

这是训练的关键。

```python
loss.backward()
```

执行：

> 根据计算图使用链式法则，计算 Loss 对所有模型参数的梯度。

注意：

这一步：

```text
只计算 gradient
```

没有修改参数。

---

<a id="origin-2626"></a>
## 59. `nn.utils.clip_grad_norm_`

```python
nn.utils.clip_grad_norm_(
    model.parameters(),
    1.0
)
```

计算：

```text
所有模型参数梯度组成的整体 L2 Norm
```

如果超过：

```text
1.0
```

统一缩小。

例如梯度整体范数：

```text
5
```

那么大概整体乘：

\[
\frac{1}{5}
\]

变成范数：

```text
1
```

防止梯度爆炸。

注意：

> 裁剪的是 Gradient，不是 Reward。

---

<a id="origin-2675"></a>
## 60. `optimizer.step()`

```python
optimizer.step()
```

这一步才真正：

```text
修改模型参数。
```

所以训练顺序一定是：

```text
zero_grad
↓
forward
↓
loss
↓
backward
↓
clip gradient
↓
optimizer.step
```

严格地说这个文件是先 forward/loss，再 `zero_grad()`，也是完全成立的，因为清零只需要发生在本次 backward 之前。文件实际训练循环见这里。

---

<a id="origin-2707"></a>
## 61. 第二部分：Reward Model 到底是怎么训练出来的？

下面真正把它掰开来讲。

---

<a id="origin-2713"></a>
## 62. 第一阶段：Reward Model 的数据到底是什么？（重点）

假设数据：

```json
{
  "chosen": [
    {
      "role": "user",
      "content": "太阳从哪里升起？"
    },
    {
      "role": "assistant",
      "content": "太阳从东方升起。"
    }
  ],

  "rejected": [
    {
      "role": "user",
      "content": "太阳从哪里升起？"
    },
    {
      "role": "assistant",
      "content": "太阳从西方升起。"
    }
  ]
}
```

注意：

Reward Model 数据不是：

```text
Question → Correct Answer
```

而是：

```text
相同上下文

       ┌─ Answer A：更好
Prompt
       └─ Answer B：更差
```

---

<a id="origin-2763"></a>
## 63. 为什么必须是相同 Prompt？

因为我们的监督信号：

\[
r_c>r_r
\]

想表达：

> 对于**同一个问题**，回答 A 比回答 B 好。

如果：

```text
chosen：
1+1？ → 2

rejected：
法国首都？ → 伦敦
```

然后要求：

```text
chosen > rejected
```

根本不知道究竟比较的是什么。

因此代码检查：

```python
chosen[:-1] == rejected[:-1]
```

也就是：

```text
除了最后一个 assistant 回答
历史必须完全相同。
```

---

<a id="origin-2808"></a>
## 64. 为什么 `[:-1]`？（重点）

假设：

```text
chosen =

[
 user: Q1
 assistant: A1
 user: Q2
 assistant: 好答案
]
```

```text
rejected =

[
 user: Q1
 assistant: A1
 user: Q2
 assistant: 差答案
]
```

最后一条：

```text
最终 Answer
```

不同。

但是前面：

```text
Q1
A1
Q2
```

**必须一致。
**
所以：

```python
chosen[:-1]
rejected[:-1]
```

就是：

```text
去掉最后回答以后比较历史。
```

---

<a id="origin-2867"></a>
## 65. 第二阶段：把两条对话转换成 Token

假设：

```text
Prompt：
1+1?

chosen：
2

rejected：
5
```

为了方便教学，假设 Tokenize 后：

```text
chosen:

[1,10,20,2]
```

```text
rejected:

[1,10,21,2]
```

可以理解：

```text
1  = 开始/角色标记
10 = Prompt
20 = chosen answer
21 = rejected answer
2  = EOS
```

真实 MiniMind Tokenizer 当然不会这么简单。

---

<a id="origin-2910"></a>
## 66. 第三阶段：Batch 如何组织？

假设：

```text
B=2
```

也就是有两个偏好对：

```text
Pair 0：
c0
r0

Pair 1：
c1
r1
```

程序组织成：

```text
[
 c0,
 c1,
 r0,
 r1
]
```

所以真正 Transformer 输入数量：

\[
N=2B
\]

如果：

```text
batch_size=32
```

意味着：

```text
32 对
```

实际上前向：

```text
64 条序列。
```

---

<a id="origin-2967"></a>
## 67. 第四阶段：Reward Model **的模型结构**

这个 Reward Model 本质：

```text
MiniMind Backbone
+
Linear Reward Head
```

即：

```text
Token IDs

   ↓

Embedding

   ↓

Transformer Block 1

   ↓

Transformer Block 2

   ↓

...

   ↓

Transformer Block L

   ↓

Hidden States
[N,T,H]

   ↓

最后真实 Token
[N,H]

   ↓

Linear(H,1)

   ↓

Reward
[N]
```

---

<a id="origin-3024"></a>
## 68. 和普通语言模型差在哪里？

普通 Causal LM：

```text
Hidden State
    ↓
LM Head
    ↓
Vocabulary logits
```

如果：

```text
Vocab = 6400
```

每个位置：

```text
H → 6400
```

输出：

```text
下一个 Token 的概率。
```

Reward Model：

```text
Hidden State
    ↓
Reward Head
    ↓
1 个数字
```

：

```text
H → 1
```

不生成 Token。

---

<a id="origin-3074"></a>
## 69. 第五阶段：为什么首先加载 SFT 模型？

默认程序加载：

```text
full_sft_768.pth
```

这一点很重要。

想象一个完全随机 Transformer：

```text
"1+1等于2"

和

"1+1等于香蕉"
```

它连文字语义都不知道。

Reward Model 训练数据通常远小于语言模型预训练数据。

所以更加合理的是：

```text
已经会语言的 SFT Model

        ↓

拿掉 LM Head

        ↓

加 Reward Head

        ↓

训练 Preference
```

因此：

```text
SFT
已经学会“理解文本”

Reward Training
进一步学会“什么回答更好”
```

---

<a id="origin-3128"></a>
## 70. SFT 哪些参数被加载？

原来的 SFT State Dict 可能：

```text
model.embed_tokens.weight

model.layers.0....

model.layers.1....

...

lm_head.weight
```

程序：

```python
backbone = {
    k[len("model."):]: v
    for k,v in weights.items()
    if k.startswith("model.")
}
```

只选：

```text
model.*
```

也就是说：

```text
MiniMind Backbone
```

被拿出来。

而：

```text
lm_head.weight
```

不会加载。

然后：

```python
model.model.load_state_dict(backbone)
```

加载进 Reward Model 的 Backbone。

具体实现见文件。

---

<a id="origin-3188"></a>
## 71. 所以训练开始时是什么状态？

可以理解成：

```text
MiniMind Backbone：

已经经过 SFT
懂语言、懂问题、懂回答


Reward Head：

随机初始化
还不知道什么叫“好”
```

然后 Preference Dataset 开始教它：

```text
这种 Hidden State → 分数应该更高

那种 Hidden State → 分数应该更低
```

与此同时：

> Backbone 也会继续调整。

---

<a id="origin-3219"></a>
## 72. 第六阶段：Transformer 得到什么？

假设：

```text
N=4
T=6
H=768
```

输入：

```text
input_ids.shape

[4,6]
```

进入 MiniMind：

```python
hidden, _, aux_loss =
    self.model(...)
```

得到：

```text
hidden.shape

[4,6,768]
```

什么意思？

4 条句子。

每条 6 个 Token。

每个 Token：

```text
768 维 Hidden State。
```

---

<a id="origin-3266"></a>
## 73. 举一条序列

比如：

```text
用户
：
1+1
？
助手
：
2
<EOS>
```

每一个位置都有：

\[
h_1,h_2,\dots,h_T
\]

其中：

\[
h_T\in\mathbb R^{768}
\]

因为 Transformer 是 Decoder-only 因果注意力：

\[
h_T
\]

能够看到：

\[
x_1,x_2,\dots,x_T
\]

所以：

```text
h_T
```

不是只代表：

```text
EOS
```

它实际上已经融合：

```text
Prompt + Answer
```

的信息。

---

<a id="origin-3327"></a>
## 74. 第七阶段：Reward Head 怎么打分？

假设为了手算：

```text
H=4
```

最后 Hidden State：

\[
h=
[2,0,0,0]
\]

Reward Head：

\[
w=
[0.5,-0.5,0.25,0]
\]

那么：

\[
r=w h
\]

：

\[
r=
2\times0.5
+0\times(-0.5)
+0\times0.25
+0\times0
\]

得到：

\[
r=1
\]

于是这个完整回答：

```text
Reward = 1
```

---

<a id="origin-3379"></a>
## 75. 这是不是概率？

不是。

Reward 可以：

```text
10

2

0

-1

-100
```

没有要求：

\[
0\le r\le1
\]

所以：

```text
reward = 0.9
```

不能解释成：

```text
90% 是好答案。
```

这是一个：

```text
未校准标量。
```

---

<a id="origin-3423"></a>
## 76. 第八阶段：Chosen 和 Rejected 分数

假设一个 Batch：

```text
B=2
```

前向得到：

```text
scores =

[
 1.0,
 0.0,
-1.0,
 1.0
]
```

因为排列：

```text
[c0,c1,r0,r1]
```

所以：

```python
chosen, rejected = scores.chunk(2)
```

得到：

```text
chosen =
[1.0,0.0]
```

```text
rejected =
[-1.0,1.0]
```

因此：

第一对：

```text
chosen = 1
rejected = -1
```

第二对：

```text
chosen = 0
rejected = 1
```

---

<a id="origin-3486"></a>
## 77. 第九阶段：真正核心的 Reward Model 数学

我们并没有：

```text
chosen 的正确 Reward 标签
rejected 的正确 Reward 标签
```

只有：

```text
chosen 应该 > rejected
```

所以首先计算：

\[
\Delta=r_c-r_r
\]

---

<a id="origin-3509"></a>
### 77.1 第一对

\[
r_c=1
\]

\[
r_r=-1
\]

因此：

\[
\Delta=2
\]

---

<a id="origin-3527"></a>
### 77.2 第二对

\[
r_c=0
\]

\[
r_r=1
\]

因此：

\[
\Delta=-1
\]

---

<a id="origin-3545"></a>
## 78. 为什么用 Sigmoid？

定义：

\[
P(c\succ r)
=
\sigma(r_c-r_r)
\]

其中：

\[
\sigma(x)
=
\frac1{1+e^{-x}}
\]

它可以理解为：

> Reward Model 认为 chosen 胜过 rejected 的概率。

注意：

这里：

```text
Reward 本身不是概率
```

但是：

```text
Reward 差经过 Sigmoid
```

可以作为 Pairwise Preference Probability。

---

<a id="origin-3585"></a>
## 79. 第一对

\[
\Delta=2
\]

所以：

\[
\sigma(2)
=
\frac1{1+e^{-2}}
\approx0.8808
\]

意思：

```text
模型认为 chosen 比 rejected 好的概率约 88.08%
```

---

<a id="origin-3608"></a>
## 80. 第二对

\[
\Delta=-1
\]

：

\[
\sigma(-1)
\approx0.2689
\]

意思：

```text
模型只认为 chosen 有 26.89% 概率比 rejected 好。
```

说明当前模型：

```text
排反了。
```

---

<a id="origin-3635"></a>
## 81. 为什么 Loss 是负对数？

我们的标签永远是：

```text
chosen 胜出
```

也就是目标概率：

```text
1
```

因此采用 Negative Log Likelihood：

\[
L
=
-\log P(c\succ r)
\]

**\(\succ\)代表“优于”，** 代入：

\[
P(c\succ r)=
\sigma(r_c-r_r)
\]

得到：

\[
\boxed{
L=
-\log\sigma(r_c-r_r)
}
\]

这就是 Reward Model 最核心的公式。

代码正是：

```python
ranking_loss = -F.logsigmoid(
    chosen.float() - rejected.float()
).mean()
```



---

<a id="origin-3687"></a>
## 82. 三种最重要的情况

<a id="origin-3689"></a>
### 82.1 情况 1：chosen 明显更高

\[
r_c=2
\]

\[
r_r=0
\]

所以：

\[
\Delta=2
\]

：

\[
P=0.881
\]

Loss：

\[
L=-\log0.881
\approx0.127
\]

很小。

模型：

```text
做对了。
```

---

<a id="origin-3728"></a>
## 83. 情况 2：两个分数相等

\[
r_c=0
\]

\[
r_r=0
\]

于是：

\[
\Delta=0
\]

：

\[
\sigma(0)=0.5
\]

Loss：

\[
-\log0.5
=
0.693
\]

模型相当于：

```text
完全不知道哪一个好。
```

---

<a id="origin-3766"></a>
## 84. 情况 3：模型排反了

\[
r_c=0
\]

\[
r_r=2
\]

所以：

\[
\Delta=-2
\]

：

\[
\sigma(-2)=0.119
\]

Loss：

\[
-\log0.119
\approx2.127
\]

Loss 很大。

说明：

```text
不仅没区分出来，而且还反着排。
```

---

<a id="origin-3805"></a>
## 85. 这个 Loss 到底想做什么？

目标就是：

\[
r_c-r_r
\]

越来越大。

也就是：

```text
chosen 分高一点
rejected 分低一点
```

更准确地说：

```text
把二者的差拉大。
```

---

<a id="origin-3830"></a>
## 86. 从求导彻底看懂

定义：

\[
\Delta=r_c-r_r
\]

Loss：

\[
L=-\log\sigma(\Delta)
\]

它可以化成：

\[
L=\log(1+e^{-\Delta})
\]

对 \(\Delta\) 求导：

\[
\frac{\partial L}{\partial\Delta}
=
\sigma(\Delta)-1
\]

---

<a id="origin-3860"></a>
## 87. 假设两个分数一样

\[
r_c=0
\]

\[
r_r=0
\]

所以：

\[
\Delta=0
\]

\[
\sigma(0)=0.5
\]

于是：

\[
\frac{\partial L}{\partial\Delta}
=
0.5-1
=
-0.5
\]

梯度下降：

\[
\Delta_{\text{new}}
=
\Delta
-
\eta(-0.5)
\]

：

\[
\Delta_{\text{new}}
=
\Delta
+
0.5\eta
\]

所以：

\[
\Delta
\]

会增大。

这正是我们想要的。

---

<a id="origin-3922"></a>
## 88. 分别对 chosen 和 rejected 求导

因为：

\[
\Delta=r_c-r_r
\]

所以：

\[
\frac{\partial\Delta}{\partial r_c}=1
\]

：

\[
\boxed{
\frac{\partial L}{\partial r_c}
=
\sigma(\Delta)-1
}
\]

而：

\[
\frac{\partial\Delta}{\partial r_r}=-1
\]

所以：

\[
\boxed{
\frac{\partial L}{\partial r_r}
=
1-\sigma(\Delta)
}
\]

---

<a id="origin-3964"></a>
## 89. 还是用两个分数相等的情况

\[
\Delta=0
\]

：

\[
\sigma(0)=0.5
\]

所以：

\[
\frac{\partial L}{\partial r_c}
=
-0.5
\]

\[
\frac{\partial L}{\partial r_r}
=
+0.5
\]

梯度下降：

Chosen：

\[
r_c'
=
r_c-\eta(-0.5)
\]

：

\[
r_c'=r_c+0.5\eta
\]

也就是：

```text
chosen 上升。
```

Rejected：

\[
r_r'
=
r_r-\eta(0.5)
\]

：

\[
r_r'=r_r-0.5\eta
\]

也就是：

```text
rejected 下降。
```

于是二者分开。

---

<a id="origin-4036"></a>
## 90. 这就是 Reward Model 训练的核心

可以把整个 Reward Training 理解成：

```text
人工：
这个好
这个差

     ↓

Reward Model：
给两个答案各自打分

     ↓

比较：
你现在有没有让好答案 > 差答案？

     ↓

如果没有：
调整模型

     ↓

让：
chosen ↑
rejected ↓

或者至少：
chosen - rejected ↑
```

---

<a id="origin-4072"></a>
## 91. Reward Head 是怎么被更新的？

Reward：

\[
r=w^Th
\]

Chosen：

\[
r_c=w^Th_c
\]

Rejected：

\[
r_r=w^Th_r
\]

因此：

\[
\Delta
=
w^T(h_c-h_r)
\]

设：

\[
g=
\frac{\partial L}{\partial\Delta}
\]

则：

\[
\boxed{
\frac{\partial L}{\partial w}
=
g(h_c-h_r)
}
\]

这句话非常重要。

Reward Head 实际学习：

> **哪些 Hidden-State 特征能够区分好回答与差回答。**

---

<a id="origin-4125"></a>
## 92. 一个最简单的数值例子

假设：

\[
h_c=
[2,1]
\]

\[
h_r=
[0,1]
\]

初始：

\[
w=
[0,0]
\]

因此：

\[
r_c=0
\]

：

\[
r_r=0
\]

：

\[
\Delta=0
\]

因此：

\[
g=-0.5
\]

而：

\[
h_c-h_r
=
[2,0]
\]

所以：

\[
\frac{\partial L}{\partial w}
=
-0.5[2,0]
\]

：

\[
[-1,0]
\]

如果：

\[
\eta=0.1
\]

梯度下降：

\[
w'
=
w-\eta\nabla w
\]

：

\[
w'
=
[0,0]-0.1[-1,0]
\]

：

\[
w'=[0.1,0]
\]

重新评分：

Chosen：

\[
r_c
=
0.1\times2
=
0.2
\]

Rejected：

\[
r_r
=
0.1\times0
=
0
\]

于是：

\[
r_c>r_r
\]

模型学会：

```text
Hidden State 第一维出现这种特征，
可能意味着这是更好的回答。
```

---

<a id="origin-4257"></a>
## 93. 那为什么 Backbone 也会更新？

因为：

\[
r=w^Th
\]

Reward Head 的输入：

\[
h
\]

不是固定特征。

它来自：

```text
Transformer。
```

所以：

\[
L
\rightarrow
r
\rightarrow
h
\rightarrow
Transformer
\]

梯度还会继续传播。

---

<a id="origin-4295"></a>
## 94. 对 Hidden State 的梯度

Chosen：

\[
r_c=w^Th_c
\]

因此：

\[
\frac{\partial r_c}{\partial h_c}
=
w
\]

于是：

\[
\frac{\partial L}{\partial h_c}
=
\frac{\partial L}{\partial r_c}w
\]

Rejected 同样：

\[
\frac{\partial L}{\partial h_r}
=
\frac{\partial L}{\partial r_r}w
\]

然后：

```text
Hidden State
↓
Transformer 最后一层
↓
上一层
↓
...
↓
Embedding
```

梯度一路往前传播。

---

<a id="origin-4345"></a>
## 95. 所以 Reward Model 不是：

```text
固定 SFT
+
训练一个简单 Linear
```

这个程序实际上是：

```text
SFT 参数作为初始化

         ↓

Reward Head 随机初始化

         ↓

整个模型一起训练
```

因此：

```text
Attention 参数会变
FFN 参数会变
Embedding 会变
Norm 会变
Reward Head 会变
```

---

<a id="origin-4379"></a>
## 96. 为什么这样训练后模型能够知道“答案好不好”？

因为大量数据不断提供：

```text
这种回答 > 那种回答
```

例如：

```text
正确回答 > 错误回答

完整回答 > 答非所问

安全回答 > 危险回答

遵循指令 > 不遵循指令

有事实依据 > 胡编乱造
```

如果训练数据里真的包含这些偏好，

模型就会逐渐调整：

```text
Hidden Representation
```

和：

```text
Reward Head
```

使得这些回答之间出现稳定的 Score 差异。

---

<a id="origin-4419"></a>
## 97. 一个很重要的理解：Reward Head 并不直接看文字

Reward Head 看到的是：

\[
h_{\text{last}}
\]

例如：

```text
768 个浮点数。
```

不是直接：

```text
“太阳从东方升起”
```

真正理解自然语言的是：

```text
MiniMind Backbone。
```

Reward Head 做的是：

```text
768 维语义表示
      ↓
一个方向投影
      ↓
Reward
```

---

<a id="origin-4457"></a>
## 98. 可以把 Reward Head 想象成一把“评分尺”

假设 Hidden Space 中：

```text
某些方向
=
事实正确性

某些方向
=
相关性

某些方向
=
完整性

某些方向
=
安全性

某些方向
=
语言质量
```

这是概念上的理解，并不是说某个神经元严格对应某一种属性。

Reward Head：

\[
r=w^Th
\]

相当于学：

```text
这些特征应该分别给多大的权重。
```

---

<a id="origin-4499"></a>
## 99. 但是 Backbone 也训练，所以比“一把固定尺”更强 （重点）

因为训练同时还可以让：

```text
Hidden Space 本身发生变化。
```

也就是说：

```text
不仅学习怎么用尺子量

还学习怎样把答案表示得更容易被这把尺子区分。
```

---

<a id="origin-4517"></a>
## 100. 第十阶段：一个 Batch 完整手算

假设：

```text
B=2
```

模型得到：

\[
r_c=[1,0]
\]

\[
r_r=[-1,1]
\]

---

<a id="origin-4537"></a>
### 100.1 Pair 1

\[
\Delta_1=1-(-1)=2
\]

\[
L_1
=
-\log\sigma(2)
\]

：

\[
L_1\approx0.126928
\]

---

<a id="origin-4557"></a>
### 100.2 Pair 2

\[
\Delta_2=0-1=-1
\]

：

\[
L_2
=
-\log\sigma(-1)
\]

：

\[
L_2\approx1.313262
\]

---

<a id="origin-4579"></a>
### 100.3 Batch Mean

\[
L
=
\frac{L_1+L_2}{2}
\]

：

\[
L
=
\frac{
0.126928+1.313262
}{2}
\]

：

\[
\boxed{
L\approx0.720095
}
\]

这个数字和文件给出的教学例子完全一致。

---

<a id="origin-4609"></a>
## 101. Accuracy 是怎么算的？

代码：

```python
accuracy = (
    chosen > rejected
).float().mean()
```

还是：

```text
chosen =
[1,0]

rejected =
[-1,1]
```

比较：

```text
1 > -1
True

0 > 1
False
```

转换：

```text
[1,0]
```

平均：

\[
\frac{1+0}{2}=0.5
\]

所以：

```text
accuracy=0.5
```

---

<a id="origin-4659"></a>
## 102. 这个 Accuracy 是不是 Reward Model 的最终准确率？

不是。

文件自己特别提醒：

> 这里只是当前 Training Batch 的 Preference Ranking Accuracy。

它不是：

```text
验证集准确率
测试集准确率
真实世界准确率
```

这个程序甚至：

```text
没有 Validation Loop。
```

---

<a id="origin-4683"></a>
## 103. Chosen 和 Rejected 日志是什么意思？

代码输出：

```text
chosen=...
rejected=...
```

例如：

```text
chosen=0.500
rejected=0.000
```

只是：

```text
当前 Batch 中 chosen 原始 Reward 的平均值

和

rejected 原始 Reward 的平均值。
```

不要理解成：

```text
50% 与 0%。
```

---

<a id="origin-4717"></a>
## 104. 第十一阶段：MoE 的 `aux_loss`

程序：

```python
scores, aux_loss = model(...)
```

然后：

\[
L
=
L_{\text{ranking}}
+
L_{\text{aux}}
\]

对于普通 Dense MiniMind：

```text
aux_loss = 0
```

所以：

\[
L=L_{\text{ranking}}
\]

如果使用 MoE：

```text
aux_loss
```

主要用于：

```text
专家负载均衡
```

防止所有 Token 都跑到少数 Expert。

---

<a id="origin-4763"></a>
## 105. 一次参数更新到底发生了什么？

完整顺序：

```text
input_ids
mask
   │
   ▼
MiniMind
   │
   ▼
hidden
   │
   ▼
final_hidden
   │
   ▼
reward_head
   │
   ▼
scores
   │
   ▼
chosen/rejected
   │
   ▼
ranking_loss
   │
   ▼
loss.backward()
   │
   ├── reward_head.grad
   │
   ├── attention.grad
   │
   ├── FFN.grad
   │
   ├── embedding.grad
   │
   └── ...
   │
   ▼
clip_grad_norm
   │
   ▼
AdamW.step()
   │
   ▼
新的模型参数
```

---

<a id="origin-4817"></a>
## 106. 一个特别容易搞错的地方

`backward()`：

```text
不会修改参数。
```

只会得到：

```text
parameter.grad
```

真正修改参数：

```python
optimizer.step()
```

---

<a id="origin-4839"></a>
## 107. 下一 Batch 用的是不是新模型？

是。

例如：

```text
Batch 1
↓
forward
↓
backward
↓
optimizer.step
```

参数已经更新。

所以：

```text
Batch 2
```

的 Forward 用的是：

```text
更新后的 Reward Model。
```

---

<a id="origin-4871"></a>
## 108. 整个训练从时间顺序完整走一次（重点）

现在把程序真正完整走一遍。

---

<a id="origin-4877"></a>
### 108.1 Step 1：加载 Tokenizer

```text
文字
↓
Token ID
```

---

<a id="origin-4887"></a>
### 108.2 Step 2：创建 Reward Model

```text
MiniMind Backbone
+
Reward Head
```

---

<a id="origin-4897"></a>
### 108.3 Step 3：加载 SFT Backbone

默认：

```text
从 SFT Model 读取 model.* 参数
```

但：

```text
LM Head 不需要。
```

---

<a id="origin-4913"></a>
### 108.4 Step 4：读取 Preference Data

每一行：

```text
chosen
rejected
```

---

<a id="origin-4924"></a>
### 108.5 Step 5：检查两个回答是否对应同一个历史

```text
chosen[:-1]
==
rejected[:-1]
```

---

<a id="origin-4934"></a>
### 108.6 Step 6：应用 Chat Template

例如：

```text
user:
1+1?

assistant:
2
```

变成模型标准聊天格式。

---

<a id="origin-4950"></a>
### 108.7 Step 7：Tokenizer

```text
字符串
↓
Token IDs
```

---

<a id="origin-4960"></a>
### 108.8 Step 8：过滤非法数据

过滤：

```text
过长

空答案

chosen == rejected

非法消息结构
```

---

<a id="origin-4976"></a>
### 108.9 Step 9：DataLoader 取 B 个 Pair

例如：

```text
B=2
```

---

<a id="origin-4986"></a>
### 108.10 Step 10：Collate

变成：

```text
[c0,c1,r0,r1]
```

进行动态 Padding。

得到：

```text
input_ids : [2B,T]

mask      : [2B,T]
```

---

<a id="origin-5006"></a>
### 108.11 Step 11：送入 MiniMind

得到：

```text
hidden :
[2B,T,H]
```

---

<a id="origin-5017"></a>
### 108.12 Step 12：找到每条序列的最后真实 Token

```text
length =
mask.sum(dim=1)
```

：

```text
last=length-1
```

---

<a id="origin-5032"></a>
### 108.13 Step 13：取最终 Hidden

得到：

```text
final_hidden :
[2B,H]
```

---

<a id="origin-5043"></a>
### 108.14 Step 14：Reward Head

\[
r=W_rh
\]

得到：

```text
scores :
[2B]
```

---

<a id="origin-5058"></a>
### 108.15 Step 15：拆回两组

```text
chosen :
[B]

rejected :
[B]
```

---

<a id="origin-5070"></a>
### 108.16 Step 16：计算 Score Difference

\[
\Delta_i
=
r_{c,i}-r_{r,i}
\]

---

<a id="origin-5080"></a>
### 108.17 Step 17：计算 Preference Probability

\[
P_i
=
\sigma(\Delta_i)
\]

---

<a id="origin-5090"></a>
### 108.18 Step 18：计算 Pairwise Loss

\[
L_i
=
-\log P_i
\]

：

\[
L_i
=
-\log
\sigma(r_{c,i}-r_{r,i})
\]

---

<a id="origin-5109"></a>
### 108.19 Step 19：Batch 平均

\[
L_{\text{ranking}}
=
-\frac1B
\sum_{i=1}^{B}
\log\sigma(
r_{c,i}-r_{r,i}
)
\]

---

<a id="origin-5123"></a>
### 108.20 Step 20：加 MoE Loss

\[
L
=
L_{\text{ranking}}
+
L_{\text{aux}}
\]

---

<a id="origin-5135"></a>
### 108.21 Step 21：清空 Gradient

```python
optimizer.zero_grad()
```

---

<a id="origin-5143"></a>
### 108.22 Step 22：Backpropagation

```python
loss.backward()
```

梯度：

```text
Loss

↓
Reward Difference

↓
Chosen Score + Rejected Score

↓
Reward Head

↓
Last Hidden State

↓
Transformer

↓
全部 Backbone 参数
```

---

<a id="origin-5175"></a>
### 108.23 Step 23：Gradient Clipping

```python
clip_grad_norm_(...,1.0)
```

---

<a id="origin-5183"></a>
### 108.24 Step 24：AdamW 更新

```python
optimizer.step()
```

---

<a id="origin-5191"></a>
### 108.25 Step 25：继续下一 Batch

不断重复。

---

<a id="origin-5197"></a>
## 109. 训练结束后模型学到了什么？（重点）

最后得到的是一个函数：

\[
R_\theta(x,y)
\]

其中：

```text
x = Prompt / 对话历史

y = Response
```

输入：

```text
Prompt + Response
```

输出：

```text
一个 Reward。
```

---

<a id="origin-5227"></a>
## 110. 推理的时候怎么用？

例如：

```text
Prompt：
1+1等于几？

Response：
等于2。
```

组成：

```python
[
 {
   "role":"user",
   "content":"1+1等于几？"
 },
 {
   "role":"assistant",
   "content":"等于2。"
 }
]
```

然后：

```text
Chat Template
↓
Tokenizer
↓
MiniMind
↓
最后 Hidden
↓
Reward Head
↓
Reward
```

例如：

```text
reward = 2.17
```

---

<a id="origin-5278"></a>
## 111. 如果另一个答案得到：

```text
reward = -0.82
```

那么可以说：

```text
Reward Model 更偏好第一个。
```

但是不能轻易说：

```text
第一个是 2.17 分水平
第二个是 -0.82 分水平
```

因为 Pairwise Training 只约束：

\[
r_c-r_r
\]

绝对零点本身没有明确物理意义。

---

<a id="origin-5307"></a>
## 112. 为什么 Reward 可以整体平移？

例如原来：

```text
chosen = 2
rejected = 0
```

差：

\[
2
\]

如果都加 100：

```text
chosen = 102
rejected = 100
```

差仍然：

\[
2
\]

因此：

\[
\sigma(2)
\]

完全没变化。

也就是说训练目标对：

\[
r\rightarrow r+C
\]

是不敏感的。

这也是为什么：

> Reward 的绝对数值不要过度解释。

---

<a id="origin-5357"></a>
## 113. 甚至 Score Scale 也不是天然“标准分”

例如：

```text
Model A：
chosen=2
rejected=0
```

与：

```text
Model B：
chosen=20
rejected=0
```

不意味着：

```text
Model B 的回答质量是 A 的十倍。
```

只是模型内部 Reward 尺度不同。

---

<a id="origin-5385"></a>
## 114. Reward Model 和 SFT 的最核心区别

<a id="origin-5387"></a>
### 114.1 SFT

数据：

```text
Prompt
↓
Target Answer
```

目标：

\[
P(y|x)
\]

Loss：

```text
每个 Token 的 Cross Entropy
```

模型学习：

> 什么回答应该被生成。

---

<a id="origin-5415"></a>
### 114.2 Reward Model

数据：

```text
Prompt

chosen answer

rejected answer
```

目标：

\[
R(x,y_c)>R(x,y_r)
\]

Loss：

\[
-\log
\sigma(
R(x,y_c)-R(x,y_r)
)
\]

模型学习：

> 哪个回答更值得偏好。

---

<a id="origin-5448"></a>
## 115. Reward Model 的输出为什么可以是无界标量（重点）？

<a id="origin-5450"></a>
## 116. 问题

Reward Model 最后输出的是一个标量：

\[
r = R_\theta(x,y)
\]

例如：

```text
回答 A：reward = 2.3
回答 B：reward = -0.7
```

这个分数通常没有经过 `sigmoid` 或 `tanh`，所以理论上：

\[
r \in (-\infty,+\infty)
\]

于是自然会产生一个问题：

> 如果 Reward 可以无限大或者无限小，会不会导致训练出问题？

答案是：

> **理论上确实存在把分数差不断拉大的趋势，但随着 chosen 和 rejected 已经被明显区分，梯度会迅速趋近于 0。真正需要注意的是：Pairwise Reward Model 只约束相对大小，并没有定义 Reward 的绝对标尺。**

---

<a id="origin-5481"></a>
## 117. Reward Model 真正优化的不是单个 Reward，而是分数差

Pairwise Reward Model 的损失通常为：

\[
L
=
-\log \sigma(r_c-r_r)
\]

其中：

- \(r_c\)：chosen 的 Reward
- \(r_r\)：rejected 的 Reward

定义：

\[
\Delta = r_c-r_r
\]

于是：

\[
L=-\log\sigma(\Delta)
\]

因此训练真正关心的是：

\[
\boxed{r_c-r_r}
\]

而不是：

\[
r_c
\]

或者：

\[
r_r
\]

各自到底应该是多少。

---

<a id="origin-5530"></a>
## 118. 为什么确实存在“把差距越拉越大”的趋势？

例如：

\[
r_c=2,\qquad r_r=0
\]

那么：

\[
\Delta=2
\]

于是：

\[
\sigma(2)\approx0.881
\]

Loss：

\[
L=-\log(0.881)\approx0.127
\]

如果进一步变成：

\[
r_c=10,\qquad r_r=-10
\]

那么：

\[
\Delta=20
\]

此时：

\[
\sigma(20)\approx1
\]

所以：

\[
L\approx0
\]

也就是说，从纯数学目标看：

```text
chosen 比 rejected 高一点
```

虽然已经正确，但是：

```text
chosen 比 rejected 高很多
```

Loss 会更低。

因此 Pairwise Loss 确实存在：

\[
\boxed{\text{不断增大 }r_c-r_r\text{ 的倾向}}
\]

---

<a id="origin-5602"></a>
## 119. 那为什么实际不会一直疯狂涨到无穷大？

关键要看梯度。

对于：

\[
L=-\log\sigma(\Delta)
\]

有：

\[
\frac{\partial L}{\partial \Delta}
=
\sigma(\Delta)-1
\]

也可以写成：

\[
\frac{\partial L}{\partial \Delta}
=
-\sigma(-\Delta)
\]

看几个数值：

| \(\Delta=r_c-r_r\) | \(\sigma(\Delta)\) | \(\frac{\partial L}{\partial \Delta}\) |
|---:|---:|---:|
| 0 | 0.5000 | -0.5000 |
| 2 | 0.8808 | -0.1192 |
| 5 | 0.9933 | -0.0067 |
| 10 | 0.99995 | -0.000045 |
| 20 | 接近 1 | 接近 0 |

可以看到：

```text
分差小
↓
梯度大
↓
模型努力把 chosen 和 rejected 拉开
```

但是：

```text
分差已经很大
↓
梯度接近 0
↓
模型几乎不再继续推动这个样本
```

所以 Logistic / Bradley–Terry Loss 本身具有一种“软刹车”。

---

<a id="origin-5662"></a>
## 120. 例如：两个分数相等时

假设：

\[
r_c=0
\]

\[
r_r=0
\]

所以：

\[
\Delta=0
\]

此时：

\[
\sigma(0)=0.5
\]

因此：

\[
\frac{\partial L}{\partial \Delta}
=
0.5-1
=
-0.5
\]

梯度还很大。

模型会明显推动：

\[
r_c-r_r
\]

增大。

---

<a id="origin-5708"></a>
## 121. 但如果已经分得很开

例如：

\[
r_c=10
\]

\[
r_r=0
\]

则：

\[
\Delta=10
\]

：

\[
\frac{\partial L}{\partial \Delta}
\approx -0.000045
\]

几乎已经没有梯度。

可以理解成模型在说：

> 这个样本我已经非常确定 chosen 更好了，没有必要继续使劲拉开。

---

<a id="origin-5741"></a>
## 122. 更重要的问题：Reward 的绝对值其实没有意义

例如下面三组分数：

<a id="origin-5745"></a>
### 122.1 第一组

\[
r_c=2,\qquad r_r=0
\]

<a id="origin-5751"></a>
### 122.2 第二组

\[
r_c=102,\qquad r_r=100
\]

<a id="origin-5757"></a>
### 122.3 第三组

\[
r_c=-998,\qquad r_r=-1000
\]

三者都有：

\[
r_c-r_r=2
\]

因此：

\[
L=-\log\sigma(2)
\]

完全一样。

所以 Reward Model 根本没有学到：

```text
0 分应该代表什么
10 分应该代表什么
100 分应该代表什么
```

它只学到了：

\[
\boxed{\text{谁应该排在谁前面}}
\]

---

<a id="origin-5793"></a>
## 123. 因此 Reward 的“零点”是不确定的

例如：

```text
chosen = 2
rejected = 0
```

如果全部加 100：

```text
chosen = 102
rejected = 100
```

分差：

\[
102-100=2
\]

还是一样。

所以：

\[
\boxed{R(x,y)\rightarrow R(x,y)+C}
\]

不会改变 Pairwise Loss。

也就是说：

> **Reward 的绝对零点没有被 Pairwise Training 定义。**

---

<a id="origin-5831"></a>
## 124. Reward 的尺度也不是天然的“标准分”

例如：

```text
模型 A：

chosen = 2
rejected = 0
```

而另一个模型：

```text
模型 B：

chosen = 20
rejected = 0
```

不能说：

> 模型 B 认为这个回答比模型 A 好 10 倍。

因为不同 Reward Model 的分数尺度本来就可能完全不同。

所以 Reward 更适合解释成：

```text
模型内部的相对偏好分数
```

而不是：

```text
有固定单位的绝对质量分数
```

---

<a id="origin-5871"></a>
## 125. 为什么不直接在 Reward Head 后面加 sigmoid？

例如把：

\[
r=W^Th
\]

改成：

\[
r=\sigma(W^Th)
\]

这样 Reward 就被限制在：

\[
0<r<1
\]

看起来好像更加安全。

但是会出现问题。

因为 Reward Model 后面的 Pairwise Probability 又定义为：

\[
P(c\succ r)
=
\sigma(r_c-r_r)
\]

如果：

\[
0<r_c<1
\]

且：

\[
0<r_r<1
\]

那么最大的分差也只能接近：

\[
1-0=1
\]

于是最大的偏好概率只能接近：

\[
\sigma(1)
\approx0.731
\]

也就是说，即使模型极其确定：

```text
chosen 远远好于 rejected
```

最多也只能表达大约：

\[
73.1\%
\]

这就把模型表达能力限制得太死。

所以 Reward Head 通常直接输出：

\[
\boxed{(-\infty,+\infty)}
\]

范围内的实数。

---

<a id="origin-5952"></a>
## 126. Reward Head 后面为什么通常没有 sigmoid？

普通分类模型：

```text
logit
↓
sigmoid
↓
0~1 概率
```

但 Reward Model 不一样。

Reward 本身只是：

```text
一个 logit / score
```

真正变成“chosen 胜出的概率”的地方是：

\[
\boxed{
P(c\succ r)
=
\sigma(r_c-r_r)
}
\]

所以 sigmoid 用在：

```text
两个 Reward 的差
```

而不是：

```text
单个 Reward
```

上。

---

<a id="origin-5998"></a>
## 127. 从数学上看，它确实存在参数变大的可能

假设训练数据完全可以被模型正确分开。

只要：

\[
r_c>r_r
\]

那么把分差继续放大：

\[
r_c-r_r
\rightarrow+\infty
\]

就可以让：

\[
L\rightarrow0
\]

因此在理想化数学情况下，确实可能出现：

\[
\|W\|\rightarrow\infty
\]

的趋势。

这和 Logistic Regression 在完全线性可分数据上的现象很相似。

但是：

\[
r_c-r_r
\]

越大，梯度就越接近 0，所以这种增长会越来越慢。

---

<a id="origin-6041"></a>
## 128. 这份 `train_reward.py` 里还有两个机制帮助稳定训练

<a id="origin-6043"></a>
### 128.1 AdamW 的 Weight Decay

代码使用：

```python
optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=args.learning_rate
)
```

AdamW 带有 Weight Decay。

可以理解成：

```text
参数变得太大
↓
会受到一定惩罚
```

因此能够在一定程度上抑制：

\[
\|W\|
\]

无限增大。

---

<a id="origin-6074"></a>
### 128.2 Gradient Clipping

代码：

```python
nn.utils.clip_grad_norm_(
    model.parameters(),
    1.0
)
```

表示：

```text
如果这一轮所有参数梯度的整体范数 > 1
↓
把梯度统一缩小
```

例如：

\[
\|\nabla\|=5
\]

可能整体缩放成：

\[
\|\nabla\|=1
\]

注意：

> Gradient Clipping 限制的是梯度大小，不是 Reward 本身。

所以它主要防止：

```text
某一次更新突然非常大
```

而不是直接限制：

```text
Reward ∈ [-10,10]
```

---

<a id="origin-6123"></a>
## 129. 真正需要特别注意的是：Reward 给 PPO 使用的时候

如果 Reward Model 只是用来：

```text
比较回答 A 和 B 哪个更好
```

那么：

```text
A = 2
B = 0
```

和：

```text
A = 102
B = 100
```

其实差别不大。

因为都是：

\[
A-B=2
\]

但是 PPO 会把 Reward 真正放进强化学习计算。

例如：

```text
Reward
↓
Return
↓
Advantage
↓
PPO Loss
↓
Policy Gradient
```

如果 Reward 的尺度突然特别大：

```text
正常：

Reward = 2
```

变成：

```text
Reward = 2000
```

那么：

```text
Return 变大
↓
Advantage 变大
↓
Policy Gradient 可能变大
↓
Policy 更新过猛
```

所以 PPO 阶段通常还需要特别处理 Reward 的尺度。

---

<a id="origin-6199"></a>
## 130. PPO 中常见的稳定手段

例如：

```text
Reward Normalization
```

把 Reward 调整到相对稳定的分布。

或者：

```text
Reward Scaling
```

人为乘一个缩放系数。

或者：

```text
Reward Clipping
```

限制极端奖励。

另外还有：

```text
KL Penalty
```

防止 Policy 为了追求 Reward：

```text
疯狂偏离原来的 Reference Model
```

以及：

```text
Advantage Normalization
```

控制 PPO 最终真正使用的 Advantage 的尺度。

---

<a id="origin-6247"></a>
## 131. 一个很好理解的类比：温度计

可以把 Reward Model 想象成一个：

```text
只学习相对冷热关系的温度计
```

训练数据只告诉它：

```text
A 比 B 热

C 比 A 热

D 比 C 冷
```

却从来没有告诉它：

```text
A = 30℃
B = 20℃
```

所以它可能学成：

```text
A = 2
B = 0
```

也可能：

```text
A = 102
B = 100
```

只要：

```text
A > B
```

并且分差合适，

Pairwise Loss 就满意。

因此：

\[
\boxed{\text{Reward Model 学的是顺序，而不是绝对刻度}}
\]

---

<a id="origin-6304"></a>
## 132. 最核心的一句话

Reward Model 的输出虽然是：

\[
\boxed{r\in(-\infty,+\infty)}
\]

但是 Pairwise Training 真正优化的是：

\[
\boxed{r_c-r_r}
\]

而不是单独优化：

\[
r_c\rightarrow+\infty
\]

或者：

\[
r_r\rightarrow-\infty
\]

同时，当：

\[
r_c-r_r
\]

已经足够大之后：

\[
\boxed{
\frac{\partial L}{\partial(r_c-r_r)}
\rightarrow0
}
\]

所以继续拉大分差的动力会迅速减弱。

---

<a id="origin-6349"></a>
## 133. 最终总结

Reward Model：

\[
R_\theta(x,y)
\]

输出一个无界标量：

\[
R_\theta(x,y)\in\mathbb R
\]

Pairwise Loss：

\[
\boxed{
L
=
-\log
\sigma(
r_c-r_r
)
}
\]

它只要求：

\[
\boxed{
r_c>r_r
}
\]

并希望二者有足够明显的分差。

但是：

```text
Reward 的绝对零点没有意义
Reward 的绝对尺度也没有统一标准
```

因此：

\[
\boxed{
\text{Reward Model 主要学习的是相对排序，而不是绝对打分}
}
\]

训练时由于 sigmoid 饱和：

\[
r_c-r_r\text{ 越大}
\]

则：

\[
\text{梯度越接近 0}
\]

因此不会一直以很强的梯度向无穷大推动。

而当 Reward 后续交给 PPO 使用时，还需要通过：

```text
Reward Normalization
Reward Scaling
KL Penalty
Advantage Normalization
```

等机制控制整个强化学习过程的数值尺度。


---

<a id="origin-6429"></a>
## 134. Reward Model 和 DPO 又有什么区别？

二者可以使用同样的数据：

```text
chosen
rejected
```

但是做的事情不同。

---

<a id="origin-6442"></a>
### 134.1 Reward Model

显式训练：

\[
R_\theta(x,y)
\]

最终得到：

```text
一个单独的评分模型。
```

---

<a id="origin-6458"></a>
### 134.2 DPO

通常直接训练：

```text
Policy Model
```

比较：

```text
chosen/rejected 的概率差
```

并结合：

```text
Reference Model
```

不必单独训练一个 Reward Model。

这个文件的注释也明确指出：

```text
Reward Model 不计算策略/参考模型概率比。
```



---

<a id="origin-6490"></a>
## 135. Reward Model 和 PPO 是什么关系？

经典 RLHF 可以：

```text
Preference Data
       ↓
Reward Model Training
       ↓
得到 Reward Model
       ↓
Policy 生成回答
       ↓
Reward Model 给回答打分
       ↓
PPO 根据 Reward
更新 Policy
```

所以 Reward Model 的作用可以简单理解为：

> **把“人类偏好”训练成一个可以自动运行的打分器。**

否则 PPO 每生成一次回答，都让真人过来打一次分，成本根本无法接受。

---

<a id="origin-6517"></a>
## 136. 为什么叫“人类偏好的代理模型”？

原本真实目标是：

```text
人觉得哪个好？
```

但真人不能每秒打几万次分。

所以训练一个：

\[
R_\theta(x,y)
\]

去近似：

```text
人类偏好。
```

之后强化学习就可以：

```text
不断调用 Reward Model。
```

---

<a id="origin-6547"></a>
## 137. 但 Reward Model 并不天然代表“真理”

这非常重要。

Reward Model 学到的是：

```text
训练数据中的偏好模式。
```

如果 Preference Dataset：

```text
存在偏差
存在错误
覆盖不足
```

Reward Model 也会继承这些问题。

所以 Reward Model 更准确的定义不是：

```text
真理模型
```

而是：

> **Preference Model。**

---

<a id="origin-6579"></a>
## 138. 这个 `train_reward.py` 特别适合教学的原因

它非常“干净”。

没有：

```text
Distributed Training
DeepSpeed
FSDP
AMP
GradScaler
Gradient Accumulation
Scheduler
复杂 Checkpoint
Validation Pipeline
```

基本只有：

```text
数据
→ 模型
→ Reward
→ Pairwise Loss
→ Backward
→ AdamW
```

因此特别适合先把：

```text
Reward Model 最核心原理
```

讲透。

---

<a id="origin-6618"></a>
## 139. 这个实现没有做什么？

必须明确。

---

<a id="origin-6624"></a>
### 139.1 没有 Token Classification

不是：

```text
每个 Token 一个 Reward。
```

而是：

```text
整条 Response 一个 Reward。
```

---

<a id="origin-6640"></a>
### 139.2 没有 LM Head

不输出：

```text
Vocabulary logits。
```

---

<a id="origin-6650"></a>
### 139.3 没有 Next-token Labels

没有：

```text
labels
```

也没有：

```text
input → shift → target
```

---

<a id="origin-6666"></a>
### 139.4 没有 Reference Model

和 PPO/DPO 的一些环节不同。

---

<a id="origin-6672"></a>
### 139.5 没有绝对 Reward Label

数据没有：

```text
chosen = 8.5 分

rejected = 2.0 分
```

---

<a id="origin-6684"></a>
### 139.6 没有 Validation

打印的：

```text
accuracy
```

只是 Training Batch Accuracy。

---

<a id="origin-6696"></a>
### 139.7 没有冻结 Backbone

整个模型一起更新。

---

<a id="origin-6702"></a>
### 139.8 没有梯度累积

```text
一个 Batch
=
一次 optimizer.step()
```

---

<a id="origin-6712"></a>
### 139.9 没有混合精度

本程序是：

```text
FP32 教学实现。
```

---

<a id="origin-6722"></a>
### 139.10 没有学习率 Scheduler

Learning Rate：

```text
固定。
```

---

<a id="origin-6732"></a>
## 140. 最后用一个完整故事彻底串起来

假设今天我们刚刚有一个已经完成 SFT 的 MiniMind。

它已经能够理解：

```text
“1+1是多少？”
```

也能够生成：

```text
“2”
```

但是我们现在希望它进一步知道：

```text
哪些回答更受人偏好。
```

于是准备数据：

```text
Prompt：
1+1是多少？

Chosen：
2

Rejected：
5
```

---

首先把两段完整对话分别送进同一个 MiniMind：

```text
Prompt + Chosen
         ↓
      MiniMind
         ↓
      Hidden
         ↓
最后 Token Hidden
         ↓
Reward Head
         ↓
r_chosen
```

另一边：

```text
Prompt + Rejected
         ↓
      MiniMind
         ↓
      Hidden
         ↓
最后 Token Hidden
         ↓
Reward Head
         ↓
r_rejected
```

注意：

> 左右不是两个 Reward Model。

而是：

> **同一个 Reward Model 被调用两次。**

参数完全共享。

---

假设一开始模型：

```text
chosen = 0.1

rejected = 0.8
```

明显排反。

于是：

\[
\Delta
=
0.1-0.8
=
-0.7
\]

：

\[
P(c\succ r)
=
\sigma(-0.7)
\approx0.332
\]

Loss：

\[
L
=
-\log0.332
\approx1.103
\]

Loss 比较大。

---

反向传播以后：

```text
chosen 对应方向
得到“应该提高 chosen-rejected 差值”的梯度

rejected 对应方向
得到相反梯度
```

Reward Head 更新。

Transformer Backbone 也更新。

---

训练很多 Preference Pair 之后：

再次遇到类似输入，可能得到：

```text
chosen = 2.4

rejected = -0.3
```

那么：

\[
\Delta=2.7
\]

：

\[
P(c\succ r)
=
\sigma(2.7)
\approx0.937
\]

Loss：

\[
-\log0.937
\approx0.065
\]

模型已经很好地区分。

---

<a id="origin-6907"></a>
## 141. 整个 Reward Model 训练最重要的五个公式

<a id="origin-6909"></a>
### 141.1 公式一：完整输入

\[
s=(x,y)
\]

其中：

```text
x = Prompt / History
y = Response
```

---

<a id="origin-6924"></a>
### 141.2 公式二：Transformer

\[
H
=
f_\theta(s)
\]

：

\[
H\in
\mathbb R^{T\times d}
\]

---

<a id="origin-6941"></a>
### 141.3 公式三：Reward

取最后位置：

\[
h_{\text{last}}
\]

然后：

\[
\boxed{
r
=
w^T h_{\text{last}}
}
\]

---

<a id="origin-6961"></a>
### 141.4 公式四：Preference Probability

\[
\boxed{
P(y_c\succ y_r|x)
=
\sigma(
r_c-r_r
)
}
\]

---

<a id="origin-6975"></a>
### 141.5 公式五：Reward Model Loss

\[
\boxed{
L_{\text{RM}}
=
-
\frac1B
\sum_{i=1}^{B}
\log
\sigma
\left(
R_\theta(x_i,y_i^c)
-
R_\theta(x_i,y_i^r)
\right)
}
\]

这就是整个程序最核心的数学公式。

---

<a id="origin-6998"></a>
## 142. Reward Model 训练总流程

```text
               Preference Dataset
                      │
          ┌───────────┴───────────┐
          │                       │
       Chosen                  Rejected
          │                       │
          ▼                       ▼
    Chat Template            Chat Template
          │                       │
          ▼                       ▼
      Tokenizer                Tokenizer
          │                       │
          └───────────┬───────────┘
                      ▼
              [c0,c1,...,r0,r1,...]
                      │
                      ▼
                Padding + Mask
                      │
                      ▼
               MiniMind Backbone
                      │
                      ▼
               Hidden [2B,T,H]
                      │
                      ▼
          Last Real Token Hidden
                      │
                      ▼
                Reward Head
                  H → 1
                      │
                      ▼
               Scores [2B]
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
       r_chosen                r_rejected
          │                       │
          └───────────┬───────────┘
                      ▼
             Δ = r_c - r_r
                      │
                      ▼
                 sigmoid(Δ)
                      │
                      ▼
            -log sigmoid(Δ)
                      │
                      ▼
                   Loss
                      │
                      ▼
                  backward
                      │
             ┌────────┴────────┐
             ▼                 ▼
        Reward Head         Backbone
             │                 │
             └────────┬────────┘
                      ▼
                   AdamW
                      │
                      ▼
             新 Reward Model
```

---

<a id="origin-7070"></a>
## 143. 最后一句话总结

这份代码做的事情其实可以压缩为：

> **先用已经会理解语言的 SFT MiniMind，把“Prompt + Response”压缩成最后一个 Token 的语义向量，再训练一个标量评分头，同时微调整个 Backbone；通过 `-log sigmoid(r_chosen-r_rejected)`，让人类偏好的回答分数逐渐高于不偏好的回答。**

所以 Reward Model 最本质的训练目标不是：

```text
学会“答案应该是多少分”
```

而是：

\[
\boxed{
\text{学会让好答案的分数相对更高}
}
\]

而这正是后续 RLHF / PPO 能够使用它作为自动奖励函数的基础。
