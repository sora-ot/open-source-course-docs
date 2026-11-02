# LoRA 原理与低秩推导


<a id="origin-3"></a>
## 1. LoRA 到底要解决什么问题？

假设我们有一个已经预训练好的大模型。

其中某一层 Linear 为：

\[
y = W_0x
\]

这里：

\[
x\in \mathbb{R}^{d_{\text{in}}}
\]

\[
W_0\in \mathbb{R}^{d_{\text{out}}\times d_{\text{in}}}
\]

\[
y\in\mathbb{R}^{d_{\text{out}}}
\]

例如 Transformer 中：

```text
hidden state
     ↓
   q_proj
     ↓
      Q
```

如果：

\[
d_{\text{in}}=4096
\]

\[
d_{\text{out}}=4096
\]

那么：

\[
W_0\in\mathbb{R}^{4096\times4096}
\]

一共有：

\[
4096\times4096
=
16,777,216
\]

也就是约 **1678 万个参数**。

---

<a id="origin-65"></a>
## 2. 普通全量微调到底在干什么？

预训练结束以后，我们已经有：

\[
W_0
\]

现在想在自己的数据上继续训练。

普通 Full Fine-Tuning 做的是：

\[
W_0
\rightarrow
W
\]

我们可以把新的参数写成：

\[
W=W_0+\Delta W
\]

其中：

- \(W_0\)：预训练模型原来的参数
- \(\Delta W\)：微调过程中学到的参数变化

所以微调后的计算其实就是：

\[
y
=
Wx
\]

代入：

\[
W=W_0+\Delta W
\]

得到：

\[
y
=
(W_0+\Delta W)x
\]

展开：

\[
\boxed{
y=W_0x+\Delta Wx
}
\]

这一行非常重要。

它告诉我们：

> 微调其实可以理解成：在原模型 \(W_0x\) 的基础上，再学习一个“修正量” \(\Delta Wx\)。

---

<a id="origin-132"></a>
## 3. Full Fine-Tuning 为什么贵？

问题出现在：

\[
\Delta W
\]

如果：

\[
W_0\in\mathbb{R}^{4096\times4096}
\]

那么：

\[
\Delta W
\in
\mathbb{R}^{4096\times4096}
\]

也需要学习：

\[
4096\times4096
=
16,777,216
\]

个参数。

也就是说：

> 为了稍微修改一下这个已经训练好的模型，我们又要训练完整的 1678 万个参数。

而一个大语言模型有很多这样的矩阵。

例如：

```text
q_proj
k_proj
v_proj
o_proj

gate_proj
up_proj
down_proj
...
```

再乘几十层 Transformer Block。

所以全量微调的训练参数可能达到几十亿甚至几百亿。

---

<a id="origin-190"></a>
## 4. LoRA 最核心的想法从哪里来？

LoRA 提出了一个非常重要的假设：

> 大模型虽然参数非常多，但是为了适应一个新任务，真正需要发生的参数变化可能并没有那么复杂。

也就是说：

\[
\Delta W
\]

虽然表面上是一个巨大的：

\[
4096\times4096
\]

矩阵，但它可能实际上只包含少数几个主要的“变化方向”。

数学上就是：

\[
\operatorname{rank}(\Delta W)
\ll 4096
\]

这就是：

<a id="origin-219"></a>
## 5. Low-Rank

也就是：

<a id="origin-223"></a>
## 6. 低秩

LoRA：

\[
\text{Low-Rank Adaptation}
\]

名字就是这么来的。

---


<a id="origin-236"></a>
## 7. 补充：线性代数里矩阵的秩到底怎么计算？

前面我们说：

\[
\operatorname{rank}(A)
\]

表示矩阵中有多少个**真正独立的方向**。

但是实际拿到一个矩阵以后，我们怎么知道它的 Rank 到底是多少？

线性代数里最常用的方法就是：

\[
\boxed{\text{初等行变换}}
\]

把矩阵逐渐化成：

\[
\boxed{\text{行阶梯形矩阵}}
\]

最后：

> **数一数有多少个非零行，也就是有多少个主元（pivot），Rank 就是多少。**

---

<a id="origin-266"></a>
## 8. 什么叫初等行变换？

矩阵有三种基本的行变换。

<a id="origin-270"></a>
### 8.1 第一种：交换两行

例如：

\[
\begin{bmatrix}
1&2\\
3&4
\end{bmatrix}
\]

交换第一行和第二行：

\[
R_1\leftrightarrow R_2
\]

得到：

\[
\begin{bmatrix}
3&4\\
1&2
\end{bmatrix}
\]

---

<a id="origin-298"></a>
### 8.2 第二种：某一行乘一个非零常数

例如：

\[
R_1\leftarrow2R_1
\]

那么：

\[
\begin{bmatrix}
1&2\\
3&4
\end{bmatrix}
\]

变成：

\[
\begin{bmatrix}
2&4\\
3&4
\end{bmatrix}
\]

注意，乘数不能是 0。

---

<a id="origin-328"></a>
### 8.3 第三种：某一行加上另一行的若干倍

这是最重要的一种。

例如：

\[
R_2\leftarrow R_2-2R_1
\]

如果：

