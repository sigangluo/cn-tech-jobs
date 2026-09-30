"""工作年限识别和分档的测试。运行: python3 -m unittest discover -s tests

用例都来自真实职位里出现过的写法；改 scripts/lib/years.py 的规则后先跑一遍，避免改好一处、坏了另一处。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.schema import BUCKETS, make_job, min_years, validate, year_bucket
from lib.years import parse_years


class ParseYears(unittest.TestCase):
    def check(self, text, required, preferred=""):
        self.assertEqual(parse_years(text), (required, preferred), text)

    def test_basic(self):
        self.check("3年以上后端开发经验", "3年以上")
        self.check("5年及以上研发经验", "5年以上")          # 「及以上」统一成「以上」
        self.check("具备3-5年互联网产品经验", "3-5年")
        self.check("3~5年 大数据开发经验", "3-5年")
        self.check("至少2年及以上项目开发经验", "2年以上")

    def test_chinese_numerals(self):
        self.check("两年以上产品经验", "2年以上")
        self.check("三年及以上开发经验", "3年以上")
        self.check("十年以上行业经验", "10年以上")

    def test_not_mentioned(self):
        self.check("", "未提及")
        self.check("熟悉 Python，良好的沟通能力", "未提及")
        self.check(None, "未提及")

    def test_explicit_no_limit(self):
        self.check("本科及以上学历，工作经验不限；", "不限")
        self.check("5、不限工作年限。", "不限")

    def test_not_a_work_experience_year(self):
        self.check("2026年毕业的同学", "未提及")
        self.check("2年内毕业", "未提及")
        self.check("熟悉近两年内主流开源工作的核心技术", "未提及")

    def test_preferred_in_same_clause(self):
        self.check("5年以上服务端经验，有2年以上管理经验优先", "5年以上", "2年以上")
        self.check("2年以上互联网数据分析经验优先；", "未提及", "2年以上")

    def test_preferred_section(self):
        self.check("1、3年以上后端经验；\n加分项\n1、有5年以上大模型经验", "3年以上", "5年以上")
        self.check("具备以下条件者优先：\n1、3年以上经验", "未提及", "3年以上")

    def test_priority_word_elsewhere_does_not_swallow_requirement(self):
        # 「AI素养与学习能力优先：」不是加分项分节标题，后面硬性的 5 年不能被当成优先
        text = "2、AI素养与学习能力优先：对AI有兴趣；\n4、丰富的实战经验：5年及以上数据分析经验；有平台型产品经验者加分；"
        self.check(text, "5年以上")

    def test_first_experience_year_wins(self):
        self.check("3年以上研发经验，1年以上AI研发经验", "3年以上")


class Buckets(unittest.TestCase):
    def bucket(self, years):
        return BUCKETS[year_bucket(years, min_years(years))]

    def test_mapping(self):
        cases = {
            "未提及": "未提及", "": "未提及",
            "不限": "明确不限", "0-3年": "明确不限", "3年以内": "明确不限", "3年以下": "明确不限",
            "1年以上": "1-2年", "1.5年以上": "1-2年", "2年以上": "1-2年",
            "3年以上": "3-4年", "3-5年": "3-4年", "4年以上": "3-4年",
            "5年以上": "5-7年", "7年以上": "5-7年", "8年以上": "8年以上", "10年以上": "8年以上",
        }
        for years, want in cases.items():
            self.assertEqual(self.bucket(years), want, years)


class Validate(unittest.TestCase):
    META = {"categories": {"研发": "技术", "产品": "产品"}}

    def job(self, id, category="研发", date="2026-09-30", url=""):
        return make_job(id=id, title="t", category=category, date=date, url=url)

    def test_ok_and_drops_other_categories(self):
        kept = validate([self.job("1"), self.job("2", "产品"), self.job("3", "运营")], self.META)
        self.assertEqual([j["id"] for j in kept], ["1", "2"])

    def test_rejects_bad_data(self):
        for bad in ([], [self.job("1"), self.job("1")], [self.job("1", date="昨天")], [self.job("1", url="http://x")]):
            with self.assertRaises(ValueError):
                validate(bad, self.META)

    def test_whole_site_category_missing_is_an_error(self):
        with self.assertRaises(ValueError):
            validate([self.job("1")], self.META)          # 一个「产品」都没有


if __name__ == "__main__":
    unittest.main()
