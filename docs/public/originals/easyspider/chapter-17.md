# 17.Selenium：从 Python 基本操作到 EasySpider 浏览器执行

> 第 14 篇把“输入、点击、采集”等操作发成了消息。先弄清楚这些动作在 Python 中怎样真正执行，再进入第 16～23 篇的流程图存储与执行结构。
>
> 前两篇已经讲清任务怎样存储，以及 `executeNode()` 怎样组织循环、判断和递归。本篇从 Selenium 基础操作开始，第三部分每节先读现有 JSON 参数，再看流程与原版核心源码，逐项解释打开网页、输入、点击、提取和浏览器定制；第 24 节集中讲 `handleHistory()` 的新标签页与同页恢复，第四部分独立讲解 judgeExecute 的九种条件与分支选择，第五部分串起完整采集调用链。到第 17 篇结束，执行阶段讲完。
>
> 所有基础样例共用一份[本地练习页](示例-Selenium/index.html)，完整 Python 程序在 [demo.py](示例-Selenium/demo.py)。每个操作都有页面对象、代码和预期结果，不依赖搜索网站的页面结构。

---

## 第一部分：Selenium 是什么，最基本的操作是什么

### 1. Selenium 让 Python 向浏览器发命令

平常在浏览器里搜索房源，我们会打开网页、找到输入框、输入地区、点击搜索，再读出房源标题。Selenium WebDriver 提供相应的 Python 接口，让程序完成这些动作。

~~~python
driver.get(url)                                 # 打开网页
box = driver.find_element(By.ID, "area")         # 找到一个输入框
box.clear()                                    # 清空原有内容
box.send_keys("海淀")                           # 输入文字
driver.find_element(By.ID, "search").click()    # 点击搜索
text = driver.find_element(By.ID, "status").text # 读取页面上的文本
~~~

先认清两种对象：

| 对象 | 代表什么 | 常见操作 |
| --- | --- | --- |
| driver，类型为 WebDriver | 一次浏览器会话，可以控制页面、窗口和当前文档 | get、back、refresh、find_element、quit |
| box、button、link，类型为 WebElement | 浏览器中找到的一个具体 DOM 元素的引用 | clear、send_keys、click、text、get_attribute |

driver 负责找到元素；找到以后，元素对象负责输入、点击、取值。例如 box 不是已经取出的字符串，而是输入框的引用；读取输入框当前内容还要调用 box.get_attribute("value")。

Selenium 常用于网页自动化测试，也可以用于采集需要浏览器执行 JavaScript、点击交互之后才出现的数据。本篇关注 WebDriver 的 Python 用法。[官方入门说明](https://www.selenium.dev/documentation/webdriver/getting_started/first_script/)

### 2. 一条 Python 语句，怎样到达 Chrome

~~~text
Python 程序
    ↓ 调用 selenium 库，发送 WebDriver 命令
ChromeDriver 进程
    ↓ 控制 Chrome
Chrome 浏览器
    ↓ 执行页面动作或返回信息
Python 得到结果
~~~

例如：

~~~python
link = driver.find_element(By.ID, "download")
address = link.get_attribute("href")
~~~

第一行请求浏览器找元素，得到一个元素引用；第二行用这个引用请求读取 href，得到 Python 字符串。页面还在浏览器中，Python 并没有把整个网页变成一组可以随意访问的本地对象。

这里的 ChromeDriver 是驱动程序，Selenium 是 Python 使用的库，Chrome 是实际显示并执行网页的浏览器。ChromeDriver 内部使用 Chrome 的控制接口；换成 Firefox 等浏览器时，驱动实现也会不同。

启动可以有两种写法：

~~~python
from selenium import webdriver

driver = webdriver.Chrome()
~~~

这种写法交给 Selenium Manager 管理驱动的查找与准备，首次启动可能需要联网下载。手动准备了驱动时，则显式指定路径：

~~~python
from selenium.webdriver.chrome.service import Service

driver = webdriver.Chrome(
    service=Service(r"C:\tools\chromedriver.exe")
)
~~~

还可以通过 ChromeOptions.binary_location 指定浏览器可执行文件。EasySpider 的打包版就会显式配置浏览器和驱动路径，方便使用随软件提供的文件。两者仍需兼容，不应把“打包在一起”理解为任何更新后都不会发生版本问题。[Selenium Manager](https://www.selenium.dev/documentation/selenium_manager/)

### 3. 先准备一份能重复练习的页面

进入 [示例-Selenium](示例-Selenium/README.md) 目录，安装样例依赖并启动本地 HTTP 服务：

~~~powershell
Set-Location "Docs\讲义\示例-Selenium"
python -m pip install -r requirements.txt
python -m http.server 8765 --bind 127.0.0.1
~~~

服务运行期间，在浏览器访问 http://127.0.0.1:8765/index.html。练习页有：

~~~text
地区输入框：id=area，name=area，初始值为“海淀”
搜索按钮：id=search
结果提示：id=status
房源列表：id=houses
下一页按钮：id=next
~~~

固定房源数据：

| 地区 | 第 1 页 | 第 2 页 |
| --- | --- | --- |
| 海淀 | A：单间 2500 元；B：整租 6500 元 | C：单间 2800 元 |
| 朝阳 | D：整租 7000 元 | E：单间 3000 元 |

页面特意让搜索与翻页延迟 200 毫秒更新，让我们能看见“点击完成”与“结果更新完成”之间的区别。

样例 requirements.txt 使用 Selenium 4 的范围约束；项目 [ExecuteStage/requirements.txt](../../ExecuteStage/requirements.txt) 当前固定为 selenium==4.47.0。基础 API 按 Selenium 4 写法讲解，不把项目固定版本当成最新版。

### 4. 第一个完整 Python 例子：输入、点击、读取

另开一个终端，同样进入示例目录，创建或阅读下面的程序。HTTP 服务需要继续运行。

~~~python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = webdriver.Chrome()                       # 1. 创建浏览器会话
try:
    driver.get("http://127.0.0.1:8765/index.html")  # 2. 打开页面
    wait = WebDriverWait(driver, 5)

    box = driver.find_element(By.ID, "area")      # 3. 找到输入框
    box.clear()                                  # 4. 清空原有“海淀”
    box.send_keys("朝阳")                         # 5. 输入“朝阳”
    print("输入框当前值:", box.get_attribute("value"))

    button = driver.find_element(By.ID, "search")
    button.click()                               # 6. 点击搜索

    wait.until(EC.text_to_be_present_in_element(
        (By.ID, "status"), "朝阳 第1页"))          # 等这次搜索的结果更新

    link = driver.find_element(By.CSS_SELECTOR, ".detail-link")
    print("可见文本:", link.text)                  # 7. 读取结果
    print("链接地址:", link.get_attribute("href"))
    print("页面标题:", driver.title)
    driver.save_screenshot("result.png")
finally:
    driver.quit()                                # 8. 结束整个会话
~~~

关键输出：

~~~text
输入框当前值: 朝阳
可见文本: D：朝阳 整租 7000元
链接地址: http://127.0.0.1:8765/detail.html?id=D
页面标题: Selenium 房源练习页
~~~

逐行想一遍：先获得浏览器对象，再获得输入框对象；清空、输入改变输入框状态，点击让网页执行搜索，等待结果提示变成“朝阳 第1页”，最后才读取链接。

等待不是固定睡 5 秒，而是在最多 5 秒内反复检查条件，条件成立就返回。

我们已经有同样的可运行实现：

~~~powershell
python demo.py --case basics
~~~

程序结束会关闭它创建的浏览器。需要观察过程时用默认模式；验证一批操作时可加 --headless：

~~~powershell
python demo.py --case all --headless
~~~

---

## 第二部分：每一种基本操作，都用具体样例理解

下面的短例共用这些变量：

~~~python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = "http://127.0.0.1:8765/"
driver = webdriver.Chrome()
wait = WebDriverWait(driver, 5)
driver.get(BASE + "index.html")
wait.until(EC.text_to_be_present_in_element((By.ID, "status"), "海淀 第1页"))
~~~

每节作为独立练习时，先重新打开练习页并等待初始结果。这样上一节翻页、切 iframe 或关闭标签页不会影响下一节。demo.py 已经在每个样例开始前重置页面，结束时用 finally 调用 quit。

### 5. 找元素：定位方式、单数与复数

定位的意思是告诉浏览器“我要操作页面里的哪一个元素”。先看页面的一条房源：

~~~html
<li class="house" data-key="A">
  <a class="detail-link" href="detail.html?id=A">A：海淀 单间 2500元</a>
  <span class="price">2500</span>
</li>
~~~

八种常用定位方式都能在练习页找到具体对象：

| Python 写法 | 找到什么 |
| --- | --- |
| driver.find_element(By.ID, "area") | 地区输入框 |
| driver.find_element(By.NAME, "area") | 同一个输入框 |
| driver.find_element(By.CLASS_NAME, "house") | 第一条房源的 li |
| driver.find_element(By.TAG_NAME, "button") | 第一个 button，本页为搜索按钮 |
| driver.find_element(By.LINK_TEXT, "A：海淀 单间 2500元") | A 的详情链接 |
| driver.find_element(By.PARTIAL_LINK_TEXT, "A：") | 文字包含 A：的链接 |
| driver.find_element(By.CSS_SELECTOR, "#houses .detail-link") | 列表中的第一条详情链接 |
| driver.find_element(By.XPATH, "//ul[@id='houses']/li/a[@class='detail-link']") | 同一条详情链接 |

By.CLASS_NAME 的参数是一个类名。想匹配同时具有多个 class 的元素，改用 CSS 选择器。

~~~python
first = driver.find_element(By.CLASS_NAME, "house")
all_houses = driver.find_elements(By.CLASS_NAME, "house")
print(first.get_attribute("data-key"))  # A
print(len(all_houses))                  # 2
print([h.get_attribute("data-key") for h in all_houses])  # ['A', 'B']
~~~

find_element 取第一个匹配者，不验证“只能有一个”。原生 Selenium 的 find_elements 返回列表，即使只有一个结果也仍是列表。

~~~python
from selenium.common.exceptions import NoSuchElementException

print(driver.find_elements(By.ID, "missing"))  # []
try:
    driver.find_element(By.ID, "missing")
except NoSuchElementException:
    print("找不到这个元素")
~~~

元素也能继续找自己的后代：

~~~python
house = driver.find_elements(By.CLASS_NAME, "house")[0]
price = house.find_element(By.XPATH, ".//span[@class='price']")
print(price.text)  # 2500
~~~

XPath 的 .// 表示从当前 house 元素往下找，这与前面讲过的相对 XPath 相接。

运行对应样例：python demo.py --case locators。

### 6. 输入：清空、追加、回车和复选框

练习页的 note 输入框初始为“原有内容”。

~~~python
note = driver.find_element(By.ID, "note")
note.clear()
note.send_keys("海淀")
print(note.get_attribute("value"))  # 海淀

note.send_keys(" 单间")
print(note.get_attribute("value"))  # 海淀 单间
~~~

send_keys 会在当前光标位置输入，不自动替换旧内容，所以输入之前常常先 clear。

输入框的当前内容通常读 value；note.text 读的是元素的可见文本，不等同于输入框的 value。

~~~python
box = driver.find_element(By.ID, "area")
box.clear()
box.send_keys("朝阳", Keys.ENTER)
wait.until(EC.text_to_be_present_in_element((By.ID, "status"), "朝阳 第1页"))
~~~

Keys.ENTER 是按键，字符串 "<enter>" 本身不会自动变成回车。EasySpider 后面会专门解释这个占位符。

单行输入框还可以这样用按键清空：

~~~python
note.send_keys(Keys.HOME)
note.send_keys(Keys.SHIFT, Keys.END)
note.send_keys(Keys.DELETE)
note.send_keys("朝阳")
~~~

这段针对单行文本有清晰的“移到开头、选到末尾、删除”含义；多行 textarea 的 HOME/END 范围要另行验证，不应当成所有输入控件的万能清空方式。

复选框先读状态，再按需点击：

~~~python
checkbox = driver.find_element(By.ID, "only-single")
if not checkbox.is_selected():
    checkbox.click()
print(checkbox.is_selected())  # True
~~~

运行样例：python demo.py --case input；复选框见 --case click。[元素输入与点击](https://www.selenium.dev/documentation/webdriver/elements/interactions/)

### 7. 点击：普通点击、动作链、双击、JS 与坐标

普通按钮先这样写：

~~~python
driver.find_element(By.ID, "search").click()
~~~

想把鼠标动作排成序列，可以用 ActionChains：

~~~python
button = driver.find_element(By.ID, "search")
ActionChains(driver).move_to_element(button).click().perform()
~~~

前两步构造动作，perform 才提交执行。双击样例：

~~~python
button = driver.find_element(By.ID, "double")
ActionChains(driver).double_click(button).perform()
print(driver.find_element(By.ID, "double-result").text)  # 已双击
~~~

JavaScript 点击通过页面脚本调用 DOM 的 click：

~~~python
button = driver.find_element(By.ID, "search")
driver.execute_script("arguments[0].click()", button)
~~~

它与鼠标动作序列的事件语义不同，不能保证触发同样的悬停、按下、抬起过程。普通 WebElement.click 也有滚动与可交互检查，不能概括为“只会触发 click，而动作链一定更好”。

坐标点击可以先计算搜索按钮在视口中的中心：

~~~python
button = driver.find_element(By.ID, "search")
driver.execute_script("arguments[0].scrollIntoView({block:'center'})", button)
x, y = driver.execute_script(
    "const r=arguments[0].getBoundingClientRect();"
    "return [r.x+r.width/2, r.y+r.height/2]", button)
driver.execute_script(
    "document.elementFromPoint(arguments[0],arguments[1]).click()", x, y)
~~~

elementFromPoint 接收视口坐标；滚动、窗口大小和遮挡都会影响这个点下的元素。上述代码是 JS 坐标点击，并没有移动操作系统的鼠标。

运行样例：--case click 与 --case script。[鼠标动作](https://www.selenium.dev/documentation/webdriver/actions_api/mouse/)

### 8. 读取：文本、属性、HTML、CSS 与页面信息

~~~python
house = driver.find_elements(By.CLASS_NAME, "house")[0]
link = house.find_element(By.CSS_SELECTOR, ".detail-link")

print(link.text)                              # A：海淀 单间 2500元
print(link.get_attribute("href"))             # 绝对地址 .../detail.html?id=A
print(house.get_attribute("data-key"))        # A
print(driver.find_element(By.ID, "area").get_attribute("value"))  # 海淀
print(driver.find_element(By.ID, "photo").get_attribute("src"))   # .../sample.svg
~~~

get_attribute 会按 Selenium 的规则读取属性/属性值，href、src 常返回浏览器解析后的绝对 URL。需要区分 HTML 声明值和 DOM 当前属性值时，可用 get_dom_attribute 与 get_property：

~~~python
print(link.get_dom_attribute("href"))  # detail.html?id=A
print(link.get_property("href"))       # http://127.0.0.1:8765/detail.html?id=A
~~~

练习页中还有：

~~~html
<p id="mixed">房源描述<span>近地铁</span></p>
~~~

~~~python
mixed = driver.find_element(By.ID, "mixed")
print(mixed.text)                        # 房源描述近地铁
print(mixed.get_attribute("innerHTML"))  # 房源描述<span>近地铁</span>
print(mixed.get_attribute("outerHTML"))  # 包含外层 p 标签
~~~

只要直接文本，不包括 span 的文本，可交给 JS 遍历文本子节点：

~~~python
direct_text = driver.execute_script(
    "return Array.from(arguments[0].childNodes)"
    ".filter(n=>n.nodeType===3).map(n=>n.nodeValue).join('').trim()", mixed)
print(direct_text)  # 房源描述
~~~

其他取值：

~~~python
background = driver.find_element(By.ID, "background")
print(background.value_of_css_property("background-image"))  # url(".../sample.svg")
print(driver.title)                                         # Selenium 房源练习页
print(driver.current_url)                                   # 当前地址
html_text = driver.page_source                              # 当前文档的 HTML 字符串
~~~

运行样例：python demo.py --case extract。页面 URL、标题与截图等接口见 [WebDriver API](https://www.selenium.dev/selenium/docs/api/py/selenium_webdriver_remote/selenium.webdriver.remote.webdriver.html)。

### 9. 等待：什么时候可以做下一步

点击“延迟添加元素”后，页面 700 毫秒后才增加 id=loaded 的段落：

~~~python
driver.find_element(By.ID, "load-delayed").click()
loaded = wait.until(EC.presence_of_element_located((By.ID, "loaded")))
print(loaded.text)  # 加载完成
~~~

until 返回的就是条件找到的元素，后面可以直接使用。

“出现”与“可见”分开练习：

~~~python
hidden = driver.find_element(By.ID, "hidden-field")
print(hidden.is_displayed())  # False：在 DOM 中，但隐藏

driver.find_element(By.ID, "reveal").click()
field = wait.until(EC.visibility_of_element_located((By.ID, "hidden-field")))
field.send_keys("等可见后输入")
~~~

常用条件：

| 条件 | 等到什么 |
| --- | --- |
| presence_of_element_located | DOM 中已有匹配元素 |
| visibility_of_element_located | 匹配元素可见 |
| element_to_be_clickable | 元素可见并 enabled；不保证没有遮挡 |
| text_to_be_present_in_element | 某个元素的文本包含指定内容 |
| staleness_of(old_element) | 旧元素引用已经失效 |
| alert_is_present | JavaScript 弹窗出现 |

例如等按钮可用：

~~~python
button = wait.until(EC.element_to_be_clickable((By.ID, "search")))
button.click()
~~~

driver.get 默认按页面加载策略等待，仍不能保证后续异步业务内容已更新。固定 sleep 只经过一段时间，不验证结果；显式等待验证具体状态。不要混用隐式与显式等待，以免总等待时间难以预估。[等待策略](https://www.selenium.dev/documentation/webdriver/waits/)

运行样例：python demo.py --case wait。

### 10. iframe：先进入对应文档，再找元素

练习页的主文档包含 outer-frame，外层 iframe 又包含 inner-frame。它们各有独立的文档：

~~~text
主文档：area
└─ outer-frame：frame-result、frame-note
   └─ inner-frame：nested-result、nested-note
~~~

~~~python
wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "outer-frame")))
print(driver.find_element(By.ID, "frame-result").text)  # 外层房源
driver.find_element(By.ID, "frame-note").send_keys("外层输入")

wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "inner-frame")))
print(driver.find_element(By.ID, "nested-result").text)  # 内层房源

driver.switch_to.parent_frame()        # 内层回到外层
print(driver.find_element(By.ID, "frame-note").get_attribute("value"))  # 外层输入
driver.switch_to.default_content()     # 直接回主文档
print(driver.find_element(By.ID, "area").get_attribute("value"))       # 海淀
~~~

主文档里的查找不会自动穿过 iframe。切进去后，driver 的当前查找上下文也变了；完成后需要切回对应文档。

