---
title: "04 · XPath"
description: "easyspider · 元素与任务 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/04.XPath详解.md"
originalUrl: "/originals/easyspider/chapter-04.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 04.XPath：元素定位的通用语言

> EasySpider 的"元素重放"能力，全靠 XPath。
> 不懂 XPath，就无法理解后面的匹配算法。这一篇从零讲透。

---

## 1. 为什么需要 XPath

网页是一棵 **DOM 树**。

想定位其中某个节点，有两种思路。

| 方式 | 例子 | 特点 |
| --- | --- | --- |
| CSS 选择器 | `div.title > a` | 简洁，但不能"往上走" |
| **XPath** | `/html/body/div[3]/a[1]` | 强大，能上能下、能算、能筛 |

XPath 全称 **XML Path Language**。

它把树当成"文件系统路径"来定位。

```text
文件路径： /home/user/docs/a.txt
XPath   ： /html/body/div[3]/a[1]
             很像，对吧？
```

---

## 2. 基本语法（10 分钟够用）

先假设网页结构是这样的：

```html
<html>
  <body>
    <div class="header">标题</div>
    <div class="list">
      <a href="/p1">商品一</a>
      <a href="/p2">商品二</a>
      <a href="/p3">商品三</a>
    </div>
  </body>
</html>
```

常见的表达式和匹配结果：

| 表达式 | 含义 | 匹配结果 |
| --- | --- | --- |
| `/html/body/div` | 绝对路径 | 2 个 div |
| `/html/body/div[2]` | 第 2 个 div | `<div class="list">` |
| `//a` | 任意位置的 a | 3 个 a |
| `//a[1]` | 第 1 个 a | 商品一 |
| `//div[@class='list']` | class 为 list 的 div | list 那个 |
| `//a[@href='/p2']` | href 属性匹配 | 商品二 |
| `//a[contains(@href,'p')]` | href 含 p | 全部 3 个 |
| `//a/text()` | 取文本 | 商品一/二/三 |
| `//div[2]/a[2]` | 组合路径 | 商品二 |

### 两个符号的区别

- `/` ：绝对/子节点（从当前往下走一层）
- `//`：相对/后代节点（往下任意层）

---

## 3. 浏览器里怎么试

打开任意网页，按 F12 → Console，输入：

```js
$x("//a")            // Chrome 内置，$x 就是 XPath 查询
$x("//a/text()")     // 取文本
```

在 Elements 面板按 `Ctrl+F`，也能用 XPath 搜索高亮。

**调 EasySpider 的 XPath 时，这个技巧能省一半时间。**

---

## 4. 在代码里使用 XPath：两种姿势

**A. 浏览器端（JS）** —— 用 `document.evaluate`

```js
let result = document.evaluate(
    "//a",
    document,                 // 在哪个上下文里找
    null,
    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,  // 返回类型
    null
);
for (let i = 0; i < result.snapshotLength; i++) {
    console.log(result.snapshotItem(i));
}
```

**B. 执行器端（Python/Selenium）**

```python
element = browser.find_element(By.XPATH, "//a")          # 找第一个
elements = browser.find_elements(By.XPATH, "//a")        # 找全部
```

**C. 快速提取模式（Python/lxml）**

```python
from lxml import html
tree = html.fromstring(page_source)
rows = tree.xpath("//div[@class='list']/a")   # 快很多！
```

💡 EasySpider 的 `quickExtractable`（快速提取）就是走 lxml 这条路。

因为 lxml 比 Selenium 逐元素查找快得多。

---

## 5. 核心：`readXPath` 的实现原理（逐行拆解）

这是本项目最核心的一段代码。

位置：`Extension/manifest_v3/src/content-scripts/global.js`，第 100–154 行。

它被谁调用？

```js
// addEl 里（global.js 第 194 行附近）
global.nodeList.push({
    ...
    xpath: readXPath(global.NowNode, 1),        // 主 XPath
    "allXPaths": getElementXPaths(global.NowNode) // 候选 XPath 清单
});
```

你每点选一个元素，就调一次。

### 5.1 先看函数签名和三个参数

```js
export function readXPath(element, type = 1, node = document.body) {
```

三个参数各管一件事：

