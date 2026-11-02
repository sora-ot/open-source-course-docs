# MHA 多头注意力


---

<a id="origin-5"></a>
## 1. 从最普通的单头 Attention 开始

先暂时不要考虑 Multi-Head Attention。

假设当前有一句话：

```text
I love artificial intelligence
```

对于某一层 Transformer 来说，每个 token 都有一个 hidden state。

例如：

```math
x_I,\quad
x_{\text{love}},\quad
x_{\text{artificial}},\quad
x_{\text{intelligence}}
```

然后通过三组参数矩阵：

```math
W_Q,\quad W_K,\quad W_V
```

得到：

```math
Q=XW_Q
```

```math
K=XW_K
```

```math
V=XW_V
```

对于 `love` 这个 token：

```math
Q_{\text{love}}
=
x_{\text{love}}W_Q
```

对于 `I`：

```math
K_I
=
x_IW_K
```

```math
V_I
=
x_IW_V
```

对于 `love` 自己：

```math
K_{\text{love}}
=
x_{\text{love}}W_K
```

```math
V_{\text{love}}
=
x_{\text{love}}W_V
```

于是 `love` 可以通过：

```math
Q_{\text{love}}K_I^T
```

以及：

```math
Q_{\text{love}}K_{\text{love}}^T
```

判断：

> 当前这个 `love` 应该关注前面的哪些 token？

经过 Softmax：

```math
\alpha
=
\operatorname{softmax}
\left(
\frac{QK^T}{\sqrt{d_k}}
\right)
```

最后得到输出：

```math
O_{\text{love}}
=
\alpha_I V_I
+
\alpha_{\text{love}}V_{\text{love}}
```

这就是最基本的 Self-Attention。

**注意这里的输出\(O_\text{love}\)是一个加权求和的向量或矩阵，它代表了根据注意力权重从 Value（值）中提取出的关键信息，后面跟全连接层等可以输出hidden state.**

---

<a id="origin-125"></a>
## 2. 一个 Attention Head 本质上在干什么？

可以把一个 Attention Head 简单理解成：

> 用一种特定的方式，判断“当前 token 应该从哪些 token 中读取信息”。

其计算过程是：

```text
当前 token
    ↓
生成 Query
    ↓
拿 Query 和所有 Key 比较
    ↓
得到 Attention Score
    ↓
Softmax
    ↓
决定从哪些 Value 中读取多少信息
```

公式：

```math
\operatorname{Attention}(Q,K,V)
=
\operatorname{softmax}
\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
```

也就是说，一个 Attention Head 同时包含两件事情：

第一件：

```text
去哪里找？
```

由：

```math
QK^T
```

决定。

第二件：

```text
找到之后拿什么信息回来？
```

由：

```math
V
```

决定。

---

<a id="origin-190"></a>
## 3. 那为什么一个 Attention Head 不够？

这是理解 Multi-Head Attention 最关键的问题。

考虑一句话：

```text
The animal didn't cross the street because it was too tired.
```

假设模型当前正在处理：

```text
it
```

对于 `it` 来说，它可能同时需要知道很多不同的信息。

例如：

<a id="origin-210"></a>
### 3.1 指代关系

模型可能需要知道：

```text
it 指的是谁？
```

可能重点关注：

```text
animal
```

---

<a id="origin-226"></a>
### 3.2 语法关系

模型可能需要关注：

```text
it → was → tired
```

---

<a id="origin-236"></a>
### 3.3 动作关系

模型可能还需要知道：

```text
谁没有 cross the street？
```

因此可能关注：

```text
cross
```

---

<a id="origin-252"></a>
### 3.4 局部上下文

某些情况下，模型可能只需要关注附近的 token：

```text
because it was
```

---

于是出现了一个问题。

如果只有一个 Attention Head，那么对于 `it`：

```math
Q_{\text{it}}
```

只能产生一套 Attention Score：

```math
Q_{\text{it}}K^T
```

然后得到一套 Attention 分布：

```math
\alpha_{\text{it}}
```

也就是：

```text
所有不同的信息关系
       ↓
都必须塞进
同一套 Attention 分布
```

这就会限制模型的表达能力。

---

<a id="origin-295"></a>
## 4. Multi-Head Attention 的核心思想

既然一个 token 可能同时需要从多个角度观察上下文，那么：

> 能不能让同一个 token 同时产生多个不同的 Query？

当然可以。

这就是：

<a id="origin-305"></a>
## 5. Multi-Head Attention

简称：

```text
MHA
```

假设：

```math
h=4
```

也就是有 4 个 Attention Head。

那么对于同一个 token `it`，我们不再只有：

```math
Q_{\text{it}}
```

而是有：

```math
Q_{\text{it}}^{(1)}
```

```math
Q_{\text{it}}^{(2)}
```

```math
Q_{\text{it}}^{(3)}
```

```math
Q_{\text{it}}^{(4)}
```

它们来自不同的投影参数：

```math
Q^{(1)}=XW_Q^{(1)}
```

```math
Q^{(2)}=XW_Q^{(2)}
```

```math
Q^{(3)}=XW_Q^{(3)}
```

```math
Q^{(4)}=XW_Q^{(4)}
```

因此：

```math
Q_{\text{it}}^{(1)}
=
x_{\text{it}}W_Q^{(1)}
```

```math
Q_{\text{it}}^{(2)}
=
x_{\text{it}}W_Q^{(2)}
```

等等。

---

<a id="origin-381"></a>
## 6. 不只是 Query 不一样，K 和 V 也不一样

标准的 MHA 并不是：

```text
多个 Q
共享一套 K/V
```

而是：

> 每个 Head 都有自己独立的 Q、K、V 投影。

例如四个 Head：

```text
Head 1:
Q¹   K¹   V¹

Head 2:
Q²   K²   V²

Head 3:
Q³   K³   V³

Head 4:
Q⁴   K⁴   V⁴
```

数学上：

```math
Q^{(i)}=XW_Q^{(i)}
```

```math
K^{(i)}=XW_K^{(i)}
```

```math
V^{(i)}=XW_V^{(i)}
```

第一个 Head：

```math
H_1
=
\operatorname{softmax}
\left(
\frac{
Q^{(1)}K^{(1)T}
}{
\sqrt{d_k}
}
\right)
V^{(1)}
```

第二个 Head：

```math
H_2
=
\operatorname{softmax}
\left(
\frac{
Q^{(2)}K^{(2)T}
}{
\sqrt{d_k}
}
\right)
V^{(2)}
```

依此类推。

最后：

```math
H
=
\operatorname{Concat}
(
H_1,H_2,H_3,H_4
)
```

然后再经过：

```math
O=HW_O
```

得到最终的 Multi-Head Attention 输出。

---

<a id="origin-479"></a>
## 7. MHA 的本质：为什么不同 Head 会学到不同特征？

<a id="origin-481"></a>
## 8. 先提出最关键的问题

很多资料介绍 Multi-Head Attention 时都会说：

> 不同 Attention Head 可以关注不同的信息。

例如：

```text
Head 1：可能关注语法关系
Head 2：可能关注指代关系
Head 3：可能关注局部上下文
Head 4：可能关注长距离依赖
```

但是这里其实跳过了最重要的一步：

> **为什么它们会不一样？**

模型训练数据里并没有这样的标签：

```text
Head 1，请你学习语法。

Head 2，请你学习指代。

Head 3，请你学习位置关系。
```

也没有一个 Loss 写成：

```text
如果 Head 1 学会主谓关系，奖励它。
```

真正发生的事情其实是：

```text
不同 Head
↓
拥有不同参数
↓
随机初始化时就已经不完全一样
↓
产生不同输出
↓
对最终预测产生不同影响
↓
反向传播得到不同梯度
↓
参数朝不同方向更新
↓
差异越来越明显
↓
最终形成不同的 Attention Pattern / 特征表示
```

所以首先一定要记住：

> **Head 的分工不是人工设计出来的，而是训练过程中自己“长出来”的。**

---

<a id="origin-544"></a>
## 9. 先从一个 token 的 hidden state 开始

假设当前 token 是：

```text
love
```

进入 Attention 层之前，它有一个 hidden state：

```math
x_{\text{love}}
```

例如模型维度：

```math
d_{\text{model}}=4096
```

那么：

```math
x_{\text{love}}\in\mathbb{R}^{4096}
```

注意：

这个向量并不能简单理解成：

```text
第 1 维 = 词性
第 2 维 = 情感
第 3 维 = 主语
第 4 维 = 动词
```

真实神经网络不是这么整齐的。

更准确地说：

> hidden state 的几千个维度共同编码了当前 token 的各种上下文信息。

里面可能混合包含：

```text
词义
词性
句法关系
实体信息
位置关系
上下文信息
指代信息
语义角色
……
```

这些信息是高度混合在一起的。

---

<a id="origin-605"></a>
## 10. Attention Head 做的第一件事，其实就是“重新看这个向量”

如果只有一个 Attention Head，我们会计算：

```math
Q=xW_Q
```

```math
K=xW_K
```

```math
V=xW_V
```

这里：

```math
W_Q
```

其实就是在做一个线性投影：

```text
原来的 hidden state
        ↓
经过 W_Q
        ↓
重新组织其中的信息
        ↓
得到 Query 表示
```

所以：

```math
Q=xW_Q
```

不是单纯地“把 x 复制一下”。

它实际上相当于：

> 从 hidden state 中提取、组合一组适合进行“查询”的特征。

---

<a id="origin-653"></a>
## 11. 一个简单例子：同一个 x 可以被投影成完全不同的东西

为了方便理解，假设 hidden state 只有 4 维：

```math
x=
[x_1,x_2,x_3,x_4]
```

假设这四维粗略地蕴含：

```text
x1：某类语法信息

x2：某类实体信息

x3：某类位置信息

x4：某类语义信息
```

这只是为了帮助理解，真实模型不会这么规整。

现在假设有两个不同的 Query 投影矩阵。

Head 1：

```math
W_Q^{(1)}
```

Head 2：

```math
W_Q^{(2)}
```

例如 Head 1 最终学成了：

```math
Q^{(1)}
=
xW_Q^{(1)}
```

更加依赖：

```text
x1、x3
```

而 Head 2：

```math
Q^{(2)}
=
xW_Q^{(2)}
```

更加依赖：

```text
x2、x4
```

那么即便输入：

```math
x
```

完全相同：

```text
同一个 love
同一个 hidden state
```

经过两个不同矩阵以后：

```math
Q^{(1)}\neq Q^{(2)}
```

于是两个 Head 看到的其实是：

```text
同一个 token 的不同投影视角。
```

---

<a id="origin-745"></a>
## 12. 用一个真正的数学例子看就非常直观了

假设：

```math
x=
\begin{bmatrix}
1 & 2 & 3 & 4
\end{bmatrix}
```

为了简单，我们让每个 Query Head 最后只有二维。

Head 1 的参数：

```math
W_Q^{(1)}
=
\begin{bmatrix}
1&0\\
0&0\\
0&1\\
0&0
\end{bmatrix}
```

那么：

```math
Q^{(1)}
=
xW_Q^{(1)}
```

得到：

```math
Q^{(1)}
=
[1,3]
```

**也就是说 Head 1 主要把：**

```text
第 1 维
第 3 维
```

**抽了出来，此时的\(Q^{(1)}\)就是一个只包含\(x\)的第1和第3维信息的查询向量。**

