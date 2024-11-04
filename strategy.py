import time
import os, sys
from urllib.parse import parse_qs, urlparse
import hashlib
import logging
from utils import ist, round_to_nearest_0_05, place_limit_order, place_market_order, place_market_exit, is_order_complete, wait_for_orders_to_complete, check_unsold_lots
from brokerapi import getshoonyatradeapi
from datetime import datetime
from logger import LocalJsonLogger, ThrottlingLogger, logger_entry
from api_websocket import OpenWebSocket
from custom_threading import MyThread
from seperate_strategy import NewStrategy





logging.basicConfig(filename=f'strategy_log_files/strategy__{datetime.now(ist).strftime("%Y_%m%d_%H %M %S")}.log', level=logging.INFO)

def trace_execution(str= 'no data', data=datetime.now(ist).strftime("%Y %m %d - %H /%M/ %S")):
    print(f'{str} at {data}')
    logging.info(f'{str} at {data}')
# flag to tell us if the api_websocket is open


# Constants Configs
SYMBOL = 'Nifty bank'
BUY_BACK_STATIC = True
INITIAL_LOTS = 1  # Start with 1 lot
STRIKE_DIFFERENCE = 300
ONE_LOT_QUANTITY = 15  # Number of units per lot in Bank Nifty
TARGET_PROFIT = 500
MAX_LOSS = 300
MAX_LOSS_PER_LEG = 200
SAFETY_STOP_LOSS_PERCENTAGE = 0.83
BUY_BACK_PERCENTAGE = 0.82
SELL_TARGET_PERCENTAGE = 0.025
BUY_BACK_LOSS_PERCENTAGE = 0.90
AVAILABLE_MARGIN = 5000
ENTRY_TIME = {
    'hours': 9,
    'minutes': 33,
    'seconds': 0
}
EXIT_TIME = {
    'hours': 14,
    'minutes': 50,
    'seconds': 0

}

# DYNAMIC CONFIG
BUY_BACK_LOTS = 1





# Strategy LEVEL global Variables

