---
title: "03 · Chrome 扩展与 MV3"
description: "easyspider · 元素与任务 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/03.Chrome扩展开发MV3.md"
originalUrl: "/originals/easyspider/chapter-03.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 03.Chrome 扩展开发（Manifest V3）从零讲透

EasySpider 的依赖安装、源码启动与扩展调试入口见 [第 27 篇的开发环境与源码调试部分](/easyspider/chapter-27)。本篇从独立小扩展开始，讲清扩展机制后再回到项目。

> 这一篇先完全不讲 EasySpider。
>
> 我们从零写一个**跟 EasySpider 毫无关系**的小扩展。
>
> 把扩展"有哪些零件、每个零件干什么、文件长什么样、怎么跟网页交互、零件之间怎么通信"全部走一遍。
>
> 最后再回头看：EasySpider 是怎么做的。

---

## 第一部分：从零写一个自己的扩展

### 1. 扩展到底是什么

浏览器扩展，就是**一段寄生在浏览器里的程序**。

它能做普通网页脚本做不到的事：

```text
① 读取 / 修改你正在看的任何网页
② 在浏览器工具栏放一个图标和面板
③ 在后台默默跑逻辑（即使没有打开任何网页）
④ 调用浏览器本身的 API（标签页、书签、下载……）
⑤ 和浏览器之外的程序通信（比如本机的一个服务）
```

和普通网页脚本最本质的区别：

> **网页脚本只能管自己那个页面；扩展能管所有页面。**

---

### 2. 最简单的扩展：两个文件

先来一个" Hello World "级别的。

功能：**让所有网页的背景变成黄色。**

#### 文件 1：manifest.json（扩展的身份证）

```json
{
  "manifest_version": 3,
  "name": "我的第一个扩展",
  "version": "1.0",
  "content_scripts": [
    {
      "matches": ["https://*/*"],
      "js": ["content.js"]
    }
  ]
}
```

逐行解释：

```text
manifest_version : 3        用 MV3 标准（当前主流）
name / version              名字和版本号
content_scripts             "往网页里注入脚本"的声明
  matches                   哪些网页注入（这里=所有 https 页面）
  js                        注入哪个文件
```

#### 文件 2：content.js（被注入网页的脚本）

```js
document.body.style.background = "yellow";
```

就一行。

#### 怎么运行

```text
① 新建一个文件夹，把两个文件放进去
② 地址栏输入 chrome://extensions
③ 右上角打开「开发者模式」
④ 点「加载已解压的扩展程序」，选中这个文件夹
⑤ 随便打开一个 https 网站
```

背景变黄了。

> 一个扩展，最少就这么多。

---

### 3. 但是这个例子缺了什么

上面的例子只有 content script 一个零件。

真实的扩展通常有**四个零件**：

```text
① manifest.json     身份证（必须有）
② content script    注入网页的"手"——能操作 DOM
③ background        后台的"大脑"——能用完整 Chrome API
④ popup             点图标弹出的小面板——给用户看、让用户点
```

它们各有各的能力边界：

| 零件 | 能操作网页 DOM | 能用完整 Chrome API | 有界面吗 | 什么时候活着 |
| --- | --- | --- | --- | --- |
| content script | ✅ | 只有一小部分 | 无 | 页面开着就活着 |
| background | ❌ | ✅ | 无 | 事件来了就醒，闲了可能被回收 |
| popup | ❌ | ✅ | 有（小面板） | 面板开着才活着 |

💡 **核心矛盾**：

> 只有 content script 能碰到网页，
> 但只有 background / popup 能用完整的浏览器 API。
>
> 所以它们**必须互相通信**。

---

### 4. 一个完整例子：字数统计器

现在写一个四零件齐全的扩展。

功能：

```text
① 点扩展图标，弹出一个小面板
② 面板上有个「统计字数」按钮
③ 点按钮 → 统计当前网页的字数 → 显示在面板上
④ 每次统计，后台悄悄记一条历史
⑤ 面板上还能查"上一次统计了多少字"
```

#### 4.1 文件结构

> 💡 **这个例子的完整可运行版本已放在讲义文件夹里**：`示例扩展-字数统计器/`，加载方式见其中的 README。

