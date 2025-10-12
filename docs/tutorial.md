# Options Trading Framework 详细教程

本教程将详细介绍如何使用Options Trading Framework进行期权策略的回测和实时交易。

## 📋 目录

1. [环境安装](#环境安装)
2. [配置设置](#配置设置)
3. [策略回测](#策略回测)
4. [实时交易](#实时交易)
5. [风险管理](#风险管理)
6. [监控和分析](#监控和分析)
7. [常见问题](#常见问题)

## 🔧 环境安装

### 系统要求

- Python 3.8+
- Linux/macOS/Windows
- 至少4GB内存
- 稳定的网络连接（实时交易）

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd options_trading
```

2. **创建虚拟环境**
```bash
# 使用conda (推荐)
conda create -n options_trading python=3.9
conda activate options_trading

# 或使用venv
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows
```

3. **安装依赖**
```bash
pip install -e .
```

4. **安装额外依赖（实时交易）**
```bash
pip install matplotlib requests pandas numpy
```

## ⚙️ 配置设置

### Deribit API配置

实时交易需要配置Deribit API凭证：

1. **获取API密钥**
   - 访问 [Deribit测试网](https://test.deribit.com) 或 [Deribit主网](https://www.deribit.com)
   - 创建账户并生成API密钥

2. **配置环境变量**
```bash
# 创建 .env 文件
cat > .env << EOF
DERIBIT_TESTNET_CLIENT_ID=your_testnet_client_id
DERIBIT_TESTNET_CLIENT_SECRET=your_testnet_client_secret
DERIBIT_MAINNET_CLIENT_ID=your_mainnet_client_id
DERIBIT_MAINNET_CLIENT_SECRET=your_mainnet_client_secret
EOF
```

### 策略配置文件

#### Calendar Spread配置
```yaml
# qtrade/cryptotrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml
strategy_config:
  max_positions: 3
  min_iv_spread: 0.02  # 最小IV价差 2%
  time_pairs:
    - [7, 30]    # 7天 vs 30天
    - [14, 30]   # 14天 vs 30天
    - [14, 60]   # 14天 vs 60天

risk_management:
  stop_loss_ratio: -0.30    # -30% 止损
  profit_target_ratio: 0.50  # +50% 止盈
  max_loss_per_trade: 0.05   # 单笔最大损失 5% BTC
```

#### Straddle配置
```yaml
# qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml
strategy_config:
  max_positions: 2
  min_days_to_expiry: 7
  max_days_to_expiry: 21
  min_iv_premium: 0.05  # IV > RV + 5%

delta_hedge:
  enabled: true
  delta_threshold: 0.05  # 5% Delta阈值
  hedge_instrument: "BTC-PERPETUAL"
```

## 📊 策略回测

### Calendar Spread回测

```python
from qtrade.simulate_tarde.spread_trading import backtest_strategy

# 基础回测
results = backtest_strategy(
    data_folder='data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks',
    init_btc=1.0,
    strategy_name="calendar_spread",
    enable_delta_hedge=False,
    save_folder='calendar_results'
)

# 查看结果
print(f"总收益率: {results['total_return']:.2%}")
print(f"年化收益率: {results['annual_return']:.2%}")
print(f"最大回撤: {results['max_drawdown']:.2%}")
print(f"Sharpe比率: {results['sharpe_ratio']:.2f}")
```

### Straddle回测

```python
# Straddle策略回测（含Delta对冲）
results = backtest_strategy(
    data_folder='data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks',
    init_btc=1.0,
    strategy_name="gamma_scalping_sell_straddle",
    enable_delta_hedge=True,
    delta_threshold=0.05,
    hedge_cost_bps=0.0002,  # 2bps对冲成本
    save_folder='straddle_results'
)
```

### 回测结果分析

回测完成后会生成：
- `equity_curve.png`: Equity曲线图
- `performance_metrics.json`: 详细性能指标
- `trade_log.csv`: 交易记录
- `drawdown_analysis.png`: 回撤分析图

## ⚡ 实时交易

### 基础实时交易

```python
from qtrade.cryptotrader.trading_engine.trading_engine import TradingEngine

# 创建交易引擎
trading_engine = TradingEngine(
    calendar_config_path="qtrade/cryptotrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml",
    gamma_scalping_config_path="qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml",
    env="testnet",  # 使用测试网
    max_open_calendar=2,
    max_open_gamma_scalping=1,
    enable_delta_hedge=True,
    output_folder="./trading_results_20231012"
)

# 启动交易（阻塞运行）
trading_engine.run_loop(
    check_durantion=300,  # 5分钟检查间隔
    order_type="market"   # 使用市价单
)
```

### 高级配置

```python
# 自定义风险管理参数
from qtrade.cryptotrader.trading_engine.risk_manager import RiskManager

risk_manager = RiskManager(
    max_positions=5,
    enable_delta_hedge=True,
    delta_risk_threshold=0.3,      # Delta风险阈值
    delta_hedge_threshold=0.05,    # Delta对冲阈值
    stop_loss_ratio=-0.25,         # -25% 止损
    profit_target_ratio=0.40,      # +40% 止盈
    price_change_risk_ratio=0.12   # 12% 价格变化风险
)

# 使用自定义风险管理器
trading_engine.risk_manager = risk_manager
```

### 多线程架构

实时交易引擎包含3个独立线程：

1. **主交易线程**
   - 机会发现和排序
   - 订单执行
   - 持仓管理

2. **风险监控线程**
   - 实时Greeks更新
   - 平仓条件检查
   - Delta对冲执行

3. **P&L记录线程**
   - 账户equity监控
   - 曲线图生成
   - 交易记录

## 🛡️ 风险管理

### 多层风险控制

#### 1. 基础止损止盈
```python
# 在RiskManager中设置
stop_loss_ratio = -0.30     # -30% 止损
profit_target_ratio = 0.50  # +50% 止盈
```

#### 2. IV反转检测
```python
# Straddle策略IV反转逻辑
if avg_iv_change < -0.10:  # 平均IV下降10%
    return True, "IV大幅下降获利平仓"

if single_leg_iv_change > 0.10:  # 单腿IV上升10%
    return True, "IV剧烈上升风险平仓"
```

#### 3. 时间衰减保护
```python
# Calendar Spread时间保护
if days_to_short_expiry <= 0:
    return True, "短期期权到期强制平仓"

# Straddle时间保护  
if days_to_expiry <= 1:
    return True, "临近到期强制平仓"
```

#### 4. Delta风险控制
```python
# 自动Delta对冲
if abs(net_delta) > delta_risk_threshold:
    hedge_size = -net_delta
    hedge_action(hedge_size, order_type="market")
```

### 风险参数调优

| 参数 | 保守 | 平衡 | 激进 |
|------|------|------|------|
| stop_loss_ratio | -20% | -30% | -40% |
| profit_target_ratio | +30% | +50% | +70% |
| delta_risk_threshold | 0.2 | 0.3 | 0.5 |
| price_change_risk_ratio | 8% | 12% | 20% |

## 📈 监控和分析

### 实时监控

交易引擎运行时会实时输出：

```
🔍 [2023-10-12 14:30:00] 开始持仓监控...
📊 当前持仓: Straddle=1, Calendar=2
✅ Straddle持仓 straddle_001: 继续持有 (P&L: +15.2%, 0.00152 BTC)
⚠️ Calendar持仓 calendar_001 需要平仓: IV价差反转平仓
📊 [2023-10-12 14:30:15] Equity记录:
   当前Equity: 1.00234 BTC
   相对P&L: +0.00234 BTC (+0.23%)
```

### 输出文件分析

#### 1. Equity曲线图
```
trading_results/charts/equity_curve_20231012.png
```
- 上图：相对P&L (BTC)
- 下图：相对P&L百分比

#### 2. P&L数据文件
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

#### 3. 平仓记录
```
=== POSITION CLOSE RECORD ===
Time: 2023-10-12 14:35:22
Position Type: Calendar Spread
Close Reason: IV价差反转平仓 (入场: +2.1% → 当前: -0.8%)
P&L Information:
  Unrealized P&L: +0.00156 BTC
  P&L Ratio: +12.4%
Environment: testnet
```

### 性能分析工具

```python
# 分析P&L历史数据
import json
import pandas as pd
import matplotlib.pyplot as plt

# 加载数据
with open('trading_results/logs/pnl_data.json', 'r') as f:
    data = json.load(f)

# 转换为DataFrame
df = pd.DataFrame(data['history'])
df['datetime'] = pd.to_datetime(df['datetime'])
df.set_index('datetime', inplace=True)

# 计算统计指标
returns = df['relative_pnl'].pct_change().dropna()
sharpe_ratio = returns.mean() / returns.std() * np.sqrt(365*24*4)  # 15分钟数据年化
max_drawdown = (df['relative_pnl'] / df['relative_pnl'].cummax() - 1).min()

print(f"Sharpe比率: {sharpe_ratio:.2f}")
print(f"最大回撤: {max_drawdown:.2%}")

# 绘制详细分析图
fig, axes = plt.subplots(2, 2, figsize=(15, 10))

# Equity曲线
axes[0,0].plot(df.index, df['relative_pnl'])
axes[0,0].set_title('Equity Curve')
axes[0,0].set_ylabel('Relative P&L (BTC)')

# 回撤图
drawdown = df['relative_pnl'] / df['relative_pnl'].cummax() - 1
axes[0,1].fill_between(df.index, drawdown, 0, alpha=0.3, color='red')
axes[0,1].set_title('Drawdown')
axes[0,1].set_ylabel('Drawdown (%)')

# 收益分布
axes[1,0].hist(returns, bins=50, alpha=0.7)
axes[1,0].set_title('Returns Distribution')
axes[1,0].set_xlabel('Daily Returns')

# 滚动Sharpe比率
rolling_sharpe = returns.rolling(window=96).apply(
    lambda x: x.mean() / x.std() * np.sqrt(365*24*4)
)
axes[1,1].plot(rolling_sharpe.index, rolling_sharpe)
axes[1,1].set_title('Rolling Sharpe Ratio (24h)')
axes[1,1].set_ylabel('Sharpe Ratio')

plt.tight_layout()
plt.savefig('trading_results/charts/detailed_analysis.png', dpi=300)
plt.show()
```

## ❓ 常见问题

### Q1: 如何切换到主网交易？

```python
# 确保已配置主网API密钥
trading_engine = TradingEngine(
    # ... 其他参数
    env="mainnet"  # 改为mainnet
)
```

⚠️ **警告**: 主网交易涉及真实资金，请先在测试网充分验证策略。

### Q2: 如何调整检查频率？

```python
# 更频繁的检查（2分钟）
trading_engine.run_loop(check_durantion=120)

# 不太频繁的检查（10分钟）
trading_engine.run_loop(check_durantion=600)
```

**建议**: 5分钟是平衡延迟和API限制的好选择。

### Q3: 如何处理网络中断？

交易引擎具有自动重连机制：
- API调用失败时自动重试
- 网络中断时暂停交易，恢复后继续
- 所有状态持久化到本地文件

### Q4: 如何备份交易数据？

```bash
# 定期备份结果文件夹
tar -czf trading_backup_$(date +%Y%m%d).tar.gz trading_results/

# 或使用rsync同步到远程服务器
rsync -av trading_results/ user@backup-server:/backups/trading/
```

### Q5: 如何监控多个策略？

```python
# 创建多个交易引擎实例
engines = []

for i in range(3):
    engine = TradingEngine(
        # ... 配置参数
        output_folder=f"./trading_results_strategy_{i}",
        max_open_calendar=1,  # 每个实例持仓更少
        max_open_gamma_scalping=1
    )
    engines.append(engine)

# 在不同进程中运行
import multiprocessing

def run_engine(engine):
    engine.run_loop()

processes = []
for engine in engines:
    p = multiprocessing.Process(target=run_engine, args=(engine,))
    p.start()
    processes.append(p)

# 等待所有进程
for p in processes:
    p.join()
```

### Q6: 如何优化策略参数？

1. **使用回测进行参数扫描**
```python
# 参数网格搜索
stop_loss_ratios = [-0.20, -0.25, -0.30, -0.35]
profit_target_ratios = [0.30, 0.40, 0.50, 0.60]

best_sharpe = -999
best_params = None

for stop_loss in stop_loss_ratios:
    for profit_target in profit_target_ratios:
        results = backtest_strategy(
            # ... 其他参数
            stop_loss_ratio=stop_loss,
            profit_target_ratio=profit_target
        )
        
        if results['sharpe_ratio'] > best_sharpe:
            best_sharpe = results['sharpe_ratio']
            best_params = (stop_loss, profit_target)

print(f"最佳参数: 止损={best_params[0]}, 止盈={best_params[1]}")
```

2. **A/B测试**
```python
# 同时运行两个不同参数的策略
engine_conservative = TradingEngine(
    # ... 保守参数
    output_folder="./results_conservative"
)

engine_aggressive = TradingEngine(
    # ... 激进参数  
    output_folder="./results_aggressive"
)
```

## 🚀 进阶使用

### 自定义策略

```python
from qtrade.cryptotrader.arbitrage_searcher.base_strategy import BaseStrategy

class CustomStrategy(BaseStrategy):
    def check_opportunities(self):
        # 实现自定义机会发现逻辑
        pass
    
    def calculate_signal_strength(self, opportunity):
        # 实现自定义信号强度计算
        pass

# 集成到交易引擎
trading_engine.add_custom_strategy(CustomStrategy())
```

### 实时通知

```python
import requests

def send_notification(message):
    # 发送到Slack/Discord/邮件
    webhook_url = "your_webhook_url"
    requests.post(webhook_url, json={"text": message})

# 在平仓时发送通知
def on_position_close(position, reason, pnl):
    message = f"平仓通知: {position.symbol}, 原因: {reason}, P&L: {pnl:.4f} BTC"
    send_notification(message)

trading_engine.on_position_close = on_position_close
```

### 数据库集成

```python
import sqlite3

# 创建数据库连接
conn = sqlite3.connect('trading_history.db')

# 创建表
conn.execute('''
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    strategy TEXT,
    action TEXT,
    symbol TEXT,
    pnl REAL,
    reason TEXT
)
''')

# 记录交易到数据库
def log_trade_to_db(trade_info):
    conn.execute('''
    INSERT INTO trades (timestamp, strategy, action, symbol, pnl, reason)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', trade_info)
    conn.commit()
```

---

## 📞 支持

如果遇到问题或需要帮助：

1. 查看 [常见问题](#常见问题) 部分
2. 检查日志文件中的错误信息
3. 确认网络连接和API密钥配置
4. 在测试网环境下验证配置

**记住**: 期权交易涉及高风险，请务必先在测试环境中充分验证策略，再考虑实盘交易。

