# PPO 训练完整数值例子


---

<a id="origin-5"></a>
## 1. 先不要看代码：这个函数到底干什么？

整个 `ppo_train_epoch()` 可以先压缩成这样一条主线：

```text
一批 Prompt
    ↓
Actor 生成回答
    ↓
保存生成时 Actor 的 old_log_prob
    ↓
Reward Model 给整条回答打分
    ↓
Critic 给回答过程中每一步预测 Value
    ↓
算 GAE
    ↓
得到：
advantages
returns
    ↓
固定住这一批数据
    ↓
重新让“当前 Actor / 当前 Critic”前向
    ↓
Actor：
new_log_prob
↓
new / old
↓
PPO Clip Loss

Critic：
new_value
↓
和 returns 比较
↓
Value Loss
    ↓
总 Loss
    ↓
backward
    ↓
更新 Actor + Critic
```

最关键的一句话：

> **Rollout 阶段负责“出题并制作训练标签”；Update 阶段负责“根据这些固定标签训练模型”。**

所以这里实际上有两个阶段：

```text
阶段 A：Rollout + 制作训练目标
阶段 B：PPO Update
```

不是：

```text
生成一个回答
→ 得一个 reward
→ 直接拿 reward 做 loss
```

而是中间还隔着：

```text
old_logp
old_value
GAE
advantages
returns
```

---

<a id="origin-82"></a>
## 2. 整篇讲义只用这一组数据

为了避免一会儿一个例子，我们从头到尾固定：

```text
Batch Size B = 2
Prompt 最大宽度 P = 3
Response 最大宽度 R = 3

PAD = 0
EOS = 2
```

PPO 参数采用代码默认值：

```text
gamma             = 1.0
lambda            = 0.95

clip_epsilon       = 0.2
cliprange_value    = 0.2

vf_coef            = 0.5
kl_coef            = 0.02

ppo_update_iters   = 2
mini_batch_size    = 2

accumulation_steps = 1
early_stop_kl      = 0.25
```

假设两条 Prompt 分词后是：

```text
Prompt A：

真实 token：
[11, 12]

左 PAD 后：
[0, 11, 12]


Prompt B：

[13, 14, 15]
```

因此：

```python
enc.input_ids = [
    [ 0, 11, 12],
    [13, 14, 15]
]
```

对应：

```python
attention_mask = [
    [0, 1, 1],
    [1, 1, 1]
]
```

---

<a id="origin-151"></a>
## 3. 第一步：Actor 生成回答

现在 Actor 对两条 Prompt 分别生成回答。

假设：

```text
Prompt A：

21 → EOS

Prompt B：

31 → 32 → EOS
```

也就是：

```text
A response = [21, 2]
B response = [31, 32, 2]
```

但这里的生成函数会把已经结束的序列继续用 EOS 补齐，所以最终：

```python
completion_ids = [
    [21,  2, 2],
    [31, 32, 2]
]
```

注意第一条：

```text
21, EOS, EOS
        ↑
最后这个 EOS 只是补齐出来的
不能参加 PPO
```

于是完整序列：

```python
gen_out = [
    [ 0, 11, 12, 21,  2, 2],
    [13, 14, 15, 31, 32, 2]
]
```

画出来：

```text
                 Prompt        Response
              ┌──────────┐   ┌───────────┐
Sample A      0  11  12     21   2    2
                                   ↑    ↑
                                 EOS   补齐EOS

Sample B     13  14  15     31  32    2
                                        ↑
                                       EOS
```

Rollout 的同时还保存了：

```python
old_resp_logp
```

假设为：

```python
old_resp_logp = [
    [-0.7, -0.2, -2.0],
    [-0.4, -0.8, -0.1]
]
```

意思是：

```text
Prompt A：

log π_old(21)  = -0.7
log π_old(EOS) = -0.2

第三个 EOS 后面会被 mask，
所以 -2.0 最终没用。


Prompt B：

log π_old(31)  = -0.4
log π_old(32)  = -0.8
log π_old(EOS) = -0.1
```

这里的：

\[
\pi_{\text{old}}
\]

不是另外保存了一整个 Old Model。

在这个实现中，真正固定下来的是：

```text
这一批回答生成时的 old_resp_logp
```

后面 Actor 参数即使变了：

```python
old_resp_logp
```

也不会变。

---

<a id="origin-273"></a>
## 4. 第二步：先解决整个函数最容易糊涂的问题——位置怎么对应？

这是理解这段代码最重要的一步。

完整序列：

```text
位置：

  0   1   2   3   4   5
  ↓   ↓   ↓   ↓   ↓   ↓

  0  11  12  21   2   2
```

Transformer 是：

```text
位置 0 的输出 → 预测位置 1
位置 1 的输出 → 预测位置 2
位置 2 的输出 → 预测位置 3
位置 3 的输出 → 预测位置 4
位置 4 的输出 → 预测位置 5
```

所以：

```text
12 后面的 hidden state
        ↓
预测 21

21 后面的 hidden state
        ↓
预测 EOS
```

因此回答虽然位于：

```text
完整序列位置：

3, 4, 5
```

但是预测这些回答 token 的 logits / value 应该取：

```text
2, 3, 4
```

所以代码：

```python
resp_idx = [0, 1, 2]

logp_pos = prompt_lens - 1 + resp_idx
```

这里：

```text
prompt_lens = 3
```

于是：

```text
3 - 1 + [0,1,2]

= [2,3,4]
```

两条样本都是：

```python
logp_pos = [
    [2,3,4],
    [2,3,4]
]
```

这三个位置的意义是：

```text
位置 2：

Prompt
... 12
    ↓
预测回答第 1 个 token


位置 3：

... 12 21
       ↓
预测回答第 2 个 token


位置 4：

... 21 EOS
        ↓
预测回答第 3 个 token
```

所以以后你看到：

```python
.gather(1, logp_pos)
```

就应该直接翻译成：

> **“从完整序列中，把负责预测 Response token 的那些位置拿出来。”**

---

<a id="origin-392"></a>
## 5. 第三步：把补齐 EOS 排除掉

刚才：

```python
completion_ids = [
    [21,  2, 2],
    [31, 32, 2]
]
```

Rollout 后端最开始给：

```python
completion_mask = [
    [1,1,1],
    [1,1,1]
]
```

