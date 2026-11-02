# LoRA 前向、梯度与部署


> LoRA（Low-Rank Adaptation）的核心思想：
>
> **冻结原来的大模型参数，只额外训练两个很小的低秩矩阵，用它们近似“微调时真正需要修改的权重”。**

理解 LoRA，最重要的是搞清楚以下几个问题：

1. Full Fine-tuning 到底在改什么？
2. 为什么一个巨大的权重更新矩阵，可以用两个小矩阵代替？
3. LoRA 的前向传播到底怎么算？
4. A、B 两个矩阵是怎么通过梯度学出来的？
5. LoRA 放进 Transformer 的 Q/K/V/FFN 后到底发生了什么？
6. LoRA 为什么能显著节省参数、显存和存储空间？
7. LoRA、QLoRA、Adapter 之间是什么关系？

---

<a id="origin-19"></a>
## 1. 从最普通的线性层开始

先不要管 LoRA。

神经网络中最普通的线性层可以写成：

$$
y = Wx + b
$$

其中：

- $x \in \mathbb{R}^{d_{in}}$
- $W \in \mathbb{R}^{d_{out}\times d_{in}}$
- $y \in \mathbb{R}^{d_{out}}$

假设：

$$
d_{in}=4096
$$

$$
d_{out}=4096
$$

那么一个线性层中的权重参数数量就是：

$$
4096\times4096=16,777,216
$$

也就是说，仅仅一个 Linear 层就有大约：

$$
1677\text{ 万}
$$

个参数。

---

<a id="origin-61"></a>
## 2. Full Fine-tuning 到底在做什么？

假设预训练模型已经学好了一个权重矩阵：

$$
W_0
$$

现在我们拿这个模型去做医疗、法律、代码等领域微调。

传统 Full Fine-tuning 会直接修改：

$$
W_0
$$

经过训练以后，它变成：

$$
W'
$$

于是我们可以把这个过程重新写成：

$$
\boxed{
W' = W_0 + \Delta W
}
$$

这里的：

$$
\Delta W
$$

表示：

> 微调以后，相对于原始模型，权重到底发生了多少变化。

---

<a id="origin-103"></a>
### 2.1 一个简单例子

假设原始权重：

$$
W_0=
\begin{bmatrix}
1.0 & 0.3\\
0.2 & 0.8
\end{bmatrix}
$$

Fine-tuning 以后：

$$
W'=
\begin{bmatrix}
1.1 & 0.28\\
0.25 & 0.75
\end{bmatrix}
$$

那么：

$$
\Delta W=W'-W_0
$$

所以：

$$
\Delta W=
\begin{bmatrix}
0.1 & -0.02\\
0.05 & -0.05
\end{bmatrix}
$$

因此可以把 Fine-tuning 理解成：

```text
预训练模型
    ↓
已有参数 W0
    ↓
学习修改量 ΔW
    ↓
W' = W0 + ΔW
```

换句话说：

> Fine-tuning 真正需要学习的，其实是“应该如何修改原模型”。

---

<a id="origin-159"></a>
## 3. LoRA 的核心问题

LoRA 提出了一个非常关键的问题：

> 我们真的有必要直接学习整个 $\Delta W$ 吗？

假设：

$$
\Delta W\in\mathbb{R}^{4096\times4096}
$$

那么就意味着需要学习：

$$
16,777,216
$$

个修改量。

但是大模型经过预训练以后，本身已经拥有：

- 语言能力
- 世界知识
- 推理模式
- 代码知识
- 文本结构
- 基本任务能力

Fine-tuning 往往不是重新学习所有东西，而只是：

> 对已有能力做针对性的调整。

于是 LoRA 做出了一个重要假设：

> Fine-tuning 所需要的权重变化 $\Delta W$，可能集中在一个低维子空间中。

也就是说：

$$
\Delta W
$$

虽然尺寸很大，但真正的“有效自由度”可能并不高。

这就是：

<a id="origin-206"></a>
## 4. Low Rank

也就是：

> **低秩。**

---

<a id="origin-214"></a>
## 5. 什么叫“低秩”？

先看一个 rank=1 的例子。

假设：

$$
b=
\begin{bmatrix}
1\\
2\\
3
\end{bmatrix}
$$

以及：

$$
a=
\begin{bmatrix}
2 & -1
\end{bmatrix}
$$

计算：

$$
ba
$$

得到：

$$
\begin{bmatrix}
1\\
2\\
3
\end{bmatrix}
\begin{bmatrix}
2 & -1
\end{bmatrix}
=
\begin{bmatrix}
2 & -1\\
4 & -2\\
6 & -3
\end{bmatrix}
$$

虽然这个矩阵尺寸是：

$$
3\times2
$$

但是：

```text
第2行 = 第1行 × 2
第3行 = 第1行 × 3
```

所以实际上只有一个独立方向。

因此：

$$
rank=1
$$

---

<a id="origin-286"></a>
## 6. Rank-2、Rank-r 是什么意思？

如果：

$$
\Delta W
=
b_1a_1^T+b_2a_2^T
$$

那么可以理解为：

```text
第一个 rank-1 修改方向
+
第二个 rank-1 修改方向
```

所以：

$$
rank(\Delta W)\le2
$$

更一般地：

