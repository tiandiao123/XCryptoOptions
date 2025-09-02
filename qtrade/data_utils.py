
import os
import re
from datetime import datetime
from pathlib import Path

def get_sorted_dates_from_files(folder_path, print_info=True):
    """
    从文件夹中的CSV文件名提取日期并返回排序后的日期列表和文件映射
    
    Args:
        folder_path: 文件夹路径
        
    Returns:
        tuple: (sorted_dates, date_to_file_dict)
            - sorted_dates: 排序后的datetime.date对象列表
            - date_to_file_dict: 日期到文件路径的映射字典 {date: file_path}
    """
    
    folder = Path(folder_path)
    
    if not folder.exists():
        raise ValueError(f"文件夹不存在: {folder_path}")
    
    dates = []
    date_to_file = {}  # 新增：日期到文件路径的映射
    pattern = r'okex-options_quotes_(\d{4}-\d{2}-\d{2})_OPTIONS_30min_klines_with_iv_greeks\.csv'
    
    # 扫描文件夹中的所有CSV文件
    for file_path in folder.glob("*.csv"):
        filename = file_path.name
        match = re.match(pattern, filename)
        
        if match:
            date_str = match.group(1)  # 提取 YYYY-MM-DD
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                dates.append(date_obj)
                date_to_file[date_obj] = str(file_path)  # 存储完整文件路径
            except ValueError:
                print(f"警告: 无法解析日期 {date_str} 从文件 {filename}")
        else:
            print(f"警告: 文件名格式不匹配 {filename}")
    
    # 排序并去重
    unique_dates = sorted(list(set(dates)))
    
    if print_info:
        print(f"✅ 成功提取 {len(unique_dates)} 个唯一日期")
        print(f"📅 日期范围: {unique_dates[0]} 到 {unique_dates[-1]}" if unique_dates else "📅 未找到有效日期")
        print(f"📁 文件映射: {len(date_to_file)} 个文件")
    
    return unique_dates, date_to_file


def get_intraday_30min_data(csv_file_path, price_type='spot_open', print_info=True):
    """
    从CSV文件中提取一天的30分钟时间段和对应的现货价格（去重）
    
    Args:
        csv_file_path: CSV文件路径
        price_type: 价格类型，可选 'spot_open', 'spot_close', 'spot_high', 'spot_low'
        
    Returns:
        tuple: (time_list, price_list, time_price_dict)
            - time_list: 排序后的唯一时间列表 (datetime对象)
            - price_list: 对应的现货价格列表
            - time_price_dict: 时间到价格的映射字典 {datetime: price}
    """
    import pandas as pd
    from datetime import datetime
    import os
    
    try:
        # 读取CSV文件
        df = pd.read_csv(csv_file_path)
        
        # 检查必要的列
        required_columns = ['time', price_type]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"CSV文件缺少必要列: {missing_columns}")
        
        # 转换时间格式
        df['datetime'] = pd.to_datetime(df['time'])
        
        # 过滤有效数据
        df = df.dropna(subset=['datetime', price_type])
        
        if len(df) == 0:
            print(f"⚠️  文件中没有有效数据: {os.path.basename(csv_file_path)}")
            return [], [], {}
        
        # 关键修复：按时间去重，每个时间点只保留一条记录
        # 使用groupby取每个时间点的第一个价格值（同一时间点spot price应该相同）
        unique_df = df.groupby('datetime').agg({
            price_type: 'first'  # 取第一个值
        }).reset_index()
        
        # 按时间排序
        unique_df = unique_df.sort_values('datetime')
        
        # 提取时间和价格
        time_list = unique_df['datetime'].tolist()
        price_list = unique_df[price_type].tolist()
        
        # 创建时间到价格的映射
        time_price_dict = dict(zip(time_list, price_list))
        
        # 统计信息
        if print_info:
            date_str = time_list[0].strftime('%Y-%m-%d') if time_list else 'Unknown'
            print(f"📊 {date_str} 30分钟数据:")
            print(f"   原始记录数: {len(df)}")
            print(f"   去重后时间点: {len(time_list)}")
            print(f"   时间范围: {time_list[0].strftime('%H:%M')} - {time_list[-1].strftime('%H:%M')}")
            print(f"   {price_type}价格范围: ${min(price_list):,.2f} - ${max(price_list):,.2f}")
            print(f"   平均价格: ${sum(price_list)/len(price_list):,.2f}")
        
        return time_list, price_list, time_price_dict, df 
        
    except Exception as e:
        print(f"❌ 读取文件失败: {os.path.basename(csv_file_path)} - {e}")
        return [], [], {}


