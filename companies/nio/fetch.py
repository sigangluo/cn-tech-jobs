"""蔚来社招（nio.jobs.feishu.cn，飞书招聘）。接口不需要登录。"""
from lib.feishu_hire import fetch_jobs

META = dict(
    name="蔚来",
    order=131,
    list_url="https://nio.jobs.feishu.cn/index",
    categories={"技术（无类别，按职位名识别）": "技术", "产品（无类别，按职位名识别）": "产品"},
    date_label="发布时间",
    facets=[("职能分类", "dept"), ("职位标签", "职位标签", "multi")],
    note="蔚来官网的职位没有类别字段，「技术」「产品」全部按职位名识别（含 工程师 / 开发 / 算法 / 产品经理 等关键词），可能有漏有误；"
         "只收「全职」；工作年限以任职要求里写的为准，没写再用官网的「工作经验」字段",
)

HOST = "nio.jobs.feishu.cn"


def fetch():
    return fetch_jobs(HOST, label="蔚来")
