"""从仓库提取原始渲染函数，生成第 19 讲教学页；可用 Chromium 截图。

python Docs/讲义/示例-Flowchart/生成渲染演示.py
python Docs/讲义/示例-Flowchart/生成渲染演示.py --screenshots
python Docs/讲义/示例-Flowchart/生成渲染演示.py --html-snapshots
仅使用 Python 标准库；截图与 HTML 快照导出需要本机安装 Chrome 或 Edge。
"""
from pathlib import Path
import argparse
from html.parser import HTMLParser
import json
import os
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE = REPO / 'ElectronJS/src/taskGrid/FlowChart.js'


def build():
    source = SOURCE.read_text(encoding='utf-8-sig')
    pieces = []
    for start, end in [
        ('function newNode(node)', 'function arrowMouseDown(e)'),
        ('function refresh(nowArrowReset = true)', 'function deleteElement()'),
    ]:
        pieces.append(source[source.index(start):source.index(end)].strip())
    target = HERE / '渲染机制-源码片段.js'
    target.write_text(
        '// 由生成渲染演示.py从FlowChart.js提取；请修改原文件后重新生成。\n'
        '// 两个函数的函数体保持原样；教学页另行提供app、LANG和bindEvents。\n\n'
        + '\n\n'.join(pieces) + '\n', encoding='utf-8')
    print('Source snippets generated.', flush=True)


def find_browser(browser_arg):
    candidates = [browser_arg] if browser_arg else [
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google/Chrome/Application/chrome.exe'),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft/Edge/Application/msedge.exe'),
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Microsoft/Edge/Application/msedge.exe'),
    ]
    browser = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
    if browser is None:
        raise SystemExit('Chrome/Edge not found; supply --browser PATH.')
    return browser


def capture(browser_arg):
    browser = find_browser(browser_arg)
    output = HERE.parent / '图片/Flowchart'
    output.mkdir(parents=True, exist_ok=True)
    cases = [
        ('01-空画布', 'empty', None, 500),
        ('02-三个顺序动作', 'sequence', None, 800),
        ('03-先建立空循环框', 'loop', 2, 740),
        ('04-先把提取放在框外', 'loop', 3, 840),
        ('05-再把点击放进框内', 'loop', None, 950),
        ('06-两层循环', 'nested', None, 1210),
        ('07-判断与横向分支', 'judge', None, 990),
        ('08-点击方块与事件', 'loop', None, 930),
    ]
    with tempfile.TemporaryDirectory(prefix='.render-profile-', dir=HERE) as profile:
        # 清理范围限定为本脚本目录下新建的临时配置目录。
        assert Path(profile).resolve().is_relative_to(HERE.resolve())
        for label, scene, step, height in cases:
            url = (HERE / '渲染机制-演示.html').as_uri() + f'?scene={scene}&capture=1'
            if step is not None:
                url += f'&step={step}'
            if label.startswith('08'):
                url += '&select=4'
            image = output / f'渲染-{label}.png'
            command = [
                str(browser), '--headless=new', '--disable-gpu', '--no-first-run',
                '--disable-crash-reporter', '--disable-breakpad',
                '--no-default-browser-check', '--hide-scrollbars',
                f'--user-data-dir={profile}', '--allow-file-access-from-files',
                '--run-all-compositor-stages-before-draw', '--virtual-time-budget=2500',
                f'--window-size=960,{height}', f'--screenshot={image}', url,
            ]
            result = subprocess.run(command, capture_output=True, timeout=45,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode or not image.is_file():
                raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
            print(f'Screenshot {label[:2]} saved ({image.stat().st_size} bytes).', flush=True)


def export_html(browser_arg):
    class SnapshotParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active = False
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if tag == 'code' and dict(attrs).get('id') == 'demo-html-output':
                self.active = True

        def handle_endtag(self, tag):
            if tag == 'code':
                self.active = False

        def handle_data(self, data):
            if self.active:
                self.parts.append(data)

    browser = find_browser(browser_arg)
    cases = [('empty', 'empty', None)]
    cases += [(f'sequence-{i}', 'sequence', i) for i in range(1, 4)]
    cases += [(f'loop-{i}', 'loop', i) for i in range(5)]
    cases += [(f'nested-{i}', 'nested', i) for i in range(1, 7)]
    cases += [(f'judge-{i}', 'judge', i) for i in range(1, 6)]
    cases += [('loop-selected', 'loop', None)]
    snapshots = {}
    with tempfile.TemporaryDirectory(prefix='.render-profile-', dir=HERE) as profile:
        assert Path(profile).resolve().is_relative_to(HERE.resolve())
        for key, scene, step in cases:
            url = (HERE / '渲染机制-演示.html').as_uri() + f'?scene={scene}'
            if step is not None:
                url += f'&step={step}'
            if key == 'loop-selected':
                url += '&select=4'
            result = subprocess.run([
                str(browser), '--headless=new', '--disable-gpu', '--no-first-run',
                '--disable-crash-reporter', '--disable-breakpad', '--no-default-browser-check',
                f'--user-data-dir={profile}', '--allow-file-access-from-files',
                '--virtual-time-budget=1000', '--dump-dom', url,
            ], capture_output=True, timeout=45,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
            parser = SnapshotParser()
            parser.feed(result.stdout.decode('utf-8'))
            snapshot = ''.join(parser.parts).replace('\r', '')
            if not snapshot.startswith('<div id="0"'):
                raise RuntimeError(f'HTML snapshot missing: {key}')
            snapshots[key] = snapshot
            print(f'HTML snapshot {key} exported.', flush=True)
    (HERE / '渲染机制-HTML快照.json').write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', action='store_true')
    parser.add_argument('--html-snapshots', action='store_true')
    parser.add_argument('--browser', help='Chrome/Edge executable path')
    args = parser.parse_args()
    build()
    if args.screenshots:
        capture(args.browser)
    if args.html_snapshots:
        export_html(args.browser)
