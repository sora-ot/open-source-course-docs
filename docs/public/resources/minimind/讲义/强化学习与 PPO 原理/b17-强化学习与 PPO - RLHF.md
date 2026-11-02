# 强化学习与 PPO / RLHF


<a id="origin-3"></a>
## 1. ——用一个连续例子，把 Policy Gradient、Critic、TD、GAE、Importance Sampling、PPO-Clip、Reward Model 全部串起来

---

<a id="origin-7"></a>
## 2. 从最简单的强化学习故事开始

先完全不讲 PPO。

假设我们训练一个机器人走迷宫。

机器人面前有三个方向：

```text
左
右
前
```

机器人当前看到的情况叫：

\[
s_t
\]

也就是：

> State，状态。

机器人选择一个动作：

\[
a_t
\]

也就是：

> Action，动作。

动作执行以后，环境给它一个奖励：

\[
r_t
\]

也就是：

> Reward，奖励。

同时机器人进入新的状态：

\[
s_{t+1}
\]

所以一次强化学习交互最基本的结构就是：

```text
State
  ↓
Action
  ↓
Reward
  ↓
Next State
```

数学上：

\[
s_t
\rightarrow
a_t
\rightarrow
r_t
\rightarrow
s_{t+1}
\]

---

<a id="origin-83"></a>
## 3. Policy 是什么

机器人不是每次固定向右，而是有一个策略：

\[
\pi_\theta(a|s)
\]

其中：

- \(\pi\)：Policy
- \(\theta\)：神经网络参数
- \(s\)：状态
- \(a\)：动作

例如当前状态 \(s\) 下：

```text
左：20%
右：60%
前：20%
```

那么：

\[
\pi_\theta(\text{右}|s)=0.6
\]

意思就是：

> 在状态 \(s\) 下，当前 Policy 选择“右”的概率是 0.6。

---

<a id="origin-118"></a>
## 4. 为什么 Policy 要输出概率，而不是直接输出一个动作

因为强化学习需要探索。

如果一开始就永远：

```text
右
```

那机器人可能永远不知道：

```text
左边其实有更短的路
```

所以 Policy 通常输出一个概率分布。

例如：

\[
\pi_\theta(a|s)
=
[0.2,0.6,0.2]
\]

然后根据这个概率采样动作。

这意味着：

> 同一个状态，多次运行，可能选择不同动作。

这件事非常重要。

因为它直接导致：

> 同一个 Policy 可能产生很多不同 trajectory。

---

<a id="origin-158"></a>
## 5. 什么是 trajectory

假设机器人从起点开始：

```text
s0
↓ 选择右
s1
↓ 选择前
s2
↓ 选择左
s3
↓ 到终点
```

这整条过程就是一条：

> trajectory，轨迹。

写成：

\[
\tau
=
(s_0,a_0,r_0,s_1,a_1,r_1,\ldots)
\]

---

<a id="origin-187"></a>
## 6. “轨迹不是只有一条吗？”——一次运行确实只有一条，但理论上有很多可能轨迹

这是一个非常关键的问题。

一次真实运行：

> 当然只产生一条 trajectory。

但是在运行之前，由于 Policy 是随机的，可能出现很多结果。

例如起点：

```text
向左：20%
向右：60%
向前：20%
```

那么可能轨迹有：

```text
轨迹1：
右 → 前 → 终点

轨迹2：
左 → 撞墙 → 返回 → 右 → 终点

轨迹3：
前 → 前 → 死路

轨迹4：
右 → 左 → 右 → ...
```

所以：

\[
\boxed{
一次 Rollout 只产生一条真实轨迹
}
\]

但是：

\[
\boxed{
Policy 理论上定义了很多“可能轨迹”的概率分布
}
\]

---

<a id="origin-239"></a>
## 7. 什么是 Reward 和 Return

Reward：

\[
r_t
\]

只表示：

> 当前这一步得到多少奖励。

但强化学习真正关心的，通常不是眼前这一分，而是：

> 从现在开始未来一共能得到多少奖励。

于是定义：

\[
G_t
\]

叫：

> Return。

---

<a id="origin-267"></a>
## 8. Return \(G_t\) 是怎么来的

假设：

```text
t=0：奖励 1
t=1：奖励 2
t=2：奖励 10
```

如果直接相加：

\[
G_0=1+2+10=13
\]

但是强化学习通常认为：

> 越遥远的奖励越不确定，因此价值应该适当打折。

所以引入：

\[
\gamma
\]

称为：

> discount factor，折扣因子。

例如：

\[
\gamma=0.9
\]

那么：

\[
G_t
=
r_t
+
\gamma r_{t+1}
+
\gamma^2r_{t+2}
+\cdots
\]

例如：

\[
G_0
=
1+0.9\times2+0.9^2\times10
\]

得到：

\[
G_0
=
1+1.8+8.1
=
10.9
\]

因此：

\[
G_t
=
\sum_{k=0}^{\infty}
\gamma^k r_{t+k}
\]

---

<a id="origin-345"></a>
## 9. \(G_t\) 是真实算出来的吗

如果一条 trajectory 已经完整跑完：

```text
r0, r1, r2, ..., rT
```

那么：

\[
G_t
\]

可以直接从真实 reward 往回算。

例如：

\[
G_T=r_T
\]

\[
G_{T-1}=r_{T-1}+\gamma G_T
\]

\[
G_{T-2}=r_{T-2}+\gamma G_{T-1}
\]

所以：

\[
\boxed{
完整 Rollout 中的 G 是根据真实 Reward 算出来的
}
\]

---

<a id="origin-385"></a>
## 10. 如果未来还没有真的跑完怎么办

假设一条轨迹非常长。

我们只 Rollout 到：

```text
t=1000
```

但环境还没终止。

那：

\[
r_{1001},r_{1002},\ldots
\]

我们还不知道。

这时候不能直接算完整 Return。

于是会使用一个模型：

\[
V(s_{1000})
\]

来估计后面未来的价值。

例如：

\[
G_{999}
\approx
r_{999}
+
\gamma V(s_{1000})
\]

这叫：

> Bootstrapping（自举法）。

---

<a id="origin-431"></a>
## 11. Value \(V(s)\) 到底是什么

定义：

\[
\boxed{
V^\pi(s)
=
\mathbb E_\pi[G_t|s_t=s]
}
\]

自然语言：

> 现在位于状态 \(s\)，以后一直按照当前 Policy 行动，平均未来能拿多少 Return？

---

<a id="origin-449"></a>
## 12. “平均期望价值”到底怎么来的

假设我们真的能从同一个状态 \(s\) 出发很多次。

结果：

```text
第一次：Return = 8
第二次：Return = 12
第三次：Return = 9
第四次：Return = 11
第五次：Return = 10
```

平均：

\[
\frac{8+12+9+11+10}{5}
=
10
\]

那么：

\[
V^\pi(s)\approx10
\]

所以：

\[
\boxed{
V(s) 本质上就是未来 Return 的条件期望
}
\]

---

<a id="origin-487"></a>
## 13. 真实训练中不会真的把同一个状态重复玩很多遍

现实状态空间太大。

例如大模型：

```text
Prompt + 已生成的全部 Token
```

每个上下文都可能不同。

所以不可能维护：

```text
状态A → 10
状态B → 12
状态C → 5
```

这样的表。

于是用神经网络：

\[
V_\phi(s)
\]

近似 Value。

这个模型就是：

**Critic**

---

<a id="origin-523"></a>
## 14. Actor-Critic

这里自然产生两个网络。

<a id="origin-527"></a>
### 14.1 Actor

Actor 负责：

> 我应该做什么动作？

输出：

\[
\pi_\theta(a|s)
\]

例如：

```text
左  0.2
右  0.6
前  0.2
```

**在大模型PPO/RLHF 里，Actor基本就是当前正在被训练的那个“负责最终回答问题的”大语言模型，也就是 Policy Model。**

<a id="origin-549"></a>
### 14.2 Critic

Critic 负责：

> 当前这个状态大概值多少分？

输出：

\[
V_\phi(s)
\]

例如：

\[
V_\phi(s)=8.7
\]

因此：

```text
Actor：
决定怎么做

Critic：
评价当前情况
```

这就是：

> Actor-Critic。


---

<a id="origin-584"></a>
## 15. Q Function 是什么

Value 只问：

> “当前状态整体上值多少？”

但我们更想问：

> “如果我在这个状态下，先执行某个具体 Action，会怎么样？”

于是定义：

\[
\boxed{
Q^\pi(s,a)
=
\mathbb E[G_t|s_t=s,a_t=a]
}
\]

---

<a id="origin-606"></a>
### 15.1 \(Q(s_t,a_t)\) 和 \(G_t\) 到底是什么关系？

**注意这里标题写的是\((s_t,a_t)\)，而上面公式里是\((s,a)\)**。

\[
\boxed{
Q^\pi(s_t,a_t)
=
\mathbb E
[
G_t|s_t,a_t
]
}
\]

意思是：

**在 \(s_t\) 下先选择 \(a_t\)，之后继续按照 Policy \(\pi\) 行动，未来平均能获得多少 Return。**

所以：

\[
\boxed{
Q=\text{期望 Return}
}
\]



<a id="origin-635"></a>
### 15.2 \(G_t\) 是 Q 的一次实际样本

假设同一个：

\[
(s_t,a_t)
\]

重复 Rollout 三次：

第一次：

\[
G_t^{(1)}=8
\]

第二次：

\[
G_t^{(2)}=12
\]

第三次：

\[
G_t^{(3)}=10
\]

那么：

\[
Q^\pi(s_t,a_t)
\approx
\frac{8+12+10}{3}
=
10
\]

因此：

\[
\boxed{
G_t
\text{ 是一次实际 Return}
}
\]

而：

\[
\boxed{
Q^\pi(s_t,a_t)
\text{ 是很多次可能 Return 的期望}
}
\]

---

<a id="origin-693"></a>
## 16. V 和 Q 的区别

假设：

\[
V(s)=10
\]

表示：

> 当前状态下，按照当前 Policy 平均能拿 10 分。

但是具体动作：

```text
向左：
Q(s,左)=6

向右：
Q(s,右)=14

向前：
Q(s,前)=10
```

那么：

- 向右明显比平均水平好；
- 向左明显比平均水平差。

于是引出 Advantage。

---

<a id="origin-727"></a>
## 17. Advantage 是什么

定义：

\[
\boxed{
A^\pi(s,a)
=
Q^\pi(s,a)-V^\pi(s)
}
\]

如果：

\[
V(s)=10
\]

而：

\[
Q(s,\text{右})=14
\]

那么：

\[
A(s,\text{右})=4
\]

意思：

> 右这个 Action 比当前状态下的平均选择好 4 分。

如果：

\[
Q(s,\text{左})=6
\]

那么：

\[
A(s,\text{左})=-4
\]

说明：

> 左比平均水平差 4 分。

---

<a id="origin-779"></a>
## 18. 强化学习真正应该学什么

直觉上：

如果：

\[
A(s,a)>0
\]

那么：

> 以后在这个状态下，多选一点这个 Action。

如果：

\[
A(s,a)<0
\]

那么：

> 以后少选一点这个 Action。

这其实已经非常接近 Policy Gradient。

---

<a id="origin-807"></a>
## 19. 强化学习的目标 \(J(\theta)\)

我们希望 Policy 长期平均 Reward 最大。

定义：

\[
\boxed{
J(\theta)
=
\mathbb E_{\tau\sim\pi_\theta}
[R(\tau)]
}
\]

这里：

\[
R(\tau)
\]

表示整条 trajectory 的总 Reward。

---

<a id="origin-832"></a>
## 20. 为什么 \(J(\theta)\) 里面要对很多 trajectory 求期望

因为 Policy 是随机的。

假设只有 3 条可能轨迹：

```text
轨迹1：
概率 0.7
Reward 10

轨迹2：
概率 0.2
Reward 5

轨迹3：
概率 0.1
Reward -10
```

那么：

\[
J(\theta)
=
0.7\times10
+
0.2\times5
+
0.1\times(-10)
\]

\[
=7
\]

所以：

\[
\boxed{
J(\theta)
=
\sum_\tau
P_\theta(\tau)
R(\tau)
}
\]

即在当前策略\(\theta\)下产生的轨迹的Reward之和。
**则优化目标为：尽可能优化出一个策略\(\theta\)，使得这个策略产生的轨迹所获得的奖励最大。**

---

<a id="origin-885"></a>
## 21. 现实中不可能真的枚举全部轨迹

真实环境里可能有海量 trajectory。

所以理论：

\[
\sum_\tau
P_\theta(\tau)R(\tau)
\]

实际：

> 通过 Rollout 采一批 trajectory，用样本平均近似。

即：

\[
J(\theta)
\approx
\frac1N
\sum_{i=1}^N
R(\tau_i)
\]

这就是：

> Monte Carlo estimation。

---

<a id="origin-916"></a>
## 22. 为什么不能直接采样 1000 条轨迹，用原始的 PR 逐条训练？

<a id="origin-918"></a>
## 23. 最初的目标就是最大化期望 Reward

\[
\boxed{J(\theta)=\sum_{\tau}P_\theta(\tau)R(\tau)}
\]

其中：

- \(\tau\)：模型生成的一条完整轨迹（例如一段回答）。
- \(P_\theta(\tau)\)：当前 Policy 生成这条轨迹的概率。
- \(R(\tau)\)：这条轨迹得到的 Reward。

我们希望调整参数 \(\theta\)，让 \(J(\theta)\) 最大。

**如果能枚举所有轨迹并计算上式，就可以直接对 \(J\) 反向传播，不需要 Policy Gradient 推导。** 但大模型的可能轨迹数量太多，无法穷举。

<a id="origin-934"></a>
## 24. 那么只采样 1000 条，一条一条更新，可以吗？

**代码上完全可以。** 因为对于已经确定的一条轨迹 \(\tau\)，\(P_\theta(\tau)\) 是可微的：

\[
L_\tau(\theta)=-P_\theta(\tau)R(\tau)
\]

可以执行：

```python
loss = -trajectory_prob * reward
loss.backward()
optimizer.step()
```

但问题是：**单条轨迹的 \(PR\) 梯度，不一定是原始期望 Reward 的正确更新方向。** 采样 1000 条、分别更新 1000 次，也不能自动消除这个问题。

<a id="origin-952"></a>
## 25. 一个数值例子：直接用 PR 甚至可能越训练越差

假设模型只有两个动作：

| 动作 | 当前概率 | Reward |
|---|---:|---:|
| A | 0.2 | 2 |
| B | 0.8 | 1 |

令 \(P_\theta(A)=\theta\)，\(P_\theta(B)=1-\theta\)。原始目标是：

\[
J(\theta)=2\theta+(1-\theta)=1+\theta
\]

所以正确梯度为：

\[
\boxed{\frac{dJ}{d\theta}=1}
\]

即应该**增大 A 的概率**。

但如果按照当前 Policy 抽一个动作，然后直接求 \(P_\theta(a)R(a)\) 的梯度：

- 抽到 A，梯度 \(\frac{d}{d\theta}(2\theta)=2\)，概率为 0.2。
- 抽到 B，梯度 \(\frac{d}{d\theta}(1-\theta)=-1\)，概率为 0.8。

平均梯度却是：

\[
0.2\times 2+0.8\times(-1)=\boxed{-0.4}
\]

**真实目标希望增加 A 的概率（梯度 +1），而这种采样更新的平均方向却要降低 A 的概率（梯度 -0.4）。**

问题出在：**高概率轨迹已经更容易被抽到，再对采到的 \(PR\) 求平均，相当于多乘了一次采样概率。** 当采样分布固定为 \(P_\theta\) 时，这种梯度估计对应的是 \(\sum_\tau P_\theta(\tau)\,\nabla_\theta[P_\theta(\tau)R(\tau)]\)，而不是 \(\nabla_\theta J\)。

> 上述计算是在当前参数处分析单步更新方向。逐条更新时参数会变化，还会产生旧采样策略与新策略不一致的问题，但并不能消除上述根本偏差。

<a id="origin-992"></a>
## 26. 所以要使用Policy Gradient解决

从原始目标出发：

\[
\begin{aligned}
\nabla_\theta J
&=\sum_\tau R(\tau)\nabla_\theta P_\theta(\tau)\\
&=\sum_\tau P_\theta(\tau)R(\tau)\nabla_\theta\log P_\theta(\tau)\\
&=\boxed{\mathbb E_{\tau\sim P_\theta}\left[R(\tau)\nabla_\theta\log P_\theta(\tau)\right]}
\end{aligned}
\]

这里利用恒等式：

\[
\nabla_\theta P_\theta(\tau)
=P_\theta(\tau)\nabla_\theta\log P_\theta(\tau)
\]

这样就可以**按当前 Policy 采样少量轨迹，用每条轨迹的 \(R\nabla\log P\) 估计正确梯度**。

回到刚才的例子：

- 抽到 A：\(R(A)\frac{d}{d\theta}\log P(A)=2/0.2=10\)。
- 抽到 B：\(R(B)\frac{d}{d\theta}\log P(B)=-1/0.8=-1.25\)。

平均为：

\[
0.2\times10+0.8\times(-1.25)=\boxed{1}
\]

**这次与原始目标的真实梯度完全相同！**（指期望值；有限样本会有随机误差。）

---

<a id="origin-1029"></a>
## 27. Policy Gradient详细推导

一条 trajectory 的概率：

\[
\boxed{
P_\theta(\tau)
=
P(s_0)
\prod_t
\pi_\theta(a_t|s_t)
P(s_{t+1}|s_t,a_t)
}
\]

这里分成三部分。

---

<a id="origin-1048"></a>
### 27.1 \(P(s_0)\)

初始状态出现的概率。

例如：

> 环境一开始把机器人放到哪里。

对于大模型：

> 训练数据里抽到了哪个 Prompt。

---

<a id="origin-1062"></a>
### 27.2 \(\pi_\theta(a_t|s_t)\)

就是：

> 当前 Policy 在状态 \(s_t\) 下，选择实际动作 \(a_t\) 的概率。

例如：

```text
状态：
"1+1="

Policy：
"2": 0.85
"3": 0.05
...
```

如果实际选中：

```text
"2"
```

那么：

\[
\pi_\theta(a_t|s_t)=0.85
\]

---

<a id="origin-1094"></a>
### 27.3 \(P(s_{t+1}|s_t,a_t)\)

环境的状态转移概率。

例如机器人：

```text
当前房间
+
向右
```

可能：

```text
80% 进入房间B
20% 滑到房间C
```

那么：

\[
P(s_{t+1}|s_t,a_t)
\]

描述的就是这个随机转移。

---

<a id="origin-1123"></a>
## 28. 和马尔科夫链是什么关系

强化学习通常建立在：

> Markov Decision Process，MDP

之上。

**即：强化学习并不是天然满足马尔可夫性质，而是经典强化学习理论通常假设环境可以建模为马尔可夫决策过程（MDP）。**

MDP 中：

\[
P(s_{t+1}|s_t,a_t)
\]

表示：

> 当前状态和当前动作足够决定下一状态的分布。

Markov Property：

\[
P(s_{t+1}|s_0,\ldots,s_t,a_t)
=
P(s_{t+1}|s_t,a_t)
\]

---

<a id="origin-1153"></a>
### 28.1 固定 Policy 后，MDP 会诱导出一条 Markov Chain

因为：

