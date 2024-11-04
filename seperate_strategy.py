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
        # Logging
        trace_execution('entered strategy')

        # API & WebSocket initialization
        self.api = datas['api']
        self.api_websocket = datas['api_websocket']

        # Strategy parameters
        self.SYMBOL = datas['SYMBOL']
        self.BUY_BACK_STATIC = datas['BUY_BACK_STATIC']
        self.INITIAL_LOTS = datas['INITIAL_LOTS']
        self.STRIKE_DIFFERENCE = datas['STRIKE_DIFFERENCE']
        self.ONE_LOT_QUANTITY = datas['ONE_LOT_QUANTITY']
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

        # Dynamic configuration
        self.BUY_BACK_LOTS = datas['BUY_BACK_LOTS']

        # Strategy level variables
        self.LEG_TOKEN = {}
        self.CURRENT_STRATEGY_ORDERS = []
        self.subscribedTokens = []

        # Price data structure to track CE and PE prices
        self.PRICE_DATA = {
            'CE_PRICE_DATA': {key: 0 for key in ['INITIAL_SELL_CE', 'INITIAL_BUY_CE', 
                                                 'BUY_BACK_BUY_CE', 'BUY_BACK_SELL_CE', 
                                                 'RE_ENTRY_BUY_CE', 'RE_ENTRY_SELL_CE']},
            'PE_PRICE_DATA': {key: 0 for key in ['INITIAL_SELL_PE', 'INITIAL_BUY_PE', 
                                                 'BUY_BACK_BUY_PE', 'BUY_BACK_SELL_PE', 
                                                 'RE_ENTRY_BUY_PE', 'RE_ENTRY_SELL_PE']}
        }

        # Strategy status flags
        self.strategy_running = False
        self.exited_strategy_started = False
        self.exited_strategy_completed = False

        # Sell prices for CE and PE
        self.sell_price_ce = 0
        self.sell_price_pe = 0

        # Logging handler
        self.strategy_log_class = {}

        
    def fetch_atm_strike(self):
        trace_execution('entered in fetch_atm_strike')

        try:
            # Fetch the current Bank Nifty price
            banknifty_price = self.api.get_quotes(exchange='NSE', token='26009')
            current_price = float(banknifty_price['lp'])
            print(current_price)

            # Calculate the ATM strike price rounded to the nearest 100
            atm_strike = round(current_price / 100) * 100
            print(atm_strike)

            # Generate nearest CE and PE option symbols based on ATM strike and strike difference
            nearest_symbol_ce = f"{atm_strike + self.STRIKE_DIFFERENCE} NIFTY BANK CE"
            nearest_symbol_pe = f"{atm_strike - self.STRIKE_DIFFERENCE} NIFTY BANK PE"

            # Fetch option chain details for both CE and PE
            option_chains_ce = self.api.searchscrip(exchange='NFO', searchtext=nearest_symbol_ce)
            option_chains_pe = self.api.searchscrip(exchange='NFO', searchtext=nearest_symbol_pe)

            ce_option = option_chains_ce['values'][0]
            pe_option = option_chains_pe['values'][0]

            # Set up token details for both CE and PE
            self.LEG_TOKEN = {
                'PE': pe_option['token'],
                'CE': ce_option['token'],
                'PE_tsym': pe_option['tsym'],
                'CE_tsym': ce_option['tsym']
            }

            # Subscription for tokens if not already subscribed
            subscribeDataPE = f"NFO|{pe_option['token']}"
            subscribeDataCE = f"NFO|{ce_option['token']}"
            
            if subscribeDataPE not in self.subscribedTokens or subscribeDataCE not in self.subscribedTokens:
                self.api.subscribe([subscribeDataPE, subscribeDataCE])
                self.subscribedTokens.extend([subscribeDataPE, subscribeDataCE])
                time.sleep(5)

            trace_execution('completed in fetch_atm_strike')
            return atm_strike

        except Exception as e:
            trace_execution(f'Error in fetch_atm_strike: {e}')
            return None


    # Calculate PNL based on current leg status
    def calculate_leg_pnl(self, option_type, type, lots):
        try:
            # Check if PRICE_DATA and the required subkey exist
            price_data_key = option_type + '_PRICE_DATA'
            if price_data_key not in self.PRICE_DATA:
                trace_execution(f"Error: {price_data_key} not found in PRICE_DATA.")
                raise ValueError('Error on exit')
            
            # Get the PRICE_DATAS for the given option_type
            PRICE_DATAS = self.PRICE_DATA[price_data_key]
            
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
            if not self.exited_strategy_completed:
                self.exit_strategy()
                trace_execution(f'Error in calculate_leg_pnl: {e}')
            else:
                trace_execution(f'calculate_leg_pnl Error but already exited: {e}')
            

        
    # Function to calculate total PNL
    def calculate_leg_pnl(self, option_type, trade_type, lots):
        try:
            # Define price data key based on option type (CE or PE)
            price_data_key = f"{option_type}_PRICE_DATA"
            if price_data_key not in self.PRICE_DATA:
                trace_execution(f"Error: {price_data_key} not found in PRICE_DATA.")
                raise ValueError('Price data key not found in PRICE_DATA.')

            # Access relevant PRICE_DATA for the given option type
            price_data = self.PRICE_DATA[price_data_key]

            # Formulate node keys for buy and sell prices
            node_sell = f"{trade_type}_SELL_{option_type}"
            node_buy = f"{trade_type}_BUY_{option_type}"

            # Initialize price variables, with fallback to the last traded price if needed
            sold_price = price_data.get(node_sell, 0) or self.api_websocket.fetch_last_trade_price(option_type, self.LEG_TOKEN)
            bought_price = price_data.get(node_buy, 0) or self.api_websocket.fetch_last_trade_price(option_type, self.LEG_TOKEN)

            # Calculate difference in prices
            pnl_difference = float(sold_price) - float(bought_price)

            # Compute PnL based on lot size and quantity per lot
            pnl = pnl_difference * lots * self.ONE_LOT_QUANTITY
            return float(pnl)

        except Exception as e:
            # Exit strategy if needed and log the error
            if not self.exited_strategy_completed:
                self.exit_strategy()
                trace_execution(f'Error in calculate_leg_pnl: {e}')
            else:
                trace_execution(f'calculate_leg_pnl Error but strategy already exited: {e}')
            return 0.0  # Return 0 as default in case of error
        
        
    def calculate_total_pnl(self, log=False):
        try:
            # Calculate PnL for each leg type and trade stage
            ce_entry_pnl = self.calculate_leg_pnl('CE', 'INITIAL', self.INITIAL_LOTS)
            pe_entry_pnl = self.calculate_leg_pnl('PE', 'INITIAL', self.INITIAL_LOTS)
            ce_pnl = self.calculate_leg_pnl('CE', 'BUY_BACK', self.BUY_BACK_LOTS)
            pe_pnl = self.calculate_leg_pnl('PE', 'BUY_BACK', self.BUY_BACK_LOTS)
            ce_re_entry_pnl = self.calculate_leg_pnl('CE', 'RE_ENTRY', self.INITIAL_LOTS)
            pe_re_entry_pnl = self.calculate_leg_pnl('PE', 'RE_ENTRY', self.INITIAL_LOTS)

            # Sum up the PnL values
            total_pnl = ce_pnl + pe_pnl + ce_entry_pnl + pe_entry_pnl + ce_re_entry_pnl + pe_re_entry_pnl

            # Optional logging of PnL components if log is True
            if log:
                trace_execution(
                    f'Total PnL calculation breakdown: ce_pnl={ce_pnl}, pe_pnl={pe_pnl}, '
                    f'ce_entry_pnl={ce_entry_pnl}, pe_entry_pnl={pe_entry_pnl}, '
                    f'ce_re_entry_pnl={ce_re_entry_pnl}, pe_re_entry_pnl={pe_re_entry_pnl}'
                )
            return total_pnl

        except Exception as e:
            # Handle errors and ensure strategy exits gracefully
            if not self.exited_strategy_completed:
                trace_execution(f'Error in calculate_total_pnl: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'calculate_total_pnl Error but already exited: {e}')
            return 0.0  # Return 0 as a safe default in case of error

        
    def check_for_stop_loss(self, option_type, selldetails, buydetails):
        trace_execution('entered in check_for_stop_loss')
        try:
            # Retrieve the latest order status
            ORDER_STATUS = self.api_websocket.get_latest_data()
            sell_target_order_id = selldetails['sell_target_order_id']
            buy_back_order_id = buydetails['buy_back_order_id']
            
            log_sell = ThrottlingLogger(sell_target_order_id, logger_entry)
            
            while not is_order_complete(sell_target_order_id, ORDER_STATUS, log_sell, self.strategy_log_class):
                if self.exited_strategy_started or self.stop_event.is_set():
                    break

                # Fetch the Last Traded Price (LTP) for the specified option type
                ltp = self.api_websocket.fetch_last_trade_price(option_type, self.LEG_TOKEN)
                leg_pnl = self.calculate_leg_pnl(option_type, 'BUY_BACK', self.BUY_BACK_LOTS)

                # Stop loss check based on per-leg loss limit or LTP percentage threshold
                avg_buy_price = float(ORDER_STATUS[buy_back_order_id].get('avgprc', 0))
                if leg_pnl <= -self.MAX_LOSS_PER_LEG or ltp <= avg_buy_price * self.BUY_BACK_LOSS_PERCENTAGE:
                    trace_execution(f"{option_type} {leg_pnl} reached stop-loss threshold, exiting remaining orders.")
                    trace_execution(f"{option_type} {self.PRICE_DATA} ORDER PRICE DETAILS")

                    # Check for unsold lots and cancel existing order if necessary
                    unsold_lots = check_unsold_lots(sell_target_order_id, self.api_websocket)
                    cancel_response = self.api.cancel_order(sell_target_order_id)
                    
                    logger_entry(self.strategy_log_class, 'tsym', sell_target_order_id, 'typ', option_type, 
                                'qty', str(cancel_response), 'CAN', 0, 0, 'cancel_order')

                    if 'result' not in cancel_response:
                        # Double-check if cancellation was successful
                        current_status = ORDER_STATUS.get(sell_target_order_id, {}).get('status', '').lower()
                        if current_status != 'complete':
                            raise ValueError('Error in cancel Order')

                    # Place a market order to sell unsold lots
                    sell_target_order_id = place_market_order(self.api, self.LEG_TOKEN, option_type, 'S', unsold_lots, 'end')
                    trace_execution(f'INSIDE sell_order_id :{sell_target_order_id}')

                    # Confirm the new order placement
                    while not (sell_target_order_id in ORDER_STATUS and ORDER_STATUS[sell_target_order_id].get('tsym')):
                        trace_execution("Waiting for buy_back_order_id and 'tsym' data...")
                        time.sleep(0.25)

                    trace_execution(f'ORDER_STATUS[sell_target_order_id]: {ORDER_STATUS[sell_target_order_id]}')
                    break

                time.sleep(1)  # Polling delay to avoid busy waiting

            return sell_target_order_id

        except Exception as e:
            if not self.exited_strategy_completed:
                trace_execution(f'Error in check_for_stop_loss: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'check_for_stop_loss Error but already exited: {e}')



        

    def sell_at_limit_price(self, option_type, buydetails):
        trace_execution('entered in sell_at_limit_price')
        try:
            # Retrieve the latest order status
            ORDER_STATUS = self.api_websocket.get_latest_data()
            buy_back_lots = self.BUY_BACK_LOTS * self.ONE_LOT_QUANTITY

            # Set and log buy-back average price
            buy_back_avg_price = float(buydetails['buy_back_avg_price'])
            self.PRICE_DATA[f"{option_type}_PRICE_DATA"][f"BUY_BACK_BUY_{option_type}"] = buy_back_avg_price
            trace_execution(f'crossed 1 {buy_back_avg_price} {self.PRICE_DATA[f"{option_type}_PRICE_DATA"][f"BUY_BACK_BUY_{option_type}"]}')
            # Calculate the sell target price based on the buy-back price and target percentage
            sell_target_price = round_to_nearest_0_05(buy_back_avg_price * float(1 + self.SELL_TARGET_PERCENTAGE))
            trace_execution(f"Calculated sell target price for {option_type}: {sell_target_price}")

            # Place a limit sell order
            sell_target_order_id = place_limit_order(
                self.api,
                self.LEG_TOKEN,
                option_type,
                'S',
                buy_back_lots,
                limit_price=sell_target_price,
                leg_type='end'
            )

            # Wait for order confirmation
            while not (sell_target_order_id in ORDER_STATUS and ORDER_STATUS[sell_target_order_id].get('tsym')):
                trace_execution("Waiting for order confirmation...")
                time.sleep(0.25)

            # Log the sell order details
            logger_entry(
                self.strategy_log_class,
                ORDER_STATUS[sell_target_order_id]['tsym'],
                sell_target_order_id,
                'S',
                option_type,
                buy_back_lots,
                sell_target_price,
                'LMT',
                0,
                0,
                'placed'
            )

            # Add the sell target order ID to the current strategy orders
            self.CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
            trace_execution(f"Sell target order placed successfully for {option_type}: {sell_target_order_id}")

            return {
                'sell_target_order_id': sell_target_order_id,
                'sell_target_price': sell_target_price
            }

        except Exception as e:
            if not self.exited_strategy_completed:
                trace_execution(f'Error in sell_at_limit_price: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'sell_at_limit_price Error but already exited: {e}')
       
        
        
    def buy_at_limit_price(self, option_type, sell_price):
        trace_execution('entered in buy_at_limit_price')
        try:
            # Calculate the buy-back lot size and price
            buy_back_lots = self.BUY_BACK_LOTS * self.ONE_LOT_QUANTITY
            buy_back_price = round_to_nearest_0_05(float(sell_price) * self.BUY_BACK_PERCENTAGE)
            
            trace_execution(f"Calculated buy-back price for {option_type}: {buy_back_price}")

            # Place a limit buy order
            buy_back_order_id = place_limit_order(
                self.api,
                self.LEG_TOKEN,
                option_type,
                'B',
                buy_back_lots,
                limit_price=buy_back_price,
                leg_type='start'
            )

            # Wait for order confirmation
            ORDER_STATUS = self.api_websocket.get_latest_data()
            while not (buy_back_order_id in ORDER_STATUS and ORDER_STATUS[buy_back_order_id].get('tsym')):
                trace_execution("Waiting for buy_back_order_id and 'tsym' data...")
                time.sleep(0.25)

            # Log order placement details
            logger_entry(
                self.strategy_log_class,
                ORDER_STATUS[buy_back_order_id]['tsym'],
                buy_back_order_id,
                'B',
                option_type,
                buy_back_lots,
                buy_back_price,
                'LMT',
                0,
                0,
                'placed'
            )

            # Add the buy-back order ID to the current strategy orders
            self.CURRENT_STRATEGY_ORDERS.append(buy_back_order_id)
            trace_execution(f"Buy-back order placed successfully for {option_type}: {buy_back_order_id}")

            # Monitor for order completion
            log_buy = ThrottlingLogger(buy_back_order_id, logger_entry)
            while not is_order_complete(buy_back_order_id, ORDER_STATUS, log_buy, self.strategy_log_class):
                time.sleep(0.25)

            # Retrieve and log the average price for the completed order
            buy_back_avg_price = ORDER_STATUS[buy_back_order_id]['avgprc']
            self.PRICE_DATA[f"{option_type}_PRICE_DATA"][f"BUY_BACK_BUY_{option_type}"] = buy_back_avg_price

            return {
                'buy_back_avg_price': buy_back_avg_price,
                'buy_back_order_id': buy_back_order_id
            }

        except Exception as e:
            if not self.exited_strategy_completed:
                trace_execution(f'Error while executing buy_at_limit_price: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'buy_at_limit_price Error but already exited: {e}')


    # Monitor individual leg logic (CE/PE)
    def monitor_leg(self, option_type, sell_price):
        try:
            trace_execution('entered in monitor_leg')
            ORDER_STATUS = self.api_websocket.get_latest_data()
            leg_entry = False
            trace_execution(f'Starting monitor for {option_type}')

            while self.strategy_running and not leg_entry:
                # Fetch the latest traded price (LTP) for the option leg
                ltp = self.api_websocket.fetch_last_trade_price(option_type, self.LEG_TOKEN)

                if self.exited_strategy_started or self.stop_event.is_set():
                    break

                # Check if the LTP has reached the stop-loss threshold
                if ltp <= (sell_price * self.SAFETY_STOP_LOSS_PERCENTAGE):
                    leg_entry = True
                    trace_execution(f"{option_type} reached safety stop-loss threshold, exiting position...")

                    # Buy back the leg at the limit price and then sell at the target price
                    buydetails = self.buy_at_limit_price(option_type, sell_price)
                    selldetails = self.sell_at_limit_price(option_type, buydetails)

                    # Check if we need to exit based on stop event
                    if self.exited_strategy_started or self.stop_event.is_set():
                        break

                    # Monitor for stop-loss condition on the sell target
                    sell_target_order_id = self.check_for_stop_loss(option_type, selldetails, buydetails)

                    # Wait for all orders to complete
                    if wait_for_orders_to_complete(
                        sell_target_order_id,
                        self.api_websocket,
                        logger_entry,
                        self.strategy_log_class,
                        timeout=40,
                        interval=0.25
                    ):
                        # Log completion and add order details to current strategy orders
                        self.CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
                        self.PRICE_DATA[f"{option_type}_PRICE_DATA"][f"BUY_BACK_SELL_{option_type}"] = float(
                            ORDER_STATUS[sell_target_order_id]['avgprc']
                        )
                        trace_execution(f"{option_type} completed with order ID {sell_target_order_id}")
                        trace_execution(f"{option_type} {self.PRICE_DATA} ORDER PRICE DETAILS")
                    break
            trace_execution(f'end_monitor {option_type}')
            return True

        except (TypeError, ZeroDivisionError, ValueError) as e:
            if not self.exited_strategy_completed:
                trace_execution(f'Error in monitor_leg ({type(e).__name__}): {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_leg Error but already exited: {e}')
            raise ValueError('Error on exit')
            
        except Exception as e:
            # Catch all other exceptions
            if not self.exited_strategy_completed:
                trace_execution(f'Unexpected error in monitor_leg: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_leg Error but already exited: {e}')
            raise ValueError('Error on exit')


    # Function to monitor the strategy
    def monitor_strategy(self):
        try:
            trace_execution('entered in monitor_strategy')
            end_time = ist_datatime.replace(
                hour=self.EXIT_TIME['hours'],
                minute=self.EXIT_TIME['minutes'],
                second=self.EXIT_TIME['seconds'],
                microsecond=0
            ).time()

            while self.strategy_running:
                if self.exited_strategy_started or self.stop_event.is_set():
                    break

                current_time = datetime.now(ist).time()
                if current_time >= end_time:
                    trace_execution('End time reached, exiting strategy.')
                    self.exit_strategy()
                    break

                # Calculate the PNL and check for target or max loss conditions
                pnl = self.calculate_total_pnl(False)
                if pnl >= self.TARGET_PROFIT and not self.exited_strategy_started:
                    trace_execution(f"Target profit of ₹{self.TARGET_PROFIT} reached. Exiting strategy.")
                    self.exit_strategy()
                    break
                elif pnl <= -self.MAX_LOSS and not self.exited_strategy_started:
                    trace_execution(f"Max loss of ₹{self.MAX_LOSS} reached. Exiting strategy.")
                    self.exit_strategy()
                    break

                time.sleep(5)  # Check PNL every 5 seconds
            return True

        except (TypeError, ZeroDivisionError, ValueError) as e:
            # Handle specific errors and exit strategy if needed
            if not self.exited_strategy_completed:
                trace_execution(f'{type(e).__name__} error in monitor_strategy: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')

        except Exception as e:
            # Catch all other exceptions
            if not self.exited_strategy_completed:
                trace_execution(f'Unexpected error in monitor_strategy: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'monitor_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')


    def check_order_qty(self):
        totals = {'CE': 0, 'PE': 0}
        symbols = {'CE': '', 'PE': ''}
        try:
            trace_execution('entered in check_order_qty')
            ORDER_STATUS = self.api_websocket.get_latest_data()
            unique_orders = set(self.CURRENT_STRATEGY_ORDERS)

            for order_id in unique_orders:
                order = ORDER_STATUS.get(order_id)
                if not order:
                    trace_execution(f"Order {order_id} not found in ORDER_STATUS, skipping...")
                    continue

                status = order.get('status', '').lower()
                if status not in ['open', 'pending', 'trigger_pending', 'complete']:
                    trace_execution(f"Order {order_id} has invalid status '{status}', skipping...")
                    continue

                qty = float(order.get('qty', 0))
                tsym = order.get('tsym')
                typ = order.get('trantype')
                option_info = order.get('option_type', '').split()
                if len(option_info) < 2:
                    trace_execution(f"Invalid option_type format for order {order_id}, skipping...")
                    continue

                option_type, leg_type = option_info[0], option_info[1]
                trace_execution(f"Processing order {order_id}: Leg Type: {leg_type}, Status: {status}, Option Type: {option_type}, Qty: {qty}, Type: {typ}")

                # Cancel incomplete orders
                if status in ['open', 'pending', 'trigger_pending']:
                    trace_execution(f"Canceling incomplete order: {order_id}")
                    cancel_response = self.api.cancel_order(order_id)
                    if 'result' not in cancel_response:
                        current_orders = self.api_websocket.get_latest_data()
                        current_status = current_orders.get(order_id, {}).get('status', '').lower()
                        if current_status != 'complete':
                            raise ValueError(f"Error in canceling Order {order_id}")
                    logger_entry(
                        self.strategy_log_class, tsym, order_id, typ, option_type, qty, str(cancel_response),
                        'CANCEL', 0, 0, 'cancel_order'
                    )
                    if leg_type == 'start':  # Skip quantity for initial unexecuted orders
                        continue
                    qty = float(order.get('flqty', 0))  # Adjusted filled quantity

                # Update totals for completed orders
                if option_type in totals:
                    if typ == 'S':
                        totals[option_type] -= qty
                    elif typ == 'B':
                        totals[option_type] += qty
                    symbols[option_type] = tsym

            trace_execution('completed in check_order_qty')
            return {
                'symbols': symbols,
                'totals': totals
            }

        except Exception as e:
            if not self.exited_strategy_completed:
                trace_execution(f'Error in check_order_qty: {e}')
                self.exit_strategy()
            else:
                trace_execution(f'check_order_qty Error but already exited: {e}')
            raise ValueError('Error in check_order_qty')

        
    # Function to exit the strategy
    def exit_strategy(self):
        try:
            trace_execution('entered in exit_strategy')
            
            # Stop the strategy
            self.strategy_running = False
            
            # Check if exit strategy has already been initiated
            if self.exited_strategy_started:
                raise ValueError('Error: exit_strategy already called.')
            self.exited_strategy_started = True
            trace_execution('Exiting strategy...')
            
            # Retrieve the latest order status
            ORDER_STATUS = self.api_websocket.get_latest_data()
            trace_execution(f'Current ORDER_STATUS: {ORDER_STATUS}')
            
            # Check the current order quantities
            values = self.check_order_qty()
            totals = values['totals']
            symbols = values['symbols']
            trace_execution(f"Totals: {totals}, Symbols: {symbols}")
            
            # Place market exit orders for remaining positions
            for option_type, total_qty in totals.items():
                if total_qty != 0:
                    buy_or_sell = 'S' if total_qty > 0 else 'B'
                    tsym = symbols[option_type]
                    trace_execution(f"Placing market exit for {option_type}: {buy_or_sell} {abs(total_qty)} lots")
                    
                    # Place market exit order
                    order_id = place_market_exit(self.api, tsym, buy_or_sell, abs(total_qty))
                    self.CURRENT_STRATEGY_ORDERS.append(order_id)
                    
                    # Wait for the order to complete
                    wait_for_orders_to_complete(
                        order_id,
                        self.api_websocket,
                        logger_entry,
                        self.strategy_log_class,
                        timeout=100
                    )
            
            # Verify that all positions have been closed
            final_values = self.check_order_qty()
            for option_type, final_total in final_values['totals'].items():
                if final_total != 0:
                    raise ValueError(f"Error: Positions not fully closed for {option_type}.")
            
            # Set strategy exit completion flag
            self.exited_strategy_completed = True
            
            # Signal any waiting threads or processes
            if self.stop_event:
                self.stop_event.set()
            
            trace_execution('Strategy exited successfully')
            trace_execution(f'Strategy profit and loss: {self.calculate_total_pnl(True)}')
            
            # Optionally unsubscribe from all symbols
            # self.api.unsubscribe_all()
            
            return True
        
        except Exception as e:
            # Handle exceptions and ensure proper logging
            if not self.exited_strategy_completed:
                trace_execution(f'An error occurred in exit_strategy: {e}')
                # Optionally unsubscribe from all symbols
                # self.api.unsubscribe_all()
            else:
                trace_execution(f'exit_strategy Error but already exited: {e}')
            raise ValueError('Error on exit')


    def run_strategy(self):
        trace_execution('passed run_strategy')
        
        # Initialize necessary variables
        self.strategy_log_class = LocalJsonLogger()
        start_time = ist_datatime.replace(
            hour=self.ENTRY_TIME['hours'], 
            minute=self.ENTRY_TIME['minutes'], 
            second=self.ENTRY_TIME['seconds'], 
            microsecond=0
        ).time()
        end_time = ist_datatime.replace(
            hour=self.EXIT_TIME['hours'], 
            minute=self.EXIT_TIME['minutes'], 
            second=self.EXIT_TIME['seconds'], 
            microsecond=0
        ).time()
        
        lots = self.INITIAL_LOTS * self.ONE_LOT_QUANTITY
        trace_execution('entered run_strategy')

        while not self.strategy_running:
            current_time = datetime.now(ist).time()
            
            if current_time >= end_time:
                self.exit_strategy()
                break

            if start_time <= current_time <= end_time:
                if not self.strategy_running:
                    atm_strike = self.fetch_atm_strike()
                    trace_execution('ATM strike price fetched')

                    # Fetch initial sell prices for CE and PE
                    sell_price_ce = self.api_websocket.fetch_last_trade_price('CE', self.LEG_TOKEN)
                    sell_price_pe = self.api_websocket.fetch_last_trade_price('PE', self.LEG_TOKEN)
                    
                    trace_execution(f'Option Prices - CE: {sell_price_ce}, PE: {sell_price_pe}')
                    trace_execution(f'passed OPTION PRICE {atm_strike - self.STRIKE_DIFFERENCE} pe price {sell_price_pe} _ {atm_strike + self.STRIKE_DIFFERENCE} pe price {sell_price_ce}')

                    # Calculate lots based on available margin if BUY_BACK_STATIC is not set
                    if not self.BUY_BACK_STATIC:
                        ce_lot = int(self.AVAILABLE_MARGIN / (self.ONE_LOT_QUANTITY * sell_price_ce))
                        pe_lot = int(self.AVAILABLE_MARGIN / (self.ONE_LOT_QUANTITY * sell_price_pe))
                        self.BUY_BACK_LOTS = min(ce_lot, pe_lot)

                    # Log initial order entries
                    logger_entry(self.strategy_log_class, 'CE', 'orderno', 'direction', 'CE', self.ONE_LOT_QUANTITY, sell_price_ce, 'GET MKT', 0, 0, 'start')
                    logger_entry(self.strategy_log_class, 'PE', 'orderno', 'direction', 'PE', self.ONE_LOT_QUANTITY, sell_price_pe, 'GET MKT', 0, 0, 'start')

                    # Initialize price data for CE and PE
                    self.PRICE_DATA = {
                        'CE_PRICE_DATA': {'INITIAL_SELL_CE': 0},
                        'PE_PRICE_DATA': {'INITIAL_SELL_PE': 0}
                    }

                    # Start monitoring threads for CE and PE legs and strategy
                    self.strategy_running = True
                    ce_thread = MyThread(target=self.monitor_leg, args=('CE', sell_price_ce), daemon=True)
                    pe_thread = MyThread(target=self.monitor_leg, args=('PE', sell_price_pe), daemon=True)
                    strategy_thread = MyThread(target=self.monitor_strategy, daemon=True)

                    try:
                        trace_execution('Starting strategy threads')
                        ce_thread.start()
                        pe_thread.start()
                        strategy_thread.start()
                        
                        ce_thread.join()
                        pe_thread.join()
                        self.exit_strategy()
                        strategy_thread.join()
                        break

                    except (TypeError, ZeroDivisionError, ValueError) as e:
                        if not self.exited_strategy_completed:
                            trace_execution(f'Error in run_strategy ({type(e).__name__}): {e}')
                            self.exit_strategy()
                        else:
                            trace_execution(f'run_strategy Error but already exited: {e}')
                        raise ValueError('Error on exit')

                    except Exception as e:
                        if not self.exited_strategy_completed:
                            trace_execution(f'Unexpected error in run_strategy: {e}')
                            self.exit_strategy()
                        else:
                            trace_execution(f'run_strategy Error but already exited: {e}')
                        raise ValueError('Error on exit')

            else:
                # Calculate time to sleep until start_time
                time_to_sleep = (datetime.combine(datetime.today(), start_time) - datetime.combine(datetime.today(), current_time)).total_seconds()
                trace_execution("Outside trading hours, strategy paused.")
                time.sleep(max(time_to_sleep, 0))  # Ensure no negative sleep

        return True
