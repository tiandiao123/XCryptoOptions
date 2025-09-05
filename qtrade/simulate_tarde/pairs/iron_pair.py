import re
from datetime import datetime, date
from qtrade.data_utils import get_option_open_price


def find_iron_condor_opportunity(atm_options, spot_price, min_iv_threshold=0.6):
    """
    寻找Iron Condor套利机会 - 高IV环境下的时间价值收割
    
    策略逻辑：
    1. 仅在IV >> RV时开仓（高IV环境）
    2. 选择一周后到期的期权构建Iron Condor
    3. Call侧：卖出OTM Call + 买入更OTM Call（上方保护）
    4. Put侧：卖出OTM Put + 买入更OTM Put（下方保护）
    5. 收取时间价值，赌现货在到期时保持在区间内
    
    Args:
        atm_options: ATM期权列表
        spot_price: 现货价格
        min_iv_threshold: 最低IV阈值（默认60%）
        
    Returns:
        dict or None: Iron Condor机会，如果没找到则返回None
    """
    if not atm_options or not spot_price:
        return None
    
    # 筛选一周后到期的期权 (5-10天)
    target_options = [opt for opt in atm_options if 5 <= opt['days_to_expiry'] <= 10]
    
    if not target_options:
        return None
    
    # 检查IV水平是否足够高
    avg_iv = sum(opt['iv'] for opt in target_options) / len(target_options)
    if avg_iv < min_iv_threshold:
        return None
    
    # 按期权类型分组
    calls = [opt for opt in target_options if opt['option_type'] == 'C']
    puts = [opt for opt in target_options if opt['option_type'] == 'P']
    
    if not calls or not puts:
        return None
    
    # 🎯 构建Iron Condor配对
    iron_condor = _find_best_iron_condor(calls, puts, spot_price)
    
    if not iron_condor:
        return None
    
    # 计算收益风险比
    max_profit = iron_condor['net_premium']
    max_loss = iron_condor['max_risk'] - max_profit
    
    if max_profit <= 0 or max_loss <= 0:
        return None
    
    profit_risk_ratio = max_profit / max_loss
    
    # 要求合理的收益风险比
    if profit_risk_ratio < 0.2:  # 至少1:5的风险收益比
        return None
    
    return {
        'iron_condor': iron_condor,
        'strategy_type': 'iron_condor',
        'avg_iv': avg_iv,
        'profit_risk_ratio': profit_risk_ratio,
        'days_to_expiry': iron_condor['call_short']['days_to_expiry']
    }


