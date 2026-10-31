"""导出服务测试：目录构建 + 分平台/合并 CSV + JSONL。"""
import json
import os

from src.services.search_output_service import build_search_output_dir, export_search_results

RECORDS = {
    "goofish": [
        {"商品信息": {"商品标题": "闲鱼货", "当前售价": "¥100", "商品链接": "http://x", "商品ID": "1",
                     "卖家昵称": "卖家A", "发货地区": "广东", "发布时间": "2026-10-31"},
         "爬取时间": "2026-10-31T10:00:00", "platform": "goofish"},
    ],
    "jd": [
        {"商品信息": {"商品标题": "京东货", "当前售价": "¥200", "商品链接": "http://j", "商品ID": "2",
                     "卖家昵称": "", "发货地区": "", "发布时间": ""},
         "爬取时间": "2026-10-31T10:00:00", "platform": "jd"},
    ],
}


def test_build_search_output_dir_format(tmp_path, monkeypatch):
    class FakeNow:
        def strftime(self, fmt):
            return "202610311030"
    monkeypatch.setattr(
        "src.services.search_output_service.datetime",
        type("DT", (), {"now": lambda: FakeNow()}),
    )
    out = build_search_output_dir("希捷")
    assert out == os.path.join("output", "希捷_202610311030")


def test_export_search_results_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out_dir = export_search_results("希捷", RECORDS)
    assert os.path.isdir(out_dir)
    files = os.listdir(out_dir)
    assert "希捷_goofish.csv" in files
    assert "希捷_jd.csv" in files
    assert "希捷_merged.csv" in files
    assert "希捷_merged.jsonl" in files

    with open(os.path.join(out_dir, "希捷_merged.csv"), encoding="utf-8-sig") as f:
        head = f.readline()
    assert "平台" in head or "platform" in head

    with open(os.path.join(out_dir, "希捷_merged.jsonl"), encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert {line["platform"] for line in lines} == {"goofish", "jd"}
