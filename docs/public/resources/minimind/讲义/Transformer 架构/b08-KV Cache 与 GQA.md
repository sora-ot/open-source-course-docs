# KV Cache 与 GQA


<a id="origin-3"></a>
## 1. 一句话理解 KV Cache

在大模型自回归生成过程中：

> **KV Cache = 把历史 token 已经计算好的 Key 和 Value 保存起来，后续生成新 token 时直接复用，避免重复计算。**

注意：

> **缓存的是 K 和 V，不是 Q。**

---

<a id="origin-15"></a>
## 2. 先回忆 Self-Attention

假设输入：

```text
I love AI
```

输入表示记作：

```math
X
```

经过三个线性映射：

```math
Q = XW_Q
```

```math
K = XW_K
```

```math
V = XW_V
```

Attention 为：

```math
\mathrm{Attention}(Q,K,V)
=
\mathrm{softmax}
\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
```

对于 Decoder-only 模型，因为存在 Causal Mask：

```text
I      只能看 I
love   可以看 I, love
AI     可以看 I, love, AI
```

对应注意力范围：

```text
              K_I   K_love   K_AI
Q_I            ✓
Q_love         ✓       ✓
Q_AI           ✓       ✓       ✓
```

---

<a id="origin-73"></a>
## 3. 什么叫自回归生成？

假设 prompt 是：

```text
I love
```

模型希望继续生成：

```text
I love AI very much
```

大模型不会一次性生成：

```text
AI very much
```

而是逐 token 生成。

例如：

```text
第 1 次：

I love
   ↓
AI
```

然后：

```text
第 2 次：

I love AI
      ↓
very
```

然后：

```text
第 3 次：

I love AI very
           ↓
much
```

从数学上看：

```math
x_1,x_2
\rightarrow x_3
```

接着：

```math
x_1,x_2,x_3
\rightarrow x_4
```

再接着：

```math
x_1,x_2,x_3,x_4
\rightarrow x_5
```

这就是 **Autoregressive Generation，自回归生成**。

---
<a id="origin-149"></a>
## 4. 自回归生成：每一轮到底送什么进 Transformer？

假设初始 Prompt 是：

```text
I love
```

模型会一个 Token 一个 Token 地向后生成。

---

<a id="origin-161"></a>
### 4.1 第 1 轮 (第1次推理)

当前完整序列：

```text
I love
```

把整个序列送入 Transformer：

```text
I love
  ↓
Tokenizer
  ↓
[token_I, token_love]
  ↓
Embedding
  ↓
送入 Transformer
  ↓
得到最后一个位置的 hidden state
  ↓
LM Head
  ↓
预测下一个 Token
  ↓
AI
```

所以：

```text
送入 Transformer：
I love

Transformer 输出用于预测：
AI
```

---

<a id="origin-203"></a>
### 4.2 第 2 轮 (第2次推理)

上一轮生成了：

```text
AI
```

把它追加到原序列：

```text
I love AI
```

如果暂时不考虑 KV Cache，那么这一轮会把：

```text
I love AI
```

整个序列重新送入 Transformer：

```text
I love AI
    ↓
Embedding
    ↓
送入 Transformer
    ↓
得到最后一个位置 AI 的 hidden state
    ↓
LM Head
    ↓
预测
    ↓
very
```

所以：

```text
送入 Transformer：
I love AI

Transformer 输出用于预测：
very
```

**注意，要把它理解为完全不同的一次推理案例，跟第一次推理是两个完全独立的案例！！！**

---

<a id="origin-255"></a>
### 4.3 第 3 轮 (第3次推理)

上一轮又生成：

```text
very
```

追加以后：

```text
I love AI very
```

再次送入 Transformer：

```text
I love AI very
      ↓
Embedding
      ↓
送入 Transformer
      ↓
得到最后一个位置 very 的 hidden state
      ↓
LM Head
      ↓
预测
      ↓
much
```

所以：

```text
送入 Transformer：
I love AI very

Transformer 输出用于预测：
much
```

---

<a id="origin-299"></a>
## 5. 整个自回归过程

```text
第 1 轮：

送入 Transformer：
I love

        ↓

预测：
AI
```

```text
第 2 轮：

把 AI 追加进去

I love AI

        ↓

送入 Transformer：
I love AI

        ↓

预测：
very
```

```text
第 3 轮：

把 very 追加进去

I love AI very

        ↓

送入 Transformer：
I love AI very

        ↓

预测：
much
```

所以最基本的自回归生成过程是：

```text
I love
↓
送入 Transformer
↓
生成 AI

I love AI
↓
送入 Transformer
↓
生成 very

I love AI very
↓
送入 Transformer
↓
生成 much

I love AI very much
↓
送入 Transformer
↓
继续生成...
```

核心就是：

$$
\boxed{
\text{生成一个新 Token}
\rightarrow
\text{追加到原序列}
\rightarrow
\text{新的完整序列再次送入 Transformer}
}
$$

---

<a id="origin-391"></a>
## 6. 从多次推理理解 KV Cache

理解 KV Cache，一个很直观的方式是：

> **把自回归生成看成很多次不同的推理。**

假设最开始输入：

```text
I love
```

模型生成：

```text
AI
```

那么下一次推理时，输入就变成：

```text
I love AI
```

再生成：

```text
very
```

于是第三次推理的输入变成：

```text
I love AI very
```

整个过程是：

```text
第 1 次推理：

输入 Transformer：
I love

↓
预测

AI
```

```text
第 2 次推理：

输入 Transformer：
I love AI

↓
预测

very
```

```text
第 3 次推理：

输入 Transformer：
I love AI very

↓
预测

much
```

**这只是三个独立的推理案例，这三次推理之间没有任何关系！！！**

---

<a id="origin-469"></a>
## 7. 关键问题：这些是不同的推理，但很多计算是一样的


<a id="origin-472"></a>
## 8. 第一次推理：输入 `I love`

假设某一层 Transformer 的输入 hidden state 是：

$$
h_I,\quad h_{\text{love}}
$$

分别计算：

$$
Q_I=h_IW_Q
$$

$$
K_I=h_IW_K,\qquad V_I=h_IW_V
$$

以及：

$$
Q_{\text{love}}=h_{\text{love}}W_Q
$$

$$
K_{\text{love}}=h_{\text{love}}W_K
$$

$$
V_{\text{love}}=h_{\text{love}}W_V
$$

于是：

$$
Q=
\begin{bmatrix}
Q_I\\
Q_{\text{love}}
\end{bmatrix}
$$

$$
K=
\begin{bmatrix}
K_I\\
K_{\text{love}}
\end{bmatrix}
$$

---

<a id="origin-524"></a>
## 9. 第一次推理的 Attention Score 矩阵

先计算：

$$
S=\frac{QK^T}{\sqrt{d_k}}
$$

暂时忽略：

$$
\frac{1}{\sqrt{d_k}}
$$

那么矩阵就是：

$$
S^{(1)}
=
\begin{bmatrix}
Q_IK_I^T & Q_IK_{\text{love}}^T\\
Q_{\text{love}}K_I^T & Q_{\text{love}}K_{\text{love}}^T
\end{bmatrix}
$$

可以把行和列写出来：

| Query \ Key |                      `I` |                               `love` |
| ----------- | -----------------------: | -----------------------------------: |
| `I`         |             \(Q_IK_I^T\) |             \(Q_IK_{\text{love}}^T\) |
| `love`      | \(Q_{\text{love}}K_I^T\) | \(Q_{\text{love}}K_{\text{love}}^T\) |

但是 Decoder 使用 Causal Mask。

因此：

```text
            Key
          I       love

Query I    ✓        ×
      love ✓        ✓
```

所以 Mask 之后：

$$
S^{(1)}_{\text{mask}}
=
\begin{bmatrix}
Q_IK_I^T
&
-\infty
\\
Q_{\text{love}}K_I^T
&
Q_{\text{love}}K_{\text{love}}^T
\end{bmatrix}
$$

也就是说：

* `I` 只能看 `I`
* `love` 可以看 `I love`

---

<a id="origin-591"></a>
## 10. 第一次推理真正重要的是最后一行

因为现在我们的目标是：

```text
I love
↓
预测 AI
```

所以真正用来预测下一个 token 的，是最后一个位置 `love` 的输出。

也就是这一行：

$$
\boxed{
[
Q_{\text{love}}K_I^T,\;
Q_{\text{love}}K_{\text{love}}^T
]
}
$$

Softmax 后：

$$
[
\alpha_I,\alpha_{\text{love}}
]
$$

然后：

$$
O_{\text{love}}
=
\alpha_I V_I
+
\alpha_{\text{love}}V_{\text{love}}
$$


如假设 `love` 这个位置经过 Attention Score 和 Softmax 以后，得到：

$$
\alpha_I=0.3
$$

$$
\alpha_{\text{love}}=0.7
$$

表示：

```text
love 这个位置：

30% 关注 I
70% 关注 love
```


那么 `love` 位置最终的 Attention 输出为：

$$
O_{\text{love}}
=
0.3
V_{\text{I}}
+
0.7
V_{\text{love}}
$$



继续经过后面的 Transformer 层以及 LM Head：

```text
O_love
↓
...
↓
LM Head
↓
logits
↓
AI
```

于是模型生成：

```text
AI
```

以上来自Attention公式：

```math
\mathrm{Attention}(Q,K,V)
=
\mathrm{softmax}
\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
```

---

<a id="origin-700"></a>
## 11. 开始第二次推理

现在把刚刚生成的：

```text
AI
```

加入序列。

所以新的完整输入是：

```text
I love AI
```

注意：

> **这是一次新的 Transformer 推理。**

如果完全不使用 KV Cache，那么就把：

```text
I love AI
```

三个 token 全部重新计算一遍。

---

<a id="origin-730"></a>
## 12. 第二次推理重新计算 Q/K/V

三个位置：

```text
I
love
AI
```

分别得到：

$$
Q_I,K_I,V_I
$$

$$
Q_{\text{love}},K_{\text{love}},V_{\text{love}}
$$

$$
Q_{\text{AI}},K_{\text{AI}},V_{\text{AI}}
$$

所以：

$$
Q=
\begin{bmatrix}
Q_I\\
Q_{\text{love}}\\
Q_{\text{AI}}
\end{bmatrix}
$$

$$
K=
\begin{bmatrix}
K_I\\
K_{\text{love}}\\
K_{\text{AI}}
\end{bmatrix}
$$

---

<a id="origin-776"></a>
## 13. 第二次推理的 Attention 矩阵

完整的 Attention Score 是：

$$
S^{(2)}
=
\begin{bmatrix}
Q_IK_I^T
&
Q_IK_{\text{love}}^T
&
Q_IK_{\text{AI}}^T
\\
Q_{\text{love}}K_I^T
&
Q_{\text{love}}K_{\text{love}}^T
&
Q_{\text{love}}K_{\text{AI}}^T
\\
Q_{\text{AI}}K_I^T
&
Q_{\text{AI}}K_{\text{love}}^T
&
Q_{\text{AI}}K_{\text{AI}}^T
\end{bmatrix}
$$

写成表格：

| Query \ Key |                      `I` |                               `love` |                               `AI` |
| ----------- | -----------------------: | -----------------------------------: | ---------------------------------: |
| `I`         |             \(Q_IK_I^T\) |             \(Q_IK_{\text{love}}^T\) |             \(Q_IK_{\text{AI}}^T\) |
| `love`      | \(Q_{\text{love}}K_I^T\) | \(Q_{\text{love}}K_{\text{love}}^T\) | \(Q_{\text{love}}K_{\text{AI}}^T\) |
| `AI`        |   \(Q_{\text{AI}}K_I^T\) |   \(Q_{\text{AI}}K_{\text{love}}^T\) |   \(Q_{\text{AI}}K_{\text{AI}}^T\) |

---

<a id="origin-814"></a>
## 14. 加上 Causal Mask

因果关系是：

```text
          I    love    AI
I         ✓      ×      ×
love      ✓      ✓      ×
AI        ✓      ✓      ✓
```

所以：

$$
S^{(2)}_{\text{mask}}
=
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
$$

---

<a id="origin-853"></a>
## 15. 对比两次 Attention 矩阵

第一次：

$$
\boxed{
\begin{bmatrix}
Q_IK_I^T
&
-\infty
\\
Q_{\text{love}}K_I^T
&
Q_{\text{love}}K_{\text{love}}^T
\end{bmatrix}
}
$$

第二次：

$$
\boxed{
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
}
$$

仔细观察第二次矩阵的左上角：

$$
\begin{bmatrix}
Q_IK_I^T
&
-\infty
\\
Q_{\text{love}}K_I^T
&
Q_{\text{love}}K_{\text{love}}^T
\end{bmatrix}
$$

它和第一次推理：

$$
\begin{bmatrix}
Q_IK_I^T
&
-\infty
\\
Q_{\text{love}}K_I^T
&
Q_{\text{love}}K_{\text{love}}^T
\end{bmatrix}
$$

**完全一样。**

也就是：

```text
第 1 次：

        I       love
I       老结果
love    老结果   老结果
```

第二次只是扩展成：

```text
第 2 次：

        I       love       AI

I       老结果     ×         ×

love    老结果    老结果      ×

AI      新结果    新结果     新结果
```

所以真正新增的，其实只有：

$$
\boxed{
[
Q_{\text{AI}}K_I^T,\;
Q_{\text{AI}}K_{\text{love}}^T,\;
Q_{\text{AI}}K_{\text{AI}}^T
]
}
$$

也就是 Attention 矩阵**新增加的最后一行**。

---
<a id="origin-966"></a>
## 16. 为什么第二次推理左上角 Attention 矩阵与第一次完全一样？

<a id="origin-968"></a>
## 17. 把 Q 和 K 继续拆开

因为：

$$
Q_I=x_IW_Q
$$

$$
Q_{\text{love}}=x_{\text{love}}W_Q
$$

以及：

$$
K_I=x_IW_K
$$

$$
K_{\text{love}}=x_{\text{love}}W_K
$$

所以第一次推理的 Attention 矩阵实际上是：

$$
\boxed{
\begin{bmatrix}
(x_IW_Q)(x_IW_K)^T
&
-\infty
\\
(x_{\text{love}}W_Q)(x_IW_K)^T
&
(x_{\text{love}}W_Q)(x_{\text{love}}W_K)^T
\end{bmatrix}
}
$$

---

第二次推理左上角的 \(2\times2\) 区域同样是：

$$
\boxed{
\begin{bmatrix}
(x_IW_Q)(x_IW_K)^T
&
-\infty
\\
(x_{\text{love}}W_Q)(x_IW_K)^T
&
(x_{\text{love}}W_Q)(x_{\text{love}}W_K)^T
\end{bmatrix}
}
$$

可以看到：

> **拆开以后，两边连公式都一模一样。**

逐项比较：

$$
\underbrace{(x_IW_Q)(x_IW_K)^T}_{\text{第一次}}
=
\underbrace{(x_IW_Q)(x_IW_K)^T}_{\text{第二次}}
$$

$$
\underbrace{(x_{\text{love}}W_Q)(x_IW_K)^T}_{\text{第一次}}
=
\underbrace{(x_{\text{love}}W_Q)(x_IW_K)^T}_{\text{第二次}}
$$

$$
\underbrace{(x_{\text{love}}W_Q)(x_{\text{love}}W_K)^T}_{\text{第一次}}
=
\underbrace{(x_{\text{love}}W_Q)(x_{\text{love}}W_K)^T}_{\text{第二次}}
$$

---

<a id="origin-1050"></a>
## 18. 为什么会完全一样？

原因只有两个。

<a id="origin-1054"></a>
## 19. \(W_Q\)、\(W_K\) 没有变化

**当前处于模型推理阶段。**

**模型参数已经训练完成，因此：**

$$
W_Q,\quad W_K,\quad W_V
$$

都是固定的。

所以第一次推理和第二次推理：

$$
W_Q^{(1)}=W_Q^{(2)}
$$

$$
W_K^{(1)}=W_K^{(2)}
$$

不会因为新生成了一个 `AI` 就发生变化。

---

<a id="origin-1080"></a>
## 20. 历史位置的 \(x_I\)、\(x_{\text{love}}\) 也没有变化

比较两次推理：

```text
第一次：

I love
```

```text
第二次：

I love AI
```

由于 Causal Mask：

```text
        I    love    AI

I       ✓      ×      ×
love    ✓      ✓      ×
AI      ✓      ✓      ✓
```

`I` 和 `love` 看不到后来加入的 `AI`。

所以：

```text
第一次推理：

I     看到：I
love  看到：I love
```

第二次仍然是：

```text
第二次推理：

I     看到：I
love  看到：I love
```

因此历史位置的 hidden state 不会变化（尤其是第一层的输入为Q_I，两次输入完全相同）：

$$
x_I^{(1)}=x_I^{(2)}
$$

$$
x_{\text{love}}^{(1)}
=
x_{\text{love}}^{(2)}
$$

---

<a id="origin-1140"></a>
## 21. 为什么历史位置的 Hidden State 不会变化？

<a id="origin-1142"></a>
## 22. 第一层：输入本身就完全相同

需要注意：

> **第一层的输入不是 \(Q_I\)，而是 \(x_I\)。**

\(Q_I\) 是由：

$$
Q_I=x_IW_Q
$$

计算出来的。

对于 `I` 来说：

第一次推理：

```text
I love
```

第二次推理：

```text
I love AI
```

`I` 仍然是同一个 token，并且仍然位于同一个位置。

因此它的 Token Embedding 和 Position Encoding 都没有变化。

所以第一层输入满足：

$$
\boxed{
x_I^{(1)}=x_I^{(2)}
}
$$

同理：

$$
\boxed{
x_{\text{love}}^{(1)}
=
x_{\text{love}}^{(2)}
}
$$

---

<a id="origin-1194"></a>
## 23. 模型参数也没有变化

现在处于推理阶段，因此模型参数固定：

$$
W_Q,\quad W_K,\quad W_V
$$

在两次推理之间都不会变化。

所以：

$$
W_Q^{(1)}=W_Q^{(2)}
$$

$$
W_K^{(1)}=W_K^{(2)}
$$

$$
W_V^{(1)}=W_V^{(2)}
$$

---

<a id="origin-1220"></a>
## 24. 因此第一层的 Q/K/V 完全相同

因为：

$$
Q_I=x_IW_Q
$$

所以：

$$
Q_I^{(1)}
=
x_I^{(1)}W_Q
$$

而：

$$
x_I^{(1)}=x_I^{(2)}
$$

因此：

$$
\boxed{
Q_I^{(1)}
=
x_I^{(1)}W_Q
=
x_I^{(2)}W_Q
=
Q_I^{(2)}
}
$$

同理：

$$
\boxed{
K_I^{(1)}
=
x_I^{(1)}W_K
=
x_I^{(2)}W_K
=
K_I^{(2)}
}
$$

以及：

$$
\boxed{
V_I^{(1)}
=
x_I^{(1)}W_V
=
x_I^{(2)}W_V
=
V_I^{(2)}
}
$$

对于 `love` 同样成立：

$$
Q_{\text{love}}^{(1)}
=
Q_{\text{love}}^{(2)}
$$

$$
K_{\text{love}}^{(1)}
=
K_{\text{love}}^{(2)}
$$

$$
V_{\text{love}}^{(1)}
=
V_{\text{love}}^{(2)}
$$

---

<a id="origin-1306"></a>
## 25. 第一层 Attention 结果也完全相同

例如 `love` 位置的 Attention：

第一次：

$$
Q_{\text{love}}K_I^T
$$

和：

$$
Q_{\text{love}}K_{\text{love}}^T
$$

第二次仍然是：

$$
Q_{\text{love}}K_I^T
$$

和：

$$
Q_{\text{love}}K_{\text{love}}^T
$$

因为：

$$
Q_{\text{love}}
$$

没变，

$$
K_I
$$

没变，

$$
K_{\text{love}}
$$

也没变。

所以 Attention Score 完全一样。

经过 Softmax 后的 Attention Weight 也完全一样。

再和同样没有变化的：

$$
V_I,\quad V_{\text{love}}
$$

加权求和，得到的 Attention 输出也完全一样。

因此：

$$
\boxed{
O_{\text{love}}^{(1)}
=
O_{\text{love}}^{(2)}
}
$$

---

<a id="origin-1378"></a>
## 26. 所以第一层输出 Hidden State 也完全相同

第一层后面还会经过：

```text
Attention
↓
Residual
↓
Norm
↓
FFN
↓
Residual
↓
...
```

由于：

* 输入相同
* Attention 输出相同
* 模型参数相同

因此最终得到的第一层输出也相同：

$$
\boxed{
h_I^{(1,1)}
=
h_I^{(1,2)}
}
$$

$$
\boxed{
h_{\text{love}}^{(1,1)}
=
h_{\text{love}}^{(1,2)}
}
$$

也就是说：

> **两次推理中，历史 token 第一层计算结束后的 hidden state 完全相同。**

---

<a id="origin-1426"></a>
## 27. 到第二层，这种“相同”会继续传递

第二层的输入，就是第一层的输出。

既然：

$$
h_I^{(1,1)}
=
h_I^{(1,2)}
$$

那么第二层的输入也相同。

因此第二层再次有：

$$
Q_I^{(2,1)}
=
Q_I^{(2,2)}
$$

$$
K_I^{(2,1)}
=
K_I^{(2,2)}
$$

$$
V_I^{(2,1)}
=
V_I^{(2,2)}
$$

Attention 输出继续相同。

于是第二层输出继续相同。

---

<a id="origin-1466"></a>
## 28. 这种关系会一直传到最后一层

整个过程可以理解成：

```text
第一层输入相同
      ↓
第一层 Q/K/V 相同
      ↓
第一层 Attention 相同
      ↓
第一层输出 Hidden State 相同
      ↓
第二层输入相同
      ↓
第二层 Q/K/V 相同
      ↓
第二层 Attention 相同
      ↓
第二层输出 Hidden State 相同
      ↓
......
      ↓
最后一层结果仍然相同
```

也就是：

$$
\boxed{
\text{第一层输入相同}
\Rightarrow
Q/K/V相同
\Rightarrow
Attention相同
\Rightarrow
Hidden\ State相同
\Rightarrow
\text{下一层输入相同}
}
$$

然后逐层重复：

$$
\boxed{
\text{Layer 1}
\Rightarrow
\text{Layer 2}
\Rightarrow
\text{Layer 3}
\Rightarrow
\cdots
}
$$

---

<a id="origin-1524"></a>
## 29. 为什么新增的 AI 不会破坏这个关系？

根本原因还是 Causal Mask。

第二次推理虽然多了：

```text
AI
```

但对于：

```text
I
love
```

来说，它们都看不到未来的 `AI`。

所以：

```text
I
```

仍然只依赖：

```text
I
```

而：

```text
love
```

仍然只依赖：

```text
I love
```

它们的计算路径和第一次推理完全相同。

因此：