$$
\Delta W
=
\sum_{i=1}^{r}b_i a_i^T
$$

那么：

$$
rank(\Delta W)\le r
$$

把这些向量组合起来，就可以写成两个矩阵相乘：

$$
\boxed{
\Delta W = BA
}
$$

其中：

$$
A\in\mathbb{R}^{r\times d_{in}}
$$

$$
B\in\mathbb{R}^{d_{out}\times r}
$$

因此：

$$
BA
$$

的尺寸为：

$$
(d_{out}\times r)(r\times d_{in})
$$

最终：

$$
BA\in\mathbb{R}^{d_{out}\times d_{in}}
$$

与原来的：

$$
W
$$

尺寸完全一样。

---

<a id="origin-370"></a>
## 7. LoRA 最核心的公式

普通 Fine-tuning：

$$
\boxed{
W'=W_0+\Delta W
}
$$

LoRA 认为：

$$
\Delta W\approx BA
$$

于是：

$$
\boxed{
W'=W_0+BA
}
$$

其中：

- $W_0$：原始预训练模型参数
- $W_0$：冻结，不训练
- $A$：低秩矩阵，可训练
- $B$：低秩矩阵，可训练

结构可以画成：

```text
                       Frozen
                         ↓
x ───────────────────→ W0 ─────────────┐
                                       │
                                       + ───→ y
                                       │
x ─────────────→ A ─────→ B ──────────┘
                  ↑        ↑
                Train    Train
```

---

<a id="origin-417"></a>
## 8. LoRA 千万不要理解错

LoRA 并不是说：

$$
W_0
$$

本身是低秩的。

实际上：

$$
W_0
$$

完全可以是一个高秩矩阵。

LoRA 假设的是：

$$
\boxed{
\Delta W \text{ 可以近似为低秩矩阵}
}
$$

也就是说：

> 原模型本身的知识仍然非常复杂，但为了适应某个新任务，需要进行的“修改”可能只集中在少量方向上。

---

<a id="origin-449"></a>
## 9. 一个完整的数值例子

现在完整算一次 LoRA。

假设原始线性层：

$$
W_0=
\begin{bmatrix}
1 & 0.5 & -0.5\\
0.2 & -0.3 & 0.8
\end{bmatrix}
$$

所以：

$$
W_0\in\mathbb{R}^{2\times3}
$$

输入：

$$
x=
\begin{bmatrix}
1\\
2\\
-1
\end{bmatrix}
$$

---

<a id="origin-482"></a>
### 9.1 原模型输出

计算：

$$
y_0=W_0x
$$

第一维：

$$
1\times1+0.5\times2+(-0.5)\times(-1)
$$

得到：

$$
1+1+0.5=2.5
$$

第二维：

$$
0.2\times1+(-0.3)\times2+0.8\times(-1)
$$

得到：

$$
0.2-0.6-0.8=-1.2
$$

所以：

$$
y_0=
\begin{bmatrix}
2.5\\
-1.2
\end{bmatrix}
$$

---

<a id="origin-526"></a>
## 10. 加入 LoRA

假设：

$$
r=1
$$

那么：

$$
A\in\mathbb{R}^{1\times3}
$$

$$
B\in\mathbb{R}^{2\times1}
$$

假设训练以后：

$$
A=
\begin{bmatrix}
0.2 & -0.1 & 0.3
\end{bmatrix}
$$

$$
B=
\begin{bmatrix}
0.5\\
-0.4
\end{bmatrix}
$$

那么：

$$
BA=
\begin{bmatrix}
0.5\\
-0.4
\end{bmatrix}
\begin{bmatrix}
0.2 & -0.1 & 0.3
\end{bmatrix}
$$

得到：

$$
\Delta W=
\begin{bmatrix}
0.1 & -0.05 & 0.15\\
-0.08 & 0.04 & -0.12
\end{bmatrix}
$$

新的权重：

$$
W'=W_0+\Delta W
$$

得到：

$$
W'=
\begin{bmatrix}
1.1 & 0.45 & -0.35\\
0.12 & -0.26 & 0.68
\end{bmatrix}
$$

---

<a id="origin-602"></a>
## 11. 新模型输出

LoRA 带来的额外输出为：

$$
\Delta y=\Delta Wx
$$

第一维：

$$
0.1\times1-0.05\times2+0.15\times(-1)
$$

得到：

$$
-0.15
$$

第二维：

$$
-0.08\times1+0.04\times2+(-0.12)\times(-1)
$$

得到：

$$
0.12
$$

于是：

$$
\Delta y=
\begin{bmatrix}
-0.15\\
0.12
\end{bmatrix}
$$

最终：

$$
y=y_0+\Delta y
$$

所以：

$$
\begin{bmatrix}
2.5\\
-1.2
\end{bmatrix}
+
\begin{bmatrix}
-0.15\\
0.12
\end{bmatrix}
=
\begin{bmatrix}
2.35\\
-1.08
\end{bmatrix}
$$

最终：

$$
\boxed{
y=
\begin{bmatrix}
2.35\\
-1.08
\end{bmatrix}
}
$$

这里最重要的是：

> 原来的 $W_0$ 一个参数都没有改。

LoRA 只是通过：

$$
BA
$$

额外增加了一点修改量。