```text
element   目标元素（要给它生成 XPath 的那个）
type      生成策略：
            type=0  允许"抄近路"——有 id 用 id、有唯一 class 用 class
            type=1  不使用 id/class 近路，按父子结构逐层拼路径
                    绝对还是相对，取决于第三个参数 node
                    （nodeList 调用时使用默认 body，保存绝对 XPath）
node      爬到哪一层就停：
            document.body   生成绝对路径（默认）
            某个祖先元素     生成相对于它的路径片段（例如商品块内字段）
```

原代码注释原话：

```text
type=0 代表默认可通过 id 生成 xpath
type=1 代表只能从根节点生成 xpath, nodeList 里必须使用绝对 xpath!
```

### 5.2 完整代码（真实代码，一行未删）

```js
export function readXPath(element, type = 1, node = document.body) {
    let pre_xpath = "";
    // if(global.iframe){
    //     pre_xpath = "//iframe";
    // }
    try {
        if (type == 0) //type=0代表默认可通过id生成xpath
        {
            if (element.id !== "") {
                return pre_xpath + '//*[@id=\"' + element.id + '\"]';
            }
            if (element.className != "") {
                let names = element.className.split(" ");
                for (let i = 0; i < names.length; i++) {
                    if (names[i] != "") {
                        let elements_of_class = node.getElementsByClassName(names[i]);
                        if (elements_of_class.length == 1) {
                            return pre_xpath + '//*[contains(@class, \"' + names[i] + '\")]'
                        }
                    }
                }
            }
        }
        if (element == node) { //递归到body处，结束递归
            if (node == document.body) {
                return pre_xpath + '/html/' + element.tagName.toLowerCase();
            } else {
                return "";
            }
        }
        let ix = 1, //在nodelist中的位置，且每次点击初始化
            siblings = element.parentNode.childNodes; //同级的子元素

        for (let i = 0, l = siblings.length; i < l; i++) {
            let sibling = siblings[i];
            if (sibling == element) {
                return readXPath(element.parentNode, type, node)
                     + '/' + element.tagName.toLowerCase() + '[' + (ix) + ']';
            } else if (sibling.nodeType == 1 && sibling.tagName == element.tagName) {
                //防止多计算了插入的操作台的3个div元素导致定位错误
                if (sibling.id != "wrapperDiv" && sibling.id != "wrapperTdiv"
                    && sibling.id != "wrapperToolkit") {
                    ix++;
                }
            }
        }
    } catch {
        return pre_xpath + "/"
    }
}
```

下面逐段拆。

### 5.3 第一段：`pre_xpath` 是什么

```js
let pre_xpath = "";
// if(global.iframe){
//     pre_xpath = "//iframe";
// }
```

意思是：

> 预留的"路径前缀"。

本来打算：元素在 iframe 里时，路径前面加 `//iframe`。

现在这段被注释掉了——iframe 是靠 `switch_to.frame()` 处理的（见第 17 篇）。

所以 `pre_xpath` 目前**永远是空串**，看到它忽略即可。

### 5.4 插播：先复习一下"递归"是什么

后面全是递归。

不熟的同学先花三分钟看这一节，熟的可以跳过。

#### 一句话定义

> **递归 = 函数在自己里面调用自己。**

但光调自己会无限循环，所以必须配齐两样东西：

```text
① 出口（base case）
   什么条件下不再递归，直接返回结果

② 递进（recursive case）
   每次调用，问题都要比上一次更小
```

#### 最小例子：阶乘

```js
function f(n) {
    if (n == 1) return 1;        // ① 出口
    return n * f(n - 1);         // ② 递进：n 每次减 1
}

f(3);   // 6
```

把它拆开看，递归其实是**两个阶段**：

```text
【下去】一层层问下去，还没算出来
  f(3)  → 3 * f(2)
    f(2)  → 2 * f(1)
      f(1)  → 撞到出口，返回 1

【回来】一层层把结果算出来
      f(1) = 1
    f(2) = 2 * 1 = 2
  f(3) = 3 * 2 = 6        ← 最终结果在最外层才算出
```

💡 记住这个"**下去 / 回来**"的分法。

readXPath 的用法完全一样。

#### 再来一个更贴近的例子：往上数层数

```js
function howDeep(el) {
    if (el == document.body) return 0;        // 出口：到顶了
    return 1 + howDeep(el.parentNode);        // 递进：往上挪一层
}
```

意思是：

