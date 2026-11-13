---
title: "15 · 多智能体系统"
description: "openclaw · 会话执行与协作 · 课程讲义"
project: "openclaw"
sourcePath: "OpenClaw/OpenClaw-Course/15_多智能体系统原理完整讲义.md"
originalUrl: "/originals/openclaw/chapter-15.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 15 多智能体系统原理完整讲义：从任务拆分到子会话、并发与结果汇总

> 阅读顺序：先读“课堂主线”的完整父子 prompt、Skill、数据和运行调用链，再读后面的机制补充。
>
> **课堂主线 A～E：完整协作工程、两项 spawn 参数、核心实现、时序和断点。**  
> **第一、二部分：补充多会话、任务图、生命周期与调度算法。**  
> **第三部分：继续沿 OpenClaw 的 spawn、registry、announce 源码展开。**
>
> 最核心的一句话是：
>
> **模型提出分工并理解结果；程序创建独立会话、执行调度、记录父子关系并回传完成事件。**

第 12 讲说明了联网检索和网页证据怎样参与单会话回答，第 13、14 讲接着走完一个 AgentSession 从装配到执行、记录与恢复的过程。现在把任务拆给多个助手，继续追踪独立会话怎样创建、怎样传递任务，以及结果怎样回到父会话。第 10、11 讲介绍的项目资源与长期记忆，也要按各个会话的宿主配置和作用域接入。

文中的 `get_prices`、`get_stock` 等午饭工具需要由应用提供。

---

## 课堂主线：完整协作例子，再沿着调用栈读实现

本讲在 OpenClaw 宿主中演示协作。`sessions_spawn`、父子登记表、Lane 和完成回传来自 OpenClaw；独立 Pi 的 `AgentSession` 本身不会仅凭一份 Skill 自动拥有这些能力。

下面把“用户输入什么”“父助手读取什么”“给子助手传了什么”“程序在哪里启动子任务”全部展开。例子中的协作是课程内容，不会在编写本讲义时实际启动子助手。

### A. 完整例子：一份 Skill 如何引出两项子任务

#### A.1 Workspace、规则和数据文件

假设 Workspace 绝对路径是 `/work/lunch-workspace`：

```text
lunch-workspace/
├── AGENTS.md
├── SOUL.md
├── USER.md
├── TOOLS.md
├── skills/
│   └── choose-lunch-team/
│       └── SKILL.md
└── data/
    ├── prices.json
    └── stock.json
```

为使整条演示不依赖实际餐馆接口，子助手通过 OpenClaw 本次可用的文件读取工具读取固定数据。原生文件读取工具常见名为 `read`，以本次活跃工具列表为准。

`AGENTS.md` 完整示例：

```markdown
# 午饭协作规则
用户明确要求分工查询午饭时，先读取 choose-lunch-team 技能。
两项查询分别处理价格口味和库存，主助手负责最终比较。
传给子助手的任务必须包含候选 ID、数据路径、输出字段和禁止事项。
子助手只查询、只返回结果，不改文件、不下单、不再派生任务。
主助手收到两项结果后才给最终推荐；失败项必须说明。
```

其余 Bootstrap 文件的完整示例：

```markdown
# SOUL.md
你负责核实材料并给出清楚的午饭建议，使用简短中文。
```

```markdown
# USER.md
用户希望在最终方案中看到价格、口味、库存和是否下单。
本次选择条件以用户当前输入为准。
```

```markdown
# TOOLS.md
教学价格文件：/work/lunch-workspace/data/prices.json。
教学库存文件：/work/lunch-workspace/data/stock.json。
这些路径只提供查询资料，不代表系统已经注册任何自定义菜单工具。
```

`data/prices.json` 完整内容：

```json
[
  { "id": "A", "name": "牛肉面", "price": 18, "spicy": true },
  { "id": "B", "name": "鸡腿饭", "price": 22, "spicy": false },
  { "id": "C", "name": "蛋炒饭", "price": 10, "spicy": false }
]
```

`data/stock.json` 完整内容：

```json
[
  { "id": "A", "stock": 8 },
  { "id": "B", "stock": 6 },
  { "id": "C", "stock": 12 }
]
```

主助手和两项子任务在本例均使用同一 Agent 的 Workspace，且只读取数据。不同部署、目标 Agent 和沙箱配置下，必须先确认子助手可访问这些路径。

#### A.2 完整的协作 Skill

文件：`skills/choose-lunch-team/SKILL.md`。

```markdown
---
name: choose-lunch-team
description: 用户明确要求分工核对午饭价格口味与库存时，拆成两项独立查询，由主助手汇总。
---

# 午饭分工查询

## 前置条件
本次有 sessions_spawn 工具，且子助手能读取指定数据文件。
本教学候选固定为 A 牛肉面、B 鸡腿饭、C 蛋炒饭。

## 执行步骤
1. 记录本次口味、预算和下单约束。
2. 调用 sessions_spawn 创建价格口味任务。
   任务中给出全部候选和 prices.json 的绝对路径。
   要求返回 id、name、price、spicy、source；不筛掉超预算候选。
3. 调用 sessions_spawn 创建库存任务。
   任务中给出全部候选和 stock.json 的绝对路径。
   要求返回 id、stock、source。
4. 两项都用 runtime=subagent、mode=run、cleanup=keep。
5. 受理回执只说明已提交，不是业务结果。
   按宿主的完成通知机制等待，不要频繁轮询。
   当前宿主提供并支持 sessions_yield 时，可调用它让出本轮。
6. 收到两项结果后，以 id 连接记录，过滤口味、预算和库存。
7. 返回符合条件的最低价方案，注明使用教学文件以及未下单。

## 子任务限制
只读指定数据，只返回结果，不修改文件、不下单、不再创建子任务。
文件不可读或字段缺失时返回明确错误，不编造数值。

## 失败处理
有任何一项失败时，不把缺失字段当作正常值；说明缺失并决定是否重试。
```

这是方法说明。真正提供 `sessions_spawn` 的是宿主工具，真正创建子会话的是后面的 `spawnSubagentDirect`。

