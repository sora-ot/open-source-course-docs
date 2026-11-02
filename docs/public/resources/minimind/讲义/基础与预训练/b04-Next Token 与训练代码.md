# Next Token 与训练代码


在 Causal Language Model（如 GPT、MiniMind）中，一个很容易产生的疑问是：

> 为什么是 `BOS I love → AI`，而不是简单地 `love → AI`？
>
> 如果模型只有一次 `forward()`，它是怎么把 `BOS I love` 这些前面的 token 全部作为上下文考虑进去的？

核心答案是：

> **Transformer 在一次 forward 中，会同时为序列中的每一个位置计算一个“包含前文上下文信息”的 hidden state。**

因此：

```text
love 这个位置的 hidden state
```

并不只是表示：

```text
love
```

而是表示：

```text
BOS I love
```

这主要是通过 **Causal Self-Attention** 实现的。

---

<a id="origin-35"></a>
## 1. 先看一个具体例子

假设输入序列是：

```text
BOS I love AI
```

对应：

```python
input_ids = [
    BOS,
    I,
    love,
    AI
]
```

一次送进 Transformer：

```python
hidden_states = model(input_ids)
```

模型会一次性产生四个位置的 hidden state：

```text
位置 0：BOS  → h0
位置 1：I    → h1
位置 2：love → h2
位置 3：AI   → h3
```

但是这里需要特别注意：

```text
h0 并不只是普通的 BOS embedding

h1 并不只是普通的 I embedding

h2 并不只是普通的 love embedding

h3 并不只是普通的 AI embedding
```

经过 Transformer 的 Self-Attention 后，它们已经融合了上下文信息。

实际上可以理解成：

```text
h0 = f(BOS)

h1 = f(BOS, I)

h2 = f(BOS, I, love)

h3 = f(BOS, I, love, AI)
```

所以：

```text
h2
```

虽然位于 `love` 这个位置，但是它代表的是：

```text
BOS I love
```

这整个上下文。

---

<a id="origin-111"></a>
## 2. 为什么 love 能看到 BOS 和 I？

因为 Transformer 使用了：

```text
Self-Attention
```

同时 Decoder-only 模型又加入了：

```text
Causal Mask
```

也就是因果掩码。

假设输入：

```text
BOS    I    love    AI
```

Causal Mask 规定每个位置：

- 可以看到自己；
- 可以看到前面的 token；
- 不能看到未来 token。

因此：

```text
            可以看到的 token

            BOS    I    love    AI

BOS          ✓     ×      ×      ×

I            ✓     ✓      ×      ×

love         ✓     ✓      ✓      ×

AI           ✓     ✓      ✓      ✓
```

因此：

```text
BOS 位置：
只能看到 BOS

I 位置：
可以看到 BOS + I

love 位置：
可以看到 BOS + I + love

AI 位置：
可以看到 BOS + I + love + AI
```

所以当模型处理 `love` 位置时，它实际上已经可以读取：

```text
BOS
I
love
```

三部分信息。

---

<a id="origin-183"></a>
## 3. Self-Attention 是怎么做到的？

假设输入有四个 token：

```text
BOS    I    love    AI
```

首先，每个 token 会生成：

```text
Q：Query
K：Key
V：Value
```

可以表示为：

```text
Q_BOS
Q_I
Q_love
Q_AI
```

```text
K_BOS
K_I
K_love
K_AI
```

```text
V_BOS
V_I
V_love
V_AI
```

然后计算 Attention：

\[
QK^T
\]

得到一个注意力矩阵。

例如：

```text
                 Key

             BOS     I     love     AI

Query

BOS           ?      ?      ?       ?

I             ?      ?      ?       ?

love          ?      ?      ?       ?

AI            ?      ?      ?       ?
```

然后加上 Causal Mask：

```text
                 BOS       I       love       AI

BOS               ✓       -∞        -∞       -∞

I                 ✓        ✓        -∞       -∞

love              ✓        ✓         ✓       -∞

AI                ✓        ✓         ✓        ✓
```

这里的：

```text
-∞
```

表示：

> 这个位置不能看。

经过 Softmax 后：

```text
softmax(-∞) ≈ 0
```

所以未来 token 的注意力权重会变成 0。

---

<a id="origin-282"></a>
## 4. love 位置到底算了什么？

对于 `love` 这个位置，它可以看到：

```text
BOS
I
love
```

因此它最终得到的表示可以简化理解为：

\[
h_{\text{love}}
=
a_1 V_{\text{BOS}}
+
a_2 V_{\text{I}}
+
a_3 V_{\text{love}}
\]

其中：

```text
a1
a2
a3
```

是 attention 权重。

例如可能是：

```text
BOS  → 0.1
I    → 0.4
love → 0.5
```

那么：

\[
h_{\text{love}}
=
0.1V_{\text{BOS}}
+
0.4V_{\text{I}}
+
0.5V_{\text{love}}
\]

所以：

```text
h_love
```

已经不是单纯的 `"love"`。

它实际上已经融合了：

```text
BOS
I
love
```

的上下文信息。

---

<a id="origin-354"></a>
## 5. 多层 Transformer 会进一步融合上下文

实际模型中一般不是只有一层 Attention。

而是：

```text
输入 Embedding

    ↓

Transformer Block 1

    ↓

Transformer Block 2

    ↓

Transformer Block 3

    ↓

...

    ↓

Transformer Block N
```

假设关注 `love` 位置。

第一层之后：

```text
love
  ↓
融合 BOS、I、love
```

第二层：

```text
继续基于已经融合后的表示进行计算
```

第三层：

```text
进一步抽取更复杂的上下文关系
```

直到最后得到：

```python
hidden_states[:, 2, :]
```

这个向量。

这个向量真正表示的不是：

```text
love
```

而是：

```text
在 "BOS I love" 这个上下文中，
当前 love 位置的语义表示。
```

---

<a id="origin-429"></a>
## 6. 为什么只需要一次 forward？

这正是 Transformer 和 RNN 非常不同的地方。

RNN 更接近：

```text
先处理 BOS

    ↓

再处理 I

    ↓

再处理 love

    ↓

再处理 AI
```

是比较明显的串行过程。

而 Transformer 可以直接：

```text
BOS I love AI
```

整个序列一起送进去。

一次矩阵计算就可以同时得到：

```text
h0 = f(BOS)

h1 = f(BOS, I)

h2 = f(BOS, I, love)

h3 = f(BOS, I, love, AI)
```

也就是说，一次 forward 相当于同时计算了多个前缀：

```text
BOS

BOS I

BOS I love

BOS I love AI
```

并不需要真的运行四次模型。

---

<a id="origin-489"></a>
## 7. 一次 forward 后发生了什么？

假设输入：

```text
BOS I love AI EOS
```

经过：

```python
hidden_states = self.model(input_ids)
```

得到：

```text
hidden_states[0]
=
BOS 的上下文表示


hidden_states[1]
=
BOS I 的上下文表示


hidden_states[2]
=
BOS I love 的上下文表示


hidden_states[3]
=
BOS I love AI 的上下文表示


hidden_states[4]
=
BOS I love AI EOS 的上下文表示
```

接下来：

```python
logits = self.lm_head(hidden_states)
```

`lm_head` 会把：

```text
hidden_size
```

映射到：

```text
vocab_size
```

也就是：

```text
上下文表示
      ↓
整个词表中每个 token 的预测分数
```

因此：

```text
logits[0]
```

表示：

```text
看到 BOS 后，
下一个 token 是什么？
```

---

```text
logits[1]
```

表示：

```text
看到 BOS I 后，
下一个 token 是什么？
```

---

```text
logits[2]
```

表示：

```text
看到 BOS I love 后，
下一个 token 是什么？
```

---

```text
logits[3]
```

表示：

```text
看到 BOS I love AI 后，
下一个 token 是什么？
```

---

<a id="origin-611"></a>
## 8. 为什么 logits[2] 能预测 AI？

现在假设：

```text
input_ids:

BOS    I    love    AI    EOS
```

模型产生：

```text
logits[0]
logits[1]
logits[2]
logits[3]
logits[4]
```

其中：

```text
logits[2]
```

来自：

```text
hidden_states[2]
```

而：

```text
hidden_states[2]
```

已经通过 Causal Self-Attention 融合了：

```text
BOS I love
```

因此：

```text
logits[2]
```

实际表示：

\[
P(\text{next token}\mid BOS,I,love)
\]

所以它预测：

```text
AI
```

是完全合理的。

不是：

\[
P(AI\mid love)
\]

而是：

\[
P(AI\mid BOS,I,love)
\]

---

<a id="origin-689"></a>
## 9. labels 为什么要错开一位？

Dataset 中可能返回：

```text
input_ids:

[BOS, I, love, AI, EOS]
```

以及：

```text
labels:

[BOS, I, love, AI, EOS]
```

看起来完全没有错位。

但是在模型的 `forward()` 中：

```python
x = logits[..., :-1, :]
y = labels[..., 1:]
```

会进行错位。

原来的：

```text
logits：

位置0
位置1
位置2
位置3
位置4
```

去掉最后一个：

```text
x：

logits[0]
logits[1]
logits[2]
logits[3]
```

而 labels：

```text
BOS
I
love
AI
EOS
```

去掉第一个：

```text
y：

I
love
AI
EOS
```

于是形成：

```text
logits[0]  ↔ I
logits[1]  ↔ love
logits[2]  ↔ AI
logits[3]  ↔ EOS
```

而 logits 各位置所包含的上下文分别是：

```text
logits[0]
来自 f(BOS)

        ↓

预测 I
```

```text
logits[1]
来自 f(BOS, I)

        ↓

预测 love
```

```text
logits[2]
来自 f(BOS, I, love)

        ↓

预测 AI
```

```text
logits[3]
来自 f(BOS, I, love, AI)

        ↓

预测 EOS
```

因此真正训练的是：

```text
BOS
    → I

BOS I
    → love

BOS I love
    → AI

BOS I love AI
    → EOS
```

---

<a id="origin-827"></a>
## 10. 对应到 MiniMind 的代码

MiniMind 中：

```python
hidden_states, past_key_values, aux_loss = self.model(
    input_ids,
    attention_mask,
    past_key_values,
    use_cache,
    **kwargs
)
```

假设：

```python
input_ids = [
    BOS,
    I,
    love,
    AI,
    EOS
]
```

那么经过一次 Transformer：

```text
hidden_states[0]
=
f(BOS)

hidden_states[1]
=
f(BOS, I)

hidden_states[2]
=
f(BOS, I, love)

hidden_states[3]
=
f(BOS, I, love, AI)

hidden_states[4]
=
f(BOS, I, love, AI, EOS)
```

然后：

```python
logits = self.lm_head(hidden_states)
```

得到：

```text
logits[0]
= 基于 BOS 预测下一个 token

logits[1]
= 基于 BOS I 预测下一个 token

logits[2]
= 基于 BOS I love 预测下一个 token

logits[3]
= 基于 BOS I love AI 预测下一个 token
```

最后：

```python
x = logits[..., :-1, :]
y = labels[..., 1:]
```

对齐成：