```text
问：这个元素上面有几层？
答：如果它已经是 body → 0 层
    否则 → 1 + "爸爸上面有几层"
```

这就是 `readXPath` 爬 DOM 的**骨架**——

只是它往上爬时顺便数了"自己排第几"。

#### 第三个例子：递归"回来"时拼字符串

这是理解 §5.8 的关键：

```js
function buildPath(el) {
    if (el == document.body) return "/html/body";   // 出口
    return buildPath(el.parentNode) + "/" + el.tagName.toLowerCase();
}
```

走一遍：

```text
下去：
  buildPath(a)      → 要等爸爸的结果
    buildPath(div)  → 要等爸爸的结果
      buildPath(body) → 返回 "/html/body"

回来：
  div 那层："/html/body" + "/div" = "/html/body/div"
  a 那层  ："/html/body/div" + "/a" = "/html/body/div/a"
```

看出来了吗？

> **片段是在"回来"的路上拼出来的，最外层最后完成。**

`readXPath` 只是把 `"/" + tagName` 换成 `"/" + tagName + "[" + ix + "]"`。

一模一样的结构。

#### 递归 vs 循环

顺便提一句，`getAbsoluteXPathWithReverseIndex`（§6.1）做的是**同一件事**，但它用的是 `while` 循环 + `unshift`。

```text
递归：下去数排号，回来拼路径
循环：边爬边记，从数组头部插入
```

两种写法都能算出同一条路径。

ES 里两个都实现了——后面 §6 会对照着看。

复习结束，回到 `readXPath` 的主线。

### 5.5 第二段：`type == 0` 的"抄近路"分支

```js
if (type == 0) {
    if (element.id !== "") {
        return pre_xpath + '//*[@id=\"' + element.id + '\"]';
    }
    ...
}
```

意思是：

> 元素自己有 id？直接生成 `//*[@id="xxx"]`，返回，不爬了。

id 在页面里应该唯一，所以这一条路径既短又稳。

```js
    if (element.className != "") {
        let names = element.className.split(" ");
        for (...) {
            let elements_of_class = node.getElementsByClassName(names[i]);
            if (elements_of_class.length == 1) {
                return pre_xpath + '//*[contains(@class, \"' + names[i] + '\")]'
            }
        }
    }
```

意思是：

> 没有 id？那就逐个试 class：
>
> 把 `className`（可能是 `"btn primary active"` 这种多个）按空格拆开，
> 对每个 class 名问一句：**"页面里用这个 class 的元素是不是只有 1 个？"**
> 是 → 生成 `//*[contains(@class, "btn")]`，返回。

💡 关键判断是 `elements_of_class.length == 1`。

> class 不像 id，不保证唯一。
>
> 只有"全页唯一"的 class 才敢拿来当定位符。

这两条近路走不通，才进入下面的"爬楼梯"主逻辑。

💡 为什么 nodeList 里偏偏要用 `type=1`（禁近路）？

> 因为 id / class 可能重复出现在列表的每一行里。
>
> 比如商品列表里每行都有 `id="price"`（不规范但常见）。
>
> 存绝对路径，才能保证"回放时定位的就是当初点的那一个"。

### 5.6 第三段：递归的出口

```js
if (element == node) { //递归到body处，结束递归
    if (node == document.body) {
        return pre_xpath + '/html/' + element.tagName.toLowerCase();
    } else {
        return "";
    }
}
```

意思是：

> 一路向上爬，爬到 `node` 就停。

两种停法：

```text
node 是 document.body：
    返回 "/html/body"   ← 绝对路径的起点
node 是某个循环列表元素：
    返回 ""（空串）      ← 相对路径的起点，从列表往下算
```

🔬 第二种停法就是**相对 XPath**的来源。

后面第 7 篇"手动匹配与相对 XPath"会用到它——

同一个 `readXPath`，换个 `node` 参数，就从"绝对定位"变"列表内定位"。

#### 5.6.1 完整例子：相对于商品块 article，定位第二个 span

这次不从 html/body 开始，而是把一个商品块作为参照元素。假设这份 HTML 中，article 是 body 的直接子元素，也是 body 下第一个 article：

```html
<article id="product">
  <div>
    <span>作者：张三</span>
    <span>Java 入门</span>
  </div>
  <p>￥99</p>
</article>
```

