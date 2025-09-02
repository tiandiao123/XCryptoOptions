import re
from datetime import datetime, date
from qtrade.data_utils import get_option_open_price


def find_calendar_iron_spread_options(atm_options):
    '''
    寻找日历对角价差期权组合 - 选择IV价差最大的策略
    
    策略逻辑：
    1. 检查波动率条件：近月IV > 远月IV 
    2. 评估所有策略配对，选择IV价差最大的
    3. 构建4腿组合：
       - Call Calendar Diagonal: Long远月ATM Call + Short近月OTM Call
       - Put Calendar Diagonal: Long远月ATM Put + Short近月OTM Put
    
    Args:
        atm_options: ATM期权列表，每个包含symbol, strike_price, option_type, 
                    days_to_expiry, iv, delta, spot_open等信息
    
    Returns:
        dict or False: 如果找到合适组合返回字典，否则返回False
        返回IV价差最大的策略组合
    '''
    
    if not atm_options or len(atm_options) < 4:
        return False
    
    # 获取现货价格
    spot_price = atm_options[0]['spot_open']
    
    # 按到期时间分组
    options_by_expiry = {}
    for option in atm_options:
        days = option['days_to_expiry']
        if days not in options_by_expiry:
            options_by_expiry[days] = []
        options_by_expiry[days].append(option)
    
    # 获取可用的到期时间（排序）
    available_expiries = sorted(options_by_expiry.keys())
    
    if len(available_expiries) < 2:
        return False
    
    # 定义所有策略
    strategies = [
        {
             'name': '15D_vs_1M',
             'short_range': (12, 18),    # 15天左右 (12-18天)
             'long_range': (25, 35)      # 1个月左右 (25-35天)
        },
        {
            'name': '14D_vs_2M',
            'short_range': (10, 18),    # 14天左右 (10-18天)
            'long_range': (55, 70)      # 2个月左右 (55-70天)
        },
        {
            'name': '7D_vs_30D',
            'short_range': (5, 10),    # 7天左右 (5-10天)
            'long_range': (25, 35)      # 30天左右 (25-35天)
        },
        {
            'name': '1M_vs_3M', 
            'short_range': (25, 35),    # 1个月左右 (25-35天)
            'long_range': (85, 95)      # 3个月左右 (85-95天)
        }
    ]
    
    # 🆕 存储所有有效的策略组合
    valid_strategies = []
    
    # 🆕 评估每种策略
    for strategy in strategies:
        short_range = strategy['short_range']
        long_range = strategy['long_range']
        
        # 找到符合范围的到期时间
        short_expiries = [d for d in available_expiries 
                        if short_range[0] <= d <= short_range[1]]
        long_expiries = [d for d in available_expiries 
                       if long_range[0] <= d <= long_range[1]]
        
        if not short_expiries or not long_expiries:
            continue
        
        # 选择最接近目标的时间
        short_target = (short_range[0] + short_range[1]) / 2
        long_target = (long_range[0] + long_range[1]) / 2
        
        best_short = min(short_expiries, key=lambda x: abs(x - short_target))
        best_long = min(long_expiries, key=lambda x: abs(x - long_target))
        
        short_options = options_by_expiry[best_short]
        long_options = options_by_expiry[best_long]
        
        # 计算平均IV
        short_iv_avg = sum(opt['iv'] for opt in short_options) / len(short_options)
        long_iv_avg = sum(opt['iv'] for opt in long_options) / len(long_options)
        
        # 检查波动率条件：近月IV > 远月IV
        if short_iv_avg <= long_iv_avg:
            continue
        
        # 计算IV价差
        iv_spread = short_iv_avg - long_iv_avg
        
        # 尝试构建期权组合
        strategy_result = _build_strategy_combination(
            strategy, short_options, long_options, spot_price, 
            best_short, best_long, short_iv_avg, long_iv_avg, iv_spread
        )
        
        if strategy_result:
            valid_strategies.append(strategy_result)
    
    # 🆕 如果没有有效策略，返回False
    if not valid_strategies:
        return False
    
    # 🆕 按IV价差排序，选择最大的
    valid_strategies.sort(key=lambda x: x['analysis']['iv_spread'], reverse=True)
    best_strategy = valid_strategies[0]
    
    # 🆕 添加策略选择信息
    best_strategy['strategy_selection'] = {
        'total_candidates': len(valid_strategies),
        'selected_reason': f"最大IV价差: {best_strategy['analysis']['iv_spread']:.1%}",
        'all_candidates': [
            {
                'strategy': s['strategy_type'],
                'iv_spread': s['analysis']['iv_spread'],
                'short_days': s['analysis']['short_term_days'],
                'long_days': s['analysis']['long_term_days']
            }
            for s in valid_strategies
        ]
    }
    
    return best_strategy


