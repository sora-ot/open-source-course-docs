---
title: "24 · Electron"
description: "easyspider · 工程实践 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/24.ElectronJS详解.md"
originalUrl: "/originals/easyspider/chapter-24.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 24.ElectronJS：把网页变成桌面软件

第 14 篇讲扩展与流程图的消息。本篇先认识 Electron 的主进程、窗口和通信，再在第 16.2 节具体追踪：录制输入、点击时，主进程怎样通过 WebDriver 直接操作设计浏览器；第三部分继续讲单步调试，以及主进程怎样向插件发送 trial、notify 等消息。下一篇“调试功能详解”接着解释插件如何接收并呈现这些结果。

> EasySpider 看起来是一个装在 Windows/Mac 上的桌面软件，双击就能跑；但它的界面**其实是一个网页**。

> 让它"既是网页又能干桌面软件的活"的，就是 Electron。

> 这一篇先写一个和 EasySpider 完全无关的最小 Electron 便签本（主进程 + preload + 渲染进程 + IPC 全打通），
> 再把这个模型套到 EasySpider 真实的 `ElectronJS/` 上，逐行拆它的窗口管理、IPC 与三大服务端口。

**本篇结构**（和第 6 篇一样）：

```text
第一部分：先写一个极简 Electron 便签本，跟 EasySpider 完全无关，复制就能跑
第二部分：再看 EasySpider 的 ElectronJS/，包括窗口、通信和 WebDriver 模拟输入/点击
第三部分：Electron 如何处理调试请求并向浏览器插件发送消息
```

> 📌 **关于行号**：行号取自当前仓库版本；**对不上时以函数名/关键词搜索为准**。

---

---

## 第一部分：先写一个极简 Electron 便签本（与 EasySpider 无关）

### 1. 先看清问题

#### 1.1 场景

你想做一个"便签本"：打开窗口、输入文字、点"保存"，文字就写进硬盘上的一个文件。

用纯网页做？**做不到**——浏览器里的 JS 不能随便读写本地文件。
用 Python/Qt 做？能做，但界面要手写，很累。

Electron 的答案：**界面用网页写，脏活交给 Node.js**。

#### 1.2 输入和输出

| | |
|---|---|
| **输入** | 用户在窗口里打字、点按钮 |
| **输出** | 本地文件被写入/读取（网页本身做不到的事） |

#### 1.3 中间隔着一道墙

这道墙就是**进程隔离**：

```text
┌──────────────── 渲染进程 ────────────────┐   ┌──────── 主进程 ────────┐
│ 你的网页（HTML/CSS/JS）                   │   │ Node.js                │
│ 能：操作 DOM、发 Ajax、画界面              │   │ 能：读写文件、开子进程、 │
│ 不能：碰文件系统、开进程、关窗口           │   │   管窗口、系统对话框     │
└───────────────────────────────────────────┘   └────────────────────────┘
                    └──────── IPC 通道（消息）────────┘
```

界面世界与系统权限在两边，必须靠**消息**传递 —— 这就是 IPC。

---

### 2. 补一点最小背景知识

#### 2.1 Electron = Chromium + Node.js + 外壳

```text
Chromium  → 负责把 HTML/CSS/JS 画出来（渲染进程）
Node.js   → 负责文件系统、子进程、本地 socket（主进程）
外壳      → 负责窗口标题栏、菜单、托盘、打包成 exe / dmg / deb
```

VSCode、Slack、Discord、微信开发者工具都是 Electron 做的。

#### 2.2 两种进程对比

| | 主进程 Main | 渲染进程 Renderer |
|---|---|---|
| 入口 | `package.json` 的 `"main"` 字段（通常是 `main.js`） | 一个 HTML 页面 |
| 数量 | **恰好 1 个** | 每个窗口 1 个 |
| 能干什么 | 建窗口、读写文件、起子进程、系统 API、菜单 | 只能跑网页 |
| 崩溃后果 | 整个应用挂掉 | 只挂那一个窗口 |
| 类比 | 公司总部（有公章） | 各分公司前台（只能打电话请示） |

💡 **为什么要分开？** 主要是为了**安全**：万一网页里有恶意脚本，它也不能直接删你的硬盘。

#### 2.3 preload：唯一被允许"脚踏两条船"的脚本

它先于页面加载执行，**既看得见部分 Node/Electron API，又够得着渲染进程的 `window`**。
它的唯一职责通常是：把几个安全函数**挂到 `window` 上**（通过 `contextBridge`）。

```text
渲染进程的网页             preload.js                     主进程
   window.api.xxx()   →   contextBridge 暴露的函数   →   ipcRenderer.send/invoke
                                                              ↓ IPC 通道
                                                          ipcMain.handle/on
```

#### 2.4 IPC 的三种常用模式

| 模式 | 渲染进程 | 主进程 | 有没有返回值 |
|---|---|---|---|
| **请求-响应**（推荐） | `ipcRenderer.invoke(ch, arg)` | `ipcMain.handle(ch, h)` | ✅ 返回 Promise |
| **单向通知** | `ipcRenderer.send(ch, arg)` | `ipcMain.on(ch, h)` | ❌ 不返回 |
| **旧式回调** | `send` + `on` | `event.reply(ch2, data)` | 靠再发一条消息 |

---

### 3. 从零写一个最小可运行例子

#### 3.1 目录结构

```text
my-notes/
├── package.json       ← 声明入口是 main.js
├── main.js            ← 主进程：建窗口 + 处理 IPC + 读写文件
├── preload.js         ← 桥梁：把 4 个函数挂到 window.api
└── index.html         ← 渲染进程：界面（可以直接 <script> 写原生 JS）
```

> EasySpider 的结构和它**几乎一模一样**：`ElectronJS/main.js`、`ElectronJS/src/js/preload.js`、`ElectronJS/src/index.html`。

#### 3.2 package.json

```json
{
  "name": "my-notes",
  "version": "1.0.0",
  "main": "main.js",
  "scripts": { "start": "electron ." },
  "devDependencies": { "electron": "^27.1.3" }
}
```

#### 3.3 主进程 main.js（带完整中文注释）

```js
// ===== 主进程：整个应用只有一个，拥有"全部权限" =====
const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const fs = require("fs");                       // ← Node 的文件系统只有这里能用
const path = require("path");

let win = null;                                 // 窗口引用必须挂全局，否则会被 GC 回收导致闪退

// ① 建窗口
function createWindow() {
    win = new BrowserWindow({
        width: 700,
        height: 500,
        webPreferences: {
            // ★ preload 在页面加载【之前】执行，是唯一能合法使用 ipcRenderer 的地方
            preload: path.join(__dirname, "preload.js"),
            // contextIsolation 在 Electron 12+ 默认为 true，隔离了页面与 preload 的 JS 世界
            contextIsolation: true,
        },
    });
    win.loadFile("index.html");                 // 把本地 HTML 当作界面加载
}

// ② App 就绪后才能建窗口
app.whenReady().then(() => {
    registerIpc();                              // 先注册 IPC 监听，免得消息来了没人接
    createWindow();
});

// ③ 关闭非 macOS 平台的最后一个窗口 → 退出应用
app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
});

// ④ macOS 上点 Dock 图标、且没有窗口时 → 再建一个
app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ⑤ IPC 注册：所有"脏活"都在这里做
function registerIpc() {
    // 模式 A：invoke / handle —— 有返回值（Promise）
    ipcMain.handle("read-note", async () => {
        try {
            return { ok: true, text: fs.readFileSync(getNotePath(), "utf-8") };  // 读文件
        } catch (e) {
            return { ok: false, text: "" };     // 第一次运行文件不存在，返回空串即可
        }
    });

    // 模式 A：带参数的版本
    ipcMain.handle("save-note", async (event, text) => {
        fs.writeFileSync(getNotePath(), text);  // 写文件
        return { ok: true, length: text.length };
    });

    // 模式 B：send / on —— 只通知，不返回
    ipcMain.on("quit-app", () => {
        app.quit();                             // 退出也是主进程的权限
    });

    // 模式 C：主进程主动弹系统对话框（渲染进程弹不出原生对话框）
    ipcMain.handle("pick-file", async () => {
        const r = await dialog.showOpenDialog({ properties: ["openFile"] });
        return r.canceled ? "" : r.filePaths[0];
    });
}

// 放在用户数据目录里，避免和程序文件混在一起
function getNotePath() {
    return path.join(app.getPath("userData"), "note.txt");
}
```

