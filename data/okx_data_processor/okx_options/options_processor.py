# options_filter_btc.py
# -*- coding: utf-8 -*-
"""
OKX期权数据过滤器：删除ETH期权，只保留BTC期权
不进行聚合，直接过滤并保存原始数据
"""

import argparse
import pandas as pd

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_csv", required=True, help="输入 CSV 路径")
    ap.add_argument("--out-csv", dest="out_csv", required=True, help="输出 CSV 路径")
    ap.add_argument("--chunksize", type=int, default=100_000, help="每块读取行数")
    ap.add_argument("--aggregate", action="store_true", help="是否进行30分钟聚合")
    ap.add_argument("--ts-unit", choices=["ms","s"], default="ms", help="时间戳单位（默认ms）")
    return ap.parse_args()

def filter_btc_only(df):
    """过滤数据：删除ETH期权，只保留BTC期权"""
    print(f"  原始行数: {len(df):,}")
    
    # 统计各币种行数
    eth_count = df['symbol'].str.startswith('ETH-USD-', na=False).sum()
    btc_count = df['symbol'].str.startswith('BTC-USD-', na=False).sum()
    other_count = len(df) - eth_count - btc_count
    
    print(f"  ETH期权: {eth_count:,} 行 (将被删除)")
    print(f"  BTC期权: {btc_count:,} 行 (保留)")
    print(f"  其他: {other_count:,} 行")
    
    # 只保留BTC期权
    filtered_df = df[df['symbol'].str.startswith('BTC-USD-', na=False)].copy()
    
    print(f"  过滤后: {len(filtered_df):,} 行")
    return filtered_df