def _find_best_iron_condor(calls, puts, spot_price):
    """
    构建最佳Iron Condor组合
    
    结构：
    - Short Call (卖出看涨，现货上方)
    - Long Call (买入看涨，更高执行价保护)  
    - Short Put (卖出看跌，现货下方)
    - Long Put (买入看跌，更低执行价保护)
    
    Returns:
        dict or None: Iron Condor配置
    """
    best_iron_condor = None
    best_net_premium = -float('inf')
    
    # 设置执行价格范围 (相对现货价格的百分比)
    otm_range = (0.03, 0.08)    # OTM范围：3%-8%
    wing_spread = (0.02, 0.05)   # 翼展：2%-5%
    
    # Call侧：找到合适的OTM Call配对
    call_pairs = []
    for short_call in calls:
        if short_call['strike_price'] <= spot_price:
            continue  # 跳过ITM或ATM
        
        short_moneyness = (short_call['strike_price'] - spot_price) / spot_price
        if not (otm_range[0] <= short_moneyness <= otm_range[1]):
            continue
        
        # 寻找保护性Long Call
        for long_call in calls:
            if long_call['strike_price'] <= short_call['strike_price']:
                continue
            
            long_moneyness = (long_call['strike_price'] - spot_price) / spot_price
            spread_width = long_moneyness - short_moneyness
            
            if wing_spread[0] <= spread_width <= wing_spread[1]:
                call_pairs.append((short_call, long_call))
    
    # Put侧：找到合适的OTM Put配对
    put_pairs = []
    for short_put in puts:
        if short_put['strike_price'] >= spot_price:
            continue  # 跳过ITM或ATM
        
        short_moneyness = (spot_price - short_put['strike_price']) / spot_price
        if not (otm_range[0] <= short_moneyness <= otm_range[1]):
            continue
        
        # 寻找保护性Long Put
        for long_put in puts:
            if long_put['strike_price'] >= short_put['strike_price']:
                continue
            
            long_moneyness = (spot_price - long_put['strike_price']) / spot_price
            spread_width = long_moneyness - short_moneyness
            
            if wing_spread[0] <= spread_width <= wing_spread[1]:
                put_pairs.append((short_put, long_put))
    
    # 组合Call和Put配对，寻找最佳Iron Condor
    for call_short, call_long in call_pairs:
        for put_short, put_long in put_pairs:
            
            # 计算净权利金收入
            net_premium = (call_short['open'] - call_long['open'] + 
                          put_short['open'] - put_long['open'])
            
            if net_premium <= 0:
                continue  # 必须收取权利金
            
            # 计算最大风险
            call_spread_width = call_long['strike_price'] - call_short['strike_price']
            put_spread_width = put_short['strike_price'] - put_long['strike_price']
            max_risk = min(call_spread_width, put_spread_width)
            
            # 检查风险收益比
            if net_premium / max_risk < 0.2:
                continue
            
            if net_premium > best_net_premium:
                best_net_premium = net_premium
                best_iron_condor = {
                    'call_short': call_short,
                    'call_long': call_long,
                    'put_short': put_short,
                    'put_long': put_long,
                    'net_premium': net_premium,
                    'max_risk': max_risk,
                    'call_spread_width': call_spread_width,
                    'put_spread_width': put_spread_width
                }
    
    return best_iron_condor