#### 3.4 preload.js（桥梁，只有十几行）

```js
// ===== preload：跑在渲染进程里，但先于页面执行，且可使用 ipcRenderer =====
const { contextBridge, ipcRenderer } = require("electron");

// ★ contextBridge 是唯一安全地把东西挂到 window 上的方式
contextBridge.exposeInMainWorld("api", {
    readNote: () => ipcRenderer.invoke("read-note"),          // 对应 ipcMain.handle
    saveNote: (text) => ipcRenderer.invoke("save-note", text), // 带参数
    pickFile: () => ipcRenderer.invoke("pick-file"),
    quitApp: () => ipcRenderer.send("quit-app"),               // 对应 ipcMain.on，不等回包
});
```

🔬 **注意这里暴露的是"函数"而不是"`ipcRenderer` 对象本身"**。
如果把整个 `ipcRenderer` 暴露出去，页面就能收发任意频道，隔离等于白做。

#### 3.5 index.html（界面）

```html
<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>便签本</title></head>
<body style="font-family:sans-serif;padding:16px">
  <textarea id="t" style="width:100%;height:200px"></textarea><br>
  <button id="load">读取</button>
  <button id="save">保存</button>
  <button id="pick">选个文件</button>
  <button id="quit">退出</button>
  <p id="log" style="color:#666"></p>

  <script>
    // 页面上能用的只有 preload 挂上来的 window.api —— 看不到 require、看不到 ipcRenderer
    const { api } = window;
    const $ = (id) => document.getElementById(id);

    $("load").onclick = async () => {
      const r = await api.readNote();          // ← await 一个跨进程的 Promise
      $("t").value = r.text;
      $("log").textContent = r.ok ? "读取成功" : "还没有存档";
    };

    $("save").onclick = async () => {
      const r = await api.saveNote($("t").value);
      $("log").textContent = `已保存 ${r.length} 个字`;
    };

    $("pick").onclick = async () => {
      const p = await api.pickFile();          // ← 主进程弹原生对话框
      $("log").textContent = p ? `选中：${p}` : "取消了";
    };

    $("quit").onclick = () => api.quitApp();   // ← 单向通知，不等回包
  </script>
</body>
</html>
```

#### 3.6 跑起来

```bash
cd my-notes
npm install electron --save-dev
npm start
```

#### 3.7 一次"保存"的完整链路

```text
① 用户点按钮          网页 JS 调 api.saveNote(text)
② preload             ipcRenderer.invoke("save-note", text)
③ IPC 通道            跨越进程边界，序列化后送到主进程
④ 主进程              ipcMain.handle 的回调执行 fs.writeFileSync(...)
⑤ 返回                { ok: true, length: n } 沿原路回来
⑥ Promise resolve     await 拿到结果，更新界面文案
```

💡 **关键点**：第 ④ 步是唯一能动文件的地方，其余都只是在"传话"。

---

### 4. `contextBridge` 为什么非用不可

假设没有 `contextIsolation`，preload 里写 `window.saveNote = ...` 也能工作，但会发生这样的事：

```text
❌ 不隔离时：
    页面的第三方脚本 → 改掉 window.saveNote → 你调的函数变成别人的了
    页面的恶意脚本   → 直接 window.require("fs") → 硬盘任它写

✅ 隔离 + contextBridge：
    preload 与页面是【两个互不相通的 JS 世界】
    contextBridge 相当于在墙上开一个只能塞纸条的小窗：
        白名单里的函数才过墙，其余一律看不到
```

| 场景 | 直接挂 `window` | `contextBridge` |
|---|---|---|
| 页面能不能改掉暴露的函数 | 能（可劫持） | 不能（冻结、只读） |
| 页面能不能摸到 `require` | 能 | 不能 |
| 暴露粒度 | 整个模块 | 你挑的几个函数 |

> Electron 12 之后 `contextIsolation` 默认就是 `true`，EasySpider 也因此可以省略这个配置项（见 §9.2）。

---

### 5. 窗口管理的最小常识

三个必须知道的事件：

| 事件 | 什么时候触发 | 通常做什么 |
|---|---|---|
| `app.whenReady()` | Electron 初始化完成 | **此时才能建窗口** |
| `app.on("activate")` | macOS 点 Dock 图标 | 没窗口就重建一个 |
| `app.on("window-all-closed")` | 所有窗口都关了 | 非 macOS 就 `app.quit()` |

⚠️ **最常见的坑**：`BrowserWindow` 实例如果只存在函数局部变量里，函数结束就会被垃圾回收，窗口**闪一下就没了**。
所以一定要像 §3.3 那样挂在模块级的 `let win` 上。

---

### 6. 这个最小例子还缺什么

| 缺的东西 | 说明 | EasySpider 怎么补的 |
|---|---|---|
| **没有打包** | 只能 `npm start` 自己跑 | electron-forge 打成 exe / dmg（§17） |
| **preload 路径写死** | 相对路径换目录就坏 | 用 `path.join(__dirname, ...)`（ES 也是这么写的） |
| **没有多窗口管理** | 一个 `win` 变量只能管一个 | 用多个模块级变量：`mainWindow` / `flowchart_window` / `invoke_window`（§10） |
| **渲染进程没有 Node 能力** | 只能在主进程写文件 | ES 干脆把服务端/Node 服务也放主进程（§16） |
| **页面是本地 file://** | 想换皮肤得改打包内容 | ES 改成从本地 HTTP 服务加载页面（§9.3） |
| **没有跨窗口/跨端通信** | 只有 IPC | ES 额外开了 WebSocket 给浏览器扩展用（§15） |
| **数据目录写死** | macOS 打包后会失败 | `getDir()` 按平台切换（§18.2） |
| **没有自动更新、日志** | 排查问题困难 | ES 有 `check_update.js`、`config.debug` 日志重定向（§16.4） |

---

---

## 第二部分：EasySpider 是怎么做的

### 7. `ElectronJS/` 目录导览

EasySpider 的桌面端全部在这个文件夹里：

| 文件 / 目录 | 作用 |
|---|---|
| `main.js`（约 1877 行） | **主进程**：总指挥部，下文主角 |
| `src/js/preload.js` | **桥梁**：只暴露 4 个 IPC 函数 |
| `src/index.html` + `src/index.js` | **渲染进程**：首页（Vue3 写的语言/协议选择界面） |
| `src/taskGrid/` | 流程图编辑器画面（`FlowChart.html`、`logic.js`、`taskList.html` 等） |
| `server.js`（约 940 行） | Node/Express：本地文件服务 + 任务增删改查 API |
| `config.json` | 端口、用户数据目录、语言等配置 |
| `ws`（依赖） + `WebSocket.Server` | WebSocket 服务端，端口 **8084** |
| `forge.config.js` / `package_*.cmd` / `clean_and_release_*.cmd` | 打包脚本 |
| `start_direct.cmd` / `start_server.js` | 开发与纯服务启动方式 |

> 🔬 注意 `src/js/` 里除了 `preload.js` 还有 `jquery-3.4.1.min.js` 和 `vue.global.js`——
> 它们和 `preload.js` **毫无关系**，是给页面本身用的前端库。

---

### 8. 主进程职责地图

```text
ElectronJS/main.js 的六件事
① 创建主窗口            createWindow()                      199 行
② 起本地 HTTP 服务      task_server.start(webserver_port)   112 行（→ server.js）
③ 起 WebSocket 服务     new WebSocket.Server({port: 8084})  1414 行（接浏览器扩展）
④ 设计浏览器操作        selenium-webdriver 模拟输入、点击及单步试运行
⑤ 正式执行 Python        spawn(execute_path, parameters)     1163 行
⑥ 窗口管理 / IPC        handleOpenBrowser / handleOpenInvoke / ipcMain.on
```