#### A.3 完整的主用户 prompt

```text
请先读 choose-lunch-team 技能，再分工核对今天的教学午饭数据。
候选是 A 牛肉面、B 鸡腿饭、C 蛋炒饭。
价格口味读 /work/lunch-workspace/data/prices.json，
库存读 /work/lunch-workspace/data/stock.json。
用两个子助手分别查询，最终帮我选不辣、20 元以内、有货的最低价午饭。
只给方案，不要下单；不要修改文件。
```

父助手在第一次请求中看到 Bootstrap 规则、可用技能目录和宿主工具 Schema。它先读取上述 SKILL.md；文件读取结果进入下一次模型请求后，再按 Skill 组织任务。

#### A.4 第一个 sessions_spawn：完整的价格任务参数

```json
{
  "task": "只读查询。候选为 A 牛肉面、B 鸡腿饭、C 蛋炒饭。读取 /work/lunch-workspace/data/prices.json，按候选 ID 返回完整 JSON 数组，每项包含 id、name、price、spicy、source。source 写数据文件路径。不要过滤候选，主助手将按不辣、20 元以内筛选。文件不可读或字段缺失时明确报告。禁止修改文件、下单或再派生任务。",
  "label": "lunch-price",
  "runtime": "subagent",
  "mode": "run",
  "cleanup": "keep",
  "runTimeoutSeconds": 120
}
```

#### A.5 第二个 sessions_spawn：完整的库存任务参数

```json
{
  "task": "只读查询。候选为 A 牛肉面、B 鸡腿饭、C 蛋炒饭。读取 /work/lunch-workspace/data/stock.json，按候选 ID 返回完整 JSON 数组，每项包含 id、stock、source。source 写数据文件路径。stock=0 表示无货，缺失表示未知，不要改成有货。文件不可读或字段缺失时明确报告。禁止修改文件、下单或再派生任务。",
  "label": "lunch-stock",
  "runtime": "subagent",
  "mode": "run",
  "cleanup": "keep",
  "runTimeoutSeconds": 120
}
```

两个调用均不指定 `agentId`，按本地默认规则采用请求者的 Agent 配置，同时创建不同的子 Session。这里需要的是两项独立上下文中的任务，不要求先配置两个不同身份的 Agent。

#### A.6 父助手先拿到什么，子助手最终返回什么

第一项受理回执的教学阅读视图如下，真实结果另有 note 等字段，UUID 与 runId 由宿主生成：

```json
{
  "status": "accepted",
  "childSessionKey": "agent:main:subagent:<uuid-P>",
  "runId": "run-P",
  "mode": "run"
}
```

第二项同理得到另一个子会话和 `run-S`。`<uuid-P>` 是教学占位符，不能拿它当实际会话键调用工具。

价格子助手读取文件后，预期业务结果为：

```json
[
  { "id": "A", "name": "牛肉面", "price": 18, "spicy": true, "source": "/work/lunch-workspace/data/prices.json" },
  { "id": "B", "name": "鸡腿饭", "price": 22, "spicy": false, "source": "/work/lunch-workspace/data/prices.json" },
  { "id": "C", "name": "蛋炒饭", "price": 10, "spicy": false, "source": "/work/lunch-workspace/data/prices.json" }
]
```

库存子助手预期业务结果为：

```json
[
  { "id": "A", "stock": 8, "source": "/work/lunch-workspace/data/stock.json" },
  { "id": "B", "stock": 6, "source": "/work/lunch-workspace/data/stock.json" },
  { "id": "C", "stock": 12, "source": "/work/lunch-workspace/data/stock.json" }
]
```

业务结果通过后续完成通知交回，不是 `sessions_spawn` 的同步返回值。父助手收齐后得到：A 辣，排除；B 超预算，排除；C 10 元、不辣、库存 12，符合要求。

最终回答可以是：“按教学文件，推荐蛋炒饭：10 元、不辣、有货，符合 20 元预算。尚未下单。”

### B. 核心实现：从工具 execute 到一个新的模型运行

#### B.1 sessions_spawn 在哪里注册成可调用工具

[openclaw-tools.ts 的 createOpenClawTools](/source/?file=cb7d125c061753f2ae.ts) 在适用的宿主路径收集 `createSessionsSpawnTool(...)`。是否实际暴露仍取决于运行模式和工具策略；部分 embedded 模式有自己的工具接入规则。

工具定义在 [sessions-spawn-tool.ts](/source/?file=31b532c623d68cd438.ts)。其 `execute` 解析模型提交的 `task`、`runtime`、`agentId`、`mode`、`cleanup` 等参数。对于本例 `runtime="subagent"`，调用：

```ts
// 源码调用的关键字段摘录，省略其他可选参数。
const result = await spawnSubagentDirect(
  { task, label: label || undefined, agentId: requestedAgentId,
    runTimeoutSeconds, mode, cleanup },
  { agentSessionKey: opts?.agentSessionKey,
    workspaceDir: opts?.workspaceDir },
);
```

`runtime="acp"` 进入另一条接入路径，不是本例的本地 subagent 启动过程。

#### B.2 深度检查、子会话创建和目标选择在哪里

