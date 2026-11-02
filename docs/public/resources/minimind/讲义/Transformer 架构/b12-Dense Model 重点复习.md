# Dense Model 重点复习


> 本讲义只讲需要重点复习、容易混淆的部分，不从头介绍 Dense Transformer：
>
> 1. Mixed Precision：中间 FP16 梯度、最终 FP32 grad 与 Unscale  
> 2. Gradient Accumulation：为什么 32 × 8 等价于 Batch 256  
> 3. KV Cache：为什么每轮只算最后一行，为什么只缓存 K/V  
> 4. MHA / MQA / GQA：区别、KV Cache 压缩与 Repeat  
> 5. RoPE / YaRN：绝对位置、相对位置、高频/低频与“重要性是学出来的”  
> 6. RMSNorm vs Gradient Clipping  
> 7. ReLU vs SiLU，以及 Gated FFN 的意义与实现  

---

<a id="origin-15"></a>
## 1. Mixed Precision：为什么要 Scale？Unscale 和 FP16 / FP32 到底是什么关系？

<a id="origin-17"></a>
### 1.1 先抓住核心

混合精度训练时，可以把过程理解成：

```text
Forward / Backward 中大量矩阵运算
        ↓
使用 FP16 / BF16
        ↓
中间很多局部梯度计算也处在低精度计算路径中
        ↓
最终梯度累积到模型参数的 .grad
        ↓
通常以 FP32 保存
        ↓
Unscale
        ↓
Optimizer Step
```

也就是说：

> **虽然最后用于参数更新的梯度通常以 FP32 保存，但在它形成之前，大量中间反向传播计算已经通过 FP16/BF16 完成。**

真正危险的地方就在这里：

> **如果某个中间梯度在 FP16 计算阶段已经因为太小而变成了 0，那么最后即使把结果放到 FP32 里，也救不回来了。**

因此才需要：

```text
先 Scale
再 Backward
最后 Unscale
```

---

<a id="origin-55"></a>
### 1.2 反向传播里到底有哪些“中间梯度变量”？

假设有一条很简单的网络：

\[
x
\overset{W_1}{\longrightarrow}
a
\overset{\mathrm{SiLU}}{\longrightarrow}
h
\overset{W_2}{\longrightarrow}
z
\longrightarrow
L
\]

其中：

\[
a=xW_1
\]

\[
h=\operatorname{SiLU}(a)
\]

\[
z=hW_2
\]

反向传播时，可以定义：

\[
\bar z
=
\frac{\partial L}{\partial z}
\]

\[
\bar h
=
\frac{\partial L}{\partial h}
\]

\[
\bar a
=
\frac{\partial L}{\partial a}
\]

这些就是反向传播中的中间梯度。

具体有：

\[
\bar h
=
\bar z W_2^T
\]

再因为：

\[
h=\operatorname{SiLU}(a)
\]

所以：

\[
\bar a
=
\bar h
\odot
\operatorname{SiLU}'(a)
\]

最后：

\[
\frac{\partial L}{\partial W_1}
=
x^T\bar a
\]

因此真正落到 `W1.grad` 里的，是：

\[
\frac{\partial L}{\partial W_1}
\]

但在它出现之前，已经经过了：

\[
\bar z,\bar h,\bar a
\]

这一整串中间梯度。

---

<a id="origin-155"></a>
### 1.3 为什么“最后是 FP32”仍然不够？

假设：

\[
\bar z
=
2\times10^{-8}
\]

也就是：

```text
0.00000002
```

如果这个中间梯度在 FP16 路径中计算，它可能直接下溢：

\[
2\times10^{-8}
\overset{\text{FP16}}{\longrightarrow}
0
\]

于是：

\[
\bar z=0
\]

接下来：

\[
\bar h
=
\bar zW_2^T
=
0
\]

再：

\[
\bar a
=
\bar h
\odot
\operatorname{SiLU}'(a)
=
0
\]

最终：

\[
\frac{\partial L}{\partial W_1}
=
x^T\bar a
=
0
\]

即使最后保存成：

```text
W1.grad = FP32(0)
```

它仍然只是：

```text
0
```

因为信息已经在前面的低精度反向过程中丢失。

---

<a id="origin-233"></a>
### 1.4 一张图看明白

没有 Scale：

```text
真实梯度信息

∂L/∂z = 2×10^-8
        │
        │ FP16 中间反传
        ▼
        0
        │
        ▼
∂L/∂h = 0
        │
        ▼
∂L/∂a = 0
        │
        ▼
∂L/∂W1 = 0
        │
        ▼
最后存进 FP32 grad

FP32(0)

信息已经没了
```

所以：

> **最后的 FP32 只能保证“最后保存”精度高，无法恢复前面 FP16 阶段已经丢掉的梯度。**

---

<a id="origin-269"></a>
### 1.5 Scale 真正保护的是整条反向链

假设：

\[
S=65536
\]

先：

\[
L_{\text{scaled}}
=
SL
\]

那么反向链上的梯度都会一起乘：

\[
S
\]

也就是：

\[
\bar z_{\text{scaled}}
=
S\bar z
\]

\[
\bar h_{\text{scaled}}
=
S\bar h
\]

\[
\bar a_{\text{scaled}}
=
S\bar a
\]

最终：

\[
\frac{\partial L_{\text{scaled}}}{\partial W_1}
=
S
\frac{\partial L}{\partial W_1}
\]

---

<a id="origin-322"></a>
### 1.6 用刚才那个数继续算

原本：

\[
\bar z
=
2\times10^{-8}
\]

Scale 后：

\[
\bar z_{\text{scaled}}
=
65536\times2\times10^{-8}
\approx0.00131
\]

于是：

```text
原来：
2×10^-8
↓
FP16
↓
可能直接变0
```

现在：

```text
0.00131
↓
FP16
↓
可以正常表示
```

假设：

\[
W_2=0.1
\]

则：

\[
\bar h_{\text{scaled}}
=
0.00131\times0.1
=
1.31\times10^{-4}
\]

再假设：

\[
\operatorname{SiLU}'(a)=0.5
\]

则：

\[
\bar a_{\text{scaled}}
=
1.31\times10^{-4}\times0.5
=
6.55\times10^{-5}
\]