对应依赖（`package.json`）：

| 依赖 | 用在哪 |
|---|---|
| `selenium-webdriver` | ④ 主进程直接驱动设计 Chrome：录制时即时输入/点击，以及节点试运行 |
| `ws` | ③ WebSocket 服务端 8084 |
| `express` + `cors` + `formidable` + `multer` + `http` | ② 本地 HTTP 服务与上传 |
| `xlsx` | 读写 Excel（任务参数的批量导入） |
| `node-window-manager` | 调整外部浏览器窗口位置 |
| `child_process`(`spawn`/`exec`/`execFile`) | ⑤ 启动 Python 执行器、查 Chrome 版本 |

---

### 9. 建窗口：`createWindow()`

真实代码在 `ElectronJS/main.js`（第 199-232 行）：

```js
// ElectronJS/main.js · 第 199 行起
function createWindow() {
    // Create the browser window.
    mainWindow = new BrowserWindow({
        width: 600,                                    // ① 固定尺寸的启动窗口
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, "src/js/preload.js"),   // ② ★ 唯一的桥梁
        },
        icon: iconPath,                                // ③ 窗口图标
        // frame: false, //取消window自带的关闭最小化等
        resizable: false,                              // ④ 主窗口禁止改尺寸
    });

    // and load the index.html of the app.
    // mainWindow.loadFile('src/index.html');          // ⑤ 注释掉的老写法
    mainWindow.loadURL(                                // ⑥ ★ 改为从本地 HTTP 服务加载
        server_address +
        "/index.html?user_data_folder=" + config.user_data_folder +
        "&copyright=" + config.copyright +
        "&lang=" + config.lang,
        {extraHeaders: "pragma: no-cache\n"}           // ⑦ 绕过缓存，改了页面立刻生效
    );
    // 隐藏菜单栏
    const {Menu} = require("electron");
    Menu.setApplicationMenu(null);                     // ⑧ 不显示默认菜单
    mainWindow.on("close", function (e) {              // ⑨ 非 macOS：关主窗口 = 退出
        if (process.platform !== "darwin") {
            app.quit();
        }
    });
    //调试模式
    // mainWindow.webContents.openDevTools();          // ⑩ 想调试就打开这行
}
```

#### 9.1 两个值得注意的点

**① `mainWindow` 是模块级变量**

主进程顶部（第 171 行）就有 `let mainWindow = null;`，和第 172-183 行的
`flowchart_window`、`invoke_window`、`socket_window` 等一起构成**多窗口管理**（详见 §10）。

> 这正是 §6 表格里"最常见坑"的正确答案：EasySpider 的 4 个窗口引用全部挂在模块级，不会被 GC 掉。

**② macOS 上不退出**

第 ⑨ 段的平台判断：macOS 习惯是"关窗口 ≠ 退程序"，所以只在非 darwin 平台 `app.quit()`。
同文件第 1865 行的 `window-all-closed` 也做了同样的判断。

#### 9.2 为什么没写 `contextIsolation`

因为它从 Electron 12 起**默认就是 `true`**（本项目用的是 `electron ^27.1.3`，见 `package.json` 第 30 行）。
不写 = 用默认值 = 已隔离，preload 必须用 `contextBridge` 才能把东西给页面。

#### 9.3 为什么用 `loadURL` 而不是 `loadFile`

被注释掉的旧写法是 `mainWindow.loadFile('src/index.html')`。改成 `loadURL` 的好处很实在：

| | `loadFile("src/index.html")` | `loadURL(server_address + "/index.html?...")` |
|---|---|---|
| 协议 | `file://` | `http://localhost:8074` |
| 传参 | 只能通过 IPC 或全局变量 | **可以直接用 URL query**（见代码里的 `lang`/`copyright`） |
| 改页面 | 必须重新打包 | 改完刷新即可、且带了 `pragma: no-cache` |
| 多个窗口 | 各自一个 file 路径 | 同一套服务给所有窗口/调试用 |

> 代价是必须先把 HTTP 服务跑起来（§16.1），而且如果 8074 端口被占，界面就打不开——这是个真实的用户痛点（§16.3）。

---

### 10. 桥梁：`src/js/preload.js` 全部内容

这是 EasySpider 的 preload，**只有 15 行**：

```js
// ElectronJS/src/js/preload.js（全文）
/**
 * The preload script runs before. It has access to web APIs
 * as well as Electron's renderer process modules and some
 * polyfilled Node.js functions.
 *
 * https://www.electronjs.org/docs/latest/tutorial/sandbox
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {   // ★ 挂到 window.electronAPI
    startDesign: (lang="en", user_data_folder = '', mobile=false) =>
        ipcRenderer.send('start-design', lang, user_data_folder, mobile),      // 单向
    startInvoke: (lang="en") =>
        ipcRenderer.send('start-invoke', lang),                                // 单向
    acceptAgreement: () =>
        ipcRenderer.send('accept-agreement'),                                  // 单向
    changeLang: (lang="en") =>
        ipcRenderer.send('change-lang', lang)                                  // 单向
})
```

🔬 **观察**：4 个 API **全是 `send`**（单向通知），没有一个用 `invoke`。
也就是说 EasySpider 的 IPC **全部是"发件不回执"**——我们第一部分讲的"请求-响应"模式在这里一条都没用上。

为什么？因为这 4 件事都是**命令**（去开窗、去写配置），不需要返回值；
界面上的反馈（比如语言切换后的界面切换）由渲染进程自己处理即可（见 §11）。

---

### 11. 渲染进程怎么用：`src/index.js`

页面这边用 Vue 3 写的（`src/index.html` 第 261 行用 `<script type="module" src="index.js">` 引入）：

```js
// ElectronJS/src/index.js（核心片段）
import enLocale from './locale/en/strings.js';
import zhLocale from './locale/zh/strings.js';

function getUrlParam(name) {                       // 从 URL query 里取值（§9.3 的收益）
    var reg = new RegExp("(^|&)" + name + "=([^&]*)(&|$)");
    var r = window.location.search.substr(1).match(reg);
    if (r != null) return unescape(r[2]);
    return "";
}

let app = Vue.createApp({
    data() {
        return {
            lang: '-',
            user_data_folder: getUrlParam("user_data_folder"),   // ← 主进程塞进 URL 的
            copyright: 0,
            step: 0,
        }
    },
    mounted() {
        this.copyright = parseInt(getUrlParam("copyright"));
        if (this.copyright == 0) { this.step = -1; }             // 没同意过协议 → 先弹协议
        this.lang = getUrlParam("lang");
        /* …还顺手去 GitHub Release API 查一次最新版本号… */
    },
    methods: {
        changeLang(lang = 'zh') {
            this.lang = lang;                                    // ① 先改自己的界面
            window.electronAPI.changeLang(lang);                 // ② 再通知主进程落盘
        },
        acceptAgreement() {
            this.step = 0;
            window.electronAPI.acceptAgreement();                // ← preload 暴露的那 4 个之一
        },
        startDesign(lang, with_data = false, mobile=false) {
            if (with_data) {
                if (this.user_data_folder == null || this.user_data_folder == "") {
                    alert("请指定用户信息目录");                  // 参数校验在渲染进程做
                    return;
                }
                window.electronAPI.startDesign(lang, this.user_data_folder, mobile);
            } else {
                window.electronAPI.startDesign(lang, '', mobile);
            }
        },
        startInvoke(lang) {
            window.electronAPI.startInvoke(lang);
        }
    }
}).mount('#app');
```

💡 **分工很清楚**：渲染进程管"界面该怎么变"，主进程管"配置要落盘、窗口要打开"。
两边都不越界——这正是 §1.3 那张隔离图的落地。

---

### 12. IPC 四条消息全表

