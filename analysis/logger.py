import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger(log_path=None):
    if log_path is None:
        base = os.path.dirname(__file__)
        log_path = os.path.join(base, 'analysis.log')
    logger = logging.getLogger('analysis')
    logger.setLevel(logging.DEBUG)
    # Ensure we have a handler that writes to the requested log_path.
    # If existing handler(s) point to a different file (e.g. after restarts), replace them.
    need_new_handler = True
    for h in list(logger.handlers):
        try:
            existing_path = getattr(h, 'baseFilename', None)
        except Exception:
            existing_path = None
        if existing_path and os.path.abspath(existing_path) == os.path.abspath(log_path):
            need_new_handler = False
        else:
            # remove handlers that point to a different file to avoid silent mismatches
            logger.removeHandler(h)

    if need_new_handler:
        handler = RotatingFileHandler(log_path, maxBytes=1024*1024, backupCount=3, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    # avoid propagation to root logger to reduce duplicate messages
    logger.propagate = False
    return logger