$$
\boxed{
\text{后面新增的 token 不会改变历史 token 的 hidden state}
}
$$

---

<a id="origin-1579"></a>
## 30. 最终结论

第一次：

```text
I love
```

第二次：

```text
I love AI
```

虽然是两次不同的推理，但对于历史 token：

```text
I
love
```

来说：

$$
x\text{ 不变}
$$

模型参数：

$$
W_Q,\quad W_K,\quad W_V
$$

也不变。

因此：

$$
Q/K/V\text{ 不变}
$$

Attention 结果也不变。

于是下一层 hidden state 继续不变。

这种关系会一直传递到 Transformer 的最后一层。

因此：

$$
\boxed{
\text{历史 token 在所有 Transformer 层中的 K/V 都不会变化}
}
$$

这也是为什么 KV Cache 可以：

> **在每一层都缓存历史 token 的 K/V，并在下一次自回归推理中直接复用。**


---

<a id="origin-1641"></a>
## 31. 因此 Q、K、V 也全部一样

因为：

$$
Q_I=x_IW_Q
$$

而：

$$
x_I \text{ 不变},\qquad W_Q \text{ 不变}
$$

所以：

$$
Q_I^{(1)}=Q_I^{(2)}
$$

同理：

$$
Q_{\text{love}}^{(1)}
=
Q_{\text{love}}^{(2)}
$$

以及：

$$
K_I^{(1)}=K_I^{(2)}
$$

$$
K_{\text{love}}^{(1)}
=
K_{\text{love}}^{(2)}
$$

所以最终：

$$
\boxed{
\text{历史 }x\text{ 不变}
+
\text{模型 }W\text{ 不变}
\Rightarrow
\text{历史 }Q/K/V\text{ 都不变}
}
$$

也就意味着：

$$
\boxed{
\text{第二次推理 Attention 矩阵左上角}
=
\text{第一次推理 Attention 矩阵}
}
$$

---

<a id="origin-1705"></a>
## 32. 第二次真正新增的只有最后一行

第二次输入：

```text
I love AI
```

旧的部分：

$$
\begin{bmatrix}
Q_IK_I^T
&
-\infty
\\
Q_{\text{love}}K_I^T
&
Q_{\text{love}}K_{\text{love}}^T
\end{bmatrix}
$$

已经和第一次完全一样。

真正新增的只有：

$$
\boxed{
[
Q_{\text{AI}}K_I^T,\;
Q_{\text{AI}}K_{\text{love}}^T,\;
Q_{\text{AI}}K_{\text{AI}}^T
]
}
$$

展开就是：

$$
\boxed{
[
(x_{\text{AI}}W_Q)(x_IW_K)^T,\;
(x_{\text{AI}}W_Q)(x_{\text{love}}W_K)^T,\;
(x_{\text{AI}}W_Q)(x_{\text{AI}}W_K)^T
]
}
$$

因此从矩阵角度看：

```text
第一次：

        I       love

I       老
love    老       老
```

第二次：

```text
        I       love       AI

I       老        ×         ×
love    老        老        ×
AI      新        新        新
```

> **第二次推理只是给第一次的 Attention 矩阵新增了一行真正需要计算的内容。**

而历史 token 的：

$$
K_I,\quad K_{\text{love}}
$$

以及对应的：

$$
V_I,\quad V_{\text{love}}
$$

都没有变化，因此可以直接缓存并复用。

这就是 KV Cache 能成立的数学原因。

<a id="origin-1792"></a>
## 33. 所以第二次推理真正需要计算什么？

没有 KV Cache：

```text
输入：

I love AI

↓

重新计算：

I     的 Q/K/V
love  的 Q/K/V
AI    的 Q/K/V

↓

重新计算整个 Attention 矩阵
```

但是我们刚刚已经证明：

```text
I
love
```

对应的大量结果跟第一次完全一样。

所以有 KV Cache 后：

```text
第一次已经保存：

K_I       V_I
K_love    V_love
```

第二次只计算新 token：

```text
AI
↓
Q_AI
K_AI
V_AI
```

然后直接：

$$
Q_{\text{AI}}
$$

和：

$$
[
K_I,K_{\text{love}},K_{\text{AI}}
]
$$

进行计算：

$$
\boxed{
[
Q_{\text{AI}}K_I^T,\;
Q_{\text{AI}}K_{\text{love}}^T,\;
Q_{\text{AI}}K_{\text{AI}}^T
]
}
$$

注意：

> **有 KV Cache 以后，第二轮甚至没必要把完整的 \(3\times3\) Attention 矩阵重新算出来。**

只需要计算：

```text
             Key
        I    love    AI

AI      ✓     ✓      ✓
↑
只有这一行
```

---

<a id="origin-1885"></a>
## 34. 第三次推理也是一样

第二次生成：

```text
very
```

于是第三次逻辑输入：

```text
I love AI very
```

如果没有 KV Cache，需要算：

$$
4\times4
$$

Attention：

$$
\begin{bmatrix}
* & -\infty & -\infty & -\infty\\
* & * & -\infty & -\infty\\
* & * & * & -\infty\\
* & * & * & *
\end{bmatrix}
$$

其中前三行其实之前已经计算过：

```text
I      → 老的
love   → 老的
AI     → 老的
```

真正新增的只有最后一行：

$$
\boxed{
[
Q_{\text{very}}K_I^T,\;
Q_{\text{very}}K_{\text{love}}^T,\;
Q_{\text{very}}K_{\text{AI}}^T,\;
Q_{\text{very}}K_{\text{very}}^T
]
}
$$

所以：

```text
           I     love     AI     very

I          老      ×       ×       ×
love       老      老      ×       ×
AI         老      老      老      ×
very       新      新      新      新
```

KV Cache 就让我们：

> **不要再计算上面的“老区域”，只计算新增加的最后一行。**

---

<a id="origin-1954"></a>
## 35. 这就是 KV Cache 最核心的本质

自回归生成可以看成：

```text
第 1 次推理：

I love
```

然后：

```text
第 2 次推理：

I love AI
```

然后：

```text
第 3 次推理：

I love AI very
```

它们的 Attention 矩阵分别是：

```text
2 × 2

↓

3 × 3

↓

4 × 4

↓

5 × 5
```

但每次增加一个 token 后：

> **旧矩阵的左上角区域其实完全没有变化。**

真正新增加的只有：

> **Attention 矩阵最下面的一行。**

因此：

$$
\boxed{
KV\ Cache
=
保存历史 token 的 K/V
}
$$

下一轮只需要：

$$
\boxed{
Q_{\text{new}}
\times
K_{\text{history+new}}^T
}
$$

即：

$$
\boxed{
\text{只计算 Attention 矩阵新增加的最后一行}
}
$$

而不需要重新计算整个矩阵。

---

<a id="origin-2038"></a>
## 36. 为什么缓存的是 K、V，而不是 Q？

还是看这个例子。

第一次推理输入：

```text
I love
```

第二次推理输入：

```text
I love AI
```

第二次推理相比第一次，Attention 矩阵真正新增的只有最后一行：

$$
\boxed{
[
Q_{\text{AI}}K_I^T,\;
Q_{\text{AI}}K_{\text{love}}^T,\;
Q_{\text{AI}}K_{\text{AI}}^T
]
}
$$

注意这里用到了：

```text
当前 token 的 Q：

Q_AI
```

以及：

```text
历史 token 的 K：

K_I
K_love
```

**但是完全没有用到：**

```text
Q_I
Q_love
```

---

<a id="origin-2092"></a>
### 36.1 新增这一行到底在做什么？

本质上是在问：

> `AI` 这个新位置，应该关注前面的哪些 token？

所以必须使用当前 token 的：

$$
Q_{\text{AI}}
$$

去查询历史 token 的：

$$
K_I,\quad K_{\text{love}}
$$

也就是：

$$
Q_{\text{AI}}K_I^T
$$

$$
Q_{\text{AI}}K_{\text{love}}^T
$$

得到 Attention 权重以后，还需要取出对应的 Value：

$$
V_I,\quad V_{\text{love}}
$$

例如：

$$
O_{\text{AI}}
=
\alpha_I V_I
+
\alpha_{\text{love}}V_{\text{love}}
+
\alpha_{\text{AI}}V_{\text{AI}}
$$

所以第二次推理真正需要历史保存的是：

$$
\boxed{
K_I,\;K_{\text{love}}
}
$$

和：

$$
\boxed{
V_I,\;V_{\text{love}}
}
$$

---

<a id="origin-2156"></a>
### 36.2 为什么历史 Q 没有用？

因为：

$$
Q_I
$$

只负责当初计算：

> `I` 这个位置应该关注谁？

而：

$$
Q_{\text{love}}
$$

只负责当初计算：

> `love` 这个位置应该关注谁？

**对 `love` 而言，第二次推理相比第一次没有新增任何可见信息，因此它的 Attention 计算不会发生变化。**

第二次新增 `AI` 后，我们并不需要重新问：

```text
I 应该关注谁？
love 应该关注谁？
```

我们现在只需要问：

```text
AI 应该关注谁？
```

所以只需要新的：

$$
Q_{\text{AI}}
$$

---

<a id="origin-2201"></a>
### 36.3 对比一下就很清楚

第一次已经算过：

```text
Q_I
↓
查询历史 K
↓
得到 I 的输出
```

以及：

```text
Q_love
↓
查询 K_I、K_love
↓
得到 love 的输出
```

第二次新增 `AI`：

```text
Q_AI
↓
查询 K_I、K_love、K_AI
↓
取 V_I、V_love、V_AI
↓
得到 AI 的输出
```

可以看到：

```text
历史 Q：
Q_I
Q_love
```

第二次完全没有再使用。

但是历史：

```text
K_I
K_love

V_I
V_love
```

却仍然被新的 `Q_AI` 使用。

---

<a id="origin-2259"></a>
### 36.4 再看第三次推理

假设第二次生成：

```text
very
```

第三次输入变成：

```text
I love AI very
```

真正新增的 Attention 行是：

$$
\boxed{
[
Q_{\text{very}}K_I^T,\;
Q_{\text{very}}K_{\text{love}}^T,\;
Q_{\text{very}}K_{\text{AI}}^T,\;
Q_{\text{very}}K_{\text{very}}^T
]
}
$$

然后输出：

$$
O_{\text{very}}
=
\alpha_I V_I
+
\alpha_{\text{love}}V_{\text{love}}
+
\alpha_{\text{AI}}V_{\text{AI}}
+
\alpha_{\text{very}}V_{\text{very}}
$$

还是一样：

```text
当前需要：

Q_very
```

历史需要：

```text
K_I
K_love
K_AI

V_I
V_love
V_AI
```

历史不需要：

```text
Q_I
Q_love
Q_AI
```

---

<a id="origin-2330"></a>
### 36.5 最终结论

每次新增一个 token，真正新增的是 Attention 矩阵的最后一行：

$$
Q_{\text{new}}K_{\text{history}}^T
$$

所以未来推理需要：

```text
当前 token 的 Q
+
历史 token 的 K
+
历史 token 的 V
```

而不需要历史 token 的 Q。

因此：

$$
\boxed{
Q：只在自己那一轮使用一次，不需要缓存
}
$$

$$
\boxed{
K：未来的新 Q 还会继续查询，需要缓存
}
$$

$$
\boxed{
V：Attention 加权求和时还会继续使用，需要缓存
}
$$

一句话记住：

> **新 token 用自己的 Q，去查询过去的 K，再读取过去的 V；它从来不需要过去的 Q。**

---

<a id="origin-2376"></a>
## 37. 从“Attention Score 只新增一行”理解 KV Cache

<a id="origin-2378"></a>
## 38. 先说结论

理解 KV Cache，可以换一个非常直观的角度：

> **自回归生成时，每一轮真正有用的 Attention Score，只有新 token 对所有历史 token 计算出来的“新增一行”。**

以前已经计算过的那些 Attention Score 行，在当前这一轮已经没有用了。

但是：

> **新 token 仍然需要使用历史 token 的 K 和 V。**

所以：

```text
历史 Attention Score：不需要缓存
历史 Q：不需要缓存

历史 K：需要缓存
历史 V：需要缓存
```

这就是所谓的：

```text
KV Cache
```

---

<a id="origin-2408"></a>
## 39. 从第三个 token 开始看

假设当前已经有：

```text
Token 1：I
Token 2：love
```

现在第三个 token：

```text
AI
```

进入模型。

如果按照完整 Attention 的写法，本来可以形成一个完整的 Attention Score：

```text
                K1       K2       K3

Q1              s11

Q2              s21      s22

Q3              s31      s32      s33
```

其中：

```math
s_{ij}=Q_iK_j^T
```

例如第三行：

```math
s_{31}=Q_3K_1^T
```

```math
s_{32}=Q_3K_2^T
```

```math
s_{33}=Q_3K_3^T
```

---

<a id="origin-2459"></a>
## 40. 为什么这一轮只需要第三行？

因为现在是在生成：

```text
第 4 个 token
```

最终真正需要的是第三个位置的 hidden state：

```math
H_3
```

然后：

```math
H_3
\rightarrow
LM\ Head
\rightarrow
Softmax
\rightarrow
P(x_4)
```

也就是说：

```text
H1：用于以前的预测
H2：用于以前的预测
H3：用于现在预测第4个token
```

当前这一轮只关心：

```math
H_3
```

而要得到：

```math
H_3
```

这一层中只需要计算：

```math
O_3
```

---

<a id="origin-2513"></a>
## 41. O3 只依赖 Attention Score 的第三行

第三行 Attention Score 是：

```math
[
Q_3K_1^T,
Q_3K_2^T,
Q_3K_3^T
]
```

例如：

```math
[2,1,3]
```

对这一行单独做 Softmax：

```math
\operatorname{Softmax}([2,1,3])
```

假设得到：

```math
[0.245,0.090,0.665]
```

也就是：

```math
[
\alpha_{31},
\alpha_{32},
\alpha_{33}
]
```

然后：

```math
O_3
=
\alpha_{31}V_1
+
\alpha_{32}V_2
+
\alpha_{33}V_3
```

例如：

```math
O_3
=
0.245V_1
+
0.090V_2
+
0.665V_3
```

因此，为了计算第三个 token 的输出，只需要：

```text
Q3
K1 K2 K3
V1 V2 V3
```

根本不需要：

```text
Q1K1

Q2K1
Q2K2
```

也就是：

```text
以前 Attention Score 的那些历史行。
```

---

<a id="origin-2602"></a>
## 42. 所以 Attention Score 的“左上角”已经没用了

以前可能计算过：

```text
Q1K1

Q2K1
Q2K2
```

这些值的作用是什么？

它们当时是为了计算：

```text
O1
O2
```

进而得到：

```text
H1
H2
```

但是当前第 3 轮推理的时候：

```text
H1 不需要重新预测
H2 不需要重新预测
```

我们现在只要：

```text
H3
```

所以以前那些 Attention Score：

```text
Q1K1

Q2K1
Q2K2
```

当前这一轮已经没有用途。

因此：

> **Attention Score 的历史部分没有必要缓存。**

---

<a id="origin-2659"></a>
## 43. 但是历史 K 还要继续使用

**虽然过去的 Attention Score 没用了，但是新 token 仍然必须和历史 token 建立 Attention。因此不能说和历史的信息无关。**

第三个 token 需要计算：

```math
Q_3K_1^T
```

```math
Q_3K_2^T
```

```math
Q_3K_3^T
```

因此：

```text
K1
K2
```

仍然需要。

而 K 来自：

```math
K_i=H_iW_K
```

如果没有缓存，那么第三轮就必须重新计算：

```math
K_1=H_1W_K
```

```math
K_2=H_2W_K
```

但：

```text
K1、K2 与上一轮完全一样
```

所以重新计算纯粹是浪费。

于是直接把：

```text
K1
K2
```

缓存下来。

第三轮只新增：

```text
K3
```

于是：

```text
KV Cache 中的 K：

K1
K2
K3
```

---

<a id="origin-2737"></a>
## 44. 为什么历史 V 也需要缓存？

Attention 的过程并不是算完：

```math
QK^T
```

就结束了。

Softmax 得到权重以后，还需要：

```math
O_3
=
\alpha_{31}V_1
+
\alpha_{32}V_2
+
\alpha_{33}V_3
```

因此第三个 token 仍然需要：

```text
V1
V2
V3
```

而：

```math
V_i=H_iW_V
```

如果没有缓存，那么同样需要重新计算：

```math
V_1=H_1W_V
```

```math
V_2=H_2W_V
```

这些结果也没有发生变化。

所以同样提前存起来。

第三轮只新增：

```text
V3
```

于是：

```text
KV Cache 中的 V：

V1
V2
V3
```

---

<a id="origin-2805"></a>
## 45. 为什么不缓存 Q？

因为历史 Q 以后不会再使用。

例如：

```math
Q_2
```

的作用，是第二个 token 当时计算：

```math
Q_2K_1^T
```

```math
Q_2K_2^T
```

也就是回答：

> 第二个 token 应该关注谁？

这个问题在第二轮已经解决完了。

第三轮需要回答的是：

> 第三个 token 应该关注谁？

所以需要的是：

```math
Q_3
```

而不是：

```math
Q_1,Q_2
```

因此：

```text
历史 Q 没有必要缓存。
```

---

<a id="origin-2855"></a>
## 46. 为什么不缓存历史 Attention Score？

同样的道理。

历史 Attention Score，例如：

```math
Q_2K_1^T
```

表示的是：

> 第 2 个 token 当时对第 1 个 token 的关注程度。

但是现在第 3 个 token 进来，需要的是：

```math
Q_3K_1^T
```

这是一个完全新的 Query。

以前的：

```math
Q_2K_1^T
```

并不能帮助我们计算：

```math
Q_3K_1^T
```

所以：

```text
历史 Attention Score
```

未来不会再次使用。

没有必要缓存。

---

<a id="origin-2901"></a>
## 47. 所以第三轮真正发生的事情

假设前两轮已经缓存：

```text
K1 K2

V1 V2
```

第三个 token 进入：

```text
Token 3
```

先得到：

```math
H_3
```

然后投影：

```math
Q_3=H_3W_Q
```

```math
K_3=H_3W_K
```

```math
V_3=H_3W_V
```

此时：

```text
历史 Cache：

K1 K2
V1 V2

新计算：

K3
V3
Q3
```

然后只计算：

```math
[
Q_3K_1^T,
Q_3K_2^T,
Q_3K_3^T
]
```

得到：

```text
一条新的 Attention Score 向量
```

而不是重新得到整个：

```text
3 × 3 Attention Score 矩阵
```

---

<a id="origin-2976"></a>
## 48. Softmax 之后继续使用缓存的 V

对：

```math
[
Q_3K_1^T,
Q_3K_2^T,
Q_3K_3^T
]
```

进行 Softmax：

```math
[
\alpha_{31},
\alpha_{32},
\alpha_{33}
]
```

然后：

```math
O_3
=
\alpha_{31}V_1
+
\alpha_{32}V_2
+
\alpha_{33}V_3
```

其中：

```text
V1：从 Cache 取
V2：从 Cache 取
V3：当前新算
```

于是得到：

```math
O_3
```

继续经过：

```text
残差连接
↓
Norm
↓
FFN
↓
残差连接
```

得到这一层第三个 token 的新 hidden state。

---

<a id="origin-3040"></a>
## 49. 到下一层继续同样的过程

需要特别注意：

> KV Cache 并不是整个 Transformer 只有一份。

而是：

```text
每一层都有自己独立的 KV Cache。
```

例如 32 层 Transformer：

```text
Layer 1：
K1 K2
V1 V2

Layer 2：
K1 K2
V1 V2

Layer 3：
K1 K2
V1 V2

...

Layer 32：
K1 K2
V1 V2
```

第三个 token 来以后，每一层都只新增：

```text
K3
V3
```

同时只计算当前 token 的一条 Attention。

---

<a id="origin-3085"></a>
## 50. 第四个 token 来的时候也是一样

当第 4 个 token 到来时：

```text
历史已经缓存：

K1 K2 K3
V1 V2 V3
```

只需要新算：

```math
Q_4
```

```math
K_4
```

```math
V_4
```

然后计算：

```math
[
Q_4K_1^T,
Q_4K_2^T,
Q_4K_3^T,
Q_4K_4^T
]
```

得到：

```text
1 × 4
```

的 Attention Score 向量。

然后 Softmax：

```math
[
\alpha_{41},
\alpha_{42},
\alpha_{43},
\alpha_{44}
]
```

再：

```math
O_4
=
\alpha_{41}V_1
+
\alpha_{42}V_2
+
\alpha_{43}V_3
+
\alpha_{44}V_4
```

---

<a id="origin-3156"></a>
## 51. 第五个 token 也是一样

第 5 个 token：

```text
历史 K：

K1 K2 K3 K4
```

新 Query：

```math
Q_5
```

于是只计算：

```math
[
Q_5K_1^T,
Q_5K_2^T,
Q_5K_3^T,
Q_5K_4^T,
Q_5K_5^T
]
```

也就是：

```text
1 × 5
```

因此整个自回归 Decode 的过程其实是：

```text
第3轮：

Q3
 ↓
[K1 K2 K3]
 ↓
1×3 Attention Score


第4轮：

Q4
 ↓
[K1 K2 K3 K4]
 ↓
1×4 Attention Score


第5轮：

Q5
 ↓
[K1 K2 K3 K4 K5]
 ↓
1×5 Attention Score
```

而不是：

```text
第3轮重新算 3×3

第4轮重新算 4×4

第5轮重新算 5×5
```

---

<a id="origin-3232"></a>
## 52. KV Cache 到底缓存什么？

可以总结成下面这张表：

| 内容                 | 是否缓存 | 原因                             |
| ------------------ | ---: | ------------------------------ |
| 历史 Q               |    × | 旧 Query 的任务已经完成                |
| 历史 Attention Score |    × | 只是旧 Query 和旧 Key 的匹配结果，以后不会再使用 |
| 历史 K               |    ✓ | 未来的新 Query 仍然要和历史 K 进行匹配       |
| 历史 V               |    ✓ | 未来的新 token 仍然要从历史 V 中提取信息      |

因此：

```text
为什么叫 KV Cache？

因为真正值得缓存的，
正好就是历史 K 和历史 V。
```

---

<a id="origin-3254"></a>
## 53. 一个非常直观的理解

可以把整个过程想象成：

```text
历史 token 已经留下：

K1    V1
K2    V2
K3    V3
...
```

新的 token 到来以后：

```text
新的 Query
Q_new
```

去问：

```text
我和哪个历史 token 最相关？
```

于是：

```math
Q_{\text{new}}K_1^T
```

```math
Q_{\text{new}}K_2^T
```

```math
Q_{\text{new}}K_3^T
```

得到 Attention 权重。

然后再根据这些权重：

```text
从 V1、V2、V3 中取出信息
```

因此：

```text
K：

负责让新的 Query
判断“应该关注谁”。


V：

负责让新的 token
真正“读取对应的信息”。
```