---

<a id="origin-695"></a>
## 12. 实际上不用真的算 BA

虽然数学上：

$$
\Delta W=BA
$$

但是实际计算时没有必要先把：

$$
BA
$$

真的乘出来。

因为：

$$
BAx=B(Ax)
$$

所以可以先：

$$
Ax
$$

再：

$$
B(Ax)
$$

例如：

$$
d=4096
$$

$$
r=8
$$

则：

```text
4096
  ↓
  A
  ↓
  8
  ↓
  B
  ↓
4096
```

也就是说：

> 先把 4096 维压缩到 8 维，再从 8 维映射回 4096 维。

---

<a id="origin-759"></a>
## 13. 从网络结构上理解 LoRA

因此 LoRA 可以看成一个很小的旁路：

```text
                         ┌──────── W0 ────────┐
                         │                    │
x ──────────────────────→│                    ├────┐
                         └────────────────────┘    │
                                                   +
                         ┌── A ─── B ──────────┐  │
x ──────────────────────→│4096→8→4096          ├──┘
                         └─────────────────────┘
                                                   ↓
                                                   y
```

LoRA branch 本质是：

$$
d_{in}\rightarrow r\rightarrow d_{out}
$$

---

<a id="origin-784"></a>
## 14. 为什么 LoRA 不需要激活函数？

LoRA 的核心结构：

$$
B(Ax)
$$

中间通常没有：

- ReLU
- SiLU
- GELU

等非线性。

所以：

$$
B(Ax)=BAx
$$

于是：

$$
W_0x+BAx
=
(W_0+BA)x
$$

因此 LoRA 最终能够直接：

> merge 到原权重中。

---

<a id="origin-820"></a>
## 15. 参数量到底少多少？

原始矩阵：

$$
W\in\mathbb{R}^{4096\times4096}
$$

Full Fine-tuning 参数：

$$
4096\times4096
=
16,777,216
$$

假设：

$$
r=8
$$

那么：

$$
A\in\mathbb{R}^{8\times4096}
$$

参数：

$$
8\times4096=32768
$$

B：

$$
B\in\mathbb{R}^{4096\times8}
$$

参数也是：

$$
32768
$$

总共：

$$
65536
$$

比例：

$$
\frac{65536}{16777216}
=
0.00390625
$$

即：

$$
\boxed{
0.39\%
}
$$

也就是说：

> 对于这个 Linear 层，LoRA 的可训练参数只有 Full Fine-tuning 的约 1/256。

---

<a id="origin-894"></a>
## 16. Rank r 到底控制什么？

Rank 是 LoRA 最重要的超参数之一。

如果：

$$
r=1
$$

则：

$$
\Delta W=b_1a_1^T
$$

只能学习一个主要修改方向。

如果：

$$
r=2
$$

则：

$$
\Delta W=
b_1a_1^T+b_2a_2^T
$$

可以学习两个方向。

如果：

$$
r=8
$$

则：

$$
\Delta W=
\sum_{i=1}^{8}b_ia_i^T
$$

可以看成：

> 8 个 rank-1 修改模式的叠加。

---

<a id="origin-946"></a>
### 16.1 Rank 越大

```text
r ↑

表达能力 ↑
参数量 ↑
显存 ↑
优化器状态 ↑
过拟合风险可能 ↑
```

---

<a id="origin-960"></a>
### 16.2 Rank 越小

```text
r ↓

表达能力 ↓
参数量 ↓
显存 ↓
训练成本 ↓
```

所以：

> rank 并不是越大越好，而是模型容量和训练成本之间的权衡。

---

<a id="origin-977"></a>
## 17. 一个语义上的理解

假设一个大模型已经知道：

```text
苹果
Python
数据库
律师
医院
Transformer
神经网络
```

现在要把它 Fine-tune 成一个医疗问答模型。

模型并不需要重新学习：

- 什么是自然语言
- 什么是医生
- 什么是药
- 什么是人体
- 怎么生成一句完整的话

它可能只是需要加强一些任务方向，例如：

```text
方向 1：医学术语理解
方向 2：疾病 → 症状
方向 3：药物 → 禁忌
方向 4：风险提示
方向 5：医生式回答风格
方向 6：检查建议
```

那么 Fine-tuning 所需修改可能集中在少数方向。

这就是 LoRA 的直觉。

---

<a id="origin-1018"></a>
## 18. 实际 LoRA 还有 alpha

真实 LoRA 通常写成：

$$
\boxed{
W'
=
W_0+
\frac{\alpha}{r}BA
}
$$

其中：

- $r$：LoRA rank
- $\alpha$：LoRA alpha

定义：

$$
s=\frac{\alpha}{r}
$$

那么：

$$
\boxed{
y=
W_0x+sBAx
}
$$

---

<a id="origin-1053"></a>
## 19. alpha 是干什么的？

alpha 主要负责控制：

> LoRA branch 的整体缩放强度。

例如：

$$
r=8
$$

$$
\alpha=16
$$

那么：

$$
s=\frac{16}{8}=2
$$

所以：

$$
\Delta W=2BA
$$

如果：

$$
r=16
$$

$$
\alpha=16
$$

那么：

$$
s=1
$$

因此可以粗略理解为：

