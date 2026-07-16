"""简单日志工具。"""

import logging
import sys

_configured = {}


def setup_logger(name: str) -> logging.Logger:
    if name in _configured:
        return _configured[name]
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    _configured[name] = logger
    return logger
