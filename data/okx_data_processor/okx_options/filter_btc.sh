#!/bin/bash
# OKX期权数据处理脚本：过滤BTC期权 + 可选30分钟聚合 + 智能批量处理
# 
# 批量模式特点：
# - 分批解压：每次只解压MICRO_BATCH_SIZE个文件，节省硬盘空间
# - 并行处理：同一批文件同时进行聚合处理，提高效率
# - 自动清理：处理完成后删除临时CSV文件，保持原始.gz文件

# 设置输入和输出文件（单文件模式）
INPUT_CSV="okx_btc_quotes/okex-options_quotes_2024-07-20_OPTIONS.csv"
OUTPUT_CSV_FILTERED="okx_btc_quotes/okex-options_quotes_2024-07-20_BTC_ONLY.csv"
OUTPUT_CSV_AGGREGATED="okx_btc_quotes/okex-options_quotes_2024-07-20_BTC_30MIN.csv"

# 批量处理设置
BATCH_INPUT_DIR="/data/option_data/okx_datasets4"
BATCH_OUTPUT_DIR="collected_klines_data"

# 设置参数
CHUNK_SIZE=100000
TS_UNIT="ms"
MICRO_BATCH_SIZE=4  # 每次只解压处理4个文件，节省硬盘空间

# 选择处理模式
MODE=${1:-"filter"}  # 可选: filter, aggregate, batch

if [ "$MODE" = "aggregate" ]; then
    echo "开始处理OKX期权数据 (30分钟聚合模式)..."
    echo "输入文件: $INPUT_CSV"
    echo "输出文件: $OUTPUT_CSV_AGGREGATED"
    echo "Chunk大小: $CHUNK_SIZE"
    echo "时间戳单位: $TS_UNIT"
    echo "================================"

    # 运行聚合脚本
    python options_processor.py \
        --in "$INPUT_CSV" \
        --out-csv "$OUTPUT_CSV_AGGREGATED" \
        --chunksize $CHUNK_SIZE \
        --aggregate \
        --ts-unit $TS_UNIT

    echo "30分钟聚合完成！"

elif [ "$MODE" = "filter" ]; then
    echo "开始过滤OKX期权数据 (仅过滤模式)..."
    echo "输入文件: $INPUT_CSV"
    echo "输出文件: $OUTPUT_CSV_FILTERED"
    echo "Chunk大小: $CHUNK_SIZE"
    echo "================================"

    # 运行过滤脚本
    python options_processor.py \
        --in "$INPUT_CSV" \
        --out-csv "$OUTPUT_CSV_FILTERED" \
        --chunksize $CHUNK_SIZE

    echo "过滤完成！"