```text
logits[0] → I

logits[1] → love

logits[2] → AI

logits[3] → EOS
```

---

<a id="origin-920"></a>
## 11. 一张图理解整个过程

```text
输入：

BOS       I       love       AI       EOS
 │        │         │         │
 │        │         │         │
 └────────┴─────────┴─────────┴───────
              Transformer
         Causal Self-Attention
                  │
                  ↓

h0        h1         h2         h3         h4

│          │          │          │
│          │          │          │
│          │          │          │

表示：     表示：      表示：      表示：

BOS       BOS I      BOS I love  BOS I love AI

│          │          │          │
↓          ↓          ↓          ↓

lm_head   lm_head    lm_head    lm_head

│          │          │          │
↓          ↓          ↓          ↓

logits0   logits1    logits2    logits3

│          │          │          │
↓          ↓          ↓          ↓

预测 I    预测 love   预测 AI    预测 EOS
```

所以真正发生的是：

```text
BOS
↓
I


BOS I
↓
love


BOS I love
↓
AI


BOS I love AI
↓
EOS
```

---

<a id="origin-985"></a>
## 12. 最关键的理解

很多初学者容易把：

```text
logits[2]
```

理解成：

```text
只根据第 2 个 token，也就是 love，预测 AI
```

这是不对的。

正确理解应该是：

```text
logits[2]
```

虽然位于：

```text
love
```

这个位置，

但是它对应的 hidden state 已经通过 Self-Attention 看到了：

```text
BOS
I
love
```

所以实际上：

\[
\text{logits}_2
=
f(BOS,I,love)
\]

然后模型学习：

\[
P(AI\mid BOS,I,love)
\]

而不是：

\[
P(AI\mid love)
\]

---

<a id="origin-1045"></a>
## 13. 为什么训练时一次 forward，生成时却要多次 forward？

这里还可以进一步区分：

<a id="origin-1049"></a>
### 13.1 训练阶段

训练时整句话已经知道：

```text
BOS I love AI EOS
```

所以可以一次全部输入：

```python
model([
    BOS,
    I,
    love,
    AI,
    EOS
])
```

借助 Causal Mask：

```text
每个位置都只能看前面，
但是所有位置可以并行计算。
```

因此一次 forward 就可以同时训练：

```text
BOS            → I
BOS I          → love
BOS I love     → AI
BOS I love AI  → EOS
```

---

<a id="origin-1087"></a>
### 13.2 推理生成阶段

生成的时候未来 token 不知道。

例如一开始只有：

```text
BOS I
```

模型先预测：

```text
love
```

然后变成：

```text
BOS I love
```

再预测：

```text
AI
```

再变成：

```text
BOS I love AI
```

再预测：

```text
EOS
```

因此生成是：

```text
一步一步自回归生成
```

而训练可以：

```text
一次 forward 并行计算所有位置。
```

---

<a id="origin-1141"></a>
## 14. 最后一句话总结

一定要记住：

> **Transformer 中某个位置的 hidden state，不只是这个 token 本身的表示，而是通过 Causal Self-Attention 融合了当前位置以及之前所有 token 的上下文表示。**

因此：

```text
love 位置
```

对应的实际上是：

```text
BOS I love
```

所以：

```text
love 位置的 logits
```

真正表达的是：

\[
P(\text{next token}\mid BOS,I,love)
\]

于是训练：

```text
BOS I love → AI
```

而不是简单的：

```text
love → AI
```

整个过程之所以只需要一次 forward，是因为 Transformer 可以利用矩阵运算，在一次计算中**并行得到所有位置的上下文表示**：

```text
BOS
BOS I
BOS I love
BOS I love AI
...
```

然后同时完成所有位置的 Next Token Prediction。
---

<a id="origin-1196"></a>
## 15. 为什么一个序列样本可以完成多条“前缀 → 下一 Token”的训练？

另一个很重要的问题是：

> 按照传统做法，如果一句话是 `I love AI`，似乎应该构造多条训练样本：
>
> - `BOS → I`
> - `BOS I → love`
> - `BOS I love → AI`
> - `BOS I love AI → EOS`
>
> 那为什么在 Transformer 里，只需要一个：
>
> ```text
> [BOS, I, love, AI, EOS]
> ```
>
> 就可以完成上面几条训练任务？

核心答案是：

> **一个 Dataset 样本虽然只有一个序列，但 Transformer 会在这个序列的每一个位置都产生一个预测结果，因此一个长度为 T 的序列，可以同时提供大约 T-1 个 next-token 训练目标。**

---

<a id="origin-1221"></a>
## 16. 传统做法：显式构造多个样本

假设一句话是：

```text
I love AI
```

加入特殊 token 后：

```text
BOS I love AI EOS
```

如果按照“一个前缀对应一条训练样本”的传统思路，可以构造：

```text
样本 1：

输入：
BOS

标签：
I
```

```text
样本 2：

输入：
BOS I

标签：
love
```

```text
样本 3：

输入：
BOS I love

标签：
AI
```

```text
样本 4：

输入：
BOS I love AI

标签：
EOS
```

也就是：

```text
BOS              → I

BOS I            → love

BOS I love       → AI

BOS I love AI    → EOS
```

如果真的这样训练，就可能需要分别执行：

```python
model([BOS])

model([BOS, I])

model([BOS, I, love])

model([BOS, I, love, AI])
```

也就是多次 forward。

---

<a id="origin-1305"></a>
## 17. 这样做会产生大量重复计算

观察这些样本：

```text
[BOS]

[BOS, I]

[BOS, I, love]

[BOS, I, love, AI]
```

会发现前面的内容被重复计算了很多次。

例如：

```text
BOS
```

出现在所有样本里。

```text
BOS I
```

也会在后面的多个样本中重复出现。

如果每个前缀都单独做一次 forward，就会产生很多重复计算。

---

<a id="origin-1339"></a>
## 18. Transformer 的做法：整个序列一次送进去

Transformer 训练时直接输入：

```text
[BOS, I, love, AI, EOS]
```

也就是：

```python
input_ids = [
    BOS,
    I,
    love,
    AI,
    EOS
]
```

然后只做一次：

```python
hidden_states = model(input_ids)
```

一次 forward 就会同时得到：

```text
h0
h1
h2
h3
h4
```

由于 Causal Mask 的存在：

```text
h0 = f(BOS)

h1 = f(BOS, I)

h2 = f(BOS, I, love)

h3 = f(BOS, I, love, AI)

h4 = f(BOS, I, love, AI, EOS)
```

所以一次 forward 实际上已经同时计算了这些前缀：

```text
BOS

BOS I

BOS I love

BOS I love AI

BOS I love AI EOS
```

---

<a id="origin-1405"></a>
## 19. 一个序列样本里其实包含多个 token-level 训练目标

Dataset 层面看：

```text
[BOS, I, love, AI, EOS]
```

只是：

```text
1 条 sequence-level sample
```

但是在语言模型的 Loss 层面，它包含多个监督目标：

```text
BOS             → I

BOS I           → love

BOS I love      → AI

BOS I love AI   → EOS
```

所以需要区分两个概念：

<a id="origin-1433"></a>
### 19.1 Sequence-level sample

Dataset 里的一整条序列：

```text
[BOS, I, love, AI, EOS]
```

这是 1 条样本。

<a id="origin-1443"></a>
### 19.2 Token-level prediction target

序列中每个位置产生的预测任务：

```text
BOS             → I
BOS I           → love
BOS I love      → AI
BOS I love AI   → EOS
```

这里实际上有 4 个训练目标。

因此：

> **1 条序列样本，不等于只有 1 个预测任务。**

---

<a id="origin-1462"></a>
## 20. 为什么 Causal Mask 能让一个序列等价于多个前缀样本？

假设输入：

```text
BOS    I    love    AI    EOS
```

Causal Mask 是一个下三角结构：

```text
             BOS     I     love     AI     EOS

BOS           ✓

I             ✓      ✓

love          ✓      ✓       ✓

AI            ✓      ✓       ✓      ✓

EOS           ✓      ✓       ✓      ✓       ✓
```

因此，在同一次 forward 里：

```text
位置 0 只能看到：

BOS
```

```text
位置 1 可以看到：

BOS I
```

```text
位置 2 可以看到：

BOS I love
```

```text
位置 3 可以看到：

BOS I love AI
```

```text
位置 4 可以看到：

BOS I love AI EOS
```

所以这一个序列，天然就在一次矩阵计算中“模拟”出了多个不同长度的前缀。

---

<a id="origin-1522"></a>
## 21. lm_head 会给每个位置都产生一次词表预测

经过 Transformer 得到：

```text
h0
h1
h2
h3
h4
```

再经过：

```python
logits = self.lm_head(hidden_states)
```

得到：

```text
logits0
logits1
logits2
logits3
logits4
```

分别可以理解成：

```text
logits0：

根据 BOS
预测下一个 token
```

```text
logits1：

根据 BOS I
预测下一个 token
```

```text
logits2：

根据 BOS I love
预测下一个 token
```

```text
logits3：

根据 BOS I love AI
预测下一个 token
```

因此：

```text
一次 forward
```

不是产生：

```text
1 个 prediction
```

而是产生：

```text
每一个位置各 1 个 prediction
```

---

<a id="origin-1600"></a>
## 22. labels 错位后，多个预测任务会自动对齐

原始：

```text
input_ids:

[BOS, I, love, AI, EOS]
```

Dataset 中：

```text
labels:

[BOS, I, love, AI, EOS]
```

模型 forward 后：

```text
logits:

[logits0, logits1, logits2, logits3, logits4]
```

MiniMind 中：

```python
x = logits[..., :-1, :]
y = labels[..., 1:]
```

于是：

```text
x：

logits0
logits1
logits2
logits3
```

而：

```text
y：

I
love
AI
EOS
```

形成：

```text
logits0  → I

logits1  → love

logits2  → AI

logits3  → EOS
```

结合每个 logits 的上下文：

```text
f(BOS)             → I

f(BOS, I)          → love

f(BOS, I, love)    → AI

f(BOS, I, love,AI) → EOS
```

所以一条序列一次 forward，就同时完成了四个 next-token prediction。

---

<a id="origin-1683"></a>
## 23. CrossEntropyLoss 其实会同时计算多个位置的 Loss

假设四个位置的正确答案分别是：

```text
I
love
AI
EOS
```

那么实际上会有多个 token loss：

\[
L_0=-\log P(I\mid BOS)
\]

\[
L_1=-\log P(love\mid BOS,I)
\]

\[
L_2=-\log P(AI\mid BOS,I,love)
\]

\[
L_3=-\log P(EOS\mid BOS,I,love,AI)
\]

最终总 Loss 通常对这些有效位置进行平均或聚合：

\[
L
=
\frac{L_0+L_1+L_2+L_3}{4}
\]

例如：

```text
BOS → I
loss = 0.3

BOS I → love
loss = 0.8

BOS I love → AI
loss = 0.2

BOS I love AI → EOS
loss = 0.5
```

最终：

\[
Loss
=
\frac{0.3+0.8+0.2+0.5}{4}
=
0.45
\]

