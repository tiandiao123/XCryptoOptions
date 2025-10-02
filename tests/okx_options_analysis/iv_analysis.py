#!/usr/bin/env python3
"""
OKX期权ATM IV期限结构分析 - 修复版
分批处理大数据量，避免内存溢出
修复了列名冲突的bug
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os
import re
from datetime import datetime, timezone
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# 设置图表样式
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")

# 期限配置字典
TERM_CONFIGS = {
    "1m_vs_3m": {
        "term1": {"name": "1-month", "min_days": 25, "max_days": 35},
        "term2": {"name": "3-month", "min_days": 80, "max_days": 100},
        "title": "1-month vs 3-month Options",
        "output_prefix": "1month_vs_3month"
    },
    "7d_vs_1m": {
        "term1": {"name": "7-day", "min_days": 5, "max_days": 10},
        "term2": {"name": "1-month", "min_days": 25, "max_days": 35},
        "title": "7-day vs 1-month Options",
        "output_prefix": "7day_vs_1month"
    },
    "15d_vs_1m": {
        "term1": {"name": "15-day", "min_days": 12, "max_days": 18},
        "term2": {"name": "1-month", "min_days": 25, "max_days": 35},
        "title": "15-day vs 1-month Options",
        "output_prefix": "15day_vs_1month"
    },
    "15d_vs_2m": {
        "term1": {"name": "15-day", "min_days": 12, "max_days": 18},
        "term2": {"name": "2-month", "min_days": 55, "max_days": 65},
        "title": "15-day vs 2-month Options",
        "output_prefix": "15day_vs_2month"
    }
}

def process_single_file(csv_file, term_config):
    """
    处理单个CSV文件，返回ATM期权数据
    根据term_config配置筛选指定期限的期权
    
    修复：直接使用CSV中已有的列，不重新解析symbol
    """
    try:
        df = pd.read_csv(csv_file)
        
        # 检查必要的列是否存在
        required_columns = ['symbol', 'time', 'open', 'spot_open', 'iv', 'time_to_expiry', 'strike_price', 'option_type']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"文件缺少必要列: {missing_columns} - {os.path.basename(csv_file)}")
            return None
        
        # 基本数据清洗
        df = df.dropna(subset=['symbol', 'time', 'open', 'spot_open', 'iv', 'time_to_expiry'])
        
        # 过滤异常IV值和计算失败的行
        df = df[
            (df['iv'] > 1e-05) & 
            (df['iv'] < 4.99) & 
            (df['calculation_success'] == True) &
            (df['error'].isna() | (df['error'] == ''))
        ]
        
        if len(df) == 0:
            return None
        
        # 过滤掉当天到期的期权（时间到期 < 2天）
        df = df[df['days_to_expiry'] >= 2.0].copy()
        
        if len(df) == 0:
            return None
        
        # 使用CSV中已有的strike_price列
        df['strike'] = df['strike_price']
        
        # 计算moneyness
        df['moneyness'] = df['spot_open'] / df['strike']
        
        # 筛选ATM期权（moneyness在0.95-1.05之间）
        atm_df = df[
            (df['moneyness'] >= 0.95) & 
            (df['moneyness'] <= 1.05)
        ].copy()
        
        if len(atm_df) == 0:
            return None
        
        # 按期限分类：根据配置进行分类
        term1_mask = (atm_df['days_to_expiry'] >= term_config['term1']['min_days']) & (atm_df['days_to_expiry'] <= term_config['term1']['max_days'])
        term2_mask = (atm_df['days_to_expiry'] >= term_config['term2']['min_days']) & (atm_df['days_to_expiry'] <= term_config['term2']['max_days'])
        
        atm_df['term_category'] = None
        atm_df.loc[term1_mask, 'term_category'] = term_config['term1']['name']
        atm_df.loc[term2_mask, 'term_category'] = term_config['term2']['name']
        
        target_df = atm_df[atm_df['term_category'].notna()].copy()
        
        if len(target_df) == 0:
            return None
            
        # 只保留需要的列以节省内存
        columns_to_keep = [
            'symbol', 'time', 'iv', 'spot_open', 'moneyness', 'term_category', 
            'strike', 'option_type', 'time_to_expiry', 'days_to_expiry'
        ]
        target_df = target_df[columns_to_keep]
        
        return target_df
        
    except Exception as e:
        print(f"处理文件失败: {os.path.basename(csv_file)} - {e}")
        return None

def create_time_series_from_batch(batch_data):
    """
    从批量数据创建时间序列统计
    """
    if len(batch_data) == 0:
        return pd.DataFrame()
    
    # 转换时间格式
    batch_data['datetime'] = pd.to_datetime(batch_data['time'])
    
    # 按时间和期限分组统计
    time_series = batch_data.groupby(['datetime', 'term_category']).agg({
        'iv': ['mean', 'median', 'std', 'count'],
        'spot_open': 'first',
        'moneyness': ['mean', 'std'],
        'time_to_expiry': ['mean', 'std']
    }).reset_index()
    
    # 平整列名
    time_series.columns = [
        'datetime', 'term_category', 
        'iv_mean', 'iv_median', 'iv_std', 'iv_count',
        'spot_price', 'moneyness_mean', 'moneyness_std',
        'tte_mean', 'tte_std'
    ]
    
    # 过滤数据量太少的时间点
    time_series = time_series[time_series['iv_count'] >= 3]
    
    return time_series

def process_data_in_batches(data_dir, term_config, batch_size=80):
    """
    分批处理数据，根据配置分析指定期限的期权
    """
    print(f"📊 分批处理模式启动 - {term_config['title']}...")
    
    # 获取所有CSV文件
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    csv_files.sort()
    
    print(f"找到 {len(csv_files)} 个文件")
    print(f"批次大小: {batch_size} 文件/批")
    
    total_batches = (len(csv_files) + batch_size - 1) // batch_size
    print(f"总批次数: {total_batches}")
    
    all_time_series = []
    all_stats = {
        'total_atm_data': 0,
        'term1_count': 0,
        'term2_count': 0,
        'term1_iv_list': [],
        'term2_iv_list': [],
        'term1_name': term_config['term1']['name'],
        'term2_name': term_config['term2']['name'],
        'date_range': [None, None]
    }
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(csv_files))
        
        batch_files = csv_files[start_idx:end_idx]
        
        print(f"\n🔄 处理批次 {batch_num + 1}/{total_batches} ({len(batch_files)} 文件)")
        
        batch_data = []
        successful_files = 0
        
        for csv_file in tqdm(batch_files, desc=f"批次{batch_num+1}"):
            file_data = process_single_file(csv_file, term_config)
            if file_data is not None:
                batch_data.append(file_data)
                successful_files += 1
        
        print(f"  批次成功处理: {successful_files}/{len(batch_files)} 文件")
        
        if batch_data:
            # 合并批次数据
            batch_df = pd.concat(batch_data, ignore_index=True)
            
            print(f"  批次数据: {len(batch_df):,} 行ATM数据")
            
            # 更新统计信息
            term1_data = batch_df[batch_df['term_category'] == term_config['term1']['name']]
            term2_data = batch_df[batch_df['term_category'] == term_config['term2']['name']]
            
            all_stats['total_atm_data'] += len(batch_df)
            all_stats['term1_count'] += len(term1_data)
            all_stats['term2_count'] += len(term2_data)
            
            if len(term1_data) > 0:
                all_stats['term1_iv_list'].extend(term1_data['iv'].tolist())
            if len(term2_data) > 0:
                all_stats['term2_iv_list'].extend(term2_data['iv'].tolist())
            
            # 更新日期范围
            dates = pd.to_datetime(batch_df['time'])
            if all_stats['date_range'][0] is None:
                all_stats['date_range'][0] = dates.min()
                all_stats['date_range'][1] = dates.max()
            else:
                all_stats['date_range'][0] = min(all_stats['date_range'][0], dates.min())
                all_stats['date_range'][1] = max(all_stats['date_range'][1], dates.max())
            
            # 创建时间序列
            batch_time_series = create_time_series_from_batch(batch_df)
            if len(batch_time_series) > 0:
                all_time_series.append(batch_time_series)
            
            # 清理内存
            del batch_df, batch_data
            
            print(f"  累计ATM数据: {all_stats['total_atm_data']:,} 行")
            print(f"  {all_stats['term1_name']}: {all_stats['term1_count']:,}, {all_stats['term2_name']}: {all_stats['term2_count']:,}")
    
    # 合并所有时间序列
    if all_time_series:
        print("\n🔄 合并时间序列数据...")
        combined_time_series = pd.concat(all_time_series, ignore_index=True)
        
        # 按时间和期限重新聚合（处理重复时间点）
        final_time_series = combined_time_series.groupby(['datetime', 'term_category']).agg({
            'iv_mean': 'mean',
            'iv_median': 'mean', 
            'iv_std': 'mean',
            'iv_count': 'sum',
            'spot_price': 'first',
            'moneyness_mean': 'mean',
            'moneyness_std': 'mean',
            'tte_mean': 'mean',
            'tte_std': 'mean'
        }).reset_index()
        
    else:
        final_time_series = pd.DataFrame()
    
    return final_time_series, all_stats

def create_visualization(time_series_df, stats, term_config):
    """
    创建期权期限结构的可视化图表
    """
    print(f"🎨 Creating {term_config['title']} visualization charts...")
    
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(f'OKX BTC Options ATM IV Term Structure Analysis: {term_config["title"]}', fontsize=16, fontweight='bold')
    
    # 图1: IV时间序列对比
    ax1 = axes[0, 0]
    
    term1_data = time_series_df[time_series_df['term_category'] == term_config['term1']['name']]
    term2_data = time_series_df[time_series_df['term_category'] == term_config['term2']['name']]
    
    if len(term1_data) > 0:
        ax1.plot(term1_data['datetime'], term1_data['iv_mean'], 
                label=f'{term_config["term1"]["name"]} ATM IV', alpha=0.8, linewidth=1.5, color='blue')
    
    if len(term2_data) > 0:
        ax1.plot(term2_data['datetime'], term2_data['iv_mean'], 
                label=f'{term_config["term2"]["name"]} ATM IV', alpha=0.8, linewidth=1.5, color='red')
    
    ax1.set_title(f'ATM IV Time Series Comparison ({term_config["title"]})')
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Implied Volatility')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 图2: IV分布对比
    ax2 = axes[0, 1]
    
    term1_iv = np.array(stats['term1_iv_list'])
    term2_iv = np.array(stats['term2_iv_list'])
    
    if len(term1_iv) > 0 and len(term2_iv) > 0:
        ax2.hist([term1_iv, term2_iv], bins=50, alpha=0.7, 
                label=[stats['term1_name'], stats['term2_name']], color=['blue', 'red'])
        ax2.set_title('ATM IV Distribution Comparison')
        ax2.set_xlabel('Implied Volatility')
        ax2.set_ylabel('Frequency')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
    
    # 图3: 期限价差时间序列
    ax3 = axes[1, 0]
    
    if len(term1_data) > 0 and len(term2_data) > 0:
        merged_data = pd.merge(
            term1_data[['datetime', 'iv_mean']].rename(columns={'iv_mean': 'iv_term1'}),
            term2_data[['datetime', 'iv_mean']].rename(columns={'iv_mean': 'iv_term2'}),
            on='datetime', how='inner'
        )
        
        if len(merged_data) > 0:
            merged_data['term_spread'] = merged_data['iv_term2'] - merged_data['iv_term1']
            
            ax3.plot(merged_data['datetime'], merged_data['term_spread'], 
                    color='green', linewidth=1.5, alpha=0.8)
            ax3.axhline(y=0, color='black', linestyle='--', alpha=0.5)
            ax3.set_title(f'Term Spread ({stats["term2_name"]}IV - {stats["term1_name"]}IV)')
            ax3.set_xlabel('Time')
            ax3.set_ylabel('Spread')
            ax3.grid(True, alpha=0.3)
            
            # 添加统计信息
            avg_spread = merged_data['term_spread'].mean()
            ax3.text(0.02, 0.98, f'Average Spread: {avg_spread:.3f} ({avg_spread*100:.1f}%)', 
                    transform=ax3.transAxes, bbox=dict(boxstyle="round", facecolor='wheat'),
                    verticalalignment='top')
    
    # 图4: 散点图相关性 + 统计摘要
    ax4 = axes[1, 1]
    
    if len(term1_data) > 0 and len(term2_data) > 0:
        merged_data = pd.merge(
            term1_data[['datetime', 'iv_mean']].rename(columns={'iv_mean': 'iv_term1'}),
            term2_data[['datetime', 'iv_mean']].rename(columns={'iv_mean': 'iv_term2'}),
            on='datetime', how='inner'
        )
        
        if len(merged_data) > 0:
            ax4.scatter(merged_data['iv_term1'], merged_data['iv_term2'], 
                       alpha=0.6, color='purple')
            
            # 添加45度线
            min_iv = min(merged_data['iv_term1'].min(), merged_data['iv_term2'].min())
            max_iv = max(merged_data['iv_term1'].max(), merged_data['iv_term2'].max())
            ax4.plot([min_iv, max_iv], [min_iv, max_iv], 'r--', alpha=0.8, label='y=x')
            
            ax4.set_title(f'{stats["term1_name"]} vs {stats["term2_name"]} IV Correlation')
            ax4.set_xlabel(f'{stats["term1_name"]} ATM IV')
            ax4.set_ylabel(f'{stats["term2_name"]} ATM IV')
            ax4.legend()
            ax4.grid(True, alpha=0.3)
            
            # 计算相关系数
            correlation = merged_data['iv_term1'].corr(merged_data['iv_term2'])
            ax4.text(0.05, 0.95, f'Correlation: {correlation:.3f}', 
                    transform=ax4.transAxes, bbox=dict(boxstyle="round", facecolor='lightblue'))
    
    # 添加整体统计信息
    stats_text = f"""
