"""腾讯社招（careers.tencent.com）。接口不需要登录。列表接口没有任职要求，要逐个职位再取一次详情。"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years, resolve_years

META = dict(
    name="腾讯",
    order=11,
    list_url="https://careers.tencent.com/home.html",
    categories={"技术": "技术", "产品": "产品"},
    date_label="更新时间",
    facets=[("事业群", "dept"), ("产品线", "产品线")],
    note="只收录官网「社招」（attrId=1），不含实习和海外岗位；工作年限以任职要求里写的为准，任职要求没写时用官网的「工作经验」字段"
         "（官网字段是粗档位，常和任职要求对不上，有的还写成「不限」）；优先年限从「加分项」里识别；官网没有发布时间，这里是最近更新时间",
)

BASE = "https://careers.tencent.com"
LIST_API = BASE + "/tencentcareer/api/post/Query"
DETAIL_API = BASE + "/tencentcareer/api/post/ByPostId"
PAGE = 100
DELAY = 0.3
WORKERS = 5
# 要抓的一级职位类别（官网的 parentCategoryId）。其他: 40002 设计, 40004 营销与公关, 40005 销售/服务与支持, 40006 内容 ……
PARENT_CATEGORY_IDS = {"技术": 40001, "产品": 40003}

session = new_session(Referer=BASE + "/")


def _get(url, params, what):
    params = {"timestamp": int(time.time() * 1000), "language": "zh-cn", "area": "cn", **params}
    return call_json(lambda: session.get(url, params=params, timeout=30),
                     lambda j: j.get("Code") == 200 and isinstance(j.get("Data"), dict), what)["Data"]


def list_posts(parent_id):
    posts, page, total = [], 1, None
    while total is None or len(posts) < total:
        d = _get(LIST_API, {"attrId": 1, "parentCategoryId": parent_id, "pageIndex": page, "pageSize": PAGE}, "腾讯列表")
        total = d["Count"]
        if not d["Posts"]:
            break
        posts += d["Posts"]
        page += 1
        time.sleep(DELAY)
    ids = {p["PostId"] for p in posts}
    if len(ids) < total:
        raise ValueError(f"腾讯 parentCategoryId={parent_id}: 官网共 {total} 条，只抓到 {len(ids)} 条")
    return list({p["PostId"]: p for p in posts}.values())


def detail(post_id):
    time.sleep(DELAY)
    return _get(DETAIL_API, {"postId": post_id}, f"腾讯详情 {post_id}")


def fmt_years(name):
    """'三年以上工作经验' -> '3年以上'；'不限' -> '不限'。"""
    if (name or "").strip() in ("", "不限"):
        return "不限" if name else "未提及"
    return parse_years(name)[0]


def fetch():
    posts = []
    for category, pid in PARENT_CATEGORY_IDS.items():
        got = list_posts(pid)
        print(f"[{category}] {len(got)} 条，取详情…", flush=True)
        posts += got
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        details = list(pool.map(lambda p: detail(p["PostId"]), posts))
    jobs = []
    for p, d in zip(posts, details):
        date = re.match(r"(\d{4})年(\d{2})月(\d{2})日", d.get("LastUpdateTime") or "")
        requirement = "\n".join(x for x in (d.get("Requirement"), d.get("ImportantItem") and "【加分项】\n" + d["ImportantItem"]) if x)
        years, pref, source = resolve_years(fmt_years(d.get("RequireWorkYearsName") or p.get("RequireWorkYearsName")), requirement)
        jobs.append(make_job(
            id=p["PostId"], code=p.get("RecruitPostId"), title=d.get("RecruitPostName") or p["RecruitPostName"],
            category=d.get("CategoryName") or p["CategoryName"], cities=[d.get("LocationName") or p["LocationName"]],
            country=d.get("CountryName") or p.get("CountryName"), dept=d.get("BGName") or p.get("BGName"),
            years=years, pref_years=pref,
            date="-".join(date.groups()) if date else "",
            url=f"{BASE}/jobdesc.html?postId={p['PostId']}",
            description=d.get("Responsibility"),
            requirement=requirement,
            extra={"年限来源": source, "产品线": d.get("ProductName"), "子公司": d.get("ComName")}))
    return jobs
