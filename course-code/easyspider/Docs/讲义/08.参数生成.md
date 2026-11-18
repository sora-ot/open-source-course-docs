# 08.参数生成：从已选节点到完整字段对象

上一篇已经通过手动匹配确定了已选元素和共同路径。接着先看这些元素怎样变成参数：程序究竟保存了什么？为什么两个链接能变成两行，而标题、图片、价格又能变成同一行的不同列？

阅读顺序是：先画网页树，认识 `nodeList` 中的选择记录，再推演这些记录怎样变成字段和行，最后逐句分析 `generateParameters()` 与 `generateMultiParameters()`。字段转换为预览表的 **`generateValTable()`**（没有复数 `s`），放在[第 10 篇末尾](10.选中子元素算法.md)，等讲完子元素采集后再完整拆解。

本篇以 [扩展源码 global.js](../../Extension/manifest_v3/src/content-scripts/global.js) 为准。前面讲义使用的 [中文发布版 global.js](../../ElectronJS/EasySpider_zh/content-scripts/global.js) 中，这几个函数的核心分支相同；扩展源码还包含较长的教学注释，搜索函数名比依赖固定行号更可靠。

## 第一部分：同一张网页，为什么有三种参数组织方式

### 1. 先画出网页元素树

字母表示节点名称，括号内表示标签。以下 HTML 忽略标签间的空白后，对应下面的树：

```html
<section>
  <article id="p1">
    <a href="/java"><span>Java 入门</span></a>
    <img src="java.jpg">
    <p>￥99</p>
  </article>
  <article id="p2">
    <a href="/python"><span>Python 入门</span></a>
    <img src="python.jpg">
    <p>￥88</p>
    <strong>促销</strong>
  </article>
</section>
```

```text
                              A(section)
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
            B(article)                          C(article)
                 │                                   │
     ┌───────────┼───────────┐           ┌───────────┼───────────┬───────────┐
     │           │           │           │           │           │           │
   D(a)       E(img)       F(p)        G(a)       H(img)       I(p)      J(strong)
     │                                   │
  K(span)                             L(span)
```

后面对象例子约定：页面地址是 `https://example.test/books`，标题是“图书列表”，语言为中文，`iframe = false`，存储中的 `parameterNum = 1`。路径按这份 HTML 位于 `body` 下推演。所有 `U_D`、`U_G` 等标识都是随机 `unique_index` 的示意值。

### 1.1 先看输入：`nodeList` 里面到底有什么

源码名称是 **`nodeList`**，它保存的是“已选元素的记录”。假设先选中 D 链接，再把同类链接 G 加入选择，记录如下：

```js
// D、G 是真实 DOM 元素引用；字母只是对应上面的树。
const D = document.querySelector("#p1 a");
const G = document.querySelector("#p2 a");

// 选择完成后的结构示意，不是要求重新手工赋值。
global.nodeList = [
    {
        node: D,
        step: 1,
        bgColor: "",
        boxShadow: "none",
        xpath: "/html/body/section[1]/article[1]/a[1]",
        allXPaths: [
            "/html/body/section[1]/article[1]/a[1]",
            "//a[contains(., 'Java 入门')]",
            "/html/body/section/article[last()-1]/a"
        ]
    },
    {
        node: G,
        step: 2,
        bgColor: "",
        boxShadow: "none",
        xpath: "/html/body/section[1]/article[2]/a[1]",
        allXPaths: [
            "/html/body/section[1]/article[2]/a[1]",
            "//a[contains(., 'Python 入门')]",
            "/html/body/section/article/a"
        ]
    }
];
```

| 记录中的键 | 保存什么 | 后面用来做什么 |
|---|---|---|
| `node` | 页面上真实的 DOM 元素 | 读取 `tagName`、`textContent`、`href`、`src` 等；也能修改高亮样式 |
| `step` | 加入选择时的操作批次 | 撤销一次操作时，找出该批次加入的元素 |
| `bgColor` | 选择时保存的原背景色 | 清空或撤销选择时恢复背景色；本例假设为空字符串 |
| `boxShadow` | 选择时记录的阴影值 | 恢复选择提示时使用；当前源码的保存表达式通常得到 `"none"` |
| `xpath` | 选中这个元素的结构路径 | 生成字段的定位信息，或者参与计算共同路径 |
| `allXPaths` | 这个元素的备用 XPath 数组 | 保存其他定位方式，供后续使用 |

这些记录由 `addEl()` 或 `readyToList()` 建立。`nodeList` 是普通 JavaScript 数组，其中每项是对象；这里的 `node` 是 DOM 引用，不能用字符串 `"D"` 代替。

逐项检查第一条记录：`global.nodeList[0].node === D`，因此从它能读出 `tagName === "A"`、`textContent === "Java 入门"`、`getAttribute("href") === "/java"`。**文字和地址此时仍在 DOM 元素上，选择记录没有额外保存 `value`。**

第二条记录同理，能读出“Python 入门”和 `/python`。这里的 `step=2` 表示第二次选择操作，和预览的行号不是一回事：预览行号由数组下标决定，第二条记录的行号是 `num=1`。如果一次“选中全部”加入多个候选，它们还会共享同一个 `step`。

### 1.2 再看转换：两个选择记录怎样生成两列参数

本篇说的“parameters”实际存放在 **`global.outputParameters`**。它保存字段配置和示例值；生成函数从 `nodeList` 读取元素，新建这些字段对象，并保留原来的选择记录。

先固定调用条件：`generateParameters(0)`，也就是采集全部文本，链接文本与链接地址两个开关都开启，编号从 `1` 开始。暂时只追踪输入到输出的过程，异步读取和具体分支在第三部分展开。

**第一步：读取第一个选择记录。**

```js
num = 0;
nd = global.nodeList[0].node;  // D
ndPath = global.nodeList[0].xpath;
ndAllXPaths = global.nodeList[0].allXPaths;
ndText = nd.textContent;      // "Java 入门"
```

这里的变量赋值是执行快照。`num=0` 让代码进入“建立字段”分支，`nd.tagName === "A"` 又让它进入链接分支。一个链接同时提供文字和地址，所以建立两个字段；这两个字段共享本轮生成的标识 `U_D`。

**第二步：把 D 的两个值放进新字段的第 0 行。**

```js
// 只展示本次变化涉及的键；完整字段对象在后文展开。
global.outputParameters = [
    {
        name: "参数1_链接文本",
        exampleValues: [{num: 0, value: "Java 入门"}]
    },
    {
        name: "参数2_链接地址",
        exampleValues: [{num: 0, value: "/java"}]
    }
];
```

这是结果快照，实际源码用 `push()` 新建字段。输入有两个已选链接，因此两列都设置 `relative=true`、`relativeXPath=""`、`allXPaths=""`，表示后续相对循环项读取。虽然本轮读出了 D 的绝对路径和备用路径，**同类多元素分支没有把它们写进这两个字段**；共同路径由另一个界面状态 `nowPath` 保存。

**第三步：读取 G，把第二行追加到已有字段。**

`num` 变为 `1`，读到 G 的文本“Python 入门”和地址 `/python`。此时 `num==0` 不成立，代码进入追加分支：文本追加到 `outputParameters[0]`，地址追加到 `outputParameters[1]`。字段数仍是两列，结果变为：

```js
// 仍然只展示 name 和 exampleValues。
global.outputParameters = [
    {
        name: "参数1_链接文本",
        exampleValues: [
            {num: 0, value: "Java 入门"},
            {num: 1, value: "Python 入门"}
        ]
    },
    {
        name: "参数2_链接地址",
        exampleValues: [
            {num: 0, value: "/java"},
            {num: 1, value: "/python"}
        ]
    }
];
```

