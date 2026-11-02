# Encoder 与 Decoder-only


<a id="origin-3"></a>
## 1. 先区分两个很容易混淆的概念

理解 Transformer 架构时，最重要的是区分：

\[
\boxed{\text{Encoder / Decoder：网络模块名称}}
\]

和：

\[
\boxed{\text{Encoding / Decoding：信息处理过程}}
\]

这两组概念不是一回事。

一个模型可以：

- 没有独立的 Encoder 模块；
- 但仍然存在“把输入转成内部表示”的 Encoding 过程。

同理，一个 Encoder-only 模型最后也可能把内部表示映射成类别或标签，但我们不会因此说它包含 Decoder。

所以：

\[
\boxed{
\text{有 Encoding}
\neq
\text{有 Encoder}
}
\]

以及：

\[
\boxed{
\text{有输出生成}
\neq
\text{一定有 Decoder 模块}
}
\]

---

<a id="origin-48"></a>
## 2. 为什么 Transformer Encoder 可以看到双向信息

<a id="origin-50"></a>
## 3. Encoder 的输入在一开始就是完整给定的

假设输入是：

```text
我 喜欢 吃 苹果
```

对于 Encoder 来说，这四个 token 一开始就已经全部输入模型。

也就是说，Encoder 从一开始就知道：

```text
我      喜欢      吃      苹果
```

它的目标不是预测下一个 token，而是：

> 对整段已经给定的输入建立更好的上下文表示。

因此它没有必要遮挡右边的信息。

---

<a id="origin-74"></a>
## 4. Encoder 的 Self-Attention 不使用 Causal Mask

标准 Self-Attention：

\[
\text{Attention}(Q,K,V)
=
\text{softmax}
\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
\]

对于序列：

```text
我 喜欢 吃 苹果
```

如果长度为 4，那么 \(QK^T\) 会形成一个 \(4\times4\) 的注意力矩阵。

可以理解为：

\[
\begin{bmatrix}
我\to我 & 我\to喜欢 & 我\to吃 & 我\to苹果\\
喜欢\to我 & 喜欢\to喜欢 & 喜欢\to吃 & 喜欢\to苹果\\
吃\to我 & 吃\to喜欢 & 吃\to吃 & 吃\to苹果\\
苹果\to我 & 苹果\to喜欢 & 苹果\to吃 & 苹果\to苹果
\end{bmatrix}
\]

也就是：

```text
            我   喜欢   吃   苹果
我          ✓    ✓    ✓    ✓
喜欢        ✓    ✓    ✓    ✓
吃          ✓    ✓    ✓    ✓
苹果        ✓    ✓    ✓    ✓
```

每一个 token 都可以看到所有其他 token。

因此：

```text
我 ← 喜欢 → 吃 → 苹果
```

“喜欢”既能看左边，也能看右边。

所以我们通常说：

\[
\boxed{
\text{Encoder 使用双向 Self-Attention}
}
\]

---

<a id="origin-136"></a>
## 5. “双向”并不是指模型真的跑两个方向

Transformer Encoder 的“双向”并不是像传统双向 RNN 那样：

```text
→ → → → →
← ← ← ← ←
```

不是：

- 一条网络从左往右；
- 一条网络从右往左。

Transformer 的意思是：

> 在一次 Self-Attention 中，每一个 token 都可以直接 attend 到整段输入中的所有位置。

因此更准确地说：

\[
\boxed{
\text{Bidirectional}
=
\text{每个位置都能访问整段输入}
}
\]

---

<a id="origin-166"></a>
## 6. 为什么 Decoder 不能看到右边

<a id="origin-168"></a>
## 7. Decoder 的核心任务是预测未来

对于 Decoder-only 语言模型，例如 GPT，核心训练目标是：

\[
\boxed{
P(x_t\mid x_1,\ldots,x_{t-1})
}
\]

也就是：

> 根据前面的 token，预测下一个 token。

例如：

```text
我 喜欢 吃 苹果
```

模型学习的是：

```text
我
↓
预测：喜欢
```

然后：

```text
我 喜欢
↓
预测：吃
```

然后：

```text
我 喜欢 吃
↓
预测：苹果
```

如果模型在预测“苹果”之前就能看到“苹果”，那就相当于提前看到了答案。

---

<a id="origin-216"></a>
## 8. 因此 Decoder 必须加 Causal Mask

Decoder 中的 Attention 通常写成：

