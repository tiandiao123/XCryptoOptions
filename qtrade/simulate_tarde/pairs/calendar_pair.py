import re
from datetime import datetime, date
from qtrade.data_utils import get_option_open_price


def find_atm_calendar_pair(atm_options, spot_price=None, min_days_gap=7, atm_tolerance=0.03, min_iv_spread=0.02):
    """
    寻找最佳单向Calendar Spread期权组合 - 选择IV价差最大的策略
    
    Args:
        atm_options: ATM期权列表
        spot_price: 现货价格（可选）
        min_days_gap: 最小时间间隔（天）
        atm_tolerance: ATM容忍度（改为3%，更严格）
        min_iv_spread: 最小IV价差要求（2%）
    """
    
    if not atm_options or len(atm_options) < 2:
        return False
    
    # 获取现货价格
    if spot_price is None:
        spot_price = atm_options[0]['spot_open']
    
    # 🚀 步骤1：高效数据预处理 - 按到期时间和期权类型分组
    grouped_data = _group_options_by_expiry_and_type(atm_options)
    
    if len(grouped_data) < 2:
        return False
    
    # 🎯 步骤2：获取有潜力的时间配对
    promising_pairs = _get_promising_time_pairs(grouped_data, min_days_gap)

    
    if not promising_pairs:
        return False
    
    # 🔍 步骤3：高效寻找最佳Calendar组合
    best_combination = _find_best_calendar_combination(
        grouped_data, promising_pairs, spot_price, atm_tolerance
    )


    
    # 🔧 添加最小IV价差检查
    if not best_combination or best_combination['iv_spread'] < min_iv_spread:
        return False
    
    # 🏆 步骤4：构建最终结果
    return _build_calendar_result(best_combination, spot_price)


def _group_options_by_expiry_and_type(atm_options):
    """
    高效分组：按到期时间和期权类型分组
    
    Returns:
        dict: {
            days_to_expiry: {
                'C': [call_options],
                'P': [put_options]
            }
        }
    """
    grouped = {}
    
    for option in atm_options:
        days = option['days_to_expiry']
        option_type = option['option_type']
        
        if days not in grouped:
            grouped[days] = {'C': [], 'P': []}
        
        grouped[days][option_type].append(option)
    
    # 🔧 优化：预先按strike排序，便于后续ATM匹配
    for days in grouped:
        for opt_type in ['C', 'P']:
            grouped[days][opt_type].sort(key=lambda x: x['strike_price'])
    
    return grouped


def _get_promising_time_pairs(grouped_data, min_days_gap):
    """
    简化搜索：预定义的时间配对策略
    
    策略组合：
    - 7天 vs 1个月 (25-35天)
    - 14天 vs 1个月 (25-35天) 
    - 14天 vs 2个月 (55-70天)
    - 14天 vs 3个月 (85-95天)
    
    Returns:
        list: [(short_days, long_days), ...]
    """
    available_expiries = sorted(grouped_data.keys())
    
    # 🎯 预定义策略配对
    predefined_strategies = [
        {
            'name': '7D_vs_1M',
            'short_range': (5, 10),      # 7天左右 (5-10天)
            'long_range': (25, 35)       # 1个月左右 (25-35天)
        },
        {
            'name': '14D_vs_1M', 
            'short_range': (12, 18),     # 14天左右 (12-18天)
            'long_range': (25, 35)       # 1个月左右 (25-35天)
        },
        {
            'name': '14D_vs_2M',
            'short_range': (12, 18),     # 14天左右 (12-18天)
            'long_range': (55, 70)       # 2个月左右 (55-70天)
        },
        {
            'name': '14D_vs_3M',
            'short_range': (12, 18),     # 14天左右 (12-18天)  
            'long_range': (85, 95)       # 3个月左右 (85-95天)
        }
    ]
    
    promising_pairs = []
    
    for strategy in predefined_strategies:
        short_range = strategy['short_range']
        long_range = strategy['long_range']
        
        # 找到符合范围的到期时间
        short_candidates = [d for d in available_expiries 
                          if short_range[0] <= d <= short_range[1]]
        long_candidates = [d for d in available_expiries 
                         if long_range[0] <= d <= long_range[1]]
        
        if not short_candidates or not long_candidates:
            continue
        
        # 选择最接近目标的时间
        short_target = (short_range[0] + short_range[1]) / 2
        long_target = (long_range[0] + long_range[1]) / 2
        
        best_short = min(short_candidates, key=lambda x: abs(x - short_target))
        best_long = min(long_candidates, key=lambda x: abs(x - long_target))
        
        # 🎯 简化：跳过IV检查，直接添加配对
        promising_pairs.append((best_short, best_long, strategy['name']))
    
    # 去重（可能有相同的时间配对）
    unique_pairs = []
    seen = set()
    
    for short_days, long_days, strategy_name in promising_pairs:
        pair_key = (short_days, long_days)
        if pair_key not in seen:
            seen.add(pair_key)
            unique_pairs.append((short_days, long_days, strategy_name))
    
    return unique_pairs


