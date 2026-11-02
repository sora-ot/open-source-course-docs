---
title: "16 · 递归执行"
description: "easyspider · 流程图与执行 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/16.Flowchart递归执行原理.md"
originalUrl: "/originals/easyspider/chapter-16.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 16.Flowchart 与 Python 执行器：控制流与数据落盘

![房源采集示例页面：海淀第1页的A、B，以及全部五条房源数据](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%88%BF%E6%BA%90%E9%87%87%E9%9B%86-%E9%A1%B5%E9%9D%A2%E7%A4%BA%E4%BE%8B.png)

**先看页面长什么样：** 左侧是海淀第1页，A是单间、B是整租；点击“下一页”后是C。切换到朝阳，两页分别是D、E。右侧列出了讲义使用的全部五条房源，判断后只采集单间A、C、E。

截图来自[配套房源教学页](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Flowchart/%E6%88%BF%E6%BA%90%E9%87%87%E9%9B%86-%E6%95%99%E5%AD%A6%E9%A1%B5.html)，数据与原来的房源教学模型一致。下面按地区循环、页面循环、房源循环逐层追踪执行和返回。

**点击房源 A 之后，详情页长这样：**

![房源A的详情页：海淀单间、月租2500元、描述和房源示意图](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%88%BF%E6%BA%90%E9%87%87%E9%9B%86-%E8%AF%A6%E6%83%85%E9%A1%B5%E7%A4%BA%E4%BE%8B.png)

这就是上面列表中 A 对应的[房源详情教学页](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Selenium/detail.html?id=A)：标题是“A：海淀 单间”，月租是2500元，下面还有描述和房源示意图。列表里的房源链接负责带我们进入这一页；“提取信息”操作在详情页读取所需字段，完成后恢复到原来的列表位置，再处理 B。这里的图片是教学占位图。

## 先回忆：整个房源采集流程是什么

我们的任务是：**依次搜索“海淀、朝阳”，每个地区处理两轮页面，逐条检查房源，只进入“单间”的详情页提取信息，最后得到 A、C、E 三条记录。**

**先认清三个循环分别在循环什么：**

| 循环层次 | 本章名称 | 具体在重复什么 |
| --- | --- | --- |
| **第一个循环（最外层）** | **地区循环，也就是输入循环** | 依次取“海淀、朝阳”作为输入值。每轮输入一个地区并搜索，再处理这个地区的页面。 |
| **第二个循环（中间层）** | **页面循环，也就是点击“下一页”的循环** | 在当前地区内，每轮先处理本页的所有房源链接，再点击“下一页”。本例执行两轮。 |
| **第三个循环（最内层）** | **房源循环，也就是逐条处理链接的循环** | 在当前这一页中，依次取出 A、B 等房源链接；每条分别判断，符合条件就点击进入详情页、提取，再恢复列表。 |

**这三个循环是嵌套关系：输入一个地区后，进入“下一页”循环；每轮翻页之前，先用链接循环处理完本页所有链接。当前地区的页面循环全部结束，才回到输入循环，输入下一个地区。**

先从使用者的角度，把操作顺序走一遍：

1. **打开房源网站。** 这一步在所有循环外面，只执行一次。
2. **取一个地区，输入并搜索。** 先输入“海淀”，点击搜索；海淀的页面全部处理完后，再输入“朝阳”并搜索。这是**第一个循环：地区输入循环（最外层）**。
3. **循环点击“下一页”，逐页处理当前地区。** 每轮先处理本页的房源，再点击“下一页”。这就是**第二个循环：页面循环，也就是点击“下一页”的循环（中间层）**。
4. **逐条处理本页的房源：符合条件的先点击进入详情页，再提取详情。** 例如海淀第1页先处理 A，再处理 B，这就是**第三个循环：逐条处理本页链接的房源循环（最内层）**。先在列表页找到本轮的房源链接元素，再由 `executeNode()` 执行孩子节点：判断是否为单间；如果是，就先执行“点击房源”，进入对应的详情页，再执行“提取信息”。**注意：执行“提取信息”时，已经点进这条房源的详情页了，读取的是详情页中的内容。提取完成并恢复列表后，才开始处理下一条房源。**
5. **判断当前房源是不是单间。** A 是单间，就点击 A、进入详情页、提取信息，再恢复到列表，继续处理 B；B 是整租，走空分支，直接跳过。这里“点击、提取”属于单间分支，整租不会执行它们。
6. **本页处理完，再点击下一页。** 按同样的步骤处理剩余页面；当前地区的两轮页面完成后，返回地区循环，开始下一个地区。两个地区都完成后，任务结束，采集结果按输出配置保存。

把这些操作放回层次结构，就是：

~~~text
打开网页
第一个循环：地区输入循环，海淀 → 朝阳
    输入当前地区 → 点击搜索
    第二个循环：点击“下一页”的页面循环，本地区第1轮 → 第2轮
        第三个循环：逐条处理链接的房源循环，依次取出本页每条房源链接
            判断当前房源文字是否包含“单间”
                是：点击房源 → 进入详情页 → 提取详情 → 恢复列表后继续
                否：跳过，继续下一条房源
        本页房源全部处理完 → 点击下一页
~~~

本例的正常执行顺序是：**海淀第1页 A（采集）、B（跳过）→ 海淀第2页 C（采集）→ 朝阳第1页 D（跳过）→ 朝阳第2页 E（采集）**。所以预期输出只有 A、C、E。这里先回忆业务顺序；字段怎样暂存、怎样组成一行并写入文件，后面再追踪。

注意原教学模型把“点击下一页”放在页面循环体末尾，因此每轮都会执行，包括第2轮。正常推演假定按钮可用；两轮结束后不再处理翻到的页面。按钮不存在等情况的源码分支见后文。

**接下来要解释的是：页面循环执行到“房源循环”时，为什么会再次进入同一个执行函数；等房源处理完，它又怎样返回，接着执行“点击下一页”。**

---

> 上一篇从 do 外循环的循环体推导了父子结构，并存好 13 个节点。
>
> 本篇先写一个普通 while，看看它怎样执行循环体。循环体中又有循环时，再引出递归。
>
> 后面用海淀、朝阳的五条房源，逐次跟踪进入、重复与返回，并对照真实 Python 源码。第 13 节区分调用返回与浏览器恢复，第七至九部分讲循环/条件细节、正式执行器生命周期与真实端到端任务。下一篇再讲 Selenium 如何落实每个操作，并在第 24 节集中推演 `handleHistory()`；执行阶段到第 17 篇讲完。

---

## 第一部分：while 的循环体怎样执行存下来的操作

### 1. 先只执行一个页面循环

假设第一个输入循环已经输入“海淀”并搜索，现在进入第二个循环——**点击“下一页”的页面循环**，要处理两轮页面。按照原图，它的循环体顺序是“用第三个链接循环处理本页全部房源，然后点击下一页”。

Python 没有 do/while 语法，可以用 while True 配合末尾的退出检查表达这条正常路径：

~~~python
count = 0
while True:
    process_all_houses_on_this_page()   # 循环体的第一个操作
    click_next_page()                  # 循环体的第二个操作

    count += 1
    if count == 2:
        break
~~~

第 1 轮：处理海淀第 1 页的 A、B，点击下一页，count 变成 1，继续。

第 2 轮：处理海淀第 2 页的 C，点击下一页，count 变成 2，break。

因此 while 负责“这段循环体重复几次”，循环体里的顺序语句负责“一轮具体做什么”。循环体完成后，才进行本例的计数退出检查。

这段是教学代码，尚未加入查找循环元素、异常、停止信号和页面恢复。实际单元素循环的正常路径也有这个骨架，但不能据此认为源码任何情况下都保证执行一次。

### 2. 先看写死的嵌套循环：一层、两层、三层怎样写

先暂时不看 `sequence` 和执行器。如果这个房源任务由我们自己写 Python，循环层次可以直接写在代码的缩进里。

下面三段是**逐步增加业务范围的教学代码，不是 EasySpider 原版源码**。`input_area()`、`click_search()` 等名字代表对应操作，暂时省略 Selenium 实现；打开网页在所有循环外面，只执行一次。

#### 2.1 只有一个循环：依次输入地区

先只要求搜索海淀和朝阳，不处理页面和房源。一个输入循环就够了：

~~~python
for area in ["海淀", "朝阳"]:         # 第一个循环：依次取输入值
    input_area(area)                  # 输入当前地区
    click_search()                   # 点击搜索
~~~

先输入海淀、搜索，再输入朝阳、搜索。这里只有一层需要重复的业务。

#### 2.2 两个循环：每次搜索后，再循环点击下一页

现在增加要求：每个地区都要处理两轮页面。就得在输入循环里面，再套一个页面循环：

~~~python
for area in ["海淀", "朝阳"]:         # 第一个循环：输入地区
    input_area(area)
    click_search()

    page_count = 0
    while True:                      # 第二个循环：点击“下一页”的循环
        process_all_houses_on_this_page()  # 暂时把处理本页封装成一步
        click_next_page()            # 本页处理完，再点击下一页

        page_count += 1
        if page_count == 2:
            break
~~~

**输入一次海淀后，先把海淀的两轮页面做完，才会回到外层，输入朝阳。** 两层循环各管自己的重复范围。

#### 2.3 三个循环：每次翻页之前，逐条处理本页链接

再把“处理本页”展开：本页有 A、B 两个链接，就要先处理 A，再处理 B。因此页面循环里面还要套第三个循环：

~~~python
for area in ["海淀", "朝阳"]:         # 第一个循环：输入地区
    input_area(area)
    click_search()

    page_count = 0
    while True:                      # 第二个循环：点击“下一页”的循环
        houses = houses_on_current_page()  # 先找到本页房源链接
        for house in houses:         # 第三个循环：逐条处理本页链接
            if "单间" in house.text:
                click_house(house)   # 先点击，进入这条房源的详情页
                extract_house()      # 此时已经在详情页，提取详情
                restore_list_page_if_needed()  # 恢复列表，再处理下一条

        click_next_page()            # 所有链接处理完，才点击下一页
        page_count += 1
        if page_count == 2:
            break
~~~

这就是**一层业务循环写一层缩进，两层套两层，三层套三层**。这里为了看清层次，省略了页面跳转后重新定位链接等细节；实际执行器的查找、异常与页面恢复逻辑见后文及第17篇。

#### 2.4 问题来了：软件事先不知道用户会套多少层

上面的写法能工作，是因为我们提前知道任务恰好有三个循环，于是把三层结构写死了。但是 EasySpider 允许用户继续往循环里放循环：房源详情中还可能有图片列表，图片项下面也可能再有其他操作。

**软件写好时，并不知道用户将来设计的任务有几层循环。不能为一层、两层、三层、四层……分别写一套执行代码。**

理论上可以根据流程图生成新的 Python 程序，再执行生成的程序；但这需要另外一套代码生成机制。**当前 EasySpider 的做法是：保存流程图的节点和父子关系，用同一套执行器直接读取并执行这些数据。用户增加一层循环，只增加节点及其孩子列表，执行器代码不需要跟着增加一层缩进。**

这里说可以继续嵌套，是指层数由任务结构决定，不是在程序里写一个永不结束的循环；实际深度仍受 Python 调用栈等运行条件限制。

那么，同一套执行器怎样进入下一层，又怎样返回？先看它从哪里知道“这一层里面要做什么”。

#### 2.5 循环体存在 sequence 中，每一轮按顺序执行孩子


上一章存的是：

~~~text
graph[5] 页面循环：sequence = [6, 12]  # 6 = 房源循环，12 = 点击下一页；每轮先处理本页全部房源，再翻页
graph[6] 房源循环：sequence = [7]      # 7 = 判断是否为单间；每条房源都执行这个判断
graph[12] 点击下一页：sequence = []   # 没有孩子节点，只执行自身的点击操作
~~~

页面循环的一轮，可以先展开成：

~~~python
executeNode(6)      # 做完整段房源循环，等待它完成
executeNode(12)     # 再点击下一页
~~~

把固定写死的两次调用换成孩子列表遍历，就得到：

~~~python
page_node = graph[5]                      # 5 = 页面循环
count = 0
while True:
    for child in page_node["sequence"]:    # 依次取出 6（房源循环）、12（点击下一页）
        executeNode(child)                # 执行这一轮的一个孩子

    count += 1
    if count == 2:
        break
