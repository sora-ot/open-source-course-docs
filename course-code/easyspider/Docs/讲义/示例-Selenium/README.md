# Selenium 基础操作：本地页面与 Python 样例

配合[第 17 篇 Selenium 讲义](../17.Selenium详解.md)。页面使用固定的海淀、朝阳五条房源，不需要真实网站账号。搜索与翻页延迟 200 毫秒更新，供等待和元素失效练习。

## 1. 启动

从仓库根目录进入本目录：

~~~powershell
Set-Location "Docs\讲义\示例-Selenium"
python -m pip install -r requirements.txt
python -m http.server 8765 --bind 127.0.0.1
~~~

在浏览器访问 http://127.0.0.1:8765/index.html。保留这个终端，另开终端同样进入本目录运行：

~~~powershell
python demo.py --case basics
python demo.py --case all --headless
~~~

需要已安装的 Chrome，驱动默认由 Selenium Manager 管理，首次使用可能联网准备文件。也可以显式配置路径：

~~~powershell
$env:SELENIUM_BROWSER = "C:\tools\chrome\chrome.exe"
$env:SELENIUM_DRIVER = "C:\tools\chromedriver.exe"
python demo.py --case basics
~~~

路径只是格式样例，请替换成自己的文件。设置浏览器路径和驱动路径后，仍须保证它们兼容。

换端口时同步指定 SELENIUM_DEMO_URL，例如 http://127.0.0.1:8766。

## 2. 17 组样例

每组开始前重新打开练习页，最后统一 quit。命令格式为 python demo.py --case 名称，可追加 --headless。

| 名称 | 操作 | 预期观察 |
| --- | --- | --- |
| basics | 输入朝阳、搜索、读文本与 URL | D：朝阳 整租 7000元 |
| locators | 八种定位、单数、复数、查找失败 | 海淀首页两条房源；复数找不到为 [] |
| input | 清空、追加、HOME/SHIFT/END/DELETE、回车 | 追加为“海淀 单间”，清空后“朝阳” |
| click | 复选框、双击、JS 点击 | 状态切换；显示“已双击” |
| extract | 文本、href、value、src、属性、HTML、CSS | A、2500；直接文本与子元素文本不同 |
| wait | 等 DOM 出现、等可见 | “加载完成”；可见后输入 |
| iframe | 进入外层、内层、返回父文档和主文档 | 外层房源、内层房源 |
| windows | 新标签页切换、关闭、同页跳转后退 | A 详情；回到列表 |
| select | 按索引、value、可见文字选择 | 朝阳的 value 为 cy |
| actions | 鼠标悬停 | “已悬停”可见 |
| script | JS 返回值、滚动、计算视口坐标点击 | 读出输入框值；滚动位置变化 |
| alert | alert 确认、confirm 取消、prompt 输入 | 已取消；采集备注 |
| cookie | 添加、读取、刷新、删除 | haidian；删除后 None |
| screenshot | 视口截图、元素截图、PNG 字节 | output/page.png、house.png |
| download | 浏览器下载、Python 按 src 下载 | output/sample.txt、photo.svg |
| stale | 翻页后访问旧元素，重新查找 | 旧引用失效；重取 C |
| collect | 两地区、两页，只采单间、存 CSV | A 2500、C 2800、E 3000 |

## 3. 采集程序输出

~~~powershell
python demo.py --case collect
~~~

结果保存到本目录的 output/houses.csv。截图与下载也只写到 output，运行会创建这个目录。download 样例会移除自己上次生成的 output/sample.txt，再验证本次下载完成。

本页第二页的下一页按钮禁用，collect 的手写程序在第二页采集完后不再点击；后续 Flowchart 教学模型有独立的循环次数与末尾点击假设，以其讲义说明为准。

## 4. 附加操作

讲义中的 lxml 快照解析与 ddddocr 截图识别是附加练习，需要分别安装 lxml、ddddocr。它们不属于 Selenium 库，也不在默认 17 组运行范围内。

项目 MyChrome 的 iframe 参数、BrowserThread 与配置化执行示例需要项目完整依赖和任务上下文；demo.py 使用原生 Selenium，不能直接给它的 find_element 增加 iframe=True。
