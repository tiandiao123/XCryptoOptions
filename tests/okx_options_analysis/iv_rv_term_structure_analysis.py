# -*- coding: utf-8 -*-
"""
IV vs RV Term Structure Analysis
分析短期IV > 长期IV时，IV < RV 和 IV > RV 的市场情况占比

结合 vol_tracker 进行实时波动率计算
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import os
import sys
from typing import Dict, List, Tuple, Optional
from tqdm import tqdm

# 导入自定义模块
sys.path.append('/home/ubuntu/options_trading')
from qtrade.data_loader import ATMOptionsIterator
from qtrade.simulate_tarde.vol_tracker.vol_tracker import VolTracker

plt.rcParams['font.size'] = 12
plt.rcParams['figure.figsize'] = (12, 8)
sns.set_style("whitegrid")

class IVRVTermStructureAnalyzer:
    """
    IV vs RV Term Structure 分析器
    
    分析在短期IV > 长期IV的情况下：
    - IV < RV 的占比
    - IV > RV 的占比
    - 不同期限结构的分布
    """
    
    def __init__(self, 
                 data_folder: str,
                 output_folder: str = 'iv_rv_term_structure_analysis'):
        """
        初始化分析器
        
        Args:
            data_folder: 数据文件夹路径
            output_folder: 输出文件夹路径
        """
        self.data_folder = data_folder
        self.output_folder = output_folder
        
        # 创建输出文件夹
        os.makedirs(self.output_folder, exist_ok=True)
        
        # 初始化数据加载器
        self.iterator = ATMOptionsIterator(data_folder, silent_mode=True)
        
        # 初始化波动率跟踪器
        self.vol_tracker = VolTracker(
            window_size=96,      # 2天数据
            ewma_lambda=0.94,    # RiskMetrics标准
            min_periods=30,      # 最小30个点开始计算
            refit_frequency=48   # 每天重拟合
        )
        
        # 存储分析结果
        self.analysis_data = []
        
        # 期限定义
        self.term_configs = [
            {
                'name': '7D_vs_30D',
                'short_range': (5, 10),     # 7天左右
                'long_range': (25, 35)      # 30天左右
            },
            {
                'name': '14D_vs_60D', 
                'short_range': (12, 18),    # 14天左右
                'long_range': (55, 65)      # 60天左右
            },
            {
                'name': '30D_vs_90D',
                'short_range': (25, 35),    # 30天左右
                'long_range': (85, 95)      # 90天左右
            }
        ]
        
        print(f"✅ IV-RV Term Structure Analyzer 初始化完成")
        print(f"📊 数据范围: {self.iterator.dates[0]} 到 {self.iterator.dates[-1]}")
        print(f"📁 输出文件夹: {self.output_folder}")
    
    def analyze_single_timepoint(self, 
                                data_point: Dict, 
                                realized_vol: float) -> Optional[Dict]:
        """
        分析单个时间点的IV vs RV情况
        
        Args:
            data_point: 时间点数据
            realized_vol: 实现波动率
            
        Returns:
            分析结果字典或None
        """
        timestamp = data_point['time']
        spot_price = data_point['spot_price']
        atm_options = data_point['atm_options']
        
        if len(atm_options) == 0 or realized_vol is None:
            return None
        
        results = []
        
        # 对每个期限配置进行分析
        for config in self.term_configs:
            # 筛选短期和长期期权
            short_options = [
                opt for opt in atm_options 
                if config['short_range'][0] <= opt['days_to_expiry'] <= config['short_range'][1]
            ]
            
            long_options = [
                opt for opt in atm_options 
                if config['long_range'][0] <= opt['days_to_expiry'] <= config['long_range'][1]
            ]
            
            if not short_options or not long_options:
                continue
            
            # 计算平均IV
            short_iv_avg = np.mean([opt['iv'] for opt in short_options])
            long_iv_avg = np.mean([opt['iv'] for opt in long_options])
            
            # 检查是否为期限结构倒挂 (短期IV > 长期IV)
            if short_iv_avg > long_iv_avg:
                # 计算IV相对于RV的情况
                short_iv_vs_rv = "IV > RV" if short_iv_avg > realized_vol else "IV < RV"
                long_iv_vs_rv = "IV > RV" if long_iv_avg > realized_vol else "IV < RV"
                
                result = {
                    'timestamp': timestamp,
                    'date': data_point['date'],
                    'spot_price': spot_price,
                    'term_structure': config['name'],
                    'short_iv': short_iv_avg,
                    'long_iv': long_iv_avg,
                    'realized_vol': realized_vol,
                    'iv_spread': short_iv_avg - long_iv_avg,
                    'short_iv_vs_rv': short_iv_vs_rv,
                    'long_iv_vs_rv': long_iv_vs_rv,
                    'short_iv_ratio': short_iv_avg / realized_vol,
                    'long_iv_ratio': long_iv_avg / realized_vol,
                    'is_inverted': True,  # 期限结构倒挂
                    'short_options_count': len(short_options),
                    'long_options_count': len(long_options)
                }
                
                results.append(result)
        
        return results if results else None
    
    def run_analysis(self, 
                     start_date=None, 
                     end_date=None,
                     sample_frequency: int = 1) -> pd.DataFrame:
        """
        运行完整的IV vs RV分析
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            sample_frequency: 采样频率 (1=每个时间点, 2=每2个时间点)
            
        Returns:
            分析结果DataFrame
        """
        print("🚀 开始 IV vs RV Term Structure 分析...")
        
        if start_date is None:
            start_date = self.iterator.dates[0]
        if end_date is None:
            end_date = self.iterator.dates[-1]
        
        print(f"📅 分析期间: {start_date} 到 {end_date}")
        
        count = 0
        inverted_count = 0
        
        # 遍历数据
        for i, data_point in enumerate(tqdm(
            self.iterator.iterate_date_range(start_date, end_date),
            desc="Processing Time Points"
        )):
            # 采样控制
            if i % sample_frequency != 0:
                continue
            
            timestamp = data_point['time']
            spot_price = data_point['spot_price']
            
            # 更新波动率跟踪器
            vol_result = self.vol_tracker.add_price(spot_price, timestamp)
            
            # 获取实现波动率
            realized_vol = vol_result.get('ewma_vol_annualized')
            
            if realized_vol is None:
                continue
            
            # 分析当前时间点
            timepoint_results = self.analyze_single_timepoint(data_point, realized_vol)
            
            if timepoint_results:
                self.analysis_data.extend(timepoint_results)
                inverted_count += 1
            
            count += 1
            
            # 定期显示进度
            if count % 1000 == 0:
                print(f"📊 已处理 {count} 个时间点，发现 {inverted_count} 个倒挂情况")
        
        # 转换为DataFrame
        df_results = pd.DataFrame(self.analysis_data)
        
        print(f"✅ 分析完成！")
        print(f"📈 总时间点: {count}")
        print(f"📊 倒挂情况: {inverted_count}")
        print(f"📋 有效分析记录: {len(df_results)}")
        
        return df_results
    
    def generate_statistics(self, df: pd.DataFrame) -> Dict:
        """生成统计分析"""
        if len(df) == 0:
            return {}
        
        stats = {}
        
        # 总体统计
        stats['total_records'] = len(df)
        stats['unique_dates'] = df['date'].nunique()
        stats['date_range'] = (df['date'].min(), df['date'].max())
        
        # 按期限结构分组统计
        for term_name in df['term_structure'].unique():
            term_data = df[df['term_structure'] == term_name]
            
            # IV vs RV 占比统计
            short_iv_vs_rv_counts = term_data['short_iv_vs_rv'].value_counts()
            long_iv_vs_rv_counts = term_data['long_iv_vs_rv'].value_counts()
            
            stats[term_name] = {
                'total_count': len(term_data),
                'short_iv_vs_rv': {
                    'IV > RV': short_iv_vs_rv_counts.get('IV > RV', 0),
                    'IV < RV': short_iv_vs_rv_counts.get('IV < RV', 0),
                    'IV > RV %': short_iv_vs_rv_counts.get('IV > RV', 0) / len(term_data) * 100,
                    'IV < RV %': short_iv_vs_rv_counts.get('IV < RV', 0) / len(term_data) * 100
                },
                'long_iv_vs_rv': {
                    'IV > RV': long_iv_vs_rv_counts.get('IV > RV', 0),
                    'IV < RV': long_iv_vs_rv_counts.get('IV < RV', 0),
                    'IV > RV %': long_iv_vs_rv_counts.get('IV > RV', 0) / len(term_data) * 100,
                    'IV < RV %': long_iv_vs_rv_counts.get('IV < RV', 0) / len(term_data) * 100
                },
                'avg_metrics': {
                    'short_iv': term_data['short_iv'].mean(),
                    'long_iv': term_data['long_iv'].mean(),
                    'realized_vol': term_data['realized_vol'].mean(),
                    'iv_spread': term_data['iv_spread'].mean(),
                    'short_iv_ratio': term_data['short_iv_ratio'].mean(),
                    'long_iv_ratio': term_data['long_iv_ratio'].mean()
                }
            }
        
        return stats
    
    def create_visualizations(self, df: pd.DataFrame, stats: Dict):
        """创建可视化图表"""
        if len(df) == 0:
            return
        
        # 1. IV vs RV 占比饼图
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('IV vs RV Distribution in Term Structure Inversion', fontsize=16, fontweight='bold')
        
        for i, term_name in enumerate(df['term_structure'].unique()):
            # Short-term IV vs RV
            ax1 = axes[0, i]
            term_stats = stats[term_name]['short_iv_vs_rv']
            sizes = [term_stats['IV > RV'], term_stats['IV < RV']]
            labels = [f"IV > RV\n({term_stats['IV > RV %']:.1f}%)", 
                     f"IV < RV\n({term_stats['IV < RV %']:.1f}%)"]
            colors = ['#ff7f7f', '#7fbfff']
            
            ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.0f', startangle=90)
            ax1.set_title(f'{term_name}\nShort-term IV vs RV', fontweight='bold')
            
            # Long-term IV vs RV
            ax2 = axes[1, i]
            term_stats = stats[term_name]['long_iv_vs_rv']
            sizes = [term_stats['IV > RV'], term_stats['IV < RV']]
            labels = [f"IV > RV\n({term_stats['IV > RV %']:.1f}%)", 
                     f"IV < RV\n({term_stats['IV < RV %']:.1f}%)"]
            
            ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.0f', startangle=90)
            ax2.set_title(f'{term_name}\nLong-term IV vs RV', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_folder, 'iv_vs_rv_distribution.png'), 
                   dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. 时间序列图
        fig, axes = plt.subplots(3, 1, figsize=(15, 12))
        fig.suptitle('IV vs RV Time Series Analysis', fontsize=16, fontweight='bold')
        
        for i, term_name in enumerate(df['term_structure'].unique()):
            term_data = df[df['term_structure'] == term_name].copy()
            term_data = term_data.sort_values('timestamp')
            
            ax = axes[i]
            
            # 绘制IV和RV
            ax.plot(term_data['timestamp'], term_data['short_iv'], 
                   label='Short-term IV', color='red', alpha=0.7)
            ax.plot(term_data['timestamp'], term_data['long_iv'], 
                   label='Long-term IV', color='blue', alpha=0.7)
            ax.plot(term_data['timestamp'], term_data['realized_vol'], 
                   label='Realized Vol (EWMA)', color='green', alpha=0.8, linewidth=2)
            
            ax.set_title(f'{term_name} - IV vs RV Over Time', fontweight='bold')
            ax.set_ylabel('Volatility')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 格式化x轴
            if len(term_data) > 100:
                ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_folder, 'iv_rv_timeseries.png'), 
                   dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. 散点图：IV Ratio vs Spot Price
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        fig.suptitle('IV/RV Ratio vs Spot Price', fontsize=16, fontweight='bold')
        
        for i, term_name in enumerate(df['term_structure'].unique()):
            term_data = df[df['term_structure'] == term_name]
            
            ax = axes[i]
            
            # 短期IV/RV ratio
            scatter1 = ax.scatter(term_data['spot_price'], term_data['short_iv_ratio'], 
                                 c=term_data['short_iv_ratio'], cmap='RdYlBu_r', 
                                 alpha=0.6, s=20, label='Short-term IV/RV')
            
            ax.axhline(y=1, color='black', linestyle='--', alpha=0.7, label='IV = RV')
            ax.set_xlabel('Spot Price ($)')
            ax.set_ylabel('IV/RV Ratio')
            ax.set_title(f'{term_name}')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 添加colorbar
            plt.colorbar(scatter1, ax=ax, label='IV/RV Ratio')
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_folder, 'iv_rv_ratio_scatter.png'), 
                   dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📊 可视化图表已保存到: {self.output_folder}")
    
    def save_results(self, df: pd.DataFrame, stats: Dict):
        """保存分析结果"""
        # 保存详细数据
        csv_path = os.path.join(self.output_folder, 'iv_rv_analysis_detailed.csv')
        df.to_csv(csv_path, index=False)
        
        # 保存统计摘要
        summary_path = os.path.join(self.output_folder, 'analysis_summary.txt')
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("IV vs RV Term Structure Analysis Summary\n")
            f.write("="*50 + "\n\n")
            
            f.write(f"Analysis Period: {stats['date_range'][0]} to {stats['date_range'][1]}\n")
            f.write(f"Total Records: {stats['total_records']:,}\n")
            f.write(f"Unique Dates: {stats['unique_dates']:,}\n\n")
            
            for term_name in df['term_structure'].unique():
                term_stats = stats[term_name]
                f.write(f"\n{term_name} Analysis:\n")
                f.write("-" * 30 + "\n")
                f.write(f"Total Inverted Cases: {term_stats['total_count']:,}\n\n")
                
                f.write("Short-term IV vs RV:\n")
                f.write(f"  IV > RV: {term_stats['short_iv_vs_rv']['IV > RV']:,} ({term_stats['short_iv_vs_rv']['IV > RV %']:.1f}%)\n")
                f.write(f"  IV < RV: {term_stats['short_iv_vs_rv']['IV < RV']:,} ({term_stats['short_iv_vs_rv']['IV < RV %']:.1f}%)\n\n")
                
                f.write("Long-term IV vs RV:\n")
                f.write(f"  IV > RV: {term_stats['long_iv_vs_rv']['IV > RV']:,} ({term_stats['long_iv_vs_rv']['IV > RV %']:.1f}%)\n")
                f.write(f"  IV < RV: {term_stats['long_iv_vs_rv']['IV < RV']:,} ({term_stats['long_iv_vs_rv']['IV < RV %']:.1f}%)\n\n")
                
                avg_metrics = term_stats['avg_metrics']
                f.write("Average Metrics:\n")
                f.write(f"  Short-term IV: {avg_metrics['short_iv']:.2%}\n")
                f.write(f"  Long-term IV: {avg_metrics['long_iv']:.2%}\n")
                f.write(f"  Realized Vol: {avg_metrics['realized_vol']:.2%}\n")
                f.write(f"  IV Spread: {avg_metrics['iv_spread']:.2%}\n")
                f.write(f"  Short IV/RV Ratio: {avg_metrics['short_iv_ratio']:.2f}\n")
                f.write(f"  Long IV/RV Ratio: {avg_metrics['long_iv_ratio']:.2f}\n")
        
        print(f"📁 分析结果已保存到:")
        print(f"   详细数据: {csv_path}")
        print(f"   统计摘要: {summary_path}")
    
    def run_full_analysis(self, 
                         start_date=None, 
                         end_date=None,
                         sample_frequency: int = 2):
        """运行完整分析流程"""
        print("🎯 开始完整的 IV vs RV Term Structure 分析")
        print("="*60)
        
        # 1. 运行数据分析
        df_results = self.run_analysis(start_date, end_date, sample_frequency)
        
        if len(df_results) == 0:
            print("❌ 没有找到期限结构倒挂的情况")
            return
        
        # 2. 生成统计
        stats = self.generate_statistics(df_results)
        
        # 3. 创建可视化
        self.create_visualizations(df_results, stats)
        
        # 4. 保存结果
        self.save_results(df_results, stats)
        
        # 5. 打印关键结果
        print("\n🎯 关键发现:")
        print("="*40)
        
        for term_name in df_results['term_structure'].unique():
            term_stats = stats[term_name]
            print(f"\n📊 {term_name}:")
            print(f"   倒挂案例数: {term_stats['total_count']:,}")
            print(f"   短期 IV > RV: {term_stats['short_iv_vs_rv']['IV > RV %']:.1f}%")
            print(f"   短期 IV < RV: {term_stats['short_iv_vs_rv']['IV < RV %']:.1f}%")
            print(f"   长期 IV > RV: {term_stats['long_iv_vs_rv']['IV > RV %']:.1f}%")
            print(f"   长期 IV < RV: {term_stats['long_iv_vs_rv']['IV < RV %']:.1f}%")
        
        print(f"\n✅ 完整分析完成！结果保存在: {self.output_folder}")


if __name__ == "__main__":
    print("🚀 IV vs RV Term Structure Analysis")
    print("="*50)
    
    # 配置参数
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    output_folder = '/home/ubuntu/options_trading/qtrade/okx_options_analysis/iv_rv_term_structure_analysis'
    
    # 创建分析器
    analyzer = IVRVTermStructureAnalyzer(data_folder, output_folder)
    
    # 选择分析时间范围 (可以调整)
    start_date = analyzer.iterator.dates[-365]  # 最近一年
    end_date = analyzer.iterator.dates[-1]
    
    print(f"📅 分析时间范围: {start_date} 到 {end_date}")
    
    # 确认是否继续
    choice = input("\n是否开始分析? (y/n): ").strip().lower()
    if choice in ['y', 'yes']:
        # 运行完整分析
        analyzer.run_full_analysis(
            start_date=start_date,
            end_date=end_date,
            sample_frequency=2  # 每2个时间点采样一次，提高速度
        )
    else:
        print("❌ 分析已取消")