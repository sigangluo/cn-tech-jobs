"""合并（build.py）→ 质量报告（audit.py）这条链路，用最小的假数据端到端跑一遍。"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import audit
import build
from lib.schema import make_job, write_csv

META = {"name": "示例", "categories": {"研发": "技术", "产品": "产品"}, "date_label": "发布时间",
        "facets": [("二级类别", "subcategory"), ("标签", "标签", "multi")]}


def job(i, **kw):
    base = dict(id=str(i), title=f"工程师{i}", category="研发", cities=["北京市"], date="2026-11-01",
                years="3年以上", years_source="任职要求", url=f"https://example.com/{i}",
                description="做事", requirement="本科", subcategory="后端", extra={"标签": "急招、远程"})
    return make_job(**{**base, **kw})


def write_company(root, key, jobs):
    d = root / "data" / key
    d.mkdir(parents=True)
    write_csv(d / "技术.csv", jobs, "发布时间")
    return SimpleNamespace(key=key, meta=META, data_dir=d)


class LoadCompany(unittest.TestCase):
    def test_builds_compact_jobs_and_facets(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = write_company(Path(tmp), "demo", [job(1), job(2, years="未提及", years_source="未找到", url="", cities=["北京", "上海"])])
            jobs, jd = build.load_company(c)
            by_id = {j["id"]: j for j in jobs}
            self.assertEqual(by_id["1"]["ci"], ["北京"])                 # 「北京市」归一成「北京」
            self.assertEqual(by_id["1"]["yb"], 3)                        # 3 年以上 -> 3-4 年档（BUCKETS 的第 3 项）
            self.assertEqual(by_id["2"]["yb"], 0)                        # 未提及单独成档
            self.assertEqual(by_id["2"]["u"], "")                        # 没有链接就留空，不编一个
            self.assertEqual(by_id["1"]["f"], ["后端", ["急招", "远程"]])  # multi 维度是列表
            self.assertEqual(jd["1"], ["做事", "本科"])
            defs = build.facet_defs(c, jobs)
            self.assertEqual([v for v, _ in defs[1]["values"]], ["急招", "远程"])

    def test_missing_data_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = SimpleNamespace(key="none", meta=META, data_dir=Path(tmp) / "absent")
            self.assertIsNone(build.load_company(c))


class Audit(unittest.TestCase):
    def make_root(self, tmp, jobs):
        root = Path(tmp)
        c = write_company(root, "demo", jobs)
        built, jd = build.load_company(c)
        (root / "site/data/jd").mkdir(parents=True)
        (root / "reports").mkdir()
        (root / "site/data/jd/demo.json").write_text(json.dumps(jd, ensure_ascii=False), encoding="utf-8")
        (root / "site/data/jobs.json").write_text(json.dumps(
            {"generated": "2026-11-07", "companies": [{"key": "demo", "name": "示例", "fetched_at": "2026-11-07T00:00:00+00:00"}],
             "jobs": built}, ensure_ascii=False), encoding="utf-8")
        return root

    def test_counts_and_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [job(i) for i in range(4)] + [job(i, years="未提及", years_source="未找到", url="") for i in range(4, 10)]
            report = audit.build_report(self.make_root(tmp, jobs))
            c = report["companies"][0]
            self.assertEqual(c["jobs"], 10)
            self.assertEqual(c["years_unspecified"], 6)
            self.assertEqual(c["years_not_found"], 6)
            self.assertEqual(c["years_from_text"], 4)
            self.assertEqual(c["years_source_unrecorded"], 0)
            self.assertEqual(c["missing_direct_link"], 6)
            self.assertTrue(any("没识别出工作年限" in a for a in c["alerts"]))      # 60% > 50% 阈值
            self.assertTrue(any("缺直达链接" in a for a in c["alerts"]))
            self.assertEqual(report["jobs_sha256"], hashlib.sha256((Path(tmp) / "site/data/jobs.json").read_bytes()).hexdigest())
            self.assertIn("示例", audit.markdown_summary(report))

    def test_clean_data_has_no_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit.build_report(self.make_root(tmp, [job(i) for i in range(5)]))
            self.assertEqual(report["alerts"], [])

    def test_drop_vs_previous_report_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(tmp, [job(i) for i in range(5)])
            (root / "reports/2026-10-31.json").write_text(json.dumps({"companies": [{"key": "demo", "jobs": 10}]}), encoding="utf-8")
            c = audit.build_report(root)["companies"][0]
            self.assertEqual(c["jobs_change"], -5)
            self.assertTrue(any("比上次少" in a for a in c["alerts"]))


if __name__ == "__main__":
    unittest.main()
