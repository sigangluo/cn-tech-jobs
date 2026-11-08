"""把看板（含数据）发布到 gh-pages 分支，这个分支永远只有一个提交。

main 分支放代码和质量报告；完整职位数据每周都在变，如果也提交到 main，旧数据会一直留在 git 历史里。
这里的做法是：把 site/ 拷到临时目录，在里面新建一个只有一个提交的仓库，强制推送到 gh-pages。
旧版本就没有了，线上永远只有当前这一份。

用法:
    python3 scripts/publish.py                        # 只构建发布目录并检查，不推送（安全，默认）
    python3 scripts/publish.py --push                 # 确认无误后加上，强制推送 gh-pages
    python3 scripts/publish.py --archive .backups/X   # 回滚：发布某个本地存档（见下）；同样要加 --push 才会推送

回滚：gh-pages 只有一个提交、data/ 又不进 git，推送之后旧版本在线上就没有了。所以每次 --push 前都会把要发布的内容存成
.backups/site-<数据日期>-<时间>.tar.gz（本地，被 .gitignore 忽略，只保留最近 KEEP_BACKUPS 份）。发布出问题时用 --archive 重新发布上一份。

前提: 仓库已配置 remote（默认 origin），并在 GitHub 的 Settings → Pages 里把 Source 设为 gh-pages 分支。
提交作者取本仓库 git config 里的 user.name / user.email —— 发布到外部平台前请确认它是你想公开的身份。
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
BACKUPS = ROOT / ".backups"
KEEP_BACKUPS = 3


def safe_extract(archive, dest):
    """解包存档；拒绝指向目录之外的路径（tarfile 的 filter 参数要 Python 3.12，这里手动校验以兼容老版本）。"""
    with tarfile.open(archive) as tar:
        for m in tar.getmembers():
            if not (dest / m.name).resolve().is_relative_to(dest.resolve()) or m.issym() or m.islnk():
                sys.exit(f"存档里有不安全的路径: {m.name}")
        tar.extractall(dest)


def save_backup(stage, generated):
    """把即将发布的内容存档，只留最近 KEEP_BACKUPS 份。返回存档路径。"""
    BACKUPS.mkdir(exist_ok=True)
    path = BACKUPS / f"site-{generated}-{datetime.now():%H%M%S}.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        tar.add(stage, arcname=".")
    for old in sorted(BACKUPS.glob("site-*.tar.gz"))[:-KEEP_BACKUPS]:
        old.unlink()
    return path


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
    ap.add_argument("--archive", help="发布这个本地存档（回滚用），而不是当前的 site/")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="jobs-archive-") as unpacked:
        source = SITE
        if args.archive:
            safe_extract(args.archive, Path(unpacked))
            source = Path(unpacked)
        publish(args, source)


def publish(args, source):
    jobs = source / "data" / "jobs.json"
    if not jobs.exists():
        sys.exit(f"{jobs} 不存在，先运行: python3 scripts/update.py")
    name, email = git("config", "user.name", check=False), git("config", "user.email", check=False)
    if not name or not email:
        sys.exit("git 没有配置提交作者。先在本仓库里运行:\n  git config user.name <名字>\n  git config user.email <你想公开的邮箱>")
    generated = json.loads(jobs.read_text(encoding="utf-8"))["generated"]
    quality = source / "data" / "quality.json"
    if not quality.exists() or json.loads(quality.read_text(encoding="utf-8")).get("jobs_sha256") != hashlib.sha256(jobs.read_bytes()).hexdigest():
        sys.exit("数据质量报告缺失或与当前 jobs.json 不匹配；先运行: python3 scripts/audit.py")

    with tempfile.TemporaryDirectory(prefix="jobs-publish-") as tmp:
        stage = Path(tmp)
        shutil.copytree(source, stage, dirs_exist_ok=True)
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

        print(f"本地存档（回滚用）: {save_backup(stage, generated)}" if not args.archive else "回滚发布：使用已有存档，不再新建存档")
        git("init", "-q", "-b", args.branch, cwd=stage)
        git("config", "user.name", name, cwd=stage)
        git("config", "user.email", email, cwd=stage)
        git("add", "-A", cwd=stage)
        git("commit", "-q", "-m", f"publish: 数据日期 {generated}", cwd=stage)
        git("push", "--force", remote_url, f"HEAD:{args.branch}", cwd=stage)
        print(f"已强制推送到 {remote_url} 的 {args.branch} 分支。Pages 通常一两分钟后更新。")


if __name__ == "__main__":
    main()
