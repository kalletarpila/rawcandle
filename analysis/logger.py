import logging
import os
from logging.handlers import RotatingFileHandler


def _is_analysis_log_enabled() -> bool:
    value = os.getenv("ENABLE_ANALYSIS_LOG", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def setup_logger(log_path=None):
    if log_path is None:
        base = os.path.dirname(__file__)
        log_path = os.path.join(base, "analysis.log")
    logger = logging.getLogger("analysis")
    logger.setLevel(logging.DEBUG)
    file_logging_enabled = _is_analysis_log_enabled()
    target_path = os.path.abspath(log_path)
    need_file_handler = file_logging_enabled
    has_null_handler = False

    for handler in list(logger.handlers):
        existing_path = getattr(handler, "baseFilename", None)
        is_file_handler = existing_path is not None
        if is_file_handler:
            if (
                file_logging_enabled
                and os.path.abspath(existing_path) == target_path
                and need_file_handler
            ):
                need_file_handler = False
                continue
            logger.removeHandler(handler)
            handler.close()
            continue
        if isinstance(handler, logging.NullHandler):
            if file_logging_enabled:
                logger.removeHandler(handler)
            else:
                has_null_handler = True

    if file_logging_enabled and need_file_handler:
        handler = RotatingFileHandler(
            log_path, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
        formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    elif not file_logging_enabled and not has_null_handler:
        logger.addHandler(logging.NullHandler())

    # avoid propagation to root logger to reduce duplicate messages
    logger.propagate = False
    return logger