**第四步：把每列的示例值排成预览。**

`generateValTable()` 根据两个选择记录创建两行，得到按列存储的数组：

```js
global.app._data.valTable = [
    ["Java 入门", "Python 入门"],  // 第 0 列
    ["/java", "/python"]         // 第 1 列
];
```

| 行号 | 参数1_链接文本 | 参数2_链接地址 |
|---|---|---|
| `0` | Java 入门 | /java |
| `1` | Python 入门 | /python |

把整个转换过程连起来：

```text
nodeList：按已选元素组织
    第 0 项 D ──读取──→ "Java 入门"、"/java"
    第 1 项 G ──读取──→ "Python 入门"、"/python"
                          │
                          ▼ 按字段归拢
outputParameters：按预览列组织
    第 0 项 链接文本：第 0 行 "Java 入门"，第 1 行 "Python 入门"
    第 1 项 链接地址：第 0 行 "/java"，第 1 行 "/python"
                          │
                          ▼ generateValTable()
valTable：每个字段一列，列内按行号排列
```

因此，从选择记录到字段对象，需要**读取 DOM 内容、判断字段角色、确定行号、建立或追加字段**。`step`、`bgColor`、`boxShadow` 留在选择记录中；参数名、`nodeType`、`contentType`、`exampleValues` 和 `unique_index` 等由生成函数新建。DOM 引用另存到 `outputParameterNodes`，后面的 §4 会说明它怎样关联高亮。

这个例子成立的前提是两个节点按同类元素处理。若选的是链接 D、图片 E、价格 F，生成函数就改走 `generateMultiParameters()`：每个位置建立自己的字段，示例行号都为 `0`。接下来先比较这些组织方式，再展开完整参数对象。

### 2. 先决定“一个节点是一列，还是一行”

| 选择方式 | 手工理解 | 生成函数 | 预览形状 |
|---|---|---|---|
| 只选 D 链接 | 一个链接提供文本、地址两个字段 | `generateParameters(0)` | 2 列、1 行 |
| 选 D、G 两个同类链接 | 每个链接是一条记录，共用文本、地址字段 | `generateParameters(0)` | 2 列、2 行 |
| 选 D 链接、E 图片、F 价格 | 每个位置提供不同字段，合起来描述一条记录 | `generateMultiParameters()` | 4 列、1 行 |
| 只选 B 一个商品块，再选子元素；未点“选中全部” | 一个块提供一行，块内多个位置提供多列 | `handleDescendents(0)` | 4 列、1 行 |
| 选 B、C 两个商品块，再选子元素 | 每个块是一条记录，块内位置决定字段 | `handleDescendents(0)` | 5 列、2 行，首行促销为空 |

`handleElement()` 决定普通多元素调用哪条路：

```js
if (global.nodeList.length > 1) {
    global.app._data.option = relatedTest();
    if (global.app._data.option == 100) {
        generateMultiParameters();
    } else {
        generateParameters(0);
    }
} else if (global.nodeList.length == 1) {
    findRelated();
}
```

按条件一步步推：

1. 只有一个已选元素时，执行 `findRelated()`，先寻找候选。这个分支没有自动生成参数。
2. 有多个已选元素时，先调用 `relatedTest()`，比较路径的标签序列。
3. 标签序列不同，返回 `100`，进入无规律多元素生成，每个位置分别建字段。
4. 标签序列一致，返回 `50`，进入同类生成，第一个元素建字段，后面的元素追加行值。
5. 这是一种结构判断，程序没有理解“哪个是商品标题”。想把整块里的多个字段按商品对齐，需要第 10 篇的子元素遍历。

## 第二部分：参数 dict 到底长什么样

### 3. 单个普通文本字段的完整对象

JavaScript 中这里叫对象；如果按 Python 的习惯理解，它就是一个字段的 dict。选择价格 F，并调用 `generateParameters(0)`，得到：

```json
{
  "nodeType": 0,
  "contentType": 0,
  "relative": false,
  "name": "参数1_文本",
  "desc": "",
  "extractType": 0,
  "relativeXPath": "/html/body/section[1]/article[1]/p[1]",
  "allXPaths": [
    "/html/body/section[1]/article[1]/p[1]",
    "//p[contains(., '￥99')]",
    "/html/body/section/article[last()-1]/p"
  ],
  "exampleValues": [{"num": 0, "value": "￥99"}],
  "unique_index": "U_F",
  "iframe": false
}
```

`allXPaths` 来自 `getElementXPaths()`；上面列的是本例价格元素可得到的路径。换一份 DOM，有 id、class、name 等属性时，备选路径也会变化。

| 键 | 要回答的问题 | 本例解释 |
|---|---|---|
| `nodeType` | 这个字段来自什么元素或内容角色？ | `0` 普通元素；`1` 链接内容；`2` 链接地址；`3` INPUT；`4` IMG |
| `contentType` | 具体按什么方式读取？ | `0` 全部文本；`1` 直接文本；其他类型见下表 |
| `relative` | 路径是否依附循环项或商品块？ | 单个价格为 `false` |
| `relativeXPath` | 到哪里取值？ | 虽然名字叫“相对 XPath”，`relative=false` 时也保存绝对路径 |
| `allXPaths` | 有哪些备用定位方式？ | 单元素保存数组；同类多元素生成时实际写入空字符串 |
| `name` | 字段在界面上叫什么？ | 用存储中的编号命名 |
| `desc` | 字段说明是什么？ | 初始空字符串 |
| `extractType` | 是否标记特殊提取方式？ | 本分支初始化为 `0`；不要与 `contentType` 混为一谈 |
| `exampleValues` | 第几行展示什么示例值？ | `num` 指定 `value` 属于哪一行，从 `0` 开始；某行没有对应的 `num`，那一格就为空 |
| `unique_index` | 怎么关联字段与页面高亮记录？ | `generateParameters()`、`generateMultiParameters()` 使用随机字符串加时间戳；`handleDescendents()` 使用块内路径。两种赋值详见 §6.1 |
| `iframe` | 是否来自 iframe 内？ | 记录当前扩展实例的 iframe 标记 |

字段对象并没有完全统一的键集合：`generateParameters()` 的链接地址分支没有写 `extractType`，`generateMultiParameters()` 和子元素分支也没有写这个键。不能把“某个示例有这个键”推成“所有字段都有这个键”。

### 4. 另外一个数组保存的是 DOM 引用

`global.outputParameters` 保存字段；`global.outputParameterNodes` 保存页面节点及高亮关联：

```js
// 结构示意，node 是真实 DOM 元素，不是字符串 "F"。
{
    node: F对应的DOM元素,
    unique_index: "U_F",
    boxShadow: "none"
}
```

它们不是一一对应：一个链接生成文本和地址两个字段，但普通生成只为这个链接放入一条节点记录，两个字段共享标识。预览、删除字段、高亮恢复需要区分这两个数组；发送消息时传的是 `outputParameters`，不会把 DOM 元素一起发给流程图。

## 第三部分：逐步走进 generateParameters()

### 5. 先清旧数据，再异步取得参数编号

```js
function generateParameters(type, linktext = true, linkhref = true) {
    clearParameters(false);
    let n = 1;
    chrome.storage.local.get('parameterNum', function (items) {
        n = items.parameterNum;
        let ndPath = "";
        let ndAllXPaths = [];
        clearParameters(false);
        // 遍历 nodeList、生成字段，最后 generateValTable()
    });
}
```