def preprocess_for_aggregation(df, ts_unit="ms"):
    """为聚合准备数据：计算mid_price和时间桶"""
    print(f"  预处理调试：原始数据 {len(df)} 行")
    
    # 检查价格数据
    ask_na = df['ask_price'].isna().sum()
    bid_na = df['bid_price'].isna().sum()
    print(f"  价格数据检查：ask_price缺失{ask_na}行, bid_price缺失{bid_na}行")
    
    # 计算中间价格
    df['mid_price'] = (df['ask_price'] + df['bid_price']) / 2.0
    mid_na = df['mid_price'].isna().sum()
    mid_valid = (~df['mid_price'].isna()).sum()
    print(f"  mid_price: 有效{mid_valid}行, 缺失{mid_na}行")
    
    # 处理时间戳 - 优先使用local_timestamp（更分散）
    if 'local_timestamp' in df.columns:
        ts_col = 'local_timestamp'
        print(f"  使用时间戳列: {ts_col} (本地时间戳)")
    elif 'timestamp' in df.columns:
        ts_col = 'timestamp'
        print(f"  使用时间戳列: {ts_col} (服务器时间戳)")
    else:
        raise ValueError("找不到时间戳列 (timestamp 或 local_timestamp)")
    
    # 检查时间戳分散度
    unique_timestamps = df[ts_col].nunique()
    print(f"  时间戳唯一值: {unique_timestamps} 个（总{len(df)}行）")
    
    if unique_timestamps == 1:
        print(f"  警告：所有数据都有相同的时间戳！")
        # 如果所有时间戳相同，尝试使用另一个时间戳列
        if ts_col == 'local_timestamp' and 'timestamp' in df.columns:
            print(f"  尝试使用timestamp列...")
            alt_unique = df['timestamp'].nunique()
            if alt_unique > unique_timestamps:
                ts_col = 'timestamp'
                print(f"  切换到timestamp列，唯一值: {alt_unique}")
        elif ts_col == 'timestamp' and 'local_timestamp' in df.columns:
            print(f"  尝试使用local_timestamp列...")
            alt_unique = df['local_timestamp'].nunique()
            if alt_unique > unique_timestamps:
                ts_col = 'local_timestamp'
                print(f"  切换到local_timestamp列，唯一值: {alt_unique}")
    
    # 转换为datetime - OKX时间戳是微秒级，需要转换为毫秒
    if ts_unit == 'ms':
        # OKX的时间戳实际是微秒，需要除以1000转为毫秒
        df['dt'] = pd.to_datetime(df[ts_col].astype('int64') // 1000, unit='ms', errors='coerce')
        print(f"  时间戳转换: 微秒->毫秒 (除以1000)")
    else:
        df['dt'] = pd.to_datetime(df[ts_col].astype('int64'), unit=ts_unit, errors='coerce')
        
    dt_na = df['dt'].isna().sum()
    dt_valid = (~df['dt'].isna()).sum()
    print(f"  时间转换: 有效{dt_valid}行, 失败{dt_na}行")
    
    if dt_valid > 0:
        time_range_seconds = (df['dt'].max() - df['dt'].min()).total_seconds()
        print(f"  时间范围: {df['dt'].min()} 到 {df['dt'].max()}")
        print(f"  时间跨度: {time_range_seconds:.1f} 秒")
    else:
        print(f"  错误：没有有效的时间数据！")
    
    # 创建30分钟时间桶
    df['time_bucket'] = df['dt'].dt.floor('30min')
    bucket_na = df['time_bucket'].isna().sum()
    bucket_valid = (~df['time_bucket'].isna()).sum()
    print(f"  时间桶: 有效{bucket_valid}行, 失败{bucket_na}行")
    
    # 检查有效数据行数
    valid_rows = (~df['mid_price'].isna() & ~df['dt'].isna() & ~df['time_bucket'].isna()).sum()
    print(f"  完全有效数据: {valid_rows}行")
    
    return df

def aggregate_30min(df):
    """30分钟聚合：计算OHLC（保留原始时间戳确保正确性）"""
    if df.empty:
        return pd.DataFrame()
    
    print(f"  聚合前行数: {len(df):,}")
    
    # 检查关键列是否存在
    required_cols = ['symbol', 'time_bucket', 'mid_price', 'dt']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        print(f"  错误：缺少必需列 {missing}")
        return pd.DataFrame(columns=['symbol', 'time', 'open', 'high', 'low', 'close'])
    
    # 过滤掉无效数据
    valid_mask = (~df['mid_price'].isna() & ~df['dt'].isna() & ~df['time_bucket'].isna())
    df_clean = df[valid_mask].copy()
    print(f"  清理后数据: {len(df_clean)} 行（移除了 {len(df) - len(df_clean)} 行无效数据）")
    
    if df_clean.empty:
        print(f"  错误：清理后没有有效数据")
        return pd.DataFrame(columns=['symbol', 'time', 'open', 'high', 'low', 'close'])
    
    # 检查时间桶分布
    unique_symbols = df_clean['symbol'].nunique()
    unique_buckets = df_clean['time_bucket'].nunique()
    print(f"  唯一期权合约: {unique_symbols} 个")
    print(f"  唯一时间桶: {unique_buckets} 个")
    print(f"  第一个时间桶: {df_clean['time_bucket'].min()}")
    print(f"  最后时间桶: {df_clean['time_bucket'].max()}")
    
    # 按symbol和时间桶分组
    grouped = df_clean.groupby(['symbol', 'time_bucket'])
    group_count = grouped.ngroups
    print(f"  分组数量: {group_count}")
    
    if group_count == 0:
        print(f"  错误：没有有效分组")
        return pd.DataFrame(columns=['symbol', 'time', 'open', 'high', 'low', 'close'])
    
    def get_ohlc(group):
        """基于原始时间戳计算正确的OHLC"""
        # 按原始时间戳排序，确保时间顺序正确
        group_sorted = group.sort_values('dt')
        
        return pd.Series({
            'open': group_sorted['mid_price'].iloc[0],   # 最早时间的价格
            'high': group_sorted['mid_price'].max(),     # 最高价格
            'low': group_sorted['mid_price'].min(),      # 最低价格
            'close': group_sorted['mid_price'].iloc[-1], # 最晚时间的价格
            'first_time': group_sorted['dt'].iloc[0],    # 保留第一个时间用于验证
            'last_time': group_sorted['dt'].iloc[-1]     # 保留最后一个时间用于验证
        })
    
    # 应用自定义OHLC计算
    try:
        agg_result = grouped.apply(get_ohlc, include_groups=False).reset_index()
        
        # 检查聚合结果是否为空或结构异常
        if agg_result.empty:
            print(f"  警告：聚合结果为空")
            return pd.DataFrame(columns=['symbol', 'time', 'open', 'high', 'low', 'close'])
        
        # 检查必需的列是否存在
        required_cols = ['symbol', 'time_bucket', 'open', 'high', 'low', 'close', 'first_time', 'last_time']
        missing_cols = [col for col in required_cols if col not in agg_result.columns]
        if missing_cols:
            print(f"  错误：缺少必需的列: {missing_cols}")
            return pd.DataFrame(columns=['symbol', 'time', 'open', 'high', 'low', 'close'])
        
        # 将时间桶转换为人类可读的UTC格式
        agg_result['time'] = agg_result['time_bucket'].dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # 保留最终需要的列
        agg_result = agg_result[['symbol', 'time', 'open', 'high', 'low', 'close', 'time_bucket', 'first_time', 'last_time']]
        
        print(f"  聚合后行数: {len(agg_result):,}")
        return agg_result
        
    except Exception as e:
        print(f"  聚合出错: {e}")
        print(f"  返回空结果以继续处理")
        return pd.DataFrame(columns=['symbol', 'time', 'open', 'high', 'low', 'close'])

def main():
    args = parse_args()
    
    print(f"输入文件: {args.in_csv}")
    print(f"输出文件: {args.out_csv}")
    print(f"Chunk大小: {args.chunksize:,}")
    print(f"聚合模式: {'开启 (30分钟)' if args.aggregate else '关闭'}")
    if args.aggregate:
        print(f"时间戳单位: {args.ts_unit}")
    print("-" * 50)

    # 读取CSV文件，分块处理
    reader = pd.read_csv(args.in_csv, chunksize=args.chunksize, low_memory=False)
    
    total_rows = 0
    total_btc_rows = 0
    first_chunk = True
    
    # 存储聚合结果（如果需要聚合）
    all_aggregated_data = []

    for i, chunk in enumerate(reader, 1):
        print(f"\n[Chunk {i}] 处理中...")
        
        # 步骤1：过滤数据（删除ETH，保留BTC）
        filtered_chunk = filter_btc_only(chunk)
        
        total_rows += len(chunk)
        total_btc_rows += len(filtered_chunk)
        
        if len(filtered_chunk) == 0:
            print(f"[Chunk {i}] 没有BTC数据，跳过")
            continue
        
        if args.aggregate:
            # 步骤2：聚合模式 - 预处理并聚合
            try:
                processed_chunk = preprocess_for_aggregation(filtered_chunk, args.ts_unit)
                aggregated_chunk = aggregate_30min(processed_chunk)
                
                if len(aggregated_chunk) > 0:
                    all_aggregated_data.append(aggregated_chunk)
                    print(f"[Chunk {i}] 聚合完成")
                else:
                    print(f"[Chunk {i}] 聚合结果为空，跳过")
                    
            except Exception as e:
                print(f"[Chunk {i}] 聚合出错: {e}")
                print(f"[Chunk {i}] 继续处理下一个chunk")
        else:
            # 步骤2：非聚合模式 - 直接保存过滤后的数据
            if first_chunk:
                filtered_chunk.to_csv(args.out_csv, index=False, mode='w')
                first_chunk = False
            else:
                filtered_chunk.to_csv(args.out_csv, index=False, mode='a', header=False)
            
            print(f"[Chunk {i}] 直接保存完成")

    # 处理聚合模式的最终合并
    if args.aggregate:
        if all_aggregated_data:
            print(f"\n开始合并 {len(all_aggregated_data)} 个聚合结果...")
            
            try:
                # 合并所有聚合结果
                combined_data = pd.concat(all_aggregated_data, ignore_index=True)
                
                # 对合并后的数据再次聚合（因为同一时间桶可能分布在不同chunk中）
                print("对合并数据进行最终聚合...")
                
                # 按 symbol 和 time_bucket 分组进行最终聚合
                final_grouped = combined_data.groupby(['symbol', 'time_bucket'])
                
                def final_ohlc_merge(group, symbol, time_bucket):
                    """正确合并跨chunk的OHLC数据"""
                    # 找到真正的开盘价：最早时间对应的开盘价
                    earliest_idx = group['first_time'].idxmin()
                    true_open = group.loc[earliest_idx, 'open']
                    
                    # 找到真正的收盘价：最晚时间对应的收盘价  
                    latest_idx = group['last_time'].idxmax()
                    true_close = group.loc[latest_idx, 'close']
                    
                    # 最高价和最低价取所有chunk的极值
                    true_high = group['high'].max()
                    true_low = group['low'].min()
                    
                    # 时间信息用于验证
                    earliest_time = group['first_time'].min()
                    latest_time = group['last_time'].max()
                    
                    return pd.Series({
                        'symbol': symbol,
                        'open': true_open,
                        'high': true_high,
                        'low': true_low,
                        'close': true_close,
                        'earliest_time': earliest_time,
                        'latest_time': latest_time,
                        'time_bucket': time_bucket
                    })
                
                # 应用最终合并逻辑，手动处理分组
                final_results = []
                for (symbol, time_bucket), group in final_grouped:
                    try:
                        result = final_ohlc_merge(group, symbol, time_bucket)
                        final_results.append(result)
                    except Exception as e:
                        print(f"合并出错 {symbol} {time_bucket}: {e}")
                        continue
                
                if final_results:
                    final_result = pd.DataFrame(final_results)
                    
                    # 格式化时间为人类可读格式
                    final_result['time'] = final_result['time_bucket'].dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                    
                    # 保留最终需要的列，并按symbol和时间排序
                    final_result = final_result[['symbol', 'time', 'open', 'high', 'low', 'close']]
                    final_result = final_result.sort_values(['symbol', 'time'])
                    
                    # 保存最终结果
                    final_result.to_csv(args.out_csv, index=False)
                    
                    print(f"最终聚合结果: {len(final_result):,} 行")
                else:
                    print("警告：没有成功的聚合结果可保存")
                    
            except Exception as e:
                print(f"最终合并出错: {e}")
                print("尝试保存部分结果...")
                
                # 尝试保存原始的聚合结果（不进行跨chunk合并）
                try:
                    if all_aggregated_data:
                        simple_result = pd.concat(all_aggregated_data, ignore_index=True)
                        simple_result = simple_result[['symbol', 'time', 'open', 'high', 'low', 'close']]
                        simple_result.to_csv(args.out_csv, index=False)
                        print(f"保存了简化结果: {len(simple_result):,} 行")
                    else:
                        print("没有可保存的数据")
                except Exception as e2:
                    print(f"保存简化结果也失败: {e2}")
        else:
            print("警告：没有聚合数据可保存")

    print("\n" + "="*50)
    print(f"处理完成！")
    print(f"总处理行数: {total_rows:,}")
    print(f"保留BTC行数: {total_btc_rows:,}")
    print(f"删除ETH行数: {total_rows - total_btc_rows:,}")
    print(f"保留比例: {total_btc_rows/total_rows*100:.1f}%")
    print(f"输出文件: {args.out_csv}")
    
    if args.aggregate:
        print(f"聚合模式: 30分钟K线数据已生成")

if __name__ == "__main__":
    main()
