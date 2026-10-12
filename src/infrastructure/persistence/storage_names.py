"""
SQLite 持久化相关的统一命名规则。
"""
from __future__ import annotations

import re

DEFAULT_DATABASE_PATH = "data/app.sqlite3"
RESULT_FILE_SUFFIX = "_full_data.jsonl"

# 会破坏 URL 路由(/)或文件路径安全性的字符，统一替换为下划线；中文等可读字符保留。
_ILLEGAL_FILENAME_CHARS = re.compile(r"[/\\:*?\"<>|\s]+")


def build_result_filename(keyword: str) -> str:
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", str(keyword or ""))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return f"{cleaned or 'task'}{RESULT_FILE_SUFFIX}"


def normalize_keyword_from_filename(filename: str) -> str:
    return str(filename or "").replace(RESULT_FILE_SUFFIX, "")


def normalize_keyword_slug(keyword: str) -> str:
    text = "".join(
        char for char in str(keyword or "").lower().replace(" ", "_")
        if char.isalnum() or char in "_-"
    ).rstrip("_")
    return text or "unknown"
