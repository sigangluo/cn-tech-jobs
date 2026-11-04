"""排除招聘渠道标错、但职位名称明确显示不属于社招正式岗位的条目。"""
import re


_OUT_OF_SCOPE = re.compile(r"【(?:派遣|外包|实习)】|[（(](?:派遣|外包|实习)[）)]|^\s*\d{2,4}届校招")


def out_of_scope_title(title):
    return bool(_OUT_OF_SCOPE.search(title or ""))
