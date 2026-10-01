"""蚂蚁集团社招（talent.antgroup.com）。接口不需要 token。"""
import time
from datetime import datetime, timedelta, timezone

from lib.http import FetchError, call_json, new_session
from lib.schema import make_job
from lib.years import resolve_years

META = dict(
    name="蚂蚁集团",
    order=20,
    list_url="https://talent.antgroup.com/",
    # 蚂蚁的类别命名不统一（"技术类-开发"和"技术-开发"并存，还有"LB技术"），category 保留"-"之前的原始写法，
    # 在这里合并成看板类别；这样看板上能看到每个看板类别到底来自蚂蚁的哪些原始分类
    categories={"技术类": "技术", "技术": "技术", "LB技术": "技术", "AL技术": "技术",
                "产品类": "产品", "产品": "产品", "LB产品": "产品"},
    date_label="发布时间",
    facets=[("职位类别", "category"), ("细分类别", "subcategory"), ("部门", "dept"), ("学历", "学历")],
)

API = "https://hrcareersweb.antgroup.com/api/social/position/search"
PAGE = 30           # 单页条数；超过 30 左右接口会报"系统繁忙"
DELAY = 1.0         # 请求间隔，避免给服务器压力
MAX_ROUNDS = 4      # 翻页漏项时最多补抓几轮
CST = timezone(timedelta(hours=8))
DEGREE = {"bachelor": "本科", "master": "硕士", "doctorate": "博士", "other": "其他"}

session = new_session(**{
    "content-type": "application/json;charset=UTF-8", "origin": "https://talent.antgroup.com",
    "referer": "https://talent.antgroup.com/", "accept-language": "zh-CN,zh;q=0.9",
})


def search(page_index):
    """返回一页结果；越过最后一页时 content 为空列表。"""
    body = {
        "key": "", "regions": "", "categories": "", "subCategories": "", "bgCode": "",
        "socialQrCode": "", "pageIndex": page_index, "pageSize": PAGE,
        "channel": "group_official_site", "language": "zh",
    }
    return call_json(lambda: session.post(API, json=body, timeout=30),
                     lambda j: j.get("success") and j.get("errorMsg") == "成功", "蚂蚁")


def crawl():
    """翻页抓取全部职位。翻页过程中列表顺序可能有变动导致漏项，所以不足总数时再补抓几轮，合并去重。"""
    raw, total = {}, None
    for round_ in range(1, MAX_ROUNDS + 1):
        page = 1
        while True:
            j = search(page)
            total = j["totalCount"]
            if not j["content"]:
                break
            for p in j["content"]:
                raw[p["id"]] = p
            print(f"第 {round_} 轮第 {page} 页，累计去重 {len(raw)} / {total}", flush=True)
            page += 1
            time.sleep(DELAY)
        if len(raw) >= total:
            break
    if len(raw) < total * 0.99:   # 缺失超过 1% 视为抓取失败；少量缺失（接口翻页本身不稳）只警告
        raise FetchError(f"只抓到 {len(raw)} / {total} 条，翻页漏项补抓 {MAX_ROUNDS} 轮后仍不全")
    if len(raw) < total:
        print(f"警告：只抓到 {len(raw)} / {total} 条", flush=True)
    return raw


def years(exp):
    """结构化字段 experience {from, to} -> '3年以上' / '3-5年' / '不限'。"""
    lo, hi = (exp or {}).get("from"), (exp or {}).get("to")
    if lo is None and hi is None:
        return "未提及"
    if not lo and not hi:
        return "不限"
    return f"{lo or 0}-{hi}年" if hi else f"{lo}年以上"


def fetch():
    jobs = []
    for p in crawl().values():
        head, _, sub = ((p.get("categories") or [""])[0]).partition("-")   # "技术类-开发" -> 技术类 / 开发
        y, pref, source = resolve_years(years(p.get("experience")), p.get("requirement"))
        ts = p.get("publishTime")
        jobs.append(make_job(
            id=p["id"], code=p.get("code"), title=p.get("name"), category=head, subcategory=sub,
            cities=p.get("workLocations") or [], dept=p.get("department"), years=y, pref_years=pref,
            date=datetime.fromisoformat(ts).astimezone(CST).strftime("%Y-%m-%d %H:%M") if ts else "",
            url=f"https://talent.antgroup.com/off-campus-position?positionId={p['id']}",   # 页面自带的 tid 参数是跟踪用的，不需要
            description=p.get("description"), requirement=p.get("requirement"),
            extra={"学历": DEGREE.get(p.get("degree"), p.get("degree")), "年限来源": source}))
    return jobs