def get_atm_options_at_time(df, target_time, spot_price=None, atm_tolerance=0.05, print_info=True):
    """
    获取指定时间点的ATM期权信息
    
    Args:
        df: pandas DataFrame，包含期权数据
        target_time: 目标时间点，可以是字符串或datetime对象
        spot_price: 现货价格（可选），如果不提供则使用DataFrame中的spot_open
        atm_tolerance: ATM容忍度（默认5%，即0.95-1.05 moneyness）
        
    Returns:
        list: ATM期权信息字典列表，每个dict包含：
              symbol, open, spot_open, iv, delta, gamma, vega, days_to_expiry
    """
    import pandas as pd
    from datetime import datetime
    
    try:
        # 转换目标时间为datetime对象
        if isinstance(target_time, str):
            if 'UTC' in target_time:
                target_dt = pd.to_datetime(target_time)
            else:
                target_dt = pd.to_datetime(target_time + ' UTC')
        else:
            target_dt = pd.to_datetime(target_time)
        
        # 转换DataFrame的时间列
        if 'datetime' not in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])
        
        # 筛选指定时间点的数据
        time_filtered_df = df[df['datetime'] == target_dt].copy()
        
        if len(time_filtered_df) == 0:
            if print_info:
                print(f"⚠️  时间点 {target_dt} 没有找到数据")
            return []
        
        if print_info:
            print(f"📊 时间点 {target_dt.strftime('%Y-%m-%d %H:%M:%S')} 的期权数据:")
            print(f"   原始记录数: {len(time_filtered_df)}")
        
        # 使用提供的spot_price或DataFrame中的spot_open
        if spot_price is not None:
            current_spot = spot_price
            time_filtered_df['current_spot'] = spot_price
        else:
            if 'spot_open' not in time_filtered_df.columns:
                if print_info:
                    print(f"❌ DataFrame中缺少spot_open列且未提供spot_price")
                return []
            current_spot = time_filtered_df['spot_open'].iloc[0]
            time_filtered_df['current_spot'] = time_filtered_df['spot_open']
        
        # 计算moneyness
        if 'strike_price' not in time_filtered_df.columns:
            if print_info:
                print(f"❌ DataFrame中缺少strike_price列")
            return []
        
        time_filtered_df['moneyness'] = time_filtered_df['current_spot'] / time_filtered_df['strike_price']
        
        # 筛选ATM期权
        atm_df = time_filtered_df[
            (time_filtered_df['moneyness'] >= (1 - atm_tolerance)) & 
            (time_filtered_df['moneyness'] <= (1 + atm_tolerance)) &
            (time_filtered_df['calculation_success'] == True)  # 只要计算成功的
        ].copy()
        
        if len(atm_df) == 0:
            if print_info:
                print(f"   ⚠️  该时间点没有找到ATM期权 (moneyness范围: {1-atm_tolerance:.2f}-{1+atm_tolerance:.2f})")
            return []
        
        if print_info:
            print(f"   ATM期权数量: {len(atm_df)}")
            print(f"   现货价格: ${current_spot:,.2f}")
            print(f"   执行价格范围: ${atm_df["strike_price"].min():,.0f} - ${atm_df["strike_price"].max():,.0f}")
            print(f"   Moneyness范围: {atm_df['moneyness'].min():.3f} - {atm_df['moneyness'].max():.3f}")
        
        # 提取需要的字段，组装成字典列表
        atm_options_list = []
        
        for _, row in atm_df.iterrows():
            option_info = {
                'symbol': row['symbol'],
                'open': row['open'],
                'spot_open': row['current_spot'],
                'strike_price': row['strike_price'],
                'moneyness': row['moneyness'],
                'option_type': row['option_type'],
                'iv': row['iv'],
                'delta': row['pa_delta'],  # 使用BS Delta
                'gamma': row['pa_gamma'],  # 使用BS Gamma  
                'vega': row['pa_vega'],    # 使用BS Vega
                'days_to_expiry': row['days_to_expiry'],
                'time_to_expiry': row['time_to_expiry']
            }
            
            # 如果有PA希腊字母，也包含进去
            if 'pa_delta' in row:
                option_info['pa_delta'] = row['pa_delta']
            if 'pa_gamma' in row:
                option_info['pa_gamma'] = row['pa_gamma']
            if 'pa_vega' in row:
                option_info['pa_vega'] = row['pa_vega']
                
            atm_options_list.append(option_info)
        
        # 按指定规则排序：
        # 1. days_to_expiry 从小到大
        # 2. 相同days_to_expiry的话，按离spot_open最近的排在前面
        atm_options_list.sort(key=lambda x: (
            x['days_to_expiry'], 
            abs(x['strike_price'] - x['spot_open'])
        ))

        if print_info:
            print(f"   ✅ 返回 {len(atm_options_list)} 个ATM期权（按到期时间和价格距离排序）")
        
        return atm_options_list
        
    except Exception as e:
        if print_info:
            print(f"❌ 处理失败: {e}")
        return []


