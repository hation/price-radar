import pytest

from pr import _parse_args, main

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
