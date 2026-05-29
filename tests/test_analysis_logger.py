import logging

from analysis.logger import setup_logger


def _reset_analysis_logger():
    logger = logging.getLogger("analysis")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def test_setup_logger_defaults_to_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("ENABLE_ANALYSIS_LOG", raising=False)
    _reset_analysis_logger()
    log_path = tmp_path / "analysis.log"

    logger = setup_logger(log_path=str(log_path))
    logger.info("default-disabled")

    assert not log_path.exists()
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)
    assert not any(hasattr(handler, "baseFilename") for handler in logger.handlers)


def test_setup_logger_enables_file_logging(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_ANALYSIS_LOG", "true")
    _reset_analysis_logger()
    log_path = tmp_path / "analysis.log"

    logger = setup_logger(log_path=str(log_path))
    logger.info("enabled-log-line")

    assert log_path.exists()
    assert "enabled-log-line" in log_path.read_text(encoding="utf-8")
    assert sum(hasattr(handler, "baseFilename") for handler in logger.handlers) == 1


def test_setup_logger_repeated_initialization_does_not_duplicate_handlers(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ENABLE_ANALYSIS_LOG", "1")
    _reset_analysis_logger()
    log_path = tmp_path / "analysis.log"

    logger = setup_logger(log_path=str(log_path))
    logger = setup_logger(log_path=str(log_path))
    logger.info("no-duplicate")

    assert sum(hasattr(handler, "baseFilename") for handler in logger.handlers) == 1
