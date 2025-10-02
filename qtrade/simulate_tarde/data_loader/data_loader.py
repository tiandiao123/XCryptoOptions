import pandas as pd
from datetime import datetime
import sys
import os

from qtrade.simulate_tarde.data_loader.data_utils import (
    get_sorted_dates_from_files, 
    get_intraday_30min_data, 
    get_atm_options_at_time,
    get_option_open_price
)

class ATMOptionsIterator:
    """
    ATM期权迭代器
    遍历指定文件夹中所有CSV文件的所有时间点，提取ATM期权信息
    """
    
    def __init__(self, folder_path, atm_tolerance=0.05, min_days_to_expiry=2, silent_mode=False):
        """
        初始化ATM期权迭代器
        
        Args:
            folder_path: 包含CSV文件的文件夹路径
            atm_tolerance: ATM容忍度（默认5%）
            min_days_to_expiry: 最小到期天数（默认2天，排除当天交割）
            silent_mode: 静默模式（默认False）
        """
        self.folder_path = folder_path
        self.atm_tolerance = atm_tolerance
        self.min_days_to_expiry = min_days_to_expiry
        self.silent_mode = silent_mode
        
        # 获取所有日期和文件映射
        if not silent_mode:
            print(f"🚀 初始化ATM期权迭代器...")
        self.dates, self.date_files = get_sorted_dates_from_files(folder_path, print_info=not silent_mode)
        
        if not silent_mode:
            print(f"📊 配置参数:")
            print(f"   ATM容忍度: ±{atm_tolerance*100:.1f}%")
            print(f"   最小到期天数: {min_days_to_expiry}天")
        
        # 迭代状态
        self.current_date_idx = 0
        self.current_time_idx = 0
        self.current_times = []
        self.current_df = None
        
        # 统计信息
        self.stats = {
            'total_dates': len(self.dates),
            'processed_dates': 0,
            'total_time_points': 0,
            'total_atm_options': 0,
            'failed_dates': []
        }
    
    def __iter__(self):
        """实现迭代器协议"""
        self.current_date_idx = 0
        self.current_time_idx = 0
        self.current_times = []  # 确保初始为空，强制加载第一个日期
        return self
    
    def __next__(self):
        """
        获取下一个时间点的ATM期权列表
        
        Returns:
            dict: {
                'date': 当前日期,
                'time': 当前时间点,
                'spot_price': 现货价格,
                'atm_options': ATM期权列表
            }
        """
        # 如果所有日期都处理完了
        if self.current_date_idx >= len(self.dates):
            raise StopIteration
        
        # 如果当前日期的时间点都处理完了，加载下一个日期
        if self.current_time_idx >= len(self.current_times):
            # 如果不是第一次加载，移动到下一个日期
            if self.current_times:  # 如果之前已加载过数据，说明当前日期已处理完
                self.current_date_idx += 1
            
            success = self._load_next_date()
            if not success:
                raise StopIteration
        
        # 获取当前时间点的ATM期权
        current_time = self.current_times[self.current_time_idx]
        current_spot = self.current_time_price_map[current_time]
        
        # 获取ATM期权
        atm_options = get_atm_options_at_time(
            self.current_df, 
            current_time, 
            spot_price=current_spot, 
            atm_tolerance=self.atm_tolerance,
            print_info=False
        )
        
        # 过滤最小到期天数
        filtered_atm_options = [
            opt for opt in atm_options 
            if opt['days_to_expiry'] >= self.min_days_to_expiry
        ]
        
        # 更新统计
        self.stats['total_time_points'] += 1
        self.stats['total_atm_options'] += len(filtered_atm_options)
        
        # 准备返回数据
        result = {
            'date': self.dates[self.current_date_idx],
            'time': current_time,
            'spot_price': current_spot,
            'atm_options': filtered_atm_options,
            'data': self.current_df, # 原始数据
            'total_atm_count': len(filtered_atm_options)
        }
        
        # 移动到下一个时间点
        self.current_time_idx += 1
        
        return result
    
    def _load_next_date(self):
        """加载当前日期的数据"""
        if self.current_date_idx >= len(self.dates):
            return False
            
        current_date = self.dates[self.current_date_idx]
        file_path = self.date_files[current_date]
        
        # print(f"\n📅 处理日期 {self.current_date_idx + 1}/{len(self.dates)}: {current_date}")  # 静默模式
        
        try:
            # 获取当天的30分钟数据
            times, prices, time_price_map, df = get_intraday_30min_data(file_path, print_info=False)
            
            if len(times) > 0:
                self.current_times = times
                self.current_time_price_map = time_price_map
                self.current_df = df
                self.current_time_idx = 0
                self.stats['processed_dates'] += 1
                
                # print(f"   ✅ 成功加载 {len(times)} 个时间点")  # 静默模式
                return True
            else:
                # print(f"   ⚠️  该日期没有有效数据，跳过")  # 静默模式
                # 没有数据，跳到下一个日期
                self.current_date_idx += 1
                return self._load_next_date()  # 递归尝试下一个日期
                
        except Exception as e:
            # print(f"   ❌ 加载日期失败: {e}")  # 静默模式
            self.stats['failed_dates'].append(current_date)
            # 加载失败，跳到下一个日期
            self.current_date_idx += 1
            return self._load_next_date()  # 递归尝试下一个日期
    
    def get_summary_stats(self):
        """获取统计摘要"""
        return self.stats.copy()
    
    def iterate_date_range(self, start_date, end_date):
        """
        迭代指定日期范围的ATM期权
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Yields:
            dict: 时间点ATM期权信息
        """
        # 找到日期范围内的日期
        target_dates = [date for date in self.dates if start_date <= date <= end_date]
        
        if not target_dates:
            print(f"⚠️  日期范围 {start_date} 到 {end_date} 内没有数据")
            return
        
        # 遍历目标日期
        for target_date in target_dates:
            file_path = self.date_files[target_date]
            
            try:
                # 获取该日期的数据
                times, prices, time_price_map, df = get_intraday_30min_data(file_path, print_info=False)
                
                for time_point in times:
                    spot_price = time_price_map[time_point]
                    atm_options = get_atm_options_at_time(
                        df, time_point, spot_price, self.atm_tolerance, print_info=False
                    )
                    
                    # 过滤最小到期天数
                    filtered_options = [
                        opt for opt in atm_options 
                        if opt['days_to_expiry'] >= self.min_days_to_expiry
                    ]
                    
                    yield {
                        'date': target_date,
                        'time': time_point,
                        'spot_price': spot_price,
                        'atm_options': filtered_options,
                        'data': df,
                        'total_atm_count': len(filtered_options)
                    }
                    
            except Exception as e:
                if not self.silent_mode:
                    print(f"❌ 处理日期 {target_date} 失败: {e}")
                continue
    
    def get_atm_options_for_date(self, target_date):
        """
        获取指定日期所有时间点的ATM期权
        
        Args:
            target_date: 目标日期
            
        Returns:
            list: 该日期所有时间点的ATM期权数据
        """
        if target_date not in self.date_files:
            print(f"❌ 日期 {target_date} 不存在")
            return []
        
        file_path = self.date_files[target_date]
        
        try:
            # 获取该日期的数据
            times, prices, time_price_map, df = get_intraday_30min_data(file_path, print_info=False)
            
            date_atm_options = []
            
            for time_point in times:
                spot_price = time_price_map[time_point]
                atm_options = get_atm_options_at_time(df, time_point, spot_price, self.atm_tolerance, print_info=False)
                
                # 过滤最小到期天数
                filtered_options = [
                    opt for opt in atm_options 
                    if opt['days_to_expiry'] >= self.min_days_to_expiry
                ]
                
                if filtered_options:
                    date_atm_options.append({
                        'date': target_date,
                        'time': time_point,
                        'spot_price': spot_price,
                        'atm_options': filtered_options
                    })
            
            return date_atm_options
            
        except Exception as e:
            print(f"❌ 处理日期 {target_date} 失败: {e}")
            return []



