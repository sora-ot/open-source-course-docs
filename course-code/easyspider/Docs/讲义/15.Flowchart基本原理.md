# 15.Flowchart 基本原理：消息到了，顺序、循环和判断怎样存

> 第 14 篇把操作消息发了出来。接收端要保存这些操作，供以后执行。
>
> 第 14 篇已经说明扩展怎样发出输入、点击、采集等操作消息；现在先研究怎样把这些操作组织成可保存、可执行的流程。
>
> 本篇先说明为什么循环体需要层次关系，再从一个 root 开始，逐步加入顺序动作、循环和内层循环，最后用房源原图推到完整执行树。
>
> 第 16 篇沿着同一份结构执行，解释 while 的循环体为什么会调用执行函数，以及递归怎样自然出现。

---

## 第一部分：为什么需要层次关系

### 1. 只有顺序操作，一串列表就够了

假设只做一次搜索：

~~~text
打开网页 → 输入“海淀” → 点击搜索
~~~

收到三条消息，就存三个操作：

~~~js
const actions = [
  { option: 1, parameters: { links: "https://example.com/rent" } },
  { option: 4, parameters: { xpath: "//input[@id='area']", value: "海淀" } },
  { option: 2, parameters: { xpath: "//button[@id='search']" } }
];
for (const action of actions) {
  execute(action);
}
~~~

数组顺序就是执行顺序。这是从零设计的简化模型，域名和 XPath 都是假设；还没有使用 EasySpider 的实际存储格式。

### 2. 加入循环后，还必须记录哪些动作一起重复

现在要依次搜索“海淀、朝阳”：打开网页只做一次，每个地区都要先输入、再点击搜索。

~~~text
打开网页
第 1 轮：输入海淀 → 点击搜索
第 2 轮：输入朝阳 → 点击搜索
~~~

如果只保存一串同级操作：

~~~text
打开网页 → 地区循环 → 输入地区 → 点击搜索
~~~

列表只说明四项的先后，没有记录“输入地区、点击搜索”属于地区循环的循环体。把循环体留空、输入与搜索放在外面，含义就是先结束循环，再输入和搜索各一次。

程序里用大括号标出循环体，流程数据也需要保存这段范围。可以把循环看成一个容器，把每轮要重复的操作放进它的孩子列表：

~~~text
root（整张任务的最外层容器）
├─ 打开网页
└─ 地区循环
   ├─ 输入地区
   └─ 点击搜索
~~~

**同级顺序回答“先做谁、后做谁”，父子关系回答“哪些操作属于这一轮”。** 判断同样需要层次：哪些动作属于满足条件的分支，也必须保存下来。

因此，任务在逻辑上需要有序的父子结构。节点对象仍可以集中存放在一个数组里，再由每个容器记录自己的直接孩子。下面先用小图演示 EasySpider 怎样构建这套结构，再回到完整房源案例。

---

## 第二部分：空白画布里，已经有一个 root

### 3. nodeList 最初只有一个对象

打开 [FlowChart.js](../../ElectronJS/src/taskGrid/FlowChart.js)，文件开头先定义节点数组，再构造 root，最后把它放进去。下面摘出结构字段；真实 root 还带有默认 parameters、isInLoop 等字段。

~~~js
let nodeList = Array();
let root = {
  index: 0,
  id: 0,
  parentId: 0,
  type: -1,
  option: 0,
  title: "root",
  sequence: []
};
nodeList.push(root);
~~~

所以“还没有加任何操作”时，内存不是空数组：

~~~text
nodeList.length = 1
nodeList[0] = root
nodeList[0].sequence = []
~~~

root 是整张图的入口，也是最外层容器。它的孩子列表为空，表示暂时没有操作。画布上的开始标记由渲染函数另行生成，root 不作为普通操作方块再画一次。

### 4. 一个节点要存哪几类信息

先只认识这些字段，不急着记界面编号；id、parentId 与 index 的对照留到第 18 篇：

| 字段 | 回答什么问题 | 例子 |
| --- | --- | --- |
| index | 对象放在 nodeList 的哪个数组位置 | index=2 对应 nodeList[2] |
| title | 界面显示什么名字 | 点击按钮 |
| option | 这是哪一种操作 | 2=点击，8=循环 |
| type | 用什么外观模板画 | 0=普通方块，1=循环框 |
| parameters | 这个操作的具体配置是什么 | XPath、输入文字、循环列表 |
| sequence | 这个容器有哪些直接孩子，依次是谁 | [1,2] 表示先孩子 1，再孩子 2 |
| id、parentId、position | 当前界面怎样定位它 | refresh 重算，第 18 篇详解 |

`type` 与 `option` 的职责不同。例如循环节点通常同时有 `type=1`、`option=8`：一个用于选绘图模板，一个用于识别操作。

| 节点类别 | type | option |
| --- | --- | --- |
| root | -1 | 0 |
| 普通操作 | 0 | 1～7，分别对应打开、点击、提取、输入等 |
| 循环 | 1 | 8 |
| 判断 | 2 | 9 |
| 条件分支 | 3 | 10 |

接下来所有快照都只展示结构字段，省略默认参数和界面辅助字段，**不是可以直接导入的完整任务 JSON**。数字若没有另外标注，均表示 nodeList 数组下标。

---

## 第三部分：先加三个顺序节点，数据怎样变化

### 5. 加第一个“打开网页”

创建时取 `index=nodeList.length`。此时长度为 1，新对象就存到数组第 1 项。然后把数字 1 接到 root 的孩子列表中。

~~~text
① 追加对象：nodeList[1] = 打开网页
② 接入结构：nodeList[0].sequence = [1]
~~~

结构快照：

~~~json
[
  {"index":0, "title":"root",     "option":0, "sequence":[1]},
  {"index":1, "title":"打开网页", "option":1, "sequence":[]}
]
~~~

图的关系是：

~~~text
root
└─ 1 打开网页
~~~

这两步缺一不可：只追加对象，却不把它接到 root 可达的 sequence 中，下次刷新就不会画出它。

### 6. 再加“点击按钮”和“提取结果”

继续在 root 末尾依次添加两个普通动作：

| 操作完成后 | nodeList 末尾新增什么 | root.sequence |
| --- | --- | --- |
| 加打开网页 | 下标 1：打开网页 | [1] |
| 加点击按钮 | 下标 2：点击按钮 | [1,2] |
| 加提取结果 | 下标 3：提取结果 | [1,2,3] |