\[
\text{Attention}(Q,K,V)
=
\text{softmax}
\left(
\frac{QK^T}{\sqrt{d_k}}
+
M
\right)V
\]

其中 \(M\) 是 Causal Mask。

例如：

\[
M=
\begin{bmatrix}
0 & -\infty & -\infty & -\infty\\
0 & 0 & -\infty & -\infty\\
0 & 0 & 0 & -\infty\\
0 & 0 & 0 & 0
\end{bmatrix}
\]

经过 Softmax 后，被加上 \(-\infty\) 的位置注意力概率变成 0。

于是：

```text
            我   喜欢   吃   苹果
我          ✓
喜欢        ✓    ✓
吃          ✓    ✓    ✓
苹果        ✓    ✓    ✓    ✓
```

对应：

\[
\begin{bmatrix}
1&0&0&0\\
1&1&0&0\\
1&1&1&0\\
1&1&1&1
\end{bmatrix}
\]

所以：

\[
\boxed{
\text{Decoder 只能看到自己和左边，不能看到右边未来 token}
}
\]

---

<a id="origin-278"></a>
## 9. Encoder 和 Decoder 的注意力差异

<a id="origin-280"></a>
## 10. 用矩阵对比最直观

<a id="origin-282"></a>
### 10.1 Encoder

```text
████
████
████
████
```

每个位置都可以访问所有位置。

<a id="origin-293"></a>
#### 10.1.1 Decoder

```text
█
██
███
████
```

只能看到左边和自己。

所以：

\[
\boxed{
\text{Encoder：全局 Self-Attention}
}
\]

\[
\boxed{
\text{Decoder：Causal Self-Attention}
}
\]

---

<a id="origin-320"></a>
## 11. 为什么大语言模型经常采用 Decoder-only

<a id="origin-322"></a>
## 12. 大语言模型可以把大量任务统一成 Next Token Prediction

Decoder-only 架构最强的一点是：

> 很多任务都可以转化为“给定前文，继续生成”。

例如：

<a id="origin-330"></a>
### 12.1 问答

```text
Q: 中国首都是哪里？
A:
```

模型生成：

```text
北京
```

<a id="origin-343"></a>
#### 12.1.1 翻译

```text
Translate into Chinese:
I love China.
Answer:
```

模型继续生成：

```text
我爱中国。
```

<a id="origin-357"></a>
#### 12.1.2 分类

```text
这部电影太好看了。
情感：
```

模型生成：

```text
正面
```

<a id="origin-370"></a>
#### 12.1.3 代码生成

```text
写一个 Python 快速排序：
```

模型继续生成：

```python
def quicksort(...):
```

因此可以统一成：

\[
\boxed{
P(x_t\mid x_{<t})
}
\]

训练目标也统一为：

\[
\boxed{
\mathcal L
=
-\sum_t \log P(x_t\mid x_{<t})
}
\]

这让一个模型可以统一处理大量任务。

---

<a id="origin-404"></a>
## 13. Decoder-only 的“编码过程”在哪里

<a id="origin-406"></a>
## 14. Decoder-only 没有独立 Encoder，但仍然要形成内部表示

假设输入：

```text
中国 的 首都 是 哪里 ？
```

首先 Token 会变成 Embedding：

```text
中国 → e1
的   → e2
首都 → e3
是   → e4
哪里 → e5
？   → e6
```

然后加上位置信息：

\[
z_i^{(0)} = e_i + p_i
\]

接着进入第一层 Transformer Block：

\[
z^{(1)}
=
\text{Block}_1(z^{(0)})
\]

第二层：

\[
z^{(2)}
=
\text{Block}_2(z^{(1)})
\]

一直到第 \(L\) 层：

\[
z^{(L)}
=
\text{Block}_L(z^{(L-1)})
\]

最终得到：

```text
中国 → h1
的   → h2
首都 → h3
是   → h4
哪里 → h5
？   → h6
```

这里的 \(h_i\) 已经不是原始词向量。

而是：

\[
\boxed{
\text{Contextual Hidden Representation}
}
\]

也就是上下文化语义表示。

---

<a id="origin-480"></a>
## 15. 这就是 Decoder-only 里的 Encoding

Decoder-only 中：

```text
Token
↓
Embedding
↓
Position Information
↓
Causal Self-Attention
↓
MLP
↓
多层堆叠
↓
Hidden States
```

这整个过程都在：

