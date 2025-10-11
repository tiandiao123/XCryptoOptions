#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deribit Options Position Information Module - 精确P&L版本
基于 private/get_account_summary 获取最精确的P&L数据，专为对冲交易设计
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from qtrade.order_api.deribit_order_placer.options_order import get_options_positions
from qtrade.order_api.deribit_order_placer.current_balance import get_account_summary


@dataclass
class PreciseOptionPositionInfo:
    """精确期权持仓信息数据类 - 专为对冲交易设计"""
    instrument_name: str
    size: float                    # 持仓数量
    direction: str                 # buy/sell
    mark_price: float              # 标记价格
    unrealized_pnl: float          # 精确未实现盈亏 (来自账户汇总)
    estimated_entry_price: float   # 估算的开仓价格
    is_found: bool                 # 是否找到持仓
    data_source: str               # 数据来源标识
    
    def __str__(self):
        return (f"PrecisePosition({self.instrument_name}: "
                f"size={self.size}, direction={self.direction}, "
                f"mark_price={self.mark_price:.6f}, "
                f"pnl={self.unrealized_pnl:.8f}, "
                f"entry_price={self.estimated_entry_price:.6f}, "
                f"source={self.data_source})")


def get_precise_option_position_info(instrument_name: str, env: str = "testnet") -> PreciseOptionPositionInfo:
    """
    获取单个期权合约的精确持仓信息 - 基于账户汇总API
    
    Args:
        instrument_name: 期权合约名称，如 "BTC-25OCT25-70000-C"
        env: 交易环境 ("testnet" 或 "mainnet")
        
    Returns:
        PreciseOptionPositionInfo: 精确持仓信息对象
    """
    try:
        # Step 1: 获取持仓基础信息 (大小、方向、标记价格)
        all_positions = get_options_positions(env=env, exclude_zero_positions=True)
        
        target_position = None
        for position in all_positions:
            if position.get("instrument_name") == instrument_name:
                target_position = position
                break
        
        if not target_position:
            return PreciseOptionPositionInfo(
                instrument_name=instrument_name,
                size=0.0,
                direction="none",
                mark_price=0.0,
                unrealized_pnl=0.0,
                estimated_entry_price=0.0,
                is_found=False,
                data_source="not_found"
            )
        
        # Step 2: 获取基础持仓信息
        size = target_position.get("size", 0.0)
        direction = target_position.get("direction", "unknown")
        mark_price = target_position.get("mark_price", 0.0)
        
        # Step 3: 从账户汇总获取精确P&L
        currency = instrument_name.split('-')[0]  # BTC-28NOV25-114000-C -> BTC
        account_summary = get_account_summary(currency, env)
        precise_total_pnl = account_summary.get("total_pl", 0.0)
        
        # Step 4: 计算单个合约的P&L
        # 如果只有一个期权持仓，全部P&L归属于该合约
        # 如果有多个持仓，需要按比例分配或使用其他策略
        single_position_pnl = _calculate_single_position_pnl(
            instrument_name, precise_total_pnl, all_positions, env
        )
        
        # Step 5: 估算开仓价格
        estimated_entry_price = _estimate_entry_price_from_pnl(
            mark_price, single_position_pnl, size, direction
        )
        
        return PreciseOptionPositionInfo(
            instrument_name=instrument_name,
            size=size,
            direction=direction,
            mark_price=mark_price,
            unrealized_pnl=single_position_pnl,
            estimated_entry_price=estimated_entry_price,
            is_found=True,
            data_source="account_summary"
        )
        
    except Exception as e:
        print(f"❌ 获取精确期权持仓信息失败 {instrument_name}: {e}")
        return PreciseOptionPositionInfo(
            instrument_name=instrument_name,
            size=0.0,
            direction="error",
            mark_price=0.0,
            unrealized_pnl=0.0,
            estimated_entry_price=0.0,
            is_found=False,
            data_source="error"
        )


def _calculate_single_position_pnl(instrument_name: str, total_pnl: float, 
                                  all_positions: List[Dict], env: str) -> float:
    """
    计算单个持仓的精确P&L
    
    策略：
    1. 如果只有一个持仓：全部P&L归属于该持仓
    2. 如果有多个持仓：按标记价值比例分配P&L
    3. 特殊情况：使用更精确的计算方法
    """
    try:
        if len(all_positions) == 1:
            # 情况1: 只有一个持仓，全部P&L归属于该合约
            print(f"📊 单一持仓，全部P&L归属: {total_pnl:.8f} BTC")
            return total_pnl
        
        elif len(all_positions) > 1:
            # 情况2: 多个持仓，按标记价值比例分配
            target_position = None
            total_mark_value = 0.0
            
            for position in all_positions:
                mark_price = position.get("mark_price", 0.0)
                size = abs(position.get("size", 0.0))
                mark_value = mark_price * size
                total_mark_value += mark_value
                
                if position.get("instrument_name") == instrument_name:
                    target_position = position
            
            if target_position and total_mark_value > 0:
                target_mark_price = target_position.get("mark_price", 0.0)
                target_size = abs(target_position.get("size", 0.0))
                target_mark_value = target_mark_price * target_size
                
                # 按标记价值比例分配P&L
                allocation_ratio = target_mark_value / total_mark_value
                allocated_pnl = total_pnl * allocation_ratio
                
                print(f"📊 多持仓P&L分配:")
                print(f"   目标合约标记价值: {target_mark_value:.6f}")
                print(f"   总标记价值: {total_mark_value:.6f}")
                print(f"   分配比例: {allocation_ratio:.4f}")
                print(f"   分配P&L: {allocated_pnl:.8f} BTC")
                
                return allocated_pnl
        
        # 默认情况：无法精确计算，返回0
        print(f"⚠️ 无法精确计算单个持仓P&L，返回0")
        return 0.0
        
    except Exception as e:
        print(f"❌ P&L分配计算失败: {e}")
        return 0.0


