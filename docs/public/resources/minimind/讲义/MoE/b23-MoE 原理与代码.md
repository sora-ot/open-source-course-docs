# MoE 原理与代码


---

<a id="origin-5"></a>
## 1. MoE 到底是什么？

MoE：

\[
\boxed{\text{Mixture of Experts}}
\]

中文通常叫：

> **混合专家模型**

它最核心的思想非常简单：

> 不再让所有 Token 都经过同一个 FFN，而是准备很多个不同的 FFN，再让模型自己决定：当前这个 Token 应该交给哪几个 FFN 处理。

这些不同的 FFN 就叫：

\[
\boxed{\text{Expert}}
\]

即：

> 专家。

因此最简单地说：

\[
\boxed{
\text{MoE}
=
\text{多个 FFN}
+
\text{一个负责选择 FFN 的 Router}
}
\]

---

<a id="origin-45"></a>
## 2. 为什么会出现 MoE？

先回忆普通 Transformer。

一个 Transformer Block 大致可以写成：

```text
Hidden State
    ↓
Attention
    ↓
Residual
    ↓
FFN
    ↓
Residual
    ↓
下一层
```

其中 FFN 通常类似：

\[
x
\rightarrow
W_1
\rightarrow
\text{Activation}
\rightarrow
W_2
\]

例如：

\[
4096
\rightarrow
11008
\rightarrow
4096
\]

普通 Dense Transformer 中，每一个 Token 都经过：

\[
\boxed{\text{同一个 FFN}}
\]

例如：

```text
"I"      ──→ FFN
"love"   ──→ FFN
"AI"     ──→ FFN
```

也就是说：

> 所有 Token 共享这一套 FFN 参数。

---

<a id="origin-107"></a>
## 3. Dense 模型的问题：参数量和计算量一起增加

如果希望模型能力更强，一种很直接的办法就是：

```text
把 FFN 做得越来越大
```

比如：

\[
4096
\rightarrow
11008
\rightarrow
4096
\]

改成更大的中间层。

这样当然可以增加参数量。

但是问题是：

\[
\boxed{
\text{参数量增加}
\Rightarrow
\text{每个 Token 的计算量也增加}
}
\]

因为每个 Token 都必须经过完整 FFN。

所以 Dense 模型往往存在：

\[
\boxed{
\text{模型越大}
\Rightarrow
\text{每个 Token 算得越多}
}
\]

---

<a id="origin-153"></a>
## 4. MoE 的目标：参数很多，但每次只计算一小部分

MoE 的思想是：

> 我可以准备很多套 FFN，但不让每个 Token 都经过全部 FFN。

例如准备：

```text
Expert 0
Expert 1
Expert 2
Expert 3
Expert 4
Expert 5
Expert 6
Expert 7
```

一共：

\[
8
\]

个 Expert。

假设：

\[
TopK=2
\]

那么对于一个 Token，只选择其中两个 Expert。

例如：

```text
"AI"
 ↓
Router
 ↓
Expert 2
Expert 6
```

其他：

```text
Expert 0
Expert 1
Expert 3
Expert 4
Expert 5
Expert 7
```

这一轮都不计算。

因此：

\[
\boxed{
\text{总参数很多}
}
\]

但是：

\[
\boxed{
\text{单个 Token 只激活少量参数}
}
\]

这就是 MoE 最重要的思想：

\[
\boxed{\text{Sparse Activation}}
\]

即：

> 稀疏激活。

---

<a id="origin-240"></a>
## 5. Dense 和 MoE 的直接对比

Dense：

```text
Token
 ↓
FFN
 ↓
Output
```

所有 Token：

```text
Token 1 ─→ FFN
Token 2 ─→ FFN
Token 3 ─→ FFN
Token 4 ─→ FFN
```

MoE：

```text
                  ┌→ Expert 0
                  ├→ Expert 1
Token → Router ───┼→ Expert 2
                  ├→ Expert 3
                  └→ ...
```

但是对于某个 Token：

```text
只选择 Top-k 个 Expert
```

例如：

```text
Token 1 → Expert 1 + Expert 4
Token 2 → Expert 0 + Expert 6
Token 3 → Expert 1 + Expert 5
```

因此 MoE 经常叫：

\[
\boxed{\text{Sparse MoE}}
\]

---

<a id="origin-293"></a>
## 6. Expert 到底是什么？

这是学习 MoE 时首先要搞清楚的问题。

Expert 通常并不是：

```text
一个完整的大模型
```

而是：

\[
\boxed{\text{一个 FFN}}
\]

普通 Transformer：

```text
Attention
   ↓
FFN
```

MoE Transformer：

```text
Attention
   ↓
MoE
```

而这个 MoE 内部是：

```text
Router
+
Expert 0
+
Expert 1
+
Expert 2
+
...
```

其中每个 Expert 本身就是一个 FFN。

比如：

\[
Expert_i(x)
=
W_{2,i}
\sigma(W_{1,i}x)
\]

如果使用 LLaMA 常见的 SwiGLU，则类似：

\[
Expert_i(x)
=
W_{down,i}
\left[
\operatorname{SiLU}(W_{gate,i}x)
\odot
W_{up,i}x
\right]
\]

所以本质上：

\[
\boxed{
\text{MoE 就是把原来的一个 FFN 换成很多个 FFN}
}
\]

然后再增加一个 Router 来选择。

---

<a id="origin-375"></a>
## 7. 为什么通常替换 FFN，而不是 Attention？

因为 FFN 本身就是 Transformer 中非常大的参数模块。

假设：

\[
d_{model}=4096
\]

FFN 为：

\[
4096
\rightarrow
11008
\rightarrow
4096
\]

仅仅两个主要矩阵：

\[
W_1\in\mathbb R^{4096\times11008}
\]

\[
W_2\in\mathbb R^{11008\times4096}
\]

参数量大约：

\[
2\times4096\times11008
\]

约为：

\[
90M
\]

所以如果把：

```text
1 个 FFN
```

变成：

```text
8 个 FFN
```

参数容量一下子就增加很多。

但如果每次只计算其中：

```text
2 个
```

那么计算量不会按照 8 倍一起增长。

因此 MoE 可以实现：

\[
\boxed{
\text{更大的参数容量}
+
\text{相对较低的激活计算量}
}
\]

---

<a id="origin-451"></a>
## 8. MoE 最核心的组件：Router

假设某个 Token 当前的 hidden state 是：

\[
x\in\mathbb R^d
\]

例如：

\[
d=4096
\]

Router 的任务是：

> 判断当前 Token 应该送给哪些 Expert。

最简单的 Router 就是一个线性层：

\[
z=xW_r
\]

假设有：

\[
N=8
\]

个 Expert。

那么：

\[
W_r\in\mathbb R^{4096\times8}
\]

所以：

\[
x
\in
\mathbb R^{4096}
\]

经过 Router 后：

\[
z
\in
\mathbb R^8
\]

例如：

\[
z=
[
1.2,\,
-0.5,\,
2.0,\,
0.3,\,
-1.1,\,
1.5,\,
0.7,\,
2.4
]
\]

这 8 个数分别对应：

```text
Expert 0 的分数
Expert 1 的分数
Expert 2 的分数
...
Expert 7 的分数
```

---

<a id="origin-533"></a>
## 9. Router 实际在学习什么？

Router 实际在学习：

\[
\boxed{
\text{什么样的 hidden state 应该交给哪个 Expert}
}
\]

训练之后，不同 Expert 可能形成不同的 specialization。

例如可能出现：

```text
某些 Expert 更擅长代码模式
某些 Expert 更擅长数学模式
某些 Expert 更擅长语言结构
某些 Expert 更偏向某些语义特征
```

但是要注意：

> 我们通常不会人为规定 Expert 0 就是数学专家，Expert 1 就是代码专家。

Expert 的分工通常是：

\[
\boxed{\text{训练过程中自动形成}}
\]

而且实际的分工往往比：

```text
数学专家
代码专家
英语专家
```

复杂得多。

---

<a id="origin-576"></a>
## 10. Router 为什么还要经过 Softmax？

Router 首先输出 logits：

\[
z=xW_r
\]

例如：

\[
z=
[
1,\,
3,\,
2,\,
0
]
\]

再经过：

\[
p=\operatorname{softmax}(z)
\]

假设得到：

\[
p=
[
0.087,\,
0.644,\,
0.237,\,
0.032
]
\]

这表示：

```text
Expert 0 → 0.087
Expert 1 → 0.644
Expert 2 → 0.237
Expert 3 → 0.032
```

并且：

\[
\sum_i p_i=1
\]

这些概率经常叫：

\[
\boxed{\text{Routing Weight}}
\]

或者：

\[
\boxed{\text{Gate Weight}}
\]

---

<a id="origin-643"></a>
## 11. Top-k Routing

假设：

\[
TopK=2
\]

对于：

\[
[
0.087,\,
0.644,\,
0.237,\,
0.032
]
\]

最大的两个是：

```text
Expert 1 → 0.644
Expert 2 → 0.237
```

所以当前 Token 只交给：

```text
Expert 1
Expert 2
```

其余 Expert 不执行。

这就是：

\[
\boxed{\text{Top-k Routing}}
\]

---

<a id="origin-686"></a>
## 12. Top-1 和 Top-2

如果：

\[
TopK=1
\]

那么：

```text
Token
 ↓
Router
 ↓
Expert 3
```

每个 Token 只经过一个 Expert。

优点：

```text
计算量低
```

缺点：

```text
一次路由错误影响比较直接
表达能力可能相对弱一些
```

所以很多 MoE 会使用：

\[
TopK=2
\]

也就是：

> 一个 Token 同时经过两个 Expert。

---

<a id="origin-731"></a>
## 13. Top-k 之后为什么有时还要重新归一化？

假设 Softmax 后：

\[
[
0.1,\,
0.6,\,
0.2,\,
0.1
]
\]

Top-2 选中：

\[
0.6,\ 0.2
\]

它们加起来：

\[
0.8
\]

如果希望最后两个 Expert 的权重之和仍然为：

\[
1
\]

那么重新归一化：

\[
g_1
=
\frac{0.6}{0.8}
=
0.75
\]

\[
g_2
=
\frac{0.2}{0.8}
=
0.25
\]

于是：

\[
g_1+g_2=1
\]

代码中可能会看到：

```python
weight = weight / weight.sum(
    dim=-1,
    keepdim=True
)
```

---

<a id="origin-797"></a>
## 14. 多个 Expert 的输出怎么融合？

假设某个 Token 最终选择：

```text
Expert 1 → 0.7
Expert 5 → 0.3
```

分别执行：

\[
y_1=Expert_1(x)
\]

\[
y_5=Expert_5(x)
\]

最终输出不是简单相加，而是：

\[
y
=
0.7y_1
+
0.3y_5
\]

一般写成：

\[
\boxed{
y=
\sum_{i\in TopK}
g_iExpert_i(x)
}
\]

其中：

\[
g_i
\]

就是当前 Expert 的 Gate Weight。

---

<a id="origin-846"></a>
## 15. 一个完整数字例子

假设有 4 个 Expert：

```text
E0
E1
E2
E3
```

某个 Token 的 hidden state：

\[
x
\]

经过 Router：

\[
z=
[
0.5,\,
2.0,\,
1.5,\,
-1.0
]
\]

Softmax 后假设：

\[
p=
[
0.12,\,
0.53,\,
0.32,\,
0.03
]
\]

Top-2：

```text
Expert 1
Expert 2
```

重新归一化：

\[
g_1
=
\frac{0.53}{0.53+0.32}
\approx0.624
\]

\[
g_2
=
\frac{0.32}{0.53+0.32}
\approx0.376
\]

然后：

\[
y_1=Expert_1(x)
\]

\[
y_2=Expert_2(x)
\]

最后：

\[
\boxed{
y=
0.624y_1
+
0.376y_2
}
\]

---

<a id="origin-933"></a>
## 16. 可以把 MoE 理解成“医院分诊”

一个比较直观的类比：

```text
病人
 ↓
分诊台
 ↓
不同医生
```

其中：

```text
Router = 分诊台

Expert = 专科医生
```

比如：

```text
病人
 ↓
Router
 ↓
70% → 专家 A
30% → 专家 B
```

最后：

\[
y
=
0.7y_A
+
0.3y_B
\]

MoE 的逻辑基本就是这样。

---

<a id="origin-978"></a>
## 17. 从 Batch 角度理解 MoE

真实训练不会只有一个 Token。

输入一般是：

\[
X\in\mathbb R^{B\times T\times D}
\]

例如：

\[
B=2
\]

\[
T=4
\]

\[
D=4096
\]

那么一共有：

\[
B\times T=8
\]

个 Token。

通常先 reshape：

\[
X
\rightarrow
X_f
\]

得到：

\[
X_f
\in
\mathbb R^{8\times4096}
\]

然后所有 Token 一起进入 Router：

\[
R=X_fW_r
\]

假设有 8 个 Expert：

\[
R
\in
\mathbb R^{8\times8}
\]

意思是：

> 8 个 Token，每个 Token 都有 8 个 Expert 分数。

---

<a id="origin-1046"></a>
## 18. 一个 Batch 的路由例子

假设有 5 个 Token：

```text
T0
T1
T2
T3
T4
```

有 4 个 Expert：

```text
E0
E1
E2
E3
```

Top-2 结果：

```text
T0 → E0, E2
T1 → E1, E2
T2 → E0, E3
T3 → E1, E2
T4 → E2, E3
```

真正运行的时候，一般不会写：

```text
先计算 T0
再计算 T1
再计算 T2
...
```

因为这样太慢。

通常会把属于同一个 Expert 的 Token 聚到一起。

所以重新整理成：

```text
E0：
T0
T2

E1：
T1
T3

E2：
T0
T1
T3
T4

E3：
T2
T4
```

然后一次性计算：

```text
E0(T0,T2)

E1(T1,T3)

E2(T0,T1,T3,T4)

E3(T2,T4)
```

这样就可以利用 GPU 的矩阵并行能力。

---

<a id="origin-1128"></a>
## 19. `one_hot` 在 MoE 中是做什么的？

真实代码中经常看到：

```python
expert_mask = F.one_hot(
    topk_idx,
    num_classes=num_experts
)
```

例如：

```text
Token 0 → Expert 1, Expert 3

Token 1 → Expert 0, Expert 2
```

假设一共有 4 个 Expert。

那么：

```text
Expert 0 → [1,0,0,0]
Expert 1 → [0,1,0,0]
Expert 2 → [0,0,1,0]
Expert 3 → [0,0,0,1]
```

通过 one-hot，就可以方便地回答：

> 哪些 Token 选择了 Expert 0？

> 哪些 Token 选择了 Expert 1？

> 哪些 Token 选择了 Expert 2？

这样程序就可以把属于同一个 Expert 的 Token 聚集起来。

---

<a id="origin-1170"></a>
## 20. 一个 Expert 如何批量处理属于自己的 Token？

假设：

```text
Expert 2
```

被以下 Token 选中：

```text
Token 1
Token 4
Token 7
Token 10
```

那么先根据索引取出：

```python
expert_input = x[token_indices]
```

例如得到：

\[
expert\_input
\in
\mathbb R^{4\times4096}
\]

然后一次执行：

```python
expert_output = expert_2(
    expert_input
)
```

得到：

\[
expert\_output
\in
\mathbb R^{4\times4096}
\]

这样 Expert 2 就一次性处理完自己的所有 Token。

---

<a id="origin-1221"></a>
## 21. `output.index_add_()` 到底是干什么的？

这是 MoE 实现里面非常关键的一个操作。

首先不要考虑 MoE。

先单独理解：

```python
output.index_add_(
    dim,
    index,
    source
)
```

它的核心意思是：

\[
\boxed{
\text{把 source 中的内容，根据 index 指定的位置，加到 output 上}
}
\]

注意关键词是：

\[
\boxed{\text{加}}
\]

而不是：

```text
覆盖
```

---

<a id="origin-1259"></a>
## 22. `index_add_` 最简单例子

假设：

```python
import torch

output = torch.tensor([
    10.,
    20.,
    30.,
    40.
])

index = torch.tensor([
    1,
    3
])

source = torch.tensor([
    5.,
    7.
])
```

现在执行：

```python
output.index_add_(
    0,
    index,
    source
)
```

什么意思？

`source[0] = 5`

对应：

```text
index[0] = 1
```

所以：

\[
output[1]
=
output[1]+5
\]

原来：

\[
output[1]=20
\]

变成：

\[
25
\]

---

`source[1] = 7`

对应：

```text
index[1] = 3
```

所以：

\[
output[3]
=
output[3]+7
\]

原来：

\[
40
\]

变成：

\[
47
\]

最终：

```python
tensor([
    10.,
    25.,
    30.,
    47.
])
```

所以：

\[
\boxed{
index\_add_
=
按照 index 指定的位置进行累加
}
\]

---

<a id="origin-1377"></a>
## 23. 为什么叫 `index_add_`？

拆开来看：

```text
index
+
add
+
_
```

`index`：

> 根据索引指定位置。

`add`：

> 执行加法。

最后的：

```text
_
```

表示：

\[
\boxed{\text{in-place}}
\]

即：

> 直接修改原来的 Tensor。

所以：

```python
output.index_add_(...)
```

会直接改变：

```python
output
```

本身。

---

<a id="origin-1429"></a>
## 24. 如果一个 index 重复出现会怎么样？

这正是 `index_add_` 特别适合 MoE 的原因。

例如：

```python
output = torch.tensor([
    0.,
    0.,
    0.
])

index = torch.tensor([
    1,
    1
])

source = torch.tensor([
    3.,
    5.
])
```

执行：

```python
output.index_add_(
    0,
    index,
    source
)
```

第一条：

```text
source[0] = 3
index[0] = 1
```

所以：

\[
output[1]+=3
\]

第二条：

```text
source[1] = 5
index[1] = 1
```

还是：

\[
output[1]+=5
\]

最后：

\[
output[1]=3+5=8
\]

所以结果：

```python
tensor([
    0.,
    8.,
    0.
])
```

也就是说：

> 多个 source 如果指向同一个 index，会自动累加到同一个位置。

这正好对应 MoE：

> 同一个 Token 可以被多个 Expert 选中，所以多个 Expert 的输出最终都要累加回这个 Token。

---

<a id="origin-1515"></a>
## 25. 二维 Tensor 中的 `index_add_`

MoE 里 `output` 一般不是一维，而是：

\[
[Token数,\ hidden\_size]
\]

比如：

```python
output = torch.zeros(
    3,
    2
)
```

得到：

\[
output=
\begin{bmatrix}
0&0\\
0&0\\
0&0
\end{bmatrix}
\]

假设：

```python
index = torch.tensor([
    0,
    2
])
```

然后：

```python
source = torch.tensor([
    [1., 2.],
    [3., 4.]
])
```

执行：

```python
output.index_add_(
    0,
    index,
    source
)
```

含义：

```text
source 第 0 行
加到 output 第 0 行

source 第 1 行
加到 output 第 2 行
```

所以：

\[
output=
\begin{bmatrix}
1&2\\
0&0\\
3&4
\end{bmatrix}
\]

---

<a id="origin-1594"></a>
## 26. `dim=0` 到底是什么意思？

这里：

```python
output.index_add_(
    0,
    index,
    source
)
```

第一个参数：

```python
0
```

表示：

> 沿着第 0 维，也就是“行”进行索引累加。

MoE 中：

\[
output.shape
=
[Token数,\ hidden\_size]
\]

第 0 维就是：

```text
Token 维
```

所以：

```python
dim=0
```

就是：

> 根据 Token 的编号，把 Expert 输出加回对应 Token 的位置。

---

<a id="origin-1642"></a>
## 27. 为什么 MoE 特别适合用 `index_add_`？

假设：

\[
TopK=2
\]

那么一个 Token 会被两个 Expert 处理。

例如：

```text
Token 3
 ↓
Expert 1
Expert 5
```

Expert 1 得到：

\[
E_1(x_3)
\]

Expert 5 得到：

\[
E_5(x_3)
\]

最终：

\[
output_3
=
g_1E_1(x_3)
+
g_5E_5(x_3)
\]

所以：

```text
Token 3 的 output
```

需要被写入两次。

但不是：

```text
第二次覆盖第一次
```

而是：

\[
\boxed{\text{累加}}
\]

因此 `index_add_` 就特别合适。

---

<a id="origin-1707"></a>
## 28. 一个真正对应 MoE 的 `index_add_` 数字例子

假设有 3 个 Token：

```text
T0
T1
T2
```

hidden size 为：

\[
2
\]

先初始化：

```python
output = torch.zeros(
    3,
    2
)
```

即：

\[
output=
\begin{bmatrix}
0&0\\
0&0\\
0&0
\end{bmatrix}
\]

现在 Expert 0 处理了：

