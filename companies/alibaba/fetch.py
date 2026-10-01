"""阿里巴巴集团社招（talent.alibaba.com）。接口不需要登录，但要先打开一次页面拿 XSRF-TOKEN 作为 _csrf 参数。

总站 talent.alibaba.com 汇总了所有事业群的岗位，但接口不说岗位属于哪个事业群。各事业群有自己的招聘站（同一套接口、不同域名），
所以再逐个抓一遍事业群站点，靠职位 id 反查事业群（各站点之间没有重复的 id）。"""
import re
import time
from datetime import datetime, timedelta, timezone

from lib.http import FetchError, call_json, new_session
from lib.schema import make_job
from lib.years import resolve_years

GUESS_TECH, GUESS_PRODUCT = "技术（无类别，按职位名识别）", "产品（无类别，按职位名识别）"

META = dict(
    name="阿里巴巴",
    order=70,
    list_url="https://talent.alibaba.com/",
    # 不同事业群的类别写法不一样：多数是「技术类」「产品类」，平头哥、控股集团等写「技术」「产品」；
    # 淘天、阿里云、盒马等事业群的大部分岗位接口不给类别，按职位名识别（见 guess_category）
    categories={"技术类": "技术", "技术": "技术", "产品类": "产品", "产品": "产品",
                GUESS_TECH: "技术", GUESS_PRODUCT: "产品"},
    date_label="发布时间",
    facets=[("事业群", "dept"), ("职位类别", "category"), ("细分类别", "subcategory"), ("学历", "学历")],
    note="汇总官网 talent.alibaba.com 下所有事业群的岗位。事业群是抓各事业群自己的招聘站再按职位 id 对应的，"
         "少数岗位（事业群站点抓取受 500 条上限限制或站点打不开的，如阿里云、飞猪）对应不上，显示为「（未标注）」；"
         "淘天、阿里云、盒马等事业群的大部分岗位接口没有给类别，这部分按职位名识别技术 / 产品（含 工程师 / 研发 / 算法 / 产品经理 等，"
         "不含解决方案架构师、售前、运营等），可能有漏也可能有误，卡片里以「无类别，按职位名识别」标出",
)

HUB = "talent.alibaba.com"
PAGE = 50           # 单页条数
DELAY = 1.0         # 请求间隔，避免给服务器压力
# 事业群名 -> 招聘站域名（总站首页「进入招聘官网」的去向）。新增事业群：这里补一行
BG_SITES = {
    "控股集团": "talent-holding.alibaba.com", "淘天集团": "talent.taotian.com", "淘宝闪购": "talent.ele.me",
    "飞猪": "talent.fliggy.com", "阿里国际数字商业": "aidc-jobs.alibaba.com", "阿里云": "careers.aliyun.com",
    "Token Foundry": "careers-tongyi.alibaba.com", "千问办公": "talent.dingtalk.com", "千问事业部": "talent.quark.cn",
    "平头哥": "recruitment.t-head.cn", "高德地图": "talent.amap.com", "菜鸟": "talent.cainiao.com",
    "虎鲸文娱": "jobs.hujing-dme.com", "盒马": "hire.freshippo.com", "阿里健康": "careers.alihealth.cn",
    "灵犀互娱": "talent.lingxigames.com", "菜鸟驿站": "talent-post.alibaba.com", "亚博科技": "talent.agtech.com",
    "橙狮体育": "jobs.alisports.com",
}
CST = timezone(timedelta(hours=8))
DEGREE = {"bachelor": "本科", "master": "硕士", "doctorate": "博士", "other": "其他"}



def open_site(host):
    """新开一个会话并拿到该站点的 XSRF-TOKEN；返回搜索函数 search(页码)。"""
    page_url = f"https://{host}/off-campus/position-list?lang=zh"
    s = new_session(**{"Origin": f"https://{host}", "Referer": page_url, "Accept-Language": "zh-CN,zh;q=0.9"})
    s.get(page_url, timeout=30)
    if not s.cookies.get("XSRF-TOKEN"):
        raise FetchError(f"阿里巴巴：{host} 没有拿到 XSRF-TOKEN，页面可能改版了")

    def search(page_index):
        body = {"channel": "group_official_site", "language": "zh", "batchId": "", "categories": "", "deptCodes": [],
                "key": "", "pageIndex": page_index, "pageSize": PAGE, "regions": "", "subCategories": "", "shareType": "",
                "shareId": "", "myReferralShareCode": ""}
        return call_json(lambda: s.post(f"https://{host}/position/search", params={"_csrf": s.cookies.get("XSRF-TOKEN")},
                                        json=body, timeout=30),
                         lambda j: j.get("success") and (j.get("content") or {}).get("datas") is not None, "阿里巴巴")["content"]
    return search