主进程这边的注册都在 `app.whenReady()` 里（`ElectronJS/main.js` 第 1771-1796 行）：

```js
// ElectronJS/main.js · 第 1771 行起
app.whenReady().then(() => {
    session.defaultSession.webRequest.onBeforeSendHeaders((details, callback) => {
        details.requestHeaders["Accept-Language"] = "zh";    // ① 统一注入请求头
        callback({cancel: false, requestHeaders: details.requestHeaders});
    });
    ipcMain.on("start-design", handleOpenBrowser);           // ② 打开设计器
    ipcMain.on("start-invoke", handleOpenInvoke);            // ③ 打开执行列表
    ipcMain.on("accept-agreement", function (event, arg) {   // ④ 同意协议 → 写 config.json
        config.copyright = 1;
        fs.writeFileSync(path.join(task_server.getDir(), "config.json"), JSON.stringify(config));
        config = JSON.parse(fs.readFileSync(path.join(task_server.getDir(), "config.json")));
    });
    ipcMain.on("change-lang", function (event, arg) {        // ⑤ 切换语言 → 写 config.json
        config.lang = arg;
        fs.writeFileSync(path.join(task_server.getDir(), "config.json"), JSON.stringify(config));
        config = JSON.parse(fs.readFileSync(path.join(task_server.getDir(), "config.json")));
    });
    createWindow();                                          // ⑥ 一切就绪后才建窗口
    app.on("activate", function () {
        if (BrowserWindow.getAllWindows().length === 0) { createWindow(); }
    });
    /* …macOS 上还会用 execFile 检查 Chrome 与 ChromeDriver 版本是否匹配（第 1805-1858 行）… */
});
```

| 频道 | preload 暴露名 | 主进程接收函数 | 干什么 |
|---|---|---|---|
| `start-design` | `startDesign(lang, folder, mobile)` | `handleOpenBrowser`（1694 行） | 起浏览器 + 打开流程图设计窗口 |
| `start-invoke` | `startInvoke(lang)` | `handleOpenInvoke`（1743 行） | 打开"任务执行"列表窗口 |
| `accept-agreement` | `acceptAgreement()` | 匿名函数（1778 行） | 把 `copyright=1` 写进 config.json |
| `change-lang` | `changeLang(lang)` | 匿名函数（1787 行） | 把 `lang` 写进 config.json |

```text
完整链路（以"点击开始设计"为例）：
  index.js  methods.startDesign()
      → window.electronAPI.startDesign(lang, folder, mobile)   [preload]
      → ipcRenderer.send("start-design", ...)                  [IPC]
      → ipcMain.on("start-design", handleOpenBrowser)          [主进程]
      → runBrowser(...) + 新建 flowchart_window 并 loadURL(...)
```

🔬 **一个细节**：两个写配置的处理函数写完都**重新读了一遍** config.json（第 1785、1794 行），
保证内存里的 `config` 变量和磁盘一致——这是并发写入时很实用的习惯。

---

### 13. 窗口管理一：打开设计器 `handleOpenBrowser()`

`ElectronJS/main.js` 第 1694-1741 行：

```js
// ElectronJS/main.js · 第 1694 行起
function handleOpenBrowser(event, lang = "en", user_data_folder = "", mobile = false) {
    const webContents = event.sender;                       // ① 谁发的消息
    const win = BrowserWindow.fromWebContents(webContents); // ② 反查它属于哪个窗口
    runBrowser(lang, user_data_folder, mobile);             // ③ 用 selenium 起真的 Chrome

    let size = screen.getPrimaryDisplay().workAreaSize;     // ④ 拿主显示器可用区
    let width = parseInt(size.width);
    let height = parseInt(size.height * 0.5);               //    设计器占半屏高
    flowchart_window = new BrowserWindow({
        x: 0, y: 0, width: width, height: height,
        icon: iconPath,
        maximizable: true,
        resizable: true,
    });                                                     // ⑤ ★ 注意：这里没有 preload

    let url = "";
    let id = -1;
    if (lang == "en") {
        url = server_address + `/taskGrid/FlowChart.html?id=${id}&wsport=${websocket_port}`
            + "&backEndAddressServiceWrapper=" + server_address + "&mobile=" + mobile.toString();
    } else if (lang == "zh") {
        url = server_address + `/taskGrid/FlowChart_CN.html?id=${id}&wsport=${websocket_port}`
            + "&backEndAddressServiceWrapper=" + server_address + "&mobile=" + mobile.toString();
    }
    flowchart_window.loadURL(url, {extraHeaders: "pragma: no-cache\n"});   // ⑥ 还是本地 HTTP
    if (process.platform != "darwin") {
        flowchart_window.hide();                            // ⑦ 先藏着，等参数准备好再显示
    }
    flowchart_window.on("close", function (event) {
        mainWindow.show();                                  // ⑧ 关掉时把首页叫回来
        driver.quit();                                      //    同时关掉驱动的浏览器
    });
}
```

#### 13.1 关键：这个窗口**没有 preload**

对比 §9 的主窗口，这里 `new BrowserWindow` 里**没有 `webPreferences`**，于是：

- 页面**拿不到 `window.electronAPI`**；
- 它与主进程通信**不走 IPC**，而是页面自己连 **WebSocket 8084**（URL 里那个 `wsport=${websocket_port}` 就是给它的）；
- 这些页面（`taskGrid/*`）由本地 HTTP 服务提供，任何人用浏览器访问同一个地址也能得到同样的页面。

> 💡 **这是一个很有意思的设计选择**：只有"首页"这个受信任的页面吃 IPC 通道，
> 流程图界面干脆降级用 WebSocket——客观上减小了 IPC 的攻击面（尽管它是本地服务）。

#### 13.2 窗口关系图

```text
mainWindow（首页，有 preload，走 IPC）
    │  点"开始设计" → start-design
    ↓
flowchart_window（流程图设计器，无 preload，走 WS 8084）
    ↑                          ↓ beginInvoke(msg.type==1)
    │ 关闭时 mainWindow.show() │  mainWindow.hide() + flowchart_window.show()
    │                          ↑
    └─── invoke_window  ←──────┘（taskList.html，也是无 preload）
```

---

### 14. 窗口管理二：打开执行列表 `handleOpenInvoke()`

`ElectronJS/main.js` 第 1743-1766 行：

```js
// ElectronJS/main.js · 第 1743 行起
function handleOpenInvoke(event, lang = "en") {
    invoke_window = new BrowserWindow({icon: iconPath});    // ① 也是没有 preload
    let url = "";
    language = lang;                                        // ② 记住语言，后面提示语要用
    if (lang == "en") {
        url = server_address + `/taskGrid/taskList.html?type=1&wsport=${websocket_port}`
            + "&backEndAddressServiceWrapper=" + server_address;
    } else if (lang == "zh") {
        url = server_address + `/taskGrid/taskList.html?type=1&wsport=${websocket_port}`
            + "&backEndAddressServiceWrapper=" + server_address + "&lang=zh";
    }
    invoke_window.loadURL(url, {extraHeaders: "pragma: no-cache\n"});
    invoke_window.maximize();                               // ③ 最大化
    mainWindow.hide();                                      // ④ 把首页藏起来
    invoke_window.on("close", function (event) {
        mainWindow.show();                                  // ⑤ 关掉时再把首页叫回来
    });
}
```

💡 **窗口管理的最小套路**就是这三步：`show()` / `hide()` 配合 `close` 事件互相叫回来。
EasySpider 一共有 3 个窗口变量：`mainWindow`、`flowchart_window`、`invoke_window`（第 171-183 行）。

---

### 15. 三大服务与端口

EasySpider 运行时会开**不止一个**服务，这是排查问题时最重要的信息：