```text
T0
T2
```

它得到加权之后的结果：

\[
source=
\begin{bmatrix}
1&2\\
3&4
\end{bmatrix}
\]

对应 Token 索引：

```python
token_idx = torch.tensor([
    0,
    2
])
```

执行：

```python
output.index_add_(
    0,
    token_idx,
    source
)
```

结果：

\[
output=
\begin{bmatrix}
1&2\\
0&0\\
3&4
\end{bmatrix}
\]

---

接下来 Expert 1 又处理了：

```text
T0
T1
```

得到：

\[
source=
\begin{bmatrix}
5&6\\
7&8
\end{bmatrix}
\]

对应：

```python
token_idx = torch.tensor([
    0,
    1
])
```

再次执行：

```python
output.index_add_(
    0,
    token_idx,
    source
)
```

那么：

```text
T0 已经有 Expert 0 的结果了

现在再把 Expert 1 的结果加进去
```

所以：

\[
T0:
[1,2]+[5,6]
=
[6,8]
\]

T1：

\[
[0,0]+[7,8]
=
[7,8]
\]

T2 不变：

\[
[3,4]
\]

最终：

\[
\boxed{
output=
\begin{bmatrix}
6&8\\
7&8\\
3&4
\end{bmatrix}
}
\]

这就是 MoE 中：

\[
\boxed{
\text{多个 Expert 的结果重新聚合回原 Token}
}
\]

的过程。

---

<a id="origin-1884"></a>
## 29. 把 Gate Weight 也放进来

真实 MoE 中不是直接：

\[
E_i(x)
\]

写回。

而是：

\[
g_iE_i(x)
\]

例如：

```text
Token 0
```

经过：

```text
Expert 0，权重 0.7
Expert 1，权重 0.3
```

Expert 0 输出：

\[
[2,4]
\]

加权后：

\[
0.7[2,4]
=
[1.4,2.8]
\]

Expert 1 输出：

\[
[10,20]
\]

加权后：

\[
0.3[10,20]
=
[3,6]
\]

那么：

```python
output.index_add_(...)
```

第一次写入：

\[
[1.4,2.8]
\]

第二次继续加：

\[
[3,6]
\]

最后：

\[
output_0
=
[1.4,2.8]+[3,6]
\]

得到：

\[
\boxed{
[4.4,8.8]
}
\]

这正好就是：

\[
0.7E_0(x)
+
0.3E_1(x)
\]

---

<a id="origin-1985"></a>
## 30. 对应到常见 MoE 代码

可能看到：

```python
output.index_add_(
    0,
    token_idx,
    expert_output * weight
)
```

逐项解释：

```python
output
```

表示：

> 所有 Token 最终的 MoE 输出。

shape 一般：

\[
[BT,D]
\]

---

```python
token_idx
```

表示：

> 当前这些 Expert 输出应该写回哪些 Token。

例如：

```text
[0, 3, 7, 10]
```

说明当前 Expert 处理的是：

```text
Token 0
Token 3
Token 7
Token 10
```

---

```python
expert_output
```

表示：

> 当前 Expert 对这些 Token 的计算结果。

---

```python
weight
```

表示：

> 每个 Token 对当前 Expert 的 Gate Weight。

---

所以：

```python
expert_output * weight
```

就是：

\[
g_iE_i(x)
\]

然后：

```python
output.index_add_(
    0,
    token_idx,
    ...
)
```

就是：

> 把这些加权 Expert 输出累加回原来的 Token 位置。

因此整行代码本质上就是在实现：

\[
\boxed{
y_t
=
\sum_{i\in TopK(t)}
g_{t,i}E_i(x_t)
}
\]

---

<a id="origin-2099"></a>
## 31. 为什么不能简单写 `output[token_idx] = expert_output`？

因为这样是：

\[
\boxed{\text{覆盖}}
\]

假设：

```text
Token 0
```

先经过：

```text
Expert 1
```

结果：

\[
[1,2]
\]

如果：

```python
output[0] = [1,2]
```

然后 Token 0 又经过：

```text
Expert 5
```

得到：

\[
[3,4]
\]

再执行：

```python
output[0] = [3,4]
```

那么：

```text
Expert 1 的结果没了
```

最后只剩：

\[
[3,4]
\]

这是错误的。

我们真正需要：

\[
[1,2]+[3,4]
=
[4,6]
\]

所以需要：

```python
index_add_
```

而不是简单赋值。

---

<a id="origin-2181"></a>
## 32. 一句话记住 `index_add_`

核心关系如下：

\[
\boxed{
\texttt{index\_add\_}
=
\text{根据索引，把结果“加回”原来的位置}
}
\]

在 MoE 中：

\[
\boxed{
\text{不同 Expert 的输出最终要加回对应 Token}
}
\]

所以它非常适合实现 Expert 输出聚合。

---

<a id="origin-2205"></a>
## 33. MoE 最大的问题：Expert 负载不均衡

假设有 8 个 Expert。

本来希望：

```text
不同 Token 分散到不同 Expert
```

但训练过程中 Router 可能发现：

```text
Expert 3 好像比较好用
```

于是大量 Token 都去：

```text
Expert 3
```

例如：

```text
Token 1 → E3
Token 2 → E3
Token 3 → E3
Token 4 → E3
...
```

最终：

```text
E3：非常拥挤

其他 Expert：几乎没人用
```

这叫：

\[
\boxed{\text{Load Imbalance}}
\]

即：

> 负载不均衡。

---

<a id="origin-2257"></a>
## 34. 为什么会出现 Expert Collapse？

假设训练早期：

```text
Expert 3 偶然表现稍好
```

于是 Router 更喜欢它：

```text
更多 Token → Expert 3
```

Expert 3 因为收到更多 Token：

```text
获得更多训练
```

于是变得更强。

Router 又会：

```text
更加喜欢 Expert 3
```

形成：

```text
稍微强
 ↓
收到更多 Token
 ↓
训练更多
 ↓
变得更强
 ↓
收到更多 Token
```

最终可能出现：

\[
\boxed{\text{Expert Collapse}}
\]

也就是：

> 大部分 Token 都集中到少数几个 Expert。

---

<a id="origin-2311"></a>
## 35. 为什么 Expert Collapse 很严重？

第一：

```text
很多 Expert 参数几乎没被使用
```

也就是：

> 参数浪费。

第二：

```text
某些 Expert 过载
```

如果 Expert 分布在不同 GPU：

```text
GPU0 很忙
GPU1 很闲
GPU2 很闲
GPU3 爆满
```

于是整个训练速度取决于最慢的那个 GPU。

所以：

> Expert Collapse 不只是模型问题，也是系统性能问题。

---

<a id="origin-2346"></a>
## 36. 解决办法：Auxiliary Loss

因此 MoE 通常会增加一个：

\[
\boxed{\text{Auxiliary Loss}}
\]

简称：

```text
Aux Loss
```

它不是用来预测下一个 Token 的。

它主要用来：

\[
\boxed{\text{鼓励 Expert 之间负载更加均衡}}
\]

总 Loss 可能是：

\[
L
=
L_{\text{LM}}
+
\lambda L_{\text{aux}}
\]

其中：

\[
L_{\text{LM}}
\]

是普通语言模型 Cross Entropy。

而：

\[
L_{\text{aux}}
\]

是 MoE 的负载均衡损失。

---

<a id="origin-2396"></a>
## 37. \(f_i\) 和 \(P_i\) 到底是什么？

一个经典形式是：

\[
\boxed{
L_{\text{aux}}
=
N
\sum_{i=1}^{N}
f_iP_i
}
\]

其中：

\[
N
\]

表示 Expert 数量。

两个最重要的量：

\[
\boxed{
f_i
=
\text{Expert i 实际接到了多少 Token}
}
\]

而：

\[
\boxed{
P_i
=
\text{Router 平均有多喜欢 Expert i}
}
\]

这两个很像，但完全不同。

---

<a id="origin-2442"></a>
## 38. 用完整数字例子理解 \(P_i\)

假设有 4 个 Expert：

```text
E0
E1
E2
E3
```

有 4 个 Token：

```text
T1
T2
T3
T4
```

Router Softmax 后得到：

\[
P=
\begin{bmatrix}
0.10 & 0.20 & 0.60 & 0.10\\
0.05 & 0.15 & 0.70 & 0.10\\
0.10 & 0.10 & 0.70 & 0.10\\
0.05 & 0.15 & 0.75 & 0.05
\end{bmatrix}
\]

每一行：

> 一个 Token 对四个 Expert 的概率。

例如第一行：

\[
[0.10,0.20,0.60,0.10]
\]

表示：

```text
T1 对 E0：0.10
T1 对 E1：0.20
T1 对 E2：0.60
T1 对 E3：0.10
```

---

<a id="origin-2495"></a>
## 39. \(P_i\)：看 Router 的平均偏好

例如 E2。

四个 Token 对 E2 的概率：

\[
0.60,\ 0.70,\ 0.70,\ 0.75
\]

所以：

\[
P_2
=
\frac{
0.60+0.70+0.70+0.75
}{4}
\]

得到：

\[
P_2=0.6875
\]

意思是：

> Router 对这批 Token 平均把 68.75% 的概率放到了 Expert 2 上。

其他 Expert：

\[
P_0
=
\frac{
0.10+0.05+0.10+0.05
}{4}
=
0.075
\]

\[
P_1
=
0.15
\]

\[
P_3
=
0.0875
\]

所以：

\[
\boxed{
P=
[
0.075,\,
0.15,\,
0.6875,\,
0.0875
]
}
\]

---

<a id="origin-2565"></a>
## 40. \(f_i\)：看真正的路由结果

现在假设：

\[
TopK=1
\]

每个 Token 只选概率最大的 Expert。

刚才：

```text
T1 → E2
T2 → E2
T3 → E2
T4 → E2
```

所以：

```text
E0：0 个 Token

E1：0 个 Token

E2：4 个 Token

E3：0 个 Token
```

总共有：

\[
4
\]

个 Token。

于是：

\[
f_0=0
\]

\[
f_1=0
\]

\[
f_2=1
\]

\[
f_3=0
\]

所以：

\[
\boxed{
f=
[
0,\,
0,\,
1,\,
0
]
}
\]

---

<a id="origin-2638"></a>
## 41. \(f_i\) 和 \(P_i\) 的区别

放在一起：

| Expert | \(f_i\) | \(P_i\) |
|---|---:|---:|
| E0 | 0 | 0.075 |
| E1 | 0 | 0.15 |
| E2 | 1 | 0.6875 |
| E3 | 0 | 0.0875 |

其中：

\[
f_2=1
\]

意思是：

> 实际上 100% 的 Token 都被送给 E2。

而：

\[
P_2=0.6875
\]

意思是：

> Router 平均给 E2 68.75% 的概率。

所以：

\[
\boxed{
f_i=\text{实际选择结果}
}
\]

而：

\[
\boxed{
P_i=\text{Router 的软概率偏好}
}
\]

---

<a id="origin-2687"></a>
## 42. 为什么要用 \(f_iP_i\)？

如果某个 Expert：

```text
实际接到了很多 Token
```

也就是：

\[
f_i
\]

很大。

同时 Router：

```text
还特别喜欢它
```

也就是：

\[
P_i
\]

也很大。

那么：

\[
f_iP_i
\]

就会很大。

所以：

\[
\boxed{
f_iP_i
}
\]

可以理解为：

> 某个 Expert 既真的很忙，又被 Router 特别偏爱的程度。

---

<a id="origin-2739"></a>
## 43. 计算刚才的 Aux Loss

前面：

\[
f=
[
0,0,1,0
]
\]

\[
P=
[
0.075,\,
0.15,\,
0.6875,\,
0.0875
]
\]

那么：

\[
f_0P_0=0
\]

\[
f_1P_1=0
\]

\[
f_2P_2
=
1\times0.6875
=
0.6875
\]

\[
f_3P_3=0
\]

所以：

\[
\sum_i f_iP_i
=
0.6875
\]

因为：

\[
N=4
\]

于是：

\[
L_{\text{aux}}
=
4\times0.6875
\]

得到：

\[
\boxed{
L_{\text{aux}}
=
2.75
}
\]

说明：

> Router 当前明显过度偏爱 E2。

---

<a id="origin-2820"></a>
### 43.1 Top-k MoE Auxiliary Loss：一般公式与数值例子

假设：

- 一共有 \(T\) 个 Token
- 一共有 \(E\) 个 Expert
- 每个 Token 选择 \(K\) 个 Expert

我们先定义两个量。

---

<a id="origin-2832"></a>
## 44. Router 对 Expert 的平均偏好：\(P_i\)

对于第 \(t\) 个 Token，Router 给 Expert \(i\) 的概率记为：

\[
p_{t,i}
\]

并且：

\[
\sum_{i=1}^{E} p_{t,i}=1
\]

那么 Expert \(i\) 的平均 Router 概率为：

\[
\boxed{
P_i
=
\frac{1}{T}
\sum_{t=1}^{T}
p_{t,i}
}
\]

它表示：

> Router 平均有多喜欢 Expert \(i\)。

---

<a id="origin-2864"></a>
## 45. Expert 的实际负载：\(f_i\)

对于 Top-\(K\) Routing，每个 Token 会实际选择 \(K\) 个 Expert。

因此一共会产生：

\[
T\times K
\]

次 Expert 选择。

定义：

\[
\boxed{
f_i
=
\frac{
\text{Expert }i\text{ 被选中的总次数}
}{
T\times K
}
}
\]

因此：

\[
\sum_{i=1}^{E}f_i=1
\]

它表示：

> 所有实际路由中，有多大比例最终去了 Expert \(i\)。

---

<a id="origin-2902"></a>
## 46. 最一般、最直观的 Auxiliary Loss

常见的负载均衡思想可以写成：

\[
\boxed{
L_{\text{aux}}
=
E
\sum_{i=1}^{E}
f_iP_i
}
\]

如果再乘一个辅助损失系数：

\[
\lambda
\]

那么：

\[
\boxed{
L_{\text{aux}}
=
\lambda E
\sum_{i=1}^{E}
f_iP_i
}
\]

这就是最值得记住的形式。

其中：

\[
\boxed{
f_i
=
\text{Expert }i\text{ 实际承担的路由比例}
}
\]

\[
\boxed{
P_i
=
\text{Router 平均给 Expert }i\text{ 的概率}
}
\]

所以：

\[
\boxed{
f_iP_i
}
\]

可以理解成：

> Expert \(i\) 实际已经很忙，并且 Router 还很偏爱它的程度。

---

<a id="origin-2968"></a>
## 47. 为什么这个公式能衡量负载不均衡？

如果某个 Expert：

\[
f_i
\]

很大，说明：

> 实际很多 Token 都去了它。

同时：

\[
P_i
\]

也很大，说明：

> Router 本身也一直偏爱它。

那么：

\[
f_iP_i
\]

就会很大。

因此：

\[
L_{\text{aux}}
\]

会增大。

训练为了降低这个 Loss，就会倾向于：

\[
P_i\downarrow
\]

也就是：

> Router 不要继续过度偏爱已经很忙的 Expert。

---

<a id="origin-3018"></a>
## 48. 完全均衡时是什么情况？

假设：

\[
E
\]

个 Expert 完全均衡。

那么：

\[
f_i=\frac1E
\]

同时：

\[
P_i=\frac1E
\]

于是：

\[
\sum_{i=1}^{E} f_iP_i
=
E\times
\frac1E
\times
\frac1E
\]

得到：

\[
\frac1E
\]

所以：

\[
L_{\text{aux}}
=
E\times\frac1E
=
1
\]

因此不考虑 \(\lambda\) 时：

\[
\boxed{
\text{理想均衡状态下 }L_{\text{aux}}=1
}
\]

如果带系数：

\[
\lambda
\]

则：

\[
\boxed{
L_{\text{aux}}=\lambda
}
\]

---

<a id="origin-3091"></a>
## 49. Top-2 的具体数值例子

现在设：

\[
E=4
\]

即有 4 个 Expert：

\[
E_0,E_1,E_2,E_3
\]

有：

\[
T=4
\]

个 Token。

每个 Token 选择：

\[
K=2
\]

个 Expert。

因此总共有：

\[
T\times K
=
4\times2
=
8
\]

次 Expert 选择。

---

<a id="origin-3135"></a>
## 50. 假设 Router 的概率如下

4 个 Token 的 Router 概率分别是：

\[
\begin{aligned}
T_1 &: [0.50,\ 0.30,\ 0.15,\ 0.05]\\
T_2 &: [0.40,\ 0.35,\ 0.15,\ 0.10]\\
T_3 &: [0.45,\ 0.20,\ 0.25,\ 0.10]\\
T_4 &: [0.35,\ 0.30,\ 0.25,\ 0.10]
\end{aligned}
\]

---

<a id="origin-3150"></a>
## 51. 先计算 \(P_i\)

Expert 0：

\[
P_0
=
\frac{
0.50+0.40+0.45+0.35
}{4}
\]

所以：

\[
P_0
=
\frac{1.70}{4}
=
0.425
\]

---

Expert 1：

\[
P_1
=
\frac{
0.30+0.35+0.20+0.30
}{4}
\]

所以：

\[
P_1
=
\frac{1.15}{4}
=
0.2875
\]

---

Expert 2：

\[
P_2
=
\frac{
0.15+0.15+0.25+0.25
}{4}
\]

所以：

\[
P_2
=
0.20
\]

---

Expert 3：

\[
P_3
=
\frac{
0.05+0.10+0.10+0.10
}{4}
\]

所以：

\[
P_3
=
0.0875
\]

因此：

\[
\boxed{
P=
[
0.425,\,
0.2875,\,
0.20,\,
0.0875
]
}
\]

检查：

\[
0.425+0.2875+0.20+0.0875
=
1
\]

---

<a id="origin-3258"></a>
## 52. Top-2 实际选择结果

每个 Token 选择概率最大的两个 Expert。

所以：

\[
T_1
\rightarrow
E_0,E_1
\]

\[
T_2
\rightarrow
E_0,E_1
\]

\[
T_3
\rightarrow
E_0,E_2
\]

\[
T_4
\rightarrow
E_0,E_1
\]

总共 8 次路由：

```text
E0 被选择 4 次
E1 被选择 3 次
E2 被选择 1 次
E3 被选择 0 次
```

---

<a id="origin-3299"></a>
## 53. 计算 \(f_i\)

因为总选择次数：

\[
8
\]

所以：

\[
f_0
=
\frac48
=
0.5
\]

\[
f_1
=
\frac38
=
0.375
\]

\[
f_2
=
\frac18
=
0.125
\]

\[
f_3
=
0
\]

因此：

\[
\boxed{
f=
[
0.5,\,
0.375,\,
0.125,\,
0
]
}
\]

检查：

\[
0.5+0.375+0.125=1
\]

---

<a id="origin-3361"></a>
## 54. 计算 \(f_iP_i\)

Expert 0：

\[
f_0P_0
=
0.5\times0.425
=
0.2125
\]

Expert 1：

\[
f_1P_1
=
0.375\times0.2875
\]

约：

\[
0.1078
\]

Expert 2：

\[
f_2P_2
=
0.125\times0.20
=
0.025
\]

Expert 3：

\[
f_3P_3
=
0\times0.0875
=
0
\]

---

<a id="origin-3409"></a>
## 55. 求和

\[
\sum_i f_iP_i
=
0.2125
+
0.1078
+
0.025
\]

约：

\[
0.3453
\]

因为：

\[
E=4
\]

所以：

\[
L_{\text{aux}}
=
4\times0.3453
\]

得到：

\[
\boxed{
L_{\text{aux}}
\approx1.381
}
\]

如果：

\[
\lambda=0.01
\]

那么：

\[
L_{\text{aux}}
=
0.01\times1.381
\]

最终：

\[
\boxed{
L_{\text{aux}}
\approx0.01381
}
\]

---

<a id="origin-3475"></a>
## 56. 为什么 1.381 说明不够均衡？

因为完全均衡时：

\[
L_{\text{aux}}=1
\]

现在：

\[
L_{\text{aux}}\approx1.381
\]

说明负载存在明显偏斜。

从 \(f\) 也能直接看出来：

\[
f=
[
0.5,\,
0.375,\,
0.125,\,
0
]
\]

其中：

```text
E0：50%
E1：37.5%
E2：12.5%
E3：0%
```

显然：

> E0 和 E1 很忙，而 E3 完全没人用。

所以 Aux Loss 比理想状态更高。

---

<a id="origin-3520"></a>
## 57. 再看完全均衡的 Top-2 情况

仍然：

\[
T=4,\quad K=2,\quad E=4
\]

总路由次数：

\[
8
\]

如果每个 Expert 都恰好被选：

\[
2
\]

次，那么：

\[
f_i
=
\frac28
=
0.25
\]

