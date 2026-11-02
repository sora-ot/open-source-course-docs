# LayerNorm、RMSNorm 与 Pre-Norm


在 Transformer 中，我们前面已经讨论过一个非常重要的问题：

```math
Attention(Q,K,V)
=
softmax\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
```

其中之所以要除以：

```math
\sqrt{d_k}
```

本质上是为了控制 Attention Score 的数值尺度。

因为如果 \(Q\)、\(K\) 每个维度的方差大约为 1，那么：

```math
Var(Q\cdot K)\approx d_k
```

于是：

```math
Std(Q\cdot K)\approx\sqrt{d_k}
```

所以需要除以：

```math
\sqrt{d_k}
```

把数值重新拉回一个稳定的尺度。

但这里又会产生一个新的问题：

> 我们为什么敢假设进入 Attention 的向量数值尺度是比较稳定的？

实际上，如果什么都不做，随着网络越来越深，神经网络内部的数值尺度可能不断变化。

这就引出了：

```text
Normalization
```

---

<a id="origin-55"></a>
## 1. 深层网络首先面临的问题：数值尺度会不断漂移

假设某一层的 hidden state 是：

```math
x=[x_1,x_2,\dots,x_d]
```

开始时可能是：

```text
[-0.8, 0.3, 1.1, -0.4]
```

但是经过：

```text
Linear
↓
Attention
↓
Residual
↓
MLP
↓
Residual
↓
下一层
↓
下一层
...
```

以后，数值可能逐渐变成：

```text
[-8, 3, 11, -4]
```

甚至：

```text
[-80, 30, 110, -40]
```

也可能反过来变得越来越小：

```text
[-0.00008, 0.00003, 0.00011, -0.00004]
```

这就意味着：

```text
不同层之间的 activation 数值尺度可能不稳定
```

一旦数值尺度发生剧烈变化，就可能影响：

```text
Attention Score
↓
Softmax
↓
梯度传播
↓
训练稳定性
```

例如：

```text
hidden state 很大
        ↓
Q、K 很大
        ↓
Q·K 更大
        ↓
softmax 输入很大
        ↓
softmax 极其尖锐
```

因此，深层神经网络需要某种机制不断控制内部表示的数值尺度。

即：如果某一层 hidden state 的典型数值从 1 左右逐渐放大到 10、100，或者缩小到 0.001，那么后面由它生成的 Q、K、V、Attention score 和 MLP 输出都会跟着改变数量级。LayerNorm/RMSNorm 的作用，**就是尽量把每个 Block 的 hidden state 拉回到相近的尺度（1左右），** 让后续计算始终在比较稳定的数值范围里进行。

---

<a id="origin-144"></a>
## 2. 一个最自然的想法：把数据标准化

假设：

```math
x=[2,4,6,8]
```

首先计算均值：

```math
\mu
=
\frac{2+4+6+8}{4}
=
5
```

然后计算方差：

```math
\sigma^2
=
\frac{
(2-5)^2+
(4-5)^2+
(6-5)^2+
(8-5)^2
}{4}
```

得到：

```math
\sigma^2=5
```

标准差：

```math
\sigma=\sqrt5
```

然后进行标准化：

```math
\hat{x_i}
=
\frac{x_i-\mu}
{\sqrt{\sigma^2+\epsilon}}
```

这就是 LayerNorm 最核心的思想。

---

<a id="origin-200"></a>
## 3. LayerNorm 到底做了什么？

LayerNorm 可以简单理解成两步：

```text
第一步：重新居中
第二步：重新缩放
```

也就是：

```math
x_i
\rightarrow
x_i-\mu
\rightarrow
\frac{x_i-\mu}{\sigma}
```

完整公式：

```math
LayerNorm(x)
=
\frac{x-\mu}
{\sqrt{\sigma^2+\epsilon}}
\odot\gamma+\beta
```

其中：

```math
\mu
=
\frac{1}{d}
\sum_{i=1}^{d}x_i
```

```math
\sigma^2
=
\frac{1}{d}
\sum_{i=1}^{d}(x_i-\mu)^2
```

---

<a id="origin-247"></a>
## 4. LayerNorm 第一步：减去均值

假设：

```math
x=[2,4,6,8]
```

均值：

```math
\mu=5
```

减去均值：

```math
x-\mu
=
[-3,-1,1,3]
```

这样以后：

```text
原来：

2  4  6  8

整体中心在 5 附近
```

变成：

```text
-3  -1  1  3

整体中心移动到 0
```

因此：

```math
Mean(x-\mu)=0
```

这叫：

```text
re-centering
重新居中
```

---

<a id="origin-302"></a>
## 5. LayerNorm 第二步：除以标准差

现在：

```math
[-3,-1,1,3]
```

它虽然已经围绕 0，但整体尺度可能仍然比较大。

于是再除以标准差：

```math
\frac{x-\mu}{\sigma}
```

例如最终可能得到：

```math
[-1.34,-0.45,0.45,1.34]
```

此时：

```math
Mean\approx0
```

同时：

```math
Var\approx1
```

因此 LayerNorm 实际做的是：

```text
原始向量
   ↓
减去均值
   ↓
均值 ≈ 0
   ↓
除以标准差
   ↓
方差 ≈ 1
```

---

<a id="origin-352"></a>
## 6. 为什么标准化后还需要 \(\gamma\) 和 \(\beta\)？

如果 LayerNorm 永远强行要求：

```math
Mean=0
```

以及：

```math
Var=1
```

可能会限制模型表达能力。

所以 LayerNorm 最后还会加入两个可学习参数：

```math
\gamma
```

和：

```math
\beta
```

最终：

```math
y
=
\gamma
\frac{x-\mu}
{\sqrt{\sigma^2+\epsilon}}
+
\beta
```

其中：

```text
γ：重新控制尺度
β：重新控制位置
```

可以理解成：

> 先把数据拉回一个稳定状态，然后让神经网络自己学习“真正需要的尺度和偏移”。

---

<a id="origin-405"></a>
## 7. LayerNorm 为什么对 Transformer 很重要？

Transformer 中一个 token 的 hidden state 可能是：

```math
x\in\mathbb R^{4096}
```

它会不断经过：

```text
Attention
↓
Residual
↓
MLP
↓
Residual
↓
下一层
```

如果没有归一化，每层的数值尺度可能逐渐漂移。

LayerNorm 相当于不断告诉网络：

```text
不要让数值越来越大

也不要越来越小

尽量保持在稳定范围内
```

因此它可以：

```text
控制 activation 数值范围
↓
改善训练稳定性
↓
帮助深层网络训练
```

---

<a id="origin-451"></a>
## 8. 但是 LayerNorm 又引出了一个问题

LayerNorm 同时做了：

```text
1. 减均值
2. 除标准差
```

也就是说：

```text
重新居中
+
重新缩放
```

于是有人提出一个问题：

> 对 Transformer 来说，我们真正最需要的，是不是其实只是“控制尺度”？

换句话说：

```text
减均值真的必须吗？
```

如果真正危险的是：

```text
1
→
10
→
100
→
1000
```

这种 activation 尺度不断膨胀，

那么也许只要控制：

```text
向量整体大小
```

就足够了。

这就是 RMSNorm 的出发点。

---

<a id="origin-504"></a>
## 9. RMS 是什么？

RMS 的全称：

```text
Root Mean Square
```

中文：

```text
均方根
```

对于向量：

```math
x=[x_1,x_2,\dots,x_d]
```

RMS 定义为：

```math
RMS(x)
=
\sqrt{
\frac{1}{d}
\sum_{i=1}^{d}x_i^2
}
```

步骤很简单：

```text
每个数平方
↓
求平均
↓
开平方
```

---

<a id="origin-547"></a>
## 10. RMSNorm 怎么做？

RMSNorm 直接使用：

```math
RMSNorm(x)
=
\frac{x}
{\sqrt{
\frac{1}{d}\sum_{i=1}^{d}x_i^2+\epsilon
}}
\odot\gamma
```

注意它与 LayerNorm 最大的区别：

<a id="origin-563"></a>
### 10.1 LayerNorm

```math
\frac{x-\mu}
{\sqrt{
\frac{1}{d}\sum_i(x_i-\mu)^2+\epsilon
}}
```

<a id="origin-572"></a>
### 10.2 RMSNorm

```math
\frac{x}
{\sqrt{
\frac{1}{d}\sum_i x_i^2+\epsilon
}}
```

RMSNorm 没有：

```math
x-\mu
```

这一步。

---

<a id="origin-591"></a>
## 11. LayerNorm 和 RMSNorm 的核心区别

可以直接记成：

```text
LayerNorm：

重新居中
+
重新缩放
```

即：

```text
减均值
+
控制尺度
```

而：

```text
RMSNorm：

只重新缩放
```

也就是：

```text
不减均值
只控制尺度
```

因此：

```math
\boxed{
RMSNorm
\approx
去掉“减均值”的 LayerNorm
}
```

当然，两者并不严格等价。

---

<a id="origin-640"></a>
## 12. 一个具体例子

假设：

```math
x=[1,2,3,4]
```

---

<a id="origin-650"></a>
### 12.1 LayerNorm

均值：

```math
\mu
=
\frac{1+2+3+4}{4}
=
2.5
```

减均值：

```math
[-1.5,-0.5,0.5,1.5]
```

再除以标准差，得到大约：

```math
[-1.34,-0.45,0.45,1.34]
```

因此：

```text
均值 ≈ 0
方差 ≈ 1
```

---

<a id="origin-683"></a>
### 12.2 RMSNorm

首先计算：

```math
RMS
=
\sqrt{
\frac{
1^2+2^2+3^2+4^2
}{4}
}
```

即：

```math
RMS
=
\sqrt{\frac{30}{4}}
```

约为：

```math
RMS\approx2.739
```

然后：

```math
x'
=
\frac{[1,2,3,4]}{2.739}
```

得到：

```math
x'
\approx
[0.365,0.730,1.095,1.461]
```

注意：

```text
它的均值并不是 0
```

但：

```math
\frac{
0.365^2+
0.730^2+
1.095^2+
1.461^2
}{4}
\approx1
```

所以：

```math
RMS(x')\approx1
```

RMSNorm 达到了自己的目标：

> 控制向量整体数值尺度，而不强制均值变成 0。

---

<a id="origin-757"></a>
## 13. RMSNorm 为什么有效？

很多深层网络真正危险的问题往往是：

```text
activation 的绝对尺度越来越大
```

例如：

```text
第 1 层：

[1, 2, 3]

第 10 层：

[10, 20, 30]

第 30 层：

[1000, 2000, 3000]
```

这种尺度漂移可能导致：

```text
Q、K 变大
↓
QK^T 变大
↓
softmax 过于尖锐
↓
训练不稳定
```

而 RMSNorm 可以不断把：

```text
向量整体尺度
```

拉回一个比较稳定的范围。

因此很多 Transformer 场景中：

```text
控制尺度
```

往往已经足够重要。

---
<a id="origin-810"></a>
### 13.1 具体看一下 RMSNorm 是怎么把不同尺度拉回来的

假设不同层的 activation 分别是：

```text
第 1 层：

[1, 2, 3]

第 10 层：

[10, 20, 30]

第 30 层：

[1000, 2000, 3000]
```

这三个向量其实方向完全相同，只是整体尺度越来越大：

```text
[10, 20, 30]
=
10 × [1, 2, 3]

[1000, 2000, 3000]
=
1000 × [1, 2, 3]
```

RMSNorm 会对每个向量先计算自己的 RMS：

```math
RMS(x)
=
\sqrt{
\frac{1}{d}
\sum_{i=1}^{d}x_i^2
}
```