然后：

```python
loss.backward()
```

这几个位置产生的梯度会一起反向传播。

所以：

> **一次 forward 虽然只返回一个总 loss，但这个 loss 内部实际上综合了序列中多个 token 位置的训练误差。**

---

<a id="origin-1760"></a>
## 24. 从代码角度看，为什么 CrossEntropyLoss 可以一次处理所有位置？

假设：

```python
x.shape = [B, T-1, V]
```

其中：

```text
B = batch size
T = sequence length
V = vocab size
```

而：

```python
y.shape = [B, T-1]
```

MiniMind 中：

```python
loss = F.cross_entropy(
    x.view(-1, x.size(-1)),
    y.view(-1),
    ignore_index=-100
)
```

会把：

```text
[B, T-1, V]
```

展开成：

```text
[B × (T-1), V]
```

同时把：

```text
[B, T-1]
```

展开成：

```text
[B × (T-1)]
```

也就是说：

> batch 中所有样本、所有 token 位置，都被一次性送进 CrossEntropyLoss。

例如：

```text
batch_size = 2
sequence_length = 5
```

每条序列有：

```text
4 个 next-token target
```

两条序列总共：

```text
2 × 4 = 8
```

个 token-level prediction target。

CrossEntropyLoss 会一次性计算这 8 个位置的损失。

---

<a id="origin-1845"></a>
## 25. 一条长度为 T 的序列能提供多少训练目标？

假设序列长度为：

\[
T
\]

例如：

```text
[BOS, I, love, AI, EOS]
```

长度：

```text
T = 5
```

通常可以产生：

\[
T-1
\]

个 next-token prediction target。

所以：

```text
T = 5
```

产生：

```text
4 个训练目标
```

即：

```text
位置 0 → 预测位置 1

位置 1 → 预测位置 2

位置 2 → 预测位置 3

位置 3 → 预测位置 4
```

---

<a id="origin-1899"></a>
## 26. 对于长序列，这个效果更加明显

假设一个预训练样本长度是：

```text
2048 tokens
```

它并不是：

```text
1 条样本只训练 1 次预测
```

而是大约可以提供：

```text
2047 个 next-token prediction targets
```

即：

```text
token 0
→ token 1

token 0~1
→ token 2

token 0~2
→ token 3

...

token 0~2046
→ token 2047
```

因此一个长序列本身就包含大量监督信号。

---

<a id="origin-1941"></a>
## 27. 为什么说 LLM 训练的数据量通常用 Token 数量衡量？

假设有：

```text
100 万条文本
```

如果每条文本平均：

```text
1000 tokens
```

那么虽然 Dataset 中只有：

```text
100 万条 sequence sample
```

但是实际可以产生接近：

```text
10 亿个 token-level prediction targets
```

所以大语言模型预训练通常更加关注：

```text
训练了多少 token
```

而不仅仅是：

```text
训练了多少条文本
```

因为真正产生监督信号的是序列中的 token 位置。

---

<a id="origin-1983"></a>
## 28. 传统做法和 Transformer 做法对比

<a id="origin-1985"></a>
### 28.1 传统显式展开

```text
样本 1：
[BOS]
→ I

样本 2：
[BOS, I]
→ love

样本 3：
[BOS, I, love]
→ AI

样本 4：
[BOS, I, love, AI]
→ EOS
```

模型可能需要多次 forward：

```text
Forward 1

Forward 2

Forward 3

Forward 4
```

而且有大量重复前缀计算。

---

<a id="origin-2021"></a>
### 28.2 Transformer 做法

只输入：

```text
[BOS, I, love, AI, EOS]
```

执行：

```text
1 次 forward
```

借助：

```text
Causal Self-Attention
+
Causal Mask
+
每个位置都输出 logits
```

同时得到：

```text
BOS             → I

BOS I           → love

BOS I love      → AI

BOS I love AI   → EOS
```

因此：

> **Transformer 并不是减少了训练目标，而是把原本多个前缀样本的训练目标，打包到了同一个序列和同一次 forward 中并行完成。**

---

<a id="origin-2063"></a>
## 29. 整个过程一张图理解

```text
Dataset 中只有 1 条序列：

[BOS, I, love, AI, EOS]

               ↓

        Transformer
    Causal Self-Attention

               ↓

同时得到不同位置的上下文表示：

h0 = f(BOS)

h1 = f(BOS, I)

h2 = f(BOS, I, love)

h3 = f(BOS, I, love, AI)

h4 = f(BOS, I, love, AI, EOS)

               ↓
            lm_head
               ↓

logits0
logits1
logits2
logits3
logits4

               ↓
         labels 错位一位
               ↓

logits0 → I

logits1 → love

logits2 → AI

logits3 → EOS

               ↓

分别产生 token-level loss：

L0
L1
L2
L3

               ↓

       CrossEntropyLoss

               ↓

      聚合成一个总 Loss

               ↓

          loss.backward()
```

---

<a id="origin-2135"></a>
## 30. 最后总结

需要同时理解两个层次。

<a id="origin-2139"></a>
### 30.1 第一层：为什么 `love` 位置能根据 `BOS I love` 预测 AI？

因为：

> `love` 位置经过 Causal Self-Attention 后，它的 hidden state 已经融合了 `BOS`、`I`、`love` 的上下文信息。

所以：

```text
logits[2]
```

表示的不是：

\[
P(AI\mid love)
\]

而是：

\[
P(AI\mid BOS,I,love)
\]

---

<a id="origin-2165"></a>
### 30.2 第二层：为什么一条序列可以完成多条训练样本的工作？

因为一次 forward 会同时计算：

```text
f(BOS)

f(BOS, I)

f(BOS, I, love)

f(BOS, I, love, AI)
```

然后每一个位置都产生自己的 logits。

因此：

```text
[BOS, I, love, AI, EOS]
```

这一条 sequence-level sample，可以同时产生：

```text
BOS             → I
BOS I           → love
BOS I love      → AI
BOS I love AI   → EOS
```

四个 token-level prediction target。

所以最核心的一句话是：

> **Transformer 把“多个不同长度前缀分别训练”的传统做法，通过 Causal Mask 和并行 Self-Attention，合并成“一条完整序列一次 forward，同时训练所有位置”。**

这正是 Decoder-only 大语言模型预训练的核心机制之一。

---

<a id="origin-2206"></a>
## 31. Transformer 为什么可以并行训练：从逐 Token 训练到前缀共享

<a id="origin-2208"></a>
## 32. 先看一个最简单的训练句子

假设训练语料中有一句：

```text
<BOS> I love AI very much
```

对于自回归语言模型来说，它真正需要学习的是：

```text
<BOS>                  → I
<BOS> I                → love
<BOS> I love           → AI
<BOS> I love AI        → very
<BOS> I love AI very   → much
```

也就是说，一个长度为 5 的目标序列，本质上可以看成产生了 5 个训练任务。

---

<a id="origin-2230"></a>
## 33. 最直观的训练方法：一个任务一个任务地训练

最朴素的办法当然可以写成：

```text
样本1：
<BOS>
→ 预测 I

样本2：
<BOS> I
→ 预测 love

样本3：
<BOS> I love
→ 预测 AI

样本4：
<BOS> I love AI
→ 预测 very

样本5：
<BOS> I love AI very
→ 预测 much
```

这样做在逻辑上完全没有问题。

例如：

```text
<BOS> I love
```

送进 Transformer：

```text
<BOS> I love
      ↓
Transformer
      ↓
预测下一个 Token：AI
```

然后下一次再送：

```text
<BOS> I love AI
```

得到：

```text
预测下一个 Token：very
```

这样一个前缀一个前缀训练，理论上同样能够训练语言模型。

---

<a id="origin-2290"></a>
## 34. 但这里存在大量重复计算

仔细观察这几个训练样本：

```text
样本1：<BOS>

样本2：<BOS> I

样本3：<BOS> I love

样本4：<BOS> I love AI

样本5：<BOS> I love AI very
```

它们并不是五个互不相关的样本。

而是：

```text
<BOS>

<BOS> I

<BOS> I love

<BOS> I love AI

<BOS> I love AI very
```

每一个后面的样本都把前面的样本完整包含了进去。

例如：

```text
<BOS>
```

出现了 5 次。

```text
<BOS> I
```

出现在后面 4 个样本中。

```text
<BOS> I love
```

出现在后面 3 个样本中。

因此这里真正大量重复的是：

> 历史前缀对应的计算。

---

<a id="origin-2350"></a>
## 35. 第一层中到底重复了什么？

例如比较两个样本：

```text
样本3：
<BOS> I love
```

和：

```text
样本4：
<BOS> I love AI
```

在 Transformer 第一层中，都需要首先计算：

```math
Q = XW_Q
```

```math
K = XW_K
```

```math
V = XW_V
```

所以对于：

```text
<BOS> I love
```

需要计算：

```math
Q_{\text{BOS}},K_{\text{BOS}},V_{\text{BOS}}
```

```math
Q_I,K_I,V_I
```

```math
Q_{\text{love}},K_{\text{love}},V_{\text{love}}
```

然后计算 Attention Score。

例如：

```math
Q_IK_{\text{BOS}}^T
```

以及：

```math
Q_{\text{love}}K_{\text{BOS}}^T
```

```math
Q_{\text{love}}K_I^T
```

等等。

---

但是下一次训练：

```text
<BOS> I love AI
```

时，前面的：

```text
<BOS> I love
```

又出现了一遍。

于是：

```math
Q_{\text{BOS}},K_{\text{BOS}},V_{\text{BOS}}
```

又算一次。

```math
Q_I,K_I,V_I
```

又算一次。

```math
Q_{\text{love}},K_{\text{love}},V_{\text{love}}
```

也又算一次。

甚至前面的 Attention Score 也再次计算。

所以第一层已经存在大量重复。

---

<a id="origin-2462"></a>
## 36. Attention Score 矩阵也能非常直观地看到重复

假设当前只有：

```text
BOS I love
```

Attention Score 矩阵可以写成：

```math
\begin{bmatrix}
Q_BK_B^T & -\infty & -\infty
\\
Q_IK_B^T & Q_IK_I^T & -\infty
\\
Q_LK_B^T & Q_LK_I^T & Q_LK_L^T
\end{bmatrix}
```

这里为了简洁：

```text
B = BOS
L = love
```

---

下一次再输入：

```text
BOS I love AI
```

Attention Score 变成：

```math
\begin{bmatrix}
Q_BK_B^T & -\infty & -\infty & -\infty
\\
Q_IK_B^T & Q_IK_I^T & -\infty & -\infty
\\
Q_LK_B^T & Q_LK_I^T & Q_LK_L^T & -\infty
\\
Q_AK_B^T & Q_AK_I^T & Q_AK_L^T & Q_AK_A^T
\end{bmatrix}
```

注意左上角这一块：

```math
\begin{bmatrix}
Q_BK_B^T & -\infty & -\infty
\\
Q_IK_B^T & Q_IK_I^T & -\infty
\\
Q_LK_B^T & Q_LK_I^T & Q_LK_L^T
\end{bmatrix}
```