现在完整的结构骨架是：

~~~json
[
  {"index":0, "title":"root",     "option":0, "sequence":[1,2,3]},
  {"index":1, "title":"打开网页", "option":1, "sequence":[]},
  {"index":2, "title":"点击按钮", "option":2, "sequence":[]},
  {"index":3, "title":"提取结果", "option":3, "sequence":[]}
]
~~~

画面中三个动作从上到下排列。执行时 root 也按自己的 sequence 依次调用它们。

**此时数组存储顺序恰好等于动作顺序，只是因为我们一直在末尾添加。** 下一步故意在图的中间插入一个后来才创建的节点，就能看出两者的区别。

### 7. sequence=[] 为什么不表示任务结束

点击按钮 2 的 sequence 为空，表示它没有孩子。点击完成后，会返回调用它的 root；root 再取自己 sequence 中的下一项 3，执行提取。

~~~text
root.sequence = [1,2,3]
                       ↑ root 负责继续取下一项

nodeList[2].sequence = []  只表示点击动作没有孩子
~~~

所以 sequence 更准确的含义是**有顺序的直接孩子下标列表**。它没有在每个叶子里另存一条“下一站”连接；递归调用与返回见第 16 讲。

---

## 第四部分：中间加一个循环，需要换数据格式吗

### 8. 新循环仍然追加到 nodeList 末尾

现在希望图上先打开网页，再进入一个循环，最后提取结果。**先在打开网页与点击按钮之间插入空循环，暂时还不把点击移进去。**

新增前 `nodeList.length=4`，所以循环获得 `index=4`。**它在图上的位置居中，存储位置仍然是数组末尾。**

也就是说：**任何时候新增节点，都是追加到 nodeList 末尾；不管它在图上是居中、居左还是居右。 真正决定他的实际执行顺序的，是它在父节点 sequence 中的下标位置。**

如把数字 4 插入 root.sequence 的第二个位置，就能让它在打开网页后、点击按钮前执行。

~~~text
对象数组：
原来：[root, 打开网页, 点击按钮, 提取结果]
现在：[root, 打开网页, 点击按钮, 提取结果, 循环]

root 的孩子：
原来：[1,2,3]
现在：[1,4,2,3]

新循环的孩子：
4.sequence = []
~~~

父孩子列表的修改可以写成：

~~~js
nodeList[0].sequence.splice(1, 0, 4);
// 从孩子列表位置 1 开始，删除 0 项，插入下标 4
~~~

此时关系为：

~~~text
root
├─ 1 打开网页
├─ 4 循环（暂时为空）
├─ 2 点击按钮
└─ 3 提取结果
~~~

`nodeList[2]` 和 `nodeList[3]` 都没有搬家。新循环在 root.sequence 的第二个位置，所以画在打开网页后面。

**增加循环并不要求把扁平数组改成嵌套对象，也不要求重新排列 nodeList。** 循环本身还是一个节点对象，只是它可以在自己的 sequence 里容纳一组动作。

### 9. 把已有点击放进循环，改的是两份 sequence

空循环不会自动把后面的动作包进去。**要让点击属于循环体，需要把下标 2 从 root 的孩子列表摘掉，再插入循环的孩子列表。**

~~~text
修改前：
0.sequence = [1,4,2,3]
4.sequence = []

修改后：
0.sequence = [1,4,3]
4.sequence = [2]
~~~

用已知稳定下标演示结构修改：

~~~js
nodeList[0].sequence.splice(2, 1); // 从 root 摘掉孩子 2
nodeList[4].sequence.push(2);      // 接到循环内部
~~~

这里是解释数据变化的教学写法；真实界面会通过锚点、界面编号映射和移动工具定位两边，详见第 20 讲。

现在的完整结构骨架：

~~~json
[
  {"index":0, "title":"root",     "option":0, "sequence":[1,4,3]},
  {"index":1, "title":"打开网页", "option":1, "sequence":[]},
  {"index":2, "title":"点击按钮", "option":2, "sequence":[]},
  {"index":3, "title":"提取结果", "option":3, "sequence":[]},
  {"index":4, "title":"循环",     "option":8, "sequence":[2]}
]
~~~

对应关系：

~~~text
root
├─ 1 打开网页
├─ 4 循环
│  └─ 2 点击按钮
└─ 3 提取结果
~~~

如果循环参数要求重复两轮，含义就是：打开网页 → 循环里点击两轮 → 循环结束 → 提取一次。循环次数放在 parameters 中，不能只凭 sequence 判断重复几次。

第 19、20 讲的小例子从这份五节点结构开始，第 18 讲统一使用后面的七节点双层循环例子。接下来的添加动作与嵌套循环练习各自独立推演，不继续累加到这份基准图。

### 10. 循环里再加动作，仍然用相同格式

独立练习：希望每轮先输入、再点击。新建输入节点 5 时，仍然追加到 nodeList 末尾；只把数字 5 插入循环的孩子列表开头。

~~~text
新增对象：nodeList[5] = 输入文字

0.sequence 仍是 [1,4,3]
4.sequence 从 [2] 变成 [5,2]
~~~

这时数组下标 5 的输入动作，比下标 2 的点击先执行。**存储得晚，不妨碍它在某个容器中排在前面。**

如果还需要嵌套循环，也继续用同一套格式。例如从五节点基准图独立推演：

~~~text
追加 5（内层循环），追加 6（内层动作）
0.sequence = [1,4,3]
4.sequence = [2,5]
5.sequence = [6]
~~~

内层循环只是外层循环的一个孩子；它再拥有自己的孩子。判断也沿用这种表示，只是判断的直接孩子是条件分支，各分支再保存内部动作。第 20 讲会展开判断的创建过程。

最后把这个两层循环的例子完整展开。这里仍从五节点基准图出发，节点 5 是新建的内层循环，节点 6 的内层动作取名为“点击内层按钮”。此时 `nodeList.length=7`，完整结构骨架为：

~~~json
[
  {"index":0, "title":"root",         "option":0, "sequence":[1,4,3]},
  {"index":1, "title":"打开网页",     "option":1, "sequence":[]},
  {"index":2, "title":"点击按钮",     "option":2, "sequence":[]},
  {"index":3, "title":"提取结果",     "option":3, "sequence":[]},
  {"index":4, "title":"外层循环",     "option":8, "sequence":[2,5]},
  {"index":5, "title":"内层循环",     "option":8, "sequence":[6]},
  {"index":6, "title":"点击内层按钮", "option":2, "sequence":[]}
]
~~~

