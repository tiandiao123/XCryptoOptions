# API 参考文档

本文档详细介绍Options Trading Framework的核心API接口。

## 📋 目录

1. [TradingEngine](#tradingengine)
2. [RiskManager](#riskmanager)
3. [Order API](#order-api)
4. [Strategy API](#strategy-api)
5. [Utils API](#utils-api)

## 🚀 TradingEngine

主交易引擎，负责协调所有交易活动。

### 构造函数

```python
TradingEngine(
    calendar_config_path: str,
    gamma_scalping_config_path: str,
    env: str = "testnet",
    max_open_calendar: int = 1,
    max_open_gamma_scalping: int = 1,
    enable_delta_hedge: bool = True,
    output_folder: str = "/home/ubuntu/options_trading/trading_results"
)
```

**参数**:
- `calendar_config_path`: Calendar Spread策略配置文件路径
- `gamma_scalping_config_path`: Gamma Scalping策略配置文件路径
- `env`: 交易环境 ("testnet" 或 "mainnet")
- `max_open_calendar`: Calendar Spread最大持仓数量
- `max_open_gamma_scalping`: Gamma Scalping最大持仓数量
- `enable_delta_hedge`: 是否启用Delta对冲
- `output_folder`: 结果输出文件夹路径

### 主要方法

#### run_loop()

```python
def run_loop(self, check_durantion: int = 300, order_type: str = "market") -> None
```

启动主交易循环，包含3个独立线程。

**参数**:
- `check_durantion`: 检查间隔（秒）
- `order_type`: 订单类型 ("market" 或 "limit")

**示例**:
```python
trading_engine.run_loop(
    check_durantion=300,  # 5分钟检查
    order_type="market"
)
```

#### record_pnl()

```python
def record_pnl(self, record_interval: int = 300) -> None
```

定期记录账户P&L并生成equity曲线。

**参数**:
- `record_interval`: 记录间隔（秒）

#### _ranking_opportunities()

```python
def _ranking_opportunities(self, opportunities: List[Union[CalendarSpreadOpportunity, StraddleOpportunity]]) -> Union[CalendarSpreadOpportunity, StraddleOpportunity, None]
```

对交易机会进行排序并返回最佳机会。

**返回**: 最佳交易机会或None

## 🛡️ RiskManager

风险管理系统，负责持仓监控和风险控制。

### 构造函数

```python
RiskManager(
    symbol: str = "BTCUSDT",
    max_positions: int = 1,
    enable_delta_hedge: bool = False,
    delta_hedge_threshold: float = 0.05,
    delta_risk_threshold: float = 0.5,
    stop_loss_ratio: float = -0.3,
    profit_target_ratio: float = 0.5,
    price_change_risk_ratio: float = 0.15,
    realized_vol_level: str = "30m",
    env: str = "testnet"
)
```

**参数**:
- `symbol`: 交易标的符号
- `max_positions`: 最大持仓数量
- `enable_delta_hedge`: 是否启用Delta对冲
- `delta_hedge_threshold`: Delta对冲阈值
- `delta_risk_threshold`: Delta风险阈值
- `stop_loss_ratio`: 止损比例
- `profit_target_ratio`: 止盈比例
- `price_change_risk_ratio`: 价格变化风险比例
- `realized_vol_level`: 实现波动率计算级别
- `env`: 交易环境

### 主要方法

#### add_position()

```python
def add_position(self, position_id: str, position: Union[StraddleOpportunity, CalendarSpreadOpportunity], position_type: str) -> bool
```

添加新持仓到管理系统。

**参数**:
- `position_id`: 持仓唯一标识
- `position`: 持仓对象
- `position_type`: 持仓类型 ("straddle" 或 "calendar_spread")

**返回**: 是否成功添加

#### remove_position()

```python
def remove_position(self, position_id: str, position_type: str) -> bool
```

从管理系统移除持仓。

#### check_close_condition()

```python
def check_close_condition(self, position: Union[StraddleOpportunity, CalendarSpreadOpportunity], env: str) -> Tuple[bool, str]
```

检查持仓是否满足平仓条件。

**返回**: (是否需要平仓, 平仓原因)

#### close_positions()

```python
def close_positions(
    self, 
    position: Union[StraddleOpportunity, CalendarSpreadOpportunity],
    env: str = "testnet",
    close_reason: str = "Unknown",
    position_close_log: str = None
) -> Dict[str, Any]
```

执行持仓平仓操作。

**参数**:
- `position`: 要平仓的持仓对象
- `env`: 交易环境
- `close_reason`: 平仓原因
- `position_close_log`: 平仓日志文件路径

#### hedge_action()

```python
def hedge_action(
    self,
    newly_hedge_size: float,
    instrument: str = "BTC-PERPETUAL",
    order_type: str = "market",
    price: float = None,
    env: str = "testnet"
) -> bool
```

执行Delta对冲操作。

**参数**:
- `newly_hedge_size`: 需要对冲的Delta数量
- `instrument`: 对冲工具
- `order_type`: 订单类型
- `price`: 限价单价格（可选）
- `env`: 交易环境

#### monitor_positions()

```python
def monitor_positions(self, check_duration: str = "5min") -> None
```

启动持仓监控循环。

**参数**:
- `check_duration`: 检查间隔 ("5min", "10min", "15min", "30min")

## 📞 Order API

与Deribit交易所交互的API接口。

### 期权订单

#### place_options_market_order_btc_notional()

```python
def place_options_market_order_btc_notional(
    instrument: str,
    side: str,
    contracts: float,
    reduce_only: bool = False,
    env: str = "testnet"
) -> Dict[str, Any]
```

下达期权市价单。

**参数**:
- `instrument`: 期权合约名称
- `side`: 交易方向 ("buy" 或 "sell")
- `contracts`: 合约数量
- `reduce_only`: 是否仅减仓
- `env`: 交易环境

**返回**: 订单结果字典

### 期货订单

#### place_market_order_btc_notional()

```python
def place_market_order_btc_notional(
    instrument: str,
    side: str,
    btc_amount: float,
    reduce_only: bool = False,
    env: str = "testnet"
) -> Dict[str, Any]
```

下达期货市价单。

#### place_limit_order_btc_notional()

```python
def place_limit_order_btc_notional(
    instrument: str,
    side: str,
    btc_amount: float,
    price: float,
    post_only: bool = False,
    reduce_only: bool = False,
    env: str = "testnet"
) -> Dict[str, Any]
```

下达期货限价单。

### 账户信息

#### get_account_summary()

```python
def get_account_summary(currency: str, env: str = "testnet") -> Dict[str, Any]
```

获取账户摘要信息。

**参数**:
- `currency`: 币种 ("BTC" 或 "ETH")
- `env`: 交易环境

**返回**: 账户信息字典，包含:
- `balance`: 账户余额
- `equity`: 账户净值
- `available_funds`: 可用资金
- `unrealized_pnl`: 未实现盈亏

### 持仓信息

#### get_instrument_pnl()

```python
def get_instrument_pnl(instrument_name: str, env: str = "testnet") -> float
```

获取特定合约的P&L。

#### get_instrument_open_price()

```python
def get_instrument_open_price(instrument_name: str, env: str = "testnet") -> float
```

获取特定合约的开仓价格。

#### get_instrument_position_size()

```python
def get_instrument_position_size(instrument_name: str, env: str = "testnet") -> float
```

获取特定合约的持仓大小。

#### get_instrument_iv()

```python
def get_instrument_iv(instrument_name: str, env: str = "testnet") -> float
```

获取特定合约的隐含波动率。

## 📈 Strategy API

策略相关的API接口。

### Calendar Spread

#### CalendarSpreadOpportunity

```python
@dataclass
class CalendarSpreadOpportunity:
    rank: int
    short_option: OptionData
    long_option: OptionData
    iv_spread: float
    iv_spread_pct: float
    time_gap_days: int
    net_premium: float
    max_profit_potential: float
    signal_strength: str
    short_option_entry_iv: float = 0.0
    long_option_entry_iv: float = 0.0
    open_status: bool = False
    contracts: float = 0.0
```

#### update_calendar_spread_opportunity()

```python
def update_calendar_spread_opportunity(
    opportunity: CalendarSpreadOpportunity,
    realized_vol: float,
    net_delta_only: bool = False,
    env: str = "testnet"
) -> Union[float, None]
```

更新Calendar Spread机会的Greeks数据。

### Straddle

#### StraddleOpportunity

```python
@dataclass
class StraddleOpportunity:
    call_option: OptionData
    put_option: OptionData
    strategy_type: str = "short_straddle"
    avg_iv: float = 0.0
    realized_vol: float = 0.0
    iv_premium: float = 0.0
    iv_premium_pct: float = 0.0
    call_option_entry_iv: float = 0.0
    put_option_entry_iv: float = 0.0
    entry_spot_price: float = 0.0
    # ... 其他字段
```

#### update_straddle_opportunity()

```python
def update_straddle_opportunity(
    opportunity: StraddleOpportunity,
    realized_vol: float,
    net_delta_only: bool = False,
    env: str = "testnet"
) -> Union[float, None]
```

更新Straddle机会的Greeks数据。

### OptionData

```python
@dataclass
class OptionData:
    symbol: str
    strike: float
    expiry: str
    days_to_expiry: int
    option_type: str
    iv: float
    bid: float
    ask: float
    mid_price: float
    delta: float
    net_delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
```

期权基础数据结构。

## 🔧 Utils API

工具函数和辅助类。

### 线程安全容器

#### ThreadSafeMap

```python
class ThreadSafeMap:
    def __init__(self, init: Optional[Mapping[Any, Any]] = None)
    def __len__(self) -> int
    def __contains__(self, key: Any) -> bool
    def get(self, key: Any, default: Any = None) -> Any
    def __getitem__(self, key: Any) -> Any
    def __setitem__(self, key: Any, value: Any) -> None
    def pop(self, key: Any, default: Any = None) -> Any
    def items(self) -> List[Tuple[Any, Any]]
    def keys(self) -> List[Any]
    def values(self) -> List[Any]
```

线程安全的字典实现。

### 波动率追踪

#### RealDataEWMAVolTracker

```python
class RealDataEWMAVolTracker:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
        window_size: int = 96,
        ewma_lambda: float = 0.94
    )
    
    def predict(self) -> Dict[str, float]:
        """返回当前预测的波动率"""
        return {
            "realized_vol_annualized": float,
            "ewma_vol": float,
            "confidence": float
        }
```

实时EWMA波动率追踪器。

## 📊 数据结构

### 配置文件格式

#### Calendar Spread配置

```yaml
strategy_config:
  max_positions: 3
  min_iv_spread: 0.02
  atm_tolerance_pct: 0.03
  time_pairs:
    - [7, 30]
    - [14, 30]
    - [14, 60]

risk_management:
  stop_loss_ratio: -0.30
  profit_target_ratio: 0.50
  max_loss_per_trade: 0.05

market_filters:
  min_bid_price: 0.001
  max_bid_ask_spread_pct: 0.25
  min_open_interest: 5
```

#### Straddle配置

```yaml
strategy_config:
  max_positions: 2
  min_days_to_expiry: 7
  max_days_to_expiry: 21
  min_iv_premium: 0.05

volatility_criteria:
  min_iv_premium: 0.03

time_criteria:
  min_days_to_expiry: 7
  max_days_to_expiry: 35
  optimal_days_range: [7, 25]

delta_hedge:
  enabled: true
  delta_threshold: 0.05
  hedge_ratio: 1.0
```

### 返回数据格式

#### 订单结果

```json
{
  "success": true,
  "order_id": "12345678",
  "instrument": "BTC-28NOV25-114000-C",
  "side": "buy",
  "amount": 1.0,
  "price": 0.0625,
  "timestamp": "2023-10-12T14:30:00Z",
  "commission": 0.0003
}
```

#### P&L数据

```json
{
  "initial_equity": 1.0,
  "history": [
    {
      "timestamp": "2023-10-12 14:30:00",
      "equity": 1.00234,
      "relative_pnl": 0.00234,
      "datetime": "2023-10-12T14:30:00"
    }
  ],
  "last_update": "2023-10-12 14:30:00"
}
```

## 🚨 错误处理

### 异常类型

#### DeribitAPIError

```python
class DeribitAPIError(Exception):
    def __init__(self, message: str, error_code: int = None)
```

Deribit API相关错误。

#### InsufficientFundsError

```python
class InsufficientFundsError(Exception):
    def __init__(self, required: float, available: float)
```

资金不足错误。

#### PositionNotFoundError

```python
class PositionNotFoundError(Exception):
    def __init__(self, position_id: str)
```

持仓未找到错误。

### 错误处理示例

```python
from qtrade.order_api.exceptions import DeribitAPIError, InsufficientFundsError

try:
    result = place_options_market_order_btc_notional(
        instrument="BTC-28NOV25-114000-C",
        side="buy",
        contracts=1.0,
        env="testnet"
    )
except DeribitAPIError as e:
    print(f"API错误: {e.message} (代码: {e.error_code})")
except InsufficientFundsError as e:
    print(f"资金不足: 需要 {e.required}, 可用 {e.available}")
except Exception as e:
    print(f"未知错误: {e}")
```

## 🔍 调试和日志

### 日志配置

```python
import logging

# 设置日志级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading.log'),
        logging.StreamHandler()
    ]
)

# 获取特定模块的日志器
logger = logging.getLogger('qtrade.trading_engine')
logger.setLevel(logging.DEBUG)
```

### 调试模式

```python
# 启用详细日志
trading_engine = TradingEngine(
    # ... 其他参数
    debug_mode=True
)

# 或者设置环境变量
import os
os.environ['QTRADE_DEBUG'] = '1'
```

---

## 📝 版本历史

### v1.0.0
- 基础回测功能
- Calendar Spread和Straddle策略

### v2.0.0 (当前)
- 实时交易引擎
- 多线程架构
- 完整的风险管理系统
- Deribit API集成
- 实时监控和分析

---

这个API文档涵盖了框架的所有主要接口。如需更详细的信息，请参考源代码中的文档字符串和示例。