class IronPair:
    def __init__(self, iron_condor, entry_time, entry_spot_price,
                 delta_hedge_enabled=False, delta_threshold=0.05, contract_multiplier=1.0):
        """Iron Condor组合"""
        self.entry_time = entry_time
        self.entry_spot_price = entry_spot_price
        
        # 四个期权的价格
        self.call_short_price = iron_condor['call_short']['open']
        self.call_long_price = iron_condor['call_long']['open']
        self.put_short_price = iron_condor['put_short']['open']
        self.put_long_price = iron_condor['put_long']['open']
        
        # 🆕 当前希腊字母
        self.call_short_iv = iron_condor['call_short']['iv']
        self.call_long_iv = iron_condor['call_long']['iv']
        self.put_short_iv = iron_condor['put_short']['iv']
        self.put_long_iv = iron_condor['put_long']['iv']
        
        self.call_short_delta = iron_condor['call_short'].get('pa_delta', iron_condor['call_short'].get('delta', 0))
        self.call_long_delta = iron_condor['call_long'].get('pa_delta', iron_condor['call_long'].get('delta', 0))
        self.put_short_delta = iron_condor['put_short'].get('pa_delta', iron_condor['put_short'].get('delta', 0))
        self.put_long_delta = iron_condor['put_long'].get('pa_delta', iron_condor['put_long'].get('delta', 0))
        
        self.call_short_gamma = iron_condor['call_short'].get('pa_gamma', iron_condor['call_short'].get('gamma', 0))
        self.call_long_gamma = iron_condor['call_long'].get('pa_gamma', iron_condor['call_long'].get('gamma', 0))
        self.put_short_gamma = iron_condor['put_short'].get('pa_gamma', iron_condor['put_short'].get('gamma', 0))
        self.put_long_gamma = iron_condor['put_long'].get('pa_gamma', iron_condor['put_long'].get('gamma', 0))
        
        self.call_short_vega = iron_condor['call_short'].get('pa_vega', iron_condor['call_short'].get('vega', 0))
        self.call_long_vega = iron_condor['call_long'].get('pa_vega', iron_condor['call_long'].get('vega', 0))
        self.put_short_vega = iron_condor['put_short'].get('pa_vega', iron_condor['put_short'].get('vega', 0))
        self.put_long_vega = iron_condor['put_long'].get('pa_vega', iron_condor['put_long'].get('vega', 0))
        
        # 🆕 入场时的希腊字母（用于对比）
        self.entry_greeks = {
            'call_short': {
                'price': iron_condor['call_short']['open'],
                'iv': self.call_short_iv,
                'delta': self.call_short_delta,
                'gamma': self.call_short_gamma,
                'vega': self.call_short_vega
            },
            'call_long': {
                'price': iron_condor['call_long']['open'],
                'iv': self.call_long_iv,
                'delta': self.call_long_delta,
                'gamma': self.call_long_gamma,
                'vega': self.call_long_vega
            },
            'put_short': {
                'price': iron_condor['put_short']['open'],
                'iv': self.put_short_iv,
                'delta': self.put_short_delta,
                'gamma': self.put_short_gamma,
                'vega': self.put_short_vega
            },
            'put_long': {
                'price': iron_condor['put_long']['open'],
                'iv': self.put_long_iv,
                'delta': self.put_long_delta,
                'gamma': self.put_long_gamma,
                'vega': self.put_long_vega
            }
        }
        
        # 保持向后兼容
        self.option_entry_prices = {
            'call_short': iron_condor['call_short']['open'],
            'call_long': iron_condor['call_long']['open'],
            'put_short': iron_condor['put_short']['open'],
            'put_long': iron_condor['put_long']['open']
        }
        
        # 入场净权利金（我们收取的权利金）
        self.entry_premium = iron_condor['net_premium']
        
        # 风险参数
        self.max_risk = iron_condor['max_risk']
        self.max_profit = self.entry_premium
        
        # 🆕 盈亏跟踪
        self.current_pnl = 0.0
        self.current_options_pnl = 0.0
        self.is_active = True
        self.last_update_time = entry_time
        
        # 存储期权符号
        self.option_symbols = {
            'call_short': iron_condor['call_short']['symbol'],
            'call_long': iron_condor['call_long']['symbol'],
            'put_short': iron_condor['put_short']['symbol'],
            'put_long': iron_condor['put_long']['symbol']
        }
        
        # 执行价格
        self.strike_prices = {
            'call_short': iron_condor['call_short']['strike_price'],
            'call_long': iron_condor['call_long']['strike_price'],
            'put_short': iron_condor['put_short']['strike_price'],
            'put_long': iron_condor['put_long']['strike_price']
        }
        
        # 🆕 Delta对冲相关配置（Iron Condor通常Delta中性，但可选）
        self.delta_hedge_enabled = delta_hedge_enabled
        self.delta_threshold = delta_threshold
        self.contract_multiplier = contract_multiplier
        
        if delta_hedge_enabled:
            # Delta对冲状态
            self.average_hedge_spot_price = 0.0
            self.current_delta = 0.0
            self.current_hedge_delta = 0.0
            self.inverse_perpetual_pnl = 0.0
            self.realized_perpetual_pnl = 0.0
            self.hedge_transactions = []
            self.total_hedge_cost = 0.0
    
    def update_pnl(self, current_time, df, current_spot_price, print_info=False):
        """更新Iron Condor的P&L"""
        if not self.is_active:
            return False, "已平仓"
        
        try:
            # 获取四个期权的当前价格
            call_short_current = get_option_open_price(df, self.option_symbols['call_short'], current_time, print_info=False)
            call_long_current = get_option_open_price(df, self.option_symbols['call_long'], current_time, print_info=False)
            put_short_current = get_option_open_price(df, self.option_symbols['put_short'], current_time, print_info=False)
            put_long_current = get_option_open_price(df, self.option_symbols['put_long'], current_time, print_info=False)
            
            if any(price is None for price in [call_short_current, call_long_current, put_short_current, put_long_current]):
                return False, "missing_prices"
            
            # 更新当前价格
            self.call_short_price = call_short_current
            self.call_long_price = call_long_current
            self.put_short_price = put_short_current
            self.put_long_price = put_long_current
            
            # 计算P&L（Iron Condor是卖出策略，收取权利金）
            # P&L = 入场权利金 - 当前期权组合价值
            current_portfolio_value = (call_short_current - call_long_current + 
                                     put_short_current - put_long_current)
            
            self.current_pnl = self.entry_premium - current_portfolio_value
            self.last_update_time = current_time
            
            return True, "success"
            
        except Exception as e:
            return False, f"exception: {str(e)}"
    
    def should_close(self, current_time, current_spot_price, max_loss_pct=0.8, target_profit_pct=0.5):
        """
        平仓条件检查
        
        Args:
            current_time: 当前时间
            current_spot_price: 当前现货价格
            max_loss_pct: 最大亏损百分比（相对于最大风险）
            target_profit_pct: 目标盈利百分比（相对于入场权利金）
            
        Returns:
            tuple: (should_close, reason)
        """
        if not self.is_active:
            return False, "已平仓"
        
        # 1. 到期平仓检查
        days_remaining = self._get_days_to_expiry(current_time)
        if days_remaining <= 0:
            return True, "期权到期"
        
        # 2. 盈利目标达成
        profit_threshold = self.entry_premium * target_profit_pct
        if self.current_pnl >= profit_threshold:
            return True, f"盈利目标达成 (目标: {target_profit_pct:.0%})"
        
        # 3. 止损检查
        max_loss_threshold = -self.max_risk * max_loss_pct
        if self.current_pnl <= max_loss_threshold:
            return True, f"止损 (P&L: {self.current_pnl/self.entry_premium:.1%})"
        
        # 4. 现货价格突破检查
        if current_spot_price >= self.strike_prices['call_short']:
            return True, f"现货突破上轨 (${current_spot_price:,.0f} >= ${self.strike_prices['call_short']:,.0f})"
        
        if current_spot_price <= self.strike_prices['put_short']:
            return True, f"现货突破下轨 (${current_spot_price:,.0f} <= ${self.strike_prices['put_short']:,.0f})"
        
        # 5. 临近到期强制平仓
        if days_remaining <= 1:
            return True, "临近到期强制平仓"
        
        return False, "持续持有"
    
    def _get_days_to_expiry(self, current_time):
        """计算到期天数"""
        # 从期权符号中提取到期日期
        symbol = self.option_symbols['call_short']
        match = re.search(r'(\d{6})', symbol)
        if not match:
            return 0
        
        expiry_str = match.group(1)
        try:
            expiry_date = datetime.strptime(f"20{expiry_str}", "%Y%m%d").date()
            current_date = current_time.date()
            return (expiry_date - current_date).days
        except:
            return 0
    
    def close(self, close_time, reason):
        """平仓Iron Condor"""
        if not self.is_active:
            return None
        
        self.is_active = False
        pnl_pct = self.current_pnl / self.entry_premium if self.entry_premium != 0 else 0
        
        return {
            'close_time': close_time,
            'reason': reason,
            'pnl': self.current_pnl,
            'pnl_pct': pnl_pct,
            'strategy_type': 'iron_condor',
            'entry_premium': self.entry_premium,
            'contract_pnl': {
                'call_short': self.call_short_price,
                'call_long': self.call_long_price,
                'put_short': self.put_short_price,
                'put_long': self.put_long_price
            }
        }
    
    def get_portfolio_delta(self):
        """计算组合净Delta（理论上应接近0）"""
        # Iron Condor理论上是Delta中性策略
        # 这里简化计算，实际应该从希腊字母数据获取
        return 0.0
