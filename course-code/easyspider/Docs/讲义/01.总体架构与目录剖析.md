# 01.总体架构与目录剖析

> 目标：读完这篇，你能对着仓库任何一个文件夹说出"它在干什么"。

---

## 1. 先看全局：三层结构

EasySpider 可以理解成"**设计器 + 执行器**"两部分。

下面这张图把设计阶段和执行阶段一起画了出来：

```text
        ┌─────────────────── 设计阶段（人在操作） ───────────────────┐
        │                                                          │
        │   Extension (浏览器扩展)          ElectronJS (桌面程序)     │
        │   ├─ 在网页上选元素               ├─ 任务列表/流程图 UI      │
        │   ├─ 高亮/待选提示                ├─ 试运行（调用Selenium）  │
        │   └─ 把选中结果打成 JSON  ──WS──► ├─ 保存任务为 .json        │
        │                                  └─ 调起执行器              │
        └──────────────────────────────────────────────────────────┘
                                  │ 任务.json
                                  ▼
        ┌─────────────────── 执行阶段（机器在跑） ───────────────────┐
        │   ExecuteStage (Python 执行器)                            │
        │   └─ Selenium 驱动 Chrome，按 graph 逐节点重放，落地数据    │
        └──────────────────────────────────────────────────────────┘
```

一句话记住这张图：

> 上半部分是人在设计，下半部分是机器在跑，中间靠一份任务 JSON 连接。

---

## 2. 逐个文件夹拆解

下面一个文件夹一个文件夹地拆开看。

### 2.1 `Extension/` —— 浏览器里的"拾取器"

先看它的目录结构。

```text
Extension/manifest_v3/
├── src/manifest.json            ← 扩展的"身份证"（MV3 格式）
├── src/background.ts            ← 后台 service worker（连 WebSocket）
├── src/popup.html / popup.js    ← 点扩展图标弹出的小面板
└── src/content-scripts/         ← 【核心】注入到每个网页里运行的脚本
    ├── main.js                  ← 入口：注入工具台、绑定鼠标事件
    ├── global.js    (1186行)    ← 【心脏】选中/待选/匹配/XPath 全部算法
    ├── toolkit.vue  (934行)     ← 网页右下角那个"操作台"界面
    ├── messageInteraction.js    ← 与 Electron 的 WebSocket 通信
    ├── trial.js                 ← 试运行时的元素高亮与提示
    ├── iframe.vue               ← iframe 场景下的操作台
    └── config.json              ← 语言配置 {"language":"zh"}
```

**一句话**：这是整个软件的"手"，你所有点击都由它捕捉并翻译。

### 2.2 `ElectronJS/` —— 桌面软件的外壳与大脑

同样先看目录结构。

```text
ElectronJS/
├── main.js         (1876行)   ← 【Electron 主进程】创建窗口、WebSocket服务、调Selenium
├── server.js       (940行)    ← 本地 HTTP 文件服务（Express）
├── forge.config.js            ← 打包配置
└── src/
    ├── index.html / index.js  ← 主界面入口
    ├── js/vue.global.js       ← Vue3 运行时（直接引入，无构建）
    ├── taskGrid/              ← 【任务编辑区】
    │   ├── FlowChart.html     ← 英文流程图界面（83KB 单文件）
    │   ├── FlowChart_CN.html  ← 中文流程图界面
    │   ├── FlowChart.js       ← 流程图逻辑（节点增删、连线、保存）
    │   ├── logic.js           ← 流程图业务逻辑
    │   ├── taskList.html      ← 任务列表页
    │   ├── taskInfo.html      ← 任务信息（输入/输出参数表）
    │   ├── executeTask.html   ← 执行任务页
    │   └── test_pages/        ← 内置测试网页（学习匹配算法用！）
    └── locale/                ← 中英文语言包
```

**一句话**：这是"指挥中心"，负责画流程图、管任务文件、启动一切。

### 2.3 `ExecuteStage/` —— Python 执行引擎

它的目录结构如下。