~~~

注意，下面的 `for child` 是遍历孩子节点的执行器代码，不是额外增加的业务循环。它和外层 `while` 分工如下：

| 代码 | 本例取值 | 负责什么 |
| --- | --- | --- |
| 外层 while | 页面第 1 轮、第 2 轮 | 反复执行整个循环体 |
| 内层 for | 6（房源循环）、12（点击下一页） | 一轮里面按顺序执行各个孩子 |

for 取到 6 时，会停在 executeNode(6) 这次调用上。等整段房源循环结束并返回，for 才取到 12。不能理解成调用 6 后立即启动 12。

这就把问题缩小了：不管当前容器处于第几层，都按它的 `sequence` 执行孩子。如果孩子本身也是循环，就让执行器进入那个孩子，仍然使用相同的规则。第 3 节把这件事展开，就是递归。

#### 2.6 循环定位到元素以后，由谁提取数据？

先用一个独立的小例子说明分工：**采集列表页上每条房源的标题和租金，不点击进入详情页。** 假设网页上有两张房源卡片：

~~~html
<ul>
  <li class="house">
    <h2>A：海淀单间</h2>
    <span class="rent">2500元/月</span>
  </li>
  <li class="house">
    <h2>B：海淀整租</h2>
    <span class="rent">5800元/月</span>
  </li>
</ul>
~~~

为了看清“一轮里可以执行多个流程节点”，把标题和租金分成两个提取节点，再加一个自定义操作输出处理日志。下面编号仅用于这个小例子，与后面的十三节点任务分开：

~~~text
0 root
├─ 1 打开列表页
└─ 2 循环房源卡片                       option = 8，sequence = [3, 4, 5]
   │  循环 XPath：//li[@class='house']  # 定位整张卡片
   ├─ 3 提取标题                       option = 3，sequence = []
   │    标题：相对于当前卡片的 /h2
   ├─ 4 提取租金                       option = 3，sequence = []
   │    租金：相对于当前卡片的 /span[@class='rent']
   └─ 5 自定义操作：输出本条处理完成的日志  option = 5，sequence = []
~~~

这两个提取字段都设置为相对当前循环元素提取（`relative=true`）。本例特意拆成两个提取节点：节点 3 设置 `clear=1、newLine=0`，先清空字段并暂存标题；节点 4 设置 `clear=0、newLine=1`，保留标题、补上租金，再追加完整的一行。节点 5 只输出日志，不追加采集行。标题和租金也可以合放在一个提取节点里，这里拆开是为了展示循环体中多个节点的顺序执行。

**循环回答“这一轮处理哪张卡片”，提取节点回答“从这张卡片读取哪些字段”。** 循环 XPath 只选出了 `li` 元素，不会因为选中了它，就自动知道要采标题、租金，还是图片、链接。

| 谁负责 | 本例做什么 | 交给下一步的内容 |
| --- | --- | --- |
| 循环节点 2 | 找到两张卡片，逐轮取出当前卡片，再依次执行孩子 3、4、5 | 当前元素，以及循环路径、元素索引 |
| 提取节点 3 | 在当前卡片中找标题，读取文本 | 暂存标题，不追加行 |
| 提取节点 4 | 在同一张卡片中找租金，读取文本 | 补上租金，追加包含标题和租金的一行 |
| 自定义操作节点 5 | 输出本条房源处理完成的日志 | 日志信息 |

把普通执行路径展开，就能看到“定位到元素”和“对元素做操作”是两步：

~~~text
executeNode(2)
  → loopExecute(房源卡片)
    → 按 //li[@class='house'] 找到 [卡片A, 卡片B]
    → index = 0
    │
    ├─ while 检查：0 < 2，成立
    │   → 当前元素 = 卡片A                     # 循环选中本轮对象
    │   → executeNode(3, 卡片A, 循环XPath, 0)   # 本轮第一个操作：提取标题
    │     → getData(...)
    │       → 相对卡片A 找 h2，读出“A：海淀单间”
    │       → 暂存标题，不追加行，返回
    │     → executeNode(3) 返回到循环
    │   → executeNode(4, 卡片A, 循环XPath, 0)   # 本轮第二个操作：仍然处理卡片A
    │     → getData(...)
    │       → 相对卡片A 找 span.rent，读出“2500元/月”
    │       → 保留标题、补上租金，追加完整一行，返回
    │     → executeNode(4) 返回到循环
    │   → executeNode(5, 卡片A, 循环XPath, 0)   # 本轮第三个操作：仍然处理卡片A
    │     → customOperation(...)，输出“A处理完成”的日志，返回
    │     → executeNode(5) 返回到循环
    │   → 本轮孩子 [3, 4, 5] 全部执行完，index = 1
    │
    ├─ while 检查：1 < 2，成立
    │   → 当前元素 = 卡片B
    │   → executeNode(3, 卡片B, 循环XPath, 1)   # 新一轮从第一个操作重新开始
    │     → getData(...)
    │       → 相对卡片B 找 h2，读出“B：海淀整租”
    │       → 清空上一轮字段、暂存本轮标题，不追加行，返回
    │     → executeNode(3) 返回到循环
    │   → executeNode(4, 卡片B, 循环XPath, 1)
    │     → getData(...)
    │       → 相对卡片B 找 span.rent，读出“5800元/月”
    │       → 保留标题、补上租金，追加完整一行，返回
    │     → executeNode(4) 返回到循环
    │   → executeNode(5, 卡片B, 循环XPath, 1)
    │     → customOperation(...)，输出“B处理完成”的日志，返回
    │     → executeNode(5) 返回到循环
    │   → 本轮孩子 [3, 4, 5] 全部执行完，index = 2
    │
    └─ while 检查：2 < 2，不成立，循环结束并返回
~~~

**同一轮里，变化的是第一个参数 `nodeId`：3 → 4 → 5；当前卡片、循环 XPath 和索引保持相同。三个操作全部执行完，才换成下一张卡片，再从节点 3 开始。** 因此顺序是 `A的3 → A的4 → A的5 → B的3 → B的4 → B的5`。循环的 `sequence` 还可以继续加入更多节点，每轮都会按顺序执行它们。

如果只保留循环节点，把它的 `sequence` 改成 `[]`，就只是依次取出 A、B，没有孩子负责提取，因此不会产生这两行采集记录。如果把循环里的操作换成“点击元素”，并配置为使用当前循环元素，执行的就是逐张点击；放入“判断 → 点击 → 提取”，就按这组操作处理每张卡片。**选中一个元素，不等于读取它的数据，也不等于点击它；具体动作由循环体中的节点及其参数决定。**

这里“循环只是定位元素”强调的是职责划分；完整说法是：元素列表循环负责定位、遍历和调度孩子。源码还可能把满足条件的“循环＋提取”合并为快速提取路径，直接在 `loopExecute()` 中批量读取，但读取哪些字段仍来自提取节点的配置。上面的调用链展示普通路径，便于看清这两类节点的分工。

### 3. 引出递归：孩子本身又是循环，就再次调用同一个执行函数

先明确 `executeNode()` 的角色：**它是“执行一个节点”的统一入口，也是按节点类型选择具体执行函数的分发器。** 调用者只需要把节点编号和当前循环上下文交给它；它读取节点的 `option`，再决定调用点击、输入、提取、循环还是判断函数。例如，点击交给 `clickElement()`，循环交给 `loopExecute()`，判断交给 `judgeExecute()`。

你可以把它理解为对各种操作提供了一个共同的“执行”接口：**外层只说“执行这个节点”，具体怎么执行由分发器选择的函数负责。** 这与抽象函数给人的“统一调用、不同实现”的感觉相似。不过，严格说 `executeNode()` 是一个已经写好函数体的普通方法，内部用 `if/elif` 分发；它不是等待子类重写的抽象方法。

如果孩子是点击、输入等普通操作，分发器调用具体函数，操作完成后就返回。如果孩子本身也是循环，就要先进入这个孩子，等它里面的操作全部完成，再回到外层继续。

**先只看海淀第 1 页：这一页有房源 A（单间）和 B（整租）。** 页面循环的一轮只有两件事：

1. 执行节点 **6（房源循环）**，把这一页的 A、B 都处理完。
2. 等节点 6 返回，再执行节点 **12（点击下一页）**。

下面把第一件事展开。表中的数字都是节点在 `graph` 中的数组下标，不是 `option` 类型值。

| 步骤 | 当前执行什么 | 接下来去哪里 |
| --- | --- | --- |
| 1 | **5（页面循环）** 开始第 1 轮，调用 **6（房源循环）** | 进入房源循环；页面循环等它完成 |
| 2 | **6（房源循环）** 取出房源 A，调用 **7（判断是否为单间）** | 进入对 A 的判断 |
| 3 | **7（判断）** 发现 A 是单间，选择 **8（单间分支）** | 进入单间分支 |
| 4 | **8（单间分支）** 先执行 **10（点击房源）**，再执行 **11（提取信息）** | 点击进入 A 的详情页，在详情页提取信息 |
| 5 | A 的单间分支执行完，分支返回到判断，判断再返回到**房源循环** | 房源循环恢复列表，继续处理 B |
| 6 | **6（房源循环）** 取出 B，再调用 **7（判断）**；B 是整租，选择 **9（兜底分支）** | 兜底分支没有操作，直接返回判断，再返回房源循环 |
| 7 | A、B 都处理完，**6（房源循环）** 结束 | 返回**5（页面循环）**，接着执行它的下一个孩子 |
| 8 | **5（页面循环）**调用 **12（点击下一页）** | 翻页操作返回后，第 1 轮结束；页面循环开始第 2 轮 |

**关键是第 1 步到第 7 步之间，页面循环一直等在“执行房源循环”这次调用上。** 它必须等 A、B 全部处理完，才能继续点击下一页。

到了第 2 轮，页面循环再次调用 **6（房源循环）**，这次处理第 2 页的房源 C；处理完再执行 **12（点击下一页）**，之后达到本例设定的两轮，页面循环结束。

这里的递归体现在：`executeNode()` 把房源循环交给 `loopExecute()`，而 `loopExecute()` 处理每条房源时，又调用同一个 `executeNode()` 去执行判断节点。外层和内层共用同一个分发入口，各自的执行位置由函数调用栈保存。

下面把真实的分发核心和简化的循环示意放在一起，观察“分发到循环，再由循环调用分发器”的关系。`executeNode()` 保留源码的方法签名、字段和调用参数，省略暂停、等待、日志、异常、保存及断点续采处理；这里只列本例用到的操作类型。

~~~python
def executeNode(self, nodeId, loopValue="", loopPath="", index=0):
    node = self.procedure[nodeId]  # 按数组下标取出要执行的节点

    if node["option"] == 0 or node["option"] == 10:
        # 0 = root 根节点；10 = 判断条件分支节点（由判断节点选中后执行）
        # 二者都按 sequence 的顺序执行孩子
        for i in node["sequence"]:
            self.executeNode(i, loopValue, loopPath, index)
    elif node["option"] == 1:  # 1 = 打开网页
        self.openPage(node["parameters"], loopValue)
    elif node["option"] == 2:  # 2 = 点击元素，例如点击房源、点击下一页
        self.clickElement(node["parameters"], loopValue, loopPath, index)
    elif node["option"] == 3:  # 3 = 提取数据，例如提取房源标题、租金
        self.getData(node["parameters"], loopValue, node["isInLoop"],
                     parentPath=loopPath, index=index)
    elif node["option"] == 4:  # 4 = 输入文字，例如输入当前地区
        self.inputInfo(node["parameters"], loopValue)
    elif node["option"] == 8:  # 8 = 循环，重复执行循环体中的孩子
        self.loopExecute(node, loopValue, loopPath, index)
    elif node["option"] == 9:  # 9 = 判断，检查条件并选择一个分支执行
        self.judgeExecute(node, loopValue, loopPath, index)


def loopExecute(self, node, loopValue, loopPath="", index=0):
    # 以下为循环的简化示意；每轮的取值和退出条件由循环类型决定
    while has_another_round(node, loopValue, loopPath, index):
        currentValue, currentPath, currentIndex = current_round_context(
            node, loopValue, loopPath, index)
        for i in node["sequence"]:  # 每轮按顺序执行循环体中的孩子
            self.executeNode(i, currentValue, currentPath, currentIndex)
