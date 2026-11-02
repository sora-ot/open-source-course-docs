# 10.选中子元素与预览表：先用 DFS 生成字段，再转换成表格

第 8 篇已认识字段对象与示例值，上一篇又手工走过 DFS 和 BFS，写出了栈与队列的示例代码。现在把两部分接起来，将栈式 DFS 放回 EasySpider：选中商品块后，怎样把块里的标题、链接、图片、价格和数量输入项变成采集字段？

这一篇先沿 `handleDescendents(0)` 的“应选尽选”模式讲解，分别观察**只选中一个块，以及选中多个块**。后面再补上 `handleDescendents(2)` 的“所有块共同元素”模式。每个模式都先把原理和例子讲清楚，再按执行顺序拆源码。等两种子元素模式都讲完，最后统一分析 `generateValTable()`：先给输入与输出，再看行数、缺值和每个格子的生成过程。

## 第一部分：先看商品块，手工决定应该出现哪些字段

### 1. 两张商品卡片，信息分布在哪里

假设页面上有两张卡片。第一张是 Java 书，第二张是 Python 书，第二张还多了一条促销提示：

```text
Java 商品块                         Python 商品块
├── 链接：Java 入门                  ├── 链接：Python 入门
│   └── 标题文字的包装元素             │   └── 标题文字的包装元素
├── 图片：java.jpg                   ├── 图片：python.jpg
├── 价格：￥99                       ├── 价格：￥88
└── 数量输入项：1                     ├── 数量输入项：2
                                    └── 促销提示：限时促销
```

标题的包装元素里面还有一个更深的文字元素，这里把它作为链接整体内容的一部分。链接本身已经能提供完整标题，后面会看到源码怎样避免再往这条包装分支里建立重复字段。

我们把每张卡片的最外层称为“块”。用户正式选中的是块，而不是先把标题、图片、价格分别加入选择名单。

### 2. 情况一：只选中 Java 这一个块

选中 Java 卡片，点击“选中子元素”，我们希望预览中出现：

| 商品 | 链接文本 | 链接地址 | 图片地址 | 价格文本 | 数量值 |
|---|---|---|---|---|---|
| Java 书 | Java 入门 | `/java` | `java.jpg` | ￥99 | 1 |

这里有五个字段，但不表示有五个已选块。一个块提供一行数据，里面的不同内容提供不同字段。

链接要拆成两列：一列是文字，一列是地址。纯粹包住其他元素的容器，如果自己没有直接文本，就不必额外建立一列“整块文字”。

还要知道每个字段在页面上的位置。当前只有一个块，源码为字段保存从文档根开始的绝对路径，能够直接定位 Java 卡片中的具体元素。

### 3. 情况二：正式选中 Java、Python 两个块

这一次先让两个商品块都进入已选名单，再点击“选中子元素（应选尽选）”。我们按上一篇的 DFS 顺序逐块检查。

先走完 Java 块，建立前面的五个字段。再走 Python 块：对应位置已经有字段时，就把 Python 的值追加到该字段；到最后遇见之前没有的促销提示，就新增一列。

最后希望看到：

| 商品 | 链接文本 | 链接地址 | 图片地址 | 价格文本 | 数量值 | 促销文本 |
|---|---|---|---|---|---|---|
| Java 书 | Java 入门 | `/java` | `java.jpg` | ￥99 | 1 | 空白 |
| Python 书 | Python 入门 | `/python` | `python.jpg` | ￥88 | 2 | 限时促销 |

**应选尽选允许后面的块带来新字段。** 促销只在第二个块中出现，也会被加入；第一个块对应位置没有值，预览补空白。

这部分的应选尽选不求路径交集；后面的第五、六部分再解释怎样只保留所有已选块中都存在的位置。

### 4. 两个块里的价格，怎样知道应该放进同一列

不用变量名，先把规则说清楚：分别以当前块作为起点，记录到元素的走法；走法相同，就暂时当作同一个字段位置。

| 内容 | Java 块内的走法 | Python 块内的走法 | 处理结果 |
|---|---|---|---|
| 链接 | 第一个链接 | 第一个链接 | 共用文本、地址两列 |
| 图片 | 第一张图片 | 第一张图片 | 共用图片地址列 |
| 价格 | 第一个段落 | 第一个段落 | 共用价格文本列 |
| 数量 | 第一个输入项 | 第一个输入项 | 共用数量值列 |
| 促销 | 没有 | 第一个强调元素 | 第二块新增一列 |

这里判断的是结构位置，不是理解文字的业务含义。两块都存在第一个段落，并不保证它们都表示价格。

如果第二块在价格前插入另一个段落，原先的“第一个段落”就换了内容，实际字段对齐也会受到影响。后面读到路径比较时，要一直记着这个前提。

### 5. 手工推演时，把三种记录分开

| 记录 | 本例保存什么 | 是否改变已选块数量 |
|---|---|---|
| 正式选中的块 | Java 块，或者 Java、Python 两个块 | 这是已选名单本身 |
| 要采集的字段 | 链接文本、链接地址、图片地址、价格、数量、促销 | 不增加已选块 |
| 字段的示例值 | 各块在该字段位置提供的值 | 不增加已选块 |

点击“选中子元素”之后，软件主要更新字段与预览，并不是把所有后代都塞进已选块名单。先把这个区别讲清楚，再进入代码。

## 第二部分：给同一个案例建立 DOM 与路径模型

### 6. 用这份 HTML 对应刚才的卡片

以下是教学模型，可以保存成 HTML 在浏览器里观察。后面所有路径和数量都按它推演，不代替真实商品页面的 DOM。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>商品块示例</title></head>
<body>
<section>
  <article id="java">
    <a href="/java"><span>Java <em>入门</em></span></a>
    <img src="java.jpg">
    <p>￥99</p>
    <input value="1">
  </article>
  <article id="python">
    <a href="/python"><span>Python <em>入门</em></span></a>
    <img src="python.jpg">
    <p>￥88</p>
    <input value="2">
    <strong>限时促销</strong>
  </article>
