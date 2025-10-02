import re
import numpy as np
import time
from datetime import datetime, date
from qtrade.simulate_tarde.data_loader.data_utils import get_option_open_price, get_option_full_info


def find_straddle_opportunity(atm_options, realized_vol=None, iv_threshold_pct=0.05):
    """
    寻找Straddle机会 - 优先Sell，无Sell机会时找Buy
    
    策略逻辑：
    1. Sell Straddle: 7-14天期权，IV > RV + 5% 时卖出
    2. Buy Straddle: 1个月期权，IV < RV - 5% 时买入
    
    Args:
        atm_options: ATM期权列表
        realized_vol: 已实现波动率（年化）
        iv_threshold_pct: IV阈值（默认5%）
        
    Returns:
        dict or None: Straddle机会配置
    """
    if not atm_options:
        return None
    
    # 🎯 Step 1: 优先检查Sell Straddle机会
    sell_opportunity = find_sell_straddle_opportunity(atm_options, realized_vol, iv_threshold_pct)
    if sell_opportunity:
        return sell_opportunity
    
    # 🎯 Step 2: 如果没有Sell机会，检查Buy Straddle机会
    buy_opportunity = find_buy_straddle_opportunity(atm_options, realized_vol, iv_threshold_pct)
    if buy_opportunity:
        return buy_opportunity
    
    return None


def find_sell_straddle_opportunity(atm_options, realized_vol=None, iv_threshold_pct=0.05, spot_price=None, price_tolerance=0.01):
    """
    寻找Short Straddle机会 - 7-20天期权，IV高估时卖出，执行价格在现货价格±1%范围内
    
    Args:
        atm_options: ATM期权列表
        realized_vol: 已实现波动率（年化）
        iv_threshold_pct: IV高于RV的阈值（默认5%）
        spot_price: 现货价格（用于ATM筛选，可选）
        price_tolerance: 价格容忍度（默认1%）
        
    Returns:
        dict or None: Short Straddle配置
    """
    if not atm_options or realized_vol is None:
        return None
    
    # 🆕 获取现货价格
    if spot_price is None and atm_options:
        # 从第一个期权中获取现货价格
        spot_price = atm_options[0].get('spot_open', atm_options[0].get('spot_price', None))
    
    if spot_price is None:
        return None
    
    # �� 计算±1%价格范围
    min_strike = spot_price * (1 - price_tolerance)
    max_strike = spot_price * (1 + price_tolerance)
    
    # 🔧 修改：筛选7-20天期权，且执行价格在现货价格±1%范围内
    short_term_options = [
        opt for opt in atm_options 
        if (7 <= opt['days_to_expiry'] <= 20 and 
            min_strike <= opt['strike_price'] <= max_strike)  # 🆕 添加价格范围限制
    ]
    
    if not short_term_options:
        return None
    
    # 按期权类型分组
    calls = [opt for opt in short_term_options if opt['option_type'] == 'C']
    puts = [opt for opt in short_term_options if opt['option_type'] == 'P']
    
    if not calls or not puts:
        return None
    
    # 🔍 寻找最佳ATM Straddle配对
    best_straddle = _find_best_atm_straddle_pair(calls, puts, strategy_type="short")
    
    if not best_straddle:
        return None
    
    # 🎯 检查IV是否高于RV + 阈值
    avg_iv = (best_straddle['call_option']['iv'] + best_straddle['put_option']['iv']) / 2
    iv_premium = avg_iv - realized_vol
    
    if iv_premium < iv_threshold_pct:
        return None  # IV溢价不够，不适合卖出
    
    # 第84-92行：修改返回字典，添加新的信息字段
    return {
        'straddle': best_straddle,
        'strategy_type': 'short_straddle',
        'iv_premium': iv_premium,
        'avg_iv': avg_iv,
        'realized_vol': realized_vol,
        'days_to_expiry': best_straddle['call_option']['days_to_expiry'],
        'iv_condition_met': True,
        'spot_price': spot_price,  # 🆕 添加现货价格信息
        'strike_range': f"${min_strike:.0f}-${max_strike:.0f}",  # 🆕 添加价格范围信息
        'selected_strike': best_straddle['call_option']['strike_price']  # 🆕 添加选中的执行价格
    }


