---
title: "完整讲义目录"
description: "easyspider · 参考与演示 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/README.md"
originalUrl: "/originals/easyspider/directory.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# EasySpider 源码讲义 · 总目录

这套讲义按源码中的业务依赖组织：先读第 00～02 篇建立全局观，再走通扩展的选择、参数、预览和消息，第 15 篇回答任务怎样存，第 16 篇回答怎样递归执行，第 17 篇再用 Selenium 落实具体浏览器操作，并集中讲新标签页与同页历史恢复。执行阶段在第 15–17 篇讲完，之后继续讲稳定下标与界面编号、渲染与增删改查，再接入消息、保存加载、Electron、调试与本地服务，最后用第 27 篇串起开发环境搭建、源码调试、版本更新、打包与发布；需要提前动手时，可先读第 27 篇前两部分。

## 一、总体与导读

| 序号 | 标题 | 内容 |
| --- | --- | --- |
| [00](/easyspider/chapter-00) | 讲义导读与学习路线 | 项目零件、进程与推荐阅读顺序 |
| [01](/easyspider/chapter-01) | 总体架构与目录剖析 | 文件夹职责与通信全景 |
| [02](/easyspider/chapter-02) | 数据流全链路 | 从选中元素到数据落盘 |

## 二、扩展基础

| 序号 | 标题 | 关键文件 |
| --- | --- | --- |
| [03](/easyspider/chapter-03) | Chrome 扩展开发（MV3） | manifest、content script、后台脚本 |
| [04](/easyspider/chapter-04) | XPath 元素定位 | global.js 的 readXPath 等 |

## 三、扩展选择、参数与遍历

| 序号 | 标题 | 核心函数或概念 |
| --- | --- | --- |
| [05](/easyspider/chapter-05) | 元素待选与选中机制 | addEl / readyToList / clearEl |
| [06](/easyspider/chapter-06) | 同类元素自动匹配 | findRelated |
| [07](/easyspider/chapter-07) | 手动匹配与相对 XPath | relatedTest / combineXpath |
| [08](/easyspider/chapter-08) | 参数生成 | 四种选择场景、完整字段 dict、内容类型与父级 XPath |
| [09](/easyspider/chapter-09) | DFS 与 BFS | A～H 树、栈、队列、逐轮推理 |
| [10](/easyspider/chapter-10) | 选中子元素与预览表 | handleDescendents 的模式 0、2；路径交集与字段映射；generateValTable 的逐格转换 |

## 四、界面与消息

| 序号 | 标题 | 具体内容 |
| --- | --- | --- |
| [11](/easyspider/chapter-11) | Vue 背景：模板、状态与构建 | 操作台的前置背景；仓库 Vue 2.7 与 Vue3 对照 |
| [12](/easyspider/chapter-12) | toolkit.vue 业务详解 | 选择、预览、确认、删行删列、输入、点击和翻页 |
| [13](/easyspider/chapter-13) | WebSocket 实时通信 | 三进程连接与消息往返 |
| [14](/easyspider/chapter-14) | 消息交互详解 | 发送函数、六种接收分支、两层 JSON、循环路径与编号回传 |

~~~text
选择 nodeList → 匹配/遍历 → outputParameters → generateValTable
                                                    ↓
                                          toolkit.vue 预览与确认
                                                    ↓
                                          messageInteraction.js
                                                    ↓
                                        Flowchart：存储与执行结构
~~~

## 五、执行阶段：任务结构 → 递归执行 → Selenium 操作

统一使用“海淀/朝阳、两轮页面、五个房源、只采单间”的例子，先理解操作怎样组织、循环怎样调用孩子，再看浏览器怎样执行。真实任务的 JSON 参数与源码按场景对照。

| 序号 | 标题 | 读完应该能回答 |
| --- | --- | --- |
| [15](/easyspider/chapter-15) | 层次关系、逐步搭图与完整执行树 | 为什么需要容器？从 root 加动作和循环时，nodeList 与 sequence 怎样变？房源图怎样对应代码？ |
| [16](/easyspider/chapter-16) | 递归执行、控制流与正式执行器 | 循环怎样先找到当前元素，再调用 executeNode？为什么只采 A、C、E？数据怎样保存、续采与收尾？ |
| [17](/easyspider/chapter-17) | Selenium：基本操作、真实参数与历史恢复 | JSON 怎样驱动输入、点击与提取？循环点单个元素和逐个链接有何区别？handleHistory 怎样恢复列表？ |

配套材料：

- [本地练习页与 Python 样例](/source/?file=b2ee2869ff9f486627.md)：17 组独立操作和完整房源采集程序。
- [房源三栏原图](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%88%BF%E6%BA%90%E9%87%87%E9%9B%86-%E6%B5%81%E7%A8%8B%E4%B8%8E%E6%89%A7%E8%A1%8C%E6%A0%91-%E5%8E%9F%E7%89%88.png)：保留原始文字、布局与蓝色 1–16 执行阶段编号；节点下标另见正文。
- [房源教学模型与手算说明](/source/?file=91ecaf27be672c6f80.md)：关键参数、完整编号表、正常路径记录和预期次数。
- [房源教学模型 JSON](/source/?file=ce174a47484f884969.json)：第15篇的结构与参数对照。
- [房源教学页面](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Flowchart/%E6%88%BF%E6%BA%90%E9%87%87%E9%9B%86-%E6%95%99%E5%AD%A6%E9%A1%B5.html)：第16篇开头截图对应的页面，可切换地区与翻页。

