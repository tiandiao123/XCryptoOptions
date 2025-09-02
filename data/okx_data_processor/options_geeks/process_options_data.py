#!/usr/bin/env python3
"""
期权数据处理主程序
一键处理options_with_spot目录下的所有CSV文件
为每行期权数据计算IV、Delta、Gamma、Vega和历史利率
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime

# 导入我们的批量处理器
from batch_processor import BatchProcessor

def validate_directories(input_dir: str, output_dir: str) -> tuple:
    """
    验证输入和输出目录
    
    Args:
        input_dir: 输入目录路径
        output_dir: 输出目录路径
        
    Returns:
        tuple: (input_path, output_path) 或 (None, None) 如果验证失败
    """
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        return None, None
    
    if not input_path.is_dir():
        print(f"❌ 输入路径不是目录: {input_dir}")
        return None, None
    
    # 检查输入目录是否包含期权数据文件
    csv_files = list(input_path.glob("okex-options_quotes_*_OPTIONS_30min_klines_with_spot.csv"))
    if not csv_files:
        print(f"❌ 输入目录中没有找到期权数据文件")
        print(f"   期望的文件格式: okex-options_quotes_*_OPTIONS_30min_klines_with_spot.csv")
        return None, None
    
    print(f"✅ 输入目录验证通过: {input_dir}")
    print(f"   找到 {len(csv_files)} 个期权数据文件")
    
    # 创建输出目录
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ 输出目录就绪: {output_dir}")
    except Exception as e:
        print(f"❌ 无法创建输出目录: {e}")
        return None, None
    
    return input_path, output_path

def print_banner():
    """打印程序横幅"""
    print("=" * 80)
    print("🚀 OKX期权数据处理系统")
    print("   计算隐含波动率(IV)、希腊字母(Delta/Gamma/Vega)和历史利率")
    print("=" * 80)

def print_system_info():
    """打印系统信息"""
    print(f"📊 系统信息:")
    print(f"   Python版本: {sys.version.split()[0]}")
    print(f"   运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   工作目录: {os.getcwd()}")

def confirm_processing(total_files: int, estimated_time: float = None):
    """
    确认是否开始处理
    
    Args:
        total_files: 总文件数
        estimated_time: 估计处理时间（小时）
    """
    print(f"\n🎯 处理计划:")
    print(f"   总文件数: {total_files:,}")
    
    if estimated_time:
        print(f"   估计耗时: {estimated_time:.1f} 小时")
    
    print(f"\n⚠️  注意事项:")
    print(f"   - 处理过程可能需要较长时间")
    print(f"   - 请确保有足够的磁盘空间")
    print(f"   - 处理过程中可以按 Ctrl+C 中断")
    
    while True:
        choice = input(f"\n确认开始处理? (y/n): ").strip().lower()
        if choice in ['y', 'yes']:
            return True
        elif choice in ['n', 'no']:
            return False
        else:
            print("请输入 y 或 n")

def estimate_processing_time(total_files: int) -> float:
    """
    估计处理时间
    
    Args:
        total_files: 总文件数
        
    Returns:
        float: 估计时间（小时）
    """
    # 基于经验数据的粗略估计
    # 假设每个文件平均18k行，每行0.01秒处理时间
    avg_rows_per_file = 18000
    seconds_per_row = 0.01
    
    total_estimated_seconds = total_files * avg_rows_per_file * seconds_per_row
    return total_estimated_seconds / 3600.0

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="处理OKX期权数据，计算IV和希腊字母",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--input-dir",
        default="/home/ubuntu/options_trading/data/okx_data_processor/okx_options/options_with_spot",
        help="输入目录路径（包含options_with_spot文件）\n默认: %(default)s"
    )
    
    parser.add_argument(
        "--output-dir", 
        default="./options_with_iv_greeks",
        help="输出目录路径\n默认: %(default)s"
    )
    
    parser.add_argument(
        "--rate-cache-dir",
        default="./rate_cache", 
        help="利率数据缓存目录\n默认: %(default)s"
    )
    
    parser.add_argument(
        "--max-files",
        type=int,
        help="限制处理的最大文件数（用于测试）"
    )
    
    parser.add_argument(
        "--start-from",
        type=int,
        default=0,
        help="从第几个文件开始处理（用于续传）\n默认: %(default)s"
    )
    
    parser.add_argument(
        "--force-refresh-rates",
        action="store_true",
        help="强制刷新历史利率数据"
    )
    
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="跳过确认，直接开始处理"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true", 
        help="静默模式，减少输出信息"
    )
    
    args = parser.parse_args()
    
    # 打印横幅和系统信息
    if not args.quiet:
        print_banner()
        print_system_info()
    
    # 验证目录
    print(f"\n📁 验证输入输出目录...")
    input_path, output_path = validate_directories(args.input_dir, args.output_dir)
    
    if not input_path or not output_path:
        print(f"\n❌ 目录验证失败，程序退出")
        sys.exit(1)
    
    # 检查利率缓存
    if args.force_refresh_rates:
        print(f"🔄 将强制刷新历史利率数据")
    
    try:
        # 创建批量处理器
        print(f"\n🚀 初始化批量处理器...")
        processor = BatchProcessor(
            input_dir=str(input_path),
            output_dir=str(output_path),
            rate_cache_dir=args.rate_cache_dir
        )
        
        # 如果需要刷新利率数据
        if args.force_refresh_rates:
            print(f"🔄 刷新历史利率数据...")
            processor.calculator.rate_fetcher.load_or_fetch_rates(force_refresh=True)
        
        # 获取文件列表
        input_files = processor.get_input_files()
        
        if args.start_from > 0:
            input_files = input_files[args.start_from:]
        
        if args.max_files:
            input_files = input_files[:args.max_files]
        
        total_files = len(input_files)
        
        if total_files == 0:
            print(f"❌ 没有文件需要处理")
            sys.exit(1)
        
        # 估计处理时间
        estimated_time = estimate_processing_time(total_files)
        
        # 确认处理
        if not args.yes and not args.quiet:
            if not confirm_processing(total_files, estimated_time):
                print(f"\n❌ 用户取消处理")
                sys.exit(0)
        
        # 开始处理
        print(f"\n🚀 开始批量处理...")
        result = processor.process_all_files(
            max_files=args.max_files,
            start_from=args.start_from,
            show_file_progress=args.quiet
        )
        
        # 显示最终结果
        if not args.quiet:
            print(f"\n🎉 处理完成!")
            
            if result['total_rows'] > 0:
                calc_success_rate = (result['successful_calculations'] / result['total_rows']) * 100
                print(f"📊 整体成功率: {calc_success_rate:.1f}%")
            
            print(f"📁 结果保存在: {output_path}")
        
        # 返回成功状态
        sys.exit(0)
        
    except KeyboardInterrupt:
        print(f"\n\n❌ 用户中断处理 (Ctrl+C)")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ 处理过程中发生错误: {e}")
        if not args.quiet:
            import traceback
            print(f"\n详细错误信息:")
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
