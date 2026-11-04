"""职位标题明确指出招聘类型时，校验社招收录范围。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.scope import non_rnd_inferred_job, out_of_scope_title
from lib.feishu_hire import guess_category
from companies.alibaba.fetch import guess_category as alibaba_guess_category


class Scope(unittest.TestCase):
    def test_explicitly_out_of_scope(self):
        for title in ("【派遣】机器人平台开发工程师", "区域运维技术支持主管（派遣）", "27届校招GLM算法工程师"):
            with self.subTest(title=title):
                self.assertTrue(out_of_scope_title(title))

    def test_social_jobs_with_grad_years_are_kept(self):
        for title in ("【探索者】智能语音测试工程师(24-26届)", "校招平台后端工程师", "算法工程师"):
            with self.subTest(title=title):
                self.assertFalse(out_of_scope_title(title))

    def test_engineer_title_is_not_enough_for_tech_category(self):
        for title in ("国际物流规划工程师", "【探索者】SQE工程师（电子电器方向）",
                      "小米汽车-机电工程师-南通", "总装电气工程师", "机器人SQE工程师",
                      "新产品导入（NPI）工程师", "电池产线仿真工程师"):
            with self.subTest(title=title):
                self.assertIsNone(guess_category(title))

    def test_research_and_development_roles_are_kept(self):
        for title in ("物流算法工程师", "AI FDE工程师（制造与物流）",
                      "电机控制器机械结构工程师", "AI基建架构师"):
            with self.subTest(title=title):
                self.assertEqual(guess_category(title), "技术")

    def test_non_rnd_engineers_are_not_inferred_as_technical(self):
        for title in ("安全工程师（物流）", "【探索者】物流信息化管理工程师",
                      "物流信息化产品工程师", "产线开发工程师", "渠道开发高级经理菲律宾",
                      "机器人商业合作工程师（工业制造场景）"):
            with self.subTest(title=title):
                self.assertTrue(non_rnd_inferred_job(title))
                self.assertIsNone(guess_category(title))
        for title in ("菜鸟-高级工艺工程师-智造工厂", "盒马-前置仓开发项目管理-总部"):
            with self.subTest(title=title):
                self.assertTrue(non_rnd_inferred_job(title))
                self.assertIsNone(alibaba_guess_category(title))

    def test_review_samples_exclude_service_and_factory_operations(self):
        for title in ("运维主管", "软件刷写技工（广州）", "诚云科技-IDC运维工程师（设施）-中卫",
                      "诚云科技-高级技术服务工程师-新金融", "诚云科技-资深IT自维修工程师-杭州",
                      "阿里云智能-服务器生产测试专家-深圳"):
            with self.subTest(title=title):
                self.assertTrue(non_rnd_inferred_job(title))
        self.assertIsNone(guess_category("运维工程师（天津）", "负责换电站设备维保、安装和故障处理"))
        self.assertEqual(guess_category("运维工程师", "维护云上后台系统和自动化平台"), "技术")

    def test_logistics_software_development_is_still_in_scope(self):
        self.assertFalse(non_rnd_inferred_job("物流算法工程师"))
        self.assertEqual(guess_category("物流算法工程师"), "技术")

    def test_generic_project_titles_use_manufacturing_description(self):
        for title, duty in (("项目管理工程师（探索者）", "负责制造项目/工艺相关战略规划支持"),
                            ("项目管理高级工程师（广州）", "负责零件制造项目/工艺规划"),
                            ("项目管理高级工程师", "负责制造工程平台与产线规划")):
            with self.subTest(title=title):
                self.assertIsNone(guess_category(title, duty))
        self.assertEqual(guess_category("软件项目管理工程师", "管理软件开发和测试项目"), "技术")
