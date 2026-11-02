# 61 · PPO 代码中的 GAE

<!-- LECTURE-CONTENT-START -->

> 本文只解释 `trainer/train_ppo.py` 中 GAE 的实际数据流：回答 token 如何与状态价值对齐、序列奖励如何变成逐 token 优势，以及这些结果怎样分别进入 Actor 和 Critic。

GAE 的通用公式、偏差与方差可以先看[《策略梯度》中的 GAE](../../%E8%AE%B2%E4%B9%89/%E5%BC%BA%E5%8C%96%E5%AD%A6%E4%B9%A0%E4%B8%8E%20PPO%20%E5%8E%9F%E7%90%86/s3503af2f-%E7%AD%96%E7%95%A5%E6%A2%AF%E5%BA%A6%E4%B8%8E%20Actor-Critic.md#origin-677)；标准环境中的 `done` 与 `last_value` 写法可以看 [PPO 讲义中的 GAE 计算](../../%E8%AE%B2%E4%B9%89/%E5%BC%BA%E5%8C%96%E5%AD%A6%E4%B9%A0%E4%B8%8E%20PPO%20%E5%8E%9F%E7%90%86/s41b0a574-PPO%20%E8%A3%81%E5%89%AA%E7%9B%AE%E6%A0%87%E4%B8%8E%E9%80%9A%E7%94%A8%E5%AE%9E%E7%8E%B0.md#origin-426)。这里关注大语言模型回答生成这一种具体轨迹。

## 1. 这段 GAE 接收什么

在 MiniMind 的 PPO 中，一条 prompt 生成一条 response。若 batch 大小为 `B`，batch 中补齐后的最大回答长度为 `R`，GAE 相关变量为：

| 变量 | 形状 | 含义 |
| --- | --- | --- |
| `rewards` | `[B]` | 奖励模型和规则奖励给整条回答的总分 |
| `resp_policy_mask` | `[B, R]` | 有效回答 token 为 1，结构性右侧补齐列和首个 EOS 之后的位置为 0 |
| `old_resp_values` | `[B, R]` | rollout 时 Critic 对每个回答动作之前状态的价值预测 |
| `token_rewards` | `[B, R]` | 将整条回答的总分放到最后一个有效 token 后得到的稀疏奖励 |
| `advantages` | `[B, R]` | GAE 得到的逐 token 优势；稍后会做 masked 标准化 |
| `returns` | `[B, R]` | Critic 的回归目标，由原始优势加旧价值构造 |

代码中的默认参数是：

```python
gamma = 1.0
lam = 0.95
```

完整数据流是：

```text
完整回答的总奖励 [B]
        |
        v
最后一个有效 token 上的稀疏奖励 [B,R]
        |
        v
TD residual -> 逆序 GAE -> raw advantages [B,R]
                         |                 |
                         |                 +-> masked 标准化 -> Actor
                         |
                         + old values -> returns -> Critic
```

## 2. token 与状态价值如何对齐

这是整段代码最容易发生一位偏移的地方。

设 prompt 为 $x$，回答 token 为 $y_0,y_1,\ldots,y_{L-1}$。生成第 $t$ 个回答 token 时：

$$
s_t=(x,y_0,\ldots,y_{t-1}),\qquad a_t=y_t
$$

因此：

$$
\log\pi(a_t\mid s_t)
$$

和


$$
V(s_t)
$$

必须取自同一个预测位置。`V(s_t)` 是“生成 $y_t$ 之前，当前前缀的价值”，不是 token $y_t$ 自身拥有一个价值。

为简化时间轴，先看一条在 `gen_out` 中没有左侧 PAD、prompt 长度为 3 的样本：

```text
gen_out 位置：  0    1    2     3    4     5     6    7
gen_out：      p0   p1   p2    51   52    EOS   PAD  PAD
回答内部 t：                   0    1     2     3    4
动作 a_t：                    51   52    EOS   PAD  PAD
logp_pos：                     2    3     4     5    6
```

语言模型位置 2 的输出分布预测位置 3 的 token `51`，所以第一个回答动作对应的预测位置是 `prompt_len - 1`。代码对每条样本构造：

```python
resp_idx = torch.arange(resp_labels.size(1), device=gen_out.device).unsqueeze(0)
logp_pos = prompt_lens.unsqueeze(1) - 1 + resp_idx
```

rollout 引擎返回的 `old_resp_logp` 已经按回答列排列。训练侧再用 `logp_pos` 从完整序列中取出同一批动作对应的 Critic 价值；更新阶段的当前 Actor 和参考模型 log-prob 也按这组位置提取：

```python
old_resp_logp = rollout_result.per_token_logps
old_resp_values = values_seq.gather(1, logp_pos) * resp_value_mask
```

Torch 后端的 `prompt_lens` 是输入张量中 completion 开始前的固定列数，包含左侧 PAD 占用的列；SGLang 后端先移除左侧 PAD，因此返回每条样本实际的 prompt 长度。两者都必须与各自返回的 `gen_out` 布局配套使用，不能混用索引。

对上面的例子：

| `t` | 动作 | 生成动作前的状态 | `logp_pos` | `old_resp_values[:, t]` |
| ---: | --- | --- | ---: | --- |
| 0 | `51` | `prompt` | 2 | $V(s_0)$ |
| 1 | `52` | `prompt + 51` | 3 | $V(s_1)$ |
| 2 | `EOS` | `prompt + 51 + 52` | 4 | $V(s_2)$ |

于是循环中的 `old_resp_values[:, t + 1]` 才对应 $V(s_{t+1})$。

## 3. EOS、PAD 与有效回答 mask

代码先读取 rollout 后端提供的结构性有效位置 mask，再查找第一个 EOS：

```python
resp_pad_mask = rollout_result.completion_mask.to(args.device).bool()
resp_lengths = resp_pad_mask.sum(dim=1)
valid_resp = resp_lengths > 0

eos_mask = resp_labels.eq(tokenizer.eos_token_id) & resp_pad_mask
has_eos = eos_mask.any(dim=1)
eos_pos = torch.argmax(eos_mask.int(), dim=1)

resp_lengths = torch.where(has_eos, eos_pos + 1, resp_lengths).long().clamp(min=1)
resp_policy_mask = ((resp_idx < resp_lengths.unsqueeze(1)) & resp_pad_mask).float()
resp_value_mask = resp_policy_mask.clone()
```

变量名 `resp_pad_mask` 容易让人以为它总是由 `token != PAD` 得到，实际语义由 `completion_mask` 决定。SGLang 对变长回答右补 PAD，并在这些列返回 0；当前 Torch 后端返回全 1，再由训练代码截到首个 EOS。因此最终应以 `resp_policy_mask` 为准。

首个 EOS 本身仍是 Actor 采取的一个动作，所以它参与策略损失和价值损失；EOS 后的位置不参与。

| 情况 | 有效位置 | 当前处理 |
| --- | --- | --- |
| 正常生成 EOS | 从首 token 到首个 EOS，包含 EOS | EOS 是最后一个有效动作 |
| EOS 后的 PAD、重复 EOS 或其他后缀 | 无效 | 最终 mask 为 0 |
| 未生成 EOS | 所有后端标记为真实的 response token | 最后一个返回 token 被当作轨迹末端 |
| rollout 返回零个 token | 没有有效位置 | `valid_resp=False`，不放奖励，损失分母用 `clamp(min=1)` 防止除零 |

当前实现要求每条回答的有效 token 构成一个连续前缀。后面的 GAE 循环没有逐步乘 mask，它能正确工作依赖的正是这个条件。

“返回零个 token”和“解码后的文本为空”并不相同。若模型第一个动作就是 EOS，跳过特殊 token 后文本看起来为空，但 EOS 仍是一个有效动作，`valid_resp=True`。

## 4. 将序列奖励放到末端

奖励模型评价的是完整回答，返回形状为 `[B]` 的序列级奖励。代码先创建全零的逐 token 奖励，再将总奖励放到最后一个有效位置：

```python
token_rewards = torch.zeros_like(old_resp_logp)
last_idx = resp_lengths - 1
token_rewards[
    torch.arange(B, device=args.device)[valid_resp],
    last_idx[valid_resp],
] += rewards[valid_resp]
```

例如：

```text
response：         [51, 52, EOS, PAD, PAD]
resp_policy_mask： [ 1,  1,   1,   0,   0]
sequence reward：  2.0
token_rewards：    [ 0,  0, 2.0,   0,   0]
```

把奖励写在 EOS 位置只是一种数组对齐方式。它表示“生成完整条回答后得到 2.0”，并不表示 EOS 这个 token 单独创造了 2.0 的奖励。

当前实现也没有把参考模型 KL 填入 `token_rewards`。KL 在更新 Actor 时单独加入 `policy_loss`，因此这里的 Critic 学习预测外部回答奖励，不包含 KL-shaped reward。KL 的具体计算见[《PPO 代码中的 KL 散度计算》](../../%E8%AE%B2%E4%B9%89/PPO%20%E9%87%87%E6%A0%B7%E4%B8%8E%E8%AE%AD%E7%BB%83/s0c014541-PPO%20%E4%B8%AD%E7%9A%84%E4%B8%A4%E7%B1%BB%20KL%20%E6%95%A3%E5%BA%A6.md)。

## 5. 代码怎样从后向前计算 GAE

标准 GAE 可以带一个 nonterminal 指示量 $m_t$：

$$
\delta_t
=
r_t+\gamma m_tV(s_{t+1})-V(s_t)
$$

$$
A_t
=
\delta_t+\gamma\lambda m_tA_{t+1}
$$

真正终止后 $m_t=0$，不再 bootstrap，也不再把后续优势传回来。

项目代码为：

```python
gen_len = old_resp_values.size(1)
lastgaelam = torch.zeros(B, device=args.device)
advs_rev = []

for t in reversed(range(gen_len)):
    nv = old_resp_values[:, t + 1] if t < gen_len - 1 else 0.0
    delta = token_rewards[:, t] + args.gamma * nv - old_resp_values[:, t]
    lastgaelam = delta + args.gamma * args.lam * lastgaelam
    advs_rev.append(lastgaelam)

advantages = torch.stack(advs_rev[::-1], dim=1)
returns = advantages + old_resp_values
```

各变量对应关系为：

| 代码变量 | 数学含义 |
| --- | --- |
| `old_resp_values[:, t]` | $V(s_t)$ |
| `nv` | $V(s_{t+1})$，轨迹末端取 0 |
| `delta` | 一步 TD residual $\delta_t$ |
| `lastgaelam` | 当前的原始 GAE 优势 $A_t$ |
| `advs_rev` | 按 $T-1,T-2,\ldots,0$ 收集的优势列表 |
| `advs_rev[::-1]` | 恢复为正常时间顺序 |

`lastgaelam` 的形状是 `[B]`，所以循环虽然沿时间维逐步执行，却同时处理 batch 中的全部样本。

代码没有显式写 `done` 或 $m_t$。对正常生成 EOS 的样本，它依靠以下事实得到等价的终止效果：

1. EOS 后的 `old_resp_values` 已经被 `resp_value_mask` 置为 0；
2. EOS 后的 `token_rewards` 也是 0；
3. 逆序循环从全零的 `lastgaelam` 开始。

因此无效后缀始终得到 0；循环到 EOS 时，`nv=0`，相当于 terminal 的 $m_t=0$。

## 6. 用一条回答完整手算

继续使用前面的短回答。设：

```text
token_rewards：   [0,   0,   2.0, 0, 0]
old values：      [0.2, 0.4, 0.3, 0, 0]
gamma：           1.0
lambda：          0.95
```

从右向左计算：

| `t` | 动作 | $r_t$ | $V_t$ | $V_{t+1}$ | $\delta_t=r_t+V_{t+1}-V_t$ | $A_t=\delta_t+0.95A_{t+1}$ | $A_t+V_t$ |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | PAD | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 | PAD | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | EOS | 2.0 | 0.3 | 0 | 1.7 | 1.7 | 2.0 |
| 1 | `52` | 0 | 0.4 | 0.3 | -0.1 | 1.515 | 1.915 |
| 0 | `51` | 0 | 0.2 | 0.4 | 0.2 | 1.63925 | 1.83925 |

最终得到：

```text
deltas：         [0.2, -0.1, 1.7, 0, 0]
raw advantages： [1.63925, 1.515, 1.7, 0, 0]
returns：        [1.83925, 1.915, 2.0, 0, 0]
```

第一项也可以直接展开检查：

$$
A_0
=
0.2+0.95(-0.1)+0.95^2(1.7)
=
1.63925
$$

`returns` 没有全部等于 2.0，不是计算错误。这里 $\lambda=0.95$，GAE return 混合了不同步数的 bootstrap 估计；当 $\gamma=1$、$\lambda=1$ 且末端真实终止时，这个例子中的 return 才会全部回到 2.0。

原始优势表示后续结果相对 Critic 基线预期好多少。它是下游 TD residual 的加权和，不是某个 token 对最终奖励的因果贡献证明。

## 7. raw advantage、return 与标准化优势

顺序非常重要：代码先用原始优势构造 Critic 目标，再覆盖 `advantages` 变量为标准化结果。

```python
# 此时 advantages 还是 raw advantages
returns = advantages + old_resp_values

adv_mean = (
    advantages * resp_policy_mask
).sum() / resp_policy_mask.sum().clamp(min=1)

adv_var = (
    (advantages - adv_mean) ** 2 * resp_policy_mask
).sum() / resp_policy_mask.sum().clamp(min=1)

advantages = (
    (advantages - adv_mean)
    * torch.rsqrt(adv_var + 1e-8)
    * resp_policy_mask
)
```

三者不能混用：

| 量 | 是否标准化 | 用途 |
| --- | --- | --- |
| raw advantage | 否 | 构造 `returns`，也是分析 GAE 数值时应查看的量 |
| `returns` | 否 | Critic 的回归目标 |
| 覆盖后的 `advantages` | 是 | Actor 的 PPO 策略损失权重 |

均值和方差只统计当前 rank 的 batch 中所有有效 token，PAD 不参与。每个 token 权重相同，因此较长回答会向统计量贡献更多位置。

标准化保持数值的相对顺序，但可能改变单个位置的正负号。例如原始优势 `[1, 2]` 都为正，减去均值后会变成 `[-0.5, 0.5]`。所以 Actor 最终看到的正负号表示“高于或低于当前 batch 的有效 token 平均水平”，不能再直接解释成原始 GAE 是否大于 0。

## 8. EOS 终止与长度截断并不相同

当前实现对两种情况都令最后的 `nv=0`：

```python
nv = old_resp_values[:, t + 1] if t < gen_len - 1 else 0.0
```

但二者在标准强化学习语义中不同：

| 轨迹结束原因 | 标准处理 | 当前代码 |
| --- | --- | --- |
| 生成 EOS，任务真正终止 | $V(s_{T})=0$ | 置 0，处理正确 |
| 没有 EOS，后端停止返回 token | 若任务仍可继续，应使用 $V(s_T)$ bootstrap | 仍置 0，按终止处理 |

无 EOS 最常见的原因是达到 `max_gen_len`，也可能来自后端的其他停止条件。当前实现相当于把这种回答边界也定义为任务的硬终点。如果它只是为了控制采样成本的 time limit，这种处理会带来截断偏差。要支持标准的 time-limit bootstrap，需要让 rollout 结果区分 `terminated` 和 `truncated`，并为截断样本额外保留最后状态的 $V(s_T)$。

这也是项目循环不能直接复制到一般并行环境 PPO 的原因。通用环境还可能在一个固定长度 buffer 中包含多个 episode，必须显式使用 `done/nonterminal` mask。

## 9. 为什么默认 `gamma=1.0`

通用 PPO 示例常见 `gamma=0.99`，项目默认使用：

```python
parser.add_argument("--gamma", type=float, default=1.0)
parser.add_argument("--lam", type=float, default=0.95)
```

在有限长度的文本生成中，`gamma=1.0` 表示不因为 token 离回答末尾更远，就额外折扣最终回答奖励。但这不表示所有未来信息权重相同：GAE 中第 $l$ 个未来 TD residual 的权重仍为

$$
(\gamma\lambda)^l=0.95^l
$$

若 Critic 的所有价值预测暂时都是 0，且只有末端奖励 $R$，则更早位置的原始优势约为：

$$
A_t=0.95^{T-1-t}R
$$

所以 `gamma` 控制任务回报的时间折扣，`lambda` 控制多个 TD residual 在优势估计中的混合；两者不能当作同一个参数理解。

## 10. GAE 结果最终流向哪里

更新阶段重新计算当前 Actor 和 Critic 的输出，但 rollout 时保存的 `old_resp_logp`、`old_resp_values`、`advantages` 和 `returns` 在这一批 PPO 更新中保持固定。

Actor 使用标准化后的优势：

```python
policy_loss = (
    torch.max(
        -advantages[inds] * ratio,
        -advantages[inds] * torch.clamp(
            ratio, 1.0 - args.clip_epsilon, 1.0 + args.clip_epsilon
        ),
    )
    * resp_policy_mask[inds]
).sum() / resp_policy_mask[inds].sum().clamp(min=1)
```

Critic 使用未标准化的 `returns`。忽略 value clipping 时，核心误差是：

```python
value_error = mb_resp_values - returns[inds]
```

实际代码还对 value 更新做了 clipping，但无论是否 clipping，回归目标都是同一个 `returns`。

可以把两条路径记成：

```text
raw advantages --标准化--> Actor：决定哪些已采样 token 相对更值得提高概率
       |
       + old values ------> Critic：学习逼近 GAE return

reference KL -------------> 只在 Actor policy loss 中单独加入
```

## 11. 调试时检查什么

阅读或修改这段代码时，可以先检查这些不变量：

1. `old_resp_logp`、`old_resp_values`、`token_rewards`、`advantages`、`returns` 和两个 response mask 的形状都应为 `[B, R]`。
2. `logp_pos[:, t]` 必须同时对齐动作 $a_t$ 的 log-prob 和动作发生前状态的 $V(s_t)$。
3. 每条有效样本只有最后一个有效位置收到序列奖励；对每个有效样本 `b`，应有 `token_rewards[b].sum() == rewards[b]`。
4. 对正常 EOS 样本，EOS 后的 value、reward、raw advantage 和 return 都应为 0。
5. `returns` 必须在优势标准化之前满足 `returns = raw_advantages + old_resp_values`。
6. 若有效位置不止一个，且原方差相对 `1e-8` 足够大，标准化后有效优势的 masked 均值应接近 0、方差应接近 1；原方差很小时，epsilon 会使新方差明显小于 1。
7. 无 EOS 样本是否应当 bootstrap 必须是明确的任务选择，不能只由数组到达末列偶然决定。

这段实现的核心不是“把奖励复制给每个 token”，而是先让 Critic 给出每个动作前状态的基线，再用一串 TD residual 逆序修正这条基线。理解了时间对齐、终止语义，以及 raw advantage 与标准化 advantage 的区别，代码里的 GAE 就能和公式逐项对应起来。