如果：

\[
x=2
\]

那么：

\[
\frac{\partial L_{\text{scaled}}}{\partial W_1}
=
2\times6.55\times10^{-5}
=
1.31\times10^{-4}
\]

这条反向链中的数值都比原来安全得多。

---

<a id="origin-414"></a>
### 1.7 最后的 FP32 grad 中装的是什么？

此时：

```text
W1.grad
```

通常已经是 FP32。

但里面装的是：

\[
\frac{\partial L_{\text{scaled}}}{\partial W_1}
\]

也就是：

\[
S
\frac{\partial L}{\partial W_1}
\]

因此：

> **虽然类型已经是 FP32，但数值仍然是放大过的。**

所以还不能直接：

```python
optimizer.step()
```

---

<a id="origin-449"></a>
### 1.8 Unscale 真正做什么？

Unscale：

\[
\frac{\partial L}{\partial W_1}
=
\frac{
\partial L_{\text{scaled}}/\partial W_1
}{
S
}
\]

即：

```text
最终 FP32 grad 中存的是：
Sg

Unscale 后：
Sg / S = g
```

所以必须把两件事分开：

```text
FP16 → FP32
```

是：

```text
数据类型 / 存储精度
```

而：

```text
Scale → Unscale
```

是：

```text
数值大小
```

---

<a id="origin-499"></a>
### 1.9 混合精度训练流程图

```text
原始 Loss L
    │
    │ × 65536
    ▼
Scaled Loss
    │
    ▼
Backward
    │
    ├───────────────┐
    │               │
    ▼               ▼
中间梯度1        中间梯度2
FP16/BF16        FP16/BF16
    │               │
    └──────┬────────┘
           ▼
       更多中间梯度
       FP16/BF16
           │
           ▼
   最终参数 Gradient
      通常存 FP32
           │
           │ 此时仍是 Sg
           ▼
        Unscale
           │
           │ ÷ S
           ▼
       真实梯度 g
           │
           ▼
   Gradient Clipping
           │
           ▼
     Optimizer Step
```

---

<a id="origin-543"></a>
### 1.10 一句话结论

> **Scale 的真正作用不是保护最后那个 FP32 grad，而是保护“通往这个 FP32 grad 的整条低精度反向传播路径”；Unscale 则是在最终 FP32 grad 安全形成以后，把它从 \(Sg\) 恢复成真实的 \(g\)。**

---

<a id="origin-549"></a>
## 2. Gradient Accumulation：为什么 32 × 8 等价于 Batch 256？

假设：

```text
micro batch = 32
accumulation steps = 8
```

那么：

\[
32\times8=256
\]

第一轮 32 个样本：

\[
l_1,\dots,l_{32}
\]

先求平均：

\[
L_1
=
\frac{l_1+\cdots+l_{32}}{32}
\]

因为还要累计 8 次，所以再除：

\[
8
\]

得到：

\[
L_1'
=
\frac{l_1+\cdots+l_{32}}{256}
\]

**反向传播：**

\[
g_1
=
\nabla_\theta L_1'
\]

**但不更新参数。**

第二轮：

\[
L_2'
=
\frac{l_{33}+\cdots+l_{64}}{256}
\]

再次 backward。

PyTorch 会把梯度累加：

\[
g
=
g_1+g_2
\]

因此此时：

\[
g
=
\nabla_\theta
\frac{
l_1+\cdots+l_{64}
}{256}
\]

连续累计 8 次：

\[
g
=
\nabla_\theta
\frac{
l_1+\cdots+l_{256}
}{256}
\]

这正是 Batch Size 256 的平均梯度。

---

<a id="origin-646"></a>
### 2.1 为什么中间不能更新参数？

真正 Batch 256 时：

```text
256 个样本
全部基于同一份参数 W
```

如果第 1 个 micro batch 后就：

```python
optimizer.step()
```

参数变成：

\[
W_1
\]

那第 2 个 micro batch 的梯度已经是在：

\[
W_1
\]

上计算，而不是原来的：

\[
W_0
\]

于是就不再等价于一个大 Batch。

---

<a id="origin-683"></a>
### 2.2 为什么每次还要除以 8？

如果不除，8 次累加后：

\[
g
=
\nabla(L_1+\cdots+L_8)
\]

会相当于：

```text
真正 Batch 256 平均梯度的 8 倍
```

所以通常：

```python
loss = loss / accumulation_steps
```

---

<a id="origin-707"></a>
### 2.3 一句话

> **梯度累计的本质就是：多个 micro batch 先只累计梯度，中间不更新参数，累计结束后才用一次合并后的平均梯度更新参数。**

---

<a id="origin-713"></a>
## 3. KV Cache：为什么每轮只需要新增的一行？

假设第一轮输入：

```text
I love
```

Attention Score：

\[
\begin{bmatrix}
Q_IK_I^T & -\infty
\\
Q_{\text{love}}K_I^T &
Q_{\text{love}}K_{\text{love}}^T
\end{bmatrix}
\]

下一轮输入变成：

```text
I love AI
```

完整 Attention Score：

\[
\begin{bmatrix}
Q_IK_I^T
&
-\infty
&
-\infty
\\
Q_{\text{love}}K_I^T
&
Q_{\text{love}}K_{\text{love}}^T
&
-\infty
\\
Q_{\text{AI}}K_I^T
&
Q_{\text{AI}}K_{\text{love}}^T
&
Q_{\text{AI}}K_{\text{AI}}^T
\end{bmatrix}
\]

前两行上一轮已经计算过。

这一轮真正新增的是：

\[
[
Q_{\text{AI}}K_I^T,\,
Q_{\text{AI}}K_{\text{love}}^T,\,
Q_{\text{AI}}K_{\text{AI}}^T
]
\]

所以：

> **这一轮真正需要计算的只是最后一行。**

---

<a id="origin-780"></a>
### 3.1 为什么历史 K 必须缓存？

当前 Query：

\[
Q_{\text{AI}}
\]

仍然需要和：

\[
K_I,\quad
K_{\text{love}},\quad
K_{\text{AI}}
\]

做匹配。

所以过去 token 的：

