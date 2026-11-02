---
title: "44 · PPO 算法详解"
description: "minimind · 强化学习与 PPO 原理 · 课程讲义"
project: "minimind"
sourcePath: "MiniMind/讲义/PPO算法详细讲义.md"
originalUrl: "/resources/minimind/%E8%AE%B2%E4%B9%89/%E5%BC%BA%E5%8C%96%E5%AD%A6%E4%B9%A0%E4%B8%8E%20PPO%20%E5%8E%9F%E7%90%86/se8dc6aaa-PPO%20%E7%AE%97%E6%B3%95%E8%AF%A6%E8%A7%A3.md"
outline: [2, 3]
downloadLabel: "下载整理后 Markdown"
---

# 44 · PPO 算法详解


<a id="origin-3"></a>
## 1. PPO 核心概念

PPO，全称：

> **Proximal Policy Optimization，近端策略优化**

它是强化学习中非常重要的一类 **Policy Gradient（策略梯度）算法**。

PPO 的核心思想其实可以浓缩成一句话：

> **如果一个动作比预期好，就提高以后选择它的概率；如果一个动作比预期差，就降低选择它的概率。**
>
> **但是每次不要改得太猛。**

前半句话是 Policy Gradient。

后半句话就是 PPO 最重要的贡献。

整个 PPO 可以按照下面的故事线理解：

```text
强化学习
    ↓
策略 πθ(a|s)
    ↓
希望最大化累计奖励
    ↓
Policy Gradient
    ↓
好的动作提高概率，坏的动作降低概率
    ↓
问题：一次更新太大可能把策略搞崩
    ↓
需要限制新旧策略变化幅度
    ↓
Importance Sampling
    ↓
概率比值 r_t(θ)
    ↓
Clip 截断
    ↓
PPO
```

---

<a id="origin-49"></a>
## 2. 从最简单的强化学习开始

先不要考虑 PPO。

假设有一个机器人。

机器人面对一个状态：

```text
前方有一个路口
```

它有三个动作：

```text
a1 = 向左
a2 = 向右
a3 = 直走
```

机器人并不是固定选择某个动作，而是维护一个概率：

```text
向左：20%
向右：50%
直走：30%
```

写成数学形式：

$$
\pi(a|s)
$$

这里：

- $s$：state，状态
- $a$：action，动作
- $\pi$：policy，策略

例如：

$$
\pi(\text{右}|s)=0.5
$$

意思就是：

> 在状态 $s$ 下，选择“向右”的概率是 50%。

---

<a id="origin-101"></a>
## 3. 神经网络策略

真实的强化学习中，我们通常使用神经网络产生这些概率。

例如输入：

$$
s
$$

经过神经网络：

$$
f_\theta(s)
$$

得到 logits：

$$
[1.2,\ 2.0,\ 0.7]
$$

经过 Softmax：

$$
\pi_\theta(a|s)
=
\text{Softmax}(f_\theta(s))
$$

可能得到：

$$
[0.25,\ 0.56,\ 0.19]
$$

也就是说：

```text
左：0.25
右：0.56
直走：0.19
```

这里的：

$$
\theta
$$

就是整个神经网络中的参数。

所以：

$$
\pi_\theta(a|s)
$$

实际上表示：

> **参数为 $\theta$ 的神经网络，在状态 $s$ 下选择动作 $a$ 的概率。**

---

<a id="origin-165"></a>
## 4. 强化学习真正想优化什么？

假设机器人：

```text
向右
↓
找到出口
↓
奖励 +10
```

那么很自然：

> 下一次再碰到类似状态，应该提高“向右”的概率。

如果：

```text
向左
↓
撞墙
↓
奖励 -5
```

那么：

> 下一次应该降低“向左”的概率。

所以强化学习最终希望最大化：

$$
J(\theta)
=
\mathbb E_{\tau\sim \pi_\theta}
[R(\tau)]
$$

其中：

$$
\tau
=
(s_0,a_0,s_1,a_1,\cdots)
$$

代表一条完整轨迹。

而：

$$
R(\tau)
$$

代表这一整条轨迹获得的累计奖励。

因此：

$$
J(\theta)
$$

可以简单理解成：

> **当前策略平均能够获得多少奖励。**

我们的目标就是：

$$
\max_\theta J(\theta)
$$

---

<a id="origin-240"></a>
## 5. Return：未来总奖励

假设机器人经历：

```text
t=0    奖励 1
t=1    奖励 2
t=2    奖励 10
```

最简单情况下：

$$
G_0
=
1+2+10
=
13
$$

但是强化学习通常认为：

> 越遥远的奖励越不确定，因此价值应该适当打折。

所以引入：

$$
\gamma
$$

称为：

> discount factor，折扣因子。

例如：

$$
\gamma=0.9
$$

那么：

$$
G_t
=
r_t
+
\gamma r_{t+1}
+
\gamma^2r_{t+2}
+\cdots
$$

例如：

$$
G_0
=
1+0.9\times2+0.9^2\times10
$$

得到：

$$
G_0
=
1+1.8+8.1
=
10.9
$$

因此：

$$
G_t
=
\sum_{k=0}^{\infty}
\gamma^k r_{t+k}
$$

---

<a id="origin-322"></a>
## 6. 最核心的问题：怎么训练 Policy？

假设现在：

$$
\pi_\theta(\text{右}|s)=0.5
$$

机器人选择了“右”。

最后发现：

```text
这个动作很好
Reward = +10
```

我们希望：

$$
0.5
\rightarrow
0.55
\rightarrow
0.60
$$

也就是：

> 提高这个动作未来被选择的概率。

反过来，如果：

```text
Reward = -10
```

希望：

$$
0.5
\rightarrow
0.45
\rightarrow
0.40
$$

所以最原始的想法就是：

$$
\text{好的动作}
\Rightarrow
\pi_\theta(a|s)\uparrow
$$

$$
\text{坏的动作}
\Rightarrow
\pi_\theta(a|s)\downarrow
$$

这就是 Policy Gradient 的核心。

---

<a id="origin-387"></a>
## 7. 为什么出现 $\log \pi_\theta(a|s)$？

？？？公式怎么来的

Policy Gradient 中有一个非常著名的公式：

$$
\nabla_\theta J(\theta)
=
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
G_t
\right]
$$