运行样例：python demo.py --case iframe。[iframe 切换](https://www.selenium.dev/documentation/webdriver/interactions/frames/)

### 11. 标签页与导航：分别处理“换窗口”和“同窗口跳转”

练习页的“新标签页打开 A”使用 target="_blank"。点击前记下已有句柄，点击后取新增句柄：

~~~python
original = driver.current_window_handle
before = set(driver.window_handles)

driver.find_element(By.CSS_SELECTOR, ".new-tab").click()
wait.until(lambda d: len(set(d.window_handles) - before) == 1)
new_handle = (set(driver.window_handles) - before).pop()

driver.switch_to.window(new_handle)
print(driver.find_element(By.ID, "title").text)  # A：海淀 单间
driver.close()                                 # 只关闭当前详情页
driver.switch_to.window(original)              # 切回列表
~~~

句柄是窗口/标签页的标识，不应依赖 window_handles 的列表顺序判断新旧。这里用集合差值找新增者。[窗口与标签页](https://www.selenium.dev/documentation/webdriver/interactions/windows/)

同一个标签页跳转则用导航：

~~~python
driver.find_element(By.CSS_SELECTOR, ".detail-link").click()
print(driver.title)  # A 房源详情
driver.back()
wait.until(EC.presence_of_element_located((By.ID, "area")))
print(driver.title)  # Selenium 房源练习页
driver.forward()    # 再前进到详情
driver.refresh()    # 刷新当前详情
~~~

也可以主动创建新标签页：

~~~python
driver.switch_to.new_window("tab")  # 创建并自动切换
driver.get(BASE + "detail.html?id=A")
~~~

close 关闭当前窗口；quit 结束会话并清理该会话管理的窗口。close 后需要切到仍然存在的句柄才能继续操作。[导航接口](https://www.selenium.dev/documentation/webdriver/interactions/navigation/)

运行样例：python demo.py --case windows。

### 12. 下拉框与鼠标悬停

原生 select：

~~~html
<select id="region">
  <option value="hd">海淀</option>
  <option value="cy">朝阳</option>
</select>
~~~

~~~python
dropdown = Select(driver.find_element(By.ID, "region"))
dropdown.select_by_index(1)             # 从 0 开始，1 是朝阳
print(dropdown.first_selected_option.text)  # 朝阳

dropdown.select_by_value("hd")
print(dropdown.first_selected_option.text)  # 海淀

dropdown.select_by_visible_text("朝阳")
print(dropdown.first_selected_option.get_attribute("value"))  # cy
~~~

Select 适用于 HTML select，不能直接用于 div/li 模拟的下拉组件；后者仍需定位菜单与选项，按页面交互点击。[Select 用法](https://www.selenium.dev/documentation/webdriver/support_features/select_lists/)

悬停样例：

~~~python
target = driver.find_element(By.ID, "hover-area")
ActionChains(driver).move_to_element(target).perform()
print(driver.find_element(By.ID, "hover-tip").text)  # 已悬停
~~~

运行样例：--case select 与 --case actions。

### 13. 执行 JavaScript 与滚动

execute_script 的脚本在当前页面上下文中执行；return 把 JS 值交回 Python：

~~~python
note = driver.find_element(By.ID, "note")
value = driver.execute_script("return arguments[0].value", note)
print(value)  # 原有内容
~~~

arguments[0] 是第一个额外参数。传入 WebElement 时，浏览器把它解析成对应的 DOM 元素。没有 return 的脚本通常给 Python 返回 None。

~~~python
bottom = driver.find_element(By.ID, "bottom")
driver.execute_script("arguments[0].scrollIntoView({block:'center'})", bottom)
print(driver.execute_script("return window.scrollY"))  # 大于 0

driver.execute_script("window.scrollTo(0,0)")
driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
~~~

一个是 JS 调整滚动位置，一个是向 body 发送 END 按键；页面焦点、可滚动容器与事件处理不同，效果也可能不同。

运行样例：python demo.py --case script。

### 14. 提示框、确认框和输入弹窗

这些是 JavaScript 的 alert/confirm/prompt，不是网页内普通 div 弹层。

~~~python
driver.find_element(By.ID, "alert").click()
alert = wait.until(EC.alert_is_present())
print(alert.text)  # 练习提示
alert.accept()

driver.find_element(By.ID, "confirm").click()
wait.until(EC.alert_is_present()).dismiss()
print(driver.find_element(By.ID, "confirm-result").text)  # 已取消

driver.find_element(By.ID, "prompt").click()
prompt = wait.until(EC.alert_is_present())
prompt.send_keys("采集备注")
prompt.accept()
print(driver.find_element(By.ID, "prompt-result").text)  # 采集备注
~~~

accept 确认，dismiss 取消，send_keys 用于可输入的 prompt。普通网页弹层仍要用 find_element 定位其按钮。[弹窗接口](https://www.selenium.dev/documentation/webdriver/interactions/alerts/)

运行样例：python demo.py --case alert。

### 15. Cookie：先进入对应站点，再设置

~~~python
driver.get(BASE + "index.html")
driver.add_cookie({"name": "demo_area", "value": "haidian"})
print(driver.get_cookie("demo_area")["value"])  # haidian

driver.refresh()
print(driver.get_cookie("demo_area")["value"])  # 仍为 haidian
driver.delete_cookie("demo_area")
print(driver.get_cookie("demo_area"))           # None
~~~

添加 Cookie 时浏览器必须已有适用的站点上下文。Cookie 在本例只是练习数据，不会自动改变地区输入框，也不能凭空构造真实网站的登录状态。[Cookie 操作](https://www.selenium.dev/documentation/webdriver/interactions/cookies/)

运行样例：python demo.py --case cookie。

### 16. 截图、OCR 与下载

截图先分清整页当前视口与单个元素：

~~~python
driver.save_screenshot("page.png")         # 浏览器当前视口
house = driver.find_element(By.CLASS_NAME, "house")
house.screenshot("house.png")              # 单条房源
image_bytes = house.screenshot_as_png      # PNG 字节，留在 Python 内存
~~~

save_screenshot 通常不是整个长页面的截图。需要整页时另行设置窗口、拼接或使用浏览器支持的接口，不应把“截图”与“整页截图”混为一谈。

OCR 是截图之后交给另一个库识别，Selenium 本身不做识别。以下附加例子需要安装 ddddocr：

~~~python
from ddddocr import DdddOcr

image_bytes = driver.find_element(By.ID, "captcha").screenshot_as_png
text = DdddOcr(show_ad=False).classification(image_bytes)
print(text)  # 目标是练习页上的 1234，实际结果取决于识别效果
~~~

这个 OCR 例子是对截图数据的识别，不包含网站验证码的交互流程。

下载目录在创建浏览器前配置：

~~~python
from pathlib import Path

download_dir = Path("downloads").resolve()
download_dir.mkdir(exist_ok=True)
options = webdriver.ChromeOptions()
options.add_experimental_option("prefs", {
    "download.default_directory": str(download_dir),
    "download.prompt_for_download": False,
})
driver = webdriver.Chrome(options=options)
try:
    driver.get(BASE + "index.html")
    driver.find_element(By.ID, "download").click()
    # click 返回时不代表文件已经下载完成
    WebDriverWait(driver, 10).until(
        lambda d: (download_dir / "sample.txt").exists())
    print((download_dir / "sample.txt").read_text(encoding="utf-8"))
finally:
    driver.quit()
~~~

这段配置例子独立创建了一个会话。正式代码不要在未关闭旧会话时覆盖 driver 变量。

图片 URL 也可以先由 Selenium 读出，再用 Python 下载：

~~~python
from urllib.request import urlopen
from pathlib import Path

url = driver.find_element(By.ID, "photo").get_attribute("src")
with urlopen(url, timeout=5) as response:
    Path("photo.svg").write_bytes(response.read())
~~~

读取 src 并不会下载图片到指定文件。对于需要登录 Cookie、请求头或签名的图片，独立 HTTP 请求还需对应的访问上下文。本地样例不需要这些。

运行样例：--case screenshot 与 --case download。OCR 是选做，不包含在 --case all 中。

### 17. 元素失效：同一位置，可能已经换了一个 DOM 节点

练习页翻页时会替换列表内容：

~~~python
from selenium.common.exceptions import StaleElementReferenceException

old_link = driver.find_element(By.CSS_SELECTOR, ".detail-link")  # A
driver.find_element(By.ID, "next").click()
wait.until(EC.staleness_of(old_link))

try:
    print(old_link.text)
except StaleElementReferenceException:
    fresh = driver.find_element(By.CSS_SELECTOR, ".detail-link")
    print(fresh.text)  # C：海淀 单间 2800元
~~~

old_link 仍指向上一页的节点；新页面即使有相同 XPath，也需要重新定位。只 sleep 不会把旧引用变成新引用。实际代码应等待目标状态，再重新查找，并限制重试次数。

运行样例：python demo.py --case stale。

### 18. 浏览器选项与超时：用具体配置理解

下面的初始化配置作为独立脚本的起步部分；先结束之前练习的会话，再创建新 driver，操作完成后仍需在 finally 中调用 quit。demo.py 的 create_driver 和 main 已经把这两部分连好。

~~~python
from selenium.webdriver.chrome.service import Service

options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--window-size=1280,1000")
# 手动配置时，按自己的安装路径填写：
# options.binary_location = r"C:\tools\chrome\chrome.exe"
# driver = webdriver.Chrome(service=Service(r"C:\tools\chromedriver.exe"), options=options)
driver = webdriver.Chrome(options=options)
~~~

headless 控制是否显示界面；窗口大小会影响布局、元素位置和截图。user-data-dir 可指定浏览器用户目录，但当前已被另一个会话占用的目录不宜重复使用。

两类超时：

~~~python
from selenium.common.exceptions import TimeoutException

driver.set_page_load_timeout(10)
driver.set_script_timeout(5)
try:
    driver.get(BASE + "index.html")
except TimeoutException:
    driver.execute_script("window.stop()")
~~~

页面加载超时并不等于后面所有业务元素都可用了；停止加载后仍应根据具体目标判断能否继续。set_script_timeout 主要用于异步脚本等待等场景，不应理解为能可靠中断任何卡死的同步页面 JS。

---

## 第三部分：先读参数、看流程，再追 EasySpider 的核心实现

代码中的 `⭐️⭐️⭐️` 是讲解补充的注释，用来标明“父循环本轮处理谁”和“何处调用执行函数完成具体操作”；执行语句沿用原源码。

每节按“真实 JSON 参数 → 大致流程 → 核心源码 → 代入参数解释”阅读。代码使用当前仓库原语句，只摘与本节有关的部分；省略处以 `# ……` 标出，保留原变量、判断和调用方式。省略的上下文和完整异常处理用源码链接承接，不另写优化版函数。片段用于对照原方法，需要结合原来的作用域阅读。

第 14 篇是扩展发出的操作消息；这里是保存后的任务节点。节点 option 决定调用什么方法，parameters 提供动作参数，父容器 sequence 组织操作顺序。Examples 与 ElectronJS/tasks 是现有任务；房源教学模型另标为结构练习。

先看一轮任务的总体位置：

~~~text
读取任务 → 创建浏览器/任务线程 → 预处理与初始化输出字段
  → run 从 root 执行 → 各节点先等待目标，再调用具体动作
  → 动作按配置定位、输入/点击/读取；完成后滚动或等待
  → 一轮详情操作结束后，列表循环恢复页面并推进到下一项
  → 输出行进入缓存 → 达到阈值或正常收尾时写盘
~~~

源码入口：[执行器](../../ExecuteStage/easyspider_executestage.py)、[MyChrome](../../ExecuteStage/myChrome.py)、[utils](../../ExecuteStage/utils.py)。本部分讲动作的过程；第 15–16 篇已经讲过完整结构、递归与生命周期，这里沿着它们的调用链继续追踪具体操作。

### 19. 任务先怎样读进 Python，动作参数又从哪里取

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[1].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": false,
  "url": "https://www.jx-jx.net/article/9",
  "links": "https://www.jx-jx.net/article/9",
  "maxWaitTime": 10,
  "wait": 0
}
~~~

**大致流程**：从本地文件或服务接口读出 service → 线程保存 graph → executeNode 按下标取节点 → 按 option 调用具体方法。

本例 option=1 是打开网页。先看本地读取与保存执行结构的原语句：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `__main__：本地读取执行实例`，第 2565–2568 行。

~~~python
file_path = os.path.join(local_folder, str(id) + ".json")
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()
    service = json.loads(content)  # 加载服务信息
~~~

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `BrowserThread.__init__()：保存 graph`，第 190 行。

~~~python
self.procedure = service["graph"]  # 程序执行流程
~~~

executeNode 用数组下标取节点，再把 parameters 交给动作函数；remote 路径通过 queryExecutionInstance 接口取得同一份 service。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `executeNode()：取节点与打开网页分发`，第 969、1006–1008 行。

~~~python
node = self.procedure[nodeId]
    # ……（省略其他原代码）
    elif node["option"] == 1:  # 打开网页操作
        # if not (nodeId == 1 and self.service["cloudflare"] == 1):
        self.openPage(node["parameters"], loopValue)
~~~

Examples 文件用于认识参数；正式执行入口读的是执行实例。allXPaths 是设计时备选路径，普通动作不会自动轮流尝试所有备选。任务存取的细节见第 23、26 篇。

<a id="output-parameters"></a>

#### 19.1 self.outputParameters 是什么，怎样变成最终输出

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `任务顶层`（只摘本节用到的键，值保持原样）。

~~~json
{
  "outputParameters": [
    {
      "id": 0,
      "name": "参数1_链接文本",
      "desc": "",
      "type": "string",
      "exampleValue": "华建建设集团有限公司"
    },
    {
      "id": 1,
      "name": "参数2_链接地址",
      "desc": "",
      "type": "string",
      "exampleValue": "https://www.jx-jx.net/articleview/574.html"
    }
  ]
}
~~~

**大致流程**：字段配置初始化成空字典 → 采集结果按 name 更新字典 → new_line 拍成一行 → OUTPUT 缓存 → saveData 写入结果文件。

self 是本任务的 BrowserThread；self.outputParameters 是“字段名 → 当前字段值”的字典。任务 JSON 的 outputParameters 是字段配置数组，self.OUTPUT 才是已组装、待写盘的行列表。

初始化根据 name 建空值，并记录字段类型与是否写入：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `BrowserThread.__init__()：初始化输出字段`，第 258–263 行。

~~~python
for param in service["outputParameters"]:  # 初始化输出参数
    if param["name"] not in self.outputParameters.keys():
        self.outputParameters[param["name"]] = ""
        self.dataNotFoundKeys[param["name"]] = False
        self.outputParametersTypes.append(param.get("type", "text"))
        self.outputParametersRecord.append(bool(param.get("recordASField", True)))
~~~

上面的任务初始化后是两项空值。若一次采集读到了任务样例中的内容，当前字典可手推成：

~~~json
{"参数1_链接文本":"华建建设集团有限公司","参数2_链接地址":"https://www.jx-jx.net/articleview/574.html"}
~~~

exampleValue 是设计时样例，初始化不会把它当运行值。getData 更新字段，并在字段循环之后按配置生成行：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：字段赋值与组装行`，第 2278、2281–2284 行。

~~~python
        self.outputParameters[p["name"]] = content
# ……（省略其他原代码）
if param["recordASField"] > 0 and param["newLine"]:
    line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
    self.OUTPUT.append(line)
~~~

new_line 的核心是按字典顺序取 values，保留完整值；maxViewLength 只限制终端预览：

**核心源码**：[utils.py](../../ExecuteStage/utils.py) → `new_line()`，第 295–304 行。

~~~python
def new_line(outputParameters, maxViewLength, record):
    line = []
    i = 0
    for value in outputParameters.values():
        line.append(value)
        if record[i]:
            print(value[:maxViewLength], " ", end="")
        i += 1
    print("")
    return line
~~~

上面的字典经过 `new_line()` 后，返回的 `line` 具体是：

~~~python
["华建建设集团有限公司", "https://www.jx-jx.net/articleview/574.html"]
~~~

也就是按字段顺序把两个值取出来，组成一行列表；字段名不放进这一行。执行 `self.OUTPUT.append(line)` 后，若追加前缓存为空，`self.OUTPUT` 就是：

~~~python
[
    ["华建建设集团有限公司", "https://www.jx-jx.net/articleview/574.html"]
]
~~~

外层列表存放多条记录，内层列表是一条记录的各列值。如果缓存里已有表头或其他记录，这一行就追加到它们后面。下一条记录可以覆盖字段字典，已经组装的上一行仍留在缓存。`clear` 决定采前是否清空字段，`newLine` 决定是否生成一行。

saveData 达到缓存阈值或正常收尾时才写盘；CSV 分支按记录标志过滤列：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `saveData()：阈值、CSV 写入与清缓存`，第 568、582–587、602 行。

~~~python
if exit == True or len(self.OUTPUT) >= self.save_threshold:
    # ……（省略其他原代码）
    if self.outputFormat == "csv" or self.outputFormat == "txt":
        file_name = "Data/Task_" + \
                    str(self.id) + "/" + self.saveName + \
                    '.' + self.outputFormat
        write_to_csv(file_name, self.OUTPUT,
                     self.outputParametersRecord)
    # ……（省略其他原代码）
    self.OUTPUT = []
~~~

**核心源码**：[utils.py](../../ExecuteStage/utils.py) → `write_to_csv()`，第 307–315 行。

~~~python
def write_to_csv(file_name, data, record):
    with open(file_name, 'a', encoding='utf-8-sig', newline="") as f:
        f_csv = csv.writer(f)
        for line in data:
            to_write = []
            for i in range(len(line)):
                if record[i]:
                    to_write.append(line[i])
            f_csv.writerow(to_write)
~~~

本例两列的 recordASField 缺省为真，结果包含链接文字和地址。recordASField=false 的字段仍可用于 Field 引用与条件判断。其他格式、续采与收尾见第 16 篇。

### 20. 浏览器启动与驱动定制：哪些来自 JSON，哪些来自启动代码

**从文件读取的参数示例**：[Exec and Eval.json](../../Examples/Exec%20and%20Eval.json) → `任务顶层`（只摘本节用到的键，值保持原样）。

~~~json
{
  "version": "0.5.0",
  "cloudflare": 0,
  "environment": 0,
  "saveName": "current_time",
  "outputFormat": "xlsx"
}
~~~

**大致流程**：先选浏览器与驱动、设置 Options → 建立浏览器会话 → 为任务注入新文档脚本、设置下载目录 → 创建并启动 BrowserThread。

本例 cloudflare=0 走普通浏览器，environment=0 不启用移动模拟。Chrome 本地驱动创建的核心是：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `__main__：Service 与 MyChrome`，第 2610–2611 行。

~~~python
selenium_service = Service(executable_path=driver_path)
browser_t = MyChrome(service=selenium_service, options=options, mode='local_driver')
~~~

浏览器建立后，线程初始化通过 CDP 注册新文档脚本；登录态目录、无头模式与驱动路径还来自启动配置：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `BrowserThread.__init__()：注册新文档脚本`，第 169–180 行。

~~~python
stealth_path = os.path.join(os.path.dirname(driver_path), "stealth.min.js")
with open(stealth_path, 'r') as f:
    js = f.read()
    self.print_and_log("Loading stealth.min.js")
self.browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': js})  # TMALL 反扒
self.browser.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
        Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
        })
"""
})
~~~

下载目录随后重定向到本任务 files，后台线程监视下载。cloudflare=1 使用另一驱动分支 MyUCChrome；驱动补丁和 profile 复制按对应源码实现。任务输出参数 saveName/outputFormat 则控制结果文件，不是 Chrome Options。设计态浏览器见第 24 篇。

#### 20.1 replace_field_values：先把字段引用替换成当前值

**从文件读取的参数示例**：[169.json](../../ElectronJS/tasks/169.json) → `graph[6].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": false,
  "xpath": "//*[@id=\"key\"]",
  "value": "Field[\"自定义操作\"]Field[\"参数2_文本\"]"
}
~~~

**大致流程**：读取 JSON 中带 `Field["字段名"]` 的文本 → 从 `self.outputParameters` 取当前字段值 → 替换成普通字符串 → 交给后续的打开网页、输入或元素定位代码。

`Field["参数2_文本"]` 是 EasySpider 约定的占位写法。JSON 读出来后它仍是一段字符串，调用 `replace_field_values()` 才会替换。常见调用中的三个参数是：

| 参数 | 传入什么 | 用途 |
| --- | --- | --- |
| `orginal_text` | `url`、`value`、`xpath` 等待处理的字符串 | 保留普通文字，替换其中的模板内容；源码形参就是这个拼写 |
| `outputParameters` | `self.outputParameters` | 按字段名读取本任务当前值，见前面的 19.1 节 |
| `browser` | `self`，即当前 `BrowserThread`；缺省为 `None` | 普通字段替换不需要它；`JS(...)` 分支通过它访问 `self.browser`，表达式也可引用任务上下文 |

以上面的输入节点为例，假设前面的采集和自定义操作执行后，运行时字典中的两项是（这里是演示当前值，不是把 JSON 的 `exampleValue` 自动填进去）：

~~~python
self.outputParameters = {
    "自定义操作": "800",
    "参数2_文本": "/手机/数码"
}
~~~

输入节点的原文与替换结果对应如下：

~~~text
替换前：Field["自定义操作"]Field["参数2_文本"]
替换后：800/手机/数码
~~~

两个占位符挨在一起，所以替换结果直接拼接，不会自动增加空格或分隔符。这个节点 `useLoop=false`，输入值来自 `parameters.value`；经替换等处理后，才由 `textbox.send_keys(replaced_text)` 输入搜索框。

**核心源码**：[utils.py](../../ExecuteStage/utils.py) → `replace_field_values()`，只摘普通字段替换主线，省略表达式处理分支，保留原代码：

~~~python
def replace_field_values(orginal_text, outputParameters, browser=None):
    field_pattern = r'Field\["([^"]+)"\]'
    try:
        working_text = orginal_text
        # ……（省略 eval(...)、JS(...) 分支）
        replaced_text = re.sub(
            field_pattern,
            lambda match: str(outputParameters.get(match.group(1), '')),
            working_text,
        )
    except Exception as e:
        print("eval替换失败，请检查eval语句是否正确。| Failed to replace eval, please check if the eval statement is correct.")
        print(e)
        replaced_text = orginal_text
    return replaced_text
~~~

`field_pattern` 匹配 `Field["字段名"]`；`match.group(1)` 取出字段名；`outputParameters.get(..., '')` 查当前值，找不到时用空字符串；`str(...)` 把取到的值转成字符串。`re.sub()` 返回替换后的文本，不修改字段字典。没有占位符的普通网址会原样返回。即使字段设置了 `recordASField=0`，只要它仍在运行时字典中，就可以被引用。

完整函数还支持 `eval("...")` 和 `JS("...")`：前者计算 Python 表达式，例如 `eval("1 + 2")` 得到字符串 `"3"`；后者通过 `browser.browser.execute_script(...)` 执行浏览器脚本，例如 `JS("return document.title")` 得到当前标题。当前实现先处理这些表达式，再替换剩余的普通 `Field[...]`；本节先掌握字段替换，后面的普通 URL、XPath 和输入值都沿用这一入口。

### 21. 打开网页：JSON 的 URL 怎样变成 get 和 Cookie 操作

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[1].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": false,
  "url": "https://www.jx-jx.net/article/9",
  "links": "https://www.jx-jx.net/article/9",
  "maxWaitTime": 10,
  "scrollType": 0
}
~~~

**大致流程**：打开前：进入方法先等 1 秒、整理标签页、选择 URL 并替换字段、设置超时 → get(url) → 打开后：按配置设置 Cookie、记录 history、滚动 → 返回 executeNode 做节点后等待。

本例 useLoop=false、url 不是 about:blank，实际 URL 来自本轮 self.links[self.urlId]，同时清空已有输出值：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `openPage()：原 URL 选择与字段替换`，第 1570–1580 行。

~~~python
if param["useLoop"]:
    url = loopValue
elif param["url"] != "about:blank":
    url = self.links[self.urlId]
    # clear output parameters
    for key in self.outputParameters:
        self.outputParameters[key] = ""
else:  # 在流程图其他位置设置了打开网页的操作，读取的应该是第一个网址，如打开网页后登录，再打开第二个网页
    url = list(filter(isnotnull, param["links"].split("\n")))[0]
# 将value中的Field[""]替换为outputParameters中的键值
url = replace_field_values(url, self.outputParameters, self)
~~~

选好网址后，设置加载/脚本超时，再 get；Cookie 设置发生在 get 之后：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `openPage()：超时、打开与 Cookie`，第 1586–1596 行。

~~~python
self.browser.set_page_load_timeout(maxWaitTime)  # 加载页面最大超时时间
self.browser.set_script_timeout(maxWaitTime)
self.browser.get(url)
if param["cookies"] != "":
    self.browser.delete_all_cookies()  # 清除所有已有cookie
    cookies = param["cookies"].split('\n')
    for cookie in cookies:
        name, value = cookie.split('=', 1)
        cookie_dict = {'name': name, 'value': value}
        # 加载 cookie
        self.browser.add_cookie(cookie_dict)
~~~

本例旧 JSON 的 cookies 由预处理补为空。Cookie 非空时先删除现有 Cookie，再逐行拆 name=value 添加；代码没有紧接着自动刷新。之后记录浏览器历史并调用 scrollDown；加载超时会尝试 window.stop。useLoop=true 时用本轮网址，about:blank 分支使用节点 links 的第一条。

### 22. 普通输入与批量输入：inputText 怎样落到 inputInfo

**从文件读取的参数示例**：[0.json](../../ElectronJS/tasks/0.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "xpath": "//*[@id=\"gh-ac\"]",
  "useLoop": false,
  "value": "iPhone",
  "beforeJS": "",
  "afterJS": ""
}
~~~

**大致流程**：输入前：稍等、替换定位路径、找到输入框、执行前置 JS → 用按键删除原值 → 选固定 value 或 loopValue，替换字段/处理分段 → send_keys 输入，必要时回车 → 执行后置 JS。

普通输入记录为 option=4，调用原 inputInfo。定位、前置脚本、清空一行和选择值的核心如下：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `inputInfo()：定位、清空与选择输入值`，第 1629–1647 行。

~~~python
xpath = replace_field_values(
    param["xpath"], self.outputParameters, self)
textbox = self.browser.find_element(
    By.XPATH, xpath, iframe=param["iframe"])
#     textbox.send_keys(Keys.CONTROL, 'a')
#     textbox.send_keys(Keys.BACKSPACE)
self.execute_code(
    2, param["beforeJS"], param["beforeJSWaitTime"], textbox, iframe=param["iframe"])  # 执行前置JS
# Send the HOME key
textbox.send_keys(Keys.HOME)
# Send the SHIFT + END key combination
textbox.send_keys(Keys.SHIFT, Keys.END)
# Send the DELETE key
textbox.send_keys(Keys.DELETE)
value = ""
if param["useLoop"]:
    value = loopValue
else:
    value = param["value"]
~~~

中间按原 replace_field_values 处理 Field 引用，移除 enter 标记；index 非零时按 ~ 分段取值。真正输入与后置动作是：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `inputInfo()：发送文字/回车与后置 JS`，第 1666–1672 行。

~~~python
textbox.send_keys(replaced_text)
if value.lower().find("<enter>") >= 0:
    textbox.send_keys(Keys.ENTER)
self.recordLog("输入文字|Input text: " +
               replaced_text + " to " + xpath)
self.execute_code(
    2, param["afterJS"], param["afterJSWaitTime"], textbox, iframe=param["iframe"])  # 执行后置js
~~~

代入本例 useLoop=false，取 iPhone，最终输入该字符串。没有 enter 标记就不发回车。HOME/SHIFT+END/DELETE 是原版的删除方式，对多行控件不能保证清空全文；旧任务 index 缺省为 0、iframe 缺省为 false。

#### 22.1 批量输入先建立文本循环，输入孩子取本轮值

**从文件读取的参数示例**：[169.json](../../ElectronJS/tasks/169.json) → `graph[7].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": "3",
  "textList": "A~TField[\"自定义操作\"]T~C"
}
~~~

**从文件读取的参数示例**：[169.json](../../ElectronJS/tasks/169.json) → `graph[8].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "xpath": "//*[@id=\"key\"]",
  "useLoop": true,
  "value": "",
  "index": 0
}
~~~

**大致流程**：文本循环拆 textList → 每轮取一段 text → 按 sequence 调孩子并传入 text → 输入孩子 useLoop=true 取 loopValue → 执行上一节的输入步骤。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：固定文本循环的核心调用`，第 1455、1461–1475 行。

~~~python
textList = node["parameters"]["textList"].split("\n")
# ……（省略其他原代码）
for text in textList:  # ⭐️⭐️⭐️这是父文本循环，本轮上下文是 text；取出当前文本后，再由 executeNode 执行孩子操作
    if self.shutdown_event.is_set():
        break
    if index < skipCount:
        index += 1
        self.print_and_log("跳过第" + str(index) + "个文本")
        self.print_and_log("Skip the " + str(index) + "th text")
        continue
    text = replace_field_values(text, self.outputParameters, self)
    # self.recordLog("当前循环文本|Current loop text:", text)
    for i in node["sequence"]:  # 挨个执行操作
        self.executeNode(i, text, "", 0)  # ⭐️⭐️⭐️这里执行当前文本对应的孩子操作；输入孩子会把 text 交给 inputInfo，再执行 send_keys
        if self.BREAK or self.CONTINUE:  # 如果有break操作，下面的操作不执行
            self.CONTINUE = False
            break
~~~

这里省略跳过项和退出的外围内容，保留原来的 for text 与孩子调用。169 的输入孩子 value 为空，但 useLoop=true，因此 inputInfo 取当前循环值：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `inputInfo()：循环值输入`，第 1643–1647、1666–1668 行。

~~~python
value = ""
if param["useLoop"]:
    value = loopValue
else:
    value = param["value"]
# ……（省略其他原代码）
textbox.send_keys(replaced_text)
if value.lower().find("<enter>") >= 0:
    textbox.send_keys(Keys.ENTER)
~~~

循环决定重复多少次，输入方法每次只处理当前 text。169 的 Field 引用保持文件原值；设计态即时键盘输入是另一条消息链。

### 23. 点击：普通点击、循环当前项与新标签页设置

**从文件读取的参数示例**：[221.json](../../ElectronJS/tasks/221.json) → `graph[3].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "xpath": "",
  "useLoop": true,
  "loopType": 1,
  "clickWay": 0,
  "newTab": 1,
  "wait": 2,
  "maxWaitTime": 10
}
~~~

**大致流程**：点击前：设置超时、计算本轮 XPath、定位元素、执行前置 JS → 按 clickWay/newTab 点击 → 点击后：处理弹窗和后置 JS、等待、检测标签页变化并更新 history、滚动。

本节按四个具体场景展开定位与点击。循环如何恢复网页在第 24 节讲，前后置 JS 和异常降级可回到原 clickElement 查看，不在每个例子里重复完整方法。

| 场景 | 点击用的路径 | 元素索引 |
| --- | --- | --- |
| useLoop=false | 节点自己的 xpath | 函数内设为 0 |
| useLoop=true、xpath 为空 | 父循环传来的 clickPath | 保留循环 index |
| useLoop=true、xpath 非空 | (clickPath)[index+1] + xpath | 拼接后函数内设为 0 |

**循环执行的主线是：先根据循环节点的 XPath 找到网页元素，确定本轮的 `element`；然后遍历 `node["sequence"]`，逐个调用 `executeNode()`，执行循环内配置的点击、提取数据等具体操作。**

这里的 `element` 是网页上的元素；`node["sequence"]` 中的 `i` 是要执行的孩子节点编号。**找到元素只是准备本轮上下文，真正执行什么操作，由 `executeNode()` 根据孩子节点的 `option` 分派。**

先区分两个层次：父循环的 `loopType` 决定“每轮找同一位置”还是“依次遍历一组元素”；点击孩子的 `useLoop` 决定是否沿用父循环传来的定位上下文。`useLoop=true` 本身不能说明父循环有多少个元素。循环类型以父循环节点（`option=8`）的 `parameters.loopType` 为准，点击节点里保留的同名键不负责驱动循环。

| 父循环类型 | 父循环怎样取元素 | 传给点击孩子的 index |
| --- | --- | --- |
| `loopType=0`，循环点击单个元素，如下一页 | 每轮 `find_element()` 重新定位同一 XPath | 每轮都是 `0` |
| `loopType=1`，循环点击每个元素，如列表中的各个链接 | `find_elements()` 得到一组元素，逐项处理 | `0、1、2…` |

下面先看“网页是什么样、这一轮要点谁”，再看 JSON 参数和原版核心代码。

| 小节 | 当前场景 | 循环类型 | 每轮点谁 |
| --- | --- | --- | --- |
| 23.1 | 点击一次搜索按钮 | 普通点击 | 搜索按钮 |
| 23.2 | 采完一页后，再点下一页 | 循环点击单个元素，`loopType=0` | 当前页的下一页按钮 |
| 23.3 | 依次进入列表中每个学科的详情 | 循环点击每个链接对应的元素，`loopType=1` | 第一项、第二项、第三项…… |
| 23.4 | 依次处理每个分类块，点击块内第一个链接 | 循环遍历每个块，`loopType=1` | 当前块的 `/a[1]` |

Python 列表从 0 开始，XPath 位置从 1 开始。

#### 23.1 场景一：点击一次搜索按钮，普通点击

**当前场景**：在搜索框输入关键字后，只点一次搜索按钮。这一步是普通点击，`useLoop=false`，使用点击节点自己的 XPath；没有父循环逐项切换目标。

**从文件读取的参数示例**：[0.json](../../ElectronJS/tasks/0.json) → `graph[3].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": false,
  "xpath": "//*[@id=\"gh-btn\"]"
}
~~~

**大致流程**：父容器调用点击节点 → 使用节点自己的 XPath → 取第一个匹配结果 → 执行普通点击 → 返回父容器。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `clickElement()：普通路径定位`，第 1709–1716 行。

~~~python
else:
    index = 0
    path = xpath  # 不然使用元素定义的xpath
    # element = self.browser.find_element(
    #     By.XPATH, path, iframe=param["iframe"])
elements = self.browser.find_elements(
    By.XPATH, path, iframe=param["iframe"])
element = elements[index]  # ⭐️⭐️⭐️这里在点击函数内按 index 选出本次点击目标；父容器已传入定位上下文，此句还没有执行点击
~~~

本例 path 为搜索按钮 XPath，index=0。原文件没有 newTab，原方法缺省按 0；默认动作链分支为：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `clickElement()：默认点击`，第 1746–1756 行。

~~~python
elif click_way == 0:  # 用selenium的点击方法
    try:
        actions = ActionChains(self.browser)  # 实例化一个action对象
        if newTab == 1:  # 在新标签页打开
            if sys.platform == "darwin":  # Mac
                actions.key_down(Keys.COMMAND).click(element).key_up(Keys.COMMAND).perform()
            else:
                # Ctrl + Click
                actions.key_down(Keys.CONTROL).click(element).key_up(Keys.CONTROL).perform()
        else:
            actions.click(element).perform()
~~~

动作链失败后原函数会滚动再试，最后用 JS 降级。那些异常分支不会改变本例“取自己的 XPath、点第一个结果”的定位主线。

#### 23.2 场景二：反复点“下一页”，循环点击单个元素

**当前场景**：学科详情中有分页表格。先采集第1页，再点“下一页”；采集第2页，再点“下一页”，直到满足停止条件。这里是**循环点击单个元素**，父循环 `loopType=0`：每轮都找当前页的同一个“下一页”位置。

~~~text
第1轮：采第1页 → 点第1页的“下一页”按钮，index=0
第2轮：采第2页 → 点第2页的“下一页”按钮，index=0
第3轮：采第3页 → 点第3页的“下一页”按钮，index=0
~~~

本例使用 `221.json` 中的 `graph[6]` 父循环和 `graph[7]` 点击孩子。页码在变化，点击目标的定位规则不变。

**从文件读取的参数示例**：[221.json](../../ElectronJS/tasks/221.json) → `graph[6].parameters`（父循环，只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 0,
  "xpath": "//*[contains(@class, \"ant-pagination-next\")]/a[1]",
  "iframe": false,
  "exitCount": 0
}
~~~

**从文件读取的参数示例**：[221.json](../../ElectronJS/tasks/221.json) → `graph[7].parameters`（点击孩子，只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": true,
  "xpath": "",
  "iframe": false,
  "clickWay": 0
}
~~~

**大致流程**：每轮定位当前页面的“下一页”这一个元素 → 顺序执行孩子 `[4,7]`，先采当前页、再点击下一页 → 留在翻页后的页面继续循环 → 根据页面变化、元素是否存在和退出配置停止。每轮传给点击节点的索引都是 `0`。

**本例先用 `find_element()` 找到当前页的“下一页”元素，再通过 `executeNode(i, element, xpath, 0)` 执行循环中的孩子节点：孩子4采集当前页，孩子7执行点击。先找元素，再执行操作；找到“下一页”元素本身并不会立即点击。**

**循环这一块**：原单个元素分支每轮用 `find_element()`，没有“遍历多个目标元素”的 `elements` 列表。这里只摘循环、定位、孩子调用和次数退出；页面内容不变判断等省略：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：loopType=0 单个元素循环`。

~~~python
count = 0  # 执行次数
# ……（省略其他原代码）
while True:  # do while循环
    if self.shutdown_event.is_set():
        break
    try:
        finished = False
        # ……（省略其他原代码）
        xpath = replace_field_values(
            node["parameters"]["xpath"], self.outputParameters, self)
        # self.recordLog("循环元素|Loop element:", xpath)
        element = self.browser.find_element(
            By.XPATH, xpath, iframe=node["parameters"]["iframe"])  # ⭐️⭐️⭐️这是单元素父循环，每轮先找到当前页的下一页元素；还没有点击
        for i in node["sequence"]:  # 挨个执行操作
            self.executeNode(
                i, element, xpath, 0)  # ⭐️⭐️⭐️当前下一页元素已找到，这里依次执行孩子4采集当前页、孩子7点击下一页；索引固定传 0
    # ……（省略其他原代码）
    except NoSuchElementException:
        # except:
        self.print_and_log("Single loop element not found: ",
                           xpath)
        self.print_and_log("找不到要循环的单个元素: ", xpath)
        # ……（省略其他原代码）
        break  # 如果找不到元素，退出循环
    # ……（省略其他原代码）
    count = count + 1
    self.print_and_log("Page: ", count)
    # self.print_and_log(node["parameters"]["exitCount"], "-------")
    if node["parameters"]["exitCount"] == count:  # 如果达到设置的退出循环条件的话
        break
~~~

关键是 `self.executeNode(i, element, xpath, 0)` 的最后一个参数始终为 `0`。`count` 统计执行轮数，不用于选择第几个链接。本例 `exitCount=0`，不按固定次数退出；原代码还会检测页面内容变化、找不到元素等停止条件。

**点击这一块**：`useLoop=true` 且孩子 `xpath=""`，所以 `path=clickPath`，沿用“下一页”的路径。原 `clickElement()` 统一用 `find_elements()` 返回列表，再取 `elements[index]`：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `clickElement()：沿用父路径、选出单个点击目标`，第 1700–1702、1714–1716 行。

~~~python
elif param["useLoop"]:  # 使用循环的情况下，传入的clickPath就是实际的xpath
    if xpath == "":
        path = clickPath
# ……（省略其他原代码）
elements = self.browser.find_elements(
    By.XPATH, path, iframe=param["iframe"])
element = elements[index]  # ⭐️⭐️⭐️这里在点击函数内按 index 选出本次点击目标；父容器已传入定位上下文，此句还没有执行点击
~~~

**既然本例 `index=0`，为什么不直接用 `find_element()`？**

因为 `clickElement()` 是多个场景共用的点击函数，传入的 `index` 并不总是 `0`：

| 具体场景 | 点击函数中的 index | 实际选择 |
| --- | --- | --- |
| 23.2：反复点“下一页” | 每轮都是 `0` | 当前页的下一页按钮 |
| 23.3：依次点列表中的每个链接 | 依次为 `0、1、2…` | 第一项、第二项、第三项…… |
| 23.4：点击当前块内的子链接 | 先将块位置写入 XPath，再将局部索引设为 `0` | 已限定到当前块的第一个匹配结果 |

如果只考虑本节“下一页”这一种场景，并且能找到匹配元素，直接 `find_element()` 取得的目标与 `find_elements()` 后取 `elements[0]` 相同。但公共函数还要处理列表循环的第二、第三个入口；对同一父路径直接调用 `find_element()`，每次都只会取第一个匹配结果，无法按传入的索引切换目标。因此原版统一采用“查找匹配列表 → 按 `index` 选出一个元素”的写法，随后只点击选中的那个 `element`。

原点击函数没有直接点击父循环传来的 `loopElement`，而是根据路径重新定位。这里的 `elements` 是点击函数内部的查找结果列表；即使 XPath 只匹配一个元素，`find_elements()` 也返回列表。例如当前页只有一个“下一页”按钮时：

~~~text
父循环：element = 当前页的下一页按钮，传入 index=0
点击函数：elements = [当前页的下一页按钮]
选中目标：element = elements[0]
~~~

随后原方法创建动作链并点击这个 `element`。本例没有 `newTab`，缺省为 `0`，对应以下两句原代码（省略两句之间的新标签页判断分支）：

~~~python
actions = ActionChains(self.browser)  # 实例化一个action对象
# ……（省略 newTab 判断分支）
actions.click(element).perform()
~~~

下一轮仍按同一 XPath 重新找翻页后的“下一页”按钮，再点击一个元素；不会把 `index` 加成 `1、2、3`。单个元素循环也不走列表循环轮末的 `handleHistory()` 恢复，否则翻页后又退回原页，就无法继续采下一页。

#### 23.3 场景三：逐个进入学科详情，循环点击每个链接

**当前场景**：学科排名列表上有多个学科入口。需要进入第一项详情，处理完返回列表；再进入第二项详情，直到处理完各项。这里是**循环点击每个链接对应的元素**，父循环 `loopType=1`，每轮换一个目标。原任务的父 XPath 定位链接内的 `span[2]`，点击这个文字元素触发对应链接。

~~~text
第一轮：列表项A → 点击A → 处理A的详情 → 回到列表，index=0
第二轮：列表项B → 点击B → 处理B的详情 → 回到列表，index=1
第三轮：列表项C → 点击C → 处理C的详情 → 回到列表，index=2
~~~

A、B、C 表示按原 XPath 顺序匹配到的入口，用于说明循环顺序。本例和 23.2 都来自 `221.json`：外层逐项进入详情，详情里再循环点“下一页”，因此文件中同时存在两种父循环。

**从文件读取的参数示例**：[221.json](../../ElectronJS/tasks/221.json) → `graph[2].parameters`（父循环，只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 1,
  "xpath": "/html/body/div[1]/div[1]/div[1]/div[2]/div[2]/div[1]/div/div[2]/div/a[1]/span[2]",
  "iframe": false
}
~~~

