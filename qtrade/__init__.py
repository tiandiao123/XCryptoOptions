#!/usr/bin/env python3
"""
qtrade - OKX Options Trading Analysis Package

A comprehensive toolkit for cryptocurrency options data analysis,
including implied volatility analysis, term structure studies, 
and trading strategy development.

Modules:
    okx_options_analysis: Advanced options analysis tools
    simulate_trade: Trading simulation framework (WIP)

Example:
    >>> from qtrade.okx_options_analysis import iv_analysis
    >>> from qtrade.okx_options_analysis import term_structure_richness_analysis
"""

__version__ = "1.0.0"
__author__ = "OKX Options Trading Team"
__email__ = "trading@example.com"
__description__ = "Professional tools for OKX options data analysis"

# Public API
from . import okx_options_analysis

# Version info
VERSION = __version__

# Package metadata
__all__ = [
    'okx_options_analysis',
    'VERSION',
    '__version__',
    '__author__',
    '__email__',
    '__description__'
]

# Configuration
DEFAULT_CONFIG = {
    'data_dir': '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks',
    'output_dir': '/home/ubuntu/options_trading/qtrade/analysis_results',
    'cache_dir': '/home/ubuntu/options_trading/qtrade/cache',
    'log_level': 'INFO'
}

def get_config():
    """获取默认配置"""
    return DEFAULT_CONFIG.copy()

def set_config(**kwargs):
    """设置配置参数"""
    global DEFAULT_CONFIG
    DEFAULT_CONFIG.update(kwargs)

# 包初始化信息
def info():
    """显示包信息"""
    print(f"qtrade v{__version__}")
    print(f"Author: {__author__}")
    print(f"Description: {__description__}")
    print(f"Available modules: {__all__}")

if __name__ == "__main__":
    info()
