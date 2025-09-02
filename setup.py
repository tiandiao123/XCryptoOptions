#!/usr/bin/env python3
"""
Setup script for qtrade package - OKX Options Trading Analysis Tools
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取README文件
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

# 读取requirements文件
requirements_file = this_directory / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file, 'r') as f:
        install_requires = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
else:
    install_requires = [
        'pandas>=1.3.0',
        'numpy>=1.21.0',
        'matplotlib>=3.3.0',
        'seaborn>=0.11.0',
        'tqdm>=4.60.0',
        'requests>=2.25.0'
    ]

setup(
    name="qtrade",
    version="1.0.0",
    author="OKX Options Trading Team",
    author_email="trading@example.com",
    description="Professional tools for OKX options data analysis and trading strategy development",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourcompany/qtrade",
    
    # Package discovery
    packages=find_packages(),
    include_package_data=True,
    
    # Python version requirement
    python_requires=">=3.8",
    
    # Dependencies
    install_requires=install_requires,
    
    # Optional dependencies
    extras_require={
        'dev': [
            'pytest>=6.0',
            'pytest-cov>=2.0',
            'black>=21.0',
            'flake8>=3.8'
        ],
        'analysis': [
            'jupyter>=1.0',
            'plotly>=5.0',
            'dash>=2.0'
        ]
    },
    
    # Console scripts - 命令行工具
    entry_points={
        'console_scripts': [
            'qtrade-iv-analysis=qtrade.okx_options_analysis.iv_analysis:main',
            'qtrade-richness=qtrade.okx_options_analysis.term_structure_richness_analysis:main',
            'qtrade-vol-analysis=qtrade.okx_options_analysis.vol_analysis:main',
        ],
    },
    
    # 分类信息
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry", 
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    
    # 关键词
    keywords="options trading analysis implied-volatility term-structure cryptocurrency bitcoin okx",
    
    # 项目URLs
    project_urls={
        'Documentation': 'https://github.com/yourcompany/qtrade/docs',
        'Bug Reports': 'https://github.com/yourcompany/qtrade/issues',
        'Source': 'https://github.com/yourcompany/qtrade',
    },
    
    # Package data - 包含数据文件
    package_data={
        'qtrade': [
            'okx_options_analysis/richness_analysis/*',
            'okx_options_analysis/term_structure_analysis/*',
            '*.sh',
            '*.txt',
            '*.csv'
        ],
    },
    
    # 数据文件
    data_files=[
        ('qtrade/docs', ['README.md'] if Path('README.md').exists() else []),
        ('qtrade/config', ['requirements.txt'] if Path('requirements.txt').exists() else []),
    ],
    
    # Zip安全
    zip_safe=False,
)