和上一次一模一样。

真正新增的主要是最后一行：

```math
[
Q_AK_B^T,\,
Q_AK_I^T,\,
Q_AK_L^T,\,
Q_AK_A^T
]
```

所以如果每个前缀单独跑一遍 Transformer，左上角历史部分就会不停重复计算。

---

<a id="origin-2540"></a>
## 37. 为什么前面的结果不会因为后面的 Token 出现而改变？

关键就是：

<a id="origin-2544"></a>
## 38. Causal Mask

自回归 Transformer 规定：

> 一个位置只能看到自己以及自己前面的 Token，不能看到未来 Token。

例如：

```text
             BOS    I    love    AI
BOS           ✓
I             ✓     ✓
love          ✓     ✓      ✓
AI            ✓     ✓      ✓      ✓
```

因此当：

```text
AI
```

被加到后面以后：

```text
BOS
I
love
```

这些历史 Token 根本看不到 AI。

所以它们的计算结果不会因为 AI 的加入而发生变化。

例如：

```text
输入1：
BOS I love
```

和：

```text
输入2：
BOS I love AI
```

在同一组模型参数下：

```math
H_{\text{love}}^{(1)}
```

是相同的。

因为 `love` 在第一层只能看到：

```text
BOS I love
```

它根本不知道后面已经多了一个：

```text
AI
```

。

这就是一个非常重要的性质：

```math
\boxed{
\text{未来 Token 不会改变历史 Token 的 hidden state}
}
```

---

<a id="origin-2624"></a>
## 39. 后面层是不是也会重复？

会。

而且这里重复的不再只是原始 Token 的 Q/K/V，而是：

> 历史 Token 在整个 Transformer Block 中的全部中间计算结果。

例如：

```text
样本3：
<BOS> I love
```

第一层算完以后得到：

```math
H_{\text{BOS}}^{(1)}
```

```math
H_I^{(1)}
```

```math
H_{\text{love}}^{(1)}
```

---

接下来输入：

```text
样本4：
<BOS> I love AI
```

由于 Causal Mask：

```math
H_{\text{BOS}}^{(1)}
```

不变，

```math
H_I^{(1)}
```

不变，

```math
H_{\text{love}}^{(1)}
```

也不变。

只是新增：

```math
H_{\text{AI}}^{(1)}
```

因此：

```text
样本3，第1层：

H_BOS^1   H_I^1   H_love^1


样本4，第1层：

H_BOS^1   H_I^1   H_love^1   H_AI^1
^^^^^^^^^^^^^^^^^^^^^^^^^^^
          重复
```

---

<a id="origin-2705"></a>
## 40. 到第二层，重复的是什么？

第二层的输入已经不是原始的：

```text
BOS
I
love
```

而是：

```math
H_{\text{BOS}}^{(1)}
```

```math
H_I^{(1)}
```

```math
H_{\text{love}}^{(1)}
```

。

第二层又会执行：

```text
H^(1)
 ↓
RMSNorm
 ↓
Q / K / V 投影
 ↓
Attention
 ↓
W_O
 ↓
Residual
 ↓
RMSNorm
 ↓
FFN
 ↓
Residual
 ↓
H^(2)
```

例如：

```math
H_I^{(1)}
\rightarrow
Q_I^{(2)},K_I^{(2)},V_I^{(2)}
```

然后继续参与第二层 Attention。

---

但因为样本3和样本4中的：

```math
H_I^{(1)}
```

完全一样，

所以第二层中的：

```math
Q_I^{(2)}
```

```math
K_I^{(2)}
```

```math
V_I^{(2)}
```

也完全一样。

Attention 结果一样。

FFN 结果一样。

因此：

```math
H_I^{(2)}
```

还是一样。

---

所以：

```text
样本3，第2层：

H_BOS^2   H_I^2   H_love^2


样本4，第2层：

H_BOS^2   H_I^2   H_love^2   H_AI^2
^^^^^^^^^^^^^^^^^^^^^^^^^^^
          重复
```

---

<a id="origin-2822"></a>
## 41. 第三层、第四层直到最后一层也是一样

由于第二层历史 Token 的 hidden state 没变：

```math
H_{\text{BOS}}^{(2)}
```

```math
H_I^{(2)}
```

```math
H_{\text{love}}^{(2)}
```

进入第三层以后当然也不会变。

所以：

```text
第1层：

样本3：
H_BOS^1  H_I^1  H_love^1

样本4：
H_BOS^1  H_I^1  H_love^1  H_AI^1
^^^^^^^^^^^^^^^^^^^^^^^^^^
重复
```

```text
第2层：

样本3：
H_BOS^2  H_I^2  H_love^2

样本4：
H_BOS^2  H_I^2  H_love^2  H_AI^2
^^^^^^^^^^^^^^^^^^^^^^^^^^
重复
```

```text
第3层：

样本3：
H_BOS^3  H_I^3  H_love^3

样本4：
H_BOS^3  H_I^3  H_love^3  H_AI^3
^^^^^^^^^^^^^^^^^^^^^^^^^^
重复
```

一直到：

```text
Layer 32
```

都是这样。

---

<a id="origin-2888"></a>
## 42. 所以后面层到底重复了什么？

可以把一个标准 Transformer Block 简化成：

```text
hidden state
    ↓
RMSNorm
    ↓
Q / K / V Projection
    ↓
Attention
    ↓
W_O
    ↓
Residual
    ↓
RMSNorm
    ↓
FFN
    ↓
Residual
    ↓
下一层 hidden state
```

如果你分别运行：

```text
BOS I love
```

和：

```text
BOS I love AI
```

那么历史 Token：

```text
BOS
I
love
```

对应的：

```text
RMSNorm

Q

K

V

Attention

W_O

Residual

FFN

最终 hidden state
```

全部会重新计算一次。

而且不是只重复一层。

如果有 32 层，那么历史 Token 在：

```text
Layer 1
Layer 2
Layer 3
...
Layer 32
```

中的整条计算链都会重新跑一遍。

---

<a id="origin-2974"></a>
## 43. 可以把这种浪费画成这样

如果逐个前缀训练：

```text
样本1：

BOS
 └── Layer1 → Layer2 → Layer3 → ... → Layer32
```

接下来：

```text
样本2：

BOS ── Layer1 → Layer2 → ... → Layer32
 ↑
 这一整条历史路径重新算

I   ── Layer1 → Layer2 → ... → Layer32
```

再下一个：

```text
样本3：

BOS  ─────────────────────────→ Layer32
 ↑
 又重新算

I    ─────────────────────────→ Layer32
 ↑
 又重新算

love ─────────────────────────→ Layer32
```

再下一个：

```text
样本4：

BOS  ─────────────────────────→ Layer32
 ↑
 又重新算

I    ─────────────────────────→ Layer32
 ↑
 又重新算

love ─────────────────────────→ Layer32
 ↑
 又重新算

AI   ─────────────────────────→ Layer32
```

所以越往后：

```text
历史前缀越来越长
↓
被重复计算的内容越来越多
```

---

<a id="origin-3043"></a>
## 44. Transformer 怎么解决这个问题？

Transformer 训练的时候并不真的分别构造：

```text
BOS

BOS I

BOS I love

BOS I love AI

BOS I love AI very
```

而是直接一次输入：

```text
BOS I love AI very
```

然后利用 Causal Mask：

```text
BOS位置：

只能看到：
BOS
```

```text
I位置：

只能看到：
BOS I
```

```text
love位置：

只能看到：
BOS I love
```

```text
AI位置：

只能看到：
BOS I love AI
```

```text
very位置：

只能看到：
BOS I love AI very
```

因此一次 forward 就同时模拟出了所有前缀任务。

---

<a id="origin-3106"></a>
## 45. 一个完整序列实际上同时承担了多个训练样本

输入：

```text
<BOS> I love AI very
```

目标：

```text
I love AI very much
```

可以对齐成：

```text
输入：
<BOS>    I      love      AI      very
  │      │        │        │        │
  ↓      ↓        ↓        ↓        ↓
预测：
 I      love      AI      very     much
```

因此一个输入序列内部实际上同时完成：

```text
<BOS>
→ I
```

```text
<BOS> I
→ love
```

```text
<BOS> I love
→ AI
```

```text
<BOS> I love AI
→ very
```

```text
<BOS> I love AI very
→ much
```

这就是所谓：

> 一条序列，一次 forward，同时产生多个 next-token prediction。

---

<a id="origin-3164"></a>
## 46. 从 Attention 矩阵来看，实际上就是“一行一个训练任务”

完整 Attention Score：

```math
\begin{bmatrix}
Q_1K_1^T
&
-\infty
&
-\infty
&
-\infty
&
-\infty
\\
Q_2K_1^T
&
Q_2K_2^T
&
-\infty
&
-\infty
&
-\infty
\\
Q_3K_1^T
&
Q_3K_2^T
&
Q_3K_3^T
&
-\infty
&
-\infty
\\
Q_4K_1^T
&
Q_4K_2^T
&
Q_4K_3^T
&
Q_4K_4^T
&
-\infty
\\
Q_5K_1^T
&
Q_5K_2^T
&
Q_5K_3^T
&
Q_5K_4^T
&
Q_5K_5^T
\end{bmatrix}
```

可以理解成：

```text
第1行：
对应长度为1的前缀

第2行：
对应长度为2的前缀

第3行：
对应长度为3的前缀

第4行：
对应长度为4的前缀

第5行：
对应长度为5的前缀
```

所以：

> 一个 Attention 矩阵已经同时包含了所有前缀任务所需要的 Attention 结果。

---

<a id="origin-3247"></a>
## 47. 那如果真的坚持“一个 Token 一个 Token 训练”，效果会不会一样？

这里一定要区分两种情况。

---

<a id="origin-3253"></a>
## 48. 情况一：逐 Token / 逐前缀计算，但是不立即更新参数

例如：

```text
样本1：
<BOS> → I
```

计算：

```math
L_1
```

反向传播得到：

```math
g_1
```

但暂时不更新参数。

---

然后：

```text
样本2：
<BOS> I → love
```

得到：

```math
L_2
```

以及：

```math
g_2
```

仍然不更新。

---

一直到：

```math
g_1,g_2,g_3,g_4,g_5
```

全部算完。

最后统一：

```math
g
=
g_1+g_2+g_3+g_4+g_5
```

然后才：

```python
optimizer.step()
```

。

---

而并行 Transformer 是直接得到：

```math
L
=
L_1+L_2+L_3+L_4+L_5
```

再做：

```math
\nabla_\theta L
```

由于梯度具有线性性质：

```math
\nabla_\theta
(
L_1+L_2+L_3+L_4+L_5
)
```

等于：

```math
\nabla_\theta L_1
+
\nabla_\theta L_2
+
\nabla_\theta L_3
+
\nabla_\theta L_4
+
\nabla_\theta L_5
```

因此：

```math
\boxed{
\nabla_\theta
\left(
\sum_iL_i
\right)
=
\sum_i
\nabla_\theta L_i
}
```

所以：

> 逐个前缀计算 + 梯度累积 + 最后统一更新

和：

