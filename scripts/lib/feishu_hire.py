"""飞书招聘（Feishu Hire）官网的通用抓取。

很多公司的招聘官网都是同一套系统（域名形如 xxx.jobs.feishu.cn，小米是私有化的 xiaomi.jobs.f.mioffice.cn），
接口一样：POST /api/v1/search/job/posts，不需要登录和签名。接入这类公司时 fetch.py 只需要说明域名和类别映射。

用法：fetch.py 里直接 `return fetch_jobs(HOST)`，META["categories"] 把下面的类别名映射成看板类别。

只收「全职」（官网的社招里还混着实习、外包、顾问）。每个职位的类别这样定：
  1. 职位上的 job_category 是一棵三层树（行业 → 职能 → 细分），取第二层的职能名，如「研发」「产品 / 策划 / 项目」；
  2. 很多公司没把类别填到职能层（只挂在「互联网 / 电子 / 网游」这个行业上），或者站点根本没有类别（小米、蔚来、小鹏），
     这些职位按职位名识别：category 记为「技术（无类别，按职位名识别）」或「产品（无类别，按职位名识别）」，识别不出的记为「（未分类）」，不进看板。
"""
import re
import time
from datetime import datetime, timedelta, timezone

from .http import FetchError, call_json, new_session
from .schema import make_job
from .years import resolve_years

PAGE = 100
DELAY = 3.0         # 每页约 400KB，连续请求 4 次左右就会被限流（HTTP 429 "ratelimit triggered"）
BACKOFF = (10, 20, 40, 60)   # 被限流后依次等待的秒数
CST = timezone(timedelta(hours=8))

GUESSED = {"技术": "技术（无类别，按职位名识别）", "产品": "产品（无类别，按职位名识别）"}   # 和阿里的写法一致
# 各公司 META["note"] 的共同部分
NOTE = ("只收「全职」（不含实习、外包、顾问）；工作年限以任职要求里写的为准，没写再用官网的结构化字段（有的站点没有这个字段）。"
        "官网的职能类别填写不全：有「研发」「产品 / 策划 / 项目」类别的按官网算（「产品」里会混有策划和项目管理类），"
        "没填到职能层的按职位名识别（含 工程师 / 开发 / 算法 / 产品经理 等，可能有漏有误），识别不出的不收录")
# 按职位名识别技术 / 产品岗：先排除明显不是的（销售、招聘、运营……），再看有没有研发类关键词
_NOT_TECH = re.compile(r"销售|售前|售后|招聘|采购|财务|法务|商务|运营|市场|行政|客服|顾问|实习|培训|HR|BP|门店|交付|维修|喷漆|钣金|质检|质量|生产|制造|工艺|装配|焊|冲压|设备|模具|物料|供应商|安全环保|现场|知识产权|专利")
_TECH = re.compile(r"工程师|开发|算法|架构师|研究员|科学家|软件|前端|后端|客户端|服务端|全栈|测试|运维|SRE|大模型|机器学习|深度学习|"
                   r"Android|iOS|Java|Python|C\+\+|Golang|Engineer|Developer|Scientist|数据(?:工程|挖掘|科学)|研发工程师|技术(?:专家|负责人|经理)", re.I)
_PAREN = re.compile(r"[（(][^）)]*[）)]|【[^】]*】")
_PRODUCT = re.compile(r"产品(?:经理|负责人|专家|总监|设计师)|[Pp]roduct\s*(?:Manager|Lead|Owner)|产品$")


def guess_category(title):
    """按职位名识别：返回 "技术" / "产品" / None。"""
    t = _PAREN.sub("", title or "").strip()
    if _PRODUCT.search(t) and not re.search(r"运营|实习|销售|市场", t):
        return "产品"
    if _TECH.search(t) and not _NOT_TECH.search(t):
        return "技术"
    return None


def function_name(p):
    """职位的职能类别（job_category 树的第二层）；只挂在行业层或没有类别时返回 None。"""
    chain, c = [], p.get("job_category")
    while c:
        chain.append(c.get("name"))
        c = c.get("parent")
    return chain[-2] if len(chain) >= 2 else None


def new_client(host):
    base = f"https://{host}"
    return new_session(**{"Origin": base, "Referer": base + "/index", "Portal-Channel": "saas-career", "Portal-Platform": "pc",
                          "website-path": "index", "accept-language": "zh-CN", "x-csrf-token": "undefined"})


def _call(session, host, method, path, ok, **kw):
    """带限流退避的请求：被限流（429 / 空内容）就按 BACKOFF 等待后重试，最后仍失败由 call_json 抛 FetchError。"""
    limited = lambda r: r.status_code == 429 or not r.text.strip() or r.text.startswith("ratelimit")

    def send():
        r = session.request(method, f"https://{host}{path}", timeout=30, **kw)
        for wait in BACKOFF:
            if not limited(r):
                break
            print(f"{host}: 被限流，等 {wait}s", flush=True)
            time.sleep(wait)
            r = session.request(method, f"https://{host}{path}", timeout=30, **kw)
        return r
    return call_json(send, ok, host)["data"]


