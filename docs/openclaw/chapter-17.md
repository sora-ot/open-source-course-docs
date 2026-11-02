---
title: "17 · 路由、Session 与并发调度"
description: "openclaw · 系统集成 · 课程讲义"
project: "openclaw"
sourcePath: "OpenClaw/OpenClaw-Course/17_OpenClaw Multi-Agent路由、Session管理与并发调度.md"
originalUrl: "/originals/openclaw/chapter-17.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 17 OpenClaw Multi-Agent 路由、Session 管理与并发调度

Alice 在 WeChat 中发来一句：“你好，我想讨论一个 TypeScript 项目。”电脑上的 OpenClaw 已经接收了这条消息，但它还不能立即把文本交给模型：同一台电脑同时服务多个用户，也配置了不同用途的 Agent。它需要确定由谁处理、接续哪段历史、何时开始执行，以及把结果送回哪里。

本章沿着这条消息的数据变化展开，再加入 Bob、Carol 和群组消息，观察同一套机制如何处理多用户与并发。此前讲过的 Pi AgentSession、消息树和 Agent Loop 在这里作为底层能力使用；重点是 OpenClaw 怎样把它们组织成一个长期服务。

本章基于 OpenClaw v2026.4.22 源码进行分析。人物、账户数字、时间和 UUID 均为教学示例，数据变化由源码推导。

## 1. 固定场景：先跟随 Alice 的一条消息

### 1.1 两个 Agent、一个 Bot、三个用户

电脑上运行一个 Gateway，使用账户 ID 为 `default` 的 WeChat Bot。Alice、Bob、Carol 的 WeChat 用户 ID 分别为 `101`、`202`、`303`；另有一个群 `-100700`。本章普通私聊中，chat.id 与用户 ID 恰好相同；平台适配器仍将它们作为不同来源字段处理。

main Agent 负责日常聊天，coding Agent 负责群里的代码任务。三人的私聊相互隔离，普通执行共同使用两个并发槽。这里暂时把“槽”理解为允许同时开始一项完整 Agent 运行的额度，第 7 节再分析实现。

以下片段用于补充上一章已完成 WeChat 接入、认证和用户/群授权的配置。

~~~json5
{
  agents: {
    defaults: { maxConcurrent: 2 },
    list: [
      {
        id: "main",
        default: true,
        workspace: "~/.openclaw/workspace",
        agentDir: "~/.openclaw/agents/main/agent",
        model: { primary: "openai/gpt-5.4" },
      },
      {
        id: "coding",
        workspace: "~/.openclaw/workspace-coding",
        agentDir: "~/.openclaw/agents/coding/agent",
        model: { primary: "anthropic/claude-sonnet-4-6" },
      },
    ],
  },
  session: { dmScope: "per-channel-peer" },
  messages: {
    queue: {
      mode: "collect",
      debounceMs: 1000,
      cap: 20,
      drop: "summarize",
    },
  },
  bindings: [
    {
      agentId: "main",
      match: { channel: "WeChat", accountId: "*" },
    },
    {
      agentId: "coding",
      match: {
        channel: "WeChat",
        accountId: "default",
        peer: { kind: "group", id: "-100700" },
      },
    },
  ],
}
~~~

`agents.list` 列出可选择的 Agent；`bindings` 根据消息来源选择其中一个；`session.dmScope` 决定私聊按什么字段分开；`messages.queue` 决定运行中又来消息时怎样处理；`maxConcurrent` 则限制普通执行的共享额度。**“main Agent”和“main Global Lane”只是恰好同名：前者是一套 Agent 配置，后者是多个 Agent 普通运行共用的调度队列。**

后文没有明确声明变更时，都沿用这份配置。比较 dmScope 时只改 dmScope；比较消息模式时只改 queue mode。加入 Discord 的段落会单独说明新增账户与规则，结束后回到本节设置。

### 1.2 平台消息提供了哪些具体值

Alice 的第一条消息只保留下列与本章有关的原始字段：

~~~json
{
  "message_id": 501,
  "from": { "id": 101, "first_name": "Alice" },
  "chat": { "id": 101, "type": "private" },
  "text": "你好，我想讨论一个 TypeScript 项目。"
}
~~~

这是删去其他字段的教学输入。消息由 WeChat 插件处理，所以 channel 为 WeChat；接收它的账户任务是 default。插件取 from.id 构造发送者与 direct peer，取 chat.id 保留回复目标。私聊 101 的路由输入为：

~~~text
channel   = "WeChat"
accountId = "default"
peer      = { kind: "direct", id: "101" }
~~~

route 返回后，MsgContext 中相关字段为：

~~~text
Provider / Surface = "WeChat"
AccountId           = "default"
SenderId            = "101"
From / To           = "WeChat:101"
SessionKey          = "agent:main:WeChat:direct:101"
OriginatingChannel  = "WeChat"
OriginatingTo       = "WeChat:101"
MessageThreadId     = undefined
~~~

`WeChat:101` 是插件保存的投递目标；peer ID 为 `101`，Session Key 为 `agent:main:WeChat:direct:101`，三者分别参与目标发送、路由匹配和历史查找。direct peer 优先取 senderId，投递目标来自 chatId；本例两者的数值恰好相同。

### 1.3 这条消息从接收到回复，数据怎样衔接

以下假设示例机器的用户主目录为 `/home/student`。

假设代码生成的 UUID 为 `7e1520f2-6177-4a98-8a4e-68245ac79417`，简记为 S1。下表列出第一次成功处理过程中逐步形成的数据及其用途。

| 阶段 | Alice 的具体数据 | 下一步用途 |
| --- | --- | --- |
| Binding | direct 101 不匹配群规则，命中渠道兜底 | 选择 agentId=main，matchedBy=binding.channel |
| Session Key | `agent:main:WeChat:direct:101` | 作为 Store 查找键与执行作用域 |
| SessionEntry | main 的 sessions.json 中该 Key 对应的对象 | 保存当前 sessionId、路径与元数据 |
| Session ID | `7e1520f2-6177-4a98-8a4e-68245ac79417` | 标识当前持久化会话实例 |
| Session File | `/home/student/.openclaw/agents/main/sessions/7e1520f2-6177-4a98-8a4e-68245ac79417.jsonl` | 交给 Pi SessionManager 打开 |
| Session Lane | `session:agent:main:WeChat:direct:101` | 同一逻辑会话的完整 Run 串行 |
| Global Lane | `main`，容量 2 | 与 Bob、Carol 及 coding 的普通 Run 共用额度 |
| Pi AgentSession | 使用上述 sessionFile 打开的 manager 创建 | 恢复历史，接收含本条用户文本的 prompt |
| 回复来源 | WeChat / default / WeChat:101 | 经本次请求的投递上下文回到 Alice |

**Store 中有条目、JSONL 中有历史、内存中有正在运行的 AgentSession，是三个不同状态。** WeChat 可以在回复初始化前先登记来源元数据；因此第一次消息不等于进入 initSessionState 时 Store 必然为空。第 5 节会把这个先后过程展开。

下图展示数据交接，方框表示处理阶段；真实函数调用在后文逐段展开：

~~~mermaid
flowchart TD
    I["Alice：from.id=101 / chat.id=101"] -->|"WeChat / default / direct:101"| R["Binding → main"]
    R -->|"per-channel-peer"| K["agent:main:WeChat:direct:101"]
    K -->|"查 sessions.json"| E["SessionEntry → S1"]
    E -->|"sessionFile"| F["S1.jsonl：Pi 历史"]
    E -->|"sessionKey 申请执行"| L["session:agent:main:WeChat:direct:101"]
    L -->|"取得会话槽后申请"| G["main Global Lane：容量 2"]
    G -->|"获得额度后创建"| P["Pi AgentSession"]
    F -->|"SessionManager 恢复当前分支"| P
    P -->|"结果 + 原始来源"| O["WeChat / default / WeChat:101"]
~~~

图中的 S1.jsonl 是表中完整 UUID 文件名的缩写。原始用户文本进入 prompt 前还可能增加消息来源与上下文信息，因此 MsgContext.Body 只是最终输入的一部分。

### 1.4 Bob、Carol 加入以后，新增了什么问题

在后面的并发练习中，Alice 正在执行的耗时请求记为 A1。她尚未等到结果，又发 A2：“只分析原因。”Bob 发 B1，Carol 再发 C1。四个编号仅表示本次并发例中的输入，不是源码 runId。

沿用基准配置，A2 属于 Alice 的同一 Session，先保留在待处理消息队列；B1 属于 Bob 的独立 Session，可以使用第二个执行槽；C1 虽也有独立 Session，但两个全局槽已满，需要等待。A1 结束后，A2 才形成后续运行。若 Alice 还连续补充 A3，collect 可以在条件相同的情况下合并 A2、A3。

这提出了后面两组源码问题：Session Key 为什么能把三个人分开？已经分开的运行，又怎样既能并行又不会无限启动？第 7 节先画出这组事件的完整时间线，再拆执行队列；第 8 节解释 A2/A3 的默认 collect 路径及其他模式。

## 2. 多个 Agent 与多个用户，分别共享什么

### 2.1 main 与 coding 是两套执行配置

日常聊天和代码任务往往需要不同的工作目录、默认模型、工具规则和会话历史。OpenClaw 允许在同一 Gateway 配置中声明多个 Agent，让请求按来源进入不同的执行环境。

`agents.list` 保存这些 Agent 的配置，`agentId` 用于选择和定位它们。一个 Agent 可以服务多个用户，也可以拥有很多 Session。普通 Session Key 的 `agent:<id>:` 前缀明确了所属 Agent。

没有 Agent 列表时，默认 ID 为 `main`；有列表时，优先使用第一个 `default: true` 项，否则使用列表第一项：

~~~ts
export function resolveDefaultAgentId(cfg: OpenClawConfig): string {
  const agents = listAgentEntries(cfg);
  if (agents.length === 0) {
    return DEFAULT_AGENT_ID;
  }
  const defaults = agents.filter((agent) => agent?.default);
  if (defaults.length > 1 && !defaultAgentWarned) {
    defaultAgentWarned = true;
    getLog().warn("Multiple agents marked default=true; using the first entry as default.");
  }
  const chosen = (defaults[0] ?? agents[0])?.id?.trim();
  return normalizeAgentId(chosen || DEFAULT_AGENT_ID);
}
~~~

所以，把 Agent 命名为 `main` 与把它设为默认，是两个不同决定。配置可以把 `coding` 标为默认；没有 Binding 命中的请求就会回退到它。

本章显式将 main 标为默认，并用 Binding 将群 -100700 分给 coding；改变群路由不会修改 Alice 的用户身份。

声明两个 Agent 不会自动创建两个 Bot，也不要求启动两个 Gateway。Bot 账户由渠道配置管理，Agent 由 agents.list 管理，两者通过 Binding 联系。

Multi-Agent Routing 主要组织配置、历史与请求分配。Subagent 和 Agent 间通信需要额外的运行关系与权限；配置 main、coding 并不会让它们自动协商分工。

### 2.2 目录、模型与权限的边界

Workspace 是 Agent 的默认工作目录。`agentDir` 是模型目录、认证配置等运行状态的目录。Session Store 与 transcript 默认放在 `agents/<agentId>/sessions/`，不是 Workspace 或 agentDir 的另一种叫法。

| Agent | Workspace | agentDir | 默认会话目录 |
| --- | --- | --- | --- |
| main | `~/.openclaw/workspace` | `~/.openclaw/agents/main/agent` | `~/.openclaw/agents/main/sessions` |
| coding | `~/.openclaw/workspace-coding` | `~/.openclaw/agents/coding/agent` | `~/.openclaw/agents/coding/sessions` |

在基准配置中，main 与 coding 的 Workspace、agentDir 和会话目录都不同。Alice、Bob、Carol 的私聊则共享 main 的配置与 Workspace，但可以拥有三个不同的会话文件。Agent 数量与 Session 数量并没有一一对应关系。

有效主模型优先使用 Agent 自己的 model，再回退 agents.defaults.model；Session 覆盖与本次运行参数还可参与选择。模型目录和认证文件由 agentDir 定位。默认路径的解析与认证继承细节放在第 10.1 节。

Workspace 是默认工作目录，本身不提供操作系统权限隔离。工具实际能访问哪里，仍取决于工具策略、sandbox 和宿主权限。认证加载还会经过主存储继承与合并分支，凭证的实际可用范围由这些加载规则共同决定。

### 2.3 同一条消息里的几种身份

“谁发来的”包含平台身份、接收账户与聊天目标三个不同问题。

| 字段或概念 | 表示什么 | 通常从哪里得到 |
| --- | --- | --- |
| channel | 渠道类型，如 WeChat、discord | 正在处理消息的插件 |
| accountId | 插件使用的 Bot/平台账户配置项 | 渠道账户任务 |
| SenderId | 平台发送者的用户 ID | WeChat from.id、Discord author.id 等 |
| peer.kind / peer.id | 本次聊天对象的类型与 ID | 插件根据私聊、群、频道构造 |
| guildId / teamId | 服务器或团队 | Discord guild、Slack team 等上下文 |
| memberRoleIds | 发送者在服务器中的角色 ID 集合 | 插件取得的成员资料 |
| thread ID | topic/thread 子对话标识 | 平台线程字段 |
| agentId | 选择哪个 Agent 配置 | Binding 或默认 Agent |
| sessionKey | 请求归属的逻辑会话地址 | 路由、插件后处理、别名规范化 |
| sessionId | 当前会话实例的 ID | Store 中复用或创建 UUID |
| runId | 一次执行的相关标识 | 调用参数或执行层生成 UUID |

WeChat 私聊 peer 通常对应发送者；群聊 peer 则是群或话题，SenderId 仍然是具体发言人。Bot 的 accountId 选择接收账户，群组 ID 表示聊天目标，Alice 的用户 ID 则标识发送者。

假设默认 Bot 收到 Alice `101` 与 Bob `202` 两个私聊消息。两者 channel、accountId 相同，SenderId 与 direct peer 不同。只按渠道/账户匹配的 Binding 可以让两人进入同一个 Agent；是否进入同一个 Session，还要看 dmScope。

还要区分“取得用户 ID”和“允许用户操作”。访问策略、配对、群规则和命令授权决定请求能否继续。`identityLinks` 只影响 Session 地址中的身份映射，不替代认证或授权。检查顺序由插件决定；例如 WeChat 先计算 route，随后执行 DM access 检查。

## 3. Binding：先判断这条消息应该由谁处理

### 3.1 同一个 Bot，为什么私聊进 main、群聊进 coding

Alice 发给 Bot 的私聊与 Bob 发到群 -100700 的消息，都由同一个 WeChat 账户接收。渠道和账户相同，聊天对象不同；Binding 正是把这种来源差别映射到 Agent。

从基准配置中只取出两条规则：

~~~json5
bindings: [
  { agentId: "main", match: { channel: "WeChat", accountId: "*" } },
  {
    agentId: "coding",
    match: {
      channel: "WeChat",
      accountId: "default",
      peer: { kind: "group", id: "-100700" },
    },
  },
]
~~~

第一条将本渠道未被更高优先级规则接走的消息分给 main；第二条把 default 账户中的特定群分给 coding。这里 agentId 是结果，match 是条件；channel 指 WeChat 渠道，accountId 指 Bot 账户，peer 指聊天对象。群消息的 SenderId 仍然是 Bob 的 202，peer.id 则是 -100700。

渠道兜底写在前面仍不影响精确群规则优先命中：Binding 先按匹配层级选择规则，同层才按配置顺序查找。

### 3.2 先手动匹配 Alice 与群消息

Alice 的输入为 `WeChat / default / direct:101`。先按 channel、accountId 筛候选，两条规则都暂时留下：第一条的 * 接受 default，第二条显式要求 default。随后检查 peer，第二条要求 group:-100700，与 direct:101 不符，不能命中。其他更具体的层级也没有适用规则，最终渠道兜底生效，返回：

~~~text
agentId  = "main"
matchedBy = "binding.channel"
~~~

Bob 在群中发消息时，输入改为 `WeChat / default / group:-100700`。候选仍是同样两条；第二条的 peer kind、ID 和账户全部满足，第一条的宽泛渠道条件也满足。但精确 peer 属于第 1 层，渠道兜底属于第 8 层，所以第二条先返回：

~~~text
agentId  = "coding"
matchedBy = "binding.peer"
~~~

把两次检查并排看：

| 检查 | Alice 私聊 | Bob 在群中发言 |
| --- | --- | --- |
| channel / account 筛选 | 两条都是候选 | 两条都是候选 |
| 精确 group:-100700 | direct:101，不满足 | group:-100700，满足 |
| 渠道兜底 | 成为最终命中 | 条件虽满足，但不再走到这一层 |
| 输出 | main / binding.channel | coding / binding.peer |

### 3.3 真实输入结构、字段规范化与候选集合

刚才两条规则属于普通 route Binding，真实类型如下：

