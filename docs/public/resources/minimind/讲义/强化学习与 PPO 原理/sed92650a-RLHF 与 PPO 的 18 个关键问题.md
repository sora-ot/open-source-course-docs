# RLHF 与 PPO 的 18 个关键问题

<a id="origin-2"></a>
## 1. ——从自然语言故事到 Reward Model、Critic、GAE、Importance Sampling 与 PPO-Clip 的完整推导

> 本讲义以“大模型如何使用 PPO 做 RLHF”为主线。
>
> 目标不是只记住 PPO 的一个 Clip 公式，而是彻底理解：Reward Model 怎么训练、Critic 怎么训练、Rollout 为什么有效、Policy Gradient 为什么有 log、Value/Advantage/TD/GAE 是什么、Importance Sampling 为什么会引出 Ratio，以及 PPO-Clip 为什么能限制策略更新。

---

<a id="origin-10"></a>
## 2. 目录

1. 先看全局：大模型 PPO 到底在训练什么
2. 一个完全不写公式的 RLHF-PPO 故事
3. Reward Model 到底怎么训练
4. Rollout 到底是什么
5. Critic / Value Model 到底怎么训练
6. PPO 更新阶段为什么不重新生成序列
7. 强化学习最基础的 State / Action / Reward / Policy
8. Return \(G_t\)、Value \(V\)、Q、Advantage \(A\)
9. PPO 和马尔科夫链 / MDP 的关系
10. Policy Gradient 的目标 \(J(\theta)\)
11. 为什么会有很多条轨迹，而不是只有一条
12. 轨迹概率 \(P_\theta(\tau)\) 中每一项是什么意思
13. Policy Gradient 中的 \(\log\) 到底怎么来的
14. Value 的“平均期望”到底从哪里来
15. TD Error 是什么，公式怎么来的
16. Bias 和 Variance 为什么会此消彼长
17. GAE 是怎么把多个 TD Error 合起来的
18. 为什么 \(V_t^{target}=A_t+V(s_t)\)
19. Importance Sampling 到底在修正什么
20. Importance Sampling 中的 \(f\) 到底是什么
21. 为什么 PPO 使用 Probability Ratio
22. PPO-Clip 的完整推导
23. 为什么坏动作的 \(-1.6\) 能阻止继续激进下降
24. PPO 的完整 Loss
25. Reference Model 和 Old Policy 为什么不是一个东西
26. 大模型 PPO 的完整数学数据流
27. 一个具体的大模型 PPO 数值例子
28. PPO 训练伪代码
29. 18 个问题逐题总结
30. 最终知识地图

---

<a id="origin-45"></a>
## 3. 先看全局：大模型 PPO 到底在训练什么

在经典 RLHF + PPO 中，先把最重要的几个角色分清楚。

```text
1. Policy / Actor
   真正要被强化学习更新的 LLM

2. Reward Model
   给完整回答打“偏好分”

3. Critic / Value Model
   预测当前生成到这里，未来大约还能得到多少 Reward

4. Reference Model
   冻结的参考语言模型，用来防止训练后的模型跑得太远

5. Old Policy
   当前这一轮 Rollout 时的 Policy 快照，用于计算 PPO Ratio
```

一定先记住：

\[
\boxed{\text{Reward Model} \neq \text{Critic}}
\]

\[
\boxed{\pi_{\text{ref}} \neq \pi_{\text{old}}}
\]

\[
\boxed{\text{Ratio} \neq \text{另一个模型}}
\]

\[
\boxed{\text{Advantage} \neq \text{另一个神经网络}}
\]

---

<a id="origin-86"></a>
## 4. 一个完全不写公式的 RLHF-PPO 故事

先不看任何公式。

假设我们已经有一个经过 SFT 的语言模型。

用户输入：

```text
Q：1+1 等于多少？请简单解释。
```

这个模型已经会回答问题，但答案质量可能不同。

例如可能生成：

```text
回答 A：
1+1=2，因为一个物体再加一个物体，一共有两个物体。
```

也可能生成：

```text
回答 B：
答案是 2。
```

甚至有很小概率生成：

```text
回答 C：
1+1=3。
```

我们希望：

> 通过人类偏好，让模型以后更容易生成 A 这种回答，更少生成 C 这种回答。

这就是 RLHF 的一个典型目标。

<a id="origin-127"></a>
### 4.1 第一步：先训练一个“阅卷老师”

我们准备偏好数据：

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

这个数据的含义不是：

```text
good answer 是标准答案，请逐 Token 模仿它
```

而是：

```text
同一个问题下：
good answer 比 bad answer 更好
```

所以我们训练出来的 Reward Model 做的事情是：

```text
Prompt + Response
        ↓
 Reward Model
        ↓
 一个标量分数
```

例如：

```text
Q + good answer → 3.2
Q + bad answer  → 0.7
```

它真正需要学会的是：

```text
3.2 > 0.7
```

而不是一定要学出“满分 10 分中的 8.4 分”。

<a id="origin-182"></a>
### 4.2 第二步：让当前 Policy 真的生成答案

现在进入 PPO。

假设当前 Policy 真的生成：

```text
1+1=2，因为两个1放在一起就是2。
```

注意，大模型不是一次性把这句话吐出来。

实际是：

```text
Prompt
↓
采样 token_1
↓
Prompt + token_1
↓
采样 token_2
↓
Prompt + token_1 + token_2
↓
……
↓
EOS
```

这整条生成过程就是一条 trajectory / 轨迹。

而“真正运行当前 Policy，采出轨迹”的过程，就叫 Rollout。

<a id="origin-216"></a>
### 4.3 第三步：Rollout 时会保存大量信息

例如在某一步：

```text
当前上下文：
"1+1="
```

Policy 输出：

```text
"2" : 0.85
"3" : 0.05
"4" : 0.02
...
```

最终采样到：

```text
"2"
```

那么会保存：

```text
State：
"1+1="

Action：
"2"

old_prob：
0.85

old_log_prob：
log(0.85)
```

下一步继续生成。

所以一条 Rollout 最终会保存类似：

```text
s0, a0, old_log_prob0
s1, a1, old_log_prob1
s2, a2, old_log_prob2
...
```

以及 Reward、Value、done / EOS 等。

<a id="origin-269"></a>
### 4.4 第四步：Reward Model 给整段回答打分

完整 Response 生成后：

```text
Prompt + Response
        ↓
 Reward Model
        ↓
 Reward = 8.7
```

于是我们知道：

> 这整条回答总体表现不错。

但马上有一个问题：

> “8.7 分”到底应该归因给哪一个 Token？

所以还需要 Critic。

<a id="origin-291"></a>
### 4.5 第五步：Critic 预测“现在走到这里，前景怎么样”

例如：

```text
状态：
"1+1="
```

Critic 预测：

```text
V = 7.5
```

意思：

> 按照当前 Policy 从这里继续生成，预计最后大约能得到 7.5 分。

当已经生成：

```text
"1+1=2"
```

Critic 可能预测：

```text
V = 8.2
```

当已经生成：

```text
"1+1=2，因为"
```

Critic 可能预测：

```text
V = 8.4
```

所以 Critic 不是决定下一个 Token。

它是在评价：

> “照现在这个局面继续走下去，最终大概值多少分？”

