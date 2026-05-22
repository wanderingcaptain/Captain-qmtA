"""
Market Data Layer — 统一的数据获取与缓存层。
拆分为缓存装饰器、代理配置初始化以及核心业务方法。

变更记录：
  v1.1  - 解耦数据层与缓存逻辑（引入 @cached 装饰器）
        - 代理凭证移至环境变量读取，不在模块顶层执行副作用
        - _get_spot() 和 _get_em_spot_volume_ratios() 改为公开方法 get_spot()
        - 移除冗长的内联重试，改用统一的 @retry 装饰器
        - 补充异常处理，统一抛出 DataFetchError
"""

import os
import time
import functools
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from utils.exceptions import DataFetchError, RateLimitError
from utils.retry import retry
from utils.market_utils import to_sina_code, normalize_code
from utils.logger import get_logger

logger = get_logger("data.market")


# ============================================================
# 通用缓存装饰器
# ============================================================
def cached(ttl_seconds: int = 60):
    """
    轻量级方法级别的 TTL 缓存装饰器（不区分实例，针对单例使用）。
    """
    def decorator(func):
        cache_data = {}

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 将 args 和 kwargs 转换为可哈希的 key
            # 注：这里只支持简单的基本类型参数，复杂类型请勿作为缓存 key
            key = str(args) + str(kwargs)
            now = datetime.now()

            if key in cache_data:
                timestamp, data = cache_data[key]
                if (now - timestamp).total_seconds() < ttl_seconds:
                    return data

            # 缓存过期或不存在，调用原函数
            result = func(self, *args, **kwargs)
            cache_data[key] = (now, result)
            return result

        return wrapper
    return decorator