```text
K_I
K_love
```

必须保留。

因为：

\[
K=XW_K
\]

历史 hidden state 不变、参数 \(W_K\) 不变，因此历史 K 也不变。

**没必要重复算，毕竟算起来很麻烦。**

---

<a id="origin-819"></a>
### 3.2 为什么 V 也必须缓存？

Softmax 以后：

\[
\alpha_I,\alpha_{\text{love}},\alpha_{\text{AI}}
\]

最终：

\[
O_{\text{AI}}
=
\alpha_I V_I
+
\alpha_{\text{love}}V_{\text{love}}
+
\alpha_{\text{AI}}V_{\text{AI}}
\]

例如：

\[
\alpha_I=0.1,\quad
\alpha_{\text{love}}=0.7,\quad
\alpha_{\text{AI}}=0.2
\]

那么：

\[
O_{\text{AI}}
=
0.1V_I+0.7V_{\text{love}}+0.2V_{\text{AI}}
\]

所以历史 V 也必须保留。

可以理解为：

```text
K：
决定“该关注谁、关注多少”

V：
提供“真正取回来的内容”
```

---

<a id="origin-869"></a>
### 3.3 为什么历史 Q 不需要缓存？

历史：

\[
Q_I
\]

只负责当时计算：

```text
I 应该关注谁
```

历史：

\[
Q_{\text{love}}
\]

只负责当时计算：

```text
love 应该关注谁
```

这一轮新增的信息只有：

```text
AI 应该关注谁？
```

所以只需要：

\[
Q_{\text{AI}}
\]

不需要历史 Q。

---

<a id="origin-911"></a>
### 3.4 “前几行没用了”应该怎么理解？

不是：

```text
历史 token 的信息没用了
```

而是：

> **历史 token 作为 Query 时计算出来的那些 Attention 行，不需要重新计算。**

当前 token 仍然要访问：

```text
历史 K
历史 V
```

所以：

```text
历史 Attention 行：
不用重算

历史 K/V：
必须保留
```

---

<a id="origin-942"></a>
### 3.5 KV Cache 大小

近似：

\[
\text{KV Cache}
\propto
2
\times
L
\times
N_{\text{layer}}
\times
N_{\text{KVHead}}
\times
d_{\text{head}}
\]

其中：

```text
2：
K + V

L：
序列长度

N_layer：
层数

N_KVHead：
KV Head 数

d_head：
每个 Head 的维度
```

---

<a id="origin-981"></a>
### 3.6 一句话

> **KV Cache 的本质不是缓存整个 Attention，而是因为每轮只新增最后一行，而这最后一行要继续访问历史 K 和 V，所以把历史 K/V 存起来即可。**

---

<a id="origin-987"></a>
## 4. 单头 Attention、MHA、MQA、GQA：区别和 KV Cache

假设：

```text
hidden size = 4096
num_heads = 32
```

那么：

\[
d_{\text{head}}
=
\frac{4096}{32}
=
128
\]

---

<a id="origin-1008"></a>
### 4.1 单头 Attention

只有：

```text
1 个 Q
1 个 K
1 个 V
```

只有一个注意力空间。

---

<a id="origin-1022"></a>
### 4.2 MHA

```text
32 个 Q Head
32 个 K Head
32 个 V Head
```

即：

\[
N_Q=32
\]

\[
N_{KV}=32
\]

每个 Query Head 都有自己的 K/V：

```text
Q1 ↔ K1/V1
Q2 ↔ K2/V2
...
Q32 ↔ K32/V32
```

---

<a id="origin-1051"></a>
### 4.3 MQA

仍然有：

```text
32 个 Q Head
```

但只保留：

```text
1 个 K Head
1 个 V Head
```

即：

\[
N_Q=32
\]

\[
N_{KV}=1
\]

所有 Query Head 共用同一套 K/V：

```text
Q1 ┐
Q2 │
Q3 ├── K1/V1
...│
Q32┘
```

---

<a id="origin-1088"></a>
### 4.4 GQA

例如：

```text
32 个 Q Head
8 个 KV Head
```

那么：

\[
32/8=4
\]

也就是：

```text
Q1-Q4   → K1/V1
Q5-Q8   → K2/V2
...
Q29-Q32 → K8/V8
```

即每 4 个 Query Head 共用一套 K/V。

---

<a id="origin-1116"></a>
### 4.5 为什么 GQA 可以减少 KV Cache？

因为：

\[
\text{KV Cache}
\propto
N_{\text{KVHead}}
\]

MHA：

\[
N_{\text{KVHead}}=32
\]

GQA：

\[
N_{\text{KVHead}}=8
\]

所以：

\[
\frac{8}{32}
=
\frac14
\]

即：

> **在其他条件相同的情况下，KV Cache 大约只有 MHA 的 1/4。**

---

<a id="origin-1152"></a>
### 4.6 Repeat 到底干什么？

假设：

```text
Q Head = 8
KV Head = 2
```

那么每 4 个 Q 共用一个 KV。

原始：

```text
K1
K2
```

在 Attention 计算时，逻辑上展开成：

```text
K1 K1 K1 K1 K2 K2 K2 K2
```

V 同理。

这是为了让：

```text
KV 的 Head 维度
```

和：

```text
Q 的 Head 维度
```

对齐。

---

<a id="origin-1194"></a>
### 4.7 Repeat 不是生成新的独立参数

它不是：

```text
复制出8套新的K/V参数
```

而是：

> **同一个底层 K/V 被多个 Query Head 共同引用。**

例如：

```text
Q1 ─┐
Q2 ─┼── K1
Q3 ─┤
Q4 ─┘
```

反向传播时：

\[
g_{K_1}
=
g_1+g_2+g_3+g_4
\]

所以可以理解为：

> **一个 K/V 矩阵同时接到了多个 Query 分支上。**

---

<a id="origin-1229"></a>
### 4.8 四者一句话总结

```text
单头：
1Q + 1KV

MHA：
多个Q，每个Q有自己的KV

MQA：
多个Q，全部共用1套KV

GQA：
多个Q，按组共享KV
```

---

<a id="origin-1247"></a>
## 5. 绝对位置编码 vs RoPE：为什么 RoPE 天然带相对位置？

