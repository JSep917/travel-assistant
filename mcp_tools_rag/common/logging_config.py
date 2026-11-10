import logging
import os
import sys


def setup_logging() -> None:
    """应用入口调用一次，统一日志格式和级别。"""
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    # 降低第三方库噪声
    for name in (
        "httpx",
        "httpcore",
        "pymilvus",
        "urllib3",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
