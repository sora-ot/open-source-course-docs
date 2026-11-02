"""Serve the built site locally, including VitePress clean URLs."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import webbrowser

DIST = Path(__file__).resolve().parents[1] / 'docs' / '.vitepress' / 'dist'


class DocumentationHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.mp4': 'video/mp4'}

    def list_directory(self, path):
        # Removed sections must return 404 rather than expose a directory listing.
        self.send_error(404, 'File not found')
        return None

    def translate_path(self, path):
        target = Path(super().translate_path(path))
        if not target.exists() and target.suffix == '' and target.with_suffix('.html').exists():
            return str(target.with_suffix('.html'))
        return str(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--no-open', dest='open', action='store_false', help='Start without opening a browser window.')
    args = parser.parse_args()
    if not DIST.is_dir():
        raise SystemExit('Build the site first: npm install, then npm run build.')
    url = f'http://127.0.0.1:{args.port}/'
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(DocumentationHandler, directory=str(DIST)))
    print(f'Course documentation: {url}', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