**从文件读取的参数示例**：[221.json](../../ElectronJS/tasks/221.json) → `graph[3].parameters`（点击孩子，只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": true,
  "xpath": "",
  "iframe": false,
  "clickWay": 0,
  "newTab": 1
}
~~~

**大致流程**：父循环找学科入口列表 → `index=0` 开始逐项处理 → 调点击孩子3，沿用列表路径和当前索引 → 执行详情分页孩子6（即 23.2）→ `handleHistory()` 恢复到入口列表 → `index` 加一，处理下一项。

**本例先用 `find_elements()` 找到整组学科入口，再用 `element = elements[index]` 取出本轮入口，然后调用 `executeNode(i, element, xpath, index)` 执行孩子节点：孩子3点击当前入口，孩子6处理其详情分页。完成这一轮后，再换下一个 `element`。**

**循环这一块**：这时才需要 `elements` 保存整组入口。以下保留原源码的列表定位、当前项选择、失效重取、孩子调用和轮末恢复，省略停止与跳过等分支：

**先认清恢复参数 `thisHandle`：它保存“进入本次父循环时，WebDriver正在控制哪个标签页”的句柄，也就是这个标签页的字符串标识。** 本例从学科列表页进入循环，因此它记住的是列表标签页；切到详情新标签页后，这个保存值仍然指向原列表。它来自循环入口的赋值，不是当前链接元素，也不是列表索引，详细定义与状态对照见[第24.5节](#window-handle)。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：loopType=1 列表循环`。

~~~python
xpath = replace_field_values(
    node["parameters"]["xpath"], self.outputParameters, self)
elements = self.browser.find_elements(By.XPATH,
                                      xpath, iframe=node["parameters"]["iframe"])
# ……（省略其他原代码）
index = 0
# ……（省略其他原代码）
while index < len(elements):
    # ……（省略其他原代码）
    try:
        element = elements[index]  # ⭐️⭐️⭐️注意这里在 parent（父元素）循环中，先取出本轮的当前学科入口元素；具体操作随后由 executeNode 执行
        element_text = element.text
    except StaleElementReferenceException: # 如果元素已经失效，重试
        self.print_and_log("元素已失效，重新获取元素|Element has expired, reacquiring element")
        elements = self.browser.find_elements(By.XPATH,
                                              xpath, iframe=node["parameters"]["iframe"])
        element = elements[index]  # ⭐️⭐️⭐️元素失效重取后，仍按 index 选出当前学科入口元素；具体操作随后由 executeNode 执行
    for i in node["sequence"]:  # 挨个顺序执行循环里所有的操作
        self.executeNode(i, element,
                         xpath, index)  # ⭐️⭐️⭐️当前学科入口已选好，这里执行孩子3点击该入口，再执行孩子6处理详情分页
    # ……（省略其他原代码）
    index, elements = self.handleHistory(node, xpath, thisHandle, thisHistoryURL, thisHistoryLength, index, elements=elements)
    # ……（省略其他原代码）
    index = index + 1
~~~

**点击这一块**：孩子 `useLoop=true`、`xpath=""`，所以重新按父路径查找，保留本轮 `index`。例如第二轮父循环传来 `index=1`，点击函数取 `elements[1]`，就是第二个入口。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `clickElement()：当前列表项定位与新标签页点击`。

~~~python
elif param["useLoop"]:  # 使用循环的情况下，传入的clickPath就是实际的xpath
    if xpath == "":
        path = clickPath
# ……（省略其他原代码）
elements = self.browser.find_elements(
    By.XPATH, path, iframe=param["iframe"])
element = elements[index]  # ⭐️⭐️⭐️这里在点击函数内按 index 选出本次点击目标；父容器已传入定位上下文，此句还没有执行点击
~~~

本例 `newTab=1`，原点击分支用 Ctrl（Mac 为 Command）配合点击，尝试在新标签页打开当前入口：

~~~python
elif click_way == 0:  # 用selenium的点击方法
    try:
        actions = ActionChains(self.browser)  # 实例化一个action对象
        if newTab == 1:  # 在新标签页打开
            if sys.platform == "darwin":  # Mac
                actions.key_down(Keys.COMMAND).click(element).key_up(Keys.COMMAND).perform()
            else:
                # Ctrl + Click
                actions.key_down(Keys.CONTROL).click(element).key_up(Keys.CONTROL).perform()
        else:
            actions.click(element).perform()
~~~

点击函数没有循环点击整个 `elements`，每次只对选出的 `element` 执行一次动作。决定接下来处理B、C的是父循环的 `index = index + 1`。新标签页切换和轮末历史恢复见第24节。

#### 23.4 场景四：逐个点击分类块中的第一个链接

**当前场景**：京东首页的分类菜单有多个分类块，每个块里包含链接。现在逐块处理：第一轮点块A里的第一个链接，第二轮点块B里的第一个链接。这里是**循环遍历每个块**，父循环 `loopType=1`；点击目标是当前块内的一个子元素。

~~~text
第一轮：分类块A → 点击 A/a[1]
第二轮：分类块B → 点击 B/a[1]
第三轮：分类块C → 点击 C/a[1]
~~~

A、B、C 只是为了推演顺序而给匹配到的分类块起的代号，实际定位以以下原任务参数为准。

**从文件读取的参数示例**：[174.json](../../ElectronJS/tasks/174.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 1,
  "xpath": "/html/body/div[5]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div"
}
~~~

**从文件读取的参数示例**：[174.json](../../ElectronJS/tasks/174.json) → `graph[4].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": true,
  "xpath": "/a[1]",
  "iframe": false,
  "clickWay": 0
}
~~~

与 23.3 直接点击循环项相比，这里父路径选的是分类块，孩子 `xpath="/a[1]"` 才选中要点击的链接。循环类型仍是 `loopType=1`，每轮都点击当前块里的一个链接。

**大致流程**：父循环遍历块并传 index → 点击函数将当前块的位置写入 XPath，再追加 `/a[1]` → 点击函数内查找索引设为 0，取查找结果中的一个子元素 → 本轮结束后恢复页面，父循环继续下一块。

**本例先找到整组分类块，并取出本轮的分类块 `element`；再调用 `executeNode()` 执行块内配置的操作。执行到点击孩子4时，点击方法才根据当前块的位置和 `/a[1]` 定位子链接并点击。**

**循环这一块**与 23.3 同样使用 `loopType=1`。区别是 `elements` 装的是分类块；`174.json` 的孩子顺序为 `[3,4,5]`，依次提取当前块文字、点击块内链接、提取点击后的数据。以下是原列表循环中选当前块、调用孩子和推进索引的核心：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()`（定位整组块和失效重取同 23.3，此处只摘本轮调用）。

~~~python
try:
    element = elements[index]  # ⭐️⭐️⭐️注意这里在 parent（父元素）循环中，先取出本轮的当前分类块父元素；具体操作随后由 executeNode 执行
    element_text = element.text
except StaleElementReferenceException: # 如果元素已经失效，重试
    self.print_and_log("元素已失效，重新获取元素|Element has expired, reacquiring element")
    elements = self.browser.find_elements(By.XPATH,
                                          xpath, iframe=node["parameters"]["iframe"])
    element = elements[index]  # ⭐️⭐️⭐️元素失效重取后，仍按 index 选出当前分类块父元素；具体操作随后由 executeNode 执行
for i in node["sequence"]:  # 挨个顺序执行循环里所有的操作
    self.executeNode(i, element,
                     xpath, index)  # ⭐️⭐️⭐️当前分类块已选好，这里依次执行孩子3采块内文字、孩子4点击子链接、孩子5采点击后的数据
# ……（省略其他原代码）
index, elements = self.handleHistory(node, xpath, thisHandle, thisHistoryURL, thisHistoryLength, index, elements=elements)
# ……（省略其他原代码）
index = index + 1
~~~

**点击这一块**用非空后缀分支。先将父循环位置限定为 [index+1]，再接 /a[1]；完整路径已经选定当前块，所以函数内索引重置为 0：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `clickElement()：当前块的子路径与点击`，第 1700–1716、1746–1756 行。

~~~python
elif param["useLoop"]:  # 使用循环的情况下，传入的clickPath就是实际的xpath
    if xpath == "":
        path = clickPath
    else:
        path = "(" + clickPath + ")" + \
               "[" + str(index + 1) + "]" + \
               xpath
        index = 0  # 如果是相对循环内元素的点击，在定位到元素后，index应该重置为0
# ……（省略其他原代码）
elements = self.browser.find_elements(
    By.XPATH, path, iframe=param["iframe"])
element = elements[index]  # ⭐️⭐️⭐️这里在点击函数内按 index 选出本次点击目标；父容器已传入定位上下文，此句还没有执行点击
~~~

本例没有 `newTab`，缺省为 `0`。定位后仍执行原动作链的普通点击分支：

~~~python
actions = ActionChains(self.browser)  # 实例化一个action对象
# ……（省略 newTab 判断分支）
actions.click(element).perform()
~~~

这里有两个函数各自的 `elements`，需要分开看。用 `P` 表示真实父路径，假设有三个块 A、B、C，每块有一个直属的 `a`：

| 所在函数 | 查找路径 | 查找结果示意 | 本轮实际使用 |
| --- | --- | --- | --- |
| 父 `loopExecute()` | `P` | `[块A, 块B, 块C]` | 第二轮取 `elements[1]`，即块B |
| 子 `clickElement()` | `(P)[2]/a[1]` | `[块B中的链接]` | 局部索引设为 `0`，取 `elements[0]` 点击 |

所以点击函数里的 `elements` 并不表示又遍历一组链接；它统一用 `find_elements()` 查找，再选中其中一个。这个路径若匹配一个链接，结果就是只含一个元素的列表。`/a[1]` 选取当前块下的第一个直属 `a`；没有匹配结果时会进入原代码的找不到元素处理。

外层 `index=0/1/2` 时分别查 `(P)[1]/a[1]`、`(P)[2]/a[1]`、`(P)[3]/a[1]`。点击函数内的 `index=0` 是局部查找索引，父 `loopExecute()` 的索引仍递增。

本例版本为 0.3.6，保留该相对后缀；≤0.3.5 的旧任务循环点击会在预处理中清空孩子 `xpath`。是否换窗口仍按实际点击结果处理。

<a id="handle-history"></a>

### 24. handleHistory 专题：先看两种“点进详情后，怎样回到列表”的例子

**当前例子：列表页上有“详情A”“详情B”两个链接，要先点A、采A的详情，再点B、采B的详情。这里是循环点击每个链接，每轮换一个目标。** A、B 是为了手算浏览器状态起的代号，后面再对照仓库中的真实任务。

现在只考虑一个问题：**采完A时，浏览器正在A的详情页面，下一轮怎样回到原来的列表，找到并点击B？** 先用两种实际浏览过程说明，后半节再放参数和代码。

#### 24.1 情况一：点击A后弹出新标签页

假设最开始只有一个标签页，里面显示列表。点击A时，网站另外打开一个标签页显示A的详情，原来的列表页仍然保留。

| 步骤 | 浏览器里有什么 | 程序当前在哪一页 | 这一步做什么 |
| --- | --- | --- | --- |
| 1. 开始 | 列表页 | 列表页 | 记住列表页的标签页身份和网址，再找到当前链接A |
| 2. 点A | 列表页、A详情页 | 程序切到A详情页 | 发现出现了新标签页后，把操作目标切过去 |
| 3. 采A | 列表页、A详情页 | A详情页 | 执行本轮剩余的详情采集；详情中有分页时，先完成里面的循环 |
| 4. 采完A | 列表页、A详情页 | 从A详情页回到列表页 | 关闭已经用完的A详情标签页，再切回原列表标签页 |
| 5. 点B | 列表页、B详情页 | 程序切到B详情页 | 父循环改取下一个链接B，打开它并采集 |
| 6. 采完B | 列表页 | 列表页 | 关闭B详情标签页，回到列表，继续下一项或结束 |

**这种情况的处理是“切到新详情标签页 → 采详情 → 关闭详情标签页 → 切回原列表页”。列表一直在另一个标签页里，不需要在详情标签页里按后退来找它。**

如果原列表页没有重载，其中的链接元素引用通常还能使用；下一轮仍会按原循环逻辑检查并取出B。

#### 24.2 情况二：点击A后没有新标签页，当前页面直接跳转

这次浏览器始终只有一个标签页。点击A后，原来的列表内容被详情内容替换：地址从列表网址变成A详情网址。采完A时，如果直接查找B，当前页面里已经没有原来的列表，因此必须先返回列表。

| 步骤 | 标签页数量 | 当前显示的页面 | 这一步做什么 |
| --- | --- | --- | --- |
| 1. 开始 | 1个 | 列表页 | 记住当前标签页、列表网址和此时的历史状态，再找到链接A |
| 2. 点A | 仍为1个 | A详情页 | 同一个标签页跳转，普通导航会增加历史记录 |
| 3. 采A | 仍为1个 | A详情页 | 用详情页自己的字段路径完成采集 |
| 4. 采完A | 仍为1个 | 返回列表页 | 沿浏览器历史退回出发时的列表，等待恢复 |
| 5. 准备B | 仍为1个 | 列表页 | 检查原链接元素引用是否仍有效；失效时重新查找列表，再取B |
| 6. 点B、采B | 仍为1个 | B详情页 | 处理B后，再沿历史回到列表 |

**这种情况的处理是“当前页进入详情 → 采详情 → 在同一个标签页中沿历史退回列表 → 检查或重取链接 → 点击下一项”。不能关闭这个标签页，否则连原列表所在的标签页也关掉了。**

用一条普通导航的历史记录手算：进入循环时已有“首页 → 搜索页 → 列表页”3条记录；点击A后增加“A详情页”，变成4条。原执行器用出发时记录的长度3与点击后保存的长度4计算差值，得到负1，尝试后退一步。采集完成后，从详情页执行函数返回，并不等于网页已经后退；需要专门执行浏览器恢复。

#### 24.3 先分清：标签页、历史记录和元素引用各管什么

| 要记住的东西 | 在上面例子中的作用 |
| --- | --- |
| 原列表所在的标签页 | 新标签页场景中，知道关完详情后要切回哪一页 |
| 原列表网址与历史状态 | 同页跳转场景中，判断怎样沿历史回到出发页 |
| 原来找到的链接元素引用 | 返回后继续处理下一项；如果列表重建，旧引用可能失效，需要重新定位 |

**浏览器回到同一个列表网址，不代表原来的链接元素对象一定还能用。** 同页导航后，网页可能重新创建了整棵页面结构，原来指向A、B的元素引用就可能过期。原版循环先尝试读取当前项，发现失效后才重查列表；并不是每次恢复都无条件重新查找全部元素。

两种情况共同遵守同一顺序：**父循环先找到本轮链接 → 执行点击与本轮全部详情操作 → 恢复列表 → 再处理下一个链接。** 这与反复点“下一页”的单个元素循环不同；翻页循环需要留在下一页，不在每轮末尾退回原页。

#### 24.4 再看真实任务参数：两种情况分别对应什么文件

**新标签页例子**来自 [221.json](../../ElectronJS/tasks/221.json)。外层 `graph[2]` 是 `loopType=1` 的列表循环，`sequence=[3,6]`：先执行点击孩子3，再执行详情分页孩子6。前面的例子把详情内的这些操作统称为“采完本轮详情”，不改变任务原有的孩子顺序。

**从文件读取的参数示例**：[221.json](../../ElectronJS/tasks/221.json) → `graph[3].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": true,
  "xpath": "",
  "clickWay": 0,
  "newTab": 1,
  "wait": 2
}
~~~

`newTab=1` 让原点击分支尝试组合键点击；它还会在点击后等待。本轮真正走哪种恢复路径，仍以执行后的当前标签页状态为准。

**当前页跳转例子**来自 [循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json)。父循环 `graph[2].sequence=[3,4]`，先点击3，再执行详情采集4。

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 1,
  "xpath": "/html/body/div[2]/div[10]/div[2]/div[1]/table[1]/tbody[1]/tr/td[5]/a[1]/span[1]/div[1]",
  "historyWait": 2
}
~~~

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json) → `graph[3].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": true,
  "wait": 8
}
~~~

原文件没有 `newTab`，原点击方法缺省按0处理。`wait=8` 是点击后等待详情；`historyWait=2` 是沿历史回退后的等待。任务 JSON 的 `history/tabIndex` 属于设计时信息，恢复时使用下面代码在运行现场记录的状态。

#### 24.5 最后对照原版核心代码：记录起点、执行详情、恢复列表

以下只摘 [easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) 的核心执行语句；`⭐️⭐️⭐️` 为讲解注释，省略的原代码用注释标明。

**① 进入父循环，先记住出发点。** 原 `loopExecute()` 记录列表所在标签页、网址和历史长度。

<a id="window-handle"></a>

**`thisHandle` 是“本次循环开始时所在标签页的句柄”。句柄是 WebDriver 返回的字符串标识，用来识别一个窗口或标签页。** `thisHandle` 是作者起的局部变量名；`self.browser.current_window_handle` 才是读取当前操作目标句柄的 Selenium 属性。

在本节例子里，循环从列表页开始，因此保存的是原列表标签页的句柄。用“列表句柄”“详情句柄”代称实际的长字符串，逐步看它们的区别：

| 时刻 | 已保存的 thisHandle | 此刻的 current_window_handle | 说明 |
| --- | --- | --- | --- |
| 进入循环，当前控制列表页 | 列表句柄 | 列表句柄 | 把这次循环的出发标签页记下来 |
| 新标签页打开后，程序切到A详情 | 仍是列表句柄 | 详情句柄 | 当前操作目标变了，先前保存的字符串不会跟着变化 |
| 关闭详情并切回列表 | 仍是列表句柄 | 列表句柄 | 两者相等，说明当前又控制原来的标签页 |
| 另一种情况：同一标签页从列表跳到A详情 | 仍是列表句柄 | 仍是列表句柄 | 标签页没变，只有网址和页面内容变了，要靠历史处理返回 |

**所以比较 `current_window_handle != thisHandle`，判断的是“是否换了标签页”，不是“网址有没有变化”。同一标签页跳转到另一个网址，句柄仍然相同。** 句柄也不是 `0、1、2` 这样的标签页序号；JSON里的设计时 `tabIndex` 和运行时句柄是两种信息。

这个值在**每次调用 `loopExecute()` 的入口**记录，不是每处理一个链接就重新赋值。外层从列表进入时保存列表标签页；内层循环若在详情标签页中开始，就保存详情标签页。各次函数调用都有自己的局部 `thisHandle`，分别记住各自的出发点。

**下面第一句只是把当时的句柄保存下来，不会切换标签页。** 后面恢复时，原代码通过当前句柄与它比较，判断是否已回到本次循环的出发标签页。

~~~python
thisHandle = self.browser.current_window_handle  # 记录本次循环内的标签页的ID；⭐️⭐️⭐️保存本次循环的出发标签页，之后切换标签页时此值不会自动改变
try:
    thisHistoryLength = self.browser.execute_script(
        'return history.length')  # 记录本次循环内的history的length
except:
    thisHistoryLength = 0
self.history["index"] = thisHistoryLength
self.history["handle"] = thisHandle
thisHistoryURL = self.browser.current_url
~~~

**② 父循环逐项执行：先找到当前链接，再完成全部详情孩子，最后恢复。** 这里展示普通列表循环路径，停止、跳过等外围分支省略。

~~~python
xpath = replace_field_values(
    node["parameters"]["xpath"], self.outputParameters, self)
elements = self.browser.find_elements(By.XPATH,
                                      xpath, iframe=node["parameters"]["iframe"])
# ……（省略其他原代码）
index = 0
# ……（省略其他原代码）
while index < len(elements):
    # ……（省略其他原代码）
    try:
        element = elements[index]  # ⭐️⭐️⭐️先取出本轮父循环的当前链接元素，稍后再执行点击和详情操作
        element_text = element.text
    except StaleElementReferenceException: # 如果元素已经失效，重试
        self.print_and_log("元素已失效，重新获取元素|Element has expired, reacquiring element")
        elements = self.browser.find_elements(By.XPATH,
                                              xpath, iframe=node["parameters"]["iframe"])
        element = elements[index]  # ⭐️⭐️⭐️先取出本轮父循环的当前链接元素，稍后再执行点击和详情操作
    for i in node["sequence"]:  # 挨个顺序执行循环里所有的操作
        self.executeNode(i, element,
                         xpath, index)  # ⭐️⭐️⭐️这里执行本轮孩子：点击当前链接，再完成详情采集或详情内的嵌套循环
    # ……（省略其他原代码）
    index, elements = self.handleHistory(node, xpath, thisHandle, thisHistoryURL, thisHistoryLength, index, elements=elements)  # ⭐️⭐️⭐️孩子全部返回后才恢复列表
    # ……（省略其他原代码）
    index = index + 1  # ⭐️⭐️⭐️恢复处理完成后，再推进到下一个链接
~~~

`executeNode()` 返回后，浏览器可能仍在详情页。紧接着的 `handleHistory()` 才负责浏览器恢复；完成这一步后才让 `index` 加一。

**③ 新标签页的切入在点击方法末尾完成。** 原 `clickElement()` 比较点击前后的句柄数量；有变化时切到句柄列表最后一项，并更新当前历史所对应的句柄。

~~~python
if tempHandleNum != len(self.browser.window_handles):  # 如果有新标签页的行为发生
    self.browser.switch_to.window(
        self.browser.window_handles[-1])  # 跳转到新的标签页
    self.history["handle"] = self.browser.current_window_handle
~~~

原方法还会读取当前页的历史长度，保存到 `self.history["index"]`。新标签页情况下，保存的是详情标签页的历史；同页导航情况下，保存的是原标签页跳到详情后的历史。

**④ 对应情况一：本轮结束时，当前标签页不是出发的列表标签页，就关闭详情并切回。** 以下是原 `handleHistory()` 的窗口分支；在前面只有“列表+一个详情”的例子中，就是关闭A详情，再回到列表。

**为什么这里要 `while True`，而不是只关闭一次？因为一轮详情操作里，可能又打开了第二层标签页。** 例如：

1. 列表标签页记为L，进入本次循环时保存 `thisHandle=L`。
2. 点击链接A，新开详情标签页D，程序切到D。
3. 在详情里点击附件，又开附件标签页F，程序切到F。
4. 本轮详情与附件采集完成，要回到L，再处理列表中的链接B。

为了按原代码逐步手算，假定此时 `window_handles` 的排列为 `[L, D, F]`，当前控制的是F。原方法每关闭一页，就切到剩余句柄列表的最后一项：

| while轮次 | 关闭前控制谁 | 执行close后还剩谁 | 切到剩余最后一项 | 与thisHandle比较 |
| --- | --- | --- | --- | --- |
| 第1轮 | F：附件页 | `[L, D]` | D：详情页 | D不等于L，继续关闭 |
| 第2轮 | D：详情页 | `[L]` | L：原列表页 | L等于L，立即break |

**只关闭一次会停在D，仍未回到原列表；循环关闭到当前句柄等于 `thisHandle` 时就结束，L被保留下来。** 如果只开了D一个详情页，那么第1轮关闭D、切到L，马上break，只会关闭一次。

这里的L、D、F是句柄代号。示例按上述排列推演；原代码确实依赖剩余句柄的最后一项，相关顺序假设见第24.6节。

~~~python
try:
    changed_handle = self.browser.current_window_handle != thisHandle
except:  # 如果网页被意外关闭了的情况下
    self.browser.switch_to.window(
        self.browser.window_handles[-1])
    changed_handle = self.browser.window_handles[-1] != thisHandle
if changed_handle:  # 如果执行完一次循环之后标签页的位置发生了变化
    try:
        while True:  # 一直关闭窗口直到当前标签页
            self.browser.close()  # 关闭使用完的标签页
            self.browser.switch_to.window(
                self.browser.window_handles[-1])
            if self.browser.current_window_handle == thisHandle:
                break
    except Exception as e:
        self.print_and_log("关闭标签页发生错误：", e)
        self.print_and_log(
            "Error occurred while closing tab: ", e)
~~~

