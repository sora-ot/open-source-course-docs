---
title: "06 · 同类元素自动匹配"
description: "easyspider · 元素与任务 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/06.同类元素自动匹配.md"
originalUrl: "/originals/easyspider/chapter-06.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 06.同类元素自动匹配：点一个，猜出一整列

> 你点了一个商品标题，软件立刻猜出"页面上还有 19 个同类标题"。

> 这一篇讲这个"猜"是怎么实现的——本项目最巧妙的一段算法。

**本篇结构**（和第 3 篇一样）：

```text
第一部分：先写一个「同类高亮器」，跟 EasySpider 完全无关，你自己就能跑
第二部分：再看 EasySpider 是怎么做的，逐行拆真实代码
```

配套可运行示例：**[示例-同类元素匹配/index.html](/resources/easyspider/%E7%A4%BA%E4%BE%8B-%E5%90%8C%E7%B1%BB%E5%85%83%E7%B4%A0%E5%8C%B9%E9%85%8D/index.html)**
（直接用浏览器打开，点商品标题就能看到算法一步步试的过程）

---

---

## 第一部分：先自己写一个「同类高亮器」（与 EasySpider 无关）

### 1. 先看清问题

#### 1.1 场景

一个商品列表页，有 20 个商品。你想把 20 个标题全抓下来。

笨办法：一个个点，点 20 次。

聪明办法：**点 1 个，软件自动猜出另外 19 个**。

#### 1.2 什么叫"同类"？

直觉上：它们是**同一个列表容器里、同一层、同一种标签**的元素。

```text
<ul>
  <li><div><a>商品一</a></div></li>   ← 这 20 个 a 是"同类"，当然<div>也是同类，**<li>也是同类**
  <li><div><a>商品二</a></div></li>
  ...
  <li><div><a>商品二十</a></div></li>
</ul>
```

用 XPath 的话说：**前缀相同，只有末尾的索引不同**。

#### 1.3 输入和输出

| | |
|---|---|
| **输入** | 一个元素的绝对 XPath，比如 `/html/body/div[1]/ul[1]/li[3]/div[1]/a[1]` |
| **输出** | 页面上所有"同类"元素，比如 20 个 `<a>` |

---

### 2. 复习：XPath 的两个基本操作

要写这个算法，只需要会用两样东西。

#### 2.1 绝对 XPath 长什么样

```text
/html/body/div[1]/ul[1]/li[3]/div[1]/a[1]
 │     │      │      │     │      │     └─ 第 1 个 a
 │     │      │      │     │      └─────── 第 1 个 div
 │     │      │      │     └────────────── 第 3 个 li   ★ 区分同类的是它
 │     │      │      └──────────────────── 第 1 个 ul
 │     │      └─────────────────────────── 第 1 个 div
 │     └────────────────────────────────── body
 └──────────────────────────────────────── html
```

`[n]` 是**索引**：在同级同标签的兄弟里排第几个。

#### 2.2 `document.evaluate`：浏览器自带的"按 XPath 找元素"

```js
let result = document.evaluate(
    "/html/body/div[1]/ul[1]/li[3]/div[1]/a[1]",  // ① XPath 表达式
    document,                                      // ② 从哪个节点开始找
    null,                                          // ③ 命名空间（HTML 用不上，给 null）
    XPathResult.ANY_TYPE,                          // ④ 结果类型
    null                                           // ⑤ 复用已有的结果对象（一般给 null）
);
```

> 浏览器 Console 里的 `$x("//div")` 就是它的快捷方式。

#### 2.3 `iterateNext()` 是**游标**，不是数组

这是理解整个算法的关键。

```js
let r = document.evaluate(path, document, null, XPathResult.ANY_TYPE, null);

r.iterateNext();   // 取第 1 个元素
r.iterateNext();   // 取第 2 个元素
r.iterateNext();   // 取第 3 个元素（没有了就返回 null）
```

它像一根**往下拨的指针**：每调一次就吐出下一个，**吐完了返回 `null`**。

所以想数一共有几个，就是：

```js
let n = 0;
while (r.iterateNext()) n++;   // 一直拨到 null 为止
```

💡 **记住这一点**：后面判断"有没有同类"，就是靠"能不能拨出第 2 个"。

---

### 3. 手工版：我自己去掉索引

先不写循环，手动试一次，感受一下。

#### 3.1 一行代码的威力