一个常见问题是：

> 为什么突然出现一个 log？

关键来自：

$$
\nabla_\theta p_\theta
=
p_\theta
\nabla_\theta\log p_\theta
$$

因为：

$$
\nabla_\theta \log p_\theta
=
\frac{1}{p_\theta}
\nabla_\theta p_\theta
$$

所以：

$$
p_\theta
\nabla_\theta\log p_\theta
=
\nabla_\theta p_\theta
$$

这叫：

> **log derivative trick**

也叫：

> likelihood ratio trick。

---

<a id="origin-445"></a>
## 8. Policy Gradient 到底在干什么？

公式：

$$
\nabla_\theta J(\theta)
=
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
G_t
\right]
$$

可以拆成两部分：

$$
\nabla_\theta
\log\pi_\theta(a_t|s_t)
$$

表示：

> 怎么修改神经网络参数，才能改变这个动作的概率。

而：

$$
G_t
$$

决定：

> 到底应该提高还是降低它。

如果：

$$
G_t>0
$$

那么梯度方向：

```text
提高这个动作概率
```

如果：

$$
G_t<0
$$

则：

```text
降低这个动作概率
```

---

<a id="origin-507"></a>
## 9. Reward 高就一定代表动作好吗？

不一定。

例如有两个状态。

状态 A：

```text
正常情况下平均只能拿 1 分
```

结果这次：

```text
拿了 5 分
```

实际上已经非常优秀。

但是状态 B：

```text
正常情况下平均能拿 100 分
```

结果这次：

```text
拿了 5 分
```

实际上非常差。

所以仅仅看：

$$
G_t
$$

是不合理的。

我们真正关心的是：

> **这个结果比原本预期好多少？**

于是出现：

<a id="origin-555"></a>
## 10. Advantage

---

<a id="origin-559"></a>
## 11. Value Function

定义：

$$
V^\pi(s)
$$

意思：

> 从状态 $s$ 开始，按照当前策略继续行动，未来平均可以得到多少奖励。

例如：

```text
当前状态平均能得到 100 分
```

那么：

$$
V(s)=100
$$

如果真实最终得到了：

$$
G_t=120
$$

那么：

```text
实际：120
预期：100
```

这个动作比预期好：

$$
120-100=20
$$

于是定义：

$$
A_t
=
G_t-V(s_t)
$$

这就是：

> **Advantage，优势函数。**

---

<a id="origin-616"></a>
## 12. Advantage 的直觉

$$
A_t>0
$$

表示：

> 这个动作比预期好。

所以：

$$
\pi(a_t|s_t)\uparrow
$$

如果：

$$
A_t<0
$$

表示：

> 这个动作比预期差。

所以：

$$
\pi(a_t|s_t)\downarrow
$$

如果：

$$
A_t\approx0
$$

说明：

> 跟正常水平差不多。

于是没有必要大幅更新。

---

<a id="origin-662"></a>
## 13. Actor-Critic

这里自然产生两个网络。

<a id="origin-666"></a>
### 13.1 Actor

Actor 负责：

> 我应该做什么动作？

输出：

$$
\pi_\theta(a|s)
$$

例如：

```text
左  0.2
右  0.6
前  0.2
```

<a id="origin-686"></a>
### 13.2 Critic

Critic 负责：

> 当前这个状态大概值多少分？

输出：

$$
V_\phi(s)
$$

例如：

$$
V_\phi(s)=8.7
$$

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

<a id="origin-720"></a>
## 14. 从 Policy Gradient 到 Advantage Policy Gradient

现在 Policy Gradient 变成：

$$
\nabla_\theta J(\theta)
=
\mathbb E
\left[
\nabla_\theta
\log\pi_\theta(a_t|s_t)
A_t
\right]
$$

这条公式非常重要。

简单记忆：

$$
\boxed{
\nabla \log\pi
\times
A
}
$$

意思就是：

> 根据 Advantage 的正负，调整当前动作概率。

---

<a id="origin-753"></a>
## 15. 到这里其实还不是 PPO

现在我们的算法大概是：

```text
1. 用 Policy 与环境交互
2. 得到：
   s_t
   a_t
   r_t
3. 计算 Advantage
4. A > 0
   提高动作概率
5. A < 0
   降低动作概率
```

问题来了。

假设：

$$
\pi_{\text{old}}(a|s)=0.2
$$

这个动作很好。

一次梯度更新后变成：

$$
0.9
$$

理论上概率提高了。

但是：

```text
0.2 → 0.9
```

变化实在太大。

可能直接把原来的策略破坏掉。

---

<a id="origin-800"></a>
## 16. Policy Gradient 最大的问题：步子迈得太大

假设原策略：

```text
左：0.30
中：0.40
右：0.30
```

经过一次巨大的梯度更新：

```text
左：0.02
中：0.96
右：0.02
```

也许“中”这一次恰好表现不错。

但不代表永远都应该选中。

这样的剧烈改变可能导致策略突然崩溃。

所以我们希望：

> 新 Policy 和旧 Policy 之间不要差得太远。

这就是 PPO 中：

> **Proximal（近似）**

这个词的来源。

---

<a id="origin-836"></a>
## 17. PPO 最核心的思想

假设旧策略是：

$$
\pi_{\theta_{\text{old}}}
$$

更新后的策略是：

$$
\pi_\theta
$$

我们希望：

```text
新策略比旧策略好
```

但同时：

```text
新策略不能离旧策略太远
```

因此 PPO：

> **不是不允许策略变化，而是不允许一次变化得太多。**

---

<a id="origin-868"></a>
## 18. Importance Sampling：重要性采样

我们有一批数据：

$$
(s_t,a_t,r_t)
$$

这些数据其实来自：

$$
\pi_{\theta_{\text{old}}}
$$

也就是说：

> 是旧 Policy 采样出来的。

但是现在我们正在训练：

$$
\pi_\theta
$$

问题出现了：

> 数据是旧策略产生的，却想拿来训练新策略。

怎么办？

引入：

$$
r_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\theta_{\text{old}}}(a_t|s_t)
}
$$

注意：

PPO 论文里一般把这个比例写成：

$$
r_t(\theta)
$$

这里的 $r$ **不是 reward**。

而是：

> probability ratio，概率比值。

---

<a id="origin-926"></a>
## 19. Probability Ratio 到底是什么意思？