> 一次并行 forward + 一次 backward

在数学目标上基本等价。

---

<a id="origin-3390"></a>
## 49. 为什么只是“基本等价”？

真实代码中可能存在一些很小的实现差异，例如：

```text
Dropout 随机性

浮点数加法顺序

FP16 / BF16 舍入误差

混合精度

并行 kernel 的实现差异
```

因此计算机实际跑出来不一定 bit-by-bit 完全相同。

但从优化目标上：

```text
它们是在计算同一个东西。
```

---

<a id="origin-3416"></a>
## 50. 情况二：每算一个 Token 就立即更新参数

如果变成：

```text
<BOS> → I

backward

optimizer.step()
```

然后：

```text
<BOS> I → love

backward

optimizer.step()
```

再：

```text
<BOS> I love → AI

backward

optimizer.step()
```

那么这和并行训练就不一样了。

---

假设初始参数：

```math
\theta_0
```

第一个任务得到：

```math
g_1
=
\nabla_\theta L_1(\theta_0)
```

于是：

```math
\theta_1
=
\theta_0-\eta g_1
```

。

---

第二个任务开始计算的时候，参数已经变成：

```math
\theta_1
```

所以：

```math
g_2
=
\nabla_\theta L_2(\theta_1)
```

而不是：

```math
\nabla_\theta L_2(\theta_0)
```

。

然后：

```math
\theta_2
=
\theta_1-\eta g_2
```

。

整个轨迹：

```text
θ0
 ↓ L1
θ1
 ↓ L2
θ2
 ↓ L3
θ3
 ↓ L4
...
```

---

而并行训练是：

```text
              L1
              │
              L2
              │
θ0 ───────────L3
              │
              L4
              │
              L5
```

所有：

```math
L_1,L_2,L_3,L_4,L_5
```

都是在同一个：

```math
\theta_0
```

下计算。

最后：

```math
g
=
g_1+g_2+g_3+g_4+g_5
```

一次更新：

```math
\theta_1
=
\theta_0-\eta g
```

。

---

<a id="origin-3574"></a>
## 51. 一个简单例子

假设第一个 token 给出的梯度：

```math
g_1=10
```

第二个 token：

```math
g_2=-8
```

如果一起算：

```math
g=10-8=2
```

最终只是稍微更新一下。

---

但如果第一个 token 算完马上更新：

```math
\theta_1
=
\theta_0-10\eta
```

模型参数已经发生变化。

第二个 token 再计算梯度的时候，原来的：

```math
-8
```

可能已经变成：

```math
-3
```

甚至：

```math
+2
```

。

因为梯度本身也是参数的函数：

```math
g(\theta)
```

参数改变以后，后面的梯度自然也会改变。

所以：

```text
逐 Token 更新
```

和：

```text
所有 Token 一起更新
```

优化轨迹并不相同。

---

<a id="origin-3652"></a>
## 52. 还有一个非常容易混淆的问题：一个 Token 输入是不是只输入当前 Token？

不是。

如果语言模型要预测：

```text
AI
```

正确的输入应该是：

```text
<BOS> I love
```

而不是只输入：

```text
love
```

。

如果变成：

```text
love → AI
```

那模型只能根据 `love` 预测 `AI`。

它就丢掉了：

```text
<BOS> I
```

这些历史上下文。

这已经不是标准的自回归语言模型训练方式了。

---

正确的逐 Token / 逐前缀版本应该是：

```text
<BOS>
→ I
```

然后：

```text
<BOS> I
→ love
```

然后：

```text
<BOS> I love
→ AI
```

然后：

```text
<BOS> I love AI
→ very
```

所以所谓：

> 一个 Token 一个 Token 地训练

更准确地说其实应该叫：

> 一个前缀一个前缀地训练。

---

<a id="origin-3734"></a>
## 53. 为什么这种方法计算成本很高？

假设序列长度是：

```math
L=8192
```

如果真的逐前缀训练，你相当于依次跑：

```text
长度 1

长度 2

长度 3

长度 4

...

长度 8192
```

。

也就是：

```text
[1]

[1 2]

[1 2 3]

[1 2 3 4]

...

[1 ... 8192]
```

大量历史 Token 被一次又一次重新计算。

---

而 Transformer 训练直接：

```text
[1 2 3 ... 8192]
```

一次送进去。

再利用 Causal Mask 自动保证：

```text
位置1只看前1个

位置2只看前2个

位置3只看前3个

...

位置8192只看前8192个
```

于是一次矩阵运算就完成了原来大量前缀任务。

---

<a id="origin-3806"></a>
## 54. 所以“并行训练”的本质是什么？

很多人第一次听：

> Transformer 可以并行训练

容易理解成：

> 每个 Token 彼此独立地训练。

其实不是。

不同 Token 之间依然存在 Attention 依赖关系。

真正的意思是：

> 对于一个已经完整给定的训练序列，我们已经知道所有 Token，所以可以同时计算所有位置的 hidden state 和预测结果。

例如训练的时候我们本来就已经知道：

```text
<BOS> I love AI very much
```

所以没有必要像真正生成文本一样：

```text
先预测 I

再等 I 生成出来

再预测 love

再等 love 生成出来
```

因为训练时答案已经全部知道。

因此可以直接把整句话送入。

---

<a id="origin-3848"></a>
## 55. 训练和推理在这里有一个非常重要的区别

<a id="origin-3850"></a>
### 55.1 训练

整条序列已经知道：

```text
<BOS> I love AI very much
```

所以可以一次输入：

```text
<BOS> I love AI very
```

一次得到：

```text
I love AI very much
```

所有位置的预测。

因此可以并行。

---

<a id="origin-3876"></a>
### 55.2 推理

假设现在只有：

```text
<BOS> I love
```

模型还不知道下一个 Token 是什么。

只能先生成：

```text
AI
```

才能得到：

```text
<BOS> I love AI
```

再生成：

```text
very
```

所以生成过程本身仍然必须：

```text
Token 1
↓
Token 2
↓
Token 3
↓
Token 4
```

串行进行。

---

<a id="origin-3920"></a>
## 56. 这和 KV Cache 又能连起来

前面已经看到：

```text
BOS I love
```

变成：

```text
BOS I love AI
```

以后，Attention Score 中左上角的历史部分其实都没有变化。

真正新增的是：

```math
[
Q_{\text{AI}}K_{\text{BOS}}^T,
Q_{\text{AI}}K_I^T,
Q_{\text{AI}}K_{\text{love}}^T,
Q_{\text{AI}}K_{\text{AI}}^T
]
```

也就是新增这一行。

这就是 KV Cache 的核心直觉之一：

> 历史 Token 的 K 和 V 已经算过了，不需要重新计算。

因此推理时保存：

```text
历史 K
历史 V
```

下一轮只计算新 Token 的：

```text
Q_new
K_new
V_new
```

然后：

```text
Q_new
```

去和所有历史：

```text
K
```

做 Attention。

---

<a id="origin-3984"></a>
## 57. 为什么训练一般不用同样方式逐 Token + KV Cache？

因为训练的时候需要反向传播。

训练希望一次得到：

```text
位置1的 Loss

位置2的 Loss

位置3的 Loss

...

位置L的 Loss
```

然后统一构建计算图进行反向传播。

GPU 最擅长的是大规模矩阵运算。

所以直接：

```text
整段 Sequence
↓
大矩阵乘法
↓
同时得到所有位置
```

通常远比：

```text
Token 1 算一次

Token 2 算一次

Token 3 算一次

...
```

高效。

---

<a id="origin-4032"></a>
## 58. 最后把整个故事串成一句话

假设一句话：

```text
<BOS> I love AI very much
```

传统思路可以把它拆成：

```text
<BOS>
→ I

<BOS> I
→ love

<BOS> I love
→ AI

<BOS> I love AI
→ very

<BOS> I love AI very
→ much
```

但这些训练样本之间存在大量重复：

```text
BOS

BOS I

BOS I love

BOS I love AI
```

这些历史前缀会在：

```text
Embedding

Layer 1
Layer 2
...
Layer N
```

中反复计算。

每一层重复的不只是 Q/K/V，而是：

```text
RMSNorm
Q/K/V
Attention
W_O
Residual
FFN
hidden state
```

整套计算。

由于：

```math
\boxed{
\text{Causal Mask 保证未来 Token 不会影响历史 Token}
}
```

所以这些历史计算本来就是一样的。

于是 Transformer 干脆：

```text
<BOS> I love AI very
```

一次送进去。

利用 Causal Mask：

```text
第1个位置模拟长度1前缀

第2个位置模拟长度2前缀

第3个位置模拟长度3前缀

...

第L个位置模拟长度L前缀
```

从而一次 forward 同时完成所有 next-token prediction。

---

<a id="origin-4134"></a>
## 59. 最核心的三个结论

<a id="origin-4136"></a>
### 59.1 结论一

Transformer 并行训练并没有改变语言模型的训练目标。

它依然在学习：

```text
历史 Token
→
预测下一个 Token
```

。

它只是把大量相互重叠的前缀任务：

```text
BOS

BOS I

BOS I love

BOS I love AI
```

合并到了一次矩阵计算中。

---

<a id="origin-4166"></a>
### 59.2 结论二

所谓“重复计算”，不仅仅是重复 Token。

真正重复的是历史 Token 对应的整套网络计算：

```text
Embedding

Q/K/V

Attention

RMSNorm

FFN

Residual

每一层 hidden state
```

而且会一直重复到 Transformer 的最后一层。

---

<a id="origin-4192"></a>
### 59.3 结论三

如果：

```text
逐前缀计算
+
所有梯度累积
+
最后只更新一次参数
```

那么从数学目标上：

```math
\boxed{
\text{基本等价于并行训练}
}
```

但如果：

```text
每算一个 Token
↓
立刻 optimizer.step()
```

那么参数会在不同 Token 之间发生改变：

```text
θ0 → θ1 → θ2 → θ3 ...
```

这就和标准 Transformer 并行训练不一样了。

---

<a id="origin-4230"></a>
## 60. 一句话总结

> Transformer 的并行训练，本质上是利用 Causal Mask，把原本需要分别计算的多个“逐渐增长的历史前缀”合并到一次矩阵运算中；因为未来 Token 不会影响历史 Token，所以这些前缀中大量重复的 Attention、FFN 和 hidden state 计算没有必要反复进行，而可以一次性并行完成。

---

<a id="origin-4236"></a>
## 61. Transformer 训练中的梯度、前序 Token 与多层 QKV：从单个 Loss 到反向传播

<a id="origin-4238"></a>
## 62. 串行一个样本更新一次，和批量更新，哪个效果更好？

假设一句话产生以下几个训练目标：

```text
<BOS>                  → I
<BOS> I                → love
<BOS> I love           → AI
<BOS> I love AI        → very
<BOS> I love AI very   → much
```

可以有两种训练方式。

---

<a id="origin-4254"></a>
## 63. 方式一：一个样本算完就立即更新一次

例如：

```text
<BOS> → I
↓
计算 Loss
↓
backward
↓
optimizer.step()

<BOS> I → love
↓
计算 Loss
↓
backward
↓
optimizer.step()

<BOS> I love → AI
↓
计算 Loss
↓
backward
↓
optimizer.step()
```