进入 [subagent-spawn.ts 的 spawnSubagentDirect](/source/?file=ab9093a6fa6799a944.ts#L363)，关键判断和标识生成的源码摘录如下：

```ts
const maxSpawnDepth =
  cfg.agents?.defaults?.subagents?.maxSpawnDepth ?? DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH;
// 随后：callerDepth >= maxSpawnDepth 时返回 forbidden。

const activeChildren = countActiveRunsForSession(requesterInternalKey);
// 随后：activeChildren >= maxChildren 时返回 forbidden。

const targetAgentId = requestedAgentId ? normalizeAgentId(requestedAgentId) : requesterAgentId;
const childSessionKey = `agent:${targetAgentId}:subagent:${crypto.randomUUID()}`;
```

两个调用各生成一个 UUID。跨 Agent 时还有 `allowAgents` 等检查，不能认为模型可以随意指定任何 Agent。

#### B.3 子助手实际收到的 prompt 长什么样

同一文件先用 `buildSubagentSystemPrompt(...)` 构造子任务角色和回传规则，再构造 `childTaskMessage`：

```ts
const childTaskMessage = [
  `[Subagent Context] You are running as a subagent (depth ${childDepth}/${maxSpawnDepth}). Results auto-announce to your requester; do not busy-poll for status.`,
  spawnMode === "session"
    ? "[Subagent Context] This subagent session is persistent and remains available for thread follow-up messages."
    : undefined,
  `[Subagent Task]: ${task}`,
]
  .filter((line): line is string => Boolean(line))
  .join("\n\n");
```

本例 `mode=run`，所以持久会话那一行不出现。价格子任务的用户消息是：一段自动添加的 Subagent Context，加上 A.4 的完整 `task`。它不是自动复制父会话的全部活动消息，也不依赖子助手猜测“主助手刚才说的预算”。

#### B.4 哪一个调用真正把子任务交给执行系统

仍在 [subagent-spawn.ts](/source/?file=ab9093a6fa6799a944.ts#L740)，实际边界是 `callSubagentGateway`：

```ts
// 源码调用的关键字段摘录，省略来源和其他运行字段。
const response = await callSubagentGateway({
  method: "agent",
  params: {
    message: childTaskMessage,
    sessionKey: childSessionKey,
    idempotencyKey: childIdem,
    lane: AGENT_LANE_SUBAGENT,
    extraSystemPrompt: childSystemPrompt,
    timeout: runTimeoutSeconds,
  },
  timeoutMs: 10_000,
});
```

`timeoutMs: 10_000` 是这次 Gateway 请求的超时参数；`timeout: runTimeoutSeconds` 是传给子运行的期限，本例 120 秒。不要把两者混成“子任务只允许跑 10 秒”。

Gateway 的 `agent` 方法入口见 [server-methods/agent.ts](/source/?file=c39d8a9267d8f93bde.ts)，它把请求交给 `agentCommandFromIngress` 等正常执行链，再进入 embedded runner。不是在父助手的一次模型请求里递归计算出另一个模型的结果。

#### B.5 父子关系何时登记，为什么 accepted 不等于完成

成功提交后调用 `registerSubagentRun`，关键关联字段是：

```ts
// 源码登记参数摘录。
registerSubagentRun({
  runId: childRunId,
  childSessionKey,
  controllerSessionKey: requesterInternalKey,
  requesterSessionKey: requesterInternalKey,
  requesterOrigin: childSessionOrigin,
  requesterDisplayKey,
  task,
  cleanup,
  label: label || undefined,
  // 另有模型、超时、附件、spawnMode 等字段。
});
```

入口位于 [subagent-registry.ts](/source/?file=e7c1fba2e657045afc.ts#L757)。随后 spawn 返回 `status: "accepted"`、`runId`、`childSessionKey` 等。此时已提交并登记，但业务文件可能还没被子助手读取。

### C. 两个子任务在哪里并行，在哪里回到父助手

#### C.1 Lane 负责调度，不负责决定业务分工

[pi-embedded-runner/run.ts](/source/?file=2404b063c2e804b099.ts#L221) 先计算 `sessionLane`、`globalLane`，再嵌套调用 `enqueueSession(() => enqueueGlobal(...))`。

本例可用以下配置片段演示并发限制；这是需要合并到现有 OpenClaw 配置中的相关字段，不包含模型认证等其他设置：

```json
{
  "agents": {
    "defaults": {
      "subagents": {
        "maxConcurrent": 2,
        "maxSpawnDepth": 1,
        "maxChildrenPerAgent": 2
      }
    }
  }
}
```

[server-lanes.ts](/source/?file=b25cc42d767cc0bf37.ts) 用 `setCommandLaneConcurrency(CommandLane.Subagent, resolveSubagentMaxConcurrent(cfg))` 设置子运行额度。

两项任务有不同 Session Lane，但都需要 Subagent 类别的可用额度。允许并行不保证同一毫秒开始；并发为 1 时仍可先受理两项，再排队执行。

#### C.2 子助手内部也会运行自己的 prompt → 模型 → 工具循环

每个子任务都再次经过 Bootstrap 准备、有效工具装配、`activeSession.prompt(effectivePrompt)`、AgentLoop 和文件读取；这里的 `effectivePrompt` 来源于提交的 `childTaskMessage`，还可能经过宿主处理。价格助手读取 prices.json，库存助手读取 stock.json，再分别生成 A.6 的最终结果。

Skill 正文已经指导父助手如何构造 `task`；子助手是否再次读取某个 Skill，取决于它自己的可用资源和任务要求。这里的子任务只需读取指定数据，没有必要重新发现父助手的全部方法。

#### C.3 谁观察到子任务已经结束

[subagent-registry.ts 的 ensureListener](/source/?file=e7c1fba2e657045afc.ts#L652) 订阅 Agent 事件，关键查找如下：

```ts
if (!evt || evt.stream !== "lifecycle") {
  return;
}
const phase = evt.data?.phase;
const entry = subagentRuns.get(evt.runId);
```

`start` 更新起始信息；`end` 推动 `completeSubagentRun(...)`；`error` 还可能先进入延迟处理，避免把 Provider 正在重试的暂态错误过早当作最终失败。

所以回传依赖 `runId` 找到父子登记关系，不靠“谁最后打印了一句话”来猜测归属。

#### C.4 业务文本怎样变成完成通知

[subagent-announce.ts 的 runSubagentAnnounceFlow](/source/?file=840f0799aef42333e7.ts#L221) 取得最终结果 `findings`，构造内部事件。真实关键字段：

```ts
{
  type: "task_completion",
  source: announceType === "cron job" ? "cron" : "subagent",
  childSessionKey: params.childSessionKey,
  childSessionId: announceSessionId,
  announceType,
  taskLabel,
  status: outcome.status,
  statusLabel,
  result: findings,
  statsLine,
  replyInstruction,
}
```

接着调用 `deliverSubagentAnnouncement(...)`。它和 [subagent-announce-delivery.ts](/source/?file=6d3a7bd29b69736804.ts) 等模块根据请求者状态处理引导、排队、内部后续输入或渠道投递。

**完成事件不是原来那次 `sessions_spawn` 的第二个同步返回值。** 它会在适当时机让请求者取得新材料，父助手后续模型请求才据此综合结果。某些顶层路径还可能直接投递子结果，不能把所有宿主情况都简化成固定的一种消息角色。

#### C.5 父助手怎样等待、怎样汇总

本例的父助手取得两份 accepted 后，按本次宿主支持的机制等待完成通知。`sessions_yield` 只在提供了 `onYield` 的上下文中有效；实现见 [sessions-yield-tool.ts](/source/?file=9b2c082df0e7cd8d94.ts)。它请求让出本轮，不会立即返回两份最终业务结果。

假设库存先完成，父助手先记录 S；价格稍后完成，再记录 P。业务汇总可用以下**教学伪代码**表示，OpenClaw 的通用 Registry 并没有内置这套午饭业务：

```text
收到一个完成结果：
    按登记的子任务身份确认是价格 P 还是库存 S
    检查 status、数据字段和 source
    保存成功结果；失败时标记缺失

P 与 S 都成功时：
    按 id 连接两组结果
    保留 spicy=false 且 price<=20 且 stock>0 的项
    从中选择最低价
    对照原用户“只给方案、不下单”要求生成回答
```

这里主助手可由模型根据上下文完成汇总；Skill 的作用是提供步骤。程序的责任是隔离会话、运行工具、调度执行并把结果交给正确的请求者。

### D. 从用户输入到最终方案的完整时序

```text
用户：先读协作 Skill，用两个子助手查数据，不辣、20 元以内、不下单
  ↓
父 Session：prompt → 第 1 次模型请求
  ← read(skills/choose-lunch-team/SKILL.md)
  → toolResult：完整分工步骤
  ↓
父 Session：后续模型请求读到 Skill
  ← sessions_spawn(价格 task)
  → execute → spawnSubagentDirect → Gateway agent → 登记 run-P
  ← accepted-P
  ← sessions_spawn(库存 task)
  → execute → spawnSubagentDirect → Gateway agent → 登记 run-S
  ← accepted-S
  ↓
父助手按支持的机制让出 / 等待
  ├→ CHILD-P：Session Lane → Subagent Lane → 子模型 → read(prices.json)
  └→ CHILD-S：Session Lane → Subagent Lane → 子模型 → read(stock.json)
       ↓                                  ↓
   价格最终文本                         库存最终文本
       └→ lifecycle end → Registry → announce / delivery ←┘
  ↓
父会话在允许时机取得完成结果，后续模型请求综合 P 与 S
  ↓
最终：蛋炒饭 10 元、不辣、有货，尚未下单
```

两个 spawn 工具调用可以出现在同一条助手消息，也可以分属不同轮，取决于模型和工具执行配置。子任务的并行由 Lane 额度决定，不是由上面示意图的左右位置决定。

### E. 课堂断点表

| 想确认的事实 | 源码位置 | 本例应观察的数据 |
|---|---|---|
| 父助手使用了协作 Skill | 父会话后续模型请求 | 含 Skill 正文的读取结果 |
| 模型确实提出了分工 | `sessions-spawn-tool.ts / execute` | A.4、A.5 两组参数 |
| 子任务已独立创建 | `subagent-spawn.ts / spawnSubagentDirect` | 两个 childSessionKey |
| 子助手究竟收到什么 | 同文件 `childTaskMessage` | Subagent Context + 完整 task |
| 已提交到执行系统 | 同文件 `callSubagentGateway` | method=agent、lane=subagent |
| 父子关系有据可查 | `registerSubagentRun` | runId、请求者和子会话关联 |
| 已完成业务执行 | Registry lifecycle 监听 | 对应 runId 的终态 |
| 最终材料已送出 | `runSubagentAnnounceFlow` | task_completion.result |
| 父助手已经利用结果 | 父会话后续请求与回答 | P、S 及正确的筛选条件 |

---

## 第一部分：补充理解多会话、并发和结果汇总

### 1. 一份午饭任务，为什么要三个助手

用户对主助手说：

> 帮我比较今天的午饭。不辣，20 元以内。价格和库存都确认一下，先给方案，不要下单。

假设主助手已经取得一份候选清单：

```text
A：牛肉面
B：鸡腿饭
C：蛋炒饭
```

接下来有两份独立的资料可以查询：

```text
任务 P：核对 A、B、C 的价格与口味
任务 S：核对 A、B、C 的实时库存
```

两个子助手分别负责 P、S，主助手负责比较和回答。

这里先准备同一份候选清单，是为了让两项查询面对相同的对象，而不是各自猜测用户要查哪些午饭。

### 2. 多 Agent 配置与本次多助手协作有何区别

系统可能配置多个 Agent：

```text
main：日常助手
coding：代码助手
research：资料助手
```

收到消息后，路由器可以选择其中一个接手。

```text
某个入口的消息 → 选择 coding → coding 回答
```

这说明系统支持多个 Agent 配置，但不意味着这条消息已经被拆成多个并行任务。

本讲的协作发生在接手之后：

```text
主助手拿到午饭任务
    ├→ 启动价格子任务
    └→ 启动库存子任务
    ↓
收到结果并汇总
```

路由选择和运行时分工是两层不同的机制。

### 3. “子助手”是不是必须对应另一份 Agent 配置

不一定。

可以沿用同一份 Agent 配置，创建新的子会话：

```text
Agent 配置：main

父会话：agent:main:…
价格子会话：agent:main:subagent:…
库存子会话：agent:main:subagent:…
```

也可以指定其他允许调用的 Agent 配置，例如 research。

所以要分开看：

| 名称 | 表示什么 |
|---|---|
| agentId | 选择哪份 Agent 配置 |
| sessionKey | 选择哪一段会话状态 |
| runId | 跟踪哪一次运行 |
| label | 帮助人和程序识别本次任务的名称 |

同一个 agentId 下，可以同时有多个不同的 Session。

### 4. 主助手先把任务边界写清楚

价格子任务接收：

```text
候选：A 牛肉面、B 鸡腿饭、C 蛋炒饭。
查询今天的价格与是否辣。
只查询，不下单。
按候选 ID 返回价格、口味、来源和查询时间。
无法确认的字段写“未知”，不要猜测。
```

库存子任务接收：

```text
候选：A 牛肉面、B 鸡腿饭、C 蛋炒饭。
查询今天的实时库存。
只查询，不下单。
按候选 ID 返回有货 / 售罄 / 未知、来源和查询时间。
```

任务描述中的候选集合、约束和输出字段，都是协作接口的一部分。

### 5. 为什么不能只写“你去查价格”

因为子会话不是直接共享父会话的同一个消息数组。

“价格”指哪几份午饭？是否允许下单？查询哪一天？怎样返回？

若这些条件只存在于父会话中，却没有通过任务、选定上下文或受支持的附件等机制交给子任务，子助手就可能缺少必要信息。

本讲按显式任务文本传递依赖资料，不假定系统自动复制父会话全部历史。

### 6. 第一次 sessions_spawn 返回什么

主助手请求启动价格任务。

程序检查通过后，返回一份类似结果：

```text
status = accepted
childSessionKey = agent:main:subagent:price-示意ID
runId = run-P
mode = run
```

这里的短 ID 只是便于教学。实际子会话键使用生成的唯一标识。

这份返回值表示：

> 这项子任务已被接收并建立了跟踪关系。

它没有包含最终的午饭价格，也不证明子任务已经取得执行额度。

### 7. 第二次 spawn 也返回 accepted

库存任务得到另一组标识：

```text
status = accepted
childSessionKey = agent:main:subagent:stock-示意ID
runId = run-S
```

此时有三份会话状态：

```text
父会话 PARENT
    用户任务
    两次 spawn 的工具调用和返回

价格子会话 CHILD-P
    价格任务
    自己的模型与工具消息

库存子会话 CHILD-S
    库存任务
    自己的模型与工具消息
```

父会话不会因为两项任务被接收，就立刻多出所有子任务的内部消息。

### 8. 程序为什么必须记住父子关系

当价格任务完成时，系统要知道：

```text
这是哪一次运行？
属于哪个子会话？
应该把结果交回哪个父会话？
当前任务是否已经发送过完成通知？
后面是否还需要清理？
```

所以需要 Registry：

| runId | 子会话 | 请求者会话 | 任务 |
|---|---|---|---|
| run-P | CHILD-P | PARENT | 查询价格 |
| run-S | CHILD-S | PARENT | 查询库存 |

Registry 保存的是执行关系和生命周期信息，不是用来替代子会话完整历史的另一份聊天记录。

### 9. 两个子助手怎样各自运行

每个子助手内部仍然是前面学过的执行过程：

```text
任务文本
    ↓
AgentSession.prompt
    ↓
请求模型
    ↓
调用工具
    ↓
生成 toolResult
    ↓
继续请求模型
    ↓
形成子任务结果
```

价格子任务得到：

| ID | 价格 | 口味 |
|---|---:|---|
| A | 30 元 | 不辣 |
| B | 20 元 | 不辣 |
| C | 10 元 | 不辣 |

库存子任务得到：

| ID | 库存 |
|---|---|
| A | 有货 |
| B | 售罄 |
| C | 有货 |

### 10. 它们一定同时开始吗

不一定。至少要区分：

```text
已经 accepted
    ↓
等待调度额度
    ↓
实际开始运行
```

假设子任务并发额度只有 1：

```text
价格任务运行
库存任务排队
    ↓
价格结束，库存开始
```

如果额度是 2，而且没有其他占用和依赖，则两项任务可以同时推进。

“启动了两个子任务”不能直接等同于“两个子任务已经并行执行”。

### 11. 为什么还要限制同一 Session 的执行

不同子会话可以并行，但同一个会话的两次普通运行若任意竞争：

```text
运行一读取旧历史
运行二也读取旧历史
两边分别追加消息和修改状态
```

就容易出现上下文和输出交错。

OpenClaw 的 embedded runner 使用会话 Lane 组织执行，再使用全局类别 Lane 限制整体并发。

```text
同一 sessionKey 的普通运行
    进入相同的 Session Lane

不同子会话的运行
    进入不同 Session Lane
    但共同竞争 Subagent Lane 的额度
```

运行中的 steer、终止和特殊控制路径另有处理，不能把所有控制动作都简化成普通 prompt 排队。

### 12. 主助手这时候需要一直轮询吗

通常不需要。

它可以说明正在等待，并在支持的上下文中使用 `sessions_yield` 结束当前轮次，把控制权交回调度系统。

```text
主助手提交价格任务和库存任务
    ↓
主助手让出当前轮次
    ↓
子任务继续执行
    ↓
完成事件送回请求者
    ↓
父会话后续处理结果
```

这不是在模型内部挂起一个永不结束的思考过程，也不是操作系统线程一直睡眠等子任务。

该工具需要宿主提供 yield 回调；没有相应运行上下文时，工具会返回错误。

### 13. 库存先返回怎么办

异步任务可以乱序完成。

假设先得到库存结果：

```text
PARENT 已有：
    库存结果 S

PARENT 尚缺：
    价格结果 P
```

主助手应该识别“还缺价格”，而不是把“第一个回来”当成“全部完成”。

稍后价格回来，再进行连接：

```text
以候选 ID 为键
    将价格表与库存表合并
```

不能按两张表的行号强行配对，因为子助手可能采用不同的排序。

### 14. 最终怎样得到“蛋炒饭”

主助手形成：

| ID | 午饭 | 价格 | 不辣 | 库存 | 是否满足本次要求 |
|---|---|---:|---|---|---|
| A | 牛肉面 | 30 元 | 是 | 有货 | 超预算 |
| B | 鸡腿饭 | 20 元 | 是 | 售罄 | 无货 |
| C | 蛋炒饭 | 10 元 | 是 | 有货 | 满足 |

然后回答：

> 建议蛋炒饭，10 元、不辣，目前有货；尚未下单。

这一步是父助手根据用户目标和多路结果进行综合判断。

完成事件负责把材料送回来，不会自动把所有业务比较都替父助手做完。

### 15. 子助手结果为什么还要检查

假设价格子助手返回：

```text
C：10 元
另外建议立刻下单。
```

父助手可以使用已核对的价格，但仍应遵守用户“先给方案，不要下单”的要求。

子助手输出是待理解和校验的结果材料，不会自动获得覆盖父会话任务约束的权限。

还要检查来源、查询时间、候选 ID、缺失字段和冲突。多一位助手不等于事实自动更可靠。

### 16. 其中一个任务失败了怎么办

假设价格成功，库存超时：

```text
价格：已确认
库存：未知，查询超时
```

主助手可以根据任务需要选择：

```text
重试库存查询
缩小查询范围
明确标注库存未确认，先给条件性方案
向用户说明需要补充的信息
```

不能把没有返回库存解释为“有货”。

部分成功、全部成功、被取消、执行失败和结果投递失败，也应分别观察。

### 17. 子助手结束了，父助手就一定收到结果了吗

还隔着回传链路：

```text
子运行进入终态
    ↓
Registry 更新状态
    ↓
提取可用的最终结果
    ↓
构造完成事件
    ↓
交给请求者会话或相应投递路径
    ↓
父会话在允许的时机消费
```

父会话可能正在运行，完成事件可能进入排队或引导路径；渠道投递也可能失败。

所以“子任务执行成功”和“父会话已消费结果”“用户已收到最终回复”是三个不同事实。

### 18. 子会话独立，文件也一定独立吗

不一定。

沿用同一个 Agent 配置的多个子会话，可能访问相同 Workspace。实际目录和访问范围还受目标 Agent、配置和运行约束影响。

如果两个子助手同时写：

```text
result.md
```

可能相互覆盖。

更容易检查的分工是：

```text
价格子任务只返回价格，或写 price-result.json
库存子任务只返回库存，或写 stock-result.json
主助手负责最终报告
```

不同会话的消息数组独立，并不自动提供文件级事务隔离。

### 19. 子助手是不是能无限再生子助手

需要限制。

否则可能出现：

```text
主助手
    ├→ 子助手
    │     ├→ 孙助手
    │     │     └→ ……
    │     └→ ……
    └→ ……
```

程序通常会检查：

| 限制 | 控制什么 |
|---|---|
| maxSpawnDepth | 子任务嵌套深度 |
| maxChildrenPerAgent | 当前请求者可同时拥有的活跃子任务数量 |
| allowAgents | 能否选择其他目标 Agent 配置 |
| 并发额度 | 可以有多少项运行实际同时推进 |
| 超时与清理规则 | 任务何时结束、留下哪些资源 |

深度、活跃子任务数和执行并发是不同维度。

---

## 第二部分：把例子抽象成算法

### 20. 先画任务依赖图

本例可以写成：

```text
取得共同候选清单
        │
        ├→ 查询价格与口味 ─┐
        │                 │
        └→ 查询库存 ──────┤
                          ▼
                    连接与过滤结果
                          ↓
                       最终回答
```

图中可以并行的是两条独立查询。

如果库存查询必须先知道价格筛选出的候选，那它就依赖价格结果，不能直接假定两者同时开始。

任务拆分的关键是识别输入依赖，而不只是把标题平均分给两个助手。

### 21. 什么任务适合拆出去

优先考虑：

```text
输入能明确传递
结果能独立校验
与其他任务共享修改较少
工作量足以抵消启动与汇总开销
```

只需一次简单查询时，主助手自己执行可能更直接。

同一个 Agent 并行调用工具，与启动两个独立子会话，也不是相同成本的方案。后者增加独立上下文、模型决策和回传过程。

### 22. 用状态机描述一项子任务

下面是教学状态机，不是声称源码中有一组完全同名的枚举：

```text
提出请求
    ├→ forbidden / error
    │
    └→ accepted
           ↓
       排队 / 开始执行
           ↓
       执行终态：成功、失败、超时、取消
           ↓
       完成通知：待处理、已投递或失败待处理
           ↓
       按策略保留或清理
```

运行状态与投递状态最好分别理解，因为执行成功后仍可能存在回传问题。

### 23. spawn 算法

```text
输入：task、可选 agentId、运行模式、超时等

1. 解析请求者 Session 和 Agent。
2. 检查调用深度与活跃子任务数量。
3. 决定目标 Agent；需要时检查 allowAgents。
4. 检查目标运行环境、沙箱及相关约束。
5. 生成独立 childSessionKey。
6. 准备子会话元数据、任务上下文、附件等。
7. 调用 Gateway 的 agent 方法，提交子运行。
8. 注册 runId、子会话和请求者的关系。
9. 返回 accepted 与跟踪标识。
```

若中途失败，代码还需清理临时子会话和附件等资源。本地源码对这些失败路径有专门处理。

### 24. 调度算法

```text
收到某个 Session 的运行请求
    ↓
进入该 Session 对应的 Lane
    ↓
取得运行类别 Lane 的并发额度
    ↓
准备并执行 embedded run
    ↓
释放相应额度
```

普通主运行通常使用 Main 类别；本讲子任务提交到 Subagent 类别。Cron 等路径还有额外安排，不能把类别映射简化成所有路径都相同。

两层队列分别解决会话状态顺序与整体资源使用问题。

### 25. 用时间算清并行能省多少

假设忽略启动、模型思考和汇总开销：

```text
价格查询 = 8 秒
库存查询 = 5 秒
```

串行查询约为：

```text
8 + 5 = 13 秒
```

充分并行时，等待两个结果约为：

```text
max(8, 5) = 8 秒
```

真实系统还要加上：

```text
子会话启动 + 各自模型调用 + 调度等待 + 完成回传 + 父助手汇总
```

如果 Subagent 并发额度是 1，或者库存依赖价格结果，本例就不能获得上面的完整并行收益。

### 26. 完成回传算法

```text
1. 观察运行生命周期事件和已注册的任务关系。
2. 确定任务终态，处理重试或错误的相关边界。
3. 取得子会话中的可用结果。
4. 构造包含任务身份、状态、结果等信息的完成事件。
5. 确定请求者与投递方式。
6. 根据请求者状态进入引导、排队或相应投递路径。
7. 更新通知、重试与清理状态。
```

它不是简单的“子助手 return 一个字符串，父助手原地立刻拿到”。

### 27. 父助手的汇总算法

```text
维护本次任务所需的结果集合：{价格 P, 库存 S}

每次收到完成结果：
    根据任务身份匹配需要的结果项
    检查状态、来源、时间与字段
    记录成功材料和缺失信息

当满足本次回答条件时：
    用候选 ID 连接 P 与 S
    应用口味、预算和库存过滤
    核对用户当前约束
    给出最终方案及未确认事项
```

这段算法可以由模型结合上下文执行，也可以在业务系统中部分结构化实现。OpenClaw 的通用完成回传本身不包含午饭业务规则。

### 28. run 模式、session 模式和 cleanup 分别回答什么

| 维度 | 回答的问题 |
|---|---|
| mode=run | 本次按一项任务执行 |
| mode=session | 创建适合后续交互的会话模式，部分场景涉及线程绑定 |
| cleanup=keep / delete | 按支持的流程决定后续会话保留或清理 |

它们不是同一个开关。

`mode=session` 也不代表永远有一台独立机器持续运行；具体会话复用、线程支持、生命周期和保留限制依赖宿主实现。

本讲使用 `mode=run`，避免把持续交互和一次任务混进同一条演示主线。

### 29. 持久化 Registry 能保证什么

它帮助系统保存已知的任务关系与状态，使后续恢复、完成处理或清理有据可查。

但 Registry 是元数据，不是模型执行进程的完整快照。

```text
登记表在磁盘上
    ≠
程序崩溃后，任意外部调用都能从同一条机器指令继续
```

模型请求、工具副作用和渠道投递各有自己的恢复边界。父助手也不能因为收到重复完成通知，就无条件重复执行下单等动作。

---

## 第三部分：代码实现

### 30. 工具入口接受哪些任务参数

打开 [sessions-spawn-tool.ts](/source/?file=31b532c623d68cd438.ts)。

本地 Schema 包含 `task`、`label`、`runtime`、`agentId`、`model`、`mode`、`cleanup`、`runTimeoutSeconds` 等字段，还支持某些特定路径的附件和其他参数。

教学调用可以写成：

```json
{
  "task": "候选 A 牛肉面、B 鸡腿饭、C 蛋炒饭。核对今天的价格和口味，只查询不下单。按候选 ID 返回价格、口味、来源和查询时间；未知字段明确标注。",
  "label": "lunch-price",
  "runtime": "subagent",
  "mode": "run",
  "cleanup": "keep",
  "runTimeoutSeconds": 120
}
```

另一项库存任务使用自己的 `task` 和 `label`。

这里不指定 `agentId`，沿本地默认规则选择请求者 Agent。`runtime="acp"` 会进入其他执行接入路径，本讲不把它当成本地 subagent 实现的同义词。

### 31. 深度与数量在哪里检查

打开 [subagent-spawn.ts 的 spawnSubagentDirect](/source/?file=ab9093a6fa6799a944.ts#L363)。

可直接找到两类判断：

```text
callerDepth >= maxSpawnDepth
    → forbidden

activeChildren >= maxChildren
    → forbidden
```

`activeChildren` 来自请求者 Session 对应的活跃运行计数。

因此 `maxChildrenPerAgent` 的配置名不能被直接理解成整个系统所有 Session 共用的一把全局执行并发锁。

### 32. 目标 Agent 的允许范围在哪里检查

同一文件先取得请求者 Agent，再计算目标：

```ts
// 源码摘录：目标 Agent 的选择。
const targetAgentId = requestedAgentId ? normalizeAgentId(requestedAgentId) : requesterAgentId;
```

本地实现支持要求显式 `agentId` 的配置；满足这一前置条件后，跨到其他 Agent 时会检查请求者配置中的 `subagents.allowAgents` 等规则。

若没有跨配置需求，本讲不必为两个子会话预先建立两份不同 Agent 配置。

### 33. 子会话键在哪里生成

还是 [subagent-spawn.ts](/source/?file=ab9093a6fa6799a944.ts#L497)：

```ts
// 源码摘录：独立子会话标识。
const childSessionKey = `agent:${targetAgentId}:subagent:${crypto.randomUUID()}`;
```

`agentId` 决定配置归属，UUID 区分不同子会话。

不能只用 label 当作唯一标识；两个任务可能使用相同 label。

### 34. 真正启动子运行的边界在哪里

同一文件调用 `callSubagentGateway`，方法为 `agent`。

关键参数的阅读视图如下，属于教学整理，不是完整可独立运行的源码函数：

```text
method = agent
message = childTaskMessage
sessionKey = childSessionKey
lane = AGENT_LANE_SUBAGENT
extraSystemPrompt = childSystemPrompt
timeout = runTimeoutSeconds
idempotencyKey = childIdem
```

子任务通过 Gateway 进入正常的 Agent 执行系统，不是另外在父模型调用的 JavaScript 栈里递归执行一份模型思考。

请求幂等标识帮助识别重复提交；它也不自动让所有业务工具的副作用都具备幂等性。

### 35. Registry 怎样接上父子关系

在成功提交后，代码调用 `registerSubagentRun`。

重点字段包括：

```text
runId
childSessionKey
controllerSessionKey
requesterSessionKey
requesterOrigin
task
label
cleanup
spawnMode
```

入口见 [subagent-registry.ts](/source/?file=e7c1fba2e657045afc.ts#L757)，实际管理逻辑还委托给相关模块。

在嵌套子任务场景中，请求者可能也是子会话，所以回传关系需要按登记的请求者逐层处理。

### 36. accepted 返回语句在哪里

在 [subagent-spawn.ts 的返回处](/source/?file=ab9093a6fa6799a944.ts#L919)，成功结果包含：

```text
status: accepted
childSessionKey
runId
mode
note
以及模型、附件等相关回执
```

这与子任务的业务结果表是两种数据。

父会话首先得到的是工具调用回执，最终结果通过后续完成处理到达。

### 37. 两层 Lane 在哪里嵌套

打开 [pi-embedded-runner/run.ts](/source/?file=2404b063c2e804b099.ts)。

先计算：

```text
sessionLane = resolveSessionLane(sessionKey 或 sessionId)
globalLane  = resolveGlobalLane(lane)
```

然后将全局类别队列嵌在会话队列任务里：

```text
enqueueSession(
    取得本会话的执行顺序后，调用 enqueueGlobal(
        实际的准备与运行工作
    )
)
```

这是对源码结构的伪代码整理。

命名规则可看 [lanes.ts](/source/?file=2f1bfb6678ecb40965.ts)：会话 Lane 使用 `session:` 前缀。

全局额度由 [server-lanes.ts](/source/?file=b25cc42d767cc0bf37.ts) 设置：

```ts
// 源码摘录：主运行与子运行额度的配置。
setCommandLaneConcurrency(CommandLane.Main, resolveAgentMaxConcurrent(cfg));
setCommandLaneConcurrency(CommandLane.Subagent, resolveSubagentMaxConcurrent(cfg));
```

Main 和 Subagent 是不同类别的额度，不应当直接理解为“所有运行都加起来只能有 main 的数量”。

### 38. 生命周期事件怎样推动完成处理

回到 [subagent-registry.ts 的 ensureListener](/source/?file=e7c1fba2e657045afc.ts)。

监听器检查 lifecycle 事件，按 `runId` 查找登记记录，并处理 start、end、error 等阶段。

本地实现对某些瞬时 error 会延迟终态处理，避免 Provider 重试仍在进行时过早发送最终失败通知。

因此，看到一次底层错误日志，不一定表示整项子任务已经最终失败。应查看登记状态、后续生命周期和最终 outcome。

### 39. 最终结果怎样变成完成事件

打开 [subagent-announce.ts 的 runSubagentAnnounceFlow](/source/?file=840f0799aef42333e7.ts#L221)。

取得结果和状态后，代码构造 `task_completion` 内部事件，其中包含：

```text
childSessionKey
childSessionId
taskLabel
status
result
replyInstruction
以及相关统计和说明
```

然后调用 `deliverSubagentAnnouncement`。

请求者是子助手时，结果可以作为内部后续输入交回协调者；顶层场景还可能涉及直接投递和渠道来源选择。具体会根据请求者状态和选项决定，不是永远使用同一种可见消息形式。

继续阅读 [subagent-announce-delivery.ts](/source/?file=6d3a7bd29b69736804.ts)，可以检查引导、排队和投递分支。

### 40. sessions_yield 为什么需要宿主配合

打开 [sessions-yield-tool.ts](/source/?file=9b2c082df0e7cd8d94.ts)。

```ts
// 源码摘录：上下文检查与 yield 回调。
if (!opts?.sessionId) {
    return jsonResult({ status: "error", error: "No session context" });
}
if (!opts?.onYield) {
    return jsonResult({ status: "error", error: "Yield not supported in this context" });
}
await opts.onYield(message);
return jsonResult({ status: "yielded", message });
```

工具本身只通过回调请求宿主处理。

在 [attempt.ts](/source/?file=4c2d09aeeb74b60140.ts) 等宿主路径中，还要配合当前 Session 的中断与后续运行机制，才能完成“让出本轮、以后消费结果”。

不能把工具返回的 `yielded` 解释成所有子任务已经完成。

### 41. 失败与清理代码为什么很多

spawn、执行、回传和清理跨越了不同组件：

```text
临时子会话已创建，但 Gateway 提交失败
运行已提交，但登记失败
工具已成功，但模型最终整理失败
子任务成功，但完成投递失败
通知已发送，但后续清理未完成
```

这些都需要分别处理。

本地 spawn 代码在失败路径中会尝试清理临时 Session、附件及相关资源；Registry 和 announce 模块则处理后续状态、通知重试与清理。

阅读时应把“业务完成”“通知完成”“清理完成”画成不同的观察点，而不是找一个万能的 done。

### 42. 最后把完整链路再走一遍

```text
用户：选不辣、20 元以内的午饭，不下单
    ↓
主助手：取得 A、B、C 的共同候选清单
    ↓
sessions_spawn：价格任务 → accepted、run-P、CHILD-P
sessions_spawn：库存任务 → accepted、run-S、CHILD-S
    ↓
程序：子会话、Registry、Session Lane、Subagent Lane
    ↓
两个子任务各自运行模型与工具
    ↓
库存先完成 → 库存完成事件
价格后完成 → 价格完成事件
    ↓
回传给请求者，在允许时机进入父会话处理
    ↓
父助手：按候选 ID 连接结果，应用用户约束
    ↓
最终回答：蛋炒饭 10 元、不辣、有货，尚未下单
```

这个系统的协作关系来自任务与结果的传递，不要求三个模型共享同一个活动消息数组。

### 43. 课堂练习

先按本讲画出三个会话、两个 runId、两项任务及回传关系，再分别改变一个条件：

1. Subagent 并发额度从 2 改成 1。
2. 库存任务超时，价格任务成功。
3. 两项任务同时写入同一个报告文件。
4. 价格结果重复投递一次。
5. 子助手建议下单，但用户仍只允许给方案。
6. 库存查询必须依赖价格筛选后的候选。

对每种变化，说明执行顺序、可用结果和最终回答条件怎样改变；不要只回答“多开一个 Agent”。

上一讲：[14 AgentSession 执行原理](/openclaw/chapter-14)  
下一讲：[16 OpenClaw Gateway 架构、多渠道接入与消息事件通信](/openclaw/chapter-16)