> 把原始 token 转换成更高层的内部表示。

所以从信息处理角度看，它当然属于一种 Encoding。

例如最后一个位置：

```text
？
↓
h6
```

因为它可以通过 Causal Attention 看见：

```text
中国 的 首都 是 哪里 ？
```

所以 \(h_6\) 已经编码了类似这样的信息：

> 当前上下文是在询问中国的首都。

因此：

\[
\boxed{
\text{Decoder-only 也存在 Encoding 过程}
}
\]

---

<a id="origin-534"></a>
## 16. 那为什么还有“解码过程”

<a id="origin-536"></a>
## 17. Hidden State 最后会映射成词表概率

得到最终 hidden state 后，例如 \(h_6\)：

\[
h_6
\rightarrow
\text{Linear}
\rightarrow
\text{Softmax}
\]

得到词表分布：

```text
北：0.65
上：0.04
南：0.03
东：0.01
...
```

于是模型选择：

```text
北
```

然后新的输入变成：

```text
中国 的 首都 是 哪里 ？ 北
```

继续计算并预测：

```text
京
```

因此生成过程是：

```text
Hidden State
↓
Vocabulary Distribution
↓
Next Token
↓
追加到输入
↓
继续生成
```

这就是实际生成意义上的 decoding。

---

<a id="origin-594"></a>
## 18. 为什么有 Encoding 过程，却仍叫 Decoder-only

<a id="origin-596"></a>
## 19. 因为“Decoder-only”说的是网络架构

这是整个问题最关键的一点。

“Decoder-only”并不是说：

> 模型内部只发生 decoding，不发生 encoding。

而是说：

> 模型的 Transformer 主体只由 Decoder-style Block 构成，没有独立的 Encoder Stack。

---

<a id="origin-610"></a>
## 20. 原始 Transformer 有两个独立 Stack

原始 Transformer：

```text
输入
 ↓
┌────────────┐
│ Encoder    │
│ Encoder    │
│ Encoder    │
└────────────┘
 ↓
Encoder Output
 ↓
┌────────────┐
│ Decoder    │
│ Decoder    │
│ Decoder    │
└────────────┘
 ↓
输出
```

所以它有：

\[
\boxed{
\text{Encoder Stack + Decoder Stack}
}
\]

---

<a id="origin-644"></a>
## 21. GPT 只有一个 Decoder-style Stack

GPT：

```text
Prompt
  ↓
┌─────────────────┐
│ Transformer     │
│ Decoder Block   │
│ Decoder Block   │
│ Decoder Block   │
└─────────────────┘
  ↓
Next Token
```

没有独立 Encoder。

因此叫：

\[
\boxed{
\text{Decoder-only}
}
\]

其中：

> “only” 指只有 Decoder-style Stack。

并不是：

> “only” 指模型内部只允许发生 Decoding。

---

<a id="origin-681"></a>
## 22. 为什么这些 Block 被称为 Decoder-style

<a id="origin-683"></a>
## 23. 最关键特征是 Causal Self-Attention

原始 Transformer Decoder 有一个非常典型的特点：

\[
\boxed{
\text{Masked Self-Attention}
}
\]

也就是：

```text
            我   喜欢   吃   苹果
我          ✓
喜欢        ✓    ✓
吃          ✓    ✓    ✓
苹果        ✓    ✓    ✓    ✓
```

这正是 GPT 使用的核心机制。

因此 GPT 被归类为 Decoder-only。

---

<a id="origin-709"></a>
## 24. 但 GPT 的 Decoder 又不是原始 Decoder 的完全复制

<a id="origin-711"></a>
## 25. 原始 Transformer Decoder 还包含 Cross-Attention

原始 Decoder Block：

```text
Masked Self-Attention
        ↓
Cross-Attention
        ↓
Feed Forward
```

其中 Cross-Attention 用来读取 Encoder 的输出。

但是 GPT 根本没有 Encoder。

所以也不需要 Cross-Attention。

GPT 中更接近：

```text
Causal Self-Attention
        ↓
MLP
```

不断堆叠：

```text
Token
  ↓
Embedding
  ↓
┌────────────────────┐
│ Causal Self-Attn   │
│        ↓           │
│       MLP          │
└────────────────────┘
        × N
  ↓
LM Head
  ↓
Next Token
```

因此从更严谨的术语上说：

\[
\boxed{
\text{GPT 更接近 Causal Transformer}
}
\]

