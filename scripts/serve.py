"""本地预览看板：python3 scripts/serve.py [端口，默认 8000]，然后打开 http://localhost:8000。

和 `python3 -m http.server -d site` 的区别：每次都让浏览器重新校验，更新数据后刷新页面就是最新的，
不会因为浏览器缓存了旧的 jobs.json / app.js 而看到过期内容。
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


class NoCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):   # 不刷屏
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"http://localhost:{port}  （Ctrl+C 退出）")
    ThreadingHTTPServer(("127.0.0.1", port), partial(NoCache, directory=str(SITE))).serve_forever()