~~~ts
export type AgentBindingMatch = {
  channel: string;
  accountId?: string;
  peer?: { kind: ChatType; id: string };
  guildId?: string;
  teamId?: string;
  /** Discord role IDs used for role-based routing. */
  roles?: string[];
};

export type AgentRouteBinding = {
  /** Missing type is interpreted as route for backward compatibility. */
  type?: "route";
  agentId: string;
  comment?: string;
  match: AgentBindingMatch;
};
~~~

`agentId` 是命中后的目标；`match` 描述匹配条件。省略 type 兼容为普通 route。当前配置还存在 `type: "acp"`，但普通路由枚举会区分这类 ACP Binding，本章使用 route 主线。

`peer.id: "*"` 在此版本中表示相应 peer kind 的通配约束。`roles` 是平台角色 ID 数组。不同字段要共同满足；roles 数组内部则是任意一个角色命中即可。

账户条件尤其容易误解：

| match.accountId | 实际意义 |
| --- | --- |
| 省略或空值 | 只匹配规范化 ID 为 `default` 的账户 |
| default | 显式匹配规范化 ID 为 `default` 的账户 |
| work 等命名账户 | 匹配指定账户 |
| * | 在该渠道内跨账户匹配 |

这里的 `default` 是路由层固定的账户 ID，不会随渠道的 `defaultAccount` 自动改成另一个命名账户；后者由渠道适配器解析。因此 `{ channel: "WeChat" }` 不是“所有 WeChat Bot”的同义配置。

`resolveAgentRoute(input)` 接收配置、channel/account、peer/parentPeer，以及 guild/team/roles。这些来源值由渠道插件提供：

~~~ts
export function resolveAgentRoute(input: ResolveAgentRouteInput): ResolvedAgentRoute {
  const channel = normalizeToken(input.channel);
  const accountId = normalizeAccountId(input.accountId);
  const peer = input.peer
    ? {
        kind: normalizeChatType(input.peer.kind) ?? input.peer.kind,
        id: normalizeId(input.peer.id),
      }
    : null;
  const guildId = normalizeId(input.guildId);
  const teamId = normalizeId(input.teamId);
  const memberRoleIds = input.memberRoleIds ?? [];
  const memberRoleIdSet = new Set(memberRoleIds);
  const dmScope = input.cfg.session?.dmScope ?? "main";
  const identityLinks = input.cfg.session?.identityLinks;
  const shouldLogDebug = shouldLogVerbose();
  const parentPeer = input.parentPeer
    ? {
        kind: normalizeChatType(input.parentPeer.kind) ?? input.parentPeer.kind,
        id: normalizeId(input.parentPeer.id),
      }
    : null;
~~~

预处理先规范 channel 和 accountId，再整理 peer 与上级范围字段，角色转成 Set。Binding 比较阶段主要对 peer ID 做字符串规范与 trim；最终 Session Key 的小写化在后续阶段处理。

在 Alice 的调用中，规范化后的 channel、accountId 和 peer 仍分别为 WeChat、default、direct:101；没有父级、服务器、团队或角色。函数接着取得渠道/账户候选及其分类索引。进入候选集合的群规则仍需通过 peer 条件检查。 索引如何避免反复扫描所有规则，放到第 3.7 节。

### 3.4 八层匹配：层级顺序与同级 find

真实源码按以下次序匹配：

| 优先级 | matchedBy | 本层条件 |
| --- | --- | --- |
| 1 | binding.peer | 当前 peer 精确匹配 |
| 2 | binding.peer.parent | parentPeer 精确匹配 |
| 3 | binding.peer.wildcard | 当前 peer kind 的 id 通配 |
| 4 | binding.guild+roles | guild 与至少一个成员角色共同满足 |
| 5 | binding.guild | 有 guild、没有 roles 约束 |
| 6 | binding.team | team 约束 |
| 7 | binding.account | accountPattern 非 *，含缺省 default |
| 8 | binding.channel | accountPattern 为 * 的渠道兜底 |
| 后备 | default | 默认 Agent |

本地 Multi-Agent 文档的优先级概括漏列了 peer wildcard；应以实际 tiers 为准。前三层原代码如下：

~~~ts
{
  matchedBy: "binding.peer",
  enabled: Boolean(peer),
  scopePeer: peer,
  candidates: collectPeerIndexedBindings(bindingsIndex, peer),
  predicate: (candidate) => candidate.match.peer.state === "valid",
},
{
  matchedBy: "binding.peer.parent",
  enabled: Boolean(parentPeer && parentPeer.id),
  scopePeer: parentPeer && parentPeer.id ? parentPeer : null,
  candidates: collectPeerIndexedBindings(bindingsIndex, parentPeer),
  predicate: (candidate) => candidate.match.peer.state === "valid",
},
{
  matchedBy: "binding.peer.wildcard",
  enabled: Boolean(peer),
  scopePeer: peer,
  candidates: bindingsIndex.byPeerWildcard,
  predicate: (candidate) => candidate.match.peer.state === "wildcard-kind",
},
~~~

父级匹配改变的是检查 Binding 时使用的 `scopePeer`。例如线程没有专属 Binding，但父频道有，就可以继承父频道的 Agent；这不代表线程历史一定与父频道共用。

最终选择循环：

~~~ts
for (const tier of tiers) {
  if (!tier.enabled) {
    continue;
  }
  const matched = tier.candidates.find(
    (candidate) =>
      tier.predicate(candidate) &&
      matchesBindingScope(candidate.match, {
        ...baseScope,
        peer: tier.scopePeer,
      }),
  );
  if (matched) {
    if (shouldLogDebug) {
      logDebug(`[routing] match: matchedBy=${tier.matchedBy} agentId=${matched.binding.agentId}`);
    }
    return choose(matched.binding.agentId, tier.matchedBy);
  }
}

return choose(resolveDefaultAgentId(input.cfg), "default");
~~~

外层 for 决定层级优先级，内层 find 决定同级配置顺序。**跨层时，数组后面的精确 peer 规则也能压过前面的渠道兜底；同层时，第一个满足所有条件的规则生效。** 同层 peer 规则即使分别使用通配账户与精确账户，也仍按配置顺序选择。

每层候选仍需通过完整的条件检查：

~~~ts
function matchesBindingScope(match: NormalizedBindingMatch, scope: BindingScope): boolean {
  if (match.peer.state === "invalid") {
    return false;
  }
  if (match.peer.state === "valid") {
    if (
      !scope.peer ||
      !peerKindMatches(match.peer.kind, scope.peer.kind) ||
      scope.peer.id !== match.peer.id
    ) {
      return false;
    }
  }
  if (match.peer.state === "wildcard-kind") {
    if (!scope.peer || !peerKindMatches(match.peer.kind, scope.peer.kind)) {
      return false;
    }
  }
  return routeBindingScopeMatches(match, scope);
}
~~~

无效 peer 规则直接匹配失败。精确 peer 检查 kind 与 ID，wildcard 检查 kind，然后继续检查 guild、team、roles。当前 `peerKindMatches` 还允许 group/channel 兼容，direct 不属于这一兼容范围。

角色数组内部用 some：

~~~ts
function hasAnyRouteBindingRole(
  roles: readonly string[],
  memberRoleIds: Iterable<string> | null | undefined,
): boolean {
  if (!memberRoleIds) {
    return false;
  }
  if (hasRoleLookup(memberRoleIds)) {
    return roles.some((role) => memberRoleIds.has(role));
  }
  const memberRoleIdSet = new Set(memberRoleIds);
  return roles.some((role) => memberRoleIdSet.has(role));
}
~~~

上层范围检查还会分别检查 guild 与 team，再调用角色匹配：

~~~ts
export function routeBindingScopeMatches(
  constraint: RouteBindingScopeConstraint,
  scope: RouteBindingScope,
): boolean {
  const guildId = normalizeRouteBindingId(scope.guildId);
  const teamId = normalizeRouteBindingId(scope.teamId);
  const groupSpace = normalizeRouteBindingId(scope.groupSpace);
  if (!scopeIdMatches({ constraint: constraint.guildId, exact: guildId, groupSpace })) {
    return false;
  }
  if (!scopeIdMatches({ constraint: constraint.teamId, exact: teamId, groupSpace })) {
    return false;
  }

  const roles = normalizeRouteBindingRoles(constraint.roles);
  if (!roles) {
    return true;
  }
  return hasAnyRouteBindingRole(roles, scope.memberRoleIds);
}
~~~

所以 `roles: ["role-dev", "role-admin"]` 只要求命中其中一个；但同条规则的 guild、team、peer 等已配置约束仍需同时满足。这些条件的判断依赖渠道调用者提供相应数据。

把这段代码代回 Alice：peer 层没有通过的群候选，最终走到 binding.channel。代回群 -100700：peer 层的 find 得到 coding 规则，立即 return choose，不再访问后面的渠道层。优先级来自 tiers 的固定次序，同级选择来自 find；匹配过程不计算字段数量或得分。

### 3.5 choose 把 Agent 选择变成完整路由结果

命中后，局部函数 choose 先用 `pickFirstExistingAgentId` 检查 Agent ID，再生成 Session 地址：

~~~ts
const choose = (agentId: string, matchedBy: ResolvedAgentRoute["matchedBy"]) => {
  const resolvedAgentId = pickFirstExistingAgentId(input.cfg, agentId);
  const sessionKey = normalizeLowercaseStringOrEmpty(
    buildAgentSessionKey({
      agentId: resolvedAgentId,
      channel,
      accountId,
      peer,
      dmScope,
      identityLinks,
    }),
  );
  const mainSessionKey = normalizeLowercaseStringOrEmpty(
    buildAgentMainSessionKey({
      agentId: resolvedAgentId,
      mainKey: DEFAULT_MAIN_KEY,
    }),
  );
  const route = {
    agentId: resolvedAgentId,
    channel,
    accountId,
    sessionKey,
    mainSessionKey,
    lastRoutePolicy: deriveLastRoutePolicy({ sessionKey, mainSessionKey }),
    matchedBy,
  };
  if (routeCache && routeCacheKey) {
    routeCache.set(routeCacheKey, route);
    if (routeCache.size > MAX_RESOLVED_ROUTE_CACHE_KEYS) {
      routeCache.clear();
      routeCache.set(routeCacheKey, route);
    }
  }
  return route;
};
~~~

显式 Agent 列表非空时，Binding 指向未知 agentId 会回退到默认 Agent。

| 返回字段 | 作用 |
| --- | --- |
| agentId | 解析该 Agent 的模型、目录与策略 |
| channel / accountId | 归一化来源 |
| sessionKey | 此阶段生成的逻辑会话地址 |
| mainSessionKey | 该 Agent 的主会话地址 |
| lastRoutePolicy | 表达 main 或 session 的最近投递路由更新范围 |
| matchedBy | 说明哪层规则命中 |

此时返回的是路由数据，历史加载和 Pi AgentSession 创建在后续执行阶段进行。这里的 mainSessionKey 使用 `DEFAULT_MAIN_KEY`，未读取 `cfg.session.mainKey`；Session 初始化随后还会进行主别名规范化。

对 Alice，choose 返回的主要字段由上述代码推导为：

~~~json
{
  "agentId": "main",
  "channel": "WeChat",
  "accountId": "default",
  "sessionKey": "agent:main:WeChat:direct:101",
  "mainSessionKey": "agent:main:main",
  "lastRoutePolicy": "session",
  "matchedBy": "binding.channel"
}
~~~

choose 内部已经调用 Key builder，所以 Session Key 在路由返回时便存在；第 4 节将单独展开这一步的字符串生成。current Key 与 mainSessionKey 不相等，lastRoutePolicy 为 session。对群请求，agentId 和 Session Key 则分别变为 coding 与 `agent:coding:WeChat:group:-100700`。

### 3.6 扩展条件与同级冲突：临时加入 Discord 规则

本小节只在基准配置之外加入一个 Discord 账户 work 及以下三条路由规则，WeChat 规则保持不变。假设该账户已经接入并通过访问检查；这三条规则用于观察同级顺序，读完后回到 WeChat 基准场景。

~~~json5
[
  { agentId: "main", match: { channel: "discord", accountId: "work" } },
  {
    agentId: "coding",
    match: {
      channel: "discord", accountId: "work",
      peer: { kind: "channel", id: "9001" },
    },
  },
  {
    agentId: "main",
    match: {
      channel: "discord", accountId: "work",
      peer: { kind: "channel", id: "9001" },
    },
  },
]
~~~

频道 9001 同时满足后两条精确 peer 规则。它们处在同一层，find 按原配置顺序选择先出现的 coding；前面的账户兜底优先级较低。换成频道 9002，两个 peer 都失败，才命中 main 的账户规则。换成 accountId=personal，则这三条 work 规则在候选阶段就被排除。

guildId、teamId、roles 参与的是同一个匹配器。比如给一条规则同时配置 guildId 与 roles:["role-dev","role-admin"]，消息必须属于该 guild，且成员拥有至少一个列出的角色；若同时配置 peer，还必须满足 peer。先前的精确 peer、父 peer 和 peer 通配层仍早于 guild+roles 层。平台未提供对应字段时，相应约束就无法满足。

### 3.7 进阶：规则很多时，如何减少重复匹配

匹配语义确定以后，再看性能问题：若同一 Bot 不断收到消息，反复解析相同规则、遍历所有渠道没有必要。

`getEvaluatedBindingsForChannelAccount` 按渠道和账户缩小候选，`getEvaluatedBindingIndexForChannelAccount` 再提供 peer、guild、team 等索引。`buildEvaluatedBindingsByChannel` 保存原配置顺序，`mergeEvaluatedBindingsInSourceOrder` 按该顺序合并精确账户桶和通配账户桶。因此，索引缩小了搜索范围，同时保留原有匹配语义。

分类索引保留了规则层级与候选顺序：

~~~ts
type EvaluatedBindingsIndex = {
  byPeer: Map<string, EvaluatedBinding[]>;
  byPeerWildcard: EvaluatedBinding[];
  byGuildWithRoles: Map<string, EvaluatedBinding[]>;
  byGuild: Map<string, EvaluatedBinding[]>;
  byTeam: Map<string, EvaluatedBinding[]>;
  byAccount: EvaluatedBinding[];
  byChannel: EvaluatedBinding[];
};
~~~

byGuildWithRoles、byGuild、byTeam 按范围 ID 查找候选数组；byPeer 的键还包含聊天类型，例如 `group:-100700`。`peerLookupKeys` 同时考虑 group/channel 的兼容键，`collectPeerIndexedBindings` 再合并并去重。byPeerWildcard、byAccount、byChannel 保存相应类别的候选数组。Alice 的检查只涉及 WeChat/default 相关规则；条目中的 order 保留原配置顺序，所以索引不会改变同级第一条获胜的语义。

这些结果围绕配置对象缓存在进程内。最终 route cache 的键包含渠道、账户、peer/parent、guild/team、角色与 dmScope 等影响结果的维度；有 identityLinks 或详细调试日志时，当前函数跳过最终结果缓存。缓存让同样的判断更快，不负责创建 Session，也不保存聊天历史。

## 4. Session Key：同一个 Agent 怎样区分 Alice 与 Bob

### 4.1 先把 Alice 的输入拼成一个具体地址

Binding 已选择 main。把同一组来源字段交给 Session Key builder：

~~~text
输入：
  agentId  = "main"
  channel  = "WeChat"
  accountId = "default"
  peer.kind = "direct"
  peer.id   = "101"
  dmScope   = "per-channel-peer"

输出：
  agent:main:WeChat:direct:101
~~~

这个字符串的每一段都有来源：

| 结果中的部分 | 来源 | 作用 |
| --- | --- | --- |
| agent | 构造器写入的固定前缀 | 标明 Agent 作用域 Key |
| main | Binding 选出的 agentId | 指向 main Agent |
| WeChat | 接入插件提供的 channel | 区分渠道 |
| direct | peer.kind 进入私聊分支 | 标明私聊 |
| 101 | WeChat from.id 经插件构造的 peer.id | 区分 Alice |

accountId 已用于筛选 Binding，但 `per-channel-peer` 的模板没有它，所以 default 不出现在结果里。同一个字段可以参与前一个判断，却不出现在后一个地址中。

现在再让 Bob 用同一个 Bot 发私聊：前四段不变，末段从 101 变成 202。coding 群请求则连 Agent、聊天类型和 peer 都改变。这已经给出了多 Session 隔离的具体依据，不需要为每个用户再启动一个 Gateway。

### 4.2 对照 buildAgentPeerSessionKey 的执行分支

路由中的 `buildAgentSessionKey` 是参数转接包装，随后进入 `buildAgentPeerSessionKey`。只有 direct 分支使用 dmScope：

~~~ts
const peerKind = params.peerKind ?? "direct";
if (peerKind === "direct") {
  const dmScope = params.dmScope ?? "main";
  let peerId = (params.peerId ?? "").trim();
  const linkedPeerId =
    dmScope === "main"
      ? null
      : resolveLinkedPeerId({
          identityLinks: params.identityLinks,
          channel: params.channel,
          peerId,
        });
  if (linkedPeerId) {
    peerId = linkedPeerId;
  }
  peerId = normalizeLowercaseStringOrEmpty(peerId);
  if (dmScope === "per-account-channel-peer" && peerId) {
    const channel = normalizeLowercaseStringOrEmpty(params.channel) || "unknown";
    const accountId = normalizeAccountId(params.accountId);
    return `agent:${normalizeAgentId(params.agentId)}:${channel}:${accountId}:direct:${peerId}`;
  }
  if (dmScope === "per-channel-peer" && peerId) {
    const channel = normalizeLowercaseStringOrEmpty(params.channel) || "unknown";
    return `agent:${normalizeAgentId(params.agentId)}:${channel}:direct:${peerId}`;
  }
  if (dmScope === "per-peer" && peerId) {
    return `agent:${normalizeAgentId(params.agentId)}:direct:${peerId}`;
  }
  return buildAgentMainSessionKey({
    agentId: params.agentId,
    mainKey: params.mainKey,
  });
}
~~~

执行顺序是：确定 dmScope → 取 peerId → 非 main 模式尝试身份关联 → 规范化 peerId → 按模式拼接字段。底层函数在隔离模式缺少有效 peerId 时会回退主会话；正常 route wrapper 则会先为某些缺失 ID 填入 unknown，因此两种入口的缺值结果可能不同。

代入 Alice 的值，peerKind 为 direct，dmScope 不是 main；基准配置没有 identityLinks，所以 peerId 保持 "101"。per-account-channel-peer 分支不满足，随后 per-channel-peer 分支满足，直接返回 `agent:main:WeChat:direct:101`。return 之后不会继续落入 per-peer 或主会话后备分支。

路由包装函数 `buildAgentSessionKey` 负责把 peer.kind/id 转成底层的 peerKind/peerId 参数，并传入 agentId、channel、accountId、dmScope 与 identityLinks。生成的 Key 随后进入 choose 构造的路由结果。

### 4.3 只改变 dmScope，Alice 与 Bob 的历史会怎样变化

本小节只临时改变 `session.dmScope`，两个 Agent、Bot、Binding 与 maxConcurrent=2 都保持不变。四种模式比较完毕后恢复 per-channel-peer。

仍使用 main、WeChat/default、Alice 101 与 Bob 202，四种结果为：

| dmScope | Alice 的 Key | Bob 的 Key | 区分字段 |
| --- | --- | --- | --- |
| main | `agent:main:main` | `agent:main:main` | Agent / 主 Key |
| per-peer | `agent:main:direct:101` | `agent:main:direct:202` | Agent + peer |
| per-channel-peer | `agent:main:WeChat:direct:101` | `agent:main:WeChat:direct:202` | Agent + channel + peer |
| per-account-channel-peer | `agent:main:WeChat:default:direct:101` | `agent:main:WeChat:default:direct:202` | Agent + channel + account + peer |

per-channel-peer 隔离渠道但不隔离账户。同一用户同时使用两个 WeChat Bot，若都选择同一 Agent，仍可能共用 Key。per-account-channel-peer 才明确把账户加入私聊地址。

~~~ts
export function buildAgentMainSessionKey(params: {
  agentId: string;
  mainKey?: string | undefined;
}): string {
  const agentId = normalizeAgentId(params.agentId);
  const mainKey = normalizeMainKey(params.mainKey);
  return `agent:${agentId}:${mainKey}`;
}
~~~

Agent ID 与 mainKey 先规范化，缺省主 Key 为 main，因此 main Agent 的典型主会话地址是 `agent:main:main`。它没有 channel、account、sender 字段。

正常 Agent ID 会 trim、小写化，无效字符还有替换和长度限制。Key 是有约定格式的字符串，供 Store、运行登记和队列使用；不等于 Pi 对象地址，也不等于 transcript 文件名。

因此，只把 dmScope 改成 main 时，Alice 与 Bob 的来源 ID 仍然正确，Binding 也仍然选择 main；变化发生在地址拼接，二者都查 `sessions.json["agent:main:main"]`。如果 Alice 先留下私人信息，Bob 后来请求“继续”，两次 Pi 运行就可能读取同一段历史。

改回基准 per-channel-peer 后，Alice 查 direct:101，Bob 查 direct:202，分别得到各自 entry 与 transcript。把 maxConcurrent 改成 1 不能达到这个效果：串行执行仍然可以先后读写同一份历史。两人共享 main 的模型、工具和 Workspace，也不妨碍正常会话加载使用不同文件；其他文件访问和跨会话工具仍有各自的权限边界。

### 4.4 同一个 Alice 使用两个渠道：先看关联前后，再读映射代码

为本小节增加一个明确的扩展条件：Alice 还有 Discord 用户 ID `501`，她在 Discord default 账户中的私聊也被路由到 main。Carol 始终是 WeChat 用户 303。这里的两个平台 ID 不会因昵称相同而自动关联。

先保持基准 per-channel-peer、不配置 identityLinks，随后分别只改身份映射与 dmScope：

| 步骤与配置变化 | WeChat Alice 101 | Discord Alice 501 |
| --- | --- | --- |
| ① 无关联，per-channel-peer | `agent:main:WeChat:direct:101` | `agent:main:discord:direct:501` |
| ② 仅改为 per-peer，仍无关联 | `agent:main:direct:101` | `agent:main:direct:501` |
| ③ 保持 per-peer，加入下列 identityLinks | `agent:main:direct:alice` | `agent:main:direct:alice` |
| ④ 保留关联，dmScope 改回 per-channel-peer | `agent:main:WeChat:direct:alice` | `agent:main:discord:direct:alice` |

第 ③ 步配置变化为：

~~~json5
session: {
  dmScope: "per-peer",
  identityLinks: {
    alice: ["WeChat:101", "discord:501"],
  },
}
~~~

源码同时构造裸 peerId 与带 channel 前缀的候选，再按配置查找 canonical 名称：

~~~ts
const candidates = new Set<string>();
const rawCandidate = normalizeToken(peerId);
if (rawCandidate) {
  candidates.add(rawCandidate);
}
const channel = normalizeToken(params.channel);
if (channel) {
  const scopedCandidate = normalizeToken(`${channel}:${peerId}`);
  if (scopedCandidate) {
    candidates.add(scopedCandidate);
  }
}
if (candidates.size === 0) {
  return null;
}
for (const [canonical, ids] of Object.entries(identityLinks)) {
  const canonicalName = canonical.trim();
  if (!canonicalName) {
    continue;
  }
  if (!Array.isArray(ids)) {
    continue;
  }
  for (const id of ids) {
    const normalized = normalizeToken(id);
    if (normalized && candidates.has(normalized)) {
      return canonicalName;
    }
  }
}
~~~

对 WeChat 101，候选包含 "101" 与 "WeChat:101"，所以返回 canonical 名称 alice；对 Discord 501，命中 "discord:501"，同样返回 alice。builder 把这个名字作为新的 peerId，再按 dmScope 拼接。

第 ③ 步不保留渠道，两个 Key 才相同；第 ④ 步仍保留 WeChat/discord，所以即使末段相同也不合并。per-account-channel-peer 还会保留账户段，例如 `agent:main:WeChat:default:direct:alice`。main 模式则直接使用主会话，不查询 identityLinks。

裸 ID 也受支持，但不同平台碰巧相同的 ID 可能被错误合并；带渠道前缀能明确映射来源。身份映射只决定会话地址，不修改访问权限。**本节结束后撤去临时 identityLinks，回到基准 per-channel-peer**，因此后面的 Alice Key 仍以 101 结尾。

### 4.5 群聊、频道与线程：从同一套输入继续变化

非 direct 的 Key 不经过 dmScope：

~~~ts
  const channel = normalizeLowercaseStringOrEmpty(params.channel) || "unknown";
  const peerId = normalizeLowercaseStringOrEmpty(params.peerId) || "unknown";
  return `agent:${normalizeAgentId(params.agentId)}:${channel}:${peerKind}:${peerId}`;
}
~~~