假设旧策略：

$$
\pi_{\text{old}}(a|s)=0.4
$$

新策略：

$$
\pi_\theta(a|s)=0.48
$$

那么：

$$
r_t
=
\frac{0.48}{0.4}
=
1.2
$$

说明：

> 新策略选择这个动作的概率，是旧策略的 1.2 倍。

如果：

$$
r_t=1
$$

说明新旧策略在这个动作上的概率没变。

如果：

$$
r_t>1
$$

说明动作概率提高了。

如果：

$$
r_t<1
$$

说明动作概率降低了。

---

<a id="origin-980"></a>
## 20. PPO 的第一个目标函数

有了：

$$
r_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
$$

最直接的 Policy Objective 就变成：

$$
L(\theta)
=
\mathbb E_t
[
r_t(\theta)A_t
]
$$

如果：

$$
A_t>0
$$

说明动作很好。

那么希望：

$$
r_t>1
$$

即：

$$
\pi_\theta(a|s)
>
\pi_{\text{old}}(a|s)
$$

提高它的概率。

如果：

$$
A_t<0
$$

说明动作不好。

那么希望：

$$
r_t<1
$$

降低它的概率。

但它还是可能改得太猛。

---

<a id="origin-1049"></a>
## 21. PPO 最关键的公式：Clip

PPO 提出了：

$$
\boxed{
L^{CLIP}(\theta)
=
\mathbb E_t
[
\min(
r_t(\theta)A_t,
\operatorname{clip}
(
r_t(\theta),
1-\epsilon,
1+\epsilon
)
A_t
)
]
}
$$

这基本就是 PPO 最重要的一条公式。

---

<a id="origin-1077"></a>
## 22. 什么是 clip？

例如：

$$
\epsilon=0.2
$$

那么：

$$
1-\epsilon=0.8
$$

$$
1+\epsilon=1.2
$$

所以：

$$
\operatorname{clip}(r_t,0.8,1.2)
$$

意思是：

```text
r < 0.8
→ 强制变成 0.8

0.8 ≤ r ≤ 1.2
→ 保持不变

r > 1.2
→ 强制变成 1.2
```

例如：

$$
r=1.1
$$

则：

$$
clip(1.1)=1.1
$$

但是：

$$
r=1.8
$$

则：

$$
clip(1.8)=1.2
$$

---

<a id="origin-1140"></a>
## 23. 为什么 Clip 可以限制更新？

考虑一个好动作：

$$
A_t=2
$$

旧策略：

$$
\pi_{\text{old}}=0.4
$$

假设新策略：

$$
\pi_\theta=0.44
$$

那么：

$$
r_t
=
\frac{0.44}{0.4}
=
1.1
$$

没有超过：

$$
1.2
$$

所以：

$$
r_tA_t
=
1.1\times2
=
2.2
$$

正常奖励模型。

---

<a id="origin-1190"></a>
## 24. 如果改得太猛呢？

旧策略：

$$
0.4
$$

新策略突然变成：

$$
0.6
$$

那么：

$$
r_t
=
\frac{0.6}{0.4}
=
1.5
$$

但是 PPO 设置：

$$
\epsilon=0.2
$$

于是：

$$
clip(1.5,0.8,1.2)=1.2
$$

因此：

$$
r_tA_t
=
1.5\times2
=
3
$$

而：

$$
clip(r_t)A_t
=
1.2\times2
=
2.4
$$

最终：

$$
\min(3,2.4)
=
2.4
$$

也就是说：

> 从 PPO Objective 的角度继续把概率从 1.2 倍提高到 1.5 倍，已经不会获得额外收益。

因此继续疯狂提高动作概率失去了动力。

---

<a id="origin-1262"></a>
## 25. 为什么有一个 min？

考虑：

$$
A_t>0
$$

这是一个好动作。

我们希望提高概率，但最多鼓励到：

$$
1+\epsilon
$$

所以：

$$
r_t>1.2
$$

以后，使用：

$$
1.2A_t
$$

而不是：

$$
r_tA_t
$$

所以取：

$$
\min
$$

---

<a id="origin-1304"></a>
## 26. 再看一个坏动作

假设：

$$
A_t=-2
$$

说明这个动作不好。

旧概率：

$$
0.4
$$

新概率：

$$
0.28
$$

那么：

$$
r_t
=
\frac{0.28}{0.4}
=
0.7
$$

计算：

$$
r_tA_t
=
0.7\times(-2)
=
-1.4
$$

clip：

$$
clip(0.7)=0.8
$$

所以：

$$
0.8\times(-2)
=
-1.6
$$

最终：

$$
\min(-1.4,-1.6)
=
-1.6
$$

因此：

> PPO 不会因为你继续疯狂降低这个动作概率而得到更多好处。

---

<a id="origin-1374"></a>
## 27. PPO Clip 的完整直觉

<a id="origin-1376"></a>
### 27.1 情况一

$$
A_t>0（要采取的新动作是好的）,\quad r_t<1
$$

$r_t<1$即训练出来的新策略反而让这个新动作被选择的概率降低了。

好动作概率反而降低，PPO 会惩罚。

<a id="origin-1386"></a>
### 27.2 情况二

$$
A_t>0,\quad r_t>1
$$

好动作概率提高，PPO 会奖励。

但：

$$
r_t>1+\epsilon
$$

以后不再给予额外奖励。

<a id="origin-1402"></a>
### 27.3 情况三

$$
A_t<0,\quad r_t>1
$$

坏动作概率反而提高，PPO 会惩罚。

<a id="origin-1410"></a>
### 27.4 情况四

$$
A_t<0,\quad r_t<1
$$

坏动作概率下降，PPO 会鼓励。

但：

$$
r_t<1-\epsilon
$$

以后不再给予额外奖励。

所以 PPO 本质上是在说：

```text
好动作：
概率可以提高
但别提高太多

坏动作：
概率可以降低
但别降低太多
```

---

<a id="origin-1440"></a>
## 28. PPO 并不是把概率直接限制在 ±20%

假设：

$$
\epsilon=0.2
$$

很多人会说：

> PPO 强制 Policy 每次最多变化 20%。

严格来说不准确。

PPO Clip 限制的是：

$$
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
$$

在目标函数中的收益。

它并不是直接执行：