\[
P_\pi(s'|s)
=
\sum_a
\pi(a|s)P(s'|s,a)
\]

所以：

\[
\boxed{
MDP + 固定 Policy
\Rightarrow
Policy-induced Markov Chain
}
\]

而 PPO：

> 不断修改 Policy，因此不断改变未来状态分布。

---

<a id="origin-1180"></a>
## 29. 马尔可夫性质、马尔可夫链与强化学习

<a id="origin-1182"></a>
### 29.1 一、一句话理解马尔可夫性质

**过去发生的事情不是没有影响，而是：只要当前状态足够完整，过去对未来的影响就已经体现在当前状态里。**

也就是说：**如果当前状态已经包含了预测下一步所需的全部信息，那么再知道过去的状态，也不会改变对下一步的概率预测。**

所以，要预测下一步，不需要把全部历史再看一遍。

但有一个重要前提：**并非所有现实过程都天然满足马尔可夫性质。是否成立，取决于过程本身以及我们怎样定义“状态”。**

<a id="origin-1192"></a>
### 29.2 二、公式是什么意思？

对于随机过程 $S_0,S_1,\ldots$，马尔可夫性质写作：

$$
\boxed{P(S_{t+1}\mid S_t,S_{t-1},\ldots,S_0)
=P(S_{t+1}\mid S_t)}
$$

- **左边**：知道从过去到现在的所有状态，预测下一步。
- **右边**：只知道当前状态，预测下一步。
- **等号**：过去的状态不会在当前状态之外，额外增加对下一步的预测信息。

这里说的是**条件概率分布相同**，不是说下一步一定确定、没有随机性。

也可以理解为：**给定当前状态后，下一步与更早的历史条件独立。**

<a id="origin-1209"></a>
### 29.3 三、最简单的反例：只知道汽车的位置，不够

假设汽车在直线上行驶，每一秒更新一次位置。在**匀速运动**的简化情况下：

$$
x_{t+1}=x_t+v_t\Delta t
$$

其中 $x_t$ 是当前位置，$v_t$ 是速度，$\Delta t=1$ 秒。

假设你只知道汽车当前在 **10 米**处：

- 如果速度是 $+2$ 米/秒，下一秒在 **12 米**。
- 如果速度是 $-2$ 米/秒，下一秒在 **8 米**。

只知道位置 $x_t=10$，无法判断下一秒更可能在哪里。更早的位置历史可能帮助我们推测当前速度，因此“只有位置”一般不是充分状态。

此时可能出现：

$$
P(x_{t+1}\mid x_t,x_{t-1})\neq P(x_{t+1}\mid x_t)
$$

这说明：**当状态只定义成位置时，这个位置序列通常不是马尔可夫链。**

<a id="origin-1234"></a>
### 29.4 四、重新定义状态：位置 + 速度

现在把状态定义为：

$$
\boxed{S_t=(x_t,v_t)}
$$

假设：

$$
S_t=(10,2)
$$

在匀速运动假设下，下一秒的位置为：

$$
x_{t+1}=10+2\times 1=12
$$

此时不必再查看汽车几分钟前在哪里，因为下一步所需的信息已包含在当前的 $(x_t,v_t)$ 中。

如果还存在加速度、驾驶员操作、随机扰动等，就需要在模型中额外考虑它们：例如把操作作为**动作**，把随机扰动写入**状态转移概率**，必要时补充状态变量。

**关键结论：马尔可夫性质不是“忘记历史”，而是“用足够完整的当前状态总结历史”。**

**也就是说：当前状态是过去历史对未来影响的充分总结。**

<a id="origin-1262"></a>
### 29.5 五、为什么叫“马尔可夫链”？

当随机过程满足马尔可夫性质时，就称为**马尔可夫链**（通常考虑离散时间）。

例如，假设今天的天气状态只有“晴”和“雨”，而明天的天气分布只依赖于今天：

| 今天 | 明天晴 | 明天雨 |
|---|---:|---:|
| 晴 | 0.8 | 0.2 |
| 雨 | 0.3 | 0.7 |

那么：

$$
P(S_{t+1}=\text{晴}\mid S_t=\text{雨})=0.3
$$

我们不必知道前天、大前天的天气，就能按照这个假设预测明天。这是一个**假设性的马尔可夫链示例**；真实天气能否只由“晴/雨”描述，是另一回事。

> 严格来说，马尔可夫链描述的是**没有显式决策动作的状态随机转移**；强化学习通常使用引入动作的马尔可夫决策过程（MDP）。

<a id="origin-1283"></a>
### 29.6 六、强化学习里的马尔可夫性质：MDP

强化学习的下一步不仅受当前状态影响，还受智能体选择的动作影响。

因此，在**马尔可夫决策过程**（Markov Decision Process, MDP）中：

$$
\boxed{
P(s_{t+1},r_t\mid s_t,a_t,s_{t-1},a_{t-1},\ldots)
=P(s_{t+1},r_t\mid s_t,a_t)
}
$$

意思是：只要知道**当前状态** $s_t$ 和**当前动作** $a_t$，就足以确定下一状态与奖励的概率分布，无须再考虑完整历史。

这里的“确定”指**确定概率分布**，不是保证下一状态只有一种结果。

---

<a id="origin-1302"></a>
## 30. 为什么强化学习中的轨迹概率可以写成连乘？

<a id="origin-1304"></a>
## 31. 我们要证明什么？

在马尔可夫决策过程（MDP）中，一条长度为 $T$ 的轨迹写作：

$$
\tau=(s_0,a_0,s_1,a_1,\ldots,a_{T-1},s_T)
$$

它在策略 $\pi$ 下发生的概率为：

$$
\boxed{
P_\pi(\tau)
=\rho_0(s_0)
\prod_{t=0}^{T-1}
\pi(a_t\mid s_t)P(s_{t+1}\mid s_t,a_t)
}
$$

其中：

- $\rho_0(s_0)$：初始状态为 $s_0$ 的概率。
- $\pi(a_t\mid s_t)$：策略在状态 $s_t$ 选择动作 $a_t$ 的概率。
- $P(s_{t+1}\mid s_t,a_t)$：环境在状态 $s_t$ 执行动作 $a_t$ 后到达状态 $s_{t+1}$ 的概率。
- $\prod$：把每一步的概率相乘。

**问题：为什么一整条轨迹的概率，可以拆成上面这些概率的连乘？**

答案分两步：**先使用概率论的链式法则，再使用马尔可夫性质简化条件。**

<a id="origin-1334"></a>
## 32. 第一步：概率论的链式法则

对于两个随机变量（或事件）$A,B$：

$$
P(A,B)=P(A)P(B\mid A)
$$

对于三个变量：

$$
P(A,B,C)=P(A)P(B\mid A)P(C\mid A,B)
$$

推广到五个变量：

$$
\boxed{
\begin{aligned}
P(A,B,C,D,E)
={}&P(A)\\
&\cdot P(B\mid A)\\
&\cdot P(C\mid A,B)\\
&\cdot P(D\mid A,B,C)\\
&\cdot P(E\mid A,B,C,D)
\end{aligned}
}
$$

直观理解：**一连串指定事件全部发生的概率，等于第一个事件发生的概率，乘以后一个事件在前面事件已经发生的条件下发生的概率，依次乘下去。**

这里还**没有使用马尔可夫性质**；链式法则本身就是概率论恒等式。

<a id="origin-1367"></a>
## 33. 第二步：应用到一条两步轨迹

考虑轨迹：

$$
\tau=(s_0,a_0,s_1,a_1,s_2)
$$

它表示：

```text
初始状态 s0
    ↓
策略选择动作 a0
    ↓
环境转移到 s1
    ↓
策略选择动作 a1
    ↓
环境转移到 s2
```

我们要求的是这五个指定结果**全部按顺序发生**的联合概率：

$$
P_\pi(s_0,a_0,s_1,a_1,s_2)
$$

把上一节的链式法则直接套进来：

$$
\begin{aligned}
&P_\pi(s_0,a_0,s_1,a_1,s_2)\\
={}&P(s_0)\\
&\cdot P(a_0\mid s_0)\\
&\cdot P(s_1\mid s_0,a_0)\\
&\cdot P(a_1\mid s_0,a_0,s_1)\\
&\cdot P(s_2\mid s_0,a_0,s_1,a_1)
\end{aligned}
$$

注意：此时后两项仍然保留了全部历史信息，还不是最终公式。

<a id="origin-1410"></a>
## 34. 第三步：利用马尔可夫性质，把长条件变短

<a id="origin-1412"></a>
### 34.1 初始状态分布

将第一项写成：

$$
P(s_0)=\rho_0(s_0)
$$

<a id="origin-1420"></a>
### 34.2 马尔可夫策略：动作只依赖当前状态

如果 Policy 是马尔可夫策略，那么只需知道当前状态 $s_t$ 就能确定动作的概率分布，不必再知道完整历史。

因此：

$$
P(a_0\mid s_0)=\pi(a_0\mid s_0)
$$

以及：

$$
\boxed{P(a_1\mid s_0,a_0,s_1)=\pi(a_1\mid s_1)}
$$

<a id="origin-1436"></a>
### 34.3 环境的马尔可夫性质：下一状态只依赖当前状态和动作

对于 MDP 环境：

$$
\boxed{P(s_2\mid s_0,a_0,s_1,a_1)=P(s_2\mid s_1,a_1)}
$$

也就是说，**在已知 $s_1,a_1$ 后，更早的 $s_0,a_0$ 不再提供预测 $s_2$ 所必需的额外信息。**

对第一步的环境转移，本来就有：

$$
P(s_1\mid s_0,a_0)
$$

将这些简化代入完整的链式法则，就得到：

$$
\boxed{
\begin{aligned}
P_\pi(\tau)
={}&\rho_0(s_0)\\
&\cdot \pi(a_0\mid s_0)\\
&\cdot P(s_1\mid s_0,a_0)\\
&\cdot \pi(a_1\mid s_1)\\
&\cdot P(s_2\mid s_1,a_1)
\end{aligned}
}
$$

这就是**两步轨迹的概率连乘公式**。

<a id="origin-1469"></a>
## 35. 第四步：推广到 $T$ 步

对于：

$$
\tau=(s_0,a_0,s_1,a_1,\ldots,a_{T-1},s_T)
$$

同样先用链式法则，再利用马尔可夫性质和马尔可夫策略的假设，得到：

$$
\begin{aligned}
P_\pi(\tau)
={}&\rho_0(s_0)\\
&\cdot\pi(a_0\mid s_0)P(s_1\mid s_0,a_0)\\
&\cdot\pi(a_1\mid s_1)P(s_2\mid s_1,a_1)\\
&\cdots\\
&\cdot\pi(a_{T-1}\mid s_{T-1})P(s_T\mid s_{T-1},a_{T-1})
\end{aligned}
$$

每一步的结构都是：

$$
\pi(a_t\mid s_t)P(s_{t+1}\mid s_t,a_t)
$$

把重复相乘的结构用 $\prod$ 表示，就得到：

$$
\boxed{
P_\pi(\tau)
=\rho_0(s_0)
\prod_{t=0}^{T-1}
\pi(a_t\mid s_t)P(s_{t+1}\mid s_t,a_t)
}
$$

**所以，“连乘”来自概率的链式法则；能写成如此简单的每一步乘积，则需要马尔可夫性质及马尔可夫策略假设。**

<a id="origin-1509"></a>
## 36. 它与 $P_\pi(s'\mid s)=\sum_a\pi(a\mid s)P(s'\mid s,a)$ 有什么关系？

首先，固定一个动作 $a$，动作和下一状态同时发生的条件联合概率为：

$$
P_\pi(a,s'\mid s)=\pi(a\mid s)P(s'\mid s,a)
$$

如果**只关心下一状态 $s'$，不关心到底选了哪个动作**，就要对所有可能动作求和：

$$
\boxed{
P_\pi(s'\mid s)
=\sum_a\pi(a\mid s)P(s'\mid s,a)
}
$$

而轨迹概率 $P_\pi(\tau)$ 研究的是**已经指定每个状态和动作的整条轨迹**，所以把各个指定步骤的条件概率连乘，而**不对动作求和**。

例如，如果轨迹已固定为 $(s_0,a_0,s_1)$：

$$
P_\pi(s_0,a_0,s_1)
=\rho_0(s_0)\pi(a_0\mid s_0)P(s_1\mid s_0,a_0)
$$

如果只问“从 $s_0$ 出发下一步到达 $s_1$ 的概率”，动作没有固定：

$$
P_\pi(s_1\mid s_0)
=\sum_{a_0}\pi(a_0\mid s_0)P(s_1\mid s_0,a_0)
$$

**两者不矛盾：指定动作就相乘；动作不确定、需要消去动作变量，就对动作求和。**

<a id="origin-1544"></a>
## 37. 一句话总结

> **概率链式法则**告诉我们：一条轨迹的联合概率可以拆成一系列条件概率的连乘；**MDP 的马尔可夫性质与马尔可夫策略**进一步告诉我们：每一步只需要当前状态和动作，于是最终得到 $P_\pi(\tau)=\rho_0(s_0)\prod_t\pi(a_t\mid s_t)P(s_{t+1}\mid s_t,a_t)$。

> 注意：如果策略依赖完整历史，而不是只依赖 $s_t$，链式法则仍然成立，但相应策略项一般需要写成 $\pi(a_t\mid s_0,a_0,\ldots,s_t)$，不能直接简化为 $\pi(a_t\mid s_t)$。


---

<a id="origin-1553"></a>
## 38. Policy Gradient 到底在优化什么

我们要最大化：

\[
J(\theta)
=
\sum_\tau
P_\theta(\tau)R(\tau)
\]

对参数求导：

\[
\nabla_\theta J
=
\sum_\tau
\nabla_\theta P_\theta(\tau)
R(\tau)
\]

问题来了：

\[
P_\theta(\tau)
\]

是一个复杂概率乘积。

**直接求导非常麻烦。**

这就引出最关键的问题：

> 为什么 Policy Gradient 里突然出现 \(\log\)？

---

<a id="origin-1590"></a>
## 39. 为什么连乘直接求导比较麻烦？

<a id="origin-1592"></a>
### 39.1 一、首先明确：不同时间步的概率不要求加起来等于 1

在强化学习中，策略

\[
\pi_\theta(a_t\mid s_t)
\]

表示：**参数为 \(\theta\) 的策略，在状态 \(s_t\) 下选择动作 \(a_t\) 的概率。**

需要区分两种情况。

<a id="origin-1604"></a>
#### 39.1.1 情况 1：同一个状态下，所有互斥动作的概率之和必须等于 1

例如在状态 \(s_1\) 下只有两个动作 A、B：

\[
\pi_\theta(A\mid s_1)=0.3,\qquad
\pi_\theta(B\mid s_1)=0.7
\]

因此：

\[
0.3+0.7=1
\]

<a id="origin-1619"></a>
#### 39.1.2 情况 2：不同时间步，实际选中动作的概率不要求加起来等于 1

假设一条轨迹包含三次选择：

| 时间步 | 当前状态 | 实际选中的动作 | 该动作被选中的概率 |
|---|---|---|---|
| 1 | \(s_1\) | \(a_1\) | 0.3 |
| 2 | \(s_2\) | \(a_2\) | 0.7 |
| 3 | \(s_3\) | \(a_3\) | 0.8 |

虽然：

\[
0.3+0.7+0.8=1.8>1
\]

**但没有问题：这些是三个不同状态/时间步中的条件概率，不是同一次决策中互斥动作的概率。**

如果初始状态已固定，且环境转移是确定性的，那么整条动作轨迹发生的概率为：

\[
P_\theta(\tau)
=\pi_\theta(a_1\mid s_1)\pi_\theta(a_2\mid s_2)\pi_\theta(a_3\mid s_3)
=0.3\times0.7\times0.8=0.168
\]

注意：**三个时间步使用的是同一套策略参数 \(\theta\)，只是输入状态不同。**

<a id="origin-1647"></a>
### 39.2 二、为什么连乘直接求导比较麻烦？

为了看到求导的区别，假设这三个时间步实际选中动作的概率分别为：

\[
p_1(\theta)=\theta,\quad p_2(\theta)=1-\theta,\quad p_3(\theta)=\theta,\qquad 0<\theta<1
\]

它们分别属于三个不同时间步，因此不要求 \(p_1+p_2+p_3=1\)。

整条轨迹的概率：

\[
P_\theta(\tau)=p_1p_2p_3=\theta(1-\theta)\theta
\]

如果直接求导，要使用**乘积求导法则**：

\[
\begin{aligned}
\frac{dP_\theta(\tau)}{d\theta}
&=p_1'p_2p_3+p_1p_2'p_3+p_1p_2p_3'\\
&=(1-\theta)\theta-\theta^2+\theta(1-\theta)\\
&=2\theta-3\theta^2
\end{aligned}
\]

三个因子产生三项；如果有 1000 个时间步，就会产生 1000 项，每一项还带着其余概率的乘积。

**每求一项，都要保留其余概率的乘积；步数越多，乘积求导的表达就越长。** 而且，**小概率连乘可能变得非常小**，例如 \(0.1^{1000}=10^{-1000}\)，直接计算可能**下溢**。

即有三个问题：

**1. 原始公式要求枚举所有可能轨迹，在大模型里不可行。**

**2. 直接求导的表达式很长，难以逐步计算，乘法运算量大。**

**3. 小概率连乘可能导致数值下溢，难以通过采样估计期望。**

**这不是说连乘不能求导，而是直接写出来会比较繁琐；自动微分软件实际上可以处理这种运算。**

<a id="origin-1688"></a>
### 39.3 三、取 Log 后为什么就方便了？

利用数学性质：

\[
\log(ab)=\log a+\log b
\]

所以整条轨迹的概率取对数后：

\[
\log P_\theta(\tau)=\log p_1+\log p_2+\log p_3
\]

此时求导：

\[
\frac{d\log P_\theta(\tau)}{d\theta}
=\frac{p_1'}{p_1}+\frac{p_2'}{p_2}+\frac{p_3'}{p_3}
\]

对于上面的例子：

\[
\boxed{
\frac{d\log P_\theta(\tau)}{d\theta}
=\frac1\theta-\frac1{1-\theta}+\frac1\theta
}
\]

如果轨迹有 1000 步，就写成：

\[
\boxed{
\nabla_\theta\log P_\theta(\tau)
=\sum_{t=1}^{1000}\nabla_\theta\log\pi_\theta(a_t\mid s_t)
}
\]

这里假设环境状态转移与初始状态分布不依赖 \(\theta\)。如果环境是随机的，完整轨迹概率还要乘上初始状态概率和环境转移概率，但它们的 Log 对 \(\theta\) 求导为零，因此结果仍然成立。

<a id="origin-1729"></a>
### 39.4 四、注意：取 Log 后，梯度本身变了，不能直接替换

一般而言：

\[
\nabla_\theta P_\theta(\tau)\neq\nabla_\theta\log P_\theta(\tau)
\]

真正使用的是链式法则得到的**恒等式**：

\[
\boxed{
\nabla_\theta P_\theta(\tau)
=P_\theta(\tau)\nabla_\theta\log P_\theta(\tau)
}
\]

代入连加形式：

\[
\boxed{
\nabla_\theta P_\theta(\tau)
=P_\theta(\tau)\sum_t\nabla_\theta\log\pi_\theta(a_t\mid s_t)
}
\]

用 \(\theta=0.2\) 验证三步例子：

\[
P_\theta(\tau)=0.2\times0.8\times0.2=0.032
\]

直接求导：

\[
2(0.2)-3(0.2)^2=0.28
\]

用 Log 的恒等式：

\[
0.032\times\left(\frac1{0.2}-\frac1{0.8}+\frac1{0.2}\right)
=0.032\times8.75=0.28
\]

**结果完全一致，并没有擅自改变原来的梯度。**


---

<a id="origin-1779"></a>
## 40. \(\log\) 到底怎么来的

数学上我们知道：

$$
\frac{d}{dx}\log f(x)
=
\frac{f'(x)}{f(x)}
$$

这是由复合函数求导得到的。

令：

$$
y=\log f(x)
$$

根据链式法则：

$$
\frac{dy}{dx}
=
\frac{1}{f(x)}\cdot f'(x)
$$

**因此（主要看这个公式）：**

$$
\frac{d}{dx}\log f(x)
=
\frac{f'(x)}{f(x)}
$$

将两边同时乘以 $f(x)$：

$$
f(x)\frac{d}{dx}\log f(x)
=
f'(x)
$$

所以可以写成：

$$
\boxed{
f'(x)
=
f(x)\frac{d}{dx}\log f(x)
}
$$

也就是说：

> **一个函数本身的导数，可以写成「函数本身 × 函数对数的导数」。**

**因此（看上面那个让看的公式）：**

\[
\nabla_\theta \log P_\theta
=
\frac{
\nabla_\theta P_\theta
}{
P_\theta
}
\]

所以：

\[
\boxed{
\nabla_\theta P_\theta
=
P_\theta
\nabla_\theta\log P_\theta
}
\]

这不是强化学习专用公式。

只是：

> 对数导数公式。

它也叫：

> Log-Derivative Trick

或者：

> Likelihood Ratio Trick

---

<a id="origin-1874"></a>
## 41. 把它代入 Policy Gradient

原来：

\[
\nabla_\theta J
=
\sum_\tau
\nabla_\theta P_\theta(\tau)
R(\tau)
\]

代入：

\[
\nabla_\theta P_\theta(\tau)
=
P_\theta(\tau)
\nabla_\theta\log P_\theta(\tau)
\]

得到：

\[
\nabla_\theta J
=
\sum_\tau
P_\theta(\tau)
\nabla_\theta\log P_\theta(\tau)
R(\tau)
\]

注意：

\[
\sum_\tau P_\theta(\tau)(\cdots)
\]

就是期望。

所以：

\[
\boxed{
\nabla_\theta J
=
\mathbb E_{\tau\sim\pi_\theta}
[
\nabla_\theta
\log P_\theta(\tau)
R(\tau)
]
}
\]

**上面这个公式就叫做Policy Gredient（策略梯度）。**

---

<a id="origin-1933"></a>
## 42. 为什么取 log 后更好

原来：

\[
P_\theta(\tau)
=
P(s_0)
\prod_t
\pi_\theta(a_t|s_t)
P(s_{t+1}|s_t,a_t)
\]

取 log：

\[
\log P_\theta(\tau)
=
\log P(s_0)
+
\sum_t
\log \pi_\theta(a_t|s_t)
+
\sum_t
\log P(s_{t+1}|s_t,a_t)
\]

乘法变成了加法。

---

<a id="origin-1964"></a>
## 43. 为什么环境项求导后消失，以及为什么最后从 \(R(\tau)\) 变成了 \(G_t\)

Policy 的参数是：

\[
\theta
\]

它只直接影响 Policy：

\[
\pi_\theta(a_t|s_t)
\]

而环境状态转移：

\[
P(s_{t+1}|s_t,a_t)
\]

并不由 Policy 参数 \(\theta\) 直接决定。

**因此，在前面25的：**

\[
\nabla_\theta \log P_\theta(\tau)
\]

中，初始状态概率：

\[
P(s_0)
\]

与 \(\theta\) 无关，所以：

\[
\nabla_\theta \log P(s_0)=0
\]

环境转移概率：

\[
P(s_{t+1}|s_t,a_t)
\]

同样不包含 Policy 参数 \(\theta\)，所以：

\[
\nabla_\theta
\log P(s_{t+1}|s_t,a_t)
=
0
\]

**因此最终只剩下 Policy 这一部分：**

\[
\boxed{
\nabla_\theta
\log P_\theta(\tau)
=
\sum_t
\nabla_\theta
\log \pi_\theta(a_t|s_t)
}
\]

---

<a id="origin-2034"></a>
### 43.1 先不要急着写成 \(G_t\)

把上面的结果代回前面已经得到的：

\[
\nabla_\theta J
=
\mathbb E_{\tau\sim\pi_\theta}
\left[
\nabla_\theta
\log P_\theta(\tau)
R(\tau)
\right]
\]

**根据27最后的公式带入，首先应该得到：**

\[
\boxed{
\nabla_\theta J
=
\mathbb E
\left[
\left(
\sum_t
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\right)
R(\tau)
\right]
}
\]

也可以把求和移进去：

\[
\boxed{
\nabla_\theta J
=
\mathbb E
\left[
\sum_t
\nabla_\theta
\log\pi_\theta(a_t|s_t)
R(\tau)
\right]
}
\]

**到这一步为止，\(R(\tau)\) 还没有变成 \(G_t\)。**

这里：

\[
R(\tau)
\]

表示整条轨迹的总回报。

例如：

\[
R(\tau)
=
r_0+r_1+r_2+r_3
\]

那么上面的式子实际上相当于：

\[
\begin{aligned}
\nabla_\theta J
=
\mathbb E[
&
\nabla_\theta\log\pi_\theta(a_0|s_0)R(\tau)
\\
+&
\nabla_\theta\log\pi_\theta(a_1|s_1)R(\tau)
\\
+&
\nabla_\theta\log\pi_\theta(a_2|s_2)R(\tau)
\\
+&
\nabla_\theta\log\pi_\theta(a_3|s_3)R(\tau)
]
\end{aligned}
\]

也就是说：

> 此时每一个动作 \(a_t\)，都乘上了整条轨迹的总奖励 \(R(\tau)\)。

---

<a id="origin-2129"></a>
### 43.2 但是这样会出现一个问题

假设：

\[
R(\tau)
=
r_0+r_1+r_2+r_3
\]

现在看第 \(2\) 步的动作：

\[
a_2
\]

它对应的梯度项是：

\[
\nabla_\theta
\log\pi_\theta(a_2|s_2)
R(\tau)
\]

展开：

\[
=
\nabla_\theta
\log\pi_\theta(a_2|s_2)
(r_0+r_1+r_2+r_3)
\]

但是这里：

\[
r_0,\quad r_1
\]

在执行 \(a_2\) 之前就已经发生了。

时间顺序是：

```text
执行 a0
↓
得到 r0

执行 a1
↓
得到 r1

执行 a2
↓
得到 r2

执行 a3
↓
得到 r3
```

因此：

\[
a_2
\]

不可能再反过来影响：

\[
r_0,\quad r_1
\]

所以，对于第 \(t\) 步动作来说：

> 过去已经发生的奖励，与当前动作没有因果关系。

因此没有必要让：

\[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\]

继续乘前面的那些奖励。

---

<a id="origin-2217"></a>
### 43.3 把整条轨迹回报拆成“过去 + 未来”

对于第 \(t\) 步，可以把：

\[
R(\tau)
\]

拆成：

\[
R(\tau)
=
\underbrace{
r_0+r_1+\cdots+r_{t-1}
}_{\text{过去奖励}}
+
\underbrace{
r_t+r_{t+1}+\cdots
}_{\text{从当前开始的未来奖励}}
\]

定义：

\[
\boxed{
G_t
=
r_t+r_{t+1}+r_{t+2}+\cdots
}
\]

这个 \(G_t\) 就叫：

> **Return from time \(t\)**  
> 或者  
> **Reward-to-go**

如果考虑折扣因子 \(\gamma\)，那么：

\[
\boxed{
G_t
=
r_t
+
\gamma r_{t+1}
+
\gamma^2 r_{t+2}
+
\cdots
}
\]

因此：

\[
R(\tau)
=
\text{过去奖励}
+
G_t
\]

---

<a id="origin-2283"></a>
### 43.4 为什么过去奖励可以严格去掉？（请课外根据讲义推导）

对于第 \(t\) 步：

\[
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
R(\tau)
\right]
\]

拆成：

\[
\begin{aligned}
&
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
(r_0+\cdots+r_{t-1})
\right]
\\
+&
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
G_t
\right]
\end{aligned}
\]

第一项其实等于：

\[
0
\]

原因是过去奖励在选择 \(a_t\) 之前已经确定，而：

\[
\mathbb E_{a_t\sim\pi_\theta}
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\right]
=
0
\]

证明：

<a id="origin-2338"></a>
#### 43.4.1 为什么这个期望等式成立？

我们要证明：

\[
\mathbb E_{a_t\sim\pi_\theta}
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\right]
=
0
\]

其中最关键的是理解前两个等式分别是怎么来的。

---

<a id="origin-2356"></a>
#### 43.4.2 第一个等式：把“期望”展开成求和

原式：

\[
\mathbb E_{a_t\sim\pi_\theta}
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\right]
\]

变成：

\[
\sum_{a_t}
\pi_\theta(a_t|s_t)
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\]

这里使用的是离散随机变量最基本的期望公式：

\[
\boxed{
\mathbb E[f(X)]
=
\sum_x P(X=x)f(x)
}
\]

在这里：

\[
X=a_t
\]

动作 \(a_t\) 的概率分布是：

\[
P(a_t)=\pi_\theta(a_t|s_t)
\]

而我们要求期望的那个函数是：

\[
f(a_t)
=
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\]

所以直接代入：

\[
\mathbb E_{a_t\sim\pi_\theta}
[f(a_t)]
=
\sum_{a_t}
\pi_\theta(a_t|s_t)f(a_t)
\]

得到：

\[
\boxed{
\mathbb E_{a_t\sim\pi_\theta}
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\right]
=
\sum_{a_t}
\pi_\theta(a_t|s_t)
\nabla_\theta
\log\pi_\theta(a_t|s_t)
}
\]

