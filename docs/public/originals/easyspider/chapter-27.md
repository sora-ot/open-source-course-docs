# 27.项目开发、调试、打包与发布

> 前面的讲义逐步解释了 EasySpider 的业务与源码。本篇把工程实践串成一条完整路线：**搭建环境 → 从源码启动 → 分进程调试 → 验证任务 → 构建并组装 → 压缩发布 → 检查更新。**

先用本地网页跑通一个“打开网页 → 采集标题”的任务，再沿扩展、Electron、流程图和 Python 的断点观察数据，最后把验证过的环境交付给用户。

本篇以 **Windows x64、PowerShell、VS Code 打开仓库根目录**为主要操作路线，分别补充 Linux、macOS 的开发与发布差异。命令块会标明工作目录；请按阶段执行并检查结果。

**阅读导航：**

| 部分 | 章节 | 内容 |
| --- | --- | --- |
| 一 | [1～6 节](#1-先分清你究竟在运行哪一份代码) | 开发环境搭建与源码启动 |
| 二 | [7～14 节](#7-调试-electron-主进程看消息怎样转发) | 源码调试与端到端验证 |
| 三 | [15～16 节](#15-用户没有你的开发环境) | 从开发验收到发布流程 |
| 四 | [17～20 节](#17-更新版本为什么不只改-packagejson) | 版本、浏览器、执行器与扩展构建 |
| 五 | [21～24 节](#21-electron-forgepackage-和-make-分别在哪一层) | Electron 与各平台发布目录组装 |
| 六 | [25～30 节](#25-compresspy按当前平台选择最终文件名) | 压缩、验证、发布与检查更新 |

初次搭建环境可先完成第 1～6 节；需要跟踪源码时继续第 7～14 节。准备发版时，从第 15 节进入发布流程；第 18、20 节还会解释前面使用的浏览器准备与扩展构建脚本。

这里的“源码调试”包括断点、变量和调用栈。[第 25 篇](25.调试功能详解.md) 则解释软件面向用户提供的标记、条件预览和试运行功能，可配合本篇的调试器一起观察。

发布部分以仓库的 [发布备忘录](../../ElectronJS/发布备忘录.md) 和各平台脚本为依据，逐项说明输入、输出、依赖顺序与遗留问题。文中的 `0.6.5` 是阅读源码时的版本，`0.6.6` 仅为下一次发版的教学示例；本文不代表已执行版本升级或发布操作。

---

# 第一部分：开发环境搭建与源码启动

## 1. 先分清：你究竟在运行哪一份代码

项目里有两份同名的 `main.js`，还有一个同样用 JavaScript 写的流程图页面。它们所在的进程不同：

~~~text
Chrome：被采集的网页
  └── 扩展内容脚本
      Extension/manifest_v3/src/content-scripts/main.js
                     │ WebSocket 8084
                     ▼
Electron 主进程
  ElectronJS/main.js
    ├── 创建窗口、启动设计用 Chrome、转发消息
    ├── server.js：HTTP 8074；Excel 上传 8075
    └── Electron 页面：src/taskGrid/logic.js、FlowChart.js
                     │ HTTP / 子进程
                     ▼
Python 执行器
  ExecuteStage/easyspider_executestage.py
    └── 创建执行用 Chrome、运行节点、保存结果
~~~

**设计用 Chrome 与正式执行用 Chrome 是不同的浏览器会话。** 前者由 Electron 中的 JavaScript Selenium 控制；后者由 Python Selenium 控制。

| 要观察的现象 | 对应源码 | 调试器应该连到哪里 |
| --- | --- | --- |
| 鼠标选中元素、操作台、生成 XPath | 扩展的 `main.js`、`global.js`、`toolkit.vue` | 设计用 Chrome 中目标网页的 DevTools |
| 收到 WebSocket 消息、转发给流程图 | `ElectronJS/main.js` | Electron 主进程 inspector |
| 增加节点、改参数、保存任务 | `ElectronJS/src/taskGrid/` | 流程图窗口的 DevTools |
| HTTP 路由、读写任务文件 | `ElectronJS/server.js` | Electron 主进程 inspector |
| 正式执行节点、提取数据、写文件 | `ExecuteStage/easyspider_executestage.py` | 启动该 Python 源码的调试器 |

如果断点总是灰色或一直不命中，先确认：**调试器连的是这个进程吗？进程加载的是你改的这份文件吗？**

## 2. 开发环境需要哪些工具

### 2.1 工具与版本从哪里确认

| 工具 | 用途 | 本仓库的依据 |
| --- | --- | --- |
| Git | 获取源码、查看改动；发布时筛选样例 | 后文的发布组装脚本还会读取 Git 跟踪记录 |
| Node.js、npm | 安装两套 JS 工程依赖，构建扩展、启动 Electron | 两个 `package.json` 与各自锁文件 |
| Python | 运行执行器和辅助脚本 | `ExecuteStage/requirements.txt` |
| Chrome、ChromeDriver | 设计和正式执行网页操作 | `ElectronJS/main.js` 与执行器中的资源路径 |
| VS Code | 阅读源码、断点、调用栈 | 本讲提供工作区配置示例 |
| Windows C++ 构建工具 | 编译依赖中的原生 Node 模块 | `ElectronJS/README.md` 的环境说明 |

Python 开发环境以 **3.11、64 位**作为本讲统一起点：当前 Linux、macOS 执行器构建脚本也明确检查 Python 3.11。Windows 32 位有独立的旧依赖路线，详见本篇第 19.5、22.4 节。

仓库当前 `ElectronJS/package.json` 声明 Electron `^27.1.3`，扩展工程使用 Vue `^2.7.14`、Rollup `^2.38.5`。这是读取源码时的依赖声明，实际安装版本还要看锁文件与安装结果。讲义中的“Vue3 背景”不意味着要把此工程的 Vue 直接升级到 3。

仓库没有在这两个 `package.json` 中统一固定开发用 Node 版本。搭建成功后应记录 `node --version`、`npm --version` 与 Python 版本，方便复现；不必为跟随某个工具的最新版本而同时升级整套项目依赖。

### 2.2 先确认命令找得到

从仓库根目录打开 PowerShell：

~~~powershell
git --version
node --version
npm --version
py -3.11 --version
~~~

如果系统没有 Windows Python Launcher 的 `py` 命令，使用已安装 Python 3.11 的完整路径替代。`python --version` 指向什么版本也要确认，不能只凭“机器上装过 Python”判断。

从 ZIP 解压的源码可以做开发练习，但可能没有 Git 仓库信息；后文依赖 `git ls-files` 的发布步骤还需要完整的 Git 工作副本。

## 3. 安装三套工程的依赖

### 3.1 先记住目录地图

~~~text
EasySpider/                         ← VS Code 打开的工作区
├── .venv/                          ← 本讲新建的 Python 虚拟环境
├── ElectronJS/
│   ├── package.json
│   ├── package-lock.json
│   ├── node_modules/               ← Electron 工程的依赖
│   ├── tasks/                      ← 开发模式的任务模板
│   └── execution_instances/        ← 开发模式的执行实例
├── Extension/manifest_v3/
│   ├── package.json
│   ├── package-lock.json
│   └── node_modules/               ← 扩展工程的依赖
└── ExecuteStage/
    ├── requirements.txt
    └── easyspider_executestage.py
~~~

两个 `node_modules` 各自安装。在仓库根目录运行一次 `npm install`，不能替代它们。

### 3.2 Python：建虚拟环境，直接调用其中的解释器

当前目录：**仓库根目录**。

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ExecuteStage\requirements.txt
.\.venv\Scripts\python.exe -m pip check
~~~

本讲直接写出虚拟环境解释器路径，避免终端是否激活、PowerShell 激活脚本能否执行等问题影响判断。

`python -m pip` 会把依赖装到这个 Python 对应的环境。安装时如果某个固定版本找不到，先检查 Python 版本、架构、包源和完整错误信息；不要静默删掉版本约束后继续把结果当成同一套环境。

可以再运行仓库中的依赖冒烟检查：

~~~powershell
.\.venv\Scripts\python.exe scripts\smoke_python_dependencies.py
~~~

这个脚本实际使用图片处理、OCR、Excel、Pandas 等依赖；它验证当前 Python 环境，不会启动 EasySpider，也不会验证最终发布包。Linux 的桌面显示与键盘依赖还需满足当前运行环境。

### 3.3 扩展：在 manifest_v3 目录安装

当前从**仓库根目录**出发：

~~~powershell
cd Extension\manifest_v3
npm install
~~~

此工程会构建 TypeScript、Vue、CSS 和 manifest。不要把 `src/` 中的 TypeScript、Vue 文件直接当成已经能加载的发布扩展。

### 3.4 Electron：安装主程序依赖

当前目录：`Extension/manifest_v3`。

~~~powershell
cd ..\..\ElectronJS
npm install
~~~

Windows 如果卡在 `node-gyp`、原生模块编译阶段，先按 [ElectronJS 环境说明](../../ElectronJS/README.md) 准备所需的 C++ 工具链。安装输出里的下载失败、编译失败与应用运行错误是不同阶段的问题。

如确认为原生模块与 Electron 运行时不匹配，可参考该说明中的 `npx electron-rebuild`。`electron-rebuild` 已列在当前开发依赖里，不需要把每次启动都变成重新安装、重新编译。

安装完成后再进入下一步。不要只因为终端回到了提示符，就跳过非零退出状态与报错信息。

## 4. 准备设计与执行要用的浏览器资源

### 4.1 主程序找的是工程中的浏览器

Windows x64 的关键文件是：

~~~text
ElectronJS/
├── chrome_win64/
│   ├── chrome.exe
│   ├── Chrome 自身的其他资源
│   ├── chromedriver_win64.exe
│   ├── execute_win64.bat
│   └── stealth.min.js
├── stealth.min.js
└── XPathHelper_MV3/
    └── manifest.json
~~~

`main.js` 显式指定浏览器和驱动路径。所以系统 Chrome 能正常打开，并不代表 EasySpider 已找到它要启动的 Chrome。

### 4.2 两种准备方式

**方式一：使用仓库的更新脚本。**

当前目录：`ElectronJS`。

~~~powershell
..\.venv\Scripts\python.exe update_chrome.py
~~~

脚本会生成 stealth、下载驱动、删除旧的工程浏览器目录，再复制本机已经安装的 Chrome。它不会替你把本机 Chrome 安装成最新版。已有目录中的冻结执行器等文件也可能被一并移除，因此应先确认没有需要保留的内容。

本机 Chrome 不在脚本写死的路径、版本检测不正确或目标平台不同，都需要先核对脚本；完整分析见 [第 18 节](#18-更新浏览器复制本机-chrome再准备驱动)。

**方式二：手工准备匹配的资源。**

按 `ElectronJS/README.md` 的路线，复制完整 Chrome 目录，放入兼容的驱动，并按上述文件名组织资源；也可以从自己已验证的同平台 EasySpider 包中复制对应浏览器资源目录。

从发布包复制资源只是准备运行环境。之后启动的应当仍是本仓库的 Electron 主程序，不能误点发布包的 exe，结果一直在看旧代码。

### 4.3 用“实际文件”检查

当前目录：`ElectronJS`。

~~~powershell
Test-Path .\chrome_win64\chrome.exe
Test-Path .\chrome_win64\chromedriver_win64.exe
Test-Path .\chrome_win64\execute_win64.bat
Test-Path .\stealth.min.js
Test-Path .\XPathHelper_MV3\manifest.json
.\chrome_win64\chromedriver_win64.exe --version
~~~

同时在这份 Chrome 中确认浏览器版本。文件存在只是第一步，还要验证浏览器与驱动能真正建立会话，以及当前浏览器是否支持源码采用的扩展安装方式。

Python 源码调试不依赖已经生成的 `easyspider_executestage.exe`。只有要验证界面直接启动冻结执行器时，才需要按本篇第 19 节生成它。

## 5. 构建扩展，再从源码启动 Electron

### 5.1 构建中英文扩展

当前从**仓库根目录**出发：

~~~powershell
cd Extension\manifest_v3
npm run package
~~~

`package.js` 会修改 `src/content-scripts/config.json` 中的语言，分别构建英文和中文，再把目录、CRX 复制到 `ElectronJS/`。

完成后检查：

~~~powershell
Test-Path ..\..\ElectronJS\EasySpider_zh\manifest.json
Test-Path ..\..\ElectronJS\EasySpider_en\manifest.json
~~~

当前 `main.js` 使用 BiDi 从 `EasySpider_zh/`、`EasySpider_en/` 目录安装扩展，还会安装 `XPathHelper_MV3/`。只检查 CRX 是否生成不够。

源码、构建输出和实际加载目录之间的关系是：

~~~text
Extension/manifest_v3/src/
        ↓ Rollup
Extension/manifest_v3/dist/
        ↓ package.js 按语言整理并复制
ElectronJS/EasySpider_zh/ 或 EasySpider_en/
        ↓ main.js 通过 BiDi 安装
设计用 Chrome 里的扩展
~~~

### 5.2 启动主程序

当前目录：`Extension/manifest_v3`。

~~~powershell
cd ..\..\ElectronJS
npm run start_direct
~~~

`start_direct` 实际执行 `cross-env NODE_ENV=development electron .`，入口来自 `package.json` 的 `"main": "main.js"`。

保留这个终端。主进程的 `console.log`、启动 Chrome 的异常、本地服务错误，通常都要先从这里看。

默认端口分工：

| 端口 | 内容 | 是否应跟着随意改 |
| --- | --- | --- |
| 8074 | 主本地 HTTP 服务，任务与页面 | 由配置控制；改动后同步检查所有调用地址 |
| 8075 | Excel 上传 | 当前 server.js 固定监听 |
| 8084 | 扩展与界面 WebSocket | 扩展源码写死；只改一边会断连 |
| 8765 | 本讲临时练习网页 | 自己选择；与项目服务独立 |
| 9229 | 后面调试 Electron 主进程 | 调试时才启用 |

先访问 `http://localhost:8074/queryTasks`，确认返回任务列表。HTTP 服务正常不意味着 8084 已连通，也不意味着扩展安装成功，要继续验证设计入口。

只保留一份正在运行的 EasySpider 主程序。已启动的发布版也可能占用这些端口。

### 5.3 用本地网页做第一次验收

另开终端，当前目录：**仓库根目录**。

~~~powershell
.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory "Docs/讲义/示例-Selenium"
~~~

在 EasySpider 里创建任务，网址填写：

~~~text
http://127.0.0.1:8765/index.html
~~~

选择中文进入设计后，确认：

1. 出现设计用 Chrome 和流程图窗口。
2. 网页中出现 EasySpider 操作台。
3. 右键选中一个房源标题，能够看到高亮和采集预览。
4. 确认采集后，流程图新增提取数据节点。
5. 保存成一个自己的练习任务。

先做一次简单的“打开网页 → 采集标题”，输出选择 CSV。循环、登录信息、OCR、去重和复杂条件可以留到后面的讲义。

练习页已有完整说明：[示例-Selenium/README.md](示例-Selenium/README.md)。此处先用它作为固定网页，不需要同时运行 `demo.py`。

## 6. 保存任务后，先生成执行实例，再运行 Python

### 6.1 两套编号为什么不能混用

本地服务中：

~~~text
tasks/T.json                      任务模板
        ↓ 执行页 POST /invokeTask
execution_instances/E.json       本次执行实例
        ↓ Python --ids [E]
真正执行
~~~

任务模板编号 `T` 与执行实例编号 `E` 可能恰好相同，也可能不同。调试时必须记下它们各自的含义。

在任务执行页面填写好参数，点击 **“获得任务执行ID”**，记录页面返回的 EID。这个入口在 [executeTask.html](../../ElectronJS/src/taskGrid/executeTask.html) 的 `invokeTask()` 中，调用 `server.js` 的 `/invokeTask`，生成执行实例。

假设本次得到 EID 为 `12`，先在浏览器或终端确认：

~~~text
http://localhost:8074/queryExecutionInstance?id=12
~~~

应当返回你刚创建的本地练习任务，而不是另一个任务。**12 只是下面命令的示例，实际使用自己的 EID。**

### 6.2 在另一个终端直接运行源码

当前目录：**仓库根目录**，保留 Electron 和练习网页服务两个终端。

~~~powershell
cd ExecuteStage
..\.venv\Scripts\python.exe easyspider_executestage.py --ids '[12]' --read_type remote --server_address http://localhost:8074 --headless 0 --user_data 0 --keyboard 0
~~~

| 参数 | 在本次练习中的含义 |
| --- | --- |
| `--ids '[12]'` | 读取执行实例 12；方括号表示列表 |
| `--read_type remote` | 向本地 HTTP 服务读取执行实例 |
| `--server_address` | 这里的 remote 仍指本机 8074，不需要另一台电脑 |
| `--headless 0` | 显示执行用 Chrome，便于观察 |
| `--user_data 0` | 从纯净模式开始，减少已有登录状态干扰 |
| `--keyboard 0` | 禁用暂停键监听，使用调试器控制暂停与继续 |

`remote` 模式下，Electron 的任务服务要保持运行。这里没有启用执行器自己的远程控制服务，`--read_type remote` 与 `--remote_control` 是两回事。

### 6.3 为什么特意 cd ExecuteStage

Windows x64、Linux 的开发路径检测会利用：

~~~text
当前工作目录/../ElectronJS/
~~~

从 `ExecuteStage` 运行时，能找到兄弟目录中的浏览器资源；从仓库根目录直接运行同一个文件，可能走进另一个路径分支。

Python 启动时还计算 `DATA_DIRECTORY` 并执行 `os.chdir(DATA_DIRECTORY)`。本讲从普通终端启动源码、没有设置 `EASYSPIDER_DATA_DIR` 时，数据目录默认由当前工作目录决定。

因此本次典型路径为：

~~~text
ElectronJS/tasks/T.json                   保存的任务
ElectronJS/execution_instances/E.json     主程序生成的执行实例
ExecuteStage/Data/Task_E/...               这次手动运行源码产生的结果
~~~

如果继承了 `EASYSPIDER_DATA_DIR` 环境变量，或通过 Electron 启动冻结执行器，实际数据目录可能不同。先看启动参数、环境变量和日志，不能只在一个固定 Data 目录里找。

### 6.4 local 模式还要准备本地实例文件

将 `--read_type` 改成 `local` 后，源码会在本地实例目录查找 `E.json`，Windows、Linux 通常跟随运行数据目录下的 `execution_instances/`。

它不会因为你开着编辑器，就自动去读取 `ElectronJS/tasks/`。本讲先统一用 remote 模式，等明确执行实例与数据目录后再练习离线执行；macOS 的本地实例目录还有单独分支。

运行成功后，确认执行用 Chrome 打开练习页，并在输出中看到自己选取的标题。至此，开发环境才完成第一轮端到端验收。


# 第二部分：源码调试与端到端验证

## 7. 调试 Electron 主进程：看消息怎样转发

### 7.1 用 inspector 启动

先关闭普通方式启动的 EasySpider，释放它占用的端口。保留本地练习网页服务。

当前目录：`ElectronJS`，Windows PowerShell：

~~~powershell
$env:NODE_ENV = "development"
npx electron --inspect-brk=9229 .
~~~

`--inspect-brk` 会在主进程 JavaScript 开始执行时暂停，等待调试器连接。此时主界面、8074 服务还没启动，属于预期现象。

可以在普通 Chrome 打开 `chrome://inspect`，配置本地 `localhost:9229`，找到 Electron 的 Node 调试目标后点击 inspect，再继续执行；也可以用第 10 节的 VS Code 附加配置。

`--inspect=9229` 则启用调试接口但不在第一行等待，适合应用已经启动后再进入断点。窗口 DevTools 与主进程 inspector 的区别、两个启动参数的行为，见 [Electron 官方调试说明](https://www.electronjs.org/docs/latest/tutorial/debugging-main-process)。

### 7.2 第一组断点放在哪里

打开 `ElectronJS/main.js`，优先按函数或关键词找位置：

| 位置 | 触发方式 | 暂停后看什么 |
| --- | --- | --- |
| `wss.on("connection")` 中的 `ws.on("message")` | 浏览器或流程图发消息 | 原始 message、解析后的 msg、type |
| `beginInvoke(msg, ws)` 的 `msg.type == 3` 分支 | 在扩展中确认采集字段 | from、message.pipe、socket_flowchart |
| `runBrowser()` | 进入设计任务 | driverPath、chromeBinaryPath、扩展目录 |
| `server.js` 的 `/manageTask` 分支 | 保存任务 | 任务对象、分配的编号、落盘路径 |
| `server.js` 的 `/invokeTask` 分支 | 获得任务执行 ID | 模板 ID、输入覆盖、执行实例 EID |

消息入口会频繁收到注册、标题和通知等消息。需要跟踪采集事件时，可以在 `msg` 已解析的那一行之后设置条件断点：

~~~js
msg.type === 3 && msg.from === 0
~~~

`type=3` 到达后先确认内容，再逐步走过：

~~~js
socket_flowchart.send(msg.message.pipe);
~~~

主进程转交的是内层 `pipe` 字符串。下一站应到流程图页面的调试器观察，主进程的调用栈不会直接变成另一个进程里的 `handleAddElement()`。

### 7.3 日志开关与断点不是一回事

`ElectronJS/config.json` 中 `debug: true` 会使 `main.js` 将部分控制台日志同时追加到当前工作目录的 `info.log`。修改后需要重启主程序。

它不会自动打开 inspector，也不会让 VS Code 中所有断点生效。需要断点仍要按本节连接调试器。

当前配置里还有作者机器的 `absolute_user_data_folder`。首次练习使用纯净模式；以后启用用户数据时，应通过界面选择自己的目录并核对配置。

## 8. 调试流程图页面：F12 打开的是哪个窗口

### 8.1 现有项目已经有 F12 入口

让**流程图窗口获得焦点**，按 F12，部分键盘需要 Fn+F12。

源码路径是：

~~~text
src/taskGrid/global.js：document.onkeydown
        ↓ currKey == 123
新建 WebSocket，发送 {type: 6}
        ↓
main.js：msg.type == 6
        ↓
尝试打开 flowchart_window、invoke_window 的 DevTools
~~~

这依赖 WebSocket 已正常工作。它不是对所有系统窗口通用的“按一下必定出现开发者工具”。

首页的 `createWindow()` 中还保留了：

~~~js
// mainWindow.webContents.openDevTools();
~~~

需要观察首页时，可在本地开发副本临时启用后重启；流程图则可在对应窗口创建后调用 `flowchart_window.webContents.openDevTools()`。实验结束后检查并整理这些本地调试改动。

### 8.2 页面里先看这三个面板

| 面板 | 第一轮该做什么 |
| --- | --- |
| Console | 看 JS 报错、WebSocket 连接日志和业务对象 |
| Network | 看 /manageTask 等 HTTP 请求，以及 WebSocket 消息 |
| Sources | 给 logic.js、FlowChart.js 设置断点，检查调用栈与局部变量 |

如果浏览器把 WebSocket 帧显示为 Messages，在 8084 的连接下查看收发消息；不要只在 HTTP 请求列表中寻找它。

先在 `logic.js` 的 `ws.onmessage`、`handleAddElement()` 和 `saveService()` 设置断点。插入与刷新机制再跟到第 18～23 篇。

### 8.3 观察“新增节点”时不要只盯 DOM

收到 `singleCollect` 后，`handleAddElement()` 可能：

- 新增一个 `option=3` 的提取数据节点；
- 如果当前已经选中提取数据节点，向原节点追加字段。

因此断点里要同时看：

~~~text
msg.type
msg.parameters
app._data.nowNode
nodeList
actionSequence
~~~

这些变量分别代表消息输入、当前选择、持久化节点与界面映射。先确认数据变化，再看界面刷新结果。

不要在 Console 里只看一眼展开后的旧日志就认定它代表当时状态；需要保存某一刻的普通 JSON 数据时，可以在暂停位置序列化一份对象快照。包含 DOM 引用的扩展对象则不能直接整体当作 JSON 序列化。

## 9. 调试 Chrome 扩展：内容脚本、后台、popup 分开看

### 9.1 内容脚本在目标网页的 DevTools 里

在**由 EasySpider 启动的设计用 Chrome**里，打开练习网页的 DevTools：

1. 进入 Sources，找到该网页对应的内容脚本区域，通常显示为 Content scripts。
2. 找到 EasySpider 扩展实际加载的 JS。
3. 搜索 `collectSingle`、`singleCollect`、`addEl` 等标志。
4. 在可执行语句上设置断点，再回页面触发选中或采集。

扩展内容脚本有独立的 JavaScript 上下文。Console 需要选择对应扩展、对应 iframe；调试器暂停后，也可以直接从当前作用域查看导入的模块与局部变量。

`global` 是源码导入的对象，不保证能在网页默认 Console 中直接输入 `global.nodeList` 就访问到。暂停在使用它的扩展函数内部，再查看 Scope 更可靠。

后台 service worker 的日志在 `chrome://extensions` 对应扩展的检查入口里；popup 则需要检查 popup 自己。三者的 Console 分开，具体入口见 [Chrome 官方扩展调试教程](https://developer.chrome.com/docs/extensions/get-started/tutorial/debug)。

### 9.2 推荐的第一组观察点

| 源码 | 断点 | 应观察什么 |
| --- | --- | --- |
| `content-scripts/global.js` | `addEl()` | 当前 DOM、XPath、nodeList、readyList |
| `content-scripts/toolkit.vue` | 确认采集对应的处理逻辑 | 预览字段、选择的操作 |
| `content-scripts/messageInteraction.js` | `collectSingle()` | outputParameters、内层 message |
| 同一文件 | `global.ws.send(...)` 前 | 外层 type、from、message.pipe |

单元素采集的结构是：

~~~text
内层：message.type = "singleCollect"
      message.parameters = global.outputParameters
        ↓ JSON.stringify
外层：type = 3
      from = 0
      message.pipe = 上面的 JSON 字符串
~~~

可以在暂停时检查：

~~~js
JSON.parse(message_action.message.pipe)
~~~

前提是停在定义了 `message_action` 的对应函数作用域里。这里第一次解析外层、第二次解析内层，是协议本身的包装方式。

### 9.3 改完源码为什么可能看不到效果

检查下面这张表：

| 改了什么 | 让修改生效的步骤 |
| --- | --- |
| 扩展 `src/` | 重新构建、同步到 ElectronJS 的语言目录，再重建设计会话 |
| `npm run dev` 监听得到的 `dist/` | 确认浏览器加载的是 dist，而不是另一份 EasySpider_zh 目录 |
| Electron `main.js`、`server.js` | 重启 Electron 主进程 |
| 流程图 `logic.js`、HTML、CSS | 保存后重新加载对应页面；先保存未落盘的任务 |
| Python `.py`，当前直接运行源码 | 重新运行 Python 源码调试会话 |
| Python `.py`，当前由界面启动 exe | 重新冻结并替换执行器，再验证；源码断点应改用第 10 节的源码启动 |

`npm run dev` 的定义是 `rollup -c -w`，会监听源码、更新 `dist`；它没有负责持续复制到 `ElectronJS/EasySpider_zh`。本讲第一轮使用 `npm run package`，再关闭旧设计会话、重新进入设计，先把加载关系固定下来。

如果只做一个语言版本的局部实验，也可以按当前语言配置执行 `npm run build`，把完整 `dist` 内容替换到对应语言的生成目录。最终目录应直接包含 `manifest.json`，不能多套一层 `dist/`。

### 9.4 断点应该打在源码，还是构建后的文件

当前 `rollup.config.js` 没有显式启用 `output.sourcemap`，所以不能假定 DevTools 一定显示原来的 `.vue`、`.ts` 并能准确映射行号。

第一轮先在**实际加载的构建 JS**里按函数或字符串定位断点。若要持续调试原始文件，可在本地开发构建中配置 source map，再确认生成的映射确实被浏览器加载。

长期修改应写回 `Extension/manifest_v3/src/`。直接修改生成目录只会暂时改变这一份产物，下次构建还会被覆盖。

## 10. Python 断点与一份可复制的 VS Code 配置

### 10.1 先选虚拟环境解释器

在 VS Code 中安装 Microsoft 的 Python、Python Debugger 扩展，执行 **Python: Select Interpreter**，选择本仓库的：

~~~text
Windows：.venv/Scripts/python.exe
Linux/macOS：.venv/bin/python
~~~

VS Code 当前的 Python 调试配置使用 `"type": "debugpy"`，`program`、`args`、`cwd` 分别控制入口、参数和工作目录，见 [VS Code 官方 Python 调试文档](https://code.visualstudio.com/docs/python/debugging)。

仓库现有 [ExecuteStage/.vscode/launch.json](../../ExecuteStage/.vscode/launch.json) 是旧配置，使用 `"type": "python"`、相对入口和示例编号。只打开 `ExecuteStage` 与打开整个仓库，`workspaceFolder` 含义不同，不能原样混用。

### 10.2 打开仓库根目录时使用这一份

下面配置是**放到仓库根目录 `.vscode/launch.json` 的示例**；本讲不覆盖已有工作区配置。如果已有该文件，把配置项合入原来的数组。

~~~json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Electron：附加主进程 9229",
      "type": "node",
      "request": "attach",
      "address": "127.0.0.1",
      "port": 9229,
      "skipFiles": ["<node_internals>/**"]
    },
    {
      "name": "Python：源码执行（先生成 EID）",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/ExecuteStage/easyspider_executestage.py",
      "cwd": "${workspaceFolder}/ExecuteStage",
      "console": "integratedTerminal",
      "justMyCode": true,
      "args": [
        "--ids", "[${input:easyspiderEid}]",
        "--read_type", "remote",
        "--server_address", "http://localhost:8074",
        "--headless", "0",
        "--user_data", "0",
        "--keyboard", "0"
      ],
      "env": {
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1"
      }
    }
  ],
  "inputs": [
    {
      "id": "easyspiderEid",
      "type": "promptString",
      "description": "输入执行页已生成的执行实例 EID，只填一个数字"
    }
  ]
}
~~~

使用顺序：

1. 需要调主进程时，先按第 7 节用 inspector 启动 Electron，再选择“Electron：附加主进程 9229”，按 F5，继续到主界面。
2. 保持主程序和练习页服务运行，设计、保存任务，并生成 EID。
3. 在 Python 文件里打断点，选择“Python：源码执行”，按 F5，输入刚获得的 EID。

这两项配置不会自动构建扩展，也不会再启动第二份主程序。它们分别接入已经启动的 Electron 和新启动的 Python 源码进程。

`inputs` 在启动时询问 EID，避免学生为了换编号反复编辑 JSON。输入数字即可，不要再输入一层方括号。

如果只把 `ExecuteStage` 作为 VS Code 工作区打开，Python 项应改成：

~~~json
{
  "program": "${workspaceFolder}/easyspider_executestage.py",
  "cwd": "${workspaceFolder}"
}
~~~

这是要替换的两个字段，不是完整启动配置。

### 10.3 Python 第一轮打哪些断点

在 `easyspider_executestage.py` 中按函数名查找：

| 位置 | 观察内容 |
| --- | --- |
| `requests.get(.../queryExecutionInstance...)` 后 | 本次到底读到了哪个 service |
| `self.procedure = service["graph"]` | 任务图与元数据是否符合预期 |
| `BrowserThread.executeNode()` | nodeId、option、sequence、当前循环上下文 |
| `openPage()` | 实际打开的网址 |
| `getData()` | 字段 XPath、定位结果、提取值 |
| `saveData()` | OUTPUT、保存阈值、文件路径 |

注意把第一个断点放在请求结果已经解析之后；把字段观察断点放在变量已赋值之后。

`BrowserThread` 是线程。命中节点执行断点时，可以在调试器的线程与调用栈视图中查看当前执行线程，不必把它误认为另一个不可调试的 exe。

想只停在提取数据节点，可在 `executeNode()` 内设置条件：

~~~python
self.procedure[nodeId]["option"] == 3
~~~

F10 逐过程、F11 进入函数、F5 继续。先只设几个业务断点，避免每次第三方库内部调用都打断阅读。

Python 断点不会命中界面启动的那份已冻结程序。本节的配置明确启动的是 `easyspider_executestage.py`；查看终端启动命令就能确认。

## 11. 端到端练习：跟踪一次“采集房源标题”

这一次不同时暂停所有进程。每到一站看清数据后继续，让消息送到下一站，再切换相应调试器。

### 11.1 设计阶段的四站

在本地练习页选中一个房源标题，确认采集：

| 站点 | 暂停位置 | 记录一项证据 |
| --- | --- | --- |
| ① 扩展 | `collectSingle()` 发消息之前 | parameters 中字段名和 XPath |
| ② Electron | `beginInvoke()` 的 type=3 分支 | from=0；pipe 解析后为 singleCollect |
| ③ 流程图 | `handleAddElement()` | 新建 option=3，或给当前提取节点追加字段 |
| ④ 本地服务 | `/manageTask` 分支 | 保存成哪个 tasks/T.json |

记录应当能解释同一段 XPath 怎样从网页选择传到任务图，而不是只写“断点命中了”。

Node 主进程暂停时，本地服务和消息转发也可能暂停；外部等待还会继续计时。首次练习不要长时间停在启动 Chrome、等待元素等超时敏感位置。

### 11.2 从模板转到执行实例

到执行页面，点“获得任务执行ID”：

~~~text
tasks/T.json
    ↓ /invokeTask：复制任务、应用执行参数、分配/使用 EID
execution_instances/E.json
~~~

修改流程图并保存后，之前的执行实例不会自动变成新模板。需要重新生成或更新执行实例，再调试那个 EID，才能保证观察的是本次改动。

### 11.3 正式执行阶段的三站

用第 10 节的 Python 配置启动：

| 站点 | 暂停位置 | 记录一项证据 |
| --- | --- | --- |
| ⑤ 读取实例 | 解析 service 后 | EID 对应的任务名、graph |
| ⑥ 执行节点 | `executeNode()` → `getData()` | 节点 option、字段 XPath、实际标题 |
| ⑦ 保存结果 | `saveData()` | 输出记录和实际落盘目录 |

第一次只验证标题文字。成功后再加入翻页、循环、条件，分别对照第 15～17 篇阅读。

### 11.4 试运行可以怎么配合源码调试

在流程图里点击某字段的“标记”或“试运行”，可以观察：

~~~text
logic.js：trialElement()
       ↓ type=4
main.js：beginInvoke() 对应分支
       ↓ trial / notify
扩展：messageInteraction.js → trial.js / 通知
~~~

这条链通常由 Electron 主进程执行 Selenium 动作，不会进入 Python 的 `getData()`。如果 Python 断点没有命中，先判断触发的是“试运行一个字段”还是“正式执行任务”。

该链的业务细节集中在 [第 24 篇](24.ElectronJS详解.md)、[第 25 篇](25.调试功能详解.md)。本篇先连接调试器，再配合对应源码逐段跟踪。

## 12. Linux、macOS 怎样对应这套流程

### 12.1 Python 虚拟环境路径不同

从仓库根目录：

~~~bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r ExecuteStage/requirements.txt
.venv/bin/python -m pip check
~~~

执行源码时：

~~~bash
cd ExecuteStage
../.venv/bin/python easyspider_executestage.py --ids '[12]' --read_type remote --server_address http://localhost:8074 --headless 0 --user_data 0 --keyboard 0
~~~

`12` 仍要替换成实际 EID。两套 Node 工程的安装、扩展构建和 `npm run start_direct` 的目录顺序与前面一致。

主进程调试时，在 `ElectronJS` 中：

~~~bash
NODE_ENV=development npx electron --inspect-brk=9229 .
~~~

### 12.2 浏览器与运行环境不同

| 平台 | 开发用浏览器资源 | 额外注意 |
| --- | --- | --- |
| Linux x64 | `ElectronJS/chrome_linux64/` | 可执行权限、桌面显示环境、浏览器沙箱；update 脚本默认版本为 131，须核对 |
| macOS | `ElectronJS/chrome_mac64.app/`、`ElectronJS/chromedriver_mac64` | Intel/Apple 芯片与 Python、Chrome、驱动匹配；平台权限与资源定位 |

Linux 上 `pynput`、图形 Chrome 等可能需要有效的桌面显示环境。即使使用 `--keyboard 0`，源码仍有导入相关模块的过程，不能把它当成解决所有无显示环境问题的开关。

macOS 源码的浏览器查找有独立分支，会检查资源环境变量、执行器所在位置和兄弟 `ElectronJS`。它的默认配置文件夹和 `read_type=local` 实例路径还会涉及 `~/Library/Application Support/EasySpider/`。

本讲跨平台先用 remote 模式明确从当前开发版 8074 读取实例；如果配置或资源定位异常，按启动日志检查候选路径。打包版的 `userData`、App Translocation 和签名见本篇第 24 节。

## 13. 常见故障：先判断失败在哪一层

| 现象 | 优先检查 | 应看到的证据 |
| --- | --- | --- |
| npm 找不到 package.json | 当前目录是否是两个工程之一 | 终端路径、对应 package.json |
| pip 安装了，VS Code 仍报缺模块 | 终端与调试器是否用了同一解释器 | `sys.executable` 指向 .venv |
| 原生 Node 模块加载失败 | 构建工具链、目标架构、Electron 重建 | 安装/重建错误日志 |
| Electron 启动后马上报端口占用 | 旧开发版、发布版是否仍在运行 | 端口对应的进程 |
| 主界面能开，设计 Chrome 起不来 | 浏览器/驱动路径、兼容性、权限 | driverPath、chromeBinaryPath、启动异常 |
| Chrome 出现，但没有操作台 | 扩展目录、BiDi 安装、当前网页是否匹配 | manifest、安装日志、内容脚本错误 |
| 采集操作没传到流程图 | 8084、连接注册、from 与 pipe | 每一站实际收发的消息 |
| Python 找不到浏览器 | cwd 是否为 ExecuteStage；数据目录是否被环境变量覆盖 | 实际 cwd、浏览器路径 |
| Python 读不到任务 | EID 是否存在；误把模板编号当成实例编号 | /queryExecutionInstance 的返回 |
| 代码已改，运行仍是旧结果 | 扩展副本、旧进程、旧实例、旧 exe | 加载路径与实例内容 |
| 调试断点不命中 | 调试进程、加载文件、条件是否正确 | 调试器连接、可执行行与调用栈 |
| 有结果日志，却找不到 CSV | 启动方式与数据目录、保存阈值 | saveData 的路径、OUTPUT 与收尾过程 |

Windows 可先只读查看监听信息：

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8074,8075,8084 |
    Select-Object LocalAddress,LocalPort,OwningProcess
~~~

先根据进程号确认来源，再正常关闭重复运行的程序。不要把所有浏览器或 Python 进程一并结束。

断点命中后常用的检查值：

~~~text
JavaScript：当前消息、实际文件路径、连接对象
Python：sys.executable、os.getcwd()、c.read_type、c.ids、service["graph"]
浏览器：当前 URL、窗口/iframe、实际加载扩展
~~~

## 14. 开发调试验收与源码回读

完成开发与调试部分时，留下以下记录：

- 工具版本与 Python 解释器路径；
- 一次本地练习任务的模板 TID、执行实例 EID；
- 一条采集消息的内层、外层结构；
- 扩展、主进程、流程图、Python 各一次断点观察；
- 最终输出文件的实际路径与一条正确采集结果。

需要回读具体业务原理时，可按问题查找前面的源码讲义：

| 问题 | 源码回读 |
| --- | --- |
| 扩展的内容脚本、后台和 popup 怎样工作 | [03.Chrome 扩展开发](03.Chrome扩展开发MV3.md) |
| Vue 模板怎样变成操作台，消息怎样发送 | [11.Vue 背景](11.Vue3详解.md)、[12.toolkit.vue](12.toolkit.vue详解.md)、[14.消息交互](14.messageInteraction.js详解.md) |
| Python 怎样解释 graph 并控制浏览器 | [15.任务结构](15.Flowchart基本原理.md)、[16.递归执行](16.Flowchart递归执行原理.md)、[17.Selenium](17.Selenium详解.md) |
| 消息怎样插入节点，保存成任务 | [21.消息入图](21.消息到流程图节点.md) 与 [23.保存与加载](23.流程图的保存与加载.md) |
| 软件里的标记、试运行怎样实现 | [24.Electron](24.ElectronJS详解.md)、[25.调试功能](25.调试功能详解.md) |
| 服务端怎样管理文件、启动执行器 | [26.Node 与 Express](26.Node与Express.md) |
| 开发成功后怎样交付给其他电脑 | 继续阅读本篇第 15～30 节 |

开发环境与调试链路验收后，下面转向发布：把已验证的源码、浏览器资源和执行器组装成其他电脑可以使用的软件包。

---

# 第三部分：从开发验收到发布流程

## 15. 用户没有你的开发环境

开发时，三部分代码各有自己的运行方式：

| 部分 | 开发时怎样运行 | 用户侧需要交付什么 |
| --- | --- | --- |
| 浏览器扩展 | Rollup 构建 TypeScript、Vue 和 CSS | Chrome 可以加载的扩展目录；脚本也生成 CRX |
| Electron 主程序 | Node 依赖装好后运行 Electron | Electron 运行时、主程序、页面、依赖与资源 |
| Python 执行器 | 安装 requirements 后运行 `.py` | 当前平台的独立可执行程序及其打包进去的依赖 |
| 浏览器环境 | 开发者机器已经装了 Chrome | 随包携带的 Chrome、匹配的 ChromeDriver、辅助脚本 |

用户不应该先去装 Node、pip 和一长串 Python 库，才能点“本地直接运行”。

所以发布过程的目标是把运行所需的零件**放进约定的位置**：

~~~text
源码
  ├── 扩展构建 → 中英文扩展目录与 CRX
  ├── Python 冻结 → easyspider_executestage(.exe)
  └── 浏览器准备 → Chrome + ChromeDriver + 启动脚本
                         ↓
               放进 ElectronJS 的资源目录
                         ↓
                 Electron Forge 打包
                         ↓
          清理开发数据 + 补齐源码、样例、启动入口
                         ↓
             .temp_to_pub/ 下的平台暂存目录
                         ↓
              7z / tar.xz 最终发布压缩包
                         ↓
              人工创建 GitHub Release 并上传
                         ↓
               用户下载；首页查询最新版本
~~~

这里有四个容易混用的词：

| 词 | 在本项目中的具体含义 |
| --- | --- |
| 构建 | 把扩展源码变成浏览器资源，或把 Python 冻结成可执行文件 |
| 组装 | 把 Electron、浏览器、执行器、源码与样例摆成能运行的目录 |
| 压缩 | 把组装好的平台目录变成 `.7z` 或 `.tar.xz` |
| 发布 | 把压缩包交给用户下载，并说明版本、平台和变化 |

**生成了压缩包，不等于已经上传；用户看到新版本号，也不等于已经自动安装。**

## 16. 发布备忘录给出的主线，以及必须补上的依赖

[`ElectronJS/发布备忘录.md`](../../ElectronJS/发布备忘录.md) 的顺序是：

~~~text
1. 更改版本
2. 更新 Chrome 和 ChromeDriver
3. 生成执行阶段可执行文件
4. 按平台打包
5. Windows 额外清理与组装
6. 在 .temp_to_pub 压缩
~~~

把真实脚本展开后，依赖关系是：

~~~text
change_version.py
        ↓
update_chrome.py
        ↓
generateEXE_* / generateExecutable_*
        ↓
package_*
  ├── 内部先执行 Extension/manifest_v3/package.js
  ├── Electron Forge package / make
  └── Linux、macOS 继续完成平台组装
        ↓
Windows 再执行 clean_and_release_*
        ↓
暂存目录检查、运行验证
        ↓
compress.py
        ↓
人工发布 Release
~~~

为什么更新浏览器必须放在冻结执行器前面？

因为 `update_chrome.py` 会删除旧的 `chrome_win64`、`chrome_linux64` 等目录，再复制本机 Chrome。Windows、Linux 的执行器也保存在这些目录里。**如果先生成执行器，再更新浏览器，刚生成的执行器就可能被一起删掉。**

为什么扩展和执行器都要在 Electron 打包前准备好？

因为 Forge 打包拿的是当时 `ElectronJS/` 中的资源。之后再更新开发目录中的执行器，已经生成的发布目录不会自动跟着更新。

macOS 是一个需要单独记住的分支：执行器先生成在暂存目录，`package_macos.sh` 在 Forge 处理完成后再把它复制进 `.app`，最后统一签名。

---

# 第四部分：版本、浏览器、执行器与扩展构建

## 17. 更新版本：为什么不只改 package.json

### 17.1 同一个版本分散在哪些地方

入口：[`ElectronJS/change_version.py`](../../ElectronJS/change_version.py)。

当前用法要带参数：

~~~powershell
# 从仓库根目录执行；0.6.6 是教学示例
python ElectronJS/change_version.py 0.6.6
~~~

脚本用 `Path(__file__).resolve().parent` 定位自己，因此不依赖你当前在哪个目录。这一点比其他使用相对路径的旧脚本稳妥。

它更新的是 **9 个文件**：

| 文件 | 更新的内容 | 为什么需要 |
| --- | --- | --- |
| `.temp_to_pub/compress.py` | `easyspider_version` | 最终压缩包的文件名 |
| `ElectronJS/src/taskGrid/logic.js` | 匹配 `"version": "` 的版本字段 | 界面状态与保存任务 JSON 时的版本 |
| `ExecuteStage/easyspider_executestage.py` | 命令行默认配置中的版本 | 执行器知道自己的版本 |
| `ElectronJS/src/index.html` | 中英文“当前版本”文字 | 用户看到的本地版本 |
| `ElectronJS/package.json` | 顶层 `version` 与 Forge 的 `appVersion` | Node 包元数据与应用版本 |
| `ElectronJS/package-lock.json` | 顶层及根包版本 | 锁文件元数据 |
| `Extension/manifest_v3/package.json` | 顶层版本 | 扩展工程元数据 |
| `Extension/manifest_v3/package-lock.json` | 顶层及根包版本 | 扩展锁文件元数据 |
| `Extension/manifest_v3/src/manifest.json` | `version` | Chrome 读取的扩展版本 |

不要把 `package-lock.json` 中所有依赖的版本都替换掉。脚本只改项目自身的版本，不会把第三方依赖也改成 EasySpider 的版本。

### 17.2 文本替换和 JSON 更新是两套操作

文本文件用正则替换，核心逻辑如下：

~~~python
pattern = re.escape(prefix) + r"\d+\.\d+\.\d+"
updated, count = re.subn(pattern, prefix + version, text)
if count == 0:
    raise ValueError(...)
~~~

例如匹配：

~~~text
原来："version": "0.6.5"
改成："version": "0.6.6"
~~~

`re.subn` 会返回替换后的文字和替换次数。`logic.js` 中不止一个对应字段，这种写法会把匹配项一起改掉；一个都没找到则报错，避免源码格式改变后悄悄漏改。

JSON 文件则先解析成对象：

~~~python
data["version"] = version
if isinstance(data.get("packages"), dict) and "" in data["packages"]:
    data["packages"][""]["version"] = version
if update_forge_app_version:
    data["config"]["forge"]["packagerConfig"]["appVersion"] = version
~~~

这里 `packages[""]` 是锁文件里“当前根包”的信息，不是某个第三方库。

### 17.3 这一步有哪些边界

- 输入只接受 `数字.数字.数字`，例如 `0.6.6`；`v0.6.6`、`0.6.6-beta.1` 都不符合脚本正则。
- 备忘录中的 `python change_version.py` 已不足以直接运行，当前版本必须提供参数。
- `package.json` 还留着 `"change_version": "node change_version.js"`，但仓库里没有对应 JS 文件；这里应调用 Python 脚本。
- `package_win32.json` 仍保留旧版本和旧依赖，没有被这个脚本更新。
- 已生成的 `EasySpider_zh/`、`EasySpider_en/` 不会直接改；需要重新构建。
- 历史任务 JSON 不会被批量改成新版本；它记录的是任务创建或保存时使用的格式版本。
- 更新按文件依次写入，没有整体回滚。中途失败时，前面的文件可能已改，后面的尚未改，要检查修改结果。

### 17.4 任务版本也参与执行判断

`easyspider_executestage.py` 从任务中读取：

~~~python
self.task_version = service.get("version", "")
~~~

缺少版本时会提示使用旧版；代码随后对 `"0.3.1"` 做比较，并处理旧任务与执行器版本不匹配的情况。

这里用的是**字符串比较**，并非完整的语义版本比较器。讲课时可以让学生手算 `"0.10.0"` 与 `"0.3.1"` 的字符串顺序，观察它和按整数比较版本段的区别。

因此，“统一版本号”的作用不仅是让首页好看，还涉及任务元数据、执行器判断、应用信息和发布包命名的一致性。

## 18. 更新浏览器：复制本机 Chrome，再准备驱动

入口：[`ElectronJS/update_chrome.py`](../../ElectronJS/update_chrome.py)。

### 18.1 名字叫 update，但它没有安装新版 Chrome

脚本主要做四件事：

~~~text
① 调用 npm 工具生成 stealth.min.js
② 判断要匹配的 Chrome 大版本，查找 ChromeDriver 下载地址
③ 下载驱动；把本机已经安装的 Chrome 复制到工程目录
④ 放入驱动、启动脚本和辅助资源，并设置部分执行权限
~~~

主要浏览器来源写在脚本里：

| 平台 | 本机 Chrome 来源 | 工程中准备的资源 |
| --- | --- | --- |
| Windows | `C:\Program Files\Google\Chrome\Application` | `chrome_win64/` 或 `chrome_win32/` |
| Linux | `/opt/google/chrome` | `chrome_linux64/` |
| macOS | `/Applications/Google Chrome.app` | `chrome_mac64.app/`，驱动另放在 ElectronJS 根目录 |

**它下载的是驱动；浏览器主体来自本机安装目录。** 如果希望发布包带更新的 Chrome，需要先保证本机被复制的浏览器就是预期版本。

### 18.2 驱动版本怎样选

`get_chrome_version()` 的行为有平台差异：

| 平台 | 版本来源 |
| --- | --- |
| Windows | 读取当前用户注册表里的 Chrome 版本，提取结果取前三个字符 |
| macOS | 读取本机 Chrome 的 `Versions/Current` 符号链接；失败回退到 `131` |
| Linux | 直接使用默认值 `131` |

所以 Linux 上“复制的 Chrome 是新版，脚本选的驱动仍是 131”是可能出现的；Windows 的注册表来源与实际复制路径也需要核对。

对于大版本 `>= 114`，脚本请求 Chrome for Testing 的版本清单，倒序查找符合大版本前缀且包含 `chromedriver` 下载项的记录，再按目标平台挑下载地址。

旧版本走手工维护的 `old_driver_version` 映射。这里讲的是脚本现有分支条件，不能把它理解为会自动解决任意浏览器版本的匹配问题。

### 18.3 平台和架构怎样选

脚本结合 `sys.platform` 与 `platform.architecture()` 判断分支；macOS 再用处理器信息区分 Intel 和 Apple。

这意味着“在 64 位 Windows 上运行 32 位 Python”与“运行 64 位 Python”可能进入不同分支。构建时应把 Python、Chrome、驱动与 Electron 的目标架构一起核对。

Windows x64 成功准备后，资源大致是：

~~~text
ElectronJS/chrome_win64/
├── chrome.exe
├── Chrome 自身的其他文件与目录
├── chromedriver_win64.exe
├── execute_win64.bat
└── stealth.min.js
~~~

**此时还没有新生成的 Python 执行器。** 下一步才把它放进来。

### 18.4 读源码时要识别出的遗留点

当前脚本有几处不能只按“Done”判断成功的地方：

- 找不到匹配驱动时，没有完整的“未匹配”报错流程，后续可能使用未赋值的 `url`。
- Windows 注册表版本提取使用 `[:3]`，不能当成适用于所有位数大版本的通用解析。
- Windows 32 位分支仍从 `win64_chrome_path` 复制浏览器；备用驱动复制路径还写成了 `chromedriver_win64.exe`。
- Windows 会删除复制来的版本目录中的 `Installer`，没有先判断该目录是否存在。
- macOS 分支没有像 Windows、Linux 那样复制 `stealth.min.js`；打包前需要确认 ElectronJS 根目录中的这份资源已准备好。
- 脚本重建浏览器目录；因此执行器必须在它之后重新生成。

本讲解释这些现状，实际发版时应先解决目标平台相关的问题，再继续后面的组装步骤。

## 19. Python 执行器：把 .py 冻结为独立程序

入口：[`ExecuteStage/`](../../ExecuteStage/Readme.md) 下各平台的生成脚本。

### 19.1 为什么 Electron 还要带一个 Python 程序

Electron 能画界面、管理任务，但正式采集逻辑在 `easyspider_executestage.py`。

用户点“本地直接运行”时，主程序需要启动的是一个可执行文件，而不是假定用户电脑上的 `python` 命令和依赖都齐全。

本项目用 PyInstaller 收集 Python 运行所需的模块、原生库与数据，生成平台对应的程序。`-F` 与 `--onefile` 都表示单文件形式；这个文件仍然是针对操作系统和 CPU 架构构建的产物。

### 19.2 Windows x64：除了 Python 代码，还要带模型和 DLL

源码：[`generateEXE_win64.cmd`](../../ExecuteStage/generateEXE_win64.cmd)。

脚本先删除 `build/`、`dist/`，再从**当前 Python 环境**查出两个资源的位置：

~~~text
onnxruntime/capi/onnxruntime_providers_shared.dll
ddddocr/common_old.onnx
~~~

随后运行：

~~~bat
pyinstaller -F --icon=favicon.ico ^
  --hidden-import selenium.webdriver.ie.webdriver ^
  --add-data "%ONNX_DLL%;onnxruntime\capi" ^
  --add-data "%DDDDOCR_MODEL%;ddddocr" ^
  easyspider_executestage.py
~~~

上面的 `^` 只是为了在讲义中换行，原脚本把命令写在一行。

逐项拆开：

| 参数 | 作用 |
| --- | --- |
| `-F` | 生成单文件执行器 |
| `--icon` | 设置图标 |
| `--hidden-import` | 显式补入指定 Selenium 模块 |
| 第一个 `--add-data` | 把 ONNX Runtime 的共享 DLL 带进去 |
| 第二个 `--add-data` | 把 OCR 模型带进去 |
| 最后的 `.py` | 程序入口 |

为什么模型需要显式指定？因为 `common_old.onnx` 不是一段能靠普通 `import` 直接定位的 Python 源码。源码能运行，并不代表冻结时所有数据资源都会自动齐全。

成功后，脚本检查输出并复制到：

~~~text
ExecuteStage/dist/easyspider_executestage.exe
        ↓
ElectronJS/chrome_win64/easyspider_executestage.exe
~~~

注意：Windows 脚本调用的是 `pyinstaller` 命令，先前查资源调用的是 `python`。应确保这两个命令来自同一个已安装依赖的环境。

### 19.3 Linux：脚本明确检查构建环境

源码：[`generateExecutable_Linux64.sh`](../../ExecuteStage/generateExecutable_Linux64.sh)。

它要求：

~~~text
宿主系统：Linux x86_64
Python：3.11，架构 x86_64
~~~

通过 `PYTHON_BIN` 选择解释器，并用 `"$PYTHON_BIN" -m PyInstaller` 调用打包器。

与 Windows 的重要区别：

- ONNX Runtime 原生库寻找的是 `onnxruntime_pybind11_state*.so`。
- 原生库通过 `--add-binary` 加入，模型通过 `--add-data` 加入。
- 源路径与目标路径之间使用冒号。
- 通过 `install -m 755` 把结果放进 `ElectronJS/chrome_linux64/`。

这个脚本拒绝在非 Linux x86_64 主机上执行，不应把它当作 Windows 上的 Linux 交叉构建入口。

### 19.4 macOS：轻量版与完整版是两次冻结

源码：[`generateExecutable_Macos.sh`](../../ExecuteStage/generateExecutable_Macos.sh)。

它要求本机 macOS，Python 3.11 的架构与 `uname -m` 一致，支持 `arm64` 和 `x86_64`。

脚本连续构建两次：

| 文件 | 构建方式 | 功能区别 |
| --- | --- | --- |
| `easyspider_executestage` | 排除 ddddocr、onnxruntime、pandas、numpy 等模块 | 轻量版，缺少 OCR、Pandas 去重等能力 |
| `easyspider_executestage_full` | 加入 OCR 模型、ONNX 原生库，按完整依赖构建 | 完整版，用于需要这些能力的任务 |

两份结果先放在：

~~~text
.temp_to_pub/EasySpider_MacOS/
├── easyspider_executestage
└── easyspider_executestage_full
~~~

轻量版保留 Pillow，因为执行器本身也导入它。`easyspider_executestage.py` 对 OCR、Pandas 的导入设置了异常处理，缺失时给出使用完整版的提示。

**提示使用完整版，不代表程序会自动切换。** `main.js` 的默认 macOS 执行路径指向不带 `_full` 的文件。

### 19.5 Windows 32 位仍是旧脚本路线

[`generateEXE_win32.cmd`](../../ExecuteStage/generateEXE_win32.cmd) 把依赖资源写成作者机器上的 Python 3.8 32 位绝对路径：

~~~text
C:\Users\Naibo\AppData\Local\Programs\Python\Python38-32\...
~~~

换台机器不能直接照抄运行，需要按实际环境修改。对应依赖清单是 [`requirements_win32.txt`](../../ExecuteStage/requirements_win32.txt)，不能默认与目前的 [`requirements.txt`](../../ExecuteStage/requirements.txt) 共用同一套环境。

`ExecuteStage/Readme.md` 的通用“Python 3.7 及以上”说明，也不能覆盖当前 Linux、macOS 脚本对 Python 3.11 的明确检查。

## 20. 扩展打包：同一份源码怎样生成中英文两份产物

入口：[`Extension/manifest_v3/package.js`](../../Extension/manifest_v3/package.js)。

### 20.1 先认清三个命令

`Extension/manifest_v3/package.json` 中：

~~~json
{
  "scripts": {
    "build": "rollup -c",
    "dev": "rollup -c -w",
    "crx": "crx3",
    "package": "node package.js"
  }
}
~~~

| 命令 | 做什么 |
| --- | --- |
| `npm run dev` | 监听源码变化并重新构建，服务于开发 |
| `npm run build` | 根据当前配置构建一次到 `dist/` |
| `npm run package` | 执行中英文两轮构建、生成 CRX，并复制到 ElectronJS |

所以只执行一次 `npm run build`，并不等于完成中英文发布资源的更新。

### 20.2 Rollup 把什么变成什么

[`rollup.config.js`](../../Extension/manifest_v3/rollup.config.js) 以 `src/manifest.json` 为入口，输出到 `dist/`。

构建管线涉及：

~~~text
manifest.json 描述扩展入口
         ↓
Chrome 扩展构建插件解析各脚本与资源
         ↓
Vue / TypeScript / CSS / JSON / 模块依赖处理
         ↓
dist/manifest.json、可运行 JS、CSS 与静态资源
~~~

源码还通过环境变量配置 manifest 的 `key` 和部分前端配置。它们属于构建输入；发布构建要保持所需配置一致。这里不需要把开发者的环境文件当作用户运行配置一起分发。

### 20.3 package.js 实际顺序

~~~text
读取 src/content-scripts/config.json
        ↓
language = "en"
        ↓
npm run build → dist/ 改名为 EasySpider_en/
        ↓
npm run crx EasySpider_en
        ↓
复制英文 CRX 和目录到 ElectronJS/
        ↓
language = "zh"
        ↓
重复一遍，生成并复制中文版
~~~

最终 ElectronJS 中同时有：

~~~text
ElectronJS/
├── EasySpider_en/
├── EasySpider_en.crx
├── EasySpider_zh/
└── EasySpider_zh.crx
~~~

脚本会替换目标目录，结束后源码配置中的语言停在 `zh`。因此构建前后应检查工作区，不能假定打包完全不修改源码目录。

另一个细节是：`execSync` 失败会抛异常，而 `copyFolderSync` 对复制异常只打印错误。发布验证还需要确认目标目录确实更新了。

### 20.4 当前主程序加载的是目录

`ElectronJS/README.md` 中还有“缺少 CRX 会报错”的旧说明，但当前 `main.js` 的 `options.addExtensions(...)` 已被注释。

实际设计任务路径使用 BiDi WebExtension API：

~~~js
// main.js 摘录；easySpiderPath 由语言决定
const easySpiderId = await webExtension.install(
    ExtensionData.setPath(easySpiderPath)
);
~~~

`easySpiderPath` 指向 `EasySpider_zh` 或 `EasySpider_en` 目录。随后还安装 `XPathHelper_MV3` 目录。

所以当前打包检查至少要确认：

~~~text
EasySpider_zh/manifest.json
EasySpider_en/manifest.json
XPathHelper_MV3/manifest.json
~~~

**只更新 CRX、漏掉目录，当前主程序仍可能装入旧扩展，甚至安装失败。**

---

# 第五部分：Electron 与各平台发布目录组装

## 21. Electron Forge：package 和 make 分别在哪一层

入口：[`ElectronJS/package.json`](../../ElectronJS/package.json)。

~~~json
{
  "scripts": {
    "start_direct": "cross-env NODE_ENV=development electron .",
    "package": "electron-forge package",
    "make": "electron-forge make"
  }
}
~~~

放回本项目的流程中理解：

| 命令 | 当前发布脚本怎样使用 |
| --- | --- |
| `start_direct` | 开发运行，不生成最终用户包 |
| `package` | Windows、Linux 用它生成平台应用目录 |
| `make` | macOS 用它生成 ZIP，再解压到发布暂存目录 |

仓库的内联 Forge 配置声明了 Squirrel、ZIP、DEB、RPM 等 makers，另有一份 [`forge.config.js`](../../ElectronJS/forge.config.js)。阅读配置时要留意这两处，并核对实际构建加载的配置和输出。

不能仅凭“声明了 maker”就认定发布流程一定交付对应安装包。本项目的 Windows 最终交付仍走外层目录加 `.7z`，Linux 走 `.tar.xz`，macOS 会把 Forge ZIP 解压后再组装成最终 `.7z`。

`publishers` 为空；这条发布链里也没有自动上传 GitHub 的命令。

### 21.1 为什么资源目录特别重要

当前应用资源布局按以下路径使用：

~~~text
Windows / Linux：
  EasySpider/resources/app/

macOS：
  EasySpider.app/Contents/Resources/app/
~~~

这里存主程序、页面、扩展、浏览器资源等。阅读 `main.js` 时，`__dirname` 通常就是这些主程序文件所在的位置。

本章的组装脚本直接访问 `resources/app`，不能随意改成别的资源布局而不改脚本和运行时路径。

### 21.2 原生 Node 模块为什么也会影响构建

Electron 工程依赖 `node-window-manager` 等模块。`ElectronJS/README.md` 说明 Windows 安装依赖时可能涉及 C++ 构建工具；遇到对应的原生模块问题时，还给出 `electron-rebuild` 的处理方式。

这和 Python 的 DLL、`.so` 是同一类交付问题：**除了 JS/Python 源码，还可能有与平台、架构或运行时匹配的原生代码。**

不要在安装依赖失败的状态下继续打包，也不要把某个平台的 `node_modules` 当成所有平台都能直接复用的产物。

## 22. Windows x64：为什么打包后还要 clean_and_release

### 22.1 package_win64.cmd 只完成前半段

源码：[`package_win64.cmd`](../../ElectronJS/package_win64.cmd)。

有效主线是：

~~~text
切到 Extension/manifest_v3
    node package.js
切回 ElectronJS
    删除 out
    npm run package
~~~

成功后，清理脚本预期看到：

~~~text
ElectronJS/out/EasySpider-win32-x64/
~~~

名字里的 `win32` 是平台名，`x64` 才是架构，并不表示这是 32 位软件。

Windows 批处理大量使用相对路径，应该从脚本预期目录运行。它不像 Linux、macOS 脚本那样先统一解析自己的绝对路径。

另外，当前 Windows package 脚本没有显式传 `--arch`；不能因为文件名叫 `package_win64.cmd`，就认定它会替你强制设置架构。

### 22.2 clean_and_release_win64.cmd 分成四组工作

源码：[`clean_and_release_win64.cmd`](../../ElectronJS/clean_and_release_win64.cmd)。

**第一组：整理 Electron 应用目录。**

~~~text
out/EasySpider-win32-x64
        ↓ 改名
out/EasySpider
        ↓ 清理
移到 .temp_to_pub/EasySpider_windows_x64/EasySpider
~~~

清理应用内部的其他架构浏览器、驱动下载临时目录、开发数据、任务、执行实例、用户浏览器目录、IDE 文件及构建工具安装包等。

这里删掉的是应用资源里的开发副本。正式要分发的样例任务稍后单独放在外层。

**第二组：附带 Python 源码。**

脚本重建外层 `Code/`，复制：

~~~text
ExecuteStage/*.py
requirements.txt
Readme.md
undetected_chromedriver_ES/
.vscode/
~~~

`myCode.py` 还会额外复制到发布包根目录。它和 `Code/` 是源码与扩展入口，不能替代冻结后的执行器。

**第三组：清空运行数据。**

清除或重建：

~~~text
user_data/
TempUserDataFolder/
Data/
execution_instances/
~~~

这些目录里可能有开发时的浏览器状态、测试输出和执行记录，不应作为默认运行状态交付给用户。

**第四组：重新放入受版本控制的样例任务。**

x64 脚本先重建外层 `tasks/`，再执行 `git ls-files -- ElectronJS/tasks`，仅复制 Git 跟踪的任务文件，并保留子目录。

这比直接复制本机整个 `tasks/` 更可控：临时新建、未纳入版本控制的任务不会自然混进去。

但反过来，**已被 Git 跟踪的文件也要由维护者确认可以发布**。Git 跟踪状态只是脚本的筛选标准。

这一步还说明发布环境需要可用的 Git 仓库信息；只有源码文件、没有 Git 跟踪记录时，不能假定会得到同样的样例集合。

### 22.3 最终 Windows x64 目录应该怎样读

以下是组装完成后的关键结构，省略浏览器与 Electron 的大量内部文件：

~~~text
.temp_to_pub/EasySpider_windows_x64/
├── EasySpider.exe                 外层已有启动入口
├── EasySpider.bat                 start EasySpider/EasySpider.exe
├── EasySpider/
│   ├── EasySpider.exe             实际 Electron 程序
│   └── resources/app/
│       ├── main.js
│       ├── server.js
│       ├── src/
│       ├── EasySpider_zh/
│       ├── EasySpider_en/
│       ├── XPathHelper_MV3/
│       └── chrome_win64/
│           ├── chrome.exe
│           ├── chromedriver_win64.exe
│           ├── execute_win64.bat
│           ├── stealth.min.js
│           └── easyspider_executestage.exe
├── Code/                          执行阶段源码
├── myCode.py
├── tasks/                         样例任务
├── execution_instances/           空的执行实例目录
├── Data/                          空的输出目录
└── LICENSE、说明文件等
~~~

外层启动器、说明和许可证等模板文件已经存在于 `.temp_to_pub` 的平台目录中。**clean 脚本并不是从零生成整个发布包。** 从空目录重建发布环境时，需要把这些模板一起准备好。

### 22.4 Windows x32 不能只把 x64 改个名字

对应脚本预期产物是 `EasySpider-win32-ia32`，暂存目录是 `EasySpider_windows_x32`。

但当前路线存在差异：

- `package_win32.cmd` 没有自动切换到 `package_win32.json`，也没有显式设置 `ia32`。
- `package_win32.json` 仍是旧版本元数据，不能直接视为同步维护的当前配置。
- 执行器依赖绝对路径，需要单独准备 32 位环境。
- `clean_and_release_win32.cmd` 复制全部 `tasks/*`，没有采用 x64 的 Git 跟踪筛选。
- 它在清理时删除 ElectronJS 根目录中的两份 CRX。
- `execute_win32.bat` 的开发分支还引用 `chrome_win64`。

这些都是从“脚本叫什么”看不出的差异。32 位发布需要逐项核对，不能把 x64 命令列表原样换后缀就当作已验证流程。

## 23. Linux：把打包和清理合在一个脚本里

源码：[`package_linux64.sh`](../../ElectronJS/package_linux64.sh)。

### 23.1 开始就做平台与资源检查

脚本要求原生 Linux x86_64，检查浏览器目录中有：

~~~text
chrome
chromedriver_linux64
chrome_crashpad_handler
chrome_sandbox 或 chrome-sandbox
~~~

然后复制 `execute_linux64.sh`，修正执行权限，构建扩展，再运行：

~~~bash
npm run package -- --platform=linux --arch=x64
~~~

产物预期为 `out/EasySpider-linux-x64`，之后自动清理并移入：

~~~text
.temp_to_pub/EasySpider_Linux_x64/EasySpider/
~~~

它还负责复制 `Code/`、样例任务、清理配置和缓存，所以**Linux 不需要再运行 Windows 的 clean 脚本**。

前置检查主要覆盖浏览器文件，并没有把“冻结后的执行器必须存在”纳入同样的强制检查；发布前仍需确认 `chrome_linux64/easyspider_executestage` 已生成。

### 23.2 为什么必须保留 easy-spider.sh

发布模板中的 [`easy-spider.sh`](../../.temp_to_pub/EasySpider_Linux_x64/easy-spider.sh) 会：

1. 根据脚本自身的位置定位 Electron 与 Chrome。
2. 给浏览器、驱动、执行器和启动脚本补执行权限。
3. 分别检查 Electron 自带沙箱和附带 Chrome 的沙箱。
4. 必要时通过 `sudo` 设置沙箱的属主和 `4755` 权限。
5. 启动实际的 Electron 程序。

打包阶段的 `chmod 755` 与首次运行时的沙箱权限设置是两件事，不能互相替代。脚本同时处理两套沙箱，是因为 Electron 的界面浏览器和采集使用的 Chrome 是不同的组件。

执行器的启动包装脚本也很简洁：

~~~bash
# execute_linux64.sh 核心行
exec "$SCRIPT_DIR/easyspider_executestage" "$@"
~~~

它根据包装脚本的位置找执行器，并把参数原样传下去。**执行器的位置**与**运行数据的工作目录**不必是同一个目录。

## 24. macOS：两种芯片、两份执行器、最后签名

源码：[`package_macos.sh`](../../ElectronJS/package_macos.sh)。

### 24.1 先确定架构，再处理 Forge ZIP

~~~text
uname -m
  ├── arm64  → Electron --arch=arm64
  └── x86_64 → Electron --arch=x64
~~~

脚本先构建扩展，再运行 `npm run make -- --platform=darwin --arch=...`，从 `out/make/zip/darwin/<架构>/` 找到 ZIP，解压到暂存目录。

接着清理 `EasySpider.app/Contents/Resources/app` 中的其他平台资源与开发数据，复制源码，把受 Git 跟踪的样例放进外层 `Sample Tasks/`。

注意这里的样例目录叫 `Sample Tasks`，不是 Windows、Linux 的 `tasks`。它不等同于 macOS 实际保存用户任务的位置。

### 24.2 为什么执行器同时在 app 里面和外面

最终关键结构：

~~~text
EasySpider_MacOS/
├── EasySpider.app/
│   └── Contents/Resources/app/
│       ├── chrome_mac64.app/
│       ├── chromedriver_mac64
│       ├── easyspider_executestage
│       └── easyspider_executestage_full
├── easyspider_executestage
├── easyspider_executestage_full
├── execute_macos.sh
├── first_time_run.sh
├── Sample Tasks/
└── Code/、myCode.py、说明文件等
~~~

原因在 `main.js` 与组装脚本的注释中写得很明确：macOS 的 App Translocation 可能让应用运行在临时的迁移路径下。此时按照 `.app` 的位置去找“外面的兄弟文件”，路径不一定还成立。

所以主程序启动的是应用包内部的执行器；外层副本保留给便携目录和手工命令行使用。

### 24.3 资源与用户数据必须分开

`server.js` 的关键判断：

~~~js
if (app.isPackaged && process.platform === "darwin")
    return app.getPath("userData");
if (app.isPackaged)
    return path.resolve(process.resourcesPath, "../..");
return __dirname;
~~~

对应关系是：

| 运行方式 | 任务与运行数据目录 |
| --- | --- |
| 开发模式 | `ElectronJS/` |
| Windows、Linux 打包版 | 外层便携发布目录 |
| macOS 打包版 | Electron 的 `userData` |

`main.js` 启动执行器时还传入 `EASYSPIDER_DATA_DIR` 与 `EASYSPIDER_APP_RESOURCES`，并设置工作目录。

因此 macOS 的执行器可以从应用包内取浏览器资源，同时把任务数据写进稳定的用户目录。排查“我保存的任务去哪了”，不能只在 `.app` 内寻找。

### 24.4 为什么签名一定放在最后

脚本在所有复制、删除结束后才签名：

~~~text
外层轻量执行器
外层完整执行器
app 内轻量执行器
app 内完整执行器
EasySpider.app
        ↓
codesign --verify --deep --strict
~~~

`CODESIGN_IDENTITY` 默认是 `-`，即 ad hoc 签名；设置了身份时，脚本会使用该身份，并带上 runtime 和 timestamp 选项。

默认 ad hoc 签名不能被讲成已经完成 Developer ID 分发流程。当前脚本也没有公证、staple 等后续步骤；只能按它实际执行的签名与验证来描述。

如果签名后又替换包内执行器或扩展，就要重新完成签名验证。

模板中的 `first_time_run.sh` 使用 `xattr -cr` 清除 app 与外层执行器的扩展属性。它属于另一种首次运行辅助操作，不能等同于前面的签名、公证流程。

---

# 第六部分：压缩、验证、发布与检查更新

## 25. compress.py：按当前平台选择最终文件名

入口：[`.temp_to_pub/compress.py`](../../.temp_to_pub/compress.py)。

必须在 `.temp_to_pub` 中执行，因为其中大量路径以 `./EasySpider_...` 为起点。

### 25.1 最终压缩格式

假设版本为 `0.6.6`：

| 当前运行平台 | 暂存目录 | 输出文件 |
| --- | --- | --- |
| Windows，64 位 Python | `EasySpider_windows_x64` | `EasySpider_0.6.6_Windows_x64.7z` |
| Windows，32 位 Python | `EasySpider_windows_x32` | `EasySpider_0.6.6_Windows_x32.7z` |
| Linux，64 位 Python | `EasySpider_Linux_x64` | `EasySpider_0.6.6_Linux_x64.tar.xz` |
| macOS，Intel | `EasySpider_MacOS` | `EasySpider_0.6.6_MacOS_Intel_Chip.7z` |
| macOS，Apple | `EasySpider_MacOS` | `EasySpider_0.6.6_MacOS_Apple_Arm_Chip.7z` |

**选择依据是运行 compress.py 的环境，不是自动检查包内每个二进制。** 用错构建环境，文件名仍可能看起来正常。

Windows 分支源码使用 `EasySpider_Windows_x64` 这样的大小写，模板目录是 `EasySpider_windows_x64`；常见 Windows 文件系统下通常能对应，涉及大小写敏感环境时要额外核对。

### 25.2 它还会再次清运行数据

Windows、Linux 分支删除用户浏览器数据、输出、执行实例、配置文件等，再重建空的 `Data` 和 `execution_instances`。

macOS 分支对临时浏览器目录做清理，Apple 分支还清空 `Data`；清理范围并不完全等同于 Windows、Linux。macOS 组装脚本已经做过的清理也不能省略。

这意味着：**可以先运行暂存包验证，但最终压缩会清掉它的部分运行数据。** 解压最终压缩包后还应再做一次独立验证，确认真正交付的内容可用。

### 25.3 压缩命令与成功判断

普通 7z 路线核心是：

~~~python
subprocess.call(["7z", "a", "-mx=9", output_file, folder_path])
~~~

找不到命令等异常时退到 `7za`。源码另有 `compress_folder_to_7z_split()`，使用 `-v95m` 分卷，并额外尝试 `7zz`，但当前主流程里的分卷调用被注释了。

Linux 用：

~~~python
subprocess.call(["tar", "-Jcvf", file_name, "./EasySpider_Linux_x64"])
~~~

这里有一个很适合课堂讨论的细节：

~~~text
subprocess.call 返回非零退出码
        ≠
Python 一定抛异常
~~~

当前脚本没有检查这些返回码，后面仍可能打印 `successfully`；只有发生异常才会走备用命令。因此应核对实际产物、压缩工具退出状态与解压结果，不能只看最后一句输出。

普通压缩函数会先移除同名输出文件，所以重新压缩也会替换以前的同名包。

## 26. 发布验证：分清“依赖可用”和“最终包可用”

### 26.1 仓库已有两个有用的自检入口

**第一层：Python 构建环境。**

[`scripts/smoke_python_dependencies.py`](../../scripts/smoke_python_dependencies.py) 测试图片处理、OCR 推理、HTML/XML、Excel、Pandas、Selenium 配置、键盘表示与 MySQL 字符串转义。

从仓库根目录运行：

~~~powershell
python scripts/smoke_python_dependencies.py
~~~

它验证的是**当前解释器的依赖环境**，并不代表 PyInstaller 已把模型和原生库正确带进最终执行器。它还包含 OCR、Pandas 检查，不适合拿来要求 macOS 轻量执行器具备全部功能。

**第二层：Windows x64 暂存包的浏览器与驱动。**

[`scripts/test_bundled_chrome.py`](../../scripts/test_bundled_chrome.py) 明确定位暂存包中的 Chrome 和 ChromeDriver，启动无头浏览器，读取页面标题与 h1，再退出。

~~~powershell
python scripts/test_bundled_chrome.py --stage .temp_to_pub/EasySpider_windows_x64
~~~

默认访问示例网站，断言标题和 h1 都是 `Example Domain`。虽然提供 `--url`，断言仍是固定值，不能把 URL 换成任意网站就期待通过。

它只覆盖 Windows x64 的浏览器路径，不覆盖主界面、扩展和正式执行器的完整业务。

### 26.2 最终交付还要从用户入口走一遍

建议在新解压目录里验证以下几条链：

| 验证链 | 观察什么 |
| --- | --- |
| 启动入口 → 主界面 | 入口、Electron 和本地服务路径正确 |
| 选择语言 → 设计任务 → Chrome | 中英文扩展目录可安装，操作台能出现 |
| 选择网页元素 → 流程图 → 保存 | 扩展、WebSocket、编辑器与任务存取连通 |
| 保存任务 → 本地执行 → 输出文件 | 冻结执行器、驱动、任务目录和输出目录连通 |
| OCR、Excel、去重等相关任务 | 需要的模型、原生库和数据依赖实际随包可用 |
| 关闭重开 → 读取任务 | 数据写在预期位置并能持久保存 |

macOS 的轻量版与完整版要按各自能力验证。Linux 要从外层启动脚本验证权限与沙箱。还应测试包含空格、中文的路径，避免开发时固定工作目录掩盖路径问题。

这里最有价值的检查是：**最终压缩包解压后，软件能否在目标环境中依靠包内资源完成一个真实任务。**

## 27. 一次 Windows x64 发版的操作顺序

下面整理的是现有脚本的调用顺序；其中更新浏览器和清理脚本会删除、重建相关目录，执行前应备份开发数据，并确认当前工作目录与目标平台。

### 27.1 先准备两个 Node 工程与 Python 环境

环境安装细节见 [本篇第 3 节](#3-安装三套工程的依赖)。下面列出发版时的目录顺序；如使用虚拟环境，应确保后续 Python、pip 和 PyInstaller 都来自同一个目标环境。

从仓库根目录起：

~~~powershell
cd Extension/manifest_v3
npm install

cd ../../ElectronJS
npm install

cd ../ExecuteStage
python -m pip install -r requirements.txt
~~~

Windows 还应按工程说明准备原生模块所需的构建工具。先确认依赖安装成功，不能在安装失败后继续下面的流程。

### 27.2 改版本、准备浏览器、生成执行器

~~~powershell
# 当前在 ExecuteStage，先回根目录
cd ..
python ElectronJS/change_version.py 0.6.6
python scripts/smoke_python_dependencies.py

cd ElectronJS
python update_chrome.py

cd ../ExecuteStage
.\generateEXE_win64.cmd
~~~

这一步后应检查 `ElectronJS/chrome_win64` 中的 Chrome、驱动、启动脚本、stealth 和新生成的执行器。

### 27.3 构建扩展、打包并组装

~~~powershell
cd ../ElectronJS
.\package_win64.cmd
.\clean_and_release_win64.cmd

cd ..
python scripts/test_bundled_chrome.py --stage .temp_to_pub/EasySpider_windows_x64
~~~

`package_win64.cmd` 已经调用扩展的 `package.js`，不必为完成同一轮流程再单独构建一次扩展。每个阶段成功后再进入下一阶段，旧版批处理并非每一步都具备完整的失败中止逻辑。

完成界面、任务设计和正式执行验证后：

~~~powershell
cd .temp_to_pub
python compress.py
~~~

最后把压缩包解到新目录，再从用户入口验证。

### 27.4 Linux、macOS 的对应入口

以下都是在**对应的原生构建主机**上、准备好各工程依赖后的调用顺序，不是让 Windows 同时构建所有平台：

~~~bash
# 仓库根目录
python3 ElectronJS/change_version.py 0.6.6

cd ElectronJS
python3 update_chrome.py

cd ../ExecuteStage
# Linux 二选一
bash generateExecutable_Linux64.sh
# macOS 对应：
# bash generateExecutable_Macos.sh

cd ../ElectronJS
# Linux
bash package_linux64.sh
# macOS 对应：
# bash package_macos.sh

cd ../.temp_to_pub
python3 compress.py
~~~

Linux 要先核对 `update_chrome.py` 的默认大版本与实际复制的浏览器；macOS 要核对本机芯片、Python、浏览器、驱动和 Electron 的架构。

Linux、macOS 生成脚本默认使用 `python3`，也支持通过 `PYTHON_BIN` 指定已准备好的 Python 3.11 解释器。macOS 如需指定签名身份，应在运行组装脚本前配置 `CODESIGN_IDENTITY`。

## 28. 上传 Release 与用户检查更新是怎样接上的

### 28.1 仓库脚本到哪里结束

目前这条脚本链没有创建 Git tag、创建 GitHub Release 或上传 assets 的步骤；`.github/` 中也没有对应的发布工作流。

因此，人工发布的交接信息应包括：

~~~text
版本：0.6.6
Tag：v0.6.6
对应源码：本次通过验证的提交
附件：已验证的各平台压缩包
说明：功能变化、修复、平台/架构、已知限制与使用提示
~~~

在 GitHub 上创建相应版本的 Release，上传对应附件并发布，是压缩之后的维护者操作。本讲不把它写成已存在的自动脚本。

应用查询的仓库位置由源码固定为 `NaiboWang/EasySpider`。如果分发的是自己的分支，需要检查更新入口是否仍指向原仓库。

### 28.2 check_update.js：命令行检查版本

源码：[`ElectronJS/check_update.js`](../../ElectronJS/check_update.js)。

它读取本地 `package.json` 的 `version`，请求 GitHub 的 `releases/latest`，取：

~~~js
const latestVersion = release.tag_name.replace('v', '');
if (version !== latestVersion) {
    console.log('There is a new version of EasySpider, ...');
}
~~~

重点有三条：

1. 比较的是字符串是否相等，没有判断哪个版本更大。
2. 它只打印下载提示，没有下载、替换程序或自动重启。
3. 它假定 API 返回的 JSON 包含 `tag_name`，没有完整处理 HTTP 错误状态和缺失字段。

手动运行入口是：

~~~powershell
# 在 ElectronJS 中
node check_update.js
~~~

当前 `main.js` 没有把它作为应用自动更新模块调用。

### 28.3 首页还有另一套“最新版本”展示

源码：[`ElectronJS/src/index.js`](../../ElectronJS/src/index.js) 与 [`index.html`](../../ElectronJS/src/index.html)。

首页挂载时用 `XMLHttpRequest` 请求同一个 GitHub `releases/latest` 接口，然后：

~~~js
const release = JSON.parse(request.responseText);
const latestVersion = release.tag_name;
app.$data.newest_version = latestVersion;
~~~

首页的两个值来源不同：

~~~text
“软件当前版本” → index.html 中写死，change_version.py 更新
“官网最新版本” → GitHub Release API 返回的 tag_name
~~~

因此：

- 只改本地版本但没有发布 Release，“最新版本”仍来自已有线上 Release。
- 发布了 Release，用户本地“当前版本”也不会自动变化。
- API 请求失败时不能据此推断用户已经是最新版本。
- 首页主要展示最新标签和下载链接，没有完成自动更新安装。

到这里，整个环才闭合：

~~~text
维护者改版本 → 构建 → 组装 → 验证 → 压缩 → 发布 Release
                                                   ↓
                                      首页 / 检查脚本读取 tag_name
                                                   ↓
                                           用户自行下载新版
~~~

## 29. 常见问题：从症状反查哪一层没交付好

| 症状 | 优先检查 |
| --- | --- |
| 首页版本、任务版本与压缩包名对不上 | 是否使用带参数的 Python 版本脚本，是否在改版本后重新构建 |
| 主界面能开，点设计任务失败 | Chrome/驱动匹配、架构、扩展目录和 XPathHelper_MV3 是否齐全 |
| CRX 是新的，操作台却还是旧的 | 当前主程序加载的是目录，检查 EasySpider_zh/en 的构建结果 |
| 设计正常，本地执行找不到程序 | 是否先生成执行器；之后更新浏览器是否又把它删掉 |
| 源码 OCR 正常，冻结程序失败 | OCR 模型与 ONNX 原生库是否打入，实际运行的是哪份执行器 |
| Linux 报权限或沙箱问题 | 是否使用外层启动脚本，执行位与两套沙箱是否就绪 |
| macOS 找不到外层执行器或任务 | app 内执行器、资源环境变量、userData 与 App Translocation 路径 |
| Windows clean 找不到 out 目录 | Forge 是否成功，实际产物架构与 clean 预期目录是否一致 |
| 发布包带了自己的测试任务或状态 | 样例筛选、用户数据清理范围、已跟踪任务内容与最终解压结果 |
| 压缩脚本打印成功，却没有可用附件 | 压缩工具是否存在、返回码、输出文件与解压完整性 |
| 本地比线上新，检查脚本仍说有新版 | 脚本只做不相等判断，没有版本大小比较 |
| 新包中仍是旧的执行逻辑 | 是否只修改 .py 而忘了重新冻结，或冻结后没有重新组装 |

这些问题的共同排查方法是：**沿着“源码 → 中间产物 → 暂存目录 → 压缩包 → 实际运行路径”逐层看文件。** 不要只确认源码里已经修改。

## 30. 课堂练习与源码阅读索引

### 30.1 动手练习

**练习一：画出一个版本号的传播路径。**

以 `0.6.5 → 0.6.6` 为例，列出版本脚本更新的 9 个文件。分别指出哪个影响任务 JSON、哪个影响应用元数据、哪个影响压缩包名。先阅读和手算，不必在工作目录实际改版。

**练习二：判断两个错误顺序。**

~~~text
A：生成执行器 → 更新浏览器 → 打包 Electron
B：打包 Electron → 重新生成执行器 → 直接压缩旧暂存目录
~~~

A 会在哪一步丢文件？B 为什么会把新源码和旧二进制一起交付？

**练习三：跟踪一个用户操作的文件路径。**

在 Windows x64 暂存包里，从 `EasySpider.bat` 开始，依次找到 Electron 主程序、Chrome、驱动、扩展目录、执行器和输出目录。再解释 macOS 为什么不能完全照搬这张路径图。

**练习四：只提出修改方案。**

任选一项，说明要改哪些位置、怎样验证：

- 把 `check_update.js` 的不相等判断改成版本段的整数比较。
- 让压缩失败时不再打印成功。
- 让 Linux 打包在缺少冻结执行器时立即中止。
- 把 Windows 32 位脚本里的作者绝对路径改为当前环境查找。
- 让各平台都采用一致的样例筛选与发布前检查规则。

### 30.2 源码索引

| 阅读目标 | 源码 |
| --- | --- |
| 发布顺序提示 | [发布备忘录](../../ElectronJS/发布备忘录.md) |
| 统一版本号 | [change_version.py](../../ElectronJS/change_version.py) |
| Chrome 与驱动准备 | [update_chrome.py](../../ElectronJS/update_chrome.py) |
| 扩展双语言构建 | [package.js](../../Extension/manifest_v3/package.js)、[rollup.config.js](../../Extension/manifest_v3/rollup.config.js) |
| Python Windows 构建 | [win64](../../ExecuteStage/generateEXE_win64.cmd)、[win32](../../ExecuteStage/generateEXE_win32.cmd) |
| Python Linux/macOS 构建 | [Linux64](../../ExecuteStage/generateExecutable_Linux64.sh)、[macOS](../../ExecuteStage/generateExecutable_Macos.sh) |
| Python 依赖体积辅助分析 | [package_size.py](../../ExecuteStage/package_size.py)：估算安装环境中包目录的大小，不是最终发布包大小 |
| Electron 配置 | [package.json](../../ElectronJS/package.json)、[forge.config.js](../../ElectronJS/forge.config.js) |
| Windows 构建与组装 | [package_win64.cmd](../../ElectronJS/package_win64.cmd)、[clean_and_release_win64.cmd](../../ElectronJS/clean_and_release_win64.cmd) |
| Windows x32 构建与组装 | [package_win32.cmd](../../ElectronJS/package_win32.cmd)、[clean_and_release_win32.cmd](../../ElectronJS/clean_and_release_win32.cmd) |
| Linux/macOS 组装 | [package_linux64.sh](../../ElectronJS/package_linux64.sh)、[package_macos.sh](../../ElectronJS/package_macos.sh) |
| 最终压缩 | [compress.py](../../.temp_to_pub/compress.py) |
| 运行路径与数据位置 | [main.js](../../ElectronJS/main.js)、[server.js](../../ElectronJS/server.js)、[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) |
| 两种版本检查入口 | [check_update.js](../../ElectronJS/check_update.js)、[src/index.js](../../ElectronJS/src/index.js) |

---

返回目录：[README.md](README.md) ｜ 上一篇：[26.Node.js 与 Express](26.Node与Express.md)