回到列表后，若 `self.history["handle"]` 仍指向刚关掉的详情页，下一条历史判断就不会拿详情页的长度去回退列表页；它还要求“保存历史的句柄等于当前句柄”。

**⑤ 对应情况二：标签页没换，但保存的历史长度与出发时不同，就计算差值回退。** 普通例子中 `thisHistoryLength=3`、`self.history["index"]=4`，差值为负1；原代码执行相应的浏览器历史移动，再等待 `historyWait`。

~~~python
if self.history["index"] != thisHistoryLength and self.history["handle"] == self.browser.current_window_handle:  # 如果执行完一次循环之后历史记录发生了变化，注意当前页面的判断
    difference = thisHistoryLength - self.history["index"]  # 计算历史记录变化差值
    self.browser.execute_script('history.go(' + str(difference) + ')')  # 回退历史记录
    # if node["parameters"]["historyWait"] > 2:  # 回退后要等待的时间
    time.sleep(node["parameters"]["historyWait"])
    # ……（省略其他原代码）
    try:
        self.browser.execute_script('window.stop()')
    except:
        pass
~~~

**把 `history.go(...)` 的数字和最终脚本直接展开看。** 以下是两个独立的普通导航例子：都从同一个标签页里的“首页 → 搜索页 → 列表页”开始，此时保存的历史长度为3；每次点击后，原 `clickElement()` 都更新当前保存的历史长度。

| 例子 | 出发时的thisHistoryLength | 详情操作后保存的self.history["index"] | difference怎么算 | 最终发送的JavaScript | 浏览器怎样移动 |
| --- | --- | --- | --- | --- | --- |
| 列表 → A详情 | 3 | 4 | `3 - 4 = -1` | `history.go(-1)` | 从第4条A详情退一步，回到第3条列表 |
| 列表 → A详情 → 附件页面，始终在同一个标签页 | 3 | 5 | `3 - 5 = -2` | `history.go(-2)` | 从第5条附件退两步，经过A详情，回到第3条列表 |

第二个例子的历史位置可以按下面读：

| 历史条目 | 页面 | 执行回退前后的位置 |
| --- | --- | --- |
| 第1条 | 首页 | |
| 第2条 | 搜索页 | |
| 第3条 | 列表页 | 执行后回到这里 |
| 第4条 | A详情页 | 后退时经过这里 |
| 第5条 | 附件页面 | 执行前在这里 |

以差值负2为例，`str(difference)` 得到字符串 `"-2"`；拼接 `'history.go(' + str(difference) + ')'` 后，脚本就是 `history.go(-2)`。`execute_script()` 把这段JavaScript交给浏览器执行，实际页面导航由浏览器完成。

**负数表示沿历史向后，正数表示向前；这里两个例子都是负数，所以发生回退。** 移动的是历史中的当前位置，历史条目总数不会因后退而自动从5减成3。上面的数字只对应“普通点击新增历史”的推演；复杂路由与旧前进历史的边界见第24.6节。

**⑥ 回到列表后，旧元素若失效，下一轮重查再取当前项。** 这是父列表循环的原分支，处理的是网页元素引用，不是历史记录本身。

~~~python
try:
    element = elements[index]  # ⭐️⭐️⭐️仍取本轮 index 对应的链接；失效时先重查列表，再取同一位置
    element_text = element.text
except StaleElementReferenceException: # 如果元素已经失效，重试
    self.print_and_log("元素已失效，重新获取元素|Element has expired, reacquiring element")
    elements = self.browser.find_elements(By.XPATH,
                                          xpath, iframe=node["parameters"]["iframe"])
    element = elements[index]  # ⭐️⭐️⭐️仍取本轮 index 对应的链接；失效时先重查列表，再取同一位置
~~~

如果原列表没有重载，旧元素仍有效，就继续使用；如果同页返回造成引用失效，则重取列表后按当前 `index` 选择下一项。

#### 24.6 按原实现理解边界，不把两种例子扩大成所有页面

- **没开新标签页，也不一定需要后退。** 如果点击只是打开模态框或展开同页内容，没有新增历史，原方法可能不自动恢复；应在本轮采集后安排关闭或返回操作。只用 `replaceState` 换网址而不增加历史，也不能指望它自动重新打开列表网址。
- **历史长度不是当前历史指针。** 上面3到4的例子用于说明普通新增导航；后退后历史长度通常仍是4。旧的前进历史、重定向或复杂前端路由，可能使“长度差就是后退步数”的假设不成立。
- **原代码按实际句柄处理。** `newTab=0` 也可能因网站自身行为打开新标签页；`newTab=1` 也可能没有打开。原切换、关闭策略使用句柄列表最后一项，没有计算新旧句柄集合差；多个无关窗口等情况要按实际源码判断。
- **恢复页面和重取元素是相邻的两个环节。** `handleHistory()` 只有在特定的 URL 修正分支才重新查找元素；普通返回后，通常由下一轮的失效检查决定是否重取。重取仍按列表位置推进，列表排序或条目数量变化时可能错位；固定的回退等待时间也不等于确认列表已经就绪。

### 25. 提取场景一：collectSingle，定位一个字段再读值

**当前例子：进入芜湖房地产交易信息网的一条楼栋详情，只提取页面上的“楼/幢”文字。** 详情页有楼栋信息，本节先选其中一个文本元素，不处理整张列表。任务保存的样例主体文字是 `楼/幢:6`，要写入的字段叫“参数1_文本”。

| 页面上有什么 | 本次提取什么 | 形成什么记录 |
| --- | --- | --- |
| 一条楼栋详情，其中显示“楼/幢:6” | 这个元素的普通文本 | 当前详情的一条记录，“参数1_文本”保存该文字 |

这里用样例的主要文字说明内容；JSON 的 `exampleValues` 原值还含换行和制表符，实际结果按页面取值，不在讲解中额外改写提取规则。以下先看这一个字段的真实配置，再看定位和取值源码。

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json) → `graph[4].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数1_文本",
  "nodeType": 0,
  "contentType": 0,
  "relative": false,
  "relativeXPath": "/html/body/div[2]/div[2]/div[2]/div[2]/div[1]",
  "default": "",
  "downloadPic": 0
}
~~~

**大致流程**：采集前：可按 clear 清字段、取当前 HTML → 按 optimizable 选原提取路径 → 定位并读各字段 → 按 name 更新字典 → 字段循环结束后按配置组装行，随后调用 saveData。

本例 relative=false，详情字段使用自己的 XPath。先看通用 Selenium 路径中的定位和取值：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：非相对字段定位`，第 2206–2208 行。

~~~python
else:
    element = self.browser.find_element(
        By.XPATH, relativeXPath, iframe=p["iframe"])
~~~

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：读取字段、赋值与生成行`，第 2250–2252、2278–2284 行。

~~~python
            self.execute_code(
                2, p["beforeJS"], p["beforeJSWaitTime"], element, iframe=p["iframe"])  # 执行前置js
            content = self.get_content(p, element)
        # ……（省略其他原代码）
        self.outputParameters[p["name"]] = content
        self.execute_code(
            2, p["afterJS"], p["afterJSWaitTime"], element, iframe=p["iframe"])  # 执行后置JS
if param["recordASField"] > 0 and param["newLine"]:
    line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
    self.OUTPUT.append(line)
~~~

contentType=0、nodeType=0 由 get_content 读普通文本，保存到“参数1_文本”。本例也可能满足原 lxml 优化条件；这里解释通用路径，路径选择的核心见第 25.4、27 节。字段字典到文件的关系见[第 19.1 节](#output-parameters)。

#### 25.1 场景二：collectMultiNoPattern，不同位置组成同一行

**当前例子：在京东首页，一次采集分散在不同位置的内容，合成同一条记录。** 本节先看原任务的前两个字段：一个在左侧分类区域，另一个在首页上方包含购物车、搜索推荐等文字的区域。两处各有自己的 XPath，要分别定位和读取。

| 原任务字段 | 页面内容与保存的样例 | 本次要取的内容 |
| --- | --- | --- |
| 参数1_文本 | 分类区域，样例为 `/手机/数码` | 该区域的文本 |
| 参数2_文本 | 另一处容器，样例包含“我的购物车”“平板電腦”“领券中心今日推荐”等 | 该容器的整段文本，包含其实际空白 |

**这一例是“多个位置 → 多个字段 → 同一行”，不是每找到一个字段就单独输出一行。** 原任务还配置了其他字段；下面只摘这两个字段来说明同一次采集中的处理顺序。

**从文件读取的参数示例**：[108.json](../../ElectronJS/tasks/108.json) → `graph[3].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数1_文本",
  "nodeType": 0,
  "contentType": 0,
  "relative": false,
  "relativeXPath": "/html/body/div[5]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]",
  "default": "",
  "downloadPic": 0
}
~~~

**从文件读取的参数示例**：[108.json](../../ElectronJS/tasks/108.json) → `graph[3].parameters.params[1]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数2_文本",
  "nodeType": 0,
  "contentType": 0,
  "relative": false,
  "relativeXPath": "/html/body/div[4]/div[1]",
  "default": "",
  "downloadPic": 0
}
~~~

**大致流程**：进入同一个字段 for → 按每个字段自己的 XPath 找元素并读值 → 逐个更新字段名 → 全部字段处理完才生成一条记录。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：多个非相对字段的核心`，第 2180–2184、2206–2208、2250–2252、2278–2284 行。

~~~python
for p in param["params"]:
    if not p["optimizable"]:
        content = ""
        relativeXPath = replace_field_values(
            p["relativeXPath"], self.outputParameters, self)
                # ……（省略其他原代码）
                else:
                    element = self.browser.find_element(
                        By.XPATH, relativeXPath, iframe=p["iframe"])
            # ……（省略其他原代码）
            self.execute_code(
                2, p["beforeJS"], p["beforeJSWaitTime"], element, iframe=p["iframe"])  # 执行前置js
            content = self.get_content(p, element)
        # ……（省略其他原代码）
        self.outputParameters[p["name"]] = content
        self.execute_code(
            2, p["afterJS"], p["afterJSWaitTime"], element, iframe=p["iframe"])  # 执行后置JS
if param["recordASField"] > 0 and param["newLine"]:
    line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
    self.OUTPUT.append(line)
~~~

108 的两个示例字段都 relative=false，分别读不同页面位置。字段 for 中先更新“参数1_文本”，再更新“参数2_文本”；new_line 在字段 for 之后，所以它们组成同一行。原任务还含其他字段，也由同一循环处理，不能只定位一次后给全部字段复用一个 element。

#### 25.2 场景三：提取全部同类元素，空相对路径指当前项

**当前例子：协会网站的企业列表上有一排企业链接，要把每家企业的名称和链接地址采下来，每个链接形成一条记录。** 本例直接在列表页读取当前 `a` 元素，不需要点击进入企业详情。

任务保存的前两组样例内容是：

| 列表顺序 | 要提取的链接文字 | 要提取的 href |
| --- | --- | --- |
| 第一项 | 华建建设集团有限公司 | https://www.jx-jx.net/articleview/574.html |
| 第二项 | 嘉兴市明洲电力建设有限公司 | https://www.jx-jx.net/articleview/573.html |

**先找到整组链接，每轮取一个当前链接；再调用 `executeNode()` 执行采集孩子，从同一个链接分别读取文字和地址，组成这一行，然后处理下一个链接。** 两个字段都直接指向当前 `a`，所以相对 XPath 为空。

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[7].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "xpath": "/html/body/div[1]/div[5]/div[1]/div[1]/div[2]/ul[1]/li/a[1]",
  "loopType": 1
}
~~~

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[8].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数1_链接文本",
  "nodeType": 1,
  "contentType": 0,
  "relative": true,
  "relativeXPath": "",
  "default": "",
  "downloadPic": 0
}
~~~

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[8].parameters.params[1]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数2_链接地址",
  "nodeType": 2,
  "contentType": 0,
  "relative": true,
  "relativeXPath": "",
  "default": "",
  "downloadPic": 0
}
~~~

**大致流程**：父列表循环将当前 a 传给采集孩子 → 空相对路径直接使用该 loopElement → 两个字段分别读文字/href → 组装当前链接的一行 → 处理下一条。

**这里的 `element` 是父循环已经找到的“当前企业链接”的 Selenium 元素对象（`WebElement`），不是链接文字，也不是链接地址字符串。它来自先前的 `elements = find_elements(...)` 和本轮的 `element = elements[index]`。**

先把父循环的上半段接上，才能看清它从哪里来。此时 `node` 是父循环 `graph[7]`，`xpath` 是上面 JSON 中匹配整组企业链接的路径：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：查找列表、取出当前元素、执行孩子`（省略停止、跳过和轮末恢复等分支，保留原代码）。

~~~python
xpath = replace_field_values(
    node["parameters"]["xpath"], self.outputParameters, self)
elements = self.browser.find_elements(By.XPATH,
                                      xpath, iframe=node["parameters"]["iframe"])
# ……（省略其他原代码）
index = 0
# ……（省略其他原代码）
while index < len(elements):
    # ……（省略其他原代码）
    try:
        element = elements[index]  # ⭐️⭐️⭐️注意这里在 parent（父元素）循环中，先取出本轮的当前企业链接父元素 a；具体操作随后由 executeNode 执行
        element_text = element.text
    except StaleElementReferenceException: # 如果元素已经失效，重试
        self.print_and_log("元素已失效，重新获取元素|Element has expired, reacquiring element")
        elements = self.browser.find_elements(By.XPATH,
                                              xpath, iframe=node["parameters"]["iframe"])
        element = elements[index]  # ⭐️⭐️⭐️元素失效重取后，仍按 index 选出当前企业链接父元素 a；具体操作随后由 executeNode 执行
    for i in node["sequence"]:  # 挨个顺序执行循环里所有的操作
        self.executeNode(i, element,
                         xpath, index)  # ⭐️⭐️⭐️当前企业链接父元素已选好，这里执行采集孩子8，提取该链接的文字和 href
    # ……（省略其他原代码）
    index = index + 1
~~~

**外层 `while` 遍历的是网页元素，先用 `elements[index]` 选出本轮的 `element`；内层 `for i in node["sequence"]` 遍历的是配置好的操作节点，再调用 `executeNode()` 执行这些操作。内层 `for` 本身不负责查找元素。**

| 变量 | 在本例中具体是什么 |
| --- | --- |
| `elements` | 父 XPath 匹配到的整组企业链接元素对象 |
| `index` | 本轮处理第几个链接，从 `0` 开始 |
| `element = elements[index]` | 第一轮是“华建建设集团有限公司”对应的 `a` 元素；第二轮是“嘉兴市明洲电力建设有限公司”对应的 `a` 元素 |
| `node["sequence"]` | 父循环的孩子节点编号列表，本例为 `[8]` |
| `i` | 本轮要执行的操作节点编号，本例为 `8`，即采集节点 |

`executeNode(8, element, xpath, index)` 把当前链接作为第二个实参传入。先看原源码的函数定义行，就能看到它在函数内叫什么：

~~~python
def executeNode(self, nodeId, loopValue="", loopPath="", index=0):
~~~

忽略 Python 自动传入的 `self`，第二个实参 `element` 对应第二个形参 `loopValue`。因此在这次调用里，`loopValue` 就是父循环选中的当前链接元素。随后按 `option=3` 把它继续传给 `getData()`：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `executeNode()：把当前元素交给采集方法`，第 1011–1016 行。

~~~python
elif node["option"] == 3:  # 提取数据
    # 针对提取数据操作，设置操作开始的步骤，用于不小心关闭后的恢复的增量采集
    if self.totalSteps >= self.startSteps:
        self.getData(node["parameters"], loopValue, node["isInLoop"],
                    parentPath=loopPath, index=index)
        self.saveData()
~~~

**`loopElement` 就是 `getData()` 的形参，来源在函数定义这一行，而不是在函数体里另外查找或创建：**

~~~python
def getData(self, param, loopElement, isInLoop=True, parentPath="", index=0):
~~~

把刚才的调用与定义按位置对齐（`self` 自动传入）：

| 调用 `getData()` 时传入的值 | `getData()` 接收它的形参 | 本例含义 |
| --- | --- | --- |
| `node["parameters"]` | `param` | 采集节点8的字段配置 |
| `loopValue` | `loopElement` | 父循环选中的当前企业链接元素 |
| `node["isInLoop"]` | `isInLoop` | 该采集节点是否位于循环中 |
| `parentPath=loopPath` | `parentPath` | 父循环的链接列表 XPath |
| `index=index` | `index` | 当前链接在列表中的位置 |

**所以看不到单独的 `loopElement = ...` 赋值语句：调用函数时，Python 已经把传入的 `loopValue` 绑定给形参 `loopElement`。** 第一轮它指向“华建建设集团有限公司”的 `a` 元素，第二轮指向“嘉兴市明洲电力建设有限公司”的 `a` 元素。

完整传递链是：**父循环的 `element` → `executeNode()` 的 `loopValue` → `getData()` 的 `loopElement`。** 下面的 `element = loopElement` 只是让采集方法的局部变量 `element` 指向这个已有对象，不会重新查找网页元素；随后才读取它的文字和 href。

**这里直接写 `element = loopElement`，是因为字段设置了 `relative=true`，并且 `relativeXPath=""`：空的相对路径表示“要提取的就是当前循环元素本身”，所以不需要二次查找。它不表示元素为空或没有找到元素。**

| 当前循环元素是什么 | 字段的相对 XPath | 接下来怎样取字段元素 |
| --- | --- | --- |
| 本节的企业链接 `a` | `""` | 直接令 `element = loopElement`，从这个 `a` 读取文字或 href |
| 第25.3节的商品块 | `/div[1]/div[1]/div[1]/a[1]` | 当前块还不是要取值的链接，需要沿子路径继续找到块内的 `a`，再读取文字或 href |

**所以判断顺序是：先确认字段使用相对定位，再判断相对路径是否为空；为空直接用当前项，非空继续定位字段元素。** 原源码中，非空路径不含 `//` 时用 `loopElement.find_element(...)` 查找子元素；含 `//` 时则先组合当前项位置与相对路径，再用浏览器定位，具体分支见第25.3节。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：当前循环项取值与输出`，第 2189–2191、2250–2252、2278–2284 行。

~~~python
                if p["relative"]:  # 是否相对xpath
                    if relativeXPath == "":  # 相对xpath有时候就是元素本身，不需要二次查找
                        element = loopElement
            # ……（省略其他原代码）
            self.execute_code(
                2, p["beforeJS"], p["beforeJSWaitTime"], element, iframe=p["iframe"])  # 执行前置js
            content = self.get_content(p, element)
        # ……（省略其他原代码）
        self.outputParameters[p["name"]] = content
        self.execute_code(
            2, p["afterJS"], p["afterJSWaitTime"], element, iframe=p["iframe"])  # 执行后置JS
if param["recordASField"] > 0 and param["newLine"]:
    line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
    self.OUTPUT.append(line)
~~~

relative=true、relativeXPath="" 对应 element=loopElement；nodeType=1 取链接文字，2 取 href。两列指向同一个当前 a。满足整体快速提取条件时，本例会用第 27 节的原快速循环；两条路线均按本轮记录取值。

#### 25.3 场景四：父元素是整张商品卡片，子元素是卡片内的图片链接模块

**当前例子：eBay 列表中的每张商品卡片是一个父 `li`，卡片内又有商品图片链接模块、价格等区域。本节先逐张找到父卡片，再进入其中的图片链接模块，提取这个模块的链接文字和 href；每张卡片形成一条记录。**

**先看父元素长什么样。** 下面按原任务 XPath 画出一张卡片的结构示意；模块名称是教学标记，URL 的查询部分省略，不是复制网页原始 HTML：

~~~html
<li class="商品卡片">                         <!-- 父元素：当前 loopElement -->
  <div>                                      <!-- 相对路径第1层 div[1] -->
    <div>                                    <!-- 第2层 div[1] -->
      <div>                                  <!-- 第3层 div[1] -->
        <a href="https://www.ebay.com/itm/204347640092?...">
          <!-- 子模块：商品图片链接模块，本节要找到的字段元素 -->
          <div>
            <img src="https://i.ebayimg.com/thumbs/images/g/yS0AAOSwc1Vjq2a2/s-l300.webp">
          </div>
        </a>
      </div>
      <div class="价格模块">这里示意同一卡片的其他区域</div>
    </div>
  </div>
</li>
~~~

**父元素是外层整张 `li` 卡片；字段元素是卡片内图片链接模块的 `a`。需要先找到父卡片，再沿相对路径走到这个模块。** 本节的两个字段都读取这个 `a`，一个取文字，一个取 href。原任务第一条链接文字样例为空；上面的模块以图片为内容，没有另外虚构商品名称。图片 `src` 是原任务另一个字段的目标，此处先展开链接的两个字段。

| 层次 | 本例对应什么 | 找到它后做什么 |
| --- | --- | --- |
| 父元素列表 | 全部商品卡片 `li` | 父循环逐张处理 |
| 当前父元素 `loopElement` | 第一张商品卡片 `li` | 作为这轮字段查找的起点 |
| 子模块的字段元素 `element` | 当前卡片内的 `a` | 提取链接文字、href，写入当前记录 |

**从文件读取的参数示例**：[0.json](../../ElectronJS/tasks/0.json) → `graph[6].parameters`（父循环，值保持原样）。父循环的 `sequence=[7]`，找到当前商品卡片后，由采集孩子7读取块内字段。

~~~json
{
  "loopType": 1,
  "xpath": "/html/body/div/div[4]/div[2]/div[1]/div[2]/ul[1]/li"
}
~~~

**从文件读取的参数示例**：[0.json](../../ElectronJS/tasks/0.json) → `graph[7].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "para1_link_text",
  "nodeType": 1,
  "contentType": 0,
  "relative": true,
  "relativeXPath": "/div[1]/div[1]/div[1]/a[1]",
  "default": "",
  "downloadPic": 0
}
~~~

**从文件读取的参数示例**：[0.json](../../ElectronJS/tasks/0.json) → `graph[7].parameters.params[1]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "para2_link_address",
  "nodeType": 2,
  "contentType": 0,
  "relative": true,
  "relativeXPath": "/div[1]/div[1]/div[1]/a[1]",
  "default": "",
  "downloadPic": 0
}
~~~

**把父 XPath、子模块相对 XPath 和最终位置放在一起。** 以第一轮 `index=0` 为例：

~~~text
父元素列表的 XPath（parentPath）：
/html/body/div/div[4]/div[2]/div[1]/div[2]/ul[1]/li

当前父元素：上面列表中的第1张卡片（loopElement）：
(/html/body/div/div[4]/div[2]/div[1]/div[2]/ul[1]/li)[1]

字段相对于当前父元素的 XPath（relativeXPath）：
/div[1]/div[1]/div[1]/a[1]

最终定位到子模块的完整位置（从整页看）：
(/html/body/div/div[4]/div[2]/div[1]/div[2]/ul[1]/li)[1]/div[1]/div[1]/div[1]/a[1]
~~~

括号后的 `[1]` 选择父列表中的第1张商品卡片，后面追加的 `/div[1]/div[1]/div[1]/a[1]` 才是在这张卡片内部走到图片链接模块。下一轮选择第2张卡片，再走同样的相对路径。

**本例原代码实际使用“当前父元素 + 相对路径”查找：** 因为相对路径不含 `//`，它执行 `loopElement.find_element(By.XPATH, relativeXPath[1:])`，传给查找方法的路径是：

~~~text
div[1]/div[1]/div[1]/a[1]
~~~

`loopElement` 已经限定了当前父卡片，去掉开头 `/` 后从这张卡片内部开始查找。上面展开的完整 XPath 用来说明最终位置；**本例没有实际生成 `full_path` 变量。只有原代码中“相对路径含 `//`”的另一条分支，才会组合 `parentPath`、`index+1` 和 `relativeXPath` 得到 `full_path`。**

**大致流程**：父循环按父 XPath 找整组 `li` → 每轮取一张卡片作为 `loopElement` → `executeNode(7, ...)` 执行采集孩子 → 按相对 XPath 在卡片内找到图片链接模块的 `a` → 读取该模块的文字和 href → 当前卡片形成一行，再处理下一张。

**先看父元素的循环：先找到全部卡片，再逐张执行采集孩子。** 这里沿普通 Selenium 提取路径展开，优化路线见第27节。以下是原 `loopType=1` 分支的核心；入口快照、停止和跳过等外围处理省略。此时 `node` 是 `0.json` 的父循环 `graph[6]`，`node["sequence"]=[7]`。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()`，父列表定位、逐项调用与索引推进。

~~~python
xpath = replace_field_values(
    node["parameters"]["xpath"], self.outputParameters, self)
elements = self.browser.find_elements(By.XPATH,
                                      xpath, iframe=node["parameters"]["iframe"])
# ……（省略其他原代码）
index = 0
# ……（省略其他原代码）
while index < len(elements):
    # ……（省略其他原代码）
    try:
        element = elements[index]  # ⭐️⭐️⭐️注意这里在 parent（父元素）循环中，先取出本轮的当前商品卡片父元素 li；具体操作随后由 executeNode 执行
        element_text = element.text
    except StaleElementReferenceException: # 如果元素已经失效，重试
        self.print_and_log("元素已失效，重新获取元素|Element has expired, reacquiring element")
        elements = self.browser.find_elements(By.XPATH,
                                              xpath, iframe=node["parameters"]["iframe"])
        element = elements[index]  # ⭐️⭐️⭐️元素失效重取后，仍按 index 选出当前商品卡片父元素 li；具体操作随后由 executeNode 执行
    for i in node["sequence"]:  # 挨个顺序执行循环里所有的操作
        self.executeNode(i, element,
                         xpath, index)  # ⭐️⭐️⭐️当前商品卡片父元素已选好，这里执行采集孩子7，再在卡片内部定位子模块并读取字段
    # ……（省略其他原代码）
    index, elements = self.handleHistory(node, xpath, thisHandle, thisHistoryURL, thisHistoryLength, index, elements=elements)
    # ……（省略其他原代码）
    index = index + 1
~~~

**外层 `while` 每轮取出一张父卡片 `element`；内层 `for` 执行这张卡片的采集操作。调用 `executeNode(7, element, xpath, index)` 后，这张卡片经 `loopValue` 传到 `getData()` 的 `loopElement`，父路径经 `loopPath` 传到 `parentPath`，`index` 表示它是第几张。** 两种子元素查找分支都接在这个父循环之后。

接下来才进入采集方法，按字段的相对路径选择下面的 `if/else`：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：相对字段定位核心`，第 2189–2208 行。

~~~python
if p["relative"]:  # 是否相对xpath
    if relativeXPath == "":  # 相对xpath有时候就是元素本身，不需要二次查找
        element = loopElement
    else:
        # 如果字串里有//即子孙查找，则不动语句
        if relativeXPath.find("//") >= 0:
            # full_path = "(" + parentPath + \
            #     relativeXPath + ")" + \
            #     "[" + str(index + 1) + "]"
            full_path = "(" + parentPath + ")" + \
                        "[" + str(index + 1) + "]" + \
                        relativeXPath
            element = self.browser.find_element(
                By.XPATH, full_path, iframe=p["iframe"])
        else:
            element = loopElement.find_element(By.XPATH,
                                               relativeXPath[1:])
else:
    element = self.browser.find_element(
        By.XPATH, relativeXPath, iframe=p["iframe"])
~~~

**分支 A：相对 XPath 不含 `//`，走 `else`，在当前父元素里面按层级找。**

就是前面的 eBay 商品卡片：父元素是 `li`，子模块是卡片里沿三层 `div` 才能到达的 `a`。原任务相对路径不为空，且 `relativeXPath.find("//")` 返回 `-1`：

| 本轮的输入 | 具体值 |
| --- | --- |
| 当前父元素 `loopElement` | 第一张商品卡片 `li`（`index=0`） |
| 原相对路径 `relativeXPath` | `/div[1]/div[1]/div[1]/a[1]` |
| `relativeXPath[1:]` | `div[1]/div[1]/div[1]/a[1]` |
| 原代码执行哪句 | `loopElement.find_element(By.XPATH, relativeXPath[1:])` |
| 查找结果 `element` | 第一张卡片中图片链接模块的 `a` |

这里 `find_element()` 的调用对象是当前父元素，去掉开头 `/` 后从这张卡片内部逐层查找。它最终指向前面展开的 `(父XPath)[1]/div[1]/div[1]/div[1]/a[1]`，但这一分支不创建 `full_path`。

**分支 B：相对 XPath 含 `//`，走 `if`，先把“当前父元素的位置”写入完整路径，再从浏览器查找。**

换一份原任务说明这条分支：[158.json](../../ElectronJS/tasks/158.json) 是京东页面的子元素采集任务，父循环选择一组活动块，字段“参数47_文本”读取块内倒计时模块中的 `em` 文字。字段保存的样例是“剩余9天22时10分”。块内层级用下面的结构示意：

