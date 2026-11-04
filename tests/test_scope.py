"""职位标题明确指出招聘类型时，校验社招收录范围。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.scope import out_of_scope_title
from lib.feishu_hire import guess_category


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
                      "小米汽车-机电工程师-南通", "总装电气工程师", "机器人SQE工程师"):
            with self.subTest(title=title):
                self.assertIsNone(guess_category(title))

    def test_research_and_development_roles_are_kept(self):
        for title in ("物流算法工程师", "AI FDE工程师（制造与物流）",
                      "电机控制器机械结构工程师", "AI基建架构师"):
            with self.subTest(title=title):
                self.assertEqual(guess_category(title), "技术")
