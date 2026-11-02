# Rollout 的 PyTorch 与 SGLang 实现


> 配套文件：`train_ppo.py`
>
> 这个文件最核心的作用不是“训练 PPO”，而是：
>
> **把“当前 Policy 如何生成回答”这一件事独立出来，并统一封装成本地 PyTorch 和远端 SGLang 两种实现。**

---

<a id="origin-11"></a>
## 1. 一句话先说清楚这个文件干什么

在 PPO 中，训练之前必须先让当前 Actor 真正生成回答：

```text
Prompt
  ↓
Current Policy
  ↓
真正采样 Response
  ↓
保存这次采样时：
- 生成了哪些 token
- 每个 token 当时的 log probability
- 哪些位置是真实回答、哪些是 PAD
- Prompt 到底有多长
  ↓
交给 train_ppo.py
  ↓
计算 Reward / GAE / PPO Loss
```

`rollout_engine.py` 就专门负责上面这一段。

所以可以把两个文件这样分工：

```text
train_ppo.py
    ↓
负责：
Reward
Critic
GAE
PPO ratio
Clip
KL
Backward
Optimizer Step


rollout_engine.py
    ↓
负责：
拿当前 Policy 生成回答
保存 old logp
整理 token
整理 mask
必要时把新 Actor 权重同步给采样端
```

---

<a id="origin-63"></a>
## 2. 为什么要单独写一个 `RolloutEngine`？

最直接的写法，其实可以把生成代码直接塞进：

```python
train_ppo.py
```

比如：

```python
output_ids = actor_model.generate(...)
```

但是这样会有一个问题：

> 如果以后不想用 PyTorch 原生 `generate()`，而是想用 SGLang、vLLM 或别的高性能推理后端，训练代码就得跟着一起改。

所以作者抽象出：

```python
RolloutEngine
```

训练代码只写：

```python
rollout_result = rollout_engine.rollout(...)
```

至于背后到底是：

```text
PyTorch 本地 generate
```

还是：

```text
HTTP 请求 SGLang
```

`train_ppo.py` 根本不用管。

这是一种很典型的软件工程思想：

\[
\boxed{
\text{训练逻辑}
\quad\text{和}\quad
\text{采样/推理后端}
\text{解耦}
}
\]

---

<a id="origin-120"></a>
## 3. 整个文件的结构

这个文件主要有 6 个部分：

```text
1. compute_per_token_logps()
      ↓
   根据完整生成序列
   重新计算每个回答 token 的 log probability


2. RolloutResult
      ↓
   统一定义 rollout 返回什么


3. RolloutEngine
      ↓
   抽象基类，规定所有 rollout backend 必须实现：
   rollout()
   update_policy()


4. TorchRolloutEngine
      ↓
   本地 PyTorch 直接 generate


5. SGLangRolloutEngine
      ↓
   HTTP 调远端 SGLang 生成


6. create_rollout_engine()
      ↓
   根据配置选择 Torch 或 SGLang
```

---

<a id="origin-160"></a>
## 4. 这个文件在 PPO 流程中的位置

```text
                 train_ppo.py

Prompt
  │
  ▼
Tokenizer
  │
  ▼
prompt_ids
attention_mask
  │
  ▼
┌───────────────────────────────┐
│       rollout_engine.py       │
│                               │
│  Current Policy 真正采样回答  │
│                               │
│  返回：                       │
│  output_ids                   │
│  completion_ids               │
│  old per-token logps          │
│  completion text              │
│  prompt lengths               │
│  completion mask              │
└───────────────┬───────────────┘
                │
                ▼
             Reward
                │
                ▼
             Critic
                │
                ▼
              GAE
                │
                ▼
        PPO New-vs-Old Ratio
                │
                ▼
              Loss
                │
                ▼
          optimizer.step()
                │
                ▼
         Actor 参数更新
                │
                ▼
 rollout_engine.update_policy()
                │
                ▼
让采样端以后使用新的 Policy
```

---

<a id="origin-219"></a>
## 5. PPO 中为什么 Rollout 特别重要？

SFT 中一般已经有标准答案：

```text
Prompt
+
Ground Truth Answer
```

所以直接 teacher forcing 就行。

但是 PPO 没有固定标准回答。

必须让：

```text
Current Actor
```

自己真正生成：

```text
Response
```

这一步就叫：

\[
\boxed{
Rollout
}
\]

例如：

```text
Prompt：
浙江大学软件学院在哪里？

Current Actor：
浙江大学软件学院位于宁波。
```

PPO 接下来训练的，就是这次真实发生的生成轨迹。

---

<a id="origin-267"></a>
## 6. Rollout 不只是需要 Response 文本

PPO 后面还需要：

```text
生成了哪些 token
每个 token 当初的概率是多少
Prompt 多长
Response 多长
哪里是真实 token
哪里是 PAD
```

例如：

```text
Prompt：
Q

Actor：
A B C EOS
```