基准配置中的 WeChat 群 -100700 路由到 coding，得到 `agent:coding:WeChat:group:-100700`；第 3.6 节临时扩展中的 Discord 频道 9001 路由到 coding，得到 `agent:coding:discord:channel:9001`。群内不同 SenderId 共用群 peer，因此共享群历史。

这个通用模板没有 accountId，因此不同账户的群或频道消息仍需按最终 Key 判断是否共享会话。`buildGroupHistoryKey` 虽然包含 accountId，但它用于群历史缓冲，与持久化 Session 使用不同的键。

线程 Key 的处理由平台插件决定。WeChat 群 topic 17 可得到 `agent:coding:WeChat:group:-100700:topic:17`。WeChat 私聊线程在基础 Key 后追加 `:thread:<threadId>`，调用处将 chatId 与 dmThreadId 组合，所以本章 per-channel-peer 模式下得到 `agent:main:WeChat:direct:101:thread:101:17`；若只把 dmScope 改为 main，才得到 `agent:main:main:thread:101:17`。Discord 线程通常用线程自身的频道 ID 作 peer，后续 `resolveThreadSessionKeys` 使用 `useSuffix: false`，不再套用 WeChat 后缀。

下图展示 Key 的生成分支：

~~~mermaid
flowchart TD
    P["agentId + channel + accountId + peer"] --> D{"direct?"}
    D -->|"是"| M{"dmScope"}
    M -->|"main"| A["agent:ID:main"]
    M -->|"其余模式"| I["identityLinks 可替换 peerId"]
    I -->|"per-peer"| B["agent:ID:direct:PEER"]
    I -->|"per-channel-peer"| C["agent:ID:CHANNEL:direct:PEER"]
    I -->|"per-account-channel-peer"| E["agent:ID:CHANNEL:ACCOUNT:direct:PEER"]
    D -->|"否"| G["agent:ID:CHANNEL:KIND:PEER"]
    A -->|"插件线程等后处理"| T["最终 MsgContext.SessionKey"]
    B -->|"保留隔离维度"| T
    C -->|"保留隔离维度"| T
    E -->|"保留隔离维度"| T
    G -->|"平台 topic / thread 规则"| T
~~~

两条消息是否共享逻辑历史，由最终 Key 是否相同决定。Key 确定之后，下一步才是查它当前对应哪一个会话实例。

### 4.6 进阶：为什么插件返回的最终 Key 还要再确认

WeChat 通过 `msg.from.id` 等字段构造 direct peer；缺少 senderId 时才回退 chatId。群 topic 使用 `群ID:topic:话题ID` 作为当前 peer，并传父群 peer。Discord 使用 author.id 构造私聊 peer，普通服务器频道和线程则使用相应 conversationId；成员角色和 guild 从平台事件上下文取得。

WeChat 的 route 之后还可能受到 topic Agent 配置、ACP 或运行时 conversation binding 的影响。本章普通示例假设没有这些覆盖。

当前 WeChat 还有专门保护：非默认命名账户若仅命中 default 后备路由，普通私聊的最终基础 Key 强制使用 per-account-channel-peer；群消息则要求明确匹配，否则拒收。这里的默认账户由 WeChat 账户配置解析，未必永远叫 default。

第 4.3 节的默认私聊混用案例采用“默认 Bot、普通私聊、无线程后缀”的前提。其他插件路径可能继续修改 route 中的 Key，历史查找应使用后处理完成的最终值。

## 5. Alice 连续三次请求：创建、复用，再切换到新实例

### 5.1 先看三次请求中什么变、什么不变

回到基准配置：没有 identityLinks，dmScope 为 per-channel-peer。Alice 顺序发送：

~~~text
第一次：你好，我想讨论一个 TypeScript 项目。
第二次：继续刚才的话题。
第三次：/new
~~~

假设前一次已经正常完成，三次发生在同一个有效会话周期内。/new 是通过普通消息文本进入的已授权命令；本例不取 native command、ACP、soft reset 或插件提前返回的分支，Workspace 已完成初始设置。模型回答的措辞不属于源码确定结果。

定义三个贯穿后文的值：

~~~text
K  = agent:main:WeChat:direct:101
S1 = 7e1520f2-6177-4a98-8a4e-68245ac79417
S2 = 8f263103-7288-4ba9-9b5f-79356bd8a528
~~~

K 是逻辑对话的地址，S1/S2 是假设随机生成的实例 ID。sessions.json 用 K 查找当前 SessionEntry，entry 再保存 sessionId 与 sessionFile。

| 时刻 | sessions.json 中 K 的状态 | Pi 读写的历史 |
| --- | --- | --- |
| 第一条接收前 | 本例假设没有 K | 尚无 S1 历史 |
| 第一条准备并执行 | 登记 S1，补全 S1.jsonl 路径 | 新文件中形成第一轮记录 |
| 第二条准备并执行 | K 仍指向 S1，活动时间更新 | 打开 S1.jsonl，恢复第一轮后继续 |
| 第三条普通 /new | K 改指 S2，解析 S2.jsonl | 旧 S1 文件归档，新实例执行启动输入 |

下面展示同一个 K 在三次请求中的映射变化：

~~~mermaid
flowchart LR
    A["第一次：K 原先不存在"] -->|"登记来源并准备文件路径"| B["K → S1"]
    B -->|"第二次：未过期，复用 ID"| C["K → S1"]
    C -->|"第三次：已授权 /new"| D["K → S2"]
    C -->|"旧文件归档"| O["S1.jsonl.reset.时间戳"]
    D -->|"新启动输入与回复"| N["S2.jsonl"]
~~~

### 5.2 第一次：先登记元数据，再准备 Pi 文件

第一条消息的 Binding 结果仍是 main / binding.channel，Key 为 K。源头字段和第 1 节一致，回复目标仍是 WeChat:101。

WeChat 插件在进入 `getReplyFromConfig` 之前调用 `recordInboundSession`，普通私聊会请求更新当前 K 的投递位置：

~~~text
buildWeChatMessageContext(...)
  → await buildWeChatInboundContextPayload(...)
      → await recordInboundSession({ sessionKey: K, updateLastRoute: ... })
          → 发起 recordSessionMetaFromInbound(...)
          → await updateLastRoute({ sessionKey: K, ... })
  ← 完成该私聊的投递路由登记
  → 随后进入 getReplyFromConfig → initSessionState
~~~

recordSessionMetaFromInbound 本身是发起后挂 catch 的异步调用；但本例还会等待 updateLastRoute。两条写入路径都能为缺失 Key 创建元数据 entry，更新同一 Store 时使用相应写入协调。

创建或合并条目时，`mergeSessionEntryWithPolicy` 内部选择实例 ID 的语句为：

~~~ts
const sessionId = patch.sessionId ?? existing?.sessionId ?? crypto.randomUUID();
const updatedAt = resolveMergedUpdatedAt(existing, patch, options);
if (!existing) {
  return normalizeSessionRuntimeModelFields({ ...patch, sessionId, updatedAt });
}
~~~

patch 没指定 ID，旧 entry 又不存在，才生成 UUID。本例假设得到 S1。接入记录此时可能已经保存来源、deliveryContext、lastChannel、lastTo 和 lastAccountId；此时登记的只是元数据，Pi 聊天历史尚未创建。在正常完成本次接入记录后，进入 initSessionState 时通常已经能查到这个只有元数据的 entry。

现在已经有 `ctx.SessionKey`，但它只是地址。普通回复入口 `getReplyFromConfig` 会等待 `initSessionState` 返回会话状态：

~~~ts
const commandAuthorized = finalized.CommandAuthorized;
const sessionState = useFastTestBootstrap
  ? initFastReplySessionState({
      ctx: finalized,
      cfg,
      agentId,
      commandAuthorized,
      workspaceDir,
    })
  : await initSessionState({
      ctx: finalized,
      cfg,
      commandAuthorized,
    });
~~~

初始化的主要数据路线是：

~~~text
ctx.SessionKey
  → resolveSessionAgentId(...) 选择 Agent 作用域
  → resolveStorePath(session.store, { agentId })
  → loadSessionStore(storePath, { skipCache: true })
  → 检查命令授权并识别重置指令
  → resolveSessionKey(...) + canonicalizeMainSessionAlias(...)
  → sessionStore[sessionKey]
  → 解析过期策略并判断 freshness
  → 复用 sessionId 或生成 UUID
  → resolveAndPersistSessionFile(...)
  → updateSessionStore(...)
  → 按需归档旧 transcript
  → 返回 sessionCtx / sessionEntry / sessionId / storePath 等
~~~

其中 `resolveSessionKey` 优先尊重已经存在的 SessionKey：

~~~ts
export function resolveSessionKey(scope: SessionScope, ctx: MsgContext, mainKey?: string) {
  const explicit = ctx.SessionKey?.trim();
  if (explicit) {
    return normalizeExplicitSessionKey(explicit, ctx);
  }
  const raw = deriveSessionKey(scope, ctx);
  if (scope === "global") {
    return raw;
  }
  const canonicalMainKey = normalizeMainKey(mainKey);
  const canonical = buildAgentMainSessionKey({
    agentId: DEFAULT_AGENT_ID,
    mainKey: canonicalMainKey,
  });
  const isGroup = raw.includes(":group:") || raw.includes(":channel:");
  if (!isGroup) {
    return canonical;
  }
  return `agent:${DEFAULT_AGENT_ID}:${raw}`;
}
~~~