假设：

```text
A 在位置1
B 在位置5
```

绝对位置编码告诉模型：

```text
A：位置1
B：位置5
```

**模型需要自己通过训练逐渐学会：**

\[
5-1=4
\]

也就是：

```text
A 和 B 相距4
```

---

<a id="origin-1277"></a>
### 5.1 RoPE

位置 \(m\) 的 Query：

\[
Q_m'
=
R(m\theta)Q_m
\]

位置 \(n\) 的 Key：

\[
K_n'
=
R(n\theta)K_n
\]

做 Attention：

\[
Q_m'^T K_n'
\]

代入：

\[
Q_m^T
R(m\theta)^T
R(n\theta)
K_n
\]

因为：

\[
R(m\theta)^T
=
R(-m\theta)
\]

所以：

\[
Q_m'^T K_n'
=
Q_m^T
R((n-m)\theta)
K_n
\]

这里直接出现：

\[
n-m
\]

也就是：

```text
相对位置
```

因此：

> **绝对位置编码给模型“1 和 5”；RoPE 让 QK 内积天然出现“5−1=4”这种相对位置结构。**

---

<a id="origin-1346"></a>
## 6. RoPE / YaRN：高频和低频到底哪个重要？

<a id="origin-1348"></a>
### 6.1 最关键的一句话

> **高频不是天然比低频重要，低频也不是天然比高频重要。**

真正的情况是：

> **RoPE 给模型同时提供很多不同频率的位置通道；某个语义关系到底更依赖高频还是低频，是模型在训练过程中学出来的。**

---

<a id="origin-1358"></a>
### 6.2 一个 token 为什么同时有很多频率？

RoPE 会把 hidden dimension 两两配对。

例如：

```text
第1、2维：
频率 θ1

第3、4维：
频率 θ2

第5、6维：
频率 θ3

...

最后一对：
频率 θm
```

其中：

```text
有些维度转得快
→ 高频

有些维度转得慢
→ 低频
```

所以同一个 token 同时拥有：

```text
高频位置表示
+
中频位置表示
+
低频位置表示
```

---

<a id="origin-1402"></a>
### 6.3 从公式看

假设只看两个频率：

```text
高频：
θ_H

低频：
θ_L
```

相对位置：

\[
\Delta=n-m
\]

高频贡献：

\[
S^{(H)}
=
Q_H^T
R(\Delta\theta_H)
K_H
\]

低频贡献：

\[
S^{(L)}
=
Q_L^T
R(\Delta\theta_L)
K_L
\]

总 Attention Score 可以简化成：

\[
S
=
S^{(H)}+S^{(L)}
\]

真实模型则更像：

\[
S
=
\sum_i
Q_i^T
R(\Delta\theta_i)
K_i
\]

即很多频率一起参与。

---

<a id="origin-1463"></a>
### 6.4 到底高频贡献大还是低频贡献大？

关键取决于：

\[
Q_i,K_i
\]

而：

\[
Q=XW_Q
\]

\[
K=XW_K
\]

所以：

\[
Q_H,K_H,Q_L,K_L
\]

本质上都是：

> **训练出来的。**

训练过程可以理解成：

```text
某种语义关系
↓
某些频率帮助预测得更准
↓
Loss 更低
↓
反向传播更新 WQ、WK
↓
模型逐渐学会：
这种关系更依赖哪些频率
```

---

<a id="origin-1508"></a>
### 6.5 案例1：数据库 操作系统

假设模型看到大量语料：

```text
数据库操作系统
```

当：

```text
数据库
操作系统
```

距离为：

\[
1
\]

时，它们可能形成紧密术语。

但如果相隔：

\[
50
\]

个 token，它们可能只是同一篇文章中的两个相关概念。

高频对：

```text
距离1
距离2
距离3
```

变化非常敏感。

因此如果模型发现：

```text
利用高频维度
能更好区分
“数据库操作系统”
和
“数据库……操作系统”
```

那么训练会推动：

\[
W_Q,W_K
\]

让相关高频通道在这种语义关系中贡献更大。

所以：

> **不是人工规定“短语必须用高频”，而是模型训练后发现高频对这类任务更有用。**

---

<a id="origin-1573"></a>
### 6.6 案例2：长距离指代

例如：

```text
张三提出了一个方案。
……
中间隔了100个token
……
他最终撤回了它。
```

这里：

```text
“他”
```

可能需要关联：

```text
“张三”
```

低频转得更慢，更适合提供平滑的长距离位置信息。

如果训练发现：

```text
某些低频维度
能更好完成长距离关联
```

那么梯度会推动：

\[
W_Q,W_K
\]

让这些低频通道贡献更大。

因此：

> **长距离关系中低频往往更有帮助，但到底使用多少，仍然是训练学出来的。**

---

<a id="origin-1620"></a>
### 6.7 高频/低频不是固定语义标签

不能写成：

```text
高频 = 短语
低频 = 指代
```

正确理解是：

```text
高频：
提供对短距离变化更敏感的位置基函数

低频：
提供对长距离变化更平滑的位置基函数
```

然后模型自己学习：

```text
当前语义关系
应该组合哪些频率
```

---

<a id="origin-1648"></a>
### 6.8 “频率工具箱”的理解

RoPE 相当于给模型：

```text
高频尺子
中频尺子
低频尺子
```

模型训练后自己学会：

```text
这个关系：
高频更有用

那个关系：
低频更有用

另一种关系：
高频 + 低频一起用
```

所以最核心的一句话是：

> **RoPE 提供频率，模型学习频率的重要性。**

---

<a id="origin-1677"></a>
## 7. 为什么长上下文需要 YaRN？

假设训练时：

```text
最大长度 = 4K
```

推理时突然变成：

```text
32K
```

那么某些 RoPE 频率对应的旋转角度会进入：

```text
训练阶段没有充分见过的范围
```

例如可以用下面的类比理解：

```text
训练时某个频率只常见：
0°~90°

推理时：
突然出现180°
```

问题不是：

```text
180°不能计算
```

而是：

> **模型没怎么训练过这种相位关系。**

---

<a id="origin-1719"></a>
### 7.1 为什么不能所有频率一起除以 8？

