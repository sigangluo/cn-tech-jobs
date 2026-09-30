"""哔哩哔哩社招（jobs.bilibili.com）。接口不需要登录，但每次要先取一个 csrf token 放在 x-csrf 请求头里。"""
import re
import time

from lib.http import FetchError, call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="哔哩哔哩",
    order=80,
    list_url="https://jobs.bilibili.com/social/positions",
    categories={"技术类": "技术", "AI类": "技术", "产品": "产品"},
    date_label="发布时间",
    note="B 站官网没有单独的「产品类」，产品岗和运营岗都在「产品运营类」里，接口也没有再细分的字段。"
         "这里「产品」是按职位名从「产品运营类」里识别的（含 产品经理 / 产品负责人 / 产品专家 / 以「…产品」结尾，不含产品运营），可能有漏；"
         "「技术」= 官网的「技术类」+「AI 类」，不含游戏类里的游戏开发；职位描述和任职要求在接口里是同一段文本，按「工作要求」字样拆开",
)

BASE = "https://jobs.bilibili.com"
API = BASE + "/api/srs/position/positionList"
PAGE = 100          # 单页条数
DELAY = 0.5         # 请求间隔，避免给服务器压力
# 要抓的职位类别（名称 -> 接口的 postCode）。加类别：这里补一行，META["categories"] 里再映射一下
# 其他类别: 02 大职能类, 03 产品运营类, 04 设计类, 05 内容类, 06 文创类, 07 市场营销类, 08 运营保障类, 10 项目管理类, 11 游戏类
CATEGORY_CODES = {"技术类": "01", "AI类": "13", "产品运营类": "03"}

# 官网没有产品分类，靠职位名从「产品运营类」里识别：去掉括号里的补充说明后，含 产品经理/负责人/专家，或以「产品」结尾，且不是「产品运营」
PRODUCT_TITLE = re.compile(r"产品(经理|负责人|专家)|产品$")
PAREN = re.compile(r"[（(][^）)]*[）)]")

session = new_session(**{"Origin": BASE, "Referer": BASE + "/social/positions",
                         "x-appkey": "ops.ehr-api.auth", "x-usertype": "2", "x-channel": "social"})
csrf = {}


def new_token():
    j = call_json(lambda: session.get(BASE + "/api/auth/v1/csrf/token", timeout=30), lambda j: j.get("code") == 0 and j.get("data"), "B站")
    csrf["token"] = j["data"]


def search(page, code):
    body = {"pageSize": PAGE, "pageNum": page, "positionName": "", "postCode": [code], "postCodeList": [code], "workLocationList": [],
            "workTypeList": ["3"], "positionTypeList": ["3"], "deptCodeList": [], "recruitType": 0, "practiceTypes": [], "onlyHotRecruit": 0}
    return call_json(lambda: session.post(API, json=body, headers={"x-csrf": csrf["token"]}, timeout=30),
                     lambda j: j.get("code") == 0 and (j.get("data") or {}).get("list") is not None, "B站")["data"]


def split_jd(text):
    """接口里职责和要求在同一段文本里，形如「工作职责:…\n工作要求:…」；拆不开就整段当职责。"""
    m = re.search(r"\n\s*(?:工作要求|任职要求|岗位要求)\s*[:：]?", text or "")
    return (text[:m.start()], text[m.start():]) if m else (text, "")


def fetch():
    new_token()
    raw = {}
    for category, code in CATEGORY_CODES.items():
        page = 1
        while True:
            d = search(page, code)
            for p in d["list"]:
                raw[p["id"]] = (category, p)
            if not d["list"] or len(d["list"]) < PAGE:
                break
            page += 1
            time.sleep(DELAY)
        print(f"[{category}] 累计去重 {len(raw)}", flush=True)
        time.sleep(DELAY)
    jobs = []
    for category, p in raw.values():
        if category == "产品运营类":
            title = PAREN.sub("", p.get("positionName") or "").strip()
            if PRODUCT_TITLE.search(title) and "产品运营" not in title:
                category = "产品"
        duty, req = split_jd(p.get("positionDescription"))
        years, pref = parse_years(req or duty)
        jobs.append(make_job(
            id=p["id"], title=p.get("positionName"), category=category,
            cities=(p.get("workLocation") or "").replace("，", "、").split("、"), years=years, pref_years=pref,
            date=(p.get("pushTime") or "")[:16], url=f"{BASE}/social/positions/{p['id']}",
            description=duty, requirement=req, extra={"官网职位类别": p.get("postCodeName")}))
    return jobs
