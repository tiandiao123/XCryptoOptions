# Deribit Options Order Placement Tutorial

## 📋 Overview

This tutorial explains how to place and manage options orders on Deribit using our Python API wrapper. You'll learn how to find options contracts, place market/limit orders, and manage order cancellation for options trading.

## 🔧 Prerequisites

- Python environment with required dependencies
- Deribit testnet API credentials configured
- Basic understanding of options trading concepts (calls, puts, strikes, expiry)

## 🚀 Getting Started

### Import Required Functions

```python
from qtrade.demo_trade.deribit_order_placer.options_order import (
    get_options_instruments,
    get_options_orderbook,
    place_options_market_order,
    place_options_limit_order,
    place_options_limit_order_relative_to_market,
    cancel_options_order,
    get_options_order_status,
    find_atm_options,
    get_options_positions,
    get_open_options_orders
)
```

## 📊 Understanding Options Basics

### Options Contract Format
Deribit options follow this naming convention:
- `BTC-25JAN25-100000-C` → BTC Call, expires Jan 25 2025, $100,000 strike
- `ETH-15FEB25-4000-P` → ETH Put, expires Feb 15 2025, $4,000 strike

### Key Components:
- **Underlying**: BTC or ETH
- **Expiry Date**: When the option expires
- **Strike Price**: The exercise price
- **Type**: C (Call) or P (Put)

## 🎯 Finding Options Contracts

### 1. Get Available Options

```python
# Get all available BTC options
instruments = get_options_instruments("BTC", expired=False, env="testnet")

print(f"Found {len(instruments)} BTC options")

# Show first few options
for instrument in instruments[:5]:
    name = instrument.get("instrument_name")
    strike = instrument.get("strike")
    print(f"  {name} - Strike: ${strike:,.0f}")
```

### 2. Find At-The-Money (ATM) Options

```python
# Automatically find options closest to current BTC price
atm_result = find_atm_options("BTC", days_to_expiry=7, env="testnet")

if not atm_result.get("error"):
    current_price = atm_result["current_price"]
    atm_calls = atm_result["atm_calls"]
    atm_puts = atm_result["atm_puts"]
    
    print(f"Current BTC Price: ${current_price:,.2f}")
    print(f"Found {len(atm_calls)} ATM calls and {len(atm_puts)} ATM puts")
    
    # Get the best ATM call option
    if atm_calls:
        best_call = atm_calls[0]
        print(f"Best ATM Call: {best_call['instrument_name']}")
        print(f"Strike: ${best_call['strike']:,.0f}")
        print(f"Days to expiry: {best_call['days_to_expiry']}")
```

### 3. Get Real-Time Market Data

```python
# Get orderbook for a specific option
instrument = "BTC-25JAN25-100000-C"
orderbook = get_options_orderbook(instrument, depth=5, env="testnet")

if orderbook:
    print(f"Market data for {instrument}:")
    print(f"  Best Bid: {orderbook['best_bid']:.4f}")
    print(f"  Best Ask: {orderbook['best_ask']:.4f}")
    print(f"  Spread: {orderbook['spread']:.4f}")
    print(f"  Mid Price: {orderbook['mid_price']:.4f}")
```

## 📝 Order Types and Placement

### 1. Market Orders

Market orders execute immediately at the best available price.

```python
# Buy 1 BTC call option at market price
result = place_options_market_order(
    instrument="BTC-25JAN25-100000-C",
    side="buy",           # "buy" or "sell"
    amount=1,             # Number of contracts
    reduce_only=False,    # True to only reduce existing position
    env="testnet"         # "testnet" or "mainnet"
)

if result.get("success"):
    print(f"✅ Market order placed! ID: {result['order_id']}")
    print(f"📊 State: {result['order_state']}")
    print(f"✅ Filled: {result['filled_amount']}")
else:
    print(f"❌ Order failed: {result.get('error')}")
```

### 2. Limit Orders

Limit orders execute only at your specified price or better.

```python
# Sell 1 BTC call option at specific price
result = place_options_limit_order(
    instrument="BTC-25JAN25-100000-C",
    side="sell",
    amount=1,             # Number of contracts
    price=0.05,           # Limit price (in BTC)
    post_only=False,      # True for maker-only orders
    reduce_only=False,    # True to only reduce positions
    env="testnet"
)

if result.get("success"):
    order_id = result["order_id"]
    print(f"✅ Limit order placed! ID: {order_id}")
    
    # Store order_id for later management
    pending_orders.append(order_id)
else:
    print(f"❌ Limit order failed: {result.get('error')}")
```