LEG_TOKEN = {}
PRICE_DATA = {
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
CURRENT_STRATEGY_ORDERS = []
subscribedTokens = []




# Global variables
strategy_running = False
exited_strategy_started = False
exited_strategy_completed = True
sell_price_ce = 0
sell_price_pe = 0
ist_datatime = datetime.now(ist)

#api = getflattradeapi()
api = {}

strategy_log_class = {}









# Utility function to fetch the ATM strike price
def fetch_atm_strike(self):
    trace_execution('entered in fetch_atm_strike')

    try:
        # Fetch the current Bank Nifty price
        banknifty_price = api.get_quotes(exchange='NSE', token='26009')
        current_price = float(banknifty_price['lp'])
        print(current_price)

        # Calculate the ATM strike price rounded to the nearest 100
        atm_strike = round(current_price / 100) * 100
        print(atm_strike)

        # Generate nearest CE and PE option symbols based on ATM strike and strike difference
        nearest_symbol_ce = f"{atm_strike + STRIKE_DIFFERENCE} NIFTY BANK CE"
        nearest_symbol_pe = f"{atm_strike - STRIKE_DIFFERENCE} NIFTY BANK PE"

        # Fetch option chain details for both CE and PE
        option_chains_ce = api.searchscrip(exchange='NFO', searchtext=nearest_symbol_ce)
        option_chains_pe = api.searchscrip(exchange='NFO', searchtext=nearest_symbol_pe)

        ce_option = option_chains_ce['values'][0]
        pe_option = option_chains_pe['values'][0]

        # Set up token details for both CE and PE
        LEG_TOKEN = {
            'PE': pe_option['token'],
            'CE': ce_option['token'],
            'PE_tsym': pe_option['tsym'],
            'CE_tsym': ce_option['tsym']
        }

        # Subscription for tokens if not already subscribed
        subscribeDataPE = f"NFO|{pe_option['token']}"
        subscribeDataCE = f"NFO|{ce_option['token']}"
        
        if subscribeDataPE not in subscribedTokens or subscribeDataCE not in subscribedTokens:
            api.subscribe([subscribeDataPE, subscribeDataCE])
            subscribedTokens.extend([subscribeDataPE, subscribeDataCE])

        trace_execution('completed in fetch_atm_strike')
        return atm_strike

    except Exception as e:
        trace_execution(f'Error in fetch_atm_strike: {e}')
        return None


# Calculate PNL based on current leg status
def calculate_leg_pnl(option_type, type, lots, api_websocket):
    global PRICE_DATA
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
        last_traded_price = api_websocket.fetch_last_trade_price(option_type, LEG_TOKEN)
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
        
        pnl = difference * lots * ONE_LOT_QUANTITY
        return float(pnl)
    except Exception as e:
        if not exited_strategy_completed:
            exit_strategy(api_websocket, {})
            trace_execution(f'Error in calculate_leg_pnl: {e}')
        else:
            trace_execution(f'calculate_leg_pnl Error but already exited: {e}')
        

    
# Function to calculate total PNL
def calculate_total_pnl(api_websocket, log=False):
    try:
        ce_entry_pnl = calculate_leg_pnl('CE', 'INITIAL', INITIAL_LOTS, api_websocket)
        pe_entry_pnl = calculate_leg_pnl('PE', 'INITIAL', INITIAL_LOTS, api_websocket)
        ce_pnl = calculate_leg_pnl('CE', 'BUY_BACK', BUY_BACK_LOTS, api_websocket)
        pe_pnl = calculate_leg_pnl('PE', 'BUY_BACK', BUY_BACK_LOTS, api_websocket)
        ce_re_entry_pnl = calculate_leg_pnl('CE', 'RE_ENTRY', INITIAL_LOTS, api_websocket)
        pe_re_entry_pnl = calculate_leg_pnl('PE', 'RE_ENTRY', INITIAL_LOTS, api_websocket)  # Corrected to 'PE'
        pnl = ce_pnl + pe_pnl + ce_entry_pnl + pe_entry_pnl + ce_re_entry_pnl + pe_re_entry_pnl
        if log:
            trace_execution(f'pnl ce_pnl {ce_pnl} + pe_pnl {pe_pnl} + ce_entry_pnl {ce_entry_pnl} + pe_entry_pnl {pe_entry_pnl} + ce_re_entry_pnl {ce_re_entry_pnl} + pe_re_entry_pnl{pe_re_entry_pnl}')
        return pnl
    except Exception as e:
        if not exited_strategy_completed:
            trace_execution(f'Error in calculate_total_pnl: {e}')
            exit_strategy(api_websocket, {})
        else:
            trace_execution(f'calculate_total_pnl Error but already exited: {e}')

def check_for_stop_loss(option_type, stop_event, selldetails, buydetails, api_websocket):
    global PRICE_DATA
    trace_execution('entered in check_for_stop_loss')
    try:
        ORDER_STATUS = api_websocket.get_latest_data()
        sell_target_order_id = selldetails['sell_target_order_id']
        buy_back_order_id = buydetails['buy_back_order_id']
        log_sell = ThrottlingLogger(sell_target_order_id, logger_entry)
        while not is_order_complete(sell_target_order_id, ORDER_STATUS, log_sell ,strategy_log_class): #static instead check weather ltp > selltarget_price
            if exited_strategy_started or stop_event.is_set():
                break
            ltp = api_websocket.fetch_last_trade_price(option_type, LEG_TOKEN)  # Fetch LTP for the option leg
            legpnl = calculate_leg_pnl(option_type, 'BUY_BACK', BUY_BACK_LOTS, api_websocket)

            if legpnl <= -MAX_LOSS_PER_LEG or ltp <=  (float(ORDER_STATUS[buy_back_order_id]['avgprc']) * BUY_BACK_LOSS_PERCENTAGE):
                trace_execution(f"{option_type} {legpnl} reached 10% loss, exiting remaining orders.")
                trace_execution(f"{option_type} {PRICE_DATA} ORDER PRICE DETAILS")
                unsold_lots = check_unsold_lots(sell_target_order_id, api_websocket)
                cancel_responce = api.cancel_order(sell_target_order_id)
                logger_entry(strategy_log_class, 'tsym',sell_target_order_id, 'typ',option_type,'qty',str(cancel_responce), 'CAN', 0, 0, 'cancel_order')
                if 'result' not in cancel_responce:
                    current_orders = api_websocket.get_latest_data()
                    current_status = current_orders.get(sell_target_order_id, {}).get('status', '').lower()
                    if current_status != 'complete':
                        raise ValueError('Error in cancel Order')
                sell_target_order_id = place_market_order(api, LEG_TOKEN, option_type, 'S', unsold_lots, 'end')
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
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'check_for_stop_loss Error but already exited: {e}')

    

