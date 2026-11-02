# generate 推理详解


先看核心代码的整体目标：

```python
@torch.inference_mode()
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

这段代码本质上在重复做一件事情：

```text
已有文本
   ↓
模型预测“下一个 token”的 logits
   ↓
对 logits 做温度调整
   ↓
重复惩罚
   ↓
Top-K
   ↓
Top-P
   ↓
采样 / argmax
   ↓
得到新 token
   ↓
拼回输入
   ↓
继续预测下一个 token
```

例如：

```text
输入：

I love

第 1 轮：
I love
   ↓
预测 AI

第 2 轮：
I love AI
   ↓
预测 very

第 3 轮：
I love AI very
   ↓
预测 much

最终：

I love AI very much
```

这就是所谓：

```text
Autoregressive Generation
自回归生成
```

---

<a id="origin-85"></a>
## 1. `@torch.inference_mode()`：进入纯推理模式

代码：

```python
@torch.inference_mode()
```

意思是：

> 下面这个函数只是做推理，不需要计算梯度。

训练时：

```text
forward
↓
loss
↓
backward
↓
梯度
↓
更新参数
```

因此 PyTorch 必须保存很多中间结果：

```text
activation
计算图
梯度信息
```

但是生成文本的时候：

```text
I love
↓
AI
```

我们并不需要：

```python
loss.backward()
```

所以可以关闭梯度。

相当于：

```python
with torch.no_grad():
    ...
```

但 `inference_mode()` 更进一步针对纯推理做了优化。

主要好处：

```text
减少显存
减少额外计算
提高推理速度
```

---

<a id="origin-154"></a>
## 2. `input_ids`：真正送给模型的不是文字，而是 token 编号

例如：

```text
"I love AI"
```

经过 tokenizer：

```python
input_ids = [1, 245, 893, 1024]
```

可能表示：

```text
1     → BOS
245   → I
893   → love
1024  → AI
```

因此：

```python
input_ids
```

实际上是：

```text
token ID 序列
```

而不是字符串。

---

<a id="origin-193"></a>
## 3. `num_return_sequences`：一次生成几个答案

代码：

```python
input_ids = kwargs.pop("input_ids", inputs).repeat(
    num_return_sequences,
    1
)
```

假设原始输入：

```python
input_ids.shape = [1, 3]
```

内容：

```text
[BOS, I, love]
```

如果：

```python
num_return_sequences = 3
```

就会复制成：

```text
[BOS, I, love]
[BOS, I, love]
[BOS, I, love]
```

shape：

```text
[3, 3]
```

然后三条序列分别采样。

例如最终可能得到：

```text
I love AI.
I love programming.
I love this game.
```

---

<a id="origin-248"></a>
## 4. `attention_mask`：告诉模型哪些 token 是真的，哪些是 padding

例如一个 batch：

```text
句子 1：
I love AI

句子 2：
I love
```

为了组成矩阵，可能 padding：

```text
I love AI
I love PAD
```

对应：

```python
input_ids =
[
    [10, 20, 30],
    [10, 20,  0]
]
```

attention mask：

```python
attention_mask =
[
    [1, 1, 1],
    [1, 1, 0]
]
```

表示：

```text
1 → 有效 token
0 → padding，不应该参与 Attention
```

当新生成一个 token 时：

```python
attention_mask = torch.cat([
    attention_mask,
    attention_mask.new_ones(
        attention_mask.shape[0], 1
    )
], -1)
```

因为新生成的 token 当然是真实 token：

```text
原来：

1 1 1

生成一个 token 后：

1 1 1 1
```

---

<a id="origin-319"></a>
## 5. `max_new_tokens`：最多新生成多少个 token

例如：

```python
max_new_tokens = 100
```

表示：

> 原输入之后，最多再生成 100 个 token。

注意它不是：

```text
最终总长度 = 100
```

而是：

```text
新增长度最多 = 100
```

例如输入已经有：

```text
500 token
```

那么最多得到：

```text
500 + 100 = 600 token
```

---

<a id="origin-357"></a>
## 6. `past_key_values`：KV Cache

这是生成阶段最重要的优化之一。

假设第一轮：

```text
I love
```

模型计算：

```text
K_I
V_I

K_love
V_love
```

准备预测：

```text
AI
```

下一轮输入逻辑上变成：

```text
I love AI
```

如果完全重算：

```text
K_I
V_I

K_love
V_love

K_AI
V_AI
```

其中：

```text
I
love
```

的 K/V 明明上一轮已经算过了。

所以缓存：

```text
K_I
V_I
K_love
V_love
```

下一轮只计算：

```text
K_AI
V_AI
```

这就是：

```text
KV Cache
```

代码：

```python
past_key_values = outputs.past_key_values
```

---

<a id="origin-441"></a>
## 7. 为什么 `past_len` 可以决定只输入后面的 token

代码：

```python
past_len = past_key_values[0][0].shape[1] if past_key_values else 0
```

假设缓存中已经有：

```text
I love AI
```

也就是：

```python
past_len = 3
```

此时：

```python
input_ids =
[I, love, AI, very]
```

那么：

```python
input_ids[:, past_len:]
```

就是：

```text
[very]
```

因此只把：

```text
very
```

送进去。

过去：

```text
I love AI
```

的信息由 KV Cache 提供。

---

<a id="origin-498"></a>
## 8. `outputs.logits[:, -1, :]` 为什么只取最后一个位置

模型输出：

```python
outputs.logits
```

shape 通常是：

```text
[B, L, V]
```

其中：

```text
B = batch size
L = sequence length
V = vocabulary size
```

例如：

```text
[B, 4, 32000]
```

说明四个位置都会产生一个词表预测。

例如输入：

```text
BOS I love AI
```

模型理论上同时输出：

```text
BOS → I
I → love
love → AI
AI → ?
```

但是生成阶段真正关心的只是：

```text
AI → 下一个 token 是什么
```

所以取：

```python
outputs.logits[:, -1, :]
```

得到：

```text
[B, V]
```

也就是：

> 最后一个位置对整个词表的预测分数。

---

<a id="origin-567"></a>
## 9. logits 是什么

假设词表只有 5 个 token：

```text
AI
dog
cat
great
EOS
```

模型输出：

```python
logits = [
    4.0,
    1.0,
    0.5,
    3.0,
    -1.0
]
```

注意：

```text
logits 还不是概率
```

它只是模型给每个 token 的原始分数。

经过：

```python
softmax(logits)
```

才会得到概率。

---

<a id="origin-609"></a>
## 10. `temperature`：控制概率分布有多尖锐

代码：

```python
logits = outputs.logits[:, -1, :] / temperature
```

公式：

```math
P_i =
\frac{
e^{z_i/T}
}{
\sum_j e^{z_j/T}
}
```

其中：

```text
z_i = logits
T   = temperature
```

---

<a id="origin-637"></a>
### 10.1 Temperature = 1

假设：

```text
logits:

A = 4
B = 3
C = 2
```

直接 Softmax。

概率可能大约：

```text
A = 66.5%
B = 24.5%
C = 9.0%
```

---

<a id="origin-661"></a>
## 11. Temperature < 1：让模型更保守

假设：

```python
temperature = 0.5
```

那么：

```text
4 / 0.5 = 8
3 / 0.5 = 6
2 / 0.5 = 4
```

Softmax：

```text
A ≈ 86.7%
B ≈ 11.7%
C ≈ 1.6%
```

可以发现：

```text
原本：

66.5%
24.5%
9.0%

↓

降低 temperature：

86.7%
11.7%
1.6%
```

最高概率 token 变得更占优势。

因此：

```text
temperature 越低
↓
分布越尖
↓
模型越确定
↓
随机性越低
```

---

<a id="origin-719"></a>
## 12. Temperature > 1：让模型更随机

例如：

```python
temperature = 2
```

变成：

```text
4 / 2 = 2
3 / 2 = 1.5
2 / 2 = 1
```

概率会变平。

例如大约：

```text
A = 50.6%
B = 30.7%
C = 18.6%
```

于是原本低概率 token 更容易被抽中。

所以：

```text
temperature 越高
↓
概率越平均
↓
随机性越强
↓
生成越发散
```

---

<a id="origin-761"></a>
## 13. Temperature 最简单的理解

可以把它理解成：

```text
Temperature

低：
“相信第一名”

高：
“第一名虽然最好，但后面的也给点机会”
```

例如模型预测：

```text
我今天去：

