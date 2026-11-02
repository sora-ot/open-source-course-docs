# 08 Compaction 上下文压缩完整讲义：从具体例子到算法与代码

> 本讲义按一个固定顺序讲清楚 Compaction：
>
> **第一部分：只看一个完全具体的例子，不讲代码。**  
> **第二部分：把例子抽象成算法。**  
> **第三部分：最后再看代码实现。**
>
> 最核心的一句话是：
>
> **程序负责决定“切哪里、哪些消息进入摘要、哪些消息保留原文”；大模型负责真正把待摘要内容压缩成语义摘要。**

---

# 第一部分：先只看完整例子

# 1. 为什么需要 Compaction

假设我们在做一个午饭 Agent。

用户最开始提出：

> 帮我选一份不辣的午饭，预算 20 元。  
> 先给方案，不要下单。

Agent 会不断查询午饭、查询库存情况、比较候选午饭。

如果对话越来越长：

```text
用户要求
↓
查询午饭
↓
工具返回几十条结果
↓
查询库存情况
↓
工具再返回大量结果
↓
用户继续修改要求
↓
Agent继续查询
↓
……
```

那么模型每一次继续工作，都重新带上全部历史，Context 会越来越大。

Compaction 的目的不是删除历史，而是把：

```text
较老的原始消息
```

变成：

```text
较短的语义摘要
```

同时继续保留：

```text
最近一段原始消息
```

因此模型后续看到的不是：

```text
全部原始历史
```

而是：

```text
摘要 + 最近原文
```

---

# 2. 第一轮完整消息：L0～L7

先有下面 8 条记录：

| 编号 | 内容 |
|---|---|
| L0 | 用户：帮我选一份不辣的午饭。先给方案，不要下单。 |
| L1 | 助手：你的预算是多少？ |
| L2 | 用户：20 元以内。 |
| L3 | 助手：调用 `list_meals`。 |
| L4 | 工具：牛肉面售价 30 元，鸡腿饭售价 20 元，蛋炒饭售价 10 元，三份都不辣。 |
| L5 | 助手：调用 `get_stock`，查询鸡腿饭、蛋炒饭的库存情况。 |
| L6 | 工具：鸡腿饭售罄，蛋炒饭有货。 |
| L7 | 助手：建议蛋炒饭；尚未下单。 |

其中：

```text
L3 → L4
```

是一组：

```text
toolCall → toolResult
```

而：

```text
L5 → L6
```

又是另一组：

```text
toolCall → toolResult
```

---

# 3. Compaction 为什么需要“预算”

程序希望最近的原始消息不要无限增长。

于是有一个参数：

```text
keepRecentTokens
```

它的意思不是：

> 整个请求最多只能有这么多 token。

而是：

> 希望“最近继续保留为原文的那一段”大约占这么多 token。

为了教学，我们假设：

```text
keepRecentTokens = 79
```

真实系统的默认值可以比这个大得多。

---

# 4. 为什么会看到“字符串长度 ÷ 4”

这是第一个很容易误解的地方。

## 4.1 真实 token 并不是“4 个字符 = 1 token”

真正的大模型会经过自己的 Tokenizer：

```text
字符串
↓
Tokenizer
↓
Token 序列
↓
模型
```

不同模型、不同语言、不同字符串，实际 token 数都不同。

因此：

```text
4 个字符 = 1 token
```

**不是一个真实的语言规律。**

---

## 4.2 那为什么 Compaction 里还要除以 4

因为在“找切点”时，程序只需要一个：

```text
便宜、快速、够用的大小估算
```

它不是为了精确计费，而是为了回答：

```text
L4 大概比 L2 大多少？
最近这些消息大概已经占多少空间？
从哪里切比较合适？
```

所以程序使用一个粗略尺子：

```text
estimatedTokens ≈ 字符串长度 / 4
```

再向上取整。

可以把它理解成：

> `/4` 是一个本地近似尺子，不是真实 Tokenizer。

---

## 4.3 为什么不直接调用分词器，算得更准一些

**可以使用分词器；这里采用 `/4`，是一种在精度、通用性和实现成本之间的工程取舍。** 下面是结合实现作出的解释，不代表源码记录了作者的全部设计动机。

首先，**Pi 会对接不同厂家的模型，不能拿一个分词器准确统计所有模型。** 不同模型的词表、编码规则可能不同；要提高准确度，就需要选择与目标模型匹配的 Tokenizer，并维护模型到分词器的映射。对于没有提供可用本地分词器的模型，还可能需要调用服务端计数接口。