1. 进入函数就清旧字段、旧节点高亮和旧预览。`false` 表示不在这一步重置 `selectedDescendents`、`selectStatus`。
2. 注册读取编号的回调。`type`、`linktext`、`linkhref` 由这次调用保存下来，回调以后还能读到。
3. 外层函数没有返回数组，也没有等待回调；它同步返回 `undefined`。
4. Chrome 返回 `items` 后，回调把 `items.parameterNum` 赋给 `n`，再清一次字段。
5. 回调遍历的是执行当时的 `global.nodeList`。等待期间若选择改变，读到的也会改变，并不是调用瞬间的快照。

这里的 `get('parameterNum', ...)` 没有提供缺失时的默认值，和 `generateMultiParameters()` 的 `get({parameterNum: 1}, ...)` 不同。`main.js` 在特定后台页面重置编号；不能仅因外层写了 `let n = 1`，就断言缺失时仍然得到 `1`，因为回调会覆盖它。

### 6. 每轮先找节点，再生成样例内容

```js
let nd = global.nodeList[num]["node"];
ndPath = global.nodeList[num]["xpath"];
ndAllXPaths = global.nodeList[num]["allXPaths"];
let unique_index = Math.random().toString(36).substring(2)
    + Date.now().toString(36);
```

以 F 价格为例：`num=0` → `nd` 是 F 的 DOM 对象 → `ndPath` 取选择记录里的绝对路径 → 生成本轮标识 → 保存高亮记录 → 根据 `type` 计算 `ndText`。

### 6.1 `unique_index` 怎样生成：先区分具体函数

在 **`generateParameters()` 和 `generateMultiParameters()`** 中，源码使用的是：

```js
let unique_index = Math.random().toString(36).substring(2) + Date.now().toString(36);
```

一步步拆开这条表达式：

1. `Math.random()` 生成一个大于等于 `0`、小于 `1` 的随机数。
2. `.toString(36)` 将它写成 36 进制字符串，使用 `0–9`、`a–z`。例如随机数恰好为 `0.5` 时，结果是 `"0.i"`。
3. `.substring(2)` 从下标 `2` 开始截取，去掉前面的 `"0."`；上述示例得到 `"i"`。
4. `Date.now()` 取得当前时间戳，以毫秒计，再通过 `.toString(36)` 转成字符串。假设时间戳为 `1700000000000`，得到 `"loyw3v28"`。
5. 用 `+` 拼接两个字符串，上述假设下得到 `"iloyw3v28"`。实际运行时随机数和时间会变化，具体值也随之变化。

因此，前面普通参数例子中的 `U_D`、`U_E`、`U_F` 是为了跟踪对应关系而使用的**随机标识占位名**。例如 D 生成文本和地址两列时，两列都使用处理 D 的这一轮生成的标识；处理 E、F 时则各自重新执行这条表达式。

而后面的 **`handleDescendents()` 子元素生成**使用另一套赋值：

```js
ndPath = readXPath(nd, 1, tnode);  // nd 相对于当前商品块 tnode 的路径
let unique_index = ndPath;
```

| 生成函数 | `unique_index` 的来源 | 本篇示例 |
|---|---|---|
| `generateParameters()` | 随机字符串 + 时间戳 | `U_D`、`U_F`，均为占位名 |
| `generateMultiParameters()` | 随机字符串 + 时间戳 | D 两列共享 `U_D`，E 用 `U_E`，F 用 `U_F` |
| `handleDescendents()` | `ndPath`，即相对于商品块的路径 | `/a[1]`、`/img[1]`、`/p[1]`、`/strong[1]`，是实际赋值 |

读到字段里的 `unique_index` 时，要先确认它来自哪个生成函数。例如 D、E、F 的四列数组来自 `generateMultiParameters()`，使用随机标识；促销字段的 `/strong[1]` 来自 `handleDescendents(0)`，使用路径标识。

### 7. type 控制内容读取，nodeType 控制字段角色

| `type` / `contentType` | 源码怎样得到样例 | 代入本例或补充元素 |
|---|---|---|
| `0` 全部文本 | `textContent`；IMG 改读 `src`，INPUT 改读 `value` 属性 | D 得“Java 入门”，E 得 `java.jpg`，F 得“￥99” |
| `1` 直接文本 | 遍历直接 `childNodes`，只累加 `nodeType===3` 的文本，再去空白；IMG/INPUT 仍有特殊分支 | D 的字在 span 中，所以 D 的直接文本为空；F 得“￥99” |
| `2` innerHTML | `nd.innerHTML` | D 得 `<span>Java 入门</span>` |
| `3` outerHTML | `nd.outerHTML` | D 得包含外层 a 的 HTML |
| `4` 背景图片 | 从 `nd.style.backgroundImage` 去掉 `url(...)`，再取逗号分隔的第一项 | 内联 `background-image:url("cover.jpg")` 得 `cover.jpg` |
| `5` 页面地址 | `window.location.href` | `https://example.test/books` |
| `6` 页面标题 | `document.title` | “图书列表” |
| `7/8/9` | 函数注释提到截图/OCR/JS，但本函数没有对应读取分支 | 不能宣称在这里已生成截图或 OCR 结果；初始 `ndText` 仍为空 |
| `10` 下拉框值 | `nd.value` | `<select>` 选中 `<option value="js">Java</option>` 得 `js` |
| `11` 下拉框文字 | `nd.options[nd.selectedIndex].text` | 同一个选项得到 `Java` |

两点要按实际表达式理解：INPUT 这里取的是 `getAttribute("value")`，不等于用户编辑后的当前 `.value`；背景图这里读内联样式，不是 `getComputedStyle()`。下拉框类型要求选中的节点确实有对应属性。

### 8. 情况一：只选一个链接 D，默认生成两列

**先看本情况的完整 `nodeList` 输入。** 字母表示前面树中的真实 DOM 引用；这里按逐个手动选择演示，`step` 是选择批次，`bgColor`、`boxShadow` 沿用前面的示意值。

```js
// 选择完成后的结构示意。
global.nodeList = [
    {
        "node": D,
        "step": 1,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[1]/a[1]",
        "allXPaths": [
            "/html/body/section[1]/article[1]/a[1]",
            "//a[contains(., 'Java 入门')]",
            "/html/body/section/article[last()-1]/a"
        ]
    }
];
```

调用 `generateParameters(0)`，两个开关都默认为 `true`：

1. `num=0`，读取 D 的 `textContent`，得到“Java 入门”。
2. 判断 `num==0` 成立，因此进入“建字段”分支。
3. D 的 `tagName=="A"`，进入链接分支。
4. `linktext=true`，新建文本字段，编号从 `1` 变成 `2`。
5. `linkhref=true`，读 `href` 属性，新建地址字段，编号从 `2` 变成 `3`。
6. 没有下一节点，调用 `generateValTable()`；已选节点数为 `1`，所以每列展示一行。

实际字段对象如下。为了便于观察，用 `U_D` 代替随机标识；路径数组对应没有空白的本例链接：

```json
[
  {
    "nodeType": 1,
    "contentType": 0,
    "relative": false,
    "name": "参数1_链接文本",
    "desc": "",
    "extractType": 0,
    "relativeXPath": "/html/body/section[1]/article[1]/a[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [{"num": 0, "value": "Java 入门"}],
    "unique_index": "U_D",
    "iframe": false
  },
  {
    "nodeType": 2,
    "contentType": 0,
    "relative": false,
    "name": "参数2_链接地址",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/a[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [{"num": 0, "value": "/java"}],
    "unique_index": "U_D",
    "iframe": false
  }
]
```