---

Head 2：

```math
W_Q^{(2)}
=
\begin{bmatrix}
0&0\\
1&0\\
0&0\\
0&1
\end{bmatrix}
```

那么：

```math
Q^{(2)}
=
xW_Q^{(2)}
```

得到：

```math
Q^{(2)}
=
[2,4]
```

也就是主要提取：

```text
第 2 维
第 4 维
```

于是：

```math
Q^{(1)}=[1,3]
```

而：

```math
Q^{(2)}=[2,4]
```

输入明明完全相同：

```math
x=[1,2,3,4]
```

但是：

```math
W_Q^{(1)}\neq W_Q^{(2)}
```

所以：

```math
Q^{(1)}\neq Q^{(2)}
```

---

<a id="origin-866"></a>
## 13. 所以“为什么 Query Head 可以不一样？”

答案其实非常直接：

**因为不同 Query Head 使用的参数不一样，因此它抽取的特征就不一样。**

对于同一个 token：

```math
x
```

Head 1：

```math
Q^{(1)}
=
xW_Q^{(1)}
```

Head 2：

```math
Q^{(2)}
=
xW_Q^{(2)}
```

Head 3：

```math
Q^{(3)}
=
xW_Q^{(3)}
```

因为：

```math
W_Q^{(1)}
\neq
W_Q^{(2)}
\neq
W_Q^{(3)}
```

所以自然：

```math
Q^{(1)}
\neq
Q^{(2)}
\neq
Q^{(3)}
```

---

<a id="origin-924"></a>
## 14. 实际代码中真的有很多个 W_Q 吗？

这里又有一个容易混淆的地方。

从数学上，我们经常写：

```math
W_Q^{(1)},W_Q^{(2)},...,W_Q^{(h)}
```

表示每个 Head 有自己的 Query 投影。

但是实际代码中通常不会真的写：

```python
self.q1 = Linear(...)
self.q2 = Linear(...)
self.q3 = Linear(...)
...
```

而是使用一个大的：

```math
W_Q
```

例如：

```math
W_Q
\in
\mathbb{R}^{4096\times4096}
```

先算：

```math
Q=XW_Q
```

得到：

```text
4096维 Q
```

然后 reshape：

```text
4096
↓
32 heads × 128 dimensions
```

于是：

```text
Q Head 1 → 前 128 维

Q Head 2 → 接下来 128 维

Q Head 3 → 再接下来 128 维

...
```

这在数学上等价于把大的：

```math
W_Q
```

按列切成：

```math
W_Q=
[
W_Q^{(1)}
\;
W_Q^{(2)}
\;
\cdots
\;
W_Q^{(32)}
]
```

所以本质仍然是：

```text
不同 Query Head
拥有不同的一组参数。
```
---

<a id="origin-1020"></a>
## 15. 单头 Attention 到多头 Attention：Query 的长度怎么变？

回忆：假设模型的 hidden size （Transformer 里，每个 token 用多少个数字来表示）是：

```math
d_{\text{model}}=4096
```

也就是说，一个 token 的 输入，即hidden state为：

```math
x\in\mathbb{R}^{4096}
```

---

<a id="origin-1036"></a>
## 16. 传统单头 Attention

单头 Attention 中，可以让：

```math
W_Q\in\mathbb{R}^{4096\times4096}
```

于是：

```math
Q=xW_Q
```

得到：

```math
Q\in\mathbb{R}^{4096}
```

也就是说：

> **单头 Attention 中，一个 token 只有一个 Query，这个 Query 的长度是 4096。**

可以画成：

```text
x
4096维
 ↓ W_Q
Q
4096维
```

即：

```text
单头 Attention：

Q
[----------------------------------------]
                  4096维
```

---

<a id="origin-1082"></a>
## 17. 变成 32 头 Multi-Head Attention

现在仍然假设：

```math
d_{\text{model}}=4096
```

并且设置：

```math
n_{\text{heads}}=32
```

输入仍然是：

```math
x\in\mathbb{R}^{4096}
```

先经过：

```math
Q=xW_Q
```

得到的总 Query 长度仍然是：

```math
4096
```

但是现在不再把这 4096 维看成一个 Query。

而是把它拆成：

```math
32
```

个 Query Head。

因为：

```math
4096\div32=128
```

所以每个 Query Head 的长度是：

```math
d_{\text{head}}=128
```

于是：

```text
Q
4096维

 ↓ reshape

32 × 128
```

也就是：

```text
多头 Attention：

Q
[Head1][Head2][Head3] ... [Head32]
 128    128    128           128
```

---

<a id="origin-1159"></a>
## 18. 最终发生了什么变化？

单头 Attention：

```text
1 个 Query

每个 Query：4096维
```

也就是：

```math
\boxed{
1\times4096
}
```

变成 32 头 MHA 后：

```text
32 个 Query Head

每个 Query Head：128维
```

也就是：

```math
\boxed{
32\times128
}
```

而：

```math
32\times128=4096
```

所以：

> **总维度并没有变化。**

只是从：

```text
1 个大的 4096 维 Query
```

变成：

```text
32 个小的 128 维 Query
```

---

<a id="origin-1217"></a>
## 19. 一张表看懂

| 结构           | Query 数量 | 每个 Query 长度 |  总长度 |
| ------------ | -------: | ----------: | ---: |
| 单头 Attention |        1 |        4096 | 4096 |
| 32 头 MHA     |       32 |         128 | 4096 |

所以最核心的变化就是：

```text
单头：

1 × 4096
```

变成：

```text
多头：

32 × 128
```

即：

```math
\boxed{
4096
=
32\times128
}
```

---

<a id="origin-1252"></a>
## 20. 一句话总结

> **Multi-Head Attention 并不是把 Query 的总长度扩大，而是把原来一个大的 Query 拆成多个较小的 Query Head。**

例如：

```text
单头：
1 个 4096 维 Query

↓

32 头 MHA：
32 个 128 维 Query Head
```

所以：

```math
\boxed{
\text{总维度不变，只是从“一个大 Query”变成“多个小 Query”。}
}
```
---

<a id="origin-1277"></a>
## 21. MHA 中为什么每个 Head 都有自己的 Q/K/V，以及 Q 为什么要切分

先明确一个最容易混淆的点：

> **标准 MHA 中，不是只有每个 Head 的 K/V 独立，而是每个 Head 都有自己独立的一套 Q、K、V。**

假设：

```math
d_{\text{model}}=4096
```

并且：

```math
n_{\text{head}}=32
```

那么每个 Head 的维度是：

```math
d_{\text{head}}
=
\frac{4096}{32}
=
128
```

所以：

```math
\boxed{
d_{\text{head}}=128
}
```

---

<a id="origin-1315"></a>
## 22. 每个 Head 实际上都有自己的一套 Q/K/V

标准 MHA 中，第 1 个 Head：

```math
Q^{(1)}\in\mathbb{R}^{128}
```

```math
K^{(1)}\in\mathbb{R}^{128}
```

```math
V^{(1)}\in\mathbb{R}^{128}
```

第 2 个 Head：

```math
Q^{(2)}\in\mathbb{R}^{128}
```

```math
K^{(2)}\in\mathbb{R}^{128}
```

```math
V^{(2)}\in\mathbb{R}^{128}
```

一直到第 32 个 Head：

```math
Q^{(32)},K^{(32)},V^{(32)}
```

它们也都是 128 维。

所以可以画成：

```text
Head 1:
Q¹：128维
K¹：128维
V¹：128维

Head 2:
Q²：128维
K²：128维
V²：128维

Head 3:
Q³：128维
K³：128维
V³：128维

...

Head 32:
Q³²：128维
K³²：128维
V³²：128维
```

---

<a id="origin-1381"></a>
## 23. 为什么 Q 也必须是 128 维？

因为一个 Head 内部要计算：

```math
Q^{(h)}K^{(h)T}
```

也就是 Query 和 Key 要做点积。

例如 Head 1：

```math
Q^{(1)}
\in
\mathbb{R}^{1\times128}
```

而：

```math
K^{(1)}
\in
\mathbb{R}^{1\times128}
```

那么：

```math
Q^{(1)}K^{(1)T}
```

维度就是：

```math
[1\times128]
\times
[128\times1]
```

得到：

```math
[1\times1]
```

也就是一个 Attention Score。

所以：

> **同一个 Head 内部的 Q 和 K 必须在同一个 head_dim 空间中。**

在这个例子里就是：

```math
128
```

维。

---

<a id="origin-1443"></a>
## 24. MHA 可以理解成很多个“小 Attention”

这是最容易理解的方式。

假设原来只有单头：

```text
一个大 Attention

Q：4096维
K：4096维
V：4096维
```

变成 32 头以后，可以理解成：

```text
32 个小 Attention

Head 1：
Q¹ = 128维
K¹ = 128维
V¹ = 128维

Head 2：
Q² = 128维
K² = 128维
V² = 128维

...

Head 32：
Q³² = 128维
K³² = 128维
V³² = 128维
```

每个 Head 独立计算：

```math
O^{(h)}
=
\operatorname{softmax}
\left(
\frac{
Q^{(h)}K^{(h)T}
}{
\sqrt{128}
}
\right)V^{(h)}
```

例如 Head 1：

```math
O^{(1)}
=
\operatorname{softmax}
\left(
\frac{
Q^{(1)}K^{(1)T}
}{
\sqrt{128}
}
\right)V^{(1)}
```

Head 2：

```math
O^{(2)}
=
\operatorname{softmax}
\left(
\frac{
Q^{(2)}K^{(2)T}
}{
\sqrt{128}
}
\right)V^{(2)}
```

---

<a id="origin-1527"></a>
## 25. 每个 Head 的输出最后再拼起来

每个 Head 的输出：

```math
O^{(h)}
\in
\mathbb{R}^{128}
```

一共有 32 个 Head：

```math
O^{(1)},
O^{(2)},
\dots,
O^{(32)}
```

最后：

```math
O
=
\operatorname{Concat}
(
O^{(1)},
O^{(2)},
\dots,
O^{(32)}
)
```

因为：

```math
32\times128=4096
```

所以最终：

```math
O\in\mathbb{R}^{4096}
```

于是整个 Attention 层的输入和输出维度保持一致：

```text
输入：

4096维

↓

32 个 Head

每个 Head：128维

↓

Concat

↓

4096维
```

**后面这个4096维度的带信息的向量会接比如全连接层输出logit。**

---

<a id="origin-1598"></a>
## 26. “每个 Head 有独立 K/V”到底是什么意思？

这里特别容易误解。

所谓：

> 每个 Head 有独立的 K/V

**不是说：**

```text
每个 Head 都有一整套 4096 维 K/V
```

而是说：

> 每个 Head 有自己独立的 K/V 投影参数。

例如：

```math
W_K^{(1)}
\neq
W_K^{(2)}
```

以及：

```math
W_V^{(1)}
\neq
W_V^{(2)}
```

但是每一个小矩阵的维度是：

```math
W_K^{(h)}
\in
\mathbb{R}^{4096\times128}
```

以及：

```math
W_V^{(h)}
\in
\mathbb{R}^{4096\times128}
```

所以：

```text
独立
```

指的是：

```text
参数不同
```

不是：

```text
每个 Head 都重新拥有完整的 4096 维空间。
```

