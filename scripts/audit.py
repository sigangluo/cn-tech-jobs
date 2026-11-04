"""为当前看板生成可复核的数据质量快照。每个计数都来自实际发布的数据。"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from lib.companies import ROOT


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

    def counts(rows):
        n = len(rows)
        inferred = sum("按职位名识别" in j["rc"] for j in rows)
        missing_link = sum(not j["u"] for j in rows)
        return {
            "jobs": n,
            "category_inferred": inferred,
            "category_inferred_rate": round(inferred / n, 4) if n else 0,
            "years_from_text": sum(year_sources.get((j["c"], str(j["id"]))) in ("任职要求", "职位描述") for j in rows),
            "years_from_official_field": sum(year_sources.get((j["c"], str(j["id"]))) == "官网字段" for j in rows),
            "years_source_unrecorded": sum(not year_sources.get((j["c"], str(j["id"]))) for j in rows),
            "years_unspecified": sum(j["yb"] == 0 for j in rows),
            "missing_city": sum(not j["ci"] for j in rows),
            "missing_direct_link": missing_link,
            "missing_direct_link_rate": round(missing_link / n, 4) if n else 0,
            "missing_requirement": sum(not jd[j["c"]][str(j["id"])][1].strip() for j in rows),
        }

    samples = {}
    def sample_order(j):
        key = f"{data['generated']}:{j['c']}:{j['id']}".encode()
        return hashlib.sha256(key).digest()

    for c in companies:
        rows = [j for j in jobs if j["c"] == c["key"]]
        samples[c["key"]] = {
            "inferred_category": [{"id": j["id"], "title": j["t"], "category": j["cat"], "url": j["u"]}
                                  for j in sorted(rows, key=sample_order) if "按职位名识别" in j["rc"]][:5],
            "years_from_text": [{"id": j["id"], "title": j["t"], "years": j["y"],
                                 "source": year_sources.get((j["c"], str(j["id"]))),
                                 "source_excerpt": jd[j["c"]][str(j["id"])][
                                     0 if year_sources.get((j["c"], str(j["id"]))) == "职位描述" else 1][:180]}
                                for j in sorted(rows, key=sample_order)
                                if year_sources.get((j["c"], str(j["id"]))) in ("任职要求", "职位描述")][:5],
            "missing_direct_link": [{"id": j["id"], "title": j["t"]}
                                    for j in sorted(rows, key=sample_order) if not j["u"]][:5],
        }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "jobs_generated": data["generated"],
        "jobs_sha256": hashlib.sha256(raw).hexdigest(),
        "method": "规则计数和按日期、公司及职位 ID 的哈希固定抽样；样本供人工复核，不代表已由 AI 核验。年限来源未记录时不猜测，缺失任职要求只检查独立字段。",
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
    return report


def main():
    report = build_report()
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    for path in (ROOT / "site/data/quality.json", ROOT / "reports" / f"{report['jobs_generated']}.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(f"质量报告：{report['total']['jobs']} 条；类别推断 {report['total']['category_inferred']}；"
          f"缺直达链接 {report['total']['missing_direct_link']}；缺城市 {report['total']['missing_city']}")


if __name__ == "__main__":
    main()
