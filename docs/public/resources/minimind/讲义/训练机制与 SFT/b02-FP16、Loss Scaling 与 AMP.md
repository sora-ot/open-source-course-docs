# FP16、Loss Scaling 与 AMP


> 这一节不把概念拆散讲，而是沿着一次完整的混合精度训练流程，从问题出发，一步一步解释为什么需要这些机制。

---

<a id="origin-7"></a>
## 1. 先看问题：为什么 FP16 训练会出问题？

训练神经网络时，最基本的流程是：

```text
Forward
   ↓
Loss
   ↓
Backward
   ↓
Gradient
   ↓
Optimizer
   ↓
更新参数
```

如果全部使用 FP32，这个过程通常比较稳定。

但是 FP32 有两个问题：

1. 显存占用大；
2. 计算速度相对慢。

因此在现代 GPU 上，我们希望尽量使用：

```text
FP16
```

或者：

```text
BF16
```

进行计算。

特别是 Transformer / GPT 里大量都是矩阵乘法：

\[
Y=XW
\]

这些操作使用 FP16 / BF16 时，可以充分利用 GPU Tensor Core，提高吞吐量。

于是问题来了：

> **既然 FP16 更快，为什么不把整个训练全部改成 FP16？**

因为：

\[
\boxed{\text{FP16 的数值范围太小}}
\]

特别是在反向传播时，一些很小的梯度可能直接消失。

---

<a id="origin-68"></a>
## 2. FP16 和 FP32 到底差在哪里？

FP16 一共只有 16 bit：

```text
FP16
┌────────┬──────────────┬────────────────────┐
│ sign   │ exponent     │ fraction           │
│ 1 bit  │ 5 bits       │ 10 bits            │
└────────┴──────────────┴────────────────────┘
```

FP32 则有：

```text
FP32
┌────────┬──────────────┬────────────────────┐
│ sign   │ exponent     │ fraction           │
│ 1 bit  │ 8 bits       │ 23 bits            │
└────────┴──────────────┴────────────────────┘
```

FP32 的指数位更多，所以：

- 能表示更大的数；
- 能表示更小的数；
- 动态范围更大。

FP16 的动态范围明显更小。

---

<a id="origin-100"></a>
## 3. FP16 能表示多小的数字？

FP16 最小的正正规数（normal number）大约是：

\[
2^{-14}
\approx
6.1\times10^{-5}
\]

但是 FP16 还有次正规数（subnormal number），可以继续表示更小的值。

FP16 最小正 subnormal 大约是：

\[
2^{-24}
\approx
5.96\times10^{-8}
\]

所以理论上，FP16 可以表示非常接近：

\[
6\times10^{-8}
\]

的数。

但是再小很多，就没有对应的 FP16 表示了。

例如：

\[
1\times10^{-8}
\]

已经明显小于：

\[
5.96\times10^{-8}
\]

于是这个数在 FP16 中可能被舍入为：

\[
\boxed{0}
\]

这就是：

\[
\boxed{\text{Underflow，下溢}}
\]

---

<a id="origin-156"></a>
## 4. 为什么经常会看到 `3×10^-8 → 0`？

教材里经常会写：

```text
3 × 10^-8
    ↓
FP16
    ↓
0
```

这个例子表达的是：

> **很小的梯度可能在 FP16 中消失。**

严格来说，\(3\times10^{-8}\) 正好位于 0 和 FP16 最小 subnormal 附近，因此具体结果还和：

- 舍入方式；
- GPU 硬件；
- 是否使用 Flush-To-Zero（FTZ）

有关。

所以如果要讲得最严谨，可以用：

\[
1\times10^{-8}
\]

作为例子，因为它明显小于 FP16 的最小正 subnormal。

核心不是死记某一个具体数字，而是理解：

\[
\boxed{
\text{当数值小到 FP16 无法表示时，它可能直接变成 0}
}
\]

---

<a id="origin-198"></a>
## 5. 为什么神经网络里会产生这么小的梯度？

反向传播使用链式法则。

假设：

\[
L
\]

是 Loss。

某个参数 \(w\) 的梯度可能是：

\[
\frac{\partial L}{\partial w}
=
\frac{\partial L}{\partial y_4}
\frac{\partial y_4}{\partial y_3}
\frac{\partial y_3}{\partial y_2}
\frac{\partial y_2}{\partial y_1}
\frac{\partial y_1}{\partial w}
\]

也就是很多导数连续相乘。

例如：

\[
0.1
\times
0.05
\times
0.01
\times
0.02
\]

结果是：

\[
1\times10^{-6}
\]

再继续经过更多层，就可能得到：

\[
10^{-7}
\]

甚至：

\[
10^{-8},\quad10^{-9}
\]

所以深层神经网络的 backward 中，本来就很容易产生非常小的中间梯度。

---

<a id="origin-258"></a>
## 6. 梯度变成 0 有什么严重后果？

参数更新一般写成：

\[
w_{t+1}
=
w_t-\eta g
\]

其中：

\[
g=\frac{\partial L}{\partial w}
\]

假设真实梯度：

\[
g=1\times10^{-8}
\]

如果 FP16 把它变成：

\[
g=0
\]

那么：

\[
w_{t+1}
=
w_t-\eta\times0
\]

也就是：

\[
w_{t+1}=w_t
\]

这个参数这一步完全没有更新。

如果大量梯度都这样：

```text
真实梯度很小
   ↓
FP16 无法表示
   ↓
变成 0
   ↓
参数无法获得正确更新
   ↓
模型训练受影响
```

所以我们需要解决：

\[
\boxed{\text{FP16 小梯度下溢}}
\]

---

<a id="origin-324"></a>
## 7. 第一个解决思路：把 Loss 放大

现在假设：

\[
L
\]

是原始 Loss。

我们不直接：

```python
loss.backward()
```

而是先乘一个很大的数：

\[
S
\]

比如：

\[
S=65536
\]

定义：

\[
L'=SL
\]

然后对：

\[
L'
\]

进行 backward。

---

<a id="origin-368"></a>
## 8. 为什么放大 Loss 会把梯度也放大？

因为：

\[
L'=SL
\]

对参数 \(w\) 求导：