只看元素节点，树形关系如下；我们要定位 E，以 A 为参照起点：

```text
                     A: article#product
                              │
              ┌───────────────┴───────────────┐
              │                               │
           B: div                           C: p
              │
      ┌───────┴───────┐
      │               │
   D: span         E: span
```

先取得两个真实 DOM 对象，再调用源码函数：

```js
const block = document.getElementById("product"); // A：参照元素
const target = block.querySelectorAll("span")[1]; // E：目标元素

const relativePath = readXPath(target, 1, block);
console.log(relativePath); // "/div[1]/span[2]"
```

三个实参分别是：`element=E`、`type=1`、`node=A`。**第三个参数始终是 A；递归时改变的是第一个参数，沿 E → B → A 向上走。**

按代码执行顺序推理：

1. **处理 E。** `type=1`，跳过 id/class 快捷分支。E 不等于参照 A，继续扫描它的父节点 B 的 `childNodes`。
2. `ix` 从 `1` 开始。遇到前面的 D，它也是 SPAN，所以 `ix` 变成 `2`；HTML 中的换行空白是文本节点，不会增加同名元素计数。
3. 遇到目标 E，准备把 `/span[2]` 接在父路径后面。父路径还不知道，所以先调用 `readXPath(B, 1, A)`，E 这一层暂停等待。
4. **处理 B。** B 不等于 A；B 是 A 下第一个 DIV，得到 `ix=1`。准备追加 `/div[1]`，但先调用 `readXPath(A, 1, A)`，B 这一层也暂停。
5. **处理 A。** 现在 `element==node`，命中递归出口。参照元素 A 不是 `document.body`，所以返回空字符串 `""`。A 的标签、id 和它在 body 中的序号都不加入这段路径。
6. **返回 B。** B 拿到父调用返回的 `""`，拼接 `"" + "/div[1]"`，得到 `/div[1]`。
7. **返回 E。** E 拿到 `/div[1]`，再拼接 `/span[2]`，得到最终结果 `/div[1]/span[2]`。

把“向上调用”和“返回时拼接”分开看：

```text
向上调用：
readXPath(E, 1, A)
    → readXPath(B, 1, A)
        → readXPath(A, 1, A)  返回 ""

返回时拼接：
A 返回：""
B 返回："" + "/div[1]"                   = "/div[1]"
E 返回："/div[1]" + "/span[2]"           = "/div[1]/span[2]"
```

这里的 `/div[1]/span[2]` 是 EasySpider 保存的**相对路径片段**。如果直接以 document 为上下文执行这个以 `/` 开头的 XPath，它会从文档根查找，不会自动以 A 为起点。使用它有两种方式：

```js
// 方式一：和参照块的绝对路径拼起来，再从 document 查找。
const blockPath = readXPath(block, 1); // 默认 node=document.body
const absolutePath = blockPath + relativePath;
// "/html/body/article[1]/div[1]/span[2]"

const foundFromDocument = document.evaluate(
    absolutePath, document, null,
    XPathResult.FIRST_ORDERED_NODE_TYPE, null
).singleNodeValue;

// 方式二：在片段前加点，显式以 block 为 XPath 上下文。
const foundFromBlock = document.evaluate(
    "." + relativePath, block, null,
    XPathResult.FIRST_ORDERED_NODE_TYPE, null
).singleNodeValue;
// 执行的是 "./div[1]/span[2]"
```

两个查询都定位到 E。这个例子也说明：`type=1` 本身不代表一定返回绝对路径，决定递归停在哪里的是 `node`。

| 调用 | 结果 | 原因 |
|---|---|---|
| `readXPath(target, 1)` | `/html/body/article[1]/div[1]/span[2]` | 默认停在 body，并以 `/html/body` 为起点 |
| `readXPath(target, 1, block)` | `/div[1]/span[2]` | 停在 article，不包含 article 自己 |
| `readXPath(target, 1, target.parentNode)` | `/span[2]` | 停在 div，只保留 div 内的走法 |
| `readXPath(block, 1, block)` | `""` | 起点就是目标，不需要再向下走 |

本例选 `type=1`，是为了跳过可能提前返回的 id/class 快捷定位，沿结构到达指定参照元素。第三个参数应传目标自身或它的祖先；该函数没有先检查祖先关系，不能把任意一个不相关元素都当作可靠的相对路径起点。