假设初始参数为：

$$
\theta_0
$$

第一个样本产生梯度：

$$
g_1=\nabla_\theta L_1(\theta_0)
$$

然后立刻更新：

$$
\theta_1
=
\theta_0-\eta g_1
$$

第二个样本计算梯度时，参数已经变成：

$$
\theta_1
$$

所以：

$$
g_2
=
\nabla_\theta L_2(\theta_1)
$$

而不是：

$$
\nabla_\theta L_2(\theta_0)
$$

然后继续：

$$
\theta_2
=
\theta_1-\eta g_2
$$

训练轨迹就是：

```text
θ0
↓
样本1
↓
θ1
↓
样本2
↓
θ2
↓
样本3
↓
θ3
```

这种方式相当于非常极端的小 batch，甚至可以近似理解成：

$$
\text{batch size}=1
$$

---

<a id="origin-4358"></a>
## 64. 这种方式有什么问题？

最大的特点是：

> 每次参数更新，只听一个训练目标的意见。

假设几个样本对应的梯度是：

$$
g_1=+10
$$

$$
g_2=-8
$$

$$
g_3=+6
$$

$$
g_4=-5
$$

那么参数更新可能表现为：

```text
往右很多
↓
又往左
↓
又往右
↓
又往左
```

也就是说：

$$
\boxed{\text{梯度噪声比较大}}
$$

更新非常频繁，但训练轨迹也比较抖。

---

<a id="origin-4404"></a>
## 65. 方式二：多个训练目标一起计算，再统一更新

现在更常见的是：

$$
L
=
\frac{
L_1+L_2+L_3+L_4+L_5
}{5}
$$

然后计算：

$$
g
=
\nabla_\theta L
$$

等价于：

$$
g
=
\frac{
g_1+g_2+g_3+g_4+g_5
}{5}
$$

最后统一：

$$
\theta_{\text{new}}
=
\theta-\eta g
$$

例如：

$$
g_1=10
$$

$$
g_2=-8
$$

$$
g_3=6
$$

$$
g_4=-5
$$

$$
g_5=2
$$

则：

$$
g
=
\frac{
10-8+6-5+2
}{5}
=
1
$$

于是模型得到的是一个综合后的更新方向。

可以理解成：

> 不是每一个训练样本单独决定模型往哪里走，而是先综合一批训练信号，再决定整体更新方向。

---

<a id="origin-4484"></a>
## 66. 为什么现代深度学习一般采用 Mini-Batch？

也不能简单说：

> Batch 越大越好。

如果整个训练集只算一次平均梯度，然后才更新一次：

```text
整个训练集
↓
一个巨大 Loss
↓
一次 backward
↓
更新一次
```

那么更新频率会太低。

因此实际采用的是：

$$
\boxed{\text{Mini-Batch}}
$$

也就是：

```text
一小批数据
↓
计算平均 Loss
↓
backward
↓
更新一次

下一小批数据
↓
计算平均 Loss
↓
backward
↓
再更新一次
```

这是以下几个因素之间的平衡：

$$
\boxed{
\text{梯度稳定性}
+
\text{参数更新频率}
+
\text{GPU计算效率}
}
$$

---

<a id="origin-4544"></a>
## 67. 对 Transformer 来说，还要同时考虑 Token 级别的并行

例如一次 batch 中有：

```text
64 条 Sequence
```

每条：

```text
2048 Tokens
```

那么一次参数更新可能综合：

$$
64\times2048
=
131072
$$

个 token 位置产生的训练信号。

这些梯度统一汇总后，再进行一次：

```python
optimizer.step()
```

所以现代 Transformer 通常不会：

```text
一个 Token
→ 更新一次
```

而是：

```text
大量 Token
→ 一起产生 Loss
→ 统一 backward
→ 更新一次
```

---

<a id="origin-4592"></a>
## 68. 一个很关键的问题：只有最后一个标签，前面的 Token 还会不会参与训练？

假设现在不考虑并行训练，而是单独训练一个前缀：

```text
输入：

<BOS> I love

标签：

AI
```

这里只有一个标签：

```text
AI
```

也就是说真正直接产生监督 Loss 的，是最后一个位置：

```text
love → AI
```

那么会不会只有 `love` 被训练？

不是。

---

<a id="origin-4624"></a>
## 69. 前两个 Token 虽然没有直接标签，但参与了最后位置的计算

假设三个位置分别记为：

$$
x_1,x_2,x_3
$$

对应：

```text
x1 = BOS
x2 = I
x3 = love
```

最后一个位置要预测：

```text
AI
```

那么它首先通过 Attention 使用前面三个 Token。

例如：

$$
q_3
$$

去和：

$$
k_1,k_2,k_3
$$

计算 Attention Score：

$$
s_{31}
=
q_3k_1^T
$$

$$
s_{32}
=
q_3k_2^T
$$

$$
s_{33}
=
q_3k_3^T
$$

经过 Softmax：

$$
[
\alpha_{31},
\alpha_{32},
\alpha_{33}
]
=
\operatorname{softmax}
(
[s_{31},s_{32},s_{33}]
)
$$

假设：

$$
[
\alpha_{31},
\alpha_{32},
\alpha_{33}
]
=
[
0.2,0.5,0.3
]
$$

则第三个位置的 Attention 输出：

$$
o_3
=
0.2v_1
+
0.5v_2
+
0.3v_3
$$

所以：

$$
o_3
$$

虽然属于第三个位置，但是里面已经使用了：

$$
v_1,v_2,v_3
$$

三个位置的信息。

---

<a id="origin-4737"></a>
## 70. 最后一个 Loss 实际上依赖于前面的 Token

后续：

$$
o_3
\rightarrow
h_3
\rightarrow
\text{logits}
\rightarrow
P(\text{AI})
\rightarrow
L_3
$$

例如：

$$
L_3
=
-\log P(\text{AI})
$$

因此整个计算图实际上是：

```text
x1 → K1 ─┐
         │
x2 → K2 ─┼──→ Attention
         │
x3 → K3 ─┘       ↑
                  │
x3 → Q3 ─────────┘

x1 → V1 ─┐
x2 → V2 ─┼──→ O3 → logits → P(AI) → L3
x3 → V3 ─┘
```

所以虽然：

```text
BOS
I
```

没有分别对应自己的标签，

但它们产生的：

$$
K_1,V_1,K_2,V_2
$$

被第三个位置使用了。

因此它们仍然位于：

$$
L_3
$$

的计算路径上。

---

<a id="origin-4804"></a>
## 71. 为什么

$$
\frac{\partial L_3}{\partial k_1}
\neq0
$$

？

这其实就是反向传播最基础的思想。

先不要看 Transformer。

假设有：

$$
y=wx
$$

Loss：

$$
L
=
\frac12(y-t)^2
$$

代入：

$$
y=wx
$$

得到：

$$
L
=
\frac12(wx-t)^2
$$

因此：

$$
L
$$

其实是：

$$
x
$$

的函数。

所以当然可以计算：

$$
\frac{\partial L}{\partial x}
$$

。

---

<a id="origin-4869"></a>
## 72. Loss 对某个变量求导，到底是什么意思？

最核心的理解是：

$$
\boxed{
\frac{\partial L}{\partial x}
}
$$

表示：

> 如果 \(x\) 稍微变化一点，最终 Loss 会变化多少。

或者更严格一点：

$$
\frac{\partial L}{\partial x}
$$

描述的是：

> Loss 对变量 \(x\) 的局部敏感程度。

---

<a id="origin-4895"></a>
## 73. 一个最简单的数字例子

假设：

$$
x=2
$$

$$
w=3
$$

则：

$$
y=wx=6
$$

真实答案：

$$
t=10
$$

Loss：

$$
L
=
\frac12(y-t)^2
$$

所以：

$$
L
=
\frac12(6-10)^2
=
8
$$

求：

$$
\frac{\partial L}{\partial x}
$$

利用链式法则：

$$
\frac{\partial L}{\partial x}
=
\frac{\partial L}{\partial y}
\frac{\partial y}{\partial x}
$$

其中：

$$
\frac{\partial L}{\partial y}
=
y-t
$$

而：

$$
\frac{\partial y}{\partial x}
=
w
$$

所以：

$$
\frac{\partial L}{\partial x}
=
(y-t)w
$$

代入：

$$
=
(6-10)\times3
$$

得到：

$$
\boxed{
\frac{\partial L}{\partial x}
=
-12
}
$$

这个 \(-12\) 表示：

> 如果 \(x\) 稍微变大，Loss 会下降。

---

<a id="origin-4999"></a>
## 74. 但是 x 会被 optimizer 直接更新吗？

不一定。

这要区分：

<a id="origin-5005"></a>
### 74.1 梯度传到某个变量

和：

<a id="origin-5009"></a>
### 74.2 optimizer 更新某个变量

这是两回事。

例如：

$$
\frac{\partial L}{\partial x}
$$

虽然存在，

但如果 \(x\) 是普通输入数据，那么 optimizer 并不会执行：

$$
x
\leftarrow
x-\eta
\frac{\partial L}{\partial x}
$$

真正更新的一般是模型参数：

$$
w
$$

例如：

$$
\frac{\partial L}{\partial w}
=
(y-t)x
$$

然后：

$$
w
\leftarrow
w-\eta
\frac{\partial L}{\partial w}
$$

---

<a id="origin-5055"></a>
## 75. 那为什么还需要计算中间变量的梯度？

因为这个变量可能来自更前面的计算。

例如：

$$
x=az
$$

整个计算图：

```text
z
↓
乘以参数 a
↓
x
↓
乘以参数 w
↓
y
↓
Loss
```

虽然：

$$
x
$$

本身不是参数，

但：

$$
\frac{\partial L}{\partial x}
$$

需要继续用于计算：

$$
\frac{\partial L}{\partial a}
$$

因为：

$$
\frac{\partial L}{\partial a}
=
\frac{\partial L}{\partial x}
\frac{\partial x}{\partial a}
$$

这就是：

$$
\boxed{\text{链式法则}}
$$

也是反向传播的核心。

---

<a id="origin-5120"></a>
## 76. 回到 Transformer：为什么 \(k_1\) 的梯度不为 0？

因为存在这条完整路径：

$$
k_1
\rightarrow
s_{31}
\rightarrow
\alpha
\rightarrow
o_3
\rightarrow
L_3
$$

其中：

$$
s_{31}
=
q_3k_1^T
$$

改变：

$$
k_1
$$

就会改变：

$$
s_{31}
$$

而：

$$
s_{31}
$$

变化会改变 Softmax：

$$
\alpha_{31},
\alpha_{32},
\alpha_{33}
$$

进而改变：

$$
o_3
$$

最终改变：

$$
L_3
$$

所以：

$$
L_3
$$

是：

$$
k_1
$$

的函数。

因此一般有：

$$
\boxed{
\frac{\partial L_3}{\partial k_1}
\neq0
}
$$

特殊情况下数值恰好可能是 0，但从计算路径来说，它通常不是恒等于 0。

