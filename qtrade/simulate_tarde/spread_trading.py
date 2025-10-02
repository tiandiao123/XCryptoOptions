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

from qtrade.simulate_tarde.data_loader import ATMOptionsIterator
from qtrade.simulate_tarde.vol_tracker.vol_tracker import VolTracker
from qtrade.simulate_tarde.data_loader.data_utils import get_option_full_info
from qtrade.simulate_tarde.trading_utils import print_final_backtest_report, print_hedge_stats

from qtrade.simulate_tarde.pairs.calendar_pair import CalendarPair, find_atm_calendar_pair
from qtrade.simulate_tarde.calendar_helper import (
    calculate_atm_iv_1month, 
    log_excluded_trade_details, 
    print_opening_position_info, 
    print_closing_position_info,  # 🆕 新增
    should_exclude_trade_pnl, 
    update_plot,
)

from qtrade.simulate_tarde.pairs.straddle_pair import StraddlePair, find_sell_straddle_opportunity
from qtrade.simulate_tarde.straddle_helper import (
    print_straddle_opening_info, print_straddle_closing_info,
    should_exclude_straddle_trade, log_excluded_straddle_trade
)

from qtrade.simulate_tarde.pairs.search_straggle_options import find_buy_straggle_opportunity, find_sell_straggle_opportunity



def save_experiment_params(save_folder, data_folder, strategy_name, init_btc,
                          exclude_abnormal_trades, use_straggle_search, price_pct_threshold,
                          enable_delta_hedge, delta_threshold, hedge_cost_bps, 
                          inverse_contract_multiplier, max_delta_threshold, max_loss_pct, target_profit_pct, 
                          enable_plot, plot_update_interval):
    """
    保存实验参数到JSON文件
    
    Args:
        save_folder: 保存文件夹路径
        data_folder: 数据文件夹路径
        strategy_name: 策略名称
        init_btc: 初始BTC数量
        exclude_abnormal_trades: 是否排除异常交易
        use_straggle_search: 是否使用straggle搜索
        price_pct_threshold: 价格百分比阈值
        enable_delta_hedge: 是否启用Delta对冲
        delta_threshold: Delta阈值
        hedge_cost_bps: 对冲成本(bps)
        inverse_contract_multiplier: 反向合约乘数
        enable_plot: 是否启用绘图
        plot_update_interval: 绘图更新间隔
    """
    import json
from datetime import datetime
    
    experiment_params = {
        "experiment_info": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_folder": data_folder,
            "save_folder": save_folder
        },
        "strategy_params": {
            "strategy_name": strategy_name,
            "init_btc": init_btc,
            "exclude_abnormal_trades": exclude_abnormal_trades,
            "use_straggle_search": use_straggle_search,
            "price_pct_threshold": price_pct_threshold
        },
        "delta_hedge_params": {
            "enable_delta_hedge": enable_delta_hedge,
            "delta_threshold": delta_threshold,
            "hedge_cost_bps": hedge_cost_bps,
            "inverse_contract_multiplier": inverse_contract_multiplier,
            "max_delta_threshold": max_delta_threshold,
            "max_loss_pct": max_loss_pct,
            "target_profit_pct": target_profit_pct
        },
        "display_params": {
            "enable_plot": enable_plot,
            "plot_update_interval": plot_update_interval
        }
    }
    
    # 保存参数到JSON文件
    params_file = os.path.join(save_folder, "experiment_params.json")
    with open(params_file, 'w', encoding='utf-8') as f:
        json.dump(experiment_params, f, indent=2, ensure_ascii=False)
    
    print(f"📝 实验参数已保存到: {params_file}")


def get_predicted_volatility(vol_tracker, spot_price, time_obj):
    """
    获取预测波动率 - 优先GARCH，备用EWMA
    
    Args:
        vol_tracker: 波动率跟踪器
        spot_price: 现货价格
        time_obj: 时间对象
        
    Returns:
        tuple: (predicted_vol, vol_model, vol_result)
    """
    # 更新波动率跟踪器
    vol_result = vol_tracker.add_price(spot_price, time_obj)
    
    # 选择可用的波动率预测
    garch_vol = vol_result.get('garch_vol_annualized')
    ewma_vol = vol_result.get('ewma_vol_annualized')
    
    if garch_vol is not None:
        predicted_vol = garch_vol
        vol_model = "GARCH"
    elif ewma_vol is not None:
        predicted_vol = ewma_vol
        vol_model = "EWMA"
    else:
        predicted_vol = None
        vol_model = "无"
    
    return predicted_vol, vol_model, vol_result


