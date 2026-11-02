"""Create the website's reading copy; never edit the teacher's originals."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
DOCS = SITE / 'docs'
PUBLIC = DOCS / 'public'
EASY = ROOT / 'EasySpider' / 'Docs' / '讲义'
CLAW = ROOT / 'OpenClaw' / 'OpenClaw-Course'
MINI = ROOT / 'MiniMind整理版'
MINI_MANIFEST = json.loads((MINI / '内容映射.json').read_text(encoding='utf-8'))
MINI_PARTS = { (MINI / p['file']).resolve(): (d, p) for d in MINI_MANIFEST['documents'] for p in d['parts'] }
WARNINGS: list[dict] = []
SOURCE_FILES: dict[str, dict] = {}
PAGE_MAP: dict[Path, str] = {}
COPY_COUNT = 0

EASY_TITLES = [
    '导读与学习路线', '总体架构与目录', '数据流全链路', 'Chrome 扩展与 MV3',
    'XPath', '元素待选与选中', '同类元素自动匹配', '手动匹配与相对 XPath',
    '采集参数生成', 'DFS 与 BFS', '选中子元素算法', 'Vue 3 基础',
    'toolkit.vue', 'WebSocket', '消息交互', '流程图基本原理', '递归执行',
    'Selenium', '流程图数据结构', '流程图渲染', '流程图增删改查', '消息到流程图节点',
    '循环采集与参数栏', '流程图保存与加载', 'Electron', '调试功能',
    'Node 与 Express', '开发、调试与发布',
]
CLAW_TITLES = [
    '整体架构', '源码目录与规模', 'TypeScript 速成', 'Pi-Agent 与 OpenClaw',
    '模型接口与流式传输', 'AgentLoop 执行循环', '工具系统', 'Compaction 上下文压缩',
    'SessionManager', 'Bootstrap、Skill 与 Extension', '记忆系统与 RAG',
    '互联网 RAG', 'AgentSession 运行准备', 'AgentSession 执行', '多智能体系统',
    'Gateway 与多渠道通信', '路由、Session 与并发调度', 'Workspace 与长期记忆',
]
GROUPS = {
    'easyspider': [
        ('认识项目', range(0, 3)), ('元素与任务', range(3, 11)),
        ('界面与通信', range(11, 15)), ('流程图与执行', range(15, 24)),
        ('工程实践', range(24, 28)),
    ],
    'openclaw': [
        ('架构与准备', range(1, 5)), ('一次任务如何运行', range(5, 8)),
        ('会话与上下文', range(8, 11)), ('记忆与知识检索', range(11, 13)),
        ('会话执行与协作', range(13, 16)), ('系统集成', range(16, 19)),
    ],
}
PAGES: list[dict] = []


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


def outside_fences(text: str, transform):
    output = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            output.append(line)
        elif fence is None:
            output.append(transform(line))
        else:
            output.append(line)
    return '\n'.join(output) + '\n'


def register(project: str, file: Path, slug: str, title: str, group: str):
    route = f'/{project}/{slug}'
    PAGE_MAP[file.resolve()] = route
    PAGES.append(dict(project=project, file=file, slug=slug, title=title, group=group, route=route))


def prepare_catalog():
    for f in sorted(EASY.glob('*.md')):
        m = re.match(r'^(\d+)\.', f.name)
        if m:
            i = int(m[1])
            group = next(name for name, ids in GROUPS['easyspider'] if i in ids)
            register('easyspider', f, f'chapter-{i:02}', f'{i:02} · {EASY_TITLES[i]}', group)
        else:
            register('easyspider', f, 'directory', '完整讲义目录', '参考与演示')
    for f in sorted(CLAW.glob('*.md')):
        m = re.match(r'^(\d+)_', f.name)
        if m:
            i = int(m[1])
            group = next(name for name, ids in GROUPS['openclaw'] if i in ids)
            register('openclaw', f, f'chapter-{i:02}', f'{i:02} · {CLAW_TITLES[i - 1]}', group)
        else:
            slug = ('session-tree' if '会话' in f.name else 'skills-extensions' if '技能' in f.name else 'messages-events')
            title = ('会话树源码补充' if '会话' in f.name else '技能与扩展源码补充' if '技能' in f.name else '消息与事件源码补充')
            register('openclaw', f, slug, title, '源码补充')
    register('llamafactory', ROOT / 'LLaMAFactory_10分钟项目讲义.md', 'ten-minutes', '十分钟理解核心实现', '课堂主线')
    register('llamafactory', ROOT / 'LLaMAFactory源码讲解提纲与关键代码.md', 'source-outline', '源码提纲与关键代码', '扩展阅读')
    register('langchain', ROOT / 'LangChain十分钟讲义.md', 'ten-minutes', '十分钟理解 Runnable', '课堂主线')
    PAGE_MAP[(MINI / 'README.md').resolve()] = '/minimind/'
    for d in MINI_MANIFEST['documents']:
        for p in d['parts']:
            register('minimind', MINI / p['file'], p['slug'], p['title'], d['group'])
        # Preserve references to the unpartitioned originals.
        PAGE_MAP[(MINI / d['snapshot']).resolve()] = '/minimind/' + d['parts'][0]['slug']
        PAGE_MAP[(ROOT / 'MiniMind' / d['original']).resolve()] = '/minimind/' + d['parts'][0]['slug']


def copy_file(source: Path, dest: Path):
    global COPY_COUNT
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    COPY_COUNT += 1


def resource_url(file: Path) -> str | None:
    # Preserve all local paths in demonstrations, including scripts, CSS and images.
    if file.is_relative_to(EASY):
        rel = file.relative_to(EASY)
        if rel.parts[0] in ['图片', '示例-Flowchart', '示例-Selenium', '示例-同类元素匹配', '示例扩展-字数统计器'] or file.suffix == '.html':
            return '/resources/easyspider/' + quote(rel.as_posix())
    if file.is_relative_to(CLAW / 'assets'):
        return '/resources/openclaw/' + quote(file.relative_to(CLAW).as_posix())
    if file.is_relative_to(MINI):
        return '/resources/minimind/' + quote(file.relative_to(MINI).as_posix())
    return None


def source_url(file: Path, fragment: str) -> str:
    rel = file.relative_to(ROOT).as_posix()
    key = hashlib.sha256(rel.encode()).hexdigest()[:18] + file.suffix
    if key not in SOURCE_FILES:
        copy_file(file, PUBLIC / 'resources' / 'sources' / key)
        SOURCE_FILES[key] = dict(path=rel, name=file.name, lines=len(file.read_text(encoding='utf-8-sig', errors='replace').splitlines()))
    return '/source/?file=' + key + ('#' + fragment if fragment else '')


def convert_link(raw: str, original: Path) -> str:
    # The teaching material uses ordinary inline links, sometimes with a quoted title.
    suffix = ''
    raw = raw.strip()
    if raw.startswith('<') and '>' in raw:
        i = raw.index('>')
        raw, suffix = raw[1:i], raw[i + 1:]
    else:
        title = re.search(r'\s+"[^"\n]*"$', raw)
        if title:
            raw, suffix = raw[:title.start()], title[0]
    if re.match(r'^(?:[a-z][a-z0-9+.-]*:|//|#)', raw, re.I):
        return raw + suffix
    parts = urlsplit(raw)
    path = unquote(parts.path)
    if path.startswith(('/minimind/', '/guide/', '/source/')):
        return raw + suffix
    if not path:
        return raw + suffix
    resolved = (original.parent / path).resolve()
    # Reading copies use new filenames while old cross-references name the originals.
    if original.resolve() in MINI_PARTS:
        document, _ = MINI_PARTS[original.resolve()]
        logical = (ROOT / 'MiniMind' / Path(document['original']).parent / path).resolve()
        if logical.is_file():
            resolved = logical
            # Images and attachments keep the original relative layout.
            attachment = next((a for a in MINI_MANIFEST['attachments'] if (ROOT/'MiniMind'/a['source']).resolve()==logical),None)
            if attachment:
                resolved = (MINI/attachment['snapshot']).resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.exists() or not resolved.is_file():
        WARNINGS.append(dict(file=str(original.relative_to(ROOT)), target=raw, reason='当前资料未提供此链接目标'))
        return '/guide/unavailable#reference' + suffix
    frag = '#' + parts.fragment if parts.fragment else ''
    query = '?' + parts.query if parts.query else ''
    if resolved in PAGE_MAP:
        if original.resolve() in MINI_PARTS and parts.fragment:
            # Old GitHub anchors can point into a later partition; resolve by heading.
            target_doc = next((d for d in MINI_MANIFEST['documents'] if resolved in [(MINI/d['snapshot']).resolve(), (ROOT/'MiniMind'/d['original']).resolve()]),None)
            if target_doc:
                fragment = unquote(parts.fragment)
                slug = lambda s: re.sub(r'[\W_]+','',s.replace('`','').lower())
                for p in target_doc['parts']:
                    for h in p['headings']:
                        if (fragment == 'origin-'+str(h['originLine']) or slug(h.get('sourceTitle',h['title'])) == slug(fragment)):
                            return '/minimind/'+p['slug']+'#origin-'+str(h['originLine'])+suffix
        return PAGE_MAP[resolved] + frag + suffix
    resource = resource_url(resolved)
    if resource and resolved.suffix.lower() in {'.html', '.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp', '.mp4', '.pdf', '.pptx', '.zip'}:
        return resource + query + frag + suffix
    return source_url(resolved, parts.fragment) + suffix


def normalize(text: str, file: Path) -> str:
    clean_lines = []
    outside_fences(text, lambda line: clean_lines.append(line) or line)
    heading_count = sum(bool(re.match(r'^#\s', line)) for line in clean_lines)
    seen_h1 = False

    def convert_line(line):
        nonlocal seen_h1
        h = re.match(r'^(#{1,6}) (.+)$', line)
        if h:
            n = len(h[1])
            if n == 1 and not seen_h1:
                seen_h1 = True
            elif heading_count > 1:
                line = '#' * min(n + 1, 6) + ' ' + h[2]
        # Let Markdown handle HTML-looking teaching examples as literal text.
        def convert_prose(prose):
            prose = re.sub(r'<img\b[^>]*?src=["\']([^"\']+)["\'][^>]*>', r'![](\1)', prose, flags=re.I)
            def replace_link(m):
                if len(re.findall(r'`+', prose[:m.start()])) % 2:
                    return m[0]
                dest = convert_link(m[2], file)
                if m[1].startswith('!') and dest.startswith('/guide/unavailable'):
                    return '[原讲义此处配图未随资料提供](/guide/unavailable#reference)'
                return m[1] + dest + m[3]
            # Permit inline code/math and one level of brackets in link labels.
            return re.sub(r'(!?\[(?:[^\[\]\n]|\[[^\]\n]*\])*\]\()([^\n]+?)(\))', replace_link, prose)
        # Inline code can itself contain an example Markdown link; leave it untouched.
        line = convert_prose(line)
        if line.strip() == r'\[':
            return '$$'
        if line.strip() == r'\]':
            return '$$'
        line = re.sub(r'\\\((.+?)\\\)', r'$\1$', line)
        if file.name.startswith('27.'):
            # Preserve GitHub-style anchors already used by the original chapter.
            aliases = {
                '1': '1-先分清你究竟在运行哪一份代码',
                '3': '3-安装三套工程的依赖',
                '7': '7-调试-electron-主进程看消息怎样转发',
                '15': '15-用户没有你的开发环境',
                '17': '17-更新版本为什么不只改-packagejson',
                '18': '18-更新浏览器复制本机-chrome再准备驱动',
                '21': '21-electron-forgepackage-和-make-分别在哪一层',
                '25': '25-compresspy按当前平台选择最终文件名',
            }
            section = re.match(r'^#{1,6}\s+(\d+)\.\s', line)
            if section and section[1] in aliases:
                line = f'<a id="{aliases[section[1]]}"></a>\n' + line
        return line

    return outside_fences(text, convert_line)


def copy_resources():
    for name in ['图片', '示例-Flowchart', '示例-Selenium', '示例-同类元素匹配', '示例扩展-字数统计器']:
        folder = EASY / name
        if folder.exists():
            for file in folder.rglob('*'):
                if file.is_file() and file.suffix not in ['.pyc'] and '__pycache__' not in file.parts:
                    copy_file(file, PUBLIC / 'resources' / 'easyspider' / file.relative_to(EASY))
    for file in EASY.glob('*.html'):
        copy_file(file, PUBLIC / 'resources' / 'easyspider' / file.name)
    for file in (CLAW / 'assets').rglob('*'):
        if file.is_file() and file.suffix in ['.png', '.svg', '.jpg', '.webp']:
            copy_file(file, PUBLIC / 'resources' / 'openclaw' / file.relative_to(CLAW))
    for file in (ROOT / 'videos').glob('*.mp4'):
        copy_file(file, PUBLIC / 'resources' / 'videos' / file.name)
    for item in MINI_MANIFEST['attachments']:
        file = MINI / item['snapshot']
        copy_file(file, PUBLIC / 'resources' / 'minimind' / item['snapshot'])
    for item in MINI_MANIFEST['codeFiles']:
        source_url(MINI / item['snapshot'], '')


def generate_pages():
    for p in PAGES:
        file = p['file']
        text = file.read_text(encoding='utf-8-sig')
        original_url = f"/originals/{p['project']}/{p['slug']}.md"
        copy_file(file, PUBLIC / original_url.lstrip('/'))
        original_path = file.relative_to(ROOT).as_posix()
        mini = MINI_PARTS.get(file.resolve())
        if mini:
            document, part = mini
            original_url = '/resources/minimind/' + quote(document['snapshot'])
            original_path = 'MiniMind/' + document['original']
            text = text.replace(MINI_MANIFEST['marker'], '', 1)
        fm = {
            'title': p['title'], 'description': f"{p['project']} · {p['group']} · 课程讲义",
            'project': p['project'], 'sourcePath': original_path,
            'originalUrl': original_url, 'outline': [2, 3],
            'downloadLabel': '下载整理后 Markdown' if p['project']=='minimind' else '下载原始 Markdown',
        }
        # JSON objects are valid YAML scalars; emit one key per line for VitePress.
        header = '---\n' + ''.join(k + ': ' + json.dumps(v, ensure_ascii=False) + '\n' for k, v in fm.items()) + '---\n\n'
        note = ''
        if p['project'] == 'llamafactory' and p['slug'] == 'ten-minutes':
            note = '> **阅读提示：**原稿开头以 SFT + LoRA 的调用链引入，后半段重点展开 Full SFT。阅读时请区分两条微调分支；本站保留原稿内容。\n\n'
        rendered = normalize(text, file)
        if mini:
            # Stable aliases allow original section links to survive partitioning.
            head_iter = iter(part['headings'])
            def heading_alias(line):
                if re.match(r'^#{1,6}\s',line):
                    try:
                        h = next(head_iter)
                    except StopIteration:
                        return line
                    return f'<a id="origin-{h["originLine"]}"></a>\n'+line
                return line
            first, _, rest = rendered.partition('\n')
            rendered = first+'\n'+outside_fences(rest,heading_alias)
        write(DOCS / p['project'] / (p['slug'] + '.md'), header + note + rendered)


PROJECTS = [
    dict(id='easyspider', name='EasySpider', eyebrow='可视化采集 · 28 节',
         description='从网页上的一次点击，追到流程图、任务 JSON 与自动化执行。',
         topics=['浏览器扩展', 'XPath', '流程图', 'Selenium'], first='chapter-00',
         intro='沿“人选择网页元素 → 扩展生成消息 → 桌面端构建流程图 → 执行器读取 JSON”的主线，理解一个真实桌面应用怎样协作。'),
    dict(id='openclaw', name='OpenClaw', eyebrow='智能体系统 · 18 节 + 3 篇补充',
         description='跟随一条用户消息，理解 Agent 如何调用工具、管理记忆并完成协作。',
         topics=['AgentLoop', '上下文', 'RAG', '多智能体'], first='chapter-01',
         intro='先认识 OpenClaw 与 Pi 的分层，再把模型、工具、会话、记忆和多智能体串成一次完整任务。'),
    dict(id='llamafactory', name='LLaMAFactory', eyebrow='训练框架 · 10 分钟主线',
         description='看不同数据、模型与微调配置，如何进入同一条训练流水线。',
         topics=['SFT', '数据适配', 'LoRA', 'Trainer'], first='ten-minutes',
         intro='从数据适配、Template、标签构造和模型适配出发，理解训练框架如何组织已有模型与训练能力。十分钟主线之后可以继续阅读源码提纲。'),
    dict(id='langchain', name='LangChain', eyebrow='组件编排 · 10 分钟主线',
         description='用一条 prompt | model | parser，读懂统一接口与组件组合。',
         topics=['Runnable', 'Adapter', '组合', 'invoke'], first='ten-minutes',
         intro='从一个问题经过 Prompt、模型和 Parser 的过程，理解 Model Adapter、Runnable 和 RunnableSequence。包含不需要 API Key 的模拟课堂示例。'),
    dict(id='minimind', name='MiniMind', eyebrow=f"大模型训练 · {len(MINI_MANIFEST['groups'])} 个主题",
         description='从下一个 Token 到 PPO 更新，把模型结构、训练原理与源码逐层串起来。',
         topics=['预训练与 SFT', 'Transformer', 'PPO / RLHF', 'MoE / LoRA'], first=MINI_MANIFEST['documents'][0]['parts'][0]['slug'],
         intro='从梯度与预训练出发，按训练机制、Transformer 架构、模型源码、PPO、MoE 与 LoRA 阅读。相关原理、代码和数值例子放在同一主题下，提供完整讲义下载与源码对照。'),
]


def generate_overviews():
    for project in PROJECTS:
        pid = project['id']
        pages = [p for p in PAGES if p['project'] == pid]
        group_names = list(dict.fromkeys(p['group'] for p in pages))
        text = f"---\ntitle: {project['name']}\nproject: {pid}\nprojectOverview: true\n---\n\n# {project['name']}\n\n{project['intro']}\n\n"
        text += f"[开始阅读 →](/{pid}/{project['first']}) · [返回课程首页](/) · [查看学习路线](/guide/)\n\n"
        text += '## 你会学到什么\n\n' + ' · '.join(project['topics']) + '\n\n'
        for group in group_names:
            text += f'## {group}\n\n'
            for p in pages:
                if p['group'] == group:
                    text += f"- [{p['title']}]({p['route']})\n"
            text += '\n'
        if pid == 'easyspider':
            text += '## 动手观察\n\n[打开交互演示与配套资料 →](/labs/)\n\n在交互图解中观察 XPath、DFS 和流程图数据结构，再回到对应章节读代码。\n'
        write(DOCS / pid / 'index.md', text)


def generate_sidebar():
    sidebar = {}
    for project in PROJECTS:
        pid = project['id']
        pages = [p for p in PAGES if p['project'] == pid]
        groups = list(dict.fromkeys(p['group'] for p in pages))
        sidebar['/' + pid + '/'] = [
            dict(text=project['name'], items=[dict(text='项目导读', link='/' + pid + '/')])
        ] + [dict(text=group, collapsed=False, items=[dict(text=p['title'], link=p['route']) for p in pages if p['group'] == group]) for group in groups]
    sidebar['/guide/'] = [dict(text='课程导航', items=[dict(text='如何使用这些讲义', link='/guide/'), dict(text='资料引用说明', link='/guide/unavailable')])]
    write(DOCS / '.vitepress' / 'sidebar.json', json.dumps(sidebar, ensure_ascii=False, indent=2))
    catalog = [dict(project=p['project'], title=p['title'], route=p['route'], group=p['group'], source=p['file'].relative_to(ROOT).as_posix()) for p in PAGES]
    write(PUBLIC / 'catalog.json', json.dumps(catalog, ensure_ascii=False, indent=2))
    write(DOCS / '.vitepress' / 'projects.json', json.dumps(PROJECTS, ensure_ascii=False, indent=2))
    write(DOCS / '.vitepress' / 'stats.json', json.dumps(dict(projects=len(PROJECTS), pages=len(PAGES), sourceDocuments=53+len(MINI_MANIFEST['documents'])),ensure_ascii=False))
    write(DOCS / '.vitepress' / 'minimind-manifest.json', json.dumps(MINI_MANIFEST,ensure_ascii=False,indent=2))


def main():
    # Clear only MiniMind outputs owned by this generator, including removed drafts.
    for relative in ['minimind', 'public/resources/minimind', 'public/originals/minimind']:
        target = (DOCS / relative).resolve()
        if not target.is_relative_to(DOCS.resolve()) or target == DOCS.resolve():
            raise ValueError(target)
        if target.exists():
            shutil.rmtree(target)
    prepare_catalog()
    copy_resources()
    generate_pages()
    generate_overviews()
    generate_sidebar()
    write(PUBLIC / 'source-files.json', json.dumps(SOURCE_FILES, ensure_ascii=False))
    unique_warnings = list({(w['file'], w['target']): w for w in WARNINGS}.values())
    unavailable = '# 资料引用说明\n\n## 当前资料中缺少的引用 {#reference}\n\n你打开的引用没有随当前课程文件夹提供。以下保留原稿引用的路径，便于核对和补齐版本；本站不以其他版本的同名文件替代。\n\n'
    for name in dict.fromkeys(w['file'] for w in unique_warnings):
        unavailable += f'### {Path(name).name}\n\n'
        for warning in unique_warnings:
            if warning['file'] == name:
                unavailable += f"- `{warning['target']}`\n"
        unavailable += '\n'
    unavailable += '## 如何阅读源码页\n\n本站源码阅读页展示讲义实际引用的本地文件快照，保留路径和行号，用于对照课堂内容，不会在网页中执行这些代码。\n\n[返回学习路线](/guide/)\n'
    write(DOCS / 'guide' / 'unavailable.md', unavailable)
    report = dict(lectures=len(PAGES), sourceFiles=len(SOURCE_FILES), copiedFiles=COPY_COUNT, warnings=unique_warnings)
    write(SITE / '内容同步报告.json', json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Synced {len(PAGES)} lecture pages, {len(SOURCE_FILES)} referenced source files, {COPY_COUNT} assets/originals.")
    print(f"Unavailable source references: {len(unique_warnings)}. See 内容同步报告.json.")


if __name__ == '__main__':
    main()