~~~

这里的 **0 表示 root 根节点，10 表示判断条件分支节点**（例如“单间分支”“整租分支”）；二者都是按顺序执行孩子的容器。**9 才是判断节点**，由它检查各个条件并选择要执行的分支；选中某个 option=10 的分支后，再执行该分支中的孩子。

<a id="loop-context"></a>

**重点：这三个参数告诉孩子“当前这一轮正在处理谁、用什么路径定位、它在元素列表的哪个位置”。它们由当前循环为本轮准备，再传给孩子；进入更内层的循环后，内层会为自己的每一轮准备新的参数。**

`loopValue`、`loopPath`、`index` 分别传递当前循环的值（例如房源元素或地区文字）、定位路径和元素索引。上面的简化代码用 `currentValue`、`currentPath`、`currentIndex` 表示为本轮准备的这三个实参，它们共同构成执行孩子所需的循环上下文。**`nodeId` 和 `i` 选择“执行哪个节点”；后三个参数说明“这个节点本次处理什么”。**

下半段的 `loopExecute()` 是说明函数分工的伪代码，`has_another_round()`、`current_round_context()` 不是仓库中的 API；真实循环的推进、退出和历史恢复按各个 `loopType` 分支实现，单元素循环的 `while True` 写法见后文。

**例子一：地区循环把当前地区文字传给输入节点。**

节点 **3（输入地区）**的 `useLoop=true`。地区循环取到“海淀”时，传入“海淀”；下一轮取到“朝阳”时，传入“朝阳”：

~~~python
self.executeNode(3, "海淀", "", 0)  # 3 = 输入地区；本次输入“海淀”
self.executeNode(3, "朝阳", "", 0)  # 同一个输入节点；下一地区轮次输入“朝阳”
~~~

两次调用执行的是同一个节点，变化的是 `loopValue`。`inputInfo()` 看到 `useLoop=true`，就用传来的地区文字作为输入值。本例文本循环传入的 `loopPath` 是空字符串，`index` 固定为 0；**处理第二个地区也传 0，它不是“第几轮循环”的通用计数器。**

**例子二：房源循环把当前房源元素和元素位置传给判断。**

假设 `house_a`、`house_b` 分别代表 Selenium 找到的 A、B 房源链接元素。房源循环依次调用：

~~~python
self.executeNode(7, house_a, "//a[@class='house']", 0)  # 7 = 判断；当前是 A，第 1 个元素
self.executeNode(7, house_b, "//a[@class='house']", 1)  # 7 = 判断；当前是 B，第 2 个元素
~~~

| 实参位置 | 处理 A 时 | 处理 B 时 | 负责什么 |
| --- | --- | --- | --- |
| 第 1 个：nodeId | `7` | `7` | 都执行 **7（判断是否为单间）** |
| 第 2 个：loopValue | `house_a` | `house_b` | 把当前房源交给判断函数；在那里形参名是 `loopElement` |
| 第 3 个：loopPath | `//a[@class='house']` | 同一个房源列表 XPath | 说明从哪里定位这一类房源 |
| 第 4 个：index | `0` | `1` | 说明当前是匹配元素列表中的第几个；从 0 开始 |

`judgeExecute()` 就可以通过 `loopElement.text` 判断当前房源是否含“单间”：检查 A 时读 A，检查 B 时读 B。A 满足条件后，分支仍把这组参数继续传给 **10（点击房源）**：

~~~python
self.executeNode(10, house_a, "//a[@class='house']", 0)  # 10 = 点击房源；本次目标是 A
~~~

本例点击节点 `useLoop=true`、自身 `xpath=""`，所以 `clickElement()` 使用传入的列表路径，并按 `index` 选目标。其定位核心是：

~~~python
path = clickPath  # 此处 clickPath 接收的就是外面传来的 loopPath
# 本例 index=0，定位匹配列表中的第 1 个房源
elements = self.browser.find_elements(By.XPATH, path, iframe=param["iframe"])
element = elements[index]
~~~

这样既传递了当前房源供判断使用，也让后续点击能按列表路径和索引定位目标；`clickElement()` 的本分支会重新查找元素，并非直接对传进来的 `house_a` 调用点击。

**例子三：进入内层循环时，上下文会随当前处理对象改变。**

下面三次调用属于逐层进入不同循环的过程。`next_button` 表示页面循环当前找到的“下一页”元素，`house_a` 表示房源循环随后找到的 A 链接：

~~~python
# 地区循环把当前地区交给孩子 5（页面循环）
self.executeNode(5, "海淀", "", 0)

# 页面循环找到下一页元素，再把本轮上下文交给孩子 6（房源循环）
self.executeNode(6, next_button, "//a[@id='next']", 0)

# 房源循环自行查找房源链接，再把当前房源交给孩子 7（判断）
self.executeNode(7, house_a, "//a[@class='house']", 0)
~~~

**同一个 `loopValue` 参数名，在这三次调用中依次接收“海淀”文字、下一页元素、A 房源元素；`loopPath` 也从空字符串变为下一页路径，再变为房源列表路径。** 更内层的判断收到的是 A，不能因为外层正在处理海淀，就认为它收到的 `loopValue` 仍是“海淀”。

房源循环返回后，页面循环继续执行自己的下一个孩子 **12（点击下一页）**，仍使用页面循环保留的参数：

~~~python
self.executeNode(12, next_button, "//a[@id='next']", 0)  # 12 = 点击下一页
~~~

**处理 B 时，房源循环的 `index=1`，不会把外层点击下一页的 `index` 改成 1。** 每次函数调用都有自己的局部变量，外层的页面元素、路径和执行位置都保留在外层调用中。后三个参数要跟着“当前是哪一层、当前处理哪一项”来读，不能只看参数名字。

先沿着调用链看一次进入内层的过程：

~~~text
executeNode(5)
  → loopExecute(页面)
    → executeNode(6)
      → loopExecute(房源)
        → executeNode(7)
          → judgeExecute(判断)
            → executeNode(8)
              → executeNode(10)，返回
              → executeNode(11)，返回
~~~

#### 3.1 把 while 的多轮执行也展开

上面只画了“一路进入单间分支”，还没有画出循环的重复。通用规则是：**一次进入 `loopExecute()` 后，由它内部的 while 重复执行整组孩子；每个孩子返回后，才继续下一个孩子；整组孩子做完后，才进入下一轮。**

本例的孩子列表是：页面循环 `5 → [6, 12]`，房源循环 `6 → [7]`，单间分支 `8 → [10, 11]`，兜底分支 `9 → []`。因此页面循环每一轮都执行 `executeNode(6)`、`executeNode(12)`；其中节点 6 又会按本页的房源数量，多次执行 `executeNode(7)`。

下面沿用海淀的两轮页面：第 1 页有 A（单间）、B（整租），第 2 页有 C（单间）。这是**正常路径的调用展开示意**，省略等待、日志、异常等处理；页面循环的退出检查在循环体末尾，房源循环的条件检查在每轮开头。

~~~text
executeNode(5)                                      # 页面循环，只调用一次
  → loopExecute(页面)，count = 0
    │
    ├─ while True：进入第 1 轮，当前是海淀第 1 页
    │   → executeNode(6)                            # 本轮第一个孩子：处理本页全部房源
    │     → loopExecute(房源)，找到 [A, B]，index = 0
    │       │
    │       ├─ while 检查：0 < 2，成立；处理 A
    │       │   → executeNode(7)，当前房源 = A
    │       │     → judgeExecute(判断)，A 是单间，选中分支 8
    │       │       → executeNode(8)
    │       │         → executeNode(10)，点击 A，返回到 executeNode(8)
    │       │         → executeNode(11)，提取 A，返回到 executeNode(8)
    │       │         → 分支孩子执行完，返回到 judgeExecute()
    │       │       → judgeExecute() 返回到 executeNode(7)
    │       │     → executeNode(7) 返回到房源 loopExecute()
    │       │   → 按需恢复列表，index = 1
    │       │
    │       ├─ while 检查：1 < 2，成立；处理 B
    │       │   → executeNode(7)，当前房源 = B       # 同一个节点，再执行一次
    │       │     → judgeExecute(判断)，B 是整租，选中分支 9
    │       │       → executeNode(9)，没有孩子，直接返回到 judgeExecute()
    │       │       → judgeExecute() 返回到 executeNode(7)
    │       │     → executeNode(7) 返回到房源 loopExecute()
    │       │   → 按需恢复列表，index = 2
    │       │
    │       └─ while 检查：2 < 2，不成立；结束本次房源循环
    │         → 房源 loopExecute() 返回到 executeNode(6)
    │     → executeNode(6) 返回到页面 loopExecute()
    │   → executeNode(12)，点击下一页，返回到页面 loopExecute()
    │   → 本轮孩子 [6, 12] 全部执行完；count = 1，未达到 2，继续
    │
    ├─ while True：进入第 2 轮，当前是海淀第 2 页
    │   → executeNode(6)                            # 新一轮再次调用节点 6
    │     → loopExecute(房源)，重新找到 [C]，index 重新设为 0
    │       │
    │       ├─ while 检查：0 < 1，成立；处理 C
    │       │   → executeNode(7)，当前房源 = C
    │       │     → judgeExecute(判断)，C 是单间，选中分支 8
    │       │       → executeNode(8)
    │       │         → executeNode(10)，点击 C，返回到 executeNode(8)
    │       │         → executeNode(11)，提取 C，返回到 executeNode(8)
    │       │         → 分支孩子执行完，返回到 judgeExecute()
    │       │       → judgeExecute() 返回到 executeNode(7)
    │       │     → executeNode(7) 返回到房源 loopExecute()
    │       │   → 按需恢复列表，index = 1
    │       │
    │       └─ while 检查：1 < 1，不成立；结束本次房源循环
    │         → 房源 loopExecute() 返回到 executeNode(6)
    │     → executeNode(6) 返回到页面 loopExecute()
    │   → executeNode(12)，点击下一页，返回到页面 loopExecute()
    │   → 本轮孩子 [6, 12] 全部执行完；count = 2，达到 2，break
    │
    └─ 页面 loopExecute() 返回到 executeNode(5)
  → executeNode(5) 返回到调用它的外层，外层继续执行
~~~

如果配置为更多轮，页面循环就在同一次 `loopExecute(页面)` 调用中继续第 3、4……轮，每轮仍按 `[6, 12]` 执行；每次进入节点 6，都重新开始一次房源循环。这里第 2 轮仍执行点击下一页，之后才检查次数并退出，与循环体末尾的退出检查一致。

把具体房源和分支细节收起来，通用执行过程就是：

~~~text
executeNode(循环节点)
  → loopExecute(循环节点)
    → 第 1 轮：executeNode(孩子1)，返回 → executeNode(孩子2)，返回 → ……
    → 第 2 轮：executeNode(孩子1)，返回 → executeNode(孩子2)，返回 → ……
    → ……直到满足退出条件
    → loopExecute() 返回
  → executeNode(循环节点) 返回，调用它的外层继续执行

如果某个孩子也是循环：先完整执行这个孩子内部的所有轮次，再返回。
如果某个孩子是判断：只执行选中的分支，分支里的孩子全部完成后再返回。
~~~

**执行一个容器的孩子时，又调用了执行节点的同一套函数，这就自然形成递归。** EasySpider 不只存在 executeNode 直接调用自身，还存在 executeNode → loopExecute → executeNode 这样的间接递归。

重复与递归分工不同：while 让同一段循环体再做一轮；递归进入这一轮中更内层的任务。一个叶子没有孩子，操作完成就返回；一个空分支的 for 没有迭代，也直接返回。正常的有限树不会因为使用递归而无限下钻，循环能否结束则由它自己的退出机制决定。

用户可以继续嵌套第四层、第五层循环，分发函数仍然相同。也可以用显式栈实现解释器，但当前代码用函数调用栈保存执行位置，这与程序块的层次很吻合。

### 4. 完整业务的手写程序，和存下来的树一一对应

为了看清嵌套范围，可以暂时把执行器展开成只服务于这个任务的手写程序：