逐个看各节点的 sequence：

| 下标 | 节点 | sequence（直接孩子） |
| --- | --- | --- |
| 0 | root | [1,4,3] |
| 1 | 打开网页 | [] |
| 2 | 点击按钮 | [] |
| 3 | 提取结果 | [] |
| 4 | 外层循环 | [2,5] |
| 5 | 内层循环 | [6] |
| 6 | 点击内层按钮 | [] |

对应关系：

~~~text
root
├─ 1 打开网页
├─ 4 外层循环
│  ├─ 2 点击按钮
│  └─ 5 内层循环
│     └─ 6 点击内层按钮
└─ 3 提取结果
~~~

外层循环的 sequence 只写直接孩子 `[2,5]`，不会把内层动作 6 也写进去；动作 6 由内层循环的 `[6]` 管理。执行时，root 先打开网页，再进入外层循环；外层每轮先执行点击按钮 2，再执行整个内层循环 5。等外层循环全部结束，root 才执行提取结果 3。两层各重复几轮，仍分别由各自的 parameters 决定。

---

## 第五部分：nodeList 有顺序，但这个顺序负责什么

### 11. 对象存储位置与流程中的顺序要分开

回看五节点基准图：

| 观察角度 | 得到什么 |
| --- | --- |
| 按 nodeList 数组位置看 | 0 root、1 打开、2 点击、3 提取、4 循环 |
| 看 root.sequence | 1 打开、4 循环、3 提取 |
| 看循环 4 的 sequence | 2 点击 |
| 看执行含义 | 打开 → 执行循环及其内部点击 → 提取 |

因此可以把 nodeList 理解为**按稳定数组位置存放节点对象的表**。JavaScript 数组当然有下标顺序，但这里不拿这个顺序表示流程的先后或嵌套。

正常新增时，节点取当前长度作为 index，再 push 到末尾；创建、复制和加载的具体路径不同，不能理解成每次点击或每条消息都必然新增一个对象。

父节点的 sequence 同时表达：

1. **归属**：哪些是这个容器的直接孩子。
2. **局部顺序**：这些孩子按什么次序处理。

整张图的执行行为还要结合 option、parameters 和递归规则。循环重复孩子，判断选择分支，不能把所有 sequence 拼接成一张固定的运行轨迹。

---

## 第六部分：回到房源原图，从循环体推到完整的树

前面的小图已经说明怎样追加对象、修改孩子列表。下面换成一份独立的房源任务，先根据业务确定循环体，再构建它的层次；节点下标将重新从 0 开始，与五节点小图和七节点嵌套练习分别使用。

### 12. 看原图：这里有一个 do 外循环

![房源采集：服务流程、层次封装与执行树](图片/Flowchart/房源采集-流程与执行树-原版.png)

配图直接来自原始幻灯片，保留原来的文字、框线、箭头和蓝色 1–16 编号。蓝色数字表示执行阶段，正文后面另列节点数组下标。

先只看左栏最外侧的回边：

~~~text
输入地段名
    ↓
搜索、处理这个地段的房源
    ↓
地段名全部输入完毕？
    否：回到“输入搜索项”
    是：结束
~~~

先处理一个地段，再检查是否还有地段，这就是业务上的 do/while 思路。可以用下面的伪代码表达。假设地区列表非空，先取“海淀”：

~~~text
打开网页

do {                                      // 地区外循环
    输入当前地区
    点击搜索
    处理这个地区的页面与房源
    移到下一个地区
} while (还有地区没有处理)
~~~

这里要先确定**循环体的边界**：输入、搜索、处理页面，都在外层 do 的大括号里；打开网页在大括号外，只做一次。

因此存储时也要保留这个归属：

~~~text
root
├─ 打开网页
└─ 地区循环
   ├─ 输入当前地区
   ├─ 点击搜索
   └─ 处理页面
~~~

**循环内部的操作必须放在循环节点里面，作为它的子节点。** 父子关系来自程序块的包含关系。只把“循环、输入、搜索”摆成三个同级节点，就丢掉了循环体的范围。

这里用 do/while 解释业务结构。Python 没有 do 关键字；实际执行器的单元素循环用 while True 配合 break，源码也注释为 do while。地区文本列表则实际用 for 遍历，不能把所有循环类型都当成同一段 while 代码。第 16 篇会逐项对照。

### 13. 为什么同级列表表达不出“输入和搜索都要重复”

先把页面采集省略，只搜索“海淀、朝阳”。正确语义是：

~~~text
地区循环的第 1 轮：输入海淀 → 点击搜索
地区循环的第 2 轮：输入朝阳 → 点击搜索
~~~

这时一个循环节点要保存两类信息：

~~~text
循环参数：遍历哪些地区，例如“海淀\n朝阳”
循环体：本轮依次执行哪些操作，例如“输入、搜索”
~~~

假设暂时给节点编号：0 为 root，1 为打开网页，2 为地区循环，3 为输入，4 为搜索。正确的孩子列表是：

~~~js
root.sequence = [1, 2];
areaLoop.sequence = [3, 4];
~~~

root 执行到 2 后，由地区循环在每一轮执行 3、4。因此收到输入、搜索消息时，除了构造操作对象，还必须知道插入的是哪个容器的循环体。锚点和手动插入的实现见第 20 篇，消息接入见第 21 篇，本篇先确定它们应当存在哪里。

如果错存成：

~~~js
root.sequence = [1, 2, 3, 4];
areaLoop.sequence = [];
~~~

含义会变成：

~~~text
打开网页
执行一个没有孩子的地区循环
地区循环全部结束
输入一次
搜索一次
~~~

输入和搜索不再跟随每个地区重复。这里操作对象完全相同，业务行为却变了，原因就在包含关系。

再看一种容易漏掉的错误：

~~~js
root.sequence = [1, 2, 4];
areaLoop.sequence = [3];
~~~

两轮会先输入海淀，再输入朝阳；离开循环后才点击一次搜索。把搜索放到循环外，已经改变了程序含义。

### 14. 地区循环里面，还有一个页面循环

回到原图左栏：“达到最大翻页次数？”回答“否”，会继续获取新房源链接；回答“是”，才去检查地区是否处理完。也就是说，一个地区要处理多轮页面。