假设你点中的是第 3 个商品的标题：

```text
/html/body/div[1]/ul[1]/li[3]/div[1]/a[1]     → 匹配 1 个（就它自己）
```

把 `li[3]` 的索引去掉，变成：

```text
/html/body/div[1]/ul[1]/li/div[1]/a[1]        → 匹配 20 个！
                        ↑
                   索引没了 = "所有 li"
```

**一个字符的差别，结果从 1 个变成 20 个。**

#### 3.2 为什么去掉索引就能"套住"一批？

因为 XPath 里 `li` 和 `li[3]` 的含义完全不同：

| 写法 | 含义 |
|---|---|
| `li[3]` | 第 3 个 li —— **精确到某一个** |
| `li` | 所有的 li —— **一整层** |

去掉索引 = 把"精确到某一个"放宽成"这一层全要"。

> 🔑 **这就是整个算法的核心洞察**：
> **尝试去掉某一层的索引，看匹配数会不会变多。变多了，就找到了同类。**

---

### 4. 自动化：把"去索引"写成循环

手工只能试一层。自动化要解决三件事：

```text
① 怎么把一条 XPath 拆成"标签名"和"索引"两部分？
② 怎么把拆开的东西重新拼回一条 XPath？
③ 从哪一层开始试？什么时候停？
```

#### 4.1 ① 拆成两个数组

```js
// 输入：/html/body/div[1]/ul[1]/li[3]/div[1]/a[1]
// 输出：
//   标签名数组 ["html","body","div","ul","li","div","a"]
//   索引数组   [-1,     -1,    1,    1,   3,   1,   1  ]
//                              ↑ -1 表示"这一层没有索引"
```

`-1` 是个**编码技巧**：用 `-1` 统一表示"这一层不加 `[n]`"，这样一个数组就能表达"有的层有索引、有的层没有"。

> 为什么 `html` 和 `body` 是 `-1`？
> 因为求绝对路径的递归到 `body` 就收尾了，直接拼出 `/html/body`，不带索引（EasySpider 就是这么做的，见 §8.1）。

#### 4.2 ② 拼回去

```js
function combineXpath(names, idxs) {
    let p = "";
    for (let i = 0; i < names.length; i++) {
        p = p + "/" + names[i];
        if (idxs[i] !== -1) p = p + "[" + idxs[i] + "]";  // 只有不是 -1 才加索引
    }
    return p;
}
```

配合"把某一位置成 `-1`"，就能生成"去掉那一层索引"的新路径：

```js
let temp = idxs.slice();   // 复制一份（别改原数组！）
temp[4] = -1;              // 去掉 li 的索引
combineXpath(names, temp); // → /html/body/div[1]/ul[1]/li/div[1]/a[1]
```

#### 4.3 ③ 从右往左试

```js
for (let i = idxs.length - 1; i >= 0; i--) {   // 注意：从 length-1 开始，i--
    if (idxs[i] === -1) continue;              // 本来就没索引，跳过
    // ...去掉这一层的索引，试试看
}
```

**为什么从右往左？**

越靠右（越靠近目标元素）的层级，索引越可能是"列表项编号"，去掉它最容易得到一批同类。

而且从右往左能**最快找到"最具体"的那个同类集合**——越往左去掉越宽泛，反而会捞进一堆无关元素。

#### 4.4 ④ 怎么判断"成了"：`iterateNext()` 调两次

```js
let result = document.evaluate(path, document, null, XPathResult.ANY_TYPE, null);

result.iterateNext();                    // 拨第 1 下（结果丢掉不用）
if (result.iterateNext() != null) {      // 还能拨出第 2 下 → 至少 2 个！
    // 找到同类了，停止
}
```

💡 **为什么要调两次？**

因为游标第一次拨出来的一定是"第 1 个"，**能拨出第 2 个才说明"不止一个"**。

这是一个很省事的写法——**不用先把总数数完**，拨两下就知道答案。

---

### 5. 完整可运行例子

#### 5.1 文件在哪

**[示例-同类元素匹配/index.html](/resources/easyspider/%E7%A4%BA%E4%BE%8B-%E5%90%8C%E7%B1%BB%E5%85%83%E7%B4%A0%E5%8C%B9%E9%85%8D/index.html)** —— 双击用浏览器打开即可。

左边是一个模拟的商品列表，右边是运行日志。点任意一个商品标题，程序会：

