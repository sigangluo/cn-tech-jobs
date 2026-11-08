"""为当前看板生成可复核的数据质量快照。每个计数都来自实际发布的数据。

用法:
    python3 scripts/audit.py             # 生成 site/data/quality.json 和 reports/<数据日期>.json，并打印需要关注的项
    python3 scripts/audit.py --summary   # 把已生成的 site/data/quality.json 打印成 Markdown 表（GitHub Actions 的摘要用）

「alerts」是按 THRESHOLDS 自动标出的、值得看一眼的指标，不是错误：已知的、可以接受的情况记录在 .claude/known-issues.md，
更新数据后先对照它，只有**新出现**的或明显恶化的才需要处理。
"""
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone

from lib.companies import ROOT
from lib.schema import INFERRED_MARK

# 超过这些阈值就在 alerts 里提醒。改阈值只在这里改，文档引用这里。
THRESHOLDS = {
    "years_unspecified_rate": 0.5,       # 一半以上职位没识别出工作年限
    "missing_city_rate": 0.1,
    "missing_direct_link_rate": 0.05,
    "missing_requirement_rate": 0.05,
    "category_inferred_rate": 0.5,       # 多数职位的类别靠职位名推断
    "jobs_drop_vs_previous": 0.2,        # 比上一份报告少了这么多（抓取阶段的硬门槛是 30%）
}
TEXT_SOURCES = ("任职要求", "职位描述")


def build_report(root=ROOT):
    path = root / "site/data/jobs.json"
    raw = path.read_bytes()
    data = json.loads(raw)
    jobs = data["jobs"]
    companies = data["companies"]
    jd = {c["key"]: json.loads((root / "site/data/jd" / f"{c['key']}.json").read_text(encoding="utf-8"))
          for c in companies}
    year_sources = {}
    for c in companies:
        for path in (root / "data" / c["key"]).glob("*.csv"):
            with path.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    year_sources[(c["key"], row["职位ID"])] = row.get("年限来源", "")

    def source_of(j):
        return year_sources.get((j["c"], str(j["id"])), "")

    def counts(rows):
        n = len(rows)
        rate = lambda k: round(k / n, 4) if n else 0
        inferred = sum(INFERRED_MARK in j["rc"] for j in rows)
        missing_link = sum(not j["u"] for j in rows)
        unspecified = sum(j["yb"] == 0 for j in rows)
        missing_city = sum(not j["ci"] for j in rows)
        missing_req = sum(not jd[j["c"]][str(j["id"])][1].strip() for j in rows)
        return {
            "jobs": n,
            "category_inferred": inferred, "category_inferred_rate": rate(inferred),
            "years_from_text": sum(source_of(j) in TEXT_SOURCES for j in rows),
            "years_from_official_field": sum(source_of(j) == "官网字段" for j in rows),
            "years_not_found": sum(source_of(j) == "未找到" for j in rows),
            "years_source_unrecorded": sum(not source_of(j) for j in rows),   # 应为 0：抓取脚本都该走 resolve_years
            "years_unspecified": unspecified, "years_unspecified_rate": rate(unspecified),
            "missing_city": missing_city, "missing_city_rate": rate(missing_city),
            "missing_direct_link": missing_link, "missing_direct_link_rate": rate(missing_link),
            "missing_requirement": missing_req, "missing_requirement_rate": rate(missing_req),   # 只检查独立字段
        }

    samples = {}

    def sample_order(j):
        key = f"{data['generated']}:{j['c']}:{j['id']}".encode()
        return hashlib.sha256(key).digest()

    for c in companies:
        rows = [j for j in jobs if j["c"] == c["key"]]
        samples[c["key"]] = {
            "inferred_category": [{"id": j["id"], "title": j["t"], "category": j["cat"], "url": j["u"]}
                                  for j in sorted(rows, key=sample_order) if INFERRED_MARK in j["rc"]][:5],
            "years_from_text": [{"id": j["id"], "title": j["t"], "years": j["y"],
                                 "source": source_of(j),
                                 "source_excerpt": jd[j["c"]][str(j["id"])][
                                     0 if source_of(j) == "职位描述" else 1][:180]}
                                for j in sorted(rows, key=sample_order)
                                if source_of(j) in TEXT_SOURCES][:5],
            "missing_direct_link": [{"id": j["id"], "title": j["t"]}
                                    for j in sorted(rows, key=sample_order) if not j["u"]][:5],
        }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "jobs_generated": data["generated"],
        "jobs_sha256": hashlib.sha256(raw).hexdigest(),
        "method": "规则计数和按日期、公司及职位 ID 的哈希固定抽样；样本供人工复核，不代表已由 AI 核验。"
                  "年限来源由抓取脚本记录（任职要求 / 职位描述 / 官网字段 / 未找到）；缺失任职要求只检查独立字段。",
        "total": counts(jobs),
        "companies": [{"key": c["key"], "name": c["name"], "fetched_at": c.get("fetched_at"),
                       **counts([j for j in jobs if j["c"] == c["key"]]), "samples": samples[c["key"]]}
                      for c in companies],
    }
    earlier = sorted(p for p in (root / "reports").glob("*.json") if p.stem < data["generated"])
    if earlier:
        previous = json.loads(earlier[-1].read_text(encoding="utf-8"))
        report["previous_report"] = earlier[-1].name
        old_by_key = {c["key"]: c for c in previous["companies"]}
        for c in report["companies"]:
            if c["key"] in old_by_key:
                c["jobs_change"] = c["jobs"] - old_by_key[c["key"]]["jobs"]
                c["jobs_previous"] = old_by_key[c["key"]]["jobs"]
    for c in report["companies"]:
        c["alerts"] = alerts_for(c)
    report["alerts"] = [f"{c['name']}：{a}" for c in report["companies"] for a in c["alerts"]]
    return report


