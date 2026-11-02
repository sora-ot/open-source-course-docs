# PPO 训练代码


> 目标：不是只会“跑 PPO”，而是看懂这份代码为什么这样写、每一个关键 API 在做什么、每一个张量是什么形状，以及一条 Prompt 到底怎样一步一步变成一次 PPO 参数更新。
>
> 源文件：`train_ppo.py`，共 532 行。
>
> 记号：
>
> - `B`：一个 rollout batch 中的 Prompt 数量
> - `P`：Prompt token 长度
> - `R`：Response token 长度
> - `T=P+R`：完整序列长度
> - `H`：hidden size
> - `V`：词表大小
> - `old`：采样这批回答时的策略
> - `new/current`：正在被 PPO 更新的 Actor
> - `ref`：冻结的参考策略，通常是 SFT 模型

---

<a id="origin-21"></a>
## 1. 先用一句话说清楚这份程序在干什么

这份代码实现的是一个典型的 **LLM PPO 在线强化学习循环**：

```text
Prompt
  ↓
Actor 生成回答
  ↓
保存“采样时 Actor”对每个回答 token 的 old_log_prob
  ↓
Reward Model + 规则奖励 → 整条回答 reward
  ↓
Critic 对每个回答位置估计 Value
  ↓
把最终 reward 放到最后一个回答 token
  ↓
GAE 从后往前传播奖励
  ↓
得到每个 token 的 Advantage 和 Return
  ↓
对同一批 rollout 做若干轮 PPO 更新
  ├── 更新 Actor
  └── 更新 Critic
  ↓
必要时把新 Actor 同步给 rollout engine
  ↓
保存权重
```

最重要的是：

> **PPO 不是“生成一个回答，然后直接让 reward 对语言模型反向传播”。**

Reward Model 给出来的只是一个分数，它本身通常没有连接到 Actor 的计算图。

真正让 Actor 更新的是：

\[
\text{Reward}
\rightarrow
\text{GAE}
\rightarrow
A_t
\rightarrow
\text{PPO Policy Loss}
\rightarrow
\nabla_\theta
\]

---

<a id="origin-73"></a>
## 2. 先分清四个模型/角色

这份代码至少要同时理解四个角色。

<a id="origin-77"></a>
### 2.1 Actor：当前正在训练的语言模型

代码：

```python
actor_model, tokenizer = init_model(...)
```

Actor 做两件事：

1. 根据 Prompt 生成 Response；
2. PPO 更新时重新计算 Response token 的概率。

记为：

\[
\pi_\theta(a_t|s_t)
\]

其中：

- \(s_t\)：当前上下文；
- \(a_t\)：当前生成的 token；
- \(\theta\)：Actor 参数。

---

<a id="origin-104"></a>
### 2.2 Old Policy：采样这批数据时的 Actor

代码中没有单独创建一个 `old_model`。

而是 rollout 时直接保存：

```python
old_resp_logp = rollout_result.per_token_logps
```

所以“旧策略”被压缩成了：

> **这批动作当初被采样出来时的 log probability。**

例如：

```text
token:       A       B       C
old_logp:   -0.7    -1.1    -0.3
```

后面 Actor 更新后，再算：

```text
new_logp
```

于是：

\[
r_t(\theta)
=
\frac{\pi_\theta(a_t|s_t)}
{\pi_{\text{old}}(a_t|s_t)}
=
\exp(
\log\pi_\theta
-
\log\pi_{\text{old}}
)
\]

这就是 PPO 的概率比值。

<a id="origin-148"></a>
#### 2.2.1 为什么不一定要真的保存一整份 old model？

因为 PPO 对这批已经采样好的 token，只需要知道：

\[
\pi_{\text{old}}(a_t|s_t)
\]

也就是说，只要保存这些被选中 token 的 old log probability 就够了。

---

<a id="origin-160"></a>
### 2.3 Reference Model：永远冻结的参考模型

代码：

```python
ref_model, _ = init_model(...)
ref_model = ref_model.eval().requires_grad_(False)
```

它与 old policy 的作用完全不同。

<a id="origin-171"></a>
#### 2.3.1 old policy 的作用

回答：

> “这批 token 当初是以多大概率被采样出来的？”

用于 PPO ratio：

\[
\frac{\pi_{\text{new}}}{\pi_{\text{old}}}
\]

<a id="origin-183"></a>
#### 2.3.2 reference model 的作用

回答：

> “当前 Actor 是否已经偏离原始 SFT 模型太远？”

用于 reference KL 约束。

所以：

```text
Old Policy
    ↓
控制“一次 PPO 更新别跨太大步”

Reference Model
    ↓
控制“长期训练别离原始模型太远”
```

---

<a id="origin-205"></a>
### 2.4 Critic：估计每个 token 状态有多“值钱”

代码：

```python
class CriticModel(MiniMindForCausalLM):
    def __init__(self, params):
        super().__init__(params)
        self.value_head = nn.Linear(params.hidden_size, 1)
```

普通语言模型：

\[
[B,T,H]
\rightarrow
[B,T,V]
\]

Critic：

\[
[B,T,H]
\rightarrow
[B,T,1]
\rightarrow
[B,T]
\]

它不预测“下一个 token 是什么”，而是预测：

\[
V(s_t)
\]

即：

> 从当前状态继续往后走，预计最终能得到多少回报？

---

<a id="origin-246"></a>
## 3. 外部库和项目外部接口：逐个讲清楚

下面不是按源码顺序，而是按功能分类。相同 API 在源码里出现多次，这里只解释一次。

---

<a id="origin-252"></a>
### 3.1 `os` / `sys`：处理 Python 导包路径

<a id="origin-254"></a>
#### 3.1.1 `os.path.dirname(__file__)`

```python
os.path.dirname(__file__)
```

`__file__` 是当前 Python 文件路径。

假设：

```text
/project/trainer/train_ppo.py
```

那么：

```python
os.path.dirname(__file__)
```

得到：

```text
/project/trainer
```

---

<a id="origin-282"></a>
#### 3.1.2 `os.path.join(...)`

把多个路径片段按当前操作系统规则拼起来。

```python
os.path.join("/project/trainer", "..")
```

得到类似：

```text
/project/trainer/..
```

---

<a id="origin-298"></a>
#### 3.1.3 `os.path.abspath(...)`

把相对路径变成绝对路径。

例如：

```text
/project/trainer/..
```

转成：

```text
/project
```

---

<a id="origin-316"></a>
#### 3.1.4 `sys.path.append(...)`

Python 导包时会搜索 `sys.path` 中的目录。

代码：

```python
sys.path.append(project_root)
```

等价于告诉 Python：

> “除了默认环境，还到项目根目录找 `model`、`dataset`、`trainer`。”

---

<a id="origin-332"></a>
#### 3.1.5 `os.makedirs(path, exist_ok=True)`

创建目录。

```python
os.makedirs(args.save_dir, exist_ok=True)
```

`exist_ok=True` 表示：

```text
目录不存在 → 创建
目录已经存在 → 不报错
```

---

<a id="origin-349"></a>
### 3.2 `warnings`

<a id="origin-351"></a>
#### 3.2.1 `warnings.filterwarnings('ignore')`

把 Python warning 隐藏掉。

注意：

> Warning 不是 Error。

它不会改变程序逻辑，只是不打印警告。

---

<a id="origin-363"></a>
### 3.3 `datasets`

```python
import datasets
```

这份脚本并没有调用 `datasets.xxx()`。

注释说明它主要是一个：

> Windows 下 `pyarrow / torch DLL` 冲突规避。

也就是说，这里的作用更多是“通过导入顺序影响动态库加载”，而不是训练逻辑本身。

---

<a id="origin-379"></a>
### 3.4 `argparse`：命令行参数

<a id="origin-381"></a>
#### 3.4.1 `argparse.ArgumentParser(...)`

创建命令行解析器。

```python
parser = argparse.ArgumentParser(...)
```

---

<a id="origin-391"></a>
#### 3.4.2 `parser.add_argument(...)`

定义允许用户输入的参数。

例如：

```python
parser.add_argument(
    "--learning_rate",
    type=float,
    default=3e-7
)
```

于是命令行可以写：

```bash
python train_ppo.py --learning_rate 1e-6
```

如果不写，就用：

```text
3e-7
```

---

<a id="origin-419"></a>
#### 3.4.3 `parser.parse_args()`

真正读取命令行参数：

```python
args = parser.parse_args()
```

以后：

```python
args.learning_rate
args.batch_size
args.gamma
```

就可以访问。

---

<a id="origin-439"></a>
### 3.5 `math`

<a id="origin-441"></a>
#### 3.5.1 `math.ceil(x)`

向上取整。

例如：

\[
\frac{5}{2}=2.5
\]

```python
math.ceil(2.5)
```

得到：

```text
3
```

代码用它估算：

- 一个大 batch 要切几个 mini-batch；
- 总共大约有多少 optimizer step。

---

<a id="origin-468"></a>
### 3.6 `re`：正则表达式（重点）

<a id="origin-470"></a>
#### 3.6.1 `re.findall(pattern, text)`

找出所有匹配项。

<a id="origin-474"></a>
##### 3.6.1.1 在重复惩罚中

```python
re.findall(r"\w+|[^\w\s]", text.lower())
```

把文本粗略拆成：

- 单词/数字等；
- 标点符号。

例如：

```text
Hello, world!
```

变成：

```python
["hello", ",", "world", "!"]
```

<a id="origin-497"></a>
##### 3.6.1.2 在 Prompt 解析中

代码：

```python
pattern = r"<\|im_start\|>(system|user|assistant)\s+(.*?)<\|im_end\|>"
matches = re.findall(pattern, prompt, re.DOTALL)
```

用于把 ChatML 风格文本：

```text
<|im_start|>user
你好
<|im_end|>
```

还原成：

```python
{
    "role": "user",
    "content": "你好"
}
```

---

<a id="origin-525"></a>
#### 3.6.2 `re.DOTALL`

默认正则中的 `.` 不匹配换行符。

加 `re.DOTALL` 后：

```text
.
```

也能跨行匹配。

这对多行消息很重要。

---

<a id="origin-541"></a>
### 3.7 `contextlib.nullcontext`

<a id="origin-543"></a>
#### 3.7.1 `nullcontext()`

它是一个“什么都不做”的上下文管理器。

代码：

```python
autocast_ctx = (
    nullcontext()
    if device_type == "cpu"
    else torch.cuda.amp.autocast(...)
)
```

于是后面可以统一写：

```python
with autocast_ctx:
    ...
```

CPU 时：

```text
什么都不做
```

GPU 时：

```text
进入 AMP autocast
```

这样就不用写两套代码。

---

<a id="origin-580"></a>
### 3.8 PyTorch：创建 Tensor

<a id="origin-582"></a>
#### 3.8.1 `torch.zeros(...)`

创建全 0 Tensor。

例如：

```python
torch.zeros(3)
```

得到：

```text
[0, 0, 0]
```

代码：

```python
rewards = torch.zeros(len(responses), device=args.device)
```

形状：

\[
[B]
\]

---

<a id="origin-612"></a>
#### 3.8.2 `torch.zeros_like(x)`

创建和 `x`：

- shape 一样；
- dtype 通常一样；
- device 一样；

但内容全为 0。

```python
token_rewards = torch.zeros_like(old_resp_logp)
```

如果：

\[
old\_resp\_logp \in \mathbb{R}^{B\times R}
\]

那么：

\[
token\_rewards \in \mathbb{R}^{B\times R}
\]

---

<a id="origin-640"></a>
#### 3.8.3 `torch.tensor(data, device=...)`

把 Python list / number 转成 Tensor。

代码：

```python
reward_model_scores = torch.tensor(
    reward_model_scores,
    device=args.device
)
```

---

<a id="origin-655"></a>
#### 3.8.4 `torch.arange(n)`

得到：

```text
0,1,2,...,n-1
```

例如：

```python
resp_idx = torch.arange(R)
```

得到回答内部位置：

```text
[0,1,2,...,R-1]
```

---

<a id="origin-677"></a>
#### 3.8.5 `torch.randperm(n)`

得到 `0 ~ n-1` 的随机排列。

例如：

```python
torch.randperm(5)
```

可能得到：

```text
[3,0,4,1,2]
```

PPO 用它随机打乱样本，再切 mini-batch。

---

<a id="origin-697"></a>
#### 3.8.6 `torch.stack(list, dim=...)`（重点）

把若干形状相同的 Tensor 沿新维度堆起来。

GAE 是倒序逐时刻算的：

```python
advs_rev.append(lastgaelam)
```

最后：

```python
torch.stack(advs_rev[::-1], dim=1)
```

重新得到：

\[
[B,R]
\]

<a id="origin-719"></a>
#### 3.8.7 `torch.stack(list, dim=...)`：为什么 GAE 最后要这样写？

`torch.stack()` 的作用是：

> 把多个**形状相同的 Tensor**，沿着一个新的维度堆起来。

在 PPO 的 GAE 中：

```python
advs_rev.append(lastgaelam)
```

每一次循环得到的是：

> 当前时间步、整个 Batch 的 Advantage。

---

<a id="origin-737"></a>
##### 3.8.7.1 假设 Batch 中有 2 条回答

即：

\[
B=2
\]

每条回答有 3 个 token：

\[
R=3
\]

例如：

```text
样本1：A1 A2 A3
样本2：B1 B2 B3
```

我们最终希望得到的 Advantage 矩阵是：

\[
[B,R]=[2,3]
\]

也就是：

```text
          token1   token2   token3
样本1      A1       A2       A3
样本2      B1       B2       B3
```

---

<a id="origin-774"></a>
##### 3.8.7.2 GAE 是从后往前计算的

代码：

```python
for t in reversed(range(gen_len)):
```

如果：

```text
gen_len = 3
```

那么实际计算顺序是：

```text
t = 2
t = 1
t = 0
```

也就是：

```text
token3
↓
token2
↓
token1
```

---

<a id="origin-808"></a>
##### 3.8.7.3 第一次循环：计算最后一个 token

假设两个样本最后一个 token 的 Advantage 分别是：

```python
lastgaelam = tensor([1.2, 0.8])
```

这里：

```text
1.2 → 样本1的 token3
0.8 → 样本2的 token3
```

形状是：

\[
[B]=[2]
\]

然后：

```python
advs_rev.append(lastgaelam)
```

于是：

```python
advs_rev = [
    tensor([1.2, 0.8])
]
```

---

<a id="origin-845"></a>
##### 3.8.7.4 第二次循环：计算 token2

假设得到：

```python
lastgaelam = tensor([1.5, 1.1])
```

其中：

```text
1.5 → 样本1的 token2
1.1 → 样本2的 token2
```

继续：

```python
advs_rev.append(lastgaelam)
```

得到：

```python
advs_rev = [
    tensor([1.2, 0.8]),   # token3
    tensor([1.5, 1.1])    # token2
]
```

---

<a id="origin-877"></a>
##### 3.8.7.5 第三次循环：计算 token1

假设：

```python
lastgaelam = tensor([1.8, 1.4])
```

继续 append：

```python
advs_rev = [
    tensor([1.2, 0.8]),   # token3
    tensor([1.5, 1.1]),   # token2
    tensor([1.8, 1.4])    # token1
]
```

注意：

> 因为 GAE 是倒着计算的，所以现在列表顺序也是反的。

现在是：

```text
token3
token2
token1
```

但我们真正想要的是：

```text
token1
token2
token3
```

---

<a id="origin-917"></a>
##### 3.8.7.6 所以先使用 `[::-1]`

代码：

```python
advs_rev[::-1]
```

表示：

> 把 Python List 倒过来。

于是：

```python
[
    tensor([1.8, 1.4]),   # token1
    tensor([1.5, 1.1]),   # token2
    tensor([1.2, 0.8])    # token3
]
```

现在时间顺序恢复正常：

```text
token1
token2
token3
```

---

<a id="origin-949"></a>
##### 3.8.7.7 接下来使用 `torch.stack(..., dim=1)`

代码：

```python
advantages = torch.stack(advs_rev[::-1], dim=1)
```

当前有三个 Tensor：

```python
tensor([1.8, 1.4])   # token1
tensor([1.5, 1.1])   # token2
tensor([1.2, 0.8])   # token3
```

每一个 Tensor 的形状都是：

\[
[B]=[2]
\]

可以把它们想象成：

```text
token1：

[1.8,
 1.4]


token2：

[1.5,
 1.1]


token3：

[1.2,
 0.8]
```

现在沿：

```python
dim=1
```

把它们拼起来：

```text
             token1   token2   token3

样本1          1.8      1.5      1.2

样本2          1.4      1.1      0.8
```

最终：

```python
advantages = tensor([
    [1.8, 1.5, 1.2],
    [1.4, 1.1, 0.8]
])
```

形状：

\[
[2,3]
\]

也就是：

\[
[B,R]
\]

---

<a id="origin-1031"></a>
##### 3.8.7.8 为什么是 `dim=1`？

因为我们希望：

```text
第 0 维：Batch
第 1 维：Response Token
```

即：

```text
advantages[样本编号][token编号]
```

例如：

```python
advantages[0]
```

得到：

```text
[1.8, 1.5, 1.2]
```

表示：

> 第 1 条回答三个 token 的 Advantage。

而：

```python
advantages[1]
```

得到：

```text
[1.4, 1.1, 0.8]
```

表示：

> 第 2 条回答三个 token 的 Advantage。

---

<a id="origin-1080"></a>
##### 3.8.7.9 如果使用 `dim=0` 会怎样？

如果写：

```python
torch.stack(advs_rev[::-1], dim=0)
```

得到：

```python
tensor([
    [1.8, 1.4],   # token1
    [1.5, 1.1],   # token2
    [1.2, 0.8]    # token3
])
```

形状：

\[
[R,B]=[3,2]
\]

也就是说：

```text
          样本1   样本2

token1     1.8     1.4
token2     1.5     1.1
token3     1.2     0.8
```

但后面的 PPO 代码通常希望数据格式是：

\[
[B,R]
\]

也就是：

```text
每一行 = 一条回答
每一列 = 一个 token
```

所以源码使用：

```python
dim=1
```

---

<a id="origin-1135"></a>
##### 3.8.7.10 最后把整个过程画出来

```text
GAE 倒序计算：

t = 2
lastgaelam = [1.2, 0.8]
          ↓ append

t = 1
lastgaelam = [1.5, 1.1]
          ↓ append

t = 0
lastgaelam = [1.8, 1.4]
          ↓ append
```

此时：

```python
advs_rev = [
    [1.2, 0.8],   # token3
    [1.5, 1.1],   # token2
    [1.8, 1.4]    # token1
]
```

先反转：

```python
advs_rev[::-1]
```

得到：

```python
[
    [1.8, 1.4],   # token1
    [1.5, 1.1],   # token2
    [1.2, 0.8]    # token3
]
```

再：

```python
torch.stack(..., dim=1)
```

得到：

```python
[
    [1.8, 1.5, 1.2],   # 样本1
    [1.4, 1.1, 0.8]    # 样本2
]
```

最终：

\[
\boxed{
advantages.shape=[B,R]
}
\]

---

<a id="origin-1204"></a>
##### 3.8.7.11 一句话记忆

```python
torch.stack(advs_rev[::-1], dim=1)
```

可以拆成两件事：

```text
[::-1]
    ↓
因为 GAE 是倒着算的，
先把 token 顺序恢复成 token1 → token2 → token3

torch.stack(..., dim=1)
    ↓
把每个时间步得到的 [B] Advantage
沿 token 维拼起来

最终：
[B] × R
→
[B,R]
```

所以最终矩阵的含义就是：

```text
行 = 不同样本
列 = 不同 response token
值 = 每个 token 对应的 Advantage
```

---

<a id="origin-1239"></a>
#### 3.8.8 `torch.where(condition, x, y)`（重点）

逐元素：

```text
condition 为 True → 取 x
condition 为 False → 取 y
```

代码用它处理：

```text
如果发现 EOS → 长度取 EOS 位置 + 1
否则 → 使用原非 PAD 长度
```

---

<a id="origin-1257"></a>
#### 3.8.9 `torch.argmax(x, dim=...)`

找到最大值的位置。

这里 `eos_mask` 是 0/1：

```text
[0,0,1,0,0]
```

`argmax` 得到：

```text
2
```

所以可以找到第一个 EOS。

---

<a id="origin-1277"></a>
#### 3.8.10 `torch.exp(x)`

\[
e^x
\]

PPO 中最关键的用法：

\[
\exp(
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
)
=
\frac{
\pi_{\text{new}}
}{
\pi_{\text{old}}
}
\]

---

<a id="origin-1301"></a>
#### 3.8.11 `torch.clamp(x, min, max)`（重点）

把数值限制在指定区间。

例如：

```text
1.4
```

如果限制：

```text
[0.8,1.2]
```

就变成：

```text
1.2
```

PPO 最经典的 clipping 就是它。

---

<a id="origin-1327"></a>
#### 3.8.12 `torch.max(a,b)`

逐元素取较大值。

代码写的是损失：

```python
torch.max(
    -A * ratio,
    -A * clipped_ratio
)
```

因为：

\[
\max(-x,-y)
=
-\min(x,y)
\]

所以它与经典 PPO：

\[
-\min(
r_t A_t,
\operatorname{clip}(r_t)A_t
)
\]

完全对应。

---

<a id="origin-1361"></a>
#### 3.8.13 `torch.rsqrt(x)`（重点）

计算：

\[
\frac{1}{\sqrt{x}}
\]

代码：

```python
advantages = (
    advantages - adv_mean
) * torch.rsqrt(adv_var + 1e-8)
```

其实就是标准化：

\[
\frac{A-\mu}{\sqrt{\sigma^2+\epsilon}}
\]

---

<a id="origin-1385"></a>
### 3.9 PyTorch：关闭梯度

<a id="origin-1387"></a>
#### 3.9.1 `torch.no_grad()`

```python
with torch.no_grad():
    ...
```

表示里面的运算：

> 不构建反向传播计算图。

这不等于：

```python
model.eval()
```

两者区别：

```text
no_grad()
    → 不记录梯度

eval()
    → 改变 Dropout / BatchNorm 等模块行为
```

在这份代码中，Reward Model、rollout Critic、Reference Model 概率都不需要从这里反向传播。

---

<a id="origin-1418"></a>
### 3.10 `nn.Linear`

```python
nn.Linear(H, 1)
```

数学形式：

\[
y = xW^T+b
\]

如果：

\[
x\in\mathbb{R}^{B\times T\times H}
\]

且：

\[
W\in\mathbb{R}^{1\times H}
\]

得到：

\[
y\in\mathbb{R}^{B\times T\times1}
\]

