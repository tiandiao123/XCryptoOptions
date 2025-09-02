# qtrade - Professional OKX Options Trading Analysis Package

A comprehensive Python package for cryptocurrency options data analysis, featuring advanced implied volatility studies, term structure analysis, and trading strategy development tools.

## 🚀 Features

### 📊 Core Analysis Modules

- **IV Analysis**: Implied volatility term structure analysis with ATM option filtering
- **Richness Analysis**: Term structure richness calculation based on weighted IV ratios
- **Vol Analysis**: Additional volatility analysis tools (extensible framework)

### 🎯 Key Capabilities

- **ATM Options Extraction**: Intelligent filtering of At-The-Money options
- **Term Structure Analysis**: 7d, 14d, 60d, 90d term analysis
- **Richness Calculation**: `richness = short_term_iv / long_term_iv`
- **Batch Processing**: Handle 1000+ CSV files efficiently
- **Professional Visualization**: Publication-ready charts and reports

## 📁 Package Structure

```
qtrade/
├── __init__.py                     # Main package interface
├── okx_options_analysis/           # Options analysis module
│   ├── __init__.py                # Module interface
│   ├── iv_analysis.py             # IV term structure analysis
│   ├── term_structure_richness_analysis.py  # Richness analysis
│   ├── vol_analysis.py            # Volatility analysis tools
│   └── results/                   # Analysis results storage
└── simulate_tarde/                 # Trading simulation (WIP)
    └── __init__.py                # Simulation interface
```

## ⚡ Quick Start

### Installation

```bash
# Clone or download the package
cd /home/ubuntu/options_trading

# Install in development mode
pip install -e .

# Or install from requirements
pip install -r requirements.txt
```

### Basic Usage

```python
import qtrade

# Show package information
qtrade.info()

# Extract ATM options from a file
from qtrade import extract_atm_options
atm_data = extract_atm_options('your_options_file.csv')

# Run term structure analysis  
from qtrade import analyze_term_structure
analyze_term_structure('1m_vs_3m')

# Run richness analysis
from qtrade import calculate_richness
analyzer = calculate_richness(data_dir, output_dir)
results = analyzer.process_all_files()
```

### Command Line Tools

```bash
# IV term structure analysis
qtrade-iv-analysis 1m_vs_3m
qtrade-iv-analysis 7d_vs_1m

# Extract ATM options
qtrade-iv-analysis extract /path/to/file.csv

# Richness analysis
qtrade-richness
```

## 📊 Analysis Types

### 1. Term Structure Analysis

Compare different option maturities:

- `1m_vs_3m`: 1-month vs 3-month options
- `7d_vs_1m`: 7-day vs 1-month options  
- `15d_vs_1m`: 15-day vs 1-month options
- `15d_vs_2m`: 15-day vs 2-month options

### 2. Richness Analysis

Calculate term structure richness:

```
short_term_iv = 0.5 * atm7d_iv + 0.5 * atm14d_iv
long_term_iv = 0.5 * atm60d_iv + 0.5 * atm90d_iv
richness = short_term_iv / long_term_iv
```

### 3. ATM Option Filtering

Intelligent ATM option extraction:
- Moneyness range: 0.95 - 1.05
- Minimum days to expiry: 2+ days
- IV range filtering: Remove extreme outliers
- Quality control: Only successful calculations

## 📈 Output Files

### Analysis Results
- **Time series data**: CSV files with processed data
- **Visualization**: High-resolution PNG charts  
- **Statistical reports**: Detailed TXT summaries
- **Correlation analysis**: Scatter plots and correlation coefficients

### File Organization
```
analysis_results/
├── richness_analysis/
│   ├── richness_time_series.png
│   ├── iv_comparison.png
│   ├── richness_distribution.png
│   └── richness_analysis_report.txt
└── term_structure_analysis/
    ├── 1month_vs_3month/
    ├── 7day_vs_1month/
    └── [other combinations]/
```

