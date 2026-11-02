---
title: "13 · AgentSession 运行准备"
description: "openclaw · 会话执行与协作 · 课程讲义"
project: "openclaw"
sourcePath: "OpenClaw/OpenClaw-Course/13_AgentSession运行准备完整讲义.md"
originalUrl: "/originals/openclaw/chapter-13.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 13 Agent Session 运行准备：先看例子，再看定义与加载

本讲以本地 `pi-master` 为准，用“午饭助手”贯穿各节。每节先看文件或使用例子，再看源码中的关键定义，最后说明大致加载过程。实现只保留与当前问题相关的片段，完整分支通过源码链接查看。

第 09 讲解释了 SessionManager 怎样保存与恢复历史；第 10、11 讲分别解释项目资源与长期记忆怎样进入上下文。现在回到 Pi SDK，本讲把模型、认证、资源、工具和当前分支的历史消息装配成可用的 AgentSession；下一讲再从 `session.prompt()` 进入内部 `Agent.prompt()`，跟踪一次输入怎样执行。OpenClaw 的长期记忆由宿主接入，创建 Pi 的 AgentSession 本身不会自动获得 memory-core。

## 第一部分：先看准备什么

### 1. 一个任务需要哪些准备

**例子：** 用户说：“帮我选一份不辣的午饭，预算 20 元。先给方案，不要下单。”

在查询菜单以前，程序要先知道项目在哪里、用哪个模型、有哪些规则和工具、是否需要恢复旧记录。

```text
cwd、agentDir
    ├→ SettingsManager：工作设置
    ├→ AuthStorage → ModelRegistry：认证与模型目录
    ├→ SessionManager：历史记录与当前分支
    └→ DefaultResourceLoader：项目资料、Skill、模板、扩展
                         ↓
          选择模型与 thinking level，恢复消息
                         ↓
                       Agent
                         ↓
                    AgentSession
                         ├→ ExtensionRunner、事件订阅
                         └→ 工具注册表、活跃工具、系统提示词
                         ↓
                    宿主绑定与启动
                         ↓
               session.prompt → agent.prompt
```

这张图是依赖关系图。真实工厂中的创建顺序还要对照第 5.1 节。

### 2. 每个对象在午饭任务中是什么

**例子：** “预算 20 元”是用户任务；“默认模型、重试次数”是运行设置；“先查库存”是项目规则，三者进入程序的位置不同。

| 对象 | 代码中的职责 | 午饭例子 |
|---|---|---|
| 宿主 | 提供入口、界面和会话动作 | CLI、网页或 OpenClaw |
| `SettingsManager` | 读取、合并和提供运行设置 | 默认模型、thinking level、压缩与重试参数 |
| `AuthStorage` | 保存凭据来源，按需解析认证 | 调用模型使用的 key 或 OAuth |
| `ModelRegistry` | 管理模型描述与请求配置 | 模型 ID、协议、地址、上下文窗口 |
| `SessionManager` | 管理历史 Entry、分支和 JSONL | 恢复昨天讨论到的位置 |
| `ResourceLoader` | 加载规则、Skill、模板、扩展等 | 选餐方法、项目要求、午饭模板 |
| `Agent` | 保存运行状态，执行模型与工具循环 | 查询菜单、查询库存、继续回答 |
| `AgentSession` | 连接 Agent、历史和运行依赖 | 处理输入、保存消息、协调扩展 |
| `ExtensionRunner` | 调度扩展处理函数并绑定动作 | 启动回调、输入与工具处理 |

模型配置、认证资料、工具定义、历史消息和系统提示词分别准备，随后再装配到一起。

### 3. 准备完成时应当得到什么

**例子：** 今天新建午饭会话，还没有查询过菜单。

| 准备项 | 本例得到的内容 |
|---|---|
| 工作目录 | 午饭项目的绝对路径 |
| 设置 | 从用户级与项目级配置合并出的有效设置 |
| 模型与认证 | 选中的模型对象，以及请求时取得认证的入口 |
| 历史 | 新会话的聊天消息为 `[]`，但可以已有初始设置 Entry |
| 项目资料 | “先核对价格与库存，未经授权不下单” |
| 工具 | `read`、`list_meals`、`get_stock` 的可执行定义 |
| 系统提示词 | 午饭角色、项目资料和相关资源说明 |
| 内部关系 | 事件订阅、扩展运行环境、宿主绑定 |

此时只是具备查询能力，还没有今天的菜单和库存结果。打开旧会话时，历史项换成当前分支重建出的消息；加载旧查询结果不会自动重新查询库存。

### 4. 哪些准备一次，哪些每次输入都做

**例子：** 用户先问“20 元以内”，再补一句“预算改成 30 元”。第二句话通常不需要重新创建全部对象。

| 时机 | 主要工作 |
|---|---|
| 初始化服务或刷新 | 设置、认证来源、模型目录、资源 |
| 创建或替换会话 | SessionManager、Agent、AgentSession、工具和提示词 |
| 每次普通输入 | 处理命令与模板、检查状态、构造新消息 |

OpenClaw 还会在外层确定目标 Agent、Session Key 和 Workspace 等。本讲集中看 Pi 的装配，可对照 OpenClaw 的 [attempt.ts](/source/?file=4c2d09aeeb74b60140.ts)。

## 第二部分：例子、定义与加载

### 5. 基础依赖：目录、设置、认证、模型与历史

**例子：** 在午饭项目启动，读取用户配置，并选择新建会话或恢复昨天的记录。下面各小节分别看这些输入如何变成对象。

#### 5.1 cwd、agentDir 与工厂入口

**例子：** 本讲统一使用以下教学目录。Windows 上可用 `resolve("lunch")` 等得到本机路径。

```text
/course/lunch/                         ← cwd
├── AGENTS.md
└── .pi/
    ├── settings.json
    ├── SYSTEM.md
    ├── APPEND_SYSTEM.md
    ├── skills/choose-lunch/SKILL.md
    ├── prompts/lunch.md
    ├── extensions/lunch-rules.ts
    └── themes/lunch-dark.json

/course/pi-agent/                      ← agentDir
├── settings.json
├── auth.json
├── models.json
└── sessions/lunch-demo.jsonl           ← 示例显式指定的历史文件
```

