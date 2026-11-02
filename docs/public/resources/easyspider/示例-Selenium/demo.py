"""第 15 篇的本地 Selenium 操作样例。先启动 README 中的 HTTP 服务。"""
import argparse
import csv
import os
from pathlib import Path
from urllib.request import urlopen

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE = os.environ.get('SELENIUM_DEMO_URL', 'http://127.0.0.1:8765').rstrip('/') + '/'
OUTPUT = Path(__file__).resolve().parent / 'output'


def create_driver(headless=False):
    OUTPUT.mkdir(exist_ok=True)
    options = webdriver.ChromeOptions()
    options.add_argument('--window-size=1280,1000')
    if headless:
        options.add_argument('--headless')
    if os.environ.get('SELENIUM_BROWSER'):
        options.binary_location = os.environ['SELENIUM_BROWSER']
    options.add_experimental_option('prefs', {
        'download.default_directory': str(OUTPUT),
        'download.prompt_for_download': False,
    })
    if os.environ.get('SELENIUM_DRIVER'):
        service = Service(os.environ['SELENIUM_DRIVER'])
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(10)
    return driver


def reset(driver):
    driver.switch_to.default_content()
    driver.get(BASE + 'index.html')
    WebDriverWait(driver, 5).until(
        lambda d: '第1页' in d.find_element(By.ID, 'status').text)


def search(driver, area):
    box = driver.find_element(By.ID, 'area')
    box.clear()
    box.send_keys(area)
    version = driver.find_element(By.ID, 'houses').get_attribute('data-version')
    driver.find_element(By.ID, 'search').click()
    WebDriverWait(driver, 5).until(
        lambda d: d.find_element(By.ID, 'houses').get_attribute('data-version') != version)


def basics(driver):
    box = driver.find_element(By.ID, 'area')
    box.clear()
    box.send_keys('朝阳')
    print('输入框当前值:', box.get_attribute('value'))
    driver.find_element(By.ID, 'search').click()
    WebDriverWait(driver, 5).until(EC.text_to_be_present_in_element((By.ID, 'status'), '朝阳 第1页'))
    link = driver.find_element(By.CSS_SELECTOR, '.detail-link')
    print('可见文本:', link.text)
    print('链接地址:', link.get_attribute('href'))
    assert link.text == 'D：朝阳 整租 7000元'


def locators(driver):
    queries = [(By.ID, 'area'), (By.NAME, 'area'), (By.CLASS_NAME, 'house'),
               (By.TAG_NAME, 'button'), (By.LINK_TEXT, 'A：海淀 单间 2500元'),
               (By.PARTIAL_LINK_TEXT, 'A：'), (By.CSS_SELECTOR, '#houses .detail-link'),
               (By.XPATH, "//ul[@id='houses']/li/a[@class='detail-link']")]
    for by, value in queries:
        print(by, value, '->', driver.find_element(by, value).tag_name)
    assert len(driver.find_elements(By.CLASS_NAME, 'house')) == 2
    assert driver.find_elements(By.ID, 'missing') == []
    try:
        driver.find_element(By.ID, 'missing')
    except NoSuchElementException:
        print('单数查找不存在的元素: NoSuchElementException')
    else:
        raise AssertionError('Expected missing element exception')


def inputs(driver):
    note = driver.find_element(By.ID, 'note')
    note.clear()
    note.send_keys('海淀')
    print('追加前:', note.get_attribute('value'))
    note.send_keys(' 单间')
    assert note.get_attribute('value') == '海淀 单间'
    note.send_keys(Keys.HOME)
    note.send_keys(Keys.SHIFT, Keys.END)
    note.send_keys(Keys.DELETE)
    note.send_keys('朝阳')
    print('按键清空后:', note.get_attribute('value'))
    assert note.get_attribute('value') == '朝阳'
    box = driver.find_element(By.ID, 'area')
    box.clear()
    box.send_keys('朝阳', Keys.ENTER)
    WebDriverWait(driver, 5).until(EC.text_to_be_present_in_element((By.ID, 'status'), '朝阳 第1页'))


def clicks(driver):
    checkbox = driver.find_element(By.ID, 'only-single')
    checkbox.click()
    assert checkbox.is_selected()
    checkbox.click()
    assert not checkbox.is_selected()
    button = driver.find_element(By.ID, 'double')
    ActionChains(driver).double_click(button).perform()
    assert driver.find_element(By.ID, 'double-result').text == '已双击'
    # JavaScript 点搜索按钮，不需要构造鼠标动作序列。
    driver.execute_script('arguments[0].click()', driver.find_element(By.ID, 'search'))
    WebDriverWait(driver, 5).until(lambda d: '第1页' in d.find_element(By.ID, 'status').text)
    print('复选框切换、双击、JS 点击完成')