PPO 后面不仅要知道：

```text
回答是 A B C
```

还必须知道：

```text
A 当初生成时概率是多少？
B 当初生成时概率是多少？
C 当初生成时概率是多少？
EOS 当初生成时概率是多少？
```

也就是：

\[
\log\pi_{\text{old}}(a_t|s_t)
\]

因为 PPO 后面要算：

\[
ratio_t
=
\frac{
\pi_{\text{new}}(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

所以：

> **Rollout 阶段必须把 Old Policy 的 token log probability 保存下来。**

---

<a id="origin-329"></a>
## 7. `compute_per_token_logps()` 是干什么的？

函数：

```python
def compute_per_token_logps(
    model,
    input_ids,
    n_keep,
    attention_mask=None
):
```

功能：

> 给定已经生成完成的 `Prompt + Response`，重新前向一次模型，取出最后 `n_keep` 个目标 token 的 log probability。

例如：

```text
完整序列：

Prompt            Response
10 11 12 13   |   51 52 EOS
```

如果：

```text
n_keep = 3
```

最终希望拿到：

```text
log P(51)
log P(52)
log P(EOS)
```

形状：

\[
[B,R]
\]

---

<a id="origin-377"></a>
## 8. 为什么已经 `generate()` 了，还要重新计算 log probability？

这是这个文件里非常重要的一点。

生成过程可能是：

```text
原始 logits
↓
temperature
↓
top-k / top-p
↓
过滤
↓
sample
```

但 PPO 后面要比较的是：

\[
\pi_{\text{policy}}(a_t|s_t)
\]

所以 Torch backend 在生成结束之后：

```text
固定已经生成出来的 token
↓
再 forward 一次原始模型
↓
log_softmax
↓
读取这些真实生成 token 的 log probability
```

代码注释也明确强调：

> 这里重新评估生成序列的原始模型 log 概率，并不是直接读取 temperature / top-p 过滤后的采样概率。

---

<a id="origin-419"></a>
## 9. `n_keep <= 0`

```python
if n_keep <= 0:
    return input_ids.new_empty(
        (input_ids.size(0), 0),
        dtype=torch.float32
    )
```

如果没有回答 token，就返回：

\[
[B,0]
\]

的空 Tensor。

这是边界条件处理。

---

<a id="origin-441"></a>
## 10. 为什么要 unwrap DDP？

```python
unwrapped = (
    model.module
    if isinstance(model, DistributedDataParallel)
    else model
)
```

如果模型被 DDP 包起来：

```text
model
↓
DistributedDataParallel Wrapper
↓
model.module
↓
真正的原始模型
```

所以需要拿：

```python
model.module
```

---

<a id="origin-471"></a>
## 11. `input_ids.is_inference()` 为什么还要 `detach().clone()`？

代码：

```python
input_ids = (
    input_ids.detach().clone()
    if input_ids.is_inference()
    else input_ids
)
```

某些 Tensor 可能来自：

```python
torch.inference_mode()
```

这种 Tensor 带有 inference 属性，缺少计算梯度等信息。

为了后面能作为普通 Tensor 安全使用，代码把它：

```text
detach
↓
clone
↓
变成独立普通 Tensor
```

---

<a id="origin-503"></a>
## 12. 最关键的一行：为什么 `logits_to_keep=n_keep+1`？

代码：

```python
logits = unwrapped(
    input_ids,
    attention_mask=attention_mask,
    logits_to_keep=n_keep + 1
).logits[:, :-1, :]
```

假设：

```text
Prompt 长度 = 4
Response 长度 = 3
```

完整序列：

```text
index:
0   1   2   3   4   5   6

token:
10  11  12  13  51  52  EOS
                └───────────┘
                 Response
```

语言模型预测关系：

```text
位置0 logits → 预测 11
位置1 logits → 预测 12
位置2 logits → 预测 13
位置3 logits → 预测 51
位置4 logits → 预测 52
位置5 logits → 预测 EOS
位置6 logits → 预测 EOS 后面的 token
```

我们真正关心的是：

```text
51
52
EOS
```

对应的是：

```text
logits[3]
logits[4]
logits[5]
```

如果只想通过“保留末尾 logits”的接口取出来，就先保留最后：

\[
R+1
\]

个位置：

```text
logits[3]
logits[4]
logits[5]
logits[6]
```

再：

```python
[:, :-1, :]
```

去掉最后一个：

```text
logits[6]
```

最后剩：

```text
logits[3]
logits[4]
logits[5]
```

正好预测：

```text
51
52
EOS
```

所以：

\[
\boxed{
n\_keep+1
}
\]

本质来自：

> **语言模型是 next-token prediction，因此预测位置比目标 token 位置提前 1。**

---

<a id="origin-619"></a>
## 13. `zip(logits, input_ids[:, -n_keep:])`

假设：

\[
logits.shape=[B,R,V]
\]

而：

\[
input\_ids[:,-R:].shape=[B,R]
\]

每次循环拿一条样本：

```text
logits_row：
[R,V]

ids_row：
[R]
```

---

<a id="origin-645"></a>
## 14. `log_softmax + gather`

代码：

```python
torch.gather(
    logits_row.log_softmax(dim=-1),
    1,
    ids_row.unsqueeze(1)
).squeeze(1)
```

先：

```python
logits_row.log_softmax(dim=-1)
```

得到：

\[
[R,V]
\]

也就是：

```text
每个 Response 位置
对整个词表的 log probability
```

例如第一个位置：

```text
token 0 → -4.2
token 1 → -2.0
token 2 → -0.7
token 3 → -3.6
...
```

如果真实生成 token 是：

```text
token 2
```

我们只需要：

```text
-0.7
```

`gather()` 就是干这个。

---

<a id="origin-702"></a>
## 15. 为什么 `ids_row.unsqueeze(1)`？

原来：

```text
ids_row.shape = [R]
```

例如：

```text
[51, 52, 2]
```

变成：

```text
[
 [51],
 [52],
 [ 2]
]
```

形状：

\[
[R,1]
\]

这样就可以沿：

```text
词表维 dim=1
```

每一行取出一个目标 token 的 log probability。

最后：

```python
.squeeze(1)
```

从：

\[
[R,1]
\]

变回：

\[
[R]
\]

---

<a id="origin-760"></a>
## 16. 最后 `torch.stack`

每条样本产生一个：

\[
[R]
\]

例如：

```text
sample0：
[-0.5,-0.2,-0.1]

sample1：
[-0.8,-0.3,-0.4]
```

最后：

```python
torch.stack(per_token_logps)
```

得到：

```text
[
  [-0.5,-0.2,-0.1],
  [-0.8,-0.3,-0.4]
]
```

形状：

\[
[B,R]
\]

这就是 PPO 后面使用的：

```text
old_resp_logp
```

---

<a id="origin-807"></a>
## 17. 为什么这个函数本身不写 `torch.no_grad()`？

源码注释明确说明：

> 函数自身不关闭梯度。

这是为了让这个函数保持通用。

如果调用方：

```python
with torch.no_grad():
    compute_per_token_logps(...)
```

就不建图。

如果调用方不关梯度，它仍然可以正常参与 autograd。

在当前 Torch rollout 里，它是在：

```python
with torch.no_grad():
```

里面调用的，所以得到的是：

```text
Old Policy 历史概率
```

不需要梯度。

---

<a id="origin-842"></a>
## 18. `RolloutResult` 是什么？

```python
@dataclass
class RolloutResult:
    output_ids: Tensor
    completion_ids: Tensor
    per_token_logps: Tensor
    completions: List[str]
    prompt_lens: Tensor
    completion_mask: Tensor
```

它就是：

> **一次 rollout 的统一结果容器。**

可以理解成一个“快递箱”，把 PPO 后面需要的采样信息一次性装好。

---

<a id="origin-863"></a>
## 19. 为什么用 `@dataclass`？

不用 dataclass 时，需要手写：

```python
class RolloutResult:
    def __init__(...):
        self.output_ids = ...
        self.completion_ids = ...
        ...
```

用了：

```python
@dataclass
```

以后只声明字段即可。

---

<a id="origin-885"></a>
## 20. 六个字段到底是什么？

假设：

```text
Prompt：
[10,11,12,13]

Response：
[51,52,EOS]
```

<a id="origin-897"></a>
### 20.1 `output_ids`

```text
[10,11,12,13,51,52,EOS]
```

即：

\[
Prompt+Response
\]

<a id="origin-909"></a>
### 20.2 `completion_ids`

```text
[51,52,EOS]
```

只包含回答。

<a id="origin-917"></a>
### 20.3 `per_token_logps`

```text
[-0.5,-0.2,-0.1]
```

表示：

\[
\log\pi_{\text{old}}(51)
\]

\[
\log\pi_{\text{old}}(52)
\]

\[
\log\pi_{\text{old}}(EOS)
\]

<a id="origin-937"></a>
### 20.4 `completions`

解码后的文本：

```text
"2。"
```

用于：

```text
Reward Model
规则 Reward
Debug
```

<a id="origin-953"></a>
### 20.5 `prompt_lens`

例如：

```text
4
```

后面 PPO 用它定位 Response 的预测位置。

<a id="origin-963"></a>
### 20.6 `completion_mask`

例如：

```text
[1,1,1,0,0]
```

表示：

```text
前三个是真实回答
后两个只是 PAD
```

---

<a id="origin-980"></a>
## 21. `RolloutEngine(ABC)` 是什么？

```python
class RolloutEngine(ABC):
```

`ABC`：

```text
Abstract Base Class
抽象基类
```

它不是一个真正工作的推理引擎。

它更像是在规定：

> “任何 Rollout Engine，都必须长成什么样。”

---

<a id="origin-1001"></a>
## 22. `@abstractmethod`

它规定两个方法必须由子类实现：

```python
rollout(...)
```

和：

```python
update_policy(...)
```

所以未来不管增加：

```text
Torch
SGLang
vLLM
TensorRT
```

只要实现相同接口，训练代码就不用改。

---

<a id="origin-1028"></a>
## 23. 为什么一定需要两个接口？

<a id="origin-1030"></a>
### 23.1 `rollout()`

负责：

```text
Prompt
↓
Current Policy
↓
Response
↓
Old LogP
```

<a id="origin-1044"></a>
### 23.2 `update_policy()`

负责：

```text
PPO 更新 Actor
↓
采样器同步新 Policy
↓
下一批 rollout 用新的 Policy
```

这两个正好对应在线 PPO 的：

```text
采样
↓
训练
↓
重新采样
```

循环。

---

<a id="origin-1070"></a>
## 24. `TorchRolloutEngine`

这是最简单的实现：

```text
训练模型
和
采样模型

都在同一个 Python 进程里
```

所以直接：

```python
model.generate(...)
```

就行。

---

<a id="origin-1092"></a>
## 25. 为什么 Torch rollout 要 `torch.no_grad()`？

```python
with torch.no_grad(), ctx:
```

Rollout 只是生成训练数据，不是在这里更新参数。

所以不需要：

```text
反向传播计算图
```

关闭梯度可以：

- 省显存；
- 减少 autograd 开销。

---

<a id="origin-1113"></a>
## 26. `ctx = autocast_ctx or nullcontext()`

如果开启混合精度，就用：

```text
autocast
```

否则：

```text
nullcontext()
```

什么都不做。

于是后面可以统一写：

```python
with torch.no_grad(), ctx:
```

---

<a id="origin-1137"></a>
## 27. `repeat_interleave(num_generations, dim=0)`

假设：

```text
B = 2

Prompt：
P1
P2

num_generations = 3
```

执行后：

```text
P1
P1
P1
P2
P2
P2
```

这样一个 Prompt 就可以采样多个回答。

---

<a id="origin-1166"></a>
## 28. `model.generate()` 关键参数

```python
max_new_tokens
```

最多生成多少 Response token。

```python
do_sample=True
```

表示真正采样，而不是永远选 argmax。

```python
temperature
```

控制采样随机性。

```python
pad_token_id
eos_token_id
```

分别告诉生成器：

```text
PAD 是谁
EOS 是谁
```

---

<a id="origin-1200"></a>
## 29. Torch backend 如何得到 `completion_ids`？

```python
prompt_len = prompt_ids.size(1)

completion_ids = output_ids[:, prompt_len:]
```

因为 Torch backend 中输入 Prompt 已经 padding 成统一宽度：

```text
[padded prompt | completion]
```

所以直接从统一的 `prompt_len` 后面切即可。

---

<a id="origin-1218"></a>
## 30. 为什么 Torch backend 的 `prompt_lens` 全一样？

返回：

```python
prompt_ids.new_full(
    (output_ids.size(0),),
    prompt_len
)
```

这里记录的是：

```text
padding 后统一 Prompt 宽度
```

所以 Torch backend 中每条都是同一个值。

---

<a id="origin-1239"></a>
## 31. 为什么 Torch backend 的 `completion_mask` 直接全 1？

代码：

```python
attention_mask.new_ones(
    output_ids.size(0),
    completion_ids.size(1)
)
```

也就是这一层先认为：

```text
Response 区域都有效
```

后面的 `train_ppo.py` 还会结合：

```text
PAD
EOS
```

重新构造最终：

```text
resp_policy_mask
```

所以最终 PPO 仍会裁掉无效位置。

---

<a id="origin-1273"></a>
## 32. Torch 的 `update_policy()` 为什么只有一行？

```python
def update_policy(self, model):
    self.policy_model = model
```

因为：

```text
训练 Actor
和
Rollout Actor

本质上在同一个 Python 进程中
```

直接替换引用即可。

不需要：

```text
保存文件
发 HTTP
远端 reload
```

---

<a id="origin-1302"></a>
## 33. `SGLangRolloutEngine` 为什么复杂很多？

因为它的结构是：

```text
训练进程
   │
   │ HTTP
   ▼
SGLang Server
   │
   ▼
独立推理模型
```

所以：

```text
Rollout
```

要发 HTTP 请求。

而：

```text
Policy 更新
```

也必须显式把新权重同步给远端。

---

<a id="origin-1335"></a>
## 34. SGLang 启动方式

文件开头给了示例：

```bash
python -m sglang.launch_server \
  --model-path ./minimind-3 \
  --attention-backend triton \
  --host 0.0.0.0 \
  --port 8998
```

也就是说训练脚本运行前，需要先有一个：

```text
SGLang 推理服务器
```

监听：

```text
8998
```

端口。

---

<a id="origin-1363"></a>
## 35. `base_url.rstrip('/')`

例如：

```text
http://localhost:8998/
```

变成：

```text
http://localhost:8998
```

这样后面拼：

```text
/generate
```

不会出现双斜杠。

---

<a id="origin-1387"></a>
## 36. 为什么 SGLang backend 自己也要 Tokenizer？

```python
AutoTokenizer.from_pretrained(...)
```

因为本地还要负责：

```text
completion token decode
EOS/PAD ID
保存 tokenizer
```

所以必须和服务端模型使用匹配的 tokenizer。

---

<a id="origin-1405"></a>
## 37. 为什么发给 SGLang 前先去掉左 PAD？

训练侧可能是：

```text
样本1：
[11,12,13,14]

样本2：
[PAD,PAD,21,22]
```

代码：

```python
valid_ids = ids[mask.bool()].tolist()
```

样本2变成：

```text
[21,22]
```

这样远端真正收到的是真实 Prompt。

---

<a id="origin-1433"></a>
## 38. 所以 SGLang 的 `prompt_lens` 每条可能不同

例如：

```text
Prompt1 = 4 tokens
Prompt2 = 2 tokens
```

最终：

```text
prompt_lens = [4,2]
```

因为左 PAD 已经被去掉。

---

<a id="origin-1452"></a>
## 39. `payload`

```python
payload = {
    "input_ids": all_input_ids,
    "sampling_params": {
        "temperature": temperature,
        "max_new_tokens": max_new_tokens,
        "stop_token_ids": [...]
    },
    "return_logprob": True
}
```

可以翻译成：

```text
“这些是 Prompt Token。

请按给定 temperature 和最大长度生成。

遇到 EOS 停止。

同时把生成 token 的 log probability 返回给我。”
```

---

<a id="origin-1480"></a>
## 40. `requests.post()`

```python
resp = self.http.post(
    f"{self.base_url}/generate",
    json=payload,
    timeout=self.timeout
)
```

向 SGLang：

```text
POST /generate
```

发送 JSON 请求。

---

<a id="origin-1500"></a>
## 41. `raise_for_status()`

如果服务返回：

```text
404
500
503
```

等异常 HTTP 状态，就直接抛异常。

避免后面把错误响应继续当正常生成结果处理。

---

<a id="origin-1516"></a>
## 42. SGLang 返回什么？

代码重点读取：

```python
output_ids
```

以及：

```python
output_token_logprobs
```

所以远端返回：

```text
生成了哪些 token
+
这些 token 的 logprob
```

---

<a id="origin-1540"></a>
## 43. 为什么 `raw_logprobs` 要兼容不同格式？

代码支持：

```text
[logprob, ...]
```

或者直接：

```text
logprob
```

说明作者在兼容不同服务返回格式。

---

<a id="origin-1558"></a>
## 44. 为什么 logprob 长度还要和 completion 对齐？

代码处理：

```python
len(logprobs)
<
len(completion_ids)
```

和：

```python
len(logprobs)
>
len(completion_ids)
```

说明远端 API 可能返回长度不完全一致。

---

<a id="origin-1580"></a>
## 45. 少了的 logprob 为什么补 `0.0`？

```python
logprobs = [0.0] * missing + logprobs
```

这里的：

```text
0.0
```

只是：

> **对齐占位。**

不是说真实概率：

\[
p=1
\]

因为：

\[
\log p=0
\Rightarrow p=1
\]

需要注意：

\[
\boxed{
这里的 0.0 是占位值，不是真实 old logp
}
\]

实际训练最好保证：

> 服务真正完整返回每个 completion token 的正确 logprob。

---

<a id="origin-1623"></a>
## 46. 为什么过长就取尾部？

```python
logprobs = logprobs[-len(completion_ids):]
```

因为真正关心的是：

```text
Completion 对应的 logprob
```

所以保留与 Completion 同长度的尾部。

---

<a id="origin-1639"></a>
## 47. 为什么需要重新构造 `full_output`？

```python
full_output = prompt + completion_ids
```

因为远端分别返回/保存：

```text
Prompt
Response
```

但 `train_ppo.py` 后面还需要：

```text
Prompt + Response
```

作为 Critic、Reference、Actor 的完整输入。

所以重新拼起来。

---

<a id="origin-1664"></a>
## 48. SGLang 为什么要自己 Padding？

不同回答可能长度不同：

```text
Response1：
A B EOS

Response2：
C D E F EOS
```

Python list 可以长度不同。

但是二维 Tensor 必须规整。

所以：

```text
Response1：
A B EOS PAD PAD

Response2：
C D E F EOS
```

---

<a id="origin-1692"></a>
## 49. `pad_to_tensor()`

```python
def pad_to_tensor(seqs, max_len, pad_val=0):
    return torch.tensor([
        s + [pad_val] * (max_len - len(s))
        for s in seqs
    ], device=device)
```

就是：

```text
所有序列
↓
补到相同 max_len
↓
组成二维 Tensor
```

---

<a id="origin-1714"></a>
## 50. `completion_mask`

假设：

```text
Response1 长度 = 3
Response2 长度 = 5
```

那么：

```text
sample1：
[1,1,1,0,0]

sample2：
[1,1,1,1,1]
```

这就告诉 `train_ppo.py`：

```text
哪些位置是真的生成 token
哪些位置只是 PAD
```

---

<a id="origin-1742"></a>
## 51. 为什么统一成 `RolloutResult` 很重要？

Torch 内部：

```text
本地 generate
本地重新算 logp
```

SGLang 内部：

```text
HTTP generate
服务直接返回 logp
自己重组 Tensor
```

内部完全不同。

但是最后都统一：

```python
RolloutResult(...)
```

所以训练代码只需要知道：

```python
rollout_result.output_ids
rollout_result.completion_ids
rollout_result.per_token_logps
rollout_result.completions
rollout_result.prompt_lens
rollout_result.completion_mask
```

这就是接口抽象的真正价值。

---

<a id="origin-1782"></a>
## 52. 两个 backend 对比

| 项目 | TorchRolloutEngine | SGLangRolloutEngine |
|---|---|---|
| 模型位置 | 训练进程内 | 外部 SGLang 服务 |
| 生成方式 | `model.generate()` | HTTP `/generate` |
| old logp | 本地重新 forward | 服务返回 |
| Prompt PAD | 保留统一 padded 宽度 | 发请求前去掉 PAD |
| Policy 更新 | 替换模型引用 | 导出权重 + 通知远端加载 |
| HTTP 开销 | 无 | 有 |
| 适合场景 | 简单、本地、小规模 | 独立高性能推理服务 |

---

<a id="origin-1796"></a>
## 53. `SGLangRolloutEngine.update_policy()` 是另一个重点

PPO 更新之后：

```text
训练端 Actor
已经是新权重
```

但远端 SGLang 可能还在使用：

```text
旧 Policy
```

所以必须：

```python
update_policy(model)
```

同步。

---

<a id="origin-1821"></a>
## 54. 为什么只让 Rank 0 更新远端？

代码：

```python
if not dist.is_initialized() or dist.get_rank() == 0:
```

多 GPU DDP 下：

```text
rank0
rank1
rank2
rank3
```

模型参数经过同步后应该一致。

所以完全没必要：

```text
4 个 rank
同时写 checkpoint
同时发 4 个 HTTP 请求
```

只需要：

```text
rank0
```

执行一次。

---

<a id="origin-1858"></a>
## 55. 为什么还要 unwrap `torch.compile`？

```python
unwrapped = getattr(
    unwrapped,
    "_orig_mod",
    unwrapped
)
```

如果模型经过：

```python
torch.compile()
```

原始模型可能在：

```python
_orig_mod
```

里面。

所以：

```text
DDP
↓
.module

compile
↓
._orig_mod

最终拿到真正原始模型
```

---

<a id="origin-1898"></a>
## 56. 导出新 Policy 权重

```python
state_dict = {
    k: v.detach().half().cpu()
    for k, v in unwrapped.state_dict().items()
}
```

含义：

```text
新 Actor 参数
↓
detach
↓
FP16
↓
CPU
↓
准备保存
```

---

<a id="origin-1923"></a>
## 57. `save_pretrained()`

```python
unwrapped.save_pretrained(...)
```

把模型按 Transformers 风格保存到：

```text
shared_ckpt_path
```

Tokenizer 也：

```python
self.tokenizer.save_pretrained(abs_path)
```

---

<a id="origin-1943"></a>
## 58. 为什么必须是共享目录？

因为可能是：

```text
训练进程
在机器 A

SGLang
在机器 B
```

SGLang 收到：

```text
model_path
```

以后必须真的能读取这个路径。

所以一般需要：

```text
NFS
共享磁盘
共享容器卷
```

---

<a id="origin-1973"></a>
## 59. `/update_weights_from_disk`

训练端写完新权重后：

```python
POST /update_weights_from_disk
```

并告诉 SGLang：

```text
新模型在这个路径
```

于是：

```text
Actor PPO 更新
↓
保存新权重
↓
SGLang 从磁盘读取
↓
推理端切换成新 Policy
```

---

<a id="origin-2001"></a>
## 60. 为什么同步失败必须报错？

假设：

```text
训练端：
Actor = v5

SGLang：
还停留在 v2
```

那下一批 rollout 是 v2 生成的。

但训练代码可能以为：

```text
当前 Policy 已经是 v5
```

这会让：

```text
old logp
new logp
PPO ratio
```

全部失去预期含义。

所以这里宁愿：

```python
raise RuntimeError(...)
```

也不应该悄悄继续。

---

<a id="origin-2041"></a>
## 61. `broadcast()` 为什么出现？

只有：

```text
rank0
```

真正更新远端。

所以假设：

```text
rank0 更新失败
```

其他 rank 默认并不知道。

于是：

```python
dist.broadcast(ok_t, src=0)
```

把：

```text
成功 / 失败
```

这个状态从 rank0 发给所有 rank。

---

<a id="origin-2075"></a>
## 62. `broadcast` 和前面 PPO 的 `all_reduce` 区别

<a id="origin-2077"></a>
### 62.1 `all_reduce`

```text
rank0 提供一个值
rank1 提供一个值
rank2 提供一个值
↓
求和 / 求平均
↓
所有 rank 拿到结果
```

<a id="origin-2089"></a>
### 62.2 `broadcast`

```text
只有 rank0 提供最终值
↓
复制给其他 rank
```

例如：

```text
rank0：
ok = 0
```

broadcast 后：

```text
rank0 → 0
rank1 → 0
rank2 → 0
rank3 → 0
```

---

<a id="origin-2115"></a>
## 63. `barrier()`

```python
dist.barrier()
```

意思：

> 所有 rank 都必须到齐，才能继续。

这样可以避免：

```text
rank1 已经开始下一轮
但 rank0 还在处理远端模型更新
```

---

<a id="origin-2134"></a>
## 64. `flush_cache()`

```python
POST /flush_cache
```

作用：

> 请求远端清理推理缓存。

至于 SGLang 内部具体清理哪些缓存，这个文件本身没有继续展开，所以不能仅根据当前源码进一步确定。

---

<a id="origin-2148"></a>
## 65. `health()`

```python
GET /health
```

检查：

```text
SGLang 服务是否健康
```

返回 HTTP 200：

```text
True
```

否则：

```text
False
```

---

<a id="origin-2174"></a>
## 66. `create_rollout_engine()`：工厂函数

```python
if engine_type == "torch":
    return TorchRolloutEngine(...)
elif engine_type == "sglang":
    return SGLangRolloutEngine(...)
```

调用者只需要告诉它：

```text
我要 torch
```

或者：

```text
我要 sglang
```

它负责创建正确对象。

---

<a id="origin-2199"></a>
## 67. 为什么叫工厂函数？

因为它专门：

> **根据配置生产不同类型的对象。**

以后如果增加：

```text
vllm
```

只需在这里再加：

```python
elif engine_type == "vllm":
    return VLLMRolloutEngine(...)
```

训练代码仍然可以不变。

---

<a id="origin-2222"></a>
## 68. 这个文件最关键的一句话其实在开头注释里

它说：

> 采样结果用于构造训练目标；策略更新时还需重新前向计算带梯度的 log 概率。

这句话非常重要。

Rollout 时得到：

\[
\log\pi_{\text{old}}
\]

它只是：

```text
历史数据
```

通常在：

```python
torch.no_grad()
```

下计算。

所以：

```text
不需要梯度
```

---

<a id="origin-2258"></a>
## 69. PPO 更新时为什么还要重新 forward？

因为 PPO 真正要更新的是：

```text
Current Actor
```

所以必须重新算：

\[
\log\pi_{\text{new}}
\]

而且这一次必须连接：

```text
Current Actor 参数
↓
logits
↓
logp
↓
Policy Loss
↓
backward
```

所以：

```text
Old logp
=
Rollout 阶段保存
=
不需要梯度

New logp
=
PPO Update 阶段重新 forward
=
必须有梯度
```

---

<a id="origin-2304"></a>
## 70. 为什么不能直接拿 Rollout 的 logp 反向传播？

因为 Rollout logp：

```text
已经是采样那一刻的历史值
```

而且通常在：

```python
torch.no_grad()
```

里面计算。

它没有连着当前 Actor 的梯度图。

PPO 要更新 Current Actor，必须：

```text
当前 Actor
↓
重新 forward
↓
new logp
↓
PPO Loss
↓
backward
```

---

<a id="origin-2338"></a>
## 71. 正好对应 PPO Ratio

\[
ratio_t
=
\frac{
\pi_{\text{new}}(a_t|s_t)
}{
\pi_{\text{old}}(a_t|s_t)
}
\]

其中：

```text
π_old
↓
rollout_engine.py 提供
```

而：

```text
π_new
↓
train_ppo.py 更新阶段重新计算
```

两个文件一起才组成完整 PPO。

---

<a id="origin-2370"></a>
## 72. 一个完整数字例子

假设：

```text
Prompt IDs：
[10,11,12,13]
```

Rollout 生成：

```text
[51,52,EOS]
```

完整：

```text
[10,11,12,13,51,52,EOS]
```

---

<a id="origin-2393"></a>
### 72.1 Rollout 阶段

重新计算 Old LogP：

```text
位置3 → 预测 51
位置4 → 预测 52
位置5 → 预测 EOS
```

假设：

```text
old logp：

[-0.50,-0.20,-0.10]
```

于是返回：

```text
output_ids
=
[10,11,12,13,51,52,EOS]

completion_ids
=
[51,52,EOS]

per_token_logps
=
[-0.50,-0.20,-0.10]

prompt_lens
=
[4]

completion_mask
=
[1,1,1]
```

---

<a id="origin-2437"></a>
### 72.2 PPO Update 阶段

Actor 重新 forward。

假设当前：

```text
new logp：

[-0.45,-0.18,-0.08]
```

第一个 token：

\[
log\_ratio
=
-0.45-(-0.50)
=
0.05
\]

所以：

\[
ratio=e^{0.05}\approx1.051
\]

表示：

> 当前 Policy 现在给这个动作的概率，比 Rollout 时提高了约 5.1%。

---

<a id="origin-2471"></a>
## 73. 再看 `update_policy()`

假设：

```text
Actor v0
↓
PPO
↓
Actor v1
```

<a id="origin-2483"></a>
### 73.1 Torch backend

```python
self.policy_model = actor_model
```

后面直接用 v1。

<a id="origin-2491"></a>
### 73.2 SGLang backend

```text
Actor v1
↓
save_pretrained
↓
共享目录
↓
HTTP update_weights_from_disk
↓
SGLang 加载 v1
```

下一批 rollout 才真正使用：

```text
Policy v1
```

---

<a id="origin-2513"></a>
## 74. 所以 Online PPO 实际是两个循环咬在一起

```text
================ 采样 ================

Current Policy
↓
Rollout
↓
Response + Old LogP


================ 训练 ================

Reward
↓
Critic
↓
GAE
↓
PPO
↓
Actor Update


================ 同步 ================

update_policy()
↓
Rollout Engine 获得新 Policy


================ 再采样 ================

New Policy
↓
新的 Rollout
↓
新的 Old LogP
```

不断重复：

```text
采样
↓
训练
↓
同步
↓
再采样
```

这就是：

\[
\boxed{
Online PPO
}
\]

---

<a id="origin-2576"></a>
## 75. 最应该记住的 10 句话

1. `rollout_engine.py` 不负责 PPO Loss，它负责**在线采样**。
2. Rollout 不只返回回答，还必须保存 **Old Policy 的 per-token logp**。
3. `compute_per_token_logps()` 根据完整序列重新计算回答 token 的原始模型 logp。
4. `n_keep+1` 来自 next-token prediction 的一位错位。
5. `RolloutResult` 统一 Torch 和 SGLang backend 的输出格式。
6. `RolloutEngine` 抽象出 `rollout()` 和 `update_policy()` 两个核心接口。
7. Torch backend 在本地直接 `model.generate()`。
8. SGLang backend 通过 HTTP 远端生成，并需要显式同步新权重。
9. Old logp 不需要梯度；PPO Update 的 New logp 必须重新前向并带梯度。
10. 这个文件真正解决的是：**训练算法不应该关心底层到底使用什么推理引擎。**

---

<a id="origin-2591"></a>
## 76. 最终总图

```text
                        ┌─────────────────────┐
                        │     train_ppo.py    │
                        └──────────┬──────────┘
                                   │
                                   │ Prompt IDs
                                   ▼
                  ┌────────────────────────────────┐
                  │       RolloutEngine API        │
                  │                                │
                  │ rollout()                      │
                  │ update_policy()                │
                  └──────────────┬─────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼

       TorchRolloutEngine              SGLangRolloutEngine

        本地 model.generate              HTTP /generate
                 │                               │
                 ▼                               ▼
       本地重新计算 old logp             服务返回 token/logp
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼

                         RolloutResult

                    output_ids
                    completion_ids
                    per_token_logps
                    completions
                    prompt_lens
                    completion_mask

                                 │
                                 ▼
                           train_ppo.py
                                 │
                                 ▼
                       Reward / Critic / GAE
                                 │
                                 ▼
                       PPO New-vs-Old Ratio
                                 │
                                 ▼
                            backward
                                 │
                                 ▼
                         optimizer.step()
                                 │
                                 ▼
                       Actor Policy 更新
                                 │
                                 ▼
                   rollout_engine.update_policy()
                                 │
                                 ▼
                     下一批 rollout 使用新 Policy
```

---

<a id="origin-2658"></a>
## 77. 一句话总结

`rollout_engine.py` 本质上就是：

\[
\boxed{
\text{PPO 训练器和“真正负责生成回答的 Policy 推理后端”之间的一层统一适配器}
}
\]

它把：

```text
本地 PyTorch generate
```

和：

```text
远端 SGLang HTTP 推理
```

统一成：

```python
rollout(...)
update_policy(...)
```

并保证 PPO 后面都能拿到：

\[
\boxed{
\text{Response}
+
\text{Old LogP}
+
\text{Prompt Length}
+
\text{Mask}
}
\]

其中最关键的一项就是：

\[
\boxed{
\log\pi_{\text{old}}(a_t|s_t)
}
\]

因为后面 PPO 的：

\[
\frac{
\pi_{\text{new}}
}{
\pi_{\text{old}}
}
\]

正是建立在这里保存下来的 Old Policy 概率之上。