---

<a id="origin-853"></a>
#### 13.1.1 第 1 层

```math
x=[1,2,3]
```

RMS 为：

```math
RMS(x)
=
\sqrt{
\frac{1^2+2^2+3^2}{3}
}
```

```math
=
\sqrt{
\frac{14}{3}
}
\approx 2.160
```

所以归一化之后：

```math
\hat{x}
=
\left[
\frac{1}{2.160},
\frac{2}{2.160},
\frac{3}{2.160}
\right]
```

得到：

```math
\hat{x}
\approx
[0.463,\ 0.926,\ 1.389]
```

---

<a id="origin-899"></a>
#### 13.1.2 第 10 层

```math
x=[10,20,30]
```

RMS 为：

```math
RMS(x)
=
\sqrt{
\frac{10^2+20^2+30^2}{3}
}
```

```math
=
\sqrt{
\frac{1400}{3}
}
\approx 21.602
```

所以：

```math
\hat{x}
=
\left[
\frac{10}{21.602},
\frac{20}{21.602},
\frac{30}{21.602}
\right]
```

得到：

```math
\hat{x}
\approx
[0.463,\ 0.926,\ 1.389]
```

---

<a id="origin-945"></a>
#### 13.1.3 第 30 层

```math
x=[1000,2000,3000]
```

RMS 为：

```math
RMS(x)
=
\sqrt{
\frac{1000^2+2000^2+3000^2}{3}
}
```

```math
=
\sqrt{
\frac{14,000,000}{3}
}
\approx 2160.247
```

所以：

```math
\hat{x}
=
\left[
\frac{1000}{2160.247},
\frac{2000}{2160.247},
\frac{3000}{2160.247}
\right]
```

得到：

```math
\hat{x}
\approx
[0.463,\ 0.926,\ 1.389]
```

---

于是原来的：

```text
第 1 层：
[1, 2, 3]

第 10 层：
[10, 20, 30]

第 30 层：
[1000, 2000, 3000]
```

经过 RMSNorm 后都会变成：

```text
[0.463, 0.926, 1.389]
```

也就是说：

```text
[1, 2, 3]
      ↓
   RMSNorm
      ↓
[0.463, 0.926, 1.389]


[10, 20, 30]
      ↓
   RMSNorm
      ↓
[0.463, 0.926, 1.389]


[1000, 2000, 3000]
      ↓
   RMSNorm
      ↓
[0.463, 0.926, 1.389]
```

所以 RMSNorm 做的事情可以概括成：

```text
整体放大 10 倍
→ RMS 也放大 10 倍
→ 一除，10 倍被抵消

整体放大 1000 倍
→ RMS 也放大 1000 倍
→ 一除，1000 倍也被抵消
```

数学上，如果：

```math
x'=cx
```

那么：

```math
RMS(x')
=
RMS(cx)
=
|c|RMS(x)
```

因此当 `c > 0` 时：

```math
\frac{cx}{RMS(cx)}
=
\frac{cx}{cRMS(x)}
=
\frac{x}{RMS(x)}
```

所以：

```text
RMSNorm 并不是把每个数压到 0~1。

它真正做的是：

消除向量整体的尺度变化，
同时保留各维度之间原本的相对比例。
```

这就是为什么即使深层网络中的 activation 从：

```text
[1, 2, 3]
```

一路漂移成：

```text
[1000, 2000, 3000]
```

RMSNorm 依然可以在进入后续 Attention 或 MLP 之前，把它们重新拉回到近似一致的数值尺度。


---

<a id="origin-1100"></a>
## 14. 为什么现在很多 LLM 使用 RMSNorm？

可以把原因概括成：

```text
LayerNorm：

控制中心
+
控制尺度
```

而：

```text
RMSNorm：

只控制尺度
```

RMSNorm 不需要显式执行：

```text
求均值
↓
每个元素减去均值
```

所以：

```text
实现更简单
计算路径更简单
同时在很多 Transformer / LLM 中效果很好
```

因此很多现代大语言模型会使用：

```text
RMSNorm
```

来替代经典 LayerNorm。

但应该注意：

> 不是因为 LayerNorm “错了”，而是 RMSNorm 发现，对于很多 Transformer 场景，只做尺度归一化就已经足够有效。

---

<a id="origin-1150"></a>
## 15. 到这里还有一个问题：Norm 应该放在哪里？

假设我们已经决定：

```text
需要 Norm
```

那么马上会出现另一个问题：

> Norm 应该放在 Attention / MLP 前面，还是后面？

这就产生了：

```text
Post-Norm
```

和：

```text
Pre-Norm
```

---

<a id="origin-1176"></a>
## 16. 先从最简单的残差连接开始

暂时不要管 Transformer。

假设输入：

```math
x
```

有一个神经网络模块：

```math
F(x)
```

这里的 \(F\) 可以代表：

```text
Attention
```

也可以代表：

```text
MLP
```

最简单的残差结构：

```math
y=x+F(x)
```

结构：

```text
x ───────────────────┐
                     +
x → F(x) ─────────────┘
                     ↓
                     y
```

这里存在两条路径：

```text
第一条：

x ───────────────→ y
```

这是：

```text
Residual / Skip Connection
```

另一条：

```text
x
↓
F(x)
↓
y
```

---

<a id="origin-1246"></a>
## 17. 为什么 Residual Connection 很重要？

因为即使：

```math
F(x)
```

非常复杂，

至少还有：

```math
x
```

可以直接传过去。

所以：

```math
y=x+F(x)
```

意味着：

> 网络不需要每一层都重新构造整个表示，只需要在原有 \(x\) 的基础上学习一个增量。

可以理解成：

```text
新表示
=
旧表示
+
这一层学习到的修改
```

---

<a id="origin-1286"></a>
## 18. Post-Norm 是什么？

原始 Transformer 使用的是典型的 Post-Norm。

公式：

```math
\boxed{
y=Norm(x+F(x))
}
```

执行顺序：

```text
x
↓
F(x)
↓
和原来的 x 相加
↓
Norm
↓
y
```

所以叫：

```text
Post-Norm
```

因为 Norm 在 residual addition 之后。

结构：

```text
x ──────────────────┐
                    +
x → F(x) ────────────┘
                    ↓
                   Norm
                    ↓
                    y
```

---

<a id="origin-1334"></a>
## 19. Post-Norm 的一个具体例子

假设：

```math
x=[1,2,3]
```

Attention 输出：

```math
F(x)=[0.1,0.2,0.3]
```

首先做 Residual：

```math
x+F(x)
```

得到：

```math
[1.1,2.2,3.3]
```

然后再做：

```math
Norm([1.1,2.2,3.3])
```

假设得到：

```math
[-1.22,0,1.22]
```

注意：

虽然原来的：

```math
x=[1,2,3]
```

通过 residual 被加进去了，

但是之后又整体经过了一次：

```text
Norm
```

所以最终已经不再保留原始：

```math
[1,2,3]
```

的数值形式。

---

<a id="origin-1398"></a>
## 20. Post-Norm 的关键特点

Post-Norm：

```math
y=Norm(x+F(x))
```

虽然存在：

```text
Residual Connection
```

但是：

```text
x
```

并不是完全直接地传递到下一层。

因为：

```text
x
↓
+
↓
Norm
↓
下一层
```

也就是说：

> residual path 最终仍然必须经过 Norm。

---

<a id="origin-1438"></a>
## 21. Pre-Norm 是什么？

后来越来越多 Transformer 使用 Pre-Norm。

公式：

```math
\boxed{
y=x+F(Norm(x))
}
```

执行顺序：

```text
x
↓
Norm
↓
F
↓
和原始 x 相加
↓
y
```

结构：

```text
x ─────────────────────────┐
                           +
x → Norm → F ───────────────┘
                           ↓
                           y
```

这时候最大的区别出现了：

> 原始 \(x\) 有一条完全不经过 Norm 的直通路径。

即：

```text
x
──────────────────────────→ y
```

---

<a id="origin-1487"></a>
## 22. 用同样的数字看 Pre-Norm

还是：

```math
x=[1,2,3]
```

先：

```math
Norm(x)
```

假设得到：

```math
[-1.22,0,1.22]
```

再经过：

```math
F
```

假设：

```math
F(Norm(x))
=
[0.1,0.2,0.3]
```

最后：

```math
y
=
x+
F(Norm(x))
```

于是：

```math
y
=
[1,2,3]
+
[0.1,0.2,0.3]
```

得到：

```math
\boxed{
[1.1,2.2,3.3]
}
```

这里原始：

```math
[1,2,3]
```

完整保留在 residual path 中。

---

<a id="origin-1558"></a>
## 23. Pre-Norm 和 Post-Norm 最核心的区别

直接看公式。

<a id="origin-1562"></a>
### 23.1 Post-Norm

```math
\boxed{
y=Norm(x+F(x))
}
```

结构：

```text
x ───────────────┐
                 +
x → F ────────────┘
                 ↓
                Norm
                 ↓
                 y
```

<a id="origin-1582"></a>
### 23.2 Pre-Norm

```math
\boxed{
y=x+F(Norm(x))
}
```

结构：

```text
x ───────────────────┐
                     +
x → Norm → F ─────────┘
                     ↓
                     y
```

一句话：

```text
Post-Norm：
Norm 在 residual 相加之后

Pre-Norm：
Norm 在 F 之前
```

---

<a id="origin-1612"></a>
## 24. 为什么 Pre-Norm 更有利于梯度传播？

这是 Pre-Norm 非常重要的原因。

对于：

```math
y=x+F(Norm(x))
```

对 \(x\) 求导：

```math
\frac{\partial y}{\partial x}
=
1+
\frac{\partial F(Norm(x))}
{\partial x}
```

这里有一个非常重要的：

```math
\boxed{1}
```

因为：

```math
\frac{\partial x}{\partial x}=1
```

也就是说，即使：

```math
\frac{\partial F}{\partial x}
```

很小，

梯度仍然有一条：

```text
直接通过 x 的路径
```

可以传播。

---

<a id="origin-1662"></a>
## 25. Pre-Norm 的梯度通道

可以画成：

```text
Forward：

x ────────────────────────┐
                          +
x → Norm → F ──────────────┘
                          ↓
                          y
```

反向传播时：

```text
gradient
    ↓
    ├────────────────────→ x
    │
    └→ F → Norm ─────────→ x
```

因此存在一条：

```text
gradient
↓
直接回到 x
```

的路径。

这就是：

```text
Identity Gradient Path
```

---

<a id="origin-1704"></a>
## 26. Post-Norm 的梯度有什么不同？

Post-Norm：

```math
y=Norm(x+F(x))
```

令：

```math
z=x+F(x)
```

那么：

```math
y=Norm(z)
```

所以：

```math
\frac{\partial y}{\partial x}
=
\frac{\partial Norm(z)}
{\partial z}
\left(
1+
\frac{\partial F(x)}
{\partial x}
\right)
```

注意：

虽然 residual 中也有：

```math
1
```

但整个东西外面还乘着：

```math
\frac{\partial Norm}
{\partial z}
```

因此：

> 梯度无法完全绕过 Norm。

结构上：

```text
gradient
   ↓
  Norm
   ↓
   +
  / \
 x   F
```

所有梯度首先都要通过：

```text
Norm
```

---

<a id="origin-1777"></a>
## 27. 为什么网络越深，这个区别越重要？

假设网络只有：

```text
2 层
```

差异可能没那么明显。

但如果有：

```text
32 层
64 层
80 层
100 层
```

Post-Norm 的梯度可能需要连续经过：