def extracts(driver):
    house = driver.find_elements(By.CLASS_NAME, 'house')[0]
    link = house.find_element(By.CSS_SELECTOR, '.detail-link')
    print('可见文本:', link.text)
    print('href:', link.get_attribute('href'))
    print('value:', driver.find_element(By.ID, 'area').get_attribute('value'))
    print('自定义属性:', house.get_attribute('data-key'))
    print('图片地址:', driver.find_element(By.ID, 'photo').get_attribute('src'))
    mixed = driver.find_element(By.ID, 'mixed')
    direct = driver.execute_script(
        "return Array.from(arguments[0].childNodes).filter(n=>n.nodeType===3).map(n=>n.nodeValue).join('').trim()", mixed)
    assert mixed.text == '房源描述近地铁' and direct == '房源描述'
    print('全部文本:', mixed.text, '; 直接文本:', direct)
    print('innerHTML:', mixed.get_attribute('innerHTML'))
    print('outerHTML:', mixed.get_attribute('outerHTML'))
    print('背景图片:', driver.find_element(By.ID, 'background').value_of_css_property('background-image'))
    print('页面标题:', driver.title, '; 当前 URL:', driver.current_url)


def waits(driver):
    driver.find_element(By.ID, 'load-delayed').click()
    loaded = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, 'loaded')))
    assert loaded.text == '加载完成'
    assert not driver.find_element(By.ID, 'hidden-field').is_displayed()
    driver.find_element(By.ID, 'reveal').click()
    field = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, 'hidden-field')))
    field.send_keys('等可见后输入')
    assert field.get_attribute('value') == '等可见后输入'
    print('等待 DOM 出现、等待可见完成')


def frames(driver):
    wait = WebDriverWait(driver, 5)
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'outer-frame')))
    print(driver.find_element(By.ID, 'frame-result').text)
    driver.find_element(By.ID, 'frame-note').send_keys('外层输入')
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'inner-frame')))
    assert driver.find_element(By.ID, 'nested-result').text == '内层房源'
    print(driver.find_element(By.ID, 'nested-result').text)
    driver.switch_to.parent_frame()
    assert driver.find_element(By.ID, 'frame-note').get_attribute('value') == '外层输入'
    driver.switch_to.default_content()
    assert driver.find_element(By.ID, 'area').get_attribute('value') == '海淀'


def windows(driver):
    original = driver.current_window_handle
    before = set(driver.window_handles)
    driver.find_element(By.CSS_SELECTOR, '.new-tab').click()
    WebDriverWait(driver, 5).until(lambda d: len(set(d.window_handles) - before) == 1)
    new_handle = (set(driver.window_handles) - before).pop()
    driver.switch_to.window(new_handle)
    assert driver.find_element(By.ID, 'title').text == 'A：海淀 单间'
    print('新标签页:', driver.title)
    driver.close()
    driver.switch_to.window(original)
    driver.find_element(By.CSS_SELECTOR, '.detail-link').click()
    assert driver.title == 'A 房源详情'
    driver.back()
    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, 'area')))
    print('同标签页后退:', driver.title)


def selections(driver):
    select = Select(driver.find_element(By.ID, 'region'))
    select.select_by_index(1)
    assert select.first_selected_option.text == '朝阳'
    select.select_by_value('hd')
    assert select.first_selected_option.text == '海淀'
    select.select_by_visible_text('朝阳')
    assert select.first_selected_option.get_attribute('value') == 'cy'
    print('下拉框:', select.first_selected_option.text, select.first_selected_option.get_attribute('value'))


def actions(driver):
    ActionChains(driver).move_to_element(driver.find_element(By.ID, 'hover-area')).perform()
    assert driver.find_element(By.ID, 'hover-tip').is_displayed()
    print('悬停结果:', driver.find_element(By.ID, 'hover-tip').text)


def scripts(driver):
    note = driver.find_element(By.ID, 'note')
    print('JS 返回值:', driver.execute_script('return arguments[0].value', note))
    driver.execute_script('arguments[0].scrollIntoView({block:"center"})', driver.find_element(By.ID, 'bottom'))
    assert driver.execute_script('return window.scrollY') > 0
    driver.execute_script('window.scrollTo(0,0)')
    # 坐标以视口为基准，通过实际按钮的几何位置计算。
    x, y = driver.execute_script('const r=arguments[0].getBoundingClientRect(); return [r.x+r.width/2,r.y+r.height/2]', driver.find_element(By.ID, 'search'))
    driver.execute_script('document.elementFromPoint(arguments[0],arguments[1]).click()', x, y)
    WebDriverWait(driver, 5).until(lambda d: '第1页' in d.find_element(By.ID, 'status').text)
    print('滚动、坐标 JS 点击完成')


