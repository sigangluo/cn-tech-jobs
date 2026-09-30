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


def call_json(request, ok, what="请求", tries=4):
    """发请求并返回 JSON。

    request: 无参函数，返回 requests.Response；ok: 判断返回的 JSON 是否表示成功。
    网络抖动、非 JSON、业务失败都按 2s / 4s / 6s 退避重试，最终仍失败就抛 FetchError。
    """
    last = ""
    for attempt in range(tries):
        try:
            j = request().json()
            if ok(j):
                return j
            last = f"接口返回异常: {str(j)[:200]}"
        except Exception as e:
            last = f"请求失败: {e}"
        print(f"{what}: {last}（第 {attempt + 1}/{tries} 次）", flush=True)
        time.sleep(2 * (attempt + 1))
    raise FetchError(f"{what}连续失败，已停止：{last}")