### 3. Smart Relative Orders

Place orders relative to current market prices.

```python
# Buy order slightly above current best bid
result = place_options_limit_order_relative_to_market(
    instrument="BTC-25JAN25-100000-C",
    side="buy",
    amount=1,
    offset=0.001,         # 0.001 BTC above best bid
    post_only=True,       # Maker-only order
    env="testnet"
)

# For sell orders, offset is subtracted from best ask
# For buy orders, offset is added to best bid

if result.get("success"):
    print(f"✅ Relative order placed!")
    print(f"Reference Price: {result['reference_price']:.4f}")
    print(f"Final Price: {result['price']:.4f}")
```

## 🔍 Order Management

### Check Order Status

```python
order_id = "your_order_id_here"

status = get_options_order_status(order_id, "testnet")

if status:
    print(f"📊 Order Status:")
    print(f"   🆔 Order ID: {order_id}")
    print(f"   📊 State: {status.get('order_state')}")
    print(f"   ✅ Filled: {status.get('filled_amount', 0)}")
    print(f"   ⏳ Remaining: {status.get('amount', 0) - status.get('filled_amount', 0)}")
else:
    print("❌ Order not found or error occurred")
```

### Cancel Individual Order

```python
order_id = "your_order_id_here"

cancel_result = cancel_options_order(order_id, "testnet")

if cancel_result.get("success"):
    print(f"✅ Order {order_id} canceled successfully!")
else:
    print(f"❌ Cancel failed: {cancel_result.get('error')}")
```

### Cancel All Options Orders

```python
# Cancel all BTC options orders
cancel_result = cancel_all_options_orders("BTC", "testnet")

if cancel_result.get("success"):
    canceled_count = cancel_result.get("canceled_count", 0)
    print(f"✅ Canceled {canceled_count} options orders!")
else:
    print(f"❌ Cancel all failed: {cancel_result.get('error')}")
```

## 📊 Portfolio Management

### Check Current Positions

```python
# Get all BTC options positions
positions = get_options_positions("BTC", "testnet")

print(f"📊 Current Options Positions: {len(positions)}")

for pos in positions:
    instrument = pos.get("instrument_name")
    size = pos.get("size", 0)
    direction = pos.get("direction")
    mark_price = pos.get("mark_price", 0)
    pnl = pos.get("unrealized_pnl", 0)
    
    print(f"\n📋 {instrument}")
    print(f"   Size: {size} contracts ({direction})")
    print(f"   Mark Price: {mark_price:.4f}")
    print(f"   Unrealized PnL: {pnl:.6f} BTC")
```

### Check Open Orders

```python
# Get all open BTC options orders
orders = get_open_options_orders("BTC", "testnet")

print(f"📝 Open Options Orders: {len(orders)}")

for order in orders:
    order_id = order.get("order_id")
    instrument = order.get("instrument_name")
    direction = order.get("direction")
    amount = order.get("amount", 0)
    price = order.get("price")
    
    print(f"\n📋 {order_id}")
    print(f"   {instrument}")
    print(f"   {direction.upper()} {amount} @ {price:.4f}")
```

## 🎯 Complete Options Trading Workflow

Here's a complete example showing a typical options trading workflow:

```python
import time

def complete_options_workflow():
    """Demonstrate complete options trading workflow"""
    
    print("🚀 Starting Options Trading Workflow")
    print("=" * 50)
    
    # Step 1: Find ATM options
    print("\n📊 Step 1: Finding ATM BTC options...")
    atm_result = find_atm_options("BTC", days_to_expiry=7, env="testnet")
    
    if atm_result.get("error"):
        print(f"❌ Error: {atm_result['error']}")
        return
    
    current_price = atm_result["current_price"]
    atm_calls = atm_result["atm_calls"]
    
    if not atm_calls:
        print("❌ No ATM calls found")
        return
    
    # Select best ATM call
    target_option = atm_calls[0]["instrument_name"]
    strike = atm_calls[0]["strike"]
    
    print(f"✅ Selected: {target_option}")
    print(f"   Current BTC: ${current_price:,.2f}")
    print(f"   Strike: ${strike:,.0f}")
    
    # Step 2: Get market data
    print(f"\n📋 Step 2: Getting market data...")
    orderbook = get_options_orderbook(target_option, env="testnet")
    
    if not orderbook or orderbook.get("best_bid", 0) <= 0:
        print("❌ No valid market data")
        return
    
    best_bid = orderbook["best_bid"]
    best_ask = orderbook["best_ask"]
    
    print(f"💰 Market Data:")
    print(f"   Best Bid: {best_bid:.4f}")
    print(f"   Best Ask: {best_ask:.4f}")
    print(f"   Spread: {orderbook['spread']:.4f}")
    
    # Step 3: Place limit order below market
    print(f"\n📝 Step 3: Placing limit buy order...")
    limit_price = best_bid + 0.001  # Slightly above bid
    
    order_result = place_options_limit_order(
        instrument=target_option,
        side="buy",
        amount=1,
        price=limit_price,
        post_only=True,
        env="testnet"
    )
    
    if not order_result.get("success"):
        print(f"❌ Order failed: {order_result.get('error')}")
        return
    
    order_id = order_result["order_id"]
    print(f"✅ Order placed: {order_id}")
    
    # Step 4: Monitor order for 30 seconds
    print(f"\n⏰ Step 4: Monitoring order for 30 seconds...")
    
    for i in range(6):  # Check every 5 seconds
        time.sleep(5)
        
        status = get_options_order_status(order_id, "testnet")
        
        if not status:
            print("❌ Could not get order status")
            break
        
        order_state = status.get("order_state")
        filled_amount = status.get("filled_amount", 0)
        
        print(f"📊 Check {i+1}: {order_state}, Filled: {filled_amount}")
        
        # If filled or cancelled, stop monitoring
        if order_state in ["filled", "cancelled", "rejected"]:
            print(f"🎯 Order {order_state}")
            return
    
    # Step 5: Cancel if still open
    print(f"\n🚫 Step 5: Canceling unfilled order...")
    
    cancel_result = cancel_options_order(order_id, "testnet")
    
    if cancel_result.get("success"):
        print("✅ Order canceled successfully")
    else:
        print(f"❌ Cancel failed: {cancel_result.get('error')}")
    
    # Step 6: Check final portfolio
    print(f"\n📊 Step 6: Final portfolio check...")
    positions = get_options_positions("BTC", "testnet")
    orders = get_open_options_orders("BTC", "testnet")
    
    print(f"📋 Final Status:")
    print(f"   Positions: {len(positions)}")
    print(f"   Open Orders: {len(orders)}")

# Run the workflow
complete_options_workflow()
```

## 💡 Options Trading Strategies

### 1. Buying Calls (Bullish)

```python
# Buy ATM call when expecting price increase
atm_result = find_atm_options("BTC", days_to_expiry=14)
atm_call = atm_result["atm_calls"][0]["instrument_name"]

# Place market order for immediate execution
result = place_options_market_order(
    instrument=atm_call,
    side="buy",
    amount=1,
    env="testnet"
)
```

### 2. Buying Puts (Bearish)

```python
# Buy ATM put when expecting price decrease
atm_result = find_atm_options("BTC", days_to_expiry=14)
atm_put = atm_result["atm_puts"][0]["instrument_name"]

# Place limit order below market
orderbook = get_options_orderbook(atm_put)
limit_price = orderbook["best_bid"] + 0.001

result = place_options_limit_order(
    instrument=atm_put,
    side="buy",
    amount=1,
    price=limit_price,
    env="testnet"
)
```

### 3. Selling Options (Premium Collection)

```python
# Sell out-of-the-money options to collect premium
# Find options with strikes away from current price

atm_result = find_atm_options("BTC", days_to_expiry=7)
current_price = atm_result["current_price"]

# Look for OTM calls (strikes above current price)
instruments = get_options_instruments("BTC", expired=False)

otm_calls = []
for instrument in instruments:
    strike = instrument.get("strike", 0)
    name = instrument.get("instrument_name", "")
    
    # Find calls with strikes 5% above current price
    if "-C" in name and strike > current_price * 1.05:
        otm_calls.append(name)

if otm_calls:
    # Sell OTM call for premium
    target_call = otm_calls[0]
    
    result = place_options_limit_order_relative_to_market(
        instrument=target_call,
        side="sell",
        amount=1,
        offset=-0.001,  # Slightly below ask for quick fill
        env="testnet"
    )
```

## ⚠️ Risk Management

### 1. Position Sizing

```python
# Never risk more than you can afford to lose
max_risk_per_trade = 0.01  # 1% of portfolio

# Calculate position size based on option premium
orderbook = get_options_orderbook("BTC-25JAN25-100000-C")
option_price = orderbook["best_ask"]

# If option costs 0.05 BTC and max risk is 0.01 BTC
max_contracts = int(max_risk_per_trade / option_price)
print(f"Max safe position: {max_contracts} contracts")
```

### 2. Time Decay Management