把“处理这个地区的页面与房源”展开：

~~~text
打开网页

do {                                      // 地区循环
    输入当前地区
    点击搜索

    do {                                  // 页面循环
        处理当前页的所有房源
        点击下一页
    } while (还没有达到规定轮次)

    移到下一个地区
} while (还有地区没有处理)
~~~

先按大括号划分归属，暂时不要关心图形怎样画：

| 程序块 | 本块的一轮包含什么 | 存成哪些直接子节点 |
| --- | --- | --- |
| root | 打开网页，执行整个地区循环 | 打开网页、地区循环 |
| 地区循环体 | 输入、搜索、处理整个页面循环 | 输入、搜索、页面循环 |
| 页面循环体 | 处理当前页所有房源，再翻页 | 房源循环、点击下一页 |

内层的整个页面循环，是外层地区循环的一个孩子。它里面的房源操作不必同时列为地区循环的直接孩子。

“移到下一个地区”“检查已完成几轮”由循环的执行机制负责，不必各存一个操作节点。孩子列表记录本轮要做的业务操作，循环参数记录遍历输入与退出规则。

~~~text
地区循环
├─ 输入当前地区
├─ 点击搜索
└─ 页面循环
   ├─ 房源循环
   └─ 点击下一页
~~~

例如轮到“海淀”时，要等海淀的整个页面循环完成，才能进入“朝阳”。父节点里的先后顺序，针对的是整段子任务。

### 15. 房源循环里面，再放判断和分支

原图左栏“房源链接已全部处理？”的回边，表示在一页中逐条处理链接。仍然从循环体的范围推结构：

~~~text
do {                                      // 页面循环
    对当前页的每一个房源链接 {              // 房源循环
        if (当前链接文字包含“单间”) {
            点击这个房源链接
            提取房源信息
        } else {
            空操作
        }
    }
    点击下一页
} while (还没有达到规定轮次)
~~~

“只采单间”决定一条房源应该执行哪组操作。所以判断是房源循环的孩子，两个候选分支是判断的孩子，点击与提取是单间分支的孩子：

~~~text
房源循环
└─ 判断
   ├─ 单间分支
   │  ├─ 点击当前房源
   │  └─ 提取房源信息
   └─ 非单间分支（空）
~~~

原图右栏非单间一侧的虚线“空操作”表达什么也不做。存成一个没有操作孩子的分支即可，不需要真的创建两个空操作节点。

原图中三个“是否处理完”的检查，属于相应循环的结束机制；“是否单间”属于业务选择。EasySpider 中前者由循环类型、遍历结束和退出参数处理，后者才用判断与分支节点表示。

### 16. 对照原图中栏：外框就是循环体的范围

现在回看中栏，会发现层次框不是为了排版好看：

~~~text
root
├─ 打开网页
└─ 地区循环                              // 最外层蓝框
   ├─ 输入当前地区
   ├─ 点击搜索按钮
   └─ 页面循环                           // 中层蓝框
      ├─ 房源循环                        // 内层蓝框
      │  └─ 判断
      │     ├─ 单间分支                  // 左侧绿框
      │     │  ├─ 点击当前房源
      │     │  └─ 提取信息
      │     └─ 非单间分支（空）          // 右侧绿框
      └─ 点击下一页
~~~

每个框对应一个有边界的程序块。右栏的实线把这些“包含关系”连成树；蓝色虚线展示实际执行中的进入、交接与返回。

因此保存结构时，只需要记录父节点有哪些有序的孩子。循环重复与函数返回会在执行时发生，不需要把蓝色回边一并写进孩子列表。

### 17. 用 A、B 两条房源检查“下一页”的位置

海淀第 1 页有：

~~~html
<a class="house" href="/house/101">A：海淀 单间 2500元</a>
<a class="house" href="/house/102">B：海淀 整租 6500元</a>
~~~

正确结构是：

~~~text
页面循环
├─ 房源循环：判断 A 并采集，判断 B 并跳过
└─ 点击下一页
~~~

等两条房源处理完，才翻页。如果把“点击下一页”放进房源循环，每条房源处理后都会翻页。处理完 A 就离开了当前页，B 的处理还没有完成，列表元素也可能失效。

再把“点击下一页”放到页面循环外，则页面循环的每一轮都缺少翻页操作：可能反复处理同一页，整个页面循环结束后才翻一次。

| 点击下一页属于谁 | 正常情况下的执行时机 |
| --- | --- |
| 房源循环 | 每处理一条房源就翻页 |
| 页面循环 | 每处理完一页房源就翻页 |
| 地区循环、位于页面循环后 | 整个页面循环结束才翻一次 |

**归属决定重复范围，孩子顺序决定同一轮中的先后。** 这是数据结构的来源，也是检查结构是否合理的方法。

### 18. 后续手算固定一份数据

后面使用相同的数据，避免每讲一个机制就更换业务：

| 地区 | 页面轮次 | 本页房源 |
| --- | --- | --- |
| 海淀 | 第 1 轮 | A：单间 2500 元；B：整租 6500 元 |
| 海淀 | 第 2 轮 | C：单间 2800 元 |
| 朝阳 | 第 1 轮 | D：整租 7000 元 |
| 朝阳 | 第 2 轮 | E：单间 3000 元 |

每个地区执行两轮页面循环。正常路径中，暂定两轮都能找到并点击“下一页”按钮；因此每个地区点击两次，包括第二轮末尾的一次。这里“两轮处理”与“最终停在第二页”含义不同，源码退出条件见第 16 篇。

应该采集 A、C、E。这个结果将由树的层次、循环参数和判断条件共同得到。

---

## 第七部分：把房源树对照到实际节点数组

### 19. 设计、保存与执行使用的数组名称

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

前面已经从 [FlowChart.js](../../ElectronJS/src/taskGrid/FlowChart.js) 的 root 构造过程看到：节点集中放进 `nodeList`，容器的 `sequence` 只存孩子下标。这里的 `graph[0].sequence=[1,2]` 沿用同一表示。正式执行从数组第 0 项 root 开始，屏幕里的“开始/结束”提示不需要各存一个业务操作。

保存时叫 `service.graph`，设计时叫 `nodeList`，Python 中叫 `self.procedure`。这三个名字对应同一份节点数组在不同阶段的使用。

