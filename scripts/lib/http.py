"""各公司抓取脚本共用的 HTTP 小工具。

新增重试 / 等待逻辑时，请走这里的 backoff()，这样耗时会计入 STATS，update.py 的汇总才说得清「这家为什么慢」。
"""
import time

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")

# 本次抓取的请求统计：fetch_company.py 在结束时打印，update.py 汇总。
STATS = {"requests": 0, "retries": 0, "rate_limited": 0, "waited_s": 0}


class FetchError(RuntimeError):
    """抓取失败。抛出后 fetch_company.py 会以非零退出码结束，update.py 据此中止。"""


def backoff(seconds, rate_limited=False):
    """退避等待，并记入统计。rate_limited=True 表示是被限流（HTTP 429）而不是普通失败。"""
    STATS["rate_limited" if rate_limited else "retries"] += 1
    STATS["waited_s"] += seconds
    time.sleep(seconds)


def new_session(**headers):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*", **headers})
    return s


RATE_BACKOFF = (10, 20, 40, 60, 60, 60)   # 被限流（HTTP 429 / "ratelimit triggered"）后依次等待的秒数


def call_json(request, ok, what="请求", tries=4, limited=None):
    """发请求并返回 JSON。

    request: 无参函数，返回 requests.Response；ok: 判断返回的 JSON 是否表示成功。
    网络抖动、非 JSON、业务失败都按 2s / 4s / 6s 退避重试，最终仍失败就抛 FetchError。
    被限流（429）的情况单独处理：等得更久（10s 起步），次数也更多，不占用上面的重试次数。
    limited: 可选，判断一个响应是不是被限流的函数；默认只认 HTTP 429 和以 "ratelimit" 开头的正文。
    """
    is_limited = limited or (lambda r: r.status_code == 429 or r.text.startswith("ratelimit"))
    last, attempt, waits = "", 0, 0
    while attempt < tries:
        pause = 2 * (attempt + 1)
        try:
            STATS["requests"] += 1
            r = request()
            if is_limited(r):
                if waits >= len(RATE_BACKOFF):
                    raise FetchError(f"{what}一直被限流，已停止")
                last = "被限流（HTTP 429）"
                print(f"{what}: {last}，等 {RATE_BACKOFF[waits]}s", flush=True)
                backoff(RATE_BACKOFF[waits], rate_limited=True)
                waits += 1
                continue
            j = r.json()
            if ok(j):
                return j
            last = f"接口返回异常: {str(j)[:200]}"
        except FetchError:
            raise
        except Exception as e:
            last = f"请求失败: {e}"
        attempt += 1
        print(f"{what}: {last}（第 {attempt}/{tries} 次）", flush=True)
        backoff(pause)
    raise FetchError(f"{what}连续失败，已停止：{last}")


def get_ok(session, url, what="请求", tries=3, **kw):
    """带重试的普通 GET（不要求返回 JSON，比如先打开页面拿 cookie）。2xx 才算成功，最终失败抛 FetchError。"""
    last = ""
    for attempt in range(1, tries + 1):
        try:
            STATS["requests"] += 1
            r = session.get(url, timeout=30, **kw)
            if r.ok:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = f"请求失败: {e}"
        print(f"{what}: {last}（第 {attempt}/{tries} 次）", flush=True)
        if attempt < tries:
            backoff(2 * attempt)
    raise FetchError(f"{what}连续失败，已停止：{last}")


def ensure_complete(got, total, what, tolerance=0.005):
    """翻页抓取后核对数量：官网声称的总数 total，实际去重后抓到 got。

    翻页过程中职位会上下架，官网的总数和翻页内容对不齐几条是正常的（实测过 725 条只抓到 724 条）。
    所以允许少一点：最多 max(2, total × tolerance) 条，并打印警告；再多就是真的抓漏了，抛 FetchError。
    """
    if got >= total:
        return
    allowed = max(2, int(total * tolerance))
    if total - got > allowed:
        raise FetchError(f"{what}: 官网共 {total} 条，只抓到 {got} 条（允许最多少 {allowed} 条）")
    print(f"⚠ {what}: 官网共 {total} 条，抓到 {got} 条（翻页期间职位上下架造成的正常偏差，未超过容忍的 {allowed} 条）", flush=True)
