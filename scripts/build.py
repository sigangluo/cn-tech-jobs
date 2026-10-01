"""把各公司的 CSV 合并成看板数据。

读:  data/<公司>/*.csv                （由 fetch_company.py 产出）
写:  site/data/jobs.json         精简职位列表（前端启动时加载）
     site/data/jd/<公司>.json     职位描述 / 任职要求（点开某个职位时才加载）
     site/data/csv/<公司>/<类别>.csv  原始 CSV 的副本，供页面上下载

公司列表来自 companies/ 目录的自动发现；这里不出现任何具体公司名。

用法:
    python3 scripts/build.py              # 以今天为数据日期
    python3 scripts/build.py --date 2026-10-05
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.companies import ROOT, discover
from lib.schema import BUCKETS, CATEGORIES, min_years, normalize_city, read_jobs, year_bucket

SITE_DATA = ROOT / "site" / "data"


def dump(path, obj, **kw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, **kw), encoding="utf-8")


def cities_of(job):
    """['北京', '上海'] 或 ['北京、上海'] 都拆成城市列表；只按顿号 / 逗号 / 斜杠切，避免把 'San Jose(USA)' 切碎。"""
    out = []
    for raw in job["cities"]:
        for c in re.split(r"[、,，/]+", raw):
            c = normalize_city(c)
            if c and c not in out:
                out.append(c)
    return out


NO_VALUE = "（未标注）"


def facet_value(job, source, multi=False):
    """专属筛选维度的取值：来源是标准字段 category（官网原始一级类别）/ subcategory / dept，或者 extra 里的列名。
    空值统一记为"（未标注）"。multi 的维度（如职位标签）一个职位可以有多个值，返回列表，extra 里用「、」分隔。"""
    v = {"category": job["category"], "subcategory": job["subcategory"], "dept": job["dept"]}.get(source) \
        or job["extra"].get(source, "")
    if multi:
        return [x.strip() for x in v.split("、") if x.strip()] or [NO_VALUE]
    return v or NO_VALUE


def load_company(c):
    """读取一家公司的全部 CSV，返回 (看板职位列表, {职位ID: [描述, 任职要求]})；还没有数据时返回 None。"""
    files = sorted(c.data_dir.glob("*.csv")) if c.data_dir.exists() else []
    if not files:
        print(f"⚠ {c.meta['name']}（{c.key}）还没有数据，已跳过。先运行: python3 scripts/update.py --only {c.key}")
        return None
    jobs, jd = [], {}
    facets = c.meta["facets"]
    for f in files:
        for j in read_jobs(f, c.meta["date_label"]):
            cat = c.meta["categories"].get(j["category"])
            if cat not in CATEGORIES:
                continue
            ymin = min_years(j["years"])
            jobs.append({
                "id": j["id"], "c": c.key, "cat": cat, "rc": j["category"], "t": j["title"], "ci": cities_of(j),
                "y": j["years"], "ym": ymin, "yb": year_bucket(j["years"], ymin), "yp": j["pref_years"],
                "dp": j["dept"], "dt": j["date"][:10],
                "u": j["url"] if j["url"].startswith("https://") else "",
                **({"f": [facet_value(j, f[1], len(f) > 2) for f in facets]} if facets else {}),
            })
            jd[j["id"]] = [j["description"], j["requirement"]]
    if len(jobs) != len({j["id"] for j in jobs}):
        sys.exit(f"{c.meta['name']} 有重复的职位 ID，数据有问题")
    return jobs, jd


def facet_defs(c, all_jobs):
    """这家公司的专属筛选维度：[{label, values: [[取值, 职位数], ...]}]，取值按职位数从多到少。"""
    mine = [j for j in all_jobs if j["c"] == c.key]
    out = []
    for i, (label, source, *_) in enumerate(c.meta["facets"]):
        counts = {}
        for j in mine:
            for v in (j["f"][i] if isinstance(j["f"][i], list) else [j["f"][i]]):
                counts[v] = counts.get(v, 0) + 1
        if set(counts) <= {NO_VALUE}:
            print(f"⚠ {c.meta['name']} 的专属筛选「{label}」（来源 {source}）所有职位都没有值，来源名是不是写错了？")
        out.append({"label": label, "values": sorted(counts.items(), key=lambda kv: (kv[0] == NO_VALUE, -kv[1], kv[0]))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat(), help="数据日期 YYYY-MM-DD")
    today = ap.parse_args().date

    companies, all_jobs, counts = [], [], {}
    for c in discover():
        loaded = load_company(c)
        if loaded is None:
            continue
        jobs, jd = loaded
        all_jobs += jobs
        companies.append(c)
        counts[c.key] = {cat: sum(j["cat"] == cat for j in jobs) for cat in CATEGORIES}
        dump(SITE_DATA / "jd" / f"{c.key}.json", jd, separators=(",", ":"))
    if not companies:
        sys.exit("没有任何公司有数据，先运行: python3 scripts/update.py")
    csv_dir = SITE_DATA / "csv"
    shutil.rmtree(csv_dir, ignore_errors=True)         # 每次整体重建，已移除的公司 / 类别不会残留
    for c in companies:
        (csv_dir / c.key).mkdir(parents=True, exist_ok=True)
        for f in c.data_dir.glob("*.csv"):
            shutil.copy(f, csv_dir / c.key / f.name)
    for f in (SITE_DATA / "jd").glob("*.json"):       # 已经移除的公司，清掉它的职位描述文件
        if f.stem not in counts:
            f.unlink()

    all_jobs.sort(key=lambda j: (j["dt"], j["id"]), reverse=True)
    dump(SITE_DATA / "jobs.json", {
        "generated": today,
        "companies": [{"key": c.key, "name": c.meta["name"], "list_url": c.meta["list_url"],
                       "note": c.meta["note"], "date_label": c.meta["date_label"],
                       "csv": sorted(f.stem for f in c.data_dir.glob("*.csv")),
                       "facets": facet_defs(c, all_jobs)} for c in companies],
        "categories": CATEGORIES,
        "buckets": BUCKETS,
        "jobs": all_jobs,
    }, separators=(",", ":"))

    print(f"{today}：共 {len(all_jobs)} 条，{len(companies)} 家公司")
    for c in companies:
        print(f"  {c.meta['name']}: " + " · ".join(f"{cat} {n}" for cat, n in counts[c.key].items()))


if __name__ == "__main__":
    main()