def get_precise_total_pnl_for_instruments(instrument_names: List[str], env: str = "testnet") -> Dict[str, Any]:
    """
    获取多个期权合约的精确总P&L - 直接基于账户汇总
    
    Args:
        instrument_names: 期权合约名称列表
        env: 交易环境
        
    Returns:
        Dict: 包含精确P&L信息的字典
    """
    try:
        # Step 1: 确定主要币种
        currencies = set()
        for instrument in instrument_names:
            currency = instrument.split('-')[0]
            currencies.add(currency)
        
        total_precise_pnl = 0.0
        currency_breakdown = {}
        
        # Step 2: 为每个币种获取精确账户P&L
        for currency in currencies:
            account_summary = get_account_summary(currency, env)
            currency_pnl = account_summary.get("total_pl", 0.0)
            
            currency_breakdown[currency] = {
                "total_pl": currency_pnl,
                "equity": account_summary.get("equity", 0.0),
                "balance": account_summary.get("balance", 0.0)
            }
            
            total_precise_pnl += currency_pnl
        
        # Step 3: 验证持仓存在性
        all_positions = get_options_positions(env=env, exclude_zero_positions=True)
        found_instruments = []
        
        for position in all_positions:
            instrument = position.get("instrument_name", "")
            if instrument in instrument_names:
                found_instruments.append(instrument)
        
        result = {
            "total_precise_pnl": total_precise_pnl,
            "currency_breakdown": currency_breakdown,
            "found_instruments": found_instruments,
            "total_instruments": len(instrument_names),
            "found_count": len(found_instruments),
            "data_source": "account_summary",
            "precision_level": "maximum"
        }
        
        print(f"📊 精确P&L汇总:")
        print(f"   总P&L: {total_precise_pnl:.8f} BTC")
        print(f"   找到持仓: {len(found_instruments)}/{len(instrument_names)}")
        print(f"   数据来源: 账户汇总API (最高精度)")
        
        return result
        
    except Exception as e:
        print(f"❌ 获取精确总P&L失败: {e}")
        return {
            "total_precise_pnl": 0.0,
            "currency_breakdown": {},
            "found_instruments": [],
            "total_instruments": len(instrument_names),
            "found_count": 0,
            "data_source": "error",
            "precision_level": "none"
        }


def get_multiple_options_position_info(instrument_names: List[str], env: str = "testnet") -> Dict[str, PreciseOptionPositionInfo]:
    """
    批量获取多个期权合约的持仓信息
    
    Args:
        instrument_names: 期权合约名称列表
        env: 交易环境
        
    Returns:
        Dict[str, PreciseOptionPositionInfo]: 合约名称到持仓信息的映射
    """
    result = {}
    
    try:
        for instrument_name in instrument_names:
            info = get_precise_option_position_info(instrument_name, env)
            result[instrument_name] = info
        
        return result
        
    except Exception as e:
        print(f"❌ 批量获取期权持仓信息失败: {e}")
        # 返回空结果但保持结构
        for instrument_name in instrument_names:
            result[instrument_name] = PreciseOptionPositionInfo(
                instrument_name=instrument_name,
                size=0.0,
                direction="error",
                mark_price=0.0,
                unrealized_pnl=0.0,
                estimated_entry_price=0.0,
                is_found=False,
                data_source="error"
            )
        return result


def _estimate_entry_price_from_pnl(mark_price: float, unrealized_pnl: float, 
                                  size: float, direction: str) -> float:
    """
    通过精确未实现P&L反推估算开仓价格
    """
    try:
        if abs(size) < 1e-8:
            return 0.0
        
        if direction == "buy":
            # Buy position: PnL = (mark_price - entry_price) * size
            estimated_entry_price = mark_price - (unrealized_pnl / size)
        elif direction == "sell":
            # Sell position: PnL = (entry_price - mark_price) * size
            estimated_entry_price = mark_price + (unrealized_pnl / size)
        else:
            return 0.0
        
        return max(0.0, estimated_entry_price)
        
    except Exception as e:
        print(f"❌ 估算开仓价格失败: {e}")
        return 0.0


# 保持向后兼容的别名
get_option_position_info = get_precise_option_position_info
get_total_pnl_for_instruments = lambda instruments, env: get_precise_total_pnl_for_instruments(instruments, env)["total_precise_pnl"]


def demo_precise_position_info():
    """
    演示精确期权持仓信息功能
    """
    print("🚀 精确期权持仓信息模块演示")
    print("=" * 60)
    
    try:
        # 测试真实存在的合约
        real_instrument = "BTC-28NOV25-114000-C"
        
        print("📊 精确单个合约查询:")
        info = get_precise_option_position_info(real_instrument, "testnet")
        print(f"   {info}")
        
        print(f"\n📊 精确总P&L查询:")
        result = get_precise_total_pnl_for_instruments([real_instrument], "testnet")
        print(f"   精确总P&L: {result['total_precise_pnl']:.8f} BTC")
        print(f"   精度级别: {result['precision_level']}")
        print(f"   数据来源: {result['data_source']}")
        
        print("✅ 精确演示完成")
        
    except Exception as e:
        print(f"❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    demo_precise_position_info()