\[
\frac{\partial L'}{\partial w}
=
\frac{\partial(SL)}{\partial w}
\]

因为 \(S\) 是常数：

\[
\frac{\partial L'}{\partial w}
=
S\frac{\partial L}{\partial w}
\]

所以：

\[
\boxed{
\nabla L'=S\nabla L
}
\]

这意味着：

> Loss 放大 65536 倍，整个 backward 中的梯度也会一起放大 65536 倍。

---

<a id="origin-406"></a>
## 9. 一个具体例子

假设原始梯度：

\[
g=1\times10^{-8}
\]

FP16 中可能：

\[
1\times10^{-8}
\rightarrow0
\]

现在使用：

\[
S=65536
\]

则：

\[
g'
=
65536\times10^{-8}
\]

得到：

\[
g'
=
6.5536\times10^{-4}
\]

即：

\[
0.00065536
\]

这个值就非常容易被 FP16 表示。

所以：

```text
原始梯度
1e-8
  ↓
太小
  ↓
可能变 0
```

变成：

```text
原始梯度
1e-8
  ↓
× 65536
  ↓
6.5536e-4
  ↓
FP16 可以稳定表示
```

这就是：

\[
\boxed{\text{Loss Scaling}}
\]

---

<a id="origin-483"></a>
## 10. 但是梯度不是被改大了吗？

是的。

所以在真正更新参数前，要再除回来。

如果：

\[
g'=Sg
\]

那么：

\[
g=\frac{g'}S
\]

所以完整流程是：

```text
原始 Loss
   ↓
× Scale
   ↓
Scaled Loss
   ↓
Backward
   ↓
Scaled Gradient
   ↓
÷ Scale
   ↓
真实 Gradient
   ↓
Optimizer Step
```

数学上最终还是原来的梯度：

\[
g
\]

因此：

\[
\boxed{
\text{Loss Scaling 不改变真正的优化目标}
}
\]

它只是暂时改变中间数值尺度。

---

<a id="origin-539"></a>
## 11. 那么 Scale 是不是越大越好？

不是。

Scale 太小：

```text
梯度仍然很小
↓
underflow
↓
0
```

但 Scale 太大：

```text
梯度被放得太大
↓
超过 FP16 最大范围
↓
inf
```

FP16 最大有限数大约是：

\[
65504
\]

假设真实梯度：

\[
g=10
\]

如果：

\[
S=65536
\]

那么：

\[
Sg=655360
\]

明显超过：

\[
65504
\]

于是可能变成：

\[
\boxed{\infty}
\]

也就是：

\[
\boxed{\text{Overflow，上溢}}
\]

所以我们的目标是：

\[
\boxed{
\text{找到尽可能大、但又不会 Overflow 的 Scale}
}
\]

---

<a id="origin-615"></a>
## 12. 这就引出了 GradScaler

手工固定：

```python
scale = 65536
```

并不理想。

因为：

- 不同模型不一样；
- 不同 batch 不一样；
- 不同训练阶段不一样；
- 梯度分布也会不断变化。

因此 PyTorch 提供：

```python
torch.amp.GradScaler
```

典型代码：

```python
scaler = torch.amp.GradScaler("cuda")
```

它可以自动管理 Loss Scale。

---

<a id="origin-648"></a>
## 13. GradScaler 到底干了什么？

GradScaler 可以理解为一个：

> **自动管理 Loss Scaling 的控制器**

它负责：

1. 放大 Loss；
2. 进行 scaled backward；
3. 恢复梯度；
4. 检查是否出现 `inf` / `NaN`；
5. 决定是否执行 optimizer step；
6. 动态调整下一轮 Scale。

典型代码：

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

---

<a id="origin-675"></a>
## 14. `scaler.scale(loss)` 是什么？

假设当前 scale：

\[
S=65536
\]

那么：

```python
scaled_loss = scaler.scale(loss)
```

概念上近似等于：

```python
scaled_loss = loss * 65536
```

然后：

```python
scaled_loss.backward()
```

所以：

```python
scaler.scale(loss).backward()
```

大致可以理解成：

```python
(loss * scale).backward()
```

于是所有 backward 梯度整体被放大。

---

<a id="origin-717"></a>
## 15. 为什么一定要从 Loss 开始放大？

因为如果等 backward 完以后再写：

```python
for p in model.parameters():
    p.grad *= scale
```

已经晚了。

一些非常小的中间梯度可能在 backward 过程中就已经：

\[
1\times10^{-8}
\rightarrow0
\]

你最后再放大：

\[
0\times65536
\]

仍然是：

\[
0
\]

因此必须在 backward 之前就放大 Loss。

这样 Scale 才能沿着整个计算图传播：

\[
L'=SL
\]

从而：

\[
\nabla L'=S\nabla L
\]

---

<a id="origin-763"></a>
## 16. GradScaler 为什么还要检查 inf 和 NaN？

因为 Scale 也可能太大。

假设：

```text
scaled gradient
→ overflow
→ inf
```

如果还继续执行：

```python
optimizer.step()
```

那么：

\[
w
\leftarrow
w-\eta\times\infty
\]

参数可能直接变成：

```text
inf
```

或者：

```text
NaN
```

训练可能立刻崩掉。

因此：

```python
scaler.step(optimizer)
```

不仅仅是简单的：

```python
optimizer.step()
```

它会先检查梯度。

如果正常：

```text
正常 gradient
↓
optimizer.step()
```

如果发现：

```text
inf / NaN
```

则：

```text
跳过这一轮参数更新
```

---

<a id="origin-839"></a>
## 17. `scaler.update()` 是干什么的？

GradScaler 会动态调节 Scale。

例如当前：

\[
S=65536
\]

如果连续很多 step 都很稳定：

```text
没有 inf
没有 NaN
```

说明 Scale 可能还可以再大一点。

于是：

\[
65536
\rightarrow
131072
\]

如果突然出现 overflow：

```text
inf / NaN
```

说明 Scale 太大。

于是：

\[
131072
\rightarrow
65536
\]

所以：

\[
\boxed{
\text{GradScaler 在自动寻找“尽量大但安全”的 Scale}
}
\]

这叫：

\[
\boxed{\text{Dynamic Loss Scaling}}
\]

---

<a id="origin-898"></a>
## 18. 到这里还有一个问题：为什么训练代码里还有 autocast？

因为 Loss Scaling 解决的是：

\[
\boxed{\text{FP16 backward 的数值范围问题}}
\]

但我们还有另一个问题：

> 哪些算子应该用 FP16？哪些算子应该保留 FP32？

如果你简单地把整个模型都强制变成 FP16：

```python
model.half()
```

有些算子可能数值不稳定。

所以现代 PyTorch 通常使用：

```python
autocast
```

---

<a id="origin-926"></a>
## 19. autocast 是什么？

典型代码：

```python
with torch.autocast(
    device_type="cuda",
    dtype=torch.float16
):
    output = model(x)
    loss = criterion(output, y)
```

`autocast` 的含义是：

\[
\boxed{\text{Automatic Mixed Precision Casting}}
\]

即：

> 自动混合精度类型转换。

它不是：

> “把 with 里面所有计算全部变成 FP16。”

而是：

> **根据不同 operator 的数值特性，自动决定使用 FP16、BF16 或 FP32。**

---

<a id="origin-959"></a>
## 20. 为什么有些运算适合 FP16？

Transformer 里大量计算都是：

\[
Y=XW
\]

例如：

- Q projection；
- K projection；
- V projection；
- Attention matrix multiplication；
- MLP；
- Linear。

这些大规模矩阵乘法：

```text
FP16 / BF16
```

通常：

- 更快；
- 更省显存带宽；
- 可以利用 Tensor Core。

所以 autocast 会尽量让这类操作用低精度。

---

<a id="origin-992"></a>
## 21. 为什么不能所有操作都 FP16？

因为有些操作对数值精度更加敏感。

例如某些：

- reduction；
- normalization；
- exponent；
- logarithm；
- loss 计算；
- softmax 相关操作。

使用 FP16 时容易累积更大的数值误差。

因此 autocast 会根据 PyTorch 的 operator policy 自动选择更安全的 dtype。

所以应当记住：

\[
\boxed{
\text{autocast = 按算子自动选择合适精度}
}
\]

而不是：

\[
\text{autocast = 全部 FP16}
\]

---

<a id="origin-1025"></a>
## 22. autocast 为什么叫“混合精度”？

因为一次 Forward 中可能出现：

```text
Linear         → FP16
MatMul         → FP16
某些 Reduction → FP32
某些 Loss      → FP32
Linear         → FP16
```

所以整个网络内部同时存在：

```text
FP16 + FP32
```

因此叫：

\[
\boxed{\text{Mixed Precision Training}}
\]

---

<a id="origin-1051"></a>
## 23. autocast 和 GradScaler 的分工

到这里可以非常清楚地区分：

<a id="origin-1055"></a>
### 23.1 autocast

负责：

\[
\boxed{\text{Forward 中“用什么精度算”}}
\]

---

<a id="origin-1065"></a>
### 23.2 GradScaler

负责：

\[
\boxed{\text{Backward 中“小梯度不要丢”}}
\]

所以：

```text
autocast
   ↓
让适合低精度的 Forward 算子使用 FP16

GradScaler
   ↓
让 FP16 Backward 中的小梯度不容易 underflow
```

---

<a id="origin-1087"></a>
## 24. 一次标准 AMP 训练到这里变成

```python
with torch.autocast(
    device_type="cuda",
    dtype=torch.float16
):
    output = model(x)
    loss = criterion(output, y)

scaler.scale(loss).backward()
```

解释：

```text
autocast
↓
Forward 使用混合精度
↓
得到 Loss
↓
GradScaler 放大 Loss
↓
Backward
↓
得到 scaled gradients
```

---

<a id="origin-1118"></a>
## 25. 但现在有一个新问题：gradient 还是被放大的

假设：

\[
S=1024
\]

真实梯度：

\[
g=0.002
\]

backward 后：

\[
g'
=
1024\times0.002
=
2.048
\]

现在 parameter.grad 里对应的是放大后的：

\[
2.048
\]

但真正 optimizer 应该使用：

\[
0.002
\]

所以必须把它除回来。

这就是：

\[
\boxed{\text{unscale}}
\]

---

<a id="origin-1164"></a>
## 26. `unscale_()` 是什么？为什么恢复真实梯度后不会再次下溢？

在混合精度训练中，我们经常会看到下面这样的代码：

```python
scaler.unscale_(optimizer)
```

它的作用是：

> **把 Loss Scaling 产生的“放大梯度”，恢复成真实梯度。**

但这里很容易产生一个疑问：

> 既然 Loss Scaling 就是为了防止 FP16 中的小梯度下溢，那么 `unscale_()` 又把梯度变小了，岂不是重新下溢了吗？

答案是：

> **通常不会。因为 Loss Scaling 主要保护的是 FP16 的反向传播计算过程，而 `unscale_()` 之后恢复出来的梯度通常存储在 FP32 中。**

经过：

```python
scaler.scale(loss).backward()
```

之后，梯度其实还是被放大过的：

```math
g'=Sg
```

因此不能直接拿：

```math
g'
```

更新参数。

否则相当于把梯度人为扩大了：

```math
S
```

倍。

所以在参数更新之前需要恢复：

```math
g=\frac{g'}{S}
```

这就是：

```python
scaler.unscale_(optimizer)
```

所做的事情。

<a id="origin-1226"></a>
## 27. `unscale_()` 发生在什么时候？

整个过程如下：

```text
原始 Loss
   ↓
× Scale
   ↓
Scaled Loss
   ↓
backward()
   ↓
计算放大梯度
g' = Sg
   ↓
unscale_()
   ↓
恢复真实梯度
g = g' / S
   ↓
optimizer.step()
   ↓
更新参数
```

因此：

```text
backward()
    ↓
unscale_()
    ↓
optimizer.step()
```

所以：

```math
\boxed{
\text{unscale 发生在 backward 之后、参数更新之前}
}
```

---

<a id="origin-1272"></a>
## 28. 最关键的问题：恢复以后不会重新下溢吗？

假设刚才：

```math
g'=2.048\times10^{-5}
```

执行：

```python
scaler.unscale_(optimizer)
```

得到：

```math
g
=
\frac{2.048\times10^{-5}}{1024}
```

因此：

```math
g=2\times10^{-8}
```

于是又回到了非常小的：

```text
0.00000002
```

看起来似乎又有下溢风险。

但是关键区别是：

> **这个时候梯度通常已经保存在 FP32 的梯度缓冲区中。**

所以：

```text
2 × 10^-8
```

虽然对于 FP16 来说可能比较危险，

但是对于 FP32 来说完全可以正常保存。

因此：

```text
FP16 backward 阶段：

2e-8
  ↓
太小，危险

所以先：

2e-8 × 1024
  ↓
2.048e-5

安全通过 FP16 计算

之后：

2.048e-5 ÷ 1024
  ↓
2e-8

此时保存在 FP32 grad 中
  ↓
不会因为这个数量级而变成 0
```

<a id="origin-1350"></a>
## 29. 为什么 Gradient Clipping 前必须先 unscale？

假设真实梯度：

\[
g=[0.3,0.4]
\]

它的 L2 norm：

\[
\|g\|_2
=
\sqrt{0.3^2+0.4^2}
=
0.5
\]

假设：

```python
max_norm = 1.0
```

因为：

\[
0.5<1
\]

所以根本不需要裁剪。

但是假设：

\[
S=1024
\]

scaled gradient：

\[
g'
=
[307.2,409.6]
\]

它的 norm：

\[
\|g'\|_2=512
\]

如果这时候直接：

```python
clip_grad_norm_(..., max_norm=1.0)
```

程序会认为：

\[
512>1
\]

于是大幅裁剪。

但真实梯度的 norm 明明只有：

\[
0.5
\]

所以这是错误的。

因此正确流程必须是：

```text
Scaled Gradient
      ↓
unscale_
      ↓
True Gradient
      ↓
clip_grad_norm_
```

---

<a id="origin-1438"></a>
## 30. 什么是 `clip_grad_norm_()`？

代码：

```python
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)
```

它的作用是：

> **限制整个模型梯度向量的范数不能太大。**

它不是把每一个梯度都单独限制在：

```text
[-1, 1]
```

而是看所有参数梯度组成的整体向量。

---

<a id="origin-1463"></a>
## 31. 什么叫整体梯度范数？

假设模型只有两个参数：

\[
w_1,\quad w_2
\]

梯度：

\[
g_1=3
\]

\[
g_2=4
\]

可以看作一个梯度向量：

\[
g=[3,4]
\]

它的 L2 norm：

\[
\|g\|_2
=
\sqrt{3^2+4^2}
\]

得到：

\[
5
\]

这就是：

\[
\boxed{\text{Gradient Norm}}
\]

---

<a id="origin-1509"></a>
## 32. 如果 max_norm=1 会发生什么？

当前：

\[
\|g\|=5
\]

但允许最大：

\[
1
\]

所以需要把整个向量等比例缩小。

缩放比例：

\[
\frac{1}{5}
\]

于是：

\[
[3,4]
\]

变成：

\[
[0.6,0.8]
\]

新的 norm：

\[
\sqrt{0.6^2+0.8^2}
=
1
\]

注意方向没有改变。

因为：

\[
[0.6,0.8]
=
0.2[3,4]
\]

所以：

> **Gradient Clipping 保留方向，只缩短长度。**

---

<a id="origin-1567"></a>
## 33. 为什么需要 Gradient Clipping？

有时候训练过程中梯度会突然爆大。

例如：

```text
step 100
grad norm = 0.8

step 101
grad norm = 1.1

step 102
grad norm = 0.9

step 103
grad norm = 150

step 104
grad norm = 2400
```

如果直接更新参数：

\[
w_{t+1}=w_t-\eta g
\]

巨大梯度可能让参数发生非常大的跳动。

导致：

- Loss 爆炸；
- 参数不稳定；
- inf；
- NaN。

因此可以设置：

```python
max_norm = 1.0
```

让：

```text
grad norm = 0.8
→ 不变

grad norm = 150
→ 缩小到 1

grad norm = 2400
→ 缩小到 1
```

---

<a id="origin-1626"></a>
## 34. Loss Scaling 和 Gradient Clipping 是两个相反的问题

这点非常重要。

<a id="origin-1630"></a>
### 34.1 Loss Scaling

解决：

\[
\boxed{\text{梯度太小}}
\]

目的：

```text
防止 underflow
```

特点：

```text
临时放大
最后会除回来
```

---

<a id="origin-1653"></a>
### 34.2 Gradient Clipping

解决：

\[
\boxed{\text{梯度太大}}
\]

目的：

```text
防止训练不稳定
```

特点：

```text
真正缩小梯度
不会再恢复
```

所以：

| 对比项 | Loss Scaling | Gradient Clipping |
|---|---|---|
| 解决什么 | 梯度太小 | 梯度太大 |
| 是否临时 | 是 | 否 |
| 会不会恢复 | 会 unscale | 不会 |
| 主要目的 | 数值精度 | 训练稳定性 |
| 是否改变真实优化步幅 | 理论上不改变 | 会改变 |

---


<a id="origin-1687"></a>
## 35. 为什么梯度裁剪要放在 `unscale_()` 后面？

例如我们希望：

```python
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)
```

意思是：

> 如果真实梯度的整体范数超过 1，就进行裁剪。

但是如果还没有执行：

```python
unscale_()
```

那么梯度还是：

```math
g'=Sg
```

例如：

真实梯度：

```math
g=0.1
```

如果：

```math
S=1024
```

那么当前 `.grad` 中可能是：

```math
g'=102.4
```

这时执行：

```python
clip_grad_norm_(..., 1.0)
```

优化器会认为：

```text
梯度 = 102.4
```

于是疯狂裁剪。

但实际上真实梯度只有：

```text
0.1
```

根本不应该裁剪。

所以正确顺序必须是：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)

scaler.update()
```

---

<a id="origin-1775"></a>
## 36. 完整流程

典型 AMP 训练代码：

```python
optimizer.zero_grad()

with torch.autocast(
    device_type="cuda",
    dtype=torch.float16
):
    output = model(x)
    loss = criterion(output, y)

# 1. 放大 loss，并执行 backward
scaler.scale(loss).backward()

# 2. 恢复真实梯度
scaler.unscale_(optimizer)

# 3. 对真实梯度进行裁剪
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

# 4. 更新参数
scaler.step(optimizer)

# 5. 更新 Scale
scaler.update()
```

完整流程可以表示成：

```text
Forward
   ↓
Loss
   ↓
× Scale
   ↓
Scaled Loss
   ↓
Backward
   ↓
Scaled Gradient
g' = Sg
   ↓
unscale_
   ↓
True Gradient
g = g'/S
   ↓
Gradient Clipping
   ↓
Optimizer Step
   ↓
更新参数
```

---

<a id="origin-1838"></a>
## 37. `scaler.step()` 和 `optimizer.step()` 的关系

通常使用 AMP 时，不直接写：

```python
optimizer.step()
```

而是：

```python
scaler.step(optimizer)
```

原因之一是：

```python
scaler.step(optimizer)
```

会检查梯度中是否出现：

```text
inf
```

或者：

```text
NaN
```

如果梯度正常：

```text
scaler.step()
      ↓
optimizer.step()
```

如果出现溢出：

```text
Gradient = inf / NaN
      ↓
跳过 optimizer.step()
```

避免错误梯度破坏模型参数。

---

<a id="origin-1890"></a>
## 38. 不手动调用 `unscale_()` 可以吗？

可以。

例如：

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

这种写法是允许的。

因为：

```python
scaler.step(optimizer)
```

会在内部完成必要的 unscale 操作。

所以：

```text
scaler.step(optimizer)

大致可以理解成：

unscale
   ↓
检查 inf / NaN
   ↓
optimizer.step()
```

因此，如果中间不需要操作梯度，可以不手动写：

```python
scaler.unscale_(optimizer)
```

---

<a id="origin-1936"></a>
## 39. 什么时候必须显式调用 `unscale_()`？

当我们需要在：

```python
optimizer.step()
```

之前操作**真实梯度**时。

例如：

```python
torch.nn.utils.clip_grad_norm_()
```

这时候就应该：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    1.0
)

scaler.step(optimizer)

scaler.update()
```

否则裁剪的是：

```text
Scaled Gradient
```

而不是真实梯度。

---

<a id="origin-1979"></a>
### 39.1 补充：为什么没有 `clip_grad_norm_()` 可以不写 `unscale_()`，有了就要写？

可以，整理成一份适合直接复制的 Markdown：

<a id="origin-1983"></a>
## 40. 为什么没有 `clip_grad_norm_()` 可以不写 `unscale_()`，有了就要写？

核心原因只有一句话：

> `scaler.step(optimizer)` 在真正执行 `optimizer.step()` 之前，本来就会自动执行 `unscale`；但 `clip_grad_norm_()` 发生在 `scaler.step()` 之前，因此如果想让它裁剪“真实梯度”，就必须提前手动 `unscale_()`。

---

<a id="origin-1991"></a>
## 41. 先看 Loss Scaling 做了什么

假设真实的 loss 为：

```math
L
```

GradScaler 当前的缩放倍数为：

```math
S=1024
```

代码：

```python
scaler.scale(loss).backward()
```

实际上相当于先计算：

```math
L'=SL
```

然后对：

```math
L'
```

进行反向传播。

原本真实梯度为：

```math
g=\frac{\partial L}{\partial W}
```

放大 loss 之后得到：

```math
g'
=
\frac{\partial (SL)}{\partial W}
=
S\frac{\partial L}{\partial W}
=
Sg
```

也就是说：

```text
真实梯度 g
    ↓
乘以 Scale
    ↓
Scaled Gradient = Sg
```

例如：

```math
g=0.002
```

如果：

```math
S=1024
```

那么反向传播之后 `.grad` 里面保存的是：

```math
g'
=
1024\times0.002
=
2.048
```

因此此时：

```python
parameter.grad
```

里面看到的并不是：

```text
0.002
```

而是：

```text
2.048
```

---

<a id="origin-2095"></a>
## 42. 没有 `clip_grad_norm_()` 时为什么不用手动 `unscale_()`？

正常的 AMP 代码可以写成：

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

这里没有显式写：

```python
scaler.unscale_(optimizer)
```

但代码依然是正确的。

因为：

```python
scaler.step(optimizer)
```

内部会帮我们完成必要的 `unscale`。

可以近似理解为：

```python
def scaler_step(optimizer):

    if optimizer 还没有被 unscale:
        unscale_(optimizer)

    检查梯度中是否存在 inf / nan

    if 梯度正常:
        optimizer.step()
```

因此：

```python
scaler.step(optimizer)
```

并不是简单等价于：

```python
optimizer.step()
```

而更像是：

```text
恢复真实梯度
+
检查 Inf / NaN
+
optimizer.step()
```

---

<a id="origin-2161"></a>
## 43. `scaler.step()` 到底是怎么自动恢复梯度的？

假设：

```math
S=1024
```

真实梯度：

```math
g=0.002
```

反向传播后得到：

```math
g'=Sg
```

即：

```math
g'
=
1024\times0.002
=
2.048
```

此时：

```text
.grad = 2.048
```

GradScaler 自己知道当前：

```text
scale = 1024
```

所以 `scaler.step()` 内部可以执行：

```math
g
=
\frac{g'}{S}
```

即：

```math
g
=
\frac{2.048}{1024}
=
0.002
```

于是整个过程为：

```text
真实梯度
0.002

    ↓ × 1024

Scaled Gradient
2.048

    ↓ scaler.step()

内部执行：
2.048 / 1024

    ↓

真实梯度
0.002

    ↓

optimizer.step()
```

因此所谓：

> `scaler.step()` 自动恢复梯度

本质上没有什么神秘的。

就是：

> GradScaler 知道自己之前把 loss 放大了多少倍，因此在参数更新前，再把梯度除以相同的倍数。

---

<a id="origin-2259"></a>
## 44. 所以没有梯度裁剪时可以直接这样写

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

执行过程：

```text
loss
 │
 │ × Scale
 ▼
scaled_loss
 │
 │ backward()
 ▼
scaled gradient
 │
 │
 ▼
scaler.step(optimizer)
 │
 ├── 自动 unscale
 │
 ▼
真实 gradient
 │
 ├── 检查 Inf / NaN
 │
 ▼
optimizer.step()
```

这里没有任何代码需要在：

```python
backward()
```

和：

```python
scaler.step()
```

之间读取或者修改真实梯度。

所以：

> 没有必要提前手动 `unscale_()`。

---

<a id="origin-2317"></a>
## 45. 加入 `clip_grad_norm_()` 后，问题出现了

现在我们想限制梯度范数：

```python
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)
```

假设真实梯度仍然是：

```math
g=0.002
```

显然：

```math
0.002<1
```

这个梯度其实根本不应该被裁剪。

但是经过 Loss Scaling：

```math
S=1024
```

反向传播之后：

```math
g'
=
1024\times0.002
=
2.048
```

此时 `.grad` 里面是：

```text
2.048
```

---

<a id="origin-2366"></a>
## 46. 如果直接 Clip 会发生什么？

如果这样写：

```python
scaler.scale(loss).backward()

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)
scaler.update()
```

那么 `clip_grad_norm_()` 读取到的是：

```text
2.048
```

而不是：

```text
0.002
```

于是它看到：

```math
2.048>1
```

就会认为：

> 梯度太大了，需要裁剪。

但是实际上真实梯度：

```math
0.002
```

根本不大。

也就是说：

```text
真实梯度：

0.002
```

本来应该：

```text
不裁剪
```

但是因为 Loss Scaling：

```text
0.002
   ↓ ×1024
2.048
```

`clip_grad_norm_()` 错误地看到：

```text
2.048 > 1
```

于是进行了不该进行的裁剪。

---

<a id="origin-2444"></a>
## 47. 所以必须在 Clip 之前先恢复真实梯度

正确写法：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)

scaler.update()
```

执行过程：

```text
真实梯度
0.002

    ↓ Loss Scaling

Scaled Gradient
2.048

    ↓ scaler.unscale_(optimizer)

真实梯度
0.002

    ↓ clip_grad_norm_()

按照真实梯度判断是否需要裁剪

    ↓

scaler.step(optimizer)

    ↓

optimizer.step()
```

---

<a id="origin-2494"></a>
## 48. `unscale_()` 的真正目的是什么？

这里非常容易产生一个误解：

> 是不是因为 `optimizer.step()` 必须使用真实梯度，所以必须手动 `unscale_()`？

并不是。

因为：

```python
scaler.step(optimizer)
```

本身就会自动完成 `unscale`。

真正的问题是：

```python
clip_grad_norm_()
```

发生在：

```python
scaler.step()
```

之前。

因此：

> 如果想在 `scaler.step()` 之前对梯度进行任何依赖真实数值的操作，就需要提前把梯度恢复回来。

所以真正的逻辑是：

```text
不是 optimizer.step() 需要手动 unscale

而是 clip_grad_norm_() 需要看到真实梯度
```

---

<a id="origin-2538"></a>
## 49. 为什么 `clip_grad_norm_()` 自己不能自动 `unscale`？

因为：

```python
torch.nn.utils.clip_grad_norm_()
```

本身完全不知道 GradScaler 的存在。

它接收到的只有：

```python
model.parameters()
```

以及：

```python
max_norm
```

例如：

```python
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    1.0
)
```

它做的事情非常简单：

```text
读取 parameter.grad
        ↓
