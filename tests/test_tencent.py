import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from companies.tencent.fetch import subcategory_names


class TencentCategories(unittest.TestCase):
    def test_uses_official_child_names_and_excludes_parents(self):
        rows = [
            {"Code": "40001", "ParentId": "", "Name": "技术"},
            {"Code": "40001001", "ParentId": "40001", "Name": "技术研发类"},
            {"Code": "40003001", "ParentId": "40003", "Name": "产品类"},
            {"Code": "40002001", "ParentId": "40002", "Name": "设计类"},
        ]
        self.assertEqual(subcategory_names(rows), {"40001001": "技术研发类", "40003001": "产品类"})

    def test_fails_when_dictionary_shape_changes(self):
        with self.assertRaisesRegex(ValueError, "字典"):
            subcategory_names([])


if __name__ == "__main__":
    unittest.main()