```text
word-counter/
├── manifest.json      身份证 + 权限声明
├── popup.html         面板长什么样（HTML）
├── popup.js           面板的逻辑
├── content.js         注入网页：负责数数
└── background.js      后台：负责记账
```

5 个文件，每个都不长，下面逐个看。

#### 4.2 manifest.json

```json
{
  "manifest_version": 3,
  "name": "字数统计器",
  "version": "1.0",
  "description": "统计当前网页的字数并保存历史",
  "action": {
    "default_popup": "popup.html",
    "default_title": "字数统计器"
  },
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [
    {
      "matches": ["http://*/*", "https://*/*"],
      "js": ["content.js"]
    }
  ],
  "permissions": ["storage", "activeTab", "scripting"],
  "host_permissions": ["http://*/*", "https://*/*"]
}
```

比刚才多了几块，逐块解释：

```text
action.default_popup      点工具栏图标时，弹出 popup.html
background.service_worker 后台脚本（MV3 叫 service worker）
permissions               扩展想用的浏览器能力：
   storage               读写 chrome.storage（跨零件共享的存储）
   activeTab             访问"当前正在看的标签页"
   scripting             允许动态向页面注入脚本
host_permissions          允许访问哪些网站的页面
```

💡 **permissions 是安装时弹给用户看的**。

要得越多，用户越警惕。

只申请真正需要的。

#### 4.3 popup.html（面板长什么样）

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style> body { width: 240px; font-family: sans-serif; } </style>
</head>
<body>
  <h3>当前页面字数</h3>
  <p id="result">点下面按钮开始统计</p>

  <button id="count">统计字数</button>
  <button id="history">查看上次结果</button>

  <script src="popup.js"></script>
</body>
</html>
```

就是一个普通的小网页。

唯一特别的是：它**运行在扩展自己的小窗口里**，和任何网页都不挨着。

#### 4.4 popup.js（面板的逻辑）

```js
// ① 点「统计字数」：问当前网页的 content script 要字数
document.getElementById("count").onclick = function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    chrome.tabs.sendMessage(tabs[0].id, { cmd: "getCount" }, function (response) {
      if (chrome.runtime.lastError) {
        // 页面里没有 content script（比如刚装完扩展，页面还没刷新）
        document.getElementById("result").innerText = "请刷新页面后重试";
        return;
      }
      document.getElementById("result").innerText = response.count + " 个字";
    });
  });
};

// ② 点「查看上次结果」：从共享存储里读
document.getElementById("history").onclick = function () {
  chrome.storage.local.get("history", function (items) {
    let h = items.history || [];
    document.getElementById("result").innerText =
      h.length ? "上次：" + h[h.length - 1].count + " 个字" : "还没有历史";
  });
};
```

出现了两个关键 API，先记住长相：

```text
chrome.tabs.query(...)          找到"当前激活的标签页"
chrome.tabs.sendMessage(tabId, ...)  向那个标签页里的 content script 发消息
chrome.storage.local.get(...)   从共享存储读数据
```

#### 4.5 content.js（数数的人）

```js
// 被 manifest 注入到每个网页里
// 这里可以直接用 document —— 因为它就"活在"网页里

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.cmd === "getCount") {
    let text = document.body.innerText;            // ① 拿整页文字
    let count = text.replace(/\s+/g, "").length;   // ② 去掉空白，数字符

    sendResponse({ count: count });                // ③ 回给 popup

    // ④ 顺手告诉后台：记一笔
    chrome.runtime.sendMessage({ cmd: "record", count: count });
  }
});
```

注意两个方向**不同**的消息 API：

```text
chrome.runtime.onMessage     监听：谁发给"我"都行
chrome.runtime.sendMessage   发给"扩展的其他零件"（background / popup）
sendResponse                 用"回调"的方式回复"这一次"的提问
```

**注意这个sendResponse是从content.js回给popup.js的回调函数，这里直接调用**，而chrome.runtime.sendMessage是content.js发给background.js的。

#### 4.6 background.js（记账的人）

```js
// 后台 service worker：唯一的职责是维护"历史记录"

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.cmd === "record") {
    chrome.storage.local.get("history", function (items) {
      let h = items.history || [];
      h.push({
        url: sender.tab.url,        // sender 参数里自带"从哪个页面发来的"
        count: request.count,
        time: Date.now()
      });
      chrome.storage.local.set({ history: h });
    });
  }
});
```

🔬 **注意 `sender` 参数**：

> onMessage 的第二个参数 `sender`，
> 自动带有 `sender.tab.url` 等来源信息。
>
> 不需要调用方自己传"我是谁"。

#### 4.7 跑起来的样子

```text
你点图标
  → popup.html 弹出