def sell_at_limit_price(option_type,api_websocket, buydetails):
    global PRICE_DATA
    trace_execution('entered in sell_at_limit_price')
    try:
        ORDER_STATUS = api_websocket.get_latest_data()
        buy_back_lots = BUY_BACK_LOTS * ONE_LOT_QUANTITY
        print(f"{option_type} sell_at_limit_price...0")
        buy_back_avg_price = buydetails['buy_back_avg_price']
        PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_BUY_'+option_type] = buy_back_avg_price            
        sell_target_price = round_to_nearest_0_05(float(buy_back_avg_price) * float(1 + SELL_TARGET_PERCENTAGE))
        print(f"{option_type} ThrottlingLogger... 2")
        print(f"{option_type} ThrottlingLogger... 2.1")
        sell_target_order_id = place_limit_order(api, LEG_TOKEN, option_type, 'S', buy_back_lots, limit_price=sell_target_price, leg_type='end')
        while not (sell_target_order_id in ORDER_STATUS and ORDER_STATUS[sell_target_order_id].get('tsym')):
            # Optionally perform some action or add a delay to avoid busy waiting
            print("Waiting for buy_back_order_id and 'tsym' data...")
            time.sleep(0.25)
        print(f"{option_type} ThrottlingLogger... 2.2 {sell_target_order_id}")
        logger_entry(strategy_log_class, ORDER_STATUS[sell_target_order_id]['tsym'],sell_target_order_id,'S',option_type,buy_back_lots,sell_target_price, 'LMT', 0, 0, 'placed')
        print(f'OUTSIDE sell_target_order_id {sell_target_order_id}')
        CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
        print(f"{option_type} ThrottlingLogger... 3")

            
        return {
            'sell_target_order_id': sell_target_order_id,
            'sell_target_price': sell_target_price
        }
    except Exception as e:
        if not exited_strategy_completed:
            trace_execution(f'error in sell_at_limit_price: {e}')
            exit_strategy(api_websocket, {})
        else:
            trace_execution(f'sell_at_limit_price Error but already exited: {e}')
    
    
    
    
def buy_at_limit_price(option_type, sell_price, api_websocket):
    global PRICE_DATA, logger_entry
    trace_execution('entered in buy_at_limit_price')
    try:
        print(f"{option_type} buy_at_limit_price...0")
        buy_back_lots = BUY_BACK_LOTS * ONE_LOT_QUANTITY
        ORDER_STATUS = api_websocket.get_latest_data()
        buy_back_price = round_to_nearest_0_05(float(sell_price) * float(BUY_BACK_PERCENTAGE))
        print(f"{option_type} reached round_to_nearest_0_05...")
        buy_back_order_id = place_limit_order(api, LEG_TOKEN, option_type, 'B', buy_back_lots, limit_price=buy_back_price, leg_type='start')
        while not (buy_back_order_id in ORDER_STATUS and ORDER_STATUS[buy_back_order_id].get('tsym')):
            # Optionally perform some action or add a delay to avoid busy waiting
            print("Waiting for buy_back_order_id and 'tsym' data...")
            time.sleep(0.25)
        logger_entry(strategy_log_class, ORDER_STATUS[buy_back_order_id]['tsym'] ,buy_back_order_id,'B',option_type,buy_back_lots,buy_back_price, 'LMT', 0, 0, 'placed')
        CURRENT_STRATEGY_ORDERS.append(buy_back_order_id)
        print(f"{option_type} ThrottlingLogger...0")
        log_buy = ThrottlingLogger(buy_back_order_id, logger_entry)
        while not is_order_complete(buy_back_order_id, ORDER_STATUS, log_buy, strategy_log_class):
            time.sleep(0.25)
        print(f"{option_type} ThrottlingLogger... 1")
        buy_back_avg_price = ORDER_STATUS[buy_back_order_id]['avgprc']
        PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_BUY_'+option_type] = buy_back_avg_price
        return {
            'buy_back_avg_price' : buy_back_avg_price,
            'buy_back_order_id' : buy_back_order_id
        }
    except Exception as e:
        if not exited_strategy_completed:
            trace_execution(f'Error while buy_at_limit_price: {e}')
            exit_strategy(api_websocket, {})
        else:
            trace_execution(f'buy_at_limit_price Error but already exited: {e}')