---

<a id="origin-1668"></a>
## 27. Q 也是一样的

Query 也不是公共的。

每个 Head 同样有自己独立的：

```math
W_Q^{(h)}
```

例如：

```math
W_Q^{(1)}
\in
\mathbb{R}^{4096\times128}
```

```math
W_Q^{(2)}
\in
\mathbb{R}^{4096\times128}
```

并且：

```math
W_Q^{(1)}
\neq
W_Q^{(2)}
```

于是对于同一个 hidden state：

```math
x
\in
\mathbb{R}^{4096}
```

Head 1：

```math
Q^{(1)}
=
xW_Q^{(1)}
```

得到：

```math
Q^{(1)}
\in
\mathbb{R}^{128}
```

Head 2：

```math
Q^{(2)}
=
xW_Q^{(2)}
```

得到：

```math
Q^{(2)}
\in
\mathbb{R}^{128}
```

因为：

```math
W_Q^{(1)}
\neq
W_Q^{(2)}
```

所以通常：

```math
Q^{(1)}
\neq
Q^{(2)}
```

---

<a id="origin-1758"></a>
## 28. 所以标准 MHA 真正应该画成什么样？

假设某个 token 的 hidden state：

```math
x\in\mathbb{R}^{4096}
```

那么：

```text
                       Head 1
                 ┌─ W_Q¹ → Q¹ [128]
                 ├─ W_K¹ → K¹ [128]
                 └─ W_V¹ → V¹ [128]

                       ↓

                   Attention 1


                       Head 2
                 ┌─ W_Q² → Q² [128]
                 ├─ W_K² → K² [128]
x [4096] ────────┤─ W_V² → V² [128]

                       ↓

                   Attention 2


                       ...

                       Head 32
                 ┌─ W_Q³² → Q³² [128]
                 ├─ W_K³² → K³² [128]
                 └─ W_V³² → V³² [128]

                       ↓

                   Attention 32
```

也就是说：

> **每个 Head 都是一整套独立的小型 Attention。**


---

<a id="origin-1809"></a>
## 29. 从“为什么要多头”讲起：为什么参数量几乎不变，但 Multi-Head Attention 能表达更丰富的信息？

理解 Multi-Head Attention，可以从一个非常自然的问题开始：

> **既然一个 Attention Head 只能产生一套 Attention Weight，那我能不能多搞几个 Head，让模型同时从多个角度观察上下文？**

答案当然是可以。

但接下来马上会遇到一个问题：

> **如果每个 Head 都和原来的单头一样大，参数量岂不是直接爆炸？**

Multi-Head Attention 的整个设计，其实就是围绕这个问题展开的。

为了让整个过程更加具体，下面统一使用这句话作为例子：

```text
小明把一把红色雨伞递给小红，因为外面下雨了。
```

我们重点观察：

```text
小红
```

这个 token 在 Attention 中是怎样从前文获取信息的。

---

<a id="origin-1839"></a>
## 30. 从一个单头 Attention 开始

假设模型的 hidden size 是：

\[
d_{model}=4096
\]

对于句子：

```text
小明把一把红色雨伞递给小红，因为外面下雨了。
```

每一个 token 都有自己的：

\[
4096
\]

维 hidden state。

例如：

\[
x_{\text{小明}},
x_{\text{红色}},
x_{\text{雨伞}},
x_{\text{小红}},
x_{\text{下雨}}
\in
\mathbb{R}^{4096}
\]

如果现在只有一个 Attention Head，那么可以使用：

\[
W_Q,W_K,W_V
\in
\mathbb{R}^{4096\times4096}
\]

于是：

\[
Q=XW_Q
\]

\[
K=XW_K
\]

\[
V=XW_V
\]

所以对于 `小红`：

\[
q_{\text{小红}}
\in
\mathbb{R}^{4096}
\]

然后：

\[
q_{\text{小红}}
\]

会分别和前面所有 token 的 Key 进行匹配。

例如：

\[
q_{\text{小红}}k_{\text{小明}}^T
\]

\[
q_{\text{小红}}k_{\text{红色}}^T
\]

\[
q_{\text{小红}}k_{\text{雨伞}}^T
\]

\[
q_{\text{小红}}k_{\text{小红}}^T
\]

等等。

经过 Softmax，可能得到一套 Attention Weight。

例如为了方便理解：

```text
小明      30%
红色       5%
雨伞      40%
递给      10%
小红      10%
其他       5%
```

然后：

\[
o_{\text{小红}}
=
\sum_j
\alpha_jv_j
\]

最终：

\[
o_{\text{小红}}
\in
\mathbb{R}^{4096}
\]

---

<a id="origin-1963"></a>
## 31. 单头 Attention 真正的问题：只有一套 Attention Weight

刚才只有一套：

```text
小明      30%
红色       5%
雨伞      40%
递给      10%
小红      10%
其他       5%
```

这意味着：

> 整个 4096 维 Value，都必须按照这一套 token 权重进行信息聚合。

但是我们真正理解：

```text
小明把一把红色雨伞递给小红，因为外面下雨了。
```

时，其实可能同时需要回答很多完全不同的问题。

例如：

```text
问题 1：
“是谁把东西递给小红的？”

答案：
小明


问题 2：
“递给小红的是什么东西？”

答案：
雨伞


问题 3：
“雨伞是什么颜色？”

答案：
红色


问题 4：
“为什么要递雨伞？”

答案：
因为外面下雨了
```

这几个问题显然不应该使用完全相同的 Attention Weight。

例如：

```text
“是谁递东西？”
→ 应该主要关注 小明

“递的是什么？”
→ 应该主要关注 雨伞

“是什么颜色？”
→ 应该主要关注 红色

“为什么需要雨伞？”
→ 应该主要关注 下雨
```

但单头只有：

\[
\boxed{
1\text{ 套 Softmax 权重}
}
\]

所以一个非常自然的想法就是：

> **那我能不能多搞几个 Attention Head，让每个 Head 分别去找不同的信息？**

---

<a id="origin-2051"></a>
## 32. 最直接的想法：做 32 个完整的 4096 维 Head

假设我们想要：

\[
32
\]

个 Attention Head。

最直觉的做法就是：

```text
Head 1：4096维
Head 2：4096维
Head 3：4096维
...
Head 32：4096维
```

这样每个 Head 都可以拥有自己独立的：

\[
Q,K,V
\]

以及自己的：

\[
Attention
\]

例如：

```text
Head 1：
专门去找“是谁递东西？”

Head 2：
专门去找“递的是什么？”

Head 3：
专门去找“是什么颜色？”

Head 4：
专门去找“为什么发生？”

...
```

当然真实模型不会这么整齐地分工，但这个直觉非常适合帮助理解。

问题在于：

> 如果每个 Head 都还是完整的 4096 维，参数量和计算量会变得非常大。

---

<a id="origin-2109"></a>
## 33. 如果每个 Head 都是 4096 维，参数量会发生什么？

原来一个 Query 投影 **（线性变换，即把原来的表示映射到另一个特征空间，这里指的是把 hidden state 线性映射到 Query 特征空间。）**：

\[
W_Q
\in
\mathbb{R}^{4096\times4096}
\]

参数量：

\[
4096\times4096
\]

如果现在有 32 个完整的 4096 维 Query Head：

\[
W_Q^{(1)}
\in
\mathbb{R}^{4096\times4096}
\]

\[
W_Q^{(2)}
\in
\mathbb{R}^{4096\times4096}
\]

……

一直到：

\[
W_Q^{(32)}
\in
\mathbb{R}^{4096\times4096}
\]

那么总参数量就变成：

\[
32\times4096\times4096
\]

直接扩大：

\[
\boxed{
32\times
}
\]

K 和 V 同样如此。

所以这种设计虽然可以得到：

\[
32
\]

套独立 Attention，

但是代价太高。

因此真正的问题变成：

> **有没有办法得到 32 套独立 Attention，但是又不把参数量扩大 32 倍？**

答案就是 Multi-Head Attention 的经典设计。

---

<a id="origin-2183"></a>
## 34. 保持总维度 4096 不变，把它分给 32 个 Head

我们不让每个 Head 都占：

\[
4096
\]

维。

而是让总投影维度仍然保持：

\[
4096
\]

不变。

既然现在要分成：

\[
32
\]

个 Head，

那么每个 Head 分到：

\[
d_{head}
=
\frac{4096}{32}
=
128
\]

于是：

```text
Head 1：128维
Head 2：128维
Head 3：128维
...
Head 32：128维
```

总维度仍然：

\[
32\times128
=
4096
\]

所以：

\[
\boxed{
d_{head}
=
\frac{d_{model}}{N_{head}}
}
\]

可以从设计动机上理解为：

**想要 32 套 Attention，
但又不想付出 32 倍参数，
于是保持总投影维度 4096 不变，
把它分给 32 个 Head，
每个 Head 使用 128 维。**

---

<a id="origin-2257"></a>
## 35. 但是千万不要理解成“把原始 X 直接切成 32 段”

假设：

\[
x\in\mathbb{R}^{4096}
\]

一个很容易产生的错误理解是：

```text
X 的第 1~128维
        ↓
     Head 1

X 的第129~256维
        ↓
     Head 2

...

X 的最后128维
        ↓
     Head 32
```

如果真的是这样，那么：

> Head 1 永远只能看到 X 的前 128 维。

这确实会造成严重的信息割裂。

但 Transformer 不是这样做的。

真正发生的是：

**32 个 Head 都读取完整的 4096 维 X，
只是通过不同的投影矩阵，
各自生成不同的 128 维表示。
**

---

<a id="origin-2300"></a>
## 36. 真正的 Q：一个大投影可以看成 32 个小投影

整体：

\[
W_Q
\in
\mathbb{R}^{4096\times4096}
\]

可以从数学上看成：

\[
W_Q
=
[
W_Q^{(1)}
|
W_Q^{(2)}
|
\dots
|
W_Q^{(32)}
]
\]

其中：

\[
W_Q^{(h)}
\in
\mathbb{R}^{4096\times128}
\]

于是对于 `小红`：

\[
q_{\text{小红}}^{(1)}
=
x_{\text{小红}}W_Q^{(1)}
\]

\[
q_{\text{小红}}^{(2)}
=
x_{\text{小红}}W_Q^{(2)}
\]

……

\[
q_{\text{小红}}^{(32)}
=
x_{\text{小红}}W_Q^{(32)}
\]

每一个：

\[
q_{\text{小红}}^{(h)}
\in
\mathbb{R}^{128}
\]

但是关键是：

\[
\boxed{
\text{每个 Head 都以完整的 }x_{\text{小红}}\in\mathbb{R}^{4096}
\text{ 作为输入}
}
\]

可以画成：

```text
                         完整 x_小红
                         [4096维]
                            │
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
     W_Q^1               W_Q^2             ... W_Q^32
   4096×128             4096×128             4096×128
        ↓                   ↓                   ↓
    q_小红^1            q_小红^2            q_小红^32
      128维                128维                128维
```

所以：

**不是把 X 切成 32 份，
而是让 32 个不同的小投影器
同时从完整 X 中提取不同的 128 维 Query。**

---

<a id="origin-2396"></a>
## 37. 可以把 32 个 Query Head 理解成“同时提出 32 种不同的问题”

还是这句话：

```text
小明把一把红色雨伞递给小红，因为外面下雨了。
```

