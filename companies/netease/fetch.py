"""网易社招（hr.163.com）。接口不需要 token。"""
import time
from datetime import datetime

from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="网易",
    order=40,
    list_url="https://hr.163.com/job-list.html",
    # 网易的一级分类里，游戏程序（客户端 / 服务端开发）、人工智能（算法）、游戏测试（测试开发）都是技术岗，和「技术」合并
    categories={"技术": "技术", "游戏程序": "技术", "人工智能": "技术", "游戏测试": "技术", "产品": "产品"},
    date_label="更新时间",
    facets=[("业务线", "业务线"), ("部门", "dept"), ("学历", "学历要求")],
    note="「技术」= 网易的「技术」+「游戏程序」+「人工智能」+「游戏测试」；游戏策划、游戏艺术、运营、市场等类别未收录",
)

BASE = "https://hr.163.com"
API = BASE + "/api/hr163/position/queryPage"
PAGE = 100   # 单页条数，接口上限（500 会失败）
DELAY = 0.3  # 请求间隔，避免给服务器压力
# workType：0 社招（页面上标「全职」），1 实习，2 外包/派遣（这一条是根据职位名称推断的）。只要社招
SOCIAL = "0"

session = new_session(**{"Origin": BASE, "Referer": BASE + "/job-list.html", "authType": "ursAuth", "language": "zh"})


def search(page):
    body = {"currentPage": page, "pageSize": PAGE}
    return call_json(lambda: session.post(API, json=body, timeout=30), lambda j: j.get("code") == 200, "网易")["data"]


def resolve_years(p):
    """返回 (工作年限, 年限来源, 优先年限)。

    接口的 reqWorkYearsName 是粗粒度档位（不限 / 0-3年 / 3-5年…）。接口写"不限"时，再去任职要求里找：
    找到具体年限就用它；找不到才保留"不限"。接口给了具体档位时直接沿用。
    """
    api = p.get("reqWorkYearsName")
    req, pref = parse_years(p.get("requirement"))
    if api and api != "不限":
        return api, "接口", pref
    if req not in ("未提及", "不限"):
        return req, "任职要求", pref
    return "不限", "接口", pref


def fetch():
    raw, page = {}, 1
    while True:
        data = search(page)
        for p in data["list"]:
            raw[p["id"]] = p
        print(f"第 {page}/{data['pages']} 页，累计去重 {len(raw)} / {data['total']}", flush=True)
        if data["lastPage"] or not data["list"]:
            break
        page += 1
        time.sleep(DELAY)
    jobs = []
    for p in raw.values():
        if p.get("workType") != SOCIAL:
            continue
        years, source, pref = resolve_years(p)
        ts = p.get("updateTime")
        jobs.append(make_job(
            id=p["id"], title=p.get("name"), category=p.get("firstPostTypeName"),
            cities=p.get("workPlaceNameList") or [], dept=p.get("firstDepName"), years=years, pref_years=pref,
            date=datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "",
            url=f"{BASE}/job-detail.html?id={p['id']}&lang=zh",   # 必须带 lang=zh，否则站点会把访问者带回首页
            description=p.get("description"), requirement=p.get("requirement"),
            extra={"业务线": p.get("productName"), "年限来源": source,
                   "学历要求": p.get("reqEducationName"), "招聘人数": p.get("recruitNum")}))
    return jobs
