"""<公司名>社招（<官网地址>）。

新增一家公司：
  1. 复制整个 _template 目录，目录名改成公司的英文 key（如 tencent），它同时是 data/<key>/ 的目录名；
  2. 改下面的 META，实现 fetch()；
  3. 运行  python3 scripts/update.py --only <key>  ——它会抓取、校验并写出 data/<key>/*.csv，
     然后  python3 scripts/update.py --build-only  合并进看板。看板、趋势、文档都会自动带上这家公司，不用改别处。

写 fetch() 前先在浏览器 F12 → Network → Fetch/XHR 里找到返回职位列表的接口，Copy as cURL，
确认不带 cookie 是否也能调通；分页上限和单页条数也要试一下。以 _ 开头的目录不会被当成公司。
"""
from lib.http import call_json, new_session   # call_json: 带重试的请求；new_session: 带 UA 的 Session
from lib.schema import make_job               # 统一的职位格式
from lib.years import parse_years             # 从任职要求里识别工作年限（接口没有结构化年限时用）

META = dict(
    name="公司名",                          # 看板上显示的名字
    order=100,                              # 显示顺序，数字小的在前（可省略）
    list_url="https://example.com/jobs",    # 官网职位列表；没有直达链接的职位会指向这里
    categories={"研发": "技术"},             # 公司自己的类别名 -> 看板类别（见 lib/schema.py 的 CATEGORIES）；只导出这里列出的。
                                            # 可以多个对一个（{"技术类": "技术", "LB技术": "技术"}）；fetch() 里 category 要填公司的原始写法，
                                            # 不要自己合并，看板会据此显示每个看板类别来自哪些原始分类
    date_label="发布时间",                   # fetch() 返回的 date 是「发布时间」还是「更新时间」
    facets=[],                              # 这家公司专属的筛选维度 [(显示名, 数据来源)]，来源是 "subcategory"、"dept" 或 extra 里的列名；
                                            # 只选中这家公司时，看板会多出对应的下拉框。挑区分度高的（十几到几十种取值），可省略
    note="",                                # 这家公司数据的特殊说明，会显示在看板页脚（可省略）
)


def fetch():
    """抓取全部职位，返回 make_job(...) 的列表。抓不到 / 接口变了就抛异常（不要返回半截数据）。"""
    raise NotImplementedError("照 companies/ 下其他公司的 fetch.py 写")
    # 示例：
    # session = new_session(Referer="https://example.com/")
    # j = call_json(lambda: session.post(URL, json={...}, timeout=30), lambda j: j["code"] == 0, "公司名")
    # years, pref = parse_years(p["requirement"])
    # return [make_job(id=p["id"], title=p["name"], category=p["type"], cities=[p["city"]],
    #                  years=years, pref_years=pref, date=p["publishDate"], url=p["url"],
    #                  description=p["duty"], requirement=p["requirement"]) for p in items]