<a id="origin-340"></a>
### 4.6 第六步：判断某一步“比预期好还是差”

如果：

```text
原本 Critic 觉得：
从 "1+1=" 开始，未来大概 7.5 分
```

结果生成 `"2"` 后，事情发展得比预想还好，那么我们就认为：

```text
"2" 这个 Action 比平均预期更好
```

也就是：

```text
Advantage > 0
```

于是：

> 下次在类似上下文中，提高 `"2"` 的概率。

反过来，如果生成 `"3"` 导致最终 Reward 很差：

```text
Advantage < 0
```

于是：

> 下次降低 `"3"` 的概率。

这就是 Policy Gradient 的核心直觉。

<a id="origin-377"></a>
### 4.7 第七步：为什么还要 PPO，而不是直接猛改

假设旧模型：

```text
P_old("2" | "1+1=") = 0.85
```

我们发现 `"2"` 是好 Action。

如果直接猛更新，可能：

```text
0.85 → 0.999999
```

对于一个 Token 看起来问题不大，但对于一个几十亿参数的大模型，如果大量 Token 概率同时剧烈变化，可能导致：

```text
语言能力下降
回答模式坍缩
重复
过度迎合 Reward Model
```

所以 PPO 说：

> 方向可以改，但别一下子改太远。

<a id="origin-406"></a>
### 4.8 第八步：Rollout 固定下来，再进行 PPO Update

这是理解 PPO 的关键。

Rollout 时真实采到了：

```text
A → B → C → D
```

PPO 更新参数以后，如果重新生成，也许第一步就不再选 A，于是后面的序列当然会全部改变。

但 PPO 在“更新这批数据”的阶段：

> 不重新生成！

而是固定这条旧 trajectory：

```text
s0 → A
s1 → B
s2 → C
s3 → D
```

用新模型重新计算：

```text
P_new(A | s0)
P_new(B | s1)
P_new(C | s2)
P_new(D | s3)
```

再和 Rollout 时保存的旧概率比较。

训练几轮后：

```text
旧 Rollout 不再使用
```

再用最新 Policy 重新 Rollout。

所以 PPO 的基本节奏是：

```text
Rollout
↓
固定数据
↓
训练几个 Epoch
↓
丢掉旧 Rollout
↓
用新 Policy 重新 Rollout
↓
再训练
```

---

<a id="origin-468"></a>
## 5. Reward Model 到底怎么训练

<a id="origin-470"></a>
### 5.1 Reward Model 不是普通 SFT

普通 SFT 的数据是：

```text
Prompt → 标准 Response
```

模型做 Next Token Prediction。

Loss 大致：

\[
L_{\text{SFT}}
=
-\sum_t
\log p(y_t|x,y_{<t})
\]

它是 Token-level 监督。

而 Reward Model 的数据是：

```text
同一个 Prompt：

Chosen Response
Rejected Response
```

只告诉模型：

\[
\text{Chosen} \succ \text{Rejected}
\]

这是 Preference Learning / Pairwise Preference Learning。

<a id="origin-508"></a>
### 5.2 Reward Model 的网络结构

最简单理解：

```text
原本 LLM：
hidden state
↓
LM Head
↓
Vocabulary logits
```

改成：

```text
Reward Model：
hidden state
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

输出一个 Scalar。

<a id="origin-546"></a>
### 5.3 chosen / rejected 怎么变成 Loss

对 chosen：

\[
r_c
=
R_\psi(x,y_c)
\]

对 rejected：

\[
r_r
=
R_\psi(x,y_r)
\]

希望：

\[
r_c>r_r
\]

最经典做法：

\[
P(y_c\succ y_r)
=
\sigma(r_c-r_r)
\]

然后最小化：

\[
\boxed{
L_{\text{RM}}
=
-\log
\sigma(r_c-r_r)
}
\]

<a id="origin-589"></a>
### 5.4 数值例子

一开始：

\[
r_c=0.4,\quad r_r=0.6
\]

模型判断反了。

\[
r_c-r_r=-0.2
\]

Loss 较大。

反向传播会推动：

```text
r_c ↑
r_r ↓
```

例如：

```text
0.4, 0.6
→ 0.8, 0.3
→ 1.6, -0.2
→ 2.5, -0.8
```

<a id="origin-621"></a>
### 5.5 Reward Model 学的是相对偏好

例如：

\[
r_c=5,\quad r_r=2
\]

和：

\[
r_c=105,\quad r_r=102
\]

差都为 3。

从 pairwise preference 的角度，它们提供的排序信息类似。

所以 Reward Model 核心不是学习“绝对满分几分”，而是：

> Chosen 应该比 Rejected 得分高。

---

<a id="origin-645"></a>
## 6. Rollout 到底是什么

\[
\boxed{
\text{Rollout}=
\text{让当前 Policy 真正运行，采集轨迹数据}
}
\]

<a id="origin-654"></a>
### 6.1 普通强化学习中的 Rollout

```text
s0
↓ policy sample a0
a0
↓ environment
r0, s1
↓ policy sample a1
a1
↓ environment
r1, s2
...
```

<a id="origin-669"></a>
### 6.2 大模型中的 Rollout

取一批 Prompt：

```text
Prompt_1
Prompt_2
...
Prompt_N
```

当前 LLM 真正生成：

```text
Response_1
Response_2
...
Response_N
```

每一步 Token 都是一个 Action。

所以：

\[
\boxed{
\text{LLM Rollout 真的会进行自回归采样}
}
\]

<a id="origin-699"></a>
### 6.3 一次 Rollout 和很多轨迹

一次单独生成：

> 一条 trajectory。

一批 Rollout：

> 很多 trajectory。

即使同一个 Prompt，多次采样也可能得到不同 Response。

---

<a id="origin-713"></a>
## 7. Critic / Value Model 到底怎么训练

Critic 需要学习：

\[
V^\pi(s)
\]

含义：

> 在当前 State 下，如果以后继续按照当前 Policy 行动，未来预期能得到多少 Return。

<a id="origin-725"></a>
### 7.1 Critic 一开始并不知道 Value

例如：

```text
State：
"1+1="
```

Critic 初始可能预测：

```text
V = 0.3
```

但最终 Rollout 得到高 Reward，所以它需要学习。

<a id="origin-742"></a>
### 7.2 最简单理解：用真实 Return 当 Target

如果一条轨迹最后 Reward 是 8，最粗略可以理解：

```text
s0 → target ≈ 8
s1 → target ≈ 8
s2 → target ≈ 8
...
```

Critic 当前预测：

```text
3,4,5,6
```

用：

\[
L_V
=
(V_\phi(s_t)-V_t^{target})^2
\]

训练。

<a id="origin-769"></a>
### 7.3 实际 PPO 常用 GAE 构造 Target

先算 TD Error：

\[
\delta_t
=
r_t+\gamma V_{\text{old}}(s_{t+1})
-
V_{\text{old}}(s_t)
\]

再算 GAE：

\[
A_t
=
\delta_t
+
\gamma\lambda\delta_{t+1}
+
(\gamma\lambda)^2\delta_{t+2}
+
\cdots
\]

然后：

\[
\boxed{
V_t^{target}
=
A_t+V_{\text{old}}(s_t)
}
\]

这个 Target 固定下来，作为 Critic 的监督信号。

<a id="origin-807"></a>
### 7.4 Critic 网络结构

常见两种。

<a id="origin-811"></a>
#### 7.4.1 共享 Backbone

```text
Transformer
     │