# Monitor individual leg logic (CE/PE)
def monitor_leg(option_type, sell_price, strike_price, stop_event, api_websocket):
    try:
        global strategy_running, PRICE_DATA, exited_strategy_started, logger_entry
        trace_execution('entered in monitor_leg')
        ORDER_STATUS = api_websocket.get_latest_data()
        # PRICE_DATA[option_type+'_PRICE_DATA']['INITIAL_BUY_'+option_type] = sell_price
        leg_entry = False
        print('monitor '+option_type)
        while strategy_running and not leg_entry:
            # print('while check monitor')
            ltp = api_websocket.fetch_last_trade_price(option_type, LEG_TOKEN)  # Fetch LTP for the option leg
            if exited_strategy_started or stop_event.is_set():
                break
            if ltp <= (float(sell_price) * float(SAFETY_STOP_LOSS_PERCENTAGE)):
                leg_entry = True

                print(f"{option_type} reached 76% of sell price, exiting...")
                buydetails = buy_at_limit_price(option_type, sell_price, api_websocket)
                selldetails = sell_at_limit_price(option_type, api_websocket, buydetails)
                print(f"{option_type} ThrottlingLogger... 4 {selldetails}")
                if exited_strategy_started or stop_event.is_set():
                    break
                print(f"{option_type} ThrottlingLogger... 5")
                
                sell_target_order_id = check_for_stop_loss(option_type, stop_event, selldetails, buydetails, api_websocket)
                
                if wait_for_orders_to_complete(sell_target_order_id, api_websocket, logger_entry, strategy_log_class, 40, 0.25):
                    CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
                    PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_SELL_'+option_type] = float(ORDER_STATUS[sell_target_order_id]['avgprc'])
                    print(f"{option_type} {PRICE_DATA} ORDER PRICE DETAILS")
                    print('------------------------------------')
                    print(f"{option_type} ThrottlingLogger... 6 {sell_target_order_id}, {ORDER_STATUS}")
                print('end_monitor '+option_type)
                break
        return True
    except TypeError as e:
        if not exited_strategy_completed:
            trace_execution(f'Type error in monitor_leg: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_leg Error but already exited: {e}')
        raise ValueError('Error on exit')
    except ZeroDivisionError as e:
        if not exited_strategy_completed:
            trace_execution(f'Math error in monitor_leg: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_leg Error but already exited: {e}')
        raise ValueError('Error on exit')
    except ValueError as e:
        if not exited_strategy_completed:
            trace_execution(f'Value error in monitor_leg: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_leg Error but already exited: {e}')
        raise ValueError('Error on exit')
    except Exception as e:
        # Catch all other exceptions
        if not exited_strategy_completed:
            trace_execution(f'error in monitor_leg: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_leg Error but already exited: {e}')
        raise ValueError('Error on exit')
    