```python
new_probability = clip(new_probability)
```

而是：

> 当 probability ratio 超过范围以后，目标函数不再鼓励继续朝这个方向变化。

因此它是一种：

> **soft constraint**

而不是绝对硬约束。

---

<a id="origin-1484"></a>
## 29. 为什么 PPO 可以重复使用一批数据？

假设我们采集了一批数据：

```text
10000 个 state-action
```

全部来自：

$$
\pi_{\text{old}}
$$

然后：

```text
Epoch 1
更新一次 Policy
```

Policy 已经变化了。

如果继续训练：

```text
Epoch 2
Epoch 3
Epoch 4
```

这批数据越来越不像当前 Policy 产生的。

于是使用：

$$
r_t
=
\frac{
\pi_\theta
}{
\pi_{\text{old}}
}
$$

来修正。

同时 Clip 防止当前策略离采样策略越来越远。

因此一批 rollout 数据可以进行：

```text
多轮 minibatch SGD
```

---

<a id="origin-1541"></a>
## 30. 为什么通常保存 log probability？

代码里一般不会直接保存：

$$
\pi(a|s)
$$

而是：

$$
\log\pi(a|s)
$$

假设：

```python
old_log_prob
new_log_prob
```

那么：

$$
\log r_t
=
\log\pi_\theta(a_t|s_t)
-
\log\pi_{\text{old}}(a_t|s_t)
$$

因此：

$$
r_t
=
\exp(
\log\pi_\theta
-
\log\pi_{\text{old}}
)
$$

代码里经常是：

```python
ratio = torch.exp(new_log_prob - old_log_prob)
```

也就是：

$$
\boxed{
r_t
=
e^{
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
}
}
$$

因为：

$$
e^{\log a-\log b}
=
\frac ab
$$

---

<a id="origin-1614"></a>
## 31. PPO 还有一个重要问题：Advantage 怎么算？

最简单可以：

$$
A_t
=
G_t-V(s_t)
$$

但这个估计方差比较大。

PPO 通常使用：

> **GAE**

全称：

> Generalized Advantage Estimation

---

<a id="origin-1636"></a>
## 32. 先理解 TD Error

定义：

$$
\delta_t
=
r_t
+
\gamma V(s_{t+1})
-
V(s_t)
$$

这里注意：

这个 $r_t$ 是 **reward**。

不要和 PPO 的 probability ratio 混淆。

为了避免混乱，可以把 probability ratio 写成：

$$
\rho_t
$$

不过 PPO 原论文里通常还是写：

$$
r_t(\theta)
$$

假设：

$$
V(s_t)=10
$$

执行动作以后：

$$
r_t=2
$$

并到达：

$$
V(s_{t+1})=11
$$

假设：

$$
\gamma=0.9
$$

那么：

$$
\delta_t
=
2
+
0.9\times11
-
10
$$

得到：

$$
\delta_t=1.9
$$

意思是：

```text
实际表现比预期高 1.9
```

因此：

$$
\delta_t>0
$$

说明：

> 这个动作看起来比预期好。

---

<a id="origin-1728"></a>
## 33. GAE 的公式

GAE 定义：

$$
A_t^{GAE}
=
\delta_t
+
\gamma\lambda\delta_{t+1}
+
(\gamma\lambda)^2\delta_{t+2}
+\cdots
$$

即：

$$
\boxed{
A_t^{GAE}
=
\sum_{l=0}^{\infty}
(\gamma\lambda)^l
\delta_{t+l}
}
$$

其中：

$$
\lambda\in[0,1]
$$

---

<a id="origin-1763"></a>
## 34. GAE 为什么需要 $\lambda$？

因为 Advantage estimation 有一个经典矛盾：

> Bias 和 Variance。

如果只看一步：

$$
A_t\approx\delta_t
$$

优点：方差小。

缺点：依赖 Critic，偏差可能比较大。

如果直接一直算到最后：

$$
A_t
=
G_t-V(s_t)
$$

优点：偏差小。

缺点：方差很大。

所以 GAE 在两者之间折中。

当：

$$
\lambda=0
$$

有：

$$
A_t=\delta_t
$$

只看一步。

当：

$$
\lambda\rightarrow1
$$

会越来越接近 Monte Carlo Return。

因此：

$$
\lambda
$$

就是一个：

> bias-variance tradeoff 参数。

PPO 经常使用：

$$
\gamma=0.99
$$

$$
\lambda=0.95
$$

---

<a id="origin-1837"></a>
## 35. GAE 一个具体例子

假设：

$$
\gamma=0.9
$$

$$
\lambda=0.8
$$

有：

$$
\delta_0=1
$$

$$
\delta_1=2
$$

$$
\delta_2=-1
$$

那么：

$$
A_0
=
1
+
0.9\times0.8\times2
+
(0.9\times0.8)^2\times(-1)
$$

因为：

$$
\gamma\lambda
=
0.72
$$

所以：

$$
A_0
=
1
+
0.72\times2
-
0.72^2
$$

$$
=
1+1.44-0.5184
$$

最终：

$$
A_0
=
1.9216
$$

---

<a id="origin-1910"></a>
## 36. GAE 实际代码为什么倒着算？

GAE 有一个递推形式：

$$
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
$$

因此：

```text
最后一步
↑
倒着往前
```

非常方便。

伪代码：

```python
gae = 0

for t in reversed(range(T)):
    delta = reward[t] + gamma * value[t+1] - value[t]
    gae = delta + gamma * lambda_ * gae
    advantage[t] = gae
```

---

<a id="origin-1945"></a>
## 37. Critic 怎么训练？

Actor 学的是：

$$
\pi_\theta(a|s)
$$

Critic 学的是：

$$
V_\phi(s)
$$

它需要预测：

> 从这个状态开始最终大概能得到多少奖励。

我们有一个目标：

$$
V_t^{target}
$$

通常：

$$
V_t^{target}
=
A_t+V(s_t)
$$

然后使用均方误差：

$$
L^{VF}
=
\frac12
\left(
V_\phi(s_t)
-
V_t^{target}
\right)^2
$$

例如：

```text
真实目标价值 = 10
Critic预测 = 7
```

那么：

$$
L
=
\frac12(7-10)^2
=
4.5
$$

通过反向传播：

```text
Critic慢慢学成：

7 → 8 → 9 → 10
```