计算 Gradient Norm
        ↓
判断是否超过 max_norm
        ↓
如果超过，就缩小梯度
```

它并不知道：

```text
你有没有用 AMP

你有没有使用 GradScaler

scale 是多少

当前 gradient 有没有被 scale

应该除以多少
```

例如它根本不知道当前：

```text
scale = 1024
```

还是：

```text
scale = 65536
```

因此：

> `clip_grad_norm_()` 没有能力自动执行 `unscale`。

---

<a id="origin-2613"></a>
## 50. 那手动 `unscale_()` 后，`scaler.step()` 不会又除一次吗？

不会。

例如我们写：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    1.0
)

scaler.step(optimizer)
```

可能会担心：

```text
第一次：

2.048 / 1024
=
0.002
```

然后 `scaler.step()` 再执行一次：

```text
0.002 / 1024
```

这样梯度岂不是又变小了？

实际上不会。

---

<a id="origin-2654"></a>
## 51. GradScaler 会记录当前 optimizer 是否已经 unscale

当你执行：

```python
scaler.unscale_(optimizer)
```

之后，GradScaler 会记录：

```text
这个 optimizer 的梯度已经 unscale 过了
```

因此后面执行：

```python
scaler.step(optimizer)
```

时，可以近似理解为：

```python
if optimizer 没有执行过 unscale:
    scaler.unscale_(optimizer)

optimizer.step()
```

