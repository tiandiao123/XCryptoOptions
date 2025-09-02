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
from qtrade.simulate_tarde.calendar_pair import CalendarPair, find_calendar_spread_options
from qtrade.simulate_tarde.vol_tracker.vol_tracker import VolTracker  # 🆕 导入vol_tracker

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


def backtest_calendar_spread(data_folder: str, 
                            init_btc: float = 1.0, 
                            enable_plot: bool = True, 
                            plot_update_interval: int = 500, 
                            save_folder: str = 'calendar_spread_backtest_result'):
    """
    日历对角价差回测 - 带实时图表
    
    Args:
        data_folder: 数据文件夹路径
        init_btc: 初始BTC资产
        enable_plot: 是否启用实时图表
        plot_update_interval: 图表更新间隔（每N个时间点更新一次）
    """
    os.makedirs(save_folder, exist_ok=True)

    iterator = ATMOptionsIterator(
        data_folder,
        silent_mode=True
    )

    start_time = time.time()
    processed_count = 0
    total_atm_count = 0
    
    # 简化统计
    opportunities_found = 0
    unique_dates_with_opportunities = set()
    unique_dates = set()

    print("🚀 开始日历对角价差回测...")

    total_asset = init_btc
    has_opened_position = False
    calendar_pair = None

    sum_asset_pnl = total_asset
    sum_asset_pnl_list = []
    time_list = []  # 🆕 存储对应的时间点
    
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

    
    start_date = iterator.dates[-int(365)]
    end_date = iterator.dates[-1]
    print(f"back test from {start_date} to {end_date}")
    
    # 🆕 初始化波动率跟踪器 - 使用GARCH模型
    vol_tracker = VolTracker(
        window_size=200,     # 增加到200个点 (约4天数据，GARCH需要更多历史数据)
        ewma_lambda=0.94,    # RiskMetrics标准  
        min_periods=100,     # GARCH模型需要更多最小数据点
        refit_frequency=48   # 每天重拟合GARCH
    )
    
    print("📊 波动率预测模型: GARCH(1,1) + EWMA备用")

    for time_point_data in iterator.iterate_date_range(start_date, end_date):
        processed_count += 1
        date = time_point_data['date'] 
        time_obj = time_point_data['time']
        spot = time_point_data['spot_price']
        atm_options = time_point_data['atm_options']
        total_atm_count += len(atm_options)

        unique_dates.add(date)
        
        # 🆕 更新波动率跟踪器
        vol_result = vol_tracker.add_price(spot, time_obj)
        
        # 🆕 优先使用GARCH预测，备用EWMA
        # 🔧 暂时禁用GARCH，使用EWMA
        # garch_vol = None  # 
        garch_vol = vol_result.get('garch_vol_annualized')
        ewma_vol = vol_result.get('ewma_vol_annualized')
        
        # 选择可用的波动率预测
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

        # 检查日历对角套利机会
        if has_opened_position is False:
            calendar_spread_options = find_calendar_spread_options(atm_options)
        
            if calendar_spread_options:
                has_opened_position = True
                opportunities_found += 1
                unique_dates_with_opportunities.add(date)

                calendar_pair = CalendarPair(calendar_spread_options['call_diagonal'], 
                                           calendar_spread_options['put_diagonal'], 
                                           time_obj, 
                                           spot)
                
                print(f"===============================  📥 开仓新持仓 =================================")
                print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
                print(f"   策略: {calendar_spread_options['strategy_type']}")
                print(f"   现货价格: ${spot:,.2f}")
                print(f"   入场权利金: {calendar_pair.entry_premium:.6f} BTC")
                
                # 🆕 波动率对比 - 优先显示GARCH
                print(f"\n📊 波动率分析:")
                if predicted_vol:
                    print(f"   {vol_model}预测波动率: {predicted_vol:.1%}")
                    # 如果有GARCH，也显示EWMA作为对比
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
                print(f"   策略IV: 短期{analysis['near_term_iv']:.1%} vs 长期{analysis['long_term_iv']:.1%} (价差:{analysis['iv_spread']:+.1%})")
                
                # 合约信息
                print(f"\n📋 合约信息:")
                print(f"   LC: {calendar_pair.long_term_call_price:.6f} ({calendar_pair.option_symbols['long_call']})")
                print(f"   SC: {calendar_pair.short_term_call_price:.6f} ({calendar_pair.option_symbols['short_call']})")
                print(f"   LP: {calendar_pair.long_term_put_price:.6f} ({calendar_pair.option_symbols['long_put']})")
                print(f"   SP: {calendar_pair.short_term_put_price:.6f} ({calendar_pair.option_symbols['short_put']})")


        else:
            # update pnl
            update_success, failure_reason = calendar_pair.update_pnl(time_obj, time_point_data['data'], spot, print_info=False)
            
            if update_success:
                # 正常更新P&L，检查是否需要平仓
                should_close, reason = calendar_pair.should_close(time_obj, spot)
            else:
                # 无法更新P&L，强制平仓
                should_close = True
                
                # 根据失败原因设置平仓原因
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
                # 保存P&L在清空对象之前
                final_pnl = calendar_pair.current_pnl
                close_info = calendar_pair.close(time_obj, reason)
                
                # 更新状态和资产
                has_opened_position = False
                total_asset += final_pnl
                sum_asset_pnl = total_asset
                
                print(f"\n📤 平仓: {reason}")
                print(f"   时间: {time_obj.strftime('%Y-%m-%d %H:%M')}")
                print(f"   P&L: {final_pnl:.6f} BTC")
                print(f"   Percentage of P&L to Entry Premium: {close_info['pnl_pct']:.2%}")
                print(f"   总资产: {total_asset:.6f} BTC")
                print(f"   current spot price: {spot}")
                print(f"   LC: {calendar_pair.long_term_call_price:.6f} ({calendar_pair.option_symbols['long_call']})")
                print(f"   SC: {calendar_pair.short_term_call_price:.6f} ({calendar_pair.option_symbols['short_call']})")
                print(f"   LP: {calendar_pair.long_term_put_price:.6f} ({calendar_pair.option_symbols['long_put']})")
                print(f"   SP: {calendar_pair.short_term_put_price:.6f} ({calendar_pair.option_symbols['short_put']})")


                                # 🆕 各合约P&L
                if 'contract_pnl' in close_info:
                    contract_pnl = close_info['contract_pnl']
                    print(f"   合约P&L: LC:{contract_pnl['long_call']:+.4f} SC:{contract_pnl['short_call']:+.4f} LP:{contract_pnl['long_put']:+.4f} SP:{contract_pnl['short_put']:+.4f}")
                
                calendar_pair = None

                # if opportunities_found == 4:
                #     exit(0)
            else:
                sum_asset_pnl = total_asset + calendar_pair.current_pnl

        # 🆕 记录时间和资产数据
        sum_asset_pnl_list.append(sum_asset_pnl)
        time_list.append(time_obj)

        # 🆕 实时更新图表
        if enable_plot and processed_count % plot_update_interval == 0:
            update_plot(ax, line, time_list, sum_asset_pnl_list, init_btc)
            
            # 🆕 动态保存图表
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

    # 🆕 最终更新图表
    if enable_plot:
        update_plot(ax, line, time_list, sum_asset_pnl_list, init_btc, final_update=True)
        
        # 简单保存图表
        plt.savefig(os.path.join(save_folder, 'calendar_spread_backtest_result.png'), dpi=300, bbox_inches='tight')
        print(f"📊 图表已保存: {os.path.join(save_folder, 'calendar_spread_backtest_result.png')}")

    # 最终统计
    total_elapsed = time.time() - start_time
    unique_dates_count = len(unique_dates_with_opportunities)
    total_unique_dates = len(iterator.dates)
    final_return = (sum_asset_pnl - init_btc) / init_btc * 100
    
    print(f"\n" + "="*60)
    print(f"🎉 回测完成！")
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
    
    # 🆕 保持图表显示
    if enable_plot:
        plt.ioff()  # 关闭交互模式
        plt.show()  # 保持图表显示
    
    return {
        'time_list': time_list,
        'asset_pnl_list': sum_asset_pnl_list,
        'total_return': final_return,
        'opportunities_found': opportunities_found
    }