---

<a id="origin-3319"></a>
## 54. 为什么仅仅缓存 K、V 就能够“记住历史”（重点）？

这里的关键是：

> 新 token 并不需要重新恢复整个过去的 Attention 计算过程。

它只需要能够：

```text
找到历史信息
+
读取历史信息
```

而：

```text
K
```

负责：

```text
找到谁
```

```text
V
```

负责：

```text
读取什么
```

所以：

```text
历史 Attention Score
```

虽然已经被丢掉了，

但是未来 token 仍然可以通过：

```text
新的 Q
+
历史 K
+
历史 V
```

重新访问整个历史上下文。

因此可以说：

> **KV Cache 不是缓存“历史是怎么算出来的”，而是缓存“未来继续访问历史时还需要的历史表示”。**

---

<a id="origin-3381"></a>
## 55. 从“新增一行”的角度总结 KV Cache

自回归生成过程中，每新增一个 token：

```text
过去 Attention Score 的前几行
已经没有用了。
```

这一轮只需要：

```text
新 token 对所有历史 token
产生的一行新的 Attention Score。
```

例如：

```text
第3轮：新增第3行
第4轮：新增第4行
第5轮：新增第5行
```

而这一行需要：

```text
新的 Q
+
所有历史 K
```

Softmax 以后，又需要：

```text
所有历史 V
```

所以：

```text
历史 Attention Score：不用保存
历史 Q：不用保存

历史 K：保存
历史 V：保存
```

最终就得到：

```text
KV Cache
```

---

<a id="origin-3437"></a>
## 56. 最终一句话总结

> **KV Cache 的本质，就是利用“自回归推理每轮只需要新增的一行 Attention”这一特点：历史 Attention Score 和历史 Q 都已经失去作用，而未来的新 Query 仍然需要访问历史 K，并利用对应的历史 V 获取信息，因此只缓存 K 和 V，就可以避免重复计算历史 token，同时保持与完整 Attention 相同的推理结果。**

再压缩一点：

> **旧 Attention Score 已经过期，旧 K/V 仍然有用；每轮只算新 Query 对历史 K 的一行 Attention，再利用历史 V 聚合信息，这就是 KV Cache。**


---

<a id="origin-3448"></a>
## 57. 有 KV Cache 后，完整生成流程是什么？

大模型推理通常可以分成两个阶段：

```text
Prefill
+
Decode
```

---

<a id="origin-3460"></a>
## 58. Prefill 阶段

假设 prompt 是：

```text
I love AI
```

第一次输入时，整个 prompt 一次进入模型：

```text
I   love   AI
```

模型计算：

```text
Q_I
Q_love
Q_AI
```

```text
K_I
K_love
K_AI
```

```text
V_I
V_love
V_AI
```

其中：

```text
K_I
K_love
K_AI
```

和：

```text
V_I
V_love
V_AI
```

会被保存起来。

因此 KV Cache 变成：

```text
K Cache:

[K_I, K_love, K_AI]
```

```text
V Cache:

[V_I, V_love, V_AI]
```

与此同时，模型根据最后一个位置的 hidden state，预测出下一个 token：

```text
very
```

这一整个处理 prompt 的阶段叫：

```text
Prefill
```

---

<a id="origin-3540"></a>
## 59. Decode 阶段

现在模型已经生成：

```text
very
```

下一步要继续预测。

如果有 KV Cache，就不需要重新输入：

```text
I love AI very
```

而是只需要处理新 token：

```text
very
```

计算：

```math
Q_{\text{very}}
```

```math
K_{\text{very}}
```

```math
V_{\text{very}}
```

然后把新的 K/V 加到 Cache 中。

---

<a id="origin-3580"></a>
### 59.1 更新 K Cache

之前：

```text
[K_I, K_love, K_AI]
```

现在：

```text
[K_I, K_love, K_AI, K_very]
```

数学表示：

```math
K_{\text{all}}
=
[
K_I,
K_{\text{love}},
K_{\text{AI}},
K_{\text{very}}
]
```

---

<a id="origin-3609"></a>
### 59.2 更新 V Cache

之前：

```text
[V_I, V_love, V_AI]
```

现在：

```text
[V_I, V_love, V_AI, V_very]
```

数学表示：

```math
V_{\text{all}}
=
[
V_I,
V_{\text{love}},
V_{\text{AI}},
V_{\text{very}}
]
```

---

<a id="origin-3638"></a>
### 59.3 当前 Attention

只需要当前 Query：

```math
Q_{\text{very}}
```

然后：

```math
\mathrm{Attention}_{\text{very}}
=
\mathrm{softmax}
\left(
\frac{
Q_{\text{very}}
K_{\text{all}}^T
}{
\sqrt{d_k}
}
\right)
V_{\text{all}}
```

注意：

这里完全不需要重新计算：

```text
Q_I
Q_love
Q_AI
```

也不需要重新计算历史：

```text
K_I
K_love
K_AI
```

以及：

```text
V_I
V_love
V_AI
```

---

<a id="origin-3691"></a>
## 60. 最容易理解错的一点

有 KV Cache 后：

> **不是说模型只看当前 token。**

真正的意思是：

> **模型只重新计算当前 token，但当前 token 仍然可以看到全部历史上下文。**

例如已经有：

```text
I love artificial intelligence because it
```

现在模型只需要新计算：

```text
it
```

但：

```math
Q_{\text{it}}
```

仍然会与所有历史 Key 做匹配：

```text
K_I

K_love

K_artificial

K_intelligence

K_because

K_it
```

所以模型仍然拥有完整上下文。

---

<a id="origin-3739"></a>
## 61. 一个具体矩阵例子

为了简单，假设：

```math
d_k = 2
```

已经有三个历史 token：

```text
I
love
AI
```

它们对应的 K Cache：

```math
K_{\text{cache}}
=
\begin{bmatrix}
1 & 0 \\
0 & 1 \\
1 & 1
\end{bmatrix}
```

V Cache：

```math
V_{\text{cache}}
=
\begin{bmatrix}
1 & 2 \\
3 & 4 \\
5 & 6
\end{bmatrix}
```

现在新来了：

```text
very
```

它计算得到：

```math
Q_{\text{very}}
=
\begin{bmatrix}
0.5 & 1
\end{bmatrix}
```

以及：

```math
K_{\text{very}}
=
\begin{bmatrix}
0.2 & 0.8
\end{bmatrix}
```

```math
V_{\text{very}}
=
\begin{bmatrix}
7 & 8
\end{bmatrix}
```

于是新的 K：

```math
K
=
\begin{bmatrix}
1 & 0 \\
0 & 1 \\
1 & 1 \\
0.2 & 0.8
\end{bmatrix}
```

新的 V：

```math
V
=
\begin{bmatrix}
1 & 2 \\
3 & 4 \\
5 & 6 \\
7 & 8
\end{bmatrix}
```

现在只计算：

```math
Q_{\text{very}}K^T
```

尺寸为：

```math
[1\times2]
\times
[2\times4]
```

得到：

```math
[1\times4]
```

这四个数分别表示：

```text
very 对 I 的 Attention Score

very 对 love 的 Attention Score

very 对 AI 的 Attention Score

very 对 very 自己的 Attention Score
```

注意：

这一轮完全不需要：

```text
Q_I
Q_love
Q_AI
```

---

<a id="origin-3883"></a>
## 62. 没有 KV Cache 与有 KV Cache 的区别

假设 prompt 已经有：

```text
1000 token
```

接下来再生成 5 个 token。

---

<a id="origin-3895"></a>
### 62.1 没有 KV Cache

第 1 次：

```text
重新计算 1000 token
```

第 2 次：

```text
重新计算 1001 token
```

第 3 次：

```text
重新计算 1002 token
```

第 4 次：

```text
重新计算 1003 token
```

第 5 次：

```text
重新计算 1004 token
```

累计需要重复处理：

```math
1000+1001+1002+1003+1004
```

---

<a id="origin-3935"></a>
### 62.2 有 KV Cache

Prefill 时先处理：

```text
1000 token
```

之后：

```text
第 1 次：只重新计算 1 个 token

第 2 次：只重新计算 1 个 token

第 3 次：只重新计算 1 个 token

第 4 次：只重新计算 1 个 token

第 5 次：只重新计算 1 个 token
```

历史信息直接通过：

```text
KV Cache
```

复用。

---

<a id="origin-3967"></a>
## 63. KV Cache 后 Attention 是否变成 O(1)？

不是。

这是非常重要的一个细节。

假设当前已经有：

```math
t
```

个 token。

虽然当前只重新计算一个 token 的：

```math
Q_t
```

```math
K_t
```

```math
V_t
```

但是：

```math
Q_t
```

仍然要和历史所有 Key：

```math
K_1,K_2,\dots,K_t
```

做匹配。

因此单次 decode 的 Attention 仍然需要大约：

```math
O(t)
```

的工作。

KV Cache 消除的是：

> **历史 token 的重复前向计算。**

但没有消除：

> **当前 token 对全部历史 K/V 的读取和 Attention 计算。**

所以：

```text
上下文越长
↓
每次 decode 仍然越贵
```

---

<a id="origin-4035"></a>
## 64. KV Cache 存在哪里？

不是整个 Transformer 只有一份 KV Cache。

而是：

> **每个 Transformer Layer 都有自己独立的 KV Cache。**

例如模型有 32 层：

```text
Layer 1
├── K Cache
└── V Cache

Layer 2
├── K Cache
└── V Cache

Layer 3
├── K Cache
└── V Cache

...

Layer 32
├── K Cache
└── V Cache
```

原因是每一层都有自己的：

```math
W_K^{(l)}
```

以及：

```math
W_V^{(l)}
```

并且每层输入 hidden state 也不同：

```math
h^{(l)}
```

因此：

```math
K^{(l)}
=
h^{(l)}W_K^{(l)}
```

```math
V^{(l)}
=
h^{(l)}W_V^{(l)}
```

所以每一层的 K/V 都不同，必须独立缓存。


---

<a id="origin-4102"></a>
## 65. 从训练到推理：Causal Mask、Attention 矩阵、Attention 向量与 KV Cache

<a id="origin-4104"></a>
## 66. 先区分两个完全不同的阶段

理解 Transformer 的 Attention 时，一个非常容易混淆的问题是：

> 为什么有时候我们说 Attention 是一个矩阵，有时候推理时又说 Attention 只是一个向量？

原因是：

Transformer 在实际运行时存在两个不同场景：

```text
场景一：训练 / Prompt Prefill

一次输入很多个 token
→ 可以同时计算很多个 Query
→ Attention Score 是矩阵


场景二：Decode 自回归生成

每次只新增一个 token
→ 本轮只有一个新的 Query
→ Attention Score 是向量
```

因此必须分开理解。

---

<a id="origin-4133"></a>
## 67. 训练阶段：一次输入整个序列

假设一次输入 5 个 token：

$$
x_1,x_2,x_3,x_4,x_5
$$

每个 token 都有自己的 hidden state：

$$
h_1,h_2,h_3,h_4,h_5
$$

然后统一计算：

$$
Q=HW_Q
$$

$$
K=HW_K
$$

$$
V=HW_V
$$

因此：

$$
Q=
\begin{bmatrix}
Q_1\\
Q_2\\
Q_3\\
Q_4\\
Q_5
\end{bmatrix}
$$

同理：

$$
K=
\begin{bmatrix}
K_1\\
K_2\\
K_3\\
K_4\\
K_5
\end{bmatrix}
$$

以及：

$$
V=
\begin{bmatrix}
V_1\\
V_2\\
V_3\\
V_4\\
V_5
\end{bmatrix}
$$

---

<a id="origin-4202"></a>
## 68. 训练阶段为什么会产生一个 Attention Score 矩阵？

因为：

$$
S=QK^T
$$

所以：

$$
S=
\begin{bmatrix}
Q_1K_1^T & Q_1K_2^T & Q_1K_3^T & Q_1K_4^T & Q_1K_5^T\\
Q_2K_1^T & Q_2K_2^T & Q_2K_3^T & Q_2K_4^T & Q_2K_5^T\\
Q_3K_1^T & Q_3K_2^T & Q_3K_3^T & Q_3K_4^T & Q_3K_5^T\\
Q_4K_1^T & Q_4K_2^T & Q_4K_3^T & Q_4K_4^T & Q_4K_5^T\\
Q_5K_1^T & Q_5K_2^T & Q_5K_3^T & Q_5K_4^T & Q_5K_5^T
\end{bmatrix}
$$

如果序列长度为：

$$
L=5
$$

那么 Attention Score 矩阵的大小就是：

$$
\boxed{5\times5}
$$

一般来说：

$$
\boxed{L\times L}
$$

---

<a id="origin-4243"></a>
## 69. Attention Score 矩阵的“行”到底是什么意思？

这是理解整个 Transformer 最关键的地方之一。

第 1 行：

$$
[
Q_1K_1^T,
Q_1K_2^T,
\dots,
Q_1K_5^T
]
$$

表示：

> 第 1 个 token 的 Query \(Q_1\)，分别和所有 Key 做匹配。

所以第 1 行负责：

$$
\boxed{\text{计算第1个token应该关注哪些位置}}
$$

---

第 2 行：

$$
[
Q_2K_1^T,
Q_2K_2^T,
\dots,
Q_2K_5^T
]
$$

负责：

$$
\boxed{\text{计算第2个token应该关注哪些位置}}
$$

---

第 3 行：

$$
[
Q_3K_1^T,
Q_3K_2^T,
\dots,
Q_3K_5^T
]
$$

负责：

$$
\boxed{\text{计算第3个token应该关注哪些位置}}
$$

因此：

$$
\boxed{
Attention矩阵第i行
=
第i个token发出的查询
}
$$

---

<a id="origin-4318"></a>
## 70. 但问题来了：第 3 个 token 怎么能看到第 4、5 个 token？

如果直接计算：

$$
QK^T
$$

数学上第 3 行确实会得到：

$$
[
Q_3K_1^T,
Q_3K_2^T,
Q_3K_3^T,
Q_3K_4^T,
Q_3K_5^T
]
$$

也就是说：

> 如果什么都不处理，第 3 个 token 是可以和第 4、5 个 token 匹配的。

但是自回归语言模型不允许：

```text
token3
```

偷看：

```text
token4
token5
```

因为这些是未来信息。

于是就需要：

$$
\boxed{\text{Causal Mask}}
$$

---

<a id="origin-4365"></a>
## 71. Causal Mask 到底是什么？

构造一个 Mask：

$$
M=
\begin{bmatrix}
0&-\infty&-\infty&-\infty&-\infty\\
0&0&-\infty&-\infty&-\infty\\
0&0&0&-\infty&-\infty\\
0&0&0&0&-\infty\\
0&0&0&0&0
\end{bmatrix}
$$

然后计算：

$$
S_{\text{masked}}
=
\frac{QK^T}{\sqrt{d_k}}+M
$$

于是原来的 Attention Score：

$$
\begin{bmatrix}
s_{11}&s_{12}&s_{13}&s_{14}&s_{15}\\
s_{21}&s_{22}&s_{23}&s_{24}&s_{25}\\
s_{31}&s_{32}&s_{33}&s_{34}&s_{35}\\
s_{41}&s_{42}&s_{43}&s_{44}&s_{45}\\
s_{51}&s_{52}&s_{53}&s_{54}&s_{55}
\end{bmatrix}
$$

变成：

$$
\begin{bmatrix}
s_{11}&-\infty&-\infty&-\infty&-\infty\\
s_{21}&s_{22}&-\infty&-\infty&-\infty\\
s_{31}&s_{32}&s_{33}&-\infty&-\infty\\
s_{41}&s_{42}&s_{43}&s_{44}&-\infty\\
s_{51}&s_{52}&s_{53}&s_{54}&s_{55}
\end{bmatrix}
$$

---

<a id="origin-4414"></a>
## 72. Causal Mask 并不是把矩阵缩小

这是一个非常重要的理解。

假设序列长度是：

$$
5
$$

那么整个 Attention Score 仍然是：

$$
\boxed{5\times5}
$$

并不是：

```text
第1个token算1×1

第2个token算2×2

第3个token算3×3

...
```

而是一次统一计算：

$$
\boxed{5\times5}
$$

只是不同位置允许使用的元素不同。

例如：

```text
          K1   K2   K3   K4   K5

Q1        ✓    ×    ×    ×    ×

Q2        ✓    ✓    ×    ×    ×

Q3        ✓    ✓    ✓    ×    ×

Q4        ✓    ✓    ✓    ✓    ×

Q5        ✓    ✓    ✓    ✓    ✓
```

这就是经典的下三角结构。

---

<a id="origin-4470"></a>
## 73. 以第 3 个 token 为例

虽然整个序列长度是：

$$
5
$$

所以第 3 行最开始仍然是一个长度为 5 的向量：

$$
[
Q_3K_1^T,
Q_3K_2^T,
Q_3K_3^T,
Q_3K_4^T,
Q_3K_5^T
]
$$

加入 Causal Mask 之后：

$$
[
Q_3K_1^T,
Q_3K_2^T,
Q_3K_3^T,
-\infty,
-\infty
]
$$

然后做 Softmax：

$$
\operatorname{softmax}
(
[
s_{31},
s_{32},
s_{33},
-\infty,
-\infty
]
)
$$

得到：

$$
[
\alpha_{31},
\alpha_{32},
\alpha_{33},
0,
0
]
$$

所以可以直观理解为：

> Causal Mask 强制让未来位置在 Softmax 后的 Attention 权重变成 0。

---

<a id="origin-4535"></a>
## 74. 为什么加 \(-\infty\) 就会变成 0？

Softmax：

$$
\operatorname{softmax}(z_i)
=
\frac{e^{z_i}}
{\sum_j e^{z_j}}
$$

如果：

$$
z_i=-\infty
$$

那么：

$$
e^{-\infty}=0
$$

所以：

$$
\operatorname{softmax}(-\infty)=0
$$

因此未来位置不会对最终输出产生任何贡献。

所以更严格地说：

> 不是 Softmax 算完之后强行把未来位置改成 0。

而是：

> **Softmax 之前把未来位置对应的 score 设成 \(-\infty\)，因此 Softmax 后自然得到 0。**

---

<a id="origin-4576"></a>
## 75. 第 3 个 token 最后到底使用了哪些 Value？

第 3 行 Softmax 后：

$$
[
\alpha_{31},
\alpha_{32},
\alpha_{33},
0,
0
]
$$

再乘：

$$
V=
\begin{bmatrix}
V_1\\
V_2\\
V_3\\
V_4\\
V_5
\end{bmatrix}
$$

于是：

$$
O_3
=
\alpha_{31}V_1+
\alpha_{32}V_2+
\alpha_{33}V_3+
0V_4+
0V_5
$$

也就是：

$$
\boxed{
O_3
=
\alpha_{31}V_1+
\alpha_{32}V_2+
\alpha_{33}V_3
}
$$

因此虽然整个输入里面已经存在：

$$
x_4,x_5
$$

但是：

$$
O_3
$$

完全拿不到它们的信息。

---

<a id="origin-4643"></a>
## 76. 这就是为什么训练时可以一次输入整个句子

比如：

```text
<BOS> I love AI very much
```

虽然：

```text
I
love
AI
very
much
```

全部已经在 GPU 中，

但对于较早的位置来说，未来 token 的 Attention 权重都会被 Mask 成：

$$
0
$$

所以：

```text
<BOS>
```

看不到：

```text
I love AI very much
```

而：

```text
<BOS> I
```

对应的位置看不到：

```text
love AI very much
```

因此所有位置可以一次并行计算，同时又不会偷看未来。

---

<a id="origin-4697"></a>
## 77. 为什么训练阶段特别适合使用 Attention 矩阵理解？

因为一次训练本来就在同时计算多个 Query：

$$
Q_1,Q_2,\dots,Q_L
$$

所以：

$$
QK^T
$$

天然形成：

$$
L\times L
$$

的矩阵。

例如：

$$
L=5
$$

就是：

$$
5\times5
$$

其中：

```text
第1行 → token1

第2行 → token2

第3行 → token3

第4行 → token4

第5行 → token5
```

然后一次矩阵运算：

$$
AV
$$

同时得到：

$$
O_1,O_2,O_3,O_4,O_5
$$

所以训练阶段可以记成：

$$
\boxed{
Attention矩阵
=
很多个Attention向量上下堆起来
}
$$

实际上：

$$
A=
\begin{bmatrix}
A_1\\
A_2\\
A_3\\
A_4\\
A_5
\end{bmatrix}
$$

其中：

$$
A_i
$$

就是第 \(i\) 个 token 对所有位置的 Attention 权重向量。

---

<a id="origin-4790"></a>
## 78. 所以“Attention 矩阵”其实就是很多条 Attention 向量拼起来

例如：

$$
A_1=
[1,0,0,0,0]
$$

$$
A_2=
[\alpha_{21},\alpha_{22},0,0,0]
$$

$$
A_3=
[\alpha_{31},\alpha_{32},\alpha_{33},0,0]
$$

$$
A_4=
[\alpha_{41},\alpha_{42},\alpha_{43},\alpha_{44},0]
$$

$$
A_5=
[\alpha_{51},\alpha_{52},\alpha_{53},\alpha_{54},\alpha_{55}]
$$

把它们上下摞起来：

$$
A=
\begin{bmatrix}
A_1\\
A_2\\
A_3\\
A_4\\
A_5
\end{bmatrix}
$$

就变成：

$$
\boxed{\text{Attention Matrix}}
$$

所以从本质上说：

> Attention 矩阵并不是什么额外的新东西，它只是很多个 token 的 Attention 权重向量一起计算后的矩阵形式。

---

<a id="origin-4844"></a>
## 79. 但是到了推理阶段，思维方式应该切换

训练的时候可以使用：

$$
\boxed{\text{Attention矩阵}}
$$

来理解。

但是进入自回归推理的 Decode 阶段后，如果还一直想象一个完整 Attention 矩阵，反而容易绕进去。

因为：

> Decode 每一次实际上只新增一个 token。

所以真正新增的只有：

$$
\boxed{\text{一条Attention向量}}
$$

---

<a id="origin-4868"></a>
## 80. 推理其实又可以分成两个阶段

一个完整的大模型推理过程一般可以分成：

```text
Prompt
↓
Prefill
↓
开始生成
↓
Decode
↓
Decode
↓
Decode
...
```

即：

$$
\boxed{
\text{Prefill + Decode}
}
$$

这两个阶段 Attention 的计算方式不同。

---

<a id="origin-4899"></a>
## 81. Prefill 阶段

假设用户输入：

```text
我 喜欢 浙江 大学
```

一共有 4 个 token。

Prefill 时，这 4 个 token 会一次性进入模型。

因此仍然可以计算：

$$
QK^T
$$

得到：

$$
4\times4
$$

的 Attention Score 矩阵：

