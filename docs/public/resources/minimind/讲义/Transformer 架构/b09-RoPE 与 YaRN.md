# RoPE 与 YaRN


<a id="origin-3"></a>
## 1. 先看核心问题

我们经常说：

> 单纯的 Self-Attention 并没有天然的“第几个位置”的概念。

这句话到底是什么意思？

例如一句话：

```text
我  爱  浙大
```

如果只看普通的 Self-Attention，那么对于“爱”这个 token，它确实可以分别计算自己和：

```text
我
爱
浙大
```

之间的注意力关系。

例如可能得到：

$$
[0.2,\ 0.1,\ 0.7]
$$

表示：

```text
爱 → 我       20%
爱 → 爱       10%
爱 → 浙大     70%
```

所以：

> Self-Attention 确实可以知道“爱”和哪些 token 更相关。

但是如果没有额外的位置编码，它并不知道：

```text
我      是第 1 个 token
爱      是第 2 个 token
浙大    是第 3 个 token
```

也就是说：

> Self-Attention 天然擅长建模“谁和谁相关”，但并不天然知道“谁在谁前面、谁在谁后面”。

---

<a id="origin-59"></a>
## 2. 可以把它理解成“桌子上的卡片”

假设现在桌子上有三张卡片：

```text
[我]    [爱]    [浙大]
```

Self-Attention 可以读懂每张卡片上写了什么。

它也可以判断：

```text
“爱”和“浙大”关系比较强
“爱”和“我”也有关系
```

但是如果我把三张卡片重新摆成：

```text
[浙大]    [爱]    [我]
```

如果没有任何位置相关的信息，那么对于纯 Self-Attention 来说：

```text
还是三个 token：

我
爱
浙大
```

它并没有一个额外信号告诉自己：

> 刚才“我”在前，“浙大”在后。

> 现在“浙大”在前，“我”在后。

所以最核心的问题是：

> Self-Attention 能看到“成员”，但不知道“排列顺序”。

---

<a id="origin-104"></a>
## 3. 一个更明显的例子：狗咬人 vs 人咬狗

考虑两个句子：

```text
狗  咬  人
```

和：

```text
人  咬  狗
```

它们包含的 token 完全一样：

```text
狗
咬
人
```

Self-Attention 可以学习到：

```text
“咬”和“狗”有关系

“咬”和“人”有关系
```

但是如果完全没有位置信息，仅仅根据 token 集合，并不能直接判断：

```text
狗 → 咬 → 人
```

还是：

```text
人 → 咬 → 狗
```

而这两个句子的意思显然完全不同。

所以对于自然语言来说：

> 只知道“有哪些词”是不够的，还必须知道“这些词按照什么顺序出现”。

这就是位置编码存在的原因。

---

<a id="origin-156"></a>
## 4. 最基本的 Position Embedding

最简单的位置编码思路是：

$$
\boxed{
InputEmbedding
=
TokenEmbedding
+
PositionEmbedding
}
$$

也就是说：

> 一个 token 的最终输入 = “这个词是谁” + “这个词在哪里”。

---

<a id="origin-176"></a>
### 4.1 一个最简单的数值例子

还是：

```text
我  爱  浙大
```

为了方便理解，假设 Token Embedding 只有 3 维。

词向量：

$$
x_{\text{我}}
=
[1,0,1]
$$

$$
x_{\text{爱}}
=
[0,1,1]
$$

$$
x_{\text{浙大}}
=
[1,1,0]
$$

现在我们再给每一个位置准备一个 Position Embedding：

第 1 个位置：

$$
p_1=
[0.1,0,0]
$$

第 2 个位置：

$$
p_2=
[0,0.1,0]
$$

第 3 个位置：

$$
p_3=
[0,0,0.1]
$$

于是：

<a id="origin-231"></a>
#### 4.1.1 “我”

$$
h_1
=
x_{\text{我}}+p_1
$$

$$
=
[1,0,1]+[0.1,0,0]
$$

$$
=
[1.1,0,1]
$$

---

<a id="origin-251"></a>
#### 4.1.2 “爱”

$$
h_2
=
x_{\text{爱}}+p_2
$$

$$
=
[0,1,1]+[0,0.1,0]
$$

$$
=
[0,1.1,1]
$$

---

<a id="origin-271"></a>
#### 4.1.3 “浙大”

$$
h_3
=
x_{\text{浙大}}+p_3
$$

$$
=
[1,1,0]+[0,0,0.1]
$$

$$
=
[1,1,0.1]
$$

于是：

```text
原来：

我      → [1, 0, 1]
爱      → [0, 1, 1]
浙大    → [1, 1, 0]
```

加入 Position Embedding 后：

```text
我 + 第1位
→ [1.1, 0, 1]

爱 + 第2位
→ [0, 1.1, 1]

浙大 + 第3位
→ [1, 1, 0.1]
```

可以直观地理解成：

```text
“我，而且我在第 1 个位置”

“爱，而且我在第 2 个位置”

“浙大，而且我在第 3 个位置”
```

---

<a id="origin-324"></a>
## 5. 为什么不能直接把 1、2、3 塞进去？

因为 Transformer 中所有信息最终都必须以向量形式参与计算。

假设：

$$
d_{model}=512
$$

那么 Token Embedding 是：

$$
x\in\mathbb{R}^{512}
$$

Position Embedding 通常也必须是：

$$
p\in\mathbb{R}^{512}
$$

然后才能进行：

$$
x+p
$$

所以不是简单地：

```text
爱 + 2
```

而是：

```text
“爱”的 512 维向量
+
“第 2 个位置”的 512 维向量
```

得到新的 512 维表示。

---

<a id="origin-370"></a>
## 6. 同一个词在不同位置，表示会不同

这个例子非常重要。

考虑：

```text
我  爱  浙大
    ↑
   第2位
```

这里“爱”的输入是：

$$
x_{\text{爱}}+p_2
$$

但是如果句子变成：

```text
爱  我  浙大
↑
第1位
```

这里“爱”的输入变成：

$$
x_{\text{爱}}+p_1
$$

注意：

“爱”的 Token Embedding 没有变：

$$
x_{\text{爱}}
$$

但是位置发生了变化：

$$
p_1\neq p_2
$$

因此：

$$
x_{\text{爱}}+p_1
\neq
x_{\text{爱}}+p_2
$$

所以模型能够知道：

> 虽然都是“爱”，但一个“爱”在第 1 位，一个“爱”在第 2 位。

---

<a id="origin-430"></a>
## 7. 一个自然的问题：两种完全不同的信息为什么可以直接相加？

现在会产生一个非常自然的问题：

> Token Embedding 表示的是“词是什么”，Position Embedding 表示的是“位置在哪里”，这两个含义完全不同的向量，为什么可以直接相加？

例如：

$$
x_{\text{爱}}
=
[1,2]
$$

位置 2 的向量：

$$
p_2
=
[0.1,-0.2]
$$

相加以后：

$$
h
=
x_{\text{爱}}+p_2
$$

$$
=
[1.1,1.8]
$$

模型最后只看到了：

$$
[1.1,1.8]
$$

那它怎么知道：

```text
哪些东西来自“爱”？

哪些东西来自“第 2 个位置”？
```

---

<a id="origin-481"></a>
## 8. 答案：模型根本不需要把它们拆回来

这是最重要的一点。

模型并不会做：

```text
[1.1, 1.8]
        ↓
把词义拆出来
        ↓
把位置拆出来
```

它真正做的是：

> 直接使用这个混合表示完成后面的 Attention 和预测。

假设：

$$
h=x+p
$$

然后计算：

$$
Q=hW_Q
$$

代进去：

$$
Q=(x+p)W_Q
$$

根据线性运算的分配律：

$$
Q=xW_Q+pW_Q
$$

也就是说：

> 虽然 x 和 p 已经加在了一起，但它们仍然都能对后续的 Q 产生影响。

同理：

$$
K=(x+p)W_K
$$

可以展开：

$$
K=xW_K+pW_K
$$

所以词义信息和位置信息都会进入后面的 Attention 计算。

---

<a id="origin-543"></a>
## 9. 一个更具体的数值例子

假设：

$$
x=
[10,5]
$$

表示词义信息。

位置向量：

$$
p=
[1,-1]
$$

那么：

$$
h=x+p
$$

$$
=[11,4]
$$

现在假设后面的某个线性投影方向是：

$$
W=
\begin{bmatrix}
1\\
1
\end{bmatrix}
$$

那么：

$$
hW
=
11+4
=
15
$$

从展开形式来看：

$$
(x+p)W
=
xW+pW
$$

其中：

$$
xW
=
10+5
=
15
$$

而：

$$
pW
=
1+(-1)
=
0
$$

所以这个投影方向实际上：

> 主要使用了词义信息，而几乎忽略了位置信息。

---

现在换一个投影方向：

$$
W=
\begin{bmatrix}
1\\
-1
\end{bmatrix}
$$

那么：

$$
hW
=
11-4
=
7
$$

其中：

$$
xW
=
10-5
=
5
$$

而：

$$
pW
=
1-(-1)
=
2
$$

所以这个方向中：

> 位置信息明显参与了结果。

因此模型可以学习很多不同的投影方向：

```text
某些方向
→ 更关注词义

某些方向
→ 更关注位置

某些方向
→ 同时结合词义和位置
```

这就是为什么两种信息即使相加了，后面的网络依然可以有效利用。

---

<a id="origin-686"></a>
## 10. 可以把它类比成声音叠加

假设一段录音：

$$
y
=
\text{人声}
+
\text{背景音乐}
$$

录音保存下来以后，并不存在：

```text
左边一半是人声

右边一半是背景音乐
```

它们已经叠加成同一个波形了。

但是这并不代表：

> 人声信息和背景音乐信息消失了。

因为二者具有不同的结构特征。

神经网络可以学习：

```text
哪些变化更像人声

哪些变化更像背景音乐
```

Token Embedding 和 Position Embedding 也是类似的。

$$
h=x+p
$$

虽然混在一起了，但它们仍然保留了可利用的结构。

---

<a id="origin-732"></a>
## 11. 模型为什么能学会区分这些信息？

因为训练过程中会出现大量重复模式。

例如同一个词“爱”，可能出现在很多位置：

$$
x_{\text{爱}}+p_1
$$

$$
x_{\text{爱}}+p_2
$$

$$
x_{\text{爱}}+p_3
$$

$$
x_{\text{爱}}+p_{100}
$$

另一方面，同一个位置 2 上，也会出现大量不同的词：

$$
x_{\text{我}}+p_2
$$

$$
x_{\text{爱}}+p_2
$$

$$
x_{\text{浙大}}+p_2
$$

$$
x_{\text{今天}}+p_2
$$

$$
x_{\text{人工智能}}+p_2
$$

模型在大量数据里不断观察这些组合后，就能够学习：

```text
某些稳定变化主要与“词是什么”有关

某些稳定变化主要与“位置在哪里”有关
```

所以：

> 并不是程序员规定“前 100 维表示词义，后 100 维表示位置”。

事实上不存在这样的硬性划分。

而是模型自己学习：

$$
\boxed{
如何解释和使用 x+p
}
$$

---

<a id="origin-800"></a>
## 12. 最重要的一点：不是“拆开”，而是“共同影响”

不要把它理解成：

```text
x + p
  ↓
Transformer
  ↓
重新拆成 x 和 p
```

更准确的理解是：

```text
词义 x
   \
    \
     → 混合表示 → Attention
    /
   /
位置 p
```

模型真正需要的其实可能只是：

> “当前位置这个‘爱’，应该关注前面的‘我’吗？”

只要：

$$
x+p
$$

能够帮助模型回答这个问题，就已经足够。

模型没有必要恢复出原来的：

$$
x
$$

和：

$$
p
$$

---

<a id="origin-850"></a>
## 13. Position Encoding 和 Causal Mask 不要混淆

这两个概念非常容易混在一起。

<a id="origin-854"></a>
### 13.1 Position Encoding

解决的问题是：

> token 在哪里？

例如：

```text
我       第1位
爱       第2位
浙大     第3位
```

它让模型能够学习：

```text
谁在谁前面？

谁在谁后面？

相隔多远？
```

---

<a id="origin-880"></a>
### 13.2 Causal Mask

解决的问题是：

> 当前 token 允许看到哪些位置？

例如 GPT 中：

```text
我  爱  浙大
```

当计算“爱”这个位置时：

```text
我      ✓
爱      ✓
浙大    ×
```

因为“浙大”属于未来 token。

所以：

```text
        我   爱   浙大

我      ✓
爱      ✓   ✓
浙大    ✓   ✓    ✓
```

这是 Causal Mask。

---

因此可以简单记成：

```text
Position Encoding
        ↓
告诉模型：
“它们在哪里”
```

而：

```text
Causal Mask
        ↓
告诉模型：
“哪些位置允许看”
```

这是两个完全不同的问题。

---

<a id="origin-938"></a>
## 14. 为什么有了 Attention 还需要位置编码？

<a id="origin-940"></a>
## 15. 一个很自然的问题

假设一句话是：

```text
I love you
```

在 Attention 中，我们本来就会计算：

```math
S_{I,you}=Q_IK_{you}^T
```

以及：

```math
S_{you,I}=Q_{you}K_I^T
```

而且由于：

```math
W_Q\neq W_K
```

通常还有：

```math
S_{I,you}\neq S_{you,I}
```

所以 Attention 显然已经可以表示一种：

> token 与 token 之间的“关系”。

于是很自然会产生一个问题：

> Attention 既然可以学习“关系”，那为什么不能把“位置关系”也一起学进去？
> 为什么还一定需要 Position Embedding、RoPE 之类的位置编码？

答案是：

> **Attention 当然可以表示位置关系。**
>
> 但前提是：
> **你必须先把“位置信息”提供给 Attention。**

问题不在于 Attention 没能力学习位置关系，而在于：

> 如果 Q 和 K 只由 token 内容产生，那么原始 Attention 的公式里根本没有“位置”这个变量。

---

<a id="origin-994"></a>
## 16. 先看最原始的 Attention

假设第 \(i\) 个 token 的 hidden state 为：

```math
x_i
```

那么：

```math
Q_i=x_iW_Q
```

```math
K_i=x_iW_K
```

两个 token 之间的 Attention Score 为：

```math
S_{ij}=Q_iK_j^T
```

展开：

```math
S_{ij}
=
(x_iW_Q)(x_jW_K)^T
```

观察这个公式。

真正参与运算的是：

```text
x_i
x_j
W_Q
W_K
```

虽然我们写了下标：

```math
i,j
```

但是：

> **\(i\) 和 \(j\) 只是用来标记“这是第几个 token”，并没有真正作为数值进入公式。**

也就是说：

```math
i=1
```

还是：

```math
i=100
```

如果这个位置上的 token hidden state 都是同一个：

```math
x_I
```

那么：

```math
Q_I=x_IW_Q
```

得到的结果还是一样。

---

<a id="origin-1075"></a>
## 17. 用 `I love you` 举例

例如：

```text
I love you
```

假设：

```math
x_I=[1,0]
```

```math
x_{you}=[0,1]
```

为了简化：

```math
W_Q=W_K=I
```

那么：

```math
Q_I=[1,0]
```

```math
K_{you}=[0,1]
```

因此：

```math
S_{I,you}
=
Q_IK_{you}^T
```

即：

```math
S_{I,you}
=
[1,0]
\begin{bmatrix}
0\\
1
\end{bmatrix}
=0
```

---

现在把句子交换一下：

```text
you love I
```

此时 `I` 从第一个位置跑到了第三个位置。

但是如果没有位置编码：

```math
x_I
```

还是：

```math
[1,0]
```

所以：

```math
Q_I=[1,0]
```

而 `you` 还是：

```math
x_{you}=[0,1]
```

所以：

```math
K_{you}=[0,1]
```

于是：

```math
S_{I,you}
=
[1,0]
\begin{bmatrix}
0\\
1
\end{bmatrix}
=0
```

还是完全一样。

---

<a id="origin-1187"></a>
## 18. 问题出在哪里？

对于 Attention 来说：

```text
I love you
```

和：

```text
you love I
```

如果没有任何位置编码，那么 `I` 和 `you` 这一对 token 的内容没有发生变化。

因此：

```math
Q_IK_{you}^T
```

也不会因为它们交换位置就自动改变。

Attention 可以知道：

> `I` 和 `you` 之间存在某种关系。

但是仅靠 token 内容，它不知道：

```text
第一次：
I 在 you 前面

第二次：
I 在 you 后面
```

因为：

> **“前面”和“后面”这个信息根本没有被送进公式。**

---

<a id="origin-1231"></a>
## 19. 所以问题不是 Attention 学不会

这一点非常重要。

错误理解是：

> Attention 只能学语义关系，不能学位置关系。

这个说法并不准确。

更加准确的说法应该是：

> **Attention 本质上只是一个“关系计算器”。**

它完全可以同时学习：

```text
语义关系
位置关系
语法关系
指代关系
距离关系
……
```

但是有一个基本前提：

> **这些信息必须能够从输入中获得。**

如果输入只有：

```text
token 内容
```

那 Attention 就不可能凭空知道：

```text
这个 token 是第 1 个还是第 100 个
```

这就类似于：

```text
输入：
小明
小红
```

你要求一个模型判断：

```text
谁坐在左边？
```

但是你从来没有告诉模型：

```text
座位在哪里
```

那模型再强也没法知道。

---

<a id="origin-1296"></a>
## 20. Position Embedding 做了什么？

最经典的方法非常直接。

原本：

```math
x_i
```

只有 token 内容。

现在给它加入位置向量：

```math
p_i
```

得到：

```math
h_i=x_i+p_i
```

然后再计算：

```math
Q_i=h_iW_Q
```

```math
K_i=h_iW_K
```

也就是：

```math
Q_i=(x_i+p_i)W_Q
```

```math
K_j=(x_j+p_j)W_K
```

Attention Score 就变成：

```math
S_{ij}
=
Q_iK_j^T
```

即：

```math
S_{ij}
=
[(x_i+p_i)W_Q]
[(x_j+p_j)W_K]^T
```

这时候：

```math
p_i
```

和：

```math
p_j
```

已经真正进入了 Attention 计算。

因此：

```text
token 是什么
```

以及：

```text
token 在哪里
```

都会影响最终的 Attention Score。

---

<a id="origin-1387"></a>
## 21. 所以 Attention 最终确实可以包含位置关系

加入位置编码之后，就不能再简单地把 Attention 理解成：

```text
纯语义相关性
```

更加准确的理解应该是：

```text
Attention Score
=
综合关系
```

这个“综合关系”可能包含：

```text
语义关系
+
位置关系
+
语法关系
+
上下文关系
+
其他模型自己学习出来的模式
```

因此：

> **位置编码并不是在 Attention 外面另外搞一套独立的“位置系统”。**

它的真正作用是：

> **把位置这个变量注入 Attention，使 Attention 本身能够把位置关系纳入自己的关系计算。**

---

<a id="origin-1427"></a>
## 22. RoPE 更能体现这一点

RoPE 的思想更加直接。

原本 Attention Score 是：

```math
S_{ij}=q_i^Tk_j
```

RoPE 会根据 token 所在位置对 Q、K 做旋转。

假设：

```math
R_i
```

表示第 \(i\) 个位置对应的旋转矩阵。

那么：

```math
q_i'=R_iq_i
```

```math
k_j'=R_jk_j
```

Attention Score 变成：

```math
S_{ij}
=
(q_i')^Tk_j'
```

代入：

```math
S_{ij}
=
(R_iq_i)^T(R_jk_j)
```

整理：

```math
S_{ij}
=
q_i^TR_i^TR_jk_j
```

而旋转矩阵具有这样的性质：

```math
R_i^TR_j=R_{j-i}
```

因此：

```math
\boxed{
S_{ij}
=
q_i^TR_{j-i}k_j
}
```

这条公式非常关键。

---

<a id="origin-1501"></a>
## 23. RoPE 直接把相对位置放进 Attention

原来的 Attention：

```math
q_i^Tk_j
```

主要取决于：

```text
token 内容
```

加入 RoPE 以后：

```math
q_i^TR_{j-i}k_j
```

里面直接出现了：

```math
j-i
```

而：

```math
j-i
```

正是两个 token 的：

> **相对位置。**

例如：

```text
I love you
```

假设：

```text
I   → 位置 1
love→ 位置 2
you → 位置 3
```

那么 `you` 和 `I` 的位置差是：

```math
1-3=-2
```

或者根据具体采用的 \(i,j\) 方向写成 \(+2\)。

最重要的不是正负号约定，而是：

```text
相距 2 个 token
```

已经进入 Attention Score。

---

<a id="origin-1569"></a>
## 24. 如果交换位置会发生什么？

例如：

```text
I love you
```

与：

```text
you love I
```

虽然：

```text
I
you
```

这两个 token 本身完全没变，

但是它们的：

```math
j-i
```

发生了变化。

所以：

```math
R_{j-i}
```

也发生变化。

最终：

```math
S_{I,you}
```

也可以发生变化。

于是 Attention 就有能力区分：

```text
I 在 you 前面
```

和：

```text
I 在 you 后面
```

---

<a id="origin-1630"></a>
## 25. 一个特别重要的区别

因此千万不要把：

```text
Attention 关系
```

和：

```text
位置关系
```

理解成两个完全独立的模块。

更加准确的关系是：

```text
                 token 内容
                     ↓
                  Q、K
                     ↓
位置关系 ─────────→ Attention Score
                     ↓
              最终综合关系
```

对于 RoPE 来说尤其明显：

```text
token 内容
    +
相对位置
    ↓
Attention Score
```

因此：

> **RoPE 最终修改的就是 Attention 关系本身。**

---

<a id="origin-1674"></a>
## 26. 再回答最开始的问题

最开始的问题是：

> Attention 中本来就有“某种关系”，这个关系难道不能包含位置关系吗？

答案是：

> **完全可以。**

甚至现代 Transformer 正是在这么做。

但必须区分两个概念：

<a id="origin-1688"></a>
### 26.1 Attention 的能力

Attention 可以表达各种关系：

```text
语义
位置
语法
距离
指代
……
```

<a id="origin-1701"></a>
#### 26.1.1 Attention 拥有的信息

如果：

```math
Q_i=x_iW_Q
```

```math
K_j=x_jW_K
```

而：

```math
x_i
```

中完全没有位置信息，

那么 Attention 就没有任何依据判断：

```text
谁在前
谁在后
距离多远
```

因此：

> **不是 Attention 不会学位置，而是你必须先把位置告诉它。**

---

<a id="origin-1735"></a>
## 27. 一个非常直观的类比

可以把 Attention 想象成一个非常聪明的人。

你给他：

```text
I
love
you
```

这三个词，他可以分析：

```text
I 和 love 有关系
love 和 you 有关系
I 和 you 也有关系
```

但是如果你只给他一个无序集合：

```text
{I, love, you}
```

却不告诉他排列顺序，

那么他无法知道原句究竟是：

```text
I love you
```

还是：

```text
you love I
```

位置编码所做的事情，就是告诉他：

```text
I    → 位置1
love → 位置2
you  → 位置3
```

然后 Attention 再把：

```text
词的内容
+
词的位置
```

一起拿来计算关系。

---

<a id="origin-1795"></a>
## 28. Causal Mask 能不能代替位置编码？

这里还有一个容易混淆的问题。

Decoder-only Transformer 中本来就有 Causal Mask。

例如：

```text
            I   love   you

I           ✓    ×      ×

love        ✓    ✓      ×

you         ✓    ✓      ✓
```

所以 `you` 确实知道：

```text
I 和 love 都在自己前面
```

因此 Causal Mask 已经提供了一部分：

> **先后关系。**

但是它提供的信息非常粗。

对于 `you` 来说：

```text
I
love
```

都只是：

```text
可以看到
```

Mask 没有直接告诉它：

```text
love 距离 you = 1

I 距离 you = 2
```

更没有直接表达：

```text
相差 5 个 token

相差 100 个 token
```

因此：

```text
Causal Mask
```

主要解决：

> **能不能看。**

而位置编码 / RoPE 解决：

> **在哪里、距离多远、相对位置是什么。**

二者作用并不相同。

---

<a id="origin-1872"></a>
## 29. 最终总结

可以把整个问题压缩成下面几句话。

<a id="origin-1876"></a>
### 29.1 第一层理解

Attention 本质上负责：

```text
token 与 token 之间的关系
```

这种关系当然可以包括：

```text
位置关系
```

---

<a id="origin-1892"></a>
### 29.2 第二层理解

但是如果：

```math
Q_i=x_iW_Q
```

```math
K_j=x_jW_K
```

其中只有 token 内容，没有位置，

那么：

```math
Q_iK_j^T
```

就不可能凭空知道：

```text
i 和 j 相差几个位置
```

---

<a id="origin-1920"></a>
### 29.3 第三层理解

Position Embedding / RoPE 的目的不是：

> 再搞一套和 Attention 无关的东西。

而是：

> **把位置变量送进 Attention。**

于是最终：

```text
语义信息
+
位置信息
        ↓
Attention
        ↓
综合关系
```

---

<a id="origin-1944"></a>
### 29.4 第四层理解：RoPE

RoPE 后：

```math
\boxed{
S_{ij}=q_i^TR_{j-i}k_j
}
```

这里：

```math
j-i
```

已经直接进入 Attention Score。

因此：

> **现代 Attention 中的“关系”，本来就是可以同时包含语义关系和位置关系的。**

---

<a id="origin-1968"></a>
## 30. 一句话总结

> **Attention 是一个“关系计算器”，它当然可以学习位置关系；但如果输入里没有位置变量，它就无法凭空知道位置。Position Encoding 和 RoPE 的作用，就是把位置关系注入 Attention，使最终的 Attention Score 同时反映 token 内容与位置关系。**

还可以进一步浓缩成：

```text
Attention 决定“关系怎么算”。

位置编码决定“位置这个信息有没有被提供给 Attention”。
```


---

<a id="origin-1983"></a>
## 31. RoPE 原理：从位置编码到相对位置

RoPE 这一块最关键的不是先背公式，而是把下面这条逻辑真正想明白：

> **Attention 本身能判断“谁和谁内容相关”，但它天然不知道“谁在前、谁在后、距离多远”；RoPE 的做法不是把位置直接加到 hidden state 上，而是根据 token 的位置去旋转 Q、K，使得 \(Q\cdot K\) 在计算相关性时自然同时包含“内容关系 + 相对位置关系”。**

---

<a id="origin-1991"></a>
## 32. 为什么 Attention 需要位置编码？

先回到最基本的问题。

假设有：

```text
我 爱 你
```

和：

```text
你 爱 我
```

Embedding 以后，每个 token 都有自己的向量。

Attention 做：

```math
QK^T
```

它本质上是在问：

> 当前 token 和其他 token 的内容匹配程度是多少？

但单纯的 Self-Attention 并没有天然的“第几个位置”的概念。

所以我们需要额外告诉模型：

```text
“我”在位置 0
“爱”在位置 1
“你”在位置 2
```

否则：

```text
我 爱 你
```

和：

```text
你 爱 我
```

仅靠“有哪些 token”是不够的。

---

<a id="origin-2045"></a>
## 33. 最直观的位置编码方法

一种非常直接的方法就是：

```math
x'=x+PE(position)
```

也就是：

```text
Token Embedding
      +
Position Embedding
      ↓
新的 hidden state
```

例如：

```text
“我”的语义向量
+
“位置0”的向量
```

得到：

```text
“位于位置0的我”
```

这种方法可以理解成：

> **直接把位置信息加进 token 表示。**

---

<a id="origin-2083"></a>
## 34. RoPE 的思路不一样

RoPE：

```text
Rotary Position Embedding
旋转位置编码
```

它不是简单做：

```math
x+PE
```

而是：

> **根据 token 所处的位置，把 Q 和 K 旋转一定角度。**

也就是：

```text
hidden state
    ↓
生成 Q、K
    ↓
根据 position
旋转 Q、K
    ↓
Q · K
    ↓
Attention Score
```

---

<a id="origin-2119"></a>
## 35. 什么叫“旋转一个向量”？

先别想高维。

只看二维。

假设：

```math
q=
\begin{bmatrix}
1\\
0
\end{bmatrix}
```

它在坐标系中指向右边：

```text
        y
        ↑
        |
        |
--------+------→ x
             q=(1,0)
```

现在把它逆时针旋转 \(90^\circ\)。

得到：

```math
q'=
\begin{bmatrix}
0\\
1
\end{bmatrix}
```

也就是：

```text
        y
        ↑
        q'
        |
--------+------→ x
```

---

<a id="origin-2170"></a>
## 36. 数学上怎么旋转？

二维旋转矩阵：

```math
R(\theta)
=
\begin{bmatrix}
\cos\theta&-\sin\theta\\
\sin\theta&\cos\theta
\end{bmatrix}
```

一个向量：

```math
x=
\begin{bmatrix}
x_1\\
x_2
\end{bmatrix}
```

旋转以后：

```math
x'
=
R(\theta)x
```

也就是：

```math
\begin{bmatrix}
x'_1\\
x'_2
\end{bmatrix}
=
\begin{bmatrix}
\cos\theta&-\sin\theta\\
\sin\theta&\cos\theta
\end{bmatrix}
\begin{bmatrix}
x_1\\
x_2
\end{bmatrix}
```

