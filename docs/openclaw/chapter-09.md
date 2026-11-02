---
title: "09 · SessionManager"
description: "openclaw · 会话与上下文 · 课程讲义"
project: "openclaw"
sourcePath: "OpenClaw/OpenClaw-Course/09_SessionManager全流程详解.md"
originalUrl: "/originals/openclaw/chapter-09.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 09 SessionManager 全流程：从 Message、Entry、leafId 到分叉与恢复

> 本文先完全不讲算法实现，也不放代码。
>
> 目标是只用一个“午饭 Agent”的具体例子，把 **Session、Message、Entry、parentId、leafId、byId，以及整个 Agent Session 从创建、保存、分叉、恢复到继续执行的全过程**讲清楚。
>
> 后续再单独讲算法和代码实现。

---

## 1. 先从一个具体任务开始

用户最开始说：

> 帮我选一份不辣的午饭。先给方案，不要下单。

Agent 回答：

> 你的预算是多少？

用户说：

> 20 元以内。

然后 Agent：

1. 调用 `list_meals` 查询午饭；
2. 得到牛肉面 30 元、鸡腿饭 20 元、蛋炒饭 10 元，三份都不辣；
3. 调用 `get_stock` 查询预算内的鸡腿饭、蛋炒饭的库存；
4. 得到鸡腿饭售罄，蛋炒饭有货；
5. 最后回答：“建议蛋炒饭；尚未下单。”

我们把整个过程编号成：

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

现在关键问题来了：

> Agent 到底应该怎么“记住”这件事？

---

## 2. Message 只是“说了什么”

比如 L2：

> 20 元以内。

从聊天本身来看，它只需要记录类似这些信息：

| 字段 | 含义 |
|---|---|
| role | 谁说的，例如 user |
| content | “20 元以内” |
| timestamp | 什么时候产生 |

这个东西叫：

## Message

也就是：

> **真正发送给 Agent / 模型的聊天消息本身。**

但是，只存 Message 不够。

为什么？

假设一个小时以后用户说：

> 不对，我想把预算改成 30 元以内。

那么程序必须知道：

> 你是从原对话的哪个位置开始改的？

仅仅看到一句：

> 30 元以内。

根本不知道它是接在谁后面的。

所以要在 Message 外面再包一层。

---

## 3. Entry 才是 Session 里面真正的“节点”

比如 L2 不再只是：

> 用户：20 元以内。

而是变成一条完整记录：

| 内容 | 值 |
|---|---|
| id | L2 |
| parentId | L1 |
| type | message |
| message | 用户：“20 元以内” |
| timestamp | 某个时间 |

这一个完整对象叫：

## Entry

所以一定要分清：

### Message

负责：

> **“说了什么？”**

### Entry

负责：

> **“这件事情是什么记录？”**

> **“编号是多少？”**

> **“它接在哪条记录后面？”**

可以理解成：

```text
Entry
│
├── id
├── parentId
├── timestamp
├── type
│
└── Message
    ├── role
    └── content
```

这里最重要的是：

> **Session 管理的主要单位其实是 Entry，而不只是 Message。**

因为 Session 以后还要保存一些根本不是普通聊天消息的东西。

例如：

- 模型切换；
- thinking level 变化；
- compaction 摘要；
- branch summary；
- 标签；
- 其他设置变化。

这些也都可以是 Entry。

所以：

> **Message 只是 Entry 的一种内容。**

---

## 4. id 是每个节点的身份证

比如用户两次都说：

> 20 元以内。

文字完全一样。

如果程序以后要说：

> “回到第一次说这句话的位置。”

就不能靠文字查找。

因此每条 Entry 都有自己的：

## id

例如：

```text
L0
L1
L2
L3
...
```

实际程序当然不是 L0、L1，而是 UUID 一类的编号。

这里只是为了教学方便。

所以：

```text
id = 我是谁
```

而不是：

```text
id = 我在数组第几个位置
```

这是很重要的。

因为数组位置可能变化，但：

> **这条 Entry 的 id 不变。**

---

## 5. parentId 决定“我是接在谁后面的”

现在开始出现真正的树结构。

### 5.1 第一条 L0

用户说：

> 帮我选一份不辣的午饭。先给方案，不要下单。

它是整个任务第一条记录。

前面没人。

所以：

```text
L0.parentId = null
```

---

### 5.2 Agent 回答 L1

Agent：

> 你的预算是多少？

这显然是对 L0 的继续。

所以：

```text
L1.parentId = L0
```

---

### 5.3 用户回答 L2

用户：

> 20 元以内。

这是接着 L1 回答。

所以：

```text
L2.parentId = L1
```

于是形成：

```text
L0
│
└── L1
    │
    └── L2
```

再继续：

```text
L0
└── L1
    └── L2
        └── L3
            └── L4
                └── L5
                    └── L6
                        └── L7
```

这时候看起来还只是一条直线。

但是实际上它已经是一棵：

## Tree

只是目前还没有分叉。

所以：

> `parentId` 记录的是**历史上这条 Entry 是接在谁后面生成的**。

---

## 6. 新增一条记录时，程序怎么知道 parentId 填谁？

假设目前已经有：

```text
L0 → L1
```

现在用户输入 L2。

程序创建 L2 时必须写：

```text
L2.parentId = ?
```

它怎么知道应该填 L1？

不是每次都把整棵树遍历一遍。

SessionManager 自己维护一个变量：

## leafId

这是这套机制最关键的变量之一。

---

## 7. leafId 到底是什么？

可以先把它理解成：

> **“如果现在再来一条新的 Entry，它应该接在哪条 Entry 后面？”**

或者更加口语一点：

> **“当前光标停在哪里？”**

比如：

```text
L0 → L1
      ↑
   leafId
```

此时：

```text
leafId = L1
```

现在用户说：

> 20 元以内。

准备创建 L2。

注意这时候：

```text
leafId 还是 L1
```

因此：

```text
L2.parentId = leafId
            = L1
```

L2 创建完成以后：

```text
leafId = L2
```

于是：

```text
L0 → L1 → L2
           ↑
        leafId
```

所以一个非常重要的区别是：

> **parentId 是每条 Entry 自己保存的历史关系。**

> **leafId 是整个 SessionManager 当前保存的“当前位置”。**

可以记成：

```text
parentId = 我当初接在谁后面

leafId = 现在从哪里继续
```

---

## 8. 从一个完全空的 Session 开始看

最开始：

```text
什么都没有
```

此时：

```text
leafId = null
```

---

### 8.1 用户产生 L0

用户：

> 帮我选一份不辣的午饭……

创建 L0 时：

```text
旧 leafId = null
```

所以：

```text
L0.parentId = null
```

创建完成以后：

```text
leafId = L0
```

---

### 8.2 Agent 产生 L1

Agent：

> 你的预算是多少？

创建之前：

```text
leafId = L0
```

所以：

```text
L1.parentId = L0
```

完成后：

```text
leafId = L1
```

---

### 8.3 用户产生 L2

用户：

> 20 元以内。

创建之前：

```text
leafId = L1
```

所以：

```text
L2.parentId = L1
```

完成后：

```text
leafId = L2
```

---

于是整个规则特别简单：

| 新建记录 | 创建前 leafId | 新记录 parentId | 创建后 leafId |
|---|---|---|---|
| L0 | null | null | L0 |
| L1 | L0 | L0 | L1 |
| L2 | L1 | L1 | L2 |
| L3 | L2 | L2 | L3 |
| L4 | L3 | L3 | L4 |
| … | … | … | … |
| L7 | L6 | L6 | L7 |

最终：

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7
                                       ↑
                                    leafId
```

---

## 9. 为什么这个变量叫 leaf？

因为正常情况下：

> 当前对话一直往下走。

那么当前位置自然在树最末端，也就是叶子节点。

所以叫：

```text
leafId
```

但是这个名字稍微有一点迷惑性。

因为：

> **leafId 实际上可以临时指向一个有孩子的中间节点。**

这是理解 Session Tree 最容易卡住的地方。

---

## 10. 真正发生分叉

原任务已经执行完成：

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7
                                       ↑
                                    leafId
```

然后用户突然说：

> 我不想沿着这个结果继续。

> 我要回到刚才询问预算的位置重新来。

也就是说：

> 回到 L1。

于是 SessionManager 把：

```text
leafId
```

从：

```text
L7
```

改成：

```text
L1
```

此时：

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7
      ↑
   leafId
```

注意：

## L2～L7 没有删除。

它们仍然存在。

只是：

> **当前光标回到了 L1。**

这正是为什么 Session 不能简单理解成一个 messages 数组。

如果只是一个数组，你通常只能：

```text
L0 L1 L2 L3 L4 L5 L6 L7
```

然后把后面的删掉。

但是 Session Tree 可以：

> **保留旧路线，同时从中间再开一条新路线。**

---

## 11. 用户现在输入一个新的预算

用户：

> 预算改成 30 元以内，其他要求不变。

我们叫它：

```text
B0
```

创建 B0 前：

```text
leafId = L1
```

所以：

```text
B0.parentId = L1
```

创建后：

```text
leafId = B0
```

树变成：

```text
L0
│
└── L1
    │
    ├── L2 → L3 → L4 → L5 → L6 → L7
    │
    └── B0
         ↑
      leafId
```

这个图特别重要。

因为：

```text
L2路线 = 20 元预算方案

B0路线 = 30 元预算方案
```

两条路线都保存着。

---

## 12. B0 为什么还知道“不辣、先给方案、不下单”？

因为 B0 不是一个孤立节点。

它有：

```text
B0.parentId = L1
```

然后：

```text
L1.parentId = L0
```

于是从 B0 往前追：

```text
B0
↑
L1
↑
L0
```

倒过来就是当前路径：

```text
L0 → L1 → B0
```

所以模型这一次真正应该看到的是：

1. L0：选一份不辣的午饭，先给方案，不要下单；
2. L1：你的预算是多少？
3. B0：预算改成 30 元以内，其他要求不变。

而不应该看到：

```text
L2
L3
L4
L5
L6
L7
```

因为那些属于：

> **20 元预算那条兄弟分支。**

所以特别重要的一点是：

> **Session 保存的记录 ≠ 当前模型看到的历史。**

Session 中现在一共保存：

```text
L0 L1 L2 L3 L4 L5 L6 L7 B0
```

一共 9 条。

但是当前模型输入只有：

```text
L0 L1 B0
```

---

## 13. Session 到底是什么？

现在可以比较完整地定义它了。

Session 绝对不是：

> 一个 messages 数组。

更接近：

```text
Session
│
├── 一堆 Entry
│
│   ├── L0
│   ├── L1
│   ├── L2
│   ├── ...
│   └── B0
│
├── Entry 之间的 parentId 关系
│
├── 当前 leafId
│
├── byId 索引
│
├── Session 本身的 metadata
│
└── 持久化文件
```

因此它实际上是一份：

> **带历史树、当前位置以及恢复能力的 Agent 工作档案。**

---

## 14. byId 又是干什么的？

现在我们知道：

```text
B0.parentId = L1
```

那么程序需要：

> 根据字符串 `"L1"` 找到真正的 L1 Entry。

如果每次都把所有 Entry 从头扫一遍，会很麻烦。

所以 SessionManager 还维护：

## byId

你可以把它想象成一张通讯录：

| ID | 对应 Entry |
|---|---|
| L0 | L0完整对象 |
| L1 | L1完整对象 |
| L2 | L2完整对象 |
| … | … |
| B0 | B0完整对象 |

于是从 B0 往前找：

```text
B0.parentId = L1
        ↓
