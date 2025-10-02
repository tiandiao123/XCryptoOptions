import json
from qtrade.demo_trade.order_placer.inverse_perpetual_contract import check_order_status, close_position, get_current_positions, place_inverse_perp_order, place_inverse_perp_order_with_btc_notional
from qtrade.demo_trade.order_placer.utils import get_current_btc_price


def test_place_order():
    inst = "BTC-USD-SWAP"
    side = "buy"
    size = 1  # ✅ Fixed: Whole number contracts (was 0.1)
    ordtype = "market"
    # price = 10000
    posSide = None  # ✅ Fixed: None for net mode (was "long")
    order_res = place_inverse_perp_order(
            instId=inst,
            side=side,
            sz_contracts=size,
            ordType=ordtype,
            px=None,
            posSide=posSide,
            tdMode="cross",
        )

    print("Order result:", json.dumps(order_res, indent=2))


def test_place_order_with_btc_notional():
    inst = "BTC-USD-SWAP"
    side = "buy"
    btc_notional = 0.1
    ordtype = "market"
    posSide = None  # ✅ Fixed: None for net mode (was "long")
    order_res = place_inverse_perp_order_with_btc_notional(
        instId=inst,
        side=side,
        btc_notional=btc_notional,
        ordType=ordtype,
        px=None,
        posSide=posSide,
        tdMode="cross",
    )
    print("Order result:", json.dumps(order_res, indent=2))


def demo_position_management():
    """演示完整的仓位管理流程"""
    print("🚀 开始仓位管理演示...")
    
    # 1. 查看当前仓位
    print("\n📊 Step 1: 查看当前仓位")
    positions = get_current_positions()

    
    # 2. 平掉BTC-USD-SWAP仓位
    print("\n🎯 Step 2: 平掉BTC-USD-SWAP仓位")
    order_id = close_position("BTC-USD-SWAP")
    
    # 3. 检查订单状态
    if order_id:
        print("\n📋 Step 3: 检查平仓订单状态")
        import time
        time.sleep(2)  # 等待2秒让订单处理
        check_order_status(order_id, "BTC-USD-SWAP")
    
    # 4. 再次查看仓位确认平仓成功
    print("\n✅ Step 4: 确认平仓结果")
    final_positions = get_current_positions()
    
    return order_id


def test_place_limit_order():
    inst = "BTC-USD-SWAP"
    side = "buy"
    btc_notional = 0.1
    ordtype = "limit"
    px = get_current_btc_price("BTC-USD-SWAP") - 2
    posSide = None
    order_id, order_res = place_inverse_perp_order_with_btc_notional(
        instId=inst,
        side=side,
        btc_notional=btc_notional,
        ordType=ordtype,
        px=px,
        posSide=posSide,
        tdMode="cross",
    )
    print("Order result:", json.dumps(order_res, indent=2))


if __name__ == "__main__":
    test_place_limit_order()