所以：

\[
f=
[
0.25,
0.25,
0.25,
0.25
]
\]

如果 Router 的平均偏好也是：

\[
P=
[
0.25,
0.25,
0.25,
0.25
]
\]

那么：

\[
\sum_i f_iP_i
=
4\times0.25\times0.25
=
0.25
\]

所以：

\[
L_{\text{aux}}
=
4\times0.25
=
\boxed{1}
\]

这就是理想均衡状态。

---

<a id="origin-3598"></a>
## 58. 最后只记这三个公式

Router 平均偏好：

\[
\boxed{
P_i
=
\frac1T
\sum_{t=1}^{T}
p_{t,i}
}
\]

Expert 实际负载：

\[
\boxed{
f_i
=
\frac{
\text{Expert }i\text{ 被 Top-k 选中的次数}
}{
T K
}
}
\]

最终 Aux Loss：

\[
\boxed{
L_{\text{aux}}
=
\lambda E
\sum_{i=1}^{E}
f_iP_i
}
\]

---

<a id="origin-3640"></a>
## 59. 一句话理解

\[
\boxed{
f_i
=
\text{Expert }i\text{ 实际接了多少活}
}
\]

\[
\boxed{
P_i
=
\text{Router 平均有多喜欢 Expert }i
}
\]

所以：

\[
\boxed{
f_iP_i
=
\text{这个 Expert 已经很忙，Router 却还继续偏爱它的程度}
}
\]

Aux Loss 的作用就是：

> 让这种“又忙、又持续被偏爱”的 Expert 得到惩罚，从而推动 Router 把更多 Token 分散到其他 Expert。

---
<a id="origin-3673"></a>
## 60. 完全均衡的时候是什么样？

假设：

```text
T1 → E0
T2 → E1
T3 → E2
T4 → E3
```

那么：

\[
f=
[
0.25,\,
0.25,\,
0.25,\,
0.25
]
\]

如果 Router 平均概率也完全均衡：

\[
P=
[
0.25,\,
0.25,\,
0.25,\,
0.25
]
\]

那么：

\[
\sum_i f_iP_i
=
4\times0.25\times0.25
\]

得到：

\[
0.25
\]

再乘：

\[
N=4
\]

所以：

\[
\boxed{
L_{\text{aux}}=1
}
\]

---

<a id="origin-3738"></a>
## 61. 为什么理想值不是 0，而是 1？

因为完全均衡时：

\[
f_i
=
\frac1N
\]

同时：

\[
P_i
=
\frac1N
\]

所以：

\[
\sum_i f_iP_i
=
N
\times
\frac1N
\times
\frac1N
\]

得到：

\[
\frac1N
\]

再乘：

\[
N
\]

就得到：

\[
\boxed{1}
\]

因此对于这种定义：

\[
\boxed{
L_{\text{aux}}
\text{ 越接近 1，通常越均衡}
}
\]

---

<a id="origin-3797"></a>
## 62. 如果所有 Token 都去一个 Expert

假设：

\[
N=4
\]

并且：

\[
f=
[
0,0,1,0
]
\]

Router 也几乎完全偏向 E2：

\[
P=
[
0,0,1,0
]
\]

那么：

\[
\sum_i f_iP_i=1
\]

所以：

\[
L_{\text{aux}}
=
4
\]

即：

\[
\boxed{
L_{\text{aux}}=4
}
\]

而完全均衡时：

\[
L_{\text{aux}}=1
\]

所以优化目标会倾向于：

```text
4
↓
1
```

即推动 Expert 负载更加均衡。

---

<a id="origin-3863"></a>
## 63. 为什么不直接只用 \(f_i\)？

这是很关键的一点。

有人可能会想：

> \(f_i\) 已经表示实际负载了，直接让所有 \(f_i\) 接近平均不就行了吗？

问题是：

\[
f_i
\]

通常来自：

```text
Top-k
argmax
```

也就是：

```text
选中 Expert 2
没选中 Expert 1
```

这是一个离散选择。

因此：

\[
f_i
\]

本身很难直接给 Router 提供平滑梯度。

---

<a id="origin-3903"></a>
## 64. 为什么需要 \(P_i\)？

因为：

\[
P_i
\]

来自：

\[
softmax(W_rx)
\]

它是连续的。

因此：

\[
\boxed{
P_i
\text{ 可以反向传播}
}
\]

所以：

```text
f_i
```

负责告诉模型：

> 实际负载是什么样。

而：

```text
P_i
```

负责：

> 给 Router 提供可微的调整方向。

因此：

\[
f_iP_i
\]

把：

```text
实际负载
```

和：

```text
可微 Router 概率
```

连接起来。

---

<a id="origin-3970"></a>
## 65. 一个更直观的理解

可以把：

\[
f_i
\]

理解成：

> 这个专家实际接到了多少活。

把：

\[
P_i
\]

理解成：

> 老板有多想继续把活交给这个专家。

比如：

```text
Expert 2 已经接了 70% 的工作
```

即：

\[
f_2=0.7
\]

而 Router 还给它：

\[
P_2=0.6
\]

那么：

\[
f_2P_2
=
0.42
\]

很大。

说明：

> 它已经很忙了，Router 还特别喜欢继续给它派活。

Aux Loss 就会惩罚这种行为。

---

<a id="origin-4028"></a>
## 66. 为什么 \(f_iP_i\) 可以推动 Router 改变？

假设：

\[
f_2=0.7
\]

那么：

\[
f_2P_2
=
0.7P_2
\]

这时：

\[
P_2
\]

稍微增加一点，Loss 就增加得比较明显。

于是梯度会推动：

\[
P_2\downarrow
\]

也就是：

> Router 不要继续那么偏爱 Expert 2。

其他负载较低的 Expert：

\[
f_i
\]

较小，因此对应惩罚较小。

最终 Router 会慢慢把更多概率分配给其他 Expert。

---

<a id="origin-4074"></a>
## 67. 一句话记住 \(f_i\) 和 \(P_i\)

可以概括为：

\[
\boxed{
f_i
=
\text{这个 Expert 实际接到了多少活}
}
\]

\[
\boxed{
P_i
=
\text{Router 平均有多想把活给它}
}
\]

而：

\[
\boxed{
f_iP_i
=
\text{它既已经很忙、Router 又继续偏爱它的程度}
}
\]

---

<a id="origin-4106"></a>
## 68. Capacity 是什么？

即使有 Aux Loss，某个 Batch 仍然可能瞬间有很多 Token 去同一个 Expert。

所以一些 MoE 会规定：

\[
\boxed{\text{Expert Capacity}}
\]

即：

> 一个 Expert 最多允许处理多少 Token。

例如：

```text
Expert Capacity = 1000
```

如果当前 Expert 收到：

```text
1200 Token
```

那么多出来：

```text
200 Token
```

可能会：

```text
丢弃
重新路由
或者特殊处理
```

具体看模型实现。

---

<a id="origin-4150"></a>
## 69. Capacity Factor

通常：

\[
Capacity
=
CapacityFactor
\times
\frac{
Tokens\times TopK
}{
N_{expert}
}
\]

例如：

\[
Tokens=1024
\]

\[
TopK=2
\]

\[
N_{expert}=8
\]

一共会产生：

\[
1024\times2
=
2048
\]

次 Expert 分配。

平均每个 Expert：

\[
2048/8
=
256
\]

如果：

\[
CapacityFactor=1.25
\]

那么：

\[
Capacity
=
256\times1.25
=
320
\]

所以一个 Expert 最多允许处理大约：

\[
320
\]

个 Token。

---

<a id="origin-4224"></a>
## 70. 为什么 MoE 参数很大，但计算量没有同比增长？

假设每个 FFN 参数量为：

\[
100M
\]

Dense：

```text
一个 FFN
```

总参数：

\[
100M
\]

每个 Token 计算：

\[
100M
\]

对应的 FFN 参数。

---

MoE：

```text
8 个 Expert
```

每个：

\[
100M
\]

所以总 Expert 参数：

\[
800M
\]

但是：

\[
TopK=2
\]

每个 Token 只经过两个 Expert。

因此每 Token 激活的 Expert 参数大约：

\[
200M
\]

所以：

```text
总参数：800M

单 Token 激活：200M
```

这就是：

\[
\boxed{
\text{Total Parameters}
\neq
\text{Activated Parameters}
}
\]

---

<a id="origin-4306"></a>
## 71. MoE 中哪些部分仍然是 Dense 的？

MoE 并不是整个 Transformer 都稀疏。

通常：

```text
Embedding
Attention
Norm
Router
```

依旧会被所有 Token 使用。

只有：

```text
Expert FFN
```

是稀疏激活。

因此：

```text
Token
 ↓
Attention        ← 每个 Token 都算
 ↓
Router           ← 每个 Token 都算
 ↓
Top-k Experts    ← 只算少数 Expert
 ↓
Output
```

---

<a id="origin-4345"></a>
## 72. Router 参数量大吗？

通常并不大。

例如：

\[
d=4096
\]

有：

\[
8
\]

个 Expert。

Router：

\[
W_r
\in
\mathbb R^{4096\times8}
\]

参数量：

\[
4096\times8
=
32768
\]

而一个 FFN 可能有数千万甚至上亿参数。

所以：

\[
\boxed{
Router 本身通常不是参数大户
}
\]

---

<a id="origin-4391"></a>
## 73. MoE 真正困难的地方：Token Dispatch

数学上：

\[
y=
\sum_i g_iE_i(x)
\]

其实并不复杂。

真正困难的是：

> Token 到底怎么快速送到正确的 Expert。

特别是在多个 GPU 上。

例如：

```text
GPU0：Expert 0,1
GPU1：Expert 2,3
GPU2：Expert 4,5
GPU3：Expert 6,7
```

现在 GPU0 上某个 Token：

```text
需要 Expert 6
```

那它的数据就需要送到：

```text
GPU3
```

另一个 Token：

```text
需要 Expert 2
```

则需要送到：

```text
GPU1
```

所以会产生大量 GPU 之间的数据交换。

---

<a id="origin-4445"></a>
## 74. All-to-All Communication

MoE 训练中经常需要：

\[
\boxed{\text{All-to-All Communication}}
\]

例如：

```text
GPU0 → GPU1
GPU0 → GPU3
GPU1 → GPU2
GPU2 → GPU0
GPU3 → GPU1
...
```

Token 先被发送到 Expert 所在 GPU。

Expert 计算完成之后：

```text
Expert Output
```

又要送回原来的位置。

所以：

> MoE 算法本身并不复杂，但大规模系统实现非常复杂。

---

<a id="origin-4480"></a>
## 75. Expert Parallelism

普通大模型常见：

```text
Data Parallel

Tensor Parallel

Pipeline Parallel
```

MoE 又多了一个非常重要的并行方式：

\[
\boxed{\text{Expert Parallelism}}
\]

例如：

```text
GPU0：
Expert 0
Expert 1

GPU1：
Expert 2
Expert 3

GPU2：
Expert 4
Expert 5

GPU3：
Expert 6
Expert 7
```

Router 计算完：

```text
Token → 对应 Expert 所在 GPU
```

计算完成：

```text
Expert Output → 返回
```

---

<a id="origin-4532"></a>
## 76. Router 是怎么训练的？

最终 MoE 输出：

\[
y=
g_1E_1(x)+g_3E_3(x)
\]

假设最终 Loss：

\[
L
\]

那么梯度可以通过：

\[
g_1
\]

和：

\[
g_3
\]

反向传播。

因为：

\[
g
=
softmax(W_rx)
\]

所以可以继续：

\[
\frac{\partial L}
{\partial W_r}
\]

于是 Router 参数：

\[
W_r
\]

也会被训练。

所以 Router 并不是人工规则，而是：

\[
\boxed{\text{可学习模块}}
\]

---

<a id="origin-4592"></a>
## 77. Top-k 明明是离散的，为什么还能训练？

Top-k 的：

```text
索引选择
```

本身确实是离散的。

例如：

```text
选 E1
选 E3
```

但被选中的 Expert 对应的 Gate Weight：

\[
g_1
\]

\[
g_3
\]

仍然来自可微的：

\[
softmax
\]

所以：

\[
y=
g_1E_1(x)
+
g_3E_3(x)
\]

仍然可以对：

\[
g_1,g_3
\]

求梯度。

再继续传播到 Router 参数。

所以可以简单理解：

> Expert 索引本身不是普通连续变量，但被选 Expert 的概率权重仍然可以参与梯度计算。

---

<a id="origin-4650"></a>
## 78. Expert 为什么会慢慢形成不同能力？

关键原因：

> 不同 Expert 收到的 Token 不一样。

例如训练一段时间后：

```text
E0 经常收到某类代码 Token

E1 经常收到某类语言结构

E2 经常收到某类数学结构

E3 经常收到另一类语义模式
```

那么：

\[
E_0
\]

收到的梯度数据和：

\[
E_1
\]

不一样。

所以它们的参数更新方向也会不同。

久而久之就产生：

\[
\boxed{\text{Expert Specialization}}
\]

---

<a id="origin-4692"></a>
## 79. 一个 Token 会更新所有 Expert 吗？

不会。

如果：

\[
TopK=2
\]

某个 Token 只经过：

```text
Expert 1
Expert 5
```

那么这个 Token 对 Expert 部分的梯度，主要只会更新：

```text
Expert 1

Expert 5
```

而：

```text
Expert 0
Expert 2
Expert 3
Expert 4
...
```

并不会因为这个 Token 直接得到同样的 Expert 梯度。

所以：

\[
\boxed{
\text{不同 Expert 收到不同训练数据}
}
\]

这正是它们形成不同能力的重要原因。

---

<a id="origin-4741"></a>
## 80. 同一个词是否永远去同一个 Expert？

不是。

Router 输入的是：

\[
\boxed{\text{当前层 hidden state}}
\]

不是单纯的：

```text
Token ID
```

例如：

```text
Apple released a new iPhone.
```

里面的：

```text
Apple
```

和：

```text
I ate an apple.
```

里面的：

```text
apple
```

虽然词面相似，但经过上下文 Attention 之后，hidden state 不一样。

因此：

\[
\boxed{
\text{完全可能走不同 Expert}
}
\]

所以 MoE Routing 是：

\[
\boxed{\text{Context-Aware}}
\]

的。

---

<a id="origin-4801"></a>
## 81. 同一个 Token 在不同层会选同一个 Expert 吗？

也不一定。

例如 Token：

```text
"model"
```

在第 5 层：

```text
Expert 1
Expert 3
```

到第 10 层：

```text
Expert 4
Expert 7
```

到第 20 层：

```text
Expert 2
Expert 6
```

因为每一层的 hidden state 已经不同。

而且不同层一般也有自己的 Router。

因此 Routing 还是：

\[
\boxed{\text{Layer-dependent}}
\]

的。

---

<a id="origin-4846"></a>
## 82. Shared Expert 是什么？

一些 MoE 架构还会加入：

\[
\boxed{\text{Shared Expert}}
\]

即：

> 不管 Router 选谁，每个 Token 都会经过这个共享 Expert。

结构类似：

```text
                 → Shared Expert

Token
                 → Router → Top-k Routed Experts
```

然后：

\[
y
=
E_{shared}(x)
+
\sum_{i\in TopK}
g_iE_i(x)
\]

---

<a id="origin-4880"></a>
## 83. Shared Expert 可以怎么理解？

可以直观理解为：

```text
Shared Expert
=
所有 Token 都需要的公共能力
```

而：

```text
Routed Experts
=
更加专门化的能力
```

例如可能把一些：

```text
通用语言能力
基础模式
公共表示
```

交给 Shared Expert。

而让 Routed Experts 专注于更有差异性的能力。

---

<a id="origin-4912"></a>
## 84. Gate 和 Router 是什么关系？

代码里面可能看到：

```python
self.gate
```

也可能看到：

```python
self.router
```

在很多 MoE 实现中，它们表达的核心作用基本一致：

\[
\boxed{
\text{根据 hidden state 计算各个 Expert 的分数}
}
\]

所以在很多代码里可以近似理解：

\[
\boxed{
Gate
\approx
Router
}
\]

只是名字不同。

---

<a id="origin-4948"></a>
## 85. MoE 常见代码结构

例如：

```python
class MOEFeedForward(nn.Module):
```

里面一般会有：

```python
self.gate

self.experts
```

例如：

```python
self.experts = nn.ModuleList(
    [
        FeedForward(config)
        for _ in range(
            config.n_routed_experts
        )
    ]
)
```

意思是：

> 创建多个独立的 FFN。

其中：

```python
experts[0]
experts[1]
experts[2]
...
```

每一个都有自己独立的参数。

---

<a id="origin-4994"></a>
## 86. Gate 的典型 shape

原始输入：

\[
x
\in
\mathbb R^{B\times T\times D}
\]

先变成：

\[
x
\in
\mathbb R^{BT\times D}
\]

例如：

```python
x = x.view(
    -1,
    hidden_size
)
```

然后：

```python
logits = self.gate(x)
```

得到：

\[
logits
\in
\mathbb R^{BT\times N_{expert}}
\]

即：

> 每个 Token 对所有 Expert 的 Router 分数。

---

<a id="origin-5041"></a>
## 87. Top-k 代码

常见：

```python
weight, ids = torch.topk(
    scores,
    k=top_k,
    dim=-1
)
```

例如：

```text
Token 0：

scores =
[0.1, 0.6, 0.2, 0.1]
```

如果：

\[
TopK=2
\]

得到：

```text
weight =
[0.6, 0.2]

ids =
[1, 2]
```

意思：

```text
选择 Expert 1

选择 Expert 2
```

---

<a id="origin-5088"></a>
## 88. 一个完整的 MoE 前向传播

假设：

```text
hidden_size = 4096

num_experts = 8

top_k = 2
```

输入：

\[
X
\in
\mathbb R^{B\times T\times4096}
\]

---

<a id="origin-5110"></a>
### 88.1 Step 1：展开 Token

\[
X
\rightarrow
X_f
\]

\[
X_f
\in
\mathbb R^{BT\times4096}
\]

---

<a id="origin-5126"></a>
### 88.2 Step 2：Router

\[
R=X_fW_r
\]

得到：

\[
R
\in
\mathbb R^{BT\times8}
\]

---

<a id="origin-5142"></a>
### 88.3 Step 3：Softmax

\[
P=softmax(R)
\]

得到：

> 每个 Token 对 8 个 Expert 的概率。

---

<a id="origin-5154"></a>
### 88.4 Step 4：Top-k

例如某个 Token：

```text
topk_idx =
[2,5]

topk_weight =
[0.71,0.29]
```

---

<a id="origin-5168"></a>
### 88.5 Step 5：按照 Expert 对 Token 分组

例如：

```text
Expert 2：
Token 0
Token 4
Token 8

Expert 5：
Token 0
Token 3
Token 7
```

---

<a id="origin-5186"></a>
### 88.6 Step 6：Expert Forward

分别计算：

\[
E_2(x)
\]

\[
E_5(x)
\]

---

<a id="origin-5200"></a>
### 88.7 Step 7：乘 Gate Weight

例如：

\[
0.71E_2(x)
\]

\[
0.29E_5(x)
\]

---

<a id="origin-5214"></a>
### 88.8 Step 8：通过 `index_add_` 加回原 Token

例如：

```python
output.index_add_(
    0,
    token_idx,
    expert_output * weight
)
```

本质上完成：

\[
y_t
=
\sum_{i\in TopK(t)}
g_{t,i}E_i(x_t)
\]

---

<a id="origin-5237"></a>
### 88.9 Step 9：恢复原 Shape

从：

\[
[BT,D]
\]

恢复：

\[
[B,T,D]
\]

然后继续进入 Transformer 下一部分。

---

<a id="origin-5255"></a>
## 89. MoE 和普通 Ensemble 不一样

Ensemble：

```text
Model A
Model B
Model C
```

通常是：

```text
完整模型分别进行推理
最后融合
```

而 MoE：

```text
一个模型内部
包含很多 Expert
```

并且：

```text
每个 Token 动态选择 Expert
```

所以：

\[
\boxed{
MoE
\neq
普通 Ensemble
}
\]

---

<a id="origin-5297"></a>
## 90. MoE 和 Multi-Head Attention 也不一样

MHA：

```text
Head 1
Head 2
Head 3
...
```

一般所有 Head 都会计算。

最终：

```text
Concat
→ W_O
```

MoE：

```text
Expert 0
Expert 1
Expert 2
...
```

通常只选择：

\[
TopK
\]

所以区别可以简单记：

```text
MHA：
所有 Head 基本都激活

MoE：
只有少数 Expert 激活
```

---

<a id="origin-5344"></a>
## 91. Expert 是越多越好吗？

不一定。

Expert 多：

优点：

```text
总参数容量大
可以产生更多 specialization
```

