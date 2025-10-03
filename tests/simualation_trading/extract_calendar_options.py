#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract calendar spread option contract data
"""

import pandas as pd
import os
from datetime import datetime

def extract_calendar_options():
    """提取四个期权合约的数据"""
    
    # 输入文件
    input_file = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks/okex-options_quotes_2021-01-30_OPTIONS_30min_klines_with_iv_greeks.csv'
    
    # 目标期权符号
    target_symbols = [
        'BTC-USD-210326-34000-C',  # Long Call (远月ATM)
        'BTC-USD-210212-35000-C',  # Short Call (近月OTM)
        'BTC-USD-210326-34000-P',  # Long Put (远月ATM)
        'BTC-USD-210212-34000-P'   # Short Put (近月OTM)
    ]
    
    # 关键时间点
    entry_time = '2021-01-30 00:00:00 UTC'
    exit_time = '2021-01-30 08:00:00 UTC'
    
    print(f"🔍 分析文件: {os.path.basename(input_file)}")
    print(f"📊 目标期权符号: {len(target_symbols)} 个")
    print("="*80)
    
    try:
        # 读取CSV文件
        df = pd.read_csv(input_file)
        print(f"📊 总记录数: {len(df):,}")
        
        # 转换时间格式
        df['datetime'] = pd.to_datetime(df['time'])
        
        # 基本统计
        print(f"⏰ 时间范围: {df['datetime'].min()} 到 {df['datetime'].max()}")
        print(f"🎯 唯一符号数: {df['symbol'].nunique():,}")
        
        # 检查目标符号是否存在
        print(f"\n🎯 检查目标期权符号:")
        missing_symbols = []
        for symbol in target_symbols:
            exists = symbol in df['symbol'].values
            status = "✅ 存在" if exists else "❌ 缺失"
            print(f"   {symbol}: {status}")
            if not exists:
                missing_symbols.append(symbol)
        
        if missing_symbols:
            print(f"\n❌ 缺失的符号: {missing_symbols}")
            print(f"🔍 查找相似符号:")
            for missing in missing_symbols:
                # 提取执行价和期权类型
                parts = missing.split('-')
                if len(parts) >= 4:
                    strike = parts[3]
                    option_type = parts[4] if len(parts) > 4 else ''
                    similar = df[df['symbol'].str.contains(f'-{strike}-', na=False)]['symbol'].unique()
                    print(f"   包含 '{strike}' 的符号: {list(similar)[:5]}")
            return
        
        # 提取每个期权的数据
        output_dir = '/home/ubuntu/options_trading/calendar_options_data'
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n📁 输出目录: {output_dir}")
        print(f"📊 提取数据:")
        
        # 关键时间点数据汇总
        entry_data = []
        exit_data = []
        
        for i, symbol in enumerate(target_symbols, 1):
            # 筛选该符号的数据
            symbol_data = df[df['symbol'] == symbol].copy()
            
            if len(symbol_data) == 0:
                print(f"   ❌ {symbol}: 无数据")
                continue
            
            # 保存到单独文件
            output_file = os.path.join(output_dir, f'{symbol.replace("-", "_")}_2021-01-30.csv')
            symbol_data.to_csv(output_file, index=False)
            
            print(f"   ✅ {symbol}:")
            print(f"      记录数: {len(symbol_data)}")
            print(f"      时间范围: {symbol_data['datetime'].min()} 到 {symbol_data['datetime'].max()}")
            print(f"      价格范围: {symbol_data['open'].min():.6f} - {symbol_data['open'].max():.6f} BTC")
            print(f"      文件: {os.path.basename(output_file)}")
            
            # 检查关键时间点的数据
            entry_record = symbol_data[symbol_data['datetime'] == pd.to_datetime(entry_time)]
            exit_record = symbol_data[symbol_data['datetime'] == pd.to_datetime(exit_time)]
            
            if len(entry_record) > 0:
                entry_info = {
                    'symbol': symbol,
                    'time': entry_time,
                    'open': entry_record['open'].iloc[0],
                    'spot_price': entry_record['spot_open'].iloc[0],
                    'strike': entry_record['strike_price'].iloc[0],
                    'iv': entry_record['iv'].iloc[0],
                    'delta': entry_record.get('pa_delta', entry_record.get('bs_delta', [0])).iloc[0]
                }
                entry_data.append(entry_info)
                print(f"      📥 入场价格 (00:00): {entry_record['open'].iloc[0]:.6f} BTC")
            else:
                print(f"      ❌ 入场时间 (00:00) 无数据")
            
            if len(exit_record) > 0:
                exit_info = {
                    'symbol': symbol,
                    'time': exit_time,
                    'open': exit_record['open'].iloc[0],
                    'spot_price': exit_record['spot_open'].iloc[0],
                    'strike': exit_record['strike_price'].iloc[0],
                    'iv': exit_record['iv'].iloc[0],
                    'delta': exit_record.get('pa_delta', exit_record.get('bs_delta', [0])).iloc[0]
                }
                exit_data.append(exit_info)
                print(f"      📤 平仓价格 (08:00): {exit_record['open'].iloc[0]:.6f} BTC")
            else:
                print(f"      ❌ 平仓时间 (08:00) 无数据")
            
            print()
        
        # 分析交易逻辑
        print(f"📊 交易分析:")
        print("="*80)
        
        if len(entry_data) == 4 and len(exit_data) == 4:
            # 计算入场权利金
            entry_premium = (
                entry_data[0]['open'] +  # Long Call
                entry_data[2]['open'] -  # Long Put
                entry_data[1]['open'] -  # Short Call
                entry_data[3]['open']    # Short Put
            )
            
            # 计算平仓权利金
            exit_premium = (
                exit_data[0]['open'] +   # Long Call
                exit_data[2]['open'] -   # Long Put
                exit_data[1]['open'] -   # Short Call
                exit_data[3]['open']     # Short Put
            )
            
            pnl = exit_premium - entry_premium
            pnl_pct = (pnl / abs(entry_premium)) * 100 if abs(entry_premium) > 1e-8 else 0
            
            print(f"💰 权利金分析:")
            print(f"   入场权利金: {entry_premium:.6f} BTC")
            print(f"   平仓权利金: {exit_premium:.6f} BTC")
            print(f"   P&L: {pnl:.6f} BTC ({pnl_pct:+.1f}%)")
            
            print(f"\n📊 现货价格变化:")
            entry_spot = entry_data[0]['spot_price']
            exit_spot = exit_data[0]['spot_price']
            spot_change = (exit_spot - entry_spot) / entry_spot * 100
            print(f"   入场现货: ${entry_spot:,.2f}")
            print(f"   平仓现货: ${exit_spot:,.2f}")
            print(f"   现货变化: {spot_change:+.2f}%")
            
            print(f"\n🎯 期权价格变化:")
            for i, (entry, exit) in enumerate(zip(entry_data, exit_data)):
                price_change = (exit['open'] - entry['open']) / entry['open'] * 100 if entry['open'] > 1e-8 else 0
                position_type = ['Long Call', 'Short Call', 'Long Put', 'Short Put'][i]
                print(f"   {position_type} ({entry['symbol']}):")
                print(f"      入场: {entry['open']:.6f} → 平仓: {exit['open']:.6f} BTC ({price_change:+.1f}%)")
                print(f"      执行价: ${entry['strike']:,.0f}, IV: {entry['iv']:.3f} → {exit['iv']:.3f}")
            
            # 检查异常
            print(f"\n🔍 异常检查:")
            
            # 检查IV变化
            for i, (entry, exit) in enumerate(zip(entry_data, exit_data)):
                iv_change = exit['iv'] - entry['iv']
                if abs(iv_change) > 1.0:  # IV变化超过100%
                    print(f"   ⚠️  {entry['symbol']} IV异常变化: {entry['iv']:.3f} → {exit['iv']:.3f} (变化: {iv_change:+.3f})")
            
            # 检查价格合理性
            for i, (entry, exit) in enumerate(zip(entry_data, exit_data)):
                if entry['open'] > 1.0 or exit['open'] > 1.0:  # 期权价格超过1 BTC
                    print(f"   ⚠️  {entry['symbol']} 价格异常高: 入场 {entry['open']:.6f}, 平仓 {exit['open']:.6f}")
        
        else:
            print(f"❌ 数据不完整，无法进行完整分析")
            print(f"   入场数据: {len(entry_data)}/4")
            print(f"   平仓数据: {len(exit_data)}/4")
        
        print(f"\n✅ 数据提取完成！文件保存在: {output_dir}")
        
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_calendar_options()