def alerts_for(c):
    """一家公司超过阈值的指标，返回人话列表。"""
    t, out = THRESHOLDS, []
    pct = lambda r: f"{r:.0%}"
    if c["years_source_unrecorded"]:
        out.append(f"{c['years_source_unrecorded']} 条没有年限来源（抓取脚本是不是没走 resolve_years？）")
    if c["years_unspecified_rate"] > t["years_unspecified_rate"]:
        out.append(f"{pct(c['years_unspecified_rate'])} 的职位没识别出工作年限")
    if c["missing_city_rate"] > t["missing_city_rate"]:
        out.append(f"{pct(c['missing_city_rate'])}（{c['missing_city']} 条）缺工作城市")
    if c["missing_direct_link_rate"] > t["missing_direct_link_rate"]:
        out.append(f"{pct(c['missing_direct_link_rate'])}（{c['missing_direct_link']} 条）缺直达链接")
    if c["missing_requirement_rate"] > t["missing_requirement_rate"]:
        out.append(f"{pct(c['missing_requirement_rate'])}（{c['missing_requirement']} 条）缺任职要求")
    if c["category_inferred_rate"] > t["category_inferred_rate"]:
        out.append(f"{pct(c['category_inferred_rate'])} 的职位类别靠职位名推断")
    prev = c.get("jobs_previous")
    if prev and c["jobs"] < prev * (1 - t["jobs_drop_vs_previous"]):
        out.append(f"职位数 {prev} -> {c['jobs']}，比上次少 {pct(1 - c['jobs'] / prev)}")
    return out


def markdown_summary(report):
    lines = ["| 公司 | 职位 | 较上次 | 类别推断 | 年限未提及 | 缺直达链接 | 缺城市 | 关注 |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    for c in report["companies"]:
        change = c.get("jobs_change")
        lines.append(f"| {c['name']} | {c['jobs']} | {'' if change is None else f'{change:+d}'} | {c['category_inferred']} | "
                     f"{c['years_unspecified']} | {c['missing_direct_link']} | {c['missing_city']} | {len(c['alerts']) or ''} |")
    if report["alerts"]:
        lines += ["", "**需要关注（对照 .claude/known-issues.md，只处理新出现或明显恶化的）：**", ""] + [f"- {a}" for a in report["alerts"]]
    return "\n".join(lines)


def main():
    if "--summary" in sys.argv:
        print(markdown_summary(json.loads((ROOT / "site/data/quality.json").read_text(encoding="utf-8"))))
        return
    report = build_report()
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    for path in (ROOT / "site/data/quality.json", ROOT / "reports" / f"{report['jobs_generated']}.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    t = report["total"]
    print(f"质量报告：{t['jobs']} 条；类别推断 {t['category_inferred']}；年限未提及 {t['years_unspecified']}；"
          f"缺直达链接 {t['missing_direct_link']}；缺城市 {t['missing_city']}；年限来源未记录 {t['years_source_unrecorded']}")
    if report["alerts"]:
        print(f"\n需要关注（{len(report['alerts'])} 项；对照 .claude/known-issues.md，只处理新出现或明显恶化的）：")
        for a in report["alerts"]:
            print("  -", a)


if __name__ == "__main__":
    main()
