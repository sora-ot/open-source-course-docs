# 18 OpenClaw Workspace、Bootstrap 与长期记忆机制

Alice 的消息已经交给 main Agent，OpenClaw 也找到了本次 Session 对应的历史文件。Agent 要维护 TypeScript 项目，还需要工作目录、项目规范和用户偏好。这些信息决定工具操作的位置，也参与模型上下文的构造。

Workspace 提供工作目录和可编辑的文件；Bootstrap 加载将其中符合条件的内容加入本次运行的上下文；Memory 保存跨 Session 使用的事实，并通过索引支持检索。三者共同连接磁盘文件、当前模型请求与后续会话。

本章基于 OpenClaw v2026.4.22。沿用第 17 章的 main、coding 与 Alice，仅用它们说明局部输入和状态变化。示例中的日期、文件内容、向量与相关性分数都是教学数据；源码摘录为连续片段，长函数只保留相关部分。

## 1. 工作环境与上下文来源

### 1.1 工作环境、当前历史与长期事实

第 17 章已经完成 Agent 路由、Session 选择与并发调度。进入 embedded runner 时，还需要准备工作环境和持久信息：

| 执行需要回答的问题 | 主要来源 | 本次运行怎样使用 |
| --- | --- | --- |
| 相对文件路径从哪里开始解析 | Agent 的 Workspace 与 Sandbox 配置 | 创建工具、确定工具工作根目录 |
| Agent 应采用什么规范与语气 | AGENTS.md、SOUL.md 等文件 | 加入符合条件的上下文 |
| 当前用户刚才讨论过什么 | 当前 Session JSONL | Pi 恢复消息树中的有效上下文 |
| 用户长期偏好、已有项目决策在哪里 | MEMORY.md、memory/ 下的 Markdown | 直接上下文、精确读取或 Memory Search |
| 从许多记忆文件中怎样找到相关段落 | Agent 对应的 Memory 索引 | FTS、向量检索及结果排序 |
| 当前消息快放不进模型时怎样保留重要事实 | Memory Flush 与 Compaction | 持久化事实、压缩会话历史，各自维护不同产物 |

图中箭头表示文件或数据的流向。文件工具完成写入后，索引管理器可在后台同步；模型通过上下文注入或工具结果取得这些内容。

~~~mermaid
flowchart TD
    Config["Agent 配置"] --> Workspace["解析 Workspace"]
    Workspace --> Files["规范、身份与记忆 Markdown"]
    Files --> Bootstrap["Bootstrap 加载与过滤"]
    Bootstrap --> Prompt["OpenClaw System Prompt"]
    History["当前 Session JSONL"] --> Pi["Pi AgentSession"]
    Prompt --> Pi
    Files -->|"Memory 文件扫描"| Index["SQLite 检索索引"]
    Index -->|"memory_search 返回片段"| Pi
    Pi -->|"模型选择并执行文件工具"| Files
~~~

本章第 2 节确定目录与作用域，第 3—5 节追踪初始化和 Prompt，第 6—12 节分析长期记忆的文件、工具、索引和检索，第 13 节说明 Memory Flush 与压缩的交接，第 14 节补充可选能力。

### 1.2 目录布局与存储职责

未自定义路径或使用特殊 Profile 时，主要目录如下。部分文件在初始化时建立，部分在后续使用中创建。

~~~text
~/.openclaw/                         OpenClaw 状态目录
  openclaw.json                      Gateway、Agent、工具、Memory 等配置
  workspace/                        main 的工作目录
    AGENTS.md
    SOUL.md
    TOOLS.md
    IDENTITY.md
    USER.md
    HEARTBEAT.md
    BOOTSTRAP.md                     初始化未完成时可能存在
    BOOT.md                          用户选配的 Gateway 启动任务
    MEMORY.md                        按需创建的长期事实
    memory/
      2026-10-08.md                  按需创建的当日记录
    .openclaw/
      workspace-state.json          Workspace 初始化状态
  workspace-coding/                 coding 的独立工作目录
    ...
  agents/
    main/
      agent/                        main 的 agentDir
        auth-profiles.json          模型认证资料
        models.json                 模型配置资料
      sessions/
        sessions.json               Session Key 到实例与元数据的映射
        <sessionId>.jsonl           Pi 会话条目与消息树
    coding/
      agent/
      sessions/
  memory/
    main.sqlite                     main 的 Builtin Memory 索引
    coding.sqlite                   coding 的 Builtin Memory 索引
~~~

最外层的 `~/.openclaw/` 是状态根目录；Workspace 内部的 `.openclaw/workspace-state.json` 只记录这个工作目录的初始化状态。两者恰好使用相同目录名，职责分别是宿主状态管理和 Workspace 初始化管理。

`agentDir` 供模型、认证和运行配置相关组件使用。Pi 的 SessionManager 打开 `sessions/` 中的 JSONL；OpenClaw 的 Session Store 管理 `sessions.json`。MemoryIndexManager 打开 `memory/<agentId>.sqlite`，建立对 Workspace 记忆文件的检索结构。同一条请求使用这些目录中的不同文件，分别取得运行配置、会话历史和记忆索引。

`resolveStateDir` 优先处理 `OPENCLAW_STATE_DIR`，通常回到 `~/.openclaw`，并保留旧状态目录的兼容查找。配置文件另有 `OPENCLAW_CONFIG_PATH` 等解析入口。显式配置会覆盖对应的缺省路径。

### 1.3 一次普通请求的上下文准备

以未启用 Sandbox 的 coding Agent 为例，用户发来“帮我维护 TypeScript 项目”。它使用显式配置的 Workspace，已有规范文件，允许调用文件工具。OpenClaw 在进入模型请求前完成以下准备：

1. `getReplyFromConfig` 根据 agentId 解析 workspaceDir 和 agentDir，再调用 `ensureAgentWorkspace` 创建目录、按需补齐基础文件。
2. 回复层把这些路径连同 sessionFile 交给 `runEmbeddedPiAgent`；一次具体执行由 `runEmbeddedAttempt` 准备。
3. runner 调用 `resolveBootstrapContextForRun`，取得文件内容，经过过滤与字符预算处理，形成带路径的 Context Files。
4. `buildEmbeddedSystemPrompt` 将工具、Skills、工作环境和 Context Files 交给 `buildAgentSystemPrompt`，生成系统提示字符串。
5. runner 创建 Pi AgentSession，传入 cwd、模型、工具和 SessionManager，再把系统提示写入 `session.agent.state.systemPrompt`。
6. Pi 接收本轮输入，将系统提示、恢复的历史与工具 schema 组成模型请求上下文。

于是，工作目录既参与工具构造，也用于定位规范文件；规范文件的正文则经过上下文构造进入模型。首次设定尚未完成时，runner 还会在本轮输入中提示模型读取 BOOTSTRAP.md，初始化对话由同一次 Agent Loop 执行。

目录优先级影响第 1 步，Sandbox 影响第 2 步之后的工具环境，缓存、Session 过滤和 Hooks 作用于第 3 步，Prompt 模式与 Pi 适配作用于第 4—6 步。

## 2. Workspace 解析与执行环境

### 2.1 Agent 配置与运行参数

沿用第 17 章的两个 Agent，可以显式指定：

~~~json5
{
  agents: {
    list: [
      { id: "main", default: true, workspace: "~/.openclaw/workspace" },
      { id: "coding", workspace: "~/.openclaw/workspace-coding" }
    ]
  }
}
~~~

main 与 coding 的 `AGENTS.md` 分别位于各自 Workspace，规范内容、项目文件和 Memory 语料因此可以独立维护。

普通渠道回复进入 `getReplyFromConfig` 后，先用已选定的 agentId 解析目录，再准备 Workspace。相关调用是：

~~~ts
  const workspaceDirRaw = resolveAgentWorkspaceDir(cfg, agentId) ?? DEFAULT_AGENT_WORKSPACE_DIR;
  const workspace = useFastTestBootstrap
    ? (await fs.mkdir(workspaceDirRaw, { recursive: true }), { dir: workspaceDirRaw })
    : await ensureAgentWorkspace({
        dir: workspaceDirRaw,
        ensureBootstrapFiles: !agentCfg?.skipBootstrap && !isFastTestEnv,
      });
  const workspaceDir = workspace.dir;
  const agentDir = resolveAgentDir(cfg, agentId);
~~~

普通运行调用 `ensureAgentWorkspace`，快速测试环境只创建目录。`skipBootstrap` 控制模板补齐；已有文件的上下文加载由后续 Bootstrap 流程处理。

回复层把 workspaceDir、agentDir、sessionFile 等放入本次执行参数。`buildEmbeddedRunExecutionParams` 继续转交这些值，`runEmbeddedPiAgent` 管理排队、模型选择与 attempt，`runEmbeddedAttempt` 才组合本次 Pi 对象。

~~~text
getReplyFromConfig
  resolveAgentWorkspaceDir → ensureAgentWorkspace
  ↓ workspaceDir / agentDir / sessionFile
回复运行参数与 buildEmbeddedRunExecutionParams
  ↓
runEmbeddedPiAgent → runEmbeddedAttempt
  ↓
createEmbeddedAgentSessionWithResourceLoader
  ↓
createAgentSession({ cwd, agentDir, sessionManager, customTools, ... })
~~~

workspaceDir、agentDir 和 sessionFile 沿这条调用链传递到 Pi 创建过程。本地 `agentCommand` 也会先准备 Workspace，再进入执行层。

### 2.2 默认目录的解析优先级

`resolveAgentWorkspaceDir` 按当前 Agent 的显式配置、默认 Agent 身份和缺省目录依次解析：

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
~~~

函数接收完整配置、Agent ID 和环境变量，返回规范化的目录字符串；目录创建由 `ensureAgentWorkspace` 完成。

当前 Agent 的 workspace 优先级最高。未设置时，默认 Agent 直接使用 `agents.defaults.workspace`，或调用 `resolveDefaultAgentWorkspaceDir`；非默认 Agent 则使用 defaults.workspace 下的 ID 子目录，没有 defaults.workspace 时回退到状态目录下的 `workspace-<agentId>`。默认 Agent 由配置选定，可以使用 main 以外的 ID。第 2.8 节给出相应的路径对照。

### 2.3 Profile 与状态目录

`resolveDefaultAgentWorkspaceDir` 根据 home 和 Profile 构造默认 Agent 的目录：

~~~ts
  const home = resolveRequiredHomeDir(env, homedir);
  const profile = env.OPENCLAW_PROFILE?.trim();
  if (profile && normalizeOptionalLowercaseString(profile) !== "default") {
    return path.join(home, ".openclaw", `workspace-${profile}`);
  }
  return path.join(home, ".openclaw", "workspace");
~~~

例如 `OPENCLAW_PROFILE=research` 会使这个函数返回 `~/.openclaw/workspace-research`。这里直接使用 home 与 `.openclaw` 构造路径，函数没有把 `OPENCLAW_STATE_DIR` 当作 Workspace 的统一父目录。

CLI 的 Profile 处理还会设置对应的状态目录与配置路径，并保留已有的显式环境变量。默认 Agent 的 Workspace 由上述 home/Profile 分支解析；非默认 Agent 的最后一个回退分支使用状态根目录。

需要固定工作位置时，可以为 main 与 coding 分别设置 `agents.list[].workspace`，覆盖这些缺省分支。

### 2.4 Sandbox 中的工作目录

`runEmbeddedAttempt` 先规范化参数，再解析 Sandbox。局部源码为：

~~~ts
  const effectiveWorkspace = sandbox?.enabled
    ? sandbox.workspaceAccess === "rw"
      ? resolvedWorkspace
      : sandbox.workspaceDir
    : resolvedWorkspace;
~~~

`resolvedWorkspace` 是本次运行传入的工作目录；`effectiveWorkspace` 是工具等组件实际采用的工作目录。没有 Sandbox 时两者相同。Sandbox 开启且 workspaceAccess 为 `rw` 时仍使用原目录；其他访问方式使用 Sandbox 自己的目录。

两个目录参数分别传给以下组件：

| 位置 | 使用的值 | 作用 |
| --- | --- | --- |
| resolveBootstrapContextForRun | resolvedWorkspace | 读取本次指定 Workspace 的 Bootstrap 文件 |
| createOpenClawCodingTools | effectiveWorkspace | 构造工具的工作根目录与相对路径环境 |
| System Prompt 的 Workspace 信息 | effectiveWorkspace，加上 Sandbox 映射信息 | 告诉模型文件工具与容器命令应使用什么路径 |
| DefaultResourceLoader、createAgentSession 的 cwd | resolvedWorkspace | Pi 会话与资源加载的工作目录参数 |

加载后的 Context File 路径还会经 `remapInjectedContextFilesToWorkspace` 映射到 effectiveWorkspace。Pi 的 cwd 保留原运行目录，工具则通过 effectiveWorkspace、容器挂载和文件桥执行操作。

### 2.5 工作目录与文件访问权限

假设 coding 的 Workspace 是 `/srv/coding`。普通文件工具收到相对路径 `src/index.ts`，会依据其构造时的工作根目录解析；exec 也有自己的 cwd 与 Sandbox 执行环境。模型不必在每次调用中重复一个很长的绝对路径。

是否允许读取 `/srv/private/notes.md`，则还要经过工具策略、`tools.fs.workspaceOnly`、Sandbox 路径检查与操作系统权限。Workspace 只是工作位置，目录名称本身没有创建操作系统隔离边界。

例如在 TOOLS.md 写入“可以使用 deploy 工具”，不会使工具注册表出现 deploy。`createOpenClawCodingTools` 组合实际工具并执行策略过滤，模型收到的工具 schema 来自这组结果；TOOLS.md 只提供说明文字。System Prompt 也明确写明 TOOLS.md 不控制工具可用性。

AGENTS.md 的“不要执行破坏性命令”约束模型的行为选择；exec 是否可用、命令是否需要审批、容器挂载是否只读，则由配置和工具实现控制。

### 2.6 Multi-Agent 的存储与共享范围

| 资源 | main 与 coding 使用不同 Workspace 时 | 仍需核对的共享条件 |
| --- | --- | --- |
| 工作文件和 Bootstrap 文件 | 默认分别从自己的目录读取 | 显式使用同一目录、额外路径或共享挂载会扩大可见范围 |
| 模型与工具环境 | 按 Agent 配置及本次运行覆盖解析 | defaults、全局工具策略、同一 Provider 可被共同使用 |
| Session 历史 | 默认分属 agents/main/sessions 与 agents/coding/sessions | 独立 Session Key 解决会话寻址，不负责操作系统权限 |
| Memory Markdown | 分属各自 Workspace | extraPaths 可以引入共同语料 |
| Memory SQLite | 默认 main.sqlite 与 coding.sqlite | store.path 覆盖可以改变数据库位置 |
| 模型认证 | 默认有各自 agentDir | 加载器支持主认证资料合并与继承 |

`ensureAuthProfileStoreWithoutExternalProfiles` 负责认证资料合并：函数先加载当前 Agent 的 store，若它与主认证路径不同，再加载主 store 并调用 `mergeAuthProfileStores(mainStore, store)`。同名资料由当前作用域参与覆盖，上层还可叠加外部认证来源。不同 agentDir 给出不同存储位置，同时保留有意的认证共享机制。

Memory 工具根据 Session Key 解析 agentId，再由 Agent 配置确定 Memory Workspace。临时运行目录与长期记忆根目录分别解析，因此前者变化时，后者仍可能保持原有作用域。

### 2.7 文件工具的构造与路径检查

路径解析的结果随后交给工具构造过程。`createOpenClawCodingTools` 先解析 Agent 与全局工具策略，再从 fs 配置得到 workspaceOnly，形成工具的文件访问策略。

`resolveToolFsConfig` 合并全局与 Agent 的文件策略：

~~~ts
  const cfg = params.cfg;
  const globalFs = cfg?.tools?.fs;
  const agentFs =
    cfg && params.agentId ? resolveAgentConfig(cfg, params.agentId)?.tools?.fs : undefined;
  return {
    workspaceOnly: agentFs?.workspaceOnly ?? globalFs?.workspaceOnly,
  };
~~~