def search(session, host, offset, portal_type=6):
    body = {"keyword": "", "limit": PAGE, "offset": offset, "job_category_id_list": [], "tag_id_list": [], "location_code_list": [],
            "subject_id_list": [], "recruitment_id_list": [], "portal_type": portal_type, "job_function_id_list": [],
            "storefront_id_list": [], "portal_entrance": 1}
    return _call(session, host, "POST", "/api/v1/search/job/posts",
                 lambda j: j.get("code") == 0 and isinstance((j.get("data") or {}).get("job_post_list"), list), json=body)


def enums(session, host):
    """官网用数字编码的字段（学历要求、工作经验）-> 文字。"""
    d = _call(session, host, "GET", "/api/v1/common/setting", lambda j: j.get("code") == 0 and isinstance(j.get("data"), dict))
    return {k: {x["key"]: x["val"] for x in d.get(k) or []} for k in ("degree_required", "job_experience")}


def function_tops(session, host, portal_type=6):
    """官网的「职能分类」是两层（大类 → 细分），职位上带的是细分。返回 {细分的 id: 大类名}，官网筛选用的是大类。"""
    d = _call(session, host, "GET", f"/api/v1/config/job/filters/{portal_type}", lambda j: j.get("code") == 0 and isinstance(j.get("data"), dict))
    return {c["id"]: top["name"] for top in d.get("job_function_list") or [] for c in top.get("children") or []}


def crawl(session, host, portal_type=6):
    """翻页抓取全部职位；抓到的数量少于官网声明的总数就抛异常。"""
    posts, offset = {}, 0
    while True:
        d = search(session, host, offset, portal_type)
        total = d["count"]
        for p in d["job_post_list"]:
            posts[p["id"]] = p
        offset += PAGE
        if offset >= total or not d["job_post_list"]:
            break
        time.sleep(DELAY)
    if len(posts) < total:
        raise FetchError(f"{host}: 官网共 {total} 条，只抓到 {len(posts)} 条")
    return list(posts.values())


def structured_years(code, names):
    """官网「工作经验」枚举 -> 工作年限文本：'3 - 5 年' -> '3-5年'，'应届毕业生' / '不限' -> '不限'；没填返回 None。"""
    v = (names.get(code) or "").replace(" ", "")
    if not v:
        return None
    return "不限" if v in ("不限", "应届毕业生") else v


def to_job(host, p, category, names, tops):
    """飞书招聘的一条职位 -> 标准职位。

    官网的筛选项都带上：subcategory = 职位类别（职能层），dept = 职能分类（大类），extra 里有 职位标签（多个）/ 招聘项目 / 学历要求 / 职能细分。
    工作年限以任职要求里写的为准，没写再用官网的结构化字段（见 years.resolve_years）。
    """
    req = p.get("requirement") or ""
    info = p.get("job_post_info") or {}
    years, pref, source = resolve_years(structured_years(info.get("experience"), names["job_experience"]), req)
    ts = p.get("publish_time")
    cities = [c.get("name") for c in (p.get("city_list") or [])] or [(p.get("city_info") or {}).get("name")]
    fn = p.get("job_function") or {}
    top = tops.get(fn.get("id")) or fn.get("name") or ""
    tags = [((t.get("name") or {}).get("name") or "").strip() for t in (p.get("tag_list") or [])]
    return make_job(
        id=p["id"], code=p.get("code"), title=p.get("title"), category=category, subcategory=function_name(p) or "",
        cities=cities, dept=top,
        years=years, pref_years=pref, date=datetime.fromtimestamp(ts / 1000, CST).strftime("%Y-%m-%d") if ts else "",
        url=f"https://{host}/index/position/{p['id']}/detail", description=p.get("description"), requirement=req,
        extra={"职位标签": "、".join(t for t in tags if t),
               "招聘项目": ((p.get("job_subject") or {}).get("name") or {}).get("zh_cn") or "",
               "学历要求": names["degree_required"].get(info.get("required_degree"), ""), "职能细分": fn.get("name") if fn.get("name") != top else "", "年限来源": source})


def fetch_jobs(host, *, portal_type=6, label=None):
    """抓取一家飞书招聘站点的全部全职社招，返回标准职位（category 的取法见文件头）。"""
    session = new_client(host)
    names, tops = enums(session, host), function_tops(session, host)
    posts = [p for p in crawl(session, host, portal_type) if (p.get("recruit_type") or {}).get("name") == "全职"]
    jobs, official, guessed = [], 0, 0
    for p in posts:
        cat = function_name(p)
        if cat:
            official += 1
        elif g := guess_category(p.get("title")):
            cat, guessed = GUESSED[g], guessed + 1
        else:
            cat = "（未分类）"
        jobs.append(to_job(host, p, cat, names, tops))
    print(f"[{label or host}] 全职 {len(posts)} 条：官网类别 {official}，按职位名识别 {guessed}，未分类 {len(posts) - official - guessed}", flush=True)
    return jobs