---

<a id="origin-2017"></a>
## 38. 为什么还要 Entropy？

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

$$
H(\pi)
=
-
\sum_a
\pi(a|s)
\log\pi(a|s)
$$

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

$$
+c_2H(\pi)
$$

鼓励一定程度的探索。

---

<a id="origin-2078"></a>
## 39. PPO 的完整目标函数

最终 PPO 常见目标：

$$
L(\theta)
=
L^{CLIP}
-
c_1L^{VF}
+
c_2H
$$

这里这个形式是 maximize。

其中：

<a id="origin-2096"></a>
### 39.1 Policy Loss

$$
L^{CLIP}
=
\mathbb E
[
\min(
r_tA_t,
clip(r_t,1-\epsilon,1+\epsilon)A_t
)
]
$$

负责：

> 学会选择更好的动作。

<a id="origin-2114"></a>
### 39.2 Value Loss

$$
L^{VF}
=
\frac12
(V(s_t)-V_t^{target})^2
$$

负责训练 Critic。

<a id="origin-2125"></a>
### 39.3 Entropy

$$
H(\pi)
=
-
\sum_a\pi(a|s)\log\pi(a|s)
$$

负责保持探索。

---

<a id="origin-2138"></a>
## 40. 为什么 PyTorch 代码里的符号经常反过来？

数学上我们希望：

$$
\max L^{CLIP}
$$

但是 PyTorch Optimizer 默认做的是：

$$
\min Loss
$$

因此代码通常：

```python
policy_loss = -torch.min(
    ratio * advantage,
    clipped_ratio * advantage
).mean()
```

注意前面的负号。

是因为：

```text
数学：
maximize objective

代码：
minimize loss
```

所以：

$$
L_{policy}
=
-
L^{CLIP}
$$

完整代码经常写：

$$
Loss
=
L_{policy}
+
c_1L_{value}
-
c_2H
$$

即：

$$
\boxed{
Loss
=
-
L^{CLIP}
+
c_1L^{VF}
-
c_2H
}
$$

---

<a id="origin-2211"></a>
## 41. PPO 从头到尾到底执行什么？

<a id="origin-2213"></a>
### 41.1 第一步：初始化 Actor 和 Critic

Actor：

$$
\pi_\theta(a|s)
$$

Critic：

$$
V_\phi(s)
$$

<a id="origin-2227"></a>
### 41.2 第二步：使用当前 Policy 与环境交互

例如：

```text
s0
↓
a0
↓
r0
↓
s1
↓
a1
↓
r1
↓
s2
...
```

保存：

```text
state
action
reward
done
old_log_prob
value
```

<a id="origin-2259"></a>
### 41.3 第三步：固定旧 Policy

此时采样策略记作：

$$
\pi_{\theta_{old}}
$$

后面训练过程中：

$$
\theta
$$

会不断更新。

但：

$$
\theta_{old}
$$

对应的是产生这批数据时的策略。

<a id="origin-2283"></a>
### 41.4 第四步：计算 TD Error

$$
\delta_t
=
r_t
+
\gamma V(s_{t+1})
-
V(s_t)
$$

<a id="origin-2295"></a>
### 41.5 第五步：计算 GAE

$$
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
$$

倒着计算。

<a id="origin-2307"></a>
### 41.6 第六步：得到 Value Target

$$
R_t
=
A_t+V(s_t)
$$

<a id="origin-2315"></a>
### 41.7 第七步：重新计算当前 Policy

得到：

$$
\pi_\theta(a_t|s_t)
$$

或者：

$$
\log\pi_\theta(a_t|s_t)
$$

<a id="origin-2329"></a>
### 41.8 第八步：计算 Ratio

$$
r_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\theta_{old}}(a_t|s_t)
}
$$

代码：

```python
ratio = torch.exp(
    new_log_prob - old_log_prob
)
```

<a id="origin-2349"></a>
### 41.9 第九步：PPO Clip

$$
surr_1
=
r_tA_t
$$

$$
surr_2
=
clip(r_t,1-\epsilon,1+\epsilon)A_t
$$

然后：

$$
L_{policy}
=
-
\min(surr_1,surr_2)
$$

<a id="origin-2372"></a>
### 41.10 第十步：Value Loss

$$
L_{value}
=
\frac12
(V_\phi(s_t)-R_t)^2
$$

<a id="origin-2381"></a>
### 41.11 第十一步：Entropy

计算：

$$
H(\pi)
$$

<a id="origin-2389"></a>
### 41.12 第十二步：总 Loss

$$
Loss
=
L_{policy}
+
c_1L_{value}
-
c_2H
$$

<a id="origin-2401"></a>
### 41.13 第十三步：反向传播

```python
optimizer.zero_grad()
loss.backward()
optimizer.step()
```

<a id="origin-2409"></a>
### 41.14 第十四步：重复多个 Epoch

例如：

```text
同一批 rollout 数据

Epoch 1
Epoch 2
Epoch 3
Epoch 4
```

每个 Epoch：

```text
shuffle
↓
划分 minibatch
↓
更新网络
```

<a id="origin-2432"></a>
### 41.15 第十五步：重新采样

旧数据用完以后：

```text
当前 Policy
↓
重新和环境交互
↓
生成新的 rollout
↓
再次训练
```

于是形成循环。

---

<a id="origin-2450"></a>
## 42. PPO 完整流程图

```text
                Environment
                     │
                     │ state s_t
                     ↓
              ┌─────────────┐
              │    Actor    │
              │   πθ(a|s)   │
              └─────────────┘
                     │
                     │ sample action
                     ↓
                    a_t
                     │
                     ↓
                Environment
                     │
             reward r_t
                     │
                     ↓
             next state s_{t+1}


同时：

s_t
 │
 ↓
┌─────────────┐
│   Critic    │
│    V(s)     │
└─────────────┘
 │
 ↓
Value


收集：

(s_t, a_t, r_t, V_t, old_log_prob)
          │
          ↓
      计算 GAE
          │
          ↓
      Advantage
          │
          ↓
计算：

ratio = π_new / π_old
          │
          ↓
 PPO Clip Objective
          │
          ├────────→ Policy Loss
          │
          ├────────→ Value Loss
          └────────→ Entropy
                        │
                        ↓
                    Total Loss
                        │
                        ↓
                 Backpropagation
                        │
                        ↓
                  更新 Actor/Critic
```