~~~python
open_page()
for area in ["海淀", "朝阳"]:
    input_area(area)
    click_search()

    page_count = 0
    while True:
        houses = houses_on_current_page()
        house_index = 0
        while house_index < len(houses):
            house = houses[house_index]
            if "单间" in house.text:
                click_house(house)
                extract_house()
            else:
                pass
            restore_list_page_if_needed()
            house_index += 1

        click_next_page()
        page_count += 1
        if page_count == 2:
            break
~~~

这里每个缩进块，就是上一篇某个容器的孩子列表：

~~~text
root 的两项：打开网页、地区循环
地区循环每轮的三项：输入、搜索、页面循环
页面循环每轮的两项：房源循环、下一页点击
房源循环每轮的一项：判断
被选中的单间分支的两项：点击、提取
~~~

手写程序把层数和操作写死在代码中；流程图把它们存成数据，由 executeNode、loopExecute、judgeExecute 解释。

地区循环在业务图中可以理解为“处理当前地区后检查还有没有地区”。本例配置为固定文本列表，因此实际源码用 for 遍历。页面循环配置为单元素循环，其源码才使用 while True。两种写法都反复执行各自的孩子列表，父子结构的来源相同。

下面进入实际源码，核对参数、分支选择以及每次返回的执行位置。

### 5. 同一个函数，接受不同的 nodeId

实际入口见 [easyspider_executestage.py](/source/?file=32b007a0fdf6d20e99.py)：

~~~python
self.procedure = service["graph"]
# run() 对当前待执行网址启动根节点
self.executeNode(0)
~~~

这里 `nodeId` 虽然名字带 Id，含义却是**数组下标**：

~~~python
node = self.procedure[nodeId]
~~~

调用 `executeNode(12)` 直接读 `graph[12]`，不是去寻找 `node["id"] == 12`，也不查询 `actionSequence`。

---

## 第二部分：executeNode 负责分发，容器负责组织

### 6. executeNode 是分发器：统一入口，按类型调用具体执行函数

一次调用可以拆成三步：**用 `nodeId` 取出节点 → 读取 `option` 判断操作类型 → 调用对应的执行函数，并等待它返回。** 这里两个数字的含义一定要分清：`nodeId` 回答“执行哪个节点”，`option` 回答“这个节点是什么类型”。

例如，`executeNode(12)` 中的 `12` 是“点击下一页”节点的数组下标；取出的 `graph[12]["option"]` 是 `2`，表示点击类型，所以最终调用 `clickElement()`。`executeNode(5)` 中的 `5` 是“页面循环”的数组下标；它的 `option` 是 `8`，所以调用 `loopExecute()`。

~~~text
executeNode(nodeId)                  # 统一入口：先取节点，再按 option 分发
├─ option = 1：打开网页    → openPage()
├─ option = 2：点击元素    → clickElement()
├─ option = 3：提取数据    → getData()
├─ option = 4：输入文字    → inputInfo()
├─ option = 8：循环        → loopExecute()
├─ option = 9：判断        → judgeExecute()
└─ option = 0 / 10：根节点 / 分支 → 在当前函数中按 sequence 逐个执行孩子
~~~

上图只列本例用到的类型。`executeNode()` 负责选择和调用；`clickElement()` 等函数负责具体操作，`loopExecute()` 负责循环的每轮处理，`judgeExecute()` 负责选择分支。循环或分支需要执行内部节点时，再交回统一入口 `executeNode()`，由它继续识别孩子的类型。

因此，遍历孩子的代码只需要写 `executeNode(child)`，不用在每一层循环里重新写一遍“如果是点击就调用点击函数，如果是输入就调用输入函数……”的类型判断。**操作差异集中在分发器中，嵌套层次由节点的孩子列表决定。**

第 3 节已将分发代码与循环示意合并，下面逐项对照各类节点的执行方式：

| 当前 option | 当前函数做什么 | sequence 的作用 |
| --- | --- | --- |
| 0 / 10 | root / 被选中的分支，逐个调用孩子 | 顺序执行一次 |
| 1 / 2 / 3 / 4 等 | 打开、点击、采集、输入 | 普通叶子一般为空，不靠它继续 |
| 8 | 交给 `loopExecute` | 每轮按顺序执行循环体 |
| 9 | 交给 `judgeExecute` | 依次检查候选分支，只执行首个匹配者 |

**只有执行 root、循环、分支这些容器时，才由容器主动组织孩子。**

普通点击结束后，不会读取某个“下一站”字段。是调用它的那层 `for` 恢复运行，再取自己的下一个孩子。

### 7. root 怎样执行打开网页和地区循环

从执行入口开始，按实际调用顺序把代码展开。下面每段都是对应函数的核心片段，省略等待、日志、异常和循环控制等细节，展示本例正常执行的路径。**每次调用都有自己的局部变量：不同代码段里的 `node` 指当前正在执行的节点。**

**第一步：先调用 root，root 再按顺序调用孩子。**

~~~python
# run() 中从根节点开始执行
self.executeNode(0)  # 0 = root 根节点

# 进入 executeNode() 后，此次调用的 nodeId = 0
node = self.procedure[nodeId]  # 取出 graph[0]，option = 0
if node["option"] == 0 or node["option"] == 10:
    # root 的 sequence = [1, 2]：1 = 打开网页，2 = 地区循环
    for i in node["sequence"]:
        self.executeNode(i, loopValue, loopPath, index)
        # i=1：等打开网页返回后，才取 i=2
        # i=2：等整个地区循环返回后，root 的孩子才全部执行完
~~~

这里已经出现一次直接递归：**外层的 `executeNode(0)` 调用内层的 `executeNode(1)`，返回后再调用 `executeNode(2)`。**

**第二步：孩子 1 打开网页并返回；孩子 2 进入地区循环。**

~~~python
# executeNode(1)：node 是 graph[1]（打开网页），option = 1
self.openPage(node["parameters"], loopValue)
# openPage() 完成 → executeNode(1) 返回 → root 的 for 继续取孩子 2

# executeNode(2)：node 是 graph[2]（地区循环），option = 8
self.loopExecute(node, loopValue, loopPath, index)
# 此时进入 loopExecute()；root 要等这整个调用结束
~~~

**第三步：地区循环每取一个地区，都执行“输入地区 → 点击搜索 → 页面循环”。**

下面是 `loopExecute()` 中 `loopType=3`（固定文本列表）的核心。此时 `node` 是 **2（地区循环）**：

~~~python
textList = node["parameters"]["textList"].split("\n")  # ["海淀", "朝阳"]
for text in textList:
    # sequence = [3, 4, 5]：3 = 输入地区，4 = 点击搜索，5 = 页面循环
    for i in node["sequence"]:
        self.executeNode(i, text, "", 0)
        # i=3：分发到 inputInfo()，输入本轮 text，返回后继续
        # i=4：分发到 clickElement()，点击搜索，返回后继续
        # i=5：分发到 loopExecute()，处理当前地区的页面，全部完成后返回
    # 原源码在本轮末尾还有 handleHistory() 等处理，此处省略
    # 海淀这一整轮完成后，for 才取出朝阳
~~~

这里是间接递归：`executeNode(2) → loopExecute(地区) → executeNode(5)`。对海淀的页面循环没有结束时，地区循环就一直等在孩子 **5（页面循环）** 的调用上。

**第四步：页面循环每一轮先处理全部房源，再点击下一页。**

`executeNode(5)` 再次分发到 `loopExecute()`，这次 `node` 是 **5（页面循环）**，走 `loopType=0`（单元素循环）分支。本例设置 `exitCount=2`：

~~~python
count = 0
while True:
    xpath = replace_field_values(
        node["parameters"]["xpath"], self.outputParameters, self)
    element = self.browser.find_element(
        By.XPATH, xpath, iframe=node["parameters"]["iframe"])

    # sequence = [6, 12]：6 = 房源循环，12 = 点击下一页
    for i in node["sequence"]:
        self.executeNode(i, element, xpath, 0)
        # i=6：等本页全部房源处理完并返回，才继续取 i=12
        # i=12：调用 clickElement() 点击下一页，返回后结束本轮孩子遍历

    count = count + 1
    if node["parameters"]["exitCount"] == count:
        break  # 本例做完两轮，页面循环返回到地区循环
~~~

第 1 轮处理海淀第 1 页的 A、B；第 2 轮处理第 2 页的 C。每轮末尾都执行 **12（点击下一页）**，包括第 2 轮；达到两轮后，页面循环结束。

**第五步：房源循环每取一条房源，就调用判断节点。**

`executeNode(6)` 也分发到 `loopExecute()`。此时 `node` 是 **6（房源循环）**，走 `loopType=1`（不固定元素列表）分支：

~~~python
xpath = replace_field_values(
    node["parameters"]["xpath"], self.outputParameters, self)
elements = self.browser.find_elements(
    By.XPATH, xpath, iframe=node["parameters"]["iframe"])
index = 0
while index < len(elements):
    element = elements[index]  # 海淀第 1 页：先取 A，再取 B
    for i in node["sequence"]:  # sequence = [7]：7 = 判断是否为单间
        self.executeNode(i, element, xpath, index)
        # 等这条房源的判断及其选中的分支全部执行完，才继续

    # thisHandle、thisHistoryURL、thisHistoryLength 由本次 loopExecute 的前置代码记录
    index, elements = self.handleHistory(
        node, xpath, thisHandle, thisHistoryURL, thisHistoryLength,
        index, elements=elements)
    index = index + 1  # 恢复列表后，推进到下一条房源
# 本页元素处理完，loopExecute() 返回，再由 executeNode(6) 返回到页面循环
~~~

这里的 `index` 是 A、B 在元素列表中的位置；`i=7` 才是判断节点的编号。

**第六步：判断选中一个分支，分支再顺序执行自己的孩子。**

`executeNode(7)` 读到 `option=9`，把当前房源交给 `judgeExecute()`：

~~~python
# executeNode(7) 内：7 = 判断节点
self.judgeExecute(node, loopValue, loopPath, index)

# judgeExecute() 内：先检查条件，选出 executeBranchId（条件检查代码省略）
# 当前是 A（单间）时，选中 8 = 单间分支
# 当前是 B（整租）时，选中 9 = 兜底分支
if executeBranchId != 0:
    self.executeNode(executeBranchId, loopElement, clickPath, index)
~~~

对 A，判断调用 `executeNode(8)`。**节点编号 8 是单间分支，它的类型是 `option=10`**，所以回到分发器中与 root 共用的“顺序执行孩子”代码：

~~~python
# executeNode(8) 内：node 是 graph[8]（单间分支）
if node["option"] == 0 or node["option"] == 10:
    # sequence = [10, 11]：10 = 点击房源，11 = 提取信息
    for i in node["sequence"]:
        self.executeNode(i, loopValue, loopPath, index)
        # i=10：option=2 → clickElement()，进入 A 的详情页，做完返回
        # i=11：option=3 → getData()，提取 A 的详情，做完返回
# 孩子全部执行完，executeNode(8) 返回到 judgeExecute()
~~~

对 B，判断调用 **9（兜底分支）**，它同样是 `option=10`，但 `sequence=[]`，因此没有孩子可执行，直接返回。

**第七步：内层做完，逐层返回，外层从原来的调用位置继续。**

处理完 A 的点击和提取后，单间分支返回到判断；判断返回到房源循环，房源循环恢复列表并继续处理 B。A、B 都处理完后，房源循环才返回到页面循环，页面循环接着执行 **12（点击下一页）**。

海淀的两轮页面全部结束后，页面循环返回到地区循环；地区循环再取“朝阳”，重复输入、搜索、处理页面的过程。两个地区都处理完后，地区循环返回到 root；root 的孩子遍历结束，`executeNode(0)` 返回。

这里的“等待返回”是普通函数调用的行为：程序在执行更内层的函数，外层保留自己的循环位置，等内层返回后继续。

### 8. 返回地址在哪里

处理海淀第 1 页的 A 时，调用关系可以画成：

~~~text
executeNode(0) root
└─ executeNode(2) 地区循环
   └─ loopExecute(地区)
      └─ executeNode(5) 页面循环
         └─ loopExecute(页面)
            └─ executeNode(6) 房源循环
               └─ loopExecute(房源)
                  └─ executeNode(7) 判断
                     └─ judgeExecute(判断)
                        └─ executeNode(8) 单间分支
                           ├─ executeNode(10) 点击 A
                           └─ executeNode(11) 提取 A
