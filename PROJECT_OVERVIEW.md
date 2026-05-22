# Captain A股交易辅助系统 (QMT_THS)

A 股量化交易辅助系统，提供盘后选股与盘中监控执行两大核心功能。

---

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 运行环境 | Python 3.14 | |
| 数据源 | **akshare** (Sina / EM 行情) | A 股实时行情、日 K 线、分钟 K 线 |
| | **akshare-proxy-patch** | East Money push2 API 代理网关 |
| 数据查询 | Sina 财经 (主) | 全市场行情、日 K 线、分钟 K 线 |
| | 东方财富 (辅) | 量比、涨停池、个股信息 |
| 配置 | 内置 Config 类 | 所有参数集中在 `config/__init__.py` |
| 持久化 | JSON 文件 | 持仓、账户快照、自选股列表 |

---

## 项目结构

```
qmt_ths/
├── main.py                     # 入口：nightly / intraday
├── run_screening.py            # 独立盘后选股脚本（带详细分类）
├── run_volume_screener.py      # 独立量比选股脚本
│
├── config/
│   └── __init__.py             # 集中配置（交易时间、选股参数、风控参数等）
│
├── data/
│   ├── market_data.py          # 市场数据层（akshare 封装）
│   └── portfolio.py            # 持仓管理与账户快照
│
├── core/
│   ├── nightly_engine.py       # 盘后选股引擎
│   └── intraday_engine.py      # 盘中实时监控执行引擎
│
├── strategies/
│   ├── screener.py             # 日线选股（涨停池 + 量比 + 仙人指路）
│   ├── momentum.py             # 一进二打板策略
│   ├── buy_logic.py            # 买入信号（三层过滤）
│   └── sell_logic.py           # 卖出信号（止损/止盈/遇阻/背离/破位）
│
├── risk/
│   ├── account_risk.py         # 账户级风控（连续亏损 -> 降仓 -> 停买）
│   └── market_risk.py          # 市场级风控（开盘熔断检测）
│
├── utils/
│   ├── helpers.py              # 工具函数（交易日判断、仓位计算）
│   ├── logger.py               # 日志配置
│   └── notifier.py             # 通知推送（支持 Console / Pushover / 企业微信 / 钉钉）
│
├── test/
│   ├── test.py                 # 基础测试
│   ├── test_data.py            # 数据接口测试
│   ├── test_intraday.py        # 盘中引擎测试
│   └── test_screener.py        # 选股器测试
│
├── screening_results/          # 选股结果输出目录
│
└── data/
    ├── positions.json          # 持仓持久化
    ├── watchlist.json          # 自选股列表（nightly 生成，intraday 使用）
    └── account.json            # 账户快照
```

---

## 模块说明

### 1. 入口 — `main.py`

```
python main.py              # 先跑盘后选股，如果盘中则继续监控
python main.py nightly      # 仅盘后选股
python main.py intraday     # 仅盘中监控
```

### 2. 数据层 — `data/market_data.py`

核心类 `MarketData`，封装所有数据接口：

| 方法 | 数据源 | 用途 |
|------|--------|------|
| `_get_spot()` | Sina 行情 | 全市场 5000+ 股票实时行情（价格、涨跌幅、成交量） |
| `_get_em_spot_volume_ratios()` | EM push2 (代理) | 全市场量比数据 |
| `get_limit_up_pool()` | EM 涨停池 (`stock_zt_pool_em`) | 当日涨停股（含连板数、封板时间、行业） |
| `get_daily_bars()` | Sina 日 K | 个股历史日线（前复权/后复权） |
| `get_minute_bars()` | Sina 分钟 K | 当日分钟线 |
| `get_stock_info()` | EM 个股信息 | 市值、行业、基本面 |
| `get_market_cap()` | EM + Sina | 总市值（含 流通市值 兜底） |
| `get_market_advancing_declining()` | Sina 行情 | 实时涨跌家数 |
| `get_vwap()` | 分钟 K 计算 | 当日 VWAP（成交量加权均价） |

**数据源说明：**
- **Sina 财经**：`vip.stock.finance.sina.com.cn` — 实时行情、日 K、分钟 K。无代理需求，但盘中频繁请求会限流。盘后使用无限制。
- **东方财富 push2**：`push2.eastmoney.com` — 量比数据，通过代理网关 `101.201.173.125` 访问。
- **东方财富 涨停池**：`push2ex.eastmoney.com` — 涨停股池，无需代理。
- **akshare 封装**：`stock_zt_pool_em`、`stock_zh_a_daily`、`stock_zh_a_minute`、`stock_individual_info_em` 等。

#### 代理配置

```python
akshare_proxy_patch.install_patch(
    "101.201.173.125",
    auth_token="202605189JYUMHB0",
    hook_domains=["push2.eastmoney.com"],  # 仅量比接口走代理
)
```

### 3. 持仓管理 — `data/portfolio.py`

| 类 | 职责 |
|------|------|
| `PositionState` | 单只持仓状态机（入场价、VWAP、止盈标记、遇阻计数、背离计时） |
| `AccountSnapshot` | 每日账户快照（资产、现金、持仓市值、连续亏损天数） |
| `Portfolio` | 持仓 CRUD、仓位计算、PnL 追踪、JSON 持久化 |

### 4. 盘后选股 — `core/nightly_engine.py`

串联 DailyScreener + SecondBoardMomentum，保存自选股列表到 `data/watchlist.json`。

### 5. 日线选股 — `strategies/screener.py`

四阶段流水线：

