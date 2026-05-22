"""
通用重试装饰器。
替代 market_data.py 中手动编写的 for attempt in range(3): ... 循环。
"""

import functools
import time
import logging
from typing import Callable, Tuple, Type

from utils.exceptions import DataFetchError

logger = logging.getLogger("qmt_ths.retry")


def retry(
    max_attempts: int = 3,
    backoff: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    raise_on_failure: bool = True,
):
    """
    重试装饰器。

    参数：
        max_attempts: 最大尝试次数（含首次）。
        backoff: 每次重试的等待基数（秒）。第 n 次等待 backoff^(n-1)。
        exceptions: 需要捕获并重试的异常类型。
        raise_on_failure: 所有尝试耗尽后是否抛出 DataFetchError；
                          False 时返回 None。

    用法：
        @retry(max_attempts=3, backoff=2.0, exceptions=(requests.Timeout,))
        def fetch_data(): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        wait = backoff ** (attempt - 1)
                        logger.warning(
                            f"[retry] {func.__qualname__} attempt {attempt}/{max_attempts} "
                            f"failed: {exc!r}. Retrying in {wait:.1f}s..."
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"[retry] {func.__qualname__} all {max_attempts} attempts failed."
                        )
            if raise_on_failure:
                raise DataFetchError(
                    f"{func.__qualname__} failed after {max_attempts} attempts"
                ) from last_exc
            return None
        return wrapper
    return decorator
