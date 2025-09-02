#!/usr/bin/env python3
"""
批量处理器
处理options_with_spot目录下的所有CSV文件
为每行期权数据计算IV和希腊字母
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import time
import json
from tqdm import tqdm
from typing import Dict, List, Optional

# 导入我们的核心计算器
from option_calculator import OptionCalculator

class BatchProcessor:
    def __init__(self, 
                 input_dir: str,
                 output_dir: str,
                 rate_cache_dir: str = "./rate_cache"):
        """
        初始化批量处理器
        
        Args:
            input_dir: 输入目录（options_with_spot）
            output_dir: 输出目录
            rate_cache_dir: 利率缓存目录
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.rate_cache_dir = rate_cache_dir
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化计算器
        print("🚀 初始化期权计算器...")
        self.calculator = OptionCalculator(rate_cache_dir=rate_cache_dir)
        
        # 统计信息
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_files': 0,
            'processed_files': 0,
            'failed_files': 0,
            'total_rows': 0,
            'successful_calculations': 0,
            'failed_calculations': 0,
            'processing_rate': 0.0,
            'failed_file_list': []
        }
    
    def get_input_files(self) -> List[Path]:
        """获取输入文件列表"""
        if not self.input_dir.exists():
            raise ValueError(f"输入目录不存在: {self.input_dir}")
        
        # 查找所有CSV文件
        csv_files = list(self.input_dir.glob("okex-options_quotes_*_OPTIONS_30min_klines_with_spot.csv"))
        csv_files.sort()  # 按文件名排序
        
        self.stats['total_files'] = len(csv_files)
        
        print(f"📁 找到 {len(csv_files)} 个输入文件")
        return csv_files
    
    def generate_output_filename(self, input_file: Path) -> Path:
        """生成输出文件名"""
        # 将 _with_spot.csv 替换为 _with_iv_greeks.csv
        base_name = input_file.stem.replace('_with_spot', '_with_iv_greeks')
        return self.output_dir / f"{base_name}.csv"
    
    def process_single_file(self, input_file: Path, show_progress: bool = True) -> Dict:
        """
        处理单个CSV文件
        
        Args:
            input_file: 输入文件路径
            show_progress: 是否显示进度条
            
        Returns:
            Dict: 处理结果统计
        """
        output_file = self.generate_output_filename(input_file)
        
        try:
            # 读取原始数据
            df = pd.read_csv(input_file)
            
            if len(df) == 0:
                return {'success': False, 'error': 'empty_file', 'rows': 0}
            
            # 检查必需的列
            required_cols = ['symbol', 'time', 'open', 'spot_open']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                return {'success': False, 'error': f'missing_columns: {missing_cols}', 'rows': len(df)}
            
            # 为每行计算期权指标
            results = []
            
            if show_progress:
                iterator = tqdm(df.iterrows(), total=len(df), 
                              desc=f"处理 {input_file.name}", 
                              leave=False)
            else:
                iterator = df.iterrows()
            
            for idx, row in iterator:
                try:
                    result = self.calculator.process_dataframe_row(row)
                    results.append(result)
                except Exception as e:
                    # 创建错误结果
                    error_result = self.calculator._create_error_result(
                        row.to_dict(), {}, 0.0, f"行处理错误: {str(e)}"
                    )
                    results.append(error_result)
            
            # 转换结果为DataFrame
            results_df = pd.DataFrame(results)
            
            # 合并原始数据和计算结果
            # 只保留计算结果中的新列，避免重复
            original_cols = df.columns.tolist()
            new_cols = [col for col in results_df.columns if col not in original_cols]
            
            # 重新组织列顺序：原始列 + 新计算列
            final_df = pd.concat([df, results_df[new_cols]], axis=1)
            
            # 保存结果
            final_df.to_csv(output_file, index=False)
            
            # 统计信息
            successful_calcs = results_df['calculation_success'].sum()
            failed_calcs = len(results_df) - successful_calcs
            
            return {
                'success': True,
                'rows': len(df),
                'successful_calculations': successful_calcs,
                'failed_calculations': failed_calcs,
                'output_file': str(output_file)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'rows': 0
            }
    
    def process_all_files(self, 
                         max_files: Optional[int] = None,
                         start_from: int = 0,
                         show_file_progress: bool = True) -> Dict:
        """
        处理所有文件
        
        Args:
            max_files: 最大处理文件数（用于测试）
            start_from: 从第几个文件开始处理
            show_file_progress: 是否显示文件级进度
            
        Returns:
            Dict: 总体处理统计
        """
        # 获取文件列表
        input_files = self.get_input_files()
        
        if start_from > 0:
            input_files = input_files[start_from:]
            print(f"从第 {start_from + 1} 个文件开始处理")
        
        if max_files:
            input_files = input_files[:max_files]
            print(f"限制处理 {max_files} 个文件")
        
        print(f"📊 准备处理 {len(input_files)} 个文件")
        print(f"📁 输出目录: {self.output_dir}")
        
        # 开始处理
        self.stats['start_time'] = datetime.now()
        print(f"🚀 开始批量处理 - {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 处理每个文件
        if show_file_progress:
            file_iterator = tqdm(input_files, desc="处理文件")
        else:
            file_iterator = input_files
        
        for i, input_file in enumerate(file_iterator):
            current_time = datetime.now()
            elapsed = (current_time - self.stats['start_time']).total_seconds()
            
            if not show_file_progress:
                print(f"\n[{i+1:3d}/{len(input_files)}] {input_file.name}")
                print(f"  已用时间: {elapsed/60:.1f} 分钟")
            
            # 检查输出文件是否已存在
            output_file = self.generate_output_filename(input_file)
            if output_file.exists():
                if not show_file_progress:
                    print(f"  ⏭️  跳过（输出文件已存在）")
                continue
            
            # 处理文件
            result = self.process_single_file(input_file, show_progress=not show_file_progress)
            
            if result['success']:
                self.stats['processed_files'] += 1
                self.stats['total_rows'] += result['rows']
                self.stats['successful_calculations'] += result['successful_calculations']
                self.stats['failed_calculations'] += result['failed_calculations']
                
                if not show_file_progress:
                    success_rate = (result['successful_calculations'] / result['rows']) * 100
                    print(f"  ✅ 成功 - {result['rows']:,} 行, 成功率: {success_rate:.1f}%")
            else:
                self.stats['failed_files'] += 1
                self.stats['failed_file_list'].append({
                    'file': str(input_file),
                    'error': result['error']
                })
                
                if not show_file_progress:
                    print(f"  ❌ 失败 - {result['error']}")
            
            # 每10个文件显示一次汇总
            if not show_file_progress and (i + 1) % 10 == 0:
                self._print_interim_stats(i + 1, len(input_files), elapsed)
        
        # 结束处理
        self.stats['end_time'] = datetime.now()
        total_elapsed = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        if self.stats['total_rows'] > 0:
            self.stats['processing_rate'] = self.stats['total_rows'] / total_elapsed
        
        # 显示最终结果
        self._print_final_summary(total_elapsed)
        
        # 保存统计信息
        self._save_processing_stats(total_elapsed)
        
        return self.stats
    
    def _print_interim_stats(self, current_file: int, total_files: int, elapsed: float):
        """打印中间统计信息"""
        success_rate = (self.stats['processed_files'] / current_file) * 100 if current_file > 0 else 0
        avg_time_per_file = elapsed / current_file if current_file > 0 else 0
        remaining_files = total_files - current_file
        eta_seconds = remaining_files * avg_time_per_file
        
        print(f"\n📊 进度汇总 [{current_file}/{total_files}]:")
        print(f"  文件成功率: {success_rate:.1f}%")
        print(f"  平均耗时: {avg_time_per_file:.1f}秒/文件")
        print(f"  预计剩余: {eta_seconds/60:.0f}分钟")
        print(f"  已处理行数: {self.stats['total_rows']:,}")
    
    def _print_final_summary(self, total_elapsed: float):
        """打印最终汇总"""
        print("\n" + "=" * 60)
        print("🎉 批量处理完成!")
        print("=" * 60)
        
        # 基本统计
        print(f"⏰ 总用时: {total_elapsed/3600:.1f} 小时 ({total_elapsed/60:.0f} 分钟)")
        print(f"📁 输出目录: {self.output_dir}")
        print(f"📊 文件处理统计:")
        print(f"  总文件数: {self.stats['total_files']}")
        print(f"  成功处理: {self.stats['processed_files']}")
        print(f"  处理失败: {self.stats['failed_files']}")
        
        if self.stats['total_files'] > 0:
            file_success_rate = (self.stats['processed_files'] / self.stats['total_files']) * 100
            print(f"  文件成功率: {file_success_rate:.1f}%")
        
        # 数据统计
        if self.stats['total_rows'] > 0:
            calc_success_rate = (self.stats['successful_calculations'] / self.stats['total_rows']) * 100
            print(f"\n📈 数据计算统计:")
            print(f"  总处理行数: {self.stats['total_rows']:,}")
            print(f"  成功计算: {self.stats['successful_calculations']:,}")
            print(f"  计算失败: {self.stats['failed_calculations']:,}")
            print(f"  计算成功率: {calc_success_rate:.1f}%")
            print(f"  处理速度: {self.stats['processing_rate']:,.0f} 行/秒")
        
        # 失败文件
        if self.stats['failed_file_list']:
            print(f"\n❌ 失败文件 ({len(self.stats['failed_file_list'])} 个):")
            for failed in self.stats['failed_file_list'][:5]:
                print(f"  - {Path(failed['file']).name}: {failed['error']}")
            if len(self.stats['failed_file_list']) > 5:
                print(f"  ... 还有 {len(self.stats['failed_file_list']) - 5} 个")
        
        print(f"\n🎯 所有结果已保存到: {self.output_dir}")
        print("✅ 批量处理任务完成!")
    
    def _save_processing_stats(self, total_elapsed: float):
        """保存处理统计到文件"""
        stats_file = self.output_dir / "processing_statistics.json"
        
        # 准备JSON兼容的统计数据
        json_stats = {
            'processing_summary': {
                'start_time': self.stats['start_time'].isoformat(),
                'end_time': self.stats['end_time'].isoformat(),
                'total_elapsed_seconds': total_elapsed,
                'total_elapsed_hours': total_elapsed / 3600
            },
            'file_statistics': {
                'total_files': self.stats['total_files'],
                'processed_files': self.stats['processed_files'],
                'failed_files': self.stats['failed_files'],
                'file_success_rate': (self.stats['processed_files'] / self.stats['total_files'] * 100) if self.stats['total_files'] > 0 else 0
            },
            'data_statistics': {
                'total_rows': self.stats['total_rows'],
                'successful_calculations': self.stats['successful_calculations'],
                'failed_calculations': self.stats['failed_calculations'],
                'calculation_success_rate': (self.stats['successful_calculations'] / self.stats['total_rows'] * 100) if self.stats['total_rows'] > 0 else 0,
                'processing_rate_rows_per_second': self.stats['processing_rate']
            },
            'failed_files': self.stats['failed_file_list'],
            'output_directory': str(self.output_dir)
        }
        
        try:
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(json_stats, f, indent=2, ensure_ascii=False)
            print(f"📊 处理统计已保存: {stats_file}")
        except Exception as e:
            print(f"⚠️  统计保存失败: {e}")

def demo():
    """演示函数"""
    print("🎯 批量处理器演示")
    print("=" * 50)
    
    # 配置
    input_dir = "/home/ubuntu/options_trading/data/okx_data_processor/okx_options/options_with_spot"
    output_dir = "./demo_output"
    
    # 创建处理器
    processor = BatchProcessor(
        input_dir=input_dir,
        output_dir=output_dir
    )
    
    # 演示：只处理前3个文件
    print("🚀 演示模式：只处理前3个文件")
    result = processor.process_all_files(max_files=3)
    
    print(f"\n📊 演示结果:")
    print(f"  处理文件: {result['processed_files']}")
    print(f"  处理行数: {result['total_rows']:,}")
    print(f"  计算成功: {result['successful_calculations']:,}")

if __name__ == "__main__":
    demo()
