# -*- coding: utf-8 -*-
"""
Gamma Scalping - Selling Straddle Finder
基于实时数据寻找Selling Straddle机会
整合EWMA波动率跟踪器和Deribit期权数据
"""

import sys
import numpy as np
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import yaml
from pathlib import Path

# 添加项目路径
sys.path.append('/home/ubuntu/options_trading')

from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.atm_options_filter import (
    get_straddle_atm_options, OptionData
)
from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.ewma_vol_tracker import RealDataEWMAVolTracker


@dataclass
class StraddleOpportunity:
    """Selling Straddle机会数据结构"""
    call_option: OptionData
    put_option: OptionData
    strategy_type: str = "short_straddle"
    
    # 波动率分析
    avg_iv: float = 0.0
    realized_vol: float = 0.0
    iv_premium: float = 0.0  # IV - RV
    iv_premium_pct: float = 0.0  # (IV - RV) / RV * 100
    
    # 价格分析
    total_premium: float = 0.0
    call_premium: float = 0.0
    put_premium: float = 0.0
    
    # 风险分析
    net_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta: float = 0.0
    total_vega: float = 0.0
    
    # 市场信息
    spot_price: float = 0.0
    strike_price: float = 0.0
    days_to_expiry: int = 0
    
    # 评分
    score: float = 0.0
    signal_strength: str = "weak"
    
    def __post_init__(self):
        """计算衍生字段"""
        # 基础价格信息
        self.call_premium = self.call_option.mid_price
        self.put_premium = self.put_option.mid_price
        self.total_premium = self.call_premium + self.put_premium
        
        # 波动率分析
        self.avg_iv = (self.call_option.iv + self.put_option.iv) / 2
        if self.realized_vol > 0:
            self.iv_premium = self.avg_iv - self.realized_vol
            self.iv_premium_pct = (self.iv_premium / self.realized_vol) * 100
        
        # 希腊字母
        self.net_delta = self.call_option.delta + self.put_option.delta  # 传统净Delta
        self.net_delta_adjusted = self.call_option.net_delta + self.put_option.net_delta  # 调整后净Delta
        self.total_gamma = self.call_option.gamma + self.put_option.gamma
        self.total_theta = self.call_option.theta + self.put_option.theta
        self.total_vega = self.call_option.vega + self.put_option.vega
        
        # 基础信息
        self.strike_price = self.call_option.strike
        self.days_to_expiry = self.call_option.days_to_expiry
    
    def calculate_score(self, config: Dict[str, Any]) -> float:
        """
        计算Straddle机会评分
        
        Args:
            config: 配置参数
            
        Returns:
            评分 (0-100)
        """
        weights = config.get("scoring_weights", {})
        iv_weight = weights.get("iv_weight", 0.7)
        premium_weight = weights.get("premium_weight", 0.3)
        
        # IV溢价评分 (0-100)
        iv_score = min(100, max(0, self.iv_premium_pct * 2))  # 50%溢价 = 100分
        
        # 权利金评分 (归一化到0-100)
        premium_score = min(100, self.total_premium * 1000)  # 0.1 BTC = 100分
        
        # 综合评分
        self.score = iv_score * iv_weight + premium_score * premium_weight
        
        # 确定信号强度
        thresholds = config.get("signal_strength_thresholds", {})
        if self.iv_premium_pct >= thresholds.get("strong_iv_premium", 12):
            self.signal_strength = "strong"
        elif self.iv_premium_pct >= thresholds.get("moderate_iv_premium", 8):
            self.signal_strength = "moderate"
        else:
            self.signal_strength = "weak"
        
        return self.score
    
    def print_summary(self):
        """打印机会摘要"""
        print(f"\n🎯 Selling Straddle机会 ({self.signal_strength.upper()})")
        print(f"   执行价: ${self.strike_price:,.0f}")
        print(f"   到期: {self.days_to_expiry}天")
        print(f"   总权利金: {self.total_premium:.4f} BTC")
        print(f"   IV溢价: {self.iv_premium_pct:+.1f}% (IV={self.avg_iv:.1%}, RV={self.realized_vol:.1%})")
        print(f"   净Delta: {self.net_delta:.3f}")
        print(f"   调整净Delta: {self.net_delta_adjusted:.3f}")
        print(f"   总Gamma: {self.total_gamma:.3f}")
        print(f"   总Theta: {self.total_theta:.3f}")
        print(f"   评分: {self.score:.1f}/100")
    
    def print_detailed(self):
        """打印详细信息"""
        self.print_summary()
        print(f"\n📊 详细信息:")
        print(f"   🔵 Call: {self.call_option.symbol}")
        print(f"      价格: Bid={self.call_option.bid:.4f}, Ask={self.call_option.ask:.4f}, Mid={self.call_premium:.4f}")
        print(f"      希腊字母: Δ={self.call_option.delta:.3f}, Net Δ={self.call_option.net_delta:.3f}, Γ={self.call_option.gamma:.3f}, Θ={self.call_option.theta:.3f}")
        print(f"      IV: {self.call_option.iv:.1%}, 持仓量: {self.call_option.open_interest}")
        
        print(f"   🔴 Put: {self.put_option.symbol}")
        print(f"      价格: Bid={self.put_option.bid:.4f}, Ask={self.put_option.ask:.4f}, Mid={self.put_premium:.4f}")
        print(f"      希腊字母: Δ={self.put_option.delta:.3f}, Net Δ={self.put_option.net_delta:.3f}, Γ={self.put_option.gamma:.3f}, Θ={self.put_option.theta:.3f}")
        print(f"      IV: {self.put_option.iv:.1%}, 持仓量: {self.put_option.open_interest}")