# Function to monitor the strategy
def monitor_strategy(stop_event, api_websocket):
    try:
        global strategy_running, exited_strategy_started
        print('monitor_strategy ')
        trace_execution('entered in monitor_strategy')
        end_time = ist_datatime.replace(hour=EXIT_TIME['hours'], minute=EXIT_TIME['minutes'], second=EXIT_TIME['seconds'], microsecond=0).time()
        while strategy_running:
            if exited_strategy_started or stop_event.is_set():
                break
            
            current_time = datetime.now(ist).time()
            if current_time >= end_time:
                exit_strategy(api_websocket, stop_event)
            pnl = calculate_total_pnl(api_websocket)  # Fetch the PNL
            if pnl >= TARGET_PROFIT and not exited_strategy_started:
                print(f"Target profit of ₹{TARGET_PROFIT} reached. Exiting strategy.")
                # strategy_running = False
                exit_strategy(api_websocket, stop_event)
                break
            elif pnl <= -MAX_LOSS and not exited_strategy_started:
                print(f"Max loss of ₹{MAX_LOSS} reached. Exiting strategy.")
                # strategy_running = False
                exit_strategy(api_websocket, stop_event)
                print('checking pnl')
                break
            time.sleep(5)  # Check PNL every 5 seconds
        return True
    except TypeError as e:
        if not exited_strategy_completed:
            trace_execution(f'Type error in monitor_strategy: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_strategy Error but already exited: {e}')
        raise ValueError('Error on exit')
    except ZeroDivisionError as e:
        if not exited_strategy_completed:
            trace_execution(f'Math error in monitor_strategy: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_strategy Error but already exited: {e}')
        raise ValueError('Error on exit')
    except ValueError as e:
        if not exited_strategy_completed:
            trace_execution(f'Value error in monitor_strategy: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_strategy Error but already exited: {e}')
        raise ValueError('Error on exit')
    except Exception as e:
        # Catch all other exceptions
        if not exited_strategy_completed:
            trace_execution(f'monitor_strategy error in monitor_strategy: {e}')
            exit_strategy(api_websocket, stop_event)
        else:
            trace_execution(f'monitor_strategy Error but already exited: {e}')
        raise ValueError('Error on exit')

def check_order_qty(api_websocket):
    totals = {'CE': 0, 'PE': 0}
    symbols = {'CE': '', 'PE': ''}
    try:
        trace_execution('entered in check_net_qty')
        ORDER_STATUS = api_websocket.get_latest_data()
        # Initialize totals and symbol tracking for CE and PE
            # Filter unique values using set
        unique_orders = set(CURRENT_STRATEGY_ORDERS)

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
                cancel_responce = api.cancel_order(key)
                if 'result' not in cancel_responce:
                    current_orders = api_websocket.get_latest_data()
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
            exit_strategy(api_websocket, {})
            logging.error(f'An unexpected error occurred check_net_qty: {e}')
        else:
            trace_execution(f'check_net_qty Error but already exited: {e}')
        raise ValueError('Error on check_net_qty')

    
# Function to exit the strategy
def exit_strategy(api_websocket, stop_event):
    try:
        global strategy_running, exited_strategy_started, exited_strategy_completed
        trace_execution('entered in exit_strategy')
        ORDER_STATUS = api_websocket.get_latest_data() 
        strategy_running = True  # Stop the strategy
        if exited_strategy_started:
            raise ValueError(f'Error in exit strategy already exit function called')
        exited_strategy_started = True
        trace_execution('Exiting strategy...')
        trace_execution('Current ORDER_STATUS:', ORDER_STATUS)

        values = check_order_qty(api_websocket)
        totals = values['totals']
        symbols = values['symbols']
        trace_execution(f"Totals: {totals}, Symbols: {symbols}")
        # Place market exit orders for remaining positions
        for option_type, total in totals.items():
            if total != 0:
                buy_or_sell = 'S' if total > 0 else 'B'
                tsym = symbols[option_type]
                trace_execution(f"Placing market exit for {option_type}: {buy_or_sell} {abs(total)} lots")
                order_id = place_market_exit(api, tsym, buy_or_sell, abs(total))
                CURRENT_STRATEGY_ORDERS.append(order_id)
                wait_for_orders_to_complete(order_id, api_websocket, logger_entry, 100)
        # Implement logic to close all open orders and exit strategy
        final_qty = check_order_qty(api_websocket)
        for option_type, total in final_qty['totals'].items():
            if total != 0:
                raise ValueError('not sold completely')
        exited_strategy_completed = True
        if stop_event:
            stop_event.set()
        trace_execution(f'Strategy exited successfully')
        trace_execution(f'Strategy profit and loss {calculate_total_pnl(api_websocket, True)}')
        # api.unsubscribe() ## need 
        return True
    except Exception as e:
        # Catch all other exceptions
        if not exited_strategy_completed:
            # api.unsubscribe()
            logging.error(f'An unexpected error occurred exit_strategy: {e}')
        else:
            trace_execution(f'exit_strategy Error but already exited: {e}')
        raise ValueError('Error on exit')



        