Data Summary:
Total ATM Data: {stats['total_atm_data']:,}
{stats['term1_name']}: {stats['term1_count']:,}
{stats['term2_name']}: {stats['term2_count']:,}

Time Range: 
{stats['date_range'][0].strftime('%Y-%m-%d')} to
{stats['date_range'][1].strftime('%Y-%m-%d')}
"""
    
    # 在图3的空白区域添加统计信息
    if len(term1_data) > 0 and len(term2_data) > 0:
        ax3.text(0.02, 0.02, stats_text, transform=ax3.transAxes, fontsize=10,
                bbox=dict(boxstyle="round", facecolor='lightgray'), 
                verticalalignment='bottom')
    
    plt.tight_layout()
    return fig

def print_detailed_statistics(stats):
    """
    打印详细统计信息
    """
    print("\n" + "="*60)
    print(f"📊 {stats['term1_name']} vs {stats['term2_name']}期权 ATM IV分析统计")
    print("="*60)
    
    term1_iv = np.array(stats['term1_iv_list'])
    term2_iv = np.array(stats['term2_iv_list'])
    
    print(f"总ATM数据点: {stats['total_atm_data']:,}")
    print(f"{stats['term1_name']}数据: {stats['term1_count']:,} ({stats['term1_count']/stats['total_atm_data']*100:.1f}%)")
    print(f"{stats['term2_name']}数据: {stats['term2_count']:,} ({stats['term2_count']/stats['total_atm_data']*100:.1f}%)")
    
    print(f"\n时间范围: {stats['date_range'][0].strftime('%Y-%m-%d')} 到 {stats['date_range'][1].strftime('%Y-%m-%d')}")
    
    if len(term1_iv) > 0:
        print(f"\n{stats['term1_name']}IV统计:")
        print(f"  平均IV: {term1_iv.mean():.3f} ({term1_iv.mean()*100:.1f}%)")
        print(f"  中位数IV: {np.median(term1_iv):.3f}")
        print(f"  标准差: {term1_iv.std():.3f}")
        print(f"  范围: {term1_iv.min():.3f} - {term1_iv.max():.3f}")
    
    if len(term2_iv) > 0:
        print(f"\n{stats['term2_name']}IV统计:")
        print(f"  平均IV: {term2_iv.mean():.3f} ({term2_iv.mean()*100:.1f}%)")
        print(f"  中位数IV: {np.median(term2_iv):.3f}")
        print(f"  标准差: {term2_iv.std():.3f}")
        print(f"  范围: {term2_iv.min():.3f} - {term2_iv.max():.3f}")
    
    if len(term1_iv) > 0 and len(term2_iv) > 0:
        avg_spread = term2_iv.mean() - term1_iv.mean()
        print(f"\n期限结构特征:")
        print(f"  平均期限价差: {avg_spread:.3f} ({avg_spread*100:.1f}%)")
        print(f"  期限结构形状: {'向上倾斜' if avg_spread > 0 else '向下倾斜或平坦'}")
        print(f"  价差标准差: {np.std(term2_iv) - np.std(term1_iv):.3f}")

def extract_atm_options_simple(csv_file, output_file=None, min_days_to_expiry=2, atm_tolerance=0.05):
    """
    简单的ATM期权提取器
    专门回答用户的需求：提取ATM期权，排除当天交割的
    
    Args:
        csv_file: 输入CSV文件
        output_file: 输出文件名（可选）
        min_days_to_expiry: 最小到期天数（默认2天）
        atm_tolerance: ATM容忍度（默认5%，即0.95-1.05 moneyness）
    """
    print(f"📊 提取ATM期权: {os.path.basename(csv_file)}")
    
    try:
        # 读取数据
        df = pd.read_csv(csv_file)
        print(f"   原始数据: {len(df):,} 行")
        
        # 基本筛选
        df = df[
            (df['calculation_success'] == True) &  # 只要计算成功的
            (df['days_to_expiry'] >= min_days_to_expiry) &  # 排除当天和次日交割
            (df['iv'] > 1e-05) & (df['iv'] < 4.99)  # 过滤异常IV
        ].copy()
        
        print(f"   基本筛选后: {len(df):,} 行")
        
        # 计算moneyness
        df['moneyness'] = df['spot_open'] / df['strike_price']
        
        # 筛选ATM期权
        atm_df = df[
            (df['moneyness'] >= (1 - atm_tolerance)) & 
            (df['moneyness'] <= (1 + atm_tolerance))
        ].copy()
        
        print(f"   ATM期权筛选后: {len(atm_df):,} 行")
        print(f"   Moneyness范围: {1-atm_tolerance:.2f} - {1+atm_tolerance:.2f}")
        
        if len(atm_df) == 0:
            print("   ⚠️ 没有找到符合条件的ATM期权")
            return None
        
        # 显示统计信息
        print(f"   到期天数范围: {atm_df['days_to_expiry'].min():.1f} - {atm_df['days_to_expiry'].max():.1f} 天")
        print(f"   IV范围: {atm_df['iv'].min():.3f} - {atm_df['iv'].max():.3f}")
        print(f"   平均IV: {atm_df['iv'].mean():.3f} ({atm_df['iv'].mean()*100:.1f}%)")
        
        # 期权类型分布
        call_count = (atm_df['option_type'] == 'C').sum()
        put_count = (atm_df['option_type'] == 'P').sum()
        print(f"   期权类型: Call {call_count}, Put {put_count}")
        
        # 保存结果
        if output_file is None:
            base_name = os.path.splitext(os.path.basename(csv_file))[0]
            output_file = f"{base_name}_ATM_filtered.csv"
        
        atm_df.to_csv(output_file, index=False)
        print(f"   💾 ATM期权已保存: {output_file}")
        
        return atm_df
        
    except Exception as e:
        print(f"   ❌ 处理失败: {e}")
        return None

def main(analysis_type="1m_vs_3m"):
    """
    主分析流程
    :param analysis_type: 分析类型，可选: "1m_vs_3m", "7d_vs_1m", "15d_vs_1m", "15d_vs_2m"
    """
    if analysis_type not in TERM_CONFIGS:
        print(f"❌ 无效的分析类型: {analysis_type}")
        print(f"可选类型: {list(TERM_CONFIGS.keys())}")
        return
    
    term_config = TERM_CONFIGS[analysis_type]
    print(f"🚀 OKX期权ATM IV期限结构分析: {term_config['title']}")
    print("="*60)
    
    data_dir = "/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks"
    output_dir = f"/home/ubuntu/options_trading/okx_options_analysis/term_structure_analysis/{term_config['output_prefix']}"
    
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # 分批处理数据
        time_series_df, stats = process_data_in_batches(data_dir, term_config, batch_size=80)
        
        if len(time_series_df) == 0:
            print(f"❌ 没有找到有效的{term_config['title']}ATM期权数据")
            return
        
        print(f"\n✅ 处理完成！")
        print(f"时间序列数据点: {len(time_series_df):,}")
        
        # 打印详细统计
        print_detailed_statistics(stats)
        
        # 创建可视化
        fig = create_visualization(time_series_df, stats, term_config)
        
        # 保存结果到专门的文件夹
        chart_file = os.path.join(output_dir, f"{term_config['output_prefix']}_atm_iv_analysis.png")
        fig.savefig(chart_file, dpi=300, bbox_inches='tight')
        print(f"\n📊 分析图表已保存: {chart_file}")
        
        # 保存时间序列数据
        ts_file = os.path.join(output_dir, f"{term_config['output_prefix']}_time_series.csv")
        time_series_df.to_csv(ts_file, index=False)
        print(f"📊 时间序列已保存: {ts_file}")
        
        # 保存统计摘要
        summary_file = os.path.join(output_dir, "analysis_summary.txt")
        with open(summary_file, 'w') as f:
            f.write(f"{term_config['title']} ATM IV分析摘要\n")
            f.write("="*50 + "\n\n")
            f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"数据范围: {stats['date_range'][0].strftime('%Y-%m-%d')} 到 {stats['date_range'][1].strftime('%Y-%m-%d')}\n\n")
            f.write(f"总ATM数据点: {stats['total_atm_data']:,}\n")
            f.write(f"{stats['term1_name']}数据: {stats['term1_count']:,}\n")
            f.write(f"{stats['term2_name']}数据: {stats['term2_count']:,}\n\n")
            
            if len(stats['term1_iv_list']) > 0:
                term1_iv = np.array(stats['term1_iv_list'])
                f.write(f"{stats['term1_name']}平均IV: {term1_iv.mean():.3f} ({term1_iv.mean()*100:.1f}%)\n")
            
            if len(stats['term2_iv_list']) > 0:
                term2_iv = np.array(stats['term2_iv_list'])
                f.write(f"{stats['term2_name']}平均IV: {term2_iv.mean():.3f} ({term2_iv.mean()*100:.1f}%)\n")
                
                if len(stats['term1_iv_list']) > 0:
                    avg_spread = term2_iv.mean() - term1_iv.mean()
                    f.write(f"平均期限价差: {avg_spread:.3f} ({avg_spread*100:.1f}%)\n")
        
        print(f"📊 分析摘要已保存: {summary_file}")
        
        plt.show()
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    
    # 检查是否是简单ATM提取模式
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        # 简单ATM提取模式
        if len(sys.argv) > 2:
            csv_file = sys.argv[2]
        else:
            csv_file = "/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks/okex-options_quotes_2021-01-12_OPTIONS_30min_klines_with_iv_greeks.csv"
        
        print("🎯 ATM期权提取模式")
        print("="*50)
        result = extract_atm_options_simple(csv_file)
        
        if result is not None:
            print(f"\n✅ 成功提取 {len(result)} 个ATM期权数据点")
        
    else:
        # 原来的期限结构分析模式
        if len(sys.argv) > 1:
            analysis_type = sys.argv[1]
        else:
            # 默认分析类型，或者提供交互式选择
            print("可选的分析类型:")
            for key, config in TERM_CONFIGS.items():
                print(f"  {key}: {config['title']}")
            
            analysis_type = input("\n请选择分析类型 (默认: 1m_vs_3m): ").strip()
            if not analysis_type:
                analysis_type = "1m_vs_3m"
        
        main(analysis_type)