</section>
</body>
</html>
```

`a` 里的 `span` 包住标题，其中 `em` 包住“入门”。两个块的根都是 `article`，Java、Python 的绝对路径分别为：

```text
Java 块：  /html/body/section[1]/article[1]
Python 块：/html/body/section[1]/article[2]
```

### 7. 同一个元素有两种路径视角

Java 块中的价格元素是 `p`：

```text
从文档根开始：/html/body/section[1]/article[1]/p[1]
从 Java 块开始：/p[1]
```

Python 块中的价格对应：

```text
从文档根开始：/html/body/section[1]/article[2]/p[1]
从 Python 块开始：/p[1]
```

绝对路径不同，块内片段相同。因此可以把两块的价格填入同一列。

| 当前节点 | 相对于自己的商品块，`readXPath(nd, 1, tnode)` 返回什么 |
|---|---|
| 块自身 `article` | `""` |
| 链接 `a` | `/a[1]` |
| 标题包装 `span` | `/a[1]/span[1]` |
| 图片 `img` | `/img[1]` |
| 价格 `p` | `/p[1]` |
| 数量 `input` | `/input[1]` |
| Python 块的促销 `strong` | `/strong[1]` |

第一项空字符串表示块自身，因为递归到本次块就停止。字段里的 `/p[1]` 是供调用方组合使用的块内路径片段；单独把它当作从文档根执行的 XPath，并不会自动定位到当前商品块。

## 第三部分：沿着一次点击，逐句拆解 handleDescendents(0)

源码仍使用第 7 篇引用的 [global.js](../../ElectronJS/EasySpider_zh/content-scripts/global.js)。搜索函数名 `handleDescendents` 即可找到；下面按原执行顺序分段列出应选尽选经过的代码。

### 8. 入口：操作台按钮把 mode 设为 0

操作台的处理函数是：

```js
selectDescendents: function (e, mode = 0) {
    handleDescendents(mode);
    this.mode = mode;
}
```

`e` 是界面事件，`mode` 默认是 0。按钮没有另外指定模式时，就调用 `handleDescendents(0)`。

这里的单块、多块取决于 `global.nodeList.length`，不是两种不同的 `mode`。**两种情况都使用应选尽选，区别在于遍历多少个块、字段保存哪种路径，以及后续值是否需要合并。**

### 9. 先读取参数编号，再清旧参数

```js
function handleDescendents(mode = 0) {
    let n = 1;
    chrome.storage.local.get({parameterNum: 1}, function (items) {
        n = items.parameterNum;
        clearParameters();
        global.app._data.selectedDescendents = true;
        let ndText, ndPath, ndAllPaths;
        // 本节省略 mode == 2 的分支；先沿 mode == 0 进入 else，后文再拆 mode 2。
        // 后续代码按实际执行顺序分段列出。
    });
}
```

上面的框架省略了其他模式的实现；以下代码继续拆解回调中的 `else` 分支。

| 语句 | 本次执行的意义 |
|---|---|
| `mode = 0` | 默认应选尽选 |
| `let n = 1` | 先准备字段编号变量 |
| `chrome.storage.local.get({parameterNum: 1}, ...)` | 异步读取参数编号；缺失时默认从 1 开始 |
| `n = items.parameterNum` | 用实际读到的编号作为起点 |
| `clearParameters()` | 清旧字段、旧预览、参数节点记录，并复位相关标志 |
| `selectedDescendents = true` | 清理后重新标记：本次已启用子元素采集 |
| `let ndText, ndPath, ndAllPaths` | 准备本轮节点的直接文本、块内路径和其他定位写法 |

**`clearParameters()` 保留 `nodeList` 中的两个已选块，清除的是原先针对整块内容建立的采集参数。接下来，程序会遍历这两个块的内部元素，为标题、链接、图片等内容重新建立采集参数。也就是说，已选块不变，采集字段从整块内容细化为块内各项内容。**

它先恢复旧参数节点记录中的阴影，再清空 `outputParameterNodes`、`outputParameters` 和 `valTable`。

举个清除前后的例子：假设已经选中 Java、Python 两个商品块，并按“整块文本”生成了采集参数。为方便阅读，下面省略 HTML 排版带来的空白，并用“整块文本”代替实际参数名。

**清除前：两个块共用一个“整块文本”字段，每个块提供一个示例值。**

| 商品块（行说明） | 整块文本 |
|---|---|
| Java 块 | Java 入门 ￥99 |
| Python 块 | Python 入门 ￥88 限时促销 |

这里采集的是 `article.textContent`，所以标题、价格、促销文字都放在同一个字段里；图片的 `src` 和输入项的 `value` 不属于文本内容，不会出现在这一列中。“商品块”这一列只是说明每行来自哪里，不是额外的采集字段。

此时几份记录可以简写为（不是完整对象）：

```text
nodeList             = [Java 块记录, Python 块记录]
outputParameterNodes = [Java 块的参数节点记录, Python 块的参数节点记录]
outputParameters     = [整块文本字段，内含 Java、Python 两个示例值]
valTable             = [["Java 入门 ￥99", "Python 入门 ￥88 限时促销"]]
```

`valTable` 按字段保存值：外层只有一个数组，表示只有一列；内层的两个值对应两个商品块。

**调用 `clearParameters()` 后、尚未开始遍历时：**

```text
nodeList             = [Java 块记录, Python 块记录]  // 仍保留两个已选块
outputParameterNodes = []
outputParameters     = []
valTable             = []
```

随后再遍历两个块，建立链接文本、链接地址、图片地址、价格文本、数量值和促销文本六个字段，预览就变成前面展示的两行、多列的表格。**清除的是旧字段及其示例值，两个商品块仍然是生成新字段的起点。**

这些操作在存储回调中发生，所以 `handleDescendents()` 返回时，不等于字段已经生成完成。下面的推演都指回调开始执行之后的状态。

### 10. 外层循环挑选块，内层循环沿 DFS 访问元素

```js
for (let num = 0; num < global.nodeList.length; num++) {
    let tnode = global.nodeList[num]["node"];
    let stack = new Array(); //深度优先搜索遍历元素
    stack.push(tnode); //从此节点开始
    while (stack.length > 0) {
        let nd = stack.pop(); // 挨个取出元素
```

逐行对应本例：

1. `num = 0` 表示先处理 Java 块。多块时处理完它，再进入 `num = 1` 的 Python 块。
2. `tnode = nodeList[num].node` 取出本轮的块根。
3. `new Array()` 建立本块自己的待办栈；每次换块都重新建栈。
4. `stack.push(tnode)` 把块自身作为第一个待办节点。
5. `while` 在栈不为空时继续；栈空表示本块遍历结束。
6. `stack.pop()` 取出当前节点 `nd`，随后对它做路径、文本、字段处理。

**`num` 怎样变化？它由外层 `for` 循环控制，每处理完一个块才加 `1`。**

```js
for (let num = 0; num < global.nodeList.length; num++) {
    // 内层 while 在这里完整遍历 nodeList[num] 这个块。
    // 遍历这个块的各个子元素时，num 不变。
} // 本块遍历结束后，执行 num++，再判断是否还有下一个块。
```

本例 `nodeList = [Java 块记录, Python 块记录]`，长度为 `2`，执行过程如下：

| 执行阶段 | `num` | 当前块与节点 | 是否进入本轮块遍历 |
|---|---:|---|---|
| 初始化，检查 `0 < 2` | 0 | `nodeList[0]`，Java 块 | 是 |
| 内层 DFS 遍历 Java 块 | 始终为 0 | 块根、链接、图片、价格、数量输入项等 | 持续处理同一个块 |
| Java 块遍历完，执行 `num++`，检查 `1 < 2` | 1 | `nodeList[1]`，Python 块 | 是 |
| 内层 DFS 遍历 Python 块 | 始终为 1 | 块根、链接、图片、价格、数量输入项、促销提示等 | 持续处理同一个块 |
| Python 块遍历完，执行 `num++`，检查 `2 < 2` | 2 | 没有第三个块 | 否，外层循环结束 |

所以，**`num` 不是子元素编号，也不是字段编号，而是当前已选块在 `nodeList` 中的下标。** Java 块虽然生成了五个字段，这五个字段的示例值都写 `num: 0`；Python 块无论复用旧字段还是新增促销字段，当前块提供的示例值都写 `num: 1`。

例如，两个块遍历完后，价格字段与促销字段的示例值分别是：

```js
// 同一价格字段：两个值来自不同块，分别放到预览的第一行、第二行
价格字段.exampleValues = [
    {num: 0, value: "￥99"},
    {num: 1, value: "￥88"}
];

// 促销只在 Python 块出现，所以只有第二行的值
促销字段.exampleValues = [
    {num: 1, value: "限时促销"}
];
```

这里用含义表示字段名。保存到示例对象中的 `num` 是当时的块下标；外层循环之后递增 `num`，不会把已经保存的 `num: 0` 改成 `num: 1`。生成预览时，`num: 0` 对应第一行，`num: 1` 对应第二行，促销列的第一行留空。

如果只选了一个块，整个块的遍历期间 `num` 都是 `0`；遍历完后递增为 `1`，因为 `1 < 1` 不成立，循环立即结束。

这正是上一篇的栈式 DFS，只是“记下名字”被换成了多步字段处理。

注意一开始访问的是块自身，不是直接跳到它的孩子。是否建立字段，要由后面的内容条件决定。

### 11. 先检查剪枝：链接下面的 span 连同后代一起跳过

先说明为什么要跳过。本例的标题链接是：

```html
<a href="/java"><span>Java <em>入门</em></span></a>
```

这里的 `span` 和 `em` 用来包装、排版标题文字。我们希望采集的是完整标题“Java 入门”和链接地址 `/java`，而 `a` 本身就能提供这两项内容：`a.textContent` 会把内部所有文字合起来，得到“Java 入门”；`a.getAttribute("href")` 则得到 `/java`。

如果处理完 `a` 后，还继续为里面的文字元素建立字段，就会重复采集标题中的内容：

| 元素 | 若继续处理，会采集什么 | 与链接文本的关系 |
|---|---|---|
| `a` | 完整链接文本“Java 入门”，以及地址 `/java` | 已经提供完整标题 |
| `span` | 直接文本“Java” | 已包含在完整标题中 |
| `em` | 直接文本“入门” | 已包含在完整标题中 |

因此，源码在遇到**直接位于 `a` 下的 `span`** 时，跳过这个 `span` 及其后代，避免把已由链接文本提供的内容再拆成重复字段。这里的“剪枝”，就是停止继续遍历这条分支。先理解这个目的，再看判断条件：

```js
if (nd.parentNode.tagName == "A" && nd.tagName == "SPAN") {
    continue; //对A标签内的SPAN元素不进行处理,剪枝，此时子元素根本不加入stack，即实现了此功能
}
```

条件同时要求：当前节点是 `SPAN`，并且它的直接父节点是 `A`。

在本例中，访问顺序开始为：

```text
article → a → span
```

到 `span` 时条件成立，执行 `continue`，直接进入下一轮 `while`。本轮的路径计算、字段处理以及末尾的孩子入栈都不执行，所以 `span` 下面的 `em` 也不会入栈。

```text
实际继续访问：article → a → span（跳过整支）→ img → p → input
不会单独处理：em
```

跳过这条分支后，链接文本仍然包含“入门”：剪枝只影响后续遍历，不会从先前读取的 `a.textContent` 中删除后代文字。

这个判断只覆盖直接位于 `A` 下的 `SPAN`。其他层级或其他标签不一定被跳过，不能理解成“链接下面的所有后代都不会产生字段”。

### 12. 计算块内路径，再检查字段是否已经存在

**在本例的多块遍历中，处理 `nodeList` 的第一个块时，各节点的块内路径都尚未记录，`index` 均为 `-1`，需要从空的 `outputParameters` 开始为可采集内容建立字段；从第二个同类型块开始，若当前路径尚未出现，`index = -1`，需要新建字段，否则 `index` 就是该路径对应字段在 `outputParameters` 中的索引，用于追加当前块的示例值。**

用两个商品块中的 `a` 链接走一遍，就能看清“没记录过就新建，记录过就追加值”的过程。本例选中了两个块，因此字段保存的是块内路径。

**第一次：访问 Java 块的 `a`，还没有对应字段。**

刚执行过 `clearParameters()`，所以初始状态是：

```js
outputParameters = [];
```

此时 `num = 0`，Java 链接的 `ndPath = "/a[1]"`。查找前先设 `index = -1`；由于数组为空，`for` 循环一次也不执行，没有机会把 `index` 改成其他值，所以查找结果仍是 `-1`，表示“没有对应字段”。

后面的新建分支会为这个链接建立两个字段：链接文本、链接地址，并把 Java 链接的值放入各自的 `exampleValues`。

新建后的记录可以简写成下面这样（省略其他属性，字段名用含义表示）：

```js
outputParameters = [
    {
        name: "链接文本",
        relativeXPath: "/a[1]",
        exampleValues: [{num: 0, value: "Java 入门"}]
    },
    {
        name: "链接地址",
        relativeXPath: "/a[1]",
        exampleValues: [{num: 0, value: "/java"}]
    }
];
```

注意：一个 `a` 元素对应两个采集字段，它们的路径都是 `/a[1]`，文本字段在前，地址字段紧跟在后。

**第二次：访问 Python 块的 `a`，对应字段已经存在。**

Java 块遍历完后，数组中已有五个字段。只保留字段名与路径，结构如下（实际对象还包含 `exampleValues` 等属性）：

```js
outputParameters = [
    {name: "链接文本", relativeXPath: "/a[1]"},     // 下标 0
    {name: "链接地址", relativeXPath: "/a[1]"},     // 下标 1
    {name: "图片地址", relativeXPath: "/img[1]"},   // 下标 2
    {name: "价格文本", relativeXPath: "/p[1]"},     // 下标 3
    {name: "数量值",   relativeXPath: "/input[1]"}  // 下标 4
];
```

接下来处理 Python 块，此时 `num = 1`。Python 链接的绝对路径虽然不同，但相对于自己的商品块，仍是 `/a[1]`。

**每访问一个节点，都会重新从 `index = -1` 开始查找。** 这次数组已有内容，循环会执行；当 `i = 0` 时，发现 `outputParameters[0].relativeXPath` 正好是 `/a[1]`，于是执行 `index = 0`，随后 `break`。因此 `index` 指向已有的链接文本字段，地址字段则在 `index + 1` 的位置。

同理，之后访问 Python 的价格时，查找 `/p[1]`，结果是 `index = 3`；访问促销提示时，查找 `/strong[1]`，已有五个字段都不匹配，`index` 仍为 `-1`，需要新增促销字段。

以 Python 链接为例，后面的已有字段分支不再新建链接字段，而是执行：

```js
// index = 0，num = 1，nd 是 Python 块中的 a
// 把 Python 的标题追加到已有“链接文本”字段的示例值数组
// nd.textContent 在本例中是 "Python 入门"
global.outputParameters[index].exampleValues.push({
    num: num,
    value: nd.textContent
});

// 把 Python 的地址追加到紧随其后的“链接地址”字段的示例值数组
// nd.getAttribute("href") 在本例中是 "/python"
global.outputParameters[index + 1].exampleValues.push({
    num: num,
    value: nd.getAttribute("href") == null ? "" : nd.getAttribute("href")
});
```

追加后，这两个字段的示例值分别是：

```text
链接文本.exampleValues = [{num: 0, value: "Java 入门"}, {num: 1, value: "Python 入门"}]
链接地址.exampleValues = [{num: 0, value: "/java"},     {num: 1, value: "/python"}]
```

因此，**第一次记录的是“这个位置要采集哪些字段”，后续记录的是“另一个块在这些字段上提供什么值”**。Python 的值追加到已有字段的 `exampleValues` 中，靠 `num = 1` 标明它来自第二个块；既不会覆盖 Java 的值，也不会再增加两列。这一节的查找代码只负责确定 `index`，具体的新建、追加操作分别在第 15、17 节展开。

再看源码如何得到上面的查找结果：

```js
ndPath = readXPath(nd, 1, tnode);
ndAllPaths = getElementXPaths(nd, tnode);
let index = -1;
for (let i = 0; i < global.outputParameters.length; i++) {
    if (global.outputParameters[i]["relativeXPath"] == ndPath) {
        index = i;
        break;
    }
}
```

其中两个路径调用可以这样理解：

```text
nd = Java 的价格 p，tnode = Java 块
readXPath(nd, 1, tnode) → /p[1]
getElementXPaths(nd, tnode) → 该元素的多种定位写法
```

`getElementXPaths()` 中的路径并不保证全都限定在本块内；这里用来对齐字段的是 `ndPath`，不是整个 `ndAllPaths` 数组。

接着从 `outputParameters` 开头逐项寻找：如果某项的 `relativeXPath` 等于本次 `ndPath`，就保存它的下标并 `break`；没有找到则保持 `index = -1`。

再把本例中几个节点的查找结果放在一起对照：

| 遍历时刻 | 本次 `ndPath` | 已有字段里的对应项 | `index` |
|---|---|---|---:|
| Java 的链接 | `/a[1]` | 尚未建立 | -1 |
| Java 的价格 | `/p[1]` | 尚未建立 | -1 |
| Python 的链接 | `/a[1]` | 链接文本列，后面紧跟地址列 | 0 |
| Python 的价格 | `/p[1]` | 价格列 | 3 |
| Python 的促销 | `/strong[1]` | 尚未建立 | -1 |

这里的 `index` 是字段数组下标；`num` 是已选块下标；两者不要混用。

### 13. 读取直接文本，按元素粒度生成字段

这一步是为了让普通文本字段按更细的元素粒度生成：分别采集各元素自身直接拥有的文字，避免父容器把子元素的文字合起来，再额外生成一个组合字段。

例如，页面上显示的价格是“￥50”，但 HTML 把货币符号和金额放在两个不同的元素里：

```html
<div class="price"><span>￥</span><span>50</span></div>
```

对应的结构是：

```text
父元素 div：整体文本为“￥50”
├── 第一个 span：直接文本为“￥”
└── 第二个 span：直接文本为“50”
```

**如果每访问一个元素，都用 `nd.textContent` 读取全部后代文本：**父元素会得到“￥50”，两个子元素分别得到“￥”和“50”。若按这些非空文本建立字段，就会生成三个字段，其中父元素的“￥50”又包含了两个子元素的内容。

**按本节源码，只读取当前元素直接拥有的文本：**结果如下。

| 当前元素 | 读取全部后代文本 | 只读取直接文本（本节源码） | 本节做法是否生成文本字段 |
|---|---|---|---|
| 父元素 `div` | `￥50` | `""` | 不生成，文字都在子元素里 |
| 第一个 `span` | `￥` | `￥` | 生成货币符号字段 |
| 第二个 `span` | `50` | `50` | 生成金额字段 |

为什么父元素的直接文本为空？因为它的两个直接孩子都是 `span` **元素节点**，没有直接属于 `div` 的**文本节点**。“￥”和“50”分别属于两个 `span`，不在 `div` 这一层读取。

因此，最终生成的字段可以对照为（字段名按含义表示）：

```text
读取全部后代文本：组合价格字段“￥50” + 货币符号字段“￥” + 金额字段“50”
只读取直接文本：                     货币符号字段“￥” + 金额字段“50”
```

**这样就不会额外出现一个来自父元素的“￥50”字段，采集粒度保留在“￥”和“50”各自所在的元素上。** 这里的粒度取决于 HTML 结构：如果“￥50”本来就是同一个元素的直接文本，仍会作为一个字段采集。

理解这个差别后，再看源码怎样筛选直接文本：

```js
ndText = "";
let ndContents = nd.childNodes;
for (let i = 0; i < ndContents.length; i++) {
    if (ndContents[i].nodeType === 3) { // if it's a text node
        ndText += ndContents[i].textContent.trim(); // add its content to the string
    }
}
ndText = ndText.replace(/\s+/g, ''); // remove any whitespace characters
```

1. `ndText = ""` 清空上一节点的结果。
2. `nd.childNodes` 包含直接孩子中的元素节点和文本节点。
3. `nodeType === 3` 只接受直接文本节点。
4. `trim()` 去掉每段直接文本两侧的空白。
5. 最后的 `replace(/\s+/g, '')` 去掉剩余空白字符。

| 当前节点 | `textContent` 会得到什么 | 这里算出的 `ndText` |
|---|---|---|
| Java 块 `article` | 标题、价格以及缩进换行等 | `""`，直接文本只有缩进空白 |
| 链接 `a` | `Java 入门` | `""`，直接孩子是 span |
| 价格 `p` | `￥99` | `￥99` |
| 图片 `img` | `""` | `""` |
| 输入项 `input` | `""` | `""` |
| 促销 `strong` | `限时促销` | `限时促销` |

链接、图片、输入项在后面有专门取值分支，因此这里的 `ndText` 为空不表示它们不能建立字段。

对于普通文本节点，删除所有空白会改变原文，例如“限时 促销”会变成“限时促销”。这是当前实现的取值规则，不是保留排版后的完整文字。

### 14. 记录参数节点与阴影：视觉标记有自己的条件

```js
let unique_index = ndPath;
if (ndText != "" || nd == tnode) {
    if (mode == 0 || (mode == 1 && (index != -1 || num == 0))) { //如果不是应选尽选，则只添加和第一个元素相同类型的子元素
        global.outputParameterNodes.push({
            "node": nd,
            "unique_index": unique_index,
            "boxShadow": nd.style.boxShadow == "" || global.boxShadowColor ? "none" : nd.style.boxShadow
        });
        nd.style.boxShadow = global.boxShadowColor;
    } else if (mode == 1 && nd == tnode) { //最外层元素标记一下
        nd.style.boxShadow = global.boxShadowColor;
    }
}
```

`unique_index = ndPath` 用块内位置作为关联标识。不同块的对应元素会共享这个标识；链接文本和链接地址也会使用同一节点的标识。

只有 `ndText` 非空，或者当前节点就是块根，才进入第一层视觉处理。在应选尽选下，`mode == 0` 恒为真，于是记录节点并设置蓝色阴影。

| 本例节点 | 满足视觉条件吗 | 会建立字段吗 |
|---|---|---|
| 块根 article | 是，`nd == tnode` | 不会，本例没有直接文本，也不是特殊标签 |
| 链接 a | 否，本例没有直接文本 | 会，专门生成链接文本、地址 |
| 图片 img | 否 | 会，专门读取 src |
| 价格 p | 是，有直接文本 | 会 |
| 输入项 input | 否 | 会，专门读取 value 属性 |

**高亮记录与采集字段不是同一张名单。** 不要用“每个有字段的节点都一定在这一步加阴影”解释源码。

`boxShadow` 的保存表达式中，`|| global.boxShadowColor` 是一个非空字符串条件，当前通常会把恢复值记成 `"none"`。因此恢复效果以实际记录为准，不能假定总能还原网页原有阴影。

### 15. index 为 -1：按节点内容建立新字段

下面是新建字段的完整分支。虽然保留了原源码中对 mode 1 的判断，但本节取 `mode = 0`，所以 `!(mode == 1 && num > 0)` 始终成立，不限制后面的块新增字段。

```js
if (index == -1) { //从第二个节点开始，只插入那些不在参数列表中的元素，根据xpath进行寻址
    //如果当前节点除了子元素外仍然有其他文字或者该元素是图片/表单项，加入子元素节点
    if (!(mode == 1 && num > 0)) { //如果不是应选尽选，则只添加和第一个元素相同类型的子元素
        if (ndText != "" || nd.tagName == "IMG" || nd.tagName == "INPUT" || nd.tagName == "A") {
            if (nd.tagName == "IMG") { //如果元素是图片
                global.outputParameters.push({
                    "nodeType": 4, //节点类型
                    "contentType": 1, // 内容类型
                    "relative": global.nodeList.length > 1 ? true : false, //是否为相对xpath路径,注意当只选择了子元素没有选中全部的时候，需要判断
                    "name": parameterName("参数") + (n++) + parameterName("_图片地址"),
                    "desc": "", //参数描述
                    "relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd), //同理需要判断
                    "allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
                    "exampleValues": [{
                        "num": num,
                        "value": nd.getAttribute("src") == null ? "" : nd.getAttribute("src")
                    }],
                    "unique_index": unique_index,
                    "iframe": global.iframe,
                });
            } else if (nd.tagName == "A") { //如果元素是超链接
                global.outputParameters.push({
                    "nodeType": 1,
                    "contentType": 0, // 内容类型
                    "relative": global.nodeList.length > 1 ? true : false, //是否为相对xpath路径
                    "name": parameterName("参数") + (n++) + parameterName("_链接文本"),
                    "desc": "", //参数描述
                    "relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd),
                    "allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
                    "exampleValues": [{"num": num, "value": nd.textContent}], //注意这里的ndtext是整个a的文字！！！
                    "unique_index": unique_index,
                    "iframe": global.iframe,
                });
                global.outputParameters.push({
                    "nodeType": 2,
                    "contentType": 0, // 内容类型
                    "relative": global.nodeList.length > 1 ? true : false, //是否为相对xpath路径
                    "name": parameterName("参数") + (n++) + parameterName("_链接地址"),
                    "desc": "", //参数描述
                    "relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd),
                    "allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
                    "exampleValues": [{
                        "num": num,
                        "value": nd.getAttribute("href") == null ? "" : nd.getAttribute("href")
                    }],
                    "unique_index": unique_index,
                    "iframe": global.iframe,
                });
            } else if (nd.tagName == "INPUT") { //如果元素是输入项
                global.outputParameters.push({
                    "nodeType": 3,
                    "contentType": 1, // 内容类型
                    "relative": global.nodeList.length > 1 ? true : false, //是否为相对xpath路径
                    "name": parameterName("参数") + (n++) + parameterName("_文本"),
                    "desc": "", //参数描述
                    "relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd),
                    "allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
                    "exampleValues": [{
                        "num": num,
                        "value": nd.getAttribute("value") == null ? "" : nd.getAttribute("value")
                    }],
                    "unique_index": unique_index,
                    "iframe": global.iframe,
                });
            } else { //其他所有情况
                global.outputParameters.push({
                    "nodeType": 0,
                    "contentType": 1, // 内容类型
                    "relative": global.nodeList.length > 1 ? true : false, //是否为相对xpath路径
                    "name": parameterName("参数") + (n++) + parameterName("_文本"),
                    "desc": "", //参数描述
                    "relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd),
                    "allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
                    "exampleValues": [{"num": num, "value": ndText}],
                    "unique_index": unique_index,
                    "iframe": global.iframe,
                });
            }
        }
    }
```

#### 15.1 先判断这个节点是否有内容可采

```js
ndText != "" || nd.tagName == "IMG"
    || nd.tagName == "INPUT" || nd.tagName == "A"
```

普通容器需要有直接文本才建立字段；`IMG`、`INPUT`、`A` 即使没有直接文本，也进入专门分支。符合条件才执行 `outputParameters.push()`。

所以 Java 块根不产生额外的整块字段，链接虽然 `ndText` 为空却仍然建立两列。

#### 15.2 四种节点各取什么值

| 分支 | 字段数 | `nodeType` | `contentType` | 示例值来源 |
|---|---:|---:|---:|---|
| IMG | 1 | 4 | 1 | `getAttribute("src")`，缺失则空字符串 |
| A | 2 | 文本 1、地址 2 | 0 | 全部 `textContent` 和 `getAttribute("href")` |
| INPUT | 1 | 3 | 1 | `getAttribute("value")`，缺失则空字符串 |
| 其他有直接文本的节点 | 1 | 0 | 1 | 前面得到的 `ndText` |

这些 `nodeType` 数字是 EasySpider 字段类型，不是 DOM 的 `nodeType` 常量。`contentType` 表示后续读取内容的方式：这里普通文本使用直接文本类型，链接文本使用全部文本类型。

`getAttribute("href")` 在本模型中得到 `/java`，不等于自动解析后的完整网址；输入项读的是 HTML 的 `value` 属性，也不能直接当作用户编辑后的实时 `.value`。

#### 15.3 每个字段对象中的各行保存什么

| 字段 | 本例的意义 |
|---|---|
| `nodeType`、`contentType` | 节点类别与取值方式 |
| `relative` | 是否作为多个块中的相对字段处理 |
| `name` | 用参数编号和类别建立默认字段名 |
| `desc: ""` | 初始描述为空 |
| `relativeXPath` | 多块存块内片段，单块存绝对路径 |
| `allXPaths` | 对应场景下生成的其他定位写法 |
| `exampleValues` | 当前块给出的样本编号和示例值 |
| `unique_index` | 当前节点的块内位置标识 |
| `iframe` | 当前脚本的框架状态 |

`parameterName()` 处理名称语言；`n++` 先使用当前编号，再把本次回调中的编号加 1。建立一列才消耗一个编号，追加第二个块的值不会再次编号。

假设存储读到 `parameterNum = 1`，Java 块遍历完成后，字段顺序是：

```text
outputParameters[0]：参数1_链接文本
outputParameters[1]：参数2_链接地址
outputParameters[2]：参数3_图片地址
outputParameters[3]：参数4_文本      ← 价格
outputParameters[4]：参数5_文本      ← 数量
```

每列初始只有一条 `num: 0` 的示例值。名字里的“文本”是默认名称，程序没有自动把价格列命名为“价格”。

### 16. 单块与多块，区别集中在这三行

各个新字段分支都使用了相同判断：

```js
"relative": global.nodeList.length > 1 ? true : false,
"relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd),
"allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
```

重点看这一行的选择：

```js
"relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd)
```

判断的是 **`nodeList` 中正式选中了几个块**，不是块内有几个子元素，也不是已经生成了几个字段。即使一个块拆出了五个字段，`nodeList.length` 仍然是 `1`。

#### 16.1 只选一个元素，再拆分它的子元素：保存绝对路径

假设只选中 Java 商品块，然后点击“选中子元素”。程序会把块里的链接、图片、价格和数量输入项分别变成采集字段，但每个字段都来自这一个确定的商品块。

此时 `global.nodeList.length > 1` 为假，取三元表达式冒号后面的 `readXPath(nd)`。它不传块根 `tnode`，因此从文档根开始计算当前子元素的绝对路径。

以价格 `p` 为例：

```text
正式选中的块：Java 块
当前子元素：Java 块中的价格 p

前面算出的 ndPath： /p[1]                                  ← 相对于 Java 块
本行调用 readXPath(nd)：/html/body/section[1]/article[1]/p[1] ← 从文档根开始
最终保存 relativeXPath：/html/body/section[1]/article[1]/p[1]
同时保存 relative：false
```

也就是说，虽然前面已经算过块内路径 `ndPath`，**单块情况下，这里会重新计算并保存绝对路径**。之后用该字段定位价格时，可以从整个文档直接找到 Java 块里的这个 `p`；其他子元素也各自保存绝对路径。

#### 16.2 选中多个同类型块，再拆分各块的子元素：保存块内路径

假设正式选中 Java、Python 两个商品块，再点击“选中子元素”。这时每个商品块是一条记录，块内的对应内容需要放进同一列，例如两本书的价格共用一个价格字段。

此时 `global.nodeList.length > 1` 为真，取问号后面的 `ndPath`。它来自前面的 `readXPath(nd, 1, tnode)`，表示**从当前商品块根 `tnode` 到当前子元素的路径**。

两个价格的绝对位置不同，但块内位置相同：

```text
Java 的价格：
  绝对路径：/html/body/section[1]/article[1]/p[1]
  块内路径：/p[1]

Python 的价格：
  绝对路径：/html/body/section[1]/article[2]/p[1]
  块内路径：/p[1]

价格字段最终保存 relativeXPath：/p[1]
同时保存 relative：true
```

第一次处理 Java 的价格时，新建价格字段，保存 `/p[1]` 和示例值“￥99”；处理 Python 的价格时，同样算出 `/p[1]`，因此能够找到已有价格字段，把“￥88”追加到该字段的 `exampleValues` 中。

如果多块时也保存 Java 价格的绝对路径，那么 Python 的块内路径 `/p[1]` 就无法与它匹配，两个价格也无法通过这里的路径比较归入同一字段。保存块内路径后，同一个字段就能表示“各商品块里的第一个 `p`”，从各自的块根出发定位对应价格。

把两种情况放在一起：

| 操作 | `relative` | 字段中的 `relativeXPath` | 定位含义 |
|---|---|---|---|
| 只选 Java 块，拆出内部字段 | false | `/html/body/section[1]/article[1]/p[1]` | 文档中这个确定的价格元素 |
| 选中 Java、Python 两块，拆出对应字段 | true | `/p[1]` | 每个已选块里的对应价格元素 |

**单块拆分时，字段保存具体子元素的绝对位置；多块拆分时，字段保存可在各块中复用的块内位置。** 属性名虽然叫 `relativeXPath`，单块时里面实际保存的仍是绝对路径，要结合 `relative` 判断意义。

已选块只有一个，哪怕 `readyList` 中已经提示很多候选，也仍然走单块判断。候选必须先转入 `nodeList`，才会参与多块遍历。

### 17. index 不为 -1：把下一块的值追加到现有列

```js
} else //如果元素节点已经存在，则只需要插入值就可以了
{
    if (nd.tagName == "IMG") { //如果元素是图片
        global.outputParameters[index]["exampleValues"].push({
            "num": num,
            "value": nd.getAttribute("src") == null ? "" : nd.getAttribute("src")
        });
    } else if (nd.tagName == "A") { //如果元素是超链接
        global.outputParameters[index]["exampleValues"].push({"num": num, "value": nd.textContent});
        global.outputParameters[index + 1]["exampleValues"].push({
            "num": num,
            "value": nd.getAttribute("href") == null ? "" : nd.getAttribute("href")
        });
    } else if (nd.tagName == "INPUT") { //如果元素是输入项
        global.outputParameters[index]["exampleValues"].push({
            "num": num,
            "value": nd.getAttribute("value") == null ? "" : nd.getAttribute("value")
        });
    } else { //其他所有情况
        global.outputParameters[index]["exampleValues"].push({"num": num, "value": ndText});
    }
}
```

这段以 `} else` 开头，承接前一节的 `if (index == -1)`。它不新建字段，只向对应列的 `exampleValues` 追加记录。

来到 Python 的价格时：

```text
num = 1
ndPath = /p[1]
index = 3
ndText = ￥88
```

执行普通文本分支后：

```js
// outputParameters[3].exampleValues
[
    { num: 0, value: "￥99" },
    { num: 1, value: "￥88" }
]
```

来到 Python 的链接时，搜索在第一个 `/a[1]` 字段处停下，所以 `index = 0`：

```text
outputParameters[index]     → 链接文本列，追加 Python 入门
outputParameters[index + 1] → 链接地址列，追加 /python
```

`index + 1` 依赖前面的建字段分支把链接文本与地址连续加入数组。两个字段保存相同路径，搜索先找到文本列，再靠相邻下标找到地址列。

来到 Python 的促销时，没有 `/strong[1]` 字段，`index` 仍是 -1，就回到新建分支。此时编号已经走到 6：

```js
// 新增的 outputParameters[5]，仅展开关键字段
{
    name: "参数6_文本",
    relative: true,
    relativeXPath: "/strong[1]",
    exampleValues: [{ num: 1, value: "限时促销" }]
}
```

它不需要预先给 Java 补一条空值记录，缺项由预览整理阶段处理。这就是应选尽选处理“后面的块多一项”的实际过程。

### 18. 本轮处理结束，逆序把孩子压入栈

```js
            for (let i = nd.children.length - 1; i >= 0; i--) {
                stack.push(nd.children[i]);
            }
        }
    }
}
```

最内层 `for` 先压当前节点最后一个孩子，再往前压。数组右端是栈顶，所以下一轮先处理第一个孩子。

以 Java 块为例，表中栈状态是本轮结束后的状态：

| 当前节点 | 本轮主要动作 | 本轮结束的栈，右端为栈顶 |
|---|---|---|
| article | 标记块根，不建字段，压入四个孩子 | `[input, p, img, a]` |
| a | 建链接文本、地址字段，压入 span | `[input, p, img, span]` |
| span | `continue`，不把 em 入栈 | `[input, p, img]` |
| img | 建图片地址字段 | `[input, p]` |
| p | 建价格文本字段 | `[input]` |
| input | 建数量字段 | `[]` |

栈空后结束 `while`，随后外层 `num++`。如果还有 Python 块，就为它重新建栈，完整走一遍。

末尾三个右括号依次结束孩子循环、当前块的 `while`、所有块的 `for`，再结束这个模式分支。字段数组则一直保留，供不同块对齐。

### 19. 字段已经生成，预览转换留到最后讲

所有块处理完，回调最后执行：

```js
generateValTable();
```

到这一步，`outputParameters` 已经保存各列字段与示例值；`num` 标明每条值属于哪一行。先记住这里调用预览转换函数，接着讲完“所有块共同元素”怎样生成字段。本篇第七部分再统一给出输入、输出，并逐句推演 `generateValTable()` 如何填入每个格子、为缺值留空。

## 第四部分：把两种情况和整条调用路线再对应起来

### 20. 单块、多块都走应选尽选，但输入不同

| 对照项 | 只选 Java 块 | 正式选中 Java、Python 两块 |
|---|---|---|
| `mode` | 0 | 0 |
| `nodeList.length` | 1 | 2 |
| 外层 `num` | 只执行 0 | 先 0，再 1 |
| 每块的遍历 | 栈式 DFS，带剪枝 | 每个块各做一次栈式 DFS，带剪枝 |
| 字段定位 | 绝对路径，`relative = false` | 块内路径，`relative = true` |
| 对应元素的值 | 建立首条示例 | 后续块追加到已有字段 |
| 后续块新增内容 | 尚未遍历，不会出现 | 新路径满足内容条件时建立新字段 |
| 本例预览 | 一行五列 | 两行六列，Java 的促销为空白 |

这个函数不会仅因为第一个块有候选，就自动遍历全部候选。它处理的是调用时参与遍历的正式已选名单。

### 21. 从按钮到预览的执行路线

```text
点击“选中子元素（应选尽选）”
  → selectDescendents(e, 0)
  → handleDescendents(0)
  → 请求存储中的 parameterNum
  → 回调：清旧参数，设置 selectedDescendents = true
  → 对 nodeList 中每个块建立栈
      → 弹出节点
      → 必要时 continue 剪枝
      → 计算块内路径，寻找对应字段
      → 读取直接文本，按条件记录阴影
      → 新位置：符合内容条件就建立字段
      → 已有位置：追加当前块的示例值
      → 逆序压入孩子，继续 DFS
  → generateValTable() 按 num 对齐示例值、补空白
  → Vue 根据字段数组与 valTable 更新预览