---

<a id="origin-5209"></a>
## 77. 用链式法则写出来

可以写成：

$$
\frac{\partial L_3}{\partial k_1}
=
\frac{\partial L_3}{\partial o_3}
\cdot
\frac{\partial o_3}{\partial \alpha}
\cdot
\frac{\partial \alpha}{\partial s}
\cdot
\frac{\partial s}{\partial k_1}
$$

你现在不需要把每一项都展开。

真正需要理解的是：

```text
k1
↓
Attention Score
↓
Softmax
↓
Attention输出
↓
预测结果
↓
Loss
```

所以梯度可以沿着这条计算路径返回。

---

<a id="origin-5247"></a>
## 78. V 的梯度更容易理解

因为：

$$
o_3
=
\alpha_{31}v_1
+
\alpha_{32}v_2
+
\alpha_{33}v_3
$$

假设：

$$
\frac{\partial L_3}{\partial o_3}
=
g
$$

那么：

$$
\frac{\partial L_3}{\partial v_1}
=
\alpha_{31}g
$$

同理：

$$
\frac{\partial L_3}{\partial v_2}
=
\alpha_{32}g
$$

$$
\frac{\partial L_3}{\partial v_3}
=
\alpha_{33}g
$$

所以只要：

$$
\alpha_{31}\neq0
$$

通常就有：

$$
\boxed{
\frac{\partial L_3}{\partial v_1}
\neq0
}
$$

这说明：

> 第一个 Token 的 Value 确实被最后一个位置的 Loss 训练到了。

---

<a id="origin-5312"></a>
## 79. 但是 K 和 V 本身不是最终需要更新的参数

例如：

$$
k_1
=
x_1W_K
$$

这里：

$$
k_1
$$

只是一次 forward 中产生的中间结果。

optimizer 不会直接执行：

$$
k_1
\leftarrow
k_1
-
\eta
\frac{\partial L}{\partial k_1}
$$

而是继续利用链式法则：

$$
\frac{\partial L}{\partial W_K}
=
x_1^T
\frac{\partial L}{\partial k_1}
$$

然后真正更新：

$$
\boxed{
W_K
}
$$

即：

$$
W_K
\leftarrow
W_K
-
\eta
\frac{\partial L}{\partial W_K}
$$

---

<a id="origin-5371"></a>
## 80. 同样，V 的梯度最终会更新 \(W_V\)

因为：

$$
v_1=x_1W_V
$$

所以：

$$
\frac{\partial L}{\partial W_V}
$$

会收到这个位置的贡献。

如果有三个 Token：

$$
v_1=x_1W_V
$$

$$
v_2=x_2W_V
$$

$$
v_3=x_3W_V
$$

注意三个 Token 使用的是同一个：

$$
W_V
$$

因此：

$$
\boxed{
\frac{\partial L}{\partial W_V}
=
x_1^T
\frac{\partial L}{\partial v_1}
+
x_2^T
\frac{\partial L}{\partial v_2}
+
x_3^T
\frac{\partial L}{\partial v_3}
}
$$

所以虽然只有一个标签：

```text
AI
```

这个标签产生的 Loss 仍然可能通过多个 Token 的 V，一起影响共享的：

$$
W_V
$$

。

---

<a id="origin-5440"></a>
## 81. 输入长度变化时，\(W_Q,W_K,W_V\) 的维度会变化吗？

不会。

这是另一个非常重要的问题。

假设：

$$
d_{\text{model}}
=
4096
$$

---

<a id="origin-5456"></a>
### 81.1 输入长度为 3

输入：

```text
BOS I love
```

则：

$$
X
\in
\mathbb R^{3\times4096}
$$

而：

$$
W_Q,W_K,W_V
\in
\mathbb R^{4096\times4096}
$$

所以：

$$
Q=XW_Q
$$

得到：

$$
Q
\in
\mathbb R^{3\times4096}
$$

同理：

$$
K,V
\in
\mathbb R^{3\times4096}
$$

---

<a id="origin-5504"></a>
### 81.2 输入长度变成 4

输入：

```text
BOS I love AI
```

那么：

$$
X
\in
\mathbb R^{4\times4096}
$$

但是：

$$
\boxed{
W_Q,W_K,W_V
\text{的维度完全不变}
}
$$

依然：

$$
W_Q,W_K,W_V
\in
\mathbb R^{4096\times4096}
$$

只是：

$$
Q,K,V
\in
\mathbb R^{4\times4096}
$$

所以：

```text
长度3：

X : 3 × 4096
WQ: 4096 × 4096
Q : 3 × 4096
```

长度4：

```text
X : 4 × 4096
WQ: 4096 × 4096
Q : 4 × 4096
```

本质上：

> 序列长度改变的是矩阵的行数，而不是参数矩阵本身的尺寸。

---

<a id="origin-5569"></a>
## 82. 为什么所有 Token 可以共享同一个 \(W_Q,W_K,W_V\)？

因为每个 Token 的 hidden state：

$$
x_i
\in
\mathbb R^{4096}
$$

维度都一样。

所以对每一个位置都可以使用：

$$
q_i
=
x_iW_Q
$$

$$
k_i
=
x_iW_K
$$

$$
v_i
=
x_iW_V
$$

例如：

$$
Q
=
\begin{bmatrix}
q_1\\
q_2\\
q_3
\end{bmatrix}
$$

本质上就是：

$$
\begin{bmatrix}
x_1\\
x_2\\
x_3
\end{bmatrix}
W_Q
$$

也就是：

$$
Q=XW_Q
$$

。

---

<a id="origin-5634"></a>
## 83. 只有最后一个位置产生 Loss 时，前面位置的 Q 会不会收到梯度？

这里要非常细致地区分。

假设只有：

```text
BOS I love
```

预测：

```text
AI
```

那么在这一层中，最终使用的是：

$$
q_3
$$

去查询：

$$
k_1,k_2,k_3
$$

即：

$$
q_3
\rightarrow
k_1,k_2,k_3
$$

所以这一层、仅考虑这个 Loss 时：

$$
q_1
$$

和：

$$
q_2
$$

并没有直接参与：

$$
o_3
$$

的计算。

因此这一条局部路径上：

$$
\frac{\partial L_3}{\partial q_1}
=
0
$$

$$
\frac{\partial L_3}{\partial q_2}
=
0
$$

而：

$$
\frac{\partial L_3}{\partial q_3}
\neq0
$$

同时：

$$
\frac{\partial L_3}{\partial k_1}
\neq0
$$

$$
\frac{\partial L_3}{\partial k_2}
\neq0
$$

$$
\frac{\partial L_3}{\partial k_3}
\neq0
$$

以及：

$$
\frac{\partial L_3}{\partial v_1}
\neq0
$$

$$
\frac{\partial L_3}{\partial v_2}
\neq0
$$

$$
\frac{\partial L_3}{\partial v_3}
\neq0
$$

---

<a id="origin-5747"></a>
## 84. 因此，“前面的 Token 被训练”并不等于“它们所有 Q/K/V 都被这个 Loss 直接用到”

对于最后位置预测：

```text
AI
```

这一层中更准确地说：

```text
前面位置：

K 被使用
V 被使用
Q 不一定被这个最后位置直接使用
```

最后位置：

```text
Q 被使用
K 被使用
V 被使用
```

所以不要简单理解成：

> 前面所有 Q、K、V 都直接参与了这个 Loss。

更准确的是：

> 哪一个变量位于 Loss 的计算路径上，哪一个变量才会从这条路径收到梯度。

---

<a id="origin-5783"></a>
## 85. 对整个 X 求导是什么样？

假设：

$$
X=
\begin{bmatrix}
x_1\\
x_2\\
x_3
\end{bmatrix}
$$

那么：

$$
\frac{\partial L}{\partial X}
=
\begin{bmatrix}
\frac{\partial L}{\partial x_1}\\
\frac{\partial L}{\partial x_2}\\
\frac{\partial L}{\partial x_3}
\end{bmatrix}
$$

如果：

$$
X
\in
\mathbb R^{3\times4096}
$$

那么：

$$
\boxed{
\frac{\partial L}{\partial X}
\in
\mathbb R^{3\times4096}
}
$$

维度与：

$$
X
$$

完全相同。

其中每一个元素：

$$
\frac{\partial L}{\partial X_{ij}}
$$

表示：

> 第 \(i\) 个 Token 的 hidden state 的第 \(j\) 个维度，如果稍微变化一点，Loss 会发生多少变化。

---

<a id="origin-5846"></a>
## 86. X 本身一定会被更新吗？

不一定。

如果这是第一层输入：

$$
x_1
=
E[\text{BOS}]
$$

$$
x_2
=
E[I]
$$

$$
x_3
=
E[\text{love}]
$$

那么真正的参数是：

$$
E
$$

即 Embedding Table。

所以：

$$
\frac{\partial L}{\partial x_i}
$$

最终继续传给：

$$
E
$$

对应的 embedding 参数。

---

如果：

$$
X
$$

是第 10 层的 hidden state，那么：

$$
X^{(10)}
$$

来自：

$$
X^{(9)}
$$

和第 9 层的各种参数。

所以：

$$
\frac{\partial L}{\partial X^{(10)}}
$$

继续向前传播，

最终得到：

$$
\frac{\partial L}{\partial W_Q^{(9)}}
$$

$$
\frac{\partial L}{\partial W_K^{(9)}}
$$

$$
\frac{\partial L}{\partial W_V^{(9)}}
$$

等等。

---

<a id="origin-5940"></a>
## 87. 所以一定要区分：“有梯度”和“被 optimizer 直接更新”

例如：

```text
Q
K
V
Attention Score
Softmax 权重
Hidden State
```

这些中间变量通常都有：

$$
\frac{\partial L}{\partial(\cdot)}
$$

但 optimizer 并不会直接更新这些值。

optimizer 真正更新的是：

```text
Embedding 参数

W_Q

W_K

W_V

W_O

FFN 的参数

RMSNorm 参数

其他可训练参数
```

统一写成：

$$
\theta
\leftarrow
\theta
-
\eta
\nabla_\theta L
$$

。

---

<a id="origin-5996"></a>
## 88. 现在进一步看第二层：Q、K、V 是否已经包含历史 Token 信息？

答案是：

$$
\boxed{\text{是}}
$$

更准确地说：

> 从第二层开始，每个位置的 Q、K、V 都来自上一层已经经过上下文融合的 hidden state。

---

<a id="origin-6010"></a>
## 89. 第一层刚开始时

输入：

```text
BOS   I   love   AI
```

对应：

$$
x_1,x_2,x_3,x_4
$$

第一层：

$$
q_i^{(1)}
=
x_iW_Q^{(1)}
$$

$$
k_i^{(1)}
=
x_iW_K^{(1)}
$$

$$
v_i^{(1)}
=
x_iW_V^{(1)}
$$

这时例如：

$$
q_{\text{love}}^{(1)}
$$

是直接从：

$$
x_{\text{love}}
$$

投影出来的。

它自己还没有通过这一层的 Attention，把：

```text
BOS
I
```