但是：

```text
第一条最后一个 EOS
```

实际上是生成完成以后为了补齐长度加进去的。

所以代码重新找：

```python
eos_mask
```

得到：

```python
[
    [False, True, True],
    [False,False, True]
]
```

然后找**第一个 EOS**：

```text
A：

第一个 EOS 的下标 = 1

因此有效 Response 长度：

1 + 1 = 2


B：

第一个 EOS 的下标 = 2

有效 Response 长度：

2 + 1 = 3
```

最终：

```python
resp_lengths = [2,3]
```

于是：

```python
resp_policy_mask = [
    [1,1,0],
    [1,1,1]
]
```

也就是：

```text
A：

21   EOS   补齐EOS
1     1      0


B：

31    32    EOS
1      1     1
```

从现在开始，一共有：

\[
2+3=5
\]

个有效 PPO token。

**后面所有 Actor Loss、Critic Loss、KL、Advantage 统计，本质上都只看这 5 个位置。**

---

<a id="origin-498"></a>
## 6. 第四步：Reward Model 给整个回答打分

假设经过：

```python
calculate_rewards(...)
```

得到：

```python
rewards = [1.0, 2.0]
```

意思是：

```text
回答 A 总奖励 = 1

回答 B 总奖励 = 2
```

注意：

这个 Reward 是：

```text
一整条回答一个 Reward
```

而不是：

```text
每个 token 一个 Reward
```

所以现在还不能直接做 PPO。

代码先创建：

```python
token_rewards = [
    [0,0,0],
    [0,0,0]
]
```

然后把整条回答的 Reward 放到**最后一个有效 token**：

```python
A 最后一个有效 token 下标 = 1
B 最后一个有效 token 下标 = 2
```

于是：

```python
token_rewards = [
    [0, 1, 0],
    [0, 0, 2]
]
```

也就是：

```text
A：

21       EOS
↓         ↓
0         1


B：

31       32       EOS
↓         ↓         ↓
0         0         2
```

这一步非常重要：

> Reward Model 只负责告诉我们：“这一整条回答最后值几分。”

至于：

> “前面的 token 到底应该分到多少功劳？”

接下来交给：

```text
Critic + GAE
```

---

<a id="origin-594"></a>
## 7. 第五步：Critic 先评价生成过程中的每一个状态

Critic 对整个：

```python
gen_out
```

前向。

假设完整输出：

```python
values_seq = [
    [0, 0, 0.2, 0.4, 0.7, 0],
    [0, 0, 0.1, 0.3, 0.5, 0]
]
```

我们不需要全部位置。

仍然通过：

```python
logp_pos = [2,3,4]
```

取出与回答动作对应的状态 Value：

```python
[
    [0.2, 0.4, 0.7],
    [0.1, 0.3, 0.5]
]
```

然后乘：

```python
resp_value_mask
```

得到：

```python
old_resp_values = [
    [0.2, 0.4, 0.0],
    [0.1, 0.3, 0.5]
]
```

这里一定要正确理解 `V`。

例如：

```text
Prompt A：

... 12
```

Critic 给：

\[
V=0.2
\]

它的意思不是：

> token 21 值 0.2 分。

而是：

> **站在即将生成 21 的这个状态，Critic 预计从这里继续生成下去，未来总收益大概是 0.2。**

然后生成 21 后：

```text
... 12 21
```

Critic 又说：

\[
V=0.4
\]

意思是：

> 现在已经生成了 21，从这个新状态往后看，未来预计还能得到 0.4 的收益。

这就是：

\[
V(s_t)
\]

---

<a id="origin-693"></a>
## 8. 第六步：现在终于可以算 GAE 了

代码：

\[
\delta_t
=
r_t+\gamma V_{t+1}-V_t
\]

然后：

\[
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
\]

这里：

```text
gamma  = 1
lambda = 0.95
```

一定要注意：

> GAE 是**从后向前算**的。

因为：

\[
A_t
\]

依赖：

\[
A_{t+1}
\]

所以顺序：

```text
最后一个 token
      ↓
倒数第二个
      ↓
倒数第三个
```

---

<a id="origin-748"></a>
## 9. 先完整手算回答 A

回答 A：

```text
token：

21      EOS      无效
```

对应：

```text
reward：

0        1        0
```

Value：

```text
0.2      0.4      0
```

Mask：

```text
1        1        0
```

---

<a id="origin-780"></a>
### 9.1 从最后一个位置 t=2 开始

这是无效补齐位置。

```text
r₂ = 0
V₂ = 0
V₃ = 0
```

所以：

\[
\delta_2
=
0+0-0
=
0
\]

最右边之后：

\[
A_3=0
\]

因此：

\[
A_2
=
0+0.95\times0
=
0
\]

得到：

```text
A₂ = 0
```

---

<a id="origin-824"></a>
## 10. t=1：EOS

现在：

```text
r₁ = 1
V₁ = 0.4
V₂ = 0
```

于是：

\[
\delta_1
=
1+1\times0-0.4
\]

\[
=0.6
\]

再计算：

\[
A_1
=
0.6
+
1\times0.95\times0
\]

所以：

\[
\boxed{A_1=0.6}
\]

---

<a id="origin-864"></a>
## 11. t=0：token 21

现在：

```text
r₀ = 0

V₀ = 0.2
V₁ = 0.4
```

所以：

\[
\delta_0
=
0+0.4-0.2
\]

\[
=0.2
\]

然后：

\[
A_0
=
0.2
+
0.95\times0.6
\]

\[
=
0.2+0.57
\]

\[
\boxed{A_0=0.77}
\]

因此第一条回答：

```python
advantages_A = [
    0.77,
    0.60,
    0
]
```

这就是 GAE 做的事情：

```text
最终 EOS 得到了 Reward=1

            ↓ GAE 向前传

21 也获得了 0.77 的 Advantage
```

也就是说：

> 虽然 Reward Model 只在回答结束以后给了一个最终分，但 GAE 把这个奖励信号向前传播给了之前的 token。

---

<a id="origin-932"></a>
## 12. 再算回答 B

回答 B：

```text
31      32      EOS
```

Reward：

```text
0       0        2
```

Value：

```text
0.1     0.3      0.5
```

---

<a id="origin-954"></a>
### 12.1 t=2：EOS

