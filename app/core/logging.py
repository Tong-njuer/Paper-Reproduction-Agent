import sys
from pathlib import Path

from loguru import logger

from app.core.config import get_config


def setup_logging() -> None:
    config = get_config().log

    logger.remove()

    logger.add(
        sys.stderr,
        level=config.level,
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[module]: <16}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    log_dir = Path(config.dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "agent_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[module]: <16} | {message}",
        rotation="00:00",
        retention=config.retention,
        encoding="utf-8",
    )


def get_logger(module: str = "agent"):
    return logger.bind(module=module)
