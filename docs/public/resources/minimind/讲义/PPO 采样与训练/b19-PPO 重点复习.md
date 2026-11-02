# PPO 重点复习

<a id="origin-6"></a>
## 1. PyTorch 梯度累加原理：为什么 `loss / accumulation_steps` 就够了？

<a id="origin-8"></a>
### 1.1 核心结论

**`loss = loss / args.accumulation_steps` 只负责缩放本次 Loss；真正的梯度累加发生在 `loss.backward()`。**

PyTorch 默认不会在每次 `backward()` 前覆盖已有梯度，而是将新算出的梯度**累加到模型参数的 `.grad` 属性**中。

注意：**不是把多次 Forward 的计算图拼接或累加起来，而是把每次 Backward 计算出的梯度累加起来。**

<a id="origin-16"></a>
### 1.2 最简单的代码

假设累计 4 个小批次才更新一次参数：

```python
accumulation_steps = 4
optimizer.zero_grad()

for i in range(4):
    output = model(x[i])
    loss = criterion(output, y[i])

    loss = loss / accumulation_steps  # 本次梯度也会缩小为 1/4
    loss.backward()                   # 自动累加到 parameter.grad

optimizer.step()                      # 四次反向传播后，更新一次参数
optimizer.zero_grad()                 # 清空梯度，为下一轮做准备
```

虽然代码里没有写 `+=`，但 `loss.backward()` 的效果可以**概念性地**理解为：

```python
parameter.grad += current_gradient
```

注意，这只是帮助理解的简化表示，并非 PyTorch 内部实现的逐字代码。

<a id="origin-43"></a>
### 1.3 用数字看看梯度如何累加

假设模型只有一个参数 $w$，四个小批次的 Loss 对 $w$ 的梯度分别为：

$$
\frac{\partial L_1}{\partial w}=4,\quad
\frac{\partial L_2}{\partial w}=8,\quad
\frac{\partial L_3}{\partial w}=12,\quad
\frac{\partial L_4}{\partial w}=16.
$$

因为每次都执行 `loss = loss / 4`，所以反向传播得到的本次梯度分别为 $1,2,3,4$。

| 操作 | 本次梯度 | 累计的 `w.grad` |
|---|---:|---:|
| `optimizer.zero_grad()` | — | 0（或 None） |
| 第 1 次 `backward()` | $4/4=1$ | $1$ |
| 第 2 次 `backward()` | $8/4=2$ | $1+2=3$ |
| 第 3 次 `backward()` | $12/4=3$ | $3+3=6$ |
| 第 4 次 `backward()` | $16/4=4$ | $6+4=10$ |
| `optimizer.step()` | — | 使用梯度 $10$ 更新 $w$ |

最终梯度：

$$
\boxed{
\frac{\partial L}{\partial w}
=\frac{4+8+12+16}{4}
=10
}
$$

在这些 Loss 都表示等权、同样归一化方式的小批次损失时，这相当于先定义总 Loss：

$$
L=\frac{L_1+L_2+L_3+L_4}{4}
$$

再反向传播一次。实际训练中使用梯度累加，就不必同时保留四个小批次的计算图。

<a id="origin-83"></a>
### 1.4 为什么计算图本身没有累加？

```text
第 1 次 Forward → 计算图 1 → backward() → w.grad = 1
                                    （图 1 通常被释放）

第 2 次 Forward → 计算图 2 → backward() → w.grad = 3
                                    （图 2 通常被释放）

第 3 次 Forward → 计算图 3 → backward() → w.grad = 6
                                    （图 3 通常被释放）

第 4 次 Forward → 计算图 4 → backward() → w.grad = 10
                                    （图 4 通常被释放）

optimizer.step() → 使用 w.grad = 10 更新参数
```

每次 Forward 都建立各自的计算图；每次 Backward 通过该图算出梯度，然后将结果累加到**同一批模型参数的 `.grad` 中**。

因此，累加期间只要不提前清空 `.grad`，前面几次计算得到的梯度就不会丢失。

<a id="origin-105"></a>
### 1.5 四个操作分别负责什么？

| 操作 | 作用 |
|---|---|
| `loss /= accumulation_steps` | 缩放每次的 Loss，因此也缩放对应梯度 |
| `loss.backward()` | 根据本次计算图求梯度，并累加到参数 `.grad` |
| `optimizer.step()` | 使用当前 `.grad` 更新模型参数 |
| `optimizer.zero_grad()` | 清除旧梯度，开始新一轮累计 |

**注意：如果每次 `backward()` 后都调用 `zero_grad()`，就无法实现跨小批次的梯度累加。**

另外，如果最后一组不足 4 个小批次，需要相应调整归一化方式；小批次样本量不同、使用按 token 平均的 Loss 等情况，也要按实际有效样本或 token 数加权，才能严格等价于一次大批次训练。

<a id="origin-118"></a>
### 1.6 一句话总结

> **`loss / accumulation_steps` 负责让每次梯度变小，`backward()` 负责自动把梯度加到 `.grad`；累计若干次以后，`optimizer.step()` 才真正更新模型参数。累加的是梯度，不是计算图。**

---

<a id="origin-124"></a>
## 2. Causal Mask、Attention Mask 与 Loss Mask 的区别

<a id="origin-126"></a>
### 2.1 两行代码分别在做什么？

```python
# 第一行：Causal Mask（因果掩码）
if self.is_causal:
    scores[:, :, :, -seq_len:] += torch.full(
        (seq_len, seq_len),
        float("-inf"),
        device=scores.device
    ).triu(1)

# 第二行：Attention Mask（这里用于 Padding Mask）
if attention_mask is not None:
    scores += (
        1.0 - attention_mask.unsqueeze(1).unsqueeze(2)
    ) * -1e9
```

虽然两行代码都是给 Attention Score 加上很大的负数，让 Softmax 后的概率接近 0，但目的不同。

- **Causal Mask：防止当前 Token 看到未来的 Token。**
- **Padding Mask：防止 Token 关注 PAD 等无效位置。**

二者都作用在 Attention Score 上，而不是直接作用在 Loss 上。

---

<a id="origin-153"></a>
### 2.2 第一行：Causal Mask（因果掩码）

假设输入句子：

```text
位置：   0    1     2      3
Token：  我   喜欢   人工    智能
```

在 Decoder-only 模型中，每个 Token 只能看到自己和前面的 Token。

| Query \ Key | 我 | 喜欢 | 人工 | 智能 |
|---|---|---|---|---|
| 我 | ✓ | × | × | × |
| 喜欢 | ✓ | ✓ | × | × |
| 人工 | ✓ | ✓ | ✓ | × |
| 智能 | ✓ | ✓ | ✓ | ✓ |

其中：

- 行表示 Query。
- 列表示 Key。
- ✓ 表示允许关注。
- × 表示不允许关注。

<a id="origin-178"></a>
#### 2.2.1 triu(1) 的作用

```python
torch.full((4, 4), float("-inf")).triu(1)
```

得到矩阵：

$$
M_{\text{causal}}=
\begin{bmatrix}
0 & -\infty & -\infty & -\infty\\
0 & 0 & -\infty & -\infty\\
0 & 0 & 0 & -\infty\\
0 & 0 & 0 & 0
\end{bmatrix}
$$

`triu(1)` 表示保留主对角线上方的元素，将其余位置设为 0。

<a id="origin-198"></a>
#### 2.2.2 加到 Attention Score 上

假设原始 Attention Score：

$$
S=
\begin{bmatrix}
1&2&3&4\\
2&3&4&5\\
3&4&5&6\\
4&5&6&7
\end{bmatrix}
$$

执行：

$$
S'=S+M_{\text{causal}}
$$

得到：

$$
S'=
\begin{bmatrix}
1&-\infty&-\infty&-\infty\\
2&3&-\infty&-\infty\\
3&4&5&-\infty\\
4&5&6&7
\end{bmatrix}
$$

再经过 Softmax：

$$
\operatorname{Softmax}(x_i)
=
\frac{e^{x_i}}{\sum_j e^{x_j}}
$$

由于：

$$
e^{-\infty}=0
$$

被 Mask 的位置对应的 Attention Weight 就变成了 0。

**结果：每个 Token 只能看到自己和前面的 Token，不能看到未来。**

<a id="origin-248"></a>
#### 2.2.3 为什么使用 -seq_len？

```python
scores[:, :, :, -seq_len:]
```

假设使用 KV Cache：

- 前面已经缓存了 3 个 Token 的 K、V。
- 当前一次输入 2 个新 Token。
- Query 长度是 2。
- Key 长度是 5。

因此：

```python
scores.shape = [batch_size, num_heads, 2, 5]
```

此时只需要对最后两个新 Token 对应的 Key 列施加局部 Causal Mask。

```text
                缓存的 Key     新的 Key
                  K0 K1 K2     K3 K4

新 Query Q3        ✓  ✓  ✓      ✓  ×
新 Query Q4        ✓  ✓  ✓      ✓  ✓
```

所以代码使用：

```python
scores[:, :, :, -seq_len:]
```

选择最后 `seq_len` 列。

这样过去缓存的 Key 不受因果掩码阻挡，而新输入的 Token 仍然不能看到未来的 Token。

注意：这是针对 Key 按时间顺序排列、缓存中都是过去 Token 的实现方式。

---

<a id="origin-291"></a>
### 2.3 第二行：Attention Mask（Padding Mask）

代码：

```python
if attention_mask is not None:
    scores += (
        1.0 - attention_mask.unsqueeze(1).unsqueeze(2)
    ) * -1e9
```

假设一个 Batch 里面有两个句子：

```text
句子 A：我 喜欢 人工 智能
句子 B：我 爱 PAD PAD
```

为了使两个句子长度一致，需要把句子 B 补齐到长度 4。

对于句子 B：

```python
attention_mask = [1, 1, 0, 0]
```

这里：

- 1：有效 Token，允许被关注。
- 0：Padding Token，不允许被关注。

<a id="origin-322"></a>
#### 2.3.1 先执行减法

```python
1.0 - attention_mask
```

得到：

```text
[0, 0, 1, 1]
```

<a id="origin-334"></a>
#### 2.3.2 再乘上 -1e9

```python
(1.0 - attention_mask) * -1e9
```

得到：

```text
[0, 0, -1e9, -1e9]
```

<a id="origin-346"></a>
#### 2.3.3 unsqueeze 的作用

假设：

```python
attention_mask.shape = [batch_size, seq_len]
```

经过：

```python
attention_mask.unsqueeze(1).unsqueeze(2)
```

变成：

```python
[batch_size, 1, 1, seq_len]
```

而 Attention Score 的形状通常是：

```python
[batch_size, num_heads, query_len, key_len]
```

通过广播机制，每个 Attention Head、每个 Query 都会使用同一个 Padding Mask。

最终对于句子 B，相当于加上：

$$
M_{\text{padding}}=
\begin{bmatrix}
0&0&-10^9&-10^9\\
0&0&-10^9&-10^9\\
0&0&-10^9&-10^9\\
0&0&-10^9&-10^9
\end{bmatrix}
$$

对应的可见关系：

| Query \ Key | 我 | 爱 | PAD | PAD |
|---|---|---|---|---|
| 我 | ✓ | ✓ | × | × |
| 爱 | ✓ | ✓ | × | × |
| PAD | ✓ | ✓ | × | × |
| PAD | ✓ | ✓ | × | × |

**注意：Padding Mask 本身不阻止看到未来，它只是阻止关注无效的 Key。**

例如第一个 Token“我”仍然可以看到第二个 Token“爱”。

所以 Padding Mask 不能代替 Causal Mask。

---

<a id="origin-403"></a>
### 2.4 两行代码一起执行会发生什么？

继续使用句子：

```text
我 爱 PAD PAD
```

<a id="origin-411"></a>
#### 2.4.1 只使用 Causal Mask

| Query \ Key | 我 | 爱 | PAD | PAD |
|---|---|---|---|---|
| 我 | ✓ | × | × | × |
| 爱 | ✓ | ✓ | × | × |
| PAD | ✓ | ✓ | ✓ | × |
| PAD | ✓ | ✓ | ✓ | ✓ |

特点：

- 不能看到未来。
- 但后面的 Token 仍可能关注前面的 PAD。

<a id="origin-425"></a>
#### 2.4.2 只使用 Padding Mask

| Query \ Key | 我 | 爱 | PAD | PAD |
|---|---|---|---|---|
| 我 | ✓ | ✓ | × | × |
| 爱 | ✓ | ✓ | × | × |
| PAD | ✓ | ✓ | × | × |
| PAD | ✓ | ✓ | × | × |

特点：

- 无法关注 PAD。
- 但可以看到未来的有效 Token。

<a id="origin-439"></a>
#### 2.4.3 同时使用 Causal Mask 和 Padding Mask

| Query \ Key | 我 | 爱 | PAD | PAD |
|---|---|---|---|---|
| 我 | ✓ | × | × | × |
| 爱 | ✓ | ✓ | × | × |
| PAD | ✓ | ✓ | × | × |
| PAD | ✓ | ✓ | × | × |

特点：

- 无法看到未来。
- 无法关注 PAD。
- 满足自回归模型的基本 Attention 限制。

需要注意：

**Padding Mask 通常屏蔽 PAD 对应的 Key 列，不一定屏蔽 PAD 对应的 Query 行。**

所以 PAD 位置仍可能计算 Attention Output。

不过在训练时，这些 PAD 位置通常不会参与 Loss 计算。

---

<a id="origin-464"></a>
### 2.5 与 SFT 中的 Loss Mask 有什么区别？

除了上述两种 Mask，SFT 中经常还存在第三种：

**Loss Mask。**

假设训练数据：

```text
用户：浙江大学在哪里？
助手：浙江省杭州市。
```

我们希望模型根据用户的问题生成助手回答。

<a id="origin-479"></a>
#### 2.5.1 Causal Mask

作用：控制 Token 之间能不能通过 Attention 互相看到。

例如助手生成“浙江省”时：

- 可以看到前面的用户问题。
- 可以看到此前的助手回答。
- 不能看到未来还未生成的“杭州市”。

<a id="origin-489"></a>
#### 2.5.2 Padding Mask

作用：如果序列中存在 PAD，防止模型关注这些无效的 Key。

例如：

```text
用户：浙江大学在哪里？
助手：浙江省杭州市。
PAD PAD PAD
```

PAD 对应的 Key 会被屏蔽。

<a id="origin-503"></a>
#### 2.5.3 Loss Mask

作用：控制哪些 Token 参与 Loss 计算。

例如：

```text
用户部分：不计算 Loss
助手部分：计算 Loss
PAD 部分：不计算 Loss
```

在代码中通常表现为：

```python
labels = input_ids.clone()

# 不训练的位置设置为 -100
labels[不需要训练的位置] = -100

loss = F.cross_entropy(
    logits.reshape(-1, vocab_size),
    labels.reshape(-1),
    ignore_index=-100
)
```

这里省略了因果语言模型中 logits 与 labels 的时间对齐（shift）细节。

需要特别注意：

**不计算用户问题部分的 Loss，并不意味着助手回答无法通过 Attention 看到用户问题。**

例如：

```text
用户：浙江大学在哪里？    不计算 Loss
助手：浙江省杭州市。      计算 Loss
```

计算助手回答的 Loss 时：

1. 助手 Token 可以通过 Attention 读取用户问题。
2. 用户 Token 对应的 Embedding、K、V 等参与了助手输出的计算。
3. 即使用户位置不直接计算 Loss，其相关计算路径仍然可能接收到梯度。
4. 模型仍然能学会利用用户问题来生成回答。

所以：

**Loss Mask 控制是否从当前位置直接产生训练损失，而 Attention Mask 控制信息能否通过 Attention 传递。二者不是一回事。**

---

<a id="origin-556"></a>
### 2.6 三种 Mask 的最终对比

| 对比 | Causal Mask | Padding Mask | Loss Mask |
|---|---|---|---|
| 解决的问题 | 防止看到未来 | 防止关注 PAD | 控制哪些位置计算 Loss |
| 作用位置 | Attention Score | Attention Score | Loss 计算 |
| 典型实现 | 上三角加 -inf | 无效 Key 加 -1e9 | labels 设置 -100 |
| 是否影响 Attention | 是 | 是 | 不直接影响 |
| 是否直接决定计算 Loss 的位置 | 否 | 否 | 是 |
| 典型使用场景 | 自回归语言模型 | Batch 补齐 | SFT 训练 |

<a id="origin-567"></a>
#### 2.6.1 一句话总结

**Causal Mask：时间上能不能看。**

**Padding Mask：这个 Key 是不是有效内容。**

**Loss Mask：这个位置要不要计算训练损失。**

三者虽然都叫 Mask，但控制的是模型计算过程中的三个不同问题。

---


<a id="origin-580"></a>
## 3. 从训练到推理：MiniMind 的 KV Cache 到底怎样建立、保存与逐 Token 拼接？

<a id="origin-582"></a>
### 3.1 先看训练：为什么 `xq / xk / xv` 一开始就是一大串？

假设一条训练样本为：

```text
我  爱  AI  技术  很
 0   1   2    3   4    ← Token 位置
```

在常见的 Decoder-only **Teacher Forcing（教师强制）**训练里，**已经知道整条训练文本**，因此可以一次性把整个序列输入模型，而不需要像聊天生成那样先预测出“爱”、再预测出“AI”、再预测出“技术”。

例如：

```python
input_ids.shape = [1, 5]        # batch_size = 1，序列长度 = 5
```

经过 Embedding：

```python
hidden_states = self.dropout(self.embed_tokens(input_ids))
# hidden_states.shape = [1, 5, 768]
```

然后进入 `Attention.forward()`：