假设：

\[
4K\rightarrow32K
\]

最粗暴的办法是：

\[
m'=\frac{m}{8}
\]

这样远距离确实被压回来了。

但是原来：

```text
距离1
```

也会变成：

\[
0.125
\]

那模型原本已经学好的：

```text
距离1和距离2的精细区别
```

也会被破坏。

---

<a id="origin-1757"></a>
### 7.2 YaRN 的真正直觉

可以把 RoPE 想成很多不同转速的表盘：

```text
快表盘：
高频

慢表盘：
低频
```

训练时，模型已经自己学会：

```text
哪些语义关系
更依赖哪些表盘
```

长上下文推理时，某些表盘进入了训练时没见过的区域。

YaRN 做的是：

> **对不同频率采用不同程度的缩放/插值，让长距离位置进入更可用的范围，同时尽量保留模型原来已经学好的频率使用方式。**

所以不应该说：

```text
YaRN 就是把低频压缩
```

更准确的是：

> **YaRN 对不同 RoPE 频率区间做差异化处理；至于哪些频率在具体语义关系中重要，仍然是模型训练出来的。**

---

<a id="origin-1794"></a>
## 8. RMSNorm vs Gradient Clipping

<a id="origin-1796"></a>
### 8.1 RMSNorm：控制 hidden state 的整体尺度

例如：

\[
x=[1,2,3]
\]

RMS：

\[
\sqrt{
\frac{1^2+2^2+3^2}{3}
}
\approx2.16
\]

归一化后：

\[
x'
\approx
[0.46,0.93,1.39]
\]

如果：

\[
x=[10,20,30]
\]

RMS：

\[
\approx21.6
\]

归一化后仍约：

\[
[0.46,0.93,1.39]
\]

如果：

\[
x=[1000,2000,3000]
\]

仍然会被拉回类似：

\[
[0.46,0.93,1.39]
\]

所以：

> **RMSNorm 负责稳定 hidden state 的整体尺度，而不是把每个值都变成 1。**

标准形式：

\[
y
=
\gamma
\odot
\frac{x}{
\sqrt{\operatorname{mean}(x^2)+\epsilon}
}
\]

其中：

\[
\gamma
\]

是可学习参数。

---

<a id="origin-1877"></a>
### 8.2 Gradient Clipping：限制梯度最大长度

假设梯度：

\[
g=[3,4]
\]

那么：

\[
\|g\|_2
=
5
\]

如果：

\[
\text{max norm}=1
\]

则：

\[
g'
=
[3,4]\times\frac15
=
[0.6,0.8]
\]

但如果：

\[
\|g\|=0.5
\]

小于阈值：

```text
就不压缩
```

所以：

```text
RMSNorm：
每层稳定 hidden state

Gradient Clipping：
梯度太大时才压缩
```

---

<a id="origin-1933"></a>
### 8.3 两者区别

| 对比 | RMSNorm | Gradient Clipping |
|---|---|---|
| 作用对象 | hidden state / activation | gradient |
| 所处阶段 | Forward | Backward 后 |
| 是否模型结构 | 是 | 否 |
| 是否每次执行 | 通常每层都有 | 超阈值才真正缩放 |
| 目的 | 稳定激活尺度 | 防止梯度爆炸 |

一句话：

> **RMSNorm 管前向 hidden state 的尺度，Gradient Clipping 管反向 gradient 的最大长度。**

---

<a id="origin-1949"></a>
## 9. ReLU、SiLU 与 Gated FFN

<a id="origin-1951"></a>
### 9.1 ReLU

\[
\operatorname{ReLU}(x)
=
\max(0,x)
\]

例如：

```text
[-2,-1,0,1,2]
↓
[0,0,0,1,2]
```

负数直接全部砍成 0。

---

<a id="origin-1971"></a>
### 9.2 SiLU

\[
\operatorname{SiLU}(x)
=
x\sigma(x)
\]

其中：

\[
\sigma(x)
=
\frac{1}{1+e^{-x}}
\]

例如：

\[
x=-2
\]

\[
\sigma(-2)\approx0.119
\]

所以：

\[
\operatorname{SiLU}(-2)
\approx-0.238
\]

而 ReLU：

\[
\operatorname{ReLU}(-2)=0
\]

因此：

```text
ReLU：
硬开关

SiLU：
平滑开关
```

SiLU 对负值不会全部一刀切掉。

---

<a id="origin-2024"></a>
### 9.3 普通 FFN

可以写成：

\[
h
=
\phi(xW_1)
\]

再：

\[
y
=
hW_2
\]

典型流程：

```text
hidden size
↓
升维
↓
非线性
↓
降维
↓
hidden size
```

---

<a id="origin-2058"></a>
### 9.4 Gated FFN

现代大模型常见：

\[
a=xW_{\text{gate}}
\]

\[
b=xW_{\text{up}}
\]

然后：

\[
h
=
\operatorname{SiLU}(a)\odot b
\]

最后：

\[
y
=
hW_{\text{down}}
\]

即：

\[
\boxed{
y
=
[
\operatorname{SiLU}(xW_{\text{gate}})
\odot
(xW_{\text{up}})
]
W_{\text{down}}
}
\]

---

<a id="origin-2103"></a>
### 9.5 Gate 的意义

假设：

```text
up_proj 输出：
[10, 3, -4]
```

gate 经过 SiLU 后：

```text
[0.9, 0.1, 0.7]
```

逐元素相乘：

```text
[10, 3, -4]
⊙
[0.9, 0.1, 0.7]
=
[9, 0.3, -2.8]
```

含义：

```text
第1维：
大量放行

第2维：
强烈抑制

第3维：
部分放行
```

所以：

```text
up_proj：
产生候选内容

gate_proj：
决定候选内容通过多少
```

---

<a id="origin-2153"></a>
### 9.6 为什么 Gate 比只有 SiLU 更灵活？

普通：

\[
\operatorname{SiLU}(xW)
\]

只有一条支路。

Gated FFN：

```text
一条支路：
产生内容

另一条支路：
控制内容
```

模型可以表达：

```text
“我有这个特征，
但当前上下文只让它通过10%。”
```

因此动态选择能力更强。

---

