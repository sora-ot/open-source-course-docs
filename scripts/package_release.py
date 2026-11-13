"""Package the standalone source and the checked GitHub Pages build, without Git history."""
from pathlib import Path
import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile

SITE = Path(__file__).resolve().parents[1]
DIST = SITE / 'docs' / '.vitepress' / 'dist-pages'
OUTPUT = SITE / 'release'


def source_files():
    # An explicit allowlist keeps caches, local credentials and authoring backups out.
    for name in ['package.json', 'package-lock.json', 'README.md', '部署与本地调试.md', '.gitignore', '.gitattributes', '内容同步报告.json']:
        yield SITE / name
    yield from sorted(SITE.glob('*.cmd'))
    for name in ['docs', 'scripts', '.github']:
        for path in sorted((SITE / name).rglob('*')):
            relative = path.relative_to(SITE)
            if path.is_file() and not any(part in {'dist', 'dist-pages', 'cache', '.temp', '__pycache__'} for part in relative.parts) and path.suffix != '.pyc':
                yield path


def main():
    if not (DIST / 'index.html').is_file() or not (DIST / '.nojekyll').is_file():
        raise SystemExit('Run npm run pages:package to build, check and package the site.')
    metadata = json.loads((DIST / 'site-build.json').read_text(encoding='utf-8'))
    report = json.loads((SITE / 'test-results' / 'links-pages.json').read_text(encoding='utf-8'))
    if report['base'] != metadata['base'] or report['missing'] or report['anchors']:
        raise SystemExit('The GitHub Pages build must pass npm run pages:check first.')
    OUTPUT.mkdir(exist_ok=True)
    packages = []
    for name, files, base in [
        ('github-pages-static.zip', sorted(p for p in DIST.rglob('*') if p.is_file()), DIST),
        ('course-docs-source.zip', sorted(set(source_files())), SITE),
    ]:
        dest = OUTPUT / name
        with ZipFile(dest, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
                    raise ValueError(f'Unexpected linked resource: {path}')
                archive.write(path, path.relative_to(base).as_posix())
        packages.append(dict(file=name, bytes=dest.stat().st_size, sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
        print(f'Created release/{name}: {dest.stat().st_size / 1024**2:.1f} MiB', flush=True)
    (OUTPUT / '部署与本地调试.md').write_bytes((SITE / '部署与本地调试.md').read_bytes())
    (OUTPUT / 'package-manifest.json').write_text(json.dumps(dict(base=metadata['base'], packages=packages), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
