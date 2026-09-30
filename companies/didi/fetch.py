"""滴滴社招（talent.didiglobal.com）。接口不需要 token。"""
import time

from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="滴滴",
    order=30,
    list_url="https://talent.didiglobal.com/social",
    categories={"技术": "技术", "产品": "产品"},
    date_label="发布时间",
    facets=[("部门", "dept")],
)

API = "https://talent.didiglobal.com/recruit-portal-service/api/job/front/list"
PAGE = 100          # 单页条数；200 会返回空
DELAY = 1.0         # 请求间隔，避免给服务器压力
# 要抓的职位类别（名称 -> 接口的 jobTypeList 取值），加类别：这里补一行，META["categories"] 里再映射一下
# 其他类别: 5 运营, 24 商业分析, 23 职能与支持, 18 安全, 21 销售与客户服务, 22 市场与公关, 2 设计, 15 战略, 19 供应链
CATEGORY_IDS = {"技术": 1, "产品": 3}

session = new_session(**{"Accept-Language": "zh-CN,zh;q=0.9", "Referer": "https://talent.didiglobal.com/social"})


def search(page, job_type):
    r = call_json(lambda: session.get(API, params={"jobTypeList": job_type, "page": page, "size": PAGE}, timeout=30),
                  lambda j: j.get("data") is not None, "滴滴")
    return r["data"]


def crawl(raw, label, job_type):
    """翻页抓取某个类别的所有职位，写入 raw（按 jdId 去重）。"""
    page = 1
    while True:
        d = search(page, job_type)
        for p in d["items"]:
            raw[p["jdId"]] = p
        if not d["items"] or page * PAGE >= d["total"]:
            break
        page += 1
        time.sleep(DELAY)
    print(f"[{label}] 总数 {d['total']}，累计去重 {len(raw)}", flush=True)


def fetch():
    raw = {}
    for name, job_type in CATEGORY_IDS.items():
        crawl(raw, name, job_type)
    jobs = []
    for p in raw.values():
        years, pref = parse_years(p.get("jobQualification"))
        jobs.append(make_job(
            id=p["jdId"], code=p.get("jdNo"), title=p.get("jobName"), category=p.get("jobTypeName"),
            cities=[p.get("workArea")], dept=p.get("deptName"), years=years, pref_years=pref,
            date=p.get("createTime"), description=p.get("jobDuty"), requirement=p.get("jobQualification"),
            extra={"更新时间": p.get("refreshTime")}))
    return jobs