\[
\delta_2
=
2-0.5
=
1.5
\]

所以：

\[
A_2=1.5
\]

---

<a id="origin-972"></a>
### 12.2 t=1：token 32

\[
\delta_1
=
0+0.5-0.3
=
0.2
\]

\[
A_1
=
0.2+0.95\times1.5
\]

\[
=
0.2+1.425
\]

\[
\boxed{A_1=1.625}
\]

---

<a id="origin-999"></a>
### 12.3 t=0：token 31

\[
\delta_0
=
0+0.3-0.1
=
0.2
\]

\[
A_0
=
0.2+0.95\times1.625
\]

\[
=
0.2+1.54375
\]

\[
\boxed{A_0=1.74375}
\]

所以：

```python
advantages_B = [
    1.74375,
    1.625,
    1.5
]
```

最终整个 Batch：

```python
advantages = [
    [0.77000, 0.600, 0.0],
    [1.74375, 1.625, 1.5]
]
```

---

<a id="origin-1045"></a>
## 13. 第七步：Critic 的训练 Target 从哪里来？

接下来这句极其重要：

```python
returns = advantages + old_resp_values
```

注意！

这里使用的是：

> **还没有标准化的原始 Advantage。**

第一条：

\[
0.77+0.2=0.97
\]

\[
0.6+0.4=1.0
\]

于是：

```text
returns_A = [0.97, 1.0, 0]
```

第二条：

\[
1.74375+0.1
=
1.84375
\]

\[
1.625+0.3
=
1.925
\]

\[
1.5+0.5
=
2.0
\]

于是：

```text
returns_B = [
    1.84375,
    1.925,
    2.0
]
```

最终：

```python
returns = [
    [0.97000, 1.000, 0],
    [1.84375, 1.925, 2.0]
]
```

这就是稍后 Critic 要学习的目标。

即：

```text
Critic 当前预测：

0.2
0.4
...

        ↓

训练以后希望靠近：

0.97
1.00
...
```

所以在这份代码里：

```text
returns
```

不是简单把最后那个 Reward=1/2 原封不动复制过来。

它是：

\[
\boxed{
R_t^{target}=V_t^{old}+A_t^{GAE}
}
\]

可以把它理解成：

> **GAE 构造出来的、更适合训练 Critic 的 Value Target。**

---

<a id="origin-1156"></a>
## 14. 第八步：为什么 Advantage 后面还要标准化？

现在有效位置共有 5 个：

```text
0.77
0.60
1.74375
1.625
1.5
```

平均值：

\[
\mu
=
\frac{
0.77+0.60+1.74375+1.625+1.5
}{5}
\]

\[
=
1.24775
\]

方差：

\[
\sigma^2
\approx
0.21995775
\]

标准差：

\[
\sigma
\approx
0.468997
\]

然后：

\[
A'_t
=
\frac{A_t-\mu}{\sigma}
\]

得到：

```python
advantages ≈ [
    [-1.0187, -1.3811, 0],
    [ 1.0576,  0.8044, 0.5379]
]
```

这里有一个需要注意的现象。

原来第一条：

```text
0.77
0.60
```

明明都是正数。

标准化以后变成：

```text
-1.0187
-1.3811
```

为什么？

因为它们虽然：

```text
绝对意义上 > 0
```

但：

```text
低于本 Batch 的平均 Advantage
```

所以标准化以后变成负数。

因此后面的 PPO Actor 可以理解成：

```text
第二条回答明显比 Batch 平均水平好
→ 增加这些动作概率

第一条回答相对 Batch 平均水平差
→ 降低这些动作概率
```

而 `returns` 不会被这个操作改变。

这是为什么代码一定是：

```python
returns = advantages + old_values

# 之后

advantages = normalize(advantages)
```

而不是先 normalize 再计算 returns。

---

<a id="origin-1276"></a>
## 15. 到这里，Rollout 阶段彻底结束

现在我们手里已经有一套**固定训练数据**：

```text
① gen_out

[
 [0,11,12,21, 2,2],
 [13,14,15,31,32,2]
]


② old_resp_logp

[
 [-0.7,-0.2,-2.0],
 [-0.4,-0.8,-0.1]
]


③ mask

[
 [1,1,0],
 [1,1,1]
]


④ old_value

[
 [0.2,0.4,0],
 [0.1,0.3,0.5]
]


⑤ standardized advantages

[
 [-1.0187,-1.3811,0],
 [ 1.0576, 0.8044,0.5379]
]


⑥ returns

[
 [0.97,1.00,0],
 [1.84375,1.925,2.0]
]
```

从现在开始：

```text
old_logp 不变
old_value 不变
advantages 不变
returns 不变
token 序列也不变
```

然后才开始真正训练。

这就是：

```text
PPO Update Stage
```

---

<a id="origin-1349"></a>
## 16. 第九步：为什么同一批数据要训练好几遍？

代码：

```python
for ppo_epoch in range(args.ppo_update_iters):
```

默认：

```text
ppo_update_iters = 2
```

也就是说：

```text
这批回答只生成一次
```

但是可以：

```text
拿它训练 Actor / Critic 两遍
```

结构其实是：

```text
DataLoader 外层：

第 1 批 Prompt
│
├─ Rollout 一次
│
├─ 算 Reward / GAE / Return 一次
│
│
├─ PPO Update Epoch 1
│
│   └─ mini-batch 更新
│
└─ PPO Update Epoch 2
    └─ mini-batch 更新


然后才：

第 2 批 Prompt
```

所以千万别把：

```text
PPO Epoch
```

理解成：

```text
重新 generate 一遍
```

它没有重新生成。

它是在反复利用：

```text
同一个 rollout
```

---

<a id="origin-1422"></a>
## 17. 第一次 PPO Update 开始时，new 和 old 是什么关系？

Rollout 刚刚结束，而且 Actor 还没有执行：

```python
optimizer.step()
```

因此理论上：

\[
\pi_{\text{new}}
=
\pi_{\text{old}}
\]

所以：

\[
\frac{\pi_{\text{new}}}{\pi_{\text{old}}}
\approx1
\]

也就是：

```text
第一次 update 的第一次 forward：

ratio ≈ 1
```

第一次：

```python
optimizer.step()
```

以后 Actor 参数改变。