class SellingStraddleFinder:
    """Selling Straddle机会寻找器"""
    
    def __init__(self, config_path: str, currency: str = "BTC", env: str = "testnet"):
        """
        初始化Selling Straddle寻找器
        
        Args:
            config_path: 配置文件路径
            currency: 币种
            env: 环境 (testnet/mainnet)
        """
        self.currency = currency
        self.env = env
        self.config = self._load_config(config_path)

        print(self.config)
        print(f"self.config['volatility_criteria']: {self.config['volatility_criteria']}")
        
        # 初始化EWMA波动率跟踪器
        self.vol_tracker = self._initialize_vol_tracker()
        
        print(f"🚀 初始化Selling Straddle寻找器")
        print(f"   币种: {currency}")
        print(f"   环境: {env}")
        print(f"   配置: {config_path}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"✅ 配置文件加载成功: {config_path}")
        return config
    
    def _initialize_vol_tracker(self) -> Optional[RealDataEWMAVolTracker]:
        """初始化波动率跟踪器"""

        vol_config = self.config.get("vol_tracker_config", {})
        
        tracker = RealDataEWMAVolTracker(
            symbol=f"{self.currency}USDT",
            interval=vol_config.get("historical_data_interval_minutes", "30m"),
            window_size=vol_config.get("window_size", 96),
            ewma_lambda=vol_config.get("ewma_lambda", 0.94)
        )
        
        if tracker.is_initialized:
            print(f"✅ EWMA波动率跟踪器初始化成功")
            return tracker
        else:
            print(f"❌ EWMA波动率跟踪器初始化失败")
            return None

    
    def get_realized_volatility(self) -> Optional[float]:
        """获取当前已实现波动率"""
        if not self.vol_tracker:
            return None
    
        result = self.vol_tracker.predict()
        if result['success']:
            return result['realized_vol_annualized']
        else:
            print(f"⚠️ 获取已实现波动率失败: {result['error']}")
            return None

    
    def find_selling_straddle_opportunities(self) -> List[StraddleOpportunity]:
        """
        寻找Selling Straddle机会
        
        Returns:
            Selling Straddle机会列表
        """
        print(f"\n🔍 寻找{self.currency} Selling Straddle机会...")
        
        # 1. 获取已实现波动率
        realized_vol = self.get_realized_volatility()
        if realized_vol is None:
            print("❌ 无法获取已实现波动率，终止搜索")
            return []
        
        print(f"📊 当前已实现波动率: {realized_vol:.1%}")
        
        # 2. 获取ATM期权
        atm_options = get_straddle_atm_options(self.config, self.currency, self.env)
        if not atm_options:
            print("❌ 未找到ATM期权")
            return []
        
        print(f"📊 获取到{len(atm_options)}个ATM期权")
        
        # 3. 筛选符合时间条件的期权
        time_filtered_options = self._filter_by_time_criteria(atm_options)
        if not time_filtered_options:
            print("❌ 没有符合时间条件的期权")
            return []
        
        print(f"📊 时间筛选后剩余{len(time_filtered_options)}个期权")


        for option in time_filtered_options:
            option.print_detailed()
        
        # 4. 寻找Straddle配对
        straddle_pairs = self._find_straddle_pairs(time_filtered_options)
        if not straddle_pairs:
            print("❌ 未找到有效的Straddle配对")
            return []
        
        print(f"📊 找到{len(straddle_pairs)}个Straddle配对")

        # 5. 筛选符合IV条件的机会
        opportunities = self._filter_by_iv_criteria(straddle_pairs, realized_vol)
        if not opportunities:
            print("❌ 没有符合IV条件的机会")
            return []
        
        print(f"📊 IV筛选后剩余{len(opportunities)}个机会")

        for i, straddle_opt_pair in enumerate(opportunities, 1):
            print(f" =================={i}-th pair==================")
            straddle_opt_pair.print_detailed()
        
        
        # 6. 计算评分并排序
        for opp in opportunities:
            opp.calculate_score(self.config)
        
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        # 7. 限制返回数量
        max_results = self.config.get("search_config", {}).get("max_results", 5)
        opportunities = opportunities[:max_results]
        
        print(f"✅ 找到{len(opportunities)}个Selling Straddle机会")
        
        return opportunities
    
    def _filter_by_time_criteria(self, options: List[OptionData]) -> List[OptionData]:
        """根据时间条件筛选期权"""
        time_criteria = self.config.get("time_criteria", {})
        min_days = time_criteria.get("min_days_to_expiry", 7)
        max_days = time_criteria.get("max_days_to_expiry", 25)
        
        filtered_options = [
            opt for opt in options
            if min_days <= opt.days_to_expiry <= max_days
        ]
        
        return filtered_options
    
    def _find_straddle_pairs(self, options: List[OptionData]) -> List[Tuple[OptionData, OptionData]]:
        """寻找Call-Put配对"""
        # 按期权类型分组
        calls = [opt for opt in options if opt.option_type == 'C']
        puts = [opt for opt in options if opt.option_type == 'P']
        
        if not calls or not puts:
            return []
        
        pairs = []
        pairing_criteria = self.config.get("pairing_criteria", {})
        strike_tolerance = pairing_criteria.get("strike_match_tolerance", 0.005)
        expiry_tolerance = pairing_criteria.get("expiry_match_tolerance_days", 1)
        
        for call in calls:
            for put in puts:
                # 检查执行价匹配
                strike_diff_pct = abs(call.strike - put.strike) / call.strike
                if strike_diff_pct > strike_tolerance:
                    continue
                
                # 检查到期日匹配 - Straddle必须完全相同的到期日
                if call.days_to_expiry != put.days_to_expiry:
                    continue
                
                # 检查数据有效性
                if not self._is_valid_pair(call, put):
                    continue
                
                pairs.append((call, put))
        
        return pairs
    
    def _is_valid_pair(self, call: OptionData, put: OptionData) -> bool:
        """检查配对是否有效"""
        pairing_criteria = self.config.get("pairing_criteria", {})
        min_iv = pairing_criteria.get("min_iv", 0.01)
        max_iv = pairing_criteria.get("max_iv", 3.0)
        min_option_price = pairing_criteria.get("min_option_price", 0.0001)
        
        # IV检查
        if call.iv < min_iv or call.iv > max_iv:
            return False
        if put.iv < min_iv or put.iv > max_iv:
            return False
        
        # 价格检查
        if call.mid_price < min_option_price or put.mid_price < min_option_price:
            return False
        
        return True
    
    def _filter_by_iv_criteria(self, pairs: List[Tuple[OptionData, OptionData]], 
                              realized_vol: float) -> List[StraddleOpportunity]:
        """根据IV条件筛选机会"""
        min_iv_premium = self.config['volatility_criteria'].get("min_iv_premium", 0.05)
        opportunities = []

        for call, put in pairs:
            avg_iv = (call.iv + put.iv) / 2
            iv_premium = avg_iv - realized_vol
            
            # 检查IV溢价是否足够
            if iv_premium >= min_iv_premium:
                opportunity = StraddleOpportunity(
                    call_option=call,
                    put_option=put,
                    realized_vol=realized_vol
                )
                opportunities.append(opportunity)
        
        return opportunities
    
    def display_opportunities(self, opportunities: List[StraddleOpportunity], 
                            detailed: bool = False):
        """显示找到的机会"""
        if not opportunities:
            print("❌ 未找到Selling Straddle机会")
            return
        
        print(f"\n🎯 找到{len(opportunities)}个Selling Straddle机会:")
        
        for i, opp in enumerate(opportunities, 1):
            print(f"\n{'='*60}")
            print(f"机会 #{i}")
            
            if detailed:
                opp.print_detailed()
            else:
                opp.print_summary()


def load_config_and_find_opportunities(config_path: str = None, currency: str = "BTC", 
                                     env: str = "testnet", detailed: bool = False) -> List[StraddleOpportunity]:
    """
    加载配置并寻找Selling Straddle机会
    
    Args:
        config_path: 配置文件路径
        currency: 币种
        env: 环境
        detailed: 是否显示详细信息
        
    Returns:
        找到的机会列表
    """
    if config_path is None:
        config_path = "/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/gamma_scalping/selling_straddle.yaml"
    
    finder = SellingStraddleFinder(config_path, currency, env)
    opportunities = finder.find_selling_straddle_opportunities()
    finder.display_opportunities(opportunities, detailed)
    return opportunities



if __name__ == "__main__":
    print("🚀 Selling Straddle机会寻找器测试")
    print("="*60)
    
    # 寻找机会
    opportunities = load_config_and_find_opportunities(
        currency="BTC",
        env="testnet", 
        detailed=True
    )
    
    print(f"\n✅ 测试完成，找到{len(opportunities)}个机会")