$$
\begin{bmatrix}
s_{11}&-\infty&-\infty&-\infty\\
s_{21}&s_{22}&-\infty&-\infty\\
s_{31}&s_{32}&s_{33}&-\infty\\
s_{41}&s_{42}&s_{43}&s_{44}
\end{bmatrix}
$$

所以：

$$
\boxed{
Prefill阶段仍然适合用Attention矩阵理解
}
$$

并且仍然需要 Causal Mask。

---

<a id="origin-4946"></a>
## 82. Prefill 之后会留下什么？

Prefill 处理完：

$$
x_1,x_2,x_3,x_4
$$

之后，会保存：

$$
K_1,K_2,K_3,K_4
$$

以及：

$$
V_1,V_2,V_3,V_4
$$

形成：

$$
\boxed{\text{KV Cache}}
$$

可以理解成：

```text
位置     K         V

x1      K1        V1

x2      K2        V2

x3      K3        V3

x4      K4        V4
```

这些信息后面生成新 token 时还要继续使用。

---

<a id="origin-4990"></a>
## 83. 进入 Decode 阶段

假设现在模型已经有：

$$
x_1,x_2,x_3,x_4
$$

现在又来了：

$$
x_5
$$

注意：

> 此时不是重新把 5 个 token 全部从头计算。

因为：

$$
K_1,V_1
$$

$$
K_2,V_2
$$

$$
K_3,V_3
$$

$$
K_4,V_4
$$

都已经缓存好了。

新 token 只需要产生：

$$
Q_5,K_5,V_5
$$

---

<a id="origin-5036"></a>
## 84. Decode 阶段最适合用 Attention 向量理解

现在我们有：

$$
Q_5
$$

和缓存中的：

$$
K_1,K_2,K_3,K_4
$$

再加新的：

$$
K_5
$$

所以直接计算：

$$
Q_5
\begin{bmatrix}
K_1\\
K_2\\
K_3\\
K_4\\
K_5
\end{bmatrix}^T
$$

得到：

$$
\boxed{
[
Q_5K_1^T,
Q_5K_2^T,
Q_5K_3^T,
Q_5K_4^T,
Q_5K_5^T
]
}
$$

这是：

$$
\boxed{1\times5}
$$

也就是：

> 一条 Attention Score 向量。

---

<a id="origin-5095"></a>
## 85. Decode 阶段没有必要再构造完整 Attention 矩阵

理论上如果硬要画，可以想象一个：

$$
5\times5
$$

的 Attention 矩阵。

但前面：

```text
第1行
第2行
第3行
第4行
```

早已经在之前处理过。

现在真正新增的只是：

```text
第5行
```

所以没有必要再重新计算：

$$
Q_1K_1^T
$$

$$
Q_2K_1^T,Q_2K_2^T
$$

等等。

实际需要的只有：

$$
\boxed{
[
Q_5K_1^T,
Q_5K_2^T,
Q_5K_3^T,
Q_5K_4^T,
Q_5K_5^T
]
}
$$

所以：

> “Attention 矩阵最后一行”

在推理阶段更多只是一个**帮助理解的概念**。

实际计算应该直接理解成：

$$
\boxed{\text{Attention向量}}
$$

---

<a id="origin-5162"></a>
## 86. Attention Score 向量之后发生什么？

得到：

$$
[
s_{51},
s_{52},
s_{53},
s_{54},
s_{55}
]
$$

进行 Softmax：

$$
[
\alpha_{51},
\alpha_{52},
\alpha_{53},
\alpha_{54},
\alpha_{55}
]
$$

然后使用所有缓存的 Value：

$$
O_5
=
\alpha_{51}V_1
+
\alpha_{52}V_2
+
\alpha_{53}V_3
+
\alpha_{54}V_4
+
\alpha_{55}V_5
$$

因此：

$$
\boxed{
O_5
=
\sum_{j=1}^{5}
\alpha_{5j}V_j
}
$$

---

<a id="origin-5217"></a>
## 87. 为什么只算一条 Attention 向量，仍然能看到所有历史信息？

这是 KV Cache 最核心的一点。

有人可能会觉得：

> 以前那个 Attention 大矩阵都不算了，只剩当前一条向量，会不会丢掉前面的信息？

不会。

因为当前 Attention 向量：

$$
[
Q_5K_1^T,
Q_5K_2^T,
Q_5K_3^T,
Q_5K_4^T,
Q_5K_5^T
]
$$

本身就和所有历史 Key：

$$
K_1,K_2,K_3,K_4
$$

进行了匹配。

而后面计算：

$$
O_5
$$

又使用：

$$
V_1,V_2,V_3,V_4,V_5
$$

所以：

$$
\boxed{
只计算当前Attention向量
\neq
只使用当前token信息
}
$$

恰恰相反：

$$
\boxed{
当前Attention向量本身就在读取整个KV Cache
}
$$

---

<a id="origin-5279"></a>
## 88. 第 6 个 token 来的时候同理

假设现在又生成：

$$
x_6
$$

KV Cache 已经有：

$$
K_1,K_2,K_3,K_4,K_5
$$

以及：

$$
V_1,V_2,V_3,V_4,V_5
$$

新的 token 只需要计算：

$$
Q_6,K_6,V_6
$$

把：

$$
K_6,V_6
$$

追加到 Cache。

然后：

$$
Q_6
\begin{bmatrix}
K_1\\
K_2\\
K_3\\
K_4\\
K_5\\
K_6
\end{bmatrix}^T
$$

得到：

$$
[
s_{61},
s_{62},
s_{63},
s_{64},
s_{65},
s_{66}
]
$$

Softmax：

$$
[
\alpha_{61},
\alpha_{62},
\alpha_{63},
\alpha_{64},
\alpha_{65},
\alpha_{66}
]
$$

最后：

$$
O_6
=
\sum_{j=1}^{6}
\alpha_{6j}V_j
$$

所以：

$$
\boxed{
每生成一个新token，只新增一条Attention向量
}
$$

---

<a id="origin-5372"></a>
## 89. 为什么历史 Attention Score 不需要缓存？

比如生成第 5 个位置时曾经计算：

$$
Q_5K_1^T
$$

$$
Q_5K_2^T
$$

$$
\dots
$$

这些 score 回答的问题是：

> 第 5 个位置当时应该关注谁？

等到生成第 6 个 token 时，现在的问题变成：

> 第 6 个位置应该关注谁？

所以需要的是：

$$
Q_6K_1^T
$$

$$
Q_6K_2^T
$$

$$
\dots
$$

过去：

$$
Q_5K_j^T
$$

已经没用了。

因为：

$$
Q_5
$$

和：

$$
Q_6
$$

代表的是两个不同位置的 Query。

---

<a id="origin-5434"></a>
## 90. 为什么 K 必须缓存？

虽然过去的 Attention Score 没用了，

但：

$$
K_1,K_2,K_3,\dots
$$

还必须保留。

因为每一个新的 Query：

$$
Q_N
$$

都需要重新和历史 Key 匹配：

$$
Q_NK_1^T
$$

$$
Q_NK_2^T
$$

$$
\dots
$$

所以：

$$
\boxed{
历史K仍然是未来Query需要查询的“索引”
}
$$

因此必须缓存。

---

<a id="origin-5478"></a>
## 91. 为什么 V 也必须缓存？

仅有 Attention 权重是不够的。

得到：

$$
[
\alpha_{N1},
\alpha_{N2},
\dots,
\alpha_{NN}
]
$$

以后还必须：

$$
O_N
=
\alpha_{N1}V_1+
\alpha_{N2}V_2+
\cdots+
\alpha_{NN}V_N
$$

所以：

$$
V_1,V_2,\dots,V_N
$$

也必须保存。

因此最终需要：

$$
\boxed{
K + V
}
$$

这就是：

$$
\boxed{\text{KV Cache}}
$$

---

<a id="origin-5528"></a>
## 92. 为什么不缓存 Q？

历史：

$$
Q_1,Q_2,\dots,Q_{N-1}
$$

分别回答的是：

```text
token1 当时应该关注谁？

token2 当时应该关注谁？

...

token(N-1) 当时应该关注谁？
```

这些问题都已经解决了。

当：

$$
x_N
$$

出现以后，

我们只关心：

$$
Q_N
$$

因为现在的问题是：

> 当前第 \(N\) 个 token 应该从过去哪些位置获取信息？

因此：

$$
\boxed{
历史Q没有必要缓存
}
$$

而：

$$
\boxed{
历史K/V仍然会被未来的新Query使用
}
$$

所以只缓存：

$$
\boxed{
K,V
}
$$

---

<a id="origin-5594"></a>
## 93. 一个非常重要的修正：不能简单说“QKV 本身都包含全部历史信息”

这一句话需要稍微谨慎。

特别是在 Transformer 第一层。

假设新来了：

$$
x_N
$$

第一层刚开始时：

$$
Q_N=x_NW_Q
$$

$$
K_N=x_NW_K
$$

$$
V_N=x_NW_V
$$

此时：

$$
Q_N
$$

主要还是来自当前 token 的输入表示。

它并不是天然已经包含所有历史 token。

真正把历史信息汇聚进来的步骤是：

$$
Q_N
$$

去查询：

$$
K_1,K_2,\dots,K_N
$$

得到 Attention 权重：

$$
\alpha_{N1},\dots,\alpha_{NN}
$$

然后：

$$
O_N
=
\sum_j\alpha_{Nj}V_j
$$

因此：

$$
\boxed{
Attention本身才是当前token融合历史信息的关键过程
}
$$

---

<a id="origin-5666"></a>
## 94. 到更深层的时候又不一样

第一层得到：

$$
H_N^{(1)}
$$

以后，

这个 hidden state 已经通过 Attention 融合了一部分历史信息。

到了第二层：

$$
Q_N^{(2)}
=
H_N^{(1)}W_Q^{(2)}
$$

$$
K_N^{(2)}
=
H_N^{(1)}W_K^{(2)}
$$

$$
V_N^{(2)}
=
H_N^{(1)}W_V^{(2)}
$$

此时：

$$
H_N^{(1)}
$$

本身已经是上下文化后的表示。

所以：

$$
Q_N^{(2)},K_N^{(2)},V_N^{(2)}
$$

也已经间接包含了前面一层汇聚来的历史信息。

然后第二层再进行一次 Attention：

$$
Q_N^{(2)}
\rightarrow
K_1^{(2)},\dots,K_N^{(2)}
$$

进一步融合信息。

因此随着 Transformer 层数增加：

$$
\boxed{
当前token的hidden\ state逐层融合越来越丰富的上下文
}
$$

---

<a id="origin-5734"></a>
## 95. 训练阶段和推理阶段其实可以统一起来

训练阶段：

$$
Q=
\begin{bmatrix}
Q_1\\
Q_2\\
\vdots\\
Q_L
\end{bmatrix}
$$

一次计算：

$$
QK^T
$$

得到：

$$
L\times L
$$

的 Attention Score 矩阵。

本质上相当于同时计算：

$$
Q_1K^T
$$

$$
Q_2K^T
$$

$$
Q_3K^T
$$

$$
\dots
$$

$$
Q_LK^T
$$

也就是很多条 Attention Score 向量。

---

而 Decode 阶段：

过去的：

$$
Q_1,Q_2,\dots,Q_{N-1}
$$

已经处理完。

所以本轮只剩：

$$
Q_NK^T
$$

即：

$$
\boxed{
1\times N
}
$$

的 Attention Score 向量。

因此可以统一理解为：

$$
\boxed{
训练 = 同时计算很多条Attention向量
}
$$

$$
\boxed{
Decode = 每轮只计算最新的一条Attention向量
}
$$

---

<a id="origin-5830"></a>
## 96. 所以 Attention 矩阵和 Attention 向量不是两个不同机制

Attention Matrix：

$$
A=
\begin{bmatrix}
A_1\\
A_2\\
\vdots\\
A_L
\end{bmatrix}
$$

其中：

$$
A_i
$$

就是第 \(i\) 个 Query 对所有 Key 产生的一条 Attention 向量。

所以：

$$
\boxed{
Attention Matrix
=
很多条 Attention Vector 纵向堆叠
}
$$

训练时：

> 所有 Query 一起算。

推理 Decode 时：

> 只有最新 Query 需要算。

核心机制其实完全一样。

---

<a id="origin-5874"></a>
## 97. Causal Mask 在 Decode 阶段还有没有意义？

在标准逐 token Decode 中，假设当前已经生成：

$$
x_1,\dots,x_N
$$

那么当前 Query：

$$
Q_N
$$

面对的是：

$$
K_1,\dots,K_N
$$

这些全部都是：

```text
过去token + 当前token
```

不存在：

$$
K_{N+1},K_{N+2},\dots
$$

因为这些未来 token 根本还没有生成。

所以这一轮 Attention Score 向量：

$$
[
Q_NK_1^T,\dots,Q_NK_N^T
]
$$

所有位置本身都是合法的。

因此标准 Decode 阶段可以直观理解成：

$$
\boxed{
未来token根本不存在，所以没有东西需要Mask
}
$$

而训练 / Prefill 不一样。

因为：

$$
x_1,\dots,x_L
$$

一次全部已经放进来了，

所以必须通过 Causal Mask 防止前面位置偷看后面位置。

---

<a id="origin-5940"></a>
## 98. 为什么训练不能也像 Decode 一样一个 token 一个 token 算？

理论上完全可以。

比如：

```text
第1次：

x1
→ 计算


第2次：

x1 x2
→ 计算


第3次：

x1 x2 x3
→ 计算

...
```

这样天然就不会看到未来 token。

但问题是：

> 太慢。

GPU 最擅长的是大的矩阵并行计算。

所以训练时直接：

$$
QK^T
$$

一次得到：

$$
L\times L
$$

然后利用：

$$
\boxed{\text{Causal Mask}}
$$

人工制造出：

```text
第1行只能看到1个token

第2行只能看到2个token

第3行只能看到3个token

...
```

的效果。

于是同时获得：

$$
\boxed{
正确的因果约束
+
GPU的大规模并行计算
}
$$

---

<a id="origin-6019"></a>
## 99. Causal Mask 真正解决的问题

因此 Causal Mask 的意义并不是：

> “Transformer 本身不知道前后顺序。”

而是更具体的：

> **当训练阶段把整条序列同时放进模型进行并行计算时，阻止当前位置使用未来 token 的内容。**

也就是说：

$$
\boxed{
Causal Mask
=
让并行训练模拟逐token自回归生成
}
$$

这句话非常重要。

训练阶段实际上在同时模拟：

```text
x1

x1 x2

x1 x2 x3

x1 x2 x3 x4

...
```

这些不同长度的前缀。

只不过全部被压进一个：

$$
L\times L
$$

的矩阵里并行计算。

---

<a id="origin-6067"></a>
## 100. 从这个角度重新理解 Causal Matrix

假设：

$$
L=5
$$

Causal Mask：

$$
\begin{bmatrix}
✓&×&×&×&×\\
✓&✓&×&×&×\\
✓&✓&✓&×&×\\
✓&✓&✓&✓&×\\
✓&✓&✓&✓&✓
\end{bmatrix}
$$

其实相当于一次模拟了：

```text
第1个任务：

[x1]


第2个任务：

[x1,x2]


第3个任务：

[x1,x2,x3]


第4个任务：

[x1,x2,x3,x4]


第5个任务：

[x1,x2,x3,x4,x5]
```

所以：

$$
\boxed{
下三角Attention矩阵
=
多个不同长度前缀任务的并行表达
}
$$

---

<a id="origin-6127"></a>
## 101. 最终把训练、Prefill、Decode 放在一起

<a id="origin-6129"></a>
### 101.1 训练

假设长度：

$$
L
$$

一次输入：

$$
x_1,\dots,x_L
$$

计算：

$$
QK^T
$$

得到：

$$
\boxed{L\times L}
$$

使用：

$$
\boxed{\text{Causal Mask}}
$$

防止未来信息泄露。

---

<a id="origin-6165"></a>
### 101.2 Prefill

用户 Prompt：

$$
x_1,\dots,x_P
$$

通常也一次并行处理。

所以也是：

$$
\boxed{P\times P}
$$

并使用 Causal Mask。

同时产生并缓存：

$$
K_1,\dots,K_P
$$

和：

$$
V_1,\dots,V_P
$$

---

<a id="origin-6197"></a>
### 101.3 Decode

现在产生：

$$
x_{P+1}
$$

只计算：

$$
Q_{P+1},K_{P+1},V_{P+1}
$$

然后：

$$
Q_{P+1}
K_{\text{cache}}^T
$$

得到：

$$
\boxed{1\times(P+1)}
$$

Attention Score 向量。

之后：

$$
\operatorname{softmax}
$$

再乘：

$$
V_{\text{cache}}
$$

得到当前：

$$
O_{P+1}
$$

然后继续生成下一个 token。

---

<a id="origin-6248"></a>
## 102. 一张图把整个故事串起来

```text
====================
      训练阶段
====================

x1 x2 x3 x4 x5
↓
Q1 Q2 Q3 Q4 Q5
↓
一次计算 QKᵀ
↓
5 × 5 Attention Score Matrix

        K1 K2 K3 K4 K5

Q1      ✓  ×  ×  ×  ×
Q2      ✓  ✓  ×  ×  ×
Q3      ✓  ✓  ✓  ×  ×
Q4      ✓  ✓  ✓  ✓  ×
Q5      ✓  ✓  ✓  ✓  ✓

↓
Softmax
↓
很多条Attention向量
↓
同时得到 O1 O2 O3 O4 O5



====================
     Prompt Prefill
====================

Prompt:
x1 x2 x3 x4

↓
一次并行处理
↓
4 × 4 Attention矩阵
↓
得到并保存：

K1 V1
K2 V2
K3 V3
K4 V4



====================
      Decode
====================

新token x5
↓
只产生新的：

Q5 K5 V5

↓
K5、V5加入KV Cache

↓
Q5 查询全部历史Key：

Q5 · [K1 K2 K3 K4 K5]ᵀ

↓
得到一条Attention Score向量：

[s51 s52 s53 s54 s55]

↓
Softmax

[α51 α52 α53 α54 α55]

↓
加权全部Value

O5 =
α51V1 +
α52V2 +
α53V3 +
α54V4 +
α55V5

↓
生成下一个token
```

---

<a id="origin-6345"></a>
## 103. 最后必须牢牢记住的几个结论

<a id="origin-6347"></a>
### 103.1 结论一：训练时是矩阵

输入长度：

$$
L
$$

Attention Score：

$$
\boxed{L\times L}
$$

因为：

$$
Q_1,\dots,Q_L
$$

同时计算。

---

<a id="origin-6371"></a>
### 103.2 结论二：每一行其实就是一条 Attention 向量

$$
\boxed{
Attention矩阵第i行
=
第i个token的Attention向量
}
$$

所以：

$$
\boxed{
Attention矩阵
=
所有token的Attention向量堆起来
}
$$

---

<a id="origin-6393"></a>
### 103.3 结论三：Causal Mask 不会缩小矩阵

训练时如果：

$$
L=5
$$

整个矩阵仍然：

$$
5\times5
$$

只是通过：

$$
-\infty
$$

让未来位置 Softmax 后：

$$
\boxed{权重=0}
$$

---

<a id="origin-6421"></a>
### 103.4 结论四：Causal Mask 的本质

$$
\boxed{
让一次并行计算模拟多个不同长度的自回归前缀
}
$$

也就是：

```text
第1行模拟：
x1

第2行模拟：
x1 x2

第3行模拟：
x1 x2 x3

...
```

---

<a id="origin-6446"></a>
### 103.5 结论五：Decode 时不要再执着于完整 Attention 矩阵

Decode 第 \(N\) 个 token 时真正计算的是：

$$
\boxed{
Q_NK_{\text{cache}}^T
}
$$

得到：

$$
\boxed{
1\times N
}
$$

的一条 Attention Score 向量。

所以：

$$
\boxed{
Decode阶段最好用Attention向量理解
}
$$

---

<a id="origin-6476"></a>
### 103.6 结论六：只算当前向量，不代表只使用当前 token

虽然只计算：

$$
Q_N
$$

这一条 Query，

但它会访问：

$$
K_1,\dots,K_N
$$

然后使用：

$$
V_1,\dots,V_N
$$

因此：

$$
\boxed{
当前token仍然可以读取全部历史上下文
}
$$

---

<a id="origin-6508"></a>
### 103.7 结论七：为什么缓存 K/V，不缓存 Attention Score？

因为过去的 Attention Score：

$$
Q_iK_j^T
$$

回答的是：

> 当时第 \(i\) 个位置应该关注谁？

这个问题已经解决。

新 token 出现以后需要回答新的问题：

> 新的 \(Q_N\) 应该关注谁？

所以必须重新计算：

$$
Q_NK_1^T,\dots,Q_NK_N^T
$$

因此历史 Attention Score 没有复用价值。

但是历史：

$$
K_1,\dots,K_{N-1}
$$

仍然要被新的 \(Q_N\) 查询，

历史：

$$
V_1,\dots,V_{N-1}
$$

仍然要参与最终加权和。

所以：

$$
\boxed{
缓存K/V，而不是Attention Score
}
$$

---

<a id="origin-6560"></a>
## 104. 最核心的一句话

整个 Transformer 从训练到推理，可以统一理解成：

$$
\boxed{
Attention的本质始终是：
一个Query去查询一组Key，
得到一条权重向量，
再利用这条权重向量加权一组Value。
}
$$

训练时：

$$
\boxed{
很多个Query一起做
\rightarrow
很多条Attention向量
\rightarrow
堆成Attention矩阵
}
$$

而 Decode 时：

$$
\boxed{
每次只有一个新Query
\rightarrow
只需要一条Attention向量
}
$$

因此：

$$
\boxed{
训练看矩阵，Decode看向量
}
$$

是理解 Transformer Attention 最清晰的一种方式。

而：

$$
\boxed{
Causal Mask负责训练时“不偷看未来”，
KV Cache负责推理时“不重复计算历史”。
}
$$

两者解决的是两个完全不同的问题。


---


<a id="origin-6620"></a>
## 105. 从 KV Cache 到 GQA：Grouped Query Attention 详解

<a id="origin-6622"></a>
## 106. 从 KV Cache 开始

假设模型正在自回归生成：

```text
我 喜欢 人工 智能
```

现在准备生成第 5 个 token。

如果没有 KV Cache，那么每生成一个新的 token，都需要重新计算前面所有 token 的：

$$
K_1,K_2,K_3,K_4
$$

以及：

$$
V_1,V_2,V_3,V_4
$$

这会产生大量重复计算。

因此，推理阶段会把历史 token 的 \(K\) 和 \(V\) 保存下来：

```text
KV Cache

token1 → K1, V1
token2 → K2, V2
token3 → K3, V3
token4 → K4, V4
```

新 token 到来后，只需要计算它自己的：

$$
Q_5,K_5,V_5
$$

然后让：

$$
Q_5
$$

去查询：

$$
K_1,K_2,K_3,K_4,K_5
$$