学校  60%
公司  25%
公园  10%
月球   5%
```

低温度：

```text
学校 ≫ 公司 ≫ 公园 ≫ 月球
```

高温度：

```text
学校
公司
公园
月球
```

之间差距缩小。

---

<a id="origin-805"></a>
## 14. `repetition_penalty`：重复惩罚

模型生成的时候经常出现：

```text
我喜欢人工智能，
人工智能非常有趣，
人工智能可以帮助我们，
人工智能……
```

甚至极端情况：

```text
很好很好很好很好很好很好……
```

因此可以惩罚已经出现过的 token。

代码：

```python
seen = torch.unique(input_ids[i])
```

得到：

```text
这条序列已经出现过哪些 token
```

然后：

```python
score = logits[i, seen]
```

找到这些 token 的 logits。

<a id="origin-844"></a>
### 14.1 用 5 列数值看清重复惩罚的全过程

先看 `torch.unique`。假设第 `i` 条序列已有的 token 编号为：

```python
input_ids[i] = tensor([3, 1, 3, 4, 1])
seen = torch.unique(input_ids[i])  # tensor([1, 3, 4])
```

`unique` 去掉重复编号，默认按编号排序。因此，已经出现过的 token 是 `1、3、4`。编号 `1` 和 `3` 虽然各出现两次，在本轮也只调整一次；这段代码不会按出现次数加重惩罚。

**这里的 `1、3、4` 是已经出现过的 token 的 ID（词表编号），在 `logits[i, seen]` 中也用作列索引，用来找到这些 token 对应的分数**。模型每次预测下一个 token 时，都会为整个词表中的候选 token 打分；**重复惩罚会调整 ID 为 `1、3、4` 的候选分数**。当惩罚系数大于 `1` 时，非零分数会降低，使这些重复候选相对未出现候选更难被选中；分数为零的候选保持不变。

接着看 `score` 和 `logits`。`logits` 的形状是 `[批次大小, 词表大小]`，`logits[i]` 表示第 `i` 条序列预测下一个 token 时，整个词表的分数。假设词表只有 5 个 token：

```text
token 编号：        0     1     2      3     4
调整前 logits[i]：[0.5,  2.0,  1.0,  -2.0,  0.0]
```

每一列对应一个 token 编号，列中的值是分数，不是概率。`seen` 用作列索引，取出已经出现过的 token 的分数：

```python
score = logits[i, seen]
      # logits[i, [1, 3, 4]]
      # tensor([2.0, -2.0, 0.0])
```

`score` 中三个值依次属于 token `1、3、4`。设 `repetition_penalty = 2.0`，执行：

```python
logits[i, seen] = torch.where(
    score > 0,
    score / repetition_penalty,
    score * repetition_penalty
)
```

逐列看原值 `->` 新值，就能看清哪些分数被调整：

```text
第 0 列（token 0，未出现）： 0.5 ->  0.5
    不参与重复惩罚，保持原值。

第 1 列（token 1，已出现）： 2.0 ->  1.0
    正数除以 2：2.0 / 2.0 = 1.0，分数变小。

第 2 列（token 2，未出现）： 1.0 ->  1.0
    不参与重复惩罚，保持原值。

第 3 列（token 3，已出现）：-2.0 -> -4.0
    负数乘以 2：-2.0 * 2.0 = -4.0，分数变小（变得更负）。

第 4 列（token 4，已出现）： 0.0 ->  0.0
    0 不满足 score > 0，走乘法分支；零乘以 2 仍然是零。
```

`torch.where` 得到 `[1.0, -4.0, 0.0]`，将它们分别写回 `logits` 的第 `1、3、4` 列，得到完整的前后对照：

```text
token 编号：        0     1     2      3     4
调整前 logits[i]：[0.5,  2.0,  1.0,  -2.0,  0.0]
调整后 logits[i]：[0.5,  1.0,  1.0,  -4.0,  0.0]
```

重复候选 token `1` 的分数从 `2.0` 降到 `1.0`，token `3` 从 `-2.0` 降到 `-4.0`。注意 **`-4.0 < -2.0`，虽然绝对值变大，但分数本身变小，所以也是惩罚**。未出现的 token `0、2` 保持原分数；重复候选 token `4` 因为分数为零，也保持不变。

为什么分数降低能惩罚重复？softmax 中，两个候选的概率比满足：

```text
p_j / p_k = exp(logit_j - logit_k)
```

降低重复候选的分数，同时保持未出现候选的分数不变，就会降低重复候选相对未出现候选的概率比。若把负数也用除法，`-2.0 / 2.0 = -1.0`，分数反而变大，相对未出现候选更有优势，因此负数要用乘法。

这里的惩罚效果以 `repetition_penalty > 1` 为前提；等于 `1` 不调整，介于 `0` 和 `1` 之间反而鼓励重复。零分数没有受到直接惩罚，而且 softmax 的归一化也受其他候选影响，因此不能保证每个重复 token 的绝对概率都下降。

---

<a id="origin-923"></a>
## 15. 为什么正数要除，负数要乘

代码：

```python
torch.where(
    score > 0,
    score / repetition_penalty,
    score * repetition_penalty
)
```

假设：

```python
repetition_penalty = 1.2
```

一个已经出现过的 token：

```text
logit = 6
```

变成：

```text
6 / 1.2 = 5
```

分数下降。

如果：

```text
logit = -2
```

不能做：

```text
-2 / 1.2 = -1.67
```

因为：

```text
-1.67 > -2
```

反而提高了概率。

因此负数应该：

```text
-2 × 1.2 = -2.4
```

这样也是降低分数。

所以：

```text
正 logits：
除以 penalty

负 logits：
乘以 penalty
```

共同目标都是：

```text
让出现过的 token 更难再次出现。
```

---

<a id="origin-1001"></a>
## 16. `top_k`：只保留概率最大的 K 个 token

假设词表：

```text
100000 个 token
```

如果直接采样：

```text
理论上 100000 个 token 都有机会被抽中
```

其中可能存在很多极低概率的怪词。

因此：

```python
top_k = 50
```

意思是：

> 只允许分数最高的 50 个 token 参与采样。

剩下：

```text
99950 个 token
```

全部：

```python
logit = -∞
```

---

<a id="origin-1041"></a>
## 17. Top-K 数值例子

假设只有 6 个候选：

```text
A  0.40
B  0.25
C  0.15
D  0.10
E  0.06
F  0.04
```

如果：

```python
top_k = 3
```

保留：

```text
A
B
C
```

删除：

```text
D
E
F
```

相当于：

```text
A  0.40
B  0.25
C  0.15
D  -∞
E  -∞
F  -∞
```

之后重新 Softmax。

于是：

```text
D、E、F
```

被抽到的概率就是：

```text
0
```

---

<a id="origin-1103"></a>
## 18. Top-K 的问题

假设某一次预测非常确定：

```text
A 90%
B  5%
C  3%
D  1%
E  1%
```

Top-K=50 其实太宽了。

但另一种情况下：

```text
A 5%
B 5%
C 4.8%
D 4.7%
...
```

模型很不确定。

这时候固定 Top-K=5 又可能太窄。

所以出现了：

```text
Top-P
```

---

<a id="origin-1139"></a>
## 19. `top_p`：根据累计概率动态决定保留多少 token

Top-P 也叫：

```text
Nucleus Sampling
核采样
```

例如：

```python
top_p = 0.85
```

意思不是：

```text
只保留概率 > 0.85 的 token
```

而是：

> 从概率最高的 token 开始累加，保留累计概率大约达到 85% 的这一组 token。

---

<a id="origin-1166"></a>
## 20. Top-P 数值例子

假设：

```text
A  40%
B  25%
C  15%
D  10%
E   6%
F   4%
```

累计概率：

```text
A       40%
A+B     65%
A+B+C   80%
A+B+C+D 90%
```

如果：

```python
top_p = 0.85
```

那么通常保留：

```text
A
B
C
D
```

因为：

```text
前三个 = 80%
```

还没达到：

```text
85%
```

加上 D 后：

```text
90%
```

于是 D 也保留。

剩余：

```text
E
F
```

删除。

---

<a id="origin-1234"></a>
## 21. 为什么代码要把 mask 右移一位

代码：

```python
mask = torch.cumsum(
    torch.softmax(sorted_logits, dim=-1),
    dim=-1
) > top_p
```

假设累计概率：

```text
A   0.40
B   0.65
C   0.80
D   0.90
E   0.96
```

`top_p=0.85`：

```text
mask:

A False
B False
C False
D True
E True
```

如果直接删：

```text
D
E
```

那么剩下：

```text
A+B+C = 0.80
```

反而没有达到 0.85。

所以代码：

```python
mask[..., 1:] = mask[..., :-1].clone()
mask[..., 0] = 0
```

把删除标志右移。

变成：

```text
A False
B False
C False
D False
E True
```

因此：

```text
D
```

作为第一个跨越阈值的 token 被保留下来。

最终候选集合：

```text
A+B+C+D = 90%
```

---

<a id="origin-1317"></a>
## 22. Top-K 和 Top-P 的区别

可以简单理解：

```text
Top-K：

“只允许前 K 名参加比赛。”
```

例如：

```text
固定前 50 名
```

而：

```text
Top-P：

“只保留累计概率达到 P 的那一小撮候选。”
```

例如：

```text
累计概率达到 85% 即停止。
```

所以：

```text
Top-K = 固定人数