~~~html
<div class="当前活动块">                  <!-- 当前父元素 loopElement -->
  <section>
    <div>                                <!-- 中间可以有不同层级 -->
      <a>
        <em>剩余9天22时10分</em>           <!-- 本节要读取的倒计时文字 -->
      </a>
    </div>
  </section>
</div>
~~~

模块名称与中间标签用于说明后代关系，实际定位由以下保存的 XPath 决定。

**从文件读取的参数示例**：[158.json](../../ElectronJS/tasks/158.json) → `graph[4].parameters`（父循环，只摘本例用到的键，值保持原样）。该循环 `sequence=[5]`，采集孩子为节点5。

~~~json
{
  "loopType": 1,
  "xpath": "/html/body/div[5]/div[2]/div[2]/div[1]/div[1]/div[2]/ul[1]/li/div[1]"
}
~~~

**从文件读取的参数示例**：[158.json](../../ElectronJS/tasks/158.json) → `graph[5].parameters.params[1]`（子字段，只摘本例用到的键，值保持原样）。

~~~json
{
  "name": "参数47_文本",
  "relative": true,
  "relativeXPath": "//a/em[1]",
  "nodeType": 0,
  "contentType": 1
}
~~~

这一例的父循环仍执行上面的原 `loopType=1` 代码，只是父路径与采集孩子来自 `158.json`。以第二轮 `index=1` 为例，原代码依次得到：

~~~text
parentPath = /html/body/div[5]/div[2]/div[2]/div[1]/div[1]/div[2]/ul[1]/li/div[1]
index = 1                         → index + 1 = 2
relativeXPath = //a/em[1]         → 包含 //，进入 if

先确定当前父元素的整页位置：
(/html/body/div[5]/div[2]/div[2]/div[1]/div[1]/div[2]/ul[1]/li/div[1])[2]

再接上 //a/em[1]，实际生成的 full_path 为：
(/html/body/div[5]/div[2]/div[2]/div[1]/div[1]/div[2]/ul[1]/li/div[1])[2]//a/em[1]
~~~

**先用 `(parentPath)[2]` 限定第2个父块，再在该块后代中寻找 `a`，取这些 `a` 的第一个 `em`；浏览器的 `find_element()` 返回其中第一个匹配元素。** 所以这里调用 `self.browser.find_element(By.XPATH, full_path, iframe=p["iframe"])` 时，完整路径里已经限定了本轮父元素，不会从第1个活动块开始取。

代码旁的“子孙查找，则不动语句”指这一分支保留 `relativeXPath` 中的 `//`，而不是执行另一分支的 `relativeXPath[1:]`；`//` 表示可以跨越中间层级。

| 对照项 | 分支 A：没有 `//` | 分支 B：包含 `//` |
| --- | --- | --- |
| 从哪里开始查 | 当前父元素 `loopElement` | 浏览器 `self.browser` |
| 怎么限定当前父块 | 已经拿到了这个父元素对象 | 在 `full_path` 中先写 `(parentPath)[index+1]` |
| 路径怎样处理 | 去掉开头 `/`，按子层级找 | 保留 `//`，在当前父块范围内找后代 |
| 最后得到什么 | 当前卡片内的 `a` 模块 | 当前活动块内的倒计时 `em` |

两个例子的 `element` 都是“本轮父块里面最终要读取的字段元素”，后续再交给 `get_content()` 取文字或属性。本节前面的两个 eBay 字段走分支 A；分支 B 的倒计时例子用于单独说明 `//` 的实际处理。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：读取字段、赋值与生成行`，第 2250–2252、2278–2284 行。

~~~python
            self.execute_code(
                2, p["beforeJS"], p["beforeJSWaitTime"], element, iframe=p["iframe"])  # 执行前置js
            content = self.get_content(p, element)
        # ……（省略其他原代码）
        self.outputParameters[p["name"]] = content
        self.execute_code(
            2, p["afterJS"], p["afterJSWaitTime"], element, iframe=p["iframe"])  # 执行后置JS
if param["recordASField"] > 0 and param["newLine"]:
    line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
    self.OUTPUT.append(line)
~~~

本例最后得到的 `element` 是当前卡片内图片链接模块的 `a`，父 `loopElement` 仍是整张 `li` 卡片。`get_content()` 再根据两个字段的 `nodeType`，分别读取该 `a` 的文字和 href；两列归入当前卡片的同一条记录。

#### 25.4 getData 怎样选择路径，怎样生成输出行

**当前例子：继续使用第25节的楼栋详情，提取“楼/幢”文字，写入“参数1_文本”。** 采集目标不变，这次专门跟踪同一个字段在 `getData()` 内的处理过程：它是从 HTML 快照中读取，还是先用 Selenium 定位元素再读取，最后怎样更新字段并生成一行。

以原任务样例的主体文字 `楼/幢:6` 为例，本轮读到的内容先成为 `content`，再保存到 `self.outputParameters["参数1_文本"]`；满足生成行的配置时，才把字段当前值组成 `line`，追加到 `self.OUTPUT`。**字段读取、字段赋值、生成输出行，是依次发生的三个步骤。**

**从文件读取的参数示例**：[循环点进详情页无新标签页打开.json](../../Examples/循环点进详情页无新标签页打开.json) → `graph[4].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数1_文本",
  "nodeType": 0,
  "contentType": 0,
  "relative": false,
  "relativeXPath": "/html/body/div[2]/div[2]/div[2]/div[2]/div[1]",
  "default": "",
  "downloadPic": 0
}
~~~

**大致流程**：getData 先准备 HTML 和清空规则 → 可优化字段走 HTML 读取，不可优化字段走 Selenium → 无论哪条原路径，结果都按字段名更新并按配置追加行。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `getData()：提取路径选择与输出核心`，第 2068–2075、2091–2095、2180–2184、2278–2284 行。

~~~python
parentPath = replace_field_values(
    parentPath, self.outputParameters, self)
if param["clear"] == 1:
    self.clearOutputParameters()
try:
    pageHTML = etree.HTML(self.browser.page_source)
except:
    pageHTML = etree.HTML("")
# ……（省略其他原代码）
for p in param["params"]:
    if p["optimizable"]:
        try:
            relativeXPath = replace_field_values(
                p["relativeXPath"], self.outputParameters, self)
# ……（省略其他原代码）
for p in param["params"]:
    if not p["optimizable"]:
        content = ""
        relativeXPath = replace_field_values(
            p["relativeXPath"], self.outputParameters, self)
        # ……（省略其他原代码）
        self.outputParameters[p["name"]] = content
        self.execute_code(
            2, p["afterJS"], p["afterJSWaitTime"], element, iframe=p["iframe"])  # 执行后置JS
if param["recordASField"] > 0 and param["newLine"]:
    line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
    self.OUTPUT.append(line)
~~~

这段只展示分流与输出位置，两个字段循环的读取主体省略。优化路径的 HTML、XPath 后缀与默认值处理见原 getData 和第 27 节；普通定位在上面四个场景讲过。isInLoop 表示节点处于循环范围，relative 表示某个字段相对当前项，二者各有作用。

### 26. contentType 与 nodeType：先从真实字段看取值分支

**当前例子：打开一篇介绍腾势N7的汽车新闻，要采集页面标题和正文，再遍历正文中的图片，提取图片地址并下载图片。** 同一篇文章里，标题、正文、图片要读取的内容不同；本节先用“页面标题”和“图片地址”两个实际字段解释 `get_content()` 怎样选择取值分支。

| 页面上有什么 | 本次要提取什么 | 任务保存的样例内容 |
| --- | --- | --- |
| 新闻页面的 title | “参数1_图片页面标题”，取整个页面标题 | 腾势N7将上市，两种前脸，外观很年轻运动，续航702km_懂车帝 |
| 新闻正文及其中的图片 | 本节展开“参数1_图片地址”，读取当前图片 src，并按配置下载 | 图片地址指向 `p9-dcd-sign.byteimg.com` 上的 `.webp` 资源，原值含签名查询参数 |

原任务先在采集节点中读取标题与正文，再由图片循环逐张执行采集。**本节要分清“对已定位的元素取什么内容”：`contentType=6` 取页面标题，`contentType=0、nodeType=4` 取图片 src；`downloadPic=1` 还会触发图片下载。** 后面的代码分别对应这些内容类型。

**从文件读取的参数示例**：[第二步：采集详情页标题内容并下载所有图片.json](../../Examples/汽车新闻采集/第二步：采集详情页标题内容并下载所有图片.json) → `graph[2].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数1_图片页面标题",
  "nodeType": 4,
  "contentType": 6,
  "relative": false,
  "relativeXPath": "/html/body/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/aside[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/a[1]/div[1]/img[1]",
  "default": "",
  "downloadPic": 0
}
~~~

**从文件读取的参数示例**：[第二步：采集详情页标题内容并下载所有图片.json](../../Examples/汽车新闻采集/第二步：采集详情页标题内容并下载所有图片.json) → `graph[4].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数1_图片地址",
  "nodeType": 4,
  "contentType": 0,
  "relative": true,
  "relativeXPath": "",
  "default": "",
  "downloadPic": 1
}
~~~

**大致流程**：getData 把字段配置 p 和已定位的 element 传入 → get_content 按 contentType 分发，再按需要看 nodeType → 返回 content → 调用方更新输出字典。

这里不贴整段 0–15 方法，先读最常用的原分支。contentType=0 时，链接/输入/图片分别读 href/value/src，普通节点读 text；图片下载另有文件副作用：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `get_content()：基本内容与 nodeType`，第 1876–1905 行。

~~~python
if p["contentType"] == 0:
    # 先处理特殊节点类型
    if p["nodeType"] == 2:
        if element.get_attribute("href") != None:
            content = element.get_attribute("href")
        else:
            content = ""
    elif p["nodeType"] == 3:
        if element.get_attribute("value") != None:
            content = element.get_attribute("value")
        else:
            content = ""
    elif p["nodeType"] == 4:  # 图片
        if element.get_attribute("src") != None:
            content = element.get_attribute("src")
        else:
            content = ""
        try:
            downloadPic = p["downloadPic"]
        except:
            downloadPic = 0
        if downloadPic == 1:
            download_image(self, content, "Data/Task_" +
                           str(self.id) + "/" + self.saveName + "/images", element)
    else:  # 普通节点
        if p["splitLine"] == 1:
            text = extract_text_from_html(element.get_attribute('outerHTML'))
            content = split_text_by_lines(text)
        else:
            content = element.text
~~~

HTML、背景图、页面地址和标题的分支很短，直接对照原实现：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `get_content()：HTML、背景图与页面信息`，第 1941–1954 行。

~~~python
elif p["contentType"] == 2:
    content = element.get_attribute('innerHTML')
elif p["contentType"] == 3:
    content = element.get_attribute('outerHTML')
elif p["contentType"] == 4:
    # 获取元素的背景图片地址
    bg_url = element.value_of_css_property('background-image')
    # 清除背景图片地址中的多余字符
    bg_url = bg_url.replace('url("', '').replace('")', '')
    content = bg_url
elif p["contentType"] == 5:
    content = self.browser.current_url
elif p["contentType"] == 6:
    content = self.browser.title
~~~

JS、系统命令、Python 表达式复用 execute_code；属性与常量按字段 JS 配置取值，末尾规范 None 并返回：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `get_content()：代码、属性、常量和返回值`，第 2022–2028、2042–2052 行。

~~~python
elif p["contentType"] == 9:
    content = self.execute_code(
        2, p["JS"], p["JSWaitTime"], element, iframe=p["iframe"])
elif p["contentType"] == 12:  # 系统命令返回值
    content = self.execute_code(1, p["JS"], p["JSWaitTime"])
elif p["contentType"] == 13:  # eval返回值
    content = self.execute_code(6, p["JS"], p["JSWaitTime"])
# ……（省略其他原代码）
elif p["contentType"] == 14:  # 元素属性值
    attribute_name = p["JS"]
    try:
        content = element.get_attribute(attribute_name)
    except:
        content = ""
elif p["contentType"] == 15:  # 常量值
    content = p["JS"]
if content == None:
    content = ""
return content
~~~

本节参数中 contentType=6 返回页面 title；contentType=0/nodeType=4 返回 src 并按 downloadPic 下载。截图/OCR 核心在第 31.2 节，Select 与直接文本等完整分支可点源码查看。其余类型按原分发对照：

| contentType | 先看参数摘录 | 再看取值实现 | 参数文件与位置 |
| --- | --- | --- | --- |
| 0 | `contentType=0, nodeType=2` | 普通/链接文字 .text；nodeType=2 href、3 value、4 src | 第 25.2 节实际链接字段 |
| 1 | `contentType=1, nodeType=4` | 普通节点只取直接文本；链接、输入、图片有特殊分支 | [0.json](../../ElectronJS/tasks/0.json) / graph[7].parameters.params[2] |
| 2 | `contentType=2, nodeType=0` | innerHTML | 教学变体：第 25 节字段改 contentType |
| 3 | `contentType=3, nodeType=0` | outerHTML | 教学变体：第 25 节字段改 contentType |
| 4 | `contentType=4, nodeType=0` | background-image 去掉 url 包装 | [35.json](../../ElectronJS/tasks/35.json) / graph[2].parameters.params[0] |
| 5 | `contentType=5, nodeType=0` | browser.current_url | [256.json](../../ElectronJS/tasks/256.json) / graph[3].parameters.params[0] |
| 6 | `contentType=6, nodeType=4` | browser.title | 本节实际页面标题字段 |
| 7 | `contentType=7, nodeType=0` | 元素截图；字段内容为空字符串 | [101.json](../../ElectronJS/tasks/101.json) / graph[18].parameters.params[0] |
| 8 | `contentType=8, nodeType=0` | 元素截图后由 ddddocr 识别 | [181.json](../../ElectronJS/tasks/181.json) / graph[3].parameters.params[0] |
| 9 | `contentType=9, nodeType=0, JS="return new Date().toString()"` | 对字段元素执行 JS，取得返回值 | [151.json](../../ElectronJS/tasks/151.json) / graph[4].parameters.params[1] |
| 10 | `contentType=10, nodeType=0` | 下拉选中项的 value | [68.json](../../ElectronJS/tasks/68.json) / graph[3].parameters.params[0] |
| 11 | `contentType=11, nodeType=0` | 下拉选中项的 text | [68.json](../../ElectronJS/tasks/68.json) / graph[3].parameters.params[1] |
| 12 | `contentType=12, nodeType=0, JS="python D:/test.py"` | 系统命令 stdout | [152.json](../../ElectronJS/tasks/152.json) / graph[3].parameters.params[3] |
| 13 | `contentType=13, nodeType=0, JS="self.a"` | Python eval 的结果 | [182.json](../../ElectronJS/tasks/182.json) / graph[3].parameters.params[0] |
| 14 | `contentType=14, nodeType=0, JS="class"` | JS 保存属性名，读取该属性 | [191.json](../../ElectronJS/tasks/191.json) / graph[3].parameters.params[0] |
| 15 | `contentType=15, nodeType=1, JS="123"` | 直接保存 JS 字符串 | [318.json](../../ElectronJS/tasks/318.json) / graph[3].parameters.params[0] |

类型 1 的普通节点只读直接文本子节点，链接、输入和图片仍有特殊分支。类型 7 保存截图但字段返回空字符串，8 返回 OCR 文本；文件副作用和字段值需要分清。这里所有读取规则都指向原 get_content。

### 27. 两层提取优化：先学会用 lxml，再理解快速循环

**当前例子：协会企业列表已经显示在页面上，现在只要采集每家企业的名称和链接地址，一家企业一行。** 先用两条链接学习 lxml 的基本用法，再回到 EasySpider：既然文字和 href 已经在 HTML 中，就有机会直接解析 HTML、批量读取字段，减少逐个操作 Selenium 元素的开销。

#### 27.1 lxml 基本用法：把 HTML 解析成树，再用 XPath 取值

lxml 可以在 Python 中把 HTML 字符串解析成一棵树，再用 XPath 找节点、读取文字和属性。它处理的是已有的 HTML，不负责打开浏览器，也不会执行网页 JavaScript。

下面是**独立的基础教学示例**，不是 EasySpider 源码摘录。企业名称和地址沿用任务保存的前两条样例，HTML 结构做了简化：

~~~python
from lxml import html

page_html = """
<ul id="companies">
  <li><a href="https://www.jx-jx.net/articleview/574.html">华建建设集团有限公司</a></li>
  <li><a href="https://www.jx-jx.net/articleview/573.html">嘉兴市明洲电力建设有限公司</a></li>
</ul>
"""

tree = html.fromstring(page_html)              # 把 HTML 字符串解析成树
rows = tree.xpath('//ul[@id="companies"]/li/a')  # 找到列表中的全部 a 节点

for row in rows:  # ⭐️⭐️⭐️每轮取一个当前链接；row 是 lxml 节点，不是 Selenium 元素
    name = row.xpath('string(.)')             # 当前 a 内的文字，返回字符串
    url = row.xpath('./@href')[0]             # 当前 a 的 href；xpath 返回列表，取第1项
    print(name, url)
~~~

运行时会输出：

~~~text
华建建设集团有限公司 https://www.jx-jx.net/articleview/574.html
嘉兴市明洲电力建设有限公司 https://www.jx-jx.net/articleview/573.html
~~~

按执行顺序，只需先理解这四步：

| 步骤 | 本例代码 | 得到什么 |
| --- | --- | --- |
| 解析 HTML | `html.fromstring(page_html)` | 一棵可以用 XPath 查询的 HTML 树 |
| 找整组节点 | `tree.xpath('//ul[@id="companies"]/li/a')` | 两个 `a` 节点组成的列表 `rows` |
| 取当前节点文字 | `row.xpath('string(.)')` | 当前企业名称；这里的 `.` 表示当前节点，`string(...)` 返回字符串 |
| 取当前节点属性 | `row.xpath('./@href')` | 当前链接的地址列表，例如 `["https://www.jx-jx.net/articleview/574.html"]`；本例已知有 href，取 `[0]` 得到地址 |

还会经常见到 `row.xpath('.//text()')`，它返回当前节点内部各段文本组成的列表。比如第一条链接的结果是 `["华建建设集团有限公司"]`；EasySpider 原快速路径会把这些文本去空白后合并。**`tree.xpath(...)` 先找出整组记录，`for row in rows` 每次处理一条记录，`row.xpath(...)` 再读取这条记录的字段。**

#### 27.2 什么情况下可以快：当前页的 HTML 已经包含要采的数据

现在把上面的 HTML 字符串换成浏览器当前页面的 `self.browser.page_source`，就能用同样的方法提取企业列表。假设有100个链接，我们要读每个链接的文字和地址：

| 提取方式 | 这100条记录怎样处理 |
| --- | --- |
| 普通 Selenium 路径 | 按当前元素执行采集，读取元素的文字、属性等；这些操作需要通过 WebDriver 与浏览器通信 |
| lxml 快速路径 | 取当前页的一份 HTML 快照，解析成树，再在 Python 内遍历节点并读取两列 |

**这个任务只读取当前页已有的文字和 href，循环里只有采集操作，所以可以检查是否满足整组快速提取条件；满足后就直接用 lxml 遍历，无需逐条调用 `executeNode()` 执行采集孩子。** 快的原因是减少了反复访问浏览器元素的通信，并不是把浏览器点击得更快。

如果任务要求“点进每家企业详情，再采详情内容”，详情尚未包含在这份列表 HTML 里，就需要按原流程执行点击与详情采集。浏览器仍负责打开网页、加载动态内容和翻页；进入新页后，要重新获取新页的 HTML 快照。

回到仓库中的真实任务，先看它保存的父循环和字段参数。

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[7].parameters`（只摘本节用到的键，值保持原样）。该父循环 `sequence=[8]`，唯一孩子8是采集节点。

~~~json
{
  "loopType": 1,
  "xpath": "/html/body/div[1]/div[5]/div[1]/div[1]/div[2]/ul[1]/li/a[1]"
}
~~~

**从文件读取的参数示例**：[最简单的翻页采集列表.json](../../Examples/最简单的翻页采集列表.json) → `graph[8].parameters.params`（两个字段，各只摘本节用到的键，值保持原样）。

~~~json
[
  {
    "name": "参数1_链接文本",
    "nodeType": 1,
    "contentType": 0,
    "relative": true,
    "relativeXPath": ""
  },
  {
    "name": "参数2_链接地址",
    "nodeType": 2,
    "contentType": 0,
    "relative": true,
    "relativeXPath": ""
  }
]
~~~

两列的相对路径都为空，表示从当前企业链接本身读取。原预处理为快速提取准备以下运行期路径（这些不是任务文件中另存的一套手写配置）：

| 运行期值 | 本例是什么 | 对应刚才的基本用法 |
| --- | --- | --- |
| `baseXPath` | 父循环保存的企业链接列表 XPath | 找整组记录，得到 `rows` |
| 名称字段的 `quickParams[*].xpath` | `.//text()` | 在当前链接中取文本，再合并 |
| 地址字段的 `quickParams[*].xpath` | `.//@href` | 在当前链接范围内取 href |

#### 27.3 为什么分两层：一个字段能快，不等于整个循环都能快

**第一层是字段的 `optimizable`：这个值能不能直接从 HTML 读？** 本例的名称和 href 都属于普通文字/属性读取，没有字段前后置 JS，也不需要分行处理，符合原字段判断。截图、OCR、输入框值等则不能直接套用这条优化；图片地址能否优化还要看是否要求下载。

**第二层是循环的 `quickExtractable`：能不能把整轮“执行采集孩子”换成 lxml 遍历？** 原 [preprocess()](../../ExecuteStage/easyspider_executestage.py) 还会检查：循环类型为1或2、唯一孩子是采集、字段全部符合条件，并且 iframe、跳过数量、等待元素等配置允许。本例父循环只有孩子8，且两个字段都只是取文字和地址，因此是这种快速循环的典型场景。

| 两层标志 | 在原执行器中的含义 |
| --- | --- |
| 某字段 `optimizable=true` | 正常调用 `getData()` 时，这个字段可以走 HTML 解析分支；任务中的其他动作仍按执行树组织 |
| 父循环 `quickExtractable=true` | 进入 `loopExecute()` 后直接用 `rows` 和 `quickParams` 读取整组记录，不逐项分派采集孩子 |

这里先理解“只读当前 HTML，才能考虑这样提速”，再看下面两块源码。其余预处理细节可回到函数中查，不在本节逐段罗列。

#### 27.4 对照原版核心代码：先判断字段，再整组读取

**第一块：字段判断。** 下面的原函数对应刚才的名称/href 两列：没有前后置 JS、内容类型允许且 `splitLine=0`，`nodeType` 为1或2时会返回 `True`。

**核心源码**：[utils.py](../../ExecuteStage/utils.py) → `detect_optimizable()`，第 182–199 行。

~~~python
def detect_optimizable(param, ignoreWaitElement=True, waitElement=""):
    try:
        splitLine = param["splitLine"]
    except:
        param["splitLine"] = 0
    if param["beforeJS"] == "" and param["afterJS"] == "" and param["contentType"] <= 1 and param["splitLine"] == 0:
        if param["nodeType"] <= 2:
            if ignoreWaitElement or waitElement == "":
                return True
            else:
                return False
        elif param["nodeType"] == 4: # 如果是图片
            if param["downloadPic"]:
                return False
            else:
                return True
    else:
        return False
~~~

**第二块：快速循环。** 满足整体条件后，原 `preprocess()` 生成 `baseXPath`、`quickParams`，并复制采集节点的 `clear/newLine` 设置。然后 `loopExecute()` 就按下面的方式取页面 HTML、查整组链接、逐链接读取两列、生成输出行。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()` 快速路径核心。只保留 `loopType=1`、记录遍历和输出；固定路径准备、文本合并、URL补全与默认值等原代码用省略号标记。

~~~python
if node["parameters"]["quickExtractable"]:
    self.browser.switch_to.default_content() # 切换到主页面
    tree = html.fromstring(self.browser.page_source)
    if int(node["parameters"]["loopType"]) == 1: # 不固定元素列表
        baseXPath = replace_field_values(node["parameters"]["baseXPath"], self.outputParameters, self)
        rows = tree.xpath(baseXPath)
    # ……（省略其他原代码）
    for row in rows:  # ⭐️⭐️⭐️父列表已经找到；本轮 row 是当前企业链接的 lxml 节点
        if node["parameters"]["clear"] == 1:
            self.clearOutputParameters()
        for param in node["parameters"]["quickParams"]:
            xpath = replace_field_values(param["xpath"], self.outputParameters, self)
            content = row.xpath(xpath)  # ⭐️⭐️⭐️在当前节点上读取字段；快路径直接在本地处理，不逐项调用 executeNode
            # ……（省略其他原代码）
            self.outputParameters[param["name"]] = content
        if node["parameters"]["newLine"]:
            line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
            self.OUTPUT.append(line)
    self.saveData()
~~~

把它代入第一条企业链接：`row` 是“华建建设集团有限公司”的 lxml `a` 节点；两个 `param` 分别让 `row.xpath()` 读到名称和地址。省略的原代码会合并文本、处理默认值，并通过 `urljoin()` 补全相对地址。更新字段字典后，`new_line()` 组成这一行：

~~~text
["华建建设集团有限公司", "https://www.jx-jx.net/articleview/574.html"]
~~~

下一轮 `row` 换成“嘉兴市明洲电力建设有限公司”的链接，形成下一行。**采集目标和一条链接对应一行的规则没有改变，改变的是读取方式：从逐项访问浏览器元素，变为解析当前页 HTML 后在本地读取。** 保存、续采与收尾仍按第16篇的原执行器流程处理。

### 28. iframe：从 JSON 的 true 看 MyChrome 的封装

**从文件读取的参数示例**：[115.json](../../ElectronJS/tasks/115.json) → `graph[3].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "xpath": "//*[@id=\"weidu1\"]",
  "iframe": true,
  "useLoop": false,
  "value": "1"
}
~~~

**大致流程**：收到 iframe 标志 → 查找前回到主文档 → 为真时搜 iframe 并递归定位，为假时用父类查找 → 返回找到的元素。

**核心源码**：[myChrome.py](../../ExecuteStage/myChrome.py) → `MyChrome.find_element()`，第 94–106 行。

~~~python
def find_element(self, by=By.ID, value=None, iframe=False):
    self.switch_to.default_content()  # Switch back to the main document
    self.iframe_env = False
    if iframe:
        frames = self.find_elements(By.CSS_SELECTOR, "iframe")
        if not frames:
            raise NoSuchElementException(f"No iframes found in the current page while searching for {value}")
        self.iframe_env = True
        element = self.find_element_recursive(by, value, frames)
    else:
        # Find element in the main document as normal
        element = super(MyChrome, self).find_element(by=by, value=value)
    return element
~~~

本例 iframe=true，在 frame 中找输入框。iframe= 是 MyChrome 扩展参数，原生 Selenium 不接收。递归内部用父类方法避免重新切回主文档；当前失败路径没有完整恢复父 frame 后再尝试所有兄弟，不能将它描述为保证搜索任意 frame 结构。

### 29. 悬停、下拉框与自定义代码：各自怎样调用 API

**从文件读取的参数示例**：[133.json](../../ElectronJS/tasks/133.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": false,
  "xpath": "//*[contains(@class, \"LeftSide_menu_list__qXCeM\")]/div[2]",
  "iframe": false
}
~~~