得到 Attention 权重，再读取：

$$
V_1,V_2,V_3,V_4,V_5
$$

因此：

> **KV Cache 的核心作用，就是缓存历史 token 的 K/V，避免在自回归生成过程中反复计算。**

---

<a id="origin-6687"></a>
## 107. KV Cache 又带来了新的问题

KV Cache 虽然减少了重复计算，但它带来了另一个问题：

> **KV Cache 非常占显存。**

原因在于 Transformer 并不是只有一个 Attention Head，而是通常有很多个 Head。

例如：

$$
N_{head}=32
$$

在传统的 Multi-Head Attention，也就是 MHA 中：

```text
Head 1：Q1 K1 V1
Head 2：Q2 K2 V2
Head 3：Q3 K3 V3
...
Head 32：Q32 K32 V32
```

也就是说：

> 每一个 Query Head 都有自己独立的一套 K 和 V。

因此，对于每一个历史 token，我们并不是只缓存：

```text
K
V
```

而是缓存：

```text
K_head1 V_head1
K_head2 V_head2
K_head3 V_head3
...
K_head32 V_head32
```

因此 KV Cache 的大小与：

$$
N_{KVHead}
$$

基本成正比。

---


<a id="origin-6744"></a>
## 108. MHA 下 KV Cache 为什么这么大？

假设某一层 Attention 的注意力头数量为：

$$
N_{head}=32
$$

在传统的 Multi-Head Attention（MHA）中，每一个 Query Head 都对应自己独立的 Key Head 和 Value Head，因此：

$$
N_{KVHead}=N_{head}=32
$$

---

对于每一个 Attention Head，假设**每个 token 对应的 Key 向量和 Value 向量的维度**均为：

$$
d_{head}=128
$$

也就是说，对于第 \(i\) 个 token，在某一个 Attention Head 中：

$$
k_i,v_i\in\mathbb{R}^{128}
$$

因此，一个 token 在一个 KV Head 中需要保存：

$$
128
$$

个 Key 数值，以及：

$$
128
$$

个 Value 数值。

---

现在假设上下文长度为：

$$
L=8192
$$

也就是说，KV Cache 中需要保存前面：

$$
8192
$$

个 token 的 Key 和 Value。

---

<a id="origin-6804"></a>
### 108.1 先看一个 KV Head

对于一个 KV Head，8192 个 token 的 Key 向量堆叠起来，可以得到：

$$
K\in\mathbb{R}^{8192\times128}
$$

因此 Key 一共包含：

$$
8192\times128
$$

个数值。

Value 同理：

$$
V\in\mathbb{R}^{8192\times128}
$$

也包含：

$$
8192\times128
$$

个数值。

所以一个 KV Head 的 KV Cache 一共需要保存：

$$
2\times8192\times128
$$

个数值。

---

<a id="origin-6844"></a>
## 109. 2 再考虑 32 个 Attention Head

传统 MHA 中：

$$
N_{KVHead}=32
$$

也就是说，每个 Head 都拥有自己独立的 K 和 V。

因此单层所有 Key 的数量为：

$$
8192\times32\times128
$$

所有 Value 的数量同样为：

$$
8192\times32\times128
$$

所以单层 KV Cache 总共需要保存：

$$
2\times8192\times32\times128
$$

个数值。

即：

$$
\boxed{
KV_{\text{single layer}}
=
2\times L\times N_{KVHead}\times d_{head}
}
$$

代入：

$$
L=8192
$$

$$
N_{KVHead}=32
$$

$$
d_{head}=128
$$

得到：

$$
2\times8192\times32\times128
=
67,108,864
$$

也就是说：

> **仅仅一层 Attention，就需要为 KV Cache 保存约 6711 万个数值。**

---

<a id="origin-6912"></a>
## 110. 3 再考虑模型有很多层

假设整个 Transformer 一共有：

$$
N_{layer}=32
$$

层。

因为每一层 Attention 都有自己独立的 K/V，所以每一层都需要维护自己的 KV Cache。

因此整个模型需要保存：

$$
2\times8192\times32\times128\times32
$$

个数值。

即：

$$
\boxed{
KV_{\text{total}}
=
2\times
L
\times
N_{layer}
\times
N_{KVHead}
\times
d_{head}
}
$$

代入数值：

$$
2
\times8192
\times32
\times32
\times128
$$

得到：

$$
2,147,483,648
$$

也就是大约：

$$
\boxed{21.47亿}
$$

个数值。

---

<a id="origin-6975"></a>
## 111. 4 为什么这会占很多显存？

因为这些数值都需要真实地存储在 GPU 显存中。

例如，如果 KV Cache 使用 FP16 或 BF16：

$$
1\text{ 个数值}=2\text{ Bytes}
$$

那么：

$$
2,147,483,648\times2
$$

约等于：

$$
4,294,967,296\text{ Bytes}
$$

也就是大约：

$$
\boxed{4\text{ GiB}}
$$

这还只是：

* batch size = 1
* 上下文长度 = 8192
* 32 层
* 32 个 KV Head

的情况。

如果上下文长度继续增加，例如：

$$
8192\rightarrow32768
$$

KV Cache 也会近似扩大：

$$
4\times
$$

---

<a id="origin-7026"></a>
## 112. 5 KV Cache 大小到底由什么决定？

忽略 batch size 和数据类型时，KV Cache 中保存的数值数量可以写成：

$$
\boxed{
KV\ Cache
\propto
2
\times
L
\times
N_{layer}
\times
N_{KVHead}
\times
d_{head}
}
$$

其中：

* \(L\)：上下文中的 token 数量
* \(N_{layer}\)：Transformer 层数
* \(N_{KVHead}\)：每层的 KV Head 数量
* \(d_{head}\)：每个 token 在每个 KV Head 中的 Key/Value 向量维度
* 前面的 \(2\)：分别对应 K 和 V

如果进一步考虑 batch size \(B\)，则：

$$
\boxed{
KV\ Cache
\propto
2
\times
B
\times
L
\times
N_{layer}
\times
N_{KVHead}
\times
d_{head}
}
$$

---

<a id="origin-7076"></a>
## 113. 一个自然的问题：不同 Q Head 能不能共享 K/V？

既然推理阶段真正需要长期缓存的是：

$$
K,V
$$

那么一个非常自然的想法就是：

> 能不能保留多个 Query Head，但让不同 Query Head 共用 K/V？

这就产生了：

$$
\boxed{\text{Multi-Query Attention，MQA}}
$$

---

<a id="origin-7096"></a>
## 114. MQA：Multi-Query Attention

传统 MHA：

```text
Q1 → K1 V1
Q2 → K2 V2
Q3 → K3 V3
Q4 → K4 V4
```

每个 Query Head 都拥有独立的 K/V。

而 MQA：

```text
Q1 ─┐
Q2 ─┤
Q3 ─┼──→ 同一个 K / V
Q4 ─┘
```

假设：

$$
N_Q=32
$$

传统 MHA 中：

$$
N_{KV}=32
$$

而 MQA 中：

$$
N_{KV}=1
$$

因此原本要缓存 32 组 K/V，现在只需要缓存 1 组。

理论上 KV Cache 可以缩小到原来的：

$$
\frac{1}{32}
$$

也就是大约：

$$
32\times
$$

的压缩。

---

<a id="origin-7154"></a>
## 115. 但是 MQA 又走得太远了

在传统 MHA 中，每个 Attention Head 都有自己独立的：

$$
W_Q,W_K,W_V
$$

因此不同 Head 可以学习不同的特征。

可以粗略理解为：

```text
Head 1：关注主谓关系
Head 2：关注代词指代
Head 3：关注长距离依赖
Head 4：关注局部搭配
...
```

真实模型中的 Head 并不一定存在这么明确的一一对应功能，这里只是为了帮助理解。

MHA 中：

```text
Q1 → K1 V1
Q2 → K2 V2
Q3 → K3 V3
...
```

每个 Head 都可以拥有自己的 KV 表示。

但是到了 MQA：

```text
Q1 ─┐
Q2 ─┤
Q3 ─┤
...  ├→ 同一套 K/V
Q32 ┘
```

虽然 Query 依然有很多个：

$$
Q_1,Q_2,\dots,Q_{32}
$$

但是所有 Query Head 都面对同一套：

$$
K,V
$$

因此：

> **K/V 的表示多样性会明显下降。**

于是就出现了一个自然的问题：

> MHA 的 KV Cache 太大，MQA 又共享得太激进，有没有一个折中的方案？

答案就是：

$$
\boxed{\text{GQA}}
$$

---

<a id="origin-7225"></a>
## 116. GQA：Grouped Query Attention

GQA 全称：

$$
\boxed{\text{Grouped Query Attention}}
$$

中文通常称为：

> **分组查询注意力**

它的核心思想非常简单：

> **不是每个 Query Head 都独占一套 K/V，也不是所有 Query Head 都共享同一套 K/V，而是把多个 Query Head 分成若干组，每一组共享一套 K/V。**

例如现在有：

$$
8
$$

个 Query Heads。

传统 MHA：

```text
Q1 → K1 V1
Q2 → K2 V2
Q3 → K3 V3
Q4 → K4 V4
Q5 → K5 V5
Q6 → K6 V6
Q7 → K7 V7
Q8 → K8 V8
```

因此：

$$
N_Q=8
$$

$$
N_{KV}=8
$$

---

使用 GQA 后，可以变成：

```text
Q1 ─┐
Q2 ─┼→ K1 V1
Q3 ─┤
Q4 ─┘

Q5 ─┐
Q6 ─┼→ K2 V2
Q7 ─┤
Q8 ─┘
```

此时：

$$
N_Q=8
$$

但：

$$
N_{KV}=2
$$

也就是说：

$$
\frac{8}{2}=4
$$

每 4 个 Query Head 共享一组 K/V。

---

<a id="origin-7310"></a>
## 117. GQA 本质上控制的是 Q Head 和 KV Head 的比例

假设：

$$
N_Q=32
$$

---

<a id="origin-7320"></a>
### 117.1 MHA

MHA 中：

$$
N_{KV}=32
$$

所以：

$$
32Q:32KV
$$

也就是：

$$
\frac{N_Q}{N_{KV}}=1
$$

一个 Q Head 对应一组 KV。

---

<a id="origin-7344"></a>
### 117.2 GQA

例如：

$$
N_{KV}=8
$$

则：

$$
32Q:8KV
$$

于是每个 KV Head 被：

$$
\frac{32}{8}=4
$$

个 Query Head 共享。

---

<a id="origin-7368"></a>
### 117.3 MQA

MQA 中：

$$
N_{KV}=1
$$

因此：

$$
32Q:1KV
$$

所有 32 个 Query Head 共用一组 K/V。

---

所以三者可以理解为一条连续的谱：

```text
MHA                   GQA                    MQA

32 Q                  32 Q                   32 Q
32 KV                  8 KV                   1 KV

共享程度低  ───────────────→  共享程度高

KV Cache 大            折中                KV Cache 最小
表达灵活                                   KV共享最激进
```

---

<a id="origin-7402"></a>
## 118. MHA 和 MQA 都可以看成 GQA 的特殊情况

从数学关系来看：

如果：

$$
N_{KV}=N_Q
$$

那么就是：

$$
\boxed{MHA}
$$

如果：

$$
N_{KV}=1
$$

那么就是：

$$
\boxed{MQA}
$$

而：

$$
1<N_{KV}<N_Q
$$

就是典型的：

$$
\boxed{GQA}
$$

因此可以把 GQA 看成一个更一般化的框架：

$$
\boxed{
MHA
\subset
GQA
}
$$

以及：

$$
\boxed{
MQA
\subset
GQA
}
$$

更准确地说：

> MHA 和 MQA 可以看成 GQA 在不同 KV Head 数量下的两个极端情况。

---

<a id="origin-7468"></a>
## 119. 为什么减少的是 KV Head，而不是 Q Head？

这是理解 GQA 最关键的一点之一。

对于当前正在生成的 token，Attention 计算形式是：

$$
Q_{current}K_{history}^{T}
$$

然后：

$$
Attention
=
softmax
\left(
\frac{Q_{current}K_{history}^{T}}
{\sqrt{d_k}}
\right)
V_{history}
$$

注意这里真正需要长期保留的是：

$$
K_{history}
$$

和：

$$
V_{history}
$$

过去 token 的 Query：

$$
Q_{history}
$$

其实已经没有用了。

因为 Query 的作用是：

> 当前 token 发起查询。

一个历史 token 当年生成时，它的 Query 用完之后就可以丢弃。

所以：

```text
历史 Q：不用缓存
历史 K：必须缓存
历史 V：必须缓存
```

这正是为什么叫：

$$
\boxed{KV\ Cache}
$$

而不是：

$$
QKV\ Cache
$$

---

因此，如果我们希望减少推理时的显存：

最值得优化的是：

$$
K,V
$$

而不是 Q。

所以 GQA 的策略就是：

> **尽量保留较多的 Query Head 来维持查询的多样性，同时减少 KV Head 的数量，从而缩小 KV Cache。**

---

<a id="origin-7555"></a>
## 120. 从 KV Cache 的角度理解 GQA

假设：

$$
N_Q=32
$$

---

<a id="origin-7565"></a>
### 120.1 MHA

$$
N_{KV}=32
$$

需要保存：

```text
32 份 K
32 份 V
```

---

<a id="origin-7580"></a>
### 120.2 GQA

假设：

$$
N_{KV}=8
$$

只需要保存：

```text
8 份 K
8 份 V
```

因此 KV Cache 变为：

$$
\frac{8}{32}
=
\frac14
$$

也就是：

$$
25\%
$$

换句话说，理论上对应部分的 KV Cache 可以减少：

$$
75\%
$$

---

<a id="origin-7617"></a>
### 120.3 MQA

如果：

$$
N_{KV}=1
$$

那么 KV Cache 变为：

$$
\frac{1}{32}
$$

是传统 MHA 的：

$$
3.125\%
$$

---

因此从 KV Cache 的角度来看：

```text
MHA
↓
KV Cache 太大
↓
减少 KV Head
↓
MQA
↓
KV Cache 极小，但共享过于激进
↓
选择中间值
↓
GQA
↓
在表达能力与推理效率之间进行折中
```

---

<a id="origin-7661"></a>
## 121. 一个非常直观的比喻

可以把 Query Head 想象成：

> **32 个学生**

把 K/V 想象成：

> **32 套参考资料**

---

<a id="origin-7673"></a>
### 121.1 MHA：每个人一套资料

```text
学生1 → 资料1
学生2 → 资料2
学生3 → 资料3
...
学生32 → 资料32
```

优点：

> 每个人都有独立、定制化的资料。

缺点：

> 需要存储 32 套资料。

对应：

$$
32Q:32KV
$$

---

<a id="origin-7699"></a>
## 122. MQA：所有人共用一套资料

```text
学生1 ─┐
学生2 ─┤
学生3 ─┤
...    ├→ 资料1
学生32 ┘
```

优点：

> 只需要保存一套资料。

缺点：

> 32 个人使用的底层资料完全相同，信息多样性降低。

对应：

$$
32Q:1KV
$$

---

<a id="origin-7725"></a>
## 123. GQA：分组共享资料

现在把 32 个学生分成：

$$
8
$$

组。

每组：

$$
4
$$

个人。

```text
学生 1~4   → 资料1
学生 5~8   → 资料2
学生 9~12  → 资料3
学生13~16  → 资料4
学生17~20  → 资料5
学生21~24  → 资料6
学生25~28  → 资料7
学生29~32  → 资料8
```

因此：

$$
32Q:8KV
$$

每：

$$
4
$$

个 Query Head 共用一套 KV。

这就同时兼顾了：

* 多个 Query Head 的查询多样性
* K/V 的一定多样性
* 更小的 KV Cache

---

<a id="origin-7776"></a>
## 124. GQA 并没有改变 Attention 的核心公式

传统 Attention：

$$
Attention(Q,K,V)
=
softmax
\left(
\frac{QK^T}
{\sqrt{d_k}}
\right)V
$$

GQA 并没有修改这个核心公式。

改变的其实是：

$$
\boxed{Q\ Head\ 与\ KV\ Head\ 的对应关系}
$$

---

<a id="origin-7800"></a>
### 124.1 MHA

传统 MHA：

$$
Q_i
\leftrightarrow
K_i,V_i
$$

例如：

$$
Q_1\leftrightarrow K_1,V_1
$$

$$
Q_2\leftrightarrow K_2,V_2
$$

$$
Q_3\leftrightarrow K_3,V_3
$$

---

<a id="origin-7826"></a>
### 124.2 GQA

假设每 4 个 Query Head 共用一个 KV Head：

$$
Q_1,Q_2,Q_3,Q_4
\leftrightarrow
K_1,V_1
$$

$$
Q_5,Q_6,Q_7,Q_8
\leftrightarrow
K_2,V_2
$$

等等。

所以：

$$
Attention_1
=
Attention(Q_1,K_1,V_1)
$$

$$
Attention_2
=
Attention(Q_2,K_1,V_1)
$$

$$
Attention_3
=
Attention(Q_3,K_1,V_1)
$$

$$
Attention_4
=
Attention(Q_4,K_1,V_1)
$$

---

<a id="origin-7872"></a>
## 125. 共享 K/V，不代表 Attention 结果相同

这一点非常重要。

虽然：

$$
Q_1,Q_2,Q_3,Q_4
$$

共用了：

$$
K_1,V_1
$$

但：

$$
Q_1\neq Q_2\neq Q_3\neq Q_4
$$

因此：

$$
Q_1K_1^T
$$

和：

$$
Q_2K_1^T
$$

一般并不相同。

即：

$$
Q_1K_1^T
\neq
Q_2K_1^T
$$

所以它们得到的：

$$
softmax\left(
\frac{QK^T}{\sqrt{d_k}}
\right)
$$

也不同。

因此最终读取 V 时的权重也不同。

例如：

$$
Attention_1
=
softmax
\left(
\frac{Q_1K^T}{\sqrt{d_k}}
\right)V
$$

而：

$$
Attention_2
=
softmax
\left(
\frac{Q_2K^T}{\sqrt{d_k}}
\right)V
$$

即使：

$$
K,V
$$

完全一样，只要：

$$
Q_1\neq Q_2
$$

通常就有：

$$
Attention_1\neq Attention_2
$$

所以：

> **GQA 共享的是 K/V 表示，而不是 Attention 权重，也不是最终 Attention 输出。**

---

<a id="origin-7974"></a>
## 126. 一个极简数学例子

假设两个 Query Head 共用一个 K：

$$
Q_1=[1,0]
$$

$$
Q_2=[0,1]
$$

而：

$$
K=
\begin{bmatrix}
1&0\\
0&1
\end{bmatrix}
$$

那么：

$$
Q_1K^T
=
[1,0]
$$

而：

$$
Q_2K^T
=
[0,1]
$$

显然：

$$
Q_1K^T
\neq
Q_2K^T
$$

虽然它们使用的是完全相同的 K。

这说明：

> 共享 K 并不意味着 Attention Score 一样。

因为不同 Query Head 的：

$$
Q
$$

本身仍然不同。

---

<a id="origin-8036"></a>
## 127. 所以 GQA 到底牺牲了什么？

从 MHA：

```text
Q1 → K1,V1
Q2 → K2,V2
```

变成 GQA：

```text
Q1 ─┐
    ├→ K1,V1
Q2 ─┘
```

意味着：

以前：

```text
Query 1
有自己的 Key/Value 表示空间

Query 2
也有自己的 Key/Value 表示空间
```

现在：

```text
两个 Query
必须共享同一套 Key/Value 表示空间
```

所以从理论上：

```text
GQA 的自由度
<
MHA
```

但是实践中发现：

> K/V Head 的数量适当减少，通常不会造成与计算、显存收益同等幅度的能力损失。

因此它成为现代大模型中很常见的设计。

---

<a id="origin-8088"></a>
## 128. 用一张图理解三者

```text
MHA
────────────────────────

Q1 ─────→ K1,V1
Q2 ─────→ K2,V2
Q3 ─────→ K3,V3
Q4 ─────→ K4,V4
Q5 ─────→ K5,V5
Q6 ─────→ K6,V6
Q7 ─────→ K7,V7
Q8 ─────→ K8,V8

8 Query Heads
8 KV Heads


GQA
────────────────────────

Q1 ─┐
Q2 ─┼────→ K1,V1
Q3 ─┤
Q4 ─┘

Q5 ─┐
Q6 ─┼────→ K2,V2
Q7 ─┤
Q8 ─┘

8 Query Heads
2 KV Heads


MQA
────────────────────────

Q1 ─┐
Q2 ─┤
Q3 ─┤
Q4 ─┤
Q5 ─┼────→ K1,V1
Q6 ─┤
Q7 ─┤
Q8 ─┘

8 Query Heads
1 KV Head
```

---

<a id="origin-8142"></a>
## 129. 最核心的三个数字

学习 GQA 时，经常会看到：

```python
n_heads
n_kv_heads
n_rep
```

它们分别表示：

<a id="origin-8154"></a>
### 129.1 Query Head 数量

$$
n\_heads=N_Q
$$

例如：

```python
n_heads = 32
```

表示有：

$$
32
$$

个 Query Head。

---

<a id="origin-8176"></a>
#### 129.1.1 KV Head 数量

$$
n\_kv\_heads=N_{KV}
$$

例如：

```python
n_kv_heads = 8
```

表示只有：

$$
8
$$

组 K/V Head。

---

<a id="origin-8198"></a>
#### 129.1.2 每个 KV Head 被复制多少次

通常：

$$
n_{rep}
=
\frac{n_{heads}}
{n_{kv\_heads}}
$$

例如：

$$
n_{rep}
=
\frac{32}{8}
=
4
$$

意味着：

> 一个 KV Head 服务 4 个 Query Head。

也可以理解为后续计算 Attention 时，需要在逻辑上将每个 K/V Head 扩展给 4 个 Query Head 使用。

---

<a id="origin-8227"></a>
## 130. GQA 与 KV Cache 的完整逻辑链

整个故事可以串成：

```text
自回归生成
    ↓
历史 token 的 K/V 会反复使用
    ↓
使用 KV Cache
    ↓
避免重复计算 K/V
    ↓
但 MHA 中每个 Head 都有自己的 K/V
    ↓
KV Cache 占用大量显存
    ↓
能不能减少 KV Head？
    ↓
MQA：所有 Query 共用一个 KV Head
    ↓
缓存很小，但共享比较激进
    ↓
GQA：多个 Query Head 分组共享 KV Head
    ↓
在表达能力、显存和推理速度之间折中
```

---

<a id="origin-8257"></a>
## 131. 最终总结

GQA 最核心的思想可以压缩成一句话：

> **保留较多的 Query Head，但减少 KV Head，让多个 Query Head 分组共享 K/V，从而显著减少 KV Cache。**

传统 MHA：

$$
N_Q=N_{KV}
$$

MQA：