但是问题也更多：

```text
通信成本增加

负载均衡更困难

每个 Expert 收到的数据可能变少

显存占用增加

部署更复杂
```

所以 Expert 数量是一个 trade-off。

---

<a id="origin-5375"></a>
## 92. MoE 的主要优点

第一：

\[
\boxed{\text{参数容量大}}
\]

第二：

\[
\boxed{\text{每个 Token 激活参数少}}
\]

第三：

\[
\boxed{\text{不同 Expert 可以自动形成 specialization}}
\]

第四：

\[
\boxed{\text{可以在相近计算预算下增加模型总容量}}
\]

---

<a id="origin-5403"></a>
## 93. MoE 的主要缺点

第一：

> 全部 Expert 参数仍然要存储。

即使当前 Token 不计算某 Expert：

```text
这个 Expert 的参数依然存在
```

---

第二：

> GPU 之间通信成本很高。

特别是：

\[
All-to-All
\]

---

第三：

> 负载可能不均衡。

---

第四：

> 训练实现更加复杂。

需要考虑：

```text
Router

Top-k

Aux Loss

Capacity

Token Dispatch

Expert Parallelism
```

---

第五：

> 推理部署更复杂。

因为不同 Token：

```text
走不同路径
```

这会让：

```text
Batching

Memory

Kernel

Communication
```

都更加复杂。

---

<a id="origin-5483"></a>
## 94. 最值得记住的一张 MoE 逻辑图

```text
                  Hidden State
                       │
                       ▼
                  ┌─────────┐
                  │ Router  │
                  └─────────┘
                       │
                       ▼
                Expert Scores
                       │
                       ▼
                    Softmax
                       │
                       ▼
                     Top-k
                       │
              ┌────────┴────────┐
              │                 │
              ▼                 ▼
         ┌─────────┐       ┌─────────┐
         │Expert 2 │       │Expert 5 │
         │  FFN    │       │  FFN    │
         └─────────┘       └─────────┘
              │                 │
              ▼                 ▼
          g₂E₂(x)           g₅E₅(x)
              │                 │
              └────────┬────────┘
                       │
                       ▼
                  index_add_
                       │
                       ▼
             g₂E₂(x) + g₅E₅(x)
                       │
                       ▼
                    Output
```

---

<a id="origin-5527"></a>
## 95. 三个最重要的公式

<a id="origin-5529"></a>
### 95.1 Router

\[
\boxed{
g(x)
=
softmax(W_rx)
}
\]

---

<a id="origin-5541"></a>
### 95.2 Top-k Expert 融合

\[
\boxed{
y
=
\sum_{i\in TopK}
g_i(x)E_i(x)
}
\]

---

<a id="origin-5554"></a>
### 95.3 负载均衡 Aux Loss

\[
\boxed{
L_{\text{aux}}
=
N
\sum_i
f_iP_i
}
\]

其中：

\[
\boxed{
f_i
=
\text{Expert i 实际接收到的 Token 比例}
}
\]

\[
\boxed{
P_i
=
\text{Router 对 Expert i 的平均概率}
}
\]

---

<a id="origin-5586"></a>
## 96. 最后总结

如果把整个 MoE 压缩成一条完整流程：

```text
Token Hidden State
        ↓
      Router
        ↓
  每个 Expert 的分数
        ↓
      Softmax
        ↓
      Top-k
        ↓
把 Token 分配到对应 Expert
        ↓
各个 Expert 批量做 FFN
        ↓
乘 Gate Weight
        ↓
index_add_
把多个 Expert 的结果
累加回原 Token 位置
        ↓
   得到 MoE 输出
```

训练时另外增加：

```text
f_i
=
Expert 实际接到多少 Token

P_i
=
Router 平均有多喜欢这个 Expert
```

构造：

\[
L_{\text{aux}}
=
N\sum_i f_iP_i
\]

避免：

```text
所有 Token 都跑去少数几个 Expert
```

---

<a id="origin-5642"></a>
## 97. 整节 MoE 最核心的一句话

\[
\boxed{
\text{MoE 就是把一个 FFN 变成很多个 FFN，
再通过 Router 为每个 Token 动态选择少数几个 FFN，
最后用 Gate Weight 加权，并通过类似 index\_add\_ 的操作，
把多个 Expert 的结果重新累加回对应 Token。}
}
\]

它最核心的价值是：

\[
\boxed{
\text{非常大的总参数容量}
+
\text{相对较少的每 Token 激活参数}
}
\]

最终可以概括成：

```text
多个 Expert
+
Router
+
Top-k
+
Sparse Activation
+
Expert Output 聚合
+
Load Balancing
=
MoE
```

---

<a id="origin-5683"></a>
## 98. MoE 原理与 `MOEFeedForward` 源码完整讲解

下面我们不再把 MoE 只停留在公式层面，而是直接结合下面这段真实代码，从输入到输出完整跑一遍。

核心代码：

```python
class MOEFeedForward(nn.Module):
    def __init__(self, config: MiniMindConfig):
        super().__init__()
        self.config = config

        self.gate = nn.Linear(
            config.hidden_size,
            config.num_experts,
            bias=False
        )

        self.experts = nn.ModuleList([
            FeedForward(
                config,
                intermediate_size=config.moe_intermediate_size
            )
            for _ in range(config.num_experts)
        ])

        self.act_fn = ACT2FN[config.hidden_act]

    def forward(self, x):
        batch_size, seq_len, hidden_dim = x.shape

        x_flat = x.view(-1, hidden_dim)

        scores = F.softmax(
            self.gate(x_flat),
            dim=-1
        )

        topk_weight, topk_idx = torch.topk(
            scores,
            k=self.config.num_experts_per_tok,
            dim=-1,
            sorted=False
        )

        if self.config.norm_topk_prob:
            topk_weight = topk_weight / (
                topk_weight.sum(
                    dim=-1,
                    keepdim=True
                ) + 1e-20
            )

        y = torch.zeros_like(x_flat)

        for i, expert in enumerate(self.experts):

            mask = (topk_idx == i)

            if mask.any():

                token_idx = (
                    mask
                    .any(dim=-1)
                    .nonzero()
                    .flatten()
                )

                weight = (
                    topk_weight[mask]
                    .view(-1, 1)
                )

                y.index_add_(
                    0,
                    token_idx,
                    (
                        expert(x_flat[token_idx])
                        * weight
                    ).to(y.dtype)
                )

            elif self.training:

                y[0, 0] += (
                    0 *
                    sum(
                        p.sum()
                        for p in expert.parameters()
                    )
                )

        if (
            self.training
            and
            self.config.router_aux_loss_coef > 0
        ):

            load = F.one_hot(
                topk_idx,
                self.config.num_experts
            ).float().mean(0)

            self.aux_loss = (
                load
                * scores.mean(0)
            ).sum() \
            * self.config.num_experts \
            * self.config.router_aux_loss_coef

        else:

            self.aux_loss = (
                scores
                .new_zeros(1)
                .squeeze()
            )

        return y.view(
            batch_size,
            seq_len,
            hidden_dim
        )
```

---

<a id="origin-5810"></a>
## 99. 先回忆：MoE 本质上在干什么？

普通 Transformer：

```text
Token
  ↓
Attention
  ↓
FFN
```

每一个 Token 都经过：

\[
\boxed{\text{同一个 FFN}}
\]

而 MoE：

```text
Token
  ↓
Router
  ↓
Top-k
  ↓
若干 Expert
```

其中：

\[
\boxed{\text{Expert 本质上就是不同的 FFN}}
\]

所以：

\[
\boxed{
\text{MoE}
=
\text{多个 FFN Expert}
+
\text{一个 Router}
}
\]

例如有 4 个 Expert：

```text
Expert 0
Expert 1
Expert 2
Expert 3
```

对于某个 Token，Router 可能得到：

```text
E0 → 0.10
E1 → 0.60
E2 → 0.25
E3 → 0.05
```

如果：

\[
TopK=2
\]

那么只让这个 Token 经过：

```text
Expert 1
Expert 2
```

最终：

\[
y
=
g_1E_1(x)
+
g_2E_2(x)
\]

---

<a id="origin-5901"></a>
## 100. 这段代码在 Transformer 中替代的是什么？

普通 Transformer Block 中：

```text
Attention
   ↓
FFN
```

使用 MoE 后：

```text
Attention
   ↓
MOEFeedForward
```

而：

```python
MOEFeedForward
```

内部实际上是：

```text
             ┌→ Expert 0
             ├→ Expert 1
x → Router ──┼→ Expert 2
             └→ Expert 3
```

每个 Expert 本身仍然是：

```python
FeedForward(...)
```

所以 MoE 主要替换的是：

\[
\boxed{\text{FFN 部分}}
\]

---

<a id="origin-5948"></a>
## 101. 先设定一个完整具体例子

为了把代码真正跑明白，我们设：

```text
batch_size = 1
seq_len = 3
hidden_size = 2

num_experts = 4
num_experts_per_tok = 2

norm_topk_prob = True
```

也就是说：

\[
B=1
\]

\[
T=3
\]

\[
H=2
\]

有：

\[
E=4
\]

个 Expert。

每个 Token 选：

\[
K=2
\]

个 Expert。

输入：

\[
x.shape=[1,3,2]
\]

为了方便，假设：

\[
x=
\begin{bmatrix}
[
1,2
]\\
[
3,4
]\\
[
5,6
]
\end{bmatrix}
\]

也就是三个 Token：

```text
Token 0 → [1,2]

Token 1 → [3,4]

Token 2 → [5,6]
```

---

<a id="origin-6028"></a>
## 102. `__init__`：先创建 Router

代码：

```python
self.gate = nn.Linear(
    config.hidden_size,
    config.num_experts,
    bias=False
)
```

这里：

```text
hidden_size = 2
num_experts = 4
```

所以 Router 的作用：

\[
\mathbb R^2
\rightarrow
\mathbb R^4
\]

也就是：

\[
[H]
\rightarrow
[E]
\]

对于一个 Token：

\[
x_t\in\mathbb R^2
\]

Router 输出：

\[
4
\]

个 Expert 的分数。

数学上：

\[
z_t=x_tW_r
\]

其中：

\[
W_r\in\mathbb R^{2\times4}
\]

---

<a id="origin-6091"></a>
## 103. `gate` 就是 Router

所以：

```python
self.gate
```

可以直接理解成：

\[
\boxed{\text{Router}}
\]

它负责：

> 当前 Token 应该选择哪些 Expert？

---

<a id="origin-6111"></a>
## 104. 创建多个 Expert

代码：

```python
self.experts = nn.ModuleList([
    FeedForward(
        config,
        intermediate_size=config.moe_intermediate_size
    )
    for _ in range(config.num_experts)
])
```

假设：

```text
num_experts = 4
```

就会真正创建：

```text
experts[0]
experts[1]
experts[2]
experts[3]
```

也就是：

```text
Expert 0 = 一个 FeedForward
Expert 1 = 一个 FeedForward
Expert 2 = 一个 FeedForward
Expert 3 = 一个 FeedForward
```

而且：

\[
\boxed{\text{每个 Expert 参数独立}}
\]

例如：

```text
Expert 0 有自己的 W_gate/W_up/W_down

Expert 1 有自己的 W_gate/W_up/W_down
```

它们不是共用同一套参数。

---

<a id="origin-6167"></a>
## 105. 为什么一定要用 `ModuleList`？

如果只是普通 Python：

```python
[
    FeedForward(...),
    FeedForward(...),
    ...
]
```

PyTorch 不一定会把里面的模块正确注册为当前模型的一部分。

使用：

```python
nn.ModuleList(...)
```

之后，PyTorch 才能够自动：

```text
model.parameters()

model.cuda()

model.state_dict()

optimizer
```

找到这些 Expert。

所以：

\[
\boxed{
ModuleList
=
告诉 PyTorch：
这些 Expert 都是模型真正的一部分
}
\]

---

<a id="origin-6214"></a>
## 106. `self.act_fn` 为什么这里看起来没有用？

代码：

```python
self.act_fn = ACT2FN[
    config.hidden_act
]
```

但是这个 `forward()` 里面确实没有直接出现：

```python
self.act_fn(...)
```

原因是：

> 真正的激活函数已经在每一个 `FeedForward` Expert 内部执行。

所以这里虽然保存了：

```python
self.act_fn
```

当前这段 `MOEFeedForward.forward()` 本身没有直接调用它。

---

<a id="origin-6244"></a>
## 107. 正式进入 forward

输入：

```python
def forward(self, x):
```

我们的：

\[
x.shape
=
[1,3,2]
\]

分别代表：

```text
B = 1
T = 3
H = 2
```

---

<a id="origin-6270"></a>
## 108. 保存原始 Shape

代码：

```python
batch_size, seq_len, hidden_dim = x.shape
```

于是：

```text
batch_size = 1
seq_len = 3
hidden_dim = 2
```

为什么保存？

因为后面要把：

```text
Batch 维
和
Token 维
```

合并。

最后还得恢复回来。

---

<a id="origin-6302"></a>
## 109. `x.view(-1, hidden_dim)`：把所有 Token 展平

代码：

```python
x_flat = x.view(
    -1,
    hidden_dim
)
```

原来：

\[
x.shape=[1,3,2]
\]

现在：

\[
x_{flat}.shape=[3,2]
\]

也就是：

\[
N=B\times T
\]

所以：

\[
N=1\times3=3
\]

得到：

\[
x_{flat}
=
\begin{bmatrix}
1&2\\
3&4\\
5&6
\end{bmatrix}
\]

以后 MoE 就暂时不关心：

```text
这个 Token 属于哪个 Batch
第几个位置
```

只认为现在有：

\[
\boxed{N=3\text{ 个 Token}}
\]

---

<a id="origin-6364"></a>
## 110. 为什么一定要展平？

因为 Router 和 Expert 的核心逻辑其实是：

> 对每一个 Token 单独进行路由。

所以：

```text
[B,T,H]
```

变成：

```text
[N,H]
```

更方便处理。

其中：

\[
N=B\times T
\]

---

<a id="origin-6392"></a>
## 111. Router 计算 Expert 概率

代码：

```python
scores = F.softmax(
    self.gate(x_flat),
    dim=-1
)
```

先看：

```python
self.gate(x_flat)
```

输入：

\[
[3,2]
\]

Router：

\[
2\rightarrow4
\]

所以输出：

\[
[3,4]
\]

即：

```text
3 个 Token

每个 Token 对 4 个 Expert
都有一个 Router logit
```

---

<a id="origin-6438"></a>
## 112. 假设 Router 最终得到这些概率

为了讲解，我们直接假设 Softmax 后：

\[
scores=
\begin{bmatrix}
0.10&0.60&0.25&0.05\\
0.40&0.10&0.20&0.30\\
0.15&0.10&0.65&0.10
\end{bmatrix}
\]

shape：

\[
[3,4]
\]

---

第一行：

\[
[0.10,0.60,0.25,0.05]
\]

表示 Token 0：

```text
E0 → 0.10
E1 → 0.60
E2 → 0.25
E3 → 0.05
```

第二行：

```text
Token 1：

E0 → 0.40
E1 → 0.10
E2 → 0.20
E3 → 0.30
```

第三行：

```text
Token 2：

E0 → 0.15
E1 → 0.10
E2 → 0.65
E3 → 0.10
```

---

<a id="origin-6498"></a>
## 113. Softmax 为什么沿 `dim=-1`？

因为：

\[
scores.shape=[N,E]
\]

最后一维：

\[
E
\]

就是 Expert 维度。

所以：

```python
dim=-1
```

表示：

> 对每个 Token 的所有 Expert 分数做 Softmax。

于是每一行满足：

\[
\sum_{i=1}^{E}p_i=1
\]

---

<a id="origin-6532"></a>
## 114. Top-k 选择 Expert

代码：

```python
topk_weight, topk_idx = torch.topk(
    scores,
    k=self.config.num_experts_per_tok,
    dim=-1,
    sorted=False
)
```

我们这里：

\[
K=2
\]

所以每个 Token 选择两个 Expert。

根据刚才的 `scores`：

---

Token 0：

```text
E0 → 0.10
E1 → 0.60
E2 → 0.25
E3 → 0.05
```

最大两个：

```text
E1 → 0.60
E2 → 0.25
```

---

Token 1：

```text
E0 → 0.40
E1 → 0.10
E2 → 0.20
E3 → 0.30
```

选：

```text
E0 → 0.40
E3 → 0.30
```

---

Token 2：

```text
E0 → 0.15
E1 → 0.10
E2 → 0.65
E3 → 0.10
```

选：

```text
E2 → 0.65
E0 → 0.15
```

---

<a id="origin-6611"></a>
## 115. 所以 `topk_idx` 可以理解成

假设返回：

\[
topk\_idx=
\begin{bmatrix}
1&2\\
0&3\\
2&0
\end{bmatrix}
\]

shape：

\[
[3,2]
\]

每一行表示：

```text
Token 0 → Expert 1, Expert 2

Token 1 → Expert 0, Expert 3

Token 2 → Expert 2, Expert 0
```

---

<a id="origin-6642"></a>
## 116. `topk_weight` 是什么？

对应：

\[
topk\_weight=
\begin{bmatrix}
0.60&0.25\\
0.40&0.30\\
0.65&0.15
\end{bmatrix}
\]

同样：

\[
shape=[3,2]
\]

也就是：

```text
Token 0：
E1 → 0.60
E2 → 0.25

Token 1：
E0 → 0.40
E3 → 0.30

Token 2：
E2 → 0.65
E0 → 0.15
```

---

<a id="origin-6679"></a>
## 117. `sorted=False` 是什么意思？

代码：

```python
sorted=False
```

表示：

> 不要求 Top-k 返回的这两个 Expert 按概率从大到小排好序。

因为后面只关心：

```text
选中了谁
对应权重是多少
```

并不关心：

```text
第一名是谁
第二名是谁
```

所以没有必要为了排序再增加额外工作。

---

<a id="origin-6709"></a>
## 118. Top-k 后重新归一化

代码：

```python
if self.config.norm_topk_prob:
    topk_weight = topk_weight / (
        topk_weight.sum(
            dim=-1,
            keepdim=True
        ) + 1e-20
    )
```

为什么？

因为虽然原始 4 个 Expert 的概率加起来是：

\[
1
\]

但只保留 Top-2 之后：

```text
保留下来的概率之和
通常小于 1
```

---

<a id="origin-6740"></a>
## 119. Token 0 的例子

Token 0 保留：

\[
0.60,\ 0.25
\]

它们加起来：

\[
0.85
\]

重新归一化：

\[
g_{0,1}
=
\frac{0.60}{0.85}
\approx0.706
\]

\[
g_{0,2}
=
\frac{0.25}{0.85}
\approx0.294
\]

于是：

```text
Token 0：

Expert 1 → 0.706
Expert 2 → 0.294
```

现在重新满足：

\[
0.706+0.294=1
\]

---

<a id="origin-6787"></a>
## 120. Token 1

原来：

\[
0.40,\ 0.30
\]

加起来：

\[
0.70
\]

所以：

\[
E0:
\frac{0.4}{0.7}
\approx0.571
\]

\[
E3:
\frac{0.3}{0.7}
\approx0.429
\]

---

<a id="origin-6817"></a>
## 121. Token 2

原来：

\[
0.65,\ 0.15
\]

加起来：

\[
0.80
\]

所以：

\[
E2:
0.8125
\]

\[
E0:
0.1875
\]

因此重新归一化后：

\[
topk\_weight
\approx
\begin{bmatrix}
0.706&0.294\\
0.571&0.429\\
0.8125&0.1875
\end{bmatrix}
\]

---

<a id="origin-6857"></a>
## 122. `1e-20` 是什么？

代码：

```python
+ 1e-20
```

只是一个极小的数：

\[
10^{-20}
\]

用于避免极端情况下：

\[
\frac{x}{0}
\]

所以这是：

\[
\boxed{\text{数值稳定项}}
\]

---

<a id="origin-6885"></a>
## 123. 创建最终输出缓冲区

代码：

```python
y = torch.zeros_like(x_flat)
```

因为：

\[
x_{flat}.shape=[3,2]
\]

所以：

\[
y.shape=[3,2]
\]

初始：

\[
y=
\begin{bmatrix}
0&0\\
0&0\\
0&0
\end{bmatrix}
\]

为什么一开始全部是 0？

因为接下来：

> 每个 Expert 算完以后，把自己的结果累加进对应 Token 的位置。

---

<a id="origin-6924"></a>
## 124. 为什么不能直接一次计算所有 Expert？

因为不同 Expert 接收到的 Token 不一样。

现在：

```text
Token 0 → E1, E2

Token 1 → E0, E3

Token 2 → E2, E0
```

所以整理一下：