~~~

每一层函数调用都有自己的局部变量、循环位置和返回位置。Python 调用栈保留这些信息。

把这一轮的几个暂停位置具体写出来。这里说“暂停位置”，是指等待子函数返回的代码位置；程序仍在执行更内层的操作。

| 当前函数调用 | 本次调用保留的状态 | 下一步什么时候发生 |
| --- | --- | --- |
| 地区的 loopExecute | 当前文本是海淀，孩子遍历到 5 | 页面循环全部返回后，才能换朝阳 |
| 页面的 loopExecute | 本轮尚未计入 count，孩子遍历到 6 | 房源循环全部返回后，才取孩子 12 |
| 房源的 loopExecute | 当前链接 A，列表 index=0，孩子为 7 | 判断返回并恢复列表后，才推进到 B |
| 判断的 judgeExecute | 已选中分支 8 | 等整条分支执行完，才返回房源循环 |
| 分支的 executeNode(8) | sequence=[10,11]，先遍历到 10 | 点击返回后，取 11；提取返回后，结束本层 for |

页面循环和房源循环虽然都调用 loopExecute，仍然是两次独立的函数调用。页面的 count 与房源的 index 分别保留在各自的调用中；进入内层不会把外层的循环位置覆盖掉。

提取 A 返回后：

~~~text
11 返回到 8 的 for
8 已没有其他孩子，返回到 judgeExecute
judgeExecute 返回到 executeNode(7)
7 返回到房源循环这一轮
房源循环进行历史/标签页处理，再取 B
~~~

因此不用存：

~~~text
11.next = 6
8.next = 7
7.next = 6
~~~

JSON 描述“谁包含谁”；Python 调用栈记录“这次调用回来以后，程序接着做什么”。

接着执行 B 时，页面那层仍然等待孩子 6 返回。B 不满足单间条件，空分支 9 返回后，房源列表的 index 从 1 推进到 2，while 条件不再满足，整个房源循环才返回到页面循环的 for。这个 for 才取到 12。

12 点击返回后，页面循环的 for 结束，count 从 0 增加到 1，while 开始下一轮。第二轮重新调用 executeNode(6)，会建立一次新的房源循环调用，从当前页的 C 开始。

---

## 第三部分：三个循环传的是三种上下文

### 9. 地区循环：把文本交给输入节点

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 3,
  "textList": "海淀\n朝阳"
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

设置：

~~~json
{
  "option": 8,
  "sequence": [3, 4, 5],
  "parameters": {
    "loopType": 3,
    "textList": "海淀\n朝阳"
  }
}
~~~

`loopType=3` 是固定文本列表。源码核心：

~~~python
textList = node["parameters"]["textList"].split("\n")
for text in textList:
    text = replace_field_values(text, self.outputParameters, self)
    for i in node["sequence"]:
        self.executeNode(i, text, "", 0)
~~~

这里省略 `skipCount`、break/continue、脚本退出和历史处理。当 `i=3` 时，孩子是输入节点（`option=4`），`executeNode()` 会进入原源码的输入分支：

~~~python
elif node["option"] == 4:  # 输入文字
    self.inputInfo(node["parameters"], loopValue)
~~~

也就是把本轮的 `text` 作为 `loopValue` 传给 `inputInfo()`。海淀这一轮：

~~~text
executeNode(3, "海淀", "", 0)
executeNode(4, "海淀", "", 0)
executeNode(5, "海淀", "", 0)
~~~

输入节点 3 设置 `useLoop=true`。`inputInfo()` 中：

~~~python
if param["useLoop"]:
    value = loopValue
else:
    value = param["value"]
~~~

随后，原源码对 `value` 做字段替换、`<enter>` 标记和取值索引处理，得到 `replaced_text`，最后真正执行 Selenium 输入的是这一句：

~~~python
textbox.send_keys(replaced_text)
~~~

完整流程是：`for text` 取出“海淀” → `executeNode(3, text, "", 0)` → `inputInfo(..., loopValue)` → `value = loopValue` → `textbox.send_keys(replaced_text)`。下一轮同样输入“朝阳”。这里的 `textbox` 是 `inputInfo()` 按输入节点 XPath 找到并清空的输入框；本例普通文本处理后仍是“海淀”或“朝阳”。

所以输入的不是固定 `parameters.value`，而是本轮传进来的地区。点击搜索等其他孩子按自己的 `option` 执行，并不是每次 `executeNode()` 都调用 `send_keys()`。以上输入分支和输入语句均摘自 [easyspider_executestage.py](/source/?file=32b007a0fdf6d20e99.py)。

### 10. 页面循环：一轮处理整页，然后点击下一页

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[5].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 0,
  "xpath": "//a[@id='next']",
  "exitCount": 2
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

设置：

~~~json
{
  "option": 8,
  "sequence": [6, 12],
  "parameters": {
    "loopType": 0,
    "xpath": "//a[@id='next']",
    "exitCount": 2
  }
}
~~~

`loopType=0` 是单元素循环。把源码外围的 while 也列出来，正常路径的控制流骨架是：

~~~python
count = 0
while True:                         # 源码注释：do while循环
    # 本轮停止检查、文本变化检查、try/except 等在此省略
    element = self.browser.find_element(
        By.XPATH, xpath, iframe=node["parameters"]["iframe"])
    for i in node["sequence"]:       # 本例依次执行 6、12
        self.executeNode(i, element, xpath, 0)
        # 源码还在这里检查 BREAK / CONTINUE

    count = count + 1
    if node["parameters"]["exitCount"] == count:
        break
    # 源码还在这里检查脚本退出条件
~~~

这正是开头推导的两层组织方式：while 管轮次，for 管本轮的孩子顺序，executeNode 管一个孩子的具体含义。取到 6 后，它会进入另一层 loopExecute；取到 12 后，它执行一次普通点击并返回。

本轮先找出下一页按钮，作为当前循环元素，然后：

~~~text
executeNode(6, 下一页按钮, 下一页XPath, 0)
    → 房源循环自行查找当前页的所有房源
    → 逐个判断、可能点击与采集
    → 整个房源循环返回
executeNode(12, 下一页按钮, 下一页XPath, 0)
    → 用循环定位上下文点击下一页
~~~

节点 12 应配置 `useLoop=true`。`exitCount=2` 限制的是**循环体执行两轮**；循环体末尾的点击也会执行两次。它不是“最多翻一次所以恰好停在第二页”。

### 11. 房源循环：把当前链接交给判断

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[6].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 1,
  "xpath": "//a[@class='house']"
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

设置：

~~~json
{
  "option": 8,
  "sequence": [7],
  "parameters": {
    "loopType": 1,
    "xpath": "//a[@class='house']"
  }
}
~~~

正常路径的源码骨架：

~~~python
elements = self.browser.find_elements(By.XPATH, xpath,
                                      iframe=node["parameters"]["iframe"])
index = 0
while index < len(elements):
    element = elements[index]
    for i in node["sequence"]:
        self.executeNode(i, element, xpath, index)
    index, elements = self.handleHistory(
        node, xpath, thisHandle, thisHistoryURL, thisHistoryLength,
        index, elements=elements)
    index = index + 1
~~~

第一次传 A：

~~~text
executeNode(7, A元素, 房源列表XPath, 0)
~~~

第二次传 B：

~~~text
executeNode(7, B元素, 房源列表XPath, 1)
~~~

这里 `index` 是当前房源在匹配列表中的位置，**不是流程图节点下标**。

三个循环都用 `loopValue` 这个参数名，但实际值随当前调用层变化：

| 调用位置 | loopValue | loopPath | index |
| --- | --- | --- | --- |
| 输入地区 3 | “海淀”文本 | 空串 | 0 |
| 页面循环体中的下一页点击 12 | 下一页按钮元素 | 下一页 XPath | 0 |
| 判断 7 和房源点击 10 | A 或 B 链接元素 | 房源列表 XPath | 0 或 1 |

内层循环会建立自己的上下文。需要外层地区值时，不能假定判断里的 `loopValue` 仍是“海淀”。

---

## 第四部分：判断怎样只执行一条分支

### 12. 从左往右检查条件，执行第一条满足条件的分支

#### 12.1 先把规则讲清楚：检查条件，然后执行选中的分支

一个判断框下面可以有多条分支，**每条分支都有自己的条件和自己的操作内容**。执行到判断节点时，程序按照界面上从左到右的分支顺序检查条件；在数据中，这个顺序保存在判断节点的 `sequence` 中。

具体过程是：

1. 先检查最左边分支的条件。
2. 条件不满足，就跳过这条分支里的全部操作，继续检查右边的下一条分支。
3. 条件满足，就记住这条分支，并停止检查后面的分支。
4. 按顺序执行选中分支里面的操作；操作全部完成后，这次判断结束，返回调用它的外层代码。
5. 如果所有条件都不满足，就不执行任何分支，直接结束这次判断并返回。

**每次执行判断节点，最多选中一条分支。选中的分支做完后，就返回外层，后面的其他分支不再检查，也不再执行。** 如果选中的是空分支，由于里面没有操作，会直接返回。

把它对应到代码，可以理解为一组 `if / elif / else`：前面的条件成立后，只执行前面那一段；前面的条件不成立，才轮到后面的条件。

#### 12.2 本例的结构：判断框管“选谁”，分支框管“选中后做什么”

继续使用海淀第 1 页的房源 A（单间）和 B（整租）。本例判断节点为 **7（判断是否为单间）**，下面从左到右放了两条分支：

| 从左到右的位置 | 分支节点 | 分支条件 | 选中后执行什么 |
| --- | --- | --- | --- |
| 左边第 1 条 | **8（单间分支）** | 当前房源元素的文字包含“单间” | **10（点击房源）**，然后 **11（提取信息）** |
| 右边第 2 条 | **9（兜底分支）** | 无条件；前面的分支未选中时走到这里就会满足 | 没有孩子操作，直接返回 |

对应的节点数据如下。**以下编号都是 `graph` 的数组下标，每个编号后面都写出对应操作：**

~~~text
graph[7] 判断是否为单间：
    option = 9                   # 判断节点，负责选择一条分支
    sequence = [8, 9]            # 8 = 单间分支（左），9 = 兜底分支（右）

graph[8] 单间分支：
    option = 10                  # 条件分支节点，选中后顺序执行自己的孩子
    parameters.class = 3         # 条件类型：当前循环元素的文字包含指定文本
    parameters.value = "单间"    # 要查找的文本
    sequence = [10, 11]          # 10 = 点击房源，11 = 提取信息

graph[9] 兜底分支：
    option = 10                  # 同样是条件分支节点
    parameters.class = 0         # 条件类型：无条件，走到这里就满足
    sequence = []                # 没有操作，选中后直接返回
~~~

这里要区分两种 `sequence`：**判断节点的 `[8, 9]` 是候选分支的检查顺序；单间分支的 `[10, 11]` 才是选中后要依次执行的操作。** 检查分支条件时，还没有执行点击或提取。

条件保存在各个分支的 `parameters` 中。例如，下面从[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) 的 `graph[8].parameters` 摘出原值：

~~~json
{
  "class": 3,
  "value": "单间"
}
~~~

`option` 区分节点是判断还是分支；`parameters.class` 区分分支采用哪种条件。**`option=9` 表示判断节点，`option=10` 表示条件分支节点，`class=3` 表示检查当前循环元素的文字。**

房源循环每次只把当前这条房源作为 `loopElement` 传进来：处理 A 时检查 A 的文字，处理 B 时检查 B 的文字。如果用 `class=1`，检查的则是整个页面的 body；列表上 A 含有“单间”，可能导致处理整租 B 时也误以为满足条件。

此 JSON 是房源教学模型，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

#### 12.3 先用本例写成容易读的 if / else

假定房源循环已经把当前房源交给 `judgeExecute()`，那么本例的业务效果可以写成下面这样。**这是按本例配置展开的等价示意：**

~~~python
if "单间" in loopElement.text:  # 当前房源满足左边单间分支的条件
    self.executeNode(8, loopElement, clickPath, index)  # 8 = 单间分支
    # 分支内部顺序执行：10（点击房源）→ 11（提取信息）