<a id="origin-2435"></a>
##### 43.4.2.1 一个简单例子

假设当前状态下只有三个动作：

\[
a_1,\quad a_2,\quad a_3
\]

Policy 给出的概率为：

\[
\pi(a_1|s)=0.2
\]

\[
\pi(a_2|s)=0.3
\]

\[
\pi(a_3|s)=0.5
\]

那么某个函数 \(f(a)\) 的期望就是：

\[
\mathbb E[f(a)]
=
0.2f(a_1)
+
0.3f(a_2)
+
0.5f(a_3)
\]

现在只需要把：

\[
f(a)
\]

换成：

\[
\nabla_\theta\log\pi_\theta(a|s)
\]

即可。

---

<a id="origin-2485"></a>
#### 43.4.3 第二个等式：为什么

\[
\pi_\theta(a_t|s_t)
\nabla_\theta
\log\pi_\theta(a_t|s_t)
=
\nabla_\theta
\pi_\theta(a_t|s_t)
\]

这里使用的是对数求导公式：

\[
\boxed{
\frac{d}{dx}\log f(x)
=
\frac{f'(x)}{f(x)}
}
\]

因此：

\[
\frac{d}{dx}\log f(x)
=
\frac{1}{f(x)}
\frac{df(x)}{dx}
\]

两边乘以：

\[
f(x)
\]

得到：

\[
\boxed{
f(x)
\frac{d}{dx}\log f(x)
=
\frac{df(x)}{dx}
}
\]

把：

\[
f(x)
\]

替换成：

\[
\pi_\theta(a_t|s_t)
\]

把：

\[
\frac{d}{dx}
\]

替换成：

\[
\nabla_\theta
\]

于是：

\[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
=
\frac{
\nabla_\theta\pi_\theta(a_t|s_t)
}{
\pi_\theta(a_t|s_t)
}
\]

两边乘以：

\[
\pi_\theta(a_t|s_t)
\]

得到：

\[
\boxed{
\pi_\theta(a_t|s_t)
\nabla_\theta
\log\pi_\theta(a_t|s_t)
=
\nabla_\theta
\pi_\theta(a_t|s_t)
}
\]

因此：

\[
\sum_{a_t}
\pi_\theta(a_t|s_t)
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\]

就可以变成：

\[
\boxed{
\sum_{a_t}
\nabla_\theta
\pi_\theta(a_t|s_t)
}
\]

---

<a id="origin-2609"></a>
#### 43.4.4 后面为什么又能继续变形？

接下来：

\[
\sum_{a_t}
\nabla_\theta
\pi_\theta(a_t|s_t)
\]

可以写成：

\[
\nabla_\theta
\sum_{a_t}
\pi_\theta(a_t|s_t)
\]

因为“求导”和“有限求和”可以交换顺序：

\[
\boxed{
\sum_i \nabla_\theta f_i
=
\nabla_\theta \sum_i f_i
}
\]

而对于一个概率分布来说，所有动作概率之和永远是：

\[
\sum_{a_t}
\pi_\theta(a_t|s_t)
=
1
\]

因此：

\[
\nabla_\theta
\sum_{a_t}
\pi_\theta(a_t|s_t)
=
\nabla_\theta 1
=
0
\]

所以最终：

\[
\boxed{
\mathbb E_{a_t\sim\pi_\theta}
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\right]
=
0
}
\]

---

<a id="origin-2674"></a>
### 43.5 把整个证明连起来

\[
\begin{aligned}
\mathbb E_{a_t\sim\pi_\theta}
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\right]
&=
\sum_{a_t}
\pi_\theta(a_t|s_t)
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\\
&=
\sum_{a_t}
\nabla_\theta
\pi_\theta(a_t|s_t)
\\
&=
\nabla_\theta
\sum_{a_t}
\pi_\theta(a_t|s_t)
\\
&=
\nabla_\theta 1
\\
&=
0
\end{aligned}
\]

其中：

- 第一个等式：使用期望定义

\[
\mathbb E[f(X)]
=
\sum_x P(x)f(x)
\]

- 第二个等式：使用对数求导公式

\[
\pi\nabla\log\pi
=
\nabla\pi
\]

- 第三个等式：求导和求和交换顺序

\[
\sum_i \nabla f_i
=
\nabla \sum_i f_i
\]

- 最后一步：所有动作的概率之和为 1

\[
\sum_a \pi_\theta(a|s)=1
\]

所以：

\[
\nabla_\theta 1=0
\]

---

<a id="origin-2747"></a>
### 43.6 一句话记忆

```text
期望
↓
展开成“概率 × 对应值”
↓
π × ∇logπ = ∇π
↓
所有动作概率求和 = 1
↓
对 1 求导 = 0
```

因此：

\[
\boxed{
\mathbb E[\nabla_\theta\log\pi_\theta(a|s)]
=
0
}
\]



**所以**

\[
\boxed{
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
R(\tau)
\right]
=
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
G_t
\right]
}
\]

**这就是为什么原来的：**

\[
R(\tau)
\]

**最终可以替换成：**

\[
G_t
\]

---

<a id="origin-2807"></a>
## 44. 这个公式直觉上到底是什么意思

\[
\nabla_\theta J=\nabla_\theta
\log\pi_\theta(a_t|s_t)
G_t
\]

可以拆成：

<a id="origin-2817"></a>
### 44.1 第一部分

\[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\]

表示：

> 参数应该怎么改，才能改变这个 Action 的概率。

<a id="origin-2828"></a>
### 44.2 第二部分

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

<a id="origin-2850"></a>
## 45. 继续改进：为什么不直接用 Reward / Return，而要 Advantage

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

---

<a id="origin-2909"></a>
### 45.1 一、先把原来的案例讲准确

假设智能体正在玩游戏，会遇到两个难度不同的状态。

<a id="origin-2913"></a>
#### 45.1.1 状态 A：困难关卡

在当前策略下，智能体从这个状态继续玩下去，**平均预期累计回报**是 1 分：

\[
V(s_A)=1
\]

**有一个 Action**，执行它后，**预期累计回报**是 5 分：

\[
Q(s_A,a)=5
\]

因此：

\[
A(s_A,a)=Q(s_A,a)-V(s_A)=5-1=\boxed{+4}
\]

**这个 Action 比当前状态下**的平均水平**好 4 分**，我们应该提高它被选中的概率。

<a id="origin-2935"></a>
#### 45.1.2 状态 B：简单关卡

在当前策略下，智能体从这个状态继续玩下去，平均预期累计回报是 100 分：

\[
V(s_B)=100
\]

**现在有一个 Action，执行它后，** 预期累计回报同样是 5 分：

\[
Q(s_B,a)=5
\]

因此：

\[
A(s_B,a)=Q(s_B,a)-V(s_B)=5-100=\boxed{-95}
\]

**这个 Action 比当前状态下**的平均水平**差 95 分**，我们应该降低它被选中的概率。

| 对比项 | 状态 A | 状态 B |
|---|---:|---:|
| 当前状态的平均预期回报 \(V(s)\) | 1 | 100 |
| 该 Action 的预期回报 \(Q(s,a)\) | 5 | 5 |
| Advantage：\(Q-V\) | **+4** | **−95** |
| 对这个 Action 的期望优化方向 | 提高概率 | 降低概率 |

**这个例子说明的不是「从 1 到 5 增长了 400%，所以进步巨大」。** Advantage **不是比值，也不是百分比**，它只做减法：

\[
\boxed{A(s,a)=Q(s,a)-V(s)}
\]

因此，从 1 到 6 与从 100 到 105，Advantage 都是 +5；但本例比较的是 **1 与 5（差 +4）**、**100 与 5（差 −95）**。这两个动作相对各自状态的表现确实不同。

---

<a id="origin-2974"></a>
### 45.2 二、如果直接用 Return 训练，会发生什么？

最原始的 REINFORCE 使用采样得到的累计回报 \(G_t\) 构建损失：

\[
\boxed{L_{\mathrm{REINFORCE}}=-G_t\log\pi_\theta(a_t\mid s_t)}
\]

假设两个状态中，这次实际采样的累计回报都恰好是：

\[
G_t=5
\]

**因为\(G_t\)是正值**，那么状态 A 的单样本损失为：

\[
L_A=-5\log\pi_\theta(a\mid s_A)
\]

**因为\(G_t\)是正值**，状态 B 的单样本损失也是：

\[
L_B=-5\log\pi_\theta(a\mid s_B)
\]

对参数求梯度：

\[
\nabla_\theta L=-5\nabla_\theta\log\pi_\theta(a\mid s)
\]

对这个单样本做梯度下降，会倾向于**提高该状态下刚刚采样到的 Action 的概率**。

因此，在这个例子中：

- 状态 A：5 分比平均的 1 分好，鼓励采样动作是合理的。
- 状态 B：5 分比平均的 100 分差，但单次 REINFORCE 仍会鼓励这个采样动作。

**注意：这不代表原始 REINFORCE 理论上训练方向错误。** 它的正确性体现在对所有可能采样结果求期望后；这里看到的是**某一次采样梯度**可能不够有针对性。

<a id="origin-3015"></a>
### 45.3 三、减去状态的预期回报后，训练信号变得更有针对性

在训练中，我们通常不知道某个动作的精确 \(Q(s,a)\)，但可以用一次采样的累计回报 \(G_t\) 来估计它。最直观的 Advantage 估计是：

\[
\boxed{\widehat A_t=G_t-V(s_t)}
\]

于是 Actor 的样本损失可以写成：

\[
\boxed{L=-\widehat A_t\log\pi_\theta(a_t\mid s_t)}
\]

在本例中，两个动作的采样 Return 都是 5：

**状态 A：**

\[
\widehat A_A=5-1=+4
\]

\[
L_A=-4\log\pi_\theta(a\mid s_A)
\]

梯度下降倾向于**提高**这个动作的概率。

**状态 B：**

\[
\widehat A_B=5-100=-95
\]

\[
L_B=95\log\pi_\theta(a\mid s_B)
\]

梯度下降倾向于**降低**这个动作的概率。

这意味着：

> 不再单纯问「这次拿到几分」，而是问「**比当前状态下正常预期的表现好多少**」。

不过，\(G_t\) 只是一次随机结果，不一定等于真实的 \(Q(s,a)\)。因此 \(\widehat A_t\) 也可能包含采样噪声；后续需要 Critic 和 GAE 来做更好的估计。

---

<a id="origin-3063"></a>
## 46. 直接用 \(G_t-V(s_t)\) 做 Advantage 的问题：为什么引入 TD 和 GAE

前面我们已经知道，Policy Gradient 中需要：

\[
\boxed{
A_t
}
\]

来告诉 Actor：

> 当前这个动作 \(a_t\)，到底比模型原本预期的好多少。

---

<a id="origin-3079"></a>
### 46.1 最直接的方法：用 \(G_t\) 估计 \(Q(s_t,a_t)\)

理论上：

\[
\boxed{
A_t
=
Q(s_t,a_t)-V(s_t)
}
\]

但是：

\[
Q(s_t,a_t)
\]

并不知道。

而一次 Rollout 中，我们可以得到真实的 Return：

\[
\boxed{
G_t
=
r_t
+
\gamma r_{t+1}
+
\gamma^2r_{t+2}
+\cdots
}
\]

所以可以用：

\[
\boxed{
Q(s_t,a_t)\approx G_t
}
\]

于是：

\[
\boxed{
A_t
\approx
G_t-V(s_t)
}
\]

这个 Advantage 已经可以直接拿去训练 Actor。

例如：

\[
G_t=10
\]

Critic 预测：

\[
V(s_t)=7
\]

那么：

\[
A_t
=
10-7
=
3
\]

说明：

> 这个动作最后的实际表现，比模型原本预计的好 3。

---

<a id="origin-3162"></a>
### 46.2 问题：完整的 \(G_t\) 方差很大

问题在于：

\[
G_t
\]

包含从当前时刻一直到整个 Rollout 结束的所有 Reward。

例如：

\[
G_t
=
r_t
+
\gamma r_{t+1}
+
\gamma^2r_{t+2}
+\cdots
+
\gamma^{T-t}r_T
\]

后面的每一步的\(r\)的任何随机变化都会影响：

\[
G_t
\]

**也就是\(\gamma r_{t+1}+\gamma^2r_{t+2}+\cdots\)的值会导致\(G_t\)方差太大。**

所以同一个：

\[
(s_t,a_t)
\]

不同 Rollout 中可能得到：

\[
G_t^{(1)}=5
\]

\[
G_t^{(2)}=12
\]

\[
G_t^{(3)}=7
\]

于是：

\[
A_t
=
G_t-V(s_t)
\]

也会跟着剧烈变化。

因此：

\[
\boxed{
\text{直接使用完整 }G_t
\text{ 会让 Advantage 方差比较大}
}
\]

而 PPO 的 Actor 最终就是直接使用 Advantage：

\[
L^{PPO}
\propto
\rho_tA_t
\]

所以：

\[
A_t
\]

如果非常不稳定，Actor 的梯度也会更加不稳定。

这就引出 TD。

---

<a id="origin-3254"></a>
## 47. TD 到底是什么

TD：

> Temporal Difference

中文：

> 时序差分。

先不用公式。

---

<a id="origin-3268"></a>
### 47.1 一个自然语言例子

当前状态 A：

```text
Critic 预测：
V(A)=100
```

执行一步以后：

```text
立刻 Reward = 10
进入状态 B
```

Critic 说：

```text
V(B)=110
```

先设：

\[
\gamma=1
\]

那走一步以后，我们对 A 有了一个新的估计：

```text
立即得到10
+
未来从B预计还能得到110
=
120
```

但原来预测：

```text
100
```

差：

\[
120-100=20
\]

这 20 就是：

> TD Error。

---

<a id="origin-3324"></a>
## 48. TD 公式

\[
\boxed{
\delta_t
=
r_t
+
\gamma V(s_{t+1})
-
V(s_t)
}
\]

解释：

\[
r_t+\gamma V(s_{t+1})
\]

叫：

> 走一步以后，根据新信息得到的新价值估计。

而：

\[
V(s_t)
\]

是：

> 原来的预测。

所以：

\[
\boxed{
TD Error
=
新估计
-
旧估计
}
\]

---

<a id="origin-3372"></a>
## 49. TD 为什么能估计 Advantage

我们知道：

\[
Q(s_t,a_t)
\]

表示：

> 当前执行这个 Action 后，未来能得到多少。

如果只展开一步：

\[
Q(s_t,a_t)
\approx
r_t+\gamma V(s_{t+1})
\]

**之所以是约等于，是因为\(Q\)是理论上严格定义的对\(G_t\)的真实期望值，而\(V\)是神经网络的一个估算值。**

而：

\[
A(s_t,a_t)
=
Q(s_t,a_t)-V(s_t)
\]

代入：

\[
A(s_t,a_t)
\approx
r_t
+
\gamma V(s_{t+1})
-
V(s_t)
\]

所以：

\[
\boxed{
A_t\approx\delta_t
}
\]

更严谨：

如果 Value 是正确的，则：

\[
\mathbb E[
\delta_t
|
s_t,a_t
]
=
A^\pi(s_t,a_t)
\]

**所以在这里可以基本上理解为：**

\[
\boxed{
TD Error 是 Advantage 的一步估计
}
\]

**和之前30节的原始公式**

\[
A_t
=
G_t-V(s_t)
\]

**相比，不同的地方在于这里用\(r_t+\gamma V(s_{t+1})\)取代了\(G_t\)，方差变小了，但是偏差会变大（见下方解释）。**

---

<a id="origin-3456"></a>
## 50. 为什么不直接只用 TD

回忆我们的梯度下降公式：

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

**现在已经用TD替代了\(G_t\)，那为什么这里不直接用\(\delta_t\)来近似\(A_t\)，然后开始优化参数？**

**因为只看一步可能太短视。**

假设：

```text
当前动作：
立刻 Reward = -1
```

看起来不好。

但这个 Action 让机器人进入了一个非常好的区域：

```text
后面 +100
```

只看当前一步：

> 可能低估这个动作。

所以我们想：

> 多看几步，但又不要一直看到终点。

这就引出 GAE。

---

<a id="origin-3504"></a>
## 51. Bias 和 Variance 到底是什么

理解 GAE 之前必须理解这两个概念。

<a id="origin-3508"></a>
### 51.1 Bias

真实值：

\[
10
\]

某个估计器每次：

```text
8
8
8
8
8
```

很稳定，但永远少 2。

所以：

```text
Bias 大
Variance 小
```

---

<a id="origin-3537"></a>
### 51.2 Variance

真实平均：

\[
10
\]

另一个估计器：

```text
0
20
3
17
10
```

平均可能接近 10，但每次差别巨大。

所以：

```text
Bias 小
Variance 大
```

---

<a id="origin-3566"></a>
## 52. 为什么完整 Return 方差大

完整 Return：

\[
G_t
=
r_t
+
\gamma r_{t+1}
+
\gamma^2r_{t+2}
+\cdots
\]

未来每一步都可能随机。

**注意：\(\gamma r_{t+1}+\gamma^2r_{t+2}+\cdots\)替换成\(\gamma V(s_{t+1})\)即为TD Error。**

例如：

```text
第1次 rollout：G=2
第2次 rollout：G=18
第3次 rollout：G=5
第4次 rollout：G=15
```

所以：

> 每次样本波动很大。

因此：

\[
\boxed{
Variance 高
}
\]

**但它是真实的rollout奖励值之和，不是一个可能错误的 Critic给出的估计值：**

\[
\boxed{
Bias 相对低
}
\]

---

<a id="origin-3616"></a>
## 53. 为什么一步 TD 方差小

TD：

\[
r_t+\gamma V(s_{t+1})
\]

只真实看：

> 下一步。

再远的未来：

> 被 Critic 的平均预测 \(V(s_{t+1})\) 压缩掉了。

**可以理解为Critic每次给出的值相对平均（因为是训练好的神经网络），所以未来随机性少很多。**

因此：

\[
\boxed{
Variance 小
}
\]

---

<a id="origin-3644"></a>
## 54. 为什么一步 TD Bias 可能大

如果：

\[
V(s_{t+1})
\]

预测错了：

```text
真实价值：10
Critic 预测：7
```

那 TD Target 一开始就偏了。

所以：

\[
\boxed{
Bias 可能大
}
\]

---

<a id="origin-3671"></a>
## 55. 偏差与方差：为什么 GAE 要在两者之间折中？

<a id="origin-3673"></a>
## 56. 偏差（Bias）是什么意思？

**偏差：多次估计的平均值与真实值之间相差多少。**

例如，真实 Advantage 是 **5**，但多次估计的平均值只有 **3**，就说明估计存在偏差。

- **偏差高：** 长期高估或低估动作的好坏，**可能让策略持续朝错误方向更新。**
- **偏差低：** 平均判断更接近真实情况，策略更新方向通常更可靠。

<a id="origin-3682"></a>
## 57. 方差（Variance）是什么意思？

**方差：多次估计结果围绕其平均值波动有多大。**

例如，真实 Advantage 是 **5**，且估计的平均值也是 **5**：

- **高方差：** 三次估计分别是 `-10、5、20`，波动很大。
- **低方差：** 三次估计分别是 `4、5、6`，比较稳定。

因此：

- **方差高：** 同一个动作有时被鼓励、有时被惩罚，**梯度更新容易反复波动，训练效率低。**
- **方差低：** 梯度估计更加稳定，随机奖励的干扰更小，训练通常更容易收敛。

<a id="origin-3696"></a>
## 58. 一句话区分

> **偏差看“平均而言准不准”，方差看“每次估计稳不稳”。**

| 情况 | 意味着什么 | 主要问题或好处 |
|---|---|---|
| 高偏差、低方差 | 每次都很稳定，但平均判断偏离真实值 | 容易稳定地学错 |
| 低偏差、高方差 | 平均判断准确，但单次估计起伏很大 | 更新不稳定，需要更多样本抵消波动 |
| 低偏差、低方差 | 既接近真实值，又比较稳定 | 理想状态，训练通常更有效率 |

---

<a id="origin-3708"></a>
## 59. GAE 的作用

GAE：