但：

```python
old_resp_logp
```

还是 rollout 时保存的那些值。

所以第二次 PPO update 时：

```text
new policy
```

已经改变了：

```text
new ≠ old
```

这个时候 ratio 的意义就充分体现出来了。

---

<a id="origin-1485"></a>
## 18. 下面假设我们已经进行过一次更新

为了真正看到 PPO Clip 的作用，我们假设第二轮 PPO Update 时，当前 Actor 对这些 token 算出的：

```python
new_logp
```

已经变成：

```python
new_resp_logp = [
    [-0.55, -0.45, 任意],
    [-0.50, -0.55, -0.25]
]
```

而 rollout 时固定的：

```python
old_resp_logp = [
    [-0.70, -0.20, -2.0],
    [-0.40, -0.80, -0.10]
]
```

---

<a id="origin-1513"></a>
## 19. 第十步：计算 log_ratio

公式：

\[
\log r_t
=
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
\]

第一条：

```text
token 21：

-0.55 - (-0.70)
= +0.15


EOS：

-0.45 - (-0.20)
= -0.25
```

第二条：

```text
31：

-0.50 - (-0.40)
= -0.10


32：

-0.55 - (-0.80)
= +0.25


EOS：

-0.25 - (-0.10)
= -0.15
```

所以：

```python
log_ratio = [
    [ 0.15, -0.25, 0],
    [-0.10,  0.25,-0.15]
]
```

---

<a id="origin-1572"></a>
## 20. 第十一步：真正的 ratio

代码：

```python
ratio = torch.exp(log_ratio)
```

所以：

\[
r_t
=
e^{\log\pi_{new}-\log\pi_{old}}
\]

即：

\[
r_t
=
\frac{
\pi_{new}
}{
\pi_{old}
}
\]

计算：

```text
e^0.15  ≈ 1.1618

e^-0.25 ≈ 0.7788

e^-0.10 ≈ 0.9048

e^0.25  ≈ 1.2840

e^-0.15 ≈ 0.8607
```

因此：

```python
ratio ≈ [
    [1.1618, 0.7788, 0],
    [0.9048, 1.2840, 0.8607]
]
```

含义例如：

```text
ratio = 1.284
```

表示：

> 当前 Actor 生成这个已经采样过的 token 的概率，大约变成原来的 1.284 倍。

而：

```text
ratio = 0.7788
```

表示：

> 当前概率只剩原来的 77.88%。

---

<a id="origin-1645"></a>
## 21. Advantage 和 Ratio 现在终于碰到一起了

我们的标准化 Advantage：

```python
A = [
    [-1.0187, -1.3811, 0],
    [ 1.0576,  0.8044, 0.5379]
]
```

所以：

```text
Sample A：

21：
A = -1.0187

EOS：
A = -1.3811
```

都小于零。

意思是：

> 这些动作相对这批样本平均水平不好，希望降低它们的概率。

而 Sample B：

```text
31：
A = +1.0576

32：
A = +0.8044

EOS：
A = +0.5379
```

意味着：

> 希望增加这些动作的概率。

于是 Actor 学习的最核心逻辑就是：

```text
A > 0
→ 提高动作概率

A < 0
→ 降低动作概率
```

---

<a id="origin-1703"></a>
## 22. 但为什么还需要 PPO Clip？

因为如果完全按：

\[
A_t r_t
\]

更新：

```text
好的动作
→ 概率可能一下提高十倍

坏的动作
→ 概率可能一下跌到非常低
```

训练会非常不稳定。

所以：

```text
clip_epsilon = 0.2
```

规定一个区间：

\[
[0.8,1.2]
\]

不是说：

> ratio 永远不能超过这个范围。

而是：

> **当变化已经太大以后，不再通过 PPO 主目标继续奖励这种过度变化。**

---

<a id="origin-1745"></a>
## 23. 逐 token 手算 Policy Loss

代码为了用梯度下降，写的是负目标：

\[
L_t
=
\max
\left(
-A_t r_t,
-A_t\operatorname{clip}(r_t,0.8,1.2)
\right)
\]

下面一个一个算。

---

<a id="origin-1763"></a>
### 23.1 Token A1：21

```text
Advantage = -1.0187

ratio = 1.1618
```

ratio 在：

```text
0.8 ~ 1.2
```

之内，不需要 Clip。

所以：

\[
-A r
=
-(-1.0187)\times1.1618
\]

约：

\[
1.1835
\]

这是一个正 Loss。

因为：

```text
这是一个负 Advantage 动作

但当前模型反而把它的概率提高到了 1.1618 倍
```

方向错了。

---

<a id="origin-1807"></a>
## 24. Token A2：EOS

```text
A = -1.3811

ratio = 0.7788
```

它是一个坏动作。

降低它的概率本来是对的。

但已经：

```text
0.7788 < 0.8
```

降得有一点过头。

原始目标：

\[
-(-1.3811)\times0.7788
\]

约：

\[
1.0756
\]

Clip 后：

\[
r_{clip}=0.8
\]

所以：

\[
-(-1.3811)\times0.8
\]

约：

\[
1.1049
\]

代码取：

\[
\max(1.0756,1.1049)
\]

因此：

\[
\boxed{1.1049}
\]

也就是说：

> 虽然这个动作确实应该降低概率，但降低到 0.8 以下以后，PPO 不希望继续猛烈推动。

---

<a id="origin-1875"></a>
## 25. Token B1：31

```text
A = +1.0576

ratio = 0.9048
```

这是一个好动作。

可是当前概率反而降低了。

Loss：

\[
-1.0576\times0.9048
\]

约：

\[
-0.9569
\]

负 Loss 完全没有问题。

因为我们是在：

```text
最小化负的收益目标
```

---

<a id="origin-1909"></a>
## 26. Token B2：32

```text
A = +0.8044

ratio = 1.2840
```

这是一个好动作。

提高概率：

```text
方向正确
```

但：

```text
1.284 > 1.2
```

提高得太猛。

原始：

\[
-0.8044\times1.284
\]

约：

\[
-1.0328
\]

Clip 后：

\[
-0.8044\times1.2
\]

约：

\[
-0.9653
\]

取最大值：

\[
\boxed{-0.9653}
\]

为什么取：

```text
-0.9653
```

而不是：