```python
bsz, seq_len, _ = x.shape
# bsz = 1, seq_len = 5

xq, xk, xv = self.q_proj(x), self.k_proj(x), self.v_proj(x)

xq = xq.view(bsz, seq_len, self.n_local_heads, self.head_dim)
xk = xk.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
xv = xv.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
```

用 MiniMind 默认参数举例：

- `hidden_size = 768`
- `num_attention_heads = 8`
- `num_key_value_heads = 4`（GQA）
- `head_dim = 768 / 8 = 96`

于是新投影得到：

| 张量 | `view()` 之后的形状 | 序列维长度 |
|---|---|---:|
| `xq` | `[1, 5, 8, 96]` | 5 |
| `xk` | `[1, 5, 4, 96]` | 5 |
| `xv` | `[1, 5, 4, 96]` | 5 |

**注意：这是因为上游真的传进来 5 个 Token，而不是 Attention 有一个“训练模式下自动把长度扩大”的特殊操作。**

那这样一次性计算，会不会让位置 0 的“我”偷看到后面的“技术”？**不会。**因果注意力（Causal Mask）保证每个位置只能关注自己及其之前的 Token：

```text
             Key：我   爱   AI   技术  很
Query：我           ✓   ×    ×    ×   ×
       爱           ✓   ✓    ×    ×   ×
       AI           ✓   ✓    ✓    ×   ×
       技术         ✓   ✓    ✓    ✓   ×
       很           ✓   ✓    ✓    ✓   ✓
```

这样，**训练时能够并行算出多个位置的预测结果**：

```text
位置 0：输入“我”                  → 预测“爱”
位置 1：输入“我 爱”               → 预测“AI”
位置 2：输入“我 爱 AI”            → 预测“技术”
位置 3：输入“我 爱 AI 技术”       → 预测“很”
```

对应 MiniMind 的训练损失代码，是将模型输出的 `logits` 与 `labels` 错开一个 Token：

```python
x = logits[..., :-1, :].contiguous()
y = labels[..., 1:].contiguous()
loss = F.cross_entropy(x.view(-1, x.size(-1)), y.view(-1), ignore_index=-100)
```

所以，在常规训练里，我们**不必**每预测一个 Token 就再调用一次模型；已知的整段序列直接输入，使用因果掩码来保证预测合法。通常也**不需要**为这个训练步骤启用跨轮复用的 KV Cache。

---

<a id="origin-668"></a>
### 3.2 开始推理：第一次调用为什么也不是长度 1？

现在换成聊天推理：用户只给了 Prompt，模型还不知道未来要生成哪些 Token。

```text
用户 Prompt：我 爱 AI
模型接下来要生成：技术 很 有趣 ...
```

<a id="origin-677"></a>
#### 3.2.1 第一次循环：KV Cache 还不存在

MiniMind 的 `generate()` 开始时：

```python
input_ids = kwargs.pop("input_ids", inputs).repeat(num_return_sequences, 1)
past_key_values = kwargs.pop("past_key_values", None)
```

先假设：

```text
input_ids       = [我, 爱, AI]
past_key_values = None
```

进入生成循环：

```python
past_len = past_key_values[0][0].shape[1] if past_key_values else 0

outputs = self.forward(
    input_ids[:, past_len:],
    attention_mask,
    past_key_values,
    use_cache=use_cache,
    **kwargs
)
```

因为 `past_key_values = None`，所以：

```python
past_len = 0
input_ids[:, past_len:] = input_ids[:, 0:]  # [我, 爱, AI]
```

**第一次送进去的还是整个 Prompt，长度是 3。** 这个过程通常称为 **Prefill**（预填充、处理提示词）。

进入 `MiniMindModel.forward()`：

```python
batch_size, seq_length = input_ids.shape
# seq_length = 3

past_key_values = past_key_values or [None] * len(self.layers)
# 由于没有历史缓存，每层对应 None

start_pos = past_key_values[0][0].shape[1] if past_key_values[0] is not None else 0
# start_pos = 0

hidden_states = self.dropout(self.embed_tokens(input_ids))
# hidden_states.shape = [1, 3, 768]
```

再选取 RoPE 位置：

```python
position_embeddings = (
    self.freqs_cos[start_pos:start_pos + seq_length],
    self.freqs_sin[start_pos:start_pos + seq_length]
)
# 对应位置 0、1、2 的 cos/sin
```

进入某一层的 Attention：

```text
x.shape   = [1, 3, 768]
seq_len   = 3
xq.shape  = [1, 3, 8, 96]
xk.shape  = [1, 3, 4, 96]
xv.shape  = [1, 3, 4, 96]
```

<a id="origin-752"></a>
#### 3.2.2 第一次 KV Cache 是在什么地方“存下来的”？

重点来了：是 **Attention 里先生成 K/V，随后把它们作为返回值交给上层保存**。

`Attention.forward()` 的关键代码顺序为：

```python
# ① 根据当前输入生成 Q、K、V
xq, xk, xv = self.q_proj(x), self.k_proj(x), self.v_proj(x)

# ② 变形、归一化
xq = xq.view(bsz, seq_len, self.n_local_heads, self.head_dim)
xk = xk.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
xv = xv.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
xq, xk = self.q_norm(xq), self.k_norm(xk)

# ③ 对 Q、K 加 RoPE
cos, sin = position_embeddings
xq, xk = apply_rotary_pos_emb(xq, xk, cos, sin)

# ④ 有历史 K/V 才拼接；第一次为 None，因此不拼接
if past_key_value is not None:
    xk = torch.cat([past_key_value[0], xk], dim=1)
    xv = torch.cat([past_key_value[1], xv], dim=1)

# ⑤ 把当前“完整 K/V”组成缓存返回值
past_kv = (xk, xv) if use_cache else None

# ⑥ 后续继续计算 Attention，然后把 output、past_kv 返回
return output, past_kv
```

所以，第一次推理的缓存就是：

```text
K_cache = [k_我, k_爱, k_AI]   # [1, 3, 4, 96]
V_cache = [v_我, v_爱, v_AI]   # [1, 3, 4, 96]
```

这里的 `k_我` 等是**各 Token 在某一 Transformer 层产生的 K 表示**，不是原始的 Token 文本。K 已经过投影、归一化、RoPE；V 已经过投影。

更准确地说，**每个 Transformer 层都有自己的一份 K/V Cache**，而不是整个模型只有一对。MiniMind 默认有 8 层，所以 `past_key_values` 最终包含 8 份 `(K, V)`。

<a id="origin-795"></a>
#### 3.2.3 这份缓存是怎样一路返回到 generate() 的？

```text
某一层 Attention.forward()
    return output, past_kv
                       ↓
MiniMindBlock.forward()
    return hidden_states, present_key_value
                       ↓
MiniMindModel.forward()
    presents.append(present)    # 收集每一层的 (K, V)
    return hidden_states, presents, aux_loss
                       ↓
MiniMindForCausalLM.forward()
    return MoeCausalLMOutputWithPast(
        ..., past_key_values=past_key_values
    )
                       ↓
generate()
    past_key_values = outputs.past_key_values if use_cache else None
```

**这最后一行，就是下一轮生成能够“记住历史 K/V”的直接原因。**

MiniMind 中 `presents` 虽然叫“当前结果”，但它保存的是供**下次 forward 使用**的完整每层 K/V；到了 `generate()`，又赋给 `past_key_values` 这个变量。

<a id="origin-821"></a>
#### 3.2.4 第一次结束时，模型已经生成了“技术”，但“技术”还没有加入 Cache

第一次前向传播结束后，模型用最后一个位置的 logits 选出下一个 Token（假设为“技术”）：

```python
logits = outputs.logits[:, -1, :] / temperature
# ……采样或 argmax 得到 next_token……

input_ids = torch.cat([input_ids, next_token], dim=-1)
past_key_values = outputs.past_key_values if use_cache else None
```

此刻两个东西**长度不同**：

```text
input_ids  = [我, 爱, AI, 技术]          # 长度 4
KV Cache   = [我, 爱, AI] 的 K/V         # 长度 3
```

**为什么 Cache 里还没有“技术”？**因为本轮前向传播时模型的输入只有 `[我, 爱, AI]`；“技术”是前向传播**结束后才预测出来的**，还没有经过下一轮的 Embedding、K/V 投影和 RoPE。它要等到下一轮被模型处理，才能写进 Cache。

这就是为什么下一轮恰好还剩下 **1 个尚未处理的 Token**。

---

<a id="origin-846"></a>
### 3.3 第二次推理：为什么新 Q、K、V 终于都只有长度 1？(重点)

现在：

```text
input_ids   = [我, 爱, AI, 技术]    # 长度 4
KV Cache    = [我, 爱, AI]         # 长度 3
```

<a id="origin-855"></a>
#### 3.3.1 generate() 先切掉已缓存的前 3 个 Token

```python
past_len = past_key_values[0][0].shape[1] if past_key_values else 0
# past_len = 3

outputs = self.forward(input_ids[:, past_len:], ...)
# input_ids[:, 3:] = [技术]，只有 1 个 Token！
```

这一行：

```python
input_ids[:, past_len:]
```

**才是真正导致本轮新计算的 `xq / xk / xv` 序列长度为 1 的源头。** 不是 `start_pos`，也不是 `view()`，更不是 `torch.cat()`。

<a id="origin-873"></a>
#### 3.3.2 MiniMindModel.forward() 接到的输入已只有 1 个 Token

```python
batch_size, seq_length = input_ids.shape
# seq_length = 1

start_pos = past_key_values[0][0].shape[1] if past_key_values[0] is not None else 0
# start_pos = 3

hidden_states = self.dropout(self.embed_tokens(input_ids))
# [1, 1, 768]
```

此时选用的位置编码是：

```python
position_embeddings = (
    self.freqs_cos[3:4],
    self.freqs_sin[3:4]
)
```

这两个信息分别回答**两个问题**：

- `seq_length = 1`：这一轮**处理几个新 Token**？答：1 个。
- `start_pos = 3`：这个 Token 在完整上下文中**是第几个位置**？答：下标 3，也就是第 4 个。

<a id="origin-900"></a>
#### 3.3.3 Attention.forward() 的 `x` 确实只有长度 1

```python
bsz, seq_len, _ = x.shape
# x.shape = [1, 1, 768]，因此 seq_len = 1

xq, xk, xv = self.q_proj(x), self.k_proj(x), self.v_proj(x)

xq = xq.view(bsz, seq_len, self.n_local_heads, self.head_dim)
xk = xk.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
xv = xv.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)

xq, xk = self.q_norm(xq), self.k_norm(xk)
```

执行之后的形状：

```text
新 xq = [1, 1, 8, 96]
新 xk = [1, 1, 4, 96]
新 xv = [1, 1, 4, 96]
```

这是你特别关心的地方：**投影和归一化时只需要处理最新一个 Token 的 Q/K/V。**

<a id="origin-925"></a>
#### 3.3.4 然后才发生“把新 K/V 拼到旧 Cache 后面”

```python
if past_key_value is not None:
    xk = torch.cat([past_key_value[0], xk], dim=1)
    xv = torch.cat([past_key_value[1], xv], dim=1)

past_kv = (xk, xv) if use_cache else None
```

第一次的历史缓存是：

```text
旧 K = [k_我, k_爱, k_AI]      # 长度 3
旧 V = [v_我, v_爱, v_AI]      # 长度 3
```

本轮仅新计算：

```text
新 K = [k_技术]               # 长度 1
新 V = [v_技术]               # 长度 1
```

执行 `torch.cat(..., dim=1)`：

```text
完整 K = [k_我, k_爱, k_AI, k_技术]     # 长度 4
完整 V = [v_我, v_爱, v_AI, v_技术]     # 长度 4
```

对应的形状变化：

| 阶段 | `xq` | `xk` | `xv` |
|---|---|---|---|
| 刚投影、变形、处理 RoPE 后 | `[1,1,8,96]` | `[1,1,4,96]` | `[1,1,4,96]` |
| 与历史 Cache 拼接后 | `[1,1,8,96]` | `[1,4,4,96]` | `[1,4,4,96]` |
| GQA `repeat_kv` 并转置后 | `[1,8,1,96]` | `[1,8,4,96]` | `[1,8,4,96]` |

这里容易误会：**`xk` 和 `xv` 的长度“只有 1”说的是新计算时；同一个变量在 `torch.cat` 后被重新赋值，此时变成长度 4。**

反过来，`xq` 并没有与旧 Q 拼接，所以仍然只有 1 个 Query。

<a id="origin-968"></a>
#### 3.3.5 只有一个 Q，为什么依然能利用所有历史上下文？

拼接后，对某个 Attention Head 来说：

\[
Q_{\text{new}} \in \mathbb{R}^{1\times96},\qquad
K_{\text{all}} \in \mathbb{R}^{4\times96},\qquad
V_{\text{all}} \in \mathbb{R}^{4\times96}.
\]

所以：

\[
Q_{\text{new}}K_{\text{all}}^T:
(1\times96)(96\times4)=(1\times4).
\]

这 4 个分数分别代表当前 Token“技术”对“我 / 爱 / AI / 技术”的注意力分数：

\[
\begin{bmatrix}
s_{\text{技术,我}} &
s_{\text{技术,爱}} &
s_{\text{技术,AI}} &
s_{\text{技术,技术}}
\end{bmatrix}.
\]

随后：

\[
\operatorname{Attention}
=\operatorname{softmax}\!\left(\frac{Q_{\text{new}}K_{\text{all}}^T}{\sqrt{96}}\right)
V_{\text{all}}.
\]

**只新算一个 Query，不代表只看一个 Token；它仍然能访问 Cache 中的所有历史 K/V。**

这一轮算完后，模型再预测下一个 Token，假设是“很”，然后：

```text
input_ids  = [我, 爱, AI, 技术, 很]          # 长度 5
KV Cache   = [我, 爱, AI, 技术] 的 K/V       # 长度 4
```

---

<a id="origin-1015"></a>
### 3.4 第三次、第四次……为什么每次都只会新进来一个 Token？

第三次循环：

```python
past_len = 4
input_ids[:, past_len:] = [很]
# 新计算 Q/K/V 的长度仍是 1
```

接下来：

```text
旧缓存长度 = 4
本轮新 K/V 长度 = 1
拼接后的新缓存长度 = 5
```

如果本轮预测出“有趣”，输入序列就从 5 个 Token 变成 6 个，但缓存暂时仍只含前 5 个；下一轮再次截取第 6 个 Token。

把整个过程排成表：

| 循环轮次 | 调用前的 `input_ids` | 轮初旧 Cache 长度 | 实际送入模型 | 新 Q/K/V 长度 | 本轮返回的 Cache 长度 | 本轮预测的新 Token |
|---|---|---:|---|---:|---:|---|
| 第 1 次 Prefill | 我 爱 AI | 0 | 我 爱 AI | 3 | 3 | 技术 |
| 第 2 次 Decode | 我 爱 AI 技术 | 3 | 技术 | 1 | 4 | 很 |
| 第 3 次 Decode | 我 爱 AI 技术 很 | 4 | 很 | 1 | 5 | 有趣 |
| 第 4 次 Decode | 我 爱 AI 技术 很 有趣 | 5 | 有趣 | 1 | 6 | …… |

**归纳一下：**

- 第一次处理了整个 Prompt，返回的 Cache 覆盖整个 Prompt。
- 第一次刚预测出来的新 Token 只追加到了 `input_ids`，尚未写入 Cache。
- 下一次循环，`input_ids` 长度正好比 Cache 长度大 1，所以 `input_ids[:, past_len:]` 恰好截出 1 个 Token。
- 当前 Token 经各层 Attention 处理后，其 K/V 被接到旧 Cache 末尾，Cache 长度加 1。
- 预测出下一 Token，`input_ids` 再比 Cache 多 1，如此循环。

因此，这个“每次只处理一个 Token”的性质是 **`generate()` 的逐 Token 生成方式 + 按缓存长度截取输入 + 把新 K/V 保存并交给下一轮** 三者共同实现的。

特别注意：**缓存机制本身并不强制每次只有一个新 Token。**如果一次追加多个尚未处理的 Token（例如分块预填充），新 Q/K/V 的序列长度也可以大于 1。

---

<a id="origin-1058"></a>
### 3.5 同一行 `shape[1]`，为什么在两个地方有不同作用？

这两处取到的数值，在普通增量生成中通常相同，但**不是同一个操作**。

<a id="origin-1062"></a>
#### 3.5.1 第一处：`generate()` 决定“本轮输入什么”

```python
past_len = past_key_values[0][0].shape[1] if past_key_values else 0
outputs = self.forward(input_ids[:, past_len:], ...)
```

例如 `past_len = 3`，完整的 `input_ids` 长度为 4：

```text
[我, 爱, AI, 技术]
 └──已缓存──┘ └未处理┘

input_ids[:, 3:] = [技术]
```

这一行直接导致 `MiniMindModel.forward()` 的 `seq_length = 1`，继续导致每一层 `Attention.forward()` 的 `seq_len = 1`。

<a id="origin-1080"></a>
#### 3.5.2 第二处：`MiniMindModel.forward()` 决定“从哪个位置取 RoPE”

```python
start_pos = past_key_values[0][0].shape[1] if past_key_values[0] is not None else 0

position_embeddings = (
    self.freqs_cos[start_pos:start_pos + seq_length],
    self.freqs_sin[start_pos:start_pos + seq_length]
)
```

因为 `start_pos = 3, seq_length = 1`：

```text
本轮只有 [技术] 这个 Token
但它不是位置 0，而是完整序列中的位置 3

因此选用 RoPE[3:4]
```