hidden state h_t
   ┌─┴───────────────┐
   ↓                 ↓
LM Head          Value Head
   ↓                 ↓
Policy logits       V(s_t)
```

Value Head：

\[
V(s_t)=w_V^Th_t+b
\]

<a id="origin-830"></a>
#### 7.4.2 独立 Critic

```text
Actor Transformer → π(a|s)
Critic Transformer → V(s)
```

<a id="origin-837"></a>
### 7.5 Reward Model 和 Critic 的区别

Reward Model：

```text
输入：Prompt + 完整 Response
输出：这整个回答有多符合人类偏好
训练数据：chosen / rejected
```

Critic：

```text
输入：Prompt + 当前已经生成的部分
输出：从这里继续生成，未来预计能拿多少 Reward
训练数据：PPO Rollout 构造的 Value Target
```

可以记：

```text
Reward Model：事后阅卷老师
Critic：写到一半时预测最后大概多少分
```

---

<a id="origin-864"></a>
## 8. PPO 更新阶段为什么不重新生成序列

假设 Rollout：

```text
s0 --A--> s1
s1 --B--> s2
s2 --C--> s3
```

后来更新一次 Policy 后，如果重新生成，第一步也许会选 X，后面当然完全变。

但 PPO 在这一批数据的 Optimization 阶段不会重新 Rollout。

它固定旧数据：

```text
(s0,A)
(s1,B)
(s2,C)
```

新 Policy 只重新计算：

```text
π_new(A|s0)
π_new(B|s1)
π_new(C|s2)
```

因此：

\[
\boxed{
\text{Rollout 阶段：真实自回归采样}
}
\]

\[
\boxed{
\text{PPO Update 阶段：固定旧轨迹，只重算概率}
}
\]

<a id="origin-908"></a>
### 8.1 为什么旧 Rollout 仍有价值

如果：

```text
π_old:
A 90%
X 10%
```

更新后：

```text
π_new:
A 88%
X 12%
```

旧轨迹 A→B→C 对新 Policy 仍然有代表性。

如果突然变成：

```text
A 1%
X 99%
```

旧轨迹就几乎不代表新 Policy。

这也是 PPO 要使用 Ratio 和 Clip 的原因。

---

<a id="origin-941"></a>
## 9. 强化学习最基础的 State / Action / Reward / Policy

<a id="origin-943"></a>
### 9.1 State

\[
s_t
\]

表示时刻 \(t\) 的当前状态。

大模型中：

\[
s_t
=
\text{Prompt + 已经生成的 Token}
\]

<a id="origin-959"></a>
### 9.2 Action

\[
a_t
\]

对于大模型：

\[
\boxed{a_t=\text{下一个 Token}}
\]

<a id="origin-971"></a>
### 9.3 Reward

\[
r_t
\]

表示执行动作后得到的即时奖励。

大模型 RLHF 中：

- 最终可能有 Reward Model Score；
- 每个 Token 还可能有 KL penalty 等 shaped reward。

<a id="origin-984"></a>
### 9.4 Policy

\[
\pi_\theta(a|s)
\]

表示参数为 \(\theta\) 的 Policy，在状态 \(s\) 下选择 Action \(a\) 的概率。

例如：

```text
State:
"1+1="