已有 SessionKey 会保留路由阶段的选择；主别名规范化则将 main 等简写转换为实际默认 Agent 对应的规范地址。

`loadSessionStore` 返回一个进程内的 `Record<string, SessionEntry>`，来源是磁盘 JSON；初始化处使用 skipCache，避免沿用旧的会话实例映射。其中保存的是会话元数据，Pi AgentSession 对象由执行层另行创建。

在本例中，entry 已有 S1 和有效 updatedAt，因此初始化复用 S1；因为尚无 sessionFile，它为 S1 解析文件路径。即使 isNewSession 仍为 false，systemSent 尚未设置，`isFirstTurnInSession = isNewSession || !currentSystemSent` 仍会识别这是首轮。因此，isNewSession 一项不能单独表示“这是不是首次形成聊天历史”。

如果某个入口进入 initSessionState 时**确实仍找不到 K**，代码还有 `crypto.randomUUID()` 的通用创建分支；第 5.3 节的真实分支会同时展示它。这一分支适用于尚无元数据条目的入口；本例 WeChat 已先完成登记。

初始化会补全文件路径并更新 Store，主要字段可表示为下列快照。时间值只为展示前后变化，省略其他真实字段：

~~~json
{
  "agent:main:WeChat:direct:101": {
    "sessionId": "7e1520f2-6177-4a98-8a4e-68245ac79417",
    "updatedAt": 1791432000000,
    "sessionFile": "/home/student/.openclaw/agents/main/sessions/7e1520f2-6177-4a98-8a4e-68245ac79417.jsonl",
    "lastChannel": "WeChat",
    "lastTo": "WeChat:101",
    "lastAccountId": "default"
  }
}
~~~

这个对象保存实例与投递元数据，第一句话的聊天记录写入 JSONL。有效队列模式在执行准备阶段解析；全局 collect 配置不会自动成为 entry.queueMode，只有相应会话覆盖才可能持久化到该字段。

真正进入 Pi 的时机还在后面：Alice 通过 Session Lane 和 main Global Lane 后，attempt 才打开 sessionFile、创建 AgentSession，并提交包含第一句话的输入。新文件的 header ID 会与 S1 对齐。Pi 的普通持久化路径在出现 assistant Entry 后满足首次 flush 条件，随后追加记录；所以“Store 已有路径”“manager 已打开”“聊天消息已写盘”并不是同一个时刻。

### 5.3 第二次：同一个 Key 怎样恢复第一轮历史

Alice 发送“继续刚才的话题”，from.id、chat.id、Bot 账户和 Binding 都没有变化，Key 仍是 K。来源更新继续保留 S1；它不会仅因又收到了平台消息就把旧实例换成新 ID。接入元数据更新对已有条目还会保留活动时间，以免绕过后面的 idle/daily 检查。

进入 initSessionState 后，按 K 找到第一轮留下的 SessionEntry：

~~~text
entry.sessionId   = S1
entry.sessionFile = /home/student/.openclaw/agents/main/sessions/7e1520f2-6177-4a98-8a4e-68245ac79417.jsonl
resetTriggered    = false
freshEntry        = true
~~~

它指向第 5.2 节同一文件。是否仍然 fresh、能否复用，由以下分支决定。

决定复用时，源码先检查 entry 是否有 sessionId、updatedAt 是否为有效数字，再检查 freshness：

~~~ts
const canReuseExistingEntry =
  Boolean(entry?.sessionId) &&
  typeof entry?.updatedAt === "number" &&
  Number.isFinite(entry.updatedAt);
// Forcing freshEntry=true prevents accidental data loss on automated system events.
const skipImplicitExpiry = hasProviderOwnedSession(entry) && resetPolicy.configured !== true;
const entryFreshness = entry
  ? isSystemEvent || skipImplicitExpiry
    ? ({ fresh: true } satisfies SessionFreshness)
    : evaluateSessionFreshness({ updatedAt: entry.updatedAt, now, policy: resetPolicy })
  : undefined;
~~~

随后，在没有明确要求新会话、条目新鲜且可复用时沿用旧 ID；否则生成 UUID。以下节选止于新建分支的初始字段赋值，后续偏好继承语句省略：

