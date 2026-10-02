import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.geo import countries_of


class Countries(unittest.TestCase):
    def test_official_country_wins(self):
        self.assertEqual(countries_of({"country": "美国", "cities": ["北京"]}), ["美国"])

    def test_default_china(self):
        self.assertEqual(countries_of({"country": "", "cities": ["北京", "中国香港", "广东省"]}), ["中国"])
        self.assertEqual(countries_of({"country": "", "cities": []}), ["中国"])

    def test_overseas_and_multi(self):
        self.assertEqual(countries_of({"country": "", "cities": ["新加坡"]}), ["新加坡"])
        self.assertEqual(countries_of({"country": "", "cities": ["北京", "旧金山", "圣何塞"]}), ["中国", "美国"])


if __name__ == "__main__":
    unittest.main()
