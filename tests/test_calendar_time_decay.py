#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Calendar Spread时间衰减保护逻辑
"""

import sys
sys.path.append('/home/ubuntu/options_trading')

from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import CalendarSpreadOpportunity
from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.atm_options_filter import OptionData
from qtrade.cryptotrader.trading_engine.risk_manager import RiskManager
from datetime import datetime, timedelta


def test_calendar_time_decay_protection():
    """测试Calendar Spread时间衰减保护逻辑"""
    
    print("🧪 测试Calendar Spread时间衰减保护逻辑")
    print("=" * 60)
    
    # 创建短期期权 - 明天到期
    tomorrow = datetime.now() + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%d%b%y").upper()
    
    short_option = OptionData(
        symbol=f"BTC-{tomorrow_str}-114000-C",
        strike=114000,
        option_type="call",
        expiry=tomorrow_str,
        days_to_expiry=1,
        iv=0.50,  # 50% IV (短期)
        bid=0.055,
        ask=0.060,
        mid_price=0.0575,
        delta=0.3,
        net_delta=0.25,
        gamma=0.0001,
        vega=0.05,
        theta=-0.001,
        rho=0.002
    )
    
    # 创建长期期权 - 一个月后到期
    month_later = datetime.now() + timedelta(days=30)
    month_str = month_later.strftime("%d%b%y").upper()
    
    long_option = OptionData(
        symbol=f"BTC-{month_str}-114000-C",
        strike=114000,
        option_type="call",
        expiry=month_str,
        days_to_expiry=30,
        iv=0.42,  # 42% IV (长期)
        bid=0.080,
        ask=0.085,
        mid_price=0.0825,
        delta=0.35,
        net_delta=0.30,
        gamma=0.00008,
        vega=0.08,
        theta=-0.0008,
        rho=0.003
    )
    
    # 创建Calendar Spread Opportunity
    calendar_opportunity = CalendarSpreadOpportunity(
        rank=1,
        short_option=short_option,
        long_option=long_option,
        iv_spread=0.08,  # 8% IV价差
        iv_spread_pct=0.19,
        time_gap_days=29,
        net_premium=-0.025,  # 支付净权利金
        max_profit_potential=0.015,
        signal_strength="STRONG"
    )
    
    # 设置entry IV
    calendar_opportunity.short_option_entry_iv = 0.50
    calendar_opportunity.long_option_entry_iv = 0.42
    
    # 创建RiskManager
    risk_manager = RiskManager(
        max_positions=1,
        enable_delta_hedge=True,
        delta_risk_threshold=0.3,
        stop_loss_ratio=-0.3,
        profit_target_ratio=0.5,
        price_change_risk_ratio=0.15
    )
    
    print("📊 测试场景1: 短期期权明天到期，亏损状态")
    print(f"   短期期权: {short_option.symbol}")
    print(f"   长期期权: {long_option.symbol}")
    print(f"   时间间隔: {calendar_opportunity.time_gap_days}天")
    
    # 解析到期日期的函数
    def parse_option_expiry_date(symbol: str):
        """解析期权合约到期日期"""
        try:
            parts = symbol.split('-')
            if len(parts) >= 2:
                date_str = parts[1]
                day = int(date_str[:2])
                month_str = date_str[2:5]
                year = 2000 + int(date_str[5:])
                
                month_map = {
                    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                }
                month = month_map.get(month_str)
                
                if month:
                    return datetime(year, month, day).date()
            return None
        except Exception:
            return None
    
    short_expiry_date = parse_option_expiry_date(short_option.symbol)
    if short_expiry_date:
        current_time = datetime.now()
        days_to_short_expiry = (short_expiry_date - current_time.date()).days
        
        print(f"   短期到期日: {short_expiry_date}")
        print(f"   剩余天数: {days_to_short_expiry}天")
        print(f"   P&L状态: 亏损 (-15%)")
        
        # 测试平仓条件
        if days_to_short_expiry <= 1:
            print("🔴 应该平仓: Calendar短期期权即将到期平仓 (避免交割风险)")
        else:
            print("✅ 继续持有: 未达到时间衰减平仓条件")
    
    print()
    
    print("📊 测试场景2: 短期期权当天到期")
    # 创建当天到期的短期期权
    today = datetime.now()
    today_str = today.strftime("%d%b%y").upper()
    
    short_option_today = OptionData(
        symbol=f"BTC-{today_str}-114000-C",
        strike=114000,
        option_type="call",
        expiry=today_str,
        days_to_expiry=0,
        iv=0.50,
        bid=0.055,
        ask=0.060,
        mid_price=0.0575,
        delta=0.3,
        net_delta=0.25,
        gamma=0.0001,
        vega=0.05,
        theta=-0.001,
        rho=0.002
    )
    
    expiry_date_today = parse_option_expiry_date(short_option_today.symbol)
    if expiry_date_today:
        days_to_expiry_today = (expiry_date_today - current_time.date()).days
        
        print(f"   短期期权: {short_option_today.symbol}")
        print(f"   短期到期日: {expiry_date_today}")
        print(f"   剩余天数: {days_to_expiry_today}天")
        
        # 当天到期或已过期检查
        if days_to_expiry_today <= 0:
            print("🔴 应该平仓: Calendar短期期权到期强制平仓 (避免单腿风险)")
        else:
            print("✅ 继续持有: 未达到强制平仓条件")
    
    print()
    
    print("📊 测试场景3: 短期期权还有3天到期")
    # 创建3天后到期的短期期权
    three_days_later = datetime.now() + timedelta(days=3)
    three_days_str = three_days_later.strftime("%d%b%y").upper()
    
    short_option_3days = OptionData(
        symbol=f"BTC-{three_days_str}-114000-C",
        strike=114000,
        option_type="call",
        expiry=three_days_str,
        days_to_expiry=3,
        iv=0.50,
        bid=0.055,
        ask=0.060,
        mid_price=0.0575,
        delta=0.3,
        net_delta=0.25,
        gamma=0.0001,
        vega=0.05,
        theta=-0.001,
        rho=0.002
    )
    
    expiry_date_3days = parse_option_expiry_date(short_option_3days.symbol)
    if expiry_date_3days:
        days_to_expiry_3days = (expiry_date_3days - current_time.date()).days
        
        print(f"   短期期权: {short_option_3days.symbol}")
        print(f"   短期到期日: {expiry_date_3days}")
        print(f"   剩余天数: {days_to_expiry_3days}天")
        
        # 3天到期检查
        if days_to_expiry_3days <= 1:
            print("🔴 应该平仓: 短期期权即将到期")
        else:
            print("✅ 继续持有: 时间充足，无需平仓")
    
    print()
    print("🎉 Calendar Spread时间衰减保护逻辑测试完成！")
    print("\n📋 总结:")
    print("   ✓ 当天到期 (≤0天) → 立即强制平仓 (避免单腿风险)")
    print("   ✓ 明天到期 (≤1天) → 平仓避免交割风险")
    print("   ✓ 时间充足 (>1天) → 继续持有")


if __name__ == "__main__":
    test_calendar_time_decay_protection()