### 20. 房源例子的完整结构表

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[2]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 8,
  "sequence": [
    3,
    4,
    5
  ]
}
~~~

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[7]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 8,
  "sequence": [
    8,
    9
  ]
}
~~~

下面固定一套教学下标。新节点的创建顺序可以不同；后面所有推演统一采用本表。

| 数组下标 index | title | option | type | sequence | 父节点 index | 父节点 title |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | root | 0 | -1 | [1, 2] | 无（根节点） | 无 |
| 1 | 打开网页 | 1 | 0 | [] | 0 | root |
| 2 | 地区循环 | 8 | 1 | [3, 4, 5] | 0 | root |
| 3 | 输入地区 | 4 | 0 | [] | 2 | 地区循环 |
| 4 | 点击搜索 | 2 | 0 | [] | 2 | 地区循环 |
| 5 | 页面循环 | 8 | 1 | [6, 12] | 2 | 地区循环 |
| 6 | 房源循环 | 8 | 1 | [7] | 5 | 页面循环 |
| 7 | 判断 | 9 | 2 | [8, 9] | 6 | 房源循环 |
| 8 | 单间分支 | 10 | 3 | [10, 11] | 7 | 判断 |
| 9 | 兜底分支 | 10 | 3 | [] | 7 | 判断 |
| 10 | 点击房源 | 2 | 0 | [] | 8 | 单间分支 |
| 11 | 提取信息 | 3 | 0 | [] | 8 | 单间分支 |
| 12 | 点击下一页 | 2 | 0 | [] | 5 | 页面循环 |

**“父节点 index”表示当前节点直接属于哪个容器，数值是那个父节点在 `nodeList` 中的数组下标。** 例如输入地区 3 的父节点是 2，表示它属于地区循环；下一页点击 12 的父节点是 5，表示它属于页面循环，在每轮房源处理完后执行。

“直接属于”只看紧邻的一层：点击房源 10 的父节点是单间分支 8；判断 7、房源循环 6 都是它的祖先，但不是它的直接父节点。root 是整棵树的根，没有结构上的父节点。

“父节点 title”就是该父节点的名称，便于直接看出归属。这两列用于帮助读表，**不是新增的 JSON 字段**。可以从 `sequence` 反向找出：哪个节点的孩子列表包含当前下标，哪个就是它的父节点。例如 `nodeList[5].sequence=[6,12]`，所以 6、12 的父节点 index 都是 5，父节点 title 都是“页面循环”。

注意源码中的 `parentId` 存的是父节点的**界面 id**，刷新时会重新计算；本列存的是父节点的**数组 index**，两者可能不同。第 18 篇会具体对照它们。

读 `nodeList[5].sequence = [6, 12]`：

~~~text
页面循环的一轮里：
先执行数组第 6 项代表的整段房源循环；
等它返回，再执行数组第 12 项的点击下一页。
~~~

不是“第 5 项之后随便可以跳到 6 或 12”。

读 `nodeList[8].sequence = [10, 11]`：

~~~text
单间分支被选中以后：
先点击房源，再提取信息。
~~~

读 `nodeList[7].sequence = [8, 9]`：

~~~text
判断依次检查第 8 项、第 9 项的条件；
只选择第一个满足的分支。
~~~

**同一个 `sequence` 字段，具体怎样解释，由父节点的 `option` 决定。**

### 21. 由教学模型 JSON 读取的结构骨架

**从文件读取的参数示例**：[房源采集-教学模型.json](../../Docs/讲义/示例-Flowchart/房源采集-教学模型.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

~~~json
[
  {"index":0, "option":0, "title":"root", "sequence":[1,2]},
  {"index":1, "option":1, "title":"打开网页", "sequence":[]},
  {"index":2, "option":8, "title":"地区循环", "sequence":[3,4,5]},
  {"index":3, "option":4, "title":"输入地区", "sequence":[]},
  {"index":4, "option":2, "title":"点击搜索", "sequence":[]},
  {"index":5, "option":8, "title":"页面循环", "sequence":[6,12]},
  {"index":6, "option":8, "title":"房源循环", "sequence":[7]},
  {"index":7, "option":9, "title":"判断", "sequence":[8,9]},
  {"index":8, "option":10, "title":"单间分支", "sequence":[10,11]},
  {"index":9, "option":10, "title":"兜底分支", "sequence":[]},
  {"index":10, "option":2, "title":"点击房源", "sequence":[]},
  {"index":11, "option":3, "title":"提取信息", "sequence":[]},
  {"index":12, "option":2, "title":"点击下一页", "sequence":[]}
]
~~~

这是一份**结构骨架，不是可直接导入执行的任务文件**。`parameters`、界面辅助字段和任务元数据还没有补齐。

带关键参数的教学模型放在 [房源采集-教学模型.json](示例-Flowchart/房源采集-教学模型.json)。它用于对照结构和练习，不连接真实网站。

### 22. 用真实任务再核对 type 与 option

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[2]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "type": 1,
  "option": 8,
  "sequence": [
    7,
    3
  ]
}
~~~

前面构建节点时已经区分了结构字段与参数；这份真实任务中的 `type=1`、`option=8` 正好对应循环框与循环操作。`sequence` 保存直接孩子，`parameters` 保存循环的具体配置。

`type: 1` 只告诉渲染器“画循环框”，不会自动让浏览器重复操作；`option: 8` 才会让执行器调用 `loopExecute()`。

`option: 10` 是条件分支容器；root 的 `option` 是 0。不能把二者混成“root 都是 10”。

### 23. 为什么可以叫“执行抽象语法树”

**从文件读取的参数示例**：[JS判断条件示例.json](../../Examples/JS判断条件示例.json) → `graph[7]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 9,
  "sequence": [
    8
  ]
}
~~~

**从文件读取的参数示例**：[JS判断条件示例.json](../../Examples/JS判断条件示例.json) → `graph[8]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 10,
  "sequence": [
    5,
    6
  ]
}
~~~

把图看成一门很小的任务语言：

~~~text
顺序容器：先做 A，再做 B
循环节点：对每个输入，重复执行 body
判断节点：检查各分支，选一个执行
叶子节点：输入、点击、提取……
~~~

这和程序里“语句块、for、if、函数调用”的组织方式相似，所以可以从教学角度叫执行抽象语法树。

仓库字段仍然叫 `graph`，数组也不是通用编译器 AST 格式。这里强调的是：**保存结构与参数，再由解释器决定控制流。**