```text
① 求出它的绝对 XPath
② 拆成「标签名数组」+「索引数组」
③ 从右往左逐层去掉索引，每试一层就打印出：新路径 + 匹配数 + 成功/失败
④ 一旦成功，停止并把所有同类元素高亮
```

#### 5.2 核心代码（带注释）

```js
/* ---------- 工具 1：求绝对 XPath（从 html 一路数下来） ---------- */
function getAbsoluteXPath(el) {
    var parts = [];
    var cur = el;
    while (cur && cur.nodeType === 1) {
        var idx = 1;                      // 自己算第 1 个
        var sib = cur.previousSibling;
        while (sib) {                     // 数前面有几个同标签的兄弟
            if (sib.nodeType === 1 && sib.tagName === cur.tagName) idx++;
            sib = sib.previousSibling;
        }
        // 与 EasySpider 保持一致：递归到 body 就收尾，且 html / body 不带索引
        if (cur === document.body) {
            parts.unshift("body");
            parts.unshift("html");
            break;
        }
        parts.unshift(cur.tagName.toLowerCase() + "[" + idx + "]");
        cur = cur.parentElement;          // 往上爬一层
    }
    return "/" + parts.join("/");
}

/* ---------- 工具 2：拆成「标签名数组」+「索引数组」 ---------- */
function splitXPath(xpath) {
    var segs = xpath.split("/").filter(function (s) { return s !== ""; });
    var names = [], idxs = [];
    for (var i = 0; i < segs.length; i++) {
        var bi = segs[i].indexOf("[");
        if (bi >= 0) {                    // 有索引，如 div[3]
            names.push(segs[i].slice(0, bi));
            idxs.push(parseInt(segs[i].slice(bi + 1).replace("]", ""), 10));
        } else {                          // 没索引，如 body
            names.push(segs[i]);
            idxs.push(-1);                // -1 = 这一层不加索引
        }
    }
    return { names: names, idxs: idxs };
}

/* ---------- 工具 3：拼回 XPath ---------- */
function combineXpath(names, idxs) {
    var p = "";
    for (var i = 0; i < names.length; i++) {
        p = p + "/" + names[i];
        if (idxs[i] !== -1) p = p + "[" + idxs[i] + "]";
    }
    return p;
}

/* ---------- 工具 4：数一数能匹配到几个 ---------- */
function countMatch(path) {
    var r = document.evaluate(path, document, null, XPathResult.ANY_TYPE, null);
    var n = 0;
    while (r.iterateNext()) n++;          // 拨到 null 为止
    return n;
}

/* ---------- 核心：从右往左逐层去索引 ---------- */
function buildPlan(xpath) {
    var sp = splitXPath(xpath);
    var steps = [];
    for (var i = sp.idxs.length - 1; i >= 0; i--) {   // ★ 从右往左
        if (sp.idxs[i] === -1) {                      // 本来就没索引，跳过
            steps.push({ level: i, name: sp.names[i], skip: true });
            continue;
        }
        var temp = sp.idxs.slice();                   // 复制一份，别动原数组
        temp[i] = -1;                                 // 去掉这一层的索引
        var path = combineXpath(sp.names, temp);      // 拼出新路径
        var n = countMatch(path);                     // 数一数
        steps.push({ level: i, name: sp.names[i], path: path, count: n, ok: n >= 2 });
        if (n >= 2) break;                            // ★ 找到同类就停止
    }
    return { names: sp.names, idxs: sp.idxs, steps: steps, xpath: xpath };
}
```

#### 5.3 跑起来的样子

点第 3 个商品标题后，右侧日志大致是这样（中间路径用 `…` 省略）：

```text
【你点的元素】 商品三
【它的绝对 XPath】
  /html/body/div[1]/div[1]/div[1]/div[1]/div[1]/ul[1]/li[3]/div[1]/a[1]

【拆解】
  标签名：[html, body, div, div, div, div, div, ul, li, div, a]
  索引  ：[-1,   -1,   1,   1,   1,   1,   1,   1,  3,  1,   1]

【从右往左逐层去索引】
  第 10 层 a：去掉索引 →
    /html/body/…/li[3]/div[1]/a
    匹配到 1 个  ✗ 只有一个，继续往左试

  第 9 层 div：去掉索引 →
    /html/body/…/li[3]/div/a[1]
    匹配到 1 个  ✗ 只有一个，继续往左试

  第 8 层 li：去掉索引 →
    /html/body/…/ul[1]/li/div[1]/a[1]
    匹配到 6 个  ✓ 成功（≥2）→ 停止，高亮全部同类

>>> 最终结果：共 6 个同类元素已被高亮
```

