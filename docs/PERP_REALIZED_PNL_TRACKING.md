# 永续合约 Realized P&L 追踪系统

## 概述

本系统实现了对永续合约（用于Delta对冲）的已实现盈亏（Realized P&L）的持续追踪，解决了OKX API `get_current_positions` 只返回当前持仓的 `realizedPnl`，而无法获取已完全平仓的历史P&L的问题。

## 核心特性

### 1. 增量查询机制
- **首次查询**：从指定时间（默认24小时前）开始获取所有成交记录
- **后续查询**：仅获取新增的成交记录（自动向前推5分钟避免遗漏）
- **智能去重**：使用 `tradeId` 作为唯一标识，自动过滤重复记录

### 2. 高效P&L计算
- **增量累加**：只累加新成交的P&L，避免重新遍历整个历史字典
- **算法复杂度**：从 O(n) 每次查询 → O(m) 仅新增记录
- **内存优化**：使用字典存储成交记录，支持快速查找和去重

### 3. 完整集成到 RiskManager
- **自动更新**：在 `monitor_positions` 循环中自动调用
- **实时显示**：在持仓状态汇总中显示未实现P&L、已实现P&L和总P&L
- **静默模式**：监控循环中使用静默模式，避免日志污染

## 文件结构

```
qtrade/optionstrader/trading_engine/okx_engine/
├── perp_pnl_tracker.py          # P&L追踪核心模块
└── okx_risk_manager.py          # RiskManager (集成P&L追踪)
```

## 使用示例

### 方法1：在 RiskManager 中自动追踪

```python
from qtrade.optionstrader.trading_engine.okx_engine.okx_risk_manager import OKXRiskManager

# 初始化 RiskManager（启用对冲才会追踪永续合约P&L）
risk_manager = OKXRiskManager(
    symbol="ETHUSDT",
    enable_delta_hedge=True,  # 必须启用对冲
    hedge_freq=5,
    env="mainnet"
)

# 启动监控（会自动追踪Realized P&L）
risk_manager.monitor_positions(check_duration="1min")
```

**输出示例：**
```
======================================================================
📊 持仓状态汇总
======================================================================
🎯 期权持仓:
   Combined Delta: -0.050900 ETH
   期权P&L (未实现): +0.00022768 ETH

🔒 永续合约对冲:
   已对冲Delta: +0.050000 ETH
   实际持仓Delta: +0.049500 ETH
   未实现P&L: +0.00015432 ETH
   已实现P&L: -0.00412102 ETH (累计2笔成交)
   永续合约Total: -0.00396670 ETH

💰 总P&L (期权+永续): -0.00373902 ETH
======================================================================
```

### 方法2：独立使用 P&L 追踪模块

```python
from qtrade.optionstrader.trading_engine.okx_engine.perp_pnl_tracker import get_perp_realized_pnl

# 初始化字典
perp_pnl_dict = {}
total_pnl = 0.0

# 首次查询
total_pnl, last_fill_time = get_perp_realized_pnl(
    instrument="ETH-USD-SWAP",
    start_time="2025-11-18 00:00:00",
    perp_pnl_dict=perp_pnl_dict,
    previous_realized_pnl=total_pnl,
    silent=False  # 显示详细输出
)

print(f"累积P&L: {total_pnl:+.8f} ETH")
print(f"成交记录数: {len(perp_pnl_dict)}")

# 后续增量查询（例如在循环中）
while True:
    time.sleep(60)  # 每分钟更新一次
    
    total_pnl, last_fill_time = get_perp_realized_pnl(
        instrument="ETH-USD-SWAP",
        start_time=str(last_fill_time),  # 使用上次的结束时间
        perp_pnl_dict=perp_pnl_dict,
        previous_realized_pnl=total_pnl,  # ⭐ 传入上次的P&L
        silent=True  # 生产环境使用静默模式
    )
```

## 技术细节

### 数据结构

```python
# perp_pnl_dict 结构
{
    "431365593": {  # tradeId (唯一标识)
        "orderId": "3049881955154452480",
        "side": "sell",
        "fillSz": "30",
        "fillPx": "3076.58",
        "fillPnl": -0.00341979,
        "fee": -0.00004876,
        "fillTime": "1763395965271",
        "ts": "1763395965272"
    },
    "431511006": { ... },
    ...
}
```

### API 调用

