"""智谱社招（app.mokahr.com/social-recruitment/zphz/148983，Moka）。接口不需要登录。"""
import base64
import html
import json
import re
import time

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from lib.feishu_hire import GUESSED, guess_category
from lib.http import call_json, new_session
from lib.schema import make_job
from lib.years import parse_years

META = dict(
    name="智谱",
    order=120,
    list_url="https://app.mokahr.com/social-recruitment/zphz/148983?locale=zh-CN#/jobs",
    categories={"算法研究": "技术", "工程研发": "技术", "产品项目方案": "产品",
                **{v: k for k, v in GUESSED.items()}},
    date_label="发布时间",
    facets=[("职位类别", "subcategory")],
    note="只收「全职」；「技术」对应官网的「算法研究」「工程研发」，「产品」对应「产品项目方案」，"
         "官网标为「其它」或没有类别的职位按职位名识别，可能有漏有误；官网没有结构化的工作年限，从任职要求文本里识别",
)

BASE = "https://app.mokahr.com"
SITE = BASE + "/social-recruitment/zphz/148983"
API = BASE + "/api/outer/ats-apply/website/jobs/v2"
PAGE = 50
DELAY = 0.3
AES_IV = b"de7c21ed8d6f50fe"

session = new_session(**{"Origin": BASE, "Referer": SITE + "?locale=zh-CN"})


def decrypt(envelope):
    key = envelope["necromancer"].encode()
    plaintext = unpad(AES.new(key, AES.MODE_CBC, AES_IV).decrypt(base64.b64decode(envelope["data"])), AES.block_size)
    return json.loads(plaintext)


def search(offset):
    body = {"orgId": "zphz", "siteId": 148983, "locale": "zh-CN", "limit": PAGE, "offset": offset}
    envelope = call_json(lambda: session.post(API, json=body, timeout=30),
                         lambda j: isinstance(j.get("data"), str) and j.get("necromancer"), "智谱")
    return decrypt(envelope)["data"]["jobs"]


def html_text(value):
    text = re.sub(r"(?i)<br\s*/?>|</(?:p|li|div|h[1-6])>", "\n", value or "")
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_jd(text):
    m = re.search(r"(?:^|\n)\s*(?:职位要求|任职要求|岗位要求|任职资格)\s*[:：]?", text)
    return (text[:m.start()], text[m.start():]) if m else (text, "")


def location(job):
    cities, countries = [], []
    for loc in job.get("locations") or []:
        province = loc.get("provinceName") or ""
        city = province if province in ("北京市", "上海市", "天津市", "重庆市") else loc.get("cityName") or province
        if city and city not in cities:
            cities.append(city)
        if loc.get("country") and loc["country"] not in countries:
            countries.append(loc["country"])
    return cities, "、".join(countries)


def fetch():
    posts, offset = [], 0
    while True:
        batch = search(offset)
        posts.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        time.sleep(DELAY)

    jobs = []
    for p in posts:
        if p.get("commitment") != "全职":
            continue
        official = (p.get("zhineng") or {}).get("name") or ""
        category = official if official in META["categories"] else GUESSED.get(guess_category(p.get("title")), "（未分类）")
        duty, req = split_jd(html_text(p.get("jobDescription")))
        years, pref = parse_years(req or duty)
        cities, country = location(p)
        jobs.append(make_job(
            id=p["id"], title=p.get("title"), category=category, subcategory=official if official != "其它" else "",
            cities=cities, country=country, years=years, pref_years=pref,
            date=(p.get("publishedAt") or p.get("openedAt") or p.get("createdAt") or "")[:10],
            url=f"{SITE}?locale=zh-CN#/job/{p['id']}", description=duty, requirement=req))
    print(f"[智谱] 全职 {sum(p.get('commitment') == '全职' for p in posts)} 条，转换 {len(jobs)} 条", flush=True)
    return jobs