Policy:
"2": 0.85
"3": 0.05
"4": 0.02
...
```

如果真正采样到 `"2"`：

\[
\pi_\theta(a_t|s_t)=0.85
\]

---

<a id="origin-1013"></a>
## 10. Return、Value、Q、Advantage

<a id="origin-1015"></a>
### 10.1 Return：从现在开始实际累计能拿多少 Reward

\[
\boxed{
G_t
=
r_t+\gamma r_{t+1}+\gamma^2r_{t+2}+\cdots
}
\]

例如：

```text
t=0: r0 = 1
t=1: r1 = 2
t=2: r2 = 10
```

\[
\gamma=0.9
\]

那么：

\[
G_0
=
1+0.9\times2+0.9^2\times10
=10.9
\]

<a id="origin-1046"></a>
### 10.2 \(G_t\) 从哪里来

如果 Rollout 已完整跑到终止：

> 由真实观测到的未来 Reward 往回累计。

如果 Rollout 被截断：

> 未展开部分可用 \(V(s_T)\) Bootstrapping。

例如：

\[
G_{T-1}
\approx
r_{T-1}+\gamma V(s_T)
\]

<a id="origin-1064"></a>
### 10.3 Value：当前状态平均多值钱

\[
\boxed{
V^\pi(s_t)
=
\mathbb E_\pi[G_t|s_t]
}
\]

自然语言：

> 现在处于 \(s_t\)，以后都按当前 Policy 走，平均能得到多少 Return？

<a id="origin-1078"></a>
### 10.4 Value 的“平均期待”从哪里来

理论上，同一个 State 出发很多次：

```text
8
12
9
11
10
```

平均 10，所以：

\[
V^\pi(s)\approx10
\]

真实训练不会对每个状态重复无穷次，因此训练神经网络：

\[
V_\phi(s)
\]

去近似这个期望。

<a id="origin-1104"></a>
### 10.5 Q：先指定某个动作后，平均多值钱

\[
\boxed{
Q^\pi(s_t,a_t)
=
\mathbb E[G_t|s_t,a_t]
}
\]

Value：让 Policy 自己选动作。

Q：第一步先指定 Action，再继续按 Policy 走。

<a id="origin-1118"></a>
### 10.6 Advantage：这个 Action 比平均水平好多少

\[
\boxed{
A^\pi(s,a)
=
Q^\pi(s,a)-V^\pi(s)
}
\]

例如：

\[
V(s)=10
\]

\[
Q(s,\text{右})=14
\]

那么：

\[
A(s,\text{右})=4
\]

所以：

\[
A>0
\Rightarrow
\text{提高该 Action 概率}
\]

\[
A<0
\Rightarrow
\text{降低该 Action 概率}
\]

---

<a id="origin-1160"></a>
## 11. PPO 和马尔科夫链 / MDP 的关系

<a id="origin-1162"></a>
### 11.1 马尔科夫性质

\[
P(s_{t+1}|s_0,\ldots,s_t)
=
P(s_{t+1}|s_t)
\]

表示：

> 如果当前 State 已经包含决策所需信息，那么已知当前 State 后，不必再额外依赖更早完整历史。

<a id="origin-1174"></a>
### 11.2 强化学习更准确是 MDP

因为还有 Action：

\[
P(s_{t+1}|s_t,a_t)
\]

所以使用 Markov Decision Process：

\[
(S,A,P,R,\gamma)
\]

<a id="origin-1188"></a>
### 11.3 固定 Policy 后得到 Policy 诱导的马尔科夫链

\[
P_\pi(s'|s)
=
\sum_a
\pi(a|s)P(s'|s,a)
\]

因此：

\[
\boxed{
\text{MDP + 固定 Policy}
\Rightarrow
\text{Markov Chain}
}
\]

而 PPO 不断修改 Policy。

---

<a id="origin-1211"></a>
## 12. Policy Gradient 的目标 \(J(\theta)\)

希望当前 Policy 平均 Reward 尽量高：

\[
\boxed{
J(\theta)
=
\mathbb E_{\tau\sim\pi_\theta}[R(\tau)]
}
\]

其中：

\[
\tau
=
(s_0,a_0,s_1,a_1,\ldots)
\]

是一条完整 trajectory。

---

<a id="origin-1235"></a>
## 13. 为什么会有很多条轨迹，而不是只有一条

一次真实运行：

> 确实只有一条 trajectory。

但运行前 Policy 有随机性，所以存在很多可能 trajectory。

同一个 Prompt 可能：

```text
轨迹1：1+1=2。
轨迹2：答案是2。
轨迹3：1+1等于二。
轨迹4：1+1=3。
```

理论目标：

\[
J(\theta)
=
\sum_\tau
P_\theta(\tau)R(\tau)
\]

<a id="origin-1261"></a>
### 13.1 三条轨迹的例子

```text
轨迹1：概率 0.7，Reward 10
轨迹2：概率 0.2，Reward 5
轨迹3：概率 0.1，Reward -10
```

\[
J
=
0.7\times10
+
0.2\times5
+
0.1\times(-10)
=7
\]

<a id="origin-1280"></a>
### 13.2 现实不枚举全部轨迹

实际通过 Rollout 采样：

\[
\tau_1,\tau_2,\ldots,\tau_N
\]

用样本平均近似：

\[
J(\theta)
\approx
\frac1N
\sum_{i=1}^{N}
R(\tau_i)
\]

---

<a id="origin-1300"></a>
## 14. 轨迹概率中的每一项

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

<a id="origin-1313"></a>
### 14.1 \(P(s_0)\)

初始状态概率。

大模型里可理解为训练时采到哪个 Prompt。

<a id="origin-1319"></a>
### 14.2 \(\pi_\theta(a_t|s_t)\)

当前 Policy 在 State \(s_t\) 下，为这次实际 Action \(a_t\) 分配的概率。

大模型：

```text
s_t = Prompt + 已生成部分
a_t = 当前真正采样到的 Token
```

<a id="origin-1330"></a>
### 14.3 \(P(s_{t+1}|s_t,a_t)\)

环境转移概率。

机器人环境可能随机。

纯文本大模型里，一旦确定当前序列和新 Token，下一个 State 基本就是拼接后的序列，因此这个转移近似确定。

---

<a id="origin-1340"></a>
## 15. Policy Gradient 中的 \(\log\) 到底怎么来的

从：

\[
J(\theta)
=
\sum_\tau
P_\theta(\tau)R(\tau)
\]

对 \(\theta\) 求导：

\[
\nabla_\theta J
=
\sum_\tau
\nabla_\theta P_\theta(\tau)R(\tau)
\]

使用恒等式：

\[
\nabla_\theta\log P_\theta
=
\frac{\nabla_\theta P_\theta}{P_\theta}
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

代回：

\[
\nabla_\theta J
=
\sum_\tau
P_\theta(\tau)
\nabla_\theta\log P_\theta(\tau)
R(\tau)
\]

即：

\[
\boxed{
\nabla_\theta J
=
\mathbb E_{\tau\sim\pi_\theta}
[
\nabla_\theta\log P_\theta(\tau)R(\tau)
]
}
\]

而：

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
\sum_t\log\pi_\theta(a_t|s_t)
+
\sum_t\log P(s_{t+1}|s_t,a_t)
\]

环境项不含 Policy 参数 \(\theta\)，所以对 \(\theta\) 求导后消失：

\[
\nabla_\theta\log P_\theta(\tau)
=
\sum_t
\nabla_\theta\log\pi_\theta(a_t|s_t)
\]

最终得到：

\[
\boxed{
\nabla_\theta J
=
\mathbb E
\left[
\sum_t
\nabla_\theta\log\pi_\theta(a_t|s_t)
G_t
\right]
}
\]

所以 \(\log\) 不是硬塞进去的，而是来自 Log-Derivative Trick。

---

<a id="origin-1454"></a>
## 16. Value 的“平均期望”到底从哪里来

理论：

\[
V^\pi(s)
=
\mathbb E[G_t|s_t=s]
\]

同一状态反复出发，Return：

```text
8
12
11
9
10
```

平均 10，所以：

\[
V^\pi(s)\approx10
\]

现实不能无穷重复，因此训练：

\[
V_\phi(s)
\]

从大量 Rollout 数据中学习这个条件期望。

---

<a id="origin-1490"></a>
## 17. TD Error 是什么，公式怎么来的

TD：Temporal Difference。

<a id="origin-1494"></a>
### 17.1 自然语言例子

当前状态 A：

```text
V(A)=100
```

走一步：

```text
立即 Reward = 10
进入 B
```

Critic：

```text
V(B)=110
```

若 \(\gamma=1\)：

走一步后的新估计：

\[
10+110=120
\]

旧估计：

\[
100
\]

差：

\[
20
\]

就是 TD Error。

<a id="origin-1537"></a>
### 17.2 公式

\[
\boxed{
\delta_t
=
r_t+\gamma V(s_{t+1})-V(s_t)
}
\]

<a id="origin-1547"></a>
### 17.3 为什么和 Advantage 有关系

\[
Q^\pi(s_t,a_t)
\approx
r_t+\gamma V^\pi(s_{t+1})
\]

而：

\[
A^\pi(s_t,a_t)
=
Q^\pi(s_t,a_t)-V^\pi(s_t)
\]

代入：

\[
A^\pi(s_t,a_t)
\approx
r_t+\gamma V^\pi(s_{t+1})-V^\pi(s_t)
\]

因此：

\[
\boxed{
A_t\approx\delta_t
}
\]

更严谨地说，如果 Value 足够准确：

\[
\mathbb E[\delta_t|s_t,a_t]
=
A^\pi(s_t,a_t)
\]

所以 TD Error 是 Advantage 的一步估计。

---

<a id="origin-1591"></a>
## 18. Bias 和 Variance 为什么会此消彼长

<a id="origin-1593"></a>
### 18.1 Bias

真实值 10。

估计器：

```text
8,8,8,8,8
```

很稳定，但长期系统性低 2。

所以：

```text
Bias 大
Variance 小
```

<a id="origin-1612"></a>
### 18.2 Variance

真实平均 10。

估计器：

```text
0,20,3,17,10
```

平均可能接近 10，但每次波动很大。

所以：

```text
Bias 小
Variance 大
```

<a id="origin-1631"></a>
### 18.3 为什么完整 Monte Carlo Return 方差大

\[
G_t
=
r_t+\gamma r_{t+1}+\cdots
\]

未来每一步都有随机性，全部累积进 Return。

所以 Variance 大。

但它不依赖一个可能错误的 Critic 去猜很远未来，所以 Bias 较低。

<a id="origin-1645"></a>
### 18.4 为什么一步 TD 方差小但可能有 Bias

\[
r_t+\gamma V(s_{t+1})
\]

只真实采样一步。

更远未来被 Critic 的“平均预测”压缩掉，所以随机性小，Variance 小。

但如果 Critic 预测错，就会产生系统性偏差，Bias 变大。

---

<a id="origin-1659"></a>
## 19. GAE 怎么把多个 TD Error 合起来

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
\cdots
}
\]

\[
0\le\lambda\le1
\]

<a id="origin-1679"></a>
### 19.1 \(\lambda=0\)

\[
A_t=\delta_t
\]

更依赖 Critic：

```text
Variance 低
Bias 可能高
```

<a id="origin-1692"></a>
### 19.2 \(\lambda\to1\)

考虑更长未来：

```text
更接近完整 Return
Bias 降低
Variance 增大
```

常见：

\[
\lambda=0.95
\]

<a id="origin-1708"></a>
### 19.3 数值例子

\[
\gamma=0.9,\quad\lambda=0.8
\]

\[
\delta_0=1,\quad\delta_1=2,\quad\delta_2=-1
\]

\[
\gamma\lambda=0.72
\]

\[
A_0
=
1+0.72\times2+0.72^2\times(-1)
\]

\[
=1.9216
\]

<a id="origin-1732"></a>
### 19.4 为什么倒着算

递推：

\[
\boxed{
A_t
=
\delta_t+\gamma\lambda A_{t+1}
}
\]

代码：

```python
gae = 0
for t in reversed(range(T)):
    delta = r[t] + gamma * V[t+1] - V[t]
    gae = delta + gamma * lam * gae
    advantage[t] = gae