```text
-1.0328
```

因为如果使用 -1.0328：

> 模型继续把概率推得更高，还会得到更多“好处”。

Clip 的目的就是：

> 你已经提高得够多了，超过 1.2 的部分不再给额外奖励。

---

<a id="origin-1985"></a>
## 27. Token B3：EOS

```text
A = +0.5379

ratio = 0.8607
```

在 Clip 范围里。

得到：

\[
-0.5379\times0.8607
\approx
-0.4629
\]

---

<a id="origin-2005"></a>
## 28. 所以整个 PPO 主 Policy Loss

五个有效 token：

```text
+1.1835
+1.1049
-0.9569
-0.9653
-0.4629
```

平均：

\[
L_{\text{PPO-core}}
\approx
-0.01934
\]

所以：

```text
policy core loss ≈ -0.01934
```

---

<a id="origin-2033"></a>
## 29. `clipfrac` 又是什么意思？

当前 5 个 ratio：

```text
1.1618
0.7788
0.9048
1.2840
0.8607
```

超出：

```text
[0.8,1.2]
```

的有：

```text
0.7788
1.2840
```

一共：

```text
2 个
```

所以：

\[
clipfrac
=
\frac25
=
0.4
\]

意思是：

> 当前 40% 的有效 token，其新旧概率比例已经跑出了 PPO 的 Clip 范围。

它主要是训练监控指标。

---

<a id="origin-2082"></a>
## 30. `approx_kl` 是干什么的？

代码还有：

\[
\text{approx\_kl}
=
\frac12
E[
(\log r_t)^2
]
\]

我们的有效 `log_ratio`：

```text
0.15
-0.25
-0.10
0.25
-0.15
```

所以：

\[
\frac{
0.5(
0.15^2+
0.25^2+
0.10^2+
0.25^2+
0.15^2
)
}{5}
\]

得到：

\[
\boxed{
approx\_kl\approx0.018
}
\]

而：

```text
early_stop_kl = 0.25
```

所以：

```text
0.018 < 0.25
```

继续训练。

如果某轮已经变成：

```text
approx_kl = 0.30
```

那么：

```python
stop_ppo = True
```

意思就是：

> 当前 Actor 已经离这次 Rollout 的 Old Policy 太远，不应该再拿这一批旧数据反复更新了。

---

<a id="origin-2159"></a>
## 31. 注意：这里其实有两个完全不同的 KL

这是整个函数另一个容易混乱的地方。

<a id="origin-2163"></a>
### 31.1 KL 1：Current Policy vs Old Policy

也就是：

```text
new
vs
rollout 时的 old
```

代码主要通过：

```python
approx_kl
```

监控。

用途：

```text
PPO Early Stop
```

它回答：

> 这一轮 PPO 已经把 Actor 从采样时策略改了多远？

---

<a id="origin-2193"></a>
### 31.2 KL 2：Current Policy vs Reference Model

另外还有：

```python
ref_model
```

这个模型一开始从基础模型加载，然后被冻结，不参与训练。

所以是：

```text
Current Actor
       ↕
Frozen Reference Model
```

用途：

> 防止 Actor 长期强化以后彻底偏离原本语言模型。

所以：

```text
old
```

和：

```text
ref
```

完全不是一个东西。

---

<a id="origin-2231"></a>
## 32. 用一个数值算 Reference KL

假设冻结 Reference Model 对这些 token 的：

```python
ref_logp = [
    [-0.75,-0.30,任意],
    [-0.45,-0.85,-0.15]
]
```

当前 Actor：

```python
new_logp = [
    [-0.55,-0.45,任意],
    [-0.50,-0.55,-0.25]
]
```

代码用：

\[
d
=
\log\pi_{ref}
-
\log\pi_{new}
\]

然后：

\[
e^d-d-1
\]

在 5 个位置平均。

这个例子约：

\[
KL_{ref}
\approx
0.015565
\]

而：

```text
kl_coef = 0.02
```

所以加到 Actor Loss：

\[
0.02\times0.015565
\approx
0.000311
\]

刚才 PPO 主 Loss：

\[
-0.019338
\]

因此最终：

\[
policy\_loss
\approx
-0.019338+0.000311
\]

\[
\boxed{
policy\_loss
\approx
-0.019026
}
\]

所以 Actor Loss 可以理解成：

\[
\boxed{
L_{Actor}
=
L_{PPO}
+
\beta KL(\pi_{new},\pi_{ref})
}
\]

---

<a id="origin-2327"></a>
## 33. 第十二步：Critic 怎么训练？

现在开始另一条支线。

之前 Critic 的旧预测：

```python
old_values = [
    [0.2,0.4,0],
    [0.1,0.3,0.5]
]
```

而它真正应该学习的 Target：

```python
returns = [
    [0.97,1.00,0],
    [1.84375,1.925,2.0]
]
```

经过一次更新以后，假设当前 Critic 已经输出：

```python
new_values = [
    [0.30,0.65,无效],
    [0.25,0.55,0.85]
]
```

直觉上当然是：

\[
(new\_value-return)^2
\]

但 PPO 对 Critic 也进行了 Clip。

---

<a id="origin-2368"></a>
## 34. Critic 的 Value Clip

代码：

\[
V_{clip}
=
clip(
V_{new},
V_{old}-0.2,
V_{old}+0.2
)
\]

例如第一条第二个位置：

```text
old value = 0.4

允许范围：

[0.2,0.6]
```

当前：

```text
new value = 0.65
```

所以 Clip：

```text
0.65
  ↓
0.60
```

第二条第二个位置：

```text
old = 0.3

允许：

[0.1,0.5]

new = 0.55

clip 后 = 0.50
```

第三个：

```text
old = 0.5

允许：

[0.3,0.7]

new = 0.85

clip 后 = 0.70
```

最终：

```python
V_clip = [
    [0.30,0.60,无效],
    [0.25,0.50,0.70]
]
```

---

<a id="origin-2445"></a>
## 35. 为什么 Critic Loss 取两个误差里的更大值？

代码是：

\[
L_V
=
\frac12
\max
\left[
(V_{new}-R)^2,
(V_{clip}-R)^2
\right]
\]

它不是：

> 直接把 Value 强行截断成 Vclip 来训练。

而是：

