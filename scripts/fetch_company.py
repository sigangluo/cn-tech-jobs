"""抓取单家公司，校验后写出 data/<key>/<看板类别>.csv。

用法:  python3 scripts/fetch_company.py <key>
一般不直接用，由 update.py 并行调用；也可以单独跑来调试新加的公司。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 让公司的 fetch.py 能 from lib... 导入

from lib.companies import discover
from lib.schema import CATEGORIES, count_rows, to_frame, validate

DROP_WARN = 0.3   # 比上次少了这么多以上就报警：多半是抓取不全，而不是真的下架了这么多


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    (c,) = discover([sys.argv[1]])
    jobs = validate(c.module.fetch(), c.meta)
    for j in jobs:
        j["site_category"] = c.meta["categories"][j["category"]]
    before = count_rows(c.data_dir.glob("*.csv")) if c.data_dir.exists() else 0   # 覆盖前的职位数
    if before and len(jobs) < before * (1 - DROP_WARN):
        print(f"⚠ 职位数 {before} -> {len(jobs)}，减少超过 {DROP_WARN:.0%}，可能是抓取不全，请检查上面的输出", flush=True)
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
    print(f"完成：共 {len(jobs)} 条 -> {c.data_dir}", flush=True)


if __name__ == "__main__":
    main()
