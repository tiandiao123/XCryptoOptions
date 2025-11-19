#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动构建 Calendar Spread 并平仓工具

用途：当你有已开仓的期权持仓，想要构建 CalendarSpreadOpportunity 对象并平仓
"""

import sys
sys.path.append('/home/ubuntu/options_trading')
import asyncio
from qtrade.optionstrader.arbitrage_searcher.option_data import CalendarSpreadOpportunity, OptionData
from qtrade.optionstrader.master_trader.async_coordinated_order_placer import close_calendar_spread_async
from qtrade.order_api.okx.client.options_client import OKXOptionsClient


def fetch_option_data_from_okx(inst_id: str, simulated: bool = False) -> OptionData:
    """
    从 OKX 获取期权的实时数据
    
    Args:
        inst_id: 期权合约ID，如 "ETH-USD-20251121-3100-C"
        simulated: 是否使用模拟盘
    
    Returns:
        OptionData 对象
    """
    from qtrade.optionstrader.arbitrage_searcher.calendar_spread.atm_options_okx import get_okx_option_market_data
    import requests
    from datetime import datetime
    
    # 1. 获取市场数据（bid/ask/mid/IV/Greeks）
    market_data = get_okx_option_market_data(inst_id)
    
    if not market_data:
        raise ValueError(f"无法获取期权市场数据: {inst_id}")
    
    # 2. 获取合约基本信息（到期日等）
    # 从 inst_id 提取币种
    parts = inst_id.split("-")
    currency = parts[0]  # ETH or BTC
    uly = f"{currency}-USD"  # ETH-USD
    
    url = "https://www.okx.com/api/v5/public/instruments"
    params = {"instType": "OPTION", "uly": uly, "instId": inst_id}
    resp = requests.get(url, params=params, timeout=5)
    inst_data = resp.json()
    
    if inst_data.get("code") != "0" or not inst_data.get("data"):
        raise ValueError(f"无法获取合约信息: {inst_id}, 错误: {inst_data.get('msg', 'Unknown')}")
    
    inst_info = inst_data["data"][0]
    
    # 解析 symbol
    parts = inst_id.split("-")
    currency = parts[0]  # ETH
    expiry_date = parts[2]  # 20251121
    strike = float(parts[3])  # 3100
    option_type = parts[4]  # C or P
    
    # 计算到期天数
    exp_ms = int(inst_info.get("expTime", 0))
    if exp_ms <= 0:
        raise ValueError(f"无效的到期时间: {inst_id}")
    
    expiry_dt = datetime.fromtimestamp(exp_ms / 1000)
    days_to_expiry = (expiry_dt - datetime.now()).days
    expiry_str = expiry_dt.strftime("%y%m%d")
    
    # 3. 构建 OptionData
    greeks = market_data.get("greeks", {})
    option_data = OptionData(
        symbol=inst_id,
        strike=strike,
        expiry=expiry_str,
        days_to_expiry=days_to_expiry,
        option_type=option_type,
        iv=float(market_data.get('mark_iv', 0)),
        bid=float(market_data.get('best_bid', 0)),
        ask=float(market_data.get('best_ask', 0)),
        mid_price=float(market_data.get('mid_price', 0)),
        delta=float(greeks.get('delta', 0)),
        net_delta=float(greeks.get('delta', 0)),
        gamma=float(greeks.get('gamma', 0)),
        vega=float(greeks.get('vega', 0)),
        theta=float(greeks.get('theta', 0)),
        rho=float(greeks.get('rho', 0)),
        open_interest=int(market_data.get('open_interest', 0))
    )
    
    print(f"✅ 获取期权数据: {inst_id}")
    print(f"   Mid: {option_data.mid_price:.4f} | IV: {option_data.iv:.1%} | Δ: {option_data.delta:.3f}")
    
    return option_data


def create_calendar_spread_from_symbols(
    short_symbol: str,
    long_symbol: str,
    crypto_notional: float = 1.0,
    simulated: bool = False
) -> CalendarSpreadOpportunity:
    """
    从期权 symbol 创建 CalendarSpreadOpportunity
    
    Args:
        short_symbol: 短期期权 symbol (要买回平仓的)
        long_symbol: 长期期权 symbol (要卖出平仓的)
        crypto_notional: 持仓数量（币本位）
        simulated: 是否模拟盘
    
    Returns:
        CalendarSpreadOpportunity 对象
    """
    print(f"\n{'='*70}")
    print(f"🔨 构建 Calendar Spread 对象")
    print(f"{'='*70}")
    print(f"   Short (买回): {short_symbol}")
    print(f"   Long (卖出): {long_symbol}")
    print(f"   数量: {crypto_notional} 币")
    print(f"   环境: {'模拟盘' if simulated else '实盘'}")
    
    # 获取期权数据
    print(f"\n📡 从 OKX 获取期权数据...")
    short_option = fetch_option_data_from_okx(short_symbol, simulated)
    long_option = fetch_option_data_from_okx(long_symbol, simulated)
    
    # 计算关键指标
    iv_spread = short_option.iv - long_option.iv
    iv_spread_pct = iv_spread / long_option.iv if long_option.iv > 0 else 0
    time_gap_days = long_option.days_to_expiry - short_option.days_to_expiry
    net_premium = long_option.mid_price - short_option.mid_price
    
    # 简化的盈利潜力估算
    max_profit_potential = abs(short_option.theta - long_option.theta) * time_gap_days / 365 * 30
    
    # 信号强度（平仓时不重要）
    signal_strength = "WEAK"
    
    # 构建机会对象
    opportunity = CalendarSpreadOpportunity(
        rank=1,
        short_option=short_option,
        long_option=long_option,
        iv_spread=iv_spread,
        iv_spread_pct=iv_spread_pct,
        time_gap_days=time_gap_days,
        net_premium=net_premium,
        max_profit_potential=max_profit_potential,
        signal_strength=signal_strength,
        open_status=True,  # 标记为已开仓
        contracts=crypto_notional  # 设置持仓数量
    )
    
    print(f"\n✅ Calendar Spread 对象已创建")
    print(f"   IV价差: {iv_spread:+.1%} ({iv_spread_pct:+.1%})")
    print(f"   时间间隔: {time_gap_days}天")
    print(f"   净保险费: {net_premium:+.4f}")
    
    return opportunity


def close_calendar_spread_position(
    short_symbol: str,
    long_symbol: str,
    crypto_notional: float = 1.0,
    simulated: bool = False,
    use_aggressive: bool = False
):
    """
    平仓 Calendar Spread 持仓
    
    Args:
        short_symbol: 短期期权 symbol (开仓时卖出的，现在要买回)
        long_symbol: 长期期权 symbol (开仓时买入的，现在要卖出)
        crypto_notional: 持仓数量（币本位）
        simulated: 是否模拟盘
        use_aggressive: 是否使用激进模式（立即成交）
    """
    print(f"\n{'='*70}")
    print(f"🚀 开始平仓 Calendar Spread")
    print(f"{'='*70}")
    
    # 1. 构建 Calendar Spread 对象
    opportunity = create_calendar_spread_from_symbols(
        short_symbol=short_symbol,
        long_symbol=long_symbol,
        crypto_notional=crypto_notional,
        simulated=simulated
    )
    
    # 2. 调用平仓函数（内部已经处理了异步）
    print(f"\n{'='*70}")
    print(f"📤 执行异步协同平仓")
    print(f"{'='*70}")
    print(f"   模式: {'激进（立即成交）' if use_aggressive else '保守（挂单等待）'}")
    
    # close_calendar_spread_async 内部有 asyncio.run()，所以直接调用即可
    result = close_calendar_spread_async(
        opportunity=opportunity,
        crypto_notional=crypto_notional,
        simulated=simulated,
        aggressive=use_aggressive
    )
    
    # 3. 显示结果
    print(f"\n{'='*70}")
    print(f"📊 平仓结果")
    print(f"{'='*70}")
    
    if result.get("success"):
        print(f"✅ 平仓成功！")
        print(f"   总耗时: {result.get('total_time', 0):.2f}秒")
        
        short_close = result.get("short_close")
        long_close = result.get("long_close")
        
        if short_close:
            print(f"\n   📉 Short腿 (买回):")
            print(f"      订单ID: {short_close.order_id}")
            print(f"      成交价: {short_close.avg_px:.4f}")
            print(f"      成交量: {short_close.filled_sz}")
            print(f"      状态: {short_close.status}")
        
        if long_close:
            print(f"\n   📈 Long腿 (卖出):")
            print(f"      订单ID: {long_close.order_id}")
            print(f"      成交价: {long_close.avg_px:.4f}")
            print(f"      成交量: {long_close.filled_sz}")
            print(f"      状态: {long_close.status}")
        
        # 等待2秒后获取P&L
        print(f"\n⏳ 等待2秒后获取P&L详情...")
        import time
        time.sleep(2)
        
        # 获取订单详情和P&L
        client = OKXOptionsClient(simulated=simulated)
        
        total_pnl = 0.0
        total_fee = 0.0
        
        if short_close and short_close.order_id:
            short_details = client.get_order_details(short_close.symbol, short_close.order_id)
            if short_details:
                short_pnl = float(short_details.get('pnl', 0))
                short_fee = float(short_details.get('fee', 0))
                total_pnl += short_pnl
                total_fee += short_fee
                print(f"\n   💰 Short腿 P&L:")
                print(f"      盈亏: {short_pnl:+.8f}")
                print(f"      手续费: {short_fee:+.8f}")
        
        if long_close and long_close.order_id:
            long_details = client.get_order_details(long_close.symbol, long_close.order_id)
            if long_details:
                long_pnl = float(long_details.get('pnl', 0))
                long_fee = float(long_details.get('fee', 0))
                total_pnl += long_pnl
                total_fee += long_fee
                print(f"\n   💰 Long腿 P&L:")
                print(f"      盈亏: {long_pnl:+.8f}")
                print(f"      手续费: {long_fee:+.8f}")
        
        print(f"\n{'='*70}")
        print(f"💰 总计")
        print(f"{'='*70}")
        print(f"   总盈亏: {total_pnl:+.8f} 币")
        print(f"   总手续费: {total_fee:+.8f} 币")
        print(f"   净盈亏: {(total_pnl + total_fee):+.8f} 币")
        
    else:
        print(f"❌ 平仓失败")
        print(f"   错误: {result.get('error', 'Unknown error')}")
    
    return result


def main():
    """主函数 - 示例用法"""
    
    # ==================== 配置参数 ====================
    # 🔴 请根据你的实际持仓修改以下参数
    
    SHORT_SYMBOL = "ETH-USD-251121-3100-C"  # 短期 Call (开仓时卖出的，现在要买回)
    LONG_SYMBOL = "ETH-USD-251226-3100-C"   # 长期 Call (开仓时买入的，现在要卖出)
    CRYPTO_NOTIONAL = 1.0  # 持仓数量（ETH）
    SIMULATED = False  
    USE_AGGRESSIVE = False  # True=立即成交, False=挂单等待
    
    # 📝 格式说明：
    # - 格式: {币种}-USD-{到期日YYMMDD}-{执行价}-{C/P}
    # - 例如: ETH-USD-251121-3100-C
    #   - ETH: 币种
    #   - 251121: 2025年11月21日
    #   - 3100: 执行价 $3,100
    #   - C: Call 看涨期权 (P 为 Put 看跌期权)
    
    # ==================== 执行平仓 ====================
    
    print(f"\n{'='*70}")
    print(f"🎯 手动平仓 Calendar Spread 工具")
    print(f"{'='*70}")
    print(f"   环境: {'🧪 模拟盘' if SIMULATED else '🔴 实盘'}")
    print(f"   模式: {'⚡ 激进（立即成交）' if USE_AGGRESSIVE else '💰 保守（挂单等待）'}")
    print(f"   数量: {CRYPTO_NOTIONAL} 币")
    print(f"\n🚀 开始执行平仓操作...")
    
    # 执行平仓（内部已经处理了异步）
    result = close_calendar_spread_position(
        short_symbol=SHORT_SYMBOL,
        long_symbol=LONG_SYMBOL,
        crypto_notional=CRYPTO_NOTIONAL,
        simulated=SIMULATED,
        use_aggressive=USE_AGGRESSIVE
    )
    
    print(f"\n✅ 操作完成！")


if __name__ == "__main__":
    main()