注意地址示例是原始 `href` 属性 `/java`，这里没有使用 `.href` 自动扩成完整网址。

**补充：简化版代码逻辑，只看外层循环。** 下面是框架示意，具体读取、建对象和子元素遍历过程仍按上面的讲解。

```js
// generateParameters(0) 内部的外层循环框架
for (let num = 0; num < global.nodeList.length; num++) {
    let nd = global.nodeList[num]["node"];
    if (num == 0) {
        // 本例 nd 是 D：建立链接文本、链接地址两个字段。
        // 两列都写入 num=0 的示例；定位保存 D 的绝对 XPath。
    }
}
// 本例 nodeList 只有 D，循环一次，得到两列、一行。
```

只循环一次：D 提供两个字段，它们都属于第 `0` 行。

### 9. 单元素其他按钮怎样改变这个对象

| 调用与选中节点 | 生成字段名，假设起始编号为 1 | `nodeType` | `contentType` | `exampleValues[0].value` |
|---|---|---:|---:|---|
| `generateParameters(0, true, false)`，D | 参数1_链接文本 | 1 | 0 | Java 入门 |
| `generateParameters(0, false, true)`，D | 参数1_链接地址 | 2 | 0 | `/java` |
| `generateParameters(0)`，E | 参数1_图片地址 | 4 | 0 | `java.jpg` |
| `generateParameters(0)`，`<input value="2">` | 参数1_文本 | 3 | 0 | `2` |
| `generateParameters(1)`，F | 参数1_文本 | 0 | 1 | ￥99 |
| `generateParameters(2, true, false)`，D | 参数1_链接Innerhtml | 1 | 2 | `<span>Java 入门</span>` |
| `generateParameters(3, true, false)`，F | 参数1_outerHTML | 0 | 3 | `<p>￥99</p>` |
| `generateParameters(4, true, false)`，普通背景图 div | 参数1_背景图片地址 | 0 | 4 | `cover.jpg` |
| `generateParameters(5, true, false)`，普通元素占位 | 参数1_页面网址 | 0 | 5 | 页面地址 |
| `generateParameters(6, true, false)`，普通元素占位 | 参数1_页面标题 | 0 | 6 | 图书列表 |
| `generateParameters(10, true, false)`，SELECT | 参数1_选择的选项值 | 0 | 10 | `js` |
| `generateParameters(11, true, false)`，SELECT | 参数1_选择的选项文本 | 0 | 11 | Java |

读表时从完整普通字段对象出发，改变这些键和名称即可；单元素仍然 `relative=false`，仍保存选中节点路径。页面标题、网址虽然不依赖元素内容，操作台仍先用 `addEl()` 放一个节点占位，让这段循环至少执行一次。

### 9.1 没有已选节点，或者属性缺失时

如果 `nodeList=[]`，编号回调仍会运行，但节点循环一次也不执行，字段数组为空；`generateValTable()` 的字段循环也不执行，最终 `valTable=[]`。这就是页面标题、网址按钮仍要放一个节点占位的原因。

IMG 缺少 src、INPUT 缺少 value 属性、链接缺少 href 时，对应分支写入空字符串 `""` 作为已有行的示例值。这和缺少整条 `{num,...}` 记录不同：前者是“这一行有值记录，但内容为空”，后者由预览算法补一个空格 `" "`。普通元素文本为空时，`generateParameters()` 仍可以建字段；子元素遍历是否建字段则另有内容和标签过滤条件。

### 10. 情况二：选 D、G 两个同类链接（未选中子元素），共用两列

**先看本情况的完整 `nodeList` 输入。** 字母表示前面树中的真实 DOM 引用；这里按逐个手动选择演示，`step` 是选择批次，`bgColor`、`boxShadow` 沿用前面的示意值。

```js
// 选择完成后的结构示意。
global.nodeList = [
    {
        "node": D,
        "step": 1,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[1]/a[1]",
        "allXPaths": [
            "/html/body/section[1]/article[1]/a[1]",
            "//a[contains(., 'Java 入门')]",
            "/html/body/section/article[last()-1]/a"
        ]
    },
    {
        "node": G,
        "step": 2,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[2]/a[1]",
        "allXPaths": [
            "/html/body/section[1]/article[2]/a[1]",
            "//a[contains(., 'Python 入门')]",
            "/html/body/section/article/a"
        ]
    }
];
```

**再看完整的 `outputParameters` 输出。** 调用 `generateParameters(0)`，链接文本、地址开关均开启；回调执行完后数组如下，`U_D` 仍表示本轮生成的随机标识：

```json
[
  {
    "nodeType": 1,
    "contentType": 0,
    "relative": true,
    "name": "参数1_链接文本",
    "desc": "",
    "extractType": 0,
    "relativeXPath": "",
    "allXPaths": "",
    "exampleValues": [
      {
        "num": 0,
        "value": "Java 入门"
      },
      {
        "num": 1,
        "value": "Python 入门"
      }
    ],
    "unique_index": "U_D",
    "iframe": false
  },
  {
    "nodeType": 2,
    "contentType": 0,
    "relative": true,
    "name": "参数2_链接地址",
    "desc": "",
    "relativeXPath": "",
    "allXPaths": "",
    "exampleValues": [
      {
        "num": 0,
        "value": "/java"
      },
      {
        "num": 1,
        "value": "/python"
      }
    ],
    "unique_index": "U_D",
    "iframe": false
  }
]
```

第一次循环仍建文本、地址两字段，但因为 `nodeList.length=2`，两个字段的定位部分变成：

```json
{
  "relative": true,
  "relativeXPath": "",
  "allXPaths": ""
}
```

1. 第一个链接 D 建字段，文本示例为 `[{num:0,value:"Java 入门"}]`，地址示例为 `[{num:0,value:"/java"}]`。
2. 第二次循环 `num=1`，取到 G，读到“Python 入门”和 `/python`。
3. `num==0` 不成立，进入追加分支，不再创建新字段。
4. 对文本列追加 `{num:1,value:"Python 入门"}`，对地址列追加 `{num:1,value:"/python"}`。
5. 因此最终仍是两个字段，每个字段各有两行示例。

```json
[
  {"num": 0, "value": "Java 入门"},
  {"num": 1, "value": "Python 入门"}
]
```

空 `relativeXPath` 表示取循环项自身，不是“没有定位信息”。循环项范围来自 `app._data.nowPath`，稍后由消息函数放进循环消息；这些路径与参数如何组合，放在消息篇和 Electron 的试运行部分继续追。

**补充：简化版代码逻辑，只看外层循环。** 下面是框架示意，具体读取、建对象和子元素遍历过程仍按上面的讲解。

```js
// generateParameters(0) 内部的外层循环框架
for (let num = 0; num < global.nodeList.length; num++) {
    let nd = global.nodeList[num]["node"];
    if (num == 0) {
        // D：建立链接文本、链接地址两列，各写入第 0 行。
    } else {
        // G：把文本、地址分别追加到已有两列，写入第 1 行。
    }
}
// 同类链接共用两列；循环两次，得到两列、两行。
```

第一次建立列，后面的同类元素只追加行值；字段数始终为两列。

### 11. 多链接只保留一列：当前源码的真实边界

后续链接的分支实际固定写了：

```js
global.outputParameters[0]["exampleValues"].push({"num": num, "value": ndText});
global.outputParameters[1]["exampleValues"].push({
    "num": num,
    "value": nd.getAttribute("href") == null ? "" : nd.getAttribute("href")
});
```

它没有再次检查 `linktext`、`linkhref`。因此：

