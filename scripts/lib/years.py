"""工作年限识别：从任职要求文本里找出"必须"和"优先"两种年限。

所有公司共用这一份规则，改规则只改这里。
"""
import re

CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_NUM = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十]{1,3})"
_YEARS_RE = re.compile(
    rf"(?P<a>{_NUM})\s*(?P<plus>[+＋])?\s*(?:[-~～—–至到]\s*(?P<b>{_NUM})\s*)?年(?P<suffix>\s*(?:及以上|以上|以内|以下|左右|\+)?)"
)
_EXP_WORDS = re.compile(r"经验|经历|工作|从业|开发|研发|实践|背景")


def _to_num(s):
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        v = float(s)
        return int(v) if v == int(v) else v
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN[s[1:]]
    if s.endswith("十"):
        return CN[s[:-1]] * 10
    if len(s) == 2 and s[1] == "十":
        return CN[s[0]] * 10
    if len(s) == 3 and s[1] == "十":
        return CN[s[0]] * 10 + CN[s[2]]
    return CN[s] if len(s) == 1 else None


# 分节标题的冒号后面是换行或直接跟编号（「具备以下条件者优先：\n1、…」）；行中间的「…经验者优先：xxx」不是标题，后面的硬性要求不能被吞掉
_HEADING_END = r"[:：][ \t]*(?:\n|$|(?=1[、.．]))"
# "加分项/优先条件"这类分节标题：标题之后的内容都算"优先"而非"必须"
_PREF_SECTION = re.compile(
    r"(?m)^[ \t]*(?:\d+[、.)）]\s*)?(?:以下[为是])?[【\[]?(?:加分项|加分条件|优先条件|优先项|加分)[】\]]?[ \t]*(?:[:：]|$)"
    rf"|(?:以下|如下)[^\n:：]{{0,12}}优先(?:考虑)?{_HEADING_END}"
    rf"|(?:者|之一)优先(?:考虑)?{_HEADING_END}|优先考虑{_HEADING_END}"
)
_PREF_CLAUSE = re.compile(r"优先|为佳|更佳|尤佳|者佳|加分")  # 年限所在分句里出现这些词，说明只是加分项
_CLAUSE_SEPS = "\n。；;，,、（）()"  # 分句分隔符：括号里的"优先"只修饰括号内的内容
_NO_LIMIT = re.compile(r"(?:工作)?经验(?:要求)?不限(?!于)|不限(?:工作)?(?:经验|年限)|年限不限")


# 条目编号和后面的数字连在一起：「2.3年以上iOS开发经验」是第 2 条、3 年以上，不是 2.3 年；「1.1-3年」是第 1 条、1-3 年。
# 只有上下文里还有相邻的编号（k±1）时才拆，所以「具备1.5年以上经验」这种真正的小数不受影响。
_ITEM_MARK = re.compile(r"(?m)(?:^|(?<=[\s；;。]))(\d{1,2})[.．、)）]")
_ITEM_GLUED = re.compile(r"(?m)(?:^|(?<=[；;。]))([ \t]*)(\d{1,2})[.．](?=\d)")


def _strip_item_numbers(text):
    nums = {int(m.group(1)) for m in _ITEM_MARK.finditer(text)}

    def drop(m):
        k = int(m.group(2))
        return m.group(1) if (k + 1 in nums or k - 1 in nums) else m.group(0)
    return _ITEM_GLUED.sub(drop, text)


def resolve_years(official, text):
    """合并官网的结构化年限字段和任职要求文本，返回 (必须年限, 优先年限, 来源)。

    任职要求里明确写了年限就以文字为准：官网字段通常是粗档位，或者干脆没填（填了"不限"，文字里却要求 3 年以上），
    候选人读到的是文字。文字没写年限时才用官网字段里的具体年限。
    "不限"只认任职要求里明确写了的：官网字段填「不限」但任职要求没提，记「未提及」（官网字段常是没填的默认值）。
    来源是 "任职要求" / "官网字段" / ""（都没有）。
    """
    req, pref = parse_years(text)
    official = (official or "").strip()
    if req not in ("未提及", "不限"):
        return req, pref, "任职要求"
    if official not in ("", "未提及", "不限"):
        return official, pref, "官网字段"
    return req, pref, "任职要求" if req == "不限" else ""


def parse_years(text):
    """从任职要求里识别 (必须的工作年限, 优先的工作年限)。

    必须年限：'3年以上' / '3-5年' / '2年'；没有硬性年限时，明确写了不限的返回 '不限'，否则 '未提及'。
    优先年限：只出现在"优先/加分项"里的年限，没有则为空字符串。
    """
    if not isinstance(text, str):
        return "未提及", ""
    text = _strip_item_numbers(text)
    m0 = _PREF_SECTION.search(text)
    pref_start = m0.start() if m0 else len(text)
    required, preferred = [], []
    for m in _YEARS_RE.finditer(text):
        a = _to_num(m.group("a"))
        b = _to_num(m.group("b")) if m.group("b") else None
        if a is None or (m.group("b") and b is None) or a >= 30 or (b or 0) >= 40:
            continue  # 排除 2026年 这类年份、"30年"之类的异常值
        after = text[m.end():m.end() + 6]
        before = text[max(0, m.start() - 2):m.start()]
        if "毕业" in after or after.startswith(("届", "内毕", "级")) or re.search(r"[近前]$|过去$", before):
            continue  # 排除 "2年内毕业" "近3年" 这类非工作年限
        suffix = m.group("suffix").strip().replace("及以上", "以上").replace("+", "以上") or ("以上" if m.group("plus") else "")   # 「5+年」「5年+」都是 5 年以上
        s = (f"{a}-{b}年" if b else f"{a}年") + suffix
        # 上下文：所在句子里是否出现"经验/工作"等词，用来优先选真正的工作年限
        ls = max(text.rfind(c, 0, m.start()) for c in "\n。；;") + 1
        rs = [i for i in (text.find(c, m.end()) for c in "\n。；;") if i != -1]
        sentence = text[ls:min(rs) if rs else len(text)]
        # 分句：再按逗号切开，判断"优先"是否修饰的就是这个年限
        cl = max(text.rfind(c, 0, m.start()) for c in _CLAUSE_SEPS) + 1
        cr = [i for i in (text.find(c, m.end()) for c in _CLAUSE_SEPS) if i != -1]
        clause = text[cl:min(cr) if cr else len(text)]
        is_pref = m.start() >= pref_start or bool(_PREF_CLAUSE.search(clause))
        (preferred if is_pref else required).append((bool(_EXP_WORDS.search(sentence)), s))

    def pick(cands):  # 取第一个带工作语境的；没有则取第一个
        return next((v for ctx, v in cands if ctx), cands[0][1] if cands else "")

    req = pick(required)
    if not req:
        req = "不限" if _NO_LIMIT.search(text) else "未提及"
    return req, pick(preferred)