Top-P = 动态人数
```

---

<a id="origin-1357"></a>
## 23. Top-K 和 Top-P 可以同时使用

对应代码如下：

```text
logits
↓
Top-K
↓
Top-P
↓
Softmax
↓
Sampling
```

例如原来：

```text
100000 个 token
```

先：

```python
top_k = 50
```

只剩：

```text
50 个
```

然后：

```python
top_p = 0.85
```

可能最后只留下：

```text
12 个
```

这 12 个再参与采样。

---

<a id="origin-1407"></a>
## 24. `do_sample=True`：采样还是贪心

代码：

```python
next_token = (
    torch.multinomial(
        torch.softmax(logits, dim=-1),
        num_samples=1
    )
    if do_sample
    else
    torch.argmax(logits, dim=-1, keepdim=True)
)
```

这是生成策略最核心的分支之一。

---

<a id="origin-1427"></a>
## 25. `do_sample=False`：Argmax 贪心生成

例如：

```text
AI       55%
robot    20%
model    15%
dog      10%
```

使用：

```python
torch.argmax(...)
```

永远选择：

```text
AI
```

所以：

```text
Greedy Decoding
```

就是：

> 每一步都选择当前概率最高的 token。

---

<a id="origin-1462"></a>
## 26. `do_sample=True`：随机采样

使用：

```python
torch.multinomial(...)
```

如果：

```text
AI       55%
robot    20%
model    15%
dog      10%
```

那么：

```text
55% → AI
20% → robot
15% → model
10% → dog
```

因此同一个 Prompt：

```text
讲一个关于机器人的故事
```

运行两次可能产生不同结果。

---

<a id="origin-1498"></a>
## 27. `torch.multinomial()` 本质就是“按概率抽签”

例如：

```python
probs = [0.1, 0.2, 0.6, 0.1]
```

调用：

```python
torch.multinomial(probs, 1)
```

不是：

```text
随机等概率选择四个
```

而是：

```text
第 1 个：10%
第 2 个：20%
第 3 个：60%
第 4 个：10%
```

所以第三个最容易被选中。

---

<a id="origin-1531"></a>
## 28. Temperature / Top-K / Top-P 的关系

这三个东西经常一起出现，但职责不同。

完整顺序：

```text
模型 logits
   ↓
Temperature
改变概率分布形状
   ↓
Top-K
按数量砍候选
   ↓
Top-P
按累计概率继续砍候选
   ↓
Softmax
   ↓
Multinomial
随机抽取
```

可以理解成：

```text
Temperature：
“候选之间差距多大？”

Top-K：
“最多让多少个候选参加？”

Top-P：
“到底保留多少概率质量？”

Multinomial：
“最终从留下的人里面抽谁？”
```

---

<a id="origin-1573"></a>
## 29. 一个完整的采样例子

假设模型输出：

```text
token      logits

A           5
B           4
C           3
D           2
E           1
F           0
```

先：

```python
temperature = 0.8
```

变成：

```text
A 6.25
B 5.00
C 3.75
D 2.50
E 1.25
F 0
```

差距被拉大。

然后：

```python
top_k = 4
```

只留下：

```text
A
B
C
D
```

于是：

```text
E = -∞
F = -∞
```

再：

```python
top_p = 0.85
```

假设 Softmax 后：

```text
A 65%
B 19%
C  9%
D  7%
```

累计：

```text
A     65%
A+B   84%
A+B+C 93%
```

于是：

```text
A
B
C
```

保留。

D 删除。

最终重新 Softmax 后可能：

```text
A 70%
B 20%
C 10%
```

然后：

```python
torch.multinomial(...)
```

随机抽：

```text
70% A
20% B
10% C
```

---

<a id="origin-1688"></a>
## 30. `EOS`：模型什么时候停止生成

例如：

```python
eos_token_id = 2
```

表示：

```text
token ID = 2
```

代表：

```text
<EOS>
End Of Sequence
```

也就是：

> 句子结束。

例如：

```text
I love AI .
<EOS>
```

生成 EOS 后，这条序列就应该停止。

---

<a id="origin-1724"></a>
## 31. `finished` 的作用

代码：

```python
finished = torch.zeros(
    input_ids.shape[0],
    dtype=torch.bool,
    device=input_ids.device
)
```

例如 batch 有 3 条：

```text
False
False
False
```

表示：

```text
都还没生成完
```

假设第一条生成 EOS：

```text
True
False
False
```

下一轮第二、第三条继续生成。

---

<a id="origin-1762"></a>
## 32. 为什么已经结束的序列还要填 EOS

代码：

```python
next_token = torch.where(
    finished.unsqueeze(-1),
    next_token.new_full(
        (next_token.shape[0], 1),
        eos_token_id
    ),
    next_token
)
```

原因是：

> 一个 batch 中所有序列必须保持相同长度。

例如：

```text
样本 1：
I love AI EOS

样本 2：
I love machine learning is ...

样本 3：
I love programming because ...
```

样本 1 已经结束。

但 batch 还要继续跑。

因此后续让它不断补：

```text
EOS EOS EOS
```

最终类似：

```text
样本1：
I love AI EOS EOS EOS

样本2：
I love machine learning EOS

样本3：
I love programming very much EOS
```

这样矩阵长度才能统一。

---

<a id="origin-1821"></a>
## 33. `finished |= ...` 是什么

代码：

```python
finished |= next_token.squeeze(-1).eq(eos_token_id)
```

假设之前：

```text
finished =
[True, False, False]
```

这一轮：

```text
next_token == EOS =
[False, True, False]
```

做 OR：

```text
True  OR False = True
False OR True  = True
False OR False = False
```

得到：

```text
[True, True, False]
```

所以：

> 一旦某条序列结束，就永远保持结束状态。

---

<a id="origin-1863"></a>
## 34. `finished.all()`：所有序列都结束就提前退出

代码：

```python
if finished.all():
    break
```

虽然：

```python
max_new_tokens = 8192
```

但不代表一定生成 8192 个。

例如第 150 个 token 时：

```text
所有 batch 都生成 EOS
```

就直接结束。

所以：

```text
max_new_tokens
```

只是：

```text
最大上限
```

而不是必须生成的数量。

---

<a id="origin-1904"></a>
## 35. `streamer`：边生成边显示

没有 streamer 时：

```text
模型生成全部 token
↓
最后一次性返回
```

用户可能看到：

```text
等待……
等待……
等待……

然后突然出现完整答案
```

而 streamer：

```text
生成一个 token
↓
立刻交给显示系统
↓
再生成下一个
```

于是你看到：

```text
今
今天
今天我
今天我们
今天我们来
今天我们来介绍
……
```

这就是 ChatGPT 类应用常见的：

```text
流式输出
Streaming
```

---

<a id="origin-1955"></a>
## 36. `streamer.put(next_token.cpu())`

代码：

```python
streamer.put(next_token.cpu())
```

说明：

```text
GPU 负责模型计算
↓
得到 token
↓
token 放到 CPU
↓
streamer 解码并显示
```

streamer 并不负责模型推理。

它主要负责：

```text
token
↓
tokenizer decode
↓
文字显示
```

---

<a id="origin-1989"></a>
## 37. `streamer.end()`

最后：

```python
streamer.end()
```

告诉 streamer：

```text
生成结束了
```

让它做最后的缓冲区清理和输出。

---

<a id="origin-2007"></a>
## 38. `use_cache=True`

如果：

```python
use_cache=True
```

则：

```python
past_key_values = outputs.past_key_values
```

下一轮可以使用 KV Cache。

流程：

```text
第一轮：

输入整个 Prompt
↓
计算全部 K/V
↓
缓存


第二轮：

只输入新 token
+
过去 KV Cache
↓
生成下一 token


第三轮：

还是只输入新 token
+
更大的 KV Cache
```

这就是现代 Decoder-only LLM 高效生成的核心。

---

<a id="origin-2055"></a>
## 39. `use_cache=False`

如果：

```python
use_cache=False
```

代码：

```python
past_key_values = None
```

因此每一轮：

```python
past_len = 0
```

于是：

```python
input_ids[:, past_len:]
```

就是：

```python
input_ids[:, 0:]
```

即完整输入。

例如：

```text
第 1 轮：

I love

第 2 轮：

I love AI

第 3 轮：

I love AI very

第 4 轮：

I love AI very much
```

每次都从头算。

非常浪费计算。

---

<a id="origin-2115"></a>
## 40. 为什么最后一个新 token 通常还没有进入 KV Cache

代码最后：

```python
return {
    'generated_ids': input_ids,
    'past_kv': past_key_values
}
```

这里有一个非常重要的细节。

假设：

```text
当前 forward 输入：

I love
```

forward 得到：

```text
KV Cache：

I
love
```

然后从 logits 采样得到：

```text
AI
```

接着：

```python
input_ids = [I, love, AI]
```

但是注意：

```text
AI 只是刚刚被“选出来”
```

它还没有再次经过：

```python
self.forward(...)
```

所以 KV Cache 里实际上还是：

```text
I
love
```

还没有：

```text
AI
```

下一轮 forward 时：

```text
AI
```

才会生成自己的：

```text
K_AI
V_AI
```

---

<a id="origin-2197"></a>
## 41. 整个 generate 的一轮到底发生什么

假设当前：

```text
input_ids:

BOS I love
```

并且过去已经缓存：

```text
BOS
I
```

那么本轮：

<a id="origin-2216"></a>
### 41.1 第一步

计算缓存长度：

```text
past_len = 2
```

---

<a id="origin-2226"></a>
### 41.2 第二步

只输入未缓存部分：

```text
love
```

---

<a id="origin-2236"></a>
### 41.3 第三步

结合：

```text
过去 KV：

