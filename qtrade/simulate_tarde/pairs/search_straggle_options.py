import numpy as np
import pandas as pd

def extract_best_pairs_for_selling(call_list, put_list, realized_vol, iv_threshold_pct):
    if not call_list or not put_list or realized_vol is None:
        return None
    
    # 筛选IV足够高的期权
    valid_calls = [
        call for call in call_list 
        if call['iv'] - realized_vol >= iv_threshold_pct
    ]
    
    valid_puts = [
        put for put in put_list 
        if put['iv'] - realized_vol >= iv_threshold_pct
    ]
    
    if not valid_calls or not valid_puts:
        return None
    
    # 找到平均IV最高的配对
    best_pair = None
    best_avg_iv = 0
    
    for call in valid_calls:
        for put in valid_puts:
            avg_iv = (call['iv'] + put['iv']) / 2
            if avg_iv > best_avg_iv:
                best_avg_iv = avg_iv
                best_pair = {
                    'call': call,
                    'put': put,
                    'avg_iv': avg_iv,
                    'call_iv_premium': call['iv'] - realized_vol,
                    'put_iv_premium': put['iv'] - realized_vol
                }
    
    return best_pair

def find_sell_straggle_opportunity(atm_options, 
                            threshold, 
                            min_days_to_expire= 7, 
                            max_days_to_expire= 25, 
                            realized_vol=None, 
                            iv_threshold_pct=0.05,
                            side="sell"):

    # fillter options whose strke price is between spot_price(1-threshold) and spot_price(1+threshold)
    if not atm_options:
        return None
    
    # 获取现货价格
    spot_price = atm_options[0].get('spot_open', atm_options[0].get('spot_price', None))
    if spot_price is None:
        return None
    
    # 计算价格范围
    min_strike = spot_price * (1 - threshold)
    max_strike = spot_price * (1 + threshold)
    
    # 筛选期权并按天数分组
    options_by_days = {}
    
    for opt in atm_options:
        # 检查到期天数
        if min_days_to_expire <= opt['days_to_expiry'] <= max_days_to_expire:
            # 检查执行价格范围
            if min_strike <= opt['strike_price'] <= max_strike:
                days = opt['days_to_expiry']
                
                # 初始化该天数的字典
                if days not in options_by_days:
                    options_by_days[days] = [[], []]  # [calls, puts]
                
                # 分类添加期权
                if opt['option_type'] == 'C' and opt['strike_price'] > spot_price:
                    options_by_days[days][0].append(opt)  # 添加到calls列表
                elif opt['option_type'] == 'P' and opt['strike_price'] < spot_price:
                    options_by_days[days][1].append(opt)  # 添加到puts列表
    
    best_options = []
    if side == "sell":
        for days in options_by_days:
            best_selling_pair = extract_best_pairs_for_selling(options_by_days[days][0], options_by_days[days][1], realized_vol, iv_threshold_pct)
            if best_selling_pair:
                best_options.append(best_selling_pair)
    
    else:
        pass 


    if best_options == []:
        return None
    
    # extract best pairs for selling based on smallest combined delta 
    best_options = sorted(best_options, key=lambda x: abs(x['call']['pa_delta'] + x['put']['pa_delta']))
    
    # 🔄 修改返回格式，兼容 StraddlePair 期望的格式
    best_pair = best_options[0]
    
    # 获取现货价格
    spot_price = atm_options[0].get('spot_open', atm_options[0].get('spot_price', None))
    
    # 转换为兼容格式
    straddle_config = {
        'call_option': best_pair['call'],
        'put_option': best_pair['put']
    }
    
    return {
        'straddle': straddle_config,
        'strategy_type': 'short_straddle', # actually short_straggle, just for compatibility
        'iv_premium': best_pair.get('call_iv_premium', 0) + best_pair.get('put_iv_premium', 0), 
        'avg_iv': best_pair.get('avg_iv', 0),
        'realized_vol': realized_vol,
        'days_to_expiry': best_pair['call']['days_to_expiry'],
        'iv_condition_met': True,
        'spot_price': spot_price,
        'strike_range': f"${spot_price * (1-threshold):.0f}-${spot_price * (1+threshold):.0f}",
        'selected_strike': best_pair['call']['strike_price']
    }