<a id="origin-2184"></a>
## 10. 最终复习总表

| 重点 | 最核心结论 |
|---|---|
| Scale / Unscale | Scale 保护整条低精度反向链；最终 FP32 grad 里仍是 \(Sg\)，Unscale 再除回 \(g\) |
| Gradient Accumulation | 多个 micro batch 中间不更新参数，梯度累加后一次性更新 |
| KV Cache | 每轮只需要新增 Attention 最后一行，因此缓存历史 K/V，不缓存历史 Q |
| MHA | 每个 Query Head 都有自己的 KV Head |
| MQA | 所有 Query Head 共用一套 KV |
| GQA | 一组 Query Head 共用一套 KV，KV Cache 随 KV Head 数减少 |
| Repeat KV | 让少量 KV Head 在计算时对齐更多 Query Head，梯度汇总回原始 KV |
| RoPE | \(QK^T\) 中天然出现 \(n-m\) 的相对位置结构 |
| 高频 / 低频 | 只是不同位置频率通道，谁重要由训练决定 |
| YaRN | 对不同频率做差异化缩放/插值，尽量保留模型已学到的频率使用方式 |
| RMSNorm | 稳定 hidden state 的整体尺度 |
| Gradient Clipping | 梯度过大时限制 gradient norm |
| ReLU | 硬截断非线性 |
| SiLU | 平滑非线性，负区间仍保留信息 |
| Gated FFN | 一条支路产生内容，一条支路控制内容放行多少 |

---

<a id="origin-2206"></a>
## 11. 最后几句话快速记忆

<a id="origin-2208"></a>
### 11.1 Mixed Precision

> **中间大量反向梯度计算可能在 FP16/BF16 中进行，最终参数 grad 通常是 FP32；Scale 是为了防止前面低精度链条里小梯度提前变 0，Unscale 是最后把 \(Sg\) 还原成 \(g\)。**

<a id="origin-2212"></a>
#### 11.1.1 Gradient Accumulation

> **32 个样本算一次梯度，连续累计 8 次且中间不更新参数，就可以形成相当于 256 个样本的一次平均梯度。**

<a id="origin-2216"></a>
#### 11.1.2 KV Cache

> **当前 token 只需要自己的 Q，但要访问所有历史 K 和 V，所以缓存 K/V，不缓存历史 Q。**

<a id="origin-2220"></a>
#### 11.1.3 GQA

> **Query Head 数可以保持很多，而 KV Head 数减少，因此既保留多查询视角，又能显著压缩 KV Cache。**

<a id="origin-2224"></a>
#### 11.1.4 RoPE / YaRN

> **RoPE 同时提供高频、中频、低频位置通道；到底哪个频率在当前语义关系中更重要，是通过 \(W_Q,W_K\) 训练学出来的。YaRN 只负责在长上下文下尽量保护这种已经学好的频率使用方式。**

<a id="origin-2228"></a>
#### 11.1.5 RMSNorm / Clip

> **RMSNorm 管 hidden state，Gradient Clipping 管 gradient。**

<a id="origin-2232"></a>
#### 11.1.6 SiLU / Gate

> **SiLU 是平滑非线性；Gate 让 FFN 不仅能产生信息，还能动态决定信息通过多少。**

---

<a id="origin-2238"></a>
## 12. RoPE 中 `freqs` 的原理与公式

代码：

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

其中真正核心的是：

```python
freqs = 1.0 / (
    rope_base ** (
        torch.arange(0, dim, 2).float() / dim
    )
)
```

它的作用是：

> 为 RoPE 的每一对二维向量分配一个不同的旋转频率。

---

<a id="origin-2269"></a>
## 13. RoPE 为什么需要 `freqs`

RoPE（Rotary Position Embedding）的核心思想是：

> 把向量的每两个维度看成一个二维平面，然后根据 token 的位置，对这个二维向量进行旋转。

例如一个 Query 向量：

```text
q = [q0, q1, q2, q3, q4, q5, ...]
```

RoPE 会把它两两分组：

```text
(q0, q1)
(q2, q3)
(q4, q5)
...
```

假设：

```text
dim = 8
```

那么：

```text
q = [q0, q1, q2, q3, q4, q5, q6, q7]
```

会变成 4 个二维向量：

```text
第 0 组：(q0, q1)
第 1 组：(q2, q3)
第 2 组：(q4, q5)
第 3 组：(q6, q7)
```

但是，这 4 组向量**不能全部按照完全相同的速度旋转**。

因此 RoPE 给不同的维度组分配不同的旋转频率：

```text
第 0 组：旋转得快
第 1 组：慢一点
第 2 组：更慢
第 3 组：最慢
```

这些旋转频率就是：

```python
freqs
```

---

<a id="origin-2330"></a>
## 14. RoPE 的频率公式

标准 RoPE 中，不同二维维度对应的频率可以写成：

\[
\boxed{
\theta_i
=
\frac{1}
{\text{base}^{\frac{2i}{d}}}
}
\]

其中：

- \(d\)：RoPE 作用的维度，也就是代码里的 `dim`
- \(i\)：第几个二维维度组
- `base`：RoPE 的基数，例如经典 Transformer 中常见 `10000`
- \(\theta_i\)：第 \(i\) 个二维维度的旋转频率

也可以写成：

\[
\theta_i
=
\text{base}^{-\frac{2i}{d}}
\]

因为：

\[
\frac{1}{a^x}=a^{-x}
\]

---

<a id="origin-2366"></a>
## 15. 为什么代码里是 `0, 2, 4, 6...`

代码：

```python
torch.arange(0, dim, 2)
```

假设：

```python
dim = 8
```

那么：

```python
torch.arange(0, 8, 2)
```

得到：

```text
[0, 2, 4, 6]
```

注意：

这里不是在说只处理：

```text
q0
q2
q4
q6
```

而是在表示四个二维组：

```text
0 → (q0, q1)

2 → (q2, q3)

4 → (q4, q5)

6 → (q6, q7)
```

因此：

```text
[0, 2, 4, 6]
```

本质上对应：

```text
4 个二维旋转平面
```

---

<a id="origin-2429"></a>
## 16. 从数学公式对应到代码

数学公式：

