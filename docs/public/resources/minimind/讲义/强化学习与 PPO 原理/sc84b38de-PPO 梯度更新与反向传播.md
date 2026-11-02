# PPO 梯度更新与反向传播


> 目标：彻底回答三个问题：
>
> 1. PPO 中到底谁是真正被更新的参数？
> 2. \(A>0\) 和 \(A<0\) 时，梯度究竟怎样改变 token 概率？
> 3. 为什么强化学习里有 State、Action、Environment、Reward Model、Critic 等一大堆东西，最后仍然只是 `loss.backward()`？

---

<a id="origin-11"></a>
## 1. 第一部分：从 SFT 与 PPO 的区别理解 Advantage 与 Actor 反向传播

<a id="origin-13"></a>
## 2. 现在和最熟悉的 SFT 对比

这一步最能解释：

> 为什么强化学习看起来很复杂，最后仍然只是一个 Loss。

我们仍然使用：

```text
浙江大学位于 → 宁波
```

---

<a id="origin-27"></a>
## 3. SFT 的完整更新流程

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

<a id="origin-95"></a>
## 4. SFT 中“正确答案”本身有梯度吗？

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

<a id="origin-131"></a>
## 5. PPO 的完整更新流程

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

<a id="origin-167"></a>
## 6. 最关键的 SFT vs PPO 对比

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

<a id="origin-199"></a>
## 7. Reward + Critic + GAE 本质是在制造 Actor 的训练信号

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

因此可以把 Advantage 理解成一种：

\[
\boxed{
\text{动态产生的软训练信号}
}
\]

它不是传统分类中的 one-hot 标签。

但是它承担了类似职责：

> 告诉模型刚才的 action 应该被鼓励还是被抑制。

---

<a id="origin-241"></a>
## 8. 三句话彻底记住

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

> **SFT 由数据集直接告诉模型哪个 token 是正确的；PPO 没有标准答案，所以先通过 State、Action、Reward、Critic、GAE 等过程计算 Advantage。Advantage 决定刚才的 action 应该提高还是降低概率；随后真正的梯度仍然沿 `new_log_prob → logits → Transformer → θ` 传播。**
> **即：Advantage 算好以后，上游的 Reward、Reward Model、GAE、Environment 不再参与这一轮 Actor 的反向传播；此时 Advantage 被当作一个固定的训练信号，作用类似于 SFT 中的标签：它告诉模型刚才这个 action 应该被鼓励还是抑制、力度有多大。真正参与反向传播的是当前 Actor 的 new_log_prob → logits → Transformer → 参数 θ 这条计算图，Advantage 只是作为一个固定系数控制梯度的方向和强度**

---

<a id="origin-266"></a>
## 9. 为什么 PPO 最后还是一个 `loss.backward()`？

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

<a id="origin-321"></a>
## 10. 为什么 Reward Model 不需要参与 backward？

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

<a id="origin-364"></a>
## 11. Advantage 到底是什么作用？

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

<a id="origin-408"></a>
## 12. 先把最容易混淆的符号说清楚

PPO 中最重要的三个符号是：

\[
\theta,\qquad
\pi_\theta(a|s),\qquad
\log \pi_\theta(a|s)
\]

它们不是一回事。

---

<a id="origin-422"></a>
### 12.1 \(\theta\)：真正被训练的模型参数

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

<a id="origin-476"></a>
### 12.2 \(\pi_\theta(a|s)\)：模型算出来的概率，不是参数

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

<a id="origin-522"></a>
### 12.3 \(\log \pi_\theta(a|s)\)：概率取 log

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

<a id="origin-551"></a>
## 13. 三者真正的关系

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

<a id="origin-615"></a>
## 14. PPO Actor 最简单的 Loss

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

<a id="origin-661"></a>
## 15. 为什么一直研究 \(\log\pi\)，最后却更新 \(\theta\)？

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

<a id="origin-725"></a>
## 16. 大模型只是把一个 \(\theta\) 变成几十亿个参数

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

<a id="origin-803"></a>
## 17. PPO 中 State 到底是什么？

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

<a id="origin-856"></a>
## 18. Action 到底是什么？

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

<a id="origin-900"></a>
## 19. Environment 去哪了？

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

<a id="origin-969"></a>
## 20. Reward Model 干什么？

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

<a id="origin-995"></a>
## 21. Critic 干什么？

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

<a id="origin-1049"></a>
## 22. Critic 为什么又要更新？

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

<a id="origin-1099"></a>
## 23. 为什么一个 backward 可以同时训练 Actor 和 Critic？

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

<a id="origin-1145"></a>
## 24. Actor 和 Critic 的梯度会串到一起吗？

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

<a id="origin-1199"></a>
## 25. 最终完整流程图

<a id="origin-1201"></a>
### 25.1 SFT

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

<a id="origin-1225"></a>
#### 25.1.1 PPO

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

<a id="origin-1280"></a>
## 26. 最后把所有对象一次性分清楚

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

<a id="origin-1301"></a>
## 27. Clip 从梯度角度是在干什么？

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

<a id="origin-1369"></a>
## 28. Reference KL 又在干什么？

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

<a id="origin-1412"></a>
## 29. 第二部分：具体例子——从 Advantage 求导到参数更新与概率变化

<a id="origin-1414"></a>
## 30. Ratio 到底是什么意思？

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

<a id="origin-1454"></a>
## 31. 先看 \(A=+2\)：为什么概率会升高？

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

<a id="origin-1511"></a>
### 31.1 对 \(\log\pi_\theta\) 求导

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

<a id="origin-1608"></a>
## 32. 重点：\(A=-2\) 的完整求导例子

现在看你最关心的情况：

\[
\boxed{
A=-2
}
\]

它意味着：

> 当前 action 比预期差，所以希望以后更不容易生成。

---

<a id="origin-1624"></a>
### 32.1 给定 Old Policy 和 Current Policy

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

<a id="origin-1674"></a>
### 32.2 计算 Loss

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

<a id="origin-1709"></a>
### 32.3 对 \(\log\pi_\theta\) 求导

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

<a id="origin-1807"></a>
## 33. 正梯度为什么会让 action probability 下降？

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

<a id="origin-1892"></a>
## 34. 把 \(A=-2\) 的梯度继续传到真正参数 \(\theta\)

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

<a id="origin-1978"></a>
## 35. 真正执行一次参数更新

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

<a id="origin-2044"></a>
## 36. 验证概率真的下降

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

<a id="origin-2125"></a>
## 37. 把 \(A=-2\) 的全过程压缩成一条链

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

<a id="origin-2170"></a>
## 38. \(A=-2\) 最终一句话

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