def process_calendar_trading_position(
    # 位置状态
    has_opened_position,
    calendar_pair,
    # 数据相关
    atm_options,
    time_point_data,
    time_obj,
    spot,
    date,
    predicted_vol,
    vol_model,
    vol_result,
    iv_1month,
    processed_count,
    # 统计相关
    opportunities_found,
    unique_dates_with_opportunities,
    total_asset,
    trade_quality_stats,
    excluded_log_file,
    hedge_stats,  # 🆕 添加对冲统计
    contract_performance_stats,  # 🆕 添加合约胜率统计
    # 配置参数
    enable_delta_hedge=False,
    delta_threshold=0.05,
    inverse_contract_multiplier=1.0,
    hedge_cost_bps=0.0002,
    exclude_abnormal_trades=True,
    max_delta_threshold=0.4,
    max_loss_pct=0.3,
    target_profit_pct=0.5
):
    """
    处理Calendar Spread交易位置的完整逻辑
    
    Returns:
        tuple: (has_opened_position, calendar_pair, opportunities_found, 
                unique_dates_with_opportunities, total_asset, sum_asset_pnl)
    """
    
    sum_asset_pnl = total_asset
    
    # 检查Calendar Spread机会
    if not has_opened_position:
        calendar_spread_options = find_atm_calendar_pair(atm_options, 
                                                        min_days_gap=14,
                                                        atm_tolerance=0.03, 
                                                        min_iv_spread=0.01)
        
        if calendar_spread_options:
            has_opened_position = True
            opportunities_found += 1
            unique_dates_with_opportunities.add(date)

            calendar_pair = CalendarPair(
                calendar_spread_options['calendar_spread'], 
                time_obj, 
                spot,
                delta_hedge_enabled=enable_delta_hedge,
                delta_threshold=delta_threshold,
                contract_multiplier=inverse_contract_multiplier
            )

            calendar_pair.temp_hedge_stats = {
                'hedge_sizes': [],
                'total_hedge_operations': 0,
                'hedge_enabled_trades': 0
            }
            
            # 初始化Delta对冲
            if enable_delta_hedge:
                hedge_success, hedge_info = calendar_pair.initialize_hedge(
                    current_time=time_obj,
                    current_spot_price=spot,
                    hedge_cost_bps=hedge_cost_bps,
                    print_info=True
                )
                
                # 🆕 收集对冲统计数据
                if hedge_success and hedge_info:

                    hedge_size = abs(hedge_info.get('hedge_delta', 0))
    
                    # 数据验证
                    if abs(calendar_pair.get_net_delta()) > 10:
                        print(f"⚠️ 检测到异常 Delta 值: {calendar_pair.get_net_delta()}")
                    else:
                        if hedge_size > 0:
                            calendar_pair.temp_hedge_stats['hedge_sizes'].append(hedge_size)
                            calendar_pair.temp_hedge_stats['total_hedge_operations'] += 1
                        calendar_pair.temp_hedge_stats['hedge_enabled_trades'] += 1
            
            # 打印开仓信息
            print_opening_position_info(
                calendar_pair, 
                calendar_spread_options, 
                spot, 
                time_obj, 
                predicted_vol, 
                vol_model, 
                vol_result, 
                iv_1month
            )
    else:
        # 更新持仓P&L
        update_success, failure_reason = calendar_pair.update_pnl(
            time_obj, 
            time_point_data['data'], 
            spot,
            atm_options,
            print_info=False
        )


        # 🆕 在update_pnl后收集对冲统计
        if enable_delta_hedge and calendar_pair.delta_hedge_enabled and update_success:
            current_hedge_size = abs(calendar_pair.current_hedge_delta)

            if current_hedge_size > 0:
                calendar_pair.temp_hedge_stats['hedge_sizes'].append(current_hedge_size)
                calendar_pair.temp_hedge_stats['total_hedge_operations'] += 1
        
        # 每100个时间点显示一次希腊字母变化
        if processed_count % 100 == 0 and update_success:
            greeks_summary = calendar_pair.get_current_greeks_summary()
            greeks_change = calendar_pair.get_greeks_change_since_entry()
            
            print(f"📊 希腊字母监控 - {time_obj.strftime('%m-%d %H:%M')}")
            print(f"   净Delta: {greeks_summary['net_delta']:+.3f} (变化: {greeks_change['delta_change']['net']:+.3f})")
            print(f"   IV价差: {greeks_summary['iv_spread']:+.1%} (变化: {greeks_change['iv_change']['spread']:+.1%})")
            print(f"   当前P&L: {calendar_pair.current_pnl:+.6f} BTC")
            # 添加对冲监控信息
            if calendar_pair.delta_hedge_enabled and calendar_pair.current_hedge_delta != 0:
                print(f"   对冲头寸: {calendar_pair.current_hedge_delta:+.3f} BTC")
                print(f"   平均持仓价: ${calendar_pair.average_hedge_spot_price:,.0f}")
                print(f"   当前现货价: ${spot:,.0f}")
        
        if update_success:
            should_close, reason = calendar_pair.should_close(time_obj, spot, max_loss_pct=max_loss_pct, target_profit_pct=target_profit_pct, iv_reversal_close=True, max_delta_threshold=max_delta_threshold, inti_BTC=1.0)
        else:
            should_close = True
            
            if "expired" in failure_reason:
                reason = f"期权到期平仓 ({failure_reason})"
            elif "missing_prices" in failure_reason:
                reason = f"无法获取期权价格，强制平仓 ({failure_reason})"
            else:
                reason = f"P&L更新失败，强制平仓 ({failure_reason})"
            
            print(f"⚠️  强制平仓原因: {reason}")
            print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
            print(f"   使用上次P&L: {calendar_pair.current_pnl:.6f} BTC")

        if should_close:
            trade_quality_stats['total_trades'] += 1
            
            # 获取平仓时刻的期权完整信息
            long_current = get_option_full_info(
                time_point_data['data'], 
                calendar_pair.option_symbols['long_option'], 
                time_obj, 
                print_info=False
            )
            short_current = get_option_full_info(
                time_point_data['data'], 
                calendar_pair.option_symbols['short_option'], 
                time_obj, 
                print_info=False
            )
            
            # 保存P&L并平仓
            final_pnl = calendar_pair.current_pnl
            close_info = calendar_pair.close(time_obj, reason, current_spot_price=spot)

            # 检查是否应该排除这次交易
            should_exclude, exclude_reason = should_exclude_trade_pnl(
                calendar_pair, close_info, spot, print_info=exclude_abnormal_trades
            )
            
            if exclude_abnormal_trades and should_exclude:
                # 排除异常交易，不计入P&L
                trade_quality_stats['excluded_trades'] += 1
                trade_quality_stats['excluded_reasons'][exclude_reason] = trade_quality_stats['excluded_reasons'].get(exclude_reason, 0) + 1
                trade_quality_stats['excluded_pnl_sum'] += final_pnl
                
                # 更新状态但不更新资产（P&L归零）
                has_opened_position = False
                sum_asset_pnl = total_asset  # 保持资产不变
                
                # 记录详细信息到日志文件
                log_excluded_trade_details(calendar_pair, close_info, exclude_reason, time_obj, spot, final_pnl, total_asset, excluded_log_file)
                
                # 在控制台只显示简要信息
                print(f"\n🚫 异常交易已排除: {exclude_reason}")
                print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')} | P&L: {final_pnl:.6f} BTC | 详情→{excluded_log_file}")
                
            else:
                # 正常交易，计入P&L
                has_opened_position = False
                total_asset += final_pnl
                sum_asset_pnl = total_asset
                

                # 🆕 累加临时统计到全局统计
                if hasattr(calendar_pair, 'temp_hedge_stats'):
                    hedge_stats['hedge_sizes'].extend(calendar_pair.temp_hedge_stats['hedge_sizes'])
                    hedge_stats['total_hedge_operations'] += calendar_pair.temp_hedge_stats['total_hedge_operations']
                    hedge_stats['hedge_enabled_trades'] += calendar_pair.temp_hedge_stats['hedge_enabled_trades']
                    
                    # 更新最大最小值
                    if calendar_pair.temp_hedge_stats['hedge_sizes']:
                        hedge_stats['max_hedge_size'] = max(hedge_stats['max_hedge_size'], max(calendar_pair.temp_hedge_stats['hedge_sizes']))
                        if hedge_stats['min_hedge_size'] == float('inf'):
                            hedge_stats['min_hedge_size'] = min(calendar_pair.temp_hedge_stats['hedge_sizes'])
                        else:
                            hedge_stats['min_hedge_size'] = min(hedge_stats['min_hedge_size'], min(calendar_pair.temp_hedge_stats['hedge_sizes']))

                # 🆕 收集合约胜率统计
                contract_performance_stats['total_contracts'] += 1
                contract_performance_stats['contract_pnls'].append(final_pnl)
                contract_performance_stats['total_pnl_sum'] += final_pnl

                if final_pnl > 0:
                    contract_performance_stats['profitable_contracts'] += 1
                    contract_performance_stats['profitable_pnl_sum'] += final_pnl
                else:
                    contract_performance_stats['losing_pnl_sum'] += final_pnl
                
                
                # 使用函数打印平仓信息
                print_closing_position_info(
                    calendar_pair=calendar_pair,
                    close_info=close_info,
                    reason=reason,
                    time_obj=time_obj,
                    spot=spot,
                    final_pnl=final_pnl,
                    long_current=long_current,
                    short_current=short_current,
                    total_asset=total_asset
                )
                
            calendar_pair = None

        else:
            sum_asset_pnl = total_asset + calendar_pair.current_pnl

    return (has_opened_position, calendar_pair, opportunities_found, 
            unique_dates_with_opportunities, total_asset, sum_asset_pnl)


