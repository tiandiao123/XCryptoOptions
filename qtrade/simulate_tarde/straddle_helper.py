# qtrade/simulate_tarde/straddle_helper.py

import os
import numpy as np
from qtrade.simulate_tarde.data_loader.data_utils import get_option_full_info


def print_straddle_opening_info(straddle_pair, straddle_opportunity, spot, time_obj, 
                               predicted_vol, vol_model, vol_result, iv_1month):
    """
    打印Straddle开仓持仓的详细信息
    
    Args:
        straddle_pair: StraddlePair对象
        straddle_opportunity: 选中的straddle机会
        spot: 现货价格
        time_obj: 时间对象
        predicted_vol: 预测波动率
        vol_model: 波动率模型名称
        vol_result: 完整的波动率结果字典
        iv_1month: 1月期ATM IV信息
    """
    print(f"===============================  📥 开仓新Straddle持仓 =================================")
    print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
    print(f"   策略: {straddle_opportunity['strategy_type'].replace('_', ' ').title()}")
    print(f"   执行价格: ${straddle_pair.strike_price:,.2f}")
    print(f"   现货价格: ${spot:,.2f}")
    print(f"   入场权利金: {straddle_pair.entry_premium:.6f} BTC")
    
    # 波动率对比
    print(f"\n📊 波动率分析:")
    if predicted_vol:
        print(f"   {vol_model}预测波动率: {predicted_vol:.1%}")
        ewma_vol = vol_result.get('ewma_vol_annualized')
        if vol_model == "GARCH" and ewma_vol:
            print(f"   EWMA波动率: {ewma_vol:.1%}")
    else:
        print(f"   预测波动率: 数据不足")
    
    if 'atm_iv_1month' in iv_1month:
        atm_iv = iv_1month['atm_iv_1month']
        option_count = iv_1month['option_count']
        print(f"   1月ATM IV: {atm_iv:.1%} (样本: {option_count})")
        
        if predicted_vol:
            iv_premium = atm_iv - predicted_vol
            print(f"   IV溢价: {iv_premium:+.1%} ({'高估' if iv_premium > 0 else '低估'})")
    elif 'error' in iv_1month:
        print(f"   1月ATM IV: 无可用数据")
    
    # Straddle具体信息
    if 'iv_premium' in straddle_opportunity:
        print(f"   IV vs RV: {straddle_opportunity.get('avg_iv', 0):.1%} vs {straddle_opportunity.get('realized_vol', 0):.1%} (溢价: {straddle_opportunity.get('iv_premium', 0):+.1%})")
    
    # 合约信息
    print(f"\n📋 合约信息:")
    print(f"   Call: {straddle_pair.call_price:.6f} BTC ({straddle_pair.option_symbols['call']})")
    print(f"   Put: {straddle_pair.put_price:.6f} BTC ({straddle_pair.option_symbols['put']})")
    print(f"   到期时间: {straddle_opportunity.get('days_to_expiry', 'N/A')}天")
    
    # IV和Delta信息
    print(f"   Call IV: {straddle_pair.call_iv:.1%}, Put IV: {straddle_pair.put_iv:.1%}")
    print(f"   Call Delta: {straddle_pair.call_delta:.3f}, Put Delta: {straddle_pair.put_delta:.3f}")
    
    # Delta分析
    net_delta = straddle_pair.get_net_delta()
    print(f"\n🔄 Delta分析:")
    print(f"   当前净Delta: {net_delta:+.3f}")
    print(f"   Moneyness: {spot / straddle_pair.strike_price:.3f}")
    
    if abs(net_delta) > 0.05:
        print(f"   ⚠️  建议考虑Delta对冲 (|净Delta| = {abs(net_delta):.3f} > 0.05)")
        delta_exposure_btc = abs(net_delta)
        delta_exposure_usd = delta_exposure_btc * spot
        print(f"   Delta敞口: ~{delta_exposure_btc:.3f} BTC (~${delta_exposure_usd:,.0f})")
    else:
        print(f"   ✅ Delta在可接受范围内")


