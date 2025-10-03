# Deribit Futures Order Placement Tutorial

## 📋 Overview

This tutorial explains how to place and manage futures orders on Deribit using our Python API wrapper. You'll learn how to place market orders, limit orders, and manage order cancellation.

## 🔧 Prerequisites

- Python environment with required dependencies
- Deribit testnet API credentials configured
- Basic understanding of futures trading concepts

## 🚀 Getting Started

### Import Required Functions

```python
from qtrade.demo_trade.deribit_order_placer.futures_order import (
    place_market_order,
    place_limit_order,
    place_limit_order_relative_to_market,
    place_market_order_btc_notional,
    place_limit_order_btc_notional,
    place_limit_order_btc_relative_to_market,
    cancel_order,
    get_order_status,
    get_current_price
)
```

## 💰 Understanding Deribit Amount Format

**Important:** Deribit futures orders use **USD notional amounts** that must be **multiples of 10**.

- ✅ Valid amounts: `10`, `20`, `30`, `40`, `50`
- ❌ Invalid amounts: `11`, `12`, `15`, `25`, `33`
- 💡 Minimum order size: `$10 USD`

## 📊 Order Types

### 1. Market Orders

Market orders execute immediately at the best available price.

**Advantages:**
- Guaranteed execution (if liquidity exists)
- Immediate fill
- Simple to use

**Disadvantages:**
- No price control
- May experience slippage
- Higher trading costs

**When to use:**
- Need immediate execution
- High liquidity markets
- Small order sizes

### 2. Limit Orders

Limit orders execute only at your specified price or better.

**Advantages:**
- Price control
- Potentially better execution price
- Can act as maker (earn rebates)

**Disadvantages:**
- May not execute
- Requires monitoring
- Market may move away

**When to use:**
- Want specific entry/exit price
- Non-urgent orders
- Volatile markets

## 🎯 Basic Order Placement

### Market Order Example

```python
# Place a market buy order for $20 USD notional
result = place_market_order(
    instrument="BTC-PERPETUAL",
    side="buy",           # "buy" or "sell"
    amount=20,            # $20 USD (must be multiple of 10)
    reduce_only=False,    # True to only reduce existing position
    env="testnet"         # "testnet" or "mainnet"
)

if result.get("success"):
    print(f"✅ Order placed! ID: {result['order_id']}")
    print(f"📊 State: {result['order_state']}")
    print(f"✅ Filled: {result['filled_amount']}")
else:
    print(f"❌ Order failed: {result.get('error')}")
```

### Limit Order Example

```python
# Place a limit sell order at $120,000
result = place_limit_order(
    instrument="BTC-PERPETUAL",
    side="sell",
    amount=30,            # $30 USD notional
    price=120000,         # $120,000 limit price
    post_only=False,      # True for maker-only orders
    reduce_only=False,
    env="testnet"
)

if result.get("success"):
    order_id = result["order_id"]
    print(f"✅ Limit order placed! ID: {order_id}")
    
    # Store order_id for later cancellation if needed
    pending_orders.append(order_id)
else:
    print(f"❌ Limit order failed: {result.get('error')}")
```

## 🟠 BTC Notional Orders (Recommended)

Our API provides convenient functions that accept BTC amounts and automatically convert to USD.

### BTC Notional Market Order

```python
# Place market order for 0.0001 BTC notional
result = place_market_order_btc_notional(
    instrument="BTC-PERPETUAL",
    side="buy",
    btc_amount=0.0001,    # 0.0001 BTC notional
    reduce_only=False,
    env="testnet"
)

# The function automatically:
# 1. Gets current BTC price
# 2. Converts 0.0001 BTC to USD
# 3. Rounds to nearest multiple of 10
# 4. Places the order

print(f"Converted: {result['btc_amount']} BTC → ${result['usd_amount']} USD")
```

### BTC Notional Limit Order

```python
# Place limit order for 0.0002 BTC at $115,000
result = place_limit_order_btc_notional(
    instrument="BTC-PERPETUAL",
    side="sell",
    btc_amount=0.0002,    # 0.0002 BTC notional
    price=115000,         # $115,000 limit price
    post_only=True,       # Maker-only order
    env="testnet"
)
```

### Smart Relative Limit Order

```python
# Place buy order $50 below current best bid
result = place_limit_order_btc_relative_to_market(
    instrument="BTC-PERPETUAL",
    side="buy",
    btc_amount=0.0001,    # 0.0001 BTC notional
    offset=50.0,          # $50 below best bid
    post_only=True,
    env="testnet"
)

# For sell orders, offset is subtracted from best ask
# For buy orders, offset is added to best bid
```

## 🔍 Order Management

### Check Order Status