所以：

```math
x'_1=x_1\cos\theta-x_2\sin\theta
```

```math
x'_2=x_1\sin\theta+x_2\cos\theta
```

---

<a id="origin-2231"></a>
## 37. RoPE 怎么把“位置”变成旋转？

假设一个基础角度是：

```math
\theta
```

那么：

```text
position = 0
→ 旋转 0θ

position = 1
→ 旋转 1θ

position = 2
→ 旋转 2θ

position = 3
→ 旋转 3θ
```

于是同一个内容如果出现在不同位置：

```text
位置不同
↓
旋转角度不同
↓
Q/K 的方向不同
```

这样位置就进入了 Q、K。

---

<a id="origin-2269"></a>
## 38. 一个最简单的例子

为了方便，假设：

```math
\theta=30^\circ
```

并假设：

```math
q=
\begin{bmatrix}
1\\
0
\end{bmatrix}
```

<a id="origin-2287"></a>
### 38.1 token 在位置 1

旋转：

```math
1\times30^\circ
```

得到：

```math
q_1'
=
\begin{bmatrix}
\cos30^\circ\\
\sin30^\circ
\end{bmatrix}
```

约等于：

```math
q_1'
=
\begin{bmatrix}
0.866\\
0.5
\end{bmatrix}
```

---

<a id="origin-2319"></a>
### 38.2 同一个 token 在位置 2

旋转：

```math
2\times30^\circ=60^\circ
```

得到：

```math
q_2'
=
\begin{bmatrix}
0.5\\
0.866
\end{bmatrix}
```

所以：

```text
内容本身没变：

[1, 0]
```

但：

```text
位置 1
→ [0.866, 0.5]

位置 2
→ [0.5, 0.866]
```

也就是说：

> **位置被编码到了向量的方向里。**

---

<a id="origin-2362"></a>
## 39. 但这看起来只是绝对位置

如果只看到这里，好像只是：

```text
position 1 → 转 θ
position 2 → 转 2θ
position 3 → 转 3θ
```

似乎只是把绝对位置编码进去。

RoPE 真正精妙的地方在于：

> **当旋转后的 Q 和 K 再做点积时，绝对位置会自动转化成相对位置。**

---

<a id="origin-2380"></a>
## 40. 假设 Query 在位置 \(m\)

原始 Query：

```math
q
```

位置：

```math
m
```

旋转以后：

```math
q_m'
=
R(m\theta)q
```

Key 位于位置：

```math
n
```

旋转以后：

```math
k_n'
=
R(n\theta)k
```

Attention 需要计算：

```math
q_m'^Tk_n'
```

代入：

```math
(R(m\theta)q)^T
(R(n\theta)k)
```

---

<a id="origin-2431"></a>
## 41. 最关键的一步

旋转矩阵有一个性质（证明参考下方）：

```math
R(\alpha)^T
=
R(-\alpha)
```

因此：

```math
R(m\theta)^T
=
R(-m\theta)
```

由上可知：