---

<a id="origin-2524"></a>
## 43. 一个完整的数字案例

假设某一步：

旧策略认为：

$$
\pi_{old}(a_t|s_t)=0.4
$$

Critic：

$$
V(s_t)=5
$$

执行动作以后：

$$
r_t=2
$$

下一个状态：

$$
V(s_{t+1})=5
$$

取：

$$
\gamma=0.9
$$

那么：

$$
\delta_t
=
2+0.9\times5-5
$$

$$
=1.5
$$

先假设：

$$
A_t=1.5
$$

说明这个动作比预期好。

训练以后，新策略：

$$
\pi_\theta(a_t|s_t)=0.5
$$

于是：

$$
ratio
=
\frac{0.5}{0.4}
=
1.25
$$

取：

$$
\epsilon=0.2
$$

允许范围：

$$
[0.8,1.2]
$$

所以：

$$
clip(1.25)=1.2
$$

计算：

$$
surr_1
=
1.25\times1.5
=
1.875
$$

$$
surr_2
=
1.2\times1.5
=
1.8
$$

PPO：

$$
\min(1.875,1.8)=1.8
$$

因此：

> 虽然继续提高这个动作概率是正确方向，但 PPO 已经开始限制更新幅度。

---

<a id="origin-2642"></a>
## 44. 为什么叫 Proximal Policy Optimization？

<a id="origin-2644"></a>
### 44.1 Policy

因为优化的是：

$$
\pi_\theta(a|s)
$$

即 Policy。

<a id="origin-2654"></a>
### 44.2 Optimization

因为我们通过：

```text
Gradient Descent / Adam
```

优化神经网络参数。

<a id="origin-2664"></a>
### 44.3 Proximal

最关键。

意味着：

> 新策略最好保持在旧策略附近。

也就是：

$$
\pi_{new}
\approx
\pi_{old}
$$

但又要比旧策略稍微好一点。

因此：

> **Proximal Policy Optimization = 在旧策略附近逐步改进策略。**

---

<a id="origin-2688"></a>
## 45. PPO 和普通梯度下降最大的区别

普通监督学习：

```text
数据固定
↓
模型预测
↓
和 Label 比较
↓
计算 Loss
↓
更新
```

数据分布本身一般不会因为网络参数更新而立即改变。

但强化学习不是。

Policy 一变：

$$
\pi_\theta
$$

它选择的动作就会变化。

动作变化：

```text
访问到的 state 会变
```

state 变化：

```text
后面的 reward 也会变
```

于是：

$$
\theta
$$

不仅决定预测结果，还决定未来训练数据本身。

因此强化学习中的模型更新必须更加谨慎。

---

<a id="origin-2740"></a>
## 46. PPO 和 TRPO 的关系

PPO 之前一个很重要的算法叫：

> TRPO  
> Trust Region Policy Optimization

TRPO 的核心也是：

> 不要让新旧策略差得太远。

它通过：

$$
D_{KL}
(
\pi_{old}
\|
\pi_{new}
)
\leq
\delta
$$

限制新旧策略。

其中：

$$
D_{KL}
$$

是 KL Divergence。

TRPO 的问题是：

```text
数学推导复杂
二阶优化复杂
工程实现麻烦
```

PPO 的目标之一就是：

> 用一个简单得多的方法实现类似效果。

因此使用：

$$
clip
$$

代替复杂的 Trust Region Optimization。

---

<a id="origin-2796"></a>
## 47. PPO 与 KL Divergence

虽然 PPO-Clip 不直接要求：

$$
KL<\delta
$$

但实际实现中经常还会监控：

$$
D_{KL}(
\pi_{old}
\|
\pi_{new}
)
$$

例如：

```text
KL 太大
```

说明 Policy 更新过猛。

有些 PPO 实现会设置：

```text
target_kl = 0.01
```

如果 KL 超过一定程度，就提前停止当前 PPO Epoch。

因此：

```text
Clip：
主要约束

KL：
辅助监控
```

---

<a id="origin-2842"></a>
## 48. Advantage 为什么通常要标准化？

代码里经常看到：

```python
advantage = (
    advantage - advantage.mean()
) / (
    advantage.std() + 1e-8
)
```

即：

$$
\hat A
=
\frac{
A-\mu_A
}{
\sigma_A+\epsilon
}
$$

例如原 Advantage：

```text
100
200
-300
400
```

数值非常大，可能导致 Policy Gradient 很大，训练不稳定。

标准化后大概变成：

```text
0.1
0.5
-1.5
0.9
```

这样优化更加稳定。

---

<a id="origin-2890"></a>
## 49. Gradient Clipping

PPO 中还有一个容易和 PPO Clip 混淆的东西：

```python
torch.nn.utils.clip_grad_norm_
```

这是：

> Gradient Clipping。

和 PPO 的：

$$
clip(r_t,1-\epsilon,1+\epsilon)
$$

不是同一回事。

<a id="origin-2910"></a>
### 49.1 PPO Clip

限制：

$$
\frac{
\pi_{new}
}{
\pi_{old}
}
$$

的目标函数收益。

<a id="origin-2924"></a>
#### 49.1.1 Gradient Clip

限制：

$$
\|\nabla_\theta L\|
$$

即梯度大小。

例如：

```python
clip_grad_norm_(
    model.parameters(),
    0.5
)
```

防止梯度爆炸。

---

<a id="origin-2947"></a>
## 50. PPO 中最容易混淆的三个 r

<a id="origin-2949"></a>
### 50.1 Reward

$$
r_t
$$

环境给出的奖励。

<a id="origin-2957"></a>
#### 50.1.1 Return

$$
R_t
=
r_t+\gamma r_{t+1}+\cdots
$$

未来累计奖励。

<a id="origin-2967"></a>
#### 50.1.2 Ratio

$$
r_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{old}(a_t|s_t)
}
$$

PPO 概率比。

这三个千万不要混在一起。

---

<a id="origin-2985"></a>
## 51. PPO 的伪代码

