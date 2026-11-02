---
title: "13 · WebSocket"
description: "easyspider · 界面与通信 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/13.WebSocket详解.md"
originalUrl: "/originals/easyspider/chapter-13.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 13.WebSocket：三进程实时通信的桥梁

上一篇已解释操作台怎样确认并调用发送函数。现在先补 WebSocket 的连接、收发和 JSON 包装背景，下一篇再按 messageInteraction.js 的每个函数追消息。

> EasySpider 的扩展和 Electron 靠 WebSocket 说话。
> 这一篇从"为什么需要它"讲到"EasySpider 具体怎么用"。

---

## 1. 先看问题：HTTP 为什么不够

传统 HTTP 是"**请求—响应**"模式。

客户端问一次，服务器答一次。

```text
客户端：喂，有新消息吗？   →  服务器：没有
客户端：喂，有新消息吗？   →  服务器：没有
客户端：喂，有新消息吗？   →  服务器：有！
```

这叫**轮询**，缺点很明显：

- 慢（要等到下次轮询才知道）；
- 浪费（大量空请求）；
- 服务器压力大。

但 EasySpider 的场景是：

**你在网页上点一下，流程图界面要立刻更新。**

这需要服务器能**主动推**给客户端。

这正是 WebSocket 的用武之地。

---

## 2. WebSocket 是什么

一句话：

> **一次握手，之后双方随时可以互发消息，连接不断开。**

把它和 HTTP 摆在一起对比最直观：

```text
HTTP:                               WebSocket:
请求 ──►                           请求（握手：我要升级协议）──►
     ◄── 响应                            ◄── 101 Switching Protocols
连接断开                             ═══════════════════════════
                                    双向通道，随时互发，保持打开
                                     ═══════════════════════════
```

它的几个关键特征：

- 基于 TCP，全双工（两边都能主动发）；
- 握手时借用 HTTP 的 `Upgrade` 头；
- 连接后用轻量的帧（frame）传数据，开销远小于 HTTP。

再用一句话对比：

| | HTTP | WebSocket |
| --- | --- | --- |
| 方向 | 单向（客户端问） | 双向 |
| 连接 | 用完即断 | 长连接 |
| 适合 | 拉数据、看网页 | 聊天、实时协作、**本项目** |

---

## 3. 最小例子：20 行搞懂

先看服务端（Node.js）。

```js
const WebSocket = require("ws");
const wss = new WebSocket.Server({ port: 8084 });

wss.on("connection", function (ws) {
    console.log("有客户端连进来了");
    ws.on("message", function (msg) {
        console.log("收到:", msg.toString());
        ws.send("我收到你的消息了");   // 主动推回去
    });
});
```

再看客户端（浏览器）。

```js
const ws = new WebSocket("ws://localhost:8084");

ws.onopen = () => ws.send("你好，我是客户端");
ws.onmessage = (evt) => console.log("收到:", evt.data);
ws.onclose = () => console.log("连接关闭了");
```

跑起来你会看到双方互相收到消息。

就这么简单。

### 3.1 补充：`send` 怎么用

上面只在 `onopen` 里发过一条。

真实场景是：**连接建立后，随时都能发**。

#### 用法一：事件触发时发（最常见）

```js
// 比如页面上有个按钮，点一下就发一条
document.getElementById("say").onclick = function () {
    ws.send("这是按钮发出来的消息");
};
```

不需要等回复，发完就完事。

对方来了会进你的 `onmessage`。

#### 用法二：发对象要先 stringify

```js
let data = { cmd: "count", value: 42 };

ws.send(JSON.stringify(data));   // ✅ 发字符串
// ws.send(data);                // ❌ 隐式转成 "[object Object]"
```

WebSocket 只能发**字符串、二进制（Blob/ArrayBuffer）**。

对象不行，必须自己转字符串。

💡 这正是坑 3 的根源，EasySpider 里到处是 `JSON.stringify`。

#### 用法三：发之前确认连接还活着

```js
function safeSend(msg) {
    if (ws.readyState === WebSocket.OPEN) {   // 1 = 已连接
        ws.send(msg);
    } else {
        console.log("还没连上，发不出去");
    }
}
```

`readyState` 有四个值：

```text
0  CONNECTING  正在握手
1  OPEN        连接好了，能收发   ← 只有这个状态能 send
2  CLOSING     正在关闭
3  CLOSED      已关闭
```

💡 **最容易踩的坑**：

```js
const ws = new WebSocket("ws://localhost:8084");
ws.send("现在还没连上");     // ❌ 直接报错 InvalidStateError
```

> `new WebSocket` 是**异步**的——
>
> 这行执行完，握手还在路上。
>
> 所以第一条消息一般放在 `onopen` 里发，或用 `safeSend` 挡一下。

🔬 **EasySpider 的做法**：

> `messageInteraction.js` 里把 `ws` 存在 `global.ws`，
>
> 之后任何地方想发，直接 `global.ws.send(...)`。
>
> 它没做 readyState 检查——
>
> 因为消息都来自用户操作，那时连接早已建立。