Critic 用它把每个 token 的 hidden state 压成一个标量 Value。

---

<a id="origin-1452"></a>
### 3.11 Tensor 的常用类型转换

<a id="origin-1454"></a>
#### 3.11.1 `.long()`

转为：

```text
torch.int64
```

常用于：

- token id；
- index；
- mask 的整数形式。

---

<a id="origin-1470"></a>
#### 3.11.2 `.int()`

转为普通整数 Tensor，一般是 int32。

这里用于：

```python
eos_mask.int()
```

方便 `argmax`。

---

<a id="origin-1484"></a>
#### 3.11.3 `.float()`

转成 float32。

例如：

```python
mask.float()
```

把：

```text
True False True
```

变成：

```text
1.0 0.0 1.0
```

---

<a id="origin-1508"></a>
#### 3.11.4 `.bool()`

转成布尔类型。

非 0：

```text
True
```

0：

```text
False
```

---

<a id="origin-1526"></a>
#### 3.11.5 `.half()`

转成 float16。

保存权重时：

```python
v.half().cpu()
```

意思是：

1. 转 FP16；
2. 搬到 CPU；
3. 再保存。

---

<a id="origin-1544"></a>
### 3.12 Tensor 的设备移动

<a id="origin-1546"></a>
#### 3.12.1 `.to(device)`

例如：

```python
tensor.to("cuda:0")
```

把 Tensor 搬到 GPU。

也可以改变 dtype。

模型也可以：

```python
critic_model.to(args.device)
```

---

<a id="origin-1566"></a>
#### 3.12.2 `.cpu()`

把 Tensor 搬回 CPU。

保存权重时可以减少 GPU 占用。

---

<a id="origin-1574"></a>
### 3.13 Tensor 形状操作

<a id="origin-1576"></a>
#### 3.13.1 `.unsqueeze(dim)`

增加一个长度为 1 的维度。

例如：

\[
[R]
\]

```python
unsqueeze(0)
```

变成：

\[
[1,R]
\]

这样才能和：

\[
[B,1]
\]

利用 broadcasting 相加。

---

<a id="origin-1606"></a>
#### 3.13.2 `.squeeze(-1)`

删除最后一个长度为 1 的维度。

Critic：

\[
[B,T,1]
\rightarrow
[B,T]
\]

---

<a id="origin-1620"></a>
#### 3.13.3 `.size(dim)`

取某个维度长度。

```python
resp_labels.size(1)
```

得到：

```text
R
```

---

<a id="origin-1636"></a>
#### 3.13.4 `.clone()`

复制一个 Tensor。

代码：

```python
labels = gen_out[:, 1:].clone()
```

得到独立 Tensor，避免后续修改影响原对象。

---

<a id="origin-1650"></a>
### 3.14 Tensor 的统计 / 聚合

<a id="origin-1652"></a>
#### 3.14.1 `.sum(dim=...)`

求和。

例如：

```python
resp_pad_mask.sum(dim=1)
```

如果：

```text
[1,1,1,0,0]
```

得到：

```text
3
```

即回答真实长度。

---

<a id="origin-1678"></a>
#### 3.14.2 `.mean()`

求平均。

日志里：

```python
rewards.mean()
```

得到当前 batch 平均奖励。

---

<a id="origin-1692"></a>
#### 3.14.3 `.max()` / `.min()`

取最大值和最小值。

调试 ratio 范围时使用。

---

<a id="origin-1700"></a>
#### 3.14.4 `.abs()`

绝对值。

```python
(ratio - 1).abs()
```

表示：

> ratio 偏离 1 有多远。

---

<a id="origin-1714"></a>
#### 3.14.5 `.any(dim=...)`（重点）

只要有一个 True，就返回 True。

例如：

```text
[False, False, True]
```

`.any()`：

```text
True
```

用于判断回答里是否出现 EOS。

---

<a id="origin-1734"></a>
### 3.15 `.gather(...)`：本文件最重要的 Tensor API 之一（重点）

先理解一个例子。

假设 logits：

\[
[B,T,V]
\]

其中最后一维是词表。

某个位置模型对词表给出：

```text
token 0 → -4.0
token 1 → -1.2
token 2 → -0.7
...
```

但真实生成 token 是：

```text
token 2
```

我们只想拿：

```text
-0.7
```

这时用：

```python
.gather(dim=2, index=token_ids)
```

就是：

> 沿词表维度，按照真实 token id 把对应 log probability 拿出来。

代码：

```python
F.log_softmax(logits, dim=-1)
    .gather(2, labels.unsqueeze(-1))
    .squeeze(-1)
```

实现：

\[
[B,T,V]
\rightarrow
[B,T,1]
\rightarrow
[B,T]
\]

然后又：

```python
.gather(1, logp_pos)
```

表示：

> 从完整序列位置中，只拿回答 token 对应的位置。

最终：

\[
[B,R]
\]

---

<a id="origin-1813"></a>
#### 3.15.1 `torch.gather()` 最简单理解

<a id="origin-1815"></a>
##### 3.15.1.1 `gather` 是干什么的？

一句话：

> **按照给定索引，从指定维度里取值。**

---

<a id="origin-1823"></a>
##### 3.15.1.2 最简单的二维例子

假设有一个 Tensor：

```python
x = torch.tensor([
    [10, 20, 30],
    [40, 50, 60]
])
```

它长这样：

```text
[
    [10, 20, 30],
    [40, 50, 60]
]
```

形状：

\[
[2,3]
\]

现在我们想：

```text
第 0 行取下标 2
第 1 行取下标 0
```

也就是想拿：

```text
30
40
```

索引写成：

```python
index = torch.tensor([
    [2],
    [0]
])
```

然后：

```python
y = torch.gather(
    x,
    dim=1,
    index=index
)
```

得到：

```text
[
    [30],
    [40]
]
```

形状：

\[
[2,1]
\]

所以：

```python
torch.gather(x, dim=1, index=index)
```

可以理解成：

> 对每一行，按照 `index` 指定的列号去取值。

---

<a id="origin-1909"></a>
##### 3.15.1.3 再看一个更直观的表格

原来的：

```text
       col0   col1   col2

row0    10     20     30
row1    40     50     60
```

索引：

```text
row0 → 取 col2
row1 → 取 col0
```

所以：

```text
row0 → 30
row1 → 40
```

最终：

```text
[
    [30],
    [40]
]
```

---

<a id="origin-1945"></a>
##### 3.15.1.4 `dim=1` 是什么意思？

原 Tensor：

\[
[2,3]
\]

可以理解成：

```text
dim=0 → 行
dim=1 → 列
```

所以：

```python
gather(dim=1)
```

就是：

> **沿列这个维度，根据索引去取值。**

---

<a id="origin-1972"></a>
##### 3.15.1.5 PPO 里为什么用 `gather`？

语言模型输出的是：

```text
每个位置
对整个词表所有 token 的概率
```

例如某一个位置：

```text
token0 → -4.0
token1 → -1.2
token2 → -0.7
token3 → -2.5
```

但这一位置真实生成的是：

```text
token2
```

所以 PPO 并不需要：

```text
[-4.0, -1.2, -0.7, -2.5]
```

全部概率。

它只需要：

```text
token2 对应的 -0.7
```

于是就可以用：

```python
.gather(...)
```

把真实 token 对应的 log probability 取出来。

---

<a id="origin-2020"></a>
###### 3.15.1.5.1 假设 `log_softmax` 后得到下面这个矩阵

对这一条样本：

```text
                 词表 token

位置          0       1       2       3       4
-------------------------------------------------
t=0         -2.0    -0.5    -3.0    -1.2    -4.0

t=1         -1.5    -2.1    -0.3    -3.5    -2.8

t=2         -4.0    -1.0    -2.0    -0.2    -3.1

t=3         -0.7    -2.5    -1.8    -3.0    -2.2
```

这个矩阵的形状就是：

\[
[T,V]=[4,5]
\]

完整 batch 形状：

\[
[B,T,V]=[1,4,5]
\]

---

<a id="origin-2052"></a>
###### 3.15.1.5.2 这个矩阵到底是什么意思？

例如：

```text
t = 0
```

这一行：

```text
token0 → -2.0
token1 → -0.5
token2 → -3.0
token3 → -1.2
token4 → -4.0
```

表示：

> 在第 0 个预测位置，模型认为下一个 token 属于整个词表中每个 token 的 log probability。

例如：

\[
\log P(token1)=-0.5
\]

而：

\[
\log P(token4)=-4.0
\]

所以模型明显更倾向：

```text
token1
```

---

<a id="origin-2094"></a>
###### 3.15.1.5.3 现在真实 token 是什么？

假设真正的 labels 是：

```text
位置0 → token1
位置1 → token2
位置2 → token3
位置3 → token0
```

所以：

```python
labels = tensor([
    [1, 2, 3, 0]
])
```

形状：

\[
[B,T]=[1,4]
\]

---

<a id="origin-2121"></a>
###### 3.15.1.5.4 我们真正想要的是什么？

虽然每个位置都有：

```text
5 个词表 token 的概率
```

但 PPO 不关心其他 token。

它只关心：

> **这个位置真正生成出来的 token，当时概率是多少？**

所以我们想从上面矩阵中取：

```text
t=0：
真实 token = 1
→ 取 -0.5

t=1：
真实 token = 2
→ 取 -0.3

t=2：
真实 token = 3
→ 取 -0.2

t=3：
真实 token = 0
→ 取 -0.7
```

最终想得到：

```text
[-0.5, -0.3, -0.2, -0.7]
```

---

<a id="origin-2163"></a>
###### 3.15.1.5.5 这就是第一次 `gather`

代码：

```python
F.log_softmax(logits, dim=-1)
    .gather(
        2,
        labels.unsqueeze(-1)
    )
```

先看：

```python
labels
```

原来：

```text
[[1, 2, 3, 0]]
```

形状：

\[
[1,4]
\]

但是 logits 是：

\[
[1,4,5]
\]

`gather(dim=2)` 要沿第 2 维，也就是词表维取值。

所以 index 也要带一个词表索引维。

于是：

```python
labels.unsqueeze(-1)
```

变成：

```text
[
    [
        [1],
        [2],
        [3],
        [0]
    ]
]
```

形状：

\[
[B,T,1]
=
[1,4,1]
\]

---

<a id="origin-2232"></a>
###### 3.15.1.5.6 `gather(dim=2)` 是怎么取的？

因为：

```python
dim=2
```

表示：

> 沿着最后一维，也就是词表 V 维取。

所以：

```text
位置 t=0：
index = 1
→ 在第0行词表中拿 token1

位置 t=1：
index = 2
→ 在第1行词表中拿 token2

位置 t=2：
index = 3
→ 在第2行词表中拿 token3

位置 t=3：
index = 0
→ 在第3行词表中拿 token0
```

所以：

```text
原矩阵：

t=0   [-2.0, -0.5, -3.0, -1.2, -4.0]
              ↑
            取这里


t=1   [-1.5, -2.1, -0.3, -3.5, -2.8]
                     ↑
                   取这里


t=2   [-4.0, -1.0, -2.0, -0.2, -3.1]
                            ↑
                          取这里


t=3   [-0.7, -2.5, -1.8, -3.0, -2.2]
         ↑
       取这里
```

得到：

```text
[
    [
        [-0.5],
        [-0.3],
        [-0.2],
        [-0.7]
    ]
]
```

形状：

\[
[B,T,1]
\]

---

<a id="origin-2310"></a>
###### 3.15.1.5.7 为什么还要 `.squeeze(-1)`？

现在最后一维只是：

```text
1
```

没有实际意义。

所以：

```python
.squeeze(-1)
```

把：

\[
[B,T,1]
\]

变成：

\[
[B,T]
\]

结果：

```text
[
    [-0.5, -0.3, -0.2, -0.7]
]
```

这时候已经完成：

> **每个序列位置，只保留真实 token 的 log probability。**

---

<a id="origin-2352"></a>
###### 3.15.1.5.8 一句话总结

`gather` 最简单的理解就是：

> **我告诉你“沿哪个维度”，再告诉你“每个位置要取哪个下标”，你就把对应值拿出来。**

在 PPO 中：

```text
第一次 gather
→ 从整个词表中取真实生成 token 的 log probability

第二次 gather
→ 从整个序列中只保留 Response 部分
```

最终得到：

\[
\boxed{
[B,R]
}
\]

也就是：

> **每条回答每个 token 对应的 log probability。**

---

<a id="origin-2382"></a>
### 3.16 `F.log_softmax`

假设 logits：

```text
[2.0, 1.0, 0.0]
```

softmax 得概率：

```text
[0.665, 0.245, 0.090]
```

log_softmax 得：

```text
[-0.408, -1.408, -2.408]
```

为什么 PPO 喜欢 log probability？

因为：

\[
\frac{p_{\text{new}}}{p_{\text{old}}}
\]

可以写成：

\[
\exp(
\log p_{\text{new}}
-
\log p_{\text{old}}
)
\]

数值更稳定。

---

<a id="origin-2424"></a>
### 3.17 `.detach()`

切断梯度历史。

例如：

```python
approx_kl.detach()
```

表示：

> 我只想拿它的数值做日志/判断，不希望这条分支继续进入反向传播。

---

<a id="origin-2440"></a>
### 3.18 `.item()`

把单元素 Tensor 变成 Python 数值。

例如：

```python
loss.item()
```

用于：

- 打日志；
- 格式化输出；
- 存 Python 变量。

注意：

> `.item()` 之后不再是计算图里的 Tensor。

---

<a id="origin-2462"></a>
### 3.19 `loss.backward()`

反向传播核心。

它根据当前 loss，计算：

\[
\frac{\partial L}{\partial \theta}
\]

并把梯度累加到：

```python
parameter.grad
```

注意：

```python
backward()
```

**不会立刻更新参数。**

真正更新是：

```python
optimizer.step()
```

---

<a id="origin-2494"></a>
### 3.20 `optim.AdamW`

```python
optim.AdamW(model.parameters(), lr=...)
```

建立 AdamW 优化器。

它根据：

```text
parameter.grad
```

修改参数。

简化理解：

\[
\theta
\leftarrow
\theta
-
\eta \cdot \text{AdamWAdjustedGradient}
\]

Actor 和 Critic 使用不同 optimizer：

```text
Actor Optimizer
Critic Optimizer
```

所以它们可以使用不同学习率。

---

<a id="origin-2531"></a>
### 3.21 `optimizer.step()`

真正执行参数更新。

```python
actor_optimizer.step()
critic_optimizer.step()
```

---

<a id="origin-2542"></a>
### 3.22 `optimizer.zero_grad()`

清掉已经累积的梯度。

为什么必须清？

PyTorch 默认：

> `.backward()` 的梯度是累加，不是覆盖。

---

<a id="origin-2554"></a>
### 3.23 `clip_grad_norm_`

代码：

```python
clip_grad_norm_(
    actor_model.parameters(),
    args.grad_clip
)
```

计算所有参数梯度的整体范数。

如果太大，就统一缩小。

例如原梯度向量范数：

\[
10
\]

最大允许：

\[
1
\]

就整体大约乘：

\[
0.1
\]

作用：

> 防止一次异常梯度导致模型参数大幅跳动。

---

<a id="origin-2593"></a>
### 3.24 `CosineAnnealingLR`

余弦学习率调度器。

学习率从较高值逐渐降到：

```python
eta_min
```

大致形式：

\[
\eta_t
=
\eta_{\min}
+
\frac{1}{2}
(\eta_{\max}-\eta_{\min})
\left(
1+\cos\frac{\pi t}{T_{\max}}
\right)
\]

---

<a id="origin-2619"></a>
#### 3.24.1 `scheduler.step()`

让学习率调度器向前走一步。

---

<a id="origin-2625"></a>
### 3.25 AMP：`torch.cuda.amp.autocast`

```python
with torch.cuda.amp.autocast(dtype=dtype):
    ...
```

允许某些 GPU 运算自动使用：

- FP16；
- BF16；

从而：

- 降低显存；
- 加速 Tensor Core 运算。

注意：

> autocast 不等于“整个模型永久转换成 FP16”。

它主要影响上下文中具体运算使用的计算精度。

---

<a id="origin-2650"></a>
### 3.26 `torch.cuda.is_available()`

判断 CUDA GPU 是否可用。

```python
"cuda:0" if torch.cuda.is_available() else "cpu"
```

---

<a id="origin-2660"></a>
### 3.27 模型状态 API

<a id="origin-2662"></a>
#### 3.27.1 `model.train()`

进入训练模式。

主要影响：

- Dropout；
- BatchNorm 等。

---

<a id="origin-2673"></a>
#### 3.27.2 `model.eval()`

进入推理模式。

注意：

> `eval()` 不会自动关闭梯度。

所以 Reference Model 又调用：

```python
.requires_grad_(False)
```

---

<a id="origin-2689"></a>
#### 3.27.3 `.requires_grad_(False)`

把模型参数设置成：

```text
不需要梯度
```

Reference Model 因此不会被训练。

---

<a id="origin-2701"></a>
#### 3.27.4 `.parameters()`

返回模型中可训练参数的迭代器。

给：

- optimizer；
- grad clipping；

使用。

---

<a id="origin-2714"></a>
#### 3.27.5 `.state_dict()`

得到模型参数和 buffer 的字典。

类似：

```python
{
    "model.layers.0....weight": tensor(...),
    ...
}
```

---

<a id="origin-2729"></a>
#### 3.27.6 `.load_state_dict(...)`

把保存的参数装回模型。

这里：

```python
critic_model.load_state_dict(
    state_dict,
    strict=False
)
```

因为 Critic 比 Actor 多了：

```text
value_head
```

`strict=False` 允许：

- checkpoint 没有 value_head；
- 模型存在额外参数。

但是要注意：

> `strict=False` 并不代表所有形状错误都会被忽略；同名参数尺寸不匹配通常仍会报错。

---

<a id="origin-2759"></a>
### 3.28 `torch.load`

读取 PyTorch 保存对象。

```python
state_dict = torch.load(...)
```

---

<a id="origin-2769"></a>
### 3.29 `torch.save`

保存 Python / Tensor 对象。

代码保存：

```python
{
    parameter_name: fp16_cpu_tensor
}
```

注意：

> 保存 `state_dict` 不等于把整个 Python 模型结构一起保存；加载时还要先构建匹配的模型。

---

<a id="origin-2787"></a>
### 3.30 `torch.compile`

PyTorch 2.x 的图编译优化。

```python
actor_model = torch.compile(actor_model)
```

它尝试把可编译的计算图优化成更高效执行版本。

代价：

- 第一次运行有编译成本；
- 动态 Python 控制流可能造成 graph break。

---

<a id="origin-2804"></a>
### 3.31 DDP：分布式训练

<a id="origin-2806"></a>
#### 3.31.1 `dist.is_initialized()`

判断 PyTorch distributed 是否已经初始化。

---

<a id="origin-2812"></a>
#### 3.31.2 `dist.get_rank()`

获取当前进程编号：

```text
rank 0
rank 1
rank 2
...
```

---

<a id="origin-2825"></a>
#### 3.31.3 `DistributedDataParallel`

```python
DistributedDataParallel(
    model,
    device_ids=[local_rank]
)
```

典型思想：

```text
GPU0：一份模型 + 一部分数据
GPU1：一份模型 + 一部分数据
GPU2：一份模型 + 一部分数据
...
```

反向传播时同步梯度。

---

<a id="origin-2847"></a>
#### 3.31.4 `.module`

DDP 包装后：

```python
ddp_model.module
```

才是原始模型。

所以源码经常写：

```python
model.module if isinstance(model, DDP) else model
```

---

<a id="origin-2865"></a>
#### 3.31.5 `dist.all_reduce(..., op=AVG)`（重点）

把所有 GPU 上的值做集合通信。

这里用于同步：

```text
approx_kl
```

为什么？

因为如果：

```text
GPU0：KL 太大 → break
GPU1：KL 不大 → 继续 backward
```

DDP 的 collective 次数不一致，可能死锁。

所以必须让所有 rank 对“是否 early stop”得到一致判断。

<a id="origin-2888"></a>
#### 3.31.6 Early Stop 后是不是就该更新 Policy 了？

源码中有：

```python
log_ratio = mb_resp_logp - old_resp_logp[inds]

approx_kl = (
    0.5 * (log_ratio ** 2) * resp_policy_mask[inds]
).sum() / resp_policy_mask[inds].sum().clamp(min=1)

approx_kl_val = approx_kl.detach().clone()

if dist.is_initialized():
    dist.all_reduce(
        approx_kl_val,
        op=dist.ReduceOp.AVG
    )

if approx_kl_val > args.early_stop_kl:
    stop_ppo = True
```

这里最容易产生一个误解：

> `Early Stop` 是不是意味着“现在该更新 Policy 了”？

更准确地说：

> **Policy 在前面的 PPO mini-batch 中其实已经更新过了。**
>
> Early Stop 的意思是：
>
> **这个 Policy 已经相对于生成当前 rollout 的 Old Policy 改得够多了，所以不要再拿这批旧 rollout 继续更新它了。**

然后应该进入：

```text
新的 Prompt / 新的 rollout
↓
让新的 Policy 重新生成数据
↓
这些新数据对应的 Policy
又成为下一批的 Old Policy
```

---

<a id="origin-2936"></a>
##### 3.31.6.1 先看一批 PPO 数据是怎么来的

假设当前 Actor 是：

```text
Policy v0
```

它先生成一批回答：

```text
Policy v0
   ↓
Rollout
   ↓
Response
```

同时保存：

```text
old_resp_logp
```

因此：

\[
\boxed{
\text{这一批数据的 Old Policy}
=
\text{Policy v0}
}
\]

---

<a id="origin-2972"></a>
##### 3.31.6.2 然后才开始 PPO Update

假设：

```python
ppo_update_iters = 4
```

意思是：

> 原计划用这一批 rollout，最多重复训练 4 轮。

开始时：

```text
Old Policy = v0
Current Actor = v0
```

所以：

\[
ratio
\approx
1
\]

\[
approx\_kl
\approx
0
\]

---

<a id="origin-3007"></a>
##### 3.31.6.3 第一轮 PPO Update 后，Policy 已经变了

例如：

```text
开始：

Policy v0
```

经过：

```python
loss.backward()
actor_optimizer.step()
```

之后变成：

```text
Policy v1
```

注意：

> **这里就已经完成了一次 Policy 更新。**

不是等到 Early Stop 才更新。

---

<a id="origin-3038"></a>
##### 3.31.6.4 但是 Old Policy 仍然是 v0

虽然当前 Actor 已经变成：

```text
v1
```