你点「统计字数」
  → popup.js 用 tabs.sendMessage 问 content.js
      → content.js 用 document 数出 3842
  → 3842 传回 popup，显示"3842 个字"
  → 同时 content.js 用 runtime.sendMessage 告诉 background.js
      → background.js 往 chrome.storage 里记一笔
你点「查看上次结果」
  → popup.js 直接从 chrome.storage 里读
```

四零件全部出场，各干各的活。

---

### 5. 扩展怎么"跟外部页面"交互


#### 5.1 注入：content script 是怎么进到网页里的

manifest 里这段就是"注入声明"：

```json
"content_scripts": [
  {
    "matches": ["http://*/*", "https://*/*"],
    "js": ["content.js"],
    "run_at": "document_end",
    "all_frames": false
  }
]
```

四个字段分别控制：

```text
matches    往哪些页面注入（URL 匹配模式）
js         注入哪些脚本（可以多个，按顺序执行）
run_at     什么时机注入：
             document_start   DOM 还没建（最早）
             document_end     DOM 建好了，图片还没加载完（最常用）
             document_idle    浏览器自己挑空闲时机（默认）
all_frames 是否连页面里的 <iframe> 也注入（默认 false）
```

#### 5.2 隔离世界：能摸 DOM，但摸不到页面的变量

content script 最反直觉的一点：

> 它和网页**共享 DOM，但不共享 JavaScript 环境**。

```text
网页自己的 JS（页面脚本）    —— 主世界（Main World）
content script              —— 隔离世界（Isolated World）
```

两个世界各自有各自的：

```text
window 对象
全局变量
setTimeout 等回调队列
```

但两边看到**同一棵 DOM 树**：

```js
// content.js 里可以：
document.body.style.background = "yellow";   // ✅ 生效，页面看得见

// 但拿不到页面自己的变量：
console.log(window.somePageVar);             // ❌ undefined（如果那是页面 JS 定义的）
```

**为什么要这么设计？**

> ① 防打架：扩展和页面的变量互不覆盖。
>
> ② 安全：页面里的恶意脚本偷不到扩展内部的数据。

---

### 6. 几个文件之间的通信关系（全景）

#### 6.1 通信总图

```text
                    ┌──────────────────────┐
                    │  chrome.storage      │
                    │  （共享的键值存储）    │
                    └──────────▲───────────┘
                               │ 谁都能读/写
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   ┌────┴─────┐          ┌─────┴────┐           ┌─────┴────┐
   │ popup    │◄────────►│background│           │  content │
   │ (面板)    │ runtime │ (后台)    │           │  script  │
   └────┬─────┘ sendMessage└──────┘           └─────▲────┘
        │                                          │
        │        tabs.sendMessage（指定标签页）       │
        └──────────────────────────────────────────┘

   网页页面 ◄──DOM 共享（但 JS 环境隔离）──► content script
```

#### 6.2 通道一：runtime.sendMessage（扩展内部广播）

```js
// 任何零件都可以发：
chrome.runtime.sendMessage({ cmd: "record", count: 42 }, function (response) {
  // 收到对方的回复
});

// 任何零件都可以收：
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.cmd === "record") { ... }
  sendResponse({ ok: true });     // 回复这一次的提问
});
```

特点：

```text
发出去 → 扩展里所有"其他零件"都可能收到
一次消息一次回复（sendResponse）
消息内容会被 JSON 序列化 → 不能发函数
```

#### 6.3 通道二：tabs.sendMessage（指定某个网页）

runtime 消息是"广播"，但 background / popup 自己不在网页里。

想跟"某个标签页的 content script"说话，必须点名：

```js
chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
  chrome.tabs.sendMessage(tabs[0].id, { cmd: "getCount" }, callback);
});
```

```text
tabs.query     查询标签页（这里=当前激活的那个）
tabs[0].id     标签页编号，通信的"门牌号"
```

#### 6.4 通道三：chrome.storage（共享内存）

消息适合"喊一嗓子"，storage 适合"留个条"：

```js
chrome.storage.local.set({ history: [...] });     // 写