```text
Expert 0：
Token 1
Token 2

Expert 1：
Token 0

Expert 2：
Token 0
Token 2

Expert 3：
Token 1
```

代码接下来就是：

> 一个 Expert 一个 Expert 地处理属于自己的 Token。

---

<a id="origin-6962"></a>
## 125. 遍历所有 Expert

代码：

```python
for i, expert in enumerate(
    self.experts
):
```

依次：

```text
i=0 → Expert 0

i=1 → Expert 1

i=2 → Expert 2

i=3 → Expert 3
```

---

<a id="origin-6986"></a>
## 126. `mask = (topk_idx == i)` 是干什么？

先看：

\[
topk\_idx=
\begin{bmatrix}
1&2\\
0&3\\
2&0
\end{bmatrix}
\]

现在：

```python
i = 0
```

执行：

```python
mask = (
    topk_idx == 0
)
```

得到：

\[
mask=
\begin{bmatrix}
False&False\\
True&False\\
False&True
\end{bmatrix}
\]

shape：

\[
[3,2]
\]

---

<a id="origin-7032"></a>
## 127. 这个 mask 怎么读？

第一行：

```text
Token 0 → [1,2]
```

里面没有 0：

```text
False False
```

第二行：

```text
Token 1 → [0,3]
```

第一个位置是 Expert 0：

```text
True False
```

第三行：

```text
Token 2 → [2,0]
```

第二个位置是 Expert 0：

```text
False True
```

所以：

> Expert 0 被 Token 1 和 Token 2 选择。

---

<a id="origin-7076"></a>
## 128. `mask.any()` 为什么要判断？

代码：

```python
if mask.any():
```

意思：

> 这一整个 mask 里面，只要存在一个 True，就说明至少有一个 Token 使用这个 Expert。

例如 Expert 0：

```text
有 True
```

所以真正调用：

```python
expert(...)
```

如果一个 Expert 完全没人选：

```text
mask 全 False
```

那就没有必要执行 FFN。

这正是：

\[
\boxed{\text{Sparse Activation}}
\]

---

<a id="origin-7116"></a>
## 129. 找出属于当前 Expert 的 Token

代码：

```python
token_idx = (
    mask
    .any(dim=-1)
    .nonzero()
    .flatten()
)
```

这一行很值得拆开。

---

<a id="origin-7133"></a>
## 130. 第一步：`mask.any(dim=-1)`

当前：

\[
mask=
\begin{bmatrix}
F&F\\
T&F\\
F&T
\end{bmatrix}
\]

执行：

```python
mask.any(dim=-1)
```

就是每一行：

> 这一行的两个 Top-k 位置，只要有一个 True 就算 True。

结果：

\[
[
False,
True,
True
]
\]

意思：

```text
Token 0 没选 Expert 0

Token 1 选了 Expert 0

Token 2 选了 Expert 0
```

---

<a id="origin-7178"></a>
## 131. 第二步：`.nonzero()`

执行：

```python
.nonzero()
```

找到 True 的位置：

\[
\begin{bmatrix}
1\\
2
\end{bmatrix}
\]

也就是：

```text
Token 1
Token 2
```

---

<a id="origin-7204"></a>
## 132. 第三步：`.flatten()`

`.nonzero()` 返回的 shape 可能是：

\[
[2,1]
\]

我们希望得到：

\[
[2]
\]

所以：

```python
.flatten()
```

最终：

```python
token_idx = tensor([1,2])
```

也就是说：

\[
\boxed{
Expert 0 需要处理 Token 1 和 Token 2
}
\]

---

<a id="origin-7240"></a>
## 133. 根据 token_idx 取 Expert 输入

现在：

```python
x_flat[token_idx]
```

原来：

\[
x_{flat}
=
\begin{bmatrix}
1&2\\
3&4\\
5&6
\end{bmatrix}
\]

而：

```python
token_idx = [1,2]
```

所以：

\[
x_{flat}[token\_idx]
=
\begin{bmatrix}
3&4\\
5&6
\end{bmatrix}
\]

这两个 Token 一次性交给：

```python
Expert 0
```

所以：

\[
Expert_0
\left(
\begin{bmatrix}
3&4\\
5&6
\end{bmatrix}
\right)
\]

GPU 可以一次矩阵运算处理两个 Token。

---

<a id="origin-7299"></a>
## 134. `weight = topk_weight[mask]` 是怎么工作的？

这是这段代码里另一个容易迷糊的地方。

假设重新归一化后：

\[
topk\_weight=
\begin{bmatrix}
0.706&0.294\\
0.571&0.429\\
0.8125&0.1875
\end{bmatrix}
\]

对于 Expert 0：

\[
mask=
\begin{bmatrix}
F&F\\
T&F\\
F&T
\end{bmatrix}
\]

所以：

```python
topk_weight[mask]
```

会把 True 对应的值取出来：

```text
Token 1 对 E0 → 0.571

Token 2 对 E0 → 0.1875
```

得到：

\[
[
0.571,
0.1875
]
\]

---

<a id="origin-7350"></a>
## 135. 为什么还要 `.view(-1,1)`？

代码：

```python
weight = (
    topk_weight[mask]
    .view(-1, 1)
)
```

变成：

\[
weight=
\begin{bmatrix}
0.571\\
0.1875
\end{bmatrix}
\]

shape：

\[
[2,1]
\]

假设 Expert 输出：

\[
[2,H]
\]

比如：

\[
H=2
\]

那么：

\[
expert\_output
=
\begin{bmatrix}
a&b\\
c&d
\end{bmatrix}
\]

乘：

\[
\begin{bmatrix}
0.571\\
0.1875
\end{bmatrix}
\]

PyTorch 会广播成：

\[
\begin{bmatrix}
0.571a&0.571b\\
0.1875c&0.1875d
\end{bmatrix}
\]

所以每一个 Token：

> 整个 hidden vector 都乘自己的 Gate Weight。

---

<a id="origin-7424"></a>
## 136. 假设 Expert 0 输出具体数字

为了继续跑例子，假设：

\[
Expert_0(Token1)
=
[
10,20
]
\]

\[
Expert_0(Token2)
=
[
30,40
]
\]

所以：

\[
expert(x_{flat}[token\_idx])
=
\begin{bmatrix}
10&20\\
30&40
\end{bmatrix}
\]

乘对应权重：

\[
\begin{bmatrix}
0.571\\
0.1875
\end{bmatrix}
\]

得到：

\[
\begin{bmatrix}
5.71&11.42\\
5.625&7.5
\end{bmatrix}
\]

这就是 Expert 0 对两个 Token 的最终贡献。

---

<a id="origin-7477"></a>
## 137. 最关键的一行：`index_add_`

代码：

```python
y.index_add_(
    0,
    token_idx,
    (
        expert(x_flat[token_idx])
        * weight
    ).to(y.dtype)
)
```

这一行实际上完成：

\[
\boxed{
\text{把 Expert 的输出加回原 Token 对应的位置}
}
\]

---

<a id="origin-7502"></a>
## 138. 先单独理解 `index_add_`

最简单例子：

```python
output = torch.tensor([
    10.,
    20.,
    30.,
    40.
])

index = torch.tensor([
    1,
    3
])

source = torch.tensor([
    5.,
    7.
])
```

执行：

```python
output.index_add_(
    0,
    index,
    source
)
```

意思：

```text
source[0] = 5
加到
output[index[0]]
=
output[1]
```

所以：

\[
20+5=25
\]

然后：

```text
source[1] = 7
加到
output[index[1]]
=
output[3]
```

所以：

\[
40+7=47
\]

结果：

```python
tensor([
    10.,
    25.,
    30.,
    47.
])
```

---

<a id="origin-7580"></a>
## 139. `index_add_` 最关键的性质：它是累加，不是覆盖

如果：

```python
index = torch.tensor([
    1,
    1
])

source = torch.tensor([
    3.,
    5.
])
```

那么两次都指向：

```text
output[1]
```

结果不是后一个覆盖前一个。

而是：

\[
output[1]
=
3+5
=
8
\]

所以：

\[
\boxed{
index\_add_
=
根据索引进行累加
}
\]

---

<a id="origin-7626"></a>
## 140. 为什么 MoE 特别需要它？

因为：

\[
TopK>1
\]

时，一个 Token 会经过多个 Expert。

例如：

```text
Token 0
 ↓
Expert 1
Expert 2
```

最终需要：

\[
y_0
=
g_1E_1(x_0)
+
g_2E_2(x_0)
\]

也就是说：

> Token 0 的输出位置要被写入不止一次。

所以不能：

```python
y[token_idx] = ...
```

因为这样后来的 Expert 会把前一个 Expert 的结果覆盖掉。

必须：

```python
y.index_add_(...)
```

不断累加。

---

<a id="origin-7677"></a>
## 141. 用 Expert 0 的例子执行 `index_add_`

现在：

\[
y=
\begin{bmatrix}
0&0\\
0&0\\
0&0
\end{bmatrix}
\]

Expert 0：

```text
token_idx = [1,2]
```

加权输出：

\[
source=
\begin{bmatrix}
5.71&11.42\\
5.625&7.5
\end{bmatrix}
\]

执行：

```python
y.index_add_(
    0,
    torch.tensor([1,2]),
    source
)
```

得到：

\[
y=
\begin{bmatrix}
0&0\\
5.71&11.42\\
5.625&7.5
\end{bmatrix}
\]

---

<a id="origin-7729"></a>
## 142. 接下来 Expert 1

回忆：

```text
Token 0 → E1,E2
```

所以 Expert 1 只处理：

```text
Token 0
```

假设：

\[
Expert_1(Token0)
=
[
2,4
]
\]

Token 0 给 E1 的权重：

\[
0.706
\]

所以：

\[
0.706[2,4]
=
[
1.412,
2.824
]
\]

执行：

```python
y.index_add_(
    0,
    tensor([0]),
    tensor([
        [1.412,2.824]
    ])
)
```

得到：

\[
y=
\begin{bmatrix}
1.412&2.824\\
5.71&11.42\\
5.625&7.5
\end{bmatrix}
\]

---

<a id="origin-7795"></a>
## 143. Expert 2 再给 Token 0 和 Token 2 加结果

Expert 2 被：

```text
Token 0
Token 2
```

选中。

假设：

\[
Expert_2(Token0)
=
[
10,10
]
\]

Token 0 对 E2 权重：

\[
0.294
\]

所以贡献：

\[
[
2.94,
2.94
]
\]

假设：

\[
Expert_2(Token2)
=
[
4,8
]
\]

Token 2 对 E2 权重：

\[
0.8125
\]

贡献：

\[
[
3.25,
6.5
]
\]

执行 `index_add_` 后：

Token 0：

\[
[
1.412,
2.824
]
+
[
2.94,
2.94
]
\]

得到：

\[
[
4.352,
5.764
]
\]

Token 2：

\[
[
5.625,
7.5
]
+
[
3.25,
6.5
]
\]

得到：

\[
[
8.875,
14
]
\]

这就是：

\[
\boxed{
多个 Expert 的结果加权以后重新合并
}
\]

---

<a id="origin-7914"></a>
## 144. Expert 3

Expert 3 只处理：

```text
Token 1
```

假设：

\[
Expert_3(Token1)
=
[
20,10
]
\]

它的权重：

\[
0.429
\]

贡献：

\[
[
8.58,
4.29
]
\]

Token 1 原来已经有 Expert 0 的贡献：

\[
[
5.71,
11.42
]
\]

继续累加：

\[
[
5.71,
11.42
]
+
[
8.58,
4.29
]
\]

得到：

\[
[
14.29,
15.71
]
\]

---

<a id="origin-7981"></a>
## 145. 最终 y

最终假设得到：

\[
y
=
\begin{bmatrix}
4.352&5.764\\
14.29&15.71\\
8.875&14
\end{bmatrix}
\]

分别就是：

```text
Token 0 的 MoE 输出

Token 1 的 MoE 输出

Token 2 的 MoE 输出
```

---

<a id="origin-8007"></a>
## 146. 用公式看 `index_add_` 到底完成了什么

对于 Token 0：

\[
y_0
=
0.706E_1(x_0)
+
0.294E_2(x_0)
\]

Token 1：

\[
y_1
=
0.571E_0(x_1)
+
0.429E_3(x_1)
\]

Token 2：

\[
y_2
=
0.1875E_0(x_2)
+
0.8125E_2(x_2)
\]

因此整段循环实际上就在实现：

\[
\boxed{
y_t
=
\sum_{i\in TopK(t)}
g_{t,i}E_i(x_t)
}
\]

---

<a id="origin-8052"></a>
## 147. 为什么 `(expert(...) * weight).to(y.dtype)`？

代码：

```python
(
    expert(x_flat[token_idx])
    * weight
).to(y.dtype)
```

`expert(...)` 得到：

\[
[M,H]
\]

`weight`：

\[
[M,1]
\]

相乘得到：

\[
[M,H]
\]

然后：

```python
.to(y.dtype)
```

是为了确保：

> 要加到 `y` 里面的数据类型和 `y` 保持一致。

例如在：

```text
FP16
BF16
FP32
```

混合精度情况下比较重要。

---

<a id="origin-8103"></a>
## 148. 如果一个 Expert 一个 Token 都没收到怎么办？

代码：

```python
elif self.training:
    y[0, 0] += (
        0 *
        sum(
            p.sum()
            for p in expert.parameters()
        )
    )
```

这是一个非常典型的：

\[
\boxed{\text{数值为 0，但保留计算图连接}}
\]

的技巧。

---

<a id="origin-8128"></a>
## 149. 为什么会出现“没人使用的 Expert”？

例如有：

```text
8 个 Expert
```

当前 Batch 只有少量 Token。

可能：

```text
E0：有 Token
E1：有 Token
E2：没人
E3：没人
...
```

那么：

```python
expert(...)
```

根本没有调用。

这个 Expert 的参数：

```text
不会自然出现在当前前向计算路径中
```

---

<a id="origin-8164"></a>
## 150. 为什么这在分布式训练里可能麻烦？

某些分布式训练方式会检查：

```text
哪些参数参与了当前 forward/backward
```

如果某个 Expert 当前完全没被用到：

```text
这些参数可能被认为是 unused parameters
```

所以代码故意写：

\[
0\times
\sum p
\]

---

<a id="origin-8187"></a>
## 151. 为什么乘 0 还有意义？

假设某 Expert 参数：

\[
\theta
\]

我们加入：

\[
0\times\theta
\]

数值显然：

\[
0
\]

所以：

> 不会改变 y 的真正结果。

但是从计算图角度：

```text
y
依然和
θ
建立了连接
```

求导：

\[
\frac{\partial (0\theta)}
{\partial\theta}
=
0
\]

虽然梯度是 0：

\[
\boxed{\text{但参数参与了计算图}}
\]

这就是这一行真正的作用。

---
<a id="origin-8238"></a>
### 151.1 MoE 中这行代码到底在干什么？

```python
y[0, 0] += 0 * sum(
    p.sum() for p in expert.parameters()
)
```

这行代码看起来很奇怪，因为：

\[
0\times任何东西=0
\]

既然最后一定是 0，为什么还要写？

答案是：

\[
\boxed{
\text{这行代码的目的不是改变数值，而是把“没被选中的 Expert 参数”挂到当前计算图上。}
}
\]

它具有三个特点：

\[
\boxed{
\text{前向贡献}=0
}
\]

\[
\boxed{
\text{梯度}=0
}
\]

但是：

\[
\boxed{
\text{Expert 参数仍然参与当前计算图}
}
\]

这主要是为了处理 MoE 在训练，尤其是某些分布式训练场景中的 **unused parameter** 问题。

---

<a id="origin-8288"></a>
## 152. 为什么会出现“没有被使用的 Expert”？

先回忆 MoE。

假设有 4 个 Expert：

```text
Expert 0
Expert 1
Expert 2
Expert 3
```

当前 Batch 中有 3 个 Token，并且：

```text
Token 0 → Expert 0, Expert 1

Token 1 → Expert 0, Expert 2

Token 2 → Expert 1, Expert 2
```

那么当前 Batch：

```text
Expert 0：有人用
Expert 1：有人用
Expert 2：有人用
Expert 3：一个 Token 都没有
```

对于 Expert 0、1、2，会正常执行：

```python
expert(x_flat[token_idx])
```

例如：

```text
Token
  ↓
Expert 参数
  ↓
Expert Output
  ↓
y
  ↓
后续网络
  ↓
Loss
```

所以它们的参数自然参与当前计算图。

但是 Expert 3 一个 Token 都没收到。

于是：

```python
mask.any()
```

等于：

```python
False
```

不会执行：

```python
expert(x_flat[token_idx])
```

那么 Expert 3 的参数就完全没有参与本轮正常前向传播。

---

<a id="origin-8368"></a>
## 153. 如果什么都不写，会发生什么？

假设 Expert 3 有参数：

\[
W_1,W_2,W_3
\]

但是当前 Batch 完全没有 Token 使用它。

那么当前计算图可能是：

```text
Expert 0 参数 ─┐
               │
Expert 1 参数 ─┼→ y → 后续网络 → Loss
               │
Expert 2 参数 ─┘


Expert 3 参数

   ×

Loss
```

也就是说：

\[
\boxed{
Expert 3 的参数和当前 Loss 没有任何计算图连接
}
\]

在普通单卡训练里，这不一定马上造成严重问题。

但是在某些分布式训练场景里，框架可能需要判断：

> 哪些参数参加了这一轮 forward/backward？

如果某些 Expert 参数没有参加，可能被认为是：

\[
\boxed{\text{unused parameters}}
\]

因此代码人为给这些 Expert 参数建立一条：

\[
\boxed{\text{数值贡献为 0 的计算图路径}}
\]

---

<a id="origin-8423"></a>
## 154. 先拆第一部分：`expert.parameters()`

代码：

```python
expert.parameters()
```

表示：

> 取得当前 Expert 的所有可训练参数。

假设这个 Expert 是一个普通 FFN，例如：

\[
Expert(x)
=
W_{down}
\left[
SiLU(W_{gate}x)
\odot
W_{up}x
\right]
\]

那么：

```python
expert.parameters()
```

里面可能包含：

```text
W_gate
W_up
W_down
```

也就是这个 Expert 的所有可训练矩阵。

---

<a id="origin-8466"></a>
## 155. `p.sum()` 是什么意思？

代码：

```python
p.sum()
```

把一个参数矩阵压缩成一个标量。

例如：

\[
p=
\begin{bmatrix}
1&2\\
3&4
\end{bmatrix}
\]

那么：

\[
p.sum()
=
1+2+3+4
=
10
\]

但是这里：

\[
\boxed{
\text{根本不关心最后等于 10 还是 100}
}
\]

真正目的只是：

> 让参数 \(p\) 出现在计算图里。

计算图：

```text
p
│
▼
sum()
│
▼
标量
```

---

<a id="origin-8522"></a>
## 156. 为什么要把所有参数都求和？

代码：

```python
sum(
    p.sum()
    for p in expert.parameters()
)
```

假设 Expert 一共有三个参数：

\[
W_1,W_2,W_3
\]

那么相当于：

\[
S
=
\sum W_1
+
\sum W_2
+
\sum W_3
\]

所以：

\[
S
\]

依赖：

\[
W_1,W_2,W_3
\]

计算图：

```text
W1 → sum ─┐
           │
W2 → sum ─┼→ S
           │
W3 → sum ─┘
```

于是当前 Expert 的所有参数都已经被引用。

---

<a id="origin-8577"></a>
## 157. 然后为什么还要乘 `0`？

接下来：

```python
0 * sum(...)
```

也就是：

\[
0\times S
\]

无论：

\[
S
\]

是多少，都有：

\[
0\times S=0
\]

所以从前向数值来看：

\[
\boxed{
0 * sum(...) = 0
}
\]

于是整行：

```python
y[0, 0] += 0 * sum(...)
```

就变成：

```python
y[0, 0] += 0
```

因此：

\[
\boxed{
y 的数值完全不会改变
}
\]

---

<a id="origin-8633"></a>
## 158. 一个具体数值例子

假设：

\[
y=
\begin{bmatrix}
2&3\\
4&5
\end{bmatrix}
\]

Expert 的所有参数求和之后：

\[
S=12345
\]

那么：

\[
0\times12345=0
\]

于是：

\[
y[0,0]
=
2+0
=
2
\]

最终：

\[
y=
\begin{bmatrix}
2&3\\
4&5
\end{bmatrix}
\]

和原来完全一样。

所以：

\[
\boxed{
\text{这行代码对前向预测结果没有任何影响}
}
\]

---

<a id="origin-8689"></a>
## 159. 那既然数值是 0，为什么还有意义？

因为：

\[
0\times S
\]

虽然数值是 0，但是这个 0 是通过：

\[
W_1,W_2,W_3
\]

计算出来的。

所以计算图依然存在：

