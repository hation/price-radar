"""搜索结果导出服务：output/关键词_时间戳/ 目录下写分平台 CSV、合并 CSV 与 JSONL。"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime

COLUMNS = [
    "标题", "价格", "链接", "商品ID", "卖家", "地区", "发布时间", "爬取时间", "platform",
]
_ILLEGAL_DIR_CHARS = re.compile(r"[/\\:*?\"<>|\s]+")


def _sanitize_dir_part(keyword: str) -> str:
    cleaned = _ILLEGAL_DIR_CHARS.sub("_", str(keyword or ""))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "task"


def build_search_output_dir(keyword: str, now: datetime | None = None) -> str:
    """生成 output/{关键词}_{yyyymmddhhmm} 目录路径。"""
    ts = (now or datetime.now()).strftime("%Y%m%d%H%M")
    return os.path.join("output", f"{_sanitize_dir_part(keyword)}_{ts}")


def _extract_row(record: dict) -> dict:
    item = record.get("商品信息", {}) or {}
    return {
        "标题": item.get("商品标题", ""),
        "价格": item.get("当前售价", ""),
        "链接": item.get("商品链接", ""),
        "商品ID": item.get("商品ID", ""),
        "卖家": item.get("卖家昵称", ""),
        "地区": item.get("发货地区", ""),
        "发布时间": item.get("发布时间", ""),
        "爬取时间": record.get("爬取时间", ""),
        "platform": record.get("platform", ""),
    }


def export_search_results(keyword: str, items_by_platform: dict) -> str:
    """导出搜索结果到 output 目录,返回目录路径。"""
    out_dir = build_search_output_dir(keyword)
    os.makedirs(out_dir, exist_ok=True)
    merged_rows = []
    base = _sanitize_dir_part(keyword)
    for platform, records in items_by_platform.items():
        rows = [_extract_row(r) for r in records]
        if not rows:
            continue
        merged_rows.extend(rows)
        with open(
            os.path.join(out_dir, f"{base}_{platform}.csv"),
            "w", newline="", encoding="utf-8-sig",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS[:-1], extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    if merged_rows:
        with open(
            os.path.join(out_dir, f"{base}_merged.csv"),
            "w", newline="", encoding="utf-8-sig",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(merged_rows)
        with open(
            os.path.join(out_dir, f"{base}_merged.jsonl"),
            "w", encoding="utf-8",
        ) as f:
            for row in merged_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out_dir