## 🔧 Configuration

### Default Settings

```python
from qtrade import get_config
config = get_config()

# Modify settings
from qtrade import set_config
set_config(
    data_dir='/path/to/your/data',
    output_dir='/path/to/output'
)
```

### Analysis Parameters

- **ATM Tolerance**: 5% (0.95-1.05 moneyness)
- **Min Days to Expiry**: 2 days
- **Term Ranges**:
  - 7d: 5-9 days
  - 14d: 12-16 days  
  - 60d: 55-65 days
  - 90d: 85-95 days

## 📊 Data Requirements

### Input CSV Format

Required columns:
- `symbol`: Option symbol (BTC-USD-YYMMDD-STRIKE-C/P)
- `time`: Timestamp (YYYY-MM-DD HH:MM:SS UTC)
- `spot_open`: Spot price
- `strike_price`: Option strike price
- `option_type`: 'C' for calls, 'P' for puts
- `iv`: Implied volatility
- `days_to_expiry`: Days until expiration
- `calculation_success`: Boolean success flag

### Expected Data Volume

- **Files**: 1000+ CSV files
- **Records per file**: 10k-30k option records
- **Total data**: Millions of option data points
- **Time range**: Multi-year historical data

## 🎯 Advanced Usage

### Custom Analysis

```python
from qtrade.okx_options_analysis.term_structure_richness_analysis import TermStructureRichnessAnalyzer

# Create custom analyzer
analyzer = TermStructureRichnessAnalyzer(
    data_dir='/your/data/path',
    output_dir='/your/output/path'
)

# Process data
combined_df = analyzer.process_all_files(batch_size=50)
richness_df = analyzer.calculate_weighted_iv_and_richness(combined_df)

# Create custom charts
charts = analyzer.create_individual_charts(richness_df)
```

### Batch Processing

```python
from qtrade.okx_options_analysis.iv_analysis import process_data_in_batches

# Custom term configuration
term_config = {
    "term1": {"name": "weekly", "min_days": 5, "max_days": 10},
    "term2": {"name": "monthly", "min_days": 25, "max_days": 35},
    "title": "Weekly vs Monthly Options"
}

# Process with custom settings
results = process_data_in_batches(data_dir, term_config, batch_size=100)
```

## 🛠️ Development

### Testing

```bash
# Test package functionality
python example_usage.py

# Test individual modules
python -m qtrade.okx_options_analysis.iv_analysis
python -m qtrade.okx_options_analysis.term_structure_richness_analysis
```

### Building

```bash
# Build distribution
python setup.py sdist bdist_wheel

# Install locally
pip install -e .
```

## 📝 Dependencies

- `pandas >= 1.3.0`: Data manipulation
- `numpy >= 1.21.0`: Numerical computations  
- `matplotlib >= 3.3.0`: Plotting
- `seaborn >= 0.11.0`: Statistical visualization
- `tqdm >= 4.60.0`: Progress bars
- `requests >= 2.25.0`: HTTP requests

## 🤝 Contributing

This package is designed for extensibility:

1. **Add new analysis modules**: Create new .py files in okx_options_analysis/
2. **Extend term configurations**: Modify TERM_CONFIGS dictionary
3. **Add visualization types**: Extend create_individual_charts() method
4. **Implement trading simulation**: Develop simulate_tarde/ module

## 📞 Support

For issues and questions:
1. Check the analysis reports for data quality issues
2. Verify CSV file format matches requirements
3. Ensure sufficient disk space for large datasets
4. Monitor memory usage during batch processing

## 📊 Performance

- **Processing Speed**: ~10-15 files/second
- **Memory Usage**: Optimized batch processing  
- **Disk Usage**: ~5GB for full analysis results
- **Scalability**: Tested with 1600+ files

---

**qtrade** - Professional cryptocurrency options analysis made simple! 🚀
