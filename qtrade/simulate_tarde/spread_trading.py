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
from qtrade.simulate_tarde.calendar_helper import (
    calculate_atm_iv_1month, 
    log_excluded_trade_details, 
    print_opening_position_info, 
    print_closing_position_info,  # 🆕 新增
    should_exclude_trade_pnl, 
    update_plot,
)

from qtrade.simulate_tarde.metric_test import calculate_performance_metrics
from qtrade.simulate_tarde.pairs.calendar_pair import CalendarPair, find_atm_calendar_pair
from qtrade.simulate_tarde.vol_tracker.vol_tracker import VolTracker
from qtrade.data_utils import get_option_full_info

# 设置matplotlib支持中文和交互模式
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
plt.ion()  # 开启交互模式


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
    # 🆕 更新波动率跟踪器
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


def trade_calendar_spread():
    pass 


def backtest_calendar_spread(data_folder: str, 
                            init_btc: float = 1.0, 
                            enable_plot: bool = True, 
                            plot_update_interval: int = 500, 
                            save_folder: str = 'calendar_spread_backtest_result',
                            exclude_abnormal_trades: bool = True,
                            # Delta对冲参数
                            enable_delta_hedge: bool = False,
                            delta_threshold: float = 0.05,
                            hedge_cost_bps: float = 0.0002,
                            inverse_contract_multiplier: float = 1.0):
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
    

    start_date = iterator.dates[-int(365 * 2.5)]
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
        
        # 🆕 获取预测波动率
        predicted_vol, vol_model, vol_result = get_predicted_volatility(vol_tracker, spot, time_obj)
        
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
                    spot,
                    delta_hedge_enabled=enable_delta_hedge,
                    delta_threshold=delta_threshold,
                    contract_multiplier=inverse_contract_multiplier  # 🆕 添加合约乘数
                )
                
                # 🆕 初始化Delta对冲
                if enable_delta_hedge:
                    hedge_success, hedge_info = calendar_pair.initialize_hedge(
                        current_time=time_obj,
                        current_spot_price=spot,
                        hedge_cost_bps=hedge_cost_bps,
                        print_info=True
                    )
                
                # 🔧 替换原来的所有打印代码为一个函数调用
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
                # 🆕 添加对冲监控信息
                if calendar_pair.delta_hedge_enabled and calendar_pair.current_hedge_delta != 0:
                    print(f"   对冲头寸: {calendar_pair.current_hedge_delta:+.3f} BTC")
                    print(f"   平均持仓价: ${calendar_pair.average_hedge_spot_price:,.0f}")
                    print(f"   当前现货价: ${spot:,.0f}")
            
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
                close_info = calendar_pair.close(time_obj, reason, current_spot_price=spot)  # 🔧 添加现货价格
                


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
                    # 正常交易，计入P&L
                    has_opened_position = False
                    total_asset += final_pnl
                    sum_asset_pnl = total_asset
                    
                    # 🆕 使用函数打印平仓信息
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
    metrics = calculate_performance_metrics(time_list, sum_asset_pnl_list, init_btc, save_folder=save_folder)
    if metrics:
        print(f"   年化收益率: {metrics['annualized_return']*100:+.2f}%")
        print(f"   年化波动率: {metrics['annualized_volatility']*100:.2f}%") 
        print(f"   Sharpe比率: {metrics['sharpe_ratio']:.3f}")
        print(f"   Sortino比率: {metrics['sortino_ratio']:.3f}")
        print(f"   最大回撤: {metrics['max_drawdown']*100:.2f}%")
        print(f"   Calmar比率: {metrics['calmar_ratio']:.3f}")
        print(f"   日胜率: {metrics['win_rate']*100:.1f}%")

if __name__ == "__main__":
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    
    # 🚀 运行Calendar Spread回测
    backtest_calendar_spread(
        data_folder=data_folder, 
        init_btc=1.0,
        enable_plot=True,
        plot_update_interval=500,
        exclude_abnormal_trades=True,
        save_folder='delta_hedge_calendar_spread_backtest_2',
        # 🆕 Delta对冲参数
        enable_delta_hedge=True,  # 启用Delta对冲
        delta_threshold=0.05,     # 5% Delta阈值
        hedge_cost_bps=0.0000,   # 2bps手续费
        inverse_contract_multiplier=1.0
    )





