"""把看板（含数据）发布到 gh-pages 分支，这个分支永远只有一个提交。

main 分支只放代码；数据每周都在变，如果也提交到 main，旧数据会一直留在 git 历史里。
这里的做法是：把 site/ 拷到临时目录，在里面新建一个只有一个提交的仓库，强制推送到 gh-pages。
旧版本就没有了，线上永远只有当前这一份。

用法:
    python3 scripts/publish.py           # 只构建发布目录并检查，不推送（安全，默认）
    python3 scripts/publish.py --push    # 确认无误后加上，强制推送 gh-pages

前提: 仓库已配置 remote（默认 origin），并在 GitHub 的 Settings → Pages 里把 Source 设为 gh-pages 分支。
提交作者取本仓库 git config 里的 user.name / user.email —— 发布到外部平台前请确认它是你想公开的身份。
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def git(*args, cwd=ROOT, check=True):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and p.returncode:
        sys.exit(f"git {' '.join(args)} 失败:\n{p.stderr.strip()}")
    return p.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="真的推送（不加就只构建和检查）")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="gh-pages")
    args = ap.parse_args()

    jobs = SITE / "data" / "jobs.json"
    if not jobs.exists():
        sys.exit("site/data/jobs.json 不存在，先运行: python3 scripts/update.py")
    name, email = git("config", "user.name", check=False), git("config", "user.email", check=False)
    if not name or not email:
        sys.exit("git 没有配置提交作者。先在本仓库里运行:\n  git config user.name <名字>\n  git config user.email <你想公开的邮箱>")
    import json
    generated = json.loads(jobs.read_text(encoding="utf-8"))["generated"]

    with tempfile.TemporaryDirectory(prefix="jobs-publish-") as tmp:
        stage = Path(tmp)
        shutil.copytree(SITE, stage, dirs_exist_ok=True)
        (stage / ".nojekyll").write_text("")            # 别让 Pages 用 Jekyll 处理这些文件
        size = sum(f.stat().st_size for f in stage.rglob("*") if f.is_file()) / 1e6
        n_files = sum(1 for f in stage.rglob("*") if f.is_file())
        print(f"发布内容: {n_files} 个文件，{size:.1f} MB（数据日期 {generated}）")
        print(f"提交作者: {name} <{email}>")

        remote_url = git("remote", "get-url", args.remote, check=False)
        if remote_url and "://" not in remote_url and "@" not in remote_url:   # 本地路径的远端：相对路径要按仓库根目录解析
            remote_url = str((ROOT / remote_url).resolve())
        if not args.push:
            print(f"\n未推送。目标: {remote_url or '（还没有配置 remote %s）' % args.remote} 的 {args.branch} 分支（强制覆盖，只留一个提交）")
            print("确认无误后运行: python3 scripts/publish.py --push")
            return
        if not remote_url:
            sys.exit(f"没有 remote「{args.remote}」，先运行: git remote add {args.remote} <仓库地址>")

        git("init", "-q", "-b", args.branch, cwd=stage)
        git("config", "user.name", name, cwd=stage)
        git("config", "user.email", email, cwd=stage)
        git("add", "-A", cwd=stage)
        git("commit", "-q", "-m", f"publish: 数据日期 {generated}", cwd=stage)
        git("push", "--force", remote_url, f"HEAD:{args.branch}", cwd=stage)
        print(f"已强制推送到 {remote_url} 的 {args.branch} 分支。Pages 通常一两分钟后更新。")


if __name__ == "__main__":
    main()
