# Deribit期权交易完整指南

## 📋 目录
1. [期权合约基础](#期权合约基础)
2. [市价单交易](#市价单交易)
3. [限价单交易](#限价单交易)
4. [订单撤销](#订单撤销)
5. [持仓平仓](#持仓平仓)
6. [实战示例](#实战示例)
7. [常见问题](#常见问题)

---

## 期权合约基础

### 合约规格
- **BTC期权**: 每张合约 = 1 BTC名义价值
- **ETH期权**: 每张合约 = 1 ETH名义价值
- **最小交易量**: 0.1张合约
- **价格精度**: 0.0001

### 合约命名规则
```
BTC-10OCT25-70000-C  → BTC看涨期权，2025年10月10日到期，行权价70000美元
ETH-15NOV25-4000-P   → ETH看跌期权，2025年11月15日到期，行权价4000美元
```

### 导入必要的函数
```python
from qtrade.order_api.deribit_order_placer.options_order import (
    place_options_market_order_btc_notional,  # BTC名义价值市价单
    place_options_market_order,               # 标准市价单
    place_options_limit_order,                # 限价单
    cancel_options_order,                     # 撤销单个订单
    cancel_all_options_orders,                # 撤销所有订单
    close_specific_options_position,          # 平掉指定持仓
    close_all_options_positions,              # 平掉所有持仓
    get_options_positions,                    # 查看持仓
    get_open_options_orders,                  # 查看挂单
    get_options_orderbook                     # 查看行情
)
```

---

## 市价单交易

### 方法1: BTC名义价值市价单（推荐）
```python
# 买入1张BTC期权合约（等于1 BTC名义价值）
result = place_options_market_order_btc_notional(
    instrument="BTC-10OCT25-70000-C",  # 期权合约名称
    side="buy",                        # "buy"买入 或 "sell"卖出
    contracts=1.0,                     # 合约数量（支持小数，如0.1, 0.5, 1.0）
    reduce_only=False,                 # True=只平仓，False=可开仓
    env="testnet"                      # "testnet"测试网 或 "mainnet"主网
)

# 检查结果
if result.get("success"):
    print(f"✅ 市价单成功!")
    print(f"   订单ID: {result['order_id']}")
    print(f"   合约数量: {result['contracts']}")
    print(f"   名义价值: {result['nominal_value']} BTC")
    print(f"   预估成本: {result['estimated_cost']:.4f} BTC")
    print(f"   BTC现价: ${result['spot_price']:,.2f}")
else:
    print(f"❌ 下单失败: {result['error']}")
```

### 方法2: 标准市价单
```python
# 直接指定合约数量的市价单
result = place_options_market_order(
    instrument="BTC-10OCT25-70000-C",
    side="buy",
    amount=1.0,                        # 合约数量
    reduce_only=False,
    env="testnet"
)

if result.get("success"):
    print(f"✅ 订单成功: {result['order_id']}")
    print(f"   成交数量: {result.get('filled_amount', 'N/A')}")
    print(f"   订单状态: {result.get('order_state', 'N/A')}")
else:
    print(f"❌ 下单失败: {result['error']}")
```

### 市价单特点
- ✅ **立即成交**: 按当前最优价格立即执行
- ⚠️ **价格不确定**: 成交价格可能与预期有差异
- 🎯 **适用场景**: 需要快速建仓或平仓时使用

---

## 限价单交易

### 基础限价单
```python
# 先查看当前行情
orderbook = get_options_orderbook("BTC-10OCT25-70000-C", env="testnet")

if orderbook:
    best_bid = orderbook["best_bid"]    # 最高买价
    best_ask = orderbook["best_ask"]    # 最低卖价
    mid_price = orderbook["mid_price"]  # 中间价
    
    print(f"📊 当前行情:")
    print(f"   最高买价: {best_bid:.4f}")
    print(f"   最低卖价: {best_ask:.4f}")
    print(f"   中间价格: {mid_price:.4f}")
    
    # 设置限价（例如：比最高买价高0.001）
    my_limit_price = best_bid + 0.001
    
    # 下限价单
    result = place_options_limit_order(
        instrument="BTC-10OCT25-70000-C",
        side="buy",
        amount=1.0,                     # 合约数量
        price=my_limit_price,           # 限价
        post_only=True,                 # True=只做Maker，False=可做Taker
        reduce_only=False,              # True=只平仓
        env="testnet"
    )
    
    if result.get("success"):
        order_id = result["order_id"]
        print(f"✅ 限价单已提交!")
        print(f"   订单ID: {order_id}")
        print(f"   限价: {my_limit_price:.4f}")
        print(f"   数量: 1.0 张")
        
        # 保存订单ID用于后续管理
        pending_order_id = order_id
    else:
        print(f"❌ 限价单失败: {result['error']}")
```

### 智能限价单策略
```python
def smart_limit_order(instrument, side, amount, aggressive_level=0.5):
    """
    智能限价单：根据买卖方向和激进程度自动设置价格
    
    Args:
        aggressive_level: 0.0-1.0，越大越激进（越容易成交）
    """
    orderbook = get_options_orderbook(instrument, env="testnet")
    
    if not orderbook or orderbook["best_bid"] <= 0:
        return {"success": False, "error": "无法获取行情数据"}
    
    best_bid = orderbook["best_bid"]
    best_ask = orderbook["best_ask"]
    spread = orderbook["spread"]
    
    if side == "buy":
        # 买单：在最高买价和最低卖价之间设置价格
        if best_ask > 0:
            limit_price = best_bid + (spread * aggressive_level)
        else:
            limit_price = best_bid + 0.001  # 如果没有卖价，略高于买价
    else:  # sell
        # 卖单：在最高买价和最低卖价之间设置价格
        if best_ask > 0:
            limit_price = best_ask - (spread * aggressive_level)
        else:
            limit_price = best_bid - 0.001  # 如果没有卖价，略低于买价
    
    print(f"🎯 智能定价:")
    print(f"   买价: {best_bid:.4f}, 卖价: {best_ask:.4f}")
    print(f"   价差: {spread:.4f}")
    print(f"   激进度: {aggressive_level}")
    print(f"   限价: {limit_price:.4f}")
    
    return place_options_limit_order(
        instrument=instrument,
        side=side,
        amount=amount,
        price=limit_price,
        post_only=False,  # 允许立即成交
        env="testnet"
    )

# 使用示例
result = smart_limit_order(
    instrument="BTC-10OCT25-70000-C",
    side="buy",
    amount=0.5,
    aggressive_level=0.7  # 70%激进度，较容易成交
)
```

### 限价单特点
- ✅ **价格确定**: 成交价格不会超过设定限价
- ⏳ **可能不成交**: 如果价格不合适可能无法成交
- 💰 **节省成本**: 通常能获得更好的成交价格
- 🎯 **适用场景**: 对价格敏感，不急于成交时使用

---

## 订单撤销

### 撤销单个订单
```python
# 使用之前保存的订单ID
order_id = "your_order_id_here"

result = cancel_options_order(order_id, env="testnet")

if result.get("success"):
    print(f"✅ 订单 {order_id} 已成功撤销")
else:
    print(f"❌ 撤销失败: {result['error']}")
```

### 撤销所有期权订单
```python
# 撤销所有BTC期权订单
result = cancel_all_options_orders(currency="BTC", env="testnet")

if result.get("success"):
    canceled_count = result.get("canceled_count", 0)
    print(f"✅ 成功撤销 {canceled_count} 个BTC期权订单")
else:
    print(f"❌ 批量撤销失败: {result['error']}")

# 撤销所有期权订单（BTC + ETH）
result = cancel_all_options_orders(env="testnet")  # 不指定currency

if result.get("success"):
    print(f"✅ 所有期权订单已撤销")
    print(f"   BTC订单: {result.get('btc_canceled', 0)} 个")
    print(f"   ETH订单: {result.get('eth_canceled', 0)} 个")
```

### 查看当前挂单
```python
# 查看所有挂单
orders = get_open_options_orders(env="testnet")

print(f"📝 当前挂单: {len(orders)} 个")

for order in orders:
    order_id = order.get("order_id")
    instrument = order.get("instrument_name")
    direction = order.get("direction")  # "buy" or "sell"
    amount = order.get("amount", 0)
    price = order.get("price", 0)
    
    print(f"   🆔 {order_id[:8]}...")
    print(f"      {instrument}")
    print(f"      {direction.upper()} {amount} 张 @ {price:.4f}")
    print()
```

---

## 持仓平仓

### 查看当前持仓
```python
# 查看所有期权持仓（默认过滤零持仓）
positions = get_options_positions(env="testnet")

print(f"📊 当前持仓: {len(positions)} 个")

for pos in positions:
    instrument = pos.get("instrument_name")
    size = pos.get("size", 0)
    direction = pos.get("direction")
    mark_price = pos.get("mark_price", 0)
    unrealized_pnl = pos.get("unrealized_pnl", 0)
    
    print(f"📋 {instrument}")
    print(f"   持仓: {size} 张 ({direction})")
    print(f"   标记价: {mark_price:.4f}")
    print(f"   未实现盈亏: {unrealized_pnl:.6f} BTC")
    print()

# 查看包括历史记录的所有持仓
all_positions = get_options_positions(exclude_zero_positions=False, env="testnet")
print(f"📊 总持仓记录（含历史）: {len(all_positions)} 个")
```

### 平掉指定持仓
```python
# 平掉指定合约的全部持仓
result = close_specific_options_position(
    instrument="BTC-10OCT25-70000-C",
    env="testnet"
)

if result.get("success"):
    print(f"✅ 持仓平仓成功!")
    print(f"   合约: {result['instrument']}")
    print(f"   原持仓: {result['original_size']} 张 ({result['original_direction']})")
    print(f"   平仓方向: {result['close_side']}")
    print(f"   平仓数量: {result['close_amount']} 张")
    print(f"   成交数量: {result['filled_amount']} 张")
    print(f"   订单ID: {result['order_id']}")
    
    if 'new_size' in result:
        print(f"   剩余持仓: {result['new_size']} 张")
else:
    print(f"❌ 平仓失败: {result['error']}")

# 平掉指定数量的持仓
result = close_specific_options_position(
    instrument="BTC-10OCT25-70000-C",
    size=0.5,  # 只平掉0.5张
    env="testnet"
)
```

### 平掉所有持仓
```python
# 平掉所有期权持仓
result = close_all_options_positions(env="testnet")

if result.get("success"):
    print(f"✅ 批量平仓完成!")
    print(f"   总持仓数: {result['total_positions']}")
    print(f"   成功平仓: {result['closed_count']} 个")
    print(f"   失败数量: {result['failed_count']} 个")
    
    # 显示成功平仓的详情
    if result.get('closed_positions'):
        print(f"\n✅ 成功平仓的持仓:")
        for pos in result['closed_positions']:
            print(f"   - {pos['instrument']}: {pos['original_direction']} {abs(pos['original_size'])} 张")
    
    # 显示失败的详情
    if result.get('failed_positions'):
        print(f"\n❌ 失败的持仓:")
        for pos in result['failed_positions']:
            print(f"   - {pos['instrument']}: {pos['error']}")
else:
    print(f"❌ 批量平仓失败: {result['error']}")

# 只平掉BTC期权持仓
result = close_all_options_positions(currency="BTC", env="testnet")
```

---

## 实战示例

### 完整的期权交易流程
```python
def complete_options_trading_example():
    """完整的期权交易示例"""
    
    print("🚀 期权交易完整流程演示")
    print("=" * 50)
    
    # Step 1: 查看账户状态
    print("\n📊 Step 1: 检查当前状态...")
    positions = get_options_positions(env="testnet")
    orders = get_open_options_orders(env="testnet")
    
    print(f"   当前持仓: {len(positions)} 个")
    print(f"   当前挂单: {len(orders)} 个")
    
    # Step 2: 选择交易标的
    target_instrument = "BTC-10OCT25-70000-C"
    print(f"\n🎯 Step 2: 选择交易标的: {target_instrument}")
    
    # Step 3: 查看行情
    print(f"\n📋 Step 3: 查看行情...")
    orderbook = get_options_orderbook(target_instrument, env="testnet")
    
    if orderbook and orderbook["best_bid"] > 0:
        print(f"   最高买价: {orderbook['best_bid']:.4f}")
        print(f"   最低卖价: {orderbook['best_ask']:.4f}")
        print(f"   价差: {orderbook['spread']:.4f}")
        
        # Step 4: 下限价买单
        print(f"\n📝 Step 4: 下限价买单...")
        limit_price = orderbook["best_bid"] + 0.001
        
        buy_result = place_options_limit_order(
            instrument=target_instrument,
            side="buy",
            amount=0.1,  # 小量测试
            price=limit_price,
            post_only=True,
            env="testnet"
        )
        
        if buy_result.get("success"):
            buy_order_id = buy_result["order_id"]
            print(f"   ✅ 买单已提交: {buy_order_id}")
            
            # Step 5: 等待一段时间后撤销（如果未成交）
            print(f"\n⏰ Step 5: 等待10秒...")
            import time
            time.sleep(10)
            
            # Step 6: 撤销未成交的订单
            print(f"\n🚫 Step 6: 撤销挂单...")
            cancel_result = cancel_options_order(buy_order_id, env="testnet")
            
            if cancel_result.get("success"):
                print(f"   ✅ 订单已撤销")
            else:
                print(f"   ℹ️ 订单可能已成交: {cancel_result.get('error')}")
        else:
            print(f"   ❌ 买单失败: {buy_result['error']}")
    else:
        print(f"   ❌ 无法获取有效行情")
        
        # 如果没有行情，尝试市价单（小量）
        print(f"\n💰 尝试小量市价单...")
        market_result = place_options_market_order_btc_notional(
            instrument=target_instrument,
            side="buy",
            contracts=0.1,
            env="testnet"
        )
        
        if market_result.get("success"):
            print(f"   ✅ 市价单成功: {market_result['order_id']}")
        else:
            print(f"   ❌ 市价单失败: {market_result['error']}")
    
    # Step 7: 最终状态检查
    print(f"\n📊 Step 7: 最终状态...")
    final_positions = get_options_positions(env="testnet")
    final_orders = get_open_options_orders(env="testnet")
    
    print(f"   最终持仓: {len(final_positions)} 个")
    print(f"   最终挂单: {len(final_orders)} 个")
    
    # 如果有持仓，演示平仓
    if final_positions:
        print(f"\n🔒 Step 8: 演示平仓...")
        for pos in final_positions:
            if abs(pos.get("size", 0)) > 0.01:  # 只平有效持仓
                instrument = pos["instrument_name"]
                
                close_result = close_specific_options_position(
                    instrument=instrument,
                    env="testnet"
                )
                
                if close_result.get("success"):
                    print(f"   ✅ {instrument} 平仓成功")
                else:
                    print(f"   ❌ {instrument} 平仓失败: {close_result['error']}")
                break  # 只演示一个
    
    print(f"\n🎉 期权交易流程演示完成!")

# 运行示例
complete_options_trading_example()
```

### 风险管理示例
```python
def risk_management_example():
    """风险管理示例"""
    
    print("⚠️ 期权风险管理示例")
    print("=" * 30)
    
    # 1. 持仓监控
    positions = get_options_positions(env="testnet")
    
    for pos in positions:
        instrument = pos.get("instrument_name")
        size = pos.get("size", 0)
        unrealized_pnl = pos.get("unrealized_pnl", 0)
        mark_price = pos.get("mark_price", 0)
        
        if abs(size) < 0.01:  # 跳过零持仓
            continue
        
        print(f"📊 检查持仓: {instrument}")
        print(f"   持仓量: {size} 张")
        print(f"   未实现盈亏: {unrealized_pnl:.6f} BTC")
        print(f"   标记价格: {mark_price:.4f}")
        
        # 2. 止损检查（亏损超过0.01 BTC）
        if unrealized_pnl < -0.01:
            print(f"   🚨 触发止损! 亏损: {unrealized_pnl:.6f} BTC")
            
            # 自动平仓
            close_result = close_specific_options_position(
                instrument=instrument,
                env="testnet"
            )
            
            if close_result.get("success"):
                print(f"   ✅ 止损平仓成功")
            else:
                print(f"   ❌ 止损平仓失败: {close_result['error']}")
        
        # 3. 止盈检查（盈利超过0.02 BTC）
        elif unrealized_pnl > 0.02:
            print(f"   🎯 触发止盈! 盈利: {unrealized_pnl:.6f} BTC")
            
            # 部分止盈（平掉一半）
            partial_size = abs(size) * 0.5
            
            close_result = close_specific_options_position(
                instrument=instrument,
                size=partial_size,
                env="testnet"
            )
            
            if close_result.get("success"):
                print(f"   ✅ 部分止盈成功，平掉 {partial_size} 张")
            else:
                print(f"   ❌ 部分止盈失败: {close_result['error']}")
        
        else:
            print(f"   ✅ 持仓正常，继续持有")
        
        print()

# 运行风险管理检查
risk_management_example()
```

---

## 常见问题

### Q1: 为什么下单失败？
**常见原因:**
- ❌ 合约不存在或已过期
- ❌ 价格设置不合理（bid=0 或 ask=0）
- ❌ 数量小于最小交易量（0.1张）
- ❌ 账户余额不足

**解决方案:**
```python
# 检查合约是否存在
orderbook = get_options_orderbook("BTC-10OCT25-70000-C", env="testnet")
if not orderbook or orderbook["best_bid"] <= 0:
    print("❌ 合约无效或无流动性")
else:
    print("✅ 合约有效，可以交易")
```

### Q2: 限价单为什么不成交？
**原因:** 价格设置过于保守

**解决方案:**
```python
# 使用更激进的价格
orderbook = get_options_orderbook(instrument, env="testnet")
if orderbook["best_ask"] > 0:
    # 买单：设置接近卖价的价格
    aggressive_price = orderbook["best_ask"] - 0.0001
else:
    # 如果没有卖价，略高于买价
    aggressive_price = orderbook["best_bid"] + 0.001
```

### Q3: 如何确认订单状态？
```python
from qtrade.order_api.deribit_order_placer.options_order import get_options_order_status

order_id = "your_order_id"
status = get_options_order_status(order_id, env="testnet")

if status:
    print(f"订单状态: {status.get('order_state')}")
    print(f"成交数量: {status.get('filled_amount', 0)}")
    print(f"剩余数量: {status.get('amount', 0) - status.get('filled_amount', 0)}")
```

### Q4: 测试网和主网的区别？
| 特性 | 测试网 (testnet) | 主网 (mainnet) |
|------|------------------|----------------|
| 资金 | 虚拟资金 | 真实资金 |
| 流动性 | 较低 | 较高 |
| 风险 | 无风险 | 有风险 |
| 用途 | 学习测试 | 实际交易 |

**建议:** 始终先在测试网熟练后再使用主网！

### Q5: 期权到期怎么办？
- **ITM期权**: 自动行权
- **OTM期权**: 自动作废
- **建议**: 到期前主动平仓，避免行权

---

## 🚨 重要提醒

### 风险警告
- ⚠️ **期权交易风险极高**，可能损失全部投资
- ⚠️ **时间价值衰减**，临近到期价值快速下降
- ⚠️ **流动性风险**，部分合约可能难以成交
- ⚠️ **杠杆风险**，小幅价格变动可能导致大幅亏损

### 最佳实践
1. **先在测试网练习** - 熟悉所有功能
2. **小额开始** - 用少量资金学习
3. **设置止损** - 控制最大亏损
4. **分散投资** - 不要全仓一个期权
5. **及时平仓** - 避免到期行权的复杂性

### 技术支持
- 如遇到API错误，检查网络连接和API密钥
- 如遇到交易问题，先在测试网验证
- 保存所有订单ID用于问题追踪

---

**免责声明:** 本指南仅供教育目的，不构成投资建议。期权交易涉及重大风险，请在充分了解风险的前提下谨慎交易。