| 端口 | 服务 | 谁起的 | 谁连它 | 用途 |
|---|---|---|---|---|
| **8074** | Node/Express 本地 HTTP 服务 | `task_server.start(config.webserver_port)`（main.js 第 112 行） | Electron 自己的窗口、浏览器 | 提供页面、任务的增删改查 API |
| **8075** | Express 文件上传服务 | `fileServer.listen(8075, "127.0.0.1")`（server.js 第 133 行） | 本地页面 | Excel/文件上传（`/excelUpload`） |
| **8084** | WebSocket 服务端 | `new WebSocket.Server({port: websocket_port})`（main.js 第 1414 行） | 浏览器扩展、流程图页面 | 实时双向通信 |

配置来源（`ElectronJS/config.json`）：

```json
{
  "webserver_address": "http://localhost",
  "webserver_port": 8074,
  "user_data_folder": "./user_data",
  "debug": false,
  "copyright": 1,
  "sys_version": "x64",
  "mysql_config_path": "./mysql_config.json",
  "lang": "zh"
}
```

相关的三行真实代码：

```js
// ElectronJS/main.js · 第 111-115 行
if(config.webserver_address.includes("localhost") || config.webserver_address.includes("127.0.0.1")) {
    task_server.start(config.webserver_port); //start local server
}
let server_address = `${config.webserver_address}:${config.webserver_port}`;
const websocket_port = 8084; //目前只支持8084端口，写死，因为扩展里面写死了
```

⚠️ **注意那行注释**：8084 是**硬编码**的（"因为扩展里面写死了"），改端口会让扩展连不上。
而 8074 是可配的——但 UI 加载地址也依赖它。

💡 **另一个细节**（安全性）：server.js 第 99-107 行把 CORS 限制在本地来源：

```js
// ElectronJS/server.js · 第 99 行起
const LOCAL_ORIGIN_RE = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i;
fileServer.use(cors({
  origin: function (origin, callback) {
    if (!origin) return callback(null, true);                 // 同源/非浏览器请求放行
    if (LOCAL_ORIGIN_RE.test(origin)) return callback(null, true);
    return callback(new Error("Origin not allowed"));         // 其他来源拒绝
  },
}));
```

> 这是为了防止**恶意网页驱动你本机上的这个管理接口**（CSRF）。做本地服务时这是必须的一条。

---

### 16. 另外三件只有主进程能干的事

#### 16.1 起本地 HTTP 服务

`main.js` 第 27 行就把它 require 进来了，102-112 行读到配置后立刻启动（见 §15）。
`server.js` 里还会先确保几个目录存在：

```js
// ElectronJS/server.js · 第 54 行起
if (!fs.existsSync(path.join(getDir(), "tasks")))
    fs.mkdirSync(path.join(getDir(), "tasks"));                    // 任务目录
if (!fs.existsSync(path.join(getDir(), "execution_instances")))
    fs.mkdirSync(path.join(getDir(), "execution_instances"));      // 执行实例（日志）目录
if (!fs.existsSync(path.join(getDir(), "config.json")))
    fs.writeFileSync(path.join(getDir(), "config.json"), JSON.stringify({...}));
```

<a id="electron-browser-actions"></a>

#### 16.2 Electron 主进程也直接操作浏览器：模拟输入与点击

**Electron 主进程不仅转发消息，也直接执行设计阶段的浏览器操作。** 具体实现是 main.js 在 Node 环境中使用 selenium-webdriver，持有 driver，通过它定位网页元素、发送按键、点击、移动鼠标和执行网页脚本；不必先启动 Python 正式执行器。

```js
// ElectronJS/main.js 的依赖
const { Builder, By, Key, until, Select,
        StaleElementReferenceException } = require("selenium-webdriver");
const chrome = require("selenium-webdriver/chrome");
```

下面用同一个案例走完：设计 Chrome 已经打开房源页，原图只有“打开网页”；用户在扩展中选择地区输入框，输入“单间”，再选择“搜索”按钮并发出点击操作。XPath 和示例值为教学假设。

##### 16.2.1 哪个对象操作哪个窗口

| 对象 | 在本例中的职责 |
| --- | --- |
| Electron 的 BrowserWindow | 显示主界面、流程图设计器、执行列表等软件窗口 |
| main.js 中的 driver | 通过 WebDriver 操作 runBrowser 启动的设计 Chrome |
| 设计 Chrome 内的扩展 | 选择网页元素，生成 XPath、操作消息和预览界面 |
| Python 执行器 | 正式运行保存后的任务，按 graph 递归执行操作 |

runBrowser 的关键创建代码如下，省去浏览器选项、扩展安装和页面初始化：

```js
const serviceBuilder = new ServiceBuilder(driverPath);
let options = new chrome.Options();
options.setChromeBinaryPath(chromeBinaryPath);
driver = new Builder()
    .forBrowser("chrome")
    .setChromeOptions(options)
    .setChromeService(serviceBuilder)
    .build();
```

之后处理操作消息时，用的就是这个主进程级 driver。这里“Electron 操作浏览器”的具体含义，是 Electron 主进程里的 Node 代码调用 WebDriver 操作设计 Chrome。

##### 16.2.2 模拟输入：一项用户操作，发送两种消息

**消息案例。** 用户选择 `//input[@id='keyword']`，在扩展操作台中输入“单间”。messageInteraction.js 的 input(value,batch=false) 会先发送操作记录，再发送键盘请求。代入本例，可以写成以下两个信封；变量名用于教学，字段与发送逻辑对应：

```js
const operation = {
  type: "inputText",
  history: 1,
  tabIndex: -1,
  iframe: false,
  xpath: "//input[@id='keyword']",
  allXPaths: ["//input[@id='keyword']"],
  value: "单间",
  useLoop: false,
  loopType: 3
};
const recordMessage = {
  type: 3,
  from: 0,
  message: {pipe: JSON.stringify(operation)}
};
const keyboardMessage = {
  type: 2,
  message: {
    keyboardStr: "单间",
    xpath: "//input[@id='keyword']",
    iframe: false,
    id: 7
  }
};
```

发送端 input 函数中的实际发送顺序为：

```js
let message_action = {
    type: 3,
    from: 0,
    message: {"pipe": JSON.stringify(message)}
};
global.ws.send(JSON.stringify(message_action));
let message_keyboard = {
    type: 2,
    message: {"keyboardStr": value, "xpath": message.xpath,
              "iframe": global.iframe, "id": global.id}
};
global.ws.send(JSON.stringify(message_keyboard));
```

**对应主进程代码。** WebSocket 收到消息后，除连接、切换标签页等专门分支外，进入 beginInvoke(msg,ws)。它对外层 type=2 执行：

```js
} else if (msg.type == 2) {
    let keyInfo = msg.message.keyboardStr;
    let enter = false;
    if (/<enter>/i.test(keyInfo)) {
        keyInfo = keyInfo.replace(/<enter>/gi, "");
        enter = true;
    }
    let element = await findElementAcrossAllWindows(
        msg,
        (notifyBrowser = true),
        (scrollIntoView = false)
    );
    await element.sendKeys(Key.HOME, Key.chord(Key.SHIFT, Key.END), keyInfo);
    if (enter) {
        await element.sendKeys(Key.ENTER);
    }
}
```

这里通过 WebDriver 发送 Home、Shift+End 和文本，最后按需要发送 Enter。对本例普通单行输入框，可以把原值替换为“单间”；这段代码没有调用 element.clear，也不能一概描述成对任意多行文本框全选全部内容。

**处理后的案例。** 两条消息的结果分别是：

| 收到的消息 | 执行者与动作 | 本例可见结果 |
| --- | --- | --- |
| type=3，内层 inputText | 主进程转给流程图；logic.js 调 addElement(4,msg) | nodeList[2] 成为输入节点，保存 value="单间"；root.sequence=[1,2] |
| type=2 | 主进程定位输入框，执行 sendKeys | 当前设计网页输入框实际显示“单间” |

**记录输入节点与当前网页真的输入文字，是两条不同消息完成的。** 发送端先发记录消息，不等于已经等到流程图确认新增成功才开始输入；源码没有在两者之间建立这种确认协议。