- $r$：决定 LoRA 有多少表达容量
- $\alpha$：决定 LoRA 修改的整体缩放

---

<a id="origin-1104"></a>
## 20. LoRA 的初始化为什么特殊？

LoRA 通常采用：

$$
A=\text{随机初始化}
$$

$$
B=0
$$

因此刚开始：

$$
BA=0
$$

所以：

$$
W'=W_0
$$

也就是说：

> 刚刚把 LoRA 挂到模型上时，模型输出和原模型保持一致。

这是一个非常重要的设计。

---

<a id="origin-1136"></a>
## 21. 为什么 A 和 B 不能都初始化成 0？

假设：

$$
A=0
$$

$$
B=0
$$

LoRA 输出：

$$
BAx=0
$$

看似没问题。

但是梯度会出问题。

定义：

$$
z=Ax
$$

LoRA 输出：

$$
\Delta y=Bz
$$

假设：

$$
g=\frac{\partial L}{\partial y}
$$

那么：

$$
\frac{\partial L}{\partial B}
=
gz^T
$$

但如果：

$$
A=0
$$

那么：

$$
z=Ax=0
$$

所以：

$$
\frac{\partial L}{\partial B}=0
$$

另一方面：

$$
\frac{\partial L}{\partial A}
=
B^Tgx^T
$$

如果：

$$
B=0
$$

那么：

$$
\frac{\partial L}{\partial A}=0
$$

于是：

```text
A = 0
B = 0

↓

grad_A = 0
grad_B = 0

↓

模型完全学不动
```

---

<a id="origin-1240"></a>
## 22. 为什么 A 随机、B=0 可以？

令：

$$
A\neq0
$$

随机初始化。

令：

$$
B=0
$$

则：

$$
BA=0
$$

所以初始化时模型行为没有变化。

但是：

$$
Ax\neq0
$$

因此：

$$
\frac{\partial L}{\partial B}
\neq0
$$

于是第一步：

```text
A：几乎不动
B：开始学习
```

等到：

$$
B\neq0
$$

以后：

$$
\frac{\partial L}{\partial A}
\neq0
$$

于是 A 也开始学习。

---

<a id="origin-1301"></a>
## 23. 把 LoRA 反向传播完整写出来

定义：

$$
z=Ax
$$

然后：

$$
\Delta y=sBz
$$

其中：

$$
s=\frac{\alpha}{r}
$$

假设：

$$
g=
\frac{\partial L}{\partial y}
$$

那么：

$$
\boxed{
\frac{\partial L}{\partial B}
=
s\,gz^T
}
$$

而：

$$
z=Ax
$$

因此：

$$
\boxed{
\frac{\partial L}{\partial A}
=
sB^Tgx^T
}
$$

初始化时：

$$
B=0
$$

所以：

$$
\frac{\partial L}{\partial A}=0
$$

但是因为 A 是随机的：

$$
z=Ax\neq0
$$

因此：

$$
\frac{\partial L}{\partial B}\neq0
$$

---

<a id="origin-1380"></a>
## 24. 一次完整的 LoRA 训练过程

Forward：

```text
                   Frozen
                     ↓
x ────────────────→ W0 ───────────────┐
                                      │
                                      + ─→ y ─→ Loss
                                      │
x ─→ Dropout ─→ A ─→ B ─→ scaling ──┘
```

Backward：

```text
Loss
 ↓
backward()
 ↓
计算 LoRA A / B 的 gradient
 ↓
W0 不更新
 ↓
optimizer.step()
 ↓
更新 A、B
```

注意：

> LoRA 并没有改变语言模型的训练目标。

例如 Causal LM 仍然使用：

$$
L
=
-\sum_t
\log
P(x_{t+1}\mid x_{\le t})
$$

CrossEntropyLoss 也没有发生本质变化。

只是：

> 哪些参数允许被 optimizer 更新发生了变化。

---

<a id="origin-1432"></a>
## 25. LoRA 到 Transformer 里加在哪里？

Transformer 中有大量 Linear。

例如 Attention：

```text
Hidden State
     │
     ├── q_proj
     ├── k_proj
     ├── v_proj
     │
 Attention
     │
     └── o_proj
```

FFN 中：

```text
gate_proj
up_proj
down_proj
```

这些本质上都是：

$$
y=Wx
$$

所以都可以改成：

$$
y=
W_0x+
\frac{\alpha}{r}BAx
$$

---

<a id="origin-1474"></a>
## 26. 以 Q Projection 为例

原始：

$$
Q=XW_Q^T
$$

加入 LoRA 后：

$$
W_Q'
=
W_Q+
sB_QA_Q
$$

所以：

