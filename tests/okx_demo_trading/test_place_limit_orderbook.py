from qtrade.demo_trade.order_placer.inverse_perpetual_contract import place_inverse_perp_order_with_btc_notional, place_limit_order_relative_to_book
from qtrade.demo_trade.order_placer.orderbook import get_bid_ask



if __name__ == "__main__":
    book = get_bid_ask("BTC-USD-SWAP")
    print(book)

    order_id, result = place_inverse_perp_order_with_btc_notional(
        instId="BTC-USD-SWAP",
        side="buy", 
        btc_notional=0.1,
        ordType="limit",
        px=book["bid"]  # Exact bid-1 price
    )