```text
Norm
↓
Norm
↓
Norm
↓
Norm
↓
...
```

而 Pre-Norm 始终保留：

```text
x
↓
x + ...
↓
x + ...
↓
x + ...
↓
...
```

这样一条 identity path。

因此在很深的 Transformer 中：

```math
\boxed{
Pre\text{-}Norm
}
```

通常更容易获得稳定的优化。

---

<a id="origin-1838"></a>
## 28. 一个 Transformer Block 其实有两个 Norm

因为一个典型 Transformer Block 包含两个主要子模块：

```text
Attention

MLP
```

所以 Pre-Norm 通常不是只做一次。

第一个子层：

```math
x_1
=
x+
Attention(Norm(x))
```

第二个子层：

```math
x_2
=
x_1+
MLP(Norm(x_1))
```

结构：

```text
             ┌───────────────────────┐
             │                       │
x ───────────┼───────────────────────+
             │                       ↑
             ↓                       │
           Norm                      │
             ↓                       │
         Attention ──────────────────┘
             ↓
            x₁
             │
             ├───────────────────────+
             │                       ↑
             ↓                       │
           Norm                      │
             ↓                       │
            MLP ─────────────────────┘
             ↓
            x₂
```

---

<a id="origin-1894"></a>
## 29. Post-Norm Transformer Block

Post-Norm 对应：

```math
x_1
=
Norm(x+Attention(x))
```

然后：

```math
x_2
=
Norm(x_1+MLP(x_1))
```

结构：

```text
x ──────────────────┐
                    +
x → Attention ───────┘
                    ↓
                  Norm
                    ↓
                   x₁
                    │
                    ├───────────────┐
                    │               +
                    └→ MLP ─────────┘
                                    ↓
                                  Norm
                                    ↓
                                   x₂
```

---

<a id="origin-1934"></a>
## 30. 现代 LLM 为什么经常是 Pre-Norm + RMSNorm？

现在可以把前面所有内容串起来。

RMSNorm 解决：

```text
输入 Attention / MLP 的数值尺度
```

Pre-Norm 解决：

```text
Residual / Gradient 直通路径
```

所以现代结构经常写成：

```math
x_1
=
x+
Attention(RMSNorm(x))
```

然后：

```math
x_2
=
x_1+
MLP(RMSNorm(x_1))
```

即：

```text
RMSNorm
↓
控制进入子层的尺度

Pre-Norm
↓
不破坏 residual identity path
```

两者解决的是不同的问题。

---

<a id="origin-1984"></a>
## 31. 现代 Transformer Block 的直观结构

典型形式：

```text
             ┌─────────────────────────┐
             │                         │
x ───────────┼─────────────────────────+
             │                         ↑
             ↓                         │
          RMSNorm                      │
             ↓                         │
         Attention ────────────────────┘
             ↓
             x₁
             │
             ├─────────────────────────+
             │                         ↑
             ↓                         │
          RMSNorm                      │
             ↓                         │
            MLP ───────────────────────┘
             ↓
             x₂
```

所以一层 Transformer 可以理解为：

```text
第一步：

先把 x 的尺度控制好
↓
Attention
↓
把 Attention 产生的“修改量”加回原来的 x


第二步：

再把新的 x₁ 尺度控制好
↓
MLP
↓
把 MLP 产生的“修改量”加回 x₁
```

因此每个 Block 更像是在：

```text
原来的表示
+
Attention 学到的一点修改
+
MLP 学到的一点修改
```

而不是每一层都完全重新生成 hidden state。

核心区别是：

> **\(\sqrt{d_k}\) 只解决“点积因为维度变大而自然变大”的问题；LayerNorm/RMSNorm 解决的是“进入 Attention/MLP 的 hidden state 自身尺度会随层数和训练过程漂移”的问题。**

---

<a id="origin-2049"></a>
## 32. Attention 已经除以 \(\sqrt{d_k}\)，为什么还需要 LayerNorm？

在 Attention 中，我们已经有：

```math
Attention(Q,K,V)
=
softmax\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
```

其中：

```math
\frac{1}{\sqrt{d_k}}
```

就是为了控制 \(QK^T\) 的数值尺度。

那么一个很自然的问题就是：

> Attention 已经做了数值缩放，为什么 Transformer 里还需要 LayerNorm 或 RMSNorm？

答案是：

```text
÷ √d_k
```

和：

```text
LayerNorm / RMSNorm
```

解决的是**两个不同层次的问题**。

---

<a id="origin-2089"></a>
## 33. 先回顾为什么 Attention 要除以 \(\sqrt{d_k}\)

假设：

```math
Q=(q_1,q_2,\dots,q_{d_k})
```

```math
K=(k_1,k_2,\dots,k_{d_k})
```

那么：

```math
Q\cdot K
=
q_1k_1+
q_2k_2+
\cdots+
q_{d_k}k_{d_k}
```

如果理想化地假设每一维：

```math
E(q_i)\approx0,\qquad Var(q_i)\approx1
```

```math
E(k_i)\approx0,\qquad Var(k_i)\approx1
```

那么：

```math
Var(Q\cdot K)
\approx d_k
```

所以：

```math
Std(Q\cdot K)
\approx\sqrt{d_k}
```

于是我们除以：

```math
\sqrt{d_k}
```

得到：

```math
Std\left(
\frac{Q\cdot K}{\sqrt{d_k}}
\right)
\approx1
```

因此：

> **除以 \(\sqrt{d_k}\) 解决的是：点积项太多以后，Attention Score 会随着维度 \(d_k\) 增大而自然变大。**

---

<a id="origin-2157"></a>
## 34. 但是这里偷偷做了一个假设

刚才整个推导有一个非常重要的前提：

```math
Var(q_i)\approx1
```

以及：

```math
Var(k_i)\approx1
```

问题是：

> 神经网络训练过程中，谁保证 \(Q\) 和 \(K\) 的尺度一直这么稳定？

实际上，并没有天然保证。

例如某一层输入 hidden state：

```math
x
```

通过线性变换：

```math
Q=xW_Q
```

```math
K=xW_K
```

如果：

```math
x
```

本身越来越大，

那么：

```math
Q
```

和：

```math
K
```

也可能一起变大。

---

<a id="origin-2217"></a>
## 35. 一个具体例子

假设理想情况下：

```text
Q 每个元素尺度 ≈ 1
K 每个元素尺度 ≈ 1
```

那么：

```math
QK^T
```

的标准差大约是：

```math
\sqrt{d_k}
```

除以：

```math
\sqrt{d_k}
```

正好变成：

```text
尺度 ≈ 1
```

很好。

---

但是假设网络训练到某一层以后：

```text
Q 每个元素尺度 ≈ 10
K 每个元素尺度 ≈ 10
```

那么每一项：

```math
q_i k_i
```

的尺度大约会变成：

```math
10\times10=100
```

于是整个点积的标准差大约不再是：

```math
\sqrt{d_k}
```

而是：

```math
100\sqrt{d_k}
```

现在再除：

```math
\sqrt{d_k}
```

得到：

```math
\frac{
100\sqrt{d_k}
}{
\sqrt{d_k}
}
=
100
```

Attention Score 还是非常大。

例如第 1 个 Block 里的 Attention score 大多在 \(-2\sim2\) 附近，如果传到第 20 个 Block 时变成了 \(-50\sim50\)，softmax 就会变得特别尖锐，训练行为也会变得很不一样。LayerNorm/RMSNorm 的作用之一，**就是尽量让每个 Block 送进去的表示都保持在相近的数值尺度上，** 让各层的 Attention 不至于一层比一层“数值爆掉”。

---

<a id="origin-2309"></a>
## 36. 这就是 \(\sqrt{d_k}\) 的局限

```math
\frac{QK^T}{\sqrt{d_k}}
```

只能消除：

```text
“因为维度 d_k 很大，所以很多项相加造成的尺度膨胀”
```

它不能解决：

```text
“Q 和 K 自己本来就已经很大”
```

所以可以记成：

```text
÷ √d_k：

解决“维度效应”
```

而：

```text
LayerNorm / RMSNorm：

解决“输入本身尺度漂移”
```

---

<a id="origin-2345"></a>
## 37. 用公式看得更清楚

不要假设：

```math
Var(q_i)=1
```

而是假设：

```math
Var(q_i)=\sigma_Q^2
```

```math
Var(k_i)=\sigma_K^2
```

在近似独立的情况下：

```math
Var(q_i k_i)
\approx
\sigma_Q^2\sigma_K^2
```

所以：

```math
Var(Q\cdot K)
\approx
d_k\sigma_Q^2\sigma_K^2
```

因此：

```math
Std(Q\cdot K)
\approx
\sqrt{d_k}\sigma_Q\sigma_K
```

除以：

```math
\sqrt{d_k}
```

之后：

```math
Std\left(
\frac{Q\cdot K}{\sqrt{d_k}}
\right)
\approx
\sigma_Q\sigma_K
```

注意：

```math
\boxed{
\sqrt{d_k}
}
```

被消掉了，

但是：

```math
\boxed{
\sigma_Q\sigma_K
}
```

还在。

这就是最关键的一点。

---

<a id="origin-2427"></a>
## 38. 举个非常直观的数字例子

假设：

```math
d_k=64
```

所以：

```math
\sqrt{d_k}=8
```

<a id="origin-2441"></a>
### 38.1 情况 A：Q、K 尺度正常

假设：

```math
\sigma_Q=1
```

```math
\sigma_K=1
```

那么：

```math
Std(Q\cdot K)
\approx
8\times1\times1
=
8
```

除以：

```math
8
```

之后：

```math
Std\approx1
```

很好。

---

<a id="origin-2479"></a>
### 38.2 情况 B：Q、K 都放大 10 倍

现在：

```math
\sigma_Q=10
```

```math
\sigma_K=10
```

那么：

```math
Std(Q\cdot K)
\approx
8\times10\times10
```

即：

```math
Std(Q\cdot K)\approx800
```

即使除以：

```math
\sqrt{64}=8
```

仍然得到：

```math
800/8=100
```

也就是：

```math
Std\approx100
```

依然非常大。

所以：

```text
÷ √d_k
```

并不能拯救一个本身尺度已经失控的 \(Q\) 和 \(K\)。

---

<a id="origin-2535"></a>
## 39. LayerNorm / RMSNorm 在这里负责什么？

假设当前 hidden state：

```math
x
```

的数值越来越大：

```text
第 1 层：

[-1, 0.5, 1.2, ...]

第 10 层：

[-10, 5, 12, ...]

第 30 层：

[-100, 50, 120, ...]
```

那么：

```math
Q=xW_Q
```

```math
K=xW_K
```

也可能越来越大。

于是 Attention：

```text
x 尺度变大
   ↓
Q、K 变大
   ↓
QK^T 变大
   ↓
即使 ÷ √d_k
仍然可能很大
   ↓
softmax 过于尖锐
```

所以在进入 Attention 之前做：

```text
LayerNorm / RMSNorm
```

就可以先控制：

```math
x
```

的尺度。

---

<a id="origin-2602"></a>
## 40. Pre-Norm 下就特别直观

现代 LLM 经常写：

```math
x'
=
x+
Attention(RMSNorm(x))
```

注意 Attention 真正接收到的不是：

```math
x
```

而是：

```math
RMSNorm(x)
```

先：

```text
x
↓
RMSNorm
↓
把输入尺度控制稳定
```

然后：

```text
稳定的 hidden state
↓
W_Q、W_K、W_V
↓
Q、K、V
```

再：

```text
Q、K
↓
QK^T
↓
÷ √d_k
↓
控制“点积维度效应”
```