```

---

<a id="origin-1756"></a>
## 20. 为什么 \(V_t^{target}=A_t+V(s_t)\)

定义：

\[
A(s,a)=Q(s,a)-V(s)
\]

移项：

\[
\boxed{
Q(s,a)=A(s,a)+V(s)
}
\]

所以如果 \(A_t\) 表示“相对旧 Value 多出来多少”，新的 Value Target 自然：

\[
\boxed{
V_t^{target}
=
V_{\text{old}}(s_t)+A_t
}
\]

数值例子：

\[
V_{\text{old}}(s_t)=5
\]

\[
A_t=2
\]

那么：

\[
V_t^{target}=7
\]

如果最简单：

\[
A_t=G_t-V(s_t)
\]

那么：

\[
A_t+V(s_t)=G_t
\]

所以“Advantage + baseline”就是绝对 Value Target。

---

<a id="origin-1814"></a>
## 21. Importance Sampling 到底修正什么

Rollout 数据来自：

\[
\pi_{\text{old}}
\]

但我们正在优化：

\[
\pi_{\text{new}}
\]

问题：

> 旧分布采的数据，怎么用来估计新分布下的期望？

通用公式：

\[
\mathbb E_{x\sim p}[f(x)]
=
\sum_xp(x)f(x)
\]

乘除 \(q(x)\)：

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
\mathbb E_{x\sim p}[f(x)]
=
\mathbb E_{x\sim q}
\left[
\frac{p(x)}{q(x)}f(x)
\right]
}
\]

到 PPO：

\[
p=\pi_{\text{new}},\quad q=\pi_{\text{old}}
\]

于是：

\[
\boxed{
\rho_t
=
\frac{\pi_{\text{new}}(a_t|s_t)}
{\pi_{\text{old}}(a_t|s_t)}
}
\]

---

<a id="origin-1882"></a>
## 22. Importance Sampling 中的 \(f\) 到底是什么

\(f\) 只是通用数学占位符：

> 你想求期望的那个量。

例如：

\[
f(x)=x^2
\]

也可以：

\[
f(x)=3x+5
\]

在 PPO surrogate objective 中，我们主要关心：

\[
A_t
\]

所以：

\[
\boxed{f\approx A_t}
\]

于是出现：

\[
\boxed{
\rho_tA_t
}
\]

---

<a id="origin-1922"></a>
## 23. 为什么 PPO 使用 Probability Ratio

\[
\boxed{
\rho_t(\theta)
=
\frac{\pi_\theta(a_t|s_t)}
{\pi_{\text{old}}(a_t|s_t)}
}
\]

它没有替代 Policy。

真正训练的仍然是：

\[
\pi_\theta
\]

Ratio 只是由新旧 Policy 算出来的量。

Advantage 也通常不是网络，而是通过 Reward、Value、GAE 计算出来的固定训练信号。

---

<a id="origin-1947"></a>
## 24. PPO-Clip 的完整推导

最简单 Importance-Sampled Objective：

\[
\boxed{
L(\theta)
=
\mathbb E_t[\rho_t(\theta)A_t]
}
\]

<a id="origin-1959"></a>
### 24.1 \(A_t>0\)

好动作，希望：

\[
\rho_t>1
\]

即提高该动作概率。

<a id="origin-1969"></a>
### 24.2 \(A_t<0\)

坏动作，希望：

\[
\rho_t<1
\]

即降低该动作概率。

<a id="origin-1979"></a>
### 24.3 但 Ratio 可能变化太大

PPO-Clip：

\[
\boxed{
L^{CLIP}(\theta)
=
\mathbb E_t
\left[
\min
\left(
\rho_tA_t,
\operatorname{clip}(\rho_t,1-\epsilon,1+\epsilon)A_t
\right)
\right]
}
\]

例如：

\[
\epsilon=0.2
\]

区间：

\[
[0.8,1.2]
\]

<a id="origin-2010"></a>
### 24.4 好动作例子

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

Ratio：

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

最终：

\[
\min(3,2.4)=2.4
\]

超过 1.2 后继续提高概率，不再得到额外 Objective 收益。

---

<a id="origin-2056"></a>
## 25. 为什么坏动作的 \(-1.6\) 能阻止继续激进下降

假设：

\[
A=-2
\]

当：

\[
\rho=0.9
\]

\[
\rho A=-1.8
\]

当：

\[
\rho=0.8
\]

\[
\rho A=-1.6
\]

PPO Objective 是最大化，所以：

\[
-1.6>-1.8
\]

表示降低坏动作概率是好事。

如果继续：

\[
\rho=0.7
\]

未 Clip：

\[
0.7\times(-2)=-1.4
\]

而：

\[
-1.4>-1.6
\]

如果不 Clip，优化器会继续觉得“降得更多更好”。

但：

\[
clip(0.7,0.8,1.2)=0.8
\]

所以 Clip 项：

\[
0.8\times(-2)=-1.6
\]

最终：

\[
\min(-1.4,-1.6)=-1.6
\]

真正含义不是“\(-1.6\) 比 \(-1.4\) 更好”。

恰恰相反，最大化时 \(-1.4\) 更好。

PPO 故意不给模型这个额外改善：

```text
ρ=0.8 → Objective=-1.6
ρ=0.7 → Objective=-1.6
ρ=0.6 → Objective=-1.6
```

因此继续降低 Ratio 不再获得更多优化动力。

---

<a id="origin-2146"></a>
## 26. PPO 的完整 Loss

论文常写最大化形式：

\[
L
=
L^{CLIP}
-c_1L^{VF}
+c_2H
\]

<a id="origin-2158"></a>
### 26.1 Policy Objective

\[
L^{CLIP}
=
\mathbb E
[
\min(
\rho_tA_t,
clip(\rho_t,1-\epsilon,1+\epsilon)A_t
)
]
\]

<a id="origin-2172"></a>
### 26.2 Value Loss

\[
L^{VF}
=
\frac12
(V_\phi(s_t)-V_t^{target})^2
\]

<a id="origin-2181"></a>
### 26.3 Entropy

\[
H(\pi)
=
-\sum_a\pi(a|s)\log\pi(a|s)
\]

用于保留一定探索。

<a id="origin-2191"></a>
### 26.4 PyTorch 常见最小化形式

\[
\boxed{
Loss
=
-L^{CLIP}
+c_1L^{VF}
-c_2H
}
\]

---

<a id="origin-2205"></a>
## 27. Reference Model 和 Old Policy 为什么不是一个东西

<a id="origin-2207"></a>
### 27.1 Old Policy

\[
\pi_{\text{old}}
\]

是：

> 当前这一批 Rollout 被采样时的 Policy 快照。

作用：

\[
\frac{\pi_{\text{new}}}{\pi_{\text{old}}}
\]

用于 PPO Ratio。

<a id="origin-2225"></a>
### 27.2 Reference Model

\[
\pi_{\text{ref}}
\]

通常是冻结的参考 SFT 模型。

作用：

> 防止 RL 后的模型偏离原始语言模型太远。

可加入 KL penalty：

\[
r_t^{KL}
=
-\beta
[
\log\pi_\theta(a_t|s_t)
-
\log\pi_{\text{ref}}(a_t|s_t)
]
\]

<a id="origin-2250"></a>
### 27.3 三者关系

```text
π_ref
│
├─长期冻结
└─用于 KL 约束