def print_straddle_closing_info(straddle_pair, close_info, reason, time_obj, spot, final_pnl,
                               call_current=None, put_current=None, total_asset=None):
    """
    打印Straddle平仓持仓的详细信息
    
    Args:
        straddle_pair: StraddlePair对象
        close_info: 平仓信息字典
        reason: 平仓原因
        time_obj: 平仓时间
        spot: 现货价格
        final_pnl: 最终P&L
        call_current: Call期权当前信息（可选）
        put_current: Put期权当前信息（可选）
        total_asset: 总资产（可选）
    """
    print(f"\n📤 Straddle平仓: {reason}")
    print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
    print(f"   策略类型: {close_info['strategy_type']}")
    print(f"   期权P&L: {close_info.get('final_options_pnl', close_info.get('final_pnl', 0)):.6f} BTC")
    
    # 期权价格信息
    print(f"   Call: {straddle_pair.call_price:.6f} BTC ({straddle_pair.option_symbols['call']})")
    print(f"   Put: {straddle_pair.put_price:.6f} BTC ({straddle_pair.option_symbols['put']})")
    
    # 平仓时的IV和Delta信息
    if call_current and put_current:
        print(f"   平仓IV: Call {call_current['iv_percent']:.1f}% vs Put {put_current['iv_percent']:.1f}%")
        print(f"   平仓Delta: Call {call_current['delta']:.3f} vs Put {put_current['delta']:.3f} (净Delta: {call_current['delta'] + put_current['delta']:+.3f})")
    else:
        print(f"   ⚠️  无法获取平仓时希腊字母信息")
    
    # 各合约P&L
    if 'contract_pnl' in close_info:
        contract_pnl = close_info['contract_pnl']
        print(f"   期权合约P&L: Call:{contract_pnl['call']:+.6f} Put:{contract_pnl['put']:+.6f}")
    
    # Delta对冲P&L信息
    if straddle_pair.delta_hedge_enabled:
        print(f"   永续浮动P&L: {straddle_pair.inverse_perpetual_pnl:.6f} BTC")
        print(f"   已实现永续合约P&L: {straddle_pair.realized_perpetual_pnl:.6f} BTC")
        print(f"   总P&L: {final_pnl:.6f} BTC")
        print(f"   平均持仓价: ${close_info.get('closing_average_price', 0):,.0f}")
        print(f"   平仓现货价: ${close_info.get('closing_spot_price', 0):,.0f}")
    else:
        print(f"   总P&L: {final_pnl:.6f} BTC")
    
    if total_asset is not None:
        print(f"   总资产: {total_asset:.6f} BTC")
    print(f"   现货价格: ${spot:,.0f}")
    print(f"   Moneyness: {spot / straddle_pair.strike_price:.3f}")


def should_exclude_straddle_trade(straddle_pair, close_info, current_spot_price, print_info=False):
    """
    检查是否应该排除Straddle交易的P&L（因为数据异常）
    
    Args:
        straddle_pair: Straddle组合对象
        close_info: 平仓信息
        current_spot_price: 当前现货价格
        print_info: 是否打印信息
        
    Returns:
        tuple: (should_exclude, reason)
    """
    spot_change_ratio = abs(current_spot_price - straddle_pair.entry_spot_price) / straddle_pair.entry_spot_price
    spot_change_ratio_threshold = 0.02

    try:
        # 1. 检查单个期权IV是否异常
        if straddle_pair.call_iv < 0.05 or straddle_pair.call_iv > 2.0:
            if print_info:
                print(f"⚠️  Call期权IV异常: {straddle_pair.call_iv:.1%}")
            return True, f"call_iv_abnormal: {straddle_pair.call_iv:.1%}"
        
        if straddle_pair.put_iv < 0.05 or straddle_pair.put_iv > 2.0:
            if print_info:
                print(f"⚠️  Put期权IV异常: {straddle_pair.put_iv:.1%}")
            return True, f"put_iv_abnormal: {straddle_pair.put_iv:.1%}"
        
        # 2. 检查IV变化是否过大
        if hasattr(straddle_pair, 'entry_greeks'):
            call_iv_change = abs(straddle_pair.call_iv - straddle_pair.entry_greeks['call_option']['iv'])
            put_iv_change = abs(straddle_pair.put_iv - straddle_pair.entry_greeks['put_option']['iv'])
            
            iv_change_threshold = 0.40  # 40%变化阈值
            if call_iv_change > iv_change_threshold and spot_change_ratio <= spot_change_ratio_threshold:
                if print_info:
                    print(f"⚠️  Call期权IV变化过大: {call_iv_change:.1%}")
                return True, f"call_iv_change_excessive: {call_iv_change:.1%}"
            
            if put_iv_change > iv_change_threshold and spot_change_ratio <= spot_change_ratio_threshold:
                if print_info:
                    print(f"⚠️  Put期权IV变化过大: {put_iv_change:.1%}")
                return True, f"put_iv_change_excessive: {put_iv_change:.1%}"
        
        # 3. 检查P&L是否过度异常（可能是数据错误）
        pnl_pct = close_info.get('pnl_total_pct', close_info.get('pnl_pct', 0))
        if abs(pnl_pct) > 5.0:  # P&L超过500%可能是数据问题
            if print_info:
                print(f"⚠️  P&L异常: {pnl_pct*100:.1f}%")
            return True, f"pnl_excessive: {pnl_pct*100:.1f}%"
        
        return False, "valid_trade"
        
    except Exception as e:
        return True, f"exception_in_validation: {str(e)}"


