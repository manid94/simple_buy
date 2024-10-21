import time
import os, sys
from urllib.parse import parse_qs, urlparse
import hashlib
import logging
from utils import ist, round_to_nearest_0_05, place_limit_order, place_market_order, place_market_exit, is_order_complete, wait_for_orders_to_complete, check_unsold_lots
from brokerapi import getshoonyatradeapi
from datetime import date, datetime
from logger import LocalJsonLogger, ThrottlingLogger, logger_entry
from api_websocket import OpenWebSocket
from custom_threading import MyThread





logging.basicConfig(filename='strategy.log', level=logging.ERROR)
# flag to tell us if the api_websocket is open


# Constants Configs
SYMBOL = 'Nifty bank'
BUY_BACK_STATIC = True
INITIAL_LOTS = 1  # Start with 1 lot
STRIKE_DIFFERENCE = 900
ONE_LOT_QUANTITY = 15  # Number of units per lot in Bank Nifty
TARGET_PROFIT = 500
MAX_LOSS = 1000
MAX_LOSS_PER_LEG = 1200
SAFETY_STOP_LOSS_PERCENTAGE = 0.98
BUY_BACK_PERCENTAGE = 0.975
SELL_TARGET_PERCENTAGE = 0.01
BUY_BACK_LOSS_PERCENTAGE = 0.93
AVAILABLE_MARGIN = 2000
ENTRY_TIME = {
    'hours': 9,
    'minutes': 36,
    'seconds': 0
}
EXIT_TIME = {
    'hours': 19,
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




# Global variables
strategy_running = False
exited_strategy = False
sell_price_ce = 0
sell_price_pe = 0
ist_datatime = datetime.now(ist)

#api = getflattradeapi()
api = {}

logger = {}









# Utility function to fetch the ATM strike price
def fetch_atm_strike():
    global LEG_TOKEN

    banknifty_price = api.get_quotes(exchange='NSE', token='26009')
    current_price = banknifty_price['lp']
    print(float(current_price))
    atm_strike = round(float(current_price) / 100) * 100
    print(atm_strike)

    nearest_symbol_ce = (str(atm_strike+STRIKE_DIFFERENCE)+' nifty bANK' + ' ce')
    nearest_symbol_pe = (str(atm_strike-STRIKE_DIFFERENCE)+' nifty bANK' + ' pe')

    # print(nearest_symbol_ce)
    # print(api.searchscrip(exchange='NFO', searchtext=nearest_symbol_ce))
    # print(api.searchscrip(exchange='NFO', searchtext=nearest_symbol_pe))
    option_chains_ce = api.searchscrip(exchange='NFO', searchtext=nearest_symbol_ce)
    option_chains_pe = api.searchscrip(exchange='NFO', searchtext=nearest_symbol_pe)
    pe_option = option_chains_pe['values'][0]
    ce_option = option_chains_ce['values'][0]
    subscribeDataPE = 'NFO|'+pe_option['token']
    subscribeDataCE = 'NFO|'+ce_option['token']
    LEG_TOKEN['PE'] = pe_option['token']
    LEG_TOKEN['CE'] = ce_option['token']
    LEG_TOKEN['PE_tsym'] = pe_option['tsym']
    LEG_TOKEN['CE_tsym'] = ce_option['tsym']
    api.subscribe([subscribeDataPE,subscribeDataCE])
    return atm_strike  # Round to nearest 100


# Calculate PNL based on current leg status
def calculate_leg_pnl(option_type, type, lots, api_websocket):
    global PRICE_DATA
    
    # Check if PRICE_DATA and the required subkey exist
    price_data_key = option_type + '_PRICE_DATA'
    if price_data_key not in PRICE_DATA:
        print(f"Error: {price_data_key} not found in PRICE_DATA.")
        return None
    
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
    if node_sell in PRICE_DATAS:
        # Use the stored price or fetch the last traded price if it's zero
        sold_price_or_ltp_price = int(PRICE_DATAS[node_sell])
        if sold_price_or_ltp_price == 0:
            sold_price_or_ltp_price = api_websocket.fetch_last_trade_price(option_type, LEG_TOKEN)
    else:
        print(f"Error: {node_sell} not found in PRICE_DATAS.")
    
    if node_buy in PRICE_DATAS:
        bought_price_or_ltp_price = PRICE_DATAS[node_buy]
        if bought_price_or_ltp_price == 0:
            bought_price_or_ltp_price = api_websocket.fetch_last_trade_price(option_type, LEG_TOKEN)
    else:
        print(f"Error: {node_buy} not found in PRICE_DATAS.")
    
    difference = float(sold_price_or_ltp_price) - float(bought_price_or_ltp_price)
    
    pnl = difference * lots * ONE_LOT_QUANTITY
    return pnl


    
# Function to calculate total PNL
def calculate_total_pnl(api_websocket):
    ce_entry_pnl = calculate_leg_pnl('CE', 'INITIAL', INITIAL_LOTS, api_websocket)
    pe_entry_pnl = calculate_leg_pnl('PE', 'INITIAL', INITIAL_LOTS, api_websocket)
    ce_pnl = calculate_leg_pnl('CE', 'BUY_BACK', BUY_BACK_LOTS, api_websocket)
    pe_pnl = calculate_leg_pnl('PE', 'BUY_BACK', BUY_BACK_LOTS, api_websocket)
    ce_re_entry_pnl = calculate_leg_pnl('CE', 'RE_ENTRY', INITIAL_LOTS, api_websocket)
    pe_re_entry_pnl = calculate_leg_pnl('PE', 'RE_ENTRY', INITIAL_LOTS, api_websocket)  # Corrected to 'PE'
    
    return ce_pnl + pe_pnl + ce_entry_pnl + pe_entry_pnl + ce_re_entry_pnl + pe_re_entry_pnl


def check_for_stop_loss(option_type, stop_event, selldetails, buydetails, api_websocket):
    global PRICE_DATA
    ORDER_STATUS = api_websocket.get_latest_data()
    sell_target_order_id = selldetails['sell_target_order_id']
    buy_back_order_id = buydetails['buy_back_order_id']
    log_sell = ThrottlingLogger(sell_target_order_id, logger_entry)
    while not is_order_complete(sell_target_order_id, ORDER_STATUS, log_sell): #static instead check weather ltp > selltarget_price
        if exited_strategy or stop_event.is_set():
            break
        ltp = api_websocket.fetch_last_trade_price(option_type, LEG_TOKEN)  # Fetch LTP for the option leg
        legpnl = calculate_leg_pnl(option_type, 'BUY_BACK', BUY_BACK_LOTS, api_websocket)
        if legpnl <= -MAX_LOSS_PER_LEG or ltp <=  (float(ORDER_STATUS[buy_back_order_id]['avgprc']) * BUY_BACK_LOSS_PERCENTAGE):
            print(f"{option_type} reached 10% loss, exiting remaining orders.")
            unsold_lots = check_unsold_lots(sell_target_order_id, api_websocket)
            api.cancel_order(sell_target_order_id)
            sell_target_order_id = place_market_order(api, LEG_TOKEN, option_type, 'S', unsold_lots, 'end')
            print(f'INSIDE sell_order_id :{sell_target_order_id}')
            print(f'ORDER_STATUS[sell_target_order_id]: {ORDER_STATUS[sell_target_order_id]}')
            break
        time.sleep(1)
    return sell_target_order_id
    

def sell_at_limit_price(option_type,api_websocket, buydetails):
    global PRICE_DATA
    ORDER_STATUS = api_websocket.get_latest_data()
    buy_back_lots = BUY_BACK_LOTS * ONE_LOT_QUANTITY
    print(f"{option_type} sell_at_limit_price...0")
    buy_back_avg_price = buydetails['buy_back_avg_price']
    sell_target_price = round_to_nearest_0_05(float(buy_back_avg_price) * float(1 + SELL_TARGET_PERCENTAGE))
    print(f"{option_type} ThrottlingLogger... 2")
    print(f"{option_type} ThrottlingLogger... 2.1")
    sell_target_order_id = place_limit_order(api, LEG_TOKEN, option_type, 'S', buy_back_lots, limit_price=sell_target_price, leg_type='end')
    print(f"{option_type} ThrottlingLogger... 2.2 {sell_target_order_id}")
    logger_entry(ORDER_STATUS[sell_target_order_id]['tsym'],sell_target_order_id,'S',option_type,buy_back_lots,sell_target_price, 'LMT', 0, 0, 'placed')
    print(f'OUTSIDE sell_target_order_id {sell_target_order_id}')
    CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
    print(f"{option_type} ThrottlingLogger... 3")

        
    return {
        'sell_target_order_id': sell_target_order_id,
        'sell_target_price': sell_target_price
    }
    
    
    
    
def buy_at_limit_price(option_type, sell_price, api_websocket):
    global PRICE_DATA, logger_entry
    print(f"{option_type} buy_at_limit_price...0")
    buy_back_lots = BUY_BACK_LOTS * ONE_LOT_QUANTITY
    ORDER_STATUS = api_websocket.get_latest_data()
    buy_back_price = round_to_nearest_0_05(float(sell_price) * float(BUY_BACK_PERCENTAGE))
    print(f"{option_type} reached round_to_nearest_0_05...")
    buy_back_order_id = place_limit_order(api, LEG_TOKEN, option_type, 'B', buy_back_lots, limit_price=buy_back_price, leg_type='start')

    logger_entry(ORDER_STATUS[buy_back_order_id]['tsym'],buy_back_order_id,'B',option_type,buy_back_lots,buy_back_price, 'LMT', 0, 0, 'placed')
    CURRENT_STRATEGY_ORDERS.append(buy_back_order_id)
    print(f"{option_type} ThrottlingLogger...0")
    log_buy = ThrottlingLogger(buy_back_order_id, logger_entry)
    while not is_order_complete(buy_back_order_id, ORDER_STATUS, log_buy):
        time.sleep(0.25)
    print(f"{option_type} ThrottlingLogger... 1")
    buy_back_avg_price = ORDER_STATUS[buy_back_order_id]['avgprc']
    PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_BUY_'+option_type] = buy_back_avg_price
    return {
        'buy_back_avg_price' : buy_back_avg_price,
        'buy_back_order_id' : buy_back_order_id
    }


# Monitor individual leg logic (CE/PE)
def monitor_leg(option_type, sell_price, strike_price, stop_event, api_websocket):
    try:
        global strategy_running, PRICE_DATA, exited_strategy, logger_entry
        ORDER_STATUS = api_websocket.get_latest_data()
        PRICE_DATA[option_type+'_PRICE_DATA']['INITIAL_BUY_'+option_type] = sell_price
        leg_entry = False
        print('monitor '+option_type)
        while strategy_running and not leg_entry:
            # print('while check monitor')
            ltp = api_websocket.fetch_last_trade_price(option_type, LEG_TOKEN)  # Fetch LTP for the option leg
            if exited_strategy or stop_event.is_set():
                break
            if ltp <= (float(sell_price) * float(SAFETY_STOP_LOSS_PERCENTAGE)):
                leg_entry = True

                print(f"{option_type} reached 76% of sell price, exiting...")
                buydetails = buy_at_limit_price(option_type, sell_price, api_websocket)
                selldetails = sell_at_limit_price(option_type, api_websocket, buydetails)
                print(f"{option_type} ThrottlingLogger... 4 {selldetails}")
                if exited_strategy or stop_event.is_set():
                    break
                print(f"{option_type} ThrottlingLogger... 5")
                
                sell_target_order_id = check_for_stop_loss(option_type, stop_event, selldetails, buydetails, api_websocket)
                
                if wait_for_orders_to_complete(sell_target_order_id, api_websocket, 40, 0.25):
                    CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
                    PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_SELL_'+option_type] = float(ORDER_STATUS[sell_target_order_id]['avgprc'])
                    print(f"{option_type} ThrottlingLogger... 6 {sell_target_order_id}, {ORDER_STATUS}")
                print('end_monitor '+option_type)
                break
        return True
    except TypeError as e:
        print(f"Type error monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None
    except ZeroDivisionError as e:
        print(f"Math error monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None
    except ValueError as e:
        print(f"Value error monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None
    except Exception as e:
        # Catch all other exceptions
        print(f"An unexpected error occurred monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None
    



# Function to monitor the strategy
def monitor_strategy(stop_event, api_websocket):
    try:
        global strategy_running, exited_strategy
        print('monitor_strategy ')
        end_time = ist_datatime.replace(hour=EXIT_TIME['hours'], minute=EXIT_TIME['minutes'], second=EXIT_TIME['seconds'], microsecond=0).time()
        while strategy_running:
            if exited_strategy or stop_event.is_set():
                break
            
            current_time = datetime.now(ist).time()
            if current_time >= end_time:
                exit_strategy(api_websocket)
            pnl = calculate_total_pnl(api_websocket)  # Fetch the PNL
            if pnl >= TARGET_PROFIT and not exited_strategy:
                print(f"Target profit of ₹{TARGET_PROFIT} reached. Exiting strategy.")
                # strategy_running = False
                exit_strategy(api_websocket)
                break
            elif pnl <= -MAX_LOSS and not exited_strategy:
                print(f"Max loss of ₹{MAX_LOSS} reached. Exiting strategy.")
                # strategy_running = False
                exit_strategy(api_websocket)
                print('checking pnl')
                break
            time.sleep(5)  # Check PNL every 5 seconds
        return True
    except TypeError as e:
        print(f"Type error monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None
    except ZeroDivisionError as e:
        print(f"Math error monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None
    except ValueError as e:
        print(f"Value error monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None
    except Exception as e:
        # Catch all other exceptions
        print(f"An unexpected error occurred monitor_leg: {e}")
        exit_strategy(api_websocket)
        return None




# Function to exit the strategy
def exit_strategy(api_websocket):
    try:
        global strategy_running, exited_strategy
        ORDER_STATUS = api_websocket.get_latest_data() 
        strategy_running = True  # Stop the strategy
        exited_strategy = True
        print('Exiting strategy...')
        print('Current ORDER_STATUS:', ORDER_STATUS)

        # Initialize totals and symbol tracking for CE and PE
        totals = {'CE': 0, 'PE': 0}
        symbols = {'CE': '', 'PE': ''}

            # Filter unique values using set
        unique_orders = set(CURRENT_STRATEGY_ORDERS)

        # Cancel incomplete orders and calculate totals for completed orders
        for key in unique_orders:
            order = ORDER_STATUS.get(key)
            if not order:
                print(f"Order {key} not found in ORDER_STATUS, skipping...")
                continue

            status = order.get('status', '').lower()

            if status not in ['open', 'pending', 'complete']:
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

            if status in ['open', 'pending']:
                print(f"Canceling incomplete order: {key}")
                api.cancel_order(key)
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

        print(f"Totals: {totals}, Symbols: {symbols}")
        # Place market exit orders for remaining positions
        for option_type, total in totals.items():
            if total != 0:
                buy_or_sell = 'S' if total > 0 else 'B'
                tsym = symbols[option_type]
                print(f"Placing market exit for {option_type}: {buy_or_sell} {abs(total)} lots")
                order_id = place_market_exit(api, tsym, buy_or_sell, abs(total))
                wait_for_orders_to_complete(order_id, api_websocket, 100)
        # Implement logic to close all open orders and exit strategy
        print("Strategy exited.")

        return True
    except Exception as e:
        # Catch all other exceptions
        print(f"An unexpected error occurred exit_strategy: {e}")
        return None



        


def run_strategy(stop_event, api_websocket):
    global strategy_running, sell_price_ce, sell_price_pe, PRICE_DATA, BUY_BACK_LOTS, logger
    logger = LocalJsonLogger()
    start_time = ist_datatime.replace(hour=ENTRY_TIME['hours'], minute=ENTRY_TIME['minutes'], second=ENTRY_TIME['seconds'], microsecond=0).time()
    end_time = ist_datatime.replace(hour=EXIT_TIME['hours'], minute=EXIT_TIME['minutes'], second=EXIT_TIME['seconds'], microsecond=0).time()
    lots = INITIAL_LOTS * ONE_LOT_QUANTITY
    print('entered run_strategy')
    atm_strike = fetch_atm_strike()
    while not strategy_running:
        current_time = datetime.now(ist).time()
        if current_time >= end_time:
            exit_strategy()
            break
        if start_time <= current_time <= end_time:
            if not strategy_running:
                atm_strike = fetch_atm_strike()
                print('passed atm strike')
                sell_price_ce = api_websocket.fetch_last_trade_price('CE', LEG_TOKEN)
                sell_price_pe = api_websocket.fetch_last_trade_price('PE', LEG_TOKEN)
                print(f'sell_price_ce{sell_price_ce}:sell_price_pe:{sell_price_pe}')
                print('passed atm strike 1')
                if(not BUY_BACK_STATIC):
                    ce_lot = int(AVAILABLE_MARGIN/(ONE_LOT_QUANTITY * sell_price_ce))
                    pe_lot = int(AVAILABLE_MARGIN/(ONE_LOT_QUANTITY * sell_price_ce))
                    BUY_BACK_LOTS = min(ce_lot, pe_lot)
                
                logger_entry('CE','orderno','direction','CE',ONE_LOT_QUANTITY,sell_price_ce,'GET MKT',0,0,'start')
                logger_entry('PE','orderno','direction','PE',ONE_LOT_QUANTITY,sell_price_pe,'GET MKT',0,0,'start')
                
                PRICE_DATA['CE_PRICE_DATA']['INITIAL_SELL_CE'] = 0
                PRICE_DATA['PE_PRICE_DATA']['INITIAL_SELL_PE'] = 0

                strategy_running = True

                ce_thread = MyThread(target=monitor_leg, args=('CE', sell_price_ce, atm_strike + STRIKE_DIFFERENCE,stop_event, api_websocket))
                pe_thread = MyThread(target=monitor_leg, args=('PE', sell_price_pe, atm_strike - STRIKE_DIFFERENCE,stop_event, api_websocket))
                strategy_thread = MyThread(target=monitor_strategy, args=(stop_event, api_websocket)) # static uncomment




                try:
                    ce_thread.start()
                    pe_thread.start()              
                    strategy_thread.start() # static uncomment
                    ce_thread.join()
                    pe_thread.join()
                    # dynamic_data.join()
                    strategy_thread.join() # static uncomment
                    break
                except TypeError as e:
                    print(f"Type error customR: {e}")
                    return None
                except ZeroDivisionError as e:
                    print(f"Math error customSR: {e}")
                    return None
                except ValueError as e:
                    print(f"Value error customVR: {e}")
                    return None
                except Exception as e:
                    # Catch all other exceptions
                    print(f"An unexpected error occurred: {e}")
                    return None



        else:
            print("Outside trading hours, strategy paused.")
            time.sleep(1)
            
        
    return True

def start_the_strategy(stop_event):
    global api
    try:
        api = getshoonyatradeapi()
        api_websocket = OpenWebSocket(api)
        logging.info('Starting WebSocket data connection...')
        
        while not api_websocket.socket_opened:
            time.sleep(0.1)
        
        run_strategy(stop_event, api_websocket)
        return True
    except TypeError as e:
        logging.error(f"Type error occurred: {e}")
        return None
    except ZeroDivisionError as e:
        logging.error(f"Math error occurred: {e}")
        return None
    except ValueError as e:
        logging.error(f"Value error occurred: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return None