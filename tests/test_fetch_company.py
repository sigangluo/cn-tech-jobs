import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_company
from lib.schema import make_job


class LargeDropGate(unittest.TestCase):
    def test_blocks_overwrite_until_company_is_explicitly_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            old = data_dir / "技术.csv"
            old.write_text("old data", encoding="utf-8")
            jobs = [make_job(id=str(i), title=f"开发工程师 {i}", category="技术", date="2026-11-04") for i in range(6)]
            company = SimpleNamespace(
                key="example", data_dir=data_dir,
                meta={"categories": {"技术": "技术"}, "date_label": "发布时间"},
                module=SimpleNamespace(fetch=lambda: jobs),
            )
            with patch.object(fetch_company, "discover", return_value=[company]), patch.object(fetch_company, "count_rows", return_value=10):
                with patch.object(sys, "argv", ["fetch_company.py", "example"]):
                    with self.assertRaisesRegex(SystemExit, "旧 CSV 未覆盖"):
                        fetch_company.main()
                self.assertEqual(old.read_text(encoding="utf-8"), "old data")
                self.assertFalse((data_dir / "fetched.json").exists())
                with patch.object(sys, "argv", ["fetch_company.py", "example", "--accept-large-drop"]):
                    fetch_company.main()
                self.assertEqual(len(pd.read_csv(old)), 6)
                self.assertEqual(__import__("json").loads((data_dir / "fetched.json").read_text())["rows"], 6)


if __name__ == "__main__":
    unittest.main()
