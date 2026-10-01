"""MiniMax 社招（vrfi1sk8a0.jobs.feishu.cn，飞书招聘）。接口不需要登录。"""
from lib.feishu_hire import NOTE, fetch_jobs

META = dict(
    name="MiniMax",
    order=121,
    list_url="https://vrfi1sk8a0.jobs.feishu.cn/index",
    categories={"研发": "技术", "技术（无类别，按职位名识别）": "技术", "产品 / 策划 / 项目": "产品", "产品（无类别，按职位名识别）": "产品"},
    date_label="发布时间",
    facets=[("招聘项目", "招聘项目"), ("职位类别", "subcategory"), ("职位标签", "职位标签", "multi")],
    note=NOTE,
)

HOST = "vrfi1sk8a0.jobs.feishu.cn"


def fetch():
    return fetch_jobs(HOST, label="MiniMax")
