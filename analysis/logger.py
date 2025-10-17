import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger(log_path=None):
    if log_path is None:
        base = os.path.dirname(__file__)
        log_path = os.path.join(base, 'analysis.log')
    logger = logging.getLogger('analysis')
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = RotatingFileHandler(log_path, maxBytes=1024*1024, backupCount=3, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
