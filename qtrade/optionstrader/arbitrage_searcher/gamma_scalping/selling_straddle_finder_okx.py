# -*- coding: utf-8 -*-
"""
Gamma Scalping - OKX Selling Straddle Finder
基于实时数据寻找OKX Selling Straddle机会
整合EWMA波动率跟踪器和OKX期权数据
"""

import sys
from typing import List, Dict, Any, Optional, Tuple
import yaml
from pathlib import Path

from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.straddle_options_okx import (
    get_straddle_atm_options_okx
)
from qtrade.optionstrader.arbitrage_searcher.option_data import OptionData, StraddleOpportunityOKX
from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.ewma_vol_tracker import RealDataEWMAVolTracker


def update_straddle_opportunity_okx(opportunity: StraddleOpportunityOKX,
                                realized_vol: float, 
                                net_delta_only: bool = True):
    """
    更新OKX Straddle机会的实时Greeks数据
    
    Args:
        opportunity: 现有的StraddleOpportunityOKX对象
        realized_vol: 最新的实现波动率
        net_delta_only: 如果为True，只返回combined net delta；如果为False，返回完整更新的对象
    
    Returns:
        如果net_delta_only=True: float (combined net delta)
        如果net_delta_only=False: StraddleOpportunityOKX (更新后的完整对象)
    """
    try:
        # 导入OKX API函数
        from qtrade.optionstrader.arbitrage_searcher.calendar_spread.atm_options_okx import (
            get_okx_option_market_data, _okx_get
        )
        
        # 获取最新的期权市场数据
        def get_latest_option_data_okx(inst_id: str) -> Dict[str, Any]:
            """获取单个OKX期权的最新市场数据"""
            try:
                # 先获取summary cache
                uly = inst_id.split('-')[0] + '-USD'  # e.g., BTC-USD
                summary_cache = {}
                
                try:
                    summ_data = _okx_get("/api/v5/public/opt-summary", params={"uly": uly})
                    sarr = (summ_data or {}).get("data", [])
                    for s in sarr:
                        iid = s.get("instId")
                        if iid:
                            summary_cache[iid] = s
                except Exception as e:
                    print(f"⚠️ 获取 opt-summary 失败: {e}")
                
                # 获取市场数据
                market_data = get_okx_option_market_data(inst_id, summary_cache=summary_cache)
                
                return {
                    "best_bid": market_data.get("best_bid", 0),
                    "best_ask": market_data.get("best_ask", 0),
                    "mid_price": market_data.get("mid_price", 0),
                    "mark_iv": market_data.get("mark_iv", 0),
                    "open_interest": market_data.get("open_interest", 0),
                    "greeks": market_data.get("greeks", {})
                }
            except Exception as e:
                print(f"⚠️ 获取{inst_id}最新数据失败: {e}")
                return None
        
        # 获取Call和Put的最新数据
        call_data = get_latest_option_data_okx(opportunity.call_option.symbol)
        put_data = get_latest_option_data_okx(opportunity.put_option.symbol)
        
        if not call_data or not put_data:
            print("❌ 无法获取期权最新数据")
            if net_delta_only:
                return opportunity.net_delta
            else:
                return opportunity
        
        # 如果只需要net delta，直接计算并返回
        if net_delta_only:
            call_delta = call_data["greeks"].get("delta", 0)
            put_delta = put_data["greeks"].get("delta", 0)
            combined_delta = call_delta + put_delta
            
            print(f"🔄 更新Delta: Call={call_delta:.4f}, Put={put_delta:.4f}, Combined={combined_delta:.4f}")
            return combined_delta
        
        # 如果需要完整更新，直接更新原对象的属性
        # 更新Call Option数据
        opportunity.call_option.iv = call_data["mark_iv"]
        opportunity.call_option.bid = call_data["best_bid"]
        opportunity.call_option.ask = call_data["best_ask"]
        opportunity.call_option.mid_price = call_data["mid_price"]
        opportunity.call_option.delta = call_data["greeks"].get("delta", 0)
        opportunity.call_option.net_delta = call_data["greeks"].get("delta", 0)  # OKX使用delta
        opportunity.call_option.gamma = call_data["greeks"].get("gamma", 0)
        opportunity.call_option.vega = call_data["greeks"].get("vega", 0)
        opportunity.call_option.theta = call_data["greeks"].get("theta", 0)
        opportunity.call_option.rho = call_data["greeks"].get("rho", 0)
        opportunity.call_option.open_interest = call_data["open_interest"]
        
        # 更新Put Option数据
        opportunity.put_option.iv = put_data["mark_iv"]
        opportunity.put_option.bid = put_data["best_bid"]
        opportunity.put_option.ask = put_data["best_ask"]
        opportunity.put_option.mid_price = put_data["mid_price"]
        opportunity.put_option.delta = put_data["greeks"].get("delta", 0)
        opportunity.put_option.net_delta = put_data["greeks"].get("delta", 0)
        opportunity.put_option.gamma = put_data["greeks"].get("gamma", 0)
        opportunity.put_option.vega = put_data["greeks"].get("vega", 0)
        opportunity.put_option.theta = put_data["greeks"].get("theta", 0)
        opportunity.put_option.rho = put_data["greeks"].get("rho", 0)
        opportunity.put_option.open_interest = put_data["open_interest"]
        
        # 更新实现波动率
        opportunity.realized_vol = realized_vol
        
        # 重新计算衍生属性
        opportunity.net_delta = opportunity.call_option.delta + opportunity.put_option.delta
        opportunity.total_gamma = opportunity.call_option.gamma + opportunity.put_option.gamma
        opportunity.total_theta = opportunity.call_option.theta + opportunity.put_option.theta
        opportunity.total_vega = opportunity.call_option.vega + opportunity.put_option.vega
        opportunity.avg_iv = (opportunity.call_option.iv + opportunity.put_option.iv) / 2
        opportunity.iv_premium = opportunity.avg_iv - opportunity.realized_vol
        opportunity.iv_premium_pct = opportunity.iv_premium * 100
        opportunity.total_premium = opportunity.call_option.mid_price + opportunity.put_option.mid_price
        
        print(f"✅ 完整更新OKX Straddle机会 (in-place):")
        print(f"   Combined Delta: {opportunity.net_delta:.4f}")
        print(f"   Total Gamma: {opportunity.total_gamma:.4f}")
        print(f"   Total Theta: {opportunity.total_theta:.4f}")
        print(f"   IV Premium: {opportunity.iv_premium_pct:+.1f}%")
        
        return opportunity
        
    except Exception as e:
        print(f"❌ 更新OKX Straddle机会失败: {e}")
        import traceback
        traceback.print_exc()
        if net_delta_only:
            return opportunity.net_delta
        else:
            return opportunity 