class MarketData:
    """
    统一的市场数据接口层。
    基于 Sina 财经和 East Money (akshare 封装)。
    """

    def __init__(self):
        self._init_proxy()

    def _init_proxy(self):
        """
        从环境变量初始化东方财富的 push2 代理网关。
        """
        host = os.environ.get("QMT_PROXY_HOST", "")
        token = os.environ.get("QMT_PROXY_TOKEN", "")

        if host and token:
            try:
                import akshare_proxy_patch
                akshare_proxy_patch.install_patch(
                    host,
                    auth_token=token,
                    retry=30,
                    hook_domains=["push2.eastmoney.com"],
                )
                logger.info(f"已启用 East Money push2 代理网关: {host}")
            except ImportError:
                logger.warning("akshare_proxy_patch 未安装，代理配置已跳过")
            except Exception as e:
                logger.error(f"代理网关初始化失败: {e}")
        else:
            logger.warning(
                "未配置代理环境变量 (QMT_PROXY_HOST / QMT_PROXY_TOKEN)。"
                "量比数据接口可能无法访问。"
            )

    # ------------------------------------------------------------------
    # 基础行情（带缓存）
    # ------------------------------------------------------------------
    @cached(ttl_seconds=60)
    @retry(max_attempts=3, backoff=2.0)
    def get_spot(self) -> pd.DataFrame:
        """
        获取全市场 A 股实时行情 (Sina API)。
        """
        count_url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service"
            "/api/json_v2.php/Market_Center.getHQNodeStockCount"
        )
        try:
            resp = requests.get(
                count_url,
                params={"node": "hs_a"},
                headers={"Referer": "https://finance.sina.com.cn"},
                timeout=15,
            )
            text = resp.text.strip()
            if text.startswith("<"):
                raise RateLimitError("Sina API 触发限流（返回 HTML）")
            total = int(text.strip('"'))
        except RateLimitError:
            raise
        except Exception as e:
            raise DataFetchError(f"获取全市场行情总数失败: {e}")

        page_count = total // 80 + (1 if total % 80 else 0)
        api_url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service"
            "/api/json_v2.php/Market_Center.getHQNodeData"
        )
        headers = {"Referer": "https://finance.sina.com.cn"}
        all_rows = []

        # 获取各分页，若单页失败则记录警告并跳过，不阻断整体流程
        for page in range(1, page_count + 1):
            params = {
                "page": str(page),
                "num": "80",
                "sort": "symbol",
                "asc": "1",
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "page",
            }
            try:
                r = requests.get(api_url, params=params, headers=headers, timeout=10)
                data = r.json()
                all_rows.extend(data)
            except Exception as e:
                logger.warning(f"获取行情分页 {page}/{page_count} 失败: {e}")

        if not all_rows:
            logger.warning("Sina 批量接口返回为空，尝试降级使用 akshare 封装...")
            import akshare as ak
            df = ak.stock_zh_a_spot()
        else:
            df = pd.DataFrame(all_rows)
            df.rename(
                columns={
                    "trade": "price",
                    "changepercent": "pct_chg",
                    "pricechange": "change",
                    "settlement": "prev_close",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "volume": "volume",
                    "amount": "amount",
                },
                inplace=True,
            )

        return df

    @cached(ttl_seconds=60)
    def get_volume_ratios(self) -> pd.DataFrame:
        """
        获取全市场量比数据 (East Money push2 API)。
        """
        all_rows = []
        page = 1
        page_size = 100
        max_pages = 60

        while page <= max_pages:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": str(page),
                "pz": str(page_size),
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f10,f12,f14",
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                data = resp.json()
                items = data.get("data", {}).get("diff", [])
                if not items:
                    break
                for item in items:
                    all_rows.append({
                        "code": str(item.get("f12", "")),
                        "name": str(item.get("f14", "")),
                        "price": item.get("f2", 0),
                        "pct_chg": item.get("f3", 0),
                        "volume_ratio": item.get("f10", 0),
                    })
                if len(items) < page_size:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"获取 EM 量比分页 {page} 失败: {e}")
                break

        df = pd.DataFrame(all_rows)
        if not df.empty:
            for col in ("price", "pct_chg", "volume_ratio"):
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df

    # ------------------------------------------------------------------
    # 个股信息
    # ------------------------------------------------------------------
    def get_stock_list(self) -> List[str]:
        """获取所有 A 股代码列表。"""
        df = self.get_spot()
        if df.empty:
            return []
        return df["code"].astype(str).tolist()

    @cached(ttl_seconds=3600)
    def get_stock_info(self, code: str) -> Dict:
        """获取个股元数据（总市值、流通股本等）。"""
        result = {}
        code_bare = normalize_code(code)

        # 1. 尝试从日线数据计算流通市值
        try:
            daily = self.get_daily_bars(code_bare, count=1)
            if not daily.empty:
                last = daily.iloc[-1]
                result["最新价"] = last["close"]
                result["流通股本"] = last.get("outstanding_share", 0)
                result["流通市值"] = last["close"] * result["流通股本"]
        except Exception:
            pass

        # 2. 从 EM API 获取详细信息
        try:
            import akshare as ak
            info_df = ak.stock_individual_info_em(code_bare)
            for _, r in info_df.iterrows():
                result[r["item"]] = r["value"]
        except Exception:
            pass

        return result

    def get_market_cap(self, code: str) -> float:
        """获取个股总市值（优先总市值，降级流通市值）。"""
        info = self.get_stock_info(code)
        cap = info.get("总市值", 0)
        if cap:
            return float(cap)
        return float(info.get("流通市值", 0))

    # ------------------------------------------------------------------
    # 涨停池与 K 线数据
    # ------------------------------------------------------------------
    @retry(max_attempts=3)
    def get_limit_up_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """获取当日涨停池数据 (EM API)。"""
        import akshare as ak
        if trade_date is not None:
            trade_date = trade_date.replace("-", "")
        df = ak.stock_zt_pool_em(date=trade_date)
        if df.empty:
            return df
        df.rename(
            columns={
                "代码": "code",
                "名称": "name",
                "涨跌幅": "pct_chg",
                "最新价": "price",
                "成交额": "amount",
                "流通市值": "float_market_cap",
                "总市值": "total_market_cap",
                "换手率": "turnover_rate",
                "封板资金": "seal_amount",
                "首次封板时间": "first_seal_time",
                "最后封板时间": "last_seal_time",
                "炸板次数": "blast_count",
                "涨停统计": "limit_up_stats",
                "连板数": "consecutive_boards",
                "所属行业": "industry",
            },
            inplace=True,
        )
        return df

    @retry(max_attempts=3)
    def get_daily_bars(
        self, code: str, count: int = 60, adjust: str = "qfq"
    ) -> pd.DataFrame:
        """
        获取日 K 线。
        抛出 DataFetchError 区分于返回空 DataFrame。
        使用 EastMoney 接口避免多线程下 PyMiniRacer C++ 崩溃。
        """
        import akshare as ak
        bare_code = strip_code_prefix(code)
        try:
            df = ak.stock_zh_a_hist(symbol=bare_code, period="daily", adjust=adjust)
        except Exception as e:
            raise DataFetchError(f"获取 {code} 日线失败: {e}")

        if df.empty or "日期" not in df.columns:
            return pd.DataFrame()

        df.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            },
            inplace=True
        )
        return df.tail(count).reset_index(drop=True)

    @retry(max_attempts=3)
    def get_minute_bars(self, code: str) -> pd.DataFrame:
        """获取当日分钟 K 线。"""
        import akshare as ak
        sina_code = to_sina_code(code)
        try:
            df = ak.stock_zh_a_minute(sina_code, period="1")
        except Exception as e:
            raise DataFetchError(f"获取 {code} 分钟线失败: {e}")

        if df.empty:
            return df

        df.rename(columns={"day": "time"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    # ------------------------------------------------------------------
    # 盘中衍生计算指标
    # ------------------------------------------------------------------
    def get_vwap(self, code: str) -> float:
        """计算当日 VWAP (成交额 / 成交量)。"""
        try:
            bars = self.get_minute_bars(code)
            if bars.empty:
                return 0.0
            total_turnover = bars["amount"].sum()
            total_volume = bars["volume"].sum()
            if total_volume == 0:
                return 0.0
            return total_turnover / total_volume
        except DataFetchError:
            return 0.0

    def get_price(self, code: str) -> float:
        """获取最新成交价。"""
        df = self.get_spot()
        code_bare = normalize_code(code)
        row = df[df["code"] == code_bare]
        if row.empty:
            return 0.0
        return float(row.iloc[0]["price"])

    def get_volume_ratio(self, code: str) -> float:
        """基于分钟线实时计算近似量比。"""
        try:
            bars = self.get_minute_bars(code)
            if bars.empty:
                return 0.0
            today_vol = bars["volume"].sum()
            daily_bars = self.get_daily_bars(code, count=6)
            if daily_bars.empty or len(daily_bars) < 2:
                return 0.0
            avg_daily_vol = daily_bars.tail(5)["volume"].mean()
            if avg_daily_vol <= 0:
                return 0.0
            return today_vol / avg_daily_vol
        except DataFetchError:
            return 0.0

    # ------------------------------------------------------------------
    # 宏观数据
    # ------------------------------------------------------------------
    @cached(ttl_seconds=30)
    def get_market_advancing_declining(self) -> Tuple[int, int, int]:
        """
        获取全市场上涨、下跌、平盘家数。
        基于 get_spot() 计算，缓存 30 秒。
        """
        df = self.get_spot()
        if df.empty:
            return 0, 0, 0

        # DataFrame column is "pct_chg" after rename in get_spot()
        advancing = int((df["pct_chg"] > 0).sum())
        declining = int((df["pct_chg"] < 0).sum())
        flat = int((df["pct_chg"] == 0).sum())
        return advancing, declining, flat

    # ------------------------------------------------------------------
    # 交易时间
    # ------------------------------------------------------------------
    @staticmethod
    def is_trading_time() -> bool:
        """判断当前时间是否处于交易时段内。"""
        now = datetime.now().time()
        from config import Config
        if Config.TRADING_TIME.MORNING_OPEN <= now <= Config.TRADING_TIME.MORNING_CLOSE:
            return True
        if Config.TRADING_TIME.AFTERNOON_OPEN <= now <= Config.TRADING_TIME.AFTERNOON_CLOSE:
            return True
        return False

    @cached(ttl_seconds=3600)
    def is_market_open_today(self) -> bool:
        """判断今日是否为交易日（基于 Sina 历史交易日历）。"""
        import akshare as ak
        try:
            df = ak.tool_trade_date_hist_sina()
            if df.empty:
                return False
            today_dt = date.today()
            return not df[df["trade_date"] == today_dt].empty
        except Exception:
            return False