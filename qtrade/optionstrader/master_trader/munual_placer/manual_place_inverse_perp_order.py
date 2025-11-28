


from qtrade.optionstrader.master_trader.async_order.async_inverse_perp_placer import place_inverse_perp_async


if __name__ == "__main__":
    place_inverse_perp_async(
        inst_id="ETH-USD-SWAP",
        side="long",
        crypto_notional=0.06,
        simulated=False,
        wait_time=30.0,
        poll_interval=0.5
    )