**反证：**如果把 `start_pos` 硬改成 `0`，而 `generate()` 中的 `input_ids[:, past_len:]` 保持不变，那么**新 Q/K/V 的长度仍然是 1**；但会取错位置编码，影响模型输出。

反过来，如果保留正确的 `start_pos = 3`，却把 `generate()` 的输入改为整个 `input_ids`，那么**新 Q/K/V 就不会自动变成长度 1**，而且还可能重复拼接历史 K/V，导致上下文与位置错位。

---

<a id="origin-1106"></a>
### 3.6 如果推理时关闭 KV Cache，会发生什么？(重点)

同样的 `generate()` 代码：

```python
past_key_values = outputs.past_key_values if use_cache else None
```

如果 `use_cache=False`，每轮结束后 `past_key_values` 都仍为 `None`，于是下一轮：

```python
past_len = 0
input_ids[:, past_len:] = input_ids[:, 0:]
```

**每轮都会重新输入当前的整段序列**：

```text
第 1 次：[我, 爱, AI]                  → 长度 3
第 2 次：[我, 爱, AI, 技术]            → 长度 4
第 3 次：[我, 爱, AI, 技术, 很]         → 长度 5
第 4 次：[我, 爱, AI, 技术, 很, 有趣]   → 长度 6
```

这时，Attention 每轮新投影出来的 Q/K/V 长度自然是 `3、4、5、6……`，没有节省对过去 Token 的重复计算。

**所以“训练时 Q/K/V 很长”与“不使用 Cache 的生成时 Q/K/V 很长”，在张量长度上可能很像，但原因和计算目标不同：**

- **训练**：我们已经拥有整段真实文本，利用 Teacher Forcing 和因果掩码，**一次前向传播并行训练多个下一个 Token 预测任务**。
- **不开 Cache 的推理**：未来文本不知道，只能逐个生成；但每生成一个又把整个已生成序列送回模型，**重复计算大量历史 Token**。
- **开 Cache 的推理**：未来仍然只能逐个生成，但历史 K/V 已有缓存；只为最新 Token 计算各层的新 Q/K/V，并更新 Cache。

---

<a id="origin-1140"></a>
### 3.7 把 MiniMind 原始关键代码连成完整流程

下面按源码真实执行顺序，将最有用的代码串起来。省略不影响 KV Cache 理解的采样、Dropout 等细节。

<a id="origin-1144"></a>
#### 3.7.1 第 1 层：`MiniMindForCausalLM.generate()`——决定本轮处理哪些 Token

```python
# 初始化：无历史缓存
past_key_values = kwargs.pop("past_key_values", None)

for _ in range(max_new_tokens):
    # 已经处理过多少个 Token？
    past_len = past_key_values[0][0].shape[1] if past_key_values else 0

    # 只传入尚未处理的 Token（首次是整个 Prompt，之后一般是 1 个）
    outputs = self.forward(
        input_ids[:, past_len:],
        attention_mask,
        past_key_values,
        use_cache=use_cache,
        **kwargs
    )

    # 根据当前上下文最后一个位置预测新的 Token
    logits = outputs.logits[:, -1, :] / temperature
    # ...根据 logits 得到 next_token...

    # 拼到完整的 input_ids 后面：供下一轮送入模型
    input_ids = torch.cat([input_ids, next_token], dim=-1)

    # 保存本次 forward 返回的所有层 K/V，供下一轮使用
    past_key_values = outputs.past_key_values if use_cache else None
```

<a id="origin-1174"></a>
#### 3.7.2 第 2 层：`MiniMindModel.forward()`——决定本轮位置以及传入 Attention 的序列长度

```python
batch_size, seq_length = input_ids.shape
past_key_values = past_key_values or [None] * len(self.layers)

# 这是 RoPE 起始位置，不是截断 input_ids 的操作
start_pos = past_key_values[0][0].shape[1] if past_key_values[0] is not None else 0

hidden_states = self.dropout(self.embed_tokens(input_ids))

position_embeddings = (
    self.freqs_cos[start_pos:start_pos + seq_length],
    self.freqs_sin[start_pos:start_pos + seq_length]
)

presents = []
for layer, past_key_value in zip(self.layers, past_key_values):
    hidden_states, present = layer(
        hidden_states,
        position_embeddings,
        past_key_value=past_key_value,
        use_cache=use_cache,
        attention_mask=attention_mask
    )
    presents.append(present)

return hidden_states, presents, aux_loss
```

<a id="origin-1204"></a>
#### 3.7.3 第 3 层：`Attention.forward()`——只投影新 Token，然后追加到历史 K/V

```python
bsz, seq_len, _ = x.shape

# 此处 x 的 seq_len 已由上游决定；Decode 阶段通常是 1
xq, xk, xv = self.q_proj(x), self.k_proj(x), self.v_proj(x)

xq = xq.view(bsz, seq_len, self.n_local_heads, self.head_dim)
xk = xk.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)
xv = xv.view(bsz, seq_len, self.n_local_kv_heads, self.head_dim)

xq, xk = self.q_norm(xq), self.k_norm(xk)
cos, sin = position_embeddings
xq, xk = apply_rotary_pos_emb(xq, xk, cos, sin)

# 复用历史 KV；不重新投影历史 Token
if past_key_value is not None:
    xk = torch.cat([past_key_value[0], xk], dim=1)
    xv = torch.cat([past_key_value[1], xv], dim=1)

# 组成可返回的 Cache（每个 Transformer 层各自一份）
past_kv = (xk, xv) if use_cache else None

# GQA：复制 KV 头数，再转置用于注意力计算
xq, xk, xv = (
    xq.transpose(1, 2),
    repeat_kv(xk, self.n_rep).transpose(1, 2),
    repeat_kv(xv, self.n_rep).transpose(1, 2)
)

# 当前 Q 与“完整历史+当前”的 K、V 计算 Attention
# ... scores / softmax / output ...

return output, past_kv
```

---

<a id="origin-1243"></a>
## 4. PPO原理复习

<a id="origin-1245"></a>
### 4.1 先补上一步：原始目标是什么，为什么后来出现了 log？

<a id="origin-1247"></a>
#### 4.1.1 原始目标：让“平均能拿到的总奖励”最大

设 \(\theta\) 是 Policy 的参数，\(\tau=(s_0,a_0,\ldots,s_T)\) 是一条完整轨迹，\(R(\tau)\) 是这条轨迹的累计奖励。

最初要优化的是：

\[
\boxed{
\max_\theta J(\theta),\qquad
J(\theta)=\mathbb E_{\tau\sim P_\theta}[R(\tau)]
=\sum_\tau P_\theta(\tau)R(\tau)
}
\]

**思路其实和 SFT 的 Loss 类似：先定义一个要优化的标量目标，再根据它对参数的梯度来更新模型（SFT 最小化 Loss，这里最大化 \(J\)，也可以最小化 \(-J\)）；但这个目标涉及所有可能轨迹的期望及轨迹概率的连乘，难以直接算出并反向传播，单次采样得到的 Reward 也不能直接穿过离散采样求导，所以我们要换一种方式计算同一目标的梯度。**

**一条轨迹出现的概率 × 这条轨迹的总奖励，再对所有可能轨迹求和，就是平均总奖励。** 不是只让某一次碰巧得到的分数变高。

**用大语言模型举例：直接按求和公式精确计算，需要把所有可能回答列出来。**

假设 Prompt 是“这个苹果怎么样？”，为了把例子缩小，模型只生成两个 Token：第一个只能选“很”或“不”，第二个只能选“甜”或“酸”。因此有四条完整回答轨迹。再假设当前策略下四条轨迹的概率都为 0.25，RM 给出的分数如下：

| 完整回答（轨迹） | 当前轨迹概率 | Reward |
|---|---:|---:|
| 很甜 | 0.25 | 4 |
| 很酸 | 0.25 | 2 |
| 不甜 | 0.25 | 1 |
| 不酸 | 0.25 | 3 |

如果直接按 \(J=\sum_\tau P_\theta(\tau)R(\tau)\) 的显式求和方式精确计算，就要把这四种情况全部计入：

\[
J=0.25\times4+0.25\times2+0.25\times1+0.25\times3=2.5
\]

同样，直接展开它的梯度，需要对所有轨迹的贡献求和：

\[
\nabla_\theta J
=\sum_\tau R(\tau)\nabla_\theta P_\theta(\tau)
\]

只有两个 Token、每步两个选项，已经有 \(2^2=4\) 条轨迹；**如果生成 100 个 Token，即使每步仍只有两个选项，也有 \(2^{100}\) 条可能轨迹**。真实大模型每步还有大量候选 Token，**直接逐条枚举全部回答、计算概率、评分并汇总梯度，在实际训练中不可行。**

**为什么直接求和时，少一条轨迹就不能得到完整梯度？** 回到上面的四种回答，原目标的梯度包含四项：

\[
\begin{aligned}
\nabla_\theta J
={}&4\nabla_\theta P_\theta(\text{很甜})
+2\nabla_\theta P_\theta(\text{很酸})\\
&+\nabla_\theta P_\theta(\text{不甜})
+\underbrace{3\nabla_\theta P_\theta(\text{不酸})}_{\text{漏掉“不酸”，就缺少这一项}}
\end{aligned}
\]

如果没有计入“不酸”，就漏掉了它的奖励 3 乘以轨迹概率的梯度。表中的 0.25 只是当前参数下的概率数值，概率本身会随 \(\theta\) 改变，因此这项贡献一般不为 0。**剩下三项仍然可以求导，但得到的只是三条轨迹的贡献之和，不是原目标完整、准确的梯度；这里的“不能求”准确地说是“不能靠漏掉一项的直接求和，得到完整梯度”。** 后面的 Policy Gradient 则用随机采样的贡献平均来估计完整期望，采用的是采样估计，而不是把未采到的项当成 0。

为方便推导，下面先取 \(\gamma=1\)，即不加折扣；假设环境和奖励规则不直接依赖 Policy 参数 \(\theta\)。

<a id="origin-1307"></a>
#### 4.1.2 为什么会出现连乘，直接求导又麻烦在哪里？

一条轨迹要依次选出多个动作。因此，它的概率包含每一步动作概率的连乘：

\[
P_\theta(\tau)
=\underbrace{\rho_0(s_0)\prod_{t=0}^{T-1}
P(s_{t+1}\mid s_t,a_t)}_{C(\tau)：初始状态与环境转移概率}
\prod_{t=0}^{T-1}\pi_\theta(a_t\mid s_t)
\]

这里的 \(C(\tau)\) 对固定轨迹而言不依赖 \(\theta\)。在大模型里，动作是 Token，状态是“Prompt + 已生成的 Token”；整段回答的概率也要把各 Token 的条件概率连乘。

先只看三步，记 \(p_t=\pi_\theta(a_t\mid s_t)\)：

\[
\nabla_\theta(p_0p_1p_2)
=(\nabla_\theta p_0)p_1p_2
+p_0(\nabla_\theta p_1)p_2
+p_0p_1(\nabla_\theta p_2)
\]

**每求一项，都要保留其余概率的乘积；步数越多，乘积求导的表达就越长。** 而且，**小概率连乘可能变得非常小**，例如 \(0.1^{1000}=10^{-1000}\)，直接计算可能**下溢**。

即有三个问题：

**1. 原始公式要求枚举所有可能轨迹，在大模型里不可行。**

**2. 直接求导的表达式很长，难以逐步计算，乘法运算量大。**

**3. 小概率连乘可能导致数值下溢，难以通过采样估计期望。**

这不是说连乘“不能求导”，而是我们希望得到一个**更容易逐步计算、也更容易通过采样估计期望**的形式。

<a id="origin-1341"></a>
#### 4.1.3 用 log 把连乘变成求和，得到策略梯度

先用一个求导恒等式：

\[
\nabla_\theta\log P_\theta(\tau)
=\frac{\nabla_\theta P_\theta(\tau)}{P_\theta(\tau)}
\quad\Longrightarrow\quad
\boxed{
\nabla_\theta P_\theta(\tau)
=P_\theta(\tau)\nabla_\theta\log P_\theta(\tau)
}
\]

再利用 \(\log(ab)=\log a+\log b\)：

\[
\log P_\theta(\tau)
=\log C(\tau)+\sum_{t=0}^{T-1}\log\pi_\theta(a_t\mid s_t)
\]

环境项的梯度为 0，于是：

\[
\boxed{
\nabla_\theta\log P_\theta(\tau)
=\sum_{t=0}^{T-1}\nabla_\theta\log\pi_\theta(a_t\mid s_t)
}
\]

代回原始目标的梯度：

\[
\begin{aligned}
\nabla_\theta J(\theta)
&=\sum_\tau R(\tau)\nabla_\theta P_\theta(\tau)\\
&=\sum_\tau P_\theta(\tau)R(\tau)
  \nabla_\theta\log P_\theta(\tau)\\
&=\boxed{
\mathbb E_{\tau\sim P_\theta}
\left[
R(\tau)\sum_{t=0}^{T-1}
\nabla_\theta\log\pi_\theta(a_t\mid s_t)
\right]
}
\end{aligned}
\]

**现在不必枚举所有轨迹：用当前 Policy 采样若干条轨迹，把“总奖励 × 各步 log 概率的梯度之和”取平均，就能估计这个梯度。** 实现时可直接计算 log 概率，不必先算极小的整段概率再取 log。

**回到刚才的苹果例子：Policy Gradient 可以只采样实际生成的回答。**

比如当前 Policy 这次 Rollout 采到了三条：

```text
第 1 条：很甜 → Reward = 4
第 2 条：不酸 → Reward = 3
第 3 条：很甜 → Reward = 4
```

对采到的一条回答，计算它的梯度贡献：

\[
g(\tau)=R(\tau)\sum_t\nabla_\theta\log\pi_\theta(a_t\mid s_t)
\]

再对这三条的贡献取平均：

\[
\boxed{
\hat g=\frac{g(\text{很甜})+g(\text{不酸})+g(\text{很甜})}{3}
}
\]

**这批样本中没有生成“很酸”和“不甜”，也可以估计策略梯度；不必为了补齐所有情况，再把这两个回答也枚举出来。** 哪些回答更常出现，由当前策略的采样概率决定，因此对采样贡献取平均就能估计公式中的期望，不需要在每条贡献上再乘一次轨迹概率。

推广到 \(N\) 条独立采样的轨迹：

\[
\boxed{
\nabla_\theta J
\approx\frac{1}{N}\sum_{i=1}^{N}
R(\tau_i)\sum_t\nabla_\theta\log\pi_\theta(a_t^{(i)}\mid s_t^{(i)}),
\qquad \tau_i\sim P_\theta
}
\]

**这也是 Policy Gradient 的优势之一：把目标的梯度改写成可以通过 Rollout 采样平均来估计的形式，避免显式遍历全部轨迹。** 原始目标本来也是期望；这里的关键是得到“可用采样估计的梯度”，而不是把一个求和目标换成另一个目标。

有限样本的平均仍是估计，不保证这三条样本就给出准确梯度；第 9–11 节再讨论它的梯度波动，以及 Advantage 如何降低这种波动。

进一步利用“当前动作不会改变过去已经拿到的奖励”，在期望中可以把各步的整段奖励权重换成从该步开始的回报 \(G_t\)，得到 REINFORCE 的常用形式：

\[
\boxed{
\nabla_\theta J(\theta)
=\mathbb E_{\tau\sim P_\theta}
\left[
\sum_{t=0}^{T-1}
G_t\nabla_\theta\log\pi_\theta(a_t\mid s_t)
\right],
\qquad
G_t=\sum_{k=t}^{T-1}r_k
}
\]

