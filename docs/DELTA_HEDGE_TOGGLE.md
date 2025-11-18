# Delta对冲开关功能说明

## 📌 功能概述

`OKXRiskManager` 现在支持通过 `enable_delta_hedge` 参数控制是否启用Delta对冲功能。

---

## ⚙️ 使用方法

### 1️⃣ **禁用Delta对冲（纯期权策略）**

```python
from qtrade.optionstrader.trading_engine.okx_engine.okx_risk_manager import OKXRiskManager

# 创建不启用对冲的Risk Manager
risk_manager = OKXRiskManager(
    symbol="ETHUSDT",
    max_positions=3,
    enable_delta_hedge=False,  # ❌ 不启用对冲
    env="mainnet"
)
```

**行为**：
- ✅ 正常监控期权持仓
- ✅ 正常执行止损/止盈
- ✅ 正常计算Net Delta（仅用于监控）
- ❌ **不会执行永续合约对冲**
- ❌ **不会清理孤立的永续合约仓位**

**日志输出**：
```
📊 [MainThread] 持仓状态: Calendar=1, Straddle=0
⏭️ [OKX] Delta对冲已禁用 (当前Net Delta=-0.0509)
```

---

### 2️⃣ **启用Delta对冲（对冲策略）**

```python
from qtrade.optionstrader.trading_engine.okx_engine.okx_risk_manager import OKXRiskManager

# 创建启用对冲的Risk Manager
risk_manager = OKXRiskManager(
    symbol="ETHUSDT",
    max_positions=3,
    enable_delta_hedge=True,   # ✅ 启用对冲
    delta_hedge_threshold=0.1, # Delta对冲阈值（0.1 ETH）
    env="mainnet"
)
```

**行为**：
- ✅ 正常监控期权持仓
- ✅ 正常执行止损/止盈
- ✅ 计算Net Delta并执行对冲
- ✅ **当 |Net Delta + Hedged Delta| > threshold 时执行对冲**
- ✅ **当无期权持仓时，自动清理所有永续合约仓位**

**日志输出**：
```
📊 [MainThread] 持仓状态: Calendar=1, Straddle=0
📊 [OKX] 执行Delta对冲: 0.0509
✅ [OKX] 永续合约对冲订单成功 - OrderID: 123456789
```

---

## 🔍 核心逻辑修改

### **监控循环中的对冲逻辑**

```python
# 只在启用对冲时执行
if self.enable_delta_hedge:
    hedge_delta_diff = -total_net_delta - self.current_hedged_delta
    
    if abs(hedge_delta_diff) > self.delta_hedge_threshold:
        self.logger.info(f"📊 [OKX] 执行Delta对冲: {hedge_delta_diff:.4f}")
        instrument = "BTC-USD-SWAP" if "BTC" in self.realize_vol_extracter.symbol else "ETH-USD-SWAP"
        self.hedge_action(hedge_delta_diff, instrument, "market", None, self.env)
        self.current_hedged_delta = -total_net_delta
    else:
        self.logger.debug(f"✅ [OKX] Delta在安全范围内 (Δ差异={hedge_delta_diff:.4f} < 阈值={self.delta_hedge_threshold})")
else:
    self.logger.debug(f"⏭️ [OKX] Delta对冲已禁用 (当前Net Delta={total_net_delta:.4f})")
```

### **孤立永续合约清理逻辑**

```python
# 只在启用对冲时检查
total_option_positions = len(self.straddle_positions) + len(self.calendar_spread_positions)
if total_option_positions == 0:
    if self.enable_delta_hedge:
        self.logger.info("📊 [MainThread] 当前无期权持仓，检查永续合约仓位...")
        self._cleanup_orphan_perp_positions()
    else:
        self.logger.debug("⏭️ [MainThread] 当前无期权持仓且未启用对冲，跳过永续合约检查")
```

---

## 📊 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_delta_hedge` | `bool` | `False` | 是否启用Delta对冲 |
| `delta_hedge_threshold` | `float` | `0.05` | Delta对冲阈值（只有 `enable_delta_hedge=True` 时生效）|
| `delta_risk_threshold` | `float` | `0.5` | Delta风险阈值（用于监控警告）|
| `hedge_freq` | `int` | `5` | 对冲频率（监控周期的倍数，例如5表示每5个监控周期执行一次对冲检查）|