1. 单个链接只采文本或只采地址时，第一轮能正常创建一列。
2. 两个链接只采文本时，第二轮先向第 0 列追加文本，再访问不存在的第 1 列，回调报错。
3. 两个链接只采地址时，第 0 列其实是地址列，却先追加了第二个链接的文本；随后同样访问不存在的第 1 列。
4. 异常发生后，回调末尾的 `generateValTable()` 不会正常执行，不能把这个路径讲成“只生成一列的正常多行预览”。

这里是在解释现有代码，未修改算法。按钮名字、注释和实际执行分支不一致时，应以分支为准。

## 第四部分：无规律多元素与子元素，怎样分别建字段

### 12. 情况三：D、E、F 合起来是一行

**先看本情况的完整 `nodeList` 输入。** 字母表示前面树中的真实 DOM 引用；这里按逐个手动选择演示，`step` 是选择批次，`bgColor`、`boxShadow` 沿用前面的示意值。

```js
// 选择完成后的结构示意。
global.nodeList = [
    {
        "node": D,
        "step": 1,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[1]/a[1]",
        "allXPaths": [
            "/html/body/section[1]/article[1]/a[1]",
            "//a[contains(., 'Java 入门')]",
            "/html/body/section/article[last()-1]/a"
        ]
    },
    {
        "node": E,
        "step": 2,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[1]/img[1]",
        "allXPaths": [
            "/html/body/section[1]/article[1]/img[1]",
            "//img[contains(., '')]",
            "/html/body/section/article[last()-1]/img"
        ]
    },
    {
        "node": F,
        "step": 3,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[1]/p[1]",
        "allXPaths": [
            "/html/body/section[1]/article[1]/p[1]",
            "//p[contains(., '￥99')]",
            "/html/body/section/article[last()-1]/p"
        ]
    }
];
```

`generateMultiParameters()` 对每个选中位置都新建字段，并且每个字段写 `relative=false`、保存自己的路径。链接仍拆两列：

| 外层 `num` | 选中节点 | 新建字段 | 字段示例的 `num` |
|---:|---|---|---:|
| 0 | D，链接 | 参数1_链接文本、参数2_链接地址 | 都为 0 |
| 1 | E，图片 | 参数3_图片地址 | 0 |
| 2 | F，价格 | 参数4_文本 | 0 |

逐步解释“为什么不是三行”：

1. D 提供文本、地址两个字段，它们都属于本条记录的第 0 行。
2. E 提供图片字段，外层循环虽已到 `num=1`，写入字段时却明确使用 `{num:0,...}`。
3. F 提供价格字段，样例行号也明确写 `0`。
4. 最后调用的是 `generateValTable(false)`，让每列只产生一行。

按 D → E → F 的选择顺序，`generateMultiParameters()` 的回调执行完后，**`global.outputParameters` 完整数组如下**。这里用 `U_D`、`U_E`、`U_F` 代替实际生成的随机标识；本分支的四个字段都没有 `extractType` 键。

```json
[
  {
    "nodeType": 1,
    "contentType": 0,
    "relative": false,
    "name": "参数1_链接文本",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/a[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [{"num": 0, "value": "Java 入门"}],
    "unique_index": "U_D",
    "iframe": false
  },
  {
    "nodeType": 2,
    "contentType": 0,
    "relative": false,
    "name": "参数2_链接地址",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/a[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [{"num": 0, "value": "/java"}],
    "unique_index": "U_D",
    "iframe": false
  },
  {
    "nodeType": 4,
    "contentType": 0,
    "relative": false,
    "name": "参数3_图片地址",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/img[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/img[1]",
      "//img[contains(., '')]",
      "/html/body/section/article[last()-1]/img"
    ],
    "exampleValues": [{"num": 0, "value": "java.jpg"}],
    "unique_index": "U_E",
    "iframe": false
  },
  {
    "nodeType": 0,
    "contentType": 0,
    "relative": false,
    "name": "参数4_文本",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/p[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/p[1]",
      "//p[contains(., '￥99')]",
      "/html/body/section/article[last()-1]/p"
    ],
    "exampleValues": [{"num": 0, "value": "￥99"}],
    "unique_index": "U_F",
    "iframe": false
  }
]
```

再按数组下标追踪生成过程：

1. 处理 D 时，先 `push()` 链接文本，再 `push()` 链接地址，得到 `outputParameters[0]` 和 `[1]`。两列来自同一个 DOM 元素，所以路径相同、标识都为 `U_D`，但 `nodeType` 和示例值不同；数组长度变为 `2`。
2. 处理 E 时，再 `push()` 图片地址，成为 `outputParameters[2]`，标识为 `U_E`；数组长度变为 `3`。图片本身没有文本，所以备用文本 XPath 中是空字符串，示例值则从 `src` 读取。
3. 处理 F 时，再 `push()` 普通文本，成为 `outputParameters[3]`，标识为 `U_F`；数组长度变为 `4`。文本从 F 的 `textContent` 读取，得到“￥99”。
4. 调用 `generateValTable(false)`，逐列取出第 `0` 行示例，得到下面的预览数组。

```js
global.app._data.valTable = [
    ["Java 入门"],  // outputParameters[0]：D 的链接文本
    ["/java"],      // outputParameters[1]：D 的链接地址
    ["java.jpg"],   // outputParameters[2]：E 的图片地址
    ["￥99"]        // outputParameters[3]：F 的价格文本
];
```

| 参数1_链接文本 | 参数2_链接地址 | 参数3_图片地址 | 参数4_文本 |
|---|---|---|---|
| Java 入门 | /java | java.jpg | ￥99 |

最终是 **3 条选择记录 → 4 个参数字段 → 1 行、4 列预览**。参数数组下标表示列，`exampleValues` 中的 `num` 表示行；这里四个字段的示例行号都为 `0`。

**补充：简化版代码逻辑，只看外层循环。** 下面是框架示意，具体读取、建对象和子元素遍历过程仍按上面的讲解。

```js
// generateMultiParameters() 内部的外层循环框架
for (let num = 0; num < global.nodeList.length; num++) {
    let nd = global.nodeList[num]["node"];
    // 每次都为 nd 新建字段：D 建两列，E、F 各建一列。
    // 每个字段的 exampleValues 都使用 num=0。
    // 外层 num 表示正在处理哪个位置，不作为本情况的行号。
}
// 三个位置合起来是一条记录，得到四列、一行。
```

每次建立新列，但每列示例的行号都为 `0`；选择了三个位置，也仍然只有一行。

### 13. 情况四：只选 B 一个商品块，再选子元素，未选中全部

**先看本情况的完整 `nodeList` 输入。** 字母表示前面树中的真实 DOM 引用；这里按逐个手动选择演示，`step` 是选择批次，`bgColor`、`boxShadow` 沿用前面的示意值。

```js
// 选择完成后的结构示意。
global.nodeList = [
    {
        "node": B,
        "step": 1,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[1]",
        "allXPaths": [
            "/html/body/section[1]/article[1]",
            "//article[contains(., '')]",
            "id(\"p1\")",
            "/html/body/section/article[last()-1]"
        ]
    }
];
```

**“选中子元素”决定从块里取哪些字段，“选中全部”决定有多少个同类商品块参与。** 这两个动作的作用不同。

假设只正式选中 B（Java 商品块），没有点击“选中全部”，再点击“选中子元素”。即使 C 已被识别为同类候选，它还没有进入 `nodeList`，本次也不会遍历 C。

#### 13.1 先看输入与结果：一个块提供一行，块内内容提供多列

已选名单只有 B，子元素关系如下：