## 六、Flowchart 界面：数据结构 → 渲染 → 增删改查 → 消息 → 保存加载

| 序号 | 标题 | 读完应该能回答 |
| --- | --- | --- |
| [18](/easyspider/chapter-18) | 稳定下标与界面编号 | 只用 nodeList 行不行？为什么还要 actionSequence 和 BFS？同一张双层循环图怎样编号和定位？ |
| [19](/easyspider/chapter-19) | 逐步渲染：refresh、DOM 与 CSS | 每一步怎样编号和追加 HTML？方块、嵌套循环、横向分支的代码与截图怎样对应？ |
| [20](/easyspider/chapter-20) | 查询、参数、锚点与结构编辑 | 怎样调整插入锚点？Vue 怎样切换右侧参数区域？新增、移动和删除分别改哪里？ |
| [21](/easyspider/chapter-21) | 消息复用新增与移动入口 | batchInputText 怎样创建循环与输入？消息何时只改已有节点？ |
| [22](/easyspider/chapter-22) | 案例：循环采集子元素与 Vue 参数栏 | 网页、消息、parameters、流程图和右侧字段表怎样对应？修改字段时变量怎样流动？ |
| [23](/easyspider/chapter-23) | 任务 JSON 的磁盘往返 | graph 与输入输出摘要怎样保存？加载和执行为什么不需要界面映射？ |

配套[附录 B：流程图三数组与 refresh](/resources/easyspider/%E9%99%84%E5%BD%95B.%E4%BA%A4%E4%BA%92%E5%BC%8F%E5%9B%BE%E8%A7%A3-%E6%B5%81%E7%A8%8B%E5%9B%BE%E4%B8%89%E6%95%B0%E7%BB%84%E4%B8%8Erefresh.html)，配合第 18～20 篇。

## 七、Electron、调试功能与本地服务

| 序号 | 标题 | 关键内容 |
| --- | --- | --- |
| [24](/easyspider/chapter-24) | ElectronJS、浏览器操作与调试消息 | 窗口、IPC、WebSocket；主进程用 WebDriver 模拟输入/点击，处理试运行并向插件发消息 |
| [25](/easyspider/chapter-25) | 调试功能详解 | 插件接收消息；逐项讲目标、字段与循环标记、条件预览和试运行反馈 |
| [26](/easyspider/chapter-26) | Node.js 与 Express | 本地服务、任务存取与文件传输 |

执行阶段在第 15–17 篇讲完：第 15 篇讲任务结构及第 14 篇各操作场景的组织；第 16 篇讲递归、循环/条件、输入覆盖、数据保存、续采、暂停/停止与真实端到端任务；第 17 篇讲 Selenium 基础、动作参数、驱动、提取和 handleHistory 的浏览器恢复。第 18–26 篇继续讲设计界面的数据结构、渲染、增删改查、消息、保存与桌面服务。

## 八、项目开发、调试、打包与发布

| 序号 | 标题 | 关键内容 |
| --- | --- | --- |
| [27](/easyspider/chapter-27) | 项目开发、调试、打包与发布 | 开发环境、源码启动、分进程断点、端到端验证、版本同步、平台构建、组装、压缩、Release 与更新检查 |

## 九、其他配套材料

- [附录 A：XPath 匹配与 DFS 栈变化](/resources/easyspider/%E9%99%84%E5%BD%95A.%E4%BA%A4%E4%BA%92%E5%BC%8F%E5%9B%BE%E8%A7%A3-XPath%E5%8C%B9%E9%85%8D%E4%B8%8EDFS.html)：配合第 6 ～ 10 篇。
- [示例扩展：字数统计器](/source/?file=0f9d6abe67b82d0c7f.md)：第 3 篇的可运行扩展。
- [示例：同类元素匹配](/resources/easyspider/%E7%A4%BA%E4%BE%8B-%E5%90%8C%E7%B1%BB%E5%85%83%E7%B4%A0%E5%8C%B9%E9%85%8D/index.html)：第 6 篇的演示页。

## 建议阅读节奏

~~~text
第 1 次：00 → 01 → 02                    建立全局观
第 2 次：03 → 04                         Chrome 扩展与 XPath
第 3 次：05 → 06 → 07                    选择与匹配
第 4 次：08 → 09 → 10                    字段、遍历、子元素采集与预览
第 5 次：11 → 12                         Vue 背景与操作台
第 6 次：13 → 14                         WebSocket 与操作消息
第 7 次：15 → 16                         任务结构、递归、控制流与正式执行器
第 8 次：17                              Selenium 基础、真实参数、动作与历史恢复
第 9 次：18 → 19 → 20                    界面编号、渲染与增删改查
第 10 次：21 → 22 → 23                   消息入图、子元素采集参数栏案例与保存加载
第 11 次：24 → 25 → 26                   Electron、调试功能与本地服务
第 12 次：27                             开发环境、源码调试、打包与发布
~~~

第 15–17 篇贯通 Selenium、任务结构和正式执行器；第 18～23 篇沿用第 15 篇构建的节点结构，先讲稳定下标与界面编号，接着讲渲染和增删改查，再讲消息加节点，最后讲保存与加载，第 24～26 篇依次讲 Electron、调试功能和 Node/Express；第 27 篇先搭建环境、启动源码并完成分进程调试，再把三部分源码与浏览器环境组装成发布包，讲清 Release 与更新检查的衔接。

开始阅读：[00.讲义导读与学习路线](/easyspider/chapter-00)。

目录位置：`Docs/讲义/` ｜ 配套源码：EasySpider（AGPL-3.0） ｜ 作者：王乃博