> 如果 Critic 一次变化太猛，就不给这种大变化带来虚假的损失改善。

例如：

```text
old = 0.4

new = 0.65

target = 1.0
```

直接误差：

\[
(0.65-1)^2
=
0.1225
\]

Clip 后：

```text
0.60
```

误差：

\[
(0.60-1)^2
=
0.16
\]

取大的：

\[
0.16
\]

也就是说：

> 你不能因为一次从 0.4 猛跳到 0.65，就把这部分改善全部算成你的成绩。

---

<a id="origin-2512"></a>
## 36. 把 5 个 Critic 位置全部算完

最终代码里进入平均的 5 个误差大约是：

```text
Sample A：

0.4489
0.1600


Sample B：

2.5400
2.0306
1.6900
```

总和：

\[
6.869564
\]

Critic Loss 前面还有：

\[
\frac12
\]

所以：

\[
value\_loss
=
\frac12
\times
\frac{6.869564}{5}
\]

得到：

\[
\boxed{
value\_loss
\approx0.686956
}
\]

---

<a id="origin-2563"></a>
## 37. 第十三步：Actor Loss + Critic Loss 合起来

代码：

```python
loss = (
    policy_loss
    + vf_coef * value_loss
    + aux_loss
) / accumulation_steps
```

假设不是 MoE：

```text
aux_loss = 0
```

我们刚才：

```text
policy_loss ≈ -0.019026

value_loss  ≈ 0.686956

vf_coef = 0.5
```

所以：

\[
L
=
-0.019026
+
0.5\times0.686956
\]

\[
=
-0.019026
+
0.343478
\]

\[
\boxed{
L\approx0.324452
}
\]

默认：

```text
accumulation_steps = 1
```

所以不用再除。

最终：

```python
loss.backward()
```

---

<a id="origin-2630"></a>
## 38. `loss.backward()` 到底更新了吗？

没有。

这一句：

```python
loss.backward()
```

只是：

```text
根据 Loss
    ↓
反向传播
    ↓
算 Actor 参数梯度
    ↓
算 Critic 参数梯度
    ↓
保存到 parameter.grad
```

真正修改参数的是：

```python
actor_optimizer.step()
critic_optimizer.step()
```

所以：

```text
backward
≠
更新参数
```

完整过程：

```text
loss
 ↓
backward
 ↓
.grad
 ↓
clip_grad_norm_
 ↓
optimizer.step
 ↓
参数真正变化
```

---

<a id="origin-2687"></a>
## 39. 为什么 Actor 和 Critic 可以一次 backward 一起训练？

因为总 Loss：

\[
L
=
L_{Actor}
+
c_1L_{Critic}
\]

其中：

```text
policy_loss
```

计算图连着：

```text
Actor
```

而：

```text
value_loss
```

计算图连着：

```text
Critic
```

所以：

```python
loss.backward()
```

以后：

```text
Actor 参数
    ↓
只得到 Actor 那部分梯度


Critic 参数
    ↓
只得到 Critic 那部分梯度
```

然后分别：

```python
actor_optimizer.step()

critic_optimizer.step()
```

所以虽然写在一个：

```python
loss
```

里面，但它们仍然是在训练两个模型。

---

<a id="origin-2760"></a>
## 40. 为什么 old value 和 returns 不会被反向传播？

因为前面计算：

```text
old value
GAE
returns
reference logp
```

都在：

```python
with torch.no_grad():
```

里面。

所以它们相当于训练 Label：

```text
old_logp      固定
old_value     固定
advantages    固定
returns       固定
ref_logp      固定
```

Update 时重新计算的才有梯度：

```text
new_logp      有梯度 → Actor

new_value     有梯度 → Critic
```

这是理解 PPO 代码最核心的分界线之一。

---

<a id="origin-2801"></a>
## 41. 把 Old、New、Ref、Reward Model 四个角色彻底分开

可以记成下面这张表：

| 东西 | 是什么 | 会不会更新 | 干什么 |
|---|---|---:|---|
| `Actor / new policy` | 当前正在训练的大模型 | 会 | 真正学习 |
| `old_resp_logp` | Rollout 时 Actor 的概率快照 | 不会 | PPO ratio |
| `ref_model` | 冻结基础模型 | 不会 | 防止 Actor 跑太远 |
| `Critic` | Value 模型 | 会 | 预测未来收益 |
| `Reward Model` | 整条回答评分模型 | 不会 | 给最终回答 Reward |

这里最容易犯的错误是把：

```text
old
```

和：

```text
ref
```

看成一回事。

不是。

---

<a id="origin-2831"></a>
## 42. Old Policy 究竟在哪里？

这份代码并没有在每一批：

```python
old_model = deepcopy(actor_model)
```

而是：

```text
Rollout 时把 old token logp 保存下来
```

例如：

```python
old_resp_logp = [
    [-0.7,-0.2,...],
    [-0.4,-0.8,-0.1]
]
```

因此计算：

\[
\frac{\pi_{new}}{\pi_{old}}
\]

只需要：

```python
new_logp - old_logp
```

再：

```python
exp()
```

就行了。

不需要真的再维护一份完整 Old Model。

---

<a id="origin-2878"></a>
## 43. Reference Model 为什么必须是完整模型？

因为 Reference Model 的目标不是：

> 永远和 rollout 那一刻比较。

而是：

> 整个 RLHF/PPO 训练过程中，一直拿初始模型当长期锚点。

例如：

```text
初始 Actor = Ref


第一次 PPO：
Actor1


第二次 PPO：
Actor2


第一百次 PPO：
Actor100
```

但：

```text
Ref
```

始终还是最开始那个模型。

因此可以持续约束：

```text
Actor100
```

不要为了刷 Reward：

```text
彻底偏离正常语言模型
```

---

<a id="origin-2928"></a>
## 44. 函数的三层循环一定要分清楚

整个代码可以抽象成：

```python
for batch in loader:

    # ① 一次新的 Rollout
    rollout()

    # Reward
    # old_value
    # GAE
    # returns

    for ppo_epoch in range(ppo_update_iters):

        shuffle()

        for minibatch in batch:

            # ② 当前 Actor / Critic 重新前向

            # policy loss
            # value loss

            backward()

            optimizer.step()
```

因此三层的职责完全不同。

---