🔬 **注意看这个例子**：`a` 和 `div` 两层都失败了（因为每个 `li` 里只有一个 `div`、一个 `a`），
真正区分同类的是 **`li` 的索引**。所以要"试三层"才成功——这正是真实网页的常见情况。

---

### 6. 这个最小例子还缺什么

它能演示核心思路，但离"能用"还差得远：

| 缺的东西 | 说明 |
|---|---|
| **没有 iframe 处理** | 元素在 iframe 里时，路径前面会带 `//iframe`，得先剥掉 |
| **只有"高亮"，没有"待选 / 选中"两态** | 真实软件要让用户先**预览**哪些被选中了，再确认 |
| **没有记下原来的样式** | 取消选择时要还原背景色和阴影，得先把原值存起来 |
| **没有参数生成** | 选中之后还要生成"输出参数"（要抓哪些字段） |
| **只用绝对路径** | 页面结构一变就失效；还需要相对路径、倒序索引等多种候选 |
| **深度不一致会失败** | 有的 `li` 里套了 `<span>`、有的没套，XPath 层数不同就匹配不上 |

下面第二部分，看 EasySpider 怎么补上这些。

---

---

## 第二部分：EasySpider 是怎么做的

### 7. 触发链路：什么时候会调用 `findRelated`

`findRelated()` 不是你手动调的，而是**每次选中元素后自动触发**。

入口是 `handleElement()`（`global.js` 第 247-259 行）：

```js
export function handleElement() {
    clearReady();                        // ① 先把上一轮的"待选"清空并还原样式
    if (global.nodeList.length > 1) {    // ② 选了很多个元素
        global.app._data.option = relatedTest();   // 走"手动匹配"（第 7 篇）
        if (global.app._data.option == 100) {
            generateMultiParameters();
        } else {
            generateParameters(0);
        }
    } else if (global.nodeList.length == 1) {      // ③ 只选了 1 个元素
        findRelated();                   // ★ 走"自动匹配"，猜同类
    }
}
```

```text
选中元素（addEl）
      ↓
handleElement()
      ↓
nodeList 里有几个元素？
   ├── 正好 1 个 → findRelated()     ← 本篇：猜同类
   └── 多于 1 个 → relatedTest()     ← 第 7 篇：校验是否同类
```

> 💡 所以：**只选 1 个时才"猜"**。你已经手动选了好几个，就不需要猜了，直接去校验它们是不是同类。

---

### 8. `findRelated()` 逐行拆解

真实代码在 `global.js` 第 1023-1057 行：

```js
export function findRelated() {
    // ① 取出已选元素的 XPath，剥掉 iframe 前缀，拆成数组
    let testPath = global.nodeList[0]["xpath"].replace("//iframe", "").split("/").splice(1);
    //   例如 "/html/body/div[3]/ul[1]/li[7]/div[1]/a[22]"
    //   → ["html","body","div[3]","ul[1]","li[7]","div[1]","a[22]"]
    //   （split 后第 0 项是空串，用 splice(1) 去掉）

    let nodeNameList = [];    // 标签名：["html","body","div","ul","li","div","a"]
    let nodeIndexList = [];   // 索引：  [-1, -1, 3, 1, 7, 1, 22]

    for (let i = 0; i < testPath.length; i++) {
        nodeNameList.push(testPath[i].split("[")[0]);        // "div[3]" → "div"
        if (testPath[i].indexOf("[") >= 0) {                 // 有索引
            nodeIndexList.push(                               // 只留下数字
                parseInt(testPath[i].split("[")[1].replace("]", ""))   // "div[3]" → 3
            );
        } else {
            nodeIndexList.push(-1);                           // 没索引 → -1
        }
    }

    let tempPath = "";
    // ② 从最右往左，挨个把索引置为 -1 试试
    for (let i = nodeIndexList.length - 1; i >= 0; i--) {
        if (nodeIndexList[i] == -1) {     // 本来就没索引，跳过
            continue;
        }
        let tempIndexList = [...nodeIndexList];  // 复制一份（展开语法）
        tempIndexList[i] = -1;                   // 去掉这一层的索引
        tempPath = combineXpath(nodeNameList, tempIndexList);  // 拼回 XPath

        // ③ 数一数能匹配到几个
        let result = document.evaluate(tempPath, document, null, XPathResult.ANY_TYPE, null);
        result.iterateNext();                    // 拨第 1 下（丢弃）
        if (result.iterateNext() != null) {      // 还能拨出第 2 下 → 存在同类！
            global.app.$data.nowPath = tempPath; // ④ 把猜出的 XPath 显示到操作台
            let element = document.evaluate(tempPath, document, null, XPathResult.ANY_TYPE, null).iterateNext();
            global.app.$data.nowAllPaths = getElementXPaths(element);  // ⑤ 给出多种候选路径
            pushToReadyList(tempPath);           // ⑥ 全部加入"待选"
            break;                               // ⑦ 结束，不再往左试
        }
    }
}
```