的信息融合进来。

---

<a id="origin-6069"></a>
## 90. 第一层 Attention 之后，hidden state 已经上下文化

对于：

```text
love
```

这一位置：

$$
o_{\text{love}}^{(1)}
=
\alpha_1v_{\text{BOS}}^{(1)}
+
\alpha_2v_I^{(1)}
+
\alpha_3v_{\text{love}}^{(1)}
$$

经过：

```text
Attention
↓
W_O
↓
Residual
↓
RMSNorm
↓
FFN
↓
Residual
```

得到：

$$
h_{\text{love}}^{(1)}
$$

这个：

$$
h_{\text{love}}^{(1)}
$$

已经不只是 `love` 自己的信息。

它已经融合了当前可见上下文：

```text
BOS
I
love
```

。

可以粗略理解为：

```text
love 自己的信息
+
BOS 提供的信息
+
I 提供的信息
+
第一层网络重新加工后的结果
```

---

<a id="origin-6143"></a>
## 91. 第二层的 Q/K/V 都从这个上下文化表示产生

第二层：

$$
q_{\text{love}}^{(2)}
=
h_{\text{love}}^{(1)}
W_Q^{(2)}
$$

$$
k_{\text{love}}^{(2)}
=
h_{\text{love}}^{(1)}
W_K^{(2)}
$$

$$
v_{\text{love}}^{(2)}
=
h_{\text{love}}^{(1)}
W_V^{(2)}
$$

因为：

$$
h_{\text{love}}^{(1)}
$$

本身已经包含历史上下文，

所以：

$$
q_{\text{love}}^{(2)}
$$

$$
k_{\text{love}}^{(2)}
$$

$$
v_{\text{love}}^{(2)}
$$

也已经携带了这些上下文信息。

所以可以说：

$$
\boxed{
\text{第二层开始的 Q/K/V 都是 contextualized 的}
}
$$

---

<a id="origin-6202"></a>
## 92. 每个位置包含多少历史信息？

由于 Causal Mask：

第一个位置：

$$
h_1^{(1)}
$$

只能融合：

```text
BOS
```

。

第二个位置：

$$
h_2^{(1)}
$$

可以融合：

```text
BOS + I
```

。

第三个位置：

$$
h_3^{(1)}
$$

可以融合：

```text
BOS + I + love
```

。

第四个位置：

$$
h_4^{(1)}
$$

可以融合：

```text
BOS + I + love + AI
```

。

因此第二层：

```text
h1¹ → Q1² K1² V1²

h2¹ → Q2² K2² V2²

h3¹ → Q3² K3² V3²

h4¹ → Q4² K4² V4²
```

其中：

```text
Q3² / K3² / V3²
```

都已经建立在：

```text
BOS + I + love
```

的上下文表示之上。

---

<a id="origin-6290"></a>
## 93. 第二层的 K 并不是把之前几个 K 简单拼起来

这个细节非常重要。

不能理解成：

$$
k_{\text{love}}^{(2)}
=
[
k_{\text{BOS}}^{(1)},
k_I^{(1)},
k_{\text{love}}^{(1)}
]
$$

不是这样的。

正确的是：

$$
k_{\text{love}}^{(2)}
=
h_{\text{love}}^{(1)}
W_K^{(2)}
$$

而：

$$
h_{\text{love}}^{(1)}
$$

是第一层 Attention、Residual、FFN 等操作之后得到的：

> 对历史上下文进行融合、压缩、重新编码后的表示。

所以第二层 K 包含历史信息，但不是简单保存历史 K。

---

<a id="origin-6331"></a>
## 94. 越往后层，上下文表示会越来越深

第一层：

```text
Token 原始表示
↓
第一次 Attention
↓
得到第一层上下文化表示
```

第二层：

```text
第一层上下文化表示
↓
生成 Q²/K²/V²
↓
再次 Attention
↓
得到第二层上下文化表示
```

第三层：

```text
第二层上下文化表示
↓
生成 Q³/K³/V³
↓
再次 Attention
↓
得到第三层上下文化表示
```

所以可以理解为：

```text
Layer 1 QKV
主要建立在 Token 初始表示上
↓
第一次上下文融合
↓
Layer 2 QKV
建立在已经融合一次上下文的信息上
↓
再次融合
↓
Layer 3 QKV
建立在更深层上下文表示上
↓
...
```

---

<a id="origin-6388"></a>
## 95. 一个自然语言例子

例如：

```text
I love Apple
```

第一层最开始：

```text
Apple
```

对应的 hidden state 主要表示这个 Token 本身。

第一层 Attention 之后：

```text
Apple
```

这个位置已经看到了：

```text
I love
```

因此：

$$
h_{\text{Apple}}^{(1)}
$$

可以理解为：

> “处在 `I love` 这个上下文中的 Apple”。

第二层：

$$
q_{\text{Apple}}^{(2)}
=
h_{\text{Apple}}^{(1)}W_Q^{(2)}
$$

因此第二层的 Query 已经不是：

> “Apple 这个词需要查询什么？”

而更像是：

> “已经知道前面是 `I love` 的情况下，这个 Apple 位置还需要从上下文中寻找什么？”

同理：

$$
k_{\text{Apple}}^{(2)}
$$

也不是单纯：

> “Apple 能提供什么？”

而是：

> “处在 `I love` 这个上下文中的 Apple，现在能提供什么匹配特征？”

而：

$$
v_{\text{Apple}}^{(2)}
$$

则表示：

> “处在当前上下文里的 Apple，如果被其他位置关注，可以提供什么经过上下文化的信息？”

---

<a id="origin-6468"></a>
## 96. 把 Loss、梯度和多层 QKV 串起来

现在整个故事可以串起来。

假设：

```text
输入：

BOS I love

标签：

AI
```

最后一个位置产生：

$$
L_3
$$

虽然只有：

```text
AI
```

这一个监督标签，

但是：

$$
L_3
$$

依赖：

$$
o_3
$$

而：

$$
o_3
$$

依赖：

$$
q_3
$$

以及：

$$
k_1,k_2,k_3
$$

和：

$$
v_1,v_2,v_3
$$

所以：

$$
L_3
$$

可以通过链式法则对这些变量求导。

例如：

$$
\frac{\partial L_3}{\partial k_1}
\neq0
$$

意味着：

> 如果第一个 Token 的 Key 稍微发生变化，会改变第三个位置的 Attention，最终改变 AI 的预测 Loss。

然后由于：

$$
k_1
=
x_1W_K
$$

梯度继续传到：

$$
W_K
$$

。

---

到了更深层：

$$
x_3
$$

已经不再只是 `love` 的原始信息，

而是上一层产生的：

$$
h_3^{(1)}
$$

它已经融合：

```text
BOS
I
love
```

。

所以第二层：

$$
Q_3^{(2)},K_3^{(2)},V_3^{(2)}
$$

本身已经带有历史上下文。

最终 Loss 再通过第二层、第一层一路向前传播。

---

<a id="origin-6607"></a>
## 97. 最后一定要区分三个概念

<a id="origin-6609"></a>
### 97.1 第一：谁直接有标签？

例如：

```text
BOS I love → AI
```

这里只直接监督：

```text
love 位置预测 AI
```

所以只有一个直接 Loss：

$$
L_3
$$

。

---

<a id="origin-6633"></a>
### 97.2 第二：谁参与了这个 Loss 的计算？

虽然前两个位置没有自己的标签，

但：

$$
K_1,V_1,K_2,V_2
$$

参与了最后位置 Attention，

因此它们处在：

$$
L_3
$$

的计算图上。

于是可以有：

$$
\frac{\partial L_3}{\partial K_1}
\neq0
$$

以及：

$$
\frac{\partial L_3}{\partial V_1}
\neq0
$$

。

---

<a id="origin-6671"></a>
### 97.3 第三：谁最终真正被 optimizer 更新？

不是：

```text
Q
K
V
Hidden State
Attention Score
```

这些临时结果。

真正被更新的是：

$$
W_Q
$$

$$
W_K
$$

$$
W_V
$$

$$
W_O
$$

Embedding 参数、FFN 参数、Norm 参数等。

统一写成：

$$
\boxed{
\theta
\leftarrow
\theta
-
\eta
\frac{\partial L}{\partial\theta}
}
$$

---

<a id="origin-6720"></a>
## 98. 最核心的四句话

<a id="origin-6722"></a>
### 98.1 第一句

$$
\boxed{
\frac{\partial L}{\partial x}
}
$$

表示：

> \(x\) 稍微改变一点，最终 Loss 会改变多少。

---

<a id="origin-6736"></a>
#### 98.1.1 第二句

只要：

$$
x
\rightarrow
\cdots
\rightarrow
L
$$

存在一条计算路径，

那么通常：

$$
\frac{\partial L}{\partial x}
\neq0
$$

。

---

<a id="origin-6761"></a>
#### 98.1.2 第三句

有梯度不代表这个变量本身会被 optimizer 更新。

中间变量的梯度主要负责继续向前传播，最终找到真正的可训练参数：

$$
\theta
$$

。

---

<a id="origin-6775"></a>
#### 98.1.3 第四句

从第二层开始：

$$
Q_i^{(l)},K_i^{(l)},V_i^{(l)}
$$

已经不是单纯由当前 Token 的原始含义产生，而是由上一层已经融合历史上下文的 hidden state 产生。

所以：

$$
\boxed{
\text{越往后的 Transformer 层，Q/K/V 都是在越来越深的上下文表示上继续工作的。}
}
$$

---

<a id="origin-6795"></a>
## 99. 一张总图

```text
输入：

BOS        I        love
 │         │          │
x1        x2         x3
 │         │          │
├→K1,V1   ├→K2,V2    ├→Q3,K3,V3
│          │          │
└──────────┴─────┬────┘
                 ↓
              Attention
                 ↓
                 O3
                 ↓
          contextualized h3
                 ↓
              下一层
                 ↓
          Q3² / K3² / V3²
                 ↓
             Attention
                 ↓
                ...
                 ↓
               logits
                 ↓
             P(AI)
                 ↓
                L3


反向传播：

L3
↑
logits
↑
高层 hidden state
↑
高层 Q/K/V
↑
Attention
↑
低层 hidden state
↑
K1 / V1 / K2 / V2 / Q3 ...
↑
WQ / WK / WV / Embedding / FFN ...
```

所以最终真正应该形成的整体理解是：

> **Loss 虽然可以只产生在最后一个预测位置，但只要前面的 Token 通过 Attention、hidden state 和后续网络参与了这个预测，它们对应的中间变量就处在 Loss 的计算图中。反向传播会沿着这些路径逐层求导，最终把梯度传到共享的 \(W_Q,W_K,W_V\)、Embedding、FFN 等可训练参数上；而从第二层开始，每个位置的 Q/K/V 本身又已经建立在包含历史上下文信息的 hidden state 上。**

如果后面继续往下讲，最自然的下一步就是把 **\(\partial L/\partial K\)、\(\partial L/\partial Q\)、\(\partial L/\partial V\) 三条梯度路径真正完整推一遍**，这样 Attention 的反向传播就彻底闭环了。