若另一次输入的 keyboardStr 为 `"海淀<enter>"`，主进程会移除标记，输入海淀后再发送一次 Enter；源码对标记不区分大小写。批量输入同样会发送键盘消息，但这里不会据此递归执行整个文本循环；正式的多轮输入仍由任务执行器完成。

##### 16.2.3 模拟点击：转给流程图之后，主进程还会点网页

**消息案例。** 在上一步输入之后，用户在扩展里选择搜索按钮，sendSingleClick 发出的内层消息可以是：

```json
{
  "type": "singleClick",
  "id": 7,
  "history": 1,
  "tabIndex": -1,
  "useLoop": false,
  "iframe": false,
  "content": "搜索",
  "xpath": "//button[@id='search']",
  "allXPaths": ["//button[@id='search']"]
}
```

它仍装在 `{type:3, from:0, message:{pipe:JSON.stringify(操作对象)}}` 中发送。

**对应主进程代码。** beginInvoke 的 type=3 分支如下，省略日志；核心执行语句保留原写法：

```js
} else if (msg.type == 3) {
    try {
        if (msg.from == 0) {
            socket_flowchart.send(msg.message.pipe);
            let message = JSON.parse(msg.message.pipe);
            let type = message.type;
            if (type.indexOf("Click") >= 0 || type.indexOf("Move") >= 0) {
                let element = await findElementAcrossAllWindows(
                    message,
                    (notifyBrowser = true),
                    (scrollIntoView = false)
                );
                if (type.indexOf("Click") >= 0) {
                    await click_element(element, type);
                } else if (type.indexOf("Move") >= 0) {
                    await driver.actions().move({origin: element}).perform();
                }
            }
        } else {
            send_message_to_browser(msg.message.pipe);
        }
    } catch (e) {
        console.log(e);
    }
}
```

singleClick 包含大小写匹配的字符串 Click，因此进入点击分支。代码先发送给流程图，然后在主进程中定位并点击；不会先等待流程图回传完成确认。mouseMove 等包含 Move 的消息则走 WebDriver 鼠标移动分支。

**处理后的案例。** 流程图接到 singleClick，新建点击 3，root.sequence 从 [1,2] 变成 [1,2,3]；主进程同时按这条分支操作网页中的搜索按钮，网页进入搜索后的状态。完整正常路径为：

```text
扩展输入“单间”
  ├─ type=3 / inputText → 流程图增加输入节点 2
  └─ type=2            → Electron 的 driver 向网页输入“单间”

扩展发出点击搜索
  └─ type=3 / singleClick
       ├─ 转给流程图   → 增加点击节点 3
       └─ 主进程执行   → driver 找到网页按钮，再 click_element
```

这里假设各步骤正常完成，再由用户发起下一步。它不是一个等待流程图和浏览器两端共同提交的事务；源码定位或转发失败时，也不会自动撤销另一端已有的记录。

##### 16.2.4 click_element 具体怎样点击

main.js 中这个函数既供录制时的即时点击调用，也供部分节点试运行调用。去掉注释后，其实际处理为：

```js
async function click_element(element, type = "click") {
    try {
        if (type == "loopClickEvery") {
            if (process.platform === "darwin") {
                await driver.actions()
                    .keyDown(Key.COMMAND).click(element).keyUp(Key.COMMAND).perform();
            } else {
                await driver.actions()
                    .keyDown(Key.CONTROL).click(element).keyUp(Key.CONTROL).perform();
            }
        } else if (type.includes("point(")) {
            let point = type.substring(6, type.length - 1).split(",");
            let x = parseInt(point[0]);
            let y = parseInt(point[1]);
            let script = `document.elementFromPoint(${x}, ${y}).click();`;
            await driver.executeScript(script);
        } else if (type == "double") {
            await driver.actions().doubleClick(element).perform();
        } else {
            await element.click();
        }
    } catch (e) {
        console.log(e);
        await driver.executeScript("arguments[0].click();", element);
    }
}
```

| 传入的 type | 实际动作 | 本例或用途 |
| --- | --- | --- |
| singleClick 或默认 click | element.click() | 点击搜索按钮一次 |
| loopClickEvery | macOS 使用 Command+点击，其他平台使用 Control+点击 | 尝试以浏览器快捷键方式打开列表链接 |
| double | WebDriver actions.doubleClick | 节点试运行中的双击方式 |
| point(x,y) | 执行 document.elementFromPoint(x,y).click() | 节点试运行中的网页坐标点击 |
| 上述路径抛出异常 | executeScript 调 arguments[0].click() | JavaScript 点击回退 |

注意，录制时收到 loopClickEvery，type=3 分支只找一次目标、调用一次 click_element；固定路径列表也先取 pathList[0] 用来定位。**消息名包含“循环”，不等于主进程在这一刻遍历全部元素。** 循环结构先记录进图里，完整遍历留给正式任务执行。

##### 16.2.5 多个标签页、iframe 时，输入和点击怎样找到目标

输入与点击都会经过 findElementAcrossAllWindows。主要输入字段为：

| 字段 | 普通键盘消息 | 录制点击的内层消息 |
| --- | --- | --- |
| 标签页标识 | msg.message.id | message.id |
| 元素路径 | msg.message.xpath | message.xpath；固定列表时可取 pathList[0] |
| iframe 标记 | msg.message.iframe | message.iframe |

id=7 是示例浏览器连接标识，主进程用 handle_pairs[7] 找对应 WebDriver 窗口句柄；它不是 nodeList 的下标，也不是 DOM 元素 id。这个映射由扩展连接注册时建立。

辅助函数优先尝试消息对应的窗口、当前窗口，再尝试其他窗口；每次由 findElement 切回顶层文档，并根据 iframe 标记决定直接定位，还是递归进入 iframe 查找。录制输入和点击调用时，通知参数为 true，自动滚动参数为 false。定位成功后，返回的 element 才能用于 sendKeys、click 或 actions。

##### 16.2.6 与“节点试运行”和“Python 正式执行”分开看

| 场景 | 消息或入口 | 实际做浏览器动作的是谁 |
| --- | --- | --- |
| 扩展输入文字时的即时反馈 | 外层 type=2 | Electron 主进程定位后调用 element.sendKeys |
| 扩展录制点击、鼠标移动 | 外层 type=3、from=0，内层类型含 Click/Move | 先转发记录，再由主进程 WebDriver 操作设计浏览器 |
| 在流程图中单步试运行输入或点击 | 外层 type=4、内层 message.type=1 | 主进程解释节点参数，仍调用 WebDriver |
| 正式运行保存后的完整任务 | 生成执行实例，再启动执行器 | Python 按 graph 组织循环、条件、输入、点击与提取 |

在 beginInvoke 的 type=4 试运行分支，option=2/7 会定位节点指定的元素，并调用 click_element 或鼠标移动；option=4 则读取 parameters.value，处理循环上下文、前后脚本等配置，再调用 sendKeys。本篇第三部分接着讲这类调试请求和结果通知；第 25 讲继续看插件怎样标记、显示反馈。

源码对应：[main.js](/source/?file=5b1dab0d6ae24484fc.js) 的 runBrowser、beginInvoke、findElementAcrossAllWindows、click_element；发送端为 [messageInteraction.js](/source/?file=1a2b7d0e84fb34fe83.js) 的 input、sendSingleClick、sendMouseMove。第 21 讲侧重消息怎样改图，本节补上同一用户操作怎样让当前网页真的发生输入与点击。

#### 16.3 正式执行：起 Python 子进程

`ElectronJS/main.js` 第 1157-1182 行：

