"""
Logging Configuration Utility

Provides standardized, structured logging across all bot modules.
"""

import logging
import sys
from config import settings


def setup_logger(name: str) -> logging.Logger:
    """Configure and return a structured logger instance."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(log_level)
        logger.propagate = False
        
    return logger
