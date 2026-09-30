"""小红书社招（job.xiaohongshu.com）。接口不需要 token。"""
import time

from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="小红书",
    order=50,
    list_url="https://job.xiaohongshu.com/social",
    # 小红书的一级方向只有「研发 / 算法 / 非技术」，产品在「非技术」下；这里按 fetch() 里整理出的类别映射
    categories={"研发": "技术", "算法": "技术", "产品": "产品"},
    date_label="发布时间",
    facets=[("细分方向", "subcategory")],
    note="小红书的「技术」= 官网的「研发」+「算法」两个方向，「产品」是「非技术」方向下的产品分类；"
         "少数岗位官网没有填方向，按岗位类型里的「…开发」「技术管理」归入研发",
)

BASE = "https://job.xiaohongshu.com"
API = BASE + "/websiterecruit/position/pageQueryPosition"
PAGE = 100          # 单页条数；200 会返回空
DELAY = 0.5         # 请求间隔，避免给服务器压力

session = new_session(**{"Referer": BASE + "/social", "Content-Type": "application/json"})


def search(page):
    body = {"pageNum": page, "pageSize": PAGE, "recruitType": "social", "positionName": ""}
    return call_json(lambda: session.post(API, json=body, timeout=30),
                     lambda j: (j.get("data") or {}).get("list") is not None, "小红书")["data"]


def category_of(p):
    """官网的方向 -> 类别：研发 / 算法 保留，非技术下取二级方向（产品、运营……）；没填方向的看岗位类型。"""
    if p.get("directionName") == "非技术":
        return p.get("subDirectionName") or "非技术"
    if p.get("directionName"):
        return p["directionName"]
    t = p.get("jobType") or ""
    return "研发" if t.endswith("开发") or t == "技术管理" else "其他"


def fetch():
    raw, page = {}, 1
    while True:
        d = search(page)
        for p in d["list"]:
            raw[p["positionId"]] = p
        print(f"第 {page} 页，累计去重 {len(raw)} / {d['total']}", flush=True)
        if not d["list"] or page >= d["totalPage"]:
            break
        page += 1
        time.sleep(DELAY)
    jobs = []
    for p in raw.values():
        years, pref = parse_years(p.get("qualification"))
        jobs.append(make_job(
            id=p["positionId"], title=p.get("positionName"), category=category_of(p),
            subcategory=p.get("subDirectionName") or p.get("jobType"),
            cities=[c for c in (p.get("workplace") or "").split("，")], years=years, pref_years=pref,
            date=p.get("publishTime"), url=f"{BASE}/social/position/{p['positionId']}",
            description=p.get("duty"), requirement=p.get("qualification"),
            extra={"岗位类型": p.get("jobType")}))
    return jobs