def _find_best_calendar_combination(grouped_data, promising_pairs, spot_price, atm_tolerance):
    """
    简化版：在预定义策略中寻找最佳Calendar组合
    
    Returns:
        dict or None: 最佳组合信息
    """
    best_iv_spread = -float('inf')
    best_combination = None
    
    # 计算ATM价格范围
    atm_range = (
        spot_price * (1 - atm_tolerance),
        spot_price * (1 + atm_tolerance)
    )
    
    for short_days, long_days, strategy_name in promising_pairs:
        short_data = grouped_data[short_days]
        long_data = grouped_data[long_days]
        
        # 🔍 分别检查Call和Put Calendar
        for option_type in ['C', 'P']:
            short_options = short_data[option_type]
            long_options = long_data[option_type]
            
            if not short_options or not long_options:
                continue
            
            # 🎯 ATM筛选
            short_atm = [opt for opt in short_options 
                        if atm_range[0] <= opt['strike_price'] <= atm_range[1]]
            long_atm = [opt for opt in long_options 
                       if atm_range[0] <= opt['strike_price'] <= atm_range[1]]
            
            if not short_atm or not long_atm:
                continue
            
            # 🚀 高效配对：找到最佳IV价差
            best_pair = _find_best_atm_pair(short_atm, long_atm, spot_price)
            
            if best_pair and best_pair['iv_spread'] > best_iv_spread:
                best_iv_spread = best_pair['iv_spread']
                best_combination = {
                    'short_option': best_pair['short_option'],
                    'long_option': best_pair['long_option'],
                    'iv_spread': best_pair['iv_spread'],
                    'option_type': option_type,
                    'short_days': short_days,
                    'long_days': long_days,
                    'strategy_name': strategy_name,
                    'strategy_type': f"{option_type.lower()}_calendar"
                }
                
                # 🔥 早期退出优化：如果IV价差很大（>10%），直接返回
                if best_iv_spread > 0.10:
                    return best_combination
    
    return best_combination


def _find_best_atm_pair(short_atm_options, long_atm_options, spot_price):
    """
    在ATM期权中找到最佳配对 - 增强版本，包含执行价格合理性检查
    
    Returns:
        dict or None: 最佳配对信息
    """
    best_iv_spread = -float('inf')
    best_pair = None
    
    for short_opt in short_atm_options:
        for long_opt in long_atm_options:
            # 🔧 验证IV有效性
            if short_opt['iv'] <= 0 or long_opt['iv'] <= 0:
                continue
            
            # 🔧 验证执行价格合理性
            if not _validate_strike_prices(short_opt, long_opt, spot_price):
                continue
            
            iv_spread = short_opt['iv'] - long_opt['iv']
            
            # 🎯 🔧 修复：强制要求正向IV价差 (短期IV > 长期IV)
            if iv_spread <= 0:
                continue  # 跳过负向或零价差
            
            # 🎯 只考虑有正向IV价差的组合
            if iv_spread > best_iv_spread:
                best_iv_spread = iv_spread
                best_pair = {
                    'short_option': short_opt,
                    'long_option': long_opt,
                    'iv_spread': iv_spread,
                    'moneyness_diff': abs(short_opt['strike_price'] - spot_price) + 
                                    abs(long_opt['strike_price'] - spot_price)
                }
    
    return best_pair


