"""理想汽车社招（li.jobs.feishu.cn，飞书招聘）。接口不需要登录。"""
from lib.feishu_hire import NOTE, fetch_jobs

META = dict(
    name="理想汽车",
    order=130,
    list_url="https://li.jobs.feishu.cn/index",
    categories={"研发": "技术", "技术（无类别，按职位名识别）": "技术", "产品 / 策划 / 项目": "产品", "产品（无类别，按职位名识别）": "产品"},
    date_label="发布时间",
    facets=[("职位类别", "subcategory")],
    note=NOTE + "；「技术」含官网「研发」下汽车研发和互联网研发两棵类别树里的同名类别",
)

HOST = "li.jobs.feishu.cn"


def fetch():
    return fetch_jobs(HOST, label="理想")