> Generalized Advantage Estimation

把多个未来 TD Error 组合起来：

\[
\boxed{
A_t^{GAE}
=
\delta_t
+
\gamma\lambda\delta_{t+1}
+
(\gamma\lambda)^2\delta_{t+2}
+\cdots
}
\]

它的形式和 Return：

\[
\boxed{
G_t
=
r_t
+
\gamma r_{t+1}
+
\gamma^2 r_{t+2}
+\cdots
}
\]

非常相似。

但二者表达的含义不同：

- \(G_t\)：把未来多个 Reward 累加起来，表示从 \(t\) 时刻开始能够获得多少未来回报。
- \(A_t^{GAE}\)：把未来多个 TD Error 按权重累加起来，用来估计 **在 \(t\) 时刻状态 \(s_t\) 下，实际选择动作 \(a_t\) 相比当前策略平均水平到底好多少。**

因此：

\[
\boxed{
A_t^{GAE}
\approx
A^\pi(s_t,a_t)
}
\]

这里虽然使用了未来的：

\[
\delta_t,\delta_{t+1},\delta_{t+2},\cdots
\]

但这些未来 TD Error 的目的，都是为了更准确地评价：

\[
\boxed{
t\text{ 时刻已经选择的动作 }a_t
}
\]

因为动作 \(a_t\) 的影响可能不会立刻全部体现在 \(r_t\) 中，而可能继续影响后面的状态和奖励。

所以可以理解成：

> **\(G_t\) 是用未来 Reward 评价“未来总共能拿多少分”；而 \(A_t^{GAE}\) 是用未来多个 TD Error 反过来评价“当前这个动作 \(a_t\) 到底比平均水平好多少”。**

---

<a id="origin-3783"></a>
## 60. \(\lambda\) 到底在控制什么

如果：

\[
\lambda=0
\]

那么：

\[
A_t=\delta_t
\]

**只看一步。**

特点：

```text
方差小
Bias 可能高
```

如果：

\[
\lambda\rightarrow1
\]

**会考虑更长未来。**

特点：

```text
Bias 下降
Variance 上升
```

所以常用：

\[
\lambda=0.95
\]

做折中。

---

<a id="origin-3831"></a>
### 60.1 GAE 最重要的用途：给 Actor 算 Advantage

PPO Actor 的核心公式：

\[
\boxed{
L^{PPO}
=
\mathbb E_t
\left[
\min
\left(
\rho_t\hat A_t,
\operatorname{clip}
(
\rho_t,
1-\epsilon,
1+\epsilon
)
\hat A_t
\right)
\right]
}
\]

这里：

\[
\boxed{
\hat A_t
}
\]

实际 PPO 中通常就是：

\[
\boxed{
\hat A_t^{GAE}
}
\]

所以：


<a id="origin-3875"></a>
#### 60.1.1 TD + GAE 首先是为了得到更稳定的 Advantage 给 Actor 使用。

这才是引入 GAE 的主线。

---

<a id="origin-3881"></a>
## 61. GAE 为什么代码倒着算

GAE 的原始公式是：

\[
\boxed{
A_t^{GAE}
=
\delta_t
+
\gamma\lambda\delta_{t+1}
+
(\gamma\lambda)^2\delta_{t+2}
+
(\gamma\lambda)^3\delta_{t+3}
+\cdots
}
\]

这里：

\[
\delta_t
=
r_t+\gamma V(s_{t+1})-V(s_t)
\]

表示第 \(t\) 步的 TD Error。

---

<a id="origin-3912"></a>
### 61.1 先看 \(A_t\)

GAE 写成：

\[
A_t
=
\delta_t
+
\gamma\lambda\delta_{t+1}
+
(\gamma\lambda)^2\delta_{t+2}
+
(\gamma\lambda)^3\delta_{t+3}
+\cdots
\]

再看下一时刻：

\[
A_{t+1}
=
\delta_{t+1}
+
\gamma\lambda\delta_{t+2}
+
(\gamma\lambda)^2\delta_{t+3}
+\cdots
\]

现在把：

\[
A_{t+1}
\]

整体乘以：

\[
\gamma\lambda
\]

得到：

\[
\gamma\lambda A_{t+1}
=
\gamma\lambda\delta_{t+1}
+
(\gamma\lambda)^2\delta_{t+2}
+
(\gamma\lambda)^3\delta_{t+3}
+\cdots
\]

你会发现：

\[
\gamma\lambda A_{t+1}
\]

正好就是 \(A_t\) 中除了第一项：

\[
\delta_t
\]

之外的所有部分。

所以：

\[
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
\]

也就是：

\[
\boxed{
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
}
\]

这就是 GAE 的递推公式。

---

<a id="origin-4007"></a>
### 61.2 为什么因此必须倒着算？

因为：

\[
A_t
\]

依赖：

\[
A_{t+1}
\]

例如：

\[
A_0
=
\delta_0+\gamma\lambda A_1
\]

想算：

\[
A_0
\]

就必须先知道：

\[
A_1
\]

但是：

\[
A_1
=
\delta_1+\gamma\lambda A_2
\]

所以又必须先知道：

\[
A_2
\]

继续：

\[
A_2
=
\delta_2+\gamma\lambda A_3
\]

所以整个依赖关系是：

```text
A0 依赖 A1
A1 依赖 A2
A2 依赖 A3
A3 依赖 A4
...
```

因此不能直接从：

\[
A_0
\]

开始算。

必须先找到最后一步。

---

<a id="origin-4085"></a>
### 61.3 从最后一步开始

假设一条 trajectory 只有 4 步：

\[
t=0,1,2,3
\]

对应：

\[
\delta_0,\delta_1,\delta_2,\delta_3
\]

如果第 3 步以后 episode 结束，那么后面已经没有：

\[
A_4
\]

因此可以认为：

\[
A_4=0
\]

所以：

\[
A_3
=
\delta_3+\gamma\lambda A_4
\]

变成：

\[
A_3
=
\delta_3
\]

于是先算：

\[
\boxed{
A_3=\delta_3
}
\]

然后就可以继续往前。

---

<a id="origin-4139"></a>
### 61.4 再算 \(A_2\)

已经知道：

\[
A_3
\]

所以：

\[
A_2
=
\delta_2
+
\gamma\lambda A_3
\]

---

<a id="origin-4159"></a>
### 61.5 再算 \(A_1\)

已经知道：

\[
A_2
\]

所以：

\[
A_1
=
\delta_1
+
\gamma\lambda A_2
\]

---

<a id="origin-4179"></a>
### 61.6 最后算 \(A_0\)

已经知道：

\[
A_1
\]

所以：

\[
A_0
=
\delta_0
+
\gamma\lambda A_1
\]

因此真正的计算顺序是：

\[
\boxed{
A_3
\rightarrow
A_2
\rightarrow
A_1
\rightarrow
A_0
}
\]

也就是：

> 从最后一步开始，向前递推。

这就是为什么 GAE 代码通常是倒着遍历 trajectory：


```python
gae = 0

for t in reversed(range(T)):
    delta = reward[t] + gamma * value[t+1] - value[t]
    gae = delta + gamma * lam * gae
    advantage[t] = gae
```

---

<a id="origin-4229"></a>
## 62. 为什么 Policy Gradient 最后变成了 Loss？

**核心理解：我们最初想优化的是期望 Reward，经过求导和一系列推导后，又根据得到的梯度，反过来构造了一个方便 PyTorch 训练的新 Loss。**

<a id="origin-4233"></a>
## 63. 最初的目标函数

\[
J(\theta)=\sum_\tau P_\theta(\tau)R(\tau)
\]

我们希望调整 Policy Model 的参数，使期望 Reward 最大。

<a id="origin-4241"></a>
## 64. 经过一系列求导和推导

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

<a id="origin-4258"></a>
## 65. 根据梯度反过来构造 Loss

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

<a id="origin-4303"></a>
## 66. 最终总结

最初我们希望最大化：

\[
J(\theta)=\sum_\tau P_\theta(\tau)R(\tau)
\]

经过推导得到了 Policy Gradient，然后根据这个梯度，反过来构造了新的 Loss。

**注意：**

**- 两个目标函数本身不恒等。
****- 新 Loss 是根据原始目标函数的梯度构造出来的。**
**- 在上述条件下，两者的期望梯度方向等价（考虑最大化与最小化的负号）。**
**- 所以我们可以利用新 Loss 来训练 Policy Model。**

这种新构造的 Loss 就叫作 **Surrogate Loss（代理损失函数）**。

---

<a id="origin-4324"></a>
## 67. Critic 为什么出现

回到Critic的定义，即想要预估\(G_t\)，因为如果我们每次都要等完整 trajectory 结束，才能知道：

\[
G_t
\]

会有两个问题：

1. 延迟很长；
2. 方差很大。

所以训练一个 Critic：

\[
V_\phi(s)
\]

用来估计：

> 现在这个局面未来大概值多少。

---

<a id="origin-4349"></a>
## 68. Critic 的 \(V\) 到底怎么训练出来

最简单情况：

假设某状态：

\[
s_t
\]

Critic 当前预测：

\[
V_\phi(s_t)=5
\]

但这次真实 Rollout 最后算出来：

\[
G_t=8
\]

那么 Value Loss：

\[
\boxed{
L_V
=
(V_\phi(s_t)-G_t)^2
}
\]

反向传播后：

```text
5 → 5.6 → 6.3 → 7.2 → ...
```

逐渐接近 8。

所以：

\[
\boxed{
Critic 是从 Rollout 产生的未来回报中学出来的
}
\]

---

<a id="origin-4399"></a>
## 69. 为什么 \(V_t^{target}=A_t+V(s_t)\)

最基础定义：

\[
A=Q-V
\]

移项：

\[
Q=A+V
\]

所以：

\[
\boxed{
V_t^{target}
=
A_t+V_{\text{old}}(s_t)
}
\]

可以理解成：

> 原本估计值 + 实际比预期好/差多少 = 新目标。

**即我们要训练 Critic，让它在输入状态 \(s_t\) 时输出的 \(V_\phi(s_t)\)，尽量接近这个状态真实的未来回报 \(G_t（期望值为Q）\)，即上面的\(Q\)。**

---

<a id="origin-4431"></a>
## 70. 一个 Critic 训练数值例子

假设：

\[
V_{\text{old}}(s_t)=5
\]

GAE：

\[
A_t=2
\]

说明：

> 实际比原来预计好 2。

所以：

\[
V_t^{target}
=
5+2
=
7
\]

现在 Critic 新 forward：

\[
V_\phi(s_t)=5.5
\]

Value Loss：

\[
L_V
=
(5.5-7)^2
\]

反向传播推动：

```text
5.5 → 6 → 6.5 → 7
```

---

<a id="origin-4481"></a>
## 71. 到这里还不是 PPO

到目前为止，我们已经有：

```text
Rollout
↓
Reward
↓
Critic
↓
TD
↓
GAE
↓
Advantage
```

那么普通 Policy Gradient 可以说：

```text
A > 0：
提高 Action 概率

A < 0：
降低 Action 概率
```

问题：

> 一次更新可能太大。

这才引出 PPO。

---

<a id="origin-4517"></a>
## 72. 为什么普通 Policy Gradient 可能不稳定

假设旧 Policy：

```text
向左：0.3
向右：0.4
向前：0.3
```

某次向右表现很好。

一次巨大更新变成：

```text
向左：0.02
向右：0.96
向前：0.02
```

这可能是过度反应。

因为：

> 一次 Rollout 中向右表现好，不代表永远应该几乎只向右。

所以我们希望：

\[
\boxed{
新 Policy 比旧 Policy 好一点
}
\]

但同时：

\[
\boxed{
新 Policy 不要离旧 Policy 太远
}
\]

这就是：

> Proximal。

---

<a id="origin-4565"></a>
## 73. 为什么会有 old policy 和 new policy

一批数据是用：

\[
\pi_{\text{old}}
\]

Rollout 出来的。

然后我们开始梯度更新。

参数一变，当前 Policy 就成为：

\[
\pi_\theta
\]

也就是 new policy。

问题：

> 旧数据是旧 Policy 采的，现在却在训练新 Policy。

于是需要 Importance Sampling。

---

<a id="origin-4593"></a>
## 74. Importance Sampling：重要性采样

我们有一批数据：

\[
(s_t,a_t,r_t)
\]

这些数据其实来自：

\[
\pi_{\theta_{\text{old}}}
\]

也就是说：

> 是旧 Policy 采样出来的。

但是现在我们正在训练：

\[
\pi_\theta
\]

问题出现了：

> 数据是旧策略产生的，却想拿来训练新策略。

怎么办？

引入：

\[
r_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\theta_{\text{old}}}(a_t|s_t)
}
\]

注意：

PPO 论文里一般把这个比例写成：

\[
r_t(\theta)
\]

这里的 \(r\) **不是 reward**。

而是：

> probability ratio，概率比值。

---

<a id="origin-4651"></a>
## 75. Probability Ratio 到底是什么意思？

假设旧策略：

\[
\pi_{\text{old}}(a|s)=0.4
\]

新策略：

\[
\pi_\theta(a|s)=0.48
\]

那么：

\[
r_t
=
\frac{0.48}{0.4}
=
1.2
\]

说明：

> 新策略选择这个动作的概率，是旧策略的 1.2 倍。

如果：

\[
r_t=1
\]

说明新旧策略在这个动作上的概率没变。

如果：

\[
r_t>1
\]

说明动作概率提高了。

如果：

\[
r_t<1
\]

说明动作概率降低了。

---

<a id="origin-4705"></a>
## 76. Importance Sampling 原理

通用问题：

我们想计算：

\[
\mathbb E_{x\sim p}[f(x)]
\]

但手头的数据来自：

\[
q(x)
\]

怎么办？

展开：

\[
\mathbb E_{x\sim p}[f(x)]
=
\sum_x
p(x)f(x)
\]

乘除：

\[
q(x)
\]

得到：

\[
=
\sum_x
q(x)
\frac{p(x)}{q(x)}
f(x)
\]

所以：

\[
\boxed{
\mathbb E_{p}[f]
=
\mathbb E_q
\left[
\frac{p}{q}f
\right]
}
\]

**即：我本来想按照分布 \(p\) 来采样并计算 \(f\) 的平均值，但手里只有按照分布 \(q\) 采出来的数据；那我可以继续用 \(q\) 的数据，只要给每个样本乘一个修正权重 \(\frac{p}{q}\)，最后得到的期望仍然等价于在 \(p\) 下计算。**

---

<a id="origin-4765"></a>
## 77. Importance Sampling 里的 \(f\) 是什么

\(f\) 只是数学占位符。

表示：

> 你真正想对某个分布求平均的那个量。

例如：

\[
f(x)=x^2
\]

或者：

\[
f(x)=3x+1
\]

都可以。

在 PPO 中：

\[
f
\]

主要对应：

\[
A_t
\]

所以才会出现：

\[
\frac{\pi_{\text{new}}}{\pi_{\text{old}}}
A_t
\]

---

<a id="origin-4808"></a>
## 78. PPO 里 Importance Sampling 真正意味着什么

PPO 的一个核心问题是：

> **我们正在更新一个新的 Policy，但是手里的训练数据却是旧 Policy 采集出来的。**

假设当前正在优化的新 Policy 是：

\[
\pi_\theta
\]

如果完全按照新 Policy 来计算目标，我们希望使用类似：

\[
\mathbb E_{\pi_\theta}
\left[
A_t
\right]
\]

这样的期望。

但是现实中，当前这批训练数据并不是：

\[
\pi_\theta
\]

刚刚生成的，而是之前的旧 Policy：

\[
\boxed{
\pi_{\text{old}}
}
\]

生成的。

---

<a id="origin-4849"></a>
### 78.1 “数据来自 \(\pi_{\text{old}}\)”到底是什么意思？

例如在某个状态：

\[
s_t
\]

旧 Policy 给三个动作的概率是：

\[
\pi_{\text{old}}(a_1|s_t)=0.6
\]

\[
\pi_{\text{old}}(a_2|s_t)=0.3
\]

\[
\pi_{\text{old}}(a_3|s_t)=0.1
\]

然后我们真的让：

\[
\pi_{\text{old}}
\]

去和环境交互。

它可能采样出了：

\[
a_t=a_2
\]

于是得到一条实际数据：

```text
状态：s_t
动作：a_2
奖励：r_t
下一状态：s_{t+1}
Advantage：A_t
```

这条数据之所以会出现，是因为当时采样它的 Policy 是：

\[
\pi_{\text{old}}
\]

并且当时：

\[
\pi_{\text{old}}(a_2|s_t)=0.3
\]

所以我们会把旧 Policy 当时对这个动作的概率：

\[
0.3
\]

也一起保存下来。

---

<a id="origin-4917"></a>
### 78.2 但是训练几步以后，Policy 已经变了

假设经过参数更新以后，新 Policy 变成：

\[
\pi_\theta
\]

对于刚才完全相同的：

\[
(s_t,a_2)
\]

新 Policy 现在给出的概率可能变成：

\[
\pi_\theta(a_2|s_t)=0.45
\]

于是：

```text
这条数据：
(s_t, a_2, A_t)

是 old Policy 采出来的：

π_old(a_2|s_t)=0.30

但是现在正在训练的是 new Policy：

π_θ(a_2|s_t)=0.45
```

这就出现了一个问题：

> **训练数据的来源分布和我们现在正在优化的 Policy 已经不一样了。**

---

<a id="origin-4958"></a>
### 78.3 Importance Sampling 怎么解决？

Importance Sampling 的基本公式是：

\[
\mathbb E_p[f]
=
\mathbb E_q
\left[
\frac{p}{q}f
\right]
\]

在 PPO 中，对动作概率来说，可以对应理解为：

\[
p
=
\pi_\theta(a_t|s_t)
\]

\[
q
=
\pi_{\text{old}}(a_t|s_t)
\]

因此定义概率比：

\[
\boxed{
r_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
}
\]

> 注意：这里的 \(r_t(\theta)\) 是 **Policy Probability Ratio**，不是环境给出的 Reward \(r_t\)。

于是 PPO 的 surrogate objective 中会出现：

\[
\boxed{
\mathbb E_{\pi_{\text{old}}}
\left[
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
A_t
\right]
}
\]

直观上就是：

> **虽然这批动作是 old Policy 采出来的，但根据“这个动作在 new Policy 下应该有多大概率”重新调整它的权重。**

---

<a id="origin-5023"></a>
### 78.4 所以 PPO 可以做到什么？

**PPO 不需要每更新一次参数，就立刻重新让新 Policy rollout 一遍。**

而是可以：

```text
继续使用 old Policy 收集的数据
↓
通过 π_new / π_old
修正这些旧数据的权重
↓
近似站在 new Policy 的角度优化
```

这就是：

\[
\boxed{
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
}
\]

在 PPO 里出现的根本来源。

---

<a id="origin-5054"></a>
### 78.5 一句话理解

\[
\boxed{
\mathbb E_p[f]
=
\mathbb E_q
\left[
\frac{p}{q}f
\right]
}
\]

在 PPO 中可以理解成：

> **虽然数据是旧 Policy \(\pi_{\text{old}}\) 采出来的，但通过乘上 \(\pi_\theta/\pi_{\text{old}}\) 这个概率比，可以把旧数据重新加权，使它更接近新 Policy \(\pi_\theta\) 下应该产生的效果。**

所以：

\[
\boxed{
\frac{\pi_\theta(a_t|s_t)}
{\pi_{\text{old}}(a_t|s_t)}
}
\]

本质上就是：

> **“旧数据在新 Policy 视角下应该算多重要”的修正系数。**


---

<a id="origin-5087"></a>
## 79. PPO 中的 Ratio

定义：

\[
\boxed{
\rho_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
}
\]

---

<a id="origin-5105"></a>
## 80. Ratio 并没有替代 Policy

必须强调：

\[
\boxed{
\rho_t
不是一个神经网络
}
\]

\[
\boxed{
\rho_t
没有替代
\pi_\theta
}
\]

它只是：

> 用新旧 Policy 对同一个 Action 的概率相除得到的数。

---

<a id="origin-5130"></a>
## 81. Advantage 也不是训练出来的一个模型

PPO update 时：

\[
A_t
\]

已经通过：

```text
Reward
+
Value
+
TD
+
GAE
```

算出来。

所以：

> PPO 不训练一个叫 A 的网络。

真正训练的是：

```text
Actor
Critic
```

---

<a id="origin-5165"></a>
## 82. Ratio 的直觉

例如：

旧 Policy：

\[
\pi_{\text{old}}(a|s)=0.4
\]

新 Policy：

\[
\pi_{\text{new}}(a|s)=0.48
\]

那么：

\[
\rho=1.2
\]

意思：

> 新 Policy 选这个 Action 的概率，是旧 Policy 的 1.2 倍。

---

如果：

\[
\rho=1
\]

说明：

> 没变。

如果：

\[
\rho>1
\]

说明：

> 概率提高。

如果：

\[
\rho<1
\]

说明：

> 概率降低。

---

<a id="origin-5225"></a>
## 83. PPO 最基础的 surrogate objective

\[
\boxed{
L(\theta)
=
\mathbb E[
\rho_tA_t
]
}
\]

---

<a id="origin-5239"></a>
### 83.1 如果 \(A_t>0\)

是好动作。

希望：

\[
\rho_t>1
\]

也就是：

> 提高这个动作概率。

---

<a id="origin-5255"></a>
### 83.2 如果 \(A_t<0\)

是坏动作。

希望：

\[
\rho_t<1
\]

也就是：

> 降低这个动作概率。

---

<a id="origin-5271"></a>
## 84. 问题又来了：Ratio 还是可能改得太猛

假设：

\[
A=2
\]

旧概率：

\[
0.4
\]

新概率：

\[
0.8
\]

那么：

\[
\rho=2
\]

这意味着：

> 概率一下翻倍。

PPO 认为：

> 方向可能是对的，但步子太大。

于是引入 Clip。

---

<a id="origin-5309"></a>
## 85. PPO-Clip 核心公式

\[
\boxed{
L^{CLIP}(\theta)
=
\mathbb E_t
\left[
\min
\left(
\rho_tA_t,
\operatorname{clip}
(\rho_t,1-\epsilon,1+\epsilon)
A_t
\right)
\right]
}
\]

**通常\(A_t\)就是\(\hat A_t^{GAE}\)。**

例如：

\[
\epsilon=0.2
\]

允许范围：

\[
[0.8,1.2]
\]

---

<a id="origin-5344"></a>
## 86. Clip 是什么意思

\[
clip(\rho,0.8,1.2)
\]

表示：

```text
ρ < 0.8
→ 用 0.8

0.8 ≤ ρ ≤ 1.2
→ 保持原值

ρ > 1.2
→ 用 1.2
```

---

<a id="origin-5365"></a>
## 87. 好动作例子

假设：

\[
A=2
\]

旧概率：

\[
0.4
\]

新概率：

\[
0.6
\]

那么：

\[
\rho=1.5
\]