byId["L1"]
        ↓
得到 L1

L1.parentId = L0
        ↓
byId["L0"]
        ↓
得到 L0
```

最后：

```text
L0.parentId = null
```

停止。

所以几个概念一定要分开：

| 东西 | 作用 |
|---|---|
| Message | 具体说了什么 |
| Entry | Session 树中的一个节点 |
| parentId | 当前节点的上一节点是谁 |
| leafId | 当前从哪里继续 |
| byId | 根据 id 快速找到 Entry |

---

## 15. 当前模型真正需要历史时怎么办？

现在 leafId 是：

```text
B0
```

SessionManager 并不是简单把所有 Entry 全扔给模型。

而是：

### 第一步

从：

```text
B0
```

开始。

### 第二步

看：

```text
B0.parentId = L1
```

找到 L1。

### 第三步

看：

```text
L1.parentId = L0
```

找到 L0。

### 第四步

L0：

```text
parentId = null
```

停止。

于是先得到：

```text
B0 ← L1 ← L0
```

再反过来：

```text
L0 → L1 → B0
```

这就是：

## 当前 Branch

然后从这些 Entry 中把 Message 提取出来：

```text
Message(L0)
Message(L1)
Message(B0)
```

最后才得到 Agent 真正使用的：

```text
messages
```

---

## 16. 三个特别容易混淆的概念

### 16.1 全部 Entry

Session 里面曾经发生过：

```text
L0
L1
L2
L3
L4
L5
L6
L7
B0
```

这是：

> **整份历史档案。**

---

### 16.2 当前 Branch

根据 B0 往前走：

```text
L0
L1
B0
```

这是：

> **当前路线。**

---

### 16.3 当前 messages

再从当前 Branch 中筛出真正的消息 Entry：

```text
user
assistant
user
toolResult
……
```

组成模型历史。

这是：

> **Agent 当前真正看到的上下文消息。**

三者不是同一个东西。

---

## 17. 为什么 Entry 数量有时候比 Message 数量更多？

假设到了 L1 后，用户把 thinking level 改成：

```text
high
```

Session 可能变成：

```text
L0
↓
L1
↓
T1：thinkingLevel = high
↓
L2
```

T1 也是 Entry。

但是它并不是：

```text
user message
```

也不是：

```text
assistant message
```

所以重建模型历史的时候：

```text
L0 Message
L1 Message
T1 设置
L2 Message
```

最终 messages 可能只有：

```text
L0
L1
L2
```

但是 Session Context 另外会恢复：

```text
thinkingLevel = high
```

所以可以理解成：

> Entry 记录“这个 Session 里发生了什么”。

而：

> Message 只记录“谁说了什么”。

压缩记录也是同样的道理，它也可以作为独立 Entry 存在。

---

## 18. Session 文件里实际上保存什么？

假设 Session 最后已经形成：

```text
L0
└─ L1
   ├─ L2 → ... → L7
   └─ B0
```

文件里不会真的按照树形缩进保存。

而是按照：

> **Entry 产生的时间顺序**

一条一条写进去。

比如：

```text
Header
L0
L1
L2
L3
L4
L5
L6
L7
B0
```

问题来了：

B0 明明是在 L7 后面写入文件的。

为什么它不是：

```text
L7 → B0
```

因为它自己写着：

```text
B0.parentId = L1
```

所以：

> **文件顺序负责表示“什么时候产生”；parentId 负责表示“树上接在哪里”。**

这是两个完全不同的关系。

---

## 19. Header 是什么？

Header 不算 Entry。

Session 文件第一部分还有一个：

## Header

它负责描述：

> 这一整份 Session 是谁。

例如包括：

- sessionId；
- cwd；
- 创建时间；
- 文件格式版本。

可以理解成：

```text
一本书
│
├── 封面：Header
│
└── 正文
    ├── Entry L0
    ├── Entry L1
    ├── Entry L2
    └── ...
```

所以：

> Header 不是 L0 的 parent。

L0 仍然：

```text
parentId = null
```

---

## 20. 把“保存流程”从头走一次

现在重新从最开始完整跑。

### 阶段 A：创建 Session

刚开始：

```text
Entries = 空
byId = 空
leafId = null
```

同时准备：

```text
Session Header
```

但是还没有聊天记录。

---

### 阶段 B：用户发送第一句话 L0

用户：

> 选一份不辣的午饭，先给方案，不要下单。

此时 Session 层收到这个 Message。

把它包装成 Entry：

```text
L0
```

创建时：

```text
parentId = 当前 leafId = null
```

然后：

```text
Entries 加入 L0
byId 加入 L0
leafId = L0
```

---

### 阶段 C：Agent 回答 L1

Agent：

> 你的预算是多少？

同样：

```text
parentId = 当前 leafId = L0
```

产生：

```text
L1.parentId = L0
```

然后：

```text
leafId = L1
```

---

### 阶段 D：用户发送 L2

> 20 元以内。

所以：

```text
L2.parentId = L1
leafId = L2
```

---

### 阶段 E：Agent 开始调用工具

Agent 决定：

> 我要先调用 list_meals 查询午饭。

产生 L3。

于是：

```text
L3.parentId = L2
leafId = L3
```

---

## 21. 工具执行结果 L4 是怎么进入 Session 的？

工具返回：

> 牛肉面 30 元，鸡腿饭 20 元，蛋炒饭 10 元，三份都不辣。

首先这还是：

## ToolResultMessage

也就是说：

> 工具执行层产生了一条消息。

Agent 首先把它加入自己的：

```text
agent.state.messages
```

也就是说，在 Agent 看来：

> 工具结果已经发生了。

然后 AgentSession 的事件处理逻辑收到：

```text
message_end
```

再把这个 Message 交给 SessionManager。

此时 SessionManager 看自己的：

```text
leafId = L3
```

于是给 L4 创建 Entry：

```text
L4.parentId = L3
```

然后：

```text
leafId = L4
```

再把它写入 Session 文件。

所以完整路径大致是：

```text
工具执行完成
↓
产生 ToolResult Message
↓
Agent 把它加入自己的消息状态
↓
AgentSession 收到消息完成事件
↓
SessionManager 把 Message 包装成 Entry
↓
parentId = 当前 leafId
↓
更新 byId
↓
更新 leafId
↓
持久化
```

注意：

> Agent 层保存的是 ToolResultMessage。

而 SessionManager 保存的是：

> 包含 id、parentId、timestamp、message 的 Entry。

---

## 22. 为什么还需要一个事件队列？

考虑：

```text
L3
↓
L4
↓
L5
```

如果事件同时乱序处理：

假如 L5 保存的时候 L4 还没保存完。

那么 L5 看到的 leafId 可能还是：

```text
L3
```

于是可能错误地变成：

```text
L3
├─ L4
└─ L5
```

但实际上应该是：

```text
L3
└─ L4
   └─ L5
```

因此 Session 这一层对事件：

> **按顺序排队处理。**

保证：

```text
L3先完成
↓
leafId=L3

L4保存
↓
leafId=L4

L5保存
↓
leafId=L5
```

这样 parentId 才不会错。

---

## 23. 第一次任务最终执行完成

最后形成：

```text
L0 用户：选一份不辣的午饭，先给方案，不下单
↓
L1 Agent：你的预算是多少？
↓
L2 用户：20 元以内
↓
L3 Agent：调用 list_meals
↓
L4 Tool：牛肉面30元、鸡腿饭20元、蛋炒饭10元，均不辣
↓
L5 Agent：调用 get_stock，查鸡腿饭、蛋炒饭的库存
↓
L6 Tool：鸡腿饭售罄，蛋炒饭有货
↓
L7 Agent：建议蛋炒饭，尚未下单
```

此时：

```text
leafId = L7
```

Agent 当前 messages 也大体对应：

```text
L0～L7
```

---

## 24. 用户点击“回到 L1”

这时候不是普通 append。

而是：

## Navigation

用户要求：

> 把当前 Session 的位置改回 L1。

这里会同时牵涉：

- SessionManager
- Agent

这两个状态都必须修改。

---

## 25. 第一步：先记住自己原来在哪

原来：

```text
oldLeafId = L7
```

目标：

```text
targetId = L1
```

于是程序可以知道：

> 我要从 L7 那条路线离开，回到 L1。

同时它还能找出：

```text
L0 → L1
```

是公共部分。

而：

```text
L2 → L3 → L4 → L5 → L6 → L7
```

是准备离开的部分。

这以后如果需要：

> Branch Summary

就可以总结这一段。

本例暂时不总结。

---

## 26. 第二步：SessionManager 改 leafId

于是：

```text
leafId = L1
```

注意到这里：

> SessionManager 已经知道当前位置是 L1。

但是还有一个问题：

## Agent 自己可能还保存着 L0～L7。

所以还没结束。

---

## 27. 第三步：重新构建当前 Branch

现在：

```text
leafId = L1
```

SessionManager 从 L1 往回：

```text
L1.parentId = L0
L0.parentId = null
```

于是当前路径：

```text
L0 → L1
```

然后重新构造：

```text
messages = [L0, L1]
```

---

## 28. 第四步：把 Agent 的历史也换掉

原来 Agent 内部：

```text
messages = L0～L7
```

现在替换成：

```text
messages = L0、L1
```

到这里以后：

> SessionManager 和 Agent 才真正重新对齐。

这也是为什么：

> **只改 leafId 是不够的。**

低层 SessionManager 只负责：

> 当前 Session 在哪。

高层 AgentSession 还必须：

> 把 Agent 真正看到的上下文重建出来。

---

## 29. 现在用户重新输入 B0

用户：

> 预算改成 30 元以内，其他要求不变。

此时：

```text
leafId = L1
```

所以：

```text
B0.parentId = L1
```

保存后：

```text
leafId = B0
```

整棵树：

```text
                         ┌→ L2 → L3 → L4 → L5 → L6 → L7
L0 → L1 ────────────────┤
                         └→ B0
                             ↑
                          leafId