```

子元素模式启用后，再点中候选扩展已选块时，`addEl()` 中也可能触发 `handleDescendents()`；点击“选中全部”的路径同样有重新处理子元素的步骤。这与第 7 篇末尾的流程总结对应。

默认调用 `handleDescendents()` 使用 mode 0。本篇先把用户明确点击应选尽选后的这一轮讲清楚；它与普通参数生成都使用异步回调，不能把不同入口安排的回调当作已经同步完成的固定顺序。

### 22. 读源码时要核对的边界

“应选尽选”仍然有内容条件和剪枝，不是每个 DOM 节点都建立一列。**没有直接文本的普通容器不建字段，链接下直接的 span 会剪掉整支。**

字段对齐依据块内 XPath，标签位置变化可能造成错列。同一位置的内容含义不同，程序也可能把它们放入同一列，因此应当检查预览。

源码从所选块向下遍历普通元素的 `children`，不会因为遇到一个 iframe 就自动进入它的文档；页面另一个文档里的节点不属于当前这棵元素子树。

当前函数生成的是字段与示例预览。确认采集、向后续流程传递数据，仍由操作台的后续采集动作完成。

### 23. 用同一个案例练习

1. 只选 Java 块，价格字段的 `relative` 和 `relativeXPath` 分别是什么？
2. 两个块都已选，Python 的价格为什么追加到第 4 列，而不是再建一列？
3. Python 的促销为什么可以新增字段？Java 的空白是在什么时候补出来的？
4. 为什么 span 里的 em 没有进栈，链接文字却仍然包含“入门”？
5. 如果在 Python 的价格前插入 `<p>包邮</p>`，原来的 `/p[1]` 列会怎样变化？
6. 为什么这个例子的 img 有图片地址字段，却没有满足前面的阴影记录条件？

第 5 题中，Python 的包邮会进入已有 `/p[1]` 列，价格变成新位置 `/p[2]`，可能新增另一列。这说明按位置对齐与按业务含义对齐是两件事。

## 第五部分：先不看代码，理解“所有块共同元素”

### 24. 先把“共同”的判断对象说清楚

操作台按钮“选中子元素（所有块共同元素）”对应模式 `2`。这里的“所有块”指正式进入 `nodeList` 的块；还留在 `readyList` 中的候选不参与本次判断。

先只考虑 §6 的 Java、Python 两个商品块。模式 2 要回答的是：**哪些块内位置在两个块中都存在？** 它比较相对于各自块根的路径，不比较文字是否相同，也不要求 Java 与 Python 指向同一个 DOM 元素。

给原例的元素加上字母，树从块根向下展开。这里 A、B 分别代表本篇的 Java、Python 卡片：

```text
                       A(article：Java 块)
                                │
          ┌─────────────┬───────┴───────┬─────────────┐
          │             │               │             │
        C(a)          D(img)           E(p)         F(input)
          │
        G(span)
          │
        H(em)
