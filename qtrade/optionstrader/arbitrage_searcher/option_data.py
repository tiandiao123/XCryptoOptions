from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class OptionData:
    """期权数据结构"""
    symbol: str
    strike: float
    expiry: str
    days_to_expiry: int
    option_type: str  # 'C' or 'P'
    iv: float
    bid: float
    ask: float
    mid_price: float
    delta: float
    net_delta: float  # 添加Net Delta近似值
    gamma: float
    vega: float
    theta: float
    rho: float
    open_interest: int = 0
    
    def __str__(self) -> str:
        """格式化显示期权信息"""
        return (f"{self.symbol} | "
                f"Strike: ${self.strike:,.0f} | "
                f"Type: {self.option_type} | "
                f"DTE: {self.days_to_expiry}d | "
                f"IV: {self.iv:.1%} | "
                f"Mid: {self.mid_price:.4f} | "
                f"Δ: {self.delta:.3f}")
    
    def print_detailed(self) -> None:
        """打印详细期权信息"""
        print(f"📊 期权详情: {self.symbol}")
        print(f"   🎯 执行价: ${self.strike:,.0f}")
        print(f"   📅 到期: {self.expiry} ({self.days_to_expiry}天)")
        print(f"   🔄 类型: {'看涨期权' if self.option_type == 'C' else '看跌期权'}")
        print(f"   💰 价格: Bid={self.bid:.4f}, Ask={self.ask:.4f}, Mid={self.mid_price:.4f}")
        print(f"   📈 波动率: {self.iv:.1%}")
        print(f"   🏛️ 持仓量: {self.open_interest}")
        print(f"   📊 希腊字母:")
        print(f"      Delta (Δ): {self.delta:+.3f}")
        print(f"      Net Delta: {self.net_delta:+.3f}")
        print(f"      Gamma (Γ): {self.gamma:+.3f}")
        print(f"      Vega (ν):  {self.vega:+.3f}")
        print(f"      Theta (Θ): {self.theta:+.3f}")
        print(f"      Rho (ρ):   {self.rho:+.3f}")
    
    def print_summary(self) -> None:
        """打印简要信息"""
        print(f"📋 {self.symbol}")
        print(f"   ${self.strike:,.0f} {self.option_type} | {self.days_to_expiry}d | "
              f"IV:{self.iv:.1%} | Mid:{self.mid_price:.4f} | Δ:{self.delta:.3f}")


@dataclass
class CalendarSpreadOpportunity:
    """Calendar Spread机会数据结构"""
    rank: int
    short_option: OptionData  # 卖出的短期期权
    long_option: OptionData   # 买入的长期期权
    iv_spread: float          # IV价差
    iv_spread_pct: float      # IV价差百分比
    time_gap_days: int        # 时间间隔（天）
    net_premium: float        # 净保险费（负数表示支出）
    max_profit_potential: float  # 最大盈利潜力
    signal_strength: str      # 信号强度：WEAK, MODERATE, STRONG

    # 🆕 开仓时的IV记录
    short_option_entry_iv: float = 0.0
    long_option_entry_iv: float = 0.0
    
    # 🆕 开仓时的实际成交价格
    short_option_entry_price: float = 0.0  # Short腿开仓价格
    long_option_entry_price: float = 0.0   # Long腿开仓价格

    open_status: bool = False  # 是否持仓
    contracts: float = 0.0 # 持仓大小


@dataclass
class StraddleOpportunityOKX:
    """OKX Selling Straddle机会数据结构"""
    call_option: OptionData
    put_option: OptionData
    strategy_type: str = "short_straddle"
    
    # 波动率分析
    avg_iv: float = 0.0
    realized_vol: float = 0.0
    iv_premium: float = 0.0  # IV - RV
    iv_premium_pct: float = 0.0  # (IV - RV) / RV * 100

    # entry iv 
    call_option_entry_iv: float = 0.0
    put_option_entry_iv: float = 0.0
    
    # 🆕 开仓时的现货价格
    entry_spot_price: float = 0.0
    
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

    open_status: bool = False  # 是否持仓
    contracts: float = 0.0 # 持仓大小
    
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
        # 从symbol提取币种
        currency = self.call_option.symbol.split("-")[0] if hasattr(self.call_option, 'symbol') and "-" in self.call_option.symbol else "UNKNOWN"
        
        print(f"\n🎯 [OKX] Selling Straddle机会 ({self.signal_strength.upper()})")
        print(f"   执行价: ${self.strike_price:,.0f}")
        print(f"   到期: {self.days_to_expiry}天")
        print(f"   总权利金: {self.total_premium:.4f} {currency}")
        print(f"   IV溢价: {self.iv_premium_pct:+.1f}% (IV={self.avg_iv:.1%}, RV={self.realized_vol:.1%})")
        print(f"   净Delta: {self.net_delta:.3f}")
        print(f"   总Gamma: {self.total_gamma:.3f}")
        print(f"   总Theta: {self.total_theta:.3f}")
        print(f"   评分: {self.score:.1f}/100")
    
    def print_detailed(self):
        """打印详细信息"""
        self.print_summary()
        print(f"\n📊 详细信息:")
        print(f"   🔵 Call: {self.call_option.symbol}")
        print(f"      价格: Bid={self.call_option.bid:.4f}, Ask={self.call_option.ask:.4f}, Mid={self.call_premium:.4f}")
        print(f"      希腊字母: Δ={self.call_option.delta:+.4f}, Γ={self.call_option.gamma:+.4f}, Θ={self.call_option.theta:+.4f}")
        print(f"      IV: {self.call_option.iv:.1%}, 持仓量: {self.call_option.open_interest}")
        
        print(f"   🔴 Put: {self.put_option.symbol}")
        print(f"      价格: Bid={self.put_option.bid:.4f}, Ask={self.put_option.ask:.4f}, Mid={self.put_premium:.4f}")
        print(f"      希腊字母: Δ={self.put_option.delta:+.4f}, Γ={self.put_option.gamma:+.4f}, Θ={self.put_option.theta:+.4f}")
        print(f"      IV: {self.put_option.iv:.1%}, 持仓量: {self.put_option.open_interest}")