| 阶段 | 操作 | 数据源 |
|------|------|--------|
| Phase 0 | 获取当日涨停池 → 直接入选 | EM 涨停池 API |
| Phase 1 | 加载全市场行情 → 过滤 ST / 科创板 / 北交所 | Sina 行情 |
| Phase 2 | 量比预筛选（量比 > 2.5） | EM push2 |
| Phase 3 | 对备选逐只拉日线确认：近期涨停 / 量能突破 / 仙人指路 | Sina 日 K |

**过滤规则：** 排除名称含 ST/\*ST、代码 688/689（科创板）、8xxxxx/BJ（北交所）。

### 6. 一进二打板 — `strategies/momentum.py`

三条件过滤：

1. **市值 < 100 亿** — `get_market_cap()` < `MAX_MARKET_CAP`
2. **15 日内有涨停**（股性活跃） — 日线找 `close >= prev_close × 1.095`
3. **现价 > 最近涨停日最低价**（底线防守） — `current_price > limit_up_low`

### 7. 买入逻辑 — `strategies/buy_logic.py`

三层过滤：

| 层 | 条件 |
|----|------|
| 宏观情绪 | 上涨家数 >= 3000 |
| 时间窗口 | 09:30–10:40 或 14:40–14:55 |
| VWAP 支撑 | ① 盘中低点触 VWAP ±0.5% ② 之后 3 分钟收盘站稳 VWAP ③ 触及时缩量（量 < 前 5 分均量 50%）④ 非急拉冷却期 |

**急拉冷却：** 3 分钟内涨幅 > 3% 且量 > 早盘均量 3 倍 → 冷却 10 分钟不买。

### 8. 卖出逻辑 — `strategies/sell_logic.py`

五大信号：

| 信号 | 触发条件 |
|------|----------|
| 止损 | 现价 < 入场 VWAP × 0.99 |
| 止盈 1 | 涨幅 >= 3% → 卖 50% |
| 止盈 2 | 涨幅 >= 5% → 卖剩余 50% |
| 遇阻 | 高点触 VWAP 后连续 2 分钟收低于 VWAP → 计数器至上限卖出 |
| 量价背离 | 量比 > 10 且涨幅 1%–2.5% 持续超过 5 分钟 |
| 日线破位 | 14:50 后现价 < min(昨收, 前日收) |

### 9. 风控 — `risk/`

**账户风控：**
- 连续亏损 2 天 → 仓位上限 50%
- 连续亏损 3 天 → 强制清仓 + 暂停买入 N 天

**市场风控：**
- 开盘 09:30–09:40 检测：
- 下跌家数 > 4000 → 全仓清仓
- 下跌家数 > 3000 → 仓位上限 50%

### 10. 独立脚本

**`run_screening.py`** — 独立盘后选股（详细分类输出）：
- 调用日线选股 → 一进二打板 → 详细分类
- 输出 JSON + 可读 TXT 到 `screening_results/YYYY-MM-DD.*`
- 分类：涨停板 / 近期涨停\_量能突破 / 量能突破 / 仙人指路 / 其他

**`run_volume_screener.py`** — 独立量比选股：
- 仅调 EM 量比数据（不依赖 Sina）
- 筛选量比 > 2.0，按量比降序排列

---

## 数据流

### 盘后选股流程

```
run_screening.py
  ├── [0] 预取全市场行情 (_get_spot) ──── 一次，传参复用
  ├── [1] DailyScreener.run(spot_df)
  │     ├── Phase 0: 涨停池 → 直接入选
  │     ├── Phase 1: spot 数据过滤 ST/688/8xx
  │     ├── Phase 2: EM 量比过滤 > 2.5
  │     └── Phase 3: 日 K 确认（涨停历史/量能/仙人指路）
  ├── [2] SecondBoardMomentum.run(candidates, spot_df)
  │     ├── 市值 < 100亿
  │     ├── 15日内有涨停
  │     └── 现价 > 涨停日最低价
  └── [3] classify_candidates(candidates, spot_df)
        └── 涨停板/量能突破/仙人指路 分类输出
```

### 盘中监控流程

```
IntradayEngine.start()
  └── 循环 tick (每 60s):
        ├── 市场风控检查（开盘熔断）
        ├── 卖出信号评估（每只持仓）
        │     ├── 止损 → 全平
        │     ├── 止盈 → 部分平
        │     ├── 遇阻 → 全平
        │     ├── 背离 → 全平
        │     └── 破位 → 全平
        ├── 账户风控检查
        │     └── 连续亏损 → 降仓/停买
        └── 买入信号评估（自选股）
              └── 三层过滤 → 开仓
```

---

## 配置说明

所有可调参数集中在 `config/__init__.py`：

| 配置类 | 关键参数 | 默认值 |
|--------|----------|--------|
| `TradingTime` | 交易时段、买入窗口 | 09:30–11:30, 13:00–15:00 |
| `MacroFilter` | 上涨家数阈值、熔断阈值 | 3000/4000 |
| `BuyParams` | VWAP 带宽、确认分钟数、缩量比、急拉阈值 | 0.5%/3min/50%/3% |
| `SellParams` | 止损比、止盈比、遇阻计数、背离参数 | 1%/3%/5min |
| `RiskParams` | 连续亏损天数限制 | 2天降仓/3天清仓 |
| `ScreenerParams` | 量比阈值、均量周期、仙人指路比例 | 2.5/30天/2x/0.2x |
| `MomentumParams` | 市值上限、涨停回溯天数 | 100亿/15天 |
| `SystemConfig` | 刷新间隔、文件路径、日志级别 | 60s |

---

## 运行方式

```bash
# 盘后选股
python main.py nightly

# 或独立盘后选股脚本（推荐，输出更详细）
python run_screening.py                           # 选今天
python run_screening.py --date 20260522           # 指定日期

# 单独量比选股
python run_volume_screener.py

# 盘中监控
python main.py intraday

# 测试
python -m test.test_screener
python -m test.test_data
```