```text
初始化 Policy πθ
初始化 Value Function Vφ

while training:

    # 1. 使用当前 Policy 采集数据

    rollout = []

    for t = 1 ... T:

        获取状态 s_t

        Actor 输出：
            πθ(a | s_t)

        采样动作：
            a_t

        保存：
            old_log_prob_t

        Critic 输出：
            V(s_t)

        环境执行 a_t

        得到：
            reward r_t
            next_state

        保存数据


    # 2. 计算 Advantage

    for t = T-1 ... 0:

        δ_t =
            r_t
            + γ V(s_{t+1})
            - V(s_t)

        A_t =
            δ_t
            + γ λ A_{t+1}


    # 3. 计算 Return

    R_t =
        A_t + V(s_t)


    # 4. 多个 Epoch 优化

    for epoch = 1 ... K:

        shuffle rollout

        for minibatch:

            new_log_prob =
                log πθ(a_t | s_t)

            ratio =
                exp(
                    new_log_prob
                    - old_log_prob
                )

            surr1 =
                ratio * A_t

            surr2 =
                clip(
                    ratio,
                    1-ε,
                    1+ε
                ) * A_t

            policy_loss =
                -mean(
                    min(surr1, surr2)
                )

            value_loss =
                mean(
                    (V(s_t)-R_t)^2
                )

            entropy =
                H(πθ)

            loss =
                policy_loss
                + c1 * value_loss
                - c2 * entropy

            optimizer.zero_grad()

            loss.backward()

            clip_grad_norm()

            optimizer.step()
```

---

<a id="origin-3098"></a>
## 52. 更接近 PyTorch 的 PPO 核心代码

```python
# 当前 Policy 重新计算动作概率
dist = actor(states)

new_log_probs = dist.log_prob(actions)

entropy = dist.entropy().mean()


# ---------------------------------
# 计算 probability ratio
# ---------------------------------

ratio = torch.exp(
    new_log_probs - old_log_probs
)


# ---------------------------------
# PPO Clip
# ---------------------------------

surr1 = ratio * advantages

surr2 = torch.clamp(
    ratio,
    1.0 - clip_eps,
    1.0 + clip_eps
) * advantages


policy_loss = -torch.min(
    surr1,
    surr2
).mean()


# ---------------------------------
# Critic
# ---------------------------------

new_values = critic(states).squeeze(-1)

value_loss = (
    new_values - returns
).pow(2).mean()


# ---------------------------------
# Total Loss
# ---------------------------------

loss = (
    policy_loss
    + value_coef * value_loss
    - entropy_coef * entropy
)


# ---------------------------------
# Backpropagation
# ---------------------------------

optimizer.zero_grad()

loss.backward()

torch.nn.utils.clip_grad_norm_(
    model.parameters(),
    max_grad_norm
)

optimizer.step()
```

真正理解 PPO 以后，这段代码实际上只有一句最重要：

```python
torch.min(
    ratio * advantage,
    clipped_ratio * advantage
)
```

整个 PPO-Clip 的核心基本都在这里。

---

<a id="origin-3188"></a>
## 53. PPO 的常见超参数

一个非常典型的配置可能是：

```text
gamma = 0.99

gae_lambda = 0.95

clip_eps = 0.2

learning_rate = 3e-4

ppo_epochs = 4

minibatch_size = 64

entropy_coef = 0.01

value_coef = 0.5

max_grad_norm = 0.5
```

分别负责：

<a id="origin-3214"></a>
### 53.1 $\gamma$

$$
\gamma=0.99
$$

未来奖励折扣，越大越关注长期利益。

<a id="origin-3222"></a>
#### 53.1.1 $\lambda$

$$
\lambda=0.95
$$

GAE 参数，控制 Bias / Variance Tradeoff。

<a id="origin-3230"></a>
#### 53.1.2 $\epsilon$

$$
\epsilon=0.2
$$

PPO Clip 范围：

$$
[0.8,1.2]
$$

<a id="origin-3242"></a>
#### 53.1.3 Learning Rate

例如：

$$
3\times10^{-4}
$$

控制神经网络梯度下降速度。

<a id="origin-3252"></a>
#### 53.1.4 PPO Epochs

例如：

```text
4
```

表示同一批 rollout 数据重复训练 4 次。

<a id="origin-3262"></a>
#### 53.1.5 Minibatch Size

例如：

```text
64
```

每次取 64 个 transition 更新。

---

<a id="origin-3274"></a>
## 54. On-Policy 是什么意思？

PPO 通常被归类为：

> On-Policy Reinforcement Learning。

所谓 On-Policy，就是：

> 基本使用当前策略附近产生的数据训练当前策略。

虽然 PPO 同一批数据可以重复训练多个 Epoch，但是因为有：

$$
\pi_{old}
$$

以及 Clip 限制：

> Policy 不能离产生数据的策略太远。

因此仍然属于 On-Policy 方法。

---

<a id="origin-3298"></a>
## 55. PPO 最大的优点

PPO 很流行并不是因为它的理论最完美。

而是因为它实现了一个非常好的平衡：

```text
算法简单
+
实现简单
+
训练稳定
+
效果不错
+
适用于连续动作
+
适用于离散动作
```

因此 PPO 长期都是强化学习中很常用的 baseline 算法之一。

---

<a id="origin-3322"></a>
## 56. PPO 的缺点

<a id="origin-3324"></a>
### 56.1 第一：Sample Efficiency 不算高

因为它属于 On-Policy。

旧数据不能像 DQN、SAC 那样长期反复使用。

需要不断重新与环境交互。

<a id="origin-3332"></a>
### 56.2 第二：超参数比较敏感

例如：

$$
learning\ rate
$$

$$
clip\ range
$$

$$
batch\ size
$$

$$
GAE\ \lambda
$$

设置不好依然可能训练不稳定。

<a id="origin-3354"></a>
### 56.3 第三：Clip 并不是真正严格的 Trust Region

PPO 只是让一次更新通常不要太远。

并不能数学上绝对保证：

$$
D_{KL}
$$

一定很小。

---

<a id="origin-3368"></a>
## 57. PPO 为什么适合连续动作？

例如机器人控制：

```text
方向盘角度：0.35

关节力矩：-0.71

速度：2.4
```

这些动作不是左 / 右 / 前，而是连续数字。

Actor 可以输出：

$$
\mu(s)
$$

和：

$$
\sigma(s)
$$

构造 Gaussian：

$$
a
\sim
\mathcal N(
\mu(s),
\sigma^2(s)
)
$$

然后：

