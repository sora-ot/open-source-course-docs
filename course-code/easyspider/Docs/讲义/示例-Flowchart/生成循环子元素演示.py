"""提取 Flowchart 的 Vue、参数模板和函数，重建第 22 讲本地演示。

python Docs/讲义/示例-Flowchart/生成循环子元素演示.py
python Docs/讲义/示例-Flowchart/生成循环子元素演示.py --screenshots
仅使用标准库；不连接 Electron、WebSocket 或实际采集浏览器。
"""
from pathlib import Path
import argparse
import html
import json
import os
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FLOW = (REPO / 'ElectronJS/src/taskGrid/FlowChart.js').read_text(encoding='utf-8-sig')
LOGIC = (REPO / 'ElectronJS/src/taskGrid/logic.js').read_text(encoding='utf-8-sig')
HTML = (REPO / 'ElectronJS/src/taskGrid/FlowChart_CN.html').read_text(encoding='utf-8-sig')


def between(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)].strip()


message = {
    'type': 'multiCollectWithPattern', 'history': 1, 'tabIndex': -1,
    'iframe': False, 'loopType': 1, 'xpath': "//div[@class='house']",
    'allXPaths': ["//div[@class='house']"], 'isDescendents': True,
    'parameters': [
        {'nodeType': 0, 'contentType': 1, 'relative': True, 'name': '标题',
         'desc': '', 'relativeXPath': '/h2[1]', 'allXPaths': ['/h2[1]'],
         'exampleValues': [{'num': 0, 'value': '海淀单间'}], 'iframe': False},
        {'nodeType': 0, 'contentType': 1, 'relative': True, 'name': '租金',
         'desc': '', 'relativeXPath': '/div[1]/span[1]', 'allXPaths': ['/div[1]/span[1]'],
         'exampleValues': [{'num': 0, 'value': '2500元'}], 'iframe': False},
    ],
}
(HERE / '循环子元素-消息案例.json').write_text(
    json.dumps(message, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

functions = [
    between(FLOW, 'function DeepClone(obj)', '// 根据元素类型'),
    between(FLOW, 'function newNode(node)', 'function arrowMouseDown(e)'),
    between(FLOW, 'function operationChange(e, theNode)', 'function elementMousedown(e)'),
    between(FLOW, 'function refresh(nowArrowReset = true)', 'function deleteElement()'),
    between(FLOW, 'function deleteElement()', 'document.getElementById("flowchart_graph").oncontextmenu'),
    between(LOGIC, 'function changeGetDataParameters(msg, i)', 'function handleAddElement(msg)'),
    between(LOGIC, 'function handleElement()', '// 新增元素时的默认参数处理'),
    between(LOGIC, 'function addParameters(t)', 'function updateUI()'),
    between(LOGIC, 'function updateUI()', '//修改元素参数'),
    between(LOGIC, 'function modifyParameters(t, param)', 'function showSuccess(msg'),
    between(LOGIC, 'function updateParentNode()', 'function trialElement(node'),
    between(LOGIC, 'function trialElement(node', '// 流程图元素点击后的处理逻辑'),
]
vue = between(FLOW, 'let app = new Vue({', '//深复制')
bootstrap = """
// 教学宿主在创建 Vue 前预置完整四节点参数；不复现现场新增的后添加属性时序。
// 参数仍由原 addParameters/modifyParameters 填入。
let nodeList = [], actionSequence = [], queue = [];
let nowNode = null, vueData = {nowNodeIndex: 0};
let id = 0, title = '', type = 0, option = 0, debuggable = true, parameterNum = 3;
function LANG(zh, en) { return zh; }
function inputDelete(event) { event.stopPropagation(); }
let lastDemoMessage = '点击循环或提取节点；在字段表中点“修改”，查看 paraIndex 和原节点参数。';
// 原 trialElement / notifyParameterNum 仍组装消息；本页只记录消息，不发送到外部。
let ws = {send(text) {
  const envelope = JSON.parse(text);
  lastDemoMessage = '原代码组装了 type=' + envelope.type + ' 的消息，本页记录到本地。';
  window.lastTrialEnvelope = envelope;
  syncInspector();
}};
function notifyParameterNum(num) { parameterNum += num; }
function showInfo(text) { lastDemoMessage = text; syncInspector(); }
function showError(text) { showInfo(text); }
function showSuccess(text) { showInfo(text); }
function makeNode(index, nodeTitle, nodeOption, nodeType, sequence) {
  const node = {index, id:0, parentId:0, title:nodeTitle, option:nodeOption,
    type:nodeType, sequence:sequence || [], isInLoop:false};
  addParameters(node);
  return node;
}
nodeList = [makeNode(0,'root',0,-1,[1,2]), makeNode(1,'打开网页',1,0),
  makeNode(2,'循环采集数据',8,1,[3]), makeNode(3,'提取标题和租金',3,0)];
nodeList[0].id = 0;
nodeList[1].parameters.links = 'https://example.com/rent';
modifyParameters(nodeList[2], demoMessage);
modifyParameters(nodeList[3], demoMessage);
"""
runtime = """
// 以下为教学宿主；原函数、Vue 配置和参数模板在上方保持源码内容。
app.getCookies = function () { showInfo('本页只展示参数状态，不连接浏览器读取 Cookie。'); };
function bindEvents() {
  document.querySelectorAll('#flowchart_graph .clk').forEach(element => {
    element.addEventListener('click', function(event) { operationChange(event, this); });
  });
}
function selectDemoNode(index) {
  const element = document.getElementById(String(nodeList[index].id));
  operationChange({button:0, stopPropagation(){}}, element);
  updateParentNode();
  syncInspector();
}
function syncInspector() {
  const output = document.getElementById('state-output');
  if (!output || typeof app === 'undefined') return;
  const field = app.nodeType === 3 ? app.params.parameters[app.paraIndex] : null;
  output.textContent = JSON.stringify({
    actionSequence:actionSequence.slice(), nowNodeIndex:vueData.nowNodeIndex,
    nodeType:app.nodeType, nowNode:app.nowNode ? 'nodeList['+vueData.nowNodeIndex+']' : null,
    parentNode:app.parentNode ? 'nodeList['+app.parentNode.index+']' : null,
    loopType:app.loopType, paraIndex:app.paraIndex,
    'params.parameters === nodeList[3].parameters.params': app.params.parameters === nodeList[3].parameters.params,
    currentField:field ? {name:field.name, relative:field.relative, relativeXPath:field.relativeXPath,
      contentType:field.contentType, paraType:field.paraType} : null,
    'nodeList[3].parameters':nodeList[3].parameters
  }, null, 2);
  document.getElementById('event-output').textContent = lastDemoMessage;
  document.getElementById('state-summary').textContent =
    'nowNodeIndex=' + vueData.nowNodeIndex + ' → nowNode=nodeList[' + vueData.nowNodeIndex +
    '] → nodeType=' + app.nodeType + '；loopType=' + app.loopType + '；paraIndex=' + app.paraIndex +
    (field ? ' → 当前字段：' + field.name + '，relativeXPath=' + field.relativeXPath : ' → 当前显示循环参数');
}
app.$watch(() => ({nodeType:app.nodeType, node:app.nowNode, parent:app.parentNode,
  paraIndex:app.paraIndex, fields:app.params.parameters}), syncInspector, {deep:true});
document.getElementById('select-loop').onclick = () => selectDemoNode(2);
document.getElementById('select-fields').onclick = () => selectDemoNode(3);
document.getElementById('reset-demo').onclick = () => location.assign(location.pathname);
refresh();
const view = new URLSearchParams(location.search).get('view') || 'title';
// 与“先新增循环并选中，再新增提取并选中”的原交互顺序一致。
selectDemoNode(2);
selectDemoNode(3);
if (view === 'loop') selectDemoNode(2);
if (view === 'rent' || view === 'edited') app.modifyParam(1);
app.$nextTick(() => {
  // 等字段详情切到租金后，通过真正的输入事件检查 v-model 写回。
  if (view === 'edited') {
    const nameInput = document.querySelector('#app .toolkittb4 tr:nth-child(2) input');
    nameInput.value = '月租';
    nameInput.dispatchEvent(new Event('input', {bubbles:true}));
    const pathInput = document.querySelector('#app textarea[placeholder^="如果要写相对"]');
    pathInput.value = '/div[1]/span[@class="rent"]';
    pathInput.dispatchEvent(new Event('input', {bubbles:true}));
  }
  app.$nextTick(() => {
  syncInspector();
  document.body.dataset.ready = '1';
  // 浏览器内核对模板切换、字段共享引用，以及两行网页数据的相对路径。
  const checks = [];
  checks.push(nodeList[2].sequence[0] === 3);
  checks.push(app.nodeType === (view === 'loop' ? 8 : 3));
  if (view !== 'loop') checks.push(app.params.parameters === nodeList[3].parameters.params);
  if (view === 'rent' || view === 'edited') checks.push(app.paraIndex === 1);
  checks.push(app.loopType === 1);
  if (view === 'edited') {
    checks.push(nodeList[3].parameters.params[1].name === '月租');
    checks.push(nodeList[3].parameters.params[1].relativeXPath === '/div[1]/span[@class="rent"]');
  }
  const cards = document.querySelectorAll('#source-page .house');
  const rows = Array.from(cards).map(card => nodeList[3].parameters.params.map(field => {
    const target = document.evaluate('.'+field.relativeXPath, card, null,
      XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    return Array.from(target.childNodes).filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent.trim()).join('');
  }));
  checks.push(JSON.stringify(rows) === JSON.stringify([['海淀单间','2500元'],['朝阳单间','2800元']]));
  const passed = checks.every(Boolean);
  document.getElementById('verification').textContent = JSON.stringify({passed,view,rows});
  document.body.dataset.verified = passed ? '1' : '0';
  });
});
"""
generated = '// 由生成循环子元素演示.py生成；原 Vue 配置与函数按边界从仓库提取。\n'
generated += 'const demoMessage = ' + json.dumps(message, ensure_ascii=False, indent=2) + ';\n\n'
generated += '\n\n'.join(functions) + '\n\n' + bootstrap + '\n\n' + vue + ';\n\n' + runtime
(HERE / '循环子元素-源码片段.js').write_text(generated, encoding='utf-8')

panels = '\n'.join(
    between(HTML, f'<div class="elements" v-if="nodeType=={n}">',
            f'<div class="elements" v-if="nodeType=={next_n}">')
    for n, next_n in [(1,2),(3,4),(8,9)]
)
template = (HERE / '循环子元素-演示模板.html').read_text(encoding='utf-8')
assert template.count('<!-- PARAMETER_PANELS -->') == 1
(HERE / '循环子元素-Vue演示.html').write_text(
    template.replace('<!-- PARAMETER_PANELS -->', panels), encoding='utf-8')
print('Generated: message JSON, extracted JS, and Vue demo HTML.')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--screenshots', action='store_true')
parser.add_argument('--browser', help='Chrome/Edge executable path')
args = parser.parse_args()
if args.screenshots:
    candidates = [Path(args.browser)] if args.browser else [
        Path(os.environ.get('PROGRAMFILES', '')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('PROGRAMFILES', '')) / 'Microsoft/Edge/Application/msedge.exe',
    ]
    browser = next((p for p in candidates if p.is_file()), None)
    if browser is None:
        raise SystemExit('Chrome/Edge not found; use --browser PATH.')
    output = HERE.parent / '图片/Flowchart'
    output.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for view, label in [('loop','01-循环参数'), ('title','02-标题参数'),
                        ('rent','03-租金参数'), ('edited','04-编辑后参数')]:
        screenshot = output / f'循环子元素-{label}.png'
        with tempfile.TemporaryDirectory(prefix='descendants-vue-preview-') as profile:
            command = [str(browser), '--headless=new', '--disable-gpu', '--no-first-run',
                       '--no-default-browser-check', '--disable-crash-reporter', '--disable-breakpad',
                       '--hide-scrollbars', '--allow-file-access-from-files', '--virtual-time-budget=1800',
                       '--window-size=1500,1350', f'--user-data-dir={profile}',
                       f'--screenshot={screenshot}', '--dump-dom',
                       (HERE / '循环子元素-Vue演示.html').as_uri() + f'?view={view}']
            result = subprocess.run(command, capture_output=True, timeout=40,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            dom = result.stdout.decode('utf-8', errors='replace')
            assert result.returncode == 0 and screenshot.is_file(), result.stderr.decode('utf-8', errors='replace')
            assert 'data-verified="1"' in dom, f'Browser verification failed: {view}'
            match = re.search(r'<pre id="state-output">(.*?)</pre>', dom, re.S)
            assert match, f'Missing state output: {view}'
            snapshots[view] = json.loads(html.unescape(match[1]))
            print(f'Browser verified: {view}; screenshot saved.', flush=True)
    (HERE / '循环子元素-状态快照.json').write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