chrome.storage.local.get("history", function (items) {  // 读
  let h = items.history;
});

chrome.storage.onChanged.addListener(function (changes, area) {  // 变了会通知
  console.log(changes.history.newValue);
});
```

💡 **为什么不用 localStorage？**

> 三个零件活在三个世界里，localStorage 各玩各的。
>
> 只有 `chrome.storage` 是扩展全局共享的，
> 而且 service worker 被回收后数据还在。

#### 6.5 通道四：Port 长连接

sendMessage 是"一问一答就散"。

要连续说话（比如每秒推送），用长连接：

```js
// 发起方：connect 时给这条连接起个名字
let port = chrome.runtime.connect({ name: "my-channel" });
port.postMessage({ hello: 1 });
port.onMessage.addListener(function (msg) { ... });
```

```js
// 接收方：频道名不用（也没法）在这里设置
// 它是发起方带过来的，挂在 port.name 上
chrome.runtime.onConnect.addListener(function (port) {
  // 只处理自己关心的频道
  if (port.name !== "my-channel") return;

  port.onMessage.addListener(function (msg) {
    port.postMessage({ reply: 1 });   // 用同一个 port 回话
  });
});
```

💡 **频道名（name）的去向**：

> 发起方在 `connect({ name })` 里"起名"；
>
> 接收方在 `onConnect` 的 `port.name` 上"读名"。
>
> 如果接收方只服务一种连接，不判断 `port.name` 也能工作——
>
> 但扩展里有多条频道时，必须靠它区分。

#### 6.6 一张表总结

| 想干什么 | 用什么 |
| --- | --- |
| content ↔ background/popup 说话 | `chrome.runtime.sendMessage` |
| background/popup → 某个网页 | `chrome.tabs.sendMessage` |
| 跨零件留数据 | `chrome.storage` |
| 连续双向通话 | `chrome.runtime.connect`（Port） |
| 跟扩展**之外**的本机程序说话 | **WebSocket / Native Messaging** |

记住最后一行，EasySpider 靠它。

---

### 7. MV3 的两个脾气（写代码前必知）

#### 7.1 background 随时会被杀

```text
MV2 时代：background page 常驻内存
MV3 时代：service worker，事件来了才醒，闲了就被回收
```

所以：

> **别把状态存在 background 的全局变量里**。
>
> 要么存 `chrome.storage`，要么每次事件来了重新读。

#### 7.2 不允许加载远程代码

```text
MV2：可以 <script src="https://cdn.xxx/vue.js">
MV3：不行！所有代码必须打包进扩展里
```

第三方库（jQuery、Vue……）要**构建时打包**进去。

> 这就是为什么 EasySpider 的扩展要用 Rollup 打包——后面讲。

---

## 第二部分：EasySpider 的扩展是怎么做的

现在零件都认识了，回头看 ES。

### 8. ES 扩展的文件结构

真实的目录（`Extension/manifest_v3/src/`）：

```text
src/
├── manifest.json            身份证
├── background.ts            后台（74 行，很小！）
├── popup.html / popup.js    工具栏小面板（141 行）
├── content-scripts/
│   ├── main.js              注入入口（350 行）
│   ├── global.js            核心算法库（1186 行）★
│   ├── messageInteraction.js 消息收发（350 行）
│   ├── toolkit.vue          网页里的"操作台"界面（934 行）★
│   ├── iframe.vue           iframe 内的提示组件（82 行）
│   ├── trial.js             试运行逻辑（334 行）
│   └── config.json          配置（语言等）
└── style/  assets/          样式和图标
```

对照第一部分的四零件：

| 通用概念 | EasySpider 对应 |
| --- | --- |
| content script | `main.js`（入口）+ `global.js` + `toolkit.vue` + …… |
| background | `background.ts`（74 行，几乎只剩转发） |
| popup | `popup.js`（显示/隐藏操作台） |
| 身份证 | `manifest.json` |

🔬 注意 `.vue` 文件出现在这里。

浏览器不认识 `.vue`——

> 所以 ES 用 **Rollup** 打包（`rollup.config.js`），
> 把 Vue、jQuery、`.vue` 组件全部编译合并成纯 JS，
> 产出到 `dist/`，加载的是打包结果。

### 9. ES 的 manifest 逐行解读

真实的 `manifest.json`：

```json
{
  "name": "EasySpider",
  "version": "0.6.5",
  "manifest_version": 3,
  "action": {
    "default_icon": { "16": "assets/icon-16.png", "128": "assets/icon-128.png" },
    "default_popup": "popup.html",
    "default_title": "EasySpider"
  },
  "background": {
    "service_worker": "background.ts"
  },
  "content_scripts": [
    {
      "matches": ["http://*/*", "https://*/*"],
      "css": ["style/toolkit.css"],
      "js": ["content-scripts/main.js"],
      "run_at": "document_end",
      "all_frames": true
    }
  ],
  "web_accessible_resources": [
    {
      "resources": ["*/*.js"],
      "matches": ["http://*/*", "https://*/*"]
    }
  ],
  "permissions": [
    "identity", "storage", "tabs",
    "scripting", "activeTab", "notifications"
  ]
}
```

跟我们的字数统计器比，多了四个值得说的点：

#### ① `"all_frames": true`

很多网站的内容藏在 `<iframe>` 里。

ES 要选中 iframe 里的元素——

> 所以必须**每个 frame 都注入一份脚本**。

这也解释了 `iframe.vue` 为什么存在。

#### ② `"run_at": "document_end"`

DOM 建好就注入，别等图片。

要选元素，DOM 在就行。

#### ③ `web_accessible_resources`

content script 有时要往页面里塞 `<img>`、动态 `<script>` 指向扩展内部的资源。

不声明这里，网页加载不到（安全限制）。

#### ④ 权限里的 `notifications`

试运行结果用系统通知弹给用户看。

### 10. ES 怎么跟网页交互

ES 的 content script 干的事，本质上是：

#### 10.1 把操作台塞进页面

`main.js` 创建一个容器，把 Vue 组件挂上去：

```js
let toolkit = document.createElement("div");
toolkit.classList = "tooltips";
// ... 挂载 ToolKit 组件（toolkit.vue）
```

于是网页右下角长出 EasySpider 的操作台——

> **它不是浏览器 UI，就是普通 DOM，跟网页原生内容混在一起。**

#### 10.2 监听鼠标，选中元素

```text
鼠标移动 → tdiv 拦截事件 → 算出下面的元素
       → div 画虚线框高亮