当前 Agent 的显式值优先，否则继承全局 tools.fs。`createToolFsPolicy` 仅在 workspaceOnly 严格等于 true 时开启统一根目录限制；具体工具还可有更窄的限制，例如 apply_patch 的默认范围控制。

接着工具层用 `resolveWorkspaceRoot(options.workspaceDir)` 得到根目录。该函数会规范化路径、展开用户目录，并拒绝把文件系统根目录直接当作有效 Workspace；无法得到合法值时回退到当前进程 cwd。正常 runner 会传入明确工作目录，工具据此确定自己的根目录。

宿主 read 工具的实际构造片段为：

~~~ts
      const freshReadTool = createReadTool(workspaceRoot);
      const wrapped = createOpenClawReadTool(freshReadTool, {
        modelContextWindowTokens: options?.modelContextWindowTokens,
        imageSanitization,
      });
      return [workspaceOnly ? wrapToolWorkspaceRootGuard(wrapped, workspaceRoot) : wrapped];
~~~

read 的构造分为三层。Pi 的 createReadTool 接收工作根目录，负责基本文件读取；OpenClaw 的 read 包装加入模型上下文、图片处理等适配；workspaceOnly 为 true 时再套根目录检查。工具同样叫 read，但它的执行函数已经由这些包装共同组成。

`wrapToolWorkspaceRootGuardWithOptions` 会取得被检查的路径参数，先进行容器路径映射，再调用 `assertSandboxPath`，通过后才执行内层工具。宿主模式也可使用这类包装实施 Workspace 根约束。

Workspace 为 `/srv/coding` 时，三类工具路径分别经过以下检查：

| 工具输入 | 解析后的意图 | workspaceOnly 开启后的判断重点 |
| --- | --- | --- |
| src/index.ts | 工作根目录中的源文件 | 必须保持在允许根目录内，且文件实际可读 |
| ../shared/design.md | 工作根目录外的相邻资料 | 根目录约束会检查这种越界 |
| /srv/private/notes.md | 明确指向另一个绝对路径 | 绝对路径仍需通过范围与别名检查 |

关闭 workspaceOnly 后，其他工具策略、专用写入边界、Sandbox 挂载与操作系统权限仍然生效。

Sandbox 路径还有额外一层：read 使用文件桥，容器内 exec 使用容器工作目录。只读 Workspace 模式会影响写工具是否加入集合；文件桥不可用时，工具构造会报告错误。模型在 Prompt 中看到路径映射说明，目的就是让它提交适合当前执行位置的路径。

### 2.8 配置与路径对照

固定默认 Agent 为 main、home 为 `/home/student`，各行配置独立：

| 配置条件 | main Workspace | coding Workspace |
| --- | --- | --- |
| 无 workspace 配置，默认状态目录 | /home/student/.openclaw/workspace | /home/student/.openclaw/workspace-coding |
| defaults.workspace = /srv/work | /srv/work | /srv/work/coding |
| defaults.workspace = /srv/work，coding 显式设置 /srv/code | /srv/work | /srv/code |
| OPENCLAW_STATE_DIR = /data/state，无 workspace 配置 | /home/student/.openclaw/workspace | /data/state/workspace-coding |

最后一行中，main 的 agentDir 与 Memory SQLite 可以位于 `/data/state`，Workspace 仍由独立的缺省算法确定。若 coding 同时显式使用 `/srv/code`，请求中的路径为：

~~~text
agentId       = coding
workspaceDir  = /srv/code
agentDir      = /data/state/agents/coding/agent
sessionFile   = /data/state/agents/coding/sessions/<本次实例>.jsonl
memory store  = /data/state/memory/coding.sqlite
~~~

工具以 `/srv/code` 为工作环境，Pi 通过 sessionFile 恢复历史，Memory 管理器打开 coding 对应的索引。

配置不变时，`/new` 替换 Session 实例，保留 workspaceDir、agentDir 和 Memory store 路径。工作文件迁移、历史文件管理和索引同步由各自的流程处理。

## 3. Workspace 初始化与首次引导

### 3.1 Workspace 文件的用途与读取入口

`ensureAgentWorkspace({ ensureBootstrapFiles: true })` 从模板补齐六种基础文件，并根据初始化状态决定是否创建 BOOTSTRAP.md。用户和 Agent 随后可以编辑这些文件；Memory 文件按需另行创建。

| 文件 | 主要内容 | 默认创建方式 | 读取与进入上下文的路径 |
| --- | --- | --- | --- |
| AGENTS.md | 工作规范、协作与文件使用约定 | 初始化时按模板补齐 | Bootstrap 候选，经 Session、运行模式与预算过滤后注入 |
| SOUL.md | 角色、语气、行为边界 | 初始化时按模板补齐 | 同上；Prompt 明确提示遵循其角色与语气 |
| USER.md | 用户资料、称呼与偏好 | 初始化时按模板补齐，之后可编辑 | 同上 |
| IDENTITY.md | Agent 名称与身份描述 | 初始化时按模板补齐，首次对话可更新 | 同上 |
| TOOLS.md | 环境说明、工具使用约定 | 初始化时按模板补齐 | 同上；实际工具来自注册和策略过滤 |
| HEARTBEAT.md | 周期检查的任务内容 | 初始化时按模板补齐 | 普通加载有 Heartbeat 条件；Heartbeat 运行另有调度入口 |
| BOOTSTRAP.md | 新 Workspace 的首次身份与偏好设定步骤 | 仅在合适的初始化阶段补种 | embedded runner 从 Context Files 中剔除，再按 BootstrapMode 提示主动读取 |
| BOOT.md | Gateway 启动时希望执行的检查或任务 | 用户自行配置 | 启用 boot-md Hook 后，gateway:startup 触发 runBootOnce 读取 |

表中的默认创建以允许模板补齐为前提；skipBootstrap 和已有自定义内容会改变初始化结果。

MEMORY.md 则按需由用户、模型工具或特定维护流程创建。它若存在，会成为 Bootstrap 加载候选；Daily Memory 有独立的启动上下文入口和检索入口，第 6 节再展开。

### 3.2 coding 的规范与用户偏好

假设初始化后，用户把 coding 的文件修改为以下短段落：

~~~text
AGENTS.md：优先检查项目已有测试，不要擅自执行破坏性命令。
SOUL.md：回答时使用严谨、简洁的技术语言。
USER.md：用户主要使用 TypeScript，希望解释重要实现细节。
TOOLS.md：项目通过 pnpm 管理，测试命令以 package.json 为准。
~~~

模型接到“帮我修改某个函数”时，AGENTS.md 引导它先了解已有验证方式；TOOLS.md 给出查找命令的环境线索；USER.md 影响解释的侧重点；SOUL.md 影响最终语言。这些指令以文件段落进入模型上下文，实际执行仍要选择工具并调用它的 schema。

测试执行还需要模型读取 package.json、找到项目命令，再调用已启用的执行工具。工具不可用时，Agent 只能完成当前权限允许的工作。

文件修改在重新加载后进入上下文；同一 Session 复用 Bootstrap 快照时可能继续使用旧内容。快照的失效条件见第 4.6 节。

### 3.3 目录创建与模板补齐

`ensureAgentWorkspace` 首先创建目录。没有要求补齐 Bootstrap 时，它直接返回 `{ dir }`。允许补齐时，才解析模板、检查文件和记录状态。

模板通常来自分发中的 `docs/reference/templates`。`loadTemplate` 通过 `resolveWorkspaceTemplateDir` 定位目录，读取对应文件，并去掉模板前面的 YAML front matter，使标题、summary 等文档元数据不被原样写入用户 Workspace。模板内容在进程中缓存；模板丢失会抛出明确错误。

补齐普通文件使用 `writeFileIfMissing`：

~~~ts
async function writeFileIfMissing(filePath: string, content: string): Promise<boolean> {
  try {
    await fs.writeFile(filePath, content, {
      encoding: "utf-8",
      flag: "wx",
    });
    return true;
  } catch (err) {
    const anyErr = err as { code?: string };
    if (anyErr.code !== "EEXIST") {
      throw err;
    }
    return false;
  }
}
~~~

`wx` 要求创建新文件；文件已存在时返回 false，不覆盖内容。空文件同样算已经存在，所以用户主动清空 HEARTBEAT.md 或其他文件，不会仅因为下一次准备 Workspace 就重新被模板填满。

`isBrandNewWorkspace` 检查六种模板路径，以及 memory、MEMORY.md、.git 等内容迹象，主要用于决定是否尝试初始化 Git 仓库。BOOTSTRAP.md 的创建另由 Workspace 状态判断。

### 3.4 初始化状态：seeded、completed 与 pending

Workspace 状态文件保存的核心字段为：

~~~ts
 type WorkspaceSetupState = {
   version: typeof WORKSPACE_STATE_VERSION;
   bootstrapSeededAt?: string;
   setupCompletedAt?: string;
 };
~~~

其中 version 为 1。`bootstrapSeededAt` 表示引导文件曾经被补种或被观察到；`setupCompletedAt` 表示 Workspace 设定已完成。写状态时先写临时 JSON，再 rename 替换正式状态文件。

`ensureAgentWorkspace` 按以下条件更新状态：

1. BOOTSTRAP.md 已存在而尚无 seeded 记录，补记 bootstrapSeededAt。
2. 已有 seeded 记录、文件已不存在且尚未 completed，记录 setupCompletedAt。
3. 文件和两个标记都不存在，检查 USER.md、IDENTITY.md 是否偏离模板，或是否已有 memory、MEMORY.md、.git 等内容。
4. 若看出这是已配置的旧 Workspace，记录完成；否则写入 BOOTSTRAP.md 模板并记录 seeded。

第 3 步识别已有工作目录。首次初始化前已有定制 USER.md 或 IDENTITY.md 时，系统可能直接记录设定完成。第 3.2 节的例子采用先初始化模板、再修改文件的顺序。

运行准备时的 pending 判断更直接：

~~~ts
export async function resolveWorkspaceBootstrapStatus(
  dir: string,
): Promise<"pending" | "complete"> {
  const resolvedDir = resolveUserPath(dir);
  const state = await readWorkspaceSetupStateForDir(resolvedDir);
  if (typeof state.setupCompletedAt === "string" && state.setupCompletedAt.trim().length > 0) {
    return "complete";
  }
  const bootstrapExists = await fileExists(path.join(resolvedDir, DEFAULT_BOOTSTRAP_FILENAME));
  return bootstrapExists ? "pending" : "complete";
}
~~~

完成标记优先；没有完成标记时再看文件存在性。因此，删除文件以后，即使下一次 ensure 尚未把 completed 写回状态文件，运行准备也可以判断为 complete。反过来，文件仍存在且没有 completed 标记时，一轮普通回答并不会自动让 Workspace 完成初始化。

### 3.5 首次对话与引导结束

模板要求模型通过对话了解 Agent 的名称、身份、表达方式和用户信息，随后更新 IDENTITY.md、USER.md，讨论 SOUL.md，并在完成后删除 BOOTSTRAP.md。

这些步骤由当前 Pi Agent Loop 中的模型和文件工具执行：OpenClaw 判断初始化状态并提供提示，模板给出对话与文件更新要求。

若第一句话只是“你好，我希望你帮我维护 TypeScript 项目”，模型可以先确认工作定位、记下已知偏好，再询问剩余必要信息。是否在这一轮完成全部初始化，取决于获得的信息及工具执行结果。引导未完成则保留文件，后续合适的交互仍可能继续。

文件删除并被初始化逻辑识别后，后续 ensure 保留完成状态，不会每轮重建 BOOTSTRAP.md。`/new` 切换的是 Session；Workspace 的完成状态还留在原目录中。

### 3.6 BootstrapMode 的选择

`resolveBootstrapMode` 的输入包含 pending、runKind、交互触发、主运行判断、目录是否为规范 Workspace、是否有文件读取能力：

~~~ts
  if (!params.bootstrapPending) {
    return "none";
  }
  if (params.runKind === "heartbeat" || params.runKind === "cron") {
    return "none";
  }
  if (!params.isPrimaryRun || !params.isInteractiveUserFacing) {
    return "none";
  }
  if (!params.hasBootstrapFileAccess) {
    return "none";
  }
  return params.isCanonicalWorkspace ? "full" : "limited";
~~~

runner 将 `user`、`manual` trigger 视为面向用户的交互。`isPrimaryBootstrapRun` 排除 Subagent 与 ACP Session；其他 Agent 也可满足主运行条件。hasBootstrapFileAccess 要求模型支持工具，且本次工具集合中有 read。

- `full`：提示读取 BOOTSTRAP.md 并完成可完成的步骤。
- `limited`：说明当前运行不能安全完成规范 Workspace 的全部初始化，继续可做部分并给出下一步。
- `none`：不加这段首次引导前缀。

Sandbox 工作副本和非规范目录会影响 full/limited 判断。Heartbeat、Cron 和子代理执行返回 none，继续处理各自任务。

BootstrapMode 控制首次引导提示；SOUL.md 等文件的加载由上下文模式与 Session 过滤控制。

## 4. Bootstrap 文件加载与上下文转换

### 4.1 Bootstrap File 与 Context File

磁盘文件加载后首先表示为 WorkspaceBootstrapFile：

~~~ts
export type WorkspaceBootstrapFile = {
  name: WorkspaceBootstrapFileName;
  path: string;
  content?: string;
  missing: boolean;
};
~~~

`name` 保留已知 Bootstrap 文件名，供允许名单和特殊处理使用；`path` 指向文件位置；`content` 保存读取到的原文；`missing` 使加载阶段能够表示“这个预期文件不可用”。

后续 `EmbeddedContextFile` 的核心是 `path` 与 `content`。这时缺失提示和长度裁剪已经转换为可放进 Prompt 的文字，文件名仍保留在路径中。

~~~mermaid
flowchart TD
    A["loadWorkspaceBootstrapFiles"] --> B["WorkspaceBootstrapFile 数组"]
    B --> C["Session 与 contextMode 过滤"]
    C --> D["agent:bootstrap Hook 调整"]
    D --> E["路径检查与 Heartbeat 过滤"]
    E --> F["buildBootstrapContextFiles"]
    F --> G["EmbeddedContextFile 数组"]
    G --> H["runner 路径映射、移除 BOOTSTRAP.md"]
    H --> I["buildAgentSystemPrompt"]
~~~

`resolveBootstrapContextForRun` 协调图中的处理过程：先调用 `resolveBootstrapFilesForRun` 完成读取与过滤，再调用 `buildBootstrapContextFiles` 转换结构。返回的 contextFiles 由 runner 继续处理并交给 Prompt 构造函数。

### 4.2 候选文件与边界读取

固定候选顺序为：

~~~text
AGENTS.md → SOUL.md → TOOLS.md → IDENTITY.md → USER.md
→ HEARTBEAT.md → BOOTSTRAP.md → 可选 MEMORY.md / memory.md
~~~

前七项无论存在与否都要形成加载结果。Memory 条目通过 `resolveMemoryBootstrapEntry` 选择：优先存在的 MEMORY.md；只有它不存在时才尝试 memory.md；两者都没有就不追加 Memory 条目。这里的大小写回退减少了大小写不敏感文件系统上重复注入同一文件的问题。

BOOT.md、DREAMS.md 和 `memory/YYYY-MM-DD.md` 分别由启动 Hook、记忆维护或 Daily Memory 读取路径处理，不在这份固定列表内。

每个候选交给 `readWorkspaceFileWithGuards`。该函数调用 `openBoundaryFile`，把 workspaceDir 作为读取边界，并把单文件上限设为 `2 * 1024 * 1024` 字节。边界检查会核对规范路径、文件类型、大小和打开后的文件身份；越出 Workspace 的符号链接目标不能通过，硬链接也默认被拒绝。指向边界内普通文件的符号链接也需要通过路径验证与安全打开检查。

这个 2 MiB 是磁盘读取安全上限。稍后注入 Prompt 时还有字符预算，二者用途不同。

读取成功形成 `missing: false`；读取失败、缺失或安全验证不通过时，普通加载路径形成 `missing: true`。上层得到的是不可用占位，不会把失败文件的内容继续送给模型。空文件则读取成功，只是在构造 Context Files 时通常没有可注入正文。