$$
N_{KV}=1
$$

GQA：

$$
1<N_{KV}<N_Q
$$

例如：

$$
N_Q=32
$$

$$
N_{KV}=8
$$

那么：

$$
n_{rep}
=
\frac{32}{8}
=
4
$$

即：

> 每 4 个 Query Head 共享一组 K/V。

因此可以把 GQA 理解成：

$$
\boxed{
MHA
\rightarrow
GQA
\rightarrow
MQA
}
$$

对应：

$$
\boxed{
KV\ Head数量逐渐减少
}
$$

以及：

$$
\boxed{
KV\ Cache逐渐减小
}
$$

最终 GQA 想解决的核心问题就是：

$$
\boxed{
在尽量保留多头注意力表达能力的同时，
显著降低 KV Cache 的显存和访存开销
}
$$

---

<a id="origin-8344"></a>
## 132. GQA 中 Repeat 的实现原理：为什么 K/V 要 Repeat？它真的复制了很多份吗？

前面已经知道，GQA（Grouped Query Attention）的核心思想是：

> **Query Head 保持较多，而多个 Query Head 共享同一个 KV Head。**

例如：

\[
N_Q=8
\]

但是只有：

\[
N_{KV}=2
\]

那么：

\[
n_{rep}
=
\frac{N_Q}{N_{KV}}
=
\frac{8}{2}
=
4
\]

也就是说：

> 每一个 KV Head 要被 4 个 Query Head 共同使用。

这就是 GQA 中经常看到的：

```python
n_rep = n_heads // n_kv_heads
```

以及：

```python
repeat_kv(...)
```

的来源。

---

<a id="origin-8394"></a>
## 133. 先看普通 MHA 为什么不需要 Repeat

假设普通 Multi-Head Attention 中有：

\[
N_Q=N_K=N_V=8
\]

那么：

```text
Q Head 0 → K Head 0 → V Head 0
Q Head 1 → K Head 1 → V Head 1
Q Head 2 → K Head 2 → V Head 2
Q Head 3 → K Head 3 → V Head 3
Q Head 4 → K Head 4 → V Head 4
Q Head 5 → K Head 5 → V Head 5
Q Head 6 → K Head 6 → V Head 6
Q Head 7 → K Head 7 → V Head 7
```

因此：

\[
Q
\]

的 Head 数量是 8，

\[
K
\]

也是 8，

\[
V
\]

也是 8。

假设忽略 Batch：

\[
Q\in\mathbb{R}^{L\times8\times d_{head}}
\]

\[
K\in\mathbb{R}^{L\times8\times d_{head}}
\]

\[
V\in\mathbb{R}^{L\times8\times d_{head}}
\]

Head 数量天然一一对应，所以可以直接做 Attention。

---

<a id="origin-8453"></a>
## 134. 但是 GQA 中 Head 数量对不上

现在使用 GQA。

假设：

\[
N_Q=8
\]

但是：

\[
N_{KV}=2
\]

那么 Q 的形状是：

\[
Q\in\mathbb{R}^{L\times8\times d_{head}}
\]

而 K/V 的形状只有：

\[
K'\in\mathbb{R}^{L\times2\times d_{head}}
\]

\[
V'\in\mathbb{R}^{L\times2\times d_{head}}
\]

也就是说：

```text
Q：

Q0
Q1
Q2
Q3
Q4
Q5
Q6
Q7


K/V：

K0 V0
K1 V1
```

问题出现了：

> 8 个 Query Head 怎么和 2 个 KV Head 做 Attention？

答案就是：

\[
\boxed{Repeat}
\]

---

<a id="origin-8518"></a>
## 135. Repeat 的本质不是产生新的 K/V

这里非常重要。

GQA 中真正计算出来的 KV Head 仍然只有：

\[
2
\]

个：

```text
K0
K1
```

以及：

```text
V0
V1
```

Repeat 并不是再通过：

\[
W_K
\]

重新计算 8 次 K。

也不是再通过：

\[
W_V
\]

重新计算 8 次 V。

而只是说：

> **让同一个 K/V Head 被多个 Query Head 使用。**

例如：

```text
Q0 ─┐
Q1 ─┤
Q2 ─┼──→ K0 / V0
Q3 ─┘

Q4 ─┐
Q5 ─┤
Q6 ─┼──→ K1 / V1
Q7 ─┘
```

因此：

\[
Q_0,Q_1,Q_2,Q_3
\]

共享：

\[
K_0,V_0
\]

而：

\[
Q_4,Q_5,Q_6,Q_7
\]

共享：

\[
K_1,V_1
\]

---

<a id="origin-8602"></a>
## 136. 为什么代码里看起来真的把 K/V 复制了？

为了让普通的多头 Attention 矩阵运算比较方便，我们通常希望：

\[
Q,K,V
\]

的 Head 维度能够对齐。

原来：

\[
Q:
[L,8,d_{head}]
\]

而：

\[
K':
[L,2,d_{head}]
\]

所以可以在逻辑上把：

\[
K'
\]

变成：

\[
K:
[L,8,d_{head}]
\]

例如原来的：

```text
K0
K1
```

经过 Repeat 后变成：

```text
K0
K0
K0
K0

K1
K1
K1
K1
```

同理：

```text
V0
V1
```

变成：

```text
V0
V0
V0
V0

V1
V1
V1
V1
```

这样 Head 数量就从：

\[
2
\]

变成：

\[
8
\]

于是：

\[
Q,K,V
\]

都可以按照 8 个 Head 来进行普通的 Attention 运算。

---

<a id="origin-8703"></a>
## 137. 一个完整的维度例子

假设：

\[
B=1
\]

序列长度：

\[
L=3
\]

Query Head 数：

\[
N_Q=8
\]

KV Head 数：

\[
N_{KV}=2
\]

每个 Head 的维度：

\[
d_{head}=128
\]

那么 Q 的形状：

\[
Q:
[1,3,8,128]
\]

但是原始 K/V：

\[
K':
[1,3,2,128]
\]

\[
V':
[1,3,2,128]
\]

因为：

\[
n_{rep}
=
\frac{8}{2}
=
4
\]

所以每个 KV Head 要服务 4 个 Query Head。

经过逻辑 Repeat：

\[
K:
[1,3,8,128]
\]

\[
V:
[1,3,8,128]
\]

于是 Head 数量就可以和：

\[
Q:
[1,3,8,128]
\]

对应起来。

---

<a id="origin-8789"></a>
## 138. Repeat 到底怎么映射？

假设 Query Head 编号为：

```text
0 1 2 3 4 5 6 7
```

KV Head 编号：

```text
0 1
```

因为：

\[
n_{rep}=4
\]

所以映射关系为：

```text
Query Head     KV Head

Q0             KV0
Q1             KV0
Q2             KV0
Q3             KV0

Q4             KV1
Q5             KV1
Q6             KV1
Q7             KV1
```

数学上可以写成：

\[
h_{KV}
=
\left\lfloor
\frac{h_Q}{n_{rep}}
\right\rfloor
\]

例如：

\[
h_Q=0
\]

则：

\[
h_{KV}
=
\left\lfloor\frac04\right\rfloor
=0
\]

所以：

\[
Q_0\rightarrow K_0,V_0
\]

对于：

\[
h_Q=3
\]

有：

\[
h_{KV}
=
\left\lfloor\frac34\right\rfloor
=0
\]

所以：

\[
Q_3\rightarrow K_0,V_0
\]

对于：

\[
h_Q=4
\]

则：

\[
h_{KV}
=
\left\lfloor\frac44\right\rfloor
=1
\]

所以：

\[
Q_4\rightarrow K_1,V_1
\]


<a id="origin-8899"></a>
## 139. 为什么 RoPE 通常在 Repeat 之前？

以 K 为例：

```text
K'
↓
RoPE
↓
Repeat
```

而不是：

```text
K'
↓
Repeat
↓
每一份再做 RoPE
```

原因很简单。

例如：

\[
K_0
\]

会被：

\[
Q_0,Q_1,Q_2,Q_3
\]

共享。

这四个 Query Head 使用的是同一个位置上的：

\[
K_0
\]

因此只需要先对：

\[
K_0
\]

做一次 RoPE：

\[
K_0'
=
RoPE(K_0)
\]

然后让：

\[
Q_0,Q_1,Q_2,Q_3
\]

共享这个已经加入位置信息的 K 即可。

没必要：

```text
复制 4 次
↓
RoPE 4 次
```

这样会产生无意义的重复计算。

因此更加合理的顺序是：

```text
生成较少的 K
      ↓
    RoPE
      ↓
逻辑上共享给多个 Q Head
```

---

<a id="origin-8987"></a>
## 140. V 为什么不需要 RoPE，但是也需要 Repeat？

因为 V 虽然不参与：

\[
QK^T
\]

所以不需要 RoPE。

但是最终 Attention 还是要计算：

\[
O=AV
\]

不同 Query Head 得到自己的 Attention Weight 后，需要读取自己所属 KV Group 的 V。

因此：

```text
Q0 Q1 Q2 Q3
```

都要读取：

```text
V0
```

而：

```text
Q4 Q5 Q6 Q7
```

都要读取：

```text
V1
```

所以 V 同样需要进行：

\[
\boxed{\text{共享映射}}
\]

也就是图中所谓的 Repeat。

---

<a id="origin-9039"></a>
## 141. GQA、Repeat 与 KV Cache：训练阶段和推理阶段到底分别怎么工作？

这里最容易混淆的是三个概念：

\[
\boxed{GQA}
\]

\[
\boxed{Repeat}
\]

\[
\boxed{KV\ Cache}
\]

它们之间有关系，但不是一回事。

最核心的一句话是：

> **GQA 和 Repeat 属于 Attention 本身的结构，因此训练和推理阶段都会存在；KV Cache 主要是自回归推理阶段为了避免重复计算历史 K/V 而使用的优化机制。**

---

<a id="origin-9063"></a>
## 142. 先假设一个 GQA

假设：

\[
N_Q=8
\]

也就是有 8 个 Query Head。

但是：

\[
N_{KV}=2
\]

也就是只有 2 个 KV Head。

因此：

\[
n_{rep}
=
\frac{N_Q}{N_{KV}}
=
\frac{8}{2}
=
4
\]

这表示：

> 每一个 KV Head 要被 4 个 Query Head 共享。

对应关系就是：

```text
Q0 Q1 Q2 Q3 → K0 / V0

Q4 Q5 Q6 Q7 → K1 / V1
```

所以：

\[
\boxed{
GQA 的本质：
多个 Query Head 共享一个 KV Head
}
\]

---

<a id="origin-9116"></a>
## 143. 训练阶段也会使用 GQA

假设训练序列是：

```text
I love AI very much
```

序列长度：

\[
L=5
\]

训练时不会一个 token 一个 token 地送进去，而是：

> **整个序列一次性送进 Transformer。**

因此模型一次性计算所有 token 的 Q、K、V。

Query 的形状：

\[
Q
\in
\mathbb{R}^{B\times L\times8\times d_{head}}
\]

而 K/V：

\[
K'
\in
\mathbb{R}^{B\times L\times2\times d_{head}}
\]

\[
V'
\in
\mathbb{R}^{B\times L\times2\times d_{head}}
\]

注意：

> 即使在训练阶段，模型真正生成的 KV Head 仍然只有 2 个，而不是 8 个。

也就是说：

```text
Q：

Q0
Q1
Q2
Q3
Q4
Q5
Q6
Q7


K/V：

K0 V0
K1 V1
```

---

<a id="origin-9185"></a>
## 144. 训练阶段仍然需要 Repeat

因为：

\[
Q
\]

有 8 个 Head，

但是：

\[
K,V
\]

只有 2 个 Head。

为了做 Attention，需要建立对应关系：

```text
Q0 → K0 / V0
Q1 → K0 / V0
Q2 → K0 / V0
Q3 → K0 / V0

Q4 → K1 / V1
Q5 → K1 / V1
Q6 → K1 / V1
Q7 → K1 / V1
```

所以训练时仍然存在：

\[
\boxed{Repeat}
\]

或者更准确地说：

\[
\boxed{KV\ Head\ Sharing / Mapping}
\]

有些代码会显式写：

```python
repeat_kv(k, n_rep=4)
repeat_kv(v, n_rep=4)
```

逻辑上变成：

```text
K0 K0 K0 K0 K1 K1 K1 K1

V0 V0 V0 V0 V1 V1 V1 V1
```

这样就可以与：

```text
Q0 Q1 Q2 Q3 Q4 Q5 Q6 Q7
```

一一对应。

---

<a id="origin-9254"></a>
## 145. 但是训练阶段通常不需要 KV Cache

这才是和推理阶段最大的区别。

推理阶段是逐 token 生成的。

例如第一轮：

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

然后预测：

```text
AI
```

下一轮：

```text
I love AI
```

如果没有 KV Cache，就会重新计算：

```text
K_I
V_I

K_love
V_love
```

这显然是重复计算。

所以推理阶段会把历史 K/V 保存下来：

```text
KV Cache

I     → K_I,    V_I
love  → K_love, V_love
```

下一轮只计算新的：

```text
K_AI
V_AI
```

这就是 KV Cache。

---

<a id="origin-9320"></a>
## 146. 为什么训练阶段不需要这么做？

训练时，例如整个样本：

```text
I love AI very much
```

会一次性全部输入模型。

也就是说：

```text
I
love
AI
very
much
```

同时进入 Transformer。

模型一次 forward 就会得到：

\[
Q_I,Q_{love},Q_{AI},Q_{very},Q_{much}
\]

同时得到：

\[
K_I,K_{love},K_{AI},K_{very},K_{much}
\]

以及：

\[
V_I,V_{love},V_{AI},V_{very},V_{much}
\]

所以训练时根本不存在：

> 下一轮生成 AI 时，又重新计算 I 和 love 的 K/V。

因为训练不是这样逐 token forward 的。

训练是：

\[
\boxed{
\text{整段序列一次并行计算}
}
\]

因此不需要把上一“生成步”的 K/V 保存给下一步。

---

<a id="origin-9378"></a>
## 147. 训练一次看到整个序列，会不会偷看未来？

不会。

因为训练阶段仍然有：

\[
\boxed{Causal\ Mask}
\]

例如：

```text
I love AI very much
```

完整 Attention 的可见关系：

\[
\begin{array}{c|ccccc}
 & I & love & AI & very & much\\
\hline
I
&
\checkmark
&
\times
&
\times
&
\times
&
\times
\\
love
&
\checkmark
&
\checkmark
&
\times
&
\times
&
\times
\\
AI
&
\checkmark
&
\checkmark
&
\checkmark
&
\times
&
\times
\\
very
&
\checkmark
&
\checkmark
&
\checkmark
&
\checkmark
&
\times
\\
much
&
\checkmark
&
\checkmark
&
\checkmark
&
\checkmark
&
\checkmark
\end{array}
\]

虽然所有 token 一次性进入 GPU，

但是：

```text
I
```

只能看到：

```text
I
```

而：

```text
love
```

只能看到：

```text
I love
```

所以：

\[
\boxed{
\text{训练可以并行计算整个序列}
}
\]

同时：

\[
\boxed{
\text{又可以保证每个 token 看不到未来}
}
\]

---

<a id="origin-9506"></a>
## 148. 训练阶段完整的数据流

假设：

\[
N_Q=8
\]

\[
N_{KV}=2
\]

整个流程可以写成：

```text
整个训练序列 X
        ↓
     RMSNorm
        ↓
 ┌──────┼──────┐
 ↓      ↓      ↓
W_Q    W_K    W_V
 ↓      ↓      ↓
8 Q     2 K     2 V
Heads   Heads   Heads
 ↓      ↓
Norm   Norm
 ↓      ↓
RoPE   RoPE
        ↓
Repeat / KV Head Mapping
        ↓
2 个 KV Head
服务 8 个 Query Head
        ↓
QK^T
        ↓
Causal Mask
        ↓
Softmax
        ↓
× V
        ↓
Attention Output
        ↓
后续网络
        ↓
Loss
        ↓
Backward
```

所以训练阶段：

\[
\boxed{
GQA\ 存在
}
\]

\[
\boxed{
Repeat\ 存在
}
\]

但是通常没有：

\[
\boxed{
跨生成步骤持续保存的 KV Cache
}
\]

---

<a id="origin-9582"></a>
## 149. 那训练时的 K/V 去哪里了？

训练时 K/V 当然也会暂时保存在显存中。

因为后面反向传播需要它们。

例如：

\[
O
=
Softmax(QK^T)V
\]

最后得到 Loss：

\[
\mathcal L
\]

反向传播时，需要计算：

\[
\frac{\partial\mathcal L}{\partial Q}
\]

\[
\frac{\partial\mathcal L}{\partial K}
\]

\[
\frac{\partial\mathcal L}{\partial V}
\]

然后继续求：

\[
\frac{\partial\mathcal L}{\partial W_Q}
\]

\[
\frac{\partial\mathcal L}{\partial W_K}
\]

\[
\frac{\partial\mathcal L}{\partial W_V}
\]

因此训练阶段的 Q/K/V 会作为：

\[
\boxed{Activation}
\]

暂时保存。

但这和：

\[
\boxed{KV\ Cache}
\]

不是一回事。

---

<a id="origin-9648"></a>
## 150. Activation 和 KV Cache 有什么区别？

训练阶段：

\[
\boxed{
Q/K/V 是为了反向传播而暂时保存的 Activation
}
\]

流程：

```text
Forward
   ↓
保存部分 Activation
   ↓
Loss
   ↓
Backward
   ↓
Optimizer.step()
   ↓
这批数据的 Activation 可以释放
```

下一批数据会重新计算。

---

推理阶段：

\[
\boxed{
K/V 是为了下一次生成继续使用而保存的 Cache
}
\]

流程：

```text
生成 token 1
   ↓
K/V 保存

生成 token 2
   ↓
历史 K/V 继续保存

生成 token 3
   ↓
历史 K/V 继续保存

...
```

所以：

| 对比 | 训练 | 自回归推理 |
|---|---|---|
| Q/K/V 是否计算 | 是 | 是 |
| GQA 是否存在 | 是 | 是 |
| Repeat 是否存在 | 是 | 是 |
| K/V 是否参与反向传播 | 是 | 否 |
| 是否跨生成步骤保存历史 K/V | 通常否 | 是 |
| 保存 K/V 的主要目的 | Backward | 避免重复计算 |

---

<a id="origin-9717"></a>
## 151. Repeat 在训练时怎么反向传播？

这是 GQA 一个非常重要的地方。

假设：

```text
Q0 Q1 Q2 Q3
      ↓
共享 K0 / V0
```

正向传播：

\[
O_0
=
Attention(Q_0,K_0,V_0)
\]

\[
O_1
=
Attention(Q_1,K_0,V_0)
\]

\[
O_2
=
Attention(Q_2,K_0,V_0)
\]

\[
O_3
=
Attention(Q_3,K_0,V_0)
\]

虽然它们共享同一个：

\[
K_0,V_0
\]

但是这四个 Query Head 都会对共享的 K/V 产生梯度。

反向传播时：

\[
\frac{\partial\mathcal L}{\partial K_0}
\]

会接收所有共享 Query Head 的梯度贡献。

可以粗略写成：

\[
\boxed{
\frac{\partial\mathcal L}{\partial K_0}
=
\frac{\partial\mathcal L_0}{\partial K_0}
+
\frac{\partial\mathcal L_1}{\partial K_0}
+
\frac{\partial\mathcal L_2}{\partial K_0}
+
\frac{\partial\mathcal L_3}{\partial K_0}
}
\]

同样：

\[
\boxed{
\frac{\partial\mathcal L}{\partial V_0}
=
\frac{\partial\mathcal L_0}{\partial V_0}
+
\frac{\partial\mathcal L_1}{\partial V_0}
+
\frac{\partial\mathcal L_2}{\partial V_0}
+
\frac{\partial\mathcal L_3}{\partial V_0}
}
\]

所以：

> 一个 KV Head 虽然被多个 Query Head 共享，但是训练时它会吸收多个 Query Head 的共同学习信号。

---

<a id="origin-9809"></a>
## 152. 如果代码用 expand()，梯度怎么办？

例如：

```python
K_repeat = K.expand(...)
```

逻辑上：

```text
K0
K0
K0
K0
```

这四个位置实际上都来自同一个：

\[
K_0
\]

PyTorch Autograd 会自动处理。

反向传播时：

```text
Q0 → loss0 ─┐
Q1 → loss1 ─┤
Q2 → loss2 ─┼──→ K0
Q3 → loss3 ─┘
```

多个分支的梯度会自动累加回原始：

\[
K_0
\]

所以不需要人工处理。

这就是共享参数、共享张量在自动微分中的正常机制。

---

<a id="origin-9855"></a>
## 153. 为什么训练不采用推理那种逐 token + KV Cache？

因为训练最重要的是：

\[
\boxed{
并行
}
\]

假设序列长度：

\[
L=4096
\]

如果像推理一样：

```text
token 1
   ↓
token 2
   ↓
token 3
   ↓
...
   ↓
token 4096
```

逐个 forward，

那么 GPU 的并行能力就无法充分利用。

训练真正做的是：

```text
4096 个 token
      ↓
一次全部送入 GPU
      ↓
一次性生成全部 Q/K/V
      ↓
一次性计算完整的 Causal Attention
```

所以训练时：

\[
\boxed{
\text{序列维度可以并行}
}
\]

而推理时：

\[
x_{t+1}
\]

没有生成出来之前，

模型根本不知道下一步输入是什么。

所以推理必须：

```text
生成一个 token
↓
再生成下一个
↓
再生成下一个
```

因此才需要：

\[
\boxed{KV\ Cache}
\]

---

<a id="origin-9937"></a>
## 154. 用 `I love AI` 比较训练和推理

<a id="origin-9939"></a>
### 154.1 训练阶段

一次性输入：

```text
<BOS> I love AI
```

可以同时训练：

```text
<BOS>          → I

<BOS> I        → love

<BOS> I love   → AI

...
```

一次 forward 直接计算：

```text
Q_BOS
Q_I
Q_love
Q_AI
```

以及：

```text
K_BOS
K_I
K_love
K_AI
```

和：

```text
V_BOS
V_I
V_love
V_AI
```

然后依靠 Causal Mask 保证每一个位置只能看前文。

因此：

\[
\boxed{
训练阶段不需要 KV Cache
}
\]

---

<a id="origin-9998"></a>
### 154.2 推理阶段

初始输入：

```text
<BOS> I love
```

预测：

```text
AI
```

第一轮得到：

```text
K_BOS,   V_BOS

K_I,     V_I

K_love,  V_love
```

保存进：

```text
KV Cache
```

第二轮只需要计算新 token `AI` 的：

\[
Q_{AI}
\]

\[
K_{AI}
\]

\[
V_{AI}
\]

然后：

\[
Q_{AI}
\]

查询：

\[
K_{BOS},K_I,K_{love},K_{AI}
\]

