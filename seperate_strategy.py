import time
import logging
from utils import ist, round_to_nearest_0_05, place_limit_order, place_market_order, place_market_exit, is_order_complete, wait_for_orders_to_complete, check_unsold_lots
from datetime import datetime
from logger import LocalJsonLogger, ThrottlingLogger, logger_entry
from custom_threading import MyThread


logging.basicConfig(filename=f'strategy_log_files/strategy__{datetime.now(ist).strftime("%Y_%m%d_%H %M %S")}.log', level=logging.INFO)

def trace_execution(str= 'no data', data=datetime.now(ist).strftime("%Y %m %d - %H /%M/ %S")):
    print(f'{str} at {data}')
    logging.info(f'{str} at {data}')
# flag to tell us if the api_websocket is open

ist_datatime = datetime.now(ist)

class NewStrategy:
    def __init__(self, datas):
        trace_execution('entered strategy')
        self.api = datas['api']
        self.api_websocket = datas['api_websocket']
        self.SYMBOL = datas['SYMBOL']
        self.BUY_BACK_STATIC = datas['BUY_BACK_STATIC']
        self.INITIAL_LOTS = datas['INITIAL_LOTS']  # Start with 1 lot
        self.STRIKE_DIFFERENCE = datas['STRIKE_DIFFERENCE']
        self.ONE_LOT_QUANTITY = datas['ONE_LOT_QUANTITY']  # Number of units per lot in Bank Nifty
        self.TARGET_PROFIT = datas['TARGET_PROFIT']
        self.MAX_LOSS = datas['MAX_LOSS']
        self.MAX_LOSS_PER_LEG = datas['MAX_LOSS_PER_LEG']
        self.SAFETY_STOP_LOSS_PERCENTAGE = datas['SAFETY_STOP_LOSS_PERCENTAGE']
        self.BUY_BACK_PERCENTAGE = datas['BUY_BACK_PERCENTAGE']
        self.SELL_TARGET_PERCENTAGE = datas['SELL_TARGET_PERCENTAGE']
        self.BUY_BACK_LOSS_PERCENTAGE = datas['BUY_BACK_LOSS_PERCENTAGE']
        self.AVAILABLE_MARGIN = datas['AVAILABLE_MARGIN']
        self.ENTRY_TIME = datas['ENTRY_TIME']
        self.EXIT_TIME = datas['EXIT_TIME']
        self.stop_event = datas['stop_event']

        # DYNAMIC CONFIG
        self.BUY_BACK_LOTS = datas['BUY_BACK_LOTS']

        # Strategy LEVEL Variables

        self.LEG_TOKEN = {}
        self.PRICE_DATA = {
            'CE_PRICE_DATA' : {
                'INITIAL_SELL_CE' : 0,
                'INITIAL_BUY_CE' : 0,
                'BUY_BACK_BUY_CE' : 0,
                'BUY_BACK_SELL_CE' : 0,
                'RE_ENTRY_BUY_CE' : 0,
                'RE_ENTRY_SELL_CE': 0
            },
            'PE_PRICE_DATA' : {
                'INITIAL_SELL_PE' : 0,
                'INITIAL_BUY_PE' : 0,
                'BUY_BACK_BUY_PE' : 0,
                'BUY_BACK_SELL_PE' : 0,
                'RE_ENTRY_BUY_PE' : 0,
                'RE_ENTRY_SELL_PE': 0
            }
        }
        self.CURRENT_STRATEGY_ORDERS = []
        self.subscribedTokens = []




        # Global variables
        self.strategy_running = False
        self.exited_strategy_started = False
        self.exited_strategy_completed = True
        self.sell_price_ce = 0
        self.sell_price_pe = 0

        self.strategy_log_class = {}
        
        
        
