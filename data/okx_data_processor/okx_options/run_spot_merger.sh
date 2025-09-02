#!/bin/bash
# 运行现货价格整合器

# 设置默认参数
INPUT_DIR="/home/ubuntu/options_trading/data/okx_data_processor/okx_options/collected_klines_data"
OUTPUT_DIR="/home/ubuntu/options_trading/data/okx_data_processor/okx_options/options_with_spot"
SPOT_CACHE="btc_spot_30min_cache.csv"
START_DATE="2020-01-01"
END_DATE="2025-08-24"

echo "==============================================="
echo "OKX期权数据现货价格整合器"
echo "==============================================="
echo "输入目录: $INPUT_DIR"
echo "输出目录: $OUTPUT_DIR"
echo "时间范围: $START_DATE 到 $END_DATE"
echo "现货缓存: $SPOT_CACHE"
echo ""

# 检查输入目录
if [ ! -d "$INPUT_DIR" ]; then
    echo "错误: 输入目录不存在: $INPUT_DIR"
    exit 1
fi

# 统计文件数
CSV_COUNT=$(find "$INPUT_DIR" -name "*.csv" | wc -l)
echo "找到 $CSV_COUNT 个期权CSV文件"

if [ $CSV_COUNT -eq 0 ]; then
    echo "警告: 没有找到期权CSV文件"
    exit 1
fi

echo ""
echo "开始处理..."

# 运行Python脚本
python spot_price_merger.py \
    --input-dir "$INPUT_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --spot-cache "$SPOT_CACHE" \
    --start-date "$START_DATE" \
    --end-date "$END_DATE"

# 检查结果
if [ $? -eq 0 ]; then
    echo ""
    echo "==============================================="
    echo "处理完成！"
    
    # 统计输出文件
    OUTPUT_COUNT=$(find "$OUTPUT_DIR" -name "*_with_spot.csv" 2>/dev/null | wc -l)
    echo "生成的输出文件: $OUTPUT_COUNT 个"
    
    if [ $OUTPUT_COUNT -gt 0 ]; then
        echo ""
        echo "输出文件示例:"
        find "$OUTPUT_DIR" -name "*_with_spot.csv" | head -5 | while read file; do
            echo "  - $(basename "$file")"
            if [ -f "$file" ]; then
                lines=$(wc -l < "$file")
                echo "    ($lines 行数据)"
            fi
        done
    fi
    
    echo ""
    echo "输出目录: $OUTPUT_DIR"
else
    echo ""
    echo "处理出现错误，请检查日志"
fi