### 5.7 第四段：核心循环——数同名兄弟

```js
let ix = 1,
    siblings = element.parentNode.childNodes;

for (let i = 0, l = siblings.length; i < l; i++) {
    let sibling = siblings[i];
    if (sibling == element) {
        return readXPath(element.parentNode, type, node)
             + '/' + element.tagName.toLowerCase() + '[' + (ix) + ']';
    } else if (sibling.nodeType == 1 && sibling.tagName == element.tagName) {
        if (sibling.id != "wrapperDiv" && sibling.id != "wrapperTdiv"
            && sibling.id != "wrapperToolkit") {
            ix++;
        }
    }
}
```

这段只回答一个问题：

> **我在爸爸的同名孩子里排第几？**

做法是：

```text
ix 从 1 开始
从左到右扫爸爸的所有孩子：
    扫到"我自己"     → 收工：拼路径返回
    扫到"同名兄弟"   → ix++
    扫到其他东西     → 不管
```

两个细节：

```text
① sibling.nodeType == 1
   只数"元素节点"。
   文本节点、注释节点（nodeType=3、8）不算兄弟。

② sibling.tagName == element.tagName
   只数"同名"的。
   XPath 的 a[2] 意思是"第 2 个 a"，不是"第 2 个孩子"。
```

### 5.8 第五段：拼路径的顺序——返回时层层外包

注意这行：

```js
return readXPath(element.parentNode, type, node)
     + '/' + element.tagName.toLowerCase() + '[' + (ix) + ']';
```

意思是：

> **先递归算爸爸的路径，算完再把自己接在后面。**

所以字符串是**递归返回时**一层层包出来的：

```text
网页结构：
  <html>
    <body>
      <div>            ← 第 2 个 div
        <a>商品一</a>
        <a>商品二</a>   ← 目标：第 2 个 a

调用过程（往下钻）：
  readXPath(a)      → 发现 a 排第 2，等爸爸的结果
    readXPath(div)  → 发现 div 排第 2，等爸爸的结果
      readXPath(body) → 撞到出口，返回 "/html/body"

返回过程（往回包）：
  div 那层  → "/html/body" + "/div[2]"  = "/html/body/div[2]"
  a 那层    → 上面 + "/a[2]"            = "/html/body/div[2]/a[2]"
```

一句话：

> **下去的时候只负责数自己的排号，回来的时候一路拼接。**

### 5.9 第六段：`try...catch` 兜底

```js
} catch {
    return pre_xpath + "/"
}
```

意思是：

> 爬的过程中任何一步炸了（比如元素中途被 JS 删了，`parentNode` 变 null），
> 就返回 `"/"`，别让扩展崩溃。

`/` 是个**必然失效**的 XPath——

执行器用它找不到元素，会走候选 XPath 兜底（下一节）。

### 5.10 那个精妙的"屏蔽三个 div"

```js
if (sibling.id != "wrapperDiv" && sibling.id != "wrapperTdiv"
    && sibling.id != "wrapperToolkit") {
    ix++;
}
```

意思是：

> 数兄弟的时候，**跳过 EasySpider 自己插进页面的 3 个 div**。

💡 为什么要跳？

```text
EasySpider 往页面里插了：
  wrapperDiv      高亮虚线框
  wrapperTdiv     鼠标拦截层
  wrapperToolkit  操作台

假设原来 body 下有：  div, div, a
ES 插入后可能变成：    div, wrapperDiv, div, a
                              ↑ 同名(div)！
```

如果不屏蔽，第二个 div 会被数成 `div[3]`。

而目标网站的可没有这层——执行时 `div[3]` 就定位错了。

> **工具插入的元素，污染了工具自己的定位算法。**
>
> 所以生成 XPath 时要主动把自己摘出去。

这是"工具反噬"的经典案例。

---

## 6. 候选 XPath 清单：`getElementXPaths` 全貌

绝对路径 `/html/body/div[2]/a[2]` 很脆弱。

网页稍微改个结构就失效。

所以 EasySpider 还会生成一批**候选 XPath**（global.js 第 49–72 行）：

