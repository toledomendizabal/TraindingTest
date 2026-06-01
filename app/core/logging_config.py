"""Logging configuration using loguru."""
import os
import sys
from loguru import logger
from app.core.config import settings


def setup_logging():
    """Configure loguru logging with separate files for different modules."""
    logs_dir = settings.LOGS_DIR
    os.makedirs(logs_dir, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console output
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True
    )

    # System log
    logger.add(
        os.path.join(logs_dir, "system_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        compression="zip"
    )

    # Signals log
    logger.add(
        os.path.join(logs_dir, "signals_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        rotation="1 day",
        retention="30 days",
        filter=lambda record: "signals" in record["extra"].get("module", "")
    )

    # Monitoring log
    logger.add(
        os.path.join(logs_dir, "monitoring_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        rotation="1 day",
        retention="30 days",
        filter=lambda record: "monitoring" in record["extra"].get("module", "")
    )

    # Error log
    logger.add(
        os.path.join(logs_dir, "errors_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="1 day",
        retention="60 days"
    )

    return logger


app_logger = setup_logging()
