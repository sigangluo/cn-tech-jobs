"""各公司抓取脚本共用的 HTTP 小工具。"""
import time

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")


class FetchError(RuntimeError):
    """抓取失败。抛出后 fetch_company.py 会以非零退出码结束，update.py 据此中止。"""


def new_session(**headers):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*", **headers})
    return s


RATE_BACKOFF = (10, 20, 40, 60, 60, 60)   # 被限流（HTTP 429 / "ratelimit triggered"）后依次等待的秒数


def call_json(request, ok, what="请求", tries=4):
    """发请求并返回 JSON。

    request: 无参函数，返回 requests.Response；ok: 判断返回的 JSON 是否表示成功。
    网络抖动、非 JSON、业务失败都按 2s / 4s / 6s 退避重试，最终仍失败就抛 FetchError。
    被限流（429）的情况单独处理：等得更久（10s 起步），次数也更多，不占用上面的重试次数。
    """
    last, attempt, limited = "", 0, 0
    while attempt < tries:
        wait = 2 * (attempt + 1)
        try:
            r = request()
            if r.status_code == 429 or r.text.startswith("ratelimit"):
                if limited >= len(RATE_BACKOFF):
                    raise FetchError(f"{what}一直被限流，已停止")
                wait, last, limited = RATE_BACKOFF[limited], "被限流（HTTP 429）", limited + 1
                print(f"{what}: {last}，等 {wait}s", flush=True)
                time.sleep(wait)
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
        time.sleep(wait)
    raise FetchError(f"{what}连续失败，已停止：{last}")