点击    → 把元素存进 global.nodeList（见第 5 篇）
```

另外 `main.js` 开头有个小机关：

```js
if (window.location.href.indexOf("backEndAddressServiceWrapper") >= 0) {
    chrome.storage.local.set({ "parameterNum": 1 });
    throw "serviceGrid";   // 是 Electron 自己的页面，不注入工具
}
```

> 用 `throw` 中断整个脚本——简单粗暴但有效。

### 11. ES 的通信架构：WebSocket，而不是 chrome.runtime

#### 11.1 为什么不用前面讲的那些通道

回想通信总图：

```text
chrome.runtime / tabs / storage → 只在"扩展内部"转
```

但 EasySpider 的消息要发给谁？

> **Electron 桌面程序里的流程图！**

那不是浏览器，更不是扩展内部。

`chrome.runtime` 够不着它。

#### 11.2 所以：Electron 开一个 WebSocket 服务端

```text
ElectronJS/main.js 启动 WebSocket 服务端，监听 localhost:8084
```

扩展这边，**三个零件各自当了 WebSocket 客户端**：

```js
// ① content script 里（messageInteraction.js）
global.ws = new WebSocket("ws://localhost:8084");

// ② background.ts 里
let ws = new WebSocket("ws://localhost:8084");

// ③ popup.js 里
var ws = new WebSocket("ws://localhost:8084");
```

三个客户端，用不同的 id 区分身份：

```text
content script : id = "C" + 随机数   （每个标签页一个）
background     : id = 0
popup          : id = 3
```

#### 11.3 消息长什么样

以"选中一个元素，通知流程图加节点"为例：

```js
// messageInteraction.js
let message = {
  "type": "inputText",           // 干了什么（操作类型）
  "history": history.length,
  "xpath": readXPath(node, 0),   // 元素的 XPath
  "allXPaths": [...],            // 候选 XPath
  "iframe": global.iframe,
  "value": value,
  ...
};

