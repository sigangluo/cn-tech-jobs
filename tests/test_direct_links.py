import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from companies.alibaba.fetch import detail_url
from companies.jd.fetch import PRODUCT_INFERRED, META


class DirectLinks(unittest.TestCase):
    def test_verified_alibaba_hosts_only(self):
        self.assertEqual(detail_url(None, "123", "阿里云智能-算法工程师"),
                         "https://careers.aliyun.com/off-campus/position-detail?positionId=123")
        self.assertEqual(detail_url(None, "123", "阿里国际站-算法工程师"),
                         "https://aidc-jobs.alibaba.com/off-campus/position-detail?positionId=123")
        self.assertEqual(detail_url(None, "123", "天猫淘宝海外-算法工程师"),
                         "https://talent.taotian.com/off-campus/position-detail?positionId=123")
        self.assertEqual(detail_url(None, "123", "飞猪-算法工程师"), "")
        self.assertEqual(detail_url("菜鸟", "123", "阿里云智能-算法工程师"), "")

    def test_jd_inferred_category_is_marked(self):
        self.assertIn("按职位名识别", PRODUCT_INFERRED)
        self.assertEqual(META["categories"][PRODUCT_INFERRED], "产品")