```text
ExecuteStage/
├── easyspider_executestage.py  (2702行) ← 【总执行器】含 OCR，功能全
├── easyspider_executestage_single.py (1137行) ← 精简执行器（无重依赖）
├── myChrome.py                 ← 定制 Chrome/undetected-chromedriver
├── utils.py       (800行)      ← 工具函数（写CSV/Excel、去重、下载图片…）
├── constants.py                ← 枚举定义（GraphOption 等）
├── config.json                 ← 执行器配置
├── requirements.txt            ← Python 依赖清单
└── undetected_chromedriver_ES/ ← 反检测驱动源码（内嵌改造版）
```

**一句话**：这是"手脚"，真正打开浏览器、点按钮、抓数据。

### 2.4 `Examples/` —— 最好的教材

`Examples/*.json` 是官方任务，格式最标准。

其中 `Examples/Sample Tasks with Python/` 展示了**如何用 Python 调用任务**：

```python
# 大意：读取 json，交给执行器，拿到数据
```

🔬 想学"任务 JSON 到底怎么写"，直接读这里的文件比看文档快十倍。

### 2.5 `Docs/`、`scripts/`、`media/`

这三个文件夹相对简单，逐个说明。

- `Docs/`：论文《面向WEB应用的智能化服务封装系统设计与实现》+ 本讲义；
- `scripts/`：环境自检、打包测试脚本；
- `media/`：README 用的动图与图片。

---

## 3. 三进程通信全景

先看下面这张全景图。

```text
                ┌─────────────────────────────────────────┐
                │            ElectronJS/main.js            │
                │  ① WebSocket.Server(8084)  ② Selenium    │
                └───────┬──────────────────────────┬───────┘
                        │ ①                        │ ② 试运行
        WS 消息（JSON）  │                          │ (设计阶段点元素就能看到效果)
                        ▼                          ▼
   ┌──────────────────────────┐        ┌──────────────────────┐
   │  Extension/content.js    │        │  Chrome (被Selenium控) │
   │  发送：选中了什么元素      │        └──────────────────────┘
   │  接收：取消选中/试运行命令 │
   └──────────────────────────┘
                        │
                        │ ③ 正式执行：spawn 子进程
                        ▼
   ┌──────────────────────────────────────────┐
   │ easyspider_executestage.py               │
   │  读 tasks/xxx.json → Selenium 重放任务    │
   └──────────────────────────────────────────┘
```

三个进程之间传的消息，格式统一长这样（见 `messageInteraction.js`）：

```js
{
  "type": 3,           // 3 = 元素增加事件
  "from": 0,           // 0 = 浏览器 → 流程图
  "message": { "pipe": JSON.stringify(节点数据) }
}
```

关于端口，有一个必须记住的点。

💡 **易错点**：端口 8084 是**写死**的。

如果你想改端口，需要同时改 `Extension/.../messageInteraction.js` 和 `ElectronJS/main.js` 两处。

---

## 4. 为什么这样设计（架构思考）

看看每个设计选择背后的好处。

| 设计选择 | 好处 |
| --- | --- |
| 扩展只负责"点"，不负责"跑" | 借用真实浏览器环境，避免被反爬识别为脚本 |
| 任务存成 JSON | 可读、可版本管理、可被其他语言调用 |
| Electron 而非纯 Web | 能操作本地文件、启动子进程、调 Selenium |
| 执行器独立成 Python | 可脱离 GUI 单独跑，方便服务器端部署/定时任务 |
| graph 用邻接表（sequence） | 天然支持循环、条件分支等复杂控制流 |

---

## 5. 本篇小结

把全篇压缩成几行：

```text
Extension  = 手（拾取元素）
ElectronJS = 脑（画流程、管任务、发号施令）
ExecuteStage = 脚（真正跑起来）
WebSocket 8084 把它们连接起来
task.json 是它们共同的语言
```

---

返回目录：[README.md](README.md) ｜ 上一篇：[00.讲义导读与学习路线](00.讲义导读与学习路线.md) ｜ 下一篇：[02.数据流全链路：从选中元素到执行完成](02.数据流全链路.md)