```text
Expert Parameters
       │
       ▼
    p.sum()
       │
       ▼
全部参数求和 S
       │
       ▼
      × 0
       │
       ▼
       0
       │
       ▼
    y[0,0]
```

于是：

\[
\boxed{
Expert 的参数仍然和 y 建立了计算图连接
}
\]

---

<a id="origin-8736"></a>
## 160. 为什么还必须加到 `y[0,0]` 上？

假设只写：

```python
dummy = 0 * sum(
    p.sum()
    for p in expert.parameters()
)
```

但是后面完全不用：

```python
dummy
```

那么计算图虽然产生了：

```text
Expert 参数
   ↓
dummy
```

但是：

```text
dummy
```

没有进入最终：

```text
Loss
```

也就是说：

```text
Expert 参数
   ↓
dummy

   ×

Loss
```

还是断开的。

所以必须把这个 dummy 连接到：

```python
y
```

上。

例如：

```python
y[0, 0] += dummy
```

于是：

```text
Expert 参数
   ↓
sum
   ↓
× 0
   ↓
y[0,0]
   ↓
后续 Transformer
   ↓
Loss
```

这样：

\[
\boxed{
Expert 参数才真正成为最终计算图的一部分
}
\]

---

<a id="origin-8827"></a>
## 161. 为什么只加到 `y[0,0]` 就够了？

因为目的只是：

\[
\boxed{
\text{建立计算图连接}
}
\]

不是为了修改输出。

所以只需要找 `y` 中任何一个会继续参与后续计算的位置即可。

例如：

```python
y[0, 0]
```

非常方便。

由于加进去的是：

\[
0
\]

所以：

```text
加到 y[0,0]
```

和：

```text
加到 y[2,100]
```

对于前向数值都没有区别。

这里只是选择：

```python
y[0,0]
```

作为一个最简单的“挂钩位置”。

---

<a id="origin-8879"></a>
## 162. 这行代码会训练这个没被选中的 Expert 吗？

不会。

这是最重要的一点。

假设某个参数：

\[
w
\]

这一行相当于：

\[
y
=
y_{old}
+
0w
\]

最终 Loss：

\[
L=L(y)
\]

根据链式法则：

\[
\frac{\partial L}{\partial w}
=
\frac{\partial L}{\partial y}
\frac{\partial y}{\partial w}
\]

而：

\[
y
=
y_{old}+0w
\]

所以：

\[
\frac{\partial y}{\partial w}
=
0
\]

因此：

\[
\boxed{
\frac{\partial L}{\partial w}
=
0
}
\]

也就是说：

> 这个 Expert 虽然参加了计算图，但这一轮不会因为这条 dummy 路径获得实际参数更新。

---

<a id="origin-8948"></a>
## 163. 最核心的区别：`grad=None` 和 `grad=0`

这是理解这行代码最重要的地方之一。

<a id="origin-8952"></a>
### 163.1 情况一：参数完全没有参与计算图

假设：

```python
w1 = Parameter(...)
w2 = Parameter(...)
```

Loss：

```python
loss = w1 ** 2
```

那么：

```text
w1 → loss
```

但是：

```text
w2
```

根本没有参与。

所以反向传播后概念上：

```text
w1.grad = 某个梯度

w2.grad = None
```

这里：

```text
None
```

意思是：

> 当前计算根本没有涉及这个参数。

---

<a id="origin-9001"></a>
## 164. 情况二：参数通过 `0 * w` 参与计算图

如果改成：

```python
loss = w1 ** 2 + 0 * w2
```

那么计算图：

```text
w1 ───────→ loss

w2 → ×0 ──→ loss
```

虽然：

\[
0w_2=0
\]

但是：

\[
w_2
\]

参与了计算图。

所以：

\[
\frac{\partial L}{\partial w_2}
=
0
\]

概念上：

```text
w2.grad = 0
```

而不是：

```text
w2.grad = None
```

因此：

\[
\boxed{
\text{grad=None}
\neq
\text{grad=0}
}
\]

---

<a id="origin-9063"></a>
## 165. 两者分别是什么意思？

<a id="origin-9065"></a>
### 165.1 `grad=None`

表示：

\[
\boxed{
\text{这个参数根本没有参与当前 Loss 的计算}
}
\]

---

<a id="origin-9077"></a>
### 165.2 `grad=0`

表示：

\[
\boxed{
\text{这个参数参与了计算，只不过当前导数恰好为 0}
}
\]

这就是：

```python
0 * parameter
```

技巧最核心的意义。

---

<a id="origin-9097"></a>
## 166. 为什么这对分布式训练有帮助？

MoE 中 Expert 是稀疏激活的。

比如不同 GPU 上：

```text
GPU 0：
Expert 0
Expert 1

GPU 1：
Expert 2
Expert 3
```

当前 Batch 可能：

```text
E0：有人用
E1：有人用
E2：有人用
E3：没人用
```

那么 E3 的参数如果完全没进入当前图：

```text
E3 参数
   ×
Loss
```

某些分布式训练机制可能把它判断成：

```text
unused parameter
```

这可能给：

```text
梯度同步
参数同步
DDP
```

等机制带来额外处理。

于是人为增加：

```python
0 * sum(...)
```

使它变成：

```text
E3 参数
   │
   ▼
  ×0
   │
   ▼
  Loss
```

于是框架看到的是：

> 这个参数参与了本轮计算，只不过梯度是 0。

而不是：

> 这个参数彻底没出现。

---

<a id="origin-9174"></a>
## 167. 为什么不直接执行一次 `expert(x)` 再乘 0？

例如为什么不写：

```python
0 * expert(x)
```

理论上也能够把 Expert 参数连进计算图。

但问题是：

> 这样真的会执行一遍完整 Expert FFN。

假设 Expert 包含：

```text
Linear
SiLU
Up Projection
Gate Projection
Down Projection
```

那么明明这个 Expert 一个 Token 都没收到，却还执行一次完整 FFN。

这样会浪费大量计算。

而：

```python
sum(
    p.sum()
    for p in expert.parameters()
)
```

只是简单引用参数并做求和。

不需要执行：

\[
Expert(x)
\]

完整前向。

所以它是一种更轻量的：

\[
\boxed{\text{Dummy Graph Connection}}
\]

即：

> 虚假的、零贡献的计算图连接。

---

<a id="origin-9233"></a>
## 168. 为什么只在训练时执行？

原代码：

```python
elif self.training:
    y[0, 0] += (
        0 *
        sum(
            p.sum()
            for p in expert.parameters()
        )
    )
```

重点：

```python
self.training
```

因为这个技巧主要解决的是：

```text
backward
梯度
分布式训练
参数同步
```

问题。

如果：

```python
model.eval()
```

进入推理：

```text
不做 backward

不更新参数
```

那么一个 Expert 没被选中：

> 直接跳过就行。

没有必要人为把它挂进计算图。

所以：

```text
训练模式：

Expert 没人用
↓
挂一个 0 贡献计算图


推理模式：

Expert 没人用
↓
直接跳过
```

---

<a id="origin-9304"></a>
## 169. 放回原来的 MoE 代码理解

原代码：

```python
for i, expert in enumerate(self.experts):

    mask = (topk_idx == i)

    if mask.any():

        token_idx = (
            mask
            .any(dim=-1)
            .nonzero()
            .flatten()
        )

        weight = (
            topk_weight[mask]
            .view(-1, 1)
        )

        y.index_add_(
            0,
            token_idx,
            (
                expert(x_flat[token_idx])
                * weight
            ).to(y.dtype)
        )

    elif self.training:

        y[0, 0] += (
            0 *
            sum(
                p.sum()
                for p in expert.parameters()
            )
        )
```

可以直接翻译成：

```text
如果当前 Expert 有 Token：

    真正运行 Expert
    ↓
    得到 Expert 输出
    ↓
    乘 Gate Weight
    ↓
    index_add_ 加回 y


如果当前 Expert 没有 Token：

    不运行 Expert
    ↓
    但训练阶段
    ↓
    用 0 × Expert参数
    ↓
    把参数挂到 y 的计算图上
```

---

<a id="origin-9374"></a>
## 170. 一个完整的具体例子

假设有：

```text
Expert 0
Expert 1
Expert 2
Expert 3
```

当前 Batch：

```text
Token 0 → Expert 0, Expert 1

Token 1 → Expert 0, Expert 2

Token 2 → Expert 1, Expert 2
```

所以：

```text
Expert 0：
Token 0
Token 1

Expert 1：
Token 0
Token 2

Expert 2：
Token 1
Token 2

Expert 3：
没人
```

---

<a id="origin-9416"></a>
### 170.1 Expert 0

```python
mask.any() == True
```

所以：

```text
取出 Token 0、1
↓
Expert 0 FFN
↓
乘权重
↓
index_add_
```

Expert 0 参数正常进入计算图。

---

<a id="origin-9438"></a>
### 170.2 Expert 1

同理：

```text
Token 0、2
↓
Expert 1
↓
y
```

参数正常进入计算图。

---

<a id="origin-9454"></a>
### 170.3 Expert 2

同理：

```text
Token 1、2
↓
Expert 2
↓
y
```

参数正常进入计算图。

---

<a id="origin-9470"></a>
### 170.4 Expert 3

因为：

```python
mask.any() == False
```

所以根本没有：

```python
expert3(...)
```

正常情况下：

```text
Expert 3 参数

    ×

    y
```

于是训练模式下执行：

```python
y[0, 0] += (
    0 *
    sum(
        p.sum()
        for p in expert3.parameters()
    )
)
```

构造：

```text
Expert 3 参数
      │
      ▼
  参数全部求和
      │
      ▼
     × 0
      │
      ▼
      0
      │
      ▼
   y[0,0]
      │
      ▼
 后续 Transformer
      │
      ▼
     Loss
```

于是：

\[
\boxed{
Expert 3 进入了计算图
}
\]

但是：

\[
\boxed{
Expert 3 对当前输出贡献为 0
}
\]

并且：

\[
\boxed{
Expert 3 当前梯度为 0
}
\]

---

<a id="origin-9556"></a>
## 171. 为什么这种做法不会破坏模型输出？

因为加入：

\[
0\times参数
\]

永远是：

\[
0
\]

所以：

\[
y_{new}
=
y_{old}+0
\]

即：

\[
\boxed{
y_{new}=y_{old}
}
\]

因此：

```text
logits 不变
预测不变
Cross Entropy 不变
前向结果不变
```

唯一改变的是：

\[
\boxed{
\text{计算图结构}
}
\]

---

<a id="origin-9605"></a>
## 172. 最终可以把这行代码理解成什么？

原代码：

```python
y[0, 0] += 0 * sum(
    p.sum()
    for p in expert.parameters()
)
```

最容易理解的中文翻译是：

> **“这个 Expert 当前虽然没有任何 Token 使用，但训练时仍然把它的全部参数通过一个数值为 0 的假路径连接到输出 y 上，使它参与当前计算图，从而避免它彻底成为未使用参数；由于前面乘了 0，因此不会改变输出，也不会产生真正的参数更新。”**

---

<a id="origin-9622"></a>
## 173. 最后记住这三个结论

<a id="origin-9624"></a>
### 173.1 第一

\[
\boxed{
0\times parameter
\text{ 的前向值为 0}
}
\]

所以：

> 不改变模型输出。

---

<a id="origin-9639"></a>
### 173.2 第二

\[
\boxed{
\frac{\partial(0\theta)}
{\partial\theta}
=
0
}
\]

所以：

> 不会真正训练这个没有被选中的 Expert。

---

<a id="origin-9656"></a>
### 173.3 第三

虽然：

\[
0\theta=0
\]

但是：

\[
\theta
\]

依然参与了这个运算，所以：

\[
\boxed{
\theta
\text{ 仍然存在于当前计算图中}
}
\]

---

<a id="origin-9681"></a>
## 174. 一句话总结

\[
\boxed{
\texttt{y[0,0] += 0 * sum(...)}
}
\]

本质就是：

\[
\boxed{
\text{用一个“数值为 0、梯度也为 0，但计算图不断开”的假连接，
把当前没有被路由到的 Expert 参数挂到最终输出上。}
}
\]

可以把它记成：

```text
没人使用的 Expert
        ↓
不真正执行 FFN
        ↓
所有参数求和
        ↓
      × 0
        ↓
   数值还是 0
        ↓
      加到 y
        ↓
参数仍在计算图中
```

所以这行代码的核心目的不是：

\[
\boxed{\text{计算}}
\]

而是：

\[
\boxed{\text{维持计算图连接}}
\]
---

<a id="origin-9729"></a>
## 175. 接下来进入 Aux Loss

代码：

```python
if (
    self.training
    and
    self.config.router_aux_loss_coef > 0
):
```

也就是：

> 只有训练时，并且辅助损失系数大于 0，才计算 Router 负载均衡损失。

因为推理时：

```text
不需要训练 Router
```

自然也不需要 Aux Loss。

---

<a id="origin-9755"></a>
## 176. 为什么 MoE 需要 Aux Loss？

因为 Router 可能产生：

\[
\boxed{\text{Expert Collapse}}
\]

比如：

```text
E0 → 几乎没人
E1 → 几乎没人
E2 → 80% Token
E3 → 几乎没人
```

这会导致：

```text
大量 Expert 参数浪费

负载不均衡

某些 GPU 特别忙

其他 GPU 空闲
```

因此要额外惩罚严重偏向某些 Expert 的 Router。

---

<a id="origin-9788"></a>
## 177. `one_hot(topk_idx)` 在这里干什么？

代码：

```python
load = F.one_hot(
    topk_idx,
    self.config.num_experts
).float().mean(0)
```

这是 Aux Loss 最关键的一行之一。

现在：

\[
topk\_idx=
\begin{bmatrix}
1&2\\
0&3\\
2&0
\end{bmatrix}
\]

shape：

\[
[N,K]=[3,2]
\]

---

<a id="origin-9820"></a>
## 178. one-hot 后的 Shape

因为：

\[
E=4
\]

所以：

```python
F.one_hot(
    topk_idx,
    4
)
```

得到：

\[
[3,2,4]
\]

即：

\[
[N,K,E]
\]

---

<a id="origin-9851"></a>
## 179. 具体展开

Token 0：

```text
[1,2]
```

转 one-hot：

```text
槽位 0：
Expert 1

[0,1,0,0]

槽位 1：
Expert 2

[0,0,1,0]
```

---

Token 1：

```text
[0,3]
```

变成：

```text
[1,0,0,0]

[0,0,0,1]
```

---

Token 2：

```text
[2,0]
```

变成：

```text
[0,0,1,0]

[1,0,0,0]
```

---

<a id="origin-9907"></a>
## 180. 所以 one-hot 完整结果

可以写成：

\[
\begin{bmatrix}
[
0,1,0,0
],
[
0,0,1,0
]
\\
[
1,0,0,0
],
[
0,0,0,1
]
\\
[
0,0,1,0
],
[
1,0,0,0
]
\end{bmatrix}
\]

shape：

\[
[3,2,4]
\]

---

<a id="origin-9944"></a>
## 181. `.mean(0)` 到底平均谁？

代码：

```python
.mean(0)
```

第 0 维是：

\[
N
\]

也就是 Token 维。

所以：

> 对所有 Token 求平均。

最后得到：

\[
[K,E]
\]

即：

\[
[2,4]
\]

---

<a id="origin-9978"></a>
## 182. 具体计算 load

第 0 个 Top-k 槽位：

```text
Token 0 → E1
Token 1 → E0
Token 2 → E2
```

所以：

```text
E0：1/3
E1：1/3
E2：1/3
E3：0
```

第一行：

\[
[
1/3,
1/3,
1/3,
0
]
\]

---

第 1 个 Top-k 槽位：

```text
Token 0 → E2
Token 1 → E3
Token 2 → E0
```

所以：

```text
E0：1/3
E1：0
E2：1/3
E3：1/3
```

第二行：

\[
[
1/3,
0,
1/3,
1/3
]
\]

所以：

\[
load=
\begin{bmatrix}
1/3&1/3&1/3&0\\
1/3&0&1/3&1/3
\end{bmatrix}
\]

---

<a id="origin-10050"></a>
## 183. 这里的 load 和之前讲的 \(f_i\) 有一点实现细节差异

之前为了理解，我们把：

\[
f_i
\]

讲成：

> Expert \(i\) 实际收到的 Token 比例。

这段代码则稍微更细。

它没有先把两个 Top-k 槽位合并成一个：

\[
[E]
\]

而是保留：

\[
[K,E]
\]

也就是：

> 分别统计“Top-k 第 1 个槽位”和“Top-k 第 2 个槽位”各自选择 Expert 的比例。

所以：

\[
load[k,i]
\]

表示：

> 在第 \(k\) 个 Top-k 槽位中，有多少比例的 Token 选择了 Expert \(i\)。

本质仍然是在统计：

\[
\boxed{\text{实际路由负载}}
\]

---

<a id="origin-10098"></a>
## 184. `scores.mean(0)` 是什么？

回忆：

\[
scores=
\begin{bmatrix}
0.10&0.60&0.25&0.05\\
0.40&0.10&0.20&0.30\\
0.15&0.10&0.65&0.10
\end{bmatrix}
\]

执行：

```python
scores.mean(0)
```

就是沿 Token 维求平均。

Expert 0：

\[
P_0=
\frac{
0.10+0.40+0.15
}{3}
\]

得到：

\[
0.2167
\]

Expert 1：

\[
P_1=
\frac{
0.60+0.10+0.10
}{3}
=
0.2667
\]

Expert 2：

\[
P_2=
\frac{
0.25+0.20+0.65
}{3}
=
0.3667
\]

Expert 3：

\[
P_3=
\frac{
0.05+0.30+0.10
}{3}
=
0.15
\]

所以：

\[
scores.mean(0)
=
[
0.2167,
0.2667,
0.3667,
0.15
]
\]

这就是我们之前讲的：

\[
\boxed{P_i}
\]

---

<a id="origin-10188"></a>
## 185. 再复习一次 \(P_i\)

\[
\boxed{
P_i
=
\text{Router 对 Expert i 的平均概率}
}
\]

也可以说：

> Router 平均有多喜欢这个 Expert。

所以：

```text
P_i
不是最终是否真的选中
```

而是：

```text
Softmax 概率层面的偏好
```

---

<a id="origin-10217"></a>
## 186. 为什么 `load * scores.mean(0)` 能广播？

当前：

\[
load.shape=[K,E]=[2,4]
\]

而：

\[
scores.mean(0).shape=[E]=[4]
\]

PyTorch 广播以后：

\[
[4]
\]

会被当成：

```text
每一个 Top-k 槽位
都乘同一个平均 Router 概率
```

即：

\[
\begin{bmatrix}
load_{0,0}P_0&
load_{0,1}P_1&
...\\
load_{1,0}P_0&
load_{1,1}P_1&
...
\end{bmatrix}
\]

---

<a id="origin-10259"></a>
## 187. 用我们的数字算一次

\[
load=
\begin{bmatrix}
1/3&1/3&1/3&0\\
1/3&0&1/3&1/3
\end{bmatrix}
\]

而：

\[
P=
[
0.2167,
0.2667,
0.3667,
0.15
]
\]

第一行：

\[
\frac13\times0.2167
+
\frac13\times0.2667
+
\frac13\times0.3667
+
0\times0.15
\]

约：

\[
0.2834
\]

第二行：

\[
\frac13\times0.2167
+
0
+
\frac13\times0.3667
+
\frac13\times0.15
\]

约：

\[
0.2445
\]

总和：

\[
0.5279
\]

---

<a id="origin-10325"></a>
## 188. 再乘 `num_experts`

代码：

```python
* self.config.num_experts
```

这里：

\[
E=4
\]

所以：

\[
0.5279\times4
\approx2.1116
\]

如果：

```text
router_aux_loss_coef = 0.01
```

那么最终：

\[
aux\_loss
=
2.1116\times0.01
\]

约：

\[
\boxed{
0.0211
}
\]

---

<a id="origin-10370"></a>
## 189. 为什么还要乘 `router_aux_loss_coef`？

因为总训练 Loss 一般不会只优化：

```text
Router Balance
```

真正主要任务还是：

\[
L_{\text{LM}}
\]

也就是语言模型的 Cross Entropy。

所以最后：

\[
L
=
L_{\text{LM}}
+
L_{\text{aux}}
\]

而配置：

```python
router_aux_loss_coef
```

控制：

> 负载均衡到底有多重要。

如果它太大：

```text
Router 可能为了平均分配，
牺牲真正的模型能力。
```

如果太小：

```text
又可能压不住 Expert Collapse。
```

---

<a id="origin-10421"></a>
## 190. 回到经典的 \(f_iP_i\)

传统表达：

\[
\boxed{
L_{\text{aux}}
=
N_E
\sum_i
f_iP_i
}
\]