BOS
I

+

当前：

love
```

做 Attention。

---

<a id="origin-2257"></a>
### 41.4 第四步

模型输出：

```text
love 位置的 logits
```

例如：

```text
AI       5.2
you      3.0
dogs     2.1
pizza    1.5
...
```

---

<a id="origin-2277"></a>
### 41.5 第五步

Temperature：

```text
logits / 0.85
```

---

<a id="origin-2287"></a>
### 41.6 第六步

Repetition Penalty：

```text
BOS
I
love
```

如果这些 token 再次成为候选，就降低它们的分数。

---

<a id="origin-2301"></a>
### 41.7 第七步

Top-K：

```text
只留下前 50 个
```

---

<a id="origin-2311"></a>
### 41.8 第八步

Top-P：

```text
只留下累计概率约 85% 的候选
```

---

<a id="origin-2321"></a>
### 41.9 第九步

Softmax：

```text
把剩余 logits 转成概率
```

---

<a id="origin-2331"></a>
### 41.10 第十步

Multinomial：

```text
按照概率抽一个
```

假设：

```text
抽到 AI
```

---

<a id="origin-2347"></a>
### 41.11 第十一步

拼接：

```text
BOS I love
+
AI
```

变成：

```text
BOS I love AI
```

---

<a id="origin-2365"></a>
### 41.12 第十二步

保存本轮：

```text
past_key_values
```

现在缓存：

```text
BOS
I
love
```

注意：

```text
AI
```

还没缓存。

---

<a id="origin-2391"></a>
### 41.13 第十三步

进入下一轮。

下一轮：

```text
只输入 AI
```

继续预测：

```text
very
```

---

<a id="origin-2409"></a>
## 42. 整个生成过程可以压缩成这一张图

```text
Prompt
│
│  "I love"
▼
Tokenizer
│
▼
input_ids
│
▼
┌─────────────────────────┐
│      Transformer        │
│                         │
│   KV Cache ─────────┐   │
└──────────┬──────────┘   │
           │              │
           ▼              │
        logits            │
           │              │
           ▼              │
      Temperature         │
           │              │
           ▼              │
   Repetition Penalty     │
           │              │
           ▼              │
         Top-K            │
           │              │
           ▼              │
         Top-P            │
           │              │
           ▼              │
        Softmax            │
           │              │
           ▼              │
  Multinomial / Argmax    │
           │              │
           ▼              │
       next_token         │
           │              │
           └──────────────┘
             拼回输入

重复执行
```

---

<a id="origin-2460"></a>
## 43. 最重要的参数总结

| 参数 | 本质作用 |
|---|---|
| `max_new_tokens` | 最多生成多少个新 token |
| `temperature` | 控制概率分布尖锐程度 |
| `top_k` | 只允许概率最高的 K 个 token |
| `top_p` | 只保留累计概率达到 P 的候选集合 |
| `do_sample` | 是否随机采样 |
| `repetition_penalty` | 降低已经出现过的 token 的概率 |
| `eos_token_id` | 生成哪个 token 时认为结束 |
| `use_cache` | 是否开启 KV Cache |
| `num_return_sequences` | 同一个 Prompt 生成多少个答案 |
| `streamer` | 是否边生成边输出 |
| `attention_mask` | 标记哪些输入 token 有效 |

---

<a id="origin-2478"></a>
## 44. Temperature / Top-K / Top-P / Sampling 最容易混淆，可以这样记

```text
模型：

“我认为下面几个词都有可能。”

      ↓

Temperature：

“我要不要把第一名的优势放大？”

      ↓

Top-K：

“只让前 K 名留下。”

      ↓

Top-P：

“留下的这些里面，只需要覆盖主要概率即可。”

      ↓

Multinomial：

“好了，现在真正抽一个。”
```

---

<a id="origin-2512"></a>
## 45. 一个自然语言例子

输入：

```text
浙江大学软件学院位于
```

模型原始预测：

```text
宁波      60%
杭州      18%
浙江      8%
中国      5%
北京      2%
上海      2%
其他      5%
```

如果：

```python
temperature = 0.3
```

会更加相信：

```text
宁波
```

可能变成：

```text
宁波 95%
其他候选很低
```

---

如果：

```python
temperature = 1.5
```

概率会更加平均：

```text
宁波 35%
杭州 22%
浙江 14%
中国 10%
……
```

随机性增加。

---

如果：

```python
top_k = 3
```

只留下：

```text
宁波
杭州
浙江
```

其他全部删除。

---

如果：

```python
top_p = 0.85
```

假设：

```text
宁波 60%
杭州 18%
浙江 8%
```

累计：

```text
宁波       60%
宁波+杭州  78%
+浙江      86%
```

于是只留下：

```text
宁波
杭州
浙江
```

---

最后：

```python
torch.multinomial(...)
```

按照剩余概率随机抽一个。

所以可能得到：

```text
浙江大学软件学院位于宁波
```

也可能低概率得到：

```text
浙江大学软件学院位于杭州
```

---

<a id="origin-2645"></a>
## 46. `do_sample=False` 时，一个很重要的结论

如果：

```python
do_sample=False
```

那么最后：

```python
torch.argmax(...)
```

直接选第一名。

这时候：

```text
temperature
Top-K
Top-P
```

在很多情况下其实意义会大幅降低。

因为只要第一名没有被过滤掉：

```text
argmax
```

最终仍然选择第一名。

所以通常：

```text
do_sample=True
```

时：

```text
temperature
top_k
top_p
```

才真正体现出采样策略的价值。

---

<a id="origin-2697"></a>
## 47. 这段 generate 代码最核心的故事

整段代码可以浓缩成：

```text
第一步：
用 Transformer 计算下一个 token 的 logits

第二步：
用 Temperature 调整“模型有多自信”

第三步：
用 repetition penalty 避免疯狂重复

第四步：
用 Top-K 去掉排名很低的候选

第五步：
用 Top-P 去掉概率质量很小的尾部候选

第六步：
用 Multinomial 随机抽一个 token
或者 Argmax 直接选第一名

第七步：
把这个 token 拼回输入

第八步：
保存 KV Cache

第九步：
继续预测下一个 token
```

因此：

```python
generate()
```

本质不是一个新的神经网络。

它只是：

> **不断调用 `forward()`，然后决定如何从 logits 中选出下一个 token，再把这个 token 送回模型继续生成。**

真正负责：

```text
Q/K/V
Attention
RoPE
RMSNorm
FFN / MoE
```

这些神经网络计算的是：

```python
forward()
```

而 `generate()` 主要负责的是：

```text
循环生成
+
KV Cache 管理
+
采样策略
+
停止条件
+
流式输出
```

这也是理解：

```text
训练
forward
generate
```

三者区别的一个非常重要的分界点。

---

<a id="origin-2785"></a>
## 48. MiniMind 中 KV Cache 的完整原理与代码流程

<a id="origin-2787"></a>
## 49. 先给出最重要的结论

在这份 MiniMind 代码中，KV Cache 的核心不是改变 Attention 的公式，而是：

> **历史 token 不再重复送进 Transformer 计算，而是直接复用它们之前已经计算好的 K 和 V。**

Attention 公式始终还是：

```math
\operatorname{Attention}(Q,K,V)
=
\operatorname{softmax}
\left(
\frac{QK^T}{\sqrt{d}}
\right)V
```

真正发生变化的是参与计算的矩阵尺寸。

不使用 KV Cache 时，假设当前上下文长度为 \(T\)：

```text
Q: T × d
K: T × d
V: T × d
```

需要计算：

```math
QK^T
```

其大小为：

```text
T × T
```

而使用 KV Cache 后，在自回归 Decode 阶段，每次只输入一个新 token：

```text
Q_new: 1 × d
K_all: T × d
V_all: T × d
```

因此只需要计算：

```math
Q_{\text{new}}K_{\text{all}}^T
```

大小变成：

```text
1 × T
```

也就是说：

> **以前需要重新计算完整 Attention Score 矩阵，现在只需要计算新增的最后一行。**

---

<a id="origin-2852"></a>
## 50. MiniMind 中 KV Cache 涉及的完整调用链

代码中的调用关系是：

```text
generate()
    ↓
MiniMindForCausalLM.forward()
    ↓
MiniMindModel.forward()
    ↓
MiniMindBlock.forward()
    ↓
Attention.forward()
```

KV Cache 会沿着这条路径不断向下传递，然后再返回：

```text
generate
    │
    │ past_key_values
    ↓
MiniMindForCausalLM
    ↓
MiniMindModel
    ↓
每一个 Transformer Block
    ↓
Attention
    ↓
计算新的 K、V
    ↓
present_key_value
    ↓
presents
    ↓
outputs.past_key_values
    ↓
重新回到 generate
```

因此 KV Cache 本质上是一个循环：

```text
旧 KV Cache
    ↓
当前新 token
    ↓
Attention
    ↓
追加新的 K、V
    ↓
得到新的 KV Cache
    ↓