def find_buy_straddle_opportunity(atm_options, realized_vol=None, iv_threshold_pct=0.05):
    """
    寻找Long Straddle机会 - 1个月期权，当IV低于RV时买入
    
    Args:
        atm_options: ATM期权列表
        realized_vol: 已实现波动率（年化）
        iv_threshold_pct: IV低于RV的阈值（默认5%，即IV < RV - 5%时买入）
        
    Returns:
        dict or None: Long Straddle配置
    """
    if not atm_options or realized_vol is None:
        return None
    
    # 筛选1个月期权 (25-35天)
    one_month_options = [
        opt for opt in atm_options 
        if 25 <= opt['days_to_expiry'] <= 35
    ]
    
    if not one_month_options:
        return None
    
    # 按期权类型分组
    calls = [opt for opt in one_month_options if opt['option_type'] == 'C']
    puts = [opt for opt in one_month_options if opt['option_type'] == 'P']
    
    if not calls or not puts:
        return None
    
    # 🔍 寻找最佳ATM Straddle配对
    best_straddle = _find_best_atm_straddle_pair(calls, puts, strategy_type="long")
    
    if not best_straddle:
        return None
    
    # 🎯 检查IV是否低于RV - 阈值
    avg_iv = (best_straddle['call_option']['iv'] + best_straddle['put_option']['iv']) / 2
    iv_discount = realized_vol - avg_iv  # RV - IV，正数表示IV被低估
    
    if iv_discount < iv_threshold_pct:
        return None  # IV折价不够，不适合买入
    
    return {
        'straddle': best_straddle,
        'strategy_type': 'long_straddle',
        'iv_discount': iv_discount,  # IV被低估的程度
        'avg_iv': avg_iv,
        'realized_vol': realized_vol,
        'days_to_expiry': best_straddle['call_option']['days_to_expiry'],
        'iv_condition_met': True
    }


def _find_best_atm_straddle_pair(calls, puts, strategy_type="long"):
    """
    寻找最佳ATM Straddle配对
    
    Args:
        calls: Call期权列表
        puts: Put期权列表
        strategy_type: "long" 或 "short"
        
    Returns:
        dict or None: 最佳Straddle配对
    """
    best_straddle = None
    best_score = -float('inf') if strategy_type == "short" else float('inf')
    
    for call_opt in calls:
        for put_opt in puts:
            # 检查是否为相同执行价格和到期日
            if (abs(call_opt['strike_price'] - put_opt['strike_price']) > call_opt['strike_price'] * 0.005 or  # 0.5%容忍度
                abs(call_opt['days_to_expiry'] - put_opt['days_to_expiry']) > 1):
                continue
            
            # 检查IV和价格有效性
            if (call_opt['iv'] <= 0 or put_opt['iv'] <= 0 or 
                call_opt['open'] <= 0 or put_opt['open'] <= 0):
                continue
            
            # 计算评分指标
            avg_iv = (call_opt['iv'] + put_opt['iv']) / 2
            total_premium = call_opt['open'] + put_opt['open']
            
            if strategy_type == "short":
                # Short Straddle: 优选高IV + 高权利金
                score = avg_iv * 0.7 + total_premium * 0.3
                if score > best_score:
                    best_score = score
                    best_straddle = {
                        'call_option': call_opt,
                        'put_option': put_opt,
                        'total_premium': total_premium,
                        'avg_iv': avg_iv,
                        'score': score
                    }
            else:
                # Long Straddle: 优选低权利金成本（相对于IV）
                if avg_iv > 0:
                    score = total_premium / avg_iv  # 权利金/IV比率，越低越好
                    if score < best_score:
                        best_score = score
                        best_straddle = {
                            'call_option': call_opt,
                            'put_option': put_opt,
                            'total_premium': total_premium,
                            'avg_iv': avg_iv,
                            'score': score
                        }
    
    return best_straddle


def parse_option_expiry_date(symbol):
    """从期权符号解析到期日"""
    match = re.search(r'BTC-USD-(\d{6})-', symbol)
    if match:
        date_str = match.group(1)  # YYMMDD
        year = 2000 + int(date_str[:2])
        month = int(date_str[2:4])
        day = int(date_str[4:6])
        return date(year, month, day)
    return None


