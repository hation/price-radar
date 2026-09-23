import importlib


def test_config_state_file_respects_env_override(monkeypatch, tmp_path):
    custom_state_file = str(tmp_path / "custom_state.json")
    monkeypatch.setenv("STATE_FILE", custom_state_file)

    import src.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.STATE_FILE == custom_state_file


def test_config_pcurl_to_mobile_defaults_to_true_matching_settings(monkeypatch):
    monkeypatch.delenv("PCURL_TO_MOBILE", raising=False)

    import src.config as config_module
    from src.infrastructure.config.settings import NotificationSettings

    reloaded = importlib.reload(config_module)

    assert reloaded.PCURL_TO_MOBILE is True
    assert reloaded.PCURL_TO_MOBILE == NotificationSettings().pcurl_to_mobile
