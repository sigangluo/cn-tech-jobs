"""字节跳动社招（jobs.bytedance.com）。接口不需要 token。"""
import time
from datetime import datetime

from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="字节跳动",
    order=10,
    list_url="https://jobs.bytedance.com/experienced/position",
    categories={"研发": "技术", "产品": "产品"},   # 字节的类别名 -> 看板类别
    date_label="发布时间",
    facets=[("二级类别", "subcategory")],       # 只选中这家公司时，看板多出的筛选：(显示名, 数据来源)
    note="看板的「技术」对应字节的「研发」类",
)

BASE = "https://jobs.bytedance.com"
API = BASE + "/api/v1/search/job/posts"
PAGE = 100          # 单页条数
SEARCH_CAP = 10000  # 单次搜索最多能翻到的条数，达到时需要继续拆分条件
DELAY = 0.3         # 请求间隔，避免给服务器压力
# 要抓的一级职位类别（名称 -> ID）。加类别：这里补一行，META["categories"] 里再映射一下
CATEGORY_IDS = {
    "研发": "6704215862603155720",
    "产品": "6704215864629004552",
}

session = new_session(**{
    "Origin": BASE, "Referer": BASE + "/experienced/position",
    "Portal-Channel": "office", "Portal-Platform": "pc", "website-path": "society", "accept-language": "zh-CN",
})


def search(offset, **filters):
    body = {
        "keyword": "", "limit": PAGE, "offset": offset,
        "job_category_id_list": [], "tag_id_list": [], "location_code_list": [],
        "subject_id_list": [], "recruitment_id_list": [], "portal_type": 2,
        "job_function_id_list": [], "storefront_id_list": [], "portal_entrance": 1,
    }
    body.update(filters)
    return call_json(lambda: session.post(API, json=body, timeout=30), lambda j: j.get("code") == 0, "字节")["data"]


def crawl(raw, label, **filters):
    """翻页抓取一组条件下的所有职位，写入 raw（按 id 去重）。返回该条件的总数。"""
    data = search(0, **filters)
    total, offset = data["count"], 0
    while True:
        for p in data["job_post_list"]:
            raw[p["id"]] = p
        offset += PAGE
        if offset >= min(total, SEARCH_CAP):
            break
        time.sleep(DELAY)
        data = search(offset, **filters)
        if not data["job_post_list"]:
            break
    print(f"[{label}] 总数 {total}，累计去重 {len(raw)}", flush=True)
    return total


def to_job(p):
    c = p.get("job_category") or {}
    parent = (c.get("parent") or {}).get("name")
    ts = p.get("publish_time")
    cities = [x["name"] for x in (p.get("city_list") or []) if x.get("name")] or [(p.get("city_info") or {}).get("name")]
    years, pref = parse_years(p.get("requirement"))
    return make_job(
        id=p["id"], code=p.get("code"), title=p.get("title"),
        category=parent or c.get("name"), subcategory=c.get("name") if parent else "",
        cities=cities, years=years, pref_years=pref,
        date=datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "",
        url=f"{BASE}/experienced/position/{p['id']}/detail",
        description=p.get("description"), requirement=p.get("requirement"),
        extra={"招聘类型": (p.get("recruit_type") or {}).get("name"),
               "工作地址": (p.get("job_post_info") or {}).get("address")})


def fetch():
    raw = {}
    for name, cid in CATEGORY_IDS.items():
        n = crawl(raw, f"类别:{name}", job_category_id_list=[cid])
        if n >= SEARCH_CAP:  # 单类别超过搜索上限时，再按城市拆分补抓
            cities = {(p.get("city_info") or {}).get("code"): (p.get("city_info") or {}).get("name") for p in raw.values()}
            for code, cname in cities.items():
                if code:
                    crawl(raw, f"{name}/{cname}", job_category_id_list=[cid], location_code_list=[code])
        time.sleep(DELAY)
    return [to_job(p) for p in raw.values()]