\[
\theta_i
=
\frac{1}
{\text{base}^{\frac{2i}{d}}}
\]

代码使用：

```python
torch.arange(0, dim, 2)
```

直接生成：

\[
0,2,4,6,\cdots
\]

所以代码中的：

```python
torch.arange(0, dim, 2) / dim
```

实际上就是：

\[
\frac{0}{d},
\frac{2}{d},
\frac{4}{d},
\frac{6}{d},
\cdots
\]

也就是公式中的：

\[
\frac{2i}{d}
\]

因此：

```python
rope_base ** (
    torch.arange(0, dim, 2).float() / dim
)
```

对应：

\[
\text{base}^{\frac{2i}{d}}
\]

再做：

```python
1.0 / (...)
```

最终就是：

\[
\boxed{
\theta_i
=
\frac{1}
{\text{base}^{\frac{2i}{d}}}
}
\]

---

<a id="origin-2507"></a>
## 17. 一个具体数值例子

假设：

```text
dim = 8
rope_base = 10000
```

首先：

```python
torch.arange(0, 8, 2)
```

得到：

```text
[0, 2, 4, 6]
```

除以：

```text
dim = 8
```

得到：

\[
\left[
\frac08,
\frac28,
\frac48,
\frac68
\right]
\]

也就是：

```text
[0, 0.25, 0.5, 0.75]
```

接下来计算：

\[
10000^{[0,\ 0.25,\ 0.5,\ 0.75]}
\]

分别为：

\[
10000^0=1
\]

\[
10000^{0.25}=10
\]

\[
10000^{0.5}=100
\]

\[
10000^{0.75}=1000
\]

所以得到：

```text
[1, 10, 100, 1000]
```

最后计算倒数：

\[
\frac{1}{[1,10,100,1000]}
\]

得到：

```text
freqs =
[1.0, 0.1, 0.01, 0.001]
```

也就是：

\[
\boxed{
\text{freqs}
=
[1,\ 0.1,\ 0.01,\ 0.001]
}
\]

---

<a id="origin-2606"></a>
## 18. 这些频率到底代表什么

现在四个二维组分别对应：

```text
(q0, q1) → freq = 1
(q2, q3) → freq = 0.1
(q4, q5) → freq = 0.01
(q6, q7) → freq = 0.001
```

这表示它们随着 token 位置增加，旋转的速度不同。

---

<a id="origin-2621"></a>
## 19. token 位置如何和 `freqs` 结合

假设 token 的位置为：

\[
m
\]

那么第 \(i\) 个二维向量的实际旋转角度是：

\[
\boxed{
\phi_{m,i}
=
m\theta_i
}
\]

也就是：

\[
\boxed{
\phi_{m,i}
=
m
\cdot
\frac{1}
{\text{base}^{2i/d}}
}
\]

代码中一般会看到类似：

```python
t = torch.arange(seq_len)
freqs = ...
freqs = torch.outer(t, freqs)
```

得到：

\[
m \times \theta_i
\]

---

例如：

```text
freqs = [1, 0.1, 0.01, 0.001]
```

对于位置：

```text
m = 3
```

旋转角度为：

\[
3\times[1,0.1,0.01,0.001]
\]

即：

```text
[3, 0.3, 0.03, 0.003]
```

也就是说，同一个 token 在不同维度上的旋转角度不同。

---

<a id="origin-2696"></a>
## 20. 最后如何旋转 Q 和 K

对于一个二维向量：

\[
\begin{bmatrix}
x_1\\
x_2
\end{bmatrix}
\]

旋转角度：

\[
\phi
\]

RoPE 使用标准二维旋转矩阵：

\[
\boxed{
R(\phi)
=
\begin{bmatrix}
\cos\phi & -\sin\phi\\
\sin\phi & \cos\phi
\end{bmatrix}
}
\]

所以：

\[
\begin{bmatrix}
x'_1\\
x'_2
\end{bmatrix}
=
\begin{bmatrix}
\cos\phi & -\sin\phi\\
\sin\phi & \cos\phi
\end{bmatrix}
\begin{bmatrix}
x_1\\
x_2
\end{bmatrix}
\]

展开：

\[
x'_1
=
x_1\cos\phi-x_2\sin\phi
\]

\[
x'_2
=
x_1\sin\phi+x_2\cos\phi
\]

其中：

\[
\phi=m\theta_i
\]

所以完整公式实际上是：

\[
\boxed{
R(m\theta_i)
}
\]

---

<a id="origin-2774"></a>
## 21. 高频和低频分别有什么作用

由于：

\[
\theta_i
=
\frac{1}{\text{base}^{2i/d}}
\]

随着 \(i\) 增大：

\[
\theta_i
\]

越来越小。

因此：

```text
前面的维度
↓
freq 大
↓
旋转速度快
↓
高频
```

而：

```text
后面的维度
↓
freq 小
↓
旋转速度慢
↓
低频
```

例如：

```text
freq = 1
```

位置从：

```text
1 → 2 → 3
```

角度：

```text
1 → 2 → 3 rad
```

变化很快。

而：

```text
freq = 0.001
```

位置：

```text
1 → 2 → 3
```

角度：

```text
0.001 → 0.002 → 0.003 rad
```

变化非常慢。

---

<a id="origin-2858"></a>
## 22. 为什么要同时有高频和低频

可以把它类比成钟表。

钟表有：

```text
秒针
分针
时针
```

它们旋转速度不同。

秒针：

```text
转得快
```

适合区分：

```text
很接近的位置
```

例如：

```text
第 10 个 token
第 11 个 token
```

而时针：

```text
转得慢
```

适合表示：

```text
更大的位置尺度
```

例如：

```text
第 1000 个 token
第 5000 个 token
```

RoPE 相当于同时拥有大量不同速度的“钟表指针”。

---

因此：

```text
高频维度
→ 对位置变化非常敏感
→ 更容易区分局部、短距离的位置关系

低频维度
→ 随位置变化较慢
→ 可以表示较大尺度的位置关系
```

不过需要特别注意：

> **不能简单说某个频率一定负责“语法”，另一个频率一定负责“长距离语义”。**

网络最终如何利用这些高频、低频维度，是通过训练学出来的。

