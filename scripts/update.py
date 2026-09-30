"""每周更新：重新抓取各公司职位，再合并成看板数据。

用法:
    python3 scripts/update.py                      # 抓取 companies/ 下所有公司 + 合并
    python3 scripts/update.py --only netease,didi  # 只重抓指定公司
    python3 scripts/update.py --build-only         # 不抓取，只用现有 data/*/*.csv 重新合并
    python3 scripts/update.py --list               # 列出当前有哪些公司

公司由 companies/ 下的目录自动发现，新增公司不用改这里。各家互不依赖、访问不同站点，所以并行跑；
最慢的一家约 6 分钟。任何一家失败都会中止，不会拿旧 CSV 混进新数据。
"""
import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)   # 管道 / 重定向时也按行输出，避免和子进程输出顺序错乱
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from lib.companies import discover


def run(c):
    started = time.time()
    p = subprocess.run([sys.executable, "-W", "ignore", str(SCRIPTS / "fetch_company.py"), c.key],
                       capture_output=True, text=True)
    lines = [ln for ln in p.stdout.strip().splitlines() if ln]
    # 只截取最后几行，但 ⚠ 警告不能被截掉
    tail = [ln for ln in lines[:-4] if ln.startswith("⚠")] + lines[-4:]
    # 退出码为 0 也要确认 CSV 真的被刷新了
    stale = [f.name for f in c.data_dir.glob("*.csv") if f.stat().st_mtime < started] if c.data_dir.exists() else ["（没有产出任何 CSV）"]
    ok = p.returncode == 0 and not stale and any(c.data_dir.glob("*.csv"))
    return c, ok, tail, p.stderr.strip().splitlines()[-3:], stale, time.time() - started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只抓这些公司（key），逗号分隔")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for c in discover():
            print(f"{c.key:12} {c.meta['name']}  {c.meta['list_url']}")
        return

    if not args.build_only:
        companies = discover(args.only.split(",") if args.only else None)
        print(f"并行抓取: {', '.join(c.key for c in companies)} ...")
        failed = []
        with ThreadPoolExecutor(max_workers=len(companies)) as pool:
            for c, ok, tail, err, stale, secs in pool.map(run, companies):
                print(f"\n[{c.key}] {'完成' if ok else '失败'}（{secs:.0f}s）")
                for ln in tail:
                    print("   ", ln)
                if not ok:
                    failed.append(c.key)
                    for ln in err:
                        print("    !", ln)
                    if stale:
                        print("    ! 这些 CSV 没有被更新:", ", ".join(stale))
        if failed:
            sys.exit(f"\n抓取失败: {', '.join(failed)}。已中止，未合并。修好后可用 --only {','.join(failed)} 重抓，再 --build-only。")

    print("\n合并数据 ...")
    subprocess.run([sys.executable, str(SCRIPTS / "build.py")], check=True)


if __name__ == "__main__":
    main()
