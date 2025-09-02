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

from qtrade.data_loader import ATMOptionsIterator
from qtrade.simulate_tarde.metric_test import calculate_performance_metrics
from qtrade.simulate_tarde.pairs.calendar_pair import CalendarPair, find_atm_calendar_pair
from qtrade.simulate_tarde.vol_tracker.vol_tracker import VolTracker
from qtrade.data_utils import get_option_full_info

# 设置matplotlib支持中文和交互模式
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
plt.ion()  # 开启交互模式


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
        if abs(close_info['pnl_pct']) > 5.0:  # P&L超过500%可能是数据问题
            if print_info:
                print(f"⚠️  P&L异常: {close_info['pnl_pct']*100:.1f}%")
            return True, f"pnl_excessive: {close_info['pnl_pct']*100:.1f}%"
        
        return False, "valid_trade"
        
    except Exception as e:
        return True, f"exception_in_validation: {str(e)}"


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


def backtest_calendar_spread(data_folder: str, 
                            init_btc: float = 1.0, 
                            enable_plot: bool = True, 
                            plot_update_interval: int = 500, 
                            save_folder: str = 'calendar_spread_backtest_result',
                            enable_data_filter: bool = True,
                            exclude_abnormal_trades: bool = True):  # 🆕 添加异常交易排除开关
    """
    Calendar Spread回测 - 增加异常交易排除功能
    """
    os.makedirs(save_folder, exist_ok=True)

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
    
    print(f"📊 总文件数: {len(iterator.dates)}")
    print(f"📅 日期范围: {iterator.dates[0]} 到 {iterator.dates[-1]}")

    start_date = iterator.dates[-int(365 * 2)]
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
        
        # 🆕 更新波动率跟踪器
        vol_result = vol_tracker.add_price(spot, time_obj)
        
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
        
        # 🆕 计算1个月ATM IV
        iv_1month = calculate_atm_iv_1month(atm_options)

        # 检查Calendar Spread机会
        if has_opened_position is False:
            calendar_spread_options = find_atm_calendar_pair(atm_options)
        
            if calendar_spread_options:
                has_opened_position = True
                opportunities_found += 1
                unique_dates_with_opportunities.add(date)

                calendar_pair = CalendarPair(
                    calendar_spread_options['calendar_spread'], 
                    time_obj, 
                    spot
                )
                
                print(f"===============================  📥 开仓新持仓 =================================")
                print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
                print(f"   策略: {calendar_spread_options['strategy_type']} ({calendar_spread_options.get('strategy_name', 'Unknown')})")
                print(f"   期权类型: {calendar_spread_options['option_type']} Calendar")
                print(f"   现货价格: ${spot:,.2f}")
                print(f"   入场权利金: {calendar_pair.entry_premium:.6f} BTC")
                
                # 🆕 波动率对比
                print(f"\n📊 波动率分析:")
                if predicted_vol:
                    print(f"   {vol_model}预测波动率: {predicted_vol:.1%}")
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
                # 🆕 添加IV信息
                print(f"   开仓IV: Long {long_opt['iv']:.1%} vs Short {short_opt['iv']:.1%} (价差: {short_opt['iv'] - long_opt['iv']:+.1%})")
                # 🆕 添加Delta信息
                print(f"   开仓Delta: Long {long_opt['delta']:.3f} vs Short {short_opt['delta']:.3f} (净Delta: {long_opt['delta'] - short_opt['delta']:+.3f})")


        else:
            # 🆕 更新持仓P&L（现在包含希腊字母更新）
            update_success, failure_reason = calendar_pair.update_pnl(
                time_obj, 
                time_point_data['data'], 
                spot,
                atm_options,  # 🆕 传入ATM期权列表
                print_info=False
            )
            
            # 🆕 每100个时间点显示一次希腊字母变化
            if processed_count % 100 == 0 and update_success:
                greeks_summary = calendar_pair.get_current_greeks_summary()
                greeks_change = calendar_pair.get_greeks_change_since_entry()
                
                print(f"📊 希腊字母监控 - {time_obj.strftime('%m-%d %H:%M')}")
                print(f"   净Delta: {greeks_summary['net_delta']:+.3f} (变化: {greeks_change['delta_change']['net']:+.3f})")
                print(f"   IV价差: {greeks_summary['iv_spread']:+.1%} (变化: {greeks_change['iv_change']['spread']:+.1%})")
                print(f"   当前P&L: {calendar_pair.current_pnl:+.6f} BTC")
            
            if update_success:
                should_close, reason = calendar_pair.should_close(time_obj, spot, iv_reversal_close=True)
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
                
                # 🆕 获取平仓时刻的期权完整信息
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
                close_info = calendar_pair.close(time_obj, reason)
                
                # 🆕 检查是否应该排除这次交易
                should_exclude, exclude_reason = should_exclude_trade_pnl(
                    calendar_pair, close_info, spot, print_info=exclude_abnormal_trades
                )
                
                if exclude_abnormal_trades and should_exclude:
                    # 🆕 排除异常交易，不计入P&L
                    trade_quality_stats['excluded_trades'] += 1
                    trade_quality_stats['excluded_reasons'][exclude_reason] = trade_quality_stats['excluded_reasons'].get(exclude_reason, 0) + 1
                    trade_quality_stats['excluded_pnl_sum'] += final_pnl
                    
                    # 更新状态但不更新资产（P&L归零）
                    has_opened_position = False
                    sum_asset_pnl = total_asset  # 保持资产不变
                    
                    # 🆕 记录详细信息到日志文件
                    log_excluded_trade_details(calendar_pair, close_info, exclude_reason, time_obj, spot, final_pnl, total_asset, excluded_log_file)
                    
                    # 🆕 在控制台只显示简要信息
                    print(f"\n🚫 异常交易已排除: {exclude_reason}")
                    print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')} | P&L: {final_pnl:.6f} BTC | 详情→{excluded_log_file}")
                    
                else:
                    # 🆕 正常交易，计入P&L
                    has_opened_position = False
                    total_asset += final_pnl
                    sum_asset_pnl = total_asset
                    
                    print(f"\n📤 平仓: {reason}")
                    print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
                    print(f"   策略类型: {close_info['strategy_type']}")
                    print(f"   P&L: {final_pnl:.6f} BTC")
                    print(f"   收益率: {close_info['pnl_pct']:.2%}")
                    print(f"   总资产: {total_asset:.6f} BTC")
                    print(f"   现货价格: ${spot:,.0f}")
                    
                    # 期权价格信息
                    print(f"   Long: {calendar_pair.long_option_price:.6f} BTC ({calendar_pair.option_symbols['long_option']})")
                    print(f"   Short: {calendar_pair.short_option_price:.6f} BTC ({calendar_pair.option_symbols['short_option']})")
                    
                    # 🆕 平仓时的IV和Delta信息
                    if long_current and short_current:
                        # 🔧 修正：统一使用 Short - Long (短期 - 长期) 的价差计算
                        print(f"   平仓IV: Long {long_current['iv_percent']:.1f}% vs Short {short_current['iv_percent']:.1f}% (价差: {short_current['iv_percent'] - long_current['iv_percent']:+.1f}%)")
                        print(f"   平仓Delta: Long {long_current['delta']:.3f} vs Short {short_current['delta']:.3f} (净Delta: {long_current['delta'] - short_current['delta']:+.3f})")
                    else:
                        print(f"   ⚠️  无法获取平仓时希腊字母信息")

                    # 各合约P&L
                    if 'contract_pnl' in close_info:
                        contract_pnl = close_info['contract_pnl']
                        print(f"   合约P&L: Long:{contract_pnl['long_option']:+.6f} Short:{contract_pnl['short_option']:+.6f}")
                    
                    calendar_pair = None

                # # 调试
                # if opportunities_found == 6:
                #     exit(0)

            else:
                sum_asset_pnl = total_asset + calendar_pair.current_pnl

        # 记录时间和资产数据
        sum_asset_pnl_list.append(sum_asset_pnl)
        time_list.append(time_obj)

        # 实时更新图表
        if enable_plot and processed_count % plot_update_interval == 0:
            update_plot(ax, line, time_list, sum_asset_pnl_list, init_btc)
            
            # 动态保存图表
            current_timestamp = time_obj.strftime('%Y%m%d_%H%M%S')
            dynamic_filename = f'calendar_spread_progress_{processed_count:06d}_{current_timestamp}.png'
            plt.savefig(os.path.join(save_folder, dynamic_filename), dpi=300, bbox_inches='tight')
            print(f"📊 进度图表已保存: {dynamic_filename}")
        
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
    unique_dates_count = len(unique_dates_with_opportunities)
    total_unique_dates = len(unique_dates)
    final_return = (sum_asset_pnl - init_btc) / init_btc * 100
    
    print(f"\n" + "="*60)
    print(f"🎉 Calendar Spread回测完成！")
    print(f"="*60)
    print(f"📊 基础统计:")
    print(f"   总时间点: {processed_count:,}")
    print(f"   套利机会: {opportunities_found:,}")
    print(f"   机会比例: {opportunities_found/processed_count*100:.3f}%")
    print(f"   有机会天数: {unique_dates_count:,}/{total_unique_dates:,}")
    print(f"   天数比例: {unique_dates_count/total_unique_dates*100:.2f}%")
    print(f"   用时: {total_elapsed/60:.1f}分钟")
    
    print(f"\n💰 最终结果:")
    print(f"   初始资产: {init_btc:.6f} BTC")
    print(f"   最终资产: {sum_asset_pnl:.6f} BTC")
    print(f"   总收益: {sum_asset_pnl - init_btc:+.6f} BTC")
    print(f"   总收益率: {final_return:+.2f}%")
    print(f"="*60)
    
    # 🆕 最终显示交易质量报告
    if exclude_abnormal_trades:
        exclude_rate = trade_quality_stats['excluded_trades'] / max(trade_quality_stats['total_trades'], 1) * 100
        
        print(f"\n📊 交易质量报告:")
        print(f"   总交易数: {trade_quality_stats['total_trades']:,}")
        print(f"   排除交易数: {trade_quality_stats['excluded_trades']:,} ({exclude_rate:.1f}%)")
        print(f"   有效交易率: {100-exclude_rate:.1f}%")
        print(f"   被排除P&L总和: {trade_quality_stats['excluded_pnl_sum']:+.6f} BTC")
        
        if trade_quality_stats['excluded_reasons']:
            print(f"   排除原因统计:")
            for reason, count in trade_quality_stats['excluded_reasons'].items():
                print(f"     {reason}: {count:,}次")
    
    # 保持图表显示
    if enable_plot:
        plt.ioff()
        plt.show()
    

    print(f"\n📊 性能指标:")
    metrics = calculate_performance_metrics(time_list, sum_asset_pnl_list, init_btc)
    if metrics:
        print(f"   年化收益率: {metrics['annualized_return']*100:+.2f}%")
        print(f"   年化波动率: {metrics['annualized_volatility']*100:.2f}%") 
        print(f"   Sharpe比率: {metrics['sharpe_ratio']:.3f}")
        print(f"   Sortino比率: {metrics['sortino_ratio']:.3f}")
        print(f"   最大回撤: {metrics['max_drawdown']*100:.2f}%")
        print(f"   Calmar比率: {metrics['calmar_ratio']:.3f}")
        print(f"   日胜率: {metrics['win_rate']*100:.1f}%")
    
    return {
        'time_list': time_list,
        'asset_pnl_list': sum_asset_pnl_list,
        'total_return': final_return,
        'opportunities_found': opportunities_found
    }


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



if __name__ == "__main__":
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    
    # 🚀 运行Calendar Spread回测
    results = backtest_calendar_spread(
        data_folder=data_folder, 
        init_btc=1.0,
        enable_plot=True,
        plot_update_interval=500,
        enable_data_filter=True,
        exclude_abnormal_trades=True  # 🆕 启用异常交易排除
    )





