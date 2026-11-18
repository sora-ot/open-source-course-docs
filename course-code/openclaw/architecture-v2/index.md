# OpenClaw / Pi Agent 架构源码讲解稿 v2

这套讲稿按 Pi Agent Book 的阅读节奏拆成 16 个可跳转页面：先建立 OpenClaw 全局地图，再进入 Pi Runtime 和 Agent Loop，随后解释 API、Tool、Message/Event、Context、Compaction、Workspace、Memory，最后回到 OpenClaw 的宿主扩展与完整请求例子。

## 版本说明

- OpenClaw：`v2026.4.22`，commit `00bd2cf7a376f1fba26291c6c4766f1f15cbdfa5`。
- Pi：`v0.69.0`，commit `85a9ce30241adf7ef62e7f4ad8bbfe2580a387e0`。
- Pi Agent Book 第 1–9 章使用较新的 Pi 版本，适合借鉴问题推进、图解和算法讲解顺序；本地文件名、函数名和默认行为以 Pi `v0.69.0` 为准。
- PiMono 精读对应较早的源码，适合解释 `agent-loop.ts`、`agent.ts` 和 AI Adapter 的分层思想。
- InferLoop 是 OpenClaw `2026.4.x` 的二手解析；本稿使用它的叙事线索，但所有 OpenClaw 路径和调用关系回到本地 `v2026.4.22` checkout 核对。

## 阅读方式

每页遵循同一套结构：问题引入 → 直觉解释 → 技术定义 → 必要算法 → 源码对应 → 具体例子或流程图 → 讲解建议。代码块中明确写出“教学伪代码”的部分用于表达控制流程，不是源码原文。

## 目录

### 第一部分：OpenClaw 全局地图

1. [M01：OpenClaw 是什么](chapters/M01.md)（网页基准 6,825 字）
2. [M02：OpenClaw 总体架构](chapters/M02.md)（网页基准 4,215 字）
3. [M03：一条请求的完整生命周期](chapters/M03.md)（网页基准 6,859 字）

### 第二部分：Pi Agent Runtime

4. [M04：为什么需要 Pi Agent Runtime](chapters/M04.md)（网页基准 5,321 字）
5. [M05：Pi 三层架构](chapters/M05.md)（网页基准 6,618 字）
6. [M06：Agent Loop](chapters/M06.md)（网页基准 4,947 字）
7. [M07：模型调用与 API Adapter](chapters/M07.md)（网页基准 5,640 字）
8. [M08：Tool System](chapters/M08.md)（网页基准 5,631 字）
9. [M09：Message 与 Event](chapters/M09.md)（网页基准 3,944 字）

### 第三部分：Context、持久化与记忆

10. [M10：Context Engineering](chapters/M10.md)
11. [M11：Compaction](chapters/M11.md)
12. [M12：Workspace 与 Bootstrap Files](chapters/M12.md)
13. [M13：Memory、Embedding 与 RAG](chapters/M13.md)

### 第四部分：OpenClaw 宿主与统一例子

14. [M14：OpenClaw 如何扩展 Pi](chapters/M14.md)
15. [M15：统一架构图与完整例子](chapters/M15.md)
16. [M16：老师会追问什么](chapters/M16.md)

## 篇幅核对

M01–M09 均按对应网页正文的非重复内容基准扩写；以下字符数是 Markdown 文件字符数，包含标题、代码和图表标记，验收时用脚本重新统计：

| 页面 | 网页基准 | 本地稿目标 |
| --- | ---: | ---: |
| M01 | 6,825 | > 6,825 |
| M02 | 4,215 | > 4,215 |
| M03 | 6,859 | > 6,859 |
| M04 | 5,321 | > 5,321 |
| M05 | 6,618 | > 6,618 |
| M06 | 4,947 | > 4,947 |
| M07 | 5,640 | > 5,640 |
| M08 | 5,631 | > 5,631 |
| M09 | 3,944 | > 3,944 |

## 图片索引

核心架构图为本地重绘，避免把网页的视觉布局当成 OpenClaw 当前实现：

- `../assets/openclaw-talk-v2/openclaw-overview.svg`：区分 WebSocket admission 与内部 ingress 的 OpenClaw 总体图。
- `../assets/openclaw-talk-v2/pi-runtime.svg`：Pi 三层与 Agent Loop 图。
- `../assets/openclaw-talk-v2/unified-request.svg`：统一请求生命周期图。

从 Pi Agent Book 页面提取到的 SVG 参考素材保存在 [`../assets/openclaw-talk-v2/reference/pi-agent-book/`](../assets/openclaw-talk-v2/reference/pi-agent-book/)，只作为章节图解风格与术语顺序参考；文件名保留抓取时的资源 id，正文不依赖这些文件才能阅读。

## 源码范围

本稿只沿决定架构的核心调用链阅读，没有递归展开整个仓库。重点包括 Pi 的 `packages/ai/src/types.ts`、`stream.ts`、`api-registry.ts`、`packages/agent/src/agent-loop.ts`、`agent.ts`、`packages/coding-agent/src/core/sdk.ts`、`agent-session.ts`、`session-manager.ts`、`core/compaction/*`，以及 OpenClaw 的 Gateway、dispatch、embedded runner、Workspace/Bootstrap、Memory plugin 和 startup/flush 文件。

返回 [总入口](../OPENCLAW_ARCHITECTURE_讲稿_v2.md)。
