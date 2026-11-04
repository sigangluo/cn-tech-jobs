"""抓取单家公司，校验后写出 data/<key>/<看板类别>.csv。

用法:  python3 scripts/fetch_company.py <key> [--accept-large-drop]
一般不直接用，由 update.py 并行调用；也可以单独跑来调试新加的公司。
"""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 让公司的 fetch.py 能 from lib... 导入

from lib.companies import discover
from lib.schema import CATEGORIES, count_rows, to_frame, validate

DROP_WARN = 0.3   # 比上次少了这么多以上就报警：多半是抓取不全，而不是真的下架了这么多


def main():
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--accept-large-drop"):
        sys.exit(__doc__)
    (c,) = discover([sys.argv[1]])
    accept_large_drop = len(sys.argv) == 3
    jobs = validate(c.module.fetch(), c.meta)
    for j in jobs:
        j["site_category"] = c.meta["categories"][j["category"]]
    before = count_rows(c.data_dir.glob("*.csv")) if c.data_dir.exists() else 0   # 覆盖前的职位数
    if before and len(jobs) < before * (1 - DROP_WARN):
        msg = f"职位数 {before} -> {len(jobs)}，减少超过 {DROP_WARN:.0%}，可能是抓取不全"
        if not accept_large_drop:
            sys.exit(f"质量门槛未通过：{msg}。旧 CSV 未覆盖；确认官网确有下架后，用 --accept-large-drop 显式接受。")
        print(f"⚠ 已显式接受：{msg}", flush=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    written = set()
    for cat in CATEGORIES:
        part = sorted((j for j in jobs if j["site_category"] == cat), key=lambda j: (j["date"], j["id"]), reverse=True)
        if not part:
            continue
        to_frame(part, c.meta["date_label"]).to_csv(c.data_dir / f"{cat}.csv", index=False, encoding="utf-8-sig")
        written.add(f"{cat}.csv")
        print(f"  {cat}: {len(part)} 条", flush=True)
    for stale in c.data_dir.glob("*.csv"):     # META["categories"] 改过之后，清掉不再产出的旧文件
        if stale.name not in written:
            stale.unlink()
    (c.data_dir / "fetched.json").write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "rows": len(jobs)}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"完成：共 {len(jobs)} 条 -> {c.data_dir}", flush=True)


if __name__ == "__main__":
    main()
