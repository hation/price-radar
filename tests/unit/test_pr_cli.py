import json

import pytest

from pr import _parse_args, main, _render_table, _print_json

def test_parse_crawl():
    args = _parse_args(["--crawl", "三星/SK 64G5600", "--pages", "2"])
    assert args.crawl == "三星/SK 64G5600"
    assert args.pages == 2
    assert args.platform == "goofish"
    assert args.mode == "keyword"

def test_parse_trend():
    args = _parse_args(["--trend", "三星/SK 64G5600", "--json"])
    assert args.trend == "三星/SK 64G5600"
    assert args.json is True

def test_parse_requires_one_action():
    with pytest.raises(SystemExit):
        _parse_args([])

def test_render_table_aligns_headers(capsys):
    _render_table(["ID", "名称"], [[1, "三星/SK"], [10, "很长很长的名字"]])
    out = capsys.readouterr().out
    assert "ID" in out and "名称" in out
    assert "三星/SK" in out and "很长很长的名字" in out

def test_render_table_empty():
    assert _render_table(["A", "B"], []) is None  # 打印 "(无数据)"，不抛异常

def test_print_json(capsys):
    _print_json({"a": 1, "中文": "值"})
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == {"a": 1, "中文": "值"}