如果之前已经：

```python
scaler.unscale_(optimizer)
```

那么就：

```text
跳过第二次 unscale
```

因此不存在重复除法。

---

<a id="origin-2699"></a>
## 52. 两种情况完整对比

<a id="origin-2701"></a>
### 52.1 情况一：没有 `clip_grad_norm_()`

代码：

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

流程：

```text
loss
 ↓
scale
 ↓
scaled loss
 ↓
backward
 ↓
scaled gradient
 ↓
scaler.step()
 ↓
自动 unscale
 ↓
真实 gradient
 ↓
optimizer.step()
```

因此：

```python
scaler.unscale_(optimizer)
```

可以不写。

---

<a id="origin-2745"></a>
### 52.2 情况二：有 `clip_grad_norm_()`

代码：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)

scaler.update()
```

流程：

```text
loss
 ↓
scale
 ↓
scaled loss
 ↓
backward
 ↓
scaled gradient
 ↓
手动 unscale
 ↓
真实 gradient
 ↓
clip_grad_norm_
 ↓
裁剪后的真实 gradient
 ↓
scaler.step()
 ↓
发现已经 unscale
 ↓
不再重复 unscale
 ↓
optimizer.step()
```

---

<a id="origin-2796"></a>
## 53. 两段代码放在一起看最清楚

<a id="origin-2798"></a>
### 53.1 不使用梯度裁剪

```python
optimizer.zero_grad()

with autocast():
    output = model(x)
    loss = criterion(output, y)

scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

这里：

```python
scaler.step(optimizer)
```

内部会自动完成：

```python
unscale
```

---

<a id="origin-2828"></a>
### 53.2 使用梯度裁剪

```python
optimizer.zero_grad()

with autocast():
    output = model(x)
    loss = criterion(output, y)

scaler.scale(loss).backward()

# 先恢复真实梯度
scaler.unscale_(optimizer)

# 再按照真实梯度进行裁剪
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)

scaler.update()
```

---

<a id="origin-2855"></a>
## 54. 最值得记住的一句话

不要把它理解成：

```text
用了 clip
↓
所以必须 unscale
```

更准确的理解应该是：

```text
只要你需要在 scaler.step() 之前
读取或者修改“真实梯度”

↓
就必须提前 unscale
```

而：

```python
clip_grad_norm_()
```

恰好属于这种操作。

---

<a id="origin-2885"></a>
## 55. 最终总结

正常情况下：

```python
scaler.scale(loss).backward()
scaler.step(optimizer)
```

完全可以，因为：

```text
scaler.step()
=
自动 unscale
+
Inf / NaN 检查
+
optimizer.step()
```

但是如果中间需要：

```python
clip_grad_norm_()
```

就必须变成：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

clip_grad_norm_()

scaler.step(optimizer)
```

原因是：

> `clip_grad_norm_()` 必须根据真实梯度进行裁剪，而不能根据 Loss Scaling 之后被人为放大的梯度进行裁剪。

所以最终可以记成：

```text
没有 Clip：

backward
    ↓
scaled gradient
    ↓
scaler.step
    ↓
自动 unscale
    ↓
optimizer.step
```

而有 Clip：

```text
backward
    ↓
scaled gradient
    ↓
手动 unscale
    ↓
真实 gradient
    ↓
clip
    ↓
scaler.step
    ↓