```text
                       B(article，已选)
                              │
                 ┌────────────┼────────────┐
                 │            │            │
               D(a)        E(img)        F(p)
                 │         java.jpg       ￥99
              K(span)
              Java 入门

C(article，Python 商品块) 未进入已选名单，本次不遍历。
```

```js
// 沿用 nodeList 的选择记录结构，这里只摘出节点与路径。
// D、E、F 是遍历 B 时发现的字段来源，没有变成三个已选商品块。
global.nodeList = [
    { node: B, xpath: "/html/body/section[1]/article[1]", /* 其余选择记录字段略 */ }
];
handleDescendents(0);
```

| 已选商品块 | 参数1_链接文本 | 参数2_链接地址 | 参数3_图片地址 | 参数4_文本（价格） |
|---|---|---|---|---|
| B，Java | Java 入门 | /java | java.jpg | ￥99 |

因此是 **1 个已选块 → 4 个字段 → 1 行、4 列**。链接本身生成文本、地址两列；C 的价格与促销都不参与，本例也不会出现促销列。

#### 13.2 完整的 `outputParameters`

沿用前面的 `parameterNum=1` 等约定，异步回调结束后的完整字段数组为：

```json
[
  {
    "nodeType": 1,
    "contentType": 0,
    "relative": false,
    "name": "参数1_链接文本",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/a[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [
      {
        "num": 0,
        "value": "Java 入门"
      }
    ],
    "unique_index": "/a[1]",
    "iframe": false
  },
  {
    "nodeType": 2,
    "contentType": 0,
    "relative": false,
    "name": "参数2_链接地址",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/a[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/a[1]",
      "//a[contains(., 'Java 入门')]",
      "/html/body/section/article[last()-1]/a"
    ],
    "exampleValues": [
      {
        "num": 0,
        "value": "/java"
      }
    ],
    "unique_index": "/a[1]",
    "iframe": false
  },
  {
    "nodeType": 4,
    "contentType": 1,
    "relative": false,
    "name": "参数3_图片地址",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/img[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/img[1]",
      "//img[contains(., '')]",
      "/html/body/section/article[last()-1]/img"
    ],
    "exampleValues": [
      {
        "num": 0,
        "value": "java.jpg"
      }
    ],
    "unique_index": "/img[1]",
    "iframe": false
  },
  {
    "nodeType": 0,
    "contentType": 1,
    "relative": false,
    "name": "参数4_文本",
    "desc": "",
    "relativeXPath": "/html/body/section[1]/article[1]/p[1]",
    "allXPaths": [
      "/html/body/section[1]/article[1]/p[1]",
      "//p[contains(., '￥99')]",
      "/html/body/section/article[last()-1]/p"
    ],
    "exampleValues": [
      {
        "num": 0,
        "value": "￥99"
      }
    ],
    "unique_index": "/p[1]",
    "iframe": false
  }
]
```

四列各有一条 `num=0` 的示例。最终预览值数组按列保存：

```js
global.app._data.valTable = [
    ["Java 入门"],
    ["/java"],
    ["java.jpg"],
    ["￥99"]
];
```

#### 13.3 一步步解释：为什么只有一行，字段又为什么保存绝对路径

1. `nodeList.length=1`，只取出 B 作为本次遍历的块。C 没有在名单中，因此没有第二行。
2. 从 B 向下检查，D 链接建文本和地址两列，E 图片建第三列，F 价格建第四列。链接里的 K 不额外建列，链接文本直接从 D 读取。
3. 当前块下标 `num=0`，所以四个字段的示例都写成 `{num:0,value:...}`。
4. 源码用 `nodeList.length > 1` 判断是否保存相对路径。这里条件为假，所以 `relative=false`，`relativeXPath` 保存从文档根出发的绝对 XPath，`allXPaths` 也通过 `getElementXPaths(nd)` 生成。
5. `unique_index` 仍由 `let unique_index = ndPath` 赋值，而 `ndPath` 是块内路径。因此价格字段可以同时有 `relativeXPath="/html/body/section[1]/article[1]/p[1]"` 和 `unique_index="/p[1]"`；定位方式由 `relative` 与 `relativeXPath` 决定。
6. 最后调用 `generateValTable()`，默认行数等于 `nodeList.length=1`。它只把已有四列示例排成一行，不会补选 C。逐格转换放到第 10 篇末尾讲。

这里先记住生成字段时的判断，完整子元素算法稍后再讲：

```js
"relative": global.nodeList.length > 1 ? true : false,
"relativeXPath": global.nodeList.length > 1 ? ndPath : readXPath(nd),
"allXPaths": global.nodeList.length > 1 ? ndAllPaths : getElementXPaths(nd),
```

也就是说，**点击“选中子元素”可以生成多列，但不会自动把同类候选变成多行。** 多行需要多个商品块已经进入已选名单；不一定必须点“选中全部”，手动选中 B、C 也可以。

**补充：简化版代码逻辑，只看外层循环。** 下面是框架示意，具体读取、建对象和子元素遍历过程仍按上面的讲解。

```js
// handleDescendents(0) 内部的外层循环框架
for (let num = 0; num < global.nodeList.length; num++) {
    let tnode = global.nodeList[num]["node"];
    // 本例只有 B：遍历 B 内的子元素，为链接、图片、价格建字段。
    // 链接拆两列，图片、价格各一列；各列示例均属于 num=0。
    // 只选一个块，因此 relative=false，字段保存绝对 XPath。
}
// C 不在 nodeList 中，不参与本次处理，得到四列、一行。
```

外层只处理一个已选块，块内不同内容生成不同列；同类候选不会自动参加。

### 14. 情况五：B、C 是同类型商品块，选中子元素后生成多行多列

**先看本情况的完整 `nodeList` 输入。** 字母表示前面树中的真实 DOM 引用；这里按逐个手动选择演示，`step` 是选择批次，`bgColor`、`boxShadow` 沿用前面的示意值。

```js
// 选择完成后的结构示意。
global.nodeList = [
    {
        "node": B,
        "step": 1,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[1]",
        "allXPaths": [
            "/html/body/section[1]/article[1]",
            "//article[contains(., '')]",
            "id(\"p1\")",
            "/html/body/section/article[last()-1]"
        ]
    },
    {
        "node": C,
        "step": 2,
        "bgColor": "",
        "boxShadow": "none",
        "xpath": "/html/body/section[1]/article[2]",
        "allXPaths": [
            "/html/body/section[1]/article[2]",
            "//article[contains(., '')]",
            "id(\"p2\")",
            "/html/body/section/article"
        ]
    }
];
```

先正式选中 B、C 两个同类型商品块，再点击“选中子元素（应选尽选）”。每个商品块对应一行，块内的链接文本、链接地址、图片、价格和促销分别对应不同列，因此本例是 **2 行、5 列**；B 没有促销，对应格子为空。只选中商品块并不等于已经生成这些子元素字段，点击“选中子元素”才会向块内遍历、生成多列。

本节先看 `handleDescendents(0)` 生成的参数形状，作为后面第 10 篇子元素遍历的预告；这里不要求先掌握 DFS。普通文字、IMG、INPUT 的 `contentType=1`，链接文本和链接地址的 `contentType=0`；多个商品块使用块内路径，`relative=true`。

| 字段 | `nodeType` | `contentType` | `relativeXPath` | 样例 |
|---|---:|---:|---|---|
| 链接文本 | 1 | 0 | `/a[1]` | 行 0 Java 入门；行 1 Python 入门 |
| 链接地址 | 2 | 0 | `/a[1]` | 行 0 `/java`；行 1 `/python` |
| 图片 | 4 | 1 | `/img[1]` | 行 0 `java.jpg`；行 1 `python.jpg` |
| 价格 | 0 | 1 | `/p[1]` | 行 0 ￥99；行 1 ￥88 |
| 促销 | 0 | 1 | `/strong[1]` | 只有行 1 促销 |