def _validate_strike_prices(short_opt, long_opt, spot_price):
    """
    验证Calendar Spread的执行价格合理性
    
    Args:
        short_opt: 近月期权
        long_opt: 远月期权
        spot_price: 现货价格
        
    Returns:
        bool: 是否合理
    """
    short_strike = short_opt['strike_price']
    long_strike = long_opt['strike_price']
    option_type = short_opt['option_type']
    
    # 🎯 执行价格应该接近ATM（在±10%范围内）
    atm_tolerance = 0.10
    min_strike = spot_price * (1 - atm_tolerance)
    max_strike = spot_price * (1 + atm_tolerance)
    
    if not (min_strike <= short_strike <= max_strike):
        return False
    if not (min_strike <= long_strike <= max_strike):
        return False
    
    # 🎯 Calendar Spread执行价格关系检查
    if option_type == 'C':
        # Call Calendar: 执行价格应该相同或short ≥ long
        # 最好是相同执行价格，或者short略高于long
        if short_strike < long_strike:
            return False
        # 执行价格差不应该太大（最多5%）
        if (short_strike - long_strike) / spot_price > 0.05:
            return False
    else:  # Put Calendar
        # Put Calendar: 执行价格应该相同或short ≤ long  
        # 最好是相同执行价格，或者short略低于long
        if short_strike > long_strike:
            return False
        # 执行价格差不应该太大（最多5%）
        if (long_strike - short_strike) / spot_price > 0.05:
            return False
    
    return True


def _build_calendar_result(best_combination, spot_price):
    """构建最终Calendar结果"""
    short_opt = best_combination['short_option']
    long_opt = best_combination['long_option']
    option_type = best_combination['option_type']
    strategy_name = best_combination.get('strategy_name', 'unknown')
    
    # 计算入场权利金（Long远月 - Short近月）
    entry_premium = long_opt['open'] - short_opt['open']
    
    result = {
        'iv_condition_met': True,
        'spot_price': spot_price,
        'strategy_type': best_combination['strategy_type'],
        'strategy_name': strategy_name,  # 🆕 添加策略名称
        'option_type': option_type,
        
        # Calendar组合信息
        'calendar_spread': {
            'long_option': long_opt,    # 远月期权 (买入)
            'short_option': short_opt   # 近月期权 (卖出)
        },
        
        # 分析信息
        'analysis': {
            'short_term_days': best_combination['short_days'],
            'long_term_days': best_combination['long_days'],
            'short_term_iv': short_opt['iv'],
            'long_term_iv': long_opt['iv'],
            'iv_spread': best_combination['iv_spread'],
            'entry_premium': entry_premium,
            'strike_spread': abs(short_opt['strike_price'] - long_opt['strike_price']),
            'short_moneyness': short_opt['strike_price'] / spot_price,
            'long_moneyness': long_opt['strike_price'] / spot_price
        }
    }
    
    return result


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