def get_option_open_price(df, symbol, target_time, print_info=True):
    """
    获取指定期权符号在指定时间点的开盘价格
    
    Args:
        df: pandas DataFrame，包含期权数据
        symbol: 期权符号，如 'BTC-USD-210115-35000-C'
        target_time: 目标时间点，可以是字符串或datetime对象
        
    Returns:
        float or None: 开盘价格，如果没找到则返回None
    """
    import pandas as pd
    
    try:
        # 转换目标时间为datetime对象
        if isinstance(target_time, str):
            if 'UTC' in target_time:
                target_dt = pd.to_datetime(target_time)
            else:
                target_dt = pd.to_datetime(target_time + ' UTC')
        else:
            target_dt = pd.to_datetime(target_time)
        
        # 转换DataFrame的时间列（如果还没转换）
        if 'datetime' not in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])
        
        # 筛选匹配的记录
        filtered_df = df[
            (df['symbol'] == symbol) & 
            (df['datetime'] == target_dt)
        ]
        
        if len(filtered_df) == 0:
            print(f"⚠️  没有找到匹配的记录: symbol={symbol}, time={target_dt}")
            return None
        
        if len(filtered_df) > 1:
            print(f"⚠️  找到多条匹配记录({len(filtered_df)}条)，使用第一条")
        
        # 获取开盘价格
        open_price = filtered_df['open'].iloc[0]
        
        # 显示额外信息
        row = filtered_df.iloc[0]

        if print_info:
            print(f"📊 期权信息:")
            print(f"   符号: {symbol}")
            print(f"   时间: {target_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   开盘价: {open_price} BTC")
        
        # 如果有现货价格信息，也显示
        if print_info:
            if 'spot_open' in row:
                print(f"   现货价格: ${row['spot_open']:,.2f}")
            if 'strike_price' in row:
                print(f"   执行价格: ${row['strike_price']:,.2f}")
            if 'iv' in row:
                print(f"   隐含波动率: {row['iv']:.3f} ({row['iv']*100:.1f}%)")
        
        return open_price
        
    except Exception as e:
        print(f"❌ 获取开盘价格失败: {e}")
        return None