其中：

\[
f_i
=
\text{Expert i 实际收到多少 Token}
\]

\[
P_i
=
\text{Router 平均有多喜欢 Expert i}
\]

这段代码的 `load`：

\[
[K,E]
\]

可以理解成：

> 将 \(f_i\) 进一步按 Top-k 槽位拆开统计。

然后：

```python
(load * scores.mean(0)).sum()
```

本质仍然是在做：

\[
\boxed{
\text{实际负载}
\times
\text{Router 偏好}
}
\]

---

<a id="origin-10477"></a>
## 191. 为什么需要同时有“实际负载”和“Router 概率”？

如果只看实际选择：

```text
E2 收到了 80% Token
```

我们确实知道它过载。

但是实际选择来源于：

```text
Top-k
```

这是一个离散过程。

它不方便直接给 Router 一个平滑梯度。

而：

\[
P_i
\]

来自：

\[
softmax(W_rx)
\]

它是：

\[
\boxed{\text{可微}}
\]

的。

所以：

```text
load
告诉模型：
实际谁太忙。

P_i
提供梯度：
Router 应该怎么调。
```

---

<a id="origin-10531"></a>
## 192. 用一句话记住

\[
\boxed{
f_i
=
\text{这个 Expert 实际接到了多少活}
}
\]

\[
\boxed{
P_i
=
\text{Router 平均有多想继续把活交给它}
}
\]

所以：

\[
\boxed{
f_iP_i
=
\text{已经很忙，而且 Router 还特别偏爱它的程度}
}
\]

---

<a id="origin-10561"></a>
## 193. General Aux Loss 和代码实现里的区别

先看最通用的公式：

\[
\boxed{
L_{\text{aux}}
=
\lambda E
\sum_{i=1}^{E}
f_iP_i
}
\]

其中：

\[
P_i
=
\frac1T
\sum_{t=1}^{T}
p_{t,i}
\]

表示：

> Router 对 Expert \(i\) 的平均概率。

而：

\[
f_i
=
\frac{
\text{Expert }i\text{ 被 Top-k 选中的总次数}
}{
T\times K
}
\]

表示：

> 把所有 Top-k 位置合在一起以后，Expert \(i\) 实际承担了多少比例的路由。

---

<a id="origin-10607"></a>
## 194. General 公式：不区分“第几个 Top-k”

假设：

\[
TopK=2
\]

有 3 个 Token：

```text
Token 0 → E1, E2

Token 1 → E0, E3

Token 2 → E2, E0
```

一共有：

\[
3\times2=6
\]

次 Expert 选择。

统计每个 Expert 总共被选中了多少次：

```text
E0：2 次
E1：1 次
E2：2 次
E3：1 次
```

因此：

\[
f_0=\frac26=\frac13
\]

\[
f_1=\frac16
\]

\[
f_2=\frac26=\frac13
\]

\[
f_3=\frac16
\]

所以：

\[
\boxed{
f=
\left[
\frac13,
\frac16,
\frac13,
\frac16
\right]
}
\]

这里完全不关心：

```text
E0 是第一个被选中，
还是第二个被选中。
```

只要被选中一次，就记一次。

所以 General 公式的思想是：

\[
\boxed{
\text{把全部 }T\times K\text{ 次路由放在一起统计}
}
\]

---

<a id="origin-10693"></a>
## 195. 代码里的做法：保留 Top-k 槽位

前面的代码中，Top-2 结果同样是：

```text
Token 0 → E1, E2

Token 1 → E0, E3

Token 2 → E2, E0
```

但是代码不会立刻把 6 次选择全部混在一起。

而是分别看两个位置。

---

<a id="origin-10711"></a>
## 196. 第一个 Top-k 槽位

只看每个 Token 的第一个 Expert：

```text
Token 0 → E1
Token 1 → E0
Token 2 → E2
```

于是：

\[
f^{(1)}
=
\left[
\frac13,
\frac13,
\frac13,
0
\right]
\]

这里：

\[
f_i^{(1)}
\]

表示：

> Expert \(i\) 在第一个 Top-k 槽位中被选择的比例。

---

<a id="origin-10746"></a>
## 197. 第二个 Top-k 槽位

再看第二个 Expert：

```text
Token 0 → E2
Token 1 → E3
Token 2 → E0
```

于是：

\[
f^{(2)}
=
\left[
\frac13,
0,
\frac13,
\frac13
\right]
\]

这里：

\[
f_i^{(2)}
\]

表示：

> Expert \(i\) 在第二个 Top-k 槽位中被选择的比例。

---

<a id="origin-10781"></a>
## 198. 两种统计方式放在一起

General 公式：

\[
\boxed{
f=
\left[
\frac13,
\frac16,
\frac13,
\frac16
\right]
}
\]

代码里的槽位统计：

\[
\boxed{
f^{(1)}
=
\left[
\frac13,
\frac13,
\frac13,
0
\right]
}
\]

\[
\boxed{
f^{(2)}
=
\left[
\frac13,
0,
\frac13,
\frac13
\right]
}
\]

两者不是完全不同的东西。

实际上 General 的 \(f_i\) 就是两个槽位统计结果的平均：

\[
\boxed{
f_i
=
\frac{
f_i^{(1)}+f_i^{(2)}
}{2}
}
\]

因为这里：

\[
K=2
\]

---

<a id="origin-10847"></a>
## 199. 验证一下

对于 E0：

\[
f_0
=
\frac{
\frac13+\frac13
}{2}
=
\frac13
\]

对于 E1：

\[
f_1
=
\frac{
\frac13+0
}{2}
=
\frac16
\]

对于 E2：

\[
f_2
=
\frac{
\frac13+\frac13
}{2}
=
\frac13
\]

对于 E3：

\[
f_3
=
\frac{
0+\frac13
}{2}
=
\frac16
\]

所以正好得到：

\[
\boxed{
f=
\left[
\frac13,
\frac16,
\frac13,
\frac16
\right]
}
\]

---

<a id="origin-10913"></a>
## 200. 但是有一个非常重要的系数区别

General 形式：

\[
L_{\text{aux}}
=
\lambda E
\sum_i
f_iP_i
\]

因为：

\[
f_i
=
\frac{
f_i^{(1)}+f_i^{(2)}
}{2}
\]

所以代入：

\[
L_{\text{aux}}
=
\lambda E
\sum_i
\frac{
f_i^{(1)}+f_i^{(2)}
}{2}
P_i
\]

得到：

\[
\boxed{
L_{\text{aux}}
=
\frac{\lambda E}{2}
\left[
\sum_i f_i^{(1)}P_i
+
\sum_i f_i^{(2)}P_i
\right]
}
\]

---

<a id="origin-10965"></a>
## 201. 而代码中的槽位求和没有除以 2

代码式的思路更接近：

\[
\boxed{
L_{\text{aux}}^{code}
=
\lambda E
\left[
\sum_i f_i^{(1)}P_i
+
\sum_i f_i^{(2)}P_i
\right]
}
\]

所以对于：

\[
K=2
\]

它和刚才定义的 General 形式之间相差：

\[
\boxed{2}
\]

也就是说：

\[
\boxed{
L_{\text{aux}}^{code}
=
2
L_{\text{aux}}^{general}
}
\]

前提是两边使用同一个：

\[
\lambda
\]

---

<a id="origin-11013"></a>
## 202. 为什么会有这个差别？

原因不是负载均衡思想不同。

而是：

> **归一化方式不同。**

General 定义：

\[
f_i
=
\frac{
\text{Expert i 被选择次数}
}{
T\times K
}
\]

所以：

\[
\sum_i f_i=1
\]

---

而按槽位分别统计时：

\[
\sum_i f_i^{(1)}=1
\]

同时：

\[
\sum_i f_i^{(2)}=1
\]

所以把两个槽位直接加起来以后：

\[
\sum_i
\left(
f_i^{(1)}+f_i^{(2)}
\right)
=
2
\]

因此相比 General 的统计方法，多出了一个：

\[
K=2
\]

的尺度。

---

<a id="origin-11074"></a>
## 203. 更一般的 Top-k 情况

如果：

\[
TopK=K
\]

General 定义：

\[
\boxed{
f_i
=
\frac{
\text{Expert i 在所有 Top-k 中被选择的次数}
}{
TK
}
}
\]

那么：

\[
\sum_i f_i=1
\]

而如果按照每个槽位分别统计：

\[
f_i^{(1)},f_i^{(2)},\dots,f_i^{(K)}
\]

则：

\[
\boxed{
f_i
=
\frac1K
\sum_{k=1}^{K}
f_i^{(k)}
}
\]

因此：

\[
\boxed{
L_{\text{aux}}^{general}
=
\frac{\lambda E}{K}
\sum_{k=1}^{K}
\sum_{i=1}^{E}
f_i^{(k)}P_i
}
\]

如果某个实现直接对所有槽位求和，而没有再除以 \(K\)，那么：

\[
\boxed{
L_{\text{aux}}^{code}
=
\lambda E
\sum_{k=1}^{K}
\sum_{i=1}^{E}
f_i^{(k)}P_i
}
\]

两者只是在：

\[
\boxed{\text{尺度}}
\]

上相差一个：

\[
K
\]

---

<a id="origin-11160"></a>
## 204. 所以到底应该记哪个？

通用形式如下：

\[
\boxed{
L_{\text{aux}}
=
\lambda E
\sum_i
f_iP_i
}
\]

其中：

\[
\boxed{
f_i
=
\frac{
\text{Expert i 在全部 }TK\text{ 次路由中被选中的次数}
}{
TK
}
}
\]

这样最容易理解。

然后看到具体代码时再补一句：

> 有些实现不会先把 Top-k 的 \(K\) 个槽位合并，而是分别统计每个槽位的 Expert 使用率后直接求和，因此会和这个 General 公式相差一个与 \(K\) 有关的常数尺度；这个常数通常可以被辅助损失系数 \(\lambda\) 吸收。

---

<a id="origin-11196"></a>
## 205. 一句话总结两者区别

General 公式：

\[
\boxed{
\text{把所有 Top-k 选择合起来，统一统计一个 }f_i
}
\]

代码中的方式：

\[
\boxed{
\text{保留每个 Top-k 槽位，分别统计 }f_i^{(1)},f_i^{(2)},\dots
}
\]

对于 Top-2：

\[
\boxed{
f_i
=
\frac{
f_i^{(1)}+f_i^{(2)}
}{2}
}
\]

所以两种方法：

> **负载均衡思想完全一样，主要区别只是统计方式和归一化尺度不同。**

---

<a id="origin-11232"></a>
## 206. 为什么 Aux Loss 能改变 Router？

假设：

\[
f_2
\]

很大。

那么：

\[
f_2P_2
\]

对：

\[
P_2
\]

会非常敏感。

为了降低 Loss，训练会倾向于：

\[
P_2\downarrow
\]

而：

\[
P_2
=
softmax(W_rx)
\]

所以：

\[
\frac{\partial L}
{\partial W_r}
\neq0
\]

最终：

\[
W_r
\]

会被更新。

于是 Router 下一次就会：

> 少把 Token 往已经拥挤的 Expert 2 上送。

---

<a id="origin-11292"></a>
## 207. `scores.new_zeros(1).squeeze()` 是什么？

如果：

```text
当前不是训练模式
```

或者：

```text
router_aux_loss_coef <= 0
```

就不计算真正 Aux Loss。

代码：

```python
self.aux_loss = (
    scores
    .new_zeros(1)
    .squeeze()
)
```

先：

```python
scores.new_zeros(1)
```

创建：

```text
长度为 1 的零 Tensor
```

并且：

```text
device
dtype
```

和 `scores` 一致。

例如：

```text
GPU 上的 BF16
```

那么这个 0 也在：

```text
同一个 GPU
同一个 dtype
```

---

<a id="origin-11354"></a>
## 208. `.squeeze()` 为什么要用？

原来：

```text
shape = [1]
```

经过：

```python
.squeeze()
```

变成：

```text
shape = []
```

也就是：

\[
\boxed{\text{0 维标量 Tensor}}
\]

这样它更像真正的：

```text
loss 标量
```

---

<a id="origin-11388"></a>
### 208.1 `self.aux_loss = scores.new_zeros(1).squeeze()` 详细解释

原代码：

```python
self.aux_loss = scores.new_zeros(1).squeeze()
```

这行代码的作用非常简单：

> 当当前不需要计算真正的 MoE Router 辅助损失时，创建一个值为 0 的标量 Tensor，作为 `aux_loss`。

也就是说：

\[
\boxed{
self.aux\_loss = 0
}
\]

但是代码没有直接写：

```python
self.aux_loss = 0
```

也没有写：

```python
self.aux_loss = torch.tensor(0.)
```

而是写：

```python
scores.new_zeros(1).squeeze()
```

主要是为了让这个 0：

\[
\boxed{
\text{自动继承 scores 的 device 和 dtype}
}
\]

---

<a id="origin-11436"></a>
## 209. 这行代码出现在哪里？

完整逻辑类似：

```python
if self.training and self.config.router_aux_loss_coef > 0:
    load = F.one_hot(
        topk_idx,
        self.config.num_experts
    ).float().mean(0)

    self.aux_loss = (
        load * scores.mean(0)
    ).sum() \
    * self.config.num_experts \
    * self.config.router_aux_loss_coef

else:
    self.aux_loss = scores.new_zeros(1).squeeze()
```

也就是说有两种情况。

---

<a id="origin-11461"></a>
### 209.1 情况 1：训练阶段，而且开启了 Router Aux Loss

那么真正计算：

\[
L_{\text{aux}}
\]

例如：

\[
L_{\text{aux}}=0.021
\]

于是：

```python
self.aux_loss = tensor(0.021)
```

---

<a id="origin-11483"></a>
### 209.2 情况 2：不需要 Aux Loss

例如：

```text
当前处于 eval 模式
```

或者：

```text
router_aux_loss_coef <= 0
```

那么不需要计算真实的负载均衡损失。

但为了让后面的代码仍然能够统一写：

```python
total_loss = lm_loss + layer.aux_loss
```

这里最好仍然给：

```python
self.aux_loss
```

一个 Tensor。

于是设置成：

\[
\boxed{0}
\]

---

<a id="origin-11521"></a>
## 210. 为什么不能直接写 `self.aux_loss = 0`？

当然从 Python 数值上：

```python
self.aux_loss = 0
```

也能表示：

\[
0
\]

但是这里的：

```text
0
```

是一个普通 Python `int`。

而真正的训练 Loss 通常是：

```python
torch.Tensor
```

例如：

```python
lm_loss
```

可能是：

```text
CUDA Tensor
BF16 / FP32 Tensor
```

因此更好的做法是：

\[
\boxed{
aux\_loss
\text{ 始终保持为 PyTorch Tensor}
}
\]

这样后续代码更加统一。

例如：

```python
loss = lm_loss + aux_loss
```

不需要判断：

```python
if isinstance(aux_loss, Tensor):
```

之类的问题。

---

<a id="origin-11589"></a>
## 211. 为什么不直接写 `torch.tensor(0.)`？

例如：

```python
self.aux_loss = torch.tensor(0.)
```

看起来似乎已经很好了。

但是它有一个潜在问题：

> 新创建的 Tensor 默认不一定和 `scores` 在同一个设备、同一个 dtype。

例如：

```python
scores.device
```

可能是：

```text
cuda:0
```

而：

```python
torch.tensor(0.)
```

默认一般创建在：

```text
CPU
```

于是可能出现：

```text
lm_loss 在 GPU
aux_loss 在 CPU
```

后面：

```python
lm_loss + aux_loss
```

就可能出现设备不一致问题。

---

<a id="origin-11644"></a>
## 212. 举个设备不一致的例子

假设：

```python
scores.device
```

是：

```text
cuda:0
```

而你写：

```python
aux_loss = torch.tensor(0.)
```

那么默认：

```text
aux_loss.device = cpu
```

后面：

```python
loss = lm_loss + aux_loss
```

如果：

```text
lm_loss.device = cuda:0
```

就相当于：

```text
GPU Tensor
+
CPU Tensor
```

这是不希望出现的。

所以更稳妥的方式是：

```python
scores.new_zeros(...)
```

---

<a id="origin-11700"></a>
## 213. `scores.new_zeros(1)` 到底是什么意思？

先看：

```python
scores.new_zeros(1)
```

它可以理解成：

> 以 `scores` 为模板，创建一个新的全零 Tensor。

关键是：

\[
\boxed{
new\_zeros
}
\]

不仅创建零，还会继承原 Tensor 的很多属性。

最重要的是：

```text
device
dtype
```

---

<a id="origin-11731"></a>
## 214. 一个具体例子

假设：

```python
scores
```

满足：

```text
scores.shape = [100, 8]

scores.device = cuda:0

scores.dtype = torch.float16
```

那么：

```python
z = scores.new_zeros(1)
```

得到：

```text
z = tensor([0.], device='cuda:0', dtype=torch.float16)
```

也就是说：

\[
z.shape=[1]
\]

并且：

\[
z.device=scores.device
\]

\[
z.dtype=scores.dtype
\]

---

<a id="origin-11779"></a>
## 215. 可以把 `new_zeros` 理解成什么？

最简单的记法：

```python
scores.new_zeros(...)
```

相当于说：

> “照着 `scores` 的设备和数据类型，再造一个全 0 Tensor。”

也就是：

```text
scores
  ↓
作为模板
  ↓
创建新的 zero Tensor
```

---

<a id="origin-11803"></a>
## 216. 它大致等价于什么？

假设：

```python
scores.new_zeros(1)
```

概念上接近：

```python
torch.zeros(
    1,
    device=scores.device,
    dtype=scores.dtype
)
```

所以：

\[
\boxed{
scores.new\_zeros(1)
}
\]

是一个更简洁的写法。

---

<a id="origin-11833"></a>
## 217. 为什么参数写 `1`？

代码：

```python
scores.new_zeros(1)
```

这里的：

```text
1
```

表示：

> 创建一个长度为 1 的一维 Tensor。

所以结果 shape：

\[
\boxed{[1]}
\]

例如：

```python
tensor([0.])
```

注意它现在还不是严格意义上的“标量 Tensor”。

它是：

\[
\boxed{\text{含一个元素的一维 Tensor}}
\]

---

<a id="origin-11873"></a>
## 218. `[1]` 和标量 Tensor 有什么区别？

例如：

```python
a = torch.tensor([0.])
```

它的 shape：

```python
a.shape
```

是：

```text
torch.Size([1])
```

也就是：

\[
[1]
\]

而：

```python
b = torch.tensor(0.)
```

它的 shape：

```python
b.shape
```

是：

```text
torch.Size([])
```

也就是：

\[
[]
\]

这叫：

\[
\boxed{\text{0 维 Tensor}}
\]

通常也叫：

> scalar tensor

---

<a id="origin-11935"></a>
## 219. 为什么 Loss 通常喜欢是标量 Tensor？

Loss 通常表示：

\[
L
\]

也就是一个数。

例如：

\[
L=2.31
\]

所以更自然的 shape 是：

\[
[]
\]

而不是：

\[
[1]
\]

因此：

```python
scores.new_zeros(1)
```

之后又调用：

```python
.squeeze()
```

---

<a id="origin-11977"></a>
## 220. `.squeeze()` 是干什么的？

`squeeze()`：

> 删除长度为 1 的维度。

例如：

```python
x = torch.tensor([0.])
```

shape：

\[
[1]
\]

执行：

```python
x.squeeze()
```

得到：

```python
tensor(0.)
```

shape：

\[
[]
\]

所以：

```python
scores.new_zeros(1).squeeze()
```

完整过程就是：

```text
先创建：

[0.]

shape = [1]

        ↓ squeeze()

变成：

0.

shape = []
```

---

<a id="origin-12039"></a>
## 221. 用 shape 变化看最清楚

第一步：

```python
scores.new_zeros(1)
```

结果：

\[
shape=[1]
\]

值：

```python
tensor([0.])
```

第二步：

```python
.squeeze()
```

结果：

\[
shape=[]
\]

值：

```python
tensor(0.)
```

所以最终：

\[
\boxed{
self.aux\_loss
}
\]

是一个：

\[
\boxed{\text{值为 0 的标量 Tensor}}
\]

---

<a id="origin-12093"></a>
## 222. 为什么不直接写 `scores.new_zeros(())`？

其实可以。

例如：

```python
scores.new_zeros(())
```

也可以直接创建：

\[
shape=[]
\]

的标量 Tensor。

也就是说：

```python
scores.new_zeros(())

```

和：

```python
scores.new_zeros(1).squeeze()
```

最终效果类似。

这里只是作者选择了：

```python
new_zeros(1)
```

再：

```python
squeeze()
```

这种写法。

---