所以实际上是两层保护。

---

<a id="origin-2661"></a>
## 41. 两种机制可以理解成“各管一段”

完整过程：

```text
hidden state x
      ↓
   RMSNorm
      ↓
控制 x 本身的尺度
      ↓
 ┌────┼────┐
 ↓    ↓    ↓
 Q    K    V
 ↓    ↓
 └─ QK^T ──┘
      ↓
   ÷ √d_k
      ↓
控制点积因为维度增加产生的尺度膨胀
      ↓
   softmax
      ↓
Attention Output
```

所以：

```text
RMSNorm / LayerNorm
```

处理的是：

```text
进入 Attention 之前
hidden state 本身是否稳定
```

而：

```math
1/\sqrt{d_k}
```

处理的是：

```text
Attention 内部
Q 和 K 做 d_k 维点积以后产生的尺度增长
```

---

<a id="origin-2715"></a>
## 42. BatchNorm 与 RMSNorm 的区别

**标准 Transformer 里通常没有 BatchNorm。**

更准确地说：

原始 Transformer 用的是 LayerNorm
现在很多 LLM 用的是 RMSNorm
BatchNorm 在 Transformer 里不是主流配置

原因主要有三个：

Transformer 的序列长度和 batch size 经常变化
BatchNorm 依赖 batch 内统计量，不太稳定。
一个 token 不应该被同 batch 里别的样本影响

BatchNorm 会跨样本算均值/方差，而 LayerNorm、RMSNorm 是对每个 token 自己的 hidden state 做归一化。

训练和推理一致性更好

LayerNorm / RMSNorm 不需要 running_mean、running_var，训练和推理行为基本一致。

BatchNorm 和之前学习的 **RMSNorm** 都属于归一化（Normalization）方法，但它们最核心的区别是：

> **BatchNorm：不同样本之间一起计算统计量。**
> **RMSNorm：每个样本 / Token 自己内部计算统计量。**

这也是为什么：

* **BatchNorm** 在 CNN、传统 MLP 中非常常见；
* **LayerNorm / RMSNorm** 在 Transformer、LLM 中更加常见。

---

<a id="origin-2749"></a>
## 43. BatchNorm 是什么？

BatchNorm 全称：

```text
Batch Normalization
```

即：

> **批归一化**

它的核心思想是：

```text
取一个 Mini-batch
        ↓
统计某个特征在这一批样本中的均值和方差
        ↓
把这个特征归一化
        ↓
再进行缩放和平移
```

---

<a id="origin-2775"></a>
## 44. 一个最简单的 BatchNorm 例子

假设某个神经元对于一个 Batch 中的 4 个样本产生：

```text
[2, 4, 6, 8]
```

也就是：

$$
x=[2,4,6,8]
$$

---

<a id="origin-2791"></a>
### 44.1 第一步：计算 Batch 均值

$$
\mu_B
=
\frac{2+4+6+8}{4}
=
5
$$

---

<a id="origin-2803"></a>
### 44.2 第二步：计算 Batch 方差

$$
\sigma_B^2
=
\frac{
(2-5)^2+
(4-5)^2+
(6-5)^2+
(8-5)^2
}{4}
$$

因此：

$$
\sigma_B^2=5
$$

---

<a id="origin-2824"></a>
### 44.3 第三步：标准化

BatchNorm 使用：

$$
\hat{x}_i
=
\frac{x_i-\mu_B}
{\sqrt{\sigma_B^2+\epsilon}}
$$

代入：

$$
[2,4,6,8]
$$

大约得到：

$$
[-1.34,-0.45,0.45,1.34]
$$

这时候整个 Batch 的数据：

```text
均值 ≈ 0
方差 ≈ 1
```

---

<a id="origin-2856"></a>
## 45. 为什么还需要 γ 和 β？

如果永远强制网络的输出：

```text
均值 = 0
方差 = 1
```

可能会限制网络的表达能力。

因此 BatchNorm 又加入两个可学习参数：

$$
\gamma
$$

和：

$$
\beta
$$

最终：

$$
y_i
=
\gamma\hat{x}_i+\beta
$$

所以完整公式为：

$$
\boxed{
y_i
=
\gamma
\frac{x_i-\mu_B}
{\sqrt{\sigma_B^2+\epsilon}}
+
\beta
}
$$

其中：

* \(\gamma\)：控制缩放；
* \(\beta\)：控制平移。

---

<a id="origin-2908"></a>
## 46. 为什么叫 BatchNorm？

关键就在：

```text
Batch
```

假设输入矩阵：

$$
X=
\begin{bmatrix}
1&2&3\\
4&5&6\\
7&8&9
\end{bmatrix}
$$

可以理解为：

```text
           feature1   feature2   feature3

sample1       1          2          3
sample2       4          5          6
sample3       7          8          9
```

BatchNorm 会：

> **沿着 Batch 方向，对每一个 Feature 分别进行归一化。**

---

例如第一个 Feature：

$$
[1,4,7]
$$

均值：

$$
\mu_1=4
$$

第二个 Feature：

$$
[2,5,8]
$$

均值：

$$
\mu_2=5
$$

第三个 Feature：

$$
[3,6,9]
$$

均值：

$$
\mu_3=6
$$

所以 BatchNorm 是：

```text
        ↓        ↓        ↓
      feature1 feature2 feature3

样本1    1        2        3
样本2    4        5        6
样本3    7        8        9
```

即：

> 同一个特征，跨多个样本统计。

---

<a id="origin-2996"></a>
## 47. RMSNorm 是什么？

RMSNorm 全称：

```text
Root Mean Square Normalization
```

即：

> 均方根归一化。

和 BatchNorm 最大的不同是：

> RMSNorm 不需要看其他样本。

假设某个 Token 的 Hidden State：

$$
x=[1,2,3,4]
$$

RMSNorm 计算：

$$
RMS(x)
=
\sqrt{
\frac{
1^2+2^2+3^2+4^2
}{4}
+\epsilon
}
$$

因此：

$$
RMS(x)
=
\sqrt{\frac{30}{4}}
=
\sqrt{7.5}
\approx2.739
$$

然后：

$$
\hat{x}
=
\frac{x}{RMS(x)}
$$

得到：

$$
[0.365,\;0.730,\;1.095,\;1.460]
$$

最后乘一个可学习参数：

$$
y
=
\gamma\odot\hat{x}
$$

因此：

$$
\boxed{
RMSNorm(x)
=
\gamma\odot
\frac{x}
{
\sqrt{
\frac1d
\sum_{j=1}^{d}x_j^2
+\epsilon
}
}
}
$$

---

<a id="origin-3084"></a>
## 48. RMSNorm 一个非常重要的特点：不减均值

BatchNorm 中有：

$$
x-\mu
$$

LayerNorm 中也有：

$$
x-\mu
$$

但 RMSNorm：

$$
\boxed{
没有减均值
}
$$

它只控制：

> 整个向量的数值尺度。

所以：

```text
LayerNorm

减均值
   +
除标准差
```

而：

```text
RMSNorm

不减均值
   +
除 RMS
```

---

<a id="origin-3132"></a>
## 49. BatchNorm 和 RMSNorm 最核心的区别

假设：

$$
X\in\mathbb{R}^{B\times D}
$$

其中：

* \(B\)：Batch Size；
* \(D\)：特征维度。

例如：

$$
X\in\mathbb{R}^{32\times4096}
$$

---

<a id="origin-3153"></a>
### 49.1 BatchNorm

它会：

```text
第1维特征：
32个样本一起统计

第2维特征：
32个样本一起统计

...

第4096维特征：
32个样本一起统计
```

即：

$$
\boxed{
沿Batch维统计
}
$$

---

<a id="origin-3180"></a>
### 49.2 RMSNorm

对于第一个样本：

```text
它自己的4096维
↓
计算RMS
↓
归一化
```

第二个样本：

```text
它自己的4096维
↓
计算RMS
↓
归一化
```

彼此完全独立。

即：

$$
\boxed{
沿特征维统计
}
$$

---

<a id="origin-3214"></a>
## 50. 一个特别直观的图

假设：

$$
X=
\begin{bmatrix}
1&2&3\\
4&5&6\\
7&8&9
\end{bmatrix}
$$

---

<a id="origin-3229"></a>
### 50.1 BatchNorm：竖着算

```text
↓     ↓     ↓

1     2     3
4     5     6
7     8     9
```

例如：

```text
[1, 4, 7]
```

一起归一化。

---

<a id="origin-3249"></a>
### 50.2 RMSNorm：横着算

```text
1  2  3  →
4  5  6  →
7  8  9  →
```

例如：

```text
[1, 2, 3]
```

自己归一化。

---

<a id="origin-3267"></a>
## 51. BatchNorm 的一个特殊性质：一个样本受其他样本影响

假设当前某个值：

$$
x=5
$$

---

<a id="origin-3277"></a>
### 51.1 Batch A

```text
[4, 5, 6]
```

均值：

$$
\mu=5
$$

所以：

$$
5-5=0
$$

归一化以后接近：

$$
0
$$

---

<a id="origin-3303"></a>
### 51.2 Batch B

换一个 Batch：

```text
[5, 100, 200]
```

此时均值：

$$
\mu
=
\frac{5+100+200}{3}
\approx101.67
$$

虽然：

$$
x
$$

仍然是：

$$
5
$$

但归一化结果已经完全不同。

所以：

$$
\boxed{
BatchNorm中一个样本的结果
会受到同一个Batch中其他样本影响
}
$$

---

<a id="origin-3345"></a>
## 52. RMSNorm 不存在这个问题

假设当前 Token：

$$
x=[1,2,3,4]
$$

RMSNorm 只计算：

$$
RMS(x)
$$

至于 Batch 里面还有什么：

```text
样本A
样本B
样本C
样本D
```

都没有关系。

因此：

$$
\boxed{
RMSNorm不同样本之间互不影响
}
$$

---

<a id="origin-3380"></a>
## 53. BatchNorm 为什么有效？

神经网络训练过程中，每一层的输出分布可能不断发生变化。

例如：

```text
Epoch 1：

均值 ≈ 0
方差 ≈ 1
```

过一段时间：

```text
Epoch 10：

均值 ≈ 20
方差 ≈ 100
```

再过一段时间：

```text
Epoch 20：

均值 ≈ -30
方差 ≈ 500
```

后面的网络层就需要不断适应前面的数值变化。

BatchNorm 相当于不断做：

```text
某层输出
   ↓
数值尺度可能很乱
   ↓
BatchNorm
   ↓
重新拉回比较稳定的范围
```

因此训练通常：

* 更稳定；
* 可以使用更大的学习率；
* 更容易收敛。

---

<a id="origin-3433"></a>
## 54. BatchNorm 在 MLP 中放在哪里？

一种经典结构：

```text
Linear
  ↓
BatchNorm
  ↓
ReLU
```

也就是：

$$
x
$$

先经过：

$$
z=Wx+b
$$

然后：

$$
BN(z)
$$

再：

$$
ReLU
$$

完整流程：

```text
输入
 ↓
Linear
 ↓
BatchNorm
 ↓
ReLU
 ↓
Linear
 ↓
BatchNorm
 ↓
ReLU
 ↓
输出层
```

---

<a id="origin-3491"></a>
## 55. BatchNorm 在 CNN 中为什么特别常见？

经典 CNN 中经常看到：

```text
Conv
 ↓
BatchNorm
 ↓
ReLU
```

例如：

```python
nn.Conv2d(...)
nn.BatchNorm2d(...)
nn.ReLU()
```

原因是 CNN 的 Feature Channel 非常适合做 Batch 统计。