```

```text
                            B(article：Python 块)
                                     │
          ┌─────────────┬───────────┬─┴─────────┬─────────────┐
          │             │           │           │             │
        I(a)          J(img)       K(p)       L(input)      M(strong)
          │
        N(span)
          │
        O(em)
```

C、I 提供不同标题，E、K 提供不同价格，但是它们分别处在相同的块内位置。M 的促销位置只有 Python 块存在，不能保留为所有块的共同字段。

前面已经解释过链接下的 span 剪枝。本模式的两轮遍历也遵守这条规则：G、N 连同 H、O 被跳过。链接仍从自身的全部文本中读取完整标题。

### 25. 第一步：分别列出每个块参与比较的位置

把“怎么从块根走到这个元素”写成块内 XPath：

| 位置 | Java 块 | Python 块 | 所有块都有吗？ |
|---|---|---|---|
| 块自身 | 空路径 `""` | 空路径 `""` | 有 |
| 第一个链接 | `/a[1]` | `/a[1]` | 有 |
| 第一张图片 | `/img[1]` | `/img[1]` | 有 |
| 第一个段落 | `/p[1]` | `/p[1]` | 有 |
| 第一个输入项 | `/input[1]` | `/input[1]` | 有 |
| 第一个 strong | 不存在 | `/strong[1]` | 没有 |

于是得到两份位置清单：

```text
Java：  ""，/a[1]，/img[1]，/p[1]，/input[1]
Python：""，/a[1]，/img[1]，/p[1]，/input[1]，/strong[1]
```

这一步只记录位置，还没有创建链接列、图片列或价格列。也不能使用两个块的绝对路径来求交集：绝对路径中的 `article[1]`、`article[2]` 本来就不同，表达的是不同商品。

### 26. 第二步：只留下每份清单中都出现的位置

先拿 Java 的清单作为当前共同位置，再逐项检查 Python 的清单：

| Python 当前位置 | Java 清单中有吗？ | 决定 |
|---|---|---|
| `""` | 有 | 保留块根位置 |
| `/a[1]` | 有 | 保留链接位置 |
| `/img[1]` | 有 | 保留图片位置 |
| `/p[1]` | 有 | 保留段落位置 |
| `/input[1]` | 有 | 保留输入项位置 |
| `/strong[1]` | 没有 | 排除促销位置 |

最后的交集为：

```text
共同位置 = ""，/a[1]，/img[1]，/p[1]，/input[1]
```

共同位置与字段数量还不是同一个概念。块根虽然在交集中，但本例只有缩进空白，没有直接文本，不生成“整个商品块”字段；链接位置则生成文本、地址两列。

因此，本例有五个共同位置，最终也是五列字段，但这是“块根不建列”和“链接拆两列”抵消后的结果，不能把共同位置数量直接当成字段数量。

### 27. 第三步：按共同位置建字段，再追加每个块的值

在真正生成字段前，共同位置已经全部确定。因此第二轮不会先建立促销列，再因为 Java 没有促销而删除它；促销位置从一开始就不进入字段处理。

1. 再走一遍 Java 块，在共有位置上建立链接文本、链接地址、图片、价格、数量五列，写入第 `0` 行示例。
2. 再走一遍 Python 块，把共有位置的内容追加到原有列，写入第 `1` 行示例。
3. 到 M 的 `/strong[1]` 时，它不在共同位置中，不新建促销列。
4. 整理预览后，得到下表。第一列“商品”仅用于讲解，不是生成的字段：

| 商品 | 链接文本 | 链接地址 | 图片地址 | 价格 | 数量 |
|---|---|---|---|---|---|
| Java | Java 入门 | `/java` | `java.jpg` | ￥99 | 1 |
| Python | Python 入门 | `/python` | `python.jpg` | ￥88 | 2 |

应选尽选模式会保留促销列并给 Java 补空白；所有块共同模式直接排除这个位置，所以本例是两行五列，没有促销列。

### 28. 再改一次例子，区别“相对首块”与“所有块共同”

原例只有第二块多促销，模式 1 与模式 2 都会排除它，结果恰好一样。为了看出区别，再在 Java 块末尾增加一个 `small` 元素，直接文字为“仅首块赠书签”，Python 没有这个位置。

```text
Java 额外位置：  /small[1]  → 仅首块赠书签
Python 额外位置：/strong[1] → 限时促销
共同位置：      两种额外位置都不包含
```

| 模式 | 对 Java 独有的赠品位置 | 对 Python 独有的促销位置 | 本例字段数 |
|---|---|---|---:|
| 0 应选尽选 | 建字段，Python 行补空格 | 建字段，Java 行补空格 | 7 |
| 1 相对首块 | 首块发现的位置可以建字段，Python 行补空格 | 后续块的新位置不建字段 | 6 |
| 2 所有块共同 | 不在交集中，不建字段 | 不在交集中，不建字段 | 5 |

模式 1 的依据是首块能发现哪些字段；模式 2 的依据是哪些位置在每个已选块中都存在。第 28 节只是对照变化，下面的代码推演继续使用 §6 的原始两块，不加入 small。

如果有第三个块，也要继续求交集。假设第三个块只有链接、图片、段落，没有输入项：

```text
前两个块的共同位置：""，/a[1]，/img[1]，/p[1]，/input[1]
第三个块的位置：    ""，/a[1]，/img[1]，/p[1]
三块最终共同位置：  ""，/a[1]，/img[1]，/p[1]
```

数量位置会被排除，最终留下链接文本、链接地址、图片、价格四列。“共同”要求每个参与块都满足，不能因为前两块有输入项就继续保留它。

## 第六部分：再看源码，逐步拆解 handleDescendents(2)

本部分核对 [扩展源码 global.js](../../Extension/manifest_v3/src/content-scripts/global.js) 中的模式 2；前面引用的中文发布版使用同样的核心分支。下面按执行顺序分段摘录，字段建对象的其他标签分支已经在 §15 展开。

### 29. 按钮把 mode 设为 2，进入独立分支

操作台按钮绑定如下：

```html
<a v-on:mousedown="selectDescendents(1,2)">选中子元素（所有块共同元素）</a>
```

第一个参数占用 `e` 的位置，第二个参数才是 `mode=2`。进入 §8 的 `selectDescendents(e, mode)` 后调用 `handleDescendents(2)`，并保存 `this.mode=2`。

异步编号回调仍然先清旧参数，再设置 `selectedDescendents=true`。随后 `if (mode == 2)` 成立，进入共有模式；它与前面模式 0 的 `else` 分支分开执行。

### 30. 第一轮 DFS：每个块先形成自己的路径数组

模式 2 分支先执行：

```js
let xpath_list = [];
for (let num = 0; num < global.nodeList.length; num++) {
    let node_xpaths = [];
    let tnode = global.nodeList[num]["node"];
    let stack = new Array();
    stack.push(tnode);
    while (stack.length > 0) {
        let nd = stack.pop();
        if (nd.parentNode.tagName == "A" && nd.tagName == "SPAN") {
            continue;
        }
        ndPath = readXPath(nd, 1, tnode);
        node_xpaths.push(ndPath);
        for (let i = nd.children.length - 1; i >= 0; i--) {
            stack.push(nd.children[i]);
        }
    }
    xpath_list.push(node_xpaths);
}
```

逐句推演 Java 块：

1. `xpath_list=[]` 用来保存所有块的路径清单。
2. `num=0` 取到 Java 块，为它单独建立 `node_xpaths=[]` 和待办栈。
3. 弹出块根，`readXPath(块根,1,块根)` 得到 `""`，首先放进 `node_xpaths`。
4. 逆序压入孩子，下一次先弹出链接，记录 `/a[1]`。
5. 再弹出链接下的 span，`continue` 跳过本轮；既不记录 span 路径，也不把 em 压入栈。
6. 继续记录图片、价格、输入项路径，栈空后，把整份 `node_xpaths` 放进 `xpath_list`。
7. `num=1` 时重新建路径数组和栈，遍历 Python 块，它比 Java 多记录 `/strong[1]`。

此时得到：

```js
xpath_list = [
    ["", "/a[1]", "/img[1]", "/p[1]", "/input[1]"],
    ["", "/a[1]", "/img[1]", "/p[1]", "/input[1]", "/strong[1]"]
];
```

本轮没有 `outputParameters.push()`，因此还没有生成任何字段。记录路径时也没有要求节点必须有直接文本，所以空容器位置可以进入清单，稍后再按内容条件判断是否建字段。

### 31. Set 与 filter：逐块收缩共同路径集合

```js
let commonXPaths = new Set(xpath_list[0]);
for (let i = 1; i < xpath_list.length; i++) {
    commonXPaths = new Set(
        xpath_list[i].filter(element => commonXPaths.has(element))
    );
}
let commonXPathList = Array.from(commonXPaths);
```

先解释每个表达式，再代入路径：

1. `new Set(xpath_list[0])` 用 Java 路径初始化共同集合，集合中的项是字符串。
2. 外层 `i=1` 取到 Python 的清单。
3. `filter()` 按顺序把 Python 清单的每个字符串传给回调形参 `element`；它不是 DOM 元素。
4. `commonXPaths.has(element)` 检查这个字符串是否已在之前各块的共同集合中，返回布尔值。
5. 返回 `true` 的项进入过滤结果，`false` 的项被排除。
6. `filter()` 执行结束后才建立新 Set，再赋给 `commonXPaths`。因此本次过滤都查询同一个旧集合，不是每检查一项就改集合。
7. `Array.from()` 将最终 Set 转成数组，供第二轮按下标查找。

| 回调收到的 `element` | `commonXPaths.has(element)` | 过滤结果累计 |
|---|---|---|
| `""` | true | `[""]` |
| `/a[1]` | true | `["","/a[1]"]` |
| `/img[1]` | true | `["","/a[1]","/img[1]"]` |
| `/p[1]` | true | `["","/a[1]","/img[1]","/p[1]"]` |
| `/input[1]` | true | `["","/a[1]","/img[1]","/p[1]","/input[1]"]` |
| `/strong[1]` | false | 保持上面的五项 |

最终：

```js
commonXPathList = ["", "/a[1]", "/img[1]", "/p[1]", "/input[1]"];
```

如果还有第三块，外层 `i=2` 继续用它的清单过滤当前集合。前两块共同但第三块没有的位置，也不会进入新的结果，这就实现了所有块的交集。

### 32. 第二轮 DFS：判断当前位置是不是共同位置

```js
let hash = {};
for (let num = 0; num < global.nodeList.length; num++) {
    let tnode = global.nodeList[num]["node"];
    let stack = new Array();
    stack.push(tnode);
    while (stack.length > 0) {
        let nd = stack.pop();
        if (nd.parentNode.tagName == "A" && nd.tagName == "SPAN") {
            continue;
        }
        ndPath = readXPath(nd, 1, tnode);
        ndAllPaths = getElementXPaths(nd, tnode);
        let index = -1;
        for (let i = 0; i < commonXPathList.length; i++) {
            if (commonXPathList[i] == ndPath) {
                index = i;
                break;
            }
        }
        // 下面处理 index != -1 的节点，末尾再把孩子压入栈。
    }
}
```

这段只摘出第二轮的遍历与查找部分。源码会在注释处处理字段并压入孩子，下一节继续展开。

**这里的 `index` 含义与模式 0 不同。** 模式 0 在字段数组里查找位置；模式 2 先在 `commonXPathList` 中查找，得到的是共同路径数组下标。

| 当前路径 | `commonXPathList` 中的下标 | 后续决定 |
|---|---:|---|
| `""` | 0 | 进入共同节点处理，但仍要检查内容 |
| `/a[1]` | 1 | 处理链接字段 |
| `/img[1]` | 2 | 处理图片字段 |
| `/p[1]` | 3 | 处理价格字段 |
| `/input[1]` | 4 | 处理数量字段 |
| `/strong[1]` | -1 | 跳过字段处理，不新增促销列 |

共有节点通过 `if (index != -1)` 后，仍按 §13 的方式拼直接文本，并按 §14 的视觉条件记录高亮。`unique_index` 仍执行 `let unique_index = ndPath`，不是随机标识。

### 33. 第一块建字段：hash 连接“共同路径下标”与“字段下标”

源码在共有节点的处理内部写了：

```js
if (num == 0) {
    if (ndText != "" || nd.tagName == "IMG" || nd.tagName == "INPUT" || nd.tagName == "A") {
        hash[index] = global.outputParameters.length;
        // 紧接着按 IMG、A、INPUT、普通文本分支 push 完整字段对象。
        // 字段对象键与 §15 相同；链接连续 push 文本、地址两列。
    }
}
```

`num==0` 只允许第一块建立字段。`hash[index]` 保存的是 **push 之前的字段数组长度**，也就是接下来第一个新字段的下标。

按 Java 块的实际顺序推：

| 当前路径 | 共同路径 `index` | push 前字段数 | 写入 hash | 新增字段及下标 |
|---|---:|---:|---|---|
| `""` | 0 | 0 | 不写，本例块根没有可采直接文本 | 无 |
| `/a[1]` | 1 | 0 | `hash[1]=0` | 链接文本 `[0]`、链接地址 `[1]` |
| `/img[1]` | 2 | 2 | `hash[2]=2` | 图片地址 `[2]` |
| `/p[1]` | 3 | 3 | `hash[3]=3` | 价格文本 `[3]` |
| `/input[1]` | 4 | 4 | `hash[4]=4` | 数量值 `[4]` |

最终：

```js
hash = {1: 0, 2: 2, 3: 3, 4: 4};
```

不能直接用 `outputParameters[index]` 追加链接文本，因为 `/a[1]` 的共同路径下标是 `1`，它对应的文本字段下标却是 `0`。块根不建列、链接拆两列，都会影响这种对应关系。

以价格字段为例，进入普通文本分支后，实际建立对象的代码为：

```js
global.outputParameters.push({
    "nodeType": 0,
    "contentType": 1,
    "relative": global.nodeList.length > 1 ? true : false,
    "name": parameterName("参数") + (n++) + "_" + parameterName("文本"),
    "desc": "",
    "relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd),
    "allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
    "exampleValues": [{"num": num, "value": ndText}],
    "unique_index": unique_index,
    "iframe": global.iframe
});
```

代入 `num=0`、`ndPath="/p[1]"`、`ndText="￥99"`、当前编号 `n=4`：生成“参数4_文本”，保存第 `0` 行价格；两个块已选，所以 `relative=true`，`relativeXPath` 保存块内片段。

### 34. 后续块只追加：先通过 hash 找到正确字段

第二块及后续块进入 `num==0` 对应的 `else` 分支。下面保留其主要代码：

```js
try {
    if (ndText != "" || nd.tagName == "IMG" || nd.tagName == "INPUT" || nd.tagName == "A") {
        if (nd.tagName == "IMG") {
            global.outputParameters[hash[index]]["exampleValues"].push({
                "num": num,
                "value": nd.getAttribute("src") == null ? "" : nd.getAttribute("src")
            });
        } else if (nd.tagName == "A") {
            global.outputParameters[hash[index]]["exampleValues"].push({
                "num": num,
                "value": nd.textContent
            });
            global.outputParameters[hash[index] + 1]["exampleValues"].push({
                "num": num,
                "value": nd.getAttribute("href") == null ? "" : nd.getAttribute("href")
            });
        } else if (nd.tagName == "INPUT") {
            global.outputParameters[hash[index]]["exampleValues"].push({
                "num": num,
                "value": nd.getAttribute("value") == null ? "" : nd.getAttribute("value")
            });
        } else {
            global.outputParameters[hash[index]]["exampleValues"].push({
                "num": num,
                "value": ndText
            });
        }
    }
} catch (e) {
    console.log("Error: -----------------------", e);
}
```

这里为排版缩短了 catch 的日志字符串，保留了捕获行为。按 Python 块逐项代入：

1. 链接 `/a[1]` 查到 `index=1`，再由 `hash[1]=0` 找到文本列 `[0]`，追加 `{num:1,value:"Python 入门"}`。
2. 同一个链接的地址写到 `hash[1]+1=1`，追加 `/python`。`+1` 依赖建立链接字段时连续 push 文本与地址。
3. 图片 `/img[1]` 得到 `index=2`、`hash[2]=2`，给图片列追加 `python.jpg`。
4. 价格 `/p[1]` 得到 `index=3`、`hash[3]=3`，给价格列追加“￥88”。
5. 输入项 `/input[1]` 得到 `index=4`、`hash[4]=4`，给数量列追加属性值 `"2"`。
6. 促销 `/strong[1]` 的 `index=-1`，连共有节点处理都不进入，不会访问 hash，也不会增加字段。

第二轮每个非剪枝节点处理完后，仍执行逆序压孩子的循环；字段不符合共有条件，并不等于在这里执行 `continue` 剪掉整支：

```js
for (let i = nd.children.length - 1; i >= 0; i--) {
    stack.push(nd.children[i]);
}
```

### 35. 完整 outputParameters 与预览结果

以下是原始 Java、Python 两个块调用 `handleDescendents(2)` 后的完整 `global.outputParameters`。假设中文、编号从 `1` 开始、`iframe=false`；两块都正式选中。

```json
[
  {
    "nodeType": 1,
    "contentType": 0,
    "relative": true,
    "name": "参数1_链接文本",
    "desc": "",
    "relativeXPath": "/a[1]",
    "allXPaths": [
      "/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [
      {"num": 0, "value": "Java 入门"},
      {"num": 1, "value": "Python 入门"}
    ],
    "unique_index": "/a[1]",
    "iframe": false
  },
  {
    "nodeType": 2,
    "contentType": 0,
    "relative": true,
    "name": "参数2_链接地址",
    "desc": "",
    "relativeXPath": "/a[1]",
    "allXPaths": [
      "/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [
      {"num": 0, "value": "/java"},
      {"num": 1, "value": "/python"}
    ],
    "unique_index": "/a[1]",
    "iframe": false
  },
  {
    "nodeType": 4,
    "contentType": 1,
    "relative": true,
    "name": "参数3_图片地址",
    "desc": "",
    "relativeXPath": "/img[1]",
    "allXPaths": [
      "/img[1]",
      "//img[contains(., '')]",
      "/html/body/section/article[last()-1]/img"
    ],
    "exampleValues": [
      {"num": 0, "value": "java.jpg"},
      {"num": 1, "value": "python.jpg"}
    ],
    "unique_index": "/img[1]",
    "iframe": false
  },
  {
    "nodeType": 0,
    "contentType": 1,
    "relative": true,
    "name": "参数4_文本",
    "desc": "",
    "relativeXPath": "/p[1]",
    "allXPaths": [
      "/p[1]",
      "//p[contains(., '￥99')]",
      "/html/body/section/article[last()-1]/p"
    ],
    "exampleValues": [
      {"num": 0, "value": "￥99"},
      {"num": 1, "value": "￥88"}
    ],
    "unique_index": "/p[1]",
    "iframe": false
  },
  {
    "nodeType": 3,
    "contentType": 1,
    "relative": true,
    "name": "参数5_文本",
    "desc": "",
    "relativeXPath": "/input[1]",
    "allXPaths": [
      "/input[1]",
      "//input[contains(., '')]",
      "/html/body/section/article[last()-1]/input"
    ],
    "exampleValues": [
      {"num": 0, "value": "1"},
      {"num": 1, "value": "2"}
    ],
    "unique_index": "/input[1]",
    "iframe": false
  }
]
```

第一轮只是收集路径，第二轮才生成这五列；它们保存的 `allXPaths` 来自首块建字段时的节点。后来追加 Python 的示例不会重建备用路径数组。

两轮结束后，回调末尾仍调用 `generateValTable()`，默认 `multiline=true`，每列填两行：

```js
global.app._data.valTable = [
    ["Java 入门", "Python 入门"],
    ["/java", "/python"],
    ["java.jpg", "python.jpg"],
    ["￥99", "￥88"],
    ["1", "2"]
];
```

本例数量直接读取 INPUT 的 `value` 属性，因此示例是字符串 `"1"`、`"2"`，不是数字。最终表格与 §27 手工推演相同。

```text
mode=2 的完整路线
    第一轮：逐块 DFS → 每块的块内路径清单
    求交集：首块初始化 Set → 后续每块 filter → commonXPathList
    第二轮：逐块 DFS → 判断共同位置
        首块：内容符合条件 → 保存 hash 映射 → 建字段
        后续块：内容符合条件 → 按 hash 找字段 → 追加示例
    整理预览：generateValTable() → 每个已选块一行