下一轮继续使用
```

---

<a id="origin-2912"></a>
## 51. 最关键的代码其实在 generate() 中

MiniMind 的生成代码中有：

```python
past_len = past_key_values[0][0].shape[1] if past_key_values else 0

outputs = self.forward(
    input_ids[:, past_len:],
    attention_mask,
    past_key_values,
    use_cache=use_cache,
    **kwargs
)
```

这里最重要的是：

```python
input_ids[:, past_len:]
```

它的含义是：

> **把已经通过 Transformer 计算过的历史 token 从本轮输入中切掉，只留下还没有计算过的新 token。**

这才是 KV Cache 能够避免重复计算的真正入口。

---

<a id="origin-2942"></a>
## 52. 用一个完整例子理解

假设初始输入为：

```text
[BOS, I, love, AI]
```

token 位置分别是：

```text
0    1      2      3
BOS  I      love   AI
```

---

<a id="origin-2959"></a>
## 53. 第一轮生成：Prefill

最开始：

```python
past_key_values = None
```

因此：

```python
past_len = 0
```

于是：

```python
input_ids[:, past_len:]
```

等价于：

```python
input_ids[:, 0:]
```

所以送入模型的仍然是完整 Prompt：

```text
[BOS, I, love, AI]
```

这一阶段叫：

<a id="origin-2993"></a>
## 54. Prefill

---

<a id="origin-2997"></a>
### 54.1 Embedding 后的输入

假设：

```text
hidden_size = 768
num_attention_heads = 8
num_key_value_heads = 4
head_dim = 96
```

因为：

```text
8 × 96 = 768
```

Embedding 后：

```text
hidden_states.shape
=
[B, 4, 768]
```

---

<a id="origin-3024"></a>
### 54.2 计算 Q、K、V

Attention 中：

```python
xq = self.q_proj(x)
xk = self.k_proj(x)
xv = self.v_proj(x)
```

由于：

```text
Q Head = 8
KV Head = 4
Head Dim = 96
```

所以 reshape 后：

```text
Q:
[B, 4, 8, 96]

K:
[B, 4, 4, 96]

V:
[B, 4, 4, 96]
```

也就是：

```text
Q_BOS
Q_I
Q_love
Q_AI

K_BOS
K_I
K_love
K_AI

V_BOS
V_I
V_love
V_AI
```

---

<a id="origin-3076"></a>
## 55. 第一轮没有历史 KV

代码：

```python
if past_key_value is not None:
    xk = torch.cat([past_key_value[0], xk], dim=1)
    xv = torch.cat([past_key_value[1], xv], dim=1)
```

第一次：

```text
past_key_value = None
```

所以这一段不会执行。

此时：

```text
K =
[K_BOS, K_I, K_love, K_AI]

V =
[V_BOS, V_I, V_love, V_AI]
```

---

<a id="origin-3106"></a>
## 56. 第一轮建立 KV Cache

代码：

```python
past_kv = (xk, xv) if use_cache else None
```

如果：

```python
use_cache=True
```

那么得到：

```text
past_kv =

(
    [K_BOS, K_I, K_love, K_AI],
    [V_BOS, V_I, V_love, V_AI]
)
```

也就是说：

> **第一次 Prefill 会把整个 Prompt 在当前 Transformer Layer 中产生的 K 和 V 保存下来。**

---

<a id="origin-3137"></a>
## 57. KV Cache 是每一层都有一份

这一点非常重要。

MiniMind 中：

```python
presents = []

for layer, past_key_value in zip(self.layers, past_key_values):
    hidden_states, present = layer(...)
    presents.append(present)
```

说明不是整个模型只有一个 KV Cache，而是：

```text
Layer 0:
K Cache
V Cache

Layer 1:
K Cache
V Cache

Layer 2:
K Cache
V Cache

...

Layer 7:
K Cache
V Cache
```

原因是不同层的 hidden state 不同，因此每一层产生的 K、V 也不同。

例如：

```math
K_i^{(1)} = H_i^{(0)}W_K^{(1)}
```

而第二层：

```math
K_i^{(2)} = H_i^{(1)}W_K^{(2)}
```

显然：

```math
K_i^{(1)} \neq K_i^{(2)}
```

所以每一层都必须单独缓存自己的 K 和 V。

---

<a id="origin-3197"></a>
## 58. 第一轮 Attention 是完整矩阵

第一次：

```text
Q 长度 = 4
K 长度 = 4
```

所以：

```math
QK^T
```

是：

```text
4 × 4
```

即：

```math
\begin{bmatrix}
Q_{BOS}\\
Q_I\\
Q_{love}\\
Q_{AI}
\end{bmatrix}
\begin{bmatrix}
K_{BOS}^T &
K_I^T &
K_{love}^T &
K_{AI}^T
\end{bmatrix}
```

得到：

```text
            BOS      I      love      AI

BOS          ✓
I            ✓       ✓
love         ✓       ✓       ✓
AI           ✓       ✓       ✓       ✓
```

通过 Causal Mask 保证每个位置只能看自己和之前的 token。

---

<a id="origin-3250"></a>
## 59. 第一轮最终只使用最后一个位置预测下一个 token

虽然第一次计算了所有位置：

```text
BOS
I
love
AI
```

但是 generate 中：

```python
logits = outputs.logits[:, -1, :]
```

只取最后一个位置：

```text
AI
```

对应的 logits。

也就是根据：

```text
BOS I love AI
```

预测下一个 token。

假设预测得到：

```text
is
```

那么：

```python
input_ids = torch.cat([input_ids, next_token], dim=-1)
```

于是完整 token 序列变成：

```text
[BOS, I, love, AI, is]
```

---

<a id="origin-3303"></a>
## 60. 注意：input_ids 仍然保存完整历史

这是很容易混淆的地方。

此时：

```text
input_ids =
[BOS, I, love, AI, is]
```

完整历史并没有被删除。

原因是完整 `input_ids` 还要用于：

- 最终返回完整生成结果；
- repetition penalty；
- tokenizer decode；
- streamer 输出；
- 保存完整上下文。

但是：

> **完整 input_ids 不代表下一轮会把全部 token 重新送进 Transformer。**

真正送入 Transformer 的内容由：

```python
input_ids[:, past_len:]
```

决定。

---

<a id="origin-3338"></a>
## 61. 第二轮开始：真正体现 KV Cache

第一轮结束后，Cache 中已经有：

```text
K_BOS
K_I
K_love
K_AI

V_BOS
V_I
V_love
V_AI
```

所以：

```python
past_len = past_key_values[0][0].shape[1]
```

得到：

```text
past_len = 4
```

而此时完整：

```text
input_ids =
[BOS, I, love, AI, is]
```

于是：

```python
input_ids[:, past_len:]
```

就是：

```python
input_ids[:, 4:]
```

最终只剩：

```text
[is]
```

因此第二轮真正送入模型的只有：

```text
is
```

而不是：

```text
BOS I love AI is
```

---

<a id="origin-3405"></a>
## 62. 第二轮只计算新 token 的 Q、K、V

第二轮：

```text
x.shape =
[B, 1, 768]
```

所以：

```python
xq = self.q_proj(x)
xk = self.k_proj(x)
xv = self.v_proj(x)
```

只会计算：

```text
Q_is
K_is
V_is
```

不会重新计算：

```text
Q_BOS
Q_I
Q_love
Q_AI
```

也不会重新计算：

```text
K_BOS
K_I
K_love
K_AI
```

更不会重新计算：

```text
V_BOS
V_I
V_love
V_AI
```

---

<a id="origin-3459"></a>
## 63. 历史 K、V 从 Cache 中取回来

Attention 中：

```python
if past_key_value is not None:
    xk = torch.cat([past_key_value[0], xk], dim=1)
    xv = torch.cat([past_key_value[1], xv], dim=1)
```

历史：

```text
past K =
[K_BOS, K_I, K_love, K_AI]

past V =
[V_BOS, V_I, V_love, V_AI]
```

当前新算：

```text
K_is
V_is
```

拼接以后：

```text
K =
[K_BOS, K_I, K_love, K_AI, K_is]

V =
[V_BOS, V_I, V_love, V_AI, V_is]
```

---

<a id="origin-3498"></a>
## 64. 为什么没有缓存 Q？

注意代码只有：

```python
xk = torch.cat(...)
xv = torch.cat(...)
```

没有：

```python
xq = torch.cat(...)
```

所以第二轮：

```text
Q =
[Q_is]

K =
[K_BOS, K_I, K_love, K_AI, K_is]

V =
[V_BOS, V_I, V_love, V_AI, V_is]
```

这是因为历史 Q 已经没有用了。

历史 Q 的作用，是在过去那一轮计算：

```text
“历史 token 自己应该关注谁？”
```

这些输出已经计算完成，没有必要再次计算。

当前真正需要解决的问题只有：

```text
“当前新 token is 应该关注历史中的谁？”
```

所以只需要：

```text
Q_is
```

但它需要和所有历史 K 做匹配，因此历史 K 必须保存。

Softmax 之后还要读取历史信息，因此历史 V 也必须保存。

所以：

> **KV Cache 缓存 K 和 V，而不是 Q。**

---

<a id="origin-3558"></a>
## 65. 第二轮 Attention Score 已经从矩阵变成“一行”

不用 KV Cache 时，第二轮如果重新输入：

```text
BOS I love AI is
```

则：

```text
Q:
5 × d