def alerts(driver):
    wait = WebDriverWait(driver, 5)
    driver.find_element(By.ID, 'alert').click()
    alert = wait.until(EC.alert_is_present())
    assert alert.text == '练习提示'
    alert.accept()
    driver.find_element(By.ID, 'confirm').click()
    wait.until(EC.alert_is_present()).dismiss()
    assert driver.find_element(By.ID, 'confirm-result').text == '已取消'
    driver.find_element(By.ID, 'prompt').click()
    prompt = wait.until(EC.alert_is_present())
    prompt.send_keys('采集备注')
    prompt.accept()
    assert driver.find_element(By.ID, 'prompt-result').text == '采集备注'
    print('提示框确认、确认框取消、输入弹窗完成')


def cookies(driver):
    driver.add_cookie({'name': 'demo_area', 'value': 'haidian'})
    assert driver.get_cookie('demo_area')['value'] == 'haidian'
    driver.refresh()
    assert driver.get_cookie('demo_area')['value'] == 'haidian'
    driver.delete_cookie('demo_area')
    assert driver.get_cookie('demo_area') is None
    print('设置、读取、刷新后保留、删除 cookie 完成')


def screenshots(driver):
    assert driver.save_screenshot(str(OUTPUT / 'page.png'))
    card = driver.find_element(By.CLASS_NAME, 'house')
    assert card.screenshot(str(OUTPUT / 'house.png'))
    assert card.screenshot_as_png.startswith(b'\x89PNG')
    print('截图:', OUTPUT / 'page.png', OUTPUT / 'house.png')


def downloads(driver):
    # 下载文件之前先移除本样例上次的同名输出，以免误判完成。
    target = OUTPUT / 'sample.txt'
    target.unlink(missing_ok=True)
    driver.find_element(By.ID, 'download').click()
    WebDriverWait(driver, 10).until(lambda d: target.exists() and target.read_bytes() == b'Selenium download example.\n')
    photo_url = driver.find_element(By.ID, 'photo').get_attribute('src')
    with urlopen(photo_url, timeout=5) as response:
        (OUTPUT / 'photo.svg').write_bytes(response.read())
    print('浏览器下载文件:', target, '; Python 按 src 下载图片:', OUTPUT / 'photo.svg')


def stale(driver):
    old = driver.find_element(By.CSS_SELECTOR, '.detail-link')
    driver.find_element(By.ID, 'next').click()
    WebDriverWait(driver, 5).until(EC.staleness_of(old))
    try:
        print(old.text)
    except StaleElementReferenceException:
        print('旧引用失效，重新查找:', driver.find_element(By.CSS_SELECTOR, '.detail-link').text)
    else:
        raise AssertionError('Expected stale element')
    assert driver.find_element(By.CSS_SELECTOR, '.detail-link').text.startswith('C：')


def collect(driver):
    rows = []
    list_handle = driver.current_window_handle
    for area in ['海淀', '朝阳']:
        search(driver, area)
        for page in range(2):
            # 先保存本页文本与 URL，避免跳转后继续持有旧 DOM 引用。
            houses = [(a.text, a.get_attribute('href')) for a in driver.find_elements(By.CSS_SELECTOR, '.detail-link')]
            for text, url in houses:
                if '单间' not in text:
                    continue
                driver.switch_to.new_window('tab')
                try:
                    driver.get(url)
                    rows.append({'地区': area, '标题': driver.find_element(By.ID, 'title').text,
                                 '价格': driver.find_element(By.ID, 'price').text, '链接': driver.current_url})
                finally:
                    driver.close()
                    driver.switch_to.window(list_handle)
            if page == 1:
                break
            previous = driver.find_element(By.CSS_SELECTOR, '.detail-link')
            driver.find_element(By.ID, 'next').click()
            WebDriverWait(driver, 5).until(EC.staleness_of(previous))
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.detail-link')))
    assert [row['标题'][0] for row in rows] == ['A', 'C', 'E']
    destination = OUTPUT / 'houses.csv'
    with destination.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['地区', '标题', '价格', '链接'])
        writer.writeheader()
        writer.writerows(rows)
    print('采集结果:', rows, '; CSV:', destination)


CASES = {'basics': basics, 'locators': locators, 'input': inputs, 'click': clicks,
         'extract': extracts, 'wait': waits, 'iframe': frames, 'windows': windows,
         'select': selections, 'actions': actions, 'script': scripts, 'alert': alerts,
         'cookie': cookies, 'screenshot': screenshots, 'download': downloads,
         'stale': stale, 'collect': collect}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['all', *CASES], default='basics')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()
    driver = create_driver(args.headless)
    try:
        names = CASES if args.case == 'all' else [args.case]
        for name in names:
            reset(driver)
            print(f'\n=== {name} ===')
            CASES[name](driver)
            print('PASS:', name)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
