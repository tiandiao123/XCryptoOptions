
import os
from pprint import pprint
import time
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np
import sys
from tqdm import tqdm

from qtrade.data_utils import get_option_full_info
from qtrade.simulate_tarde.pairs.calendar_pair import CalendarPair, find_atm_calendar_pair

def calculate_atm_iv_1month(atm_options):
    """
    计算1个月ATM期权的IV均值
    
    Args:
        atm_options: ATM期权列表
        
    Returns:
        dict: 1个月ATM IV指标
    """
    if not atm_options:
        return {}
    
    # 筛选1个月期权 (25-35天)
    one_month_options = [opt for opt in atm_options if 25 <= opt['days_to_expiry'] <= 35]
    
    if not one_month_options:
        return {'error': 'no_1month_options'}
    
    # 计算1个月ATM IV均值
    ivs = [opt['iv'] for opt in one_month_options]
    
    return {
        'atm_iv_1month': np.mean(ivs),
        'atm_iv_std': np.std(ivs),
        'option_count': len(one_month_options),
        'iv_min': min(ivs),
        'iv_max': max(ivs)
    }


def should_exclude_trade_pnl(calendar_pair, close_info, current_spot_price, print_info=False):
    """
    检查是否应该排除这次交易的P&L（因为数据异常）
    
    Args:
        calendar_pair: Calendar组合对象
        close_info: 平仓信息
        print_info: 是否打印信息
        
    Returns:
        tuple: (should_exclude, reason)
    """
    spot_change_ratio = abs(current_spot_price - calendar_pair.entry_spot_price) / calendar_pair.entry_spot_price
    spot_change_ratio_threshold = 0.02

    try:
        
        # 获取入场和平仓时的IV信息
        entry_iv_spread = calendar_pair.entry_greeks['short_option']['iv'] - calendar_pair.entry_greeks['long_option']['iv']
        current_iv_spread = calendar_pair.get_iv_spread()
        
        # 1. 检查IV价差绝对值是否超过阈值
        iv_spread_threshold = 0.20  # 20%
        if abs(current_iv_spread) > iv_spread_threshold and spot_change_ratio <= spot_change_ratio_threshold:
            if print_info:
                print(f"⚠️  平仓IV价差异常: {current_iv_spread:+.1%} (阈值: ±{iv_spread_threshold:.1%})")
            return True, f"iv_spread_excessive: {current_iv_spread:+.1%}"
        
        # 2. 检查单个期权IV是否异常
        if calendar_pair.long_option_iv < 0.05 or calendar_pair.long_option_iv > 2.0:
            if print_info:
                print(f"⚠️  Long期权IV异常: {calendar_pair.long_option_iv:.1%}")
            return True, f"long_iv_abnormal: {calendar_pair.long_option_iv:.1%}"
        
        if calendar_pair.short_option_iv < 0.05 or calendar_pair.short_option_iv > 2.0:
            if print_info:
                print(f"⚠️  Short期权IV异常: {calendar_pair.short_option_iv:.1%}")
            return True, f"short_iv_abnormal: {calendar_pair.short_option_iv:.1%}"
        
        # 3. 检查IV变化是否过大
        long_iv_change = abs(calendar_pair.long_option_iv - calendar_pair.entry_greeks['long_option']['iv'])
        short_iv_change = abs(calendar_pair.short_option_iv - calendar_pair.entry_greeks['short_option']['iv'])
        
        iv_change_threshold = 0.40  # 30%变化阈值
        if long_iv_change > iv_change_threshold and spot_change_ratio <= spot_change_ratio_threshold:
            if print_info:
                print(f"⚠️  Long期权IV变化过大: {long_iv_change:.1%}")
            return True, f"long_iv_change_excessive: {long_iv_change:.1%}"
        
        if short_iv_change > iv_change_threshold and spot_change_ratio <= spot_change_ratio_threshold:
            if print_info:
                print(f"⚠️  Short期权IV变化过大: {short_iv_change:.1%}")
            return True, f"short_iv_change_excessive: {short_iv_change:.1%}"
        
        # 4. 检查P&L是否过度异常（可能是数据错误）
        pnl_pct = close_info.get('pnl_total_pct', close_info.get('pnl_pct', 0))  # 🔧 使用正确的字段名
        if abs(pnl_pct) > 5.0:  # P&L超过500%可能是数据问题
            if print_info:
                print(f"⚠️  P&L异常: {pnl_pct*100:.1f}%")
            return True, f"pnl_excessive: {pnl_pct*100:.1f}%"
        
        return False, "valid_trade"
        
    except Exception as e:
        return True, f"exception_in_validation: {str(e)}"