$$
\pi_\theta(a|s)
$$

就是 Gaussian Probability Density。

仍然可以计算：

$$
\log\pi_\theta(a|s)
$$

因此 PPO 完全可以直接使用。

---

<a id="origin-3423"></a>
## 58. PPO 和大语言模型 RLHF 的关系

PPO 之所以后来在大模型领域也非常知名，是因为早期很多 RLHF 系统使用 PPO。

例如：

```text
Prompt
↓
LLM
↓
生成 Response
↓
Reward Model 打分
↓
Reward
↓
PPO 更新 LLM
```

这里：

```text
State：
已经生成的 token 序列

Action：
下一个 token

Policy：
LLM

Reward：
Reward Model 输出
```

因此语言模型：

$$
\pi_\theta(
x_t
|
x_{<t}
)
$$

就是 PPO 中的：

$$
\pi_\theta(a_t|s_t)
$$

---

<a id="origin-3477"></a>
## 59. PPO-RLHF 中为什么尤其害怕 Policy 改太多？

因为原来的语言模型已经具备：

```text
语言能力
知识
语法
推理能力
文本生成能力
```

如果强化学习一次修改太大：

```text
Policy 发生剧烈变化
```

可能导致：

```text
Reward 提高了一点

但：

语言能力崩了
重复输出
格式异常
模式坍缩
```

因此 RLHF 中尤其强调：

> 新 Policy 不要离原始模型太远。

除了 PPO 自身的 Clip 外，还经常加入：

$$
KL(
\pi_\theta
\|
\pi_{ref}
)
$$

惩罚。

---

<a id="origin-3526"></a>
## 60. 用一句人话理解 Policy Gradient、Actor-Critic、PPO

<a id="origin-3528"></a>
### 60.1 Policy Gradient

> 哪个动作带来的结果好，就提高它以后出现的概率。

<a id="origin-3532"></a>
#### 60.1.1 Actor-Critic

> Actor 负责做决定，Critic 负责判断这次决定比正常水平好还是坏。

<a id="origin-3536"></a>
#### 60.1.2 PPO

> 根据 Critic 的评价修改 Actor，但每次只能稳稳地改一点，不能一下子把原策略推翻。

---

<a id="origin-3542"></a>
## 61. 最后把 PPO 压缩成五个公式

<a id="origin-3544"></a>
### 61.1 公式一：TD Error

$$
\boxed{
\delta_t
=
r_t
+
\gamma V(s_{t+1})
-
V(s_t)
}
$$

表示：

> 实际情况和原先预期之间的差距。

<a id="origin-3562"></a>
### 61.2 公式二：GAE

$$
\boxed{
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
}
$$

表示：

> 综合未来多个时间步，估计这个动作到底比预期好多少。

<a id="origin-3578"></a>
### 61.3 公式三：Probability Ratio

$$
\boxed{
r_t(\theta)
=
\frac{
\pi_\theta(a_t|s_t)
}{
\pi_{\theta_{old}}(a_t|s_t)
}
}
$$

表示：

> 当前 Policy 相对于采样时 Policy，到底把这个动作概率改了多少。

<a id="origin-3596"></a>
### 61.4 公式四：PPO Clip Objective

$$
\boxed{
L^{CLIP}
=
\mathbb E
[
\min(
r_tA_t,
clip(r_t,1-\epsilon,1+\epsilon)A_t
)
]
}
$$

表示：

> 好动作提高概率，坏动作降低概率，但是不要改得太猛。

<a id="origin-3616"></a>
### 61.5 公式五：最终 Loss

$$
\boxed{
Loss
=
-
L^{CLIP}
+
c_1L^{VF}
-
c_2H
}
$$

其中：

$$
L^{VF}
=
(V-R)^2
$$

负责 Critic。

$$
H
$$

负责探索。

---

<a id="origin-3649"></a>
## 62. 一张图记住整个 PPO

```text
                当前 State
                    │
           ┌────────┴────────┐
           ↓                 ↓
        Actor             Critic
      πθ(a|s)              V(s)
           │                 │
           ↓                 │
       Sample a              │
           │                 │
           ↓                 │
       Environment           │
           │                 │
           ↓                 │
       Reward r              │
           │                 │
           └────────┬────────┘
                    ↓
              TD Error δ
                    │
                    ↓
                   GAE
                    │
                    ↓
               Advantage A
                    │
                    ↓
       ┌─────────────────────────┐
       │                         │
π_old(a|s)                 π_new(a|s)
       │                         │
       └────────────┬────────────┘
                    ↓
             Probability Ratio

           π_new(a|s)
       r = ─────────────
           π_old(a|s)

                    │
                    ↓
              PPO CLIP

     min(
         rA,
         clip(r,1-ε,1+ε)A
     )

                    │
                    ↓
             Policy Loss
                    │
          ┌─────────┼─────────┐
          ↓         ↓         ↓
       Policy     Value     Entropy
        Loss       Loss      Bonus
          │         │         │
          └─────────┼─────────┘
                    ↓
                Total Loss
                    │
                    ↓
            Backpropagation
                    │
                    ↓
               更新 Policy
                    │
                    ↓
              重新采集数据
                    │
                    └──────────────→ 循环
```

---

<a id="origin-3727"></a>
## 63. 最终总结

PPO 看起来公式很多，但真正的逻辑其实非常简单。

第一步：

> 与环境交互，看看自己做了什么。

第二步：

> Critic 判断这次结果比预期好还是坏。

第三步：

如果：

$$
A>0
$$

那么：

> 提高这个动作的概率。

如果：

$$
A<0
$$

那么：

> 降低这个动作的概率。

这就是 Policy Gradient。

但是直接这么做会有一个危险：

> Policy 可能一次变化太大。

所以计算：

$$
\frac{\pi_{new}}{\pi_{old}}
$$

看看：

> 新 Policy 相比旧 Policy 已经改变了多少。

然后通过：

$$
clip(1-\epsilon,1+\epsilon)
$$

限制进一步修改的收益。

因此 PPO 最核心的思想最终可以写成：

$$
\boxed{
\text{朝正确方向修改 Policy，但每次不要修改得太多}
}
$$

或者更加直白地说：

> **好的动作以后多做一点，坏的动作以后少做一点，但任何一次学习都不要矫枉过正。**

这就是 PPO。
