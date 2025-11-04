# OKX RiskManager 完整风控逻辑流程图

## 📊 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    OKX RiskManager                          │
│                  (自动化风险管理系统)                         │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   持仓管理            风险监控              交易执行
  (Position)         (Monitor)            (Execution)
```

---

## 1️⃣ 初始化阶段

```
用户启动
    │
    ▼
创建 RiskManager
    │
    ├─ 设置参数
    │   ├─ max_positions: 2           (最大持仓数)
    │   ├─ stop_loss_ratio: -0.3      (止损 -30%)
    │   ├─ profit_target_ratio: 0.5   (止盈 +50%)
    │   ├─ delta_hedge_threshold: 0.05 (Delta对冲阈值)
    │   └─ delta_risk_threshold: 0.5   (Delta风险阈值)
    │
    ├─ 初始化 OKX 客户端
    │   ├─ OKXOptionsClient (期权交易)
    │   └─ OKX Perp API (永续对冲)
    │
    └─ 初始化波动率跟踪器
        └─ RealDataEWMAVolTracker (实时计算RV)
```

---

## 2️⃣ 持仓添加流程

```
策略发现机会
(Calendar Spread / Straddle)
    │
    ▼
调用 add_position(opportunity)
    │
    ├─ 检查持仓数量
    │   │
    │   ├─ 未满额 ──▶ 继续
    │   │
    │   └─ 已满额 ──▶ ❌ 拒绝添加
    │
    ├─ 检查重复持仓
    │   │
    │   ├─ 不重复 ──▶ 继续
    │   │
    │   └─ 重复 ──▶ ❌ 拒绝添加
    │
    └─ 添加到持仓容器
        │
        ├─ Straddle ──▶ straddle_positions
        │
        └─ Calendar ──▶ calendar_spread_positions
```

---

## 3️⃣ 核心监控循环 (monitor_positions)

```
启动监控线程
    │
    ▼
┌─────────────────────────── 无限循环 ─────────────────────────┐
│                                                              │
│  ① 获取实现波动率 (Realized Volatility)                       │
│     │                                                        │
│     ▼                                                        │
│  ② 调用 update_positions(realized_vol)                      │
│     │                                                        │
│     ├─ 更新所有Straddle持仓                                  │
│     │   │                                                    │
│     │   ├─ 更新Greeks (Delta/Gamma/Vega/Theta)             │
│     │   ├─ 计算 Net Delta                                   │
│     │   ├─ 检查 Delta风险阈值                               │
│     │   └─ 调用 check_close_condition()                     │
│     │       │                                                │
│     │       ├─ 需要平仓? ──▶ close_positions() ──▶ 从容器移除 │
│     │       │                                                │
│     │       └─ 不需要 ──▶ 累加到 total_net_delta            │
│     │                                                        │
│     └─ 更新所有Calendar持仓 (同上)                           │
│         │                                                    │
│         └─ 返回 total_net_delta                             │
│                                                              │
│  ③ Delta对冲决策                                            │
│     │                                                        │
│     ├─ 计算对冲需求                                          │
│     │   hedge_delta_diff = -total_net_delta - current_hedged│
│     │                                                        │
│     ├─ 判断是否需要对冲                                      │
│     │   │                                                    │
│     │   ├─ |hedge_delta_diff| > threshold ──▶ 执行对冲      │
│     │   │   │                                                │
│     │   │   ├─ 市价单: BTC-USD-SWAP / ETH-USD-SWAP         │
│     │   │   └─ 更新 current_hedged_delta                    │
│     │   │                                                    │
│     │   └─ 否则 ──▶ 跳过对冲                                │
│     │                                                        │
│  ④ 休眠 (默认5分钟)                                          │
│     │                                                        │
│     └─────────────────── 继续循环 ──────────────────────────│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 4️⃣ 平仓条件检查详细流程

### A. Straddle 策略 (_check_straddle_close_condition)