π_old
│
├─当前 Rollout 时的 Policy 快照
└─用于 PPO Ratio

π_θ
│
└─当前正在更新的新 Policy
```

---

<a id="origin-2270"></a>
## 28. 大模型 PPO 的完整数学数据流

<a id="origin-2272"></a>
### 28.1 第一步：当前 Policy

\[
\pi_{\text{old}}
\]

<a id="origin-2278"></a>
### 28.2 第二步：Rollout

\[
a_t
\sim
\pi_{\text{old}}(\cdot|s_t)
\]

其中：

\[
s_t=(x,a_0,\ldots,a_{t-1})
\]

保存：

```text
state
action
old_log_prob
old_value
```

<a id="origin-2301"></a>
### 28.3 第三步：Reward Model

完整 Response：

\[
y=(a_0,\ldots,a_T)
\]

Reward：

\[
R_\psi(x,y)
\]

<a id="origin-2315"></a>
### 28.4 第四步：可选 KL shaped reward

通过 Reference Model 约束策略不要偏离太远。

<a id="origin-2319"></a>
### 28.5 第五步：Critic

\[
V_{\text{old}}(s_t)
\]

<a id="origin-2325"></a>
### 28.6 第六步：TD Error

\[
\delta_t
=
r_t
+
\gamma V_{\text{old}}(s_{t+1})
-
V_{\text{old}}(s_t)
\]

<a id="origin-2337"></a>
### 28.7 第七步：GAE

\[
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
\]

<a id="origin-2347"></a>
### 28.8 第八步：Value Target

\[
V_t^{target}
=
A_t+V_{\text{old}}(s_t)
\]

<a id="origin-2355"></a>
### 28.9 第九步：PPO Update

固定旧 trajectory，不重新生成。

新 Policy 重新计算：

\[
\log\pi_\theta(a_t|s_t)
\]

Ratio：

\[
\rho_t
=
\exp
(
\log\pi_\theta(a_t|s_t)
-
\log\pi_{\text{old}}(a_t|s_t)
)
\]

等价于：

\[
\rho_t
=
\frac{\pi_\theta(a_t|s_t)}
{\pi_{\text{old}}(a_t|s_t)}
\]

<a id="origin-2387"></a>
### 28.10 第十步：Policy Loss

\[
L_{\text{policy}}
=
-
\mathbb E
[
\min(
\rho_tA_t,
clip(\rho_t,1-\epsilon,1+\epsilon)A_t
)
]
\]

<a id="origin-2402"></a>
### 28.11 第十一步：Critic Loss

\[
L_{\text{value}}
=
\mathbb E
[
(V_\phi(s_t)-V_t^{target})^2
]
\]

<a id="origin-2413"></a>
### 28.12 第十二步：更新

更新：

```text
Actor
Critic
```

通常冻结：

```text
Reward Model
Reference Model
```

<a id="origin-2429"></a>
### 28.13 第十三步：重复有限几个 Epoch

对同一批 Rollout 做 minibatch SGD。

<a id="origin-2433"></a>
### 28.14 第十四步：重新 Rollout

旧 Rollout 不再长期使用，用更新后的 Policy 重新生成数据。

---

<a id="origin-2439"></a>
## 29. 一个具体的大模型 PPO 数值例子

Prompt：

```text
1+1=
```

旧 Policy：

```text
"2": 0.80
"3": 0.10
其他: 0.10
```

Rollout 采样到了：

```text
"2"
```

所以：

\[
\pi_{\text{old}}("2"|s)=0.8
\]

保存：

\[
\log0.8
\]

Critic 原来预测：

\[
V_{\text{old}}(s)=5
\]

最终整段回答 Reward 很好。

通过 GAE 得到：

\[
A=2
\]

所以 Value Target：

\[
V^{target}=5+2=7
\]

经过一点 Policy 更新，新 Policy：

\[
\pi_{\text{new}}("2"|s)=0.92
\]

Ratio：

\[
\rho
=
\frac{0.92}{0.8}
=1.15
\]

若：

\[
\epsilon=0.2
\]

则：

\[
clip(1.15,0.8,1.2)=1.15
\]

目标项：

\[
1.15\times2=2.3
\]

继续鼓励。

如果新概率继续到：

\[
0.99
\]

则：

\[
\rho
=
\frac{0.99}{0.8}
=1.2375
\]

未 Clip：

\[
1.2375\times2=2.475
\]

Clip：

\[
1.2\times2=2.4
\]

PPO 取 2.4。

所以超过 1.2 后继续提高概率，不再获得额外 Objective 奖励。

Critic 同时训练：

若新 Critic：

\[
V_\phi(s)=5.8
\]

Target：

\[
7
\]

Value Loss：

\[
(5.8-7)^2
\]

使 Critic 逐渐逼近更合理的价值估计。

---

<a id="origin-2583"></a>
## 30. PPO 训练伪代码

```text
# A. 先训练 Reward Model

for preference_batch:

    chosen_score =
        RewardModel(prompt + chosen)

    rejected_score =
        RewardModel(prompt + rejected)

    reward_loss =
        -log sigmoid(
            chosen_score - rejected_score
        )

    backward(reward_loss)


# B. PPO

initialize policy
initialize critic
freeze reward_model
freeze reference_model