现在模型处理：

```text
小红
```

对于某一个 Head：

\[
q_{\text{小红}}^{(1)}
\]

可以粗略理解成：

```text
“是谁把东西给我的？”
```

另一个 Head：

\[
q_{\text{小红}}^{(2)}
\]

可以粗略理解成：

```text
“给我的是什么东西？”
```

再一个 Head：

\[
q_{\text{小红}}^{(3)}
\]

可以粗略理解成：

```text
“这个东西有什么特征？”
```

再一个 Head：

\[
q_{\text{小红}}^{(4)}
\]

可以粗略理解成：

```text
“为什么发生这件事？”
```

所以：

\[
\boxed{
32\text{ 个 Query Head}
\approx
\text{对同一份完整上下文，同时提出 32 种不同的问题}
}
\]

当然真实模型中的 128 维 Query 并不是自然语言问题，它们只是连续向量。

这里的自然语言只是帮助理解这些不同投影为什么有意义。

---

<a id="origin-2474"></a>
## 38. K 也是完全一样的道理

整体：

\[
W_K
\in
\mathbb{R}^{4096\times4096}
\]

也可以看成：

\[
W_K
=
[
W_K^{(1)}
|
W_K^{(2)}
|
\dots
|
W_K^{(32)}
]
\]

其中：

\[
W_K^{(h)}
\in
\mathbb{R}^{4096\times128}
\]

所以同一个：

```text
小明
```

在不同 Head 中，会得到不同的 Key：

\[
k_{\text{小明}}^{(1)}
=
x_{\text{小明}}W_K^{(1)}
\]

\[
k_{\text{小明}}^{(2)}
=
x_{\text{小明}}W_K^{(2)}
\]

……

同一个：

```text
雨伞
```

也会得到：

\[
k_{\text{雨伞}}^{(1)},
k_{\text{雨伞}}^{(2)},
\dots
\]

---

<a id="origin-2546"></a>
## 39. K 可以理解成“同一个 token，用不同方式介绍自己”

例如在 Head 1 中：

```text
Q_小红^(1)：

“是谁把东西给我的？”
```

那么：

```text
K_小明^(1)
```

可以粗略理解成：

```text
“我是前面那个执行递东西动作的人。”
```

而：

```text
K_雨伞^(1)
```

可以粗略理解成：

```text
“我是被递出去的物品。”
```

所以：

\[
q_{\text{小红}}^{(1)}
\]

和：

\[
k_{\text{小明}}^{(1)}
\]

会更加匹配。

---

到了 Head 2：

```text
Q_小红^(2)：

“给我的是什么东西？”
```

这时：

```text
K_雨伞^(2)
```

可以粗略理解成：

```text
“我是前面被递给某人的物品。”
```

于是：

\[
q_{\text{小红}}^{(2)}
\]

和：

\[
k_{\text{雨伞}}^{(2)}
\]

会更加匹配。

所以：

\[
\boxed{
Q\text{ 是“我要找什么”}
}
\]

而：

\[
\boxed{
K\text{ 是“我有什么特征可以被你匹配”}
}
\]

---

<a id="origin-2648"></a>
## 40. Head 1 可能主要关注“小明”

假设 Head 1 的 Query 可以粗略理解成：

```text
“是谁把东西给小红？”
```

那么 Softmax 之后可能变成：

```text
小明      90%
红色       1%
雨伞       3%
递给       3%
小红       2%
其他       1%
```

于是：

\[
\alpha^{(1)}
\]

主要集中在：

```text
小明
```

所以这个 Head 可以理解成：

> **主要负责从“小明”这里取回信息。**

---

<a id="origin-2685"></a>
## 41. Head 2 可能主要关注“雨伞”

Head 2 的 Query 可以粗略理解成：

```text
“给小红的是什么？”
```

Softmax 可能变成：

```text
小明       2%
红色       3%
雨伞      90%
递给       2%
小红       2%
其他       1%
```

于是 Head 2 主要关注：

```text
雨伞
```

---

<a id="origin-2712"></a>
## 42. Head 3 可能主要关注“红色”

第三个 Head 可以粗略理解成：

```text
“这个物品有什么明显属性？”
```

于是可能得到：

```text
小明       1%
红色      85%
雨伞      10%
其他       4%
```

于是：

> Head 3 主要从 `红色` 获取信息。

---

<a id="origin-2735"></a>
## 43. Head 4 可能主要关注“下雨”

第四个 Head 可以粗略理解成：

```text
“为什么需要这把雨伞？”
```

那么它可能主要关注：

```text
下雨了
```

例如：

```text
小明       2%
雨伞       5%
因为      10%
下雨了    80%
其他       3%
```

所以：

\[
\boxed{
\text{同一个“小红”，可以在不同 Head 中拥有完全不同的 Attention 分布。}
}
\]

---

<a id="origin-2769"></a>
## 44. V 也一样可以看成 32 个不同的小投影

整体：

\[
W_V
\in
\mathbb{R}^{4096\times4096}
\]

同样可以写成：

\[
W_V
=
[
W_V^{(1)}
|
W_V^{(2)}
|
\dots
|
W_V^{(32)}
]
\]

其中：

\[
W_V^{(h)}
\in
\mathbb{R}^{4096\times128}
\]

所以：

\[
v_{\text{小明}}^{(1)}
=
x_{\text{小明}}W_V^{(1)}
\]

\[
v_{\text{雨伞}}^{(2)}
=
x_{\text{雨伞}}W_V^{(2)}
\]

等等。

---

<a id="origin-2821"></a>
## 45. V 可以理解成“找到我以后，我真正能给你什么”

例如：

```text
K_小明
```

主要负责帮助判断：

> `小明` 是不是这个 Query 正在寻找的 token？

但是一旦真正匹配到了：

```text
小明
```

真正取回的信息来自：

\[
V_{\text{小明}}
\]

可以粗略理解成包含：

```text
这是小明
他是一个人物
他刚刚执行了递雨伞这个动作
他和小红发生了直接交互
...
```

同理：

```text
K_雨伞
```

负责帮助判断：

> “雨伞是不是我要找的物品？”

而：

\[
V_{\text{雨伞}}
\]

真正提供的是：

```text
这是雨伞
它是被递出去的物品
它与红色这个属性相关
...
```

所以可以直接记：

\[
\boxed{
Q：
“我要找什么？”
}
\]

\[
\boxed{
K：
“我是不是你要找的？”
}
\]

\[
\boxed{
V：
“如果你选中了我，这是我真正提供给你的信息。”
}
\]

---

<a id="origin-2905"></a>
## 46. Q、K、V 都可以理解成一组“小投影器”

对于 Head 1：

```text
完整 X
4096维
   │
   ├── W_Q^(1) 4096×128 → Q^(1)
   │
   ├── W_K^(1) 4096×128 → K^(1)
   │
   └── W_V^(1) 4096×128 → V^(1)
```

对于 Head 2：

```text
完整 X
4096维
   │
   ├── W_Q^(2) 4096×128 → Q^(2)
   │
   ├── W_K^(2) 4096×128 → K^(2)
   │
   └── W_V^(2) 4096×128 → V^(2)
```

一直到 Head 32。

所以：

```text
                         完整 X
                        [4096维]
                            │
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
       Head 1            Head 2          ... Head 32
          │                 │                 │
     ┌────┼────┐       ┌────┼────┐       ┌────┼────┐
     ↓    ↓    ↓       ↓    ↓    ↓       ↓    ↓    ↓
    WQ   WK   WV      WQ   WK   WV      WQ   WK   WV
     ↓    ↓    ↓       ↓    ↓    ↓       ↓    ↓    ↓
    Q1   K1   V1      Q2   K2   V2      Q32  K32  V32
```

每个小投影：

\[
4096\rightarrow128
\]

---

<a id="origin-2960"></a>
## 47. 所以“4096×4096 变成 32 个 4096×128”这个理解是对的

从线性代数角度：

\[
W_Q
\in
\mathbb{R}^{4096\times4096}
\]

确实可以看成：

\[
32
\]

个：

\[
4096\times128
\]

的小投影并行工作。

K/V 同理。

所以完全可以建立这样的直觉：

\[
\boxed{
\text{一个大投影器}
\rightarrow
\text{32 个不同的小投影器}
}
\]

但更加准确的词应该是：

\[
\boxed{
\text{线性投影}
}
\]

而不是完整的“神经网络”。

因为：

\[
W_Q^{(h)}
\]

本质上只是 Linear Layer 的一部分，没有激活函数，也没有多层结构。

---

<a id="origin-3016"></a>
## 48. 每个小投影为什么有意义？

因为：

\[
W_Q^{(1)}
\neq
W_Q^{(2)}
\]

所以它们可以从同一个完整：

\[
4096
\]

维 X 中提取不同的东西。

例如：

```text
Head 1：

“小红现在想知道：
是谁把东西给我的？”
```

而：

```text
Head 2：

“小红现在想知道：
给我的是什么东西？”
```

再比如：

```text
Head 3：

“这个东西有什么属性？”
```

以及：

```text
Head 4：

“为什么发生这件事？”
```

所以：


**不是把一个问题切成 32 份，
而是让 32 个不同的小投影器
对同一份完整材料提出不同的问题。**



---

<a id="origin-3079"></a>
## 49. 那把 4096 压成 128，不还是有信息损失吗？

如果只看一个 Head：

\[
4096
\rightarrow
128
\]

确实属于降维。

所以：

\[
\boxed{
\text{单个 Head 不可能完整保留原始 4096 维中的所有细节。}
}
\]

可以说：

\[
\boxed{
\text{单个 Head 存在信息压缩。}
}
\]

但有两个非常重要的地方。

---

<a id="origin-3111"></a>
## 50. 第一：128 维不是直接从 X 中截出来的

它是：

\[
xW_Q^{(h)}
\]

或者：

\[
xW_K^{(h)}
\]

或者：

\[
xW_V^{(h)}
\]

所以：

\[
\boxed{
\text{这 128 维的每一个维度，都可以依赖完整的 4096 维 X。}
}
\]

例如 Head 1 虽然最终只有 128 维，

但是这 128 维可以从整个：

```text
小红当前知道的全部上下文信息
```

中提炼出：

```text
“谁把东西给我？”
```

相关的表示。

因此最准确的说法是：

\[
\boxed{
\text{信息来源是完整的，但表示是压缩的。}
}
\]

---

<a id="origin-3165"></a>
## 51. 第二：我们并不是只有一个 128 维 Head

我们有：

\[
32
\]

个 Head。

所以：

\[
32\times128
=
4096
\]

整体来看：

\[
4096
\rightarrow
32\times128
=
4096
\]

并没有把整个 Attention 的总表示维度压缩成：

\[
128
\]

更准确地说：

\[
\boxed{
\text{把一个大的 4096 维表示，
重新组织成 32 个不同的 128 维特征子空间。}
}
\]

---

<a id="origin-3210"></a>
## 52. 为什么这样比单头灵活？

如果只有一个 Head，

那么面对：

```text
小明把一把红色雨伞递给小红，因为外面下雨了。
```

可能只有一套Softmax后的比例：

```text
小明      87.7%
红色       2.4%
雨伞       6.6%
递给       4.9%
小红       3.3%
其他       2.0%
```

接下来真正取信息时计算：

