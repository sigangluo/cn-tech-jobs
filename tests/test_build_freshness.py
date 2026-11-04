import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build import fetched_at


class Freshness(unittest.TestCase):
    def test_timestamp_requires_matching_row_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = SimpleNamespace(key="example", data_dir=Path(tmp))
            self.assertIsNone(fetched_at(c, 2))
            (c.data_dir / "fetched.json").write_text(json.dumps({"fetched_at": "2026-11-04T10:00:00+00:00", "rows": 3}))
            with self.assertRaisesRegex(SystemExit, "职位数不符"):
                fetched_at(c, 2)
            self.assertEqual(fetched_at(c, 3), "2026-11-04T10:00:00+00:00")
