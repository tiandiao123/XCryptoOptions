from qtrade.order_api.okx.func_call.perp.perp_order import get_trade_fills_history
from datetime import datetime, timedelta


def get_perp_realized_pnl(
    instrument: str, 
    start_time: str, 
    perp_pnl_dict: dict,
    previous_realized_pnl: float = 0,
    silent: bool = False
) -> tuple[float, str]:
    """
    获取永续合约的 Realized P&L，并更新成交记录字典
    
    Args:
        instrument: 合约ID，如 "ETH-USD-SWAP"
        start_time: 开始时间，支持两种格式：
                   1. 时间戳（毫秒）："1731888000000"
                   2. 日期字符串："2025-11-18 00:00:00"
        perp_pnl_dict: 成交记录字典 {tradeId: fill_data}
                      - 保持按 fillTime 排序
                      - key: tradeId（唯一标识）
                      - value: fill详细信息
        previous_realized_pnl: 上次计算的已实现P&L（用于增量累加）
        silent: 是否静默模式（不打印详细信息）
    
    Returns:
        tuple: (total_realized_pnl, last_fill_time)
               - total_realized_pnl: 累积的已实现盈亏
               - last_fill_time: 最新成交的时间戳（毫秒），用于下次增量查询
    
    智能查询逻辑：
        - 如果 perp_pnl_dict 为空：从 start_time 开始查询
        - 如果 perp_pnl_dict 不为空：从 (last_fill_time - 5分钟) 开始查询
          （向前推5分钟是为了避免遗漏在上次检查时刚发生但未显示的交易）
    """
    
    # ===== 1. 确定查询起始时间 =====
    if perp_pnl_dict:
        # 获取字典中最后一个交易的 fillTime
        last_trade_id = list(perp_pnl_dict.keys())[-1]  # 最后一个key
        last_fill_time_ms = int(perp_pnl_dict[last_trade_id]['fillTime'])
        
        # 向前推5分钟（300000毫秒）作为安全边界
        safe_start_time_ms = last_fill_time_ms - 300000
        
        if not silent:
            print(f"🔄 增量查询模式:")
            print(f"   上次最后成交: {last_fill_time_ms} ({_ms_to_datetime(last_fill_time_ms)})")
            print(f"   本次查询起点: {safe_start_time_ms} ({_ms_to_datetime(safe_start_time_ms)}) [向前5分钟]")
        
        query_start_time_ms = str(safe_start_time_ms)
    else:
        # 首次查询：使用用户指定的 start_time
        if not start_time.isdigit():
            dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            query_start_time_ms = str(int(dt.timestamp() * 1000))
        else:
            query_start_time_ms = start_time
        
        if not silent:
            print(f"🆕 首次查询模式:")
            print(f"   查询起点: {query_start_time_ms} ({_ms_to_datetime(int(query_start_time_ms))})")
    
    # ===== 2. 获取成交历史 =====
    if not silent:
        print(f"\n🔍 查询 {instrument} 的成交历史...")
    
    fills = get_trade_fills_history(
        instId=instrument, 
        begin=query_start_time_ms, 
        simulated=False
    )
    
    if not silent:
        print(f"✅ API返回 {len(fills)} 条成交记录")
    
    # ===== 3. 去重并按时间排序 =====
    new_fills = []
    duplicate_count = 0
    
    for fill in fills:
        trade_id = fill.get('tradeId')
        
        if trade_id in perp_pnl_dict:
            # 跳过已存在的交易（去重）
            duplicate_count += 1
            continue
        
        new_fills.append(fill)
    
    if not silent:
        print(f"   新增成交: {len(new_fills)} 条")
        print(f"   重复过滤: {duplicate_count} 条")
    
    # 按 fillTime 排序（从旧到新）
    new_fills.sort(key=lambda x: int(x.get('fillTime', 0)))
    
    # ===== 4. 更新字典并计算 P&L =====
    new_pnl = 0.0
    
    for fill in new_fills:
        trade_id = fill.get('tradeId')
        fill_pnl = float(fill.get('fillPnl', 0))
        
        # 存储到字典（按时间顺序插入）
        perp_pnl_dict[trade_id] = {
            'orderId': fill.get('ordId'),
            'side': fill.get('side'),
            'fillSz': fill.get('fillSz'),
            'fillPx': fill.get('fillPx'),
            'fillPnl': fill_pnl,
            'fee': float(fill.get('fee', 0)),
            'fillTime': fill.get('fillTime'),
            'ts': fill.get('ts')
        }
        
        new_pnl += fill_pnl
        
        # 打印新增的成交
        if not silent:
            print(f"\n   ➕ TradeID: {trade_id}")
            print(f"      时间: {_ms_to_datetime(int(fill.get('fillTime', 0)))}")
            print(f"      方向: {fill.get('side')}")
            print(f"      数量: {fill.get('fillSz')} 张 @ ${float(fill.get('fillPx', 0)):,.2f}")
            print(f"      P&L: {fill_pnl:+.8f}")
    
    # ===== 5. ⭐⭐⭐ 增量累加（关键！）=====
    # 只累加新填充的 P&L，避免重新遍历整个字典
    total_pnl = previous_realized_pnl + new_pnl
    
    # ===== 6. 获取最新的 fillTime =====
    if perp_pnl_dict:
        last_trade_id = list(perp_pnl_dict.keys())[-1]
        last_fill_time = perp_pnl_dict[last_trade_id]['fillTime']
    else:
        last_fill_time = query_start_time_ms
    
    # ===== 7. 打印汇总 =====
    if not silent:
        print("\n" + "="*70)
        print("📊 汇总统计:")
        print("="*70)
        print(f"   总成交笔数: {len(perp_pnl_dict)}")
        print(f"   本次新增: {len(new_fills)} 笔")
        print(f"   本次新增P&L: {new_pnl:+.8f}")
        print(f"   累积总P&L: {total_pnl:+.8f}")
        print(f"   最新成交时间: {last_fill_time} ({_ms_to_datetime(int(last_fill_time))})")
        print("="*70)
    
    return total_pnl, last_fill_time


