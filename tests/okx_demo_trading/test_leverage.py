from qtrade.demo_trade.order_placer.leverage_manager import get_current_leverage

# Get specific contract leverage

def extract_leverage_test():
    btc_leverage = get_current_leverage("BTC-USD-SWAP")
    eth_leverage = get_current_leverage("ETH-USD-SWAP")

    print(f"BTC Leverage: {btc_leverage}x")
    print(f"ETH Leverage: {eth_leverage}x")

def set_leverage_test():
    from qtrade.demo_trade.order_placer.leverage_manager import (
        btc_leverage, eth_leverage, 
        set_btc_leverage, set_eth_leverage
    )
    # Quick set
    set_btc_leverage(1)  # Set BTC to 5x
    set_eth_leverage(1)  # Set ETH to 3x


if __name__ == "__main__":
    extract_leverage_test()
    set_leverage_test()