K:
5 × d
```

需要：

```math
QK^T
```

得到：

```text
5 × 5
```

而使用 KV Cache 后：

```text
Q:
1 × d

K:
5 × d
```

所以：

```math
Q_{is}K^T
```

得到：

```text
1 × 5
```

即：

```text
             BOS       I       love      AI       is

Q_is        score     score    score     score    score
```

所以 KV Cache 可以理解为：

> **原来整个 Attention Score 矩阵都重新计算，现在只计算新增的最后一行。**

---

<a id="origin-3624"></a>
## 66. Softmax 之后如何利用 V

得到：

```text
Q_is
```

与所有 K 的 Attention Score 后，经过 Softmax：

```math
[
\alpha_{BOS},
\alpha_I,
\alpha_{love},
\alpha_{AI},
\alpha_{is}
]
```

然后：

```math
O_{is}
=
\alpha_{BOS}V_{BOS}
+
\alpha_IV_I
+
\alpha_{love}V_{love}
+
\alpha_{AI}V_{AI}
+
\alpha_{is}V_{is}
```

因此：

> 虽然历史 token 没有重新输入模型，但当前 token 仍然能够通过历史 K/V 读取完整上下文信息。

---

<a id="origin-3666"></a>
## 67. 第三轮继续重复

假设第二轮预测：

```text
very
```

那么：

```text
input_ids =
[BOS, I, love, AI, is, very]
```

上一轮 KV Cache 长度已经变成：

```text
5
```

所以：

```python
past_len = 5
```

于是：

```python
input_ids[:, 5:]
```

只得到：

```text
[very]
```

模型只计算：

```text
Q_very
K_very
V_very
```

然后：

```text
K Cache =
K_BOS
K_I
K_love
K_AI
K_is
K_very
```

Attention 只计算：

```math
Q_{very}K_{1:6}^T
```

大小：

```text
1 × 6
```

---

<a id="origin-3739"></a>
## 68. 整个推理流程总结

MiniMind 的生成可以整理成：

```text
初始 Prompt：

[BOS, I, love, AI]

        ↓

========================
Prefill
========================

整个 Prompt 一次送入

Q: 4 个
K: 4 个
V: 4 个

Attention:
4 × 4

建立 KV Cache：

K_BOS K_I K_love K_AI
V_BOS V_I V_love V_AI

        ↓

预测 is

        ↓

========================
Decode 第 1 轮
========================

完整 input_ids：

[BOS, I, love, AI, is]

但是：

past_len = 4

所以真正输入：

[is]

只计算：

Q_is
K_is
V_is

Attention：

Q_is
×
[K_BOS K_I K_love K_AI K_is]^T

得到：

1 × 5

        ↓

预测 very

        ↓

========================
Decode 第 2 轮
========================

完整 input_ids：

[BOS, I, love, AI, is, very]

past_len = 5

真正输入：

[very]

Attention：

1 × 6
```

因此：

```math
\boxed{
\text{大模型推理}
=
\text{Prefill}
+
\text{逐 Token Decode}
}
```

---

<a id="origin-3845"></a>
## 69. Prefill 和 Decode 的区别

<a id="origin-3847"></a>
### 69.1 Prefill

Prompt 一次输入：

```text
[BOS, I, love, AI]
```

特点：

```text
seq_len > 1
```

Attention：

```text
T × T
```

主要任务：

```text
理解整个 Prompt
+
建立所有 Layer 的 KV Cache
```

---

<a id="origin-3877"></a>
### 69.2 Decode

之后每次：

```text
只输入一个新 token
```

例如：

```text
is
```

特点：

```text
seq_len = 1
```

Attention：

```text
1 × 当前总长度
```

主要任务：

```text
使用历史 KV Cache
+
计算当前新 token
+
生成下一个 token
```

---

<a id="origin-3915"></a>
## 70. RoPE 如何知道新 token 的真实位置？

第二轮虽然只输入：

```text
is
```

但它不能被当成 position 0。

MiniMind 中：

```python
start_pos = past_key_values[0][0].shape[1] if past_key_values[0] is not None else 0
```

第一轮缓存长度为：

```text
4
```

所以：

```text
start_pos = 4
```

然后：

```python
position_embeddings = (
    self.freqs_cos[start_pos:start_pos + seq_length],
    self.freqs_sin[start_pos:start_pos + seq_length]
)
```

第二轮：

```text
seq_length = 1
```

于是使用：

```text
position 4
```

所以实际位置仍然是：

```text
BOS   → 0
I     → 1
love  → 2
AI    → 3
is    → 4
very  → 5
```

虽然 Decode 每次只输入一个 token，但位置不会重新从 0 开始。

---

<a id="origin-3979"></a>
## 71. GQA 和 KV Cache 的关系

MiniMind 配置中：

```python
num_attention_heads = 8
num_key_value_heads = 4
```

所以：

```python
self.n_rep = 8 // 4
```

得到：

```text
n_rep = 2
```

说明：

```text
8 个 Query Head
共享
4 个 KV Head
```

也就是每一个 KV Head 被两个 Query Head 使用。

代码：

```python
repeat_kv(xk, self.n_rep)
repeat_kv(xv, self.n_rep)
```

会在 Attention 计算前把：

```text
4 个 KV Head
```

逻辑展开成：

```text
8 个 KV Head
```

但是注意：

```python
past_kv = (xk, xv)
```

发生在 `repeat_kv()` 之前。

因此真正存在 KV Cache 中的仍然只有：

```text
4 个 KV Head
```

而不是：

```text
8 个
```

这正是 GQA 能够降低 KV Cache 显存占用的重要原因之一。

---

<a id="origin-4053"></a>
## 72. presents 为什么叫 presents？

MiniMindModel 中：

```python
presents = []
```

然后：

```python
hidden_states, present = layer(...)
presents.append(present)
```

这里：

```text
past_key_values
```

表示：

> 进入当前 forward 之前已有的 KV Cache。

而：

```text
present_key_value
```

表示：

> 当前 forward 执行完成以后，更新后的完整 KV Cache。

例如：

```text
输入：

past KV =
K1 K2 K3 K4

当前新 token：

K5
```

执行后：

```text
present KV =
K1 K2 K3 K4 K5
```

然后：

```text
present
```

到了下一轮，又变成：

```text
past
```

所以：

```text
past
  ↓
当前 forward
  ↓
present
  ↓
下一轮
  ↓
past
```

因此 `present` 这个命名本身是合理的。

---

<a id="origin-4138"></a>
## 73. 训练阶段 KV Cache 基本没有用

这里一定要区分：

> **K、V 有用。**

和：

> **KV Cache 有用。**

这是两回事。

训练时 Attention 当然仍然必须计算：

```text
Q
K
V
```

但是通常：

```text
不需要缓存 K、V 给下一次 forward
```

---

<a id="origin-4166"></a>
## 74. 为什么训练不需要 KV Cache？

假设训练样本：

```text
[BOS, I, love, AI, very, much]
```

训练时通常一次全部输入：

```text
seq_len = 6
```

直接计算：

```text
Q1 ... Q6
K1 ... K6
V1 ... V6
```

然后通过 Causal Mask：

```text
BOS        ✓
I          ✓ ✓
love       ✓ ✓ ✓
AI         ✓ ✓ ✓ ✓
very       ✓ ✓ ✓ ✓ ✓
much       ✓ ✓ ✓ ✓ ✓ ✓
```

一次 forward 就可以同时训练：

```text
BOS                     → I
BOS I                   → love
BOS I love              → AI
BOS I love AI           → very
BOS I love AI very      → much
```

所以根本没有必要：

```text
先输入 BOS
↓
保存 KV

再输入 I
↓
保存 KV

再输入 love
↓
保存 KV
```

这种串行训练方式反而会失去 GPU 并行计算的优势。

---

<a id="origin-4229"></a>
## 75. MiniMind 训练时一般 use_cache=False

Attention 中：

```python
past_kv = (xk, xv) if use_cache else None
```

训练时通常：

```python
use_cache=False
```

于是：

```text
past_kv = None
```

虽然当前 forward 中仍然计算了：

```text
K
V
```

但不会把它们保存下来给下一轮使用。

所以最准确的说法是：

> **训练不是不计算 K、V，而是不需要 KV Cache。**

---

<a id="origin-4264"></a>
## 76. 为什么训练阶段缓存 K/V 反而不自然？

训练阶段需要反向传播。

例如：

```math
K=XW_K
```

```math
V=XW_V
```

Loss 最终还要沿着计算图反向传播：

```text
Loss
 ↓
Attention
 ↓
K / V
 ↓
