# Options Trading Backtesting Framework

一个用于期权交易策略回测的 Python 框架，专注于 BTC 期权的 Calendar Spread 和 Straddle 策略。

## 功能特性

- **策略支持**: Calendar Spread、Straddle（Long/Short）、Gamma Scalping
- **数据处理**: OKX 期权数据预处理和 IV/Greeks 计算
- **波动率预测**: GARCH(1,1) + EWMA 模型
- **Delta 对冲**: 反向永续合约对冲功能
- **风险管理**: 异常交易检测和排除
- **性能分析**: Sharpe、Sortino、MDD、Calmar 等指标

## 策略详解

### 1. Calendar Spread 策略

**策略原理**：
Calendar Spread（日历价差）是一种时间价值策略，通过买入远期期权、卖出近期期权来获利。该策略主要受益于时间衰减差异和隐含波动率结构变化。

**开仓条件**：
- 短期 IV > 长期 IV（隐含波动率期限结构倒挂）
- IV 价差 ≥ 2%
- 期权接近 ATM（±3% 容差范围）
- 预定义时间配对：7天 vs 1个月、14天 vs 1个月、14天 vs 2个月、14天 vs 3个月

**盈利机制**：
- **时间衰减**：近期期权时间价值衰减更快
- **波动率收敛**：短期高 IV 向长期低 IV 收敛
- **Delta 中性**：接近 ATM 时 Delta 相互抵消

**风险管理**：
```python
# 止损条件
max_loss_pct = 30%  # 相对入场权利金

# 止盈条件  
target_profit_pct = 50%  # 相对入场权利金

# 特殊平仓条件
1. IV 价差反转（从正值变负值）
2. 短期期权剩余 1 天且亏损
3. 现货价格突破短期期权执行价±2%
```

### 2. Gamma Scalping with Sell Straddle 策略

**策略原理**：
Short Straddle 结合 Gamma Scalping 是一种波动率套利策略。通过卖出同执行价的看涨和看跌期权，收取时间价值，同时通过 Delta 对冲来管理方向性风险。

**开仓条件**：
- 期权到期时间：7-14 天
- IV > RV + 5%（隐含波动率高估已实现波动率）
- 期权接近 ATM（现货价格接近执行价）
- 高 Gamma 环境（便于频繁对冲）

**盈利机制**：
- **时间价值收取**：Theta 正收益
- **波动率均值回归**：高估的 IV 回落到合理水平
- **Gamma Scalping**：通过频繁 Delta 对冲捕获波动率差异

**Delta 对冲机制**：
```python
# 对冲触发条件
delta_threshold = 5%  # 净 Delta 超过 5% 时重新对冲

# 对冲工具
使用 BTC 反向永续合约进行 Delta 中性对冲

# 对冲逻辑
当 Net Delta = +0.1 时，做空 0.1 BTC 永续合约
当 Net Delta = -0.1 时，做多 0.1 BTC 永续合约
```

**风险管理**：
```python
# 止损条件
max_loss_pct = 30%  # 相对入场权利金

# 止盈条件
target_profit_pct = 50%  # 相对入场权利金

# 特殊平仓条件
1. IV 大幅下降 > 10%（Short Straddle 获利信号）
2. 现货价格大幅偏离执行价 > 15%
3. 期权即将到期且亏损
4. Delta 对冲成本过高
```

## 快速开始

### 安装依赖
```bash
pip install -e .
```

### 运行回测

#### Calendar Spread 策略
```python
from qtrade.simulate_tarde.spread_trading import backtest_strategy

backtest_strategy(
    data_folder='data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks',
    init_btc=1.0,
    strategy_name="calendar_spread",
    enable_delta_hedge=False,  # Calendar Spread 通常不需要对冲
    save_folder='calendar_spread_results'
)
```

#### Gamma Scalping Sell Straddle 策略
```python
backtest_strategy(
    data_folder='data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks',
    init_btc=1.0,
    strategy_name="gamma_scalping_sell_straddle",
    enable_delta_hedge=True,   # Straddle 需要 Delta 对冲
    delta_threshold=0.05,      # 5% Delta 阈值
    hedge_cost_bps=0.0002,     # 2bps 对冲成本
    save_folder='straddle_gamma_scalping_results'
)
```

## 项目结构

```
qtrade/
├── data_loader.py              # 数据加载和迭代器
├── data_utils.py              # 数据处理工具函数
├── simulate_tarde/
│   ├── spread_trading.py      # 主回测引擎
│   ├── pairs/
│   │   ├── calendar_pair.py   # Calendar Spread 策略类
│   │   └── straddle_pair.py   # Straddle 策略类
│   ├── vol_tracker/
│   │   └── vol_tracker.py     # GARCH/EWMA 波动率预测
│   ├── calendar_helper.py     # Calendar 策略辅助函数
│   ├── straddle_helper.py     # Straddle 策略辅助函数
│   ├── trading_utils.py       # 通用交易工具
│   └── metric_performance.py  # 性能指标计算
└── okx_options_analysis/      # 期权数据分析工具
```

## 性能指标

回测结果包含以下关键指标：

- **收益指标**: 总收益率、年化收益率
- **风险指标**: 年化波动率、最大回撤 (MDD)
- **风险调整收益**: Sharpe 比率、Sortino 比率、Calmar 比率
- **交易统计**: 胜率、平均持仓时间、交易频率
- **对冲成本**: Delta 对冲总成本及其对收益的影响

## 数据要求

- **期权数据**: OKX BTC 期权 30 分钟 K 线数据
- **包含字段**: 期权价格、隐含波动率、Greeks（Delta、Gamma、Vega）
- **时间范围**: 建议至少 1 年以上的历史数据
- **数据质量**: 已处理异常值和缺失数据

## 风险提示

⚠️ **本框架仅用于学术研究和策略回测，不构成投资建议**

- 期权交易涉及高风险，可能导致全部本金损失
- 回测结果不代表未来实际表现
- 实际交易中需考虑滑点、手续费、流动性等因素
- Delta 对冲需要频繁交易，实际成本可能较高