---

<a id="origin-3515"></a>
## 56. 为什么 Transformer 很少使用 BatchNorm？

Transformer 中的数据通常是：

$$
X
\in
\mathbb{R}^{B\times T\times D}
$$

例如：

$$
B=32
$$

$$
T=1024
$$

$$
D=4096
$$

分别表示：

```text
32个句子
每个句子1024个Token
每个Token 4096维
```

如果使用 BatchNorm：

> 某一个 Token 的归一化结果可能受到其他句子影响。

例如：

```text
句子1：
我 喜欢 人工 智能
```

其中：

```text
人工
```

这个 Token 的 Hidden State，理论上应该主要由：

```text
当前句子
当前上下文
```

决定。

但 BatchNorm 可能让它受到：

```text
Batch里面另外31个句子
```

的影响。

这对 Transformer 并不是非常理想。

---

<a id="origin-3585"></a>
## 57. RMSNorm 为什么更适合 Transformer？

假设 Transformer 某个 Token：

$$
x
\in
\mathbb{R}^{4096}
$$

RMSNorm：

```text
当前Token的4096维
        ↓
     计算RMS
        ↓
      归一化
```

完全不需要其他 Token 或其他样本。

因此：

```text
Token A
自己处理

Token B
自己处理

Token C
自己处理
```

这非常符合 Transformer 的计算方式。

---

<a id="origin-3624"></a>
## 58. BatchNorm 还有一个麻烦：训练和推理行为不同

BatchNorm 在训练阶段：

```text
当前Batch
   ↓
计算均值
   ↓
计算方差
```

比如：

$$
\mu_B
$$

以及：

$$
\sigma_B^2
$$

---

但是推理的时候可能只有：

```text
1个样本
```

例如：

```text
Batch Size = 1
```

这时候当前 Batch 的统计量就不可靠。

所以 BatchNorm 在训练过程中会额外维护：

```text
running_mean
running_var
```

即：

> 均值和方差的滑动平均。

---

<a id="origin-3677"></a>
## 59. BatchNorm 的 Running Mean

例如：

$$
running\_mean
\leftarrow
(1-m)
running\_mean
+
m\mu_B
$$

类似地：

$$
running\_var
\leftarrow
(1-m)
running\_var
+
m\sigma_B^2
$$

---

训练的时候：

```text
使用当前Batch统计量
```

推理的时候：

```text
使用running_mean
使用running_var
```

因此：

$$
\boxed{
BatchNorm训练和推理行为不同
}
$$

---

<a id="origin-3726"></a>
## 60. 为什么 model.train() 和 model.eval() 很重要？

PyTorch 中：

```python
model.train()
```

表示训练模式。

BatchNorm 使用：

```text
当前Batch均值
当前Batch方差
```

并更新：

```text
running_mean
running_var
```

---

而：

```python
model.eval()
```

表示推理模式。

BatchNorm 使用：

```text
running_mean
running_var
```

不再使用当前 Batch 的统计量。

因此：

```text
model.train()
```

和：

```text
model.eval()
```

对 BatchNorm 是有实际影响的。

---

<a id="origin-3785"></a>
## 61. RMSNorm 不需要 Running Mean

RMSNorm 每次都只需要：

$$
x
$$

本身。

例如：

```text
训练：
当前Token自己计算RMS
```

推理：

```text
当前Token还是自己计算RMS
```

因此 RMSNorm 不需要：

```text
running_mean
running_var
```

训练和推理的计算方式基本一样。

---

<a id="origin-3819"></a>
## 62. Batch Size 对 BatchNorm 的影响

因为 BatchNorm 依赖：

$$
\mu_B
$$

和：

$$
\sigma_B^2
$$

因此：

```text
Batch Size越大
↓
统计量通常越稳定
```

而：

```text
Batch Size特别小
↓
均值和方差估计容易不稳定
```

例如：

```text
Batch Size = 1
```

BatchNorm 可能就会产生明显问题。

---

而 RMSNorm：

```text
Batch Size = 1

Batch Size = 8

Batch Size = 128
```

基本都没有这个问题。

因为每个样本自己算。

---

<a id="origin-3875"></a>
## 63. BatchNorm、LayerNorm、RMSNorm 放在一起看

这是理解这三个 Normalization 最推荐的方法。

假设：

$$
X=
\begin{bmatrix}
1&2&3\\
4&5&6\\
7&8&9
\end{bmatrix}
$$

---

<a id="origin-3892"></a>
### 63.1 BatchNorm

跨样本：

```text
↓     ↓     ↓

1     2     3
4     5     6
7     8     9
```

即：

> 同一个 Feature，不同样本一起归一化。

---

<a id="origin-3910"></a>
### 63.2 LayerNorm

每个样本自己：

```text
1  2  3  →

4  5  6  →

7  8  9  →
```

但 LayerNorm 会：

<a id="origin-3924"></a>
#### 63.2.1 第一步

减均值：

$$
x-\mu
$$

<a id="origin-3932"></a>
#### 63.2.2 第二步

除标准差：

$$
\frac{x-\mu}
{\sqrt{\sigma^2+\epsilon}}
$$

---

<a id="origin-3943"></a>
### 63.3 RMSNorm

同样是：

```text
1  2  3  →

4  5  6  →

7  8  9  →
```

但 RMSNorm 不减均值。

只计算：

$$
\frac{x}
{\sqrt{mean(x^2)+\epsilon}}
$$

---

<a id="origin-3966"></a>
## 64. LayerNorm 和 RMSNorm 的关系

LayerNorm：

$$
\boxed{
LayerNorm(x)
=
\gamma
\frac{x-\mu}
{\sqrt{\sigma^2+\epsilon}}
+\beta
}
$$

而 RMSNorm：

$$
\boxed{
RMSNorm(x)
=
\gamma
\frac{x}
{\sqrt{mean(x^2)+\epsilon}}
}
$$

因此可以粗略理解：

```text
LayerNorm
   ↓
去掉中心化过程
   ↓
RMSNorm
```

也就是说：

$$
\boxed{
RMSNorm更像是LayerNorm的简化版
}
$$

而不是：

$$
RMSNorm
$$

是 BatchNorm 的简化版。

---

<a id="origin-4021"></a>
## 65. 三种 Norm 最重要的区别

| 特征              | BatchNorm | LayerNorm | RMSNorm |
| --------------- | --------- | --------- | ------- |
| 统计范围            | 多个样本之间    | 单个样本内部    | 单个样本内部  |
| 跨 Batch         | 是         | 否         | 否       |
| 减均值             | 是         | 是         | 否       |
| 除标准差            | 是         | 是         | 否       |
| 除 RMS           | 否         | 否         | 是       |
| \(\gamma\)      | 有         | 有         | 有       |
| \(\beta\)       | 通常有       | 有         | 通常没有    |
| 依赖 Batch Size   | 强         | 否         | 否       |
| Running Mean    | 有         | 无         | 无       |
| Running Var     | 有         | 无         | 无       |
| Train / Eval 不同 | 是         | 基本相同      | 基本相同    |
| CNN             | 常见        | 较少        | 较少      |
| Transformer     | 少见        | 常见        | 非常常见    |
| LLM             | 少见        | 常见        | 非常常见    |

---

<a id="origin-4042"></a>
## 66. 最容易记忆的方法

可以把三种方法理解成：

```text
Normalization
       │
       ├──────────────────────┐
       │                      │
    看别人                  看自己
       │                      │
  BatchNorm          ┌────────┴────────┐
                     │                 │
                LayerNorm          RMSNorm
                     │                 │
               减均值+除方差       只控制RMS
```

---

<a id="origin-4062"></a>
## 67. 一句话理解 BatchNorm

> **BatchNorm：看看同一个 Batch 里，别人这个特征是什么水平，然后把自己调整到统一尺度。**

---

<a id="origin-4068"></a>
## 68. 一句话理解 LayerNorm

> **LayerNorm：不管别人，只看自己这一整组特征，把自己的均值和方差标准化。**

---

<a id="origin-4074"></a>
## 69. 一句话理解 RMSNorm

> **RMSNorm：也不管别人，只看自己的数值大小，而且连均值都不减，只控制整体尺度。**

---

<a id="origin-4080"></a>
## 70. 对 Transformer 最重要的理解

Transformer 中通常有：

$$
X
\in
\mathbb{R}^{B\times T\times D}
$$

对于一个 Token：

$$
x_{b,t}
\in
\mathbb{R}^{D}
$$

RMSNorm 做的是：

$$
\boxed{
对这个Token自己的D维Hidden State做归一化
}
$$

而不是：

$$
\boxed{
对整个Batch做归一化
}
$$

所以：

```text
Token
 ↓
D维Hidden State
 ↓
RMSNorm
 ↓
控制这个Token自身的数值尺度
```

这就是 RMSNorm 特别适合 Transformer / LLM 的核心原因之一。

---

<a id="origin-4130"></a>
## 71. 最终总结

<a id="origin-4132"></a>
### 71.1 BatchNorm

核心：

$$
\boxed{
跨样本统计
}
$$

计算：

$$
\mu_B
$$

和：

$$
\sigma_B^2
$$

然后：

$$
\frac{x-\mu_B}
{\sqrt{\sigma_B^2+\epsilon}}
$$

特点：

```text
依赖Batch
训练和推理不同
需要running_mean / running_var
CNN中非常常见
```

---

<a id="origin-4172"></a>
### 71.2 RMSNorm

核心：

$$
\boxed{
每个样本 / Token 自己统计
}
$$

计算：

$$
RMS(x)
=
\sqrt{mean(x^2)+\epsilon}
$$

然后：

$$
\frac{x}{RMS(x)}
$$

特点：

```text
不跨样本
不减均值
不依赖Batch Size
不需要Running Mean / Var
非常适合Transformer / LLM
```

---

最核心的一句话：

$$
\boxed{
BatchNorm看Batch中的“别人”，
RMSNorm只看“自己”。
}
$$

而 RMSNorm 与 LayerNorm 的关系更近：

$$
\boxed{
RMSNorm
\approx
LayerNorm
-
均值中心化
}
$$

<a id="origin-4229"></a>
## 72. RMSNorm 与 Gradient Clipping：从公式区别到 RMS=1 的意义

<a id="origin-4231"></a>
## 73. RMSNorm 和 Gradient Clipping 看起来很像，为什么公式却不一样？

RMSNorm 和 Gradient Clipping 都会涉及：

```text
平方
↓
求和
↓
开根号
↓
再用这个值去缩放向量
```

所以第一次看到的时候，很容易觉得：

> 它们是不是其实在做同一件事情？

其实不是。

二者虽然数学形式有一些相似，但**处理的对象不同、目标不同、发生的位置不同**。

可以先记住一句话：

> **RMSNorm 是在控制前向传播中的 hidden state 尺度；Gradient Clipping 是在控制反向传播中的梯度尺度。**

---

<a id="origin-4259"></a>
## 74. RMSNorm 的公式

假设 hidden state 为：

$$
x=[x_1,x_2,\dots,x_d]
$$

RMS 定义为：

$$
\operatorname{RMS}(x)
=
\sqrt{
\frac{1}{d}
\sum_{i=1}^{d}x_i^2+\epsilon
}
$$

RMSNorm 的核心操作为：

$$
\hat{x}
=
\frac{x}{\operatorname{RMS}(x)}
$$

实际模型中通常还会乘一个可学习参数：

$$
y
=
\gamma
\odot
\frac{x}{
\sqrt{
\frac{1}{d}
\sum_{i=1}^{d}x_i^2+\epsilon
}
}
$$

其中：