#### 8.1 三个值得单独说的点

**① `.replace("//iframe", "")`**

元素在 iframe 里时，XPath 前面会带 `//iframe` 前缀。剥掉它才能在当前文档里 `evaluate`。

**② 为什么 `html` / `body` 的索引是 `-1`？**

因为求绝对路径的 `readXPath()`（第 4 篇讲过）递归到 `body` 就收尾了：

```js
if (element == node) {                       // 递归到 body
    if (node == document.body) {
        return pre_xpath + '/html/' + element.tagName.toLowerCase();   // → "/html/body"
    }
}
```

它直接返回 `/html/body`，**这俩都不带索引**。所以 `nodeIndexList` 开头永远是 `[-1, -1, ...]`——
`-1` 分支主要就是为它们准备的。

**③ `[...nodeIndexList]` 展开语法**

`[...arr]` 是"复制一个新数组"。**必须复制**，否则改的是原数组，试完一层就回不去了。

---

### 9. `combineXpath()`：拼回一条路径

`global.js` 第 1115-1124 行：

```js
// 如：["html","body","div"], [-1,-1,2]  →  /html/body/div[2]
export function combineXpath(nameList, indexList) {
    let finalPath = "";
    for (let i = 0; i < nameList.length; i++) {
        finalPath = finalPath + "/" + nameList[i];        // 先拼标签名
        if (indexList[i] != -1) {                          // -1 表示不加索引
            finalPath = finalPath + "[" + indexList[i] + "]";
        }
    }
    return finalPath;
}
```

`-1` 就是整个算法的**编码约定**：一条路径用"标签名数组 + 索引数组"表达，`-1` = "这层不写 `[n]`"。

---

### 10. `pushToReadyList()`：塞进「待选」名单

找到同类之后，不是直接选中，而是先放进 **`readyList`（待选）**，等用户确认。

`global.js` 第 1061-1082 行：

```js
export function pushToReadyList(path) {
    let result = document.evaluate(path, document, null, XPathResult.ANY_TYPE, null);
    let node = result.iterateNext();        // 拨出第 1 个
    while (node) {                          // 一直拨到 null
        // ① 去重：只添加不在"已选中名单"里的元素
        let exist = false;
        for (let o of global.nodeList) {
            if (o["node"] == node) { exist = true; break; }
        }
        if (!exist) {
            global.readyList.push({
                "node": node,                              // 元素本身
                "bgColor": node.style.backgroundColor,     // 记下原背景色
                "boxShadow": node.style.boxShadow == "" || global.boxShadowColor
                             ? "none" : node.style.boxShadow   // ⚠️ 见下方说明
            });
        }
        // ② 加蓝色外发光 —— 这就是"待选"的视觉提示
        node.style.boxShadow = global.boxShadowColor;
        node = result.iterateNext();        // 拨下一个
    }
}
```

> `global.boxShadowColor` = `"blue 0px 0px 5px"`，待选元素会亮一圈蓝边。

⚠️ **一处小瑕疵**

```js
"boxShadow": node.style.boxShadow == "" || global.boxShadowColor ? "none" : node.style.boxShadow
```

按运算符优先级，这行等价于 `(node.style.boxShadow == "" || global.boxShadowColor) ? "none" : ...`。

而 `global.boxShadowColor` 是**恒为真的非空字符串**，所以这个条件**永远是真**——
存进去的 `boxShadow` **恒为 `"none"`**，元素的原阴影其实没被记下来。

