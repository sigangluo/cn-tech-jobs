"""排除招聘渠道标错、但职位名称明确显示不属于社招正式岗位的条目。"""
import re


_OUT_OF_SCOPE = re.compile(r"【(?:派遣|外包|实习)】|[（(](?:派遣|外包|实习)[）)]|^\s*\d{2,4}届校招")
# 这些职位名虽含「工程师」或「开发」，职责通常是物流、产线或商务运营。
# 只用于官网未提供可靠类别、必须按职位名推断的岗位；官网类别不受影响。
_NON_RND_INFERRED = re.compile(
    r"安全工程师[（(]物流[）)]|物流信息化(?:管理|产品)工程师|"
    r"(?:高级|资深)?工艺工程师|产线开发工程师|"
    r"(?:渠道|门店|经销商|前置仓)开发(?:高级)?(?:经理|项目管理)|商业合作工程师"
)
_MANUFACTURING_PROJECT = re.compile(r"制造项目[／/]工艺|制造工程平台|产线规划")
_GENERIC_PROJECT = re.compile(r"项目管理.*工程师")


def out_of_scope_title(title):
    return bool(_OUT_OF_SCOPE.search(title or ""))


def non_rnd_inferred_job(title, description=""):
    """对缺少官网类别的岗位，排除标题或描述明确指向非研发的职位。"""
    title = title or ""
    return bool(_NON_RND_INFERRED.search(title) or
                (_GENERIC_PROJECT.search(title) and _MANUFACTURING_PROJECT.search((description or "")[:600])))
