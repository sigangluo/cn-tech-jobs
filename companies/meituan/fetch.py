"""美团社招（zhaopin.meituan.com）。接口不需要 token。"""
import time
from datetime import datetime

from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="美团",
    order=40,
    list_url="https://zhaopin.meituan.com/web/position",
    categories={"技术类": "技术", "产品类": "产品"},
    date_label="更新时间",
    facets=[("二级类别", "subcategory"), ("部门", "dept")],
    note="美团接口只给「更新时间」（岗位被刷新的时间），不是首次发布时间；含 Keeta 等海外岗位",
)

BASE = "https://zhaopin.meituan.com"
API = BASE + "/api/official/job/getJobList"
PAGE = 100          # 单页条数
DELAY = 0.5         # 请求间隔，避免给服务器压力
SOCIAL = "3"        # jobType：3 社招（1 校招、2 实习）

session = new_session(**{"Referer": BASE + "/web/position", "Content-Type": "application/json"})


def search(page):
    body = {"page": {"pageNo": page, "pageSize": PAGE}, "jobShareType": "1", "keywords": "", "cityList": [],
            "department": [], "jfJgList": [], "jobType": [{"code": SOCIAL, "subCode": []}], "typeCode": [], "specialCode": []}
    return call_json(lambda: session.post(API, json=body, timeout=30),
                     lambda j: (j.get("data") or {}).get("list") is not None, "美团")["data"]


def fetch():
    raw, page = {}, 1
    while True:
        d = search(page)
        for p in d["list"]:
            raw[p["jobUnionId"]] = p
        total = d["page"]["totalCount"]
        print(f"第 {page} 页，累计去重 {len(raw)} / {total}", flush=True)
        if not d["list"] or page >= d["page"]["totalPage"]:
            break
        page += 1
        time.sleep(DELAY)
    jobs = []
    for p in raw.values():
        years, pref = parse_years(p.get("jobRequirement"))
        ts = p.get("refreshTime")
        jobs.append(make_job(
            id=p["jobUnionId"], title=p.get("name"), category=p.get("jobFamily"), subcategory=p.get("jobFamilyGroup"),
            cities=[c["name"] for c in p.get("cityList") or []], dept="、".join(d["name"] for d in p.get("department") or []),
            years=years, pref_years=pref,
            date=datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "",
            url=f"{BASE}/web/position/detail?jobUnionId={p['jobUnionId']}&highlightType=social",
            description=p.get("jobDuty"), requirement=p.get("jobRequirement")))
    return jobs