* \(d\)：hidden size；
* \(\epsilon\)：防止除零的小常数；
* \(\gamma\)：可学习的缩放参数。

---

<a id="origin-4309"></a>
## 75. Gradient Clipping 的公式

假设梯度向量为：

$$
g
$$

它的 L2 Norm 为：

$$
\|g\|_2
=
\sqrt{
\sum_i g_i^2
}
$$

如果最大允许梯度范数为：

$$
C
$$

那么 Gradient Clipping 可以写成：

$$
g_{\text{clip}}
=
g
\cdot
\min
\left(
1,
\frac{C}{\|g\|_2}
\right)
$$

它表达的意思非常简单。

如果：

$$
\|g\|_2\le C
$$

那么：

$$
g_{\text{clip}}=g
$$

完全不修改。

如果：

$$
\|g\|_2>C
$$

才进行缩放：

$$
g_{\text{clip}}
=
g\frac{C}{\|g\|_2}
$$

使得：

$$
\|g_{\text{clip}}\|_2=C
$$

---

<a id="origin-4385"></a>
## 76. 二者最核心的区别

可以先从目标上理解。

<a id="origin-4389"></a>
### 76.1 RMSNorm

RMSNorm 的目标是：

> **把 hidden state 的整体数值尺度拉回到一个稳定的参考范围。**

它会持续进行归一化。

例如：

```text
[1, 2, 3]
    ↓ RMSNorm

[10, 20, 30]
    ↓ RMSNorm

[1000, 2000, 3000]
    ↓ RMSNorm
```

虽然三个向量大小完全不同，但是经过 RMSNorm 后，它们会得到非常相似的结果。

---

<a id="origin-4414"></a>
### 76.2 Gradient Clipping

Gradient Clipping 的目标不是归一化。

它的目标是：

> **梯度正常的时候完全不管，只有梯度过大的时候才限制它。**

例如设置：

$$
C=5
$$

对于：

$$
g=[0.3,0.4]
$$

有：

$$
\|g\|=0.5
$$

没有超过 5，所以：

$$
g_{\text{clip}}
=
[0.3,0.4]
$$

不会改变。

对于：

$$
g=[30,40]
$$

有：

$$
\|g\|=50
$$

超过 5，所以：

$$
g_{\text{clip}}
=
[30,40]
\times
\frac{5}{50}
$$

得到：

$$
[3,4]
$$

此时：

$$
\|g_{\text{clip}}\|=5
$$

---

所以二者可以这样记：

```text
RMSNorm
=
归一化器
=
主动稳定尺度


Gradient Clipping
=
限幅器
=
超过阈值才干预
```

---

<a id="origin-4505"></a>
## 77. 为什么 RMSNorm 有 \(\frac{1}{d}\)，Clip 却没有？

这是一个非常重要的区别。

RMSNorm 计算的是：

$$
\sqrt{
\frac{1}{d}
\sum_i x_i^2
}
$$

Gradient Clipping 通常计算：

$$
\sqrt{
\sum_i g_i^2
}
$$

为什么一个有：

$$
\frac{1}{d}
$$

一个没有？

因为二者关注的东西不同。

---

<a id="origin-4538"></a>
### 77.1 RMSNorm 关注的是每个维度的整体数值尺度

考虑：

$$
x=[1,1]
$$

L2 Norm 为：

$$
\sqrt{1^2+1^2}
=
\sqrt2
$$

如果变成 4096 维：

$$
x=[1,1,\dots,1]
$$

一共有 4096 个 1。

那么：

$$
\|x\|_2
=
\sqrt{4096}
=
64
$$

但是从神经网络激活值的角度来看，这两个向量其实没有本质区别：

```text
2维情况：
每一维都是 1

4096维情况：
每一维仍然都是 1
```

所以如果只是因为维度变多，就说：

```text
向量尺度从 1.4 变成了 64
```

并不适合描述 hidden state 中每一维的数值水平。

因此 RMSNorm 使用：

$$
\sqrt{
\frac{1}{d}
\sum_i x_i^2
}
$$

对于：

$$
[1,1,\dots,1]
$$

无论是 2 维还是 4096 维：

$$
\operatorname{RMS}(x)=1
$$

所以 RMS 描述的是：

> **每个维度整体处于什么数值量级。**

---

<a id="origin-4617"></a>
### 77.2 Gradient Clipping 关注的是整个梯度更新有多大

Gradient Clipping 想回答的问题是：

> 这一次参数更新所对应的整个梯度向量到底有多长？

所以它直接计算：

$$
\|g\|_2
=
\sqrt{\sum_i g_i^2}
$$

它关注的是：

$$
\boxed{\text{整个梯度向量的总长度}}
$$

因此不除以维度 \(d\)。

---

<a id="origin-4641"></a>
## 78. 二者背后的真正意义

如果把 Transformer 的训练过程画出来：

```text
                前向传播

输入
 ↓
Embedding
 ↓
Hidden State
 ↓
RMSNorm
 ↓
Attention
 ↓
Hidden State
 ↓
RMSNorm
 ↓
FFN
 ↓
...
 ↓
Loss


                反向传播

Loss
 ↓
Gradient
 ↓
Gradient
 ↓
Gradient
 ↓
Gradient Clipping
 ↓
Optimizer
 ↓
更新参数
```

所以：

> **RMSNorm 管的是网络里面的信号怎么稳定地流。**

而：

> **Gradient Clipping 管的是参数怎么稳定地学。**

---

<a id="origin-4696"></a>
## 79. RMSNorm 为什么需要稳定 hidden state？

假设一个很深的 Transformer 中，hidden state 不断放大：

```text
第 1 层：

[1, 2, 3]


第 10 层：

[10, 20, 30]


第 30 层：

[1000, 2000, 3000]
```

注意：

$$
[1,2,3]
$$

和：

$$
[10,20,30]
$$

以及：

$$
[1000,2000,3000]
$$

它们的比例关系完全一样。

也就是说，它们的方向基本一样，只是整体尺度越来越大。

---

但是 Transformer 后面要计算：

$$
Q=xW_Q
$$

$$
K=xW_K
$$

然后：

$$
QK^T
$$

如果：

$$
x\rightarrow 100x
$$

那么大致会导致：

$$
Q\rightarrow100Q
$$

$$
K\rightarrow100K
$$

于是：

$$
QK^T
\rightarrow
10000QK^T
$$

也就是：

$$
100^2=10000
$$

倍。

这样 Softmax 的输入就可能变得特别大。

原本：

$$
[1,2,3]
$$

经过 Softmax 后还比较平滑。

如果变成：

$$
[100,200,300]
$$

Softmax 可能已经非常接近：

$$
[0,0,1]
$$

这会让 Attention 变得非常尖锐，训练也更容易不稳定。

因此 RMSNorm 要解决的问题是：

> **不要让 hidden state 的绝对尺度在网络中不断漂移。**

---

<a id="origin-4818"></a>
## 80. Gradient Clipping 为什么需要限制梯度？

假设某个参数：

$$
\theta=1
$$

学习率：

$$
\eta=0.001
$$

正常梯度为：

$$
g=10
$$

更新：

$$
\theta'
=
\theta-\eta g
$$

所以：

$$
\theta'
=
1-0.001\times10
=
0.99
$$

这是一个正常的小变化。

但是如果某一个 batch 导致梯度突然变成：

$$
g=100000
$$

那么：

$$
\theta'
=
1-0.001\times100000
$$

得到：

$$
\theta'=-99
$$

原本参数在：

$$
1
$$

附近。

一次更新直接跳到了：

$$
-99
$$

这就可能把之前训练很多步得到的参数状态直接破坏掉。

因此 Gradient Clipping 的意义就是：

> **允许模型正常学习，但是不允许一次参数更新迈得过大。**

所以它更像一个安全护栏。

---

<a id="origin-4902"></a>
## 81. RMSNorm 为什么这个公式就可以让尺度稳定？

这是 RMSNorm 最核心的数学原因。

先忽略 \(\gamma\) 和 \(\epsilon\)。

定义：

$$
y
=
\frac{x}{\operatorname{RMS}(x)}
$$

而：

$$
\operatorname{RMS}(x)
=
\sqrt{
\frac1d
\sum_{i=1}^{d}x_i^2
}
$$

现在来看归一化后的向量 \(y\) 的 RMS 是多少。

有：

$$
y_i
=
\frac{x_i}{
\sqrt{
\frac1d\sum_jx_j^2
}
}
$$

因此：

$$
\operatorname{RMS}(y)
=
\sqrt{
\frac1d
\sum_i y_i^2
}
$$

代入：

$$
=
\sqrt{
\frac1d
\sum_i
\left(
\frac{x_i}{
\sqrt{
\frac1d\sum_jx_j^2
}
}
\right)^2
}
$$

整理：

$$
=
\sqrt{
\frac{
\frac1d\sum_i x_i^2
}{
\frac1d\sum_j x_j^2
}
}
$$

分子和分母完全一样：

$$
=
\sqrt1
$$

因此：

$$
\boxed{
\operatorname{RMS}(y)=1
}
$$

也就是说：

> RMSNorm 不是“希望”把尺度稳定在 1 附近，而是它的数学公式直接决定了，归一化后的 RMS 就是 1。

---

<a id="origin-5003"></a>
## 82. 举一个具体例子

假设：

$$
x=[1,2,3]
$$

那么：

$$
\operatorname{RMS}(x)
=
\sqrt{
\frac{1^2+2^2+3^2}{3}
}
$$

即：

$$
=
\sqrt{
\frac{14}{3}
}
$$

约等于：

$$
2.16
$$

因此：

$$
\frac{x}{\operatorname{RMS}(x)}
$$

得到：

$$
[
0.463,
0.926,
1.389
]
$$

再计算它的 RMS：

$$
\sqrt{
\frac{
0.463^2
+
0.926^2
+
1.389^2
}{3}
}
\approx1
$$

---

现在假设原来的向量整体放大 1000 倍：

$$
x'=[1000,2000,3000]
$$

它的 RMS：

$$
\operatorname{RMS}(x')
\approx2160
$$

所以：

$$
\frac{x'}{\operatorname{RMS}(x')}
$$

仍然得到：

$$
[
0.463,
0.926,
1.389
]
$$

于是：

```text
[1, 2, 3]
      ↓ RMSNorm

[0.463, 0.926, 1.389]


[1000, 2000, 3000]
      ↓ RMSNorm

[0.463, 0.926, 1.389]
```

这就是 RMSNorm 抑制尺度漂移的核心原因。

---

<a id="origin-5117"></a>
## 83. RMSNorm 具有尺度不变性

假设一个 hidden state 为：

$$
x
$$

现在整体放大 \(c\) 倍：

$$
x'=cx
$$

那么：

$$
\operatorname{RMS}(cx)
=
|c|
\operatorname{RMS}(x)
$$

因此：

$$
\frac{cx}{
\operatorname{RMS}(cx)
}
=
\frac{cx}{
|c|\operatorname{RMS}(x)
}
$$

如果：

$$
c>0
$$

那么：

$$
=
\frac{x}{
\operatorname{RMS}(x)
}
$$

所以：

$$
\boxed{
\operatorname{RMSNorm}(cx)
=
\operatorname{RMSNorm}(x)
}
$$

先忽略 \(\gamma\)。

这个性质非常重要。

它意味着：

> 上一层就算把整个 hidden state 放大 10 倍、100 倍甚至 10000 倍，经过 RMSNorm 之后，下一层看到的整体尺度仍然基本一样。

所以：

```text
[1, 2, 3]

[10, 20, 30]

[1000, 2000, 3000]
```