def _build_strategy_combination(strategy, short_options, long_options, spot_price, 
                               best_short, best_long, short_iv_avg, long_iv_avg, iv_spread):
    """
    构建具体的策略组合
    
    Returns:
        dict or None: 策略组合信息，失败则返回None
    """
    try:
        # 1. 寻找远月ATM期权（Call和Put）
        long_calls = [opt for opt in long_options if opt['option_type'] == 'C' and opt['strike_price'] >= spot_price]
        long_puts = [opt for opt in long_options if opt['option_type'] == 'P' and opt['strike_price'] <= spot_price]
        
        if not long_calls or not long_puts:
            return None
            
        long_atm_call = min(long_calls, 
                          key=lambda x: abs(x['strike_price'] - spot_price))
        long_atm_put = min(long_puts, 
                         key=lambda x: abs(x['strike_price'] - spot_price))
        
        # 2. 寻找近月OTM期权
        short_calls = [opt for opt in short_options if opt['option_type'] == 'C']
        short_puts = [opt for opt in short_options if opt['option_type'] == 'P']
        
        # 近月OTM Call: strike >= long_call_strike
        spread_tolerance_pct = 0.0
        short_otm_calls = [opt for opt in short_calls 
                          if opt['strike_price'] >= long_atm_call['strike_price'] * (1 + spread_tolerance_pct)]
        # 近月OTM Put: strike <= long_put_strike
        short_otm_puts = [opt for opt in short_puts 
                         if opt['strike_price'] <= long_atm_put['strike_price'] * (1 - spread_tolerance_pct)]
        
        if not short_otm_calls or not short_otm_puts:
            return None
        
        # 选择最接近ATM但仍OTM的期权
        short_otm_call = min(short_otm_calls, 
                           key=lambda x: x['strike_price'] - spot_price)
        short_otm_put = max(short_otm_puts, 
                          key=lambda x: x['strike_price'])
        
        # 3. 构建最终组合
        result = {
            'iv_condition_met': True,
            'spot_price': spot_price,
            'strategy_type': strategy['name'],
            'call_diagonal': {
                'long_call': long_atm_call,    # 远月ATM Call (买入)
                'short_call': short_otm_call   # 近月OTM Call (卖出)
            },
            'put_diagonal': {
                'long_put': long_atm_put,      # 远月ATM Put (买入)
                'short_put': short_otm_put     # 近月OTM Put (卖出)
            },
            'analysis': {
                'short_term_days': best_short,
                'long_term_days': best_long,
                'near_term_iv': short_iv_avg,
                'long_term_iv': long_iv_avg,
                'iv_spread': iv_spread,
                'call_strike_spread': short_otm_call['strike_price'] - long_atm_call['strike_price'],
                'put_strike_spread': long_atm_put['strike_price'] - short_otm_put['strike_price']
            }
        }
        
        return result
        
    except Exception as e:
        # print(f"构建策略组合失败: {e}")
        return None


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