### 4.3 Session 类型与上下文过滤

`filterBootstrapFilesForSession` 对普通 Session 直接返回候选；对 Subagent 与 Cron Session 保留下面五种文件：

~~~text
AGENTS.md、TOOLS.md、SOUL.md、IDENTITY.md、USER.md
~~~

这一步会移除 MEMORY.md、HEARTBEAT.md、BOOTSTRAP.md 等其他候选。它按 Session Key 类别判断，没有普通私聊与群聊之间的统一 MEMORY.md 过滤条件。

再往后，`applyContextModeFilter` 处理 `BootstrapContextMode`：

| contextMode / runKind | 在这一层留下什么 |
| --- | --- |
| full，任意 runKind | 保留前一步结果 |
| lightweight + heartbeat | 只保留前一步结果中的 HEARTBEAT.md |
| lightweight + cron/default | 返回空数组 |

各层过滤依次缩小候选集合。例如 Session 类型已移除 HEARTBEAT.md 时，后续 lightweight heartbeat 分支得到的仍是空结果。

Heartbeat 的 `heartbeat.lightContext`、Subagent 的 lightContext 和 Cron 的轻量运行参数参与 contextMode 选择。后台运行的文件集合由 Session 类型、runKind 和 contextMode 共同决定。

最后还有专门的 Heartbeat 过滤：对默认 Agent 的非 heartbeat 运行，如果不应包含 Heartbeat 系统提示，会排除 HEARTBEAT.md。这个判断结合 Agent 的 Heartbeat 参与策略、周期和 includeSystemPromptSection。这项排除规则针对默认 Agent，非默认 Agent 不经过同一判断。

### 4.4 单文件与总量预算

默认：

| 配置 | 默认值 | 计量对象 |
| --- | --- | --- |
| agents.defaults.bootstrapMaxChars | 12,000 | 单个文件被注入的内容 |
| agents.defaults.bootstrapTotalMaxChars | 60,000 | 所有 Context File 内容的累计预算 |
| agents.defaults.bootstrapPromptTruncationWarning | once | 截断警告的去重模式 |

预算按 JavaScript 字符串长度计算并执行安全裁剪，约束的是 Context File 内容。模型 token 数与 System Prompt 的其他段落在这一预算之外。

`buildBootstrapContextFiles` 按收到的数组顺序遍历，维护 remainingTotalChars：

~~~ts
    const fileMaxChars = Math.max(1, Math.min(maxChars, remainingTotalChars));
    const trimmed = trimBootstrapContent(file.content ?? "", file.name, fileMaxChars);
    const contentWithinBudget = clampToBudget(trimmed.content, remainingTotalChars);
    if (!contentWithinBudget) {
      continue;
    }
~~~

实际逻辑先处理 missing：生成 `[MISSING] Expected at: ...`，并扣除它占用的总预算。对于存在文件，剩余预算不足 64 字符时停止加入更多文件；空内容跳过。每个加入结果的内容都会从总预算中扣减。

例如单文件预算为 100、总预算为 150，首个文件加入 100 字符后仅剩 50，低于普通文件所需的最小剩余预算 64，后续普通文件将被跳过。

### 4.5 首尾裁剪与截断提示

`trimBootstrapContent` 先移除尾部空白。过长时预留截断标记与分隔符，然后把剩余正文预算按约 75% 与 25% 分给开头和结尾。标记中提示读取原文件获得完整内容，并列出保留长度和原长度；预算很小时使用更短标记。

比例分配以扣除标记后的正文空间为基数。实现通过迭代处理标记长度变化，再约束最终长度。

runner 用 `analyzeBootstrapBudget`、`buildBootstrapPromptWarning` 生成统计与提示，并在 System Prompt Report 中记录截断状态。报告说明本次哪些文件被注入或被裁剪；它不会修改磁盘原文。

预算处理早于 embedded runner 剔除 BOOTSTRAP.md。该文件可能先占用预算；移除后，剩余文件沿用已经生成的 Context Files。

### 4.6 文件缓存与 Session 快照

文件加载采用两层缓存。

第一层是实际读取函数的文件内容缓存。其 identity 包含规范路径、device、inode、size、mtimeMs；只有身份和状态一致时才复用正文。再次进入这层读取且文件发生相应变化时，会重新获取内容。

第二层是 `getOrLoadBootstrapFiles` 保存的 Session 快照：

~~~ts
export async function getOrLoadBootstrapFiles(params: {
  workspaceDir: string;
  sessionKey: string;
}): Promise<WorkspaceBootstrapFile[]> {
  const existing = cache.get(params.sessionKey);
  if (existing) {
    return existing;
  }

  const files = await loadWorkspaceBootstrapFiles(params.workspaceDir);
  cache.set(params.sessionKey, files);
  return files;
}
~~~

`resolveBootstrapFilesForRun` 收到 sessionKey 时走这层快照；没有 sessionKey 时直接加载 Workspace 文件。快照键只有 sessionKey，没有把 Workspace 路径和文件 mtime 拼进去。因此，命中快照后连底层读取都不会再执行。

用户在同一 Session 中修改 SOUL.md，下一轮仍可能使用旧快照；第一次记录为 missing 的文件，即使后来创建，也可能继续保持旧快照中的缺失状态。模型主动调用 read 是另一条实时读取路径，不受这个 Bootstrap 快照的同一种缓存控制。

`/new`、`/reset` 及 Session rollover 的相关处理会调用 `clearBootstrapSnapshot` 或 `clearBootstrapSnapshotOnSessionRollover`。新的加载因此能看到更新后的文件。只修改 Workspace 配置并沿用同一个 sessionKey 时，仍需要使快照失效，底层文件读取才会重新发生。

### 4.7 Bootstrap Hook 扩展

`applyBootstrapHookOverrides` 把 workspaceDir、sessionKey、agentId、配置和当前 bootstrapFiles 放入 `agent:bootstrap` 事件：

~~~ts
  const event = createInternalHookEvent("agent", "bootstrap", sessionKey, context);
  await triggerInternalHook(event);
  const updated = (event.context as AgentBootstrapHookContext).bootstrapFiles;
  return Array.isArray(updated) ? updated : params.files;
~~~

这里等待的是 Hook 调用过程。Hook 可以替换 `event.context.bootstrapFiles`，返回后才继续构造 Context Files；这个阶段不会运行 Pi 的模型循环。

内置 `bootstrap-extra-files` Hook 可以按配置加载额外的已识别 Bootstrap 文件名，并再次应用 Session 过滤。自定义 Hook 的调整发生在前面的通用过滤之后，具有扩展候选集合的能力；后续 `sanitizeBootstrapFiles` 主要核对 path 是否是有效非空字符串，不会把所有内容重新当磁盘文件再读一遍。

Hook 的改动作用于本次上下文数组；磁盘文件保持原状，除非 Hook 自身另行执行文件写入。

## 5. System Prompt 构造与 Pi 交接

### 5.1 系统提示的组成

`buildEmbeddedSystemPrompt` 接收 effectiveWorkspace、工具数组、Skills 提示、上下文文件、环境信息、Sandbox 信息等，再把工具数组转换为工具名集合，调用 `buildAgentSystemPrompt`。

返回的系统提示字符串按以下顺序组织主要段落：

~~~text
基础身份：You are a personal assistant running inside OpenClaw.

Tooling：本次可用工具与使用约定
Tool Call Style / 执行与安全说明 / CLI 提示
Skills：可用技能及读取规则
Memory Recall：由已注册 Memory Capability 提供的检索指导
模型别名等条件段落
Workspace：工作目录与文件操作说明
Documentation / Sandbox / 授权发送者 / 时区等条件段落
Workspace Files (injected)：解释下方 Context Files 的来源
回复、消息与语音等条件段落

Project Context：排序后的稳定文件正文
Silent Replies：完整模式下的静默回复约定
系统 Prompt 缓存边界
Dynamic Project Context：例如 HEARTBEAT.md
Group Chat Context 或 Subagent Context
Provider 的动态补充
Heartbeats：满足条件时的 Heartbeat 指令
Runtime：Agent、模型、系统、渠道及推理设置
~~~

以上为系统提示结构摘要。Provider 贡献、系统提示覆盖、自定义 Context Engine 与 Plugin Hook 可以进一步调整内容。

Memory Recall 位于 Project Context 之前，提供 memory_search 和 memory_get 的使用指导。检索在后续模型产生工具调用时执行。

### 5.2 Context Files 的排序与来源

构造阶段先去掉 path 无效的条目，再由 `sortContextFilesForPrompt` 排序。稳定文件的主要顺序是：

~~~text
AGENTS.md → SOUL.md → IDENTITY.md → USER.md → TOOLS.md
→ BOOTSTRAP.md → MEMORY.md
~~~

其中 BOOTSTRAP.md 是通用排序表中的条目，在本文 embedded 路径中已被移除。未列出的文件再按 basename 和规范化路径排序。预算按加载结果的顺序消耗，最终展示再按这份顺序排序。

每个文件被组织成自己的 Markdown 小节，核心拼接如下：

~~~ts
  for (const file of params.files) {
    lines.push(`## ${file.path}`, "", sanitizeContextFileContentForPrompt(file.content), "");
  }
~~~

文件路径作为小节标题保留来源，content 经过特定文本清理与多余空行规整后跟在标题下。

HEARTBEAT.md 被归为动态 Context File，放在缓存边界之后。稳定规范文件位于前面，频繁变化的任务和运行信息位于后面。传输适配可利用这一分组复用稳定的 Prompt 前缀；稳定内容与动态内容仍属于同一次请求。

### 5.3 AgentSession 创建与系统提示设置

runner 准备 DefaultResourceLoader 并 reload，将 OpenClaw 管理的工具转换为 Pi customTools，同时用注册名称构造 tools allowlist，然后创建 Pi AgentSession：

~~~ts
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
~~~

`createEmbeddedAgentSessionWithResourceLoader` 将 options 交给提供的 createAgentSession 回调。Pi 建立 Agent 和 AgentSession 之后，runner 调用 `applySystemPromptOverrideToSession`，把最终系统文字写到：

~~~ts
  session.agent.state.systemPrompt = prompt;
~~~

该函数同时设置 Session 内部的 `_baseSystemPrompt` 与 `_rebuildSystemPrompt`。后续工具集合更新时，Session 重建系统提示仍使用 OpenClaw 设置的内容。

此前课程分析过 Pi 的请求构造：Agent 生成上下文快照时取得 `state.systemPrompt`、消息和工具；Agent Loop 经 transformContext、convertToLlm 后形成下面的请求上下文：

~~~ts
const llmContext: Context = {
  systemPrompt: context.systemPrompt,
  messages: llmMessages,
  tools: context.tools,
};
~~~

streamFunction 接收模型、llmContext 和请求选项，Provider 适配再将系统文字转换为协议字段。OpenClaw 提供的身份、规范、Skills、Memory Recall 与环境说明由此进入模型请求。

Session JSONL 恢复的历史位于 messages 一侧，Workspace 注入主要位于 systemPrompt 一侧，Memory 工具结果则在执行后成为新的 toolResult 消息。它们最终汇合在同一次模型输入里，但来源和更新方式仍然不同。

### 5.4 coding 首次启动时序

coding 使用规范 Workspace，未启用 Sandbox，允许补齐模板并具备所需文件工具。新目录先完成模板初始化，再填入第 3.2 节的四份说明，首次请求按以下时序执行：

~~~mermaid
sequenceDiagram
    participant User as 用户
    participant Init as Workspace 准备
    participant Run as OpenClaw runner
    participant Disk as Workspace 文件
    participant Pi as Pi AgentSession
    Init->>Disk: ensureAgentWorkspace 补齐基础文件
    Init->>Disk: 创建 BOOTSTRAP.md，记录 seeded
    User->>Run: 希望维护 TypeScript 项目
    Run->>Disk: 判断 pending，加载 Bootstrap 候选
    Disk-->>Run: 文件内容与缺失状态
    Run->>Run: 过滤、裁剪、移除 BOOTSTRAP.md
    Run->>Run: 构造系统提示与 full 引导前缀
    Run->>Pi: 创建 Session，覆盖 systemPrompt，提交输入
    Pi->>Disk: 模型调用 read 读取 BOOTSTRAP.md
    Disk-->>Pi: 首次设定步骤
    opt 本轮获得足够信息且工具执行成功
        Pi->>Disk: 更新身份、用户资料，删除 BOOTSTRAP.md
    end
    Pi-->>Run: 本次 Agent 执行结果
    Run->>Run: 满足条件时记录 full-context 条目
    Init->>Disk: 后续 ensure 观察删除，记录 completed
~~~

用户之所以在第一轮就能看到预设技术语气和工作规范，是四份文件已进入系统上下文；是否完成身份引导，则取决于当前 Loop 是否按 BOOTSTRAP.md 执行到结束。若文件尚未删除且 Workspace 未 completed，下一次符合条件的交互仍会继续引导。

### 5.5 首次引导的用户输入前缀

`resolveAttemptBootstrapRouting` 返回 BootstrapMode、是否剔除引导文件以及 userPromptPrefixText。 `shouldStripBootstrapFromEmbeddedContext` 总是返回 true。runner 在 Context Files 中移除 BOOTSTRAP.md 后，另在提交用户输入前执行：

~~~ts
        if (userPromptPrefixText) {
          effectivePrompt = `${userPromptPrefixText}\n\n${effectivePrompt}`;
        }
~~~

full 模式的前缀要求“读取 Workspace 中的 BOOTSTRAP.md，并在正常回复之前处理它”。因此，BOOTSTRAP.md 的内容通过模型主动 read 后的工具结果参与执行；普通规范文件则走 System Prompt 的 Project Context。

该读取依赖本次运行中的 read 工具。limited 模式提供限制说明，none 不添加前缀。

### 5.6 四类运行模式的职责

运行准备中的四类模式作用于不同阶段：

| 字段或类型 | 典型值 | 影响 |
| --- | --- | --- |
| BootstrapMode | full / limited / none | 是否提示执行首次 BOOTSTRAP.md 引导 |
| BootstrapContextMode | full / lightweight | 加载哪些 Workspace Context Files |
| agents.defaults.contextInjection | always / continuation-skip | 连续运行是否跳过已有的 Bootstrap 上下文 |
| PromptMode | full / minimal / none | buildAgentSystemPrompt 生成哪些系统段落 |

一个 Workspace 已完成设定，BootstrapMode 可以是 none，而 AGENTS.md、SOUL.md 仍继续按 full Context 模式注入。子代理常用 minimal Prompt，它仍有必要的工具和工作环境信息；PromptMode 为 none 则直接返回最基本的一句身份说明。

### 5.7 continuation-skip 与完成标记

`agents.defaults.contextInjection` 默认是 always。可选的 continuation-skip 会检查 Session JSONL 中的 `openclaw:bootstrap-context:full` 自定义条目。

`resolveAttemptBootstrapContext` 的关键判断为：当前 BootstrapMode 不是 full、配置为 continuation-skip、运行不是 heartbeat，并且 `hasCompletedBootstrapTurn(sessionFile)` 找到有效完成标记。成立时直接返回空的 bootstrapFiles/contextFiles。

runner 仅在符合记录条件的 full Bootstrap 运行结束后，且本次未发生 prompt 错误、中止、压缩超时或压缩时追加它。读取时最多检查 JSONL 尾部 256 KiB 与最后 500 条记录；若较新的 compaction 位于标记之后，该标记失效，本次需要重新加载上下文。

这条路径涉及三类状态：Workspace 的 setupCompletedAt、Session JSONL 中的 full-context 标记、进程内的 Bootstrap 文件快照。前者控制首次设定；第二个参与 continuation-skip；第三个控制原始文件是否重新读取。一次 `/new` 可以让新 Session 重新取得上下文，同时保留 Workspace 已完成的设定。

### 5.8 BOOT.md 与 HEARTBEAT.md 的触发

BOOT.md 不属于普通 Bootstrap 候选。启用 `boot-md` 内部 Hook 后，`gateway:startup` 事件使 handler 枚举 Agent，按各自 Workspace 调用 `runBootOnce`。该函数读取 BOOT.md，文件缺失或为空时跳过，其他读取错误返回 failed。