while training:

    # 1. Rollout
    old_policy = snapshot(policy)
    rollout_buffer = []

    for prompt in prompts:

        response = autoregressive_sample(old_policy)

        for each token t:
            save:
                state_t
                action_t
                old_log_prob_t
                old_value_t

        reward_model_score =
            RewardModel(prompt + response)

        add KL-shaped rewards if needed

    # 2. TD / GAE / Value Target
    for trajectory:

        gae = 0

        for t in reversed(range(T)):

            delta =
                reward_t
                + gamma * value_{t+1}
                - value_t

            gae =
                delta
                + gamma * lambda * gae

            advantage_t = gae

            value_target_t =
                advantage_t + old_value_t

    # 3. PPO Update
    # 注意：trajectory 固定，不重新生成

    for epoch in range(K):

        for minibatch in rollout_buffer:

            new_log_prob =
                policy.log_prob(
                    old_state,
                    old_action
                )

            ratio =
                exp(
                    new_log_prob
                    - old_log_prob
                )

            surr1 =
                ratio * advantage

            surr2 =
                clip(
                    ratio,
                    1-eps,
                    1+eps
                ) * advantage

            policy_loss =
                -mean(
                    min(surr1, surr2)
                )

            new_value =
                critic(old_state)

            value_loss =
                mean(
                    (new_value - value_target)^2
                )

            entropy =
                policy_entropy(...)

            total_loss =
                policy_loss
                + c1 * value_loss
                - c2 * entropy

            backward(total_loss)

    # 4. 丢掉旧 Rollout
    #    用更新后的 Policy 重新 Rollout
```

---

<a id="origin-2712"></a>
## 31. 18 个问题逐题总结

<a id="origin-2714"></a>
### 31.1 问题 1：\(J\) 公式中的 \(\log\) 到底怎么来的？

来自：

\[
\nabla P=P\nabla\log P
\]

也就是 Log-Derivative Trick。

作用：

- 把复杂概率乘积变成 log 求和；
- 把梯度写成可采样估计的期望；
- 环境转移项对 Policy 参数的导数消失。

---

<a id="origin-2732"></a>
### 31.2 问题 2：训练中的未来轨迹 Value 怎么得到？\(A\) 中的 \(G\) 怎么来？

\(G_t\)：由已经 Rollout 出来的真实 Reward 往回累计。

若完整终止：

\[
G_t=r_t+\gamma r_{t+1}+\cdots
\]

若截断：未展开未来可用 Value Bootstrapping。

Value 不是提前知道未来，而是 Critic 预测，并通过 Rollout Target 学出来。

---

<a id="origin-2748"></a>
### 31.3 问题 3：\(V\) 的“平均期待”怎么来？

\[
V^\pi(s)=\mathbb E[G_t|s_t=s]
\]

表示从同一个状态出发，按当前 Policy 反复运行时 Return 的平均。

实际用 Critic 网络近似。

---

<a id="origin-2760"></a>
### 31.4 问题 4：不训练 \(A\)，只训练 Ratio 吗？为什么 Ratio 可以替代 \(\pi\)？

不对。

真正训练的是 Actor / Policy 和 Critic。

Advantage 是根据 Reward、Value、GAE 算出来的训练信号。

Ratio：

\[
\rho=
\frac{\pi_{\text{new}}}{\pi_{\text{old}}}
\]

只是由新旧 Policy 算出的修正因子，没有替代 \(\pi\)。

---

<a id="origin-2779"></a>
### 31.5 问题 5：为什么 \(\min(-1.4,-1.6)=-1.6\) 能阻止更激进更新？

因为 PPO Objective 是最大化。

\[
-1.4>-1.6
\]

如果没有 Clip，继续降低坏动作概率会让 Objective 进一步变好到 -1.4。

PPO 故意用 -1.6，把继续改善截断。

---

<a id="origin-2793"></a>
### 31.6 问题 6：TD 公式怎么来的？是 Advantage 吗？

\[
\delta_t
=
r_t+\gamma V(s_{t+1})-V(s_t)
\]

来自：

\[
Q\approx r+\gamma V'
\]

以及：

\[
A=Q-V
\]

所以 TD Error 是 Advantage 的一步估计。

---

<a id="origin-2817"></a>
### 31.7 问题 7：为什么一步 TD 方差小、偏差大；完整 Return 偏差小、方差大？

一步 TD：

```text
只真实采一步
未来用 Critic 平均预测
→ 随机性小
→ Variance 小

但 Critic 可能错
→ Bias 大
```

完整 Return：

```text
整条随机未来都真实采样
→ Variance 大

不依赖错误 Critic 猜远期
→ Bias 较小
```

GAE 用 \(\lambda\) 折中。

---

<a id="origin-2845"></a>
### 31.8 问题 8：为什么 \(V_t^{target}=A_t+V(s_t)\)？

因为：

\[
A=Q-V
\Rightarrow
Q=A+V
\]

若：

\[
A=G-V
\]

则：

\[
A+V=G
\]

Advantage 加回 baseline 得到绝对 Value Target。

---

<a id="origin-2871"></a>
### 31.9 问题 9：PPO 和马尔科夫链什么关系？

强化学习一般建模为 MDP：

\[
P(s_{t+1}|s_t,a_t)
\]

固定 Policy 后：

\[
P_\pi(s'|s)
=
\sum_a\pi(a|s)P(s'|s,a)
\]

得到 Policy 诱导的 Markov Chain。

PPO 不断修改这个 Policy。

---

<a id="origin-2893"></a>
### 31.10 问题 10：大模型怎么用 RLHF 来训练 PPO？

映射：

```text
State = Prompt + 已生成 Token
Action = 下一个 Token
Policy = LLM
Reward = Reward Model + 可能的 KL shaping
Critic = Value Model / Value Head
```

流程：

```text
Rollout
→ Reward
→ Value
→ TD
→ GAE
→ Advantage
→ Ratio
→ Clip
→ 更新 Policy / Critic
```

---

<a id="origin-2921"></a>
### 31.11 问题 11：轨迹公式里的 \(\pi_\theta(a_t|s_t)\) 是什么？

就是当前 Policy 在状态 \(s_t\) 下，为本次实际 Action \(a_t\) 分配的概率。

大模型里：

```text
s_t = Prompt + 已生成文本
a_t = 本次实际采到的 Token
```

---

<a id="origin-2934"></a>
### 31.12 问题 12：轨迹不是只有一条吗？为什么有很多轨迹的期望？

一次真实运行确实只有一条。

但 Policy 在运行前有很多可能行为路径。

理论目标对所有可能轨迹求概率加权平均；实际用有限 Rollout 样本近似。

---

<a id="origin-2944"></a>
### 31.13 问题 13：Rollout 是什么，训练中真的会真实采样吗？

是。

大模型 PPO 中真的会：

```text
取 Prompt
→ autoregressive forward
→ 根据概率采样 Token
→ 生成 Response
```

---

<a id="origin-2959"></a>
### 31.14 问题 14：Importance Sampling 里的 \(f\) 是什么？

只是“我们希望求期望的那个函数”。

在 PPO surrogate objective 里主要对应 Advantage：

\[
f\approx A_t
\]

所以得到：

\[
\frac{\pi_{\text{new}}}{\pi_{\text{old}}}A_t
\]

---

<a id="origin-2977"></a>
### 31.15 问题 15：什么叫 TD？

Temporal Difference：

> 走一步后获得的新价值估计，与原 Value 预测之间的差。

\[
\delta_t
=
\underbrace{r_t+\gamma V(s_{t+1})}_{\text{走一步后的新估计}}
-
\underbrace{V(s_t)}_{\text{原预测}}
\]

---

<a id="origin-2993"></a>
### 31.16 问题 16：Reward Model 是普通 SFT 吗？chosen/rejected 怎么训练？

不是普通 SFT。

对 chosen 输出 \(r_c\)，对 rejected 输出 \(r_r\)，要求：

\[
r_c>r_r
\]

常用：

\[
\boxed{
L_{RM}
=
-\log\sigma(r_c-r_r)
}
\]

它学的是相对偏好排序。

---

<a id="origin-3017"></a>
### 31.17 问题 17：\(V\) 怎么训练出来？Critic 怎么训练？

Critic 的监督信号来自 PPO Rollout。

先算：

\[
\delta_t
=
r_t+\gamma V_{old}(s_{t+1})-V_{old}(s_t)
\]

再算 GAE 得 \(A_t\)，构造：

\[
V_t^{target}
=
A_t+V_{old}(s_t)
\]

然后：

\[
L_V
=
(V_\phi(s_t)-V_t^{target})^2
\]

训练 Critic。

---

<a id="origin-3049"></a>
### 31.18 问题 18：每执行一次 Action，后面序列都会变，那最开始 Rollout 有什么用？

会变，所以必须区分两个阶段。

Rollout 阶段：

```text
真实采样 Action
Action 改变未来 State
```

PPO Update 阶段：

```text
固定旧 trajectory
不重新生成
只让新 Policy 重新计算旧 Action 在旧 State 下的新概率
```

训练有限几个 Epoch 后，旧 Rollout 不再继续使用，重新采样。

PPO 的 Ratio 和 Clip 正是为了在短期重复使用旧 Rollout 时，限制新 Policy 不要偏离产生数据的旧 Policy 太远。

---

<a id="origin-3074"></a>
## 32. 最终知识地图

```text
人类偏好数据
chosen / rejected
        │
        ↓