let message_action = {
  type: 3,                       // 3 = 元素增加事件
  from: 0,                       // 0 = 浏览器→流程图（1 = 反向）
  message: { "pipe": JSON.stringify(message) }
};

global.ws.send(JSON.stringify(message_action));
```

外层的 `type` 是**事件类别**，内层 `pipe` 里才是具体数据。

#### 11.4 全景图

```text
┌─────────────────────── 浏览器（扩展） ───────────────────────┐
│                                                            │
│  content script ──ws:8084──┐                               │
│  (global.js 算法)           │                              │
│  (toolkit.vue 界面)         ├──► Electron main.js ◄── Python │
│  background ────ws:8084────┤    （WebSocket 服务端）  执行器  │
│  popup ────────ws:8084─────┘                               │
│                                                            │
│  小事仍走原生通道：                                          │
│    popup ──chrome.scripting──► 显示/隐藏操作台               │
│    各零件 ──chrome.storage───► parameterNum 参数计数         │
└────────────────────────────────────────────────────────────┘
```

💡 **一句话总结 ES 的通信选型**：

> 扩展内部的小事 → 原生 `chrome.*` API；
>
> 跨进程的大事（和 Electron 互传节点数据）→ **WebSocket**。

#### 11.5 background.ts 为什么只剩 74 行

打开看，一大半是**注释掉的旧代码**：

```js
// chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
//     if (request.type == 0) { ... }
//     ...
// });
```

这正是 MV2 时代的"扩展内部转发"写法。

现在数据直接走 WebSocket 了，background 只剩一件事：

```js
ws.onmessage = function (evt) {
  evt = JSON.parse(evt.data);
  if (evt["type"] == "0") {
    chrome.storage.local.set({ "parameterNum": parseInt(evt["value"]) });
  }
};
```

> **收 WebSocket 消息 → 写 chrome.storage → 给 content script 用。**
>
> 一座 74 行的小桥。

### 12. 本篇小结

```text
【通用】
扩展四零件：
  manifest     身份证+权限
  content      能摸 DOM 的手（隔离世界：共享 DOM、不共享 JS 变量）
  background   能用完整 API 的大脑（service worker，会被回收）
  popup        点图标的小面板（关了就销毁）

与网页交互 = 注入 content script（matches/run_at/all_frames）
              或按需 chrome.scripting.executeScript

零件间通信：
  runtime.sendMessage   扩展内部广播
  tabs.sendMessage      点名某网页
  chrome.storage        共享存储
  runtime.connect       长连接
  WebSocket             跟扩展之外的程序（ES 的选择）

【EasySpider】
入口 main.js + 算法 global.js + 界面 toolkit.vue
  （.vue 要靠 Rollup 打包成纯 JS）

与网页：wrapperDiv 高亮 + tdiv 拦截鼠标 + Vue 操作台直接塞进 DOM

通信：Electron 开 ws://localhost:8084，
  content/background/popup 三个客户端各自连上，
  消息 = { type 事件, from 方向, message.pipe 数据 }
  扩展内部小消息仍走 chrome.storage / scripting
```

---

### 13. 动手练习

1. 加载 `示例扩展-字数统计器/`，跑通四零件（安装步骤见该文件夹的 README）。
2. 把 matches 改成只对 `*.github.com` 生效。
3. 给 popup 加一个按钮：点击后让页面所有图片变灰（提示：content script 里遍历 `document.images`）。
4. 思考题：为什么 ES 不把流程图也做成扩展的一部分，而要放到 Electron 里？
   （提示：保存文件、启动 Python 进程，扩展都做不到。）

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[02.数据流全链路：从选中元素到执行完成](/easyspider/chapter-02) ｜ 下一篇：[04.XPath：元素定位的通用语言](/easyspider/chapter-04)