有正文时，runBootOnce 把它放入一次 boot-check 输入，生成独立的 boot Session ID，经 agentCommand 运行；它保留并恢复主 Session 映射，设置 deliver 为 false。deliver 为 false 关闭常规结果投递；若任务要求主动发消息，模型仍可调用被允许的 message 工具。

BOOT.md 是启动任务输入，之后仍交由通常的 Agent 执行能力处理。用户修改它，影响下一次相应启动触发；仅保存文件不会立刻执行一次 boot check。

HEARTBEAT.md 保存周期检查内容，调度时间由 Heartbeat 配置与 heartbeat runner 决定。Heartbeat 运行使用专门的 prompt，lightContext 可只保留必要的上下文；没有可执行事项时，可按条件跳过或返回 HEARTBEAT_OK。普通聊天即使注入了该文件，仍按普通请求执行。

## 6. 长期记忆的持久化与读取范围

### 6.1 从事实写入到跨 Session 检索

Alice 要求 Agent 记住 TypeScript、可维护性与测试偏好。正常持久化过程包含三个相互衔接的阶段。

模型先选择文件工具，将事实写入 Workspace Markdown。工具完成后，原文已经可读；Memory 管理器随后通过文件变化或同步入口发现更新，重新切块、生成缺失的 Embedding，并写入 SQLite。新 Session 提问时，模型调用 memory_search 取得候选 Chunk，再按路径和行号调用 memory_get，最后依据读到的内容回答。

写入工具返回、索引同步完成和检索结果返回，是三个独立的完成点。Watcher 安排的同步在后台推进，所以新原文与新索引可以在不同时间变得可见。这个过程涉及以下数据：

| 数据 | 保存的内容 | 下一次使用方式 |
| --- | --- | --- |
| 当前 Agent 的 messages | 本次执行可见的用户、assistant 与工具消息 | 直接参与当前请求 |
| Session JSONL | 某个 Session 的消息、分支与其他条目 | SessionManager 按当前树路径恢复上下文 |
| Compaction Summary | 为当前 Session 后续推理保留的摘要 | 从该 Session 的 compaction 条目重建消息上下文 |
| MEMORY.md | 跨会话使用的稳定事实、偏好与决策 | 合适运行中的 Bootstrap 注入、read 或 Memory 工具 |
| memory/YYYY-MM-DD.md | 当日工作记录、阶段性事实与决策 | 启动上下文、工具读取、索引检索 |
| Memory SQLite | 文件状态、Chunk 文本、Embedding、检索结构 | MemoryIndexManager 查询 |
| memory_search 返回值 | 与这一次 query 相关的候选片段 | 本轮 toolResult，供模型继续读取和回答 |

`/new` 创建新的 Session 实例，原有 Memory 文件与索引继续保留。新运行取得事实后，它才成为本次模型上下文的一部分。

### 6.2 Memory 文件的组织

USER.md 适合姓名、称呼、时区、解释偏好等用户资料；AGENTS.md 说明当前工作空间的协作规则；MEMORY.md 适合经过整理的长期事实、稳定项目知识和重要决策。这些分类通过文件约定组织内容，具体条目由用户、模型和维护流程选择。

Daily Memory 以日期组织工作记录。例如 `memory/2026-10-08.md` 可以记录当天确定的测试策略、架构选择与待办。日期方便后续选择近期内容，也为可选的时间衰减提供线索。默认文件扫描会递归读取 memory 下的 Markdown，所以 `memory/project-decisions.md` 或子目录中的主题文件同样可以被索引；文件名不必全部符合日期格式。

新 Workspace 通常尚无 MEMORY.md 和 memory/，初始化函数不会为每条消息创建它们。创建与编辑可以来自用户，也可以来自模型调用文件工具。长期文件应经过有意识的维护，否则重复、过时与互相矛盾的事实会一起进入检索语料。

普通 write 与 edit 分别按覆盖或替换语义修改文件。向已有 Daily Memory 增补时，模型或用户需要选择适当的编辑操作；第 13 节的 Flush 则使用专门的追加包装。

### 6.3 用户偏好的文件写入

用户输入进入 messages 后，模型根据要求和文件指导选择持久化目标，再调用可用的 write/edit。调用成功，磁盘内容才发生变化；若模型没有调用工具、工具被策略移除或写入失败，偏好仍可能只留在当前会话中。

Alice 的偏好写入 `memory/2026-10-08.md`。本例中该文件的完整内容为以下三行，末尾不附加空行：

~~~markdown
用户主要使用 TypeScript。
代码组织优先考虑可维护性。
修改前检查项目已有测试，并根据改动运行相关验证。
~~~

写入完成后，memory_get 可以直接读到这三行；memory_search 的可见性还取决于索引更新。

### 6.4 近期 Daily Memory 的启动注入

Daily Memory 除了通过工具读取，还可由回复层的 `buildSessionStartupContextPrelude` 加入新 Session 的启动输入。

`getReplyRun` 中与它有关的条件如下：

~~~ts
  const startupContextPrelude =
    isBareSessionReset &&
    bareResetPromptState?.shouldPrependStartupContext !== false &&
    shouldApplyStartupContext({ cfg, action: startupAction })
      ? await buildSessionStartupContextPrelude({
          workspaceDir,
          cfg,
        })
      : null;
~~~

该入口由 isBareSessionReset 控制，包含裸 `/new`、`/reset`，以及被识别为 soft reset 的运行。前缀与 reset prompt 共同组成 `baseBodyForPrompt`，进入本轮用户输入；普通 Bootstrap 则通过 System Prompt 的 Project Context 注入。

首次 Bootstrap 尚未完成且 reset prompt 采用 full/limited 引导时，shouldPrependStartupContext 为 false，以免与初始化任务混杂。设置 `agents.defaults.startupContext.enabled: false` 会关闭这项加载；applyOn 可以选择 new 或 reset。

默认读取范围与预算为：

| 项目 | 默认处理 |
| --- | --- |
| 日期窗口 | 用户时区中的今天和前一天，dailyMemoryDays 为 2 |
| UTC 日期差异 | 若 UTC 当天不在本地窗口中，补入该日期候选 |
| 同日文件 | 先尝试 YYYY-MM-DD.md，再选最多 4 个最新的同日前缀文件 |
| 文件大小检查 | maxFileBytes 为 16,384 字节，超过读取边界限制的文件不纳入 |
| 单文件正文 | maxFileChars 为 1,200，过长时裁剪 |
| 记忆块总预算 | maxTotalChars 为 2,800，封装与截断提示还参与具体组装 |

同日前缀文件例如 `2026-10-08-project-review.md`；它们按修改时间与文件名排序后选择。所有候选还需通过 Workspace 边界读取，缺失或空白内容跳过。

前缀把正文放进 `[Untrusted daily memory: ...]` 与引用块中，明确要求把它当背景资料，忽略其中夹带的指令。这种封装将笔记内容作为数据提供给模型，当前操作授权仍来自本次请求与运行策略。

近期笔记加载可以直接提供当天偏好。较早的事实、未选中的文件和被裁剪的内容，仍需后续检索或精确读取。

### 6.5 启动上下文与模板约定

AGENTS.md 模板要求优先使用 runtime-provided startup context；只有用户明确要求、上下文缺少所需内容，或者需要更深的后续阅读时，才手工重读启动文件。

规范文件可由 Bootstrap 注入，近期 Daily Memory 可由 reset 前缀加载。模型只有需要补充缺失内容或深入读取时，才再次访问文件。

模板还约定 MEMORY.md 仅在 main session 使用。加载实现中，`loadWorkspaceBootstrapFiles` 按文件存在性加入 MEMORY.md，`filterBootstrapFilesForSession` 对 Subagent/Cron 采用五文件允许名单；普通群聊和其他用户的私聊没有统一的 MEMORY.md 排除判断。因此，多用户访问范围还需要由 Agent、Workspace 与工具策略落实。

### 6.6 Agent 与用户的记忆作用域

main 与 coding 使用不同 Workspace 时，默认分别维护 MEMORY.md、Daily Memory 和每 Agent 的 SQLite 文件。

两个 Agent 使用同一 Workspace 时，会读取相同的记忆文件。默认 SQLite 仍按 agentId 分开，因此可能出现两份索引对应同一批共享原文的情况。

同一 Agent 下的 Alice 与 Bob 又是另一层问题。即使上一章已经用 per-channel-peer 分离两人的 Session，它们仍可能使用同一 Workspace 和同一 Agent 的 Memory 索引。Builtin 的查询主体按 agentId 与 memory/sessions 来源过滤，没有对每个 Chunk 增加 Alice/Bob 的独立读权限字段。

| 场景 | 默认 Bootstrap 观察 | Memory 工具还需注意什么 |
| --- | --- | --- |
| 普通私聊 | 可能包含已有 MEMORY.md | 查询的是该 Agent 的语料范围 |
| 普通群聊 | 通用过滤没有统一排除 MEMORY.md | 与其他 Session 共享的语料仍需独立访问控制 |
| Subagent / Cron Session | 五文件允许名单移除 MEMORY.md 等 | 工具是否存在由工具策略继续判断；工具若被允许，范围还要按工具实现分析 |
| 两个独立 Workspace 的 Agent | 通常各读自己的文件 | extraPaths、store.path 与显式共享可改变范围 |

保存私人资料前，需要确定 Agent、Workspace、extraPaths 和工具策略的访问范围。Session 历史按用户分开时，共享 Memory 的权限仍需独立配置。

### 6.7 可选的 session-memory Hook

启用 `session-memory` 内部 Hook 后，`command:new` 或 `command:reset` 会触发 `saveSessionToMemory`。它优先取得重置前的 previousSessionEntry，读取近期会话内容，默认使用 15 条消息作为选取参数，再写入 `memory/YYYY-MM-DD-<slug>.md`。

日期在这条 Hook 中使用事件时间的 UTC 日期；slug 可以由额外模型请求生成，也可以回退到时间字符串。文件正文由程序组织会话标识、来源和选取的对话内容；额外模型调用用于生成 slug，正文保留所选会话内容。

该 Hook 在 new/reset 命令时保存会话片段，使用带 slug 的日期文件。普通聊天中的文件写入由模型选择，Memory Flush 则依据运行预算触发，并限定到当天的 `YYYY-MM-DD.md`。

## 7. memory-core 的能力与工具注册

### 7.1 Memory Capability、工具与 CLI

默认 Memory slot 指向 `memory-core`，默认 Backend 为 builtin。前者选择哪个插件提供记忆能力，后者选择该能力使用哪种检索实现；配置上分别涉及 plugins.slots.memory 与 memory.backend。

`memory-core` 的 register 中先登记 Embedding Provider 适配器和可选维护能力，再注册 Memory Capability：

~~~ts
    api.registerMemoryCapability({
      promptBuilder: buildPromptSection,
      flushPlanResolver: buildMemoryFlushPlan,
      runtime: memoryRuntime,
      publicArtifacts: {
        listArtifacts: listMemoryCorePublicArtifacts,
      },
    });
~~~

这组字段各自用于系统提示构造、Flush Plan 生成、Memory runtime 和记忆产物枚举。宿主通过这组注册接口调用插件能力。

工具注册是另一组调用：

~~~ts
    api.registerTool(
      (ctx) =>
        createMemorySearchTool({
          config: ctx.config,
          agentSessionKey: ctx.sessionKey,
        }),
      { names: ["memory_search"] },
    );

    api.registerTool(
      (ctx) =>
        createMemoryGetTool({
          config: ctx.config,
          agentSessionKey: ctx.sessionKey,
        }),
      { names: ["memory_get"] },
    );
~~~

插件注册时登记工具工厂；构造某次运行工具集合时，`resolvePluginTools` 用运行上下文调用工厂，取得工具对象。CLI 另有注册入口，提供 memory 状态、搜索与索引命令。

### 7.2 工具工厂与 Agent 配置

`createMemorySearchTool` 与 `createMemoryGetTool` 共用 `createMemoryTool`。其中 `resolveMemoryToolContext` 做两件关键事：

1. 必须有可用配置。
2. 根据 agentSessionKey 解析 agentId，再调用 `resolveMemorySearchConfig`。

若当前 Agent 的 Memory Search 被禁用，工厂返回 null。插件未激活、Memory slot 被关闭或换成其他实现时，是否还有同名工具也要依据实际注册结果判断。

`createOpenClawTools` 通过 `resolveOpenClawPluginToolsForOptions` 汇入插件工具；外围 `createOpenClawCodingTools` 继续执行 Provider、工具 profile、Agent、用户授权和 Subagent 等策略过滤。工具注册成功与“这次模型能看到该工具”之间还隔着这层选择。

最终被允许的工具才转换为 Pi customTools，出现在工具 schema 和可执行集合中。模型调用 memory_search 时，才进入该工具的 execute。

### 7.3 Memory Recall 系统提示

`buildAgentSystemPrompt` 中的 Memory 段落来自注册的 promptBuilder。在普通完整 Prompt、使用相应 Memory 段落且工具可用时，`buildPromptSection` 生成 Memory Recall。

- search 与 get 都有：先检索过去工作、决策、日期、人物、偏好、待办，再按需要精确读行。
- 只有 search：依据匹配结果回答。
- 只有 get：已有明确文件或笔记位置时读取所需部分。
- 两个工具都没有：不生成这段检索指导。

minimal Prompt 或显式关闭 Memory 段落时也会跳过。runner 对自定义 Context Engine 还有单独的 includeMemorySection 条件，使上下文管理实现可以接管相关职责。

Memory Recall 中的 indexed session transcripts 指已纳入索引的会话记录。默认 sources 只有 memory；Session Transcript 索引需要第 8.4 节的配置。

### 7.4 memory_search 与 memory_get 的参数

`MemorySearchSchema` 的定义是：

~~~ts
export const MemorySearchSchema = Type.Object({
  query: Type.String(),
  maxResults: Type.Optional(Type.Number()),
  minScore: Type.Optional(Type.Number()),
  corpus: Type.Optional(
    Type.Union([Type.Literal("memory"), Type.Literal("wiki"), Type.Literal("all")]),
  ),
});
~~~

query 是查询文本，maxResults 限制希望返回的结果数，minScore 给出分数门槛。corpus 默认走 Memory 语料；wiki/all 用于已经注册的 Wiki 补充语料，后面简述。

`MemoryGetSchema` 则为：

~~~ts
export const MemoryGetSchema = Type.Object({
  path: Type.String(),
  from: Type.Optional(Type.Number()),
  lines: Type.Optional(Type.Number()),
  corpus: Type.Optional(
    Type.Union([Type.Literal("memory"), Type.Literal("wiki"), Type.Literal("all")]),
  ),
});
~~~

path 指定文件或对应 Backend 可解析的位置；from 是从 1 开始的行号；lines 是要读多少行，执行层按整数处理。search 查找候选，get 获取一个明确位置的正文，两者适合连续使用。

### 7.5 偏好查询的工具输入与输出

假设 Alice 问“我之前说过代码应该怎么组织？”，模型选择调用 memory_search，参数可以是：

~~~json
{
  "query": "TypeScript 代码组织 可维护性 测试",
  "maxResults": 3,
  "minScore": 0.35
}
~~~

检索目标是第 6.3 节的三行文件。假设向量候选分数为 0.90、关键词路径未命中，则默认 Hybrid 权重得到 0.63；以下返回示例采用 OpenAI Embedding，普通私聊的 citations 为 auto。

~~~json
{
  "results": [
    {
      "path": "memory/2026-10-08.md",
      "startLine": 1,
      "endLine": 3,
      "score": 0.63,
      "snippet": "用户主要使用 TypeScript。\n代码组织优先考虑可维护性。\n修改前检查项目已有测试，并根据改动运行相关验证。\n\nSource: memory/2026-10-08.md#L1-L3",
      "source": "memory",
      "citation": "memory/2026-10-08.md#L1-L3",
      "corpus": "memory"
    }
  ],
  "provider": "openai",
  "model": "text-embedding-3-small",
  "citations": "auto",
  "debug": {
    "backend": "builtin",
    "effectiveMode": "n/a",
    "searchMs": 12,
    "hits": 1
  }
}
~~~