else:                         # 左边未满足，右边兜底分支无条件满足
    self.executeNode(9, loopElement, clickPath, index)  # 9 = 兜底分支
    # 兜底分支 sequence=[]，没有操作，直接返回
# 选中的分支返回后，本次判断结束，返回房源循环
~~~

真实执行器允许用户添加任意多条分支，所以源码用 `for` 依次检查分支数据，实现这组 `if / elif / else` 的选择效果。

#### 12.4 对照真实源码：for 检查顺序，break 保证只选一条

下面摘取 [easyspider_executestage.py](/source/?file=32b007a0fdf6d20e99.py) 的 `judgeExecute()` 核心，保留本例使用的 `class=0` 和 `class=3` 两种条件；省略其他条件类型及暂停、异常处理和日志：

~~~python
def judgeExecute(self, node, loopElement, clickPath="", index=0):
    executeBranchId = 0  # 尚未选中分支；这里的 0 是初始标记，不是要执行 root

    # node 是 graph[7]（判断节点）
    for i in node["sequence"]:  # [8, 9]：先检查单间分支，再检查兜底分支
        cnode = self.procedure[i]  # 取出当前候选分支，此时还没执行分支内的操作
        tType = int(cnode["parameters"]["class"])  # 读取当前分支的条件类型

        if tType == 0:  # 无条件：走到此分支就满足
            executeBranchId = i  # 记住选中的分支
            break                # 停止检查后面的分支
        elif tType == 3:  # 当前循环元素的文字是否包含指定文本
            value = replace_field_values(
                cnode["parameters"]["value"], self.outputParameters, self)
            if loopElement.text.find(value) >= 0:  # 包含文本，条件满足
                executeBranchId = i
                break
            # 不包含时，既不选中，也不执行这条分支，for 继续检查下一条

    # 离开检查条件的 for 后，才执行选中的分支
    if executeBranchId != 0:
        self.executeNode(executeBranchId, loopElement, clickPath, index)
    # 真实源码在未选中任何分支时还会记录日志；随后本次调用返回
~~~

这里分成两个阶段：

| 阶段 | 代码 | 负责什么 |
| --- | --- | --- |
| 选择分支 | `for i in node["sequence"]`，满足时赋值并 `break` | 从左到右检查，记住第一条满足条件的分支 |
| 执行分支 | `self.executeNode(executeBranchId, ...)` | 进入选中的分支，执行它里面的孩子操作 |

**`break` 结束的是“检查分支条件”的这个 `for`。** 它不会退出房源循环，也不会跳过已经选中的分支；跳出检查后，程序紧接着调用 `executeNode()` 执行那条分支。

#### 12.5 展开 A：第一个条件满足，点击并提取，然后返回

房源循环取出 A，调用 **7（判断是否为单间）**。A 的文字包含“单间”，这次执行的过程如下：

| 步骤 | 执行过程 | 结果 |
| --- | --- | --- |
| 1 | 初始化 `executeBranchId=0` | 尚未选中分支 |
| 2 | `for` 取到 **8（单间分支）** | 读取它的 `class=3`、`value="单间"` |
| 3 | 检查 A 的文字是否包含“单间” | 满足条件，设置 `executeBranchId=8` |
| 4 | 执行 `break` | 结束分支检查，**9（兜底分支）不再检查** |
| 5 | 调用 `executeNode(8)` | 进入单间分支，依次执行 **10（点击房源）**、**11（提取信息）** |
| 6 | 单间分支的两个孩子都完成 | 分支返回到判断，判断再返回房源循环 |

第 5 步中，分发器读到单间分支的 `option=10`，所以运行第 3 节已经介绍过的容器代码：

~~~python
# 此时 node 是 graph[8]（单间分支），option = 10
if node["option"] == 0 or node["option"] == 10:
    for i in node["sequence"]:  # [10, 11]：10 = 点击房源，11 = 提取信息
        self.executeNode(i, loopValue, loopPath, index)
        # 点击房源返回后，再调用提取信息；提取完成后，本分支才返回
~~~

A 的分支做完后，这次判断就结束了。**不会因为单间分支执行完，再回头执行右边的兜底分支。** 房源循环收到返回后恢复列表，再处理 B。

#### 12.6 展开 B：第一个条件不满足，继续检查右边的兜底分支

处理 B 时，房源循环会重新调用一次判断函数，`executeBranchId` 也重新从 0 开始，不沿用处理 A 时的选择。B 是整租，文字不包含“单间”：

| 步骤 | 执行过程 | 结果 |
| --- | --- | --- |
| 1 | 检查 **8（单间分支）**的“包含单间”条件 | 不满足，**不点击 B，也不提取 B** |
| 2 | 没有执行 `break`，`for` 继续取 **9（兜底分支）** | 读取到 `class=0`，无条件满足 |
| 3 | 设置 `executeBranchId=9`，执行 `break` | 选择兜底分支并结束条件检查 |
| 4 | 调用 `executeNode(9)` | 兜底分支的 `sequence=[]`，没有孩子可执行 |
| 5 | 空分支返回到判断，判断再返回房源循环 | 这条房源处理完成，房源循环继续 |

这里“没有采集 B”来自**单间条件不满足，而且兜底分支没有放任何操作**。如果在兜底分支里放一个“记录跳过原因”的操作，处理 B 时就会执行那个操作，然后返回。

#### 12.7 多个条件都满足、全部不满足时，分别会怎样

**多个条件都满足：执行最左边第一条满足条件的分支。** 例如另外设计一个三分支判断，从左到右分别是“包含单间”“包含海淀”“无条件兜底”，当前房源 A 的文字同时包含“海淀”和“单间”：

| 从左到右的分支 | 如果单独检查，条件是否满足 | 本次实际是否检查、执行 |
| --- | --- | --- |
| 包含“单间” | 满足 | 检查后选中，执行这一条分支的内容 |
| 包含“海淀” | 满足 | 前一条已选中，不再检查，不执行 |
| 无条件兜底 | 满足 | 前一条已选中，不再检查，不执行 |

如果把“包含海淀”移到“包含单间”的左边，A 就会执行“包含海淀”那条分支的内容。**分支排列顺序也就是条件检查的优先顺序。** 这个三分支配置只是补充说明选择规则，未修改原房源教学模型。

**全部条件都不满足：本次判断不执行任何分支，返回外层继续。** 例如删除原例的兜底分支，只保留 **8（单间分支）**，则判断节点的 `sequence=[8]`。处理整租 B 时，单间条件不满足；`for` 遍历完后 `executeBranchId` 仍为 0，因而不会调用任何分支。源码记录“所有条件分支的条件都不满足”的日志后返回，房源循环继续处理下一项。

**兜底分支要放在最后。** 它是配置为 `class=0` 的普通条件分支，用“无条件满足”实现 `else` 的效果。如果把原例改成 `sequence=[9, 8]`，先检查的 **9（兜底分支）**总会满足，随即 `break`；后面的 **8（单间分支）**就没有机会被检查，A 也不会被点击和提取。

### 13. 孩子返回父循环，与浏览器回到列表是两件事

无论本次选中单间分支、选中空的兜底分支，还是没有条件满足，**判断结束后都会沿函数调用返回到房源循环，再由房源循环继续当前这一轮的后续代码。** 对 A，必须先完成点击与提取；对 B，空分支直接返回。

把房源循环中接收返回的位置写出来：

~~~python
# node 是 graph[6]（房源循环），element 是当前房源
for i in node["sequence"]:  # [7]：7 = 判断是否为单间
    self.executeNode(i, element, xpath, index)
    # 当前房源的判断及其选中分支全部返回后，程序才继续到这里

# 本轮孩子全部返回后，恢复浏览器页面，再推进到下一条房源
# 下面三个历史记录变量由本次 loopExecute 的前置代码准备
index, elements = self.handleHistory(
    node, xpath, thisHandle, thisHistoryURL, thisHistoryLength,
    index, elements=elements)
index = index + 1
~~~

**函数返回负责恢复代码的执行位置，`handleHistory()` 负责处理浏览器页面和标签页。** Python 函数返回并不会自动关闭详情标签页或把网页导航回列表。因此，处理 A 的顺序是：进入详情并提取 → 分支和判断返回 → 房源循环恢复列表 → 推进到 B。B 的空分支返回后，房源循环同样会走本轮的历史处理与索引推进。

等本页 A、B 都处理完，整个房源循环才返回到页面循环，页面循环接着执行 **12（点击下一页）**。判断分支的选择，只决定当前房源做哪些操作；页面循环后续的翻页顺序仍由它自己的孩子列表决定。

新标签页怎样关闭、同页详情怎样回退、没有新增历史时怎样处理，以及列表元素何时需要重新获取，统一在[第 17 篇第 24 节：handleHistory 专题](/easyspider/chapter-17#handle-history)结合 Selenium 核心源码展开。

---

## 第五部分：把五个房源完整手算一遍

### 14. 正常路径的节点进入记录

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

为便于对照，只列 `executeNode` 进入的数组下标，不列外围等待和浏览器恢复函数：

~~~text
0 root
1 打开网页
2 地区循环

海淀：
    3 输入海淀
    4 点击搜索
    5 页面循环
      第 1 轮：
        6 房源循环
          A：7 → 8 → 10 → 11
          B：7 → 9
        12 点击下一页
      第 2 轮：
        6 房源循环
          C：7 → 8 → 10 → 11
        12 点击下一页
    页面循环返回到地区循环

朝阳：
    3 输入朝阳
    4 点击搜索
    5 页面循环
      第 1 轮：
        6 房源循环
          D：7 → 9
        12 点击下一页
      第 2 轮：
        6 房源循环
          E：7 → 8 → 10 → 11
        12 点击下一页
    页面循环返回到地区循环

地区循环结束
root 返回，当前网址这一轮任务结束
~~~

得到三条房源记录：A、C、E。不是五条，也不是每页只有第一条。

按操作次数核对：

| 操作 | 次数 | 原因 |
| --- | --- | --- |
| 打开网页 1 | 1 | root 的第一项 |
| 输入地区 3 / 点击搜索 4 | 各 2 | 两个地区 |
| 进入房源循环 6 | 4 | 两地区，每地区两页 |
| 进入判断 7 | 5 | 五个链接 |
| 单间分支 8 / 房源点击 10 / 提取 11 | 各 3 | A、C、E 满足 |
| 兜底分支 9 | 2 | B、D 不满足 |
| 下一页点击 12 | 4 | 每轮页面循环的末项 |

### 15. 对照原图蓝色 1–16 标号

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

![房源采集：服务流程、层次封装与执行树](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%88%BF%E6%BA%90%E9%87%87%E9%9B%86-%E6%B5%81%E7%A8%8B%E4%B8%8E%E6%89%A7%E8%A1%8C%E6%A0%91-%E5%8E%9F%E7%89%88.png)

原图蓝色数字标的是**进入、交接和返回阶段**，不是 nodeList 下标，也不是 BFS 编号。

| 原图阶段 | 在本例中怎样理解 |
| --- | --- |
| 1–2 | root 先打开网页，再进入地区循环 |
| 3–5 | 输入地区、搜索，进入页面循环 |
| 6–7 | 进入房源循环，再进入判断 |
| 8 | 判断选择一个分支；左右两边代表不同条件结果 |
| 9–10 | 单间执行点击和提取；非单间是空操作占位 |
| 11–12 | 分支、判断返回到房源循环，继续下一条 |
| 13–14 | 房源处理完后点击下一页，页面循环继续 |
| 15 | 页面循环结束，回到地区循环 |
| 16 | 地区处理完，返回 root |

这些阶段会重复发生。比如 7–12 对 A、B、C 都可能发生，不是一张图只走一次。

---

## 第六部分：别把正常示例读成源码保证

### 16. 页面循环的退出和异常必须按当前代码理解

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[5].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 0,
  "xpath": "//a[@id='next']",
  "exitCount": 2,
  "exitElement": "//body",
  "breakMode": 0
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

实际 `loopType=0` 还包含：

- `exitCount=0` 时，比较 `exitElement` 的文本是否变化；
- `exitCount>0` 时，正常轮次完成后按计数退出；
- 找不到单个循环元素时，走 `NoSuchElementException` 路径；
- `BREAK / CONTINUE`、脚本条件和停止信号。

当前找不到元素的路径中：

~~~python
for i in node["sequence"]:
    if node["option"] != 2:
        self.executeNode(i, None, xpath, 0)
break
~~~

这里判断的是**循环父节点的 option**，父节点是 8，所以并没有按注释所说过滤掉点击孩子。不能把它讲成“精确跳过下一页点击”。

找不到按钮时，本例可能再次尝试执行整个循环体，点击节点也会被尝试；具体错误由后续函数处理。因此前面的次数表明确只描述“两轮都能找到按钮”的正常路径。

如果要设计真实“最多采两页”的任务，需要核对最后一页按钮状态、列表是否变化及停止条件，不能直接把图里的业务菱形当成执行器里已有的独立判断节点。

### 17. BFS 画图和递归执行，顺序为什么不同

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

本例界面 BFS 下标序列会是：

~~~text
0,1,2,3,4,5,6,12,7,8,9,10,11
~~~

但执行 A 时会先进入 `7,8,10,11`，等所有房源做完才进入 12。

BFS 为的是先有父容器再画孩子；递归执行为的是先完成一段业务，再回到同级下一项。判断还会跳过未选中的子树，循环会多次执行同一子树。

所以正式执行既不是遍历 `nodeList` 一遍，也不是按照 `actionSequence` 的排列跑一遍。

### 18. 带着这几个问题读源码

**从文件读取的参数示例**：[房源采集-教学模型.json](/source/?file=ce174a47484f884969.json) → `graph[6].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 1,
  "xpath": "//a[@class='house']",
  "historyWait": 2
}
~~~

此文件是**房源教学模型**，用于结构与控制流推演；可导入任务的参数另见后面的真实任务专题。

1. 谁反复执行 `6.sequence`？谁只执行 `8.sequence` 一次？
2. 单间提取结束后，哪个函数让浏览器回到列表？
3. 判断 B 时为什么不能检查 body 是否包含“单间”？
4. 为什么 12 的界面编号可能小于 7，却比 7 晚执行？
5. `executeNode(12)` 中的 12 和列表循环的 `index=1` 有何区别？

参考答案：房源的 `loopExecute` 与分支的 `executeNode`；`handleHistory`；body 范围太大；编号按 BFS，执行按结构；前者是节点数组下标，后者是当前匹配元素的位置。

后面的消息、渲染、编辑与保存，都要保持这份执行结构的含义。

---

## 第七部分：循环与条件的执行细节

### 19. 不固定列表、固定路径、文本、网址与命令循环

**从文件读取的参数示例**：[最简单的翻页采集列表.json](/source/?file=ab9654935e2535e491.json) → `graph[7].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 1,
  "xpath": "/html/body/div[1]/div[5]/div[1]/div[1]/div[2]/ul[1]/li/a[1]"
}
~~~