\[
A=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

那么：

\[
R_2-2R_1
=
[2,4]-2[1,2]
\]

得到：

\[
[0,0]
\]

于是矩阵变成：

\[
\begin{bmatrix}
1&2\\
0&0
\end{bmatrix}
\]

这时候立刻就能看出来：

只有一行是独立的。

因此：

\[
\boxed{\operatorname{rank}(A)=1}
\]

---

<a id="origin-383"></a>
## 9. 为什么可以随便做这些行变换？

因为这些变换不会改变矩阵中：

\[
\boxed{\text{独立信息的数量}}
\]

也就是说：

\[
\boxed{\text{初等行变换不改变矩阵的秩}}
\]

比如：

\[
A=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

第二行本来就是：

\[
2R_1
\]

我们做：

\[
R_2\leftarrow R_2-2R_1
\]

只是把这个“重复的信息”消掉：

\[
\begin{bmatrix}
1&2\\
0&0
\end{bmatrix}
\]

并没有丢掉任何真正独立的信息。

---

<a id="origin-432"></a>
## 10. 一个最简单的 Rank=1 例子

给定：

\[
A=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

做：

\[
R_2\leftarrow R_2-2R_1
\]

于是：

\[
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

变成：

\[
\begin{bmatrix}
1&2\\
0&0
\end{bmatrix}
\]

只有一行非零：

\[
[1,2]
\]

因此：

\[
\boxed{\operatorname{rank}(A)=1}
\]

---

<a id="origin-482"></a>
## 11. 一个 Rank=2 的例子

假设：

\[
A=
\begin{bmatrix}
1&2\\
3&4
\end{bmatrix}
\]

先消掉第一列下面的 3。

做：

\[
R_2\leftarrow R_2-3R_1
\]

得到：

\[
\begin{bmatrix}
1&2\\
0&-2
\end{bmatrix}
\]

现在有两行非零：

\[
[1,2]
\]

和：

\[
[0,-2]
\]

因此：

\[
\boxed{\operatorname{rank}(A)=2}
\]

---

<a id="origin-531"></a>
## 12. 一个 3×3 的完整例子

假设：

\[
A=
\begin{bmatrix}
1&2&3\\
2&4&6\\
1&1&1
\end{bmatrix}
\]

我们一步一步做。

---

<a id="origin-548"></a>
### 12.1 第一步：消掉第二行第一列

做：

\[
R_2\leftarrow R_2-2R_1
\]

因为：

\[
[2,4,6]-2[1,2,3]
=
[0,0,0]
\]

所以：

\[
A
\rightarrow
\begin{bmatrix}
1&2&3\\
0&0&0\\
1&1&1
\end{bmatrix}
\]

---

<a id="origin-578"></a>
### 12.2 第二步：消掉第三行第一列

做：

\[
R_3\leftarrow R_3-R_1
\]

得到：

\[
[1,1,1]-[1,2,3]
=
[0,-1,-2]
\]

所以：

\[
A
\rightarrow
\begin{bmatrix}
1&2&3\\
0&0&0\\
0&-1&-2
\end{bmatrix}
\]

交换第二、三行：

\[
R_2\leftrightarrow R_3
\]

得到：

\[
\begin{bmatrix}
1&2&3\\
0&-1&-2\\
0&0&0
\end{bmatrix}
\]

这就是一个行阶梯形矩阵。

---

<a id="origin-626"></a>
## 13. 最后怎么判断 Rank？

现在：

\[
\begin{bmatrix}
1&2&3\\
0&-1&-2\\
0&0&0
\end{bmatrix}
\]

有：

\[
2
\]

行非零。

因此：

\[
\boxed{\operatorname{rank}(A)=2}
\]

也可以看主元：

第一行主元：

\[
1
\]

第二行主元：

\[
-1
\]

一共有两个 pivot。

因此：

\[
\boxed{rank=2}
\]

---

<a id="origin-676"></a>
## 14. 什么叫 Pivot？

例如：

\[
\begin{bmatrix}
1&2&3\\
0&-1&-2\\
0&0&0
\end{bmatrix}
\]

第一行最左边的非零元素：

\[
1
\]

是一个 Pivot。

第二行最左边的非零元素：

\[
-1
\]

也是一个 Pivot。

所以：

```text
Pivot 1
   ↓
[ 1   2   3 ]
[ 0  -1  -2 ]
      ↑
   Pivot 2

[ 0   0   0 ]
```

Pivot 的个数就是：

\[
\boxed{\operatorname{rank}(A)}
\]

---

<a id="origin-725"></a>
## 15. 所谓“把矩阵化简”是什么意思？

线性代数里通常不是说“优化矩阵”，而是说：

\[
\boxed{\text{矩阵化简}}
\]

或者：

\[
\boxed{\text{高斯消元}}
\]

核心目标就是：

> 利用初等行变换，把矩阵变成一个更容易观察结构的形式。

例如原来：

\[
\begin{bmatrix}
1&2&3\\
2&4&6\\
1&1&1
\end{bmatrix}
\]

很难直接看出 Rank。

通过高斯消元变成：

\[
\begin{bmatrix}
1&2&3\\
0&-1&-2\\
0&0&0
\end{bmatrix}
\]

现在一眼就知道：

\[
\boxed{rank=2}
\]

---

<a id="origin-773"></a>
## 16. 行阶梯形矩阵是什么？

例如：

\[
\begin{bmatrix}
1&2&3&4\\
0&1&5&6\\
0&0&2&7\\
0&0&0&0
\end{bmatrix}
\]

它的特点是：

```text
第一行从第1列开始
第二行从第2列开始
第三行从第3列开始
第四行全0
```

非零元素像楼梯一样往右下走：

```text
× × × ×
  × × ×
    × ×
      0
```

因此叫：

\[
\boxed{\text{Row Echelon Form}}
\]

行阶梯形。

这里有：

\[
3
\]

个非零行，所以：

\[
\boxed{rank=3}
\]

---

<a id="origin-826"></a>
## 17. 还能继续化成“最简行阶梯形”

例如：

\[
\begin{bmatrix}
1&2\\
0&-2
\end{bmatrix}
\]

先：

\[
R_2\leftarrow-\frac12R_2
\]

得到：

\[
\begin{bmatrix}
1&2\\
0&1
\end{bmatrix}
\]

然后：

\[
R_1\leftarrow R_1-2R_2
\]

得到：

\[
\boxed{
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix}
}
\]

这种形式叫：

\[
\boxed{\text{Reduced Row Echelon Form}}
\]

也就是：

> 最简行阶梯形矩阵。

但是如果我们只是为了计算 Rank：

> 一般没必要化到这么彻底。

只需要化到能看出：

\[
\boxed{\text{有多少个非零行}}
\]

就够了。

---

<a id="origin-893"></a>
## 18. 为什么“非零行数”就等于独立方向数量？

例如化简以后：

\[
\begin{bmatrix}
1&2&3\\
0&-1&-2\\
0&0&0
\end{bmatrix}
\]

第三行：

\[
[0,0,0]
\]

意味着：

> 原矩阵中有一行可以完全由其他行组合得到。

所以它没有提供新的独立方向。

而前两行：

\[
[1,2,3]
\]

和：

\[
[0,-1,-2]
\]

彼此独立。

因此只有两个独立方向：

\[
\boxed{rank=2}
\]

---

<a id="origin-939"></a>
## 19. 还可以用行列式判断 Rank

对于一个：

\[
2\times2
\]

矩阵：

\[
A=
\begin{bmatrix}
a&b\\
c&d
\end{bmatrix}
\]

行列式：

\[
\det(A)=ad-bc
\]

如果：

\[
\det(A)\neq0
\]

那么：

\[
\boxed{rank(A)=2}
\]

例如：

\[
A=
\begin{bmatrix}
1&2\\
3&4
\end{bmatrix}
\]

有：

\[
\det(A)
=
1\times4-2\times3
=
-2
\]

不等于 0，所以：

\[
\boxed{rank(A)=2}
\]

---

反过来：

\[
A=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

则：

\[
\det(A)
=
1\times4-2\times2
=
0
\]

所以它不是满秩矩阵。

因为矩阵又不是全 0：

\[
A\neq0
\]

所以：

\[
\boxed{rank(A)=1}
\]

---

<a id="origin-1039"></a>
## 20. 对于 n×n 方阵，一个重要结论

如果：

\[
A\in\mathbb{R}^{n\times n}
\]

并且：

\[
\boxed{\det(A)\neq0}
\]

那么：

\[
\boxed{rank(A)=n}
\]

这叫：

\[
\boxed{\text{满秩 Full Rank}}
\]

同时意味着：

\[
A^{-1}
\]

存在。

---

如果：

\[
\det(A)=0
\]

那么：

\[
\boxed{rank(A)<n}
\]

说明里面存在重复或者线性相关的信息。

---

<a id="origin-1091"></a>
## 21. 非方阵怎么办？

比如：

\[
A\in\mathbb{R}^{3\times5}
\]

那么 Rank 最大不可能超过：

\[
3
\]

因为只有 3 行。

同样也不能超过 5。

所以一般：

\[
\boxed{
rank(A)\le\min(m,n)
}
\]

对于：

\[
A\in\mathbb{R}^{m\times n}
\]

最大 Rank 就是：

\[
\boxed{\min(m,n)}
\]

---

例如：

\[
A\in\mathbb{R}^{4096\times8}
\]

那么：

\[
rank(A)\le8
\]

因为不管 4096 有多大，中间只有 8 列。

这就直接和 LoRA 联系起来了。

---

<a id="origin-1149"></a>
## 22. 为什么 LoRA 中 \(BA\) 的 Rank 一定不会超过 \(r\)？

假设：

\[
A\in\mathbb{R}^{r\times4096}
\]

因此：

\[
rank(A)\le r
\]

同时：

\[
B\in\mathbb{R}^{4096\times r}
\]

因此：

\[
rank(B)\le r
\]

线性代数中有一个重要结论：

\[
\boxed{
rank(BA)
\le
\min(rank(B),rank(A))
}
\]

所以：

\[
rank(BA)\le r
\]

因此：

\[
\boxed{
\Delta W=BA
}
\]

一定是一个 Rank 不超过 \(r\) 的矩阵。

例如：

\[
r=8
\]

那么：

\[
\boxed{
rank(\Delta W)\le8
}
\]

这就是为什么 LoRA 天然得到一个低秩更新矩阵。

---

<a id="origin-1219"></a>
## 23. 最后记住最实用的方法

考试或者实际手算 Rank 时，最常用的办法就是：

```text
原矩阵
   ↓
初等行变换
   ↓
高斯消元
   ↓
行阶梯形
   ↓
数 Pivot / 非零行
   ↓
Rank
```

也就是：

\[
\boxed{
\text{矩阵秩}
=
\text{高斯消元后 Pivot 的数量}
}
\]

例如：

\[
\begin{bmatrix}
1&2&3\\
2&4&6\\
1&1&1
\end{bmatrix}
\]

经过消元：

\[
\longrightarrow
\begin{bmatrix}
1&2&3\\
0&-1&-2\\
0&0&0
\end{bmatrix}
\]

有两个 Pivot：

\[
\boxed{rank=2}
\]

然后回到 LoRA：

\[
\Delta W=BA
\]

因为中间维度只有：

\[
r
\]

所以：

\[
\boxed{rank(\Delta W)\le r}
\]

这就是线性代数中的“秩”和 LoRA 中“低秩”之间最直接的联系。


---

<a id="origin-1297"></a>
## 24. 什么叫“低秩”？

先不要急着看 LoRA。

举一个最简单的矩阵：

\[
M=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

虽然它是一个：

\[
2\times2
\]

矩阵，但是第二行：

\[
[2,4]
\]

实际上就是第一行：

\[
[1,2]
\]

乘 2。

所以它实际上只有一个独立方向。

因此：

\[
\operatorname{rank}(M)=1
\]

这个矩阵可以写成两个小矩阵相乘：

\[
M
=
\begin{bmatrix}
1\\
2
\end{bmatrix}
\begin{bmatrix}
1&2
\end{bmatrix}
\]

计算：

\[
\begin{bmatrix}
1\\
2
\end{bmatrix}
\begin{bmatrix}
1&2
\end{bmatrix}
=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

也就是：

\[
M=BA
\]

其中：

\[
B\in\mathbb{R}^{2\times1}
\]

\[
A\in\mathbb{R}^{1\times2}
\]

原来需要：

\[
2\times2=4
\]

个参数。

现在只需要：

\[
2\times1+1\times2=4
\]

这个小例子暂时没有省参数。

但是当矩阵非常大的时候，效果就完全不同了。

---

<a id="origin-1406"></a>
## 25. 从这里正式推出 LoRA

原来的参数变化：

\[
\Delta W
\in
\mathbb{R}^{d_{\text{out}}\times d_{\text{in}}}
\]

LoRA 不直接学习整个：

\[
\Delta W
\]

而是假设：

\[
\operatorname{rank}(\Delta W)\le r
\]

其中：

\[
r\ll
d_{\text{in}},
d_{\text{out}}
\]

于是把：

\[
\Delta W
\]

写成：

\[
\boxed{
\Delta W=BA
}
\]

其中：

\[
A
\in
\mathbb{R}^{r\times d_{\text{in}}}
\]

\[
B
\in
\mathbb{R}^{d_{\text{out}}\times r}
\]

因此：

\[
W=W_0+BA
\]

于是：

\[
y=Wx
\]

变成：

\[
y=(W_0+BA)x
\]

展开：

\[
\boxed{
y=W_0x+BAx
}
\]

这就是 LoRA 最核心的公式。

---

<a id="origin-1494"></a>
## 26. 为什么 \(BA\) 一定是低秩的？

因为：

\[
A:
d_{\text{in}}
\rightarrow r
\]

然后：

\[
B:
r
\rightarrow d_{\text{out}}
\]

中间只有：

\[
r
\]

维。

所以无论输入输出多大：

\[
\operatorname{rank}(BA)\le r
\]

例如：

\[
A:
4096
\rightarrow 8
\]

\[
B:
8
\rightarrow4096
\]

那么：

\[
BA
\]

虽然最后仍然相当于一个：

\[
4096\times4096
\]

矩阵，但是：

\[
\operatorname{rank}(BA)\le8
\]

也就是说：

> LoRA 不允许 \(\Delta W\) 在 4096 个完全独立的方向上随便变化，只允许它利用最多 8 个主要方向修改原模型。

---

<a id="origin-1564"></a>
## 27. 为什么两个小矩阵能省这么多参数？

Full Fine-Tuning 中：

\[
\Delta W
\in
\mathbb{R}^{4096\times4096}
\]

参数量：

\[
4096\times4096
=
16,777,216
\]

---

LoRA 假设：

\[
r=8
\]

于是：

\[
A\in\mathbb{R}^{8\times4096}
\]

参数量：

\[
8\times4096
=
32768
\]

而：

\[
B\in\mathbb{R}^{4096\times8}
\]

参数量：

\[
4096\times8
=
32768
\]

总参数：

\[
32768+32768
=
65536
\]

因此：

\[
\frac{65536}{16777216}
\approx0.00390625
\]

也就是：

\[
\boxed{0.39\%}
\]

原来要训练：

```text
16,777,216 个参数
```

现在只训练：

```text
65,536 个参数
```

约为原来的：

\[
\frac1{256}
\]

---

<a id="origin-1659"></a>
## 28. 一个特别重要的理解：LoRA 不是分解原来的 \(W_0\)

这是初学者最容易搞错的地方。

LoRA **不是**：

\[
W_0=BA
\]

不是把预训练模型压缩掉。

LoRA 做的是：

\[
\boxed{
\Delta W=BA
}
\]

所以：

\[
\boxed{
W=W_0+BA
}
\]

原模型：

\[
W_0
\]

完整保留。

只是额外学习一个：

\[
BA
\]

来修改它。

因此应该理解为：

```text
原模型能力 W0
      +
新任务学到的修正量 BA
      =
适应新任务后的模型
```

---

<a id="origin-1715"></a>
## 29. 更深入理解：为什么 \(BA\) 代表几个“修改方向”？

假设：

\[
r=2
\]

那么：

\[
B=
\begin{bmatrix}
|&|\\
b_1&b_2\\
|&|
\end{bmatrix}
\]

而：

\[
A=
\begin{bmatrix}
-a_1^T-\\
-a_2^T-
\end{bmatrix}
\]

矩阵相乘可以展开成：

\[
BA
=
b_1a_1^T+b_2a_2^T
\]

也就是说：

\[
\boxed{
\Delta W
=
b_1a_1^T
+
b_2a_2^T
}
\]

如果：

\[
r=8
\]

那么：

\[
\boxed{
\Delta W
=
\sum_{i=1}^{8}
b_i a_i^T
}
\]

每一个：

\[
b_i a_i^T
\]

都是一个 Rank-1 的矩阵。

所以 LoRA 可以理解成：

> 不让模型随便修改几千万个互相独立的参数，而是学习 \(r\) 个主要的“参数修改方向”，最后把这些方向组合起来。

---

<a id="origin-1795"></a>
## 30. Rank=2 的 LoRA：为什么 \(BA\) 代表几个“修改方向”？

假设 LoRA 的秩为：

\[
r=2
\]

为了方便理解，假设原始权重矩阵：

\[
W\in\mathbb R^{3\times 3}
\]

LoRA 不直接学习一个完整的：

\[
\Delta W\in\mathbb R^{3\times 3}
\]

而是把它拆成：

\[
\Delta W=BA
\]

其中：

\[
B\in\mathbb R^{3\times 2}
\]

\[
A\in\mathbb R^{2\times 3}
\]

---

<a id="origin-1833"></a>
## 31. 先给出一个具体的 \(B\)

假设：

\[
B=
\begin{bmatrix}
1&0\\
0&1\\
1&1
\end{bmatrix}
\]

可以把它按列拆成：

\[
B=
\begin{bmatrix}
|&|\\
b_1&b_2\\
|&|
\end{bmatrix}
\]

其中：

\[
b_1=
\begin{bmatrix}
1\\
0\\
1
\end{bmatrix}
\]

\[
b_2=
\begin{bmatrix}
0\\
1\\
1
\end{bmatrix}
\]

也就是说，\(B\) 中包含两个列向量：

\[
b_1,\quad b_2
\]

可以先把它们理解成两个候选的“修改方向”。

---

<a id="origin-1887"></a>
## 32. 再给出一个具体的 \(A\)

假设：

\[
A=
\begin{bmatrix}
1&2&0\\
0&-1&3
\end{bmatrix}
\]

可以按行写成：

\[
A=
\begin{bmatrix}
-a_1^T-\\
-a_2^T-
\end{bmatrix}
\]

其中：

\[
a_1^T=
\begin{bmatrix}
1&2&0
\end{bmatrix}
\]

\[
a_2^T=
\begin{bmatrix}
0&-1&3
\end{bmatrix}
\]

---

<a id="origin-1927"></a>
## 33. 展开 \(BA\)

LoRA 的修改矩阵是：

\[
\Delta W=BA
\]

因为：

\[
B=
\begin{bmatrix}
|&|\\
b_1&b_2\\
|&|
\end{bmatrix}
\]

而：

\[
A=
\begin{bmatrix}
-a_1^T-\\
-a_2^T-
\end{bmatrix}
\]

所以矩阵乘法可以展开成：

\[
\boxed{
BA=b_1a_1^T+b_2a_2^T
}
\]

因此：

\[
\boxed{
\Delta W
=
b_1a_1^T+b_2a_2^T
}
\]

---

<a id="origin-1976"></a>
## 34. 计算第一个 Rank-1 修改矩阵

先算：

\[
b_1a_1^T
\]

也就是：

\[
\begin{bmatrix}
1\\
0\\
1
\end{bmatrix}
\begin{bmatrix}
1&2&0
\end{bmatrix}
\]

得到：

\[
b_1a_1^T
=
\begin{bmatrix}
1&2&0\\
0&0&0\\
1&2&0
\end{bmatrix}
\]

观察这个矩阵的三列：

第一列：

\[
\begin{bmatrix}
1\\
0\\
1
\end{bmatrix}
=
1b_1
\]

第二列：

\[
\begin{bmatrix}
2\\
0\\
2
\end{bmatrix}
=
2b_1
\]

第三列：

\[
\begin{bmatrix}
0\\
0\\
0
\end{bmatrix}
=
0b_1
\]

因此，这个矩阵的所有列都只是：

\[
b_1
\]

的倍数。

也就是说，它实际上只有一个独立的方向：

\[
\boxed{b_1}
\]

所以：

\[
\operatorname{rank}(b_1a_1^T)=1
\]

因此 \(b_1a_1^T\) 是一个 Rank-1 矩阵。

---

<a id="origin-2071"></a>
## 35. 计算第二个 Rank-1 修改矩阵

再算：

\[
b_2a_2^T
\]

也就是：

\[
\begin{bmatrix}
0\\
1\\
1
\end{bmatrix}
\begin{bmatrix}
0&-1&3
\end{bmatrix}
\]

得到：

\[
b_2a_2^T
=
\begin{bmatrix}
0&0&0\\
0&-1&3\\
0&-1&3
\end{bmatrix}
\]

观察它的三列：

第一列：

\[
\begin{bmatrix}
0\\
0\\
0
\end{bmatrix}
=
0b_2
\]

第二列：

\[
\begin{bmatrix}
0\\
-1\\
-1
\end{bmatrix}
=
-1b_2
\]

第三列：

\[
\begin{bmatrix}
0\\
3\\
3
\end{bmatrix}
=
3b_2
\]

因此，它所有的列也都只是：

\[
b_2
\]

的倍数。

所以它也只有一个独立方向：

\[
\boxed{b_2}
\]

因此：

\[
\operatorname{rank}(b_2a_2^T)=1
\]

---

<a id="origin-2164"></a>
## 36. 两个 Rank-1 矩阵加起来

LoRA 最终的修改矩阵是：

\[
\Delta W
=
b_1a_1^T+b_2a_2^T
\]

代入：

\[
\Delta W
=
\begin{bmatrix}
1&2&0\\
0&0&0\\
1&2&0
\end{bmatrix}
+
\begin{bmatrix}
0&0&0\\
0&-1&3\\
0&-1&3
\end{bmatrix}
\]

得到：

\[
\boxed{
\Delta W
=
\begin{bmatrix}
1&2&0\\
0&-1&3\\
1&1&3
\end{bmatrix}
}
\]

这个矩阵最多只有 Rank 2：

\[
\boxed{
\operatorname{rank}(\Delta W)\leq 2
}
\]

因为它就是两个 Rank-1 矩阵相加得到的：

\[
\Delta W
=
\underbrace{b_1a_1^T}_{Rank\ 1}
+
\underbrace{b_2a_2^T}_{Rank\ 1}
\]

---

<a id="origin-2226"></a>
## 37. 为什么说 \(b_1,b_2\) 是两个“修改方向”？

这一点放到神经网络真正的前向传播里会更加明显。

原来的线性层：

\[
y=Wx
\]

加入 LoRA 后：

\[
y=(W+\Delta W)x
\]

即：

\[
y=Wx+\Delta Wx
\]

LoRA 产生的修改量就是：

\[
\Delta y=\Delta Wx
\]

因为：

\[
\Delta W
=
b_1a_1^T+b_2a_2^T
\]

所以：

\[
\Delta y
=
(b_1a_1^T+b_2a_2^T)x
\]

利用结合律：

\[
\Delta y
=
b_1(a_1^Tx)
+
b_2(a_2^Tx)
\]

因此：

\[
\boxed{
\Delta y
=
(a_1^Tx)b_1
+
(a_2^Tx)b_2
}
\]

这就是“两个修改方向”最直观的数学形式。

---

<a id="origin-2296"></a>
## 38. 给一个具体输入

假设：

\[
x=
\begin{bmatrix}
1\\
1\\
1
\end{bmatrix}
\]

先计算第一个系数：

\[
a_1^Tx
=
\begin{bmatrix}
1&2&0
\end{bmatrix}
\begin{bmatrix}
1\\
1\\
1
\end{bmatrix}
\]

得到：

\[
a_1^Tx
=
1\times1+2\times1+0\times1
=
3
\]

再计算第二个系数：

\[
a_2^Tx
=
\begin{bmatrix}
0&-1&3
\end{bmatrix}
\begin{bmatrix}
1\\
1\\
1
\end{bmatrix}
\]

得到：

\[
a_2^Tx
=
0\times1-1\times1+3\times1
=
2
\]

所以：

\[
\Delta y
=
3b_1+2b_2
\]

代入：

\[
b_1=
\begin{bmatrix}
1\\
0\\
1
\end{bmatrix}
\]

\[
b_2=
\begin{bmatrix}
0\\
1\\
1
\end{bmatrix}
\]

于是：

\[
\Delta y
=
3
\begin{bmatrix}
1\\
0\\
1
\end{bmatrix}
+
2
\begin{bmatrix}
0\\
1\\
1
\end{bmatrix}
\]

即：

\[
\Delta y
=
\begin{bmatrix}
3\\
0\\
3
\end{bmatrix}
+
\begin{bmatrix}
0\\
2\\
2
\end{bmatrix}
\]

最终：

\[
\boxed{
\Delta y=
\begin{bmatrix}
3\\
2\\
5
\end{bmatrix}
}
\]

---

<a id="origin-2440"></a>
## 39. 这个例子真正说明了什么？

最关键的公式是：

\[
\boxed{
\Delta y
=
(a_1^Tx)b_1
+
(a_2^Tx)b_2
}
\]

可以这样理解：

\[
b_1,b_2
\]

决定了：

> 模型允许沿着哪些方向修改输出。

而：

\[
a_1^Tx,\quad a_2^Tx
\]

决定了：

> 对于当前这个输入，每个方向应该使用多少。

例如当前输入得到：

\[
a_1^Tx=3
\]

\[
a_2^Tx=2
\]

于是模型就在：

\[
b_1
\]

方向移动 3 倍，在：

\[
b_2
\]

方向移动 2 倍。

最终：

\[
\Delta y=3b_1+2b_2
\]

---

<a id="origin-2506"></a>
## 40. 为什么这叫低秩？

如果直接训练完整的：

\[
\Delta W\in\mathbb R^{3\times3}
\]

那么理论上它可以自由地学习很多不同的修改方式。

但是 LoRA 强制：

\[
\Delta W=BA
\]

并且：

\[
r=2
\]

所以：

\[
\operatorname{rank}(\Delta W)\leq2
\]

也就是说，这个修改矩阵不能随便变化，而只能由两个 Rank-1 修改组合出来：

\[
\boxed{
\Delta W
=
b_1a_1^T
+
b_2a_2^T
}
\]

因此可以把 Rank=2 的 LoRA 理解成：

> 模型不再允许每个参数完全独立地随便修改，而是假设真正重要的参数变化可以压缩成少数几个主要修改模式。

---

<a id="origin-2552"></a>
## 41. 一句话总结

对于 Rank=2：

\[
\boxed{
\Delta W=b_1a_1^T+b_2a_2^T
}
\]

而真正作用到输入 \(x\) 后：

\[
\boxed{
\Delta y
=
(a_1^Tx)b_1
+
(a_2^Tx)b_2
}
\]

所以可以直观理解为：

> \(B\) 学习两个“往哪里改”的方向 \(b_1,b_2\)，而 \(A\) 根据输入 \(x\) 判断这两个方向分别应该“改多少”。

因此：

\[
\boxed{
r=2
\Longrightarrow
最多使用两个主要修改方向
}
\]

更一般地，当：

\[
r=8
\]

时：

\[
\Delta W
=
\sum_{i=1}^{8}b_i a_i^T
\]

作用到输入上就是：

\[
\boxed{
\Delta y
=
\sum_{i=1}^{8}
(a_i^Tx)b_i
}
\]

也就是：

> LoRA 学习最多 \(8\) 个主要的修改方向，并针对不同输入动态组合这些方向。

---

<a id="origin-2619"></a>
## 42. 从 SVD 的角度理解为什么这个想法合理

任何矩阵都可以通过奇异值分解：

\[
\Delta W
=
U\Sigma V^T
\]

假设真正重要的只有前 \(r\) 个奇异值。

那么：

\[
\Delta W
\approx
U_r\Sigma_rV_r^T
\]

可以进一步写成：

\[
\Delta W
=
\left(
U_r\Sigma_r^{1/2}
\right)
\left(
\Sigma_r^{1/2}V_r^T
\right)
\]

令：

\[
B=U_r\Sigma_r^{1/2}
\]

\[
A=\Sigma_r^{1/2}V_r^T
\]

于是：

\[
\boxed{
\Delta W\approx BA
}
\]

因此从数学上看：

> 如果真正有意义的参数变化主要集中在少数几个方向，就完全没有必要学习一个完整的大矩阵。

但是有一点要特别强调：

**LoRA 训练的时候并不是先训练完整 \(\Delta W\)，再做 SVD。**

而是一开始就直接把：

\[
\Delta W
\]

参数化成：

\[
BA
\]

然后直接训练 \(A,B\)。

---

<a id="origin-2694"></a>
## 43. LoRA 的完整公式为什么还有一个 \(\alpha/r\)？

实际 LoRA 一般不是：

\[
y=W_0x+BAx
\]

而是：

\[
\boxed{
y
=
W_0x+
\frac{\alpha}{r}BAx
}
\]

定义：

\[
s=\frac{\alpha}{r}
\]

于是：

\[
\boxed{
y
=
W_0x+sBAx
}
\]

其中：

- \(r\)：LoRA Rank
- \(\alpha\)：LoRA scaling 参数
- \(\alpha/r\)：LoRA 分支的缩放系数

---

<a id="origin-2737"></a>
## 44. 为什么要乘 \(\alpha/r\)？

假设：

\[
r=8
\]

我们有大约 8 个低秩方向。

如果以后改成：

\[
r=64
\]

方向多了很多。

直接计算：

\[
BA
\]

时，它的整体幅度可能也发生明显变化。

所以 LoRA 用：

\[
\frac{\alpha}{r}
\]

控制 LoRA 分支对原模型的影响大小。

例如：

\[
r=8,\quad \alpha=16
\]

那么：

\[
\frac{\alpha}{r}
=
2
\]

于是：

\[
y=W_0x+2BAx
\]

如果：

\[
r=16,\quad \alpha=16
\]

那么：

\[
\frac{\alpha}{r}
=
1
\]

于是：

\[
y=W_0x+BAx
\]

所以可以暂时把 \(\alpha\) 理解成：

> 控制 LoRA 修改原模型时的整体强度。

---

<a id="origin-2817"></a>
## 45. LoRA 前向传播到底经过了什么？

公式：

\[
y
=
W_0x+
\frac{\alpha}{r}BAx
\]

可以从右向左看。

首先：

\[
x
\in
\mathbb{R}^{d_{\text{in}}}
\]

经过：

\[
A
\in
\mathbb{R}^{r\times d_{\text{in}}}
\]

得到：

\[
z=Ax
\]

其中：

\[
z\in\mathbb{R}^{r}
\]

也就是说：

\[
d_{\text{in}}
\rightarrow r
\]

这是一次**降维**。

然后：

\[
Bz
\]

其中：

\[
B
\in
\mathbb{R}^{d_{\text{out}}\times r}
\]

得到：

\[
Bz\in\mathbb{R}^{d_{\text{out}}}
\]

也就是说：

\[
r
\rightarrow
d_{\text{out}}
\]

又升回原来的输出维度。

整个 LoRA 分支：

```text
x
│
├──────────────→ W0 ───────────→ 原模型输出
│
└→ A：降维
     ↓
     r维
     ↓
   B：升维
     ↓
   LoRA修正量
     ↓
   × α/r
     ↓
     +
     ↓
     y
```

---

<a id="origin-2921"></a>
## 46. 一个完整的数值例子

现在不用 4096 维。

我们做一个特别小的模型。

假设：

\[
x=
\begin{bmatrix}
1\\
2\\
-1
\end{bmatrix}
\]

因此：

\[
d_{\text{in}}=3
\]

原来的权重：

\[
W_0=
\begin{bmatrix}
1&2&0\\
-1&0&1
\end{bmatrix}
\]

因此：

\[
d_{\text{out}}=2
\]

---

<a id="origin-2962"></a>
### 46.1 第一步：原模型输出

计算：

\[
W_0x
\]

即：

\[
\begin{bmatrix}
1&2&0\\
-1&0&1
\end{bmatrix}
\begin{bmatrix}
1\\
2\\
-1
\end{bmatrix}
\]

第一行：

\[
1\times1+2\times2+0\times(-1)
=
5
\]

第二行：

\[
-1\times1+0\times2+1\times(-1)
=
-2
\]

所以：

\[
W_0x=
\begin{bmatrix}
5\\
-2
\end{bmatrix}
\]

---

<a id="origin-3012"></a>
## 47. 加入 Rank=1 的 LoRA

假设：

\[
r=1
\]

于是：

\[
A
\in
\mathbb{R}^{1\times3}
\]

取：

\[
A=
\begin{bmatrix}
0.1&-0.2&0.3
\end{bmatrix}
\]

而：

\[
B
\in
\mathbb{R}^{2\times1}
\]

取：

\[
B=
\begin{bmatrix}
0.5\\
-0.4
\end{bmatrix}
\]

为了方便，先假设：

\[
\frac{\alpha}{r}=1
\]

---

<a id="origin-3063"></a>
### 47.1 第一步：计算 \(Ax\)

\[
Ax
=
\begin{bmatrix}
0.1&-0.2&0.3
\end{bmatrix}
\begin{bmatrix}
1\\
2\\
-1
\end{bmatrix}
\]

得到：

\[
0.1\times1
+
(-0.2)\times2
+
0.3\times(-1)
\]

即：

\[
0.1-0.4-0.3
=
-0.6
\]

所以：

\[
Ax=-0.6
\]

注意：

原来：

\[
x\in\mathbb{R}^3
\]

现在变成：

\[
Ax\in\mathbb{R}^1
\]

这就是降维。

---

<a id="origin-3120"></a>
## 48. 第二步：计算 \(BAx\)

现在：

\[
Ax=-0.6
\]

所以：

\[
BAx
=
\begin{bmatrix}
0.5\\
-0.4
\end{bmatrix}
(-0.6)
\]

得到：

\[
BAx
=
\begin{bmatrix}
-0.3\\
0.24
\end{bmatrix}
\]

这就是 LoRA 学到的：

\[
\boxed{
修正量
}
\]

---

<a id="origin-3161"></a>
## 49. 第三步：加回原模型

原模型：

\[
W_0x
=
\begin{bmatrix}
5\\
-2
\end{bmatrix}
\]

LoRA 修正：

\[
BAx
=
\begin{bmatrix}
-0.3\\
0.24
\end{bmatrix}
\]

于是：

\[
y
=
W_0x+BAx
\]

得到：

\[
y
=
\begin{bmatrix}
5\\
-2
\end{bmatrix}
+
\begin{bmatrix}
-0.3\\
0.24
\end{bmatrix}
\]

所以：

\[
\boxed{
y=
\begin{bmatrix}
4.7\\
-1.76
\end{bmatrix}
}
\]

LoRA 所做的事情其实非常朴素：

```text
原模型输出：

[ 5    ]
[-2    ]

LoRA说：
第一个输出应该稍微降低 0.3
第二个输出应该增加 0.24

所以：

[ 4.7  ]
[-1.76 ]
```

---

<a id="origin-3241"></a>
## 50. 那么训练的时候到底训练谁？

这是理解 LoRA 最重要的一点。

Full Fine-Tuning：

```text
W0
↓
计算 Loss
↓
反向传播
↓
更新 W0
```

而 LoRA：

```text
W0：冻结，不更新

A：训练
B：训练
```

因此：

\[
\boxed{
W_0\text{ frozen}
}
\]

而：

\[
\boxed{
A,B\text{ trainable}
}
\]

训练过程：

```text
                W0
                ↓
x ───────────→ Linear ───────┐
│                            │
│                            ↓
└→ A → B → ×α/r ───────────→ + → y
   ↑   ↑
   │   │
  更新 更新

W0 不更新
```

---

<a id="origin-3300"></a>
## 51. 为什么初始化的时候通常让 LoRA 不改变原模型？

假设刚开始训练就有：

\[
BA\ne0
\]

那么 LoRA 一装上去：

\[
W_0
\]

马上就被修改了。

但此时 LoRA 还什么都没学。

这显然不太合理。

因此经典 LoRA 中常见的初始化方式是：

\[
A=\text{随机小值}
\]

而：

\[
\boxed{
B=0
}
\]

这样：

\[
BA=0
\]

所以训练刚开始：

\[
y
=
W_0x+
\frac{\alpha}{r}0
\]

得到：

\[
\boxed{
y=W_0x
}
\]

也就是说：

> 刚安装 LoRA 时，模型行为和原模型完全一样。

然后再慢慢学习修正量。

---

<a id="origin-3365"></a>
## 52. 一个非常有意思的问题：如果 \(B=0\)，第一次反向传播怎么办？

很多人会问：

既然：

\[
B=0
\]

那：

\[
BA=0
\]

是不是 \(A,B\) 都学不动了？

不是。

假设：

\[
y
=
W_0x+sBAx
\]

其中：

\[
s=\frac{\alpha}{r}
\]

假设损失：

\[
L
\]

定义：

\[
g=
\frac{\partial L}{\partial y}
\]

---

<a id="origin-3414"></a>
### 52.1 对 \(B\) 求梯度

LoRA 部分：

\[
sB(Ax)
\]

所以：

\[
\boxed{
\frac{\partial L}{\partial B}
=
s\,g(Ax)^T
}
\]

这里即使：

\[
B=0
\]

只要：

\[
A\ne0
\]

那么：

\[
Ax\ne0
\]

通常就有：

\[
\frac{\partial L}{\partial B}\ne0
\]

因此第一次梯度下降：

\[
B
\]

就开始发生变化了。

---

<a id="origin-3466"></a>
## 53. 那第一次 \(A\) 会不会更新？

对 \(A\) 求梯度：

\[
\boxed{
\frac{\partial L}{\partial A}
=
sB^Tg x^T
}
\]

如果初始：

\[
B=0
\]

那么：

\[
\frac{\partial L}{\partial A}=0
\]

所以严格来说：

> 第一次反向传播时，\(B\) 先开始学习，而 \(A\) 的梯度可能是 0。

第一次更新之后：

\[
B\ne0
\]

后面的训练：

\[
\frac{\partial L}{\partial A}\ne0
\]

于是：

\[
A,B
\]

都会开始学习。

这一点非常适合理解 LoRA 初始化。

---

<a id="origin-3518"></a>
## 54. LoRA 和普通 Linear 到底是什么关系？

普通 Linear：

\[
y=W_0x
\]

LoRA Linear：

\[
\boxed{
y
=
W_0x+
\frac{\alpha}{r}BAx
}
\]

所以 LoRA 并不是把 Linear 换掉。

而是：

> 在原 Linear 旁边增加了一条很小的可训练分支。

可以画成：

```text
                    ┌──── W0 ────────┐
                    │                 │
x ──────────────────┤                 ├──→ +
                    │                 │     │
                    └─────────────────┘     │
                                            ├→ y
                    ┌─ A ─→ B ─→ α/r ─────┘
x ──────────────────┤
                    └─ LoRA branch
```

---

<a id="origin-3559"></a>
## 55. 放到 Transformer 的 Q 矩阵里看

原来的 Attention：

\[
Q=W_Qx
\]

假设：

\[
W_Q=W_{Q,0}
\]

LoRA 加进去以后：

\[
W_Q'
=
W_{Q,0}
+
\frac{\alpha}{r}B_QA_Q
\]

因此：

\[
Q
=
W_Q'x
\]

即：

\[
\boxed{
Q
=
W_{Q,0}x
+
\frac{\alpha}{r}B_QA_Qx
}
\]

原来的：

```text
hidden state
    ↓
   WQ
    ↓
    Q
```

现在：

```text
                 WQ，冻结
                 ↓
hidden state ───────────→ 原始 Q
      │
      │
      └→ A → B → α/r → Q 的修正量
                         ↓
                        相加
                         ↓
                        新 Q
```

---

<a id="origin-3630"></a>
## 56. LoRA 可以加在哪些地方？

Transformer 中常见：

\[
W_Q,W_K,W_V,W_O
\]

都可以加入 LoRA。

即：

```text
q_proj
k_proj
v_proj
o_proj
```

也可以加到 FFN：

```text
gate_proj
up_proj
down_proj
```

早期和很多常见配置经常只训练：

```text
q_proj
v_proj
```

现在实际使用中也经常看到：

```text
q_proj
k_proj
v_proj
o_proj
```

甚至：

```text
all linear
```

核心原理完全一样。

---

<a id="origin-3683"></a>
## 57. 用 hidden_size=4096 算一次真实参数量

假设：

\[
W_Q
\in
\mathbb{R}^{4096\times4096}
\]

Full Fine-Tuning：

\[
16,777,216
\]

个可训练参数。

---

LoRA：

\[
r=8
\]

那么：

\[
A_Q
:
4096\rightarrow8
\]

参数：

\[
4096\times8=32768
\]

而：

\[
B_Q
:
8\rightarrow4096
\]

参数：

\[
8\times4096=32768
\]

总共：

\[
65536
\]

---

假设同时给：

```text
q_proj
v_proj
```

加 LoRA。

一层：

\[
65536\times2
=
131072
\]

如果模型有：

\[
32
\]

层：

\[
131072\times32
=
4,194,304
\]

也就是：

\[
\boxed{
约419万个 LoRA 参数
}
\]

而如果这 32 层中的 Q、V 全量更新：

\[
4096^2\times2\times32
\]

得到：

\[
1,073,741,824
\]

约：

\[
\boxed{
10.74亿参数
}
\]

对比：

```text
Full：

约 10.74 亿


LoRA r=8：

约 419 万
```

相差约：

\[
256
\]

倍。

---

<a id="origin-3827"></a>
## 58. 为什么训练参数少会节省大量显存？

训练一个参数并不仅仅需要存：

\[
W
\]

通常还可能要保存：

```text
参数
梯度
Optimizer State
```

比如 Adam 类优化器还需要保存：

\[
m
\]

和：

\[
v
\]

所以如果几十亿参数全部训练：

```text
Parameter
Gradient
Adam m
Adam v
```

都非常昂贵。

LoRA 中：

\[
W_0
\]

被冻结。

因此最重要的是：

```text
W0：
保存，但不需要为它维护完整训练梯度和 optimizer states

A、B：
需要训练
需要梯度
需要 optimizer states
```

所以训练显存大幅降低。

注意：

> LoRA 主要减少的是“可训练参数以及相关优化器状态”，并不代表整个模型本体消失了。

原始大模型：

\[
W_0
\]

仍然需要存在。

---

<a id="origin-3902"></a>
## 59. LoRA 为什么还能单独保存？

训练结束以后：

\[
W_0
\]

根本没有变化。

真正发生变化的是：

\[
A,B
\]

所以保存模型时，可以只保存：

```text
A
B
LoRA config
```

例如：

```text
base model：几 GB、几十 GB

LoRA adapter：
几十 MB
几百 MB
```

因此同一个基础模型：

```text
             ┌→ 医疗 LoRA
Base Model ──┼→ 法律 LoRA
             ├→ 数学 LoRA
             ├→ 代码 LoRA
             └→ 客服 LoRA
```

不需要保存五份完整模型。

---

<a id="origin-3950"></a>
## 60. 推理的时候为什么可以把 LoRA 合并回去？

训练公式：

\[
y
=
W_0x+
\frac{\alpha}{r}BAx
\]

利用分配律：

\[
y
=
\left(
W_0+
\frac{\alpha}{r}BA
\right)x
\]

因此定义：

\[
\boxed{
W_{\text{merged}}
=
W_0+
\frac{\alpha}{r}BA
}
\]

那么：

\[
\boxed{
y=W_{\text{merged}}x
}
\]

所以部署时完全可以提前计算：

\[
W_{\text{merged}}
\]

然后把 LoRA 分支消掉。

于是推理结构又变回：

```text
x
↓
一个普通 Linear
↓
y
```

这就是：

<a id="origin-4011"></a>
## 61. LoRA Merge

---

<a id="origin-4015"></a>
## 62. 用刚才的数值例子演示 Merge

之前：

\[
A=
\begin{bmatrix}
0.1&-0.2&0.3
\end{bmatrix}
\]

\[
B=
\begin{bmatrix}
0.5\\
-0.4
\end{bmatrix}
\]

计算：

\[
BA
=
\begin{bmatrix}
0.5\\
-0.4
\end{bmatrix}
\begin{bmatrix}
0.1&-0.2&0.3
\end{bmatrix}
\]

得到：

\[
BA=
\begin{bmatrix}
0.05&-0.10&0.15\\
-0.04&0.08&-0.12
\end{bmatrix}
\]

原模型：

\[
W_0=
\begin{bmatrix}
1&2&0\\
-1&0&1
\end{bmatrix}
\]

所以：

\[
W_{\text{merged}}
=
W_0+BA
\]

得到：

\[
W_{\text{merged}}
=
\begin{bmatrix}
1.05&1.90&0.15\\
-1.04&0.08&0.88
\end{bmatrix}
\]

以后直接：

\[
y=W_{\text{merged}}x
\]

就可以了。

不需要再分别运行：

\[
W_0x
\]

和：

\[
BAx
\]

---

<a id="origin-4109"></a>
## 63. LoRA 的 Rank \(r\) 到底是什么意思？

假设：

\[
\Delta W=BA
\]

其中：

\[
r=1
\]

那么：

\[
\operatorname{rank}(\Delta W)\le1
\]

模型只能学一个主要修改方向。

---

如果：

\[
r=8
\]

那么：

\[
\operatorname{rank}(\Delta W)\le8
\]

最多可以学习 8 个独立方向。

---

如果：

\[
r=64
\]

模型的修改自由度进一步增加。

所以可以粗略理解成：

```text
r 小：
参数少
限制强
表达能力较低

r 大：
参数多
限制弱
表达能力较高
```

但是：

\[
r
\]

并不是越大越好。

因为当：

\[
r
\]

越来越大时：

```text
参数量 ↑
显存 ↑
计算量 ↑
LoRA 的参数高效优势 ↓
```

甚至最终越来越接近全量微调。

---

<a id="origin-4198"></a>
## 64. \(r\) 为什么不能直接等于 4096？

理论上当然可以。

如果：

\[
r=4096
\]

那么：

\[
A
\in
\mathbb{R}^{4096\times4096}
\]

\[
B
\in
\mathbb{R}^{4096\times4096}
\]

参数甚至变成：

\[
2\times4096^2
\]

这比直接训练一个：

\[
\Delta W
\]

还多。

所以 LoRA 的意义正是：

\[
\boxed{
r\ll d
}
\]

例如：

```text
r = 4
r = 8
r = 16
r = 32
r = 64
```

---

<a id="origin-4256"></a>
## 65. 一个非常直观的类比

假设一个人已经会：

```text
中文
数学
计算机
英语
历史
物理
……
```

这就是：

\[
W_0
\]

现在我们想让他学：

```text
浙江大学软件学院研究生招生问答
```

Full Fine-Tuning 相当于：

> 把这个人的整个大脑全部重新训练一遍。

LoRA 相当于：

> 保留原来的整个大脑，只增加一套很小的“专业知识修正规则”。

所以：

\[
W_0
\]

负责原来的通用能力，

而：

\[
BA
\]

负责：

```text
遇到这种新任务时，
原来的行为应该往哪个方向调整。
```

---

<a id="origin-4313"></a>
## 66. 从优化角度看 Full Fine-Tuning 和 LoRA 的区别

Full Fine-Tuning 优化：

\[
\min_W L(W)
\]

或者写成：

\[
\min_{\Delta W}
L(W_0+\Delta W)
\]

其中：

\[
\Delta W
\]

可以是任意矩阵。

---

LoRA 则增加了一个约束：

\[
\Delta W=BA
\]

所以优化变成：

\[
\boxed{
\min_{A,B}
L
\left(
W_0+
\frac{\alpha}{r}BA
\right)
}
\]

同时：

\[
W_0
\]

保持固定。

这其实就是 LoRA 最严格的数学定义：

> 不再直接优化一个巨大的 \(\Delta W\)，而是通过两个小矩阵 \(A,B\) 对它进行低秩参数化。

---

<a id="origin-4371"></a>
## 67. LoRA 和 SFT 是什么关系？

这两个东西不是同一个维度的概念。

SFT：

<a id="origin-4377"></a>
## 68. 监督微调的训练目标

例如：

```text
Prompt:
浙江大学软件学院在哪里？

Target:
浙江大学软件学院位于宁波。
```

计算：

\[
L_{\text{CE}}
\]

然后反向传播。

---

LoRA：

<a id="origin-4401"></a>
## 69. 决定哪些参数、以什么形式被更新

因此完全可以：

\[
\boxed{
SFT + LoRA
}
\]

训练流程：

```text
Prompt + Answer
      ↓
   Transformer
      ↓
 Cross Entropy Loss
      ↓
 Backpropagation
      ↓
只更新 LoRA 的 A、B
```

所以：

> SFT 回答“训练什么目标”，LoRA 回答“参数怎么更新得更省”。

---

<a id="origin-4431"></a>
## 70. 一个简单的 LoRA Linear 实现

理论公式：

\[
y
=
W_0x+
\frac{\alpha}{r}BAx
\]

PyTorch 中通常一个 batch 的输入写成行向量形式，所以实现时经常看到：

```python
base_output = self.base(x)

lora_output = self.lora_B(
    self.lora_A(x)
)

output = base_output + self.scaling * lora_output
```

本质仍然完全对应：

\[
W_0x+
\frac{\alpha}{r}BAx
\]

简单实现：

```python
class LoRALinear(nn.Module):
    def __init__(
        self,
        in_features,
        out_features,
        r=8,
        alpha=16
    ):
        super().__init__()

        # 原来的 Linear
        self.base = nn.Linear(
            in_features,
            out_features,
            bias=False
        )

        # 冻结原模型参数
        for p in self.base.parameters():
            p.requires_grad = False

        # A: d_in -> r
        self.lora_A = nn.Linear(
            in_features,
            r,
            bias=False
        )

        # B: r -> d_out
        self.lora_B = nn.Linear(
            r,
            out_features,
            bias=False
        )

        self.scaling = alpha / r

        # 常见初始化思想：
        # A 随机，B 为 0
        nn.init.normal_(
            self.lora_A.weight,
            std=0.02
        )
        nn.init.zeros_(
            self.lora_B.weight
        )

    def forward(self, x):

        base_output = self.base(x)

        lora_output = self.lora_B(
            self.lora_A(x)
        )

        return (
            base_output
            +
            self.scaling * lora_output
        )
```

---

<a id="origin-4528"></a>
## 71. 第一次 Forward 会发生什么？

因为：

```python
self.lora_B.weight = 0
```

所以：

\[
B=0
\]

于是：

\[
BAx=0
\]

因此：

```python
lora_output = 0
```

最终：

\[
y=W_0x
\]

所以刚装上 LoRA：

> 模型不会突然发生行为改变。

---

<a id="origin-4566"></a>
## 72. 第一次 Backward 会发生什么？

Loss：

\[
L
\]

进行：

```python
loss.backward()
```

因为：

```text
base.weight.requires_grad = False
```

所以：

\[
W_0
\]

不会获得需要优化的梯度。

而：

\[
A,B
\]

属于训练参数。

第一次由于：

\[
B=0
\]

主要先推动：

\[
B
\]

发生变化。

后续：

\[
A,B
\]

都会一起被训练。

---

<a id="origin-4626"></a>
## 73. 一整个 LoRA SFT 训练流程

完整流程可以记成：

```text
① 加载预训练模型

        W0


② 冻结原模型参数

        W0
      frozen


③ 给指定 Linear 增加 LoRA

          W0
           │
x ─────────┼────→
│
└→ A → B → α/r


④ 输入训练数据

Prompt + Target


⑤ Forward

y = W0x + α/r · BAx


⑥ 计算语言模型 Loss

Cross Entropy


⑦ Backward

∂L/∂A
∂L/∂B


⑧ Optimizer 更新

A ← A - η∇A L

B ← B - η∇B L


⑨ W0 不变


⑩ 训练完成，只保存 A、B


⑪ 推理时：

方式一：
W0 + LoRA adapter

方式二：
提前 merge

Wmerged = W0 + α/r · BA
```

---

<a id="origin-4698"></a>
## 74. 最后用一组公式把 LoRA 从头串起来

<a id="origin-4700"></a>
### 74.1 第一步：预训练模型

\[
y=W_0x
\]

---

<a id="origin-4708"></a>
### 74.2 第二步：普通微调

希望：

\[
W=W_0+\Delta W
\]

所以：

\[
y
=
W_0x+\Delta Wx
\]

---

<a id="origin-4726"></a>
### 74.3 第三步：发现 \(\Delta W\) 太大

\[
\Delta W
\in
\mathbb{R}^{d_{\text{out}}\times d_{\text{in}}}
\]

参数：

\[
d_{\text{out}}d_{\text{in}}
\]

---

<a id="origin-4742"></a>
### 74.4 第四步：假设参数变化是低秩的

\[
\operatorname{rank}(\Delta W)\le r
\]

其中：

\[
r\ll d
\]

---

<a id="origin-4756"></a>
### 74.5 第五步：低秩分解

\[
\boxed{
\Delta W=BA
}
\]

其中：

\[
A
\in
\mathbb{R}^{r\times d_{\text{in}}}
\]

\[
B
\in
\mathbb{R}^{d_{\text{out}}\times r}
\]

---

<a id="origin-4780"></a>
### 74.6 第六步：加入缩放

\[
\boxed{
\Delta W
=
\frac{\alpha}{r}BA
}
\]

---

<a id="origin-4792"></a>
### 74.7 第七步：最终 Forward

\[
\boxed{
y
=
W_0x+
\frac{\alpha}{r}BAx
}
\]

---

<a id="origin-4805"></a>
### 74.8 第八步：训练时

冻结：

\[
\boxed{W_0}
\]

只优化：

\[
\boxed{A,B}
\]

所以：

\[
\boxed{
\min_{A,B}
L
\left(
W_0+\frac{\alpha}{r}BA
\right)
}
\]

---

<a id="origin-4833"></a>
### 74.9 第九步：训练结束可以合并

\[
\boxed{
W_{\text{merged}}
=
W_0+
\frac{\alpha}{r}BA
}
\]

以后：

\[
\boxed{
y=W_{\text{merged}}x
}
\]

---

<a id="origin-4854"></a>
## 75. 最应该记住的一句话

LoRA 并不是把大模型原来的权重做低秩分解，而是认为：

\[
\boxed{
\text{微调真正需要学习的参数变化 }\Delta W
\text{ 可以是低秩的}
}
\]

因此把：

\[
\Delta W
\]

从一个巨大的矩阵：

\[
d_{\text{out}}\times d_{\text{in}}
\]

改写成：

\[
\boxed{
\Delta W
=
\frac{\alpha}{r}BA
}
\]

其中：

\[
d_{\text{in}}
\rightarrow r
\rightarrow d_{\text{out}}
\]

最终：

\[
\boxed{
W
=
W_0+
\frac{\alpha}{r}BA
}
\]

训练时：

\[
\boxed{
W_0\text{ 不动，只训练 }A,B
}
\]

这就是 LoRA 的本质。

---

<a id="origin-4918"></a>
## 76. 从特征值分解到奇异值分解 SVD

<a id="origin-4920"></a>
## 77. 先不要管 SVD：矩阵到底是什么？

先从最基本的概念开始。

一个矩阵：

\[
A
\]

可以理解为一个：

\[
\boxed{\text{线性变换}}
\]

例如：

\[
A=
\begin{bmatrix}
2&0\\
0&3
\end{bmatrix}
\]

给一个向量：

\[
x=
\begin{bmatrix}
x_1\\
x_2
\end{bmatrix}
\]

经过矩阵：

\[
Ax
\]

得到：

\[
Ax=
\begin{bmatrix}
2x_1\\
3x_2
\end{bmatrix}
\]

也就是说：

```text
横方向 ×2

纵方向 ×3
```

所以矩阵可以理解成：

> 把空间中的向量进行旋转、拉伸、压缩、翻转等操作。

---

<a id="origin-4986"></a>
## 78. 什么叫特征向量？

通常一个向量经过矩阵以后：

\[
x\rightarrow Ax
\]

方向会发生变化。

例如：

\[
x=
\begin{bmatrix}
1\\
1
\end{bmatrix}
\]

经过某个矩阵以后，可能变成：

\[
Ax=
\begin{bmatrix}
3\\
1
\end{bmatrix}
\]

方向已经变了。

但是，有一些非常特殊的方向：

> 经过矩阵以后，方向不变，只是长度发生变化。

这种方向就是：

\[
\boxed{\text{特征向量}}
\]

---

<a id="origin-5030"></a>
## 79. 特征向量的定义

如果存在：

\[
v\neq0
\]

使得：

\[
\boxed{
Av=\lambda v
}
\]

那么：

\[
v
\]

叫做矩阵 \(A\) 的特征向量，

而：

\[
\lambda
\]

叫做对应的特征值。

---

<a id="origin-5064"></a>
## 80. 一个非常简单的例子

假设：

\[
A=
\begin{bmatrix}
2&0\\
0&3
\end{bmatrix}
\]

看向量：

\[
v_1=
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

计算：

\[
Av_1
=
\begin{bmatrix}
2&0\\
0&3
\end{bmatrix}
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

得到：

\[
\begin{bmatrix}
2\\
0
\end{bmatrix}
\]

也就是：

\[
Av_1
=
2
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

所以：

\[
\boxed{\lambda_1=2}
\]

而：

\[
v_1
=
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

就是一个特征向量。

---

再看：

\[
v_2=
\begin{bmatrix}
0\\
1
\end{bmatrix}
\]

有：

\[
Av_2
=
\begin{bmatrix}
0\\
3
\end{bmatrix}
\]

也就是：

\[
Av_2=3v_2
\]

所以：

\[
\boxed{\lambda_2=3}
\]

---

<a id="origin-5178"></a>
## 81. 特征值意味着什么？

对于：

\[
Av=\lambda v
\]

可以理解成：

```text
v 是一个特殊方向

矩阵 A 作用以后：

方向不变

长度 × λ
```

例如：

\[
\lambda=3
\]

表示：

> 这个方向被放大 3 倍。

如果：

\[
\lambda=0.5
\]

表示：

> 这个方向缩小到原来的 0.5 倍。

如果：

\[
\lambda=-2
\]

表示：

> 长度放大 2 倍，同时方向反转。

---

<a id="origin-5230"></a>
## 82. 那么特征值怎么计算？

假设：

\[
Av=\lambda v
\]

移项：

\[
Av-\lambda v=0
\]

注意：

\[
\lambda v
=
\lambda Iv
\]

所以：

\[
(A-\lambda I)v=0
\]

如果：

\[
v\neq0
\]

那么矩阵：

\[
A-\lambda I
\]

必须不能可逆。

因此：

\[
\boxed{
\det(A-\lambda I)=0
}
\]

这就是特征方程。

---

<a id="origin-5284"></a>
## 83. 从行列式到特征方程：为什么 $\det(A-\lambda I)=0$？

> **本节学习目标：** 不预先假设读者记得线性代数。从“行列式是什么”开始，理解行列式、可逆矩阵、齐次方程的非零解以及特征值之间的关系。重点不是记住四个结论，而是知道这些结论为什么可以连起来。

---

<a id="origin-5290"></a>
### 83.1 一、行列式（Determinant）到底是什么？

<a id="origin-5292"></a>
## 84. 先区分矩阵和行列式

一个矩阵可以写成：

$$
A=\begin{bmatrix}a&b\\c&d\end{bmatrix}.
$$

矩阵 $A$ 是一个由数字组成的表格；当我们把它看作线性变换时，它表示如何把输入向量 $x$ 变成输出向量 $Ax$。

**行列式** $\det(A)$ 则是通过这个**方阵**计算出来的**一个数**，而不是另一个矩阵。二维情形：

$$
\boxed{\det(A)=\begin{vmatrix}a&b\\c&d\end{vmatrix}=ad-bc.}
$$

注意记号区别：

- $\begin{bmatrix}a&b\\c&d\end{bmatrix}$ 表示矩阵。
- $\begin{vmatrix}a&b\\c&d\end{vmatrix}$ 表示这个矩阵的行列式，其结果是标量 $ad-bc$。

行列式只对**方阵**定义。我们先用二维理解，再推广到三维和更高维。

<a id="origin-5315"></a>
## 85. 为什么二维行列式是 $ad-bc$？

把矩阵按列写成两个向量：

$$
A=\begin{bmatrix}|&|\\u&v\\|&|\end{bmatrix},\qquad
u=\begin{bmatrix}a\\c\end{bmatrix},\quad
v=\begin{bmatrix}b\\d\end{bmatrix}.
$$

矩阵 $A$ 把二维坐标系中的两个单位基向量变成：

$$
Ae_1=u,\qquad Ae_2=v.
$$

原来由 $e_1,e_2$ 围成的单位正方形，变换后成为由 $u,v$ 围成的平行四边形。这个平行四边形的**有向面积**就是：

$$
\det(A)=ad-bc.
$$

因此，行列式有一个极其重要的几何含义：

$$
\boxed{|\det(A)|=\text{矩阵 }A\text{ 对二维面积的缩放倍数}.}
$$

其中绝对值表示面积大小；正负号表示方向是否发生翻转。

- $|\det(A)|=2$：面积变成原来的两倍。
- $|\det(A)|=\tfrac12$：面积变成原来的一半。
- $\det(A)<0$：除了面积缩放，还发生了方向翻转。
- **$\det(A)=0$：单位正方形的面积被压缩为零。**

对于三维，$|\det(A)|$ 代表体积缩放倍数；在 $n$ 维则对应 $n$ 维体积的缩放倍数。


<a id="origin-5353"></a>
## 86. 补充：行列式的几何意义——\(e_1,e_2,u,v\) 分别是什么？

<a id="origin-5355"></a>
## 87. 首先，\(e_1,e_2\) 是什么？

在二维坐标系中，我们通常定义两个标准单位向量：

\[
e_1=
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

\[
e_2=
\begin{bmatrix}
0\\
1
\end{bmatrix}
\]

其中：

- \(e_1\)：沿着 x 轴正方向走 1 个单位。
- \(e_2\)：沿着 y 轴正方向走 1 个单位。

从原点出发，利用这两个向量，可以构造出一个单位正方形。

这个正方形的四个顶点分别是：

\[
(0,0),\quad(1,0),\quad(0,1),\quad(1,1)
\]

其中：

- \(e_1\) 构成正方形的底边。
- \(e_2\) 构成正方形的左边。

所以正方形的面积为：

\[
S=1\times1=1
\]

**我们可以理解为：\(e_1,e_2\) 是变换之前的两个单位向量，它们共同确定了原来的单位正方形。**

---

<a id="origin-5403"></a>
## 88. 用矩阵 A 变换这两个向量

假设有一个矩阵：

\[
A=
\begin{bmatrix}
2&1\\
0&2
\end{bmatrix}
\]

矩阵 \(A\) 可以理解为一种线性变换规则：

\[
y=Ax
\]

即给定一个向量 \(x\)，通过矩阵乘法，将其变换成一个新向量 \(y\)。

现在分别对 \(e_1,e_2\) 进行变换。

<a id="origin-5425"></a>
### 88.1 变换第一个向量 \(e_1\)

定义变换后的向量为：

\[
u=Ae_1
\]

代入：

\[
u=
\begin{bmatrix}
2&1\\
0&2
\end{bmatrix}
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

进行矩阵乘法：

\[
u=
\begin{bmatrix}
2\times1+1\times0\\
0\times1+2\times0
\end{bmatrix}
\]

得到：

\[
\boxed{
u=
\begin{bmatrix}
2\\
0
\end{bmatrix}
}
\]

也就是说，原来：

\[
e_1=(1,0)
\]

经过矩阵 \(A\) 变换以后，变成：

\[
u=(2,0)
\]

原来沿 x 轴走 1 个单位，现在变成走 2 个单位。

<a id="origin-5483"></a>
### 88.2 变换第二个向量 \(e_2\)

同样定义：

\[
v=Ae_2
\]

代入：

\[
v=
\begin{bmatrix}
2&1\\
0&2
\end{bmatrix}
\begin{bmatrix}
0\\
1
\end{bmatrix}
\]

计算：

\[
v=
\begin{bmatrix}
2\times0+1\times1\\
0\times0+2\times1
\end{bmatrix}
\]

得到：

\[
\boxed{
v=
\begin{bmatrix}
1\\
2
\end{bmatrix}
}
\]

所以：

\[
e_2=(0,1)
\]

经过变换以后：

\[
v=(1,2)
\]

即原来向上走 1 个单位，现在变成向右走 1 个单位、向上走 2 个单位。

<a id="origin-5541"></a>
### 88.3 总结

| 变换之前 | 变换之后 |
|---|---|
| \(e_1=(1,0)^T\) | \(u=(2,0)^T\) |
| \(e_2=(0,1)^T\) | \(v=(1,2)^T\) |

**注意一个重要规律：**

变换后的：

\[
u=
\begin{bmatrix}
2\\
0
\end{bmatrix}
\]

恰好是矩阵 \(A\) 的第一列。

而：

\[
v=
\begin{bmatrix}
1\\
2
\end{bmatrix}
\]

恰好是矩阵 \(A\) 的第二列。

因此，对于任意二维矩阵：

\[
A=
\begin{bmatrix}
a&b\\
c&d
\end{bmatrix}
\]

都有：

\[
\boxed{
Ae_1=
\begin{bmatrix}
a\\
c
\end{bmatrix}
}
\]

\[
\boxed{
Ae_2=
\begin{bmatrix}
b\\
d
\end{bmatrix}
}
\]

**也就是说，矩阵的每一列，实际上就是对应标准单位向量经过变换后的结果。**

---

<a id="origin-5610"></a>
## 89. 原来的单位正方形变成了什么？

原来的单位正方形由两个向量：

\[
e_1=(1,0)
\]

\[
e_2=(0,1)
\]

构成。

四个顶点：

\[
O=(0,0)
\]

\[
e_1=(1,0)
\]

\[
e_2=(0,1)
\]

\[
e_1+e_2=(1,1)
\]

经过矩阵 \(A\) 变换以后：

\[
Ae_1=u=(2,0)
\]

\[
Ae_2=v=(1,2)
\]

因为矩阵乘法满足：

\[
A(e_1+e_2)=Ae_1+Ae_2
\]

所以第四个顶点变成：

\[
u+v=(3,2)
\]

最终，变换后的四个顶点为：

\[
(0,0),\quad(2,0),\quad(1,2),\quad(3,2)
\]

这四个点构成一个平行四边形。

其中：

- 底边向量是 \(u=(2,0)\)。
- 另一条边向量是 \(v=(1,2)\)。
- 底边长度为 2。
- 对应的高度为 2。

因此平行四边形面积：

\[
S=2\times2=4
\]

即：

\[
\boxed{S=4}
\]

注意：

**这里的平行四边形不是随意选择的，而是原来由 \(e_1,e_2\) 构成的单位正方形经过矩阵 A 变换后得到的。**

---

<a id="origin-5697"></a>
## 90. 这时候行列式有什么意义？

回到矩阵：

\[
A=
\begin{bmatrix}
2&1\\
0&2
\end{bmatrix}
\]

根据二维行列式公式：

\[
\det
\begin{bmatrix}
a&b\\
c&d
\end{bmatrix}
=ad-bc
\]

得到：

\[
\det(A)=2\times2-1\times0
\]

所以：

\[
\boxed{\det(A)=4}
\]

再来看面积：

原来的单位正方形：

\[
S_{\text{原来}}=1
\]

经过矩阵变换后的平行四边形：

\[
S_{\text{变换后}}=4
\]

面积放大倍数：

\[
\frac{S_{\text{变换后}}}{S_{\text{原来}}}
=
\frac41=4
\]

恰好等于：

\[
\boxed{\det(A)=4}
\]

这并不是巧合。

**行列式的几何意义，就是矩阵对应的线性变换对面积或体积的有符号缩放倍数。**

对于二维矩阵：

\[
\boxed{
S_{\text{变换后}}
=
|\det(A)|S_{\text{原来}}
}
\]

由于我们选择的原始正方形面积恰好为 1，因此：

\[
\boxed{
S_{\text{变换后}}=|\det(A)|
}
\]

---

<a id="origin-5784"></a>
## 91. 为什么说是“有向面积”？

普通面积不可能是负数。

但是行列式可以是：

\[
\det(A)>0
\]

也可以是：

\[
\det(A)<0
\]

因此，行列式不完全等于普通面积，而是**有向面积**。

它同时包含两个信息：

1. 绝对值表示面积缩放倍数。
2. 正负号表示空间的方向是否发生翻转。

具体来说：

<a id="origin-5809"></a>
### 91.1 情况一：行列式为正

\[
\det(A)>0
\]

说明变换保持了方向。

面积缩放倍数为：

\[
|\det(A)|
\]

<a id="origin-5823"></a>
#### 91.1.1 情况二：行列式为负

\[
\det(A)<0
\]

说明变换使方向发生了翻转，例如镜像反射。

实际面积缩放倍数仍然为：

\[
|\det(A)|
\]

例如：

\[
\det(A)=-4
\]

并不是说面积是负 4，而是：

- 面积扩大了 4 倍。
- 空间方向发生了翻转。

所以：

\[
\boxed{
\text{实际面积}=|\det(A)|
}
\]

对于原始单位正方形，其有向面积才是：

\[
\boxed{
\det(A)
}
\]

---

<a id="origin-5866"></a>
## 92. 为什么行列式为 0 就意味着不可逆？

现在我们已经知道：

\[
|\det(A)|
\]

表示二维空间中的面积缩放倍数。

如果：

\[
\det(A)=0
\]

就意味着：

\[
S_{\text{变换后}}=0
\]

也就是说：

**原本面积为 1 的正方形，经过矩阵变换以后，被压缩成了面积为 0 的形状。**

例如：

- 原来的二维正方形被压成一条直线。
- 或者整个正方形被压成一个点。

这意味着原来的两个独立方向不再独立。

也就是：

\[
u=Ae_1
\]

和：

\[
v=Ae_2
\]

变成了线性相关的向量。

这时，原来二维空间里的不同点可能被映射到同一个位置。

因此：

\[
y=Ax
\]

不能再根据输出 \(y\) 唯一恢复原来的输入 \(x\)。

所以矩阵没有逆矩阵。

由此可以直观理解：

\[
\boxed{
\det(A)=0
\Rightarrow A\text{ 不可逆}
}
\]

对于方阵，更严格的数学结论是：

\[
\boxed{
\det(A)=0
\iff A\text{ 不可逆}
}
\]


<a id="origin-5944"></a>
### 92.1 补充：为什么行列式为 0，就无法根据输出唯一恢复输入？

我们通过一个具体例子，理解为什么：

\[
\det(A)=0
\]

意味着矩阵不可逆。

<a id="origin-5954"></a>
## 93. 假设有一个矩阵 A

\[
A=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

首先计算行列式：

\[
\det(A)=1\times4-2\times2=0
\]

因此：

\[
\boxed{\det(A)=0}
\]

这说明矩阵 \(A\) 不可逆。

但为什么不可逆？我们直接计算两个不同的输入。

<a id="origin-5980"></a>
## 94. 第一个输入

假设：

\[
x_1=
\begin{bmatrix}
2\\
1
\end{bmatrix}
\]

执行矩阵变换：

\[
y_1=Ax_1
\]

代入：

\[
y_1=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\begin{bmatrix}
2\\
1
\end{bmatrix}
\]

得到：

\[
y_1=
\begin{bmatrix}
1\times2+2\times1\\
2\times2+4\times1
\end{bmatrix}
=
\begin{bmatrix}
4\\
8
\end{bmatrix}
\]

因此：

\[
\boxed{
y_1=
\begin{bmatrix}
4\\
8
\end{bmatrix}
}
\]

<a id="origin-6039"></a>
## 95. 第二个输入

现在换一个完全不同的输入：

\[
x_2=
\begin{bmatrix}
4\\
0
\end{bmatrix}
\]

执行同样的矩阵变换：

\[
y_2=Ax_2
\]

代入：

\[
y_2=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\begin{bmatrix}
4\\
0
\end{bmatrix}
\]

得到：

\[
y_2=
\begin{bmatrix}
1\times4+2\times0\\
2\times4+4\times0
\end{bmatrix}
=
\begin{bmatrix}
4\\
8
\end{bmatrix}
\]

因此：

\[
\boxed{
y_2=
\begin{bmatrix}
4\\
8
\end{bmatrix}
}
\]

<a id="origin-6098"></a>
## 96. 为什么这说明矩阵不可逆？

我们发现：

两个输入完全不同：

\[
x_1=
\begin{bmatrix}
2\\1
\end{bmatrix}
\neq
\begin{bmatrix}
4\\0
\end{bmatrix}
=x_2
\]

但是它们经过同一个矩阵 \(A\) 变换以后：

\[
Ax_1=
\begin{bmatrix}
4\\8
\end{bmatrix}
\]

\[
Ax_2=
\begin{bmatrix}
4\\8
\end{bmatrix}
\]

也就是说：

\[
\boxed{
x_1\neq x_2,\qquad Ax_1=Ax_2
}
\]

现在假设我们只知道输出：

\[
y=
\begin{bmatrix}
4\\8
\end{bmatrix}
\]

那么原来的输入究竟是什么？

可能是：

\[
x_1=
\begin{bmatrix}
2\\1
\end{bmatrix}
\]

也可能是：

\[
x_2=
\begin{bmatrix}
4\\0
\end{bmatrix}
\]

甚至还有无穷多个可能的输入。

因此，我们无法根据输出 \(y\) 唯一恢复输入 \(x\)。

这就意味着矩阵 \(A\) 不可逆。

<a id="origin-6175"></a>
## 97. 为什么会发生这种情况？

观察矩阵乘法：

\[
y=Ax
\]

令：

\[
x=
\begin{bmatrix}
a\\b
\end{bmatrix}
\]

那么：

\[
y=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\begin{bmatrix}
a\\b
\end{bmatrix}
\]

得到：

\[
y=
\begin{bmatrix}
a+2b\\
2a+4b
\end{bmatrix}
\]

注意：

\[
2a+4b=2(a+2b)
\]

因此，第二个输出分量永远是第一个输出分量的两倍。

即：

\[
\boxed{
y_2=2y_1
}
\]

这说明虽然输出包含两个数字，但这两个数字并不独立。

原来的输入有两个独立分量：

\[
a,b
\]

而输出实际上只保留了：

\[
a+2b
\]

这一个独立信息。

因此，原来二维空间中的信息被压缩到了一维。

**从几何上看，整个二维平面被矩阵 A 压缩到直线 \(y_2=2y_1\) 上。**

由于不同输入可能对应同一个输出，所以无法恢复原来的输入。

<a id="origin-6253"></a>
## 98. 为什么这也意味着存在非零向量被映射为 0？

既然：

\[
Ax_1=Ax_2
\]

两边相减：

\[
Ax_1-Ax_2=0
\]

利用矩阵乘法的分配律：

\[
A(x_1-x_2)=0
\]

令：

\[
v=x_1-x_2
\]

由于：

\[
x_1\neq x_2
\]

因此：

\[
v\neq0
\]

于是：

\[
\boxed{
Av=0,\qquad v\neq0
}
\]

在这个例子里：

\[
v=
\begin{bmatrix}
2\\1
\end{bmatrix}
-
\begin{bmatrix}
4\\0
\end{bmatrix}
=
\begin{bmatrix}
-2\\1
\end{bmatrix}
\]

验证：

\[
Av=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\begin{bmatrix}
-2\\1
\end{bmatrix}
\]

\[
=
\begin{bmatrix}
-2+2\\
-4+4
\end{bmatrix}
=
\begin{bmatrix}
0\\0
\end{bmatrix}
\]

所以确实存在：

\[
\boxed{
v\neq0,\qquad Av=0
}
\]

这个结论非常重要，因为它正好可以用来解释特征方程。

<a id="origin-6351"></a>
## 99. 最终总结

这个矩阵：

\[
A=
\begin{bmatrix}
1&2\\
2&4
\end{bmatrix}
\]

满足：

\[
\det(A)=0
\]

这意味着：

1. 矩阵的两列线性相关。
2. 二维空间被压缩到更低维度。
3. 不同输入可能得到相同输出。
4. 无法根据输出唯一恢复输入。
5. 存在非零向量 \(v\)，使得 \(Av=0\)。
6. 因此矩阵不可逆。

对于任意方阵 \(A\)，这些条件可以归纳为：

\[
\boxed{
\det(A)=0
\iff
A\text{ 不可逆}
\iff
\exists v\neq0,\ Av=0
}
\]

**一句话总结：矩阵不可逆，并不是说矩阵不能进行乘法，而是说矩阵变换丢失了信息，导致我们无法根据输出唯一恢复输入。**

这也是为什么后面求特征值时：

\[
(A-\lambda I)v=0,\qquad v\neq0
\]

必须要求：

\[
\boxed{
\det(A-\lambda I)=0
}
\]


---

<a id="origin-6409"></a>
## 100. 最终总结：\(e_1,e_2,u,v\) 与行列式是什么关系？

对于二维矩阵：

\[
A=
\begin{bmatrix}
a&b\\
c&d
\end{bmatrix}
\]

首先定义两个标准单位向量：

\[
e_1=
\begin{bmatrix}
1\\0
\end{bmatrix},
\qquad
e_2=
\begin{bmatrix}
0\\1
\end{bmatrix}
\]

它们构成一个面积为 1 的正方形。

然后使用矩阵 \(A\) 进行变换：

\[
u=Ae_1=
\begin{bmatrix}
a\\c
\end{bmatrix}
\]

\[
v=Ae_2=
\begin{bmatrix}
b\\d
\end{bmatrix}
\]

这两个新向量构成一个平行四边形。

该平行四边形的有向面积为：

\[
\boxed{
\det(A)=ad-bc
}
\]

普通面积为：

\[
\boxed{
S=|ad-bc|
}
\]

所以我们最终可以这样理解行列式：

> 行列式并不是凭空定义出来的一个计算公式。它具有明确的几何意义：描述矩阵所代表的线性变换，会把空间中的面积或体积放大、缩小多少倍，以及是否翻转方向。

而当：

\[
\boxed{
\det(A)=0
}
\]

就说明原来的空间被压缩到更低维度，某些信息无法恢复，因此矩阵不可逆。

这也为后面理解特征方程：

\[
\boxed{
\det(A-\lambda I)=0
}
\]

提供了几何基础。


<a id="origin-6496"></a>
## 101. 为什么 $\det(A)=0$ 很特殊？

如果二维行列式等于零，变换后的平行四边形面积为零。这意味着它的两条边没有撑开一个二维区域：两个列向量在同一条直线上，或者至少有一个是零向量。

也就是说，矩阵的列向量**线性相关**。存在不全为零的系数 $x_1,x_2$，满足：

$$
 x_1u+x_2v=0.
$$

把系数写成一个向量：

$$
 x=\begin{bmatrix}x_1\\x_2\end{bmatrix}\ne0,
$$

上面的式子就等于：

$$
\boxed{Ax=0,\qquad x\ne0.}
$$

**这一步很关键：行列式为零意味着存在一个非零的输入方向，被矩阵直接压成了零向量。**

更高维的情况也是一样：$\det(A)=0$ 等价于列向量线性相关，也等价于存在非零向量 $x$ 使得 $Ax=0$。

---

<a id="origin-6524"></a>
### 101.1 二、什么叫矩阵可逆？为什么行列式为零就不可逆？

<a id="origin-6526"></a>
## 102. “可逆”的定义

如果矩阵 $A$ 存在一个矩阵 $A^{-1}$，使得：

$$
AA^{-1}=A^{-1}A=I,
$$

就称 $A$ **可逆**。其中 $I$ 是单位矩阵，满足 $Ix=x$。

从输入输出的角度看：

$$
y=Ax\quad\Longrightarrow\quad x=A^{-1}y.
$$

即：**知道输出 $y$，就能够唯一找回输入 $x$。**

<a id="origin-6544"></a>
## 103. 为什么存在非零的 $x$ 满足 $Ax=0$，就不可能可逆？

假设存在：

$$
x\ne0,\qquad Ax=0.
$$

另一方面，任何矩阵都满足：

$$
A0=0.
$$

于是我们发现两个**不同的输入**：

$$
x\ne0\qquad\text{和}\qquad0
$$

竟然有相同的输出：

$$
Ax=A0=0.
$$

只看输出 $0$，已经无法判断输入到底是 $x$ 还是 $0$，因此不可能存在能“唯一还原”的逆变换。

也可以用代数直接证明：如果 $A$ 可逆，则将 $Ax=0$ 左乘 $A^{-1}$：

$$
A^{-1}Ax=A^{-1}0
\quad\Longrightarrow\quad x=0,
$$

这与 $x\ne0$ 矛盾。

结合上一节，就得到：

$$
\boxed{\det(A)=0\quad\Longrightarrow\quad A\text{ 不可逆}.}
$$

<a id="origin-6587"></a>
## 104. 反过来，为什么行列式不为零就可逆？

对二维矩阵：

$$
A=\begin{bmatrix}a&b\\c&d\end{bmatrix},
$$

当 $ad-bc\ne0$ 时，可以直接写出逆矩阵：

$$
\boxed{
A^{-1}=\frac{1}{ad-bc}
\begin{bmatrix}d&-b\\-c&a\end{bmatrix}.
}
$$

把它与 $A$ 相乘，可以验证结果就是单位矩阵 $I$。因此二维情况下，$\det(A)\ne0$ 确实保证可逆。

对更高维方阵，也有相应的伴随矩阵公式：

$$
A^{-1}=\frac{\operatorname{adj}(A)}{\det(A)}
\qquad (\det(A)\ne0).
$$

所以，对任意方阵，有完整的等价关系：

$$
\boxed{
\det(A)=0
\iff A\text{ 不可逆}
\iff \exists x\ne0,\ Ax=0.
}
$$

这个结论是理解特征方程的关键桥梁。

---

<a id="origin-6627"></a>
### 104.1 三、为什么特征值需要让 $A-\lambda I$ 不可逆？

<a id="origin-6629"></a>
## 105. 从特征值、特征向量的定义开始

如果存在一个**非零向量** $v$ 和一个数 $\lambda$，使得：

$$
\boxed{Av=\lambda v,\qquad v\ne0,}
$$

则称 $\lambda$ 是矩阵 $A$ 的**特征值**，$v$ 是与它对应的**特征向量**。

含义：一般情况下，矩阵变换可能改变一个向量的方向和长度；但对于特征向量 $v$，变换 $Av$ 的结果只是把 $v$ 乘上一个数 $\lambda$（可能伸缩、反向或变成零）。

**为什么必须要求 $v\ne0$？** 因为 $A0=\lambda0=0$ 对任意 $\lambda$ 都成立。如果允许零向量，所有数字都能“满足定义”，就无法区分真正的特征值。

<a id="origin-6643"></a>
## 106. 整理成一个齐次线性方程

从定义出发：

$$
Av=\lambda v.
$$

因为 $Iv=v$，所以 $\lambda v=\lambda Iv$，于是：

$$
Av-\lambda Iv=0.
$$

提取公共的 $v$：

$$
\boxed{(A-\lambda I)v=0,\qquad v\ne0.}
$$

此时，$\lambda$ 是否是特征值就转化成了另一个问题：

> **对于矩阵 $A-\lambda I$，方程 $(A-\lambda I)v=0$ 能否找到非零解？**

<a id="origin-6667"></a>
## 107. 为什么 $A-\lambda I$ 不可能可逆？

用反证法。假设 $A-\lambda I$ 可逆，那么：

$$
(A-\lambda I)v=0
$$

两边左乘 $(A-\lambda I)^{-1}$：

$$
(A-\lambda I)^{-1}(A-\lambda I)v
=(A-\lambda I)^{-1}0.
$$

左边化成 $Iv$，右边还是零：

$$
v=0.
$$

然而特征向量定义要求 $v\ne0$，矛盾！所以：

$$
\boxed{A-\lambda I\text{ 必须不可逆}.}
$$

**要特别区分：不可逆的是 $A-\lambda I$，而不一定是原矩阵 $A$。** 原矩阵本身完全可以可逆，同时具有特征值。

<a id="origin-6696"></a>
## 108. 为什么就得到特征方程？

第二节已经得出：

$$
M\text{ 不可逆}\iff\det(M)=0.
$$

把其中的 $M$ 换成 $A-\lambda I$：

$$
A-\lambda I\text{ 不可逆}
\iff\det(A-\lambda I)=0.
$$

因此：

$$
\boxed{\det(A-\lambda I)=0.}
$$

这就是**特征方程**。它不是人为规定的，而是从“特征向量必须非零”严格推出来的。

---

<a id="origin-6721"></a>
### 108.1 四、特征方程具体在求什么？

不代入具体数字，只用一个一般的 $2\times2$ 方阵观察公式：

$$
A=\begin{bmatrix}a&b\\c&d\end{bmatrix},
\qquad
I=\begin{bmatrix}1&0\\0&1\end{bmatrix}.
$$

先计算：

$$
A-\lambda I=
\begin{bmatrix}a-\lambda&b\\c&d-\lambda\end{bmatrix}.
$$

再取行列式：

$$
\begin{aligned}
\det(A-\lambda I)
&=(a-\lambda)(d-\lambda)-bc\\
&=\lambda^2-(a+d)\lambda+(ad-bc).
\end{aligned}
$$

令其等于零：

$$
\boxed{\lambda^2-(a+d)\lambda+(ad-bc)=0.}
$$

现在我们得到的是一个**关于 $\lambda$ 的二次方程**。求出它的根，就是特征值；再把求出的 $\lambda$ 代回：

$$
(A-\lambda I)v=0,
$$

就可以找到对应的非零特征向量。

在更高维时，$\det(A-\lambda I)=0$ 形成的多项式通常是 $n$ 次的（对于 $n\times n$ 方阵）。在复数范围内按代数重数计算有 $n$ 个根；在实数范围内则不一定全是实数根。

---

<a id="origin-6766"></a>
### 108.2 五、把全过程连成一条逻辑链

```text
行列式 det(M) 是一个数
    ↓
|det(M)| 描述线性变换对面积/体积的缩放
    ↓
det(M) = 0
    ↓
空间至少有一个方向被“压扁”
    ↓
存在非零向量 x，使得 Mx = 0
    ↓
两个不同输入可以得到相同输出
    ↓
M 不可逆

——————————————————————————————————

特征值定义：Av = λv，且 v ≠ 0
    ↓
移项：(A - λI)v = 0
    ↓
它需要一个非零解 v
    ↓
A - λI 必须不可逆
    ↓
det(A - λI) 必须等于 0
    ↓
解特征方程 det(A - λI) = 0
    ↓
得到特征值 λ
```

**最值得记住的两个结论：**

$$
\boxed{\det(M)=0\iff M\text{ 不可逆}\iff Mx=0\text{ 存在非零解}.}
$$

$$
\boxed{\lambda\text{ 是 }A\text{ 的特征值}\iff\det(A-\lambda I)=0.}
$$

**一句话总结：** 行列式为零意味着某个方向的信息在矩阵变换后消失，因此矩阵不可逆；而特征值的定义要求 $(A-\lambda I)v=0$ 有非零解，所以必须让 $A-\lambda I$ 的行列式为零。


---

<a id="origin-6815"></a>
## 109. 手算一个特征值例子

假设：

\[
A=
\begin{bmatrix}
2&1\\
1&2
\end{bmatrix}
\]

求：

\[
\det(A-\lambda I)=0
\]

首先：

\[
A-\lambda I
=
\begin{bmatrix}
2-\lambda&1\\
1&2-\lambda
\end{bmatrix}
\]

行列式：

\[
(2-\lambda)^2-1=0
\]

展开：

\[
4-4\lambda+\lambda^2-1=0
\]

所以：

\[
\lambda^2-4\lambda+3=0
\]

因式分解：

\[
(\lambda-1)(\lambda-3)=0
\]

所以：

\[
\boxed{\lambda_1=3}
\]

\[
\boxed{\lambda_2=1}
\]

---

<a id="origin-6880"></a>
## 110. 求第一个特征向量

对于：

\[
\lambda_1=3
\]

有：

\[
(A-3I)v=0
\]

即：

\[
\begin{bmatrix}
-1&1\\
1&-1
\end{bmatrix}
\begin{bmatrix}
x\\
y
\end{bmatrix}
=0
\]

得到：

\[
-x+y=0
\]

所以：

\[
x=y
\]

可以取：

\[
v_1=
\begin{bmatrix}
1\\
1
\end{bmatrix}
\]

如果归一化：

\[
\boxed{
v_1=
\frac1{\sqrt2}
\begin{bmatrix}
1\\
1
\end{bmatrix}
}
\]

---

<a id="origin-6945"></a>
## 111. 第二个特征向量

对于：

\[
\lambda_2=1
\]

有：

\[
(A-I)v=0
\]

也就是：

\[
\begin{bmatrix}
1&1\\
1&1
\end{bmatrix}
\begin{bmatrix}
x\\
y
\end{bmatrix}
=0
\]

所以：

\[
x+y=0
\]

即：

\[
y=-x
\]

因此可以取：

\[
v_2=
\begin{bmatrix}
1\\
-1
\end{bmatrix}
\]

归一化：

\[
\boxed{
v_2=
\frac1{\sqrt2}
\begin{bmatrix}
1\\
-1
\end{bmatrix}
}
\]

---

<a id="origin-7010"></a>
## 112. 什么叫特征值分解？

现在有：

\[
v_1,v_2
\]

以及：

\[
\lambda_1,\lambda_2
\]

把特征向量放进矩阵：

\[
P=
\begin{bmatrix}
|&|\\
v_1&v_2\\
|&|
\end{bmatrix}
\]

把特征值放到对角矩阵：

\[
\Lambda=
\begin{bmatrix}
\lambda_1&0\\
0&\lambda_2
\end{bmatrix}
\]

那么：

\[
\boxed{
A=P\Lambda P^{-1}
}
\]

这就是：

\[
\boxed{\text{Eigenvalue Decomposition}}
\]

特征值分解。

---

<a id="origin-7063"></a>
## 113. 这个公式是什么意思？

\[
A=P\Lambda P^{-1}
\]

计算：

\[
Ax
=
P\Lambda P^{-1}x
\]

从右向左看。

第一步：

\[
P^{-1}x
\]

把原来的向量转换到：

\[
v_1,v_2
\]

这组特殊坐标系里面。

第二步：

\[
\Lambda
\]

分别进行：

\[
v_1方向\times\lambda_1
\]

\[
v_2方向\times\lambda_2
\]

第三步：

\[
P
\]

再转换回原来的坐标系。

所以：

\[
\boxed{
A=P\Lambda P^{-1}
}
\]

的本质其实就是：

```text
换到特征向量坐标系
        ↓
每个方向单独缩放
        ↓
换回原坐标系
```
---


<a id="origin-7137"></a>
## 114. 特征值分解：为什么 \(P^{-1}x\) 表示转换到特征向量坐标系？

特征值分解的公式：

\[
\boxed{A=PDP^{-1}}
\]

其中：

- \(A\)：原始矩阵。
- \(P\)：由特征向量组成的矩阵。
- \(D\)：由特征值组成的对角矩阵。
- \(P^{-1}\)：矩阵 \(P\) 的逆矩阵。

当我们计算：

\[
Ax=PDP^{-1}x
\]

时，矩阵运算从右向左执行：

1. \(P^{-1}x\)：把原始坐标转换成特征向量坐标。
2. \(D(P^{-1}x)\)：沿各个特征向量方向，分别按照特征值进行缩放。
3. \(PD(P^{-1}x)\)：把变换后的坐标重新转换回原始坐标系。

下面通过具体例子解释。

---

<a id="origin-7168"></a>
## 115. 首先，什么叫“换一个坐标系”？

平时我们使用的二维坐标系，由两个标准单位向量构成：

\[
e_1=
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

\[
e_2=
\begin{bmatrix}
0\\
1
\end{bmatrix}
\]

假设有一个向量：

\[
x=
\begin{bmatrix}
3\\
2
\end{bmatrix}
\]

这代表：

\[
\boxed{x=3e_1+2e_2}
\]

也就是说：

- 沿着 \(e_1\) 方向走 3 个单位。
- 沿着 \(e_2\) 方向走 2 个单位。

这就是向量 \(x\) 在标准坐标系下的表示。

现在我们换一组基底：

\[
v_1=
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

\[
v_2=
\begin{bmatrix}
1\\
1
\end{bmatrix}
\]

注意，这两个新基底不一定互相垂直，只要它们线性无关，就可以构成二维空间的一组基底。

现在的问题是：

**同样一个向量 \(x=(3,2)\)，如果不用原来的 \(e_1,e_2\)，而改用 \(v_1,v_2\)，应该怎么描述它？**

---

<a id="origin-7237"></a>
## 116. 用新基底 \(v_1,v_2\) 表示向量 x

我们希望找到两个系数 \(a,b\)，使得：

\[
x=av_1+bv_2
\]

代入：

\[
\begin{bmatrix}
3\\
2
\end{bmatrix}
=
a
\begin{bmatrix}
1\\
0
\end{bmatrix}
+
b
\begin{bmatrix}
1\\
1
\end{bmatrix}
\]

展开右边：

\[
\begin{bmatrix}
3\\
2
\end{bmatrix}
=
\begin{bmatrix}
a+b\\
b
\end{bmatrix}
\]

因此：

\[
\begin{cases}
a+b=3\\
b=2
\end{cases}
\]

解得：

\[
a=1,\qquad b=2
\]

所以：

\[
\boxed{x=1v_1+2v_2}
\]

发现了吗？

同一个向量 \(x\)：

在原始坐标系 \(e_1,e_2\) 下：

\[
\boxed{
x=
\begin{bmatrix}
3\\
2
\end{bmatrix}
}
\]

在新坐标系 \(v_1,v_2\) 下：

\[
\boxed{
[x]_{v_1,v_2}=
\begin{bmatrix}
1\\
2
\end{bmatrix}
}
\]

这里的 \([x]_{v_1,v_2}\) 表示向量 \(x\) 在新基底下的坐标。

**向量本身没有改变，只是描述这个向量所使用的基底改变了，因此坐标数字也发生了变化。**

---

<a id="origin-7335"></a>
## 117. 那么 P 在这里干了什么？

我们把两个新基底向量作为列，拼成一个矩阵：

\[
P=
\begin{bmatrix}
|&|\\
v_1&v_2\\
|&|
\end{bmatrix}
\]

代入：

\[
\boxed{
P=
\begin{bmatrix}
1&1\\
0&1
\end{bmatrix}
}
\]

现在定义：

\[
c=
\begin{bmatrix}
a\\
b
\end{bmatrix}
\]

表示向量 \(x\) 在新基底下的坐标。

由于：

\[
x=av_1+bv_2
\]

所以可以写成：

\[
x=
\begin{bmatrix}
|&|\\
v_1&v_2\\
|&|
\end{bmatrix}
\begin{bmatrix}
a\\
b
\end{bmatrix}
\]

也就是：

\[
\boxed{x=Pc}
\]

因此，矩阵 \(P\) 的作用是：

> 把新基底下的坐标 \(c\)，转换成原始标准坐标系下的坐标 \(x\)。

例如：

\[
P
\begin{bmatrix}
1\\
2
\end{bmatrix}
=
\begin{bmatrix}
1&1\\
0&1
\end{bmatrix}
\begin{bmatrix}
1\\
2
\end{bmatrix}
\]

得到：

\[
\boxed{
x=
\begin{bmatrix}
3\\
2
\end{bmatrix}
}
\]

---

<a id="origin-7436"></a>
## 118. 那么 \(P^{-1}\) 为什么能反过来转换坐标？

前面有：

\[
x=Pc
\]

现在我们已知原始坐标 \(x\)，想求新基底下的坐标 \(c\)。

两边左乘 \(P^{-1}\)：

\[
P^{-1}x=P^{-1}Pc
\]

因为：

\[
P^{-1}P=I
\]

所以：

\[
P^{-1}x=Ic
\]

最终得到：

\[
\boxed{c=P^{-1}x}
\]

这就解释了：

**为什么 \(P^{-1}\) 可以把原始坐标转换成新基底下的坐标。**

在我们的例子中：

\[
P=
\begin{bmatrix}
1&1\\
0&1
\end{bmatrix}
\]

因此：

\[
P^{-1}=
\begin{bmatrix}
1&-1\\
0&1
\end{bmatrix}
\]

现在计算：

\[
P^{-1}x
=
\begin{bmatrix}
1&-1\\
0&1
\end{bmatrix}
\begin{bmatrix}
3\\
2
\end{bmatrix}
\]

得到：

\[
P^{-1}x
=
\begin{bmatrix}
3-2\\
2
\end{bmatrix}
\]

所以：

\[
\boxed{
P^{-1}x=
\begin{bmatrix}
1\\
2
\end{bmatrix}
}
\]

这恰好就是我们之前手动求出来的：

\[
x=1v_1+2v_2
\]

因此：

\[
\boxed{
P^{-1}x
}
\]

表达的就是：

> 原来的向量 \(x\)，如果改用 \(v_1,v_2\) 这两个向量作为基底，那么它的坐标是多少？

需要注意：

虽然：

\[
\begin{bmatrix}
3\\2
\end{bmatrix}
\neq
\begin{bmatrix}
1\\2
\end{bmatrix}
\]

但这两个坐标分别处于不同基底下，描述的是同一个几何向量。

---

<a id="origin-7568"></a>
## 119. 为什么特征值分解中特别喜欢用特征向量作为新基底？

现在把它和特征值分解联系起来。

假设原始矩阵是：

\[
A=
\begin{bmatrix}
2&1\\
0&3
\end{bmatrix}
\]

刚才的两个新基底：

\[
v_1=
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

\[
v_2=
\begin{bmatrix}
1\\
1
\end{bmatrix}
\]

恰好是矩阵 \(A\) 的两个特征向量。

我们验证一下。

<a id="origin-7604"></a>
### 119.1 第一个特征向量

\[
Av_1=
\begin{bmatrix}
2&1\\
0&3
\end{bmatrix}
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

得到：

\[
Av_1=
\begin{bmatrix}
2\\
0
\end{bmatrix}
\]

也就是：

\[
\boxed{Av_1=2v_1}
\]

所以：

\[
\lambda_1=2
\]

<a id="origin-7640"></a>
### 119.2 第二个特征向量

\[
Av_2=
\begin{bmatrix}
2&1\\
0&3
\end{bmatrix}
\begin{bmatrix}
1\\
1
\end{bmatrix}
\]

得到：

\[
Av_2=
\begin{bmatrix}
3\\
3
\end{bmatrix}
\]

也就是：

\[
\boxed{Av_2=3v_2}
\]

所以：

\[
\lambda_2=3
\]

这意味着：

- 在 \(v_1\) 方向上，矩阵 \(A\) 只会把向量放大 2 倍。
- 在 \(v_2\) 方向上，矩阵 \(A\) 只会把向量放大 3 倍。

**这就是特征向量坐标系的特殊之处：在这些方向上，矩阵变换只需要进行简单的缩放。**

---

<a id="origin-7685"></a>
## 120. 为什么换成特征向量坐标系之后，矩阵运算变简单了？

前面我们已经知道：

\[
x=1v_1+2v_2
\]

现在要计算：

\[
Ax
\]

代入：

\[
Ax=A(v_1+2v_2)
\]

根据矩阵乘法的线性性质：

\[
Ax=Av_1+2Av_2
\]

而：

\[
Av_1=2v_1
\]

\[
Av_2=3v_2
\]

所以：

\[
Ax=2v_1+2(3v_2)
\]

得到：

\[
\boxed{
Ax=2v_1+6v_2
}
\]

注意这里发生了什么。

原来向量 \(x\) 在特征向量坐标系下是：

\[
\begin{bmatrix}
1\\
2
\end{bmatrix}
\]

经过 \(A\) 变换之后，在同一组特征向量基底下变成：

\[
\begin{bmatrix}
2\\
6
\end{bmatrix}
\]

这个变换完全可以写成：

\[
\begin{bmatrix}
2\\
6
\end{bmatrix}
=
\begin{bmatrix}
2&0\\
0&3
\end{bmatrix}
\begin{bmatrix}
1\\
2
\end{bmatrix}
\]

因此定义：

\[
\boxed{
D=
\begin{bmatrix}
2&0\\
0&3
\end{bmatrix}
}
\]

也就是说：

**在特征向量坐标系下，原来复杂的矩阵 \(A\) 变成了简单的对角矩阵 \(D\)。**

它只需要：

\[
c_1\rightarrow\lambda_1c_1
\]

\[
c_2\rightarrow\lambda_2c_2
\]

不需要两个坐标之间相互混合。

---

<a id="origin-7803"></a>
## 121. 终于理解 \(A=PDP^{-1}\) 了

现在我们要计算：

\[
Ax
\]

其中：

\[
x=
\begin{bmatrix}
3\\
2
\end{bmatrix}
\]

三个矩阵分别为：

\[
P=
\begin{bmatrix}
1&1\\
0&1
\end{bmatrix}
\]

\[
D=
\begin{bmatrix}
2&0\\
0&3
\end{bmatrix}
\]

\[
P^{-1}=
\begin{bmatrix}
1&-1\\
0&1
\end{bmatrix}
\]

执行：

\[
\boxed{
Ax=PDP^{-1}x
}
\]

<a id="origin-7855"></a>
### 121.1 第一步：\(P^{-1}x\)，转换到特征向量坐标系

\[
P^{-1}x
=
\begin{bmatrix}
1&-1\\
0&1
\end{bmatrix}
\begin{bmatrix}
3\\
2
\end{bmatrix}
\]

得到：

\[
\boxed{
P^{-1}x=
\begin{bmatrix}
1\\
2
\end{bmatrix}
}
\]

含义：

原来的向量：

\[
x=3e_1+2e_2
\]

现在改用特征向量表示：

\[
x=1v_1+2v_2
\]

向量本身没有改变，只是换了坐标表示。

<a id="origin-7898"></a>
#### 121.1.1 第二步：乘 D，在特征向量方向上分别缩放

\[
D(P^{-1}x)
=
\begin{bmatrix}
2&0\\
0&3
\end{bmatrix}
\begin{bmatrix}
1\\
2
\end{bmatrix}
\]

得到：

\[
\boxed{
D(P^{-1}x)=
\begin{bmatrix}
2\\
6
\end{bmatrix}
}
\]

含义：

- \(v_1\) 方向的坐标由 1 变成 2。
- \(v_2\) 方向的坐标由 2 变成 6。

也就是：

\[
1v_1+2v_2
\]

经过变换变成：

\[
2v_1+6v_2
\]

<a id="origin-7942"></a>
#### 121.1.2 第三步：乘 P，转换回原始坐标系

现在：

\[
\begin{bmatrix}
2\\
6
\end{bmatrix}
\]

仍然是在特征向量坐标系下的表示。

为了得到标准坐标系下的结果，需要乘：

\[
P
\]

于是：

\[
PD(P^{-1}x)
=
\begin{bmatrix}
1&1\\
0&1
\end{bmatrix}
\begin{bmatrix}
2\\
6
\end{bmatrix}
\]

得到：

\[
\boxed{
PD(P^{-1}x)=
\begin{bmatrix}
8\\
6
\end{bmatrix}
}
\]

这就是原始坐标系下的最终结果。

---

<a id="origin-7992"></a>
## 122. 验证：直接使用 A，是否得到同样结果？

原始矩阵：

\[
A=
\begin{bmatrix}
2&1\\
0&3
\end{bmatrix}
\]

原始向量：

\[
x=
\begin{bmatrix}
3\\
2
\end{bmatrix}
\]

直接计算：

\[
Ax=
\begin{bmatrix}
2&1\\
0&3
\end{bmatrix}
\begin{bmatrix}
3\\
2
\end{bmatrix}
\]

得到：

\[
Ax=
\begin{bmatrix}
2\times3+1\times2\\
0\times3+3\times2
\end{bmatrix}
\]

因此：

\[
\boxed{
Ax=
\begin{bmatrix}
8\\
6
\end{bmatrix}
}
\]

和刚才：

\[
\boxed{
PDP^{-1}x=
\begin{bmatrix}
8\\
6
\end{bmatrix}
}
\]

完全一致。

所以：

\[
\boxed{
Ax=PDP^{-1}x
}
\]

对于所有向量 \(x\) 都成立，因此：

\[
\boxed{
A=PDP^{-1}
}
\]

---

<a id="origin-8082"></a>
## 123. 整个过程的流程图

```text
原始向量 x
标准坐标系 e1、e2

x = [3, 2]
     │
     │
     ▼
乘 P⁻¹
     │
     ▼
转换到特征向量坐标系 v1、v2

c = [1, 2]
     │
     │
     ▼
乘 D
     │
     ├── v1 方向乘 λ1 = 2
     │
     └── v2 方向乘 λ2 = 3
     │
     ▼
特征向量坐标系下的新坐标

c' = [2, 6]
     │
     │
     ▼
乘 P
     │
     ▼
转换回标准坐标系

y = [8, 6]

最终：

Ax = PDP⁻¹x
```

---

<a id="origin-8128"></a>
## 124. 最终总结

对于特征值分解：

\[
\boxed{
A=PDP^{-1}
}
\]

三个矩阵各有不同的作用。

<a id="origin-8140"></a>
### 124.1 \(P^{-1}\)：更换坐标系

\[
\boxed{
c=P^{-1}x
}
\]

将标准坐标系下的向量坐标 \(x\)，转换成以特征向量为基底的坐标 \(c\)。

<a id="origin-8150"></a>
#### 124.1.1 \(D\)：沿特征向量方向分别缩放

\[
\boxed{
c'=Dc
}
\]

其中：

\[
D=
\begin{bmatrix}
\lambda_1&0\\
0&\lambda_2
\end{bmatrix}
\]

所以每个坐标分别乘以对应的特征值。

<a id="origin-8170"></a>
#### 124.1.2 \(P\)：转换回标准坐标系

\[
\boxed{
y=Pc'
}
\]

将变换后的特征向量坐标重新转换成原始坐标系下的坐标。

因此：

\[
\boxed{
y=PDP^{-1}x
}
\]

最后得到：

\[
\boxed{
A=PDP^{-1}
}
\]

**一句话总结：特征值分解就是先把向量转换到一组特殊的坐标系（特征向量基底），在那里只做简单的缩放，再转换回原来的坐标系。**

需要注意的是：这种分解要求矩阵有足够多的线性无关特征向量，即矩阵必须可以对角化，并不是所有方阵都能写成 \(PDP^{-1}\)。


---

<a id="origin-8203"></a>
## 125. 特征值分解有什么问题？

问题来了：

不是每个矩阵都能方便地做：

\[
A=P\Lambda P^{-1}
\]

首先：

\[
A
\]

必须是：

\[
\boxed{\text{方阵}}
\]

例如：

\[
A\in\mathbb R^{3\times2}
\]

就不能直接做普通特征值分解。

因为：

\[
Av
\]

是一个三维向量，

而：

\[
\lambda v
\]

还是二维向量。

维度都不一样。

所以：

\[
Av=\lambda v
\]

根本写不通。

---

<a id="origin-8261"></a>
## 126. 但是神经网络里面大量矩阵不是方阵

例如：

\[
W
\in
\mathbb R^{4096\times11008}
\]

或者：

\[
W
\in
\mathbb R^{11008\times4096}
\]

我们还是希望知道：

> 这个矩阵最重要的几个方向是什么？

这时候普通特征值分解就不够用了。

于是：

\[
\boxed{\text{SVD}}
\]

出现了。

---

<a id="origin-8295"></a>
## 127. SVD 的核心思想和特征值分解很像

特征值分解寻找：

\[
Av=\lambda v
\]

意思是：

> 找一个方向，经过 \(A\) 以后方向还不变。

但是对于任意矩阵，这个要求太强。

SVD 放宽要求：

\[
\boxed{
Av=\sigma u
}
\]

它不要求：

\[
u=v
\]

而只是说：

> 找一个输入方向 \(v\)，经过 \(A\) 后，变成某个输出方向 \(u\)，长度放大 \(\sigma\) 倍。

---

<a id="origin-8329"></a>
## 128. 这三个量分别是什么？

\[
Av_i=\sigma_i u_i
\]

其中：

<a id="origin-8337"></a>
### 128.1 \(v_i\)

输入空间中的特殊方向。

叫：

\[
\boxed{\text{右奇异向量}}
\]

---

<a id="origin-8349"></a>
#### 128.1.1 \(u_i\)

输出空间中的特殊方向。

叫：

\[
\boxed{\text{左奇异向量}}
\]

---

<a id="origin-8361"></a>
#### 128.1.2 \(\sigma_i\)

这个方向被放大的倍数。

叫：

\[
\boxed{\text{奇异值}}
\]

---

<a id="origin-8373"></a>
## 129. 为什么又冒出来一个 \(A^TA\)？

这是 SVD 最关键的一步。

我们真正想知道的是：

> 一个输入方向 \(v\) 经过 \(A\) 以后，长度变成多少？

也就是：

\[
\|Av\|
\]

平方：

\[
\|Av\|^2
\]

根据：

\[
\|z\|^2=z^Tz
\]

所以：

\[
\|Av\|^2
=
(Av)^T(Av)
\]

展开：

\[
(Av)^T
=
v^TA^T
\]

因此：

\[
\boxed{
\|Av\|^2
=
v^TA^TAv
}
\]

所以：

\[
A^TA
\]

里面实际上装着：

\[
\boxed{
A\text{ 对输入空间各个方向的拉伸信息}
}
\]

---

<a id="origin-8441"></a>
## 130. 为什么不直接研究 \(A\)，而研究 \(A^TA\)？

因为无论：

\[
A
\]

是不是方阵：

\[
A^TA
\]

一定是方阵。

假设：

\[
A\in\mathbb R^{m\times n}
\]

那么：

\[
A^T\in\mathbb R^{n\times m}
\]

于是：

\[
A^TA
\]

尺寸：

\[
(n\times m)(m\times n)
=
n\times n
\]

所以：

\[
\boxed{
A^TA
}
\]

永远是方阵。

而且还是：

\[
\boxed{\text{对称矩阵}}
\]

因为：

\[
(A^TA)^T=A^TA
\]

---

<a id="origin-8507"></a>
## 131. 对称矩阵有什么特别好？

实对称矩阵有非常好的性质：

1. 特征值都是实数；
2. 可以找到一组互相正交的特征向量；
3. 一定可以正交对角化。

所以我们可以对：

\[
A^TA
\]

做普通特征值分解。

---

<a id="origin-8525"></a>
## 132. 对 \(A^TA\) 求特征值

有：

\[
A^TAv_i
=
\lambda_i v_i
\]

现在左乘：

\[
v_i^T
\]

得到：

\[
v_i^TA^TAv_i
=
\lambda_i v_i^Tv_i
\]

因为我们把：

\[
v_i
\]

归一化：

\[
v_i^Tv_i=1
\]

所以：

\[
v_i^TA^TAv_i
=
\lambda_i
\]

而刚才：

\[
v_i^TA^TAv_i
=
\|Av_i\|^2
\]

所以：

\[
\boxed{
\lambda_i
=
\|Av_i\|^2
}
\]

---

<a id="origin-8589"></a>
## 133. 奇异值为什么是 \(\sqrt{\lambda}\)？

如果：

\[
Av_i=\sigma_i u_i
\]

而：

\[
u_i
\]

是单位向量，那么：

\[
\|Av_i\|
=
\sigma_i
\]

因此：

\[
\|Av_i\|^2
=
\sigma_i^2
\]

前面又已经得到：

\[
\|Av_i\|^2
=
\lambda_i
\]

所以：

\[
\sigma_i^2=\lambda_i
\]

因此：

\[
\boxed{
\sigma_i=\sqrt{\lambda_i}
}
\]

这就是奇异值的来源。

不是凭空定义的。

---

<a id="origin-8647"></a>
## 134. 做一个特别简单的 SVD 数值例子

这次我们不用：

\[
\begin{bmatrix}
3&1\\
1&3
\end{bmatrix}
\]

那种容易把特征值分解和 SVD 混起来的例子。

直接用一个**非方阵**：

\[
A=
\begin{bmatrix}
3&0\\
0&2\\
0&0
\end{bmatrix}
\]

它是：

\[
3\times2
\]

所以普通特征值分解：

\[
Av=\lambda v
\]

根本不能直接做。

但 SVD 可以。

---

<a id="origin-8689"></a>
## 135. 第一步：计算 \(A^TA\)

首先：

\[
A^T=
\begin{bmatrix}
3&0&0\\
0&2&0
\end{bmatrix}
\]

所以：

\[
A^TA
=
\begin{bmatrix}
3&0&0\\
0&2&0
\end{bmatrix}
\begin{bmatrix}
3&0\\
0&2\\
0&0
\end{bmatrix}
\]

得到：

\[
\boxed{
A^TA=
\begin{bmatrix}
9&0\\
0&4
\end{bmatrix}
}
\]

---

<a id="origin-8731"></a>
## 136. 第二步：求 \(A^TA\) 的特征值

因为已经是对角矩阵：

\[
\boxed{
\lambda_1=9
}
\]

\[
\boxed{
\lambda_2=4
}
\]

对应特征向量：

\[
v_1=
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

\[
v_2=
\begin{bmatrix}
0\\
1
\end{bmatrix}
\]

于是：

\[
V=
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix}
\]

---

<a id="origin-8777"></a>
## 137. 第三步：求奇异值

因为：

\[
\sigma_i=\sqrt{\lambda_i}
\]

所以：

\[
\sigma_1=\sqrt9=3
\]

\[
\sigma_2=\sqrt4=2
\]

于是：

\[
\boxed{
\Sigma=
\begin{bmatrix}
3&0\\
0&2\\
0&0
\end{bmatrix}
}
\]

---

<a id="origin-8810"></a>
## 138. 第四步：求 \(u_1\)

根据：

\[
Av_1=\sigma_1u_1
\]

所以：

\[
u_1
=
\frac{Av_1}{\sigma_1}
\]

计算：

\[
Av_1
=
\begin{bmatrix}
3&0\\
0&2\\
0&0
\end{bmatrix}
\begin{bmatrix}
1\\
0
\end{bmatrix}
\]

得到：

\[
\begin{bmatrix}
3\\
0\\
0
\end{bmatrix}
\]

除以：

\[
\sigma_1=3
\]

所以：

\[
\boxed{
u_1=
\begin{bmatrix}
1\\
0\\
0
\end{bmatrix}
}
\]

---

<a id="origin-8873"></a>
## 139. 第五步：求 \(u_2\)

同样：

\[
Av_2
=
\begin{bmatrix}
3&0\\
0&2\\
0&0
\end{bmatrix}
\begin{bmatrix}
0\\
1
\end{bmatrix}
\]

得到：

\[
\begin{bmatrix}
0\\
2\\
0
\end{bmatrix}
\]

所以：

\[
u_2
=
\frac1{2}
\begin{bmatrix}
0\\
2\\
0
\end{bmatrix}
\]

得到：

\[
\boxed{
u_2=
\begin{bmatrix}
0\\
1\\
0
\end{bmatrix}
}
\]

再补一个与前两个垂直的：

\[
u_3=
\begin{bmatrix}
0\\
0\\
1
\end{bmatrix}
\]

于是：

\[
U=
I
\]

最终：

\[
\boxed{
A=U\Sigma V^T
}
\]

在这个例子里：

\[
U=I
\]

\[
V=I
\]

所以：

\[
A=\Sigma
\]

这是为了先把 SVD 的本质看清楚。

---

<a id="origin-8973"></a>
## 140. 再看一个真正有旋转的例子

假设：

\[
A=
\begin{bmatrix}
1&1\\
1&-1
\end{bmatrix}
\]

计算：

\[
A^TA
\]

因为：

\[
A^T=A
\]

所以：

\[
A^TA
=
\begin{bmatrix}
1&1\\
1&-1
\end{bmatrix}
\begin{bmatrix}
1&1\\
1&-1
\end{bmatrix}
\]

得到：

\[
\boxed{
A^TA=
\begin{bmatrix}
2&0\\
0&2
\end{bmatrix}
}
\]

所以：

\[
\lambda_1=\lambda_2=2
\]

因此：

\[
\sigma_1=\sigma_2=\sqrt2
\]

也就是说：

> 这个矩阵对所有正交基方向的拉伸倍数都是 \(\sqrt2\)，主要还伴随着方向变化。

---

<a id="origin-9042"></a>
## 141. SVD 的最终形式

把所有：

\[
u_i
\]

放在一起：

\[
U=
[u_1,u_2,\ldots]
\]

所有奇异值：

\[
\Sigma=
\operatorname{diag}(
\sigma_1,\sigma_2,\ldots
)
\]

所有：

\[
v_i
\]

放进：

\[
V=
[v_1,v_2,\ldots]
\]

于是：

\[
\boxed{
A=U\Sigma V^T
}
\]

---

<a id="origin-9089"></a>
## 142. 为什么是 \(V^T\)，不是 \(V\)？

因为：

\[
V
\]

的列是：

\[
v_1,v_2,\ldots
\]

这些向量互相正交，并且长度为 1。

所以：

\[
V^TV=I
\]

因此：

\[
\boxed{
V^{-1}=V^T
}
\]

所以：

\[
V^T
\]

负责把普通坐标转换到：

\[
v_1,v_2,\ldots
\]

这组奇异向量坐标系。

---

<a id="origin-9135"></a>
## 143. 所以 SVD 可以怎么理解？

\[
A=U\Sigma V^T
\]

从右往左：

<a id="origin-9143"></a>
### 143.1 第一步

\[
V^T
\]

把输入转到最合适的输入坐标系。

---

<a id="origin-9153"></a>
#### 143.1.1 第二步

\[
\Sigma
\]

分别进行：

\[
\sigma_1,\sigma_2,\ldots
\]

倍拉伸。

---

<a id="origin-9169"></a>
#### 143.1.2 第三步

\[
U
\]

把这些方向转到最终输出坐标系。

所以：

\[
\boxed{
A=
\text{旋转/换坐标}
+
\text{拉伸}
+
\text{旋转/换坐标}
}
\]

---

<a id="origin-9192"></a>
## 144. 为什么 SVD 能表示 Rank？

SVD 还可以展开成：

\[
\boxed{
A
=
\sigma_1u_1v_1^T
+
\sigma_2u_2v_2^T
+\cdots
}
\]

例如：

\[
A
=
10u_1v_1^T
+
3u_2v_2^T
+
0u_3v_3^T
\]

第三项其实没有贡献。

因此：

\[
\boxed{
rank(A)
=
\text{非零奇异值的个数}
}
\]

例如：

\[
\Sigma=
\begin{bmatrix}
10&0&0\\
0&3&0\\
0&0&0
\end{bmatrix}
\]

那么：

\[
\boxed{rank(A)=2}
\]

---

<a id="origin-9250"></a>
## 145. 为什么可以做低秩近似？

假设一个矩阵有奇异值：

\[
100,\quad20,\quad0.1,\quad0.001
\]

那么：

\[
A
=
100u_1v_1^T
+
20u_2v_2^T
+
0.1u_3v_3^T
+
0.001u_4v_4^T
\]

后面两项非常小。

所以可以近似：

\[
A
\approx
100u_1v_1^T
+
20u_2v_2^T
\]

于是只保留：

\[
2
\]

个主要方向。

因此：

\[
\boxed{
rank(A_{\text{approx}})\le2
}
\]

---

<a id="origin-9302"></a>
## 146. 理解 \(\Sigma^{1/2}\)

这是前面最容易让人疑惑的地方。

我们写：

\[
\Sigma^{1/2}
\]

这里的：

\[
\frac12
\]

和普通数字的平方根是一个意思。

例如：

\[
9^{1/2}=3
\]

因为：

\[
3\times3=9
\]

同理：

\[
4^{1/2}=2
\]

因为：

\[
2\times2=4
\]

所以：

\[
x^{1/2}
=
\sqrt{x}
\]

---

<a id="origin-9354"></a>
## 147. 那矩阵的 \(1/2\) 次方是什么意思？

一般矩阵平方根是一个更复杂的问题。

但是 SVD 中：

\[
\Sigma
\]

特别简单。

因为：

\[
\Sigma
\]

是对角矩阵。

例如：

\[
\Sigma=
\begin{bmatrix}
9&0\\
0&4
\end{bmatrix}
\]

那么：

\[
\Sigma^{1/2}
\]

只需要给每个对角元素开平方：

\[
\boxed{
\Sigma^{1/2}
=
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
}
\]

因为：

\[
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
=
\begin{bmatrix}
9&0\\
0&4
\end{bmatrix}
\]

所以：

\[
\boxed{
\Sigma^{1/2}\Sigma^{1/2}
=
\Sigma
}
\]

---

<a id="origin-9433"></a>
## 148. 再给一个最简单的数字例子

假设：

\[
\Sigma=
\begin{bmatrix}
16&0\\
0&25
\end{bmatrix}
\]

那么：

\[
\Sigma^{1/2}
=
\begin{bmatrix}
4&0\\
0&5
\end{bmatrix}
\]

因为：

\[
4^2=16
\]

\[
5^2=25
\]

所以：

\[
\begin{bmatrix}
4&0\\
0&5
\end{bmatrix}
\begin{bmatrix}
4&0\\
0&5
\end{bmatrix}
=
\begin{bmatrix}
16&0\\
0&25
\end{bmatrix}
\]

---

<a id="origin-9486"></a>
## 149. 为什么要把 \(\Sigma\) 拆成两个平方根？

因为：

\[
A=U\Sigma V^T
\]

而：

\[
\Sigma
=
\Sigma^{1/2}
\Sigma^{1/2}
\]

所以：

\[
A
=
U
\Sigma^{1/2}
\Sigma^{1/2}
V^T
\]

重新加括号：

\[
A
=
\left(
U\Sigma^{1/2}
\right)
\left(
\Sigma^{1/2}V^T
\right)
\]

现在定义：

\[
\boxed{
B=U\Sigma^{1/2}
}
\]

以及：

\[
\boxed{
C=\Sigma^{1/2}V^T
}
\]

那么：

\[
\boxed{
A=BC
}
\]

这就是“一个低秩矩阵可以拆成两个小矩阵”的来源之一。

---

<a id="origin-9555"></a>
## 150. 为什么一定要各分一半？

其实：

\[
\boxed{\text{并不是必须}}
\]

这是非常重要的一点。

例如：

\[
A=U\Sigma V^T
\]

我们也完全可以定义：

\[
B=U\Sigma
\]

\[
C=V^T
\]

于是：

\[
BC
=
U\Sigma V^T
=
A
\]

也可以。

或者：

\[
B=U
\]

\[
C=\Sigma V^T
\]

也可以。

所以：

\[
\Sigma^{1/2}
\]

并不是因为数学上“只能这么拆”。

---

<a id="origin-9615"></a>
## 151. 那为什么经常拆成一半一半？

因为这种拆法比较：

\[
\boxed{\text{对称}}
\]

原来的缩放量：

\[
\sigma_i
\]

被平均分给左右两个矩阵。

例如：

\[
\sigma_i=16
\]

如果全部给左边：

```text
左边 ×16
右边 ×1
```

也能工作。

但是用平方根：

```text
左边 ×4
右边 ×4
```

因为：

\[
4\times4=16
\]

更加对称。

---

<a id="origin-9663"></a>
## 152. 一个完整的具体数值例子

假设一个 Rank-2 矩阵的 SVD 中：

\[
U=
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix}
\]

\[
\Sigma=
\begin{bmatrix}
9&0\\
0&4
\end{bmatrix}
\]

\[
V^T=
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix}
\]

所以：

\[
A
=
U\Sigma V^T
=
\begin{bmatrix}
9&0\\
0&4
\end{bmatrix}
\]

现在：

\[
\Sigma^{1/2}
=
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
\]

定义：

\[
B
=
U\Sigma^{1/2}
\]

所以：

\[
B=
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
\]

然后：

\[
C=
\Sigma^{1/2}V^T
\]

得到：

\[
C=
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
\]

于是：

\[
BC
=
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
\begin{bmatrix}
3&0\\
0&2
\end{bmatrix}
\]

得到：

\[
\boxed{
BC=
\begin{bmatrix}
9&0\\
0&4
\end{bmatrix}
}
\]

正好就是：

\[
A
\]

---

<a id="origin-9785"></a>
## 153. 再看一个真正“降维”的例子

假设：

\[
A\in\mathbb R^{3\times3}
\]

但是：

\[
rank(A)=1
\]

那么它只需要一个奇异值：

\[
\sigma_1
\]

此时：

\[
U_1\in\mathbb R^{3\times1}
\]

\[
\Sigma_1\in\mathbb R^{1\times1}
\]

\[
V_1^T\in\mathbb R^{1\times3}
\]

例如：

\[
U_1=
\begin{bmatrix}
1\\
2\\
3
\end{bmatrix}
\]

为了简单，暂时忽略归一化，

假设：

\[
\Sigma_1=[4]
\]

以及：

\[
V_1^T=
\begin{bmatrix}
1&2&1
\end{bmatrix}
\]

那么：

\[
A
=
U_1
[4]
V_1^T
\]

---

<a id="origin-9859"></a>
## 154. 把中间的 4 拆开

因为：

\[
4=\sqrt4\sqrt4
\]

也就是：

\[
4=2\times2
\]

所以：

\[
A
=
U_1
[2]
[2]
V_1^T
\]

定义：

\[
B
=
2U_1
\]

于是：

\[
B=
\begin{bmatrix}
2\\
4\\
6
\end{bmatrix}
\]

再定义：

\[
C
=
2V_1^T
\]

所以：

\[
C=
\begin{bmatrix}
2&4&2
\end{bmatrix}
\]

于是：

\[
A=BC
\]

尺寸是：

\[
(3\times1)(1\times3)
\]

得到：

\[
3\times3
\]

矩阵。

---

<a id="origin-9942"></a>
## 155. 算一下

\[
BC
=
\begin{bmatrix}
2\\
4\\
6
\end{bmatrix}
\begin{bmatrix}
2&4&2
\end{bmatrix}
\]

得到：

\[
\boxed{
A=
\begin{bmatrix}
4&8&4\\
8&16&8\\
12&24&12
\end{bmatrix}
}
\]

这个矩阵看起来有：

\[
3\times3=9
\]

个元素。

但是它实际上只需要：

\[
B:
3\times1
\]

加上：

\[
C:
1\times3
\]

也就是：

\[
3+3=6
\]

个元素就能表示。

而且：

\[
rank(A)=1
\]

因为：

```text
第2行 = 第1行 ×2

第3行 = 第1行 ×3
```

---

<a id="origin-10016"></a>
## 156. 这和 LoRA 已经非常接近了

假设：

\[
\Delta W
\in
\mathbb R^{4096\times4096}
\]

但是它真正重要的 Rank 只有：

\[
r=8
\]

那么从 SVD 的角度：

\[
\Delta W
\approx
U_r\Sigma_rV_r^T
\]

其中：

\[
U_r:
4096\times8
\]

\[
\Sigma_r:
8\times8
\]

\[
V_r^T:
8\times4096
\]

然后：

\[
\Sigma_r
=
\Sigma_r^{1/2}
\Sigma_r^{1/2}
\]

所以：

\[
\Delta W
\approx
U_r
\Sigma_r^{1/2}
\Sigma_r^{1/2}
V_r^T
\]

重新组合：

\[
\boxed{
\Delta W
\approx
\left(
U_r\Sigma_r^{1/2}
\right)
\left(
\Sigma_r^{1/2}V_r^T
\right)
}
\]

---

<a id="origin-10094"></a>
## 157. 令这两个矩阵分别叫 \(B\) 和 \(A\)

注意这里不要和原来的大矩阵 \(A\) 混淆。

在 LoRA 里面定义：

\[
B
=
U_r\Sigma_r^{1/2}
\]

尺寸：

\[
B\in\mathbb R^{4096\times8}
\]

再定义：

\[
A
=
\Sigma_r^{1/2}V_r^T
\]

尺寸：

\[
A\in\mathbb R^{8\times4096}
\]

于是：

\[
\boxed{
\Delta W\approx BA
}
\]

尺寸：

\[
(4096\times8)
(8\times4096)
=
4096\times4096
\]

---

<a id="origin-10145"></a>
## 158. 但是这里一定注意：LoRA 并不真的这样算 SVD

这是理解 LoRA 特别重要的一句话。

LoRA 并不是：

```text
先训练出完整 ΔW
        ↓
对 ΔW 做 SVD
        ↓
得到 UΣVᵀ
        ↓
再拆成 B 和 A
```

实际上 LoRA 一开始就直接规定：

\[
\boxed{
\Delta W=BA
}
\]

然后通过梯度下降直接学习：

\[
A
\]

和：

\[
B
\]

---

<a id="origin-10183"></a>
## 159. 那为什么还要讲 SVD？

因为 SVD 给了我们一个数学直觉：

> 一个大矩阵如果主要信息集中在少数几个奇异方向上，那么根本没有必要用完整的大矩阵描述它。

例如：

\[
\Delta W
\]

虽然是：

\[
4096\times4096
\]

但是如果只有：

\[
8
\]

个主要奇异方向，

那么就可以使用：

\[
4096\times8
\]

和：

\[
8\times4096
\]

两个矩阵近似描述。

这就是：

\[
\boxed{\text{低秩}}
\]

---

<a id="origin-10231"></a>
## 160. 特征值分解和 SVD 最核心的区别

可以这样记。

<a id="origin-10235"></a>
### 160.1 特征值分解

研究：

\[
\boxed{
Av=\lambda v
}
\]

也就是：

> 找一些经过矩阵以后方向不变的特殊方向。

形式：

\[
\boxed{
A=P\Lambda P^{-1}
}
\]

主要针对：

\[
\boxed{\text{方阵}}
\]

---

<a id="origin-10265"></a>
### 160.2 SVD

研究：

\[
\boxed{
Av=\sigma u
}
\]

不要求：

\[
u=v
\]

而允许：

> 输入方向 \(v\) 经过矩阵以后变成另外一个输出方向 \(u\)。

形式：

\[
\boxed{
A=U\Sigma V^T
}
\]

可以用于：

\[
\boxed{\text{任意矩阵}}
\]

---

<a id="origin-10301"></a>
## 161. 为什么 SVD 比特征值分解更适合研究低秩？

因为：

\[
\Sigma
\]

直接把各个方向的重要程度列出来了：

\[
\sigma_1\ge\sigma_2\ge\cdots
\]

例如：

\[
\Sigma=
\begin{bmatrix}
100&0&0&0\\
0&20&0&0\\
0&0&0.01&0\\
0&0&0&0.001
\end{bmatrix}
\]

那么我们可以很直观地说：

```text
第1个方向：非常重要

第2个方向：比较重要

第3个方向：几乎没什么影响

第4个方向：几乎没什么影响
```

于是：

\[
A
\]

可以近似只保留前两个方向。

所以：

\[
\boxed{
A\approx A_2
}
\]

其中：

\[
rank(A_2)\le2
\]

---

<a id="origin-10363"></a>
## 162. 最后把整个逻辑完整串起来

最开始我们有：

\[
Av=\lambda v
\]

这叫：

\[
\boxed{\text{特征值问题}}
\]

---

对于可以特征分解的矩阵：

\[
\boxed{
A=P\Lambda P^{-1}
}
\]

---

但是普通特征值分解对非方阵不方便。

所以我们构造：

\[
\boxed{
A^TA
}
\]

它一定是：

```text
方阵
对称矩阵
```

---

求：

\[
A^TAv_i=\lambda_i v_i
\]

得到右奇异向量：

\[
v_i
\]

然后：

\[
\boxed{
\sigma_i=\sqrt{\lambda_i}
}
\]

得到奇异值。

接着：

\[
\boxed{
u_i=\frac{Av_i}{\sigma_i}
}
\]

得到左奇异向量。

最终：

\[
\boxed{
A=U\Sigma V^T
}
\]

---

如果只保留前 \(r\) 个重要方向：

\[
\boxed{
A\approx U_r\Sigma_rV_r^T
}
\]

然后：

\[
\Sigma_r
=
\Sigma_r^{1/2}
\Sigma_r^{1/2}
\]

于是：

\[
A
\approx
\left(
U_r\Sigma_r^{1/2}
\right)
\left(
\Sigma_r^{1/2}V_r^T
\right)
\]

也就是：

\[
\boxed{
A\approx BC
}
\]

于是我们知道：

> 一个低秩的大矩阵，可以用两个小矩阵相乘表示。

这就是理解 LoRA：

\[
\boxed{
\Delta W=BA
}
\]

最重要的线性代数基础。

---

<a id="origin-10504"></a>
## 163. 最后只记这一条主线

```text
矩阵 A
 │
 │ 寻找特殊方向
 ↓
特征值分解
Av = λv
 │
 │ 但只能方便处理方阵
 ↓
构造 AᵀA
 │
 ↓
AᵀAv = λv
 │
 ├── v：右奇异向量
 │
 └── √λ = σ：奇异值
          │
          ↓
     u = Av / σ
          │
          ↓
      A = UΣVᵀ
          │
          ↓
只保留前 r 个主要奇异方向
          │
          ↓
A ≈ UᵣΣᵣVᵣᵀ
          │
          ↓
Σᵣ = Σᵣ¹ᐟ² Σᵣ¹ᐟ²
          │
          ↓
A ≈ (UᵣΣᵣ¹ᐟ²)(Σᵣ¹ᐟ²Vᵣᵀ)
          │
          ↓
       A ≈ BC
          │
          ↓
LoRA：ΔW = BA
```

一句话总结：

\[
\boxed{
\text{特征值分解是在找“方向不变”的方向；}
}
\]

\[
\boxed{
\text{SVD 则把要求放宽为“输入方向 }v
\text{ 经过 }A\text{ 后变成输出方向 }u\text{”。}
}
\]

而：

\[
\boxed{
\Sigma^{1/2}
}
\]

仅仅意味着：

> 把每一个奇异值开平方，然后把原来的缩放量平均拆给左右两个低秩矩阵。

例如：

\[
\sigma=16
\]

拆成：

\[
\sqrt{16}\times\sqrt{16}
=
4\times4
=
16
\]

就是这么简单。