未 Clip：

\[
1.5\times2=3
\]

Clip：

\[
1.2\times2=2.4
\]

PPO 取：

\[
\min(3,2.4)=2.4
\]

所以：

> 超过 1.2 之后，继续提高概率不会再带来更多 Objective 收益。

---

<a id="origin-5415"></a>
## 88. 为什么还要一个 min

因为 PPO 想要：

> 取“更保守”的那个结果。

对于好动作：

```text
如果新 Policy 提升太多
→ 用 Clip 后较小的值
```

对于坏动作：

```text
如果新 Policy 降低太多
→ 也要截住
```

---

<a id="origin-5437"></a>
## 89. 坏动作为什么更容易把人绕晕

假设：

\[
A=-2
\]

旧概率：

\[
0.4
\]

新概率：

\[
0.28
\]

那么：

\[
\rho
=
0.7
\]

未 Clip：

\[
\rho A
=
0.7\times(-2)
=
-1.4
\]

Clip：

\[
0.8\times(-2)
=
-1.6
\]

最终：

\[
\min(-1.4,-1.6)
=
-1.6
\]

很多人会问：

> \(-1.6\) 比 \(-1.4\) 更负，为什么反而说它不让模型继续激进降低概率？

关键：

> PPO Objective 是最大化，不是最小化。

---

<a id="origin-5501"></a>
## 90. 为什么 \(-1.6\) 能限制继续下降

如果没有 Clip：

```text
ρ=0.9
→ -1.8

ρ=0.8
→ -1.6

ρ=0.7
→ -1.4

ρ=0.6
→ -1.2
```

因为我们要最大化：

\[
-1.2>-1.4>-1.6>-1.8
\]

所以优化器会继续觉得：

> Ratio 越低越好。

---

但加入 Clip：

```text
ρ=0.8
→ -1.6

ρ=0.7
→ min(-1.4,-1.6)
→ -1.6

ρ=0.6
→ min(-1.2,-1.6)
→ -1.6
```

于是：

\[
\boxed{
\rho<0.8 后，
Objective 不再继续变好
}
\]

所以继续降低概率：

> 没有额外收益。

这才是 Clip 真正的意思。

---

<a id="origin-5563"></a>
## 91. PPO 并不是硬性限制概率只能变 ±20%

例如：

\[
\epsilon=0.2
\]

并不是说：

> 新概率绝对不可能超过旧概率 20%。

PPO 做的是：

> 当 Ratio 超出区间后，Objective 不再奖励继续朝这个方向走。

所以是一种：

> soft constraint。

---

<a id="origin-5585"></a>
## 92. 为什么实际代码保存 log probability

代码通常保存：

```text
old_log_prob
new_log_prob
```

而不是直接保存概率。

因为：

\[
\log\rho_t
=
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
\]

所以：

\[
\boxed{
\rho_t
=
\exp(
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
)
}
\]

代码：

```python
ratio = torch.exp(
    new_log_prob - old_log_prob
)
```

---

<a id="origin-5630"></a>
## 93. PPO 完整 Policy Loss

数学上：

\[
\boxed{
L^{CLIP}
=
\mathbb E[
\min(
\rho_tA_t,
clip(\rho_t,1-\epsilon,1+\epsilon)A_t
)
]
}
\]

我们希望最大化它。

PyTorch Optimizer 默认最小化 Loss。

所以：

\[
\boxed{
L_{\text{policy}}
=
-
L^{CLIP}
}
\]

---

<a id="origin-5664"></a>
## 94. Policy Gradient 与 PPO 中 \(\pi\)、Advantage、Ratio 的关系

很多人在第一次看到 PPO 时都会有一个疑问：

前面 Policy Gradient 明明写的是：

\[
\boxed{
\nabla_\theta J
=
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
A_t
\right]
}
\]

这里明显出现了：

\[
\pi_\theta(a_t|s_t)
\]

但是到了 PPO 后面，却突然变成了：

\[
\rho_t A_t
\]

好像 \(\pi\) 不见了。

实际上：

> **\(\pi\) 并没有消失，而是被包含在 PPO 的概率比 \(\rho_t\) 里面了。**

<a id="origin-5701"></a>
### 94.1 PPO 的基础目标函数

先不考虑 Clip，最简单的 PPO surrogate objective 是：

\[
\boxed{
L(\theta)
=
\mathbb E_t
\left[
\rho_t(\theta)
A_t
\right]
}
\]

也就是：

\[
\boxed{
L(\theta)
=
\mathbb E_t
\left[
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
A_t
\right]
}
\]

所以这里的 \(\pi_\theta\) 根本没有消失。

只是从：

\[
\log\pi_\theta
\]

变成了：

\[
\frac{
\pi_\theta
}{
\pi_{\text{old}}
}
\]

---

<a id="origin-5755"></a>
### 94.2 为什么 \(\rho_t A_t\) 最后又会变回 \(\nabla\log\pi\) （课外）

这是最关键的一步。

我们从：