class SellingStraddleFinderOKX:
    """OKX Selling Straddle机会寻找器"""
    
    def __init__(self, config_path: str, currency: str = "BTC"):
        """
        初始化OKX Selling Straddle寻找器
        
        Args:
            config_path: 配置文件路径
            currency: 币种
        """
        self.currency = currency
        self.config = self._load_config(config_path)
        
        # 初始化EWMA波动率跟踪器
        self.vol_tracker = self._initialize_vol_tracker()
        
        print(f"🚀 [OKX] 初始化Selling Straddle寻找器")
        print(f"   币种: {currency}")
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
    
    def find_selling_straddle_opportunities(self) -> List[StraddleOpportunityOKX]:
        """
        寻找OKX Selling Straddle机会
        
        Returns:
            Selling Straddle机会列表
        """
        print(f"\n🔍 [OKX] 寻找{self.currency} Selling Straddle机会...")
        
        # 1. 获取已实现波动率
        realized_vol = self.get_realized_volatility()
        if realized_vol is None:
            print("❌ 无法获取已实现波动率，终止搜索")
            return []
        
        print(f"📊 当前已实现波动率: {realized_vol:.1%}")
        
        # 2. 获取OKX ATM期权
        atm_options = get_straddle_atm_options_okx(self.config, self.currency)
        if not atm_options:
            print("❌ 未找到OKX ATM期权")
            return []
        
        print(f"📊 获取到{len(atm_options)}个OKX ATM期权")
        
        # 3. 筛选符合时间条件的期权
        time_filtered_options = self._filter_by_time_criteria(atm_options)
        if not time_filtered_options:
            print("❌ 没有符合时间条件的期权")
            return []
        
        print(f"📊 时间筛选后剩余{len(time_filtered_options)}个期权")
        
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
        
        # 6. 计算评分并排序
        for opp in opportunities:
            opp.calculate_score(self.config)
        
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        # 7. 限制返回数量
        max_results = self.config.get("search_config", {}).get("max_results", 5)
        opportunities = opportunities[:max_results]
        
        print(f"✅ [OKX] 找到{len(opportunities)}个Selling Straddle机会")
        
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
                              realized_vol: float) -> List[StraddleOpportunityOKX]:
        """根据IV条件筛选机会"""
        min_iv_premium = self.config.get('volatility_criteria', {}).get("min_iv_premium", 0.05)
        opportunities = []

        for call, put in pairs:
            avg_iv = (call.iv + put.iv) / 2
            iv_premium = avg_iv - realized_vol
            
            # 检查IV溢价是否足够
            if iv_premium >= min_iv_premium:
                opportunity = StraddleOpportunityOKX(
                    call_option=call,
                    put_option=put,
                    realized_vol=realized_vol
                )
                opportunities.append(opportunity)
        
        return opportunities
    
    def display_opportunities(self, opportunities: List[StraddleOpportunityOKX], 
                            detailed: bool = False):
        """显示找到的机会"""
        if not opportunities:
            print("❌ 未找到OKX Selling Straddle机会")
            return
        
        print(f"\n🎯 [OKX] 找到{len(opportunities)}个Selling Straddle机会:")
        
        for i, opp in enumerate(opportunities, 1):
            print(f"\n{'='*60}")
            print(f"机会 #{i}")
            
            if detailed:
                opp.print_detailed()
            else:
                opp.print_summary()


def load_config_and_find_opportunities_okx(config_path: str = None, currency: str = "BTC", 
                                         detailed: bool = False) -> List[StraddleOpportunityOKX]:
    """
    加载配置并寻找OKX Selling Straddle机会
    
    Args:
        config_path: 配置文件路径
        currency: 币种
        detailed: 是否显示详细信息
        
    Returns:
        找到的机会列表
    """
    if config_path is None:
        # 尝试多个可能的配置路径
        possible_paths = [
            "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml",
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                config_path = path
                break
        
        if config_path is None:
            print("⚠️ 未找到配置文件，将使用默认配置")
            config_path = possible_paths[0]  # 使用第一个作为默认
    
    finder = SellingStraddleFinderOKX(config_path, currency)
    opportunities = finder.find_selling_straddle_opportunities()
    finder.display_opportunities(opportunities, detailed)
    return opportunities


if __name__ == "__main__":
    print("🚀 [OKX] Selling Straddle机会寻找器测试")
    print("="*60)
    
    # 寻找机会
    opportunities = load_config_and_find_opportunities_okx(
        currency="BTC",
        detailed=True
    )
    
    print(f"\n✅ 测试完成，找到{len(opportunities)}个机会")