def business_groups():
    """逐个抓事业群站点，返回 {职位 id: 事业群名}。某个站点打不开或被截断只影响这一部分岗位的事业群标注，不中止。"""
    mapping = {}
    for bg, host in BG_SITES.items():
        try:
            search, page, n = open_site(host), 1, 0
            while True:
                datas = search(page)["datas"]
                if not datas:            # 这些站点的 totalCount 不可靠，翻到空页才停
                    break
                for p in datas:
                    mapping[p["id"]] = bg
                n += len(datas)
                page += 1
                time.sleep(0.3)
            print(f"[{bg}] {n} 条", flush=True)
        except Exception as e:           # 站点打不开（如飞猪是前端路由页）：这部分岗位标「未标注」
            print(f"[{bg}] 跳过：{e}", flush=True)
    return mapping


# 接口没给类别的岗位，按职位名识别。标题形如「事业群-岗位名-方向」，只看岗位名那一段。
# 规则在有官网类别的 1600 多个岗位上校验过：识别为技术的几乎都是官网标的技术（召回约七成，故意偏保守）
_TECH = re.compile(r"工程师|开发|算法|架构师|研发|测试|测开|前端|后端|客户端|科学家|SRE|DBA|技术专家|技术负责人|技术总监|Engineer|Tech Lead")
_TECH_NOT = re.compile(r"解决方案|方案架构|售前|商业技术|BTE|技术支持|技术运营|IT服务|销售|商务|运营|培训|采购|设备|电气|机电|安装|门店|施工|品控|食品|质量|"
                       r"标注|评测|财务|法务|人力|招聘|拓展|BD|市场|客户成功|交付|实施|咨询|内容开发|投资|投放|选址|消防|资产运维|机房|数据中心|暖通")
_PRODUCT = re.compile(r"产品(经理|专家|负责人|总监|规划)|产品$|Product Manager", re.I)
_PRODUCT_NOT = re.compile(r"产品运营|运营|销售|解决方案|财务|采购|市场|营销|品类|商品|招商|物流产品|供应链产品|设计师")


def guess_category(title):
    """无类别岗位的类别：产品 / 技术 / None（识别不出，不收录）。"""
    parts = (title or "").split("-")
    role = parts[1] if len(parts) > 1 else parts[0]
    if _PRODUCT.search(role) and not _PRODUCT_NOT.search(role):
        return GUESS_PRODUCT
    if _TECH.search(role) and not _TECH_NOT.search(role) and not _PRODUCT.search(role):
        return GUESS_TECH
    return None


# 详情页用浏览器验证过、能看到职位名的事业群站点之外的：菜鸟的详情页在浏览器里是空白的，链接不拼
NO_DETAIL_LINK = {"菜鸟"}


def detail_url(bg, job_id):
    """详情页在职位所属事业群自己的站点上；对应不上事业群、或详情页没验证通过的留空（看板会指向官网）。"""
    host = None if bg in NO_DETAIL_LINK else BG_SITES.get(bg)
    return f"https://{host}/off-campus/position-detail?positionId={job_id}" if host else ""


def years(exp):
    """结构化字段 experience {from, to} -> '3年以上' / '3-5年' / '不限'。"""
    lo, hi = (exp or {}).get("from"), (exp or {}).get("to")
    if lo is None and hi is None:
        return "未提及"
    if not lo and not hi:
        return "不限"
    return f"{lo or 0}-{hi}年" if hi else f"{lo}年以上"


def fetch():
    search = open_site(HUB)
    raw, page = {}, 1
    while True:
        d = search(page)
        for p in d["datas"]:
            raw[p["id"]] = p
        total = d["totalCount"]
        print(f"第 {page} 页，累计去重 {len(raw)} / {total}", flush=True)
        if not d["datas"] or page * PAGE >= total:
            break
        page += 1
        time.sleep(DELAY)
    if len(raw) < total * 0.99:
        raise FetchError(f"只抓到 {len(raw)} / {total} 条")
    bg_of = business_groups()
    print(f"事业群对应上 {sum(i in bg_of for i in raw)} / {len(raw)} 条", flush=True)
    jobs = []
    for p in raw.values():
        head, _, sub = ((p.get("categories") or [""])[0]).partition("-")   # "技术类-安全" -> 技术类 / 安全
        if not head:
            head = guess_category(p.get("name")) or ""
        y, pref, source = resolve_years(years(p.get("experience")), p.get("requirement"))
        ts = p.get("publishTime")
        jobs.append(make_job(
            id=p["id"], code=p.get("code"), title=p.get("name"), category=head, subcategory=sub,
            cities=p.get("workLocations") or [], dept=bg_of.get(p["id"]), years=y, pref_years=pref,
            date=datetime.fromtimestamp(ts / 1000, CST).strftime("%Y-%m-%d %H:%M") if ts else "",
            url=detail_url(bg_of.get(p["id"]), p["id"]),
            description=p.get("description"), requirement=p.get("requirement"),
            extra={"学历": DEGREE.get(p.get("degree"), p.get("degree")), "年限来源": source}))
    return jobs