数组是平的；由 `sequence` 指向孩子后，逻辑结构是有序树。无需在 JSON 里把同一个孩子对象重复嵌进去。

### 24. 先检查你能不能读懂结构

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "option": 0,
  "sequence": [
    1,
    2
  ]
}
~~~

1. `root.sequence = [1,2]` 为什么不会只执行打开网页？
2. `5.sequence = [6,12]` 改成 `[12,6]`，本页采集发生在翻页前还是后？
3. 非单间分支 `sequence=[]` 为什么仍然是合法分支？
4. 如果单间分支先提取后点击，应该改哪个数组？
5. 是否需要把“提取完成后回到房源循环”的边也写入 JSON？

参考答案：root 顺序执行两个孩子；改顺序后先翻页；空分支被选中就立即返回；改 `8.sequence` 为 `[11,10]`；不需要，返回由调用关系完成。

下一篇就拿这份数组手工执行，解释“回到哪里”到底是谁记住的。

---

## 第八部分：第 14 篇的操作消息，分别怎样组成执行结构

以下是现有 JSON 中可核对的最终结构，不声称能仅凭任务 JSON 反推出用户当时点击了哪个按钮。消息到节点的具体插入代码留到第 21 篇；这里先理解保存后的结构与执行范围。

下面把节点的结构字段和 `parameters` 放在同一个对象中，便于同时看清“属于谁”和“具体做什么”。示例保留相关执行参数，省略界面定位字段、备用 XPath、预览值和未使用的脚本配置；较长的采集字段列表会单独标明节选范围。所有展示的字段值均来自所链接的原文件。

示例使用 JSONC，在每个 `option` 后用 `//` 注释说明节点类型；原任务文件仍是标准 JSON。

### 25. 单次动作和不规律多字段：先看叶子节点

**从文件读取的参数示例**：[0.json](../../ElectronJS/tasks/0.json) → `graph[2]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 2,
  "option": 4, // 输入文本
  "title": "Input Text",
  "type": 0,
  "isInLoop": false,
  "sequence": [],
  "parameters": {
    "useLoop": false,
    "xpath": "//*[@id=\"gh-ac\"]",
    "value": "iPhone",
    "wait": 0
  }
}
~~~

**从文件读取的参数示例**：[108.json](../../ElectronJS/tasks/108.json) → `graph[3]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 3,
  "option": 3, // 提取数据
  "title": "提取数据",
  "type": 0,
  "isInLoop": false,
  "sequence": [],
  "parameters": {
    "useLoop": false,
    "xpath": "",
    "wait": 0,
    "waitType": 0,
    "params": [
      {
        "name": "参数1_文本",
        "nodeType": 0,
        "contentType": 0,
        "relative": false,
        "relativeXPath": "/html/body/div[5]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]",
        "default": "",
        "downloadPic": 0
      },
      {
        "name": "参数2_文本",
        "nodeType": 0,
        "contentType": 0,
        "relative": false,
        "relativeXPath": "/html/body/div[4]/div[1]",
        "default": "",
        "downloadPic": 0
      },
      {
        "name": "参数3_链接文本",
        "nodeType": 1,
        "contentType": 0,
        "relative": false,
        "relativeXPath": "/html/body/div[4]/div[1]/div[4]/a[1]",
        "default": "",
        "downloadPic": 0
      },
      {
        "name": "参数4_链接地址",
        "nodeType": 2,
        "contentType": 0,
        "relative": false,
        "relativeXPath": "/html/body/div[4]/div[1]/div[4]/a[1]",
        "default": "",
        "downloadPic": 0
      },
      {
        "name": "参数5_文本",
        "nodeType": 0,
        "contentType": 0,
        "relative": false,
        "relativeXPath": "/html/body/div[5]/div[1]/div[1]/div[1]/div[3]/div[1]/div[4]/div[1]",
        "default": "",
        "downloadPic": 0
      }
    ]
  }
}
~~~

第 14 篇的普通 `inputText/singleClick/changeOption/mouseMove` 分别得到 option 4/2/6/7 的动作叶子；`collectSingle` 和 `collectMultiNoPattern` 都得到 option=3 的采集叶子，区别在 params 的字段数量及路径。

输入节点的 `xpath` 指定输入框，`value` 是要输入的文本；上例是在 eBay 搜索框输入 `iPhone`。采集节点的 `parameters.params` 列出字段，每项的 `name` 是输出字段名，`relativeXPath` 保存该字段的定位路径；`relative=false` 表示从页面定位，各字段不必共享同一条路径。

叶子的 `sequence=[]`。执行器不因叶子 JSON 中放了 sequence 就自动执行后继；顺序由它的父容器组织。多个无规律字段的定位由每个字段保存，不能为它们凭空制造一个共同父 XPath。

### 26. 批量输入：文本循环包含一个使用循环值的输入孩子

**从文件读取的参数示例**：[169.json](../../ElectronJS/tasks/169.json) → `graph[7]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 7,
  "option": 8, // 循环节点
  "title": "循环",
  "type": 1,
  "isInLoop": true,
  "sequence": [6, 8, 12, 13, 14, 15],
  "parameters": {
    "useLoop": false,
    "xpath": "A~B~C",
    "iframe": false,
    "loopType": "3", // 文本列表循环
    "pathList": "",
    "textList": "A~TField[\"自定义操作\"]T~C",
    "code": "",
    "waitTime": 0,
    "exitCount": 0,
    "historyWait": 2,
    "breakMode": 0,
    "breakCode": "",
    "breakCodeWaitTime": 0,
    "wait": 0,
    "waitType": 0,
    "scrollType": 0,
    "scrollCount": 1,
    "scrollWaitTime": 1
  }
}
~~~

**从文件读取的参数示例**：[169.json](../../ElectronJS/tasks/169.json) → `graph[8]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 8,
  "option": 4, // 输入文本
  "title": "输入文字",
  "type": 0,
  "isInLoop": true,
  "sequence": [],
  "parameters": {
    "useLoop": true,
    "xpath": "//*[@id=\"key\"]",
    "iframe": false,
    "value": "",
    "index": 0,
    "wait": 1,
    "waitType": 0
  }
}
~~~

第 14 篇 `batchInputText` 需要两层结构：外层循环选择本轮文本，内层输入消费该文本。169 任务还在循环里放了其他孩子；输入孩子确实位于 `sequence` 的第二项 8，而且 `useLoop=true`。