---

## ⏱️ 对冲频率控制

### **为什么需要 `hedge_freq`？**

Delta对冲不需要在每个监控周期都执行，过于频繁的对冲会导致：
1. 💸 **手续费成本高**：每次对冲都需要支付交易手续费
2. ⚠️ **滑点损失**：频繁交易导致更多滑点
3. 📊 **API限流**：过多请求可能触发交易所限流

通过 `hedge_freq` 参数，可以降低对冲频率，优化成本。

### **如何设置 `hedge_freq`？**

```python
# 示例1: 监控周期为1分钟，每5分钟对冲一次
risk_manager = OKXRiskManager(
    symbol="ETHUSDT",
    enable_delta_hedge=True,
    hedge_freq=5,  # 每5个监控周期（5分钟）检查一次对冲
    env="mainnet"
)
# 启动监控（check_duration="1min"）
risk_manager.monitor_positions(check_duration="1min")
# → 实际对冲频率: 每5分钟

# 示例2: 监控周期为5分钟，每30分钟对冲一次
risk_manager = OKXRiskManager(
    symbol="ETHUSDT",
    enable_delta_hedge=True,
    hedge_freq=6,  # 每6个监控周期（30分钟）检查一次对冲
    env="mainnet"
)
# 启动监控（check_duration="5min"）
risk_manager.monitor_positions(check_duration="5min")
# → 实际对冲频率: 每30分钟
```

### **对冲频率计算**

```
实际对冲间隔时间 = check_duration × hedge_freq
```

**示例**：
- `check_duration="1min"`, `hedge_freq=5` → 每5分钟对冲
- `check_duration="1min"`, `hedge_freq=10` → 每10分钟对冲
- `check_duration="5min"`, `hedge_freq=3` → 每15分钟对冲

### **日志输出**

```
# 初始化时显示对冲频率
✅ [OKX] RiskManager 初始化完成
   环境: 实盘
   最大持仓: 3
   Delta对冲: 启用
   对冲频率: 每 5 个监控周期

# 监控循环中的计数器日志
⏭️ [OKX] 对冲计数器: 1/5 (下次对冲周期还需 4 个监控周期)
⏭️ [OKX] 对冲计数器: 2/5 (下次对冲周期还需 3 个监控周期)
...
📊 [OKX] 执行Delta对冲: 0.0509
```

---

## 🎯 使用场景

### **场景1：纯期权策略（不对冲）**
- Calendar Spread策略（赚取时间价值差）
- Straddle策略（赌波动率）
- 不需要Delta中性
- **设置**: `enable_delta_hedge=False`

### **场景2：Delta中性策略（对冲）**
- Market Making
- 卖出期权并对冲Delta风险
- 需要保持Delta中性
- **设置**: `enable_delta_hedge=True`

---

## ⚠️ 注意事项

1. **默认不启用对冲**：为了安全，默认 `enable_delta_hedge=False`
2. **对冲需要永续合约权限**：如果启用对冲，确保API Key有永续合约交易权限
3. **实盘/模拟盘一致性**：对冲操作会根据 `env` 参数自动切换实盘/模拟盘
4. **永续合约清理**：只有启用对冲时才会自动清理孤立的永续合约仓位

---

## ✅ 测试验证

```bash
cd /home/ubuntu/options_trading
python -c "
from qtrade.optionstrader.trading_engine.okx_engine.okx_risk_manager import OKXRiskManager

# 测试禁用对冲
rm_no_hedge = OKXRiskManager(symbol='ETHUSDT', enable_delta_hedge=False)
print(f'enable_delta_hedge = {rm_no_hedge.enable_delta_hedge}')  # False

# 测试启用对冲
rm_with_hedge = OKXRiskManager(symbol='ETHUSDT', enable_delta_hedge=True)
print(f'enable_delta_hedge = {rm_with_hedge.enable_delta_hedge}')  # True
"
```

---

## 📝 总结

通过 `enable_delta_hedge` 参数，你可以轻松控制Risk Manager的对冲行为：
- **不对冲**：纯期权策略，专注于IV/时间价值
- **对冲**：Delta中性策略，降低方向性风险

根据你的交易策略灵活选择！🚀

