"""Serve the built site locally, including VitePress clean URLs."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import webbrowser
from urllib.parse import urlsplit

DIST = Path(__file__).resolve().parents[1] / 'docs' / '.vitepress' / 'dist'


class DocumentationHandler(SimpleHTTPRequestHandler):
    base_path = '/'
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.mp4': 'video/mp4'}

    def list_directory(self, path):
        # Removed sections must return 404 rather than expose a directory listing.
        self.send_error(404, 'File not found')
        return None

    def translate_path(self, path):
        pathname = urlsplit(path).path
        if self.base_path != '/' and pathname.startswith(self.base_path):
            pathname = '/' + pathname[len(self.base_path):]
        target = Path(super().translate_path(pathname))
        if not target.exists() and target.suffix == '' and target.with_suffix('.html').exists():
            return str(target.with_suffix('.html'))
        return str(target)

    def serve_request(self, head=False):
        pathname = urlsplit(self.path).path
        if self.base_path != '/':
            if pathname in ('/', self.base_path.rstrip('/')):
                self.send_response(302)
                self.send_header('Location', self.base_path)
                self.end_headers()
                return
            if not pathname.startswith(self.base_path):
                self.send_error(404, 'URL is outside the site base path')
                return
        if head:
            super().do_HEAD()
        else:
            super().do_GET()

    def do_GET(self):
        self.serve_request()

    def do_HEAD(self):
        self.serve_request(head=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--directory', type=Path, default=DIST, help='Built site directory.')
    parser.add_argument('--base', help='Override the base path recorded in site-build.json.')
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--no-open', dest='open', action='store_false', help='Start without opening a browser window.')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not (directory / 'index.html').is_file():
        raise SystemExit('No built index.html. Run npm run build (local) or npm run pages:build (GitHub Pages) first.')
    metadata = directory / 'site-build.json'
    base = args.base if args.base is not None else (json.loads(metadata.read_text(encoding='utf-8'))['base'] if metadata.exists() else '/')
    if not base.startswith('/') or any(c in base for c in '\\?#') or '//' in base or any(p in ('.', '..') for p in base.split('/')):
        raise SystemExit('Invalid site base path.')
    DocumentationHandler.base_path = base.rstrip('/') + '/'
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(DocumentationHandler, directory=str(directory)))
    url = f'http://127.0.0.1:{server.server_address[1]}{DocumentationHandler.base_path}'
    print(f'Course documentation: {url}', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