$$
o_{\text{小红}}^{(1)}
=
0.807v_{\text{小明}}^{(1)}
+
0.066v_{\text{雨伞}}^{(1)}
+
0.049v_{\text{递给}}^{(1)}
+
0.033v_{\text{小红}}^{(1)}
+
0.024v_{\text{红色}}^{(1)}
+
0.020v_{\text{其他}}^{(1)}
$$

因此这个 Head 得到的输出中：

```text
绝大多数信息来自“小明”
```


然后所有：

\[
4096
\]

维信息都按照这一套权重提取。

这意味着：

```text
“是谁递东西？”
“递的是什么？”
“是什么颜色？”
“为什么发生？”
```

都只能共用同一套注意力分布。

这显然不够灵活。

---

<a id="origin-3279"></a>
### 52.1 多头则可以


而不同 Head 因为拥有不同的 \(Q/K\) 投影，所以即使面对同一个“小红”，经过 Softmax 后也可以得到完全不同的权重。

例如：

我们现在观察：

```text
小红
```

为了简单，假设只看 3 个 Head：

```text
Head 1：关注“谁递给小红？”
Head 2：关注“递给小红什么？”
Head 3：关注“这个东西是什么颜色？”
```


<a id="origin-3301"></a>
## 53. 同一个 token，在不同 Head 中会产生不同的 V

以“小明”为例。

它原来的 hidden state 是：

\[
x_{\text{小明}}
\in
\mathbb{R}^{4096}
\]

在 Multi-Head Attention 中，不同 Head 有不同的 Value 投影矩阵：

\[
W_V^{(1)},
W_V^{(2)},
W_V^{(3)}
\]

因此，同一个：

```text
小明
```

会在不同 Head 中得到不同的 Value：

\[
v_{\text{小明}}^{(1)}
=
x_{\text{小明}}W_V^{(1)}
\]

\[
v_{\text{小明}}^{(2)}
=
x_{\text{小明}}W_V^{(2)}
\]

\[
v_{\text{小明}}^{(3)}
=
x_{\text{小明}}W_V^{(3)}
\]

所以：

\[
v_{\text{小明}}^{(1)}
\neq
v_{\text{小明}}^{(2)}
\neq
v_{\text{小明}}^{(3)}
\]

因为：

\[
W_V^{(1)}
\neq
W_V^{(2)}
\neq
W_V^{(3)}
\]

可以画成：

```text
                    完整 x_小明
                      4096维
                         │
         ┌───────────────┼───────────────┐
         ↓               ↓               ↓
      W_V^(1)         W_V^(2)         W_V^(3)
      4096×128        4096×128        4096×128
         ↓               ↓               ↓
   V_小明^(1)       V_小明^(2)       V_小明^(3)
      128维             128维             128维
```

因此：

> **同一个 token，在不同 Head 中会有不同的 V 表示。**

---

<a id="origin-3388"></a>
## 54. 每个 Head 都有自己的一整套 V

不仅“小明”有多个 V。

句子里的每一个 token，在每一个 Head 中都有自己的 V。

例如 Head 1：

```text
V_小明^(1)
V_红色^(1)
V_雨伞^(1)
V_递给^(1)
V_小红^(1)
V_下雨^(1)
...
```

Head 2：

```text
V_小明^(2)
V_红色^(2)
V_雨伞^(2)
V_递给^(2)
V_小红^(2)
V_下雨^(2)
...
```

Head 3：

```text
V_小明^(3)
V_红色^(3)
V_雨伞^(3)
V_递给^(3)
V_小红^(3)
V_下雨^(3)
...
```

所以：

\[
V^{(1)},V^{(2)},V^{(3)}
\]

并不是三个单独的向量，而是三个 Head 各自的一整套 Value。

---

<a id="origin-3440"></a>
## 55. Head 1：先算 Softmax，再对这一组 V 加权求和

假设 Head 1 学到的问题可以粗略理解成：

```text
“是谁把东西递给小红？”
```

对于“小红”的 Query：

\[
q_{\text{小红}}^{(1)}
\]

它会和 Head 1 中所有 token 的 Key 匹配：

\[
q_{\text{小红}}^{(1)}
(k_{\text{小明}}^{(1)})^T
\]

\[
q_{\text{小红}}^{(1)}
(k_{\text{雨伞}}^{(1)})^T
\]

等等。

经过 Softmax 后，假设得到：

```text
小明      80%
雨伞      10%
递给       5%
红色       2%
小红       3%
```

注意：

> 这套 Softmax 权重接下来不是拿来乘 K，而是拿来乘 V。

于是 Head 1 的输出为：

\[
O_{\text{小红}}^{(1)}
=
0.80V_{\text{小明}}^{(1)}
+
0.10V_{\text{雨伞}}^{(1)}
+
0.05V_{\text{递给}}^{(1)}
+
0.02V_{\text{红色}}^{(1)}
+
0.03V_{\text{小红}}^{(1)}
\]

也就是：

```text
80% × V_小明^(1)
+
10% × V_雨伞^(1)
+
 5% × V_递给^(1)
+
 2% × V_红色^(1)
+
 3% × V_小红^(1)
        ↓
      相加
        ↓
   O_小红^(1)
```

因此：

\[
O_{\text{小红}}^{(1)}
\in
\mathbb{R}^{128}
\]

这个 128 维向量中，大部分信息来自“小明”。

**不要忘记，这 128 维并不是只截取了原始 hidden state \(x\) 的一小部分，而是由完整的 \(x\) 经过线性投影得到的，因此它的每一个维度都可以综合利用原始 hidden state 中的全部 4096 维信息，只是最终被压缩成了一个 128 维表示。**

---

<a id="origin-3530"></a>
## 56. Head 2：又用另一套 Softmax 权重加自己的 V

Head 2 粗略可以理解成在问：

```text
“递给小红的是什么？”
```

那么它经过自己的 Q/K 匹配和 Softmax 后，可能得到：

```text
小明       5%
雨伞      85%
递给       5%
红色       3%
小红       2%
```

于是：

\[
O_{\text{小红}}^{(2)}
=
0.05V_{\text{小明}}^{(2)}
+
0.85V_{\text{雨伞}}^{(2)}
+
0.05V_{\text{递给}}^{(2)}
+
0.03V_{\text{红色}}^{(2)}
+
0.02V_{\text{小红}}^{(2)}
\]

得到：

\[
O_{\text{小红}}^{(2)}
\in
\mathbb{R}^{128}
\]

这个 Head 的输出中，大部分信息来自“雨伞”。

---

<a id="origin-3576"></a>
## 57. Head 3：同样如此

Head 3 粗略可以理解成在问：

```text
“这个东西是什么颜色？”
```

Softmax 后可能得到：

```text
小明       2%
雨伞      15%
红色      78%
递给       2%
小红       3%
```

于是：

\[
O_{\text{小红}}^{(3)}
=
0.02V_{\text{小明}}^{(3)}
+
0.15V_{\text{雨伞}}^{(3)}
+
0.78V_{\text{红色}}^{(3)}
+
0.02V_{\text{递给}}^{(3)}
+
0.03V_{\text{小红}}^{(3)}
\]

得到：

\[
O_{\text{小红}}^{(3)}
\in
\mathbb{R}^{128}
\]

这个 Head 的输出主要包含“红色”相关的信息。

---

<a id="origin-3622"></a>
## 58. 所以每个 Head 内部真正发生的是“V 的加权求和”

可以统一写成：

\[
O^{(h)}
=
\operatorname{Softmax}
\left(
\frac{Q^{(h)}(K^{(h)})^T}
{\sqrt{d_{head}}}
\right)
V^{(h)}
\]

其中：

\[
\operatorname{Softmax}
\left(
\frac{Q^{(h)}(K^{(h)})^T}
{\sqrt{d_{head}}}
\right)
\]

负责产生：

```text
每个 token 应该占多少比例
```

而：

\[
V^{(h)}
\]

负责提供：

```text
真正要取回的信息
```

所以可以记成：

\[
\boxed{
QK^T
\rightarrow
Softmax
\rightarrow
Attention\ Weight
\rightarrow
对V加权求和
}
\]

---

<a id="origin-3681"></a>
## 59. 可以把整个机制理解成“32 个小专家”

整个过程可以理解成：

```text
                       完整 X
                      [4096维]
                         ↓

         所有专家都看到完整的 4096维信息

                         ↓

   ┌────────────┬────────────┬────────────┬────────────┐
   ↓            ↓            ↓            ↓
Head 1       Head 2       Head 3       Head 4       ...
4096→128     4096→128     4096→128     4096→128
   ↓            ↓            ↓            ↓

问：
“谁递的？”   “递什么？”   “什么颜色？”   “为什么？”

   ↓            ↓            ↓            ↓

看小明         看雨伞         看红色          看下雨
```

所以可以把 Multi-Head Attention 粗略理解成：

\[
\boxed{
32\text{ 个并行的小投影专家}
}
\]

每个专家都看完整输入，

但是每个专家学到了不同的：

\[
Q/K/V
\]

投影方式和不同的 Attention 模式。

---

<a id="origin-3728"></a>
## 60. 32 个 Head 得到结果以后怎么办？

假设：

```text
Head 1：
主要从小明取回信息

Head 2：
主要从雨伞取回信息

Head 3：
主要从红色取回信息

Head 4：
主要从下雨取回信息
```

每个 Head 最后输出：

\[
128
\]

维。

例如：

\[
o_{\text{小红}}^{(1)}
\in
\mathbb{R}^{128}
\]

\[
o_{\text{小红}}^{(2)}
\in
\mathbb{R}^{128}
\]

……

一共有：

\[
32
\]

个。

然后：

\[
Concat
\]

起来：

\[
O_{concat}
=
[
O^{(1)}
|
O^{(2)}
|
\dots
|
O^{(32)}
]
\]

得到：

\[
32\times128
=
4096
\]

维。

---

<a id="origin-3812"></a>
## 61. 为什么 Concat 以后还需要 \(W_O\)？

因为简单 Concat 后，可以粗略理解成：

```text
[
Head 1 找到的“小明相关信息”
|
Head 2 找到的“雨伞相关信息”
|
Head 3 找到的“红色相关信息”
|
Head 4 找到的“下雨相关信息”
|
...
]
```

这些信息虽然已经放在同一个 4096 维向量里，

但仍然是分块组织的。

**也就是说，前 128 维可能主要来自 Head 1，中间某 128 维来自 Head 2，后面的维度又来自其他 Head；这些不同 Head 提取到的信息此时只是“并排放在一起”，彼此之间还没有充分混合。**

**因此还需要通过 \(W_O\) 做一次线性变换，让不同 Head 提取到的信息能够跨分块重新组合，从而形成统一的 4096 维表示。**

所以后面还需要：

\[
W_O
\in
\mathbb{R}^{4096\times4096}
\]

计算：

\[
Y
=
O_{concat}W_O
\]

---

<a id="origin-3856"></a>
## 62. \(W_O\) 可以理解成“最后把所有调查结果汇总起来”

前面：

```text
Head 1：
找到“小明”

Head 2：
找到“雨伞”

Head 3：
找到“红色”

Head 4：
找到“下雨”
```

这些 Head 都独立完成了自己的任务。

现在：

\[
W_O
\]

负责重新组合这些信息。

于是最终关于：

```text
小红
```

的新 hidden state 可以同时包含：