```
获取当前 P&L
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  ① 止损/止盈检查                                        │
│                                                         │
│     current_pnl_ratio ≤ -30%? ──▶ ✅ 触发止损          │
│     current_pnl_ratio ≥ +50%? ──▶ ✅ 触发止盈          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  ② IV反转检查 (对卖方不利)                             │
│                                                         │
│     获取开仓时IV: call_entry_iv, put_entry_iv          │
│     获取当前IV:   call_current_iv, put_current_iv      │
│                                                         │
│     call_iv_change = (current - entry) / entry         │
│     put_iv_change  = (current - entry) / entry         │
│                                                         │
│     IV上升 > 30%? ──▶ ✅ IV剧烈上升，平仓             │
│                      (不利于期权卖方)                   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  ③ 价格变化检查 (方向性风险)                            │
│                                                         │
│     获取开仓时现货价: entry_spot_price                  │
│     获取当前现货价:   current_spot_price                │
│                                                         │
│     price_change = |current - entry| / entry           │
│                                                         │
│     价格变化 > 15%? ──▶ ✅ 价格偏离过大，平仓          │
│                         (ATM变成ITM/OTM)               │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  ④ 时间衰减保护                                         │
│                                                         │
│     剩余天数 = min(call.days, put.days)                │
│                                                         │
│     剩余天数 ≤ 1天? ──▶ ✅ 临近到期，平仓              │
│                         (避免到期风险)                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### B. Calendar Spread 策略 (_check_calendar_close_condition)

```
获取当前 P&L
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  ① 止损/止盈检查 (同Straddle)                          │
│                                                         │
│     current_pnl_ratio ≤ -30%? ──▶ ✅ 触发止损          │
│     current_pnl_ratio ≥ +50%? ──▶ ✅ 触发止盈          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  ② IV价差反转检查 (策略核心)                           │
│                                                         │
│     short_iv = 短期期权IV                               │
│     long_iv  = 长期期权IV                               │
│                                                         │
│     iv_spread = short_iv - long_iv                     │
│                                                         │
│     Calendar依赖: short_iv > long_iv                   │
│                                                         │
│     ┌─ iv_spread ≤ 0? ──▶ ✅ IV价差反转，平仓         │
│     │                     (策略失效)                    │
│     │                                                   │
│     └─ iv_spread < 2%? ──▶ ✅ IV价差过小，平仓        │
│                             (利润空间不足)             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  ③ 时间衰减保护                                         │
│                                                         │
│     short_days_to_expiry ≤ 2天? ──▶ ✅ 短期到期，平仓  │
│                                     (避免流动性风险)    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 5️⃣ 平仓执行流程

```
触发平仓条件
    │
    ▼
close_positions(position, reason)
    │
    ├─ Straddle 平仓
    │   │
    │   ├─ 买回 Call (市价单, reduce_only=True)
    │   │   └─ place_market_order_crypto_notional()
    │   │
    │   └─ 买回 Put  (市价单, reduce_only=True)
    │       └─ place_market_order_crypto_notional()
    │
    └─ Calendar Spread 平仓
        │
        ├─ 买回 Short Option (市价单)
        │   └─ place_market_order_crypto_notional()
        │
        └─ 卖出 Long Option  (市价单)
            └─ place_market_order_crypto_notional()
```

---

## 6️⃣ Delta对冲流程

```
检测到 |Net Delta| > threshold
    │
    ▼
hedge_action(delta_diff, instrument)
    │
    ├─ Delta > 0 (多头风险)
    │   │
    │   └─ 做空永续 (卖出 BTC-USD-SWAP)
    │       └─ place_inverse_perp_order_with_btc_notional()
    │
    └─ Delta < 0 (空头风险)
        │
        └─ 做多永续 (买入 BTC-USD-SWAP)
            └─ place_inverse_perp_order_with_btc_notional()
```

---