def log_excluded_straddle_trade(straddle_pair, close_info, exclude_reason, time_obj, spot, 
                               final_pnl, total_asset, log_file_path):
    """
    将被排除Straddle异常交易的详细信息记录到日志文件
    """
    try:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"🚫 Straddle异常交易记录 - {time_obj.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*80}\n")
            
            # 基本信息
            f.write(f"排除原因: {exclude_reason}\n")
            f.write(f"平仓原因: {close_info.get('reason', 'Unknown')}\n")
            f.write(f"策略类型: {close_info['strategy_type']}\n")
            f.write(f"被排除P&L: {final_pnl:.6f} BTC (不计入总资产)\n")
            f.write(f"总资产保持: {total_asset:.6f} BTC\n")
            f.write(f"现货价格: ${spot:,.0f}\n")
            
            # 现货变化分析
            spot_change_rate = abs(spot - straddle_pair.entry_spot_price) / straddle_pair.entry_spot_price
            spot_direction = "上涨" if spot > straddle_pair.entry_spot_price else "下跌" if spot < straddle_pair.entry_spot_price else "持平"
            f.write(f"现货变化: ${straddle_pair.entry_spot_price:,.0f} → ${spot:,.0f} ({spot_direction} {spot_change_rate:.2%})\n")
            f.write(f"Moneyness变化: {straddle_pair.entry_spot_price/straddle_pair.strike_price:.3f} → {spot/straddle_pair.strike_price:.3f}\n")
            
            # IV变化详情
            if hasattr(straddle_pair, 'entry_greeks'):
                f.write(f"\n📊 IV变化分析:\n")
                f.write(f"   Call IV变化: {straddle_pair.entry_greeks['call_option']['iv']:.1%} → {straddle_pair.call_iv:.1%}\n")
                f.write(f"   Put IV变化: {straddle_pair.entry_greeks['put_option']['iv']:.1%} → {straddle_pair.put_iv:.1%}\n")
            
            # 期权价格变化详情
            f.write(f"\n💰 期权价格变化详情:\n")
            f.write(f"   Call期权: {straddle_pair.call_price:.6f} BTC\n")
            f.write(f"   Put期权: {straddle_pair.put_price:.6f} BTC\n")
            f.write(f"   入场权利金: {straddle_pair.entry_premium:.6f} BTC\n")
            
            # 期权合约信息
            f.write(f"\n📋 期权合约:\n")
            f.write(f"   Call: {straddle_pair.option_symbols['call']} (${straddle_pair.strike_price:,.0f})\n")
            f.write(f"   Put: {straddle_pair.option_symbols['put']} (${straddle_pair.strike_price:,.0f})\n")
            
            # 时间信息
            f.write(f"\n⏰ 时间信息:\n")
            f.write(f"   入场时间: {straddle_pair.entry_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"   平仓时间: {time_obj.strftime('%Y-%m-%d %H:%M:%S')}\n")
            holding_hours = (time_obj - straddle_pair.entry_time).total_seconds() / 3600
            f.write(f"   持仓时长: {holding_hours:.1f}小时\n")
            
            f.write(f"\n")
            
    except Exception as e:
        print(f"⚠️  Straddle异常交易日志写入失败: {e}")