```js
export function getElementXPaths(element, parentElement = document.body) {
    let paths = [];
    let pre_xpath = "";
    paths.push(readXPath(element, 1, parentElement));     // ① 绝对路径
    paths.push(pre_xpath + "//" + element.tagName.toLowerCase()
        + "[contains(., '" + element.textContent.slice(0, 10).trim() + "')]"); // ② 靠文本
    if (element.id) {
        paths.push(pre_xpath + `id("${element.id}")`);     // ③ 靠 id
    }
    if (element.className) {
        paths.push(pre_xpath + "//" + element.tagName.toLowerCase()
            + "[@class='" + element.className + "']");      // ④ 靠 class
    }
    if (element.name) {
        paths.push(pre_xpath + "//" + element.tagName.toLowerCase()
            + "[@name='" + element.name + "']");            // ⑤ 靠 name
    }
    if (element.alt) {
        paths.push(pre_xpath + "//" + element.tagName.toLowerCase()
            + "[@alt='" + element.alt + "']");              // ⑥ 靠 alt
    }
    paths.push(getAbsoluteXPathWithReverseIndex(element));  // ⑦ 倒序索引路径
    console.log("ALL PATHS: " + paths);
    return paths;
}
```

七条候选，三种来源：

```text
① ⑦  是"算出来"的路径（正序 / 倒序索引）
②     靠元素自身的文本内容
③④⑤⑥ 靠元素自身的属性（有哪个用哪个）
```

运行任务时，第一条失效就用后面的**依次兜底**。

网站改版后任务的存活率，全靠这份清单。

💡 ② 的细节：`element.textContent.slice(0, 10).trim()`

> 只取**前 10 个字符**当定位依据。
>
> 全文可能很长、带换行，全塞进去 XPath 又长又脆。

### 6.1 ⑦ 的完整实现：`getAbsoluteXPathWithReverseIndex`

这是很多同学找不到的一段——

**`pathIndex` 不在 `getElementXPaths` 里**，而在它第 ⑦ 步调用的 `getAbsoluteXPathWithReverseIndex` 里（global.js 第 74–97 行）：

```js
function getAbsoluteXPathWithReverseIndex(element) {
    let pre_xpath = "";
    let path = [];
    while (element && element.nodeType == Node.ELEMENT_NODE) {
        let index = 0;
        for (let sibling = element.nextSibling; sibling; sibling = sibling.nextSibling) {
            // Ignore document type declaration.
            if (sibling.nodeType == Node.DOCUMENT_TYPE_NODE)
                continue;
            if (sibling.nodeName == element.nodeName)
                ++index;
        }

        let tagName = element.nodeName.toLowerCase();
        let pathIndex = (index ? "[last()-" + index + "]" : "");
        path.unshift(tagName + pathIndex);

        element = element.parentNode;
    }
    return pre_xpath + "/" + path.join("/");
}
```

它和 `readXPath` 做的是**同一件事**（生成绝对路径），但思路**镜像相反**：

| | readXPath | getAbsoluteXPathWithReverseIndex |
| --- | --- | --- |
| 循环方式 | **递归**（先钻到顶，回来拼） | **while 循环**（边爬边记） |
| 数兄弟的方向 | 数**前面**几个同名兄弟 → `a[2]` | 数**后面**几个同名兄弟 → `a[last()-1]` |
| 拼路径 | 字符串返回时拼接 | 数组 `unshift` 从头插 |

### 6.2 逐行拆解

第一段：数"我后面还有几个同名兄弟"。

```js
let index = 0;
for (let sibling = element.nextSibling; sibling; sibling = sibling.nextSibling) {
    if (sibling.nodeType == Node.DOCUMENT_TYPE_NODE)
        continue;
    if (sibling.nodeName == element.nodeName)
        ++index;
}
```

意思是：

```text
从我的下一个兄弟开始，一路向右扫：
    是同名的元素节点 → index++
    是文档类型声明   → 跳过
```

扫完，`index` = "我后面还有 index 个同名兄弟"。

第二段：把序号翻译成 XPath 写法。

```js
let pathIndex = (index ? "[last()-" + index + "]" : "");
```

意思是：

```text
index = 0   → 我是最后一个       → 不写索引（a 就是最后一个 a）
index = 1   → 我后面还有 1 个    → a[last()-1]
index = 3   → 我后面还有 3 个    → a[last()-3]
```

对照着看：

```text
正序：  a[1]      a[2]      a[3]      a[4]
倒序：  a[last()-3] a[last()-2] a[last()-1] a[last()]
                                          ↑ index=0，省略
```

