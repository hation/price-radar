"""验证 taobao 模块正常导入且不再定义本地 _human_move_to(已迁移)。"""
import src.platforms.taobao as tb


def test_taobao_imports_and_uses_human_module():
    assert not hasattr(tb, "_human_move_to")
    assert hasattr(tb, "scrape_taobao")


def test_human_utils_reexported():
    from src.platforms._human import human_move_to
    assert callable(human_move_to)