```python
order_id = "your_order_id_here"

status = get_order_status(order_id, "testnet")

if status:
    print(f"📊 Order State: {status.get('order_state')}")
    print(f"✅ Filled Amount: {status.get('filled_amount', 0)}")
    print(f"⏳ Remaining: {status.get('amount', 0) - status.get('filled_amount', 0)}")
else:
    print("❌ Order not found or error occurred")
```

### Cancel Individual Order

```python
order_id = "your_order_id_here"

cancel_result = cancel_order(order_id, "testnet")

if cancel_result.get("success"):
    print(f"✅ Order {order_id} canceled successfully!")
else:
    print(f"❌ Cancel failed: {cancel_result.get('error')}")
```

## 🎯 Complete Order Workflow

Here's a complete example showing the typical order lifecycle:

```python
import time

def complete_order_workflow():
    """Demonstrate complete order placement and management"""
    
    # 1. Check current market price
    price_data = get_current_price("BTC-PERPETUAL", "testnet")
    current_price = price_data.get("mark_price", 0)
    print(f"💰 Current BTC Price: ${current_price:,.2f}")
    
    # 2. Place a limit order below market
    limit_price = current_price - 1000  # $1000 below market
    
    result = place_limit_order_btc_notional(
        instrument="BTC-PERPETUAL",
        side="buy",
        btc_amount=0.0001,
        price=limit_price,
        post_only=True,
        env="testnet"
    )
    
    if not result.get("success"):
        print(f"❌ Order placement failed: {result.get('error')}")
        return
    
    order_id = result["order_id"]
    print(f"✅ Limit order placed: {order_id}")
    
    # 3. Monitor order for 30 seconds
    print("⏰ Monitoring order for 30 seconds...")
    
    for i in range(6):  # Check every 5 seconds for 30 seconds
        time.sleep(5)
        
        status = get_order_status(order_id, "testnet")
        
        if not status:
            print("❌ Could not get order status")
            break
            
        order_state = status.get("order_state")
        filled_amount = status.get("filled_amount", 0)
        
        print(f"📊 Status check {i+1}: {order_state}, Filled: {filled_amount}")
        
        # If order is filled, we're done
        if order_state == "filled":
            print("🎉 Order filled successfully!")
            return
        
        # If order is cancelled or rejected, stop monitoring
        if order_state in ["cancelled", "rejected"]:
            print(f"⚠️ Order {order_state}")
            return
    
    # 4. Cancel order if still open after 30 seconds
    print("⏰ 30 seconds elapsed, canceling order...")
    
    cancel_result = cancel_order(order_id, "testnet")
    
    if cancel_result.get("success"):
        print("✅ Order canceled successfully")
    else:
        print(f"❌ Cancel failed: {cancel_result.get('error')}")

# Run the workflow
complete_order_workflow()
```

## ⚠️ Best Practices

### 1. Order Size Management
- Always use multiples of 10 for USD amounts
- Use BTC notional functions for easier amount calculation
- Respect minimum order size ($10 USD)

### 2. Price Setting
- For limit orders, check current market before setting price
- Use `get_current_price()` to get real-time market data
- Consider bid-ask spread when setting limit prices

### 3. Order Monitoring
- Always store order IDs for tracking
- Check order status periodically
- Set up automatic cancellation for unfilled orders

### 4. Error Handling
- Always check `result.get("success")` before proceeding
- Handle API errors gracefully
- Implement retry logic for network issues

### 5. Risk Management
- Use `reduce_only=True` when closing positions
- Set appropriate position sizes
- Monitor market conditions before placing orders

## 🚨 Common Issues and Solutions

### Issue 1: "Order size too small"
**Problem:** Amount is below $10 USD minimum
**Solution:** Increase BTC amount or use larger USD amount

### Issue 2: "400 Bad Request" 
**Problem:** Amount is not a multiple of 10
**Solution:** Use BTC notional functions or ensure USD amount is multiple of 10

### Issue 3: Order not filling
**Problem:** Limit price is too far from market
**Solution:** 
- Check current market price
- Adjust limit price closer to market
- Consider using market order for immediate execution

### Issue 4: "Instrument doesn't exist"
**Problem:** Wrong instrument name
**Solution:** Use correct format: "BTC-PERPETUAL", "ETH-PERPETUAL"

## 📚 Available Instruments

- `BTC-PERPETUAL` - Bitcoin perpetual futures
- `ETH-PERPETUAL` - Ethereum perpetual futures

## 🔐 Environment Settings

- `"testnet"` - For testing (recommended for learning)
- `"mainnet"` - For live trading (use with caution)

## 📞 Support

For technical issues or questions:
1. Check error messages carefully
2. Verify API credentials
3. Ensure proper environment setup
4. Test with small amounts first

## 🎓 Next Steps

1. Practice with testnet environment
2. Start with small amounts
3. Understand market dynamics
4. Implement proper risk management
5. Consider automated trading strategies

---

**⚠️ Disclaimer:** This tutorial is for educational purposes. Always test thoroughly on testnet before using real funds. Trading involves risk of loss.