W_K / W_V
```

也就是说：

```math
\frac{\partial L}{\partial W_K}
```

和：

```math
\frac{\partial L}{\partial W_V}
```

都需要正常计算。

而推理时：

```python
@torch.inference_mode()
```

不需要梯度：

```text
参数不会更新
```

所以历史 K/V 一旦计算完成，就可以直接保存并重复使用。

因此：

```math
\boxed{
\text{KV Cache 主要是一种推理优化，而不是训练优化}
}
```

---

<a id="origin-4328"></a>
## 77. 训练、Prefill、Decode 的完整对比

| 阶段 | 本轮输入 | Q 数量 | K/V 数量 | Attention Score | 是否使用 KV Cache |
|---|---:|---:|---:|---:|---|
| 训练 | 整个训练序列 | T | T | T×T | 通常否 |
| 推理 Prefill | 整个 Prompt | T | T | T×T | 建立 Cache |
| Decode 第 1 步 | 1 个新 token | 1 | T+1 | 1×(T+1) | 是 |
| Decode 第 2 步 | 1 个新 token | 1 | T+2 | 1×(T+2) | 是 |
| Decode 第 3 步 | 1 个新 token | 1 | T+3 | 1×(T+3) | 是 |

---

<a id="origin-4340"></a>
## 78. 完整 input_ids 和计算历史不是同一个东西

MiniMind 中实际上同时维护了两种历史。

<a id="origin-4344"></a>
### 78.1 第一种：完整 token 历史

```python
input_ids
```

例如：

```text
[BOS, I, love, AI, is, very]
```

它主要用于：

```text
最终输出
repetition penalty
token decode
streamer
```

---

<a id="origin-4367"></a>
### 78.2 第二种：计算历史

```python
past_key_values
```

里面保存的是：

```text
每一层历史 token 的 K/V
```

它主要用于：

```text
避免历史 token 再次经过 Transformer
```

因此可以记成：

```text
逻辑历史：
input_ids

计算历史：
past_key_values
```

---

<a id="origin-4397"></a>
## 79. 把 generate() 简化以后，KV Cache 就非常清楚

去掉 top-k、top-p、temperature 等采样逻辑后，核心可以理解成：

```python
input_ids = prompt
past_key_values = None

for _ in range(max_new_tokens):

    # 已经计算过多少 token
    past_len = (
        past_key_values[0][0].shape[1]
        if past_key_values
        else 0
    )

    # 只拿没有计算过的新 token
    new_input = input_ids[:, past_len:]

    outputs = self.forward(
        new_input,
        past_key_values=past_key_values,
        use_cache=True
    )

    # 根据最后一个位置预测下一个 token
    next_token = sample(outputs.logits[:, -1, :])

    # 完整 token 历史继续保存
    input_ids = torch.cat(
        [input_ids, next_token],
        dim=-1
    )

    # 保存新的 KV Cache
    past_key_values = outputs.past_key_values
```

KV Cache 的两个核心操作就在这里：

```text
input_ids[:, past_len:]
```

负责：

```text
切掉已经计算过的历史 token
```

而 Attention 中：

```python
xk = torch.cat([past_key_value[0], xk], dim=1)
xv = torch.cat([past_key_value[1], xv], dim=1)
```

负责：

```text
把历史 token 留下来的 K/V 接回来
```

可以总结成：

> **上面切掉，下面接回来。**

---

<a id="origin-4467"></a>
## 80. 把 Attention 简化以后更容易看懂

KV Cache 相关逻辑本质上就是：

```python
def attention(x, past_kv=None):

    # 当前新输入
    q = Wq(x)
    k = Wk(x)
    v = Wv(x)

    # 拼接历史 KV
    if past_kv is not None:
        old_k, old_v = past_kv

        k = cat(old_k, k)
        v = cat(old_v, v)

    # 更新 Cache
    new_cache = (k, v)

    # q 只有当前新 token
    output = softmax(q @ k.T) @ v

    return output, new_cache
```

图示：

```text
当前新 token
     │
     ├──→ Q_new
     │
     ├──→ K_new ─────┐
     │                │
     └──→ V_new ──┐   │
                  │   │
历史 K ───────────┼───┘
                  ↓
               K_all

历史 V ───────────┼────┐
                  │    │
V_new ────────────┘    ↓
                    V_all


Q_new × K_all^T
       ↓
    Softmax
       ↓
     × V_all
       ↓
      O_new
```

---

<a id="origin-4527"></a>
## 81. 最终总结

KV Cache 并没有修改 Attention 的数学公式：

```math
\operatorname{Attention}(Q,K,V)
=
\operatorname{softmax}
\left(
\frac{QK^T}{\sqrt d}
\right)V
```

它修改的是：

> **下一轮到底还需要重新计算哪些 token。**

不使用 KV Cache：

```text
每生成一个新 token

都重新输入：

全部历史 token + 新 token

然后重新计算：

全部 Q
全部 K
全部 V
全部 Attention Score
```

使用 KV Cache：

```text
第一次：

整个 Prompt 一次 Prefill
↓
保存每一层全部历史 K/V

之后：

每轮只输入一个新 token
↓
只计算新的 Q/K/V
↓
新 K/V 追加到历史 Cache
↓
当前 Q 和所有历史 K 做 Attention
```

所以：

```math
T\times T
```

的大矩阵重复计算，变成：

```math
1\times T
```

的新增一行计算。

---

<a id="origin-4597"></a>
## 82. 推理要点

<a id="origin-4599"></a>
### 82.1 第一句

> **KV Cache 缓存的是每一层历史 token 的 K 和 V，而不是原始 token，也不是 Q。**

<a id="origin-4603"></a>
#### 82.1.1 第二句

> **Prefill 一次处理整个 Prompt，Decode 才是一个 token 一个 token 地生成。**

<a id="origin-4607"></a>
#### 82.1.2 第三句

> **KV Cache 不改变 Attention 公式，只减少重复计算。**

<a id="origin-4611"></a>
#### 82.1.3 第四句

> **不用 Cache 时重新算整个 \(T\times T\) Attention；使用 Cache 后，Decode 每轮只算新增的 \(1\times T\) 那一行。**

<a id="origin-4615"></a>
#### 82.1.4 第五句

> **训练不是不需要 K、V，而是不需要缓存 K、V。**

<a id="origin-4619"></a>
#### 82.1.5 第六句

> **KV Cache 主要是推理优化，而不是训练优化。**

<a id="origin-4623"></a>
#### 82.1.6 第七句

MiniMind 中最核心的两部分代码是：

```python
# generate 中：
input_ids[:, past_len:]
```

负责：

```text
把历史 token 从本轮模型输入中切掉
```

以及：

```python
# Attention 中：
xk = torch.cat([past_key_value[0], xk], dim=1)
xv = torch.cat([past_key_value[1], xv], dim=1)
```

负责：

```text
把历史 K/V 从 Cache 中重新接回来
```

因此可以用一句话概括：

<a id="origin-4654"></a>
## 83. 上面切掉历史输入，下面接回历史 K/V。

这就是 MiniMind 中 KV Cache 的完整工作原理。

---

<a id="origin-4660"></a>
## 84. Transformers 中 Streamer 的基本用法

<a id="origin-4662"></a>
## 85. Streamer 是干什么的？

正常情况下：

```python
outputs = model.generate(...)
```

模型会：

```text
token1
↓
token2
↓
token3
↓
...
↓
EOS
↓
全部生成结束
↓
一次性把结果返回
```

所以用户可能要等整个回答全部生成完，才能看到文字。

而 `streamer` 的作用就是：

> **模型每生成一部分 token，就立即把已经可以显示的文本输出出去。**

效果类似 ChatGPT：

```text
浙
浙江
浙江大学
浙江大学位于
浙江大学位于宁波
...
```

而不是等全部生成完以后才一次性显示：

```text
浙江大学位于宁波。
```

---

<a id="origin-4713"></a>
## 86. 最简单的 `TextStreamer`

Transformers 提供：

```python
from transformers import TextStreamer
```

最基本的写法：

```python
from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer

tokenizer = AutoTokenizer.from_pretrained("模型路径")
model = AutoModelForCausalLM.from_pretrained("模型路径")

prompt = "浙江大学软件学院位于哪里？"

inputs = tokenizer(
    prompt,
    return_tensors="pt"
)

streamer = TextStreamer(
    tokenizer,
    skip_prompt=True,
    skip_special_tokens=True
)

model.generate(
    **inputs,
    max_new_tokens=100,
    streamer=streamer
)
```

运行时就会在终端中逐渐输出：

```text
浙江大学软件学院位于浙江省宁波市。
```

而不是等到 `generate()` 完全执行结束以后再统一打印。

---

<a id="origin-4759"></a>
## 87. 最关键的其实只有两步

第一步：

```python
streamer = TextStreamer(tokenizer)
```

创建一个 Streamer。

第二步：

```python
model.generate(
    ...,
    streamer=streamer
)
```

把它交给 `generate()`。

所以可以把整个流程理解成：

```text
model.generate()
      │
      │ 生成 token
      ▼
   token_id
      │
      ▼
   streamer
      │
      │ tokenizer.decode()
      ▼
     文本
      │
      ▼
   立即显示