虽然绝对数值完全不同，但 RMSNorm 可以把这种整体尺度差异消掉。

---

<a id="origin-5199"></a>
## 84. 为什么一定要变成 1？

这里还有一个很重要的问题：

> 为什么 RMSNorm 偏偏把 RMS 归一化成 1？

其实：

$$
\boxed{\text{并不是必须是 1}}
$$

理论上完全可以定义：

$$
y
=
5
\frac{x}{
\operatorname{RMS}(x)
}
$$

那么：

$$
\operatorname{RMS}(y)=5
$$

也可以写成：

$$
y
=
10
\frac{x}{
\operatorname{RMS}(x)
}
$$

那么：

$$
\operatorname{RMS}(y)=10
$$

数学上都没有问题。

---

<a id="origin-5249"></a>
## 85. 真正重要的是“固定尺度”，不是数字 1 本身

RMSNorm 真正希望做到的是：

```text
原来：

这一层 RMS = 0.01

下一层 RMS = 20

再下一层 RMS = 5000


经过归一化之后：

RMS ≈ 固定值

RMS ≈ 固定值

RMS ≈ 固定值
```

所以真正重要的是：

$$
\boxed{\text{尺度固定}}
$$

而不是：

$$
\boxed{\text{必须等于 1}}
$$

---

<a id="origin-5286"></a>
## 86. 为什么通常选择 1？

因为 1 是最自然的“单位尺度”。

数学和数值计算中，经常希望变量处在：

$$
O(1)
$$

附近。

例如：

```text
0.5
-0.8
1.2
1.5
-1.1
```

这些数字不会特别大，也不会特别小。

相比：

```text
0.00000001

或者

100000000
```

这种数量级更加适合数值计算。

所以让 RMS 约为 1，相当于：

> 把 hidden state 放进一个比较舒服的单位尺度范围中。

---

<a id="origin-5328"></a>
## 87. 为什么不归一化成 0？

因为如果：

$$
\operatorname{RMS}(x)=0
$$

那么一定有：

$$
x_i=0
$$

对所有维度成立。

也就是：

$$
x=[0,0,\dots,0]
$$

所有信息都消失了。

因此显然不能把尺度标准化成 0。

---

<a id="origin-5356"></a>
## 88. 为什么不统一成 100？

理论上可以，但是没有必要。

如果把 hidden state 的 RMS 固定到：

$$
100
$$

那么很多维度可能都会处在几十到几百的数量级。

后面还要计算：

$$
Q=xW_Q
$$

$$
K=xW_K
$$

以及：

$$
QK^T
$$

数值自然也会更大。

那么为了补偿这个大尺度，就需要把：

```text
权重初始化
学习率
其他层的缩放系数
```

重新相应调整。

既然如此，直接使用：

$$
1
$$

作为单位尺度是最简单自然的选择。

---

<a id="origin-5406"></a>
## 89. RMS=1 不等于每一维都等于 1

这是非常容易误解的地方。

例如：

$$
x=
[
0.463,
0.926,
1.389
]
$$

它的 RMS 大约是：

$$
1
$$

但显然：

```text
第一维 ≠ 1
第二维 ≠ 1
第三维 ≠ 1
```

RMS=1 的意思是：

> 这些维度整体的数值尺度处在 1 这个量级。

而不是：

> 每一个元素都必须变成 1。

---

<a id="origin-5445"></a>
## 90. RMS=1 也不等于 L2 Norm=1

这两个概念一定要区分。

RMS 定义为：

$$
\operatorname{RMS}(x)
=
\sqrt{
\frac1d
\sum_i x_i^2
}
$$

如果：

$$
\operatorname{RMS}(x)=1
$$

那么：

$$
\frac1d
\sum_i x_i^2
=
1
$$

因此：

$$
\sum_i x_i^2=d
$$

所以：

$$
\|x\|_2
=
\sqrt d
$$

而不是：

$$
1
$$

---

例如 Transformer 中：

$$
d=4096
$$

如果：

$$
\operatorname{RMS}(x)=1
$$

那么：

$$
\|x\|_2
=
\sqrt{4096}
=
64
$$

所以：

$$
\boxed{
\operatorname{RMS}(x)=1
}
$$

并不意味着：

$$
\boxed{
\|x\|_2=1
}
$$

---

<a id="origin-5537"></a>
## 91. 那么“典型数值大小约为 1”到底是什么意思？

这里说的：

> “典型数值”

不是一个新的严格数学术语。

它只是帮助理解 RMS 的一种直观说法。

更严谨的表达应该是：

> **这个向量中各维度的整体数值尺度大约处在 1 这个数量级。**

---

比如：

$$
x=
[
0.5,
1.0,
-1.2,
1.4,
-0.8
]
$$

这里面的数虽然并不都等于 1，但是基本都在：

$$
1
$$

附近的量级。

所以可以口语化地说：

> 这些数的典型大小大约是 1。

---

<a id="origin-5580"></a>
## 92. 为什么 RMS 可以表示“整体数值大小”？

假设：

$$
x=[1,2,3]
$$

它的 RMS：

$$
\sqrt{
\frac{1+4+9}{3}
}
\approx2.16
$$

所以可以理解为：

> 这个向量中的元素整体处于 2 左右的数值尺度。

注意，并不是说：

```text
每一个元素都等于 2.16
```

而是说：

```text
整个向量的元素大小，大致处在这个量级。
```

---

再比如：

$$
x=[100,200,300]
$$

那么：

$$
\operatorname{RMS}(x)
\approx216
$$

所以它的整体数值尺度大约在：

$$
200
$$

这个量级。

---

<a id="origin-5638"></a>
## 93. 为什么不用普通平均值衡量大小？

因为 hidden state 有正有负。

比如：

$$
x=[10,-10]
$$

普通平均值为：

$$
\frac{10+(-10)}{2}
=
0
$$

如果按照平均值来看，好像这个向量：

```text
大小≈0
```

显然不合理。

因为两个元素实际上都非常大：

$$
10
$$

和：

$$
-10
$$

---

RMS 会先平方：

$$
10^2=100
$$

$$
(-10)^2=100
$$

然后取平均：

$$
\frac{100+100}{2}
=
100
$$

最后开根号：

$$
\sqrt{100}=10
$$

所以：

$$
\operatorname{RMS}([10,-10])=10
$$

这就能够正确表示：

> 这些元素的数值大小大约处于 10 的量级。

---

<a id="origin-5714"></a>
## 94. “典型数值”最准确的理解

所以以后看到：

> RMSNorm 让每个维度的典型数值大小变成 1。

更准确地理解应该是：

$$
\boxed{
\sqrt{
\frac1d
\sum_i x_i^2
}
\approx1
}
$$

也就是：

> **整个 hidden state 中，各个维度的整体数值尺度被控制在单位尺度附近。**

而不是：

$$
x_i=1
$$

---

<a id="origin-5744"></a>
## 95. 为什么 O(1) 的尺度适合神经网络？

假设 hidden state：

$$
x_i\sim O(1)
$$

也就是说，各维度通常大约处于：

```text
0.x
1.x
-0.x
-1.x
```

这种数量级。

而神经网络的权重初始化通常也会根据输入维度控制权重的尺度。

例如可以粗略理解为：

$$
W_{ij}
\sim
O\left(
\frac1{\sqrt d}
\right)
$$

进行线性变换：

$$
y=xW
$$

其中：

$$
y_j
=
\sum_{i=1}^{d}
x_iW_{ij}
$$

虽然有很多项相加，但是由于权重尺度进行了合理设计，输出仍然可以保持在：

$$
O(1)
$$

附近。

于是可以形成：

```text
输入：

O(1)

↓

线性层

↓

输出：

O(1)

↓

RMSNorm

↓

继续：

O(1)

↓

下一层
```

这就是深层网络希望保持的一种稳定数值状态。

---

<a id="origin-5834"></a>
## 96. 既然归一化到 1，为什么后面还需要 \(\gamma\)？

真实 RMSNorm 通常是：

$$
y_i
=
\gamma_i
\frac{x_i}{
\operatorname{RMS}(x)
}
$$

这里的：

$$
\gamma_i
$$

是可以学习的。

为什么刚刚才把所有东西归一化，马上又允许它重新放大？

因为 RMSNorm 真正想去掉的是：

> **不可控的整体尺度漂移。**

但并不希望：

> **限制模型自己学习不同维度的重要程度。**

---

例如归一化后：

$$
[
0.5,
1.0,
1.5
]
$$

模型可能学习出：

$$
\gamma=
[
2,
0.5,
3
]
$$

于是最终：

$$
y=
[
1.0,
0.5,
4.5
]
$$

也就是说：

```text
RMSNorm：

先建立统一尺度
        ↓
消除不可控的整体放大/缩小
        ↓
γ 再让模型自己决定
每一维应该有多大
```

所以可以理解为：

> **RMSNorm 负责“先把尺度整理干净”，\(\gamma\) 再负责“让模型自己重新学习合理的尺度”。**

---

<a id="origin-5918"></a>
## 97. RMSNorm 和 Gradient Clipping 的最终对比

| 对比项          | RMSNorm                   | Gradient Clipping |
| ------------ | ------------------------- | ----------------- |
| 发生位置         | 前向传播                      | 反向传播之后、参数更新之前     |
| 处理对象         | Hidden State / Activation | Gradient          |
| 核心目标         | 稳定内部信号尺度                  | 防止梯度过大            |
| 是否一直执行       | 是                         | 是检查，但只有超过阈值才缩放    |
| 是否强制固定尺度     | 是，先归一到 RMS≈1              | 否                 |
| 使用的尺度        | RMS                       | L2 Norm           |
| 是否除以维度 \(d\) | 是                         | 通常否               |
| 本质           | 归一化                       | 限幅                |
| 解决的问题        | Activation 尺度漂移           | 梯度爆炸/单次更新过猛       |

---

<a id="origin-5934"></a>
## 98. 一句话总结 RMSNorm

RMSNorm 的核心公式：

$$
\boxed{
\hat{x}
=
\frac{x}{
\sqrt{
\frac1d
\sum_i x_i^2
}
}
}
$$

之所以能够稳定 hidden state，是因为：

$$
\boxed{
\operatorname{RMS}(\hat{x})=1
}
$$

它相当于使用：

> **当前向量自己的整体数值尺度**

去除：

> **当前向量本身**

从而消除：

```text
整体放大 10 倍
整体放大 100 倍
整体放大 10000 倍
```

这类尺度漂移。

---

<a id="origin-5979"></a>
## 99. 最终可以这样理解整个故事

```text
Transformer 前向传播：

Hidden State
可能越来越大或越来越小
        ↓
RMSNorm
        ↓
用自己的 RMS 除自己
        ↓
整体数值尺度回到 RMS≈1
        ↓
让下一层始终接收到
比较稳定的 O(1) 输入
```

而反向传播：

```text
Loss
 ↓
Gradient
 ↓
某一次 Gradient 可能突然特别大
 ↓
Gradient Clipping
 ↓
超过阈值才等比例缩小
 ↓
防止一次参数更新过猛
```

因此：

> **RMSNorm 解决的是“网络中的信号如何稳定地流动”。**

> **Gradient Clipping 解决的是“参数如何稳定地更新”。**

而 RMSNorm 中的：

$$
\boxed{1}
$$

并没有特殊魔法。

它只是：

> **最自然、最方便的单位尺度。**

真正重要的是：

$$
\boxed{
\text{消除不可控的尺度漂移，让 hidden state 保持在稳定、可预测的数值范围内。}
}
$$

---