\[
(q'_m)^T k'_n = (R(m\theta)q)^T(R(n\theta)k)
\]

根据：

\[
(AB)^T=B^TA^T
\]

得到：

\[
\boxed{
(R(m\theta)q)^T
=
q^TR(m\theta)^T
}
\]


于是：

```math
q_m'^Tk_n'
=
q^TR(-m\theta)R(n\theta)k
```

旋转矩阵还有另一个性质（证明同样参考下方）：

```math
R(a)R(b)=R(a+b)
```

所以：

```math
R(-m\theta)R(n\theta)
=
R((n-m)\theta)
```

最终：

```math
\boxed{
q_m'^Tk_n'
=
q^TR((n-m)\theta)k
}
```

注意：

原来的：

```math
m
```

和：

```math
n
```

最后只剩下：

```math
\boxed{n-m}
```

也就是：

> **两个 token 之间的相对位置。**

---

<a id="origin-2530"></a>
## 42. 为什么 \(q^T R((n-m)\theta)k\) 看起来像只旋转了 K？

在 RoPE 的推导中，我们最终会得到：

\[
\boxed{
q^T R((n-m)\theta)k
}
\]

乍一看，好像只有 \(k\) 被旋转了，而 \(q\) 没有旋转。

但实际上并不是这样。真正的 RoPE 是：

\[
q'_m=R(m\theta)q
\]

\[
k'_n=R(n\theta)k
\]

也就是说：

```text
Q 在位置 m → 旋转 mθ
K 在位置 n → 旋转 nθ
```

所以 **Q 和 K 实际上都进行了旋转。**

之所以最后看起来只旋转了 K，是因为数学上把两个旋转之间的“相对关系”化简出来了。

---

<a id="origin-2565"></a>
### 42.1 为什么最后只剩一个旋转矩阵？

因为：

\[
R(-m\theta)R(n\theta)
\]

代表的是：

```text
先把 mθ 抵消掉
↓
再看 nθ
↓
最终只剩 (n-m)θ
```

所以原本：

```text
Q 旋转 mθ
K 旋转 nθ
```

在比较二者时，可以等价成：

```text
Q 不动
K 相对于 Q 旋转 (n-m)θ
```

因此：

\[
\boxed{
q^T R((n-m)\theta)k
}
\]

并不是说 RoPE 只给 K 做了旋转，而是说：

> **在计算 Q 和 K 的相对关系时，可以把 Q 当成参考系，于是只需要描述 K 相对于 Q 旋转了多少。**

---

<a id="origin-2611"></a>
## 43. 用一个具体角度例子理解

假设：

```text
Q 旋转了 30°
K 旋转了 80°
```

也就是：

\[
q'=R(30^\circ)q
\]

\[
k'=R(80^\circ)k
\]

我们真正关心的是 Q 和 K 之间相差多少角度：

\[
80^\circ-30^\circ=50^\circ
\]

如果把整个场景一起向回旋转 \(30^\circ\)：

```text
Q：30° - 30° = 0°
K：80° - 30° = 50°
```

于是原来的：

```text
Q 在 30°
K 在 80°
```

就等价于：

```text
Q 在 0°
K 在 50°
```

因此：

\[
(R(30^\circ)q)^T(R(80^\circ)k)
=
q^TR(50^\circ)k
\]

---

<a id="origin-2667"></a>
## 44. 所以 \(q^TR((n-m)\theta)k\) 应该怎么读？

不要理解成：

> “只对 K 做了 RoPE。”

而应该理解成：

> **站在 Q 的参考系里，K 相对于 Q 旋转了 \((n-m)\theta\)。**

也就是：

```text
实际执行：
Q → 旋转 mθ
K → 旋转 nθ

但是比较二者时：
只关心 nθ - mθ
```

所以：

\[
\boxed{
n\theta-m\theta=(n-m)\theta
}
\]

---

<a id="origin-2698"></a>
## 45. 其实也可以反过来，只看 Q 相对 K

有：

\[
q^TR((n-m)\theta)k
\]

利用：

\[
R(\alpha)^T=R(-\alpha)
\]

也可以写成：

\[
\boxed{
(R((m-n)\theta)q)^Tk
}
\]

这时候可以理解成：

```text
K 不动
Q 相对于 K 旋转 (m-n)θ
```

所以有两种完全等价的理解：

```text
方式一：以 Q 为参考
Q 不动
K 转 (n-m)θ

方式二：以 K 为参考
K 不动
Q 转 (m-n)θ
```

---

<a id="origin-2741"></a>
## 46. 这正是 RoPE 最核心的地方

原来：

```text
Q 的绝对位置：m
K 的绝对位置：n
```

经过 RoPE：

```text
Q 旋转：mθ
K 旋转：nθ
```

然后进行点积：

```text
mθ 和 nθ
↓
做相对比较
↓
nθ - mθ
↓
(n-m)θ
```

所以：

\[
\boxed{
m,n \longrightarrow n-m
}
\]

也就是说：

> **RoPE 虽然分别根据绝对位置旋转 Q 和 K，但在 Attention 点积中最终自然表现为相对位置。**

---

<a id="origin-2783"></a>
## 47. 从逆矩阵、正交矩阵到 RoPE 中的 \(R(\alpha)^T=R(-\alpha)\)

<a id="origin-2785"></a>
### 47.1 什么是逆矩阵？

先从普通数字开始。

例如：

```math
5\times\frac15=1
```

所以：

```math
\frac15
```

可以理解成：

> 5 的逆。

矩阵中也有类似概念。

假设有矩阵：

```math
A
```

如果存在另一个矩阵：

```math
A^{-1}
```

满足：

```math
AA^{-1}
=
A^{-1}A
=
I
```

那么：

```math
A^{-1}
```

就叫：

> **A 的逆矩阵。**

---

<a id="origin-2841"></a>
### 47.2 什么是矩阵转置？

假设矩阵：

```math
A=
\begin{bmatrix}
a&b\\
c&d
\end{bmatrix}
```

它的转置：

```math
A^T
```

就是：

> 把行和列交换。

所以：

```math
A^T
=
\begin{bmatrix}
a&c\\
b&d
\end{bmatrix}
```

可以简单记成：

```text
第一行 → 第一列
第二行 → 第二列
```

---

<a id="origin-2883"></a>
### 47.3 什么是正交矩阵？

如果一个矩阵：

```math
Q
```

满足：

```math
Q^TQ=I
```

那么它就叫：

> **正交矩阵（Orthogonal Matrix）**

因为：

```math
Q^TQ=I
```

而逆矩阵满足：

```math
Q^{-1}Q=I
```

所以：

```math
\boxed{
Q^{-1}=Q^T
}
```

这就是正交矩阵最重要的性质：

> **逆矩阵直接等于转置矩阵。**

---

<a id="origin-2927"></a>
### 47.4 为什么叫“正交”矩阵？

“正交”可以理解成：

```text
互相垂直
```

正交矩阵的列向量满足两个条件：

1. 每一列长度为 1；
2. 不同列之间互相垂直。

例如：

```math
Q=
\begin{bmatrix}
a&c\\
b&d
\end{bmatrix}
```

两列：

```math
\begin{bmatrix}
a\\b
\end{bmatrix}
```

和：

```math
\begin{bmatrix}
c\\d
\end{bmatrix}
```

都具有：

```text
长度 = 1
```

并且：

```text
点积 = 0
```

所以这两列：

```text
互相垂直
+
都是单位向量
```

这就是“正交”。

---

<a id="origin-2990"></a>
### 47.5 为什么旋转矩阵是正交矩阵？

二维旋转矩阵：

```math
R(\alpha)
=
\begin{bmatrix}
\cos\alpha&-\sin\alpha\\
\sin\alpha&\cos\alpha
\end{bmatrix}
```

看它的第一列：

```math
\begin{bmatrix}
\cos\alpha\\
\sin\alpha
\end{bmatrix}
```

长度：

```math
\sqrt{
\cos^2\alpha+\sin^2\alpha
}
```

因为：

```math
\cos^2\alpha+\sin^2\alpha=1
```

所以：

```math
\text{第一列长度}=1
```

---

第二列：

```math
\begin{bmatrix}
-\sin\alpha\\
\cos\alpha
\end{bmatrix}
```

长度：

```math
\sqrt{
\sin^2\alpha+\cos^2\alpha
}
=
1
```

---

两列做点积：

```math
\cos\alpha(-\sin\alpha)
+
\sin\alpha\cos\alpha
```

得到：

```math
-\cos\alpha\sin\alpha
+
\sin\alpha\cos\alpha
=
0
```

所以：

```text
第一列长度 = 1
第二列长度 = 1
两列点积 = 0
```

因此旋转矩阵是正交矩阵。

所以：

```math
\boxed{
R(\alpha)^{-1}
=
R(\alpha)^T
}
```

---

<a id="origin-3095"></a>
### 47.6 现在和负角度连起来

前面已经知道：

```math
R(\alpha)^{-1}
=
R(-\alpha)
```

同时因为旋转矩阵是正交矩阵：

```math
R(\alpha)^{-1}
=
R(\alpha)^T
```

两个式子右边都等于：

```math
R(\alpha)^{-1}
```

所以：

```math
\boxed{
R(\alpha)^T
=
R(-\alpha)
}
```

整个逻辑就是：

```text
旋转 α 的逆操作
=
旋转 -α
        ↓
R(α)⁻¹ = R(-α)


旋转矩阵是正交矩阵
        ↓
R(α)⁻¹ = R(α)ᵀ


所以：
R(α)ᵀ = R(-α)
```

---

<a id="origin-3150"></a>
### 47.7 也可以直接从公式验证

旋转矩阵：

```math
R(\alpha)
=
\begin{bmatrix}
\cos\alpha&-\sin\alpha\\
\sin\alpha&\cos\alpha
\end{bmatrix}
```

转置：

```math
R(\alpha)^T
=
\begin{bmatrix}
\cos\alpha&\sin\alpha\\
-\sin\alpha&\cos\alpha
\end{bmatrix}
```

再看：

```math
R(-\alpha)
=
\begin{bmatrix}
\cos(-\alpha)&-\sin(-\alpha)\\
\sin(-\alpha)&\cos(-\alpha)
\end{bmatrix}
```

利用：

```math
\cos(-\alpha)=\cos\alpha
```

以及：

```math
\sin(-\alpha)=-\sin\alpha
```

得到：

```math
R(-\alpha)
=
\begin{bmatrix}
\cos\alpha&\sin\alpha\\
-\sin\alpha&\cos\alpha
\end{bmatrix}
```

正好就是：

```math
R(\alpha)^T
```

所以：

```math
\boxed{
R(\alpha)^T
=
R(-\alpha)
}
```

---



<a id="origin-3228"></a>
## 48. 为什么 \(R(a)R(b)=R(a+b)\)？

二维旋转矩阵：

```math
R(a)
=
\begin{bmatrix}
\cos a&-\sin a\\
\sin a&\cos a
\end{bmatrix}
```

```math
R(b)
=
\begin{bmatrix}
\cos b&-\sin b\\
\sin b&\cos b
\end{bmatrix}
```

这里：

```text
R(b)
```

表示先旋转：

```math
b
```

然后再乘：

```text
R(a)
```

表示再旋转：

```math
a
```

所以：

```text
先转 b
↓
再转 a
↓
总共转 a+b
```

因此直观上：

```math
\boxed{
R(a)R(b)=R(a+b)
}
```

---

<a id="origin-3294"></a>
### 48.1 先用一个最简单的例子理解

假设一个向量：

```math
x=
\begin{bmatrix}
1\\
0
\end{bmatrix}
```

它原来指向右边。

先旋转：

```math
b=30^\circ
```

再旋转：

```math
a=60^\circ
```

那么总旋转角：

```math
30^\circ+60^\circ
=
90^\circ
```

所以：

```math
R(60^\circ)
R(30^\circ)
x
=
R(90^\circ)x
```

也就是说：

```text
原向量
↓
转30°
↓
再转60°
↓
最终和直接转90°完全一样
```

因此：

```math
\boxed{
R(60^\circ)R(30^\circ)
=
R(90^\circ)
}
```

---

<a id="origin-3362"></a>
### 48.2 为什么矩阵相乘可以理解成“连续做两个操作”？

假设：

```math
y=Bx
```

表示先对：

```math
x
```

做变换：

```math
B
```

然后：

```math
z=Ay
```

表示再做：

```math
A
```

代入：

```math
z
=
A(Bx)
```

根据矩阵乘法：

```math
z
=
(AB)x
```

所以：

> **矩阵乘法 \(AB\)，本身就表示“先执行 B，再执行 A”。**

因此：

```math
R(a)R(b)
```

表示：

```text
先旋转 b
↓
再旋转 a
```

总效果自然就是：

```math
a+b
```

---

<a id="origin-3436"></a>
### 48.3 直接从矩阵乘法证明

有：

```math
R(a)
=
\begin{bmatrix}
\cos a&-\sin a\\
\sin a&\cos a
\end{bmatrix}
```

以及：

```math
R(b)
=
\begin{bmatrix}
\cos b&-\sin b\\
\sin b&\cos b
\end{bmatrix}
```

相乘：

```math
R(a)R(b)
=
\begin{bmatrix}
\cos a&-\sin a\\
\sin a&\cos a
\end{bmatrix}
\begin{bmatrix}
\cos b&-\sin b\\
\sin b&\cos b
\end{bmatrix}
```

---

<a id="origin-3477"></a>
### 48.4 左上角

矩阵乘法左上角：

```math
\cos a\cos b
+
(-\sin a)\sin b
```

也就是：

```math
\cos a\cos b
-
\sin a\sin b
```

而三角函数和角公式：

```math
\cos(a+b)
=
\cos a\cos b
-
\sin a\sin b
```

所以左上角：

```math
\boxed{
\cos(a+b)
}
```

---

<a id="origin-3515"></a>
### 48.5 右上角

右上角：

```math
\cos a(-\sin b)
+
(-\sin a)\cos b
```

得到：

```math
-\cos a\sin b
-
\sin a\cos b
```

而：

```math
\sin(a+b)
=
\sin a\cos b
+
\cos a\sin b
```

所以：

```math
-\cos a\sin b
-
\sin a\cos b
=
-\sin(a+b)
```

因此右上角：

```math
\boxed{
-\sin(a+b)
}
```

---

<a id="origin-3563"></a>
### 48.6 左下角

左下角：

```math
\sin a\cos b
+
\cos a\sin b
```

根据和角公式：

```math
\sin(a+b)
=
\sin a\cos b
+
\cos a\sin b
```

所以：

```math
\boxed{
\sin(a+b)
}
```

---

<a id="origin-3593"></a>
### 48.7 右下角

右下角：

```math
\sin a(-\sin b)
+
\cos a\cos b
```

得到：

```math
-\sin a\sin b
+
\cos a\cos b
```

也就是：

```math
\cos a\cos b
-
\sin a\sin b
```

所以：

```math
\boxed{
\cos(a+b)
}
```

---

<a id="origin-3629"></a>
### 48.8 拼起来

因此：

```math
R(a)R(b)
=
\begin{bmatrix}
\cos(a+b)&-\sin(a+b)\\
\sin(a+b)&\cos(a+b)
\end{bmatrix}
```

而根据旋转矩阵定义：

```math
R(a+b)
=
\begin{bmatrix}
\cos(a+b)&-\sin(a+b)\\
\sin(a+b)&\cos(a+b)
\end{bmatrix}
```

所以：

```math
\boxed{
R(a)R(b)
=
R(a+b)
}
```

---

<a id="origin-3665"></a>
## 49. 用数字彻底理解

假设：

```math
q=k=
\begin{bmatrix}
1\\
0
\end{bmatrix}
```

仍然设：

```math
\theta=30^\circ
```

现在：

```text
Query 位置 = 2
Key   位置 = 5
```

---

<a id="origin-3692"></a>
### 49.1 Query 旋转

位置 2：

```math
2\times30^\circ=60^\circ
```

所以：

```math
q_2'
=
\begin{bmatrix}
\cos60^\circ\\
\sin60^\circ
\end{bmatrix}
=
\begin{bmatrix}
0.5\\
0.866
\end{bmatrix}
```

---

<a id="origin-3718"></a>
### 49.2 Key 旋转

位置 5：

```math
5\times30^\circ=150^\circ
```

所以：

```math
k_5'
=
\begin{bmatrix}
\cos150^\circ\\
\sin150^\circ
\end{bmatrix}
```

即：

```math
k_5'
=
\begin{bmatrix}
-0.866\\
0.5
\end{bmatrix}
```

---

<a id="origin-3750"></a>
## 50. 两者做点积

```math
q_2'\cdot k_5'
```

得到：

```math
0.5\times(-0.866)
+
0.866\times0.5
```

也就是：

```math
-0.433+0.433=0
```

为什么？

因为两个向量之间的角度差：

```math
150^\circ-60^\circ
=
90^\circ
```

而：

```math
\cos90^\circ=0
```

所以点积为 0。

---

<a id="origin-3790"></a>
## 51. 整体往后移动，相对关系不变

原来：

```text
Query = position 2
Key   = position 5
```

距离：

```math
5-2=3
```

现在整体往后移动：

```text
Query = position 7
Key   = position 10
```

距离还是：

```math
10-7=3
```

它们的旋转角度分别变成：

```math
7\times30^\circ
```

和：

```math
10\times30^\circ
```

但是角度差仍然：

```math
(10-7)\times30^\circ
=
90^\circ
```

所以点积关系仍然一样。

因此：

```text
位置 2 和位置 5
距离 = 3

位置 7 和位置 10
距离 = 3

位置 100 和位置 103
距离 = 3
```

都会呈现相同形式的相对位置关系。

---

<a id="origin-3857"></a>
## 52. 为什么相对位置特别适合语言？

因为语言中的很多关系更依赖：

```text
距离
```

而不是：

```text
绝对位置编号
```

例如：

```text
我 非常 喜欢 苹果
```

真正有意义的是：

```text
“我”和“喜欢”相隔多远
```

而不是：

```text
“我”是不是整篇文章第 137 个 token
```

如果前面加几个词：

```text
昨天，我非常喜欢苹果。
```

整个短语整体后移。

但是：

```text
我 ↔ 喜欢
```

之间的相对关系基本没变。

所以：

```math
\boxed{
Relative\ Position
}
```

非常适合语言建模。

---

<a id="origin-3917"></a>
## 53. RoPE 最漂亮的一点

RoPE 没有直接显式计算：

```text
distance = position_K - position_Q
```

而是：

```text
position
↓
转换成旋转角度
↓
旋转 Q/K
↓
正常做 Q·K
↓
点积自动出现 n-m
```

因此可以记成：

> **RoPE 先把绝对位置编码成旋转角度，再利用旋转后的 Q、K 做点积，使 Attention Score 自然依赖相对位置。**

---

<a id="origin-3945"></a>
## 54. 为什么只旋转 Q 和 K？

Attention：

```math
Attention(Q,K,V)
=
softmax
\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
```

我们之前可以把 Q、K、V 理解成：

```text
Q：
我在找什么？

K：
我有什么特征，可以被谁找到？

V：
如果你决定关注我，
我真正提供什么内容？
```

决定：

```text
“应该关注谁？”
```

的是：

```math
QK^T
```

所以位置最需要影响的是：

```text
匹配关系
```

也就是：

```text
Q 和 K
```

而不是直接修改 V。

可以理解成：

> **位置主要影响“取谁、取多少”；V 负责“真正取回来什么内容”。**

---

<a id="origin-4004"></a>
## 55. Q/K 不是二维，而是高维怎么办？

实际模型中，一个 Attention Head 可能有很多维。

例如：

```text
head_dim = 96
```

RoPE 的办法是：

> **每两个维度分成一组。**

例如：

```math
q=
[q_0,q_1,q_2,q_3,q_4,q_5,\dots]
```

拆成：

```text
(q0, q1)
(q2, q3)
(q4, q5)
...
```

96 维：

```math
96/2=48
```

所以可以拆成：

```text
48 个二维平面
```

---

<a id="origin-4048"></a>
## 56. 每一对都做二维旋转

例如：

```text
(q0, q1)
```

做：

```math
R(position\times\theta_0)
```

下一对：

```text
(q2, q3)
```

做：

```math
R(position\times\theta_1)
```

下一对：

```text
(q4, q5)
```

做：

```math
R(position\times\theta_2)
```

……

所以：

```text
96维 Q
↓
拆成48个二维平面

(q0,q1)   → 旋转
(q2,q3)   → 旋转
(q4,q5)   → 旋转
...
(q94,q95) → 旋转
```

---

<a id="origin-4104"></a>
## 57. 为什么每一对不用同一个旋转速度？

真实 RoPE 中，不是：

```text
所有维度：
position × 同一个 θ
```

而是：

```text
第 1 对维度 → 一个频率
第 2 对维度 → 另一个频率
第 3 对维度 → 再一个频率
...
```

可以直观理解成：

```text
有些维度旋转得快
→ 对短距离位置变化更敏感

有些维度旋转得慢
→ 可以表达更长距离的位置关系
```

这和经典正弦位置编码使用不同频率的 sin/cos 思想很接近。

---

<a id="origin-4136"></a>
## 58. 一个直观类比：很多块钟

可以把一个 Attention Head 想成很多块钟。

例如：

```text
第1块钟：转得非常快
第2块钟：稍微慢一点
第3块钟：更慢
...
第48块钟：转得很慢
```

position 每增加 1：

```text
所有钟都会向前转
```

但旋转速度不一样。

所以一个位置不是由：

```text
一个角度
```

表示，

而是由：

```text
很多不同频率的角度组合
```

表示。

---

<a id="origin-4176"></a>
## 59. cos 和 sin 是干什么的？

回到二维旋转公式：

```math
x'_1
=
x_1\cos\theta
-
x_2\sin\theta
```

```math
x'_2
=
x_1\sin\theta
+
x_2\cos\theta
```

所以只要知道：

```math
\cos(position\times\theta_i)
```

和：

```math
\sin(position\times\theta_i)
```

就可以完成旋转。

因此代码通常会提前计算：

```python
freqs_cos, freqs_sin = precompute_freqs_cis(...)
```

本质上就是：

> 提前把各个位置、各个频率所需要的 cos/sin 算出来。

---

<a id="origin-4222"></a>
## 60. 为什么要 precompute？

因为：

```text
position
frequency
cos
sin
```

这些值不需要每次 forward 都重复计算。

例如最大位置：

```text
32768
```

每个 head 有：

```text
96维
→ 48对
```

可以预先准备：

```text
position 0：
48组 cos/sin

position 1：
48组 cos/sin

position 2：
48组 cos/sin

...

position 32767：
48组 cos/sin
```

训练时直接取需要的部分即可。

---

<a id="origin-4270"></a>
## 61. RoPE 在 Attention 中的位置

完整流程：

```text
hidden state
     ↓
Q/K/V Linear Projection
     ↓
Q、K
     ↓
RoPE
     ↓
加入位置信息
     ↓
QKᵀ
     ↓
÷ √d_k
     ↓
Causal Mask
     ↓
Softmax
     ↓
× V
     ↓
Attention Output
```

所以 RoPE 的位置非常明确：

> **生成 Q/K 之后，计算 Attention Score 之前。**

---

<a id="origin-4304"></a>
## 62. RoPE 和 \(1/\sqrt{d_k}\) 不是一回事

这两个操作都在 Attention 附近，但解决的问题完全不同。

RoPE：

```text
解决：
token 在哪里？
两个 token 相隔多远？
```

而：

```math
\frac1{\sqrt{d_k}}
```

解决：

```text
Q·K 维度很多
↓
点积数值尺度随维度增大
↓
需要缩放
```

所以：

```math
\boxed{
RoPE=\text{位置信息}
}
```

```math
\boxed{
1/\sqrt{d_k}=\text{数值尺度控制}
}
```

---

<a id="origin-4348"></a>
## 63. RoPE 会不会改变向量长度？

不会。

旋转只改变方向，不改变长度。

例如：

```math
q=[1,0]
```

长度：

```math
\|q\|=1
```

旋转 \(60^\circ\)：

```math
q'=[0.5,0.866]
```

长度：

```math
\sqrt{0.5^2+0.866^2}
\approx1
```

所以：

```math
\boxed{
\|R(\theta)q\|=\|q\|
}
```

也就是说：

> **RoPE 主要通过改变 Q/K 的方向加入位置，而不是通过简单放大或缩小向量。**

---

<a id="origin-4393"></a>
## 64. 最直观的教学例子

假设：

```math
q=k=[1,0]
```

没有 RoPE 时：

```math
q\cdot k=1
```

无论两个 token：

```text
相隔 1 个位置
```

还是：

```text
相隔 100 个位置
```

如果内容向量相同：

```math
q\cdot k
```

都还是：

```math
1
```

Attention 看不出距离。

---

加入 RoPE。

假设每个位置旋转：

```math
30^\circ
```

<a id="origin-4443"></a>
### 64.1 相差 1 个位置

角度差：

```math
30^\circ
```

点积：

```math
\cos30^\circ
\approx0.866
```

<a id="origin-4458"></a>
#### 64.1.1 相差 2 个位置

角度差：

```math
60^\circ
```

点积：

```math
\cos60^\circ
=0.5
```

<a id="origin-4473"></a>
#### 64.1.2 相差 3 个位置

角度差：

```math
90^\circ
```

点积：

```math
\cos90^\circ
=0
```

因此：

```text
内容完全相同

距离 1 → score 0.866
距离 2 → score 0.5
距离 3 → score 0
```

这个例子能直观说明：

> **RoPE 让 QK 的匹配不仅依赖内容，也能依赖相对位置。**

注意：

> 真实模型有很多维度和很多不同频率，因此并不是“距离越远，score 一定越低”。

这个例子只是为了帮助理解机制。

---

<a id="origin-4510"></a>
## 65. 不要误解成“越近一定越重要”

RoPE 并不是：

```text
距离近
→ Attention 一定大

距离远
→ Attention 一定小
```

真正的情况是：

```math
\boxed{
Attention\ Score
=
\text{内容关系和位置关系共同作用}
}
```

一个距离很远的 token，如果内容非常重要：

```text
模型仍然可以高度关注它
```

RoPE 只是让模型具有：

> **利用相对位置进行判断的能力。**

---

<a id="origin-4544"></a>
## 66. RoPE 是训练出来的吗？

RoPE 的：

```text
sin/cos
旋转规则
```

通常不是模型通过训练自己学出来的。

而是根据：

```text
position
frequency
```

通过公式生成。

真正训练的是：

```text
W_Q
W_K
```

也就是说：

```text
RoPE：
提供位置几何结构

W_Q / W_K：
学习如何利用这种位置结构
```

---

<a id="origin-4583"></a>
## 67. 这和 SiLU / Gate 的关系很像

之前讲 SwiGLU 时：

```text
SiLU 本身不是学出来的
↓
W_gate 是训练出来的
↓
模型学会怎样利用 SiLU
```

RoPE 也类似：

```text
sin/cos 旋转规则
不是模型自己发明的
↓
它是人工设计好的结构
↓
W_Q / W_K 在训练中学习
↓
怎样利用这种位置结构
```

也就是说：

> **RoPE 本身是人为提供的结构归纳偏置，模型通过训练学习如何使用它。**

---

<a id="origin-4614"></a>
## 68. 为什么不直接给位置一个数字？

例如：

```text
位置 0 → 0
位置 1 → 1
位置 2 → 2
位置 3 → 3
```

这种绝对编号本身，并不会自然让 Attention 得到：

```text
位置 100
和
位置 101
```

之间：

```text
距离 = 1
```

的结构。

而 RoPE 利用：

```math
R(m\theta)^TR(n\theta)
=
R((n-m)\theta)
```

从数学上天然得到：

```math
n-m
```

这就是它非常漂亮的地方。

---

<a id="origin-4659"></a>
## 69. 整个 RoPE 故事线

可以把全过程串成：

```text
Self-Attention
只能根据内容计算 Q·K
↓
不知道 token 的顺序和距离
↓
需要加入 Position Information
↓
传统方法可以：
Embedding + Position Embedding
↓
RoPE 换一种思路：
不直接修改 token embedding
↓
生成 Q、K
↓
根据 token position
旋转 Q、K
↓
position m：
Q 旋转 mθ

position n：
K 旋转 nθ
↓
二者做点积
↓
R(mθ)ᵀR(nθ)
↓
R((n-m)θ)
↓
Attention Score
自然包含相对位置 n-m
```

所以：

```math
\boxed{
RoPE
=
\text{把位置编码成 Q/K 的旋转角度}
}
```

而它最精妙的地方是：

```math
\boxed{
\text{绝对位置经过 QK 点积以后，自然转化为相对位置}
}
```

---

<a id="origin-4718"></a>
## 70. 最后一句话

如果只记一句：

> **RoPE 的核心不是“给 token 加一个位置数字”，而是根据 token 的位置旋转 Q 和 K，使 Attention 在计算 \(Q\cdot K\) 时，不仅知道“内容是否匹配”，还自然知道“两个 token 相隔多远”。**

进一步压缩：

```text
Attention：
谁和谁内容相关？

RoPE：
在这个匹配过程中，
再把“谁离谁多远”一起考虑进去。
```
---

<a id="origin-4736"></a>
## 71. RoPE 角度不是只有 360° 吗？位置重合怎么办？

这个问题非常关键。

因为旋转角度确实是周期的：

```math
360^\circ = 2\pi\ \text{rad}
```

并且：

```math
\sin(\theta+2\pi)=\sin\theta
```

```math
\cos(\theta+2\pi)=\cos\theta
```

所以如果只看**一个二维旋转平面**，确实会发生：

> 转一圈以后，方向重新回到原来的位置。

---

<a id="origin-4762"></a>
## 72. 单个频率确实会发生“重合”

假设某一组二维维度：

```math
\omega=90^\circ/token
```

那么：

```text
position 0
→ 0°

position 1
→ 90°

position 2
→ 180°

position 3
→ 270°

position 4
→ 360°
→ 等价于 0°
```

所以：

```math
position=0
```

和：

```math
position=4
```

在这一组二维维度上完全一样。

也就是说：

```text
单独一个旋转频率
确实存在周期重复
```

---

<a id="origin-4813"></a>
## 73. 为什么这不会让 RoPE 立刻失效？

因为 RoPE 并不是只用：

```text
一个 ω
```

而是使用很多不同的频率：

```text
ω₀
ω₁
ω₂
ω₃
...
```

每一组二维维度的旋转速度都不同。

例如为了方便，假设有三个频率：

```text
第一组：
每个 token 转 90°

第二组：
每个 token 转 60°

第三组：
每个 token 转 10°
```

---

<a id="origin-4848"></a>
## 74. position 0 时

三个二维平面的角度：

```text
第一组：0°
第二组：0°
第三组：0°
```

所以整个位置可以粗略记成：

```text
position 0
=
(0°, 0°, 0°)
```

---

<a id="origin-4868"></a>
## 75. position 4 时

第一组：

```math
4\times90^\circ=360^\circ
```

等价于：

```text
0°
```

第二组：

```math
4\times60^\circ=240^\circ
```

第三组：

```math
4\times10^\circ=40^\circ
```

所以：

```text
position 4
=
(0°, 240°, 40°)
```

虽然第一组已经和 position 0 重合：

```text
第一组：

position 0 → 0°
position 4 → 0°
```

但是其他组没有：

```text
position 0：

(0°, 0°, 0°)


position 4：

(0°, 240°, 40°)
```

因此整体仍然完全不同。

---

<a id="origin-4928"></a>
## 76. 所以真正的位置不是“一个角度”

这是理解 RoPE 最重要的一点。

不要理解成：

```text
position 100
→ 一个角度
```

而应该理解成：

```text
position 100
→ 很多组不同频率的角度
```

例如：

```text
position 100：

第1组 → 角度 A
第2组 → 角度 B
第3组 → 角度 C
第4组 → 角度 D
...
```

最终位置由：

```math
\boxed{
(\phi_0,\phi_1,\phi_2,\ldots)
}
```

这一整组角度共同表示。

其中：

```math
\phi_i=m\omega_i
```

---


<a id="origin-4977"></a>
## 77. 另一个例子：单个频率确实可能把两个不同距离看成一样

假设某一组二维 RoPE 的旋转频率是：

\[
\omega=60^\circ/token
\]

也就是说：

> token 的相对距离每增加 1，这一组二维向量就多旋转 \(60^\circ\)。

在 Attention 中，我们真正关心的是 Query 和 Key 的相对位置：

\[
\Delta m=n-m
\]

这一组频率对应的相对旋转角度就是：

\[
\Delta\phi
=
\Delta m\cdot\omega
\]

---

<a id="origin-5005"></a>
## 78. 例子：距离 7 和距离 607

我们来看一个最终仍然有明显角度的情况。

---

<a id="origin-5011"></a>
### 78.1 距离 7

假设两个 token 相隔：

\[
\Delta m=7
\]

那么这一组 RoPE 频率产生的相对角度：

\[
\Delta\phi
=
7\times60^\circ
=
420^\circ
\]

因为：

\[
420^\circ
=
360^\circ+60^\circ
\]

旋转一整圈以后，还剩：

\[
60^\circ
\]

所以：

\[
420^\circ
\equiv
60^\circ
\]

因此：

\[
\boxed{
R(7\omega)=R(60^\circ)
}
\]

---

<a id="origin-5061"></a>
### 78.2 距离 607

现在两个 token 相隔：

\[
\Delta m=607
\]

那么：

\[
\Delta\phi
=
607\times60^\circ
=
36420^\circ
\]

其中：

\[
36420^\circ
=
101\times360^\circ+60^\circ
\]

也就是说，它已经完整转了 101 圈，然后又多转了：

\[
60^\circ
\]

因此：

\[
36420^\circ
\equiv
60^\circ
\]

于是：

\[
\boxed{
R(607\omega)=R(60^\circ)
}
\]

---

<a id="origin-5111"></a>
## 79. 所以距离 7 和距离 607，在这一组频率上完全一样

我们得到：

\[
\boxed{
R(7\omega)
=
R(607\omega)
}
\]

因为两者最终对应的角度都是：

\[
60^\circ
\]

也就是说：

```text
距离 7
→ 420°
→ 绕一圈以后剩 60°

距离 607
→ 36420°
→ 绕 101 圈以后剩 60°
```

所以对于这一组二维 RoPE 来说：

```text
距离 7
和
距离 607
```

产生了完全相同的相对旋转。

---

<a id="origin-5153"></a>
## 80. 这意味着模型学到的信息也一样吗？

如果我们 **只看这一组 RoPE 频率提供的位置关系信息**，那么：

\[
\boxed{
距离7
\quad\text{和}\quad
距离607
}
\]

**确实无法区分。**

因为：

\[
R(7\omega)=R(607\omega)
\]

所以这一组二维平面给 Attention 提供的相对位置变化完全一样。

可以粗略理解成：

```text
这一组 RoPE 维度：

距离 7
→ “相对角度是 60°”

距离 607
→ “相对角度也是 60°”
```

因此：

> **如果模型只有这一组频率，那么仅从这一组位置编码来看，距离 7 和距离 607 是无法区分的。**

不过要注意：

> 这里只是说“这一组 RoPE 频率提供的位置关系信号一样”，并不是说完整的 Attention 信息一定完全一样。

因为 Query 和 Key 本身还有语义内容，而且真实 RoPE 还有很多其他频率。

---

<a id="origin-5199"></a>
## 81. 为什么 RoPE 不会因此立刻失效？

因为 RoPE 并不是只使用一个：

\[
\omega
\]

而是使用很多不同频率：

\[
\omega_0,\omega_1,\omega_2,\omega_3,\ldots
\]

每一组二维维度的旋转速度都不同。

例如，为了方便理解，我们假设有三组频率：

```text
第一组：60° / token
第二组：10° / token
第三组：1° / token
```

---

<a id="origin-5225"></a>
## 82. 距离 7 时，三组频率分别是什么角度？

<a id="origin-5227"></a>
### 82.1 第一组：60° / token

\[
7\times60^\circ
=
420^\circ
\]

去掉一整圈：

\[
420^\circ\bmod360^\circ
=
60^\circ
\]

---

<a id="origin-5245"></a>
### 82.2 第二组：10° / token

\[
7\times10^\circ
=
70^\circ
\]

---

<a id="origin-5255"></a>
### 82.3 第三组：1° / token

\[
7\times1^\circ
=
7^\circ
\]

所以距离 7 的整体相位组合可以粗略写成：

\[
\boxed{
(60^\circ,\ 70^\circ,\ 7^\circ)
}
\]

---

<a id="origin-5273"></a>
## 83. 距离 607 时呢？

<a id="origin-5275"></a>
### 83.1 第一组：60° / token

\[
607\times60^\circ
=
36420^\circ
\]

去掉完整旋转：

\[
36420^\circ\bmod360^\circ
=
60^\circ
\]

所以第一组还是：

\[
60^\circ
\]

这一组确实和距离 7 撞车了。

---

<a id="origin-5301"></a>
### 83.2 第二组：10° / token

\[
607\times10^\circ
=
6070^\circ
\]

去掉完整的圈：

\[
6070^\circ\bmod360^\circ
=
310^\circ
\]

所以第二组：

\[
310^\circ
\]

---

<a id="origin-5325"></a>
### 83.3 第三组：1° / token

\[
607\times1^\circ
=
607^\circ
\]

去掉一整圈：

\[
607^\circ\bmod360^\circ
=
247^\circ
\]

所以第三组：

\[
247^\circ
\]

最终距离 607 的相位组合：

\[
\boxed{
(60^\circ,\ 310^\circ,\ 247^\circ)
}
\]

---

<a id="origin-5357"></a>
## 84. 现在比较距离 7 和距离 607

距离 7：

\[
\boxed{
(60^\circ,\ 70^\circ,\ 7^\circ)
}
\]

距离 607：

\[
\boxed{
(60^\circ,\ 310^\circ,\ 247^\circ)
}
\]

可以看到：

```text
第一组：
距离 7   → 60°
距离 607 → 60°
```

**这一组确实完全分不出来。**

但是：

```text
第二组：
距离 7   → 70°
距离 607 → 310°

第三组：
距离 7   → 7°
距离 607 → 247°
```

其他频率却明显不同。

所以整体上：

\[
\boxed{
距离7\neq距离607
}
\]

<a id="origin-5407"></a>
## 85. 即使某些维度重合，也不代表 Attention 完全一样

还有一个更重要的问题。

RoPE 只是作用在：

```text
Q
K
```

上。

Attention Score 仍然取决于：

```math
QK^T
```

而 Q、K 本身还来自：

```math
Q=XW_Q
```

```math
K=XW_K
```

其中：

```text
X
```

包含 token 的内容和上下文信息。

所以即使某几个 RoPE 维度的角度碰巧重合：

```text
位置部分某些维度一样
```

也不意味着：

```text
Q 完全一样
K 完全一样
Attention 完全一样
```

因为 token 内容本身可能完全不同。

---

<a id="origin-5462"></a>
## 86. RoPE真正依赖的是“多频率组合”

所以更准确的理解是：

```text
单个二维平面
↓
周期性很强
↓
会重复
```

但：

```text
几十个二维平面
+
几十个不同 ω
↓
组合成一个高维位置模式
```

因此：

```math
\boxed{
\text{单频率会重合}
\neq
\text{整个 RoPE 位置编码会立刻重合}
}
```

---

<a id="origin-5496"></a>
## 87. 那是不是永远不会重合？

不能这么说。

从纯数学角度看：

> 周期函数一定存在重复或近似重复的问题。

尤其当 position 非常非常长时，不同位置的多频率相位组合可能变得更难区分。

这也是长上下文 RoPE 会面临的问题之一。

所以：

```text
RoPE 并不是无限长度都完美
```

而是：

```text
在合理上下文范围内
多频率组合能够非常有效地表达位置
```

超出训练长度以后：

```text
位置越来越长
↓
相位组合进入陌生区域
↓
位置外推变难
```

于是才会出现：

```text
Position Interpolation
YaRN
NTK-aware scaling
```

这类长上下文扩展方法。

---

<a id="origin-5543"></a>
## 88. RoPE 中位置周期重复为什么会产生问题？

在 RoPE（Rotary Position Embedding，旋转位置编码）中，一个非常重要的问题是：

> 如果位置 \(p\) 和位置 \(p+12\) 对应相同的旋转状态，会发生什么？

核心答案是：

> **不同的相对距离可能被映射成相同的位置关系，从而产生“位置混叠（aliasing）”。**

更准确地说，并不是模型完全分不清两个 token，而是：

$$
\boxed{\text{RoPE 无法再帮助模型区分这两个不同的相对距离}}
$$

---

<a id="origin-5561"></a>
## 89. RoPE 真正编码的是相对位置

假设位置 \(p\) 上有一个 Query：

$$
Q_p
$$

位置 \(q\) 上有一个 Key：

$$
K_q
$$

经过 RoPE 旋转之后：

$$
Q'_p=R_pQ_p
$$

$$
K'_q=R_qK_q
$$

Attention Score 中需要计算：

$$
(Q'_p)^TK'_q
$$

代入：

$$
(R_pQ_p)^T(R_qK_q)
$$

得到：

$$
Q_p^TR_p^TR_qK_q
$$

旋转矩阵具有：

$$
R_p^TR_q=R_{q-p}
$$

因此：

$$
(Q'_p)^TK'_q
=
Q_p^TR_{q-p}K_q
$$

注意这里最终出现的是：

$$
\boxed{q-p}
$$

也就是两个 token 之间的**相对距离**。

因此 RoPE 最重要的性质不是告诉模型：

```text
这个 token 在绝对位置 100
```

而是告诉模型：

```text
Query 和 Key 相隔了多少位置
```

---

<a id="origin-5639"></a>
## 90. 如果位置编码每 12 个位置完全重复

为了方便理解，假设有一个极端情况：

$$
R_{p+12}=R_p
$$

那么就意味着旋转具有周期 12。

于是：

$$
R_1=R_{13}
$$

因为：

$$
13=1+12
$$

这意味着从 RoPE 的角度来看：

```text
距离 1
```

和：

```text
距离 13
```

对应的是完全相同的旋转关系。

---

<a id="origin-5677"></a>
## 91. 一个具体例子

假设当前 token 在位置：

$$
20
$$

现在它要关注前面一个 `"apple"`。

<a id="origin-5687"></a>
### 91.1 情况一：apple 很近

```text
位置19：apple
位置20：eat
```

相对距离：

$$
20-19=1
$$

所以对应：

$$
R_1
$$

---

<a id="origin-5708"></a>
### 91.2 情况二：apple 很远

```text
位置7 ：apple
...
位置20：eat
```

相对距离：

$$
20-7=13
$$

对应：

$$
R_{13}
$$

如果旋转周期为 12：

$$
R_{13}=R_1
$$

于是：

```text
距离 1
```

和：

```text
距离 13
```

从 RoPE 提供的位置关系来看：

$$
\boxed{\text{完全一样}}
$$

---

<a id="origin-5754"></a>
## 92. 这会造成什么问题？

原本模型应该可以区分：

```text
apple 就在我前面
```

和：

```text
apple 是很久以前出现的
```

也就是说：

```text
距离 1
```

和：

```text
距离 13
```

应该拥有不同的位置特征。

正常情况下可以理解为：

```text
距离 1  → 位置模式 A
距离 2  → 位置模式 B
距离 3  → 位置模式 C
...
距离13 → 位置模式 M
```

这样模型可以学习：

```text
距离很近的 token
通常具有较强局部联系
```

或者：

```text
某些很远的 token
具有长期依赖关系
```

---

但如果发生周期重复：

```text
距离 1  → 位置模式 A
距离13 → 位置模式 A
```

模型看到：

```text
位置模式 A
```

之后，仅凭 RoPE 无法判断：

```text
这是距离 1
```

还是：

```text
这是距离 13
```

因此发生：

$$
\boxed{\text{相对位置混叠}}
$$

---

<a id="origin-5841"></a>
## 93. 不是两个 token 完全一样

这里需要特别注意。

假设：

```text
位置7 ：apple
位置19：apple
位置20：eat
```

虽然位置 7 和位置 19 的 `"apple"` 是同一个单词，但它们经过前面 Transformer 层之后的 hidden state 不一定完全相同。

也就是说：

$$
K_7\neq K_{19}
$$

因为上下文不同。

所以模型并不是完全分不清：

```text
位置7
```

和：

```text
位置19
```

真正丢失的是：

$$
\boxed{\text{由 RoPE 提供的距离区别}}
$$

也就是说：

> 内容信息可能还能区分它们，但是位置编码本身已经无法说明“一个离我 1 个 token，一个离我 13 个 token”。

---

<a id="origin-5887"></a>
## 94. 为什么这对语言模型很重要？

考虑：

```text
not good
```

这里：

```text
not
```

和：

```text
good
```

非常接近。

模型应该很容易学习：

```text
not
↓
强烈影响
↓
good
```

---

但是另外一种情况：

```text
not
...
中间几千个 token
...
good
```

虽然同样出现：

```text
not
```

和：

```text
good
```

但它们之间的位置关系显然不同。

如果：

$$
R_1=R_{4097}
$$

那么 RoPE 对：

```text
距离 1
```

和：

```text
距离 4097
```

提供的位置特征完全一样。

那么位置编码就无法帮助模型判断：

> 这个 `not` 是紧挨着 `good` 的，还是 4097 个 token 以前出现的？

---

<a id="origin-5971"></a>
## 95. 所以不是“相对位置不明显”

更准确的描述不是：

> 相对位置变得不明显。

而应该是：

$$
\boxed{\text{不同的相对位置变得不可区分}}
$$

也就是：

```text
distance = 1
```

和：

```text
distance = 13
```

被映射到了相同的位置编码模式。

这就是：

$$
\boxed{\text{Position Aliasing}}
$$

即：

> **位置混叠。**

---

<a id="origin-6009"></a>
## 96. 为什么 RoPE 要使用很多不同频率？

如果只有一个旋转频率，那么它一定会周期性重复。

假设：

$$
\theta_p=p\omega
$$

旋转一圈：

$$
2\pi
$$

对应的位置周期为：

$$
T=\frac{2\pi}{\omega}
$$

于是：

$$
R_{p+T}=R_p
$$

所以单独一个频率一定存在周期重复。

---

因此 RoPE 不只使用一个频率，而是使用很多频率：

$$
\omega_1,\omega_2,\omega_3,\dots
$$

每一组二维维度对应不同的旋转速度。

可以理解成：

```text
第1组维度：非常快
第2组维度：比较快
第3组维度：比较慢
...
最后几组：非常慢
```

因此一个距离 \(d\) 的位置特征实际上不是一个角度，而是：

$$
[
d\omega_1,
d\omega_2,
d\omega_3,
\dots
]
$$

---

<a id="origin-6072"></a>
## 97. 类似钟表

可以把它类比成钟表。

如果只有秒针：

```text
00 秒
```

和：

```text
60 秒
```

秒针的位置完全一样。

所以仅仅看秒针：

```text
无法知道过去了 0 秒
还是 60 秒
```

---

但如果同时有：

```text
秒针
+
分针
+
时针
```

那么即使：

```text
秒针回到了原来的位置
```

分针可能已经改变：

```text
秒针：一样
分针：不同
时针：不同
```

于是整体状态仍然可以区分不同时间。

---

RoPE 就类似于：

```text
高速旋转维度 ≈ 秒针
中速旋转维度 ≈ 分针
低速旋转维度 ≈ 时针
```

多个不同频率共同组成一个位置的：

$$
\boxed{\text{相位指纹}}
$$

---

<a id="origin-6143"></a>
## 98. 为什么不能让所有维度都高速旋转？

如果所有维度都在很短的长度内转很多圈，相当于：

```text
全部都是秒针
```

那么所有维度都会频繁发生周期重复。

于是长距离的位置区别能力就会下降。

因此 RoPE 有意同时保留：

```text
高频维度
```

和：

```text
低频维度
```

---

高频维度主要负责：

$$
\boxed{\text{短距离的精确区分}}
$$

例如：

```text
距离 1
距离 2
距离 3
```

变化非常明显。

---

低频维度主要负责：

$$
\boxed{\text{长距离的位置区分}}
$$

例如：

```text
距离 100
距离 1000
距离 10000
```

仍然可以保持不同的相位状态。

---

<a id="origin-6205"></a>
## 99. 最核心的结论

RoPE 中最重要的不是：

```text
某个位置转了多少圈
```

也不是：

```text
有没有覆盖完整的 360°
```

而是：

$$
\boxed{
\text{不同相对距离是否还能产生不同的多频率相位组合}
}
$$

如果：

$$
R_d=R_{d+T}
$$

那么：

```text
距离 d
```

和：

```text
距离 d+T
```

在 RoPE 的位置编码中就无法区分。

因此：

$$
\boxed{
\text{位置周期重复}
\Rightarrow
\text{相对距离混叠}
}
$$

进一步来说：

$$
\boxed{
\text{单个频率必然周期重复，但多个不同频率联合起来，可以大幅降低整体的位置混叠。}
}
$$

所以 RoPE 使用多频率，本质上就是利用：

```text
快指针
+
慢指针
```

共同编码位置，让模型既能精确识别短距离关系，又能区分长距离关系。

---

<a id="origin-6277"></a>
## 100. RoPE 大矩阵、长位置外推与 YaRN 原理

前面已经知道，RoPE 的核心思想是：

> **根据 token 的位置旋转 Q 和 K，使 Attention 在计算 \(Q\cdot K\) 时自然包含相对位置信息。**

但是这里还有三个很容易卡住的问题：

1. 为什么有些资料把 RoPE 写成一个巨大的 \(d\times d\) 矩阵？
2. 这个大矩阵为什么又可以理解成很多个二维小旋转？
3. 如果训练时位置最大只有 2047，推理时为什么会突然出现 10000？YaRN 又是在解决什么？

下面从线性代数开始重新串起来。

---

<a id="origin-6293"></a>
## 101. 先回忆二维旋转

对于一个二维向量：

```math
x=
\begin{bmatrix}
x_1\\
x_2
\end{bmatrix}
```

旋转角度 \(\theta\)：

```math
R(\theta)
=
\begin{bmatrix}
\cos\theta&-\sin\theta\\
\sin\theta&\cos\theta
\end{bmatrix}
```

旋转以后：

```math
x'
=
R(\theta)x
```

也就是：

```math
\begin{bmatrix}
x'_1\\
x'_2
\end{bmatrix}
=
\begin{bmatrix}
\cos\theta&-\sin\theta\\
\sin\theta&\cos\theta
\end{bmatrix}
\begin{bmatrix}
x_1\\
x_2
\end{bmatrix}
```

得到：

```math
x'_1
=
x_1\cos\theta-x_2\sin\theta
```

```math
x'_2
=
x_1\sin\theta+x_2\cos\theta
```

所以：

```text
二维向量
↓
乘一个 2×2 旋转矩阵
↓
得到旋转后的二维向量
```

---

<a id="origin-6368"></a>
## 102. 但是 Q 可能是 96 维，怎么办？

假设为了教学简单一点：

```math
d=6
```

Q 是一个 6 维向量：

```math
q=
\begin{bmatrix}
q_0\\
q_1\\
q_2\\
q_3\\
q_4\\
q_5
\end{bmatrix}
```

RoPE 的思想是：

> **不要试图在一个人类无法想象的 6 维空间里整体旋转，而是把它拆成若干二维平面。**

例如：

```text
第 1 组：
(q0,q1)

第 2 组：
(q2,q3)

第 3 组：
(q4,q5)
```

分别进行二维旋转。

于是：

```text
(q0,q1)
↓
二维旋转 R0

(q2,q3)
↓
二维旋转 R1

(q4,q5)
↓
二维旋转 R2
```

---

<a id="origin-6427"></a>
## 103. 那为什么有些资料写成一个 \(6\times6\) 大矩阵？

因为在线性代数里，这几个独立的二维旋转可以统一写成一个：

> **块对角矩阵（Block Diagonal Matrix）**

例如：

```math
R_m
=
\begin{bmatrix}
R_0&0&0\\
0&R_1&0\\
0&0&R_2
\end{bmatrix}
```

其中每个：

```math
R_i
```

本身都是一个：

```math
2\times2
```

矩阵。

展开以后就是：

```math
R_m=
\begin{bmatrix}
\cos\phi_0&-\sin\phi_0&0&0&0&0\\
\sin\phi_0&\cos\phi_0&0&0&0&0\\
0&0&\cos\phi_1&-\sin\phi_1&0&0\\
0&0&\sin\phi_1&\cos\phi_1&0&0\\
0&0&0&0&\cos\phi_2&-\sin\phi_2\\
0&0&0&0&\sin\phi_2&\cos\phi_2
\end{bmatrix}
```

这是一个：

```math
6\times6
```

大矩阵。

---

<a id="origin-6483"></a>
## 104. 线性代数中的分块矩阵乘法

> **对于块对角矩阵，与分块向量相乘时，各个对角块可以独立地和对应的小向量相乘。**

最简单的形式：

```math
\begin{bmatrix}
A&0\\
0&B
\end{bmatrix}
\begin{bmatrix}
x\\
y
\end{bmatrix}
=
\begin{bmatrix}
Ax\\
By
\end{bmatrix}
```

这就是关键。

---

<a id="origin-6509"></a>
## 105. 为什么成立？直接做一次矩阵乘法

来看：

```math
M=
\begin{bmatrix}
A&0\\
0&B
\end{bmatrix}
```

向量：

```math
v=
\begin{bmatrix}
x\\
y
\end{bmatrix}
```

做矩阵乘法：

```math
Mv
=
\begin{bmatrix}
A&0\\
0&B
\end{bmatrix}
\begin{bmatrix}
x\\
y
\end{bmatrix}
```

根据矩阵乘法规则：

第一块：

```math
Ax+0y
=
Ax
```

第二块：

```math
0x+By
=
By
```

所以：

```math
\boxed{
\begin{bmatrix}
A&0\\
0&B
\end{bmatrix}
\begin{bmatrix}
x\\
y
\end{bmatrix}
=
\begin{bmatrix}
Ax\\
By
\end{bmatrix}
}
```

这就是为什么：

```text
一个大块对角矩阵乘法
```

可以变成：

```text
几个互不干扰的小矩阵乘法
```

---

<a id="origin-6598"></a>
## 106. 放到 RoPE 里就非常清楚了

假设：

```math
q=
\begin{bmatrix}
q_0\\
q_1\\
q_2\\
q_3\\
q_4\\
q_5
\end{bmatrix}
```

把它写成三个二维小向量：

```math
q=
\begin{bmatrix}
q^{(0)}\\
q^{(1)}\\
q^{(2)}
\end{bmatrix}
```

其中：

```math
q^{(0)}
=
\begin{bmatrix}
q_0\\q_1
\end{bmatrix}
```

```math
q^{(1)}
=
\begin{bmatrix}
q_2\\q_3
\end{bmatrix}
```

```math
q^{(2)}
=
\begin{bmatrix}
q_4\\q_5
\end{bmatrix}
```

RoPE 大矩阵：

```math
R_m
=
\begin{bmatrix}
R_0&0&0\\
0&R_1&0\\
0&0&R_2
\end{bmatrix}
```

于是：

```math
R_mq
=
\begin{bmatrix}
R_0q^{(0)}\\
R_1q^{(1)}\\
R_2q^{(2)}
\end{bmatrix}
```

也就是：

```text
大矩阵版本：

        ┌ R0  0   0 ┐
R_m  =  │ 0   R1  0 │
        └ 0   0   R2┘

             ×

        ┌ q0,q1 ┐
        │ q2,q3 │
        └ q4,q5 ┘
```

完全等价于：

```text
(q0,q1) × R0

(q2,q3) × R1

(q4,q5) × R2
```

所以：

```math
\boxed{
\text{一个 }d\times d\text{ 的 RoPE 矩阵}
=
\text{很多个 }2\times2\text{ 旋转块组成的块对角矩阵}
}
```

---

<a id="origin-6713"></a>
## 107. 用一个真正的数字例子

假设：

```math
q=
\begin{bmatrix}
1\\
0\\
0\\
1\\
1\\
1
\end{bmatrix}
```

分成：

```text
第一组：
[1,0]

第二组：
[0,1]

第三组：
[1,1]
```

为了方便，假设三个二维平面分别旋转：

```text
第一组：90°
第二组：180°
第三组：0°
```

那么：

```math
R_0
=
\begin{bmatrix}
0&-1\\
1&0
\end{bmatrix}
```

```math
R_1
=
\begin{bmatrix}
-1&0\\
0&-1
\end{bmatrix}
```

```math
R_2
=
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix}
```

---

<a id="origin-6781"></a>
### 107.1 第一组

```math
R_0
\begin{bmatrix}
1\\0
\end{bmatrix}
=
\begin{bmatrix}
0\\1
\end{bmatrix}
```

也就是：

```text
[1,0]
↓ 旋转90°
[0,1]
```

---

<a id="origin-6804"></a>
### 107.2 第二组

```math
R_1
\begin{bmatrix}
0\\1
\end{bmatrix}
=
\begin{bmatrix}
0\\-1
\end{bmatrix}
```

即：

```text
[0,1]
↓ 旋转180°
[0,-1]
```

---

<a id="origin-6827"></a>
### 107.3 第三组

```math
R_2
\begin{bmatrix}
1\\1
\end{bmatrix}
=
\begin{bmatrix}
1\\1
\end{bmatrix}
```

即没有旋转。

---

最终拼起来：

```math
q'
=
\begin{bmatrix}
0\\
1\\
0\\
-1\\
1\\
1
\end{bmatrix}
```

所以：

```text
一个 6×6 大矩阵乘法
```

实际上就是：

```text
3 次 2×2 小矩阵乘法
+
把结果重新拼起来
```

这就是大矩阵和二维旋转之间真正的关系。

---

<a id="origin-6877"></a>
## 108. 为什么大矩阵里有那么多 0？

因为不同二维平面之间：

> **不需要互相干扰。**

例如我们希望：

```text
(q0,q1)
```

只和：

```text
(q0,q1)
```

内部发生旋转。

不能突然让：

```text
q0
```

和：

```text
q4
```

混到一起。

所以块对角矩阵中：

```text
非对角位置全部是 0
```

这样就保证：

```text
第一对维度
只在第一对内部旋转

第二对维度
只在第二对内部旋转

第三对维度
只在第三对内部旋转
```

---

<a id="origin-6932"></a>
## 109. 真正的 RoPE 大矩阵

对于位置：

```math
m
```

第 \(i\) 个二维平面的旋转角度：

```math
m\omega_i
```

因此：

```math
R_m
=
\begin{bmatrix}
R(m\omega_0)&&&\\
&R(m\omega_1)&&\\
&&\ddots&\\
&&&R(m\omega_{d/2-1})
\end{bmatrix}
```

其中：

```math
R(m\omega_i)
=
\begin{bmatrix}
\cos(m\omega_i)&-\sin(m\omega_i)\\
\sin(m\omega_i)&\cos(m\omega_i)
\end{bmatrix}
```

所以：

> **不同二维维度组使用不同频率 \(\omega_i\)，但是都遵守同一个二维旋转公式。**

---



<a id="origin-6978"></a>
## 110. 为什么普通 RoPE 长文本会出问题？

假设模型训练上下文长度是 2048：

```text
context length = 2048
```

那么一条训练样本最多：

```text
2048 个 token
```

它们的位置编号就是：

```text
token 1     → position 0
token 2     → position 1
token 3     → position 2
...
token 2048  → position 2047
```

所以：

```math
\boxed{
m_{\max}=2047
}
```

---

<a id="origin-7012"></a>
## 111. 但模型不是训练了万亿 token 吗？

对。

这特别容易误解。

假设模型训练了：

```text
1 万亿 token
```

并不意味着 position 会一直数：

```text
0
1
2
...
999999999999
```

不是这样的。

每一条新的训练序列都会重新从：

```text
position 0
```

开始。

例如：

```text
训练样本 A：

位置：
0 1 2 3 ... 2047


训练样本 B：

位置：
0 1 2 3 ... 2047


训练样本 C：

位置：
0 1 2 3 ... 2047
```

所以即使模型总共训练了：

```text
1000000000000 个 token
```

如果每条训练序列长度最大仍然是 2048，

模型看到的 position id 仍然只是：

```text
0 ～ 2047
```

**即模型只见过长度最大为2048的输入。**

---

<a id="origin-7083"></a>
## 112. 那推理时为什么会出现 position=10000？

因为推理时用户真的可能给模型一条：

```text
超过 10000 token 的连续上下文
```

例如用户一次粘贴了一篇：

```text
10001 token 的长文档
```

那么模型看到的 position 就是：

```text
第 1 个 token   → position 0
第 2 个 token   → position 1
...
第 2048 个      → position 2047
第 2049 个      → position 2048
...
第 10001 个     → position 10000
```

所以：

```math
\boxed{
m=10000
}
```

真的会出现。

---

<a id="origin-7121"></a>
## 113. 另一种情况：Prompt + 模型生成

例如用户输入：

```text
9000 token
```

然后模型开始生成。

那么：

```text
Prompt 最后一个 token
大约 position = 8999
```

模型生成：

```text
第 1 个新 token
position = 9000

第 2 个新 token
position = 9001

...
```

如果又生成了：

```text
1001 个 token
```

就会来到：

```text
position = 10000
```

所以：

> **position=10000 并不奇怪，它只是说明当前这一整条上下文已经有 10001 个 token。**

---

<a id="origin-7168"></a>
## 114. 问题来了：模型训练时从来没见过 position=10000

假设训练长度：

```math
L_{train}=2048
```

那么训练时：

```math
m\le2047
```

但是现在推理：

```math
m=10000
```

对于某一个 RoPE **频率（每往后一个 token，这一组二维向量要多旋转多少角度）**：

```math
\omega
```

训练时角度最大：

```math
2047\omega
```

推理突然变成：

```math
10000\omega
```

大约扩大了：

```math
\frac{10000}{2047}
\approx4.9
```

倍。

于是模型进入了：

> **训练时没有见过的 RoPE 旋转范围。**

YaRN 论文正是针对 RoPE 模型超出训练上下文长度时性能明显下降的问题提出长上下文扩展方法。

---

<a id="origin-7223"></a>
## 115. RoPE 中 \(\omega\) 和 rad 分别是什么意思？

在 RoPE 中，我们经常看到：

```math
\phi=m\omega
```

这里：

```math
m
```

表示：

> token 的位置编号。

例如：

```text
第 1 个 token → position 0
第 2 个 token → position 1
第 3 个 token → position 2
...
```

而：

```math
\omega
```

可以暂时理解成：

> **这一组二维维度每往后移动一个 token，需要多旋转多少角度。**

---

<a id="origin-7262"></a>
## 116. \(\omega\) 是什么意思？

例如：

```math
\omega=0.1
```

更完整地说可以理解成：

```math
\omega=0.1\ \text{rad/token}
```

意思是：

```text
position 每增加 1
↓
这一组二维向量
多旋转 0.1 rad
```

所以：

```text
position 0
→ 旋转 0 × 0.1 = 0 rad

position 1
→ 旋转 1 × 0.1 = 0.1 rad

position 2
→ 旋转 2 × 0.1 = 0.2 rad

position 3
→ 旋转 3 × 0.1 = 0.3 rad
```

因此：

```math
\boxed{
\phi=m\omega
}
```

其中：

```text
m：
位置

ω：
每走一个位置旋转多少

φ：
最终旋转角度
```

---

<a id="origin-7324"></a>
## 117. `rad` 是什么意思？

`rad` 是：

```text
radian
```

中文叫：

> **弧度**

它和：

```text
°
```

一样，都是表示角度的单位。

我们平常习惯：

```text
90°
180°
360°
```

但数学里更常使用弧度。

最重要的换算：

```math
\boxed{
\pi\ \text{rad}=180^\circ
}
```

所以：

```math
\boxed{
2\pi\ \text{rad}=360^\circ
}
```

---

<a id="origin-7372"></a>
## 118. 1 rad 等于多少度？

因为：

```math
\pi\ rad=180^\circ
```

所以：

```math
1\ rad
=
\frac{180^\circ}{\pi}
```

大约：

```math
\boxed{
1\ rad\approx57.3^\circ
}
```

因此：

```text
0.1 rad ≈ 5.73°
0.5 rad ≈ 28.65°
1 rad   ≈ 57.3°
π/2 rad = 90°
π rad   = 180°
2π rad  = 360°
```

---

<a id="origin-7409"></a>
## 119. 举一个具体的 RoPE 例子

假设：

```math
\omega=0.1\ rad/token
```

那么每个 token 向后移动一个位置：

```text
多旋转 0.1 rad
```

也就是：

```math
0.1\times57.3^\circ
\approx5.73^\circ
```

所以：

```text
position 0
→ 0 rad
→ 0°

position 1
→ 0.1 rad
→ 约 5.73°

position 2
→ 0.2 rad
→ 约 11.46°

position 3
→ 0.3 rad
→ 约 17.19°
```

---

<a id="origin-7452"></a>
## 120. 如果 position = 100 呢？

假设：

```math
m=100
```

并且：

```math
\omega=0.01
```

那么：

```math
\phi=m\omega
```

所以：

```math
\phi
=
100\times0.01
=
1\ rad
```

也就是：

```math
\boxed{
\phi\approx57.3^\circ
}
```

注意：

> `position = 100` 并不是旋转 100°。

而是：

```text
position
×
这一组维度自己的 ω
=
真正旋转角度
```

---

<a id="origin-7506"></a>
## 121. 为什么叫“频率”？

这里的：

```math
\omega
```

通常叫：

> **角频率（angular frequency）**

在 RoPE 中可以非常直观地理解成：

> **旋转速度。**

也就是：

```text
position 每增加 1
到底旋转多少角度
```

---

<a id="origin-7531"></a>
## 122. \(\omega\) 大是什么意思？

假设：

```math
\omega=0.5
```

那么每走一个 token：

```math
0.5\ rad
```

换成角度：

```math
0.5\times57.3^\circ
\approx28.6^\circ
```

所以：

```text
position 0 → 0°
position 1 → 28.6°
position 2 → 57.3°
position 3 → 85.9°
...
```

旋转得非常快。

所以：

```math
\boxed{
\omega\ 大
\Rightarrow
旋转速度快
}
```

---

<a id="origin-7576"></a>
## 123. \(\omega\) 小是什么意思？

例如：

```math
\omega=0.0005
```

那么每走一个 token，只旋转：

```math
0.0005\ rad
```

约：

```math
0.0005\times57.3^\circ
\approx0.0286^\circ
```

所以：

```text
position 增加很多
↓
角度才慢慢发生变化
```

因此：

```math
\boxed{
\omega\ 小
\Rightarrow
旋转速度慢
}
```

---

<a id="origin-7617"></a>
## 124. 为什么 RoPE 要很多不同的 \(\omega\)？

因为 RoPE 会把高维 Q/K 拆成很多二维组。

例如：

```text
第 1 组维度
→ ω₀

第 2 组维度
→ ω₁

第 3 组维度
→ ω₂

...
```

它们的旋转速度不同。

可以理解成：

```text
第 1 块钟
→ 转得快

第 2 块钟
→ 稍微慢

第 3 块钟
→ 更慢

...
```

这样模型就能同时拥有：

```text
对短距离位置变化敏感的维度

以及

对长距离位置变化敏感的维度
```

---

<a id="origin-7665"></a>
## 125. 高频和低频是什么意思？

<a id="origin-7667"></a>
### 125.1 高频

```math
\omega
```

比较大。

例如：

```math
\omega=0.5
```

每个 token：

```text
转 28.6°
```

所以位置稍微变化：

```text
角度就变化很多
```

因此对：

```text
短距离的位置变化
```

比较敏感。

---

<a id="origin-7703"></a>
### 125.2 低频

```math
\omega
```

比较小。

例如：

```math
\omega=0.0005
```

每个 token：

```text
只转 0.0286°
```

所以：

```text
要移动很多 token
角度才会明显改变
```

因此更适合表达：

```text
较长距离的位置变化
```

---

<a id="origin-7738"></a>
## 126. 为什么 position = 10000 不等于旋转 10000°？

因为真正的公式是：

```math
\phi=m\omega
```

不是：

```math
\phi=m
```

例如：

```math
m=10000
```

但：

```math
\omega=0.0005
```

那么：

```math
\phi
=
10000\times0.0005
=
5\ rad
```

而：

```math
5\ rad
\approx286.5^\circ
```

所以：

```text
position = 10000
```

真正旋转的是：

```text
约 286.5°
```

而不是：

```text
10000°
```

---

<a id="origin-7801"></a>
## 127. 如果超过 360° 怎么办？

完全没问题。

因为：

```math
360^\circ
=
2\pi\ rad
```

而 sin/cos 是周期函数：

```math
\sin(\theta+2\pi)
=
\sin\theta
```

```math
\cos(\theta+2\pi)
=
\cos\theta
```

所以：

```text
400°
```

和：

```text
40°
```

方向完全一样。

例如：

```math
400^\circ
\bmod360^\circ
=
40^\circ
```

因此 RoPE 中：

> **角度可以不断累积，数学上并不存在“超过 360° 就不能算”的问题。**

---

<a id="origin-7856"></a>
## 128. 最重要的关系

RoPE 中：

```math
\boxed{
\phi=m\omega
}
```

可以直接理解成：

```text
token 在第几个位置
        ×
这一组二维维度的旋转速度
        =
这一组维度最终旋转多少角度
```

例如：

```text
position = 100
ω = 0.01 rad/token

↓
```

```math
100\times0.01
=
1\ rad
```

即：

```text
约 57.3°
```

---

<a id="origin-7899"></a>
## 129. 用一个具体频率看看问题

假设某一个慢速维度：

```math
\omega=0.0005
```


---

<a id="origin-7910"></a>
### 129.1 训练时最大位置 2047

最大角度：

```math
2047\times0.0005
```

得到：

```math
1.0235\ rad
```

大约：

```text
58.6°
```

也就是说：

> 训练过程中，这个二维平面大概只见过从 \(0^\circ\) 转到 \(58.6^\circ\) 这一段。

---

<a id="origin-7936"></a>
### 129.2 推理突然来到 position=10000

角度：

```math
10000\times0.0005
=
5\ rad
```

大约：

```text
286°
```

于是：

```text
训练：

0° ───────── 59°


推理：

0° ───────────────────────────── 286°
```

模型突然要处理一个这个维度在训练时根本没有经历过的旋转区域。

这就是：

```text
RoPE 长度外推
```

为什么可能出问题。

---

<a id="origin-7977"></a>
## 130. 最简单粗暴的解决办法：把位置压缩回来

假设：

```text
训练长度 = 2048
推理目标 ≈ 10240
```

大约：

```math
5\times
```

长。

最简单的想法就是：

> **既然 position 太大，那就把位置除以 5。**

即：

```math
m'
=
\frac{m}{5}
```

于是：

```text
真实 position 10000
↓
压缩
↓
等效 position 2000
```

又回到了模型训练时熟悉的：

```text
0 ～ 2047
```

范围。

这就是 Position Interpolation 最基本的直觉：把更长位置线性压回训练过的位置范围。

---

<a id="origin-8028"></a>
## 131. 从 RoPE 角度看，其实也可以理解成“减慢旋转”

原来：

```math
\phi=m\omega
```

现在：

```math
m'=\frac{m}{5}
```

那么：

```math
\phi
=
\frac{m}{5}\omega
```

也可以写成：

```math
\phi
=
m\frac{\omega}{5}
```

所以：

```text
位置 ÷ 5
```

和：

```text
RoPE 频率 ÷ 5
```

在这个意义下是等价的。

于是：

```text
原来每个 token
转这么多
        ↓
现在旋转速度变慢 5 倍
```

---

<a id="origin-8083"></a>
## 132. 用刚才那个例子

原来：

```math
\omega=0.0005
```

position：

```math
m=10000
```

角度：

```math
5\ rad
```

现在把频率除以 5：

```math
\omega'
=
0.0001
```

那么：

```math
10000\times0.0001
=
1
```

rad。

这就和训练最大位置附近：

```math
2047\times0.0005
\approx1.02
```

非常接近。

所以可以理解成：

```text
超长 position
↓
不要让它旋转得太远
↓
把旋转速度放慢
↓
重新压回模型熟悉的角度范围
```

---

<a id="origin-8144"></a>
## 133. 那为什么不把所有频率都直接除以 5？

这就是问题。

因为 RoPE 不是只有一个频率。

前面已经知道：

```text
有些二维维度：
转得很快

有些：
转得中等

有些：
转得很慢
```

如果全部统一：

```text
÷5
```

那么短距离的位置区分能力也可能一起被压缩。

---

<a id="origin-8173"></a>
## 134. 举一个高频维度的例子

假设另一个维度：

```math
\omega=0.5
```

那么相邻两个 token：

```text
position 100
和
position 101
```

角度差本来是：

```math
0.5\ rad
```

大约：

```text
28.6°
```

所以这个维度对：

```text
相邻 token
```

非常敏感。

---

如果也粗暴除以 5：

```math
\omega'
=
0.1
```

那么相邻 token 的角度差只剩：

```math
0.1\ rad
```

约：

```text
5.7°
```

也就是：

```text
原来：

token100     token101
    ↘ 28.6° ↙


压缩以后：

token100   token101
   ↘5.7°↙
```

原本明显的短距离差异被压得很小。

所以：

> **统一缩放虽然帮助了长距离，但可能牺牲原本已经学得很好的短距离位置结构。**

---

<a id="origin-8254"></a>
## 135. 这就是 YaRN 的核心出发点

YaRN 的想法不是：

```text
所有频率
全部统一 ÷ s
```

而是：

> **不同频率应该区别对待。**

可以粗略分为：

```text
高频
中频
低频
```

---

<a id="origin-8277"></a>
## 136. 高频维度怎么办？

高频：

```text
转得非常快
```

例如：

```math
\omega=0.5
```

训练长度 2048 内，它已经转过很多很多圈。

所以模型已经见过：

```text
很多不同相位
```

并且这些维度通常承担较细粒度、短距离的位置区分。

因此 YaRN 倾向于：

```text
高频部分
↓
少缩放或者不缩放
↓
保留原来的短距离位置分辨能力
```

---

<a id="origin-8313"></a>
## 137. 低频维度怎么办？

低频：

```text
转得非常慢
```

例如：

```math
\omega=0.0005
```

训练 2048 token 内，它可能只走过：

```text
0° → 59°
```

结果推理到 10000：

```text
突然跑到 286°
```

进入大量训练时没见过的区域。

所以这一类维度更需要：

```text
减慢旋转速度
```

例如：

```math
\omega
\rightarrow
\frac{\omega}{5}
```

于是超长 position 会重新映射到模型更熟悉的角度范围。

所以：

```text
低频部分
↓
更多插值 / 缩放
↓
帮助长距离外推
```

---

<a id="origin-8369"></a>
## 138. 那中间频率怎么办？

不能突然：

```text
这个维度不缩放
下一个维度突然 ÷5
```

这样变化太生硬。

所以 YaRN 在中间区域做：

> **平滑过渡。**

例如可以想象：

```text
高频                 中频                 低频

×1.0       ×0.9 ×0.7 ×0.5       ×0.2
  │                │                │
  ▼                ▼                ▼
基本保留         平滑过渡          强缩放
```

这就是 YaRN 非常核心的思想：

```math
\boxed{
\text{不同 RoPE 频率采用不同程度的位置插值}
}
```

而不是全部一刀切。YaRN 的方法正是针对不同 RoPE 频率采用分段/平滑的缩放策略来扩展上下文。

---

<a id="origin-8407"></a>
## 139. 用三个具体“钟”理解 YaRN

假设只有三组 RoPE 维度。

<a id="origin-8411"></a>
### 139.1 钟 A：转得快

```math
\omega_A=0.5
```

训练中已经转过非常多圈。

主要负责：

```text
细粒度 / 短距离变化
```

YaRN：

```text
基本保持原速
```

---

<a id="origin-8433"></a>
#### 139.1.1 钟 B：中速

```math
\omega_B=0.02
```

既涉及局部，也涉及较长距离。

YaRN：

```text
稍微减速
```

例如：

```math
0.02
\rightarrow
0.012
```

---

<a id="origin-8457"></a>
#### 139.1.2 钟 C：转得很慢

```math
\omega_C=0.0005
```

训练期间只走了一小段角度。

超长推理最容易进入陌生区域。

YaRN：

```text
明显减速
```

例如：

```math
0.0005
\rightarrow
0.0001
```

于是：

```text
原本 position 10000
会转到约 286°

↓ YaRN

只转到约 57°
```

重新落到训练时熟悉的范围。

---

<a id="origin-8496"></a>
## 140. YaRN 可以理解成“多档变速器”

普通 RoPE：

```text
每一组维度都有自己的转速
```

长文本来了以后，如果简单 Position Interpolation：

```text
所有钟
统一减速 5 倍
```

而 YaRN：

```text
高速钟
→ 基本保持

中速钟
→ 部分减速

低速钟
→ 明显减速
```

所以：

> **既尽量保留短距离位置能力，又给低频维度腾出更大的长距离表示范围。**

---

<a id="origin-8530"></a>
## 141. 为什么这种方法能扩展上下文？

原始训练：

```text
模型熟悉：

position 0 ～ 2047
```

但是现在希望：

```text
0 ～ 10000
甚至更长
```

YaRN 并不是要求模型：

```text
突然学会一个完全新的位置编码体系
```

而是在做：

```text
超长位置
↓
重新映射不同 RoPE 频率
↓
让大部分旋转模式
尽量落回模型熟悉的几何区域
```

所以可以理解成：

> **不是扩建一套全新的坐标系，而是重新调整原来那些“钟”的转速，让更长的距离仍能被原坐标体系表示。**

---

<a id="origin-8570"></a>
## 142. YaRN 还有一个更完整的思想：Attention 尺度校正

当 RoPE 频率重新调整以后：

```text
Q/K 的相对角度分布
```

也会发生变化。

这会进一步影响：

```math
QK^T
```

的分布，

从而可能改变 Softmax 的：

```text
尖锐程度
```

因此完整的 YaRN 还考虑：

> **Attention 的尺度 / temperature 校正。**

直观上，例如原来：

```text
scores：

[2, 1, 0]
```

Softmax 有一定区分度。

如果位置缩放以后变成：

```text
[1, 0.5, 0]
```

那么 Softmax 会变得更平。

所以需要适当校正 Attention score 的数值尺度，让扩展长度以后 Attention 的分布不要和训练阶段差太远。

YaRN 原论文除了频率的分段插值之外，也包含对 Attention scaling 的处理。

不过在理解 MiniMind 时，可以先关注：

```text
不同频率
不同程度缩放
```

这个核心。

---

<a id="origin-8631"></a>
## 143. RoPE 长上下文：高频是否见过 position=10000？压缩会不会导致信息失真？

这里有两个非常关键的问题：

1. 如果某个 RoPE 频率已经在训练阶段转过很多圈，那么推理到 `position=10000` 时，这个角度是不是其实训练时已经见过？
2. 如果为了扩展上下文而强行压缩位置，会不会导致原来的位置信息被压缩、分辨率下降？

答案分别是：

> **单个高频维度的某个“相位”确实可能在训练时已经反复见过；但 position=10000 对应的是所有频率共同组成的一整套相位组合，不能说整个位置已经见过。**

以及：

> **位置压缩确实会带来信息失真，最直接的表现就是位置分辨率降低；YaRN 的核心就是不要把所有频率一刀切地一起压缩。**

---

<a id="origin-8648"></a>
## 144. 先回顾 RoPE 中的位置角度

对于某一组二维维度：

```math
\phi=m\omega
```

其中：

```text
m：
position

ω：
这一组维度的旋转频率

φ：
最终旋转角度
```

例如：

```math
\omega=0.5\ \text{rad/token}
```

表示：

> position 每增加 1，这组二维向量就多旋转 0.5 rad。

---

<a id="origin-8681"></a>
## 145. 一个频率转一圈需要多少 token？

完整一圈：

```math
2\pi\ \text{rad}
```

所以如果：

```math
\omega
```

每个 token 转这么多，

那么一圈所需要的 token 数：

```math
T
=
\frac{2\pi}{\omega}
```

这个：

```math
T
```

可以理解成这一组 RoPE 维度的“位置周期”。

---

<a id="origin-8715"></a>
## 146. 高频维度会很快转很多圈

假设：

```math
\omega=0.5
```

那么：

```math
T
=
\frac{2\pi}{0.5}
\approx12.57
```

也就是说：

> 大约每 13 个 token 就转一圈。

如果模型训练长度是：

```math
2048
```

那么在训练阶段，这一组二维维度大约已经转了：

```math
\frac{2048}{12.57}
\approx163
```

圈。

也就是说：

```text
训练阶段：

这一块“快钟”
已经转了 160 多圈
```

---

<a id="origin-8762"></a>
## 147. 所以 position=10000 的高频相位可能确实见过

假设：

```math
m=10000
```

```math
\omega=0.5
```

那么：

```math
\phi
=
10000\times0.5
=
5000\ \text{rad}
```

但真正的方向只取决于：

```math
5000\bmod2\pi
```

因为：

```math
\sin(\theta+2\pi)
=
\sin\theta
```

```math
\cos(\theta+2\pi)
=
\cos\theta
```

所以：

> 这一块高频“钟”在 position=10000 时所处的角度，很可能在训练期间已经反复经过很多次。

因此：

```math
\boxed{
\text{高频单维相位未必陌生}
}
```

---

<a id="origin-8818"></a>
## 148. 但“某一个相位见过”不等于“position=10000 见过”

这是最重要的区别。

RoPE 并不是只有：

```text
一个 ω
```

而是很多：

```text
ω0
ω1
ω2
ω3
...
```

所以一个 position 实际对应：

```math
(
m\omega_0,
m\omega_1,
m\omega_2,
\dots
)
```

并且每个角度都再考虑：

```math
\bmod 2\pi
```

因此 position=10000 实际上对应的是：

```text
钟0：某个角度
钟1：某个角度
钟2：某个角度
钟3：某个角度
...
```

也就是一整套：

```math
\boxed{
\text{多频率相位组合}
}
```

---

<a id="origin-8875"></a>
## 149. 一个简单例子

假设只有三块钟：

```text
钟A：
转得很快

钟B：
中等速度

钟C：
转得很慢
```

训练中，position=500 时可能：

```text
A = 30°
B = 80°
C = 10°
```

position=1000：

```text
A = 30°
B = 160°
C = 20°
```

你会发现：

```text
A
```

可能已经重复了。

但是：

```text
(A,B,C)
```

整体组合仍然不同。

所以：

```text
某一块钟已经见过这个角度
```

不等于：

```text
所有钟的组合都见过
```

---

<a id="origin-8936"></a>
## 150. 高频和低频的差别

高频：

```math
\omega
```

大。

因此：

```text
训练短短 2048 个 token
↓
已经转过很多圈
↓
大量单独相位已经见过
```

低频：

```math
\omega
```

很小。

例如：

```math
\omega=0.0005
```

训练最大：

```math
m=2047
```

角度：

```math
2047\times0.0005
\approx1.02\ rad
```

大约：

```text
59°
```

也就是说：

```text
训练阶段：

这块慢钟
只从 0° 走到了约 59°
```

它连一圈都没有走完。

---

<a id="origin-9002"></a>
## 151. position=10000 对低频维度就非常陌生

同样：

```math
\omega=0.0005
```

如果：

```math
m=10000
```

那么：

```math
\phi
=
10000\times0.0005
=
5\ rad
```

大约：

```text
286°
```

于是：

```text
训练：

0° ───────── 59°


推理：

                    286°
```

这个维度在训练时根本没走到过这里。

所以：

```math
\boxed{
\text{低频维度更容易产生真正的相位外推}
}
```

---

<a id="origin-9057"></a>
## 152. 因此第一个问题的准确答案

不能简单说：

> position=10000 训练时已经见过。

更准确的是：

> **对于高频 RoPE 维度，由于训练阶段已经转过很多圈，position=10000 对应的单个相位可能已经见过；但低频维度可能训练时连一圈都没转完，而且所有频率共同组成的 position=10000 相位组合也未必出现过。**

所以需要区分：

```math
\boxed{
\text{单频率相位见过}
}
```

和：

```math
\boxed{
\text{整个位置模式见过}
}
```

---

<a id="origin-9085"></a>
## 153. 第二个问题：强行压缩位置会不会失真？

答案：

```math
\boxed{
会
}
```


---

<a id="origin-9099"></a>
## 154. 假设原来的两个位置

```math
m_1=1000
```

和：

```math
m_2=2000
```

相对距离：

```math
\Delta m
=
2000-1000
=
1000
```

对于某个 RoPE 频率：

```math
\omega
```

它们的相对旋转角度：

```math
\Delta\phi
=
\Delta m\omega
```

假设正好：

```math
\Delta\phi=60^\circ
```

也就是说：

```text
position 1000

      ↘
       60°
      ↗

position 2000
```

两个位置在这一维上区别比较明显。

---

<a id="origin-9157"></a>
## 155. 现在把位置压缩 10 倍

为了让超长上下文塞回原来的范围，

假设做：

```math
m'
=
\frac{m}{10}
```

那么：

```text
1000 → 100

2000 → 200
```

原本距离：

```math
1000
```

现在变成：

```math
100
```

所以相对角度：

```math
60^\circ
```

也会变成：

```math
6^\circ
```

即：

```text
原来：

position 1000
和
position 2000

相差 60°
```

压缩后：

```text
只差 6°
```

---

<a id="origin-9221"></a>
## 156. 这确实意味着位置信息被压缩了

原来：

```text
60°
```

两个向量方向差异比较明显。

现在：

```text
6°
```

两者方向变得非常接近。

因此模型更难区分：

```text
“这两个位置到底差多远？”
```

也就是：

```math
\boxed{
\text{Position Resolution 下降}
}
```

位置分辨率下降。

比如原来“小红喜欢小明”句子中**小红**和**小明**的距离角度差是60°，现在就变成了6°，推理中的信息就会相对没有之前训练时的那么精确，**因此这种压缩不适合高频压缩。**

---

<a id="origin-9259"></a>
## 157. 这其实是一个经典矛盾

可以概括成：

```math
\boxed{
\text{范围}
\quad vs\quad
\text{分辨率}
}
```

即：

```text
想表示更远的位置
↓
往往需要压缩坐标
↓
局部位置差异也会一起缩小
```

这和地图非常类似。

---

<a id="origin-9285"></a>
## 158. 地图类比

原来地图：

```text
1 cm = 1 km
```

两个地点相距：

```text
100 km
```

地图上距离：

```text
100 cm
```

非常明显。

现在为了把整个国家画到同一张纸上：

```text
1 cm = 10 km
```

那么同样：

```text
100 km
```

只剩：

```text
10 cm
```

所以：

```text
可表示范围变大
```

但：

```text
局部细节变少
```

位置压缩也是同样的道理。

---

<a id="origin-9341"></a>
## 159. 如果所有 RoPE 频率都统一压缩，会有什么问题？

假设统一：

```math
\omega'
=
\frac{\omega}{10}
```

那么所有角度差都会缩小 10 倍。

例如一个高频维度原来：

```text
相邻两个 token
角度差 = 30°
```

压缩以后：

```text
角度差 = 3°
```

原本：

```text
token100
和
token101
```

很好区分。

现在：

```text
两者方向几乎一样
```

所以：

> **短距离位置分辨能力也被牺牲了。**

---

<a id="origin-9388"></a>
## 160. 这就是为什么简单 Position Interpolation 有代价

最简单的长上下文扩展：

```text
所有位置统一压缩
```

优点：

```text
超长 position
可以重新映射到训练熟悉的范围
```

缺点：

```text
所有相对距离
也一起被压缩
↓
位置分辨率下降
```

所以存在：

```math
\boxed{
\text{Long Range}
\leftrightarrow
\text{Fine Resolution}
}
```

之间的 trade-off。

---

<a id="origin-9426"></a>
## 161. YaRN 为什么不全部一起压缩？

这正是 YaRN 的核心考虑。

RoPE 本来就有：

```text
高频维度
中频维度
低频维度
```

它们承担的位置尺度不同。

---

<a id="origin-9442"></a>
## 162. 高频维度主要干什么？

高频：

```math
\omega
```

大。

例如相邻两个 token：

```text
position 100
position 101
```

可能相差：

```text
30°
```

所以它对：

```text
局部位置变化
```

非常敏感。

可以粗略理解成：

```text
高频维度
↓
负责位置“显微镜”
↓
区分近距离 token
```

如果把它也强行压缩：

```text
30° → 3°
```

局部细节就容易被压糊。

所以：

> **高频应该尽量少动。**

---

<a id="origin-9497"></a>
## 163. 低频维度主要干什么？

低频：

```math
\omega
```

小。

相邻 token 的角度变化很小。

但是随着距离越来越远：

```text
角度才慢慢变化
```

所以更适合表达：

```text
长距离位置关系
```

可以粗略理解成：

```text
低频维度
↓
负责位置“广角镜头”
↓
看更远的位置范围
```

而长上下文外推时，

真正最容易进入未见区域的也是这些：

```text
训练阶段只转了一小段
```

的低频维度。

所以：

> **低频更适合做较强的缩放。**

---

<a id="origin-9547"></a>
## 164. YaRN 的思路

YaRN 不做：

```text
所有频率 ÷10
```

而大概做：

```text
高频
↓
基本保留
↓
保住局部位置分辨率


中频
↓
逐渐缩放
↓
平滑过渡


低频
↓
更多缩放
↓
扩大长距离范围
```

也就是：

```text
             缩放程度

高频          小
 ↓
中频          中
 ↓
低频          大
```

---

<a id="origin-9593"></a>
## 165. 所以 YaRN 本质上是在做一个折中

可以总结成：

```text
如果完全不压缩：

短距离精度保住了
但长距离跑到训练没见过的区域
```

如果全部统一压缩：

```text
长距离解决了
但短距离也被压糊
```

YaRN：

```text
高频少动
↓
保留局部精度

低频多动
↓
扩展长距离

中间平滑过渡
↓
两边折中
```

所以它是在解决：

```math
\boxed{
\text{长距离范围}
\quad+\quad
\text{局部位置分辨率}
}
```

之间的矛盾。


<a id="origin-9640"></a>
## 166. 用语言案例理解 RoPE 的高频、中频和低频

前面我们说：

```text
高频 RoPE
→ 位置稍微变化，角度就变化很多

低频 RoPE
→ 位置变化很多，角度才明显变化
```

如果只用“钟表”来解释，确实比较抽象。

更适合语言模型的理解方式是：

> **高频维度更适合表达局部、精细的位置差异；低频维度更适合表达跨度较大的位置关系。**

但需要先强调：

> **这不是人为规定“某几个维度专门负责主谓关系、某几个维度专门负责段落关系”。RoPE 只是提供不同的位置频率，模型训练以后自己学习如何利用这些不同尺度的位置特征。**

---

<a id="origin-9664"></a>
## 167. 先看一个非常局部的语言关系

例如：

```text
我 喜欢 吃 苹果
```

假设当前处理：

```text
吃
```

它可能需要区分：

```text
前 1 个 token：喜欢

前 2 个 token：我
```

这里：

```text
距离 1
```

和：

```text
距离 2
```

的区别就可能很重要。

例如：

```text
我 / 喜欢 / 吃
```

和：

```text
我 / 吃 / 喜欢
```

虽然 token 差不多，

但是局部顺序一变化：

```text
语言结构就完全不同
```

所以模型需要一种位置表示：

> **哪怕只移动 1～2 个 token，也能产生比较明显的变化。**

这就是高频位置维度擅长提供的能力。

---

<a id="origin-9728"></a>
## 168. 高频为什么适合局部关系？

假设某组 RoPE：

```math
\omega_H = 0.5\ \text{rad/token}
```

那么每移动一个 token：

```math
0.5\ rad
\approx28.6^\circ
```

所以：

```text
距离 1
→ 角度差约 28.6°

距离 2
→ 角度差约 57.3°

距离 3
→ 角度差约 85.9°
```

也就是说：

```text
只移动几个 token
↓
角度已经变化很多
```

所以它对于：

```text
距离 1
距离 2
距离 3
```

非常敏感。

---

<a id="origin-9776"></a>
## 169. 一个语言例子

例如：

```text
小明 非常 喜欢 小红
```

当前：

```text
喜欢
```

可能需要利用：

```text
前面 1 个 token：
非常

前面 2 个 token：
小明
```

如果换成：

```text
小明 喜欢 非常 小红
```

仅仅几个 token 的位置变化，

语言结构就明显不一样。

所以对于：

```text
词序
局部语法
短语结构
相邻 token 关系
```

模型需要很高的位置分辨率。

可以粗略理解成：

```math
\boxed{
高频 RoPE
\rightarrow
局部语言关系
}
```

---

<a id="origin-9833"></a>
## 170. 再看一个更长距离的语言关系

例如一篇文章：

```text
第 1 段：

浙江大学软件学院位于宁波。
学院主要开展软件工程和人工智能相关研究。

……

中间经过大量文字

……

第 20 段：

该学院近年来进一步加强了人工智能领域的研究。
```

这里：

```text
“该学院”
```

可能需要联系很前面的：

```text
“浙江大学软件学院”
```

两者可能相隔：

```text
几百
甚至几千 token
```

这时候模型真正需要的是：

> **知道它们处在一个较长距离的对应关系中。**

并不一定需要：

```text
距离到底是 1001 token
还是 1002 token
```

这种极其精细的区别。

---

<a id="origin-9888"></a>
## 171. 低频为什么适合这种长距离关系？

假设：

```math
\omega_L=0.0005\ \text{rad/token}
```

那么移动一个 token：

```math
0.0005\ rad
\approx0.0286^\circ
```

所以：

```text
距离 1
→ 0.0286°

距离 10
→ 0.286°

距离 100
→ 2.86°

距离 1000
→ 28.6°

距离 2000
→ 57.3°
```

可以看到：

```text
1 个 token
2 个 token
3 个 token
```

对这一维来说区别非常小。

但：

```text
1000 个 token
2000 个 token
```

才会出现明显的角度变化。

所以：

> **低频维度不会浪费大量表示能力去区分非常细的局部距离，而是能在较大范围内缓慢变化。**

---

<a id="origin-9947"></a>
## 172. 一个更具体的语言例子

假设文章开头写：

```text
张三于 2010 年加入浙江大学，
主要从事人工智能研究。
```

经过：

```text
1500 个 token
```

以后出现：

```text
他后来开始研究大语言模型。
```

这里：

```text
“他”
```

可能需要和前面：

```text
“张三”
```

建立关系。

模型需要知道：

```text
这是一个距离比较远的上下文信息
```

但是：

```text
张三距离“他”到底是 1498 token
还是 1501 token
```

往往没有：

```text
“喜欢”和它前面一个词到底是什么”
```

那么敏感。

所以可以粗略理解：

```text
高频：
更适合精细区分几十个 token 内的位置变化

低频：
更适合表示数百、数千 token 的长距离变化
```

---

<a id="origin-10015"></a>
## 173. 高频和低频分别像在回答什么问题？

<a id="origin-10017"></a>
### 173.1 高频位置特征

更像在回答：

```text
这个词是在我前面 1 个位置，
还是前面 2 个位置？

是紧挨着我，
还是中间隔了一个词？
```

例如：

```text
我 喜欢 苹果
```

和：

```text
我 苹果 喜欢
```

局部顺序非常重要。

---

<a id="origin-10045"></a>
### 173.2 低频位置特征

更像在回答：

```text
这个信息是在当前附近，

还是在前面很远的一段内容里？
```

例如：

```text
文章第一段介绍了一个人

↓

经过 1000 多 token

↓

后面再次使用“他”
```

需要建立长距离联系。

---

<a id="origin-10073"></a>
## 174. 为什么需要高频和低频一起存在？

因为语言同时存在：

```text
局部关系
+
长距离关系
```

例如一句话：

```text
张三告诉李四，他昨天购买的那本书非常有趣。
```

模型既要理解：

```text
“非常”修饰“有趣”
```

这种：

```text
非常局部的关系
```

又可能需要判断：

```text
“他”到底指张三还是李四
```

这种：

```text
跨越更长距离的关系
```

如果是一篇长文，

还可能需要联系：

```text
几百甚至几千 token 之前定义的人物、变量、概念
```

所以只用一种位置尺度是不够的。

---

<a id="origin-10125"></a>
## 175. 可以理解成“多尺度位置感知”

RoPE 的很多不同频率可以理解成同时提供：

```text
非常局部的位置尺度

局部的位置尺度

中距离的位置尺度

长距离的位置尺度
```

类似于：

```text
高频
↓
看细节

中频
↓
看句子 / 局部段落

低频
↓
看长距离结构
```

注意：

> 这只是帮助理解的位置尺度直觉，并不是说模型内部存在明确的“句法频率”“段落频率”标签。

<a id="origin-10159"></a>
## 176. 这也解释了为什么不能把所有频率都统一压缩

假设高频原来：

```text
相邻 token
角度差 = 30°
```

这对于：

```text
“非常 好”
```

和：

```text
“好 非常”
```

这种局部顺序区分很有帮助。

如果为了扩展上下文，

全部频率统一压缩 10 倍：

```text
30°
↓
3°
```

那么：

```text
相邻 token 的位置差异
```

也被严重压缩了。

---

<a id="origin-10202"></a>
## 177. 用语言案例理解这种信息损失

原本模型可能比较容易区分：

```text
A：

我 非常 喜欢 苹果
```

和：

```text
B：

我 喜欢 非常 苹果
```

因为：

```text
“非常”
相对于
“喜欢”
```

的位置关系变化非常明显。

如果所有高频位置特征都被大幅压缩：

```text
距离 1
距离 2
```

对应的角度差都变得很小，

那么模型利用这些位置维度区分：

```text
局部词序
```

就可能变困难。

---

<a id="origin-10249"></a>
## 178. 但是低频不压缩又有什么问题？

假设模型正在阅读一篇很长的技术文档。

前面某个位置写：

```text
position 100：

我们定义配置对象 user_config，
其中包含数据库地址、缓存策略和重试次数。
```

然后中间经过了大量内容，例如：

```text
数据库初始化
日志系统
线程池
任务调度
缓存模块
异常处理
……
```

到了很后面：

```text
position 10000：

在启动服务之前，
需要重新读取 user_config，
并根据其中的重试次数初始化任务调度器。
```

这里模型需要建立一个长距离关系：

```text
前面的 user_config 定义
            ↕
后面的 user_config 使用
```

也就是说：

> **模型需要知道：后面这个 `user_config`，和很早以前定义的那个 `user_config` 有关系。**


<a id="origin-10297"></a>
### 178.1 一句话理解

<a id="origin-10299"></a>
#### 178.1.1 训练的时候，模型见过这种情况：前面定义了 user_config，过了一两千个 token 后又用到了它，这种“隔得很远但还是有关联”的关系，在 RoPE 里可能对应大约 \(60^\circ\) 的相对角度。后来推理时文本变得特别长，user_config 隔了快一万个 token 才再次出现，这时候相对角度可能一下变成 \(280^\circ\)。这个 \(280^\circ\) 的位置模式模型训练时没怎么见过，所以不太知道该怎么处理。YaRN 做的事情，就是把这种 \(280^\circ\) 的陌生关系压回到接近 \(60^\circ\) 的熟悉范围，让模型可以继续按照以前学到的方式理解：哦，这还是“前面很久以前定义的那个 user_config，现在又被引用了”，所以我知道接下来要干啥了。

---

<a id="origin-10303"></a>
## 179. 这里最重要的不是精确差几个 token

前面的：

```text
user_config
```

在：

```text
position 100
```

后面的：

```text
user_config
```

在：

```text
position 10000
```

两者相差：

```math
10000-100=9900
```

个 token。

但对于理解这段文字来说，真正重要的通常不是：

```text
到底相隔 9899 个 token

还是 9900 个 token

还是 9901 个 token
```

而是：

> **这个信息出现在很久以前，现在又被重新引用了。**

所以这种关系更偏向：

```text
长距离位置关系
```

而不是：

```text
局部精细位置关系
```

---

<a id="origin-10365"></a>
## 180. 这就是低频位置特征更适合表达的东西

假设某个低频 RoPE 维度：

```math
\omega=0.0005\ \text{rad/token}
```

它每移动一个 token，只旋转：

```math
0.0005\text{ rad}
```

大约：

```math
0.0286^\circ
```

所以：

```text
差 1 个 token
→ 几乎没变化

差 10 个 token
→ 变化也很小

差 100 个 token
→ 开始有一些变化

差 1000 个 token
→ 才出现比较明显的变化
```

因此低频位置特征不会特别敏感于：

```text
前 1 个 token

前 2 个 token
```

而更适合提供一种：

> **“这个相关信息到底是在附近，还是在很远以前？”**

的位置尺度。

---

<a id="origin-10417"></a>
## 181. 如果训练时最长只有 2048 token

假设训练上下文长度：

```math
L_{train}=2048
```

那么训练时任意两个 token 的最大相对距离大约是：

```math
2047
```

对于：

```math
\omega=0.0005
```

最大相对旋转角：

```math
2047\times0.0005
\approx1.02\text{ rad}
```

约：

```math
58.6^\circ
```

所以训练过程中，这个低频维度看到的长距离关系大致是：

```text
两个相关词距离几十 token
↓
较小角度差

距离几百 token
↓
中等角度差

距离接近 2000 token
↓
最大大约 59°
```

也就是说：

> **训练过程中，这个低频维度只学过大约 \(0^\circ\sim59^\circ\) 这一范围内的长距离位置模式。**

---

<a id="origin-10472"></a>
## 182. 用一个训练时可能见过的语言例子

例如训练文本：

```text
position 100：

我们定义配置对象 user_config。


……

position 1800：

程序启动时重新读取 user_config。
```

两者距离：

```math
1800-100=1700
```

对应角度差：

```math
1700\times0.0005
=
0.85\text{ rad}
```

约：

```math
48.7^\circ
```

这种模式模型在训练中是有机会见过的：

```text
前面定义一个对象

↓

经过很长一段文字

↓

后面重新引用这个对象
```

而低频相对角度可能是：

```text
40°
50°
接近 60°
```

这样的范围。

---

<a id="origin-10535"></a>
## 183. 但是推理时文本突然变得非常长

现在用户给模型一篇 10000 多 token 的代码文档。

前面：

```text
position 100：

user_config = {...}
```

后面：

```text
position 10000：

retry_count = user_config["retry_count"]
```

这两处相差：

```math
9900
```

个 token。

于是低频相对角度：

```math
9900\times0.0005
=
4.95\text{ rad}
```

约：

```math
283.6^\circ
```

于是情况变成：

```text
训练时模型熟悉的长距离关系：

前面的 user_config
        ↕
后面的 user_config

低频角度差大约：
0° ～ 59°
```

但现在推理：

```text
前面的 user_config
        ↕
9900 token 后的 user_config

低频角度差：
约 284°
```

也就是说：

> **语言关系本身其实还是“前面定义，后面引用”，但 RoPE 给出的低频位置模式已经跑到了模型训练时从没见过的区域。**

---

<a id="origin-10607"></a>
## 184. 问题不在于模型不认识 `user_config`

注意这里的问题不是：

```text
模型不认识 user_config
```

也不是：

```text
模型不知道两个字符串一样
```

真正的问题是：

> **Attention 在判断“当前位置应该如何利用 9900 token 前的信息”时，RoPE 提供了一种训练时从未经历过的相对位置几何关系（之前见的是两者相差48°时的关系，现在突然出现了相差284°，不知道怎么处理了）。**

也就是：

```text
内容关系：
模型可能认识

但是

位置关系：
超出了训练分布
```

所以长距离 Attention 可能变得不稳定。

---

<a id="origin-10641"></a>
## 185. 为什么要压缩低频？

假设我们把这个低频的旋转速度减慢 5 倍：

```math
\omega'
=
\frac{0.0005}{5}
=
0.0001
```

那么同样：

```math
\Delta m=9900
```

新的角度差：

```math
9900\times0.0001
=
0.99\text{ rad}
```

约：

```math
56.7^\circ
```

于是：

```text
原来：

position 100
↔
position 10000

距离 9900
↓
角度差约 284°
↓
训练没见过
```

压缩以后：

```text
position 100
↔
position 10000

距离仍然 9900
↓
角度差约 57°
↓
回到训练熟悉的范围
```

---

<a id="origin-10705"></a>
## 186. 从语言意义上怎么理解这个压缩？

可以把它理解成：

原本模型训练时学会了：

```text
“如果一个实体在前面大约 1000～2000 token 出现过，
现在又被引用，
这种长距离关系应该怎么处理。”
```

但现在推理：

```text
它出现在 9900 token 以前
```

模型没学过这么远。

于是 YaRN 做的事情相当于：

```text
真实距离：
9900 token

↓

在低频位置空间中压缩

↓

让它看起来更像：
模型以前训练过的
约 2000 token 级别长距离关系
```

于是模型可以复用原来学到的模式：

```text
“这是一个很早以前出现过，
现在重新被引用的信息。”
```

---

<a id="origin-10751"></a>
## 187. 但它不是把 9900 token 真变成 2000 token

这一点要特别注意。

文本本身：

```text
仍然有 9900 token 的实际距离
```

Attention 仍然可以访问：

```text
position 100
```

那个 token。

只是：

> **RoPE 中用于描述相对位置的旋转角度被重新缩放了。**

所以：

```text
内容没有删掉
token 没有合并
上下文没有截断
```

改变的只是：

```text
位置几何表示
```

---

<a id="origin-10789"></a>
## 188. 为什么这类关系特别适合低频？

因为对于这种长距离引用：

```text
position 100
↔
position 10000
```

模型通常不需要精确知道：

```text
它们到底差 9899
还是 9900
还是 9901
```

这些距离对于：

```text
“后面的 user_config 指的是前面的 user_config”
```

来说差别非常小。

真正重要的是：

```text
这是一个非常远距离的相关信息
```

所以低频这种：

```text
变化慢
```

的位置特征非常适合表示这种关系。

---

<a id="origin-10831"></a>
## 189. 对比高频语言关系

高频更适合：

```text
我 非常 喜欢 苹果
```

例如：

```text
“非常”
```

是在：

```text
“喜欢”前 1 个 token
```

还是：

```text
后 1 个 token
```

区别可能非常重要。

所以：

```text
距离 1
距离 2
```

需要精确区分。

---

而低频更适合：

```text
文章开头：

定义 user_config

↓

经过几千 token

↓

文章后面：

重新使用 user_config
```

这里更重要的是：

```text
近
还是
非常远
```

而不是：

```text
准确差一个 token
```

---

<a id="origin-10904"></a>
## 190. 这就是 YaRN 的直觉

YaRN 不想做：

```text
所有位置频率一起 ÷10
```

因为那会破坏：

```text
局部词序
短语结构
相邻 token 区分
```

它更希望：

```text
高频
↓
尽量保持
↓
继续分清：
前1个 token / 前2个 token / 前3个 token


低频
↓
更多压缩
↓
让：
几千 / 上万 token 的远距离关系
不要跑出模型熟悉的位置范围
```

<a id="origin-10940"></a>
## 191. YaRN 的核心公式：不同 RoPE 频率到底怎么缩放？

前面已经知道，普通 RoPE 中，第 \(i\) 组二维维度有自己的旋转频率：

```math
\omega_i
```

位置 \(m\) 对应的旋转角度：

```math
\phi_i(m)=m\omega_i
```

也就是说：

```text
position
×
这一组维度的旋转速度
=
最终旋转角度
```

---

<a id="origin-10966"></a>
## 192. YaRN 最核心的频率公式

可以写成：

```math
\boxed{
\omega_i'
=
(1-\gamma_i)\omega_i
+
\gamma_i\frac{\omega_i}{s}
}
```

把：

```math
\omega_i
```

提出来：

```math
\boxed{
\omega_i'
=
\omega_i
\left[
(1-\gamma_i)
+
\frac{\gamma_i}{s}
\right]
}
```

这就是理解 YaRN 最重要的公式。

---

<a id="origin-11005"></a>
## 193. 每一个符号是什么意思？

其中：

```math
\omega_i
```

是：

> 原始 RoPE 第 \(i\) 组二维维度的频率。

---

```math
s
```

是：

> 上下文扩展倍数。

例如：

```text
2048 → 8192
```

那么：

```math
s=4
```

---

```math
\gamma_i
```

是：

> 当前这一组频率到底应该被压缩多少。

范围：

```math
0\le\gamma_i\le1
```

---

<a id="origin-11057"></a>
## 194. 如果 \(\gamma_i=0\)

代入：

```math
\omega_i'
=
\omega_i
\left[
1+\frac{0}{s}
\right]
```

得到：

```math
\boxed{
\omega_i'=\omega_i
}
```

也就是说：

```text
完全不压缩
```

通常可以理解成：

```text
高频部分
↓
尽量保持原来的旋转速度
↓
保住局部位置分辨率
```

---

<a id="origin-11096"></a>
## 195. 如果 \(\gamma_i=1\)

代入：

```math
\omega_i'
=
\omega_i
\left[
0+\frac1s
\right]
```

得到：

```math
\boxed{
\omega_i'
=
\frac{\omega_i}{s}
}
```

也就是：

```text
完全按照扩展倍数压缩
```

例如：

```math
s=5
```

那么：

```math
\omega_i'
=
\frac{\omega_i}{5}
```

旋转速度变成原来的：

```text
1/5
```

---

<a id="origin-11147"></a>
## 196. 如果 \(\gamma_i=0.5\)

那么：

```math
\omega_i'
=
\omega_i
\left[
0.5+\frac{0.5}{s}
\right]
```

假设：

```math
s=5
```

得到：

```math
\omega_i'
=
\omega_i
(0.5+0.1)
```

所以：

```math
\boxed{
\omega_i'=0.6\omega_i
}
```

也就是：

```text
不完全保持原频率
也不完全 ÷5

而是在中间平滑过渡
```

---

<a id="origin-11194"></a>
## 197. 用一个表格看最直观

假设：

```math
s=5
```

那么：

| \(\gamma_i\) | 新频率 \(\omega_i'\) | 含义    |
| -----------: | ----------------: | ----- |
|            0 |   \(1.0\omega_i\) | 完全保持  |
|         0.25 |   \(0.8\omega_i\) | 少量压缩  |
|          0.5 |   \(0.6\omega_i\) | 中等压缩  |
|         0.75 |   \(0.4\omega_i\) | 较强压缩  |
|            1 |   \(0.2\omega_i\) | 完全 ÷5 |

所以 YaRN 不是：

```text
压
或者
不压
```

而是：

```text
不同频率
使用不同程度的压缩
```

---

<a id="origin-11229"></a>
## 198. \(\gamma_i\) 是怎么来的？

YaRN 会先根据：

```text
这个频率在原始训练长度内
到底能转多少圈
```

来判断它属于：

```text
高频
中频
低频
```

假设原始训练长度：

```math
L
```

某个频率：

```math
\omega_i
```

那么它在整个训练窗口里大约能转多少圈：

```math
\boxed{
r_i
=
\frac{L\omega_i}{2\pi}
}
```

因为：

```math
L\omega_i
```

是走完整个训练窗口累计旋转的弧度，

而：

```math
2\pi
```

是一整圈。

所以：

```math
\frac{L\omega_i}{2\pi}
```

就是：

> **在训练窗口内一共转了多少圈。**

---

<a id="origin-11296"></a>
## 199. 举例

假设：

```math
L=2048
```

某个高频：

```math
\omega_H=0.5
```

那么：

```math
r_H
=
\frac{2048\times0.5}{2\pi}
```

约：

```math
r_H\approx163
```

也就是说：

```text
训练 2048 token 的过程中
这个维度已经转了约 163 圈
```

这种频率：

```text
大量相位都见过
而且对局部位置非常敏感
```

所以 YaRN 倾向于：

```math
\gamma_i\approx0
```

即：

```text
少压或者不压
```

---

<a id="origin-11352"></a>
## 200. 再看低频

假设：

```math
\omega_L=0.0005
```

那么：

```math
r_L
=
\frac{2048\times0.0005}{2\pi}
```

约：

```math
r_L\approx0.163
```

也就是说：

```text
整个训练窗口里
连一整圈都没转完
```

这种低频一旦来到超长上下文：

```text
position 10000
```

就非常容易进入训练阶段没见过的相位范围。

所以 YaRN 更倾向于：

```math
\gamma_i\approx1
```

即：

```math
\omega_i'
\approx
\frac{\omega_i}{s}
```

---

<a id="origin-11405"></a>
## 201. YaRN 用两个阈值决定怎么处理

YaRN 通常会引入：

```math
\beta_{fast}
```

和：

```math
\beta_{slow}
```

来判断某一组维度在原训练窗口里转了多少圈。

直观理解：

```text
转得非常多
↓
属于高频
↓
少压


转得非常少
↓
属于低频
↓
多压


处在中间
↓
平滑过渡
```

经典 YaRN 常见：

```text
beta_fast = 32
beta_slow = 1
```

含义可以粗略理解成：

```text
训练窗口里转了很多圈
→ 高频区域

训练窗口里连一圈左右都不到
→ 低频区域

中间
→ 逐渐过渡
```

---

<a id="origin-11465"></a>
## 202. \(\gamma_i\) 的直观形式

可以把它理解成一个 Ramp：

```text
高频                     中频                     低频

γ=0                      0<γ<1                    γ=1

│                           │                       │
▼                           ▼                       ▼

不压                   平滑过渡                  完全压缩
```

数学上可以粗略写成：

```math
\gamma_i
=
\operatorname{clip}
\left(
\frac{i-i_{\text{low}}}
{i_{\text{high}}-i_{\text{low}}},
0,
1
\right)
```

其中：

```text
clip(...,0,1)
```

意思是：

```text
小于 0 → 设成 0

0～1 → 保持

大于 1 → 设成 1
```

所以：

```text
高频维度：
γ≈0

中频维度：
γ 从 0 慢慢变到 1

低频维度：
γ≈1
```

---
<a id="origin-11524"></a>
## 203. YaRN 中 \(\gamma_i\)、\(i\)、\(i_{\text{low}}\)、\(i_{\text{high}}\) 分别是什么意思？

前面为了说明 YaRN 如何对不同 RoPE 频率做不同程度的压缩，我们用了一个简化的过渡公式：

```math
\gamma_i
=
\operatorname{clip}
\left(
\frac{i-i_{\text{low}}}
{i_{\text{high}}-i_{\text{low}}},
0,
1
\right)
```

这里最容易搞混的是：

```math
i
```

到底是什么。

---

<a id="origin-11550"></a>
## 204. \(i\) 不是 token 的 position

首先要明确：

```math
i
```

不是：

```text
position 0
position 1
position 2
...
```

也不是：

```text
第几个 token
```

它表示的是：

> **当前正在处理第几组 RoPE 二维旋转维度，也就是第几个 RoPE 频率。**

---

<a id="origin-11579"></a>
## 205. 一个具体例子

假设一个 Attention Head 的维度是：

```math
d=8
```

那么 Q 可以写成：

```math
Q=
[q_0,q_1,q_2,q_3,q_4,q_5,q_6,q_7]
```

RoPE 会把这些维度拆成 4 组二维平面：

```text
第 0 组：
(q0,q1)

第 1 组：
(q2,q3)

第 2 组：
(q4,q5)

第 3 组：
(q6,q7)
```

每一组都有自己的旋转频率：

```text
第 0 组 → ω0
第 1 组 → ω1
第 2 组 → ω2
第 3 组 → ω3
```

因此：

```text
i = 0 → 第 0 组 RoPE 频率 ω0
i = 1 → 第 1 组 RoPE 频率 ω1
i = 2 → 第 2 组 RoPE 频率 ω2
i = 3 → 第 3 组 RoPE 频率 ω3
```

所以可以记：

```math
\boxed{
i=\text{RoPE 频率组的编号}
}
```

---

<a id="origin-11638"></a>
## 206. 那 \(i_{\text{low}}\) 和 \(i_{\text{high}}\) 是什么？

它们是两个：

> **频率分界位置。**

用来把所有 RoPE 频率划分成：

```text
基本不压缩
↓
平滑过渡
↓
充分压缩
```

三段。

例如：

```math
i_{\text{low}}=3
```

```math
i_{\text{high}}=7
```

**YaRN 并不是人工直接指定 `i_low=3、i_high=7` 这样的维度下标，而是先人为设定 `β_fast` 和 `β_slow` 两个阈值，再结合每组 RoPE 频率 \(\omega_i\) 和原始训练长度 \(L\)，计算该频率在训练窗口内大约旋转了多少圈，从而自动确定哪些频率属于高频区、过渡区和低频区。**


那么可以理解成：

```text
i < 3
↓
基本不压

3 ～ 7
↓
逐渐增加压缩程度

i > 7
↓
充分压缩
```

---

<a id="origin-11687"></a>
## 207. `clip` 是什么？

`clip` 可以理解成：

> **截断 / 限幅：把一个数强行限制在指定范围内。**

例如：

```math
\operatorname{clip}(x,0,1)
```

意思是：

> 不管 \(x\) 原来是多少，最后都把它限制在 \([0,1]\) 之间。

数学上：

```math
\operatorname{clip}(x,0,1)
=
\begin{cases}
0,&x<0\\
x,&0\le x\le1\\
1,&x>1
\end{cases}
```

例如：

```text
clip(-0.5, 0, 1) = 0

clip(0.3, 0, 1) = 0.3

clip(0.8, 0, 1) = 0.8

clip(1.6, 0, 1) = 1
```

也就是说：

```text
太小
↓
拉到下界

正常
↓
保持不变

太大
↓
压到上界
```

---

<a id="origin-11745"></a>
### 207.1 放到 YaRN 公式里

前面有：

```math
\gamma_i
=
\operatorname{clip}
\left(
\frac{i-i_{\text{low}}}
{i_{\text{high}}-i_{\text{low}}},
0,
1
\right)
```

先计算：

```math
\frac{i-i_{\text{low}}}
{i_{\text{high}}-i_{\text{low}}}
```

然后：

```text
结果 < 0
→ γ_i = 0

结果在 0～1
→ 保留原值

结果 > 1
→ γ_i = 1
```

所以最终保证：

```math
\boxed{
0\le\gamma_i\le1
}
```
---

<a id="origin-11790"></a>
## 208. 用具体数字看这个公式

假设：

```math
i_{\text{low}}=3
```

```math
i_{\text{high}}=7
```

那么：

```math
\gamma_i
=
\operatorname{clip}
\left(
\frac{i-3}{7-3},
0,
1
\right)
```

也就是：

```math
\gamma_i
=
\operatorname{clip}
\left(
\frac{i-3}{4},
0,
1
\right)
```

---

<a id="origin-11830"></a>
## 209. 当 \(i=3\)

代入：

```math
\gamma_3
=
\frac{3-3}{4}
```

得到：

```math
\gamma_3=0
```

所以：

```text
第 3 组频率
↓
γ = 0
↓
不压缩
```

---

<a id="origin-11858"></a>
## 210. 当 \(i=4\)

```math
\gamma_4
=
\frac{4-3}{4}
```

得到：

```math
\gamma_4=0.25
```

也就是说：

```text
开始有一点压缩
```

---

<a id="origin-11880"></a>
## 211. 当 \(i=5\)

```math
\gamma_5
=
\frac{5-3}{4}
```

得到：

```math
\gamma_5=0.5
```

所以：

```text
压缩程度大约走到中间
```

---

<a id="origin-11902"></a>
## 212. 当 \(i=6\)

```math
\gamma_6
=
\frac{6-3}{4}
```

得到：

```math
\gamma_6=0.75
```

说明：

```text
已经比较接近充分压缩
```

---

<a id="origin-11924"></a>
## 213. 当 \(i=7\)

```math
\gamma_7
=
\frac{7-3}{4}
```

得到：

```math
\gamma_7=1
```

所以：

```text
第 7 组开始
↓
完全采用缩放后的频率
```

---

<a id="origin-11948"></a>
## 214. 为什么还需要 `clip`？

因为如果：

```math
i<i_{\text{low}}
```

例如：

```math
i=1
```

那么：

```math
\frac{1-3}{4}
=
-0.5
```

但我们不希望：

```math
\gamma=-0.5
```

所以：

```math
clip(-0.5,0,1)
```

得到：

```math
0
```

也就是：

```text
不压缩
```

---

如果：

```math
i>i_{\text{high}}
```

例如：

```math
i=9
```

那么：

```math
\frac{9-3}{4}
=
1.5
```

但我们不希望：

```math
\gamma>1
```

所以：

```math
clip(1.5,0,1)
```

得到：

```math
1
```

也就是：

```text
完全压缩
```

---

<a id="origin-12042"></a>
## 215. 所以整个 \(\gamma_i\) 变化过程

可以写成：

```text
i 很小

↓
γ = 0

↓
不压缩


i 逐渐进入过渡区域

↓
γ = 0.25
γ = 0.5
γ = 0.75

↓
逐渐增加压缩程度


i 足够大

↓
γ = 1

↓
充分压缩
```

例如：

| \(i\) | \(\gamma_i\) |
| ----: | -----------: |
|     1 |            0 |
|     2 |            0 |
|     3 |            0 |
|     4 |         0.25 |
|     5 |          0.5 |
|     6 |         0.75 |
|     7 |            1 |
|     8 |            1 |
|     9 |            1 |

---

<a id="origin-12092"></a>
## 216. 完整 YaRN 还会做 Attention Scale 修正

YaRN 除了改变 RoPE 频率之外，

还会对 Attention 的尺度做一定校正。

常见的尺度因子形式可以写成：

```math
\boxed{
m(s)
=
1+0.1\ln s
}
```

当：

```math
s\le1
```

时通常取：

```math
m(s)=1
```

它的目的不是再处理“位置”，

而是：

> **频率变化以后，Q/K 点积和 Attention softmax 的统计分布也可能发生改变，因此适当修正 Attention 的尺度，让长上下文下的 Attention 分布不要和原训练阶段偏离太多。**

这一部分属于 YaRN 的进一步稳定化处理。YaRN 的核心仍然是前面的“按频率选择性插值”。

<a id="origin-12128"></a>
## 217. RoPE、频率分工、位置混叠与 Attention 顺序信息：完整讲义

> 频率分工的关键是：
>
> **同一个 token 的 Q/K 并不是“只属于一个频率”，而是同时包含高频、中频、低频维度。**
>
> 在训练过程中，模型会通过 \(W_Q,W_K\) 和反向传播，自动学习：
>
> - 哪些语义关系更适合依赖高频维度；
> - 哪些长距离关系更适合依赖低频维度；
> - 最终 QK 内积会把所有频率维度的贡献加起来。
>
> 因此长上下文扩展时，不能简单地把所有频率一刀切地压缩。像 YaRN 这类方法会更有针对性地处理不同频率，其中**低频部分更需要做位置插值/压缩，高频部分尽量保留原来的局部分辨能力，中间频率做平滑过渡。**

---

<a id="origin-12144"></a>
## 218. 从二维旋转开始

二维向量：

\[
v=
\begin{bmatrix}
x\\
y
\end{bmatrix}
\]

如果长度为 \(r\)，和 \(x\) 轴夹角为 \(\varphi\)，则：

\[
x=r\cos\varphi
\]

\[
y=r\sin\varphi
\]

如果再旋转 \(\theta\)：

\[
x'=r\cos(\theta+\varphi)
\]

\[
y'=r\sin(\theta+\varphi)
\]

展开得到：

\[
x'=x\cos\theta-y\sin\theta
\]

\[
y'=x\sin\theta+y\cos\theta
\]

因此：

\[
\boxed{
\begin{bmatrix}
x'\\
y'
\end{bmatrix}
=
\begin{bmatrix}
\cos\theta & -\sin\theta\\
\sin\theta & \cos\theta
\end{bmatrix}
\begin{bmatrix}
x\\
y
\end{bmatrix}
}
\]

定义：

\[
R(\theta)
=
\begin{bmatrix}
\cos\theta & -\sin\theta\\
\sin\theta & \cos\theta
\end{bmatrix}
\]

RoPE 的基本思想就是：

> 把 Q、K 的维度两两分组，然后让每一组二维向量按照位置 \(p\) 旋转。

---

<a id="origin-12223"></a>
## 219. RoPE 不是一个频率，而是一组频率

对于第 \(i\) 对维度：

\[
\theta_{p,i}=p\omega_i
\]

其中：

\[
\omega_i
\]

是这一对维度对应的旋转频率。

因此同一个位置 \(p\)，并不是只有一个角度，而是：

\[
[
p\omega_1,
p\omega_2,
p\omega_3,
\dots
]
\]

所以一个 token 在 RoPE 之后，同时拥有：

```text
高频维度
+
中频维度
+
低频维度
```

这点非常重要。

---

<a id="origin-12264"></a>
## 220. “同一个 token 同时有高频和低频”到底是什么意思？

假设一个 Attention Head 的维度是：

\[
d_{\text{head}}=8
\]

RoPE 会把它两两分组：

```text
维度 1,2   → 频率 ω1
维度 3,4   → 频率 ω2
维度 5,6   → 频率 ω3
维度 7,8   → 频率 ω4
```

假设：

```text
ω1 很高
ω2 较高
ω3 较低
ω4 很低
```

那么同一个 token 的 Query：

\[
Q=
[q_1,q_2,q_3,q_4,q_5,q_6,q_7,q_8]
\]

实际上可以理解为：

```text
[q1,q2] → 高频位置通道
[q3,q4] → 中高频位置通道
[q5,q6] → 中低频位置通道
[q7,q8] → 低频位置通道
```

所以：

\[
\boxed{
\text{不是一个 token 选一个频率，而是同一个 token 同时活在很多频率尺度上。}
}
\]

---

<a id="origin-12316"></a>
## 221. 高频和低频分别有什么特点？

<a id="origin-12318"></a>
### 221.1 高频

高频意味着：

\[
\omega_i
\]

比较大。

位置增加一点：

\[
p\rightarrow p+1
\]

角度就变化得比较明显：

\[
(p+1)\omega_i-p\omega_i
=
\omega_i
\]

因此高频对小距离非常敏感。

例如：

```text
距离 1
距离 2
距离 3
```

在高频维度上变化很明显。

所以可以粗略理解为：

\[
\boxed{
\text{高频更适合表达局部、短距离关系}
}
\]

---

<a id="origin-12364"></a>
### 221.2 低频

低频意味着：

\[
\omega_i
\]

比较小。

位置增加很多以后，角度才慢慢变化。

因此：

```text
距离 100
距离 1000
距离 5000
```

低频仍然不会快速重复。

所以可以粗略理解为：

\[
\boxed{
\text{低频更适合保留长距离尺度信息}
}
\]

---

<a id="origin-12396"></a>
## 222. 但是模型并没有被人工规定“高频负责语法，低频负责长距离”

这是一个非常关键的点。

我们并没有硬编码：

```text
高频必须学局部依赖
低频必须学长期依赖
```

真正发生的是：

> 模型在训练过程中，通过 \(W_Q,W_K\) 和反向传播，自动学习如何使用这些不同频率的维度。

也就是说：

\[
Q=xW_Q
\]

\[
K=xW_K
\]

其中：

\[
W_Q,\ W_K
\]

都是训练出来的。

模型可以逐渐学会：

> 哪些语义特征应该投影到某些高频维度上；

以及：

> 哪些语义特征应该更多投影到某些低频维度上。

---

<a id="origin-12439"></a>
## 223. QK 内积是怎么把不同频率“融合”起来的？

RoPE 之后：

\[
Q'_p=R_pQ_p
\]

\[
K'_q=R_qK_q
\]

Attention Score：

\[
S_{p,q}
=
(Q'_p)^TK'_q
\]

最终可以看成很多维度贡献之和：

\[
S_{p,q}
=
\sum_i
\text{第 }i\text{ 组频率的贡献}
\]

也就是：

\[
\boxed{
S_{p,q}
=
S_{p,q}^{(\text{高频})}
+
S_{p,q}^{(\text{中频})}
+
S_{p,q}^{(\text{低频})}
}
\]

因此 QK 并不是：

```text
先选高频
或者
先选低频
```

而是：

> **所有频率一起参加 Attention Score 的计算。**

---

<a id="origin-12496"></a>
## 224. 那模型怎么“知道”某种关系应该看高频还是低频？

答案是：

\[
\boxed{\text{通过训练自动学出来}}
\]

假设一个任务需要强烈区分：

```text
前一个 token
和
前 100 个 token
```

那么高频维度可能很有帮助。

如果某些高频维度对最终 loss 有帮助，反向传播就会推动：

\[
W_Q,\ W_K
\]

让相关语义信息更多地进入这些维度。

---

反过来，如果模型需要理解：

```text
几千 token 以前出现的主题
```

那么低频维度可能更稳定。

训练也会逐渐让某些长期依赖关系更多依赖低频部分。

所以可以这样理解：

```text
RoPE 提供很多“位置尺子”

高频尺子：
刻度很密

低频尺子：
量程很大

模型训练：
自动学会什么关系该更多利用哪把尺子
```

---

<a id="origin-12551"></a>
## 225. 一个非常重要的理解：不是 QK 计算完以后才“挑频率”

严格来说不能说：

> QK 算完以后，模型再决定这次用高频还是低频。

更准确的是：

> 在训练过程中，\(W_Q,W_K\) 会被优化，使得不同语义特征落入不同频率维度；最终 QK 内积自然体现出哪些频率贡献更大。

也就是说：

\[
\boxed{
\text{“选择频率”是训练过程中形成的分工，而不是推理时额外执行一个选择步骤。}
}
\]

---

<a id="origin-12571"></a>
## 226. 举一个自然语言例子

假设当前 token 是：

```text
good
```

前面有两个 `not`。

```text
位置 99： not
位置199： not
位置200： good
```

对于位置 200 的 `good`：

```text
距离 1：
位置199的 not

距离101：
位置99的 not
```

模型可能需要更强烈地关注：

```text
not good
```

这个局部结构。

高频维度因为对：

\[
1
\]

和：

\[
101
\]

的相位差变化更敏感，因此可以帮助模型区分：

> 哪个 `not` 是紧挨着 `good` 的。

---

但如果模型处理的是：

```text
文章开头定义了一个变量
……
几千 token 后继续使用这个变量
```

低频维度因为变化慢，可以为这种长距离关系提供更稳定的位置尺度。

所以最终可能形成：

```text
局部语法关系
→ 高频贡献较大

长距离主题/依赖
→ 低频贡献较大
```

但注意：

\[
\boxed{
\text{这不是人工写死的，而是训练后形成的统计分工。}
}
\]

---

<a id="origin-12653"></a>
## 227. 为什么“转满 360°”不等于“所有情况都见过了”？

因为：

\[
\boxed{
\text{角度是周期的}
}
\]

例如：

\[
0^\circ=360^\circ=720^\circ
\]

但距离：

\[
1,\ 4097,\ 8193
\]

不是一回事。

如果某一个频率：

\[
\omega=\frac{2\pi}{4096}
\]

那么：

\[
4096\omega=2\pi
\]

所以这一组维度上：

\[
R_{4096}=R_0
\]

这说明：

> 这一组频率已经发生周期重复。

不是说明：

> 它已经“见过所有长距离”。

---

<a id="origin-12705"></a>
## 228. 为什么不能让所有维度都转超过一圈？

如果所有维度都很快：

```text
全部都是高速指针
```

那么所有维度都会频繁重复。

相当于钟表中：

```text
秒针
+
秒针
+
秒针
+
秒针
```

这对短距离可能很敏感，但长距离很容易混淆。

真正合理的是：

```text
秒针
+
分针
+
时针
+
更慢的指针
```

也就是：

\[
\boxed{
\text{多尺度频率共同编码位置}
}
\]

---

<a id="origin-12751"></a>
## 229. 位置混叠是什么？

假设一个简化系统最终每 12 个位置完全重复：

\[
R_{p+12}=R_p
\]

那么：

\[
R_1=R_{13}
\]

也就是说：

```text
相对距离 1
```

和：

```text
相对距离 13
```

会具有相同的位置相位。

这叫：

\[
\boxed{\text{Position Aliasing，位置混叠}}
\]

---

<a id="origin-12787"></a>
## 230. 为什么 RoPE 最终体现相对位置？

位置 \(p\)：

\[
Q'_p=R_pQ_p
\]

位置 \(q\)：

\[
K'_q=R_qK_q
\]

Attention：

\[
(Q'_p)^TK'_q
\]

代入：

\[
Q_p^TR_p^TR_qK_q
\]

而：

\[
R_p^TR_q
=
R_{q-p}
\]

所以：

\[
\boxed{
(Q'_p)^TK'_q
=
Q_p^TR_{q-p}K_q
}
\]

最终出现：

\[
q-p
\]

这就是相对位置。

---

<a id="origin-12841"></a>
## 231. 距离 1 和 13 如果一样，会有什么问题？

假设：

\[
R_1=R_{13}
\]

当前 token 在位置：

\[
20
\]

一个 `apple` 在位置：

\[
19
\]

距离：

\[
1
\]

另一个 `apple` 在位置：

\[
7
\]

距离：

\[
13
\]

如果：

\[
R_1=R_{13}
\]

那么 RoPE 本身无法告诉模型：

> 哪个 `apple` 离我 1 个 token，哪个离我 13 个 token。

所以：

\[
\boxed{
\text{不是“相对位置不明显”，而是不同相对位置发生了混叠。}
}
\]

---

<a id="origin-12899"></a>
## 232. 为什么长上下文扩展需要压缩？

假设训练长度：

\[
L_{\text{train}}=4096
\]

推理时扩到：

\[
32768
\]

那么位置对应的角度整体会走到训练期间没有见过的范围。

虽然：

\[
\sin,\cos
\]

数学上仍然能算，但模型训练时形成的：

```text
高频维度如何用
中频维度如何用
低频维度如何用
```

都是基于原始上下文范围学习的。

突然拉到 8 倍长度后：

\[
\boxed{
\text{多频率联合相位分布可能严重超出训练分布}
}
\]

所以需要做上下文扩展。

---

<a id="origin-12943"></a>
## 233. 为什么不能简单“所有频率都除以 8”？

因为所有频率承担的功能并不完全一样。

如果全部统一压缩：

\[
\omega_i'
=
\frac{\omega_i}{8}
\]

那么原本负责局部精细区分的高频也会被拉慢。

结果可能是：

```text
原来距离 1 和距离 2
高频区分得非常明显

压缩以后
两者相位差变小
```

也就是说：

\[
\boxed{
\text{过度压缩高频会损害局部位置分辨率}
}
\]

---

<a id="origin-12977"></a>
## 234. 这就是 YaRN 思想里最关键的一层直觉

可以把频率分成三类理解：

<a id="origin-12981"></a>
### 234.1 高频部分

训练长度内已经旋转很多。

它主要提供：

\[
\boxed{\text{局部位置分辨率}}
\]

这部分通常希望：

```text
尽量保持原来的频率
```

不要过度压缩。

---

<a id="origin-13001"></a>
### 234.2 低频部分

训练长度内可能连一圈都没有转完，或者变化很慢。

当上下文突然扩展很多倍时，它会进入训练阶段未见过的长距离相位区域。

因此更需要：

\[
\boxed{\text{位置插值 / 压缩}}
\]

让它仍然尽量落在模型熟悉的范围。

---

<a id="origin-13017"></a>
### 234.3 中间频率

既不是完全保持，也不是完全压缩。

可以：

\[
\boxed{\text{平滑过渡}}
\]

避免频率空间突然断裂。

---

<a id="origin-13031"></a>
## 235. 把“模型学习频率分工”和“YaRN 压缩低频”连起来

这一段是整个理解中最重要的。

训练阶段：

```text
同一个 token
    ↓
同时进入高频、中频、低频维度
    ↓
WQ / WK 训练
    ↓
不同语义关系逐渐依赖不同频率维度
    ↓
QK 把所有频率贡献加起来
```

因此模型已经形成某种频率分工：

```text
某些局部关系
更依赖高频

某些长距离关系
更依赖低频
```

---

现在如果要扩上下文：

```text
4096
→
32768
```

不能粗暴地把所有频率都改掉。

否则：

> 原来模型已经学好的频率分工会被破坏。

于是更合理的是：

```text
高频：
尽量保留

低频：
重点压缩 / 插值

中频：
平滑过渡
```

这样做的本质目标是：

\[
\boxed{
\text{尽量保留原模型已经学会的“不同频率负责不同尺度关系”的能力}
}
\]

---

<a id="origin-13098"></a>
## 236. 一句话解释“为什么压缩低频”

可以这样记：

> 高频本来就是用来精细区分局部位置的，如果强行压缩，会损害短距离分辨率；低频本来负责长尺度关系，扩上下文时最容易进入训练没见过的相位区域，因此更适合做插值和压缩。

所以：

\[
\boxed{
\text{不是因为低频“不重要”才压缩，而是因为低频承担长距离尺度，扩上下文时更需要调整。}
}
\]

---

<a id="origin-13114"></a>
## 237. 接下来回到 Attention：`A love B` 和 `B love A`

先考虑：

```text
没有位置编码
+
没有 Causal Mask
```

输入：

```text
A love B
```

对应：

\[
X_1=
\begin{bmatrix}
x_A\\
x_{\text{love}}\\
x_B
\end{bmatrix}
\]

交换以后：

```text
B love A
```

对应：

\[
X_2=
\begin{bmatrix}
x_B\\
x_{\text{love}}\\
x_A
\end{bmatrix}
\]

---

<a id="origin-13160"></a>
## 238. 为什么交换位置不会直接改变第一层 Q/K？

因为：

\[
Q=XW_Q
\]

\[
K=XW_K
\]

对于 A：

\[
Q_A=x_AW_Q
\]

\[
K_A=x_AW_K
\]

这里没有：

\[
p
\]

所以 A 从第 1 个位置搬到第 3 个位置以后：

\[
Q_A
\]

本身不会因为“位置编号变化”而改变。

只是从 Q 矩阵的第 1 行搬到了第 3 行。

---

<a id="origin-13200"></a>
## 239. 用矩阵看最清楚

原来：

\[
Q_1=
\begin{bmatrix}
Q_A\\
Q_{\text{love}}\\
Q_B
\end{bmatrix}
\]

交换：

\[
Q_2=
\begin{bmatrix}
Q_B\\
Q_{\text{love}}\\
Q_A
\end{bmatrix}
\]

所以：

\[
\boxed{
Q_A\text{ 没变，只是换了行}
}
\]

K 也是一样。

---

<a id="origin-13236"></a>
## 240. 但 \(S_{B,A}\) 和 \(S_{A,B}\) 一般不一样

定义：

\[
S_{B,A}
=
Q_BK_A^T
\]

\[
S_{A,B}
=
Q_AK_B^T
\]

代入：

\[
Q_B=x_BW_Q
\]

\[
K_A=x_AW_K
\]

得到：

\[
S_{B,A}
=
x_BW_QW_K^Tx_A^T
\]

而：

\[
S_{A,B}
=
x_BW_KW_Q^Tx_A^T
\]

一般：

\[
W_QW_K^T
\neq
W_KW_Q^T
\]

因此：

\[
\boxed{
S_{B,A}
\neq
S_{A,B}
}
\]

---

<a id="origin-13298"></a>
## 241. 为什么这和“没有位置编码”不矛盾？

因为这是两个问题。

<a id="origin-13302"></a>
### 241.1 问题 1

A 看 B 和 B 看 A 是否一样？

答案：

\[
\boxed{\text{一般不一样}}
\]

因为 Query 和 Key 的角色不同。

---

<a id="origin-13316"></a>
### 241.2 问题 2

A 从位置 1 搬到位置 3，是否会因为位置编号变化而自动改变 \(Q_A,K_A\)？

没有位置编码时：

\[
\boxed{\text{不会}}
\]

所以：

\[
\boxed{
\text{Attention 可以有方向性，但仍然缺乏显式的位置顺序信息。}
}
\]

---

<a id="origin-13336"></a>
## 242. 为什么纯 Attention 仍然无法区分 `A love B` 与 `B love A` 的排列？

假设从 `love` 的视角：

\[
\alpha_A=0.6
\]

\[
\alpha_{\text{love}}=0.1
\]

\[
\alpha_B=0.3
\]

对于：

```text
A love B
```

有：

\[
O_{\text{love}}
=
0.6V_A
+
0.1V_{\text{love}}
+
0.3V_B
\]

换成：

```text
B love A
```

矩阵顺序变了，但权重跟着 token 一起换：

\[
O_{\text{love}}
=
0.3V_B
+
0.1V_{\text{love}}
+
0.6V_A
\]

两者相同。

所以纯 Self-Attention 本身更像是在处理：

\[
\boxed{\text{一个“集合”里的内容关系}}
\]

而不是天然知道：

```text
谁在左
谁在右
```

---

<a id="origin-13405"></a>
## 243. 但 GPT 还有 Causal Mask

GPT 中：

```text
A love B
```

`love` 只能看到：

```text
A, love
```

而：

```text
B love A
```

`love` 只能看到：

```text
B, love
```

因此即使没有显式位置编码：

\[
\boxed{
\text{Causal Mask 也会提供一部分“谁在我之前”的顺序信息}
}
\]

---

<a id="origin-13441"></a>
## 244. Causal Mask 和 RoPE 分别解决什么？

<a id="origin-13443"></a>
### 244.1 QK 内容匹配

回答：

> 谁和谁在语义上相关？

---

<a id="origin-13451"></a>
### 244.2 Causal Mask

回答：

> 我允许看谁？

也就是：

\[
\boxed{\text{前后可见性}}
\]

---

<a id="origin-13465"></a>
### 244.3 RoPE

回答：

> 我和他相隔多远？

也就是：

\[
\boxed{\text{相对位置 / 相对距离}}
\]

---

<a id="origin-13479"></a>
## 245. 三者可以这样理解

\[
\boxed{
\text{QK：看谁}
}
\]

\[
\boxed{
\text{Mask：能不能看}
}
\]

\[
\boxed{
\text{RoPE：隔多远}
}
\]

---

<a id="origin-13501"></a>
## 246. 最后把“频率学习”这一层彻底串起来

完整过程可以理解为：

```text
token hidden state
       ↓
WQ / WK 投影
       ↓
Q / K
       ↓
RoPE
       ↓
同一个 token 的 Q/K
同时具有：
高频 + 中频 + 低频
       ↓
QK 内积
       ↓
不同频率维度的贡献相加
       ↓
训练通过 loss
反向调整 WQ / WK
       ↓
逐渐学出：
什么关系更依赖高频
什么关系更依赖低频
```

因此：

\[
\boxed{
\text{频率分工是“学出来的”，不是人工指定的。}
}
\]

---

<a id="origin-13540"></a>
## 247. 为什么 YaRN 不能随便改频率？

因为预训练以后，模型已经形成：

```text
某些特征
→ 依赖某些高频维度

某些特征
→ 依赖某些低频维度
```

如果把所有频率统一大幅修改：

\[
\omega_i\rightarrow\omega_i'
\]

那么原来的频率-语义对应关系就可能被破坏。

因此 YaRN 的核心直觉可以概括为：

```text
高频：
局部分辨率很重要
尽量别动太多

低频：
负责长尺度
扩上下文时重点压缩

中频：
平滑过渡
```

---

<a id="origin-13577"></a>
## 248. 最核心的一张逻辑图

```text
                同一个 token
                     │
                     ▼
                  Q / K
                     │
                     ▼
          ┌──────────┼──────────┐
          │          │          │
          ▼          ▼          ▼
        高频        中频        低频
          │          │          │
          ▼          ▼          ▼
       短距离      中尺度      长距离
       更敏感                  更稳定
          │          │          │
          └──────────┼──────────┘
                     ▼
                   QK 内积
                     │
                     ▼
           所有频率贡献一起相加
                     │
                     ▼
                  loss
                     │
                     ▼
               反向传播训练
                     │
                     ▼
       模型自动形成“频率分工”
```

扩长上下文时：

```text
原上下文 4096
      ↓
扩到 32768
      ↓
不能所有频率一刀切
      ↓
高频尽量保留
低频重点压缩
中频平滑过渡
```

---

<a id="origin-13628"></a>
## 249. 最终结论

<a id="origin-13630"></a>
### 249.1 结论 1

\[
\boxed{
\text{同一个 token 同时包含高频、中频、低频位置通道。}
}
\]

---

<a id="origin-13640"></a>
### 249.2 结论 2

\[
\boxed{
\text{QK 并不会只选一个频率，而是所有频率维度共同参与内积。}
}
\]

---

<a id="origin-13650"></a>
### 249.3 结论 3

\[
\boxed{
\text{训练会通过 }W_Q,W_K\text{ 自动学习不同语义关系更依赖哪些频率维度。}
}
\]

---

<a id="origin-13660"></a>
### 249.4 结论 4

可以粗略理解为：

\[
\boxed{
\text{高频更适合局部、精细距离}
}
\]

\[
\boxed{
\text{低频更适合长距离尺度}
}
\]

但这只是归纳出的功能倾向，不是人工硬编码。

---

<a id="origin-13680"></a>
### 249.5 结论 5

\[
\boxed{
\text{RoPE 的“频率分工”是模型训练后形成的。}
}
\]

因此长上下文扩展时，应该尽量保留这种分工。

---

<a id="origin-13692"></a>
### 249.6 结论 6

YaRN 的直觉就是：

\[
\boxed{
\text{高频尽量保留，低频重点压缩，中频平滑过渡。}
}
\]

这样既尽量保留：

```text
局部位置分辨率
```

又能让：

```text
长距离位置
```

进入更合理的相位范围。

---

<a id="origin-13718"></a>
### 249.7 结论

因此真正完整的一句话是：

> **一个 token 的 Q/K 同时分布在多组高低频 RoPE 维度上；训练通过 \(W_Q,W_K\) 自动学习哪些语义关系应该更多依赖哪些频率，QK 内积再把这些频率贡献统一融合。扩展上下文时，为了不破坏已经学好的频率分工，不能所有频率一起粗暴缩放，而应更多调整负责长距离尺度的低频部分，同时尽量保留高频对局部关系的分辨能力。**

---

<a id="origin-13726"></a>
## 250. 从绝对位置编码到 RoPE 与 YaRN：完整理解位置、高低频与 Attention

---

<a id="origin-13730"></a>
## 251. 为什么 Transformer 需要位置编码？

Self-Attention 本身主要根据 token 之间的内容计算相关性。

如果没有位置编码：

```text
我 喜欢 你
```

和：

```text
你 喜欢 我
```

模型本身并没有天然的“第几个词”的概念。

因此 Transformer 必须额外加入位置信息，让模型知道：

```text
谁在前
谁在后
相隔多远
```

---

<a id="origin-13758"></a>
## 252. 传统绝对位置编码在做什么？

假设一句话：

```text
我   喜欢   浙江大学
0     1       2
```

token embedding 分别为：

$$
x_0,x_1,x_2
$$

给每个位置一个位置向量：

$$
p_0,p_1,p_2
$$

然后：

$$
h_i=x_i+p_i
$$

例如：

$$
h_0=x_0+p_0
$$

$$
h_1=x_1+p_1
$$

$$
h_2=x_2+p_2
$$

所以传统绝对位置编码显式告诉模型的是：

> 我在第几个位置。

例如：

```text
我：位置0
喜欢：位置1
浙江大学：位置2
```

---

<a id="origin-13813"></a>
## 253. Attention 更关心的往往是“相对距离”

例如：

```text
我   很   喜欢   浙江大学
0    1     2        3
```

对于：

```text
喜欢 ↔ 我
```

模型很多时候真正关心的是：

$$
2-0=2
$$

即：

> “我”在“喜欢”前面 2 个位置。

如果整句话整体向后移动：

```text
昨天   我   很   喜欢   浙江大学
0      1    2     3        4
```

现在：

$$
喜欢=3
$$

$$
我=1
$$

但：

$$
3-1=2
$$

相对关系没有变化。

---

<a id="origin-13865"></a>
## 254. 传统绝对位置编码为什么不是天然的相对位置？

传统方式：

$$
h_i=x_i+p_i
$$

然后：

$$
Q_i=(x_i+p_i)W_Q
$$

$$
K_j=(x_j+p_j)W_K
$$

Attention Score：

$$
S_{ij}=Q_iK_j^T
$$

这里直接出现的是：

$$
p_i
$$

和：

$$
p_j
$$

也就是说模型直接拿到的是：

```text
位置 i
位置 j
```

但是：

$$
j-i
$$

并没有直接出现在结构中。

模型当然可以通过训练学会：

```text
位置3和位置1
→ 相差2

位置100和位置98
→ 也相差2
```

但这个相对关系主要是进一步学习出来的。

---

<a id="origin-13930"></a>
## 255. RoPE 的核心思想

RoPE 不把位置直接加到 hidden state 上。

而是：

> 根据 token 所在的位置，去旋转 Q 和 K。

先正常计算：

$$
Q_i=x_iW_Q
$$

$$
K_j=x_jW_K
$$

然后根据位置旋转：

$$
Q_i'=R_iQ_i
$$

$$
K_j'=R_jK_j
$$

其中：

$$
R_i
$$

表示位置 \(i\) 对应的旋转矩阵。

---

<a id="origin-13968"></a>
## 256. 为什么旋转以后天然出现相对位置？

Attention Score：

$$
S_{ij}
=
(Q_i')^TK_j'
$$

代入：

$$
S_{ij}
=
(R_iQ_i)^T(R_jK_j)
$$

得到：

$$
S_{ij}
=
Q_i^TR_i^TR_jK_j
$$

而旋转矩阵满足：

$$
R_i^T=R_{-i}
$$

所以：

$$
R_i^TR_j
=
R_{-i}R_j
=
R_{j-i}
$$

因此：

$$
\boxed{
S_{ij}
=
Q_i^TR_{j-i}K_j
}
$$

这里非常关键。

原来的两个绝对位置：

$$
i,j
$$

最后自然变成：

$$
\boxed{j-i}
$$

因此 RoPE 把相对位置结构直接放进了 Attention 的计算过程。

---

<a id="origin-14038"></a>
## 257. RoPE 不是只有一个旋转频率

假设一个 Attention Head 只有：

$$
d_{head}=6
$$

那么：

$$
Q=
[q_0,q_1,q_2,q_3,q_4,q_5]
$$

RoPE 会两两分组：

$$
(q_0,q_1)
$$

$$
(q_2,q_3)
$$

$$
(q_4,q_5)
$$

写成：

```text
Q = [ q0 q1 | q2 q3 | q4 q5 ]
          ↑       ↑       ↑
        第1组    第2组    第3组
```

每个二维组使用不同旋转频率。

为了方便理解，假设：

$$
\omega_0=60^\circ/\text{token}
$$

$$
\omega_1=10^\circ/\text{token}
$$

$$
\omega_2=1^\circ/\text{token}
$$

于是：

```text
(q0,q1) → 高频：每走1个token转60°
(q2,q3) → 中频：每走1个token转10°
(q4,q5) → 低频：每走1个token转1°
```

---

<a id="origin-14101"></a>
## 258. 高频、低频不是针对不同 token 的

这是最容易误解的地方。

错误理解：

```text
“人咬狗”
→ 高频

“数据库……配置”
→ 低频
```

不是这样。

正确理解是：

> 对于任意两个 token，它们之间的相对距离都会同时进入所有 RoPE 频率维度。

例如：

```text
token A：位置4
token B：位置20
```

那么：

$$
\Delta p=20-4=16
$$

这个：

$$
16
$$

会同时作用到：

```text
高频维度
中频维度
低频维度
```

于是：

$$
\Delta\theta_k
=
\Delta p\cdot\omega_k
$$

---

<a id="origin-14158"></a>
## 259. 同一个距离 16 在不同频率中如何表示？

假设：

$$
\Delta p=16
$$

三个频率：

$$
\omega_H=60^\circ
$$

$$
\omega_M=10^\circ
$$

$$
\omega_L=1^\circ
$$

那么：

<a id="origin-14182"></a>
### 259.1 高频

$$
16\times60^\circ
=
960^\circ
$$

<a id="origin-14190"></a>
#### 259.1.1 中频

$$
16\times10^\circ
=
160^\circ
$$

<a id="origin-14198"></a>
#### 259.1.2 低频

$$
16\times1^\circ
=
16^\circ
$$

所以：

$$
\boxed{
16
\rightarrow
\begin{cases}
960^\circ & 高频\\
160^\circ & 中频\\
16^\circ & 低频
\end{cases}
}
$$

这里并不是：

```text
高频表示16的一部分
中频表示16的一部分
低频表示16的一部分
```

而是：

> 三个频率都在完整描述同一个距离 16，只是使用的“尺子”不同。

---

<a id="origin-14234"></a>
## 260. 钟表类比

同一个时间：

```text
10:23:40
```

同时由：

```text
秒针
分针
时针
```

表示。

秒针：

```text
转得快
→ 高频
```

时针：

```text
转得慢
→ 低频
```

但不是：

```text
秒针表示时间的一部分
时针表示另一部分
```

而是：

> 不同速度的指针共同描述同一个时间。

RoPE 也是如此：

```text
同一个相对距离
        ↓
高频表示一次
中频表示一次
低频表示一次
```

---

<a id="origin-14289"></a>
## 261. 为什么需要高频？

假设：

$$
\omega_H=60^\circ/\text{token}
$$

距离：

$$
\Delta p=1
$$

得到：

$$
60^\circ
$$

距离：

$$
\Delta p=2
$$

得到：

$$
120^\circ
$$

只移动：

$$
1\text{ token}
$$

角度就变化：

$$
60^\circ
$$

因此：

> 高频对局部位置变化非常敏感。

适合区分：

```text
距离1
距离2
距离3
```

这种精细的位置关系。

---

<a id="origin-14349"></a>
## 262. 高频的问题：快速绕圈

还是：

$$
\omega_H=60^\circ
$$

距离 1：

$$
1\times60^\circ
=
60^\circ
$$

距离 7：

$$
7\times60^\circ
=
420^\circ
$$

但是：

$$
420^\circ
=
360^\circ+60^\circ
$$

所以：

$$
420^\circ\equiv60^\circ
$$

于是：

```text
距离1 → 60°
距离7 → 60°
```

在这一组高频维度中发生了“撞车”。

同理：

```text
距离1
距离7
距离13
距离19
...
```

都可能周期性地出现相同相位。

---

<a id="origin-14410"></a>
## 263. 为什么需要低频？

假设低频：

$$
\omega_L=5^\circ/\text{token}
$$

那么：

距离 1：

$$
5^\circ
$$

距离 7：

$$
35^\circ
$$

距离 13：

$$
65^\circ
$$

虽然高频：

```text
距离1 → 60°
距离7 → 60°
```

撞车了，

低频却有：

```text
距离1 → 5°
距离7 → 35°
```

所以可以把它们区分开。

因此：

$$
\boxed{
高频：局部分辨率高，但很快绕圈
}
$$

$$
\boxed{
低频：局部分辨率低，但量程更长
}
$$

---

<a id="origin-14472"></a>
## 264. “位置不敏感”不等于“不需要位置”

这是理解低频最重要的一点。

低频所谓“不敏感”，指的是：

> 对相差 1、2 个 token 这样的微小变化不太敏感。

并不是：

> 完全不记录位置信息。

例如低频：

$$
\omega_L=0.5^\circ/\text{token}
$$

那么：

$$
\Delta p=1
\Rightarrow0.5^\circ
$$

$$
\Delta p=2
\Rightarrow1^\circ
$$

两者差别很小。

但：

$$
\Delta p=100
\Rightarrow50^\circ
$$

$$
\Delta p=500
\Rightarrow250^\circ
$$

差别就很大了。

因此可以理解为：

```text
高频：
1 和 2 要分得很清楚

低频：
1 和 2 差不多
但 2 和 500 必须能分开
```

---

<a id="origin-14531"></a>
## 265. 真正的文本例子：数据库—配置

假设模型看到这样一段文本：

> 系统启动后，会读取数据库连接信息。随后程序初始化日志模块、线程池、缓存模块和权限系统。如果服务仍然无法连接，请重新检查前面填写的数据库配置。

为了方便，假设关键 token 的位置是：

```text
位置10：数据库
位置30：日志
位置50：缓存
位置70：权限

位置80：重新
位置81：检查
位置82：数据库
位置83：配置
```

这里同时存在：

```text
局部关系
+
长距离关系
```

---

<a id="origin-14561"></a>
## 266. 局部关系：“数据库 配置”

最后：

```text
数据库 配置
82      83
```

两者距离：

$$
83-82=1
$$

这是一个很强的局部关系。

模型很容易认为：

> “数据库”和“配置”很可能直接组成“数据库配置”这个短语。

如果变成：

```text
数据库 的 连接 配置
```

或者：

```text
数据库发生故障，请修改对应的配置
```

虽然仍有语义关系，但局部结构已经不同。

这种：

$$
1,2,3
$$

token 的精细差异，就是高频非常擅长表达的。

---

<a id="origin-14606"></a>
## 267. 但还有一个更远的“数据库”

前面还有：

```text
位置10：数据库
```

而后面：

```text
位置83：配置
```

所以：

$$
83-10=73
$$

这里：

```text
数据库 ............... 配置
```

属于一个明显的长距离关系。

为什么“配置”还需要考虑前面位置 10 的“数据库”？

因为前面已经建立了一个主题：

> 当前系统正在处理数据库连接。

后面的：

```text
请重新检查……配置
```

到底是什么配置？

可能是：

```text
数据库配置
日志配置
缓存配置
权限配置
线程池配置
```

这些词在语义上都能够和“配置”搭配。

因此模型需要结合前文：

```text
数据库
日志
缓存
权限
```

一起判断。

---

<a id="origin-14673"></a>
## 268. “配置”会和很多前文 token 做 Attention

当前：

$$
Q_{\text{配置}}
$$

可能会和：

$$
K_{\text{数据库}}
$$

$$
K_{\text{日志}}
$$

$$
K_{\text{缓存}}
$$

$$
K_{\text{权限}}
$$

分别计算 Attention Score。

例如：

$$
S(\text{配置},\text{数据库})
$$

$$
S(\text{配置},\text{日志})
$$

$$
S(\text{配置},\text{缓存})
$$

$$
S(\text{配置},\text{权限})
$$

仅仅从语义看：

```text
数据库配置
日志配置
缓存配置
权限配置
```

其实都说得通。

这时候位置就可以提供额外的结构信息。

---

<a id="origin-14734"></a>
## 269. 这些候选与“配置”的距离

假设：

```text
数据库：位置10
日志：位置30
缓存：位置50
权限：位置70
配置：位置83
```

那么：

$$
83-10=73
$$

$$
83-30=53
$$

$$
83-50=33
$$

$$
83-70=13
$$

所以模型不仅看到：

```text
数据库
日志
缓存
权限
```

这些内容，

还可以知道：

```text
数据库 → 配置：距离73
日志   → 配置：距离53
缓存   → 配置：距离33
权限   → 配置：距离13
```

注意：

> Attention 并不是简单地认为“距离最近的最好”。

即使“权限”距离更近，整段语义仍然可能让“数据库”获得更高 Attention。

位置只是其中一个因素。

---

<a id="origin-14794"></a>
## 270. 低频到底给“数据库—配置”提供了什么？

假设低频：

$$
\omega_L=1^\circ/\text{token}
$$

那么：

```text
权限 → 配置
距离13
```

对应：

$$
13^\circ
$$

```text
缓存 → 配置
距离33
```

对应：

$$
33^\circ
$$

```text
日志 → 配置
距离53
```

对应：

$$
53^\circ
$$

```text
数据库 → 配置
距离73
```

对应：

$$
73^\circ
$$

所以低频可以比较稳定地表达：

```text
13
33
53
73
```

这些不同的长距离尺度。

---

<a id="origin-14861"></a>
## 271. 为什么“73 和 74”不需要特别敏感？

假设“数据库”从位置 10 变成位置 9：

原来：

$$
\Delta p=73
$$

现在：

$$
\Delta p=74
$$

低频：

$$
73^\circ
\rightarrow
74^\circ
$$

只变化：

$$
1^\circ
$$

这非常合理。

因为从语言角度看：

```text
数据库在73个token之前
```

和：

```text
数据库在74个token之前
```

通常没有本质区别。

模型不需要像区分：

```text
相邻
和
隔一个词
```

那样精细。

---

<a id="origin-14919"></a>
## 272. 但距离 3 和距离 73 就完全不同

距离 3：

$$
3^\circ
$$

距离 73：

$$
73^\circ
$$

差：

$$
70^\circ
$$

所以低频很容易区分：

```text
数据库 配置
```

这种局部关系，

和：

```text
数据库 ............... 配置
```

这种跨句、跨段的长距离关系。

所以低频真正想表达的不是：

> 精确相隔 73 个 token。

而更像：

> 这是附近关系，还是较远关系，还是非常远的关系。

---

<a id="origin-14965"></a>
## 273. 为什么只用高频会出问题？

假设高频：

$$
\omega_H=60^\circ/\text{token}
$$

距离 1：

$$
1\times60^\circ
=
60^\circ
$$

距离 7：

$$
7\times60^\circ
=
420^\circ
\equiv60^\circ
$$

距离 13：

$$
13\times60^\circ
=
780^\circ
\equiv60^\circ
$$

距离 73：

$$
73\times60^\circ
=
4380^\circ
\equiv60^\circ
$$

于是出现：

```text
距离1  → 60°
距离7  → 60°
距离13 → 60°
距离73 → 60°
```

只看这一组高频：

> “数据库”到底紧挨着“配置”，还是隔了 73 个 token，完全分不出来。

---

<a id="origin-15023"></a>
## 274. 低频马上能把它们区分开

如果：

$$
\omega_L=1^\circ
$$

那么：

```text
距离1  → 1°
距离7  → 7°
距离13 → 13°
距离73 → 73°
```

所以：

| 距离 | 高频 \(60^\circ/token\) | 低频 \(1^\circ/token\) |
| -: | --------------------: | -------------------: |
|  1 |          \(60^\circ\) |          \(1^\circ\) |
|  7 |          \(60^\circ\) |          \(7^\circ\) |
| 13 |          \(60^\circ\) |         \(13^\circ\) |
| 73 |          \(60^\circ\) |         \(73^\circ\) |

这就是为什么：

> 即使某些关系对精确位置不敏感，仍然需要记录位置。

因为模型仍然需要知道：

$$
\boxed{
这是局部关系，还是长距离关系
}
$$

---

<a id="origin-15063"></a>
## 275. 低频记录的是“粗粒度距离结构”

可以把低频理解成在回答：

```text
离我很近？
↓
隔了一句话？
↓
隔了一段？
↓
隔了几百个 token？
↓
非常远？
```

而不是一定要回答：

```text
到底是73还是74？
```

所以：

$$
\boxed{
低频不是不要位置
}
$$

而是：

$$
\boxed{
不要太精细的位置，但仍需要大尺度位置
}
$$

---

<a id="origin-15103"></a>
## 276. 高频和低频可以理解成不同地图比例尺

高频像：

```text
城市街道地图
```

可以看清：

```text
前一栋楼
后一栋楼
隔一个路口
```

但看全国就容易乱。

低频像：

```text
全国地图
```

两栋楼之间差：

```text
20米
```

几乎看不出来。

但：

```text
北京
上海
广州
```

之间的宏观距离非常清楚。

所以：

> 低频牺牲局部分辨率，换取长距离量程。

---

<a id="origin-15151"></a>
## 277. 真实模型中有很多频率

例如：

$$
d_{head}=128
$$

RoPE 会把它分成：

$$
64
$$

个二维组：

```text
(q0,q1)       → ω0
(q2,q3)       → ω1
(q4,q5)       → ω2
...
(q126,q127)   → ω63
```

频率一般按照类似：

$$
\omega_k
=
\frac{1}{\text{base}^{2k/d}}
$$

逐渐降低。

因此：

```text
前面的二维组
→ 高频

中间
→ 中频

后面的二维组
→ 低频
```

---

<a id="origin-15200"></a>
## 278. 同样两个 token 同时拥有所有频率

假设：

```text
A 在位置4
B 在位置20
```

那么：

$$
\Delta p=16
$$

所有二维组都会计算：

$$
16\omega_0
$$

$$
16\omega_1
$$

$$
16\omega_2
$$

$$
\cdots
$$

$$
16\omega_{63}
$$

所以：

$$
\boxed{
同样两个 token 同时拥有高频、中频、低频的位置表示
}
$$

不是：

```text
某些 token 对属于高频
另一些 token 对属于低频
```

---

<a id="origin-15254"></a>
## 279. 为什么训练后某些频率贡献会更大？

最终 Attention Score 可以写成：

$$
S_{ij}
=
\sum_k
Q_{i,k}^T
R((j-i)\omega_k)
K_{j,k}
$$

每一个二维频率组都贡献一部分：

$$
S_0+S_1+S_2+\cdots
$$

而：

$$
Q=xW_Q
$$

$$
K=xW_K
$$

其中：

$$
W_Q,W_K
$$

都是训练得到的。

因此模型可以学习：

> 把更多语义信息放到某些 RoPE 频率对应的维度上。

---

<a id="origin-15297"></a>
## 280. 高频贡献更大的例子

假设只有两个二维组：

```text
高频组
低频组
```

训练以后：

$$
Q=
[3,0\mid0.2,0]
$$

$$
K=
[3,0\mid0.2,0]
$$

那么：

```text
高频：
Q_H=[3,0]
K_H=[3,0]

低频：
Q_L=[0.2,0]
K_L=[0.2,0]
```

显然高频部分的数值更强。

因此：

$$
S_H
=
Q_H^TR_HK_H
$$

很可能远大于：

$$
S_L
=
Q_L^TR_LK_L
$$

于是：

$$
S_H\gg S_L
$$

可以理解为：

> 当前关系主要依赖高频位置维度。

---

<a id="origin-15360"></a>
## 281. 低频贡献更大的具体例子

反过来：

$$
Q=
[0.2,0\mid4,0]
$$

$$
K=
[0.2,0\mid4,0]
$$

其中：

```text
高频：
Q_H=[0.2,0]
K_H=[0.2,0]

低频：
Q_L=[4,0]
K_L=[4,0]
```

假设：

$$
\Delta p=10
$$

高频：

$$
\omega_H=30^\circ
$$

低频：

$$
\omega_L=2^\circ
$$

---

<a id="origin-15406"></a>
### 281.1 高频贡献

$$
10\times30^\circ
=
300^\circ
$$

所以：

$$
S_H
=
0.2\times0.2\times\cos300^\circ
$$

因为：

$$
\cos300^\circ=0.5
$$

所以：

$$
S_H
=
0.02
$$

---

<a id="origin-15438"></a>
### 281.2 低频贡献

$$
10\times2^\circ
=
20^\circ
$$

所以：

$$
S_L
=
4\times4\times\cos20^\circ
$$

因为：

$$
\cos20^\circ\approx0.94
$$

所以：

$$
S_L
\approx
16\times0.94
$$

得到：

$$
S_L
\approx15.04
$$

最终：

$$
S
=
S_H+S_L
$$

$$
S
=
0.02+15.04
$$

所以：

$$
\boxed{
S\approx15.06
}
$$

其中：

$$
\boxed{
S_L\gg S_H
}
$$

说明这一对 token 的 Attention Score 主要由低频维度贡献。

---

<a id="origin-15509"></a>
## 282. \(W_Q,W_K\) 到底在学习什么？

注意：

$$
W_Q,W_K
$$

并不会直接修改：

$$
\omega_k
$$

也就是说，它不会把：

```text
60°/token
```

训练成：

```text
70°/token
```

RoPE 的频率是预先规定的。

\(W_Q,W_K\) 学的是：

> 当前 token 的语义信息应该被投影到哪些维度上。

而不同维度恰好对应不同 RoPE 频率。

因此可以理解为：

$$
\boxed{
W_Q,W_K
\rightarrow
决定各频率维度上的 Q/K 信息强度
}
$$

而：

$$
\boxed{
RoPE
\rightarrow
决定这些维度旋转多快
}
$$

---

<a id="origin-15565"></a>
## 283. “人咬狗”和“数据库配置”应该如何正确理解？

错误说法：

```text
人咬狗 → 高频
数据库配置 → 低频
```

这不准确。

正确说法是：

> 任意 token 对都会同时经过全部 RoPE 频率。

但是训练以后：

> 对于某些局部顺序敏感的关系，模型可能更加利用高频维度。

例如：

```text
人 咬 狗
```

和：

```text
狗 咬 人
```

位置稍微变化，意义就大幅变化。

所以模型可能更加依赖：

```text
对 +1、-1 这种局部变化特别敏感
```

的高频维度。

而长距离关系：

```text
数据库 ............... 配置
```

可能更多利用：

```text
变化较慢、量程更长
```

的低频维度。

但这只是：

$$
\boxed{
训练后形成的偏好
}
$$

而不是 RoPE 事先规定的硬规则。

---

<a id="origin-15632"></a>
## 284. 现在进入 YaRN：为什么需要上下文扩展？

假设模型训练时：

$$
L_{\text{train}}=8192
$$

现在希望：

$$
L_{\text{new}}=32768
$$

扩展了：

$$
s=4
$$

如果仍然使用原来的 RoPE：

$$
p\omega_k
$$

当：

$$
p
$$

越来越大时，就会进入训练阶段没有充分见过的位置相位区域。

因此需要重新调整：

> 位置到旋转角度之间的映射。

---

<a id="origin-15672"></a>
## 285. 最简单的方法：Position Interpolation

扩展：

$$
4\times
$$

最简单的方法：

$$
p'
=
\frac p4
$$

例如：

$$
p=20
$$

RoPE 计算时当成：

$$
p'=5
$$

使用。

因为：

$$
\theta=p\omega
$$

所以：

$$
\frac p4\omega
=
p\frac{\omega}{4}
$$

因此：

> 压缩 position

和：

> 把频率除以 4

在这里是等价的。

---

<a id="origin-15728"></a>
## 286. Position Interpolation 的问题

普通 PI 会：

$$
\omega_k'
=
\frac{\omega_k}{4}
$$

所有频率全部统一压缩。

例如：

```text
高频：60° → 15°
中频：10° → 2.5°
低频：1°  → 0.25°
```

这虽然能够把位置范围压回训练分布，但会让原本有用的高频局部分辨率也被大幅削弱。

因此 YaRN 不选择完全一刀切。

---

<a id="origin-15754"></a>
## 287. YaRN 的核心思想

可以简化理解为：

```text
高频
→ 训练时已经经历过很多旋转
→ 可以少压

中频
→ 平滑过渡

低频
→ 训练时旋转范围较小
→ 更需要压缩
```

注意：

YaRN 并没有修改：

$$
j-i
$$

真实相对距离始终不变。

它改变的是：

$$
\omega_k
$$

从而改变：

$$
(j-i)\omega_k
$$

---

<a id="origin-15795"></a>
## 288. 一个简化的 YaRN 数字例子

假设：

$$
\omega_H=60^\circ
$$

$$
\omega_M=10^\circ
$$

$$
\omega_L=1^\circ
$$

为了教学，假设 YaRN 后：

$$
\omega_H'=60^\circ
$$

$$
\omega_M'=6^\circ
$$

$$
\omega_L'=0.25^\circ
$$

对于：

$$
\Delta p=16
$$

原始 RoPE：

$$
16\times60^\circ=960^\circ
$$

$$
16\times10^\circ=160^\circ
$$

$$
16\times1^\circ=16^\circ
$$

YaRN 后：

$$
16\times60^\circ=960^\circ
$$

$$
16\times6^\circ=96^\circ
$$

$$
16\times0.25^\circ=4^\circ
$$

于是：

| 频率 |       原始 RoPE |          YaRN |
| -- | ------------: | ------------: |
| 高频 | \(960^\circ\) | \(960^\circ\) |
| 中频 | \(160^\circ\) |  \(96^\circ\) |
| 低频 |  \(16^\circ\) |   \(4^\circ\) |

真实距离始终：

$$
\boxed{16}
$$

变的是：

$$
\boxed{
这个距离在不同频率维度上产生多大的旋转
}
$$

---

<a id="origin-15883"></a>
## 289. 为什么 YaRN 尤其要压低频？

假设训练长度：

$$
L=8
$$

低频：

$$
\omega_L=1^\circ/token
$$

训练阶段最大：

$$
8\times1^\circ
=
8^\circ
$$

也就是说：

> 模型训练时，这组低频只见过大约 \(0^\circ\sim8^\circ\)。

现在上下文扩大到：

$$
32
$$

如果频率不变：

$$
32\times1^\circ
=
32^\circ
$$

模型会进入：

```text
8° ~ 32°
```

这些训练时没有充分见过的区域。

如果压成：

$$
0.25^\circ/token
$$

那么：

$$
32\times0.25^\circ
=
8^\circ
$$

重新压回训练阶段熟悉的范围。

---

<a id="origin-15949"></a>
## 290. 高频为什么可以少压？

假设高频：

$$
\omega_H=60^\circ/token
$$

训练长度：

$$
8
$$

那么：

$$
8\times60^\circ
=
480^\circ
$$

已经超过：

$$
360^\circ
$$

即训练阶段就已经经历了一整圈甚至更多的相位。

因此：

> 高频继续向后扩展时，不像低频那样立刻进入完全没见过的新相位。

所以 YaRN 可以让高频少压缩。

---

<a id="origin-15987"></a>
## 291. YaRN 压低频以后，低频是不是没有用了？

不是。

假设原低频：

$$
1^\circ/token
$$

YaRN 后：

$$
0.25^\circ/token
$$

那么：

$$
\Delta p=1
\Rightarrow0.25^\circ
$$

确实非常小。

但：

$$
\Delta p=100
\Rightarrow25^\circ
$$

$$
\Delta p=500
\Rightarrow125^\circ
$$

$$
\Delta p=1000
\Rightarrow250^\circ
$$

所以：

```text
1 token    → 0.25°
10 token   → 2.5°
100 token  → 25°
500 token  → 125°
1000 token → 250°
```

它仍然在记录位置。

只是：

> 局部精度降低了，长距离量程增加了。

---

<a id="origin-16047"></a>
## 292. 再回到“数据库—配置”看 YaRN

假设：

```text
数据库：位置10
配置：位置83
```

距离：

$$
73
$$

原低频：

$$
1^\circ/token
$$

得到：

$$
73^\circ
$$

YaRN 后：

$$
0.25^\circ/token
$$

得到：

$$
73\times0.25^\circ
=
18.25^\circ
$$

如果数据库移动一个 token：

$$
73\rightarrow74
$$

则：

$$
18.25^\circ
\rightarrow
18.5^\circ
$$

只差：

$$
0.25^\circ
$$

说明：

> YaRN 后更加不在乎“73 和 74”的区别。

这没有问题。

因为语言上：

```text
相隔73个token
```

和：

```text
相隔74个token
```

通常没有本质差异。

---

<a id="origin-16130"></a>
## 293. 但距离 3、73、500 仍然明显不同

YaRN 后低频：

$$
0.25^\circ/token
$$

距离 3：

$$
3\times0.25^\circ
=
0.75^\circ
$$

距离 73：

$$
73\times0.25^\circ
=
18.25^\circ
$$

距离 500：

$$
500\times0.25^\circ
=
125^\circ
$$

于是：

```text
距离3
→ 很近

距离73
→ 中长距离

距离500
→ 很远
```

仍然存在明显差异。

所以 YaRN 真正在做的是：

> 进一步牺牲“精确距离”，换取更长的有效位置范围。

---

<a id="origin-16183"></a>
## 294. 用一句话理解低频和 YaRN

低频本来就在说：

> 我不在乎 73 和 74，但我在乎 3 和 500。

YaRN 进一步说：

> 那我就让你更不在乎 73 和 74，把这部分分辨率换成更长的量程，让你能够继续区分几百、几千 token 的位置结构。

---

<a id="origin-16195"></a>
## 295. 完整计算流程

假设：

```text
A：位置4
B：位置20
```

那么：

$$
\Delta p=16
$$

先计算：

$$
x_A
\xrightarrow{W_Q}
Q_A
$$

$$
x_B
\xrightarrow{W_K}
K_B
$$

假设：

$$
d_{head}=128
$$

那么 Q、K 被分成：

$$
64
$$

个二维 RoPE 组：

```text
高频
↓
中高频
↓
中频
↓
中低频
↓
低频
```

每一组有自己的：

$$
\omega_k
$$

于是：

$$
\Delta\theta_k
=
16\omega_k
$$

每组贡献一个 Attention Score：

$$
S_k
=
Q_{A,k}^T
R(16\omega_k)
K_{B,k}
$$

最终：

$$
\boxed{
S_{AB}
=
\sum_kS_k
}
$$

而：

$$
Q_{A,k},K_{B,k}
$$

来自训练后的：

$$
W_Q,W_K
$$

所以模型能够学习：

```text
某些关系
→ 高频贡献更大

另一些关系
→ 中频贡献更大

另一些关系
→ 低频贡献更大
```

---

<a id="origin-16311"></a>
## 296. RoPE、\(W_Q/W_K\)、YaRN 的职责分工

<a id="origin-16313"></a>
### 296.1 \(W_Q,W_K\)

负责：

$$
x\rightarrow Q,K
$$

决定：

> 语义信息主要投影到哪些维度。

也就间接决定：

$$
\boxed{
哪些 RoPE 频率维度对 Attention Score 贡献更大
}
$$

---

<a id="origin-16335"></a>
### 296.2 RoPE

负责定义：

$$
\omega_0,\omega_1,\dots
$$

根据位置：

$$
p
$$

产生：

$$
p\omega_k
$$

决定：

> 不同维度的位置旋转速度。

---

<a id="origin-16361"></a>
### 296.3 YaRN

在上下文扩展时：

$$
\omega_k
\rightarrow
\omega_k'
$$

于是：

$$
(j-i)\omega_k
$$

变成：

$$
(j-i)\omega_k'
$$

决定：

> 不同位置尺度的“尺子”到底要拉长多少。

---

<a id="origin-16389"></a>
## 297. 最终总结

<a id="origin-16391"></a>
### 297.1 第一层：真实距离只有一个

两个 token 的相对距离：

$$
\boxed{
\Delta p=j-i
}
$$

例如：

$$
20-4=16
$$

这个真实距离不会因为 RoPE 或 YaRN 改变。

---

<a id="origin-16411"></a>
### 297.2 第二层：同一个距离经过很多频率

$$
16
$$

会同时进入：

$$
16\omega_0
$$

$$
16\omega_1
$$

$$
\cdots
$$

$$
16\omega_{63}
$$

因此：

$$
\boxed{
同一个相对距离
\rightarrow
很多不同尺度的位置表示
}
$$

---

<a id="origin-16447"></a>
### 297.3 第三层：高频和低频

高频：

$$
\boxed{
小距离变化
\rightarrow
大角度变化
}
$$

特点：

```text
局部分辨率高
变化快
容易绕圈
```

低频：

$$
\boxed{
小距离变化
\rightarrow
小角度变化
}
$$

特点：

```text
局部分辨率低
变化慢
量程更长
```

---

<a id="origin-16487"></a>
### 297.4 第四层：低频为什么仍然要记录位置？

因为：

> “不在乎精确距离”并不等于“不在乎距离”。

例如：

```text
数据库 → 配置
```

模型可能不在乎：

```text
距离73
还是
距离74
```

但一定有必要知道：

```text
距离3
距离73
距离500
```

分别属于完全不同的位置尺度。

因此低频记录的是：

$$
\boxed{
粗粒度、长距离的位置结构
}
$$

---

<a id="origin-16527"></a>
### 297.5 第五层：模型如何决定更依赖哪种频率？

通过：

$$
W_Q,W_K
$$

模型可以让不同 RoPE 维度中的 Q/K 分量具有不同大小和方向。

因此：

$$
S_{ij}
=
\sum_k
Q_{i,k}^T
R((j-i)\omega_k)
K_{j,k}
$$

不同频率组：

$$
k
$$

对最终 Attention Score 的贡献可以不同。

---

<a id="origin-16558"></a>
### 297.6 第六层：YaRN

YaRN 不改变：

$$
\boxed{
j-i
}
$$

它改变的是：

$$
\boxed{
\omega_k
}
$$

因此：

$$
(j-i)\omega_k
$$

变成：

$$
(j-i)\omega_k'
$$

可以粗略理解：

```text
高频
→ 少压缩

中频
→ 平滑调整

低频
→ 更强压缩
```

最终：

> 尽量保留局部位置分辨能力，同时把长距离的位置尺子拉长，以支持更长上下文。

---

<a id="origin-16607"></a>
## 298. 一句话理解整个故事

> **RoPE 用很多不同频率同时描述同一个相对距离：高频像放大镜，擅长区分 1、2、3 个 token 的局部差异，但容易快速绕圈；低频像全国地图，不在乎 73 和 74 的细微区别，却能区分 3、73、500 这种不同距离尺度。模型通过 \(W_Q,W_K\) 学习哪些频率维度对当前语义关系更重要，而 YaRN 在长上下文扩展时进一步拉长这些“位置尺子”，尤其让低频覆盖更大的距离范围。**

最核心的公式：

$$
\boxed{
S_{ij}
=
\sum_k
Q_{i,k}^T
R((j-i)\omega_k)
K_{j,k}
}
$$

YaRN 后：

$$
\boxed{
S_{ij}
=
\sum_k
Q_{i,k}^T
R((j-i)\omega_k')
K_{j,k}
}
$$

其中：

$$
\boxed{
j-i
}
$$

始终是真实相对距离，

而：

$$
\boxed{
\omega_k
}
$$

决定模型用什么尺度去观察这个距离。

---

<a id="origin-16659"></a>
## 299. 传统位置编码完整讲义：从绝对位置到相对位置

<a id="origin-16661"></a>
## 300. 为什么 Transformer 必须加入位置编码？

先看一句话：

```text
我 喜欢 小明
```

和：

```text
小明 喜欢 我
```

这两句话包含的 token 是一样的：

```text
我
喜欢
小明
```

但是顺序完全不同，语义也完全不同。

问题在于：

> Self-Attention 本身并不知道 token 的先后顺序。

如果只看 token embedding：

```math
X_{\text{我}}
```

```math
X_{\text{喜欢}}
```

```math
X_{\text{小明}}
```

模型知道：

```text
这个词是谁
```

但是不知道：

```text
它在第几个位置
```

所以 Transformer 必须额外加入：

```text
Position Encoding
位置编码
```

---

<a id="origin-16724"></a>
## 301. Token Embedding 和 Position Encoding 分别解决什么问题？

可以简单理解为：

```text
Token Embedding
↓
告诉模型：
“我是谁？”
```

例如：

```text
我
喜欢
小明
```

都有自己的语义表示。

而：

```text
Position Encoding
↓
告诉模型：
“我在哪里？”
```

例如：

```text
我      → 第1个位置
喜欢    → 第2个位置
小明    → 第3个位置
```

最后把两者加起来：

```math
H_i=X_i+P_i
```

其中：

```text
Xi = token embedding
Pi = position encoding
```

于是模型得到的是：

```text
“我是谁”
+
“我在哪里”
```

---

<a id="origin-16785"></a>
## 302. 先用一个极度简化的例子理解位置编码

假设 token embedding 只有 3 维：

```math
X=[1,2,3]
```

现在为了教学方便，我们人为规定：

```text
第1个位置 → 0.1
第2个位置 → 0.2
第3个位置 → 0.3
```

那么最简单的想法可能是：

```text
位置1 → 0.1
位置2 → 0.2
位置3 → 0.3
```

但问题来了：

> 这个 0.1 到底放到向量的哪一维？

比如可以写成：

```math
P_1=[0.1,0,0]
```

也可以：

```math
P_1=[0,0.1,0]
```

还可以：

```math
P_1=[0,0,0.1]
```

到底哪个对？

答案是：

<a id="origin-16835"></a>
## 303. 都可以。

---

<a id="origin-16839"></a>
## 304. 为什么放第一维、第二维、第三维都可以？

假设我们规定：

```text
位置1 → 0.1
位置2 → 0.2
位置3 → 0.3
```

我们完全可以采用方案 A：

```text
位置1 → [0.1,0,0]
位置2 → [0.2,0,0]
位置3 → [0.3,0,0]
```

也可以采用方案 B：

```text
位置1 → [0,0.1,0]
位置2 → [0,0.2,0]
位置3 → [0,0.3,0]
```

甚至可以采用方案 C：

```text
位置1 → [0,0,0.1]
位置2 → [0,0,0.2]
位置3 → [0,0,0.3]
```

三种方式都能够区分位置。

因为只要：

```math
P_1\neq P_2\neq P_3
```

模型就能知道：

```text
它们不是同一个位置。
```

---

<a id="origin-16889"></a>
## 305. 那为什么之前会写成 `[0,0.1,0]`？

只是为了方便举例。

例如：

```math
X=[1,2,3]
```

位置编码：

```math
P_1=[0,0.1,0]
```

那么：

```math
H=X+P_1
```

得到：

```math
H=[1,2.1,3]
```

目的只是为了展示：

```text
Token Embedding
+
Position Encoding
```

这个过程。

并不是说：

```text
位置一定要加在第2维
```

也不是说：

```text
第2维专门负责位置
```

所以：

> `[0,0.1,0]` 只是一个教学例子，不是 Transformer 真实的位置编码方式。

---

<a id="origin-16945"></a>
## 306. 为什么模型能知道 `[0.1,0,0]` 和 `[0,0.1,0]` 不一样？

因为它们是两个不同的向量。

例如：

```math
A=[0.1,0,0]
```

```math
B=[0,0.1,0]
```

后面假设接一个矩阵：

```math
W=
\begin{bmatrix}
10\\
20\\
30
\end{bmatrix}
```

那么：

```math
AW
=
0.1\times10
=
1
```

而：

```math
BW
=
0.1\times20
=
2
```

所以：

```text
虽然数值都是 0.1，
但是所在维度不同，
经过矩阵运算以后结果就不同。
```

因此模型当然能够区分。

---

<a id="origin-17002"></a>
## 307. 但这里有一个更重要的问题

如果我们真的这样设计：

```text
位置1 → [0.1,0,0]
位置2 → [0.2,0,0]
位置3 → [0.3,0,0]
```

其实非常粗糙。

因为我们只是把：

```text
位置编号
```

简单塞进一个维度里。

真实 Transformer 并不是这么做的。

真实的位置编码使用：

> 整个高维向量共同表示一个位置。

例如：

```text
位置1：

[0.84,0.54,0.10,0.99,0.01,0.999,...]
```

```text
位置2：

[0.91,-0.42,0.20,0.98,0.02,0.999,...]
```

```text
位置3：

[0.14,-0.99,0.30,0.95,0.03,0.999,...]
```

所以：

```text
位置1
```

不是：

```text
0.1
```

而是：

```text
一整个高维向量 P1
```

---

<a id="origin-17068"></a>
## 308. 为什么要用整个向量表示位置？

因为模型的 hidden state 本身就是高维的。

例如：

```text
hidden size = 4096
```

那么：

```math
X_i\in R^{4096}
```

为了相加：

```math
H_i=X_i+P_i
```

位置编码也必须是：

```math
P_i\in R^{4096}
```

所以每一个位置实际上都有：

```text
4096 个位置相关数值
```

共同描述当前位置。

---

<a id="origin-17106"></a>
## 309. 那这 4096 个维度分别是什么意思？

这里非常重要：

> 一般不能简单地给每个维度赋予一个人类可解释的含义。

不能说：

```text
第1维 = 位置
第2维 = 距离
第3维 = 前后关系
```

真实神经网络通常不是这么组织信息的。

更加准确的理解是：

```text
很多维度共同组成一种模式
```

就像：

```text
条形码
```

一样。

一个条形码里：

```text
第17根线
```

本身没有必要单独解释。

重要的是：

```text
整个条形码组合起来
```

代表一个唯一的信息。

位置编码也是这样。

---

<a id="origin-17156"></a>
## 310. 原始 Transformer 到底是怎么生成位置编码的？

原始 Transformer 使用的是：

<a id="origin-17160"></a>
## 311. Sinusoidal Position Encoding

公式为：

```math
PE(pos,2i)
=
\sin
\left(
\frac{pos}
{10000^{2i/d}}
\right)
```

```math
PE(pos,2i+1)
=
\cos
\left(
\frac{pos}
{10000^{2i/d}}
\right)
```

其中：

```text
pos
```

表示：

```text
token 的绝对位置
```

例如：

```text
0
1
2
3
4
...
```

而：

```text
i
```

表示：

```text
不同的维度组。
```

---

<a id="origin-17221"></a>
## 312. 最直观的理解：不同维度就是不同速度的钟

这是理解 Sinusoidal Position Encoding 最容易的方法。

假设只用 6 维。

可以理解成有三只钟：

```text
第1、2维
→ 快钟

第3、4维
→ 中速钟

第5、6维
→ 慢钟
```

每只钟都随着：

```text
位置增加
```

不断旋转。

---

<a id="origin-17250"></a>
## 313. 为什么一对维度要用 sin 和 cos？

因为：

```text
sin
cos
```

共同可以表示一个二维圆上的位置。

例如一个角度：

```math
\theta
```

可以表示成：

```math
[\sin\theta,\cos\theta]
```

例如：

```text
位置1
↓
角度 θ1
↓
[sin θ1, cos θ1]
```

位置2：

```text
位置2
↓
角度 θ2
↓
[sin θ2, cos θ2]
```

于是：

```text
每个位置
```

都会对应圆上的一个不同方向。

---

<a id="origin-17303"></a>
## 314. 为什么还要有很多不同频率？

如果只有一只钟，会发生一个严重问题：

> 钟会转一圈。

例如：

```text
位置1
```

可能是：

```text
30°
```

过了一整圈之后：

```text
位置13
```

也可能重新来到：

```text
30°
```

那么仅靠这一只钟：

```text
位置1
```

和：

```text
位置13
```

就分不出来了。

怎么办？

再加入很多不同速度的钟。

例如：

```text
快钟：
已经转了一圈

慢钟：
只转了一小点
```

所以虽然快钟一样：

```text
位置1 ≈ 位置13
```

但慢钟不一样。

多个频率一起看，就可以区分。

---

<a id="origin-17373"></a>
## 315. 所以真实位置编码更像“多只不同速度的钟”

例如：

```text
位置 1
```

可能得到：

```text
快钟：某个角度
中钟：某个角度
慢钟：某个角度
```

位置 2：

```text
快钟：转了一些
中钟：转了一点
慢钟：几乎没动
```

位置 100：

```text
快钟：已经转了很多圈
中钟：转了一部分
慢钟：只转了一点
```

最终把这些：

```text
sin
cos
sin
cos
sin
cos
...
```

全部拼起来：

```math
P_{100}
=
[
\sin\theta_1,
\cos\theta_1,
\sin\theta_2,
\cos\theta_2,
...
]
```

形成：

```text
位置100的高维位置指纹。
```

---

<a id="origin-17439"></a>
## 316. 所以现在重新理解 `[0,0.1,0]`

现在可以更加准确地说：

```math
[0,0.1,0]
```

这个例子只是为了说明：

```text
“往 token embedding 中加入位置信息”
```

而不是说明：

```text
Transformer 真的是把 0.1 塞进第二维。
```

如果真的只用：

```text
0.1
0.2
0.3
```

表示位置，

那么它们放：

```text
第一维
第二维
第三维
```

都没有本质区别。

真正的 Transformer 采用的是：

```text
一个完整的高维位置向量
```

而不是：

```text
一个标量 + 某一个特殊维度。
```

---

<a id="origin-17493"></a>
## 317. 为什么这种位置编码叫“绝对位置编码”？

因为它直接输入的是：

```text
当前位置是多少。
```

例如：

```text
token A → 位置3
token B → 位置5
```

模型得到的是：

```math
P_3
```

以及：

```math
P_5
```

也就是：

```text
A 在第3个位置
B 在第5个位置
```

所以这是：

<a id="origin-17529"></a>
## 318. Absolute Position

绝对位置。

---

<a id="origin-17535"></a>
## 319. 但一个关键问题来了

既然传统位置编码给的是：

```text
绝对位置
```

那么模型是不是不知道：

```text
两个 token 相隔多少？
```

不是。

实际上：

**模型完全可以根据两个绝对位置，进一步学习出相对位置。**

---

<a id="origin-17557"></a>
## 320. 最简单的生活例子

假设告诉你：

```text
小明住 8 楼
小红住 11 楼
```

这里给你的都是：

```text
绝对位置
```

分别是：

```text
8
11
```

但是你马上可以算出：

```math
11-8=3
```

于是得到：

```text
小红比小明高3层。
```

这个：

```text
3
```

就是：

```text
相对位置。
```

所以：

```text
有绝对位置
```

并不代表：

```text
不知道相对位置。
```

而是：

```text
绝对位置
↓
比较
↓
得到相对位置
```

---

<a id="origin-17627"></a>
## 321. Transformer 里面怎么实现这种“比较”？

假设两个 token 在：

```text
位置 i
位置 j
```

加入位置编码以后：

```math
H_i=X_i+P_i
```

```math
H_j=X_j+P_j
```

然后生成：

```math
Q_i=H_iW_Q
```

```math
K_j=H_jW_K
```

Attention Score：

```math
S_{ij}=Q_iK_j^T
```

代进去：

```math
S_{ij}
=
(X_i+P_i)W_Q
\left(
(X_j+P_j)W_K
\right)^T
```

展开以后会包含：

```math
P_iW_QW_K^TP_j^T
```

也就是说：

> 两个位置编码之间确实会发生交互。

所以模型可以逐渐学习：

```text
位置 i
和
位置 j
```

之间是什么关系。

例如：

```text
j=i+1
```

可能意味着：

```text
下一个 token
```

```text
j=i-1
```

可能意味着：

```text
前一个 token
```

```text
|i-j| 很小
```

可能意味着：

```text
两个 token 距离很近。
```

---

<a id="origin-17727"></a>
## 322. Sin/Cos 为什么特别适合学习相对位置？

因为三角函数有一个非常重要的性质：

```math
\cos(a-b)
=
\cos a\cos b
+
\sin a\sin b
```

假设：

```text
位置 i
```

对应角度：

```math
\theta_i
```

位置 j：

```math
\theta_j
```

那么两个位置的 sin/cos 进行组合时：

```math
\sin\theta_i
```

```math
\cos\theta_i
```

和：

```math
\sin\theta_j
```

```math
\cos\theta_j
```

可以产生：

```math
\cos(\theta_i-\theta_j)
```

注意这里出现的是：

```math
\theta_i-\theta_j
```

也就是：

> 两个位置之间的差。

---

<a id="origin-17795"></a>
## 323. 这意味着什么？

虽然传统 Sinusoidal Position Encoding 输入的是：

```text
绝对位置 i
```

和：

```text
绝对位置 j
```

但它们之间发生数学运算以后，很容易得到：

```text
i-j
```

相关的信息。

所以：

```text
绝对位置
```

可以进一步产生：

```text
相对位置关系。
```

---

<a id="origin-17831"></a>
## 324. 一个具体例子

假设有：

```text
位置100
位置101
```

从绝对位置看：

```text
100
101
```

数值都很大。

但是对于语言而言，真正重要的往往是：

```math
101-100=1
```

也就是说：

```text
它们是相邻 token。
```

Sin/Cos 的结构，使模型比较容易从：

```text
P100
P101
```

中学习：

```text
距离 = 1
```

这样的关系。

---

<a id="origin-17878"></a>
## 325. 所以“绝对位置编码”到底是什么意思？

这里一定要区分：

<a id="origin-17882"></a>
### 325.1 编码进去的东西

传统位置编码直接提供：

```text
“我在第几个位置”
```

例如：

```text
位置3
位置5
```

这是：

```text
绝对位置。
```

---

<a id="origin-17905"></a>
### 325.2 模型最后学到的东西

模型可以进一步学习：

```text
位置5
相对于
位置3
```

是：

```text
后面2个位置。
```

这就是：

```text
相对位置。
```

所以：

> “绝对位置编码”描述的是输入方式，而不是模型最终只能理解绝对位置。

---

<a id="origin-17933"></a>
## 326. 可以把整个过程理解成

```text
A 在位置3
B 在位置5
        ↓
输入两个绝对位置
        ↓
Attention 中发生交互
        ↓
模型学习：
5 - 3 = 2
        ↓
B 在 A 后面两个位置
```

---

<a id="origin-17951"></a>
## 327. 那 RoPE 为什么还要出现？

既然传统位置编码已经可以学习相对位置，

为什么后来还要 RoPE？

因为传统方法更像：

```text
先告诉模型：

A 在位置3
B 在位置5

        ↓

然后让模型自己学习：

位置5和位置3之间是什么关系
```

也就是：

```text
绝对位置
↓
模型再学习相对关系
```

---

<a id="origin-17982"></a>
## 328. RoPE 的思路更加直接

RoPE 不再简单使用：

```math
X+P
```

而是：

```text
根据 token 的位置
直接旋转 Q 和 K
```

然后：

```math
Q_iK_j^T
```

中会自然出现：

```text
位置差 i-j
```

相关的信息。

所以可以粗略理解为：

```text
传统位置编码：

先告诉模型
“你在哪里”

然后让模型学习
“你们相距多远”
```

而：

```text
RoPE：

直接让 Attention Score
对“你们相距多远”敏感
```

---

<a id="origin-18034"></a>
## 329. 用一句话总结传统位置编码和 RoPE

传统位置编码：

```text
绝对位置
↓
加入 Hidden State
↓
Attention
↓
模型学习相对位置
```

RoPE：

```text
绝对位置
↓
旋转 Q、K
↓
QK^T
↓
天然体现相对位置
```

---

<a id="origin-18062"></a>
## 330. 最终把整个故事串起来

```text
Transformer 的 Attention
本身不知道顺序

        ↓

所以需要 Position Encoding

        ↓

Token Embedding：
“我是谁”

Position Encoding：
“我在哪里”

        ↓

X + P

        ↓

最简单的教学例子可以写：

位置1 → 0.1
位置2 → 0.2
位置3 → 0.3

        ↓

如果只是这么假设：

0.1 放第一维、第二维、第三维
其实都可以

        ↓

因为重点不是
“必须放在哪一维”

而是：

不同位置得到不同表示

        ↓

但真实 Transformer
并不是简单把 0.1 塞进某一维

        ↓

而是：

每一个位置
生成一个完整的高维向量

P1
P2
P3
...

        ↓

原始 Transformer 使用 Sin/Cos

        ↓

不同维度
相当于不同频率的钟

快钟
中钟
慢钟

        ↓

很多不同频率共同组成
一个位置的“指纹”

        ↓

所以：

P1 ≠ P2 ≠ P3

        ↓

这些位置编码提供的是：

绝对位置

“我在第几个位置”

        ↓

但是多个位置
在 Attention 中发生交互

        ↓

模型可以进一步学习：

i 和 j 的关系

        ↓

例如：

j - i = 1

表示：

两个 token 相邻

        ↓

所以：

传统位置编码
虽然显式编码绝对位置

但模型可以从中
学习出相对位置关系

        ↓

而 RoPE 更进一步：

直接把相对位置关系
体现在 Q、K 的几何关系中
```

---

<a id="origin-18198"></a>
## 331. 最核心的几个结论

<a id="origin-18200"></a>
### 331.1 结论一

```math
[0,0.1,0]
```

只是教学示例。

它不是 Transformer 真实的位置编码。

---

<a id="origin-18212"></a>
### 331.2 结论二

如果真的规定：

```text
位置1 → 0.1
位置2 → 0.2
```

那么：

```text
把 0.1 放第一维
第二维
第三维
```

理论上都可以。

并不存在：

```text
“为什么一定放第二维”
```

的问题。

---

<a id="origin-18241"></a>
### 331.3 结论三

真实 Transformer 不会把位置简单塞进某一个维度。

而是：

```text
整个高维向量
```

共同表示一个位置。

---

<a id="origin-18255"></a>
### 331.4 结论四

Sinusoidal Position Encoding 可以理解成：

```text
很多不同速度的钟
```

一起记录当前位置。

---

<a id="origin-18267"></a>
### 331.5 结论五

传统位置编码显式提供的是：

```text
绝对位置
```

但是模型可以通过 Attention 中的位置交互学习：

```text
相对位置。
```

---

<a id="origin-18283"></a>
### 331.6 结论六

最准确的一句话是：

> **传统位置编码告诉模型“我在哪里”；模型再根据不同 token 的位置表示，学习“我们之间相距多远”。**

而 RoPE 则进一步把：

> **“我们之间相距多远”直接融入 Q、K 的 Attention 计算中。**