## 7️⃣ 完整数据流图

```
┌──────────────────────────────────────────────────────────┐
│                    策略层                                 │
│  (CalendarSpreadManager / GammaScalpingManager)         │
└────────────────────┬─────────────────────────────────────┘
                     │ 发现机会
                     ▼
┌──────────────────────────────────────────────────────────┐
│                 RiskManager                              │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  持仓容器                                        │   │
│  │  - straddle_positions                           │   │
│  │  - calendar_spread_positions                    │   │
│  └─────────────────────────────────────────────────┘   │
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │  监控循环 (monitor_positions)                    │   │
│  │                                                  │   │
│  │  每5分钟:                                        │   │
│  │  1. update_positions()                          │   │
│  │  2. check_close_condition()                     │   │
│  │  3. hedge_action()                              │   │
│  └─────────────────────────────────────────────────┘   │
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │  风险检查                                        │   │
│  │  - 止损/止盈                                     │   │
│  │  - IV反转                                        │   │
│  │  - 价格变化                                      │   │
│  │  - 时间衰减                                      │   │
│  │  - Delta风险                                     │   │
│  └─────────────────────────────────────────────────┘   │
└────────────────────┬─────────────────────────────────────┘
                     │ 交易指令
                     ▼
┌──────────────────────────────────────────────────────────┐
│                  OKX 交易层                              │
│                                                          │
│  ┌──────────────────┐       ┌──────────────────┐       │
│  │  期权交易        │       │  永续对冲        │       │
│  │  OKXOptionsClient│       │  OKX Perp API    │       │
│  │                  │       │                  │       │
│  │  - 市价单        │       │  - 市价单        │       │
│  │  - 限价单        │       │  - 限价单        │       │
│  │  - 平仓          │       │  - Delta对冲     │       │
│  └──────────────────┘       └──────────────────┘       │
└──────────────────────────────────────────────────────────┘
```

---

## 8️⃣ 关键参数配置

```python
# 风险参数
stop_loss_ratio: -0.3          # 止损: -30%
profit_target_ratio: 0.5       # 止盈: +50%
delta_hedge_threshold: 0.05    # Delta对冲阈值: 0.05 BTC
delta_risk_threshold: 0.5      # Delta风险阈值: 0.5 BTC
price_change_risk_ratio: 0.15  # 价格变化风险: 15%

# 时间参数
check_duration: "5min"         # 监控间隔: 5分钟
realized_vol_level: "30m"      # 波动率计算周期: 30分钟

# 持仓限制
max_positions: 2               # 最大持仓数: 2
```

---

## 9️⃣ 风险等级与响应

```
┌────────────────────────────────────────────────────────┐
│  风险等级           条件              响应              │
├────────────────────────────────────────────────────────┤
│  🟢 安全      |Delta| < 0.05      继续持有              │
│  🟡 警告      |Delta| > 0.05      执行对冲              │
│  🟠 风险      |Delta| > 0.5       强制平仓              │
│  🔴 止损      P&L ≤ -30%          立即平仓              │
│  🟢 止盈      P&L ≥ +50%          锁定利润              │
│  🟠 IV反转    IV变化 > 30%        平仓保护              │
│  🔴 到期      剩余 ≤ 1天          强制平仓              │
└────────────────────────────────────────────────────────┘
```

---

## 🎯 总结

**OKX RiskManager 核心三要素：**

1. **实时监控** - 每5分钟更新Greeks和P&L
2. **智能平仓** - 多维度风险检查（P&L/IV/价格/时间）
3. **自动对冲** - Delta中性策略，永续合约对冲

**特点：**
- ✅ 全自动化运行
- ✅ 多策略支持 (Straddle + Calendar)
- ✅ 实时风险监控
- ✅ 智能平仓决策
- ✅ Delta中性对冲
- ✅ 完整的日志记录

---

**这就是完整的 OKX RiskManager 风控逻辑！** 🚀

