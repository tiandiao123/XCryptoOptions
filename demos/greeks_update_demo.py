#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Greeks更新功能演示脚本
展示如何在实际交易中使用update_straddle_opportunity函数
"""

import sys
import time
sys.path.append('/home/ubuntu/options_trading')

from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import (
    SellingStraddleFinder,
    update_straddle_opportunity
)


def demo_real_time_greeks_monitoring():
    """演示实时Greeks监控"""
    print("🚀 实时Greeks监控演示")
    print("=" * 60)
    
    try:
        # 1. 初始化Straddle寻找器
        config_path = "/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml"
        finder = SellingStraddleFinder(config_path=config_path, currency="BTC", env="testnet")
        
        # 2. 寻找Straddle机会
        print("🔍 寻找Straddle机会...")
        opportunities = finder.find_selling_straddle_opportunities()
        
        if not opportunities:
            print("❌ 未找到Straddle机会")
            return
        
        # 3. 选择第一个机会进行监控
        selected_opportunity = opportunities[0]
        print(f"\n📊 选择监控的Straddle:")
        print(f"   Call: {selected_opportunity.call_option.symbol}")
        print(f"   Put: {selected_opportunity.put_option.symbol}")
        print(f"   执行价: ${selected_opportunity.strike_price:,.0f}")
        
        # 4. 实时监控循环
        print(f"\n🔄 开始实时监控 (按Ctrl+C停止)...")
        print(f"{'时间':<10} {'Net Delta':<12} {'Total Gamma':<12} {'Total Theta':<12} {'IV Premium':<10}")
        print("-" * 65)
        
        iteration = 0
        max_iterations = 10  # 限制演示次数
        
        while iteration < max_iterations:
            try:
                # 获取当前时间
                current_time = time.strftime("%H:%M:%S")
                
                # 更新Net Delta（快速更新）
                current_net_delta = update_straddle_opportunity(
                    opportunity=selected_opportunity,
                    realized_vol=0.35,  # 可以从实时数据源获取
                    net_delta_only=True,
                    env="testnet"
                )
                
                # 每3次迭代进行一次完整更新
                if iteration % 3 == 0:
                    updated_opportunity = update_straddle_opportunity(
                        opportunity=selected_opportunity,
                        realized_vol=0.35,
                        net_delta_only=False,
                        env="testnet"
                    )
                    
                    # 显示完整信息
                    print(f"{current_time:<10} {current_net_delta:<12.4f} {updated_opportunity.total_gamma:<12.6f} {updated_opportunity.total_theta:<12.2f} {updated_opportunity.iv_premium_pct:<10.1f}%")
                else:
                    # 只显示Net Delta
                    print(f"{current_time:<10} {current_net_delta:<12.4f} {'---':<12} {'---':<12} {'---':<10}")
                
                iteration += 1
                
                # 等待10秒（实际应用中可以根据需要调整）
                if iteration < max_iterations:
                    time.sleep(10)
                
            except KeyboardInterrupt:
                print(f"\n⏹️ 用户停止监控")
                break
            except Exception as e:
                print(f"\n❌ 监控出错: {e}")
                break
        
        print(f"\n✅ 演示完成!")
        
    except Exception as e:
        print(f"❌ 演示失败: {e}")


def demo_risk_management_integration():
    """演示风险管理集成"""
    print("\n🛡️ 风险管理集成演示")
    print("=" * 60)
    
    try:
        # 模拟一个已有的Straddle持仓
        from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.atm_options_filter import OptionData
        from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import StraddleOpportunity
        
        # 创建模拟持仓
        call_option = OptionData(
            symbol="BTC-28NOV25-122000-C",
            strike=122000.0,
            expiry="2025-11-28",
            days_to_expiry=18,
            option_type="C",
            iv=0.39, bid=0.0585, ask=0.0595, mid_price=0.0590,
            delta=0.50, net_delta=0.441, gamma=0.00001,
            vega=100.0, theta=-5.0, rho=10.0, open_interest=100
        )
        
        put_option = OptionData(
            symbol="BTC-28NOV25-122000-P",
            strike=122000.0,
            expiry="2025-11-28",
            days_to_expiry=18,
            option_type="P",
            iv=0.395, bid=0.0580, ask=0.0600, mid_price=0.0590,
            delta=-0.50, net_delta=-0.559, gamma=0.00001,
            vega=100.0, theta=-5.0, rho=-10.0, open_interest=80
        )
        
        position = StraddleOpportunity(
            call_option=call_option,
            put_option=put_option,
            realized_vol=0.35,
            spot_price=121316.13
        )
        
        print(f"📊 模拟持仓: {position.call_option.symbol} Straddle")
        print(f"   初始Net Delta: {position.net_delta_adjusted:.4f}")
        
        # 风险阈值设置
        DELTA_RISK_THRESHOLD = 0.1  # Net Delta超过0.1时需要对冲
        GAMMA_RISK_THRESHOLD = 0.001  # Gamma风险阈值
        
        print(f"\n🎯 风险阈值设置:")
        print(f"   Delta风险阈值: ±{DELTA_RISK_THRESHOLD}")
        print(f"   Gamma风险阈值: {GAMMA_RISK_THRESHOLD}")
        
        # 模拟风险检查
        print(f"\n🔍 进行风险检查...")
        
        # 获取最新Greeks
        updated_net_delta = update_straddle_opportunity(
            opportunity=position,
            realized_vol=0.35,
            net_delta_only=True,
            env="testnet"
        )
        
        # 风险评估
        delta_risk = abs(updated_net_delta)
        
        print(f"📊 风险评估结果:")
        print(f"   当前Net Delta: {updated_net_delta:.4f}")
        print(f"   Delta风险水平: {delta_risk:.4f}")
        
        if delta_risk > DELTA_RISK_THRESHOLD:
            print(f"⚠️ Delta风险超标! 需要进行对冲")
            print(f"   建议对冲数量: {-updated_net_delta:.4f} Delta")
            print(f"   对冲方向: {'买入' if updated_net_delta < 0 else '卖出'}现货")
        else:
            print(f"✅ Delta风险在可控范围内")
        
        # 获取完整Greeks进行更详细的风险分析
        print(f"\n🔄 获取完整Greeks数据进行深度风险分析...")
        updated_position = update_straddle_opportunity(
            opportunity=position,
            realized_vol=0.35,
            net_delta_only=False,
            env="testnet"
        )
        
        print(f"📈 完整风险指标:")
        print(f"   Net Delta: {updated_position.net_delta_adjusted:.4f}")
        print(f"   Total Gamma: {updated_position.total_gamma:.6f}")
        print(f"   Total Theta: {updated_position.total_theta:.2f}")
        print(f"   Total Vega: {updated_position.total_vega:.2f}")
        print(f"   IV Premium: {updated_position.iv_premium_pct:+.1f}%")
        
        # Gamma风险评估
        gamma_risk = abs(updated_position.total_gamma)
        if gamma_risk > GAMMA_RISK_THRESHOLD:
            print(f"⚠️ Gamma风险较高: {gamma_risk:.6f}")
        else:
            print(f"✅ Gamma风险可控: {gamma_risk:.6f}")
        
        # Theta收益评估
        daily_theta = updated_position.total_theta
        print(f"💰 预期日收益 (Theta): {daily_theta:.4f} BTC")
        
        print(f"\n✅ 风险管理演示完成!")
        
    except Exception as e:
        print(f"❌ 风险管理演示失败: {e}")


def main():
    """主演示函数"""
    print("🎯 Greeks更新功能实际应用演示")
    print("=" * 80)
    
    # 演示1: 实时监控
    demo_real_time_greeks_monitoring()
    
    # 演示2: 风险管理集成
    demo_risk_management_integration()
    
    print(f"\n" + "=" * 80)
    print(f"🎉 演示完成!")
    print(f"\n📚 关键功能总结:")
    print(f"   ✅ update_straddle_opportunity() 函数已实现")
    print(f"   ✅ 支持net_delta_only=True快速更新")
    print(f"   ✅ 支持net_delta_only=False完整更新")
    print(f"   ✅ 实时获取Deribit API数据")
    print(f"   ✅ 适用于风险管理和实时监控")
    
    print(f"\n🚀 下一步建议:")
    print(f"   1. 集成到RiskManager类中")
    print(f"   2. 添加到TradingEngine的风险检查循环")
    print(f"   3. 设置合理的更新频率和API限流")
    print(f"   4. 添加异常处理和重试机制")


if __name__ == "__main__":
    main()