使用 OKX API `/api/v5/trade/fills-history` 获取历史成交：
- **参数**：`instId` (合约ID), `begin` (起始时间，毫秒)
- **返回**：每笔成交的详细信息，包括 `fillPnl`（已实现盈亏）
- **分页**：自动处理分页，获取所有匹配的成交记录

### 查询逻辑流程

```
┌─────────────────────────────────────────────────┐
│  perp_pnl_dict 是否为空？                        │
└────────┬────────────────────────────────────────┘
         │
    ┌────┴────┐
    │ 是      │ 否
    │         │
    ▼         ▼
┌──────┐  ┌────────────────────────────┐
│使用   │  │ 获取最后一笔成交时间          │
│start_│  │ last_fill_time             │
│time  │  └────────┬───────────────────┘
└───┬──┘           │
    │              ▼
    │    ┌─────────────────────────┐
    │    │ 向前推5分钟              │
    │    │ safe_start = last - 5min│
    │    └────────┬────────────────┘
    │             │
    └─────┬───────┘
          ▼
    ┌────────────────────┐
    │ 调用OKX API         │
    │ get_trade_fills     │
    └────────┬───────────┘
             ▼
    ┌────────────────────┐
    │ 去重（检查tradeId） │
    └────────┬───────────┘
             ▼
    ┌────────────────────┐
    │ 按时间排序          │
    └────────┬───────────┘
             ▼
    ┌────────────────────┐
    │ 存入perp_pnl_dict   │
    │ 累加fillPnl        │
    └────────┬───────────┘
             ▼
    ┌────────────────────┐
    │ 返回 total_pnl +    │
    │ last_fill_time     │
    └────────────────────┘
```

## RiskManager 集成细节

### 初始化变量

```python
# 在 __init__ 中添加
self.perp_pnl_dict = {}  # {tradeId: fill_data}
self.total_perp_realized_pnl = 0.0
self.last_perp_fill_time = None
```

### 监控循环中的更新

```python
# 在 monitor_positions 中
if self.enable_delta_hedge:
    # 确定查询起始时间
    if self.last_perp_fill_time is None:
        start_time = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    else:
        start_time = str(self.last_perp_fill_time)
    
    # 调用增量更新
    self.total_perp_realized_pnl, self.last_perp_fill_time = get_perp_realized_pnl(
        instrument=instrument,
        start_time=start_time,
        perp_pnl_dict=self.perp_pnl_dict,
        previous_realized_pnl=self.total_perp_realized_pnl,
        silent=True
    )
```

### P&L 计算公式

```python
# 永续合约P&L
perp_unrealized_pnl = sum(pos['upl'] for pos in perp_positions)
perp_realized_pnl = self.total_perp_realized_pnl
perp_total_pnl = perp_unrealized_pnl + perp_realized_pnl

# 组合总P&L
options_pnl = sum(各期权持仓的未实现P&L)
total_pnl = options_pnl + perp_total_pnl
```

## 性能优化

### 1. 增量计算
- **旧方案**：每次查询都重新对整个字典求和
  ```python
  total_pnl = sum(data['fillPnl'] for data in perp_pnl_dict.values())  # O(n)
  ```
- **新方案**：只累加新增的P&L
  ```python
  total_pnl = previous_realized_pnl + new_pnl  # O(1)
  ```

### 2. 查询优化
- 使用 `last_fill_time - 5min` 作为起始时间
- 避免重复查询已知的历史数据
- API调用次数最小化

### 3. 去重优化
- 使用字典的 O(1) 查找特性
- `if trade_id in perp_pnl_dict:` 快速过滤重复

## 测试

### 单元测试
```bash
# 测试独立模块
python tests/test_fills_history.py

# 测试RiskManager集成
python tests/test_risk_manager_pnl_tracking.py
```

### 验证点
- ✅ 首次查询能正确获取历史成交
- ✅ 增量查询能正确识别并过滤重复记录
- ✅ P&L累加计算准确
- ✅ 静默模式不输出冗余日志
- ✅ RiskManager中P&L显示正确

## 注意事项

1. **时间单位**：OKX API使用毫秒时间戳，需要正确转换
2. **tradeId 唯一性**：一个订单可能有多个fill，每个fill有唯一的tradeId
3. **5分钟重叠**：查询时向前推5分钟是必要的，避免遗漏边界交易
4. **前提条件**：只有启用 `enable_delta_hedge=True` 时才会追踪永续合约P&L

## 维护者

- 代码位置：`qtrade/optionstrader/trading_engine/okx_engine/`
- 相关Issue：Realized P&L追踪需求
- 最后更新：2025-11-18