但是：

```python
old_resp_logp
```

不会重新计算。

它仍然记录：

> 当初 `v0` 生成这批 Response 时的概率。

所以：

```text
Old Policy     = v0
Current Policy = v1
```

现在就可以比较：

\[
\pi_{v1}
\]

和：

\[
\pi_{v0}
\]

---

<a id="origin-3079"></a>
##### 3.31.6.5 第二轮又继续更新

继续使用同一批 rollout：

```text
Policy v1
↓
PPO Update
↓
Policy v2
```

但 Old Policy 仍然：

```text
v0
```

所以现在比较的是：

\[
v2
\quad vs \quad
v0
\]

随着不断更新：

```text
v0 → v1 → v2 → v3
```

Current Policy 会越来越远离：

```text
Old Policy v0
```

---

<a id="origin-3119"></a>
##### 3.31.6.6 `approx_kl` 就是在检测“已经离 v0 多远”

代码：

```python
log_ratio = mb_resp_logp - old_resp_logp
```

比较：

```text
当前 Policy
vs
生成这批数据时的 Old Policy
```

然后：

\[
approx\_kl
=
\operatorname{mean}
\left[
\frac12
(\log\pi_{\text{new}}
-
\log\pi_{\text{old}})^2
\right]
\]

它可以理解成：

> **当前 Policy 已经离生成这批 rollout 的 Policy 有多远。**

---

<a id="origin-3155"></a>
##### 3.31.6.7 举一个完整过程

假设：

```text
ppo_update_iters = 4

early_stop_kl = 0.25
```

一开始：

```text
Old Policy = v0
Current    = v0
```

---

<a id="origin-3174"></a>
###### 3.31.6.7.1 第 1 轮

```text
v0
↓
PPO Update
↓
v1
```

假设：

```text
approx KL(v1, v0) = 0.05
```

还很小：

```text
0.05 < 0.25
```

所以：

```text
继续
```

---

<a id="origin-3204"></a>
###### 3.31.6.7.2 第 2 轮

```text
v1
↓
继续 PPO
↓
v2
```

得到：

```text
approx KL(v2, v0) = 0.14
```

仍然：

```text
0.14 < 0.25
```

继续。

---

<a id="origin-3230"></a>
###### 3.31.6.7.3 第 3 轮

```text
v2
↓
继续 PPO
↓
v3
```

现在：

```text
approx KL(v3, v0) = 0.31
```

超过：

```text
early_stop_kl = 0.25
```

于是：

```text
Early Stop
```

---

<a id="origin-3260"></a>
##### 3.31.6.8 Early Stop 到底停止什么？

它不是：

```text
停止整个 PPO 训练
```

也不是：

```text
把已经更新出来的 v3 丢掉
```

更不是：

```text
现在才开始更新 Policy
```

而是：

> **停止继续使用“v0 生成的这一批 rollout”训练当前 Policy。**

也就是说原本：

```text
第1轮 ✓
第2轮 ✓
第3轮 ✓
第4轮
```

变成：

```text
第1轮 ✓
第2轮 ✓
第3轮 ✓

KL 太大
↓
Early Stop

第4轮 ✗
```

当前 Actor 保留：

```text
Policy v3
```

---

<a id="origin-3315"></a>
##### 3.31.6.9 为什么这时候应该换一批新的 rollout？

因为当前数据是：

```text
Policy v0
```

生成的。

但是模型已经变成：

```text
Policy v3
```

如果还继续拿：

```text
v0 生成的数据
```

训练：

```text
v3
```

那么数据就越来越：

```text
off-policy
```

即：

> 数据产生时的策略，与当前正在训练的策略已经相差太大。

所以更加合理的流程是：

```text
Old Policy v0
↓
生成 Rollout A
↓
PPO 更新
↓
v1
↓
PPO 更新
↓
v2
↓
PPO 更新
↓
v3

发现 KL(v3,v0) 太大
↓
Early Stop
↓
不要继续使用 Rollout A
↓
用新的 Policy 再生成新 Rollout
```

---

<a id="origin-3383"></a>
##### 3.31.6.10 下一批 Rollout 到来以后，谁成为新的 Old Policy？

假设新的 rollout 是由：

```text
Policy v3
```

生成的。

那么：

```text
Policy v3
↓
生成 Rollout B
↓
保存这次生成时的 log probability
```

这些 log probability 就成为：

```python
old_resp_logp
```

于是：

\[
\boxed{
\text{下一批数据的 Old Policy}
=
v3
}
\]

然后又可以开始新的 PPO 更新：

```text
Old = v3
Current = v3

↓ PPO

v4

↓ PPO

v5

↓ KL 太大

Early Stop

↓ 新 Rollout
```

---

<a id="origin-3442"></a>
##### 3.31.6.11 所以 PPO 实际上是不断重复这个循环

```text
================ 第 1 批 ================

Policy v0
   ↓
Rollout
   ↓
Old Policy = v0
   ↓
PPO Update
   ↓
v1
   ↓
PPO Update
   ↓
v2
   ↓
KL 太大
   ↓
Early Stop


================ 第 2 批 ================

Policy v2
   ↓
重新 Rollout
   ↓
Old Policy = v2
   ↓
PPO Update
   ↓
v3
   ↓
PPO Update
   ↓
v4
   ↓
KL 太大
   ↓
Early Stop


================ 第 3 批 ================

Policy v4
   ↓
重新 Rollout
   ↓
...
```

所以：

\[
\boxed{
\text{Old Policy 不是永久固定的}
}
\]

而是：

> **每次重新 rollout 时，负责产生这批数据的 Policy。**

---

<a id="origin-3510"></a>
##### 3.31.6.12 所以 Early Stop 可以理解成：“该换新数据了”

这是最容易理解的方式。

Early Stop 实际在说：

> **当前 Policy 已经和生成这批数据的 Policy 差得比较远了。**
>
> **这批 rollout 已经被利用得差不多了，不要再榨它了。**
>
> **应该进入后面的 rollout，用较新的 Policy 产生新数据。**

因此可以简单记成：

```text
KL 小
↓
Old rollout 还比较“新鲜”
↓
可以继续 PPO


KL 太大
↓
Old rollout 已经比较“过时”
↓
Early Stop
↓
换新 rollout
```

---

<a id="origin-3543"></a>
##### 3.31.6.13 但是要特别区分“更新 Actor 参数”和“同步 Rollout Policy”

在源码里真正修改 Actor 参数的是：

```python
actor_optimizer.step()
```

所以：

```text
PPO mini-batch
↓
backward
↓
optimizer.step
↓
Actor 参数已经更新
```

---

但是如果：

```text
Rollout Engine
```

内部维护了一份独立的 Policy 副本，那么还需要：

```python
rollout_engine.update_policy(actor_model)
```

把新的 Actor 参数同步过去。

也就是说：

```text
Actor 参数更新
```

和：

```text
Rollout Engine 中的 Policy 同步
```

是两个不同概念。

---

<a id="origin-3595"></a>
##### 3.31.6.14 当前这份代码什么时候调用 `update_policy()`？

源码中训练过程中有：

```python
if step % args.save_interval == 0 or step == iters:
    rollout_engine.update_policy(actor_model)
```

也就是说：

> 从当前文件能够明确看到的是，Rollout Engine 会在指定间隔或当前 epoch 最后一个 step 同步 Actor。

因此不能简单说：

```text
Early Stop
↓
立刻调用 update_policy()
```

因为当前源码并不是这么写的。

更准确地说：

> **Early Stop 表示停止当前 rollout 的继续 PPO 更新；Actor 本身已经通过 optimizer.step() 更新。至于 rollout engine 什么时候拿到最新 Actor，则由 `update_policy()` 的调用时机决定。**

---

<a id="origin-3624"></a>
##### 3.31.6.15 现在再看 `dist.all_reduce(..., AVG)` 就非常清楚了

每张 GPU 会自己算：

```text
Current Policy
vs
Old Policy
```

之间的：

```text
local approx KL
```

例如：

```text
GPU0：

KL = 0.30


GPU1：

KL = 0.10
```

如果：

```text
threshold = 0.25
```

没有同步的话：

```text
GPU0：
认为这批 rollout 已经过时
→ Early Stop


GPU1：
认为还能继续训练
→ 继续 PPO
```

这样 DDP 就会出现控制流不一致。

---

<a id="origin-3676"></a>
##### 3.31.6.16 所以先执行

```python
dist.all_reduce(
    approx_kl_val,
    op=dist.ReduceOp.AVG
)
```

得到：

\[
\frac{0.30+0.10}{2}
=
0.20
\]

然后：

```text
GPU0 → KL = 0.20
GPU1 → KL = 0.20
```

所有 GPU 一起判断：

```text
这批 rollout
还能不能继续用？
```

---

<a id="origin-3709"></a>
##### 3.31.6.17 最后的完整流程

```text
Current Actor
      │
      ▼
生成一批 Rollout
      │
      ▼
保存生成时的 old_logp
      │
      ▼

这时：
Old Policy = 当前 Actor

      │
      ▼
PPO Update
      │
      ▼
Actor 参数发生变化
      │
      ▼
再 PPO Update
      │
      ▼
Actor 继续变化
      │
      ▼

计算：

Current Actor
vs
Old Policy

      │
      ▼
approx_kl
      │
      ▼

多 GPU：

all_reduce AVG

      │
      ▼
得到 Global Approx KL
      │
      ▼

KL 是否太大？

   ┌───────┴───────┐
   │               │
   否              是
   │               │
   ▼               ▼

继续使用          Early Stop
当前 rollout          │
继续 PPO              │
                      ▼
                不再继续使用
                 这批旧 rollout
                      │
                      ▼
                 进入后续数据
                 /新的 Rollout
                      │
                      ▼
               新 Policy 产生新数据
                      │
                      ▼
               它又成为新的
                  Old Policy
```

---

<a id="origin-3791"></a>
##### 3.31.6.18 一句话总结 Early Stop

\[
\boxed{
\text{Early Stop}
=
\text{当前 Policy 已经相对 Old Policy 改得够多了，
停止继续利用这批 rollout}
}
\]

它不是：

```text
现在才更新 Policy
```

而是：

```text
Policy 已经更新了一些
↓
发现离 Old Policy 太远
↓
别再用旧 rollout 继续更新
↓
进入新的 rollout 周期
```

因此可以概括为：

> **PPO 的 Early Stop 本质上是在判断：“当前这批 rollout 还能不能继续用？”如果 Current Policy 已经离产生这批数据的 Old Policy 太远，就停止继续训练这批数据，转向后续的新 rollout，让新的策略重新产生更匹配当前 Policy 的训练数据。**

---

<a id="origin-3826"></a>
#### 3.31.7 `dist.all_reduce(..., op=AVG)`（重点）：这里的 KL 到底是什么？

源码中有：

```python
log_ratio = mb_resp_logp - old_resp_logp[inds]

approx_kl = (
    0.5 * (log_ratio ** 2) * resp_policy_mask[inds]
).sum() / resp_policy_mask[inds].sum().clamp(min=1)

approx_kl_val = approx_kl.detach().clone()

if dist.is_initialized():
    dist.all_reduce(
        approx_kl_val,
        op=dist.ReduceOp.AVG
    )

if approx_kl_val > args.early_stop_kl:
    stop_ppo = True
```

看到这里很容易产生一个疑问：

> **PPO / RLHF 里面不是 Reference Model 才需要计算 KL 吗？为什么这里 Old Policy 也出现了一个 `approx_kl`？**

答案是：

> **这里实际上存在两种完全不同用途的“KL”。**

一定要分开。

---

<a id="origin-3861"></a>
##### 3.31.7.1 先给结论：代码里有两种 KL

| 名称 | 比较对象 | 主要作用 | 是否直接加入 Actor Loss |
|---|---|---|---|
| `approx_kl` | Current Actor vs Old Policy | 监控这一批 PPO 更新是不是走得太远，做 Early Stop | 否 |
| `kl_ref_penalty` | Current Actor vs Reference Model | 防止强化学习长期把 Actor 带离原始 SFT 模型 | 是 |

因此可以概括为：

> **“PPO 里面不是 Ref Model 才使用 KL 吗？”**

如果指的是：

> **RLHF 中那个作为训练正则项、真正惩罚 Actor 偏离原始模型的 KL**

那么是对的。

那个 KL 是：

```text
Current Actor
    vs
Reference Model
```

而这里的：

```python
approx_kl
```

是另外一个东西：

```text
Current Actor
    vs
Old Policy
```

它主要只是一个：

> **策略更新幅度监控指标。**

---

<a id="origin-3906"></a>
##### 3.31.7.2 先重新区分 Old Policy 和 Reference Model

这是理解两个 KL 的关键。

<a id="origin-3910"></a>
###### 3.31.7.2.1 Old Policy

Old Policy 是：

> **生成当前这批 rollout 数据时的 Actor。**

例如：

```text
Actor v0
↓
生成一批 Response
↓
保存 old_resp_logp
```

那么对于这一批数据：

```text
Old Policy = Actor v0
```

随后 PPO 更新：

```text
Actor v0
↓
Actor v1
↓
Actor v2
```

但是：

```text
old_resp_logp
```

一直保存的还是：

```text
Actor v0 生成这批 token 时的概率
```

---

<a id="origin-3956"></a>
###### 3.31.7.2.2 Reference Model

Reference Model 则是：

> **训练开始时冻结下来的原始模型，通常就是 SFT 模型。**

例如：

```text
               SFT Model
                /     \
               /       \
              ▼         ▼

           Actor       Ref Model
             │             │
             │             │
        不断 PPO 更新      永远冻结
```

所以：

```text
Old Policy
=
每一批 rollout 都会重新定义

Reference Model
=
整个 PPO 训练过程中基本一直不变
```

---

<a id="origin-3990"></a>
##### 3.31.7.3 为什么两者都可以出现“KL”？

因为 KL 本质上只是：

> **衡量两个概率分布差异有多大的数学工具。**

所以理论上只要有：

```text
概率分布 A
vs
概率分布 B
```

都可以计算 KL。

因此：

```text
New Policy vs Old Policy
```

可以算 KL。

同时：

```text
Current Actor vs Reference Model
```

当然也可以算 KL。

关键不在于：

> “KL 只能给谁用？”

而在于：

> **这两个 KL 各自拿来干什么。**

---

<a id="origin-4032"></a>
##### 3.31.7.4 第一种：New Policy vs Old Policy 的 `approx_kl`

这就是当前：

```python
dist.all_reduce(...)
```

前面的那个 KL。

代码：

```python
log_ratio = (
    mb_resp_logp
    -
    old_resp_logp[inds]
)
```

其中：

```text
mb_resp_logp
=
当前正在 PPO 更新的 Actor
对已经生成 token 的 log probability


old_resp_logp
=
这些 token 当初 rollout 出来时
Actor 的 log probability
```

所以：

\[
\text{log\_ratio}_t
=
\log \pi_{\text{new}}(a_t|s_t)
-
\log \pi_{\text{old}}(a_t|s_t)
\]

也就是：