<a id="origin-12142"></a>
## 223. 为什么不用 `torch.zeros_like(scores)`？

如果写：

```python
torch.zeros_like(scores)
```

那么会创建一个和：

```python
scores
```

shape 完全一样的 Tensor。

假设：

\[
scores.shape=[N,E]
\]

例如：

\[
[1000,8]
\]

那就会创建：

\[
[1000,8]
\]

这么大的 0 Tensor。

但我们这里只需要：

\[
\boxed{\text{一个 0}}
\]

所以没必要浪费内存。

因此使用：

```python
scores.new_zeros(1)
```

只创建一个元素。

---

<a id="origin-12196"></a>
## 224. 为什么这里的 aux_loss 必须是 0？

回忆：

```python
if self.training and self.config.router_aux_loss_coef > 0:
```

只有满足条件才真正计算：

\[
L_{\text{aux}}
\]

否则表示：

> 当前这一轮不需要 Router 辅助损失。

数学上自然应该：

\[
\boxed{
L_{\text{aux}}=0
}
\]

这样总 Loss：

\[
L
=
L_{\text{LM}}
+
L_{\text{aux}}
\]

就变成：

\[
L
=
L_{\text{LM}}+0
\]

也就是：

\[
\boxed{
L=L_{\text{LM}}
}
\]

不会产生任何额外影响。

---

<a id="origin-12252"></a>
## 225. 一个完整例子

假设正常训练时：

\[
L_{\text{LM}}=2.4
\]

Router Aux Loss：

\[
L_{\text{aux}}=0.03
\]

那么：

\[
L=
2.4+0.03
=
2.43
\]

---

如果关闭 Aux Loss：

```python
router_aux_loss_coef = 0
```

那么代码进入：

```python
self.aux_loss = scores.new_zeros(1).squeeze()
```

得到：

\[
L_{\text{aux}}=0
\]

于是：

\[
L=
2.4+0
=
2.4
\]

---

<a id="origin-12306"></a>
## 226. 为什么还要把 `aux_loss` 保存成 Tensor？

因为后面模型可能统一收集：

```python
layer.aux_loss
```

比如：

```python
total_aux_loss = sum(
    layer.mlp.aux_loss
    for layer in model.layers
)
```

如果某些层：

```text
aux_loss 是 Tensor
```

而另一些层：

```text
aux_loss 是 None
```

代码就要额外判断。

但现在统一规定：

```text
有 Aux Loss：
返回一个 Tensor

没有 Aux Loss：
也返回一个值为 0 的 Tensor
```

后面就可以直接求和。

这是非常常见的编程思想：

\[
\boxed{
\text{用“零值”代替“没有值”}
}
\]

---

<a id="origin-12359"></a>
## 227. 为什么不用 `None`？

理论上可以：

```python
self.aux_loss = None
```

但是后面如果写：

```python
loss = lm_loss + self.aux_loss
```

就会出问题。

必须写：

```python
if self.aux_loss is not None:
    loss += self.aux_loss
```

而如果统一使用：

```python
tensor(0.)
```

就可以直接：

```python
loss += self.aux_loss
```

因为：

\[
L+0=L
\]

所以代码更加简洁。

---

<a id="origin-12404"></a>
## 228. `new_zeros` 最重要的优点：device 自动匹配

假设当前模型运行在：

```text
cuda:3
```

那么：

```python
scores.device
```

就是：

```text
cuda:3
```

执行：

```python
scores.new_zeros(1)
```

得到的 Tensor 自动也是：

```text
cuda:3
```

所以你不用写：

```python
torch.zeros(
    1,
    device=x.device
)
```

---

<a id="origin-12447"></a>
## 229. dtype 也自动匹配

假设：

```python
scores.dtype
```

是：

```text
torch.float32
```

那么：

```python
scores.new_zeros(1)
```

也是：

```text
float32
```

如果 `scores` 是：

```text
float16
```

创建出来也会跟随相应 dtype。

所以：

\[
\boxed{
new\_zeros
=
自动继承 dtype + device
}
\]

---

<a id="origin-12493"></a>
## 230. 一个直观对比

假设：

```python
scores
```

是：

```text
device = cuda:0
dtype = float16
```

---

如果写：

```python
torch.tensor(0.)
```

可能得到：

```text
device = cpu
dtype = float32
```

---

如果写：

```python
scores.new_zeros(1)
```

得到：

```text
device = cuda:0
dtype = float16
```

所以后者更安全。

---

<a id="origin-12542"></a>
## 231. `.squeeze()` 会不会把错误的维度也删掉？

这里不会有问题。

因为：

```python
scores.new_zeros(1)
```

明确只有一个维度：

\[
[1]
\]

所以：

```python
.squeeze()
```

只会把这个：

\[
1
\]

长度维度删掉。

得到：

\[
[]
\]

不存在多维 Tensor 被意外 squeeze 的问题。

---

<a id="origin-12582"></a>
## 232. 最终这行代码的每一步

原代码：

```python
self.aux_loss = scores.new_zeros(1).squeeze()
```

可以拆成：

```python
temp = scores.new_zeros(1)
```

此时：

```text
value = [0]

shape = [1]

device = scores.device

dtype = scores.dtype
```

然后：

```python
temp = temp.squeeze()
```

得到：

```text
value = 0

shape = []

device = scores.device

dtype = scores.dtype
```

最后：

```python
self.aux_loss = temp
```

所以：

\[
\boxed{
self.aux\_loss
=
\text{与 scores 同设备、同 dtype 的 0 维零 Tensor}
}
\]

---

<a id="origin-12644"></a>
## 233. 把它和正常 Aux Loss 对比

正常计算：

```python
self.aux_loss = (
    load * scores.mean(0)
).sum() \
* self.config.num_experts \
* self.config.router_aux_loss_coef
```

最终通常得到：

```python
tensor(0.0213)
```

shape：

\[
[]
\]

---

不计算 Aux Loss：

```python
self.aux_loss = scores.new_zeros(1).squeeze()
```

得到：

```python
tensor(0.)
```

shape：

\[
[]
\]

所以两种情况下：

```text
self.aux_loss
```

的数据结构完全一致：

```text
都是 Tensor
都是标量
都是相同 device
都是兼容 dtype
```

区别只是：

```text
一个是真实 loss

一个是 0
```

---

<a id="origin-12713"></a>
## 234. 这是一种非常典型的“接口统一”设计

代码希望后面的人不用管：

```text
这一层到底有没有计算 Aux Loss？
```

只要统一写：

```python
aux_loss = layer.aux_loss
```

就行。

因为：

```text
开启：
aux_loss = 真实值

关闭：
aux_loss = 0
```

所以：

\[
\boxed{
\text{调用接口始终一致}
}
\]

---

<a id="origin-12749"></a>
## 235. 和 Python `0` 最核心的区别

Python：

```python
0
```

只是一个普通整数。

而：

```python
scores.new_zeros(1).squeeze()
```

是：

\[
\boxed{\text{PyTorch 标量 Tensor}}
\]

它有：

```text
device
dtype
shape
Tensor 运算语义
```

因此更适合继续参与模型 Loss 计算。

---

<a id="origin-12784"></a>
## 236. 一句话理解 `new_zeros`

可以直接记：

```python
A.new_zeros(shape)
```

等价于一句人话：

> **“照着 A 的设备和数据类型，创建一个指定 shape 的全 0 Tensor。”**

所以：

```python
scores.new_zeros(1)
```

就是：

> “照着 scores，创建一个长度为 1 的零 Tensor。”

---

<a id="origin-12808"></a>
## 237. 一句话理解 `squeeze`

```python
.squeeze()
```

就是：

> 删除长度为 1 的维度。

这里：

\[
[1]
\]

变成：

\[
[]
\]

所以：

```python
tensor([0.])
```

变成：

```python
tensor(0.)
```

---

<a id="origin-12844"></a>
## 238. 最终流程图

```text
当前不需要 Aux Loss
        │
        ▼
scores.new_zeros(1)
        │
        ▼
创建：
tensor([0.])
shape = [1]
device = scores.device
dtype = scores.dtype
        │
        ▼
     squeeze()
        │
        ▼
创建：
tensor(0.)
shape = []
        │
        ▼
self.aux_loss
        │
        ▼
后面可以直接：
total_loss += aux_loss
```

---

<a id="origin-12877"></a>
## 239. 最后总结

原代码：

```python
self.aux_loss = scores.new_zeros(1).squeeze()
```

做了三件事情。

第一：

\[
\boxed{
\text{创建一个值为 0 的 Tensor}
}
\]

表示：

> 当前没有 Router Aux Loss。

第二：

\[
\boxed{
\text{自动继承 scores 的 device 和 dtype}
}
\]

避免出现：

```text
CPU / GPU 不一致

FP16 / FP32 不一致
```

第三：

\[
\boxed{
\text{通过 squeeze 把 [1] 变成标量 []}
}
\]

使：

```python
self.aux_loss
```

和正常计算出的 Loss 一样，都是标量 Tensor。

所以整行代码最准确的人话翻译是：

> **“当前不需要计算 Router 辅助损失，因此创建一个和 `scores` 同设备、同数据类型的标量 0，作为本层的 `aux_loss`，这样后续代码仍然可以统一地把它加入总 Loss，而不需要额外判断。”**

最终：

\[
\boxed{
\texttt{scores.new\_zeros(1).squeeze()}
=
\text{一个与 scores 兼容的标量 Tensor 0}
}
\]

---

<a id="origin-12947"></a>
## 240. 为什么 aux_loss 不直接 return？

这里：

```python
self.aux_loss = ...
```

但最后：

```python
return y.view(...)
```

没有：

```python
return y, aux_loss
```

说明这个设计选择了：

> 每个 MoE 层先把自己的 Aux Loss 保存在成员变量里。

之后更高层的模型：

```text
遍历各个 MoE Layer
```

把这些：

```python
layer.mlp.aux_loss
```

汇总起来。

所以：

\[
\boxed{
aux\_loss
\text{存在模块属性中，而不是 forward 第二个返回值}
}
\]

---

<a id="origin-12996"></a>
## 241. 最后恢复 Shape

代码：

```python
return y.view(
    batch_size,
    seq_len,
    hidden_dim
)
```

当前：

\[
y.shape=[N,H]
\]

也就是：

\[
[3,2]
\]

恢复：

\[
[B,T,H]
\]

即：

\[
[1,3,2]
\]

这样整个 MoE Layer：

> 输入什么 Shape，输出仍然是什么 Shape。

所以对于 Transformer 外部模块：

```text
输入 [B,T,H]

输出 [B,T,H]
```

跟普通 FFN 完全兼容。

---

<a id="origin-13048"></a>
## 242. 把整个代码流程串起来

完整过程：

```text
输入 x
[B,T,H]
   │
   ▼
view
   │
   ▼
x_flat
[N,H]
   │
   ▼
Linear Router
   │
   ▼
Router logits
[N,E]
   │
   ▼
Softmax
   │
   ▼
scores
[N,E]
   │
   ▼
Top-k
   │
   ├───────────────┐
   ▼               ▼
topk_idx        topk_weight
[N,K]             [N,K]
   │
   │
   ▼
按照 Expert
寻找自己的 Token
   │
   ▼
token_idx
   │
   ▼
取出 x_flat[token_idx]
   │
   ▼
Expert FFN
   │
   ▼
Expert Output
   │
   ▼
乘 Gate Weight
   │
   ▼
index_add_
   │
   ▼
累加回原 Token
   │
   ▼
y
[N,H]
   │
   ▼
view
   │
   ▼
[B,T,H]
```

同时训练阶段：

```text
topk_idx
   │
   ▼
one_hot
   │
   ▼
实际负载 load
   │
   ┐
   │
scores
   │
   ▼
scores.mean(0)
Router 平均偏好 P_i
   │
   └──────┐
          ▼
      load × P
          │
          ▼
       aux_loss
```

---

<a id="origin-13151"></a>
## 243. 这段代码最核心的 6 个 Tensor

关键结论如下。

| Tensor | Shape | 含义 |
|---|---|---|
| `x_flat` | \([N,H]\) | 展平后的所有 Token |
| `scores` | \([N,E]\) | 每个 Token 对所有 Expert 的概率 |
| `topk_idx` | \([N,K]\) | 每个 Token 选择的 K 个 Expert |
| `topk_weight` | \([N,K]\) | 被选 Expert 的 Gate Weight |
| `y` | \([N,H]\) | 最终 MoE 输出 |
| `load` | \([K,E]\) | 各 Top-k 槽位的 Expert 实际选择比例 |

其中：

\[
N=B\times T
\]

---

<a id="origin-13172"></a>
## 244. 最核心的三个公式对应哪段代码？

<a id="origin-13174"></a>
### 244.1 Router

数学：

\[
\boxed{
P
=
softmax(XW_r)
}
\]

代码：

```python
scores = F.softmax(
    self.gate(x_flat),
    dim=-1
)
```

---

<a id="origin-13197"></a>
### 244.2 Top-k MoE 输出

数学：

\[
\boxed{
y_t
=
\sum_{i\in TopK(t)}
g_{t,i}E_i(x_t)
}
\]

代码核心：

```python
y.index_add_(
    0,
    token_idx,
    expert(x_flat[token_idx])
    * weight
)
```

---

<a id="origin-13223"></a>
### 244.3 负载均衡

概念公式：

\[
\boxed{
L_{\text{aux}}
=
N_E
\sum_i
f_iP_i
}
\]

代码：

```python
load = F.one_hot(
    topk_idx,
    self.config.num_experts
).float().mean(0)

self.aux_loss = (
    load
    * scores.mean(0)
).sum() \
* self.config.num_experts \
* self.config.router_aux_loss_coef
```

---

<a id="origin-13255"></a>
## 245. 为什么 MoE 可以“参数很多，但每 Token 计算较少”？

假设：

```text
8 个 Expert
```

每个 Expert：

\[
100M
\]

参数。

那么总 Expert 参数：

\[
800M
\]

但是：

\[
TopK=2
\]

意味着每个 Token 只真正执行：

```text
2 个 Expert
```

所以每个 Token 只激活大约：

\[
200M
\]

Expert 参数。

于是：

\[
\boxed{
\text{Total Parameters}
\gg
\text{Activated Parameters per Token}
}
\]

这就是 MoE 最大价值。

---

<a id="origin-13311"></a>
## 246. 为什么不同 Expert 会慢慢学出不同能力？

因为不同 Expert 收到：

\[
\boxed{\text{不同 Token}}
\]

例如：

```text
Expert 0
长期收到某类 Token

Expert 1
长期收到另一类 Token
```

于是它们的：

```text
训练数据不同

梯度不同

参数更新方向不同
```

所以最后形成：

\[
\boxed{\text{Expert Specialization}}
\]

---

<a id="origin-13347"></a>
## 247. Router 看的是词本身吗？

不是。

Router 输入：

\[
x
\]

是：

\[
\boxed{\text{当前 Transformer 层的 hidden state}}
\]

hidden state 已经包含上下文信息。

所以：

```text
Apple released iPhone.
```

里的 `Apple`

和：

```text
I ate an apple.
```

里的 `apple`

虽然词面相同或接近：

```text
hidden state 完全可能不同
```

所以它们可能：

\[
\boxed{\text{被路由到不同 Expert}}
\]

---

<a id="origin-13395"></a>
## 248. 同一个 Token 在不同层会不会去不同 Expert？

完全可能。

因为不同 Transformer 层：

```text
hidden state 不同

Router 参数也不同
```

所以：

```text
Layer 5：
Token → Expert 1,3

Layer 10：
Token → Expert 2,6

Layer 20：
Token → Expert 0,7
```

都是正常的。

因此 MoE Routing 是：

\[
\boxed{
\text{Token-level}
+
\text{Context-dependent}
+
\text{Layer-dependent}
}
\]

---

<a id="origin-13436"></a>
## 249. 这段实现为什么没有把所有 Expert 都计算一遍？

因为那样就失去了 MoE 的意义。

如果：

\[
8
\]

个 Expert 全部执行：

\[
y
=
\sum_{i=1}^{8}
g_iE_i(x)
\]

虽然数学没问题，但计算量会近似变成：

```text
8 个 FFN 全算
```

就失去了：

\[
\boxed{\text{Sparse Activation}}
\]

这段代码通过：

```python
mask
```

只找到真正被使用的 Expert。

再通过：

```python
if mask.any():
```

确保：

\[
\boxed{\text{没人选择的 Expert 根本不执行}}
\]

---

<a id="origin-13489"></a>
## 250. `index_add_` 为什么可以看成 MoE 汇流器？

可以把整个 MoE 想象成：

```text
                    → Expert 0 ─┐
                    → Expert 1 ─┤
Token → Router →    → Expert 2 ─┼→ 汇总
                    → Expert 3 ─┘
```

而：

```python
index_add_
```

就是最后这个：

\[
\boxed{\text{汇总}}
\]

它干的事情是：

```text
Expert 输出先乘自己的 Gate Weight

然后按照原 Token 编号

加回对应位置
```

因此：

\[
\boxed{
index\_add_
=
MoE 中把“分流”后的结果重新“汇流”
}
\]

这个理解非常重要。

---

<a id="origin-13536"></a>
## 251. `mask → token_idx → expert → index_add_` 四步一定要连起来理解

代码：

```python
mask = (
    topk_idx == i
)
```

回答：

> 哪些 Token 选择了当前 Expert？

---

```python
token_idx = (
    mask
    .any(-1)
    .nonzero()
    .flatten()
)
```

回答：

> 这些 Token 原来的编号是什么？

---

```python
expert(
    x_flat[token_idx]
)
```

完成：

> 当前 Expert 批量处理自己的 Token。

---

```python
y.index_add_(
    0,
    token_idx,
    expert_output * weight
)
```

完成：

> 把 Expert 的加权结果加回这些 Token 原来的位置。

所以完整逻辑：

```text
找 Token
↓
取 Token
↓
Expert 计算
↓
乘 Gate Weight
↓
加回原 Token
```

---

<a id="origin-13607"></a>
## 252. MoE 完整数据流图

```text
x: [B,T,H]
      │
      ▼
reshape
      │
      ▼
x_flat: [N,H]
      │
      ▼
┌─────────────┐
│   Router    │
│ H → E       │
└─────────────┘
      │
      ▼
scores: [N,E]
      │
      ▼
    Top-k
      │
 ┌────┴─────┐
 ▼          ▼
idx        weight
[N,K]      [N,K]
 │
 │
 ├─────────────────────────┐
 │                         │
 ▼                         ▼
找出 E0 的 Token        找出 E1 的 Token
 │                         │
 ▼                         ▼
Expert 0 FFN            Expert 1 FFN
 │                         │
 ▼                         ▼
× weight                × weight
 │                         │
 └─────────┬───────────────┘
           ▼
       index_add_
           │
           ▼
       y: [N,H]
           │
           ▼
       reshape
           │
           ▼
       [B,T,H]
```

训练时额外：

```text
topk_idx
   │
   ▼
one_hot
   │
   ▼
实际 Expert load
   │
   ├───────────────┐
   │               │
scores             │
   │               │
mean               │
   │               │
   ▼               │
Router 平均概率    │
   │               │
   └──────┬────────┘
          ▼
      Aux Loss
          │
          ▼
   防止 Expert Collapse
```

---

<a id="origin-13691"></a>
## 253. 最后把整段代码压缩成人话

这段 `MOEFeedForward` 实际上只做了 7 件事：

```text
1. 把所有 Token 展平。

2. Router 给每个 Token 对所有 Expert 打分。

3. 每个 Token 只选择 Top-k 个 Expert。

4. 按 Expert 对 Token 重新分组。

5. 每个 Expert 只处理属于自己的 Token。

6. Expert 输出乘 Gate Weight，
   再用 index_add_ 加回原 Token。

7. 训练时额外计算负载均衡 Aux Loss。
```

---

<a id="origin-13714"></a>
## 254. 一句话总结这段源码

\[
\boxed{
\texttt{MOEFeedForward}
\text{ 做的就是：
先用 Router 把 Token 分流到少数 Expert，
每个 Expert 独立做 FFN，
再按照 Gate Weight 用 index\_add\_ 把结果汇流回来。}
}
\]

而训练阶段再通过：

\[
\boxed{
\text{实际 Expert 负载}
\times
\text{Router 平均偏好}
}
\]

构造辅助损失，避免：

\[
\boxed{\text{所有 Token 都挤到少数 Expert}}
\]

因此整个 MoE 可以最终概括成：

```text
Router
  ↓
Top-k
  ↓
Token 分流
  ↓
Expert FFN
  ↓
Gate Weight
  ↓
index_add_ 汇流
  ↓
MoE Output

同时：

Routing Load
+
Router Probability
↓
Aux Loss
↓
Load Balance
```

这就是这段代码从头到尾真正做的事情。