后果：本来带阴影的元素，取消待选后阴影会丢失。
（正确写法应该是 `node.style.boxShadow == "" ? "none" : node.style.boxShadow`。）

---

### 11. 走一遍真实 DOM 的逐层尝试

假设你点中的是第 7 个商品标题，它的 XPath 是：

```text
/html/body/div[3]/div[1]/ul[1]/li[7]/div[1]/a[22]
```

算法从右往左试：

| 轮次 | 去掉哪一层 | 生成的 XPath | 匹配数 | 结果 |
|---|---|---|---|---|
| 1 | `a[22]` | `/html/body/div[3]/div[1]/ul[1]/li[7]/div[1]/a` | 1 | ❌ 只有一个 |
| 2 | `div[1]` | `/html/body/div[3]/div[1]/ul[1]/li[7]/div/a[22]` | 1 | ❌ 只有一个 |
| 3 | `li[7]` | `/html/body/div[3]/div[1]/ul[1]/li/div[1]/a[22]` | **20** | ✅ **成功，停止** |

（再往左是被跳过的 `html` / `body`，因为它们的索引是 `-1`。）

```text
结果：
  nowPath     = /html/body/div[3]/div[1]/ul[1]/li/div[1]/a[22]
  nowAllPaths = 该元素的多种候选 XPath（给用户选）
  readyList   = 20 个待选元素，都带上了蓝色外发光
```

---

### 12. `readyToList()`：从「待选」转正

用户点"选中全部"后，待选元素才真正进入 `nodeList`。

`global.js` 第 1094-1111 行：

```js
export function readyToList(step, dealparameters = true) {
    for (let o of global.readyList) {
        global.nodeList.push({
            node: o["node"],                              // 元素
            "step": global.step,                          // 属于第几步操作
            bgColor: o["bgColor"],                        // 原背景色（还原用）
            "boxShadow": o["boxShadow"],                  // 原阴影（还原用）
            xpath: readXPath(o["node"], 1),               // 重新求一次绝对 XPath
            "allXPaths": getElementXPaths(o["node"])      // 多种候选路径
        });
        o["node"].style.backgroundColor = global.selectedColor;  // 上青色 = 已选中
    }
    clearReady();                                    // 清空待选
    if (dealparameters) {                            // 防止"先选子元素再选全部"失效
        generateParameters(0);                       // 生成输出参数（0 = 纯文本）
    }
}
```

💡 **一个细节**：函数签名里有 `step` 参数，但里面用的是 `global.step`——
**传进来的 `step` 实际上没被用到**。这是个无害的小疏漏。

---

### 13. `selectAllElements()`：一键全选按钮

操作台上"选中全部"按钮背后就是它（`global.js` 第 1084-1091 行）：

```js
export function selectAllElements(context = null) {
    global.step++;                          // ① 步数 +1
    readyToList(global.step, false);        // ② 待选转正（false = 暂不生成参数）
    handleElement();                        // ③ 重新处理（此时 nodeList > 1，会走 relatedTest）
    if (context.selectedDescendents) {
        handleDescendents();                // ④ 若之前选过子元素，新节点也要重选
    }
}
```

注意第 ③ 步：转正之后 `nodeList` 变长了，再次 `handleElement()` 就会走**另一个分支**（`relatedTest()`），
从第 6 篇的算法切到第 7 篇的手动匹配校验。

---

### 14. `clearReady()`：清空待选并还原

`global.js` 第 238-244 行：

```js
export function clearReady() {
    for (let node of global.readyList) {
        node["node"].style.boxShadow = node["boxShadow"];   // 还原原来的阴影
    }
    global.readyList.splice(0, global.readyList.length);     // 清空数组
}
```

`handleElement()` 每次开头都会先调它——**先擦干净上一轮的待选**，再重新猜。

---

### 15. 三个设计权衡

#### 15.1 为什么从右往左？

| 方向 | 后果 |
|---|---|
| 从右往左 | 先试最靠目标的一层，命中率高，得到的同类集合**最具体** |
| 从左往右 | 一开始就去掉很外层（如 `div[3]`），会捞进大量无关元素 |

#### 15.2 为什么"匹配数 ≥ 2"就停？

只要变多，就说明找到了一个"能套住多个"的层级，目的已经达到。

继续往左只会**越来越宽泛**，引入噪声（比如把侧边栏的链接也算进来）。