def update_plot(ax, line, time_list, asset_list, init_btc):
    """更新实时图表"""
    if not time_list or not asset_list:
        return
    
    # 更新数据
    line.set_data(time_list, asset_list)
    
    # 动态调整坐标轴范围
    ax.set_xlim(time_list[0], time_list[-1])
    
    # Y轴范围：稍微扩展以便观察
    y_min = min(min(asset_list), init_btc) * 0.95
    y_max = max(max(asset_list), init_btc) * 1.05
    ax.set_ylim(y_min, y_max)
    
    # 🔧 智能设置X轴时间标签 - 添加年份支持
    total_points = len(time_list)
    
    # 检查时间跨度是否超过一年
    time_span_days = (time_list[-1] - time_list[0]).days
    
    if time_span_days > 365:
        # 超过一年显示年份
        time_format = '%Y-%m-%d'
    elif time_span_days > 60:
        # 超过两个月显示月-日
        time_format = '%m-%d %H:%M'
    else:
        # 短期显示详细时间
        time_format = '%m-%d %H:%M'
    
    if total_points > 20:
        if total_points < 100:
            interval = max(1, total_points // 10)
        elif total_points < 1000:
            interval = max(1, total_points // 15)
        else:
            interval = max(1, total_points // 20)
        
        display_times = time_list[::interval]
        display_labels = [t.strftime(time_format) for t in display_times]
        
        ax.set_xticks(display_times)
        ax.set_xticklabels(display_labels, rotation=45, ha='right')
    else:
        ax.set_xticks(time_list)
        ax.set_xticklabels([t.strftime(time_format) for t in time_list], rotation=45, ha='right')
    
    # 添加当前收益信息到标题
    if asset_list:
        current_return = (asset_list[-1] - init_btc) / init_btc * 100
        # 🆕 在标题中也显示时间范围
        start_time = time_list[0].strftime('%Y-%m')
        end_time = time_list[-1].strftime('%Y-%m')
        ax.set_title(f'Calendar Spread Strategy ({start_time} to {end_time}) - Current Return: {current_return:+.2f}%', 
                    fontsize=14, fontweight='bold')
    
    # 刷新图表
    ax.figure.canvas.draw()
    ax.figure.canvas.flush_events()
    

    plt.tight_layout()


def print_opening_position_info(calendar_pair, calendar_spread_options, spot, time_obj, predicted_vol, vol_model, vol_result, iv_1month):
    """
    打印开仓持仓的详细信息
    
    Args:
        calendar_pair: CalendarPair对象
        calendar_spread_options: 选中的calendar spread机会
        spot: 现货价格
        time_obj: 时间对象
        predicted_vol: 预测波动率
        vol_model: 波动率模型名称
        vol_result: 完整的波动率结果字典
        iv_1month: 1月期ATM IV信息
    """
    print(f"===============================  📥 开仓新持仓 =================================")
    print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
    print(f"   策略: {calendar_spread_options['strategy_type']} ({calendar_spread_options.get('strategy_name', 'Unknown')})")
    print(f"   期权类型: {calendar_spread_options['option_type']} Calendar")
    print(f"   现货价格: ${spot:,.2f}")
    print(f"   入场权利金: {calendar_pair.entry_premium:.6f} BTC")
    
    # 波动率对比
    print(f"\n📊 波动率分析:")
    if predicted_vol:
        print(f"   {vol_model}预测波动率: {predicted_vol:.1%}")
        # 从vol_result中获取EWMA
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
    
    # 策略IV信息
    analysis = calendar_spread_options['analysis']
    print(f"   策略IV: 短期{analysis['short_term_iv']:.1%} vs 长期{analysis['long_term_iv']:.1%} (价差:{analysis['iv_spread']:+.1%})")
    
    # 合约信息
    print(f"\n📋 合约信息:")
    long_opt = calendar_spread_options['calendar_spread']['long_option']
    short_opt = calendar_spread_options['calendar_spread']['short_option']
    print(f"   Long ({analysis['long_term_days']}天): {calendar_pair.long_option_price:.6f} BTC ({long_opt['symbol']})")
    print(f"   Short ({analysis['short_term_days']}天): {calendar_pair.short_option_price:.6f} BTC ({short_opt['symbol']})")
    print(f"   执行价格: Long ${long_opt['strike_price']:,.0f} vs Short ${short_opt['strike_price']:,.0f}")
    
    # IV和Delta信息
    print(f"   开仓IV: Long {long_opt['iv']:.1%} vs Short {short_opt['iv']:.1%} (价差: {short_opt['iv'] - long_opt['iv']:+.1%})")
    print(f"   开仓Delta: Long {long_opt['delta']:.3f} vs Short {short_opt['delta']:.3f} (净Delta: {long_opt['delta'] - short_opt['delta']:+.3f})")
    
    # Delta分析
    net_delta = calendar_pair.get_net_delta()
    print(f"\n🔄 Delta分析:")
    print(f"   当前净Delta: {net_delta:+.3f}")
    if abs(net_delta) > 0.05:
        print(f"   ⚠️  建议考虑Delta对冲 (|净Delta| = {abs(net_delta):.3f} > 0.05)")
        # 计算大致的Delta敞口
        delta_exposure_btc = abs(net_delta)
        delta_exposure_usd = delta_exposure_btc * spot
        print(f"   Delta敞口: ~{delta_exposure_btc:.3f} BTC (~${delta_exposure_usd:,.0f})")
    else:
        print(f"   ✅ Delta在可接受范围内")


def log_excluded_trade_details(calendar_pair, close_info, exclude_reason, time_obj, spot, final_pnl, total_asset, log_file_path):
    """
    将被排除异常交易的详细信息记录到日志文件
    
    Args:
        calendar_pair: Calendar组合对象
        close_info: 平仓信息
        exclude_reason: 排除原因
        time_obj: 当前时间
        spot: 现货价格
        final_pnl: 最终P&L
        total_asset: 总资产
        log_file_path: 日志文件路径
    """
    try:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"🚫 异常交易记录 - {time_obj.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*80}\n")
            
            # 基本信息
            f.write(f"排除原因: {exclude_reason}\n")
            f.write(f"平仓原因: {close_info.get('reason', 'Unknown')}\n")
            f.write(f"策略类型: {close_info['strategy_type']}\n")
            f.write(f"被排除P&L: {final_pnl:.6f} BTC (不计入总资产)\n")
            f.write(f"总资产保持: {total_asset:.6f} BTC\n")
            f.write(f"现货价格: ${spot:,.0f}\n")
            
            # 现货变化分析
            spot_change_rate = abs(spot - calendar_pair.entry_spot_price) / calendar_pair.entry_spot_price
            spot_direction = "上涨" if spot > calendar_pair.entry_spot_price else "下跌" if spot < calendar_pair.entry_spot_price else "持平"
            f.write(f"现货变化: ${calendar_pair.entry_spot_price:,.0f} → ${spot:,.0f} ({spot_direction} {spot_change_rate:.2%})\n")
            
            # IV变化详情
            entry_iv_spread = calendar_pair.entry_greeks['short_option']['iv'] - calendar_pair.entry_greeks['long_option']['iv']
            current_iv_spread = calendar_pair.get_iv_spread()
            f.write(f"\n📊 IV变化分析:\n")
            f.write(f"   IV价差变化: {entry_iv_spread:+.1%} → {current_iv_spread:+.1%}\n")
            f.write(f"   Long IV变化: {calendar_pair.entry_greeks['long_option']['iv']:.1%} → {calendar_pair.long_option_iv:.1%}\n")
            f.write(f"   Short IV变化: {calendar_pair.entry_greeks['short_option']['iv']:.1%} → {calendar_pair.short_option_iv:.1%}\n")
            
            # 期权价格变化详情
            entry_long_price = calendar_pair.entry_greeks['long_option']['price']
            entry_short_price = calendar_pair.entry_greeks['short_option']['price']
            current_long_price = calendar_pair.long_option_price
            current_short_price = calendar_pair.short_option_price
            
            # 计算价格变化百分比
            long_price_change_pct = (current_long_price - entry_long_price) / entry_long_price if entry_long_price != 0 else 0
            short_price_change_pct = (current_short_price - entry_short_price) / entry_short_price if entry_short_price != 0 else 0
            
            f.write(f"\n💰 期权价格变化详情:\n")
            f.write(f"   Long期权: {entry_long_price:.6f} → {current_long_price:.6f} BTC ({long_price_change_pct:+.1%})\n")
            f.write(f"   Short期权: {entry_short_price:.6f} → {current_short_price:.6f} BTC ({short_price_change_pct:+.1%})\n")
            f.write(f"   入场权利金: {calendar_pair.entry_premium:.6f} BTC\n")
            f.write(f"   当前权利金: {current_long_price - current_short_price:.6f} BTC\n")
            
            # 期权合约信息
            f.write(f"\n📋 期权合约:\n")
            f.write(f"   Long: {calendar_pair.option_symbols['long_option']} (${calendar_pair.long_strike:,.0f})\n")
            f.write(f"   Short: {calendar_pair.option_symbols['short_option']} (${calendar_pair.short_strike:,.0f})\n")
            
            # 时间信息
            f.write(f"\n⏰ 时间信息:\n")
            f.write(f"   入场时间: {calendar_pair.entry_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"   平仓时间: {time_obj.strftime('%Y-%m-%d %H:%M:%S')}\n")
            holding_hours = (time_obj - calendar_pair.entry_time).total_seconds() / 3600
            f.write(f"   持仓时长: {holding_hours:.1f}小时\n")
            
            # 异常分析
            f.write(f"\n🔍 异常分析:\n")
            if spot_change_rate <= 0.02:
                f.write(f"   ⚠️  现货小幅变化({spot_change_rate:.2%})但期权价格/IV大幅变动 → 疑似数据异常\n")
            else:
                f.write(f"   🌊 现货大幅变化({spot_change_rate:.2%})期间的异常数据\n")
            
            # 显示各项异常指标
            long_iv_change = abs(calendar_pair.long_option_iv - calendar_pair.entry_greeks['long_option']['iv'])
            short_iv_change = abs(calendar_pair.short_option_iv - calendar_pair.entry_greeks['short_option']['iv'])
            iv_spread_change = abs(current_iv_spread - entry_iv_spread)
            
            f.write(f"   Long IV变化幅度: {long_iv_change:.1%}\n")
            f.write(f"   Short IV变化幅度: {short_iv_change:.1%}\n")
            f.write(f"   IV价差变化幅度: {iv_spread_change:.1%}\n")
            f.write(f"   Long价格变化幅度: {abs(long_price_change_pct):.1%}\n")
            f.write(f"   Short价格变化幅度: {abs(short_price_change_pct):.1%}\n")
            
            f.write(f"\n")
            
    except Exception as e:
        print(f"⚠️  异常交易日志写入失败: {e}")


def print_closing_position_info(calendar_pair, close_info, reason, time_obj, spot, final_pnl, 
                               long_current=None, short_current=None, total_asset=None):
    """
    打印平仓持仓的详细信息
    
    Args:
        calendar_pair: CalendarPair对象
        close_info: 平仓信息字典
        reason: 平仓原因
        time_obj: 平仓时间
        spot: 现货价格
        final_pnl: 最终P&L
        long_current: Long期权当前信息（可选）
        short_current: Short期权当前信息（可选）
        total_asset: 总资产（可选）
    """
    print(f"\n📤 平仓: {reason}")
    print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
    print(f"   策略类型: {close_info['strategy_type']}")
    print(f"   期权P&L: {close_info.get('final_options_pnl', close_info.get('final_pnl', 0)):.6f} BTC")

    # 期权价格信息
    print(f"   Long: {calendar_pair.long_option_price:.6f} BTC ({calendar_pair.option_symbols['long_option']})")
    print(f"   Short: {calendar_pair.short_option_price:.6f} BTC ({calendar_pair.option_symbols['short_option']})")
    
    # 平仓时的IV和Delta信息
    if long_current and short_current:
        # 统一使用 Short - Long (短期 - 长期) 的价差计算
        print(f"   平仓IV: Long {long_current['iv_percent']:.1f}% vs Short {short_current['iv_percent']:.1f}% (价差: {short_current['iv_percent'] - long_current['iv_percent']:+.1f}%)")
        print(f"   平仓Delta: Long {long_current['delta']:.3f} vs Short {short_current['delta']:.3f} (净Delta: {long_current['delta'] - short_current['delta']:+.3f})")
    else:
        print(f"   ⚠️  无法获取平仓时希腊字母信息")
    
    # 各合约P&L
    if 'contract_pnl' in close_info:
        contract_pnl = close_info['contract_pnl']
        print(f"   期权合约P&L: Long:{contract_pnl['long_option']:+.6f} Short:{contract_pnl['short_option']:+.6f}")
    
    # Delta对冲P&L信息
    if calendar_pair.delta_hedge_enabled:
        print(f"   永续浮动P&L: {calendar_pair.inverse_perpetual_pnl:.6f} BTC")
        print(f"   已实现永续合约P&L: {calendar_pair.realized_perpetual_pnl:.6f} BTC")
        print(f"   总P&L: {final_pnl:.6f} BTC")
        print(f"   平均持仓价: ${close_info.get('closing_average_price', 0):,.0f}")
        print(f"   平仓现货价: ${close_info.get('closing_spot_price', 0):,.0f}")
    else:
        print(f"   总P&L: {final_pnl:.6f} BTC")

    if total_asset is not None:
        print(f"   总资产: {total_asset:.6f} BTC")
    print(f"   现货价格: ${spot:,.0f}")