`freqs` 只是给模型提供：

```text
不同尺度的位置变化方式
```

至于哪些维度最终更重要、用于表达什么信息，是模型训练后决定的。

---

<a id="origin-2942"></a>
## 23. 为什么使用指数形式

RoPE 没有直接使用：

```text
1
0.9
0.8
0.7
...
```

这种线性频率。

而使用：

\[
1,
\frac1{10},
\frac1{100},
\frac1{1000},
\cdots
\]

这种指数尺度。

原因是 Transformer 需要同时表示非常不同尺度的位置关系。

例如：

```text
1 个 token
10 个 token
100 个 token
1000 个 token
10000 个 token
```

如果使用线性变化，频率覆盖范围会比较有限。

指数变化可以使不同维度自然覆盖：

```text
局部位置
中等距离
长距离
超长距离
```

不同尺度。

---

<a id="origin-2995"></a>
## 24. `rope_base` 是干什么的

公式：

\[
\theta_i
=
\frac{1}
{\text{rope\_base}^{2i/d}}
\]

因此：

```text
rope_base
```

决定：

> 不同维度之间的频率分布范围。

例如：

```text
rope_base = 10000
```

和：

```text
rope_base = 1,000,000
```

相比，后者会产生更多非常低的频率。

简单理解：

```text
rope_base 越大
↓
后面的维度 freq 越小
↓
旋转得越慢
↓
位置变化周期越长
```

因此现代长上下文模型有时会使用更大的：

```python
rope_theta
```

例如：

```text
1e6
```

从而改变频率分布，使位置编码更加适合较长的上下文。

---

<a id="origin-3058"></a>
## 25. `[: (dim // 2)]` 是什么意思

代码：

```python
torch.arange(0, dim, 2)[: (dim // 2)]
```

其中：

```python
torch.arange(0, dim, 2)
```

本身通常已经有：

\[
\frac{dim}{2}
\]

个元素。

例如：

```text
dim = 128
```

则：

```python
torch.arange(0, 128, 2)
```

得到：

```text
0, 2, 4, ..., 126
```

总共：

```text
64
```

个数。

而：

```python
dim // 2
```

也是：

```text
64
```

因此：

```python
[: (dim // 2)]
```

很多情况下实际上没有改变结果。

它主要是在明确保证：

```text
freqs 的数量 = dim / 2
```

因为每个 frequency 对应一个二维平面：

```text
两个维度共享一个旋转频率
```

所以：

\[
\boxed{
\text{freqs 数量}
=
\frac{dim}{2}
}
\]

---

<a id="origin-3150"></a>
## 26. `attn_factor = 1.0` 是什么

代码：

```python
freqs, attn_factor = ..., 1.0
```

相当于：

```python
freqs = ...
attn_factor = 1.0
```

这里：

```text
attn_factor
```

不是标准 RoPE 频率计算的核心组成部分。

在普通 RoPE 中：

```python
attn_factor = 1.0
```

意味着：

> 不额外对 RoPE 的 cos / sin 或 Attention 尺度进行缩放。

在 YaRN 等长上下文扩展方法中，`attn_factor` 可能会被进一步调整。

因此此时可以简单理解为：

```text
标准 RoPE：
attn_factor = 1
不做额外修正
```

---

<a id="origin-3195"></a>
## 27. 整段代码可以拆成下面几步

原代码：

```python
freqs = 1.0 / (
    rope_base ** (
        torch.arange(0, dim, 2)[: (dim // 2)].float() / dim
    )
)
```

可以拆成：

```python
# 第一步：得到每一个二维维度的编号
indices = torch.arange(0, dim, 2).float()
```

例如：

```text
dim = 8

indices =
[0, 2, 4, 6]
```

然后：

```python
# 第二步：除以总维度
exponent = indices / dim
```

得到：

```text
[0, 0.25, 0.5, 0.75]
```

然后：

```python
# 第三步：指数变化
scale = rope_base ** exponent
```

如果：

```text
rope_base = 10000
```

得到：

```text
[1, 10, 100, 1000]
```

最后：

```python
# 第四步：取倒数
freqs = 1.0 / scale
```

得到：

```text
[1, 0.1, 0.01, 0.001]
```

---

<a id="origin-3270"></a>
## 28. 最终完整逻辑

整个 RoPE 可以理解为：

```text
hidden dimension
        ↓
两个维度组成一个二维平面
        ↓
为每一个二维平面分配不同的 frequency
        ↓
freq_i = 1 / base^(2i/d)
        ↓
token 有位置 m
        ↓
angle = m × freq_i
        ↓
得到 cos(angle)、sin(angle)
        ↓
构造二维旋转矩阵
        ↓
旋转 Q、K
        ↓
把位置信息写入 Q、K
```

因此这一句：

```python
freqs = 1.0 / (
    rope_base ** (
        torch.arange(0, dim, 2).float() / dim
    )
)
```

最核心的数学意义就是：

\[
\boxed{
\theta_i
=
\frac{1}
{\text{rope\_base}^{2i/d}}
}
\]

然后 token 位置 \(m\) 对应的真正旋转角度：

\[
\boxed{
\phi_{m,i}
=
m\theta_i
=
\frac{m}
{\text{rope\_base}^{2i/d}}
}
\]

最后使用：

\[
\boxed{
R(\phi_{m,i})
=
\begin{bmatrix}
\cos \phi_{m,i} & -\sin \phi_{m,i}\\
\sin \phi_{m,i} & \cos \phi_{m,i}
\end{bmatrix}
}
\]

对 Q 和 K 的每一对维度进行旋转。

---

<a id="origin-3347"></a>
### 28.1 一句话总结

```python
freqs = 1.0 / (rope_base ** (torch.arange(0, dim, 2) / dim))
```

本质是在做：

> **给 Q/K 的每两个维度分配一个不同的旋转速度，使不同维度以从高频到低频的方式编码不同尺度的位置信息。**

其核心公式就是：

\[
\boxed{
\theta_i
=
\text{rope\_base}^{-\frac{2i}{d}}
}
\]

而真正用于第 \(m\) 个 token 旋转的角度为：

\[
\boxed{
m\theta_i
}
\]