```

### 36. 用原例检查理解，再看“位置共同”的边界

1. 为什么共同路径数组有 `""`，最终却没有“整个商品块”这一列？
2. `/a[1]` 的共同路径下标是 `1`，为什么文本要写到字段 `[0]`？
3. 加入第三块但第三块没有输入项，数量列在哪一步被排除？
4. Java 有 `/small[1]`、Python 有 `/strong[1]`，为什么模式 0、1、2 分别得到 7、6、5 列？
5. 如果 Python 在价格前插入一个段落“包邮”，所有块共同模式能保证价格对齐吗？

第 5 题仍要按结构推：Java 的 `/p[1]` 是价格，Python 的 `/p[1]` 变成包邮，它们的路径仍共同，会写进同一列；Python 的真实价格改为 `/p[2]`，Java 没有这个位置，所以被交集排除。共同位置不能保证业务含义相同。

还要注意，共同位置只保证元素存在，不保证内容非空。如果首块某个普通 p 没有直接文本，它虽然可进入交集，却不会在首块建字段，也不会建立该位置的 hash 映射；后块同位置有直接文本时，尝试按缺失映射追加会被 catch 捕获，代码不会自动补建字段。上面的完整示例采用首块可正常建立各列的输入。

只选一个块时，交集就是它自己的路径集合，没有其他块用于筛选；仍要经过内容条件与链接 span 剪枝。想理解“所有块共同”的筛选效果，应使用至少两个已选块对照。

## 第七部分：generateValTable() 怎样填每个格子

这里回到[第 8 篇的商品树](08.参数生成.md)：B、C 是 Java、Python 两个商品块，D、E、F 是首块中的链接、图片、价格。这个例子没有前面案例的数量输入项，因此应选尽选生成五列；促销仅出现在第二块中。字段生成过程已经讲完，下面只看 `outputParameters` 怎样转换成 `valTable`。

先用 B、C 两个商品块给出一次完整的输入与输出。读完这个例子，再分析 `multiline` 和循环中每一步的变化。

**输入一：已选节点名单 `global.nodeList`。**

本例已经正式选中 B、C，第一行对应 Java 商品块，第二行对应 Python 商品块：

| 数组位置 | 已选节点 | 对应预览行号 |
|---|---|---:|
| `nodeList[0]` | B，Java 商品块 | 0 |
| `nodeList[1]` | C，Python 商品块 | 1 |

因此 `global.nodeList.length=2`。本函数从这个数组读取已选数量；各字段的值由下面的参数数组提供。

**输入二：待整理的完整 `global.outputParameters`。**

这是第 8 篇 §14 的子元素生成结果，共五个字段。每个字段的 `exampleValues` 保存“哪个行号有什么值”，促销只有第 `1` 行的值：

```json
[
  {
    "nodeType": 1,
    "contentType": 0,
    "relative": true,
    "name": "参数1_链接文本",
    "desc": "",
    "relativeXPath": "/a[1]",
    "allXPaths": [
      "/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [
      {"num": 0, "value": "Java 入门"},
      {"num": 1, "value": "Python 入门"}
    ],
    "unique_index": "/a[1]",
    "iframe": false
  },
  {
    "nodeType": 2,
    "contentType": 0,
    "relative": true,
    "name": "参数2_链接地址",
    "desc": "",
    "relativeXPath": "/a[1]",
    "allXPaths": [
      "/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [
      {"num": 0, "value": "/java"},
      {"num": 1, "value": "/python"}
    ],
    "unique_index": "/a[1]",
    "iframe": false
  },
  {
    "nodeType": 4,
    "contentType": 1,
    "relative": true,
    "name": "参数3_图片地址",
    "desc": "",
    "relativeXPath": "/img[1]",
    "allXPaths": [
      "/img[1]",
      "//img[contains(., '')]",
      "/html/body/section/article[last()-1]/img"
    ],
    "exampleValues": [
      {"num": 0, "value": "java.jpg"},
      {"num": 1, "value": "python.jpg"}
    ],
    "unique_index": "/img[1]",
    "iframe": false
  },
  {
    "nodeType": 0,
    "contentType": 1,
    "relative": true,
    "name": "参数4_文本",
    "desc": "",
    "relativeXPath": "/p[1]",
    "allXPaths": [
      "/p[1]",
      "//p[contains(., '￥99')]",
      "/html/body/section/article[last()-1]/p"
    ],
    "exampleValues": [
      {"num": 0, "value": "￥99"},
      {"num": 1, "value": "￥88"}
    ],
    "unique_index": "/p[1]",
    "iframe": false
  },
  {
    "nodeType": 0,
    "contentType": 1,
    "relative": true,
    "name": "参数5_文本",
    "desc": "",
    "relativeXPath": "/strong[1]",
    "allXPaths": [
      "/strong[1]",
      "//strong[contains(., '促销')]",
      "/html/body/section/article/strong"
    ],
    "exampleValues": [{"num": 1, "value": "促销"}],
    "unique_index": "/strong[1]",
    "iframe": false
  }
]
```

**调用：**

```js
generateValTable(); // 默认 multiline=true，本例每列填 2 行
```

**输出：写入 `global.app._data.valTable` 的数组。**

```js
global.app._data.valTable = [
    ["Java 入门", "Python 入门"], // 第 0 列：链接文本
    ["/java", "/python"],        // 第 1 列：链接地址
    ["java.jpg", "python.jpg"],  // 第 2 列：图片地址
    ["￥99", "￥88"],             // 第 3 列：价格
    [" ", "促销"]                // 第 4 列：促销，第 0 行缺值，补一个空格
];
```

字段数组提供五列，已选名单提供两行。预览数组按 `valTable[列号][行号]` 保存，界面显示为：

| 行号 | 参数1_链接文本 | 参数2_链接地址 | 参数3_图片地址 | 参数4_文本（价格） | 参数5_文本（促销） |
|---|---|---|---|---|---|
| 0 | Java 入门 | /java | java.jpg | ￥99 | `" "` |
| 1 | Python 入门 | /python | python.jpg | ￥88 | 促销 |

从输入对照输出可以观察到：字段顺序决定列顺序，示例中的 `num` 决定值所属的行，缺失行的位置补 `" "`。表头由字段的 `name` 提供，表格值数组只保存各个格子的值；函数将结果写入 Vue 数据，其返回值为 `undefined`。

先解释缺失字段怎样保持商品行号，再区别同类记录与不同字段来源，最后逐句推演排表代码。

### 37. 核心：顺序已经排好，按 num 填入表格

**`num` 就是“这个 `value` 是第几行的值”，行号从 `0` 开始。某行没有对应 `num` 的示例，那一格就是空的。** 例如 `{num:2,value:"会员价"}` 表示“会员价”属于第 `2` 行，也就是界面上的第三行。

**`outputParameters` 已经排好了字段顺序，每个字段的 `exampleValues` 也按 `num` 从小到大保存。`generateValTable()` 只负责把这些示例转换成表格：当前行有对应的 `num` 就填值，没有就补空格，继续下一行。**

应选尽选模式下，某个字段可能只在部分商品块中出现。例如三个商品中，Java 有优惠券，Python 没有促销，Go 有会员价。促销字段只有两条示例：

```js
exampleValues = [
    {num: 0, value: "优惠券"},
    {num: 2, value: "会员价"}
];
```

虽然只有两条示例，表格仍要给三个商品各留一行：

`num=0` 表示第一行填“优惠券”，`num=2` 表示第三行填“会员价”；没有 `num=1` 的示例，所以第二行为空。代码用一个空格 `" "` 表示这个空格子。

| 当前行 `j` | 当前示例下标 `tindex` | 当前示例的 `num` | 怎么填 |
|---:|---:|---:|---|
| 0 | 0 | 0 | 对得上，填“优惠券”，示例下标前进 |
| 1 | 1 | 2 | 对不上，补 `" "`，示例留着等下一行 |
| 2 | 1 | 2 | 对得上，填“会员价”，示例下标前进 |

转换后，这一列就是：

```js
["优惠券", " ", "会员价"]
```

**`j` 走表格的每一行，`tindex` 只在用掉一条示例后前进。** 第 `1` 行缺值时，跳过的是这行的取值，不是那条 `num=2` 的示例；它要留给第 `2` 行，所以两者不能合并。示例已经读完时，剩余行也补空格。

### 38. `multiline` 决定行数：同类元素按记录排，不同位置按字段排

先判断 `nodeList` 中的元素在本次采集中代表什么。它可能装的是多个同类记录，也可能装的是描述一条记录的不同字段来源。

**通常情况：多个同类元素或商品块，每个对应一行。**

例如选中了三个商品的价格 p，它们的值分别为“￥99”“￥88”“￥77”。这些位置作为同类元素处理时，生成一个价格字段，示例行号为 `0`、`1`、`2`；`nodeList.length=3`，预览就要填三行：

```text
价格列
￥99    ← 第 0 个已选元素
￥88    ← 第 1 个已选元素
￥77    ← 第 2 个已选元素
```

选三个商品块也是同一含义：一个块是一条记录，块内可以提供多个字段，但预览仍是三行。某一列只有两条示例，也不能把总行数缩成两行，否则会破坏与其他列的商品对应关系。

**另一种情况：三个不同字段的位置，共同描述一条记录。**

例如只在一个商品中，分别选标题 h2、图片 img、价格 p：

```html
<article>
  <h2>Java 入门</h2>
  <img src="java.jpg">
  <p>￥99</p>