optimizer.step
```

最核心的一句话：

> **`unscale_()` 不是为了帮助 `optimizer.step()`，而是为了让发生在 `scaler.step()` 之前的梯度操作能够看到真实梯度。**

---

可以，下面这版就专门把“**为什么 Loss Scaling 只乘一个 Loss 标量，就能保护 backward 中间梯度**”这条主线完整串起来。

<a id="origin-2970"></a>
## 56. Loss Scaling 为什么只给 Loss 乘一个系数，就能保护整个 Backward？

理解 Loss Scaling，最关键的不是最终的 `parameter.grad`，而是：

> **Backward 过程中存在大量“中间梯度”，这些中间梯度可能以 FP16 参与计算，因此可能在到达 FP32 的 `.grad` 之前就已经下溢成 0。**

Loss Scaling 真正主要保护的，就是这些 **Backward 中间梯度**。

---

<a id="origin-2980"></a>
## 57. 先明确：FP16 在 Backward 阶段到底干什么？

混合精度训练中，FP16 并不是只用于 Forward。

Backward 本身也需要做大量矩阵运算。

例如一个最简单的线性层：

```math
Y=XW
```

Forward 要计算：

```math
Y=XW
```

Backward 时需要计算两个重要梯度：

```math
\frac{\partial L}{\partial X}
=
\frac{\partial L}{\partial Y}W^T
```

以及：

```math
\frac{\partial L}{\partial W}
=
X^T\frac{\partial L}{\partial Y}
```

这两个式子本质上也都是大型矩阵乘法。

所以：

```text
Forward
X @ W
    ↓
可以使用 FP16 / Tensor Core
    ↓
加速计算

Backward
dY @ Wᵀ
Xᵀ @ dY
    ↓
同样包含大量矩阵乘
    ↓
也可以使用低精度计算
```

因此 FP16 在 Backward 中的主要作用仍然是：

```text
更快
+
减少带宽和显存压力
+
利用 Tensor Core
```

但是随之而来的问题就是：

> **Backward 中的梯度通常非常小，FP16 表示范围有限，小梯度可能下溢。**

---

<a id="origin-3051"></a>
## 58. 最终 `.grad` 是 FP32，为什么还会有问题？

这是最容易困惑的地方。

假设模型参数：

```python
W.dtype == torch.float32
```

那么很多普通 AMP 训练场景下：

```python
W.grad.dtype == torch.float32
```

也就是说最终用于 optimizer 的参数梯度通常会累积在 FP32 中。

于是很容易产生一个想法：

> 最后都是 FP32 存梯度，那 FP16 下溢有什么关系？

问题是：

> **梯度在到达最终 FP32 `.grad` 之前，还需要经过一长串 Backward 中间计算。**

如果中途已经丢失，FP32 再精确也救不回来。

---

<a id="origin-3081"></a>
## 59. 什么叫 Backward 中间梯度？

假设网络结构：

```text
x
↓
Layer1
↓
h1
↓
Layer2
↓
h2
↓
Layer3
↓
y
↓
Loss
```

Backward 从 Loss 开始：

```text
Loss
 ↑
dL/dy
 ↑
Layer3
 ↑
dL/dh2
 ↑
Layer2
 ↑
dL/dh1
 ↑
Layer1
 ↑
dL/dx
```

其中：

```math
\frac{\partial L}{\partial y}
```

```math
\frac{\partial L}{\partial h_2}
```

```math
\frac{\partial L}{\partial h_1}
```

都属于：

> **中间梯度**

它们不是最终某个参数的 `.grad`，而是：

> 用来继续向前传播梯度的临时梯度信号。

---

<a id="origin-3147"></a>
## 60. 以一个线性层为例看得最清楚

假设：

```math
Y=XW
```

Backward 时，上游先传下来：

```math
G_Y
=
\frac{\partial L}{\partial Y}
```

然后这一层计算：

```math
G_X
=
\frac{\partial L}{\partial X}
=
G_YW^T
```

同时：

```math
G_W
=
\frac{\partial L}{\partial W}
=
X^TG_Y
```

整个流程：

```text
上游传来的梯度
G_Y = dL/dY
        │
        ├──────────────┐
        │              │
        ▼              ▼

G_Y @ Wᵀ           Xᵀ @ G_Y

        │              │
        ▼              ▼

G_X = dL/dX       G_W = dL/dW

        │              │
        ▼              ▼

继续向前传播      累积到 W.grad
                  通常最终是 FP32
```

这里真正危险的是左边：

```text
G_Y
↓
G_X
↓
下一层的中间梯度
↓
再下一层的中间梯度
```

这些中间梯度可能在低精度路径中参与计算。

---

<a id="origin-3223"></a>
## 61. FP16 下溢发生在哪里？

假设某个中间梯度：

```math
G_Y
=
3\times10^{-8}
```

这个数字非常小。

如果它在某个 FP16 运算路径中无法被正常表示，就可能：

```math
3\times10^{-8}
\rightarrow
0
```

于是后面：

```math
G_X
=
G_YW^T
```

就变成：

```math
G_X
=
0\times W^T
=
0
```

同样：

```math
G_W
=
X^TG_Y
```

也可能变成：

```math
G_W
=
X^T\times0
=
0
```

于是整个过程变成：

```text
真实中间梯度

3 × 10⁻⁸

    ↓

FP16 中间计算

    ↓

下溢成 0

    ↓

后面所有计算看到的都是 0

    ↓

最终存进 FP32 .grad

    ↓