def run_strategy(stop_event, api_websocket):
    trace_execution('passed run_strategy')
    global strategy_running, sell_price_ce, sell_price_pe, PRICE_DATA, BUY_BACK_LOTS, strategy_log_class
    strategy_log_class = LocalJsonLogger()
    start_time = ist_datatime.replace(hour=ENTRY_TIME['hours'], minute=ENTRY_TIME['minutes'], second=ENTRY_TIME['seconds'], microsecond=0).time()
    end_time = ist_datatime.replace(hour=EXIT_TIME['hours'], minute=EXIT_TIME['minutes'], second=EXIT_TIME['seconds'], microsecond=0).time()
    lots = INITIAL_LOTS * ONE_LOT_QUANTITY
    print('entered run_strategy')
    while not strategy_running:
        current_time = datetime.now(ist).time()
        if current_time >= end_time:
            exit_strategy(api_websocket, stop_event)
            break
        if start_time <= current_time <= end_time:
            if not strategy_running:
                atm_strike = fetch_atm_strike()
                trace_execution('passed atm strike')
                sell_price_ce = api_websocket.fetch_last_trade_price('CE', LEG_TOKEN)
                sell_price_pe = api_websocket.fetch_last_trade_price('PE', LEG_TOKEN)
                print(f'sell_price_ce{sell_price_ce}:sell_price_pe:{sell_price_pe}')
                trace_execution(f'passed OPTION PRICE {atm_strike - STRIKE_DIFFERENCE} pe price {sell_price_pe} _ {atm_strike + STRIKE_DIFFERENCE} pe price {sell_price_pe}')
                if(not BUY_BACK_STATIC):
                    ce_lot = int(AVAILABLE_MARGIN/(ONE_LOT_QUANTITY * sell_price_ce))
                    pe_lot = int(AVAILABLE_MARGIN/(ONE_LOT_QUANTITY * sell_price_pe))
                    BUY_BACK_LOTS = min(ce_lot, pe_lot)
                
                logger_entry(strategy_log_class, 'CE','orderno','direction','CE',ONE_LOT_QUANTITY,sell_price_ce,'GET MKT',0,0,'start')
                logger_entry(strategy_log_class, 'PE','orderno','direction','PE',ONE_LOT_QUANTITY,sell_price_pe,'GET MKT',0,0,'start')
                
                PRICE_DATA['CE_PRICE_DATA']['INITIAL_SELL_CE'] = 0
                PRICE_DATA['PE_PRICE_DATA']['INITIAL_SELL_PE'] = 0

                strategy_running = True

                ce_thread = MyThread(target=monitor_leg, args=('CE', sell_price_ce, atm_strike + STRIKE_DIFFERENCE,stop_event, api_websocket))
                pe_thread = MyThread(target=monitor_leg, args=('PE', sell_price_pe, atm_strike - STRIKE_DIFFERENCE,stop_event, api_websocket))
                strategy_thread = MyThread(target=monitor_strategy, args=(stop_event, api_websocket)) # static uncommen

                try:
                    trace_execution('passed try in run_strategy')
                    ce_thread.start()
                    pe_thread.start()              
                    strategy_thread.start() # static uncomment
                    ce_thread.join()
                    pe_thread.join()
                    exit_strategy(api_websocket, stop_event)
                    # dynamic_data.join()
                    strategy_thread.join() # static uncomment
                    break
                except TypeError as e:
                    if not exited_strategy_completed:
                        trace_execution(f'Typr error in run_strategy: {e}')
                        exit_strategy(api_websocket, stop_event)
                    else:
                        trace_execution(f'run_strategy Error but already exited: {e}')
                    raise ValueError('Error on exit')
                except ZeroDivisionError as e:
                    if not exited_strategy_completed:
                        trace_execution(f'Math error in run_strategy: {e}')
                        exit_strategy(api_websocket, stop_event)
                    else:
                        trace_execution(f'run_strategy Error but already exited: {e}')
                    raise ValueError('Error on exit')
                except ValueError as e:
                    if not exited_strategy_completed:
                        trace_execution(f'Value error in run_strategy: {e}')
                        exit_strategy(api_websocket, stop_event)
                    else:
                        trace_execution(f'run_strategy Error but already exited: {e}')
                    raise ValueError('Error on exit')
                except Exception as e:
                    # Catch all other exceptions
                    if not exited_strategy_completed:
                        trace_execution(f'error in run_strategy: {e}')
                        exit_strategy(api_websocket, stop_event)
                    else:
                        trace_execution(f'run_strategy Error but already exited: {e}')
                    raise ValueError('Error on exit')



        else:
            time_to_sleep = start_time - current_time
            print("Outside trading hours, strategy paused.")
            time.sleep(time_to_sleep)        
    return True