class StraddlePair:
    """
    Straddle策略组合类 - 支持Long/Short + Delta对冲
    
    Long Straddle: 买入相同执行价格的Call和Put (看大波动)
    Short Straddle: 卖出相同执行价格的Call和Put (看小波动)
    """
    
    def __init__(self, straddle_config, entry_time, entry_spot_price, 
                 delta_hedge_enabled=False, delta_threshold=0.05, contract_multiplier=1.0):
        """
        初始化Straddle组合
        
        Args:
            straddle_config: Straddle配置字典
            entry_time: 入场时间
            entry_spot_price: 入场时现货价格
            delta_hedge_enabled: 是否启用Delta对冲
            delta_threshold: Delta对冲阈值
            contract_multiplier: 合约乘数
        """
        self.entry_time = entry_time
        self.entry_spot_price = entry_spot_price
        self.strategy_type = straddle_config['strategy_type'].lower()
        
        # 提取期权信息
        call_option = straddle_config['straddle']['call_option']
        put_option = straddle_config['straddle']['put_option']
        
        # 期权价格
        self.call_price = call_option['open']
        self.put_price = put_option['open']
        
        # 🆕 当前希腊字母
        self.call_iv = call_option['iv']
        self.put_iv = put_option['iv']
        self.call_delta = call_option.get('pa_delta', call_option.get('delta', 0))
        self.put_delta = put_option.get('pa_delta', put_option.get('delta', 0))
        self.call_gamma = call_option.get('pa_gamma', call_option.get('gamma', 0))
        self.put_gamma = put_option.get('pa_gamma', put_option.get('gamma', 0))
        self.call_vega = call_option.get('pa_vega', call_option.get('vega', 0))
        self.put_vega = put_option.get('pa_vega', put_option.get('vega', 0))
        
        # 🆕 入场时的希腊字母（用于对比）
        self.entry_greeks = {
            'call_option': {
                'price': call_option['open'],
                'iv': self.call_iv,
                'delta': self.call_delta,
                'gamma': self.call_gamma,
                'vega': self.call_vega
            },
            'put_option': {
                'price': put_option['open'],
                'iv': self.put_iv,
                'delta': self.put_delta,
                'gamma': self.put_gamma,
                'vega': self.put_vega
            }
        }
        
        # 执行价格（Straddle中Call和Put应该有相同执行价格）
        self.strike_price = call_option['strike_price']
        if abs(call_option['strike_price'] - put_option['strike_price']) > 1e-6:
            print(f"⚠️  警告: Call执行价({call_option['strike_price']}) != Put执行价({put_option['strike_price']})")
        

        self.entry_premium = self.call_price + self.put_price     # 总是正数
        
        # 🆕 盈亏跟踪
        self.current_pnl = 0.0
        self.current_options_pnl = 0.0
        self.is_active = True
        self.last_update_time = entry_time
        
        # 存储期权符号以便查询
        self.option_symbols = {
            'call': call_option['symbol'],
            'put': put_option['symbol']
        }
        
        # 保持向后兼容
        self.option_entry_prices = {
            'call': call_option['open'],
            'put': put_option['open']
        }
        
        # 🆕 Delta对冲相关配置
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
        
        
        print(f"✅ {self.strategy_type.replace('_', ' ').title()}创建:")
        print(f"   执行价格: ${self.strike_price:,.2f}")
        print(f"   入场现货价: ${entry_spot_price:,.2f}")
        print(f"   入场权利金: {self.entry_premium:.6f} BTC")
        print(f"   Call价格: {self.call_price:.6f} BTC (IV: {self.call_iv:.1%})")
        print(f"   Put价格: {self.put_price:.6f} BTC (IV: {self.put_iv:.1%})")
        print(f"   平均IV: {(self.call_iv + self.put_iv) / 2:.1%}")
        print(f"   净Delta: {self.get_net_delta():+.3f}")
    
    def initialize_hedge(self, current_time=None, current_spot_price=None, hedge_cost_bps=0.0002, print_info=False):
        """
        初始化Delta对冲 - 复用calendar_pair的逻辑
        """
        if not self.delta_hedge_enabled:
            if print_info:
                print("🔄 Delta对冲未启用，跳过初始对冲")
            return True, None
        
        net_delta = self.get_net_delta()
        
        if print_info:
            print(f"🔄 执行初始Delta对冲:")
            print(f"   组合净Delta: {net_delta:+.3f}")
            print(f"   Delta阈值: ±{self.delta_threshold:.3f}")
        
        # 检查是否需要对冲
        if abs(net_delta) < self.delta_threshold:
            if print_info:
                print(f"   ✅ Delta在阈值内，无需对冲")
            return True, None
        
        # 初始化对冲参数
        self.average_hedge_spot_price = current_spot_price
        self.current_delta = net_delta * self.contract_multiplier
        self.current_hedge_delta = -self.current_delta  # 反向对冲
        
        if print_info:
            print(f"   📊 初始对冲执行:")
            print(f"     平均对冲现货价格: ${self.average_hedge_spot_price:,.0f}")
            print(f"     当前对冲Delta: {self.current_hedge_delta:+.3f}")
        
        return True, {'hedge_delta': self.current_hedge_delta, 'hedge_price': self.average_hedge_spot_price}
    
    def update_greeks(self, current_time, current_df, current_atm_options=None, print_info=False):
        """
        更新希腊字母信息
        """
        if not self.is_active:
            return False, "position_closed", None
        
        try:
            # 🆕 优先从ATM期权列表获取信息，备用DataFrame查询
            call_info = None
            put_info = None
            
            if current_atm_options:
                # 从ATM期权列表中查找
                for option in current_atm_options:
                    if option['symbol'] == self.option_symbols['call']:
                        call_info = option
                    elif option['symbol'] == self.option_symbols['put']:
                        put_info = option
            
            # 如果ATM列表中没找到，使用data_utils函数
            if not call_info:
                call_info = get_option_full_info(
                    current_df, 
                    self.option_symbols['call'], 
                    current_time, 
                    print_info=False
                )
            
            if not put_info:
                put_info = get_option_full_info(
                    current_df, 
                    self.option_symbols['put'], 
                    current_time, 
                    print_info=False
                )
            
            # 检查是否成功获取信息
            if not call_info or not put_info:
                missing = []
                if not call_info:
                    missing.append(self.option_symbols['call'])
                if not put_info:
                    missing.append(self.option_symbols['put'])
                
                return False, f"missing_greeks: {missing}", None
            
            # 🆕 更新价格
            self.call_price = call_info.get('open', call_info.get('option_price_coin', 0))
            self.put_price = put_info.get('open', put_info.get('option_price_coin', 0))
            
            # 🆕 更新希腊字母
            self.call_iv = call_info.get('iv', 0)
            self.put_iv = put_info.get('iv', 0)
            
            # 优先使用PA希腊字母
            self.call_delta = call_info.get('pa_delta', call_info.get('delta', 0))
            self.put_delta = put_info.get('pa_delta', put_info.get('delta', 0))
            self.call_gamma = call_info.get('pa_gamma', call_info.get('gamma', 0))
            self.put_gamma = put_info.get('pa_gamma', put_info.get('gamma', 0))
            self.call_vega = call_info.get('pa_vega', call_info.get('vega', 0))
            self.put_vega = put_info.get('pa_vega', put_info.get('vega', 0))
            
            # 构建返回信息
            greeks_info = {
                'call_option': {
                    'price': self.call_price,
                    'iv': self.call_iv,
                    'delta': self.call_delta,
                    'gamma': self.call_gamma,
                    'vega': self.call_vega
                },
                'put_option': {
                    'price': self.put_price,
                    'iv': self.put_iv,
                    'delta': self.put_delta,
                    'gamma': self.put_gamma,
                    'vega': self.put_vega
                }
            }
            
            if print_info:
                print(f"📊 Straddle希腊字母更新 - 时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"   Call: IV={self.call_iv:.1%}, Δ={self.call_delta:.3f}, Γ={self.call_gamma:.6f}, υ={self.call_vega:.6f}")
                print(f"   Put: IV={self.put_iv:.1%}, Δ={self.put_delta:.3f}, Γ={self.put_gamma:.6f}, υ={self.put_vega:.6f}")
                print(f"   净Delta: {self.get_net_delta():+.3f}")
            
            return True, "success", greeks_info
            
        except Exception as e:
            if print_info:
                print(f"❌ 更新希腊字母失败: {e}")
            return False, f"exception: {str(e)}", None
    
    def update_pnl(self, current_time, current_df, current_spot_price=None, current_atm_options=None, print_info=False):
        """
        更新当前盈亏 - 增强版本，同时更新希腊字母
        """
        if not self.is_active:
            if print_info:
                print("⚠️  组合已平仓，无法更新P&L")
            return False, "position_closed"
        
        # 检查期权是否已到期
        current_date = current_time.date()
        expired_options = []
        
        for position, symbol in self.option_symbols.items():
            expiry_date = parse_option_expiry_date(symbol)
            if expiry_date and current_date >= expiry_date:
                expired_options.append((position, symbol, expiry_date))
        
        if expired_options:
            if print_info:
                print(f"⚠️  以下期权已到期:")
                for pos, sym, exp_date in expired_options:
                    print(f"     {pos}: {sym} (到期日: {exp_date})")
            return False, "options_expired"
        
        # 🆕 先更新希腊字母
        greeks_success, greeks_reason, greeks_info = self.update_greeks(
            current_time, current_df, current_atm_options, print_info=False
        )
        
        if not greeks_success:
            if print_info:
                print(f"⚠️  无法更新希腊字母: {greeks_reason}")
            return False, greeks_reason
        

        current_premium = self.call_price + self.put_price
        
        # 计算期权P&L
        if "long" in self.strategy_type:
            self.current_options_pnl = current_premium - self.entry_premium
        else:
            self.current_options_pnl = self.entry_premium - current_premium

            
            self.last_update_time = current_time
        
        # 🆕 更新Delta对冲P&L（如果启用）
        if self.delta_hedge_enabled and current_spot_price:
            # 复用calendar_pair的对冲逻辑
            self.inverse_perpetual_pnl, self.realized_perpetual_pnl = self.update_hedge(current_spot_price=current_spot_price)
        else:
            self.inverse_perpetual_pnl = 0.0
            self.realized_perpetual_pnl = 0.0
        
        self.current_pnl = self.current_options_pnl + self.inverse_perpetual_pnl + self.realized_perpetual_pnl

            
        if print_info:
            print(f"📊 Straddle P&L更新 - 时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"   策略类型: {self.strategy_type.replace('_', ' ').title()}")
            print(f"   执行价格: ${self.strike_price:,.2f}")
            print(f"   入场权利金: {self.entry_premium:.6f} BTC")
            print(f"   当前权利金: {current_premium:.6f} BTC")
            print(f"   期权P&L: {self.current_options_pnl:.6f} BTC")

    
        # 🆕 添加Delta对冲信息
        if self.delta_hedge_enabled:
            print(f"   永续P&L: {self.inverse_perpetual_pnl:.6f} BTC")
            print(f"   已实现P&L: {self.realized_perpetual_pnl:.6f} BTC")
            print(f"   总P&L: {self.current_pnl:.6f} BTC")
            print(f"   对冲合约: {self.current_hedge_delta:+.3f} BTC")
            print(f"   平均持仓价: ${self.average_hedge_spot_price:,.0f}")
            if current_spot_price:
                print(f"   当前现货价: ${current_spot_price:,.0f}")
        else:
            print(f"   总P&L: {self.current_options_pnl:.6f} BTC")
        
        print(f"   Call价格: {self.call_price:.6f} BTC (IV: {self.call_iv:.1%})")
        print(f"   Put价格: {self.put_price:.6f} BTC (IV: {self.put_iv:.1%})")
        print(f"   净Delta: {self.get_net_delta():+.3f}")
                
        if current_spot_price:
            print(f"   现货价格: ${current_spot_price:,.2f}")
            print(f"   价格变化: {(current_spot_price - self.entry_spot_price) / self.entry_spot_price * 100:+.2f}%")
            moneyness = current_spot_price / self.strike_price
            print(f"   Moneyness: {moneyness:.3f}")
            
        return True, "success"
            
    def get_net_delta(self):
        """获取组合净Delta"""
        if "long" in self.strategy_type:
            # Long Straddle: +Call Delta + Put Delta
            return self.call_delta + self.put_delta
        else:
            # Short Straddle: -Call Delta - Put Delta
            return -(self.call_delta + self.put_delta)
    
    def get_net_gamma(self):
        """获取组合净Gamma"""
        if "long" in self.strategy_type:
            # Long Straddle: +Call Gamma + Put Gamma
            return self.call_gamma + self.put_gamma
        else:
            # Short Straddle: -Call Gamma - Put Gamma
            return -(self.call_gamma + self.put_gamma)
    
    def get_net_vega(self):
        """获取组合净Vega"""
        if "long" in self.strategy_type:
            # Long Straddle: +Call Vega + Put Vega
            return self.call_vega + self.put_vega
        else:
            # Short Straddle: -Call Vega - Put Vega
            return -(self.call_vega + self.put_vega)
    
    def get_average_iv(self):
        """获取平均IV"""
        return (self.call_iv + self.put_iv) / 2
    
    def get_current_greeks_summary(self):
        """获取当前希腊字母摘要"""
        return {
            'net_delta': self.get_net_delta(),
            'net_gamma': self.get_net_gamma(),
            'net_vega': self.get_net_vega(),
            'average_iv': self.get_average_iv(),
            'call_greeks': {
                'iv': self.call_iv,
                'delta': self.call_delta,
                'gamma': self.call_gamma,
                'vega': self.call_vega
            },
            'put_greeks': {
                'iv': self.put_iv,
                'delta': self.put_delta,
                'gamma': self.put_gamma,
                'vega': self.put_vega
            }
        }
    
    def get_greeks_change_since_entry(self):
        """获取相对于入场时的希腊字母变化"""
        return {
            'delta_change': {
                'call': self.call_delta - self.entry_greeks['call_option']['delta'],
                'put': self.put_delta - self.entry_greeks['put_option']['delta'],
                'net': self.get_net_delta() - (self.entry_greeks['call_option']['delta'] + self.entry_greeks['put_option']['delta'])
            },
            'iv_change': {
                'call': self.call_iv - self.entry_greeks['call_option']['iv'],
                'put': self.put_iv - self.entry_greeks['put_option']['iv'],
                'average': self.get_average_iv() - (self.entry_greeks['call_option']['iv'] + self.entry_greeks['put_option']['iv']) / 2
            }
        }
    
    # 🆕 复用calendar_pair的对冲方法
    def calculate_hedge_pnl(self, cost_spot_price, current_spot_price, hedge_size):
        """计算对冲P&L - 复用calendar_pair逻辑"""
        if hedge_size > 0:
            pnl_dollar = hedge_size * (current_spot_price - cost_spot_price)
            pnl = pnl_dollar / current_spot_price
        else:
            pnl_dollar = abs(hedge_size) * (cost_spot_price - current_spot_price)
            pnl = pnl_dollar / current_spot_price
        return pnl

    def update_hedge(self, current_spot_price=None):
        """
        更新Delta对冲 - 复用calendar_pair逻辑
        """
        if not self.delta_hedge_enabled:
            return 0.0, 0.0
        
        new_delta = self.get_net_delta()
        required_delta = -new_delta
        
        # 检查是否需要调整对冲
        if abs(self.current_delta) != 0 or abs(self.current_hedge_delta) != 0:
            assert (abs(self.current_delta) == abs(self.current_hedge_delta)
                    and self.current_delta * self.current_hedge_delta < 0), \
                    f"Delta对冲不平衡 with self.current_delta: {self.current_delta} and self.current_hedge_delta: {self.current_hedge_delta}"

        # 如果不需要重新对冲
        if abs(required_delta - self.current_hedge_delta) <= self.delta_threshold:
            self.inverse_perpetual_pnl = self.calculate_hedge_pnl(
                cost_spot_price=self.average_hedge_spot_price, 
                current_spot_price=current_spot_price, 
                hedge_size=self.current_hedge_delta
            )
            return self.inverse_perpetual_pnl, self.realized_perpetual_pnl 
        
        # 需要重新对冲 - 完整复制calendar_pair逻辑
        if self.current_delta >= 0 and new_delta >= 0:
            if new_delta > self.current_delta:
                more_delta_to_short = new_delta - self.current_delta
                # 计算新的平均对冲价格（加权平均）
                numerator = abs(self.current_hedge_delta) * self.average_hedge_spot_price + more_delta_to_short * current_spot_price
                denominator = abs(self.current_hedge_delta) + more_delta_to_short
                self.average_hedge_spot_price = numerator / denominator
                
                self.current_delta = new_delta
                self.current_hedge_delta = -self.current_delta
                self.inverse_perpetual_pnl = self.calculate_hedge_pnl(
                    cost_spot_price=self.average_hedge_spot_price, 
                    current_spot_price=current_spot_price, 
                    hedge_size=self.current_hedge_delta
                )
            
            else:
                delta_to_remove = self.current_delta - new_delta  # > 0 
                self.realized_perpetual_pnl += self.calculate_hedge_pnl(
                    cost_spot_price=self.average_hedge_spot_price, 
                    current_spot_price=current_spot_price, 
                    hedge_size=-delta_to_remove
                )
                
                self.current_delta = new_delta 
                self.current_hedge_delta += delta_to_remove

                if abs(self.current_delta) != 0 or abs(self.current_hedge_delta) != 0:
                    assert (abs(self.current_delta) == abs(self.current_hedge_delta)
                            and self.current_delta * self.current_hedge_delta < 0), \
                            f"Delta对冲不平衡 with self.current_delta: {self.current_delta} and self.current_hedge_delta: {self.current_hedge_delta}"

        elif self.current_delta <= 0 and new_delta <= 0:
            if new_delta < self.current_delta:
                more_delta_to_long = self.current_delta - new_delta
                # 计算新的平均对冲价格（加权平均）
                numerator = abs(self.current_hedge_delta) * self.average_hedge_spot_price + more_delta_to_long * current_spot_price
                denominator = abs(self.current_hedge_delta) + more_delta_to_long
                self.average_hedge_spot_price = numerator / denominator
                
                self.current_delta = new_delta
                self.current_hedge_delta = -self.current_delta
                self.inverse_perpetual_pnl = self.calculate_hedge_pnl(
                    cost_spot_price=self.average_hedge_spot_price, 
                    current_spot_price=current_spot_price, 
                    hedge_size=self.current_hedge_delta
                )
            else:
                delta_to_remove = new_delta - self.current_delta  # > 0
                self.realized_perpetual_pnl += self.calculate_hedge_pnl(
                    cost_spot_price=self.average_hedge_spot_price, 
                    current_spot_price=current_spot_price, 
                    hedge_size=delta_to_remove
                )
                
                self.current_delta = new_delta 
                self.current_hedge_delta -= delta_to_remove

                if abs(self.current_delta) != 0 or abs(self.current_hedge_delta) != 0:
                    assert (abs(self.current_delta) == abs(self.current_hedge_delta)
                            and self.current_delta * self.current_hedge_delta < 0), \
                            f"Delta对冲不平衡 with self.current_delta: {self.current_delta} and self.current_hedge_delta: {self.current_hedge_delta}"
        
        # 跨象限调整（从正Delta变负Delta或反之）
        else:
            # 先平掉原有对冲
            self.realized_perpetual_pnl += self.calculate_hedge_pnl(
                cost_spot_price=self.average_hedge_spot_price, 
                current_spot_price=current_spot_price, 
                hedge_size=self.current_hedge_delta
            )
            
            # 重新开始新的对冲
            self.average_hedge_spot_price = current_spot_price
            self.current_delta = new_delta
            self.current_hedge_delta = -self.current_delta
            self.inverse_perpetual_pnl = 0.0  # 新的对冲开始时P&L为0

        return self.inverse_perpetual_pnl, self.realized_perpetual_pnl
    
    def should_close(self, 
                    current_time, 
                    current_spot_price=None, 
                    predicted_vol=None,
                    max_loss_pct=0.3, 
                    target_profit_pct=0.5, 
                    price_threshold_pct=0.15, 
                    iv_reversal_close=True, 
                    max_delta_threshold=0.3, 
                    inti_BTC = 1.0):
        """
        Straddle平仓条件检查 - 增强版本
        """
        if not self.is_active:
            return False, "已平仓"
        
        # 🆕 IV反转检查（对于Short Straddle特别重要）
        if iv_reversal_close:
            if "short" in self.strategy_type:
                entry_avg_iv = (self.entry_greeks['call_option']['iv'] + self.entry_greeks['put_option']['iv']) / 2
                current_avg_iv = self.get_average_iv()
                
                # 如果IV大幅下降（Short Straddle获利信号）
                iv_decline = entry_avg_iv - current_avg_iv
                if iv_decline > 0.10:  # IV下降超过10%
                    return True, f"IV大幅下降平仓 (IV下降: {iv_decline:.1%})"
            else:
                entry_avg_iv = (self.entry_greeks['call_option']['iv'] + self.entry_greeks['put_option']['iv']) / 2
                current_avg_iv = self.get_average_iv()
                
                iv_increase = current_avg_iv - entry_avg_iv

                if iv_increase > 0.10:  # IV上升超过10%
                    return True, f"IV大幅上升平仓 (IV上升: {iv_increase:.1%})"
                # get current realized vol
                assert predicted_vol is not None, "predicted_vol is None"
                if current_avg_iv > predicted_vol * (1 + 0.015):
                    return True, f"IV大幅上升平仓 (IV上升: {iv_increase:.1%})"

        
        # 计算P&L百分比
        if abs(self.entry_premium) > 1e-8:
            pnl_pct = self.current_pnl / abs(self.entry_premium)
        else:
            pnl_pct = 0
        
        # 止损条件
        if pnl_pct < -max_loss_pct:
            return True, f"止损 (P&L: {pnl_pct*100:.1f}%)"
        
        # 止盈条件
        if pnl_pct > target_profit_pct:
            return True, f"止盈 (P&L: {pnl_pct*100:.1f}%)"

        
        # 🆕 Delta风险控制 - 净Delta过大时强制平仓
        
        if self.delta_hedge_enabled:
            current_net_delta = self.get_net_delta()
            if abs(current_net_delta) > max_delta_threshold * inti_BTC:
                if abs(self.current_hedge_delta) > 1:
                    print(f"Delta风险过大强制平仓 (净Delta: {current_net_delta:+.3f} BTC > ±{max_delta_threshold:.1f})")
                    print(f"self.current_hedge_delta: {self.current_hedge_delta}")
                    print(f"call option delta: {self.call_delta}")
                    print(f"put option delta: {self.put_delta}")
                    exit(0)
                return True, f"Delta风险过大强制平仓 (净Delta: {current_net_delta:+.3f} BTC > ±{max_delta_threshold:.1f})"
        
        # Straddle特有的平仓条件
        if current_spot_price is not None:
            price_move_pct = abs(current_spot_price - self.strike_price) / self.strike_price
            
            if "long" in self.strategy_type:
                # Long Straddle: 价格大幅偏离执行价格时可能获利
                if price_move_pct > price_threshold_pct:
                    direction = "上涨" if current_spot_price > self.strike_price else "下跌"
                    return True, f"价格大幅{direction} (偏离执行价{price_move_pct*100:.1f}%)"
            else:
                # Short Straddle: 价格靠近执行价格时获利，远离时亏损
                if price_move_pct > price_threshold_pct:
                    direction = "上涨" if current_spot_price > self.strike_price else "下跌"
                    return True, f"价格大幅{direction}，风险增加 (偏离执行价{price_move_pct*100:.1f}%)"
        
        # 🆕 时间衰减保护
        expiry_date = parse_option_expiry_date(self.option_symbols['call'])
        if expiry_date:
            days_to_expiry = (expiry_date - current_time.date()).days
            
            # 临近到期强制平仓
            if days_to_expiry <= 1:
                return True, f"临近到期强制平仓 (剩余: {days_to_expiry}天)"
            
            # Short Straddle在最后2天时，如果盈利则考虑平仓锁定利润
            if "short" in self.strategy_type and days_to_expiry <= 2 and pnl_pct > 0.1:
                return True, f"Short Straddle临近到期获利平仓 (剩余: {days_to_expiry}天, P&L: {pnl_pct*100:.1f}%)"
        
        return False, "持续持有"
    
    def close(self, close_time=None, close_reason="手动平仓", current_spot_price=None):
        """
        平仓 - 包含Delta对冲平仓
        """
        if not self.is_active:
            return None
        
        # 🆕 记录平仓前的对冲信息
        closing_hedge_size = self.current_hedge_delta if self.delta_hedge_enabled else 0
        closing_average_price = self.average_hedge_spot_price if self.delta_hedge_enabled else 0
        
        # 🆕 如果启用Delta对冲，先平掉永续合约
        if self.delta_hedge_enabled and current_spot_price and "missing_greeks" not in close_reason:
            # 平掉永续合约，实现最终P&L
            final_hedge_pnl = self.calculate_hedge_pnl(
                cost_spot_price=self.average_hedge_spot_price, 
                current_spot_price=current_spot_price, 
                hedge_size=self.current_hedge_delta
            )
            self.realized_perpetual_pnl += final_hedge_pnl
            self.inverse_perpetual_pnl = 0.0
        
        # print(f"self.realized_perpetual_pnl: {self.realized_perpetual_pnl}")
        
        # 计算各个合约的盈亏
        if "long" in self.strategy_type:
            # Long Straddle: 买入合约，价格上涨盈利
            contract_pnl = {
                'call': self.call_price - self.option_entry_prices['call'],  # 当前价格 - 买入价格
                'put': self.put_price - self.option_entry_prices['put']
            }
        else:
            # Short Straddle: 卖出合约，价格下跌盈利  
            contract_pnl = {
                'call': self.option_entry_prices['call'] - self.call_price,  # 卖出价格 - 当前价格
                'put': self.option_entry_prices['put'] - self.put_price
            }
        
        # 计算最终总P&L
        if self.delta_hedge_enabled:
            final_total_pnl = self.current_options_pnl + self.realized_perpetual_pnl
        else:
            final_total_pnl = self.current_options_pnl
        
        close_info = {
            'entry_time': self.entry_time,
            'close_time': close_time or self.last_update_time,
            'strategy_type': self.strategy_type,
            'strike_price': self.strike_price,
            'entry_premium': self.entry_premium,
            'final_options_pnl': self.current_options_pnl,
            'final_hedge_pnl': self.realized_perpetual_pnl if self.delta_hedge_enabled else 0.0,
            'final_total_pnl': final_total_pnl,
            'close_reason': close_reason,
            'pnl_options_pct': self.current_options_pnl / abs(self.entry_premium) if abs(self.entry_premium) > 1e-8 else 0,
            'pnl_total_pct': final_total_pnl / abs(self.entry_premium) if abs(self.entry_premium) > 1e-8 else 0,
            'contract_pnl': contract_pnl,
            'delta_hedge_enabled': self.delta_hedge_enabled,
            # 🆕 添加对冲平仓信息
            'closing_hedge_size': closing_hedge_size,
            'closing_average_price': closing_average_price,
            'closing_spot_price': current_spot_price
        }
        
        self.is_active = False
        return close_info
    
    def calculate_breakeven_points(self):
        """计算盈亏平衡点"""
        premium_total = abs(self.entry_premium)
        
        if "long" in self.strategy_type:
            # Long Straddle盈亏平衡点: Strike ± Premium
            upper_breakeven = self.strike_price + premium_total
            lower_breakeven = self.strike_price - premium_total
        else:
            # Short Straddle盈亏平衡点: Strike ± Premium
            upper_breakeven = self.strike_price + premium_total
            lower_breakeven = self.strike_price - premium_total
        
        return {
            'upper_breakeven': upper_breakeven,
            'lower_breakeven': lower_breakeven,
            'strike_price': self.strike_price,
            'premium_paid': premium_total
        }
    
    def get_current_status(self):
        """获取当前状态信息"""
        return {
            'is_active': self.is_active,
            'strategy_type': self.strategy_type,
            'entry_time': self.entry_time,
            'entry_spot_price': self.entry_spot_price,
            'strike_price': self.strike_price,
            'entry_premium': self.entry_premium,
            'current_options_pnl': self.current_options_pnl,
            'current_pnl': self.current_pnl,
            'last_update_time': self.last_update_time,
            'call_price': self.call_price,
            'put_price': self.put_price,
            'option_symbols': self.option_symbols.copy()
        }
