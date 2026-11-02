---
title: "02 · 数据流全链路"
description: "easyspider · 认识项目 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/02.数据流全链路.md"
originalUrl: "/originals/easyspider/chapter-02.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 02.数据流全链路：从选中元素到执行完成

> 上一篇讲了"有哪些零件"，这一篇讲"数据怎么流"。

> 全程跟着一个元素走一遍，你就懂整个项目了。

---

## 1. 起点：你在网页上右键点了一个商品标题

此时发生了 3 件事（代码在 `Extension/.../main.js`）。

```js
// 1) 监听 mousedown，触发 addEl
document.addEventListener("mousedown", addEl);

// 2) addEl 把元素存进 global.nodeList
global.nodeList.push({
    node: global.NowNode,          // DOM 元素引用
    step: global.step,             // 第几次点击
    bgColor: style,                // 原背景色（用于还原）
    xpath: readXPath(global.NowNode, 1),      // 绝对 XPath
    allXPaths: getElementXPaths(global.NowNode) // 多个候选 XPath
});
global.NowNode.style.backgroundColor = "rgba(151,255,255,0.6)"; // 高亮
```

**关键点**：此刻只记录了"元素 + 它的 XPath"，还没形成任务。

---

## 2. 第二步：自动找同类元素（待选 readyList）

选中一个标题后，软件会问：

*页面上还有没有长得像它的元素？*

这段逻辑叫 `findRelated()`，它的思路极妙（详见第 6 篇）。

```text
原始 XPath：/html/body/div[3]/div[1]/div[1]/a[22]
                                  ↑ 把这里的数组索引一层层去掉试试
                                        ↓
尝试：     /html/body/div[3]/div[1]/div[1]/a
                → 如果去掉索引后能匹配到 ≥2 个元素，就说明"同类"
```

找到的同类元素放进 `global.readyList`（**待选框**，虚线高亮）。

然后等待你点"选中全部"确认。

这两个列表的区别，先记住：

```text
nodeList  = 已选中（实线高亮，青色背景）
readyList = 待选中（虚线框，等你确认）
```

💡 这两个列表的区别，是理解整个交互的**核心**。

---

## 3. 第三步：生成任务节点（JSON 片段）

你在操作台上点了"采集该元素的文本"。

这时 `toolkit.vue` 会调用 `generateParameters()`。

它生成 `outputParameters`（要采集的字段），并通过 WebSocket 发给 Electron：

```js
// messageInteraction.js
let message = {
    "type": 3,
    "from": 0,
    "message": { "pipe": JSON.stringify(nodeData) }
};
global.ws.send(JSON.stringify(message));
```

Electron 收到后，把它插入流程图，成为一个节点（比如"提取数据"节点）。

---

## 4. 第四步：保存任务成 JSON

流程图上的节点最终被序列化成我们熟悉的那个 JSON。

```json
{
  "name": "我的任务",
  "url": "https://example.com",
  "graph": [
    { "id": 1, "option": 1, "title": "打开网页", "sequence": [2] },
    { "id": 2, "option": 3, "title": "提取数据", "sequence": [3],
      "parameters": {
        "params": [
          { "name": "参数1", "relativeXPath": "/html/body/div[3]/a[1]",
            "nodeType": 0, "contentType": 0 }
        ]
      }
    }
  ],
  "outputParameters": [ { "name": "参数1", "type": "string" } ]
}
```

---

## 5. 第五步：执行器接管

当你点"执行任务"，Electron 用子进程启动 Python 执行器。

```py
# easyspider_executestage.py
self.procedure = service["graph"]     # 整个图
...
def executeNode(self, nodeId, ...):
    node = self.procedure[nodeId]
    if node["option"] == 1:  self.openPage(...)      # 打开网页
    elif node["option"] == 2: self.clickElement(...)  # 点击
    elif node["option"] == 3: self.getData(...)       # 提取
    elif node["option"] == 8: self.loopExecute(...)   # 循环
    elif node["option"] == 9: self.judgeExecute(...)  # 条件
    ...
```

**这就是"重放"**。

`executeNode` 递归地沿着 `sequence` 走。

遇到循环就展开。

遇到条件就选择分支。

---

## 6. 第六步：数据落地

提取到的数据不断填进 `self.outputParameters`。

每采集一条就 `saveData()` 追加写文件。

数据最终落到这样的目录里：

```text
Data/Task_<id>/<saveName>/
├── files/        ← 下载的文件
├── images/       ← 下载的图片
├── screenshots/  ← 元素截图
└── result.csv    ← 采集结果（csv/txt/xlsx/json/mysql 可选）
```

---

## 7. 全链路总览图

把前面七步连起来，就是这条流水线：

```text
[你在网页右键点元素]
        │
        ▼
 main.js: addEl()
        │  记录 XPath
        ▼
 global.nodeList  ──findRelated()──►  global.readyList (待选)
        │
        │ 点"选中全部" / "采集文本"
        ▼
 toolkit.vue: generateParameters()
        │
        │ WebSocket(8084) type=3
        ▼
 Electron main.js: 插入流程图节点
        │
        │ 点"保存/执行"
        ▼
 task.json (含 graph + outputParameters)
        │ 子进程
        ▼
 easyspider_executestage.py: executeNode() 逐节点重放
        │
        ▼
 Selenium 操作真实 Chrome → 抓取 → 写 CSV/Excel/JSON
```

---

## 8. 一句话总结

再压缩成四行：

```text
人点元素   → 变成 XPath
XPath      → 变成 JSON 节点（graph）
graph      → 被 executeNode 逐节点重放
重放结果   → 落到 Data/ 目录
```

理解了这条流水线，后面每一篇都是在放大其中的某一环。

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[01.总体架构与目录剖析](/easyspider/chapter-01) ｜ 下一篇：[03.Chrome 扩展开发（Manifest V3）从零讲透](/easyspider/chapter-03)