def extract_best_pairs_for_buying(call_list, put_list, realized_vol, iv_threshold_pct):
    """
    Extract best call-put pairs for BUYING straggle options
    Logic: Buy when IV is LOW relative to realized volatility (expecting volatility expansion)
    """
    if not call_list or not put_list or realized_vol is None:
        return None
    
    # 筛选IV足够低的期权 (opposite of selling - we want cheap options)
    valid_calls = [
        call for call in call_list 
        if realized_vol - call['iv'] >= iv_threshold_pct  # IV should be BELOW RV
    ]
    
    valid_puts = [
        put for put in put_list 
        if realized_vol - put['iv'] >= iv_threshold_pct   # IV should be BELOW RV
    ]
    
    if not valid_calls or not valid_puts:
        return None
    
    # 找到平均IV最低的配对 (cheapest options for buying)
    best_pair = None
    best_avg_iv = float('inf')  # Start with infinity, find minimum
    
    for call in valid_calls:
        for put in valid_puts:
            avg_iv = (call['iv'] + put['iv']) / 2
            if avg_iv < best_avg_iv:  # Find LOWEST IV (cheapest)
                best_avg_iv = avg_iv
                best_pair = {
                    'call': call,
                    'put': put,
                    'avg_iv': avg_iv,
                    'call_iv_discount': realized_vol - call['iv'],  # How cheap call is
                    'put_iv_discount': realized_vol - put['iv']     # How cheap put is
                }
    
    return best_pair


def find_buy_straggle_opportunity(atm_options, 
                            threshold, 
                            min_days_to_expire= 15, 
                            max_days_to_expire= 35, 
                            realized_vol=None, 
                            iv_threshold_pct=0.05,
                            side="buy"):
    """
    Find opportunities to BUY straggle options (long strangle)
    
    Strategy: Buy OTM calls and puts when IV is low relative to expected volatility
    Expecting: Volatility expansion, large price moves in either direction
    
    Args:
        threshold: Price range around spot (e.g., 0.01 for ±1%)
        iv_threshold_pct: Minimum discount of IV below RV (default 5%)
        side: "buy" for long straggle
    
    Returns:
        dict: Long straggle opportunity or None
    """
    
    # Filter options whose strike price is between spot_price(1-threshold) and spot_price(1+threshold)
    if not atm_options:
        return None
    
    # 获取现货价格
    spot_price = atm_options[0].get('spot_open', atm_options[0].get('spot_price', None))
    if spot_price is None:
        return None
    
    # 计算价格范围
    min_strike = spot_price * (1 - threshold)
    max_strike = spot_price * (1 + threshold)
    
    # 筛选期权并按天数分组
    options_by_days = {}
    
    for opt in atm_options:
        # 检查到期天数
        if min_days_to_expire <= opt['days_to_expiry'] <= max_days_to_expire:
            # 检查执行价格范围
            if min_strike <= opt['strike_price'] <= max_strike:
                days = opt['days_to_expiry']
                
                # 初始化该天数的字典
                if days not in options_by_days:
                    options_by_days[days] = [[], []]  # [calls, puts]
                
                # 分类添加期权 (same logic as selling - OTM options)
                if opt['option_type'] == 'C' and opt['strike_price'] > spot_price:
                    options_by_days[days][0].append(opt)  # 添加到calls列表
                elif opt['option_type'] == 'P' and opt['strike_price'] < spot_price:
                    options_by_days[days][1].append(opt)  # 添加到puts列表
    
    best_options = []
    if side == "buy":
        for days in options_by_days:
            best_buying_pair = extract_best_pairs_for_buying(
                options_by_days[days][0], 
                options_by_days[days][1], 
                realized_vol, 
                iv_threshold_pct
            )
            if best_buying_pair:
                best_options.append(best_buying_pair)
    else:
        pass 

    if best_options == []:
        return None
    
    # Extract best pairs for buying based on smallest combined delta (most delta-neutral)
    best_options = sorted(best_options, key=lambda x: abs(x['call']['pa_delta'] + x['put']['pa_delta']))
    
    # 修改返回格式，兼容 StraddlePair 期望的格式
    best_pair = best_options[0]
    
    # 转换为兼容格式
    straddle_config = {
        'call_option': best_pair['call'],
        'put_option': best_pair['put']
    }
    
    return {
        'straddle': straddle_config,
        'strategy_type': 'long_straddle',  # Actually long_straggle (long strangle)
        'iv_discount': best_pair.get('call_iv_discount', 0) + best_pair.get('put_iv_discount', 0), 
        'avg_iv': best_pair.get('avg_iv', 0),
        'realized_vol': realized_vol,
        'days_to_expiry': best_pair['call']['days_to_expiry'],
        'iv_condition_met': True,
        'spot_price': spot_price,
        'strike_range': f"${spot_price * (1-threshold):.0f}-${spot_price * (1+threshold):.0f}",
        'selected_strike': best_pair['call']['strike_price']
    }