```js
let spawn = require("child_process").spawn;
let execution_started = false;
if (msg.message.execute_type == 1 && msg.message.id != -1) {
    if (process.platform === "darwin" && !fs.existsSync(execute_path)) {
        console.error("macOS execution stage is missing from the app bundle:", execute_path);
    } else {
        const child_process = spawn(execute_path, parameters, {
            cwd: task_server.getDir(),                 // ① 工作目录 = 数据目录（不是 app 目录）
            env: {
                ...process.env,
                PYTHONUNBUFFERED: "1",                 // ② 日志不缓冲，才能实时看到
                PYTHONUTF8: "1",
                EASYSPIDER_DATA_DIR: task_server.getDir(),       // ③ 告诉 Python 数据在哪
                EASYSPIDER_APP_RESOURCES: __dirname,
            },
        });
        execution_started = true;
        child_process.on("error", (error) => console.error("Failed to start execution stage:", error));
        child_process.stdout.on("data", function (data) {
            console.log(data.toString());              // ④ Python 的输出实时打到 Electron 日志
        });
    }
}
```

💡 **`cwd` 与环境变量是关键细节**：把数据目录通过 `cwd` + `EASYSPIDER_DATA_DIR` 传给子进程，
Python 端就不需要猜自己在哪（这与 §18.2 的 macOS 迁移问题是一回事）。

#### 16.4 调试开关

```js
// ElectronJS/main.js · 第 97-108 行
if (config.debug) {
    let logPath = "info.log";
    let logFile = fs.createWriteStream(logPath, {flags: "a"});
    console.log = function () {                      // ← 把 console.log 重定向到文件
        logFile.write(util.format.apply(null, arguments) + "\n");
        process.stdout.write(util.format.apply(null, arguments) + "\n");
    };
    console.error = function () { /* …同理… */ };
}
```

把 `config.json` 里的 `"debug"` 改成 `true`，运行时就会在程序目录生成 `info.log`。

---

### 17. 打包：从源码到 exe

`package.json` 的 scripts：

```json
{
"scripts": {
    "start_direct": "cross-env NODE_ENV=development electron .",
    "change_version": "node change_version.js",
    "start": "electron-forge start",
    "package": "electron-forge package",
    "make": "electron-forge make"
}
}
```

| 命令 | 作用 |
|---|---|
| `npm start`（`electron-forge start`） | 开发运行 |
| `npm run package` | 产出可直接运行的程序目录 |
| `npm run make` | 产出安装包：Windows 用 squirrel，macOS 用 zip，Linux 用 deb/rpm |

对应 makers 在 `package.json` 的 `config.forge.makers`（第 50-69 行）：

```json
[
{ "name": "@electron-forge/maker-squirrel", "config": { "name": "EasySpider" } },
{ "name": "@electron-forge/maker-zip", "platforms": ["darwin"] },
{ "name": "@electron-forge/maker-deb" },
{ "name": "@electron-forge/maker-rpm" }
]
```

仓库里还有 `package_win64.cmd`、`clean_and_release_win64.cmd` 等脚本做清理与发布。

💡 **打包后用户不需要装浏览器或 Python**——Chromium 和 Python 执行器都跟着打进去了。

---

### 18. 两个真实世界的问题

#### 18.1 端口被占用

因为 8074（还有 8075、8084）是固定端口，**另一个实例或其他软件占了，界面就打不开**。

```text
现象：双击 EasySpider 没反应 / 白屏 / 打开的是别人的服务
排查：netstat -ano | findstr 8074   然后看是谁占用
注意：8084 因为扩展里写死了，不能改（main.js 第 115 行的注释）
```

#### 18.2 打包后数据写到哪：`getDir()`

`ElectronJS/server.js` 第 35-44 行：

```js
function getDir() {
  // On macOS, never use the packaged app's __dirname for mutable data.
  // Gatekeeper may launch the app through App Translocation, where that path
  // points into a temporary private directory. …
  if (app.isPackaged && process.platform === "darwin") return app.getPath("userData");
  if (app.isPackaged) return path.resolve(process.resourcesPath, "../..");
  return __dirname;
}
```

| 情况 | 返回 |
|---|---|
| 未打包（开发） | `__dirname`（即 `ElectronJS/` 本身） |
| 已打包 · Windows/Linux | `process.resourcesPath` 的上两级（**便携版目录**，方便 U 盘携带） |
| 已打包 · macOS | `app.getPath("userData")` |

💡 **为什么 macOS 要特殊处理？**
macOS 的 Gatekeeper 会对没签名/被隔离的应用启用 **App Translocation**：
把应用放到一个随机的只读临时目录执行，此时 `__dirname`/`resourcesPath` 指到临时路径，写数据会失败甚至丢失。
所以用 Electron 提供的稳定 `userData` 目录。

> 这正是跨平台开发里很典型的一个坑：同一份代码，Windows 上"便携目录"是可爱的，macOS 上却是陷阱。

---

### 19. 设计权衡

#### 19.1 为什么界面从 HTTP 加载而不是 `file://`

已在 §9.3 对比。代价是**必须先起服务**；该写法还支持用 URL query 传参，开发调试更省事。

#### 19.2 为什么 IPC 全用单向 `send`

因为这 4 条消息都是命令型操作，没有返回值需求；少一层 Promise 也少一层出错点。
代价是**主进程做没做成，渲染进程并不知道**——比如启动浏览器失败，界面不会立刻报错。

#### 19.3 为什么流程图界面不用 IPC 而是 WebSocket

| | IPC | WebSocket 8084 |
|---|---|---|
| 通道 | Electron 内部 | 本机 TCP |
| 谁能连 | 只有开了 preload 的窗口 | 任意能连该端口的进程/页面/扩展 |
| 跨平台连通 | 只在 Electron 内 | 浏览器扩展也能接进来 ✅ |

EasySpider 的浏览器扩展（Chrome MV3）**不是 Electron 的一部分**，它没法用 IPC，
只能靠 WebSocket 与 Electron 对话。既然要开 8084，**流程图界面复用同一条路**反而更省事、也让 Web 版能直接跑。

#### 19.4 为什么 Python 执行器用子进程而不是自己实现

Python 生态里有 selenium、`ddddocr`、`xlsx`、HTTP client……重写成本极高。
Electron 只要负责"把子进程拉起来、把 stdout 打到日志"就够了。

---

### 20. 局限与应对

| 局限 | 原因 | 说明 / 应对 |
|---|---|---|
| **端口冲突会导致打不开** | 8074/8075/8084 固定 | 先查占用进程；8084 不可改（扩展写死） |
| **8084 无鉴权** | WebSocket 服务面向本机 | 任何人连上 8084 都能下指令；只在可信环境使用 |
| **macOS 数据目录特殊** | Gatekeeper App Translocation | `getDir()` 已处理（§18.2） |
| **包体很大** | 自带 Chromium + Python 执行器 | Electron 的固有代价 |
| **主进程卡住 = 整个界面卡住** | 只有一个主进程 | `travel()` 等同步 IO 会短暂阻塞（注意 §16.1 的同步 API） |
| **IPC 无回执** | 全用 `send` | 启动浏览器失败时界面不会立刻报错 |
| **Web 内容可被修改** | 页面都由本机 HTTP 提供 | 这是"可以用浏览器直接打开调试"的另一面 |

---

### 21. 本篇小结

```text
Electron = Chromium（渲染）+ Node.js（主进程）+ 打包外壳
两种进程：主进程 1 个（窗口/文件/子进程），渲染进程每窗口 1 个（只能跑网页）
preload：唯一合法把网段上的桥；contextBridge.exposeInMainWorld 是唯一安全挂法
IPC：invoke/handle（有回值，Promise） vs send/on（单向通知）

EasySpider 的真实结构：
  ElectronJS/main.js        主进程（约 1877 行）：窗口 + WebSocket + 起服务 + spawn Python
  ElectronJS/src/js/preload.js  15 行，只暴露 startDesign/startInvoke/acceptAgreement/changeLang
  ElectronJS/src/index.js   渲染进程 Vue3：调 window.electronAPI.*
  ElectronJS/server.js      Express：8074 页面+API、8075 上传
  8084 WebSocket            给浏览器扩展和流程图界面用

窗口：mainWindow（有 preload，走 IPC）/ flowchart_window / invoke_window（都无 preload，走 WS）
数据目录：未打包=__dirname；Win/Linux 打包=resourcesPath 上两级；macOS 打包=userData
```