class CalendarIronPair:
    def __init__(self, call_diagonal, put_diagonal, entry_time, entry_spot_price):
        """日历对角价差组合"""
        self.entry_time = entry_time
        self.entry_spot_price = entry_spot_price
        
        # 当前价格
        self.short_term_call_price = call_diagonal['short_call']['open']
        self.short_term_put_price = put_diagonal['short_put']['open']
        self.long_term_call_price = call_diagonal['long_call']['open']
        self.long_term_put_price = put_diagonal['long_put']['open']
        
        # 🆕 存储各个合约的入场价格
        self.option_entry_prices = {
            'long_call': call_diagonal['long_call']['open'],
            'short_call': call_diagonal['short_call']['open'],
            'long_put': put_diagonal['long_put']['open'],
            'short_put': put_diagonal['short_put']['open']
        }
        
        # 入场价格
        self.entry_premium = (call_diagonal['long_call']['open'] + 
                             put_diagonal['long_put']['open'] -
                             call_diagonal['short_call']['open'] - 
                             put_diagonal['short_put']['open'])
        
        # 盈亏跟踪
        self.current_pnl = 0.0
        self.is_active = True
        self.last_update_time = entry_time
        
        # 存储期权符号以便查询
        self.option_symbols = {
            'long_call': call_diagonal['long_call']['symbol'],
            'short_call': call_diagonal['short_call']['symbol'],
            'long_put': put_diagonal['long_put']['symbol'],
            'short_put': put_diagonal['short_put']['symbol']
        }
        
        # 存储执行价格用于风险管理
        self.short_call_strike = call_diagonal['short_call']['strike_price']
        self.short_put_strike = put_diagonal['short_put']['strike_price']
        self.long_call_strike = call_diagonal['long_call']['strike_price']
        self.long_put_strike = put_diagonal['long_put']['strike_price']
    
    def update_pnl(self, current_time, current_df, current_spot_price=None, print_info=False):
        """
        更新当前盈亏 - 增强版本，包含到期检查和更好的错误处理
        
        Args:
            current_time: 当前时间点
            current_df: 当前时间点的期权数据DataFrame
            current_spot_price: 当前现货价格（可选）
            print_info: 是否打印详细信息
        
        Returns:
            tuple: (success, reason)
                - success: bool, 是否成功更新
                - reason: str, 失败原因（如果失败的话）
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
        
        try:
            # 获取四个期权的当前价格
            current_prices = {}
            missing_options = []
            
            for position, symbol in self.option_symbols.items():
                price = get_option_open_price(
                    current_df, 
                    symbol, 
                    current_time, 
                    print_info=False  # 避免过多输出
                )
                
                if price is not None:
                    current_prices[position] = price
                else:
                    missing_options.append(symbol)
            
            # 检查是否所有期权价格都获取到了
            if len(current_prices) != 4:
                if print_info:
                    print(f"⚠️  无法获取所有期权价格，缺失: {missing_options}")
                return False, f"missing_prices: {missing_options}"
        
        # 计算当前组合价值
            # Long positions: 买入的期权，价格上涨有利
            # Short positions: 卖出的期权，价格下跌有利
            current_premium = (
                current_prices['long_call'] +    # 买入远月ATM Call
                current_prices['long_put'] -     # 买入远月ATM Put  
                current_prices['short_call'] -   # 卖出近月OTM Call
                current_prices['short_put']      # 卖出近月OTM Put
            )

            self.short_term_call_price = current_prices['short_call']
            self.short_term_put_price = current_prices['short_put']
            self.long_term_call_price = current_prices['long_call']
            self.long_term_put_price = current_prices['long_put']
            
            # 计算P&L
            self.current_pnl = current_premium - self.entry_premium
            self.last_update_time = current_time
            
            if print_info:
                print(f"📊 P&L更新 - 时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"   入场权利金: {self.entry_premium:.6f} BTC")
                print(f"   当前权利金: {current_premium:.6f} BTC")
                print(f"   当前P&L: {self.current_pnl:.6f} BTC")
                if current_spot_price:
                    print(f"   现货价格: ${current_spot_price:,.2f}")
                    print(f"   价格变化: {(current_spot_price - self.entry_spot_price) / self.entry_spot_price * 100:+.2f}%")
            
            return True, "success"
            
        except Exception as e:
            if print_info:
                print(f"❌ 更新P&L失败: {e}")
            return False, f"exception: {str(e)}"
    
    def get_current_status(self):
        """获取当前状态信息"""
        return {
            'is_active': self.is_active,
            'entry_time': self.entry_time,
            'entry_spot_price': self.entry_spot_price,
            'entry_premium': self.entry_premium,
            'current_pnl': self.current_pnl,
            'last_update_time': self.last_update_time,
            'option_symbols': self.option_symbols.copy()
        }
    
    def should_close(self, current_time, current_spot_price=None, max_loss_pct=0.2, target_profit_pct=0.4, breakthrough_tolerance_pct=0.05):
        """
        简单的平仓条件检查 - 增强版本，包含现货价格突破检查（带容忍度）
        
        Args:
            current_time: 当前时间
            current_spot_price: 当前现货价格
            max_loss_pct: 最大亏损百分比（相对于入场权利金）
            target_profit_pct: 目标盈利百分比
            breakthrough_tolerance_pct: 突破容忍度百分比（默认2%）
            
        Returns:
            tuple: (should_close, reason)
        """
        if not self.is_active:
            return False, "已平仓"
        
        # 🆕 现货价格突破短期期权执行价格区间检查（带容忍度）
        # if current_spot_price is not None:
        #     # 计算突破容忍度的绝对值
        #     call_tolerance = self.short_call_strike * breakthrough_tolerance_pct
        #     put_tolerance = self.short_put_strike * breakthrough_tolerance_pct
            
        #     # 当现货价格突破短期Call的执行价格 + 容忍度（向上突破）
        #     call_breakthrough_threshold = self.short_call_strike * (1 + breakthrough_tolerance_pct)
        #     if current_spot_price > call_breakthrough_threshold:
        #         breakthrough_pct = (current_spot_price - self.short_call_strike) / self.short_call_strike * 100
        #         return True, f"现货突破短期Call执行价+容忍度 (现货: ${current_spot_price:,.2f} > 阈值: ${call_breakthrough_threshold:,.2f}, 突破: {breakthrough_pct:.1f}%)"
            
        #     # 当现货价格突破短期Put的执行价格 - 容忍度（向下突破）
        #     put_breakthrough_threshold = self.short_put_strike * (1 - breakthrough_tolerance_pct)
        #     if current_spot_price < put_breakthrough_threshold:
        #         breakthrough_pct = (self.short_put_strike - current_spot_price) / self.short_put_strike * 100
        #         return True, f"现货突破短期Put执行价-容忍度 (现货: ${current_spot_price:,.2f} < 阈值: ${put_breakthrough_threshold:,.2f}, 突破: {breakthrough_pct:.1f}%)"
        
        # 计算P&L百分比
        if abs(self.entry_premium) > 1e-8:  # 避免除零
            pnl_pct = self.current_pnl / abs(self.entry_premium)
        else:
            pnl_pct = 0
        
        # 止损条件
        if pnl_pct < -max_loss_pct:
            return True, f"止损 (P&L: {pnl_pct*100:.1f}%)"
        
        # 止盈条件
        if pnl_pct > target_profit_pct:
            return True, f"止盈 (P&L: {pnl_pct*100:.1f}%)"
        
        # 检查近月期权是否即将到期（比如还有1天）
        # 这里需要根据实际情况调整
        
        return False, "持续持有"
    
    def close(self, close_time=None, close_reason="手动平仓"):
        """
        平仓 - 添加各个合约的P&L信息
        
        Args:
            close_time: 平仓时间
            close_reason: 平仓原因
            
        Returns:
            dict: 平仓信息，包含各个合约P&L
        """
        if not self.is_active:
            return None
        
        # 计算各个合约的盈亏
        # Long positions: 当前价格 - 入场价格
        # Short positions: 入场价格 - 当前价格
        contract_pnl = {
            'long_call': self.long_term_call_price - self.option_entry_prices['long_call'],
            'short_call': self.option_entry_prices['short_call'] - self.short_term_call_price,
            'long_put': self.long_term_put_price - self.option_entry_prices['long_put'],
            'short_put': self.option_entry_prices['short_put'] - self.short_term_put_price
        }
        
        close_info = {
            'entry_time': self.entry_time,
            'close_time': close_time or self.last_update_time,
            'entry_premium': self.entry_premium,
            'final_pnl': self.current_pnl,
            'close_reason': close_reason,
            'pnl_pct': self.current_pnl / abs(self.entry_premium) if abs(self.entry_premium) > 1e-8 else 0,
            
            # 🆕 各个合约的P&L
            'contract_pnl': contract_pnl
        }
        
        self.is_active = False
        return close_info