```

---

<a id="origin-4802"></a>
## 88. `TextStreamer(tokenizer)` 为什么必须传 tokenizer？

因为大模型真正生成的是：

```text
Token ID
```

例如：

```text
[3241, 982, 7312]
```

而不是直接生成：

```text
浙江大学
```

所以 Streamer 收到 token 后，需要：

```python
tokenizer.decode(...)
```

把 Token ID 转回人能看到的文本。

整个过程：

```text
模型
↓
token_id
↓
Streamer
↓
Tokenizer.decode()
↓
字符串
↓
显示
```

---

<a id="origin-4848"></a>
## 89. `skip_prompt=True`

例如输入：

```text
用户：浙江大学在哪里？
```

模型回答：

```text
浙江大学位于浙江省杭州市。
```

如果：

```python
skip_prompt=False
```

Streamer 可能连输入 Prompt 一起显示：

```text
用户：浙江大学在哪里？浙江大学位于浙江省杭州市。
```

如果：

```python
skip_prompt=True
```

则跳过输入 Prompt，只显示新生成的部分：

```text
浙江大学位于浙江省杭州市。
```

所以聊天机器人通常会使用：

```python
streamer = TextStreamer(
    tokenizer,
    skip_prompt=True
)
```

---

<a id="origin-4897"></a>
## 90. `skip_special_tokens=True`

模型输出中可能包含：

```text
<bos>
<eos>
<|im_start|>
<|im_end|>
```

这类特殊 token。

如果：

```python
skip_special_tokens=True
```

解码时就不会把这些特殊 token 显示给用户。

因此经常写：

```python
streamer = TextStreamer(
    tokenizer,
    skip_prompt=True,
    skip_special_tokens=True
)
```

---

<a id="origin-4930"></a>
## 91. Streamer 并不是负责生成 token 的

这一点非常重要。

很多人看到：

```python
streamer=streamer
```

容易误以为：

> Streamer 参与了模型采样。

实际上不是。

真正负责生成的仍然是：

```python
model.generate()
```

内部仍然执行：

```text
模型 forward
↓
得到 logits
↓
temperature / top-k / top-p
↓
选择 next_token
↓
把 next_token 加入输入
↓
继续 forward
```

Streamer 只是旁边接收生成结果：

```text
                ┌──────────────→ Streamer → 显示
                │
model.generate()
      │
      ▼
生成 next_token
      │
      ▼
继续下一轮生成
```

所以：

> **Streamer 负责“怎么把生成过程展示出来”，而不是“怎么生成”。**

---

<a id="origin-4988"></a>
## 92. `TextStreamer` 内部可以简单理解成什么？

可以把它极度简化成：

```python
class SimpleStreamer:

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def put(self, token_ids):
        text = self.tokenizer.decode(token_ids)
        print(text, end="", flush=True)

    def end(self):
        print()
```

真正的 `TextStreamer` 要复杂一些，因为它不会机械地每得到一个 token 就一定立即打印，而是会处理：

- token 解码；
- 单词边界；
- 文本缓存；
- Prompt 跳过；
- 最后的缓存刷新。

可以先理解为：

```text
put(token)
    ↓
收到新 token
    ↓
decode
    ↓
打印

end()
    ↓
生成结束
    ↓
把剩余缓存输出
```

---

<a id="origin-5034"></a>
## 93. `generate()` 和 Streamer 是怎么连接起来的？

可以把内部过程简化理解为：

```python
while not finished:

    outputs = model(input_ids)

    next_token = sample(outputs.logits)

    # 告诉 streamer：
    # 我刚刚生成了这个 token
    streamer.put(next_token)

    input_ids = append(
        input_ids,
        next_token
    )

streamer.end()
```

于是：

```text
生成 token1
↓
streamer.put(token1)
↓
生成 token2
↓
streamer.put(token2)
↓
生成 token3
↓
streamer.put(token3)
↓
...
↓
EOS
↓
streamer.end()
```

这就是 Streaming Generation 最核心的原理。

---

<a id="origin-5083"></a>
## 94. `TextStreamer` 的问题：它主要负责直接打印

比如：

```python
streamer = TextStreamer(tokenizer)

model.generate(
    **inputs,
    streamer=streamer
)
```

文字会直接打印到：

```text
stdout / 控制台
```

这很适合：

```text
命令行程序
Demo
课堂演示
```

但是如果你开发：

```text
网页
Gradio
GUI
聊天窗口
API
```

通常不是简单地：

```python
print(...)
```

而是希望：

```python
for text in streamer:
    更新网页
```

这时候就可以使用：

```python
TextIteratorStreamer
```

---

<a id="origin-5141"></a>
## 95. `TextIteratorStreamer`

基本导入：

```python
from transformers import TextIteratorStreamer
```

基本写法：

```python
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TextIteratorStreamer
)

from threading import Thread

tokenizer = AutoTokenizer.from_pretrained("模型路径")
model = AutoModelForCausalLM.from_pretrained("模型路径")

prompt = "介绍一下 Transformer。"

inputs = tokenizer(
    prompt,
    return_tensors="pt"
)

streamer = TextIteratorStreamer(
    tokenizer,
    skip_prompt=True,
    skip_special_tokens=True
)

generation_kwargs = {
    **inputs,
    "max_new_tokens": 200,
    "streamer": streamer
}

thread = Thread(
    target=model.generate,
    kwargs=generation_kwargs
)

thread.start()

for new_text in streamer:
    print(new_text, end="", flush=True)
```

---

<a id="origin-5195"></a>
## 96. 为什么 `TextIteratorStreamer` 经常要配 `Thread`？

如果直接写：

```python
model.generate(...)
```

程序会一直卡在这里：

```text
开始 generate
↓
生成 token
↓
生成 token
↓
生成 token
↓
...
↓
全部生成结束
↓
generate 返回
↓
程序才继续执行
```

那么你就没办法同时：

```python
for text in streamer:
```

读取 Streamer。

因此通常把生成放到另外一个线程：

```text
主线程                     生成线程

for text in streamer       model.generate()
       ▲                         │
       │                         │
       └────── Streamer ◄────────┘
```

生成线程：

```text
不断产生 token
```

主线程：

```text
不断从 streamer 读取文本
```

于是就实现了：

> **一边生成，一边显示。**

---

<a id="origin-5260"></a>
## 97. `TextStreamer` 和 `TextIteratorStreamer` 的区别

| 类 | 主要用途 |
|---|---|
| `TextStreamer` | 直接把生成文字打印到终端 |
| `TextIteratorStreamer` | 程序自己通过 `for` 循环获取生成文本 |

例如：

<a id="origin-5269"></a>
### 97.1 `TextStreamer`

```python
streamer = TextStreamer(tokenizer)

model.generate(
    **inputs,
    streamer=streamer
)
```

相当于：

```text
模型生成
↓
Streamer
↓
直接打印
```

---

<a id="origin-5292"></a>
### 97.2 `TextIteratorStreamer`

```python
for text in streamer:
    ...
```

相当于：

```text
模型生成
↓
Streamer Queue
↓
你的程序自己获取 text
↓
想怎么处理都可以
```

例如：

```python
for text in streamer:

    print(text)

    # 或者
    update_web_page(text)

    # 或者
    send_to_frontend(text)
```

---

<a id="origin-5327"></a>
## 98. `TextIteratorStreamer` 可以理解成一个 Queue

内部思想可以简单理解成：

```text
生成线程：

token
↓
decode
↓
text
↓
Queue.put(text)
```

另一边：

```text
主线程：

Queue.get()
↓
new_text
↓
显示
```

所以：

```python
for new_text in streamer:
```

本质上可以理解成不断从一个：

```text
文本队列
```

中取出最新生成的内容。

---

<a id="origin-5371"></a>
## 99. 最简单的记忆方式

<a id="origin-5373"></a>
### 99.1 普通生成

```python
output = model.generate(...)
```

流程：

```text
生成全部 token
↓
generate 返回
↓
decode
↓
显示完整回答
```

---

<a id="origin-5393"></a>
### 99.2 `TextStreamer`

```python
model.generate(
    ...,
    streamer=TextStreamer(tokenizer)
)
```

流程：

```text
生成 token
↓
Streamer
↓
decode
↓
直接打印

生成 token
↓
Streamer
↓
decode
↓
继续打印
```

---

<a id="origin-5424"></a>
### 99.3 `TextIteratorStreamer`

```text
生成线程
    │
    ▼
model.generate()
    │
    ▼
Streamer
    │
    ▼
Queue
    │
    ▼
for new_text in streamer
    │
    ▼
自己的程序处理
```

---

<a id="origin-5447"></a>
## 100. 一句话总结

`streamer` 并不改变 Transformer 的生成算法。

它只是把原来的：

```text
全部生成完成
↓
一次性返回
```

变成：

```text
生成一点
↓
交给 Streamer

再生成一点
↓
再交给 Streamer

再生成一点
↓
再交给 Streamer
```

因此：

\[
\boxed{
Streamer
=
模型生成过程与实时显示过程之间的接口
}
\]

最简单的：

```python
TextStreamer
```

适合直接输出到终端。

而：

```python
TextIteratorStreamer
```

则适合：

```text
GUI
Web
Gradio
聊天机器人
API 流式返回
```

因为程序可以自己逐段取得生成出来的文本。