`jsonResult` 将该对象包装为工具结果，并序列化为模型可读的文本。fallback、mode 等可选值缺失时不写入 JSON。Builtin 在工具层的 debug.effectiveMode 固定显示 n/a，内部检索流程由管理器决定。

snippet 是有长度预算的候选片段。模型如果需要确认完整措辞或相邻内容，可以继续调用 memory_get：

~~~json
{
  "path": "memory/2026-10-08.md",
  "from": 1,
  "lines": 3
}
~~~

文件共三行，本次精确读取返回：

~~~json
{
  "text": "用户主要使用 TypeScript。\n代码组织优先考虑可维护性。\n修改前检查项目已有测试，并根据改动运行相关验证。",
  "path": "memory/2026-10-08.md",
  "from": 1,
  "lines": 3
}
~~~

文件后面仍有内容时，返回值可增加 `truncated: true`、nextFrom，并在 text 后附续读提示。

模型据此形成回答。search/get 的结果作为本轮 toolResult 保留在当前会话中；未来 Session 再次使用这些事实时，需要相应的读取或检索。

### 7.6 memory_get 的读取范围与预算

Builtin Backend 下，memory_get 直接调用 `readAgentMemoryFile`，继而进入 `readMemoryFile`，无须先创建 Embedding Provider 或搜索管理器。这使精确读取与向量服务是否可用相对独立。

它先把相对路径解析到 Agent Workspace，检查是否属于允许的记忆路径或配置的 extraPaths，再要求 Markdown 后缀及合法普通文件。常规记忆路径包含 MEMORY.md、memory.md、DREAMS.md 和 memory/ 下的文件；允许读取的集合与默认索引扫描集合并不完全相同。

缺省读取从第 1 行开始，最多选择 120 行，再受 12,000 字符正文预算限制。Agent 的 contextLimits 可以覆盖默认行数和字符预算。`buildMemoryReadResult` 先按行切片，`buildMemoryReadResultFromSlice` 再处理字符截断与续读位置。

返回文本还可能附加续读提示，整个 JSON 也包含定位字段，因而总长度可超过正文预算。单行文本自身超限时，工具会说明硬截断情况及原文读取方式。

对 Builtin 的普通记忆路径，文件已消失可以返回空 text 与 path；非法路径、读取失败等会由工具转换为 disabled/error 结果。search 的不可用结果则还可包含 unavailable、warning、action 等字段，用来区分“没有找到相关内容”和“检索本身不可用”。

## 8. Memory 语料与 SQLite 索引

### 8.1 索引构建与查询

少量长期事实可以直接放进 MEMORY.md，但 Daily Memory 会随工作持续增加。如果每次提问都把几年笔记全部加入上下文，读取成本、Prompt 长度和无关信息都会增长。

检索把任务分成两步：后台把可搜索的文本组织起来；提问时只找与 query 相关的片段。Builtin Memory 的 SQLite 因而同时保存文件状态、Chunk 文本和搜索辅助结构。Markdown 仍然是用户可以阅读、编辑和迁移的原文来源。

~~~mermaid
flowchart TD
    Files["MEMORY.md 与 memory/ Markdown"] --> Scan["listMemoryFiles / buildFileEntry"]
    Scan --> Changed["比较文件 hash"]
    Changed -->|"需要更新"| Chunk["chunkMarkdown"]
    Chunk -->|"Provider 可用"| Embed["缓存复用 / Embedding 请求"]
    Embed --> Write["writeChunks"]
    Chunk -->|"无 Provider：FTS-only"| Write
    Write --> DB["SQLite：chunks、FTS 与可用向量表"]
    Query["memory_search query"] --> Search["关键词与向量候选"]
    DB --> Search
    Search --> Merge["合并、排序与过滤"]
    Merge --> Result["片段返回本轮 Agent"]
~~~

图中的 Embedding 分支只有在 Provider 可用时才参与。没有 Provider 时仍可以形成 FTS-only 索引与搜索。

### 8.2 Backend 选择与管理器创建

工具先调用 `getMemorySearchManager({ cfg, agentId })`。`resolveMemoryBackendConfig` 解析 memory.backend：默认 builtin；配置 qmd 时尝试 QMD 管理器，必要时有返回 Builtin 的路径。

默认路径加载 `MemoryIndexManager` 并调用它的静态 get。get 先解析当前 Agent 的 Memory Search 配置、Workspace，再决定创建还是复用实例。实例缓存键包含：

~~~ts
    const key = `${agentId}:${workspaceDir}:${JSON.stringify(settings)}:${purpose}`;
~~~

purpose 可区分正常工作与状态检查。构造函数打开数据库、确保 schema、建立来源集合，并在非 status-only 模式准备文件 Watcher、Session 更新监听和可选周期同步；Provider 初始化则延后处理，以减少仅查询状态或建立对象时的额外工作。

`MemorySearchManager` 定义对外接口，`MemoryIndexManager` 实现 Builtin 管理器。它继承索引与 Embedding 操作类，search 再调用 manager-search、hybrid 和存储辅助函数完成查询。

### 8.3 文件扫描范围

`resolveMemorySearchConfig` 合并 `agents.defaults.memorySearch` 与当前 Agent 的 memorySearch 覆盖。默认 enabled 为 true，sources 为 `["memory"]`，experimental.sessionMemory 为 false。

`listMemoryFiles` 的普通扫描范围为：

- Workspace 根目录中的 MEMORY.md 与 memory.md，如果确实是普通 Markdown 文件。
- Workspace 的 memory/ 目录下递归发现的 `.md` 文件。
- 配置 extraPaths 中的 Markdown 文件或目录；相对路径以 Workspace 为基准，绝对路径按配置处理。

目录遍历跳过符号链接和非普通文件，并在最后按 realpath 去重。Bootstrap 加载只选择大小写 Memory 文件中的一个，而索引扫描会尝试两者再去重；在大小写敏感文件系统中，两个独立文件确实可能都参与索引。

extraPaths 合并默认配置和 Agent 覆盖后去重。它可以扩展到 Workspace 外的共享语料，Agent 的最终 Memory 范围由 Workspace 与 extraPaths 共同确定。

DREAMS.md 虽然可被 memory_get 精确读取，却不在这里的根目录默认扫描列表；要让根目录 DREAMS.md 参与默认这条索引流程，需要把它纳入额外路径等实际配置。memory/ 下的 Dreaming 报告则按普通 Markdown 扫描规则处理。

### 8.4 Session Transcript 的可选索引

`normalizeSources` 对 sessions 的准入是：

~~~ts
    if (source === "sessions" && sessionMemoryEnabled) {
      normalized.add("sessions");
    }
~~~

因此，典型启用配置应同时包含：

~~~json5
{
  agents: {
    defaults: {
      memorySearch: {
        sources: ["memory", "sessions"],
        experimental: { sessionMemory: true }
      }
    }
  }
}
~~~

sources 中包含 sessions 且 experimental.sessionMemory 开启时，Session 来源才进入索引集合。

启用后，Session 文件由独立扫描与同步路径处理，会先把选取的消息转换成可索引文本，再用 lineMap 把 Chunk 行号映射回原始 JSONL 行。它们的 source 标记为 sessions，和 memory 文件来源并列。会话语料范围按当前 Agent 确定。

### 8.5 SQLite 表结构与数据关系

默认数据库路径由 `resolveStorePath` 构造为状态根目录下的 `memory/<agentId>.sqlite`。`memorySearch.store.path` 可覆盖，且支持用 `{agentId}` 填入 Agent ID。

主要结构如下：

| 表或结构 | 关键字段 | 作用 |
| --- | --- | --- |
| meta | key、value | 保存索引配置元数据，主要键为 memory_index_meta_v1 |
| files | path 主键、source、hash、mtime、size | 判断文件是否变化、清理已删除文件 |
| chunks | id 主键、path、source、start_line/end_line、hash、model、text、embedding、updated_at | 保存可检索文本块及向量 JSON |
| embedding_cache | provider、model、provider_key、hash 复合主键，embedding、dims、updated_at | 相同 Provider 配置与内容复用向量 |
| chunks_fts | FTS5 虚拟表，text 为全文索引内容，其余定位字段 UNINDEXED | 关键词匹配与 BM25 排序 |
| chunks_vec | sqlite-vec 的 vec0 虚拟表，id 与 FLOAT[dimensions] | 原生向量候选查询 |

其中 chunks 的实际建表片段为：

~~~sql
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'memory',
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  hash TEXT NOT NULL,
  model TEXT NOT NULL,
  text TEXT NOT NULL,
  embedding TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
~~~

embedding 列保存向量的 JSON 字符串；FTS-only 模式可保存空数组。可用的 chunks_vec 另存 Float32 向量，用同一个 Chunk ID 与 chunks 关联。

文件、Chunk 与搜索结构通过 path 和 id 关联，schema 未声明 SQL 外键：

~~~text
files
  path = memory/2026-10-08.md
  hash = H(完整文件)
        │ 同一路径
        ├── chunks.id = H(source:path:起行:止行:块hash:model)
        │     text / embedding / start_line / end_line
        │         ├── chunks_fts.id → 用于文本检索
        │         └── chunks_vec.id → 用于向量检索
        └── 该文件的另一条 Chunk

embedding_cache
  (provider, model, provider_key, 块hash) → 可复用向量
~~~

SQLite 的意义是把这些可本地查询的数据结构放在一个数据库中，并支持文件增量状态、全文查询和可选向量扩展。磁盘 Markdown、数据库中的 Chunk 文本、Embedding 数组和 FTS/vec 索引各有职责；删除索引可以重建，删除原文则改变了持久记忆来源。

## 9. Markdown 切块与原文定位

### 9.1 检索粒度与上下文重叠

一个 Daily Memory 文件可能同时包含用户偏好、某次故障与一个项目决策。若整个文件只生成一个向量，query 与无关内容会一起计算，返回结果也难以定位。Chunk 把检索单位缩小到附近几行，使工具能够返回路径、起止行和片段。

Chunk 太小会失去前后关系；太大容易混合多个主题。overlap 保留相邻块之间的部分内容，降低一句话或一组连续决策在边界处被分开的影响。

默认 chunking.tokens 为 400、overlap 为 80。它们是预算参数，具体算法没有调用模型 tokenizer 对每行精确分词。

### 9.2 token 预算与 CJK 加权估算

`chunkMarkdown` 的起始部分为：

~~~ts
  const lines = content.split("\n");
  if (lines.length === 0) {
    return [];
  }
  const maxChars = Math.max(32, chunking.tokens * CHARS_PER_TOKEN_ESTIMATE);
  const overlapChars = Math.max(0, chunking.overlap * CHARS_PER_TOKEN_ESTIMATE);
  const chunks: MemoryChunk[] = [];
~~~

`CHARS_PER_TOKEN_ESTIMATE` 为 4，因此默认正文预算是 1,600 个加权字符单位，重叠目标是 320 个单位。每行的实际累计量来自 `estimateStringChars(line) + 1`，其中额外的 1 用于估计换行。

`estimateStringChars` 对普通拉丁文本基本按字符串长度计数，对其正则覆盖的 CJK 等字符增加权重，使一个相应字符按约 4 个单位参与预算。它还处理部分 CJK 扩展区字符的 UTF-16 代理对。

实际文本容量取决于各类字符的权重。这里采用估算预算，模型 tokenizer 对同一文本得到的 token 数仍可能不同。

### 9.3 按行处理与长行切分

算法先按换行得到 lines，再顺序处理每行。普通长度的行直接成为一个 segment；很长的行先按 maxChars 做粗切分，若某段加权长度仍超过预算，再按更小步长切开，并避免在相关细分路径中劈开代理对。

标题、空行和列表均作为文本行参与预算，算法按行与加权长度切块。由于没有解析 Markdown 标题树，同一标题下的内容可以分布在多个 Chunk 中。

处理每个 segment 的核心为：

~~~ts
    for (const segment of segments) {
      const lineSize = estimateStringChars(segment) + 1;
      if (currentChars + lineSize > maxChars && current.length > 0) {
        flush();
        carryOverlap();
      }
      current.push({ line: segment, lineNo });
      currentChars += lineSize;
    }
~~~

current 保存当前块中的文本和原始行号，currentChars 保存累计预算。加入新段将超限时，先输出当前块，再从旧块尾部保留 overlap，最后加入新段。处理完全部行后，最后一次 flush 输出剩余内容。

### 9.4 Chunk 生成、行号与文本 hash

flush 取当前第一段和最后一段的 lineNo，拼接文本并形成：

~~~ts
    const text = current.map((entry) => entry.line).join("\n");
    const startLine = firstEntry.lineNo;
    const endLine = lastEntry.lineNo;
    chunks.push({
      startLine,
      endLine,
      text,
      hash: hashText(text),
      embeddingInput: buildTextEmbeddingInput(text),
    });
~~~

行号从 1 开始，供搜索结果与引用使用。长行切成多个 segment 后仍保留原始行号，因此多个 Chunk 可以定位到原文中的同一行。

hashText 使用 SHA-256，对当前 Chunk 文本求 hash。它首先描述内容相同性；真正的数据库 Chunk ID 还会在写入时加入来源、路径、起止行和模型。

### 9.5 overlap 的回收过程

`carryOverlap` 从 current 尾部向前累计：

~~~ts
    let acc = 0;
    const kept: Array<{ line: string; lineNo: number }> = [];
    for (let i = current.length - 1; i >= 0; i -= 1) {
      const entry = current[i];
      if (!entry) {
        continue;
      }
      acc += estimateStringChars(entry.line) + 1;
      kept.unshift(entry);
      if (acc >= overlapChars) {
        break;
      }
    }
    current = kept;
    currentChars = acc;
~~~

acc 达到目标时停止回收。最后保留的行段可能使其超过 overlapChars，因此实际重叠量由完整行段共同决定。

carryOverlap 后会立即加入新 segment，保留的重叠与新段相加可能超过 maxChars。后续 Provider 索引路径通过 `enforceEmbeddingMaxInputTokens` 再处理输入限制；切块参数主要控制检索粒度与估算预算。

### 9.6 中文笔记的切块推导

取下面 10 行文本，末尾不额外添加空行：

~~~markdown
# 用户偏好

用户主要使用 TypeScript。
代码应当优先保证可维护性。
修改前应运行项目已有测试。

# 项目记录

项目采用 pnpm。
主要模块位于 packages 目录。
~~~

取 `tokens: 32, overlap: 8`，则 maxChars 为 128，overlapChars 为 32。各行按同一加权规则计算：

| 行号 | 内容概要 | estimateStringChars + 1 |
| --- | --- | ---: |
| 1 | # 用户偏好 | 19 |
| 2 | 空行 | 1 |
| 3 | 用户主要使用 TypeScript。 | 40 |
| 4 | 代码应当优先保证可维护性。 | 53 |
| 5 | 修改前应运行项目已有测试。 | 53 |
| 6 | 空行 | 1 |
| 7 | # 项目记录 | 19 |
| 8 | 空行 | 1 |
| 9 | 项目采用 pnpm。 | 26 |
| 10 | 主要模块位于 packages 目录。 | 47 |

前四行总量为 113；加入第 5 行将变成 166，于是输出 Chunk 1。重叠从第 4 行开始，单行 53 已达到 32 的目标，因此保留第 4 行，再加入第 5 行。

接着，第 4—8 行共 127；第 9 行到来时再次输出。尾部第 8、7、6 行只有 `1 + 19 + 1 = 21`，还不足 32，于是继续保留第 5 行，实际 overlap 成为 74。加入第 9 行后，当前总量为 100。

第 10 行让当前总量超出 128，再输出一次；这次从第 9 行向前保留第 9、8、7 行，共 46，然后加入第 10 行形成最后一个块。

最终结果为：

| Chunk | 原文行范围 | 累计加权量 | 与前块共享的原文 |
| --- | --- | ---: | --- |
| 1 | 1—4 | 113 | 无 |
| 2 | 4—8 | 127 | 第 4 行 |
| 3 | 5—9 | 100 | 第 5—8 行 |
| 4 | 7—10 | 93 | 第 7—9 行 |

