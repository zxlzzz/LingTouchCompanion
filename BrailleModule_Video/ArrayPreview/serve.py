"""Serve only this local array preview and its assets."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import partial
import sys
import webbrowser

ROOT = Path(__file__).resolve().parent

class PreviewHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 8867), partial(PreviewHandler, directory=str(ROOT)))
    print('Array preview: http://127.0.0.1:8867/', flush=True)
    if '--open' in sys.argv:
        webbrowser.open('http://127.0.0.1:8867/')
    server.serve_forever()