<a id="origin-6041"></a>
## 100. RMSNorm 中 `weight` 的作用

MiniMind 中 RMSNorm 的核心代码是：

```python
class RMSNorm(torch.nn.Module):
    def __init__(self, dim: int, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def norm(self, x):
        return x * torch.rsqrt(
            x.pow(2).mean(-1, keepdim=True) + self.eps
        )

    def forward(self, x):
        return (
            self.weight * self.norm(x.float())
        ).type_as(x)
```

其中最容易产生疑问的是：

```python
self.weight = nn.Parameter(torch.ones(dim))
```

为什么 RMSNorm 已经把数据归一化了，后面还要再乘一个 `weight`？

---

<a id="origin-6073"></a>
## 101. 先看 RMSNorm 本身做了什么

假设一个 token 的 hidden state 是：

```text
x = [3, 4]
```

RMSNorm 首先计算：

```math
RMS(x)
=
\sqrt{
\frac{3^2+4^2}{2}
}
```

也就是：

```math
RMS(x)
=
\sqrt{12.5}
\approx 3.5355
```

因此：

```math
\hat{x}
=
\frac{x}{RMS(x)}
```

得到：

```text
[3, 4]
      ↓
除以 3.5355
      ↓
[0.8485, 1.1314]
```

代码对应：

```python
self.norm(x)
```

这一部分只完成：

> **把整个向量的整体尺度拉到比较稳定的范围。**

源代码中的 `norm()` 也是沿最后一维计算均方值，再乘平方根倒数，输出形状保持不变。

---

<a id="origin-6132"></a>
## 102. 如果没有 `weight` 会怎样？

如果 RMSNorm 只有：

```python
return self.norm(x)
```

那么每一次归一化之后：

```text
每一个维度都只能服从同一个归一化尺度
```

例如：

```text
[3,4]
↓
[0.8485,1.1314]
```

模型没有办法说：

```text
第 1 个维度我想让它更重要一点

第 2 个维度我想让它弱一点
```

因为归一化过程本身只是机械地：

```text
整体除以 RMS
```

它没有任何可学习参数。

---

<a id="origin-6172"></a>
## 103. `weight` 就是给每个维度一个“可学习缩放系数”

代码：

```python
self.weight = nn.Parameter(
    torch.ones(dim)
)
```

假设：

```python
dim = 2
```

初始化时：

```text
weight = [1, 1]
```

所以刚开始：

```text
归一化结果：

[0.8485, 1.1314]

×

weight：

[1,1]

=

[0.8485, 1.1314]
```

刚初始化的时候：

```text
weight 不改变结果
```

因为所有值都是：

```text
1
```

但关键是：

```python
nn.Parameter
```

表示它是一个：

> **可以通过反向传播学习的模型参数。**

源文件也明确说明，`weight` 是长度为 `dim` 的可学习缩放参数，并且会广播到所有 batch 和 token 位置。

---

<a id="origin-6238"></a>
## 104. 训练之后 `weight` 可以发生变化

假设经过训练后：

```text
weight = [2, 0.5]
```

RMSNorm 得到：

```text
[0.8485, 1.1314]
```

再乘：

```text
[2, 0.5]
```

得到：

```text
[
0.8485 × 2,
1.1314 × 0.5
]
```

即：

```text
[1.6970, 0.5657]
```

所以：

```text
第 1 个维度
被放大了 2 倍

第 2 个维度
被缩小到了 0.5 倍
```

源代码的注释也给出了同样的例子：当 `weight=[2,0.5]` 时，归一化后的两个维度会分别乘以这两个缩放系数。

---

<a id="origin-6287"></a>
## 105. 所以 `weight` 最核心的作用是什么？

一句话：

> **RMSNorm 负责把整体尺度标准化，而 `weight` 负责让模型重新学习“每一个维度应该有多大”。**

可以理解为：

```text
RMSNorm：

先统一整体尺度

↓

weight：

再允许不同维度拥有不同的重要程度
```

---

<a id="origin-6309"></a>
## 106. 为什么归一化以后又要允许放大？不会白归一化了吗？

这是一个非常重要的问题。

表面上看：

```text
先把数据归一化

然后又乘 weight 放大
```

好像前面的归一化白做了。

其实不是。

因为两者控制的是不同东西。

---

<a id="origin-6329"></a>
### 106.1 RMSNorm 控制的是“整体尺度”

比如：

```text
[3,4]
```

和：

```text
[300,400]
```

方向完全一样，只是整体大了 100 倍。

RMSNorm 后：

```text
[3,4]
→
[0.8485,1.1314]
```

而：

```text
[300,400]
→
[0.8485,1.1314]
```

因此 RMSNorm 消除了：

```text
整体大小的不稳定变化
```

---

<a id="origin-6369"></a>
### 106.2 `weight` 控制的是“各个维度之间的相对缩放”

例如：

```text
weight = [2,0.5]
```

表示：

```text
第一个维度允许更强

第二个维度允许更弱
```

所以最终仍然可以得到：

```text
[1.6970,0.5657]
```

**这个值是训练过程中根据整个任务的 Loss 自动学出来的。**

---

<a id="origin-6395"></a>
## 107. 一个非常形象的理解

可以把 RMSNorm 想象成：

> **先把所有人的整体音量统一。**

比如原来：

```text
维度1：300
维度2：400
```

整体声音特别大。

RMSNorm 先把它压回：

```text
0.8485
1.1314
```

但是模型可能发现：

```text
第1个频道很重要
第2个频道没那么重要
```

于是 `weight` 学成：

```text
[2,0.5]
```

最终：

```text
第1个频道被加强
第2个频道被减弱
```

所以：

```text
RMSNorm
=
控制整体音量

weight
=
单独调每个频道的音量
```

---

<a id="origin-6451"></a>
## 108. `weight` 是一个数，还是很多个数？

不是一个数。

假设：

```python
hidden_size = 4096
```

那么：

```python
RMSNorm(4096)
```

里面：

```python
self.weight
```

的形状就是：

```text
[4096]
```

也就是：

```text
w1, w2, w3, ..., w4096
```

每一个 hidden dimension 都有自己独立的缩放系数。

---

<a id="origin-6489"></a>
## 109. 对 `[B,T,H]` 是怎么乘的？

假设输入：

```text
x.shape = [2,3,4]
```

表示：

```text
2 个样本
3 个 token
每个 token 4 个特征
```

那么：

```text
weight.shape = [4]
```

例如：

```text
weight = [1.0, 0.5, 2.0, 0.8]
```

PyTorch 会自动广播。

也就是每一个 token 都使用同样的一套：

```text
[1.0,0.5,2.0,0.8]
```

例如：

```text
Batch 0
    token 0 → × weight
    token 1 → × weight
    token 2 → × weight

Batch 1
    token 0 → × weight
    token 1 → × weight
    token 2 → × weight
```

所以：

> 不同 token 不拥有不同的 `weight`。

而是：

> 所有 token 共享同一套“每个特征维度的缩放参数”。

---

<a id="origin-6549"></a>
## 110. 为什么要共享？

因为 hidden state 的第 `i` 个维度，在整个模型里属于同一个特征空间。

所以：

```text
第 i 个特征
```

对应一个统一的可学习缩放：

```text
weight[i]
```

而不是：

```text
token 1 一套参数
token 2 又一套参数
```

否则参数量会随着序列长度变化，也不符合 Transformer 的参数共享方式。

---

<a id="origin-6576"></a>
## 111. `nn.Parameter` 为什么重要？

如果只是写：

```python
self.weight = torch.ones(dim)
```

它只是普通 Tensor。

而写：

```python
self.weight = nn.Parameter(
    torch.ones(dim)
)
```

之后，PyTorch 会把它登记成：

```text
模型参数
```

所以：

```python
model.parameters()
```

能够找到它。

优化器也会更新它。

例如：

```python
optimizer = torch.optim.Adam(
    model.parameters()
)
```

训练过程中：

```text
Loss
 ↓
反向传播
 ↓
计算 weight 的梯度
 ↓
optimizer.step()
 ↓
更新 weight
```

因此 `weight` 可以从：

```text
[1,1]
```

逐渐训练成：

```text
[0.83,1.26]
```

或者：

```text
[2.01,0.47]
```

具体值完全由训练数据决定。

---

<a id="origin-6654"></a>
## 112. 一个完整的数值例子

假设：

```text
x = [3,4]
```

初始化：

```text
weight = [1,1]
```

首先：

```math
RMS
=
\sqrt{
(3^2+4^2)/2
}
=
3.5355
```

于是：

```text
norm(x)

=

[3/3.5355,
 4/3.5355]

≈

[0.8485,
 1.1314]
```

初始：

```text
weight=[1,1]
```

输出：

```text
[0.8485,1.1314]
```

---

训练一段时间以后，假设：

```text
weight=[2,0.5]
```

那么：

```text
output

=

[0.8485,1.1314]
*
[2,0.5]
```

得到：

```text
[1.6970,0.5657]
```

于是模型成功做到：

```text
整体尺度仍然先被稳定

但是不同特征维度
可以重新拥有不同强度
```

---

<a id="origin-6745"></a>
## 113. 为什么 `weight` 初始值是 1？

代码：

```python
torch.ones(dim)
```

不是随机初始化，而是：

```text
[1,1,1,...,1]
```

这是非常合理的。

因为刚开始希望：

```text
RMSNorm 的归一化结果
```

不要被额外改变。

即：

```math
\hat{x}\times1=\hat{x}
```

所以初始化时：

```text
weight 相当于什么都没做
```

然后再通过训练慢慢学习：

```text
哪些维度需要加强
哪些维度需要减弱
```

---

<a id="origin-6790"></a>
## 114. 可以把 RMSNorm 拆成两步

原代码：

```python
return (
    self.weight *
    self.norm(x.float())
).type_as(x)
```

为了教学，可以拆开：

```python
# 第一步：把整体尺度归一化
normalized_x = self.norm(x.float())

# 第二步：每一个特征维度乘自己的可学习缩放参数
scaled_x = self.weight * normalized_x

# 第三步：恢复原数据类型
output = scaled_x.type_as(x)

return output
```

其中真正 RMSNorm 的逻辑，可以理解为：

```text
x
↓
计算 RMS
↓
x / RMS
↓
得到稳定尺度
↓
× weight
↓
允许模型重新调整每个维度的重要程度
```

---

<a id="origin-6834"></a>
## 115. 最关键的区别

一定不要把这两件事情混在一起：

```text
RMSNorm 的归一化部分

和

weight 的学习部分
```

它们分别负责：

| 部分 | 作用 |
|---|---|
| `x / RMS(x)` | 稳定整个 token hidden state 的整体尺度 |
| `weight` | 学习每一个 hidden dimension 应该放大还是缩小 |

所以：

```text
RMSNorm
≠
单纯把数值固定到某个范围
```

更准确地说：

```text
RMSNorm
=
先消除不稳定的整体尺度变化
+
再给模型一个可学习的逐维缩放自由度
```

---

<a id="origin-6873"></a>
## 116. 一句话总结

RMSNorm 中：

```python
self.weight = nn.Parameter(
    torch.ones(dim)
)
```

的作用是：

> **在 RMSNorm 把 hidden state 的整体尺度归一化之后，再给每一个特征维度一个独立、可学习的缩放系数，使模型既获得数值稳定性，又不会失去调整不同特征重要程度的能力。**

最简单地记：

```text
RMSNorm：

把整个向量拉回稳定尺度

weight：

再决定每个维度分别应该多强
```

也可以用音量作类比：

> **RMSNorm 负责“统一总音量”，`weight` 负责“分别调每个频道的音量”。**