> 小明把东西递给了小红；

> 递的是一把雨伞；

> 这把雨伞是红色的；

> 之所以需要雨伞，是因为外面下雨了。

因此：

\[
\boxed{
W_O
=
\text{把多个 Head 的独立调查结果重新融合}
}
\]

---

<a id="origin-3912"></a>
## 63. 所以整个 Multi-Head Attention 是“先分工，再协作”

完整故事：

```text
一开始只有一个 4096维 Head
        ↓
只能产生 1 套 Attention
        ↓
但理解一句话时，
我们希望同时寻找很多不同的信息
        ↓
想做 32 个 Head
        ↓
最直接：
32 个 Head 每个都4096维
        ↓
参数量、计算量约 ×32
        ↓
太贵
        ↓
保持总投影维度 4096 不变
        ↓
4096 / 32 = 128
        ↓
做 32 个 128维 Head
        ↓
但每个 Head 都读取完整4096维 X
        ↓
通过不同 W_Q / W_K / W_V
各自提取不同的128维表示
        ↓
32种 Q 表示
32种 K 表示
32种 V 表示
        ↓
32种不同 Q/K 匹配空间
        ↓
32张 Attention Matrix
        ↓
32套 Softmax 权重
        ↓
不同 Head 从不同 token 中找信息
        ↓
例如：
Head 1 找“小明”
Head 2 找“雨伞”
Head 3 找“红色”
Head 4 找“下雨”
        ↓
32 × 128维输出
        ↓
Concat
        ↓
4096维
        ↓
W_O
        ↓
把所有 Head 的信息重新融合
```

---

<a id="origin-3975"></a>
## 64. 为什么总参数量基本没变？

单头：

\[
W_Q
\in
\mathbb{R}^{4096\times4096}
\]

多头：

\[
32
\]

个：

\[
W_Q^{(h)}
\in
\mathbb{R}^{4096\times128}
\]

总参数量：

\[
32\times4096\times128
\]

因为：

\[
32\times128
=
4096
\]

所以：

\[
32\times4096\times128
=
4096\times4096
\]

因此：

\[
\boxed{
\text{Q 投影总参数量没有变}
}
\]

K/V 同理。

所以：

\[
\boxed{
\text{Head 数量增加，但总投影容量没有增加。}
}
\]

---

<a id="origin-4041"></a>
## 65. 参数量没变，为什么表达能力却更丰富？

因为真正增加的不是：

\[
\text{总维度}
\]

也不是：

\[
\text{总参数量}
\]

而是：

\[
\boxed{
\text{独立的 Attention 模式数量}
}
\]

单头：

```text
只有 1 套 Attention

“谁递的？”
“递什么？”
“什么颜色？”
“为什么？”

全部只能共享同一套权重
```

而多头：

```text
Head 1：
一套 Attention
→ 找小明

Head 2：
另一套 Attention
→ 找雨伞

Head 3：
另一套 Attention
→ 找红色

Head 4：
另一套 Attention
→ 找下雨

...
```

因此：

\[
\boxed{
\text{相同的总参数，
被组织成了更多独立的信息匹配和信息路由机制。}
}
\]

---

<a id="origin-4109"></a>
## 66. 单头和多头的本质区别

单头：

```text
完整4096维
    ↓
1个Q空间
1个K空间
1个V空间
    ↓
1张 Attention Matrix
    ↓
1套 Softmax
    ↓
所有4096维信息
共用同一种关注策略
```

多头：

```text
完整4096维
    ↓
32个不同的小Q投影
32个不同的小K投影
32个不同的小V投影
    ↓
32个不同的Q/K匹配空间
    ↓
32张 Attention Matrix
    ↓
32套 Softmax
    ↓
不同 Head 可以寻找不同信息
    ↓
例如：
小明 / 雨伞 / 红色 / 下雨 / ...
    ↓
Concat
    ↓
W_O
    ↓
重新融合成4096维
```

---

<a id="origin-4157"></a>
## 67. 最终可以这样理解 Multi-Head Attention

最开始：

\[
\boxed{
1\text{ 个 }4096\text{ 维 Head}
}
\]

我们希望：

\[
\boxed{
32\text{ 个不同的 Attention 视角}
}
\]

如果直接复制成：

\[
32\times4096
\]

参数量太贵。

所以改成：

\[
\boxed{
32\times128
}
\]

保持：

\[
32\times128=4096
\]

总表示维度和总投影参数量基本不变。

但是每个 Head：

\[
\boxed{
\text{都读取完整的 X}
}
\]

并通过不同的：

\[
W_Q^{(h)},W_K^{(h)},W_V^{(h)}
\]

学习自己的低维表示。

于是可以粗略理解成：

```text
Head 1：
问“谁把东西给小红？”
→ 找小明

Head 2：
问“给小红的是什么？”
→ 找雨伞

Head 3：
问“雨伞是什么颜色？”
→ 找红色

Head 4：
问“为什么需要雨伞？”
→ 找下雨

...
```

最后：

\[
Concat+W_O
\]

把所有 Head 找回来的信息重新组合。

<a id="origin-4245"></a>
## 68. 投影和神经网络有什么区别？

可以简单理解：

**线性投影擅长“重新组合已有特征”；
非线性网络可以“根据条件产生更复杂的新特征”。**

<a id="origin-4252"></a>
## 69. 投影：通常就是一次线性变换

例如：

\[
y=xW
\]

或者：

\[
y=xW+b
\]

在代码里通常就是：

```python
nn.Linear(...)
```

例如：

\[
4096
\rightarrow
128
\]

可以写成：

\[
q=xW_Q
\]

其中：

\[
W_Q\in\mathbb{R}^{4096\times128}
\]

它做的事情就是：

> 把原来的 4096 维表示，重新组合成 128 维表示。

所以投影本质上是：

\[
\boxed{
\text{一次线性映射}
}
\]

---

<a id="origin-4306"></a>
## 70. 神经网络通常是多层 + 非线性

例如一个简单的 MLP：

```text
输入
 ↓
Linear
 ↓
ReLU / SiLU
 ↓
Linear
 ↓
输出
```

数学上：

\[
h=SiLU(xW_1)
\]

然后：

\[
y=hW_2
\]

这里不仅有多个矩阵：

\[
W_1,W_2
\]

还有非线性激活：

\[
SiLU
\]

所以它能够学习更加复杂的非线性关系。

---

<a id="origin-4350"></a>
## 71. 两者最简单的区别

投影：

```text
x
↓
Linear
↓
y
```

也就是：

\[
\boxed{
y=xW
}
\]

神经网络：

```text
x
↓
Linear
↓
Activation
↓
Linear
↓
Activation
↓
...
↓
y
```

所以可以简单记成：

\[
\boxed{
\text{投影 = 一层线性变换}
}
\]

\[
\boxed{
\text{神经网络 = 多层线性变换 + 非线性激活}
}
\]

---

<a id="origin-4404"></a>
## 72. 投影虽然简单，但也会训练

比如：

\[
q=xW_Q
\]

其中：

\[
W_Q
\]

虽然只是一个投影矩阵，但它依然是：

\[
\boxed{
\text{可训练参数}
}
\]

反向传播会更新：

\[
W_Q
\]

所以：

> 投影的计算形式很简单，但“怎么投影”是模型训练出来的。

---

<a id="origin-4438"></a>
## 73. 在 Transformer 里

Q/K/V：

\[
Q=XW_Q
\]

\[
K=XW_K
\]

\[
V=XW_V
\]

这里的：

\[
W_Q,W_K,W_V
\]

都是：

\[
\boxed{
\text{线性投影}
}
\]

而 FFN：

```text
Linear
↓
SiLU
↓
Linear
```

才更像我们通常说的：

\[
\boxed{
\text{神经网络}
}
\]

---

<a id="origin-4488"></a>
## 74. 一句话总结

\[
\boxed{
\text{投影：一次矩阵乘法，负责重新表示特征}
}
\]

\[
\boxed{
\text{神经网络：多层矩阵变换 + 非线性激活，负责学习复杂关系}
}
\]

---


<a id="origin-4505"></a>
## 75. 但还有一个更深的问题

你可能马上会继续问：

> 好，我知道参数不一样了，但是为什么这些不同参数最后就能学出不同的“语义”？

这就要进入训练过程。

---

<a id="origin-4515"></a>
## 76. 训练刚开始时，其实每个 Head 什么都不会

刚初始化模型的时候：

```math
W_Q^{(1)}
```

```math
W_Q^{(2)}
```

```math
W_K^{(1)}
```

```math
W_K^{(2)}
```

……

基本都是随机初始化的。

所以训练刚开始：

```text
Head 1
并不知道什么叫语法。

Head 2
也不知道什么叫指代。

Head 3
更不知道什么叫长距离依赖。
```

它们一开始本质就是：

> **很多组随机的线性投影。**

---

<a id="origin-4558"></a>
## 77. 这里有一个极其重要的机制：随机初始化打破对称性

假设有两个 Head。

如果非常极端地让：

```math
W_Q^{(1)}
=
W_Q^{(2)}
```

```math
W_K^{(1)}
=
W_K^{(2)}
```

```math
W_V^{(1)}
=
W_V^{(2)}
```

而且后续所有条件都完全对称，

那么：

```text
Head 1 的输出
=
Head 2 的输出
```

它们收到的梯度也可能完全相同。

于是：

```text
训练一次以后还是一样
训练一万次以后仍然一样
```

那 Multi-Head 就失去意义了。

---

而真实训练中：

```math
W_Q^{(1)}
\neq W_Q^{(2)}
```

从初始化时就成立。

例如：

```math
W_Q^{(1)}
=
0.013,-0.021,\cdots
```

而：

```math
W_Q^{(2)}
=
-0.008,0.017,\cdots
```

只是这么一点点随机差异，

就会造成：

```math
Q^{(1)}\neq Q^{(2)}
```

然后：

```math
K^{(1)}\neq K^{(2)}
```

于是：

```math
Q^{(1)}K^{(1)T}
\neq
Q^{(2)}K^{(2)T}
```

Attention 分布不同：

```math
A^{(1)}\neq A^{(2)}
```

最后 Head 输出不同：

```math
H^{(1)}\neq H^{(2)}
```

这就打破了两个 Head 之间原本可能存在的“对称”。

这个过程叫：

> **Symmetry Breaking，打破对称性。**

它是神经网络能够让多个神经元、多个 Head 学到不同东西的重要基础。

---

<a id="origin-4674"></a>
## 78. 接下来真正让它们产生分工的是 Loss

假设训练样本：

```text
The cat sat on the mat because it was tired.
```

模型需要预测某个下一个 token。

最终经过很多 Transformer 层以后，模型产生概率：

```math
P(y|x)
```

然后计算 Cross Entropy：

```math
L=-\log P(y_{\text{true}})
```

假设模型预测错了。

Loss 很大。

反向传播就开始了：

```text
Loss
 ↓
LM Head
 ↓
最后一个 Transformer Block
 ↓
Attention
 ↓
每个 Head
 ↓
Q/K/V 投影参数
```

---

<a id="origin-4718"></a>
## 79. Head 1 和 Head 2 收到的梯度为什么会不一样？

因为：

```text
Head 1 当前输出的东西
和
Head 2 当前输出的东西
本来就不一样。
```

例如：