“Decoder-only”是沿用了 Transformer 家族中的历史命名。

---

<a id="origin-768"></a>
## 26. 一个非常直观的类比

<a id="origin-770"></a>
## 27. Encoder–Decoder 像两个部门

传统 Encoder–Decoder：

```text
阅读理解部：
阅读材料
↓
形成笔记

写作部：
读取笔记
↓
生成答案
```

也就是：

```text
Encoder
↓
Hidden Representation
↓
Decoder
```

---

<a id="origin-798"></a>
## 28. Decoder-only 像一个部门把两件事都做了

GPT：

```text
写作部：
自己阅读材料
↓
自己形成理解
↓
直接继续往下写
```

虽然这个“写作部”内部也完成了：

- 阅读；
- 理解；
- 表示；
- 生成；

但组织架构上仍然只有一个部门。

所以还是：

\[
\boxed{
\text{Decoder-only}
}
\]

---

<a id="origin-830"></a>
## 29. 最终关系总结

<a id="origin-832"></a>
## 30. Encoder

```text
完整输入
↓
双向 Self-Attention
↓
上下文表示
```

特点：

\[
\boxed{
\text{可以看左边，也可以看右边}
}
\]

因为：

> 不使用 Causal Mask。

---

<a id="origin-856"></a>
## 31. Decoder-only

```text
Prompt / 历史 Token
↓
Causal Self-Attention
↓
上下文 Hidden State
↓
预测 Next Token
↓
继续输入
```

特点：

\[
\boxed{
\text{只能看自己和左边}
}
\]

因为：

> 使用 Causal Mask。

---

<a id="origin-884"></a>
## 32. Decoder-only 中有没有 Encoding

有。

过程：

```text
Token
↓
Embedding
↓
多层 Attention + MLP
↓
Hidden States
```

就是：

\[
\boxed{
\text{Encoding Process}
}
\]

---

<a id="origin-910"></a>
## 33. Decoder-only 中有没有 Encoder

没有独立的 Encoder Stack。

因此：

\[
\boxed{
\text{Decoder-only}
}
\]

---

<a id="origin-924"></a>
## 34. 最重要的三句话

<a id="origin-926"></a>
### 34.1 第一句

\[
\boxed{
\text{Encoder 能双向看，是因为没有 Causal Mask}
}
\]

<a id="origin-934"></a>
#### 34.1.1 第二句

\[
\boxed{
\text{Decoder-only 也会把输入编码成 Hidden States}
}
\]

<a id="origin-942"></a>
#### 34.1.2 第三句

\[
\boxed{
\text{有 Encoding 过程，不代表有 Encoder 模块}
}
\]

---

<a id="origin-952"></a>
## 35. 核心要点

> **Decoder-only 中的 “Decoder” 是网络结构名称，而不是说模型内部只发生“解码”。GPT 没有独立的 Encoder Stack，但 Prompt 仍然会经过 Embedding、Causal Self-Attention 和 MLP，被逐层转换成上下文化 Hidden States，这就是 Encoding 过程；之所以仍然叫 Decoder-only，是因为整个 Transformer 主体只有采用因果注意力的 Decoder-style Block。**


---

<a id="origin-959"></a>
## 36. 为什么这类结构被称为 Decoder Block

<a id="origin-961"></a>
## 37. “Decoder” 这个名字首先来自它在原始 Transformer 中承担的角色

原始 Transformer 是一个典型的 Encoder–Decoder 架构。

例如机器翻译任务：

```text
I love China.
      ↓
   Transformer
      ↓
我爱中国。
```

其中：

- Encoder 负责处理源语言序列；
- Decoder 负责一步一步生成目标语言序列。

可以画成：

```text
源语言输入
I love China.
     ↓
  Encoder
     ↓
源语言语义表示
     ↓
  Decoder
     ↓
我 → 爱 → 中国
```

因此：

\[
\boxed{
\text{Decoder 这个名字，本质上来自“负责生成目标序列”这一角色}
}
\]

而不是因为它里面存在某一个特定算子。

---

<a id="origin-1007"></a>
## 38. 原始 Transformer 的 Encoder 和 Decoder

可以把原始 Transformer 看成两侧：

```text
Encoder Side                  Decoder Side
────────────                  ────────────
Bidirectional                 Masked Self-Attention
Self-Attention                       ↓
      ↓                       Cross-Attention
     MLP                             ↓
                                    MLP
```