**从文件读取的参数示例**：[112.json](/source/?file=04ddae11bfef4618b8.json) → `graph[11].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 2,
  "pathList": "//*[contains(@class, \"pagination\")]/ul[1]/li[1]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[2]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[3]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[4]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[5]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[6]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[7]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[8]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[9]/a[1]"
}
~~~

**从文件读取的参数示例**：[Exec and Eval.json](/source/?file=b473d006c6fd3bdc39.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": "3",
  "textList": "1\n1\n1\n1\n1\n1\n1\n"
}
~~~

先对照前三种输入形式：一条 XPath 找整组元素，多条 XPath 每条找一项，一段换行文本每行当循环值。它们最后都执行同一个 sequence，但传下去的上下文不同。

| loopType | 如何取本轮值 | 传给孩子的 loopValue / loopPath / index |
| --- | --- | --- |
| 0 | 重复定位同一个元素 | WebElement / 当前 xpath / 0 |
| 1 | 查整组 elements，逐位置处理 | WebElement / 共同 xpath / 元素 index |
| 2 | pathList 按换行拆分 | WebElement / 当前单条 path / 0 |
| 3 | textList 按换行拆分并替换字段 | 字符串 / 空路径 / 0 |
| 4 | textList 拆成网址列表、过滤空行 | URL 字符串 / 空路径 / 0 |
| 5 | 执行页面 JavaScript，返回码 >0 才进本轮 | 返回码 / 配置 xpath / 0 |
| 6 | 执行系统命令，按返回文本转换成返回码 | 返回码 / 配置 xpath / 0 |
| 7 | 执行 Python eval，返回码 >0 才继续 | 返回码 / 配置 xpath / 0 |

单元素循环并不调用每项历史恢复；它就是为了让点击下一页后的页面留在下一页。不固定/固定元素循环在正常轮末调用 handleHistory；文本循环也调用，固定网址循环没有这个轮末调用。不能说所有循环都会自动退回起始页。

`skipCount` 由预处理补 0，可跳过开始项；当前文本/网址分支的局部 index 不在每个正常轮末递增，所以这个分支的跳过行为有实现限制，不能按元素列表循环类推。空行规则也不同：网址列表过滤空行，普通多行文本可能保留尾部空项。

#### 19.1 固定网址与命令循环的真实参数

**从文件读取的参数示例**：[15.json](/source/?file=06d8d29c05652251e9.json) → `graph[6].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": "4"
}
~~~

**从文件读取的参数示例**：[52.json](/source/?file=1d807d2ab2eb77d73f.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": "5",
  "code": "return window.innerHeight > 200",
  "waitTime": 0
}
~~~

**从文件读取的参数示例**：[172.json](/source/?file=f04b25b31f7791464d.json) → `graph[9].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": "7",
  "code": "self.tb < 20",
  "waitTime": 0
}
~~~

15 任务 `loopType="4"` 的网址存于 textList，不是另一个 urlList 数组；每轮把网址传给 `useLoop=true` 的打开网页孩子。52 的页面 JS `return window.innerHeight > 200` 返回真值时反复执行循环体：若孩子不改变窗口高度，这个条件不会自己变假。

172 的 Python 循环条件 `self.tb < 20` 配合孩子里的 `self.tb += 1` 推进，体现“循环体负责改变条件依赖的状态”。系统命令循环则使用模式 1 获取 stdout，再由 get_output_code 转为控制码；不是直接读取进程 exit code。

命令循环每轮在孩子之前判断，≤0 就停止；单元素循环的计数与 breakCode 在正常循环体之后检查。两者不能都解释成统一的 do-while 语义。

### 20. 九种条件的真实 class 与代码模式映射

**从文件读取的参数示例**：[JS判断条件示例.json](/source/?file=b617a7a96e2e83298f.json) → `graph[8].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "class": "7",
  "code": "return arguments[0].nextElementSibling.nextSibling.innerText.includes(\"免费资源\") && !arguments[0].innerText.includes(\"上一页\")",
  "waitTime": 0
}
~~~

**从文件读取的参数示例**：[Exec and Eval.json](/source/?file=b473d006c6fd3bdc39.json) → `graph[7].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "class": "8",
  "code": "self.myVar == self.outputParameters[\"检测字段\"]",
  "waitTime": 0
}
~~~

JS 示例 class="7" 表示针对循环项执行 JS，`arguments[0]` 是当前链接，检查相邻文字包含免费资源且不是上一页；只有满足时才执行它的 `[5,6]`（点击、提取）。Exec and Eval 示例 class="8" 实际调用 Python eval，比较 self.myVar 与已提取的检测字段，不能沿用旧讲义“针对元素的系统命令”这一说法。

| class | 条件与执行位置 |
| --- | --- |
| 0 | 无条件兜底 |
| 1 | 当前页面 body 包含 value 文本 |
| 2 | 当前页面存在 value XPath 的元素 |
| 3 | 当前 loopElement.text 包含 value |
| 4 | 当前 loopElement 内存在元素；源码对 value 先取 `[1:]` 再查 |
| 5 | 页面 JS，execute_code(0) |
| 6 | 系统命令，execute_code(1) |
| 7 | 针对当前循环元素 JS，execute_code(2, loopElement) |
| 8 | Python eval，execute_code(6, loopElement) |

命令结果转字符串，包含 `rue` 则当作 1，否则尝试 int；结果 >0 即满足。不是与某个另存的布尔值做严格相等比较。匹配首项后 break，再 executeNode(选中分支)。

试运行时 trial.js 有条件预览，显示满足/不满足；它是在设计页面给反馈，不等于 Python 已执行了整个分支或完成数据写盘，反向链路见第 24、25 篇。

BREAK / CONTINUE 的实现代码和完整例子见[第 17 篇第 30 节](/easyspider/chapter-17#break-continue)。

## 第八部分：正式执行器生命周期

### 21. 初始化与预处理：把磁盘参数准备成运行期数据

**从文件读取的参数示例**：[Exec and Eval.json](/source/?file=b473d006c6fd3bdc39.json) → `任务顶层`（只摘本节用到的键，值保持原样）。

~~~json
{
  "version": "0.5.0",
  "links": "https://www.jd.com",
  "saveName": "current_time",
  "saveThreshold": 10,
  "outputFormat": "xlsx",
  "maxViewLength": 15
}
~~~

一个任务由一个 BrowserThread 管理：浏览器会话、graph、输出字段字典、缓存 OUTPUT、日志缓冲、暂停 event 与停止 shutdown_event 都属于这次执行。主入口为每个任务复制 Options 并启动线程；I/O 等待期间适合线程，但 Python 计算仍受运行时约束，多个浏览器也会消耗内存。

初始化先生成 Data/Task_<id>/ 与保存目录、读取可选的 steps、注入脚本和重定向下载，然后设置 `self.procedure=service['graph']`、拆顶层 links、按输出摘要建立空字段字典、类型与 record 标志，接着 preprocess，再 readFromExcel。

`preprocess()` 兼容 params/paras，补 iframe、clear/newLine、skipCount、exitElement，统一 XPath 标签大小写，处理旧版循环点击路径，计算逐字段 optimizable 与整体 quickExtractable。它没有替你验证所有业务 XPath 当前都有效，也不是把 graph 编译成一个扁平动作列表。

这里版本号仍用源码的字符串比较逻辑，不应夸成完整语义版本解析。无 version 的老任务会被拒绝；带 version 的旧 JSON 也要按兼容代码读取。运行期追加的 quickParams 等无需说成用户 JSON 中原本有的参数。

### 22. 输入摘要、Excel 覆盖与 Field 替换

**从文件读取的参数示例**：[Exec and Eval.json](/source/?file=b473d006c6fd3bdc39.json) → `任务顶层`（只摘本节用到的键，值保持原样）。

~~~json
{
  "inputParameters": [
    {
      "id": 0,
      "name": "urlList_0",
      "nodeId": 1,
      "nodeName": "点击元素",
      "value": "https://www.jd.com",
      "desc": "要采集的网址列表，多行以\\n分开",
      "type": "text",
      "exampleValue": "https://www.jd.com"
    },
    {
      "id": 1,
      "name": "loopText_1",
      "nodeId": 2,
      "nodeName": "循环",
      "desc": "要输入的文本/网址,多行以\\n分开",
      "type": "text",
      "exampleValue": "1\n1\n1\n1\n1\n1\n1\n",
      "value": "1\n1\n1\n1\n1\n1\n1\n"
    }
  ]
}
~~~

**从文件读取的参数示例**：[169.json](/source/?file=a3b038f41a703d1e28.json) → `graph[6].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "value": "Field[\"自定义操作\"]Field[\"参数2_文本\"]",
  "useLoop": false,
  "xpath": "//*[@id=\"key\"]"
}
~~~

输入摘要用 name 对外暴露参数，nodeId 指回 graph 数组位置。`readFromExcel()` 在 inputExcel 非空时读第一张工作表，首行作为参数名，列值转字符串；重复名称组合时用 `~` 拼分段值。`urlList_0` 可以覆盖 self.links，其他名字匹配 inputParameters 后按节点类型更新 links/value/exitCount/textList。

这是执行器读取已有工作簿的机制分析，不需要本次生成或修改 Excel。设置 inputExcel 失败时记录错误并使用默认参数，代码也不是按输出字段名来反查输入节点。

169 任务输入值为 `Field["自定义操作"]Field["参数2_文本"]`，它使用已采集/自定义操作结果替换模板。例如两项当前值分别为 A、B，则输入字符串变成 AB。**源码语法是 `Field["字段名"]`，不是旧第 29 篇的 `{字段名}`。**