\[
\text{log\_ratio}_t
=
\log
\frac{
\pi_{\text{new}}(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

---

<a id="origin-4092"></a>
##### 3.31.7.5 它和 PPO 的 Ratio 本来就是一家的

PPO 最核心的公式里面本来就有：

\[
r_t(\theta)
=
\frac{
\pi_{\text{new}}(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

代码：

```python
ratio = torch.exp(log_ratio)
```

因为：

\[
e^{
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
}
=
\frac{
\pi_{\text{new}}
}{
\pi_{\text{old}}
}
\]

所以：

```text
Old vs New
```

本来就是 PPO 自身必须比较的两套策略。

---

<a id="origin-4138"></a>
##### 3.31.7.6 PPO 为什么要关心 New 和 Old 差多远？

因为 PPO 的思想就是：

> **同一批 rollout 可以反复训练几次，但是 Current Actor 不能离产生这批数据的 Old Policy 太远。**

例如：

```text
第 0 次：

Old Policy = Current Actor

ratio ≈ 1
```

第一次更新：

```text
Current Actor 稍微变化

ratio ≈ 1.05
```

第二次更新：

```text
Current Actor 再变化

ratio ≈ 1.12
```

如果一直训练：

```text
ratio = 2.5
```

说明：

> 当前 Actor 已经和生成这批数据时的策略差得非常远。

这时继续拿：

```text
Old Policy 生成的旧数据
```

训练 Current Actor，就越来越不可靠。

所以必须：

```text
走太远
↓
停止继续利用这批 rollout
```

---

<a id="origin-4198"></a>
##### 3.31.7.7 所以代码额外计算了 `approx_kl`

源码：

```python
approx_kl = (
    0.5 * (log_ratio ** 2)
    * resp_policy_mask[inds]
).sum() / resp_policy_mask[inds].sum().clamp(min=1)
```

核心就是：

\[
\boxed{
\text{approx\_kl}
=
\operatorname{mean}
\left[
\frac12
(
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
)^2
\right]
}
\]

---

<a id="origin-4229"></a>
##### 3.31.7.8 这个是不是理论公式里的 KL？

<a id="origin-4231"></a>
###### 3.31.7.8.1 有关系，但不是直接精确计算完整 KL

经典 KL：

\[
D_{KL}(P\|Q)
=
\sum_x
P(x)
\log
\frac{P(x)}{Q(x)}
\]

例如语言模型下一 token：

```text
            北京    上海    广州

Old         0.6     0.3     0.1

New         0.5     0.3     0.2
```

完整 KL 要把：

```text
北京
上海
广州
……
整个词表
```

全部考虑进去。

---

但是这份 PPO 代码主要拿的是：

> **真正 rollout 出来的 token 的 log probability。**

例如实际生成：

```text
“北京”
```

只比较：

\[
\log P_{\text{new}}(\text{北京})
\]

和：

\[
\log P_{\text{old}}(\text{北京})
\]

然后利用：

\[
\frac12
(\log ratio)^2
\]

作为策略变化幅度的一个近似指标。

所以它叫：

```python
approx_kl
```

即：

```text
approximate KL
```

---

<a id="origin-4313"></a>
##### 3.31.7.9 为什么这种东西可以用来监控 KL？

当：

```text
New Policy
```

和：

```text
Old Policy
```

比较接近时：

\[
\log
\frac{
\pi_{\text{new}}
}{
\pi_{\text{old}}
}
\]

是一个比较小的量。

在这种“小变化”情况下，可以使用二阶近似来衡量策略变化：

\[
\boxed{
\frac12
(\log ratio)^2
}
\]

所以这里不是：

> 精确计算完整 KL。

而是：

> **使用一个 KL-like 的二阶近似量监控 New/Old Policy 的距离。**

---

<a id="origin-4359"></a>
##### 3.31.7.10 一个简单数值例子

假设 rollout 时某 token：

\[
P_{\text{old}}=0.20
\]

那么：

\[
\log P_{\text{old}}
=
\log 0.20
\approx
-1.609
\]

PPO 更新以后：

\[
P_{\text{new}}=0.25
\]

那么：

\[
\log P_{\text{new}}
=
\log 0.25
\approx
-1.386
\]

所以：

\[
log\_ratio
=
-1.386-(-1.609)
\]

\[
=
0.223
\]

于是：

\[
approx\_kl
=
\frac12
(0.223)^2
\]

\[
\approx
0.0249
\]

可以把它理解成：

> 当前策略相对 Old Policy 已经移动了一点距离。

---

<a id="origin-4426"></a>
##### 3.31.7.11 为什么已经有 PPO Clip，还需要 `approx_kl`？

因为两者解决的层次不完全一样。

PPO Clip：

\[
\operatorname{clip}
(
ratio,
1-\epsilon,
1+\epsilon
)
\]

主要是在：

> **Policy Loss 中限制每个动作的概率比变化。**

例如：

```text
ratio = 1.8

clip epsilon = 0.2
```

那么 surrogate objective 中只按照：

```text
1.2
```

附近处理。

---

而：

```python
approx_kl
```

是在看：

> **这一整轮 PPO 更新以后，New Policy 总体是不是已经离 Old Policy 太远了。**

所以可以理解成两层保护：

```text
PPO Clip
    ↓
局部限制每个 token 的更新


Approx KL
    ↓
整体监控这一批 PPO Update 是否已经走太远
```

如果 KL 太大：

```text
直接 Early Stop
```

---

<a id="origin-4494"></a>
##### 3.31.7.12 第二种：Current Actor vs Reference Model 的 KL

这体现了：

> **RLHF 里面 Ref Model 那个 KL。**

源码中还有：

```python
kl_ref_penalty = (
    torch.exp(
        ref_resp_logp[inds]
        - mb_resp_logp
    )
    -
    (
        ref_resp_logp[inds]
        - mb_resp_logp
    )
    -
    1.0
)
```

然后：

```python
policy_loss = (
    PPO_clip_loss
    +
    args.kl_coef * kl_ref_penalty
)
```

也就是说：

\[
\boxed{
L_{\text{Actor}}
=
L_{\text{PPO}}
+
\beta L_{\text{KL-ref}}
}
\]

---

<a id="origin-4542"></a>
##### 3.31.7.13 Reference KL 是真正加入 Loss 的

它的作用是：

> **防止 Actor 为了 Reward，长期训练以后偏离原始 SFT 模型太远。**

例如：

```text
Reference Model：

北京 0.50
上海 0.25
广州 0.15
```

经过很多轮 PPO：

```text
Actor：

北京 0.95
上海 0.02
广州 0.01
```

虽然：

```text
每一次 New vs Old
```

可能都只走了一小步，

但累积很多次以后：

```text
Current Actor
```

还是可能已经离：

```text
Reference Model
```

非常远。

所以 Reference Model 相当于：

> **长期锚点。**

---

<a id="origin-4596"></a>
##### 3.31.7.14 两种 KL 最大的区别：一个管“这一小步”，一个管“长期漂移”

可以这样理解：

```text
                         Reference Model
                              ▲
                              │
                       KL Ref Penalty
                              │
                   防止长期越来越远
                              │
                              │
Old Policy  ◄────────── Current Actor
    ▲
    │
 Approx KL
    │
限制当前这一轮
不要离 Old Policy 太远
```

---

<a id="origin-4620"></a>
##### 3.31.7.15 `approx_kl` 不直接参与梯度优化

这一点非常重要。

代码：

```python
approx_kl_val = approx_kl.detach().clone()
```

然后：

```python
if approx_kl_val > args.early_stop_kl:
    stop_ppo = True
```

也就是说：

```text
approx_kl

不是：

“KL 大，所以通过这个 KL Loss
直接反向传播把 Actor 拉回来。”
```

而是：

```text
KL 大
↓
说明当前这批 rollout 已经被训练得太狠了
↓
不要继续训练了
↓
Early Stop
```

所以它更像：

> **仪表盘上的警报器。**

---

<a id="origin-4666"></a>
##### 3.31.7.16 Reference KL 则直接参加 Actor Loss

Reference KL：

```python
args.kl_coef * kl_ref_penalty
```

是：

```text
真正加到 policy_loss 中
```

所以它会：

```text
KL Ref 越大
↓
Actor Loss 越大
↓
反向传播
↓
产生梯度
↓
把 Actor 往 Reference 附近拉
```

这是一个真正的：

> **训练正则项。**

---

<a id="origin-4700"></a>
##### 3.31.7.17 所以“PPO 里面 Ref Model 才用 KL”该怎么准确表达？

最准确的说法应该是：

> **在 LLM PPO / RLHF 中，我们通常说的“KL Penalty”主要指 Current Actor 和 Reference Model 之间的 KL，它作为正则项限制 Actor 长期偏离 SFT 模型。**

但是：

> **PPO 实现中还经常计算 Current Actor 和 Old Policy 之间的 approximate KL，用来监控当前 PPO 更新步幅，必要时 Early Stop。**

所以：

```text
Reference KL
=
训练惩罚项


Old/New Approx KL
=
训练过程监控指标
```

这是两回事。

---

<a id="origin-4727"></a>
##### 3.31.7.18 那 `approx_kl_val` 又是什么？

代码：

```python
approx_kl_val = approx_kl.detach().clone()
```

这里：

```python
approx_kl
```

本来来自：

```text
Actor
↓
logits
↓
log probability
↓
log_ratio
↓
approx_kl
```

所以它属于当前计算图。

但是 Early Stop 只是要判断：

```text
这个数字是不是 > threshold？
```

根本不需要梯度。

所以：

```python
detach()
```

表示：

> **把它从梯度计算图中切下来。**

---

<a id="origin-4777"></a>
##### 3.31.7.19 为什么还要 `clone()`？

因为后面：

```python
dist.all_reduce(
    approx_kl_val,
    ...
)
```

会：

> **原地修改这个 Tensor。**

所以：

```python
clone()
```

创建一份独立副本。

因此：

```python
approx_kl_val
```

可以理解成：

> **从 `approx_kl` 复制出来、专门用于 DDP 同步和 Early Stop 判断的数值版本。**

这里的：

```text
val
```

就是：

```text
value
```

不是 Critic 的 Value。

---

<a id="origin-4826"></a>
##### 3.31.7.20 三个变量的关系

```text
log_ratio
    ↓
New Policy 和 Old Policy
单个 token 的 log probability 差
```

然后：

```text
0.5 × log_ratio²
    ↓
每个 token 的近似策略变化量
```

再：

```text
对当前 GPU 的有效 token 求平均
    ↓
approx_kl
```

最后：

```text
detach().clone()
    ↓
approx_kl_val
```

所以：

| 变量 | 含义 |
|---|---|
| `log_ratio` | 每个 token 上 New 和 Old 的 log 概率差 |
| `approx_kl` | 当前 GPU 当前 mini-batch 的平均近似 KL |
| `approx_kl_val` | 脱离计算图后、用于同步和 Early Stop 的数值副本 |

---

<a id="origin-4869"></a>
##### 3.31.7.21 为什么接下来需要 `dist.all_reduce(..., AVG)`？

假设有两张 GPU。

DDP 会让不同 GPU 处理不同的数据：

```text
GPU0：
样本 A、B

GPU1：
样本 C、D
```

所以各自算出的：

```python
approx_kl
```

可能不同。

例如：

```text
GPU0：

approx_kl = 0.30


GPU1：

approx_kl = 0.10
```

于是各自：

```python
approx_kl_val = approx_kl.detach().clone()
```

以后：

```text
GPU0：
approx_kl_val = 0.30

GPU1：
approx_kl_val = 0.10
```

---

<a id="origin-4922"></a>
##### 3.31.7.22 如果让每张 GPU 自己判断会发生什么？

假设：

```text
early_stop_kl = 0.25
```

那么：

```text
GPU0：

0.30 > 0.25
↓
停止 PPO
```

但是：

```text
GPU1：

0.10 < 0.25
↓
继续 PPO
```

于是：

```text
GPU0：
不再进行下一轮 backward


GPU1：
继续 loss.backward()
```

这在 DDP 中非常危险。

---

<a id="origin-4965"></a>
##### 3.31.7.23 为什么会危险？

因为 DDP 的：

```python
loss.backward()
```

不仅仅是在一张 GPU 上自己计算梯度。

它还会自动进行：

```text
GPU0 gradient
        \
         \
          → all_reduce → 平均梯度

         /
GPU1 gradient
```

例如：

```text
GPU0：

gradient = 2


GPU1：

gradient = 4
```

DDP 会同步：

\[
\frac{2+4}{2}=3
\]

然后：

```text
GPU0：
gradient = 3

GPU1：
gradient = 3
```

---

<a id="origin-5018"></a>
##### 3.31.7.24 如果 GPU0 已经停止了呢？

那么：

```text
GPU0：
不执行 backward
```

GPU1：

```text
执行 backward
↓
进入梯度 all_reduce
↓
等待 GPU0
```

但是 GPU0：

```text
根本没有进入这一轮 all_reduce
```

于是 GPU1 一直等：

```text
GPU1：

“GPU0 的梯度呢？”

↓
等
↓
等
↓
卡住
```

最后就可能出现：

```text
DDP Hang / Deadlock
```

---

<a id="origin-5066"></a>
##### 3.31.7.25 所以必须先统一所有 GPU 的 KL

源码：

```python
dist.all_reduce(
    approx_kl_val,
    op=dist.ReduceOp.AVG
)
```

假设：

```text
GPU0：

0.30


GPU1：

0.10
```

执行后：

\[
\frac{0.30+0.10}{2}
=
0.20
\]

然后：

```text
GPU0：

approx_kl_val = 0.20


GPU1：

approx_kl_val = 0.20
```

---

<a id="origin-5113"></a>
##### 3.31.7.26 然后所有 GPU 用相同值判断

```python
if approx_kl_val > args.early_stop_kl:
    stop_ppo = True
```

现在：

```text
GPU0：
KL = 0.20

GPU1：
KL = 0.20
```

所以一定：

```text
一起继续
```

或者：

```text
一起停止
```

不会出现：

```text
一张卡停
另一张卡继续
```

---

<a id="origin-5151"></a>
##### 3.31.7.27 `all_reduce(AVG)` 本身并不计算 KL

这一点也要特别注意。

KL 已经在前面算好了：

```python
approx_kl = ...
```

`all_reduce` 做的是：

```text
GPU0 的 local KL
GPU1 的 local KL
GPU2 的 local KL
GPU3 的 local KL
        ↓
求平均
        ↓
所有 GPU 都拿到同一个值
```

所以：

\[
\boxed{
all\_reduce
\neq
计算 KL
}
\]

而是：

\[
\boxed{
all\_reduce
=
同步不同 GPU 已经计算好的 KL
}
\]

---

<a id="origin-5196"></a>
##### 3.31.7.28 举一个四卡例子

假设：

```text
GPU0：KL = 0.10
GPU1：KL = 0.20
GPU2：KL = 0.30
GPU3：KL = 0.40
```

执行：

```python
dist.all_reduce(
    approx_kl_val,
    op=dist.ReduceOp.AVG
)
```

得到：

\[
KL_{\text{global}}
=
\frac{
0.10+0.20+0.30+0.40
}{4}
\]

\[
=
0.25
\]

最终：

```text
GPU0 → 0.25
GPU1 → 0.25
GPU2 → 0.25
GPU3 → 0.25
```

这样所有 GPU：

```text
看到的是同一个 global KL
```

---

<a id="origin-5248"></a>
##### 3.31.7.29 整个过程一张图

```text
             Current Actor
                   │
                   │
          重新计算 Response LogP
                   │
                   ▼

             mb_resp_logp

                   │
                   │ 减去 rollout 时保存的
                   ▼

             old_resp_logp

                   │
                   ▼

log_ratio
=
log π_new - log π_old

                   │
                   ▼

每个 Token：

0.5 × log_ratio²

                   │
                   ▼

对当前 GPU
所有有效 Response Token 求平均

                   │
                   ▼

              approx_kl

当前 GPU 的
Local Approximate KL

                   │
                   ▼

           detach().clone()

                   │
                   ▼

           approx_kl_val

不参与梯度，
专门用于同步和判断

                   │
                   ▼

dist.all_reduce(..., AVG)

                   │
                   ▼

所有 GPU 的 local KL 求平均

                   │
                   ▼

所有 GPU 得到相同的
Global Approx KL

                   │
                   ▼

approx_kl_val > threshold ?

          ┌────────┴────────┐
          │                 │
         否                是
          │                 │
          ▼                 ▼

     所有 GPU          所有 GPU
       继续              停止
```

---

<a id="origin-5340"></a>
##### 3.31.7.30 最后再把两种 KL 放在一张图里

```text
                    PPO / RLHF

                         Actor
                           │
          ┌────────────────┴────────────────┐
          │                                 │
          ▼                                 ▼

      Old Policy                    Reference Model
          │                                 │
          │                                 │
New vs Old Approx KL              Actor vs Ref KL
          │                                 │
          ▼                                 ▼

监控当前 PPO                    真正加入 Policy Loss
是否更新太远                         的 KL Penalty
          │                                 │
          ▼                                 ▼

Early Stop                      防止长期偏离 SFT
```

---

<a id="origin-5368"></a>
##### 3.31.7.31 一张表彻底记住

| 比较 | 使用方式 | 目的 |
|---|---|---|
| New vs Old | `ratio` | PPO Clip |
| New vs Old | `approx_kl` | PPO Early Stop |
| New vs Ref | `kl_ref_penalty` | 加入 Actor Loss，防止长期漂移 |

所以：

\[
\boxed{
\text{Old Policy 同时参与 Ratio、Clip 和 Approx KL}
}
\]

而：

\[
\boxed{
\text{Reference Model 主要参与 KL Regularization}
}
\]

---

<a id="origin-5394"></a>
##### 3.31.7.32 最准确的一句话总结

关键关系如下：

> **我们通常说 PPO/RLHF 里的“KL 惩罚”时，指的是 Actor 和 Reference Model 之间的 KL，它直接加入 Policy Loss，防止 Actor 长期偏离原始 SFT 模型。**
>
> **但 PPO 实现中还可以额外计算 Current Actor 和 Old Policy 之间的 `approx_kl`。这个 KL 不作为训练惩罚项，而是用来监控当前 PPO 更新是否已经离采样策略太远，超过阈值就 Early Stop。**
>
> **在多 GPU DDP 下，每张 GPU 算出的 local `approx_kl` 不同，因此代码通过 `dist.all_reduce(..., AVG)` 把它们同步成相同的 global KL，使所有 GPU 一起继续或一起停止，避免不同 GPU 的 backward / collective 次数不一致而导致训练卡死。**

最终关系可以记成：

```text
Reference KL
=
长期约束
=
进入 Loss


Old/New Approx KL
=
短期更新监控
=
不进入 Loss
=
只用于 Early Stop
```

这就是这段：

```python
approx_kl_val = approx_kl.detach().clone()

dist.all_reduce(
    approx_kl_val,
    op=dist.ReduceOp.AVG
)
```

在 PPO + DDP 代码中的真正意义。

---

<a id="origin-5438"></a>
#### 3.31.8 （重点）为什么 PPO 中可以用

\[
\boxed{
\frac12(\log ratio)^2
}
\]

近似衡量 KL？

在这份 PPO 代码中：

```python
log_ratio = mb_resp_logp - old_resp_logp[inds]
```

然后：

```python
approx_kl = (
    0.5 * (log_ratio ** 2) * resp_policy_mask[inds]
).sum() / resp_policy_mask[inds].sum().clamp(min=1)
```

也就是说，代码把：

\[
\boxed{
\frac12(\log ratio)^2
}
\]

当成 New Policy 和 Old Policy 之间 KL 的一个近似量。

这个形式不是随便定义的。

它来自：

> **当 New Policy 和 Old Policy 很接近时，对真正 KL 的二阶近似。**

---

<a id="origin-5480"></a>
##### 3.31.8.1 先定义 PPO 中的 `ratio`

PPO 中：

\[
ratio
=
\frac{
\pi_{\text{new}}(a|s)
}{
\pi_{\text{old}}(a|s)
}
\]

定义：

\[
x
=
\log ratio
\]

那么：

\[
x
=
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
\]

同时：

\[
ratio=e^x
\]

如果 New Policy 和 Old Policy 很接近，那么：

\[
ratio\approx1
\]

所以：

\[
x=\log ratio\approx0
\]

也就是说：

\[
x
\]

是一个比较小的数。

---

<a id="origin-5540"></a>
##### 3.31.8.2 真正的 KL 是什么？

考虑：

\[
D_{KL}
(
\pi_{\text{old}}
\|
\pi_{\text{new}}
)
\]

定义是：

\[
D_{KL}
=
\sum_a
\pi_{\text{old}}(a)
\log
\frac{
\pi_{\text{old}}(a)
}{
\pi_{\text{new}}(a)
}
\]

也可以写成期望：

\[
D_{KL}
=
\mathbb E_{\pi_{\text{old}}}
\left[
\log
\frac{
\pi_{\text{old}}
}{
\pi_{\text{new}}
}
\right]
\]

而前面定义：

\[
x
=
\log
\frac{
\pi_{\text{new}}
}{
\pi_{\text{old}}
}
\]

所以：

\[
\log
\frac{
\pi_{\text{old}}
}{
\pi_{\text{new}}
}
=
-x
\]

因此：

\[
\boxed{
D_{KL}
=
-\mathbb E_{\pi_{\text{old}}}[x]
}
\]

也就是：

\[
\boxed{
D_{KL}
=
-\mathbb E_{\pi_{\text{old}}}
[\log ratio]
}
\]

---

<a id="origin-5633"></a>
##### 3.31.8.3 \(\pi_{\text{new}}(a)\)是概率分布，因此有一个重要性质

注意：

> 概率分布必须满足归一化。

也就是说：

\[
\sum_a
\pi_{\text{new}}(a)
=
1
\]

而：

\[
\pi_{\text{new}}(a)
=
\pi_{\text{old}}(a)e^{x_a}
\]

因为：

\[
e^{x_a}
=
\frac{
\pi_{\text{new}}(a)
}{
\pi_{\text{old}}(a)
}
\]

所以：

\[
\sum_a
\pi_{\text{old}}(a)e^{x_a}
=
1
\]

写成期望就是：

\[
\boxed{
\mathbb E_{\pi_{\text{old}}}
[e^x]
=
1
}
\]

这个条件非常重要。

---

<a id="origin-5692"></a>
##### 3.31.8.4 当 New 和 Old 很接近时，对 \(e^x\) 做泰勒展开

因为：

\[
x\approx0
\]

所以：

\[
e^x
=
1+x+\frac{x^2}{2}
+\frac{x^3}{6}
+\cdots
\]

如果：

\[
x
\]

足够小，那么三阶及以上项：

\[
x^3,x^4,\cdots
\]

就比较小，可以先忽略。

于是：

\[
e^x
\approx
1+x+\frac{x^2}{2}
\]

---

<a id="origin-5734"></a>
##### 3.31.8.5 代入概率归一化条件

前面有：

\[
\mathbb E[e^x]=1
\]

代入二阶近似：

\[
\mathbb E
\left[
1+x+\frac{x^2}{2}
\right]
\approx
1
\]

展开：

\[
1
+
\mathbb E[x]
+
\frac12
\mathbb E[x^2]
\approx
1
\]

两边减去 1：

\[
\mathbb E[x]
+
\frac12
\mathbb E[x^2]
\approx
0
\]

因此：

\[
-\mathbb E[x]
\approx
\frac12
\mathbb E[x^2]
\]

---

<a id="origin-5788"></a>
##### 3.31.8.6 而 KL 正好等于 \(-E[x]\)

前面已经得到：

\[
D_{KL}
=
-\mathbb E[x]
\]

因此：

\[
D_{KL}
\approx
\frac12
\mathbb E[x^2]
\]

而：

\[
x=\log ratio
\]

所以：

\[
\boxed{
D_{KL}
\approx
\frac12
\mathbb E
\left[
(\log ratio)^2
\right]
}
\]

这就是代码中：

```python
0.5 * (log_ratio ** 2)
```

的数学来源。

---

<a id="origin-5837"></a>
##### 3.31.8.7 为什么一定要平方？

因为：

\[
\log ratio
\]

有正有负。

例如：

```text
token A：
log_ratio = +0.1

token B：
log_ratio = -0.1
```

如果直接平均：

\[
\frac{
0.1+(-0.1)
}{2}
=
0
\]

看起来好像：

> New Policy 和 Old Policy 完全没变化。

但实际上：

```text
token A 的概率变大了
token B 的概率变小了
```

策略显然发生了变化。

所以要平方：

\[
(+0.1)^2=0.01
\]

\[
(-0.1)^2=0.01
\]

这样不管：

```text
概率变大
```

还是：

```text
概率变小
```

都会被认为是：

> 策略发生了变化。

这也符合“距离”的直觉：

```text
向左偏 0.1
和
向右偏 0.1
```

距离都应该是正的。

---

<a id="origin-5918"></a>
##### 3.31.8.8 为什么前面正好是 \(\frac12\)？

因为二阶泰勒展开：

\[
e^x
=
1+x+\frac{x^2}{2!}+\cdots
\]

其中：

\[
2!=2
\]

所以二阶项本来就是：

\[
\frac{x^2}{2}
\]

因此：

\[
\boxed{
\frac12
}
\]

不是人为随便加的系数。

而是从：

\[
e^x
\]

的二阶泰勒展开自然得到的。

---

<a id="origin-5960"></a>
##### 3.31.8.9 为什么 KL 公式里有期望，代码却可以直接算？

我们经常看到：

\[
\boxed{
D_{KL}
\approx
\frac12
\mathbb E
\left[
(\log ratio)^2
\right]
}
\]

这里很多人会有一个疑问：

> 公式里面明明有一个期望 \(\mathbb E\)，为什么代码里直接算 `0.5 * log_ratio ** 2` 就可以了？

关键是：

> **代码不是把期望去掉了，而是用样本平均来近似这个期望。**

---

<a id="origin-5986"></a>
###### 3.31.8.9.1 理论上的期望

假设有一个随机变量：

\[
X
\]

理论上的期望写作：

\[
\mathbb E[X]
\]

但实际训练时，我们不可能把整个概率分布里的所有情况都枚举出来。

所以实际只能采样得到：

\[
X_1,X_2,\dots,X_N
\]

然后用样本平均：

\[
\boxed{
\mathbb E[X]
\approx
\frac1N
\sum_{i=1}^{N}X_i
}
\]

这就是 Monte Carlo 估计。

---

<a id="origin-6023"></a>
###### 3.31.8.9.2 放到 KL 公式里

原公式是：

\[
D_{KL}
\approx
\frac12
\mathbb E
\left[
(\log ratio)^2
\right]
\]

假设：

\[
x_i
=
\log ratio_i
\]

那么：

\[
D_{KL}
\approx
\frac12
\mathbb E[x^2]
\]

用样本平均代替期望：

\[
\boxed{
D_{KL}
\approx
\frac1N
\sum_{i=1}^{N}
\frac12x_i^2
}
\]

也就是：

\[
\boxed{
D_{KL}
\approx
\frac1N
\sum_{i=1}^{N}
\frac12
(\log ratio_i)^2
}
\]

---

<a id="origin-6081"></a>
###### 3.31.8.9.3 所以代码最简单可以写成

```python
approx_kl = 0.5 * (log_ratio ** 2).mean()
```

这里：

```python
0.5 * (log_ratio ** 2)
```

是在对每一个样本计算：

\[
\frac12(\log ratio_i)^2
\]

而：

```python
.mean()
```

就是在计算：

\[
\frac1N
\sum_i
\]

也就是用样本平均近似：

\[
\mathbb E[\cdot]
\]

所以：

```python
.mean()
```

可以理解成代码里的：

\[
\boxed{
\mathbb E
}
\]

---

<a id="origin-6134"></a>
###### 3.31.8.9.4 举一个具体例子

假设一共有 4 个有效 token：

```text
log_ratio =
[0.1, 0.2, -0.1, 0.3]
```

先分别计算：

\[
\frac12(\log ratio)^2
\]

得到：

\[
\frac12(0.1)^2=0.005
\]

\[
\frac12(0.2)^2=0.020
\]

\[
\frac12(-0.1)^2=0.005
\]

\[
\frac12(0.3)^2=0.045
\]

所以得到：

```text
[0.005, 0.020, 0.005, 0.045]
```

然后求平均：

\[
approx\_kl
=
\frac{
0.005+0.020+0.005+0.045
}{4}
\]

得到：

\[
approx\_kl
=
0.01875
\]

代码就是：

```python
approx_kl = 0.5 * (log_ratio ** 2).mean()
```

---

<a id="origin-6199"></a>
###### 3.31.8.9.5 那实际 PPO 代码为什么写得更复杂？

实际代码可能是：

```python
approx_kl = (
    0.5 * (log_ratio ** 2) * resp_policy_mask[inds]
).sum() / resp_policy_mask[inds].sum().clamp(min=1)
```

看起来比较复杂，其实本质还是：

```python
mean()
```

只不过这里有 padding，所以不能对所有位置直接求平均。

---

<a id="origin-6219"></a>
###### 3.31.8.9.6 为什么要乘 mask？

例如：

```text
log_ratio:
[0.1, 0.2, -0.1, 0.3, 0.5]

mask:
[1,   1,    1,   0,   0]
```

其中：

```text
1 = 有效 response token
0 = padding / 无效位置
```

先计算：

\[
\frac12(\log ratio)^2
\]

得到：

```text
[0.005, 0.020, 0.005, 0.045, 0.125]
```

再乘 mask：

```text
[0.005, 0.020, 0.005, 0, 0]
```

也就是说：

> 后两个无效 token 不参与 KL 计算。

---

<a id="origin-6262"></a>
###### 3.31.8.9.7 `.sum()` 在做什么？

```python
(
    0.5 * (log_ratio ** 2) * mask
).sum()
```

得到：

\[
0.005+0.020+0.005
=
0.030
\]

这是所有有效 token 的 KL 估计值之和。

---

<a id="origin-6282"></a>
###### 3.31.8.9.8 为什么还要除以 `mask.sum()`？

因为：

```python
mask.sum()
```

就是有效 token 的数量。

上面的例子：

```text
mask =
[1, 1, 1, 0, 0]
```

所以：

\[
mask.sum()=3
\]

最终：

\[
approx\_kl
=
\frac{0.030}{3}
=
0.010
\]

因此：

```python
(value * mask).sum() / mask.sum()
```

其实就是：

\[
\boxed{
\text{只对有效 token 求平均}
}
\]

也就是：

```text
masked mean
```

---

<a id="origin-6337"></a>
###### 3.31.8.9.9 对应回理论公式

理论公式：

\[
\boxed{
D_{KL}
\approx
\frac12
\mathbb E
\left[
(\log ratio)^2
\right]
}
\]

实际代码：

```python
approx_kl = (
    0.5 * (log_ratio ** 2) * mask
).sum() / mask.sum()
```

可以一一对应：

```text
理论：

E[
    1/2 × (log ratio)^2
]


代码：

(
    1/2 × (log_ratio)^2
).mean()
```

如果存在 padding：

```text
理论：

对有效 token 求期望


代码：

(
    value × mask
).sum()
──────────────
   mask.sum()
```

---

<a id="origin-6397"></a>
###### 3.31.8.9.10 一个非常重要的理解

不能把：

\[
\frac12
(\log ratio)^2
\]

本身直接理解成最终的：

\[
D_{KL}
\]

更准确地说：

\[
\frac12
(\log ratio_i)^2
\]

只是：

> **第 \(i\) 个采样 token 对 KL 的一个估计贡献。**

真正的 KL 估计还需要把多个采样值平均：

\[
\boxed{
D_{KL}
\approx
\frac1N
\sum_i
\frac12
(\log ratio_i)^2
}
\]

也就是：

```python
0.5 * (log_ratio ** 2).mean()
```

---

<a id="origin-6444"></a>
###### 3.31.8.9.11 为什么这里可以用 token 平均？

因为 PPO rollout 本身已经产生了一批样本。

例如：

```text
Prompt 1
  ├── token 1
  ├── token 2
  ├── token 3
  └── token 4

Prompt 2
  ├── token 1
  ├── token 2
  └── token 3
```

这些 token 对应的 action：

\[
a_t
\]

本身就是从 Policy 中采样出来的。

因此可以用这些实际采样到的 token：

```text
token 1
token 2
token 3
...
```

去近似理论上的分布期望：

\[
\mathbb E_{a\sim\pi}[\cdot]
\]

也就是说：

```text
理论上：
对整个 Policy 分布求期望

实际上：
拿 rollout 已经采样出来的 token 求平均
```

---

<a id="origin-6498"></a>
###### 3.31.8.9.12 整个过程画出来

```text
理论 KL

D_KL
≈
1/2 E[(log ratio)²]

        ↓

真实分布没法全部枚举

        ↓

用 rollout 采样

        ↓

得到很多 token 的 log_ratio

x₁, x₂, x₃, ..., xₙ

        ↓

每个 token 算

1/2 x₁²
1/2 x₂²
1/2 x₃²
...
1/2 xₙ²

        ↓

求样本平均

1/N Σ 1/2 xᵢ²

        ↓

近似理论期望

E[1/2 x²]
```

---

<a id="origin-6546"></a>
###### 3.31.8.9.13 最终一句话总结

> 公式中的
>
> \[
> \mathbb E
> \]
>
> 表示理论上对整个概率分布求期望；实际 PPO 训练无法枚举整个分布，因此直接使用 rollout 中已经采样出来的 token 做 Monte Carlo 估计，用这些 token 的平均值来近似期望。因此：
>
> \[
> \boxed{
> \frac12
> \mathbb E[(\log ratio)^2]
> }
> \]
>
> 在代码中通常写成：
>
> ```python
> 0.5 * (log_ratio ** 2).mean()
> ```
>
> 如果存在 padding，则使用：
>
> ```python
> (
>     0.5 * (log_ratio ** 2) * mask
> ).sum() / mask.sum()
> ```
>
> 本质完全一样：**`.mean()` 或 masked mean，就是代码里对期望 \(\mathbb E\) 的样本近似。**

---
<a id="origin-6580"></a>
##### 3.31.8.10 用一个具体数字例子

假设某个 token：

\[
P_{\text{old}}
=
0.20
\]

PPO 更新后：

\[
P_{\text{new}}
=
0.22
\]

那么：

\[
ratio
=
\frac{0.22}{0.20}
=
1.1
\]

于是：

\[
\log ratio
=
\log1.1
\approx
0.0953
\]

近似 KL：

\[
\frac12
(0.0953)^2
\]

\[
\approx
0.00454
\]

这个值很小。

符合直觉：

```text
0.20
↓
0.22
```

New Policy 只比 Old Policy 改了一点点。

---

<a id="origin-6644"></a>
##### 3.31.8.11 如果变化很大呢？

假设：

\[
P_{\text{old}}
=
0.20
\]

而：

\[
P_{\text{new}}
=
0.40
\]

那么：

\[
ratio
=
2
\]

\[
\log ratio
=
\log2
\approx
0.693
\]

所以：

\[
\frac12
(0.693)^2
\]

\[
\approx
0.240
\]

明显比前面的：

\[
0.00454
\]

大很多。

说明：

> Current Policy 已经离 Old Policy 更远了。

---

<a id="origin-6704"></a>
##### 3.31.8.12 为什么只在“小变化”情况下近似得好？

因为我们刚才实际上忽略了：

\[
\frac{x^3}{6}
+
\frac{x^4}{24}
+\cdots
\]

如果：

\[
x=0.05
\]

那么：

\[
x^2=0.0025
\]

\[
x^3=0.000125
\]

三阶项已经非常小。

这时候只保留到二阶：

\[
1+x+\frac{x^2}{2}
\]

通常比较合理。

---

但如果：

\[
x=2
\]

那么：

\[
x^2=4
\]

\[
x^3=8
\]

这时候三阶、高阶项根本不能忽略。

所以：

\[
\frac12x^2
\]

就不能非常准确地代表真实 KL。

---

<a id="origin-6771"></a>
##### 3.31.8.13 为什么 PPO 特别适合使用这种近似？

因为 PPO 本身就是在做：

> **小步更新。**

PPO 不希望：

```text
New Policy
```

一次就离：

```text
Old Policy
```

非常远。

也就是说：

\[
ratio
\]

应该尽量在：

\[
1
\]

附近。

所以：

\[
\log ratio
\]

也应该在：

\[
0
\]

附近。

恰好满足：

> 泰勒二阶近似适用的“小变化区域”。

因此：

\[
\boxed{
\frac12
(\log ratio)^2
}
\]

非常适合用来监控 PPO 当前更新幅度。

---

<a id="origin-6836"></a>
##### 3.31.8.14 对应到源码

代码：

```python
log_ratio = (
    mb_resp_logp
    -
    old_resp_logp[inds]
)
```

就是：

\[
\log ratio
=
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
\]

然后：

```python
0.5 * (log_ratio ** 2)
```

就是：

\[
\frac12
(\log ratio)^2
\]

最后：

```python
(
    ...
    * resp_policy_mask[inds]
).sum() / resp_policy_mask[inds].sum().clamp(min=1)
```

就是只对：

```text
有效 Response Token
```

求平均。

于是：

\[
\boxed{
approx\_kl
=
\mathbb E
\left[
\frac12
(\log ratio)^2
\right]
}
\]

---

<a id="origin-6904"></a>
##### 3.31.8.15 最核心的推导链

可以把整个推导压缩成：

\[
ratio
=
\frac{
\pi_{\text{new}}
}{
\pi_{\text{old}}
}
\]

定义：

\[
x=\log ratio
\]

因为：

\[
\pi_{\text{new}}
=
\pi_{\text{old}}e^x
\]

概率归一化要求：

\[
\mathbb E_{\text{old}}[e^x]=1
\]

**当：**

\[
x\approx0
\]

**时（泰勒公式的前提，只有x在0附近才成立的公式）：**

\[
e^x
\approx
1+x+\frac{x^2}{2}
\]

所以：

\[
1+
E[x]
+
\frac12E[x^2]
\approx
1
\]

因此：

\[
-E[x]
\approx
\frac12E[x^2]
\]

而：

\[
KL
=
-E[x]
\]

所以：

\[
\boxed{
KL
\approx
\frac12
E
[
(\log ratio)^2
]
}
\]

---

<a id="origin-6995"></a>
##### 3.31.8.16 一句话记忆

代码里的：

```python
0.5 * (log_ratio ** 2)
```

不是一个随便定义的“距离”。

它来自：

> **New Policy 与 Old Policy 很接近时，对真实 KL 做二阶泰勒展开。**

核心思想就是：

```text
New ≈ Old
↓
ratio ≈ 1
↓
log_ratio ≈ 0
↓
可以做二阶展开
↓
一阶项由于概率归一化关系抵消
↓
主要剩下：

0.5 × log_ratio²
```

因此：

\[
\boxed{
\text{approx KL}
\approx
\frac12
(\log ratio)^2
}
\]

本质上是在用：

> **New Policy 和 Old Policy 的 log probability 变化平方**

来近似衡量两套策略之间的距离。

---

<a id="origin-7046"></a>
#### 3.31.9 `dist.barrier()`

所有进程都必须走到这里，才能继续。

相当于：

```text
大家集合，等人到齐。
```

---

<a id="origin-7058"></a>
#### 3.31.10 `dist.destroy_process_group()`

训练结束后销毁 distributed 通信组。

---

<a id="origin-7064"></a>
### 3.32 `DataLoader`

负责：

```text
Dataset
  ↓
取样
  ↓
组成 batch
  ↓
多进程加载
  ↓
返回给训练循环
```

---

<a id="origin-7082"></a>
#### 3.32.1 `DistributedSampler`

多 GPU 时把 Dataset 分给不同 rank。

例如 100 条数据，2 个 GPU，大致：

```text
GPU0 → 一部分索引
GPU1 → 另一部分索引
```

---

<a id="origin-7095"></a>
#### 3.32.2 `sampler.set_epoch(epoch)`

DistributedSampler 每轮通常要设置 epoch。

作用：

> 每个 epoch 使用新的、但各 rank 之间一致协调的随机打乱。

---

<a id="origin-7105"></a>
### 3.33 Python 内置函数，也在理解代码时很重要

<a id="origin-7107"></a>
#### 3.33.1 `len(x)`

长度。

---

<a id="origin-7113"></a>
#### 3.33.2 `enumerate(x)`

同时得到：

```text
index + item
```

---

<a id="origin-7123"></a>
#### 3.33.3 `zip(a,b)`

把两组数据一一配对。

---

<a id="origin-7129"></a>
#### 3.33.4 `range(n)`

生成整数序列。

---

<a id="origin-7135"></a>
#### 3.33.5 `reversed(...)`

倒序遍历。

GAE 必须从后往前算，所以使用它。

---

<a id="origin-7143"></a>
#### 3.33.6 `min / max`

普通 Python 最小/最大值。

---

<a id="origin-7149"></a>
#### 3.33.7 `set(...)`（重点）

去重集合。

重复 n-gram 惩罚中：

```python
len(grams) - len(set(grams))
```

就是：

```text
总 n-gram 数
-
去重后 n-gram 数
=
重复数量
```

---

<a id="origin-7171"></a>
#### 3.33.8 `isinstance(obj, Type)`

判断对象是否属于某类型。

这里主要判断：

```text
模型是不是被 DDP 包装了。
```

---

<a id="origin-7183"></a>
#### 3.33.9 `getattr(obj, name, default)`

按名字读取属性。

例如：

```python
getattr(raw_actor, "_orig_mod", raw_actor)
```

如果 `torch.compile` 产生 `_orig_mod`：

```text
取原始模型
```

否则：

```text
仍使用 raw_actor
```

---

<a id="origin-7207"></a>
### 3.34 项目内部但定义在其他文件中的接口

这些不是第三方库 API，但对本文件很重要。

由于当前只有 `train_ppo.py`，这里严格按调用方式解释，不臆测其内部实现。

<a id="origin-7213"></a>
#### 3.34.1 `MiniMindConfig`

创建 MiniMind 模型配置。

本文件明确传入：

```python
hidden_size
num_hidden_layers
use_moe
```

---

<a id="origin-7227"></a>
#### 3.34.2 `MiniMindForCausalLM`

MiniMind 因果语言模型基类。

Actor 和 Critic 都依赖它。

---

<a id="origin-7235"></a>
#### 3.34.3 `RLAIFDataset`

根据调用可以确定：

```python
RLAIFDataset(
    data_path,
    tokenizer,
    max_length=...,
    thinking_ratio=...
)
```

它负责提供 PPO 训练需要的 Prompt 数据。

---

<a id="origin-7252"></a>
#### 3.34.4 `Logger`

项目封装的日志打印函数。

---

<a id="origin-7258"></a>
#### 3.34.5 `is_main_process()`

判断当前是否主进程。

多 GPU 时通常只让 rank 0：

- 打印日志；
- 保存模型；
- 上传 wandb/swanlab 指标。

---

<a id="origin-7270"></a>
#### 3.34.6 `init_distributed_mode()`

初始化 distributed，并返回：

```text
local_rank
```

---

<a id="origin-7280"></a>
#### 3.34.7 `setup_seed(seed)`

设置随机种子。

---

<a id="origin-7286"></a>
#### 3.34.8 `init_model(...)`

初始化：

- MiniMind 模型；
- tokenizer；

并基于某个权重名称加载初始参数。

---

<a id="origin-7297"></a>
#### 3.34.9 `lm_checkpoint(...)`

从本文件调用可知，它至少支持两类行为：

1. 不传 model 时尝试读取 checkpoint；
2. 传入 model/optimizer/scheduler 等时保存完整训练状态。

---

<a id="origin-7306"></a>
#### 3.34.10 `SkipBatchSampler`

用于续训时跳过已经训练过的 batch。

---

<a id="origin-7312"></a>
#### 3.34.11 `LMForRewardModel`

Reward Model 包装器。

本文件实际使用接口：

```python
reward_model.get_score(messages, answer)
```

返回一个回答分数。

其内部究竟：

- 用哪个 tokenizer；
- 如何拼接 conversation；
- 取哪个输出位置；

不在当前文件中，不能从本文件确定。

---

<a id="origin-7334"></a>
#### 3.34.12 `create_rollout_engine`

创建 rollout 引擎。

本文件支持：

```text
torch
sglang
```

至少暴露两个接口：

```python
rollout_engine.rollout(...)
rollout_engine.update_policy(...)
```

---

<a id="origin-7354"></a>
## 4. 正式进入 PPO：先看整个训练的数据流（重点）

训练循环核心在：

```python
ppo_train_epoch(...)
```

每个大 batch 都经历：

```text
阶段 1：Prompt tokenizer
阶段 2：Actor rollout
阶段 3：Reward
阶段 4：准备 mask / token 对齐
阶段 5：Critic old value
阶段 6：Reference log probability
阶段 7：GAE
阶段 8：Advantage 标准化
阶段 9：多轮 PPO mini-batch 更新
阶段10：梯度更新
阶段11：同步 rollout engine
阶段12：日志与保存
```

下面逐块拆开。

---

<a id="origin-7383"></a>
## 5. 初始化阶段：训练开始前发生了什么

<a id="origin-7385"></a>
### 5.1 初始化分布式环境

```python
local_rank = init_distributed_mode()
```

如果 DDP 已启用：

```python
args.device = f"cuda:{local_rank}"
```

例如：

```text
rank 0 → cuda:0
rank 1 → cuda:1
```

---

<a id="origin-7406"></a>
### 5.2 设置随机种子

```python
setup_seed(
    42 + rank
)
```

不同 rank 使用不同 seed，可以避免完全相同的随机采样。

---

<a id="origin-7418"></a>
### 5.3 构造模型配置

```python
lm_config = MiniMindConfig(
    hidden_size=args.hidden_size,
    num_hidden_layers=args.num_hidden_layers,
    use_moe=bool(args.use_moe)
)
```

---

<a id="origin-7430"></a>
### 5.4 Actor 和 Reference 从相同起点开始

```python
actor_model, tokenizer = init_model(...)
ref_model, _ = init_model(...)
```

然后：

```python
ref_model = ref_model.eval().requires_grad_(False)
```

因此初始时通常：

\[
\pi_{\text{actor}}
=
\pi_{\text{ref}}
\]

后面：

```text
Actor → 不断训练
Ref   → 永远不动
```

于是两者逐渐分开。

---

<a id="origin-7462"></a>
### 5.5 Critic 怎么初始化？

先读取 SFT Actor 权重：

```python
state_dict = torch.load(...)
```

再建立 Critic：

```python
critic_model = CriticModel(lm_config)
```

Critic 包含：

```text
MiniMind backbone
+
value_head
```

然后：

```python
critic_model.load_state_dict(
    state_dict,
    strict=False
)
```

这意味着：

```text
Critic backbone
    ← 尽量继承语言模型已有表示能力

value_head
    ← Actor checkpoint 中不存在，因此从新初始化开始学习
```

这是很常见的做法。

---

<a id="origin-7507"></a>
### 5.6 Reward Model

```python
reward_model = LMForRewardModel(...)
```

它不参与 PPO 的梯度更新。

它只负责：

```text
Prompt + Answer
    ↓
一个标量评分
```

---

<a id="origin-7525"></a>
### 5.7 优化器

```python
actor_optimizer = AdamW(actor_model.parameters(), ...)
critic_optimizer = AdamW(critic_model.parameters(), ...)
```

注意：

> Actor 和 Critic 是两套独立参数、两套独立 optimizer。

---

<a id="origin-7538"></a>
## 6. 第一步：取一批 Prompt

训练循环：

```python
for step, batch in enumerate(loader):
    prompts = batch["prompt"]
```

假设：

```text
B = 2
```

得到：

```python
prompts = [
    "问题 A",
    "问题 B"
]
```

---

<a id="origin-7564"></a>
## 7. 第二步：Tokenizer

代码：

```python
enc = tokenizer(
    prompts,
    return_tensors="pt",
    padding=True,
    truncation=True,
    max_length=args.max_seq_len,
    padding_side="left"
)
```

假设两条 Prompt：

```text
Prompt A：4 tokens
Prompt B：2 tokens
```

左 padding 后：

```text
A: [11, 12, 13, 14]
B: [PAD,PAD,21,22]
```

attention mask：

```text
A: [1,1,1,1]
B: [0,0,1,1]
```

为什么生成模型常用 left padding？

因为 batch generation 时：

> 每条序列的“最后一个有效 token”在相同右侧边界附近，更方便自回归生成。

---

<a id="origin-7608"></a>
## 8. 第三步：Rollout——Actor 真正生成回答

代码：

```python
rollout_result = rollout_engine.rollout(
    prompt_ids=enc.input_ids,
    attention_mask=enc.attention_mask,
    num_generations=1,
    max_new_tokens=args.max_gen_len,
    temperature=0.8
)
```

Rollout 的含义：

> 用当前策略真正采样动作，而不是拿标准答案做 teacher forcing。

例如 Prompt：

```text
中国的首都是？
```

Actor 逐 token 生成：

```text
北
京
。
EOS
```

---

<a id="origin-7643"></a>
## 9. Rollout 返回了什么？

<a id="origin-7645"></a>
### 9.1 `output_ids`

```python
gen_out = rollout_result.output_ids
```

是：

```text
Prompt + Response
```

例如：

```text
[10,11,12,13 | 51,52,EOS]
```

形状约：

\[
[B,P+R]
\]

---

<a id="origin-7671"></a>
### 9.2 `completion_ids`

```python
completion_ids = rollout_result.completion_ids
```

只有回答：

```text
[51,52,EOS]
```

形状：

\[
[B,R]
\]

---

<a id="origin-7691"></a>
### 9.3 `prompt_lens`

每条 Prompt 的真实 token 长度：

```text
[4, 2, ...]
```

---

<a id="origin-7701"></a>
### 9.4 `completions`

解码后的字符串。

例如：

```text
"北京。"
```

用于：

- 规则奖励；
- Reward Model。

---

<a id="origin-7718"></a>
### 9.5 `per_token_logps`

```python
old_resp_logp
```

这是 PPO 的核心缓存。

例如：

```text
北      京      。
-0.50   -0.20   -0.75
```

它记录：

\[
\log\pi_{\text{old}}(a_t|s_t)
\]

注意：

> 这里的 old 不是“一开始的 SFT 模型”，而是“生成当前这批 rollout 时的策略”。

---

<a id="origin-7745"></a>
## 10. 第四步：计算 Reward

代码：

```python
rewards = calculate_rewards(...)
```

最终：

\[
rewards\in\mathbb{R}^{B}
\]

即：

> 一条回答一个总分。

---

<a id="origin-7765"></a>
## 11. Reward 由四部分组成（重点）

<a id="origin-7767"></a>
### 11.1 长度奖励

```python
+0.5
```

如果回答长度：

```text
20 ~ 800 字符
```

否则：

```text
-0.5
```

它在鼓励：

> 不要过短，也不要无限长。

---

<a id="origin-7791"></a>
### 11.2 Thinking 格式奖励

如果回答里有：

```text
</think>
```

则检查：

1. thinking 内容长度；
2. `</think>` 是否只出现一次。

注意：

> 这是这份代码自己定义的任务规则，不是 PPO 必需组件。

---

<a id="origin-7810"></a>
### 11.3 重复惩罚

函数：

```python
rep_penalty(answer)
```

默认使用 3-gram。

例如：

```text
我 爱 AI 我 爱 AI
```

如果大量连续 3-token 片段重复，惩罚增加。

最高惩罚：

```text
0.5
```

---

<a id="origin-7836"></a>
### 11.4 Reward Model 分数

```python
score = reward_model.get_score(
    messages,
    answer
)
```

最后：

```python
rewards += reward_model_scores
```

所以：

\[
R
=
R_{\text{length}}
+
R_{\text{thinking}}
-
R_{\text{repeat}}
+
R_{\text{RM}}
\]

---

<a id="origin-7867"></a>
## 12. 注意：Reward 是整条回答一个分数

现在有：

```text
response:
token1 token2 token3 token4 EOS

reward:
2.7
```

但是 PPO 是 token 级策略：

\[
\pi(a_t|s_t)
\]

所以必须把一个序列级 reward 转成 token 级训练信号。

这正是后面的：

> **Critic + GAE**

要解决的问题。

---

<a id="origin-7895"></a>
## 13. 第五步：构造完整序列 Mask

```python
full_mask = (
    gen_out != tokenizer.pad_token_id
).long()
```

例如：

```text
gen_out:
[10,11,12,13,51,52,EOS,PAD,PAD]

full_mask:
[1, 1, 1, 1, 1, 1, 1, 0, 0]
```

这个 mask 会给：

- Actor；
- Critic；
- Reference Model；

使用。

---

<a id="origin-7923"></a>
## 14. 为什么 `labels = gen_out[:,1:]`？

语言模型做的是：

```text
当前位置 hidden state
    ↓
预测下一个 token
```

假设：

```text
input:
10 11 12 13 51 52 EOS
```

那么预测对应关系：

```text
位置0 → 预测 11
位置1 → 预测 12
位置2 → 预测 13
位置3 → 预测 51
位置4 → 预测 52
位置5 → 预测 EOS
```

所以 labels：

```python
gen_out[:, 1:]
```

就是：

```text
11 12 13 51 52 EOS
```

---

<a id="origin-7965"></a>
## 15. `logp_pos` 为什么要减 1？

这是整个代码最容易看晕的地方之一。

假设：

```text
Prompt 长度 P = 4
```

完整序列：

```text
index: 0   1   2   3 | 4   5   6
token: 10  11  12  13 | 51  52 EOS
                         ↑
                       第一个回答 token
```

但是：

```text
token 51
```

是由：

```text
index 3 的 hidden state
```

预测出来的。

所以回答第 0 个 token 对应的“策略 logp 位置”是：

\[
P-1
\]

回答第 \(j\) 个 token：

\[
P-1+j
\]

代码：

```python
logp_pos = (
    prompt_lens.unsqueeze(1)
    - 1
    + resp_idx
)
```

---

<a id="origin-8022"></a>
## 16. Response Mask：只训练真正回答 token

rollout 返回：

```python
completion_mask
```

例如：

```text
样本1: [1,1,1,0,0]
样本2: [1,1,1,1,1]
```

然后又检查 EOS。

为什么还要检查 EOS？

因为：

> PAD mask 只知道“是不是 padding”，但回答可能在 PAD 之前已经出现 EOS。

所以最终：

```python
resp_policy_mask
```

只保留：

```text
第一个回答 token
...
EOS
```

之后全部不参与 PPO loss。

---

<a id="origin-8063"></a>
## 17. 第六步：Critic 先给 rollout 估 Value

代码：

```python
with torch.no_grad():
    values_seq = critic_for_rollout(
        input_ids=gen_out,
        attention_mask=full_mask
    )
```

得到：

\[
values\_seq\in\mathbb{R}^{B\times T}
\]

含义：

```text
完整序列每个位置
都有一个 V(s)
```

---

<a id="origin-8090"></a>
## 18. 为什么 Critic 也用 `logp_pos`？

```python
old_resp_values = values_seq.gather(
    1,
    logp_pos
)
```

要把 Value 和 Actor 的动作对齐。

例如：

```text
状态：
Prompt 到 index 3 为止

动作：
生成 token 51
```

Actor：

```text
index 3 hidden state → token 51 的概率
```

Critic：

```text
index 3 hidden state → V(s_0)
```

因此同一个 `logp_pos` 可以把：

```text
state value
action log probability
```

对齐到一个 PPO 时间步。

---

<a id="origin-8134"></a>
## 19. 第七步：Reference Model 算 token log probability

代码逻辑可以拆成四步。

<a id="origin-8138"></a>
### 19.1 第一步：Reference 前向

\[
[B,T]
\rightarrow
[B,T,V]
\]

---

<a id="origin-8148"></a>
### 19.2 第二步：去掉最后一个预测位置

```python
logits[:, :-1]
```

因为最后一个位置没有对应的 next-token label。

---

<a id="origin-8158"></a>
### 19.3 第三步：log_softmax

\[
logits
\rightarrow
\log p(v)
\]

---

<a id="origin-8168"></a>
### 19.4 第四步：gather

先按真实 token id gather，再按 response 位置 gather。

最终：

\[
ref\_resp\_logp\in\mathbb{R}^{B\times R}
\]

表示：

\[
\log\pi_{\text{ref}}(a_t|s_t)
\]

---

<a id="origin-8186"></a>
## 20. 到这里，三个概率终于齐了

对于同一个回答 token：

```text
old_resp_logp
    = 采样它时 Actor 的 log probability

mb_resp_logp
    = PPO 更新阶段“当前 Actor”的 log probability

ref_resp_logp
    = 冻结 Reference Model 的 log probability
```

三者用途：

```text
new - old
    ↓
PPO ratio / PPO clipping

new - ref
    ↓
Reference KL 约束
```

---

<a id="origin-8215"></a>
## 21. 第八步：把整条回答 Reward 放到最后一个 token

代码：

```python
token_rewards = torch.zeros_like(old_resp_logp)

token_rewards[
    batch_index,
    last_idx
] += rewards
```

假设回答有 4 个 token：

```text
A B C EOS
```

最终 reward：

```text
2.0
```

则：

```text
token reward:
[0, 0, 0, 2.0]
```

这很重要：

> 本代码没有直接给前面的 token 外部 reward。

---

<a id="origin-8253"></a>
## 22. 那前面的 token 怎么知道自己好不好？

靠：

> GAE 从后往前传播。

例如：

```text
回答：
A → B → C → EOS

最终 reward：
2.0
```

虽然 `A` 当时没有直接 reward，但：

> 如果从 A 开始后面最终获得 2.0，那么 A 的选择当然也应该得到一定 credit。

这就是 temporal credit assignment。

---

<a id="origin-8277"></a>
## 23. 第九步：GAE 从最基本的 TD Error 开始

先看一步 TD error：

\[
\delta_t
=
r_t
+
\gamma V(s_{t+1})
-
V(s_t)
\]

理解成：

```text
实际得到的即时奖励
+
下一状态预计价值
-
当前状态原来预计价值
```

---

<a id="origin-8303"></a>
## 24. 用数值例子理解 TD Error

假设：

```text
V(s_t)     = 1.0
V(s_{t+1}) = 1.4
r_t        = 0
gamma      = 1
```

那么：

\[
\delta_t
=
0+1.4-1.0
=
0.4
\]

意思：

> 从这个状态实际往后走以后，未来看起来比 Critic 原来估计的更好。

所以这一步 Advantage 应该偏正。

---

<a id="origin-8332"></a>
## 25. 只用一步 TD 为什么不够？

因为 LLM 一条回答可能：

```text
100 个 token
```

真正 reward 只在最后。

如果只看一步：

```text
第 1 个 token
只看到第 2 个 token 的 Value
```

奖励传播会非常依赖 Critic 精度。

所以使用 GAE：

\[
A_t^{GAE}
=
\delta_t
+
\gamma\lambda\delta_{t+1}
+
(\gamma\lambda)^2\delta_{t+2}
+\cdots
\]

递推形式：

\[
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
\]

---

<a id="origin-8376"></a>
## 26. 代码正是倒序执行 GAE（重点）

```python
for t in reversed(range(gen_len)):
    nv = (
        old_resp_values[:, t + 1]
        if t < gen_len - 1
        else 0.0
    )

    delta = (
        token_rewards[:, t]
        + gamma * nv
        - old_resp_values[:, t]
    )

    lastgaelam = (
        delta
        + gamma * lam * lastgaelam
    )
```

为什么必须倒序？

因为：

\[
A_t
\]

依赖：

\[
A_{t+1}
\]

所以必须先算后面，再算前面。

---

<a id="origin-8416"></a>
## 27. GAE 完整数值例子

假设回答 3 个 token：

```text
a1 a2 EOS
```

外部 reward：

```text
R = 2
```

所以：

\[
r_1=0,\quad r_2=0,\quad r_3=2
\]

Critic 旧预测：

\[
V_1=0.5,\quad
V_2=0.7,\quad
V_3=0.8
\]

设置：

\[
\gamma=1,\quad \lambda=0.95
\]

---

<a id="origin-8452"></a>
### 27.1 最后一个 token

下一状态 value 按代码取：

\[
V_4=0
\]

所以：

\[
\delta_3
=
2+0-0.8
=
1.2
\]

\[
A_3
=
1.2
\]

---

<a id="origin-8478"></a>
### 27.2 第二个 token

\[
\delta_2
=
0+0.8-0.7
=
0.1
\]

\[
A_2
=
0.1
+
0.95\times1.2
=
1.24
\]

---

<a id="origin-8500"></a>
### 27.3 第一个 token

\[
\delta_1
=
0+0.7-0.5
=
0.2
\]

\[
A_1
=
0.2
+
0.95\times1.24
=
1.378
\]

所以最终：

```text
A1 = 1.378
A2 = 1.240
A3 = 1.200
```

虽然：

```text
前两个 token 的直接 reward 都是 0
```

但最后 reward 已经通过 GAE 传回前面。

---

<a id="origin-8538"></a>
## 28. `Return = Advantage + Old Value` 是什么意思？

代码：

```python
returns = advantages + old_resp_values
```

因为：

\[
A_t
\approx
Q_t - V_{\text{old}}(s_t)
\]

所以：

\[
Q_t
\approx
A_t+V_{\text{old}}(s_t)
\]

这里的 `returns` 就作为 Critic 的训练目标。

注意一个非常重要的区分：

```text
Advantage
    → 主要给 Actor 用

Return / Value Target
    → 主要给 Critic 用
```

---

<a id="origin-8576"></a>
## 29. Advantage 为什么还要标准化？（重点）

代码：

```python
advantages =
    (advantages - mean)
    / sqrt(var + eps)
```

作用：

```text
原始 Advantage：
[-8, -1, 0.2, 3, 20]

标准化后：
大约变成均值 0、方差 1
```

这样做主要为了：

- 稳定梯度尺度；
- 减少不同 batch reward 尺度差异；
- 让 PPO 超参数更容易使用。

---

<a id="origin-8604"></a>
## 30. 进入真正 PPO 更新阶段

到现在为止：

> 还没有更新 Actor。

前面只是收集固定 rollout 数据：

```text
response token
old logp
old value
reference logp
advantage
return
mask
```

这份固定数据接下来会被重复利用：

```python
for ppo_epoch in range(
    args.ppo_update_iters
):
```

默认：

```text
2 轮
```

---

<a id="origin-8638"></a>
## 31. 为什么同一批数据可以更新多轮？

生成 LLM rollout 很贵。

如果：

```text
生成一次回答
只 backward 一次
然后扔掉
```

数据利用率很低。

PPO 的思路是：

> 同一批 rollout 可以做几轮更新，但必须限制新策略不要离 old policy 太远。

这就是：

```text
ratio clipping
+
approx KL early stop
```

存在的原因。

---

<a id="origin-8668"></a>
## 32. Mini-batch

假设：

```text
B = 8
mini_batch_size = 2
```

随机排列：

```text
[5,1,7,0,6,2,3,4]
```

切成：

```text
[5,1]
[7,0]
[6,2]
[3,4]
```

每个小批独立 forward/backward。

---

<a id="origin-8696"></a>
## 33. Critic 在更新阶段重新 forward

```python
mb_values_seq = critic_unwrapped(...)
mb_resp_values = mb_values_seq.gather(...)
```

为什么不能继续用：

```text
old_resp_values
```

因为：

```text
old_resp_values
    = PPO 更新前 Critic 的预测

mb_resp_values
    = 当前 Critic 参数下重新算出的预测
```

Critic 每更新一次后，后者都会变化。

---

<a id="origin-8723"></a>
## 34. Actor 也重新 forward

```python
res = actor_unwrapped(...)
```

再得到：

```python
mb_resp_logp
```

这就是：

\[
\log\pi_{\theta}(a_t|s_t)
\]

注意：

> Response token 没重新采样。

还是原来的 token。

变化的是：

> 当前 Actor 现在给这些旧动作多大概率。

---

<a id="origin-8753"></a>
## 35. 为什么 PPO 不重新生成 token？

因为 PPO 正在问：

> 对同一批已经发生过的动作，新策略和旧策略相比发生了多大变化？

所以动作必须固定。

否则：

```text
old policy 生成 A
new policy 重新生成 B
```

这两个概率没有办法直接作为同一个动作的 ratio。

---

<a id="origin-8772"></a>
## 36. `log_ratio`

代码：

```python
log_ratio = (
    mb_resp_logp
    -
    old_resp_logp
)
```

即：

\[
\log r_t
=
\log\pi_{\text{new}}
-
\log\pi_{\text{old}}
\]

然后：

```python
ratio = torch.exp(log_ratio)
```

得到：

\[
r_t
=
\frac{
\pi_{\text{new}}
}{
\pi_{\text{old}}
}
\]

---

<a id="origin-8814"></a>
## 37. 第一轮 PPO 更新开始时为什么 ratio 应该接近 1？

如果 rollout 刚刚由当前 Actor 生成：

```text
采样时 Actor
=
开始更新时 Actor
```

那么：

\[
\pi_{\text{new}}
=
\pi_{\text{old}}
\]

所以：

\[
r_t=1
\]

\[
\log r_t=0
\]

这就是源码提供 `debug_log_ratio` 的原因。

如果第一轮第一个 mini-batch 就偏离很大，可能意味着：

- rollout engine 权重没同步；
- dropout 等训练/推理状态造成差异；
- token 对齐有问题；
- log probability 计算逻辑不一致；
- 外部 rollout 引擎与本地 Actor 不完全一致。

---

<a id="origin-8854"></a>
## 38. Approx KL：防止一次 PPO 更新走太远

代码：

\[
\text{approx\_kl}
=
\frac12
(\log r_t)^2
\]

再对有效 token 求平均。

当：

\[
\log r_t
\]

很小时，它可以作为新旧策略变化幅度的近似量。

如果：

```python
approx_kl > early_stop_kl
```

则：

```python
stop_ppo = True
```

意思：

> 这一批 rollout 已经被利用得够多了，再继续更新可能偏离 old policy 太远。

---

<a id="origin-8893"></a>
## 39. 为什么 DDP 下要同步 KL？

假设：

```text
GPU0 approx_KL = 0.30
GPU1 approx_KL = 0.10
threshold       = 0.25
```

如果 GPU0 停，GPU1 不停：

```text
GPU0 少一次 backward
GPU1 多一次 backward
```

下一次 DDP 梯度同步时通信次序不一致，可能挂死。

因此：

```python
dist.all_reduce(
    approx_kl_val,
    op=AVG
)
```

让所有卡基于相同平均 KL 做决定。

---

<a id="origin-8925"></a>
## 40. PPO Clip 到底在防什么？

假设某 token：

\[
A_t>0
\]

说明：

> 这个 token 比预期好，希望提高它的概率。

普通 policy gradient 可能会疯狂提高：

```text
old probability = 0.10
new probability = 0.30
```

ratio：

\[
3.0
\]

变化太大。

PPO 限制：

\[
r_t
\in
[1-\epsilon,1+\epsilon]
\]

默认：

\[
\epsilon=0.2
\]

也就是大致：

```text
[0.8,1.2]
```

---

<a id="origin-8974"></a>
## 41. PPO Actor Loss 的经典公式

目标是最大化：

\[
L^{CLIP}
=
\mathbb{E}
\left[
\min
\left(
r_t A_t,
\operatorname{clip}
(r_t,1-\epsilon,1+\epsilon)
A_t
\right)
\right]
\]

但优化器默认最小化 loss。

所以写成：

\[
L_{\text{policy}}
=
-
L^{CLIP}
\]

源码用：

```python
max(
    -A * ratio,
    -A * clipped_ratio
)
```

正好等价。

---

<a id="origin-9017"></a>
## 42. Advantage > 0 时，PPO 在做什么？

假设：

\[
A=2
\]

说明动作比预期好。

若：

\[
ratio=1.1
\]

则：

```text
提高概率是允许的
```

若：

\[
ratio=1.8
\]

就太激进。

clip 到：

\[
1.2
\]

避免继续获得“疯狂提高概率”的训练收益。

---

<a id="origin-9057"></a>
## 43. Advantage < 0 时呢？

假设：

\[
A=-2
\]

说明：

> 这个 token 比预期差，希望降低概率。

但如果一下从：

```text
0.5
```

降到：

```text
0.01
```

也太激进。

所以 PPO 同样限制概率不能一次下降过头。

---

<a id="origin-9087"></a>
## 44. `clipfrac`

代码统计：

```python
abs(ratio - 1) > epsilon
```

的有效 token 比例。

例如：

```text
1000 个 token
其中 220 个超出 clipping 区间
```

则：

```text
clipfrac = 0.22
```

它是一个重要诊断指标：

> 越高说明当前 update 越多 token 已经撞到 clipping 边界。

---

<a id="origin-9116"></a>
## 45. Reference KL Penalty （重点）

源码：

```python
x = ref_logp - new_logp

exp(x) - x - 1
```

逐 token 形式：

\[
e^x-x-1
\]

其中：

\[
x
=
\log\pi_{\text{ref}}
-
\log\pi_{\text{new}}
\]

这个函数满足：

\[
e^x-x-1\ge 0
\]

**而且当 \(x\) 很小时（泰勒公式展开）：**

\[
e^x
\approx
1+x+\frac{x^2}{2}
\]

所以：

\[
e^x-x-1
\approx
\frac{x^2}{2}
\]

也就是说：

> 当 new 与 ref 很接近时，它近似一个二次偏离惩罚。

从合适的采样分布取期望时，它与 KL 估计有直接关系；在这份实现里，可以把它稳妥理解为：

> **一个 token 级的 reference-policy KL-like penalty。**

最后：

\[
L_{\text{actor}}
=
L_{\text{PPO clip}}
+
\beta
L_{\text{ref penalty}}
\]

其中：

```text
beta = args.kl_coef
```

---

<a id="origin-9191"></a>
## 46. 一个极其重要的实现细节：本代码有两种“KL”

**先给结论：当 \(x\) 接近 0 时，\(\frac12x^2\) 和 \(e^x-x-1\) 数值差不多，可以近似看作一样。**

\[
\boxed{e^x-x-1\approx\frac12x^2\qquad(x\approx0)}
\]

因为：

\[
e^x-x-1=\frac12x^2+\frac16x^3+\cdots
\]

\(x\) 很小时，后面的高阶项很小，所以两种写法差别很小。**这里的“差不多”有 \(x\approx0\) 这个前提；\(x\) 较大时，两者会有明显差别。**

先记住这个结论，再看下面它们分别比较哪个 Policy，以及取哪个分布的期望。代码中的两个变量都是对有效回答 Token 求平均后的估计／代理量。

<a id="origin-9209"></a>
### 46.1 第一种：new vs old

```python
approx_kl
```

用途：

```text
PPO early stop
```

意思：

> 这一轮 update 是否已经离采样策略太远？

---

<a id="origin-9227"></a>
### 46.2 第二种：new vs reference

```python
kl_ref_penalty
```

用途：

```text
直接加到 policy loss
```

意思：

> 当前模型是否离原始参考模型太远？

---

<a id="origin-9245"></a>
### 46.3 为什么 PPO 中两种 KL 写法不一样？

**先记住：当 \(x\approx0\) 时，两种写法数值很接近。** 进一步解释它们与 KL 的关系时，再区分三个层次：单个 Token 的计算项、对指定分布取期望、有限样本上的经验平均。 不能直接把单个 Token 的 \(\frac12x^2\) 或 \(e^x-x-1\) 写成整个 KL。

固定状态 \(s\) 时，KL 的定义是：

\[
D_{\mathrm{KL}}(q\|p)
=\sum_a q(a\mid s)\log\frac{q(a\mid s)}{p(a\mid s)}
=\mathbb E_{a\sim q(\cdot\mid s)}
\left[\log\frac{q(a\mid s)}{p(a\mid s)}\right]
\]

所以，除了比较哪两个 Policy，还必须说明：**log 比值的方向、动作从哪个分布采样、取期望还是只看样本值。**

\(e^x-x-1\approx\frac12x^2\) 是单样本函数在 \(x\approx0\) 时的关系；它不能替代上面的期望和采样条件。

---

<a id="origin-9264"></a>
#### 46.3.1 new/old：代码算的是二次项的经验平均

本代码使用：

\[
x_{i,t}^{\mathrm{old/new}}
=\log\pi_\theta(a_{i,t}\mid s_{i,t})
-\log\pi_{\mathrm{old}}(a_{i,t}\mid s_{i,t})
\]

\[
\boxed{
\widehat K_{\mathrm{old/new}}
=\frac{\sum_{i,t}m_{i,t}\,\frac12(x_{i,t}^{\mathrm{old/new}})^2}
{\sum_{i,t}m_{i,t}}
}
\]

这里的 \(m_{i,t}\) 是有效回答掩码。**\(\frac12x^2\) 是单个 Token 的项，完整的 `approx_kl` 是对有效 Token 求平均后的标量。**

在固定状态、动作按旧策略采样的标准设定下，它估计：

\[
\mathbb E_{a\sim\pi_{\mathrm{old}}}
\left[\frac12\left(\log\frac{\pi_\theta(a\mid s)}
{\pi_{\mathrm{old}}(a\mid s)}\right)^2\right]
\]

这个期望通常不等于精确 KL；当两个分布足够接近时，它与 \(D_{\mathrm{KL}}(\pi_{\mathrm{old}}\|\pi_\theta)\) 二阶一致，适合作为近似监控量。有限样本还会带来采样误差。

---

<a id="origin-9296"></a>
#### 46.3.2 policy/reference：注意本代码中 log 比值的方向

本代码实际使用：

\[
\boxed{
x_{i,t}^{\mathrm{ref/new}}
=\log\pi_{\mathrm{ref}}(a_{i,t}\mid s_{i,t})
-\log\pi_\theta(a_{i,t}\mid s_{i,t})
}
\]

**这里是 ref 减 new，原文写成 policy 减 ref 与源码不符。** 平方会消去符号差异，\(e^x-x-1\) 则不会。

每个 Token 上计算：

\[
k_{i,t}^{\mathrm{ref}}=e^{x_{i,t}^{\mathrm{ref/new}}}
-x_{i,t}^{\mathrm{ref/new}}-1
\]

然后才得到代码中的参考惩罚：

\[
\boxed{
\widehat K_{\mathrm{ref}}
=\frac{\sum_{i,t}m_{i,t}k_{i,t}^{\mathrm{ref}}}
{\sum_{i,t}m_{i,t}}
}
\]

它同样是有效 Token 上的经验平均。它在什么条件下对应哪个 KL，必须结合期望所用的采样分布判断，见[真正要分清：比较谁、向哪个方向比较、对谁取期望](../../%E8%AE%B2%E4%B9%89/PPO%20%E9%87%87%E6%A0%B7%E4%B8%8E%E8%AE%AD%E7%BB%83/b21-PPO%20%E8%AE%AD%E7%BB%83%E4%BB%A3%E7%A0%81.md#origin-9676)。

---

<a id="origin-9331"></a>
#### 46.3.3 两个单样本函数的局部关系：Taylor 展开

考虑：

\[
e^x
\]

在 \(x=0\) 附近做 Taylor 展开：

\[
e^x
=
1+x+\frac{x^2}{2}
+\frac{x^3}{6}
+\frac{x^4}{24}
+\cdots
\]

因此：

\[
e^x-x-1
\]

等于：

\[
1+x+\frac{x^2}{2}
+\frac{x^3}{6}
+\cdots
-x-1
\]

前面的：

\[
1
\]

和：

\[
x
\]

正好被消掉：

\[
e^x-x-1
=
\frac{x^2}{2}
+
\frac{x^3}{6}
+
\frac{x^4}{24}
+\cdots
\]

因此，当：

\[
x\approx0
\]

时，高阶项：

\[
x^3,\ x^4,\ldots
\]

都非常小。

于是：

\[
\boxed{
e^x-x-1
\approx
\frac12x^2
}
\]

这说明两个单样本函数在 x 接近 0 时的局部关系；它本身还不是包含采样分布与期望的 KL 公式。

---

<a id="origin-9418"></a>
#### 46.3.4 举一个具体数值例子

下面只比较单个样本上两个函数的数值，不把它们直接当作整个分布的 KL。

假设：

\[
x=0.05
\]

<a id="origin-9428"></a>
##### 46.3.4.1 第一种写法

\[
\frac12x^2
\]

得到：

\[
\frac12\times0.05^2
=
0.00125
\]

---

<a id="origin-9444"></a>
##### 46.3.4.2 第二种写法

\[
e^x-x-1
\]

得到：

\[
e^{0.05}-0.05-1
\]

因为：

\[
e^{0.05}\approx1.051271
\]

所以：

\[
1.051271-0.05-1
=
0.001271
\]

两者分别是：

```text
0.5 × x²          = 0.001250

exp(x) - x - 1    = 0.001271
```

几乎一样。

---

<a id="origin-9482"></a>
#### 46.3.5 old/new 的二次项为什么可以作为近似监控量？

若两个分布接近，并且相关 log 比值接近 0，则：

\[
e^x-x-1=\frac12x^2+O(x^3)
\]

因此，在相同采样分布下，二次项的期望可以近似对应的 \(e^x-x-1\) 的期望。

**这是局部近似，不是恒等式。** 不能因为 PPO 希望每次更新较小，就断言所有 Token 的 \(x\) 必然小，或者二次项已经精确等于 KL。`approx_kl` 的名称也体现了它是近似监控值。

---

<a id="origin-9496"></a>
#### 46.3.6 而且这个 `approx_kl` 经常只是拿来监控

例如：

```python
if approx_kl > target_kl:
    break
```

它的目的不是精确计算某个最终 Loss。

它更多是在判断：

```text
new policy
    ↓
是不是已经偏离 old policy 太远？
```

如果：

```text
偏得太远
```

就停止这一轮继续更新。

所以：

\[
\frac12x^2
\]

已经足够简单、稳定、便宜。

---

<a id="origin-9533"></a>
#### 46.3.7 reference 项为什么可以使用 \(e^x-x-1\)？

令 \(x=\log(\pi_{\mathrm{ref}}/\pi_\theta)\)。在固定状态、动作确实按当前 Policy \(\pi_\theta\) 采样、两个分布具有相同支持集时：

\[
\mathbb E_{a\sim\pi_\theta}\left[e^x-x-1\right]
=D_{\mathrm{KL}}(\pi_\theta\|\pi_{\mathrm{ref}})
\]

**关键是这个带采样分布的期望恒等式，而不只是“保留更多高阶信息”。**

本代码会复用旧 Rollout，实际动作不是每轮重新从当前 Policy 采样，因此还要区分上面的理想期望与本代码的经验代理惩罚，见[真正要分清：比较谁、向哪个方向比较、对谁取期望](../../%E8%AE%B2%E4%B9%89/PPO%20%E9%87%87%E6%A0%B7%E4%B8%8E%E8%AE%AD%E7%BB%83/b21-PPO%20%E8%AE%AD%E7%BB%83%E4%BB%A3%E7%A0%81.md#origin-9676)。

---

<a id="origin-9548"></a>
#### 46.3.8 当 \(x\) 变大时，两种公式开始有明显区别

例如：

\[
x=1
\]

第一种：

\[
\frac12x^2
=
0.5
\]

第二种：

\[
e^1-1-1
\]

因为：

\[
e\approx2.718
\]

所以：

\[
2.718-2
=
0.718
\]

已经有一定差异。

---

如果：

\[
x=2
\]

第一种：

\[
\frac12\times2^2
=
2
\]

第二种：

\[
e^2-2-1
\]

因为：

\[
e^2\approx7.389
\]

所以：

\[
7.389-3
=
4.389
\]

差异就非常明显了。

因此可以理解为：

```text
x 很小时：

exp(x) - x - 1
≈
0.5x²


x 较大时：

高阶项开始明显
```

**那么，哪一种更接近我们想估计的真正 KL？**

**在采样分布和 log 比值方向匹配的前提下，\(e^x-x-1\) 更直接：它的期望等于目标 KL；\(\frac12x^2\) 只是二阶近似。**

令 \(x=\log(p/q)\)，在两个分布具有相同支持集时：

\[
\boxed{
D_{\mathrm{KL}}(q\|p)
=\mathbb E_{a\sim q}[e^x-x-1]
\approx\mathbb E_{a\sim q}\left[\frac12x^2\right]
}
\]

- **\(x\) 很小时**：两者数值差不多。
- **偏离较大时**：平方项的近似误差可能明显，指数形式没有这层二阶近似误差。
- **只有有限样本时**：仍然有采样波动，不能保证指数形式在每一批中都更接近真实 KL。

这里说的是带有正确采样分布的期望，而不是单个 Token 的数值就等于 KL。本代码的 reference 项复用旧 Rollout，采样分布也会影响结果，不能只因使用了指数形式就认定它精确。

---

<a id="origin-9661"></a>
#### 46.3.9 不是“比较 old 就用平方，比较 reference 就用指数”

对 old/new，也可以令 \(x=\log(\pi_\theta/\pi_{\mathrm{old}})\)，在标准旧策略动作采样的设定下使用：

\[
\mathbb E_{a\sim\pi_{\mathrm{old}}}[e^x-x-1]
=D_{\mathrm{KL}}(\pi_{\mathrm{old}}\|\pi_\theta)
\]

再以样本平均估计这个期望。Stable-Baselines3 的 PPO 实现就采用这一类经验平均作早停监控，见其[源码](https://stable-baselines3.readthedocs.io/en/master/_modules/stable_baselines3/ppo/ppo.html)。

**选用哪个样本函数是一层问题，取哪个分布的期望、估计哪个方向的 KL 是另一层问题。不能只按比较对象给两种公式分工。**

---

<a id="origin-9676"></a>
#### 46.3.10 真正要分清：比较谁、向哪个方向比较、对谁取期望

**你看到的 \(\frac12x^2\) 和 \(e^x-x-1\)，首先都是单个样本上的函数。把它们与 KL 联系起来，必须写出期望。**

先固定状态 \(s\)，令 \(p,q\) 是两个具有相同支持集的概率分布：

\[
x(a)=\log\frac{p(a\mid s)}{q(a\mid s)}
\]

因为：

\[
\mathbb E_{a\sim q}[e^{x(a)}]
=\sum_a q(a\mid s)\frac{p(a\mid s)}{q(a\mid s)}
=1
\]

所以：

\[
\boxed{
\mathbb E_{a\sim q}[e^x-x-1]
=-\mathbb E_{a\sim q}[x]
=D_{\mathrm{KL}}(q\|p)
}
\]

**这才是完整关系：期望外面的 \(q\)、log 比值中的 \(p/q\) 和 KL 的方向必须对应起来。**

<a id="origin-9706"></a>
##### 46.3.10.1 New Policy 与 Old Policy

令：

\[
q=\pi_{\mathrm{old}},\qquad p=\pi_\theta,\qquad
x=\log\pi_\theta-\log\pi_{\mathrm{old}}
\]

则：

\[
D_{\mathrm{KL}}(\pi_{\mathrm{old}}\|\pi_\theta)
=\mathbb E_{a\sim\pi_{\mathrm{old}}}[e^x-x-1]
\]

本代码实际监控的是二次近似项的样本平均：

\[
\widehat K_{\mathrm{old/new}}
=\frac{\sum_{i,t}m_{i,t}\frac12x_{i,t}^2}{\sum_{i,t}m_{i,t}}
\]

所以它包含两层：**用二次项近似，以及用有限样本平均代替期望。** 其用途是监控当前 Policy 是否偏离采样时的旧 Policy 太远。

<a id="origin-9731"></a>
##### 46.3.10.2 Current Policy 与 Reference Policy

令：

\[
q=\pi_\theta,\qquad p=\pi_{\mathrm{ref}},\qquad
y=\log\pi_{\mathrm{ref}}-\log\pi_\theta
\]

则理想的期望恒等式为：

\[
\boxed{
D_{\mathrm{KL}}(\pi_\theta\|\pi_{\mathrm{ref}})
=\mathbb E_{a\sim\pi_\theta}[e^y-y-1]
}
\]

但是，本代码每轮更新都复用旧 Rollout，因而它对已有动作求平均，**不是每次重新按当前 \(\pi_\theta\) 采样后求平均**。在按旧策略采样的标准设定下，其平均对应的动作期望是：

\[
\mathbb E_{a\sim\pi_{\mathrm{old}}}[e^y-y-1]
\]

这个量一般不等于上式的 \(D_{\mathrm{KL}}(\pi_\theta\|\pi_{\mathrm{ref}})\)。当新旧 Policy 足够接近时，可以把它作为近似的参考 KL 代理惩罚；不能无条件称它为当前 Policy/reference KL 的精确值或无偏估计。

若在同一个固定状态下要严格把旧动作分布换成当前动作分布，需要相应的重要性权重：

\[
D_{\mathrm{KL}}(\pi_\theta\|\pi_{\mathrm{ref}})
=\mathbb E_{a\sim\pi_{\mathrm{old}}}
\left[
\frac{\pi_\theta(a\mid s)}{\pi_{\mathrm{old}}(a\mid s)}
(e^y-y-1)
\right]
\]

本代码的 `kl_ref_penalty` 没有乘这个权重。这里仅解释当前实现，没有修改训练代码。

<a id="origin-9770"></a>
##### 46.3.10.3 代码里的求和、除以有效 Token 数意味着什么？

对任一单 Token 计算项 \(k_{i,t}\)，代码最终计算：

\[
\widehat K
=\frac{\sum_{i,t}m_{i,t}k_{i,t}}{\sum_{i,t}m_{i,t}}
\]

**它是这批有效回答 Token 上的经验平均，用于估计相应采样过程下的期望。** Prompt 和补齐位置不计入这个平均。前面的 KL 恒等式针对固定状态的动作分布；跨不同状态求平均后，也不能直接称为完整轨迹分布的 KL。

以上按标准 PPO 中动作采样分布与保存的旧概率一致来推导。本仓库生成时还可能使用 temperature 等采样处理，而 old logp 保存原始模型概率；严格讨论无偏性时，还需要核对实际采样分布与这些概率是否一致。

---

<a id="origin-9785"></a>
#### 46.3.11 把样本项、期望和经验平均连起来

```text
明确 log 比值的方向，以及动作的采样分布
                    ↓
为每个已采样 Token 计算 k2 = x²/2 或 k3 = exp(x)-x-1
                    ↓
用有效 Token 的样本平均，估计该采样过程下的期望
                    ↓
再判断：这个期望精确对应哪个 KL，还是某种近似／代理量
```

Taylor 展开只说明 \(k_3(x)\approx k_2(x)\) 的局部函数关系，不会自动补上期望，也不会改变采样分布。

---

<a id="origin-9801"></a>
#### 46.3.12 放到 PPO 训练里看

可以把 PPO 里面两个约束理解成：

```text
                 PPO Policy
                    │
        ┌───────────┴───────────┐
        ↓                       ↓
和 Old Policy 比             和 Ref Model 比
        │                       │
        ↓                       ↓
一次更新别走太远            整个 RLHF 别跑偏
        │                       │
        ↓                       ↓
old/new KL                  policy/ref KL
        │                       │
        ↓                       ↓
常见：0.5x²             常见：exp(x)-x-1
```

但注意：

```text
这只是常见写法
不是数学规定
```

---

<a id="origin-9831"></a>
#### 46.3.13 最终一句话总结

> **不能只看“比较谁”或单个 Token 上的公式。必须同时看 log 比值方向、动作采样分布，以及是否用样本平均估计期望。本代码的 old/new 项是二次近似监控值，reference 项是在旧 Rollout 上计算的经验代理惩罚；两者都不能省略条件后直接写成精确 KL。**

公式形式可对照 [verl 的 KL 计算源码](https://verl.readthedocs.io/en/latest/_modules/verl/trainer/ppo/core_algos.html)，其中也明确区分了单样本 KL 估计量与将其作为训练损失使用时的梯度问题。

---

<a id="origin-9839"></a>
## 47. 本代码没有把 reference KL 加入 token reward

有一些 RLHF 实现会写：

\[
r_t
=
r_t^{RM}
-
\beta
\left(
\log\pi_\theta
-
\log\pi_{ref}
\right)
\]

也就是：

> 把 KL 直接作为 token reward shaping。

但这份代码不是这样。

这里：

```text
token_rewards
    ← 只在最终 token 加 external reward

reference KL
    ← 在 policy_loss 里单独加惩罚
```

这是理解本实现与其他 PPO/RLHF 实现差异的关键。

---

<a id="origin-9876"></a>
## 48. Critic Loss （重点）

<a id="origin-9878"></a>
### 48.1 先明确：公式里的 R 是什么？

本节公式里的 \(R\) 是 **Return，也就是 Critic 要拟合的目标回报**。为了明确它对应哪个 token，下面统一写成 \(R_t\)：

\[
\boxed{R_t = Return_t = \text{当前状态 }s_t\text{ 对应的目标回报}}
\]

这里的 \(s_t\) 是生成第 \(t\) 个回答 token 之前的状态，即“Prompt + 已生成的回答前缀”。Critic 要根据这个前缀，预测从现在继续生成还能获得多少回报。

因此要区分：

| 符号 / 变量 | 含义 |
| --- | --- |
| \(r_t\) / `token_rewards[:, t]` | 当前一步的即时奖励 |
| \(R_t\) / `returns[:, t]` | 当前状态的目标回报，作为 Critic 的训练标签 |
| \(V_{\text{old}}(s_t)\) / `old_resp_values[:, t]` | 本轮 PPO 更新前，旧 Critic 对该状态的预测 |
| \(V_{\text{new}}(s_t)\) / `mb_resp_values[:, t]` | 训练时重新 forward 得到的当前 Critic 预测 |

**本节的 \(R_t\) 表示 Return；张量形状 `[B, R]` 中的 `R` 表示回答宽度。两处只是用了同一个字母，含义不同。**

<a id="origin-9899"></a>
### 48.2 这份代码里的 R_t 是怎样算出来的？

先看最直接的回报概念。对于一条完整结束的回答，若最后一个有效 token 的下标是 \(T-1\)，从当前位置开始的折扣累计奖励为：

\[
G_t = r_t + \gamma r_{t+1} + \gamma^2 r_{t+2}
+ \cdots + \gamma^{T-1-t}r_{T-1}
\]

但是，这份代码实际给 Critic 使用的目标，是由 **GAE Advantage 加旧 Value** 构造的回报估计：

\[
\boxed{R_t = A_t^{\mathrm{GAE}} + V_{\text{old}}(s_t)}
\]

对应源码：

```python
advantages = torch.stack(advs_rev[::-1], dim=1)  # 原始 GAE Advantage
returns = advantages + old_resp_values         # Critic 的目标 R_t
```

可以把它读成：

> 旧 Critic 原来预测能得到这么多回报，再加上 GAE 根据本次采样得到的修正量，就得到这次训练使用的目标回报。

其中，GAE 先计算每一步的 TD Error：

\[
\delta_t = r_t + \gamma V_{\text{old}}(s_{t+1})
- V_{\text{old}}(s_t)
\]

再从后向前递推：

\[
A_t^{\mathrm{GAE}} = \delta_t + \gamma\lambda A_{t+1}^{\mathrm{GAE}}
\]

对于这份代码按终止处理的回答，最后一个有效 token 之后的 Value 和 Advantage 均按 0 处理。于是还可以展开成：

\[
\boxed{
R_t = V_{\text{old}}(s_t)
+ \delta_t
+ \gamma\lambda\delta_{t+1}
+ (\gamma\lambda)^2\delta_{t+2}
+ \cdots
+ (\gamma\lambda)^{T-1-t}\delta_{T-1}
}
\]

把递推关系代入，还能得到一个更直观的等价形式：

\[
R_t = r_t + \gamma\left[
(1-\lambda)V_{\text{old}}(s_{t+1}) + \lambda R_{t+1}
\right]
\]

也就是：**当前奖励，加上“下一状态旧 Value”和“下一步目标回报”的加权组合。**

- 当 \(\lambda=1\)，且末尾 Value 为 0 时，\(R_t\) 就退化为前面的折扣累计奖励 \(G_t\)。
- 当 \(\lambda<1\) 时，\(R_t\) 混合了实际奖励与旧 Critic 的估计，因此不必等于单纯把后续奖励累加得到的数。

这里的 \(A_t^{\mathrm{GAE}}\) 必须是**标准化之前**的 Advantage。源码先生成 `returns`，再标准化供 Actor 使用的 `advantages`；标准化不会改变已经算好的 `returns`。

<a id="origin-9966"></a>
### 48.3 用一条三个 token 的回答算出 R_t

假设回答有三个有效 token，Reward Model 给整条回答打分 2.0。按照这份代码，外部奖励只放在最后一个有效 token 上：

```text
token_rewards   = [0.0, 0.0, 2.0]
old_resp_values = [0.2, 0.4, 0.3]
gamma = 1.0
lambda = 0.95
```

从最后一个位置开始算：

**t = 2：最后一个 token。** 后面没有未来 Value：

\[
\delta_2 = 2.0 + 0 - 0.3 = 1.7
\]

\[
A_2 = 1.7,\qquad R_2 = A_2 + V_{\text{old}}(s_2)
= 1.7 + 0.3 = 2.0
\]

**t = 1：倒数第二个 token。** 当前即时奖励虽然是 0，但后续奖励会经由 GAE 传回来：

\[
\delta_1 = 0 + 0.3 - 0.4 = -0.1
\]

\[
A_1 = -0.1 + 0.95\times1.7 = 1.515
\]

\[
R_1 = 1.515 + 0.4 = 1.915
\]

**t = 0：第一个 token。**

\[
\delta_0 = 0 + 0.4 - 0.2 = 0.2
\]

\[
A_0 = 0.2 + 0.95\times1.515 = 1.63925
\]

\[
R_0 = 1.63925 + 0.2 = 1.83925
\]

汇总：

| 位置 t | 即时奖励 r_t | 旧 Value | 原始 GAE Advantage | 目标回报 R_t |
| --- | --- | --- | --- | --- |
| 0 | 0.0 | 0.2 | 1.63925 | 1.83925 |
| 1 | 0.0 | 0.4 | 1.515 | 1.915 |
| 2 | 2.0 | 0.3 | 1.7 | 2.0 |

所以，训练时 Critic 应当分别向下面三个目标靠近：

```text
第一个状态 → 1.83925
第二个状态 → 1.915
第三个状态 → 2.0
```

这些值都是对“从当前位置继续生成的回报”的估计。前两个位置的即时奖励为 0，目标回报仍然可以大于 0；又因为这里 \(\lambda=0.95\)，三个目标也不必全部等于最终评分 2.0。

<a id="origin-10036"></a>
### 48.4 把 R_t 放回 Critic Loss

在本轮同一批 Rollout 的 PPO 更新期间，\(R_t\) 和 \(V_{\text{old}}(s_t)\) 都固定。计算它们时使用了 `torch.no_grad()`，训练只通过当前预测 \(V_{\text{new}}(s_t)\) 更新 Critic。

Critic 要学习：

\[
V_\phi(s_t)
\approx
R_t
\]

最简单可以：

\[
(V_{\text{new}}(s_t)-R_t)^2
\]

但 PPO 同样不希望 Critic 一次变化太猛。

所以先构造：

\[
V_{\text{clip}}
=
\operatorname{clip}
(
V_{\text{new}},
V_{\text{old}}-\epsilon_v,
V_{\text{old}}+\epsilon_v
)
\]

即把\(V_\text{new}\)限制在\([V_{\text{old}}-\epsilon_v,
V_{\text{old}}+\epsilon_v]\)之间，然后比较：

\[
(V_{\text{new}}-R_t)^2
\]

和：

\[
(V_{\text{clip}}-R_t)^2
\]

取较大者。

逐 token 的计算逻辑（伪代码）：

```python
0.5 * max(
    (new_value - target_return) ** 2,
    (clipped_value - target_return) ** 2
)
```

也就是：

\[
\frac12
\max
\left[
(V_{\text{new}}-R_t)^2,
(V_{\text{clip}}-R_t)^2
\right]

\]

这让 Critic 不能通过跨很大一步轻易获得更小 loss。

---

<a id="origin-10109"></a>
## 49. 为什么 Critic 训练目标不是 Reward 本身？

因为 Reward 只有：

```text
整条回答最后一个分数
```

而 Critic 要预测：

```text
每个中间状态从现在开始的未来回报
```

因此训练目标应该是：

```text
Return / bootstrapped value target
```

而不是简单把：

```text
每一个 token 都回归到最终 reward
```

---

<a id="origin-10137"></a>
## 50. 总 Loss

正常情况下：

```python
loss = (
    policy_loss
    +
    vf_coef * value_loss
    +
    aux_loss
) / accumulation_steps
```

即：

\[
L
=
L_{\text{actor}}
+
c_vL_{\text{critic}}
+
L_{\text{MoE aux}}
\]

默认：

\[
c_v=0.5
\]

---

<a id="origin-10171"></a>
## 51. 为什么 Actor 和 Critic 可以放在同一个 `loss.backward()`？

虽然总 loss 写在一起，但计算图其实有不同分支：

```text
policy_loss
    ↓
Actor 参数

value_loss
    ↓
Critic 参数

aux_loss
    ↓
Actor 的 MoE 分支
```

因此一次：

```python
loss.backward()
```

会分别把梯度写到：

```text
actor_parameter.grad
critic_parameter.grad
```

然后两套 optimizer 分别 step。

---

<a id="origin-10206"></a>
## 52. Early Stop 时为什么还 `backward()`？

源码：

```python
if stop_ppo:
    loss = (
        policy_loss
        + vf_coef * value_loss
        + aux_loss
    ) * 0.0
```

然后仍然：

```python
loss.backward()
```

这样：

```text
计算图路径还在
梯度贡献 = 0
```

主要服务于 DDP 通信一致性。

可以理解为：

> “这一步我不想更新，但多卡程序的通信节奏仍然要对齐。”

---

<a id="origin-10240"></a>
## 53. 梯度累积

代码：

```python
loss = loss / accumulation_steps
loss.backward()
```

每次 backward 不立刻 step。

只有：

```python
grad_accum_step % accumulation_steps == 0
```

才：

```text
clip grad
optimizer.step
scheduler.step
zero_grad
```

---

<a id="origin-10268"></a>
## 54. 用数值例子理解梯度累积

假设：

```text
accumulation_steps = 4
```

四个 mini-batch 原始 loss：

```text
L1
L2
L3
L4
```

每次实际 backward：

\[
L_1/4,\;
L_2/4,\;
L_3/4,\;
L_4/4
\]

梯度累加后：

\[
\frac{
\nabla L_1+
\nabla L_2+
\nabla L_3+
\nabla L_4
}{4}
\]

再更新一次。

近似相当于：

> 用更大的有效 batch 做一次更新。

---

<a id="origin-10313"></a>
## 55. 一个源码级注意点：batch 尾部会主动 flush 梯度

如果一个 rollout batch 结束时：

```text
grad_accum_step
```

还没有整除：

```text
accumulation_steps
```

源码仍然会：

```python
optimizer.step()
zero_grad()
```

所以它不会把这一小段未完成累积的梯度一直拖到后面。

但要注意：

> 代码没有在这个 flush 后把 `grad_accum_step` 重新归零。

当 `accumulation_steps > 1` 且每个 rollout batch 的 mini-batch 数不能整除它时，后续计数与“实际已经清空的梯度”可能不完全对齐。

这是阅读当前源码时值得检查的实现细节。

---

<a id="origin-10346"></a>
## 56. 更新之后，Old Policy 会立刻变吗？

不会。

对当前这批 rollout：

```text
old_resp_logp
```

已经固定。

无论 Actor 被更新几次：

```text
old_resp_logp 永远不变
```

而：

```text
mb_resp_logp
```

每次 forward 都可能变化。

所以：

```text
第一次：
ratio ≈ 1

更新后：
ratio ≠ 1

继续更新：
ratio 可能进一步偏离 1
```

这正是 PPO clip 开始发挥作用的过程。

---

<a id="origin-10389"></a>
## 57. 那什么时候产生“新的 old policy”？

下一次 rollout。

新 Actor 生成下一批回答时：

```text
新采样时的 logp
```

会被保存成下一批数据的：

```text
old_resp_logp
```

所以“old”永远是：

> **相对于当前 rollout batch 而言的旧策略。**

不是永久固定的一个模型。

---

<a id="origin-10413"></a>
## 58. `rollout_engine.update_policy(actor_model)`

源码会在初始化后同步一次 Actor。

训练过程中又在：

```text
save_interval
或最后一个 step
```

调用更新。

这说明 rollout engine 可能维护：

- Actor 的独立副本；
- 甚至外部 SGLang 服务里的权重。

如果引擎内部确实是独立模型，那么：

> `update_policy` 决定生成端什么时候拿到新的 Actor 权重。

具体同步机制需要查看 `rollout_engine` 的实现，本文件本身无法确定。

---

<a id="origin-10439"></a>
## 59. 日志里每个指标什么意思？

<a id="origin-10441"></a>
### 59.1 `reward`

当前 rollout batch 的平均外部总奖励。

---

<a id="origin-10447"></a>
### 59.2 `approx_kl`

当前 Actor 相对于当前 rollout 的 old policy 改变有多大。

---

<a id="origin-10453"></a>
### 59.3 `kl_ref`

当前 Actor 相对于 frozen reference 的偏离惩罚。

---

<a id="origin-10459"></a>
### 59.4 `clipfrac`

有多少 token 的 ratio 超出了：

\[
[1-\epsilon,1+\epsilon]
\]

---

<a id="origin-10469"></a>
### 59.5 `critic_loss`

Critic 回归 Return 的误差。

---

<a id="origin-10475"></a>
### 59.6 `avg_response_len`

平均生成长度。

---

<a id="origin-10481"></a>
### 59.7 `actor_lr / critic_lr`

当前两个 optimizer 的学习率。

---

<a id="origin-10487"></a>
## 60. 保存 Actor 权重

代码先 unwrap：

```text
DDP
torch.compile
```

拿到原始模型。

然后：

```python
state_dict()
```

再：

```python
half().cpu()
```

保存。

这是一个偏部署/轻量保存的 Actor 权重文件。

---

<a id="origin-10516"></a>
## 61. 为什么还要另外保存完整 checkpoint？

因为只保存 Actor state_dict 不够续训。

完整续训至少还需要：

```text
Actor 参数
Critic 参数
Actor optimizer
Critic optimizer
Actor scheduler
Critic scheduler
epoch
step
实验日志 ID
```

否则：

> 模型参数虽然回来了，但 AdamW 的一阶/二阶动量、学习率进度等都丢了。

这就是：

```python
lm_checkpoint(...)
```

保存完整状态的意义。

---

<a id="origin-10548"></a>
## 62. 把一条样本从头到尾用数字走一遍

现在假设只有一条 Prompt。

<a id="origin-10552"></a>
### 62.1 Prompt

```text
Q：1+1 等于多少？
```

token 后：

```text
[10,11,12,13]
```

所以：

\[
P=4
\]

---

<a id="origin-10572"></a>
### 62.2 Actor rollout

生成：

```text
[51,52,EOS]
```

完整序列：

```text
[10,11,12,13,51,52,EOS]
```

---

<a id="origin-10588"></a>
### 62.3 old log probability

rollout 时：

```text
token 51: logp = -0.50
token 52: logp = -0.20
EOS:      logp = -0.10
```

所以：

\[
old\_logp=
[-0.50,-0.20,-0.10]
\]

---

<a id="origin-10607"></a>
### 62.4 Reward

假设：

```text
长度奖励        +0.5
thinking 奖励   +0.0
重复惩罚        -0.0
RM 分数          +1.5
```

总 reward：

\[
R=2.0
\]

---

<a id="origin-10626"></a>
### 62.5 token reward

```text
[0,0,2.0]
```

---

<a id="origin-10634"></a>
### 62.6 Critic old value

假设：

```text
[0.5,0.7,0.8]
```

---

<a id="origin-10644"></a>
### 62.7 GAE

前面已经算出：

```text
A:
[1.378,1.240,1.200]
```

Return：

\[
Return=A+V
\]

所以：

```text
[1.878,1.940,2.000]
```

注意最后一个：

\[
1.2+0.8=2.0
\]

正好回到最终 reward。

---

<a id="origin-10675"></a>
### 62.8 PPO 更新前第一次 forward

假设 new logp 仍然：

```text
[-0.50,-0.20,-0.10]
```

则：

```text
log_ratio = [0,0,0]
ratio     = [1,1,1]
```

---

<a id="origin-10692"></a>
### 62.9 第一次梯度更新

因为三个 Advantage 都是正的：

```text
Actor 会倾向提高这三个已生成 token 的概率。
```

假设更新后：

```text
new logp:
[-0.45,-0.16,-0.08]
```

---

<a id="origin-10709"></a>
### 62.10 第二轮 PPO

第一个 token：

\[
log\_ratio
=
-0.45-(-0.50)
=
0.05
\]

\[
ratio=e^{0.05}\approx1.051
\]

说明新策略给它的概率大约比 old policy 高 5.1%。

只要没有超过 clipping 范围：

```text
继续允许学习
```

---

<a id="origin-10735"></a>
### 62.11 如果更新太大

假设某 token：

\[
ratio=1.5
\]

而：

\[
\epsilon=0.2
\]

clipped ratio：

\[
1.2
\]

Actor 不会因为把好动作从：

```text
1.2 倍继续推到 1.5 倍
```

而继续获得同等训练收益。

这就是 PPO 的“Proximal”：

> 尽量待在旧策略附近更新。

---

<a id="origin-10769"></a>
## 63. Actor、Critic、Reward Model、Reference Model 到底各学什么？

| 模块 | 是否训练 | 输入 | 输出 | 学什么 |
|---|---:|---|---|---|
| Actor | 是 | Prompt + Response prefix | 下一个 token 概率 | 哪些 token 更值得生成 |
| Critic | 是 | Prompt + Response prefix | 标量 Value | 当前状态未来预计回报 |
| Reward Model | 否 | Prompt + 完整 Answer | 标量分数 | 在 PPO 阶段只负责评分 |
| Reference Model | 否 | Prompt + Response prefix | token 概率 | 只作为“别偏离太远”的锚点 |

---

<a id="origin-10780"></a>
## 64. PPO 中最重要的两个监督信号

<a id="origin-10782"></a>
### 64.1 Actor 看的是

\[
Advantage
\]

含义：

> 这次动作相对 Critic 的预期，到底更好还是更差？

---

<a id="origin-10794"></a>
### 64.2 Critic 看的是

\[
Return
\]

含义：

> 这个状态真正应该预测成多少未来回报？

---

<a id="origin-10806"></a>
## 65. 为什么 Reward Model 不直接训练 Actor？

因为 Reward Model 输出：

```text
2.0
```

并不能直接告诉语言模型：

```text
“第 17 个 token 的哪个 logits 应该增大多少？”
```

PPO 做的事情就是构造这条桥：

\[
Reward
\rightarrow
Advantage
\rightarrow
\log\pi(a_t|s_t)
\rightarrow
Actor Gradient
\]

---

<a id="origin-10834"></a>
## 66. 为什么需要 Critic？不用行不行？

理论上可以直接使用 Monte Carlo Return：

\[
G_t
\]

做 REINFORCE：

\[
\nabla J
\approx
G_t
\nabla\log\pi(a_t|s_t)
\]

但问题是方差很大。

Critic 提供 baseline：

\[
A_t
=
Q_t-V(s_t)
\]

于是：

```text
这次 reward = 3
```

本身并不能说明“好”。

如果 Critic 原来只期待：

```text
1
```

那么：

```text
3 很好
```

如果 Critic 原来期待：

```text
5
```

那么：

```text
3 反而低于预期
```

所以 Advantage 比裸 Reward 更适合告诉 Actor：

> 这次动作到底值得增加还是降低概率。

---

<a id="origin-10899"></a>
## 67. 为什么 PPO 还要 Value Clipping？

Actor 有 clipping 是因为：

> 策略一次不能变太猛。

Critic 也可能发生：

```text
V_old = 0.5
一次更新后 V_new = 5.0
```

这种大跳同样会让下一轮 Advantage 估计不稳定。

所以 Critic 也做：

```text
old value 附近的 clipping
```

---

<a id="origin-10922"></a>
## 68. 这份代码里 `gamma=1.0` 意味着什么？

一般：

\[
0<\gamma\le1
\]

是未来奖励折扣。

本文件默认：

\[
\gamma=1
\]

表示：

> 后面的 reward 不因为“距离更远”本身而额外衰减。

这在有限长度 LLM response 里很常见。

但 GAE 仍然有：

\[
\lambda=0.95
\]

所以优势递推中仍有：

\[
0.95
\]

的衰减/平滑。

---

<a id="origin-10960"></a>
## 69. `lambda=0.95` 在做什么？

GAE 是 bias-variance tradeoff。

直觉：

```text
lambda 小
→ 更依赖一步 TD
→ 方差低
→ 更依赖 Critic
→ bias 可能更大

lambda 接近 1
→ 看得更远
→ 更接近完整 return
→ bias 小一些
→ 方差可能更大
```

默认：

```text
0.95
```

是常见折中。

---

<a id="origin-10990"></a>
## 70. `clip_epsilon=0.2`

PPO ratio 大致限制在：

\[
[0.8,1.2]
\]

不是说真实概率绝对不能超出这个范围。

而是：

> 超出后，surrogate objective 不再继续奖励过度变化。

---

<a id="origin-11006"></a>
## 71. `early_stop_kl=0.25`

这是第二层保险。

即使 clip objective 已经存在，如果总体：

```text
new vs old
```

偏离过大，直接停止继续利用这一批 rollout。

所以：

```text
clip
    = token 层面的局部限制

early-stop KL
    = 整批更新层面的整体刹车
```

---

<a id="origin-11030"></a>
## 72. `kl_coef=0.02`

控制：

```text
当前 Actor 偏离 Reference 的代价
```

过大：

```text
Actor 很难离开原模型
强化学习作用变弱
```

过小：

```text
Actor 可能为了 reward 大幅漂移
```

---

<a id="origin-11053"></a>
## 73. `vf_coef=0.5`

总 loss 中 Critic loss 权重：

\[
L
=
L_{\text{policy}}
+
0.5L_{\text{value}}
+\cdots
\]

它控制 Actor 与 Critic 梯度尺度的相对贡献。

---

<a id="origin-11070"></a>
## 74. 为什么 rollout 和 update 要分开？

这是 PPO 最核心的“on-policy-ish”结构：

```text
先冻结一批行为数据
↓
把产生它们的概率记成 old policy
↓
对这批固定数据做有限次数更新
↓
不能离 old 太远
↓
重新 rollout
```

如果无限次重复训练旧 rollout：

> 数据越来越 off-policy，PPO ratio 的方差和失真都会越来越大。

---

<a id="origin-11092"></a>
## 75. 一张总流程图

```text
┌──────────────────────┐
│      Dataset         │
│       Prompt         │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│      Tokenizer       │
│ input_ids / mask     │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│  Rollout Engine      │
│   Current Actor      │
└─────────┬────────────┘
          │
          ├── response tokens
          ├── old token logp
          └── response text
          │
          ▼
┌──────────────────────┐
│    Reward Stage      │
│ rules + RM score     │
└─────────┬────────────┘
          │
          │ sequence reward R
          ▼
┌──────────────────────┐
│   Old Critic Value   │
│   V_old(s_t)         │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│ Reference Model      │
│ log π_ref(a_t|s_t)   │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│ token reward         │
│ [0,0,...,R]          │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│       GAE            │
│ Advantage / Return   │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────────────────────┐
│         PPO Update × K               │
│                                      │
│ Current Actor → new logp             │
│       │                              │
│       ├─ new-old → ratio → clip      │
│       └─ new-ref → KL penalty        │
│                                      │
│ Current Critic → new value           │
│       └─ return → value loss         │
└─────────┬────────────────────────────┘
          │
          ▼
┌──────────────────────┐
│ backward             │
│ grad accumulation    │
│ grad clipping        │
│ optimizer.step       │
└─────────┬────────────┘
          │
          ▼
┌──────────────────────┐
│ Sync rollout policy  │
│ Save checkpoint      │
└──────────────────────┘
```

---

<a id="origin-11177"></a>
## 76. 最后把 PPO 核心公式和代码变量一一对应

<a id="origin-11179"></a>
### 76.1 概率比

\[
r_t(\theta)
=
\frac{\pi_\theta(a_t|s_t)}
{\pi_{\text{old}}(a_t|s_t)}
\]

代码：

```python
log_ratio = (
    mb_resp_logp
    -
    old_resp_logp
)

ratio = torch.exp(log_ratio)
```

---

<a id="origin-11202"></a>
### 76.2 TD Error

\[
\delta_t
=
r_t
+
\gamma V(s_{t+1})
-
V(s_t)
\]

代码：

```python
delta = (
    token_rewards[:, t]
    + gamma * nv
    - old_resp_values[:, t]
)
```

注意：

> 这里公式中的 \(r_t\) 是 reward，不是 PPO ratio。两个符号常常都写成 \(r\)，应区分成 `reward_t` 和 `ratio_t`。

---

<a id="origin-11230"></a>
### 76.3 GAE

\[
A_t
=
\delta_t
+
\gamma\lambda A_{t+1}
\]

代码：

```python
lastgaelam = (
    delta
    + gamma * lam * lastgaelam
)
```

---

<a id="origin-11251"></a>
### 76.4 Return

\[
R_t^{target}
=
A_t+V_{\text{old}}(s_t)
\]

代码：

```python
returns = (
    advantages
    + old_resp_values
)
```

---

<a id="origin-11270"></a>
### 76.5 PPO Clip Objective

\[
L^{CLIP}
=
\min
\left(
ratio_tA_t,
\operatorname{clip}(ratio_t)A_t
\right)
\]

代码以“最小化负目标”实现。

---

<a id="origin-11286"></a>
### 76.6 Value Loss

\[
L_V
=
\frac12
\max
\left[
(V_{\text{new}}-R)^2,
(V_{\text{clip}}-R)^2
\right]
\]

---

<a id="origin-11301"></a>
### 76.7 总损失

\[
L
=
L_{\text{policy}}
+
c_vL_V
+
L_{\text{aux}}
\]

其中 policy loss 自身已经包含 reference penalty。

---

<a id="origin-11317"></a>
## 77. 读完整份代码后，最应该记住的 12 句话

1. **Actor 负责生成 token，Critic 负责估计状态价值。**
2. **Reward Model 只给回答打分，不直接对 Actor 反向传播。**
3. **old policy 是“产生当前 rollout 的策略”，不是永远固定的 SFT 模型。**
4. **reference model 才是长期冻结的锚点。**
5. **old logp 用于 PPO ratio；ref logp 用于 reference KL 约束。**
6. **整条回答的 Reward 被放在最后一个有效 response token。**
7. **GAE 再把最终奖励的影响从后往前传播。**
8. **Advantage 告诉 Actor：这次动作比预期好还是差。**
9. **Return 告诉 Critic：这个状态的 Value 应该往哪里拟合。**
10. **PPO 可以重复利用同一批 rollout，但用 clip 和 KL early stop 防止更新过头。**
11. **Actor 和 Critic 虽然共用一个总 loss backward，但由两套 optimizer 分别更新。**
12. **下一轮 rollout 到来时，当前 Actor 才会成为新的 old policy。**

---

<a id="origin-11334"></a>
## 78. PPO 训练流程总结

如果只用 1 分钟解释这份代码：

```text
第一步，Actor 根据 Prompt 采样回答，并保存当时每个 token 的概率，
这就是 old policy。

第二步，Reward Model 给整条回答打分，
代码把这个分数放到最后一个 token。

第三步，Critic 给每个生成位置估计 Value，
GAE 从最后向前算出每个 token 的 Advantage 和 Return。

第四步，Actor 用 PPO：
如果 Advantage 为正，就提高该 token 概率；
如果为负，就降低概率；
但 new/old 的 ratio 不能变化太大。

第五步，Critic 用 Return 训练 Value，
同时 Actor 还受到 frozen reference model 的 KL 约束。

第六步，同一批 rollout 更新若干轮后重新生成新数据，
新的 Actor 在下一批 rollout 中就成为新的 old policy。
```

---

<a id="origin-11362"></a>
## 79. 这份源码中特别值得继续追的三个文件

如果要把“调用接口”继续深入到“内部实现”，下一步最值得看的是：

```text
trainer/rollout_engine.py
```

重点看：

```text
rollout()
update_policy()
per_token_logps 到底怎样计算
torch / sglang 两种实现怎样保持一致
```

第二个：

```text
trainer/trainer_utils.py
```

重点看：

```text
init_model()
LMForRewardModel
lm_checkpoint()
init_distributed_mode()
SkipBatchSampler
```

第三个：

```text
model/model_minimind.py
```

重点看：

```text
MiniMindForCausalLM.forward()
self.model(...)
logits 的具体形成
Critic 继承这个模型后 hidden state 的来源
```

当前讲义对这三个文件只按 `train_ppo.py` 暴露出来的接口职责解释，没有假设其未展示的内部实现。

---

<a id="origin-11414"></a>
## 80. 最后一张“变量字典”

| 变量 | 形状 | 含义 |
|---|---|---|
| `enc.input_ids` | `[B,P]` | padding 后 Prompt token |
| `gen_out` | `[B,P+R]` | Prompt + Response |
| `completion_ids` | `[B,R]` | Response token |
| `old_resp_logp` | `[B,R]` | rollout 时 Actor 对生成 token 的 logp |
| `rewards` | `[B]` | 每条回答总奖励 |
| `full_mask` | `[B,P+R]` | 完整序列非 PAD mask |
| `labels` | `[B,P+R-1]` | next-token labels |
| `resp_idx` | `[1,R]` | 回答内部位置 0..R-1 |
| `logp_pos` | `[B,R]` | 每个回答 token 对应的预测位置 |
| `resp_policy_mask` | `[B,R]` | PPO 有效回答 token mask |
| `values_seq` | `[B,P+R]` | Critic 对完整序列各位置的 Value |
| `old_resp_values` | `[B,R]` | rollout 时 response 对齐后的 old Value |
| `ref_resp_logp` | `[B,R]` | Reference 对生成 token 的 logp |
| `token_rewards` | `[B,R]` | token 级 reward，外部奖励只放末尾 |
| `advantages` | `[B,R]` | GAE Advantage |
| `returns` | `[B,R]` | Critic Value target |
| `mb_resp_values` | `[mb,R]` | 当前 Critic 的 Value |
| `mb_resp_logp` | `[mb,R]` | 当前 Actor 的 logp |
| `log_ratio` | `[mb,R]` | `new_logp-old_logp` |
| `ratio` | `[mb,R]` | `π_new/π_old` |
| `policy_loss` | scalar | Actor PPO + reference penalty |
| `value_loss` | scalar | Critic clipped value loss |
| `loss` | scalar | 最终反向传播损失 |

---

<a id="origin-11444"></a>
## 81. 一句话收尾

这份程序真正实现的不是“Reward Model 给分，然后训练语言模型”这么简单，而是：

\[
\boxed{
\text{Rollout}
\rightarrow
\text{Old Policy Statistics}
\rightarrow
\text{Reward}
\rightarrow
\text{Critic}
\rightarrow
\text{GAE}
\rightarrow
\text{PPO Ratio + Clip}
\rightarrow
\text{Actor/Critic Update}
}
\]

其中最核心的桥梁是：

\[
\boxed{
Reward
\rightarrow
Advantage
\rightarrow
Policy\ Gradient
}
\]

而 PPO 相比最普通 Policy Gradient 多出来的关键思想就是：

\[
\boxed{
\text{可以重复利用一批 rollout，但每次只能在 old policy 附近小步更新}
}
\]

这就是 **Proximal Policy Optimization** 中 “Proximal” 的本质。
