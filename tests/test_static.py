"""静态检查：各公司的 fetch.py 和 scripts/ 里没有未定义的名字。

抓取脚本只有真正联网时才会执行到的分支，单测覆盖不到。一次改 import / 重命名函数时漏改一处（NameError），
要等到下周一抓取才暴露——这个检查在提交前就能拦住。
"""
import ast
import builtins
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_GLOBALS = {"__file__", "__name__", "__doc__"}


def undefined_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defined = set(dir(builtins)) | MODULE_GLOBALS
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            defined.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
        elif isinstance(n, ast.arg):
            defined.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            defined.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            defined.add(n.name)
    return sorted({(n.lineno, n.id) for n in ast.walk(tree)
                   if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in defined})


class NoUndefinedNames(unittest.TestCase):
    def test_company_fetchers_and_scripts(self):
        files = sorted(ROOT.glob("companies/*/fetch.py")) + sorted(ROOT.glob("scripts/**/*.py"))
        self.assertTrue(files)
        problems = [f"{p.relative_to(ROOT)}:{line}: {name}" for p in files for line, name in undefined_names(p)]
        self.assertEqual(problems, [], "未定义的名字（多半是改 import / 重命名时漏改了一处）")

    def test_checker_catches_a_missing_import(self):    # 防止检查器自己失灵：这正是腾讯那次的 bug
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.py"
            p.write_text("from os import path\n\ndef f():\n    return ensure_complete(1, 2)\n", encoding="utf-8")
            self.assertEqual([name for _, name in undefined_names(p)], ["ensure_complete"])


if __name__ == "__main__":
    unittest.main()