def update_plot(ax, line, time_list, asset_list, init_btc, final_update=False):
    """
    更新实时图表
    
    Args:
        ax: matplotlib轴对象
        line: 线条对象
        time_list: 时间列表
        asset_list: 资产列表
        init_btc: 初始资产
        final_update: 是否为最终更新
    """
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
    
    # 🎯 智能设置X轴时间标签（避免过密）
    total_points = len(time_list)
    if total_points > 20:
        # 根据数据点数量动态调整显示密度
        if total_points < 100:
            interval = max(1, total_points // 10)
        elif total_points < 1000:
            interval = max(1, total_points // 15)
        else:
            interval = max(1, total_points // 20)
        
        # 选择要显示的时间点
        display_times = time_list[::interval]
        display_labels = [t.strftime('%m-%d %H:%M') for t in display_times]
        
        ax.set_xticks(display_times)
        ax.set_xticklabels(display_labels, rotation=45, ha='right')
    else:
        # 数据点少时显示所有时间
        ax.set_xticks(time_list)
        ax.set_xticklabels([t.strftime('%m-%d %H:%M') for t in time_list], rotation=45, ha='right')
    
    # 添加当前收益信息到标题
    if asset_list:
        current_return = (asset_list[-1] - init_btc) / init_btc * 100
        ax.set_title(f'Calendar Spread Strategy - Current Return: {current_return:+.2f}%', 
                    fontsize=14, fontweight='bold')
    
    # 刷新图表
    ax.figure.canvas.draw()
    ax.figure.canvas.flush_events()
    
    if final_update:
        plt.tight_layout()


if __name__ == "__main__":
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    
    # 🚀 运行回测并显示实时图表
    results = backtest_calendar_spread(
        data_folder=data_folder, 
        init_btc=1.0,
        enable_plot=True,           # 启用实时图表
        plot_update_interval=500    # 每500个时间点更新一次图表
    )