Chunk 2 的最后一项是第 8 行空行，拼接结果保留相应的尾部换行。表中的累计量包含每个 segment 的换行估算，与拼接后的 text.length 分别计算。

标题随行位置进入不同块，overlap 使部分内容重复出现。检索合并按 Chunk ID 去重，处理两条路径命中的同一个块；不同 ID 的相邻重叠块仍可同时入选，可选 MMR 用于进一步减少结果冗余。

### 9.7 文件更新与 Chunk 标识

写入数据库时，ID 的实际组成是：

~~~ts
      const id = hashText(
        `${source}:${entry.path}:${chunk.startLine}:${chunk.endLine}:${chunk.hash}:${model}`,
      );
~~~

如果用户在文件开头插入一段文字，后面某段内容本身未变，但行号可能改变，因此 Chunk ID 也可能变化。Embedding 缓存则使用内容 hash 与 Provider 配置标识等作为键，仍可能复用这段未变文本的向量。

索引更新先比较整份文件 hash，变化后重新切块并替换该文件的索引记录。Embedding 缓存可复用内容未变的向量，降低文件级更新的重复计算成本。

## 10. Embedding 与索引同步

### 10.1 Embedding Provider 与模型选择

Embedding 将文本映射为数值数组，用向量关系度量语义相关性。Provider 决定请求的服务或本地实现，model 指定 Embedding 模型，返回数组长度确定向量维度。

聊天模型与 Embedding 模型分别解析，可以选择不同模型和 Provider。

`MemoryIndexManager.loadProviderResult` 把配置、Agent 的 agentDir、解析后的 Provider/model 等交给 `createEmbeddingProvider`。通过注册的 MemoryEmbeddingProviderAdapter 选择实现。memory-core 自身注册 local，OpenAI、Google、Voyage、Mistral 等 Provider 插件分别提供相应适配器。

在 `provider: "auto"` 下，函数按适配器 autoSelectPriority 排序尝试。上述适配器的顺序为符合自动选择条件的 local、openai、gemini、voyage、mistral。local 仅在配置了实际存在的本地模型文件时进入自动候选，默认远程模型地址不满足这一条件。

某个适配器缺少凭据等、且声明可以继续自动选择时，会尝试下一项；无法继续的初始化错误仍可能抛出。配置显式 Provider 时，失败是否转用另一个 Provider 由 fallback 控制，默认 fallback 为 none。

### 10.2 Provider 缺失与请求失败

自动选择走完仍没有合适适配器，可以返回：

~~~ts
    return {
      provider: null,
      requestedProvider: "auto",
      providerUnavailableReason:
        reasons.length > 0 ? reasons.join("\n\n") : "No embeddings provider available.",
    };
~~~

管理器据此运行 FTS-only 模式，直接建立文本索引并执行关键词查询。

已有 Provider 的 query Embedding 请求失败时，`embedQueryWithTimeout` 的错误可以向工具层传播，形成 disabled/unavailable 结果。索引同步中的部分错误则可激活配置好的 fallback Provider 并重建。

Provider 为 null 对应正常的 FTS-only 工作模式；Provider 请求报错则需要按具体失败路径处理。

### 10.3 indexFile 的文本与向量分支

`indexFile(entry, { source, content? })` 接收文件元数据与来源。普通 Memory 文件可从磁盘读取正文，Session 来源可以传入预处理后的 content。

无 Provider 的主要片段为：

~~~ts
      const content = options.content ?? (await fs.readFile(entry.absPath, "utf-8"));
      const chunks = filterNonEmptyMemoryChunks(chunkMarkdown(content, this.settings.chunking));
      if (options.source === "sessions" && "lineMap" in entry) {
        remapChunkLines(chunks, entry.lineMap);
      }
      this.writeChunks(entry, options.source, "fts-only", chunks, [], false);
      return;
~~~

有 Provider 时，普通 Markdown 同样先切块，再经过 Provider 输入限制处理，随后取得 Embedding。默认走 `embedChunksInBatches`；配置并支持远端 Batch API 时才进入另一条 batch job 路径。

向量返回后，函数选择一个非空向量样本，以它的 length 调用 `ensureVectorReady`，再把文本、向量和索引信息交给 `writeChunks`。vec0 表由此采用与 Embedding 结果一致的维度。

### 10.4 Embedding 缓存与批量请求

`embedChunksInBatches` 先调用 `collectCachedEmbeddings`，返回位置对齐的 embeddings 和 missing 列表。若没有缺失项，直接返回缓存数组。

缺失的 Chunk 进入分批请求：

~~~ts
    const { embeddings, missing } = this.collectCachedEmbeddings(chunks);

    if (missing.length === 0) {
      return embeddings;
    }

    const missingChunks = missing.map((m) => m.chunk);
    const batches = buildMemoryEmbeddingBatches(missingChunks, EMBEDDING_BATCH_MAX_TOKENS);
    const toCache: Array<{ hash: string; embedding: number[] }> = [];
~~~

每批调用 Provider 的 embedBatch，返回向量按原 Chunk 位置填回 embeddings，再调用 `upsertMemoryEmbeddingCache`。这种普通批量请求默认可用。另一个配置 `remote.batch.enabled` 控制异步远端 Batch 作业，默认关闭。

例如文件有 8 个 Chunk，5 个内容 hash 已在相同 Provider 配置缓存中，实际只需为另外 3 个请求向量。即使重建了该文件的 chunks 行，也不必重复计算全部 8 个 Embedding。

缓存键包含 provider、model、provider_key 和 hash。provider_key 可以纳入适配器提供的模型、服务地址和影响结果的配置数据，避免仅凭文本相同就误用不同服务设置生成的向量。

### 10.5 Chunk 与索引记录写入

`writeChunks` 先清理该 path/source 的旧 Chunk 相关数据，再逐块写入 chunks；有可用向量表时写入 chunks_vec；FTS 可用时写入 chunks_fts；最后更新 files 中的文件 hash、mtime 和 size。

向量在 chunks.embedding 中以 JSON 保存，在 chunks_vec 中以 Float32 blob 保存。前者也支持 sqlite-vec 不可用时的应用层余弦计算，后者用于原生候选查询。Embedding 缓存则独立保存可复用计算结果。

如果某文件从磁盘删除，后续 sync 对比 activePaths 与旧 files 记录，清理该文件的 files/chunks/FTS/vec 数据。同步完成后，删除的文件不再产生检索候选。

meta 的 memory_index_meta_v1 值记录 provider、model、providerKey、sources、scopeHash、chunkTokens、chunkOverlap、vectorDims、ftsTokenizer 等。名称中的 v1 标识这组元数据的版本；建表代码通过列检查兼容部分旧 schema。

### 10.6 增量更新与索引重建

`shouldRunFullMemoryReindex` 比较当前配置与 meta，包括 Provider/model/providerKey、语料来源、额外范围与多模态配置摘要、切块参数、FTS tokenizer，以及向量结构所需维度信息是否缺失等条件。

显式 force 也可以要求重建。普通生产路径优先走 `runSafeReindex`，为新索引准备单独的数据库并在成功后切换；只有特定测试环境开关才走不安全的直接重建分支。

模型变化后，检索按当前 model 过滤 Chunk，重建流程生成与新模型匹配的索引数据。向量维度变化时，vec0 表也重新建立对应维度。

配置不要求全量重建时，`syncMemoryFiles` 比较文件 hash：相同文件跳过，变化文件重新进入 indexFile。文件 mtime 和 size 是元数据，但内容 hash 才是这一层决定是否重新索引的主要比较值。

### 10.7 索引同步的触发与等待

| 入口 | 默认设置 | 实际动作与等待关系 |
| --- | --- | --- |
| 文件 Watcher | watch 为 true；watchDebounceMs 为 1,500 | add/change/unlink 标记 dirty，稳定等待与 debounce 后启动同步 |
| warmSession | onSessionStart 为 true | 在管理器搜索路径首次遇到某个 Session Key 时，后台安排 session-start 同步 |
| search 时刷新 | onSearch 为 true | 已有索引时，发现 dirty/sessionsDirty 后启动后台同步 |
| 首次搜索发现索引为空 | search 的独立引导分支 | await 一次 force sync，再判断是否有可搜索内容 |
| 周期同步 | intervalMinutes 为 0 | 默认不设周期；配置正数后由定时器触发 |
| 手工索引 | 用户请求相关 Memory CLI 操作 | 可等待同步完成，force 可用于重建 |

Watcher 先经过 awaitWriteFinish 稳定性检查与 debounce，再推进排队、扫描、Embedding 请求和数据库写入。因此，1,500 毫秒是 debounce 参数，新增内容的可检索时间还取决于整个同步过程。

Builtin 的 warmSession 由 search 调用，用 sessionWarm 集合记录已预热的 Session Key，内部以 `void this.sync(...)` 安排后台工作。onSessionStart 因而作用于这条预热路径。

首查空库则明确等待：

~~~ts
    if (!hasIndexedContent) {
      try {
        // A fresh process can receive its first search before background watch/session
        // syncs have built the index. Force one synchronous bootstrap so the first
        // lookup after restart does not fail closed with empty results.
        await this.sync({ reason: "search", force: true });
      } catch (err) {
        log.warn(`memory sync failed (search-bootstrap): ${String(err)}`);
      }
      hasIndexedContent = this.hasIndexedContent();
    }
~~~

空库分支通过 await 等待索引任务的 Promise 完成，内部 I/O 仍按异步方式执行。已有索引时，搜索刷新通常不等待，本次查询可使用更新前的内容。

### 10.8 文件修改后的索引可见性

假设 SQLite 已经有旧索引，Alice 的新偏好通过工具写入了 Daily Memory：

~~~text
t0  write/edit 完成：Markdown 已更新
t1  Watcher 观察变化：dirty = true，安排 debounce
t2  用户立即发起搜索：可能仍从旧索引返回
t3  sync 扫描文件：文件 hash 改变，重新切块
t4  缓存复用与缺失 Embedding 计算结束，写入 SQLite
t5  后续搜索可从新索引取得新增片段
~~~

无可用 Provider 时，t4 执行纯文本 FTS 写入；Embedding 请求失败时，索引更新可能中止。

memory_get 直接读取原文，能够取得尚未同步到索引的修改；memory_search 返回当前索引中的候选。

## 11. Memory Search 的检索与排序

### 11.1 检索信号与候选预算

原文记录了 Alice 对 TypeScript、代码可维护性与测试的偏好，查询却可能是“之前我们定下的编程习惯是什么”。查询没有完整重复原文术语，Embedding 仍有机会把两段相近含义映射到相近方向。

另一些查询依赖准确文字，例如 SessionManager、某个配置键或具体 Session Key。关键词检索对这类内容很有价值：它可以要求某个术语确实出现在索引文本中，减少只因主题相近而返回无关段落的情况。

Hybrid Search 分别取得两组候选，将相同 Chunk 的两种信号合并评分。仅被其中一条路径命中的 Chunk 也参与合并。

在第 10 节的空库引导、query 规范化与后台同步之后，管理器解析：

~~~ts
    const minScore = opts?.minScore ?? this.settings.query.minScore;
    const maxResults = opts?.maxResults ?? this.settings.query.maxResults;
    const hybrid = this.settings.query.hybrid;
    const candidates = Math.min(
      200,
      Math.max(1, Math.floor(maxResults * hybrid.candidateMultiplier)),
    );
~~~

默认 maxResults 为 6，minScore 为 0.35，candidateMultiplier 为 4，所以每路先取得最多 24 个候选。候选上限硬限制为 200；配置中的 multiplier 还会被规范化到 1—20。

先放宽候选、再统一筛选，使两个检索结果有足够的合并空间。若向量侧一开始就只取最终 6 个结果，一些文本侧很强、向量侧稍低的片段可能过早被排除。

配置解析会把 vectorWeight/textWeight 约束到合法范围后归一化。默认 `0.7 + 0.3 = 1`；两者配置后都为零时回退默认权重。下面的计算都使用默认值。

### 11.2 Query Embedding 与余弦相似度

索引时每个 Chunk 已有向量；搜索时 `embedQueryWithTimeout(cleaned)` 将 query 转为同一 Provider/model 的查询向量。数组存在非零分量时，才继续向量查询。

相似度采用余弦关系。对于同维向量 q 与 x：

$$
\operatorname{cos}(q,x)=\frac{q\cdot x}{\lVert q\rVert\lVert x\rVert}
$$

取二维向量 q = (1, 1)，计算结果如下：

| Chunk 向量 | 点积 | 模长乘积 | 余弦相似度 |
| --- | ---: | ---: | ---: |
| (1, 1) | 2 | 2 | 1 |
| (1, 0) | 1 | √2 | 约 0.7071 |
| (-1, 0) | -1 | √2 | 约 -0.7071 |

Embedding 模型通常输出更高维的向量，具体维数由模型及其配置决定；方向与语义的对应关系由模型学习。

余弦值可以为负，返回的向量分数保留这一取值范围。minScore 则是单独规范化的筛选门槛。

### 11.3 sqlite-vec 查询与应用层回退

`searchVector` 首先尝试 `ensureVectorReady(queryVec.length)`。扩展可用时，把 queryVec 转为 Float32 blob，以 vec0 的 MATCH/KNN 语法选候选。其 SQL 结构如下，注释标出动态追加的来源过滤位置：

~~~sql
SELECT c.id, c.path, c.start_line, c.end_line, c.text,
       c.source,
       vec_distance_cosine(v.embedding, ?) AS dist
  FROM chunks_vec v
  JOIN chunks c ON c.id = v.id
 WHERE v.embedding MATCH ? AND k = ? AND c.model = ?
       /* 此处追加已启用来源的过滤条件 */
 ORDER BY dist ASC
 LIMIT ?
~~~

vec0 建表使用默认距离进行 KNN 候选选择；SELECT 再显式计算 vec_distance_cosine，用 `score = 1 - dist` 得到最终向量分数。候选选择与最终评分分别使用各自的距离表达式。

为了减轻 model/source 后置过滤使候选不足的问题，初始 KNN k 采用候选 limit 的 8 倍。按默认 24 个候选计算，第一次 KNN 请求 192；如果过滤后仍不足且数据库中还有可匹配内容，代码还可能扩大 KNN 范围后重新查询。这个扩展是向量查询内部的候选选择，与 Hybrid 的 candidateMultiplier 是两个层次。

原生扩展不可用时，`listChunks` 从 chunks 取出当前 model 与来源下的 embedding JSON，在应用层逐个计算余弦相似度：

~~~ts
  const scored = candidates
    .map((chunk) => ({
      chunk,
      score: cosineSimilarity(params.queryVec, chunk.embedding),
    }))
    .filter((entry) => Number.isFinite(entry.score));
~~~

之后降序排序并取 limit。余弦辅助函数处理零向量等异常输入，非有限结果被过滤。该回退路径继续使用已有 Embedding，在应用代码中完成 Vector Search；Provider 为 null 时才进入 FTS-only 分支。

候选返回 path、startLine、endLine、score、source 和 snippet。snippet 截取 Chunk 原文头部最多 700 字符；行范围仍指向完整 Chunk，因此展示文本可能短于该范围，也可能未包含位于后半段的搜索词。

### 11.4 FTS5 索引与 MATCH 查询

FTS5 是 SQLite 的全文检索虚拟表模块。chunks_fts 为 text 建立文本检索结构，使查询可以通过 MATCH 找到包含相应 token 的行；id、path、source、model、start_line、end_line 标为 UNINDEXED，主要用于定位与过滤。

搜索 SessionManager 时，MATCH 在 Chunk 正文的索引中查找该术语。path 字段只作为元数据保存，FTS-only 排序中的 path boost 也只对已经命中的候选加分。

默认 tokenizer 为 unicode61。可配置 trigram，建表时使用 `tokenize='trigram case_sensitive 0'`；Tokenizer 改变还会参与重建条件。

FTS5 在这里承担“哪些文本行符合查询”和“怎样获得 BM25 rank”两个任务，文本最终仍可通过 id/path/行号回到原文件。

`buildFtsQuery` 从原 query 中取字母、数字、下划线组成的连续 token，再加双引号，以 AND 连接：