```math
H^{(1)}
=
A^{(1)}V^{(1)}
```

而：

```math
H^{(2)}
=
A^{(2)}V^{(2)}
```

因为参数不同：

```math
A^{(1)}\neq A^{(2)}
```

```math
V^{(1)}\neq V^{(2)}
```

所以：

```math
H^{(1)}\neq H^{(2)}
```

而最终：

```math
H=
\operatorname{Concat}
(
H^{(1)},H^{(2)},...
)
W_O
```

因此 Head 1 和 Head 2 通过不同路径影响最终 Loss。

反向传播后：

```math
\frac{\partial L}
{\partial W_Q^{(1)}}
```

通常不会等于：

```math
\frac{\partial L}
{\partial W_Q^{(2)}}
```

所以它们更新方向不同。

---

<a id="origin-4792"></a>
## 80. 把这个过程真正写出来

假设：

```math
H^{(1)}
=
\operatorname{Attention}
(
Q^{(1)},K^{(1)},V^{(1)}
)
```

其中：

```math
Q^{(1)}=XW_Q^{(1)}
```

最终 Loss：

```math
L
```

那么链式法则：

```math
\frac{\partial L}
{\partial W_Q^{(1)}}
=
\frac{\partial L}
{\partial H^{(1)}}
\frac{\partial H^{(1)}}
{\partial Q^{(1)}}
\frac{\partial Q^{(1)}}
{\partial W_Q^{(1)}}
```

而对于 Head 2：

```math
\frac{\partial L}
{\partial W_Q^{(2)}}
=
\frac{\partial L}
{\partial H^{(2)}}
\frac{\partial H^{(2)}}
{\partial Q^{(2)}}
\frac{\partial Q^{(2)}}
{\partial W_Q^{(2)}}
```

由于：

```math
H^{(1)}\neq H^{(2)}
```

而且：

```math
Q^{(1)}\neq Q^{(2)}
```

因此两条计算路径完全不一样。

所以：

```math
\frac{\partial L}
{\partial W_Q^{(1)}}
\neq
\frac{\partial L}
{\partial W_Q^{(2)}}
```

于是更新：

```math
W_Q^{(1)}
\leftarrow
W_Q^{(1)}
-
\eta
\frac{\partial L}
{\partial W_Q^{(1)}}
```

而：

```math
W_Q^{(2)}
\leftarrow
W_Q^{(2)}
-
\eta
\frac{\partial L}
{\partial W_Q^{(2)}}
```

两个 Head 就开始向不同方向走。

---

<a id="origin-4897"></a>
## 81. 用一个非常直观的训练故事来理解

假设模型经常遇到：

```text
The dog chased the cat because it was scared.
```

```text
The boy picked up the book because it was useful.
```

```text
The animal couldn't walk because it was injured.
```

模型为了正确预测后面的词，

经常需要搞清楚：

```text
it 到底指谁？
```

训练过程中，假设偶然有一个 Head：

```text
Head 3
```

因为随机初始化的原因，

它恰好开始稍微更多地关注：

```text
代词前面的名词。
```

例如：

```text
it
↓
dog
```

或者：

```text
it
↓
book
```

这种 Attention Pattern 偶然对预测有帮助。

那么：

```text
预测更准确
↓
Loss 更低
```

反向传播就会告诉 Head 3：

> 你现在这种参数方向是有用的。

于是梯度更新会进一步强化这种行为。

---

经过大量类似数据以后：

```text
偶然的一点点偏向
↓
对任务有帮助
↓
梯度强化
↓
偏向越来越明显
↓
形成稳定模式
```

最后就可能出现：

```text
这个 Head 对某类指代关系特别敏感。
```

---

<a id="origin-4991"></a>
## 82. 另一个 Head 为什么不会也学成一模一样？

因为它从一开始的位置就不一样。

例如 Head 7 因为随机初始化：

```text
一开始恰好更容易关注前一个动词。
```

如果这种模式也有助于预测：

```text
Head 7 的这一方向也会被梯度强化。
```

所以训练慢慢可能形成：

```text
Head 3：
对实体/指代关系比较敏感

Head 7：
对谓词/动作关系比较敏感
```

这有点像：

```text
两个学生最开始随机尝试不同的解题方法。

一种方法在某类题上越来越好，
另一种方法在另一类题上越来越好。

最后自然形成了不同擅长方向。
```

没人事先规定谁负责什么。

---

<a id="origin-5032"></a>
## 83. 为什么模型“愿意”保留多个不同 Head？

因为最终输出会把所有 Head 拼起来。

例如：

```math
H
=
\operatorname{Concat}
(
H_1,H_2,H_3,H_4
)
```

然后：

```math
O=HW_O
```

也就是说：

```text
Head 1 提供一部分信息
Head 2 提供另一部分信息
Head 3 再提供一些信息
Head 4 再提供一些信息
```

最后模型把它们组合起来。

如果：

```text
Head 1 和 Head 2 完全一样
```

那么两者提供的是重复信息。

对于固定的模型容量来说：

```text
重复信息通常没有充分利用参数。
```

而如果：

```text
Head 1 提供 A

Head 2 提供 B
```

最终模型可以同时使用：

```text
A + B
```

更有机会降低 Loss。

所以优化过程存在一种自然压力：

> **让不同 Head 学到互补的信息可能比所有 Head 完全重复更有用。**

---

<a id="origin-5100"></a>
## 84. 但是一定要非常严谨：并不是每个 Head 都一定高度专业化

这里千万不能讲成：

```text
Head 1 一定负责主语

Head 2 一定负责宾语

Head 3 一定负责指代
```

这是不准确的。

真实的大模型里面：

```text
有些 Head 会明显表现出某种模式

有些 Head 同时承担多种信息

有些 Head 功能相近

有些 Head 存在冗余

甚至有些 Head 删除以后影响也不大
```

所以更准确的说法是：

> Multi-Head Attention 提供了多个独立的表示子空间，使训练过程有机会形成不同、互补的 Attention Pattern。

而不是：

> 每一个 Head 都会自动变成一个人类可以清楚解释的语言学模块。

---

<a id="origin-5138"></a>
## 85. Query Head 到底学的是什么？

现在再进一步区分 Q、K、V。

一个 Attention Head：

```math
A
=
\operatorname{softmax}(QK^T)
```

其中：

```math
Q=XW_Q
```

```math
K=XW_K
```

---

可以粗略理解：

```text
Q：
我正在寻找什么特征？

K：
我可以被什么类型的问题匹配？

V：
如果你关注我，我实际提供什么信息？
```

所以某个 Query Head：

```math
Q^{(1)}
```

通过训练，其实是在学习：

> **当前 token 应该以什么方式描述自己的“信息需求”。**

例如，同一个 `it`：

```text
Head 1 的 Query：
可能更加突出“我需要找到指代对象”的特征

Head 2 的 Query：
可能更加突出“我需要寻找相关谓词”的特征

Head 3 的 Query：
可能更加突出“我需要关注附近信息”的特征
```

再次强调：

这些不是人为写死的语义。

只是为了帮助理解训练后的投影空间可能形成怎样的功能。

---

<a id="origin-5206"></a>
## 86. 为什么同一个 token 可以有多个 Query？

现在这件事情应该很好理解了。

同一个：

```math
x_{\text{it}}
```

里面本身就包含大量混合信息。

例如粗略理解成：

```text
it

里面同时包含：

“我是代词”
“我在这个位置”
“我的前面出现了 because”
“我参与当前句法结构”
“我和某些实体可能有关”
……
```

Head 1 使用：

```math
W_Q^{(1)}
```

把其中某些组合投影出来：

```math
Q_{\text{it}}^{(1)}
=
x_{\text{it}}W_Q^{(1)}
```

Head 2 使用：

```math
W_Q^{(2)}
```

投影另一组特征：

```math
Q_{\text{it}}^{(2)}
=
x_{\text{it}}W_Q^{(2)}
```

所以：

```text
不是一个 token 有多个“身份”。

而是：

同一个复杂 hidden state
可以从多个不同方向进行投影。
```

---


<a id="origin-5275"></a>
## 87. 一个更准确的 MHA 图

不要只画成：

```text
          → Head 1
Input →   → Head 2
          → Head 3
```

更准确的理解应该是：

```text
                        ┌→ WQ¹ → Q¹ ─┐
                        │             │
                        ├→ WK¹ → K¹ ─┼→ Attention Head 1
                        │             │
                        └→ WV¹ → V¹ ─┘

                        ┌→ WQ² → Q² ─┐
                        │             │
hidden state X ─────────├→ WK² → K² ─┼→ Attention Head 2
                        │             │
                        └→ WV² → V² ─┘

                        ┌→ WQ³ → Q³ ─┐
                        │             │
                        ├→ WK³ → K³ ─┼→ Attention Head 3
                        │             │
                        └→ WV³ → V³ ─┘
```

由于：

```math
W_Q^{(1)},W_K^{(1)},W_V^{(1)}
```

和：

```math
W_Q^{(2)},W_K^{(2)},W_V^{(2)}
```

都是独立可学习参数，

所以每个 Head 可以形成自己的：

```text
Query 空间
Key 空间
Value 空间
```

---

<a id="origin-5331"></a>
## 88. 注意：一个 Head 真正学习的是 Q 和 K 的“匹配规则”

这一点特别关键。

例如 Head 1 的 Attention Score：

```math
S_{ij}^{(1)}
=
Q_i^{(1)}
K_j^{(1)T}
```

展开：

```math
S_{ij}^{(1)}
=
(x_iW_Q^{(1)})
(x_jW_K^{(1)})^T
```

可以继续写成：

```math
S_{ij}^{(1)}
=
x_i
W_Q^{(1)}
W_K^{(1)T}
x_j^T
```

所以 Head 1 实际上学习了一套：

```math
W_Q^{(1)}W_K^{(1)T}
```

对应的匹配规则。

而 Head 2：

```math
S_{ij}^{(2)}
=
x_i
W_Q^{(2)}
W_K^{(2)T}
x_j^T
```

学习的是另一套：

```math
W_Q^{(2)}W_K^{(2)T}
```

因此：

> 不同 Head 本质上可以学习不同的“什么样的 token 关系应该获得高分”的规则。

这比简单说：

> “不同 Head 看不同语义”

更加准确。

---

<a id="origin-5401"></a>
## 89. 举一个直观的抽象例子

假设 Head 1 最终学成：

```text
如果：

当前 token 很像代词

而过去 token 很像实体名词

那么 Attention Score 提高
```

即：

```text
代词 Query
×
实体 Key
→ 高分
```

于是：

```text
it → animal
```

容易得到高 Attention。

---

而 Head 2 可能学成：

```text
如果：

当前 token 和某个过去 token
存在很强的谓词语义关联

那么 Attention Score 提高
```

于是：

```text
it → tired
```

或者：

```text
subject → verb
```

得到更高 Attention。

---

两个 Head 没有收到：

```text
“学习指代”
```

这样的监督标签。

它们只是因为：

```text
这些关系有助于预测下一个 token
```

所以在海量训练中逐渐被保留下来。

---

<a id="origin-5479"></a>
## 90. 整个训练机制压缩成一条完整链条

这是理解 MHA 最关键的一条：

