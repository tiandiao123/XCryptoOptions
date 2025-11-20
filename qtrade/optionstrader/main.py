

from qtrade.optionstrader.trading_engine.okx_engine.okx_trading_engine import OKXTradingEngine


if __name__ == "__main__":
    trading_engine = OKXTradingEngine(
        calendar_config_path="/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/calendar_spread/calendar_spread.yaml",
        gamma_scalping_config_path="/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/gamma_scalping_sell_straddle/gamma_scalping_sell_straddle.yaml",
        env="testnet"
    )
    trading_engine.run_loop()