def start_the_strategy(stop_event):
    global api
    try:
        trace_execution(f'Starting WebSocket data connection...{datetime.now(ist).strftime("%Y %m %d - %H /%M/ %S")}')
        api = getshoonyatradeapi()
        api_websocket = OpenWebSocket(api)
        
        while not api_websocket.is_socket_opened():
            time.sleep(0.1)



        new_data = {
                    # API & WebSocket initialization
        'api': api,
        'api_websocket':api_websocket,

        # Strategy parameters
        'SYMBOL':SYMBOL,
        'BUY_BACK_STATIC':BUY_BACK_STATIC,
        'INITIAL_LOTS':INITIAL_LOTS,
        'STRIKE_DIFFERENCE':STRIKE_DIFFERENCE,
        'ONE_LOT_QUANTITY':ONE_LOT_QUANTITY,
        'TARGET_PROFIT':TARGET_PROFIT,
        'MAX_LOSS':MAX_LOSS,
        'MAX_LOSS_PER_LEG':MAX_LOSS_PER_LEG,
        'SAFETY_STOP_LOSS_PERCENTAGE':SAFETY_STOP_LOSS_PERCENTAGE,
        'BUY_BACK_PERCENTAGE':BUY_BACK_PERCENTAGE,
        'SELL_TARGET_PERCENTAGE':SELL_TARGET_PERCENTAGE,
        'BUY_BACK_LOSS_PERCENTAGE':BUY_BACK_LOSS_PERCENTAGE,
        'AVAILABLE_MARGIN':AVAILABLE_MARGIN,
        'ENTRY_TIME':ENTRY_TIME,
        'EXIT_TIME':EXIT_TIME,
        'stop_event':stop_event,

        # Dynamic configuration
        'BUY_BACK_LOTS':BUY_BACK_LOTS,
        }

        my_strategy = NewStrategy(new_data)
        my_strategy.run_strategy()
        #run_strategy(stop_event, api_websocket)
        api.close_websocket()
        return True
    except TypeError as e:
        trace_execution(f"Type error occurred: {e}")
        exit_strategy(api_websocket, stop_event)
        raise ValueError('Error on exit')
    except ZeroDivisionError as e:
        trace_execution(f"Math error occurred: {e}")
        exit_strategy(api_websocket, stop_event)
        raise ValueError('Error on exit')
    except ValueError as e:
        trace_execution(f"Value error occurred: {e}")
        exit_strategy(api_websocket, stop_event)
        raise ValueError('Error on exit')
    except Exception as e:
        trace_execution(f"An unexpected error occurred: {e}")
        exit_strategy(api_websocket, stop_event)
        raise ValueError('Error on exit')