<a id="origin-2963"></a>
## 45. 第一层：Loader Batch

例如：

```text
Batch 1：

Prompt A
Prompt B
```

干一次：

```text
生成回答
Reward
GAE
```

下一次：

```text
Batch 2：

Prompt C
Prompt D
```

会重新生成。

所以：

> **Loader 层决定什么时候产生新的经验。**

---

<a id="origin-2999"></a>
## 46. 第二层：PPO Update Epoch

比如：

```text
ppo_update_iters = 2
```

就表示：

```text
同一批 A、B 生成结果

训练一次
↓
参数发生改变
↓
再训练一次
```

所以：

> **PPO Epoch 决定同一批经验重复利用多少次。**

次数不能无限大。

因为 Actor 越训练越远：

\[
\pi_{new}
\]

就会越来越偏离：

\[
\pi_{old}
\]

所以才需要：

```text
Clip
+
approx KL
+
Early Stop
```

---

<a id="origin-3049"></a>
## 47. 第三层：Mini-batch

假设：

```text
B = 64
mini_batch_size = 8
```

一批 Rollout 有：

```text
64 条回答
```

并不会 64 条一次全部 forward。

而是：

```text
第 1 小批：8
第 2 小批：8
...
第 8 小批：8
```

而我们这个例子：

```text
B = 2

mini_batch_size = 2
```

所以：

```text
一次就处理两条
```

---

<a id="origin-3091"></a>
## 48. `early_stop_kl` 到底停的是谁？

假设：

```text
ppo_update_iters = 10
```

已经进行了：

```text
第 1 次
第 2 次
第 3 次
```

此时：

```text
approx_kl = 0.30
```

超过：

```text
0.25
```

就：

```python
stop_ppo = True
```

于是不会继续：

```text
第 4
第 5
...
第 10
```

但是：

> 它不会结束整个训练。

下一批 Prompt：

```text
Prompt C
Prompt D
```

仍然会正常 Rollout。

因此：

```text
early stop
```

真正含义是：

> **停止继续利用“当前这批旧 rollout 数据”更新 Actor。**

不是：

> PPO 训练程序永久结束。

---

<a id="origin-3163"></a>
## 49. 为什么 Early Stop 时代码仍然 backward？

代码会把：

```python
loss
```

乘：

```text
0
```

即：

```python
loss = (...) * 0
```

然后仍然：

```python
loss.backward()
```

这是主要为了分布式 DDP 保持：

```text
各 GPU forward / backward 通信流程一致
```

否则：

```text
GPU 0 break 了
GPU 1 还在 backward
```

容易发生通信等待甚至死锁。

所以：

```text
计算图还走
梯度贡献 = 0
```

---

<a id="origin-3213"></a>
## 50. 梯度累积在这里怎么理解？

默认：

```text
accumulation_steps = 1
```

最简单：

```text
每个 minibatch

forward
↓
backward
↓
optimizer.step
↓
zero_grad
```

如果：

```text
accumulation_steps = 4
```

理论目标就是：

```text
Mini-batch 1
backward

Mini-batch 2
backward

Mini-batch 3
backward

Mini-batch 4
backward

↓

四次梯度累计

↓

optimizer.step
```

所以代码会把每次 Loss：

\[
\frac{L}{4}
\]

再累加 4 次梯度。

需要特别注意：

> 当前文件在每个 rollout batch 末尾还会主动提交“不足一个 accumulation window”的剩余梯度，而且 `grad_accum_step` 没有在这个尾部提交后归零。

所以当：

```text
accumulation_steps > 1
```

时，当前实现的跨 rollout 梯度累计边界并不特别规整。

默认：

```text
accumulation_steps = 1
```

时没有这个问题。

---

<a id="origin-3295"></a>
## 51. 最后模型究竟朝什么方向更新？

我们的例子中，标准化后：

```text
Sample A：

21   A=-1.0187

EOS  A=-1.3811
```

所以 Actor 倾向：

```text
降低这些动作概率
```

而：

```text
Sample B：

31   A=+1.0576

32   A=+0.8044

EOS  A=+0.5379
```

Actor 倾向：

```text
增加这些动作概率
```

同时：

```text
PPO Clip
```

告诉 Actor：

> 调可以，但一次别调太狠。

而：

```text
Reference KL
```

告诉 Actor：

> 长期也别离原始语言模型越来越远。

---

<a id="origin-3353"></a>
## 52. Critic 在学什么？

Critic 原来：

```text
Sample A：

0.2
0.4
```

GAE 认为更合理的 Target 是：

```text
0.97
1.00
```

所以 Critic 会逐渐学习：

```text
以后遇到类似状态：

不要再只预测 0.2
应该预测得更接近 0.97
```

为什么要训练 Critic？

因为下一批 Rollout 时：

```text
更准确的 V(s)
```

能够带来：

```text
更准确、更低方差的 Advantage
```

进而：

```text
Actor 更新更稳定
```

所以存在一个循环：

```text
Actor 生成数据
     ↓
Critic 帮 Actor 计算 Advantage
     ↓
Actor 变好

同时

真实 Reward
     ↓
训练 Critic
     ↓
Critic 对未来收益估计变好
     ↓
下一轮 Advantage 更准确
```

---

<a id="origin-3422"></a>
## 53. 把整个数值例子压缩成一张表

<a id="origin-3424"></a>
### 53.1 Rollout 得到

| Sample | Response | Reward |
|---|---|---:|
| A | `21 EOS` | 1 |
| B | `31 32 EOS` | 2 |

---

<a id="origin-3433"></a>
### 53.2 Old Log Probability

```text
A：
[-0.7, -0.2]

B：
[-0.4, -0.8, -0.1]
```

---

<a id="origin-3445"></a>
### 53.3 Old Value

```text
A：
[0.2,0.4]

B：
[0.1,0.3,0.5]
```

---

<a id="origin-3457"></a>
### 53.4 Token Reward

```text
A：
[0,1]

B：
[0,0,2]
```

---

<a id="origin-3469"></a>
### 53.5 Raw GAE Advantage

```text
A：
[0.77,0.60]

B：
[1.74375,1.625,1.5]
```

---

<a id="origin-3481"></a>
### 53.6 Critic Target

```text
A：
[0.97,1.00]

B：
[1.84375,1.925,2.0]
```

