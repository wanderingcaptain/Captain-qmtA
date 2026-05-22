"""
日志工具 — 统一 logger 配置。
提供 setup_logger（根 logger 初始化）和 get_logger（子模块 logger 获取）。

设计原则：
  - 仅在根 logger 上附加 handler，子 logger 通过继承传播日志。
  - 防止重复调用 setup_logger 时 handler 叠加导致日志重复输出。
  - 使用 RotatingFileHandler 防止日志文件无限增长。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

from config import SystemConfig

# 根 logger 名称
ROOT_LOGGER_NAME = "qmt_ths"

# 是否已初始化（防止重复设置）
_initialized: bool = False


def setup_logger(name: str = ROOT_LOGGER_NAME) -> logging.Logger:
    """
    初始化根 logger，配置文件和控制台两个 handler。
    重复调用是安全的（幂等）。

    参数：
        name: logger 名称，默认为根 logger "qmt_ths"。
    返回：
        配置好的 Logger 实例。
    """
    global _initialized
    logger = logging.getLogger(name)

    # 已有 handler 则直接返回，防止重复添加
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, SystemConfig.LOG_LEVEL.upper(), logging.DEBUG))
    # 不向上传播（避免 root logger 重复输出）
    logger.propagate = False

    log_dir = SystemConfig.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y%m%d')}.log")

    # 文件 handler：全量 DEBUG 级别，按 10MB 轮转，保留 7 个备份
    fh = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=7,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))

    # 控制台 handler：INFO 级别，精简格式
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    ))

    logger.addHandler(fh)
    logger.addHandler(ch)
    _initialized = True
    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    获取模块子 logger。
    子 logger 自动继承根 logger 的 handler（无需重复配置）。
    若根 logger 尚未初始化，则先调用 setup_logger()。

    参数：
        module_name: 模块标识，如 "core.intraday"、"strategies.screener"。
    返回：
        logging.Logger 实例，名称为 "qmt_ths.<module_name>"。

    用法：
        logger = get_logger("core.intraday")
        logger.info("引擎启动")
    """
    if not _initialized:
        setup_logger()
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{module_name}")