Reward Model Training
        │
        ↓
得到“回答质量裁判”
        │
        │
当前 Policy / Actor
        │
        ↓
真实 Rollout
        │
        ↓
trajectory
(state, action, old_log_prob)
        │
        ↓
完整 Response ─────────────→ Reward Model
                                  │
                                  ↓
                               Reward
                                  │
                                  ↓
Critic: V(s_t) ──────────────────┘
        │
        ↓
     TD Error
        │
        ↓
       GAE
        │
        ↓
   Advantage A
        │
        ↓
固定旧 trajectory
新 Policy 重新算 π_new(a_t|s_t)
        │
        ↓
Probability Ratio
        │
 π_new(a_t|s_t)
ρ = ───────────────
 π_old(a_t|s_t)
        │
        ↓
     PPO Clip
        │
        ↓
   Policy Loss
      │       │
      │       └────→ Critic Loss
      │                │
      ↓                ↓
 更新 Actor        更新 Critic
      │                │
      └──────┬─────────┘
             ↓
        若干 Epoch
             ↓
       丢掉旧 Rollout
             ↓
   用最新 Policy 重新采样
             ↓
          下一轮
```

---

<a id="origin-3149"></a>
## 33. 最后只记住 10 句话

1. **Policy 是做决定的，Critic 是预测局面价值的。**
2. **Reward Model 是偏好裁判，通常用 chosen / rejected 训练，不是普通 Token-level SFT。**
3. **Rollout 是让当前 Policy 真正运行、真实采样 trajectory。**
4. **一次运行只有一条 trajectory，但 Policy 理论上可以产生大量可能 trajectory。**
5. **\(V(s)\) 是未来 Return 的期望，由 Critic 从 Rollout 数据中学出来。**
6. **TD Error 是“走一步后的新价值估计”和“原 Value 预测”的差。**
7. **GAE 用多个 TD Error 来估计 Advantage，并在 Bias / Variance 之间折中。**
8. **Ratio 不是另一个模型，也没有替代 Policy；它只是 \(\pi_{new}/\pi_{old}\)。**
9. **PPO Update 阶段固定旧 trajectory，不重新采样；训练几轮后才重新 Rollout。**
10. **PPO 的核心就是：好动作提高概率，坏动作降低概率，但每轮都不能改得太猛。**

---

<a id="origin-3164"></a>
## 34. 最核心公式汇总

<a id="origin-3166"></a>
### 34.1 Return

\[
G_t
=
r_t+\gamma r_{t+1}+\gamma^2r_{t+2}+\cdots
\]

<a id="origin-3174"></a>
#### 34.1.1 Value

\[
V^\pi(s)
=
\mathbb E_\pi[G_t|s_t=s]
\]

<a id="origin-3182"></a>
#### 34.1.2 Q

\[
Q^\pi(s,a)
=
\mathbb E[G_t|s_t=s,a_t=a]
\]

<a id="origin-3190"></a>
#### 34.1.3 Advantage

\[
A^\pi(s,a)
=
Q^\pi(s,a)-V^\pi(s)
\]

<a id="origin-3198"></a>
#### 34.1.4 TD Error

\[
\delta_t
=
r_t+\gamma V(s_{t+1})-V(s_t)
\]

<a id="origin-3206"></a>
#### 34.1.5 GAE

\[
A_t^{GAE}
=
\sum_{l=0}^{\infty}
(\gamma\lambda)^l
\delta_{t+l}
\]

<a id="origin-3216"></a>
#### 34.1.6 Value Target

\[
V_t^{target}
=
A_t+V_{old}(s_t)
\]

<a id="origin-3224"></a>
#### 34.1.7 Ratio

\[
\rho_t(\theta)
=
\frac{\pi_\theta(a_t|s_t)}
{\pi_{old}(a_t|s_t)}
\]

<a id="origin-3233"></a>
#### 34.1.8 PPO-Clip

\[
L^{CLIP}
=
\mathbb E_t
\left[
\min
\left(
\rho_tA_t,
clip(\rho_t,1-\epsilon,1+\epsilon)A_t
\right)
\right]
\]

<a id="origin-3248"></a>
#### 34.1.9 Reward Model Pairwise Loss

\[
L_{RM}
=
-\log
\sigma
\left(
r_{chosen}-r_{rejected}
\right)
\]

<a id="origin-3260"></a>
#### 34.1.10 Critic Loss

\[
L_V
=
\mathbb E
\left[
(V_\phi(s_t)-V_t^{target})^2
\right]
\]

<a id="origin-3271"></a>
#### 34.1.11 PPO 总 Loss（最小化形式）

\[
Loss
=
-L^{CLIP}
+c_1L_V
-c_2H(\pi)
\]

---

<a id="origin-3283"></a>
## 35. 一句话总结

\[
\boxed{
\text{RLHF-PPO}
=
\text{人类偏好训练 Reward Model}
\rightarrow
\text{Policy Rollout}
\rightarrow
\text{Critic 估值}
\rightarrow
\text{TD / GAE 算 Advantage}
\rightarrow
\text{PPO Clip 稳定更新 Actor}
\rightarrow
\text{同步训练 Critic}
}
\]

如果把 PPO 再翻译成人话，就是：

> **先让模型真实回答问题；再用 Reward Model 告诉它整段回答好不好；用 Critic 判断每一步原本应该有多好；用 Advantage 判断实际动作比预期好还是差；好动作以后多选一点，坏动作以后少选一点，但为了不把原模型一下子改坏，每一轮都只允许稳稳地改一点。**
