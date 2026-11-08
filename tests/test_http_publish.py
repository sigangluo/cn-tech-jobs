"""重试 / 完整性核对（lib/http.py）和发布存档（publish.py）。不访问网络。"""
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import publish
from lib import http
from lib.http import FetchError


def response(text="{}", status=200, js=None):
    r = MagicMock(status_code=status, text=text, ok=200 <= status < 300)
    r.json.return_value = js if js is not None else {}
    return r


class Completeness(unittest.TestCase):
    def test_small_drift_is_tolerated_but_large_gap_fails(self):
        http.ensure_complete(724, 725, "x")                  # 实测过：翻页期间有 1 条上下架
        http.ensure_complete(725, 725, "x")
        http.ensure_complete(730, 725, "x")                  # 多了也没事
        with self.assertRaisesRegex(FetchError, "只抓到"):
            http.ensure_complete(700, 725, "x")              # 少 25 条（> 0.5%）是真的抓漏了
        with self.assertRaises(FetchError):
            http.ensure_complete(0, 3, "x")                  # 总数很小时，最多容忍 2 条
        http.ensure_complete(990, 1000, "x", tolerance=0.01)  # 阿里用 1%


class CallJson(unittest.TestCase):
    def setUp(self):
        http.STATS.update(requests=0, retries=0, rate_limited=0, waited_s=0)

    def test_retries_then_succeeds_and_counts_waits(self):
        calls = [response(js={"code": 1}), response(js={"code": 0, "data": 1})]
        with patch.object(http.time, "sleep") as sleep:
            out = http.call_json(lambda: calls.pop(0), lambda j: j["code"] == 0, "t")
        self.assertEqual(out["data"], 1)
        self.assertEqual((http.STATS["requests"], http.STATS["retries"], http.STATS["waited_s"]), (2, 1, 2))
        sleep.assert_called_once_with(2)

    def test_rate_limit_waits_longer_and_is_counted_separately(self):
        calls = [response("ratelimit triggered", 429), response(js={"code": 0})]
        with patch.object(http.time, "sleep"):
            http.call_json(lambda: calls.pop(0), lambda j: j["code"] == 0, "t")
        self.assertEqual((http.STATS["rate_limited"], http.STATS["retries"], http.STATS["waited_s"]), (1, 0, 10))

    def test_custom_rate_limit_predicate(self):     # 飞书招聘被限流时会返回空内容
        calls = [response("", 200), response(js={"code": 0})]
        with patch.object(http.time, "sleep"):
            http.call_json(lambda: calls.pop(0), lambda j: j["code"] == 0, "t", limited=lambda r: not r.text.strip())
        self.assertEqual(http.STATS["rate_limited"], 1)

    def test_gives_up_with_fetch_error(self):
        with patch.object(http.time, "sleep"):
            with self.assertRaisesRegex(FetchError, "连续失败"):
                http.call_json(lambda: response(js={"code": 1}), lambda j: j["code"] == 0, "t", tries=2)

    def test_get_ok_retries_connection_errors(self):
        session = MagicMock()
        session.get.side_effect = [ConnectionError("reset"), response()]
        with patch.object(http.time, "sleep"):
            self.assertTrue(http.get_ok(session, "https://x", "t").ok)
        session.get.side_effect = ConnectionError("reset")
        with patch.object(http.time, "sleep"):
            with self.assertRaisesRegex(FetchError, "连续失败"):
                http.get_ok(session, "https://x", "t", tries=2)


class PublishArchive(unittest.TestCase):
    def test_keeps_only_latest_backups_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stage = tmp / "stage"
            (stage / "data").mkdir(parents=True)
            (stage / "data/jobs.json").write_text("{}")
            with patch.object(publish, "BACKUPS", tmp / "bk"), patch.object(publish, "KEEP_BACKUPS", 2):
                paths = []
                for hhmmss in ("010101", "020202", "030303"):
                    with patch.object(publish, "datetime") as dt:
                        dt.now.return_value.__format__ = lambda self, fmt: hhmmss
                        paths.append(publish.save_backup(stage, "2026-11-07"))
                left = sorted(p.name for p in (tmp / "bk").iterdir())
                self.assertEqual(len(left), 2)
                out = tmp / "out"
                out.mkdir()
                publish.safe_extract(paths[-1], out)
                self.assertEqual((out / "data/jobs.json").read_text(), "{}")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            evil = tmp / "evil.tar.gz"
            with tarfile.open(evil, "w:gz") as tar:
                info = tarfile.TarInfo("../escape.txt")
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))
            dest = tmp / "dest"
            dest.mkdir()
            with self.assertRaisesRegex(SystemExit, "不安全"):
                publish.safe_extract(evil, dest)
            self.assertFalse((tmp / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