~~~ts
export function buildFtsQuery(raw: string): string | null {
  const tokens =
    raw
      .match(/[\p{L}\p{N}_]+/gu)
      ?.map((t) => t.trim())
      .filter(Boolean) ?? [];
  if (tokens.length === 0) {
    return null;
  }
  const quoted = tokens.map((t) => `"${t.replaceAll('"', "")}"`);
  return quoted.join(" AND ");
}
~~~

据此可以手工转换：

| 输入 | 基础 FTS 表达式 |
| --- | --- |
| SessionManager | `"SessionManager"` |
| TypeScript tests | `"TypeScript" AND "tests"` |
| agent:main:WeChat:direct:101 | `"agent" AND "main" AND "WeChat" AND "direct" AND "101"` |

冒号没有被当作原样整体匹配的一部分。这个处理还使用户输入的 FTS 运算符、标点等不会直接原样拼进 MATCH 语法；真正执行时 query 值通过 SQL 参数绑定。

默认组合要求全部 token 匹配，较长的口语问题可能因此无结果。FTS-only 模式会在整体查询无结果后提取关键词重试，见第 11.8 节。

### 11.5 中文查询与 trigram

上述正则把连续中文提取为一个 token，默认 unicode61 按字符类别处理文本边界。两者都没有引入中文词典分词，因此“可维护性”能否命中“代码可维护性”，取决于所选 tokenizer 的具体规则。

trigram 对文本建立三字符片段索引，有利于连续文本的子串匹配。不过不足三个字符的部分 CJK 查询不能只靠 trigram MATCH。

`planKeywordSearch` 在 trigram 模式下，将符合 CJK 检测且少于三个 Unicode 字符的 token 放入 substringTerms，其余放入 matchTerms。于是：

- 查询“测试”可以形成 `text LIKE '%测试%'` 条件。
- 查询“TypeScript 测试”可以同时使用 MATCH 与 LIKE，两组条件通过 AND 组合。
- LIKE 参数中的 `%`、`_`、反斜杠会被转义，避免改变预期的子串含义。

查询仅含短 CJK 子串、没有 MATCH 部分时，代码将 rank 表达式设为 0，并直接赋予 textScore = 1。这个 LIKE 分支采用固定评分。

### 11.6 BM25 分数转换

`searchKeyword` 从 FTS 表读取候选时计算 `bm25(chunks_fts)`，按 rank 升序排列。BM25 根据词项频率、语料中的区分度和文档长度等因素衡量文本匹配；SQLite 的 rank 方向与后面“分数越大越好”的合并方向不同。

`bm25RankToScore` 统一分数方向：

~~~ts
export function bm25RankToScore(rank: number): number {
  if (!Number.isFinite(rank)) {
    return 1 / (1 + 999);
  }
  if (rank < 0) {
    const relevance = -rank;
    return relevance / (1 + relevance);
  }
  return 1 / (1 + rank);
}
~~~

用 r 表示 rank，可以写为：

$$
\operatorname{textScore}(r)=
\begin{cases}
0.001, & r\text{ 不是有限数}\\
\frac{-r}{1-r}, & r<0\\
\frac{1}{1+r}, & r\geq0
\end{cases}
$$

取 rank = -4、-1 和 2 复算，结果分别为 0.8、0.5 和约 0.3333。负数分支把相关性绝对值映射为正分数：绝对值很小时接近 0，增大时逐渐趋近 1。转换后的 textScore 用于组合检索信号，不具有概率含义。

### 11.7 Hybrid 合并、阈值与 Lexical Fallback

有 Provider 且 FTS/Hybrid 可用时，管理器先取得 keywordResults，再等待 query Embedding 并查询 vectorResults，最后调用 `mergeHybridResults`。这两条检索分支在 search 中依次执行。

合并函数创建 byId Map：向量候选先写入 vectorScore，并把 textScore 设为 0；关键词候选若找到相同 id，就补 textScore，且可使用其非空 snippet；否则新增一个 vectorScore 为 0 的条目。

合并分数的代码为：

~~~ts
    const score = params.vectorWeight * entry.vectorScore + params.textWeight * entry.textScore;
~~~

默认公式为：

$$
S=0.7S_{vector}+0.3S_{text}
$$

某一路缺失时以 0 参与加权，另一条路径仍使用原权重。textScore 来自第 11.6 节的 BM25 转换，vectorScore 来自余弦相似度。

给三个假定候选手算：

| Chunk | 向量分数 | 文本分数 | 计算 | 综合分数 |
| --- | ---: | ---: | --- | ---: |
| A：两路都命中 | 0.80 | 0.60 | 0.7×0.80 + 0.3×0.60 | 0.74 |
| B：仅向量命中 | 0.90 | 0 | 0.7×0.90 | 0.63 |
| C：仅文本命中 | 0 | 1.00 | 0.3×1.00 | 0.30 |

默认 minScore 为 0.35 时，正常严格过滤保留 A、B，C 被排除。source/path/行号随结果保留；合并函数的公共结果不再需要返回内部 Chunk ID。

如果所有合并结果都低于 minScore，但关键词侧确实找到了候选，完全丢弃结果可能会漏掉明确的术语命中。因此管理器在这个特定条件下取：

~~~ts
    const relaxedMinScore = Math.min(minScore, hybrid.textWeight);
~~~

它按 `source:path:startLine:endLine` 找出属于关键词候选的合并结果，再交给 `selectScoredResults`。函数先尝试原门槛，没有严格结果才采用 relaxedMinScore。

在上表中，只要 A 或 B 通过严格门槛，就不会为了补足数量把 C 自动加回来。若本次只有 C，宽松门槛为 min(0.35, 0.3) = 0.3，C 才能被保留。

若 C 的 textScore 只有 0.5，综合分数为 0.15，仍达不到 0.3。数据库虽产生了候选，最终工具结果仍可能因分数门槛而为空。

### 11.8 FTS-only 检索

Provider 为 null 时，search 完全跳过 query Embedding。只要 FTS 被启用且可用，先用完整 query 执行关键词搜索，并启用 boostFallbackRanking。

完整 AND 查询没有结果时，再由 extractKeywords 提取关键词，分别查询并合并；同一 Chunk 多次出现时保留最高分。

这条路径还有词项重合率、文本词项密度、路径相关性和长度相关的排序补分。`scoreFallbackKeywordResult` 的主要计算是：

~~~ts
  const lexicalBoost = uniqueQueryOverlap * 0.45 + density * 0.2 + pathBoost + textLengthBoost;
  return Math.min(1, params.ftsScore + lexicalBoost);
~~~

其中 pathBoost 对 query token 出现在 path 中的情况按项加 0.18，textLengthBoost 上限为 0.18；这些补分作用于已找到的候选。这组补分仅用于 FTS-only 回退排序；默认 Hybrid 使用经过 bm25RankToScore 转换的文本分数。

结果随后应用可选时间衰减、按分数排序，再尝试 minScore。所有结果都未通过时，这条纯文本路径可把门槛放宽到 0，保留已有匹配。FTS 自身不可用、或 Hybrid 配置关闭导致 FTS 未启用而又没有 Provider 时，则没有这条文本搜索能力可用。

### 11.9 可选排序：Temporal Decay 与 MMR

默认 Hybrid 开启，但 MMR 与 Temporal Decay 都关闭。

Temporal Decay 开启后，先按年龄调整综合分数：

$$
S_{decayed}=S\cdot e^{-\ln(2)\cdot age/halfLifeDays}
$$

halfLifeDays 默认为 30。`memory/YYYY-MM-DD.md` 可以从文件名取日期；MEMORY.md、memory.md 和 memory/ 下的非标准日期主题文件可作为 evergreen 内容不衰减；其他符合条件来源可回退文件 mtime。该调整仅在启用 Temporal Decay 时生效。

MMR 用于降低相邻重叠 Chunk 或重复内容占满结果的情况。它先把相关性分数归一化，再按以下目标迭代选取：

$$
MMR(c)=\lambda\cdot relevance(c)
 -(1-\lambda)\cdot\max_{s\in selected}similarity(c,s)
$$

候选间相似度使用 snippet 词集合的 Jaccard 相似度。默认 lambda 为 0.7，仍需显式启用才能生效。

合并函数中的顺序是加权、可选时间衰减、降序排序、可选 MMR。管理器随后筛选并取 maxResults。工具层把 Memory 与可选 Wiki 结果汇总时还会按 score 排序，因此 MMR 对入选候选集合的影响应与最终 JSON 的展示顺序分开看待。

### 11.10 检索结果与 Agent Loop 的交接

默认 Builtin 的调用关系可以缩写为：

~~~text
Pi 执行 memory_search.execute
  → getMemoryManagerContext
    → getMemorySearchManager
      → MemoryIndexManager.get
  → await manager.search(query, options)
    → 空索引时 await sync；已有索引可后台刷新
    → searchKeyword
    → embedQueryWithTimeout → searchVector
    → mergeHybridResults → 分数门槛与结果上限
  → 引用装饰、corpus 标记与工具结果包装
  → Pi toolResult 消息
  → 同一 Agent Loop 的后续模型请求
~~~

Provider 为 null 时，执行第 11.8 节的 FTS-only 分支。FTS 不可用但 Provider 可用时，执行 vector-only，并按向量分数过滤。query Embedding 报错可传播到工具层；被捕获的单路查询错误则可能使该路候选为空。查询成功但没有匹配时，返回空结果集。

默认 citations 为 auto，普通 direct Session 可附带 `path#L...` 引用；group/channel 的自动引用策略不同。这项判断控制引用展示，并没有为数据库内容建立用户级访问控制。

工具等待 manager.search 及结果包装完成。返回 JSON 前，queueShortTermRecallTracking 已安排回忆信号记录，但内部记录操作没有被 await；search 启动的后台同步也可继续运行。Pi 收到本次结果后，模型再决定调用 memory_get 或直接回答。

## 12. 跨 Session 的记忆恢复

### 12.1 写入、索引与查询时序

第 6.3 节的偏好文件位于 main 的独立 Workspace。以下时序假设 Memory Search 已开启、工具策略允许 search/get，且索引同步在新 Session 查询前成功完成；新 Session 通过第 7.5 节的工具调用取得原文。

~~~mermaid
sequenceDiagram
    participant Alice
    participant Old as 旧 Session 的 Agent
    participant File as Memory Markdown
    participant Index as MemoryIndexManager
    participant New as 新 Session 的 Agent
    Alice->>Old: 记住 TypeScript 与测试偏好
    Old->>File: 模型选择并执行文件写入
    File-->>Old: 写入工具成功结果
    Note over File,Index: 文件变化被观察后，异步安排同步
    Index->>File: 扫描、读取变化文件
    File-->>Index: 原文与文件状态
    Index->>Index: 切块、Embedding 或 FTS-only、写索引
    Alice->>New: /new 后询问之前的偏好
    New->>Index: memory_search(query)
    Index-->>New: 片段、分数、路径与行号
    New->>File: memory_get(path, from, lines)
    File-->>New: 精确原文
    New-->>Alice: 根据已取得的记忆回答
~~~

Old→File 的写入和 New→Index 的检索分别由两次模型执行选择；文件变化通过独立的同步任务进入索引。`/new` 切换 Session，已有 Workspace 记忆文件和 Memory 索引继续保留。

### 12.2 新 Session 的事实来源

新 Session 获取事实的来源可能是：

1. 事实保存在 MEMORY.md，且本次 Bootstrap 条件允许注入。
2. 事实位于近期 Daily Memory，裸 reset 启动前缀选中并加载该段。
3. 模型依据 Memory Recall 指导执行 memory_search，再按需要 memory_get。

已有明确路径时，模型也可用普通 read 或 memory_get 直接读取。System Prompt、启动输入和工具结果分别记录事实进入本轮上下文的具体位置。

偏好若只保存在旧 Session 中，默认 Memory 语料不包含这段历史。新 Session 要使用它，需要启用 Session Memory 索引、由 session-memory Hook 保存相应记录，或明确恢复旧历史。

### 12.3 持久化与检索问题定位

| 观察到的现象 | 优先检查的层次 |
| --- | --- |
| Agent 说记住了，新 Session 却找不到 | 是否有成功文件写入、目标是否属于当前 Agent 的语料 |
| memory_get 能读到，search 暂时搜不到 | 索引同步、dirty 状态、Embedding/FTS 错误与查询门槛 |
| 搜到了相似内容，却漏掉精确术语 | FTS tokenizer、AND 查询构造、model/source 过滤 |
| 搜到很多重复段落 | Chunk overlap、原文重复、MMR 是否启用 |
| /new 后规范还是旧的 | 是否经过快照清理、实际 Workspace 与 Session Key 是否符合预期 |
| Bob 的 Session 能看到 Alice 的资料 | 是否共用同一 Agent Workspace/索引，是否配置共享语料与访问策略 |

这些问题分别落在存储、同步、搜索和上下文入口。先找到数据在哪一层发生变化，才能解释某次回答为什么有或没有使用以前的事实。

## 13. Memory Flush 与 Compaction

### 13.1 持久记忆与会话压缩

Alice 连续讨论了很多轮 TypeScript 项目，已经确定“采用 pnpm”“修改前先检查测试”“模块边界按业务划分”等决策。上下文接近预算时，运行层需要减少下一次请求的历史长度；同时，其中一些事实还值得在未来新的 Session 中使用。

Pi Compaction 把当前 Session 的较早内容压缩为摘要，并保留需要继续推理的历史部分。Memory Flush 则额外安排一次模型执行，让模型选择值得持久化的内容并写入 Workspace 记忆文件。

| 机制 | 输入重点 | 主要产物 | 谁在之后读取 |
| --- | --- | --- | --- |
| Memory Flush | 当前会话中值得跨 Session 保留的事实 | 当日 Memory Markdown 的新增内容 | 新 Session 的启动加载、文件读取或索引检索 |
| Pi Compaction | 当前 Session 超长历史、需要保留的上下文 | JSONL 中的 compaction 条目及后续消息上下文 | 该 Session 的 SessionManager / AgentSession |

这两个操作可以都调用模型，但拥有不同的目标、Prompt 和持久化位置。Flush 也允许模型判断没有新内容需要保存，返回静默结果。

memory-core 提供的 Flush Plan 包含触发预算、提示文本和目标路径。回复层读取这份计划，检查当前 Session 的用量与执行条件，再决定是否安排额外运行。

### 13.2 token 阈值与输入估算

`shouldRunMemoryFlush` 经 `resolveMemoryFlushGateState` 取得有效 token 数与阈值。主要公式为：

$$
T=\max(0,\ contextWindow-reserveTokensFloor-softThresholdTokens)
$$

只有存在 SessionEntry、取得正的有效 token 数且阈值有效时，才继续比较。达到阈值，并且当前 compaction 周期尚未 Flush，才返回 true。

假设有效 contextWindow 为 200,000，reserve 为 20,000，softThreshold 为 4,000，则 T 为 176,000。运行时的有效窗口由配置与模型解析结果确定。

运行层估算即将提交的请求用量，将上一轮输入、输出与当前新增输入合并计算。`resolveEffectivePromptTokens` 的连续片段为：

~~~ts
  const base = Math.max(0, basePromptTokens ?? 0);
  const output = Math.max(0, lastOutputTokens ?? 0);
  const estimate = Math.max(0, promptTokenEstimate ?? 0);
  // Flush gating projects the next input context by adding the previous
  // completion and the current user prompt estimate.
  return base + output + estimate;
~~~

若上一轮 prompt 为 170,000、上一轮 output 为 5,000、当前输入估计为 2,000，投影得到 177,000，超过上述阈值。

totalTokensFresh 用于判断持久化数值是否新鲜。数值过时或未知时，运行层可从 Transcript 的 usage 获取最近可靠数据；接近阈值时还会读取上一轮输出，避免漏掉这部分增长。当前 prompt 的 token 数通过消息估算函数计算。

### 13.3 执行门槛与周期去重

`runMemoryFlushIfNeeded` 先判断执行环境是否允许尝试：普通宿主环境可继续；Sandbox 环境要求 workspaceAccess 为 rw；Heartbeat 和 CLI Provider 路径跳过。