**代码中的定义。** [CreateAgentSessionOptions](/source/?file=07502145bf1ffa712b.ts#L33) 允许宿主传目录，也允许直接传入已有依赖：

```ts
// 接口节选，省略模型、工具等其他选项。
export interface CreateAgentSessionOptions {
  cwd?: string;
  agentDir?: string;
  authStorage?: AuthStorage;
  modelRegistry?: ModelRegistry;
  sessionManager?: SessionManager;
  settingsManager?: SettingsManager;
  resourceLoader?: ResourceLoader;
}
```

**大致怎样加载。** [createAgentSession()](/source/?file=07502145bf1ffa712b.ts#L176) 先补齐目录和缺少的对象：

```ts
// 源码节选。
const cwd = options.cwd ?? options.sessionManager?.getCwd() ?? process.cwd();
const agentDir = options.agentDir ?? getDefaultAgentDir();
```

后续顺序是 AuthStorage → ModelRegistry → SettingsManager → SessionManager → 默认 ResourceLoader。每个依赖都优先复用宿主传入的实例；`??` 右边的创建表达式只在没有传入对象时执行。

`cwd` 决定项目资源位置，`agentDir` 决定用户级设置、认证和模型文件位置。默认 `agentDir` 由 [getAgentDir()](/source/?file=f56342646902820db9.ts#L209) 决定，通常为 `~/.pi/agent`，也支持环境配置。

#### 5.2 SettingsManager：两层设置怎样定义和合并

**文件例子。** 用户级 `/course/pi-agent/settings.json`：

```json
{
  "defaultProvider": "lunch-lab",
  "defaultModel": "lunch-demo",
  "defaultThinkingLevel": "medium",
  "compaction": { "enabled": true, "reserveTokens": 16384, "keepRecentTokens": 20000 },
  "retry": { "maxRetries": 3 }
}
```

项目级 `/course/lunch/.pi/settings.json`：

```json
{
  "defaultThinkingLevel": "high",
  "compaction": { "keepRecentTokens": 12000 },
  "retry": { "maxRetries": 1 }
}
```

合并后，本例 thinking level 为 `high`，压缩保留量为 `12000`，而全局的 `enabled` 与 `reserveTokens` 仍然保留。

读取例子：

```ts
const settingsManager = SettingsManager.create(cwd, agentDir);
settingsManager.getDefaultThinkingLevel(); // high
settingsManager.getCompactionSettings();
// { enabled: true, reserveTokens: 16384, keepRecentTokens: 12000 }
settingsManager.getRetrySettings();
// { enabled: true, maxRetries: 1, baseDelayMs: 2000, maxDelayMs: 60000 }
```

**代码中的定义。** [Settings](/source/?file=a7b1c7acc6cf6a0b83.ts#L68) 描述字段，[SettingsManager](/source/?file=a7b1c7acc6cf6a0b83.ts#L240) 保存两层原始设置及有效设置：

```ts
// Settings 的部分字段。
defaultProvider?: string;
defaultModel?: string;
defaultThinkingLevel?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
compaction?: CompactionSettings;
retry?: RetrySettings;

// SettingsManager 的核心字段。
private storage: SettingsStorage;
private globalSettings: Settings;
private projectSettings: Settings;
private settings: Settings;
```

存储后端用 scope 区分两个文件：

```ts
export type SettingsScope = "global" | "project";

export interface SettingsStorage {
  withLock(scope: SettingsScope, fn: (current: string | undefined) => string | undefined): void;
}
```

**大致怎样加载。** [create() / fromStorage()](/source/?file=a7b1c7acc6cf6a0b83.ts#L274) 的过程是：

```text
SettingsManager.create(cwd, agentDir)
→ FileSettingsStorage 确定两个文件路径
→ 分别读取 global、project
→ JSON.parse，再迁移旧字段
→ 保存两层原始设置
→ deepMergeSettings(global, project) 得到有效设置
```

合并函数对顶层字段逐项处理；两边都是非数组对象时，合并这一层子字段；数组直接由项目值替换。它没有递归调用自身，不能推断成任意深度递归合并。首次读取失败的作用域贡献 `{}`，错误可以从 `drainErrors()` 取得。

有些默认值由 getter 补齐，而非创建时写满 JSON。这些设置随后分别交给 Agent 的队列与请求配置、AgentSession 的压缩和重试等逻辑。读取设置本身不会执行点餐或压缩。

#### 5.3 AuthStorage：凭据对象与实际认证值

**文件例子。** `/course/pi-agent/auth.json`：

```json
{
  "lunch-lab": { "type": "api_key", "key": "demo-key-from-auth-file" }
}
```

上面是教学字符串。也可以给当前进程临时覆盖：

```ts
const authStorage = AuthStorage.create(join(agentDir, "auth.json"));
authStorage.setRuntimeApiKey("lunch-lab", "demo-key-runtime");
// 本次取 key 时优先使用运行时值，不写回 auth.json。
```

**代码中的定义。** [auth-storage.ts](/source/?file=5c78ca37f246b4a65d.ts#L23) 按 provider 保存凭据：

```ts
export type ApiKeyCredential = { type: "api_key"; key: string };
export type OAuthCredential = { type: "oauth" } & OAuthCredentials;
export type AuthCredential = ApiKeyCredential | OAuthCredential;
export type AuthStorageData = Record<string, AuthCredential>;

// AuthStorage 中的核心状态。
private data: AuthStorageData = {};
private runtimeOverrides: Map<string, string> = new Map();
```

文件中存的是凭据对象，不是 Model，也不是聊天消息。OAuth 凭据还包含 access、refresh、expires 等字段。

**大致怎样加载。** [create() 与构造函数](/source/?file=5c78ca37f246b4a65d.ts#L205) 创建文件后端，然后调用 `reload()`：

```text
AuthStorage.create(authPath)
→ FileAuthStorageBackend
→ 构造函数调用 reload()
→ 加锁读取 auth.json
→ JSON.parse，保存到 data
```

文件后端首次读取时可能创建目录和内容为 `{}` 的 auth.json。真正请求认证时，[getApiKey()](/source/?file=5c78ca37f246b4a65d.ts#L446) 才按分支取值：运行时覆盖 → 文件凭据 → provider 环境变量 → fallback resolver。有文件凭据但解析或刷新失败时，部分分支会直接返回，不一定继续所有后备来源。

`hasAuth()` 是配置存在性检查，不刷新 OAuth。`getApiKey()` 才可能刷新过期 OAuth。API key 的字符串还能表示环境变量名或 `!` 开头的命令；[resolveConfigValue()](/source/?file=4f8a21838e568dc621.ts#L18) 负责解析。普通字符串没有对应环境变量时，会被当作字面值，因此“配置存在”不等于“远端认证成功”。

#### 5.4 ModelRegistry：模型描述与请求配置

**文件例子。** `/course/pi-agent/models.json`：

```json
{
  "providers": {
    "lunch-lab": {
      "api": "openai-completions",
      "baseUrl": "https://model.example.invalid/v1",
      "apiKey": "demo-key-from-models-file",
      "headers": { "X-App": "lunch-course" },
      "models": [{ "id": "lunch-demo", "reasoning": true }]
    }
  }
}
```

地址和 key 都用于教学。读完以后，可以查到 `lunch-lab/lunch-demo`；缺省字段会补成 `input: ["text"]`、`contextWindow: 128000`、`maxTokens: 16384` 等。它们是配置元数据，不是远端测量结果。

```ts
const modelRegistry = ModelRegistry.create(authStorage, join(agentDir, "models.json"));
const model = modelRegistry.find("lunch-lab", "lunch-demo");
```

**代码中的定义。** [ModelRegistry](/source/?file=0e557b1d53638cfcd2.ts#L303) 主要保存：

```ts
private models: Model<Api>[] = [];
private providerRequestConfigs: Map<string, ProviderRequestConfig> = new Map();
private modelRequestHeaders: Map<string, Record<string, string>> = new Map();
private registeredProviders: Map<string, ProviderConfigInput> = new Map();
private loadError: string | undefined = undefined;
```

其中 `models` 放模型描述；另外两张请求配置表保存 provider 级和模型级的 key、headers 等来源；构造时还保留同一个 AuthStorage 实例。

**大致怎样加载。** [loadModels()](/source/?file=0e557b1d53638cfcd2.ts#L356) 的主线是：

```text
ModelRegistry.create(authStorage, modelsPath)
→ 构造函数调用 loadModels()
→ 读取 models.json，做 JSON 与配置校验
→ 登记 provider 请求配置、解析自定义模型
→ 加载内置模型，应用 provider / 单模型覆盖
→ 按 provider + id 合并，自定义同名模型优先
→ 应用已登录 OAuth provider 的模型调整
→ 保存 models
```

没有自定义文件时仍有内置模型；自定义文件加载出错时记录 `loadError`，保留内置模型。通常这里在本地整理目录，没有逐个请求远端模型。

`find()` 只查目录，`getAvailable()` 只按认证配置过滤。请求时才调用 [getApiKeyAndHeaders()](/source/?file=0e557b1d53638cfcd2.ts#L668)，优先取 AuthStorage 的认证，再考虑 models.json 配置，并解析请求头。因此本例 auth.json 中的 key 会优先于 models.json 中的 key。

#### 5.5 SessionManager：文件怎样变成当前历史

**文件例子。** `/course/pi-agent/sessions/lunch-demo.jsonl` 是每行一个 JSON 对象，没有外层数组：

```jsonl
{"type":"session","version":3,"id":"019a1f00-0000-7000-8000-000000000001","timestamp":"2026-10-26T00:00:00.000Z","cwd":"/course/lunch"}
{"type":"model_change","id":"11111111","parentId":null,"timestamp":"2026-10-26T00:00:00.001Z","provider":"lunch-lab","modelId":"lunch-demo"}
{"type":"thinking_level_change","id":"22222222","parentId":"11111111","timestamp":"2026-10-26T00:00:00.002Z","thinkingLevel":"high"}
{"type":"message","id":"33333333","parentId":"22222222","timestamp":"2026-10-26T00:00:00.003Z","message":{"role":"user","content":[{"type":"text","text":"帮我选一份不辣的午饭，预算 20 元。"}],"timestamp":1792972800003}}
```

这是展示恢复结构的短文件；正常对话保存后还会有助手与工具结果等记录，首次持久化时机见第 09 讲。

**代码中的定义。** [session-manager.ts](/source/?file=043f6d188e65e3207b.ts#L31) 区分 Header 和 Entry：

```ts
// 类型节选。
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

// SessionManager 的部分索引状态。
private fileEntries: FileEntry[] = [];
private byId: Map<string, SessionEntry> = new Map();
private leafId: string | null = null;
```

**大致怎样加载。** [open()](/source/?file=043f6d188e65e3207b.ts#L1325) 先读 Header 确定 cwd，再进入文件加载与索引重建：

```text
open(path)
→ Header 决定 cwd，或采用显式 cwdOverride
→ 构造函数调用 setSessionFile()
→ 读取 Entry、处理版本迁移
→ 重建 byId 等索引，恢复到最后 Entry
→ buildSessionContext() 沿当前路径生成消息、模型与 thinking level
```

对上面的文件，恢复模型为 `lunch-lab/lunch-demo`，thinking 为 `high`，聊天消息只有那一条 user 消息。Header 不属于聊天消息，模型和 thinking Entry 也不会变成普通 user 消息。

`byId` 与 `leafId` 是加载后重建的内存状态，不是文件中单独保存的两个字段。新建则走 `create()`，准备 Header、ID 与空索引；`inMemory()` 也准备历史结构，只是不写 JSONL。

#### 5.6 Lock：为什么读取和写回要放在同一个锁范围里

**例子：** 两个 Pi 进程同时修改 settings.json：A 改默认模型，B 改主题。如果两者都拿旧文件整体覆盖写回，后写入者可能把另一人的更新覆盖掉。另一个常见例子是两个进程同时发现 OAuth 过期，都准备刷新认证。

初始文件内容：

```json
{
  "defaultModel": "old-model",
  "theme": "light"
}
```

A 只把 defaultModel 改成 lunch-demo，B 只把 theme 改成 dark，希望最终两个修改都保留：

```json
{
  "defaultModel": "lunch-demo",
  "theme": "dark"
}
```

下面直接使用本地 Pi Agent 的原始代码。先看 SettingsManager 怎样调用 Lock，再看文件后端如何加锁；最后看 OAuth 刷新这一处异步使用。

**1. 初始化读取设置：在 withLock 回调中取得文件文本。**

原始代码：[settings-manager.ts:309](/source/?file=a7b1c7acc6cf6a0b83.ts#L309)。保留完整方法或类，仅调整外层缩进。

```ts
private static loadFromStorage(storage: SettingsStorage, scope: SettingsScope): Settings {
	let content: string | undefined;
	storage.withLock(scope, (current) => {
		content = current;
		return undefined;
	});

	if (!content) {
		return {};
	}
	const settings = JSON.parse(content);
	return SettingsManager.migrateSettings(settings);
}
```

这里的回调只保存 current，并返回 undefined，因此不要求写回。JSON.parse 和旧字段迁移发生在 withLock 返回之后；锁内完成的是文件读取。创建时的调用主线为 SettingsManager.create() → fromStorage() → tryLoadFromStorage() → loadFromStorage()。

**2. 保存设置：在 withLock 回调中合并本次修改。**

原始代码：[settings-manager.ts:477](/source/?file=a7b1c7acc6cf6a0b83.ts#L477)。保留完整方法或类，仅调整外层缩进。

```ts
private persistScopedSettings(
	scope: SettingsScope,
	snapshotSettings: Settings,
	modifiedFields: Set<keyof Settings>,
	modifiedNestedFields: Map<keyof Settings, Set<string>>,
): void {
	this.storage.withLock(scope, (current) => {
		const currentFileSettings = current
			? SettingsManager.migrateSettings(JSON.parse(current) as Record<string, unknown>)
			: {};
		const mergedSettings: Settings = { ...currentFileSettings };
		for (const field of modifiedFields) {
			const value = snapshotSettings[field];
			if (modifiedNestedFields.has(field) && typeof value === "object" && value !== null) {
				const nestedModified = modifiedNestedFields.get(field)!;
				const baseNested = (currentFileSettings[field] as Record<string, unknown>) ?? {};
				const inMemoryNested = value as Record<string, unknown>;
				const mergedNested = { ...baseNested };
				for (const nestedKey of nestedModified) {
					mergedNested[nestedKey] = inMemoryNested[nestedKey];
				}
				(mergedSettings as Record<string, unknown>)[field] = mergedNested;
			} else {
				(mergedSettings as Record<string, unknown>)[field] = value;
			}
		}

		return JSON.stringify(mergedSettings, null, 2);
	});
}
```

这就是前面“两进程分别修改模型和主题”的源码对应点。current 是后端这次读取的文件文本；代码先解析成 currentFileSettings，再只覆盖 modifiedFields。对子对象，还能按 modifiedNestedFields 合并本次修改的子字段。返回 JSON 字符串表示交给后端写回。

setDefaultModel()、setTheme() 等设置方法标记修改字段，save() 把持久化任务加入 writeQueue，再调用上面的 persistScopedSettings()。同一实例的 writeQueue 负责排队，文件后端的 Lock 负责协调使用同一锁协议的其他进程。

**3. 文件后端：FileSettingsStorage 的完整加锁实现。**

原始代码：[settings-manager.ts:152](/source/?file=a7b1c7acc6cf6a0b83.ts#L152)。保留完整方法或类，仅调整外层缩进。

```ts
export class FileSettingsStorage implements SettingsStorage {
	private globalSettingsPath: string;
	private projectSettingsPath: string;

	// ⭐️ 已讲（12 讲义，第 5.2 节）：确定 agentDir/settings.json 与 cwd/.pi/settings.json 两个存储路径。
	constructor(cwd: string, agentDir: string) {
		this.globalSettingsPath = join(agentDir, "settings.json");
		this.projectSettingsPath = join(cwd, CONFIG_DIR_NAME, "settings.json");
	}

	// ⭐️ 已讲（12 讲义，第 5.6 节）：调用 proper-lockfile，同步重试 ELOCKED 并保留其他错误。
	private acquireLockSyncWithRetry(path: string): () => void {
		const maxAttempts = 10;
		const delayMs = 20;
		let lastError: unknown;

		for (let attempt = 1; attempt <= maxAttempts; attempt++) {
			try {
				return lockfile.lockSync(path, { realpath: false });
			} catch (error) {
				const code =
					typeof error === "object" && error !== null && "code" in error
						? String((error as { code?: unknown }).code)
						: undefined;
				if (code !== "ELOCKED" || attempt === maxAttempts) {
					throw error;
				}
				lastError = error;
				const start = Date.now();
				while (Date.now() - start < delayMs) {
					// Sleep synchronously to avoid changing callers to async.
				}
			}
		}

		throw (lastError as Error) ?? new Error("Failed to acquire settings lock");
	}

	// ⭐️ 已讲（12 讲义，第 5.6 节）：读取当前文本、执行回调、按需写回，并在 finally 中释放锁。
	withLock(scope: SettingsScope, fn: (current: string | undefined) => string | undefined): void {
		const path = scope === "global" ? this.globalSettingsPath : this.projectSettingsPath;
		const dir = dirname(path);

		let release: (() => void) | undefined;
		try {
			// Only create directory and lock if file exists or we need to write
			const fileExists = existsSync(path);
			if (fileExists) {
				release = this.acquireLockSyncWithRetry(path);
			}
			const current = fileExists ? readFileSync(path, "utf-8") : undefined;
			const next = fn(current);
			if (next !== undefined) {
				// Only create directory when we actually need to write
				if (!existsSync(dir)) {
					mkdirSync(dir, { recursive: true });
				}
				if (!release) {
					release = this.acquireLockSyncWithRetry(path);
				}
				writeFileSync(path, next, "utf-8");
			}
		} finally {
			if (release) {
				release();
			}
		}
	}
}
```

完整顺序是：确定 global 或 project 路径 → 文件存在时先加锁再读 → 把文本交给调用方回调 → 有新文本则写回 → finally 释放。回调抛错也会进入 finally。同步加锁只对 ELOCKED 重试，最多尝试 10 次，每次间隔约 20ms。

需要按源码区分一个边界：文件不存在时，回调先收到 undefined；若需要首次写入，之后才创建目录并加锁。因此“先加锁再读取当前文件”的完整顺序对应已有文件分支，不能把首次创建分支说成同样的顺序。

**4. OAuth 刷新：AuthStorage 真正怎样使用异步 Lock。**

原始代码：[auth-storage.ts:390](/source/?file=5c78ca37f246b4a65d.ts#L390)。保留完整方法或类，仅调整外层缩进。

```ts
private async refreshOAuthTokenWithLock(
	providerId: OAuthProviderId,
): Promise<{ apiKey: string; newCredentials: OAuthCredentials } | null> {
	const provider = getOAuthProvider(providerId);
	if (!provider) {
		return null;
	}

	const result = await this.storage.withLockAsync(async (current) => {
		const currentData = this.parseStorageData(current);
		this.data = currentData;
		this.loadError = null;

		const cred = currentData[providerId];
		if (cred?.type !== "oauth") {
			return { result: null };
		}

		if (Date.now() < cred.expires) {
			return { result: { apiKey: provider.getApiKey(cred), newCredentials: cred } };
		}

		const oauthCreds: Record<string, OAuthCredentials> = {};
		for (const [key, value] of Object.entries(currentData)) {
			if (value.type === "oauth") {
				oauthCreds[key] = value;
			}
		}

		const refreshed = await getOAuthApiKey(providerId, oauthCreds);
		if (!refreshed) {
			return { result: null };
		}

		const merged: AuthStorageData = {
			...currentData,
			[providerId]: { type: "oauth", ...refreshed.newCredentials },
		};
		this.data = merged;
		this.loadError = null;
		return { result: refreshed, next: JSON.stringify(merged, null, 2) };
	});

	return result;
}
```

这里最关键的是进入 withLockAsync 后重新读取 currentData，并再次检查 expires：另一个进程已刷新就直接使用新凭据；仍过期才调用 getOAuthApiKey()。返回的 result 是调用结果，next 是后端需要写回的完整认证 JSON。

其文件后端 withLockAsync() 的完整实现如下，能看到真正的 lockfile.lock()、重试选项、锁状态检查以及异步释放：

原始代码：[auth-storage.ts:122](/source/?file=5c78ca37f246b4a65d.ts#L122)。保留完整方法或类，仅调整外层缩进。

```ts
async withLockAsync<T>(fn: (current: string | undefined) => Promise<LockResult<T>>): Promise<T> {
	this.ensureParentDir();
	this.ensureFileExists();

	let release: (() => Promise<void>) | undefined;
	let lockCompromised = false;
	let lockCompromisedError: Error | undefined;
	const throwIfCompromised = () => {
		if (lockCompromised) {
			throw lockCompromisedError ?? new Error("Auth storage lock was compromised");
		}
	};

	try {
		release = await lockfile.lock(this.authPath, {
			retries: {
				retries: 10,
				factor: 2,
				minTimeout: 100,
				maxTimeout: 10000,
				randomize: true,
			},
			stale: 30000,
			onCompromised: (err) => {
				lockCompromised = true;
				lockCompromisedError = err;
			},
		});

		throwIfCompromised();
		const current = existsSync(this.authPath) ? readFileSync(this.authPath, "utf-8") : undefined;
		const { result, next } = await fn(current);
		throwIfCompromised();
		if (next !== undefined) {
			writeFileSync(this.authPath, next, "utf-8");
			chmodSync(this.authPath, 0o600);
		}
		throwIfCompromised();
		return result;
	} finally {
		if (release) {
			try {
				await release();
			} catch {
				// Ignore unlock errors when lock is compromised.
			}
		}
	}
}
```

认证文件后端先确保目录与文件存在，再等待锁，读取当前文本并 await 回调，有 next 才写回。锁被报告为 compromised 时会记录状态，并在后续检查点抛错；finally 中尝试 await release()。这些都是 Pi Agent 现有实现中的使用位置。

### 6. ResourceLoader：资源怎样定义和加载

**例子：** 午饭项目已经放好选餐 Skill、需求模板、项目规则和扩展。希望初始化后能列出它们，而不是立刻执行点餐。

本地对应的接口叫 `ResourceLoader`，默认实现叫 `DefaultResourceLoader`。下面把每类输入分开看。

#### 6.1 加载器：构造对象与读取资源

**例子：** 只 `new` 一个加载器，还看不到项目文件；`reload()` 后才有加载结果。

```ts
const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
resourceLoader.getAgentsFiles(); // 此时 { agentsFiles: [] }
await resourceLoader.reload();
```

**代码中的定义。** [ResourceLoader](/source/?file=9d3a691c82fb128e60.ts#L30) 用 getter 暴露各类结果：

```ts
// 接口节选。
getExtensions(): LoadExtensionsResult;
getSkills(): { skills: Skill[]; diagnostics: ResourceDiagnostic[] };
getPrompts(): { prompts: PromptTemplate[]; diagnostics: ResourceDiagnostic[] };
getThemes(): { themes: Theme[]; diagnostics: ResourceDiagnostic[] };
getAgentsFiles(): { agentsFiles: Array<{ path: string; content: string }> };
getSystemPrompt(): string | undefined;
getAppendSystemPrompt(): string[];
reload(): Promise<void>;
```

**大致怎样加载。** [构造函数](/source/?file=9d3a691c82fb128e60.ts#L216) 保存目录、开关、附加路径和覆盖回调，复用 SettingsManager，创建 EventBus、DefaultPackageManager、初始 ExtensionRuntime，并把资源结果设为空。

[reload()](/source/?file=9d3a691c82fb128e60.ts#L343) 才刷新设置、解析来源、读取资源并保存结果。SDK 自己创建默认加载器时会调用 reload；宿主传入已有加载器时，需要宿主先准备好。

#### 6.2 EventBus：扩展之间的共享频道

**例子：** 一段扩展发布午饭预算，另一段订阅同一频道。

```ts
const bus = createEventBus();
const off = bus.on("lunch:ready", (data) => console.log(data));
bus.emit("lunch:ready", { budget: 20 });
off();
```

**代码中的定义。** [event-bus.ts](/source/?file=6982c4638dc60fbe73.ts#L4)：

```ts
export interface EventBus {
  emit(channel: string, data: unknown): void;
  on(channel: string, handler: (data: unknown) => void): () => void;
}
```

**大致怎样建立。** `createEventBus()` 创建 Node EventEmitter，返回 emit、on 和清空订阅的方法。加载器默认创建一份，也可以使用宿主传入的实例，再把同一总线交给各扩展。

`on()` 返回取消订阅函数；处理函数可以异步执行，但 `emit()` 返回 void，不会等待所有异步处理完成。这是扩展共享通信入口，Agent 生命周期事件另有订阅机制。

#### 6.3 DefaultPackageManager：先找到资源路径

**文件例子。** 如果用资源包，项目 `/course/lunch/.pi/settings.json` 可以增加以下字段，其他设置保持原有内容：

```json
{
  "packages": ["./lunch-pack"]
}
```

对应 `/course/lunch/.pi/lunch-pack/package.json`：

```json
{
  "name": "lunch-course-resources",
  "version": "1.0.0",
  "type": "module",
  "pi": {
    "extensions": ["./extensions/lunch-rules.ts"],
    "skills": ["./skills"],
    "prompts": ["./prompts"],
    "themes": ["./themes"]
  }
}
```

包内路径相对包根目录；项目设置中的 `./lunch-pack` 相对 `cwd/.pi`。若使用第 5.1 节的默认资源目录，则可不配置这个包，两者是可选的摆放方式。

**代码中的定义。** [ResolvedResource](/source/?file=55e69bd078c31ff5e2.ts#L44) 表示找到的一项资源：

```ts
export interface ResolvedResource {
  path: string;
  enabled: boolean;
  metadata: PathMetadata;
}
```

`ResolvedPaths` 分成 extensions、skills、prompts、themes 四类数组；metadata 记录来源、作用域、是否来自包等。

**大致怎样加载。** [resolve()](/source/?file=55e69bd078c31ff5e2.ts#L846) 分别读取全局和项目原始设置，解析包来源、显式本地路径，再补上自动发现目录。[readPiManifest()](/source/?file=55e69bd078c31ff5e2.ts#L2030) 读取 package.json 并返回 `pi` 字段。

自动发现包括项目 `.pi` 和 agentDir 下对应资源目录，当前版本还发现用户及祖先目录的 `.agents/skills`。普通设置数组合并是项目覆盖全局，但这里取两层原始配置，按资源来源规则收集两边，不能套用简单数组覆盖结论。

输出仍然是路径与来源信息，尚未变成 Skill 对象或扩展工具。

#### 6.4 扩展：文件中的注册函数

**文件例子。** `/course/lunch/.pi/extensions/lunch-rules.ts`：

```ts
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function lunchRules(pi: ExtensionAPI) {
  pi.on("session_start", async (_event, ctx) => {
    console.log("午饭会话已启动：", ctx.cwd);
  });
}
```

加载时执行 `lunchRules(pi)`，只是注册处理函数；宿主后来绑定并发出 session_start 时，才执行 console.log。

**代码中的定义。** [Extension 与 LoadExtensionsResult](/source/?file=baffea2d47e73908cd.ts) 中与本例有关的字段：

```ts
// Extension 字段节选。
path: string;
handlers: Map<string, HandlerFn[]>;
tools: Map<string, RegisteredTool>;
commands: Map<string, RegisteredCommand>;
flags: Map<string, ExtensionFlag>;

// 加载结果。
extensions: Extension[];
errors: Array<{ path: string; error: string }>;
runtime: ExtensionRuntime;
```

**大致怎样加载。** [loadExtensions()](/source/?file=d170abdf93d664a78b.ts#L452) 加载模块并执行导出工厂，把工具、命令和处理函数登记在 Extension 中；内联 `extensionFactories` 则直接调用工厂。

共享的 [ExtensionRuntime](/source/?file=d170abdf93d664a78b.ts#L136) 初始带有动作占位函数、flagValues 和待注册 provider 队列。注册可以发生在加载阶段；发送消息、切换模型等会话动作要等 Runner 绑定。扩展加载不等于启动事件已执行，也不等于业务工具已调用。

#### 6.5 Skill 与 Prompt Template：两个 Markdown 文件

**文件例子。** `/course/lunch/.pi/skills/choose-lunch/SKILL.md`：

````md
---
name: choose-lunch
description: 按口味、价格和库存比较午饭候选。
---
先排除不符合口味的餐品，再比较预算内候选，最后查询库存。
````

`/course/lunch/.pi/prompts/lunch.md`：

````md
---
description: 按预算准备午饭方案
---
帮我选一份不辣的午饭，预算 $1 元。先给方案，不要下单。
````

第二份在输入 `/lunch 20` 时，可以展开成带 20 元预算的需求。

```ts
resourceLoader.getSkills().skills.map((s) => s.name);   // 包含 choose-lunch
resourceLoader.getPrompts().prompts.map((p) => p.name); // 包含 lunch
```

**代码中的定义。** [Skill](/source/?file=08398ed5b2b3650ff5.ts#L78) 和 [PromptTemplate](/source/?file=81f806b0803812db28.ts#L12) 的字段侧重点不同：

```ts
// Skill 的主要字段。
name: string;
description: string;
filePath: string;
baseDir: string;
sourceInfo: SourceInfo;
disableModelInvocation: boolean;

// PromptTemplate 的主要字段。
name: string;
description: string;
content: string;
filePath: string;
```

**大致怎样加载。** 加载器根据路径调用 `loadSkills()` 和 `loadPromptTemplates()`，读取 Markdown 并解析 YAML 头部，生成对象和诊断结果。

Skill 解析时会读文件，但返回对象没有保存全部正文的 content 字段，主要提供名称、描述和位置；系统提示词通常放目录说明，需要时再读取正文。模板则保存 content，供输入展开使用；名字通常来自文件名。加载模板不会自动添加用户消息。

#### 6.6 项目上下文与系统提示词来源

**文件例子。** 用户级 `/course/pi-agent/AGENTS.md`：

````md
# 通用工作要求

使用中文，回答简短。价格、库存等信息先查询再下结论。
````

项目级 `/course/lunch/AGENTS.md`：

````md
# 午饭项目规则

先用 list_meals 查价格，再用 get_stock 查库存。
用户不吃辣；没有授权时不要下单。
````

同目录没有 AGENTS.md 时，也可使用 `/course/lunch/CLAUDE.md`，内容例如：

````md
# 午饭项目规则

先核对菜单和库存，再给出预算内的不辣方案。
````

自定义角色放在 `/course/lunch/.pi/SYSTEM.md`：

````md
你是午饭助手。
根据用户口味和预算比较候选，回答包含价格和库存依据。
````

额外要求放在 `/course/lunch/.pi/APPEND_SYSTEM.md`：

````md
本次只提供选餐建议。用户未授权时，不下单，也不声称已经下单。
````

如果宿主另外想读取 `/course/lunch/USER.md`，文件内容可以是：

````md
# 用户偏好

用户不吃辣，偏好简短回答。
````

USER.md 需要宿主显式接入，不能仅放到目录中就认为默认加载器会读取。

**代码中的定义。** [ResourceLoader](/source/?file=9d3a691c82fb128e60.ts#L30) 对这三种结果分别提供：

```ts
getAgentsFiles(): { agentsFiles: Array<{ path: string; content: string }> };
getSystemPrompt(): string | undefined;
getAppendSystemPrompt(): string[];
```

**大致怎样加载。** [loadProjectContextFiles()](/source/?file=9d3a691c82fb128e60.ts#L82) 先收集用户级上下文，再按祖先到项目的顺序收集。每个目录先尝试 AGENTS.md，成功读取就采用；否则还会尝试 CLAUDE.md，不会把同目录两者都拼入。结果保存文件路径与完整正文。

SYSTEM.md 与 APPEND_SYSTEM.md 各自按项目 `.pi` → agentDir 的优先级发现一份；显式选项优先。`resolvePromptInput()` 支持正文或文件位置，存在的文件会被读取成字符串。

例如自动发现后，`getSystemPrompt()` 返回“你是午饭助手……”正文，`getAppendSystemPrompt()` 返回包含追加要求的字符串数组；此时还未组织成最终系统提示词。

USER.md 不在默认候选中，宿主可以读取后通过 `agentsFilesOverride` 注入。也可以直接构造 `{ path, content }` 注入，此时磁盘上不必真的存在 USER.md；区别在于宿主有没有实际执行文件读取。

#### 6.7 主题：JSON 颜色表怎样变成 Theme

**文件例子。** `/course/lunch/.pi/themes/lunch-dark.json` 大概如下。这是结构节选；完整颜色字段可直接参考本地 [dark.json](/source/?file=331915796bc96d86e4.json)：

```jsonc
{
  "name": "lunch-dark",
  "vars": { "accent": "#8abeb7", "gray": "#808080" },
  "colors": {
    "accent": "accent",
    "muted": "gray",
    "text": "",
    "userMessageBg": "#343541"
    // 此处省略其他必需颜色字段；实际文件需保留完整颜色表。
  },
  "export": { "pageBg": "#18181e", "cardBg": "#1e1e24" }
}
```

实际主题文件使用完整 JSON；上面用 jsonc 注释标出省略位置。

**代码中的定义。** [ThemeJsonSchema](/source/?file=da4212de3ee6595a6c.ts#L24) 定义 name、可选 vars、完整 colors 和可选 export。颜色值支持字符串或 0～255 的整数；字符串可以是色值、变量引用或空字符串。

**大致怎样加载。** [loadThemeFromPath()](/source/?file=da4212de3ee6595a6c.ts#L618) 读文件 → 解析 JSON → 校验 schema → 解析 vars 引用 → 创建 Theme。例如 `colors.accent: "accent"` 引用 `vars.accent`。

结果从 `getThemes()` 取得，错误进入 diagnostics。加载资源后，还要由界面选择使用哪个主题；主题内容不作为午饭业务规则放进系统提示词。

#### 6.8 reload 与服务工厂：把结果准备齐

**例子：** 午饭项目放好前面几类资源后，宿主希望得到一套可复用的服务，再创建会话。

```ts
const services = await createAgentSessionServices({ cwd, agentDir });
services.resourceLoader.getSkills();
services.modelRegistry.find("lunch-lab", "lunch-demo");
```

**代码中的定义。** [AgentSessionServices](/source/?file=39808a3defe33903af.ts#L66) 把同一工作目录的依赖聚在一起：

```ts
export interface AgentSessionServices {
  cwd: string;
  agentDir: string;
  authStorage: AuthStorage;
  settingsManager: SettingsManager;
  modelRegistry: ModelRegistry;
  resourceLoader: ResourceLoader;
  diagnostics: AgentSessionRuntimeDiagnostic[];
}
```

**大致怎样加载。** ResourceLoader 的 reload 主线只需要记住：

```text
刷新设置 → 解析包与资源路径 → 筛选启用项
→ 加载扩展与内联工厂 → 检查冲突
→ 更新 Skill、模板、主题
→ 读取项目上下文 → 解析系统提示词来源 → 保存结果
```

[createAgentSessionServices()](/source/?file=39808a3defe33903af.ts#L131) 补齐设置、认证、Registry 和加载器，等待 reload，再处理扩展暂存的 provider 注册及 flag 值。因此宿主能在创建 AgentSession 前，使用更新后的目录选择扩展提供的模型。`createAgentSessionFromServices()` 再把这些实例传给 SDK。

直接调用 SDK 则走 SDK 自己的装配路径，暂存 provider 注册在后续 Runner 核心绑定时处理，两条路径的时序不同。

reload 会重新读取文件设置，也不会顺便调用 ModelRegistry.refresh。每类资源有独立 errors 或 diagnostics；reload 返回不代表所有候选都成功加载。`noSkills` 等开关主要影响默认来源，显式附加路径在相应分支中仍可能保留。

### 7. 模型选择：显式选项、历史与默认设置

**例子：** 昨天的午饭会话保存模型 A，今天宿主显式传模型 B，则使用 B；未显式传入时，才尝试恢复 A。若恢复失败，再考虑设置与可用目录。

**代码中的定义。** [SessionContext](/source/?file=043f6d188e65e3207b.ts#L165) 为恢复提供这三类结果：

```ts
export interface SessionContext {
  messages: AgentMessage[];
  thinkingLevel: string;
  model: { provider: string; modelId: string } | null;
}
```

SDK 还接受 `options.model`，ModelRegistry 提供 `find()` 与认证配置检查。

**大致怎样准备。** [sdk.ts](/source/?file=07502145bf1ffa712b.ts#L203) 先 `buildSessionContext()`，判断是否有恢复消息，再按以下优先级选择：

```text
options.model
→ 历史模型存在且有认证来源
→ findInitialModel()：设置默认模型
→ 可用模型中的 provider 默认模型，再取首个可用模型
```

[findInitialModel()](/source/?file=f490b6302cb35e5f4c.ts#L478) 也有 CLI 与 scopedModels 分支，但这里 SDK 没传 CLI 模型参数，并传入空 scopedModels，不能套用其他入口的全部分支。

还有一个关键差别：恢复历史模型会检查认证来源；设置默认模型找到后，该分支直接返回，不再检查认证。选出了 Model 对象仍不保证请求时有可用 key。完全没选出模型时，SDK 返回 fallback 说明；后续普通输入还会检查运行条件。

### 8. Thinking level：设置值还要结合模型能力

**例子：** 项目设置为 `high`。选中的午饭模型声明 `reasoning: true`，创建时可以保留 high；若不支持 reasoning，则改为 off。

**代码中的定义。** Settings 的 `defaultThinkingLevel` 包含 off、minimal、low、medium、high、xhigh；SDK 接受显式 `options.thinkingLevel`，恢复上下文也带 thinkingLevel。

**大致怎样准备。** [SDK 的选择代码](/source/?file=07502145bf1ffa712b.ts#L223) 按下面顺序处理：

```text
显式 thinkingLevel
→ 有恢复消息时，使用分支上的 thinking 设置；缺少对应 Entry 则查默认设置
→ 默认设置或 DEFAULT_THINKING_LEVEL（medium）
→ 没有模型或 model.reasoning 为 false：off
```

关键能力判断只需保留这几行：

```ts
if (!model || !model.reasoning) {
  thinkingLevel = "off";
}
```

这里的 high 是模型思考配置，与用户的“20 元预算”是不同参数。

### 9. Agent：状态和回调怎样装进去

**例子：** 模型已经选好，但还没有收到本次午饭输入。此时 Agent 的聊天消息可以是空数组，工具与系统提示词稍后由 AgentSession 安装。

```ts
// SDK 装配位置节选，其他回调见源码。
agent = new Agent({
  initialState: { systemPrompt: "", model, thinkingLevel, tools: [] },
  convertToLlm: convertToLlmWithBlockImages,
  // streamFn、transformContext、队列与传输配置在同一构造位置传入。
});
```

**代码中的定义。** [AgentOptions](/source/?file=3688aa044ebb960834.ts#L109) 提供初始状态、消息转换、streamFn、上下文变换、队列模式和请求回调等选项。Agent 内部状态包括 systemPrompt、model、thinkingLevel、tools、messages 和当前运行状态。

**大致怎样建立。** [SDK](/source/?file=07502145bf1ffa712b.ts#L261) 安装转换与请求函数；[Agent 构造函数](/source/?file=3688aa044ebb960834.ts#L207) 建立状态、两条输入队列并保存这些回调。

| 入口 | 后续用途 |
|---|---|
| `convertToLlm` | 转换内部消息，并按设置过滤图片 |
| `streamFn` | 请求时解析 Registry 认证与 headers，再调用 streamSimple |
| `transformContext` | 通过共享引用取得当前 ExtensionRunner，处理上下文 |
| `onPayload/onResponse` | 请求前、响应后的扩展入口 |
| 队列与传输选项 | steering、followUp、transport、thinking budgets 等 |

保存函数不表示立即执行它；这一步不会发出模型请求。`extensionRunnerRef` 是可更新引用，等下一阶段 Runner 建立后，这些回调就能读到它。底层 tools 与 messages 的 setter 复制外层数组，具体消息内容仍按各自数据结构保存。

### 10. 恢复消息，或为新会话记录初始设置

**例子：** 新建午饭会话时聊天消息仍为 `[]`，但历史树先记下模型和 thinking。打开旧会话时，Agent 直接装入当前分支重建出的消息。

**代码中的定义。** Agent 有 `state.messages: AgentMessage[]`；SessionManager 中的 model_change 和 thinking_level_change 则是设置 Entry，两者不是同一种记录。

**大致怎样装入。** [sdk.ts 的恢复分支](/source/?file=07502145bf1ffa712b.ts#L364) 只需看这几处关键语句：

```ts
// 旧会话分支。
agent.state.messages = existingSession.messages;

// 新会话分支：有模型时记录模型，再记录 thinking。
sessionManager.appendModelChange(model.provider, model.id);
sessionManager.appendThinkingLevelChange(thinkingLevel);
```

这些语句位于不同分支，不能直接当成连续执行的宿主代码。旧会话若缺少 thinking Entry，还会补记当前等级。设置 Entry 留在历史树中，不会作为普通聊天消息发给模型。

### 11. AgentSession：把依赖接成一个会话

**例子：** 午饭 Agent 已有模型和历史，现在要让完成消息进入保存流程，同时把扩展、工具和项目规则接起来。

**代码中的定义。** [AgentSessionConfig](/source/?file=24209413646c397dc9.ts#L141) 的核心依赖是：

```ts
// 配置字段节选。
agent: Agent;
sessionManager: SessionManager;
settingsManager: SettingsManager;
cwd: string;
resourceLoader: ResourceLoader;
customTools?: ToolDefinition[];
modelRegistry: ModelRegistry;
```

**大致怎样建立。** [构造函数](/source/?file=24209413646c397dc9.ts#L313) 先保存依赖与选项，再做三件事：

```ts
this._unsubscribeAgent = this.agent.subscribe(this._handleAgentEvent);
this._installAgentToolHooks();

this._buildRuntime({
  activeToolNames: this._initialActiveToolNames,
  includeAllExtensionTools: true,
});
```

第一步接入内部事件处理与保存，第二步安装工具调用前后的扩展入口，第三步建立 Runner、工具注册表和基础提示词。宿主之后的显示订阅另行接入。

### 12. Runner 与工具：定义、注册、允许和启用

**例子：** 午饭应用提供查询库存的工具，参数是餐品名称数组。下面是宿主自定义工具示例，执行时使用教学库存：

```ts
const getStockTool = defineTool({
  name: "get_stock",
  label: "查询库存",
  description: "查询指定午饭库存，0 表示售罄，不下单。",
  parameters: Type.Object({ meals: Type.Array(Type.String()) }),
  async execute(_id, params) {
    const inventory: Record<string, number> = { "鸡腿饭": 0, "蛋炒饭": 8 };
    const stocks = params.meals.map((name) => ({ name, stock: inventory[name] ?? null }));
    return {
      content: [{ type: "text", text: JSON.stringify(stocks) }],
      details: { stocks },
    };
  },
});
```

同样可以提供菜单工具：

```ts
const listMealsTool = defineTool({
  name: "list_meals",
  label: "查询菜单",
  description: "查询午饭价格与是否辣，不下单。",
  parameters: Type.Object({}),
  async execute() {
    const menu = [
      { name: "牛肉面", price: 30, spicy: false },
      { name: "鸡腿饭", price: 20, spicy: false },
      { name: "蛋炒饭", price: 10, spicy: false },
    ];
    return { content: [{ type: "text", text: JSON.stringify(menu) }], details: { menu } };
  },
});
```

把两份定义交给 SDK 的方式：

| 内容 | 示例 | 意义 |
|---|---|---|
| 定义 | `customTools: [listMealsTool, getStockTool]` | 确实有 Schema 和 execute |
| 允许范围 | `tools: ["read", "list_meals", "get_stock"]` | 本会话允许这些名称 |
| 最终结果 | `agent.state.tools` | 已注册且选中的工具对象 |

**代码中的定义。** [ToolDefinition](/source/?file=baffea2d47e73908cd.ts#L422) 提供 name、description、parameters 和 execute 等字段。模型需要名称、说明与参数 Schema；程序需要实际 execute。定义工具时不会自动执行库存查询。

ExtensionRuntime 是加载阶段建立的共享状态与动作入口；ExtensionRunner 是后来建立的调度对象，持有已加载扩展、runtime、cwd、SessionManager 与 ModelRegistry。

**大致怎样建立。** [_buildRuntime()](/source/?file=24209413646c397dc9.ts#L2390) 与 [_refreshToolRegistry()](/source/?file=24209413646c397dc9.ts#L2297) 的主线是：

```text
按 cwd 与 Settings 创建内置工具定义
→ 取得 ResourceLoader 的扩展结果
→ 创建 ExtensionRunner，更新共享引用
→ 绑定核心动作与已有宿主能力
→ 合并内置、扩展、SDK customTools 定义
→ 按允许范围过滤，包装执行函数，建立 Map
→ 选择活跃工具，写入 agent.state.tools
```

同名工具在合并中由后放入的定义覆盖先放入的定义。只写 `"get_stock"` 不会凭空产生执行函数。[setActiveToolsByName()](/source/?file=24209413646c397dc9.ts#L819) 会跳过注册表中不存在的名称，并根据有效工具重建系统提示词。

### 13. 系统提示词：加载文本怎样组合起来

**例子：** 第 6.6 节的文件加载以后，午饭会话的系统提示词大致由以下内容组成：

```text
你是午饭助手……                         ← SYSTEM.md
本次只提供选餐建议……                   ← APPEND_SYSTEM.md
# Project Context
用户级与项目级 AGENTS.md 的路径和正文
可见 Skill 的名称、描述与位置           ← read 工具可用时
当前日期与工作目录
```

**代码中的定义。** [BuildSystemPromptOptions](/source/?file=16fcd113d065a4c54a.ts#L9) 主要接受：

```ts
// 字段节选。
customPrompt?: string;
appendSystemPrompt?: string;
cwd: string;
contextFiles?: Array<{ path: string; content: string }>;
skills?: Skill[];
selectedTools?: string[];
```

**大致怎样组织。** [_rebuildSystemPrompt()](/source/?file=24209413646c397dc9.ts#L916) 读取 ResourceLoader 的结果，再加上有效工具的提示片段和指南，传给 [buildSystemPrompt()](/source/?file=16fcd113d065a4c54a.ts#L31)。

有自定义角色时，从该正文开始，追加要求、项目上下文、符合条件的 Skill 目录，最后加日期与 cwd；没有自定义角色时，走默认 coding assistant 分支。自定义分支不会再执行后面的默认角色与默认指南构建。

最终得到字符串并写入 `agent.state.systemPrompt`。历史消息在 messages 中，工具 Schema 与 execute 在 tools 中，三类数据分别准备。

### 14. 宿主绑定：启动事件何时运行

**例子：** 宿主给午饭会话接上错误显示，并等待扩展启动：

```ts
await session.bindExtensions({
  onError(error) { console.error("扩展错误：", error.error); },
});
```

此时第 6.4 节注册的 session_start 处理函数才会输出“午饭会话已启动”。

**代码中的定义。** [ExtensionBindings](/source/?file=24209413646c397dc9.ts#L172) 提供可选 UI 上下文、会话命令动作、shutdownHandler 与 onError。

**大致怎样接入。** [bindExtensions()](/source/?file=24209413646c397dc9.ts#L2088) 保存宿主能力，然后：

```text
应用绑定
→ 等待 session_start 处理
→ 若有 resources_discover，收集动态 Skill / 模板 / 主题路径
→ 更新资源，必要时重建系统提示词
```

只绑定 onError 不代表已提供 UI 或会话命令。`createAgentSession()` 返回与 `bindExtensions()` 返回是两个观察点：前者完成初始装配，后者等待这次启动和动态资源处理完成。

### 15. 本次输入：从准备进入执行

**例子：** 用户直接说“帮我选 20 元以内的不辣午饭”，或者使用已加载的 `/lunch 20` 模板。

```ts
await session.prompt("帮我选一份不辣的午饭，预算 20 元。先给方案，不要下单。");
```

**代码中的定义。** [PromptOptions](/source/?file=24209413646c397dc9.ts#L181) 控制模板展开、图片、运行中输入的 steer/followUp 方式等；普通 prompt 的文本会被组织为新的 user 消息。

**大致怎样处理。** [AgentSession.prompt()](/source/?file=24209413646c397dc9.ts#L968) 依次处理命令、input handler、Skill 命令和模板，检查运行状态、模型与认证，构造本次新消息，再等待 before_agent_start。

普通路径最终调用：

```ts
await this.agent.prompt(messages);
await this.waitForRetry();
```

历史此前已经放在 Agent 状态中，这里的 messages 主要是本次新输入和补充消息。命令处理、扩展接管或排队分支可能提前返回；真正进入模型与工具循环的过程留在第 14 讲。

## 第三部分：把各块装配关系连起来

### 16. 完整午饭宿主示例

**例子：** 下面把导入、业务数据、两个工具、目录、设置、认证、模型目录、历史、资源、会话创建、订阅、启动绑定和清理放进同一份 TypeScript 文件。变量和工具都在这里定义，可以整段阅读，不需要拼接前面各节的片段。

不传参数时新建会话；传入 JSONL 路径时恢复会话，并按该会话的 cwd 加载项目资源。模型沿用已有配置与恢复规则，菜单和库存使用教学数据。代码最后打印准备结果，`session.prompt()` 保留为第 14 讲的执行入口。

```ts
import { resolve, join } from "node:path";
import { Type } from "typebox";
import {
  AuthStorage,
  DefaultResourceLoader,
  ModelRegistry,
  SessionManager,
  SettingsManager,
  createAgentSession,
  defineTool,
  getAgentDir,
} from "@mariozechner/pi-coding-agent";

// A. 教学业务数据：定义数据和工具时，不会执行查询。
const meals = [
  { name: "牛肉面", price: 30, spicy: false, stock: 5 },
  { name: "鸡腿饭", price: 20, spicy: false, stock: 0 },
  { name: "蛋炒饭", price: 10, spicy: false, stock: 8 },
];

// B. 工具定义：Schema 给模型使用，execute 给程序执行。
const listMealsTool = defineTool({
  name: "list_meals",
  label: "查询午饭菜单",
  description: "查询午饭名称、价格和是否辣，不查询库存，不下单。",
  parameters: Type.Object({}),
  async execute() {
    const menu = meals.map(({ name, price, spicy }) => ({ name, price, spicy }));
    return {
      content: [{ type: "text", text: JSON.stringify(menu) }],
      details: { menu },
    };
  },
});

const getStockTool = defineTool({
  name: "get_stock",
  label: "查询午饭库存",
  description: "查询指定午饭库存，0 表示售罄，null 表示未找到，不下单。",
  parameters: Type.Object({ meals: Type.Array(Type.String()) }),
  async execute(_toolCallId, params) {
    const stocks = params.meals.map((name) => ({
      name,
      stock: meals.find((meal) => meal.name === name)?.stock ?? null,
    }));
    return {
      content: [{ type: "text", text: JSON.stringify(stocks) }],
      details: { stocks },
    };
  },
});

async function prepareLunchSession(sessionFile?: string) {
  // C. 先决定历史来源，再以历史所属的 cwd 准备依赖。
  const sessionManager = sessionFile
    ? SessionManager.open(resolve(sessionFile))
    : SessionManager.create(process.cwd());
  const cwd = sessionManager.getCwd();
  const agentDir = getAgentDir();

  // D. 设置、认证来源与模型目录。
  const settingsManager = SettingsManager.create(cwd, agentDir);
  const authStorage = AuthStorage.create(join(agentDir, "auth.json"));
  const modelRegistry = ModelRegistry.create(authStorage, join(agentDir, "models.json"));

  // E. 加载项目资源，明确提供午饭角色和教学用户资料。
  const resourceLoader = new DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager,
    systemPromptOverride: () => [
      "你是午饭助手。",
      "先查询菜单价格，再检查预算内候选的库存。",
      "根据用户口味与预算比较方案，回答简短清楚。",
      "本例只提供查询能力，不执行下单。",
    ].join("\n"),
    agentsFilesOverride: (base) => ({
      agentsFiles: [
        ...base.agentsFiles,
        // 直接注入内容，不要求磁盘上真的存在 USER.md。
        { path: join(cwd, "USER.md"), content: "用户不吃辣，偏好简短回答。" },
      ],
    }),
  });
  await resourceLoader.reload();

  console.log("设置准备结果：", {
    defaultProvider: settingsManager.getDefaultProvider(),
    defaultModel: settingsManager.getDefaultModel(),
    thinkingLevel: settingsManager.getDefaultThinkingLevel(),
    compaction: settingsManager.getCompactionSettings(),
    retry: settingsManager.getRetrySettings(),
  });
  console.log("设置读取错误：", settingsManager.drainErrors());
  console.log("认证读取错误：", authStorage.drainErrors());
  console.log("模型目录：", {
    all: modelRegistry.getAll().length,
    configured: modelRegistry.getAvailable().length,
    error: modelRegistry.getError(),
  });
  console.log("资源准备结果：", {
    skills: resourceLoader.getSkills().skills.map((s) => s.name),
    prompts: resourceLoader.getPrompts().prompts.map((p) => p.name),
    contextFiles: resourceLoader.getAgentsFiles().agentsFiles.map((f) => f.path),
    extensions: resourceLoader.getExtensions().extensions.map((e) => e.path),
  });
  console.log("资源诊断：", {
    extensions: resourceLoader.getExtensions().errors,
    skills: resourceLoader.getSkills().diagnostics,
    prompts: resourceLoader.getPrompts().diagnostics,
    themes: resourceLoader.getThemes().diagnostics,
  });

  // F. SDK 完成模型选择、历史恢复、Agent 与 AgentSession 装配。
  const { session, modelFallbackMessage } = await createAgentSession({
    cwd,
    agentDir,
    settingsManager,
    authStorage,
    modelRegistry,
    sessionManager,
    resourceLoader,
    customTools: [listMealsTool, getStockTool],
    tools: ["read", "list_meals", "get_stock"],
  });
  if (modelFallbackMessage) console.error(modelFallbackMessage);

  // G. 宿主的显示订阅；内部的消息保存订阅已由 AgentSession 安装。
  const unsubscribe = session.subscribe((event) => {
    if (event.type === "message_end" && event.message.role === "assistant") {
      for (const part of event.message.content) {
        if (part.type === "text") console.log(part.text);
      }
    }
  });

  // H. 接上宿主错误处理，等待启动事件和动态资源处理。
  try {
    await session.bindExtensions({
      onError(error) {
        console.error("扩展错误：", error.error);
      },
    });
  } catch (error) {
    unsubscribe();
    session.dispose();
    throw error;
  }

  return { session, unsubscribe };
}

// 不传参数：新建会话；传入 JSONL 路径：恢复该文件的会话。
const { session, unsubscribe } = await prepareLunchSession(process.argv[2]);
try {
  console.log("最终准备结果：", {
    cwd: session.sessionManager.getCwd(),
    sessionFile: session.sessionManager.getSessionFile(),
    model: session.model?.id,
    thinkingLevel: session.thinkingLevel,
    historyMessages: session.agent.state.messages.length,
    activeTools: session.getActiveToolNames(),
    systemPrompt: session.agent.state.systemPrompt,
  });

  // 第 14 讲的执行入口；实际运行需要可用的模型与认证。
  await session.prompt("帮我选一份不辣的午饭，预算 20 元。先给方案，不要下单。");
} finally {
  unsubscribe();
  session.dispose();
}
```

代码使用当前 SDK 与 TypeBox，需要相应依赖及 SDK 构建或解析环境。默认用户级设置由 getAgentDir() 决定，项目级资源按 cwd 发现；如果沿用前文虚构的模型地址，仅能用于观察准备过程，真实执行前要使用实际可用的模型配置。

**代码与前文的对应关系。**

| 代码块 | 完成的准备 | 对应讲解 |
|---|---|---|
| A、B | 菜单、库存及两个完整工具定义 | 第 12 节 |
| C | 新建或打开历史，确定工作目录 | 第 5.1、5.5 节 |
| D | 设置、认证来源、模型目录 | 第 5.2～5.4 节 |
| E | 加载资源，提供午饭角色与用户资料 | 第 6、13 节 |
| F | 模型与 thinking 选择、历史恢复、Agent 与会话装配 | 第 7～12 节 |
| G、H | 显示订阅、错误处理、启动与动态资源 | 第 11、14 节 |
| 最后的 prompt 与 finally | 执行入口、取消订阅和释放会话 | 第 15 节及第 14 讲 |

新建会话在没有启动扩展额外添加消息时，historyMessages 为 0；活跃工具为 read、list_meals、get_stock。模型与 thinkingLevel 由配置、恢复规则和模型能力决定。准备结果打印完毕后，代码会取消订阅并释放会话；取消注释 prompt 那一行，才进入“查菜单 → 查库存 → 给建议”的执行阶段。

### 源码阅读索引：第 13 讲的 ⭐️ 标记

以下列出本讲涉及的源码文件。每个标记注明讲义节号与职责；链接行号已按当前注释位置更新。

| 源码文件 | 主要内容 | 对应节号 |
|---|---|---|
| [core/sdk.ts](/source/?file=07502145bf1ffa712b.ts#L176) | 依赖补齐、模型与历史恢复、会话装配 | 5.1、7～11、16 |
| [config.ts](/source/?file=f56342646902820db9.ts#L209) | 用户级配置目录 | 5.1 |
| [core/settings-manager.ts](/source/?file=a7b1c7acc6cf6a0b83.ts#L240) | 两层设置、字段合并与文件 Lock | 5.2、5.6 |
| [core/auth-storage.ts](/source/?file=5c78ca37f246b4a65d.ts#L197) | 凭据加载、认证解析与 OAuth Lock | 5.3、5.6 |
| [core/resolve-config-value.ts](/source/?file=4f8a21838e568dc621.ts#L18) | 认证配置值解析 | 5.3 |
| [core/model-registry.ts](/source/?file=0e557b1d53638cfcd2.ts#L303) | 模型目录、覆盖项与请求认证 | 5.4、7 |
| [core/session-manager.ts](/source/?file=043f6d188e65e3207b.ts#L680) | 历史容器、Header 与恢复上下文 | 5.5、7、10 |
| [core/resource-loader.ts](/source/?file=9d3a691c82fb128e60.ts#L161) | 资源构造、reload、结果与动态扩展 | 6、13～14 |
| [core/event-bus.ts](/source/?file=6982c4638dc60fbe73.ts#L15) | 扩展共享事件频道 | 6.2 |
| [core/package-manager.ts](/source/?file=55e69bd078c31ff5e2.ts#L749) | 资源包清单与路径发现 | 6.3 |
| [core/extensions/types.ts](/source/?file=baffea2d47e73908cd.ts#L422) | 扩展结果、Runtime 与工具定义 | 6.4、12 |
| [core/extensions/loader.ts](/source/?file=d170abdf93d664a78b.ts#L452) | 扩展模块与工厂注册 | 6.4 |
| [core/extensions/runner.ts](/source/?file=1a64f1a2d3fca70128.ts#L221) | 扩展调度、核心动作与启动事件 | 6.8、9、12、14 |
| [core/skills.ts](/source/?file=08398ed5b2b3650ff5.ts#L417) | Skill 读取与目录元数据 | 6.5、13 |
| [core/prompt-templates.ts](/source/?file=81f806b0803812db28.ts#L215) | 输入模板读取与展开 | 6.5、15 |
| [modes/interactive/theme/theme.ts](/source/?file=da4212de3ee6595a6c.ts#L618) | 主题 JSON 解析与 Theme 创建 | 6.7 |
| [core/agent-session-services.ts](/source/?file=39808a3defe33903af.ts#L131) | 准备并复用 cwd 绑定的服务 | 6.8 |
| [core/model-resolver.ts](/source/?file=f490b6302cb35e5f4c.ts#L478) | 初始模型选择与回退 | 7 |
| [core/defaults.ts](/source/?file=c2072cac2086406abe.ts#L4) | 默认思考等级 | 8 |
| [pi-agent-core/agent.ts](/source/?file=3688aa044ebb960834.ts#L174) | Agent 状态、队列与请求回调 | 9、15 |
| [core/agent-session.ts](/source/?file=24209413646c397dc9.ts#L242) | 内部订阅、工具、提示词及宿主绑定 | 11～16 |
| [core/system-prompt.ts](/source/?file=16fcd113d065a4c54a.ts#L31) | 系统提示词组合 | 13 |
| [OpenClaw/agents/pi-embedded-runner/run/attempt.ts](/source/?file=4c2d09aeeb74b60140.ts#L437) | OpenClaw 外层运行准备入口 | 4 |

上一讲：[12 互联网 RAG 原理](/openclaw/chapter-12)  
下一讲：[14 Agent Session 执行原理](/openclaw/chapter-14)
