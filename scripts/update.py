"""每周更新：重新抓取各公司职位，再合并成看板数据。

用法:
    python3 scripts/update.py                      # 抓取 companies/ 下所有公司 + 合并
    python3 scripts/update.py --only netease,didi  # 只重抓指定公司
    python3 scripts/update.py --build-only         # 不抓取，只用现有 data/*/*.csv 重新合并
    python3 scripts/update.py --list               # 列出当前有哪些公司
    python3 scripts/update.py --allow-failures netease   # 仅 CI 用：点名的公司抓取失败也继续合并其余公司（本机不要用）

公司由 companies/ 下的目录自动发现，新增公司不用改这里。各家互不依赖、访问不同站点，所以并行跑，总耗时约等于最慢那一家
（实测约 7 分钟，腾讯最慢）。失败的公司会在其他公司跑完后自动重试一次（多数失败是瞬时的网络抖动）；
仍然失败就中止，不会拿旧 CSV 混进新数据。结束时打印每家的耗时和请求统计，用来判断慢在哪。
"""
import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)   # 管道 / 重定向时也按行输出，避免和子进程输出顺序错乱
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from lib.companies import discover

RETRY_PAUSE = 30   # 秒。失败的公司等一会儿再重试，给限流 / 网络抖动留出恢复时间


def run(c, accept_large_drop=False):
    started = time.time()
    cmd = [sys.executable, "-W", "ignore", str(SCRIPTS / "fetch_company.py"), c.key]
    if accept_large_drop:
        cmd.append("--accept-large-drop")
    p = subprocess.run(cmd, capture_output=True, text=True)
    lines = [ln for ln in p.stdout.strip().splitlines() if ln]
    stats = {}
    if lines and lines[-1].startswith("[stats] "):
        stats = json.loads(lines.pop()[len("[stats] "):])
    # 只截取最后几行，但 ⚠ 警告不能被截掉
    tail = [ln for ln in lines[:-4] if ln.startswith("⚠")] + lines[-4:]
    # 退出码为 0 也要确认 CSV 真的被刷新了
    stale = [f.name for f in c.data_dir.glob("*.csv") if f.stat().st_mtime < started] if c.data_dir.exists() else ["（没有产出任何 CSV）"]
    ok = p.returncode == 0 and not stale and any(c.data_dir.glob("*.csv"))
    return {"c": c, "ok": ok, "tail": tail, "err": p.stderr.strip().splitlines()[-3:], "stale": stale,
            "secs": time.time() - started, "stats": stats}


def report(r):
    c = r["c"]
    print(f"\n[{c.key}] {'完成' if r['ok'] else '失败'}（{r['secs']:.0f}s）")
    for ln in r["tail"]:
        print("   ", ln)
    if not r["ok"]:
        for ln in r["err"]:
            print("    !", ln)
        if r["stale"]:
            print("    ! 这些 CSV 没有被更新:", ", ".join(r["stale"]))


def crawl_all(companies, accepted):
    with ThreadPoolExecutor(max_workers=len(companies)) as pool:
        results = list(pool.map(lambda c: run(c, c.key in accepted), companies))
    for r in results:
        report(r)
    return results


def timing_table(results, wall):
    """每家耗时 + 请求统计，慢的在前。「限流等待」是被 HTTP 429 逼着睡掉的秒数，「重试等待」是普通失败后退避的秒数。"""
    print(f"\n耗时汇总（总计 {wall:.0f}s，公司并行，总耗时约等于最慢的一家）")
    print(f"  {'公司':<12}{'耗时s':>6}{'请求数':>7}{'限流次':>7}{'重试次':>7}{'等待s':>7}")
    for r in sorted(results, key=lambda r: -r["secs"]):
        s = r["stats"]
        print(f"  {r['c'].key:<12}{r['secs']:>6.0f}{s.get('requests', '-'):>7}{s.get('rate_limited', '-'):>7}"
              f"{s.get('retries', '-'):>7}{s.get('waited_s', '-'):>7}" + ("" if r["ok"] else "  ← 失败"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只抓这些公司（key），逗号分隔")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--allow-failures", metavar="KEYS", default="",
                    help="这些公司抓取失败时不中止，用其余公司继续合并；逗号分隔。只给 CI 用（已知某家在 GitHub 服务器上抓不到），"
                         "本机用会把旧 CSV 混进新数据")
    ap.add_argument("--accept-large-drop", metavar="KEYS", help="确认官网确实大量下架后，接受指定公司本次超过 30%% 的数量下降；逗号分隔")
    args = ap.parse_args()

    if args.list:
        for c in discover():
            print(f"{c.key:12} {c.meta['name']}  {c.meta['list_url']}")
        return

    if not args.build_only:
        started = time.time()
        companies = discover(args.only.split(",") if args.only else None)
        accepted = set(args.accept_large_drop.split(",")) if args.accept_large_drop else set()
        unknown = accepted - {c.key for c in companies}
        if unknown:
            ap.error("--accept-large-drop 包含未抓取的公司: " + ", ".join(sorted(unknown)))
        print(f"并行抓取: {', '.join(c.key for c in companies)} ...")
        results = crawl_all(companies, accepted)
        failed = [r["c"] for r in results if not r["ok"]]
        if failed:
            print(f"\n{len(failed)} 家失败（{', '.join(c.key for c in failed)}），{RETRY_PAUSE}s 后自动重试一次 ...")
            time.sleep(RETRY_PAUSE)
            retried = {r["c"].key: r for r in crawl_all(failed, accepted)}
            results = [retried.get(r["c"].key, r) for r in results]
        timing_table(results, time.time() - started)
        failed = [r["c"].key for r in results if not r["ok"]]
        tolerated = [k for k in failed if k in set(args.allow_failures.split(","))]
        if tolerated:
            print(f"\n⚠ 允许失败并继续: {', '.join(tolerated)}（没有它们本次的数据）")
            failed = [k for k in failed if k not in tolerated]
        if failed:
            sys.exit(f"\n抓取失败: {', '.join(failed)}（已重试过一次）。已中止，未合并。查清原因（见 .claude/runbook.md）后用 "
                     f"--only {','.join(failed)} 重抓，再 --build-only。")

    print("\n合并数据 ...")
    subprocess.run([sys.executable, str(SCRIPTS / "build.py")], check=True)
    subprocess.run([sys.executable, str(SCRIPTS / "audit.py")], check=True)


if __name__ == "__main__":
    main()