Encoder 主要做：

```text
完整输入
↓
双向理解
↓
形成上下文表示
```

Decoder 主要做：

```text
已经生成的目标序列
↓
因果注意力
↓
读取 Encoder 信息
↓
生成下一个 Token
```

---

<a id="origin-1045"></a>
## 39. 为什么 GPT 被称为 Decoder-only

<a id="origin-1047"></a>
## 40. GPT 继承了原始 Transformer 的“目标生成侧”

GPT 没有独立 Encoder。

因此也不需要读取 Encoder 输出的 Cross-Attention。

于是 GPT 的 Block 更接近：

```text
Causal Self-Attention
        ↓
MLP
```

不断堆叠：

```text
Token
  ↓
Embedding
  ↓
┌────────────────────┐
│ Causal Self-Attn   │
│        ↓           │
│       MLP          │
└────────────────────┘
        × N
  ↓
LM Head
  ↓
Next Token
```

也就是说，GPT 从原始 Transformer Decoder 中保留了最核心的：

- 自回归生成；
- Causal Self-Attention；
- 根据左边 token 预测右边 token。

而去掉了：

- 独立 Encoder；
- Cross-Attention。

因此大家把这一类模型称为：

\[
\boxed{
\text{Decoder-only Transformer}
}
\]

---

<a id="origin-1101"></a>
## 41. Decoder-only 是一种“架构谱系”上的名字

可以这样理解 Transformer 家族的发展：

```text
               原始 Transformer
               /             \
              /               \
     Encoder Side          Decoder Side
          ↓                    ↓
       BERT                 GPT
          ↓                    ↓
   Encoder-only          Decoder-only
```

BERT 主要继承原始 Transformer 的 Encoder 风格：

```text
Bidirectional Self-Attention
↓
MLP
```

GPT 主要继承原始 Transformer 的 Decoder 风格：

```text
Causal Self-Attention
↓
MLP
```

因此：

> Decoder-only 这个名字带有明显的历史继承关系。

---


<a id="origin-1139"></a>
## 42. 最容易误解的一点

不要把下面两句话混在一起：

<a id="origin-1143"></a>
### 42.1 错误理解

```text
只要用了 Causal Mask，
这个 Block 就天然定义为 Decoder Block。
```

这不够准确。

<a id="origin-1152"></a>
#### 42.1.1 正确理解

```text
原始 Transformer 中，
负责目标序列生成的模块被称为 Decoder。

为了自回归生成，
Decoder 使用了 Masked Self-Attention。

GPT 继承了这种自回归、因果注意力的结构，
因此被历史性地归类为 Decoder-only。
```

---

<a id="origin-1167"></a>
## 43. 一个非常直观的历史关系

可以这样记：

```text
原始 Transformer Decoder
        │
        ├── 自回归生成
        ├── Masked Self-Attention
        ├── Cross-Attention
        └── Feed Forward
                │
                │ GPT 去掉 Encoder
                ▼
GPT
        │
        ├── 自回归生成
        ├── Causal Self-Attention
        └── MLP
```

因此：

\[
\boxed{
\text{GPT 是“Decoder 风格”的 Transformer}
}
\]

而不是：

\[
\boxed{
\text{GPT 等于原始 Decoder 的完整复制}
}
\]

---

<a id="origin-1206"></a>
## 44. 最终总结

<a id="origin-1208"></a>
## 45. 为什么这一类被称为 Decoder Block

最核心的逻辑是：

```text
原始 Transformer 中
负责生成目标序列的一侧
↓
被命名为 Decoder
↓
为了自回归生成
使用 Masked Self-Attention
↓
GPT 继承这种因果、自回归结构
↓
被称为 Decoder-only
```

所以：

\[
\boxed{
\text{Decoder Block 这个名字首先来自功能角色和历史架构}
}
\]

而：

\[
\boxed{
\text{Causal Self-Attention 是它最典型的结构特征之一}
}
\]

---

<a id="origin-1244"></a>
## 46. 核心要点

> **“Decoder Block” 这个名字来自原始 Transformer 中负责自回归生成目标序列的那一侧；Masked/Causal Self-Attention 是为了实现这种生成方式而使用的关键机制。GPT 继承了这种自回归、因果注意力的 Decoder 风格，因此被称为 Decoder-only，但它并不是原始 Transformer Decoder Block 的完整复制，因为它没有 Cross-Attention。**