# Utility function to fetch the ATM strike price
    def fetch_atm_strike(self):        
        trace_execution('entered in fetch_atm_strike')
        banknifty_price = self.api.get_quotes(exchange='NSE', token='26009')
        current_price = banknifty_price['lp']
        print(float(current_price))
        atm_strike = round(float(current_price) / 100) * 100
        print(atm_strike)

        nearest_symbol_ce = (str(atm_strike+self.STRIKE_DIFFERENCE)+' nifty bANK' + ' ce')
        nearest_symbol_pe = (str(atm_strike-self.STRIKE_DIFFERENCE)+' nifty bANK' + ' pe')

        # print(nearest_symbol_ce)
        # print(self.api.searchscrip(exchange='NFO', searchtext=nearest_symbol_ce))
        # print(self.api.searchscrip(exchange='NFO', searchtext=nearest_symbol_pe))
        option_chains_ce = self.api.searchscrip(exchange='NFO', searchtext=nearest_symbol_ce)
        option_chains_pe = self.api.searchscrip(exchange='NFO', searchtext=nearest_symbol_pe)
        pe_option = option_chains_pe['values'][0]
        ce_option = option_chains_ce['values'][0]
        subscribeDataPE = 'NFO|'+pe_option['token']
        subscribeDataCE = 'NFO|'+ce_option['token']
        self.LEG_TOKEN['PE'] = pe_option['token']
        self.LEG_TOKEN['CE'] = ce_option['token']
        self.LEG_TOKEN['PE_tsym'] = pe_option['tsym']
        self.LEG_TOKEN['CE_tsym'] = ce_option['tsym']
        if subscribeDataPE not in self.subscribedTokens and subscribeDataCE not in self.subscribedTokens:
            self.api.subscribe([subscribeDataPE, subscribeDataCE])
            self.subscribedTokens.extend([subscribeDataPE, subscribeDataCE])

        
        trace_execution('completed in fetch_atm_strike')
        return atm_strike  # Round to nearest 100


    # Calculate PNL based on current leg status
    def calculate_leg_pnl(self, option_type, type, lots):
        try:
            # Check if PRICE_DATA and the required subkey exist
            price_data_key = option_type + '_PRICE_DATA'
            if price_data_key not in PRICE_DATA:
                trace_execution(f"Error: {price_data_key} not found in PRICE_DATA.")
                raise ValueError('Error on exit')
            
            # Get the PRICE_DATAS for the given option_type
            PRICE_DATAS = PRICE_DATA[price_data_key]
            
            # Create the keys for sell and buy nodes
            node_sell = type + '_SELL_' + option_type
            node_buy = type + '_BUY_' + option_type

            # Initialize prices
            sold_price_or_ltp_price = 0
            bought_price_or_ltp_price = 0

            # Debug print statements to show keys and data
            # print(f"node_sell: {node_sell}")
            # print(f"node_buy: {node_buy}")
            # print("PRICE_DATAS:", PRICE_DATAS)

            # Check if the nodes exist in PRICE_DATAS before accessing
            last_traded_price = self.api_websocket.fetch_last_trade_price(option_type, self.LEG_TOKEN)
            if node_sell in PRICE_DATAS:
                # Use the stored price or fetch the last traded price if it's zero
                sold_price_or_ltp_price = float(PRICE_DATAS[node_sell])
                if sold_price_or_ltp_price == 0:
                    sold_price_or_ltp_price = last_traded_price
            else:
                trace_execution(f"Error: {node_sell} not found in PRICE_DATAS.")
            
            if node_buy in PRICE_DATAS:
                bought_price_or_ltp_price = PRICE_DATAS[node_buy]
                if bought_price_or_ltp_price == 0:
                    bought_price_or_ltp_price = last_traded_price
            else:
                trace_execution(f"Error: {node_buy} not found in PRICE_DATAS.")
            
            difference = float(sold_price_or_ltp_price) - float(bought_price_or_ltp_price)
            
            pnl = difference * lots * self.ONE_LOT_QUANTITY
            return float(pnl)
        except Exception as e:
            if not exited_strategy_completed:
                self.exit_strategy()
                trace_execution(f'Error in calculate_leg_pnl: {e}')
            else:
                trace_execution(f'calculate_leg_pnl Error but already exited: {e}')
            

        
    # Function to calculate total PNL
    def calculate_total_pnl(self, log=False):
        try:
            ce_entry_pnl = self.calculate_leg_pnl('CE', 'INITIAL', self.INITIAL_LOTS)
            pe_entry_pnl = self.calculate_leg_pnl('PE', 'INITIAL', self.INITIAL_LOTS)
            ce_pnl = self.calculate_leg_pnl('CE', 'BUY_BACK', BUY_BACK_LOTS)
            pe_pnl = self.calculate_leg_pnl('PE', 'BUY_BACK', BUY_BACK_LOTS)
            ce_re_entry_pnl = self.calculate_leg_pnl('CE', 'RE_ENTRY', self.INITIAL_LOTS)
            pe_re_entry_pnl = self.calculate_leg_pnl('PE', 'RE_ENTRY', self.INITIAL_LOTS)  # Corrected to 'PE'
            pnl = ce_pnl + pe_pnl + ce_entry_pnl + pe_entry_pnl + ce_re_entry_pnl + pe_re_entry_pnl
            if log:
                trace_execution(f'pnl ce_pnl {ce_pnl} + pe_pnl {pe_pnl} + ce_entry_pnl {ce_entry_pnl} + pe_entry_pnl {pe_entry_pnl} + ce_re_entry_pnl {ce_re_entry_pnl} + pe_re_entry_pnl{pe_re_entry_pnl}')
            return pnl
        except Exception as e:
            if not exited_strategy_completed:
                trace_execution(f'Error in calculate_total_pnl: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'calculate_total_pnl Error but already exited: {e}')

    def check_for_stop_loss(self, option_type, selldetails, buydetails):
        PRICE_DATA
        trace_execution('entered in check_for_stop_loss')
        try:
            ORDER_STATUS = self.api_websocket.get_latest_data()
            sell_target_order_id = selldetails['sell_target_order_id']
            buy_back_order_id = buydetails['buy_back_order_id']
            log_sell = ThrottlingLogger(sell_target_order_id, logger_entry)
            while not is_order_complete(sell_target_order_id, ORDER_STATUS, log_sell ,strategy_log_class): #static instead check weather ltp > selltarget_price
                if exited_strategy_started or self.stop_event.is_set():
                    break
                ltp = self.api_websocket.fetch_last_trade_price(option_type, self.LEG_TOKEN)  # Fetch LTP for the option leg
                legpnl = self.calculate_leg_pnl(option_type, 'BUY_BACK', BUY_BACK_LOTS)

                if legpnl <= -self.MAX_LOSS_PER_LEG or ltp <=  (float(ORDER_STATUS[buy_back_order_id]['avgprc']) * self.BUY_BACK_LOSS_PERCENTAGE):
                    trace_execution(f"{option_type} {legpnl} reached 10% loss, exiting remaining orders.")
                    trace_execution(f"{option_type} {PRICE_DATA} ORDER PRICE DETAILS")
                    unsold_lots = check_unsold_lots(sell_target_order_id, self.api_websocket)
                    cancel_responce = self.api.cancel_order(sell_target_order_id)
                    logger_entry(strategy_log_class, 'tsym',sell_target_order_id, 'typ',option_type,'qty',str(cancel_responce), 'CAN', 0, 0, 'cancel_order')
                    if 'result' not in cancel_responce:
                        current_orders = self.api_websocket.get_latest_data()
                        current_status = current_orders.get(sell_target_order_id, {}).get('status', '').lower()
                        if current_status != 'complete':
                            raise ValueError('Error in cancel Order')
                    sell_target_order_id = place_market_order(self.api, self.LEG_TOKEN, option_type, 'S', unsold_lots, 'end')
                    trace_execution(f'INSIDE sell_order_id :{sell_target_order_id}')
                    while not (sell_target_order_id in ORDER_STATUS and ORDER_STATUS[sell_target_order_id].get('tsym')):
                        # Optionally perform some action or add a delay to avoid busy waiting
                        trace_execution("Waiting for buy_back_order_id and 'tsym' data...")
                        time.sleep(0.25)
                    trace_execution(f'ORDER_STATUS[sell_target_order_id]: {ORDER_STATUS[sell_target_order_id]}')
                    break
                time.sleep(1)
            return sell_target_order_id
        except Exception as e:
            if not exited_strategy_completed:
                trace_execution(f'Error in check_for_stop_loss: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'check_for_stop_loss Error but already exited: {e}')

        

    def sell_at_limit_price(self, option_type, buydetails):
        trace_execution('entered in sell_at_limit_price')
        try:
            ORDER_STATUS = self.api_websocket.get_latest_data()
            buy_back_lots = BUY_BACK_LOTS * self.ONE_LOT_QUANTITY
            print(f"{option_type} sell_at_limit_price...0")
            buy_back_avg_price = buydetails['buy_back_avg_price']
            self.PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_BUY_'+option_type] = buy_back_avg_price            
            sell_target_price = round_to_nearest_0_05(float(buy_back_avg_price) * float(1 + self.SELL_TARGET_PERCENTAGE))
            print(f"{option_type} ThrottlingLogger... 2")
            print(f"{option_type} ThrottlingLogger... 2.1")
            sell_target_order_id = place_limit_order(self.api, self.LEG_TOKEN, option_type, 'S', buy_back_lots, limit_price=sell_target_price, leg_type='end')
            while not (sell_target_order_id in ORDER_STATUS and ORDER_STATUS[sell_target_order_id].get('tsym')):
                # Optionally perform some action or add a delay to avoid busy waiting
                print("Waiting for buy_back_order_id and 'tsym' data...")
                time.sleep(0.25)
            print(f"{option_type} ThrottlingLogger... 2.2 {sell_target_order_id}")
            logger_entry(strategy_log_class, ORDER_STATUS[sell_target_order_id]['tsym'],sell_target_order_id,'S',option_type,buy_back_lots,sell_target_price, 'LMT', 0, 0, 'placed')
            print(f'OUTSIDE sell_target_order_id {sell_target_order_id}')
            self.CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
            print(f"{option_type} ThrottlingLogger... 3")

                
            return {
                'sell_target_order_id': sell_target_order_id,
                'sell_target_price': sell_target_price
            }
        except Exception as e:
            if not exited_strategy_completed:
                trace_execution(f'error in sell_at_limit_price: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'sell_at_limit_price Error but already exited: {e}')
        
        
        
        
    def buy_at_limit_price(self, option_type, sell_price):
 
        trace_execution('entered in buy_at_limit_price')
        try:
            print(f"{option_type} buy_at_limit_price...0")
            buy_back_lots = BUY_BACK_LOTS * self.ONE_LOT_QUANTITY
            ORDER_STATUS = self.api_websocket.get_latest_data()
            buy_back_price = round_to_nearest_0_05(float(sell_price) * float(self.BUY_BACK_PERCENTAGE))
            print(f"{option_type} reached round_to_nearest_0_05...")
            buy_back_order_id = place_limit_order(self.api, self.LEG_TOKEN, option_type, 'B', buy_back_lots, limit_price=buy_back_price, leg_type='start')
            while not (buy_back_order_id in ORDER_STATUS and ORDER_STATUS[buy_back_order_id].get('tsym')):
                # Optionally perform some action or add a delay to avoid busy waiting
                print("Waiting for buy_back_order_id and 'tsym' data...")
                time.sleep(0.25)
            logger_entry(strategy_log_class, ORDER_STATUS[buy_back_order_id]['tsym'] ,buy_back_order_id,'B',option_type,buy_back_lots,buy_back_price, 'LMT', 0, 0, 'placed')
            self.CURRENT_STRATEGY_ORDERS.append(buy_back_order_id)
            print(f"{option_type} ThrottlingLogger...0")
            log_buy = ThrottlingLogger(buy_back_order_id, logger_entry)
            while not is_order_complete(buy_back_order_id, ORDER_STATUS, log_buy, strategy_log_class):
                time.sleep(0.25)
            print(f"{option_type} ThrottlingLogger... 1")
            buy_back_avg_price = ORDER_STATUS[buy_back_order_id]['avgprc']
            self.PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_BUY_'+option_type] = buy_back_avg_price
            return {
                'buy_back_avg_price' : buy_back_avg_price,
                'buy_back_order_id' : buy_back_order_id
            }
        except Exception as e:
            if not exited_strategy_completed:
                trace_execution(f'Error while buy_at_limit_price: {e}')
                self.self.exit_strategy()
            else:
                trace_execution(f'buy_at_limit_price Error but already exited: {e}')

    # Monitor individual leg logic (CE/PE)
    def monitor_leg(self, option_type, sell_price, strike_price):
        try:
            global strategy_running, PRICE_DATA, exited_strategy_started, logger_entry
            trace_execution('entered in monitor_leg')
            ORDER_STATUS = self.api_websocket.get_latest_data()
            # PRICE_DATA[option_type+'_PRICE_DATA']['INITIAL_BUY_'+option_type] = sell_price
            leg_entry = False
            print('monitor '+option_type)
            while strategy_running and not leg_entry:
                # print('while check monitor')
                ltp = self.api_websocket.fetch_last_trade_price(option_type, self.LEG_TOKEN)  # Fetch LTP for the option leg
                if exited_strategy_started or self.stop_event.is_set():
                    break
                if ltp <= (float(sell_price) * float(self.SAFETY_STOP_LOSS_PERCENTAGE)):
                    leg_entry = True

                    print(f"{option_type} reached 76% of sell price, exiting...")
                    buydetails = self.buy_at_limit_price(option_type, sell_price)
                    selldetails = self.sell_at_limit_price(option_type, buydetails)
                    print(f"{option_type} ThrottlingLogger... 4 {selldetails}")
                    if exited_strategy_started or self.stop_event.is_set():
                        break
                    print(f"{option_type} ThrottlingLogger... 5")
                    
                    sell_target_order_id = self.check_for_stop_loss(option_type, selldetails, buydetails)
                    
                    if wait_for_orders_to_complete(sell_target_order_id, self.api_websocket, logger_entry, strategy_log_class, 40, 0.25):
                        self.CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
                        self.PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_SELL_'+option_type] = float(ORDER_STATUS[sell_target_order_id]['avgprc'])
                        print(f"{option_type} {PRICE_DATA} ORDER PRICE DETAILS")
                        print('------------------------------------')
                        print(f"{option_type} ThrottlingLogger... 6 {sell_target_order_id}, {ORDER_STATUS}")
                    print('end_monitor '+option_type)
                    break
            return True
        except TypeError as e:
            if not exited_strategy_completed:
                trace_execution(f'Type error in monitor_leg: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_leg Error but already exited: {e}')
            raise ValueError('Error on exit')
        except ZeroDivisionError as e:
            if not exited_strategy_completed:
                trace_execution(f'Math error in monitor_leg: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_leg Error but already exited: {e}')
            raise ValueError('Error on exit')
        except ValueError as e:
            if not exited_strategy_completed:
                trace_execution(f'Value error in monitor_leg: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_leg Error but already exited: {e}')
            raise ValueError('Error on exit')
        except Exception as e:
            # Catch all other exceptions
            if not exited_strategy_completed:
                trace_execution(f'error in monitor_leg: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_leg Error but already exited: {e}')
            raise ValueError('Error on exit')
        



    # Function to monitor the strategy
    def monitor_strategy(self):
        try:
            global strategy_running, exited_strategy_started
            print('monitor_strategy ')
            trace_execution('entered in monitor_strategy')
            end_time = ist_datatime.replace(hour=self.EXIT_TIME['hours'], minute=self.EXIT_TIME['minutes'], second=self.EXIT_TIME['seconds'], microsecond=0).time()
            while strategy_running:
                if exited_strategy_started or self.stop_event.is_set():
                    break
                
                current_time = datetime.now(ist).time()
                if current_time >= end_time:
                    self.exit_strategy()
                pnl = self.calculate_total_pnl()  # Fetch the PNL
                if pnl >= self.TARGET_PROFIT and not exited_strategy_started:
                    print(f"Target profit of ₹{self.TARGET_PROFIT} reached. Exiting strategy.")
                    # strategy_running = False
                    self.exit_strategy()
                    break
                elif pnl <= -self.MAX_LOSS and not exited_strategy_started:
                    print(f"Max loss of ₹{self.MAX_LOSS} reached. Exiting strategy.")
                    # strategy_running = False
                    self.exit_strategy()
                    print('checking pnl')
                    break
                time.sleep(5)  # Check PNL every 5 seconds
            return True
        except TypeError as e:
            if not exited_strategy_completed:
                trace_execution(f'Type error in monitor_strategy: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')
        except ZeroDivisionError as e:
            if not exited_strategy_completed:
                trace_execution(f'Math error in monitor_strategy: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')
        except ValueError as e:
            if not exited_strategy_completed:
                trace_execution(f'Value error in monitor_strategy: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')
        except Exception as e:
            # Catch all other exceptions
            if not exited_strategy_completed:
                trace_execution(f'monitor_strategy error in monitor_strategy: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')

    def check_order_qty(self):
        totals = {'CE': 0, 'PE': 0}
        symbols = {'CE': '', 'PE': ''}
        try:
            trace_execution('entered in check_net_qty')
            ORDER_STATUS = self.api_websocket.get_latest_data()
            # Initialize totals and symbol tracking for CE and PE
                # Filter unique values using set
            unique_orders = set(self.CURRENT_STRATEGY_ORDERS)

            # Cancel incomplete orders and calculate totals for completed orders
            for key in unique_orders:
                order = ORDER_STATUS.get(key)
                if not order:
                    print(f"Order {key} not found in ORDER_STATUS, skipping...")
                    continue

                status = order.get('status', '').lower()

                if status not in ['open', 'pending', 'trigger_pending', 'complete']:
                    print(f"Order {key} has an invalid status '{status}', skipping...")
                    continue
                
                # Cancel any order that is not complete
            
                qty = float(order['qty'])
                tsym = order['tsym']
                typ = order['trantype']
                option_info = order.get('option_type', '').split()
                if len(option_info) < 2:
                    print(f"Invalid option_type format for order {key}, skipping...")
                    continue
                option_type, leg_type = option_info[0], option_info[1]
                print(f"Calculation data: Leg Type: {leg_type}, Status: {status}, Option Type: {option_type}, Qty: {qty}, Type: {typ}")

                if status in ['open', 'pending', 'trigger_pending']:
                    print(f"Canceling incomplete order: {key}")
                    cancel_responce = self.api.cancel_order(key)
                    if 'result' not in cancel_responce:
                        current_orders = self.api_websocket.get_latest_data()
                        current_status = current_orders.get(key, {}).get('status', '').lower()
                        if current_status != 'complete':
                            raise ValueError('Error in cancel Order')
                    logger_entry(strategy_log_class, tsym,key, typ,option_type,qty,str(cancel_responce), 'CAN', 0, 0, 'cancel_order')
                    if leg_type == 'start': #if it is initial order and not executed then its quantity shouldn't be considered
                        continue
                    qty = float(order['flqty'])
                    print(f"Adjusted sold quantity: {qty}")
                
                
                # Update total quantities for completed orders
                if option_type in totals:
                    if typ == 'S':
                        totals[option_type] -= qty
                    elif typ == 'B':
                        totals[option_type] += qty
                    symbols[option_type] = tsym
                    
            trace_execution('completed in check_net_qty')
            return {
                'symbols' : symbols,
                'totals' : totals
            }
        except Exception as e:
            # Catch all other exceptions
            if not exited_strategy_completed:
                self.exit_strategy()
                logging.error(f'An unexpected error occurred check_net_qty: {e}')
            else:
                trace_execution(f'check_net_qty Error but already exited: {e}')
            raise ValueError('Error on check_net_qty')

        
    # Function to exit the strategy
    def exit_strategy(self):
        try:
            global strategy_running, exited_strategy_started, exited_strategy_completed
            trace_execution('entered in exit_strategy')
            ORDER_STATUS = self.api_websocket.get_latest_data() 
            strategy_running = True  # Stop the strategy
            if exited_strategy_started:
                raise ValueError(f'Error in exit strategy already exit function called')
            exited_strategy_started = True
            trace_execution('Exiting strategy...')
            trace_execution('Current ORDER_STATUS:', ORDER_STATUS)

            values = self.check_order_qty()
            totals = values['totals']
            symbols = values['symbols']
            trace_execution(f"Totals: {totals}, Symbols: {symbols}")
            # Place market exit orders for remaining positions
            for option_type, total in totals.items():
                if total != 0:
                    buy_or_sell = 'S' if total > 0 else 'B'
                    tsym = symbols[option_type]
                    trace_execution(f"Placing market exit for {option_type}: {buy_or_sell} {abs(total)} lots")
                    order_id = place_market_exit(self.api, tsym, buy_or_sell, abs(total))
                    self.append(order_id)
                    wait_for_orders_to_complete(order_id, self.api_websocket, logger_entry, 100)
            # Implement logic to close all open orders and exit strategy
            final_qty = self.check_order_qty()
            for option_type, total in final_qty['totals'].items():
                if total != 0:
                    raise ValueError('not sold completely')
            exited_strategy_completed = True
            if self.stop_event:
                self.stop_event.set()
            trace_execution(f'Strategy exited successfully')
            trace_execution(f'Strategy profit and loss {self.calculate_total_pnl(True)}')
            # self.api.unsubscribe() ## need 
            return True
        except Exception as e:
            # Catch all other exceptions
            if not exited_strategy_completed:
                # self.api.unsubscribe()
                logging.error(f'An unexpected error occurred exit_strategy: {e}')
            else:
                trace_execution(f'exit_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')



            


    def run_strategy(self):
        trace_execution('passed run_strategy')
        
        global strategy_running, sell_price_ce, sell_price_pe, PRICE_DATA, BUY_BACK_LOTS, strategy_log_class
        strategy_log_class = LocalJsonLogger()
        start_time = ist_datatime.replace(hour=self.ENTRY_TIME['hours'], minute=self.ENTRY_TIME['minutes'], second=self.ENTRY_TIME['seconds'], microsecond=0).time()
        end_time = ist_datatime.replace(hour=self.EXIT_TIME['hours'], minute=self.EXIT_TIME['minutes'], second=self.EXIT_TIME['seconds'], microsecond=0).time()
        lots = self.INITIAL_LOTS * self.ONE_LOT_QUANTITY
        print('entered run_strategy')
        while not strategy_running:
            current_time = datetime.now(ist).time()
            if current_time >= end_time:
                self.exit_strategy()
                break
            if start_time <= current_time <= end_time:
                if not strategy_running:
                    atm_strike = self.fetch_atm_strike()
                    trace_execution('passed atm strike')
                    sell_price_ce = self.api_websocket.fetch_last_trade_price('CE', self.LEG_TOKEN)
                    sell_price_pe = self.api_websocket.fetch_last_trade_price('PE', self.LEG_TOKEN)
                    print(f'sell_price_ce{sell_price_ce}:sell_price_pe:{sell_price_pe}')
                    trace_execution(f'passed OPTION PRICE {atm_strike - self.STRIKE_DIFFERENCE} pe price {sell_price_pe} _ {atm_strike + self.STRIKE_DIFFERENCE} pe price {sell_price_pe}')
                    if(not self.BUY_BACK_STATIC):
                        ce_lot = int(self.AVAILABLE_MARGIN/(self.ONE_LOT_QUANTITY * sell_price_ce))
                        pe_lot = int(self.AVAILABLE_MARGIN/(self.ONE_LOT_QUANTITY * sell_price_pe))
                        BUY_BACK_LOTS = min(ce_lot, pe_lot)
                    
                    logger_entry(strategy_log_class, 'CE','orderno','direction','CE',self.ONE_LOT_QUANTITY,sell_price_ce,'GET MKT',0,0,'start')
                    logger_entry(strategy_log_class, 'PE','orderno','direction','PE',self.ONE_LOT_QUANTITY,sell_price_pe,'GET MKT',0,0,'start')
                    
                    PRICE_DATA['CE_PRICE_DATA']['INITIAL_SELL_CE'] = 0
                    PRICE_DATA['PE_PRICE_DATA']['INITIAL_SELL_PE'] = 0

                    strategy_running = True

                    ce_thread = MyThread(target=self.monitor_leg, args=('CE', sell_price_ce, atm_strike + self.STRIKE_DIFFERENCE), daemon=True)
                    pe_thread = MyThread(target=self.monitor_leg, args=('PE', sell_price_pe, atm_strike - self.STRIKE_DIFFERENCE), daemon=True)
                    strategy_thread = MyThread(target=self.monitor_strategy, daemon=True) # static uncommen

                    try:
                        trace_execution('passed try in run_strategy')
                        ce_thread.start()
                        pe_thread.start()              
                        strategy_thread.start() # static uncomment
                        ce_thread.join()
                        pe_thread.join()
                        self.exit_strategy()
                        # dynamic_data.join()
                        strategy_thread.join() # static uncomment
                        break
                    except TypeError as e:
                        if not exited_strategy_completed:
                            trace_execution(f'Typr error in run_strategy: {e}')
                            self.exit_strategy()
                        else:
                            trace_execution(f'run_strategy Error but already exited: {e}')
                        raise ValueError('Error on exit')
                    except ZeroDivisionError as e:
                        if not exited_strategy_completed:
                            trace_execution(f'Math error in run_strategy: {e}')
                            self.exit_strategy()
                        else:
                            trace_execution(f'run_strategy Error but already exited: {e}')
                        raise ValueError('Error on exit')
                    except ValueError as e:
                        if not exited_strategy_completed:
                            trace_execution(f'Value error in run_strategy: {e}')
                            self.exit_strategy()
                        else:
                            trace_execution(f'run_strategy Error but already exited: {e}')
                        raise ValueError('Error on exit')
                    except Exception as e:
                        # Catch all other exceptions
                        if not exited_strategy_completed:
                            trace_execution(f'error in run_strategy: {e}')
                            self.exit_strategy()
                        else:
                            trace_execution(f'run_strategy Error but already exited: {e}')
                        raise ValueError('Error on exit')



            else:
                time_to_sleep = start_time - current_time
                print("Outside trading hours, strategy paused.")
                time.sleep(time_to_sleep)        
        return True