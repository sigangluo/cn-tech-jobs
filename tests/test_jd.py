"""真实招聘站点使用过的职位描述标题格式。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.jd import split_jd
from lib.feishu_hire import to_job


class SplitJD(unittest.TestCase):
    def test_common_headings(self):
        for heading in ("任职资格：", "【任职要求】", "岗位要求", "**职位要求**", "二、任职要求：", ".任职资格", "Job Requirements", "[Basic Requirements]"):
            with self.subTest(heading=heading):
                self.assertEqual(split_jd(f"岗位职责\n开发系统\n{heading}\n5年以上开发经验"),
                                 ("岗位职责\n开发系统", "5年以上开发经验"))

    def test_heading_with_requirement_on_same_line(self):
        self.assertEqual(split_jd("负责系统开发\n任职资格：3年以上开发经验"),
                         ("负责系统开发", "3年以上开发经验"))

    def test_no_heading_keeps_original(self):
        text = "负责理解岗位要求，开发系统。\n有 3 年开发经验。"
        self.assertEqual(split_jd(text), (text, ""))

    def test_years_in_single_field_without_heading(self):
        p = {"id": "1", "title": "芯片设计工程师", "description": "1.本科及以上学历，5年以上相关工作经验；\n2.熟悉芯片设计。"}
        job = to_job("example.jobs.feishu.cn", p, "技术", {"job_experience": {}, "degree_required": {}}, {})
        self.assertEqual(job["years"], "5年以上")
        self.assertEqual(job["years_source"], "职位描述")