```

Agent 当前 messages：

```text
L0
L1
B0
```

---

## 30. 为什么 Agent 要按新预算重新查询？

为什么不能直接拿：

```text
L6：鸡腿饭售罄，蛋炒饭有货
```

来用？

因为：

> L6 位于另外一个 Branch。

当前 Branch 是：

```text
L0 → L1 → B0
```

里面没有 L6。

而且用户预算已经从：

```text
20 元以内
```

变成：

```text
30 元以内
```

30 元预算下，牛肉面也进入了可选范围，需要查询它的库存。旧分支的工具结果不能自动当作当前分支已经查询过的事实。

这正是 Session Tree 非常重要的意义：

> **共享共同历史，但隔离分叉后的事实。**

---

## 31. 如果程序关闭，再打开这个 Session，会发生什么？

假设文件中已经保存：

```text
Header
L0
L1
L2
L3
L4
L5
L6
L7
B0
```

程序重新启动。

---

### 31.1 打开文件

SessionManager 读 JSONL。

得到：

- Header；
- 所有 Entry。

---

### 31.2 重新建立 byId

依次把：

```text
L0
L1
L2
...
B0
```

登记进去。

于是又有：

```text
byId["L0"]
byId["L1"]
...
byId["B0"]
```

---

### 31.3 恢复 leafId

文件最后保存的是：

```text
B0
```

因此重建后：

```text
leafId = B0
```

---

## 32. 恢复时不是把 9 条消息全部塞给 Agent

接下来会构建 Session Context。

它看到：

```text
leafId = B0
```

于是追：

```text
B0
↑
L1
↑
L0
```

得到：

```text
L0 → L1 → B0
```

所以恢复出来的：

```text
existingSession.messages
```

只有：

```text
L0
L1
B0
```

最后创建 Agent 时：

> 把这 3 条消息装进去。

所以重新打开后，模型接着记得：

> “选一份不辣的午饭，先给方案、不下单，现在预算改成 30 元以内。”

而不会错误地把旧 20 元预算分支的查询结果混进去。

---

## 33. 完整的“恢复链”

```text
Session 文件
↓
读 Header + Entries
↓
恢复全部 Entry
↓
建立 byId
↓
恢复 leafId
↓
从 leafId 沿 parentId 往前走
↓
得到当前 Branch
↓
从 Branch 中恢复 Messages / Model / ThinkingLevel
↓
创建 Agent
↓
把当前 messages 放入 Agent
↓
Agent 可以继续工作
```

这里要特别注意：

> **恢复的不是“整个运行现场”。**

恢复的是：

- 会话记录；
- 当前分支；
- 模型相关设置；
- thinking level 等 Session 信息。

工具正在执行到一半的临时状态、进程里的临时变量等，不能仅靠 Session 文件完整恢复。

---

## 34. 如果点击的是 L2 用户消息呢？

假如树：

```text
L0
↓
L1
↓
L2：用户“20 元以内”
↓
L3
...
```

用户在 UI 中点击：

```text
L2
```

他的目的通常不是：

> 从 L2 后面继续。

而是：

> 我要修改 L2。

所以系统实际会：

```text
leafId = L2.parentId
       = L1
```

然后把：

> “20 元以内”

重新放到编辑框里。

用户改成：

> 30 元以内

提交。

于是产生：

```text
B0.parentId = L1
```

最终：

```text
            ┌─ L2：20 元预算
L0 → L1 ────┤
            └─ B0：30 元预算
```

这个设计非常关键：

> 修改一条旧用户输入，本质上不是“修改原 Entry”。

而是：

> **回到它产生之前的位置，再生成一个新的兄弟 Entry。**

原来的 L2 继续保留。

因此历史不会丢失。

---

## 35. 如果已经进行过上下文压缩，再分叉和恢复怎么办

**已经压缩过，仍然可以回到旧节点、创建新分支和恢复会话。因为 Compaction 保留原始 Entry，改变的是 Agent 当前使用的消息列表。**

压缩上下文的组装代码将在第 55 节展开；这一节先看压缩与导航、分叉和恢复组合后会发生什么。下面仍省略初始化设置节点，并先讨论不生成 Branch Summary 的情况。

### 35.1 压缩以后，树与 Agent 的 messages 已经不同

沿用第 08 节：完成第一轮点餐后，生成压缩记录 C1：

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7 → C1
                                          ↑
                                       leafId

C1.summary = S1
C1.firstKeptEntryId = L5
```

原始消息没有从树里删除。C1 是追加到 L7 后面的一个独立 Entry，保存摘要 S1 和近期原文的保留起点 L5。

这时两个函数得到的东西不同：

| 调用 | 结果 |
|---|---|
| `getBranch()` | `[L0, L1, L2, L3, L4, L5, L6, L7, C1]`，包含完整路径上的 Entry |
| `buildSessionContext().messages` | `[S1 对应的摘要消息, Message(L5), Message(L6), Message(L7)]` |

后续代码框中的 `S1` 都是摘要消息的简写，不表示直接把一个字符串塞进 `AgentMessage[]`。

因此，**“沿 parentId 回溯得到路径”只是第一步，还需要解析路径上的压缩记录，才能得到 Agent 应使用的历史。**

### 35.2 沿着 C1 继续对话：保留摘要，追加新消息

用户没有回退，而是继续提出第 08 节的后续要求：

> 再比较一下鸡腿饭和蛋炒饭，顺便看看它们是否送汤，还是不要下单。

这条消息记作 L8。因为此时 leaf 是 C1，所以：

```text
L8.parentId = C1
```

工具查询和回答继续产生 L9～L11：

```text
L0 → ... → L7 → C1 → L8 → L9 → L10 → L11
```

当前路径里仍有 C1，因此上下文重建结果是：

```text
S1 + L5 + L6 + L7 + L8 + L9 + L10 + L11
│    └────┬────┘    └─────────┬─────────┘
摘要   压缩前保留原文      压缩后新增消息
```

这不是重新把 L0～L4 原文加回来，而是在压缩后的历史上继续工作。

### 35.3 回到 L1 再改预算：新路径里没有 C1

现在换一种操作：用户从已经压缩的会话中回到 L1，再输入“预算改成 30 元以内”。

```text
L0 → L1
      ├── L2 → L3 → L4 → L5 → L6 → L7 → C1
      └── B0：预算改成 30 元以内
           ↑
        leafId
```

从 B0 回溯得到的是：

```text
L0 → L1 → B0
```

这条路径没有 C1，所以 `buildSessionContext()` 不会使用旧摘要 S1。Agent 看到的是：

```text
L0：帮我选一份不辣的午饭。先给方案，不要下单。
L1：你的预算是多少？
B0：预算改成 30 元以内，其他要求不变。
```

旧摘要中的“20 元预算”“已查询鸡腿饭和蛋炒饭”等信息不会自动带进来。原始消息仍在，所以程序也不需要先让模型把 S1“解压”成原文。

如果用户选择生成 Branch Summary，旧路线的信息可以通过新追加的分支摘要进入当前路径，具体结构见后面的第 57 节；这与自动继承 C1 是两回事。

### 35.4 一个容易忽略的情况：回到 L7，也会绕开 C1

压缩记录的父子关系是：

```text
L7 → C1
```

因此，虽然 L7 是压缩前最后一条助手回答，但从 C1 导航回 L7 后，当前路径只到 L7 为止：

```text
L0 → L1 → ... → L7
```

C1 是 L7 的后继，不能通过沿父指针回溯找到。若这条路径上没有其他更早的压缩记录，**重建结果就会重新包含 L0～L7 的原始消息**。

可以把不同位置的结果放在一起比较：

| 当前 leaf | 当前路径是否包含 C1 | 重建后的 messages |
|---|---|---|
| C1 | 包含 | S1 + L5～L7 |
| C1 之后的 L11 | 包含 | S1 + L5～L7 + L8～L11 |
| 回退后的 L7 | 不包含 | L0～L7 原文 |
| 从 L1 分叉后的 B0 | 不包含 | L0、L1、B0 原文 |

**是否使用某条压缩记录，取决于它是否位于当前 leaf 的祖先路径上。** 不能只看“这个文件以前是否压缩过”。

### 35.5 代码为什么会得到这些结果

