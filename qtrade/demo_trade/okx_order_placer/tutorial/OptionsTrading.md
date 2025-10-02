# 📊 OKX Options Trading API Tutorial

A comprehensive guide to using the OKX Options Trading API for BTC and ETH options contracts.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- OKX API credentials (API Key, Secret, Passphrase)
- Demo trading account recommended for testing

### Installation
```bash
# Activate your environment
source ~/miniconda3/bin/activate crypto

# Navigate to project directory
cd /home/ubuntu/options_trading
```

## 📋 Table of Contents

1. [Getting Started](#getting-started)
2. [Market Data](#market-data)
3. [Order Placement](#order-placement)
4. [Position Management](#position-management)
5. [Advanced Features](#advanced-features)
6. [Examples](#examples)
7. [Safety Guidelines](#safety-guidelines)

---

## 🎯 Getting Started

### Import Required Modules

```python
from qtrade.demo_trade.order_placer.options_order import (
    place_options_market_order,
    place_options_limit_order,
    place_options_limit_order_relative_to_book,
    get_options_positions,
    close_options_position,
    get_options_bid_ask
)

from qtrade.demo_trade.order_placer.options_contract import (
    get_option_greeks,
    get_atm_options_chain,
    get_options_ticker,
    create_options_market_snapshot
)
```

### Basic Setup

```python
# Example: Get BTC options information
atm_options = get_atm_options_chain("BTC-USD")
if atm_options and atm_options.get("atm_calls"):
    sample_contract = atm_options["atm_calls"][0]["instId"]
    print(f"Sample contract: {sample_contract}")
```

---

## 💰 Market Data

### 1. Get Current Bid/Ask Prices

```python
def get_market_data(contract_id):
    """Get current market data for an options contract"""
    bid_ask = get_options_bid_ask(contract_id)
    
    if bid_ask:
        print(f"Contract: {contract_id}")
        print(f"Bid: ${bid_ask['bid']:.4f}")
        print(f"Ask: ${bid_ask['ask']:.4f}")
        print(f"Mid Price: ${bid_ask['mid_price']:.4f}")
        print(f"Spread: ${bid_ask['spread']:.4f}")
        return bid_ask
    else:
        print("No market data available")
        return None

# Example usage
contract_id = "BTC-USD-251227-100000-C"
market_data = get_market_data(contract_id)
```

### 2. Find ATM (At-The-Money) Options

```python
def find_atm_options(underlying="BTC-USD"):
    """Find at-the-money options"""
    atm_chain = get_atm_options_chain(underlying)
    
    if atm_chain:
        print(f"Spot Price: ${atm_chain['spot_price']:,.2f}")
        print(f"ATM Calls: {len(atm_chain.get('atm_calls', []))}")
        print(f"ATM Puts: {len(atm_chain.get('atm_puts', []))}")
        
        # Show top 3 ATM calls
        for i, call in enumerate(atm_chain.get('atm_calls', [])[:3]):
            print(f"  {i+1}. {call['instId']}")
            print(f"     Strike: ${call['strike_price']:,.0f}")
            print(f"     Delta: {call['delta']:.4f}")
            print(f"     Mark Price: ${call['markPrice']:.4f}")
        
        return atm_chain
    
    return None

# Example usage
atm_options = find_atm_options("BTC-USD")
```

### 3. Get Options Greeks

```python
def get_contract_greeks(contract_id):
    """Get Greeks for a specific contract"""
    greeks_data = get_option_greeks(instId=contract_id)
    
    if greeks_data:
        greeks = greeks_data[0]  # First result
        print(f"Contract: {contract_id}")
        print(f"Delta: {greeks.get('delta', 0):.4f}")
        print(f"Gamma: {greeks.get('gamma', 0):.4f}")
        print(f"Theta: {greeks.get('theta', 0):.6f}")
        print(f"Vega: {greeks.get('vega', 0):.6f}")
        print(f"Implied Vol: {float(greeks.get('volLv', 0)):.2%}")
        return greeks
    
    return None

# Example usage
contract_greeks = get_contract_greeks("BTC-USD-251227-100000-C")
```

---

## 📝 Order Placement

### 1. Market Orders

Market orders execute immediately at the best available price.

```python
def place_market_buy(contract_id, size=1):
    """Place a market buy order"""
    result = place_options_market_order(
        instId=contract_id,
        side="buy",
        sz=size
    )
    
    if result['success']:
        print(f"✅ Market buy order placed!")
        print(f"Order ID: {result['orderId']}")
        return result['orderId']
    else:
        print(f"❌ Order failed: {result['error']}")
        return None

def place_market_sell(contract_id, size=1):
    """Place a market sell order"""
    result = place_options_market_order(
        instId=contract_id,
        side="sell",
        sz=size
    )
    
    if result['success']:
        print(f"✅ Market sell order placed!")
        print(f"Order ID: {result['orderId']}")
        return result['orderId']
    else:
        print(f"❌ Order failed: {result['error']}")
        return None

# Example usage
# order_id = place_market_buy("BTC-USD-251227-100000-C", 1)
```

### 2. Limit Orders

Limit orders execute only at your specified price or better.

```python
def place_limit_buy(contract_id, price, size=1):
    """Place a limit buy order"""
    result = place_options_limit_order(
        instId=contract_id,
        side="buy",
        sz=size,
        px=price
    )
    
    if result['success']:
        print(f"✅ Limit buy order placed at ${price:.4f}")
        print(f"Order ID: {result['orderId']}")
        return result['orderId']
    else:
        print(f"❌ Order failed: {result['error']}")
        return None

def place_limit_sell(contract_id, price, size=1):
    """Place a limit sell order"""
    result = place_options_limit_order(
        instId=contract_id,
        side="sell",
        sz=size,
        px=price
    )
    
    if result['success']:
        print(f"✅ Limit sell order placed at ${price:.4f}")
        print(f"Order ID: {result['orderId']}")
        return result['orderId']
    else:
        print(f"❌ Order failed: {result['error']}")
        return None

# Example usage
# Get current market data first
bid_ask = get_options_bid_ask("BTC-USD-251227-100000-C")
if bid_ask:
    # Place buy order slightly above current bid
    buy_price = bid_ask['bid'] + 0.0001
    # order_id = place_limit_buy("BTC-USD-251227-100000-C", buy_price, 1)
```

### 3. Smart Limit Orders (Relative to Book)

These orders automatically calculate prices relative to current bid/ask.

```python
def place_smart_limit_order(contract_id, side, offset=0.0001, size=1):
    """Place a limit order relative to current bid/ask"""
    result = place_options_limit_order_relative_to_book(
        instId=contract_id,
        side=side,
        sz=size,
        offset=offset
    )
    
    if result['success']:
        print(f"✅ Smart {side} limit order placed!")
        print(f"Order ID: {result['orderId']}")
        print(f"Price: ${result['price']:.4f}")
        print(f"Reference: ${result['reference_price']:.4f}")
        return result['orderId']
    else:
        print(f"❌ Order failed: {result['error']}")
        return None

# Example usage
# Buy order: bid + $0.0001
# order_id = place_smart_limit_order("BTC-USD-251227-100000-C", "buy", 0.0001, 1)

# Sell order: ask - $0.0001  
# order_id = place_smart_limit_order("BTC-USD-251227-100000-C", "sell", 0.0001, 1)
```

---

## 📊 Position Management

### 1. Check Current Positions

```python
def check_positions():
    """Check all current options positions"""
    positions = get_options_positions()
    
    if positions:
        print(f"📊 Found {len(positions)} active positions:")
        for pos in positions:
            contract = pos.get('instId')
            size = float(pos.get('pos', 0))
            avg_price = float(pos.get('avgPx', 0))
            mark_price = float(pos.get('markPx', 0))
            pnl = float(pos.get('upl', 0))
            
            print(f"\n  📋 {contract}")
            print(f"     Size: {size} contracts")
            print(f"     Side: {'Long' if size > 0 else 'Short'}")
            print(f"     Avg Price: ${avg_price:.4f}")
            print(f"     Mark Price: ${mark_price:.4f}")
            print(f"     Unrealized PnL: ${pnl:.4f}")
    else:
        print("📭 No active positions")
    
    return positions

# Example usage
positions = check_positions()
```

### 2. Close Positions

```python
def close_position(contract_id):
    """Close a specific position"""
    result = close_options_position(contract_id)
    
    if result and result.get('success'):
        print(f"✅ Position closed successfully!")
        print(f"Close Order ID: {result['orderId']}")
        return result['orderId']
    else:
        error = result.get('error', 'Unknown error') if result else 'No result'
        print(f"❌ Failed to close position: {error}")
        return None

# Example usage
# close_order_id = close_position("BTC-USD-251227-100000-C")
```

---

## 🔥 Advanced Features

### 1. Options Strategy: Long Straddle

```python
def create_long_straddle(underlying="BTC-USD", expiry_date=None):
    """Create a long straddle position"""
    # Find ATM options
    atm_chain = get_atm_options_chain(underlying, expiry_date)
    
    if not atm_chain or not atm_chain.get('atm_calls') or not atm_chain.get('atm_puts'):
        print("❌ No suitable ATM options found")
        return None
    
    # Get ATM call and put with same strike
    atm_calls = atm_chain['atm_calls']
    atm_puts = atm_chain['atm_puts']
    
    # Find matching strike prices
    call_strikes = {opt['strike_price']: opt for opt in atm_calls}
    put_strikes = {opt['strike_price']: opt for opt in atm_puts}
    
    common_strikes = set(call_strikes.keys()) & set(put_strikes.keys())
    
    if not common_strikes:
        print("❌ No matching call/put strikes found")
        return None
    
    # Use the strike closest to spot
    spot_price = atm_chain['spot_price']
    best_strike = min(common_strikes, key=lambda x: abs(x - spot_price))
    
    call_contract = call_strikes[best_strike]['instId']
    put_contract = put_strikes[best_strike]['instId']
    
    print(f"🎯 Creating Long Straddle at ${best_strike:,.0f} strike")
    print(f"   Call: {call_contract}")
    print(f"   Put: {put_contract}")
    
    # Place orders (commented for safety)
    print("\n📝 Orders to place:")
    print(f"# Buy Call: place_options_market_order('{call_contract}', 'buy', 1)")
    print(f"# Buy Put: place_options_market_order('{put_contract}', 'buy', 1)")
    
    return {
        'call_contract': call_contract,
        'put_contract': put_contract,
        'strike': best_strike,
        'spot_price': spot_price
    }

# Example usage
straddle_info = create_long_straddle("BTC-USD")
```

### 2. Options Strategy: Covered Call

```python
def create_covered_call(underlying="BTC-USD", strike_offset_pct=0.05):
    """Create a covered call strategy"""
    # Get current spot price and ATM options
    atm_chain = get_atm_options_chain(underlying)
    
    if not atm_chain:
        print("❌ No options data available")
        return None
    
    spot_price = atm_chain['spot_price']
    target_strike = spot_price * (1 + strike_offset_pct)  # 5% OTM call
    
    # Find call option closest to target strike
    atm_calls = atm_chain.get('atm_calls', [])
    if not atm_calls:
        print("❌ No call options available")
        return None
    
    best_call = min(atm_calls, key=lambda x: abs(x['strike_price'] - target_strike))
    call_contract = best_call['instId']
    
    print(f"🎯 Covered Call Strategy")
    print(f"   Spot Price: ${spot_price:,.2f}")
    print(f"   Target Strike: ${target_strike:,.2f}")
    print(f"   Selected Call: {call_contract}")
    print(f"   Actual Strike: ${best_call['strike_price']:,.0f}")
    
    # Strategy steps (commented for safety)
    print(f"\n📝 Strategy Steps:")
    print(f"# 1. Buy underlying (BTC-USD-SWAP): place_inverse_perp_order(...)")
    print(f"# 2. Sell call option: place_options_market_order('{call_contract}', 'sell', 1)")
    
    return {
        'call_contract': call_contract,
        'strike': best_call['strike_price'],
        'spot_price': spot_price,
        'premium': best_call.get('markPrice', 0)
    }

# Example usage
covered_call_info = create_covered_call("BTC-USD", 0.05)
```

---

## 💡 Complete Examples

### Example 1: Basic Options Trading Workflow

```python
def basic_options_workflow():
    """Complete workflow for options trading"""
    print("🚀 Basic Options Trading Workflow\n")
    
    # Step 1: Find suitable options
    print("📊 Step 1: Finding ATM options...")
    atm_options = get_atm_options_chain("BTC-USD")
    
    if not atm_options or not atm_options.get('atm_calls'):
        print("❌ No options found")
        return
    
    # Step 2: Select a contract
    sample_call = atm_options['atm_calls'][0]
    contract_id = sample_call['instId']
    
    print(f"✅ Selected contract: {contract_id}")
    print(f"   Strike: ${sample_call['strike_price']:,.0f}")
    print(f"   Delta: {sample_call['delta']:.4f}")
    
    # Step 3: Get market data
    print(f"\n💰 Step 2: Getting market data...")
    bid_ask = get_options_bid_ask(contract_id)
    
    if bid_ask:
        print(f"✅ Market Data:")
        print(f"   Bid: ${bid_ask['bid']:.4f}")
        print(f"   Ask: ${bid_ask['ask']:.4f}")
        print(f"   Spread: ${bid_ask['spread']:.4f}")
    
    # Step 4: Check positions
    print(f"\n🔍 Step 3: Checking positions...")
    positions = get_options_positions()
    print(f"✅ Current positions: {len(positions)}")
    
    # Step 5: Show order examples
    print(f"\n📝 Step 4: Order examples (COMMENTED):")
    print(f"# Market buy: place_options_market_order('{contract_id}', 'buy', 1)")
    print(f"# Limit buy: place_options_limit_order('{contract_id}', 'buy', 1, {bid_ask['bid'] + 0.0001:.4f})")
    print(f"# Smart limit: place_options_limit_order_relative_to_book('{contract_id}', 'buy', 1, 0.0001)")
    
    print(f"\n✅ Workflow completed!")

# Run the workflow
basic_options_workflow()
```

### Example 2: Risk Management

```python
def risk_managed_trade(contract_id, max_loss_usd=100):
    """Example of risk-managed options trade"""
    print(f"🛡️ Risk-Managed Trade for {contract_id}")
    
    # Get market data
    bid_ask = get_options_bid_ask(contract_id)
    if not bid_ask:
        print("❌ No market data available")
        return
    
    # Calculate position size based on risk
    option_price = bid_ask['ask']  # Buying at ask
    max_contracts = int(max_loss_usd / option_price)
    
    print(f"💰 Risk Analysis:")
    print(f"   Option Price: ${option_price:.4f}")
    print(f"   Max Loss: ${max_loss_usd}")
    print(f"   Max Contracts: {max_contracts}")
    
    if max_contracts < 1:
        print("⚠️ Option too expensive for risk tolerance")
        return
    
    # Place conservative order
    print(f"\n📝 Conservative Order:")
    print(f"# place_options_limit_order('{contract_id}', 'buy', {max_contracts}, {option_price:.4f})")
    
    return {
        'contract_id': contract_id,
        'max_contracts': max_contracts,
        'option_price': option_price,
        'max_loss': max_loss_usd
    }

# Example usage
# risk_info = risk_managed_trade("BTC-USD-251227-100000-C", 100)
```

---

## ⚠️ Safety Guidelines

### 🔒 Before Trading

1. **Test Environment**: Always test with demo trading first
2. **Small Sizes**: Start with 1 contract to test functionality
3. **Understand Greeks**: Know your Delta, Gamma, Theta, Vega exposure
4. **Check Liquidity**: Ensure tight bid-ask spreads
5. **Risk Management**: Never risk more than you can afford to lose

### 📋 Best Practices

```python
# ✅ Good practices
def safe_trading_practices():
    """Demonstrate safe trading practices"""
    
    # 1. Always check market data first
    contract_id = "BTC-USD-251227-100000-C"
    bid_ask = get_options_bid_ask(contract_id)
    
    if not bid_ask:
        print("❌ No market data - don't trade")
        return
    
    # 2. Check spread is reasonable (< 5% typically)
    spread_pct = (bid_ask['spread'] / bid_ask['mid_price']) * 100
    if spread_pct > 5:
        print(f"⚠️ Wide spread: {spread_pct:.2f}% - consider avoiding")
    
    # 3. Start with small size
    size = 1  # Always start with 1 contract
    
    # 4. Use limit orders for better control
    limit_price = bid_ask['bid'] + 0.0001  # Slightly above bid
    
    # 5. Set stop-loss mentally (options can go to zero)
    max_loss_pct = 50  # Exit if down 50%
    
    print(f"✅ Safe to trade:")
    print(f"   Contract: {contract_id}")
    print(f"   Spread: {spread_pct:.2f}%")
    print(f"   Size: {size} contract")
    print(f"   Limit Price: ${limit_price:.4f}")
    print(f"   Max Loss: {max_loss_pct}%")

# Run safety check
safe_trading_practices()
```

### 🚨 Common Mistakes to Avoid

1. **Don't use market orders on illiquid options** - Use limit orders
2. **Don't ignore time decay (Theta)** - Options lose value over time
3. **Don't over-leverage** - Options can expire worthless
4. **Don't ignore implied volatility** - High IV = expensive options
5. **Don't forget about assignment risk** - Short options can be assigned

---

## 🔧 Troubleshooting

### Common Issues

```python
# Issue 1: "No market data available"
# Solution: Check if contract ID is valid and market is open

# Issue 2: "Order failed: Insufficient balance"
# Solution: Check account balance and reduce position size

# Issue 3: "Order failed: Invalid price"
# Solution: Check price is within reasonable range of current market

# Issue 4: "No positions found"
# Solution: Verify you have actual positions, not just pending orders
```

### Debug Functions

```python
def debug_contract(contract_id):
    """Debug a specific contract"""
    print(f"🔍 Debugging {contract_id}")
    
    # Check if contract exists
    bid_ask = get_options_bid_ask(contract_id)
    print(f"Market Data: {'✅' if bid_ask else '❌'}")
    
    # Check Greeks
    greeks = get_option_greeks(instId=contract_id)
    print(f"Greeks Data: {'✅' if greeks else '❌'}")
    
    # Check positions
    positions = get_options_positions(instId=contract_id)
    print(f"Positions: {len(positions) if positions else 0}")

# Example usage
# debug_contract("BTC-USD-251227-100000-C")
```

---

## 📞 Support

For issues or questions:
1. Check the debug functions above
2. Verify your API credentials
3. Ensure you're using valid contract IDs
4. Test with small sizes first

## 🎉 Happy Trading!

Remember: Options trading involves significant risk. Always:
- Start small
- Use demo mode
- Understand the Greeks
- Manage your risk
- Never invest more than you can afford to lose

---

*Last updated: October 2025*