$$
Q
=
X(W_Q')^T
$$

展开：

$$
Q
=
XW_Q^T
+
sX(B_QA_Q)^T
$$

利用：

$$
(BA)^T=A^TB^T
$$

得到：

$$
\boxed{
Q=
XW_Q^T
+
s(XA_Q^T)B_Q^T
}
$$

第二部分：

$$
s(XA_Q^T)B_Q^T
$$

就是 LoRA branch。

---

<a id="origin-1536"></a>
## 27. Tensor Shape 怎么变化？

假设：

```text
batch = 2
sequence length = 128
hidden size = 4096
rank = 8
```

输入：

$$
X
$$

shape：

```text
[2, 128, 4096]
```

A：

```text
[8, 4096]
```

计算：

$$
XA^T
$$

得到：

```text
[2,128,4096]
      ×
[4096,8]

↓

[2,128,8]
```

然后 B：

```text
[4096,8]
```

所以：

$$
B^T
$$

shape：

```text
[8,4096]
```

继续：

```text
[2,128,8]
    ×
[8,4096]

↓

[2,128,4096]
```

于是：

```text
LoRA Branch:

4096
 ↓
 8
 ↓
4096
```

最终和 Base Q 相加：

```text
Q_base    [2,128,4096]

LoRA_Q    [2,128,4096]

          ↓

Q_final   [2,128,4096]
```

因此后面的 Attention 根本不需要知道：

> 这个 Q 到底是 Base Model 产生的，还是 Base + LoRA 产生的。

---

<a id="origin-1643"></a>
## 28. LoRA 必须只加 Q/V 吗？

不是。

早期经典 LoRA 经常只对：

```text
q_proj
v_proj
```

增加 LoRA。

现在大量实际训练会加入：

```text
q_proj
k_proj
v_proj
o_proj
```

甚至进一步加入：

```text
gate_proj
up_proj
down_proj
```

所以经常会看到：

```python
target_modules = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
]
```

这意味着：

> 只允许 Attention 投影矩阵通过 LoRA 发生调整。

---

<a id="origin-1690"></a>
## 29. 为什么给 Q/K/V 加 LoRA 有意义？

Recall：

$$
Q=XW_Q
$$

Q 可以理解为：

> 当前 token 正在寻找什么信息。

---

$$
K=XW_K
$$

K 可以理解为：

> 当前 token 提供什么特征供别人匹配。

---

$$
V=XW_V
$$

V 可以理解为：

> 一旦被注意到，真正向别人传递什么信息。

所以改变：

$$
W_Q,W_K,W_V
$$

就是在改变：

> token 之间如何建立关系、如何分配注意力、以及注意以后传递什么内容。

---

<a id="origin-1734"></a>
## 30. 一个语义例子

例如输入：

> 患者正在服用华法林，可以服用阿司匹林吗？

原模型已经知道：

```text
华法林
阿司匹林
药物
患者
```

LoRA 不需要重新教授这些概念。

它可能主要加强如下关系：

```text
阿司匹林
   ↓
华法林
   ↓
共同作用
   ↓
出血风险
```

因此：

$$
\Delta W_Q,\Delta W_K,\Delta W_V
$$

实际上在改变：

> 模型在特定领域应该更加关注哪些关系。

---

<a id="origin-1775"></a>
## 31. 为什么 FFN 也可以加 LoRA？

Transformer 的 FFN 通常包括：

$$
W_{gate}
$$

$$
W_{up}
$$

$$
W_{down}
$$

如果简单理解：

- Attention：负责 token 之间的信息交互
- FFN：负责单个 token 内部的特征变换

那么：

```text
Attention LoRA
```

更多影响：

> 信息应该如何互相关注。

而：

```text
FFN LoRA
```

更多影响：

> 中间特征应该如何变换。

任务复杂时，可以给更多 Linear 层加 LoRA，从而提高适配能力。

---

<a id="origin-1820"></a>
## 32. LoRA Dropout 是什么？

实际配置中经常看到：

```python
lora_dropout=0.05
```

Forward 可以理解成：

$$
y
=
W_0x
+
sB(A(\operatorname{Dropout}(x)))
$$

Dropout 一般只作用在 LoRA branch。

作用是：

> 减少 LoRA 对训练数据中特定模式的过拟合。

数据量小时更加常见。

---

<a id="origin-1848"></a>
## 33. 最简单的 PyTorch LoRA 实现

```python
import math
import torch
import torch.nn as nn


class LoRALinear(nn.Module):

    def __init__(
        self,
        in_features,
        out_features,
        r=8,
        alpha=16,
        dropout=0.0
    ):
        super().__init__()

        # 原始 Linear
        self.base = nn.Linear(
            in_features,
            out_features
        )

        # 冻结 Base Model
        for p in self.base.parameters():
            p.requires_grad = False

        self.r = r
        self.alpha = alpha
        self.scaling = alpha / r

        # A：in_features -> r
        self.lora_A = nn.Parameter(
            torch.empty(r, in_features)
        )

        # B：r -> out_features
        self.lora_B = nn.Parameter(
            torch.zeros(out_features, r)
        )

        self.dropout = nn.Dropout(dropout)

        # A 随机初始化
        nn.init.kaiming_uniform_(
            self.lora_A,
            a=math.sqrt(5)
        )

    def forward(self, x):

        # Base Model
        base_output = self.base(x)

        # LoRA Branch
        lora_output = (
            self.dropout(x)
            @ self.lora_A.T
            @ self.lora_B.T
        )

        return (
            base_output
            +
            self.scaling * lora_output
        )
```

---

<a id="origin-1921"></a>
## 34. 代码与数学公式一一对应

代码：

```python
base_output = self.base(x)
```

对应：

$$
W_0x
$$

代码：

```python
x @ self.lora_A.T @ self.lora_B.T
```

对应：

$$
BAx
$$

代码：

```python
self.scaling = alpha / r
```

对应：

$$
\frac{\alpha}{r}
$$

最终：

```python
base_output + scaling * lora_output
```

对应：

$$
\boxed{
y=
W_0x+
\frac{\alpha}{r}BAx
}
$$

这就是 LoRA 的全部数学本质。

---

<a id="origin-1979"></a>
## 35. Hugging Face PEFT 中怎么写？

典型配置：

```python
from peft import LoraConfig, get_peft_model

config = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,

    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    ],

    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(
    model,
    config
)
```

PEFT 会自动把目标 Linear 逻辑上变成：

```text
Base Linear
+
LoRA A
+
LoRA B
```

---

<a id="origin-2020"></a>
## 36. 为什么 LoRA 文件特别小？

Full Fine-tuning 需要保存完整的新模型：

$$
W'
$$

例如 7B 模型可能包含数十亿参数。

LoRA 通常只需要保存：

```text
A
B
LoRA Config
```

原来的：

$$
W_0
$$

仍然使用 Base Model。

于是一个 Base Model 可以搭配很多 LoRA：

```text
                  Base Model
                      │
       ┌──────────────┼──────────────┐
       │              │              │
       ↓              ↓              ↓
  Medical LoRA    Code LoRA      Legal LoRA
```

---

<a id="origin-2059"></a>
## 37. LoRA 可以 Merge

训练时：

$$
y=
W_0x+sBAx
$$

可以重新写成：

$$
y=
(W_0+sBA)x
$$

因此训练完成以后可以直接计算：

$$
\boxed{
W_{\text{merged}}
=
W_0+sBA
}
$$

随后删除：

```text
A
B
```

推理时直接使用：

$$
y=W_{\text{merged}}x
$$

---

<a id="origin-2100"></a>
## 38. Merge 前后

训练阶段：

```text
             W0
             │
x ───────────┼───────────────┐
             │               │
             └→ A → B ───────┤
                             +
                             ↓
                             y
```

Merge 后：

```text
Wmerged = W0 + sBA

x
↓
Wmerged
↓
y
```

所以 Merge 后：

> 推理时没有必要再经过 A、B 两层。

---

<a id="origin-2133"></a>
## 39. LoRA 与 Adapter 的区别

经典 Adapter 经常类似：

$$
h'
=
h+
W_{up}
\sigma(W_{down}h)
$$

其中存在：

$$
\sigma
$$

这样的非线性函数。

例如：

- ReLU
- GELU

所以：

$$
W_{up}\sigma(W_{down}h)
$$

不能简单等价为：

$$
\Delta Wh
$$

因此很难直接 Merge。

---

LoRA：

$$
h'=Wh+BAh
$$

由于没有非线性：

$$
h'=(W+BA)h
$$

因此：

> LoRA 可以直接 Merge 到原权重。

---

<a id="origin-2192"></a>
## 40. LoRA 为什么能够有效？

可以从三个层面理解。

---

<a id="origin-2198"></a>
### 40.1 第一层：Base Model 已经很强

预训练模型已经掌握：

```text
语言
语法
常识
世界知识
大量推理模式
代码模式
文本生成模式
```

Fine-tuning 往往只是：

> 调整已有能力。

---

<a id="origin-2218"></a>
### 40.2 第二层：Fine-tuning 更新可能是低秩的

虽然：

$$
W
$$

非常大，

但是任务相关修改：

$$
\Delta W
$$

可能主要集中在少数方向。

于是：

$$
\Delta W\approx BA
$$

---

<a id="origin-2244"></a>
### 40.3 第三层：LoRA 会分布在整个网络中

假设一个模型有 32 层。

每层给：

```text
Q
K
V
O
```

添加 LoRA。

那么一共有：

$$
32\times4=128
$$

套独立 LoRA。

如果每一套：

$$
r=8
$$

并不意味着：

> 整个模型只能学习 8 个方向。

而是：

> 每一层、每一个功能位置都有自己的低秩调整空间。

所以整个网络的表达能力仍然非常强。

---

<a id="origin-2285"></a>
## 41. 为什么 rank=8 也可能有效？

假设：

```text
32 Transformer Layers
```

每层：

```text
q_proj
k_proj
v_proj
o_proj
```

都使用 rank=8。

那么模型拥有大量不同的：

$$
A_i,B_i
$$

这些 LoRA 分布在网络不同深度。

所以最终的适配效果来自：

> 大量局部低秩修改在深层网络中的组合。

并不是简单的“整个模型只有 8 个自由度”。

---

<a id="origin-2320"></a>
## 42. LoRA 到底节省了什么？

LoRA 主要节省三部分。

---

<a id="origin-2326"></a>
### 42.1 Trainable Parameters

Full Fine-tuning：

> 几乎所有参数都参与训练。

LoRA：

> 只有 A、B 参与训练。

---

<a id="origin-2338"></a>
### 42.2 Gradient Memory

Full Fine-tuning：

每个参数都需要：

$$
\frac{\partial L}{\partial W}
$$

LoRA：

Base Model 参数被冻结，因此不需要存储它们的训练梯度。

---

<a id="origin-2354"></a>
### 42.3 Optimizer States

例如 AdamW 通常需要保存：

- 一阶矩 $m$
- 二阶矩 $v$

Full Fine-tuning：

> 几十亿参数都需要 optimizer state。

LoRA：

> 只有 A/B 需要 optimizer state。

这一项能够显著节省显存。

---

<a id="origin-2373"></a>
## 43. LoRA 不是什么显存都省

LoRA 并不会让整个模型消失。

Forward 时仍然需要计算：

```text
Transformer hidden states
Attention
FFN
Activations
```

所以 LoRA 主要节省：

```text
Trainable Parameters
Gradients
Optimizer States
Checkpoint Size
```

但是：

> Base Model 本身仍然要加载进显存。

这也是 QLoRA 出现的原因。

---

<a id="origin-2403"></a>
## 44. QLoRA 是什么？

一句话：

> **QLoRA = 量化 Base Model + LoRA 微调。**

普通 LoRA：

```text
Base Model
FP16 / BF16
Frozen

+

LoRA
FP16 / BF16
Trainable
```

QLoRA：

```text
Base Model
4-bit
Frozen

+

LoRA
FP16 / BF16
Trainable
```

因此进一步减少：

> Base Model 本身的显存占用。

---

<a id="origin-2443"></a>
## 45. Full Fine-tuning、LoRA、QLoRA 对比

```text
Full Fine-tuning
│
├─ Base Weight：训练
├─ Gradient：全部参数
├─ Optimizer State：全部参数
└─ 显存：最高


LoRA
│
├─ Base Weight：冻结
├─ LoRA A/B：训练
├─ Gradient：只有 A/B
├─ Optimizer State：只有 A/B
└─ 显存：明显下降


QLoRA
│
├─ Base Weight：4-bit + 冻结
├─ LoRA A/B：训练
├─ Gradient：只有 A/B
├─ Optimizer State：只有 A/B
└─ 显存：进一步下降
```

---

<a id="origin-2474"></a>
## 46. Rank 怎么选？

没有绝对固定答案。

可以这样理解：

| Rank | 特点 |
|---|---|
| r=4 | 参数极少，适配能力较弱 |
| r=8 | 常见起点，成本低 |
| r=16 | 更强适配能力 |
| r=32 | 适合更复杂任务 |
| r=64 | 参数更多，容量更高 |
| r=128 | 已经属于较大的 LoRA |

核心原则：

```text
r ↑
→ 表达能力 ↑
→ 参数量 ↑
→ 显存 ↑
→ 训练成本 ↑
```

最终需要：

> 用验证集评价。

---

<a id="origin-2505"></a>
## 47. alpha 怎么选？

核心公式：

$$
scaling=
\frac{\alpha}{r}
$$

例如：

| r | alpha | scaling |
|---:|---:|---:|
| 8 | 8 | 1 |
| 8 | 16 | 2 |
| 16 | 16 | 1 |
| 16 | 32 | 2 |
| 32 | 64 | 2 |

不要死记固定值。

应该理解：

> alpha 决定 LoRA branch 被整体放大多少。

---

<a id="origin-2532"></a>
## 48. LoRA Dropout 怎么选？

常见：

```text
0
0.05
0.1
```

数据非常多：

```text
dropout 可以较低
```

数据比较少：

```text
适当 dropout 有助于避免过拟合
```

但仍然需要验证集判断。

---

<a id="origin-2558"></a>
## 49. LoRA Learning Rate 为什么经常更大？

Full Fine-tuning：

> 数十亿参数一起变化，所以学习率通常比较谨慎。

LoRA：

> 只有少量新增参数 A/B 在训练。

因此 LoRA 常常能够使用更大的学习率。

例如：

```text
Full FT:
1e-5

LoRA:
1e-4
```

这类量级差异并不罕见。

但绝对不是固定规则。

---

<a id="origin-2586"></a>
## 50. 一个完整的 LoRA 训练流程

假设要训练一个代码模型。

---

<a id="origin-2592"></a>
### 50.1 Step 1：加载 Base Model

```python
model = load_model()
```

模型内部：

```text
Embedding
↓
Transformer × N
↓
LM Head
```

---

<a id="origin-2610"></a>
### 50.2 Step 2：冻结 Base Model

```python
for p in model.parameters():
    p.requires_grad = False
```

---

<a id="origin-2619"></a>
### 50.3 Step 3：找到 target_modules

例如：

```text
q_proj
k_proj
v_proj
o_proj
```

---

<a id="origin-2632"></a>
### 50.4 Step 4：给 Linear 添加 LoRA

原来：

$$
y=W_0x
$$

变成：

$$
y=
W_0x+
\frac{\alpha}{r}BAx
$$

---

<a id="origin-2650"></a>
### 50.5 Step 5：输入训练数据

例如：

```text
<user>
写一个 Python 快速排序

<assistant>
def quicksort(...):
    ...
```

转成 token：

$$
x_1,x_2,\ldots,x_n
$$

---

<a id="origin-2671"></a>
### 50.6 Step 6：正常 Causal LM Forward

例如：

```text
BOS I love AI EOS
```

模型仍然学习：

```text
BOS → I
I → love
love → AI
AI → EOS
```

Loss 仍然是：

$$
CrossEntropyLoss
$$

---

<a id="origin-2696"></a>
### 50.7 Step 7：Backward

```python
loss.backward()
```

Base：

```text
W0
requires_grad=False
```

所以：

> 不更新。

LoRA：

```text
A
requires_grad=True

B
requires_grad=True
```

因此得到：

$$
\nabla_A L
$$

和：

$$
\nabla_B L
$$

---

<a id="origin-2737"></a>
### 50.8 Step 8：Optimizer Step

```python
optimizer.step()
```

真正变化的是：

$$
A,B
$$

过程：

```text
第 0 步：

W0 不变
A 随机
B = 0


第 100 步：

W0 不变
A 改变
B 改变


第 10000 步：

W0 仍然不变
A 学好了
B 学好了
```

---

<a id="origin-2775"></a>
## 51. 推理时怎么做？

有两种方式。

---

<a id="origin-2781"></a>
### 51.1 方法一：不 Merge

继续使用：

$$
y=
W_0x+sBAx
$$

优点：

> 可以随时切换不同 LoRA。

例如：

```text
Base Model + Medical LoRA
Base Model + Code LoRA
Base Model + Legal LoRA
```

---

<a id="origin-2804"></a>
### 51.2 方法二：Merge

直接：

$$
W'=W_0+sBA
$$

然后：

$$
y=W'x
$$

适合：

> 固定部署某一个任务。

---

<a id="origin-2824"></a>
## 52. 从四个角度理解 LoRA

---

<a id="origin-2828"></a>
### 52.1 视角一：参数高效微调

Full Fine-tuning 参数：

$$
d_{out}d_{in}
$$

LoRA：

$$
r(d_{in}+d_{out})
$$

当：

$$
r\ll d
$$

时，参数大幅减少。

---

<a id="origin-2852"></a>
### 52.2 视角二：矩阵分解

LoRA 假设：

$$
\Delta W
$$

可以写成：

$$
BA
$$

并满足：

$$
rank(\Delta W)\le r
$$

---

<a id="origin-2874"></a>
### 52.3 视角三：旁路小网络

```text
x
│
├──────────── W0 ─────────────┐
│                             │
└──── A ───→ r维 ───→ B ─────┤
                              ↓
                              y
```

---

<a id="origin-2888"></a>
### 52.4 视角四：限制 Fine-tuning 搜索空间

Full Fine-tuning 可以在：

$$
d_{out}\times d_{in}
$$

整个巨大参数空间里寻找答案。

LoRA 强制：

$$
\Delta W=BA
$$

相当于限制模型：

> 只能在一个低秩空间里寻找合适的修改方向。

这既降低了成本，也具有某种隐式正则化效果。

---

<a id="origin-2912"></a>
## 53. LoRA 最核心的一条数学主线

原模型：

$$
\boxed{
y=W_0x
}
$$

Full Fine-tuning：

$$
\boxed{
y=(W_0+\Delta W)x
}
$$

其中需要学习：

$$
\Delta W
\in
\mathbb{R}^{d_{out}\times d_{in}}
$$

LoRA 假设：

$$
\boxed{
\Delta W\approx BA
}
$$

其中：

$$
A\in\mathbb{R}^{r\times d_{in}}
$$

$$
B\in\mathbb{R}^{d_{out}\times r}
$$

并且：

$$
r\ll d_{in},d_{out}
$$

所以：

$$
\boxed{
y=
W_0x+
\frac{\alpha}{r}BAx
}
$$

训练过程中：

$$
\boxed{
W_0\text{ frozen}
}
$$

只更新：

$$
\boxed{
A,B
}
$$

最后可以 Merge：

$$
\boxed{
W_{\text{merged}}
=
W_0+
\frac{\alpha}{r}BA
}
$$

---

<a id="origin-3001"></a>
## 54. 一张图总结 LoRA

```text
                       Pretrained Model
                              │
                              ↓
                        Linear W0
                         [Frozen]
                              │
             ┌────────────────┴────────────────┐
             │                                 │
             ↓                                 ↓
        Base Branch                       LoRA Branch

           x                                  x
           │                                  │
           ↓                                  ↓
          W0                              Dropout
           │                                  │
           │                                  ↓
           │                                  A
           │                            d_in → rank
           │                                  │
           │                                  ↓
           │                                  B
           │                           rank → d_out
           │                                  │
           │                            × alpha / r
           │                                  │
           └─────────────── + ────────────────┘
                              │
                              ↓
                              y
                              │
                              ↓
                             Loss
                              │
                           backward
                              │
                    ┌─────────┴─────────┐
                    ↓                   ↓
                 update A            update B

                      W0 始终不更新
```

---

<a id="origin-3049"></a>
## 55. 最后一句话总结

LoRA 的本质不是：

> 把大模型变小。

而是：

> **相信下游任务对预训练模型的修改只需要发生在一个低维子空间中，因此冻结原模型 $W_0$，仅用两个低秩矩阵 $A$ 和 $B$ 学习权重变化 $\Delta W$。**

数学上就是：

$$
\boxed{
\Delta W
\approx
\frac{\alpha}{r}BA
}
$$

于是：

$$
\boxed{
W'
=
W_0+
\frac{\alpha}{r}BA
}
$$

这就是 LoRA 从数学原理、前向传播、反向传播、Transformer 接入到最终部署的完整主线。