关键代码仍在 [buildSessionContext()](/source/?file=043f6d188e65e3207b.ts#L322)。先回溯当前路径，源码节选：

```ts
const path: SessionEntry[] = [];
let current: SessionEntry | undefined = leaf;
while (current) {
  path.unshift(current);
  current = current.parentId ? byId.get(current.parentId) : undefined;
}
```

然后只在这条 `path` 中扫描压缩记录。下面是省略模型和 thinking level 处理后的源码节选：

```ts
let compaction: CompactionEntry | null = null;

for (const entry of path) {
  // 此处省略其他类型的处理
  if (entry.type === "compaction") {
    compaction = entry;
  }
}
```

因为路径按旧到新排列，`compaction` 最终指向**当前路径上最后一条压缩记录**。这里没有从整个 Session 文件里直接取最后一条 Compaction。

接下来根据它是否存在分两路处理。教学简化：

```ts
if (compaction) {
  // ① 放入该记录的摘要消息
  // ② 放入 firstKeptEntryId 到该压缩记录之前的保留消息
  // ③ 放入该压缩记录之后新增的消息
} else {
  for (const entry of path) {
    appendMessage(entry);
  }
}
```

这也解释了多次压缩的处理：如果当前路径中先后有 C1、C2，就以 C2 的摘要和保留起点重建；不会简单地把 S1、S2 两份摘要都拼到最前面。第 08 节的 `previousSummary` 更新过程负责把仍需保留的旧摘要信息合入新版摘要。

### 35.6 关闭后再恢复，仍然先看路径，再处理压缩

恢复不会直接把 JSONL 中所有 `message` 行交给 Agent，而是继续走：

```text
读取 Header 和所有 Entry
↓
_buildIndex() 重建索引，恢复到最后写入的 Entry
↓
buildSessionContext() 沿 parentId 找当前路径
↓
查找该路径上的最后一条 Compaction
↓
有压缩：摘要 + 保留原文 + 后续消息
无压缩：按当前路径提取消息
↓
createAgentSession() 把结果装入 Agent
```

所以，文件最后写入 C1 时，恢复出 `S1 + L5～L7`；最后写入 L11 时，恢复出 `S1 + L5～L11`；最后写入新分支的 B0 时，恢复出 `L0、L1、B0`。

还需注意一个将在第 58 节详细解释的恢复边界：如果只是把内存中的 leaf 从 C1 移到 L1，没有再追加任何记录，文件最后一条仍是 C1，重新加载后就会恢复到 C1。

> **完整规则是：先确定当前 Branch，再解析这条 Branch 上的压缩记录，最后生成 Agent 的 messages。`getBranch()` 保留历史结构，`buildSessionContext()` 才负责还原当前应使用的上下文。**

---

## 36. Branch 和 Fork 的区别

Branch 是：

> 同一 Session 内部有多条路线。

而 Fork 更像：

> 把某一条路线单独复制出去，变成新的 Session。

比如当前 Session：

```text
            ┌─ 20 元预算路线
L0 → L1 ────┤
            └─ 30 元预算路线
```

如果用户把：

```text
L0 → L1 → L2
```

Fork 出去，

那么新 Session 可以只保留：

```text
L0 → L1 → L2
```

从这里单独继续。

所以：

### Branch

还是：

> 同一本“档案”里的不同路线。

### Fork

是：

> 从其中一条路线复制出另一份“档案”。

---

## 37. switchSession 又不一样

假设现在有：

```text
Session A：午饭点餐
Session B：写论文
Session C：写代码
```

`switchSession` 就不是：

> 在树里移动。

而是：

> **把当前整套 Session 换成另外一份 Session。**

所以不仅要换：

```text
leafId
```

而是要换：

- SessionManager；
- AgentSession；
- 对应 services；
- UI 订阅关系等。

可以粗略理解成：

```text
navigateTree
=
在一本书里翻到另一页

switchSession
=
把手里这本书放下，
换另外一本书
```

---

## 38. newSession

它相当于：

> 拿一本新的空白笔记本。

新的：

```text
Header
Entries = 空
leafId = null
```

然后重新开始。

---

## 39. reload

reload 并不是：

> 换 Session。

它主要是在原 Session 不变的情况下重新加载：

- 设置；
- API Provider；
- 资源；
- Tools；
- Extensions；
- System Prompt 等运行环境。

也就是说：

```text
Session历史
不变
```

但：

```text
Agent运行资源
重新加载
```

---

## 40. 几个操作的区别

| 操作 | 本质 |
|---|---|
| append | 当前 leaf 后面新增 Entry |
| branch / navigate | 当前 Session 内移动到另一位置 |
| fork | 当前 Branch 复制成一份新 Session |
| switchSession | 换到另一份已有 Session |
| newSession | 新建空 Session |
| reload | Session 不换，重新加载运行资源 |

---

## 41. Agent 和 SessionManager 是两份状态

实际上运行中的 Agent 有两份“历史状态”。

第一份在：

## Agent

例如：

```text
agent.state.messages
```

它回答：

> **模型下一轮实际看到哪些 Message？**

第二份在：

## SessionManager

例如：

```text
Entries
byId
leafId
```

它回答：

> **完整会话树是什么？现在停在哪？**

所以：

```text
Agent
≠
SessionManager
```

通常两边会保持一致。

例如当前：

```text
SessionManager leafId = B0
```

对应：

```text
Agent.messages = L0, L1, B0
```

但是某些操作中间的瞬间，它们可能暂时不同步。

比如：

> 工具结果刚进入 Agent，但 Session 的事件队列还没把它包装成 Entry。

或者：

> SessionManager 已经 branch 到 L1，但 Agent 的 messages 还没执行替换。

因此完整过程需要：

```text
改变 SessionManager
↓
重新构建 Session Context
↓
再改变 Agent.messages
```

---

## 42. 用 Git 类比理解 Entry、leaf 和 Session

如果把整套系统想象成“Git + 聊天记录”，会比较容易理解。

### Entry

类似一个 Commit：

> 一次发生过的事情。

它知道：

```text
自己的 id
自己的内容
自己的 parent
```

---

### parentId

类似 Commit 的父 Commit：

> 我是接在哪一步后面产生的。

---

### leafId

很像：

> 当前 checkout 到哪里。

下一次产生新内容时：

> 就从这里往下接。

虽然名字叫 leaf，但它可以 checkout 到中间节点。

---

### Session

则相当于：

> 整个 Repository。

里面不仅有当前路线，还有：

> 曾经走过但现在没有选中的其他路线。

这个类比不是源码术语，只是用于理解数据关系。

---

## 43. 把整个午饭点餐例子压成一条完整故事线

一开始：

```text
Session为空
leafId=null
```

用户说：

```text
L0：选一份不辣的午饭，先给方案，不下单
```

于是：

```text
L0.parentId=null
leafId=L0
```

Agent：

```text
L1：你的预算是多少？
```

于是：

```text
L1.parentId=L0
leafId=L1
```

用户：

```text
L2：20 元以内
```

于是：

```text
L2.parentId=L1
leafId=L2
```

Agent 和工具继续执行：

```text
L3
↓
L4
↓
L5
↓
L6
↓
L7
```

最终：

```text
leafId=L7
```

完整路径：

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7
```

---

用户决定：

> 回到询问预算那里。

于是：

```text
leafId=L1
```

旧路线不删除：

```text
L2～L7依然存在
```

同时重新构建 Agent 历史：

```text
L0
L1
```

---

用户说：

```text
B0：改成30 元以内
```

于是：

```text
B0.parentId=L1
leafId=B0
```

树成为：

```text
                         20 元预算
                    ┌→ L2 → L3 → L4 → L5 → L6 → L7
                    │
L0 → L1 ────────────┤
                    │
                    └→ B0
                        30 元预算
                         ↑
                      leafId
```

当前 Session 保存：

```text
L0
L1
L2
L3
L4
L5
L6
L7
B0
```

但是当前 Branch 是：

```text
L0
L1
B0
```

所以当前 Agent 看见：

```text
L0
L1
B0
```

然后 Agent 按照：

> 30 元预算的新条件

重新执行查询。

程序关闭以后，Session 文件仍然保留整棵历史树。

重新打开：

```text
读取全部Entry
↓
重建byId
↓
恢复leafId
↓
沿parentId找到当前Branch
↓
提取当前Messages
↓
恢复模型和ThinkingLevel
↓
重新创建Agent
```

于是继续从：

```text
L0 → L1 → B0
```

工作。

---

## 44. 最核心的一张图

```text
                         Session
                            │
             ┌──────────────┴──────────────┐
             │                             │
        保存所有历史                    当前运行位置
          Entries                         leafId
             │                             │
       每个 Entry                         │
       都有 parentId                       │
             │                             │
             └───────────┬─────────────────┘
                         ↓
                 找到当前 Branch
                         ↓
                 buildSessionContext
                         ↓
              提取当前 Messages
                         ↓
                Agent.state.messages
                         ↓
                  模型继续执行
                         ↓
              新 Message / Tool Result
                         ↓
                   包成新 Entry
                         ↓
             parentId = 当前 leafId
                         ↓
                leafId = 新 Entry
                         ↓
                    持久化
```

这就是整套 Agent Session 最核心的一整个循环。

---

## 45. 一句话总结

可以把整个 Agent Session 理解成：

> **Session 保存整棵历史树，Entry 是树中的节点，parentId 保存节点之间的历史关系，leafId 表示当前从哪里继续，byId 用来根据编号快速找到节点；模型每一轮真正看到的历史，则是从当前 leafId 沿 parentId 回溯得到的当前 Branch 中提取出的 Messages。**

以下算法会在本讲第二部分、第 14 讲和[选读《Pi 会话系统源码解析》](/openclaw/session-tree#x-session-01)中继续展开。读完历史保存与恢复，再依次看第 10 讲的资源加载、第 11 讲的长期记忆、第 12 讲的互联网 RAG、第 13 讲的会话装配，最后进入第 14 讲的执行过程：

1. Session 的核心算法；
2. `append` 算法；
3. `getBranch` 算法；
4. `buildSessionContext` 算法；
5. `navigateTree` 算法；
6. Session 恢复算法；
7. 最后逐段对应源码实现。

下一讲：[10 Bootstrap、Skill 与 Extension 加载原理](/openclaw/chapter-10)

---

## 第二部分：点餐 Session 在代码里怎样实现

> 前面 1～45 节先建立直观认识。下面继续用同一个点餐任务，把这些概念逐段对应到当前仓库的代码。
>
> 标为“源码节选”的代码来自实际实现，可能省略注释或无关分支；标为“教学简化”的代码只用于展示主流程，不是可以独立运行的完整实现。
>
> `L0`～`L7`、`B0` 仍然是教学编号。真实调用返回的是程序生成的 Entry ID。

## 46. 先找到四层代码各自负责什么

| 层次 | 源码位置 | 在点餐例子里的职责 |
|---|---|---|
| Agent 循环与状态 | [agent-loop.ts](/source/?file=6adbf9ab77a3572a2f.ts)、[agent.ts](/source/?file=3688aa044ebb960834.ts) | 执行 `list_meals`、`get_stock`，产生消息和事件，更新运行中的消息状态 |
| AgentSession | [agent-session.ts](/source/?file=24209413646c397dc9.ts) | 订阅事件，把完成消息交给 SessionManager；导航后重建 Agent 的消息历史 |
| SessionManager | [session-manager.ts](/source/?file=043f6d188e65e3207b.ts) | 保存 Entry、维护 `byId` 和 `leafId`、回溯分支、读写 JSONL |
| 创建与替换运行环境 | [sdk.ts](/source/?file=07502145bf1ffa712b.ts)、[agent-session-runtime.ts](/source/?file=70034fc47cc255a0a5.ts) | 从历史创建 Agent；执行新建、切换、Fork，并重新绑定运行环境 |

这里要对应当前版本的实际类名：`agent-session-runtime.ts` 中的类叫 **`AgentSessionRuntime`**。交互模式里使用的 `runtimeHost` 是持有它的变量名。

因此，前面提到的操作，在当前代码中的入口分别是：

```text
保存消息       → AgentSession._processAgentEvent()
追加节点       → SessionManager.appendMessage()
读取当前分支   → SessionManager.getBranch()
重建上下文     → SessionManager.buildSessionContext()
同文件内导航   → AgentSession.navigateTree()
新建 / 切换 / Fork → AgentSessionRuntime
恢复后创建 Agent → createAgentSession()
```

---

## 47. Message、Entry、Header 在类型上怎样分开

源码节选，位置：[session-manager.ts 的类型定义](/source/?file=043f6d188e65e3207b.ts#L31)。

```ts
export interface SessionHeader {
  type: "session";
  version?: number;
  id: string;
  timestamp: string;
  cwd: string;
  parentSession?: string;
}

export interface SessionEntryBase {
  type: string;
  id: string;
  parentId: string | null;
  timestamp: string;
}

export interface SessionMessageEntry extends SessionEntryBase {
  type: "message";
  message: AgentMessage;
}

export type FileEntry = SessionHeader | SessionEntry;
```

`SessionEntry` 是消息记录、模型变化、压缩记录、分支摘要等类型的联合；`FileEntry` 另外包含文件头。

所以 L2 的层次是：

```text
SessionMessageEntry
├── type: "message"
├── id: L2 的真实 ID
├── parentId: L1 的真实 ID
├── timestamp: Entry 创建时间，ISO 字符串
└── message
    ├── role: "user"
    ├── content: "20 元以内。"
    └── timestamp: Message 自己的时间戳
```

**外层 Entry 的时间戳与内层 Message 的时间戳是两个字段。** 外层用于会话记录，内层属于消息数据，不能因为字段同名就当成同一个值。

另外，源码的 `generateId()` 通常取 `randomUUID().slice(0, 8)`，并检查是否与已有 Entry 冲突。Session 自身的 ID 则由 `createSessionId()` 使用 UUID v7 生成。前面的 `L0`、`L1` 是为了讲解父子关系而取的别名。

---

## 48. 创建 Session 时，哪些状态先建立起来

源码位置：[SessionManager 的字段与构造过程](/source/?file=043f6d188e65e3207b.ts#L680)。核心字段是：

```ts
private fileEntries: FileEntry[] = [];
private byId: Map<string, SessionEntry> = new Map();
private leafId: string | null = null;
private flushed: boolean = false;
```

创建新会话时，`newSession()` 生成 Header，然后执行下面这些操作。源码节选：

```ts
this.fileEntries = [header];
this.byId.clear();
this.labelsById.clear();
this.leafId = null;
this.flushed = false;
```

此时 `fileEntries` 已经有 Header，但 `getEntries()` 会过滤 Header，所以对外看到的 Entry 列表仍然为空。

**前面把 L0 当作第一个节点，是省略初始化设置后的教学视图。** 实际通过 `createAgentSession()` 创建新会话时，[sdk.ts](/source/?file=07502145bf1ffa712b.ts#L364) 还会写入初始模型和 thinking level：

```ts
if (model) {
  sessionManager.appendModelChange(model.provider, model.id);
}
sessionManager.appendThinkingLevelChange(thinkingLevel);
```

因此，真实路径可能先是：

```text
M0：model_change
↓
T0：thinking_level_change
↓
L0：用户开始点餐
↓
L1：助手询问预算
```

这时 `L0.parentId` 指向 T0。前面为突出消息之间的关系，才画成 `L0.parentId = null`；追加算法本身始终是同一条规则：**接到当前 leaf 后面。**

---

## 49. 工具结果怎样先进入 Agent，再进入 Session

以前面的 L4 为例：`list_meals` 返回三份午饭的价格。

第一步，Agent 循环把工具执行结果整理成 `ToolResultMessage`。源码节选，位置：[agent-loop.ts](/source/?file=6adbf9ab77a3572a2f.ts#L761)。

```ts
return {
  role: "toolResult",
  toolCallId: finalized.toolCall.id,
  toolName: finalized.toolCall.name,
  content: finalized.result.content,
  details: finalized.result.details,
  isError: finalized.isError,
  timestamp: Date.now(),
};
```

然后发出消息事件：

```ts
async function emitToolResultMessage(
  toolResultMessage: ToolResultMessage,
  emit: AgentEventSink,
): Promise<void> {
  await emit({ type: "message_start", message: toolResultMessage });
  await emit({ type: "message_end", message: toolResultMessage });
}
```

第二步，Agent 的 `processEvents()` 收到 `message_end`，更新自己的状态。源码节选，位置：[agent.ts](/source/?file=3688aa044ebb960834.ts#L520)。

```ts
case "message_end":
  this._state.streamingMessage = undefined;
  this._state.messages.push(event.message);
  break;
```

状态更新后，Agent 才遍历订阅者，把这个事件交给它们。

第三步，AgentSession 的构造函数订阅了这些事件：

```ts
this._unsubscribeAgent = this.agent.subscribe(this._handleAgentEvent);
```

AgentSession 处理到该事件时，再调用 `sessionManager.appendMessage(event.message)`。

完整链路是：

```text
list_meals 执行完成
↓
ToolResultMessage：三份午饭的价格
↓
message_end
↓
Agent.processEvents()：加入 agent.state.messages
↓
AgentSession：排队处理事件
↓
SessionManager.appendMessage()：包装成 L4 Entry
↓
更新索引、leaf，按持久化规则写入文件
```

这里有两种完全不同的关联：

| 字段 | 用途 |
|---|---|
| `message.toolCallId` | 说明这个工具结果回答的是哪一次工具调用 |
| `entry.parentId` | 说明这条会话记录接在哪个 Entry 后面 |

工具调用 ID 不能替代 Entry ID。L3 的工具调用保存在 assistant 消息的 `content` 中，L4 的 `toolCallId` 与该调用对应；L4 外层的 `parentId` 则指向 L3 Entry。

---

## 50. 事件队列在源码中怎样保证处理顺序

源码位置：[AgentSession 的事件入口](/source/?file=24209413646c397dc9.ts#L459)。下面是省略重试准备逻辑后的源码节选：

```ts
this._agentEventQueue = this._agentEventQueue.then(
  () => this._processAgentEvent(event),
  () => this._processAgentEvent(event),
);

this._agentEventQueue.catch(() => {});
```

`_agentEventQueue` 初始是 `Promise.resolve()`。每次收到事件，都把本次处理接到上一项后面。

因此，即使 `_processAgentEvent()` 中有等待扩展回调的 `await`，后面的事件也不会越过前面的事件：

```text
处理 L3 的 message_end
↓
appendMessage(L3)，leaf = L3
↓
处理 L4 的 message_end
↓
appendMessage(L4)，leaf = L4
↓
处理 L5 的 message_end
```

`.then()` 的两个回调分别处理上一项成功和失败的情况，让后续事件仍有机会继续处理；它不表示失败的那条记录已经成功保存。

真正保存普通消息的条件，在 [_processAgentEvent()](/source/?file=24209413646c397dc9.ts#L508) 中是：

```ts
// 源码节选：位于 event.type === "message_end" 的分支内
if (
  event.message.role === "user" ||
  event.message.role === "assistant" ||
  event.message.role === "toolResult"
) {
  this.sessionManager.appendMessage(event.message);
}
```

所以普通消息在 **完成时**保存为 Entry；流式生成过程中的 `message_update` 不会每来一个片段就新增一条聊天 Entry。扩展消息、压缩摘要等还有各自的保存入口。

---

## 51. append：parentId、byId、leafId 在哪几行更新

源码位置：[appendMessage() 与 _appendEntry()](/source/?file=043f6d188e65e3207b.ts#L846)。

```ts
appendMessage(message: Message | CustomMessage | BashExecutionMessage): string {
  const entry: SessionMessageEntry = {
    type: "message",
    id: generateId(this.byId),
    parentId: this.leafId,
    timestamp: new Date().toISOString(),
    message,
  };
  this._appendEntry(entry);
  return entry.id;
}

private _appendEntry(entry: SessionEntry): void {
  this.fileEntries.push(entry);
  this.byId.set(entry.id, entry);
  this.leafId = entry.id;
  this._persist(entry);
}
```

这两段分别负责两件事：

1. `appendMessage()` 用**旧 leafId**设置新节点的 `parentId`。
2. `_appendEntry()` 把节点加入记录和索引，再把 leaf 移到**新节点**。

例如保存“20 元以内”时：

```text
调用前：leafId = L1
↓
创建 L2：parentId = L1
↓
fileEntries.push(L2)
byId.set(L2.id, L2)
leafId = L2.id
↓
尝试持久化 L2
```

`appendThinkingLevelChange()`、`appendModelChange()`、`appendCompaction()` 也采用类似结构，最终调用同一个 `_appendEntry()`。因此这些非聊天记录同样参与父子链。

---

## 52. persist：为什么第一条用户消息不一定立即出现在文件里

源码位置：[_persist()](/source/?file=043f6d188e65e3207b.ts#L825)。下面保留实际控制流程，省略注释：

```ts
_persist(entry: SessionEntry): void {
  if (!this.persist || !this.sessionFile) return;

  const hasAssistant = this.fileEntries.some(
    (e) => e.type === "message" && e.message.role === "assistant",
  );
  if (!hasAssistant) {
    this.flushed = false;
    return;
  }

  if (!this.flushed) {
    for (const e of this.fileEntries) {
      appendFileSync(this.sessionFile, `${JSON.stringify(e)}\n`);
    }
    this.flushed = true;
  } else {
    appendFileSync(this.sessionFile, `${JSON.stringify(entry)}\n`);
  }
}
```

点餐例子中，新会话的第一次写入过程是：

| 时刻 | 内存状态 | 文件写入 |
|---|---|---|
| 创建 Session | 已有 Header，SDK 还可能追加初始设置 | 尚未因这些记录创建文件 |
| 收到 L0 用户请求 | L0 已进 `fileEntries` 和 `byId`，leaf 已更新 | 没有 assistant 消息，暂缓写入 |
| 收到 L1 助手询问预算 | L1 已追加 | 首次把 Header、设置和已有消息一起写入 |
| 后续收到 L2～L7 | 逐条追加 | 每次追加一行 JSON |

因此，“已经在 SessionManager 内存中”与“已经写进 JSONL 文件”要分开理解。`SessionManager.inMemory()` 则直接关闭文件持久化。

文件里的树关系仍然来自每行的 `parentId`，而不是文本行号；Header 也不会进入 `byId`。

<a id="session-jsonl-example"></a>

### 52.1 磁盘上的 JSONL 文件实际长什么样

下面按源码字段构造一个点餐会话文件：先完成 20 元方案并压缩为 C1，再回到 L1，输入新的 30 元预算 B0。

文件名示例：

```text
2026-10-26T04-00-00-000Z_019fff3f-7200-7000-8000-000000000001.jsonl
```

为便于与前文对照，Entry ID 使用 M0、T0、L0～L7、C1、B0；真实 Entry ID 通常是生成的 8 位十六进制字符串。`provider-a`、`model-a` 是教学标识，`usage` 中的数值统一用 0 占位，`tokensBefore = 1000` 是假设值。

**文件正文如下：每一行都是一个完整 JSON 对象，没有外层数组，也不在行与行之间加逗号。** 编辑器开启自动换行后，一条很长的记录可能显示成多行，但磁盘里仍是一条 JSONL 记录。

```jsonl
{"type":"session","version":3,"id":"019fff3f-7200-7000-8000-000000000001","timestamp":"2026-10-26T04:00:00.000Z","cwd":"E:\\lunch-agent"}
{"type":"model_change","id":"M0","parentId":null,"timestamp":"2026-10-26T04:00:00.000Z","provider":"provider-a","modelId":"model-a"}
{"type":"thinking_level_change","id":"T0","parentId":"M0","timestamp":"2026-10-26T04:00:01.000Z","thinkingLevel":"high"}
{"type":"message","id":"L0","parentId":"T0","timestamp":"2026-10-26T04:00:02.000Z","message":{"role":"user","content":"帮我选一份不辣的午饭。先给方案，不要下单。","timestamp":1792987202000}}
{"type":"message","id":"L1","parentId":"L0","timestamp":"2026-10-26T04:00:03.000Z","message":{"role":"assistant","content":[{"type":"text","text":"你的预算是多少？"}],"api":"openai-completions","provider":"provider-a","model":"model-a","usage":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"totalTokens":0,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}},"stopReason":"stop","timestamp":1792987203000}}
{"type":"message","id":"L2","parentId":"L1","timestamp":"2026-10-26T04:00:04.000Z","message":{"role":"user","content":"20 元以内。","timestamp":1792987204000}}
{"type":"message","id":"L3","parentId":"L2","timestamp":"2026-10-26T04:00:05.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"call_meals","name":"list_meals","arguments":{}}],"api":"openai-completions","provider":"provider-a","model":"model-a","usage":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"totalTokens":0,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}},"stopReason":"toolUse","timestamp":1792987205000}}
{"type":"message","id":"L4","parentId":"L3","timestamp":"2026-10-26T04:00:06.000Z","message":{"role":"toolResult","content":[{"type":"text","text":"牛肉面售价 30 元，鸡腿饭售价 20 元，蛋炒饭售价 10 元，三份都不辣。"}],"toolCallId":"call_meals","toolName":"list_meals","isError":false,"timestamp":1792987206000}}
{"type":"message","id":"L5","parentId":"L4","timestamp":"2026-10-26T04:00:07.000Z","message":{"role":"assistant","content":[{"type":"toolCall","id":"call_stock","name":"get_stock","arguments":{"meals":["鸡腿饭","蛋炒饭"]}}],"api":"openai-completions","provider":"provider-a","model":"model-a","usage":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"totalTokens":0,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}},"stopReason":"toolUse","timestamp":1792987207000}}
{"type":"message","id":"L6","parentId":"L5","timestamp":"2026-10-26T04:00:08.000Z","message":{"role":"toolResult","content":[{"type":"text","text":"鸡腿饭售罄，蛋炒饭有货。"}],"toolCallId":"call_stock","toolName":"get_stock","isError":false,"timestamp":1792987208000}}
{"type":"message","id":"L7","parentId":"L6","timestamp":"2026-10-26T04:00:09.000Z","message":{"role":"assistant","content":[{"type":"text","text":"建议蛋炒饭；尚未下单。"}],"api":"openai-completions","provider":"provider-a","model":"model-a","usage":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"totalTokens":0,"cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}},"stopReason":"stop","timestamp":1792987209000}}
{"type":"compaction","id":"C1","parentId":"L7","timestamp":"2026-10-26T04:00:10.000Z","summary":"选一份不辣的午饭，先给方案，不要下单。预算 20 元以内。已查价格：牛肉面 30 元，鸡腿饭 20 元，蛋炒饭 10 元，均不辣。牛肉面超预算，接下来查询鸡腿饭、蛋炒饭库存。","firstKeptEntryId":"L5","tokensBefore":1000}
{"type":"message","id":"B0","parentId":"L1","timestamp":"2026-10-26T04:00:11.000Z","message":{"role":"user","content":"预算改成 30 元以内，其他要求不变。","timestamp":1792987211000}}
```

把上面 13 行与会话结构对应起来：

| 文件行号 | 记录 | 作用 |
|---|---|---|
| 1 | Header，`type = "session"` | 保存会话 ID、格式版本、创建时间和 cwd；不是 Entry |
| 2～3 | M0、T0 | 保存模型和 thinking level 设置 |
| 4～5 | L0、L1 | 两条分支共享的点餐要求与预算询问 |
| 6～11 | L2～L7 | 20 元预算分支的用户输入、工具调用、工具结果和建议 |
| 12 | C1，`type = "compaction"` | 保存摘要、保留原文起点 L5 和压缩前 token 数 |
| 13 | B0 | 新的 30 元预算；虽然最后写入，`parentId` 指向 L1 |

从文件里读出的树是：

```text
M0 → T0 → L0 → L1
                ├── L2 → L3 → L4 → L5 → L6 → L7 → C1
                └── B0
```

尤其看最后一行 B0，单独展开后是：

```json
{
  "type": "message",
  "id": "B0",
  "parentId": "L1",
  "timestamp": "2026-10-26T04:00:11.000Z",
  "message": {
    "role": "user",
    "content": "预算改成 30 元以内，其他要求不变。",
    "timestamp": 1792987211000
  }
}
```

外层的 `timestamp` 是 Entry 的 ISO 时间字符串，内层 `message.timestamp` 是消息的 Unix 毫秒时间戳。外层的 `parentId = "L1"` 决定树上的位置；它不会因为文件上一行是 C1，就自动接到 C1 后面。

加载这个文件时，`_buildIndex()` 跳过第 1 行 Header，把其余 12 条 Entry 放入 `byId`，并在每一步更新 leaf。读到最后得到：

```text
leafId = B0

沿 parentId 回溯：B0 ← L1 ← L0 ← T0 ← M0

当前路径：[M0, T0, L0, L1, B0]
```

所以，即使文件中还保存着 L2～L7 和 C1，`buildSessionContext()` 也只从当前路径恢复消息与设置：消息是 L0、L1、B0；模型为 `provider-a / model-a`，thinking level 为 `high`。C1 不在当前路径上，其摘要不会自动加入。

如果文件停在第 12 行 C1，没有追加 B0，重新加载才会得到 `leafId = C1`，并按压缩规则恢复“摘要 + L5～L7”。

**JSONL 持久化的是 Header 和一条条 Entry；`byId`、`leafId` 以及 Agent 的消息列表，都由这些记录重建。**

---

## 53. getBranch：怎样从 B0 找回 L0、L1

源码位置：[getBranch()](/source/?file=043f6d188e65e3207b.ts#L1068)。

```ts
getBranch(fromId?: string): SessionEntry[] {
  const path: SessionEntry[] = [];
  const startId = fromId ?? this.leafId;
  let current = startId ? this.byId.get(startId) : undefined;
  while (current) {
    path.unshift(current);
    current = current.parentId ? this.byId.get(current.parentId) : undefined;
  }
  return path;
}
```

当 `leafId = B0` 时，每一步是：

| 当前节点 | 放入数组后 | 下一次查找 |
|---|---|---|
| B0 | `[B0]` | `byId.get(L1)` |
| L1 | `[L1, B0]` | `byId.get(L0)` |
| L0 | `[L0, L1, B0]` | `parentId = null`，结束 |

`unshift()` 把元素放到数组头部，所以虽然回溯顺序是 B0 → L1 → L0，返回顺序已经是 L0 → L1 → B0。

**这个函数没有遍历 L2～L7，也没有判断它们的消息内容。** 它只是沿父指针走，因此兄弟分支自然不会混进结果。

如果真实会话中还有 M0、T0 等祖先记录，它们也会出现在返回路径里。`getBranch()` 返回的是 Entry 路径，还没有把设置记录过滤成纯消息。

---

## 54. buildSessionContext：怎样把路径变成 Agent 的历史

SessionManager 的方法只是一个入口。源码节选：

```ts
buildSessionContext(): SessionContext {
  return buildSessionContext(this.getEntries(), this.leafId, this.byId);
}
```

真正的构建函数位于同文件的 [buildSessionContext()](/source/?file=043f6d188e65e3207b.ts#L322)。它自己沿 `parentId` 收集路径，并不是直接调用 `getBranch()`；两处使用了相同的回溯思路。

### 54.1 先区分 null 与没有传 leafId

```ts
// 源码节选
if (leafId === null) {
  return { messages: [], thinkingLevel: "off", model: null };
}
if (leafId) {
  leaf = byId.get(leafId);
}
if (!leaf) {
  leaf = entries[entries.length - 1];
}
```

显式传 `null` 表示“当前位置在第一条 Entry 之前”，必须返回空消息。没有提供 leaf 时，函数才按默认逻辑回退到最后一条 Entry；代码中指定 ID 未找到时也会走这个回退分支。

### 54.2 沿路径恢复设置，找到最近的压缩记录

源码节选：

```ts
for (const entry of path) {
  if (entry.type === "thinking_level_change") {
    thinkingLevel = entry.thinkingLevel;
  } else if (entry.type === "model_change") {
    model = { provider: entry.provider, modelId: entry.modelId };
  } else if (entry.type === "message" && entry.message.role === "assistant") {
    model = { provider: entry.message.provider, modelId: entry.message.model };
  } else if (entry.type === "compaction") {
    compaction = entry;
  }
}
```

路径已经按旧到新排列，因此后面的值覆盖前面的值。模型信息既可以来自显式切换记录，也可以来自助手消息记录的实际模型。

注意：这些信息取自**当前路径**。兄弟分支里切换过模型，并不意味着当前分支的恢复结果也要采用那个模型。

### 54.3 把能进入上下文的 Entry 转成 Message

源码节选：

```ts
const appendMessage = (entry: SessionEntry) => {
  if (entry.type === "message") {
    messages.push(entry.message);
  } else if (entry.type === "custom_message") {
    messages.push(
      createCustomMessage(
        entry.customType, entry.content, entry.display,
        entry.details, entry.timestamp,
      ),
    );
  } else if (entry.type === "branch_summary" && entry.summary) {
    messages.push(
      createBranchSummaryMessage(entry.summary, entry.fromId, entry.timestamp),
    );
  }
};
```

没有压缩时，就对路径中的每条 Entry 调用这个局部函数。模型设置、标签、普通 `custom` 记录不会作为聊天消息放进去。

点餐分叉后的结果可以表示为：

```text
Entry 路径：[M0, T0, L0, L1, B0]
↓
SessionContext
├── messages：[Message(L0), Message(L1), Message(B0)]
├── model：当前路径解析出的模型信息
└── thinkingLevel：当前路径解析出的 thinking level
```

这里的 `messages` 是 Agent 使用的内部消息历史；后续仍可能经过消息转换和扩展处理，才成为供应商 API 接收的格式。

### 54.4 具体例子：从点餐会话树生成 SessionContext

假设用户已经完成 20 元午饭方案，又回到 L1，把预算改成 30 元以内。会话中还保存了初始模型与 thinking level，完整结构如下：

```text
M0：model_change，provider = "provider-a"，modelId = "model-a"
↓
T0：thinking_level_change，thinkingLevel = "high"
↓
L0：用户：帮我选一份不辣的午饭。先给方案，不要下单。
↓
L1：助手：你的预算是多少？
├── L2：用户：20 元以内。
│    └── L3 → L4 → L5 → L6 → L7：建议蛋炒饭；尚未下单。
└── B0：用户：预算改成 30 元以内，其他要求不变。
     ↑
  leafId
```

这里的 `provider-a`、`model-a` 是教学用标识。假设 L1 的助手消息也记录了这两个值，当前路径上没有 Compaction。

现在执行：

```ts
const sessionContext = sessionManager.buildSessionContext();
```

**第一步：从 B0 回溯，而不是按文件顺序收集全部消息。**

```text
B0.parentId = L1
L1.parentId = L0
L0.parentId = T0
T0.parentId = M0
M0.parentId = null
```

使用 `unshift()` 组装后，得到：

```ts
path = [M0, T0, L0, L1, B0]; // 教学别名，表示对应 Entry 对象
```

L2～L7 虽然还在文件和 `byId` 中，但不属于这条路径，所以后面不会处理它们。

**第二步：扫描 path，解析设置。**

扫描前的初始值是 `model = null`、`thinkingLevel = "off"`、`compaction = null`。

| 扫描到的 Entry | 设置解析结果 |
|---|---|
| M0 | `model = { provider: "provider-a", modelId: "model-a" }` |
| T0 | `thinkingLevel = "high"` |
| L0 | 用户消息，不改变设置 |
| L1 | 从助手消息读取实际 provider、model；本例与 M0 相同 |
| B0 | 用户消息，不改变设置 |

整条路径没有压缩记录，因此 `compaction` 仍为 `null`。

**第三步：再次遍历 path，组装 messages。**

| Entry | `appendMessage(entry)` 的动作 | 当前 messages |
|---|---|---|
| M0 | 模型设置记录，不加入消息列表 | `[]` |
| T0 | thinking level 设置记录，不加入消息列表 | `[]` |
| L0 | 加入 `L0.message` | `[L0.message]` |
| L1 | 加入 `L1.message` | `[L0.message, L1.message]` |
| B0 | 加入 `B0.message` | `[L0.message, L1.message, B0.message]` |

**第四步：返回一个同时包含消息与设置的 SessionContext。**

下面是返回值的教学展示，省略消息的时间戳、助手消息的 usage 等字段：

```ts
{
  messages: [
    {
      role: "user",
      content: "帮我选一份不辣的午饭。先给方案，不要下单。",
    },
    {
      role: "assistant",
      content: [{ type: "text", text: "你的预算是多少？" }],
      provider: "provider-a",
      model: "model-a",
    },
    {
      role: "user",
      content: "预算改成 30 元以内，其他要求不变。",
    },
  ],
  model: { provider: "provider-a", modelId: "model-a" },
  thinkingLevel: "high",
}
```

注意，`messages` 中放的是 Entry 内部的 Message，没有把外层的 `id`、`parentId` 一起塞进去。设置则单独保存在返回值的 `model` 和 `thinkingLevel` 中。

在导航流程里，调用方随后执行：

```ts
this.agent.state.messages = sessionContext.messages;
```

于是 Agent 的历史里只保留“不辣、不下单、30 元预算”这条路线的对话；这行赋值本身不会把 `sessionContext.model` 和 `thinkingLevel` 也自动应用到 Agent。

---

## 55. 有 Compaction 时，怎样接上第 08 节

同一个 `buildSessionContext()` 在发现当前路径上的压缩记录后，会按三段组装消息：

```text
① 压缩摘要消息
② 压缩记录之前，从 firstKeptEntryId 起保留的消息
③ 压缩记录之后新增的消息
```

以下是根据源码整理的教学简化，`appendMessage()` 就是上一节的局部函数：

```ts
messages.push(
  createCompactionSummaryMessage(
    compaction.summary,
    compaction.tokensBefore,
    compaction.timestamp,
  ),
);

const compactionIdx = path.findIndex(e => e.id === compaction.id);
let foundFirstKept = false;

for (let i = 0; i < compactionIdx; i++) {
  const entry = path[i];
  if (entry.id === compaction.firstKeptEntryId) {
    foundFirstKept = true;
  }
  if (foundFirstKept) appendMessage(entry);
}

for (let i = compactionIdx + 1; i < path.length; i++) {
  appendMessage(path[i]);
}
```

沿用第 08 节：

```text
路径：L0 → L1 → ... → L7 → C1
C1.summary = S1
C1.firstKeptEntryId = L5
↓
messages = [S1 对应的摘要消息, Message(L5), Message(L6), Message(L7)]
```

保存 C1 并没有把 L0～L4 从会话树中删除。改变的是构建给 Agent 的消息列表。

而 `AgentSession` 在压缩完成后，确实会把构建结果写回 Agent。源码节选，位置：[agent-session.ts](/source/?file=24209413646c397dc9.ts#L1738)。

```ts
this.sessionManager.appendCompaction(
  summary, firstKeptEntryId, tokensBefore, details, fromExtension,
);
const newEntries = this.sessionManager.getEntries();
const sessionContext = this.sessionManager.buildSessionContext();
this.agent.state.messages = sessionContext.messages;
```

所以第 08 节的压缩和本节的分支恢复，最终都汇合到同一个入口：**构建 SessionContext，再更新 Agent 的 messages。**

### 55.1 具体例子：压缩后继续点餐，怎样重建 messages

上一节的例子没有压缩记录。现在仍用点餐任务，假设第一轮已经完成：用户预算 20 元，工具查到鸡腿饭售罄、蛋炒饭有货，助手建议蛋炒饭，但没有下单。

随后系统追加 C1，把 L0～L4 的信息整理成摘要 S1，并从 L5 起保留原文。为了突出压缩处理，下面省略模型与 thinking level 的设置节点。

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7 → C1

C1.parentId = L7
C1.summary = S1
C1.firstKeptEntryId = L5
```

S1 的内容可以简化展示为：

```text
目标：为用户选择一份不辣的午饭，先给方案，不要下单。
预算：20 元以内。
已查询价格：牛肉面 30 元、鸡腿饭 20 元、蛋炒饭 10 元，均不辣。
筛选依据：牛肉面超预算，接下来查询鸡腿饭、蛋炒饭的库存。
```

注意，这份摘要对应 L0～L4，里面不提前写入 L6 的库存结果和 L7 的最终建议；这些信息仍保留在原文里。实际第 08 节的 S1 由历史摘要和 Turn Prefix 摘要组成，这里只展示合在一起的关键信息。

现在用户又补充一条 L8：

> 再比较一下鸡腿饭和蛋炒饭，顺便看看它们是否送汤，还是不要下单。

因为追加前 leaf 是 C1，所以 `L8.parentId = C1`。此时：

```text
L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7 → C1 → L8
                                                ↑
                                             leafId
```

执行：

```ts
const sessionContext = sessionManager.buildSessionContext();
```

**第一步：回溯当前路径，找到 C1。**

```ts
// 教学别名：数组元素都是对应的 Entry 对象
path = [L0, L1, L2, L3, L4, L5, L6, L7, C1, L8];
compaction = C1;
compactionIdx = 8; // 从 0 开始计数
```

这时 `path` 仍包含 L0～L4。真正把它们排除在消息列表之外，是接下来的组装过程。

**第二步：先生成一条摘要消息，放在 messages 最前面。**

源码调用是：

```ts
messages.push(
  createCompactionSummaryMessage(C1.summary, C1.tokensBefore, C1.timestamp),
);
```

根据 [messages.ts](/source/?file=2d4c32a97bc465b1f2.ts) 的实现，加入的是下面这种内部消息：

```ts
{
  role: "compactionSummary",
  summary: S1,
  tokensBefore: C1.tokensBefore,
  timestamp: new Date(C1.timestamp).getTime(),
}
```

它不是 C1 Entry 本身，也不是一条普通助手回复。下面把它简写为 `summaryMessage`。

**第三步：扫描 C1 之前的 Entry，从 L5 开始加入保留原文。**

循环条件是 `i < compactionIdx`，所以这一步只扫描 L0～L7：

| 扫描位置 | `foundFirstKept` | 对 messages 的处理 |
|---|---|---|
| L0～L4 | `false` | 跳过，不加入原始消息 |
| L5 | 命中 `C1.firstKeptEntryId`，变成 `true` | 加入 L5 的工具调用消息：查询两份午饭的库存 |
| L6 | `true` | 加入工具结果：鸡腿饭售罄，蛋炒饭有货 |
| L7 | `true` | 加入助手回复：建议蛋炒饭；尚未下单 |

这一步结束后：

```ts
messages = [summaryMessage, L5.message, L6.message, L7.message];
```

L5 的工具调用和 L6 的工具结果仍然保留原有的对应关系。

**第四步：扫描 C1 之后的 Entry，加入新增消息 L8。**

第二个循环从 `compactionIdx + 1` 开始，本例就是从下标 9 开始：

```ts
appendMessage(L8);
```

C1 不作为普通消息再追加一次，因为它已经通过 `summaryMessage` 参与了上下文。

**第五步：得到最终消息列表，并交回 Agent。**

```ts
sessionContext.messages = [
  summaryMessage, // S1：目标、预算、价格和筛选依据
  L5.message,    // assistant：调用 get_stock
  L6.message,    // toolResult：鸡腿饭售罄，蛋炒饭有货
  L7.message,    // assistant：建议蛋炒饭；尚未下单
  L8.message,    // user：继续比较送汤情况，仍不要下单
];

// 调用方需要更新 Agent 历史时，使用这个结果
this.agent.state.messages = sessionContext.messages;
```

因此，Agent 可以从摘要读到“不辣、20 元以内、不下单”，从保留原文读到库存和原建议，再从 L8 得到新的送汤查询要求。

如果刚压缩完成、还没有 L8，最终列表就只有 `summaryMessage + L5.message + L6.message + L7.message`。如果以后又产生 L9～L11，它们会加入第三段；模型与 thinking level 仍按第 54 节的规则单独解析。

这里展示的是 Agent 内部历史。后续 `convertToLlm()` 会把 `compactionSummary` 转换成带摘要说明的 `user` 消息，再交给模型调用流程。

---

## 56. branch 与 navigateTree：只改 leaf 和完整导航的区别

低层的 `branch()` 很短。源码位置：[SessionManager.branch()](/source/?file=043f6d188e65e3207b.ts#L1163)。

```ts
branch(branchFromId: string): void {
  if (!this.byId.has(branchFromId)) {
    throw new Error(`Entry ${branchFromId} not found`);
  }
  this.leafId = branchFromId;
}
```

它只检查节点存在，然后移动指针；没有删记录，也没有更新 Agent。

高层 [AgentSession.navigateTree()](/source/?file=24209413646c397dc9.ts#L2747) 还要处理目标类型、可选摘要、扩展事件，以及 Agent 的上下文。先看“不生成摘要、不加标签”的教学简化主流程：

```ts
const targetEntry = this.sessionManager.getEntry(targetId);
if (!targetEntry) throw new Error(`Entry ${targetId} not found`);

let newLeafId: string | null;
let editorText: string | undefined;

if (targetEntry.type === "message" && targetEntry.message.role === "user") {
  newLeafId = targetEntry.parentId;
  editorText = this._extractUserMessageText(targetEntry.message.content);
} else {
  newLeafId = targetId;
}

if (newLeafId === null) {
  this.sessionManager.resetLeaf();
} else {
  this.sessionManager.branch(newLeafId);
}

const sessionContext = this.sessionManager.buildSessionContext();
this.agent.state.messages = sessionContext.messages;

return { editorText, cancelled: false };
```

实际代码还单独处理 `custom_message`，并在前后发送扩展事件；上面的片段专门保留点餐例子所需的普通消息路径。

对应两种点击方式：

| 用户选择 | 新 leaf | 返回给编辑框的文本 | Agent 历史 |
|---|---|---|---|
| L1：助手询问预算 | L1 | 无 | L0、L1 |
| L2：用户说“20 元以内” | L1，即 L2 的 parent | “20 元以内” | L0、L1 |

接着提交“预算改成 30 元以内”，普通消息保存流程会创建 B0，且 `B0.parentId = L1`。

**修改旧用户输入并没有调用“覆盖 L2”的方法。** 它复用了“导航到父节点 + 追加新消息”的两套机制。

---

## 57. 可选 Branch Summary 怎样接到新路径

如果用户选择总结离开的分支，`navigateTree()` 会先通过 `collectEntriesForBranchSummary()` 找公共祖先及待总结记录，再调用摘要器或采用扩展提供的摘要。

生成摘要以后，它走的是另外一个分支。源码节选：

```ts
const summaryId = this.sessionManager.branchWithSummary(
  newLeafId,
  summaryText,
  summaryDetails,
  fromExtension,
);
```

`branchWithSummary()` 先把 leaf 移到目标位置，再追加一条 `branch_summary` Entry。因此从 L7 回到 L1 并生成摘要时，路径会变成：

```text
L0 → L1
      ├── L2 → ... → L7
      └── BS1：离开分支的摘要
           └── B0：30 元以内
```

这时 `B0.parentId = BS1`，不再直接等于 L1。后续 `buildSessionContext()` 会把 BS1 转成内部摘要消息，让 Agent 可以读取摘要带来的信息。

所以前面“不继承兄弟分支的工具结果”对应的是**不生成分支摘要的例子**。启用摘要后，旧分支的部分信息可以通过摘要显式带入新路径。

---

## 58. 重新打开文件：怎样重建 byId 和 leafId

恢复入口是 [SessionManager.open()](/source/?file=043f6d188e65e3207b.ts#L1325)，构造过程会调用 `setSessionFile()`。

正常文件的加载流程可以概括成：

```text
open(path)
↓
读取 Header，确定 cwd 与 sessionDir
↓
构造 SessionManager
↓
setSessionFile(path)
↓
loadEntriesFromFile() 读取 JSONL
↓
必要时迁移旧格式
↓
_buildIndex()
```

`loadEntriesFromFile()` 按行 `JSON.parse()`，跳过无法解析的行，并检查第一条记录是否是带字符串 ID 的 Session Header。

下面是 `_buildIndex()` 的源码节选，省略标签索引的重建分支：

```ts
private _buildIndex(): void {
  this.byId.clear();
  this.labelsById.clear();
  this.labelTimestampsById.clear();
  this.leafId = null;
  for (const entry of this.fileEntries) {
    if (entry.type === "session") continue;
    this.byId.set(entry.id, entry);
    this.leafId = entry.id;
    // 这里还会恢复 label 相关索引
  }
}
```

每读到一个非 Header 的 Entry，leaf 都更新一次；最终停在文件中最后一条 Entry。

因此，文件末尾是 B0 时，恢复得到 `leafId = B0`，随后沿 B0 的 `parentId` 找到 L1、L0。

可以对照[第 52.1 节的 JSONL 文件示例](#session-jsonl-example)，逐行查看 Header 怎样被跳过、Entry 怎样进入索引，以及最后一行 B0 怎样决定恢复的 leaf。

### 一个恢复边界：只导航、不追加，会发生什么

`branch(L1)` 只改内存中的 `leafId`，没有追加“移动光标”记录。

因此：

```text
文件最后一条仍然是 L7
↓
运行中导航到 L1，但没有追加消息、摘要或标签
↓
关闭后重新加载
↓
_buildIndex() 恢复的 leafId 仍是 L7
```

而前面的完整例子已经追加了 B0，所以文件最后一条变成 B0，恢复后才能从新预算分支继续。

**当前实现恢复的是“最后写入的 Entry 所在路径”，不会额外从文件头读取一个持久化的 leafId。**

---

## 59. 从文件恢复完，Agent 是怎样得到这三条消息的

SessionManager 只负责恢复记录。把记录交给 Agent，还需要 [createAgentSession()](/source/?file=07502145bf1ffa712b.ts#L176)。

源码节选：

```ts
const existingSession = sessionManager.buildSessionContext();
const hasExistingSession = existingSession.messages.length > 0;
const hasThinkingEntry = sessionManager
  .getBranch()
  .some((entry) => entry.type === "thinking_level_change");
```

随后工厂函数选择模型、thinking level，创建 Agent，最后恢复消息：

```ts
if (hasExistingSession) {
  agent.state.messages = existingSession.messages;
  if (!hasThinkingEntry) {
    sessionManager.appendThinkingLevelChange(thinkingLevel);
  }
}
```

因此恢复后的点餐 Agent 得到的是：

```text
“选一份不辣的午饭，先给方案，不要下单”
“你的预算是多少？”
“预算改成 30 元以内，其他要求不变”
```

模型与 thinking level 的选择还带有运行条件：显式传入的选项优先；否则尝试采用恢复信息，结合模型是否可用、认证配置和设置默认值处理。thinking level 还会受模型能力限制。

`buildSessionContext()` 返回恢复信息，并不代表它自己已经调用了 `agent.setModel()`。设置运行中的模型，以及替换消息列表，是需要分别完成的动作；前面展示的 `navigateTree()` 更新片段只替换了消息历史。

如果要从指定 JSONL 创建会话，SDK 用法可以写成下面这样。这里 `savedSessionPath` 代表已有文件的路径；继续执行模型任务仍需相应模型配置和点餐工具：

```ts
import { createAgentSession, SessionManager } from "@mariozechner/pi-coding-agent";

const manager = SessionManager.open(savedSessionPath);
const { session } = await createAgentSession({ sessionManager: manager });

// 此时 session.agent.state.messages 已由当前分支恢复。
```

---

## 60. Fork 的代码为什么要新建文件，而不是只改 leaf

源码入口在 [AgentSessionRuntime.fork()](/source/?file=70034fc47cc255a0a5.ts#L220)。它先确定复制路径的终点：

| 参数 | 行为 | 以 L2 为目标时 |
|---|---|---|
| 默认 `position: "before"` | 要求选择用户消息；复制到它的父节点，并返回原文用于编辑 | 新会话先保留到 L1；“20 元以内”交给编辑框 |
| `position: "at"` | 复制到选中的 Entry，包含该 Entry | 新会话包含 L2 |

持久化模式下，复制部分的源码节选是：

```ts
const sourceManager = SessionManager.open(currentSessionFile, sessionDir);
const forkedSessionPath = sourceManager.createBranchedSession(targetLeafId);
if (!forkedSessionPath) {
  throw new Error("Failed to create forked session");
}
const sessionManager = SessionManager.open(forkedSessionPath, sessionDir);
```

低层的 [createBranchedSession()](/source/?file=043f6d188e65e3207b.ts#L1211) 做这些事：

1. `getBranch(targetLeafId)` 取出要复制的路径。
2. 创建新的 Session ID、文件名和 Header，记录 `parentSession`。
3. 复制路径中的记录，并根据已解析的标签状态重建标签记录。
4. 为新内容重建索引，按是否已有助手消息决定立即写文件还是延迟写入。

`createBranchedSession()` 会让接收调用的 manager 指向新会话。高层先另开一个 `sourceManager` 来执行复制，因此不会直接拿当前运行中的 manager 改写成新档案。

复制成功后，Runtime 才替换运行环境、重新绑定会话。旧文件中 L2～L7 的历史仍然存在，新文件则只有选中路径及所需记录。

如果目标在第一条记录之前，高层会直接建立空的新会话；如果使用内存模式，也就没有“新建 JSONL 文件”这一步。

---

## 61. switchSession、newSession、reload 在实现上怎样区分

[AgentSessionRuntime.switchSession()](/source/?file=70034fc47cc255a0a5.ts#L161) 的正常主流程，源码节选如下。前面的扩展取消检查在这里省略：

```ts
const previousSessionFile = this.session.sessionFile;
const sessionManager = SessionManager.open(sessionPath, undefined, options?.cwdOverride);
assertSessionCwdExists(sessionManager, this.cwd);
await this.teardownCurrent("resume", sessionManager.getSessionFile());
this.apply(
  await this.createRuntime({
    cwd: sessionManager.getCwd(),
    agentDir: this.services.agentDir,
    sessionManager,
    sessionStartEvent: { type: "session_start", reason: "resume", previousSessionFile },
  }),
);
await this.finishSessionReplacement(options?.withSession);
```

其中：

- `teardownCurrent()` 发送关闭事件并释放旧 AgentSession。
- `createRuntime()` 为目标工作目录和 SessionManager 创建新的运行环境。
- `apply()` 替换持有的 Session、services 等状态。
- `finishSessionReplacement()` 调用重新绑定逻辑和可选回调，让界面或调用方接上新会话。

`newSession()` 使用类似替换流程，但起点是 `SessionManager.create()`，而不是打开已有文件。

`reload()` 的入口仍在 [AgentSession.reload()](/source/?file=24209413646c397dc9.ts#L2444)，主要重新加载配置和运行资源。三者与导航可以这样对应：

| 操作 | SessionManager / 会话档案 | Agent 消息从哪里来 |
|---|---|---|
| `navigateTree()` | 同一份档案，移动 leaf，可能追加摘要或标签 | 重建当前路径后替换 |
| `switchSession()` | 打开另一份已有档案，重建运行环境 | 从目标档案的路径恢复 |
| `newSession()` | 建立新档案，重建运行环境 | 从新会话状态开始 |
| `reload()` | 沿用当前档案 | 保留会话历史，重建相关运行资源 |

---

## 62. 把点餐例子与源码调用连成一条线

现在可以把前面所有步骤写成具体调用关系：

```text
用户开始点餐：L0
↓
Agent 循环产生 message_end
↓
Agent.processEvents() 更新 state.messages
↓
AgentSession._handleAgentEvent() 排队
↓
AgentSession._processAgentEvent()
↓
SessionManager.appendMessage()
↓
_appendEntry()：加入 fileEntries / byId，推进 leaf
↓
_persist()：按首次写入或逐行追加规则保存
↓
L1～L7 重复同样过程，完成 20 元午饭方案
```

随后改预算：

```text
navigateTree(L1)，不生成摘要
↓
SessionManager.branch(L1)
↓
buildSessionContext() → L0、L1 的消息
↓
替换 agent.state.messages
↓
用户提交“30 元以内”
↓
普通 message_end 保存流程产生 B0，parentId = L1
↓
旧路线保留，新路线从 B0 继续
```

最后关闭并恢复：

```text
SessionManager.open(JSONL)
↓
setSessionFile() 读取记录、处理格式迁移
↓
_buildIndex() 恢复 byId，leaf 停在最后写入的 B0
↓
createAgentSession() 调用 buildSessionContext()
↓
只恢复 L0 → L1 → B0 这条路径的消息，并解析设置
↓
创建 Agent，装入恢复消息
↓
Agent 按 30 元预算继续查询午饭
```

读代码时可以始终抓住两处：

> **保存入口：`message_end → appendMessage() → _appendEntry()`。**

> **历史重建入口：`leafId → parentId 路径 → buildSessionContext() → agent.state.messages`。**