**从文件读取的参数示例**：[133.json](../../ElectronJS/tasks/133.json) → `graph[4].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "useLoop": true,
  "xpath": "/html/body/div[5]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div",
  "loopType": 1
}
~~~

**大致流程**：移动前稍等 → 按普通/循环路径定位目标 → ActionChains 移动鼠标 → 返回父容器，节点后等待由 executeNode 处理。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `moveToElement()：定位与悬停核心`，第 937–952、955 行。

~~~python
if param["useLoop"]:  # 使用循环的情况下，传入的clickPath就是实际的xpath
    if xpath == "":
        path = loopPath
    else:
        path = "(" + loopPath + ")" + \
               "[" + str(index + 1) + "]" + \
               xpath
        index = 0  # 如果是相对循环内元素的点击，在定位到元素后，index应该重置为0
    # element = loopElement
else:
    index = 0
    path = xpath  # 不然使用元素定义的xpath
path = replace_field_values(path, self.outputParameters, self)
try:
    elements = self.browser.find_elements(
        By.XPATH, path, iframe=param["iframe"])
        # ……（省略其他原代码）
        ActionChains(self.browser).move_to_element(element).perform()
~~~

133 的旧循环孩子路径会在 preprocess 中清空，再用父路径/index；普通悬停使用自己的 xpath。这个原方法没有前后置 JS 调用。单次悬停是 option=7，批量悬停由循环反复调用该动作。

#### 29.1 下拉框：sendChangeOption 的规则怎样被解释

**从文件读取的参数示例**：[135.json](../../ElectronJS/tasks/135.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "xpath": "//*[@id=\"cars\"]",
  "useLoop": false,
  "optionMode": 0,
  "optionValue": "Saab"
}
~~~

**大致流程**：读 optionMode/optionValue → useLoop 时按原规则取循环值并切到索引模式 → 找原生 select → 按模式选择 → 返回。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `switchSelect()：取值与 Select 核心`，第 888–901、903–921 行。

~~~python
optionMode = param["optionMode"]
optionValue = param["optionValue"]
if param["useLoop"]:
    index = param["index"]
    if index != 0:
        try:
            optionValue = loopValue.split("~")[index - 1]
        except:
            self.print_and_log("取值失败，可能是因为取值索引超出范围，将使用整个文本值")
            self.print_and_log(
                "Failed to get value, maybe because the index is out of range, will use the entire text value")
    else:
        optionValue = loopValue
    optionMode = 1
    # ……（省略其他原代码）
    xpath = replace_field_values(
        param["xpath"], self.outputParameters, self)
    dropdown = Select(self.browser.find_element(
        By.XPATH, xpath, iframe=param["iframe"]))
    try:
        if optionMode == 0:
            # 获取当前选中的选项索引
            current_index = dropdown.options.index(
                dropdown.first_selected_option)
            # 计算下一个选项的索引
            next_index = (current_index + 1) % len(dropdown.options)
            # 选择下一个选项
            dropdown.select_by_index(next_index)
        elif optionMode == 1:
            dropdown.select_by_index(int(optionValue))
        elif optionMode == 2:
            dropdown.select_by_value(optionValue)
        elif optionMode == 3:
            dropdown.select_by_visible_text(optionValue)
~~~

135 的 optionMode=0 表示当前索引加一并对选项数取模，虽然 optionValue 为 Saab，这一模式不按文字 Saab 查找。模式 1/2/3 分别按索引/value/文字；useLoop=true 会按原代码转成索引模式 1。div 模拟菜单不能直接套用原生 Select。

#### 29.2 自定义代码：先替换参数，再在对应环境执行

**现在举什么例子：** 前面的自定义操作先定义 `self.myVar`，后面的操作读取或更新它；更新时还可以引用已经采集的字段。这里要串起“代码文本替换”和“真正执行代码”两个阶段。

**从文件读取的参数示例**：[Exec and Eval.json](../../Examples/Exec%20and%20Eval.json) → `graph[5].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "codeMode": "5",
  "code": "self.myVar = \"-1\"",
  "waitTime": 0,
  "recordASField": 0
}
~~~

这是执行 Python 语句的节点，用来初始化自定义变量。这个文件里原值是字符串 `"-1"`；如果要定义整数变量，可以在自定义操作中填写 `self.myVar = 1`。

**大致流程**：option=5 调 `customOperation()` → 读取 `codeMode` 和 `code` → 对进入 `execute_code()` 的代码先做 `replace_field_values()` 替换 → 按模式交给 JS、系统命令、Python `exec` 或 `eval` → 返回值转字符串 → 写入以节点标题为键的输出值，按配置决定是否生成一行。

**先看执行前的替换入口**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `execute_code()`。下面是原代码中的关键一句，它位于各个执行模式的分支之前：

~~~python
code = replace_field_values(code, self.outputParameters, self)
~~~

也就是说，传进去的 `code` 会先经过这一道处理，再交给后面的执行模式。模式3/4等直接处理跳出、继续的控制操作，则不走这个入口。

**这到底是什么函数？** `replace_field_values()` 是项目自己写在 [utils.py](../../ExecuteStage/utils.py) 里的普通 Python 函数，在执行器中通过 `import` 导入。它接收一段带模板的字符串，把里面的字段引用或表达式换成当前值，**返回替换后的字符串**。最后用 `code = ...` 接住这个返回值，才得到后续实际执行的代码文本。

先拆开这次调用中的三个实参：

| 调用时传入 | 函数内的形参 | 具体是什么、用来做什么 |
| --- | --- | --- |
| `code` | `orginal_text` | 从任务节点读出的代码字符串。形参名在源码中就是这个拼写。 |
| `self.outputParameters` | `outputParameters` | 当前字段值字典。遇到 `Field["增量"]` 时，就从这里查找键“增量”。 |
| `self` | `browser` | 当前任务的执行器对象。模板求值可以读取它的属性，JS模板通过它访问真正的 Selenium 浏览器 `browser.browser`。 |

**第三个参数虽然在函数里叫 `browser`，本次传入的却是整个执行器 `self`。** 因而函数里的 `browser.myVar` 对应调用方的 `self.myVar`，`browser.browser` 对应调用方的 `self.browser`。这个普通函数没有实例方法的隐式 `self`，所以要显式把执行器对象传进去。

**先用一个完整替换过程说明。** 假设字段字典里有 `{"增量": "3"}`，用户在代码框填写的是：

~~~python
self.myVar += int(Field["增量"])
~~~

它最初只是一个字符串。函数处理后返回的字符串是：

~~~python
self.myVar += int(3)
~~~

然后才由模式5的 `exec(code)` 执行这条赋值语句。**普通 `Field[...]` 替换负责改代码文本，`self.myVar` 的赋值由后面的 exec 完成。** 如果代码是 `self.myVar = 1`，其中没有模板，它就原样返回。

**源码怎样把 `Field["增量"]` 变成3？** 下面摘自原函数，只保留普通字段替换主线，省略表达式分支和异常处理：

~~~python
field_pattern = r'Field\["([^"]+)"\]'
# ……（省略其他原代码）
working_text = orginal_text
# ……（省略 eval(...)、JS(...) 分支）
replaced_text = re.sub(
    field_pattern,
    lambda match: str(outputParameters.get(match.group(1), '')),
    working_text,
)
# ……（省略异常处理）
return replaced_text
~~~

顺着这段代码看：

1. `field_pattern` 是正则匹配规则，寻找形如 `Field["字段名"]` 的片段。
2. `re.sub()` 扫描整段代码，每找到一个匹配，就调用一次这里的 `lambda`。
3. 对 `Field["增量"]`，`match.group(1)` 取出的是字段名“增量”；用它执行 `outputParameters.get("增量", '')`，得到 `"3"`。键不存在时取空字符串。
4. `str(...)` 把值转为文本，替换整个 `Field["增量"]` 片段；其他代码保留。多个匹配会分别替换。

**完整函数还会先计算两类表达式模板。** 它的实际顺序是：处理 `eval("...")` → 处理 `JS("...")` → 替换剩余的普通 `Field[...]` → 返回字符串。假设 `self.myVar=4`，页面标题是“房源详情”，下面只展示模板片段的变化：

| 模板片段 | 替换成什么 | 值从哪里来 |
| --- | --- | --- |
| `Field["增量"]` | `3` | 当前字段字典 |
| `eval("self.myVar + 1")` | `5` | Python侧计算表达式 |
| `JS("return document.title")` | `房源详情` | Selenium执行页面脚本并读取返回值 |

`eval` 模板的原代码会先处理 `self.` 的名称映射，再匹配双引号内的表达式。以下省略包在外面的匹配循环，保留每次处理匹配项的核心：

~~~python
working_text = working_text.replace("self.", "browser.")
eval_call_pattern = re.compile(r'(?i)eval\("(.+?)"\)')
# ……（省略匹配循环和退出检查，match是找到的一个模板）
expr = _substitute_fields_as_python_literal(
    match.group(1), outputParameters)
eval_replaced_text = str(eval(expr))  # noqa: S307 - documented feature, scraped inputs are escaped above
working_text = working_text.replace(
    match.group(0), eval_replaced_text)
~~~

`match.group(0)` 是整个 `eval("...")` 模板，`match.group(1)` 是里面的表达式。`self.myVar + 1` 经名称映射后成为 `browser.myVar + 1`，就能读取第三个参数传来的执行器属性。若表达式里还含 `Field[...]`，辅助函数会先取字段值，并用 `repr()` 包装成 Python 字符串字面量，再计算表达式。

`JS` 模板同样先做名称映射并查找模板；找到一个匹配后，核心执行部分是：

~~~python
snippet = _substitute_fields_as_js_literal(
    match.group(1), outputParameters)
JS_replaced_text = str(browser.browser.execute_script(snippet))
working_text = working_text.replace(
    match.group(0), JS_replaced_text)
~~~

这里通过 `browser.browser` 找到真正的 WebDriver，执行模板里的页面脚本，再把返回值转为字符串填回原位置。辅助函数会把模板内部的字段值通过 `json.dumps()` 转成 JS可用的字符串字面量；这与模板外普通 `Field[...]` 的直接文本插入不同。

因此，这个函数既有字段文本替换，也有模板求值。表达式或JS模板可能在这个阶段就执行；整段自定义代码则在返回后才进入相应执行模式。源码用正则识别这些模板；异常时会打印提示，并返回最初传入的字符串。后面第④小点再对照模板中的 `eval("...")` 与模式6的 Python `eval`。


**① 先说清楚：为什么 exec 能执行 `self.myVar = 1`？**

先看 Python 的 `exec()` 在这里做什么：**它把收到的字符串当作 Python 语句执行，所以字符串里的赋值语句也能真正执行。** 例如传入的代码文本是 `"self.myVar = 1"`，执行它就会发生给对象属性赋值的动作。

关键还在于：这段代码里的 `self` 从哪里来？EasySpider 在 `BrowserThread` 的实例方法 `execute_code(self, ...)` 里面调用 `exec(code)`。原版模式5分支的核心是：

~~~python
code = readCode(code)
output = exec(code)
~~~

这里没有给 `exec()` 另传 `globals`、`locals` 参数，因此执行代码时可以访问当前方法上下文里的 `self`。理解这件事，可以分成三步：

1. **方法调用时已经有 `self`。** 它指向当前任务的 `BrowserThread` 对象，不需要用户在代码框里重新定义。
2. **`exec()` 执行字符串中的赋值语句。** 执行到 `self.myVar = 1` 时，Python 先找到这个 `self` 对象，再给它的 `myVar` 属性赋值。
3. **这个对象支持动态添加属性。** 即使原来没有 `myVar`，这次赋值也可以创建它；已经存在时，就更新它的值。因此无需预先在类中声明 `myVar`。

~~~text
代码框里的字符串："self.myVar = 1"
    ↓ exec在execute_code方法的上下文中执行
找到当前任务对象self
    ↓ 给这个对象添加myVar属性，值为1
方法返回后，对象还在，self.myVar也就还在
    ↓ 后续节点再次使用同一个self
可以读取self.myVar，或者继续修改它
~~~

**能跨节点保留下来，是因为值存在当前执行器对象的属性里；`exec()` 本身并不负责保存变量。**

**再说清楚：为什么跨节点使用时，要写 `self.myVar`，直接写 `myVar` 会怎样？**

**普通变量可以定义，也能在同一段代码里使用；这里需要 `self.`，是为了让前后不同节点共享这个值。** 两种写法保存数据的位置不同：

| 填写的代码 | 数据保存在哪里 | 后续节点能否直接沿用 |
| --- | --- | --- |
| `myVar = 1` | 本次 `exec()` 使用的局部命名空间中 | 当前实现没有跨调用复用它，后续节点不能靠这个名称取到之前的值 |
| `self.myVar = 1` | 当前任务执行器对象的 `myVar` 属性中 | 可以，后续节点仍能通过同一个 `self` 找到这个属性 |

先看普通变量可以正常使用的情况。**在同一个节点的一段 exec 代码中**，可以这样写：

~~~python
myVar = 1
myVar += 1
print(myVar)  # 本段代码内可以使用，打印2
~~~

问题出在把定义和读取拆到两个节点。假设当前环境没有其他同名变量：

~~~text
节点A，选择Python exec：
    myVar = 1

节点B，选择Python eval：
    myVar + 1
~~~

节点A调用一次 `execute_code()`，它执行完就返回。节点B会**重新调用一次** `execute_code()`，获得这次调用自己的方法上下文；执行器没有把上次 `exec()` 的局部名称收集起来，交给下一次使用。因此节点B计算 `myVar + 1` 时找不到 `myVar`，会产生 `NameError`。原执行器会捕获异常、记录日志，并返回空字符串。

换成属性后，两个节点可以这样配合：

~~~text
节点A，选择Python exec：
    self.myVar = 1

节点B，选择Python eval：
    self.myVar + 1
    → 得到整数2，执行器最终返回字符串"2"
~~~

为什么第二次方法调用里又有 `self`？因为两次都是**同一个执行器对象调用自己的实例方法**，Python 每次都会把这个对象传给方法的 `self` 参数。每次调用的局部上下文不同，但其中的 `self` 指向同一个对象：

~~~text
第一次execute_code调用：self ──→ 当前任务对象 ──→ myVar = 1
                                      ↑
第二次execute_code调用：self ───────────┘
~~~

**读取 `myVar` 是查找本次代码环境中的名称；读取 `self.myVar` 是先找到任务对象，再读取对象上的属性。方法返回不会清空这个对象的属性，所以后一个节点还能接着使用。**

因此，本例需要跨节点保存计数、状态时，就使用 `self.myVar`；只在当前节点内做临时计算时，直接定义普通变量即可。两者都要先赋值再读取。

下面再看自定义操作中怎样填写。三个节点按顺序执行，`clear` 均为0；后面会继续用到“增量”字段。示例填写内容与原版执行器源码分开列出。

第一个节点选择 **Python exec（`codeMode=5`）**，填写：

~~~python
self.myVar = 1
~~~

**`self` 是当前任务的 `BrowserThread` 执行器对象，`myVar` 是我们临时加到这个对象上的属性。可以把它当作当前任务中后续操作共用的变量。** 后面的 Python 自定义操作仍拿到同一个 `self`，所以能继续读写 `self.myVar`。

严格说，它是对象属性，不是 Python 模块级的全局变量；它随当前执行器对象存在，不会自动跨任务共享，也不会自动保存到输出文件。前一个节点要先执行初始化，后一个节点才能读取。这里也不应改写成只赋值 `myVar = 1` 并假定下一次 `exec()` 会自动保留这个局部名称。

**② 先替换采集字段，再更新自定义变量**

假设前面已经采集到一个字段，当前值为：

~~~python
self.outputParameters["增量"] = "3"
~~~

第二个节点仍选择 **Python exec（`codeMode=5`）**，填写：

~~~python
self.myVar += int(Field["增量"])
~~~

此时从输入文本到实际执行，依次发生：

~~~text
填写的代码：self.myVar += int(Field["增量"])
先替换字段：self.myVar += int(3)
再交给exec：将self.myVar从1更新为4
~~~

**`Field[...]` 是先被替换的文本占位符；`self.myVar` 是执行 Python 时访问的对象属性。** 本例的字段值是数字文本 `"3"`，所以替换结果可以放进 `int(3)`。普通 `Field[...]` 是原样插入文本，不会自动补上 Python 字符串引号，不能把任意文本都直接当成有效的 Python 表达式。

原任务也确实在复用这个变量：`graph[7].parameters.code` 是 `self.myVar == self.outputParameters["检测字段"]`，用于判断；`graph[10].parameters.code` 是 `self.myVar = self.outputParameters["检测字段"]`，用于更新。这里后者直接访问 Python 字典，不需要先写成 `Field[...]`。

**③ 用 eval 读取计算结果；exec 的赋值结果不是输出值**

第三个节点选择 **Python eval（`codeMode=6`）**，填写一个表达式：

~~~python
self.myVar * 10
~~~

因为前面已经把变量更新为4，这次计算结果是整数40，`execute_code()` 最后返回字符串 `"40"`。假设这个节点标题叫“计算结果”，`customOperation()` 随后就会更新：

~~~python
self.outputParameters["计算结果"] = "40"
~~~

后续输入、URL或其他自定义代码，就可以用 `Field["计算结果"]` 引用它。是否生成数据行还要看 `recordASField` 和 `newLine` 配置。

对照前两次赋值：**`exec()` 完成的是修改 `self.myVar` 的动作，本身返回 `None`；源码转字符串后是 `"None"`，不会自动把变量的新值当作返回值。要得到值，可以再用 `codeMode=6` 计算表达式。** `self.myVar = 1` 是语句，应交给 exec；`self.myVar * 10` 是表达式，可以交给 eval。

**④ 区分执行环境，以及两种不同位置的 eval**

| 模式 | 真正执行的位置 | 能否直接使用 Python 的 `self.myVar` |
| --- | --- | --- |
| 0：页面 JS | 当前浏览器页面 | 不能；页面没有这个 Python 对象 |
| 2：带元素 JS | 浏览器页面，元素作为脚本参数传入 | 不能；传入元素可用 `arguments[0]` |
| 1：系统命令 | `subprocess.run()` 启动的命令环境 | 不能直接访问当前 Python 对象 |
| 5：Python exec | 当前执行器方法的 Python 上下文 | 可以，适合赋值、更新属性等语句 |
| 6：Python eval | 当前执行器方法的 Python 上下文 | 可以，计算表达式并返回值 |

`codeMode=6` 的 `eval` 是最后真正执行 Python 表达式；而代码文本里的 `eval("...")` 模板，是前面的 `replace_field_values()` 在执行模式分发之前就计算的。例如当前 `self.myVar=4`，一个**页面 JS 节点（模式0）**可以填写：

~~~javascript
return eval("self.myVar");
~~~

处理顺序是：

~~~text
原始代码：return eval("self.myVar");
模板替换：return 4;
浏览器执行：return 4;
最终返回：字符串"4"
~~~

这里是在 Python 侧先读出变量值，再把替换后的 JS 发给浏览器。浏览器真正执行的代码里已经没有 `self.myVar`。源码在模板求值时把 `self.` 改成 `browser.`；该函数本次收到的 `browser` 参数正是执行器 `self`。因此不要把这个模板求值与浏览器原生 JS 的 `eval()` 混为一谈。

**对应的原版执行核心**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `execute_code()`。以下分别摘取各分支中的核心语句，省略日志、异常和上下文切换。

Python exec（模式5）与 eval（模式6）分别执行：

~~~python
code = readCode(code)
output = exec(code)
~~~

~~~python
code = readCode(code)
output = eval(code)
~~~

页面 JS（模式0）和带元素 JS（模式2）分别执行：

~~~python
self.browser.set_script_timeout(max_wait_time)
output = self.browser.execute_script(code)
~~~

~~~python
self.browser.set_script_timeout(max_wait_time)
output = self.browser.execute_script(code, element)
~~~

系统命令（模式1）执行并取标准输出：

~~~python
output = subprocess.run(
    code, capture_output=True, text=True, timeout=max_wait_time, shell=True)
# 输出命令返回值
output = output.stdout
~~~

各分支最终共用原来的字符串转换和返回：

~~~python
try:
    output = str(output)
except:
    output = "无法转换为字符串|Unable to convert to string"
    self.print_and_log("无法转换为字符串|Unable to convert to string", output)
return output
~~~

最后回到 `customOperation()`，把返回字符串写入输出字典；**自定义属性 `self.myVar` 的保存和输出字段的更新，是两件不同的事。** 调用与输出部分的原代码如下：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `customOperation()：代码调用与输出核心`，第 823–829、874–877、881–885 行。

~~~python
params = node["parameters"]
if params["clear"] == 1:
    self.clearOutputParameters()
codeMode = int(params["codeMode"])
code = params["code"]
output = ""
max_wait_time = int(params["waitTime"])
# ……（省略其他原代码）
else:  # 0 1 5 6
    output = self.execute_code(
        codeMode, code, max_wait_time, iframe=params["iframe"])
recordASField = bool(params["recordASField"])
# ……（省略其他原代码）
self.outputParameters[node["title"]] = output
if recordASField and params["newLine"]:
    line = new_line(self.outputParameters,
                    self.maxViewLength, self.outputParametersRecord)
    self.OUTPUT.append(line)
~~~

<a id="break-continue"></a>

### 30. BREAK / CONTINUE 怎样跨过递归函数边界

#### 30.1 BREAK 操作怎样让正在执行的循环退出

假设流程图里有一个房源循环，正常会逐条处理 A、B、C。现在希望遇到指定情况时退出这个循环，就可以在相应位置放一个 **BREAK（跳出循环）自定义操作**。

执行这个节点时，程序先设置 `self.BREAK=True`；等这次节点调用返回到 `loopExecute()`，循环检查到这个标记，才跳过剩余孩子并退出当前循环。

完整过程是：**执行 BREAK 节点 → 设置退出标记 → 逐层返回到检查标记的循环 → 清除标记并退出该循环 → 返回外层继续。**

这里要和[第 16 篇的判断分支讲解](16.Flowchart递归执行原理.md)区分：`judgeExecute()` 中找到满足条件后写的 Python `break`，只结束“检查候选分支”的 `for`，随后还会执行选中的分支。流程图中的 BREAK 节点则通过共享标记，要求 `loopExecute()` 退出它正在执行的业务循环。

#### 30.2 节点参数和设置标记的真实代码

仓库中的 [Exec and Eval.json](../../Examples/Exec%20and%20Eval.json) 就有一个真实的 BREAK 操作：`graph[9]` 是自定义操作节点，`option=5`，其 `parameters` 中的原值如下：

~~~json
{
  "codeMode": "3",
  "code": ""
}
~~~

**`option=5` 表示“自定义操作”，其中 `codeMode=3` 才表示“跳出循环”。** `code` 可以为空，程序根据模式设置标记，无需用户在代码框里写 Python 的 `break`。

`executeNode()` 先把这个节点分发给 `customOperation()`：

~~~python
# executeNode() 内部的真实分发分支
elif node["option"] == 5:  # 自定义操作，包含 BREAK、CONTINUE 等模式
    self.customOperation(node, loopValue, loopPath, index)
    self.saveData()
~~~

`customOperation()` 读取模式后，进入下面的分支。以下摘自 [easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py)，省略其他自定义操作模式：

~~~python
# customOperation() 内部
params = node["parameters"]
codeMode = int(params["codeMode"])  # JSON 中字符串 "3" 转为整数 3

if codeMode == 2:  # 针对当前循环元素执行代码
    ...  # 省略这个模式的处理，下面保留 BREAK / CONTINUE 分支
elif codeMode == 3:  # BREAK：请求跳出循环
    self.BREAK = True
    self.recordLog("跳出循环|Break the loop")
elif codeMode == 4:  # CONTINUE：请求跳过本轮剩余操作
    self.CONTINUE = True
    self.recordLog("跳过本次循环|Skip this loop")
~~~

注意这一步只设置对象上的标记，**没有在 `customOperation()` 中直接执行 Python 的 `break`**。这个函数被 `executeNode()` 调用，执行完仍按普通函数调用返回；循环在另一个函数 `loopExecute()` 里，需要由那个函数读取标记后实现退出。

#### 30.3 真正退出在哪里：先退出孩子 for，再退出业务 while

下面从 `loopExecute()` 的 `loopType=1`（不固定元素列表）分支摘取正常路径核心。`elements` 是前面已经找到的房源列表，历史记录变量也已由前置代码准备；这里省略元素失效重取、跳过项、脚本退出条件等处理：

~~~python
index = 0
while index < len(elements):  # 外层 while：逐条处理房源
    element = elements[index]

    for i in node["sequence"]:  # 内层 for：顺序执行当前房源的孩子操作
        self.executeNode(i, element, xpath, index)

        # 必须等孩子调用返回后，循环才有机会检查标记
        if self.BREAK or self.CONTINUE:
            self.CONTINUE = False
            break  # 第一个 break：退出孩子 for，本轮剩余孩子不再执行

    if self.BREAK:
        self.BREAK = False  # 清除标记，表示本循环已经处理了退出请求
        break              # 第二个 break：退出逐条处理房源的 while

    # BREAK 路径已在上面退出，不会走到本轮的这些代码
    index, elements = self.handleHistory(
        node, xpath, thisHandle, thisHistoryURL, thisHistoryLength,
        index, elements=elements)
    # ……原源码在这里还有脚本退出条件检查
    index = index + 1
~~~

这里的两次 `break` 各有作用：

| 位置 | 退出哪个循环 | 产生什么效果 |
| --- | --- | --- |
| 第一个 `break` | 遍历孩子操作的 `for` | 当前这条房源后面的孩子操作不再执行 |
| 第二个 `break` | 遍历房源元素的 `while` | 后面的房源也不再处理，当前房源循环结束 |

**只退出孩子 `for`，还不足以结束整个房源循环，所以后面还要检查一次 `self.BREAK` 并退出 `while`。** 对固定文本列表等循环，外层使用的是 `for`，同样会在孩子返回后检查标记并退出该层业务循环。

退出业务循环之后，`loopExecute()` 还会执行函数末尾的公共收尾代码，然后才返回；Python 的 `break` 本身只退出循环，不会直接退出整个函数：

~~~python
# loopExecute() 的函数末尾，各种循环类型处理后都会走到这里
self.history["index"] = thisHistoryLength
self.history["handle"] = self.browser.current_window_handle
self.scrollDown(node["parameters"])
# 函数执行到末尾，返回 executeNode()；随后再返回外层调用处
~~~

标记由最先检查到它的循环清除。该循环返回后，外层再检查时看到的已经是 `False`，所以外层可以继续自己的后续操作。这个标记没有记录“要退出第几层”，实际范围由调用返回后哪一层先读取并清除它决定。

#### 30.4 真实任务例子：检测字段连续两次相同，就退出循环

[Exec and Eval.json](../../Examples/Exec%20and%20Eval.json) 使用的就是这套机制。下面列出本例用到的真实节点；这些编号属于这份任务文件：

| 节点 | 配置与作用 |
| --- | --- |
| **0（root）** | `sequence=[5,2]`：先执行 **5（初始化变量）**，再执行 **2（固定文本列表循环）** |
| **5（初始化变量）** | 自定义 Python 操作，执行 `self.myVar = "-1"` |
| **2（循环）** | `loopType="3"`，`sequence=[1,3,6]`：**1（打开网页，节点标题为“点击元素”但 option=1）**、**3（提取数据）**、**6（判断条件）** |
| **6（判断条件）** | `sequence=[7,8]`：先检查 **7（字段相同分支）**，再检查 **8（兜底分支）** |
| **7（字段相同分支）** | `class="8"`，用 Python eval 判断 `self.myVar == self.outputParameters["检测字段"]`；选中后执行 **9（BREAK 操作）** |
| **8（兜底分支）** | `class=0`，选中后执行 **10（更新变量）** |
| **9（BREAK 操作）** | 自定义操作，`codeMode="3"`，设置 `self.BREAK=True` |
| **10（更新变量）** | 自定义 Python 操作，执行 `self.myVar = self.outputParameters["检测字段"]` |

把这份任务的业务含义展开，就是先提取本轮字段，再与上一轮保存的值比较：

~~~python
# 节点 5（初始化变量）的真实代码
self.myVar = "-1"

# 以下为每轮提取后的判断效果示意，按真实任务配置展开
if self.myVar == self.outputParameters["检测字段"]:
    # 选中节点 7（字段相同分支），执行节点 9（BREAK 操作）
    self.BREAK = True
else:
    # 选中节点 8（兜底分支），执行节点 10（更新变量）
    self.myVar = self.outputParameters["检测字段"]
# 判断返回后，外面的 loopExecute() 检查 self.BREAK，决定是否退出循环
~~~

为便于手算，假设后续各轮原本会提取到的字段依次为 `"A"、"B"、"B"、"C"`。这些字段值是解释执行过程的假设输入：

| 轮次 | 判断前保存的 myVar | 本轮检测字段 | 选择哪条分支 | 这轮之后怎样继续 |
| --- | --- | --- | --- | --- |
| 第 1 轮 | `"-1"` | `"A"` | 不相同，选 **8（兜底分支）** | **10（更新变量）**把 myVar 改为 `"A"`，继续循环 |
| 第 2 轮 | `"A"` | `"B"` | 不相同，选 **8（兜底分支）** | 把 myVar 改为 `"B"`，继续循环 |
| 第 3 轮 | `"B"` | `"B"` | 相同，选 **7（字段相同分支）** | **9（BREAK 操作）**设置标记，返回循环后退出 |
| 第 4 轮 | — | 原本可能是 `"C"` | 循环已经结束 | 不进入这一轮，也不会提取这次字段 |

第 3 轮设置标记后的返回过程是：

1. **9（BREAK 操作）**设置 `self.BREAK=True`，返回到 **7（字段相同分支）**。
2. 分支的孩子执行完，返回到 `judgeExecute()`，再由 **6（判断条件）**返回到 **2（循环）**。
3. 这次 `loopExecute()` 检查到标记，先退出孩子遍历，再清除标记并退出固定文本列表循环。
4. **2（循环）**返回到 root；这份任务 root 的孩子已执行完，随后 root 返回。

