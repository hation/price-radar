from src.services.result_storage_service import (
    load_global_blacklist_keywords_sync,
    save_global_blacklist_keywords,
)


def test_global_blacklist_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert load_global_blacklist_keywords_sync() == []

    import asyncio

    saved = asyncio.run(save_global_blacklist_keywords(["靠谱", "假货", ""]))
    assert saved == ["靠谱", "假货"]

    assert load_global_blacklist_keywords_sync() == ["靠谱", "假货"]
