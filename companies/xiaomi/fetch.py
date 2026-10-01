"""小米社招（xiaomi.jobs.f.mioffice.cn，飞书招聘的私有化部署）。接口不需要登录。"""
from lib.feishu_hire import fetch_jobs

META = dict(
    name="小米",
    order=90,
    list_url="https://xiaomi.jobs.f.mioffice.cn/index",
    categories={"技术（无类别，按职位名识别）": "技术", "产品（无类别，按职位名识别）": "产品"},
    date_label="发布时间",
    note="小米官网的职位没有类别字段，「技术」「产品」全部按职位名识别（含 工程师 / 开发 / 算法 / 产品经理 等关键词），可能有漏有误；"
         "岗位里有大量小米汽车的门店、交付、制造岗，这些不在「技术」「产品」里；只收「全职」；官网没有结构化的工作年限，从任职要求文本里识别",
)

HOST = "xiaomi.jobs.f.mioffice.cn"


def fetch():
    return fetch_jobs(HOST, label="小米")
