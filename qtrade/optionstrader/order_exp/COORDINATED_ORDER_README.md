# Calendar Spread 协同下单策略

## 📋 策略概述

这是一个智能的Calendar Spread双腿协同下单策略，旨在最小化滑点成本并避免单腿暴露风险。

### 🎯 核心优势

1. **降低成本**：两腿都尽量以被动限价单成交，避免市价单的高滑点
2. **风险控制**：避免单腿成交后另一腿挂单未成交的风险敞口
3. **快速响应**：任一腿触发后，立即处理另一腿
4. **简洁实现**：基于轮询机制，无需复杂的WebSocket订阅

## 🔄 策略流程

```
1. 准备阶段
   ├─ 获取Calendar Spread机会
   ├─ 计算两腿的挂单价格（略优于盘口）
   └─ 计算合约数量（crypto notional → contracts）

2. 挂单阶段
   ├─ 同时挂出两腿被动限价单
   │  ├─ Short腿：卖单挂在 ask - offset
   │  └─ Long腿：买单挂在 bid + offset
   └─ 记录订单ID

3. 监控阶段（轮询）
   ├─ 定期查询两腿订单状态
   ├─ 检查成交比例是否达到触发阈值
   └─ 任一腿触发 → 进入收尾阶段

4. 收尾阶段
   ├─ 立即撤销输家订单
   ├─ 查询剩余数量
   └─ 用市价单强制成交剩余数量

结果：
✅ 大概率两腿都以被动价成交
✅ 避免单腿暴露风险
✅ 总执行时间可控
```

## 📊 数据结构

### CalendarSpreadOpportunity
```python
@dataclass
class CalendarSpreadOpportunity:
    rank: int
    short_option: OptionData  # 卖出的短期期权
    long_option: OptionData   # 买入的长期期权
    iv_spread: float          # IV价差
    time_gap_days: int        # 时间间隔（天）
    net_premium: float        # 净保险费
    signal_strength: str      # 信号强度
```

### OrderStatus
```python
@dataclass
class OrderStatus:
    ord_id: str         # 订单ID
    inst_id: str        # 合约ID
    side: str           # buy/sell
    sz: int             # 合约数量
    filled_sz: int      # 已成交数量
    avg_px: float       # 平均成交价
    state: str          # live/filled/canceled
```

## 🚀 使用方法

### 方式1: 直接运行测试脚本

```bash
cd /home/ubuntu/options_trading
python qtrade/optionstrader/order_placer.py
```

**交互流程**：
1. 自动获取ETH Calendar Spread机会
2. 显示最佳交易机会
3. 确认交易参数（数量、环境）
4. 输入确认后执行协同下单

### 方式2: 在代码中调用

```python
from qtrade.optionstrader.order_placer import (
    get_calendar_spread_opportunity,
    execute_calendar_spread_trade
)

# 1. 获取交易机会
opportunity = get_calendar_spread_opportunity(
    config_path="/path/to/calendar_spread.yaml",
    currency="ETH",
    show_details=False
)

# 2. 执行协同下单
result = execute_calendar_spread_trade(
    opportunity=opportunity,
    crypto_notional=0.1,      # 0.1 ETH
    simulated=True,           # 模拟盘
    price_offset=0.0001,      # 价格偏移
    poll_interval=0.5         # 轮询间隔0.5秒
)
```

### 方式3: 使用协调器类（高级）

```python
from qtrade.optionstrader.coordinated_order_placer import CalendarSpreadCoordinator
from qtrade.order_api.okx.client.options_client import OKXOptionsClient

client = OKXOptionsClient(simulated=True)

coordinator = CalendarSpreadCoordinator(
    client=client,
    opportunity=opportunity,
    crypto_notional=0.1,
    price_offset=0.0001,
    poll_interval=0.5,
    cancel_timeout=3.0,
    trigger_ratio=1.0  # 1.0=完全成交才触发，0.5=半仓触发
)

result = coordinator.execute()
```