当前 utils.replace_field_values 还处理模板内的 eval("...") 与 JS("...")；先在这些表达式内部按对应语言转义字段字符串，再展开剩余普通 Field 引用。输入模板自己提供的代码与网页采到的数据需要分清；不要把旧的未转义插值示例直接复制过来。

### 23. 从字段字典到一行，再到磁盘：组装、阈值与输出目录

**从文件读取的参数示例**：[Exec and Eval.json](/source/?file=b473d006c6fd3bdc39.json) → `任务顶层`（只摘本节用到的键，值保持原样）。

~~~json
{
  "id": 220,
  "saveName": "current_time",
  "outputFormat": "xlsx",
  "saveThreshold": 10,
  "maxViewLength": 15,
  "outputParameters": [
    {
      "id": 0,
      "name": "检测字段",
      "desc": "",
      "type": "text",
      "recordASField": 0,
      "exampleValue": "/手机/数码"
    },
    {
      "id": 1,
      "name": "自定义操作",
      "desc": "自定义操作返回的数据",
      "type": "text",
      "recordASField": 0,
      "exampleValue": ""
    },
    {
      "id": 2,
      "name": "自定义操作",
      "desc": "自定义操作返回的数据",
      "type": "text",
      "recordASField": 0,
      "exampleValue": ""
    },
    {
      "id": 3,
      "name": "自定义操作",
      "desc": "自定义操作返回的数据",
      "type": "text",
      "recordASField": 0,
      "exampleValue": ""
    }
  ]
}
~~~

这份真实任务输出字段 recordASField 都为 0，因此它可以把检测结果用于条件判断，却不把这些列写入结果文件；不能仅看采集成功就预期出现四列 Excel。

~~~python
# utils.py 的真实 new_line 主体
line = []
i = 0
for value in outputParameters.values():
    line.append(value)
    if record[i]:
        print(value[:maxViewLength], ' ', end='')
    i += 1
return line
~~~

`maxViewLength=15` 只截短终端预览；内存 line 保留完整值，包括空值。`write_to_csv()` 在写盘阶段依据 record[i] 过滤列。旧第 29 篇“只保存有值且截断字段内容”的伪代码不符合当前实现。

采集节点的 newLine 控制是否追加行，clear 控制采前是否清字段；写盘由 `saveData()` 控制：`exit=True` 或 `len(OUTPUT)>=save_threshold` 才真正写日志、steps 与数据，再清缓存。新建 CSV/XLSX 的缓存可能先含表头，所以阈值不必恰好等于业务记录数。

| outputFormat | 保存函数/对象 |
| --- | --- |
| csv / txt | write_to_csv，UTF-8 BOM，按 record 过滤 |
| xlsx | write_to_excel，按类型转换与记录标志写入 |
| json | write_to_json，使用字段名组织对象，读取已有内容再追加写回 |
| mysql | myMySQL 创建表与 write_to_mysql，连接配置另读 |

初始化 dataWriteMode 控制追加、覆盖或名称冲突重命名；removeDuplicate=1 时在正常任务结束做去重，依赖 pandas，不能把去重当成实时防重复执行。

正常无重名的默认目录布局是：

~~~text
Data/Task_220/
├─ <saveName>.xlsx
├─ <saveName>.log
├─ <saveName>_steps.txt
└─ <saveName>/
   ├─ files/
   ├─ images/
   └─ screenshots/
~~~

`current_time` 在初始化时替换为当前时间字符串。结果数据/log/steps 在 Task_220 下，下载与图片在同名子目录下；不能沿用旧第 30 篇把所有结果都画进时间戳子目录的布局。

### 24. 断点续采、暂停、停止与收尾

**从文件读取的参数示例**：[221.json](/source/?file=756f39f73221bdbb10.json) → `任务顶层`（只摘本节用到的键，值保持原样）。

~~~json
{
  "saveName": "current_time",
  "startFromExit": 0,
  "pauseKey": "p",
  "quitWaitTime": 60,
  "recordLog": 1
}
~~~

本例 startFromExit=0 从头采，pauseKey=p，正常结束等待 60 秒再关闭浏览器。将 startFromExit 改为 1 是教学变体；还必须指向同一 saveName 的 steps 文件，若每次使用 current_time 生成新名称，不能仅靠这个开关找到上次位置。

续采读取 startSteps，执行树仍从 root 重放。普通采集节点在 totalSteps 达到 startSteps 前跳过采集，但打开、输入、点击等仍可能执行，然后 totalSteps 增长。`saveData()` 写 `totalSteps+1`；快速循环路径不会经过每个普通采集节点的计数代码，因此不能声称全路径都精确逐记录恢复。

Event 的最小背景：event.set() 放行，event.clear() 让下次 wait() 阻塞；shutdown_event.set() 表示停止请求。executeNode 和多个执行函数在入口检查停止，再在协作点等待暂停事件。长按暂停键由 utils 的按键回调切换事件状态，不是在任意 Python 指令中间抢占线程。

IPC 关停服务绑定 127.0.0.1 的动态端口，检查调用的 key 后设置共享 shutdown_event；这是给 Electron 本机控制的通道。详情见第 26 篇 stopTask，不需要向外网发布控制服务。

`run()` 为顶层 links 中每个网址设置 urlId，调用 executeNode(0)。正常结束调用 saveData(exit=True) 与去重；停止分支跳过这段正常收尾，**不能保证停止时所有未达到阈值的缓存都会写盘**。接着关闭数据库，正常路径按 quitWaitTime 等待（分成可响应停止的小段），quit 浏览器，尝试清理临时 profile，并通知下载监视线程结束。

等待异常会记录后继续，节点分发外也有异常兜底；这种策略让后面的节点有机会执行，但一次点击失败后仍可能采到错误页面。应根据详情特征、字段 default 和日志判断成功，不能把“任务执行完成”当作所有字段正确的证明。

### 25. 小练习：用一个最小解释器验证“参数 → 动作 → 控制流”

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](/source/?file=dacf0dd7482f35613c.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](/source/?file=dacf0dd7482f35613c.json) → `graph[2]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 8,
  "sequence": [
    3,
    4
  ]
}
~~~

把这份实际结构的 root=[1,2]、循环=[3,4] 代入一个不启动浏览器的练习，可以分别观察分发与循环体：

~~~python
import json
from pathlib import Path

task = json.loads(Path('Examples/循环点进详情页无新标签页打开.json')
                  .read_text(encoding='utf-8-sig'))
graph = task['graph']

def execute(i):
    node = graph[i]
    option = node['option']
    if option == 0:
        for child in node['sequence']:
            execute(child)
    elif option == 8:
        # 模拟两个链接；真实程序按 XPath 查 DOM
        for link in ('A', 'B'):
            print('当前链接', link)
            for child in node['sequence']:
                execute(child)
            print('恢复列表')
    else:
        print(i, option, node['title'])

execute(0)
~~~

从仓库根目录运行，预期先输出打开网页，再依次得到 A 的点击、采集、恢复，以及 B 的点击、采集、恢复。这里用打印代替 Selenium，没有真的实现 history、字段提取或任务续采。这个迷你执行器用来验证任务结构的解释过程；正式生命周期和线程机制已经在前几节对照真实任务解释。

还可用两个 Event 验证暂停：工作线程每个动作前 wait，主线程 clear 暂停、set 继续；写 CSV 时每完成几条 flush 一批。练习重点是验证协作点与缓存，而不是把正式执行器所有 API 重新抄一遍。

## 第九部分：真实汽车新闻任务端到端串讲

### 26. 从采列表超链接，到详情内容与图片

**从文件读取的参数示例**：[第一步：采集列表超链接地址.json](/source/?file=170e1de37e82f7f838.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

**从文件读取的参数示例**：[第一步：采集列表超链接地址.json](/source/?file=170e1de37e82f7f838.json) → `graph[2]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 8,
  "sequence": [
    6,
    3
  ]
}
~~~

**从文件读取的参数示例**：[第一步：采集列表超链接地址.json](/source/?file=170e1de37e82f7f838.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 0,
  "exitCount": 5
}
~~~

**从文件读取的参数示例**：[第二步：采集详情页标题内容并下载所有图片.json](/source/?file=fceb4183eeff090c9a.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2,
    3
  ]
}
~~~

第一步任务的真实可达结构如下，注意 graph[4]/[5] 虽然留在数组里，却不在 root 的执行路径上：

~~~text
root 0 [1,2]
├─ 1 打开资讯列表
└─ 2 单元素翻页循环 [6,3]，exitCount=5
   ├─ 6 链接列表循环 [7]
   │  └─ 7 采链接文本、链接地址
   └─ 3 点击下一页
~~~

设计时选链接并匹配同类，参数生成 relative=true 的文字/href 字段；第 14 篇 collectMultiWithPattern 包装消息，经 Electron 到流程图，建立循环与采集孩子。设置翻页把“采本页”和“下一页”放进同一个单元素循环。这些结构的插入、保存、实例生成分别继续在第 18、23、26 篇讲。

执行时 root 打开列表，外层每轮先处理全页链接，再点下一页；内层只有一个采集孩子，有条件走 lxml 快速行提取。exitCount=5 是五轮循环体，最后一次点击仍执行；不能沿用旧综合案例里不存在的 graph[6]，也不能把打开网页叶子画成执行循环的父节点。

第二步任务真实结构是：

~~~text
root 0 [1,2,3]
├─ 1 打开文章
├─ 2 一次采页面标题与正文
└─ 3 图片列表循环 [4]，xpath=id("article")//img
   └─ 4 采当前图片 src，downloadPic=1
~~~

这两个文件是两份任务；第二步原文件的 links 只有一个示例文章 URL，源码没有自动把第一步结果文件接成第二步输入。需要把第一步链接列通过输入参数/Excel 覆盖等已有任务入口供给第二步，或明确修改第二步的顶层 links。不要把“链式业务”讲成已经自动串好的跨任务管道。

第二步每个顶层链接都会重跑 root：打开该文章，采标题/正文，遍历图片。图片 downloadPic=1 不满足普通图片快速提取条件，需处理元素取值与下载；下载能否成功仍由页面资源与执行环境决定。采集记录与图片文件分别按第 23 节的布局输出。

把两份任务的结构与真实字段对照到浏览器，能完整覆盖“扩展生成参数 → 消息入图 → 保存任务 → 读取执行实例 → executeNode 分发 → 循环/提取 → 增量保存”。这条链路的重点是每个阶段的数据形态，不能只用伪造的电商 JSON 代替真实任务。

### 27. 课堂验证：先核对参数，再预测观察结果

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](/source/?file=dacf0dd7482f35613c.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 1,
  "historyWait": 2
}
~~~

**从文件读取的参数示例**：[221.json](/source/?file=756f39f73221bdbb10.json) → `graph[3].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "newTab": 1,
  "clickWay": 0
}
~~~

1. 同页详情任务：指出哪个节点等 8 秒、哪处等 2 秒，推演 history 长度从 3 到 4 的恢复；再解释为什么下一轮可能出现 StaleElement。
2. 新标签页任务：分别观察点击前后句柄数量、当前句柄、history.handle；预测详情完成后哪些窗口会被关闭，并指出最后句柄策略的假设。
3. 将同页示例改为模态详情且不新增历史：说明为什么 handleHistory 可能不恢复，循环体要在哪里加关闭动作。
4. 翻页任务：根据 [6,3] 预测“采五页”与“点击五次”的差异；检查不可达节点是否会执行。
5. 快速提取：给链接字段加入前置 JS，预测哪个优化条件失效；给图片字段开启下载，说明为什么不能只取 HTML 快照。
6. 输出与续采：把 maxViewLength 从 15 改为 3，核对终端预览与完整写盘值；为续采固定 saveName，区分重放动作和跳过采集。

这些是按真实参数做出的课堂检查，不是本次已经访问网站执行成功的报告。旧站点与原 XPath 可能变化，教学基础操作可在第 17 篇本地练习页复现，真实任务则用于源码与 JSON 对照。

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[15.Flowchart 基本原理：消息到了，顺序、循环和判断怎样存](/easyspider/chapter-15) ｜ 下一篇：[17.Selenium：从 Python 基本操作到 EasySpider 浏览器执行](/easyspider/chapter-17)