一句话：**EasySpider 的本体是一个 Electron 主进程，它一边用 IPC 听首页指挥，一边用 WebSocket 听浏览器扩展，再顺手把 Python 拉起来干脏活。**

---

### 22. 动手练习

**① 跑通第一部分的最小例子**：照 §3 建三个文件，`npm start` 运行。
确认：在页面上打字 → 保存 → 关掉重开 → 读取，文本还在（说明真的落盘了）。

**② 故意违规，看报错**：在 `index.html` 的 `<script>` 里加一行 `require("fs")`，
看看控制台报什么？这正说明了 `contextIsolation` 挡住了什么。

**③ 给最小例子加一个 `invoke`**：仿照 `read-note`，加一个 `hello` 频道，
让主进程返回 `"你好，" + name`，体会"有返回值"和"单向通知"的差别。

**④ 对照 EasySpider 的 preload**：打开 `ElectronJS/src/js/preload.js`，
数一数它暴露了几个函数、分别对应 `main.js` 里哪几个 `ipcMain.on`。
再打开 `src/index.js`，找出调用 `window.electronAPI.*` 的那几处。

**⑤ 查端口**：启动 EasySpider 后执行 `netstat -ano | findstr "8074 8075 8084"`，
确认三个端口都在；再想一想：**如果 8084 被别的程序占了，功能上会坏在哪？**

**⑥ 看图说话**：把流程图界面的一致性/独立性对照表（§13.1）画成"两个窗口、两条通道"的示意图，
标清楚哪个窗口有 preload、哪个没有、各自走什么通道。

## 第三部分：Electron 怎样把调试请求交给浏览器插件

### 23. 从流程图按钮到浏览器消息：主进程的调试出口

流程图界面、Electron 主进程、Chrome 内容脚本是三个独立的消息参与者。[logic.js](/source/?file=786aaf2ec8ee7dbd78.js) 的 `trialElement()` 发请求，[main.js](/source/?file=5b1dab0d6ae24484fc.js) 的 `msg.type==4` 分支决定标记或实际试运行。实际试运行中的点击、输入等可以由主进程 WebDriver 直接改变网页，插件还负责标记和显示反馈；录制时的即时动作见[第 16.2 节](#electron-browser-actions)。下一篇[调试功能详解](/easyspider/chapter-25)按接收顺序展开插件的定位、字段标记、条件与通知。

#### 23.1 用户点“标记”或“试运行”，请求先到主进程

```js
// logic.js / trialElement(node, type=1) 的关键代码
updateParentNode();
let message = {
    type: 4,
    from: 1,
    message: {
        type: type,
        node: JSON.stringify(node),
        parentNode: JSON.stringify(app._data.parentNode)
    }
};
ws.send(JSON.stringify(message));
```

外层数字 `4` 是调试请求协议；内层 `message.type=0` 请求标记，`1` 请求实际试运行。`node` 和 `parentNode` 是 JSON 字符串。父上下文让主进程知道相对字段 `/p[1]` 属于哪一组商品。

这里不是流程图调用 Chrome 扩展的函数，也不走首页 preload 的 IPC；流程图与插件分别连接主进程的 WebSocket 服务，调试请求由主进程处理。

#### 23.2 主进程先按内层 type 决定工作，再决定回发消息

```js
// main.js 的控制流骨架；各 option 的具体执行省略
} else if (msg.type == 4) {
    let node = JSON.parse(msg.message.node);
    let type = msg.message.type;
    if (type == 0) {
        // 定位与滚动；部分 JS 条件在此计算并写回 msg.message.result
        send_message_to_browser(JSON.stringify({type: "trial", message: msg}));
    } else {
        // 检查是否处于任务设计阶段，再执行 Selenium 动作或读取单字段
        // notify_browser(...) 发送进度、结果或错误
    }
}
```

标记路径中，主进程按 option 2/4/6/7 定位动作目标，按 option 3 取第一个字段定位，按 option 11 取 parameters.index 对应字段，按 option 8 定位循环范围。定位通过 `findElementAcrossAllWindows()` 处理窗口、iframe 与滚动；此处负责把网页视图带到目标附近，插件还会在自己的文档里查 XPath 并画标记。

条件分支 option 10 的 class 5/7 在主进程调用 execute_js，写回 `msg.message.result=0/1/-1`；其他可预览的文本/元素条件交给插件处理。循环 loopType=5 的 JS 条件则会直接通过 notify_browser 给条件成立/不成立通知。

实际试运行路径检查 flowchart_window；设计环境不满足时通知流程图，满足时先通知浏览器“正在试运行”，再按节点执行。读取一个价格字段得到 ￥99 后，回发的是 `notify` 文本，而不是再让插件执行一遍提取节点。

#### 23.3 send_message_to_browser：到底发给谁

```js
// main.js 的实际发送函数
function send_message_to_browser(message) {
    socket_window.send(message);
    for (let i in allWindowSockets) {
        try {
            allWindowSockets[i].send(message);
        } catch {
            console.log("Cannot send to socket with id: ", allWindowScoketNames[i]);
        }
    }
}
```

参数 message 已经是序列化字符串。函数先向 socket_window 发送，再遍历记录的其他网页连接；它没有在这个函数里按 node 的 id 筛出唯一目标。每个内容脚本收到后，在自己的 document 查询，因此同一个 XPath 在不同文档可能得到不同结果。

首个 send 不在 try 内，后面的发送失败才被逐项捕获；源码日志还使用了 `allWindowScoketNames` 这个拼写。不能把它解释成带目标确认、去重与可靠回执的发送队列。

#### 23.4 notify_browser：把执行结果变成插件能显示的消息

```js
function notify_browser(msg_zh, msg_en, level = "info") {
    if (msg_zh.split("：").length > 1 && msg_zh.split("：")[1].includes("null")) {
        level = "warning";
    }
    send_message_to_browser(JSON.stringify({
        type: "notify", level: level, msg_zh: msg_zh, msg_en: msg_en
    }));
}
```

例如主进程调用 `notify_browser("获取的内容：￥99", "Content obtained: ￥99", "success")`，插件收到：

```json
{"type":"notify","level":"success","msg_zh":"获取的内容：￥99","msg_en":"Content obtained: ￥99"}
```

`notify` 不带需要插件执行的 node；插件根据语言取文字，交给 createNotification。点击试运行的一些成功路径还发送 `{"type":"cancelSelection"}` 清掉选择。显示/隐藏操作台由主进程收到 type 30/31 后转换为 `showAllToolboxes/hideAllToolboxes`，也通过同一个发送出口。

#### 23.5 接到下一篇：浏览器按哪一层字段分发

| 主进程发出的外层 type | 内容脚本入口 | 下一篇展开的工作 |
| --- | --- | --- |
| `trial` | messageInteraction → trial(evt) | 解析嵌套 node/parentNode、清旧标记、按 option/class 定位或预览 |
| `notify` | messageInteraction → createNotification | 显示主进程读取的字段值、进度、条件或错误 |
| `cancelSelection` | messageInteraction → clearEl | 撤销本地选择与预览 |
| `showAllToolboxes` / `hideAllToolboxes` | 修改 wrapperToolkit.style.display | 显示/隐藏当前文档的操作台 |
| `update_parameter_num` | 更新 chrome.storage.local | 参数编号同步；属于设计状态同步 |

```text
流程图 trialElement(node,0) → type 4 请求 → Electron 定位/计算
                                           ↓ type="trial"
                                 插件 trial → 标记与条件提示

流程图 trialElement(node,1) → type 4 请求 → Electron Selenium 试运行
                                           ↓ type="notify"
                                 插件 createNotification → 显示结果
```

对同一个字段分别点标记和试运行，先记录主进程收到的内层 type，再记录发给插件的字符串 type。下一篇从这两种实际输入开始，逐个解释浏览器接收与调试过程。

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[23.流程图的保存与加载](/easyspider/chapter-23) ｜ 下一篇：[25.调试功能详解](/easyspider/chapter-25)