这份任务的退出条件是“当前字段与保存的上一轮字段相同”。初始化值为 `"-1"`，因此若第一轮就提取到 `"-1"`，第一轮也会满足退出条件。

#### 30.5 放在判断分支中的 BREAK，什么时候才会生效

回到房源教学例子，假设只在讲解中为单间分支添加一个新节点 **13（BREAK 操作，option=5、codeMode=3）**，希望“采完第一条单间就退出本页房源循环”。原教学模型文件保持原样，这里只推演下面的结构变体：

~~~text
graph[5] 页面循环：sequence = [6, 12]       # 6 = 房源循环，12 = 点击下一页
graph[6] 房源循环：sequence = [7]           # 7 = 判断是否为单间
graph[7] 判断：sequence = [8, 9]            # 8 = 单间分支，9 = 空的兜底分支
graph[8] 单间分支：sequence = [10, 11, 13]  # 10 = 点击房源，11 = 提取信息，13 = BREAK
~~~

处理 A 时，单间分支先点击 A、提取 A，再执行 BREAK。等整个判断调用返回到房源循环，房源循环才检查标记并退出，所以本页的 B 不再处理。

**这次退出的是节点 6（房源循环）。** 它清除标记并返回节点 5（页面循环）后，页面循环仍会继续调用下一个孩子 **12（点击下一页）**。BREAK 没有要求页面循环或地区循环同时退出。

还要注意本节源码里的位置：**房源循环因 BREAK 退出时，会跳过这一轮的 `handleHistory()`。** 如果点击 A 后浏览器还停在详情页，函数返回并不会让它自动恢复列表；外层仍会调用点击下一页，点击能否成功取决于当时的页面状态。设计退出位置时，应把需要的页面恢复操作安排完整。

如果把 BREAK 放在点击和提取之间，单间分支改成下面这样，又会发生什么？

~~~text
graph[8].sequence = [10, 13, 11]  # 10 = 点击房源，13 = BREAK，11 = 提取信息
~~~

`executeNode()` 执行 root 或条件分支的代码是：

~~~python
if node["option"] == 0 or node["option"] == 10:
    for i in node["sequence"]:
        self.executeNode(i, loopValue, loopPath, index)
        # 原源码这里没有检查 self.BREAK 或 self.CONTINUE
~~~

因此，节点 **13（BREAK）**返回后，分支的 `for` 仍然会取到 **11（提取信息）**并执行。等整个分支、整个判断都返回到房源循环后，才由房源循环读取标记并退出。

这和把 BREAK 直接放在循环体里不同：

| BREAK 放在哪里 | 标记何时被循环检查 | 后面的提取会不会执行 |
| --- | --- | --- |
| 房源循环直接孩子为 `[13（BREAK）,11（提取信息）]` | BREAK 节点返回后，循环立即检查 | **11 不执行**，当前房源循环退出 |
| 单间分支孩子为 `[10（点击房源）,13（BREAK）,11（提取信息）]` | 分支和判断全部返回到房源循环后才检查 | **11 仍会执行**，然后房源循环退出 |

**决定后续操作是否被跳过的，是设置标记后代码先返回到哪里，以及那里有没有检查标记。**

#### 30.6 CONTINUE 为什么只跳过本轮，下一轮还会继续

[172.json](../../ElectronJS/tasks/172.json) 的 **14（CONTINUE 操作）**使用下面的真实参数：

~~~json
{
  "codeMode": "4",
  "code": ""
}
~~~

它设置 `self.CONTINUE=True`。再看第 30.3 节的循环代码：孩子返回后，`if self.BREAK or self.CONTINUE` 成立，把 CONTINUE 清为 False，然后用第一个 `break` 退出孩子 `for`；接着 `self.BREAK` 为 False，不会触发退出业务 `while` 的第二个 `break`。

因此，在正常路径上，循环继续做 `handleHistory()`、脚本退出条件检查及 `index` 推进，然后处理下一条房源。与 BREAK 一样，CONTINUE 也要等调用返回到检查标记的循环才会被处理。

| 操作 | 当前轮剩余孩子 | 后面的循环项 | 本轮 handleHistory |
| --- | --- | --- | --- |
| BREAK | 检查到标记后跳过 | 当前循环不再继续 | 在本节元素列表分支中跳过 |
| CONTINUE | 检查到标记后跳过 | 正常路径进入下一项 | 正常路径仍执行 |

### 31. 滚动、等待与截图：参数分别作用在什么阶段

**从文件读取的参数示例**：[第二步：采集详情页标题内容并下载所有图片.json](../../Examples/汽车新闻采集/第二步：采集详情页标题内容并下载所有图片.json) → `graph[1].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "wait": 3,
  "scrollType": 0,
  "scrollCount": 1,
  "scrollWaitTime": 1,
  "maxWaitTime": 10
}
~~~

**大致流程**：动作完成后按 scrollType 选择滚动 → 每次滚动等待 scrollWaitTime → 次数用 scrollCount，或以文本不变退出 → 返回后做普通节点后等待；点击的等待在 clickElement 内处理。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `scrollDown()：按次数滚动核心`，第 617–628 行。

~~~python
if scrollType != 0 and param["scrollCount"] > 0:  # 控制屏幕向下滚动
    if scrollType == 1 or scrollType == 2:
        for i in range(param["scrollCount"]):
            body = self.browser.find_element(
                By.CSS_SELECTOR, "body", iframe=param["iframe"])
            if scrollType == 1:
                body.send_keys(Keys.PAGE_DOWN)
            elif scrollType == 2:
                body.send_keys(Keys.END)
            try:
                time.sleep(param["scrollWaitTime"])  # 下拉完等待
            except:
~~~

本例 scrollType=0 不主动滚动。1 发送 PAGE_DOWN，2 发送 END；3 反复比较 body 文本，文本不变则停。iframe 文本、类型 3 和异常重试的完整分支用源码链接承接。

普通节点与点击节点分别使用以下原等待位置：

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `executeNode()：节点后等待`，第 1043–1054 行。

~~~python
if node["option"] != 0 and node["option"] != 2:  # 点击元素操作单独定义等待时间操作
    waitTime = 0.01  # 默认等待0.01秒
    if node["parameters"]["wait"] >= 0:
        waitTime = node["parameters"]["wait"]
    try:
        waitType = int(node["parameters"]["waitType"])
    except:
        waitType = 0
    if waitType == 0:  # 固定等待时间
        time.sleep(waitTime)
    elif waitType == 1:  # 随机等待时间
        time.sleep(random.uniform(waitTime * 0.5, waitTime * 1.5))
~~~

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `clickElement()：点击后等待`，第 1827–1835 行。

~~~python
waitTime = float(param["wait"]) + 0.01  # 点击之后等待
try:
    waitType = int(param["waitType"])
except:
    waitType = 0
if waitType == 0:  # 固定等待时间
    time.sleep(waitTime)
elif waitType == 1:  # 随机等待时间
    time.sleep(random.uniform(waitTime * 0.5, waitTime * 1.5))
~~~

waitType=1 在原基准值的 0.5–1.5 倍间随机等待。固定/随机 sleep 都不验证结果是否已加载；滚动类型 3 也只比较一段时间内的文本变化。

#### 31.1 节点前等待元素：不要和点击后的 wait 混淆

**从文件读取的参数示例**：[221.json](../../ElectronJS/tasks/221.json) → `graph[3].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "waitElement": "",
  "waitElementTime": 10,
  "waitElementIframeIndex": 0,
  "wait": 2,
  "waitType": 0
}
~~~

**大致流程**：预处理等待配置 → 执行节点前检查 waitElement → 按配置切 iframe → 等元素存在 → 切回主文档 → 分发动作，超时按原异常路径记录后继续。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `preprocess()：等待配置`，第 283–288 行。

~~~python
if parameters.get("waitElementIframeIndex"):
    parameters["waitElementIframeIndex"] = int(parameters["waitElementIframeIndex"])
else:
    parameters["waitElement"] = ""
    parameters["waitElementTime"] = 10
    parameters["waitElementIframeIndex"] = 0
~~~

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `executeNode()：节点前等待核心`，第 975–992 行。

~~~python
if node["parameters"]["waitElement"] != "":
    waitElement = replace_field_values(
        node["parameters"]["waitElement"], self.outputParameters, self)
    waitElementTime = float(node["parameters"]["waitElementTime"])
    waitElementIframeIndex = node["parameters"]["waitElementIframeIndex"]
    self.print_and_log("等待元素出现:", waitElement)
    self.print_and_log(
        "Waiting for element to appear:", waitElement)
    if waitElementIframeIndex > 0:
        iframes = self.browser.find_elements(
            By.CSS_SELECTOR, "iframe", iframe=False)
        iframe = iframes[waitElementIframeIndex - 1]
        self.browser.switch_to.frame(iframe)
    WebDriverWait(self.browser, waitElementTime).until(
        EC.presence_of_element_located((By.XPATH, waitElement))
    )
    if waitElementIframeIndex > 0:
        self.browser.switch_to.default_content()
~~~

本例 waitElement 为空，不进入等待。主文档 waitElementIframeIndex=0 的原预处理会清空 waitElement；>0 时按 iframe 列表的 index-1 项切入。等待条件是 presence，不保证可见/可点击。详情目标等待应在采集节点前，放到点击节点上则等的是点击前页面。

#### 31.2 截图和 OCR：字段参数触发文件输出

**当前例子：采集内容不一定是 DOM 中能直接读取的文字，也可能是一张截图，或者截图里识别出来的文字。** 这里用两份原任务分别说明：`101.json` 对 `//body` 元素截图并保存 PNG；`181.json` 对当前循环元素截图，再用 OCR 识别其中的文字，它保存的文字样例是 `/手机/数码`。

| 本次要得到什么 | 对应场景 | 结果保存在哪里 |
| --- | --- | --- |
| 页面 body 元素的图像 | `contentType=7`，截图 | 写入 screenshots 下的 PNG 文件；该字段值为空字符串 |
| 元素图像中的文字 | `contentType=8`，OCR | 识别文字成为 `content`，再交给字段输出；临时识别图片会删除 |

下面先给两种场景的实际参数，再看保存截图和识别文字的核心源码。

**从文件读取的参数示例**：[101.json](../../ElectronJS/tasks/101.json) → `graph[18].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "自定义参数_3",
  "nodeType": 0,
  "contentType": 7,
  "relative": false,
  "relativeXPath": "//body",
  "default": "",
  "downloadPic": 0
}
~~~

**从文件读取的参数示例**：[181.json](../../ElectronJS/tasks/181.json) → `graph[3].parameters.params[0]`（只摘本节用到的键，值保持原样）。

~~~json
{
  "name": "参数1_文本",
  "nodeType": 0,
  "contentType": 8,
  "relative": true,
  "relativeXPath": "",
  "iframe": false,
  "default": "",
  "downloadPic": 0
}
~~~

**大致流程**：先定位字段元素 → 截图类型调整窗口、保存元素 PNG、恢复尺寸 → OCR 类型从元素截图生成临时图片、识别、删除临时文件并返回文字。

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `get_content()：截图文件输出核心`，第 1957–1959、1970–1973 行。

~~~python
size = self.browser.get_window_size()
width = size["width"]
height = size["height"]
# ……（省略其他原代码）
element.screenshot("Data/Task_" + str(self.id) + "/" + self.saveName +
                   "/screenshots/" + str(time.time()) + ".png")
# 截图完成后，将浏览器的窗口大小设置为原来的大小
self.browser.set_window_size(width, height)
~~~

**核心源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `get_content()：OCR 核心`，第 1979–1992 行。

~~~python
screenshot = element.screenshot_as_png
screenshot_stream = io.BytesIO(screenshot)
# 使用Pillow库打开截图，并转换为灰度图像
image = Image.open(screenshot_stream).convert('L')
temp_name = "OCR_" + str(time.time()) + ".png"
location = "Data/Task_" + \
           str(self.id) + "/" + self.saveName + "/" + temp_name
image.save(location)
ocr = DdddOcr(show_ad=False)
with open(location, 'rb') as f:
    image_bytes = f.read()
content = ocr.classification(image_bytes)
os.remove(location)
self.browser.set_window_size(width, height)
~~~

截图类型 7 的 content 保持空字符串；OCR 类型 8 返回识别文字，异常时原代码设 OCR Error。无头窗口尺寸计算和错误处理在原分支中，完整类型实现见 get_content。下载图片与截图/识别是不同输出动作。


---

<a id="judge-execute"></a>

## 第四部分：judgeExecute 按条件选择分支，再调用 executeNode 执行分支的孩子

### 32. 判断入口、九种条件与分支执行过程

本部分独立讲解判断条件怎样实现、从左到右怎样选择分支，以及选中后怎样执行分支中的操作。下面继续使用[房源教学模型](示例-Flowchart/房源采集-教学模型.json)中的 A、B 房源作例子；第五部分再把这些判断接到地区、页面和房源三个循环中。

#### 32.1 判断入口：先分清节点类型、条件类型和当前房源

`executeNode()` 读到 `option=9`，调用：

~~~python
self.judgeExecute(node, loopValue, loopPath, index)
~~~

到了 `judgeExecute(self, node, loopElement, clickPath="", index=0)` 中，各参数的含义是：

| 参数或字段 | 本例含义 |
| --- | --- |
| `node` | **7（判断节点）**，其 `sequence=[8,9]`：先检查 **8（单间分支）**，再检查 **9（兜底分支）** |
| `loopElement` | 房源循环传来的当前房源链接：处理 A 时就是 A，处理 B 时就是 B |
| `clickPath`、`index` | 当前房源列表的 XPath 和当前元素位置，执行选中分支时继续传下去 |
| `cnode` | 正在检查的候选分支，例如 **8（单间分支）** |
| `cnode["option"]` | 条件分支的节点类型为 **10** |
| `cnode["parameters"]["class"]` | 这条分支具体采用哪一种判断条件；源码转换为整数后保存在 `tType` 中 |

**`option=9` 是判断节点，`option=10` 是分支节点；下面的 `class=0～8` 才是九种条件类型。** 每条分支独立配置自己的条件。

判断按照 `node["sequence"]` 的顺序从左向右检查：不满足就继续检查下一条；第一个满足时记住分支并 `break`，停止检查后面的分支。**跳出条件检查后，才调用 `executeNode()` 执行选中的分支；这次判断最多执行一条分支。**

#### 32.2 条件 0：无条件，通常放在最右边作兜底

配置示例是 `parameters.class=0`。源码直接选中当前分支：

~~~python
if tType == 0:
    executeBranchId = i
    break
~~~

房源模型中，左边 **8（单间分支）**检查是否包含“单间”，右边 **9（兜底分支）**是 `class=0`。A 满足左边条件，右边根本不会检查；B 不满足左边条件，继续走到右边，兜底分支就被选中。

“无条件”只决定这条分支一定能被选中，选中后做什么仍由它的 `sequence` 决定。本例兜底分支 `sequence=[]`，所以直接返回；如果放了“记录跳过原因”等操作，就会执行那些操作。把无条件分支放到最左边，会使右边其他分支没有被检查的机会。

#### 32.3 条件 1：当前页面包括文本，读取整个 body 的文字

假设配置为：

~~~json
{"class": 1, "value": "单间"}
~~~

源码先取得页面 body 的文字，再检查目标文本是否出现：

~~~python
bodyText = self.browser.find_element(
    By.CSS_SELECTOR, "body", iframe=cnode["parameters"]["iframe"]).text
value = replace_field_values(
    cnode["parameters"]["value"], self.outputParameters, self)
if bodyText.find(value) >= 0:
    executeBranchId = i
    break
~~~

`find()` 找到文本会返回它的位置（从 0 开始），找不到返回 -1，所以这里用 `>=0` 判断满足。`replace_field_values()` 先把条件值里的字段引用替换为当前值，具体机制见第 20.1 节。

海淀第 1 页同时显示 A“海淀 单间 2500元”和 B“海淀 整租 6500元”。只要 A 的文字在页面中，整个 body 就包含“单间”；即使本轮传入的是 B，这条页面条件仍可能满足。**它适合判断“当前页是否出现某段文字”，逐条筛选房源则应使用条件 3。** 读取 body 失败时，源码的异常分支会继续检查下一条候选分支。

#### 32.4 条件 2：当前页面包括元素，按 XPath 查找元素

例如判断页面上有没有“下一页”链接，配置：

~~~json
{"class": 2, "value": "//a[@id='next']"}
~~~

实现核心是：

~~~python
xpath = replace_field_values(
    cnode["parameters"]["value"], self.outputParameters, self)
if self.browser.find_element(By.XPATH, xpath, iframe=cnode["parameters"]["iframe"]):
    executeBranchId = i
    break
~~~

页面存在匹配的 `<a id="next">` 时，`find_element()` 返回元素，当前分支被选中；找不到时会抛异常，源码捕获后 `continue`，检查右边下一条分支。这段代码判断的是元素能否被找到，代码中没有额外检查它是否可见、是否禁用或是否可以点击。若最后一页仍保留一个禁用的“下一页”链接，单凭这个 XPath 仍可能满足，需要把业务要求体现在条件中。

#### 32.5 条件 3：当前循环项包括文本，只检查这条房源

这正是房源教学模型里 **8（单间分支）**的真实配置：

~~~json
{"class": 3, "value": "单间"}
~~~

源码使用的是当前传入元素的文字：

~~~python
value = replace_field_values(
    cnode["parameters"]["value"], self.outputParameters, self)
if loopElement.text.find(value) >= 0:
    executeBranchId = i
    break
~~~

| 当前循环项 | 检查的文字 | 是否包含“单间” | 下一步 |
| --- | --- | --- | --- |
| A | “海淀 单间 2500元” | 是 | 选中 **8（单间分支）**，执行 **10（点击房源）**、**11（提取信息）** |
| B | “海淀 整租 6500元” | 否 | 跳过单间分支，检查 **9（兜底分支）** |

条件 1 的入口是 `self.browser.find_element(...body...).text`，条件 3 的入口是 `loopElement.text`；两者的检查范围不同。如果当前循环传进来的是地区文字等普通字符串，而不是网页元素，就不能按本例直接读取它的 `.text`；本分支的读取异常会使程序继续检查下一候选分支。

#### 32.6 条件 4：当前循环项包括元素，在当前元素中查找

这一小例把循环项设为房源卡片 `div`，卡片 A 内部有图片，卡片 B 没有图片：

~~~html
<div class="house"><a><img src="A.jpg"></a></div>  <!-- 当前循环项 A -->
<div class="house"><a>B：整租</a></div>              <!-- 当前循环项 B -->
~~~

按界面提供的相对路径写法，可以配置：

~~~json
{"class": 4, "value": "/*//img"}
~~~

实际源码有一个必须看清的切片操作：

~~~python
xpath = replace_field_values(
    cnode["parameters"]["value"][1:], self.outputParameters, self)
if loopElement.find_element(By.XPATH, xpath):
    executeBranchId = i
    break
~~~

`[1:]` 先去掉保存值的第一个字符，本例 `"/*//img"` 变成 `"*//img"`，再交给当前卡片的 `find_element()`。这条路径从卡片的子元素继续向下查找图片，能找到 A 卡片中嵌在 `a` 里的 `img`；B 卡片找不到，捕获异常后继续检查右边分支。界面的这项输入提示见 [FlowChart_CN.html](../../ElectronJS/src/taskGrid/FlowChart_CN.html) 的“当前循环项包括元素”。

条件 2 从浏览器页面查找，条件 4 从 `loopElement` 发起查找。实际范围还受最终 XPath 写法影响：例如 XPath 以 `//` 开头时会从文档根查找，不能只看到调用对象是元素，就认定任意路径都限制在卡片内部。本例需要同时看清保存的路径和切片后的路径。

#### 32.7 条件 5：页面 JavaScript 返回值，在浏览器中执行脚本

例如判断页面中是否有“下一页”元素，配置的代码可以写成：

~~~javascript
return document.querySelector("#next") !== null;
~~~

`parameters.class=5`，脚本保存在 `parameters.code` 中。判断函数将它交给 `execute_code()` 的模式 0：

~~~python
output = self.execute_code(
    0, cnode["parameters"]["code"], cnode["parameters"]["waitTime"],
    iframe=cnode["parameters"]["iframe"])
~~~

`execute_code()` 最终调用 `self.browser.execute_script(code)`。有该元素时，脚本返回 JS 的 `true`；Python 收到后转成字符串 `"True"`，在后面的公共判断中被当作满足。没有该元素时得到 `"False"`，不满足，继续检查下一条分支。

这里要写 `return`，把计算结果交回 Python。脚本运行在浏览器页面里，可使用 `document`；它不会自动得到当前房源元素，针对当前元素的脚本用条件 7。

#### 32.8 条件 6：系统命令返回值，读取命令的标准输出

配置 `parameters.class=6`，例如把 `parameters.code` 写成 Windows 命令：

~~~text
echo 1
~~~

判断函数调用 `execute_code()` 的模式 1：

~~~python
output = self.execute_code(
    1, cnode["parameters"]["code"], cnode["parameters"]["waitTime"],
    iframe=cnode["parameters"]["iframe"])
~~~

系统命令分支中的核心是：

~~~python
output = subprocess.run(
    code, capture_output=True, text=True, timeout=max_wait_time, shell=True)
output = output.stdout
~~~

`echo 1` 输出的 `"1\r\n"` 可转换为整数 1，满足条件；`echo 0` 输出可转换为 0，不满足。这里使用的是**标准输出内容**，不是进程退出码 `returncode`。所以“命令执行成功”并不自动意味着分支条件满足，需要让命令输出能被规则识别的结果。

#### 32.9 条件 7：当前循环项的 JavaScript 返回值，元素通过 arguments[0] 传入

仍以房源 A、B 为例，配置 `parameters.class=7`，代码可以写：

~~~javascript
return arguments[0].innerText.includes("单间");
~~~

与条件 5 相比，调用时多传入了当前房源元素：

~~~python
output = self.execute_code(
    2, cnode["parameters"]["code"], cnode["parameters"]["waitTime"], loopElement,
    iframe=cnode["parameters"]["iframe"])
~~~

`execute_code()` 的模式 2 最终执行：

~~~python
output = self.browser.execute_script(code, element)
~~~

传入的 `element` 就是这次的 `loopElement`，在 JS 中通过 `arguments[0]` 访问。处理 A 时检查 A 的 `innerText`，返回 true，选中当前分支；处理 B 时返回 false，继续检查下一分支。也可以用 JS 从当前元素继续检查相邻元素或属性，仓库的 [JS判断条件示例.json](../../Examples/JS判断条件示例.json) 就采用了这种方式。

#### 32.10 条件 8：Python eval 表达式，在执行器中计算并返回结果

[Exec and Eval.json](../../Examples/Exec%20and%20Eval.json) 的 `graph[7].parameters` 使用下面的真实条件：

~~~json
{
  "class": "8",
  "code": "self.myVar == self.outputParameters[\"检测字段\"]",
  "waitTime": 0
}
~~~

判断函数实际调用的是 `execute_code()` 的 **模式 6**：

~~~python
output = self.execute_code(
    6, cnode["parameters"]["code"], cnode["parameters"]["waitTime"], loopElement,
    iframe=cnode["parameters"]["iframe"])
~~~

随后在 Python 执行器中计算：

~~~python
code = readCode(code)
output = eval(code)
~~~

例如当前 `self.myVar="B"`：若 `self.outputParameters["检测字段"]` 也是 `"B"`，表达式返回 True，这条分支满足；若字段值是 `"C"`，返回 False，继续检查下一条。在该真实任务中，相同分支里放的是 BREAK 操作，不同分支里放的是更新 `self.myVar` 的操作。

**源码在 `tType==8` 旁的旧注释写着“System”，但实际调用模式 6，执行的是 Python `eval`。** 这里填写 Python 表达式，可以直接读取执行器的 `self`，例如 `self.myVar == 1`；无需写 JS 的 `return`，也不能把赋值语句 `self.myVar = 1` 当作这个条件表达式。赋值应使用第 29.2 节的自定义 Python exec 操作。

#### 32.11 条件 5～8 共用的返回值规则：为什么 true 或正整数会满足

上面四种执行环境虽然不同，`execute_code()` 最后都会把结果转换成字符串。`judgeExecute()` 再使用同一段原代码决定是否满足：

~~~python
try:
    if output.find("rue") != -1:
        code = 1
    else:
        code = int(output)
except:
    code = 0
if code > 0:
    executeBranchId = i
    break
~~~

| execute_code 返回的字符串 | 如何处理 | 条件是否满足 |
| --- | --- | --- |
| `"True"` 或 `"true"` | 包含子串 `rue`，设为 1 | 满足 |
| `"False"` | 不含 `rue`，转整数失败，设为 0 | 不满足 |
| `"1"`、`"2"` | 转成正整数 | 满足 |
| `"0"`、`"-1"` | 转整数后不大于 0 | 不满足 |
| `"0.5"` | 按 `int(output)` 转换失败，设为 0 | 不满足 |
| 空字符串或普通说明文字 | 不能转整数，且没有 `rue` 时设为 0 | 不满足 |

这里按原码查找的是子串 `rue`，并未严格判断字符串是否等于 `"true"`。下面的两个编号也要区分：

| 分支条件 class | 交给 execute_code 的 codeMode | 实际执行方式 |
| --- | --- | --- |
| 5 | 0 | 页面 JavaScript |
| 6 | 1 | 系统命令，取标准输出 |
| 7 | 2 | JavaScript，带当前循环元素 |
| 8 | 6 | Python eval |

#### 32.12 最后看完整原方法：选好分支后，统一交回 executeNode

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `BrowserThread.judgeExecute()`，第 1058–1138 行（完整原方法；仅移除统一的外围缩进，执行语句保持原样；其中条件 8 的原注释含义已在上文说明）。

~~~python
def judgeExecute(self, node, loopElement, clickPath="", index=0):
    if self.shutdown_event.is_set():
        return
    self.event.wait()
    executeBranchId = 0  # 要执行的BranchId
    for i in node["sequence"]:
        cnode = self.procedure[i]  # 获得条件分支
        tType = int(cnode["parameters"]["class"])  # 获得判断条件类型
        if tType == 0:  # 什么条件都没有
            executeBranchId = i
            break
        elif tType == 1:  # 当前页面包含文本
            try:
                bodyText = self.browser.find_element(
                    By.CSS_SELECTOR, "body", iframe=cnode["parameters"]["iframe"]).text
                value = replace_field_values(
                    cnode["parameters"]["value"], self.outputParameters, self)
                if bodyText.find(value) >= 0:
                    executeBranchId = i
                    break
            except:  # 找不到元素下一个条件
                continue
        elif tType == 2:  # 当前页面包含元素
            try:
                xpath = replace_field_values(
                    cnode["parameters"]["value"], self.outputParameters, self)
                if self.browser.find_element(By.XPATH, xpath, iframe=cnode["parameters"]["iframe"]):
                    executeBranchId = i
                    break
            except:  # 找不到元素或者xpath写错了，下一个条件
                continue
        elif tType == 3:  # 当前循环元素包括文本
            try:
                value = replace_field_values(
                    cnode["parameters"]["value"], self.outputParameters, self)
                if loopElement.text.find(value) >= 0:
                    executeBranchId = i
                    break
            except:  # 找不到元素或者xpath写错了，下一个条件
                continue
        elif tType == 4:  # 当前循环元素包括元素
            try:
                xpath = replace_field_values(
                    cnode["parameters"]["value"][1:], self.outputParameters, self)
                if loopElement.find_element(By.XPATH, xpath):
                    executeBranchId = i
                    break
            except:  # 找不到元素或者xpath写错了，下一个条件
                continue
        elif tType <= 8:  # JS命令返回值
            if tType == 5:  # JS命令返回值等于
                output = self.execute_code(
                    0, cnode["parameters"]["code"], cnode["parameters"]["waitTime"],
                    iframe=cnode["parameters"]["iframe"])
            elif tType == 6:  # System
                output = self.execute_code(
                    1, cnode["parameters"]["code"], cnode["parameters"]["waitTime"],
                    iframe=cnode["parameters"]["iframe"])
            elif tType == 7:  # 针对当前循环项的JS命令返回值
                output = self.execute_code(
                    2, cnode["parameters"]["code"], cnode["parameters"]["waitTime"], loopElement,
                    iframe=cnode["parameters"]["iframe"])
            elif tType == 8:  # 针对当前循环项的System命令返回值
                output = self.execute_code(
                    6, cnode["parameters"]["code"], cnode["parameters"]["waitTime"], loopElement,
                    iframe=cnode["parameters"]["iframe"])
            try:
                if output.find("rue") != -1:  # 如果返回值中包含true
                    code = 1
                else:
                    code = int(output)
            except:
                code = 0
            if code > 0:
                executeBranchId = i
                break
    if executeBranchId != 0:
        self.executeNode(executeBranchId, loopElement, clickPath, index)
    else:
        self.recordLog(
            "判断条件内所有条件分支的条件都不满足|None of the conditions in the judgment condition are met")
