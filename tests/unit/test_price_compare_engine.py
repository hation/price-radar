"""比价引擎单元测试:同款相似度/平台摘要/跨平台聚合。"""
import pytest

from src.services.price_compare_engine import (
    _similarity,
    _title_tokens,
    compare_keyword,
    format_compare_report,
    summarize_platform,
)


class TestTitleTokens:
    def test_tokens_strip_stopwords(self):
        tokens = _title_tokens("vivo X Fold5 全新正品 国行 包邮")
        assert "fold5" in tokens or any("fold" in t for t in tokens)
        assert "包邮" not in tokens
        assert "正品" not in tokens

    def test_tokens_lowercase(self):
        assert _title_tokens("iPhone 15 Pro") == _title_tokens("iphone 15 pro")

    def test_empty(self):
        assert _title_tokens("") == set()


class TestSimilarity:
    def test_same_config_high(self):
        # 同款同配置(成色词是停用词不算差异)→ 高相似
        assert _similarity("vivo X Fold5 16+512 全新", "vivo X Fold5 16+512 二手") >= 0.6

    def test_diff_config_rejected(self):
        # 不同配置(16+512 vs 12+256)不算同款——配置精确匹配铁律
        assert _similarity("vivo X Fold5 16+512", "vivo X Fold5 12+256") < 0.35

    def test_different_items(self):
        assert _similarity("vivo X Fold5 折叠屏手机", "戴尔显示器 27寸 4K") < 0.2

    def test_identical(self):
        assert _similarity("同款标题", "同款标题") == 1.0

    def test_empty_safe(self):
        assert _similarity("", "任意") == 0.0


class TestCompareKeyword:
    @pytest.fixture
    def seeded_db(self, monkeypatch, tmp_path):
        """临时库灌平台快照跑聚合。闲鱼走外部旧监控器库,这里断开它并把数据放 taobao/jd。"""
        monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "t.sqlite3"))
        from src.services import price_compare_engine as engine
        from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
        from src.services.price_history_service import record_market_snapshots

        # 断开外部闲鱼源(单测不依赖真实旧监控器库)
        monkeypatch.setattr(engine, "XIANYU_EXTERNAL_DB", str(tmp_path / "nonexistent.sqlite3"))
        bootstrap_sqlite_storage()
        items = {
            "taobao": [
                {"商品ID": "t1", "商品标题": "vivo X Fold5 16+512 二手", "当前售价": "¥4500",
                 "商品链接": "https://item.taobao.com/item.htm?id=1", "卖家昵称": "a"},
                {"商品ID": "t2", "商品标题": "vivo X Fold5 16+1T", "当前售价": "¥5300",
                 "商品链接": "https://item.taobao.com/item.htm?id=2", "卖家昵称": "b"},
            ],
            "jd": [
                {"商品ID": "j1", "商品标题": "vivo X Fold5 16+512 全新", "当前售价": "¥8999",
                 "商品链接": "https://item.jd.com/1.html", "卖家昵称": "vivo京东自营"},
            ],
        }
        for platform, plist in items.items():
            record_market_snapshots(
                keyword="vivo X Fold5", task_name="t", items=plist,
                run_id=f"run_{platform}", platform=platform,
            )
        return items

    def test_summarize_platform(self, seeded_db):
        s = summarize_platform("vivo X Fold5", "taobao")
        assert s.item_count == 2
        assert s.lowest_price == 4500.0
        assert "Fold5" in s.lowest_title

    def test_compare_cross_platform_gap(self, seeded_db):
        result = compare_keyword("vivo X Fold5")
        cp = result["cross_platform"]
        assert cp is not None
        assert cp["cheapest"]["platform"] == "taobao"
        assert cp["most_expensive"]["platform"] == "jd"
        assert cp["gap"] == pytest.approx(4499.0, abs=1)

    def test_same_item_candidates(self, seeded_db):
        result = compare_keyword("vivo X Fold5")
        cand = result["same_item_candidates"]
        assert cand, "jd 的 Fold5 应被识别为同款候选"
        assert cand[0]["platform"] == "jd"
        assert cand[0]["similarity"] >= 0.35

    def test_format_report(self, seeded_db):
        report = format_compare_report(compare_keyword("vivo X Fold5"))
        assert "全网比价" in report
        assert "跨平台价差" in report

    def test_empty_platforms_ok(self, seeded_db):
        result = compare_keyword("vivo X Fold5", platforms=["1688"])
        assert result["cross_platform"] is None

    def test_goofish_reads_external_db(self, monkeypatch, tmp_path):
        """闲鱼平台数据来自外部旧监控器库(只读)。"""
        import sqlite3

        ext = tmp_path / "ext.sqlite3"
        conn = sqlite3.connect(ext)
        conn.execute(
            "CREATE TABLE price_snapshots (run_id TEXT, keyword_slug TEXT, keyword TEXT, "
            "snapshot_time TEXT, item_id TEXT, title TEXT, price REAL, link TEXT, seller TEXT)"
        )
        conn.execute(
            "INSERT INTO price_snapshots VALUES ('r1', 'vivo-x-fold5', 'vivo X Fold5', "
            "'2026-09-19T06:00', 'g1', 'vivo X Fold5 12+256', 3750.0, 'https://www.goofish.com/item?id=9', '卖家')"
        )
        conn.commit()
        conn.close()
        from src.services import price_compare_engine as engine

        monkeypatch.setattr(engine, "XIANYU_EXTERNAL_DB", str(ext))
        items = engine._load_latest_run_items("vivo X Fold5", "goofish")
        assert len(items) == 1
        assert items[0]["price"] == 3750.0