---

## 4. 打开网页就能看到 WebSocket

按 F12 → Network → WS 标签页，刷新页面。

你能看到一条状态为 **101** 的请求。

点开就是实时收发的消息流。

**调试 EasySpider 时这是最常用的手段。**

---

## 5. EasySpider 中的服务端

服务端写在 `ElectronJS/main.js` 里：

```js
const websocket_port = 8084;   // 写死，因为扩展里也写死了
const WebSocket = require("ws");
let wss = new WebSocket.Server({ port: websocket_port });

wss.on("connection", function (ws) {
    ws.on("message", async function (message, isBinary) {
        // 处理来自浏览器扩展的消息
    });
    ws.on("close", async function (event) {
        // 客户端断开
    });
});
```

---

## 6. EasySpider 中的客户端（扩展）

客户端在 `Extension/.../messageInteraction.js` 里：

```js
global.ws = new WebSocket("ws://localhost:8084");

global.ws.onopen = function () {
    // 一连上就自报家门
    let message = {
        type: 0,                                  // 0 = 连接操作
        message: { id: global.id, title: document.title }
    };
    this.send(JSON.stringify(message));
};

global.ws.onmessage = function (evt) {
    evt = JSON.parse(evt.data);
    if (evt["type"] == "trial") {
        trial(evt);                    // 执行试运行高亮
    } else if (evt["type"] == "cancelSelection") {
        clearEl();                     // 取消选中
    } else if (evt["type"] == "update_parameter_num") {
        chrome.storage.local.set({"parameterNum": parseInt(evt["value"])});
    } else if (evt["type"] == "notify") {
        createNotification(LANG(evt["msg_zh"], evt["msg_en"]), evt["level"]);
    }
};
```

💡 每个标签页 `new WebSocket` 时会生成一个随机 id：

```js
id: "C" + Math.floor(Math.random() * 99999999)
```

这样服务端能区分"是哪个标签页发来的消息"。

浏览器开了多个标签页时，这一点很关键。

---

## 7. 消息协议：他们约定了什么

EasySpider 定义了简洁的消息协议。

其中 `type` 字段是判别式。

| type | 含义 | 方向 |
| --- | --- | --- |
| 0 | 连接建立 / 更新参数号 | 双向 |
| 1 | 参数索引值询问 | → |
| 2 | 键盘输入指令 | 扩展 → 主程序 |
| 3 | 元素增加事件 | 扩展 → 流程图 |
| "trial" | 试运行高亮 | 主程序 → 扩展 |
| "cancelSelection" | 取消选中 | 主程序 → 扩展 |
| "notify" | 弹通知 | 主程序 → 扩展 |

统一的信封格式长这样：

```js
{
  "type": 3,
  "from": 0,                        // 0=浏览器→流程图, 1=流程图→浏览器
  "message": { "pipe": "..." }      // 业务数据（常是 JSON 字符串）
}
```

🔬 **为什么要 `JSON.stringify` 之后再嵌套？**

因为 `message.pipe` 里的内容是另一个 JSON。

这样外层协议和内层数据解耦。

扩展起来互不影响。

---

## 8. 一次完整交互的时序

从握手到高亮，整个过程如下：

```text
扩展                           Electron
  │                               │
  │──── 握手升级协议 ─────────────►│
  │◄─── 101 Switching Protocols ──│
  │                               │
  │──── {type:0, id:"C123"} ─────►│  上报自己上线了
  │                               │
  │   （用户点了"采集文本"）        │
  │──── {type:3, pipe:"{...}"} ──►│  上报一个任务节点
  │                               │  插入流程图
  │                               │
  │◄─── {type:"trial", ...} ──────│  要求试运行高亮
  │  高亮元素                      │
  │                               │
```

---

## 9. 常见坑

💡 **坑 1：端口写死**

8084 在扩展和 Electron 里各写死一次。

改端口要改两处。

💡 **坑 2：服务没起来**

Electron 没启动时，扩展的 `ws.onopen` 不会触发。

`onclose` 里其实应该加**重连**逻辑（EasySpider 原版较简单，学习时可拓展）。

💡 **坑 3：发出去的是对象还是字符串**

很容易忘记 `JSON.stringify`，导致收到 `[object Object]`。

🔬 **进阶**：生产级 WebSocket 需要"心跳保活"（定时发 ping）。

防止中间代理把空闲连接掐断。

---

## 10. 本篇小结

```text
WebSocket = HTTP 升级来的长连接，双向实时
服务端：new WebSocket.Server({port:8084})
客户端：new WebSocket("ws://localhost:8084")
通信：统一信封 {type, from, message}
作用：把扩展、Electron 三个进程缝在一起
```

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[12.toolkit.vue：怎样画出操作台、显示表格并修改选择](/easyspider/chapter-12) ｜ 下一篇：[14.messageInteraction.js：每条消息怎样把操作台接到流程图](/easyspider/chapter-14)
