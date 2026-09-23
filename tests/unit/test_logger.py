import logging

from src.infrastructure.logging import logger as logger_module


def test_setup_logging_is_idempotent(monkeypatch):
    monkeypatch.setattr(logger_module, "_configured", False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    try:
        root.handlers = []
        logger_module.setup_logging(level="DEBUG")
        logger_module.setup_logging(level="ERROR")

        assert len(root.handlers) == 1
        assert root.level == logging.DEBUG
    finally:
        root.handlers = original_handlers


def test_get_logger_returns_named_logger():
    logger = logger_module.get_logger("my.module")
    assert logger.name == "my.module"