另有 Transcript 文件大小触发：满足可尝试条件时读取文件字节数，达到 Plan 的 forceFlushTranscriptBytes 可以要求 Flush。它用于捕捉文件已经很大、仅依赖 token 状态可能不及时的情况。文件大小按字节计量，与模型输入的 token 估算分别参与判断。

防重复依赖 SessionEntry 的计数：

~~~ts
  const compactionCount = entry.compactionCount ?? 0;
  const lastFlushAt = entry.memoryFlushCompactionCount;
  return typeof lastFlushAt === "number" && lastFlushAt === compactionCount;
~~~

`hasAlreadyFlushedForCurrentCompaction` 对 token 触发和文件大小触发都有效。当前 compactionCount 为 3，memoryFlushCompactionCount 也为 3，表示本周期已经记录过 Flush，后续几轮即使仍靠近门槛，也会由周期检查跳过重复执行。

触发 Flush 后，实际写入仍取决于工具权限、模型对持久事实的选择和文件操作结果。工具策略可能移除 read/write，模型也可判断无需新增记录。

### 13.4 Flush Plan 与写入目标

memory-core 在 Memory Capability 中注册 `flushPlanResolver: buildMemoryFlushPlan`。回复运行层通过宿主 `resolveMemoryFlushPlan({ cfg })` 取得 Plan；未注册相应能力或显式禁用时，可能没有可执行 Plan。

`buildMemoryFlushPlan` 读取 `agents.defaults.compaction.memoryFlush`。默认行为如下：

| 项目 | 默认值或规则 |
| --- | --- |
| memoryFlush.enabled | 未设为 false 时启用 Plan |
| memoryFlush.softThresholdTokens | 4,000 |
| memoryFlush.forceFlushTranscriptBytes | 2 MiB，即 2×1024×1024 字节 |
| compaction.reserveTokensFloor | 20,000，位于 compaction 下而非 memoryFlush 内 |
| prompt / systemPrompt | 使用默认文本，可配置覆盖，但仍补齐必要安全提示 |
| relativePath | 按本次执行日期生成 memory/YYYY-MM-DD.md |

Plan 的返回结构为：

~~~ts
  return {
    softThresholdTokens,
    forceFlushTranscriptBytes,
    reserveTokensFloor,
    prompt: appendCurrentTimeLine(promptBase.replaceAll("YYYY-MM-DD", dateStamp), timeLine),
    systemPrompt: systemPrompt.replaceAll("YYYY-MM-DD", dateStamp),
    relativePath,
  };
~~~

Plan 将触发参数、模型提示和写入目标交给回复运行层；额外的模型执行由运行层在门槛检查通过后启动。

默认提示要求：

- 只把持久事实写入 `memory/YYYY-MM-DD.md`，必要时创建 memory/。
- 文件已存在时追加，不覆盖已有条目。
- 不创建带小时分钟的日期变体文件。
- Flush 期间将 MEMORY.md、DREAMS.md、SOUL.md、TOOLS.md、AGENTS.md 等参考文件当作只读。
- 无需保存时使用 `NO_REPLY`。

日期由 `resolveCronStyleNow` 得到的用户时区和运行时间确定。Plan 在真正执行前用当前 nowMs 再构造一次，避免预先检查与实际执行跨日时继续写到旧日期。

例如执行时本地日期为 2026-10-08，则 relativePath 为 `memory/2026-10-08.md`。默认文本中的 YYYY-MM-DD 也替换为同一个日期，prompt 还追加当前时间信息。自定义 prompt/systemPrompt 也会补齐目标、只读与追加提示。

选择 Daily Memory 使这次整理有明确的追加位置，避免在长会话临近压缩时重写一个已经积累很多稳定事实的 MEMORY.md。之后若需要把当日记录提升为更稳定的长期条目，可以另行维护或使用启用后的 Dreaming 流程。

### 13.5 额外 Agent 执行

回复层生成新的 flushRunId，把阶段设为 memory_flushing，并经 `runWithModelFallback` 等待一次 `runEmbeddedPiAgent`。关键连续参数为：

~~~ts
          sandboxSessionKey: params.runtimePolicySessionKey,
          allowGatewaySubagentBinding: true,
          silentExpected: true,
          trigger: "memory",
          memoryFlushWritePath,
          prompt: activeMemoryFlushPlan.prompt,
          extraSystemPrompt: flushSystemPrompt,
~~~

执行沿用当前会话相关参数，使模型能够访问待整理的历史；本轮输入替换为 Flush Prompt，并附加对应的 system prompt。

模型可先 read 当日文件，再调用 write 追加新事实，也可返回 NO_REPLY。写入包装器成功返回的 details 包含目标 path 和 `appendOnly: true`，可据此核对本次工具写入。

`silentExpected: true` 表达这轮通常无对外回复，外层函数也不会把 Flush 的普通 payload 当作 Alice 的最终聊天回复直接返回。真正回答用户的运行还在后面。

### 13.6 工具允许名单与追加写入

约束同时存在于 Prompt 和工具层。

`createOpenClawCodingTools` 识别 `trigger === "memory"`，要求存在 memoryFlushWritePath；否则直接报错。它为这种运行强制采用 Workspace 文件范围，并把工具集合收缩到 read、write。普通 exec、edit、apply_patch 和 Memory 搜索等不会通过这份 Flush 专用允许名单。

遇到 write 时，它包装成 `wrapToolMemoryFlushAppendOnlyWrite`。关键逻辑为：

~~~ts
      const resolvedPath = resolveToolPathAgainstWorkspaceRoot({
        filePath,
        root: options.root,
        containerWorkdir: options.containerWorkdir,
      });
      if (resolvedPath !== allowedAbsolutePath) {
        throw new Error(
          `Memory flush writes are restricted to ${options.relativePath}; use that path only.`,
        );
      }
~~~

检查通过后，包装器调用 `appendMemoryFlushContent` 追加内容。宿主文件路径进一步调用：

~~~ts
    await appendFileWithinRoot({
      rootDir: params.root,
      relativePath: params.relativePath,
      data: params.content,
      mkdir: true,
      prependNewlineIfNeeded: true,
    });
~~~

`appendFileWithinRoot` 以不截断已有文件、追加写的方式安全打开目标；必要时创建目录，并在旧文本末尾与新文本开头都没有换行时补一个分隔换行。Sandbox 分支经文件桥读取旧文本并写入“旧内容 + 分隔符 + 新内容”，保持原有内容的追加语义。

写入权限由包装器实际执行：若 write.path 为 MEMORY.md，会因与允许路径不符而失败。后续工具策略还可进一步收窄权限。

### 13.7 完成状态与失败处理

外层 await 等待 Flush 的模型运行和其中被执行的工具过程。成功返回后，函数可以写入 `memoryFlushAt` 与 `memoryFlushCompactionCount`。

这两个字段记录 Flush 运行状态。模型返回 NO_REPLY 时也可以完成运行，因此当日文件是否新增内容，要结合写入工具结果与文件变化判断。

Flush 本身也可能发生 Compaction。运行层监听 stream 为 compaction、phase 为 end 的事件；如果观察到压缩完成，会增加 compactionCount，处理可能变化的 Session ID/File，并刷新后续队列使用的实例信息。Flush 计数再按更新后的周期记录。

执行抛错时，`runMemoryFlushIfNeeded` 捕获并记录失败，随后返回当前 Session 状态，外层继续处理用户任务；元数据记录失败也由独立的错误分支处理。

文件 Watcher 按第 10 节的同步机制处理新增内容。Flush 返回时，向量与 FTS 索引更新仍可能在后台运行。

### 13.8 Memory Flush 与 Compaction 的执行顺序

回复运行层的实际顺序是：

~~~text
await runPreflightCompactionIfNeeded(...)
await runMemoryFlushIfNeeded(...)
继续正常用户回复运行
~~~

preflight 用来处理持久化用量过时或缺失等情况下，按 Transcript 估计出的当前输入已经太大的问题。它满足自己的条件时，先调用 `compactEmbeddedPiSession`，随后更新 compactionCount，并添加压缩后刷新上下文的提示。

这意味着，某些运行在进入 Flush 检查前就已经完成一次 preflight compaction。已有新鲜用量的通常路径可以跳过 preflight，再提前触发 Flush，为后续可能的自动压缩保留持久事实。

同时，Flush 额外执行本身也进入 Pi，因而可能遇到自动压缩；普通用户执行还可能在之后压缩；用户显式 `/compact` 则有自己的压缩入口，并没有统一调用这个回复层 Flush 函数。

OpenClaw 的回复层据此为长会话增加了持久化机会：先执行必要的 preflight，再判断 Flush，随后处理正常用户任务。各处 Compaction 仍按对应入口的条件执行。

### 13.9 长对话中的执行时序

以下时序汇总长会话中的调用关系。opt 标记条件分支，文件与索引之间的 Note 标记异步观察关系。

~~~mermaid
sequenceDiagram
    participant Alice
    participant Reply as OpenClaw 回复层
    participant Pi as Pi 运行与 Compaction
    participant File as Daily Memory
    participant Index as Memory 索引
    Alice->>Reply: 继续讨论项目决策
    opt 用量过时且 Transcript 估算需要预先压缩
        Reply->>Pi: await preflight compaction
        Pi-->>Reply: 结果、摘要与更新后的会话状态
    end
    Reply->>Reply: 构造 Plan，检查预算、大小与周期计数
    opt 满足 Flush 条件
        Reply->>Pi: await 额外 memory 运行
        Note over Pi: 此次运行也可能触发 Compaction
        opt 模型选择保存新事实
            Pi->>File: 通过受限 write 追加当天事实
            File-->>Pi: 追加工具结果
        end
        Pi-->>Reply: Flush 运行结束或失败
        Reply->>Reply: 成功返回后尝试记录 Flush 元数据
    end
    Note over File,Index: 文件变化可异步触发索引同步；回复层不在此等待完成
    Reply->>Pi: 继续正常用户任务
    opt 后续执行达到压缩条件
        Pi->>Pi: 生成摘要并恢复精简上下文
    end
    Pi-->>Reply: 返回任务执行结果
    Reply-->>Alice: 发送本轮回复
    Alice->>Reply: /new，随后询问过去决策
    Reply->>Pi: 新 Session 与符合条件的启动上下文
    Pi->>Index: 若模型选择，调用 memory_search
    Index-->>Pi: 已索引事实的候选片段
    Pi->>File: 按需 memory_get
    File-->>Pi: 当前原文
    Pi-->>Reply: 根据取得的事实形成回答
    Reply-->>Alice: 发送回答
~~~

模型判断有内容需要保存时，Flush 才执行 Pi→File 的写入。运行是否发生压缩，由该次执行的预算、Pi 设置和 Context Engine 路径决定。

若索引尚未更新，新 Session 的 memory_get 或符合条件的近期启动注入仍可直接读取 Markdown；memory_search 则可能暂时返回旧索引中的内容。

### 13.10 压缩后的持久化产物

| 产物 | 长对话之后可能发生什么 | /new 之后的意义 |
| --- | --- | --- |
| 旧 Session JSONL | 保留消息与 compaction 等条目 | 仍在磁盘，但新 Session 不默认恢复全部旧消息 |
| Compaction Summary | 记录摘要及保留历史的边界 | 默认服务于原 Session 的上下文恢复 |
| MEMORY.md | 普通维护或启用的提升流程可更新；本次 Flush 视为只读 | 合适上下文中提供稳定事实 |
| Daily Memory | Flush 可以追加具体决策与偏好 | 新 Session 可启动加载、精确读取或检索 |
| SQLite Memory Index | 在同步完成后反映可索引原文 | 帮新问题找到相关 Chunk，仍需模型实际使用结果 |

Pi 的 `AgentSession.compact` 在成功生成摘要后通过 SessionManager 的 appendCompaction 保存条目，并重建当前消息上下文；Memory Flush 的 write 路径则落在 Workspace Markdown。两份数据分别由会话恢复机制和文件/检索机制使用。

## 14. 可选 Backend 与记忆维护能力

### 14.1 QMD Backend

第 8—11 节的 Builtin Backend 由 MemoryIndexManager 管理 SQLite、Embedding、FTS 与 Hybrid 排序。

配置 `memory.backend: "qmd"` 后，`getMemorySearchManager` 尝试创建 `QmdMemoryManager`。它需要可用的 QMD 命令或相应调用环境，使用 QMD collections、索引更新与查询接口。OpenClaw 通过这一接口调用外部检索组件。

QMD 具有自己的 search/vsearch/query 模式、集合配置、更新周期和范围策略；默认 QMD searchMode 是 search。查询与排序由 QMD 路径负责，上文的 Builtin Hybrid 公式适用于内置管理器。命令不可用、初始化失败或包装器处理的运行失败可触发 Builtin fallback，具体结果需看实际返回的 backend/fallback。

### 14.2 Honcho 插件与服务

仓库提供 Honcho 的接入文档，入口指向外部包 `@honcho-ai/openclaw-honcho`。它连接独立的 Honcho 服务，可使用托管服务或自行部署的服务端，以会话与用户建模方式提供跨 Session 记忆。

Honcho 的插件实现位于外部包，本地仓库提供接入文档。逐轮保存、用户建模、检索算法及与本地 Markdown 的组合方式，需要依据实际安装的插件版本确认。连接该服务还需安装插件并配置服务地址与认证。

### 14.3 Memory Wiki 补充语料

`memory-wiki` 提供独立的插件入口。它注册自己的 wiki_status、wiki_lint、wiki_apply、wiki_search、wiki_get 等工具，同时注册 Memory Prompt Supplement 与 Memory Corpus Supplement。

后者正是第 7 节 corpus 参数的接入点：普通 memory_search 默认查询 Memory；指定 `corpus: "wiki"` 时查询已注册 Wiki 补充语料；指定 all 则合并两类结果。memory_get 也能转交 Wiki supplement 获取相应内容。

Wiki 侧组织编译后的知识页面与可维护资料，通过补充语料接口参与检索。它与默认 Memory 文件索引各自维护查询实现；使用 Wiki 语料需启用插件并完成语料注册。

### 14.4 Dreaming、DREAMS.md 与稳定事实提升

memory-core 注册了 Dreaming 相关能力，但 `DEFAULT_MEMORY_DREAMING_ENABLED` 为 false。配置来自当前 Dreaming 插件的 pluginConfig.dreaming；默认 memory-core 场景对应 `plugins.entries["memory-core"].config.dreaming`。

启用后，代码协调受管理的 Cron 作业，并在对应 Heartbeat 触发中处理 Dreaming 事件。`before_agent_reply` 同时检查 heartbeat trigger、待处理的受管理事件和指定事件文本，条件匹配后才进入相应处理。

相关实现可以选取回忆信号、近期记录与其他证据，去重、整理、筛选需要提升的事实。`applyShortTermPromotions` 针对 MEMORY.md 处理符合阈值且尚未提升的候选；还存在分阶段整理、报告与 Dream Narrative 生成路径。具体输出取决于启用的阶段与 storage 配置。

DREAMS.md 是可选叙事与维护产物之一，相关函数负责读取、保留内容与追加叙事条目。它属于 Builtin memory_get 的允许读取范围，普通 Bootstrap 固定列表与默认索引扫描列表则均不包含它，具体范围见第 8.3 节。

Memory Flush 把值得保留的事实追加到 Daily Memory，Dreaming 在启用后持续整理并提升稳定事实，Memory Wiki 组织独立知识页面。QMD 和 Honcho 则分别引入外部检索组件与记忆服务，其配置和数据流由对应接入路径管理。

## 15. 状态与持久化结果核对

一次记忆操作可以从以下状态判断其完成位置：

| 需要确认的状态 | 可观察的具体证据 |
| --- | --- |
| 已经知道当前输入 | 事实出现在本轮 messages 中 |
| 已经持久化 | 目标 Markdown 中确实存在内容，且有成功写入结果 |
| 已能被检索 | 当前 Agent 的同步完成，索引中存在相关 Chunk |
| 本轮已经取得事实 | System Prompt、启动前缀或工具结果中包含相关内容 |
| 正在使用正确作用域 | Workspace、agentId、extraPaths、Backend 与工具策略符合当前用户范围 |
| 压缩后仍可继续原任务 | 当前 Session 的摘要与保留历史能重建必要上下文 |