```text
同一个 hidden state X
        ↓
不同 Head 有不同参数
        ↓
WQ¹ / WK¹ / WV¹
WQ² / WK² / WV²
        ↓
随机初始化不同
        ↓
一开始就产生略微不同的 Q/K/V
        ↓
Attention Score 不同
        ↓
Attention Pattern 不同
        ↓
各 Head 对最终预测的影响不同
        ↓
Cross Entropy Loss
        ↓
反向传播
        ↓
各 Head 得到不同梯度
        ↓
参数向不同方向更新
        ↓
训练数十亿/数万亿 token
        ↓
不同 Head 的表示空间逐渐分化
        ↓
某些 Head 对某些关系越来越敏感
        ↓
形成不同、可能互补的 Attention Pattern
```

---

<a id="origin-5520"></a>
## 91. 所以“不同 Head 捕获不同语义”的本质到底是什么？

最严格地说，不应该说：

> Head 内部存在一个叫“语法”的变量。

更准确的说法是：

> **不同 Head 通过独立的 Q/K/V 投影参数，学习不同的特征表示和不同的 token-to-token 匹配函数，因此在某些输入上会产生不同的 Attention Pattern。**

这些 Attention Pattern 有时在人类观察下表现为：

```text
语法关系
实体关系
指代关系
位置关系
局部依赖
长距离依赖
```

所以我们才方便地说：

> 这个 Head “捕获了”某类关系。

---

<a id="origin-5547"></a>
## 92. 现在再回头理解“多个 Query Head”

假设有：

```math
32
```

个 Head。

对于同一个 token：

```text
love
```

实际上产生：

```math
Q_{\text{love}}^{(1)}
```

```math
Q_{\text{love}}^{(2)}
```

```math
Q_{\text{love}}^{(3)}
```

```text
...
```

```math
Q_{\text{love}}^{(32)}
```

为什么可以不一样？

因为：

```math
Q_{\text{love}}^{(h)}
=
x_{\text{love}}
W_Q^{(h)}
```

其中：

```math
W_Q^{(1)}
\neq
W_Q^{(2)}
\neq
\cdots
\neq
W_Q^{(32)}
```

所以：

```text
同一个 love
↓
同一个 hidden state
↓
经过 32 套不同投影
↓
得到 32 个不同 Query 表示
```

这些 Query 可以理解成：

> 当前 token 从 32 个不同的“信息需求空间”向上下文发起查询。

---

<a id="origin-5626"></a>
## 93. 这一点正是后面 GQA 的基础

现在才能真正理解为什么 GQA 会说：

> **保留多个 Query Head，但让多个 Query Head 共享 K/V。**

因为：

```text
Query Head 1
Query Head 2
Query Head 3
```

之所以不同，

核心原因并不只是：

```text
它们拥有不同 K/V。
```

而首先是：

```text
它们自己的 WQ 就不同。
```

所以哪怕：

```text
Q1
Q2
```

使用同一套：

```text
K,V
```

仍然有：

```math
Q^{(1)}K^T
\neq
Q^{(2)}K^T
```

因此依然可以得到：

```text
不同 Attention Score
不同 Attention Distribution
不同信息聚合结果
```

这才给 GQA 提供了可能性。

---

<a id="origin-5687"></a>
## 94. 最后一段总结

为什么不同 Attention Head 可以学习不同的信息？

不是因为：

```text
模型提前给每个 Head 分配了工作。
```

而是因为：

```text
① 每个 Head 有独立的 Q/K/V 投影参数

② 随机初始化使这些参数一开始就不同

③ 不同参数导致不同 Q/K/V

④ 不同 Q/K/V 导致不同 Attention Pattern

⑤ 不同 Head 对最终预测产生不同影响

⑥ 反向传播因此给它们不同梯度

⑦ 长时间训练后参数逐渐分化

⑧ 某些 Head 对某些类型的 token 关系变得更加敏感
```

所以所谓：

> **“不同 Head 捕获不同特征”**

其真正的数学含义是：

```math
W_Q^{(1)},W_K^{(1)},W_V^{(1)}
```

和：

```math
W_Q^{(2)},W_K^{(2)},W_V^{(2)}
```

经过训练后形成了不同的表示空间以及不同的：

```math
QK^T
```

匹配规则。

最核心的一句话就是：

> **Multi-Head 的关键并不是把同一套 Attention 重复算很多遍，而是让多组独立参数通过训练学习多套不同的“如何表示 Query、如何表示 Key、什么样的 Q-K 关系应该获得高分、以及最终应该读取什么 Value”的规则。**

而 Query Head 之所以可以不同，最根本的原因就是：

```math
\boxed{
Q^{(h)}=XW_Q^{(h)}
}
```

其中每个：

```math
W_Q^{(h)}
```

都是不同且可训练的参数。

因此：

```math
\boxed{
Q^{(1)}
\neq
Q^{(2)}
\neq
\cdots
\neq
Q^{(h)}
}
```

这就是后面从 **MHA → GQA** 时，“为什么可以保留很多 Query Head”的真正理论基础。

---

<a id="origin-5779"></a>
## 95. 那为什么代码里看起来是“先生成一个 4096 维 Q，再切成 32 份”？

这是工程实现上的优化。

从数学上，本来完全可以写成：

```math
Q^{(1)}
=
XW_Q^{(1)}
```

```math
Q^{(2)}
=
XW_Q^{(2)}
```

```math
\cdots
```

```math
Q^{(32)}
=
XW_Q^{(32)}
```

其中：

```math
W_Q^{(h)}
\in
\mathbb{R}^{4096\times128}
```

也就是说，本来就是：

```text
32 个独立的 Query Head
```

分别计算。

---

<a id="origin-5825"></a>
## 96. 但是实际代码不想做 32 次小矩阵乘法

GPU 更擅长一次做一个大矩阵乘法。

所以工程上把：

```math
W_Q^{(1)},
W_Q^{(2)},
\dots,
W_Q^{(32)}
```

横向拼起来：

```math
W_Q
=
[
W_Q^{(1)}
|
W_Q^{(2)}
|
\cdots
|
W_Q^{(32)}
]
```

每一个：

```math
W_Q^{(h)}
:
4096\times128
```

一共 32 个。

所以拼起来以后：

```math
W_Q
:
4096\times(32\times128)
```

因为：

```math
32\times128=4096
```

所以：

```math
W_Q
\in
\mathbb{R}^{4096\times4096}
```

---

<a id="origin-5888"></a>
## 97. 然后一次算出所有 Query Head

代码只需要计算：

```math
Q=XW_Q
```

得到：

```math
Q\in\mathbb{R}^{4096}
```

然后 reshape：

```text
4096

↓

32 × 128
```

于是得到：

```text
Q¹
Q²
Q³
...
Q³²
```

---

<a id="origin-5924"></a>
## 98. 这里特别重要：并不是先有一个“大 Query”，然后再硬切

这个理解很容易误导。

不要理解成：

```text
先训练得到：

一个完整的 4096 维 Query

↓

然后人为把它切成 32 块
```

更准确的理解是：

> **本来就设计了 32 个独立的 128 维 Query Head。**

只是为了计算效率：

```text
把 32 个 W_Q 小矩阵
拼成一个大 W_Q
```

然后一次性算出来。

所以：

```math
Q=XW_Q
```

只是：

> 32 个 Query Head 的批量计算版本。

---

<a id="origin-5965"></a>
## 99. 数学上为什么完全等价？

因为：

```math
W_Q
=
[
W_Q^{(1)}
|
W_Q^{(2)}
|
\cdots
|
W_Q^{(32)}
]
```

所以：

```math
XW_Q
=
X
[
W_Q^{(1)}
|
W_Q^{(2)}
|
\cdots
|
W_Q^{(32)}
]
```

根据矩阵乘法：

```math
XW_Q
=
[
XW_Q^{(1)}
|
XW_Q^{(2)}
|
\cdots
|
XW_Q^{(32)}
]
```

而：

```math
XW_Q^{(1)}
=
Q^{(1)}
```

```math
XW_Q^{(2)}
=
Q^{(2)}
```

所以：

```math
\boxed{
Q
=
[
Q^{(1)}
|
Q^{(2)}
|
\cdots
|
Q^{(32)}
]
}
```

因此：

> **所谓“切 Q”，本质上只是把已经属于不同 Head 的结果重新恢复成 Head 维度。**

---

<a id="origin-6054"></a>
## 100. K 和 V 其实完全一样

Query 是这样：

```math
W_Q
=
[
W_Q^{(1)}
|
W_Q^{(2)}
|
\dots
|
W_Q^{(32)}
]
```

Key 也一样：

```math
W_K
=
[
W_K^{(1)}
|
W_K^{(2)}
|
\dots
|
W_K^{(32)}
]
```

Value 也一样：

```math
W_V
=
[
W_V^{(1)}
|
W_V^{(2)}
|
\dots
|
W_V^{(32)}
]
```

所以标准 MHA 中：

```text
Q：

4096
↓
32 × 128


K：

4096
↓
32 × 128


V：

4096
↓
32 × 128
```

---

<a id="origin-6130"></a>
## 101. 所以标准 MHA 其实非常对称

MHA 中：

```math
N_Q
=
N_K
=
N_V
=
32
```

每个 Head：

```math
d_{\text{head}}=128
```

所以：

```text
Head 1：

Q¹ [128]
K¹ [128]
V¹ [128]


Head 2：

Q² [128]
K² [128]
V² [128]


...


Head 32：

Q³² [128]
K³² [128]
V³² [128]
```

这才是完整的 Multi-Head Attention。

---

<a id="origin-6181"></a>
## 102. 到 GQA 的时候才发生不对称

现在才可以自然引出 GQA。

标准 MHA：

```text
Q1 ↔ K1,V1

Q2 ↔ K2,V2

Q3 ↔ K3,V3

Q4 ↔ K4,V4
```

每个 Query Head 都有自己的 K/V Head。

所以：

```math
N_Q=N_{KV}
```

例如：

```math
N_Q=32
```

```math
N_{KV}=32
```

---

GQA 做的事情则是：

> Query Head 继续保留很多，但是减少 K/V Head 的数量。

例如：

```text
Q1 ─┐
    ├→ K1,V1
Q2 ─┘


Q3 ─┐
    ├→ K2,V2
Q4 ─┘
```

这时候：

```math
N_Q=4
```

但是：

```math
N_{KV}=2
```

所以：

> **MHA 是 Q/K/V Head 数量相同；GQA 才开始让多个 Query Head 共享一套 K/V。**

---

<a id="origin-6252"></a>
## 103. 最关键的一句话

标准 MHA 中：

```math
\boxed{
\text{每个 Head 都有自己独立的一套 }
Q^{(h)},K^{(h)},V^{(h)}
}
```

例如：

```text
32 个 Head

↓

32 个 Q Head
32 个 K Head
32 个 V Head

↓

每个都是 128 维
```

而所谓代码中：

```text
4096维 Q
↓
reshape
32 × 128
```

并不是说：

> 原本只有一个真正的 4096 维 Query，然后再把它随便切开。

而是：

> **本来就设计了 32 个独立的 128 维 Query Head，只是为了 GPU 计算效率，把 32 次小矩阵乘法合并成了一次大矩阵乘法。**

所以最准确的理解是：

```math
\boxed{
\text{MHA = 多个独立的小 Attention 并行计算}
}
```

而不是：

```text
一个大 Attention
算完以后
再随便切成很多块
```

---

