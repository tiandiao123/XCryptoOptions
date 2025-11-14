#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETH 永续合约开仓/平仓测试脚本

测试流程:
1. 开仓: 做空 0.05 ETH (卖出)
2. 等待 100 秒
3. 平仓: 买回 0.05 ETH
"""

import time
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from qtrade.order_api.okx.func_call.perp.perp_order import (
    place_inverse_perp_order_crypto_notional,  # 新的通用函数名
    get_current_btc_price
)


def print_separator(title=""):
    """打印分隔线"""
    print("\n" + "=" * 70)
    if title:
        print(f"  {title}")
        print("=" * 70)
    print()


def main():
    """主测试流程"""
    
    # ==================== 配置参数 ====================
    INSTRUMENT = "ETH-USD-SWAP"
    ETH_NOTIONAL = 0.05  # 0.05 ETH
    WAIT_TIME = 100  # 等待时间（秒）
    USE_SIMULATED = False  # True=模拟盘, False=实盘
    
    env_str = "🟡 模拟盘" if USE_SIMULATED else "🔴 实盘"
    
    print_separator("ETH 永续合约交易测试")
    print(f"📊 交易参数:")
    print(f"   合约: {INSTRUMENT}")
    print(f"   数量: {ETH_NOTIONAL} ETH")
    print(f"   环境: {env_str}")
    print(f"   等待时间: {WAIT_TIME} 秒")
    
    # 获取当前价格
    current_price = get_current_btc_price(INSTRUMENT)
    if not current_price:
        print("❌ 无法获取当前价格，退出")
        return
    
    print(f"\n💰 当前 ETH 价格: ${current_price:,.2f}")
    print(f"💵 名义价值: ${ETH_NOTIONAL * current_price:,.2f} USD")
    
    input("\n⏸️  按 Enter 继续开仓...")
    
    # ==================== 步骤 1: 开仓 (做空) ====================
    print_separator("步骤 1: 开仓 - 做空 0.05 ETH")
    
    try:
        print("📝 提交卖出订单...")
        open_order_id, open_result = place_inverse_perp_order_crypto_notional(
            instId=INSTRUMENT,
            side="sell",  # 做空 = 卖出
            crypto_notional=ETH_NOTIONAL,
            ordType="market",
            simulated=USE_SIMULATED
        )
        
        if open_order_id:
            print(f"\n✅ 开仓成功!")
            print(f"   订单ID: {open_order_id}")
            print(f"   方向: 做空 (Sell)")
            print(f"   数量: {ETH_NOTIONAL} ETH")
        else:
            print(f"\n❌ 开仓失败: {open_result}")
            return
            
    except Exception as e:
        print(f"\n❌ 开仓出错: {e}")
        return
    
    # ==================== 步骤 2: 等待 ====================
    print_separator(f"步骤 2: 等待 {WAIT_TIME} 秒")
    
    print("⏳ 等待中...")
    for remaining in range(WAIT_TIME, 0, -10):
        print(f"   剩余: {remaining} 秒...", end="\r")
        time.sleep(min(10, remaining))
    
    print("\n✅ 等待完成!")
    
    # ==================== 步骤 3: 平仓 (买回) ====================
    print_separator("步骤 3: 平仓 - 买回 0.05 ETH")
    
    try:
        print("📝 提交买入订单 (平仓)...")
        close_order_id, close_result = place_inverse_perp_order_crypto_notional(
            instId=INSTRUMENT,
            side="buy",  # 平仓空单 = 买入
            crypto_notional=ETH_NOTIONAL,
            ordType="market",
            simulated=USE_SIMULATED
        )
        
        if close_order_id:
            print(f"\n✅ 平仓成功!")
            print(f"   订单ID: {close_order_id}")
            print(f"   方向: 买入 (平仓)")
            print(f"   数量: {ETH_NOTIONAL} ETH")
        else:
            print(f"\n❌ 平仓失败: {close_result}")
            return
            
    except Exception as e:
        print(f"\n❌ 平仓出错: {e}")
        return
    
    # ==================== 完成 ====================
    print_separator("测试完成")
    print("✅ 交易流程完成!")
    print(f"\n📊 交易摘要:")
    print(f"   开仓订单: {open_order_id}")
    print(f"   平仓订单: {close_order_id}")
    print(f"   环境: {env_str}")
    print(f"\n💡 提示: 查看 OKX 网页查看实际 P&L")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
    except Exception as e:
        print(f"\n\n❌ 脚本出错: {e}")
        import traceback
        traceback.print_exc()