## ⚙️ 参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `crypto_notional` | float | - | 交易数量（币本位，如0.1 ETH） |
| `price_offset` | float | 0.0001 | 相对盘口的价格偏移 |
| `poll_interval` | float | 0.5 | 轮询间隔（秒） |
| `cancel_timeout` | float | 3.0 | 撤单超时（秒） |
| `trigger_ratio` | float | 1.0 | 触发比率（0-1，1.0表示完全成交） |
| `simulated` | bool | True | 是否模拟盘 |

## 📈 执行示例输出

```
======================================================================
🎯 [Calendar Spread] 开始协同下单
======================================================================
📊 交易对:
   Short (卖出): ETH-USD-251114-3400-P
   Long (买入):  ETH-USD-251226-3400-P
   数量: 0.1 ETH
   策略: 被动挂单 + 触发跟随

📝 挂单价格:
   Short: 0.0356 ETH (sz=1)
   Long:  0.0888 ETH (sz=1)

📤 挂出Short腿...
   ✅ Short订单已挂出: 123456789

📤 挂出Long腿...
   ✅ Long订单已挂出: 987654321

✅ 两腿订单挂出完成，开始监控...

🔍 监控订单状态（轮询间隔: 0.5秒）...
   📊 Short: 0.0% | Long: 0.0%
   📊 Short: 0.0% | Long: 0.0%

🎉 Long腿触发！(成交: 1/1)

======================================================================
⚡ 开始收尾: 撤销Short腿 + 市价成交
======================================================================
📋 撤销Short腿订单...
   ✅ 撤单完成 (耗时: 0.15秒)

💥 市价成交Short腿剩余数量: 1 contracts
   ✅ 市价单已提交: 555555555

======================================================================
✅ Calendar Spread协同下单完成
======================================================================
⏱️  总耗时: 5.32秒
⚡ 触发后处理: 0.87秒
🏆 触发腿: LONG
📊 Short腿: 1/1 @ 0.0356
📊 Long腿:  1/1 @ 0.0888

🎉 交易执行成功！
   总耗时: 5.32秒
   触发腿: LONG
```

## 🔧 高级配置

### 调整触发策略

```python
# 完全成交才触发（保守）
coordinator = CalendarSpreadCoordinator(
    ...,
    trigger_ratio=1.0
)

# 80%成交就触发（激进）
coordinator = CalendarSpreadCoordinator(
    ...,
    trigger_ratio=0.8
)
```

### 调整价格策略

```python
# 更激进的挂单（更接近盘口）
coordinator = CalendarSpreadCoordinator(
    ...,
    price_offset=0.0002  # 提高成交概率但profit稍差
)

# 更保守的挂单（离盘口更远）
coordinator = CalendarSpreadCoordinator(
    ...,
    price_offset=0.00005  # 更好的profit但成交概率低
)
```

## 🛡️ 风险管理

1. **保证金检查**：下单前确保账户有足够的保证金
2. **市场流动性**：确认盘口深度足够，避免滑点过大
3. **触发超时**：如果长时间未触发，可以手动取消
4. **错误处理**：异常情况下会自动撤销所有挂单

## 🚨 注意事项

1. **测试环境**：首次使用请在模拟盘测试
2. **轮询间隔**：不要设置太短（<0.2秒），避免API限流
3. **撤单时机**：撤单+市价单有时间窗口，可能有少量双成交风险
4. **网络延迟**：网络不稳定时可能影响执行效率

## 📚 相关文件

- `coordinated_order_placer.py` - 协调器核心实现
- `order_placer.py` - 测试和执行脚本
- `options_client.py` - OKX API封装
- `calendar_spread_finder.py` - 机会搜索

## 🔄 后续优化方向

1. ✅ **WebSocket支持**：用WS推送替代轮询，响应更快
2. ✅ **动态调价**：被动单长时间不成交时自动调整价格
3. ✅ **部分成交策略**：支持部分成交后的风控逻辑
4. ✅ **多腿扩展**：支持Iron Condor等4腿策略
5. ✅ **性能监控**：记录执行时间、滑点等指标

---

**作者**: Options Trading Team  
**版本**: 1.0.0  
**最后更新**: 2025-11-04

