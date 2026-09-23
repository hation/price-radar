import threading

from src.infrastructure.config.env_manager import EnvManager


def test_get_value_prefers_env_file_when_key_present(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("WEBHOOK_URL=https://hooks.example.com/new\n", encoding="utf-8")
    monkeypatch.setenv("WEBHOOK_URL", "https://hooks.example.com/old")

    manager = EnvManager(str(env_file))

    assert manager.get_value("WEBHOOK_URL") == "https://hooks.example.com/new"


def test_get_value_falls_back_to_runtime_when_key_missing_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("WEBHOOK_URL", "https://hooks.example.com/runtime")

    manager = EnvManager(str(env_file))

    assert manager.get_value("WEBHOOK_URL") == "https://hooks.example.com/runtime"


def test_concurrent_writes_do_not_corrupt_env_file(tmp_path):
    env_file = tmp_path / ".env"
    manager = EnvManager(str(env_file))

    def _write(index: int):
        manager.set_value(f"KEY_{index}", f"value_{index}")

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = manager.read_env()
    for i in range(20):
        assert result[f"KEY_{i}"] == f"value_{i}"

    leftover_tmp_files = list(tmp_path.glob(".env.*.tmp"))
    assert leftover_tmp_files == []


def test_write_env_replaces_file_atomically_leaving_no_tmp_file(tmp_path):
    env_file = tmp_path / ".env"
    manager = EnvManager(str(env_file))

    assert manager.set_value("FOO", "bar") is True
    assert env_file.read_text(encoding="utf-8") == "FOO=bar\n"
    assert list(tmp_path.glob(".env.*.tmp")) == []