上面的循环对象保存 `loopType="3"` 和 `textList`；输入对象则保存目标输入框的 `xpath`、`useLoop=true`、空的 `value` 与 `index=0`。空 `value` 不表示本轮不输入，而是由执行器使用循环传入的文本。注意 `loopType` 在该原文件中是字符串，示例保持原样。

结构练习可以把循环体缩为 `[8]`、文本列表改成 `海淀\n朝阳`，但必须明确是修改版。原 JSON 中 `[6,8,12,13,14,15]` 不应被讲成只有一个输入节点。

### 27. 循环点击每项与循环悬停：选行容器加动作孩子

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json) → `graph[2]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 2,
  "option": 8, // 循环节点
  "title": "循环",
  "type": 1,
  "isInLoop": false,
  "sequence": [3, 4],
  "parameters": {
    "useLoop": false,
    "xpath": "/html/body/div[2]/div[10]/div[2]/div[1]/table[1]/tbody[1]/tr/td[5]/a[1]/span[1]/div[1]",
    "loopType": 1, // 不固定元素列表循环
    "pathList": "",
    "textList": "",
    "code": "",
    "waitTime": 0,
    "exitCount": 0,
    "historyWait": 2,
    "breakMode": 0,
    "breakCode": "",
    "breakCodeWaitTime": 0,
    "wait": 0,
    "scrollType": 0,
    "scrollCount": 1,
    "scrollWaitTime": 1
  }
}
~~~

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json) → `graph[3]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 3,
  "option": 2, // 点击元素
  "title": "点击元素",
  "type": 0,
  "isInLoop": true,
  "sequence": [],
  "parameters": {
    "useLoop": true,
    "xpath": "/html/body/div[2]/div[10]/div[2]/div[1]/table[1]/tbody[1]/tr/td[5]/a[1]/span[1]/div[1]",
    "loopType": 1, // 不固定元素列表循环
    "wait": 8,
    "maxWaitTime": 10,
    "scrollType": 0,
    "scrollCount": 1,
    "scrollWaitTime": 1,
    "params": []
  }
}
~~~

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json) → `graph[4]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 4,
  "option": 3, // 提取数据
  "title": "提取数据",
  "type": 0,
  "isInLoop": true,
  "sequence": [],
  "parameters": {
    "useLoop": false,
    "xpath": "",
    "wait": 0,
    "params": [
      {
        "name": "参数1_文本",
        "nodeType": 0,
        "contentType": 0,
        "extractType": 0,
        "relative": false,
        "relativeXPath": "/html/body/div[2]/div[2]/div[2]/div[2]/div[1]",
        "default": "",
        "downloadPic": 0
      }
    ]
  }
}
~~~

**从文件读取的参数示例**：[133.json](../../ElectronJS/tasks/133.json) → `graph[4]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 4,
  "option": 7, // 移动到元素（悬停）
  "title": "移动到元素",
  "type": 0,
  "isInLoop": true,
  "sequence": [],
  "parameters": {
    "useLoop": true,
    "xpath": "/html/body/div[5]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div",
    "iframe": false,
    "loopType": 1, // 不固定元素列表循环
    "wait": 0,
    "waitType": 0
  }
}
~~~

第 14 篇 `sendLoopClickEvery()` 的基本形式是元素循环包含点击孩子。此处点击循环 `[3,4]` 还包含后续详情采集，因此每一项都要先点再采；不能把采集节点放到循环外，否则只会在整个循环结束后采一次。