#### 15.3 为什么用绝对路径，而不是 class？

| 方案 | 优点 | 缺点 |
|---|---|---|
| class（如 `//*[@class="title"]`） | 页面结构变了也不怕 | 很多网站用**随机生成的 class**，每次刷新都变 |
| 绝对路径 | 不受 class 影响，稳定 | 页面结构一改就失效 |

EasySpider 选了绝对路径，再用 `getElementXPaths()` 生成**多种候选路径**（`nowAllPaths`）让用户挑，两头都照顾到。

---

### 16. 局限与应对

| 局限 | 原因 | EasySpider 的应对 |
|---|---|---|
| **深度不一致会失败** | 有的 `li` 套了 `<span>`、有的没套，XPath 层数不同 | 靠第 7 篇的 `relatedTest()` 手动匹配兜底 |
| **虚拟列表只匹配可见项** | 页面只渲染当前能看到的几条 | 无解，是页面本身的限制 |
| **结构变化导致失效** | 绝对路径的固有代价 | 提供多种候选 XPath（`nowAllPaths`） |
| **前面动态插入元素会错位** | 索引是"从前往后数"的，前面插一个就全偏了 | 第 4 篇讲的**倒序索引** XPath（`a[last()-n]`） |
| **iframe 内的元素** | 路径带 `//iframe` 前缀 | `findRelated` 里 `replace("//iframe","")` 剥掉 |

---

### 17. 与「手动匹配」的关系

两种匹配，各管一段：

```text
自动匹配 findRelated（本篇）：
   点 1 个  →  猜出所有同类  →  你确认"选中全部"

手动匹配 relatedTest（下一篇）：
   点 2 个以上  →  校验它们是否同类  →  算出最简的公共 XPath
```

| | 自动匹配 | 手动匹配 |
|---|---|---|
| 触发条件 | `nodeList.length == 1` | `nodeList.length > 1` |
| 干什么 | 猜同类 | 验证 + 求公共路径 |
| 本篇/下篇 | 本篇 | 第 7 篇 |

---

### 18. 本篇小结

```text
输入：一个元素的绝对 XPath
思路：从右往左，逐层去掉索引，看匹配数是否 ≥ 2
关键函数：
    findRelated()      拆 XPath → 从右往左试 → 找到就停
    combineXpath()     两个数组拼回一条路径（-1 = 不加索引）
    pushToReadyList()  匹配到的元素进 readyList（待选，蓝色外发光）
    readyToList()      待选转正（进 nodeList，上青色）
    clearReady()       清空待选并还原样式
技巧：iterateNext() 调两次 = 判断"是否 ≥ 2 个"，不用先数总数
输出：readyList（待选集合）→ 用户确认 → nodeList（已选中）
```

一句话：**把"精确到某一个"的索引放宽成"这一层全要"，看能套住几个。**

---

### 19. 动手练习

**① 跑配套示例**

打开 **[示例-同类元素匹配/index.html](/resources/easyspider/%E7%A4%BA%E4%BE%8B-%E5%90%8C%E7%B1%BB%E5%85%83%E7%B4%A0%E5%8C%B9%E9%85%8D/index.html)**，点不同位置的商品标题，观察：

- 为什么有时第 1 层就成功，有时要试 2、3 层？
- 试着改动 HTML（比如给某个 `li` 多加一层 `<span>`），看算法会不会失效。

**② 在 Console 里手动验证**

对着任意列表页，按 F12 打开控制台：

```js
// 先点中一个元素，看它的绝对路径能匹配几个
$x("/html/body/div[3]/div[1]/ul[1]/li[7]/div[1]/a[22]").length   // 1

// 去掉 li 的索引
$x("/html/body/div[3]/div[1]/ul[1]/li/div[1]/a[22]").length      // 20  ← 同类全出来了
```

**③ 思考题**

- 如果列表里第 3 项和第 7 项结构不同（一个套了 `<span>`，一个没有），这个算法会怎样？该怎么补救？
- `pushToReadyList` 里那个 `boxShadow` 的判断，正确的写法应该是什么？

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[05.元素待选与选中：先看鼠标做了什么，再看代码怎么记住它](/easyspider/chapter-05) ｜ 下一篇：[07.手动匹配与相对 XPath：从一行、一列到整个分类区域](/easyspider/chapter-07)
