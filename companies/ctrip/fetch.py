"""携程集团社招（careers.ctrip.com）。接口不需要登录，一次请求就能取完全部职位。"""
import html
import re

from lib.http import FetchError, call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="携程",
    order=140,
    list_url="https://careers.ctrip.com/#/experienced/jobList",
    categories={"软件开发": "技术", "测试": "技术", "AI & BI": "技术", "运维": "技术", "系统安全": "技术", "产品管理": "产品"},
    date_label="发布时间",
    facets=[("职位类型", "category"), ("事业部", "dept")],
    note="「技术」= 官网职位族里的软件开发、测试、AI 与 BI、运维、系统安全，不含技术项目管理；「产品」= 产品管理，不含 UX 设计；"
         "只收「正式」岗位，不含实习和临时工；官网没有结构化的工作年限，从任职要求文本里识别",
)

BASE = "https://careers.ctrip.com"
HEAD = {"language": "zh_CN", "version": "1"}
# 官网职位族（jobFamilyGroupCode）-> 中文名。其他: JFG_21 财务, 22 HR, 23 法务, 24 行政, 25 采购, 26 公共事务, 36 技术项目管理, 42 UX 设计, 51 市场 ……
FAMILIES = {"JFG_31": "软件开发", "JFG_32": "测试", "JFG_33": "AI & BI", "JFG_34": "运维", "JFG_35": "系统安全", "JFG_41": "产品管理"}
REGULAR = "1"       # kind：1 正式，3 临时（实习是另一个值）

session = new_session(Referer=BASE + "/", Origin=BASE)
session.cookies.set("language", "zh-CN")    # 接口按这个 cookie 决定城市名等是中文还是英文


def post(path, body, what):
    return call_json(lambda: session.post(f"{BASE}/api/{path}", json={**body, "head": HEAD}, timeout=60),
                     lambda j: j.get("retCode") == "201" and j.get("retValue") is not None, what)["retValue"]


def to_text(s):
    """职位描述是一段 HTML：段落换行，去掉标签。"""
    s = re.sub(r"</p>|<br\s*/?>|</li>", "\n", s or "")
    return re.sub(r"\n{3,}", "\n\n", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def split_jd(text):
    """requirements 形如「职位描述\n…\n任职资格\n…」，拆成 (职责, 要求)。"""
    m = re.search(r"\n任职资格\s*\n", text)
    duty, req = (text[:m.start()], text[m.end():]) if m else (text, "")
    return re.sub(r"^职位描述\s*", "", duty).strip(), req.strip()


def fetch():
    cities = {x["code"]: x["name"] for x in post("oversea/getLocation", {"countryCode": "", "citycode": "", "type": "OverseasCareersWorkPlace"}, "携程地点")}
    cond = {"fromId": [], "keyword": "", "kind": [], "country": [], "city": [], "bucode": [], "jobFamilyCode": [],
            "jobFamilyGroupCode": [], "category": 1}
    d = post("hrrecruit/getJobAd", {"condition": cond, "pager": {"index": "1", "size": "1000"}}, "携程职位")
    ads = d["recruitJobAdList"]
    if len(ads) < d["total"]:
        raise FetchError(f"携程: 官网共 {d['total']} 条，只抓到 {len(ads)} 条（单页上限变了？）")
    jobs = []
    for a in ads:
        if a.get("kind") != REGULAR or a.get("jobFamilyGroupCode") not in FAMILIES:
            continue
        duty, req = split_jd(to_text(a.get("requirements")))
        years, pref = parse_years(req or duty)
        jobs.append(make_job(
            id=a["fromId"], title=re.sub(rf"\(?{re.escape(a['fromId'])}\)?$", "", a["jobTitle"] or "").strip(),
            category=FAMILIES[a["jobFamilyGroupCode"]], cities=[cities.get(a.get("city")) or a.get("cityName")], dept=a.get("buName"),
            years=years, pref_years=pref, date=a.get("publishDate"), url=f"{BASE}/#/experienced/job-detail/{a['fromId']}",
            description=duty, requirement=req))
    return jobs