`sendLoopMouseMove()` 同样由循环选择当前项，option=7 孩子只负责悬停。133 任务中，这个悬停节点实际位于循环内的条件分支中：`graph[3] → graph[10] → graph[11] → graph[4]`；它仍通过 `useLoop=true` 使用当前循环项。共同 XPath 匹配的整组元素用 loopType=1；没有共同规则时用 loopType=2 的 pathList。新标签页或同页导航不会改变谁是谁的孩子，恢复由[第 17 篇第 24 节](17.Selenium详解.md#handle-history)结合浏览器行为解释。

### 28. 固定路径列表：把多条 XPath 保存在一个换行字符串

**从文件读取的参数示例**：[112.json](../../ElectronJS/tasks/112.json) → `graph[11]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 11,
  "option": 8, // 循环节点
  "title": "循环",
  "type": 1,
  "isInLoop": false,
  "sequence": [13, 12],
  "parameters": {
    "useLoop": false,
    "xpath": "",
    "iframe": false,
    "loopType": 2, // 固定路径列表循环
    "pathList": "//*[contains(@class, \"pagination\")]/ul[1]/li[1]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[2]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[3]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[4]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[5]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[6]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[7]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[8]/a[1]\n//*[contains(@class, \"pagination\")]/ul[1]/li[9]/a[1]",
    "textList": "",
    "code": "",
    "waitTime": 0,
    "exitCount": 0,
    "historyWait": 2,
    "breakMode": 0,
    "breakCode": "",
    "breakCodeWaitTime": 0,
    "wait": 0,
    "waitType": 0,
    "scrollType": 0,
    "scrollCount": 1,
    "scrollWaitTime": 1
  }
}
~~~

这对应第 14 篇在不规则选择下发送 `pathList` 的场景。每行是一项，不是 JSON 数组；`loopExecute()` 先 `.split("\n")`，逐条定位，再对同一 sequence 执行动作。当前路径已经选定一项，因此传给孩子的元素索引为 0，不继续沿用路径列表的 index。

这份 112 任务的固定循环实际孩子为 `[13,12]`，包含嵌套采集与点击；其他任务也可以把唯一采集节点放进去，满足条件时整体走快速提取。场景的共同点是选择项的方式，孩子列表由业务决定。

### 29. 有规律的多元素与带子元素采集：外层选记录，内层选字段

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[7]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 7,
  "option": 8, // 循环节点
  "title": "循环",
  "type": 1,
  "isInLoop": true,
  "sequence": [8],
  "parameters": {
    "useLoop": false,
    "xpath": "/html/body/div[1]/div[5]/div[1]/div[1]/div[2]/ul[1]/li/a[1]",
    "loopType": 1, // 不固定元素列表循环
    "pathList": "",
    "textList": "",
    "code": "",
    "waitTime": 0,
    "exitCount": 0,
    "historyWait": 2,
    "breakMode": 0,
    "breakCode": "",
    "breakCodeWaitTime": 0,
    "wait": 0,
    "scrollType": 0,
    "scrollCount": 1,
    "scrollWaitTime": 1
  }
}
~~~

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[8]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 8,
  "option": 3, // 提取数据
  "title": "提取数据",
  "type": 0,
  "isInLoop": true,
  "sequence": [],
  "parameters": {
    "useLoop": false,
    "xpath": "",
    "wait": 0,
    "params": [
      {
        "name": "参数1_链接文本",
        "nodeType": 1,
        "contentType": 0,
        "extractType": 0,
        "relative": true,
        "relativeXPath": "",
        "default": "",
        "downloadPic": 0
      },
      {
        "name": "参数2_链接地址",
        "nodeType": 2,
        "contentType": 0,
        "relative": true,
        "relativeXPath": "",
        "default": "",
        "downloadPic": 0
      }
    ]
  }
}
~~~

**从文件读取的参数示例**：[0.json](../../ElectronJS/tasks/0.json) → `graph[7]`（保留结构字段与相关执行参数，值保持原样；params 共 207 项，此处仅展示前 3 项）。

~~~jsonc
{
  "index": 7,
  "option": 3, // 提取数据
  "title": "Collect Data",
  "type": 0,
  "isInLoop": true,
  "sequence": [],
  "parameters": {
    "useLoop": false,
    "xpath": "",
    "loopType": 1, // 不固定元素列表循环
    "wait": 0,
    "params": [
      {
        "name": "para1_link_text",
        "nodeType": 1,
        "contentType": 0,
        "relative": true,
        "relativeXPath": "/div[1]/div[1]/div[1]/a[1]",
        "default": "",
        "downloadPic": 0
      },
      {
        "name": "para2_link_address",
        "nodeType": 2,
        "contentType": 0,
        "relative": true,
        "relativeXPath": "/div[1]/div[1]/div[1]/a[1]",
        "default": "",
        "downloadPic": 0
      },
      {
        "name": "para3_image_address",
        "nodeType": 4,
        "contentType": 1,
        "relative": true,
        "relativeXPath": "/div[1]/div[1]/div[1]/a[1]/div[1]/img[1]",
        "default": "",
        "downloadPic": 0
      }
    ]
  }
}
~~~

采集字段里的 `nodeType=1` 表示链接文本，`nodeType=2` 表示链接地址，`nodeType=4` 表示图片地址；`contentType` 另行指定提取内容的方式。eBay 示例共保存 207 个采集字段，上面仅列出前 3 个，展示同一商品块中的标题、链接与图片路径，完整列表见原文件。

第 14 篇 `collectMultiWithPattern()` 在“提取全部元素”下形成循环 + 采集：当前项本身就是字段，relativeXPath 为空。选中整块再提取子元素时，循环仍负责选记录，但 relativeXPath 是块内位置。前者在本例得到链接文字和 href，后者在 eBay 商品块内得到标题、链接及图片。

不固定列表从共同 xpath 选行；固定列表从 pathList 选行。不能把一个多字段采集节点拆成“每字段一个兄弟循环”，否则原来同一记录的字段会失去对应关系。

### 30. 循环点击单元素与两种翻页入口：孩子的位置决定先采还是先翻

**从文件读取的参数示例**：[第一步：采集列表超链接地址.json](../../Examples/汽车新闻采集/第一步：采集列表超链接地址.json) → `graph[2]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 2,
  "option": 8, // 循环节点
  "title": "循环点击下一页",
  "type": 1,
  "isInLoop": false,
  "sequence": [6, 3],
  "parameters": {
    "useLoop": false,
    "xpath": "//*[contains(@class, \"tw-mb-40\")]/ul[1]/li[last()]/a[1]/span[1]",
    "loopType": 0, // 单元素循环
    "pathList": "",
    "textList": "",
    "code": "",
    "waitTime": 0,
    "exitCount": 5,
    "historyWait": 2,
    "breakMode": 0,
    "breakCode": "",
    "breakCodeWaitTime": 0,
    "wait": 0,
    "scrollType": 0,
    "scrollCount": 1,
    "scrollWaitTime": 1
  }
}
~~~

**从文件读取的参数示例**：[第一步：采集列表超链接地址.json](../../Examples/汽车新闻采集/第一步：采集列表超链接地址.json) → `graph[3]`（保留结构字段与相关执行参数，值保持原样）。

~~~jsonc
{
  "index": 3,
  "option": 2, // 点击元素
  "title": "点击下一页",
  "type": 0,
  "isInLoop": true,
  "sequence": [],
  "parameters": {
    "useLoop": true,
    "xpath": "//*[contains(@class, \"tw-mb-40\")]/ul[1]/li[8]/a[1]/span[1]",
    "loopType": 0, // 单元素循环
    "wait": 2,
    "maxWaitTime": 10,
    "scrollType": 0,
    "scrollCount": 1,
    "scrollWaitTime": 1,
    "params": []
  }
}
~~~

第 14 篇 `sendLoopClickSingle(name)` 有三个入口：普通按钮保留 `loopClickSingle, nextPage=false`；“下一页元素”保留 `loopClickSingle` 并设 `nextPage=true`；“nextPageFromIndexPage” 则发 `loopClickNextPage, nextPage=true`。最后一种会根据 `lastAction.includes("WithLoop")` 移入已有采集循环。执行侧最终落实为 loopType=0 容器与孩子序列。

汽车新闻任务 `graph[2].sequence=[6,3]`，先执行 6 的列表采集，再执行 3 的下一页点击。因此 exitCount=5 是执行五轮“采本页 + 点下一页”，正常情况下采的是开始页起的五页，同时末尾仍点第五次下一页；不是只翻四次的手写程序。

两个入口在界面组织已有节点的方式上有区别，正式执行器不按按钮名称分发，它只读保存结果的 loopType 与 sequence。下一页节点必须是采本页节点的后一个孩子；若把下一页放进每个商品的循环体，就会每处理一个商品翻一次页。

---

返回目录：[README.md](README.md) ｜ 上一篇：[14.messageInteraction.js：每条消息怎样把操作台接到流程图](14.messageInteraction.js详解.md) ｜ 下一篇：[16.Flowchart 与 Python 执行器：递归、控制流与数据落盘](16.Flowchart递归执行原理.md)
