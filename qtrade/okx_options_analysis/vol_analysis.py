"""
OKX Options Realized Volatility Analysis
现货价格 Realized Volatility 分析工具

功能：
1. 计算多时间窗口的 realized volatility (1天、3天、7天、30天)
2. 历史分位数分析
3. 时间序列分析和可视化
4. 统计报告生成

作者: Options Trading Analysis Team
日期: 2024
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import os
from pathlib import Path
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 导入自定义模块
import sys
sys.path.append('/home/ubuntu/options_trading')
from qtrade.data_utils import (
    get_sorted_dates_from_files, 
    get_intraday_30min_data,
    get_atm_options_at_time
)


class RealizedVolatilityAnalyzer:
    """Realized Volatility 分析器"""
    
    def __init__(self, data_folder_path, output_folder=None):
        """
        初始化分析器
        
        Args:
            data_folder_path: 数据文件夹路径
            output_folder: 输出文件夹路径（可选）
        """
        self.data_folder_path = data_folder_path
        # 修改为 vol_analysis.py 同级目录
        if output_folder is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.output_folder = f"{current_dir}/vol_analysis_results"
        else:
            self.output_folder = output_folder
        
        # 创建输出文件夹
        Path(self.output_folder).mkdir(parents=True, exist_ok=True)
        
        # 获取所有日期和文件映射
        print("🚀 初始化 Realized Volatility 分析器...")
        self.dates, self.date_files = get_sorted_dates_from_files(data_folder_path)
        
        print(f"📊 找到 {len(self.dates)} 个交易日")
        print(f"📅 日期范围: {self.dates[0]} 到 {self.dates[-1]}")
        print(f"📁 输出目录: {self.output_folder}")
        
        # 存储计算结果
        self.spot_prices_df = None
        self.realized_vol_df = None
        self.atm_iv_df = None
        
    def collect_spot_prices(self, price_type='spot_open'):
        """
        收集所有时间点的现货价格数据
        
        Args:
            price_type: 价格类型 ('spot_open', 'spot_close', 'spot_high', 'spot_low')
            
        Returns:
            pd.DataFrame: 时间序列现货价格数据
        """
        print(f"\n📈 收集现货价格数据 (价格类型: {price_type})...")
        
        all_price_data = []
        
        for i, date in enumerate(tqdm(self.dates, desc="收集价格数据")):
            try:
                file_path = self.date_files[date]
                times, prices, time_price_map, _ = get_intraday_30min_data(
                    file_path, price_type=price_type, print_info=False
                )
                
                for time_point, price in zip(times, prices):
                    all_price_data.append({
                        'datetime': time_point,
                        'date': date,
                        'price': price,
                        'price_type': price_type
                    })
                    
            except Exception as e:
                print(f"⚠️  处理日期 {date} 失败: {e}")
                continue
        
        # 转换为DataFrame
        self.spot_prices_df = pd.DataFrame(all_price_data)
        self.spot_prices_df = self.spot_prices_df.sort_values('datetime').reset_index(drop=True)
        
        print(f"✅ 收集完成！")
        print(f"   总时间点: {len(self.spot_prices_df):,}")
        print(f"   价格范围: ${self.spot_prices_df['price'].min():,.2f} - ${self.spot_prices_df['price'].max():,.2f}")
        print(f"   时间范围: {self.spot_prices_df['datetime'].min()} 到 {self.spot_prices_df['datetime'].max()}")
        
        return self.spot_prices_df
    
    def collect_atm_iv_data(self, atm_tolerance=0.05, min_days_to_expiry=2):
        """
        收集所有时间点的 ATM 期权 IV 数据
        
        Args:
            atm_tolerance: ATM容忍度（默认5%）
            min_days_to_expiry: 最小到期天数（默认2天）
            
        Returns:
            pd.DataFrame: ATM IV 时间序列数据
        """
        print(f"\n📊 收集 ATM 期权 IV 数据...")
        print(f"   ATM容忍度: ±{atm_tolerance*100:.1f}%")
        print(f"   最小到期天数: {min_days_to_expiry}天")
        
        all_atm_iv_data = []
        
        for i, date in enumerate(tqdm(self.dates, desc="收集ATM IV数据")):
            try:
                file_path = self.date_files[date]
                times, prices, time_price_map, df = get_intraday_30min_data(
                    file_path, price_type='spot_open', print_info=False
                )
                
                for time_point, spot_price in zip(times, prices):
                    # 获取该时间点的ATM期权
                    atm_options = get_atm_options_at_time(
                        df, time_point, spot_price, atm_tolerance, print_info=False
                    )
                    
                    # 过滤最小到期天数
                    filtered_options = [
                        opt for opt in atm_options 
                        if opt['days_to_expiry'] >= min_days_to_expiry
                    ]
                    
                    if filtered_options:
                        # 计算 IV 统计
                        iv_values = [opt['iv'] for opt in filtered_options]
                        
                        all_atm_iv_data.append({
                            'datetime': time_point,
                            'date': date,
                            'spot_price': spot_price,
                            'atm_iv_mean': np.mean(iv_values),
                            'atm_iv_median': np.median(iv_values),
                            'atm_iv_std': np.std(iv_values),
                            'atm_options_count': len(filtered_options),
                            'atm_iv_min': np.min(iv_values),
                            'atm_iv_max': np.max(iv_values)
                        })
                        
            except Exception as e:
                print(f"⚠️  处理日期 {date} 失败: {e}")
                continue
        
        # 转换为DataFrame
        self.atm_iv_df = pd.DataFrame(all_atm_iv_data)
        self.atm_iv_df = self.atm_iv_df.sort_values('datetime').reset_index(drop=True)
        
        print(f"✅ ATM IV 数据收集完成！")
        print(f"   总时间点: {len(self.atm_iv_df):,}")
        if len(self.atm_iv_df) > 0:
            print(f"   IV 范围: {self.atm_iv_df['atm_iv_mean'].min():.3f} - {self.atm_iv_df['atm_iv_mean'].max():.3f}")
            print(f"   平均IV: {self.atm_iv_df['atm_iv_mean'].mean():.3f}")
            print(f"   平均ATM期权数: {self.atm_iv_df['atm_options_count'].mean():.1f}")
        
        return self.atm_iv_df
    
    def calculate_realized_volatility(self, windows=[1, 3, 7, 30]):
        """
        计算多时间窗口的 realized volatility
        
        Args:
            windows: 时间窗口列表（天数）
            
        Returns:
            pd.DataFrame: realized volatility 数据
        """
        if self.spot_prices_df is None:
            raise ValueError("请先调用 collect_spot_prices() 收集价格数据")
        
        print(f"\n📊 计算 Realized Volatility (窗口: {windows} 天)...")
        
        # 计算对数收益率
        df = self.spot_prices_df.copy()
        df['log_return'] = np.log(df['price'] / df['price'].shift(1))
        
        # 移除空值
        df = df.dropna()
        
        print(f"📈 对数收益率统计:")
        print(f"   总收益率点数: {len(df):,}")
        print(f"   平均收益率: {df['log_return'].mean():.6f}")
        print(f"   收益率标准差: {df['log_return'].std():.6f}")
        print(f"   最大收益率: {df['log_return'].max():.4f}")
        print(f"   最小收益率: {df['log_return'].min():.4f}")
        
        # 为每个窗口计算 realized volatility
        vol_data = []
        
        for window_days in windows:
            print(f"\n🔄 计算 {window_days} 天窗口...")
            
            # 计算每个窗口期间内的30分钟收益率个数
            # 假设每天约48个30分钟时间点
            window_periods = window_days * 48
            
            # 滚动计算realized volatility
            df[f'rv_{window_days}d'] = df['log_return'].rolling(
                window=window_periods, min_periods=int(window_periods * 0.8)
            ).std() * np.sqrt(365 * 48)  # 年化
            
            # 收集有效数据
            valid_data = df[df[f'rv_{window_days}d'].notna()].copy()
            
            for _, row in valid_data.iterrows():
                vol_data.append({
                    'datetime': row['datetime'],
                    'date': row['date'],
                    'window_days': window_days,
                    'realized_vol': row[f'rv_{window_days}d'],
                    'spot_price': row['price'],
                    'log_return': row['log_return']
                })
            
            print(f"   有效数据点: {len(valid_data):,}")
            if len(valid_data) > 0:
                print(f"   RV 范围: {valid_data[f'rv_{window_days}d'].min():.3f} - {valid_data[f'rv_{window_days}d'].max():.3f}")
                print(f"   RV 平均: {valid_data[f'rv_{window_days}d'].mean():.3f}")
        
        # 转换为DataFrame
        self.realized_vol_df = pd.DataFrame(vol_data)
        
        print(f"\n✅ Realized Volatility 计算完成！")
        print(f"   总数据点: {len(self.realized_vol_df):,}")
        print(f"   时间窗口: {windows}")
        
        return self.realized_vol_df
    
    def generate_statistics_report(self):
        """生成统计报告"""
        if self.realized_vol_df is None:
            raise ValueError("请先计算 realized volatility")
        
        print(f"\n📊 生成统计报告...")
        
        stats_data = []
        
        for window in self.realized_vol_df['window_days'].unique():
            window_data = self.realized_vol_df[
                self.realized_vol_df['window_days'] == window
            ]['realized_vol']
            
            if len(window_data) == 0:
                continue
            
            stats = {
                'window_days': window,
                'count': len(window_data),
                'mean': window_data.mean(),
                'std': window_data.std(),
                'min': window_data.min(),
                'q25': window_data.quantile(0.25),
                'median': window_data.median(),
                'q75': window_data.quantile(0.75),
                'q90': window_data.quantile(0.90),
                'q95': window_data.quantile(0.95),
                'q99': window_data.quantile(0.99),
                'max': window_data.max(),
                'skewness': window_data.skew(),
                'kurtosis': window_data.kurtosis()
            }
            stats_data.append(stats)
        
        stats_df = pd.DataFrame(stats_data)
        
        # 保存统计报告
        stats_file = f"{self.output_folder}/realized_vol_statistics.csv"
        stats_df.to_csv(stats_file, index=False)
        
        # 打印摘要
        print(f"\n📈 Realized Volatility 统计摘要:")
        print("="*70)
        print(f"{'窗口':<6} {'数据点':<8} {'均值':<8} {'中位数':<8} {'P95':<8} {'最大值':<8}")
        print("-"*70)
        
        for _, row in stats_df.iterrows():
            print(f"{row['window_days']:>4}天 {row['count']:>8.0f} "
                  f"{row['mean']:>8.3f} {row['median']:>8.3f} "
                  f"{row['q95']:>8.3f} {row['max']:>8.3f}")
        
        print(f"\n💾 统计报告已保存: {stats_file}")
        return stats_df
    
    def compare_iv_vs_rv(self, rv_window=30):
        """
        对比 ATM IV 与 Realized Volatility
        
        Args:
            rv_window: 用于对比的 RV 时间窗口（天）
            
        Returns:
            pd.DataFrame: IV vs RV 对比数据
        """
        if self.realized_vol_df is None or self.atm_iv_df is None:
            raise ValueError("请先计算 realized volatility 和收集 ATM IV 数据")
        
        print(f"\n📊 对比 ATM IV vs {rv_window}天 Realized Volatility...")
        
        # 获取指定窗口的RV数据
        rv_data = self.realized_vol_df[
            self.realized_vol_df['window_days'] == rv_window
        ][['datetime', 'realized_vol']].copy()
        
        # 合并 IV 和 RV 数据
        comparison_df = pd.merge(
            self.atm_iv_df[['datetime', 'atm_iv_mean', 'spot_price', 'atm_options_count']], 
            rv_data, 
            on='datetime', 
            how='inner'
        )
        
        if len(comparison_df) == 0:
            print("⚠️  没有找到匹配的时间点数据")
            return pd.DataFrame()
        
        # 计算统计指标
        comparison_df['iv_rv_spread'] = comparison_df['atm_iv_mean'] - comparison_df['realized_vol']
        comparison_df['iv_rv_ratio'] = comparison_df['atm_iv_mean'] / comparison_df['realized_vol']
        
        print(f"✅ IV vs RV 对比完成！")
        print(f"   匹配时间点: {len(comparison_df):,}")
        print(f"   IV 平均: {comparison_df['atm_iv_mean'].mean():.3f}")
        print(f"   RV 平均: {comparison_df['realized_vol'].mean():.3f}")
        print(f"   IV-RV 差值平均: {comparison_df['iv_rv_spread'].mean():.3f}")
        print(f"   IV/RV 比率平均: {comparison_df['iv_rv_ratio'].mean():.3f}")
        
        return comparison_df
    
    def create_visualization(self):
        """创建可视化图表"""
        if self.realized_vol_df is None:
            raise ValueError("请先计算 realized volatility")
        
        print(f"\n🎨 创建可视化图表...")
        
        # 设置图表样式
        plt.style.use('seaborn-v0_8')
        
        # 1. Realized Volatility 分析图
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('BTC Realized Volatility Analysis', fontsize=16, fontweight='bold')
        
        windows = sorted(self.realized_vol_df['window_days'].unique())
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
        
        # 子图1: 时间序列对比
        ax1 = axes[0, 0]
        for i, window in enumerate(windows):
            window_data = self.realized_vol_df[
                self.realized_vol_df['window_days'] == window
            ].copy()
            
            if len(window_data) > 0:
                ax1.plot(window_data['datetime'], window_data['realized_vol'], 
                        label=f'{window}D', alpha=0.8, linewidth=1.5, 
                        color=colors[i % len(colors)])
        
        ax1.set_title('Realized Volatility Time Series')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Realized Volatility')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 子图2: 分布对比（箱线图）
        ax2 = axes[0, 1]
        box_data = []
        box_labels = []
        
        for window in windows:
            window_data = self.realized_vol_df[
                self.realized_vol_df['window_days'] == window
            ]['realized_vol']
            
            if len(window_data) > 0:
                box_data.append(window_data.values)
                box_labels.append(f'{window}D')
        
        if box_data:
            bp = ax2.boxplot(box_data, labels=box_labels, patch_artist=True)
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
        
        ax2.set_title('Realized Volatility Distribution')
        ax2.set_xlabel('Time Window')
        ax2.set_ylabel('Realized Volatility')
        ax2.grid(True, alpha=0.3)
        
        # 子图3: 历史分位数分析
        ax3 = axes[1, 0]
        
        # 选择最长窗口进行分位数分析
        longest_window = max(windows)
        longest_data = self.realized_vol_df[
            self.realized_vol_df['window_days'] == longest_window
        ].copy()
        
        if len(longest_data) > 0:
            # 计算滚动分位数
            longest_data = longest_data.sort_values('datetime')
            longest_data['percentile'] = longest_data['realized_vol'].rolling(
                window=min(len(longest_data), 500), min_periods=50
            ).apply(lambda x: (x <= x.iloc[-1]).mean() * 100)
            
            # 绘制时间序列和分位数
            ax3_twin = ax3.twinx()
            
            line1 = ax3.plot(longest_data['datetime'], longest_data['realized_vol'], 
                           color='blue', alpha=0.7, linewidth=1, label='RV')
            line2 = ax3_twin.plot(longest_data['datetime'], longest_data['percentile'], 
                                color='red', alpha=0.7, linewidth=1, label='Percentile')
            
            ax3.set_ylabel('Realized Volatility', color='blue')
            ax3_twin.set_ylabel('Historical Percentile (%)', color='red')
            ax3.set_title(f'{longest_window}D RV Historical Percentile')
            
            # 添加分位数线
            ax3_twin.axhline(y=95, color='red', linestyle='--', alpha=0.5, label='95%')
            ax3_twin.axhline(y=75, color='orange', linestyle='--', alpha=0.5, label='75%')
            ax3_twin.axhline(y=25, color='green', linestyle='--', alpha=0.5, label='25%')
            ax3_twin.axhline(y=5, color='red', linestyle='--', alpha=0.5, label='5%')
            
            # 合并图例
            lines1, labels1 = ax3.get_legend_handles_labels()
            lines2, labels2 = ax3_twin.get_legend_handles_labels()
            ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        ax3.grid(True, alpha=0.3)
        
        # 子图4: 相关性分析
        ax4 = axes[1, 1]
        
        if len(windows) > 1:
            # 创建相关性矩阵
            corr_data = {}
            for window in windows:
                window_data = self.realized_vol_df[
                    self.realized_vol_df['window_days'] == window
                ][['datetime', 'realized_vol']].copy()
                window_data = window_data.rename(columns={'realized_vol': f'RV_{window}D'})
                
                if len(corr_data) == 0:
                    corr_data = window_data
                else:
                    corr_data = pd.merge(corr_data, window_data, on='datetime', how='inner')
            
            if len(corr_data) > 10:  # 确保有足够数据
                corr_matrix = corr_data.drop('datetime', axis=1).corr()
                
                # 绘制热力图
                sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', 
                           center=0, ax=ax4, fmt='.3f')
                ax4.set_title('RV Windows Correlation')
        
        plt.tight_layout()
        
        # 保存图表
        chart_file = f"{self.output_folder}/realized_vol_analysis.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.show()
        
        print(f"💾 图表已保存: {chart_file}")
        
        return fig
    
    def create_iv_vs_rv_visualization(self, rv_window=30):
        """
        创建 IV vs RV 对比可视化图表
        
        Args:
            rv_window: RV 时间窗口（天）
        """
        # 获取对比数据
        comparison_df = self.compare_iv_vs_rv(rv_window=rv_window)
        
        if len(comparison_df) == 0:
            print("⚠️  没有数据可供可视化")
            return None
        
        print(f"\n🎨 创建 IV vs RV 对比图表...")
        
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'ATM IV vs {rv_window}D Realized Volatility Comparison', 
                     fontsize=16, fontweight='bold')
        
        # 子图1: IV vs RV 时间序列
        ax1 = axes[0, 0]
        ax1.plot(comparison_df['datetime'], comparison_df['atm_iv_mean'], 
                label='ATM IV', alpha=0.8, linewidth=1.5, color='red')
        ax1.plot(comparison_df['datetime'], comparison_df['realized_vol'], 
                label=f'{rv_window}D RV', alpha=0.8, linewidth=1.5, color='blue')
        ax1.set_title('IV vs RV Time Series')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Volatility')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 子图2: IV vs RV 散点图
        ax2 = axes[0, 1]
        scatter = ax2.scatter(comparison_df['realized_vol'], comparison_df['atm_iv_mean'], 
                             alpha=0.6, s=20, c=comparison_df.index, cmap='viridis')
        
        # 添加45度线
        min_val = min(comparison_df['realized_vol'].min(), comparison_df['atm_iv_mean'].min())
        max_val = max(comparison_df['realized_vol'].max(), comparison_df['atm_iv_mean'].max())
        ax2.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.5, label='45° line')
        
        ax2.set_xlabel(f'{rv_window}D Realized Volatility')
        ax2.set_ylabel('ATM Implied Volatility')
        ax2.set_title('IV vs RV Scatter Plot')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 子图3: IV-RV 差值时间序列
        ax3 = axes[1, 0]
        ax3.plot(comparison_df['datetime'], comparison_df['iv_rv_spread'], 
                alpha=0.8, linewidth=1.5, color='green')
        ax3.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax3.set_title('IV - RV Spread')
        ax3.set_xlabel('Time')
        ax3.set_ylabel('IV - RV')
        ax3.grid(True, alpha=0.3)
        
        # 子图4: IV/RV 比率分布
        ax4 = axes[1, 1]
        
        # 过滤异常值
        ratio_data = comparison_df['iv_rv_ratio']
        q1, q99 = ratio_data.quantile([0.01, 0.99])
        filtered_ratio = ratio_data[(ratio_data >= q1) & (ratio_data <= q99)]
        
        ax4.hist(filtered_ratio, bins=50, alpha=0.7, color='orange', edgecolor='black')
        ax4.axvline(x=1, color='red', linestyle='--', alpha=0.7, label='IV = RV')
        ax4.axvline(x=filtered_ratio.mean(), color='blue', linestyle='--', alpha=0.7, 
                   label=f'Mean = {filtered_ratio.mean():.2f}')
        ax4.set_title('IV/RV Ratio Distribution')
        ax4.set_xlabel('IV/RV Ratio')
        ax4.set_ylabel('Frequency')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 保存图表
        chart_file = f"{self.output_folder}/iv_vs_rv_comparison.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.show()
        
        print(f"💾 IV vs RV 对比图表已保存: {chart_file}")
        
        return fig
    
    def export_data(self):
        """导出分析数据"""
        if self.realized_vol_df is None:
            raise ValueError("请先计算 realized volatility")
        
        print(f"\n💾 导出分析数据...")
        
        # 导出详细数据
        detail_file = f"{self.output_folder}/realized_vol_detail.csv"
        self.realized_vol_df.to_csv(detail_file, index=False)
        
        # 导出现货价格数据
        if self.spot_prices_df is not None:
            price_file = f"{self.output_folder}/spot_prices_timeseries.csv"
            self.spot_prices_df.to_csv(price_file, index=False)
        
        # 导出 ATM IV 数据
        if self.atm_iv_df is not None:
            iv_file = f"{self.output_folder}/atm_iv_timeseries.csv"
            self.atm_iv_df.to_csv(iv_file, index=False)
            print(f"   ATM IV数据: {iv_file}")
        
        print(f"   详细数据: {detail_file}")
        if self.spot_prices_df is not None:
            print(f"   价格数据: {price_file}")
        
        return detail_file
    
    def run_full_analysis(self, price_type='spot_open', windows=[1, 3, 7, 30], 
                         include_iv_analysis=True, rv_window_for_iv_comparison=30):
        """
        运行完整分析流程
        
        Args:
            price_type: 价格类型
            windows: 时间窗口列表
            include_iv_analysis: 是否包含 IV 分析
            rv_window_for_iv_comparison: 用于与 IV 对比的 RV 窗口（天）
        """
        print(f"\n🚀 开始完整 Realized Volatility 分析...")
        print(f"📊 分析参数:")
        print(f"   价格类型: {price_type}")
        print(f"   时间窗口: {windows} 天")
        print(f"   包含IV分析: {include_iv_analysis}")
        if include_iv_analysis:
            print(f"   IV对比窗口: {rv_window_for_iv_comparison} 天")
        print(f"   数据期间: {self.dates[0]} 到 {self.dates[-1]}")
        
        try:
            # 1. 收集价格数据
            self.collect_spot_prices(price_type=price_type)
            
            # 2. 计算realized volatility  
            self.calculate_realized_volatility(windows=windows)
            
            # 3. 收集 ATM IV 数据（如果需要）
            if include_iv_analysis:
                self.collect_atm_iv_data(atm_tolerance=0.02, min_days_to_expiry=3)
            
            # 4. 生成统计报告
            stats_df = self.generate_statistics_report()
            
            # 5. 创建 RV 可视化
            self.create_visualization()
            
            # 6. 创建 IV vs RV 对比可视化（如果有 IV 数据）
            if include_iv_analysis and self.atm_iv_df is not None:
                self.create_iv_vs_rv_visualization(rv_window=rv_window_for_iv_comparison)
            
            # 7. 导出数据
            self.export_data()
            
            print(f"\n✅ 完整分析完成！")
            print(f"📁 所有结果已保存到: {self.output_folder}")
            
            result = {
                'realized_vol_df': self.realized_vol_df,
                'spot_prices_df': self.spot_prices_df,
                'statistics_df': stats_df,
                'output_folder': self.output_folder
            }
            
            if include_iv_analysis and self.atm_iv_df is not None:
                result['atm_iv_df'] = self.atm_iv_df
            
            return result
            
        except Exception as e:
            print(f"❌ 分析过程中发生错误: {e}")
            raise


def main():
    """主函数"""
    print("🚀 BTC Realized Volatility 分析工具")
    print("="*60)
    
    # 配置参数
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    
    # 创建分析器
    analyzer = RealizedVolatilityAnalyzer(data_folder)
    
    # 运行完整分析
    results = analyzer.run_full_analysis(
        price_type='spot_open',
        windows=[1, 3, 7, 30],
        include_iv_analysis=True,
        rv_window_for_iv_comparison=30
    )
    
    print(f"\n🎉 分析完成！")
    print(f"📁 结果文件夹: {results['output_folder']}")
    

if __name__ == "__main__":
    main()