> **注意：我们没有把原始目标 \(J\) 改成 \(\log J\)，也没有对 Reward 取 log；只是利用恒等式，把同一个目标的梯度改写成了 log 概率的形式。** 后面再根据这个梯度构造便于 `backward()` 的 Loss，见[为什么 Policy Gradient 最后变成了 Loss？](../../%E8%AE%B2%E4%B9%89/PPO%20%E9%87%87%E6%A0%B7%E4%B8%8E%E8%AE%AD%E7%BB%83/b19-PPO%20%E9%87%8D%E7%82%B9%E5%A4%8D%E4%B9%A0.md#origin-1869)。

推导参考：[Spinning Up：策略梯度推导](https://spinningup.openai.com/en/latest/spinningup/rl_intro3.html#deriving-the-simplest-policy-gradient)。

---

REINFORCE 一次采样中，第 \(t\) 步的梯度贡献可写成（完整梯度还需要对时间求和、对轨迹取期望）：

\[
\hat g_t=\nabla_\theta
\log\pi_\theta(a_t|s_t)
G_t
\]

可以拆成：

<a id="origin-1463"></a>
### 4.2 第一部分

\[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\]

表示：

> 参数应该怎么改，才能改变这个 Action 的概率。

<a id="origin-1474"></a>
### 4.3 第二部分

\[
G_t
\]

表示：

> 这个 Action 后面得到的结果好不好。

所以：

```text
G 大：
往提高这个 Action 概率的方向走

G 小 / 负：
往降低这个 Action 概率的方向走
```

---

<a id="origin-1496"></a>
## 5. Policy Gradient 为什么可以只采样部分轨迹？（课外）

> **本讲义只解决一个核心问题：** 原始目标函数求导后，是对所有轨迹贡献进行求和；为什么经过 Policy Gradient 的推导，梯度就可以通过少量采样轨迹的平均值来估计？这个变化与“期望”和“大数定律”究竟是什么关系？

<a id="origin-1500"></a>
### 5.1 先说最重要的结论

**原始公式和 Policy Gradient 公式在理论上求的是同一个梯度。**

区别不在于前者“数学上绝对不能采样”，后者“数学上天然不需要所有轨迹”；区别在于：

1. **原始梯度直接写成普通求和：** 要直接、精确地把这个求和算出来，就需要计算所有轨迹对应的求和项（或另找解析算法）。不能直接按轨迹概率采样，然后把原求和项拿来平均。
2. **Policy Gradient 将相同的梯度重新写成期望：** 可以按照期望中的概率分布采样，让每条采样轨迹提供一个**正确加权的梯度贡献**。
3. **根据大数定律：** 这些梯度贡献的样本平均会随着采样次数增加，趋向真正的梯度。因此，训练时只采样一小部分轨迹，也能做一次**近似的梯度更新**。

**注意：如果要求完全精确地计算 Policy Gradient 中的期望，通常仍然要考虑所有可能轨迹。实际训练“不枚举”，是因为使用了采样近似，而不是因为写上了期望符号就自动变成精确计算。**

---

<a id="origin-1514"></a>
### 5.2 第一步：从原始目标开始，直接求导

假设一条完整轨迹是 $\tau$；在参数为 $\theta$ 的策略下，这条轨迹发生的概率是 $P_\theta(\tau)$；其奖励是 $R(\tau)$。

目标是最大化**所有可能轨迹上的期望奖励**：

$$
\boxed{
J(\theta)=\mathbb E_{\tau\sim P_\theta}[R(\tau)]
=\sum_{\tau}P_\theta(\tau)R(\tau)
}
\tag{1}
$$

假设奖励本身不直接依赖参数 $\theta$。对式 (1) 求导：

$$
\boxed{
\nabla_\theta J(\theta)
=\sum_{\tau}R(\tau)\nabla_\theta P_\theta(\tau)
}
\tag{2}
$$

**这是第一个关键位置。**

- 右侧是对所有轨迹的**普通求和**。
- 若采用“把右边各项逐个算出来，再相加”的办法，要得到**精确值**，就得处理所有轨迹。
- 对大模型来说，生成 $T$ 个 token、每步词表大小约为 $V$，候选输出数量最多可达到 $V^T$ 的量级，无法这样枚举。

但请不要误解成“式 (2) 永远不能靠采样估计”。下一步就是要把它变成**适合按 $P_\theta$ 采样的形式**。

---

<a id="origin-1548"></a>
### 5.3 第二步：为什么不能直接随机取几项然后平均？

**先记住期望的定义：**

$$
\boxed{\mathbb E_{\tau\sim P_\theta}[f(\tau)]
=\sum_{\tau}P_\theta(\tau)f(\tau)}
\tag{3}
$$

当你按照 $P_\theta$ 抽取很多条轨迹并计算 $f(\tau)$ 的平均值时，**高概率轨迹会出现得更频繁**，所以采样平均天然就在估计右侧这种“带 $P_\theta(\tau)$ 权重的求和”。

可是式 (2) 是：

$$
\sum_\tau \underbrace{R(\tau)\nabla_\theta P_\theta(\tau)}_{\text{每条轨迹的原始求和项}}
$$

**它的每一项前面没有额外的 $P_\theta(\tau)$。**

如果错误地按 $P_\theta$ 抽样，然后直接把这些原始求和项做平均，得到的将是：

$$
\underbrace{\mathbb E_{\tau\sim P_\theta}
[R(\tau)\nabla_\theta P_\theta(\tau)]}_{\text{错误的目标}}
=\sum_\tau P_\theta(\tau)R(\tau)\nabla_\theta P_\theta(\tau)
$$

这与式 (2) **不是同一个东西**，因为你通过采样频率额外乘了一次概率。

<a id="origin-1578"></a>
#### 5.3.1 用两个动作验证这个错误

假设：

| 动作（视为一条轨迹） | 概率 | 奖励 |
|---|---|---|
| A | $P_\theta(A)=\theta$ | $5$ |
| B | $P_\theta(B)=1-\theta$ | $1$ |

原始目标：

$$
J(\theta)=5\theta+1(1-\theta)=4\theta+1
$$

**直接精确求导：**

$$
\boxed{J'(\theta)=5\times 1+1\times(-1)=4}
$$

现在令 $\theta=0.8$。A 以 $0.8$ 的概率出现，B 以 $0.2$ 的概率出现。

如果错误地对原始求和项 $5$ 和 $-1$ 按当前策略采样后取平均，采样平均的理论期望是：

$$
0.8\times5+0.2\times(-1)=3.8\ne4
$$

**错在哪里？原本是 $5+(-1)$；随机采样平均却变成了 $0.8\times5+0.2\times(-1)$。**

---

<a id="origin-1611"></a>
### 5.4 第三步：怎样把“普通求和”变成“可采样的期望”？

我们希望把原始梯度：

$$
\sum_\tau R(\tau)\nabla_\theta P_\theta(\tau)
$$

改写为式 (3) 的结构：

$$
\sum_\tau P_\theta(\tau)\,f(\tau)
$$

办法非常简单：**把概率乘进去，再除出来，整个公式没有变。** 对具有正概率的轨迹：

$$
\begin{aligned}
\nabla_\theta J
&=\sum_\tau R(\tau)\nabla_\theta P_\theta(\tau)\\[4pt]
&=\sum_\tau
\underbrace{P_\theta(\tau)}_{\text{由采样频率体现}}
\underbrace{\left[
R(\tau)\frac{\nabla_\theta P_\theta(\tau)}{P_\theta(\tau)}
\right]}_{\text{每次采样应计算的值}}\\[4pt]
&=\boxed{\mathbb E_{\tau\sim P_\theta}\left[
R(\tau)\frac{\nabla_\theta P_\theta(\tau)}{P_\theta(\tau)}
\right]}
\end{aligned}
\tag{4}
$$

**这是整段推导最关键的一步。**

- 原来：需要直接累加全部轨迹的 $R(\tau)\nabla P_\theta(\tau)$，才能获得精确和。
- 现在：只要按照 $P_\theta$ 抽取轨迹，计算 $R(\tau)\nabla P_\theta(\tau)/P_\theta(\tau)$，再求样本平均，就能**估计这个精确和**。
- 除以 $P_\theta(\tau)$ 正好补偿采样时高概率轨迹被多抽到的效果。

**到式 (4) 为止，甚至还没有用到 Log！** 重要的是先把“求和”变成适合采样的“期望”。

---

<a id="origin-1653"></a>
### 5.5 第四步：期望为什么允许只计算一些样本？——大数定律

对于任意随机变量 $X$，如果 $X_1,\dots,X_N$ 是从同一个分布独立采集的样本，并满足适当条件（如有限期望），则大数定律表明：

$$
\boxed{
\frac1N\sum_{i=1}^{N}X_i
\xrightarrow[N\to\infty]{}
\mathbb E[X]
}
\tag{5}
$$

在当前固定的参数 $\theta$ 下，我们定义每条轨迹的**梯度贡献**：

$$
G(\tau)=R(\tau)\frac{\nabla_\theta P_\theta(\tau)}{P_\theta(\tau)}
$$

式 (4) 就变成：

$$
\nabla_\theta J=\mathbb E_{\tau\sim P_\theta}[G(\tau)]
$$

按照 $P_\theta$ 独立采样 $N$ 条轨迹：$\tau_1,\dots,\tau_N$，即可得到：

$$
\boxed{
\widehat{\nabla_\theta J}
=\frac1N\sum_{i=1}^{N}
R(\tau_i)\frac{\nabla_\theta P_\theta(\tau_i)}{P_\theta(\tau_i)}
}
\tag{6}
$$

式 (6) 的平均值就是我们用于更新模型的**梯度估计**，而不是必须算完所有轨迹才开始更新。

**这里必须区分两个概念：**

- **精确梯度**：式 (2) 或式 (4) 的真实值。精确完整求和通常仍需所有轨迹。
- **估计梯度**：式 (6) 只用了 $N$ 条采样轨迹。有限样本时可能有误差，但在通常条件下是无偏估计，并随着样本增多而收敛。

<a id="origin-1696"></a>
#### 5.5.1 数值验证：同样得到真实梯度 4

继续使用 $P(A)=0.8$、$P(B)=0.2$ 的例子。

每次采样需要计算的值变成：

$$
G(A)=5\times\frac{1}{0.8}=6.25
$$

$$
G(B)=1\times\frac{-1}{0.2}=-5
$$

它们按照采样概率加权后的期望：

$$
\boxed{\mathbb E[G]=0.8\times6.25+0.2\times(-5)=4}
$$

如果采样 10 次，刚好有 8 次 A 和 2 次 B，则：

$$
\hat g=\frac{8\times6.25+2\times(-5)}{10}=4
$$

如果采样 10 次，得到 7 次 A 和 3 次 B，则：

$$
\hat g=\frac{7\times6.25+3\times(-5)}{10}=2.875
$$

**所以“少量采样”并不表示每次都算得精确，而是能提供有意义的梯度估计。**

---

<a id="origin-1732"></a>
### 5.6 第五步：Log 技巧只是把采样贡献写得更容易计算

利用对数求导恒等式：

$$
\boxed{
\frac{\nabla_\theta P_\theta(\tau)}{P_\theta(\tau)}
=\nabla_\theta\log P_\theta(\tau)
}
$$

式 (4) 化为：

$$
\boxed{
\nabla_\theta J
=\mathbb E_{\tau\sim P_\theta}
\left[R(\tau)\nabla_\theta\log P_\theta(\tau)\right]
}
\tag{7}
$$

如果一条轨迹的概率是每一步策略概率与环境概率的连乘：

$$
P_\theta(\tau)
=\rho(s_0)\prod_{t=0}^{T-1}
\pi_\theta(a_t\mid s_t)\,p(s_{t+1}\mid s_t,a_t)
$$

在初始状态分布和环境转移概率不依赖 $\theta$ 时：

$$
\nabla_\theta\log P_\theta(\tau)
=\sum_{t=0}^{T-1}\nabla_\theta\log\pi_\theta(a_t\mid s_t)
$$

于是得到常见的 Policy Gradient：

$$
\boxed{
\nabla_\theta J(\theta)
=\mathbb E_{\tau\sim P_\theta}\left[
R(\tau)\sum_{t=0}^{T-1}\nabla_\theta\log\pi_\theta(a_t\mid s_t)
\right]
}
\tag{8}
$$

训练时采样 $N$ 条轨迹：

$$
\boxed{
\widehat{\nabla_\theta J}
=\frac1N\sum_{i=1}^{N}
\left[
R(\tau_i)\sum_{t=0}^{T-1}
\nabla_\theta\log\pi_\theta(a_{i,t}\mid s_{i,t})
\right]
}
\tag{9}
$$

**这里体现了两个不同的数学思想：**

- **Log 导数技巧**：将 $\nabla P/P$ 写成 $\nabla\log P$，把一条轨迹概率的连乘转成每一步 Log 概率的求和。
- **大数定律**：把“梯度的期望”转成“若干条采样轨迹的梯度贡献的平均”，从而不用做完整的精确求和。

---

<a id="origin-1802"></a>
### 5.7 原始目标也是期望，为什么不能直接采样 Reward 后反向传播？

原始目标也可以采样估计**数值**：

$$
J(\theta)=\mathbb E_{\tau\sim P_\theta}[R(\tau)]
\quad\Longrightarrow\quad
\widehat J=\frac1N\sum_{i=1}^N R(\tau_i)
$$

但是，如果轨迹是离散采样得到的，采样完之后 $R(\tau_i)$ 往往只是固定的奖励数值。对这个固定数值直接反向传播，**无法计入策略参数改变了轨迹出现概率**这个事实。

这解释了：

- $\frac1N\sum_iR(\tau_i)$：估计的是**期望奖励的大小**。
- $\frac1N\sum_iR(\tau_i)\nabla_\theta\log P_\theta(\tau_i)$：估计的是**期望奖励对模型参数的梯度**。

**不是前者不能采样，而是前者的采样平均不能直接当作正确的策略梯度。**

---

<a id="origin-1823"></a>
### 5.8 SFT 为什么也可以用 Mini-batch？

SFT 的固定训练集损失常写成：

$$
L(\theta)=\frac1M\sum_{i=1}^M L_i(\theta)
$$

求导后：

$$
\nabla_\theta L
=\frac1M\sum_{i=1}^M\nabla_\theta L_i(\theta)
=\mathbb E_{i\sim\operatorname{Uniform}(1,M)}[\nabla_\theta L_i(\theta)]
$$

因此，SFT 也可以只随机抽取一个 Mini-batch 来估计梯度。

**区别：** SFT 的数据采样通常不依赖当前模型参数，且单条数据的 Loss 本身可微；强化学习中轨迹分布 $P_\theta$ 随模型参数变化，因此需要通过 Policy Gradient 的推导，把这种概率变化纳入梯度估计。

---

<a id="origin-1845"></a>
### 5.9 一张表总结：原始梯度 vs Policy Gradient

| 关注点 | 原始梯度的直接求和 | Policy Gradient 的期望形式 |
|---|---|---|
| 数学表达式 | $\sum_\tau R(\tau)\nabla P_\theta(\tau)$ | $\mathbb E_{\tau\sim P_\theta}[R(\tau)\nabla\log P_\theta(\tau)]$ |
| 两者的精确值是否相同 | 是 | 是 |
| **直接精确计算**是否通常要考虑所有轨迹 | 是 | 是，期望展开仍是对所有轨迹求和 |
| **能否通过采样做近似估计** | 不能把原始求和项直接按 $P_\theta$ 采样平均；需调整权重 | 可以：按 $P_\theta$ 抽样，对括号中的梯度贡献取平均 |
| 为什么能不枚举做训练 | 需要先进行正确的采样估计变换 | 大数定律保证样本平均可估计期望 |
| Log 的核心作用 | 尚未使用 | 便于计算概率导数，并将连乘改为求和 |

<a id="origin-1856"></a>
### 5.10 必须记住的三句话

1. **原始梯度若直接计算完整求和，需要把所有轨迹的贡献累加起来；这说的是“精确枚举”的计算方法。**
2. **经过变换，梯度本身变成了 $\mathbb E_{\tau\sim P_\theta}[R(\tau)\nabla_\theta\log P_\theta(\tau)]$。** 每条按策略采样的轨迹都能产生一个正确加权的梯度贡献。
3. **根据大数定律，只采样少量轨迹并平均这些贡献，就能够近似原始梯度，进而更新模型。** 采样计算的是估计值，不是“只算一部分却得到必然精确的完整求和”。

> **最精炼的逻辑链：** 原始梯度的完整求和 → 乘除 $P_\theta$，改写为按策略采样的期望 → Log 导数技巧让每条样本的贡献容易计算 → 大数定律允许用样本平均来近似梯度 → 不用枚举全部轨迹也可以训练。

**说明：** 严格来说，上述推导是 Policy Gradient（REINFORCE）的基础。PPO 在此基础上还使用 Advantage、重要性采样比率和 Clip 等机制；PPO 实际优化的代理目标不一定处处与原始期望奖励目标具有完全相同的梯度。


---

<a id="origin-1869"></a>
## 6. 为什么 Policy Gradient 最后变成了 Loss？

**核心理解：我们最初想优化的是期望 Reward，经过求导和一系列推导后，又根据得到的梯度，反过来构造了一个方便 PyTorch 训练的新 Loss。**

<a id="origin-1873"></a>
### 6.1 最初的目标函数

\[
J(\theta)=\sum_\tau P_\theta(\tau)R(\tau)
\]

我们希望调整 Policy Model 的参数，使期望 Reward 最大。

<a id="origin-1881"></a>
### 6.2 经过一系列求导和推导

得到 Policy Gradient：

\[
\boxed{
\nabla_\theta J
=
\mathbb E
\left[
\nabla_\theta\log\pi_\theta(a_t|s_t)A_t
\right]
}
\]

这个公式告诉我们：**参数应该按照什么梯度方向更新。**

<a id="origin-1898"></a>
### 6.3 根据梯度反过来构造 Loss

因为 PyTorch 需要一个 Loss，再通过 `loss.backward()` 自动求梯度，所以我们构造：

\[
\boxed{
L(\theta)
=
-\mathbb E
\left[
\log\pi_\theta(a_t|s_t)A_t
\right]
}
\]

**注意，这个loss和最初的损失函数不一样**。

这里把采样数据和 Advantage 当成常量。

对这个 Loss 求导：

\[
\boxed{
\nabla_\theta L
=
-\mathbb E
\left[
\nabla_\theta\log\pi_\theta(a_t|s_t)A_t
\right]
}
\]

因此，在采样策略对应的参数处，新 Loss 的期望梯度与原始目标函数的梯度方向相反：

\[
\boxed{
\nabla_\theta L=-\nabla_\theta J
}
\]

这意味着：

- 最大化原始目标函数 \(J\)。
- 最小化新构造的 Loss \(L\)。

**在该采样策略对应的参数处，两者具有相同的期望参数更新方向。**

<a id="origin-1945"></a>
### 6.4 最终总结

**最初我们希望最大化：**

\[
J(\theta)=\sum_\tau P_\theta(\tau)R(\tau)
\]

经过推导得到了 Policy Gradient，然后根据这个梯度，反过来构造了新的 Loss。

**注意：**

**- 两个目标函数本身不恒等。**
**- 新 Loss 是根据原始目标函数的梯度构造出来的。**
**- 在上述条件下，两者的期望梯度方向等价（考虑最大化与最小化的负号）。**
**- 所以我们可以利用新 Loss 来训练 Policy Model。**

这种新构造的 Loss 就叫作 **Surrogate Loss（代理损失函数）**。Surrogate Loss 不一定在数值或形式上直接体现“Reward 越高越好”，它主要通过梯度来实现这个训练目标。

**总结：Surrogate Loss的目的不是准确表达原始目标函数的数值，而是提供正确的梯度来更新参数。**

---



<a id="origin-1970"></a>
## 7. 为什么不直接用 Reward / Return，而要 Advantage

假设状态 A：

```text
平均只能拿 1 分
```

某次拿：

```text
5 分
```

其实非常优秀。

另一个状态 B：

```text
平均能拿 100 分
```

某次也拿：

```text
5 分
```

其实非常差。

所以我们真正需要的是：

> 相比当前状态的平均水平，这个 Action 好多少。

也就是：

\[
A=Q-V
\]

**注意\(Q\)是\(G_t\)的期望，于是 Policy Gradient 更常写成（改进成）：**

\[
\boxed{
\nabla_\theta J
=
\mathbb E
[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
A_t
]
}
\]

**即把\(G_t\)替换成\(A_t\)。**

<a id="origin-2027"></a>
## 8. Reward 为什么可以用绝对分数？Policy Gradient 在期望中会反映相对差距


<a id="origin-2030"></a>
### 8.1 先固定例子：问题 A 是 5 / 1 分，问题 B 是 100 / 99 分

Reward Model（RM）使用同一个 Prompt 下的偏好对训练，常见损失为：

\[
L_{\mathrm{RM}}=-\log\sigma\left(R_{\mathrm{chosen}}-R_{\mathrm{rejected}}\right)
\]

| Prompt | 好回答的分数 | 差回答的分数 | 好回答领先多少 |
|---|---:|---:|---:|
| 问题 A | 5 | 1 | 4 |
| 问题 B | 100 | 99 | 1 |

这里“好 / 差”是**同一个 Prompt 内的相对比较**。问题 B 的好回答有 100 分，不代表它比问题 A 的好回答好 20 倍。

例如把问题 B 的分数整体减去 99，变成 1 / 0，RM 的这项损失不变：

\[
100-99=1-0=1
\]

**Pairwise Loss 约束分数差，却不确定这组分数的公共零点。** 因而真正做 Rollout 时，RM 给一个回答输出 100 分，我们需要解释：这个很大的公共基准，会不会让 Policy 错把它当成很强的学习信号？

<a id="origin-2053"></a>
### 8.2 先不用 Advantage，直接看看原始 Policy Gradient

先把“生成一整条回答”简化为一次动作，回答完成后得到 Reward，因此本节有 \(G=R\)。暂时不考虑 KL 和折扣。

对每个 Prompt，假设当前策略选择好、差回答的概率都是 0.5。分别用一个二选一参数 \(\theta\) 表示这个选择：

\[
\pi_\theta(\mathrm{好}\mid s)=\sigma(\theta),\qquad
\pi_\theta(\mathrm{差}\mid s)=1-\sigma(\theta)
\]

当 \(\theta=0\) 时，两种回答等概率，且：

\[
\frac{\partial\log\pi_\theta(\mathrm{好}\mid s)}{\partial\theta}=+0.5,
\qquad
\frac{\partial\log\pi_\theta(\mathrm{差}\mid s)}{\partial\theta}=-0.5
\]

原始策略梯度的单次采样贡献为：

\[
\boxed{g=G\frac{\partial\log\pi_\theta(a\mid s)}{\partial\theta}}
\]

<a id="origin-2078"></a>
### 8.3 本节重点是“梯度变化是否稳定”

**比较采到不同回答时，上式中的最终梯度 \(g\) 会怎样变化。Reward 或 \(G\) 是梯度的权重，最终用于更新参数的是两项相乘后的 \(g\)。**

下面的 \(g\) 都表示**最大化期望 Reward 的梯度方向**。\(g>0\) 会提高好回答的概率，\(g<0\) 会降低好回答的概率；用梯度下降时，可最小化 \(L=-G\log\pi_\theta(a\mid s)\)，得到相同的更新方向。

| Prompt | 只采到好回答时的 \(g\) | 只采到差回答时的 \(g\) |
|---|---:|---:|
| 问题 A：5 / 1 | \(5\times0.5=+2.5\) | \(1\times(-0.5)=-0.5\) |
| 问题 B：100 / 99 | \(100\times0.5=+50\) | \(99\times(-0.5)=-49.5\) |

**只看一次采样，绝对数值确实影响很大：问题 B 只领先 1 分，单次梯度却可能达到 +50。** 但 Policy Gradient 的公式里还有一个关键操作：**求期望。**

<a id="origin-2091"></a>
### 8.4 样本充足时，正负贡献会反映出真正的奖励差距

**如果好坏两种情况的轨迹都采样到了，则：**

问题 A 的期望梯度为：

\[
\begin{aligned}
\mathbb E[g_A]
&=0.5\times(+2.5)+0.5\times(-0.5)\\
&=\boxed{1}
\end{aligned}
\]

问题 B 的期望梯度为：

\[
\begin{aligned}
\mathbb E[g_B]
&=0.5\times(+50)+0.5\times(-49.5)\\
&=25-24.75\\
&=\boxed{0.25}
\end{aligned}
\]

为什么 100 分没有变成一个特别大的最终梯度？因为差回答也有 99 分，**公共基准产生的正负贡献在期望中抵消，留下的是好、差回答之间的差距。**

对这个二选一模型，令好回答概率为 \(p=\sigma(\theta)\)，可以直接写出：

\[
J(\theta)=pR_{\mathrm{好}}+(1-p)R_{\mathrm{差}}
\]

因此：

\[
\boxed{
\frac{\partial J}{\partial\theta}
=p(1-p)\left(R_{\mathrm{好}}-R_{\mathrm{差}}\right)
}
\]

当 \(p=0.5\) 时，梯度就是 \(0.25\times\text{奖励差距}\)：问题 A 的差距为 4，梯度为 1；问题 B 的差距为 1，梯度为 0.25。

**所以，Policy Gradient 即使直接使用绝对 Reward，在准确的期望中也能衡量同一状态下动作的相对差距。** 用固定策略独立采样足够多次，样本平均可以逐渐逼近这个期望。

<a id="origin-2137"></a>
### 8.5 把 100 / 99 改成 1 / 0，期望梯度仍然是 0.25

问题 B 的两种分数同时减去 99 后：

\[
\begin{aligned}
\mathbb E[g'_B]
&=0.5\times1\times(+0.5)
+0.5\times0\times(-0.5)\\
&=\boxed{0.25}
\end{aligned}
\]

**结论：单次梯度贡献可能从 50 变为 0.5，但完整期望的梯度仍是 0.25。**

这里的 0.25 是把好、差两种情况都按各自概率计入后的结果。它不要求每次采样都同时“踩到”两个回答；但如果只有很少样本，正负贡献可能来不及充分抵消。

对于这个“完整回答作为一次动作”的例子，同一个 Prompt 的所有回答统一加减常数，只改变公共基准，不改变准确求期望后的优化方向。**这解释了为什么 RM 的分数没有统一零点，也仍然可以作为训练信号。**

<a id="origin-2156"></a>
### 8.6 样本不充足时，原始 \(G\) 加权的估计可能离期望很远

还是问题 B。**只采一次时，估计可能是 +50，也可能是 −49.5，真实期望却只有 +0.25。**

**采 10 次也不一定足够**。假设这次采到 6 个好回答、4 个差回答，平均梯度为：

\[
\hat g_B=\frac{6\times50+4\times(-49.5)}{10}=\boxed{10.2}
\]

如果采到 4 个好回答、6 个差回答，则：

\[
\hat g_B=\frac{4\times50+6\times(-49.5)}{10}=\boxed{-9.7}
\]

两个批次都只比“5 个好、5 个差”多偏了一个回答，估计却大幅偏离 +0.25，甚至反向。

**这里不稳定的是最终用于更新参数的采样梯度：只采一条时可能是 +50 或 −49.5，两个小批次的平均梯度也可能是 +10.2 或 −9.7，而正确期望只有 +0.25。梯度变化很大，才是本节要说明的训练问题；估计器在理论上仍然无偏，但有限样本的梯度方差很大。**

下一节要解决的是：能否保留正确的期望梯度，同时减少对大量正负贡献抵消的依赖？

<a id="origin-2178"></a>
### 8.7 这里解决的是公共基准，不代表任意 Reward 尺度都没影响

把 100 / 99 改成 1 / 0，差距仍然是 1；把它改成 100 / 0，差距变成 100，学习信号当然会改变。

同样，RM 排序错误、分数差尺度不合适、Reward 相对 KL 惩罚过大，都不能仅靠“期望会抵消”解决。上述平移不变性针对本例固定 Prompt 下的公共分数偏移，也不能推广为任意多步任务的奖励修改都无影响。

---

<a id="origin-2186"></a>
## 9. 样本少时为什么换成 Advantage？仍用 5 / 1 和 100 / 99 算一遍

<a id="origin-2188"></a>
### 9.1 先减去当前状态的正常水平

**本节仍然以“梯度变化是否稳定”为判断标准：减去 Baseline 之后，要继续乘上 log 概率梯度，再比较不同样本的最终梯度贡献。**

问题 B 的 100 分中，很大一部分只是“这个问题本来就有很高的评分基准”。我们希望训练信号直接回答：**这个回答比当前策略的平均表现好多少？**

定义：

\[
Q^\pi(s,a)=\mathbb E_\pi[G_t\mid s_t=s,a_t=a]
\]

\[
V^\pi(s)=\mathbb E_{a\sim\pi(\cdot\mid s)}[Q^\pi(s,a)]
\]

\[
\boxed{A^\pi(s,a)=Q^\pi(s,a)-V^\pi(s)}
\]

\(Q\) 是**选定这个动作后的期望回报**，\(V\) 是**当前策略在同一状态下的平均回报**，\(A\) 是这个动作相对平均水平的增益。

本例暂时仍是确定奖励的单步任务，因此 \(Q=R=G\)。先假设 Critic 给出的 \(V\) 完全准确。

<a id="origin-2212"></a>
### 9.2 问题 A：5 / 1 分，减去平均值 3

\[
V(A)=0.5\times5+0.5\times1=3
\]

**为什么这里能直接算出 \(V\)，实际训练却要用神经网络估计？有了 Rollout，能不能直接算？**

可以用 Rollout 估计 \(V\)，但一条 Rollout 通常不能直接算出准确的 \(V\)。先区分这两个量：

\[
G_t=\text{这一次实际得到的回报},\qquad
V^\pi(s_t)=\mathbb E_\pi[G_t\mid s_t]
\]

**\(V\) 是从同一个状态出发、按当前策略行动时，多种可能结果的平均回报。** 本例能够直接算出 3，是因为**我们事先给出了全部两种结果及其概率**：好回答得 5 分、概率 0.5；差回答得 1 分、概率 0.5。

实际只做一次 Rollout，可能得到 \(G=5\)，也可能得到 \(G=1\)。**看到一次 5 分，不代表这个状态的平均水平就是 5 分；看到一次 1 分，也不代表平均水平就是 1 分。** 因此不能由这一个结果直接知道 \(V=3\)。

如果固定同一个状态、同一个策略，独立 Rollout 很多次，确实可以用样本平均估计：

\[
\boxed{\hat V(s)=\frac{G^{(1)}+G^{(2)}+\cdots+G^{(N)}}{N}}
\]

这里每次都要从同一个状态重新按策略选择动作，并继续生成到结束。样本足够多时，平均值可以逐渐接近真实的 \(V(s)\)；如果固定同一个动作，只对它后面的结果求平均，估计的则是 \(Q(s,a)\)。

**所以，神经网络并非数学上必需。** 如果状态很少，又能反复采样，直接统计平均回报也可行。但在大模型中，每个“Prompt + 已生成前缀”都是不同状态，为每个前缀反复生成大量完整回答，成本很高，也不能把不同状态的回报混在一起简单平均，就当成各自的 \(V\)。

因此，用 Critic 学习“状态 → 平均回报”的映射：以 Rollout 中的 \(G_t\) 或 TD 目标作为训练目标，通过许多样本学习各状态的正常水平，并对新前缀给出估计。**Rollout 提供训练样本，Critic 学习和预测平均值；单次回报 \(G_t\) 与 Critic 输出的 \(\hat V(s_t)\) 不是一回事。**

尤其不能直接把当前这条数据的 \(G_t\) 当成它自己的 \(V_t\)，否则：

\[
\hat A_t=G_t-V_t=G_t-G_t=0
\]

这条数据就失去了鼓励或惩罚当前动作的学习信号。

参考：[Spinning Up：价值函数定义](https://spinningup.openai.com/en/latest/spinningup/rl_intro.html#value-functions)、[VPG 中的价值函数估计](https://spinningup.openai.com/en/latest/algorithms/vpg.html)。

回到本例，用准确的平均值 3 作基准：

\[
A_{A,\mathrm{好}}=5-3=+2,\qquad
A_{A,\mathrm{差}}=1-3=-2
\]

改用 Advantage 后，单次梯度贡献为：

\[
\begin{aligned}
g_{A,\mathrm{好}}&=(+2)\times(+0.5)=+1\\
g_{A,\mathrm{差}}&=(-2)\times(-0.5)=+1
\end{aligned}
\]

好回答的概率应该提高；差回答的概率应该降低。**在这个二选一模型中，两种更新都对应提高好回答概率，所以它们对 \(\theta\) 的梯度贡献都是正数。**

<a id="origin-2271"></a>
### 9.3 问题 B：100 / 99 分，减去平均值 99.5

\[
V(B)=0.5\times100+0.5\times99=99.5
\]

所以：

\[
A_{B,\mathrm{好}}=100-99.5=+0.5,\qquad
A_{B,\mathrm{差}}=99-99.5=-0.5
\]

改用 Advantage 后：

\[
\begin{aligned}
g_{B,\mathrm{好}}&=(+0.5)\times(+0.5)=+0.25\\
g_{B,\mathrm{差}}&=(-0.5)\times(-0.5)=+0.25
\end{aligned}
\]

把前后结果放在一起：

| Prompt | 原始 \(G\) 加权：好 / 差梯度 | Advantage 加权：好 / 差梯度 | 期望梯度 |
|---|---|---|---:|
| 问题 A：5 / 1 | +2.5 / −0.5 | +1 / +1 | 1 |
| 问题 B：100 / 99 | +50 / −49.5 | +0.25 / +0.25 | 0.25 |

现在，问题 B 即使只采到一个好回答，或者只采到一个差回答，都得到 +0.25。第 9.5 节的“6 好 4 差”和“4 好 6 差”两个批次，也都会得到 +0.25。

Advantage 合适的原因就在这里：减掉公共基准后，每个样本的权重直接体现它相对当前策略的好坏，保留期望梯度，同时减少有限采样的波动。

**因此，在当前这个例子中，哪怕只有一条数据，无论采到好回答还是差回答，使用 Advantage 得到的梯度贡献都是 +0.25，不会再像直接用 \(G\) 时那样，在 +50 和 −49.5 之间大幅变化。**

**本例稳定的是最终的梯度贡献，不是说两个回答的 Advantage 相同：Advantage 是 +0.5 和 −0.5，但乘上各自的 log 概率梯度后，都得到 +0.25。** 这里梯度方差降为 0，依赖二选一、概率各 0.5、确定奖励和准确 Value 这些特殊条件；**这个例子稳定，不意味着所有情况都稳定。**

<a id="origin-2308"></a>
### 9.4 同时 Rollout 10 条：用 \(G_t\) 和 Advantage，实际梯度有什么区别？

继续使用 **100 / 99** 的例子：同一个 Prompt，好回答得 100，差回答得 99，当前生成两者的概率各为 0.5。先固定模型，假设 Critic 给出的平均水平 99.5 完全准确。

**我们期待的正确梯度是 +0.25，应提高好回答的概率。** 一条回答的梯度贡献为：

| 回答 | 直接用 \(G_t\) 的梯度 | 用 Advantage 的梯度 |
|---|---:|---:|
| 好回答，得 100 | \(100\times0.5=+50\) | \((100-99.5)\times0.5=+0.25\) |
| 差回答，得 99 | \(99\times(-0.5)=-49.5\) | \((99-99.5)\times(-0.5)=+0.25\) |

**第一批：同时 Rollout 10 条，假设采到 6 条好回答、4 条差回答。**

直接用 \(G_t\)，平均梯度为：

\[
\bar g_G=\frac{6\times50+4\times(-49.5)}{10}
=\frac{102}{10}=\boxed{+10.2}
\]

用 Advantage，平均梯度为：

\[
\bar g_A=\frac{6\times0.25+4\times0.25}{10}=\boxed{+0.25}
\]

直接用 \(G_t\) 时，方向虽正确，但梯度 10.2 远大于期待的 0.25；用 Advantage 时，这一批恰好得到正确梯度。

**第二批：仍从同一份模型采样 10 条，假设这次是 4 条好回答、6 条差回答。**

直接用 \(G_t\)，平均梯度变为：

\[
\bar g_G=\frac{4\times50+6\times(-49.5)}{10}
=\frac{-97}{10}=\boxed{-9.7}
\]

用 Advantage，平均梯度仍为：

\[
\bar g_A=\frac{4\times0.25+6\times0.25}{10}=\boxed{+0.25}
\]

**这次直接用 \(G_t\)，连更新方向都反了：负梯度会降低好回答的概率。** 用 Advantage 时，每条回答的梯度贡献都为 +0.25，所以批次平均仍为 +0.25。

把不同批次放在一起：

| 10 条 Rollout 的组成 | 直接用 \(G_t\) 的平均梯度 | 用 Advantage 的平均梯度 | 期待的正确梯度 |
|---|---:|---:|---:|
| 6 好、4 差 | +10.2 | +0.25 | +0.25 |
| 4 好、6 差 | −9.7 | +0.25 | +0.25 |
| 5 好、5 差 | +0.25 | +0.25 | +0.25 |

**模型和奖励规则没变，仅仅是采到的好、差回答数量不同，原始梯度就从 +10.2 变成 −9.7，这就是采样波动影响更新的具体表现。** 原始 Policy Gradient 的期望仍然正确，但一个有限批次不一定能让大幅的正负贡献恰好抵消。

固定模型、每批独立采样 10 条，两种方法的统计量为：

| 方法 | 批次平均梯度的期望 | 10 条平均梯度的方差 |
|---|---:|---:|
| 直接用 \(G_t\) | +0.25 | 247.50625 |
| 用 Advantage | +0.25 | 0 |

**本例中，Advantage 保留了正确的期望梯度，同时消除了批次梯度的波动。** 这个特殊结果依赖当前二选一、等概率、确定奖励和准确基线的设定；[Reward 为什么可以用绝对分数？Policy Gradient 在期望中会反映相对差距](../../%E8%AE%B2%E4%B9%89/PPO%20%E9%87%87%E6%A0%B7%E4%B8%8E%E8%AE%AD%E7%BB%83/b19-PPO%20%E9%87%8D%E7%82%B9%E5%A4%8D%E4%B9%A0.md#origin-2027)再看使用 Advantage 后仍有波动的例子。

<a id="origin-2372"></a>
### 9.5 这个例子梯度稳定，不代表所有情况都稳定

训练中最终使用的采样梯度是：

\[
\boxed{g_t=\hat A_t\nabla_\theta\log\pi_\theta(a_t\mid s_t)}
\]

其中，常见的 Advantage 估计及回报展开式为：

\[
\hat A_t^{\mathrm{MC}}=G_t-\hat V(s_t),\qquad
G_t=r_t+\gamma r_{t+1}+\gamma^2r_{t+2}+\cdots
\]

不同样本的回报、动作以及 log 概率梯度都可能不同。**用了 Advantage，并不能保证乘完之后的 \(g_t\) 每次都一样。** [Reward 为什么可以用绝对分数？Policy Gradient 在期望中会反映相对差距](../../%E8%AE%B2%E4%B9%89/PPO%20%E9%87%87%E6%A0%B7%E4%B8%8E%E8%AE%AD%E7%BB%83/b19-PPO%20%E9%87%8D%E7%82%B9%E5%A4%8D%E4%B9%A0.md#origin-2027)用 1000 / 0 奖励，直接算出这种梯度变化。

---

<a id="origin-2391"></a>
## 10. 方差是什么意思？Rollout 10 条，比较 $G_t$ 与 Advantage 的梯度

前面的 100 / 99 例子里，减去平均水平后，梯度很稳定。现在换一个 **1000 / 0** 的随机奖励例子，直接看看：**同时 Rollout 10 条，实际算出的平均梯度，与我们期待的梯度相差多少？**

第 11、12 节沿用同一个例子：选盒子，再领奖。令 $\gamma=1$，不考虑 KL。

<a id="origin-2397"></a>
### 10.1 先说明奖励和我们期待的梯度

**当前模型以 0.5 的概率选 A，以 0.5 的概率选 B：**

**- 选 A：一半概率得到 1000，一半概率得到 0，平均回报为 500。**
**- 选 B：一定得到 0。**

选盒子时奖励为 0，领奖后结束。因此，一条 Rollout 的 $G_t$ 就是最终领到的奖励。

当前状态的平均回报是 250。先假设 Critic 神经网络给出的价值估计完全准确：

$$
\hat V(s_t)=250
$$

沿用前面的参数设置：$p=\sigma(\theta)$ 控制选 A 的概率，当前 $p=0.5$。

**为什么正确的期望梯度是 $500p(1-p)$？下面分三步推导。**

**第一步：写出期望奖励。** 选 A 后的平均回报为 $0.5\times1000+0.5\times0=500$，选 B 后的回报始终为 0，因此：

$$
J(\theta)=p\times500+(1-p)\times0=500p
$$

这里 $p$ 是选 A 的概率，选 A 后中奖的概率 0.5 已经包含在平均回报 500 中。

**第二步：计算概率 $p$ 对参数 $\theta$ 的导数。** 本例用 Sigmoid 将参数变成概率：

$$
p=\sigma(\theta)=\frac{1}{1+e^{-\theta}}
$$

因此：

$$
\frac{\partial p}{\partial\theta}
=\frac{e^{-\theta}}{(1+e^{-\theta})^2}
=\frac{1}{1+e^{-\theta}}\left(1-\frac{1}{1+e^{-\theta}}\right)
=p(1-p)
$$

**第三步：用链式法则，对模型参数 $\theta$ 求导。**

$$
\boxed{
\frac{\partial J}{\partial\theta}
=\frac{\partial J}{\partial p}\frac{\partial p}{\partial\theta}
=500p(1-p)
}
$$

**关键是求导对象：对概率 $p$ 求导得到 500；对模型参数 $\theta$ 求导，还要乘上 $p$ 对 $\theta$ 的导数 $p(1-p)$。** 这个因子来自本例的 Sigmoid 参数化。

代入当前 $p=0.5$，得到我们期待的正确梯度：

$$
\frac{\partial J}{\partial\theta}=500\times0.5\times0.5=\boxed{+125}
$$

选 A 的 log 概率梯度为 $+0.5$，选 B 的为 $-0.5$。每条数据的梯度贡献是“权重乘 log 概率梯度”：

| 一条 Rollout 的结果 | $G_t$ | MC Advantage：$G_t-250$ | 直接用 $G_t$ 的梯度 | 用 MC Advantage 的梯度 |
|---|---:|---:|---:|---:|
| A，得 1000 | 1000 | $+750$ | $1000\times0.5=+500$ | $750\times0.5=+375$ |
| A，得 0 | 0 | $-250$ | $0\times0.5=0$ | $(-250)\times0.5=-125$ |
| B，得 0 | 0 | $-250$ | $0\times(-0.5)=0$ | $(-250)\times(-0.5)=+125$ |

这里用的是 $G_t-250$ 对 Advantage 的**采样估计**，仍然会受这一次领奖运气的影响。

<a id="origin-2467"></a>
### 10.2 同时 Rollout 10 条：假设采到了这些结果

| 结果 | 条数 |
|---|---:|
| A，得 1000 | 1 |
| A，得 0 | 3 |
| B，得 0 | 6 |
| 合计 | 10 |

**直接用 $G_t$：** 只有那一条中奖数据给出非零梯度，批次平均梯度为：

$$
\bar g_G=\frac{1\times500+3\times0+6\times0}{10}=\boxed{50}
$$

**用 MC Advantage：** 三类数据都有梯度贡献，批次平均梯度为：

$$
\bar g_{\mathrm{MC}}=\frac{1\times375+3\times(-125)+6\times125}{10}=\boxed{75}
$$

把实际结果与期待的梯度比较：

| 方法 | 这批 10 条算出的平均梯度 | 我们期待的正确梯度 | 这批估计与目标的差 |
|---|---:|---:|---:|
| 直接用 $G_t$ | 50 | 125 | $-75$ |
| 用 MC Advantage | 75 | 125 | $-50$ |

**这一批里，Advantage 算出的 75 比直接用 $G_t$ 算出的 50 更接近目标 125，但仍没有完全准确。** 同样的学习率下，这批数据让参数更新的幅度小于使用正确梯度时的幅度。

<a id="origin-2497"></a>
### 10.3 再采一批 10 条：梯度又可能变成另一个数

先固定同一份模型，不更新参数，比较它可能采出的不同批次：

| 10 条 Rollout 的组成 | 直接用 $G_t$ 的平均梯度 | 用 MC Advantage 的平均梯度 | 正确目标 |
|---|---:|---:|---:|
| 1 条 A 得 1000，3 条 A 得 0，6 条 B | 50 | 75 | 125 |
| 4 条 A 得 1000，2 条 A 得 0，4 条 B | 200 | 175 | 125 |
| 2 条 A 得 1000，2 条 A 得 0，6 条 B | 100 | 125 | 125 |

例如第二批，直接用 $G_t$ 得到：

$$
\bar g_G=\frac{4\times500+2\times0+4\times0}{10}=200
$$

用 MC Advantage 得到：

$$
\bar g_{\mathrm{MC}}=\frac{4\times375+2\times(-125)+4\times125}{10}=175
$$

**这就是梯度方差的直观含义：模型没变、奖励规则没变，只是采到的数据不同，各批用于更新的平均梯度就会变化。** 变化越大，方差越大，同样学习率下的更新幅度就越容易受采样运气影响。

<a id="origin-2521"></a>
### 10.4 $G_t$ 与 Advantage 的区别：期望相同，波动大小不同

按真实概率计算，三种结果“A 得 1000”“A 得 0”“B 得 0”的概率分别是 0.25、0.25、0.5。因此两种方法的期望梯度都是：

$$
\mathbb E[g_G]=0.25\times500+0.25\times0+0.5\times0=125
$$

$$
\mathbb E[g_{\mathrm{MC}}]=0.25\times375+0.25\times(-125)+0.5\times125=125
$$

固定模型，每批独立采样 10 条，反复比较很多批次，可以得到：

| 方法 | 批次平均梯度的期望 | 10 条平均梯度的方差 |
|---|---:|---:|
| 直接用 $G_t$ | 125 | 4687.5 |
| 用 MC Advantage | 125 | 3125 |

**两种方法平均而言都能得到正确答案；本例中，减去基线后，批次平均梯度的方差更小，但仍然有波动。** 上面几批只是帮助理解的具体例子，不能仅凭几批就证明方差大小；降低方差也不保证每一批都比原方法更准确。

这里改善的是“权重乘 log 概率梯度”之后的波动；固定状态、只减去一个常数，并不会改变 $G_t$ 本身的方差。

下一节继续解决剩下的问题：**能不能用 Critic 预测未来平均回报，减少随机领奖的影响？如果预测不准，又怎么办？** 这就引出 TD 和 GAE。

---

<a id="origin-2548"></a>
## 11. 同一个例子：TD 与 GAE 算出的梯度是多少？

仍然选盒子、领奖，只对选盒参数 \(\theta\) 求导。
**正确期望梯度仍是 +125。**

<a id="origin-2553"></a>
### 11.1 保留推导：从 \(G_t-V_t\) 到 TD Error

这里是全篇最重要的推导。

开始时我们有：

$$
\hat A_t^{\mathrm{MC}}=G_t-\hat V(s_t)
$$

为了看清结构，先假设价值函数为 $V$，再将 $G_t$ 展开：

$$
G_t=r_t+\gamma r_{t+1}+\gamma^2r_{t+2}+\gamma^3r_{t+3}+\cdots
$$

所以：

$$
\begin{aligned}
A_t^{\mathrm{MC}}=G_t-V(s_t)
={}&r_t+\gamma r_{t+1}+\gamma^2r_{t+2}+\cdots-V(s_t)
\end{aligned}
$$

现在只把第一步真实奖励单独拿出来：

$$
A_t^{\mathrm{MC}}=G_t-V(s_t)
=r_t+\gamma\underbrace{(r_{t+1}+\gamma r_{t+2}+\cdots)}_{G_{t+1}}-V(s_t)
$$

于是：

$$
\boxed{A_t^{\mathrm{MC}}=G_t-V(s_t)=r_t+\gamma G_{t+1}-V(s_t)}
$$

这里恰好对应你想看明白的三部分：

| 位置 | 含义 | 做什么处理 |
|---|---|---|
| 第一项 $r_t$ | $G_t$ 展开后的第一个真实即时奖励 | **保留** |
| 中间 $\gamma G_{t+1}$ | 后面从 $t+1$ 开始的全部未来回报 | **用 Critic 的 $\gamma V(s_{t+1})$ 估计** |
| 最后一项 $-V(s_t)$ | 原来 $A=Q-V$ 中被减掉的基准 | **保留** |

做这一次替换：

$$
\underbrace{r_t+\gamma G_{t+1}-V(s_t)}_{\text{原来的 MC 估计}}
\quad\longrightarrow\quad
\underbrace{r_t+\gamma V(s_{t+1})-V(s_t)}_{\text{TD Error}}
$$

定义：

$$
\boxed{\delta_t=r_t+\gamma\hat V(s_{t+1})-\hat V(s_t)}
$$

这里 $\delta_t$ 就叫 **一步 TD Error（时序差分误差）**。

**一句话理解：第一步已经拿到的真实奖励不变，后面还没拿到的奖励不再等它全部出现，而是提前交给 Critic 预测。**

严格一点，根据 Bellman 关系，如果使用真正的 $V^\pi$：

$$
Q^\pi(s_t,a_t)
=\mathbb E\left[r_t+\gamma V^\pi(s_{t+1})\mid s_t,a_t\right]
$$

两边减去 $V^\pi(s_t)$，得到：

$$
\boxed{\mathbb E[\delta_t\mid s_t,a_t]=A^\pi(s_t,a_t)}
$$

这个关系是在**条件期望**上成立，不代表任何一次实际采样的 $\delta_t$ 都等于真正的 Advantage。

> **终止状态要特殊处理**：如果这一步已结束，后面没有未来奖励，应把下一状态价值设为 0（或者用 `done` mask 屏蔽）：$\delta_t=r_t-V(s_t)$。

<a id="origin-2634"></a>
### 11.2 用准确 TD 算：每种结果的梯度都是 +125

**先假设 Critic 神经网络给出的 Value 完全正确。**

这里的 \(\hat V(s)\) 就是 **Critic 神经网络输入状态后，输出的未来平均回报估计值**。本节直接使用网络输出，不再展开 Value 的计算过程：

| 输入神经网络的状态 | 网络输出 \(\hat V\) |
|---|---:|
| \(s_t\)：还没有选盒子 | 250 |
| \(s_{t+1}^{A}\)：已经选 A，但还没有领奖 | 500 |
| \(s_{t+1}^{B}\)：已经选 B，但还没有领奖 | 0 |

**500 表示网络预测“选 A 后，未来平均能得 500”，不是这次一定领到 500。** 先假设这三个预测都准确，后面再看预测错误会怎样。

**把网络输出代入 TD 公式，算出选盒子的梯度。**

选盒子时 \(r_t=0\)，仍取 \(\gamma=1\)。

完整公式为：

\[
\delta_t=r_t+\gamma\hat V(s_{t+1})-\hat V(s_t),\qquad
g_{\mathrm{TD}}=\delta_tZ_t
\]

当前选 A 的概率 \(p=\sigma(\theta)=0.5\)，所以：

\[
Z_A=\frac{\partial\log p}{\partial\theta}=1-p=+0.5,
\qquad
Z_B=\frac{\partial\log(1-p)}{\partial\theta}=-p=-0.5
\]

如果这次选 A：

\[
\begin{aligned}
\delta_t^{A}
&=r_t+\gamma\hat V(s_{t+1}^{A})-\hat V(s_t)\\
&=0+1\times500-250=+250\\
g_{\mathrm{TD}}^{A}
&=\delta_t^{A}Z_A=(+250)\times(+0.5)=\boxed{+125}
\end{aligned}
\]

如果这次选 B：

\[
\begin{aligned}
\delta_t^{B}
&=r_t+\gamma\hat V(s_{t+1}^{B})-\hat V(s_t)\\
&=0+1\times0-250=-250\\
g_{\mathrm{TD}}^{B}
&=\delta_t^{B}Z_B=(-250)\times(-0.5)=\boxed{+125}
\end{aligned}
\]

| 选哪个 | TD Advantage | 梯度计算 | 单次梯度 |
|---|---:|---|---:|
| A | \(500-250=250\) | \(250\times0.5\) | +125 |
| B | \(0-250=-250\) | \((-250)\times(-0.5)\) | +125 |

**因此，对“选盒子”这个参数，无论选 A 后最终领到 1000 还是 0，或者选了 B，本例的一步 TD 梯度贡献都是 +125。** 这是因为选盒子这一步的 TD 使用领奖前的平均价值，没有把这一次随机领奖的结果直接放进来。

\[
\mathbb E[g_{\mathrm{TD}}]=0.5\times125+0.5\times125=125
\]

\[
\operatorname{Var}(g_{\mathrm{TD}})
=0.5(125-125)^2+0.5(125-125)^2=0
\]

**但神经网络如果预测不准确，就可能出现“偏差”。**

前面之所以每次都能得到正确的 +125，是因为本例中网络预测完全准确。实际训练时，Critic 是学出来的，预测可能出错。

假设选 A 后的真实平均回报仍是 500，网络却输出了 **200**；当前状态的 250、选 B 后的 0 仍然准确。此时：

\[
\begin{aligned}
\delta_t^{A}&=0+1\times200-250=-50\\
g_{\mathrm{TD}}^{A}&=(-50)\times(+0.5)=-25\\
\delta_t^{B}&=0+1\times0-250=-250\\
g_{\mathrm{TD}}^{B}&=(-250)\times(-0.5)=+125
\end{aligned}
\]

选 A 和 B 的概率仍各为 0.5，所以平均梯度变成：

\[
\mathbb E[g_{\mathrm{TD}}]
=0.5\times(-25)+0.5\times125=\boxed{50}
\]

**正确的期望梯度是 +125，但这个估计平均只能给出 +50，这种平均值与正确目标之间的差，就是偏差（Bias）：**

\[
\operatorname{Bias}
=\mathbb E[g_{\mathrm{TD}}]-\nabla_\theta J
=50-125=\boxed{-75}
\]

**方差问“每次估计波动大不大”，偏差问“估计的平均值是否偏离正确目标”。** MC Advantage 会受实际领奖结果的随机性影响；一步 TD 用网络预测替代未来回报，通常能减少这种波动，但错误的未来价值预测可能使平均梯度偏离正确目标。

**这就引出了 GAE：既然全用实际回报有采样波动，全靠网络预测又可能有偏差，就结合不同步数的估计，用 \(\lambda\) 调节对预测与实际回报的依赖。** GAE 是偏差与方差之间的折中方法，不保证把两者同时消除。下面先推导它如何结合这些估计，再算具体结果。

准确 TD 在本例中方差为 0，也依赖选盒子后的状态确定、两种选择等概率等设定；一般任务即使 Critic 准确，也可能仍有梯度波动。

<a id="origin-2743"></a>
### 11.3 保留推导：从 TD Error 到 GAE

承接上一节，先写出一步和两步的 Advantage 估计：一步更多依赖网络预测，两步多使用一步真实奖励。GAE 将不同步数的估计结合起来，调节这种取舍。

一步 Advantage 估计：

\[
\hat A_t^{(1)}
=r_t+\gamma\hat V(s_{t+1})-\hat V(s_t)
=\delta_t
\]

两步 Advantage 估计：

\[
\hat A_t^{(2)}
=r_t+\gamma r_{t+1}+\gamma^2\hat V(s_{t+2})-\hat V(s_t)
\]

把两个 TD Error 相加：

\[
\begin{aligned}
\delta_t+\gamma\delta_{t+1}
&=r_t+\gamma\hat V(s_{t+1})-\hat V(s_t)\\
&\quad+\gamma r_{t+1}+\gamma^2\hat V(s_{t+2})
-\gamma\hat V(s_{t+1})\\
&=\hat A_t^{(2)}
\end{aligned}
\]

中间的 Value 一正一负，抵消了。
推广到 \(n\) 步：

\[
\hat A_t^{(n)}=\sum_{l=0}^{n-1}\gamma^l\delta_{t+l}
\]

GAE 用 \(\lambda\in[0,1]\) 调节各跨度的权重。
对在 \(T\) 真正结束的轨迹：

\[
\boxed{
\hat A_t^{\mathrm{GAE}}
=\sum_{l=0}^{T-t-1}(\gamma\lambda)^l\delta_{t+l}
}
\]

**先把求和符号展开，看清楚 GAE 到底加了什么。**

\[
\begin{aligned}
\hat A_t^{\mathrm{GAE}}
&=\delta_t
+\gamma\lambda\delta_{t+1}
+(\gamma\lambda)^2\delta_{t+2}
+\cdots\\
&\quad+(\gamma\lambda)^{T-t-1}\delta_{T-1}
\end{aligned}
\]

也就是：当前这一步的 TD Error 权重为 1，下一步权重为 \(\gamma\lambda\)，再下一步权重为 \((\gamma\lambda)^2\)，一直加到结束前的最后一步。\(T\) 是终止状态所在的时刻，最后一笔奖励是 \(r_{T-1}\)。

每一个 \(\delta\) 都可以继续展开：

\[
\begin{aligned}
\hat A_t^{\mathrm{GAE}}
&=\underbrace{\bigl[r_t+\gamma\hat V(s_{t+1})-\hat V(s_t)\bigr]}_{\delta_t}\\
&\quad+\gamma\lambda
\underbrace{\bigl[r_{t+1}+\gamma\hat V(s_{t+2})-\hat V(s_{t+1})\bigr]}_{\delta_{t+1}}\\
&\quad+(\gamma\lambda)^2
\underbrace{\bigl[r_{t+2}+\gamma\hat V(s_{t+3})-\hat V(s_{t+2})\bigr]}_{\delta_{t+2}}
+\cdots
\end{aligned}
\]

**下面分别代入 \(\lambda=0\) 和 \(\lambda=1\)，看看为什么它们对应 TD 和 MC。**

**1. \(\lambda=0\)：只剩一步 TD。**

TD 是 **Temporal Difference，时序差分**。这里的一步 TD Error，是“当前真实奖励 + 对下一状态的未来价值预测”，减去“对当前状态的价值预测”。

代入 \(\lambda=0\) 后，第一项权重仍为 1，后面各项权重都为 0，所以：

\[
\boxed{
\hat A_t^{\mathrm{GAE}}=\delta_t
=r_t+\gamma\hat V(s_{t+1})-\hat V(s_t)
}
\]

**只使用当前这一步真实奖励，后面的回报交给 Critic 神经网络预测。**

例如本例选 A 时，\(r_t=0\)、\(\gamma=1\)，网络给出下一状态价值 500、当前状态价值 250：

\[
\hat A_t^{\mathrm{GAE}}=0+1\times500-250=250
\]

这就是一步 TD Advantage 估计。

**2. \(\lambda=1\)：所有 TD Error 加起来，回到 MC。**

MC 是 **Monte Carlo，蒙特卡洛**。这里的 MC 方法，就是实际采样一条完整轨迹，累计真实奖励得到 \(G_t\)，再减去当前状态的价值估计：

\[
\hat A_t^{\mathrm{MC}}=G_t-\hat V(s_t)
\]

为什么 GAE 在 \(\lambda=1\) 时会得到这个式子？先代入：

\[
\hat A_t^{\mathrm{GAE}}
=\delta_t+\gamma\delta_{t+1}
+\gamma^2\delta_{t+2}+\cdots
+\gamma^{T-t-1}\delta_{T-1}
\]

再把 TD Error 展开：

\[
\begin{aligned}
\hat A_t^{\mathrm{GAE}}
&=\bigl[r_t+\gamma\hat V(s_{t+1})-\hat V(s_t)\bigr]\\
&\quad+\gamma\bigl[r_{t+1}+\gamma\hat V(s_{t+2})-\hat V(s_{t+1})\bigr]\\
&\quad+\cdots\\
&\quad+\gamma^{T-t-1}
\bigl[r_{T-1}+\gamma\hat V(s_T)-\hat V(s_{T-1})\bigr]
\end{aligned}
\]

第一项里的 \(+\gamma\hat V(s_{t+1})\)，被第二项里的 \(-\gamma\hat V(s_{t+1})\) 抵消。之后的中间价值预测也这样一正一负地抵消，剩下：

\[
\begin{aligned}
\hat A_t^{\mathrm{GAE}}
&=r_t+\gamma r_{t+1}+\cdots
+\gamma^{T-t-1}r_{T-1}\\
&\quad+\gamma^{T-t}\hat V(s_T)-\hat V(s_t)
\end{aligned}
\]

真正结束时，终止状态的未来价值设为 \(\hat V(s_T)=0\)。而前面的奖励之和就是 \(G_t\)，因此：

\[
\boxed{\hat A_t^{\mathrm{GAE}}=G_t-\hat V(s_t)=\hat A_t^{\mathrm{MC}}}
\]

**这时，未来回报使用这条轨迹实际得到的奖励；中间状态的价值预测已经抵消，但当前状态的基线 \(\hat V(s_t)\) 仍然保留。**

例如本例选 A，最终领到 1000 或 0，仍取 \(\gamma=1\)、\(\hat V(s_t)=250\)：

\[
\hat A_t^{\mathrm{MC}}=
\begin{cases}
0+1000-250=750,&\text{领到 1000}\\
0+0-250=-250,&\text{领到 0}
\end{cases}
\]

**3. \(0<\lambda<1\)：后一步的修正只采用一部分。**

这时，中间价值预测不会全部抵消，后面的 TD Error 也会逐步衰减。例如 \(\gamma=1\)、\(\lambda=0.5\)：

\[
\hat A_t^{\mathrm{GAE}}
=\delta_t+0.5\delta_{t+1}+0.25\delta_{t+2}+\cdots
\]

**既利用 Critic 的预测，也让后面的实际奖励参与修正；通过 \(\lambda\) 调节预测误差与采样波动之间的取舍。** 对本例的两步轨迹，可以把这种结合直接写出来：

本例只有两步，且 \(\gamma=1\)：

\[
\begin{aligned}
\hat A_t^{\mathrm{GAE}}
&=\delta_t+\lambda\delta_{t+1}\\
&=(1-\lambda)\hat A_t^{(1)}+\lambda\hat A_t^{(2)}
\end{aligned}
\]

**一步 TD 提供预测；后一步 TD 用实际奖励修正。**

<a id="origin-2927"></a>
### 11.4 用 GAE 算：取 \(\lambda=0.5\)

先继续假设 Critic **准确**。
领奖后真正终止，终止状态的 Value 为 0。

因此两步 TD Error 分别为：

\[
\delta_t=V(s_{t+1})-250
\]

\[
\delta_{t+1}=R-V(s_{t+1})
\]

GAE 权重与最终梯度为：

\[
\hat A_t^{\mathrm{GAE}}=\delta_t+0.5\delta_{t+1}
\]

\[
g_{\mathrm{GAE}}=\hat A_t^{\mathrm{GAE}}Z_t
\]

每行先算权重，再乘 log 概率梯度：

| 结果 | GAE 权重计算 | 梯度计算 |
|---|---|---|
| A，得 1000 | \(250+0.5(1000-500)=500\) | \(500\times0.5=+250\) |
| A，得 0 | \(250+0.5(0-500)=0\) | \(0\times0.5=0\) |
| B，得 0 | \(-250+0.5(0-0)=-250\) | \((-250)\times(-0.5)=+125\) |

期望梯度：

\[
\mathbb E[g_{\mathrm{GAE}}]
=0.25\times250+0.25\times0+0.5\times125
=\boxed{125}
\]

梯度方差：

\[
\begin{aligned}
\operatorname{Var}(g_{\mathrm{GAE}})
&=0.25(250-125)^2\\
&\quad+0.25(0-125)^2+0.5(125-125)^2\\
&=\boxed{7812.5}
\end{aligned}
\]

把所有方法放在一起：

| 梯度 | A，得 1000 | A，得 0 | B，得 0 | 期望 | 梯度方差 |
|---|---:|---:|---:|---:|---:|
| 正确目标 | — | — | — | **+125** | — |
| 用 \(G_t\) | +500 | 0 | 0 | +125 | 46875 |
| 用 MC Advantage | +375 | −125 | +125 | +125 | 31250 |
| 用准确 TD | +125 | +125 | +125 | +125 | 0 |
| 用 GAE，\(\lambda=0.5\) | +250 | 0 | +125 | +125 | 7812.5 |

方差按三种结果的概率 0.25、0.25、0.5 计算，各行都减去期望梯度 125 后再平方、加权。“正确目标”是要估计的期望梯度，未定义单次采样结果，因此方差一栏记为“—”。

本例的梯度方差：

\[
\underbrace{46875}_{G_t}
\;\longrightarrow\;
\underbrace{31250}_{\mathrm{MC\ Advantage}}
\;\longrightarrow\;
\underbrace{7812.5}_{\mathrm{GAE},\ \lambda=0.5}
\]

**期望不变，单次梯度更接近 +125。**

本例还可写成：

\[
\operatorname{Var}(g_{\mathrm{GAE}})=31250\lambda^2
\]

\(\lambda=0\) 时方差为 0；\(\lambda=1\) 回到 MC。
这些大小关系是本例结果，一般任务不保证。

<a id="origin-3012"></a>
### 11.5 从采样到更新：偏差和方差到底怎样影响训练？

这一节从头走一次训练过程：**先采样一批数据，用同一批数据分别计算三种 $\lambda$ 的梯度，最后用批次平均梯度更新参数。**

<a id="origin-3016"></a>
#### 11.5.1 先固定当前模型：我们想得到什么梯度？

仍然使用选盒子的例子：

- 当前选 A、选 B 的概率各为 0.5。
- 选 A 后，一半概率得到 1000，一半概率得到 0。
- 选 B 后，一定得到 0。
- 正确的期望梯度是 **+125**，应提高选 A 的概率。

现在 Critic 神经网络预测错了：选 A 后的真实平均回报是 500，网络却给出 **200**；当前状态预测为 250，选 B 后预测为 0，这两项仍然准确。取 $\gamma=1$。

先固定这份策略和 Critic，比较它们在**这一次更新前**的不同估计方法。三种 $\lambda$ 使用同一批采样数据。

一条数据的梯度贡献为：

$$
g=\hat A_t^{\mathrm{GAE}}Z_t
$$

选 A 时，$Z_A=+0.5$。两步 TD Error 为：

$$
\delta_t=0+200-250=-50,\qquad \delta_{t+1}=R-200
$$

因此：

$$
g_A=\bigl[-50+\lambda(R-200)\bigr]\times0.5
$$

如果 A 得到 1000：

$$
g_{A,1000}=\bigl[-50+800\lambda\bigr]\times0.5=-25+400\lambda
$$

如果 A 得到 0：

$$
g_{A,0}=\bigl[-50-200\lambda\bigr]\times0.5=-25-100\lambda
$$

选 B 时，$Z_B=-0.5$，两步 TD Error 为 $-250$ 和 0，所以：

$$
g_{B,0}=(-250+\lambda\times0)\times(-0.5)=125
$$

把 $\lambda=0、0.5、1$ 分别代入：

| 一条数据的结果 | $\lambda=0$ | $\lambda=0.5$ | $\lambda=1$ |
|---|---:|---:|---:|
| A，得 1000 | $-25$ | $+175$ | $+375$ |
| A，得 0 | $-25$ | $-75$ | $-125$ |
| B，得 0 | $+125$ | $+125$ | $+125$ |

**接下来才是真正的采样：这一批出现了几条中奖、几条没中奖，会决定实际用于更新的平均梯度。**

<a id="origin-3075"></a>
#### 11.5.2 先采样 10 条：假设这一批中奖偏少

当前策略下，每条数据的三种结果概率分别为 0.25、0.25、0.5。采样 10 条不保证恰好按这个比例出现。

假设这一批实际得到：

| 结果 | 条数 |
|---|---:|
| A，得 1000 | 1 |
| A，得 0 | 4 |
| B，得 0 | 5 |
| 合计 | 10 |

训练时，先把 10 条数据的梯度贡献相加，再除以 10，得到批次平均梯度 $\bar g$。

**如果 $\lambda=0$：**

$$
\bar g_0=\frac{1\times(-25)+4\times(-25)+5\times125}{10}
=\frac{500}{10}=\boxed{50}
$$

**如果 $\lambda=0.5$：**

$$
\bar g_{0.5}=\frac{1\times175+4\times(-75)+5\times125}{10}
=\frac{500}{10}=\boxed{50}
$$

**如果 $\lambda=1$：**

$$
\bar g_1=\frac{1\times375+4\times(-125)+5\times125}{10}
=\frac{500}{10}=\boxed{50}
$$

**这批数据中，三个方法碰巧都给出 50，低于正确目标 125。** $\lambda=1$ 在期望上无偏，但这一次只采了 10 条，实际平均梯度也可能不准确。

这里的 $50-125=-75$ 是**这一次批次的估计误差**；不能只看这一批，就断定某个方法的理论偏差是 $-75$。

<a id="origin-3115"></a>
#### 11.5.3 换一批 10 条：假设这一批中奖偏多

仍然从同一份未更新的策略出发。另一批可能得到：

| 结果 | 条数 |
|---|---:|
| A，得 1000 | 4 |
| A，得 0 | 1 |
| B，得 0 | 5 |
| 合计 | 10 |

**如果 $\lambda=0$：**

$$
\bar g_0=\frac{4\times(-25)+1\times(-25)+5\times125}{10}
=\boxed{50}
$$

**如果 $\lambda=0.5$：**

$$
\bar g_{0.5}=\frac{4\times175+1\times(-75)+5\times125}{10}
=\boxed{125}
$$

**如果 $\lambda=1$：**

$$
\bar g_1=\frac{4\times375+1\times(-125)+5\times125}{10}
=\boxed{200}
$$

把两批结果放在一起：

| 采样到的 10 条数据 | $\lambda=0$ 的平均梯度 | $\lambda=0.5$ 的平均梯度 | $\lambda=1$ 的平均梯度 |
|---|---:|---:|---:|
| 中奖偏少：1 条 A 得 1000，4 条 A 得 0，5 条 B | 50 | 50 | 50 |
| 中奖偏多：4 条 A 得 1000，1 条 A 得 0，5 条 B | 50 | 125 | 200 |

**正确目标始终是 125，但 $\lambda=1$ 在第一批给出 50，在第二批给出 200。** 它平均意义上没有系统性偏差，但单个小批次会受到中奖次数的影响。

$\lambda=0$ 在这两批都给出 50，因为两批都恰好有 5 条 A、5 条 B，而它不使用 A 后续的中奖结果。**它减少了这部分随机波动，但错误的未来价值预测使平均梯度偏小。** 若两批选择 A、B 的次数也不同，它的批次梯度仍会变化。

<a id="origin-3158"></a>
#### 11.5.4 平均梯度算出来后，参数到底怎么更新？

先用普通策略梯度上升说明，暂不加入 PPO Clip、优势标准化或自适应优化器：

$$
\theta_{\mathrm{new}}=\theta_{\mathrm{old}}+\eta\bar g
$$

其中 $p=\sigma(\theta)$ 是选 A 的概率，$\eta$ 是学习率。$\bar g>0$ 会提高选 A 的概率，$\bar g<0$ 会降低选 A 的概率。

为了看清数字，取 $\eta=0.001$。在“中奖偏多”的第二批中：

| 方法 | 这批平均梯度 $\bar g$ | 参数变化 $\Delta\theta=0.001\bar g$ |
|---|---:|---:|
| 用正确的期望梯度作为对照 | 125 | $+0.125$ |
| $\lambda=0$ | 50 | $+0.05$ |
| $\lambda=0.5$ | 125 | $+0.125$ |
| $\lambda=1$ | 200 | $+0.2$ |

**同样的学习率，实际采样出的平均梯度直接决定这次更新的幅度。** 第一批中，三个方法的参数变化又都变成 $+0.05$。这些数字比较的是从同一个旧参数出发的一次更新，不是连续更新后的轨迹。

如果运气更差，还可能出现方向反了的批次。例如 10 条中，有 1 条 A 得 1000、7 条 A 得 0、2 条 B 得 0：

$$
\bar g_0=\frac{1\times(-25)+7\times(-25)+2\times125}{10}=5
$$

$$
\bar g_{0.5}=\frac{1\times175+7\times(-75)+2\times125}{10}=-10
$$

$$
\bar g_1=\frac{1\times375+7\times(-125)+2\times125}{10}=-25
$$

这种批次可能发生，虽然它的结果比例比前两批更偏。此时 $\lambda=1$ 的参数变化为 $-0.025$，会降低选 A 的概率；但真实的期望梯度仍为正，应该提高选 A 的概率。

**所以，偏差为 0 并不保证这次更新的方向正确；较大的方差意味着有限批次的结果可能更不稳定。** 这也不表示较小的 $\lambda$ 每次都更好：这里 $\lambda=0.5$ 也可能给出负梯度。

<a id="origin-3197"></a>
#### 11.5.5 如果采样 100 条，会怎样？

假设这次从同一份固定策略采样 100 条，得到 30 条 A 得 1000、20 条 A 得 0、50 条 B 得 0。

**如果 $\lambda=0$：**

$$
\bar g_0=\frac{30\times(-25)+20\times(-25)+50\times125}{100}
=\boxed{50}
$$

**如果 $\lambda=0.5$：**

$$
\bar g_{0.5}=\frac{30\times175+20\times(-75)+50\times125}{100}
=\boxed{100}
$$

**如果 $\lambda=1$：**

$$
\bar g_1=\frac{30\times375+20\times(-125)+50\times125}{100}
=\boxed{150}
$$

这批的 $\lambda=1$ 梯度是 150，参数变化为 $+0.15$，比前面中奖偏多的 10 条样本所给出的 200 更接近正确目标 125。

如果 100 条恰好得到 25 条 A 得 1000、25 条 A 得 0、50 条 B 得 0，三种方法的平均梯度分别是：

$$
\bar g_0=50,\qquad \bar g_{0.5}=87.5,\qquad \bar g_1=125
$$

**增加采样数量，可以让结果比例通常更接近真实概率，但不保证每一批 100 条都比某一批 10 条准确。** 上面只是可能采到的具体批次；一般规律要看重复采样的统计量。

<a id="origin-3232"></a>
#### 11.5.6 重复采样很多批：什么是偏差，什么是方差？

现在想象：固定这份模型，反复采样很多个批次，每批都算出一个平均梯度 $\bar g$。

三种结果的真实概率是 0.25、0.25、0.5，因此三种方法的理论期望分别是：

$$
\mathbb E[\bar g_0]=0.25(-25)+0.25(-25)+0.5(125)=50
$$

$$
\mathbb E[\bar g_{0.5}]=0.25(175)+0.25(-75)+0.5(125)=87.5
$$

$$
\mathbb E[\bar g_1]=0.25(375)+0.25(-125)+0.5(125)=125
$$

**偏差看的是这些批次平均梯度的期望，与正确目标 125 之间的差：**

$$
\operatorname{Bias}(\bar g)=\mathbb E[\bar g]-125
$$

因此三种偏差是 $-75$、$-37.5$、0。它们不是从某一个幸运或倒霉的批次算出来的。

**方差看的是不同批次的平均梯度，在各自期望周围波动多大。** 单条梯度的方差按以下公式计算：

$$
\operatorname{Var}(g)
=0.25(g_{A,1000}-\mu)^2
+0.25(g_{A,0}-\mu)^2
+0.5(g_{B,0}-\mu)^2
$$

其中 $\mu=\mathbb E[g]$。例如 $\lambda=1$ 时：

$$
\operatorname{Var}(g)
=0.25(375-125)^2+0.25(-125-125)^2+0.5(125-125)^2=31250
$$

固定策略和 Critic，假设每条轨迹独立采样，每批有 $N$ 条数据，则：

$$
\boxed{\operatorname{Var}(\bar g)=\frac{\operatorname{Var}(g)}{N}}
$$

把结果放在同一张表里：

| $\lambda$ | 批次平均梯度的期望 | 对正确梯度 125 的偏差 | 单条梯度方差 | 10 条平均梯度的方差 | 100 条平均梯度的方差 |
|---:|---:|---:|---:|---:|---:|
| 0：只用 TD | 50 | $-75$ | 5625 | 562.5 | 56.25 |
| 0.5：折中 | 87.5 | $-37.5$ | 9218.75 | 921.875 | 92.1875 |
| 1：回到 MC | 125 | 0 | 31250 | 3125 | 312.5 |

**从 10 条增加到 100 条，批次平均梯度的方差降为原来的十分之一，但每种方法的偏差没有改变。**

- $\lambda=0$：大量批次的平均仍趋近 50，而不是正确目标 125。仅增加采样不能修正这份 Critic 带来的系统性低估。
- $\lambda=1$：大量批次的平均正确。增加样本会减小单个批次的波动，但生成更多轨迹需要时间和计算。
- $\lambda=0.5$：本例中，平均值比 $\lambda=0$ 更接近正确目标，同时批次波动比 $\lambda=1$ 小。

<a id="origin-3294"></a>
#### 11.5.7 最后把“采样、偏差、方差、更新”连起来

一次训练是：**采样 $N$ 条 → 计算每条的 Advantage 和梯度贡献 → 求批次平均梯度 → 用这个平均梯度更新参数。**

**偏差影响平均更新是否准确。** 当前例子中，错误的预测让 $\lambda=0$ 的平均梯度从正确的 125 变成 50，平均更新幅度偏小；其他预测错误也可能造成方向错误。

**方差影响每个实际批次的更新是否稳定。** 即使平均正确，某一批的梯度仍可能过大、过小，甚至方向相反。增加样本通常能缓解这种波动，但需要采样成本。

**因此，在本例中，固定当前策略并独立采样，样本数量越多，$\lambda=1$ 的批次平均梯度从总体趋势上就越稳定地接近正确答案 +125。** 它本来就在期望上无偏；样本增加，让中奖和未中奖带来的随机波动更容易相互抵消。如果能采到足够多的样本，直接使用完整 MC 回报就更有吸引力。

**但实际训练往往没有那么多样本，每次生成完整轨迹又有成本。这时，折中就有意义了：适当减小 $\lambda$，借助 Critic 的预测减少波动，即使引入一些偏差，也可能让有限样本下的梯度估计更可靠。** 所以不能只看“$\lambda=1$ 偏差为 0”，还要看手头的采样数量能否把它的方差压下来。这里说的是总体统计趋势，不保证某一批更多的样本一定比某一批更少的样本准确。

**GAE 用 $\lambda$ 调节对预测与实际回报的依赖，在有限样本下折中这两种误差。** 这个例子不证明 $\lambda=0.5$ 永远最好，也不保证所有任务的偏差和方差都随 $\lambda$ 严格单调变化。

以上比较的是当前策略处、未加入 Clip 的梯度估计。实际 PPO 会在 Rollout 后使用固定的 Advantage，并结合 Ratio + Clip 更新；多轮更新后，梯度还会变化。下一节把这个过程对应到大模型生成。

<a id="origin-3310"></a>
### 11.6 与 PPO、实际生成的对应

LLM 的状态是 Prompt 加已生成的前缀。
动作是下一个 Token；未来奖励来自继续生成。
本例的“选盒子”对应当前动作。
“领奖”对应后续生成带来的回报。

Critic 从 Rollout 中学习平均回报。
TD 和 GAE 仍需要采样数据。
算出的 Advantage 再放进 PPO 的 Ratio + Clip 目标。

以上比较的是当前策略处的梯度估计。
PPO 多轮更新、Clip 生效后，梯度还会变化。

真正终止时，下一状态 Value 设为 0。
仅人为截断时，末端通常保留 Value bootstrap。
此时 \(\lambda=1\) 不一定等于完整 MC 回报。

GAE 理论参考：
[High-Dimensional Continuous Control Using Generalized Advantage Estimation](https://arxiv.org/abs/1506.02438)。

<a id="origin-3331"></a>
### 11.7 总结：用了 Advantage，为什么还需要 GAE？

**从 \(G_t\) 改用 Advantage，主要是为了降低策略梯度估计的方差；但减去基线不能消除所有波动。进一步使用 GAE，是为了在 Advantage 估计的偏差与方差之间取得折中。**

**GAE 没有替代 Advantage，它是一种估计 Advantage 的方法。** 整个关系是：

\[
G_t
\;\longrightarrow\;
\underbrace{G_t-\hat V(s_t)}_{\text{MC 方法估计 Advantage}}
\;\longrightarrow\;
\underbrace{\hat A_t^{\mathrm{GAE}}}_{\text{GAE 方法估计 Advantage}}
\]

**第一步：减基线，为什么能帮助降低方差？**

Advantage 衡量当前动作比这个状态下的平均表现好多少。减去只依赖状态的基线，并在 Actor 求导时将其视为常数，不改变期望策略梯度；合适的基线通常能让采样梯度更稳定。这里要降低的是 \(\hat A_t\nabla_\theta\log\pi_\theta(a_t\mid s_t)\) 的方差，不只是权重 \(\hat A_t\) 本身的方差。

但减基线仍保留了未来奖励的随机性。本例选 A 后，可能领到 1000，也可能领到 0；减去当前状态的基线 250 后，MC Advantage 仍然可能是 +750 或 −250。**同一个动作，仅因领奖运气不同，估计的 Advantage 就一正一负，梯度仍有波动。**

**第二步：TD / GAE，为什么还能进一步改进？**

一步 TD 保留当前真实奖励，用 Critic 预测的未来平均回报替代一次采样的未来回报：

\[
\underbrace{r_t+\gamma G_{t+1}-\hat V(s_t)}_{\text{MC Advantage}}
\quad\longrightarrow\quad
\underbrace{r_t+\gamma\hat V(s_{t+1})-\hat V(s_t)}_{\text{一步 TD 估计}}
\]

这样通常能减少未来随机结果带来的波动，但 **Critic 预测不准时，会引入偏差**。GAE 通过 \(\lambda\) 调节对预测与实际回报的依赖：

- \(\lambda=0\)：只用一步 TD，更依赖 Critic 预测。
- \(\lambda=1\)：完整轨迹真正终止、终止价值为 0 时，回到 MC Advantage。
- 中间取值：结合不同步数的估计，在预测误差与采样波动之间折中。

**因此，减基线与 GAE 解决的是不同层面的问题：减基线让策略梯度通常更稳定；GAE 进一步改善 Advantage 的估计。二者都不保证在所有情况下方差一定下降，GAE 也不保证估计始终无偏。**

---

<a id="origin-3371"></a>
## 12. REINFORCE 与 PPO：为什么 PPO 能复用 Rollout，为什么旧数据不能一直用？

<a id="origin-3373"></a>
### 12.1 PPO 相比 REINFORCE 的好处是什么？

<a id="origin-3375"></a>
#### 12.1.1 REINFORCE：一批 Rollout 通常只更新一次

我们的目标是调整 Policy 参数 \(\theta\)，让它生成的轨迹获得更高的期望 Reward：

\[
\boxed{J(\theta)=\mathbb E_{\tau\sim\pi_\theta}[R(\tau)]}
\]

REINFORCE 的 Policy Gradient 为：

\[
\boxed{\nabla_\theta J(\theta)=\mathbb E_{\tau\sim\pi_\theta}\!\left[\sum_t G_t\nabla_\theta\log\pi_\theta(a_t\mid s_t)\right]}
\]

训练时把最大化目标写成最小化的 Loss（以下省略不影响理解的归一化系数）：

\[
\boxed{L_{\mathrm{REINFORCE}}(\theta)=-\sum_t G_t\log\pi_\theta(a_t\mid s_t)}
\]

其中，\(G_t\) 是 Rollout 后算出的 Return，\(s_t,a_t\) 是已经采到的状态和动作；真正需要求梯度的是当前 Policy \(\pi_\theta\)。

例如，某个 Token 的 \(G_t=2\)：

\[
L=-2\log\pi_\theta(a_t\mid s_t)
\]

最小化 Loss，就会倾向于提高这个 Token 的生成概率。

**训练流程： Rollout 100 条 → 计算 Return → 更新 Policy 一次 → 用新 Policy 重新 Rollout。**

这是因为更新后的 Policy 已经改变，旧数据不再严格服从当前 Policy 的采样分布。注意：**不是每生成一个 Token 就更新一次，而是通常收集一批完整轨迹再更新。**

<a id="origin-3409"></a>
#### 12.1.2 PPO：同一批 Rollout 可以更新多次

PPO 引入新旧 Policy 的动作概率比率：

\[
\boxed{r_t(\theta)=\frac{\pi_\theta(a_t\mid s_t)}{\pi_{\mathrm{old}}(a_t\mid s_t)}}
\]

再通过 Clip 限制过度的策略更新：

\[
\boxed{L^{\mathrm{CLIP}}(\theta)=\mathbb E_t\!\left[\min\!\left(r_t A_t,\ \operatorname{clip}(r_t,1-\epsilon,1+\epsilon)A_t\right)\right]}
\]

这是要**最大化**的目标；使用梯度下降训练时最小化它的负数。

例如，旧 Policy 给某个 Token 的概率为 \(0.2\)，\(A_t=2\)，\(\epsilon=0.2\)。

当当前概率提高到 \(0.3\) 时：

\[
r_t=\frac{0.3}{0.2}=1.5,\qquad
L^{\mathrm{CLIP}}_t=\min(1.5\times2,\ 1.2\times2)=2.4
\]

概率已经提高得较多了。对于这个正 Advantage 样本，继续增大概率不会再提高其裁剪目标，所以训练会受到约束。Clip **不是**对所有概率变化的硬性保证。

**训练流程：Rollout 100 条 → 第 1 轮更新 → 第 2 轮更新 → 第 3 轮更新 → 第 4 轮更新 → 再重新 Rollout。（轮数仅作示例。）** 

**PPO 的好处：**

- **提高样本利用率： 一批 Rollout 可以训练多轮，减少为了获得多次参数更新而反复采样的开销。**
- **提高训练稳定性：通过 Ratio + Clip 抑制过大的策略变化。**

注意：PPO 不保证总计算量更少，因为多轮反向传播本身也需要计算。

<a id="origin-3445"></a>
### 12.2 重要性采样的公式明明恒等，为什么旧 Rollout 不能一直用？

从数学上讲，重要性采样确实能把旧分布下的期望换成新分布下的期望：

\[
\boxed{\mathbb E_{x\sim p_{\mathrm{new}}}[f(x)]=\mathbb E_{x\sim p_{\mathrm{old}}}\!\left[\frac{p_{\mathrm{new}}(x)}{p_{\mathrm{old}}(x)}f(x)\right]}
\]

只要**新分布可能出现的样本，在旧分布下也有非零概率**，这个等式就成立。

**但公式恒等，不等于实际只有有限次采样时，估计值一定准确。**

<a id="origin-3457"></a>
#### 12.2.1 举一个只有两个动作的例子

假设：动作 A 的 Reward = 1，动作 B 的 Reward = 0。

- 旧 Policy：\(P_{\mathrm{old}}(A)=0.001\)。
- 新 Policy：\(P_{\mathrm{new}}(A)=0.5\)。

新 Policy 的真实期望 Reward 为：

\[
\mathbb E_{\mathrm{new}}[R]=0.5\times1+0.5\times0=\boxed{0.5}
\]

按照重要性采样公式，旧数据中 A 的权重应该是：

\[
\boxed{w(A)=\frac{0.5}{0.001}=500}
\]

**数学上没有问题：旧 Policy 采到 A 的概率小，但给 A 乘上 500 倍，就能还原新 Policy 的期望。**

然而，实际训练假设只采样 1000 次。那么一次 A 都没采到的概率为：

\[
P(\text{一次 A 都没有})=(1-0.001)^{1000}\approx\boxed{36.8\%}
\]

也就是说，**有约 36.8% 的概率，1000 条旧数据里面连一个 A 都没有！**

这时你就算知道 A 的权重应该乘 500，也没有用：**数据里根本没有 A，想乘也没东西可乘。**

**换句话说：如果旧 Rollout 中一次都没有采样到动作A，那么这批数据就无法直接提供针对动作A的训练信号，因此无法直接根据A的 Reward 判断应该如何优化A。**

对包含多个 Token 的完整轨迹，这个问题可能更严重。若按完整轨迹做精确重要性采样，权重是各步概率比率的连乘：

\[
\boxed{w(\tau)=\prod_t\frac{\pi_{\mathrm{new}}(a_t\mid s_t)}{\pi_{\mathrm{old}}(a_t\mid s_t)}}
\]

轨迹较长、新旧 Policy 差距较大时，权重可能非常不稳定。并且 PPO 实际使用的是**单步 Ratio + Clip 代理目标**，并不是对完整轨迹做上述精确修正。

**所以训练到一定程度，这个Rollout就不能用了，必须要重新采样。**

<a id="origin-3500"></a>
#### 12.2.2 最后记住两句话

**第一：REINFORCE 通常一批 Rollout 更新一次；PPO 让同一批数据可以有限地更新多次，提高样本效率，同时通过 Clip 增强稳定性。**

**第二：** 重要性采样的**期望等式本身没有错**；**问题在于实际只有有限样本。当旧 Policy 和新 Policy 差得很远时，旧数据可能一直采不到新 Policy 需要的重要样本，所以旧 Rollout 不能无限复用，PPO 需要定期重新采样。**