elif [ "$MODE" = "batch" ]; then
    echo "开始批量处理文件夹 (分批解压+聚合模式，节省硬盘空间)..."
    echo "输入文件夹: $BATCH_INPUT_DIR"
    echo "输出文件夹: $BATCH_OUTPUT_DIR"
    echo "Chunk大小: $CHUNK_SIZE"
    echo "时间戳单位: $TS_UNIT"
    echo "微批大小: $MICRO_BATCH_SIZE (每次处理的文件数)"
    echo "================================"

    # 检查输入文件夹是否存在
    if [ ! -d "$BATCH_INPUT_DIR" ]; then
        echo "错误: 输入文件夹不存在: $BATCH_INPUT_DIR"
        exit 1
    fi

    # 创建输出文件夹
    mkdir -p "$BATCH_OUTPUT_DIR"

    # 获取所有.gz文件列表
    cd "$BATCH_INPUT_DIR"
    GZ_FILES=($(find . -name "*.gz" -type f))
    TOTAL_GZ_COUNT=${#GZ_FILES[@]}
    
    if [ $TOTAL_GZ_COUNT -eq 0 ]; then
        echo "没有找到.gz文件，退出"
        exit 1
    fi
    
    echo "找到 $TOTAL_GZ_COUNT 个.gz文件"
    echo "将按每批 $MICRO_BATCH_SIZE 个文件进行处理"
    echo ""

    # 回到原始工作目录
    cd - > /dev/null

    TOTAL_PROCESSED=0
    TOTAL_FAILED=0
    BATCH_NUM=1
    
    # 分批处理.gz文件
    for ((i=0; i<$TOTAL_GZ_COUNT; i+=$MICRO_BATCH_SIZE)); do
        END_IDX=$((i+$MICRO_BATCH_SIZE > $TOTAL_GZ_COUNT ? $TOTAL_GZ_COUNT : i+$MICRO_BATCH_SIZE))
        echo "================================"
        echo "处理第 $BATCH_NUM 批 (文件 $((i+1)) 到 $END_IDX，共 $((END_IDX-i)) 个文件)"
        echo "当前批次文件:"
        for ((k=i; k<$END_IDX; k++)); do
            echo "  - $(basename "${GZ_FILES[$k]}")"
        done
        echo "================================"
        
        # 当前批次的文件追踪
        CURRENT_BATCH=()           # 原始.gz文件名
        CSV_FILES_TO_PROCESS=()    # 需要处理的.csv文件
        NEWLY_UNZIPPED=()          # 新解压的文件，需要重新压缩
        
        # 步骤1: 严格按批次解压（避免重复处理）
        echo "步骤1: 解压第 $BATCH_NUM 批文件..."
        cd "$BATCH_INPUT_DIR"
        
        for ((j=i; j<i+$MICRO_BATCH_SIZE && j<$TOTAL_GZ_COUNT; j++)); do
            gz_file="${GZ_FILES[$j]}"
            gz_file=$(basename "$gz_file")  # 去掉路径前缀
            csv_file="${gz_file%.gz}"
            
            # 检查该文件是否已被处理过（通过检查输出文件是否存在）
            base_name="${csv_file%.csv}"
            output_filename="${base_name}_30min_klines.csv"
            output_path="../$BATCH_OUTPUT_DIR/$output_filename"
            
            if [ -f "$output_path" ]; then
                echo "  跳过: $gz_file (输出文件已存在: $output_filename)"
                continue
            fi
            
            # 智能解压逻辑：严格控制当前批次
            if [ -f "$csv_file" ]; then
                # CSV文件已存在（可能是之前中断留下的），直接使用
                echo "  发现遗留CSV: $csv_file (直接使用)"
                CSV_FILES_TO_PROCESS+=("$csv_file")
                CURRENT_BATCH+=("$gz_file")
                # 视为需要清理的文件，但不重新压缩
            elif [ -f "$gz_file" ]; then
                # .gz文件存在，正常解压
                echo "  解压: $gz_file"
                gunzip "$gz_file"
                
                if [ -f "$csv_file" ]; then
                    echo "  ✓ 解压成功: $csv_file"
                    CSV_FILES_TO_PROCESS+=("$csv_file")
                    CURRENT_BATCH+=("$gz_file")
                    NEWLY_UNZIPPED+=("$csv_file")  # 需要重新压缩
                else
                    echo "  ✗ 解压失败: $gz_file"
                fi
            else
                # 文件不存在或已被处理
                echo "  跳过: $gz_file (文件不存在或已处理)"
            fi
        done
        
        cd - > /dev/null
        
        # 步骤2: 并行处理当前批次的CSV文件
        echo ""
        echo "步骤2: 处理当前批次的CSV文件..."
        
        BATCH_PROCESSED=0
        BATCH_FAILED=0
        
        # 存储后台进程PID
        PIDS=()
        
        for csv_file in "${CSV_FILES_TO_PROCESS[@]}"; do
            csv_path="$BATCH_INPUT_DIR/$csv_file"
            filename=$(basename "$csv_file")
            
            if [ -f "$csv_path" ]; then
                echo "  开始处理: $filename"
                
                # 生成输出文件名
                base_name="${filename%.csv}"
                output_filename="${base_name}_30min_klines.csv"
                output_path="$BATCH_OUTPUT_DIR/$output_filename"
                
                # 后台并行处理
                (
                    python options_processor.py \
                        --in "$csv_path" \
                        --out-csv "$output_path" \
                        --chunksize $CHUNK_SIZE \
                        --aggregate \
                        --ts-unit $TS_UNIT
                    
                    # 处理完成后，记录结果到临时文件
                    if [ -f "$output_path" ] && [ -s "$output_path" ]; then
                        lines=$(wc -l < "$output_path")
                        echo "$filename:SUCCESS:$lines" >> "/tmp/batch_results_$$"
                    else
                        echo "$filename:FAILED:0" >> "/tmp/batch_results_$$"
                    fi
                ) &
                
                PIDS+=($!)
            fi
        done
        
        # 等待所有并行处理完成
        echo "  等待所有文件处理完成..."
        for pid in "${PIDS[@]}"; do
            wait $pid
        done
        
        # 读取处理结果
        if [ -f "/tmp/batch_results_$$" ]; then
            while IFS=':' read -r filename status lines; do
                if [ "$status" = "SUCCESS" ]; then
                    echo "  ✓ 成功: $filename ($lines 行K线数据)"
                    BATCH_PROCESSED=$((BATCH_PROCESSED + 1))
                else
                    echo "  ✗ 失败: $filename"
                    BATCH_FAILED=$((BATCH_FAILED + 1))
                fi
            done < "/tmp/batch_results_$$"
            rm -f "/tmp/batch_results_$$"
        fi
        
        # 步骤3: 智能重新压缩和清理
        echo ""
        echo "步骤3: 智能重新压缩和清理..."
        cd "$BATCH_INPUT_DIR"
        
        # 首先重新压缩那些新解压的文件
        if [ ${#NEWLY_UNZIPPED[@]} -gt 0 ]; then
            echo "重新压缩 ${#NEWLY_UNZIPPED[@]} 个新解压的文件..."
            for csv_file in "${NEWLY_UNZIPPED[@]}"; do
                if [ -f "$csv_file" ]; then
                    gz_name="${csv_file}.gz"
                    echo "  重新压缩: $csv_file -> $gz_name"
                    gzip "$csv_file"
                    
                    if [ -f "$gz_name" ]; then
                        echo "  ✓ 压缩成功: $gz_name"
                    else
                        echo "  ✗ 压缩失败: $csv_file"
                        # 如果压缩失败，手动删除CSV文件避免占用空间
                        rm -f "$csv_file"
                    fi
                else
                    echo "  ⚠ CSV文件已不存在: $csv_file"
                fi
            done
        else
            echo "本批次没有新解压的文件，无需重新压缩"
        fi
        
        # 然后清理任何剩余的CSV文件（比如之前就存在的）
        echo ""
        echo "清理任何剩余的CSV文件..."
        for csv_file in "${CSV_FILES_TO_PROCESS[@]}"; do
            if [ -f "$csv_file" ]; then
                echo "  清理: $csv_file"
                rm -f "$csv_file"
            fi
        done
        
        cd - > /dev/null
        
        TOTAL_PROCESSED=$((TOTAL_PROCESSED + BATCH_PROCESSED))
        TOTAL_FAILED=$((TOTAL_FAILED + BATCH_FAILED))
        
        echo ""
        echo "第 $BATCH_NUM 批处理完成："
        echo "  成功: $BATCH_PROCESSED"
        echo "  失败: $BATCH_FAILED"
        echo "  累计成功: $TOTAL_PROCESSED"
        echo "  累计失败: $TOTAL_FAILED"
        echo ""
        
        BATCH_NUM=$((BATCH_NUM + 1))
    done

    echo "================================"
    echo "批量处理全部完成！"
    echo "总文件数: $TOTAL_GZ_COUNT"
    echo "成功处理: $TOTAL_PROCESSED"
    echo "处理失败: $TOTAL_FAILED" 
    echo "输出目录: $BATCH_OUTPUT_DIR"
    echo "原始.gz文件已保持完整"

else
    echo "错误: 未知的模式 '$MODE'"
    echo "使用方法:"
    echo "  $0 filter     # 仅过滤ETH数据，保留BTC原始数据"
    echo "  $0 aggregate  # 过滤ETH数据并进行30分钟聚合"
    echo "  $0 batch      # 分批处理文件夹：解压->聚合->清理，节省硬盘空间"
    exit 1
fi
