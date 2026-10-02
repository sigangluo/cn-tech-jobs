"""所有公司统一的职位格式：抓取脚本产出、CSV 读写、校验、年限分档都在这里。

一个职位就是一个 dict，用 make_job() 创建。各公司特有的信息（学历、业务线……）放进 extra，
会写进 CSV，但不参与看板。
"""
import re

import pandas as pd

# 看板统一的职位类别。新增类别：这里加一项，并在各公司 META["categories"] 里映射过来（前端最多支持 8 个类别）。
CATEGORIES = ["技术", "产品"]

# 工作年限分档（按"最低年限"）。前两档不是年限而是两种"没有门槛"的情况，必须分开：
#   未提及   任职要求里没有写年限（不知道）
#   明确不限 写了"不限"，或写的是 0-N 年 / N 年以内这类没有最低门槛的要求（知道没有门槛）
# 前端约定：第 0 档用灰色（没有信息），其余档用同一色相的有序渐变。
BUCKETS = ["未提及", "明确不限", "1-2年", "3-4年", "5-7年", "8年以上"]
BUCKET_EDGES = [1, 3, 5, 8]      # 最低年限 >= 这些值时依次进入 1-2年 / 3-4年 / 5-7年 / 8年以上
NO_REQ = {"不限", "未提及", ""}

# (字段, CSV 列名)；日期列名由各公司 META["date_label"] 决定（发布时间 / 更新时间）
STANDARD = [
    ("id", "职位ID"), ("code", "职位编码"), ("title", "职位名称"),
    ("category", "职位类别"), ("subcategory", "二级类别"),
    ("cities", "工作城市"), ("country", "国家/地区"), ("dept", "部门"),
    ("years", "工作年限"), ("pref_years", "优先年限"),
    ("date", None), ("url", "链接"),
    ("description", "职位描述"), ("requirement", "任职要求"),
]
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def make_job(*, id, title, category, cities=(), country="", years="未提及", pref_years="", date="",
             code="", subcategory="", dept="", url="", description="", requirement="", extra=None):
    """创建一个标准职位。

    id:        公司内唯一的职位 ID
    category:  公司自己的一级类别名（如"研发"），由 META["categories"] 映射成看板类别
    cities:    城市列表，如 ["北京", "上海"]
    country:   国家/地区，如 "中国"；官网有就填，看板会出现通用的「国家/地区」筛选并和城市联动；没有就留空
    years:     必须的工作年限，如 "3年以上" / "3-5年" / "不限" / "未提及"
    pref_years: 只出现在"优先/加分"里的年限，没有就留空
    date:      "YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM"，含义由 META["date_label"] 说明
    url:       职位详情页，必须是 https://；没有就留空
    extra:     公司特有信息 {列名: 值}，只进 CSV
    """
    s = lambda v: "" if v is None else str(v).strip()
    return {
        "id": s(id), "code": s(code), "title": s(title), "category": s(category), "subcategory": s(subcategory),
        "cities": [s(c) for c in cities if s(c)], "country": s(country), "dept": s(dept),
        "years": s(years) or "未提及", "pref_years": s(pref_years), "date": s(date), "url": s(url),
        "description": s(description), "requirement": s(requirement),
        "extra": {k: s(v) for k, v in (extra or {}).items()},
    }