后面才遇到的促销字段来自 **`handleDescendents(0)`**。这个函数先计算 `ndPath = readXPath(J, 1, C)`，得到 `/strong[1]`，再执行 `let unique_index = ndPath`。因此下面对象的 `unique_index` 确实是 `/strong[1]`，它与 §12 中 `generateMultiParameters()` 生成的随机标识采用不同的赋值方式。

选中 B、C 两个商品块，调用 `handleDescendents(0)`，回调执行完后，**`global.outputParameters` 的完整数组如下**。前四列各有两行示例，第五列促销只有第 `1` 行示例；这五个字段都没有 `extractType` 键。

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

按商品块一步步看数组怎样形成：

1. 遍历 B，D 链接建立文本、地址两列，E 图片建立第三列，F 价格建立第四列。四列分别保存 `num=0` 的示例，数组长度为 `4`。
2. 遍历 C，G 链接的块内路径也是 `/a[1]`，找到已有链接字段，把文本和地址追加为第 `1` 行；H、I 同理，把图片与价格追加到已有列。此时仍是四列，每列各有两行示例。
3. 遇到 J 促销，块内路径 `/strong[1]` 尚未出现。模式 `0` 允许后面的商品块新建字段，因此新增 `outputParameters[4]`，数组长度变为 `5`。
4. 促销字段的 `exampleValues` 只有 `{num:1,value:"促销"}`，代码没有伪造第 `0` 行。调用 `generateValTable()` 时，才为缺失的第 `0` 行补一个空格 `" "`。

最终预览数组为：

```js
global.app._data.valTable = [
    ["Java 入门", "Python 入门"],  // 第 0 列：链接文本
    ["/java", "/python"],         // 第 1 列：链接地址
    ["java.jpg", "python.jpg"],   // 第 2 列：图片地址
    ["￥99", "￥88"],              // 第 3 列：价格
    [" ", "促销"]                 // 第 4 列：促销，第 0 行补空格
];
```

| 行号 | 参数1_链接文本 | 参数2_链接地址 | 参数3_图片地址 | 参数4_文本（价格） | 参数5_文本（促销） |
|---|---|---|---|---|---|
| `0` | Java 入门 | /java | java.jpg | ￥99 | `" "` |
| `1` | Python 入门 | /python | python.jpg | ￥88 | 促销 |

因此，**两个商品块 → 五个参数字段 → 两行、五列预览**。`allXPaths` 也不保证全部为块内路径：这里第一项相对块，其他备选路径有不同生成规则；后续商品块追加示例值时，没有重建已有字段的备用路径，所以前四列仍保存创建于 B 时的 `allXPaths`。

与 §13 的单块情况对照：行数由 1 变为 2，字段的 `relative` 由 `false` 变为 `true`，`relativeXPath` 从绝对路径变成块内路径；`unique_index` 仍是块内路径。

**补充：简化版代码逻辑，只看外层循环。** 下面是框架示意，具体读取、建对象和子元素遍历过程仍按上面的讲解。

```js
// handleDescendents(0) 内部的外层循环框架
for (let num = 0; num < global.nodeList.length; num++) {
    let tnode = global.nodeList[num]["node"];
    // 遍历当前商品块中的子元素。
    // 新的块内位置：建立字段，写入当前 num 的示例。
    // 已有的块内位置：追加到已有字段，仍使用当前 num。
    // 选了多个块，因此 relative=true，字段保存块内 XPath。
}
// B 建前四列；C 追加第 1 行并新增促销列，得到五列、两行。
// 促销只保存 num=1 的示例，第 0 行的空白由预览函数补上。
```

外层一轮对应一个商品块，也就是一行；块内路径决定值应该归入哪一列。

### 14.1 三种子元素模式怎样改变字段集合

| 模式 | 实际规则 | 本例 B、C 的结果 |
|---:|---|---|
| 0 应选尽选 | 后面商品块的新位置也允许建字段 | 文本、地址、图片、价格、促销，共 5 列 |
| 1 按首块的位置 | 只在第一个块发现的新位置建字段，后面只追加已有位置的值 | 首块没有促销，所以不新增促销，共 4 列 |
| 2 所有块共同位置 | 先遍历各块求路径交集，再处理共同路径 | `/strong[1]` 不在交集中，共 4 列 |

逐步比较一个变化：若再给 B 增加 `<em>首块提示</em>`，而 C 没有对应 em，模式 0 会保留首块提示和后块促销，共 6 列；模式 1 保留首块提示，不新增后块促销，共 5 列；模式 2 两种独有位置都排除，共 4 列。模式 1 保留的首块独有字段在后行没有样例值，由预览补空格。

这里“共同”判断依据块内 XPath，不检查两个元素的业务含义是否相同。模式 2 先求路径交集；其他模式在访问时查找已有字段路径。字段基本键仍按前面的单块/多块、标签分支生成，变化的是哪些字段可进入列表、哪些行有样例。

### 14.2 `relative=true`，父级商品块的 XPath 存在哪里

**每个字段只保存块内路径；定位商品块的路径单独保存。** 本例字段里的 `relative=true` 表示相对于当前循环项取值，循环项就是 B、C 这样的商品块，不一定是字段元素的直接父节点。

| 数据位置 | 本例保存什么 | 用途 |
|---|---|---|
| `global.nodeList[0].xpath` | `/html/body/section[1]/article[1]` | 已选商品块 B 的绝对路径 |
| `global.nodeList[1].xpath` | `/html/body/section[1]/article[2]` | 已选商品块 C 的绝对路径 |
| `global.app._data.nowPath` | `/html/body/section[1]/article` | 匹配同类商品块的共同路径 |
| `global.outputParameters[3].relativeXPath` | `/p[1]` | 当前商品块内价格元素的位置 |

这里 `nodeList` 选中的是 B、C 两个块。D、E、F 等子元素由 `handleDescendents()` 遍历发现，生成字段；字段对象没有额外的 `parentXPath` 键。

#### 14.2.1 `nowPath` 的来源：`findRelated()` 和 `relatedTest()`

`nowPath` 是操作台 Vue 实例中的数据，初始为空字符串。`global.js` 中有两条主要的成功赋值路径：

| 函数 | 输入状态 | 怎样得到 `nowPath` |
|---|---|---|
| `findRelated()` | 只有一个已选元素 | 从该元素的 XPath 尝试放宽一层索引，找到至少两个匹配后，保存成功的 `tempPath` |
| `relatedTest()` | 已选多个元素 | 对比各元素路径的标签序列与索引，去掉不同位置的索引，保存合并后的 `finalPath` |

**第一条路：只选 B，`findRelated()` 推测还有哪些同类商品块。**

1. 从 `nodeList[0].xpath` 读到 `/html/body/section[1]/article[1]`。
2. 从末层开始尝试，先把 `article[1]` 的索引去掉，得到 `tempPath = "/html/body/section[1]/article"`。
3. `document.evaluate()` 找到 B、C，第二次 `iterateNext()` 仍有元素，说明这条路径至少匹配两个元素。
4. 执行下面的成功分支，记录路径，再把未选中的 C 放进候选名单：

```js
// global.js → findRelated()，成功分支中的代码
global.app.$data.nowPath = tempPath;
let element = document.evaluate(tempPath, document, null, XPathResult.ANY_TYPE, null).iterateNext();
global.app.$data.nowAllPaths = getElementXPaths(element);
pushToReadyList(tempPath);
```