def get_option_full_info(df, symbol, target_time, print_info=False):
    """
    获取指定期权符号在指定时间点的完整信息（价格、IV、Delta等）
    
    Args:
        df: pandas DataFrame，包含期权数据
        symbol: 期权符号，如 'BTC-USD-210115-35000-C'
        target_time: 目标时间点，可以是字符串或datetime对象
        print_info: 是否打印详细信息
        
    Returns:
        dict or None: 完整期权信息，如果没找到则返回None
    """
    import pandas as pd
    
    try:
        # 转换目标时间为datetime对象
        if isinstance(target_time, str):
            if 'UTC' in target_time:
                target_dt = pd.to_datetime(target_time)
            else:
                target_dt = pd.to_datetime(target_time + ' UTC')
        else:
            target_dt = pd.to_datetime(target_time)
        
        # 转换DataFrame的时间列（如果还没转换）
        if 'datetime' not in df.columns:
            df['datetime'] = pd.to_datetime(df['time'])
        
        # 筛选匹配的记录
        filtered_df = df[
            (df['symbol'] == symbol) & 
            (df['datetime'] == target_dt)
        ]
        
        if len(filtered_df) == 0:
            if print_info:
                print(f"⚠️  没有找到匹配的记录: symbol={symbol}, time={target_dt}")
            return None
        
        if len(filtered_df) > 1:
            if print_info:
                print(f"⚠️  找到多条匹配记录({len(filtered_df)}条)，使用第一条")
        
        # 获取完整信息
        row = filtered_df.iloc[0]
        
        option_info = {
            'symbol': symbol,
            'time': target_dt,
            'open': row['open'],
            'iv': row.get('iv', 0),
            'iv_percent': row.get('iv_percent', 0),
            'delta': row.get('pa_delta', row.get('bs_delta', 0)),  # 优先使用PA Delta
            'gamma': row.get('pa_gamma', row.get('bs_gamma', 0)),  # 优先使用PA Gamma
            'vega': row.get('pa_vega', row.get('bs_vega', 0)),     # 优先使用PA Vega
            'strike_price': row.get('strike_price', 0),
            'spot_open': row.get('spot_open', 0),
            'days_to_expiry': row.get('days_to_expiry', 0),
            'option_type': row.get('option_type', ''),
            'calculation_success': row.get('calculation_success', False)
        }
        
        if print_info:
            print(f"📊 期权完整信息:")
            print(f"   符号: {symbol}")
            print(f"   时间: {target_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   开盘价: {option_info['open']:.6f} BTC")
            print(f"   IV: {option_info['iv']:.3f} ({option_info['iv_percent']:.1f}%)")
            print(f"   Delta: {option_info['delta']:.3f}")
            print(f"   Gamma: {option_info['gamma']:.6f}")
            print(f"   Vega: {option_info['vega']:.6f}")
            print(f"   执行价格: ${option_info['strike_price']:,.2f}")
            print(f"   现货价格: ${option_info['spot_open']:,.2f}")
            print(f"   到期天数: {option_info['days_to_expiry']:.1f}天")
        
        return option_info
        
    except Exception as e:
        if print_info:
            print(f"❌ 获取期权完整信息失败: {e}")
        return None


if __name__ == "__main__":

    print("======================TESTING TO GET DATE LIST AND FILE MAPPING======================")
    # 获取日期列表和文件映射
    dates, date_files = get_sorted_dates_from_files('/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks')

    # 使用日期列表
    print(f"最早日期: {dates[0]}")
    print(f"最晚日期: {dates[-1]}")

    # 使用文件映射快速读取指定日期的数据
    target_date = dates[10]  # 第11个日期
    file_path = date_files[target_date]
    # Assuming pandas is available for demonstration
    import pandas as pd
    df = pd.read_csv(file_path)
    print(f"日期 {target_date} 的文件: {file_path}")
    print(f"该日期数据行数: {len(df)}")

    print("======================TESTING TO GET 30 MIN DATA======================")

    # 获取某天的30分钟数据
    times, prices, time_price_map, df = get_intraday_30min_data(file_path, price_type='spot_open')

    # 使用时间列表
    print(f"第一个时间点: {times[0]}")
    print(f"对应价格: ${prices[0]:,.2f}")

    # 使用映射字典快速查找
    target_time = times[10]
    price = time_price_map[target_time] 
    print(f"时间 {target_time} 的现货价格: ${price:,.2f}")



    print("======================TESTING TO GET ATM OPTIONS AT TIME======================")
    # 获取指定时间点的ATM期权
    atm_options = get_atm_options_at_time(df, times[10])

    # 查看结果
    for option in atm_options[:10]:  # 显示前3个
        print(f"符号: {option['symbol']}")
        print(f"IV: {option['iv']:.3f} ({option['iv']*100:.1f}%)")
        print(f"Delta: {option['delta']:.3f}")
        print(f"Gamma: {option['gamma']:.3f}")
        print(f"Vega: {option['vega']:.6f}")
        print("---")
    
    print("======================TESTING TO GET OPTION OPEN PRICE======================")

    symbol = atm_options[0]['symbol']
    target_time = times[10]
    # 获取特定期权在特定时间的开盘价
    open_price = get_option_open_price(
        df, 
        symbol=symbol, 
        target_time=target_time
    )

    print(f"open price of {symbol} at {target_time} is {open_price}")
