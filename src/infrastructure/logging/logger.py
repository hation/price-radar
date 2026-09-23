"""
统一日志配置。

此前 src/services、src/api/routes 下全部用 print() 输出诊断信息，没有日志级别、
没有结构化格式，无法按级别过滤。这里提供一个轻量的 setup_logging()/get_logger()，
应用启动时调用一次 setup_logging()，其余地方用 get_logger(__name__) 取 logger。

注意：爬虫子进程（spider_v2.py / src/scraper.py / src/ai_handler.py 等）保持原有
print() 风格不变——它们的输出格式已经被多个测试通过 capsys 断言，且是面向"人在盯着
任务日志文件看"的场景，混用两种风格没有必要。
"""
from __future__ import annotations

import logging
import os
import sys

_configured = False


def setup_logging(level: str | None = None) -> None:
    """配置根 logger，只在应用启动时调用一次；重复调用是no-op。"""
    global _configured
    if _configured:
        return
    _configured = True

    resolved_level_name = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    resolved_level = getattr(logging, resolved_level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(resolved_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
