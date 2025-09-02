#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
期权数据覆盖情况检查器
功能：
1. 扫描指定目录下的所有CSV文件
2. 分析每个文件的时间范围
3. 找出缺失的日期
4. 生成数据覆盖报告
"""

import os
import pandas as pd
from datetime import datetime, timedelta
import argparse
import re
from pathlib import Path

class DataCoverageChecker:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.file_dates = {}  # 存储文件名对应的日期
        self.file_time_ranges = {}  # 存储每个文件的实际时间范围
        
    def extract_date_from_filename(self, filename):
        """从文件名提取日期"""
        # 匹配格式：okex-options_quotes_2024-01-10_OPTIONS_30min_klines.csv
        pattern = r'(\d{4}-\d{2}-\d{2})'
        match = re.search(pattern, filename)
        if match:
            return datetime.strptime(match.group(1), '%Y-%m-%d').date()
        return None
    
    def analyze_file_content(self, file_path, sample_size=1000):
        """分析文件内容的时间范围"""
        try:
            # 读取文件的前几行和后几行来确定时间范围
            df_head = pd.read_csv(file_path, nrows=sample_size)
            
            # 如果文件很大，也读取末尾部分
            with open(file_path, 'r') as f:
                lines = f.readlines()
                total_lines = len(lines)
            
            if total_lines > sample_size * 2:
                df_tail = pd.read_csv(file_path, skiprows=range(1, total_lines - sample_size))
                df_sample = pd.concat([df_head, df_tail])
            else:
                df_sample = df_head
                
            if 'time' not in df_sample.columns:
                return None, None, 0
                
            # 转换时间列
            df_sample['time'] = pd.to_datetime(df_sample['time'])
            
            min_time = df_sample['time'].min()
            max_time = df_sample['time'].max()
            record_count = len(df_sample)
            
            return min_time, max_time, record_count
            
        except Exception as e:
            print(f"分析文件 {file_path} 时出错: {e}")
            return None, None, 0
    
    def scan_directory(self):
        """扫描目录并收集文件信息"""
        print(f"扫描目录: {self.data_dir}")
        
        if not self.data_dir.exists():
            print(f"错误：目录不存在 {self.data_dir}")
            return
        
        csv_files = list(self.data_dir.glob("*.csv"))
        print(f"找到 {len(csv_files)} 个CSV文件")
        
        if not csv_files:
            print("没有找到CSV文件")
            return
        
        for i, csv_file in enumerate(csv_files, 1):
            print(f"处理文件 {i}/{len(csv_files)}: {csv_file.name}")
            
            # 从文件名提取日期
            file_date = self.extract_date_from_filename(csv_file.name)
            if file_date:
                self.file_dates[csv_file.name] = file_date
            
            # 分析文件内容的时间范围
            min_time, max_time, record_count = self.analyze_file_content(csv_file)
            
            if min_time and max_time:
                self.file_time_ranges[csv_file.name] = {
                    'min_time': min_time,
                    'max_time': max_time,
                    'record_count': record_count,
                    'file_date': file_date
                }
                print(f"  时间范围: {min_time.strftime('%Y-%m-%d %H:%M')} 到 {max_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"  记录数: {record_count}")
            else:
                print(f"  无法获取时间信息")
    
    def find_missing_dates(self):
        """找出缺失的日期"""
        if not self.file_dates:
            print("没有可分析的文件日期")
            return
        
        # 获取完整的日期范围
        all_dates = list(self.file_dates.values())
        min_date = min(all_dates)
        max_date = max(all_dates)
        
        print(f"\n数据日期范围: {min_date} 到 {max_date}")
        print(f"总天数: {(max_date - min_date).days + 1}")
        print(f"有数据的天数: {len(all_dates)}")
        
        # 生成完整的日期序列
        current_date = min_date
        expected_dates = []
        
        while current_date <= max_date:
            expected_dates.append(current_date)
            current_date += timedelta(days=1)
        
        # 找出缺失的日期
        existing_dates = set(all_dates)
        missing_dates = [date for date in expected_dates if date not in existing_dates]
        
        if missing_dates:
            print(f"\n❌ 发现 {len(missing_dates)} 个缺失日期:")
            for date in sorted(missing_dates):
                weekday = date.strftime('%A')
                print(f"  {date} ({weekday})")
        else:
            print(f"\n✅ 没有缺失的日期！")
        
        return missing_dates
    
    def generate_summary_report(self):
        """生成汇总报告"""
        print("\n" + "="*60)
        print("数据覆盖情况汇总报告")
        print("="*60)
        
        if not self.file_time_ranges:
            print("没有可分析的数据")
            return
        
        # 按文件日期排序
        sorted_files = sorted(
            self.file_time_ranges.items(), 
            key=lambda x: x[1]['file_date'] if x[1]['file_date'] else datetime.min.date()
        )
        
        # 统计信息
        total_files = len(sorted_files)
        total_records = sum(info['record_count'] for _, info in sorted_files)
        
        # 整体时间范围（基于文件内容）
        all_min_times = [info['min_time'] for _, info in sorted_files if info['min_time']]
        all_max_times = [info['max_time'] for _, info in sorted_files if info['max_time']]
        
        if all_min_times and all_max_times:
            overall_start = min(all_min_times)
            overall_end = max(all_max_times)
            
            print(f"文件总数: {total_files}")
            print(f"总记录数: {total_records:,}")
            print(f"整体时间范围: {overall_start.strftime('%Y-%m-%d %H:%M:%S')} 到 {overall_end.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"时间跨度: {(overall_end - overall_start).days + 1} 天")
        
        # 详细文件信息（显示前10个和后10个）
        print(f"\n文件详情:")
        print(f"{'文件名':<50} {'日期':<12} {'最早时间':<20} {'最晚时间':<20} {'记录数':<8}")
        print("-" * 110)
        
        display_count = min(10, len(sorted_files))
        
        # 显示前几个文件
        for filename, info in sorted_files[:display_count]:
            date_str = info['file_date'].strftime('%Y-%m-%d') if info['file_date'] else 'N/A'
            min_time_str = info['min_time'].strftime('%Y-%m-%d %H:%M') if info['min_time'] else 'N/A'
            max_time_str = info['max_time'].strftime('%Y-%m-%d %H:%M') if info['max_time'] else 'N/A'
            
            print(f"{filename:<50} {date_str:<12} {min_time_str:<20} {max_time_str:<20} {info['record_count']:<8}")
        
        if len(sorted_files) > 20:
            print("...")
            # 显示后几个文件
            for filename, info in sorted_files[-display_count:]:
                date_str = info['file_date'].strftime('%Y-%m-%d') if info['file_date'] else 'N/A'
                min_time_str = info['min_time'].strftime('%Y-%m-%d %H:%M') if info['min_time'] else 'N/A'
                max_time_str = info['max_time'].strftime('%Y-%m-%d %H:%M') if info['max_time'] else 'N/A'
                
                print(f"{filename:<50} {date_str:<12} {min_time_str:<20} {max_time_str:<20} {info['record_count']:<8}")
        elif len(sorted_files) > display_count:
            # 显示剩余文件
            for filename, info in sorted_files[display_count:]:
                date_str = info['file_date'].strftime('%Y-%m-%d') if info['file_date'] else 'N/A'
                min_time_str = info['min_time'].strftime('%Y-%m-%d %H:%M') if info['min_time'] else 'N/A'
                max_time_str = info['max_time'].strftime('%Y-%m-%d %H:%M') if info['max_time'] else 'N/A'
                
                print(f"{filename:<50} {date_str:<12} {min_time_str:<20} {max_time_str:<20} {info['record_count']:<8}")

def main():
    parser = argparse.ArgumentParser(description="期权数据覆盖情况检查器")
    parser.add_argument("--data-dir", 
                       default="/home/ubuntu/options_trading/data/okx_data_processor/okx_options/options_with_spot",
                       help="数据目录路径")
    
    args = parser.parse_args()
    
    print("期权数据覆盖情况检查器")
    print("="*60)
    
    checker = DataCoverageChecker(args.data_dir)
    
    # 扫描目录
    checker.scan_directory()
    
    # 查找缺失日期
    missing_dates = checker.find_missing_dates()
    
    # 生成报告
    checker.generate_summary_report()
    
    if missing_dates:
        print(f"\n⚠️  注意：发现 {len(missing_dates)} 个缺失日期")
    else:
        print(f"\n✅ 数据完整，无缺失日期")

if __name__ == "__main__":
    main()
