#!/usr/bin/env python3
"""
OKX期权期限结构Richness分析
基于加权组合的短期和长期IV计算
short_term_iv = 0.5 * atm7_iv + 0.5 * atm14_iv
long_term_iv = 0.5 * atm60_iv + 0.5 * atm90_iv
richness = short_term_iv / long_term_iv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os
from datetime import datetime
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# 设置图表样式
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")

class TermStructureRichnessAnalyzer:
    def __init__(self, data_dir, output_dir):
        """
        初始化期限结构Richness分析器
        
        Args:
            data_dir: 输入数据目录
            output_dir: 输出结果目录
        """
        self.data_dir = data_dir
        self.output_dir = output_dir
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 期限配置
        self.term_configs = {
            '7d': {'min_days': 5, 'max_days': 9, 'target_days': 7},
            '14d': {'min_days': 12, 'max_days': 16, 'target_days': 14},
            '60d': {'min_days': 55, 'max_days': 65, 'target_days': 60},
            '90d': {'min_days': 85, 'max_days': 95, 'target_days': 90}
        }
        
        # 统计信息
        self.stats = {
            'total_files_processed': 0,
            'total_atm_data': 0,
            'richness_data_points': 0,
            'date_range': [None, None],
            'term_data_counts': {term: 0 for term in self.term_configs.keys()},
            'richness_values': []
        }
    
    def process_single_file(self, csv_file):
        """
        处理单个CSV文件，提取各期限的ATM期权数据
        """
        try:
            df = pd.read_csv(csv_file)
            
            # 基本数据清洗
            df = df[
                (df['calculation_success'] == True) &
                (df['days_to_expiry'] >= 2.0) &  # 排除当天交割
                (df['iv'] > 1e-05) & (df['iv'] < 4.99) &
                (df['error'].isna() | (df['error'] == ''))
            ].copy()
            
            if len(df) == 0:
                return None
            
            # 计算moneyness
            df['moneyness'] = df['spot_open'] / df['strike_price']
            
            # 筛选ATM期权
            atm_df = df[
                (df['moneyness'] >= 0.95) & 
                (df['moneyness'] <= 1.05)
            ].copy()
            
            if len(atm_df) == 0:
                return None
            
            # 按期限分类
            atm_df['term_category'] = None
            for term_name, config in self.term_configs.items():
                mask = (atm_df['days_to_expiry'] >= config['min_days']) & (atm_df['days_to_expiry'] <= config['max_days'])
                atm_df.loc[mask, 'term_category'] = term_name
            
            # 只保留有期限分类的数据
            classified_df = atm_df[atm_df['term_category'].notna()].copy()
            
            if len(classified_df) == 0:
                return None
            
            # 转换时间格式
            classified_df['datetime'] = pd.to_datetime(classified_df['time'])
            
            # 按时间和期限分组，计算IV均值
            time_series = classified_df.groupby(['datetime', 'term_category']).agg({
                'iv': ['mean', 'count'],
                'spot_open': 'first',
                'moneyness': 'mean'
            }).reset_index()
            
            # 平整列名
            time_series.columns = ['datetime', 'term_category', 'iv_mean', 'iv_count', 'spot_price', 'moneyness_mean']
            
            # 只保留数据量足够的时间点
            time_series = time_series[time_series['iv_count'] >= 2]
            
            return time_series
            
        except Exception as e:
            print(f"处理文件失败: {os.path.basename(csv_file)} - {e}")
            return None
    
    def process_all_files(self, batch_size=100):
        """
        分批处理所有文件
        """
        print(f"🚀 开始期限结构Richness分析")
        print("="*60)
        
        # 获取所有CSV文件
        csv_files = glob.glob(os.path.join(self.data_dir, "*.csv"))
        csv_files.sort()
        
        print(f"📁 找到 {len(csv_files)} 个文件")
        print(f"📊 批次大小: {batch_size} 文件/批")
        
        total_batches = (len(csv_files) + batch_size - 1) // batch_size
        print(f"📈 总批次数: {total_batches}")
        
        all_time_series = []
        
        # 分批处理
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(csv_files))
            
            batch_files = csv_files[start_idx:end_idx]
            
            print(f"\n🔄 处理批次 {batch_num + 1}/{total_batches} ({len(batch_files)} 文件)")
            
            batch_results = []
            successful_files = 0
            
            for csv_file in tqdm(batch_files, desc=f"Batch {batch_num+1}"):
                result = self.process_single_file(csv_file)
                if result is not None:
                    batch_results.append(result)
                    successful_files += 1
                    self.stats['total_files_processed'] += 1
            
            print(f"  ✅ 成功处理: {successful_files}/{len(batch_files)} 文件")
            
            if batch_results:
                # 合并批次数据
                batch_df = pd.concat(batch_results, ignore_index=True)
                all_time_series.append(batch_df)
                
                self.stats['total_atm_data'] += len(batch_df)
                
                # 更新期限数据统计
                for term in self.term_configs.keys():
                    term_count = (batch_df['term_category'] == term).sum()
                    self.stats['term_data_counts'][term] += term_count
                
                print(f"  📊 批次ATM数据: {len(batch_df):,} 行")
                
                # 清理内存
                del batch_df, batch_results
        
        # 合并所有数据
        if all_time_series:
            print(f"\n🔄 合并所有时间序列数据...")
            combined_df = pd.concat(all_time_series, ignore_index=True)
            
            # 更新日期范围
            self.stats['date_range'][0] = combined_df['datetime'].min()
            self.stats['date_range'][1] = combined_df['datetime'].max()
            
            print(f"✅ 总计ATM数据: {len(combined_df):,} 行")
            print(f"📅 时间范围: {self.stats['date_range'][0].strftime('%Y-%m-%d')} 到 {self.stats['date_range'][1].strftime('%Y-%m-%d')}")
            
            return combined_df
        else:
            print("❌ 没有成功处理任何文件")
            return pd.DataFrame()
    
    def calculate_weighted_iv_and_richness(self, combined_df):
        """
        计算加权IV和Richness指标
        """
        print(f"\n📊 计算加权IV和Richness指标...")
        
        # 为每个时间点计算各期限的平均IV
        pivot_df = combined_df.pivot_table(
            index='datetime',
            columns='term_category', 
            values='iv_mean',
            aggfunc='mean'
        ).reset_index()
        
        # 检查所需期限的数据可用性
        required_terms = ['7d', '14d', '60d', '90d']
        available_terms = [col for col in pivot_df.columns if col in required_terms]
        missing_terms = [term for term in required_terms if term not in available_terms]
        
        print(f"📋 可用期限: {available_terms}")
        if missing_terms:
            print(f"⚠️  缺失期限: {missing_terms}")
        
        # 计算加权IV
        richness_df = pivot_df[['datetime']].copy()
        
        # 短期IV = 0.5 * 7天IV + 0.5 * 14天IV
        if '7d' in available_terms and '14d' in available_terms:
            richness_df['short_term_iv'] = 0.5 * pivot_df['7d'] + 0.5 * pivot_df['14d']
        elif '7d' in available_terms:
            richness_df['short_term_iv'] = pivot_df['7d']
            print("⚠️  只使用7天IV作为短期IV")
        elif '14d' in available_terms:
            richness_df['short_term_iv'] = pivot_df['14d']
            print("⚠️  只使用14天IV作为短期IV")
        else:
            print("❌ 缺少短期IV数据")
            return None
        
        # 长期IV = 0.5 * 60天IV + 0.5 * 90天IV
        if '60d' in available_terms and '90d' in available_terms:
            richness_df['long_term_iv'] = 0.5 * pivot_df['60d'] + 0.5 * pivot_df['90d']
        elif '60d' in available_terms:
            richness_df['long_term_iv'] = pivot_df['60d']
            print("⚠️  只使用60天IV作为长期IV")
        elif '90d' in available_terms:
            richness_df['long_term_iv'] = pivot_df['90d']
            print("⚠️  只使用90天IV作为长期IV")
        else:
            print("❌ 缺少长期IV数据")
            return None
        
        # 计算Richness = short_term_iv / long_term_iv
        richness_df['richness'] = richness_df['short_term_iv'] / richness_df['long_term_iv']
        
        # 过滤有效数据
        richness_df = richness_df.dropna(subset=['short_term_iv', 'long_term_iv', 'richness'])
        
        # 过滤异常值（richness在合理范围内）
        richness_df = richness_df[
            (richness_df['richness'] > 0.1) & 
            (richness_df['richness'] < 10.0)
        ]
        
        self.stats['richness_data_points'] = len(richness_df)
        self.stats['richness_values'] = richness_df['richness'].tolist()
        
        # 添加各期限的原始数据
        for term in available_terms:
            if term in pivot_df.columns:
                richness_df[f'{term}_iv'] = pivot_df[term]
        
        print(f"✅ 计算完成！")
        print(f"📊 有效Richness数据点: {len(richness_df):,}")
        print(f"📈 Richness范围: {richness_df['richness'].min():.3f} - {richness_df['richness'].max():.3f}")
        print(f"📊 平均Richness: {richness_df['richness'].mean():.3f}")
        
        return richness_df
    
    def create_individual_charts(self, richness_df):
        """
        创建单独的图表
        """
        print(f"\n🎨 创建单独的分析图表...")
        
        charts = {}
        
        # 图1: Richness时间序列
        fig1, ax1 = plt.subplots(figsize=(15, 8))
        ax1.plot(richness_df['datetime'], richness_df['richness'], 
                linewidth=1.5, alpha=0.8, color='darkblue')
        ax1.axhline(y=1.0, color='red', linestyle='--', alpha=0.7, label='Richness = 1.0')
        ax1.set_title('ATM Term Structure Richness Over Time', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Richness Ratio (Short-term IV / Long-term IV)')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # 添加统计信息
        avg_richness = richness_df['richness'].mean()
        std_richness = richness_df['richness'].std()
        ax1.text(0.02, 0.98, 
                f'Average Richness: {avg_richness:.3f}\nStd Dev: {std_richness:.3f}', 
                transform=ax1.transAxes, bbox=dict(boxstyle="round", facecolor='lightblue'),
                verticalalignment='top')
        
        plt.tight_layout()
        charts['richness_time_series'] = fig1
        
        # 图2: 短期vs长期IV对比
        fig2, ax2 = plt.subplots(figsize=(12, 8))
        ax2.plot(richness_df['datetime'], richness_df['short_term_iv'], 
                label='Short-term IV (7d+14d weighted)', alpha=0.8, linewidth=1.5, color='blue')
        ax2.plot(richness_df['datetime'], richness_df['long_term_iv'], 
                label='Long-term IV (60d+90d weighted)', alpha=0.8, linewidth=1.5, color='red')
        
        ax2.set_title('Short-term vs Long-term IV Comparison', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Time')
        ax2.set_ylabel('Implied Volatility')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        charts['iv_comparison'] = fig2
        
        # 图3: Richness分布直方图
        fig3, ax3 = plt.subplots(figsize=(10, 8))
        ax3.hist(richness_df['richness'], bins=50, alpha=0.7, color='green', edgecolor='black')
        ax3.axvline(x=1.0, color='red', linestyle='--', alpha=0.7, label='Richness = 1.0')
        ax3.axvline(x=avg_richness, color='orange', linestyle='-', alpha=0.8, label=f'Mean = {avg_richness:.3f}')
        
        ax3.set_title('Richness Distribution', fontsize=14, fontweight='bold')
        ax3.set_xlabel('Richness Ratio')
        ax3.set_ylabel('Frequency')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        charts['richness_distribution'] = fig3
        
        # 图4: 短期vs长期IV散点图
        fig4, ax4 = plt.subplots(figsize=(10, 8))
        scatter = ax4.scatter(richness_df['short_term_iv'], richness_df['long_term_iv'], 
                            alpha=0.6, c=richness_df['richness'], cmap='viridis')
        
        # 添加45度线
        min_iv = min(richness_df['short_term_iv'].min(), richness_df['long_term_iv'].min())
        max_iv = max(richness_df['short_term_iv'].max(), richness_df['long_term_iv'].max())
        ax4.plot([min_iv, max_iv], [min_iv, max_iv], 'r--', alpha=0.8, label='y=x (Richness=1.0)')
        
        # 添加颜色条
        cbar = plt.colorbar(scatter, ax=ax4)
        cbar.set_label('Richness Ratio', rotation=270, labelpad=20)
        
        ax4.set_title('Short-term vs Long-term IV Scatter Plot', fontsize=14, fontweight='bold')
        ax4.set_xlabel('Short-term IV')
        ax4.set_ylabel('Long-term IV')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        
        # 计算相关性
        correlation = richness_df['short_term_iv'].corr(richness_df['long_term_iv'])
        ax4.text(0.05, 0.95, f'Correlation: {correlation:.3f}', 
                transform=ax4.transAxes, bbox=dict(boxstyle="round", facecolor='yellow'))
        
        plt.tight_layout()
        charts['iv_scatter'] = fig4
        
        # 图5: 各期限IV时间序列
        fig5, ax5 = plt.subplots(figsize=(15, 8))
        
        colors = ['blue', 'green', 'orange', 'purple']
        for i, term in enumerate(['7d', '14d', '60d', '90d']):
            if f'{term}_iv' in richness_df.columns:
                valid_data = richness_df[richness_df[f'{term}_iv'].notna()]
                if len(valid_data) > 0:
                    ax5.plot(valid_data['datetime'], valid_data[f'{term}_iv'], 
                            label=f'{term} ATM IV', alpha=0.8, linewidth=1.2, 
                            color=colors[i % len(colors)])
        
        ax5.set_title('Individual Term ATM IV Time Series', fontsize=14, fontweight='bold')
        ax5.set_xlabel('Time')
        ax5.set_ylabel('Implied Volatility')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
        
        plt.tight_layout()
        charts['individual_terms'] = fig5
        
        return charts
    
    def save_results(self, richness_df, charts):
        """
        保存所有结果
        """
        print(f"\n💾 保存分析结果...")
        
        # 保存数据
        data_file = os.path.join(self.output_dir, "richness_time_series.csv")
        richness_df.to_csv(data_file, index=False)
        print(f"📊 时间序列数据已保存: {data_file}")
        
        # 保存图表
        for chart_name, fig in charts.items():
            chart_file = os.path.join(self.output_dir, f"{chart_name}.png")
            fig.savefig(chart_file, dpi=300, bbox_inches='tight')
            print(f"📊 图表已保存: {chart_file}")
            plt.close(fig)
        
        # 保存详细统计报告
        stats_file = os.path.join(self.output_dir, "richness_analysis_report.txt")
        self._save_statistics_report(richness_df, stats_file)
        
        print(f"📊 统计报告已保存: {stats_file}")
    
    def _save_statistics_report(self, richness_df, stats_file):
        """
        保存详细统计报告
        """
        with open(stats_file, 'w') as f:
            f.write("OKX BTC Options Term Structure Richness Analysis Report\n")
            f.write("="*60 + "\n\n")
            f.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # 数据概况
            f.write("DATA SUMMARY\n")
            f.write("-"*30 + "\n")
            f.write(f"Total Files Processed: {self.stats['total_files_processed']:,}\n")
            f.write(f"Total ATM Data Points: {self.stats['total_atm_data']:,}\n")
            f.write(f"Valid Richness Data Points: {self.stats['richness_data_points']:,}\n")
            f.write(f"Time Range: {self.stats['date_range'][0].strftime('%Y-%m-%d')} to {self.stats['date_range'][1].strftime('%Y-%m-%d')}\n\n")
            
            # 期限数据统计
            f.write("TERM DATA COUNTS\n")
            f.write("-"*30 + "\n")
            for term, count in self.stats['term_data_counts'].items():
                f.write(f"{term}: {count:,}\n")
            f.write("\n")
            
            # 加权IV统计
            if len(richness_df) > 0:
                f.write("WEIGHTED IV STATISTICS\n")
                f.write("-"*30 + "\n")
                
                short_term_stats = richness_df['short_term_iv'].describe()
                long_term_stats = richness_df['long_term_iv'].describe()
                
                f.write("Short-term IV (7d+14d weighted):\n")
                f.write(f"  Mean: {short_term_stats['mean']:.4f} ({short_term_stats['mean']*100:.1f}%)\n")
                f.write(f"  Std: {short_term_stats['std']:.4f}\n")
                f.write(f"  Min: {short_term_stats['min']:.4f}\n")
                f.write(f"  Max: {short_term_stats['max']:.4f}\n\n")
                
                f.write("Long-term IV (60d+90d weighted):\n")
                f.write(f"  Mean: {long_term_stats['mean']:.4f} ({long_term_stats['mean']*100:.1f}%)\n")
                f.write(f"  Std: {long_term_stats['std']:.4f}\n")
                f.write(f"  Min: {long_term_stats['min']:.4f}\n")
                f.write(f"  Max: {long_term_stats['max']:.4f}\n\n")
                
                # Richness统计
                richness_stats = richness_df['richness'].describe()
                f.write("RICHNESS STATISTICS\n")
                f.write("-"*30 + "\n")
                f.write(f"Mean: {richness_stats['mean']:.4f}\n")
                f.write(f"Std: {richness_stats['std']:.4f}\n")
                f.write(f"Min: {richness_stats['min']:.4f}\n")
                f.write(f"Max: {richness_stats['max']:.4f}\n")
                f.write(f"Median: {richness_stats['50%']:.4f}\n\n")
                
                # Richness异常值分析
                richness_values = richness_df['richness']
                shock_threshold = 1.45  # 参考用户图片中的1.45阈值
                
                shocks = richness_values[richness_values > shock_threshold]
                shock_dates = richness_df[richness_df['richness'] > shock_threshold]['datetime']
                
                f.write("RICHNESS SHOCK ANALYSIS\n")
                f.write("-"*30 + "\n")
                f.write(f"Shock Threshold: {shock_threshold}\n")
                f.write(f"Number of Shocks: {len(shocks)}\n")
                f.write(f"Shock Percentage: {len(shocks)/len(richness_values)*100:.2f}%\n")
                
                if len(shock_dates) > 0:
                    f.write(f"Shock Periods:\n")
                    for date in shock_dates.head(10):  # 显示前10个
                        f.write(f"  {date.strftime('%Y-%m-%d')}\n")
                    if len(shock_dates) > 10:
                        f.write(f"  ... and {len(shock_dates)-10} more\n")
    
    def print_summary(self, richness_df):
        """
        打印汇总统计
        """
        print(f"\n" + "="*60)
        print(f"📊 TERM STRUCTURE RICHNESS ANALYSIS SUMMARY")
        print(f"="*60)
        
        print(f"📈 Processing Results:")
        print(f"  Files Processed: {self.stats['total_files_processed']:,}")
        print(f"  Total ATM Data: {self.stats['total_atm_data']:,}")
        print(f"  Richness Data Points: {self.stats['richness_data_points']:,}")
        
        print(f"\n📊 Term Data Distribution:")
        for term, count in self.stats['term_data_counts'].items():
            print(f"  {term}: {count:,}")
        
        if len(richness_df) > 0:
            print(f"\n📈 Weighted IV Statistics:")
            print(f"  Short-term IV: {richness_df['short_term_iv'].mean():.3f} ± {richness_df['short_term_iv'].std():.3f}")
            print(f"  Long-term IV: {richness_df['long_term_iv'].mean():.3f} ± {richness_df['long_term_iv'].std():.3f}")
            
            print(f"\n🎯 Richness Analysis:")
            richness_mean = richness_df['richness'].mean()
            richness_std = richness_df['richness'].std()
            print(f"  Average Richness: {richness_mean:.3f}")
            print(f"  Richness Std Dev: {richness_std:.3f}")
            print(f"  Richness Range: {richness_df['richness'].min():.3f} - {richness_df['richness'].max():.3f}")
            
            # 期限结构特征
            if richness_mean > 1.0:
                print(f"  Term Structure: INVERTED (Short > Long)")
            else:
                print(f"  Term Structure: NORMAL (Long > Short)")
            
            # 市场状态分析
            high_richness_pct = (richness_df['richness'] > 1.45).sum() / len(richness_df) * 100
            print(f"  Shock Periods (>1.45): {high_richness_pct:.1f}% of time")

def main():
    """
    主分析流程
    """
    print("🚀 OKX BTC Options Term Structure Richness Analysis")
    print("="*60)
    
    # 配置路径
    data_dir = "/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks"
    output_dir = "/home/ubuntu/options_trading/okx_options_analysis/richness_analysis"
    
    # 创建分析器
    analyzer = TermStructureRichnessAnalyzer(data_dir, output_dir)
    
    try:
        # 处理所有文件
        combined_df = analyzer.process_all_files(batch_size=100)
        
        if len(combined_df) == 0:
            print("❌ 没有找到有效数据")
            return
        
        # 计算加权IV和Richness
        richness_df = analyzer.calculate_weighted_iv_and_richness(combined_df)
        
        if richness_df is None or len(richness_df) == 0:
            print("❌ 无法计算Richness指标")
            return
        
        # 创建图表
        charts = analyzer.create_individual_charts(richness_df)
        
        # 保存结果
        analyzer.save_results(richness_df, charts)
        
        # 打印汇总
        analyzer.print_summary(richness_df)
        
        print(f"\n🎉 分析完成！所有结果已保存到: {output_dir}")
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