if __name__ == "__main__":
    import time
    from tqdm import tqdm
    
    print("🚀 ATM期权迭代器完整遍历模式")
    print("="*60)
    
    # 基本迭代使用
    iterator = ATMOptionsIterator(
        '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks',
        silent_mode=True  # 使用静默模式避免过多输出
    )
    
    print(f"📊 总文件数: {len(iterator.dates)}")
    print(f"📅 日期范围: {iterator.dates[0]} 到 {iterator.dates[-1]}")


    for info in iterator.iterate_date_range(iterator.dates[0], iterator.dates[5]):
        print(f"date: {info['date']}, time: {info['time']}, spot_price: {info['spot_price']}")


    # 计算实际总时间点数
    print(f"🔍 正在计算实际时间点数...")
    actual_total_points = 0
    for i, date in enumerate(iterator.dates):
        try:
            file_path = iterator.date_files[date]
            times, _, _, _ = get_intraday_30min_data(file_path, print_info=False)
            actual_total_points += len(times)
            
            # 显示进度
            if (i + 1) % 10 == 0 or (i + 1) == len(iterator.dates):
                print(f"   已扫描 {i + 1}/{len(iterator.dates)} 个文件，找到 {actual_total_points:,} 个时间点")
        except Exception as e:
            print(f"   ⚠️  扫描日期 {date} 失败: {e}")
            continue
    
    print(f"⏰ 实际总时间点: {actual_total_points:,}")
    print(f"⏱️  估算用时: {actual_total_points * 0.02 / 60:.1f}-{actual_total_points * 0.05 / 60:.1f}分钟")
    
    # 确认是否继续
    choice = input("\n确认开始完整遍历? (y/n): ").strip().lower()
    if choice not in ['y', 'yes']:
        print("❌ 用户取消")
        exit()
    
    # 记录开始时间
    start_time = time.time()
    processed_count = 0
    total_atm_count = 0
    
    print(f"\n🚀 开始完整遍历...")
    print(f"⏱️  开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💡 可以随时按Ctrl+C中断")
    
    try:
        # 使用tqdm添加进度条，使用实际总数
        with tqdm(total=actual_total_points,
                  desc="Processing ATM Options",
                  unit="timepoints",
                  bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            
            for time_point_data in iterator:
                processed_count += 1
                date = time_point_data['date'] 
                time_obj = time_point_data['time']
                spot = time_point_data['spot_price']
                atm_options = time_point_data['atm_options']
                total_atm_count += len(atm_options)
                
                # 更新进度条
                pbar.update(1)
                pbar.set_postfix({
                    'Date': date.strftime('%m-%d'),
                    'ATM': len(atm_options),
                    'Total_ATM': f"{total_atm_count:,}",
                    'Files': f"{iterator.stats['processed_dates']}/{len(iterator.dates)}"
                })
                
                # 每1000个时间点详细显示一次
                # if processed_count % 1000 == 0:
                elapsed = time.time() - start_time
                print(f"\n📊 里程碑 - 已处理 {processed_count:,} 个时间点:")
                print(f"   当前日期: {date}")
                print(f"   已用时: {elapsed/60:.1f}分钟")
                print(f"   累计ATM期权: {total_atm_count:,}")
                print(f"   处理速度: {processed_count/elapsed:.1f} 时间点/秒")
                
    except KeyboardInterrupt:
        print(f"\n⚠️  用户中断（已处理{processed_count:,}个时间点）")
    
    # 最终统计
    total_elapsed = time.time() - start_time
    
    print(f"\n" + "="*60)
    print(f"✅ 遍历完成！")
    print(f"="*60)
    print(f"⏱️  总用时: {total_elapsed:.2f}秒 ({total_elapsed/60:.1f}分钟)")
    print(f"📈 处理时间点: {processed_count:,}")
    print(f"📊 总ATM期权: {total_atm_count:,}")
    print(f"📈 平均每时间点: {total_elapsed/processed_count:.3f}秒")
    print(f"📊 平均每时间点ATM期权: {total_atm_count/processed_count:.1f}个")
    
    # 迭代器统计
    stats = iterator.get_summary_stats()
    print(f"\n📊 详细统计:")
    print(f"   处理成功日期: {stats['processed_dates']}/{stats['total_dates']}")
    print(f"   成功率: {stats['processed_dates']/stats['total_dates']*100:.1f}%")
    print(f"   失败日期数: {len(stats['failed_dates'])}")
    if stats['failed_dates']:
        print(f"   失败日期: {stats['failed_dates'][:5]}...")  # 只显示前5个