其次，**把消息正文交给分词器，也不等于算出了整个请求的 token 数。** 真正发送给模型时，还涉及角色标记、消息模板、工具定义以及图片等内容。要接近服务端的统计，需要按对应模型和 API 的实际请求格式计数。例如，Claude 的 [Token Counting 接口](https://platform.claude.com/docs/en/build-with-claude/token-counting) 接收包含消息、系统提示和工具等字段的结构化输入，返回的计数仍被官方说明为估算。

最后，**找切点本来就是按整条消息选择边界，并不要求精确到一个 token。** 本例中，即使预算落在 L4，后面仍要调整到合法消息起点 L5。对这个任务，简单的长度估算省去了加载词表、执行分词和维护多模型适配的成本；如果改用远程计数，还会增加网络请求和等待。

所以，这里不是“分词器没有用”，而是：

```text
目标：在预算附近找一个合法消息边界
↓
选择：使用实现简单、无需额外计数请求的本地估算
↓
代价：保留原文的真实 token 数可能偏离预算
```

---

## 4.4 为什么偏偏是 4，这个估算对中文可靠吗

`/4` 可以理解为“一个 token 大约对应几个字符”这一常见粗估思路的固定系数，主要接近部分英文文本的情况。**它不是针对所有语言和模型校准过的换算公式。**

例如，假设一段中文的字符串长度是 100：

```text
本地估算：ceil(100 / 4) = 25 token
真实计数：必须由目标模型的 Tokenizer 或计数接口确定
```

不能据此认定这段中文真实只占 25 token。中文、代码、特殊符号等内容的字符与 token 比例都可能不同，`/4` 可能低估，也可能高估。

还有一个代码细节：这里的长度来自 JavaScript 的 `.length`，严格说统计的是 **UTF-16 代码单元**，不是字节数，也不总是人眼看到的字符数，例如一个 emoji 可能占多个代码单元。

源码中 `estimateTokens()` 的注释称它是保守估算、会高估 token，**但固定 `/4` 并不能保证对中文等所有输入都高估。** `Math.ceil()` 也只是把估算值向上取整，不会消除换算系数带来的误差。

---

## 4.5 系统判断是否该压缩，也完全靠除以 4 吗

**不是。要区分“整个上下文有多大”和“每条消息有多大”。**

**如果 API 已经告诉程序相应内容用了多少 token，就直接使用 API 返回的计数，不需要再用长度除以 4；除以 4 只是对没有对应计数的内容做大概估计。**

| 要解决的问题 | 这份实现使用的信息 |
|---|---|
| 正常回复后，判断是否达到自动压缩阈值 | 使用 API 返回的 `usage`，由 `calculateContextTokens()` 计算上下文用量 |
| 需要估算当前上下文时 | `estimateContextTokens()` 优先使用最近一次有效的助手 `usage`，再加上之后新增消息的估算；没有可用 `usage` 时才逐条估算全部消息 |
| 倒序扫描，决定近期原文从哪里保留 | `findCutPoint()` 调用 `estimateTokens()`，逐条累计本地估算值 |

为什么有 `usage`，切点还需要估算？因为 **`usage` 给出的是一次模型调用的总体用量，并没有给出 L0、L1、L2……每条历史消息各占多少 token。** 它能帮助判断上下文是否快满，却不能直接告诉程序从哪条消息开始保留。

例如，`estimateContextTokens()` 的思路可以表示为：

```text
最近一次有效 usage 对应的上下文用量：50,000
此后新增消息的本地估算：             2,000
当前上下文估算：                    52,000
```

它不是每次都把全部历史重新除以 4。

实现还通过 `reserveTokens` 提前留出余量；自动压缩开启且满足相应条件时，遇到上下文溢出错误也有压缩并重试一次的恢复路径。**这些机制能缓解估算误差的影响，但不保证 `/4` 永远足够准确，也不保证压缩后一定不会溢出。**

本节涉及的实现可对照 [compaction.ts](../pi-master/packages/coding-agent/src/core/compaction/compaction.ts) 中的 `estimateTokens()`、`estimateContextTokens()`、`findCutPoint()`，以及 [agent-session.ts](../pi-master/packages/coding-agent/src/core/agent-session.ts) 中的 `_checkCompaction()`。

可以记成一句话：

> **判断总量时尽量利用服务端 `usage`，选择切点时用便宜的逐条估算；如果业务要求严格控制 token，就应采用匹配模型的计数方式，并为请求格式和估算误差留出余量。**

---

# 5. 具体看 L4 为什么得到 37

假设 L4 的工具返回序列化成 JSON 后：

```text
字符串长度 = 147
```

那么：

```text
147 / 4 = 36.75
```

向上取整：

```text
37
```

所以程序估算：

```text
L4 ≈ 37 token
```

对于 Tool Call，也会根据：

```text
工具名称
+
参数 JSON
```

的字符串长度进行类似估算。

因此这里的数字主要服务于：

```text
寻找消息边界
```

而不是精确表示模型最终真实消费了多少 token。

---

# 6. 给 L0～L7 都算一个估算大小

本例使用：

| 消息 | 估算 token |
|---|---:|
| L0 | 7 |
| L1 | 4 |
| L2 | 3 |
| L3 | 3 |
| L4 | 37 |
| L5 | 21 |
| L6 | 39 |
| L7 | 18 |

现在：

```text
keepRecentTokens = 79
```

问题就变成：

> 最近原文应该从哪里开始保留？

---

# 7. 第一次 Compaction：先从最新消息往前算预算

因为我们希望保留的是：

```text
最近的原文
```

所以不是从 L0 开始，而是从最新的 L7 开始往旧处走：

```text
L7 → L6 → L5 → L4 → L3 → ...
```

---

## 7.1 先加入 L7

```text
L7 = 18

累计 = 18
```

还没达到 79。

---

## 7.2 再加入 L6

```text
18 + 39 = 57
```

还没达到 79。

---

## 7.3 再加入 L5

```text
57 + 21 = 78
```

还是没有达到 79。

只差 1。

但是程序不会从 L4 里面切 1 个 token 出来。

它按：

```text
整条 Message
```

选择边界。

---

## 7.4 再加入 L4

```text
78 + 37 = 115
```

现在：

```text
115 >= 79
```

因此预算扫描的第一落点是：

```text
L4
```

---

# 8. 预算落到 L4，为什么却不能从 L4 开始保留

因为：

```text
L3 = assistant toolCall
L4 = toolResult
```

它们是一组完整关系：

```text
L3：我要调用 list_meals
↓
L4：list_meals 返回结果
```

如果只保留：

```text
L4
L5
L6
L7
```

就会出现：

```text
工具突然返回一个结果
```

但看不到：

```text
到底是谁调用了工具、调用参数是什么
```

因此：

```text
toolResult
```

不能作为一个新的原文起点。

---

# 9. 找到非法落点以后，往哪个方向调整

这是整个切点算法最容易混淆的一步。

预算累计是：

```text
L7 → L6 → L5 → L4
```

即：

```text
从新往旧
```

但发现：

```text
L4 不能作为新开头
```

以后，不继续往 L3 找。

而是向**更新的方向**寻找第一个合法起点：

```text
L4 → L5
```

于是找到：

```text
L5
```

L5 是一个完整的 assistant Tool Call。

后面又有：

```text
L6 = 对应 Tool Result
```

因此：

```text
L5
L6
L7
```

结构完整。

最终：

```text
firstKeptEntry = L5
```

---

# 10. 为什么预算 79，最后只留下 78

最后实际保留：

```text
L5 = 21
L6 = 39
L7 = 18
```

合计：

```text
21 + 39 + 18 = 78
```

虽然预算是：

```text
79
```

但这并不矛盾。

因为预算只是帮助找到附近边界，而实际切点还必须满足：

```text
消息结构完整
```

所以最后：

```text
78 < 79
```

是完全正常的。

---

# 11. 找到 L5 以后，为什么还要再往前找一次

**因为 L5 只回答了“哪些消息继续保留原文”，还没有回答“被压掉的消息应该怎样总结，才能接上 L5”。**

这里的“再切一次”容易让人误以为：先决定从 L5 保留，后来又改成从 L2 保留。实际不是这样：

```text
第一条边界：L5，区分“要摘要的内容”和“保留的原文”。
第二条边界：L2，在要摘要的内容里，再区分“更早历史”和“本轮前半段”。

最终仍然从 L5 开始保留原文。
```

## 11.1 L5 已经合法，为什么还不够

从工具调用关系看，L5 是合法起点：

```text
L5：调用 get_stock，查询鸡腿饭、蛋炒饭的库存。
L6：鸡腿饭售罄，蛋炒饭有货。
L7：建议蛋炒饭；尚未下单。
```

调用和结果都在，结构没有断。

但如果只看这三条，仍然不知道：

- 用户这次补充了什么要求？
- 为什么只查鸡腿饭和蛋炒饭，不查牛肉面？
- 最后建议蛋炒饭时，已知它的价格是多少？

这些信息在切点以前：

```text
L2：用户说“20 元以内”。
L3：助手查询午饭列表。
L4：牛肉面 30 元，鸡腿饭 20 元，蛋炒饭 10 元，三份都不辣。
```

所以必须区分两个层次：

```text
工具结构完整：L5 的调用后面还有 L6 的结果。
任务背景衔接：L5 为什么要这样调用，需要 L2～L4 的信息解释。
```

前面选择合法切点，解决了第一件事；现在回头找本轮起点，是为了准备第二件事所需的摘要材料。

## 11.2 为什么回头找到的是 L2：按 User Turn 单独摘要有什么好处

这里一个 User Turn 指：**一次用户输入，以及它引发的助手回复、工具调用和工具结果，直到下一次用户输入之前。** 它可以包含多次工具调用。

本例中，L2 是这轮用户输入，L3～L7 都属于这轮处理过程：

```text
L2 用户补充预算
↓
L3～L4 查询午饭及价格
↓
L5～L6 查询预算内候选的库存
↓
L7 给出建议
```

因此，从 L5 向旧处找到最近的 user 消息 L2，就知道：**保留的 L5～L7 是这一轮的后半段，L2～L4 是同一轮被摘要替换的前半段。**

这轮处理在例子中已经给出了建议；这里说“前半段、后半段”，描述的是它被切点分开，不代表压缩时这轮一定还没执行完。

于是材料从两块变成三块：

```text
只找到 L5：
L0 L1 L2 L3 L4                 | L5 L6 L7
全部待摘要内容                    保留原文

再找到 L2：
L0 L1          | L2 L3 L4      | L5 L6 L7
更早历史          本轮前半段       保留原文
                 ↑               ↑
              turnStart       firstKept
```

**第二条边界只改变摘要材料的分组，不改变保留原文的范围。**

**按 User Turn 找边界的好处，是把“这一轮用户要求 → 已做的工作 → 后续动作的依据”作为一个有联系的过程来保留。** 本例单独摘要的是这一轮的前半段 L2～L4，后半段 L5～L7 仍保留原文。

具体有三个好处：

1. **突出本轮的新要求。** 更早历史里只有“选不辣午饭、先别下单”，本轮 L2 新增了“20 元以内”。单独摘要时，Prompt 明确要求写出 Original Request，有助于避免把这条新增约束淹没在整个任务的概述里。
2. **保留后续动作的依据。** L4 的价格不是孤立的查询结果，而是 L5 选择查询哪两份午饭的依据。把 L2～L4 放在一起总结，更容易留下“牛肉面超预算，鸡腿饭和蛋炒饭符合预算”这条联系，让后半段的工具调用有来由。
3. **集中保留衔接所需的信息。** 普通历史摘要面向整个任务，Turn Prefix 摘要的 Prompt 则明确说明后半段还会保留原文，要求提取理解它所需的背景。这样可以压掉前半段的冗长措辞，同时有针对性地保留预算、候选价格和筛选依据。

例如，本轮前半段可以压成：

```text
用户本轮补充预算为 20 元以内。
已查询价格：牛肉面 30 元，超预算；鸡腿饭 20 元、蛋炒饭 10 元，均不辣。
这些价格和预算信息，是理解后续两份候选库存查询的背景。
```

再接上 L5～L7 原文，就能读懂“为什么查这两份，以及最后推荐的蛋炒饭是否符合预算”。

**所以，单独摘要这一轮的前半段，主要收益是让本轮要求和执行依据更容易保留下来，并与后半段原文接上。** 这不保证比合并摘要更短，也不保证绝对不遗漏；它通过明确材料范围和摘要目标，提高保留这些信息的机会。

## 11.3 为什么不干脆从 L2 开始，把整轮原文都保留

这样确实能保留完整背景，但原文会变多。本例中：

```text
从 L5 保留：21 + 39 + 18 = 78 token
从 L2 保留：3 + 3 + 37 + 21 + 39 + 18 = 121 token

keepRecentTokens = 79
```

`79` 虽然不是硬上限，但如果每次切进一轮就回退到这轮开头，一轮里几百次工具调用都可能被一起留下，近期原文的大小就难以控制。

所以这里采用的办法是：**保留 L5～L7 的近期细节，把 L2～L4 中衔接这些细节所需的背景写成较短摘要。**

## 11.4 为什么不把 L0～L4 全部做成一个普通历史摘要

可以这样设计，也可能得到足够好的摘要；并不是合成一份就必然出错。

但这份实现把摘要任务分成两类，给模型更明确的保留重点：

- 对 L0～L1，整理整个任务的目标、长期约束和进度。
- 对 L2～L4，明确说明“这是被切开一轮的前半段，后半段保留原文”，要求保留理解后半段所需的背景。

例如，普通摘要可能只写“已查询午饭”，而衔接 L5～L7 时，预算、候选价格和筛选依据更有用：

```text
本轮预算为 20 元以内。
已查到牛肉面 30 元，超预算；鸡腿饭 20 元、蛋炒饭 10 元，均不辣。
后半段继续记录这两份候选的库存查询与最终建议。
```

专门的 Turn Prefix 摘要 Prompt，就是要把注意力放在这些衔接信息上。它有助于减少背景遗漏，但摘要仍由 LLM 生成，不保证绝对无损。

因此，再往前找一次的目的可以记成：**找到 L5，决定原文留哪里；找到 L2，决定哪些内容要作为“这轮前情”单独总结。到这里仍然没有调用 LLM，也没有发生第二轮 Compaction。**

---

# 12. Turn 起点从哪里找

注意顺序：

## 第一步

先找到最终切点：

```text
L5
```

## 第二步

再从 L5 向旧处找最近的 user：

```text
L5
↑
L4
↑
L3
↑
L2
```

于是找到：

```text
L2 = user
```

因此：

```text
firstKeptEntryIndex = L5
turnStartIndex = L2
isSplitTurn = true
```

注意这两个索引会同时保留：`turnStartIndex` 用来划分摘要材料，`firstKeptEntryIndex` 用来确定原文保留区。找到 L2 后，不会把 `firstKeptEntryIndex` 改成 L2。

---

# 13. 第一次 Compaction 因此被分成三块

现在：

```text
L0 L1 | L2 L3 L4 | L5 L6 L7
```

分别表示：

## 第一块：更早历史

```text
L0 L1
```

## 第二块：当前 Turn 被切掉的前半段

```text
L2 L3 L4
```

## 第三块：继续保留的原文

```text
L5 L6 L7
```

可以画成：

```text
更早历史              当前Turn前半段              保留原文

L0 L1          |       L2 L3 L4          |       L5 L6 L7
                        ↑                           ↑
                    turnStart                  firstKept
```

---

# 14. 到这里，“切”的工作已经完成

非常重要：

到这里都还没有真正生成摘要。

程序只是算出了：

```text
历史材料：
L0 L1

当前 Turn Prefix：
L2 L3 L4

原文保留区：
L5 L6 L7
```

因此可以记住：

> **程序负责切；大模型负责压。**

---

# 15. 真正的“压缩”是谁完成的

真正把：

```text
L0 L1
```

变成短摘要，

以及把：

```text
L2 L3 L4
```

变成 Turn Context，

是由：

```text
大模型
```

完成的。

它不是 gzip，也不是字符串压缩，也不是程序自己删除几个单词。

本质是：

```text
原始对话
↓
送给 LLM
↓
LLM 理解语义
↓
提取重要状态
↓
重新写成较短文本
```

因此 Compaction 是一种：

```text
语义有损压缩
```

目标是：

```text
丢掉表面措辞
保留继续完成任务所需要的信息
```

---

# 16. 第一次为什么会有“两种压缩”

这里的“两种压缩”是指：**同一次 Compaction 内部，对两组不同材料分别生成摘要。** 它们都使用 LLM 做语义有损压缩，区别在输入范围和摘要目标。

| 比较项 | 历史摘要 H1 | Turn Prefix 摘要 P1 |
|---|---|---|
| 本例输入 | L0～L1：被切开这一轮以前的历史 | L2～L4：被切开这一轮的前半段 |
| 主要问题 | 整个任务要做什么，有哪些约束，已经推进到哪里？ | 本轮要求是什么，切点前做了什么，保留的后半段需要什么背景？ |
| 本例重点 | 选不辣午饭；先给方案，不下单；当时正在询问预算 | 本轮预算 20 元以内；候选价格；为什么后面查询鸡腿饭和蛋炒饭 |
| 输出组织 | Goal、Constraints、Progress、Next Steps 等 | Original Request、Early Progress、Context for Suffix |
| 后续 Compaction 时 | 有旧摘要时，结合 `previousSummary` 和后来变旧的消息更新 | 按本次分出的前半段生成，不传入 `previousSummary` |

两者的关注点并非完全互斥。历史摘要也可以保留具体价格，Turn Prefix 摘要也可以保留用户约束；单独分组，是为了强调不同的保留重点。

尤其要注意本例的时间关系：H1 只读了 L0～L1，所以可能写“正在确认预算”；P1 读了后来的 L2～L4，就会补充“用户已指定 20 元以内”。最终应结合两份摘要以及保留原文，理解任务后来的进展。

这不是先把同一批消息压一次，再拿压缩结果压第二次，而是：

```text
L0 L1       → 历史摘要 H1       ┐
                              ├→ 拼接成 S1 → 后面接 L5 L6 L7 原文
L2 L3 L4    → 前半段摘要 P1     ┘
```

本例两组材料都有内容，因此会有两次 LLM 摘要调用，源码中可以并行执行；拼接 H1 和 P1 不再调用一次 LLM。若切点刚好落在 user 消息上，没有切开一轮，就只走历史摘要路径。

---

# 17. 第一种压缩：历史摘要

输入：

```text
L0 用户：
帮我选一份不辣的午饭。
先给方案，不要下单。

L1 助手：
预算是多少？
```

这些消息会先被序列化成可读文字，例如：

```text
[User]
帮我选一份不辣的午饭。
先给方案，不要下单。

[Assistant]
你希望花多少钱？
```

然后交给专门的历史摘要 Prompt。

---

# 18. 历史摘要要提取什么

它的目标不是简单说：

```text
请缩短这两句话
```

而是要整理成任务状态，例如：

```text
Goal
Constraints & Preferences
Progress
Key Decisions
Next Steps
Critical Context
```

所以 LLM 可能生成：

```markdown
## Goal
为用户选择合适的午饭。

## Constraints & Preferences
- 不要辣。
- 先提供方案，不要下单。

## Progress
- 已确认口味要求。
- 正在确认预算。

## Key Decisions
- 查询信息后先提供建议，不执行下单。

## Next Steps
1. 获取具体预算。
2. 查询可选午饭。

## Critical Context
- 口味不要辣。
```

把这份结果记成：

```text
H1
```

即：

```text
H1 = 历史摘要
```

---

# 19. 这种摘要到底丢掉了什么

例如：

```text
助手：你希望花多少钱？
```

可能被压成：

```text
正在等待预算。
```

原始句子的具体措辞没有留下。

但是：

```text
当前任务缺少预算信息
```

这个语义留下了。

所以它在做：

```text
原始语言形式
↓
丢掉

任务语义
↓
保留
```

---

# 20. 第二种压缩：Turn Prefix 摘要

现在处理：

```text
L2 L3 L4
```

它们是：

```text
L2 用户：
20 元以内。

L3 助手：
调用 list_meals。

L4 工具：
牛肉面 30 元；
鸡腿饭 20 元；
蛋炒饭 10 元；
三份都不辣。
```

注意后面：

```text
L5 L6 L7
```

还会继续保留为原文。

因此：

```text
L2 L3 L4
```

只是这一轮移入摘要区的部分；同一轮的 L5～L7 仍在原文保留区。

而是：

> 被切开这一轮执行过程的前半截，需要为保留的后半截提供背景。

这里区分的是同一轮中哪些消息被摘要替换、哪些继续保留原文，不是在判断这一轮是否已经执行结束。

---

# 21. Turn Prefix 摘要关注的问题不一样

它主要需要回答：

```text
1. Original Request
   这一轮用户到底要求了什么？

2. Early Progress
   在切点以前已经做了什么？

3. Context for Suffix
   后面保留下来的原文需要哪些背景才能读懂？
```

于是 LLM 可能生成：

```markdown
## Original Request
用户指定预算为 20 元。

## Early Progress
- 已查询午饭信息：
  - 牛肉面售价 30 元；
  - 鸡腿饭售价 20 元；
  - 蛋炒饭售价 10 元；
  - 三份都不辣。

## Context for Suffix
- 牛肉面超出 20 元预算。
- 后续需要结合鸡腿饭、蛋炒饭的库存查询结果继续判断。
```

把它记成：

```text
P1
```

即：

```text
P1 = 第一次的 Turn Prefix 摘要
```

---

# 22. 第一次 Compaction 的两次 LLM 压缩

所以第一次真正发生的是：

```text
L0 L1
↓
LLM 历史摘要
↓
H1
```

同时：

```text
L2 L3 L4
↓
LLM Turn Prefix 摘要
↓
P1
```

然后程序把：

```text
H1
+
Turn Context (split turn)
+
P1
```

拼起来。

**这里要特别强调：`Turn Context (split turn)` 这几个英文单词会原样写入摘要，并随摘要一起保存到会话记录的 `summary` 字段中。** 完整的标题文本是 `**Turn Context (split turn):**`，包括 Markdown 加粗标记和冒号。

这个标题由源码固定拼接；LLM 分别生成 H1 和 P1 的摘要正文。标题放在 P1 前，表示“被切开这一轮的前半段背景摘要”。默认实现的拼接语句是：

```ts
summary = `${historyResult}\n\n---\n\n**Turn Context (split turn):**\n\n${turnPrefixResult}`;
```

因此，摘要中实际包含下面这样的文本结构（H1、P1 是本文代号，实际位置填入生成的摘要正文）：

```markdown
H1 的摘要正文

---

**Turn Context (split turn):**

P1 的摘要正文
```

这个固定标题只在默认实现满足 `isSplitTurn && turnPrefixMessages.length > 0`、进入双摘要分支时添加。

得到：

```text
S1
```

因此：

```text
S1 = H1 + P1
```

这里的“+”主要表示文本拼接。

并不是：

```text
H1 + P1
↓
再调用一次 LLM
↓
S1
```

---

# 23. 第一次 Compaction 完成后模型看到什么

最终：

```text
S1
L5
L6
L7
```

而不是：

```text
L0
L1
L2
L3
L4
L5
L6
L7
```

所以 Context 被缩短了。

---

# 24. 但原始 L0～L7 有没有从 Session 文件中删掉

没有。

Session 历史里仍然可以保存：

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7
```

然后在末尾再追加一条：

```text
C1
```

C1 里面保存：

```text
summary = S1
firstKeptEntryId = L5
```

所以：

```text
C1
```

是在告诉系统：

> 后续模型使用 S1 表示较早历史，同时从 L5 开始继续保留原始 Message。

---

# 25. 第一次压缩后的两个“世界”

可以分成：

## Session 完整记录

```text
L0
L1
L2
L3
L4
L5
L6
L7
C1
```

## 当前模型实际使用的上下文

```text
S1
L5
L6
L7
```

所以 Compaction：

> 不一定是在删除 Session 历史，而是在改变后续送给模型的历史表示方式。

这里就和前面 Agent Loop 讲过的 `agent.state.messages` 接上了。

**压缩结果最终会替换 Agent 当前保存的消息历史。**

在这个例子中：

```text
压缩前 state.messages：
[L0, L1, L2, L3, L4, L5, L6, L7]

压缩后 state.messages：
[S1, L5, L6, L7]
```

其中 S1 是一条 `compactionSummary` 消息，内部包含 H1、固定标题和 P1。

在 [agent-session.ts](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1718) 中，下面几步紧挨着；这里的 `compact()` 就是前面 [compaction.ts 中的压缩函数](../pi-master/packages/coding-agent/src/core/compaction/compaction.ts#L717)。

```ts
const result = await compact( // 调用 compaction.ts，生成压缩摘要
  preparation,
  this.model,
  apiKey,
  headers,
  customInstructions,
  this._compactionAbortController.signal,
  this.thinkingLevel,
);
summary = result.summary; // 取出摘要 S1，内部包含 H1 和 P1
firstKeptEntryId = result.firstKeptEntryId;
tokensBefore = result.tokensBefore;
details = result.details;

if (this._compactionAbortController.signal.aborted) {
  throw new Error("Compaction cancelled");
}

this.sessionManager.appendCompaction(summary, firstKeptEntryId, tokensBefore, details, fromExtension); // 保存压缩记录 C1
const newEntries = this.sessionManager.getEntries();
const sessionContext = this.sessionManager.buildSessionContext(); // 根据 C1 组装 [S1, L5, L6, L7]
this.agent.state.messages = sessionContext.messages; // 用压缩后的消息列表替换 Agent 当前历史
```

也就是：生成 S1 → 保存压缩记录 C1 → 重建 `[S1, L5, L6, L7]` → 写回 `state.messages`。

接下来回到前面讲过的流程：

```text
state.messages：S1 + L5～L7
↓ 下次启动 Agent Loop，复制历史
currentContext.messages
↓ 每次请求时转换成模型兼容消息
llmContext.messages
↓
发送给大模型
```

所以本讲说的“活动上下文”，在 Agent 这一层就是压缩后的 `state.messages`；Session 文件仍保留完整记录。

---

# 26. 对话继续：加入 L8～L11

接下来用户又说：

```text
L8 用户：
再比较一下鸡腿饭和蛋炒饭，
顺便看看它们是否送汤，
还是不要下单。
```

助手：

```text
L9：
调用 get_meal_details，
查询鸡腿饭、蛋炒饭的送汤情况。
```

工具：

```text
L10：
鸡腿饭送汤；
蛋炒饭不送汤。
```

助手：

```text
L11：
鸡腿饭送汤，但之前查到已售罄；
蛋炒饭目前有货，但不送汤。
如果优先保证有货，蛋炒饭更合适。
仍未下单。
```

此时新的活动历史可以理解成：

```text
S1
L5
L6
L7
L8
L9
L10
L11
```

当前活动上下文如下，S1 按内部结构展开（仍是一份摘要）：

| 编号 | 内容 |
|---|---|
| S1：H1 | 历史摘要：为用户选择一份不辣的午饭；先给方案，不要下单。已确认口味要求，正在等待预算。 |
| S1：固定标题 | **Turn Context (split turn):** |
| S1：P1 | 本轮前半段摘要：用户指定预算为 20 元。已查询午饭：牛肉面售价 30 元，鸡腿饭售价 20 元，蛋炒饭售价 10 元，均不辣。牛肉面超出预算；后续需结合鸡腿饭、蛋炒饭的库存结果判断。 |
| L5 | 助手：调用 `get_stock`，查询鸡腿饭、蛋炒饭的库存情况。 |
| L6 | 工具：鸡腿饭售罄，蛋炒饭有货。 |
| L7 | 助手：建议蛋炒饭；尚未下单。 |
| L8 | 用户：再比较一下鸡腿饭和蛋炒饭，顺便看看它们是否送汤，还是不要下单。 |
| L9 | 助手：调用 `get_meal_details`，查询鸡腿饭、蛋炒饭的送汤情况。 |
| L10 | 工具：鸡腿饭送汤；蛋炒饭不送汤。 |
| L11 | 助手：鸡腿饭送汤，但之前查到已售罄；蛋炒饭目前有货，但不送汤。如果优先保证有货，蛋炒饭更合适。仍未下单。 |

---

# 27. 第二次 Compaction 从哪里开始找新切点

这是另一个非常重要的问题。

第二次 Compaction 不会重新从：

```text
L0
```

开始计算。

因为：

```text
L0～L4
```

已经由：

```text
S1
```

表示。

而 C1 里面还保存：

```text
firstKeptEntryId = L5
```

因此第二次需要重新考虑的最老原始消息是：

```text
L5
```

---

# 28. 第二次切点扫描范围

第二次真正参加：

```text
keepRecentTokens
```

扫描的是：

```text
L5
L6
L7
L8
L9
L10
L11
```

仍然从最新往旧：

```text
L11 → L10 → L9 → L8 → L7 → L6 → L5
```

但：

```text
S1
```

不作为普通 Message 参加这个预算竞争。

---

# 29. S1 在第二次 Compaction 中是什么身份

S1 是：

```text
previousSummary
```

也就是：

```text
上一版摘要
```

因此第二次可以理解成有两条轨道：

## 轨道 A：找新切点

```text
L11 → L10 → ... → L5
```

## 轨道 B：保存旧摘要

```text
previousSummary = S1
```

S1 在旁边等待之后的：

```text
摘要更新
```

---

# 30. 如果预算在走到 L5 以前就已经达到

例如假设第二次最终找到：

```text
firstKept = L8
```

那么：

```text
L5 L6 L7
```

就不再保留为原文。

它们将加入新的历史摘要。

最终：

```text
S1 + L5 + L6 + L7
↓
生成 S2
```

而：

```text
L8 ...
```

继续保持原文。

---

# 31. 如果一直到 L5 都还没有达到预算

那就意味着：

```text
L5～最新消息
```

整体仍然可以继续保留。

此时最早的重新考虑边界已经到达：

```text
L5
```

不会继续做：

```text
L5 → S1 → L4 → L3 → ...
```

因为 S1 不是一条普通的预算候选 Message。

所以：

```text
S1
```

不会拿来继续参与：

```text
keepRecentTokens
```

倒序累计。

---

# 32. 第二次仍然要先找切点，再找 Turn

假设第二次最终的新切点是：

```text
L11
```

L11 是 assistant。

那么程序再从：

```text
L11
```

向旧处找最近的 user：

```text
L11
↑
L10
↑
L9
↑
L8
```

找到：

```text
L8 = user
```

于是：

```text
turnStart = L8
```

所以第二次又发生：

```text
isSplitTurn = true
```

---

# 33. 第二次的材料怎么分

现在结构是：

```text
S1 | L5 L6 L7 | L8 L9 L10 | L11
                  ↑             ↑
              turnStart       firstKept
```

所以有：

## 旧摘要

```text
previousSummary = S1
```

## 本次又变成普通历史的原文

```text
L5 L6 L7
```

## 本次新 Turn 被切掉的前半段

```text
L8 L9 L10
```

## 继续保留的原文

```text
L11
```

---

# 34. 第二次 Compaction 也会出现两类 LLM 压缩

第一条：

```text
S1 + L5 + L6 + L7
↓
更新历史摘要
↓
H2
```

第二条：

```text
L8 + L9 + L10
↓
Turn Prefix 摘要
↓
P2
```

最后：

```text
S2 = H2 + P2
```

然后活动上下文：

```text
S2
L11
```

---

# 35. 第二次的历史压缩和第一次有什么不同

第一次没有旧摘要。

因此：

```text
L0 L1
↓
普通历史摘要
↓
H1
```

第二次已经有：

```text
S1
```

所以历史摘要实际上是：

```text
旧摘要
+
后来又变成历史的原文
↓
更新摘要
```

即：

```text
S1
+
L5 L6 L7
↓
H2
```

---

# 36. 为什么不能只总结 L5～L7

假设只做：

```text
L5 L6 L7
↓
摘要
```

可能得到：

```text
查询了鸡腿饭、蛋炒饭。
鸡腿饭售罄。
蛋炒饭有货。
已推荐蛋炒饭。
```

但是：

```text
一份午饭
不要辣
20 元以内
不要下单
```

这些都在 S1 中。

如果不把 S1 一起交给大模型，旧信息就会丢掉。

所以第二次必须是：

```text
previousSummary = S1
+
newHistory = L5 L6 L7
```

一起交给大模型。

---

# 37. 第二次历史摘要的目标

它不是要求：

> 给我写一段“增量补丁”。

而是：

> 根据旧摘要和新历史，重新生成一份能够完全取代旧摘要的新摘要。

因此：

```text
H2
```

应该同时包含：

```text
S1 中仍然重要的信息
+
L5～L7 新增的重要信息
```

例如：

```markdown
## Goal
为用户选择合适午饭。

## Constraints & Preferences
- 不要辣。
- 预算为 20 元。
- 只提供方案，不执行下单。

## Progress
- 鸡腿饭售价 20 元。
- 蛋炒饭售价 10 元。
- 已查询库存情况。
- 鸡腿饭目前已售罄。
- 蛋炒饭目前有货。
- 已向用户建议蛋炒饭。
- 尚未下单。
```

这就是：

```text
H2
```

---

# 38. 那 S1 内部原来的 H1 + P1 怎么办

第一次：

```text
S1 = H1 + P1
```

其中：

```text
P1
```

原本是：

```text
第一次被切开的 Turn Prefix
```

到了第二次更新历史时：

```text
S1
```

不会重新拆成：

```text
H1
P1
```

分别处理。

而是：

```text
整个 S1
```

作为：

```text
previousSummary
```

送进新的历史摘要调用。

也就是：

```text
S1 + L5 L6 L7
↓
H2
```

---

# 39. 为什么旧 P1 可以不再保持特殊身份

第一次时：

```text
L2 L3 L4 | L5 L6 L7
```

因为：

```text
L5 L6 L7
```

还保留原文，

所以：

```text
L2 L3 L4
```

必须被特别说明为：

```text
当前 Turn 的前半段
```

因此叫：

```text
Turn Context
```

但是第二次：

```text
L5 L6 L7
```

也准备进入摘要。

于是原本：

```text
L2 L3 L4
+
L5 L6 L7
```

整个过程已经成为过去历史。

所以旧的：

```text
P1
```

可以随着：

```text
S1 + L5 L6 L7
```

一起重新整理进：

```text
H2
```

可以把它理解为：

> 上一次的 Turn Context 到下一次压缩时“毕业”为普通历史。

---

# 40. 第二次新的 Turn Prefix 怎么产生

此时新的：

```text
L8 L9 L10 | L11
```

又被从中间切开。

所以：

```text
L8 L9 L10
```

成为新的：

```text
P2
```

LLM 会针对：

```text
Original Request
Early Progress
Context for Suffix
```

进行摘要，例如：

```markdown
## Original Request
用户要求继续比较鸡腿饭和蛋炒饭，并查询两份午饭的送汤情况；仍不要下单。

## Early Progress
- 已查询送汤信息：
  - 鸡腿饭送汤。
  - 蛋炒饭不送汤。

## Context for Suffix
- 后续保留原文将结合此前库存信息和当前送汤结果进行比较。
```

---

# 41. 第二次最终怎么得到 S2

两条 LLM 调用分别返回：

```text
H2
```

和：

```text
P2
```

程序再做：

```text
H2
+
Turn Context (split turn)
+
P2
```

得到：

```text
S2
```

最终模型看到：

```text
S2
L11
```

---

# 42. 注意：不是每次 Compaction 都一定调用两次 LLM

只有当：

```text
切点落进一个 User Turn 中间
```

也就是：

```text
isSplitTurn = true
```

时，才需要：

```text
历史摘要
+
Turn Prefix 摘要
```

两条路径。

---

# 43. 如果第二次切点正好是 L8

L8 本身是：

```text
user
```

那么：

```text
L8 L9 L10 L11
```

整个新 Turn 都保留原文。

此时：

```text
没有切开当前 Turn
```

所以第二次只需要：

```text
S1 + L5 L6 L7
↓
新的历史摘要 S2
```

然后：

```text
S2
L8
L9
L10
L11
```

没有新的：

```text
Turn Prefix
```

---

# 44. 一次 Compaction 内部的完整逻辑

现在可以把一次 Compaction 画成：

```text
当前路径
   │
   ▼
估算各消息大小
   │
   ▼
从最新往旧累计 keepRecentTokens
   │
   ▼
得到预算落点
   │
   ▼
如果落点不是合法新开头
   │
   ▼
向更新方向找合法切点
   │
   ▼
得到 firstKept
   │
   ▼
从 firstKept 向旧处找最近 user
   │
   ▼
判断是否切进 Turn
   │
   ├─────────────── 不切 Turn
   │                    │
   │                    ▼
   │           previousSummary
   │             + 旧原文
   │                    │
   │                    ▼
   │              LLM 历史摘要
   │                    │
   │                    ▼
   │                新摘要
   │
   └─────────────── 切 Turn
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
      previousSummary       当前 Turn Prefix
       + 旧历史消息
              │                   │
              ▼                   ▼
       LLM 历史摘要       LLM Prefix 摘要
              │                   │
              └─────────┬─────────┘
                        ▼
                    拼成新摘要
```

---

# 45. 最值得记住的方向

假设消息越来越新：

```text
L5   L6   L7   L8   L9   L10   L11
                                  ↑
                                最新
```

## 第一步：预算扫描

```text
L11 → L10 → L9 → ...
```

方向：

```text
向旧
```

## 第二步：非法落点修正

例如落到：

```text
L10 = toolResult
```

那么：

```text
L10 → L11
```

方向：

```text
向新
```

## 第三步：找 Turn 起点

最终切点若是：

```text
L11
```

那么：

```text
L11 → L10 → L9 → L8(user)
```

方向又是：

```text
向旧
```

所以可以记成：

> **向旧处累加预算 → 向新处校正合法切点 → 从最终切点再次向旧处寻找 user turn 起点。**

---

# 46. 第一部分最终总结

整个例子可以浓缩成：

```text
第一次：

L0 L1 | L2 L3 L4 | L5 L6 L7
  │         │           │
  │         │           └─ 保留原文
  │         └─ Prefix → LLM → P1
  └─ History → LLM → H1

S1 = H1 + P1

模型上下文：
S1 + L5 + L6 + L7
```

继续对话：

```text
S1 + L5 L6 L7 + L8 L9 L10 L11
```

第二次：

```text
S1 | L5 L6 L7 | L8 L9 L10 | L11
       │             │          │
       │             │          └─ 保留原文
       │             └─ Prefix → LLM → P2
       └─ 与S1一起 → LLM → H2

S2 = H2 + P2

模型上下文：
S2 + L11
```

---

# 第二部分：把例子抽象成算法

# 47. Compaction 实际解决四个问题

程序需要依次回答：

```text
问题 1：
最近原文应该从哪一条开始？

问题 2：
这个位置是不是合法的消息边界？

问题 3：
这个切点有没有切进一个 user turn？

问题 4：
哪些内容交给历史摘要器，
哪些内容交给 Turn Prefix 摘要器？
```

---

# 48. 核心变量

## keepRecentTokens

```text
近期原文保留预算
```

---

## firstKeptEntryIndex

```text
新的原文从哪一条 Entry 开始
```

例如：

```text
5
```

表示：

```text
从 L5 开始保留原文
```

---

## firstKeptEntryId

数组下标只是当前计算位置。

真正保存时更稳定的是：

```text
Entry ID
```

例如：

```text
firstKeptEntryId = "L5"
```

---

## turnStartIndex

如果切点进入一个 Turn 中间：

```text
从切点向旧处找到对应 user
```

例如：

```text
turnStartIndex = 2
```

---

## isSplitTurn

```text
true
```

表示：

```text
一个 user turn 被切成了两半
```

---

## previousSummary

如果之前已经做过 Compaction：

```text
previousSummary = S1
```

否则：

```text
undefined
```

---

# 49. 第一步：确定本次允许重新考虑的范围

第一次 Compaction：

```text
boundaryStart = 最早可处理位置
```

在本例里就是：

```text
L0
```

第二次 Compaction：

读取最近一次 Compaction 的：

```text
firstKeptEntryId
```

例如：

```text
L5
```

于是：

```text
boundaryStart = L5
```

所以第二次不重新从 L0 开始处理。

---

# 50. 第二步：收集合法切点

合法切点的核心原则：

```text
新的原文不能从一个孤立 toolResult 开始
```

例如：

```text
user
assistant 普通文本
assistant toolCall
```

都可能作为候选。

而：

```text
toolResult
```

通常不加入候选。

第一次：

```text
合法候选：
L0 L1 L2 L3 L5 L7
```

其中：

```text
L4 L6
```

都是 Tool Result。

---

# 51. 第三步：从后往前累计 token

伪逻辑：

```text
accumulated = 0

for message from newest to oldest:
    accumulated += estimateTokens(message)

    if accumulated >= keepRecentTokens:
        找当前位置或更靠后的第一个合法切点
        break
```

所以：

```text
预算落点
```

和：

```text
最终合法切点
```

不一定相同。

---

# 52. 第四步：找 Turn 起点

如果最终切点自身就是：

```text
user
```

那么没有把这个 Turn 从中间切开。

如果最终切点是：

```text
assistant
```

则从它往旧处寻找最近的：

```text
user
```

如果找到：

```text
turnStart < firstKept
```

则：

```text
isSplitTurn = true
```

---

# 53. 第五步：整理摘要材料

如果没有切轮：

```text
messagesToSummarize =
boundaryStart ... firstKept之前
```

```text
turnPrefixMessages = 空
```

如果切轮：

```text
messagesToSummarize =
boundaryStart ... turnStart之前
```

```text
turnPrefixMessages =
turnStart ... firstKept之前
```

保留区：

```text
firstKept ... 当前末尾
```

---

# 54. 第六步：真正调用 LLM

## 没有 split turn

只做：

```text
previousSummary
+
messagesToSummarize
↓
LLM
↓
newSummary
```

---

## 有 split turn

两条路径：

```text
路径 A：

previousSummary
+
messagesToSummarize
↓
LLM
↓
historyResult
```

以及：

```text
路径 B：

turnPrefixMessages
↓
LLM
↓
turnPrefixResult
```

最后：

```text
summary
=
historyResult
+
Turn Context
+
turnPrefixResult
```

---

# 55. 为什么历史路径能收到 previousSummary

因为它需要：

```text
滚动更新长期任务状态
```

所以第二次不能只总结：

```text
新退出原文的消息
```

而必须：

```text
旧摘要
+
新历史
↓
新摘要
```

---

# 56. 为什么 Turn Prefix 路径不需要 previousSummary

因为它的职责不是重新总结整个任务。

它只需要解释：

```text
当前这个被切开的 user turn
在切点以前发生了什么
```

它主要服务于：

```text
切点后仍保留的原文
```

---

# 57. 第七步：保存 Compaction 记录

得到新摘要以后：

```text
appendCompaction
```

保存类似：

```text
id = C1
parentId = 当前 leaf
summary = S1
firstKeptEntryId = L5
```

---

# 58. 第八步：重建模型上下文

系统找到最近 Compaction：

```text
C1
```

先生成一条内部摘要消息：

```text
S1
```

然后根据：

```text
firstKeptEntryId = L5
```

重新取：

```text
L5 L6 L7 ...
```

所以得到：

```text
S1
+
近期原始消息
```

---

# 59. 多次 Compaction 的递推形式

第一次：

```text
H1 = summarize(history1)

P1 = summarizeTurnPrefix(prefix1)

S1 = H1 + P1
```

第二次：

```text
H2 = updateSummary(
    previousSummary = S1,
    newHistory = history2
)

P2 = summarizeTurnPrefix(prefix2)

S2 = H2 + P2
```

第三次：

```text
H3 = updateSummary(
    previousSummary = S2,
    newHistory = history3
)

P3 = summarizeTurnPrefix(prefix3)

S3 = H3 + P3
```

如果某一次没有 split turn：

```text
Pi
```

不存在。

---

# 60. 算法部分一句话总结

Compaction 本质上有两个不同算法层：

## 本地程序算法

```text
估算大小
→ 找切点
→ 保证消息结构完整
→ 找 user turn
→ 分材料
```

## LLM 语义算法

```text
历史材料
→ 长期状态摘要

当前 Turn Prefix
→ 当前轮现场摘要
```

因此：

> **“怎么切”是确定性程序逻辑；“怎么写摘要”是 LLM 生成逻辑。**

---

# 第三部分：代码实现

> 下面是为了教学而整理的简化 TypeScript 风格实现。重点是看数据流，而不是逐字符复刻源码。

---

# 61. 基本数据结构

```ts
type Role =
  | "user"
  | "assistant"
  | "toolResult";

interface Message {
  role: Role;
  text?: string;

  // assistant 可能带 toolCall
  toolCall?: {
    id: string;
    name: string;
    args: unknown;
  };

  // toolResult 对应某个 toolCall
  toolCallId?: string;
}

interface Entry {
  id: string;
  message: Message;
}
```

---

# 62. 估算 token

最简单的教学版：

```ts
function estimateTextTokens(text: string): number {
  return Math.ceil(text.length / 4);
}
```

Message 版：

```ts
function estimateTokens(message: Message): number {
  if (message.role === "assistant" && message.toolCall) {
    const name = message.toolCall.name;
    const args = JSON.stringify(message.toolCall.args);

    return Math.ceil((name.length + args.length) / 4);
  }

  return estimateTextTokens(message.text ?? "");
}
```

这里再次强调：

```text
/4
```

只是一个快速近似。

---

# 63. 找合法切点

```ts
function findValidCutPoints(
  entries: Entry[],
  start: number,
  end: number
): number[] {
  const result: number[] = [];

  for (let i = start; i < end; i++) {
    const msg = entries[i].message;

    // 不让新的原文从孤立 toolResult 开始
    if (msg.role === "toolResult") {
      continue;
    }

    result.push(i);
  }

  return result;
}
```

本例得到：

```ts
[0, 1, 2, 3, 5, 7]
```

---

# 64. 根据预算寻找 firstKept

```ts
interface CutPoint {
  firstKeptEntryIndex: number;
  turnStartIndex: number;
  isSplitTurn: boolean;
}
```

主体逻辑：

```ts
function findCutPoint(
  entries: Entry[],
  startIndex: number,
  endIndex: number,
  keepRecentTokens: number
): CutPoint {

  const validCutPoints =
    findValidCutPoints(entries, startIndex, endIndex);

  let cutIndex = validCutPoints[0];
  let accumulatedTokens = 0;

  for (let i = endIndex - 1; i >= startIndex; i--) {

    accumulatedTokens += estimateTokens(entries[i].message);

    if (accumulatedTokens >= keepRecentTokens) {

      const nextValid = validCutPoints.find(
        candidate => candidate >= i
      );

      if (nextValid !== undefined) {
        cutIndex = nextValid;
      }

      break;
    }
  }

  // 后面继续确定 turn
  // ...

  return {
    firstKeptEntryIndex: cutIndex,
    turnStartIndex: -1,
    isSplitTurn: false
  };
}
```

第一次预算：

```text
L7：18
L6：57
L5：78
L4：115
```

预算落到：

```text
L4
```

然后：

```ts
candidate >= 4
```

第一个合法候选是：

```text
5
```

所以：

```text
cutIndex = 5
```

---

# 65. 找当前 Turn 的 user 起点

```ts
function findTurnStartIndex(
  entries: Entry[],
  cutIndex: number,
  boundaryStart: number
): number {

  for (let i = cutIndex; i >= boundaryStart; i--) {
    if (entries[i].message.role === "user") {
      return i;
    }
  }

  return -1;
}
```

如果：

```text
cutIndex = L5
```

则：

```text
L5 assistant
L4 toolResult
L3 assistant
L2 user
```

得到：

```text
turnStartIndex = 2
```

---

# 66. 完整判断 split turn

```ts
function finishCutPoint(
  entries: Entry[],
  cutIndex: number,
  boundaryStart: number
): CutPoint {

  const cutMessage = entries[cutIndex].message;

  if (cutMessage.role === "user") {
    return {
      firstKeptEntryIndex: cutIndex,
      turnStartIndex: -1,
      isSplitTurn: false
    };
  }

  const turnStartIndex =
    findTurnStartIndex(entries, cutIndex, boundaryStart);

  const isSplitTurn =
    turnStartIndex >= boundaryStart &&
    turnStartIndex < cutIndex;

  return {
    firstKeptEntryIndex: cutIndex,
    turnStartIndex,
    isSplitTurn
  };
}
```

---

# 67. prepareCompaction 的职责

它不是生成摘要。

它只准备：

```text
到底给摘要器什么材料
```

结果类型可以理解成：

```ts
interface CompactionPreparation {
  previousSummary?: string;

  firstKeptEntryId: string;

  messagesToSummarize: Message[];

  turnPrefixMessages: Message[];

  isSplitTurn: boolean;
}
```

---

# 68. 第一次 Compaction 的 prepare

第一次没有旧摘要：

```ts
previousSummary = undefined;
boundaryStart = 0;
```

调用：

```ts
const cut = findCutPoint(
  entries,
  0,
  entries.length,
  79
);
```

得到：

```ts
{
  firstKeptEntryIndex: 5,
  turnStartIndex: 2,
  isSplitTurn: true
}
```

于是：

```ts
messagesToSummarize = [
  L0,
  L1
];

turnPrefixMessages = [
  L2,
  L3,
  L4
];

firstKeptEntryId = "L5";
```

---

# 69. 第二次 Compaction 的 prepare

系统先找到旧 Compaction：

```text
C1
```

读出：

```ts
previousSummary = C1.summary;           // S1
oldFirstKeptId = C1.firstKeptEntryId;   // L5
```

于是：

```text
boundaryStart = L5 所在位置
```

第二次只在：

```text
L5 ... 当前最新消息
```

之间重新找切点。

假设最终：

```text
firstKept = L11
turnStart = L8
```

那么：

```ts
messagesToSummarize = [
  L5,
  L6,
  L7
];

turnPrefixMessages = [
  L8,
  L9,
  L10
];

previousSummary = S1;
```

---

# 70. 把 Message 序列化给 LLM

教学版：

```ts
function serializeConversation(
  messages: Message[]
): string {

  return messages.map(message => {

    if (message.role === "user") {
      return `[User]\n${message.text ?? ""}`;
    }

    if (
      message.role === "assistant" &&
      message.toolCall
    ) {
      return [
        "[Assistant tool calls]",
        `Tool: ${message.toolCall.name}`,
        `Args: ${JSON.stringify(message.toolCall.args)}`
      ].join("\n");
    }

    if (message.role === "toolResult") {
      return [
        "[Tool result]",
        message.text ?? ""
      ].join("\n");
    }

    return `[Assistant]\n${message.text ?? ""}`;

  }).join("\n\n");
}
```

---

# 71. 历史摘要 Prompt

教学版可以理解成：

```ts
const HISTORY_PROMPT = `
请把下面对话整理成一份能够支持后续 Agent
继续工作的状态摘要。

重点保留：

- Goal
- Constraints & Preferences
- Progress
- Key Decisions
- Next Steps
- Critical Context

不要虚构没有发生的操作。
不要把“计划做”写成“已经完成”。

<conversation>
{{conversation}}
</conversation>
`;
```

---

# 72. 有 previousSummary 时使用更新摘要

```ts
const UPDATE_HISTORY_PROMPT = `
下面是上一版摘要：

<previous-summary>
{{previousSummary}}
</previous-summary>

下面是后来又变成历史的对话：

<conversation>
{{conversation}}
</conversation>

请生成一份新的完整摘要。

要求：

1. 新摘要必须能够替代旧摘要；
2. 保留旧摘要中仍然重要的信息；
3. 把新对话中的关键进展合并进去；
4. 不要只输出“新增内容”。
`;
```

---

# 73. Turn Prefix Prompt

```ts
const TURN_PREFIX_PROMPT = `
下面内容是一轮用户请求的前半段。

这一轮的后半段仍然会以原文形式
继续出现在摘要后面。

请只整理理解后半段所必需的信息：

- Original Request
- Early Progress
- Context for Suffix

不要假设后半段已经完成。

<conversation>
{{conversation}}
</conversation>
`;
```

---

# 74. 历史摘要函数

```ts
async function generateHistorySummary(
  messages: Message[],
  previousSummary?: string
): Promise<string> {

  const conversation =
    serializeConversation(messages);

  let prompt: string;

  if (previousSummary) {
    prompt = UPDATE_HISTORY_PROMPT
      .replace(
        "{{previousSummary}}",
        previousSummary
      )
      .replace(
        "{{conversation}}",
        conversation
      );
  } else {
    prompt = HISTORY_PROMPT
      .replace(
        "{{conversation}}",
        conversation
      );
  }

  return await callLLM(prompt);
}
```

真正负责：

```text
“怎么写摘要”
```

的是：

```ts
callLLM(...)
```

---

# 75. Turn Prefix 摘要函数

```ts
async function generateTurnPrefixSummary(
  messages: Message[]
): Promise<string> {

  const conversation =
    serializeConversation(messages);

  const prompt =
    TURN_PREFIX_PROMPT.replace(
      "{{conversation}}",
      conversation
    );

  return await callLLM(prompt);
}
```

注意：

```text
Turn Prefix
```

不需要旧摘要。

---

# 76. compact 的核心结构

```ts
async function compact(
  preparation: CompactionPreparation
): Promise<string> {

  const {
    previousSummary,
    messagesToSummarize,
    turnPrefixMessages,
    isSplitTurn
  } = preparation;

  if (!isSplitTurn) {

    return await generateHistorySummary(
      messagesToSummarize,
      previousSummary
    );
  }

  const [
    historyResult,
    prefixResult
  ] = await Promise.all([

    generateHistorySummary(
      messagesToSummarize,
      previousSummary
    ),

    generateTurnPrefixSummary(
      turnPrefixMessages
    )
  ]);

  return [
    historyResult,
    "",
    "---",
    "",
    "Turn Context (split turn):",
    "",
    prefixResult
  ].join("\n");
}
```

这段代码最直接地解释了：

> 为什么一次 split-turn Compaction 内部会有两次 LLM 摘要调用。

---

# 77. 第一次调用这段代码

Preparation：

```ts
{
  previousSummary: undefined,

  messagesToSummarize: [
    L0,
    L1
  ],

  turnPrefixMessages: [
    L2,
    L3,
    L4
  ],

  isSplitTurn: true,

  firstKeptEntryId: "L5"
}
```

调用后：

```text
L0 L1
↓
historyResult = H1
```

以及：

```text
L2 L3 L4
↓
prefixResult = P1
```

最终：

```text
S1 = H1 + P1
```

---

# 78. 第二次调用这段代码

Preparation：

```ts
{
  previousSummary: S1,

  messagesToSummarize: [
    L5,
    L6,
    L7
  ],

  turnPrefixMessages: [
    L8,
    L9,
    L10
  ],

  isSplitTurn: true,

  firstKeptEntryId: "L11"
}
```

于是：

```text
S1 + L5 L6 L7
↓
historyResult = H2
```

与此同时：

```text
L8 L9 L10
↓
prefixResult = P2
```

最终：

```text
S2 = H2 + P2
```

---

# 79. 保存 Compaction

教学版：

```ts
interface CompactionRecord {
  id: string;
  parentId: string;

  summary: string;

  firstKeptEntryId: string;
}
```

第一次：

```ts
const C1: CompactionRecord = {
  id: "C1",
  parentId: "L7",
  summary: S1,
  firstKeptEntryId: "L5"
};
```

第二次：

```ts
const C2: CompactionRecord = {
  id: "C2",
  parentId: "L11",
  summary: S2,
  firstKeptEntryId: "L11"
};
```

---

# 80. 重建 Session Context

简化逻辑：

```ts
function buildSessionContext(
  entries: Entry[],
  latestCompaction: CompactionRecord
) {
  const result: Message[] = [];

  result.push({
    role: "user",
    text:
      "[Compaction Summary]\n" +
      latestCompaction.summary
  });

  const firstKeptIndex =
    entries.findIndex(
      e =>
        e.id ===
        latestCompaction.firstKeptEntryId
    );

  for (
    let i = firstKeptIndex;
    i < entries.length;
    i++
  ) {
    result.push(entries[i].message);
  }

  return result;
}
```

第一次：

```text
S1
L5
L6
L7
```

第二次：

```text
S2
L11
```

---

# 81. 程序和大模型到底各负责什么

这是整套机制最后一定要分清楚的地方。

## 程序负责

```text
是否需要 Compaction
↓
估算 token
↓
倒序累计预算
↓
找合法切点
↓
避免从 toolResult 开头
↓
找当前 user turn
↓
判断 isSplitTurn
↓
分出 History / Turn Prefix / Suffix
↓
保存 firstKeptEntryId
↓
重建 Context
```

---

## 大模型负责

```text
理解历史消息
↓
提取目标
↓
提取约束
↓
提取进度
↓
提取关键决定
↓
提取后续所需上下文
↓
生成较短的语义摘要
```

所以：

> **切点是谁，程序决定；摘要最后写成什么，大模型决定。**

---

# 82. 最终完整故事线

可以把整个 Compaction 从头到尾记成下面这条链：

```text
对话越来越长
↓
达到 Compaction 条件
↓
程序取得当前 Session 路径
↓
找到上一次 Compaction
↓
确定本次 boundaryStart
↓
从最新 Message 向旧处累计估算 token
↓
达到 keepRecentTokens
↓
得到预算落点
↓
如果是非法消息边界
向更新方向调整到合法 firstKept
↓
从 firstKept 向旧处找 user
↓
判断是否 split turn
↓
把材料分成：

① 普通历史
② 当前 Turn Prefix
③ 近期保留原文

↓
程序把 ① 交给历史摘要 LLM
↓
如果有 ②，
再把 ② 交给 Turn Prefix 摘要 LLM
↓
得到新的 Summary
↓
保存 Compaction Entry
↓
保存 firstKeptEntryId
↓
重新 Build Session Context
↓
后续模型只看到：

Summary + 最近原文
```

---

# 83. 最后用三句话记住全部机制

第一句：

> **`keepRecentTokens` 只负责帮助程序决定最近原文大概从哪里开始保留；`字符串长度 / 4` 只是一个快速估算尺子，不是真实 Tokenizer 规则。**

第二句：

> **程序先“向旧处累计预算 → 向新处校正合法切点 → 再从最终切点向旧处找 user turn”，然后才知道哪些内容应该被摘要。**

第三句：

> **真正的压缩文本由大模型生成：普通历史维护长期任务状态，Turn Prefix 维护当前被切断的一轮的局部现场；多次 Compaction 时，上一版 Summary 会作为 `previousSummary` 与后来变旧的原文一起生成新版 Summary。**


---

最后再强调一次：**压缩结果通过下面这几行代码，写回 Agent 的 `state.messages`。**

在 [agent-session.ts](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1718) 中，下面几步紧挨着；这里的 `compact()` 就是前面 [compaction.ts 中的压缩函数](../pi-master/packages/coding-agent/src/core/compaction/compaction.ts#L717)。

```ts
const result = await compact( // 调用 compaction.ts，生成压缩摘要
  preparation,
  this.model,
  apiKey,
  headers,
  customInstructions,
  this._compactionAbortController.signal,
  this.thinkingLevel,
);
summary = result.summary; // 取出摘要 S1，内部包含 H1 和 P1
firstKeptEntryId = result.firstKeptEntryId;
tokensBefore = result.tokensBefore;
details = result.details;

if (this._compactionAbortController.signal.aborted) {
  throw new Error("Compaction cancelled");
}

this.sessionManager.appendCompaction(summary, firstKeptEntryId, tokensBefore, details, fromExtension); // 保存压缩记录 C1
const newEntries = this.sessionManager.getEntries();
const sessionContext = this.sessionManager.buildSessionContext(); // 根据 C1 组装 [S1, L5, L6, L7]
this.agent.state.messages = sessionContext.messages; // 用压缩后的消息列表替换 Agent 当前历史
```

也就是：生成 S1 → 保存压缩记录 C1 → 重建 `[S1, L5, L6, L7]` → 写回 `state.messages`。