第三段：爬一层，记一层。

```js
path.unshift(tagName + pathIndex);
element = element.parentNode;
```

`unshift` 是**从数组头部插入**。

所以越往上爬，新片段越插到前面——

顺序天然就是"html 在前、自己在后"。

最后 `"/" + path.join("/")` 拼成完整路径。

### 6.3 走一遍完整例子

```text
网页：
  <html><body>
    <div><a>1</a><a>2</a></div>
    <div><a>3</a><a>4</a></div>   ← 目标是第 2 个 div 里的第 1 个 a("3")
  </body></html>

爬 a("3")：
  后面有 1 个同名兄弟(a"4") → index=1 → "a[last()-1]"
  path = ["a[last()-1]"]

爬 div：
  后面有 0 个同名兄弟      → index=0 → "div"
  path = ["div", "a[last()-1]"]   ← unshift 插到前面

爬 body / html：没有同名兄弟，pathIndex 都是 ""
  path = ["html", "body", "div", "a[last()-1]"]

结果：/html/body/div/a[last()-1]
```

### 6.4 为什么要倒序索引

普通写法 `a[2]` 是**从前往后**数。

但很多网站会**在列表前面动态插入新内容**（置顶新闻、新消息）：

```text
原来：  新闻1  新闻2  新闻3        目标=新闻2 = a[2]
置顶后：头条  新闻1  新闻2  新闻3   新闻2 变成 a[3]，a[2] 失效！
```

从后往前数就不受"前面加东西"影响：

```text
原来：  新闻2 = a[last()-1]
置顶后：新闻2 还是 a[last()-1]   ✅
```

💡 一句话：

> **正序索引怕"前面插队"，倒序索引怕"后面追加"。**
>
> 两条都存着，执行时互为兜底——这就是 ① 和 ⑦ 同时存在的意义。

---

## 7. 常用 XPath 速查表

| 需求 | 写法 |
| --- | --- |
| 取属性 | `//a/@href` |
| 取文本 | `//div/text()` |
| 包含文本 | `//div[contains(text(),'你好')]` |
| 多个条件 | `//a[@class='x' and @href]` |
| 或 | `//a[@class='x' or @class='y']` |
| 最后一个 | `//li[last()]` |
| 倒数第二个 | `//li[last()-1]` |
| 范围内的 | `//li[position()>2]` |
| 父节点 | `//a/..` |
| 第 n 个匹配 | `(//a)[3]` |
| 任意元素 | `//*[@id='main']` |

---

## 8. 常见坑

💡 **坑 1：`//a[1]` 和 `(//a)[1]` 不同**

前者在每个父节点下取第 1 个 a。

后者取全局第 1 个 a。

💡 **坑 2：大小写**

HTML 里标签通常小写，但源码可能写 `<A>`。

EasySpider 用 `lowercase_tags_in_xpath()` 统一转小写来规避。

💡 **坑 3：iframe**

iframe 内的元素不在主文档树里。

必须先 `switch_to.frame()`。

🔬 **坑 4：动态渲染**

SPA 网站 DOM 是 JS 生成的。

页面刚加载时 `//a` 可能什么都搜不到。

需要配合"等待元素出现"（WebDriverWait）。

---

## 9. 本篇小结

```text
XPath = 用路径定位 DOM 节点
/  绝对；  // 任意后代
[ ] 筛选；  @ 属性；  text() 文本

readXPath(element, type, node)：
  type=0 先抄近路（id / 唯一 class），type=1 只爬绝对路径
  node 决定停在哪：body→绝对路径，循环列表→相对路径
  核心循环：从左扫兄弟，数同名节点 ix；跳过自己插的 3 个 wrapper
  递归：下去数排号，回来拼路径
  catch 兜底返回 "/"，让候选 XPath 接手

getElementXPaths：7 条候选（绝对/文本/id/class/name/alt/倒序索引）
pathIndex 在第 ⑦ 条 getAbsoluteXPathWithReverseIndex 里：
  数"后面"几个同名兄弟 → a[last()-n]，防"前面插队"
```

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[03.Chrome 扩展开发（Manifest V3）从零讲透](/easyspider/chapter-03) ｜ 下一篇：[05.元素待选与选中：先看鼠标做了什么，再看代码怎么记住它](/easyspider/chapter-05)