class CalendarPair:
    def __init__(self, calendar_spread, entry_time, entry_spot_price):
        """单向Calendar Spread组合"""
        self.entry_time = entry_time
        self.entry_spot_price = entry_spot_price
        self.option_type = calendar_spread['long_option']['option_type']
        
        # 当前价格
        self.short_option_price = calendar_spread['short_option']['open']
        self.long_option_price = calendar_spread['long_option']['open']
        
        # 🆕 当前希腊字母
        self.long_option_iv = calendar_spread['long_option']['iv']
        self.short_option_iv = calendar_spread['short_option']['iv']
        self.long_option_delta = calendar_spread['long_option'].get('pa_delta', calendar_spread['long_option'].get('delta', 0))
        self.short_option_delta = calendar_spread['short_option'].get('pa_delta', calendar_spread['short_option'].get('delta', 0))
        self.long_option_gamma = calendar_spread['long_option'].get('pa_gamma', calendar_spread['long_option'].get('gamma', 0))
        self.short_option_gamma = calendar_spread['short_option'].get('pa_gamma', calendar_spread['short_option'].get('gamma', 0))
        self.long_option_vega = calendar_spread['long_option'].get('pa_vega', calendar_spread['long_option'].get('vega', 0))
        self.short_option_vega = calendar_spread['short_option'].get('pa_vega', calendar_spread['short_option'].get('vega', 0))
        
        # 🆕 入场时的希腊字母（用于对比）
        self.entry_greeks = {
            'long_option': {
                'price': calendar_spread['long_option']['open'],
                'iv': self.long_option_iv,
                'delta': self.long_option_delta,
                'gamma': self.long_option_gamma,
                'vega': self.long_option_vega
            },
            'short_option': {
                'price': calendar_spread['short_option']['open'],
                'iv': self.short_option_iv,
                'delta': self.short_option_delta,
                'gamma': self.short_option_gamma,
                'vega': self.short_option_vega
            }
        }
        
        # 保持向后兼容
        self.option_entry_prices = {
            'long_option': calendar_spread['long_option']['open'],
            'short_option': calendar_spread['short_option']['open']
        }
        
        # 入场价格 (Long - Short)
        self.entry_premium = (calendar_spread['long_option']['open'] - 
                             calendar_spread['short_option']['open'])
        
        # 盈亏跟踪
        self.current_pnl = 0.0
        self.is_active = True
        self.last_update_time = entry_time
        
        # 存储期权符号以便查询
        self.option_symbols = {
            'long_option': calendar_spread['long_option']['symbol'],
            'short_option': calendar_spread['short_option']['symbol']
        }
        
        # 存储执行价格用于风险管理
        self.short_strike = calendar_spread['short_option']['strike_price']
        self.long_strike = calendar_spread['long_option']['strike_price']
    
    def update_greeks(self, current_time, current_df, current_atm_options=None, print_info=False):
        """
        更新希腊字母信息
        
        Args:
            current_time: 当前时间点
            current_df: 当前时间点的期权数据DataFrame
            current_atm_options: 当前ATM期权列表（可选，优先使用）
            print_info: 是否打印详细信息
        
        Returns:
            tuple: (success, reason, greeks_info)
        """
        if not self.is_active:
            return False, "position_closed", None
        
        try:
            # 🆕 优先从ATM期权列表获取信息，备用DataFrame查询
            long_info = None
            short_info = None
            
            if current_atm_options:
                # 从ATM期权列表中查找
                for option in current_atm_options:
                    if option['symbol'] == self.option_symbols['long_option']:
                        long_info = option
                    elif option['symbol'] == self.option_symbols['short_option']:
                        short_info = option
            
            # 如果ATM列表中没找到，使用data_utils函数
            if not long_info:
                from qtrade.data_utils import get_option_full_info
                long_info = get_option_full_info(
                    current_df, 
                    self.option_symbols['long_option'], 
                    current_time, 
                    print_info=False
                )
            
            if not short_info:
                from qtrade.data_utils import get_option_full_info
                short_info = get_option_full_info(
                    current_df, 
                    self.option_symbols['short_option'], 
                    current_time, 
                    print_info=False
                )
            
            # 检查是否成功获取信息
            if not long_info or not short_info:
                missing = []
                if not long_info:
                    missing.append(self.option_symbols['long_option'])
                if not short_info:
                    missing.append(self.option_symbols['short_option'])
                
                return False, f"missing_greeks: {missing}", None
            
            # 🆕 更新价格
            self.long_option_price = long_info.get('open', long_info.get('option_price_coin', 0))
            self.short_option_price = short_info.get('open', short_info.get('option_price_coin', 0))
            
            # 🆕 更新希腊字母
            self.long_option_iv = long_info.get('iv', 0)
            self.short_option_iv = short_info.get('iv', 0)
            
            # 优先使用PA希腊字母
            self.long_option_delta = long_info.get('pa_delta', long_info.get('delta', 0))
            self.short_option_delta = short_info.get('pa_delta', short_info.get('delta', 0))
            self.long_option_gamma = long_info.get('pa_gamma', long_info.get('gamma', 0))
            self.short_option_gamma = short_info.get('pa_gamma', short_info.get('gamma', 0))
            self.long_option_vega = long_info.get('pa_vega', long_info.get('vega', 0))
            self.short_option_vega = short_info.get('pa_vega', short_info.get('vega', 0))
            
            # 构建返回信息
            greeks_info = {
                'long_option': {
                    'price': self.long_option_price,
                    'iv': self.long_option_iv,
                    'delta': self.long_option_delta,
                    'gamma': self.long_option_gamma,
                    'vega': self.long_option_vega
                },
                'short_option': {
                    'price': self.short_option_price,
                    'iv': self.short_option_iv,
                    'delta': self.short_option_delta,
                    'gamma': self.short_option_gamma,
                    'vega': self.short_option_vega
                }
            }
            
            if print_info:
                print(f"📊 希腊字母更新 - 时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"   Long: IV={self.long_option_iv:.1%}, Δ={self.long_option_delta:.3f}, Γ={self.long_option_gamma:.6f}, υ={self.long_option_vega:.6f}")
                print(f"   Short: IV={self.short_option_iv:.1%}, Δ={self.short_option_delta:.3f}, Γ={self.short_option_gamma:.6f}, υ={self.short_option_vega:.6f}")
                print(f"   净Delta: {self.get_net_delta():+.3f}")
            
            return True, "success", greeks_info
            
        except Exception as e:
            if print_info:
                print(f"❌ 更新希腊字母失败: {e}")
            return False, f"exception: {str(e)}", None
    
    def update_pnl(self, current_time, current_df, current_spot_price=None, current_atm_options=None, print_info=False):
        """
        更新当前盈亏 - 增强版本，同时更新希腊字母
        
        Args:
            current_time: 当前时间点
            current_df: 当前时间点的期权数据DataFrame
            current_spot_price: 当前现货价格（可选）
            current_atm_options: 当前ATM期权列表（可选）
            print_info: 是否打印详细信息
        
        Returns:
            tuple: (success, reason)
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
        
        # 计算当前组合价值 (Long - Short)
        current_premium = self.long_option_price - self.short_option_price
        
        # 计算P&L
        self.current_pnl = current_premium - self.entry_premium
        self.last_update_time = current_time
        
        if print_info:
            print(f"📊 Calendar P&L更新 - 时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"   策略类型: {self.option_type} Calendar")
            print(f"   入场权利金: {self.entry_premium:.6f} BTC")
            print(f"   当前权利金: {current_premium:.6f} BTC")
            print(f"   当前P&L: {self.current_pnl:.6f} BTC")
            print(f"   净Delta: {self.get_net_delta():+.3f}")
            if current_spot_price:
                print(f"   现货价格: ${current_spot_price:,.2f}")
                print(f"   价格变化: {(current_spot_price - self.entry_spot_price) / self.entry_spot_price * 100:+.2f}%")
        
        return True, "success"
    
    def get_net_delta(self):
        """获取组合净Delta"""
        return self.long_option_delta - self.short_option_delta
    
    def get_net_gamma(self):
        """获取组合净Gamma"""
        return self.long_option_gamma - self.short_option_gamma
    
    def get_net_vega(self):
        """获取组合净Vega"""
        return self.long_option_vega - self.short_option_vega
    
    def get_iv_spread(self):
        """获取IV价差 (短期IV - 长期IV)"""
        return self.short_option_iv - self.long_option_iv
    
    def get_current_greeks_summary(self):
        """获取当前希腊字母摘要"""
        return {
            'net_delta': self.get_net_delta(),
            'net_gamma': self.get_net_gamma(),
            'net_vega': self.get_net_vega(),
            'iv_spread': self.get_iv_spread(),
            'long_greeks': {
                'iv': self.long_option_iv,
                'delta': self.long_option_delta,
                'gamma': self.long_option_gamma,
                'vega': self.long_option_vega
            },
            'short_greeks': {
                'iv': self.short_option_iv,
                'delta': self.short_option_delta,
                'gamma': self.short_option_gamma,
                'vega': self.short_option_vega
            }
        }
    
    def get_greeks_change_since_entry(self):
        """获取相对于入场时的希腊字母变化"""
        return {
            'delta_change': {
                'long': self.long_option_delta - self.entry_greeks['long_option']['delta'],
                'short': self.short_option_delta - self.entry_greeks['short_option']['delta'],
                'net': self.get_net_delta() - (self.entry_greeks['long_option']['delta'] - self.entry_greeks['short_option']['delta'])
            },
            'iv_change': {
                'long': self.long_option_iv - self.entry_greeks['long_option']['iv'],
                'short': self.short_option_iv - self.entry_greeks['short_option']['iv'],
                'spread': self.get_iv_spread() - (self.entry_greeks['short_option']['iv'] - self.entry_greeks['long_option']['iv'])
            }
        }

    def get_current_status(self):
        """获取当前状态信息"""
        return {
            'is_active': self.is_active,
            'strategy_type': f"{self.option_type}_calendar",
            'entry_time': self.entry_time,
            'entry_spot_price': self.entry_spot_price,
            'entry_premium': self.entry_premium,
            'current_pnl': self.current_pnl,
            'last_update_time': self.last_update_time,
            'option_symbols': self.option_symbols.copy()
        }
    
    def should_close(self, current_time, current_spot_price=None, max_loss_pct=0.3, target_profit_pct=0.5, iv_reversal_close=True):
        """
        平仓条件检查 - 增强版本，包含IV价差反转检查
        
        Args:
            current_time: 当前时间
            current_spot_price: 当前现货价格
            max_loss_pct: 最大亏损百分比（相对于入场权利金）
            target_profit_pct: 目标盈利百分比
            iv_reversal_close: 是否启用IV价差反转平仓
            
        Returns:
            tuple: (should_close, reason)
        """
        if not self.is_active:
            return False, "已平仓"
        
        # 🆕 IV价差反转检查（最高优先级）
        if iv_reversal_close:
            entry_iv_spread = self.entry_greeks['short_option']['iv'] - self.entry_greeks['long_option']['iv']
            current_iv_spread = self.get_iv_spread()
            
            # 如果入场时IV价差为正（有利），但现在变为负值，立即平仓
            if entry_iv_spread > 0 and current_iv_spread < -0.01:
                return True, f"IV价差反转平仓 (入场: {entry_iv_spread:+.1%} → 当前: {current_iv_spread:+.1%})"
            
            # 🆕 额外检查：如果IV价差大幅收敛（超过80%），也考虑平仓
            # iv_convergence_threshold = 0.8  # 80%收敛阈值
            # if entry_iv_spread > 0:
            #     convergence_ratio = (entry_iv_spread - current_iv_spread) / entry_iv_spread
            #     if convergence_ratio > iv_convergence_threshold:
            #         return True, f"IV价差大幅收敛平仓 (收敛: {convergence_ratio*100:.1f}%, 当前价差: {current_iv_spread:+.1%})"
        
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
        
        # 🆕 时间衰减保护：如果接近短期期权到期且没有盈利，考虑平仓
        short_expiry_date = parse_option_expiry_date(self.option_symbols['short_option'])
        if short_expiry_date:
            days_to_short_expiry = (short_expiry_date - current_time.date()).days
            
            # 短期期权还有1天到期，且P&L为负，平仓避免更大损失
            if days_to_short_expiry <= 1 and pnl_pct < 0:
                return True, f"短期期权即将到期且亏损平仓 (剩余: {days_to_short_expiry}天, P&L: {pnl_pct*100:.1f}%)"
        
        return False, "持续持有"
    
    def close(self, close_time=None, close_reason="手动平仓"):
        """
        平仓
        
        Returns:
            dict: 平仓信息
        """
        if not self.is_active:
            return None
        
        # 计算各个合约的盈亏
        contract_pnl = {
            'long_option': self.long_option_price - self.option_entry_prices['long_option'],
            'short_option': self.option_entry_prices['short_option'] - self.short_option_price
        }
        
        close_info = {
            'entry_time': self.entry_time,
            'close_time': close_time or self.last_update_time,
            'strategy_type': f"{self.option_type}_calendar",
            'entry_premium': self.entry_premium,
            'final_pnl': self.current_pnl,
            'close_reason': close_reason,
            'pnl_pct': self.current_pnl / abs(self.entry_premium) if abs(self.entry_premium) > 1e-8 else 0,
            'contract_pnl': contract_pnl
        }
        
        self.is_active = False
        return close_info