```python
# Monitor time to expiry for all positions
positions = get_options_positions("BTC")

for pos in positions:
    instrument = pos["instrument_name"]
    
    # Parse expiry from instrument name (e.g., BTC-25JAN25-100000-C)
    parts = instrument.split("-")
    if len(parts) >= 2:
        expiry_str = parts[1]  # "25JAN25"
        
        # Calculate days to expiry (simplified)
        print(f"{instrument}: Check expiry {expiry_str}")
        
        # Close positions close to expiry if needed
        # if days_to_expiry < 3:
        #     close_position(instrument)
```

### 3. Stop Loss Orders

```python
# Monitor positions and close if losses exceed threshold
positions = get_options_positions("BTC")

for pos in positions:
    unrealized_pnl = pos.get("unrealized_pnl", 0)
    size = pos.get("size", 0)
    instrument = pos.get("instrument_name")
    
    # If position is losing more than 50% of premium paid
    loss_threshold = -0.025  # -0.025 BTC loss limit
    
    if unrealized_pnl < loss_threshold:
        print(f"⚠️ Stop loss triggered for {instrument}")
        
        # Close position with market order
        close_side = "sell" if size > 0 else "buy"
        
        result = place_options_market_order(
            instrument=instrument,
            side=close_side,
            amount=abs(size),
            reduce_only=True,  # Only reduce position
            env="testnet"
        )
```

## 🚨 Common Issues and Solutions

### Issue 1: "No valid bid/ask prices"
**Problem:** Option has no liquidity
**Solution:** 
- Choose more liquid options (closer to ATM, shorter expiry)
- Use market orders for immediate execution
- Check during active trading hours

### Issue 2: Order not filling
**Problem:** Limit price is too far from market
**Solution:**
```python
# Use relative orders that adjust to market
result = place_options_limit_order_relative_to_market(
    instrument=option_name,
    side="buy",
    amount=1,
    offset=0.001,  # Small offset for quick fill
    post_only=False  # Allow taker orders
)
```

### Issue 3: "Instrument doesn't exist"
**Problem:** Option contract expired or invalid name
**Solution:**
```python
# Always verify instrument exists
instruments = get_options_instruments("BTC", expired=False)
valid_names = [inst["instrument_name"] for inst in instruments]

if target_option in valid_names:
    # Safe to place order
    place_order(target_option)
else:
    print(f"❌ {target_option} not available")
```

## 📚 Available Options

### BTC Options
- Strikes: Various levels around current price
- Expiries: Weekly and monthly
- Types: Calls (C) and Puts (P)

### ETH Options  
- Strikes: Various levels around current price
- Expiries: Weekly and monthly
- Types: Calls (C) and Puts (P)

## 🔐 Environment Settings

- `"testnet"` - For testing (recommended for learning)
- `"mainnet"` - For live trading (use with extreme caution)

## 📞 Support and Best Practices

### Best Practices:
1. **Always test on testnet first**
2. **Start with small position sizes**
3. **Understand options Greeks** (delta, gamma, theta, vega)
4. **Monitor time decay** on long positions
5. **Use stop losses** to limit downside
6. **Diversify expiries** to reduce time risk
7. **Check liquidity** before placing orders

### Error Handling:
```python
def safe_options_order(instrument, side, amount, price=None):
    """Place options order with proper error handling"""
    
    try:
        # Verify instrument exists
        instruments = get_options_instruments("BTC", expired=False)
        valid_instruments = [inst["instrument_name"] for inst in instruments]
        
        if instrument not in valid_instruments:
            return {"success": False, "error": "Invalid instrument"}
        
        # Check market data
        orderbook = get_options_orderbook(instrument)
        if not orderbook or orderbook.get("best_bid", 0) <= 0:
            return {"success": False, "error": "No market data"}
        
        # Place order
        if price:
            result = place_options_limit_order(
                instrument=instrument,
                side=side,
                amount=amount,
                price=price,
                env="testnet"
            )
        else:
            result = place_options_market_order(
                instrument=instrument,
                side=side,
                amount=amount,
                env="testnet"
            )
        
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}
```

## 🎓 Next Steps

1. **Practice with testnet** - Master the basics safely
2. **Learn options theory** - Understand Greeks and strategies
3. **Start small** - Use minimal position sizes initially  
4. **Paper trade** - Test strategies without real money
5. **Risk management** - Never risk more than you can lose
6. **Advanced strategies** - Spreads, straddles, strangles

---

**⚠️ Disclaimer:** Options trading involves significant risk of loss. This tutorial is for educational purposes only. Always test thoroughly on testnet and understand the risks before trading with real funds. Past performance does not guarantee future results.