def validate(jobs, meta):
    """检查抓取结果，返回可以写入的职位（只保留 META["categories"] 里列出的类别，并映射成看板类别）。

    有问题就抛 ValueError，信息里带上下文，方便判断是接口变了还是脚本写错了。
    """
    if not jobs:
        raise ValueError("fetch() 返回了 0 条职位")
    seen, bad = set(), []
    for j in jobs:
        if not j["id"] or not j["title"]:
            bad.append(f"缺少 id 或职位名称: {j['id']!r} {j['title']!r}")
        elif j["id"] in seen:
            bad.append(f"职位 ID 重复: {j['id']}")
        elif not _DATE.match(j["date"]):
            bad.append(f"日期格式不对（要 YYYY-MM-DD…）: {j['id']} -> {j['date']!r}")
        elif j["url"] and not j["url"].startswith("https://"):
            bad.append(f"链接必须是 https://: {j['id']} -> {j['url']!r}")
        seen.add(j["id"])
    if bad:
        raise ValueError(f"{len(bad)} 处问题，前 5 条:\n  " + "\n  ".join(bad[:5]))

    mapping = meta["categories"]
    unknown = [v for v in mapping.values() if v not in CATEGORIES]
    if unknown:
        raise ValueError(f"META['categories'] 里的看板类别 {unknown} 不在 {CATEGORIES} 里（先在 schema.CATEGORIES 添加）")
    kept = [j for j in jobs if j["category"] in mapping]
    if dropped := len(jobs) - len(kept):
        print(f"忽略 {dropped} 条不在 META['categories'] 里的其他类别", flush=True)
    got = {j["category"] for j in kept}
    empty_site = [c for c in dict.fromkeys(mapping.values()) if not any(mapping[r] == c for r in got)]
    if empty_site:   # 整个看板类别一条都没有：多半是接口变了或类别名写错了
        raise ValueError(f"看板类别 {empty_site} 一条都没抓到，可能是接口变了或类别名写错了。抓到的类别有: "
                         f"{sorted({j['category'] for j in jobs})}")
    if quiet := [r for r in mapping if r not in got]:   # 某个原始分类本周恰好没有职位，不算失败
        print(f"提示: 原始分类 {quiet} 这次没有职位", flush=True)
    return kept


def count_rows(paths):
    """CSV 里的职位数（不是文本行数：职位描述里有换行）。"""
    return sum(len(pd.read_csv(p, usecols=["职位ID"], dtype=str)) for p in paths)


def to_frame(jobs, date_label):
    """职位列表 -> DataFrame（标准列 + 各公司 extra 列，extra 列按首次出现顺序排在后面）。"""
    extras = list(dict.fromkeys(k for j in jobs for k in j["extra"]))
    cols = [(f, date_label if f == "date" else label) for f, label in STANDARD]
    rows = [{**{label: ("、".join(j[f]) if f == "cities" else j[f]) for f, label in cols},
             **{k: j["extra"].get(k, "") for k in extras}} for j in jobs]
    return pd.DataFrame(rows, columns=[label for _, label in cols] + extras)


def read_jobs(path, date_label):
    """读回 CSV -> 标准职位列表（extra 列一并还原）。"""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    std = {(date_label if f == "date" else label): f for f, label in STANDARD}
    jobs = []
    for r in df.to_dict("records"):
        j = make_job(id=r["职位ID"], title=r["职位名称"], category=r["职位类别"])
        for label, f in std.items():
            if label in r:
                j[f] = r[label].strip()
        j["cities"] = [c for c in j["cities"].split("、") if c] if isinstance(j["cities"], str) else j["cities"]
        j["extra"] = {k: v for k, v in r.items() if k not in std}
        jobs.append(j)
    return jobs


def min_years(text):
    """'3-5年以上' -> 3；'1.5年以上' -> 1.5；'3年以内' / 不限 / 未提及 -> None。"""
    text = (text or "").strip()
    if text in NO_REQ or re.search(r"以内|以下", text):
        return None
    m = re.match(r"\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def year_bucket(years, ymin):
    """years 是"工作年限"文本，ymin 是 min_years(years)。返回 BUCKETS 的下标。"""
    if (years or "").strip() in ("未提及", ""):
        return 0
    if ymin is None or ymin < BUCKET_EDGES[0]:   # 不限 / 0-N年 / N年以内：没有最低门槛
        return 1
    return 2 + sum(ymin >= e for e in BUCKET_EDGES[1:])


def normalize_city(c):
    """'杭州市' -> '杭州'（两个字以上才去掉"市"，避免把"市"本身或单字城市弄坏）。"""
    c = c.strip()
    return c[:-1] if len(c) > 2 and c.endswith("市") else c