~~~ts
if (!isNewSession && freshEntry && canReuseExistingEntry) {
  sessionId = entry.sessionId;
  systemSent = entry.systemSent ?? false;
  abortedLastRun = entry.abortedLastRun ?? false;
  persistedThinking = entry.thinkingLevel;
  persistedVerbose = entry.verboseLevel;
  persistedTrace = entry.traceLevel;
  persistedReasoning = entry.reasoningLevel;
  persistedTtsAuto = entry.ttsAuto;
  persistedModelOverride = entry.modelOverride;
  persistedProviderOverride = entry.providerOverride;
  persistedModelOverrideSource = entry.modelOverrideSource;
  persistedAuthProfileOverride = entry.authProfileOverride;
  persistedAuthProfileOverrideSource = entry.authProfileOverrideSource;
  persistedAuthProfileOverrideCompactionCount = entry.authProfileOverrideCompactionCount;
  persistedLabel = entry.label;
} else {
  sessionId = crypto.randomUUID();
  isNewSession = true;
  systemSent = false;
  abortedLastRun = false;
~~~

这段分支的状态变化如下：

| initSessionState 查找 Store 时的状态 | 初始化结果 |
| --- | --- |
| 此时仍找不到 Key | 进入通用创建分支，生成新 UUID |
| Key 存在、未过期、未重置 | 复用 sessionId，更新元数据 |
| Key 存在，但已过期 | 逻辑 Key 不变，换实例 ID |
| 通过授权的一般 /new 或 /reset | 换实例 ID，并按规则保留部分用户偏好 |

这里复用的是持久化会话身份和历史。一次执行结束后，Pi 对象可以被 dispose；下次运行重新打开同一文件，仍然是在继续同一段历史。

对这次“继续”，判断条件全部满足，因此仍使用 S1，entry.updatedAt 随正常处理更新。把变化压缩为前后两项就是：

~~~text
处理前：K → { sessionId: S1, sessionFile: 原路径, updatedAt: T1 }
处理后：K → { sessionId: S1, sessionFile: 原路径, updatedAt: T2 }
~~~

第二次 Pi attempt 重新打开 S1.jsonl。SessionManager 根据当前 leaf 和 Entry 关系建立上下文，createAgentSession 将第一轮 user/assistant 消息恢复到 Agent 状态，再加入“继续刚才的话题”。第 6 节分析这一调用链。

### 5.4 第三次：/new 改变实例，保留逻辑地址

Alice 仍在同一个 WeChat 私聊发送 /new，Binding 和 dmScope 没变，逻辑 Key 仍为 K。授权通过后，初始化识别一般重置命令：

~~~ts
if (trimmedBodyLower === triggerLower || strippedForResetLower === triggerLower) {
  isNewSession = true;
  bodyStripped = "";
  resetTriggered = true;
  matchedResetTriggerLower = triggerLower;
  break;
}
~~~

空的 bodyStripped 表示命令没有尾随正文；resetTriggered 与 isNewSession 则使后面的分支创建新实例。本例假设新 UUID 是 S2。代码保存前一条 entry 以便处理旧文件，再更新 K 对应的 entry 和路径。

第三次初始化后的缩减快照为：

~~~json
{
  "agent:main:WeChat:direct:101": {
    "sessionId": "8f263103-7288-4ba9-9b5f-79356bd8a528",
    "updatedAt": 1791432120000,
    "sessionFile": "/home/student/.openclaw/agents/main/sessions/8f263103-7288-4ba9-9b5f-79356bd8a528.jsonl",
    "lastChannel": "WeChat",
    "lastTo": "WeChat:101",
    "lastAccountId": "default"
  }
}
~~~

与第一份快照相比，Key 和回复目标不变，sessionId、sessionFile、活动时间改变。旧 S1.jsonl 会尝试归档为 `7e1520f2-6177-4a98-8a4e-68245ac79417.jsonl.reset.<timestamp>`，而不是立即永久删除；S2 不再把旧两轮消息作为自己的当前分支历史恢复。

一般重置会保留部分用户选择，例如 thinking、verbose、reasoning、TTS 或模型相关覆盖，同时清除新实例不应继承的 token/压缩等计数。本例未设置这些覆盖，因此快照只展示实例与来源字段。/new 保留 Workspace 和长期记忆，新实例仍可使用这些上下文来源。

更新 Store 后，runPreparedReply 识别 bare reset，并用运行时生成的启动提示代替空正文：

~~~ts
const isBareNewOrReset = /^\/(new|reset)$/.test(normalizedCommandBody);
const isBareSessionReset =
  softResetTriggered ||
  (isNewSession &&
    ((baseBodyTrimmedRaw.length === 0 && rawBodyTrimmed.length > 0) || isBareNewOrReset));
~~~

随后 `resolveBareSessionResetPromptState` 产生相应提示，供后面的普通 Pi 运行使用。本例会创建 S2 的 AgentSession，并生成由模型决定措辞的启动/问候回复。执行正常完成后，S2.jsonl 记录启动输入与助手回复；若启动期间执行了工具，还会包含相应工具记录。启动文件的内容与加载机制留到下一章。

归档实现、/reset soft 与 Gateway RPC reset 的差异放在第 10.4 节；它们不改变这里已经看清的主线：**K 稳定指向当前实例，普通 /new 将这个指向从 S1 轮换到 S2。**

### 5.5 如果没有 /new，什么时候自动换实例

前三次请求假设处于同一有效周期。现在只考察会话时间，不修改基准配置：如果第二次“继续”隔了很久才到达，初始化会先检查 freshness，而不是无条件复用旧 ID。

本版缺省 reset 模式是 daily，小时是主机本地时间 04:00：

~~~ts
export const DEFAULT_RESET_MODE: SessionResetMode = "daily";
export const DEFAULT_RESET_AT_HOUR = 4;

export function resolveDailyResetAtMs(now: number, atHour: number): number {
  const normalizedAtHour = normalizeResetAtHour(atHour);
  const resetAt = new Date(now);
  resetAt.setHours(normalizedAtHour, 0, 0, 0);
  if (now < resetAt.getTime()) {
    resetAt.setDate(resetAt.getDate() - 1);
  }
  return resetAt.getTime();
}
~~~

`resolveDailyResetAtMs` 计算“截至现在，最近一个日重置边界”。现在若还没到今天 04:00，就退到昨天 04:00。该函数只计算时间边界，实例是否过期在处理新消息时判断。

是否过期由新消息处理时的比较决定：

~~~ts
export function evaluateSessionFreshness(params: {
  updatedAt: number;
  now: number;
  policy: SessionResetPolicy;
}): SessionFreshness {
  const dailyResetAt =
    params.policy.mode === "daily"
      ? resolveDailyResetAtMs(params.now, params.policy.atHour)
      : undefined;
  const idleExpiresAt =
    params.policy.idleMinutes != null && params.policy.idleMinutes > 0
      ? params.updatedAt + params.policy.idleMinutes * 60_000
      : undefined;
  const staleDaily = dailyResetAt != null && params.updatedAt < dailyResetAt;
  const staleIdle = idleExpiresAt != null && params.now > idleExpiresAt;
  return {
    fresh: !(staleDaily || staleIdle),
    dailyResetAt,
    idleExpiresAt,
  };
}
~~~

日过期条件是 updatedAt 早于最近 daily 边界；空闲过期条件是配置了正值 idleMinutes，且 now 严格晚于 updatedAt 加空闲时长。二者是“或”，任意满足就不再 fresh。

例如昨日 23:00 最后更新，今日 03:00 再发消息，仍在同一日边界之后；若直到今日 05:00 才来下一条，则 updatedAt 早于今日 04:00，这时才轮换实例。空闲 30 分钟与 daily 同时启用时，先满足哪一个就由哪一个使条目过期。

若要比较空闲重置，本小节临时在 session 下增加以下 reset 对象，其余配置不变：

~~~json5
{
  session: {
    reset: {
      mode: "daily",
      atHour: 4,
      idleMinutes: 30,
    },
  },
}
~~~

此外还有 resetByType 和 resetByChannel。解析时，渠道覆盖优先；否则查 direct/group/thread 类型设置，再回退普通 reset。旧 session.idleMinutes 有兼容路径；本地 DEFAULT_IDLE_MINUTES 为 0，不存在缺省“空闲 60 分钟重置”的设置。

自动系统事件有避免隐式过期的分支；某些由 provider 自己管理的 CLI 会话，在没有显式 reset 配置时也跳过默认过期。上述时间推导针对普通用户会话，这些跳过过期检查的分支有不同处理。

这项 reset 配置只用于本小节比较。后续回到基准配置：不显式设置 reset，采用默认 daily 行为，并假设示例请求之间未过期。

### 5.6 两类持久化数据如何分工

三次请求正常完成并归档成功后，本例的文件关系为：

~~~text
~/.openclaw/agents/main/sessions/
  sessions.json
  8f263103-7288-4ba9-9b5f-79356bd8a528.jsonl
  7e1520f2-6177-4a98-8a4e-68245ac79417.jsonl.reset.<timestamp>

sessions.json:
  sessionKey → SessionEntry
                 sessionId
                 updatedAt
                 sessionFile
                 来源 / 投递 / 模型 / 队列 / 使用量等元数据
~~~

前面的两份 JSON 是缩减快照。`SessionEntry` 除 ID 与路径外，还可能保存模型和认证选择、thinking/verbose/reasoning、queue mode/debounce/cap/drop、群组信息、origin、deliveryContext、最后投递位置、token 使用量等。user/assistant/toolResult 等消息则保存在 JSONL 中。

JSONL 则是底层 Pi 的会话记录：header 加逐条 Entry，包含消息与分支关系。OpenClaw 从 store 找到文件，Pi 才从该文件恢复当前分支上下文。

普通 transcript 默认叫 `<sessionId>.jsonl`，但并非所有路径都只有这个形式：

~~~ts
const safeSessionId = validateSessionId(sessionId);
const safeTopicId =
  typeof topicId === "string"
    ? encodeURIComponent(topicId)
    : typeof topicId === "number"
      ? String(topicId)
      : undefined;
const fileName =
  safeTopicId !== undefined
    ? `${safeSessionId}-topic-${safeTopicId}.jsonl`
    : `${safeSessionId}.jsonl`;
return resolvePathWithinSessionsDir(sessionsDir, fileName);
~~~

topic 形式可带额外后缀，已有 `sessionFile` 也会参与路径解析。自定义 `session.store` 支持 `{agentId}` 占位符。因此定位实际 transcript 应查 entry.sessionFile，而不是永远根据 UUID 猜文件名。

`resolveAndPersistSessionFile` 解析并保存文件路径；JSONL 的创建和聊天记录写入由后续 Pi 运行完成。

正常运行结束后的 token、模型和上下文报告更新也属于 Store 元数据，沿 `persistRunSessionUsage → persistSessionUsageUpdate → updateSessionStoreEntry` 写入；消息 Entry 则由 Pi manager 与 OpenClaw guard 追加到 JSONL。这解释了为什么只观察 sessions.json 不能重建完整对话。

同一个 K 可以跨越多次实例轮换；同一个 S1 可以接续多次 Run；每次 Run 又可能创建新的 AgentSession 对象。runId 用来关联单次运行的事件，不等于 sessionId，也不等于该 Run 内某一个模型 HTTP 请求。持久会话与内存对象的边界将在下一节对齐。

## 6. 用 Alice 的文件创建 Pi AgentSession，并恢复上下文

### 6.1 先把 OpenClaw 与 Pi 的对象对齐

| 层次 | 对象或数据 | 负责什么 |
| --- | --- | --- |
| OpenClaw 逻辑会话 | sessionKey | 路由、历史共享范围、并发作用域 |
| OpenClaw 会话索引 | SessionEntry / sessions.json | 当前实例 ID、文件路径、来源、设置、使用量 |
| Pi 单次执行会话 | AgentSession、Agent | prompt、steering、模型与工具运行协调 |
| Pi 持久历史 | SessionManager 管理的 Entry 树 / JSONL | 分支、parentId、leafId、恢复当前上下文 |

前文课程所说的 SessionTree 是由 Pi SessionManager 管理的 Entry 树；OpenClaw 的 Session Store 则是查找当前会话实例的另一层索引。

OpenClaw 增加了平台来源到逻辑会话的映射、重置策略、索引元数据、执行调度与投递目标管理。Pi 提供 AgentSession 的运行接口及 SessionManager 的树形记录、上下文重建等能力。

代入本章三次请求，OpenClaw 一直用 K 找 entry；前两次得到 S1，第三次得到 S2。Pi 则分别打开这些 ID 对应的实际文件，再创建当前 attempt 的 AgentSession。K 不会变成 Pi Entry 的 parentId，sessions.json 也不是 Pi 的 SessionTree。

### 6.2 sessionId、sessionFile 怎样从回复层传到 runner

`runPreparedReply` 构造的 followupRun 同时用于即时执行准备和可能的排队。其 run 子对象包含：

~~~text
agentId、agentDir、workspaceDir
sessionId、sessionKey、sessionFile
provider、model、authProfileId
messageProvider、agentAccountId、senderId 等来源与权限上下文
~~~

调用者进入 `runReplyAgent`，再进入 `runAgentTurnWithFallback`，在 embedded 分支把这些字段交给 `runEmbeddedPiAgent`。这一步传递的是 OpenClaw 已经选好的 Session 身份，Pi 不会重新执行 Binding。

执行层会先选择 harness。本章取 Pi 分支，调用与 Promise 返回关系为：

~~~text
runEmbeddedPiAgent(...)
  → runEmbeddedAttemptWithBackend(...)
      → runAgentHarnessAttemptWithFallback(...)
          → selectAgentHarness(...)
          → return harness.runAttempt(params)
              Pi harness 的 runAttempt 属性 = runEmbeddedAttempt
~~~

在 Pi harness 分支中，该 Promise 作为外层 async 函数的结果继续向上传递，调用者等待它完成。

因此，Alice 第二次“继续”进入 runner 时，关键参数仍指向：

~~~text
agentId      = main
sessionKey   = agent:main:WeChat:direct:101
sessionId    = 7e1520f2-6177-4a98-8a4e-68245ac79417
sessionFile  = /home/student/.openclaw/agents/main/sessions/7e1520f2-6177-4a98-8a4e-68245ac79417.jsonl
workspaceDir = /home/student/.openclaw/workspace
prompt       = 含“继续刚才的话题。”的预处理输入
~~~

最后一行列出 prompt 中的用户内容；外层还可能添加消息来源和运行上下文。

### 6.3 SessionManager 打开文件，createAgentSession 接收 manager

一次 Pi attempt 的顺序是：取得 transcript 写锁 → 修复/检查文件 → 打开并包装 SessionManager → 对齐新会话 header → 创建 AgentSession → 提交 prompt → 清理资源。

打开 manager 的关键位置：

~~~ts
await prewarmSessionFile(params.sessionFile);
sessionManager = guardSessionManager(SessionManager.open(params.sessionFile), {
  agentId: sessionAgentId,
  sessionKey: params.sessionKey,
  config: params.config,
  contextWindowTokens: params.contextTokenBudget,
  inputProvenance: params.inputProvenance,
  allowSyntheticToolResults: transcriptPolicy.allowSyntheticToolResults,
  allowedToolNames,
});
trackSessionManagerAccess(params.sessionFile);
~~~

`SessionManager.open(params.sessionFile)` 使用已解析的文件路径。外面的 `guardSessionManager` 给原有 manager 加入 OpenClaw 所需的消息、工具结果等保护，并保留底层 manager 的历史管理能力。

`prepareSessionManagerForRun` 在新文件时对齐 header.id、cwd 和内部 sessionId，使 Pi 的记录身份与 OpenClaw 选定的 S1/S2 一致。半成品文件的恢复分支留到第 10.3 节。

随后真正创建 Pi 会话：

~~~ts
const createdSession = await createEmbeddedAgentSessionWithResourceLoader<
  Awaited<ReturnType<typeof createAgentSession>>
>({
  createAgentSession: async (options) =>
    await createAgentSession(options as unknown as Parameters<typeof createAgentSession>[0]),
  options: {
    cwd: resolvedWorkspace,
    agentDir,
    authStorage: params.authStorage,
    modelRegistry: params.modelRegistry,
    model: params.model,
    thinkingLevel: mapThinkingLevel(params.thinkLevel),
    tools: sessionToolAllowlist,
    customTools: allCustomTools,
    sessionManager,
    settingsManager,
    resourceLoader,
  },
});
session = createdSession.session;
~~~

Pi 收到带有历史文件的 sessionManager，以及 cwd、agentDir、模型、认证、工具、settings、resourceLoader。`createEmbeddedAgentSessionWithResourceLoader` 再调用传入的 createAgentSession 函数。

OpenClaw 在此版本依赖的 pi-agent-core、pi-coding-agent 均为 0.69.0。相应 Pi 代码中，`createAgentSession` 使用传入 manager，调用 `buildSessionContext()`，并恢复 Agent 的消息状态。

历史恢复读的是 Entry 树的当前分支上下文，不是简单把所有 JSONL 行都原样加入模型请求。分支与压缩机制已在前章讲过；这里的关键是 OpenClaw 用正确文件把这些能力接到平台 Session 上。

Alice 第一次执行时，路径 S1.jsonl 尚无正常聊天历史；manager 初始化文件头，再由 prepareSessionManagerForRun 对齐到 S1。第二次执行时，路径已经存在，manager 从已有 Entry 恢复索引与当前分支。第三次 /new 则转到 S2.jsonl，不再以 S1 的两轮消息作为当前分支。

Pi SDK 中的恢复交接可以用两处短代码连接起来。第二处只节选存在历史时的分支开头，后续模型/思考设置恢复略去：

~~~ts
const existingSession = sessionManager.buildSessionContext();
// 检查整理出的消息列表里有没有消息：长度大于 0 就得到 true
const hasExistingSession = existingSession.messages.length > 0;
~~~

~~~ts
if (hasExistingSession) {
	// 有历史会话 → 放入第 4 步整理好的消息；若有压缩记录，则包含摘要和保留的消息
	agent.state.messages = existingSession.messages;
~~~

第一处从 SessionManager 取当前分支上下文，第二处在存在历史时把 messages 放入新 Agent 的状态。第二次“继续”据此取得第一轮历史。

### 6.4 prompt 开始本次执行，完成后释放本次对象

在普通输入准备好后，attempt 调用 activeSession.prompt。图片存在与否只影响附加参数；本章文本例进入不带图片的分支：

~~~ts
// Only pass images option if there are actually images to pass
// This avoids potential issues with models that don't expect the images parameter
if (imageResult.images.length > 0) {
  await abortable(
    activeSession.prompt(effectivePrompt, { images: imageResult.images }),
  );
} else {
  await abortable(activeSession.prompt(effectivePrompt));
}
~~~

外层 abortable 将这次等待与取消控制关联。Pi 用恢复出的历史和本次输入继续 Agent Loop，消息记录按自身的持久化规则进入 JSONL。

执行收尾还会 dispose AgentSession，并释放本次持有的资源。后续继续同一实例时，会再次打开该实例对应的文件，并可以创建新的内存对象；持久历史并不随 dispose 消失。prompt 的完成、补写处理和最终锁释放也不是同一边界；第 10.3 节保留这部分真实清理代码。

K 指向 entry，entry 选定文件，manager 恢复历史，AgentSession 再接收本次 prompt。多个请求同时进入 runner 时，还需要执行队列决定哪些请求可以开始。

## 7. Alice、Bob、Carol 同时发消息：先看时间线，再拆两级队列

### 7.1 哪些输入在等，哪些运行可以开始

沿用第 1.4 节：Alice 101 的 A1 正在执行；她补充 A2，Bob 202 发 B1，Carol 303 发 C1。三个私聊 Key 分别以 direct:101、direct:202、direct:303 结尾。maxConcurrent 仍为 2、queue mode 仍为 collect；这一节没有改配置。本节发生在第 5 节 /new 之后，Alice 当前实例为 S2；A1/A2 是这次并发练习的输入编号，不是前三次顺序请求的编号。

| 时刻 | 事件 | Session Lane | main Global Lane | 消息 followup 队列 |
| --- | --- | --- | --- | --- |
| t0 | A1 开始 | Alice 占用 | A1 占第 1 槽 | 空 |
| t1 | A2 到达 | A1 仍占用 | 不新增 A2 执行 task | Alice 队列放 A2 |
| t2 | B1 到达 | Bob 占用 | B1 占第 2 槽 | Alice 保留 A2 |
| t3 | C1 到达 | Carol 已占用 | C1 在 main 等待 | 不变 |
| t4 | B1 的全局 task 完成 | Bob 外层随后释放 | pump 启动 C1 | 不变 |
| t5 | A1 执行返回并进入回复收尾 | Alice 的执行槽释放 | A1 的槽释放 | 启动 Alice drain |
| t6 | debounce 满足 | A2 新 Run 申请 Alice lane | 有额度即执行，否则继续等 | 回调完成后移除 A2 |

表中 t4 的“完成”指释放 main task 的执行边界，不承诺 Bob 的所有平台发送都已完成。主队列的 pump 会在该 task 完成时启动下一项，不需要等手机显示已读。

下图按作用域组织行为时序，具体函数调用在后文展开。Session Lane、main Lane 是执行队列作用域，Followup 是另一套消息队列，启动 drain 和等待后续回复回调的工作由回复运行层完成。

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant R as 回复运行层
    participant F as Alice Followup
    participant AL as Alice Session Lane
    participant G as main Lane 容量2
    participant B as Bob Session Lane
    participant C as Carol Session Lane
    A->>R: A1 新输入
    R->>AL: 申请会话执行槽
    AL->>G: 申请全局槽
    G-->>AL: A1 开始执行
    A->>R: A2，当前会话 active
    R->>F: 保存 prompt 与原始回复目标
    B->>G: B1，Bob Session 槽已取得
    G-->>B: B1 开始执行
    C->>G: C1，Carol Session 槽已取得
    Note over C,G: 全局已满，C1 等待
    B-->>G: B1 task 完成
    G-->>C: pump 启动 C1
    AL-->>G: A1 task 完成
    AL-->>R: 外层执行 Promise 随后完成
    R->>F: A1 回复收尾，启动 drain
    Note over F: 等待距最后入队的安静窗口
    F->>R: 调用 followup runner
    R->>AL: 为 A2 申请 Session Lane
    AL->>G: 再申请全局槽
    G-->>AL: 有空位则执行 A2
    AL-->>R: 执行结果返回
    R-->>F: followup 回调 fulfilled
    Note over F: 移除已处理条目
~~~

A2 在 t1 尚未成为第二个执行 task，正是两套队列区别最直观的地方。如果 Alice 在安静窗口内又发 A3，collect 可以把 A2/A3 拼成一个 followup Run；若来源或授权上下文不同，则分开处理。

在上述 t3，正常默认路径可以同时出现：

~~~text
Alice followup queue:
  items = [A2]

Alice Session Lane:
  active = 1       // A1
  waiting = 0      // A2 还不是这个队列里的任务

Bob Session Lane:
  active = 1       // B1

Carol Session Lane:
  active = 1       // 外层 task 正等待 main Promise

main Global Lane:
  active = 2       // A1、B1
  waiting = [C1]
~~~

Carol 的 Session lane 已处于 active，但内层任务仍在等待 main 额度；Alice 的 followup 队列只保存新输入，尚未占用第二个 main 槽。日志中的 busy、queue size、streaming 因而需要结合所属模块解释。

这组状态提出两个不同的等待原因：A2 等 Alice 当前运行收尾，C1 等全局执行额度。它们会在不同队列中出现。下面先分析决定运行开始时间的 Command Queue，第 8 节再解释 A2 怎样被保留、合并和形成新 Run。

### 7.2 为什么同 Session 串行，不同 Session 可以并行

同一 Session 的两次运行都可能读取相同历史、追加用户和助手消息、写入工具结果、更新分支位置。如果没有执行级协调，它们可能各自从旧状态出发，最后形成相互交错的消息顺序或覆盖式修改。文件锁能限制文件写入，却不能独自表达“第二个请求应该接在第一个完整运行之后”。

另一方面，Alice 的 Session 正在等模型网络响应时，Bob 的独立 Session 不必停住。但若所有独立 Session 都无限并行，模型请求、文件工具和外部服务可能同时承受过多工作。所以代码分两级安排：同一逻辑 Session 串行；不同 Session 再共同竞争某个全局 lane 的额度。

这里的“全局”指进程中共享的命名 lane。普通运行默认使用 main；cron、subagent 等另有 lane，分别设置容量。

### 7.3 两个额度在哪里设置

新建、尚未配置的 lane 缺省容量是 1，所以 Session Lane 自然串行。Gateway 启动时会给 main、cron、subagent 设置各自容量：

~~~ts
export function applyGatewayLaneConcurrency(cfg: OpenClawConfig) {
  setCommandLaneConcurrency(CommandLane.Cron, cfg.cron?.maxConcurrentRuns ?? 1);
  setCommandLaneConcurrency(CommandLane.Main, resolveAgentMaxConcurrent(cfg));
  setCommandLaneConcurrency(CommandLane.Subagent, resolveSubagentMaxConcurrent(cfg));
}
~~~

`resolveAgentMaxConcurrent` 读取 `agents.defaults.maxConcurrent`，缺省为 4。配置重载也会更新 lane 容量。

因此，第 1 节设置 maxConcurrent: 2 后，main 与 coding 的普通 embedded 运行共同使用 main 的两个槽，不是每个 Agent 各有两个。即使当前有十个独立 Session，最多两个这种运行进入该全局 lane 的实际 task，其余各自在等待。

容量调整会触发 drain，但降低上限不是强杀已经启动的任务。现有任务完成后，调度器依据新的 active 数与上限决定能否补入下一项。

### 7.4 先进入 Session Lane，再进入 Global Lane

`runEmbeddedPiAgent` 先补全有效 Session Key，然后确定两个 lane：

~~~ts
const sessionLane = resolveSessionLane(params.sessionKey?.trim() || params.sessionId);
const globalLane = resolveGlobalLane(params.lane);
const enqueueGlobal =
  params.enqueue ?? ((task, opts) => enqueueCommandInLane(globalLane, task, opts));
const enqueueSession =
  params.enqueue ?? ((task, opts) => enqueueCommandInLane(sessionLane, task, opts));
~~~

普通路径使用 `enqueueCommandInLane`，但参数中允许注入 enqueue 替代实现。本章分析默认实现。lane 名的构造如下：

~~~ts
export function resolveSessionLane(key: string) {
  const cleaned = key.trim() || CommandLane.Main;
  return cleaned.startsWith("session:") ? cleaned : `session:${cleaned}`;
}

export function resolveGlobalLane(lane?: string) {
  const cleaned = lane?.trim();
  // Cron jobs hold the cron lane slot; inner operations must use nested to avoid deadlock.
  if (cleaned === CommandLane.Cron) {
    return CommandLane.Nested;
  }
  return cleaned ? cleaned : CommandLane.Main;
}
~~~

Alice 的 Key 若是 `agent:main:WeChat:direct:101`，对应 Session Lane 就是 `session:agent:main:WeChat:direct:101`。它按逻辑 Key 命名，不按 runId 命名；同一对话的新 Run 因而继续进入同一条 lane。

两层入队回调形成以下嵌套关系，内层工作体省略：

~~~ts
return enqueueSession(() => {
  throwIfAborted();
  return enqueueGlobal(async () => {
    throwIfAborted();
    const started = Date.now();
~~~

外层 callback 返回内层 enqueueGlobal 的 Promise。因此 Session 任务的生命周期包括“等待全局额度”和“实际执行”两个阶段。只有内层完成或失败，外层 Promise 才完成或失败，Session 槽位才让出。

假设 main 已满，Carol 的 Session Lane 原本空闲。Carol 会先占用自己的 Session 槽，然后在 main 等待。此时 Carol 没有开始模型执行，但她后续的另一个完整 Run 也不能越过当前 Session 任务。

下面的图表示真实的调用与等待关系，参数名对应源码：

~~~mermaid
flowchart TD
    R["runEmbeddedPiAgent(params)"] -->|"sessionKey 或 sessionId"| S["resolveSessionLane"]
    R -->|"params.lane"| G["resolveGlobalLane"]
    S -->|"lane 名"| ES["enqueueCommandInLane(sessionLane, callback)"]
    G -->|"lane 名供内层使用"| EG["enqueueCommandInLane(globalLane, task)"]
    ES -->|"Session 槽可用后调用 callback"| EG
    EG -->|"Global 槽可用后调用 task"| A["执行后端与 Pi attempt"]
    A -->|"完成或抛错"| GP["内层 Promise 完成或拒绝"]
    GP -->|"外层等待内层"| SP["Session 任务完成，允许下一项"]
~~~

在时间线的 t3，Carol 的外层任务已经开始，它返回的却是 main 队列中 C1 的未完成 Promise。于是 Carol lane 的 active=1 与“C1 尚未真正执行”同时成立。Bob 在 t4 让出 main 槽后，C1 的内层 task 才开始。

### 7.5 等待项与活动项怎样表示

实际数据结构很小：

~~~ts
type QueueEntry = {
  task: () => Promise<unknown>;
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
  enqueuedAt: number;
  warnAfterMs: number;
  onWait?: (waitMs: number, queuedAhead: number) => void;
};

type LaneState = {
  lane: string;
  queue: QueueEntry[];
  activeTaskIds: Set<number>;
  maxConcurrent: number;
  draining: boolean;
  generation: number;
};
~~~

QueueEntry 中的 task 是未来要调用的函数；resolve/reject 对应提交者得到的 Promise。enqueuedAt 用于计算等待时间；onWait 用于等待观察，不是启动模型的回调。

LaneState 中 queue 保存等待项，activeTaskIds 保存已经启动且尚未结束的任务。maxConcurrent 限制后者的数量。draining 用于防止调度泵同步重入。generation 用于识别进程内重置前后的任务完成通知。

lane 状态保存在进程内全局 singleton 中，使不同打包模块能看到同一队列；没有把任务函数序列化到磁盘。

### 7.6 入队、取出、完成，怎样唤起下一项

入队代码返回新的 Promise：

~~~ts
export function enqueueCommandInLane<T>(
  lane: string,
  task: () => Promise<T>,
  opts?: {
    warnAfterMs?: number;
    onWait?: (waitMs: number, queuedAhead: number) => void;
  },
): Promise<T> {
  const queueState = getQueueState();
  if (queueState.gatewayDraining) {
    return Promise.reject(new GatewayDrainingError());
  }
  const cleaned = normalizeLane(lane);
  const warnAfterMs = opts?.warnAfterMs ?? 2_000;
  const state = getLaneState(cleaned);
  return new Promise<T>((resolve, reject) => {
    state.queue.push({
      task: () => task(),
      resolve: (value) => resolve(value as T),
      reject,
      enqueuedAt: Date.now(),
      warnAfterMs,
      onWait: opts?.onWait,
    });
    logLaneEnqueue(cleaned, getLaneDepth(state));
    drainLane(cleaned);
  });
}
~~~

push 保存任务后立即调用 drainLane。若 lane 空闲，task 可以在本次 enqueue 调用内开始；容量已满时才留在队列中等待。

调度泵的启动条件是：

~~~ts
const pump = () => {
  try {
    while (state.activeTaskIds.size < state.maxConcurrent && state.queue.length > 0) {
      const entry = state.queue.shift() as QueueEntry;
      const waitedMs = Date.now() - entry.enqueuedAt;
~~~

while 同时检查活动数小于容量、等待队列非空。shift 从队首取任务，所以在这条 lane 内按 FIFO 开始；它不承诺跨多个 lane 的全局公平性。

等待日志处理之后，源码给任务分配内部 taskId、记录 generation，再启动异步工作：

~~~ts
logLaneDequeue(lane, waitedMs, state.queue.length);
const taskId = getQueueState().nextTaskId++;
const taskGeneration = state.generation;
state.activeTaskIds.add(taskId);
void (async () => {
  const startTime = Date.now();
  try {
    const result = await entry.task();
    const completedCurrentGeneration = completeTask(state, taskId, taskGeneration);
    if (completedCurrentGeneration) {
      notifyActiveTaskWaiters();
      diag.debug(
        `lane task done: lane=${lane} durationMs=${Date.now() - startTime} active=${state.activeTaskIds.size} queued=${state.queue.length}`,
      );
      pump();
    }
    entry.resolve(result);
~~~

登记 activeTaskIds 发生在 await task 之前。任务未完成时，即使 JavaScript 把执行权交回事件循环，这个槽位仍然被占用。并发额度要到任务结算后才释放。

任务结束后，completeTask 先确认任务属于当前 generation，才删除对应活动 ID，再通知等待者并 pump 下一项，最后 resolve 提交者的 Promise。失败分支同样做槽位清理与 pump，再 reject。因此正常异常不会让 lane 永久卡在“占着一个槽”。

可以把容量为 1 的单条 lane 状态写成：

| 时刻 | queue | activeTaskIds | 发生的操作 |
| --- | --- | --- | --- |
| 初始 | [] | {} | 无工作 |
| 提交 R1 | [R1]，随后取出 | {1} | task R1 开始 |
| 提交 R2 | [R2] | {1} | 无空位，R2 等待 |
| R1 完成 | [R2]，随后取出 | {2} | 删除 1，pump 启动 R2 |
| R2 完成 | [] | {} | Promise 完成，lane 空闲 |

`getQueueSize` 返回等待数加活动数，不是只返回 queue.length。观察它得到 1，可能是一项正在执行，也可能是一项在更内层等待。

将单 lane 的 pump 代回 t4：B1 完成使 main 的 active 数从 2 变为 1，while 条件重新成立，队首 C1 被取出并登记为 active。C1 完成自己的内层工作后，其返回的 Promise 才允许 Carol 的外层 Session 任务结束。

Alice 的 A2 则尚未出现在 main.queue 中。只有 A1 收尾启动消息队列 drain，A2 被组织成新 Run 后，才再次走相同的两层 enqueue。

### 7.7 执行串行与文件保护的分工

| 机制 | 键或文件 | 作用范围 | 主要解决的问题 |
| --- | --- | --- | --- |
| Session Lane | session:<逻辑 Key> | 当前进程 | 同一会话的完整运行顺序 |
| Global Lane | main 等名字 | 当前进程中的该 lane | 多 Session 的总体执行额度 |
| Transcript lock | 具体 sessionFile.lock | 遵守锁协议的写入者，可跨进程 | 同一 JSONL 的读改写冲突 |
| Store lock | sessions.json.lock | 共用该 Store 的更新者 | 不同 Session 元数据相互覆盖 |

对 Alice、Bob，两个 Session Lane 可以并行，但它们仍会更新同一 Agent 的 sessions.json，所以 Store 更新还需要自己的保护；同一个 transcript 若被另一个遵循协议的进程打开，则还需要按文件路径取得写锁。

第 10.2—10.3 节继续分析锁的取得、陈旧判断和释放。

## 8. 先理解默认 collect，再比较其他运行中消息策略

### 8.1 Alice 的 A2、A3 为什么先留下来

沿用第 7 节的并发练习，Alice 的 A1 还在执行。她又发 A2：“只分析原因。”，随后补充 A3：“不要修改文件。”。两条新消息来自同一用户、同一 Bot、同一私聊，授权上下文也相同。

默认 collect 让 A1 继续执行，将 A2、A3 放入 Alice 当前 Key 的待处理队列；A1 正常收尾、安静窗口满足后，将它们拼成一个后续 Run 的输入。这个新 Run 接续同一实例的历史，因此能看到 A1 已经产生的结果，但不会把 A1 作为排队消息再拼一遍。

本版默认值可以直接从源码确认：

~~~ts
function defaultQueueModeForChannel(_channel?: string): QueueMode {
  return "collect";
}
~~~

Alice 第一条输入到达空闲会话时，策略直接允许准备新 Run；collect 本身不会让它固定等待 1 秒，全局额度或接入机制仍可能造成等待。这里的 debounce 只在已经进入 followup drain 的消息上使用。

### 8.2 新消息怎样进入 FollowupRun 队列

Command Queue 存 `task: () => Promise`，决定一项运行什么时候可以开始。消息 followup 队列存 `FollowupRun`，其中有待处理 prompt、来源、消息 ID 和运行参数，决定新输入如何交给现在或未来的运行。

`FollowupRun` 的 routing 元数据和 run 子对象分开保存。前者记住这条消息该回哪里；后者包括 sessionId/sessionKey/sessionFile、Agent、模型与授权相关上下文。

所以，Alice 第二条消息进入 collect 队列时，不一定已经产生第二个 Command Queue task。只有 drain 决定形成新的运行后，才申请 Session Lane 和 Global Lane。

runPreparedReply 会为每条输入预先构造一个名为 followupRun 的参数对象，但“已经构造对象”不等于“已经入队”。A1 也有这个参数对象；因为它到达时会话空闲，走的是直接运行分支。A2/A3 发现当前会话 active，才可能进入 FOLLOWUP_QUEUES。

`runPreparedReply` 用 sessionKey 找活动 sessionId，再查询 isActive 和 isStreaming。活动登记结合 embedded handle 和回复运行 registry，避免只在 Pi 已经开始生成时才把 Session 视为忙碌。

ReplyOperation 可以在准备阶段登记为 queued，之后切 running；因此等全局额度时也可能 active。streaming 则需要相应后端句柄的状态，compacting 还要单独检查。是否可以 steer 取决于这些运行状态。

模式标志的计算如下；对于当前 collect，shouldSteer=false、shouldFollowup=true：

~~~ts
const resolveActiveQueueSessionId = () =>
  piRuntime?.resolveActiveEmbeddedRunSessionId(sessionKey) ?? preparedSessionState.sessionId;
const resolveQueueBusyState = () => {
  const activeSessionId = resolveActiveQueueSessionId();
  if (!activeSessionId || !piRuntime) {
    return { activeSessionId: undefined, isActive: false, isStreaming: false };
  }
  return {
    activeSessionId,
    isActive: piRuntime.isEmbeddedPiRunActive(activeSessionId),
    isStreaming: piRuntime.isEmbeddedPiRunStreaming(activeSessionId),
  };
};
let { activeSessionId, isActive, isStreaming } = resolveQueueBusyState();
const shouldSteer = resolvedQueue.mode === "steer" || resolvedQueue.mode === "steer-backlog";
const shouldFollowup =
  resolvedQueue.mode === "followup" ||
  resolvedQueue.mode === "collect" ||
  resolvedQueue.mode === "steer-backlog";
~~~

collect 不进入 steer 尝试，接着使用下面的策略函数。

~~~ts
export function resolveActiveRunQueueAction(params: {
  isActive: boolean;
  isHeartbeat: boolean;
  shouldFollowup: boolean;
  queueMode: QueueSettings["mode"];
}): ActiveRunQueueAction {
  if (!params.isActive) {
    return "run-now";
  }
  if (params.isHeartbeat) {
    return "drop";
  }
  if (params.shouldFollowup || params.queueMode === "steer") {
    return "enqueue-followup";
  }
  return "run-now";
}
~~~

第一条 A1 因 !isActive 返回 run-now；A2/A3 因 isActive 且 shouldFollowup 返回 enqueue-followup。heartbeat 的 drop 是另一种系统输入条件，不作用于本例三位用户的普通消息。

runReplyAgent 据此实际入队：

~~~ts
if (activeRunQueueAction === "enqueue-followup") {
  enqueueFollowupRun(
    queueKey,
    followupRun,
    resolvedQueue,
    "message-id",
    queuedRunFollowupTurn,
    false,
  );
  // Re-check liveness after enqueue so a stale active snapshot cannot leave
  // the followup queue idle if the original run already finished.
  if (!isRunActive?.()) {
    finalizeWithFollowup(undefined, queueKey, queuedRunFollowupTurn);
  }
  await touchActiveSessionEntry();
  typing.cleanup();
  return undefined;
}
~~~

这里入队后还重新检查 liveness。原因是“刚才看到 active”与“现在完成入队”之间，原运行可能刚好结束；如果不补查，消息可能错过启动 drain 的机会。

队列以 sessionKey 为主键，状态包括 items、draining、lastEnqueuedAt、mode、debounceMs、cap、dropPolicy、droppedCount 和 summaryLines。队列保存在进程内 FOLLOWUP_QUEUES Map 中。

A2、A3 保存到的是 `FOLLOWUP_QUEUES[K].items`，其中 K 仍为 `agent:main:WeChat:direct:101`。Bob、Carol 使用各自 Key 的队列，collect 不会把他们三个私聊混成一条输入。

### 8.3 collect 的消费过程：合并之后启动一个新 Run

原运行收尾通过 `finalizeWithFollowup` 启动 drain：

~~~ts
export const finalizeWithFollowup = <T>(
  value: T,
  queueKey: string,
  runFollowupTurn: Parameters<typeof scheduleFollowupDrain>[1],
): T => {
  scheduleFollowupDrain(queueKey, runFollowupTurn);
  return value;
};
~~~

它调用 scheduleFollowupDrain 后立即返回原值。drain 自身启动一个后台 async 函数，所以“第一次回复调用已经完成”不等于“后续消息队列全部执行完”。

后台 drain 先等待距最后一次入队的安静窗口，再检查回复目标和授权上下文能否合并。正常同目标路径取队列快照，按连续相同授权上下文分组；Alice 的 A2/A3 满足条件，落在同一个 groupItems 中。

真正构造合并输入并调用后续执行的代码为：

~~~ts
let pendingSummary = summary;
for (const groupItems of authGroups) {
  const run = groupItems.at(-1)?.run ?? queue.lastRun;
  if (!run) {
    break;
  }

  const routing = resolveOriginRoutingMetadata(groupItems);
  const prompt = buildCollectPrompt({
    title: "[Queued messages while agent was busy]",
    items: groupItems,
    summary: pendingSummary,
    renderItem: renderCollectItem,
  });
  await effectiveRunFollowup({
    prompt,
    run,
    enqueuedAt: Date.now(),
    ...routing,
  });
  queue.items.splice(0, groupItems.length);
  if (pendingSummary) {
    clearQueueSummaryState(queue);
    pendingSummary = undefined;
  }
}
~~~

run 取该组最后一条保存的运行参数；routing 保留该组的来源。buildCollectPrompt 产生新的字符串，effectiveRunFollowup 是 createFollowupRunner 返回的回调，不是 A1 的 activeSession.prompt。await 等这个回调 fulfilled 后，才从 queue.items 删除这一组；期间新到的条目仍留给后面的消费。

单条排队文本的格式来自：

~~~ts
function renderCollectItem(item: FollowupRun, idx: number): string {
  const senderLabel =
    item.run.senderName ?? item.run.senderUsername ?? item.run.senderId ?? item.run.senderE164;
  const senderSuffix = senderLabel ? ` (from ${senderLabel})` : "";
  return `---\nQueued #${idx + 1}${senderSuffix}\n${item.prompt}`.trim();
}
~~~

为精确观察拼接，假设前面的预处理已经完成，此时两个 item.prompt **恰好分别是**“只分析原因。”和“不要修改文件。”，run.senderName 均为 Alice，没有溢出摘要。按 buildCollectPrompt 的 `blocks.join("\n\n")` 规则，结果是：

~~~text
[Queued messages while agent was busy]

---
Queued #1 (from Alice)
只分析原因。

---
Queued #2 (from Alice)
不要修改文件。
~~~

这是给定两个 item.prompt 后的静态推导。真实 WeChat 输入可能已带来源和附加上下文；这段字符串也只是新一轮输入，不是包含系统提示和全部历史的完整模型请求。Queued #1/#2 是本组合并时的序号，与消息 ID、A2/A3 的教学编号都不同。

回调为这个合并输入创建新的 runId，经模型故障转移层进入 runEmbeddedPiAgent，再申请 Alice Session Lane 和 main Global Lane。即使 A1 已结束，其他 Session 仍可能占满 main，所以“合并完成”不代表“模型立即开始”。

~~~text
A1 正常收尾
  → finalizeWithFollowup(...)
      → scheduleFollowupDrain(...)
          → 启动后台 async drain
              → await waitForQueueDebounce(...)
              → 同目标检查、连续授权分组、buildCollectPrompt(...)
              → await effectiveRunFollowup(合并后的 FollowupRun)
                  → createFollowupRunner 返回的闭包
                      → 新 runId
                      → runWithModelFallback 的执行回调
                          → runEmbeddedPiAgent({ sessionKey: K, sessionId: S2, ... })
                              → Session Lane → Global Lane → Pi
              → 回调 fulfilled 后移除已处理组
      → 立即返回 A1 的原结果，不等待后台 drain 完成
~~~

本并发练习发生在第 5 节 /new 之后，所以 Alice 当前实例为 S2；K 与回复目标仍然没有改变。这里的 followup 是 OpenClaw 新 Run，不是直接调用 Pi 的 AgentSession.followUp 方法。有关不同来源不能合并的具体判断，见第 9.3 节。

### 8.4 只把模式改为 followup：相同输入变成两次后续运行

现在只临时将 `messages.queue.mode` 从 collect 改为 followup，A1、A2、A3、所有身份字段与并发额度都不变。

A2/A3 仍先进入 Alice 的待处理队列，但 drain 不把两条 prompt 拼接。它取 A2，等待一次后续运行完成并移除；再取 A3，启动另一轮。因而 A3 的历史可以包含 A2 那轮的结果，而 collect 让两条输入共同参与同一次新 Run。

逐条消费的真实代码及交接如下：

~~~ts
export async function drainNextQueueItem<T>(
  items: T[],
  run: (item: T) => Promise<void>,
): Promise<boolean> {
  const next = items[0];
  if (!next) {
    return false;
  }
  await run(next);
  items.shift();
  return true;
}
~~~

先读取队首，不先删除；回调 fulfilled 后才 shift，再处理下一条。回调仍是前节的 createFollowupRunner，每次创建一个新 Run，再进入同样的两级 lane。

这个对比只改变输入如何分成运行，不改变 Session Lane 串行，也不为 Alice 多分配一个全局槽。比较完后恢复 collect。

### 8.5 只把模式改为 steer：尝试交给当前 Run

本小节改用 `messages.queue.mode: "steer"`，其余仍为基准配置。A2 到达时，如果当前 A1 可以接收 steering，就把新输入交给 A1 的内部队列，而不等待它先结束再启动一个独立 Run。

实际判断位于 `runReplyAgent`：

~~~ts
if (shouldSteer && isStreaming) {
  const steerSessionId =
    (sessionKey ? replyRunRegistry.resolveSessionId(sessionKey) : undefined) ??
    followupRun.run.sessionId;
  const steered = queueEmbeddedPiMessage(steerSessionId, followupRun.prompt);
  if (steered && !shouldFollowup) {
    await touchActiveSessionEntry();
    typing.cleanup();
    return undefined;
  }
}
~~~

当 shouldSteer 且 isStreaming，代码找到当前活动实例，再调用 `queueEmbeddedPiMessage`。纯 steer 同步返回已接受时，代码更新会话活动时间并返回 undefined，将后续输出留给当前 Run；本次入站调用没有独立的即时回复，也不再启动新的 OpenClaw Run。

底层先查 embedded handle；不存在时还会尝试 ReplyOperation 注册的后端。在直接使用 embedded handle 的分支中，handle 必须正在 streaming，且没有 compacting：

~~~ts
export function queueEmbeddedPiMessage(sessionId: string, text: string): boolean {
  const handle = ACTIVE_EMBEDDED_RUNS.get(sessionId);
  if (!handle) {
    const queuedReplyRunMessage = queueReplyRunMessage(sessionId, text);
    if (queuedReplyRunMessage) {
      logMessageQueued({ sessionId, source: "pi-embedded-runner" });
      return true;
    }
    diag.debug(`queue message failed: sessionId=${sessionId} reason=no_active_run`);
    return false;
  }
  if (!handle.isStreaming()) {
    diag.debug(`queue message failed: sessionId=${sessionId} reason=not_streaming`);
    return false;
  }
  if (handle.isCompacting()) {
    diag.debug(`queue message failed: sessionId=${sessionId} reason=compacting`);
    return false;
  }
  logMessageQueued({ sessionId, source: "pi-embedded-runner" });
  void handle.queueMessage(text);
  return true;
}
~~~

这里最后是 `void handle.queueMessage(text); return true`。queueMessage 是异步函数，而调用者没有等待它完成。**true 仅确认找到可接收句柄并发起注入。** queueMessage 的 Promise 是否成功、模型何时消费输入，以及相关工作何时完成，都发生在后续异步执行中。

Pi handle 的接收函数会 `await activeSession.steer(text)`。Pi 再把文本转成 steering UserMessage 放入 Agent 队列。已经发到模型服务的请求不会被回写，新消息只能在后续执行边界进入上下文。

本课程 Pi 0.69.0 的 Agent Loop 先等待当前工具批次完成，再获取 steering：

~~~ts
	// Collect tool calls embedded in the assistant response. 收集助手回复中包含的工具调用。
	const toolCalls = message.content.filter((c) => c.type === "toolCall");

	const toolResults: ToolResultMessage[] = [];
	hasMoreToolCalls = false;
	if (toolCalls.length > 0) {
		// message 是刚完成的助手消息；toolCalls 是其中的调用内容块。
		// executeToolCalls 才返回独立的 toolResult 消息，其 toolCallId 对应调用块的 id。
		// 结果加入 currentContext 供下次模型请求，加入 newMessages 供本轮返回；
		// 上层会通过消息事件另行保存会话 Entry。
		const executedToolBatch = await executeToolCalls(currentContext, message, config, signal, emit);
		toolResults.push(...executedToolBatch.messages);
		hasMoreToolCalls = !executedToolBatch.terminate;

		for (const result of toolResults) {
			currentContext.messages.push(result);
			newMessages.push(result);
		}
	}

	await emit({ type: "turn_end", message, toolResults });

	pendingMessages = (await config.getSteeringMessages?.()) || [];
}
~~~

同版本 queue 文档将这一行为概括为“下个工具边界取消尚未执行 tool calls”，但上述 Pi 实现是在当前 assistant/工具批次之后消费 steering，再推进下一次模型请求；它没有逐工具读取 steering 并取消剩余工具的分支。

如果找不到可接收的 embedded handle 或 ReplyOperation 后端，或者直接 embedded handle 不能 streaming、正在 compaction，函数同步返回 false，消息会走 followup 退路。但是，已经返回 true 之后 queueMessage 的异步失败，外层并没有自动转 followup 的代码。steer 分支没有传 messageId，也未提供消息去重或完成确认。

对 A2 的“只分析原因”，steer 会影响当前 Run 后续能够观察到的输入；不会撤回已经完成的工具操作。A3 若也被接收，其消费顺序还遵守 Pi 内部 steering 队列规则，不能套用 OpenClaw collect 的文本合并。读完本节恢复 collect。

### 8.6 其他模式：同时保留 backlog，或请求中断

以下比较仍只改变 messages.queue.mode，输入与会话 Key 不变。

steer-backlog 同时使 shouldSteer、shouldFollowup 为 true。能注入时先交给当前 Run，但不会走纯 steer 的提前返回，仍保留 followup。因此当前 Run 可能回应一次，后续 Run 又处理这条消息。用户看到类似重复的回应，可能来自模式本身的双重处理语义，而非投递层重复发了一条消息。

interrupt 走另一条路。首先若 Session Lane 有工作，清除其中尚未启动的 Command Queue 项，并向活动实例请求 abort。随后等待活动 Run 的结束通知、刷新准备状态，再检查是否仍 active：

~~~ts
if (params.queueMode === "interrupt") {
  const aborted = params.abortActiveRun(params.activeSessionId);
  logVerbose(
    `Interrupting active run for ${params.sessionKey ?? params.sessionId} (aborted=${aborted})`,
  );
}

await params.waitForActiveRunEnd(params.activeSessionId);
await params.refreshPreparedState();
const refreshedBusyState = params.resolveBusyState();
if (refreshedBusyState.isActive) {
  return {
    kind: "reply",
    reply: {
      text: "⚠️ Previous run is still shutting down. Please try again in a moment.",
    },
  };
}
return { kind: "continue", busyState: refreshedBusyState };
~~~

若旧 Run 仍在关闭，就返回提示并暂缓新运行。abort 采用合作式取消，已完成的工具副作用仍然保留。clearCommandLane 清除的是执行等待项，FOLLOWUP_QUEUES 有自己的管理逻辑。

等待结束通知的范围同样有限：active registry 清除可能早于最终资源清理，但后续正常执行仍受到 Session Lane 与 transcript lock 的约束。

| 模式 | 是否影响当前 Run | 是否产生后续新 Run | 连续消息怎样处理 |
| --- | --- | --- | --- |
| collect | 不修改当前 Run | 对可合并批次启动 | 拼接原文，存在路由/授权拆分 |
| followup | 不修改当前 Run | 逐条启动 | 保持队列顺序 |
| steer | 能接收时加入当前 steering 队列 | 同步判定不能接收时退为 followup | 不在此层自动合并或只保留最后一条 |
| steer-backlog | 可 steer，同时保留 backlog | 会安排后续 | 可能当前和后续都回应 |
| interrupt | 请求 abort | 清理与等待后处理新输入 | 不承诺撤销已执行副作用 |
| queue | 正常解析为 steer | 同 steer | 兼容别名 |

### 8.7 Debounce 与容量：连续输入怎样形成批次

以下恢复基准 collect、debounceMs=1000、cap=20、drop=summarize，只在溢出小例中临时将 cap 改为 2。

followup drain 每轮根据 lastEnqueuedAt 等待安静窗口。若 debounce 为 1000ms，0ms 入队一条、600ms 又来一条，最早安静点会后移到约 1600ms，而不是固定在第一条后的 1000ms。原运行如果直到 3000ms 才结束，drain 开始时安静窗口可能已经满足。

这是运行后输入队列的 debounce，不等同于 Channel Plugin 在接入阶段合并消息的所有机制，也不会改变 Command Queue 的容量。

cap 限制每个 followup 队列的消息数。溢出处理代码是：

~~~ts
export function applyQueueDropPolicy<T>(params: {
  queue: QueueState<T>;
  summarize: (item: T) => string;
  summaryLimit?: number;
}): boolean {
  const cap = params.queue.cap;
  if (cap <= 0 || params.queue.items.length < cap) {
    return true;
  }
  if (params.queue.dropPolicy === "new") {
    return false;
  }
  const dropCount = params.queue.items.length - cap + 1;
  const dropped = params.queue.items.splice(0, dropCount);
  if (params.queue.dropPolicy === "summarize") {
    for (const item of dropped) {
      params.queue.droppedCount += 1;
      params.queue.summaryLines.push(buildQueueSummaryLine(params.summarize(item)));
    }
    const limit = Math.max(0, params.summaryLimit ?? cap);
    while (params.queue.summaryLines.length > limit) {
      params.queue.summaryLines.shift();
    }
  }
  return true;
}
~~~

new 拒绝新项；old 移除最旧项后接受新项；summarize 移除最旧项，同时保留其简短文本行供之后的 synthetic prompt 使用。这里通过压缩空白、截断等字符串操作生成摘要行，不调用 LLM；超过长度限制的原文会被截去。

例如 cap=2，已有 M1、M2，M3 到达。old 保留 M2、M3；new 保留 M1、M2；summarize 保留 M2、M3，并记住 M1 的简短摘要。cap 控制待处理消息数，maxConcurrent 控制并发执行数。

### 8.8 设置优先级与旧版别名

实际有效模式按以下顺序解析：

~~~ts
export function resolveQueueSettings(params: ResolveQueueSettingsParams): QueueSettings {
  const channelKey = normalizeOptionalLowercaseString(params.channel);
  const queueCfg = params.cfg.messages?.queue;
  const providerModeRaw =
    channelKey && queueCfg?.byChannel
      ? (queueCfg.byChannel as Record<string, string | undefined>)[channelKey]
      : undefined;
  const resolvedMode =
    params.inlineMode ??
    normalizeQueueMode(params.sessionEntry?.queueMode) ??
    normalizeQueueMode(providerModeRaw) ??
    normalizeQueueMode(queueCfg?.mode) ??
    defaultQueueModeForChannel(channelKey);
~~~

本条 inline 设置优先，其次 SessionEntry 覆盖、渠道设置、全局配置，最后 collect。基准配置已经显式设置 collect；也可以通过 /queue 指令设置当前 Session 覆盖。第 8.4—8.6 节的比较均假设没有 Session、inline 或 byChannel 模式覆盖，因此仅改变全局 mode 即可使对应策略生效。

debounce 另外考虑渠道专属值和插件默认值，解析顺序与 mode 有所不同。无覆盖时，消息队列默认 debounce 1000ms、cap 20、drop summarize。

普通字符串解析的兼容规则如下：

| 输入模式或别名 | 归一化结果 |
| --- | --- |
| steer、steering | steer |
| queue、queued | steer |
| followup、follow-ups、followups | followup |
| collect、coalesce | collect |
| steer-backlog、steer+backlog、steer_backlog | steer-backlog |
| interrupt、interrupts、abort | interrupt |

interrupt 在本版本中仍有实际执行分支；queue 经正常归一化后等同 steer。正式配置应使用规范模式名，因为配置 schema 未必接受字符串解析器支持的所有别名。

### 8.9 进阶：去重、重试与失败边界

enqueue 会检查队内重复和近期 messageId 缓存。缓存键同时含 queueKey、channel、to、account、thread 和 messageId，避免不同渠道相同消息号相互误判。近期缓存默认 5 分钟、最多 10000 项；没有 messageId 时，当前 message-id 模式不会简单按正文去重。

drain 在回调成功后才移除，直接抛错时保留尚未移除项并重新调度；入队后的 liveness 复查则防止“原运行恰好结束”造成队列停滞。这些都有明确作用，但不能扩大成 exactly-once 保证。

FOLLOWUP_QUEUES 和 Command Queue 都是内存状态，真正进程退出会丢失；溢出策略会主动丢弃内容；followup runner 有捕获执行错误后记录并返回的分支，外层可能将其视为 fulfilled；投递失败也可能只记录而不无限重试。外部副作用发生后再次执行，还可能重复产生副作用。

steer 的同步 true、followup 入队成功、模型处理成功、平台发送成功分别确认不同阶段，去重与重试也各有作用范围。

## 9. 运行结果怎样回到 Alice 的原始渠道

### 9.1 历史地址不等于回复地址

先看基准配置：Alice 当前 Run 的结果应该回到 WeChat/default/WeChat:101；K 或实例 ID 的变化都不会代替这组三个投递值。

为了观察共享会话的边界，本节临时改成 dmScope: main，并沿用第 4.4 节的扩展身份：Alice 的 WeChat ID 是 101，Discord ID 是 501，两边都路由到 main。此时两边消息进入同一个 `agent:main:main`。两次请求查到同一逻辑会话，同时各自保留入站来源。

MsgContext 仍保留 OriginatingChannel、OriginatingTo、AccountId、MessageThreadId 等字段。进入 followup 时，这些字段被复制到排队项：

~~~ts
const followupRun = {
  prompt: queuedBody,
  messageId: sessionCtx.MessageSidFull ?? sessionCtx.MessageSid,
  summaryLine: baseBodyTrimmedRaw,
  enqueuedAt: Date.now(),
  // Originating channel for reply routing.
  originatingChannel: ctx.OriginatingChannel,
  originatingTo: ctx.OriginatingTo,
  originatingAccountId: sessionCtx.AccountId,
  originatingThreadId: ctx.MessageThreadId,
~~~

为什么不能只看 SessionEntry.lastChannel？假设 WeChat 请求 T1 正在运行，Discord 请求 D1 随后到达并更新最近渠道。T1 若结束时才查询“最后使用的渠道”，就可能把 WeChat 的回答投到 Discord。最后渠道是一个会变化的会话级记录，本次请求的来源则应跟随本次请求一起保存。

同一 Session 的串行执行约束运行先后；回复来源仍需逐消息保存，才能在排队后返回正确渠道。

WeChat 那条排队输入保留的值具体是：

~~~text
queued.originatingChannel   = "WeChat"
queued.originatingAccountId = "default"
queued.originatingTo        = "WeChat:101"
queued.originatingThreadId  = undefined
~~~

这组字段跟随该条输入，而不是在它执行结束时重新从 SessionEntry.lastChannel 猜测。Alice 从 Discord 发来的另一条输入，则保存 Discord 自己的目标表示。

### 9.2 从 queued 来源到 routeReply 的真实参数

普通 dispatch 并非所有回复都调用 routeReply。当前 Provider/Surface 与 OriginatingChannel 相同的常规路径，可以继续使用插件提供的 dispatcher，它已捕获正确发送目标。

`dispatchReplyFromConfig` 比较本次 ctx 的来源与当前 surface，必要时选择显式来源路由；内部 WebChat、父级拥有的 ACP 后台会话等还有专门限制。线程优先从当前 ctx 或线程 Session Key 取，代码明确避免从可能残留旧线程信息的 store 中恢复一个过期目标。

followup 因为在后台执行，更需要使用 queued 上保存的来源：

~~~ts
// Route to originating channel if set, otherwise fall back to dispatcher.
if (shouldRouteToOriginating) {
  const result = await routeReply({
    payload,
    channel: originatingChannel,
    to: originatingTo,
    sessionKey: queued.run.sessionKey,
    accountId: queued.originatingAccountId,
    requesterSenderId: queued.run.senderId,
    requesterSenderName: queued.run.senderName,
    requesterSenderUsername: queued.run.senderUsername,
    requesterSenderE164: queued.run.senderE164,
    threadId: queued.originatingThreadId,
    cfg: runtimeConfig,
  });
~~~

传入的 channel/to/account/thread 都来自这条 queued 记录。sessionKey 仍用于确定 Agent 身份默认值与策略，不能代替投递地址。

routeReply 的出口是通用出站模块：

~~~ts
const results = await deliverOutboundPayloads({
  cfg,
  channel: channelId,
  to,
  accountId: accountId ?? undefined,
  payloads: [externalPayload],
  replyToId: resolvedReplyToId ?? null,
  threadId: resolvedThreadId,
  session: outboundSession,
  abortSignal,
  mirror:
    params.mirror !== false && params.sessionKey
      ? {
          sessionKey: params.sessionKey,
          agentId: resolvedAgentId,
          text,
          mediaUrls,
          ...(params.isGroup != null ? { isGroup: params.isGroup } : {}),
          ...(params.groupId ? { groupId: params.groupId } : {}),
        }
      : undefined,
});
~~~

本章只关注这次交接：channel 决定发送渠道，to 决定目标，accountId 选择账户，threadId 保留子会话位置；payload 是要发送的内容。后续各平台 API 已在上一章介绍。

如果来源路由失败，followup 只在 origin 与原 provider 相同时才允许回退到调用者 dispatcher；真正跨渠道时不能随意回退，否则可能发错平台。没有可用来源也没有回调时，代码会记录并放弃该批 payload。实际投递结果还取决于出站接口与平台响应。

### 9.3 collect 必须保留每一组输入的投递与授权边界

collect 要形成一段新 prompt，因此必须选一个回复目标。如果把 WeChat 和 Discord 的消息全部拼成一个 Run，再只取最后一个目标，前面请求就会失去自己的投递地址。

源码中的“跨渠道检查”实际比名字更细：

~~~ts
function resolveCrossChannelKey(item: FollowupRun): { cross?: true; key?: string } {
  const { originatingChannel: channel, originatingTo: to, originatingAccountId: accountId } = item;
  const threadId = item.originatingThreadId;
  if (!channel && !to && !accountId && (threadId == null || threadId === "")) {
    return {};
  }
  if (!isRoutableChannel(channel) || !to) {
    return { cross: true };
  }
  // Support both number (WeChat topic IDs) and string (Slack thread_ts) thread IDs.
  const threadKey = threadId != null && threadId !== "" ? String(threadId) : "";
  return {
    key: [channel, to, accountId || "", threadKey].join("|"),
  };
}
~~~

比较的是 channel、to、accountId 和 threadId。任一来源组合不同，当前 drain 就转为逐条处理；并在这一轮 drain 中保持该决定，防止取走第一项后又错误地合并剩余异目标消息。

即使目标相同，也要按相邻的授权上下文分组。`resolveFollowupAuthorizationKey` 纳入 SenderId、SenderE164、senderIsOwner、execOverrides、bashElevated 等字段；`splitCollectItemsByAuthorization` 只合并连续且 key 相同的项。显示名改变不影响授权 key，避免把纯显示变化当成权限变化。

例如同一群里 Alice、Bob、Alice 连续发言，三条输入按原顺序分组，第一条和第三条保持分开。这样既保留消息顺序，也让每一组使用对应发送者的执行上下文。

这些拆分保护不消除共享 Session 的历史事实：不同目标可以分别得到回复，但它们若使用同一 sessionKey，后续运行仍会接续同一历史。回复目标隔离与上下文隔离是两种独立要求。

### 9.4 入站选择 Agent，出站使用请求的投递目标

Binding 回答“哪一个 Agent 配置处理这条输入”，主要依据来源条件与规则优先级。routeReply 回答“这个 payload 发到哪个已确定目标”，主要依据请求保留的来源和显式投递参数。

出站不会重新扫描 bindings 来反推出用户，也不会把 sessionKey 当作 WeChat chatId。mainSessionKey、lastRoutePolicy、最近投递位置可以辅助会话管理和其他主动发送场景，但普通请求的返回地址应从这条请求自身的数据链理解。

本节的共享 Session 对比结束，后续恢复基准 per-channel-peer。回看 Alice 第一条消息，数据的终点没有改变：

~~~text
from.id=101 / chat.id=101
  → Binding: main / binding.channel
  → K=agent:main:WeChat:direct:101
  → SessionEntry: S1 + S1.jsonl 的实际路径
  → session:K → main Global Lane
  → Pi SessionManager / AgentSession / prompt
  → 本次请求携带的 WeChat/default/WeChat:101
~~~

第三次 /new 之后，替换的是中间的实例 S1→S2；A2/A3 的 collect 改变的是进入运行的时间和分组。Agent 的选择、会话历史的选择、运行调度和投递目标各自使用相应字段，并通过这条数据链联系。

## 10. 进阶实现：在正常数据链之外，补齐隔离与失败处理

### 10.1 默认目录与认证继承怎样补全 Agent 配置

实际路径可以被状态根目录与配置覆盖，Workspace 的缺省算法按以下条件选择：

~~~ts
  const id = normalizeAgentId(agentId);
  const configured = resolveAgentConfig(cfg, id)?.workspace?.trim();
  if (configured) {
    return stripNullBytes(resolveUserPath(configured, env));
  }
  const defaultAgentId = resolveDefaultAgentId(cfg);
  const fallback = cfg.agents?.defaults?.workspace?.trim();
  if (id === defaultAgentId) {
    if (fallback) {
      return stripNullBytes(resolveUserPath(fallback, env));
    }
    return stripNullBytes(resolveDefaultAgentWorkspaceDir(env));
  }
  if (fallback) {
    return stripNullBytes(path.join(resolveUserPath(fallback, env), id));
  }
  const stateDir = resolveStateDir(env);
  return stripNullBytes(path.join(stateDir, `workspace-${id}`));
}
~~~

先查该 Agent 的显式 workspace；没有时，默认 Agent 使用共享默认 Workspace。非默认 Agent 如果发现 `agents.defaults.workspace`，则使用该目录下的 Agent ID 子目录；再没有才退到状态目录中的 `workspace-<id>`。

`resolveAgentDir` 则优先使用该 Agent 的显式 agentDir，否则构造状态根目录下的 `agents/<id>/agent`。`models.json` 默认位于该 agentDir 中。有效主模型优先取 Agent 自己的 model，再回退 `agents.defaults.model`，之后 Session 覆盖和本次运行参数还可以参与选择。运行时把解析好的模型、工作目录与 agentDir 传给执行层。

加载器读取当前 Agent 的认证存储后，还可能与主认证存储合并：

~~~ts
export function ensureAuthProfileStoreWithoutExternalProfiles(
  agentDir?: string,
  options?: { allowKeychainPrompt?: boolean },
): AuthProfileStore {
  const runtimeStore = resolveRuntimeAuthProfileStore(agentDir);
  if (runtimeStore) {
    return runtimeStore;
  }
  const store = loadAuthProfileStoreForAgent(agentDir, options);
  const authPath = resolveAuthStorePath(agentDir);
  const mainAuthPath = resolveAuthStorePath();
  if (!agentDir || authPath === mainAuthPath) {
    return store;
  }

  const mainStore = loadAuthProfileStoreForAgent(undefined, options);
  return mergeAuthProfileStores(mainStore, store);
}
~~~

这里的“主认证存储”由无参数的认证路径解析决定，默认在 `agents/main/agent`，也可受环境变量影响；它不必等同于 `agents.list` 中任意标了 default 的项。合并起点是主 profiles 加当前 Agent profiles，同名项由当前存储覆盖，随后还有 OAuth 协调。缺少本地认证存储时，加载器还可以继承主存储中的认证项，并写入当前 Agent 的存储。

Agent 有独立的存储路径和配置作用域，认证加载器则支持继承、合并和外部认证叠加。这比同版本 Multi-Agent 文档中“主凭证不自动共享”的概括更具体：判断实际凭证来源时，还需要考虑上述加载分支。

这些分支解释了为什么第 2 节将“独立配置与存储位置”同“操作系统和凭证安全隔离”分开。它们不改变本章显式 Workspace/agentDir 的路径推导，也不参与选择 Alice 的 Session Key。

### 10.2 Store Lock：为什么拿到锁以后还要重读

一个 Agent 的很多 Session 共用一份 sessions.json。Alice 与 Bob 即使使用不同 Session Lane，也可能同时更新这份索引文件。

如果两人都先读到旧副本 S0，Alice 写入 A 后，Bob 再用自己的 S0 加 B 覆盖整份文件，就会丢掉 A。只保护单个 Session 的执行还不够。

`updateSessionStore` 的实现把重新读取、修改与写入包在同一个锁作用域内：

~~~ts
export async function updateSessionStore<T>(
  storePath: string,
  mutator: (store: Record<string, SessionEntry>) => Promise<T> | T,
  opts?: SaveSessionStoreOptions,
): Promise<T> {
  return await withSessionStoreLock(storePath, async () => {
    // Always re-read inside the lock to avoid clobbering concurrent writers.
    const store = loadSessionStore(storePath, { skipCache: true });
    const previousAcpByKey = collectAcpMetadataSnapshot(store);
    const result = await mutator(store);
    preserveExistingAcpMetadata({
      previousAcpByKey,
      nextStore: store,
      allowDropSessionKeys: opts?.allowDropAcpMetaSessionKeys,
    });
    await saveSessionStoreUnlocked(storePath, store, opts);
    return result;
  });
}
~~~

mutator 接收的是获得锁之后重新读取的最新对象。函数会等待 mutator，再保存，最后才返回 mutator 的结果；await 不只是等“排进队列”。

`withSessionStoreLock` 内部还有按 storePath 排列的进程内 pending 队列；每个任务获得文件锁后运行，finally 释放。这里复用 `acquireSessionWriteLock` 时传入的是 storePath，所以锁文件是 `sessions.json.lock`。它保护整份索引的读改写。

保存使用临时文件写入、sync、rename 等操作。Windows 的失败回退分支并不与正常 rename 完全等价，不宜把实现描述成所有系统、所有故障下都具备相同事务保证。

第 5 节的 initSessionState 在调用 updateSessionStore 时，只提供“应当怎样更新该 entry”；本节的锁保证修改基于取得写入资格后的 Store。Session Lane、元数据更新锁与 transcript 锁的作用域仍按第 7.7 节区分。

### 10.3 Transcript Lock 与 attempt finally：怎样保护实际文件

进入 attempt 后，代码才按 transcript 路径申请文件锁。它规范目录路径，用排他创建打开 `<sessionFile>.lock`：

~~~ts
handle = await fs.open(lockPath, "wx");
const createdAt = new Date().toISOString();
const starttime = getProcessStartTime(process.pid);
const lockPayload: LockFilePayload = { pid: process.pid, createdAt };
if (starttime !== null) {
  lockPayload.starttime = starttime;
}
await handle.writeFile(JSON.stringify(lockPayload, null, 2), "utf8");
const createdHeld: HeldLock = {
  count: 1,
  handle,
  lockPath,
  acquiredAt: Date.now(),
  maxHoldMs,
};
HELD_LOCKS.set(normalizedSessionFile, createdHeld);
return {
  release: async () => {
    await releaseHeldLock(normalizedSessionFile, createdHeld);
  },
};
~~~

锁中记录 pid、创建时间，某些平台还记录进程 starttime。遇到 EEXIST，读取并判断锁是否陈旧；不能回收时退避等待，直到取得或超时。默认不可重入，需要有意嵌套时才显式允许。

这是协作式文件锁，不是操作系统对整个 Workspace 的隔离。任意不遵守协议的程序仍能直接写 JSONL。反过来，两个不同逻辑 Key 如果被错误配置到同一个文件，Session Lane 不会认为它们是同一 lane，但文件锁仍可能发现争用。

Session Lane 串行安排同一进程内经过该 lane 的完整任务；Session 元数据更新、插件回调和外部发送各有自己的调用与同步边界。

`await activeSession.prompt(...)` 等待本次 Pi 输入处理。随后，attempt 的 finally 继续处理补写状态与资源释放；外部发送仍由相应的发送链负责：

~~~ts
try {
  try {
    params.removeToolResultContextGuard?.();
  } catch {
    /* best-effort */
  }
  try {
    await params.flushPendingToolResultsAfterIdle({
      agent: params.session?.agent as IdleAwareAgent | null | undefined,
      sessionManager: params.sessionManager as ToolResultFlushManager | null | undefined,
      clearPendingOnTimeout: true,
    });
  } catch {
    /* best-effort */
  }
  try {
    params.session?.dispose();
  } catch {
    /* best-effort */
  }
  try {
    params.releaseWsSession(params.sessionId);
  } catch {
    /* best-effort */
  }
  try {
    await params.bundleLspRuntime?.dispose();
  } catch {
    /* best-effort */
  }
} finally {
  await params.sessionLock.release();
}
~~~

清理会尽力等待 Agent idle，默认最多等待 30 秒。本调用指定 `clearPendingOnTimeout: true`：等待超时且 manager 支持清理接口时，直接清除待补状态，避免工具尚未结束就写入“缺失工具结果”。正常进入 flush 时，是否补写合成结果仍由 `allowSyntheticToolResults` 决定。随后 dispose 会话、释放相关资源，最终释放 transcript lock。

因此，prompt 返回、待补工具结果处理完成与 transcript lock 释放，仍是三个不同的完成点。

还有一个文件准备分支：已有文件但尚无 assistant Entry 时，prepareSessionManagerForRun 会清理半成品状态，让后续按正常首次写入规则处理。文件打开后的持久化进度仍取决于后续首次 flush 与追加写入。

### 10.4 重置的扩展情况：归档、soft reset 与 Gateway RPC

本地还有 `/reset soft`。它保留会话身份和 transcript，清理部分 CLI 绑定、bootstrap 快照并触发相应 hooks；ACP 场景还有限制。因此本节所谓“重置换 UUID”指一般新会话重置，不包括这一保留历史的专门模式。

普通初始化捕获前一 entry，在写入新映射后尝试归档旧 transcript。以下是存在 previousSessionEntry.sessionId 时，条件块内部的归档调用：

~~~ts
const { archiveSessionTranscriptsDetailed, resolveStableSessionEndTranscript } =
  await loadSessionArchiveRuntime();
const archivedTranscripts = archiveSessionTranscriptsDetailed({
  sessionId: previousSessionEntry.sessionId,
  storePath,
  sessionFile: previousSessionEntry.sessionFile,
  agentId,
  reason: "reset",
});
~~~

底层归档是重命名：

~~~ts
export function archiveFileOnDisk(filePath: string, reason: ArchiveFileReason): string {
  const ts = formatSessionArchiveTimestamp();
  const archived = `${filePath}.${reason}.${ts}`;
  fs.renameSync(filePath, archived);
  return archived;
}
~~~

旧文件通常成为 `旧文件.jsonl.reset.<timestamp>`。所以一般重置不是立即永久删除已有对话；新实例不再把旧实例作为当前聊天历史读取，旧文件则按归档路径保存。归档是 best-effort，后续维护策略也可能清理归档，不能据此承诺历史永久保留。

普通渠道 `getReplyFromConfig → initSessionState` 的轮换路径，不能直接等同于 Gateway RPC 的 `sessions.reset`。

Gateway 的 `performGatewaySessionReset` 会先清理相应队列和子任务，调用 abort，等待运行注册表的结束通知；等不到时返回 unavailable，而不继续正常重置。之后才在 store 更新锁内换 ID，并归档/准备 transcript。

普通渠道初始化自身没有同样的 abort/wait 调用链，不能把 RPC 的清理保证套给所有 /new。Gateway reset 还可能沿用既有 sessionFile 路径，在归档后写新 header；所以“ID 变了”也不恒等于“文件基名一定变成新 UUID”。

等待运行结束信号也有范围：active registry 被清除时可以通知 waiter，但完整 attempt finally 的资源清理和锁释放还在后面。这也是第 7.7 节将 Session Lane、活动登记和文件锁分别解释的原因。

### 10.5 清等待队列、取消活动运行与进程内重启

`clearCommandLane` 删除等待队列中的项，并用 `CommandLaneClearedError` 拒绝它们的 Promise；已经进入 activeTaskIds 的任务不会因这一操作自动取消。取消执行要另外向活动 Run 发 abort 请求。

`resetAllLanes` 则属于进程内重启协调：递增 generation、清活动计数、保留等待项、重新调度。旧任务后来完成时不能再修改新 generation 的活动计数；但它的提交 Promise 仍有自己的完成/拒绝路径。真正进程退出后，这份内存队列不能自动恢复。

Gateway 进入 draining 状态时，新 enqueue 会直接得到 `GatewayDrainingError`。这些是执行调度的生命周期处理，与第 8 节的 collect、steer 等输入策略不是一回事。

### 10.6 把实际调用点重新接起来

下面汇总普通 WeChat 消息进入 embedded Pi 的完整路线。K、S1/S2、sessionFile 和 OriginatingTo 分别沿路由结果、会话状态与回复上下文传递。

普通 WeChat 消息的主线如下。路由结果是返回数据，线程与账户保护处理会继续影响最终 `MsgContext.SessionKey`。

~~~text
buildWeChatMessageContext(...)
  → resolveWeChatConversationRoute(...)
      → resolveAgentRoute({ cfg, channel, accountId, peer, parentPeer, ... })
      ← ResolvedAgentRoute
  → resolveWeChatConversationBaseSessionKey(...)
  → 必要时 resolveThreadSessionKeys(...)
  → await buildWeChatInboundContextPayload(...)
      → await recordInboundSession(...)
          → 发起 recordSessionMetaFromInbound(...)
          → 本例 await updateLastRoute(...)
  ← 带最终 SessionKey、AccountId、SenderId、Originating* 的上下文

dispatchWeChatMessage(...)
  → WeChatDeps.dispatchReplyWithBufferedBlockDispatcher(...)
    经 plugin-sdk 导出到 provider-dispatcher 的包装函数
  → dispatchInboundMessageWithBufferedDispatcher(...)
      → dispatchInboundMessage(...)
          → withReplyDispatcher({ run: 回调 })
              → 回调调用 dispatchReplyFromConfig(...)
                  → replyResolver(ctx, options, cfg)
                    默认 resolver 为 getReplyFromConfig(...)
                      → await initSessionState(...)
                      → runPreparedReply(...)
                          → runReplyAgent(...)
                              → await runAgentTurnWithFallback(...)
                                  → runEmbeddedPiAgent(...)
~~~

`replyResolver` 是函数变量；执行故障转移层还可能选择其他后端。以上取其中进入 `runEmbeddedPiAgent` 的分支。