# 添加到 qtrade/simulate_tarde/spread_trading.py

def process_straddle_trading_position(
    # 位置状态
    has_opened_position,
    straddle_pair,
    # 数据相关
    atm_options,
    time_point_data,
    time_obj,
    spot,
    date,
    predicted_vol,
    vol_model,
    vol_result,
    iv_1month,
    processed_count,
    # 统计相关
    opportunities_found,
    unique_dates_with_opportunities,
    total_asset,
    trade_quality_stats,
    excluded_log_file,
    hedge_stats,  # 🆕 添加对冲统计
    contract_performance_stats,  # 🆕 添加合约胜率统计
    # 配置参数
    enable_delta_hedge=False,
    delta_threshold=0.05,
    inverse_contract_multiplier=1.0,
    hedge_cost_bps=0.0002,
    exclude_abnormal_trades=True,
    max_delta_threshold=0.4,
    max_loss_pct=0.3,
    target_profit_pct=0.5,
    # Straddle特定参数
    iv_threshold_pct=0.05,
    use_straggle_search=False,
    price_pct_threshold=0.01
):
    """
    处理Straddle交易位置的完整逻辑 - 专注于Sell Straddle
    
    Returns:
        tuple: (has_opened_position, straddle_pair, opportunities_found, 
                unique_dates_with_opportunities, total_asset, sum_asset_pnl)
    """
    
    sum_asset_pnl = total_asset
    
    # 检查Sell Straddle机会
    if not has_opened_position:
        if use_straggle_search:
            straddle_opportunity = find_sell_straggle_opportunity(
                atm_options=atm_options,
                threshold=price_pct_threshold,
                min_days_to_expire=7,
                max_days_to_expire=25,
                realized_vol=predicted_vol,
                iv_threshold_pct=iv_threshold_pct,
                side="sell"
            )
            
            side = "sell"
            if straddle_opportunity is None:
                straddle_opportunity = find_buy_straggle_opportunity(
                    atm_options=atm_options,
                    threshold=price_pct_threshold,
                    min_days_to_expire=15,
                    max_days_to_expire=35,
                    iv_threshold_pct=0.01,
                    realized_vol=predicted_vol,
                    side="buy"
                )
                side = "buy"
            
            # for debug 
            if straddle_opportunity is not None and side == "buy":
                print(straddle_opportunity)
                # exit(0)
                
        else:
            # 🔄 使用原有函数，使用参数化的容差
            straddle_opportunity = find_sell_straddle_opportunity(
                atm_options=atm_options,
                realized_vol=predicted_vol,
                iv_threshold_pct=iv_threshold_pct,
                spot_price=spot,
                price_tolerance=price_pct_threshold  # 使用参数化的容差
            )
        

        if straddle_opportunity:
            has_opened_position = True
            opportunities_found += 1
            unique_dates_with_opportunities.add(date)

            # 构建完整的 straddle_config
            straddle_config = {
                'straddle': straddle_opportunity['straddle'],
                'strategy_type': straddle_opportunity['strategy_type']
            }

            
            straddle_pair = StraddlePair(
                straddle_config,  # 传入完整的配置
                time_obj,
                spot,
                delta_hedge_enabled=enable_delta_hedge,
                delta_threshold=delta_threshold,
                contract_multiplier=inverse_contract_multiplier
            )

            straddle_pair.temp_hedge_stats = {
                'hedge_sizes': [],
                'total_hedge_operations': 0,
                'hedge_enabled_trades': 0
            }
            
            # 初始化Delta对冲
            if enable_delta_hedge:
                hedge_success, hedge_info = straddle_pair.initialize_hedge(
                    current_time=time_obj,
                    current_spot_price=spot,
                    hedge_cost_bps=hedge_cost_bps,
                    print_info=True
                )
                
                # 🆕 收集对冲统计数据
                if hedge_success and hedge_info:
                    hedge_size = abs(hedge_info.get('hedge_delta', 0))

                    if hedge_size > 0:
                        straddle_pair.temp_hedge_stats['hedge_sizes'].append(hedge_size)
                        straddle_pair.temp_hedge_stats['total_hedge_operations'] += 1
                    straddle_pair.temp_hedge_stats['hedge_enabled_trades'] += 1
            
            # 打印开仓信息
            print_straddle_opening_info(
                straddle_pair,
                straddle_opportunity,
                spot,
                time_obj,
                predicted_vol,
                vol_model,
                vol_result,
                iv_1month
            )

    else:
        # 更新持仓P&L
        update_success, failure_reason = straddle_pair.update_pnl(
            time_obj,
            time_point_data['data'],
            spot,
            atm_options,
            print_info=False
        )


        if enable_delta_hedge and straddle_pair.delta_hedge_enabled and update_success:
            current_hedge_size = abs(straddle_pair.current_hedge_delta)

            if current_hedge_size > 0:
                straddle_pair.temp_hedge_stats['hedge_sizes'].append(current_hedge_size)
                straddle_pair.temp_hedge_stats['total_hedge_operations'] += 1
        
        # 每100个时间点显示一次希腊字母变化
        if processed_count % 100 == 0 and update_success:
            greeks_summary = straddle_pair.get_current_greeks_summary()
            greeks_change = straddle_pair.get_greeks_change_since_entry()
            
            print(f"📊 Straddle希腊字母监控 - {time_obj.strftime('%m-%d %H:%M')}")
            print(f"   净Delta: {greeks_summary['net_delta']:+.3f} (变化: {greeks_change['delta_change']['net']:+.3f})")
            print(f"   当前P&L: {straddle_pair.current_pnl:+.6f} BTC")
            print(f"   Moneyness: {spot / straddle_pair.strike_price:.3f}")
            # 添加对冲监控信息
            if straddle_pair.delta_hedge_enabled and straddle_pair.current_hedge_delta != 0:
                print(f"   对冲头寸: {straddle_pair.current_hedge_delta:+.3f} BTC")
                print(f"   平均持仓价: ${straddle_pair.average_hedge_spot_price:,.0f}")
                print(f"   当前现货价: ${spot:,.0f}")
        
        if update_success:
            should_close, reason = straddle_pair.should_close(time_obj, 
                                                               spot, 
                                                               max_loss_pct=max_loss_pct, 
                                                               target_profit_pct=target_profit_pct, 
                                                               iv_reversal_close=True, 
                                                               max_delta_threshold=max_delta_threshold, 
                                                               inti_BTC=1.0, 
                                                               predicted_vol=predicted_vol)
        else:
            should_close = True
            
            if "expired" in failure_reason:
                reason = f"期权到期平仓 ({failure_reason})"
            elif "missing_prices" in failure_reason:
                reason = f"无法获取期权价格，强制平仓 ({failure_reason})"
            else:
                reason = f"P&L更新失败，强制平仓 ({failure_reason})"
            
            print(f"⚠️  强制平仓原因: {reason}")
            print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
            print(f"   使用上次P&L: {straddle_pair.current_pnl:.6f} BTC")

        if should_close:
            trade_quality_stats['total_trades'] += 1
            
            # 获取平仓时刻的期权完整信息
            call_current = get_option_full_info(
                time_point_data['data'],
                straddle_pair.option_symbols['call'],
                time_obj,
                print_info=False
            )
            put_current = get_option_full_info(
                time_point_data['data'],
                straddle_pair.option_symbols['put'],
                time_obj,
                print_info=False
            )
            
            # 保存P&L并平仓
            # final_pnl = straddle_pair.current_pnl
            
            close_info = straddle_pair.close(time_obj, reason, current_spot_price=spot)
            # final_pnl = close_info.get('final_total_pnl', straddle_pair.current_pnl)
            final_pnl = straddle_pair.current_pnl
            # 检查是否应该排除这次交易
            should_exclude, exclude_reason = should_exclude_straddle_trade(
                straddle_pair, close_info, spot, print_info=exclude_abnormal_trades
            )
            
            if exclude_abnormal_trades and should_exclude:
                # 排除异常交易，不计入P&L
                trade_quality_stats['excluded_trades'] += 1
                trade_quality_stats['excluded_reasons'][exclude_reason] = trade_quality_stats['excluded_reasons'].get(exclude_reason, 0) + 1
                trade_quality_stats['excluded_pnl_sum'] += final_pnl
                
                # 更新状态但不更新资产（P&L归零）
                has_opened_position = False
                sum_asset_pnl = total_asset  # 保持资产不变
                
                # 记录详细信息到日志文件
                log_excluded_straddle_trade(straddle_pair, close_info, exclude_reason, time_obj, spot, final_pnl, total_asset, excluded_log_file)
                
                # 在控制台只显示简要信息
                print(f"\n🚫 Straddle异常交易已排除: {exclude_reason}")
                print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')} | P&L: {final_pnl:.6f} BTC | 详情→{excluded_log_file}")
                
            else:
                # 正常交易，计入P&L
                has_opened_position = False
                total_asset += final_pnl
                sum_asset_pnl = total_asset

                if hasattr(straddle_pair, 'temp_hedge_stats'):
                    hedge_stats['hedge_sizes'].extend(straddle_pair.temp_hedge_stats['hedge_sizes'])
                    hedge_stats['total_hedge_operations'] += straddle_pair.temp_hedge_stats['total_hedge_operations']
                    hedge_stats['hedge_enabled_trades'] += straddle_pair.temp_hedge_stats['hedge_enabled_trades']
                    
                    # 更新最大最小值
                    if straddle_pair.temp_hedge_stats['hedge_sizes']:
                        hedge_stats['max_hedge_size'] = max(hedge_stats['max_hedge_size'], max(straddle_pair.temp_hedge_stats['hedge_sizes']))
                        if hedge_stats['min_hedge_size'] == float('inf'):
                            hedge_stats['min_hedge_size'] = min(straddle_pair.temp_hedge_stats['hedge_sizes'])
                        else:
                            hedge_stats['min_hedge_size'] = min(hedge_stats['min_hedge_size'], min(straddle_pair.temp_hedge_stats['hedge_sizes']))
                
                # 🆕 收集合约胜率统计
                contract_performance_stats['total_contracts'] += 1
                contract_performance_stats['contract_pnls'].append(final_pnl)
                contract_performance_stats['total_pnl_sum'] += final_pnl
                
                if final_pnl > 0:
                    contract_performance_stats['profitable_contracts'] += 1
                    contract_performance_stats['profitable_pnl_sum'] += final_pnl
                else:
                    contract_performance_stats['losing_pnl_sum'] += final_pnl
                
                # 使用函数打印平仓信息
                print_straddle_closing_info(
                    straddle_pair=straddle_pair,
                    close_info=close_info,
                    reason=reason,
                    time_obj=time_obj,
                    spot=spot,
                    final_pnl=final_pnl,
                    call_current=call_current,
                    put_current=put_current,
                    total_asset=total_asset
                )

                # if opportunities_found == 2:
                #     exit(0)
                
            straddle_pair = None

        else:
            sum_asset_pnl = total_asset + straddle_pair.current_pnl

    return (has_opened_position, straddle_pair, opportunities_found, 
            unique_dates_with_opportunities, total_asset, sum_asset_pnl)