这里历史：

\[
K_{BOS},K_I,K_{love}
\]

都直接从 KV Cache 中读取。

所以：

\[
\boxed{
推理阶段才真正体现 KV Cache 的价值
}
\]

---

<a id="origin-10072"></a>
## 155. GQA 对训练阶段有什么收益？

虽然训练阶段通常不用 KV Cache，

但 GQA 仍然可以减少 K/V 相关参数和计算。

例如 MHA：

\[
N_Q=32
\]

\[
N_{KV}=32
\]

而 GQA：

\[
N_Q=32
\]

\[
N_{KV}=8
\]

假设：

\[
d_{head}=128
\]

那么 MHA 中：

\[
W_K
\]

输出维度为：

\[
32\times128
=
4096
\]

而 GQA 中：

\[
W_K
\]

只需要输出：

\[
8\times128
=
1024
\]

所以：

\[
W_K
\]

和：

\[
W_V
\]

的参数量都会更小。

因此训练时也能减少一部分：

- 参数量
- K/V Projection 计算
- Activation 大小
- 显存占用

---

<a id="origin-10155"></a>
## 156. GQA 对推理阶段的收益更明显

推理阶段最重要的收益是：

\[
\boxed{
KV\ Cache\ 更小
}
\]

如果：

\[
N_Q=32
\]

传统 MHA：

\[
N_{KV}=32
\]

而 GQA：

\[
N_{KV}=8
\]

那么 KV Cache 大约变成：

\[
\frac{8}{32}
=
\frac14
\]

也就是：

\[
25\%
\]

所以理论上对应的 KV Cache 可以减少：

\[
75\%
\]

因此：

\[
\boxed{
GQA
\rightarrow
KV\ Head减少
\rightarrow
KV\ Cache减少
\rightarrow
推理显存与访存开销降低
}
\]

---

<a id="origin-10219"></a>
## 157. GQA 训练过程中 `repeat` 是如何参与反向传播和求导的？

---

<a id="origin-10223"></a>
## 158. 先明确我们到底在研究什么

假设一个 GQA 模型有：

```math
n_q = 4
```

个 Query Head，但是只有：

```math
n_{kv}=2
```

个 KV Head。

因此：

```math
n_{\text{rep}}
=
\frac{n_q}{n_{kv}}
=
\frac42
=
2
```

也就是说：

> 每一个 K/V Head 要给两个 Query Head 使用。

结构是：

```text
Q1 ─┐
    ├── K1, V1
Q2 ─┘

Q3 ─┐
    ├── K2, V2
Q4 ─┘
```

---

<a id="origin-10269"></a>
## 159. 为什么代码里会出现 repeat？

假设经过线性投影以后：

```text
Query：

Q1
Q2
Q3
Q4
```

一共有 4 个 Query Head。

但是 Key 只有：

```text
K1
K2
```

Value 只有：

```text
V1
V2
```

如果代码要使用普通的多头 Attention 形式：

```math
Q^{(h)}K^{(h)T}
```

那么 Query Head 和 KV Head 数量需要对得上。

于是代码把：

```text
K1
K2
```

变成：

```text
K1
K1
K2
K2
```

Value 同样：

```text
V1
V1
V2
V2
```

这就是所谓：

```python
repeat_kv(...)
```

于是前向传播看起来变成：

```text
Q1 → K1, V1

Q2 → K1, V1

Q3 → K2, V2

Q4 → K2, V2
```

---

<a id="origin-10351"></a>
## 160. 最关键的一点：repeat 不是产生了新的可训练 K

这里特别容易误解。

经过：

```text
K1
↓ repeat
K1a
K1b
```

以后，不要理解成：

```text
K1a 是一套新的参数

K1b 又是一套新的参数
```

实际上：

```math
K_{1a}=K_1
```

```math
K_{1b}=K_1
```

它们都来自**同一个原始 K1**。

只是前向计算时：

```text
同一个 K1

同时被 Head 1 使用
同时被 Head 2 使用
```

所以更准确应该画成：

```text
                  ┌──→ Head 1
K1 ───────────────┤
                  └──→ Head 2
```

而不是：

```text
K1 → 复制一个新的可训练 K1a
K1 → 再复制一个新的可训练 K1b
```

---

<a id="origin-10410"></a>
## 161. repeat 本身没有任何参数

这一点非常重要。

例如：

```python
k = repeat_kv(k, n_rep=2)
```

`repeat` 本身没有：

```text
weight
bias
```

也没有什么需要学习的参数。

它本质上只是一个张量操作：

```text
输入：

[K1, K2]

↓

repeat

输出：

[K1, K1, K2, K2]
```

所以训练真正需要学习的仍然是：

```math
W_K
```

以及：

```math
W_V
```

而不是：

```text
repeat
```

---

<a id="origin-10465"></a>
## 162. 先只看第一个 KV Group

为了把问题讲透，我们暂时只看：

```text
Q1
Q2
```

共享：

```text
K1
V1
```

也就是：

```text
             ┌── Q1
K1, V1 ──────┤
             └── Q2
```

前向传播：

<a id="origin-10491"></a>
### 162.1 Head 1

```math
S_1
=
Q_1K_1^T
```

经过 Softmax：

```math
A_1
=
\operatorname{softmax}(S_1)
```

然后：

```math
O_1
=
A_1V_1
```

---

<a id="origin-10517"></a>
### 162.2 Head 2

同一个：

```math
K_1
```

和：

```math
V_1
```

又被 Head 2 使用：

```math
S_2
=
Q_2K_1^T
```

```math
A_2
=
\operatorname{softmax}(S_2)
```

```math
O_2
=
A_2V_1
```

所以：

```text
                 K1
              ↙      ↘
          Head 1    Head 2

Q1 × K1ᵀ            Q2 × K1ᵀ
   ↓                   ↓
  A1                  A2
   ↓                   ↓
A1 × V1             A2 × V1
   ↓                   ↓
  O1                  O2
```

---

<a id="origin-10569"></a>
## 163. 最终 Loss 同时依赖 O1 和 O2

假设所有 Head 的结果最后经过：

```text
Concat
↓
W_O
↓
后续网络
↓
Cross Entropy
```

得到：

```math
L
```

那么：

```math
L
```

同时依赖：

```math
O_1
```

和：

```math
O_2
```

也就是说：

```text
               O1 ───┐
                     ├──→ 最终 Loss
               O2 ───┘
```

反向传播时：

```text
Loss
 ↓
 ├──→ O1
 │
 └──→ O2
```

于是两个 Head 都会产生自己的梯度。

---

<a id="origin-10629"></a>
## 164. 先看 V1 的梯度

我们有：

```math
O_1=A_1V_1
```

以及：

```math
O_2=A_2V_1
```

注意：

> 两个式子里出现的是同一个 \(V_1\)。

因此 Loss 对 \(V_1\) 的梯度，必须考虑两条路径。

也就是：

```math
\frac{\partial L}{\partial V_1}
=
\frac{\partial L}{\partial O_1}
\frac{\partial O_1}{\partial V_1}
+
\frac{\partial L}{\partial O_2}
\frac{\partial O_2}{\partial V_1}
```

因为：

```math
O_1=A_1V_1
```

所以：

```math
\frac{\partial O_1}{\partial V_1}
```

对应：

```math
A_1
```

而：

```math
O_2=A_2V_1
```

对应：

```math
A_2
```

因此可以粗略写成：

```math
\boxed{
\frac{\partial L}{\partial V_1}
=
A_1^T
\frac{\partial L}{\partial O_1}
+
A_2^T
\frac{\partial L}{\partial O_2}
}
```

最重要的是这里的：

```math
+
```

也就是说：

> **两个 Query Head 对同一个 V Head 的梯度，会加起来。**

---

<a id="origin-10717"></a>
## 165. 用计算图看就特别直观

前向：

```text
                 V1
               /    \
              /      \
             ↓        ↓
           Head1    Head2
             ↓        ↓
            O1        O2
              \      /
               \    /
                Loss
```

反向：

```text
                Loss
               /    \
              ↓      ↓
         dL/dO1    dL/dO2
              \      /
               \    /
                ↓  ↓
                  V1
```

所以：

```math
\boxed{
\nabla V_1
=
\nabla V_{1,\text{from Head1}}
+
\nabla V_{1,\text{from Head2}}
}
```

---

<a id="origin-10761"></a>
## 166. repeat 在这个过程中到底干了什么？

假设代码前向传播的时候先：

```text
原始 V：

[V1, V2]
```

然后：

```python
repeat_kv(V)
```

得到：

```text
[V1a, V1b, V2a, V2b]
```

其中：

```math
V_{1a}=V_1
```

```math
V_{1b}=V_1
```

Head 1 使用：

```text
V1a
```

Head 2 使用：

```text
V1b
```

反向传播时，假设得到：

```math
\frac{\partial L}{\partial V_{1a}}
=
G_a
```

以及：

```math
\frac{\partial L}{\partial V_{1b}}
=
G_b
```

那么 `repeat` 的 backward 做的事情就是：

```math
\boxed{
\frac{\partial L}{\partial V_1}
=
G_a+G_b
}
```

也就是说：

```text
前向：

            V1
           /  \
          ↓    ↓
        V1a   V1b


反向：

        Ga     Gb
          \   /
           \ /
            ↓
         Ga + Gb
            ↓
           V1
```

---

<a id="origin-10855"></a>
## 167. 这是理解 repeat 求导最核心的一条公式

假设：

```math
y_1=x
```

```math
y_2=x
```

也就是：

```text
x
↓ repeat
[x, x]
```

Loss：

```math
L=L(y_1,y_2)
```

因为：

```math
y_1=x
```

并且：

```math
y_2=x
```

根据链式法则：

```math
\frac{\partial L}{\partial x}
=
\frac{\partial L}{\partial y_1}
\frac{\partial y_1}{\partial x}
+
\frac{\partial L}{\partial y_2}
\frac{\partial y_2}{\partial x}
```

而：

```math
\frac{\partial y_1}{\partial x}=1
```

```math
\frac{\partial y_2}{\partial x}=1
```

所以：

```math
\boxed{
\frac{\partial L}{\partial x}
=
\frac{\partial L}{\partial y_1}
+
\frac{\partial L}{\partial y_2}
}
```

这就是：

<a id="origin-10929"></a>
## 168. repeat 的反向传播本质

---

<a id="origin-10933"></a>
## 169. 给一个最简单的数字例子

假设：

```math
x=3
```

repeat 两次：

```math
y_1=x
```

```math
y_2=x
```

所以：

```math
y_1=3
```

```math
y_2=3
```

假设 Loss：

```math
L=y_1^2+2y_2^2
```

因为：

```math
y_1=x
```

```math
y_2=x
```

所以实际上：

```math
L=x^2+2x^2
```

即：

```math
L=3x^2
```

直接求导：

```math
\frac{\partial L}{\partial x}
=
6x
```

当：

```math
x=3
```

得到：

```math
\frac{\partial L}{\partial x}=18
```

---

从 repeat 的两条路径分别算：

第一条：

```math
\frac{\partial L}{\partial y_1}
=
2y_1
=
6
```

第二条：

```math
\frac{\partial L}{\partial y_2}
=
4y_2
=
12
```

于是：

```math
\frac{\partial L}{\partial x}
=
6+12
=
18
```

完全一样。

所以：

> **重复出去几条路径，反向传播回来时，这几条路径的梯度就加起来。**

---

<a id="origin-11051"></a>
## 170. 回到 GQA 的 K

现在看 Key。

Head 1：

```math
S_1=Q_1K_1^T
```

Head 2：

```math
S_2=Q_2K_1^T
```

注意：

```math
K_1
```

也被使用了两次。

所以：

```math
\frac{\partial L}{\partial K_1}
=
\frac{\partial L}{\partial K_1}
\bigg|_{\text{Head 1}}
+
\frac{\partial L}{\partial K_1}
\bigg|_{\text{Head 2}}
```

也就是：

```math
\boxed{
\nabla K_1
=
\nabla K_1^{(Q_1)}
+
\nabla K_1^{(Q_2)}
}
```

---

<a id="origin-11101"></a>
## 171. 暂时忽略 Softmax，可以更容易看出来

先假设：

```math
S_1=Q_1K_1^T
```

Loss 对：

```math
S_1
```

传回一个梯度：

```math
G_1
=
\frac{\partial L}{\partial S_1}
```

那么：

```math
\frac{\partial L}{\partial K_1}
\bigg|_{\text{Head 1}}
=
G_1^TQ_1
```

同样 Head 2：

```math
G_2
=
\frac{\partial L}{\partial S_2}
```

产生：

```math
\frac{\partial L}{\partial K_1}
\bigg|_{\text{Head 2}}
=
G_2^TQ_2
```

因为两个 Head 使用的是同一个：

```math
K_1
```

所以最终：

```math
\boxed{
\frac{\partial L}{\partial K_1}
=
G_1^TQ_1
+
G_2^TQ_2
}
```

---

<a id="origin-11169"></a>
## 172. Softmax 并不会改变这个“梯度相加”的原则

真实 Attention 当然还有：

```math
A_1
=
\operatorname{softmax}
\left(
\frac{Q_1K_1^T}{\sqrt{d}}
\right)
```

以及：

```math
A_2
=
\operatorname{softmax}
\left(
\frac{Q_2K_1^T}{\sqrt{d}}
\right)
```

Softmax 只是让：

```text
Loss
↓
O
↓
A
↓
S
↓
K
```

这条链更复杂。

但是最终仍然存在两条路径：

```text
                        ┌── Head 1 ──→ Loss
K1 ────────────────────┤
                        └── Head 2 ──→ Loss
```

因此链式法则一定得到：

```math
\boxed{
\frac{\partial L}{\partial K_1}
=
\left(
\frac{\partial L}{\partial K_1}
\right)_{\text{Head 1}}
+
\left(
\frac{\partial L}{\partial K_1}
\right)_{\text{Head 2}}
}
```

---

<a id="origin-11235"></a>
## 173. Query 的梯度为什么不会这样合并？

因为：

```text
Q1
```

和：

```text
Q2
```

本身就是两个独立 Query Head。

所以：

```text
Q1 → Head 1
```

以及：

```text
Q2 → Head 2
```

它们不是 repeat 出来的。

因此：

```math
\nabla Q_1
```

只沿 Head 1 回去。

而：

```math
\nabla Q_2
```

只沿 Head 2 回去。

结构：

```text
Q1 → Head1 → Loss
Q2 → Head2 → Loss
```

所以：

```text
Q1 有自己的梯度

Q2 有自己的梯度
```

不会先相加成一个 Query Head。

---

<a id="origin-11300"></a>
## 174. 这正是 GQA 和 MHA 训练上的核心区别之一

<a id="origin-11302"></a>
### 174.1 MHA

假设：

```text
Q1 → K1,V1

Q2 → K2,V2
```

那么：

```text
K1 只接收来自 Head 1 的梯度

K2 只接收来自 Head 2 的梯度
```

也就是：

```math
\nabla K_1
=
\nabla K_{1,\text{Head1}}
```

```math
\nabla K_2
=
\nabla K_{2,\text{Head2}}
```

---

<a id="origin-11336"></a>
### 174.2 GQA

变成：

```text
Q1 ─┐
    ├→ K1,V1
Q2 ─┘
```

那么：

```math
\nabla K_1
=
\nabla K_{1,\text{Head1}}
+
\nabla K_{1,\text{Head2}}
```

以及：

```math
\nabla V_1
=
\nabla V_{1,\text{Head1}}
+
\nabla V_{1,\text{Head2}}
```

这就是共享参数最典型的反向传播方式。

---

<a id="origin-11370"></a>
## 175. 但是 K1 本身也不是参数，它是 W_K 算出来的

这个地方还要再向前走一步。

真正被 optimizer 更新的并不是：

```math
K_1
```

本身。

而是：

```math
W_K
```

因为：

```math
K=XW_K
```

在 GQA 中，例如：

```math
W_K
```

只生成 2 个 KV Head。

假设：

```math
d_{\text{head}}=128
```

那么：

```math
W_K
\in
\mathbb R^{d_{\text{model}}\times(2\times128)}
```

先得到：

```text
K1
K2
```

然后才：

```text
K1 → repeat → Head 1、Head 2

K2 → repeat → Head 3、Head 4
```

---

<a id="origin-11433"></a>
## 176. 梯度如何最终回到 W_K？

完整链路：

```text
Loss
 ↓
Head 1        Head 2
 ↓               ↓
K1a            K1b
  \             /
   \           /
    梯度相加
       ↓
      K1
       ↓
      W_K
```

数学上：

```math
K_1=XW_K^{(1)}
```

所以：

```math
\frac{\partial L}{\partial W_K^{(1)}}
=
X^T
\frac{\partial L}{\partial K_1}
```

但是我们前面已经知道：

```math
\frac{\partial L}{\partial K_1}
=
G_{K1,\text{Head1}}
+
G_{K1,\text{Head2}}
```

所以：

```math
\boxed{
\frac{\partial L}{\partial W_K^{(1)}}
=
X^T
\left(
G_{K1,\text{Head1}}
+
G_{K1,\text{Head2}}
\right)
}
```

这才是真正 optimizer 最终用到的梯度。

---

<a id="origin-11496"></a>
## 177. W_V 完全同样

对于：

```math
V_1=XW_V^{(1)}
```

Head 1 和 Head 2 都使用这个 V：

```text
Head 1 → V1

Head 2 → V1
```

所以：

```math
\frac{\partial L}{\partial V_1}
=
G_{V1,\text{Head1}}
+
G_{V1,\text{Head2}}
```

然后：

```math
\boxed{
\frac{\partial L}{\partial W_V^{(1)}}
=
X^T
\left(
G_{V1,\text{Head1}}
+
G_{V1,\text{Head2}}
\right)
}
```

因此：

> 一个 KV Head 会根据它所服务的多个 Query Head 的共同需求进行训练。

---

<a id="origin-11543"></a>
## 178. 这其实解释了“共享 K/V 是怎么训练出来的”

很多人会有一个疑惑：

> Q1 和 Q2 需求不一样，共享 K1，K1 到底听谁的？

答案就是：

> **两个都听。**

因为：

```math
\nabla K_1
=
\nabla K_{1,\text{Head1}}
+
\nabla K_{1,\text{Head2}}
```

所以 K1 会朝着：

```text
同时有利于 Head 1
+
同时有利于 Head 2
```

的方向更新。

可以粗略理解成：

```text
Q1 告诉 K1：
“你这样表示对我更有用。”

Q2 也告诉 K1：
“我希望你这样表示。”

        ↓

两个梯度合并

        ↓

K1 的参数寻找一个
同时服务这一组 Query Head 的表示方式
```

这就是：

<a id="origin-11594"></a>
## 179. Grouped Query Attention 中“Grouped”的训练含义

---

<a id="origin-11598"></a>
## 180. 从单头 Attention 到 MQA：KV Cache、显存与表达能力详解

<a id="origin-11600"></a>
## 181. 先统一模型参数

为了方便理解，假设一个 Transformer 模型的：

```text
hidden_size = 4096
num_query_heads = 32
head_dim = 128
```

因为：

```math
32 \times 128 = 4096
```

也就是说，一个 token 的 hidden state 是：

```math
x\in\mathbb{R}^{4096}
```

后面我们比较：

1. 最早的单头 Attention
2. MHA
3. GQA
4. MQA

最重要的是分清：

```text
hidden size
```

和：

```text
单个 Attention Head 的维度
```

不是一回事。

---

<a id="origin-11645"></a>
## 182. 最早的单头 Attention 是什么？

最简单的 Self-Attention 中，只有：

```text
1 个 Query Head
1 个 Key Head
1 个 Value Head
```

输入：

```math
x\in\mathbb{R}^{4096}
```

经过：

```math
Q=xW_Q
```

```math
K=xW_K
```

```math
V=xW_V
```

得到：

```math
Q,K,V\in\mathbb{R}^{4096}
```

因此：

```text
Hidden State
4096维
   │
   ├── WQ → Q：4096维
   │
   ├── WK → K：4096维
   │
   └── WV → V：4096维
```

所以传统单头 Attention 中，一个 K 本身就是：

```math
4096\text{维}
```

一个 V 也是：

```math
4096\text{维}
```

---

<a id="origin-11708"></a>
## 183. 单头 Attention 不等于 MQA

这是非常容易混淆的一点。

因为：

```text
单头 Attention：
只有一个 K Head 和一个 V Head
```

而：

```text
MQA：
也只有一个 K Head 和一个 V Head
```

但它们并不是同一个东西。

真正区别在于 Query。

---

<a id="origin-11732"></a>
### 183.1 单头 Attention

```text
Q Head：1个
K Head：1个
V Head：1个
```

而且：

```text
Q：4096维
K：4096维
V：4096维
```

因此：

```math
\boxed{\text{Single Head}=1Q+1K+1V}
```

---

<a id="origin-11756"></a>
### 183.2 MQA

MQA 全称：

```text
Multi-Query Attention
```

关键词就是：

```text
Multi-Query
```

它有很多 Query Head。

例如：

```text
32 个 Query Head
```

但所有 Query Head 共用：

```text
1 个 K Head
1 个 V Head
```

因此：

```math
\boxed{\text{MQA}=32Q+1K+1V}
```

所以判断是不是 MQA 的关键不是：

> 是不是只有一个 K/V。

而是：

> **是不是多个 Query Head 共享同一组 K/V。**

---

<a id="origin-11801"></a>
## 184. 为什么 MQA 的 K/V 不是 4096 维？

这也是最关键的一个问题。

可能第一反应是：

> hidden size 明明是 4096，MQA 虽然只有一个 K/V，难道这个 K/V 不也是 4096 维吗？

答案是：

> **不是。**

因为 MQA 建立在多头 Attention 的结构之上。

我们有：

```text
32 个 Query Head
```

每个 Head：

```math
d_{head}=128
```

所以：

```math
32\times128=4096
```

Query 总宽度仍然是 4096：

```math
Q\in\mathbb{R}^{32\times128}
```

但是 K/V 只有一个 Head，所以：

```math
K\in\mathbb{R}^{1\times128}
```

```math
V\in\mathbb{R}^{1\times128}
```

也就是：

```text
Hidden State
4096维
   │
   ├──────── WQ ────────→ 4096维
   │                       ↓
   │                   32 × 128
   │
   ├──────── WK ────────→ 128维
   │                       ↓
   │                   1个 K Head
   │
   └──────── WV ────────→ 128维
                           ↓
                       1个 V Head
```

所以：

```math
\boxed{\text{MQA 中单个 K/V Head 只有 }128\text{ 维}}
```

而不是 4096 维。

---

<a id="origin-11878"></a>
## 185. 为什么 KV Cache 因此变小？

KV Cache 保存的不是：

```text
4096维的原始 hidden state
```

而是 Attention 投影以后得到的：

```text
K
V
```

---

<a id="origin-11895"></a>
### 185.1 单头 Attention

