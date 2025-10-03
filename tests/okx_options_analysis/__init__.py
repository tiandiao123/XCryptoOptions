#!/usr/bin/env python3
"""
qtrade.okx_options_analysis - OKX Options Data Analysis Module

This module provides comprehensive tools for analyzing OKX cryptocurrency options data,
including implied volatility analysis, term structure studies, and richness analysis.

Main Components:
    - iv_analysis: IV term structure analysis and ATM option extraction
    - term_structure_richness_analysis: Term structure richness calculation
    - vol_analysis: Additional volatility analysis tools

Features:
    - ATM options filtering and extraction
    - Term structure analysis (7d, 14d, 60d, 90d)
    - Richness calculation: short_term_iv / long_term_iv  
    - Batch processing for large datasets
    - Professional visualization and reporting

Example Usage:
    >>> from qtrade.okx_options_analysis import iv_analysis
    >>> from qtrade.okx_options_analysis.term_structure_richness_analysis import TermStructureRichnessAnalyzer
    
    >>> # Extract ATM options
    >>> iv_analysis.extract_atm_options_simple('data.csv')
    
    >>> # Run richness analysis
    >>> analyzer = TermStructureRichnessAnalyzer(data_dir, output_dir)
    >>> results = analyzer.process_all_files()
"""

__version__ = "1.0.0"
__author__ = "OKX Options Trading Team"

# Import main modules
try:
    from . import iv_analysis
except ImportError:
    iv_analysis = None

try:
    from . import term_structure_richness_analysis
except ImportError:
    term_structure_richness_analysis = None

try:
    from . import vol_analysis
except ImportError:
    vol_analysis = None

# Public API
__all__ = [
    'iv_analysis',
    'term_structure_richness_analysis', 
    'vol_analysis',
    'extract_atm_options',
    'analyze_term_structure',
    'calculate_richness'
]

# Convenience functions
def extract_atm_options(csv_file, output_file=None, min_days_to_expiry=2, atm_tolerance=0.05):
    """
    便捷函数：提取ATM期权
    
    Args:
        csv_file: 输入CSV文件路径
        output_file: 输出文件路径（可选）
        min_days_to_expiry: 最小到期天数
        atm_tolerance: ATM容忍度
        
    Returns:
        DataFrame: ATM期权数据
    """
    if iv_analysis is not None:
        return iv_analysis.extract_atm_options_simple(
            csv_file, output_file, min_days_to_expiry, atm_tolerance
        )
    else:
        raise ImportError("iv_analysis module not available")

def analyze_term_structure(analysis_type="1m_vs_3m"):
    """
    便捷函数：期限结构分析
    
    Args:
        analysis_type: 分析类型 ("1m_vs_3m", "7d_vs_1m", etc.)
    """
    if iv_analysis is not None:
        return iv_analysis.main(analysis_type)
    else:
        raise ImportError("iv_analysis module not available")

def calculate_richness(data_dir, output_dir):
    """
    便捷函数：Richness分析
    
    Args:
        data_dir: 数据目录
        output_dir: 输出目录
        
    Returns:
        TermStructureRichnessAnalyzer: 分析器实例
    """
    if term_structure_richness_analysis is not None:
        analyzer = term_structure_richness_analysis.TermStructureRichnessAnalyzer(data_dir, output_dir)
        return analyzer
    else:
        raise ImportError("term_structure_richness_analysis module not available")

# Module information
def info():
    """显示模块信息"""
    print(f"qtrade.okx_options_analysis v{__version__}")
    print(f"Available modules:")
    for module in __all__[:3]:  # 只显示实际模块
        status = "✅" if globals().get(module) is not None else "❌"
        print(f"  {status} {module}")

# Configuration for analysis paths
ANALYSIS_CONFIG = {
    'default_data_dir': '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks',
    'default_output_dir': '/home/ubuntu/options_trading/qtrade/analysis_results',
    'term_configs': {
        '7d': {'min_days': 5, 'max_days': 9},
        '14d': {'min_days': 12, 'max_days': 16},
        '60d': {'min_days': 55, 'max_days': 65},
        '90d': {'min_days': 85, 'max_days': 95}
    },
    'atm_tolerance': 0.05,
    'min_days_to_expiry': 2
}

def get_analysis_config():
    """获取分析配置"""
    return ANALYSIS_CONFIG.copy()

if __name__ == "__main__":
    info()
