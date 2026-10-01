"""京东社招（zhaopin.jd.com）。接口不需要 token。"""
import re
import time
from datetime import datetime

from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="京东",
    order=60,
    list_url="https://zhaopin.jd.com/web/job/job_info_list/3",
    categories={"研发类": "技术", "产品": "产品"},
    date_label="发布时间",
    facets=[("所属业务", "dept"), ("职位类别", "官网职位类别")],
    note="京东官网的职位分类只有研发 / 运营 / 职能 / 采销 / 金融业务，没有「产品」类，产品经理散在研发类和运营类里。"
         "这里「产品」是按职位名识别的（含 产品经理 / 产品总监 / 产品规划 / 产品专家 / 产品岗，不含产品运营），"
         "只从研发类和运营类里挑，可能有漏；「技术」是研发类去掉这些产品岗。工作城市只到省级",
)

BASE = "https://zhaopin.jd.com"
API = BASE + "/web/job/job_list"
PAGE = 100          # 单页条数
DELAY = 0.5         # 请求间隔，避免给服务器压力
MAX_PAGES = 100     # 保护：接口越过最后一页时会重复返回最后一页，靠"没有新职位"停止，这个上限只是兜底

# 官网没有产品分类，靠职位名识别；只在这些官网类别里找，「产品运营」不算
PRODUCT_TITLE = re.compile(r"产品(经理|总监|规划|专家|岗)")
PRODUCT_FROM = {"研发类", "运营类"}

session = new_session(**{"Referer": BASE + "/web/job/job_info_list/3"})


def search(page):
    data = {"pageIndex": page, "pageSize": PAGE, "workCityJson": "[]", "jobTypeJson": "[]", "jobSearch": "", "depTypeJson": "[]"}
    return call_json(lambda: session.post(API, data=data, timeout=30), lambda j: isinstance(j, list), "京东")


def fetch():
    raw = {}
    for page in range(1, MAX_PAGES + 1):
        items = search(page)
        new = [p for p in items if p["id"] not in raw]
        if not new:
            break
        for p in new:
            raw[p["id"]] = p
        print(f"第 {page} 页，累计去重 {len(raw)}", flush=True)
        time.sleep(DELAY)
    jobs = []
    for p in raw.values():
        years, pref = parse_years(p.get("qualification"))
        ts = p.get("publishTime")
        title = p.get("positionNameOpen") or p.get("positionName")
        is_product = p.get("jobType") in PRODUCT_FROM and PRODUCT_TITLE.search(title or "")
        jobs.append(make_job(
            id=p["id"], code=p.get("positionCode"), title=title,
            category="产品" if is_product else p.get("jobType"), cities=[p.get("workCity")], dept=p.get("positionDeptName"),
            years=years, pref_years=pref,
            date=p.get("formatPublishTime") or (datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""),
            url="", description=p.get("workContent"), requirement=p.get("qualification"),
            extra={"官网职位类别": p.get("jobType")}))
    return jobs
