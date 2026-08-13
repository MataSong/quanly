"""
密码强度规则 — 前后端一致的最终防线。

规则(流行标准):
  - 长度 >= 8
  - 至少满足以下四类中的 3 类:
      大写字母 (A-Z)
      小写字母 (a-z)
      数字 (0-9)
      特殊字符 (!@#$%^&*… 以及任何非字母数字字符)

错误使用结构化 code,便于前端 i18n。
"""

import re

from rest_framework.exceptions import ValidationError

_CATEGORY_PATTERNS = [
    re.compile(r"[A-Z]"),   # 大写
    re.compile(r"[a-z]"),   # 小写
    re.compile(r"[0-9]"),   # 数字
    re.compile(r"[^A-Za-z0-9]"),  # 特殊字符
]

PASSWORD_MIN_LENGTH = 8
PASSWORD_MIN_CATEGORIES = 3


def validate_password_strength(password: str) -> tuple[bool, str]:
    """检查密码是否符合强度规则。

    Returns:
        (True, "") 如果通过。
        (False, message_str) 如果不通过 — message 可直接展示给用户。

    不会抛异常;调用方决定是否调用 raise_if_weak()。
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return (
            False,
            f"密码长度至少 {PASSWORD_MIN_LENGTH} 位,且须包含大写、小写、数字、特殊字符中的 3 类。",
        )
    categories_met = sum(1 for p in _CATEGORY_PATTERNS if p.search(password))
    if categories_met < PASSWORD_MIN_CATEGORIES:
        return (
            False,
            f"密码须包含大写、小写、数字、特殊字符中的至少 {PASSWORD_MIN_CATEGORIES} 类。",
        )
    return (True, "")


def raise_if_weak(password: str) -> None:
    """若密码不符合强度规则,抛 DRF ValidationError(结构化 code)。"""
    ok, message = validate_password_strength(password)
    if not ok:
        raise ValidationError(
            {"code": "weak_password", "message": message},
            code="weak_password",
        )
