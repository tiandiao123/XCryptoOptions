#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX期权数据现货价格整合器
功能：
1. 从OKX API获取BTC现货30分钟K线数据（2020-2025）
2. 将现货价格按时间匹配添加到期权K线数据中
3. 批量处理collected_klines_data目录下的所有文件
"""

import argparse
import pandas as pd
import requests
import time
import os
from datetime import datetime, timezone
from pathlib import Path
import json

class OKXSpotDataFetcher:
    def __init__(self):
        self.base_url = "https://www.okx.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def get_candles(self, instId, bar="30m", after=None, before=None, limit=300):
        """
        获取K线数据
        instId: BTC-USDT
        bar: 30m
        after: 请求此时间戳之前（更旧的）的分页内容，传的值为对应接口的ts
        before: 请求此时间戳之后（更新的）的分页内容，传的值为对应接口的ts
        limit: 分页返回的结果集数量，最大为300，不填默认返回100条
        """
        url = f"{self.base_url}/api/v5/market/history-candles"
        
        params = {
            'instId': instId,
            'bar': bar,
            'limit': limit
        }
        
        if after:
            params['after'] = str(after)
        if before:
            params['before'] = str(before)
            
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == '0':
                return data.get('data', [])
            else:
                print(f"API错误: {data}")
                return []
                
        except Exception as e:
            print(f"请求错误: {e}")
            return []
    
    def fetch_spot_history(self, start_date="2020-01-01", end_date="2025-01-01", 
                          instId="BTC-USDT", bar="30m"):
        """获取完整的现货历史数据"""
        print(f"开始获取 {instId} 现货数据...")
        print(f"时间范围: {start_date} 到 {end_date}")
        print(f"K线周期: {bar}")
        
        # 转换时间戳（毫秒）
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        
        all_data = []
        after_ts = None  # 从最新开始往回取
        request_count = 0
        
        while True:
            request_count += 1
            print(f"请求第 {request_count} 页...")
            
            # 获取数据
            candles = self.get_candles(instId, bar, after=after_ts, limit=300)
            
            if not candles:
                print("没有更多数据")
                break
            
            print(f"获取到 {len(candles)} 条K线数据")
            
            # 过滤时间范围
            valid_candles = []
            for candle in candles:
                ts = int(candle[0])  # 时间戳
                if start_ts <= ts <= end_ts:
                    valid_candles.append(candle)
                elif ts < start_ts:
                    # 已经到达开始时间之前，停止
                    print(f"已达到起始时间 {start_date}")
                    break
            
            if valid_candles:
                all_data.extend(valid_candles)
                print(f"有效数据: {len(valid_candles)} 条，累计: {len(all_data)} 条")
            
            # 如果最后一条数据已经早于开始时间，停止
            if candles and int(candles[-1][0]) < start_ts:
                break
            
            # 设置下次请求的after参数
            after_ts = int(candles[-1][0])
            
            # 限流
            time.sleep(0.1)
            
            # 防止无限循环
            if request_count > 10000:
                print("警告：请求次数过多，停止获取")
                break
        
        print(f"总共获取到 {len(all_data)} 条现货数据")
        
        # 转换为DataFrame
        if all_data:
            df = pd.DataFrame(all_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'volCcy', 'volCcyQuote', 'confirm'
            ])
            
            # 转换数据类型
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote']
            df[numeric_cols] = df[numeric_cols].astype(float)
            df['timestamp'] = df['timestamp'].astype('int64')
            
            # 转换时间戳为可读格式
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            df['time'] = df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            
            # 排序（按时间升序）
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
        else:
            return pd.DataFrame()

def merge_spot_with_options(options_file, spot_df, output_file):
    """将现货价格合并到期权数据中"""
    print(f"\n处理期权文件: {options_file}")
    
    try:
        # 读取期权数据
        options_df = pd.read_csv(options_file)
        print(f"期权数据: {len(options_df)} 行")
        
        if options_df.empty:
            print("期权数据为空，跳过")
            return False
        
        # 检查必需的列
        if 'time' not in options_df.columns:
            print("错误：期权数据缺少 'time' 列")
            return False
        
        print("期权数据列:", list(options_df.columns))
        print("现货数据列:", list(spot_df.columns))
        
        # 创建现货数据的时间索引字典，加速查找
        spot_time_dict = dict(zip(spot_df['time'], spot_df.index))
        
        # 匹配现货价格
        spot_opens = []
        spot_highs = []
        spot_lows = []
        spot_closes = []
        spot_volumes = []
        
        matched_count = 0
        
        for idx, row in options_df.iterrows():
            option_time = row['time']
            
            if option_time in spot_time_dict:
                # 直接匹配
                spot_idx = spot_time_dict[option_time]
                spot_row = spot_df.iloc[spot_idx]
                matched_count += 1
            else:
                # 寻找最近的时间
                try:
                    option_dt = pd.to_datetime(option_time)
                    spot_df_temp = spot_df.copy()
                    spot_df_temp['dt_temp'] = pd.to_datetime(spot_df_temp['time'])
                    spot_df_temp['time_diff'] = abs(spot_df_temp['dt_temp'] - option_dt)
                    
                    closest_idx = spot_df_temp['time_diff'].idxmin()
                    spot_row = spot_df.iloc[closest_idx]
                    
                    # 如果时间差超过1小时，设为NaN
                    if spot_df_temp.loc[closest_idx, 'time_diff'].total_seconds() > 3600:
                        spot_row = pd.Series({
                            'open': float('nan'),
                            'high': float('nan'),
                            'low': float('nan'),
                            'close': float('nan'),
                            'volume': float('nan')
                        })
                    else:
                        matched_count += 1
                        
                except Exception as e:
                    print(f"时间匹配错误 {option_time}: {e}")
                    spot_row = pd.Series({
                        'open': float('nan'),
                        'high': float('nan'),
                        'low': float('nan'),
                        'close': float('nan'),
                        'volume': float('nan')
                    })
            
            spot_opens.append(spot_row['open'])
            spot_highs.append(spot_row['high'])
            spot_lows.append(spot_row['low'])
            spot_closes.append(spot_row['close'])
            spot_volumes.append(spot_row['volume'])
        
        # 添加现货价格列
        options_df['spot_open'] = spot_opens
        options_df['spot_high'] = spot_highs
        options_df['spot_low'] = spot_lows
        options_df['spot_close'] = spot_closes
        options_df['spot_volume'] = spot_volumes
        
        print(f"成功匹配: {matched_count}/{len(options_df)} 条记录 ({matched_count/len(options_df)*100:.1f}%)")
        
        # 保存合并后的数据
        options_df.to_csv(output_file, index=False)
        print(f"保存到: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"处理文件出错: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="OKX期权数据现货价格整合器")
    parser.add_argument("--input-dir", default="/home/ubuntu/options_trading/okx_options/collected_klines_data",
                       help="期权数据输入目录")
    parser.add_argument("--output-dir", default="/home/ubuntu/options_trading/okx_options/options_with_spot",
                       help="合并后数据输出目录")
    parser.add_argument("--spot-cache", default="btc_spot_30min_cache.csv",
                       help="现货数据缓存文件")
    parser.add_argument("--start-date", default="2020-01-01",
                       help="开始日期")
    parser.add_argument("--end-date", default="2025-01-01",
                       help="结束日期")
    parser.add_argument("--force-refresh", action="store_true",
                       help="强制重新获取现货数据")
    
    args = parser.parse_args()
    
    print("="*60)
    print("OKX期权数据现货价格整合器")
    print("="*60)
    print(f"期权数据目录: {args.input_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"现货缓存文件: {args.spot_cache}")
    print(f"时间范围: {args.start_date} 到 {args.end_date}")
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 步骤1: 获取现货数据
    spot_df = None
    
    if os.path.exists(args.spot_cache) and not args.force_refresh:
        print(f"\n从缓存加载现货数据: {args.spot_cache}")
        try:
            spot_df = pd.read_csv(args.spot_cache)
            print(f"加载了 {len(spot_df)} 条现货数据")
        except Exception as e:
            print(f"加载缓存失败: {e}")
            spot_df = None
    
    if spot_df is None or args.force_refresh:
        print(f"\n从OKX API获取现货数据...")
        fetcher = OKXSpotDataFetcher()
        spot_df = fetcher.fetch_spot_history(
            start_date=args.start_date,
            end_date=args.end_date
        )
        
        if not spot_df.empty:
            # 保存缓存
            spot_df.to_csv(args.spot_cache, index=False)
            print(f"现货数据已缓存到: {args.spot_cache}")
        else:
            print("错误：无法获取现货数据")
            return
    
    # 步骤2: 处理所有期权文件
    print(f"\n开始处理期权文件...")
    input_dir = Path(args.input_dir)
    
    if not input_dir.exists():
        print(f"错误：输入目录不存在: {args.input_dir}")
        return
    
    csv_files = list(input_dir.glob("*.csv"))
    print(f"找到 {len(csv_files)} 个CSV文件")
    
    if not csv_files:
        print("没有找到CSV文件")
        return
    
    success_count = 0
    failed_count = 0
    
    for csv_file in csv_files:
        output_file = Path(args.output_dir) / f"{csv_file.stem}_with_spot.csv"
        
        success = merge_spot_with_options(csv_file, spot_df, output_file)
        
        if success:
            success_count += 1
        else:
            failed_count += 1
    
    print("\n" + "="*60)
    print("处理完成！")
    print(f"成功: {success_count} 个文件")
    print(f"失败: {failed_count} 个文件")
    print(f"现货数据范围: {spot_df['time'].min()} 到 {spot_df['time'].max()}")
    print(f"现货数据条数: {len(spot_df)}")
    print(f"输出目录: {args.output_dir}")

if __name__ == "__main__":
    main()