def backtest_strategy(data_folder: str, 
                            init_btc: float = 1.0, 
                            enable_plot: bool = True, 
                            plot_update_interval: int = 500, 
                    save_folder: str = 'calendar_spread_backtest_result',
                    exclude_abnormal_trades: bool = True,
                    # Delta对冲参数
                    enable_delta_hedge: bool = False,
                    delta_threshold: float = 0.05,
                    hedge_cost_bps: float = 0.0002,
                    inverse_contract_multiplier: float = 1.0, 
                    # 风险控制参数
                    max_delta_threshold: float = 0.4,
                    max_loss_pct: float = 0.3,
                    target_profit_pct: float = 0.5,
                    strategy_name: str = "calendar_spread",
                    use_straggle_search: bool = False,
                    price_pct_threshold: float = 0.01):
    """
    Calendar Spread回测 - 增加异常交易排除功能
    """
    os.makedirs(save_folder, exist_ok=True)
    
    # 🆕 保存实验参数
    save_experiment_params(
        save_folder=save_folder,
        data_folder=data_folder,
        strategy_name=strategy_name,
        init_btc=init_btc,
        exclude_abnormal_trades=exclude_abnormal_trades,
        use_straggle_search=use_straggle_search,
        price_pct_threshold=price_pct_threshold,
        enable_delta_hedge=enable_delta_hedge,
        delta_threshold=delta_threshold,
        hedge_cost_bps=hedge_cost_bps,
        inverse_contract_multiplier=inverse_contract_multiplier,
        max_delta_threshold=max_delta_threshold,
        max_loss_pct=max_loss_pct,
        target_profit_pct=target_profit_pct,
        enable_plot=enable_plot,
        plot_update_interval=plot_update_interval
    )

    iterator = ATMOptionsIterator(
        data_folder,
        silent_mode=True
    )

    start_time = time.time()
    processed_count = 0
    
    # 简化统计
    opportunities_found = 0
    unique_dates_with_opportunities = set()
    unique_dates = set()

    print("🚀 开始Calendar Spread回测...")

    total_asset = init_btc
    has_opened_position = False
    calendar_pair = None
    straddle_pair = None

    sum_asset_pnl = total_asset
    sum_asset_pnl_list = []
    time_list = []
    
    # 🆕 设置实时图表
    if enable_plot:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_title('Calendar Spread Strategy - Asset P&L Over Time', fontsize=14, fontweight='bold')
        ax.set_xlabel('Time')
        ax.set_ylabel('Total Asset (BTC)')
        ax.grid(True, alpha=0.3)
        
        # 初始化空线条
        line, = ax.plot([], [], 'b-', linewidth=2, label='Total Asset')
        ax.axhline(y=init_btc, color='r', linestyle='--', alpha=0.7, label=f'Initial: {init_btc:.4f} BTC')
        ax.legend()
        
        plt.tight_layout()
        plt.show(block=False)

    
    start_date = iterator.dates[-int(365 * 3)]
    end_date = iterator.dates[-1]
    print(f"回测时间范围: {start_date} 到 {end_date}")
    
    # 🆕 初始化波动率跟踪器
    vol_tracker = VolTracker(
        window_size=200,
        ewma_lambda=0.94,
        min_periods=100,
        refit_frequency=48
    )
    
    print("📊 波动率预测模型: GARCH(1,1) + EWMA备用")

    # 🆕 交易质量统计
    trade_quality_stats = {
        'total_trades': 0,
        'excluded_trades': 0,
        'excluded_reasons': {},
        'excluded_pnl_sum': 0.0  # 被排除的P&L总和
    }

    # 🆕 Delta对冲统计
    hedge_stats = {
        'hedge_sizes': [],  # 记录所有对冲大小的绝对值
        'max_hedge_size': 0.0,
        'min_hedge_size': float('inf'),
        'total_hedge_operations': 0,
        'hedge_enabled_trades': 0
    }

    # 🆕 合约胜率统计
    contract_performance_stats = {
        'total_contracts': 0,
        'profitable_contracts': 0,
        'total_pnl_sum': 0.0,
        'profitable_pnl_sum': 0.0,
        'losing_pnl_sum': 0.0,
        'contract_pnls': []  # 记录所有合约P&L
    }

    # 🆕 初始化异常交易日志文件
    excluded_log_file = os.path.join(save_folder, 'excluded_trades_log.txt')
    
    # 清空旧的日志文件并写入头部
    with open(excluded_log_file, 'w', encoding='utf-8') as f:
        f.write(f"Calendar Spread Strategy - 异常交易排除日志\n")
        f.write(f"回测开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"数据文件夹: {data_folder}\n")
        f.write(f"异常交易排除: {'启用' if exclude_abnormal_trades else '禁用'}\n")
        f.write(f"{'='*80}\n")
    
    for time_point_data in iterator.iterate_date_range(start_date, end_date):
        processed_count += 1
        date = time_point_data['date'] 
        time_obj = time_point_data['time']
        spot = time_point_data['spot_price']
        atm_options = time_point_data['atm_options']

        unique_dates.add(date)

        # 获取预测波动率
        predicted_vol, vol_model, vol_result = get_predicted_volatility(vol_tracker, spot, time_obj)
        
        # 计算1个月ATM IV
        iv_1month = calculate_atm_iv_1month(atm_options)
        
        # 处理Calendar Spread交易
        if strategy_name == "calendar_spread":
            (has_opened_position, calendar_pair, opportunities_found, 
            unique_dates_with_opportunities, total_asset, sum_asset_pnl) = process_calendar_trading_position(
                has_opened_position=has_opened_position,
                calendar_pair=calendar_pair,
                atm_options=atm_options,
                time_point_data=time_point_data,
                time_obj=time_obj,
                spot=spot,
                date=date,
                predicted_vol=predicted_vol,
                vol_model=vol_model,
                vol_result=vol_result,
                iv_1month=iv_1month,
                processed_count=processed_count,
                opportunities_found=opportunities_found,
                unique_dates_with_opportunities=unique_dates_with_opportunities,
                total_asset=total_asset,
                trade_quality_stats=trade_quality_stats,
                excluded_log_file=excluded_log_file,
                hedge_stats=hedge_stats,  # 🆕 添加
                contract_performance_stats=contract_performance_stats,  # 🆕 添加
                enable_delta_hedge=enable_delta_hedge,
                delta_threshold=delta_threshold,
                inverse_contract_multiplier=inverse_contract_multiplier,
                hedge_cost_bps=hedge_cost_bps,
                exclude_abnormal_trades=exclude_abnormal_trades,
                max_delta_threshold=max_delta_threshold,
                max_loss_pct=max_loss_pct,
                target_profit_pct=target_profit_pct
            )
        elif strategy_name == "gamma_scalping_sell_straddle":
            (has_opened_position, straddle_pair, opportunities_found, 
             unique_dates_with_opportunities, total_asset, sum_asset_pnl) = process_straddle_trading_position(
                has_opened_position=has_opened_position,
                straddle_pair=straddle_pair if 'straddle_pair' in locals() else None,
                atm_options=atm_options,
                time_point_data=time_point_data,
                time_obj=time_obj,
                spot=spot,
                date=date,
                predicted_vol=predicted_vol,
                vol_model=vol_model,
                vol_result=vol_result,
                iv_1month=iv_1month,
                processed_count=processed_count,
                opportunities_found=opportunities_found,
                unique_dates_with_opportunities=unique_dates_with_opportunities,
                total_asset=total_asset,
                trade_quality_stats=trade_quality_stats,
                excluded_log_file=excluded_log_file,
                hedge_stats=hedge_stats,  # 🆕 添加
                contract_performance_stats=contract_performance_stats,  # 🆕 添加
                enable_delta_hedge=enable_delta_hedge,
                delta_threshold=delta_threshold,
                inverse_contract_multiplier=inverse_contract_multiplier,
                hedge_cost_bps=hedge_cost_bps,
                exclude_abnormal_trades=exclude_abnormal_trades,
                max_delta_threshold=max_delta_threshold,
                max_loss_pct=max_loss_pct,
                target_profit_pct=target_profit_pct,
                iv_threshold_pct=0.05,
                use_straggle_search=use_straggle_search,
                price_pct_threshold=price_pct_threshold
            )
        elif strategy_name == "gamma_scalping_sell_calendar_spread":
            if straddle_pair is None:
                (has_opened_position, calendar_pair, opportunities_found, 
                unique_dates_with_opportunities, total_asset, sum_asset_pnl) = process_calendar_trading_position(
                    has_opened_position=has_opened_position,
                    calendar_pair=calendar_pair,
                    atm_options=atm_options,
                    time_point_data=time_point_data,
                    time_obj=time_obj,
                    spot=spot,
                    date=date,
                    predicted_vol=predicted_vol,
                    vol_model=vol_model,
                    vol_result=vol_result,
                    iv_1month=iv_1month,
                    processed_count=processed_count,
                    opportunities_found=opportunities_found,
                    unique_dates_with_opportunities=unique_dates_with_opportunities,
                    total_asset=total_asset,
                    trade_quality_stats=trade_quality_stats,
                    excluded_log_file=excluded_log_file,
                    hedge_stats=hedge_stats,  # 🆕 添加
                    contract_performance_stats=contract_performance_stats,  # 🆕 添加
                    enable_delta_hedge=enable_delta_hedge,
                    delta_threshold=delta_threshold,
                    inverse_contract_multiplier=inverse_contract_multiplier,
                    hedge_cost_bps=hedge_cost_bps,
                    exclude_abnormal_trades=exclude_abnormal_trades,
                    max_delta_threshold=max_delta_threshold,
                    max_loss_pct=max_loss_pct,
                    target_profit_pct=target_profit_pct
                )
            
            if calendar_pair is None:
                (has_opened_position, straddle_pair, opportunities_found, 
                    unique_dates_with_opportunities, total_asset, sum_asset_pnl) = process_straddle_trading_position(
                        has_opened_position=has_opened_position,
                        straddle_pair=straddle_pair if 'straddle_pair' in locals() else None,
                        atm_options=atm_options,
                        time_point_data=time_point_data,
                        time_obj=time_obj,
                        spot=spot,
                        date=date,
                        predicted_vol=predicted_vol,
                        vol_model=vol_model,
                        vol_result=vol_result,
                        iv_1month=iv_1month,
                        processed_count=processed_count,
                        opportunities_found=opportunities_found,
                        unique_dates_with_opportunities=unique_dates_with_opportunities,
                        total_asset=total_asset,
                        trade_quality_stats=trade_quality_stats,
                        excluded_log_file=excluded_log_file,
                        hedge_stats=hedge_stats,  # 🆕 添加
                        contract_performance_stats=contract_performance_stats,  # 🆕 添加
                        enable_delta_hedge=enable_delta_hedge,
                        delta_threshold=delta_threshold,
                        inverse_contract_multiplier=inverse_contract_multiplier,
                        hedge_cost_bps=hedge_cost_bps,
                        exclude_abnormal_trades=exclude_abnormal_trades,
                        max_delta_threshold=max_delta_threshold,
                        max_loss_pct=max_loss_pct,
                        target_profit_pct=target_profit_pct,
                        iv_threshold_pct=0.05,
                        use_straggle_search=use_straggle_search,
                        price_pct_threshold=price_pct_threshold
                    )

        else:
            raise ValueError(f"策略名称 {strategy_name} 不在策略集合中")

            # handle sell straddle options 
            

        # 记录时间和资产数据
        sum_asset_pnl_list.append(sum_asset_pnl)
        time_list.append(time_obj)

        # 实时更新图表
        if enable_plot and processed_count % plot_update_interval == 0:
            update_plot(ax, line, time_list, sum_asset_pnl_list, init_btc)
            
            # 动态保存图表
            # 使用固定文件名，覆盖之前的中间进度图
            progress_filename = 'backtest_progress_temp.png'
            plt.savefig(os.path.join(save_folder, progress_filename), dpi=300, bbox_inches='tight')
            print(f"📊 进度图表已更新: {progress_filename} (处理进度: {processed_count})")
        
        # 每1000个时间点显示进度
        if processed_count % 1000 == 0:
            elapsed = time.time() - start_time
            current_return = (sum_asset_pnl - init_btc) / init_btc * 100
            print(f"\n📊 进度报告:")
            print(f"   当前时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
            print(f"   已处理: {processed_count:,} 个时间点")
            print(f"   当前资产: {sum_asset_pnl:.6f} BTC")
            print(f"   当前收益: {current_return:+.2f}%")
            print(f"   套利机会: {opportunities_found:,} ({opportunities_found/processed_count*100:.3f}%)")

    # 最终更新图表
    if enable_plot:
        update_plot(ax, line, time_list, sum_asset_pnl_list, init_btc)
        plt.savefig(os.path.join(save_folder, 'calendar_spread_backtest_result.png'), dpi=300, bbox_inches='tight')
        print(f"📊 图表已保存: {os.path.join(save_folder, 'calendar_spread_backtest_result.png')}")

    # 最终统计
    total_elapsed = time.time() - start_time

    print("===========================PRINT HEGDE STATS===========================")
    print_hedge_stats(hedge_stats, contract_performance_stats, save_folder=save_folder)
    
    # 打印最终报告
    print("===========================PRINT FINAL BACKTEST REPORT===========================")
    metrics = print_final_backtest_report(
        processed_count=processed_count,
        opportunities_found=opportunities_found,
        unique_dates_with_opportunities=unique_dates_with_opportunities,
        unique_dates=unique_dates,
        total_elapsed=total_elapsed,
        init_btc=init_btc,
        sum_asset_pnl=sum_asset_pnl,
        trade_quality_stats=trade_quality_stats,
        exclude_abnormal_trades=exclude_abnormal_trades,
        time_list=time_list,
        sum_asset_pnl_list=sum_asset_pnl_list,
        save_folder=save_folder,
        enable_plot=enable_plot,
        strategy_name="Calendar Spread Strategy"
    )

    return time_list, sum_asset_pnl_list

if __name__ == "__main__":
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    
    strategy_set = set([
        "calendar_spread",
        "gamma_scalping_sell_straddle",
        "gamma_scalping_sell_calendar_spread",
    ])

    strategy_name = "calendar_spread"

    assert strategy_name in strategy_set, f"策略名称 {strategy_name} 不在策略集合中"
    
    # 🚀 运行Calendar Spread回测
    backtest_strategy(
        data_folder=data_folder, 
        init_btc=1.0,
        enable_plot=True,
        plot_update_interval=500,
        exclude_abnormal_trades=True,
        save_folder='calendar_spread_results',

        # 🆕 Delta对冲参数
        enable_delta_hedge=True,  # 启用Delta对冲
        delta_threshold=0.05,     # 5% Delta阈值, once exceed, hedge 
        hedge_cost_bps=0.0000,   # 2bps手续费
        inverse_contract_multiplier=1.0, 
        strategy_name=strategy_name,
        use_straggle_search=True, 
        price_pct_threshold=0.01, 

        # risk control parameters
        max_loss_pct=0.3,
        target_profit_pct=0.5,
        max_delta_threshold = 0.4, # close when combined delta exceed this threshold
    )





