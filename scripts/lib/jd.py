"""把官网合在一个字段里的职位描述和任职要求拆开。"""
import re


_REQUIREMENT_HEADING = re.compile(
    r"(?im)^[ \t]*(?:[一二三四五六七八九十\d]+[、.．)）][ \t]*|[.．])?"
    r"(?:\*\*|【|\[)?[ \t]*"
    r"(?:任职要求|任职资格|岗位要求|职位要求|工作要求|基本要求|"
    r"Job Requirements|Basic Requirements|Qualifications(?:\s*&\s*Requirements)?|Required Qualifications)"
    r"[ \t]*(?:\*\*|】|\])?[ \t]*(?:[:：][ \t]*|\r?\n|$)"
)


def split_jd(text):
    """找到独立的要求标题；没有明确标题时保留原文，不猜测正文边界。"""
    text = (text or "").strip()
    m = _REQUIREMENT_HEADING.search(text)
    if not m:
        return text, ""
    return text[:m.start()].strip(), text[m.end():].strip()