\[
\rho_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

开始。

对 \(\theta\) 求导：

\[
\nabla_\theta\rho_t
=
\nabla_\theta
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

因为：

\[
\pi_{\text{old}}
\]

在这一轮 PPO 更新中是固定的。

因此：

\[
\nabla_\theta
\pi_{\text{old}}
=
0
\]

所以：

\[
\nabla_\theta\rho_t
=
\frac{
\nabla_\theta
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

前面已经知道：

\[
\nabla_\theta\pi_\theta
=
\pi_\theta
\nabla_\theta\log\pi_\theta
\]

代入：

\[
\nabla_\theta\rho_t
=
\frac{
\pi_\theta(a_t|s_t)
\nabla_\theta
\log\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

前面的部分正好就是：

\[
\frac{
\pi_\theta
}{
\pi_{\text{old}}
}
=
\rho_t
\]

所以：

\[
\boxed{
\nabla_\theta\rho_t
=
\rho_t
\nabla_\theta
\log\pi_\theta(a_t|s_t)
}
\]

再对 \(\rho_tA_t\) 求导，PPO 基础目标：

\[
L(\theta)
=
\rho_tA_t
\]

在一次 Policy 更新过程中，**可以把已经算好的 \(A_t\) 看成常数。**

所以：

\[
\nabla_\theta L
=
A_t
\nabla_\theta\rho_t
\]

代入前面的结果：

\[
\nabla_\theta L
=
A_t
\rho_t
\nabla_\theta
\log\pi_\theta(a_t|s_t)
\]

因此：

\[
\boxed{
\nabla_\theta L
=
\rho_t
\nabla_\theta
\log\pi_\theta(a_t|s_t)
A_t
}
\]

---

<a id="origin-5908"></a>
### 94.3 和最开始的 Policy Gradient 对比

普通 Policy Gradient：

\[
\boxed{
\nabla_\theta J
=
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
A_t
\right]
}
\]

PPO：

\[
\boxed{
\nabla_\theta L
=
\mathbb E
\left[
\rho_t
\nabla_\theta
\log\pi_\theta(a_t|s_t)
A_t
\right]
}
\]

你会发现：

PPO 的核心仍然是：

\[
\boxed{
\nabla_\theta
\log\pi_\theta
\times
A_t
}
\]

只不过 PPO 在前面增加了一个：

\[
\boxed{
\rho_t
=
\frac{
\pi_\theta
}{
\pi_{\text{old}}
}
}
\]

用来处理：

> **当前 Policy 和产生这批 Rollout 数据的旧 Policy 已经不一样了。**

---

<a id="origin-5974"></a>
### 94.4 一个非常重要的特殊情况

刚刚开始 PPO 更新时：

\[
\theta=\theta_{\text{old}}
\]

因此：

\[
\pi_\theta
=
\pi_{\text{old}}
\]

于是：

\[
\rho_t
=
\frac{
\pi_\theta
}{
\pi_{\text{old}}
}
=
1
\]

这个时候：

\[
\nabla_\theta L
=
1
\times
\nabla_\theta
\log\pi_\theta
A_t
\]

所以：

\[
\boxed{
\nabla_\theta L
=
\nabla_\theta
\log\pi_\theta
A_t
}
\]

也就是重新回到了最原始的 Policy Gradient。

因此可以把 PPO 理解成：

> **Policy Gradient + 对新旧 Policy 差异的控制。**

---

<a id="origin-6036"></a>
### 94.5 PPO 完整 Policy Objective

因此最终：

\[
\boxed{
L^{PPO}(\theta)
=
\mathbb E_t
\left[
\min
\left(
\rho_t(\theta)A_t,
\operatorname{clip}
(
\rho_t(\theta),
1-\epsilon,
1+\epsilon
)
A_t
\right)
\right]
}
\]

其中：

\[
\boxed{
\rho_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
}
\]

展开以后其实就是：

\[
\boxed{
L^{PPO}(\theta)
=
\mathbb E_t
\left[
\min
\left(
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
A_t,
\operatorname{clip}
\left(
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
},
1-\epsilon,
1+\epsilon
\right)
A_t
\right)
\right]
}
\]

**所以 PPO 的公式里实际上从头到尾都有：**

\[
\pi_\theta
\]


---

<a id="origin-6116"></a>
## 95. Critic 的 Loss

Value Target：

\[
V_t^{target}
=
A_t+V_{\text{old}}(s_t)
\]

Critic 新预测：

\[
V_\phi(s_t)
\]

Value Loss：

\[
\boxed{
L_V
=
\frac12
(
V_\phi(s_t)
-
V_t^{target}
)^2
}
\]

---

<a id="origin-6149"></a>
## 96. 为什么还要 Entropy？

假设 Actor 学了一段时间后输出：

```text
左：0.001
右：0.998
前：0.001
```

这意味着几乎永远选择右。

问题是：

> 可能右只是目前看起来最好，不代表它真的是全局最优。

因此需要鼓励 Exploration，探索。

使用：

\[
H(\pi)
=
-
\sum_a
\pi(a|s)
\log\pi(a|s)
\]

这就是 Entropy，熵。

如果：

```text
0.33
0.33
0.34
```

Entropy 很高，说明策略比较随机，探索较多。

如果：

```text
0.999
0.0005
0.0005
```

Entropy 很低，说明策略几乎完全确定，探索很少。

所以 PPO 通常加入：

\[
+c_2H(\pi)
\]

**鼓励一定程度的探索。**

---

<a id="origin-6210"></a>
## 97. PPO 总 Loss

最终 PPO 常见目标：

\[
L(\theta)
=
L^{CLIP}
-
c_1L^{VF}
+
c_2H
\]

这里这个形式是 maximize，即**我们希望\(L(\theta)\)越大越好。**

其中：

<a id="origin-6228"></a>
### 97.1 Policy Loss

\[
L^{CLIP}
=
\mathbb E
[
\min(
r_tA_t,
clip(r_t,1-\epsilon,1+\epsilon)A_t
)
]
\]

负责：

> 学会选择更好的动作。

<a id="origin-6246"></a>
### 97.2 Value Loss

\[
L^{VF}
=
\frac12
(V(s_t)-V_t^{target})^2
\]

负责训练 Critic。

<a id="origin-6257"></a>
### 97.3 Entropy

\[
H(\pi)
=
-
\sum_a\pi(a|s)\log\pi(a|s)
\]

负责保持探索。

---

<a id="origin-6270"></a>
## 98. Rollout 到底是什么

现在正式回答这个问题。

Rollout：

\[
\boxed{
让当前 Policy 真正运行起来，产生真实训练轨迹
}
\]

机器人：

```text
真的选 Action
真的进入下一个 State
真的得到 Reward
```

大模型：

```text
真的输入 Prompt
真的 autoregressive 采样 Token
真的生成 Response
```

---

<a id="origin-6300"></a>
## 99. 大模型里一次 Rollout 到底存什么

例如 Prompt：

```text
1+1=
```

模型生成：

```text
2
```

Rollout 会保存：

```text
state:
"1+1="

action:
"2"

old_log_prob:
log P_old("2"|"1+1=")

value:
V_old("1+1=")
```

下一步继续：

```text
state:
"1+1=2"

action:
"。"

old_log_prob:
...

value:
...
```

直到 EOS。

---

<a id="origin-6350"></a>
## 100. 每执行一次 Action，后面序列都会变，那旧 Rollout 还有什么用

这个问题非常重要。

答案：

> Rollout 阶段和 PPO Update 阶段是两个完全不同的阶段。

---

<a id="origin-6360"></a>
## 101. Rollout 阶段：真的重新生成

假设：

\[
\pi_{\text{old}}
\]

生成：

```text
A → B → C → D
```

这时候：

> 每一步 Action 都真的改变后面的 State。

---

<a id="origin-6380"></a>
## 102. PPO Update 阶段：不重新生成

这条 trajectory 保存后：

```text
s0,A
s1,B
s2,C
s3,D
```

即使参数更新以后，新 Policy 如果重新生成可能变成：

```text
X → Y → Z
```

这一轮训练也不会重新生成。

而是固定旧 State / Action：

```text
π_new(A|s0)
π_new(B|s1)
π_new(C|s2)
π_new(D|s3)
```

---

<a id="origin-6410"></a>
## 103. 这有点像 Teacher Forcing

SFT：

```text
Q + 标准答案
```

即使当前模型自己会生成错答案，训练时仍然把标准前缀喂进去：

```text
P(y_t|Q,y_<t)
```

PPO Update 也类似：

> 旧 trajectory 已经固定，新模型只负责重新评价这条旧 trajectory 上的 Action 概率。

---

<a id="origin-6430"></a>
## 104. 那旧 trajectory 不会越来越过时吗

会。

所以 PPO 只重复训练有限 Epoch。

例如：

```text
Rollout
↓
Epoch 1
↓
Epoch 2
↓
Epoch 3
↓
Epoch 4
↓
丢掉这批旧数据
↓
用最新 Policy 重新 Rollout
```

PPO 的 Ratio + Clip：

> 就是为了让这一小段“旧数据重复利用”尽量合理。

---

<a id="origin-6460"></a>
## 105. 现在进入大模型 RLHF

前面全部是通用 PPO。

现在才把它映射到大模型。

---

<a id="origin-6468"></a>
## 106. 大模型里 State 是什么

大模型当前状态：

\[
s_t
\]

就是：

> Prompt + 当前已经生成的 Token。

例如：

```text
Prompt:
浙江大学位于

当前已生成:
浙江
```

那么 State 就是：

```text
浙江大学位于浙江
```

---

<a id="origin-6498"></a>
## 107. 大模型里 Action 是什么

\[
a_t
\]

就是：

> 下一个 Token。

例如：

```text
"宁"
```

或：

```text
"杭"
```

---

<a id="origin-6522"></a>
## 108. 大模型里 Policy 是谁

大模型本身：

\[
\boxed{
\pi_\theta(a_t|s_t)
}
\]

就是 Actor / Policy。

它输入：

```text
当前上下文
```

输出：

```text
整个词表上的 Token 概率分布
```

---

<a id="origin-6548"></a>
## 109. Reward 从哪里来

经典 RLHF 中：

> Reward Model 给完整 Response 一个偏好分数。

例如：

```text
Prompt + Response
↓
Reward Model
↓
8.7
```

---

<a id="origin-6566"></a>
## 110. Reward Model 是简单 SFT 吗

不是。

普通 SFT：

```text
Prompt
→ 标准 Response
→ token prediction loss
```

Reward Model：

```text
同一个 Prompt

Chosen Response
Rejected Response

只告诉：
Chosen > Rejected
```

所以它是：

> Pairwise Preference Learning。

---

<a id="origin-6596"></a>
## 111. Reward Model 的数据例子

```json
{
  "chosen": [
    {"content": "Q", "role": "user"},
    {"content": "good answer", "role": "assistant"}
  ],
  "rejected": [
    {"content": "Q", "role": "user"},
    {"content": "bad answer", "role": "assistant"}
  ]
}
```

这个数据并没有告诉 Reward Model：

```text
good answer 每个 token 都是监督标签
```

而只告诉：

```text
good answer 比 bad answer 更好
```

---

<a id="origin-6625"></a>
## 112. Reward Model 网络结构

最简单理解：

```text
Transformer
↓
最后一个有效位置 hidden state
↓
Scalar Head
↓
一个数字
```

例如：

\[
h\in\mathbb R^{4096}
\]

Reward Head：

\[
r=w^Th+b
\]

输出：

```text
chosen: 2.3
rejected: 0.8
```

---

<a id="origin-6660"></a>
## 113. Reward Model Loss

Chosen：

\[
r_c
=
R_\psi(x,y_c)
\]

Rejected：

\[
r_r
=
R_\psi(x,y_r)
\]

希望：

\[
r_c>r_r
\]

常用：

\[
\boxed{
P(y_c\succ y_r)
=
\sigma(r_c-r_r)
}
\]

Loss：

\[
\boxed{
L_{\text{RM}}
=
-\log
\sigma(r_c-r_r)
}
\]

---

<a id="origin-6707"></a>
## 114. Reward Model 一个数值例子

一开始：

\[
r_c=0.4
\]

\[
r_r=0.6
\]

判断反了。

因为：

\[
r_c-r_r=-0.2
\]

所以：

\[
\sigma(-0.2)
\]

比较小。

Loss 大。

反向传播后可能：

```text
chosen:
0.4 → 0.8 → 1.5 → 2.4

rejected:
0.6 → 0.3 → -0.2 → -0.7
```

模型学会：

> chosen 应该得分更高。

---

<a id="origin-6753"></a>
## 115. Reward Model 学的是相对偏好

假设：

\[
r_c=5,\quad r_r=2
\]

和：

\[
r_c=105,\quad r_r=102
\]

只看差：

\[
3
\]

pairwise preference 信息非常相似。

所以 Reward Model：

> 首先学习的是排序关系。

而不是天然具有某个绝对“满分 10 分”的意义。

---

<a id="origin-6783"></a>
## 116. 大模型里的 Critic 是谁

Critic：

\[
V_\phi(s_t)
\]

输入：

```text
Prompt + 已生成部分
```

输出：

> 从当前生成状态继续下去，预计最终能得到多少 Reward。

---

<a id="origin-6803"></a>
## 117. 大模型 Critic 的结构

一种常见方式：

```text
Transformer
   │
hidden state h_t
   ├─────────────→ LM Head → token logits
   │
   └─────────────→ Value Head → scalar
```

Value Head：

\[
V(s_t)
=
w_V^Th_t+b
\]

---

<a id="origin-6826"></a>
## 118. Critic 是怎么训练出来的

不是人工给标签：

```text
这个上下文 V=6.37
```

而是：

```text
Policy Rollout
↓
Reward
↓
TD
↓
GAE
↓
Value Target
↓
训练 Critic
```

---

<a id="origin-6852"></a>
## 119. 大模型 Critic 训练例子

某个 State：

```text
Prompt + "1+1="
```

旧 Critic：

\[
V_{\text{old}}=5
\]

GAE：

\[
A=2
\]

那么：

\[
V^{target}=7
\]

Critic 新预测：

\[
5.5
\]

Loss：

\[
(5.5-7)^2
\]

训练使：

```text
5.5 → 6 → 6.5 → 7
```

---

<a id="origin-6898"></a>
## 120. Reward Model 和 Critic 的区别

可以直接记：

<a id="origin-6902"></a>
### 120.1 Reward Model

```text
Prompt + 完整 Response
↓
这个完整回答整体好不好
```

像：

> 阅卷老师。

---

<a id="origin-6916"></a>
### 120.2 Critic

```text
Prompt + 当前已经生成到这里
↓
照目前这个局面，最后大概能得多少分
```

像：

> 写到一半时预测最终成绩。

---

<a id="origin-6930"></a>
## 121. Reference Model 是什么

RLHF PPO 里通常还有：

\[
\pi_{\text{ref}}
\]

它通常是：

> 冻结的 SFT 模型。

作用：

> 防止 PPO 把模型改得离原始语言模型太远。

---

<a id="origin-6948"></a>
## 122. Old Policy 和 Reference Model 不是一回事

<a id="origin-6950"></a>
### 122.1 Old Policy

\[
\pi_{\text{old}}
\]

表示：

> 当前这一批 Rollout 时的 Policy 快照。

用于：

\[
\frac{\pi_{\text{new}}}{\pi_{\text{old}}}
\]

---

<a id="origin-6968"></a>
### 122.2 Reference Model

\[
\pi_{\text{ref}}
\]

表示：

> 长期冻结的参考模型。

用于：

> KL 约束。

---

<a id="origin-6984"></a>
## 123. KL Penalty 是什么

为了防止 Policy 远离 Reference Model：

\[
r_t^{KL}
=
-\beta
\left(
\log\pi_\theta(a_t|s_t)
-
\log\pi_{\text{ref}}(a_t|s_t)
\right)
\]

直觉：

```text
新模型和原模型差得越大
→ 惩罚越大
```

---
<a id="origin-7007"></a>
## 124. 大模型 PPO 中 KL Penalty 的作用及两种实现方式

在大模型 PPO 训练中，我们希望：

1. Policy Model 生成的回答获得更高的 Reward。
2. Policy Model 不要过度偏离原来的 Reference Model。

因此，引入 KL Penalty。

对于第 t 个 Token：

\[
r_t^{KL}
=
-\beta
\left(
\log \pi_{\mathrm{old}}(a_t|s_t)
-
\log \pi_{\mathrm{ref}}(a_t|s_t)
\right)
\]

其中：

- \(\pi_{\mathrm{old}}\)：生成这批 Rollout 数据时使用的 Policy。
- \(\pi_{\mathrm{ref}}\)：冻结的 Reference Model。
- \(a_t\)：实际生成的 Token。
- \(s_t\)：当前状态，即 Prompt 加上之前已经生成的 Token。
- \(\beta\)：KL 惩罚系数。

注意：

这里的 \(r_t^{KL}\) 是一个带符号的 Reward 修正项。

实际计算中：

\[
\log \pi_{\mathrm{old}}(a_t|s_t)
-
\log \pi_{\mathrm{ref}}(a_t|s_t)
\]

可以为正，也可以为负。

因此，单个 Token 的 KL 修正项不一定是负数。

只有在对 Old Policy 的动作分布取期望时，才得到非负的 KL 散度：

\[
\mathbb E_{a_t\sim\pi_{\mathrm{old}}}
\left[
\log
\frac{\pi_{\mathrm{old}}(a_t|s_t)}
{\pi_{\mathrm{ref}}(a_t|s_t)}
\right]
=
D_{\mathrm{KL}}
(
\pi_{\mathrm{old}}
\|
\pi_{\mathrm{ref}}
)
\geq 0
\]

因此，我们可以通过 KL 项，在整体上惩罚 Policy 对 Reference Model 的偏离。

---

<a id="origin-7076"></a>
## 125. KL Penalty 是 Reward Model 算出来的吗？

不是。

这是一个非常容易混淆的地方。

<a id="origin-7082"></a>
### 125.1 Reward Model 的职责

Reward Model 接收：

\[
(x,y)
\]

其中：

- \(x\)：Prompt。
- \(y\)：Policy 生成的回答。

然后输出：

\[
R_{\mathrm{RM}}(x,y)
\]

例如：

```text
Prompt：
请解释什么是机器学习。

Policy 生成：
机器学习就是让计算机从数据中学习规律。

Reward Model：
给出 8 分。
```

Reward Model 只负责评价回答的质量。

它并不需要知道 Reference Model 给这个回答分配了多少概率。

<a id="origin-7118"></a>
#### 125.1.1 KL Penalty 的职责

KL Penalty 则需要：

```text
Policy Model 的 Token 概率

Reference Model 的 Token 概率
```

然后比较它们之间的差异。

因此：

**Reward Model 不负责计算 KL Penalty，KL Penalty 是 PPO 训练算法额外计算的。**

---

<a id="origin-7136"></a>
## 126. KL Penalty 有两种常见的加入方法

<a id="origin-7138"></a>
### 126.1 方法一：加入 Reward（Reward Shaping）

首先，Reward Model 给出：

\[
R_{\mathrm{RM}}=10
\]

假设整条回答计算出的 KL 总惩罚为：

\[
P_{\mathrm{KL}}=2
\]

那么，综合奖励为：

\[
R=10-2=8
\]

但是在实际的大模型 PPO 中，通常不只是简单地在最后减去一个数。

因为 KL 可以针对每个 Token 计算。

例如，回答包含三个 Token：

```text
Token 1：机器
Token 2：学习
Token 3：很好
```

假设对应的 KL Reward 为：

\[
r_1^{KL}=-0.3
\]

\[
r_2^{KL}=-0.5
\]

\[
r_3^{KL}=-1.2
\]

Reward Model 对整条回答打分：

\[
R_{\mathrm{RM}}=10
\]

我们可以把 Reward Model 的分数加到最后一个 Token 上。

于是：

\[
r_1=-0.3
\]

\[
r_2=-0.5
\]

\[
r_3=10-1.2=8.8
\]

这样就得到了每个 Token 的 Reward。

接下来：

```text
Reward Model Score
        +
每个 Token 的 KL Reward
        ↓
构造每个 Token 的 Reward
        ↓
计算 GAE
        ↓
计算 Advantage
        ↓
计算 PPO Actor Loss
        ↓
更新 Policy Model
```

这里最关键的是：

**KL Penalty 首先改变 Reward，然后通过 GAE 改变 Advantage，最后影响 PPO 的梯度更新。**

例如：

原来某个 Token 的 Advantage 为：

\[
A_t=3
\]

加入 KL Reward 后，重新计算 GAE，可能变成：

\[
A_t=1
\]

那么这个 Token 仍然是一个值得鼓励的动作，只是鼓励的程度变小了。

这里的 3 和 1 只是示意数值，实际变化取决于整段 Reward、Value 估计以及 GAE 参数。

---

<a id="origin-7250"></a>
### 126.2 方法二：直接加入 PPO Loss

另一种方法是不修改 Reward，而是在最终 Loss 中加入 KL 正则项。

假设：

\[
L_{\mathrm{PPO}}=-2
\]

Reference KL 正则项为：

\[
\beta D_{\mathrm{KL}}=0.5
\]

那么：

\[
L_{\mathrm{total}}=-2+0.5=-1.5
\]

注意，这里的 Loss 是需要最小化的目标。

其一般形式为：

\[
\boxed{
L_{\mathrm{total}}
=
L_{\mathrm{PPO}}
+
\beta D_{\mathrm{KL}}
\left(
\pi_\theta
\|
\pi_{\mathrm{ref}}
\right)
}
\]

这里的 \(\pi_\theta\) 表示当前正在优化的 Policy。

整个流程：

```text
Reward Model Score
        ↓
计算 GAE
        ↓
计算 Advantage
        ↓
计算 PPO Actor Loss
        │
        │
当前 Policy 和 Reference Model
        ↓
计算可微分的 Reference KL Loss
        │
        ↓
PPO Actor Loss + KL Loss
        ↓
反向传播
        ↓
更新 Policy Model
```

这时：

- PPO Actor Loss：鼓励高 Advantage 的动作。
- Reference KL Loss：惩罚 Policy 偏离 Reference Model。

**KL Loss 直接参与梯度更新，而不需要经过 GAE。**

需要注意，这里加入的是一个关于当前 Policy 参数 \(\theta\) 的可微分 KL 项。

如果只是把 Rollout 阶段已经算好的 KL 数值当作常数加到 Loss 上，它的梯度为零，并不能直接提供 KL 正则化的梯度。

---

<a id="origin-7330"></a>
## 127. 两种方法有什么区别？

| 对比 | 加到 Reward | 直接加到 Loss |
|---|---|---|
| KL 在哪里加入 | Reward 计算阶段 | Loss 计算阶段 |
| 是否影响 GAE | 是 | 不通过 KL 项影响 GAE |
| 是否影响 Advantage | 是 | KL 项不直接改变 Advantage |
| 是否直接参与梯度计算 | 不直接反传 KL 项 | 是 |
| 如何影响 Policy | 通过 Advantage | 通过 KL 正则项的梯度 |
| 主要目的 | 限制偏离 Reference | 限制偏离 Reference |

两种方法的优化思想非常接近，但不意味着每一次参数更新都完全一样。

因为 Reward Shaping 会影响 GAE 和 Advantage，而直接加入 Loss 使用的是额外的 KL 梯度。

另外，实际的 PPO Clip、有限样本估计、Value Function 误差等，也会造成差异。

---

<a id="origin-7349"></a>
## 128. 为什么大模型 PPO 经常把 KL 放在 Reward 里面？

主要原因是：

**PPO 本来就需要根据 Reward 计算 GAE 和 Advantage。**

因此，把 KL 惩罚加入 Reward 后，可以自然地复用现有 PPO 流程。

例如：

\[
r_t
=
r_t^{\mathrm{RM}}
-
\beta
\left(
\log\pi_{\mathrm{old}}(a_t|s_t)
-
\log\pi_{\mathrm{ref}}(a_t|s_t)
\right)
\]

其中 \(r_t^{\mathrm{RM}}\) 可以只在最后一个 Token 位置非零。

然后计算：

\[
\delta_t
=
r_t+\gamma V(s_{t+1})-V(s_t)
\]

再通过 GAE：

\[
\boxed{
A_t^{GAE}
=
\sum_{l=0}^{T-t-1}
(\gamma\lambda)^l
\delta_{t+l}
}
\]

最后使用 PPO Clip：

\[
L^{CLIP}(\theta)
=
\mathbb E_t
\left[
\min
\left(
\rho_t(\theta)A_t,
\operatorname{clip}
(
\rho_t(\theta),1-\epsilon,1+\epsilon
)
A_t
\right)
\right]
\]

其中：

\[
\rho_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\mathrm{old}}(a_t|s_t)
}
\]

注意这里有三个不同的 Policy 概念：

- \(\pi_\theta\)：当前正在训练的 Policy。
- \(\pi_{\mathrm{old}}\)：生成本批 Rollout 时使用的 Policy。
- \(\pi_{\mathrm{ref}}\)：冻结的 Reference Model。

Reference Model 不需要参与 PPO Clip 的概率比值计算。

它主要是提供参考分布，用于控制 Policy 偏离程度。

---

<a id="origin-7437"></a>
## 129. PPO 最终是否就是构造一个 Loss 再做梯度下降（重点）

从**真正写代码训练大模型**的角度，可以把 PPO 非常直接地理解成：

\[
\boxed{
\text{前面一大堆强化学习过程}
\rightarrow
\text{最终构造出一个 Loss}
\rightarrow
\text{backward()}
\rightarrow
\text{optimizer.step()}
}
\]

也就是说：

> **PPO 前面虽然有 Reward、Critic、Advantage、Policy Ratio、Clip 等很多步骤，但这些步骤最终都是为了构造出一个可以反向传播的 Loss。**

一旦这个 Loss 构造出来以后，后面的训练方式和普通 SFT 并没有本质区别。

---

<a id="origin-7461"></a>
### 129.1 现在和最熟悉的 SFT 对比

这一步最能解释：

> 为什么强化学习看起来很复杂，最后仍然只是一个 Loss。

我们仍然使用：

```text
浙江大学位于 → 宁波
```

---

<a id="origin-7475"></a>
### 129.2 SFT 的完整更新流程

训练样本：

```text
Prompt：
浙江大学位于

标准答案：
宁波
```

当前 Actor：

\[
\pi_\theta(\text{宁波}|s)=0.5
\]

SFT Loss：

\[
L_{\text{SFT}}
=
-\log\pi_\theta(\text{宁波}|s)
\]

所以：

\[
L_{\text{SFT}}
=
-\log0.5
\approx0.693
\]

计算图：

```text
标准答案“宁波”
        ↓
Cross Entropy Loss
        ↑
log πθ(宁波|s)
        ↑
logits
        ↑
Transformer
        ↑
θ
```

然后：

```python
loss.backward()
optimizer.step()
```

最终：

```text
θ 改变
↓
“宁波”的 probability 提高
```

---

<a id="origin-7543"></a>
### 129.3 SFT 中“正确答案”本身有梯度吗？

没有。

```text
正确答案 = 宁波
```

只是一个固定标签。

它的作用是告诉 Loss：

> 应该把哪个 token 的 probability 提高。

真正有梯度的是：

\[
\log\pi_\theta
\]

因为它来自：

\[
\theta
\]

所以：

\[
\boxed{
\text{SFT 标签不求导}
}
\]

---

<a id="origin-7579"></a>
### 129.4 PPO 的完整更新流程

PPO 没有人直接告诉：

```text
正确答案必须是“宁波”
```

所以先让 Actor 自己生成。

```text
Prompt：
浙江大学位于
↓
Actor Rollout
↓
Action：
宁波
```

理论里的：

\[
s_t
=
\text{浙江大学位于}
\]

\[
a_t
=
\text{宁波}
\]

---

<a id="origin-7615"></a>
### 129.5 最关键的 SFT vs PPO 对比

| | SFT | PPO |
|---|---|---|
| Prompt | 有 | 有 |
| 模型输出 | token | token / action |
| 谁判断 token 好坏 | 数据集标准答案 | Reward + Critic + GAE |
| 训练信号 | Cross Entropy label | Advantage |
| 当前模型输出 | \(\pi_\theta\) | \(\pi_\theta\) |
| 最终是否构造标量 Loss | 是 | 是 |
| 是否 `backward()` | 是 | 是 |
| Actor 是否更新 | 是 | 是 |
| Critic 是否存在 | 通常没有 | 有 |
| Reward Model | 没有 | 通常冻结使用 |
| Env | 不涉及 | 文本生成中常隐式存在 |

最简单总结：

\[
\boxed{
\text{SFT：人工提前做好监督信号}
}
\]

\[
\boxed{
\text{PPO：Rollout 后动态制造监督信号}
}
\]

---

<a id="origin-7647"></a>
### 129.6 Reward + Critic + GAE 本质是在制造 Actor 的训练信号

SFT：

```text
人工提前告诉：
宁波 = 正确 token
```

PPO：

```text
Actor 自己生成宁波
↓
Reward Model 打分
↓
Critic 给 baseline
↓
GAE
↓
Advantage = +1.2
↓
告诉 Actor：
刚才这个 action 比预期好
```

**因此可以把 Advantage 理解成一种：**

\[
\boxed{
\text{动态产生的软训练信号}
}
\]

它不是传统分类中的 one-hot 标签。

但是它承担了类似职责：

> 告诉模型刚才的 action 应该被鼓励还是被抑制。

---

<a id="origin-7689"></a>
### 129.7 三句话彻底记住

第一句：

\[
\boxed{
\text{SFT 和 PPO 最后都还是普通梯度下降}
}
\]

第二句：

\[
\boxed{
\text{区别主要不在 backward，而在 Loss 是怎么制造出来的}
}
\]

第三句：

> SFT 由数据集直接告诉模型哪个 token 是正确的；PPO 没有标准答案，所以先通过 State、Action、Reward、Critic、GAE 等过程计算 Advantage。Advantage 决定刚才的 action 应该提高还是降低概率；随后真正的梯度仍然沿 `new_log_prob → logits → Transformer → θ` 传播。

> **即：Advantage 算好以后，上游的 Reward、Reward Model、GAE、Environment 不再参与这一轮 Actor 的反向传播；此时 Advantage 被当作一个固定的训练信号，作用类似于 SFT 中的标签：它告诉模型刚才这个 action 应该被鼓励还是抑制、力度有多大。真正参与反向传播的是当前 Actor 的 new_log_prob → logits → Transformer → 参数 θ 这条计算图，Advantage 只是作为一个固定系数控制梯度的方向和强度**

---

<a id="origin-7715"></a>
### 129.8 为什么 PPO 最后还是一个 `loss.backward()`？

因为：

> 强化学习并没有发明一种新的反向传播算法。

它真正改变的是：

\[
\boxed{
\text{Loss 怎么构造}
}
\]

PPO 前面的一大堆：

```text
State
Action
Environment
Reward Model
Reward
Critic
GAE
Advantage
Old Policy
Reference Model
```

主要是在解决：

> 当前刚才做出的 action，到底是好还是坏？应该奖励多少？应该惩罚多少？

一旦 Advantage、Returns、Old Log Prob 等量全部准备好以后：

```text
前面的 RL 数据构造阶段结束
```

后面重新回到普通深度学习：

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
```

---

<a id="origin-7770"></a>
### 129.9 为什么 Reward Model 不需要参与 backward？

因为 Reward Model 得到：

\[
Reward=2
\]

之后，Reward 被当成固定数值。

可以画成：

```text
Reward Model
↓
Reward = 2
↓
GAE / Advantage
↓
固定训练信号
────────────────────
          Actor θ
             ↓
          new_logp
             ↓
          PPO Loss
             ↓
          backward
             ↓
             θ
```

Reward Model 和 Actor 之间没有当前 PPO Loss 的梯度链。

所以 Reward Model：

```text
负责“出分”
不负责当前 PPO 阶段的参数更新
```

---

<a id="origin-7813"></a>
### 129.10 Advantage 到底是什么作用？

所以 Advantage 本身不是梯度。

更准确地说：

\[
\boxed{
A
\text{ 决定 }
\frac{\partial L}
{\partial\log\pi_\theta}
\text{ 的方向和强度}
}
\]

可以把它理解成：

```text
A > 0
→ 好 action
→ 希望提高 probability

A < 0
→ 坏 action
→ 希望降低 probability

|A| 很大
→ 信号更强

|A| 很小
→ 信号更弱
```

因此可以把 Advantage 比作：

\[
\boxed{
\text{方向盘 + 油门}
}
\]

---

<a id="origin-7857"></a>
### 129.11 先把最容易混淆的符号说清楚

PPO 中最重要的三个符号是：

\[
\theta,\qquad
\pi_\theta(a|s),\qquad
\log \pi_\theta(a|s)
\]

它们不是一回事。

---

<a id="origin-7871"></a>
#### 129.11.1 \(\theta\)：真正被训练的模型参数

\[
\boxed{\theta}
\]

表示 Actor 大模型内部所有可训练参数。

例如：

```text
Embedding 参数
W_Q
W_K
W_V
W_O
FFN 参数
RMSNorm 参数
LM Head 参数
……
```

这些参数统称：

\[
\theta
\]

代码中真正交给优化器的是：

```python
actor_model.parameters()
```

最终真正发生的参数更新是：

\[
\boxed{
\theta_{\text{new}}
=
\theta_{\text{old}}
-
\eta\nabla_\theta L
}
\]

其中：

- \(\eta\)：学习率
- \(L\)：Loss
- \(\nabla_\theta L\)：Loss 对模型全部参数的梯度

---

<a id="origin-7925"></a>
#### 129.11.2 \(\pi_\theta(a|s)\)：模型算出来的概率，不是参数

假设当前上下文是：

```text
浙江大学位于
```

模型输出：

```text
宁波    0.70
杭州    0.15
上海    0.03
北京    0.01
……
```

如果当前 action 是：

```text
宁波
```

那么：

\[
\pi_\theta(\text{宁波}|s)=0.70
\]

所以：

\[
\boxed{
\pi_\theta(a|s)
=
\text{参数为 }\theta\text{ 的模型生成 action }a\text{ 的概率}
}
\]

它不是参数。

它是模型前向传播的输出。

---

<a id="origin-7971"></a>
#### 129.11.3 \(\log \pi_\theta(a|s)\)：概率取 log

如果：

\[
\pi_\theta(a|s)=0.7
\]

那么：

\[
\log\pi_\theta(a|s)
=
\log0.7
\approx
-0.357
\]

在 PPO 代码里，经常保存和计算的是：

```text
old_log_prob
new_log_prob
```

而不是直接保存概率。

---

<a id="origin-8000"></a>
### 129.12 三者真正的关系

应该始终记成：

```text
θ
↓
Transformer
↓
hidden state
↓
LM Head
↓
logits
↓
softmax
↓
πθ(a|s)
↓
log
↓
log πθ(a|s)
```

也就是：

\[
\boxed{
\theta
\rightarrow
\pi_\theta
\rightarrow
\log\pi_\theta
}
\]

最重要的区别：

| 符号 | 是什么 | optimizer 直接修改吗？ |
|---|---|---:|
| \(\theta\) | Actor 真正的模型参数 | **是** |
| \(\pi_\theta(a|s)\) | 模型算出来的 action 概率 | 否 |
| \(\log\pi_\theta(a|s)\) | action 的 log probability | 否 |

所以千万不要理解成：

```text
PPO 直接把 π 加 0.1
```

或者：

```text
optimizer 直接修改 logπ
```

真正被修改的一直都是：

\[
\boxed{\theta}
\]

---

<a id="origin-8064"></a>
### 129.13 PPO Actor 最简单的 Loss

先暂时忽略：

```text
Clip
Reference KL
Critic Value Loss
```

只看 PPO Actor 最核心的一项：

\[
L=-A r
\]

其中：

\[
r
=
\frac{\pi_\theta(a|s)}
{\pi_{\text{old}}(a|s)}
\]

代码中一般写成：

\[
r
=
e^{
\log\pi_\theta(a|s)
-
\log\pi_{\text{old}}(a|s)
}
\]

这里：

- \(A\)：Advantage
- \(r\)：当前 Policy 和 Old Policy 对同一个 action 的概率比
- \(\pi_\theta\)：当前 Actor
- \(\pi_{\text{old}}\)：Rollout 时的 Actor

---

<a id="origin-8110"></a>
### 129.14 为什么一直研究 \(\log\pi\)，最后却更新 \(\theta\)？

因为 PPO Loss 不是直接写成某一个 Transformer 权重的函数。

它通常写成：

\[
L=L(\log\pi_\theta)
\]

所以要使用链式法则：

\[
\boxed{
\frac{\partial L}{\partial\theta}
=
\frac{\partial L}
{\partial\log\pi_\theta}
\cdot
\frac{\partial\log\pi_\theta}
{\partial\theta}
}
\]

这两个部分含义完全不同。

第一部分：

\[
\frac{\partial L}
{\partial\log\pi_\theta}
\]

回答：

> 当前这个 action 的 log probability 应该往上还是往下推？力度多大？

第二部分：

\[
\frac{\partial\log\pi_\theta}
{\partial\theta}
\]

回答：

> 为了让这个 log probability 发生变化，Transformer 内部每个参数应该怎么改？

所以：

```text
PPO
↓
决定“这个 token 的概率该升还是该降”
↓
普通神经网络反向传播
↓
把要求分摊给 WQ / WK / WV / FFN / LM Head / …
↓
得到 ∂L/∂θ
```

---

<a id="origin-8174"></a>
### 129.15 大模型只是把一个 \(\theta\) 变成几十亿个参数

真实大模型不是：

\[
\theta=0.6
\]

而是：

\[
\theta
=
(
\theta_1,
\theta_2,
\dots,
\theta_N
)
\]

所以：

\[
\nabla_\theta L
=
\left[
\frac{\partial L}{\partial\theta_1},
\frac{\partial L}{\partial\theta_2},
\dots,
\frac{\partial L}{\partial\theta_N}
\right]
\]

反向传播：

```text
PPO Loss
↓
new_log_prob
↓
log_softmax
↓
logits
↓
LM Head
↓
Transformer 最后一层
↓
……
↓
Transformer 第一层
↓
Embedding
```

于是：

```python
loss.backward()
```

会给所有参与计算图的参数生成：

```python
parameter.grad
```

然后：

```python
actor_optimizer.step()
```

真正修改这些参数。

---

<a id="origin-8252"></a>
### 129.16 PPO 中 State 到底是什么？

对于纯文本生成：

\[
\boxed{
s_t
=
Prompt + 已经生成的 token
}
\]

例如：

```text
s0：
浙江大学位于
```

Actor 生成：

```text
a0：
宁波
```

那么下一个状态：

```text
s1：
浙江大学位于 宁波
```

即：

\[
s_{t+1}
=
[s_t,a_t]
\]

所以 State 没有消失。

它通常就隐含在：

```text
input_ids
```

里面。

---

<a id="origin-8305"></a>
### 129.17 Action 到底是什么？

大模型 PPO 中：

\[
\boxed{
a_t
=
\text{当前实际生成的 token}
}
\]

例如：

```python
completion_ids = [31, 32, 2]
```

那么：

```text
31
32
EOS
```

就是三个 action。

PPO 后面用 `gather` 找到：

> 当前 Actor 对这些已经实际采样出来的 action 给了多大 probability。

所以 Action 通常藏在：

```text
completion_ids
labels
gather index
```

里。

---

<a id="origin-8349"></a>
### 129.18 Environment 去哪了？

传统强化学习：

```text
State
↓
Action
↓
Environment
↓
Next State
↓
Reward
```

例如游戏里：

```python
next_state, reward = env.step(action)
```

但纯文本生成里环境转移非常简单：

\[
s_{t+1}
=
concat(s_t,a_t)
\]

也就是：

```text
当前文本
+
新 token
=
下一状态
```

因此看起来没有一个显式：

```python
env.step(...)
```

不是 Environment 没用了。

而是：

> **文本生成里的状态转移太简单，因此经常被生成循环隐式完成。**

如果换成 GUI Agent：

```text
Action：
点击按钮
↓
Environment：
网页 / 操作系统
↓
Observation：
新页面
```

Environment 就会重新变得非常明显。

---

<a id="origin-8418"></a>
### 129.19 Reward Model 干什么？

假设 Actor 生成完整回答后：

```text
浙江大学位于宁波。
```

Reward Model 给：

\[
Reward=2
\]

Reward Model 到这里的主要任务就是：

\[
\boxed{
\text{把回答质量变成一个数值}
}
\]

它不是当前 PPO Actor 反向传播链的一部分。

---

<a id="origin-8444"></a>
### 129.20 Critic 干什么？

假设生成“宁波”前：

\[
V(s)=0.8
\]

而最终 Reward：

\[
R=2
\]

最简单直觉下：

\[
A
\approx
R-V(s)
\]

所以：

\[
A
=
2-0.8
=
1.2
\]

于是：

```text
Reward：
最终得 2 分

Critic：
原来只预期 0.8 分

↓

实际比预期好

↓

Advantage = +1.2
```

真正代码里一般通过 TD + GAE 得到更稳定的 Advantage。

---

<a id="origin-8498"></a>
### 129.21 Critic 为什么又要更新？

Critic 和 Reward Model 不一样。

Reward Model 通常冻结。

但 Critic 需要不断提高自己的：

\[
V(s)
\]

预测能力。

所以 PPO 中通常同时存在：

\[
L_{\text{policy}}
\]

训练 Actor，以及：

\[
L_{\text{value}}
\]

训练 Critic。

总 Loss 可以写成：

\[
\boxed{
L_{\text{total}}
=
L_{\text{policy}}
+
c_vL_{\text{value}}
+
L_{\text{aux}}
}
\]

然后：

```python
loss.backward()
```

---

<a id="origin-8548"></a>
### 129.22 为什么一个 backward 可以同时训练 Actor 和 Critic？

因为计算图可以分叉：

```text
                    Total Loss
                   /          \
                  /            \
        Policy Loss          Value Loss
             ↓                  ↓
          Actor θ            Critic φ
```

所以：

```python
loss.backward()
```

以后：

```text
Actor 参数：
θ.grad

Critic 参数：
φ.grad
```

都会被算出来。

然后分别：

```python
actor_optimizer.step()
critic_optimizer.step()
```

所以：

> **一个总标量 Loss，并不意味着只更新一个模型。**

它只是把多个子 Loss 汇总成一个反向传播入口。

---

<a id="origin-8594"></a>
### 129.23 Actor 和 Critic 的梯度会串到一起吗？

正常情况下不会。

因为：

\[
L_{\text{policy}}
\]

连接的是 Actor 参数：

\[
\theta
\]

而：

\[
L_{\text{value}}
\]

连接的是 Critic 参数：

\[
\phi
\]

因此：

\[
\frac{\partial L_{\text{value}}}
{\partial\theta}
=
0
\]

而：

\[
\frac{\partial L_{\text{policy}}}
{\partial\phi}
=
0
\]

所以一次 backward 只是：

```text
同时沿两条不同计算图求导
```

---

<a id="origin-8648"></a>
### 129.24 最终完整流程图

<a id="origin-8650"></a>
#### 129.24.1 SFT

```text
Prompt
↓
模型 θ
↓
πθ
↓
和标准答案比较
↓
Cross Entropy Loss
↓
backward
↓
∂L/∂θ
↓
optimizer.step
↓
θ 更新
```

---

<a id="origin-8674"></a>
#### 129.24.2 PPO

```text
Prompt = State
↓
Actor Rollout
↓
Token = Action
↓
不断形成 Next State
↓
完整 Response
↓
Reward Model
↓
Reward
↓
Critic + GAE
↓
Advantage / Returns
↓
这些量固定，不求导
================================
当前 Actor θ 再前向
↓
new_log_prob
↓
ratio
↓
PPO Policy Loss
↓
        ┌──────────────────┐
        │                  │
        │           当前 Critic φ
        │                  ↓
        │              new_value
        │                  ↓
        │              Value Loss
        │                  │
        └────────┬─────────┘
                 ↓
             Total Loss
                 ↓
             backward()
              /       \
             ↓         ↓
          θ.grad     φ.grad
             ↓         ↓
 Actor optimizer   Critic optimizer
             ↓         ↓
         Actor 更新   Critic 更新
```

---

<a id="origin-8729"></a>
### 129.25 最后把所有对象一次性分清楚

| 对象 | 本质 | 当前 PPO 中是否直接训练 |
|---|---|---:|
| \(s_t\) | 当前上下文 / State | 否 |
| \(a_t\) | 当前生成 token / Action | 否 |
| Environment | 状态转移机制 | 否 |
| Reward Model | 完整回答评分器 | 通常否 |
| Reward | 一个固定分数 | 否 |
| Critic | \(V(s)\) 预测模型 | **是** |
| Advantage | Action 相对好坏信号 | 否 |
| Returns | Critic 的训练 Target | 否 |
| Old Log Prob | Rollout 概率快照 | 否 |
| Reference Model | KL 锚点 | 否 |
| Actor \(\theta\) | 当前策略模型 | **是** |
| Critic \(\phi\) | 当前 Value 模型 | **是** |
| Policy Loss | Actor 的训练目标 | 有梯度 |
| Value Loss | Critic 的训练目标 | 有梯度 |

---

<a id="origin-8750"></a>
### 129.26 Clip 从梯度角度是在干什么？

完整 PPO 不只是：

\[
-Ar
\]

还会做 Clip。

最大化形式：

\[
L^{CLIP}
=
\min
\left(
rA,
\operatorname{clip}(r,1-\epsilon,1+\epsilon)A
\right)
\]

训练代码通常把它转成负 Loss 去最小化。

假设：

\[
\epsilon=0.2
\]

则允许区域大致是：

\[
[0.8,1.2]
\]

如果一个好 action：

\[
A>0
\]

但它的：

\[
r=1.4
\]

说明概率已经提高很多。

PPO 会认为：

```text
方向是对的
但是已经走得太远
不要继续获得更多梯度奖励
```

因此 Clip 的本质可以理解成：

\[
\boxed{
\text{限制策略一次更新得太猛}
}
\]

---

<a id="origin-8818"></a>
### 129.27 Reference KL 又在干什么？

PPO Actor 还有一股约束力：

```text
Reference KL
```

可以理解为：

```text
Advantage：
往 Reward 更好的方向走

Reference KL：
可以走，但别离原始模型太远
```

因此 Actor 的总梯度大致来自：

\[
\boxed{
\nabla_\theta L_{\text{Actor}}
=
\nabla_\theta L_{\text{PPO}}
+
\beta
\nabla_\theta L_{\text{KL}}
}
\]

Reference Model 本身被冻结。

梯度只通过当前 Actor 的：

\[
\log\pi_\theta
\]

传回 Actor。

---

<a id="origin-8861"></a>
## 130. 具体例子——从 Advantage 求导到参数更新与概率变化

<a id="origin-8863"></a>
### 130.1 Ratio 到底是什么意思？

假设 Rollout 时：

\[
\pi_{\text{old}}(a|s)=0.4
\]

当前 Actor：

\[
\pi_\theta(a|s)=0.5
\]

那么：

\[
r
=
\frac{0.5}{0.4}
=
1.25
\]

意思：

> 当前 Actor 已经把这个 action 的概率提高到了 Rollout 时的 1.25 倍。

如果：

\[
r=0.7
\]

则表示：

> 当前 action 概率只剩 Old Policy 的 70%。

---

<a id="origin-8903"></a>
### 130.2 先看 \(A=+2\)：为什么概率会升高？

假设：

\[
A=+2
\]

这表示：

> 当前 action 比预期好，希望以后更容易生成。

再假设：

\[
\log\pi_{\text{old}}=-0.8
\]

当前：

\[
\log\pi_\theta=-0.7
\]

所以：

\[
\log r
=
-0.7-(-0.8)
=
0.1
\]

\[
r=e^{0.1}\approx1.105
\]

Loss：

\[
L=-Ar
\]

\[
=
-2\times1.105
\]

\[
\boxed{
L\approx-2.210
}
\]

---

<a id="origin-8960"></a>
#### 130.2.1 对 \(\log\pi_\theta\) 求导

因为：

\[
r
=
e^{\log\pi_\theta-\log\pi_{\text{old}}}
\]

所以：

\[
\frac{\partial r}
{\partial\log\pi_\theta}
=
r
\]

又因为：

\[
L=-Ar
\]

所以：

\[
\boxed{
\frac{\partial L}
{\partial\log\pi_\theta}
=
-Ar
}
\]

代入：

\[
A=2,\qquad r=1.105
\]

得到：

\[
\frac{\partial L}
{\partial\log\pi_\theta}
=
-2\times1.105
\]

\[
\boxed{
\frac{\partial L}
{\partial\log\pi_\theta}
\approx-2.210
}
\]

这是负梯度。

梯度下降会朝梯度反方向走。

因此它会推动：

\[
\log\pi_\theta
\]

增大。

而：

\[
\pi_\theta=e^{\log\pi_\theta}
\]

所以：

\[
\log\pi_\theta\uparrow
\Rightarrow
\pi_\theta\uparrow
\]

最终：

```text
A > 0
↓
这是一个好 action
↓
提高这个 action 的 probability
```

---

<a id="origin-9057"></a>
### 130.3 重点：\(A=-2\) 的完整求导例子

现在看你最关心的情况：

\[
\boxed{
A=-2
}
\]

它意味着：

> 当前 action 比预期差，所以希望以后更不容易生成。

---

<a id="origin-9073"></a>
#### 130.3.1 给定 Old Policy 和 Current Policy

假设：

\[
\log\pi_{\text{old}}=-0.8
\]

当前 Actor：

\[
\log\pi_\theta=-0.7
\]

因此：

\[
\log r
=
\log\pi_\theta
-
\log\pi_{\text{old}}
\]

\[
=
-0.7-(-0.8)
\]

\[
=
0.1
\]

于是：

\[
r=e^{0.1}
\approx
1.105
\]

这意味着：

> 当前 Actor 反而已经把这个坏 action 的概率提高到了 Old Policy 的约 1.105 倍。

所以 PPO 应该产生一个梯度，把它压回去。

---

<a id="origin-9123"></a>
#### 130.3.2 计算 Loss

最简单的 PPO Loss：

\[
L=-Ar
\]

代入：

\[
A=-2
\]

得到：

\[
L
=
-(-2)\times1.105
\]

\[
=
2\times1.105
\]

\[
\boxed{
L\approx2.210
}
\]

---

<a id="origin-9158"></a>
#### 130.3.3 对 \(\log\pi_\theta\) 求导

先有：

\[
L=-Ar
\]

所以：

\[
\frac{\partial L}{\partial r}
=
-A
\]

而：

\[
r
=
e^{\log\pi_\theta-\log\pi_{\text{old}}}
\]

所以：

\[
\frac{\partial r}
{\partial\log\pi_\theta}
=
r
\]

使用链式法则：

\[
\frac{\partial L}
{\partial\log\pi_\theta}
=
\frac{\partial L}{\partial r}
\frac{\partial r}
{\partial\log\pi_\theta}
\]

于是：

\[
=
(-A)\times r
\]

即：

\[
\boxed{
\frac{\partial L}
{\partial\log\pi_\theta}
=
-Ar
}
\]

现在：

\[
A=-2,\qquad r=1.105
\]

因此：

\[
\frac{\partial L}
{\partial\log\pi_\theta}
=
-(-2)\times1.105
\]

\[
=
2.210
\]

所以：

\[
\boxed{
\frac{\partial L}
{\partial\log\pi_\theta}
\approx+2.210
}
\]

注意：

> 现在得到的是**正梯度**。

---

<a id="origin-9256"></a>
### 130.4 正梯度为什么会让 action probability 下降？

假设暂时把：

\[
\log\pi
\]

当成一个直接可优化变量，只为了理解方向。

梯度下降：

\[
\log\pi_{\text{new}}
=
\log\pi_{\text{old-current}}
-
\eta
\frac{\partial L}{\partial\log\pi}
\]

现在：

\[
\frac{\partial L}{\partial\log\pi}
=
+2.210
\]

所以：

\[
\log\pi_{\text{new}}
=
\log\pi_{\text{old-current}}
-
\eta(2.210)
\]

一定会让：

\[
\log\pi
\]

变小。

因为：

\[
\pi=e^{\log\pi}
\]

所以：

\[
\boxed{
\log\pi\downarrow
\Rightarrow
\pi\downarrow
}
\]

因此：

\[
\boxed{
A<0
\Rightarrow
\text{这个 action 的概率被压低}
}
\]

但是要再次强调：

> 真实神经网络并不会直接修改 \(\log\pi\)。

真正修改的是：

\[
\theta
\]

---

<a id="origin-9341"></a>
### 130.5 把 \(A=-2\) 的梯度继续传到真正参数 \(\theta\)

为了能够手算，假设一个极简模型只有一个参数：

\[
\theta
\]

并假设：

\[
\log\pi_\theta
=
-1+0.5\theta
\]

这只是教学用的简化函数。

当前：

\[
\theta=0.6
\]

那么：

\[
\log\pi_\theta
=
-1+0.5\times0.6
\]

\[
=
-0.7
\]

与前面的假设一致。

现在：

\[
\frac{\partial\log\pi_\theta}
{\partial\theta}
=
0.5
\]

而刚才已经得到：

\[
\frac{\partial L}
{\partial\log\pi_\theta}
=
2.210
\]

所以：

\[
\frac{\partial L}{\partial\theta}
=
\frac{\partial L}
{\partial\log\pi_\theta}
\frac{\partial\log\pi_\theta}
{\partial\theta}
\]

代入：

\[
=
2.210\times0.5
\]

\[
\boxed{
\frac{\partial L}
{\partial\theta}
=
1.105
}
\]

---

<a id="origin-9427"></a>
### 130.6 真正执行一次参数更新

假设：

\[
\eta=0.1
\]

当前：

\[
\theta_{\text{old}}=0.6
\]

梯度：

\[
\frac{\partial L}{\partial\theta}
=
1.105
\]

梯度下降：

\[
\theta_{\text{new}}
=
\theta_{\text{old}}
-
\eta
\frac{\partial L}{\partial\theta}
\]

所以：

\[
=
0.6
-
0.1\times1.105
\]

\[
=
0.4895
\]

即：

\[
\boxed{
\theta:
0.6000
\rightarrow
0.4895
}
\]

真正被 optimizer 修改的是：

\[
\boxed{\theta}
\]

---

<a id="origin-9493"></a>
### 130.7 验证概率真的下降

更新前：

\[
\theta=0.6
\]

所以：

\[
\log\pi_\theta
=
-1+0.5\times0.6
=
-0.7
\]

于是：

\[
\pi_\theta
=
e^{-0.7}
\approx0.4966
\]

也就是：

```text
更新前概率 ≈ 49.66%
```

更新后：

\[
\theta=0.4895
\]

所以：

\[
\log\pi_\theta
=
-1+0.5\times0.4895
\]

\[
\approx
-0.75525
\]

于是：

\[
\pi_\theta
=
e^{-0.75525}
\approx0.4699
\]

也就是：

```text
更新前：49.66%
       ↓
更新后：46.99%
```

最终真的实现：

\[
\boxed{
A=-2
\Rightarrow
\pi_\theta(a|s)\text{ 下降}
}
\]

---

<a id="origin-9574"></a>
### 130.8 把 \(A=-2\) 的全过程压缩成一条链

```text
A = -2
↓
说明这个 action 比预期差
↓
L = -A × ratio
↓
∂L/∂logπθ = -A × ratio
↓
因为 A < 0
↓
∂L/∂logπθ > 0
↓
通过链式法则
↓
∂L/∂θ
↓
optimizer 做梯度下降
↓
θ 改变
↓
logπθ 下降
↓
πθ(a|s) 下降
↓
以后这个坏 action 更不容易生成
```

最值得记住：

\[
\boxed{
A<0
\Rightarrow
\frac{\partial L}
{\partial\log\pi_\theta}>0
\Rightarrow
\text{梯度下降最终压低 action probability}
}
\]

---

<a id="origin-9619"></a>
### 130.9 \(A=-2\) 最终一句话

\[
\boxed{
A=-2
}
\]

意味着：

```text
这个 action 比预期差
↓
PPO Loss 对 logπθ 的梯度为正
↓
梯度下降推动对应 log probability 下降
↓
链式法则把这个信号传给模型参数 θ
↓
optimizer 修改 θ
↓
重新前向后，该 action 的 probability 下降
```

所以最准确的说法不是：

> “Advantage 直接修改 probability。”

而是：

\[
\boxed{
Advantage
\rightarrow
\text{影响 Loss 的梯度}
\rightarrow
\nabla_\theta L
\rightarrow
修改\theta
\rightarrow
\pi_\theta\text{ 随之变化}
}
\]


---

<a id="origin-9666"></a>
## 131. 详细案例：大模型 PPO：先搞清楚“一轮 PPO、一批 Rollout、一个 Rollout”

在正式讲 PPO 的 Loss 之前，首先必须把三个概念区分开：

```text
一轮 PPO
    ↓
先生成一批 Rollout
    ↓
这一批 Rollout 全部算好 Reward / Advantage / Target
    ↓
再拿这一批固定数据训练若干个 PPO Epoch
    ↓
丢掉旧 Rollout
    ↓
开始下一轮 PPO
```

所以：

\[
\boxed{
\text{一轮 PPO}
\neq
\text{一个 Rollout}
}
\]

而是：

\[
\boxed{
\text{一轮 PPO}
=
\text{生成一批 Rollout}
+
\text{用这一批 Rollout 做若干次梯度更新}
}
\]

---

<a id="origin-9708"></a>
### 131.1 什么叫一个 Rollout？

对于大语言模型，一个 Rollout 可以非常简单地理解成：

> **给 Actor 一个 Prompt，让 Actor 从头到尾真正生成一次完整回答。**

例如：

```text
Prompt：

请介绍一下浙江大学。
```

Actor 开始生成：

```text
浙江
↓
大学
↓
是
↓
中国
↓
著名
↓
高校
↓
……
↓
EOS
```

这一整条生成过程：

\[
\boxed{
Prompt
\rightarrow
Token_1
\rightarrow
Token_2
\rightarrow
\cdots
\rightarrow
Token_T
}
\]

就是：

\[
\boxed{
一个\ Rollout
}
\]

也可以叫：

\[
\boxed{
一条 trajectory
}
\]

---

<a id="origin-9776"></a>
### 131.2 一个 Rollout 里面其实有很多个强化学习 Step

假设模型生成：

```text
浙江 / 大学 / 位于 / 杭州 / EOS
```

那么这不是一个动作。

而是多个动作：

```text
Step 1：生成“浙江”
Step 2：生成“大学”
Step 3：生成“位于”
Step 4：生成“杭州”
Step 5：生成 EOS
```

对于第 \(t\) 个 Token：

\[
s_t
=
\text{Prompt + 前面已经生成的所有 Token}
\]

\[
a_t
=
\text{当前生成的 Token}
\]

例如：

---

<a id="origin-9814"></a>
#### 131.2.1 Step 1

状态：

```text
请介绍一下浙江大学。
```

动作：

```text
浙江
```

即：

\[
a_1=\text{“浙江”}
\]

---

<a id="origin-9836"></a>
#### 131.2.2 Step 2

状态：

```text
请介绍一下浙江大学。浙江
```

动作：

```text
大学
```

---

<a id="origin-9852"></a>
#### 131.2.3 Step 3

状态：

```text
请介绍一下浙江大学。浙江大学
```

动作：

```text
位于
```

---

因此，一个 Rollout：

\[
\boxed{
\tau
=
(s_1,a_1,s_2,a_2,\cdots,s_T,a_T)
}
\]

本身就包含很多个：

\[
(s_t,a_t)
\]

训练样本。

---

<a id="origin-9888"></a>
### 131.3 PPO 实际上不会只做一个 Rollout

真正训练的时候，不可能：

```text
生成一个回答
↓
马上训练一次
```

通常是先准备：

\[
N
\]

个 Prompt。

例如：

```text
Q1：介绍浙江大学
Q2：解释 Transformer
Q3：写一个 Python 排序程序
Q4：解释牛顿第二定律
...
Q128：……
```

然后 Actor 对这些 Prompt 分别生成回答。

得到：

```text
Q1 → Response 1
Q2 → Response 2
Q3 → Response 3
...
Q128 → Response 128
```

每一条：

```text
Prompt + Response
```

就是一个 Rollout。

因此：

\[
\boxed{
\text{Rollout Batch}
=
\{\tau_1,\tau_2,\tau_3,\dots,\tau_N\}
}
\]

---

<a id="origin-9949"></a>
### 131.4 一个 Prompt 也可以生成多个 Rollout

有些实现中，一个 Prompt 不一定只生成一个回答。

例如同一个 Prompt：

```text
Q1：
介绍一下浙江大学。
```

可以采样 4 次：

```text
Response 1
Response 2
Response 3
Response 4
```

那么：

\[
Q_1
\]

就产生了：

\[
4
\]

个 Rollout。

如果：

\[
128
\]

个 Prompt，每个 Prompt 采样：

\[
4
\]

次，那么一批数据就是：

\[
128\times4=512
\]

条 Rollout。

因此更一般地：

\[
\boxed{
N_{\text{rollout}}
=
N_{\text{prompt}}
\times
N_{\text{response per prompt}}
}
\]

不过为了讲 PPO 原理，后面可以先假设：

\[
\boxed{
一个 Prompt 生成一个 Response
}
\]

这样最容易理解。

---

<a id="origin-10027"></a>
### 131.5 一轮 PPO 的第一件事：先生成完整的一批 Rollout

假设这一轮开始时：

\[
Actor=\pi_{\theta_0}
\]

此时把它定义成：

\[
\boxed{
\pi_{\text{old}}
=
\pi_{\theta_0}
}
\]

然后：

```text
Q1 → rollout 1
Q2 → rollout 2
Q3 → rollout 3
...
QN → rollout N
```

注意：

> **先把这一批 Rollout 全部生成出来。**

这个过程中：

\[
\boxed{
Actor 不更新
}
\]

也就是说：

```text
生成 rollout 1
不更新

生成 rollout 2
不更新

生成 rollout 3
不更新

……

全部 rollout 生成结束
```

因此整个 Rollout Batch 都是由同一个：

\[
\boxed{
\pi_{\text{old}}
}
\]

生成的。

---

<a id="origin-10096"></a>
### 131.6 每生成一个 Rollout，到底保存什么？

假设某一条 Rollout 是：

```text
Prompt
↓
token1
↓
token2
↓
token3
↓
token4
↓
EOS
```

对每一个 Token，都保存：

\[
\boxed{
s_t
}
\]

当前状态。

\[
\boxed{
a_t
}
\]

真正采样出来的 Token。

以及：

\[
\boxed{
\log\pi_{\text{old}}(a_t|s_t)
}
\]

也就是：

> 当时生成这个 Token 时，old Policy 给这个 Token 的 log probability。

同时 Critic 在这个状态上给出：

\[
\boxed{
V_{\text{old}}(s_t)
}
\]

所以一个 Rollout 最开始保存的数据大概是：

```text
token1:
state_1
action_1
old_log_prob_1
old_value_1

token2:
state_2
action_2
old_log_prob_2
old_value_2

token3:
state_3
action_3
old_log_prob_3
old_value_3

...
```

---

<a id="origin-10178"></a>
### 131.7 整批 Rollout 最开始长什么样？

假设：

\[
N=4
\]

那么可能是：

```text
================ Rollout 1 ================

Prompt Q1

token1
token2
token3
token4

保存：
old_log_prob
old_value


================ Rollout 2 ================

Prompt Q2

token1
token2
token3

保存：
old_log_prob
old_value


================ Rollout 3 ================

Prompt Q3

token1
token2
token3
token4
token5

保存：
old_log_prob
old_value


================ Rollout 4 ================

Prompt Q4

token1
token2

保存：
old_log_prob
old_value
```

这里不同回答长度完全可以不同。

例如：

\[
T_1=4
\]

\[
T_2=3
\]

\[
T_3=5
\]

\[
T_4=2
\]

后续训练时通常通过：

```text
padding
+
attention mask / response mask
```

把它们组成 Batch。

---

<a id="origin-10275"></a>
### 131.8 Rollout 完成以后，先不要训练

这是 PPO 一个非常重要的地方。

当：

\[
N
\]

条 Rollout 全部生成以后，并不是马上：

```text
loss.backward()
```

而是先对这一批数据进行：

```text
Reward 计算
↓
Value 计算
↓
TD Error
↓
GAE
↓
Value Target
```

把训练需要的东西全部准备出来。

也就是说：

\[
\boxed{
Rollout
\text{ 和 }
Optimization
\text{ 是两个阶段}
}
\]

---

<a id="origin-10320"></a>
### 131.9 第一步：Reward Model 给每条 Rollout 的完整回答打分

例如：

```text
Rollout 1：
Q1 + Response1
```

送入 Reward Model：

\[
R_\psi(x_1,y_1)
\]

得到：

\[
3.2
\]

Rollout 2：

\[
R_\psi(x_2,y_2)=1.7
\]

Rollout 3：

\[
R_\psi(x_3,y_3)=4.1
\]

……

因此：

```text
Rollout 1 → Reward Model Score = 3.2
Rollout 2 → Reward Model Score = 1.7
Rollout 3 → Reward Model Score = 4.1
...
```

Reward Model 通常对：

\[
\boxed{
完整 Response
}
\]

给一个最终分数。

---

<a id="origin-10376"></a>
### 131.10 第二步：Reference Model 计算 KL

对于 Rollout 中真正生成出来的每个 Token：

\[
a_t
\]

Reference Model 计算：

\[
\log\pi_{\text{ref}}(a_t|s_t)
\]

而 rollout 时已经保存：

\[
\log\pi_{\text{old}}(a_t|s_t)
\]

因此可以计算每个 Token 的 KL shaping：

\[
\boxed{
r_t^{KL}
=
-\beta
\left[
\log\pi_{\text{old}}(a_t|s_t)
-
\log\pi_{\text{ref}}(a_t|s_t)
\right]
}
\]

于是一个 Rollout 可以得到：

```text
token1 → KL reward
token2 → KL reward
token3 → KL reward
...
```

最后一个 Token 再加入：

\[
R_\psi(x,y)
\]

---

<a id="origin-10428"></a>
### 131.11 于是每一条 Rollout 都得到一串 Token Reward

例如一个 Rollout 有 4 个 Token：

\[
a_1,a_2,a_3,a_4
\]

最终可能得到：

\[
r_1=-0.01
\]

\[
r_2=-0.02
\]

\[
r_3=-0.01
\]

\[
r_4=3.2-0.02
\]

所以：

```text
Rollout 1

token1 → r1
token2 → r2
token3 → r3
token4 → r4
```
<a id="origin-10464"></a>
#### 131.11.1 为什么每个 Token 都会有 Reward？

在大模型 PPO / RLHF 中，Reward Model 通常是对**整个回答**打一个总分：

\[
R_\psi(x,y)
\]

例如：

\[
R_\psi(x,y)=3.2
\]

但是为了让每个 Token 都能参与强化学习训练，通常还会给每个 Token 加一个 KL Penalty。

对于第 \(t\) 个 Token：

\[
\boxed{
r_t^{KL}
=
-\beta
\left[
\log\pi_{\text{old}}(a_t|s_t)
-
\log\pi_{\text{ref}}(a_t|s_t)
\right]
}
\]

它的作用是：

> 如果当前 Actor 相比 Reference Model 偏离太多，就给这个 Token 一个惩罚。

---

<a id="origin-10501"></a>
##### 131.11.1.1 例子

假设一个回答有 4 个 Token：

\[
a_1,a_2,a_3,a_4
\]

它们的 KL Reward 分别是：

\[
-0.01,\;-0.02,\;-0.01,\;-0.02
\]

Reward Model 对整个回答打分：

\[
R_\psi(x,y)=3.2
\]

那么可以构造成：

\[
r_1=-0.01
\]

\[
r_2=-0.02
\]

\[
r_3=-0.01
\]

最后一个 Token 再加入整句话的 Reward Model 分数：

\[
r_4=3.2-0.02=3.18
\]

所以：

```text
token1 → -0.01       ← KL
token2 → -0.02       ← KL
token3 → -0.01       ← KL
token4 → 3.18        ← Reward Model 分数 + KL
```

---

<a id="origin-10552"></a>
#### 131.11.2 可以直接记成

前面的 Token：

\[
\boxed{
r_t=-KLPenalty_t
}
\]

最后一个 Token：

\[
\boxed{
r_T
=
RewardModelScore
-
KLPenalty_T
}
\]

所以你前面看到：

\[
-0.01,\;-0.02,\;-0.01
\]

这些小的负 Reward，**主要就是 KL Penalty 带来的。**

一句话：

\[
\boxed{
\text{Reward Model 给整句话打分，KL 给每个 Token 一个约束性 Reward。}
}
\]
---

<a id="origin-10591"></a>
### 131.12 第三步：每条 Rollout 分别计算 GAE

现在每个 Token 已经有：

\[
r_t
\]

同时 rollout 时已经保存：

\[
V_{\text{old}}(s_t)
\]

于是：

\[
\boxed{
\delta_t
=
r_t
+
\gamma V_{\text{old}}(s_{t+1})
-
V_{\text{old}}(s_t)
}
\]

然后从后往前：

\[
\boxed{
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
}
\]

所以每一个 Rollout 最后都会得到：

```text
token1 → advantage_1
token2 → advantage_2
token3 → advantage_3
...
```

---

<a id="origin-10642"></a>
### 131.13 再计算每个 Token 的 Value Target

有了：

\[
A_t
\]

以及：

\[
V_{\text{old}}(s_t)
\]

得到：

\[
\boxed{
V_t^{target}
=
A_t+V_{\text{old}}(s_t)
}
\]

因此，一条 Rollout 最终变成了一串完整训练样本：

```text
(state_t,
 action_t,
 old_log_prob_t,
 old_value_t,
 reward_t,
 advantage_t,
 value_target_t)
```

---

<a id="origin-10680"></a>
### 131.14 所有 Rollout 都处理完成以后，才真正得到 PPO Dataset

假设有：

\[
N
\]

条 Rollout。

那么：

```text
Rollout 1
    ↓
很多个 Token Sample

Rollout 2
    ↓
很多个 Token Sample

Rollout 3
    ↓
很多个 Token Sample

...

Rollout N
    ↓
很多个 Token Sample
```

最终合起来形成：

\[
\boxed{
\text{这一轮 PPO 的训练数据集}
}
\]

可以粗略理解成：

```text
Rollout Batch
↓
展开成大量 Token-level Sample
↓
组成 PPO Training Dataset
```

---

<a id="origin-10732"></a>
### 131.15 到这里才正式进入 PPO Optimization

现在这一批数据已经全部准备好了：

```text
state
action

old_log_prob
old_value

reward

advantage
value_target
```

从现在开始：

\[
\boxed{
\text{不再生成新的 Token}
}
\]

并且这一批数据中的：

```text
action
old_log_prob
old_value
advantage
value_target
```

全部固定。

---

<a id="origin-10771"></a>
### 131.16 然后把这批 Rollout 切成 Minibatch 训练

例如一批 Rollout 最终产生：

\[
8192
\]

个有效 Token。

可以切成：

```text
Minibatch 1
Minibatch 2
Minibatch 3
...
```

然后：

```text
Minibatch 1
↓
计算 Actor Loss
↓
计算 Critic Loss
↓
backward
↓
optimizer.step()

Minibatch 2
↓
重新 forward
↓
计算新的 current log_prob
↓
计算新的 current value
↓
算 Loss
↓
更新

...
```

---

<a id="origin-10820"></a>
### 131.17 一个 PPO Epoch 是什么？

一个 PPO Epoch 的意思就是：

> **把刚才生成的这一整批 Rollout 数据，完整训练一遍。**

例如：

```text
Rollout Batch
    ↓
Minibatch 1
Minibatch 2
Minibatch 3
Minibatch 4
```

全部训练完成：

\[
\boxed{
1\ PPO\ Epoch
}
\]

---

<a id="origin-10847"></a>
### 131.18 PPO 通常会对同一批 Rollout 训练多个 Epoch

例如：

```text
================ Epoch 1 ================

同一批 Rollout
↓
全部 Minibatch 训练一遍


================ Epoch 2 ================

还是同一批 Rollout
↓
全部 Minibatch 再训练一遍


================ Epoch 3 ================

还是同一批 Rollout
↓
全部 Minibatch 再训练一遍
```

注意：

\[
\boxed{
Rollout\ 没有重新生成
}
\]

固定的仍然是：

\[
old\_log\_prob
\]

\[
A_t
\]

\[
V_t^{target}
\]

但是 Actor 已经不断发生变化：

\[
\theta_0
\rightarrow
\theta_1
\rightarrow
\theta_2
\rightarrow
\cdots
\]

所以每次 forward 时：

\[
\pi_\theta(a_t|s_t)
\]

会重新计算。

---

<a id="origin-10917"></a>
### 131.19 为什么要保存 old_log_prob？

假设 rollout 时：

\[
\pi_{\text{old}}(a_t|s_t)=0.30
\]

因此保存：

\[
old\_prob=0.30
\]

第一次 PPO Optimization 刚开始：

\[
\pi_\theta=0.30
\]

所以：

\[
\rho_t
=
\frac{0.30}{0.30}
=
1
\]

更新一次之后：

\[
\pi_{\theta_1}(a_t|s_t)=0.33
\]

那么：

\[
\rho_t
=
\frac{0.33}{0.30}
=
1.1
\]

再更新以后：

\[
\pi_{\theta_2}(a_t|s_t)=0.35
\]

于是：

\[
\rho_t
=
\frac{0.35}{0.30}
=
1.167
\]

注意：

\[
\boxed{
分母始终是 rollout 时保存的 0.30
}
\]

所以：

\[
\boxed{
\pi_{\text{old}}
\text{ 固定}
}
\]

而：

\[
\boxed{
\pi_\theta
\text{ 不断变化}
}
\]

---

<a id="origin-11007"></a>
### 131.20 PPO Actor Loss 就是在这里计算

有：

\[
\boxed{
\rho_t
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
}
\]

以及固定好的：

\[
A_t
\]

于是：

\[
\boxed{
L^{CLIP}
=
\min
\left(
\rho_tA_t,
\operatorname{clip}
(
\rho_t,
1-\epsilon,
1+\epsilon
)
A_t
\right)
}
\]

代码里通常变成：

\[
\boxed{
Loss_{\text{Actor}}
=
-
L^{CLIP}
}
\]

然后：

```python
actor_loss.backward()
optimizer.step()
```

---

<a id="origin-11069"></a>
### 131.21 Critic 同时也训练

当前 Critic 重新计算：

\[
V_\phi(s_t)
\]

而 target 已经固定：

\[
V_t^{target}
\]

所以：

\[
\boxed{
L_{\text{Critic}}
=
\left(
V_\phi(s_t)-V_t^{target}
\right)^2
}
\]

然后同样：

```python
critic_loss.backward()
optimizer.step()
```

或者 Actor 与 Critic Loss 合并以后一起 backward。

---

<a id="origin-11106"></a>
### 131.22 多个 PPO Epoch 完成以后怎么办？

假设：

```text
Epoch 1
Epoch 2
Epoch 3
Epoch 4
```

全部结束。

这时候：

\[
\boxed{
这一批 Rollout 的使命结束
}
\]

旧数据被丢掉。

此时 Actor 已经从：

\[
\theta_0
\]

更新成：

\[
\theta_K
\]

于是：

\[
\boxed{
\pi_{\theta_K}
}
\]

成为下一轮新的：

\[
\boxed{
\pi_{\text{old}}
}
\]

然后重新：

```text
取一批 Prompt
↓
重新 Rollout
↓
生成一批新的回答
↓
重新算 Reward
↓
重新算 Advantage
↓
重新算 Value Target
↓
再做若干 PPO Epoch
```

如此不断循环。

---

<a id="origin-11179"></a>
### 131.23 整个 PPO 最清楚的层级关系

一定要把这四层分开：

```text
========================================
第 1 层：整个 PPO Training
========================================

有很多轮 PPO Iteration


        ↓


========================================
第 2 层：一轮 PPO Iteration
========================================

生成一批 Rollout
+
使用这一批 Rollout 做多个 PPO Epoch


        ↓


========================================
第 3 层：一批 Rollout
========================================

Rollout 1
Rollout 2
Rollout 3
...
Rollout N


        ↓


========================================
第 4 层：一个 Rollout
========================================

Prompt
↓
token1
↓
token2
↓
token3
↓
...
↓
EOS
```

所以完整结构是：

\[
\boxed{
PPO\ Training
\supset
PPO\ Iteration
\supset
Rollout\ Batch
\supset
Rollout
\supset
Token\ Step
}
\]

---

<a id="origin-11255"></a>
### 131.24 最终完整流程

```text
当前 Actor
πθ0
│
├─────────────── 第一轮 PPO ───────────────┐
│                                          │
│   定义：πold = πθ0                       │
│                                          │
│   取 N 个 Prompt                         │
│        ↓                                 │
│   生成 N 条 Rollout                      │
│        ↓                                 │
│   每个 Rollout 包含多个 Token Step       │
│        ↓                                 │
│   保存：                                 │
│   action                                 │
│   old_log_prob                           │
│   old_value                              │
│        ↓                                 │
│   Reward Model 打分                      │
│        ↓                                 │
│   Reference Model 算 KL                  │
│        ↓                                 │
│   构造每个 Token Reward                  │
│        ↓                                 │
│   计算 TD Error                          │
│        ↓                                 │
│   计算 GAE                               │
│        ↓                                 │
│   得到 Advantage                         │
│        ↓                                 │
│   得到 Value Target                      │
│                                          │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━       │
│   到这里：Rollout Dataset 全部固定       │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━       │
│        ↓                                 │
│   PPO Epoch 1                            │
│        ↓                                 │
│   PPO Epoch 2                            │
│        ↓                                 │
│   PPO Epoch 3                            │
│        ↓                                 │
│   Actor / Critic 被更新                  │
│                                          │
└──────────────────────────────────────────┘
        ↓

得到新的 Actor：

πθK

        ↓

把 πθK 当成下一轮新的 πold

        ↓

重新生成一批新的 Rollout

        ↓

第二轮 PPO

        ↓

……
```

---

<a id="origin-11328"></a>
### 131.25 一句话总结


PPO 不是“生成一个回答就训练一次”，而是先用当前 Actor 批量生成很多条完整 Rollout；
再把每条 Rollout 中每个 Token 的 old probability、Reward、Value、Advantage 和 Value Target 全部算好；
然后把这整批数据固定下来，切成 Minibatch，反复训练若干个 PPO Epoch；
最后丢掉这批旧数据，用更新后的 Actor 再生成下一批 Rollout。


因此整个 PPO 最核心的节奏就是：

\[
\boxed{
\text{Rollout 一批}
\rightarrow
\text{算好训练目标}
\rightarrow
\text{冻结这批数据}
\rightarrow
\text{训练多次}
\rightarrow
\text{丢掉}
\rightarrow
\text{重新 Rollout}
}
\]
---

<a id="origin-11356"></a>
## 132. 一个完整数值案例

Prompt：

```text
1+1=
```

旧 Policy：

```text
"2"：0.80
"3"：0.10
其他：0.10
```

Rollout 采到了：

```text
"2"
```

保存：

\[
\pi_{\text{old}}("2"|s)=0.8
\]

Critic：

\[
V_{\text{old}}(s)=5
\]

最终 Reward 很好。

通过 GAE：

\[
A=2
\]

所以 Value Target：

\[
V^{target}=7
\]

---

新 Policy 更新后：

\[
\pi_{\text{new}}("2"|s)=0.92
\]

Ratio：

\[
\rho
=
\frac{0.92}{0.8}
=
1.15
\]

如果：

\[
\epsilon=0.2
\]

那么：

\[
clip(1.15,0.8,1.2)=1.15
\]

所以：

\[
1.15\times2=2.3
\]

还处于正常鼓励区。

---

如果新概率继续升到：

\[
0.99
\]

那么：

\[
\rho
=
1.2375
\]

未 Clip：

\[
1.2375\times2=2.475
\]

Clip：

\[
1.2\times2=2.4
\]

PPO 最终只算：

\[
2.4
\]

说明：

> 继续提高概率已经不再得到额外奖励。

---

<a id="origin-11482"></a>
## 133. PPO 中 old policy、current policy 和 ratio 的时间关系

在一批 Rollout 刚刚生成完、Actor 还没有做任何参数更新时：

\[
\boxed{
\pi_\theta
=
\pi_{\text{old}}
}
\]

因此：

\[
\boxed{
\rho_t
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
=
1
}
\]

---

<a id="origin-11512"></a>
### 133.1 第一次更新之前

假设 Rollout 时：

\[
\pi_{\text{old}}(a_t|s_t)=0.30
\]

此时当前 Actor 还没更新：

\[
\pi_\theta(a_t|s_t)=0.30
\]

所以：

\[
\rho_t
=
\frac{0.30}{0.30}
=
1
\]

注意：

> **虽然 ratio 等于 1，但 PPO Loss 仍然可以正常计算梯度。**

因为：

\[
\rho_t
\]

里面仍然包含：

\[
\pi_\theta
\]

所以第一次更新仍然可以正常进行。

---

<a id="origin-11556"></a>
### 133.2 第一次参数更新之后

执行：

```python
loss.backward()
optimizer.step()
```

以后：

\[
\theta_0
\rightarrow
\theta_1
\]

假设现在：

\[
\pi_{\theta_1}(a_t|s_t)=0.33
\]

但是 old policy 仍然固定为 Rollout 时的：

\[
\pi_{\text{old}}(a_t|s_t)=0.30
\]

于是：

\[
\boxed{
\rho_t
=
\frac{0.33}{0.30}
=
1.1
}
\]

这时：

\[
\boxed{
\pi_{\text{current}}
\neq
\pi_{\text{old}}
}
\]

PPO 的新旧策略比较才开始明显体现出来。

---

<a id="origin-11611"></a>
### 133.3 再更新一次

假设：

\[
\theta_1
\rightarrow
\theta_2
\]

当前概率变成：

\[
\pi_{\theta_2}(a_t|s_t)=0.36
\]

而 old probability 仍然是：

\[
0.30
\]

那么：

\[
\rho_t
=
\frac{0.36}{0.30}
=
1.2
\]

如果继续变成：

\[
0.39
\]

那么：

\[
\rho_t
=
\frac{0.39}{0.30}
=
1.3
\]

此时如果：

\[
\epsilon=0.2
\]

那么 Clip 范围大约是：

\[
[0.8,1.2]
\]

所以：

\[
\rho_t=1.3
\]

就说明当前 Policy 相比 old Policy 已经变化比较大，PPO 会开始限制继续大幅更新。

---

<a id="origin-11681"></a>
### 133.4 完整生命周期

```text
当前 Actor = θ0
        ↓
生成一批 Rollout
        ↓
保存 old_log_prob
        ↓

此时：

current policy = old policy

所以：

ratio = 1

        ↓
第一次 PPO 更新
        ↓
θ0 → θ1
        ↓

old policy 仍然固定为 θ0
current policy 已经变成 θ1

所以：

ratio = πθ1 / πold

        ↓
继续训练同一批 Rollout
        ↓
θ1 → θ2
        ↓

ratio = πθ2 / πold

        ↓
继续若干 minibatch / epoch
        ↓
训练结束
        ↓
丢掉这一批 Rollout
        ↓
当前 Actor 成为下一轮新的 old policy
        ↓
重新 Rollout
```

---

<a id="origin-11734"></a>
### 133.5 最关键的一点

不要说：

\[
\boxed{
\text{只有更新以后 ratio 才有意义}
}
\]

更准确应该说：

\[
\boxed{
\text{ratio 从第一次 PPO Forward 开始就存在}
}
\]

只是第一次更新之前：

\[
\boxed{
\rho_t=1
}
\]

第一次参数更新以后：

\[
\boxed{
\rho_t\neq1
}
\]

这时候 PPO 的：

> **限制 current policy 不要偏离 old policy 太远**

这个作用才真正明显体现出来。

---

<a id="origin-11776"></a>
### 133.6 一句话记忆

\[
\boxed{
\text{Rollout 刚结束：current = old，ratio = 1}
}
\]

\[
\boxed{
\text{第一次 optimizer.step 后：current }\neq\text{ old，ratio 开始变化}
}
\]

\[
\boxed{
\text{同一批 Rollout 训练结束：丢掉旧数据，current 变成下一轮 old}
}
\]

所以 PPO 的节奏就是：

\[
\boxed{
\text{Rollout}
\rightarrow
\text{old 固定}
\rightarrow
\text{current 不断更新}
\rightarrow
\text{ratio 不断变化}
\rightarrow
\text{训练结束}
\rightarrow
\text{current 变成新的 old}
}
\]

---

<a id="origin-11816"></a>
## 134. 最终知识总图

```text
强化学习最基础
State / Action / Reward
        │
        ↓
Policy π(a|s)
        │
        ↓
Trajectory
        │
        ↓
Return G
        │
        ├───────────────┐
        │               │
        ↓               ↓
Value V               Q(s,a)
        │               │
        └───────┬───────┘
                ↓
          Advantage A
                │
                ↓
        Policy Gradient
                │
                ↓
为什么出现 log
Log-Derivative Trick
                │
                ↓
         Actor-Critic
                │
                ↓
             TD Error
                │
                ↓
               GAE
                │
                ↓
        Advantage Estimate
                │
                ↓
        Old Policy Rollout
                │
                ↓
      Importance Sampling
                │
                ↓
        π_new / π_old
                │
                ↓
            PPO Clip
                │
                ↓
     更新 Actor + Critic
                │
                ↓
         重新 Rollout
```

大模型版本：

```text
人类偏好
chosen / rejected
        │
        ↓
  Reward Model
        │
        ↓
Prompt
        │
        ↓
LLM Policy Rollout
        │
        ↓
Token trajectory
        │
        ├────────────→ Reward Model Score
        │
        ├────────────→ Reference Model KL
        │
        ↓
      Critic V
        │
        ↓
       TD
        │
        ↓
       GAE
        │
        ↓
   Advantage
        │
        ↓
π_new / π_old
        │
        ↓
    PPO Clip
        │
        ↓
更新 Policy / Critic
```
