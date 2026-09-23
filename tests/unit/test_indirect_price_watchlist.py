"""间接价服务 watchlist 增删查测试(纯本地 JSON,不触网)。"""
import pytest

from src.services import indirect_price_service as svc


@pytest.fixture(autouse=True)
def _tmp_watchlist(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(svc, "WATCHLIST_PATH", str(tmp_path / "watchlist.json"))


def test_add_dedup_and_update():
    svc.watch_add("https://item.jd.com/1.html", 100, "A")
    svc.watch_add("https://item.jd.com/1.html", 80, "B")  # 同 URL 覆盖
    items = svc.watch_list()
    assert len(items) == 1
    assert items[0]["target_price"] == 80
    assert items[0]["note"] == "B"


def test_remove():
    svc.watch_add("https://item.jd.com/1.html", 100)
    svc.watch_add("https://item.pinduoduo.com/2.html", 50)
    assert svc.watch_remove("https://item.jd.com/1.html") == 1
    assert len(svc.watch_list()) == 1
    assert svc.watch_list()[0]["url"].startswith("https://item.pinduoduo")