~~~

在房源模型中，条件 3 满足时选中 **8（单间分支）**；末尾的 `self.executeNode(executeBranchId, loopElement, clickPath, index)` 便调用这个分支。`executeNode()` 读到分支的 `option=10`，再遍历它的 `sequence=[10,11]`，按顺序执行 **10（点击房源）**和 **11（提取信息）**。

条件不满足时，继续检查 **9（兜底分支）**；它的 `class=0` 无条件满足，但 `sequence=[]`，所以不执行具体操作，直接返回。如果没有任何分支满足，`executeBranchId` 保持 0，记录日志后返回。这里的初值 0 表示“尚未选中分支”，不会因此执行 root。

选中的分支完成后，判断返回到调用它的房源循环，房源循环再做历史恢复并继续下一条房源。分支内的 BREAK / CONTINUE 如何改变循环执行，见[第 30 节](#break-continue)。**`judgeExecute()` 负责选择，分支的 `executeNode()` 负责顺序执行孩子，外层的 `loopExecute()` 负责推进到下一项。**

## 第五部分：把原版执行器接成完整采集调用链

### 33. 海淀、朝阳，只采 A、C、E

**从文件读取的参数示例**：[房源采集-教学模型.json](../../Docs/讲义/示例-Flowchart/房源采集-教学模型.json) → `graph[2].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 3,
  "textList": "海淀\n朝阳"
}
~~~

本节把前面的原版函数接到房源教学模型上。模型用于手算结构，不能直接导入执行；假定两轮都存在下一页按钮、节点正常返回、字段路径有效。下面不再用另一份手写 Selenium 采集程序描述 EasySpider，而是直接读原执行器如何解释 graph。

**一、run 按任务网址启动根节点，并完成保存与收尾。**

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `BrowserThread.run()`，第 501–551 行（完整原方法；仅移除统一的外围缩进，并补充 ⭐️⭐️⭐️ 讲解注释；执行语句不变）。

~~~python
def run(self):
    # 挨个执行程序
    for i in range(len(self.links)):
        if self.shutdown_event.is_set():
            self.print_and_log("接收到终止信号，正在中断任务... | Received termination signal, interrupting task...")
            break
        self.event.wait()  # 暂停/恢复
        self.urlId = i  # ⭐️⭐️⭐️任务网址循环先确定当前网址；下一句再从 root 执行本轮完整任务
        self.executeNode(0)  # ⭐️⭐️⭐️当前网址已确定，这里执行 root，按任务结构依次完成打开、循环、输入、点击和采集
    # files = os.listdir("Data/Task_" + str(self.id) + "/" + self.saveName)
    # 如果目录为空，则删除该目录
    # if not files:
    #     os.rmdir("Data/Task_" + str(self.id) + "/" + self.saveName)
    if self.shutdown_event.is_set():
        self.print_and_log("任务已中断 | Task interrupted")
    else:
        self.print_and_log("Done!")
        self.print_and_log("执行完成！")
        self.saveData(exit=True)
        self.removeDuplicateData()

    if self.outputFormat == "mysql":
        self.mysql.close()

    if not self.shutdown_event.is_set():
        try:
            quitWaitTime = self.service["quitWaitTime"]
        except:
            quitWaitTime = 60
        self.print_and_log(f"任务执行完毕，将在{quitWaitTime}秒后自动退出浏览器并清理临时用户目录，等待时间可在保存任务对话框中设置。")
        self.print_and_log(f"The task is completed, the browser will exit automatically and the temporary user directory will be cleaned up after {quitWaitTime} seconds, the waiting time can be set in the save task dialog.")

        # 使退出前的等待可被中断
        wait_end_time = time.time() + quitWaitTime
        while time.time() < wait_end_time:
            if self.shutdown_event.is_set():
                break
            time.sleep(0.1)

    try:
        self.browser.quit()
    except:
        pass
    self.print_and_log("正在清理临时用户目录……|Cleaning up temporary user directory...")
    try:
        shutil.rmtree(self.option["tmp_user_data_folder"])
    except:
        pass
    self.monitor_event.set()
    self.print_and_log("清理完成！|Clean up completed!")
    self.print_and_log("您现在可以安全的关闭此窗口了。|You can safely close this window now.")
~~~

self.urlId 指定本轮任务网址，self.executeNode(0) 从 graph[0] 的 root 开始。root 的 sequence=[1,2]，因此先执行打开网页 1，再执行地区循环 2。正常结束走 saveData(exit=True) 与去重，再按配置等待、退出浏览器和清理；停止分支按原代码跳过正常完成的保存逻辑。

**二、executeNode 按节点 option 分发；root 和条件分支顺序执行自己的孩子。**

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `BrowserThread.executeNode()`，第 965–1055 行（完整原方法；仅移除统一的外围缩进，并补充 ⭐️⭐️⭐️ 讲解注释；执行语句不变）。

~~~python
def executeNode(self, nodeId, loopValue="", loopPath="", index=0):
    if self.shutdown_event.is_set():
        return
    self.event.wait()
    node = self.procedure[nodeId]
    # WebDriverWait(self.browser, 10).until
    # # 等待元素出现才进行操作，10秒内未出现则报错
    # (EC.visibility_of_element_located(
    #     (By.XPATH, node["parameters"]["xpath"])))
    try:
        if node["parameters"]["waitElement"] != "":
            waitElement = replace_field_values(
                node["parameters"]["waitElement"], self.outputParameters, self)
            waitElementTime = float(node["parameters"]["waitElementTime"])
            waitElementIframeIndex = node["parameters"]["waitElementIframeIndex"]
            self.print_and_log("等待元素出现:", waitElement)
            self.print_and_log(
                "Waiting for element to appear:", waitElement)
            if waitElementIframeIndex > 0:
                iframes = self.browser.find_elements(
                    By.CSS_SELECTOR, "iframe", iframe=False)
                iframe = iframes[waitElementIframeIndex - 1]
                self.browser.switch_to.frame(iframe)
            WebDriverWait(self.browser, waitElementTime).until(
                EC.presence_of_element_located((By.XPATH, waitElement))
            )
            if waitElementIframeIndex > 0:
                self.browser.switch_to.default_content()
    except Exception as e:
        if waitElement != "":
            self.print_and_log("等待元素出现超时：", waitElement, "，将继续执行。")
            self.print_and_log("Timeout waiting for element to appear:",
                               waitElement, ", will continue to execute.")
            self.recordLog(e)
        self.recordLog("Wait element not found")
    self.recordLog("执行节点|Execute node:", node["title"])
    try:
        # 根据不同选项执行不同操作
        if node["option"] == 0 or node["option"] == 10:  # root操作,条件分支操作
            for i in node["sequence"]:  # 从根节点开始向下读取
                self.executeNode(i, loopValue, loopPath, index)  # ⭐️⭐️⭐️这里顺序执行当前 root 或分支中的孩子，继续传递原循环上下文；具体动作由孩子 option 决定
        elif node["option"] == 1:  # 打开网页操作
            # if not (nodeId == 1 and self.service["cloudflare"] == 1):
            self.openPage(node["parameters"], loopValue)
        elif node["option"] == 2:  # 点击元素
            self.clickElement(node["parameters"], loopValue, loopPath, index)
        elif node["option"] == 3:  # 提取数据
            # 针对提取数据操作，设置操作开始的步骤，用于不小心关闭后的恢复的增量采集
            if self.totalSteps >= self.startSteps:
                self.getData(node["parameters"], loopValue, node["isInLoop"],
                            parentPath=loopPath, index=index)
                self.saveData()
            else:
                # self.getDataStep += 1
                self.print_and_log("跳过第" + str(self.totalSteps) + "次提取数据。")
                self.print_and_log(
                    "Skip the " + str(self.totalSteps) + "th data extraction.")
            self.totalSteps += 1  # 总步数加一
        elif node["option"] == 4:  # 输入文字
            self.inputInfo(node["parameters"], loopValue)
        elif node["option"] == 5:  # 自定义操作
            self.customOperation(node, loopValue, loopPath, index)
            self.saveData()
        elif node["option"] == 6:  # 切换下拉框
            self.switchSelect(node["parameters"], loopValue)
        elif node["option"] == 7:  # 鼠标移动到元素上
            self.moveToElement(node["parameters"], loopValue, loopPath, index)
        elif node["option"] == 8:  # 循环
            self.loopExecute(node, loopValue, loopPath, index)  # 执行循环
        elif node["option"] == 9:  # 条件分支
            self.judgeExecute(node, loopValue, loopPath, index)
    except Exception as e:
        if self.shutdown_event.is_set(): return
        self.print_and_log("执行节点<" + node["title"] + ">时出错，将继续执行，错误为：", e)
        self.print_and_log("Error executing node <" + node["title"] + ">, will continue to execute, error is:", e)


    # 执行完之后进行等待
    if node["option"] != 0 and node["option"] != 2:  # 点击元素操作单独定义等待时间操作
        waitTime = 0.01  # 默认等待0.01秒
        if node["parameters"]["wait"] >= 0:
            waitTime = node["parameters"]["wait"]
        try:
            waitType = int(node["parameters"]["waitType"])
        except:
            waitType = 0
        if waitType == 0:  # 固定等待时间
            time.sleep(waitTime)
        elif waitType == 1:  # 随机等待时间
            time.sleep(random.uniform(waitTime * 0.5, waitTime * 1.5))
    self.event.wait()  # 等待事件结束
~~~

这里使用原数组下标和原 sequence，不把 graph 编译成手写的 for area/for page 程序。输入节点 3 调 inputInfo，点击节点 4/10/12 调 clickElement，采集节点 11 调 getData；容器分别调用 loopExecute、judgeExecute。

**重点：调用孩子时，后三个参数携带的是“当前这一层、当前这一轮”的上下文。节点编号决定执行什么操作，循环上下文决定这次操作针对什么对象。**

下面用具体实参对照；`house_a`、`house_b`、`next_button` 分别代表 Selenium 查到的 A 链接、B 链接和下一页元素：

~~~python
self.executeNode(3, "海淀", "", 0)                         # 3 = 输入地区，本次输入海淀
self.executeNode(3, "朝阳", "", 0)                         # 3 = 输入地区，下一地区轮次输入朝阳
self.executeNode(7, house_a, "//a[@class='house']", 0)       # 7 = 判断，本次检查第 1 个房源 A
self.executeNode(7, house_b, "//a[@class='house']", 1)       # 7 = 判断，下次检查第 2 个房源 B
self.executeNode(12, next_button, "//a[@id='next']", 0)      # 12 = 点击下一页，使用页面循环的上下文
~~~

这些调用展示不同执行时刻的实参。**`loopValue` 可以是地区文字，也可以是网页元素；`loopPath` 是当前循环的定位路径；`index` 在元素列表中从 0 开始，本例文本循环与单元素循环则固定传 0。** 它不是节点编号，也不是通用的循环轮次。

进入更内层循环时，内层会查找自己的对象并重新准备这三个参数；返回外层时，外层继续使用自己保留的参数。例如，房源 B 的 `index=1` 不会把下一页点击的 `index` 改成 1。完整展开见[第 16 篇的循环上下文例子](16.Flowchart递归执行原理.md#loop-context)，第四部分的判断和下面三个循环都按这一点来读。

**三、地区循环用原 loopType=3 分支把“海淀”“朝阳”传给孩子。**

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：原固定文本列表分支`，第 1454–1487 行（连续原码节选；其余上下文未展示；仅移除统一的外围缩进，并补充 ⭐️⭐️⭐️ 讲解注释；执行语句不变）。

~~~python
elif int(node["parameters"]["loopType"]) == 3:  # 固定文本列表
    textList = node["parameters"]["textList"].split("\n")
    if len(textList) == 1:  # 如果固定文本列表只有一行，现在就可以替换变量
        textList = replace_field_values(
            node["parameters"]["textList"], self.outputParameters, self).split("\n")
    skipCount = node["parameters"]["skipCount"]
    index = 0
    for text in textList:  # ⭐️⭐️⭐️这是父文本循环，本轮上下文是 text；取出当前文本后，再由 executeNode 执行孩子操作
        if self.shutdown_event.is_set():
            break
        if index < skipCount:
            index += 1
            self.print_and_log("跳过第" + str(index) + "个文本")
            self.print_and_log("Skip the " + str(index) + "th text")
            continue
        text = replace_field_values(text, self.outputParameters, self)
        # self.recordLog("当前循环文本|Current loop text:", text)
        for i in node["sequence"]:  # 挨个执行操作
            self.executeNode(i, text, "", 0)  # ⭐️⭐️⭐️这里把本轮地区 text 交给孩子，依次执行输入地区、点击搜索和页面循环
            if self.BREAK or self.CONTINUE:  # 如果有break操作，下面的操作不执行
                self.CONTINUE = False
                break
        if self.BREAK:
            self.BREAK = False
            break
        if int(node["parameters"]["breakMode"]) > 0:  # 如果设置了退出循环的脚本条件
            output = self.execute_code(int(
                node["parameters"]["breakMode"]) - 1, node["parameters"]["breakCode"],
                                       node["parameters"]["breakCodeWaitTime"],
                                       iframe=node["parameters"]["iframe"])
            code = get_output_code(output)
            if code <= 0:
                break
        index, _ = self.handleHistory(node, "", thisHandle, thisHistoryURL, thisHistoryLength, index)
~~~

模型地区循环 sequence=[3,4,5]。每轮先输入地区、点击搜索，再完成整个页面循环。输入 useLoop=true，因此第 22 节原 inputInfo 使用本轮 text。

**四、页面循环用原 loopType=0 分支，每轮先处理本页房源，再点下一页。**

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：原单元素循环完整分支`，第 1259–1354 行（连续原码节选；其余上下文未展示；仅移除统一的外围缩进，并补充 ⭐️⭐️⭐️ 讲解注释；执行语句不变）。

~~~python
elif int(node["parameters"]["loopType"]) == 0:  # 单个元素循环
    # 无跳转标签页操作
    count = 0  # 执行次数
    bodyText = "-"

    while True:  # do while循环
        if self.shutdown_event.is_set():
            break
        try:
            finished = False
            if node["parameters"]["exitCount"] == 0:
                # newBodyText = self.browser.find_element(By.XPATH, node["parameters"]["exitElement"], iframe=node["parameters"]["iframe"]).text
                # 用find_elements获取所有匹配到的文本
                try:
                    exitElements = self.browser.find_elements(By.XPATH, node["parameters"]["exitElement"], iframe=node["parameters"]["iframe"])
                    newBodyText = ""
                    for exitElement in exitElements:
                        newBodyText += exitElement.text
                except Exception as e:
                    self.print_and_log(f"设定的退出循环元素：{node['parameters']['exitElement']}的文本无法获取，本次循环将不再检测元素文本是否变化，将会继续执行，为解决此问题，您可以修改检测元素文本不变的元素为其他元素，或者将循环次数设定为固定次数大于0的值。")
                    self.print_and_log(f"The text of the exit loop element set: {node['parameters']['exitElement']} cannot be obtained, this loop will no longer check whether the text of the element has changed, and will continue to execute. To solve this problem, you can modify the element whose text does not change to other elements, or set the number of loops to a fixed number greater than 0.")
                    self.print_and_log(e)
                    exitElements = []
                    # newBodyText为随机文本，保证一直执行
                    newBodyText = str(random.random())
                if node["parameters"]["iframe"]:  # 如果标记了iframe
                    iframes = self.browser.find_elements(
                        By.CSS_SELECTOR, "iframe", iframe=False)
                    for iframe in iframes:
                        self.browser.switch_to.default_content()
                        self.browser.switch_to.frame(iframe)
                        iframe_text = super(self.browser.__class__, self.browser).find_element(
                            By.CSS_SELECTOR, "body").text  # 用super调用父类的方法
                        newBodyText += iframe_text
                        self.browser.switch_to.default_content()
                if newBodyText == bodyText:  # 如果页面内容无变化
                    self.print_and_log("页面已检测不到新内容，停止循环。")
                    self.print_and_log(
                        "No new content detected on the page, stop loop.")
                    finished = True
                    break
                else:
                    self.print_and_log("检测到页面变化，继续循环。")
                    self.print_and_log(
                        "Page changed detected, continue loop.")
                    bodyText = newBodyText
            xpath = replace_field_values(
                node["parameters"]["xpath"], self.outputParameters, self)
            # self.recordLog("循环元素|Loop element:", xpath)
            element = self.browser.find_element(
                By.XPATH, xpath, iframe=node["parameters"]["iframe"])  # ⭐️⭐️⭐️这是单元素父循环，每轮先找到当前页的下一页元素；还没有点击
            for i in node["sequence"]:  # 挨个执行操作
                self.executeNode(
                    i, element, xpath, 0)  # ⭐️⭐️⭐️当前页元素已找到，这里执行孩子：先循环处理本页房源，再点击下一页；索引固定传 0
                if self.BREAK or self.CONTINUE:  # 如果有break操作，下面的操作不执行
                    self.CONTINUE = False
                    break
            if self.BREAK:  # 如果有break操作，退出循环
                self.BREAK = False
                finished = True
                break
            finished = True
        except NoSuchElementException:
            # except:
            self.print_and_log("Single loop element not found: ",
                               xpath)
            self.print_and_log("找不到要循环的单个元素: ", xpath)
            for i in node["sequence"]:  # 不带点击元素的把剩余的如提取数据的操作执行一遍
                if node["option"] != 2:
                    self.executeNode(
                        i, None, xpath, 0)  # ⭐️⭐️⭐️这是异常路径，传入 None 继续尝试孩子操作；此时没有找到可用的父元素
            finished = True
            break  # 如果找不到元素，退出循环
        finally:
            if not finished:
                self.print_and_log("\n\n-------Retrying-------\n\n")
                self.print_and_log("-------Retrying-------: ",
                                   node["parameters"]["xpath"])
                for i in node["sequence"]:  # 不带点击元素的把剩余的如提取数据的操作执行一遍
                    if node["option"] != 2:
                        self.executeNode(
                            i, None, xpath, 0)  # ⭐️⭐️⭐️这是异常路径，传入 None 继续尝试孩子操作；此时没有找到可用的父元素
                break  # 如果找不到元素，退出循环
        count = count + 1
        self.print_and_log("Page: ", count)
        # self.print_and_log(node["parameters"]["exitCount"], "-------")
        if node["parameters"]["exitCount"] == count:  # 如果达到设置的退出循环条件的话
            break
        if int(node["parameters"]["breakMode"]) > 0:  # 如果设置了退出循环的脚本条件
            output = self.execute_code(int(
                node["parameters"]["breakMode"]) - 1, node["parameters"]["breakCode"],
                                       node["parameters"]["breakCodeWaitTime"],
                                       iframe=node["parameters"]["iframe"])
            code = get_output_code(output)
            if code <= 0:
                break
~~~

模型页面循环 sequence=[6,12]、exitCount=2。原 count 在一轮孩子执行后增加；每地区执行两轮“房源循环 + 点击下一页”，最后一轮仍点击下一页。找不到按钮的异常路径也按上面的原代码处理，不能用手写的“最后一页不点击”逻辑替代。

**五、房源循环用原 loopType=1 分支，把当前链接交给判断孩子。**

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：原不固定元素列表完整分支`，第 1355–1407 行（连续原码节选；其余上下文未展示；仅移除统一的外围缩进，并补充 ⭐️⭐️⭐️ 讲解注释；执行语句不变）。

~~~python
elif int(node["parameters"]["loopType"]) == 1:  # 不固定元素列表
    try:
        xpath = replace_field_values(
            node["parameters"]["xpath"], self.outputParameters, self)
        elements = self.browser.find_elements(By.XPATH,
                                              xpath, iframe=node["parameters"]["iframe"])
        # self.recordLog("循环元素|Loop element:", xpath)
        if len(elements) == 0:
            self.print_and_log("Loop element not found: ",
                               xpath)
            self.print_and_log("找不到循环元素：", xpath)
        index = 0
        skipCount = node["parameters"]["skipCount"]
        while index < len(elements):
            if self.shutdown_event.is_set():
                break
            if index < skipCount:
                index += 1
                self.print_and_log("跳过第" + str(index) + "个元素")
                self.print_and_log("Skip the " + str(index) + "th element")
                continue
            try:
                element = elements[index]  # ⭐️⭐️⭐️注意这里在 parent（父元素）循环中，先取出本轮的当前房源链接父元素；具体操作随后由 executeNode 执行
                element_text = element.text
            except StaleElementReferenceException: # 如果元素已经失效，重试
                self.print_and_log("元素已失效，重新获取元素|Element has expired, reacquiring element")
                elements = self.browser.find_elements(By.XPATH,
                                                      xpath, iframe=node["parameters"]["iframe"])
                element = elements[index]  # ⭐️⭐️⭐️元素失效重取后，仍按 index 选出当前房源链接父元素；具体操作随后由 executeNode 执行
            for i in node["sequence"]:  # 挨个顺序执行循环里所有的操作
                self.executeNode(i, element,
                                 xpath, index)  # ⭐️⭐️⭐️当前房源链接父元素已选好，这里先执行判断孩子7，满足条件时才进入详情并采集
                if self.BREAK or self.CONTINUE:  # 如果有break操作，下面的操作不执行
                    self.CONTINUE = False
                    break
            if self.BREAK:
                self.BREAK = False
                break
            index, elements = self.handleHistory(node, xpath, thisHandle, thisHistoryURL, thisHistoryLength, index, elements=elements)
            if int(node["parameters"]["breakMode"]) > 0:  # 如果设置了退出循环的脚本条件
                output = self.execute_code(int(
                    node["parameters"]["breakMode"]) - 1, node["parameters"]["breakCode"],
                                           node["parameters"]["breakCodeWaitTime"],
                                           iframe=node["parameters"]["iframe"])
                code = get_output_code(output)
                if code <= 0:
                    break
            index = index + 1
    except NoSuchElementException:
        self.print_and_log("Loop element not found: ", xpath)
        self.print_and_log("找不到循环元素：", xpath)
    except Exception as e:
        raise
~~~

模型房源循环 sequence=[7]。原 index 选择当前链接，executeNode(7, element, xpath, index) 把上下文交给判断；一轮结束的 handleHistory 恢复页面，再继续下一个链接。元素失效、跳过项和循环控制都保持原实现。

房源循环把当前链接交给 **7（判断节点）**后，条件检查及分支执行使用[第四部分的完整 judgeExecute 原方法](#judge-execute)：单间执行 **8（单间分支）**内的 **10（点击房源）**、**11（提取信息）**；整租执行 **9（空兜底分支）**。判断及分支返回后，房源循环再恢复列表、推进到下一条房源。

模型只配置了“标题”提取字段。按 dataset 与正常路径假设，满足条件的记录是：

| 房源 | 链接文字 |
| --- | --- |
| A | 海淀 单间 2500元 |
| C | 海淀 单间 2800元 |
| E | 朝阳 单间 3000元 |

~~~text
run → executeNode(0)
  → 打开网页
  → 地区 loopExecute（海淀、朝阳）
    → inputInfo → clickElement 搜索
    → 页面 loopExecute（两轮）
      → 房源 loopExecute（逐条链接）
        → judgeExecute（当前链接是否包含“单间”）
          → 选中分支的 executeNode → clickElement → getData → 输出行缓存
        → handleHistory → 下一个链接
      → clickElement 下一页 → 页面循环计数
  → saveData(exit=True) → 原 run 收尾
~~~

取值、字段字典、行组装和写盘分别使用第 19.1、25、26 节的原实现。第 15 篇已经推导这份 graph 怎样存，第 16 篇已经跟踪调用、返回和执行器生命周期；浏览器的历史恢复统一见本篇第 24 节。

### 34. 练习与源码阅读顺序

**从文件读取的参数示例**：[房源采集-教学模型.json](../../Docs/讲义/示例-Flowchart/房源采集-教学模型.json) → `graph[5].parameters`（只摘本节用到的键，值保持原样）。

~~~json
{
  "loopType": 0,
  "xpath": "//a[@id='next']",
  "exitCount": 2
}
~~~

本节将练习对应到真实调用入口和各原方法。先确认线程怎样启动，再沿上节完整 executeNode 分发找到具体实现；本地练习页仍可辅助观察 Selenium API，但原任务执行以本章的原版函数为准。

原主入口先建立已放行的暂停 Event，创建 BrowserThread 并启动：

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `__main__：原任务线程创建与启动`，第 2649–2655 行（连续原码节选；其余上下文未展示；仅移除统一的外围缩进，并补充 ⭐️⭐️⭐️ 讲解注释；执行语句不变）。

~~~python
event = Event()
event.set()
thread = BrowserThread(browser_t, id, service,
                       c.version, event, c.saved_file_name, config=config, option=tmp_options[i], shutdown_event=shutdown_event, commandline_config=c)
print("Thread with task id: ", id, " is created")
threads.append(thread)
thread.start()
~~~

线程 run 的根节点调用、全部动作分发和收尾已经在第 33 节给出完整源码。页面循环的固定次数退出实现是下面这段原代码；它在循环体之后计数，不能解释成翻页之前的计数：

**原版源码**：[easyspider_executestage.py](../../ExecuteStage/easyspider_executestage.py) → `loopExecute()：原单元素循环计数与退出检查`，第 1342–1354 行（连续原码节选；其余上下文未展示；仅移除统一的外围缩进，并补充 ⭐️⭐️⭐️ 讲解注释；执行语句不变）。

~~~python
count = count + 1
self.print_and_log("Page: ", count)
# self.print_and_log(node["parameters"]["exitCount"], "-------")
if node["parameters"]["exitCount"] == count:  # 如果达到设置的退出循环条件的话
    break
if int(node["parameters"]["breakMode"]) > 0:  # 如果设置了退出循环的脚本条件
    output = self.execute_code(int(
        node["parameters"]["breakMode"]) - 1, node["parameters"]["breakCode"],
                               node["parameters"]["breakCodeWaitTime"],
                               iframe=node["parameters"]["iframe"])
    code = get_output_code(output)
    if code <= 0:
        break
~~~

按下面顺序核对参数、原代码与可观察结果：

| 练习 | 参数或状态 | 对应原源码实现 |
| --- | --- | --- |
| 普通输入与批量输入 | useLoop、value、index、循环 textList | 第 22 节 inputInfo；第 33 节 loopType=3 |
| 三种点击定位 | 普通 xpath、空循环后缀、非空循环后缀 | 第 23 节 clickElement、loopType=1 |
| 输出值到文件 | 字段 name、recordASField、newLine、saveThreshold | 第 19.1 节初始化、new_line、saveData、write_to_csv |
| 多字段和相对采集 | params、relative、relativeXPath | 第 25.4 节 getData；第 26 节 get_content |
| iframe 搜索 | iframe 与浏览器当前文档 | 第 28 节 MyChrome.find_element；第 31.1 节等待分支 |
| 自定义操作 | codeMode、code、recordASField | 第 29.2 节 customOperation → execute_code |
| 滚动和等待 | scrollType/count/wait、waitType、waitElement | 第 30、30.1 节 scrollDown、executeNode 与 clickElement |
| 截图和 OCR | contentType=7/8 | 第 31.2 节 get_content 的两个原分支 |
| 回到列表继续下一项 | thisHandle、history、index | 第 24 节 loopExecute → handleHistory |
| 两层优化 | optimizable 与 quickExtractable | 第 27 节 preprocess、getData、loopExecute |
| 嵌套循环与条件返回 | sequence、loopType、class | 第 33 节 executeNode、loopExecute；第 32 节 judgeExecute |

练习：用本节 JSON 的 exitCount=2，指出原代码什么时候 count 加一，第二轮末尾是否仍执行下一页点击；再用第 33 节的五个房源，逐项解释为什么最终是 A、C、E。若把条件 value 改为“整租”作为参数练习，按第 32 节的原 judgeExecute 分支预测 B、D；无需另写一个判断算法。

每读一个方法，先读真实参数，再确认上一级实际传入的 loopValue/loopPath/index，最后跟到浏览器调用、返回值与输出缓存。此处代码都按当前仓库原实现摘录，不增加自写循环、等待或恢复函数。

---

返回目录：[README.md](README.md) ｜ 上一篇：[16.Flowchart 与 Python 执行器：递归、控制流与数据落盘](16.Flowchart递归执行原理.md) ｜ 下一篇：[18.流程图核心数据结构：稳定下标与界面编号](18.流程图核心数据结构.md)
