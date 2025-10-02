import pandas as pd
import numpy as np
import os

def extract_atm_options(df, days_threshold_min, days_threshold_max, output_suffix):
    """
    提取ATM期权
    
    参数:
    df: 原始数据DataFrame
    days_threshold_min: 到期天数最小值
    days_threshold_max: 到期天数最大值
    output_suffix: 输出文件后缀
    """
    
    # 筛选指定到期天数范围的期权
    filtered_df = df[(df['days_to_expiry'] >= days_threshold_min) & 
                     (df['days_to_expiry'] <= days_threshold_max)]
    
    print(f"筛选到期天数在 {days_threshold_min} 到 {days_threshold_max} 天的期权:")
    print(f"共找到 {len(filtered_df)} 条记录")
    
    if len(filtered_df) == 0:
        print("没有找到符合条件的期权")
        return None
    
    # 为每个时间点和期权类型找出ATM期权
    atm_options = []
    
    # 按时间分组
    for time_group, time_data in filtered_df.groupby('time'):
        spot_price = time_data['spot_price'].iloc[0]
        
        # 分别处理看涨期权和看跌期权
        for option_type in ['C', 'P']:
            type_data = time_data[time_data['option_type'] == option_type]
            
            if len(type_data) == 0:
                continue
                
            # 计算执行价格与现货价格的差异
            type_data = type_data.copy()
            type_data['price_diff'] = abs(type_data['strike_price'] - spot_price)
            
            # 找到差异最小的期权（ATM期权）
            min_diff_idx = type_data['price_diff'].idxmin()
            atm_option = type_data.loc[min_diff_idx]
            
            atm_options.append(atm_option)
    
    # 转换为DataFrame
    atm_df = pd.DataFrame(atm_options)
    
    if len(atm_df) > 0:
        # 添加价格差异百分比
        atm_df['price_diff_pct'] = abs(atm_df['strike_price'] - atm_df['spot_price']) / atm_df['spot_price'] * 100
        
        print(f"提取到 {len(atm_df)} 个ATM期权")
        print(f"执行价格与现货价格差异统计:")
        print(f"平均差异: {atm_df['price_diff_pct'].mean():.2f}%")
        print(f"最大差异: {atm_df['price_diff_pct'].max():.2f}%")
        print(f"最小差异: {atm_df['price_diff_pct'].min():.2f}%")
        
        # 保存结果
        output_filename = f"atm_options_{output_suffix}.csv"
        atm_df.to_csv(output_filename, index=False)
        print(f"结果已保存到: {output_filename}")
        
        return atm_df
    else:
        print("没有找到ATM期权")
        return None

def main():
    # 读取原始数据
    input_file = 'data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks/okex-options_quotes_2021-01-12_OPTIONS_30min_klines_with_iv_greeks.csv'
    
    print("正在读取数据...")
    df = pd.read_csv(input_file)
    print(f"原始数据: {len(df)} 条记录")
    
    print("\n" + "="*50)
    print("1. 提取当天到期的ATM期权")
    print("="*50)
    same_day_atm = extract_atm_options(df, 0, 0.1, "same_day_expiry")
    
    print("\n" + "="*50)
    print("2. 提取3天后到期的ATM期权")
    print("="*50)
    three_day_atm = extract_atm_options(df, 2.8, 3.2, "3day_expiry")
    
    # 显示示例数据
    if same_day_atm is not None and len(same_day_atm) > 0:
        print("\n当天到期ATM期权示例:")
        print(same_day_atm[['symbol', 'time', 'strike_price', 'spot_price', 'option_type', 'days_to_expiry', 'price_diff_pct']].head(10))
    
    if three_day_atm is not None and len(three_day_atm) > 0:
        print("\n3天后到期ATM期权示例:")
        print(three_day_atm[['symbol', 'time', 'strike_price', 'spot_price', 'option_type', 'days_to_expiry', 'price_diff_pct']].head(10))

if __name__ == "__main__":
    main()