此时 `nowPath` 已经可以匹配 B、C，但 C 仍可能只是候选，未加入 `nodeList`。因此“有共同路径”和“已经选中该路径下的全部元素”是两个状态。

**第二条路：已选 B、C，`relatedTest()` 从实际选择合并路径。**

```text
B：/html/body/section[1]/article[1]
C：/html/body/section[1]/article[2]
                         │
                         ▼ 标签序列相同，article 索引不同
共同路径：/html/body/section[1]/article
```

1. 取出各条选择记录的 `xpath`，拆出标签名和索引。
2. 去掉索引后，B、C 都是 `html/body/section/article`，可以继续比较。
3. `section` 的索引同为 `1`，保留；`article` 的索引分别为 `1`、`2`，将该位置记为 `-1`。
4. `combineXpath()` 对 `-1` 不写方括号，得到 `finalPath = "/html/body/section[1]/article"`。
5. 保存合并结果，并继续寻找未选中的同类候选：

```js
// global.js → relatedTest()，成功分支中的代码
global.app.$data.nowAllPaths = getElementXPaths(element);
global.app.$data.nowPath = finalPath;
pushToReadyList(finalPath);
return 50;
```

若选的是 D 链接和 E 图片，去掉索引后的标签序列不同，`relatedTest()` 会将 `nowPath` 清为 `""`，返回 `100`，交给无规律多元素分支处理。`findRelated()` 则只在找到成功候选路径时写入新值，不能把它讲成每次调用都一定生成共同路径。

源码这里写 `global.app.$data.nowPath`，消息代码写 `global.app._data.nowPath`；它们访问的是同一个 Vue 实例的数据对象。本例中 `nowAllPaths` 是首个匹配块 B 的备用定位数组，不是 B、C 的全部路径列表。

#### 14.2.2 `nowPath` 的去向：经 `messageInteraction.js` 传给 FlowChart

点击确认采集后，**`messageInteraction.js` 中的 `collectMultiWithPattern()` 把这份定位信息传给 FlowChart（流程图）**。它将商品块范围和字段放到同一条消息的不同位置。匹配结果已经全部选中时，实际赋值是：

```js
// messageInteraction.js，摘出与定位有关的赋值。
message.parameters = global.outputParameters; // 各字段的块内路径
message.xpath = global.app._data.nowPath;      // 商品块的共同路径
message.allXPaths = global.app._data.nowAllPaths;
```

然后把业务消息放进 `message_action.message.pipe`，调用 `global.ws.send(JSON.stringify(message_action))`。Electron 主进程收到外层 `type=3`、`from=0` 的消息后，用 `socket_flowchart.send(msg.message.pipe)` 转发给 FlowChart。

FlowChart 的 `logic.js` 识别业务类型 `multiCollectWithPattern`，依次执行 `addElement(8, msg)`、`addElement(3, msg)`，建立循环节点与其内部的采集节点。配置写入时，循环节点保存 `msg.xpath`，采集节点保存 `msg.parameters` 字段数组。因此商品块范围由循环节点提供，各字段共用这个范围。

```text
global.js
    findRelated() → tempPath  ─┐
    relatedTest() → finalPath ─┴→ app.$data.nowPath
                                      │
                                      ▼
messageInteraction.js：collectMultiWithPattern()
    message.xpath      ← app._data.nowPath
    message.parameters ← global.outputParameters
                                      │
                                      ▼ WebSocket → Electron 转发
FlowChart：logic.js
    循环节点（option=8）：parameters.xpath ← message.xpath
    采集节点（option=3）：parameters.params ← message.parameters
```

这里两条来源代表两种选择状态下的处理路径；消息的业务函数名和最终存储键不同，`nowPath` 经消息中的 `xpath` 进入循环节点的 `parameters.xpath`。

拿价格列逐步推演执行时的定位：

1. 用 `/html/body/section[1]/article` 找出商品块 B、C。
2. 第一轮的当前循环元素是 B。在 B 内查找 `/p[1]` 所表示的第一个 p，定位到 F，读取“￥99”。
3. 第二轮的当前循环元素是 C。同样在 C 内查找第一个 p，定位到 I，读取“￥88”。
4. 对促销列使用 `/strong[1]`：B 内没有这个位置，C 内定位到 J。字段的位置不变，变化的是每一轮提供的商品块。

用完整路径表示上述定位关系，就是：

```text
商品块共同路径：/html/body/section[1]/article

第 0 轮，当前块 B：/html/body/section[1]/article[1]
    价格 /p[1] → /html/body/section[1]/article[1]/p[1] → F

第 1 轮，当前块 C：/html/body/section[1]/article[2]
    价格 /p[1]      → /html/body/section[1]/article[2]/p[1]      → I
    促销 /strong[1] → /html/body/section[1]/article[2]/strong[1] → J
```

上图展示定位关系。执行器也可以直接在当前循环元素上查找子元素；源码对这里的 `/p[1]` 使用 `loopElement.find_element(By.XPATH, relativeXPath[1:])`，即在该块内查找 `p[1]`。

如果没有全部选中，消息改用 `loopType=2`，把各个已选商品块的路径放进 `pathList`，循环逐个定位这些块。字段仍使用块内路径，商品块范围仍由循环配置提供。消息封装与流程图节点的完整处理在第 14 篇继续展开。

## 第五部分：字段怎样进入下一段扩展链路

### 15. 从字段到预览，再到流程图节点

```text
已选节点 nodeList
        │
        ▼
generateParameters / generateMultiParameters / handleDescendents
        │
        ├── outputParameters：字段与样例
        └── outputParameterNodes：DOM 与高亮关联
        │
        ▼
generateValTable → app._data.valTable → toolkit.vue 展示
        │
        ▼
用户确认采集 → collectSingle / collectMulti* → WebSocket
```

这张图先交代整条链路。`generateValTable()` 的输入、输出、缺值对齐与逐格推演，统一放在[第 10 篇第七部分](10.选中子元素算法.md)，先读完 DFS 与子元素字段生成，再回到预览转换。

生成参数时 `n++` 只是给本次预览命名，没有在这里把新编号写回 Chrome 存储。确认采集后，流程图通过 `notifyParameterNum()` 更新编号，再发回 `update_parameter_num` 消息；因此编号闭环要到消息篇才完整。

流程图还会通过 `changeGetDataParameters()` 给字段补上 `default`、`paraType`、`recordASField`、前后置 JS、`downloadPic` 等配置。不能把这里生成的初始 dict 当作最终任务字段的全部结构。

### 16. 手工练习

1. 只选 D，调用 `generateParameters(1, true, false)`，链接文本的示例为什么为空？
2. 选 E、H 两张图片，应该新建两个字段，还是一个字段的两行？请写出 `relativeXPath` 与 `exampleValues`。
3. 选 D、E、F，为什么图片样例的 `num` 仍为 `0`？
4. 参数已经生成，流程图还没有新增节点。还缺哪个用户动作、哪层函数？

下一篇学习 DFS 与 BFS，先掌握怎样按顺序走过树。第 10 篇先用栈式 DFS 生成子元素字段，最后把这里的字段对象和示例值转换为预览表；随后才进入 Vue、操作台和消息交互。

返回目录：[README.md](README.md) ｜ 上一篇：[07.手动匹配与相对 XPath：从一行、一列到整个分类区域](07.手动匹配与相对XPath.md) ｜ 下一篇：[09.DFS 与 BFS：同一棵树，为什么会走出两种顺序](09.DFS与BFS.md)
