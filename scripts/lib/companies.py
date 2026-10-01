"""自动发现 companies/ 下的公司：每个含 fetch.py 的子目录就是一家公司，目录名就是它的 key。

以 _ 或 . 开头的目录（如 _template）会被跳过。新增公司不需要改任何其他文件。
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
COMPANIES_DIR = ROOT / "companies"
DATA_DIR = ROOT / "data"
REQUIRED_META = ("name", "list_url", "categories", "date_label")


def _load(d):
    key = d.name
    spec = importlib.util.spec_from_file_location(f"company_{key}", d / "fetch.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise RuntimeError(f"companies/{key}/fetch.py 导入失败: {e}") from e
    meta = getattr(mod, "META", None)
    if not isinstance(meta, dict) or not callable(getattr(mod, "fetch", None)):
        raise RuntimeError(f"companies/{key}/fetch.py 必须定义 META（dict）和 fetch()")
    missing = [k for k in REQUIRED_META if not meta.get(k)]
    if missing:
        raise RuntimeError(f"companies/{key}/fetch.py 的 META 缺少: {missing}")
    if meta["date_label"] not in ("发布时间", "更新时间"):
        raise RuntimeError(f"companies/{key} 的 META['date_label'] 只能是「发布时间」或「更新时间」")
    facets = meta.get("facets", [])
    if not isinstance(facets, (list, tuple)) or not all(
            isinstance(f, (list, tuple)) and len(f) in (2, 3) and all(isinstance(x, str) and x for x in f)
            and (len(f) == 2 or f[2] == "multi") for f in facets):
        raise RuntimeError(f"companies/{key} 的 META['facets'] 必须是 [(显示名, 数据来源[, 'multi']), ...]，来源是 'category'、'subcategory'、'dept' 或 extra 里的列名；"
                           f"一个职位可以有多个取值的（如职位标签）加第三项 'multi'，extra 里用「、」分隔")
    meta = {"order": 100, "note": "", **meta, "facets": [tuple(f) for f in facets]}
    return SimpleNamespace(key=key, dir=d, module=mod, meta=meta, data_dir=DATA_DIR / key)


def discover(only=None):
    """返回所有公司，按 META['order'] 再按 key 排序。only 是 key 列表，用来只取其中几家。"""
    found = [_load(d) for d in sorted(COMPANIES_DIR.iterdir())
             if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "fetch.py").exists()]
    if only is not None:
        unknown = [k for k in only if k not in {c.key for c in found}]
        if unknown:
            raise SystemExit(f"未知公司: {unknown}，可选: {[c.key for c in found]}")
        found = [c for c in found if c.key in only]
    return sorted(found, key=lambda c: (c.meta["order"], c.key))