每个 token：

```math
K\in\mathbb{R}^{4096}
```

```math
V\in\mathbb{R}^{4096}
```

所以一个 token 需要缓存：

```math
4096+4096=8192
```

个数。

---

<a id="origin-11917"></a>
### 185.2 MQA

每个 token：

```math
K\in\mathbb{R}^{128}
```

```math
V\in\mathbb{R}^{128}
```

所以只需要缓存：

```math
128+128=256
```

个数。

因此：

```math
\frac{8192}{256}=32
```

也就是说：

```math
\boxed{\text{MQA 的 KV Cache 只有传统 4096 维单头的 }1/32}
```

---

<a id="origin-11951"></a>
## 186. MHA 又是什么情况？

MHA：

```text
Multi-Head Attention
```

拥有：

```text
32 个 Q Head
32 个 K Head
32 个 V Head
```

每个 Head 是：

```math
128\text{维}
```

所以：

```math
Q:
32\times128=4096
```

```math
K:
32\times128=4096
```

```math
V:
32\times128=4096
```

因此虽然每个 K Head 只有 128 维，但总共有 32 个：

```math
32\times128=4096
```

所以 MHA 每个 token 的 KV Cache：

```math
4096+4096=8192
```

个数。

和传统 4096 维单头 Attention 在这个例子里的 KV 总宽度是一样的。

---

<a id="origin-12008"></a>
## 187. GQA 是什么？

GQA：

```text
Grouped Query Attention
```

是 MHA 和 MQA 之间的折中。

例如：

```text
Query Head = 32
KV Head = 8
```

那么：

```math
Q:
32\times128=4096
```

而：

```math
K:
8\times128=1024
```

```math
V:
8\times128=1024
```

也就是说：

```text
32个 Query Head
分成8组

每4个 Query Head
共享一套 K/V
```

---

<a id="origin-12056"></a>
## 188. 四种结构放在一起

可以直接记成：

```text
传统单头 Attention
────────────────────
Q：1 × 4096
K：1 × 4096
V：1 × 4096
```

---

```text
MHA
────────────────────
Q：32 × 128
K：32 × 128
V：32 × 128
```

---

```text
GQA
────────────────────
Q：32 × 128
K：8 × 128
V：8 × 128
```

---

```text
MQA
────────────────────
Q：32 × 128
K：1 × 128
V：1 × 128
```

所以可以总结为：

| 方法           | Q Heads | KV Heads | 每个 Head 维度 | K 总宽度 | V 总宽度 |
| ------------ | ------: | -------: | ---------: | ----: | ----: |
| 单头 Attention |       1 |        1 |       4096 |  4096 |  4096 |
| MHA          |      32 |       32 |        128 |  4096 |  4096 |
| GQA          |      32 |        8 |        128 |  1024 |  1024 |
| MQA          |      32 |        1 |        128 |   128 |   128 |

---

<a id="origin-12109"></a>
## 189. 那 MQA 的 K/V 只有 128 维，信息量不是比传统单头小很多吗？

如果只看：

```text
单个 token 的 K/V 表示容量
```

答案确实是：

```math
\boxed{\text{是的}}
```

传统单头：

```math
K,V\in\mathbb{R}^{4096}
```

MQA：

```math
K,V\in\mathbb{R}^{128}
```

从 4096 压缩到了 128。

也就是说：

> MQA 的共享 K/V 表示确实进行了非常强的压缩。

因此 MQA 是用一部分 K/V 表达能力来换取更低的 KV Cache 显存。

---

<a id="origin-12145"></a>
## 190. 那为什么 MQA 还可以工作？

因为 MQA 虽然只有一套 K/V：

```text
1个 K
1个 V
```

但它仍然保留：

```text
32个不同的 Query Head
```

也就是：

```math
Q^{(1)},Q^{(2)},\ldots,Q^{(32)}
```

这些 Query 是不同的。

所以：

```math
Q^{(1)}K^T
```

和：

```math
Q^{(2)}K^T
```

得到的 Attention Score 可以完全不同。

---

<a id="origin-12184"></a>
## 191. 举一个自然语言例子

考虑：

> 小明把苹果送给了小红，因为她很饿。

假设当前处理：

```text
“她”
```

MQA 只有一套共享的：

```text
K小明
K苹果
K小红
K送给
...
```

但是有：

```text
Q她^(1)
Q她^(2)
Q她^(3)
...
Q她^(32)
```

---

<a id="origin-12218"></a>
### 191.1 Head 1

可能学会关注：

```text
人物指代
```

得到：

```text
小明：0.05
苹果：0.05
小红：0.85
其他：0.05
```

---

<a id="origin-12237"></a>
### 191.2 Head 2

可能关注：

```text
语法关系
```

得到：

```text
小明：0.30
送给：0.40
小红：0.25
其他：0.05
```

---

<a id="origin-12256"></a>
### 191.3 Head 3

可能关注：

```text
因果关系
```

得到：

```text
小红：0.45
因为：0.25
饿：0.25
其他：0.05
```

所以虽然 K 是共享的：

```math
K
```

但是由于：

```math
Q^{(1)}\neq Q^{(2)}\neq Q^{(3)}
```

因此：

```math
Softmax(Q^{(1)}K^T)
```

```math
Softmax(Q^{(2)}K^T)
```

```math
Softmax(Q^{(3)}K^T)
```

都可以不同。

所以：

```math
\boxed{\text{MQA 仍然可以产生很多种不同的 Attention Pattern}}
```

---

<a id="origin-12309"></a>
## 192. 单头 Attention 的一个重要限制

传统单头虽然：

```math
K,V\in\mathbb{R}^{4096}
```

信息非常宽。

但是它只有：

```text
一个 Query Head
```

所以对于当前 token，只能产生：

```text
一套 Attention 权重
```

例如：

```text
小明：0.10
苹果：0.05
小红：0.75
因为：0.05
其他：0.05
```

然后：

```math
O=
0.10V_{\text{小明}}
+
0.05V_{\text{苹果}}
+
0.75V_{\text{小红}}
+\cdots
```

注意：

> 虽然每个 V 有 4096 维，但是这 4096 个维度共享的是同一套 Attention 权重。

也就是说：

```text
只有一种“怎么看这些历史 token”的方式
```

---

<a id="origin-12365"></a>
## 193. 单头与 MQA 的能力区别

因此这两者不是简单的：

```text
4096维一定强于128维
```

而是能力侧重点不同。

---

<a id="origin-12377"></a>
### 193.1 单头 Attention

特点：

```text
K/V 很宽
Attention Pattern 只有一套
```

可以理解成：

> 一个分析员，拿着一本非常厚的 4096 页资料。

资料非常详细。

但是：

> 只有一个人分析。

所以只有：

```text
一种观察方式
```

---

<a id="origin-12404"></a>
### 193.2 MQA

特点：

```text
K/V 很窄
但是有32个 Query Head
```

可以理解成：

> 32 个分析员，共享一本只有 128 页的压缩资料。

资料没有那么详细。

但是：

```text
分析员1关注人物
分析员2关注语法
分析员3关注因果
分析员4关注位置
……
```

于是可以产生：

```text
32种不同的观察方式
```

---

<a id="origin-12437"></a>
## 194. 最核心的能力对比

可以这样理解：

```math
\boxed{
\text{Attention能力}
\approx
\text{KV表示能力}
+
\text{Attention Pattern数量}
}
```

虽然这不是严格数学公式，但非常适合理解。

---

<a id="origin-12455"></a>
### 194.1 单头

```text
KV表示能力：

很宽
4096维


Attention Pattern：

1套
```

因此可以记成：

```math
\boxed{\text{单头：一套很宽的信息 + 一种看法}}
```

---

<a id="origin-12477"></a>
### 194.2 MQA

```text
KV表示能力：

比较窄
128维


Attention Pattern：

32套
```

因此：

```math
\boxed{\text{MQA：一套压缩的信息 + 很多种看法}}
```

---

<a id="origin-12499"></a>
### 194.3 MHA

MHA 则更强：

```text
32个 Query Head
+
32套独立的 K/V
```

所以可以理解成：

```math
\boxed{\text{MHA：很多套信息 + 很多种看法}}
```

代价就是：

```text
KV Cache 非常大
```

---

<a id="origin-12523"></a>
## 195. 为什么 MQA 最终输出仍然是 4096 维？

这是另一个非常容易误解的问题。

MQA 的：

```math
V\in\mathbb{R}^{128}
```

是不是意味着最终 Attention 只能输出 128 维？

不是。

因为每一个 Query Head 都会产生一个自己的输出。

第一个 Head：

```math
O^{(1)}
=
\sum_j
\alpha_j^{(1)}V_j
```

第二个 Head：

```math
O^{(2)}
=
\sum_j
\alpha_j^{(2)}V_j
```

……

第 32 个 Head：

```math
O^{(32)}
=
\sum_j
\alpha_j^{(32)}V_j
```

每一个：

```math
O^{(i)}\in\mathbb{R}^{128}
```

一共有 32 个。

所以把它们拼起来：

```math
O=
Concat(
O^{(1)},
O^{(2)},
\ldots,
O^{(32)}
)
```

得到：

```math
O\in\mathbb{R}^{32\times128}
```

即：

```math
O\in\mathbb{R}^{4096}
```

因此：

```math
\boxed{\text{MQA 最终 Attention 输出仍然可以是4096维}}
```

---

<a id="origin-12608"></a>
## 196. 为什么共享 V，还能产生不同输出？

因为虽然大家读取的是同样的：

```math
V_1,V_2,V_3
```

但是每个 Head 的 Attention 权重不同。

例如：

```math
O_1
=
0.8V_1
+
0.1V_2
+
0.1V_3
```

第二个 Head：

```math
O_2
=
0.1V_1
+
0.8V_2
+
0.1V_3
```

第三个 Head：

```math
O_3
=
0.1V_1
+
0.1V_2
+
0.8V_3
```

虽然它们使用的是同一套：

```math
V_1,V_2,V_3
```

但由于权重不同：

```math
O_1\neq O_2\neq O_3
```

所以仍然可以产生大量不同的信息组合。

---

<a id="origin-12670"></a>
## 197. 单头与 MQA 的 KV Cache 显存到底差多少？

继续假设：

```text
hidden_size = 4096
head_dim = 128
Query Head = 32
```

---

<a id="origin-12682"></a>
### 197.1 单头 Attention

每个 token：

```text
K：4096个数
V：4096个数
```

总计：

```math
8192
```

个数。

---

<a id="origin-12701"></a>
### 197.2 MQA

每个 token：

```text
K：128个数
V：128个数
```

总计：

```math
256
```

个数。

因此：

```math
\frac{8192}{256}=32
```

所以：

```math
\boxed{\text{MQA 的 KV Cache 大约缩小32倍}}
```

---

<a id="origin-12732"></a>
## 198. 举一个实际显存数字例子

假设：

```text
上下文长度 L = 8192
Transformer 层数 = 32
数据类型 = FP16/BF16
每个数字 = 2 Bytes
batch size = 1
```

---

<a id="origin-12746"></a>
### 198.1 传统单头 Attention

KV Cache 大小约为：

```math
8192
\times
32
\times
2
\times
4096
\times
2
```

其中：

```text
8192：
token数量

32：
层数

2：
K和V

4096：
K/V宽度

2：
每个FP16/BF16数字2 Bytes
```

约：

```text
4 GB
```

---

<a id="origin-12789"></a>
### 198.2 MQA

变成：

```math
8192
\times
32
\times
2
\times
128
\times
2
```

约：

```text
128 MB
```

于是：

```text
传统单头：

约 4 GB


MQA：

约 128 MB
```

差：

```math
32\times
```

注意：

> 这里比较的只是 KV Cache，不是整个模型显存。

---

<a id="origin-12836"></a>
## 199. 为什么 Q 还是 4096 维，却不会把显存重新吃回来？

因为：

```text
Q 一般不需要长期缓存
```

自回归生成过程中，真正需要保存历史信息的是：

```text
K Cache
V Cache
```

例如现在生成第 1000 个 token。

当前 token 会生成：

```text
当前 Q
当前 K
当前 V
```

为了计算当前 token 对历史 token 的 Attention，需要历史的：

```text
K1,K2,...,K999
```

以及：

```text
V1,V2,...,V999
```

但是不需要：

```text
Q1,Q2,...,Q999
```

因为过去的 Query 只负责回答过去那个时刻的问题。

例如：

```text
Q500
```

负责的是：

> 第500个 token 当时应该关注前面的哪些 token？

这个问题早就在生成第 500 个 token 时完成了。

第 1000 个 token 到来以后，需要的是：

```text
Q1000
```

去读取：

```text
K1...K1000
```

所以：

```math
\boxed{\text{KV Cache增长，Q不需要跟着长期增长}}
```

这也是为什么 MQA 可以显著降低推理显存。

---

<a id="origin-12915"></a>
## 200. MQA 中是不是要把 K/V repeat 31 次？

假设：

```text
Query Head = 32
KV Head = 1
```

那么从**计算逻辑上**来看：

> 是的。

原本有一份：

```text
K
V
```

但有 32 个 Query Head：

```text
Q1
Q2
Q3
...
Q32
```

所以这一份 K/V 要供全部 32 个 Query Head 使用。

可以画成：

```text
                    Q1
                     │
                    K/V

                    Q2
                     │
                    K/V

                    Q3
                     │
                    K/V

                    ...

                    Q32
                     │
                    K/V
```

也就是：

```text
原本1份
+
逻辑上再重复31份
=
32份
```

所以如果只是为了理解：

```math
\boxed{\text{可以理解成 repeat 31 次}}
```

---

<a id="origin-12987"></a>
## 201. 从 Tensor Shape 上怎么理解 repeat？

原来的 K：

```text
K shape：

[B, 1, L, 128]
```

其中：

```text
B：
batch size

1：
只有一个 KV Head

L：
序列长度

128：
head_dim
```

而 Query：

```text
Q shape：

[B, 32, L, 128]
```

为了做 Attention，可以逻辑上把 K 变成：

```text
[B, 32, L, 128]
```

也就是：

```text
K1 = K
K2 = K
K3 = K
...
K32 = K
```

V 同理。

---

<a id="origin-13041"></a>
## 202. 但实际 KV Cache 不会真的复制 31 份

这一点非常关键。

如果把：

```text
K
```

真正复制 32 份存起来：

```text
K1
K2
...
K32
```

那不就又回到了：

```text
32 × 128 = 4096
```

这样 MQA 就失去节省 KV Cache 的意义了。

因此：

> **KV Cache 本身始终只保存一份 K/V。**

例如：

```text
显存中的 KV Cache：

K：[128维]
V：[128维]
```

然后：

```text
Q1 ─┐
Q2 ─┤
Q3 ─┤
... │──→ 共同读取这一份 K/V
Q32─┘
```

所以更准确的说法是：

```math
\boxed{\text{逻辑上 repeat，物理存储上通常不复制}}
```

---

<a id="origin-13099"></a>
## 203. repeat 和真正复制的区别

概念上可以写：

```python
K_repeat = repeat(K, 32)
```

看起来变成：

```text
[K,K,K,...,K]
```

32份。

但是高效实现中不一定真的复制数据。

可以通过：

```text
broadcast
expand
专门的 Attention kernel
```

让 32 个 Query Head 都直接访问同一份 K/V。

因此：

```text
逻辑 Shape：

32 × 128
```

不代表：

```text
物理显存：

真的保存了32份128
```

---

<a id="origin-13145"></a>
## 204. 为什么 repeat 后反向传播仍然能训练共享 K/V？

假设只有两个 Query Head，为了简单理解：

```text
Q1
Q2
```

都读取同一个：

```text
K
```

于是计算图类似：

```text
             K
           /   \
          /     \
        Q1       Q2
         │        │
       Loss1    Loss2
```

虽然逻辑上：

```text
K被使用了两次
```

但它们最终连接回的是：

```text
同一个 K
```

所以反向传播时：

```math
\frac{\partial L}{\partial K}
=
\frac{\partial L_1}{\partial K}
+
\frac{\partial L_2}{\partial K}
```

如果 32 个 Query Head：

```math
\frac{\partial L}{\partial K}
=
\sum_{h=1}^{32}
\frac{\partial L_h}{\partial K}
```

V 同理。

也就是说：

> 32 个 Query Head 都会帮助训练这同一套共享的 K/V 表示。

可以理解成：

> 一块共享矩阵，同时接出了 32 条计算路径；反向传播时，32 条路径的梯度最终汇总回来。

---

<a id="origin-13214"></a>
## 205. 为什么后来会出现 GQA？

现在整个逻辑就很自然了。

---

<a id="origin-13220"></a>
### 205.1 单头 Attention

```text
1个 Q
1个 K
1个 V

每个都是4096维
```

优点：

```text
单个 K/V 表达非常宽
```

缺点：

```text
只有一套 Attention Pattern
KV Cache 很大
```

---

<a id="origin-13245"></a>
### 205.2 MHA

为了让模型从多个角度关注信息：

```text
32个 Q
32个 K
32个 V

每个128维
```

这样：

```text
Head1有自己的Q/K/V
Head2有自己的Q/K/V
...
Head32有自己的Q/K/V
```

表达能力很强。

但是：

```math
32\times128=4096
```

所以总 K/V 宽度还是：

```text
4096维
```

KV Cache 没有减少。

---

<a id="origin-13284"></a>
### 205.3 MQA

于是进一步想到：

> Query 保留 32 个，但是 K/V 只留一套。

于是：

```text
32个Q
1个K
1个V
```

这样 KV Cache 从：

```text
4096维
```

缩到：

```text
128维
```

非常省显存。

但是问题也出现了：

> 32 个 Query Head 必须共享同一套 K/V，压缩得太激进。

---

<a id="origin-13318"></a>
### 205.4 GQA

所以再折中一下：

```text
32个 Query Head
8个 KV Head
```

也就是：

```text
Q1~Q4    → KV1
Q5~Q8    → KV2
Q9~Q12   → KV3
...
Q29~Q32  → KV8
```

这样：

```text
比 MHA 更省 KV Cache
```

同时：

```text
比 MQA 保留更多独立的 K/V 表达
```

所以 GQA 可以看作：

```math
\boxed{\text{MHA 与 MQA 之间的折中}}
```

---

<a id="origin-13357"></a>
## 206. 从显存和能力两个角度统一理解

最终可以整理成：

| 架构  | Q Head | KV Head | K/V总宽度 | Attention Pattern | KV表达能力 | KV Cache |
| --- | -----: | ------: | -----: | ----------------: | ------ | -------- |
| 单头  |      1 |       1 |   4096 |                1套 | 单套很宽   | 大        |
| MHA |     32 |      32 |   4096 |               32套 | 最灵活    | 大        |
| GQA |     32 |       8 |   1024 |               32套 | 中等     | 中等       |
| MQA |     32 |       1 |    128 |               32套 | 压缩最强   | 最小       |

---

<a id="origin-13370"></a>
## 207. 一个最形象的比喻

<a id="origin-13372"></a>
### 207.1 单头 Attention

```text
1个人

拿着一本4096页的超级详细资料
```

优点：

```text
资料特别详细
```

缺点：

```text
只有一个人的观察角度
```

所以：

```math
\boxed{\text{一套很宽的信息 + 一种看法}}
```

---

<a id="origin-13400"></a>
### 207.2 MHA

```text
32个人

每个人都有自己的一本128页资料
```

并且这些资料内容可以不同。

所以：

```text
每个人：
问的问题不同
看的资料也不同
```

因此：

```math
\boxed{\text{很多套信息 + 很多种看法}}
```

能力强，但资料要保存 32 本。

---

<a id="origin-13428"></a>
### 207.3 MQA

```text
32个人

共享一本128页的资料
```

每个人：

```text
提出不同的问题
```

但：

```text
看的都是同一本资料
```

所以：

```math
\boxed{\text{一套压缩的信息 + 很多种看法}}
```

优点：

```text
只保存一本资料
```

所以特别省显存。

---

<a id="origin-13464"></a>
### 207.4 GQA

```text
32个人

分成8组

每4个人共享一本资料
```

于是：

```math
\boxed{\text{在表达能力和显存之间折中}}
```

---

<a id="origin-13482"></a>
## 208. 最后完整串起来

整个故事可以记成：

```text
最早单头 Attention
────────────────────────

1Q × 4096
1K × 4096
1V × 4096

特点：
K/V非常宽

问题：
只有一种 Attention 观察方式
KV Cache大


          ↓

希望让模型能够同时
从多个角度理解信息


MHA
────────────────────────

32Q × 128
32K × 128
32V × 128

特点：
32套不同的 Attention

而且：
每个Head还有自己的K/V

优点：
表达能力很强

问题：
KV Cache：

32 × 128 = 4096

还是很大


          ↓

发现推理阶段
KV Cache占显存很多


MQA
────────────────────────

32Q × 128

1K × 128
1V × 128

特点：
32个Query Head
共享同一份K/V

优点：

KV Cache：

4096
↓
128

缩小32倍

问题：
共享得太激进
K/V表达能力下降


          ↓

希望既省显存
又保留更多KV能力


GQA
────────────────────────

32Q × 128
8K × 128
8V × 128

特点：

每4个Query Head
共享一套KV

最终：

在MHA和MQA之间取得折中
```

---

<a id="origin-13590"></a>
## 209. 最核心的几句话

第一：

```math
\boxed{
\text{只有一个KV Head}
\neq
\text{传统单头 Attention}
}
```

因为 MQA 有：

```text
多个 Query Head
```

---

第二：

传统单头中的 K/V 可以是：

```math
4096\text{维}
```

而 MQA 中：

```math
K,V\in\mathbb{R}^{128}
```

因此 KV Cache 显著减少。

---

第三：

MQA 并不是整个 Attention 只有 128 维。

因为：

```text
32个 Query Head
```

分别得到：

```text
32个128维输出
```

最后：

```math
32\times128=4096
```

仍然得到 4096 维输出。

---

第四：

MQA 中唯一的一份 K/V：

```text
逻辑上
```

相当于供 32 个 Query Head 使用。

可以理解成：

```text
原来1份
+
repeat 31份
=
逻辑上的32份
```

但：

```math
\boxed{\text{KV Cache中仍然只物理保存1份}}
```

否则 MQA 就失去了节省显存的意义。

---

第五：

最终可以用一句话区分：

```text
单头 Attention：

一个人
+
一本非常厚的书


MHA：

32个人
+
32本不同的书


GQA：

32个人
+
8本书
+
每4个人共享一本


MQA：

32个人
+
1本压缩后的书
+
所有人共享
```

因此 MQA 的核心思想就是：

```math
\boxed{
\text{保留多个 Query 的观察角度}
+
\text{大幅压缩共享的 K/V}
}
```

最终换来：

```text
更小的 KV Cache
更低的推理显存
更高效的长上下文推理
```

代价则是：

```text
K/V表示能力受到一定压缩
```

这也正是 GQA 出现的原因。