---

<a id="origin-3493"></a>
### 53.7 Standardized Advantage

```text
A：
[-1.0187,-1.3811]

B：
[1.0576,0.8044,0.5379]
```

---

<a id="origin-3505"></a>
### 53.8 假设更新后的 Ratio

```text
A：
[1.1618,0.7788]

B：
[0.9048,1.2840,0.8607]
```

---

<a id="origin-3517"></a>
### 53.9 Actor 最终行为

```text
A：

Advantage < 0
→ 希望降低概率


B：

Advantage > 0
→ 希望增加概率
```

但：

```text
ratio < 0.8
或者
ratio > 1.2
```

时：

```text
PPO Clip 开始限制更新收益
```

---

<a id="origin-3548"></a>
## 54. 所以 `ppo_train_epoch` 可以最终记成下面这一张流程图

```text
┌───────────────────────────────┐
│          一批 Prompt           │
└───────────────┬───────────────┘
                ↓
         tokenizer + padding
                ↓
┌───────────────────────────────┐
│         Actor Rollout          │
│                               │
│  生成 response                │
│  保存 old_resp_logp           │
└───────────────┬───────────────┘
                ↓
       Reward Model 评分
                ↓
        Sequence Reward
                ↓
       最后 token 得 Reward
                ↓
┌───────────────────────────────┐
│         Old Critic             │
│                               │
│       old_resp_values          │
└───────────────┬───────────────┘
                ↓
            GAE 倒推
                ↓
       ┌────────┴────────┐
       ↓                 ↓
 raw Advantage         Returns
       ↓                 ↓
  标准化                固定
       ↓                 ↓
 Actor Target        Critic Target
       │                 │
       └────────┬────────┘
                ↓
=====================================
          PPO UPDATE STAGE
=====================================
                ↓
       同一批 rollout 数据
                ↓
      ┌─────────┴─────────┐
      ↓                   ↓
Current Actor       Current Critic
      ↓                   ↓
new_logp            new_value
      ↓                   ↓
new-old             与 returns 比
      ↓                   ↓
ratio               Value Clip
      ↓                   ↓
PPO Clip Loss       Value Loss
      │                   │
      └─────────┬─────────┘
                ↓
      + Reference KL
                ↓
           Total Loss
                ↓
           backward()
                ↓
       gradient clipping
                ↓
      ┌─────────┴─────────┐
      ↓                   ↓
Actor optimizer     Critic optimizer
      ↓                   ↓
Actor 参数变化      Critic 参数变化
      └─────────┬─────────┘
                ↓
      下一轮 PPO Update
                ↓
    ratio 开始真正偏离 1
                ↓
   偏离过大 → Clip / KL Early Stop
```

---

<a id="origin-3632"></a>
## 55. 最后把整段代码浓缩成 12 句话

PPO 训练的 12 个核心要点如下。

<a id="origin-3636"></a>
### 55.1 1

Actor 先对 Prompt 真正生成回答。

<a id="origin-3640"></a>
#### 55.1.1 2

生成时把每个回答 token 的：

\[
\log\pi_{old}
\]

保存下来。

<a id="origin-3650"></a>
#### 55.1.2 3

Reward Model 对整条回答给一个最终 Reward。

<a id="origin-3654"></a>
#### 55.1.3 4

最终 Reward 被放到最后一个有效回答 token。

<a id="origin-3658"></a>
#### 55.1.4 5

Critic 对每个回答动作之前的状态计算：

\[
V_{old}(s_t)
\]

<a id="origin-3666"></a>
#### 55.1.5 6

从后向前计算：

\[
\delta_t
=
r_t+\gamma V_{t+1}-V_t
\]

和：

\[
A_t
=
\delta_t+\gamma\lambda A_{t+1}
\]

<a id="origin-3684"></a>
#### 55.1.6 7

用原始 GAE Advantage 构造：

\[
Return_t
=
A_t+V_{old}(s_t)
\]

这个 Return 用来训练 Critic。

<a id="origin-3696"></a>
#### 55.1.7 8

然后把 Advantage 标准化，给 Actor 使用。

<a id="origin-3700"></a>
#### 55.1.8 9

当前 Actor 对同一批已经生成的 token 再算：

\[
\log\pi_{new}
\]

得到：

\[
r_t
=
e^{\log\pi_{new}-\log\pi_{old}}
=
\frac{\pi_{new}}{\pi_{old}}
\]

<a id="origin-3718"></a>
#### 55.1.9 10

Actor 使用：

\[
\boxed{
\min
(
r_tA_t,
clip(r_t,1-\epsilon,1+\epsilon)A_t
)
}
\]

并额外加入 Reference Model KL 约束。

<a id="origin-3734"></a>
#### 55.1.10 11

Critic 用：

\[
Returns
\]

作为目标训练，并对 Value 更新做 Clip。

<a id="origin-3744"></a>
#### 55.1.11 12

最终：

\[
\boxed{
L
=
L_{Actor}
+
c_vL_{Critic}
+
L_{aux}
}
\]

然后：

```python
loss.backward()

actor_optimizer.step()

critic_optimizer.step()
```

这就是整个：

```python
ppo_train_epoch()
```

真正做的事情。

---

<a id="origin-3780"></a>
## 56. 一句话抓住它的本质

`ppo_train_epoch` 本质上是在做：

> **Actor 先生成一批回答并把当时的自己冻结成 old 概率；Reward Model 给结果打分，Critic + GAE 把最终奖励分配给每一步；然后 Actor 根据 Advantage 调整这些 token 的生成概率，Critic 根据 Returns 修正自己的价值预测，同时 PPO Clip、Old-policy KL early stop 和 Reference KL 一起限制模型不要一次走得太远。**

如果把这句话理解透了，整个函数里剩下的大部分代码其实都只是：

```text
张量对齐
mask
gather
mini-batch
梯度累积
分布式同步
保存日志
```

而真正的 PPO 数学主线，就是：

\[
Reward
\rightarrow
GAE
\rightarrow
Advantage
\rightarrow
Ratio
\rightarrow
Clip
\rightarrow
Actor
\]

以及另一条：

\[
Reward
\rightarrow
GAE
\rightarrow
Returns
\rightarrow
Critic
\]

两条线最后在同一个 `loss.backward()` 中汇合。