def _ms_to_datetime(ms: int) -> str:
    """将毫秒时间戳转换为可读日期"""
    return datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M:%S')


def print_pnl_dict_summary(perp_pnl_dict: dict):
    """打印 perp_pnl_dict 的详细信息（调试用）"""
    print("\n" + "="*70)
    print("📋 成交记录详情（按时间排序）:")
    print("="*70)
    
    for idx, (trade_id, data) in enumerate(perp_pnl_dict.items(), 1):
        print(f"\n#{idx} TradeID: {trade_id}")
        print(f"   时间: {_ms_to_datetime(int(data['fillTime']))}")
        print(f"   订单: {data['orderId']}")
        print(f"   方向: {data['side']}")
        print(f"   数量: {data['fillSz']} 张 @ ${float(data['fillPx']):,.2f}")
        print(f"   P&L: {data['fillPnl']:+.8f}")
        print(f"   手续费: {data['fee']:+.8f}")


# ===== 使用示例 =====
if __name__ == "__main__":
    instrument = "ETH-USD-SWAP"
    
    # 初始化字典（线程安全的话可以用你的 ThreadSafeMap）
    perp_pnl_dict = {}
    
    print("🚀 第一次查询（从指定时间开始）")
    print("="*70)
    
    total_pnl, last_fill_time = get_perp_realized_pnl(
        instrument=instrument,
        start_time="2025-11-18 00:00:00",
        perp_pnl_dict=perp_pnl_dict
    )
    
    print(f"\n返回值:")
    print(f"   total_pnl: {total_pnl:+.8f}")
    print(f"   last_fill_time: {last_fill_time}")
    
    # 打印详细记录
    print_pnl_dict_summary(perp_pnl_dict)
    
    # ===== 模拟第二次增量查询 =====
    print("\n\n" + "="*70)
    print("🔄 第二次查询（增量更新）")
    print("="*70)
    
    # 这次不需要传 start_time，会自动使用 last_fill_time
    # ⭐ 传入上次的 total_pnl 作为 previous_realized_pnl
    total_pnl, last_fill_time = get_perp_realized_pnl(
        instrument=instrument,
        start_time="2025-11-18 00:00:00",  # 会被忽略，因为 dict 不为空
        perp_pnl_dict=perp_pnl_dict,
        previous_realized_pnl=total_pnl  # ⭐ 传入上次的结果
    )
    
    print(f"\n返回值:")
    print(f"   total_pnl: {total_pnl:+.8f}")
    print(f"   last_fill_time: {last_fill_time}")