仍然是 0
```

因此：

> **FP32 最终存储梯度，并不能挽救已经在 FP16 Backward 中间过程里丢失的梯度。**

---

<a id="origin-3313"></a>
## 62. 所以 Loss Scaling 真正要保护什么？

主要不是保护最终：

```python
W.grad
```

而是保护：

```text
Loss
↓
中间梯度
↓
中间梯度
↓
中间梯度
↓
……
↓
最终参数梯度
```

也就是：

> **从 Loss 一路反向传播到各个参数 `.grad` 之前的那些中间梯度。**

---

<a id="origin-3343"></a>
## 63. 那为什么只给一个 Loss 标量乘 1024 就够了？

假设原来的 Loss：

```math
L
```

我们不直接做：

```python
loss.backward()
```

而是：

```python
scaler.scale(loss).backward()
```

假设：

```math
S=1024
```

那么相当于构造：

```math
L'=SL
```

即：

```math
L'=1024L
```

关键来了。

假设我们要求：

```math
\frac{\partial L'}{\partial W}
```

那么：

```math
\frac{\partial L'}{\partial W}
=
\frac{\partial (SL)}{\partial W}
```

因为：

```math
S
```

是常数，所以：

```math
\frac{\partial L'}{\partial W}
=
S\frac{\partial L}{\partial W}
```

即：

```math
\boxed{
\frac{\partial L'}{\partial W}
=
S
\frac{\partial L}{\partial W}
}
```

所以只要：

```math
Loss\times1024
```

最终所有梯度都会自动：

```math
\times1024
```

---

<a id="origin-3436"></a>
## 64. 为什么“所有中间梯度”也会一起放大？

这里才是 Loss Scaling 最核心的地方。

假设计算图：

```text
W
↓
h1
↓
h2
↓
y
↓
L
```

正常 Backward：

```math
\frac{\partial L}{\partial W}
=
\frac{\partial L}{\partial y}
\frac{\partial y}{\partial h_2}
\frac{\partial h_2}{\partial h_1}
\frac{\partial h_1}{\partial W}
```

现在把：

```math
L
```

改成：

```math
L'=SL
```

首先：

```math
\frac{\partial L'}{\partial y}
=
\frac{\partial (SL)}{\partial y}
=
S\frac{\partial L}{\partial y}
```

所以第一个中间梯度直接被放大：

```math
\frac{\partial L'}{\partial y}
=
S
\frac{\partial L}{\partial y}
```

继续向前：

```math
\frac{\partial L'}{\partial h_2}
=
\frac{\partial L'}{\partial y}
\frac{\partial y}{\partial h_2}
```

代入：

```math
\frac{\partial L'}{\partial h_2}
=
S
\frac{\partial L}{\partial y}
\frac{\partial y}{\partial h_2}
```

所以：

```math
\frac{\partial L'}{\partial h_2}
=
S
\frac{\partial L}{\partial h_2}
```

继续：

```math
\frac{\partial L'}{\partial h_1}
=
S
\frac{\partial L}{\partial h_1}
```

最后：

```math
\frac{\partial L'}{\partial W}
=
S
\frac{\partial L}{\partial W}
```

因此：

```text
Loss × S

    ↓

dL/dy × S

    ↓

dL/dh2 × S

    ↓

dL/dh1 × S

    ↓

dL/dW × S
```

也就是说：

> **Scale 不是只影响最终梯度，而是会顺着链式法则，把整条 Backward 路径中的中间梯度一起放大。**

---

<a id="origin-3570"></a>
## 65. 可以把 Loss Scaling 理解成在 Backward 入口放一个总放大器

正常情况下：

```text
Loss
 │
 ▼
dL/dy
 │
 ▼
dL/dh2
 │
 ▼
dL/dh1
 │
 ▼
dL/dW
```

加入 Loss Scaling：

```text
Loss
 │
 │ × 1024
 ▼
Scaled Loss
 │
 ▼
1024 × dL/dy
 │
 ▼
1024 × dL/dh2
 │
 ▼
1024 × dL/dh1
 │
 ▼
1024 × dL/dW
```

所以完全没有必要手工写：

```text
每个梯度 × 1024
```

只需要在最顶端：

```math
L'=1024L
```

链式法则就自动帮你完成整条反向传播的缩放。

---

<a id="origin-3628"></a>
## 66. 一个具体数字例子

假设某个中间梯度本来是：

```math
\frac{\partial L}{\partial h}
=
3\times10^{-8}
```

如果直接用低精度 Backward：

```text
3 × 10⁻⁸
↓
FP16
↓
可能下溢
↓
0
```

现在使用：

```math
S=1024
```

那么：

```math
L'=1024L
```

所以：

```math
\frac{\partial L'}{\partial h}
=
1024
\times
3\times10^{-8}
```

得到：

```math
3.072\times10^{-5}
```

于是：

```text
原中间梯度：

3 × 10⁻⁸

    ↓ × 1024

3.072 × 10⁻⁵

    ↓

FP16 更容易表示

    ↓

Backward 继续正常传播
```

这就是 Loss Scaling 的核心。

---

<a id="origin-3702"></a>
## 67. 最终为什么还要 Unscale？

因为：

```math
L'=SL
```

之后得到的是放大的梯度：

```math
g'=Sg
```

比如真实梯度：

```math
g=0.002
```

Scale：

```math
S=1024
```

Backward 后：

```math
g'
=
2.048
```

但真正更新参数时显然不能用：

```math
2.048
```

因为我们真正想要的是：

```math
0.002
```

所以在参数更新之前：

```math
g
=
\frac{g'}{S}
```

即：

```math
g
=
\frac{2.048}{1024}
=
0.002
```

这就是：

```python
scaler.unscale_(optimizer)
```

做的事情。

---

<a id="origin-3776"></a>
## 68. 整个完整流程

假设真实中间梯度非常小：

```math
3\times10^{-8}
```

正常 FP16 Backward：

```text
Loss
 ↓
Backward
 ↓
中间梯度
3 × 10⁻⁸
 ↓
FP16 下溢
 ↓
0
 ↓
后面梯度信息全部丢失
```

Loss Scaling 后：

```text
Loss
 ↓
× 1024
 ↓
Scaled Loss
 ↓
Backward
 ↓
所有中间梯度自动 × 1024
 ↓
3.072 × 10⁻⁵
 ↓
避免过早下溢
 ↓
梯度正常传播
 ↓
最终参数梯度累积
 ↓
unscale
 ↓
÷ 1024
 ↓
恢复真实梯度
 ↓
optimizer.step()
```

<a id="origin-3831"></a>
## 69. 为什么没有 `clip_grad_norm_()` 可以不写 `unscale_()`，有了就要写？

核心原因只有一句话：

> `scaler.step(optimizer)` 在真正执行 `optimizer.step()` 之前，本来就会自动执行 `unscale`；但 `clip_grad_norm_()` 发生在 `scaler.step()` 之前，因此如果想让它裁剪“真实梯度”，就必须提前手动 `unscale_()`。

---

<a id="origin-3839"></a>
## 70. 先看 Loss Scaling 做了什么

假设真实的 loss 为：

```math
L
```

GradScaler 当前的缩放倍数为：

```math
S=1024
```

代码：

```python
scaler.scale(loss).backward()
```

实际上相当于先计算：

```math
L'=SL
```

然后对：

```math
L'
```

进行反向传播。

原本真实梯度为：

```math
g=\frac{\partial L}{\partial W}
```

放大 loss 之后得到：

```math
g'
=
\frac{\partial (SL)}{\partial W}
=
S\frac{\partial L}{\partial W}
=
Sg
```

也就是说：

```text
真实梯度 g
    ↓
乘以 Scale
    ↓
Scaled Gradient = Sg
```

例如：

```math
g=0.002
```

如果：

```math
S=1024
```

那么反向传播之后 `.grad` 里面保存的是：

```math
g'
=
1024\times0.002
=
2.048
```

因此此时：

```python
parameter.grad
```

里面看到的并不是：

```text
0.002
```

而是：

```text
2.048
```

---

<a id="origin-3943"></a>
## 71. 没有 `clip_grad_norm_()` 时为什么不用手动 `unscale_()`？

正常的 AMP 代码可以写成：

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

这里没有显式写：

```python
scaler.unscale_(optimizer)
```

但代码依然是正确的。

因为：

```python
scaler.step(optimizer)
```

内部会帮我们完成必要的 `unscale`。

可以近似理解为：

```python
def scaler_step(optimizer):

    if optimizer 还没有被 unscale:
        unscale_(optimizer)

    检查梯度中是否存在 inf / nan

    if 梯度正常:
        optimizer.step()
```

因此：

```python
scaler.step(optimizer)
```

并不是简单等价于：

```python
optimizer.step()
```

而更像是：

```text
恢复真实梯度
+
检查 Inf / NaN
+
optimizer.step()
```

---

<a id="origin-4009"></a>
## 72. `scaler.step()` 到底是怎么自动恢复梯度的？

假设：

```math
S=1024
```

真实梯度：

```math
g=0.002
```

反向传播后得到：

```math
g'=Sg
```

即：

```math
g'
=
1024\times0.002
=
2.048
```

此时：

```text
.grad = 2.048
```

GradScaler 自己知道当前：

```text
scale = 1024
```

所以 `scaler.step()` 内部可以执行：

```math
g
=
\frac{g'}{S}
```

即：

```math
g
=
\frac{2.048}{1024}
=
0.002
```

于是整个过程为：

```text
真实梯度
0.002

    ↓ × 1024

Scaled Gradient
2.048

    ↓ scaler.step()

内部执行：
2.048 / 1024

    ↓

真实梯度
0.002

    ↓

optimizer.step()
```

因此所谓：

> `scaler.step()` 自动恢复梯度

本质上没有什么神秘的。

就是：

> GradScaler 知道自己之前把 loss 放大了多少倍，因此在参数更新前，再把梯度除以相同的倍数。

---

<a id="origin-4107"></a>
## 73. 所以没有梯度裁剪时可以直接这样写

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

执行过程：

```text
loss
 │
 │ × Scale
 ▼
scaled_loss
 │
 │ backward()
 ▼
scaled gradient
 │
 │
 ▼
scaler.step(optimizer)
 │
 ├── 自动 unscale
 │
 ▼
真实 gradient
 │
 ├── 检查 Inf / NaN
 │
 ▼
optimizer.step()
```

这里没有任何代码需要在：

```python
backward()
```

和：

```python
scaler.step()
```

之间读取或者修改真实梯度。

所以：

> 没有必要提前手动 `unscale_()`。

---

<a id="origin-4165"></a>
## 74. 加入 `clip_grad_norm_()` 后，问题出现了

现在我们想限制梯度范数：

```python
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)
```

假设真实梯度仍然是：

```math
g=0.002
```

显然：

```math
0.002<1
```

这个梯度其实根本不应该被裁剪。

但是经过 Loss Scaling：

```math
S=1024
```

反向传播之后：

```math
g'
=
1024\times0.002
=
2.048
```

此时 `.grad` 里面是：

```text
2.048
```

---

<a id="origin-4214"></a>
## 75. 如果直接 Clip 会发生什么？

如果这样写：

```python
scaler.scale(loss).backward()

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)
scaler.update()
```

那么 `clip_grad_norm_()` 读取到的是：

```text
2.048
```

而不是：

```text
0.002
```

于是它看到：

```math
2.048>1
```

就会认为：

> 梯度太大了，需要裁剪。

但是实际上真实梯度：

```math
0.002
```

根本不大。

也就是说：

```text
真实梯度：

0.002
```

本来应该：

```text
不裁剪
```

但是因为 Loss Scaling：

```text
0.002
   ↓ ×1024
2.048
```

`clip_grad_norm_()` 错误地看到：

```text
2.048 > 1
```

于是进行了不该进行的裁剪。

---

<a id="origin-4292"></a>
## 76. 所以必须在 Clip 之前先恢复真实梯度

正确写法：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)

scaler.update()
```

执行过程：

```text
真实梯度
0.002

    ↓ Loss Scaling

Scaled Gradient
2.048

    ↓ scaler.unscale_(optimizer)

真实梯度
0.002

    ↓ clip_grad_norm_()

按照真实梯度判断是否需要裁剪

    ↓

scaler.step(optimizer)

    ↓

optimizer.step()
```

---

<a id="origin-4342"></a>
## 77. `unscale_()` 的真正目的是什么？

这里非常容易产生一个误解：

> 是不是因为 `optimizer.step()` 必须使用真实梯度，所以必须手动 `unscale_()`？

并不是。

因为：

```python
scaler.step(optimizer)
```

本身就会自动完成 `unscale`。

真正的问题是：

```python
clip_grad_norm_()
```

发生在：

```python
scaler.step()
```

之前。

因此：

> 如果想在 `scaler.step()` 之前对梯度进行任何依赖真实数值的操作，就需要提前把梯度恢复回来。

所以真正的逻辑是：

```text
不是 optimizer.step() 需要手动 unscale

而是 clip_grad_norm_() 需要看到真实梯度
```

---

<a id="origin-4386"></a>
## 78. 为什么 `clip_grad_norm_()` 自己不能自动 `unscale`？

因为：

```python
torch.nn.utils.clip_grad_norm_()
```

本身完全不知道 GradScaler 的存在。

它接收到的只有：

```python
model.parameters()
```

以及：

```python
max_norm
```

例如：

```python
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    1.0
)
```

它做的事情非常简单：

```text
读取 parameter.grad
        ↓
计算 Gradient Norm
        ↓
判断是否超过 max_norm
        ↓
如果超过，就缩小梯度
```

它并不知道：

```text
你有没有用 AMP

你有没有使用 GradScaler

scale 是多少

当前 gradient 有没有被 scale

应该除以多少
```

例如它根本不知道当前：

```text
scale = 1024
```

还是：

```text
scale = 65536
```

因此：

> `clip_grad_norm_()` 没有能力自动执行 `unscale`。

---

<a id="origin-4461"></a>
## 79. 那手动 `unscale_()` 后，`scaler.step()` 不会又除一次吗？

不会。

例如我们写：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    1.0
)

scaler.step(optimizer)
```

可能会担心：

```text
第一次：

2.048 / 1024
=
0.002
```

然后 `scaler.step()` 再执行一次：

```text
0.002 / 1024
```

这样梯度岂不是又变小了？

实际上不会。

---

<a id="origin-4502"></a>
## 80. GradScaler 会记录当前 optimizer 是否已经 unscale

当你执行：

```python
scaler.unscale_(optimizer)
```

之后，GradScaler 会记录：

```text
这个 optimizer 的梯度已经 unscale 过了
```

因此后面执行：

```python
scaler.step(optimizer)
```

时，可以近似理解为：

```python
if optimizer 没有执行过 unscale:
    scaler.unscale_(optimizer)

optimizer.step()
```

如果之前已经：

```python
scaler.unscale_(optimizer)
```

那么就：

```text
跳过第二次 unscale
```

因此不存在重复除法。

---

<a id="origin-4547"></a>
## 81. 两种情况完整对比

<a id="origin-4549"></a>
### 81.1 情况一：没有 `clip_grad_norm_()`

代码：

```python
scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

流程：

```text
loss
 ↓
scale
 ↓
scaled loss
 ↓
backward
 ↓
scaled gradient
 ↓
scaler.step()
 ↓
自动 unscale
 ↓
真实 gradient
 ↓
optimizer.step()
```

因此：

```python
scaler.unscale_(optimizer)
```

可以不写。

---

<a id="origin-4593"></a>
### 81.2 情况二：有 `clip_grad_norm_()`

代码：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)

scaler.update()
```

流程：

```text
loss
 ↓
scale
 ↓
scaled loss
 ↓
backward
 ↓
scaled gradient
 ↓
手动 unscale
 ↓
真实 gradient
 ↓
clip_grad_norm_
 ↓
裁剪后的真实 gradient
 ↓
scaler.step()
 ↓
发现已经 unscale
 ↓
不再重复 unscale
 ↓
optimizer.step()
```

---

<a id="origin-4644"></a>
## 82. 两段代码放在一起看最清楚

<a id="origin-4646"></a>
### 82.1 不使用梯度裁剪

```python
optimizer.zero_grad()

with autocast():
    output = model(x)
    loss = criterion(output, y)

scaler.scale(loss).backward()

scaler.step(optimizer)

scaler.update()
```

这里：

```python
scaler.step(optimizer)
```

内部会自动完成：

```python
unscale
```

---

<a id="origin-4676"></a>
### 82.2 使用梯度裁剪

```python
optimizer.zero_grad()

with autocast():
    output = model(x)
    loss = criterion(output, y)

scaler.scale(loss).backward()

# 先恢复真实梯度
scaler.unscale_(optimizer)

# 再按照真实梯度进行裁剪
torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_norm=1.0
)

scaler.step(optimizer)

scaler.update()
```

---

<a id="origin-4703"></a>
## 83. 最值得记住的一句话

不要把它理解成：

```text
用了 clip
↓
所以必须 unscale
```

更准确的理解应该是：

```text
只要你需要在 scaler.step() 之前
读取或者修改“真实梯度”

↓
就必须提前 unscale
```

而：

```python
clip_grad_norm_()
```

恰好属于这种操作。

---

<a id="origin-4733"></a>
## 84. 最终总结

正常情况下：

```python
scaler.scale(loss).backward()
scaler.step(optimizer)
```

完全可以，因为：

```text
scaler.step()
=
自动 unscale
+
Inf / NaN 检查
+
optimizer.step()
```

但是如果中间需要：

```python
clip_grad_norm_()
```

就必须变成：

```python
scaler.scale(loss).backward()

scaler.unscale_(optimizer)

clip_grad_norm_()

scaler.step(optimizer)
```

原因是：

> `clip_grad_norm_()` 必须根据真实梯度进行裁剪，而不能根据 Loss Scaling 之后被人为放大的梯度进行裁剪。

所以最终可以记成：

```text
没有 Clip：

backward
    ↓
scaled gradient
    ↓
scaler.step
    ↓
自动 unscale
    ↓
optimizer.step
```

而有 Clip：

```text
backward
    ↓
scaled gradient
    ↓
手动 unscale
    ↓
真实 gradient
    ↓
clip
    ↓
scaler.step
    ↓
optimizer.step
```

最核心的一句话：

> **`unscale_()` 不是为了帮助 `optimizer.step()`，而是为了让发生在 `scaler.step()` 之前的梯度操作能够看到真实梯度。**


<a id="origin-4815"></a>
## 85. Loss Scaling 为什么只给 Loss 乘一个系数，就能保护整个 Backward？

理解 Loss Scaling，最关键的不是最终的 `parameter.grad`，而是：

> **Backward 过程中存在大量“中间梯度”，这些中间梯度可能以 FP16 参与计算，因此可能在到达 FP32 的 `.grad` 之前就已经下溢成 0。**

Loss Scaling 真正主要保护的，就是这些 **Backward 中间梯度**。

---

<a id="origin-4825"></a>
## 86. 先明确：FP16 在 Backward 阶段到底干什么？

混合精度训练中，FP16 并不是只用于 Forward。

Backward 本身也需要做大量矩阵运算。

例如一个最简单的线性层：

```math
Y=XW
```

Forward 要计算：

```math
Y=XW
```

Backward 时需要计算两个重要梯度：

```math
\frac{\partial L}{\partial X}
=
\frac{\partial L}{\partial Y}W^T
```

以及：

```math
\frac{\partial L}{\partial W}
=
X^T\frac{\partial L}{\partial Y}
```

这两个式子本质上也都是大型矩阵乘法。

所以：

```text
Forward
X @ W
    ↓
可以使用 FP16 / Tensor Core
    ↓
加速计算

Backward
dY @ Wᵀ
Xᵀ @ dY
    ↓
同样包含大量矩阵乘
    ↓
也可以使用低精度计算
```

因此 FP16 在 Backward 中的主要作用仍然是：

```text
更快
+
减少带宽和显存压力
+
利用 Tensor Core
```

但是随之而来的问题就是：

> **Backward 中的梯度通常非常小，FP16 表示范围有限，小梯度可能下溢。**

---

<a id="origin-4896"></a>
## 87. 最终 `.grad` 是 FP32，为什么还会有问题？

这是最容易困惑的地方。

假设模型参数：

```python
W.dtype == torch.float32
```

那么很多普通 AMP 训练场景下：

```python
W.grad.dtype == torch.float32
```

也就是说最终用于 optimizer 的参数梯度通常会累积在 FP32 中。

于是很容易产生一个想法：

> 最后都是 FP32 存梯度，那 FP16 下溢有什么关系？

问题是：

> **梯度在到达最终 FP32 `.grad` 之前，还需要经过一长串 Backward 中间计算。**

如果中途已经丢失，FP32 再精确也救不回来。

---

<a id="origin-4926"></a>
## 88. 什么叫 Backward 中间梯度？

假设网络结构：

```text
x
↓
Layer1
↓
h1
↓
Layer2
↓
h2
↓
Layer3
↓
y
↓
Loss
```

Backward 从 Loss 开始：

```text
Loss
 ↑
dL/dy
 ↑
Layer3
 ↑
dL/dh2
 ↑
Layer2
 ↑
dL/dh1
 ↑
Layer1
 ↑
dL/dx
```

其中：

```math
\frac{\partial L}{\partial y}
```

```math
\frac{\partial L}{\partial h_2}
```

```math
\frac{\partial L}{\partial h_1}
```

都属于：

> **中间梯度**

它们不是最终某个参数的 `.grad`，而是：

> 用来继续向前传播梯度的临时梯度信号。

---

<a id="origin-4992"></a>
## 89. 以一个线性层为例看得最清楚

假设：

```math
Y=XW
```

Backward 时，上游先传下来：

```math
G_Y
=
\frac{\partial L}{\partial Y}
```

然后这一层计算：

```math
G_X
=
\frac{\partial L}{\partial X}
=
G_YW^T
```

同时：

```math
G_W
=
\frac{\partial L}{\partial W}
=
X^TG_Y
```

整个流程：

```text
上游传来的梯度
G_Y = dL/dY
        │
        ├──────────────┐
        │              │
        ▼              ▼

G_Y @ Wᵀ           Xᵀ @ G_Y

        │              │
        ▼              ▼

G_X = dL/dX       G_W = dL/dW

        │              │
        ▼              ▼

继续向前传播      累积到 W.grad
                  通常最终是 FP32
```

这里真正危险的是左边：

```text
G_Y
↓
G_X
↓
下一层的中间梯度
↓
再下一层的中间梯度
```

这些中间梯度可能在低精度路径中参与计算。

---

<a id="origin-5068"></a>
## 90. FP16 下溢发生在哪里？

假设某个中间梯度：

```math
G_Y
=
3\times10^{-8}
```

这个数字非常小。

如果它在某个 FP16 运算路径中无法被正常表示，就可能：

```math
3\times10^{-8}
\rightarrow
0
```

于是后面：

```math
G_X
=
G_YW^T
```

就变成：

```math
G_X
=
0\times W^T
=
0
```

同样：

```math
G_W
=
X^TG_Y
```

也可能变成：

```math
G_W
=
X^T\times0
=
0
```

于是整个过程变成：

```text
真实中间梯度

3 × 10⁻⁸

    ↓

FP16 中间计算

    ↓

下溢成 0

    ↓

后面所有计算看到的都是 0

    ↓

最终存进 FP32 .grad

    ↓

仍然是 0
```

因此：

> **FP32 最终存储梯度，并不能挽救已经在 FP16 Backward 中间过程里丢失的梯度。**

---

<a id="origin-5158"></a>
## 91. 所以 Loss Scaling 真正要保护什么？

主要不是保护最终：

```python
W.grad
```

而是保护：

```text
Loss
↓
中间梯度
↓
中间梯度
↓
中间梯度
↓
……
↓
最终参数梯度
```

也就是：

> **从 Loss 一路反向传播到各个参数 `.grad` 之前的那些中间梯度。**

---

<a id="origin-5188"></a>
## 92. 那为什么只给一个 Loss 标量乘 1024 就够了？

假设原来的 Loss：

```math
L
```

我们不直接做：

```python
loss.backward()
```

而是：

```python
scaler.scale(loss).backward()
```

假设：

```math
S=1024
```

那么相当于构造：

```math
L'=SL
```

即：

```math
L'=1024L
```

关键来了。

假设我们要求：

```math
\frac{\partial L'}{\partial W}
```

那么：

```math
\frac{\partial L'}{\partial W}
=
\frac{\partial (SL)}{\partial W}
```

因为：

```math
S
```

是常数，所以：

```math
\frac{\partial L'}{\partial W}
=
S\frac{\partial L}{\partial W}
```

即：

```math
\boxed{
\frac{\partial L'}{\partial W}
=
S
\frac{\partial L}{\partial W}
}
```

所以只要：

```math
Loss\times1024
```

最终所有梯度都会自动：

```math
\times1024
```

---

<a id="origin-5281"></a>
## 93. 为什么“所有中间梯度”也会一起放大？

这里才是 Loss Scaling 最核心的地方。

假设计算图：

```text
W
↓
h1
↓
h2
↓
y
↓
L
```

正常 Backward：

```math
\frac{\partial L}{\partial W}
=
\frac{\partial L}{\partial y}
\frac{\partial y}{\partial h_2}
\frac{\partial h_2}{\partial h_1}
\frac{\partial h_1}{\partial W}
```

现在把：

```math
L
```

改成：

```math
L'=SL
```

首先：

```math
\frac{\partial L'}{\partial y}
=
\frac{\partial (SL)}{\partial y}
=
S\frac{\partial L}{\partial y}
```

所以第一个中间梯度直接被放大：

```math
\frac{\partial L'}{\partial y}
=
S
\frac{\partial L}{\partial y}
```

继续向前：

```math
\frac{\partial L'}{\partial h_2}
=
\frac{\partial L'}{\partial y}
\frac{\partial y}{\partial h_2}
```

代入：

```math
\frac{\partial L'}{\partial h_2}
=
S
\frac{\partial L}{\partial y}
\frac{\partial y}{\partial h_2}
```

所以：

```math
\frac{\partial L'}{\partial h_2}
=
S
\frac{\partial L}{\partial h_2}
```

继续：

```math
\frac{\partial L'}{\partial h_1}
=
S
\frac{\partial L}{\partial h_1}
```

最后：

```math
\frac{\partial L'}{\partial W}
=
S
\frac{\partial L}{\partial W}
```

因此：

```text
Loss × S

    ↓

dL/dy × S

    ↓

dL/dh2 × S

    ↓

dL/dh1 × S

    ↓

dL/dW × S
```

也就是说：

> **Scale 不是只影响最终梯度，而是会顺着链式法则，把整条 Backward 路径中的中间梯度一起放大。**

---

<a id="origin-5415"></a>
## 94. 可以把 Loss Scaling 理解成在 Backward 入口放一个总放大器

正常情况下：

```text
Loss
 │
 ▼
dL/dy
 │
 ▼
dL/dh2
 │
 ▼
dL/dh1
 │
 ▼
dL/dW
```

加入 Loss Scaling：

```text
Loss
 │
 │ × 1024
 ▼
Scaled Loss
 │
 ▼
1024 × dL/dy
 │
 ▼
1024 × dL/dh2
 │
 ▼
1024 × dL/dh1
 │
 ▼
1024 × dL/dW
```

所以完全没有必要手工写：

```text
每个梯度 × 1024
```

只需要在最顶端：

```math
L'=1024L
```

链式法则就自动帮你完成整条反向传播的缩放。

---

<a id="origin-5473"></a>
## 95. 一个具体数字例子

假设某个中间梯度本来是：

```math
\frac{\partial L}{\partial h}
=
3\times10^{-8}
```

如果直接用低精度 Backward：

```text
3 × 10⁻⁸
↓
FP16
↓
可能下溢
↓
0
```

现在使用：

```math
S=1024
```

那么：

```math
L'=1024L
```

所以：

```math
\frac{\partial L'}{\partial h}
=
1024
\times
3\times10^{-8}
```

得到：

```math
3.072\times10^{-5}
```

于是：

```text
原中间梯度：

3 × 10⁻⁸

    ↓ × 1024

3.072 × 10⁻⁵

    ↓

FP16 更容易表示

    ↓

Backward 继续正常传播
```

这就是 Loss Scaling 的核心。

---

<a id="origin-5547"></a>
## 96. 最终为什么还要 Unscale？

因为：

```math
L'=SL
```

之后得到的是放大的梯度：

```math
g'=Sg
```

比如真实梯度：

```math
g=0.002
```

Scale：

```math
S=1024
```

Backward 后：

```math
g'
=
2.048
```

但真正更新参数时显然不能用：

```math
2.048
```

因为我们真正想要的是：

```math
0.002
```

所以在参数更新之前：

```math
g
=
\frac{g'}{S}
```

即：

```math
g
=
\frac{2.048}{1024}
=
0.002
```

这就是：

```python
scaler.unscale_(optimizer)
```

做的事情。

---

<a id="origin-5621"></a>
## 97. 整个完整流程

假设真实中间梯度非常小：

```math
3\times10^{-8}
```

正常 FP16 Backward：

```text
Loss
 ↓
Backward
 ↓
中间梯度
3 × 10⁻⁸
 ↓
FP16 下溢
 ↓
0
 ↓
后面梯度信息全部丢失
```

Loss Scaling 后：

```text
Loss
 ↓
× 1024
 ↓
Scaled Loss
 ↓
Backward
 ↓
所有中间梯度自动 × 1024
 ↓
3.072 × 10⁻⁵
 ↓
避免过早下溢
 ↓
梯度正常传播
 ↓
最终参数梯度累积
 ↓
unscale
 ↓
÷ 1024
 ↓
恢复真实梯度
 ↓
optimizer.step()
```

---

<a id="origin-5678"></a>
## 98. 和 FP32 `.grad` 的关系

可以把混合精度 Backward 粗略分成三类数据：

| 数据                     | 常见情况             | 作用               |
| ---------------------- | ---------------- | ---------------- |
| Forward 保存的 Activation | FP16/BF16 或 FP32 | Backward 时重新计算梯度 |
| Backward 中间梯度          | 可能参与低精度计算        | 将梯度继续向前传播        |
| 参数 `.grad`             | FP32 参数时通常为 FP32 | 最终用于 Optimizer   |

因此：

```text
FP16 / 低精度最危险的地方
        ↓
不是只有最终 .grad
        ↓
而是整个 Backward 中间梯度传播过程
```

---

<a id="origin-5700"></a>
## 99. 一个线性层的完整图

Forward：

```math
Y=XW
```

Backward：

```math
G_Y
=
\frac{\partial L}{\partial Y}
```

然后：

```math
G_X
=
G_YW^T
```

以及：

```math
G_W
=
X^TG_Y
```

可以画成：

```text
                 Loss
                  │
                  ▼

           G_Y = dL/dY
           中间梯度
                  │
          ┌───────┴────────┐
          │                │
          ▼                ▼

      G_Y @ Wᵀ          Xᵀ @ G_Y

          │                │
          ▼                ▼

     G_X = dL/dX       G_W = dL/dW
     中间梯度              │
          │                ▼
          │             W.grad
          │             通常 FP32
          ▼
     继续向前传播
```

其中：

```text
G_Y
G_X
```

这种中间梯度，正是 Loss Scaling 特别要保护的对象。

---

<a id="origin-5771"></a>
## 100. 为什么最后 FP32 保存还不够？

因为如果中间已经：

```text
3 × 10⁻⁸
↓
FP16
↓
0
```

那么后面：

```text
0
↓
转换为 FP32
↓
0.000000
```

FP32 并不会神奇地恢复成：

```text
3 × 10⁻⁸
```

所以：

> **FP32 只能准确保存“已经算出来的梯度”，不能恢复“已经在 FP16 中丢失的梯度”。**

---

<a id="origin-5805"></a>
## 101. Loss Scaling 真正解决的问题

因此不要把 Loss Scaling 简单理解成：

> 把最终梯度放大。

更准确的理解是：

> **Loss Scaling 在 Backward 开始之前，把整个梯度信号整体抬高，从而让 Backward 中那些需要参与低精度计算的中间梯度，不那么容易在传播过程中下溢成 0。**

---

<a id="origin-5817"></a>
## 102. 为什么只乘 Loss 一个标量就足够？

因为整个神经网络训练最终只有一个标量目标：

```math
L
```

所有梯度：

```math
\frac{\partial L}{\partial W_1}
```

```math
\frac{\partial L}{\partial W_2}
```

```math
\frac{\partial L}{\partial h_1}
```

```math
\frac{\partial L}{\partial h_2}
```

本质上全部是：

> “这个变量发生一点变化，会对最终 Loss 产生多大影响？”

因此只要把：

```math
L
```

变成：

```math
SL
```

那么所有：

```math
\frac{\partial L}{\partial(\cdot)}
```

自然都会变成：

```math
S
\frac{\partial L}{\partial(\cdot)}
```

即：

```math
\boxed{
L'=SL
}
```

直接导致：

```math
\boxed{
\frac{\partial L'}{\partial z}
=
S
\frac{\partial L}{\partial z}
}
```

这里的：

```math
z
```

可以是：

```text
参数 W
Activation h
中间输出 y
任何计算图中的变量
```

---

<a id="origin-5908"></a>
## 103. 最终一句话总结

Loss Scaling 不是主要为了：

```text
把最终 FP32 .grad 放大
```

而是为了：

```text
Loss × Scale
        ↓
整条 Backward 的梯度信号一起被放大
        ↓
中间梯度不容易在 FP16 计算阶段下溢
        ↓
梯度成功传播到各层
        ↓
最终累积到 FP32 .grad
        ↓
unscale
        ↓
恢复真实梯度
```

最值得记住的两个公式：

```math
\boxed{L'=SL}
```

以及：

```math
\boxed{
\frac{\partial L'}{\partial z}
=
S
\frac{\partial L}{\partial z}
}
```

所以：

> **只需要给 Loss 这个标量乘一个 Scale，就能够通过链式法则自动把整个 Backward 中所有中间梯度一起放大，这正是 Loss Scaling 能够缓解 FP16 Backward 中间梯度下溢问题的根本原因。**
