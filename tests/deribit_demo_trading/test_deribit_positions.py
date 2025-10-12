

from qtrade.order_api.deribit_order_placer.options_positions_info import get_instrument_iv, get_instrument_open_price, get_instrument_orderbook, get_instrument_pnl, get_instrument_position_size


if __name__ == "__main__":
    print(get_instrument_position_size("BTC-28NOV25-114000-C", "testnet"))
    print(get_instrument_open_price("BTC-28NOV25-114000-C", "testnet"))
    print(get_instrument_pnl("BTC-28NOV25-114000-C", "testnet"))


    get_instrument_orderbook("BTC-28NOV25-114000-C", "testnet")


    print(get_instrument_iv("BTC-28NOV25-114000-C", "testnet"))