</article>
```

| `nodeList` 中的位置 | 当前选了什么 | 应提供哪一列 | 字段示例行号 |
|---:|---|---|---:|
| 0 | 标题 h2 | 标题文本 | 0 |
| 1 | 图片 img | 图片地址 | 0 |
| 2 | 价格 p | 价格文本 | 0 |

这三个元素作为不同字段来源处理，调用 `generateMultiParameters()`，分别建立三个字段。每个字段的样例都写 `num=0`，因为它们共同属于同一条商品记录。于是应该显示**一行三列**：

| 标题文本 | 图片地址 | 价格文本 |
|---|---|---|
| Java 入门 | java.jpg | ￥99 |

对应的值数组按列保存：

```js
valTable = [["Java 入门"], ["java.jpg"], ["￥99"]];
```

这时 `nodeList.length` 虽然仍然为 `3`，却表示三个字段来源位置，而不是三个商品。为了避免生成三行，调用方使用 `generateValTable(false)`。

现在再读这一句，就能解释为什么有两个分支：

```js
let l = multiline ? global.nodeList.length : 1;
```

| `multiline` | 怎样得到行数 `l` | 背后的输入含义 |
|---|---|---|
| `true`（默认） | `nodeList.length` | 每个已选同类元素或块对应一行，选三个就填三行 |
| `false` | 固定 `1` | 已选位置分别提供字段，共同描述一条记录，只填第 0 行 |

`generateParameters()` 和 `handleDescendents()` 默认调用 `generateValTable()`；无规律多元素的 `generateMultiParameters()` 明确调用 `generateValTable(false)`。这个布尔开关由调用方传入，排表函数本身不会再次检测同类关系。

将三元表达式展开为：

```js
let l;
if (multiline) {
    l = global.nodeList.length; // 已选同类元素/块对应的行数
} else {
    l = 1;                     // 不同字段位置共同描述一条记录
}
```

还要分别计算列数与行数：

```text
列数 = global.outputParameters.length
行数 = multiline 为 true 时的 nodeList.length，或 false 时的 1

三个同类价格元素：3 条选择记录 → 1 个字段 → 3 行、1 列
三个商品块：      3 条选择记录 → 若干字段 → 3 行、若干列
标题、图片、价格：3 个字段来源 → 3 个字段 → 1 行、3 列
```

“选三个不同位置，得到三列”适用于每个位置各生成一个字段的例子。第 8 篇商品树中的 D 是链接，默认拆出文本与地址两列，所以 D、E、F 虽然也是三个不同位置，却生成四列；它们仍然只描述一条记录，预览是一行四列。

默认 `true` 也能处理一个同类记录，此时 `nodeList.length=1`，就填一行。`generateValTable()` 与 `generateValTable(true)` 的效果相同；`multiline` 不决定单元格文字是否换行，也不改变字段列数或已有的 `exampleValues`。

### 39. 完整函数与逐句拆解

下面保留源码的执行逻辑，换行并加上步骤注释：

```js
function generateValTable(multiline = true) {
    // ① 所有列的最终结果
    let paraValues = [];

    // ② 每次处理一个字段，也就是一列
    for (let i = 0; i < global.outputParameters.length; i++) {
        // ③ 当前列与示例读取位置从头开始
        let tValues = [];
        let tindex = 0;
        let l = multiline ? global.nodeList.length : 1;

        // ④ 逐个填当前列的行位置
        for (let j = 0; j < l; j++) {
            // ⑤ 还有示例，并且它正好属于当前行吗？
            if (tindex < global.outputParameters[i]["exampleValues"].length
                && global.outputParameters[i]["exampleValues"][tindex]["num"] == j) {
                // ⑥ 写入值，消费这条示例
                tValues.push(global.outputParameters[i]["exampleValues"][tindex]["value"]);
                tindex++;
            } else {
                // ⑦ 补空格，保留示例读取位置
                tValues.push(" ");
            }
        }

        // ⑧ 当前列填完，把整列加入总结果
        paraValues.push(tValues);
    }

    // ⑨ 所有列完成后，更新预览数据
    global.app._data.valTable = paraValues;
}
```

三个下标要分别理解：

| 变量 | 在哪里取值 | 回答的问题 |
|---|---|---|
| `i` | `outputParameters[i]` | 正在处理哪一个字段、哪一列？ |
| `j` | 与示例的 `num` 比较 | 正在填这一列的第几行？ |
| `tindex` | `exampleValues[tindex]` | 待读取的示例在示例数组的哪个位置？ |

另外，`l` 是小写字母 L，表示每列要填的行数；`tValues` 保存当前一列，`paraValues` 保存所有列。

以促销列为例，`i=4`，该列唯一示例在 `exampleValues[0]`，这条示例的 `num=1`。所以它同时涉及三个不同数字：**第 4 列、示例下标 0、预览行号 1**。

### 39.1 步骤①②：建立总结果，按字段顺序处理列

```js
let paraValues = [];
for (let i = 0; i < global.outputParameters.length; i++) {
```

`paraValues` 初始没有任何列。`i=0` 时处理链接文本，`i=1` 时处理链接地址，后面依次处理图片、价格、促销。列的顺序就是字段数组的顺序。

这里没有遍历 DOM，也没有读取 `nodeList[i].node` 的文字。值已经由前面的生成函数放进 `exampleValues`；本函数读取这些示例并安排位置。

### 39.2 步骤③④：为当前列准备容器和行号

```js
let tValues = [];
let tindex = 0;
let l = multiline ? global.nodeList.length : 1;
for (let j = 0; j < l; j++) {
```

以 B、C 为例，默认 `multiline=true`，所以 `l=2`：

1. `tValues=[]` 保存当前列，`tindex=0` 准备读取该字段的第一条示例。
2. `j=0` 填第 0 行，随后 `j++`，填第 1 行。
3. `j` 变为 `2` 时，`2<2` 不成立，这一列停止填值。
4. 开始下一列时，重新创建 `tValues=[]`，并让 `tindex=0`。每个字段都有自己的示例数组，读取位置不能沿用上一列的值。

这也是 `tValues`、`tindex` 写在外层循环内部的原因：每一列都要独立从头生成。

### 39.3 步骤⑤：把长条件拆成两个问题

```js
tindex < global.outputParameters[i]["exampleValues"].length
&& global.outputParameters[i]["exampleValues"][tindex]["num"] == j
```

第一个问题：**示例数组里还有待读取的项吗？** 例如有两条示例，`tindex=0`、`1` 可以读取，`tindex=2` 就到末尾了。

第二个问题：**这条示例的行号，正好等于当前要填的行号吗？** 要填第 `0` 行，但促销示例写着 `num=1`，就不能把促销提前放到第 `0` 行。

`&&` 从左到右判断，左侧为假就不计算右侧。因此示例已读完时，不会继续访问不存在的示例的 `["num"]`。

| 剩余示例情况 | 当前示例的 `num` 与 `j` | 分支 |
|---|---|---|
| 还有示例 | 相等 | 读取这条示例的 `value` |
| 还有示例 | 不相等 | 当前行补 `" "`，示例留着以后读取 |
| 没有示例 | 右侧不执行 | 当前行补 `" "` |

### 39.4 步骤⑥⑦：写入格子，决定是否消费示例

条件成立：

```js
tValues.push(global.outputParameters[i]["exampleValues"][tindex]["value"]);
tindex++;
```

先把值追加到当前列末尾，再让 `tindex` 指向下一条示例。因为 `j` 连续从 `0` 递增，每轮恰好执行一次 `push()`，本轮写入的位置就是 `tValues[j]`。

条件不成立：

```js
tValues.push(" ");
```

也写入一个格子，以保留行位置，但是**不执行 `tindex++`**。否则，一条属于后面行的示例会在补空格时被跳过。

`j++` 是内层 `for` 的更新步骤，两条分支执行完都会进入下一行；只有匹配并读取示例时，`tindex` 才前进。

### 39.5 步骤⑧⑨：放入整列，再更新界面数据

```js
paraValues.push(tValues);
// 所有字段处理完后：
global.app._data.valTable = paraValues;
```

第一句在内层循环外、外层循环内，所以一列填完才加入总结果一次。若把它写在内层循环里，就会反复加入尚未填完的同一列；源码没有这样做。

最后的赋值在两个循环外，全部列生成完毕后一次性替换 `valTable`。函数没有返回表格数组，返回值为 `undefined`；结果保存在 `global.app._data.valTable` 中。

### 40. 完整推演：五列、两个商品块，十个格子怎样生成

使用[第 8 篇 §14](08.参数生成.md) 的完整 `outputParameters`，即本部分开头给出的五列字段数组。为了专注排表，本节只摘出函数会读取的 `exampleValues`，其他键仍保留在原字段对象中：

| 列号 `i` | 字段 | `exampleValues` |
|---:|---|---|
| 0 | 链接文本 | `[{num:0,value:"Java 入门"},{num:1,value:"Python 入门"}]` |
| 1 | 链接地址 | `[{num:0,value:"/java"},{num:1,value:"/python"}]` |
| 2 | 图片地址 | `[{num:0,value:"java.jpg"},{num:1,value:"python.jpg"}]` |
| 3 | 价格 | `[{num:0,value:"￥99"},{num:1,value:"￥88"}]` |
| 4 | 促销 | `[{num:1,value:"促销"}]` |

`nodeList` 有 B、C 两条记录，调用 `generateValTable()`。进入函数时 `paraValues=[]`，每列的 `l` 都为 `2`。

### 40.1 放慢第一列：从空数组到两行文本

**开始第 0 列。** `i=0`，`0<5` 成立；创建 `tValues=[]`、`tindex=0`、`l=2`。

**填第 0 行。** `j=0`，`0<2` 成立，待读取的示例为 `{num:0,value:"Java 入门"}`：

```text
第一条件：tindex < 示例数 → 0 < 2 → true
第二条件：示例 num == j   → 0 == 0 → true

push("Java 入门") 后：tValues = ["Java 入门"]
tindex++ 后：tindex = 1
for 的 j++ 后：j = 1
```

**填第 1 行。** `j=1`，`1<2` 成立，现在读取 `exampleValues[1]`：

```text
第一条件：1 < 2 → true
第二条件：1 == 1 → true

push("Python 入门") 后：tValues = ["Java 入门", "Python 入门"]
tindex++ 后：tindex = 2
for 的 j++ 后：j = 2
```

**结束第 0 列。** `j=2` 时 `2<2` 不成立，退出内层循环，执行 `paraValues.push(tValues)`：

```js
paraValues = [["Java 入门", "Python 入门"]];
```

随后外层 `i++`，进入第 `1` 列。重新创建 `tValues=[]`、`tindex=0`；地址列从自己的第一个示例开始读取。

### 40.2 十次填格子的完整记录

“进入时 `tindex`”是判断前的值，“填后列数组”是本轮 `push()` 后的 `tValues`：

| `i` / 字段 | `j` | 进入时 `tindex` | 待读取的 `num` | 两个条件 | 填后列数组 | 结束时 `tindex` |
|---|---:|---:|---:|---|---|---:|
| 0 链接文本 | 0 | 0 | 0 | `0<2` 且 `0==0` | `["Java 入门"]` | 1 |
| 0 链接文本 | 1 | 1 | 1 | `1<2` 且 `1==1` | `["Java 入门","Python 入门"]` | 2 |
| 1 链接地址 | 0 | 0 | 0 | `0<2` 且 `0==0` | `["/java"]` | 1 |
| 1 链接地址 | 1 | 1 | 1 | `1<2` 且 `1==1` | `["/java","/python"]` | 2 |
| 2 图片地址 | 0 | 0 | 0 | `0<2` 且 `0==0` | `["java.jpg"]` | 1 |
| 2 图片地址 | 1 | 1 | 1 | `1<2` 且 `1==1` | `["java.jpg","python.jpg"]` | 2 |
| 3 价格 | 0 | 0 | 0 | `0<2` 且 `0==0` | `["￥99"]` | 1 |
| 3 价格 | 1 | 1 | 1 | `1<2` 且 `1==1` | `["￥99","￥88"]` | 2 |
| 4 促销 | 0 | 0 | 1 | `0<1` 成立，`1==0` 不成立 | `[" "]` | 0 |
| 4 促销 | 1 | 0 | 1 | `0<1` 且 `1==1` | `[" ","促销"]` | 1 |

最后两轮，`j` 从 `0` 变成 `1`，`tindex` 却先保持 `0`。同一条促销示例等到自己的行号才被读取，这就实现了缺失位置的对齐。

### 40.3 每完成一列，总数组怎样增长

```js
// i=0 的列完成后
paraValues = [["Java 入门", "Python 入门"]];

// i=1 的列完成后
paraValues = [
    ["Java 入门", "Python 入门"],
    ["/java", "/python"]
];

// i=2 的列完成后
paraValues = [
    ["Java 入门", "Python 入门"],
    ["/java", "/python"],
    ["java.jpg", "python.jpg"]
];

// i=3 的列完成后
paraValues = [
    ["Java 入门", "Python 入门"],
    ["/java", "/python"],
    ["java.jpg", "python.jpg"],
    ["￥99", "￥88"]
];

// i=4 的列完成后
paraValues = [
    ["Java 入门", "Python 入门"],
    ["/java", "/python"],
    ["java.jpg", "python.jpg"],
    ["￥99", "￥88"],
    [" ", "促销"]
];
```

外层 `i` 变为 `5`，`5<5` 不成立，结束外层循环，再把上述数组赋给 `global.app._data.valTable`。

### 41. 完整推演 `multiline=false`：D、E、F 怎样变成一行四列

使用[第 8 篇 §12](08.参数生成.md) 的完整字段数组：D 建立链接文本、链接地址两列，E 建图片列，F 建价格列。`nodeList.length=3`，但四列都只有一条 `num=0` 的示例。

`generateMultiParameters()` 调用 `generateValTable(false)`，逐列代入：

| 外层 `i` | 每列初始化 | 内层判断 | 读取值 | 当前列结束后的 `paraValues` |
|---:|---|---|---|---|
| 0 | `tValues=[]`，`tindex=0`，`l=1` | `j=0`，`0<1` 且 `0==0` | Java 入门 | `[["Java 入门"]]` |
| 1 | 重新初始化，`l=1` | `j=0`，`0<1` 且 `0==0` | /java | `[["Java 入门"],["/java"]]` |
| 2 | 重新初始化，`l=1` | `j=0`，`0<1` 且 `0==0` | java.jpg | `[["Java 入门"],["/java"],["java.jpg"]]` |
| 3 | 重新初始化，`l=1` | `j=0`，`0<1` 且 `0==0` | ￥99 | `[["Java 入门"],["/java"],["java.jpg"],["￥99"]]` |

每列填完第 `0` 行，`j++` 变为 `1`，`1<1` 不成立，立即结束当前列。外层仍遍历全部四个字段，最终有四列，每列一行：

```js
valTable = [["Java 入门"], ["/java"], ["java.jpg"], ["￥99"]];
```

如果这份输入错误地使用默认 `true`，每列的 `l` 都变为 `3`。第 `0` 行读取唯一示例后，`tindex=1`，第 `1`、`2` 行没有示例，都会补空格：

```js
// 同一份 D、E、F 字段输入，使用 true 时的结果。
valTable = [
    ["Java 入门", " ", " "],
    ["/java", " ", " "],
    ["java.jpg", " ", " "],
    ["￥99", " ", " "]
];
```

这就多出了两行空白。`false` 的作用是让调用方表达“这几个位置属于同一条记录”。

### 41.1 `false` 只处理第 0 行，不会把其他行压到第一行

再拿本部分开头的 B、C 五列输入调用 `generateValTable(false)`，得到：

```js
valTable = [
    ["Java 入门"],
    ["/java"],
    ["java.jpg"],
    ["￥99"],
    [" "] // 促销示例的 num=1，与唯一处理的 j=0 不匹配
];
```

因此 `false` 的含义是“只填预览第 `0` 行”。如果每列的第一条示例属于别的行，也不会挪到第 `0` 行。第 `1` 行的“Python 入门”等值不进入此次预览，原 `exampleValues` 保持不变。

### 41.2 按列保存的数据，Vue 怎样显示成行

函数生成的是 `valTable[列号][行号]`。例如两个商品块的结果：

```js
valTable[0][0] // "Java 入门"：链接文本列，第 0 行
valTable[0][1] // "Python 入门"：链接文本列，第 1 行
valTable[4][0] // " "：促销列，第 0 行
valTable[4][1] // "促销"：促销列，第 1 行
```

`toolkit.vue` 的中文预览模板实际写的是：

```html
<tr v-for="i in valTable[0].length">
  <td v-for="j in list.opp.length">{{ valTable[j - 1][i - 1] }}</td>
  <!-- 后面还有删除当前行的单元格 -->
</tr>
```

模板中的 `i`、`j` 是模板自己的变量：`i` 遍历界面行，`j` 遍历字段列，含义与生成函数中的同名变量不同。Vue 的数字范围从 `1` 开始，所以访问数组时分别减 `1`。

1. 显示第一行，模板 `i=1`，依次读取 `valTable[0][0]`、`[1][0]`、`[2][0]`、`[3][0]`、`[4][0]`。
2. 显示第二行，模板 `i=2`，依次读取 `valTable[0][1]`、`[1][1]`、`[2][1]`、`[3][1]`、`[4][1]`。
3. 表头从 `list.opp`（即 `global.outputParameters`）读取各字段的 `name`。`generateValTable()` 没有把字段名放进值数组。

| 行号 | 链接文本 | 链接地址 | 图片地址 | 价格 | 促销 |
|---|---|---|---|---|---|
| 0 | Java 入门 | /java | java.jpg | ￥99 | `" "` |
| 1 | Python 入门 | /python | python.jpg | ￥88 | 促销 |

生成函数先逐列排值，模板再逐行读取这些列，界面就显示为通常的表格。没有额外生成一份按行存储的数组。

还有一个由循环条件直接决定的情况：若 `outputParameters=[]`，外层循环一次也不执行，最终 `valTable=[]`，没有任何字段列。

### 42. 预览转换练习

1. 某列有 `[{num:0,value:"甲"},{num:2,value:"丙"}]`，已选记录数为 3，分别调用 `generateValTable()` 与 `generateValTable(false)`，逐轮写出 `j`、`tindex` 和该列结果。
2. 促销列只有 `[{num:1,value:"促销"}]`，为什么 `generateValTable(false)` 得到 `[" "]`，不能得到 `["促销"]`？


---

到这里，第 8 篇的参数对象、第 9 篇的 DFS 已经接到真实的子元素采集逻辑：应选尽选允许后块新增字段，所有块共同模式则先求块内路径交集，再建立和填充字段。最后由 `generateValTable()` 按 `num` 把各列示例放入对应行，缺值的格子留空。接下来补 Vue 的模板与状态背景，再追操作台怎样确认采集、消息怎样发给流程图。

返回目录：[README.md](README.md) ｜ 上一篇：[09.DFS 与 BFS：同一棵树，为什么会走出两种顺序](09.DFS与BFS.md) ｜ 下一篇：[11.Vue3详解：读懂 toolkit.vue 前的模板、状态与构建背景](11.Vue3详解.md)
