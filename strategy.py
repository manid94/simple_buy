import threading
import time
import os, sys
from urllib.parse import parse_qs, urlparse
import hashlib
import pandas as pd
from utils import ist, round_to_nearest_0_05, place_limit_order, place_market_order, place_market_exit, is_order_complete
from brokerapi import getshoonyatradeapi
from datetime import date, datetime
from logger import LocalJsonLogger
import pytz

# Common to all strategies
ORDER_STATUS = {}
# flag to tell us if the websocket is open
socket_opened = False
SYMBOLDICT = {}

# Constants Configs
SYMBOL = 'Nifty bank'
BUY_BACK_STATIC = False
INITIAL_LOTS = 1  # Start with 1 lot
STRIKE_DIFFERENCE = 400
ONE_LOT_QUANTITY = 15  # Number of units per lot in Bank Nifty
TARGET_PROFIT = 500
MAX_LOSS = 1000
MAX_LOSS_PER_LEG = 1200
SAFETY_STOP_LOSS_PERCENTAGE = 0.83
BUY_BACK_PERCENTAGE = 0.82
SELL_TARGET_PERCENTAGE = 0.02
BUY_BACK_LOSS_PERCENTAGE = 0.93
AVAILABLE_MARGIN = 25000
ENTRY_TIME = {
    'hours': 11,
    'minutes': 2,
    'seconds': 0
}
EXIT_TIME = {
    'hours': 14,
    'minutes': 50,
    'seconds': 0

}

# DYNAMIC CONFIG
BUY_BACK_LOTS = 6





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

logger = LocalJsonLogger()

def logger_entry(tsymbol, orderno, direction, order_type, qty, ordered_price, order_method, fillqty, avg_price, status):
    # Using a dictionary for clear and structured data logging
    datas = {
        "symbol": tsymbol,
        "order_number": orderno,
        "direction": direction,
        "order_type": order_type,
        "quantity": qty,
        "ordered_price": ordered_price,
        "order_method": order_method,
        "filled_quantity": fillqty,
        "average_price": avg_price,
        "status": status
    }
    
    # Generate log entry and append to log
    new_entry = logger.generate_log_entry(datas)
    logger.append_log(new_entry)
    
    return True






#application callbacks
def event_handler_order_update(message):
    global ORDER_STATUS
    # print('print("order event: " + str(message))')
    # order event: {
    #       't': 'om', 'norenordno': '24101600226847', 'uid': 'FT053455', 'actid': 'FT053455', 'exch': 'NFO', 'tsym': 'BANKNIFTY16OCT24P50500',
    #        'trantype': 'B', 'qty': '30', 'prc': '5.25', 'pcode': 'I', 'remarks': 'my_order_002', 'rejreason': ' ', 'status': 'COMPLETE',
    #        'reporttype': 'Fill', 'flqty': '30', 'flprc': '2.85', 'flid': '380225664', 'fltm': '16-10-2024 11:15:20', 'prctyp': 'LMT',
    #         'ret': 'DAY', 'exchordid': '1500000079566637', 'fillshares': '30', 'dscqty': '0', 'avgprc': '2.85', 'exch_tm': '16-10-2024 11:15:20'
    # }
    # print("order event: " + str(message))
    
    if 'norenordno' in message:
        ORDER_STATUS[message['norenordno']] = {}
        ORDER_STATUS[message['norenordno']]['status'] = message['status']
        ORDER_STATUS[message['norenordno']]['flqty'] =  message.get('flqty', 0)
        ORDER_STATUS[message['norenordno']]['qty'] =  message.get('qty', 0)
        ORDER_STATUS[message['norenordno']]['tsym'] =  message.get('tsym', 0)
        ORDER_STATUS[message['norenordno']]['trantype'] =  message.get('trantype', 'S')
        ORDER_STATUS[message['norenordno']]['option_type'] =  message.get('remarks', 'exit')

        # print('norenordno')
        # print(message['status'].lower())
        if message['status'].lower() == 'complete':
            ORDER_STATUS[message['norenordno']]['avgprc'] =  message.get('avgprc', 0)
        logger_entry(message.get('tsym', 0),message['norenordno'],message.get('remarks', 'exit'),message.get('trantype', 'S'),message.get('qty', 0),message.get('prc', 0), 'LMT',  message.get('flqty', 0),message.get('avgprc', 0),  'placed')
            

    


def event_handler_quote_update(message):
    global SYMBOLDICT
    #e   Exchange
    #tk  Token
    #lp  LTP
    #pc  Percentage change
    #v   volume
    #o   Open price
    #h   High price
    #l   Low price
    #c   Close price
    #ap  Average trade price

    # print("quote event: {0}".format(time.strftime('%d-%m-%Y %H:%M:%S')) + str(message))

    key = message['tk']
    if key in SYMBOLDICT:
        symbol_info =  SYMBOLDICT[key]
        symbol_info.update(message)
        SYMBOLDICT[key] = symbol_info
    else:
        SYMBOLDICT[key] = message

    # print(SYMBOLDICT[key])

def open_callback():
    global socket_opened
    socket_opened = True
    #print('app is connected')

    #api.subscribe(['NSE|22', 'BSE|522032'])

#end of callbacks

def fetch_last_trade_price(option_type):
        # print('Deepak')
        # print(SYMBOLDICT)
        
        # Check if the option_type exists in LEG_TOKEN
        if option_type not in LEG_TOKEN:
            raise ValueError(f"Invalid option_type: {option_type}")
        
        # Get the token for the given option_type
        leg_token = LEG_TOKEN[option_type]
        
        # Check if the leg_token exists in SYMBOLDICT
        if leg_token not in SYMBOLDICT:
            raise KeyError(f"Token {leg_token} not found in SYMBOLDICT")
        
        # Fetch the last trade price
        temp_data = SYMBOLDICT[leg_token].get('lp', None)
        
        # Validate if the last trade price (temp_data) exists and is not None
        if temp_data is None:
            raise ValueError(f"No last trade price available for {option_type} (token: {leg_token})")
        
        # Return the last trade price as a float
        return float(temp_data)





def open_socket():
    if socket_opened != True:
        print(socket_opened)
        api.start_websocket(order_update_callback=event_handler_order_update, subscribe_callback=event_handler_quote_update, socket_open_callback=open_callback)
    #api.start_websocket(order_update_callback=event_handler_order_update, subscribe_callback=event_handler_quote_update, socket_open_callback=open_callback)
    print(socket_opened)
    return True





# Utility function to fetch the ATM strike price
def fetch_atm_strike():
    global LEG_TOKEN

    socket = threading.Thread(target=open_socket, args=())
    socket.start()

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


    socket.join()
    api.subscribe([subscribeDataPE,subscribeDataCE])
    return atm_strike  # Round to nearest 100


# Calculate PNL based on current leg status
def calculate_leg_pnl(option_type, type, lots):
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
            sold_price_or_ltp_price = fetch_last_trade_price(option_type)
    else:
        print(f"Error: {node_sell} not found in PRICE_DATAS.")
    
    if node_buy in PRICE_DATAS:
        # Use the stored price or fetch the last traded price if it's zero
        bought_price_or_ltp_price = PRICE_DATAS[node_buy]
        if bought_price_or_ltp_price == 0:
            bought_price_or_ltp_price = fetch_last_trade_price(option_type)
    else:
        print(f"Error: {node_buy} not found in PRICE_DATAS.")
    
    # Calculate the PNL difference
    difference = float(sold_price_or_ltp_price) - float(bought_price_or_ltp_price)
    
    # Print the calculated values for debugging
    # print(f"Sold Price: {sold_price_or_ltp_price}")
    # print(f"Bought Price: {bought_price_or_ltp_price}")
    # print(f"PNL Difference: {difference}")
    
    # Calculate the PNL considering the number of lots
    pnl = difference * lots * ONE_LOT_QUANTITY
    return pnl


    
# Function to calculate total PNL
def calculate_total_pnl():
    ce_entry_pnl = calculate_leg_pnl('CE', 'INITIAL', INITIAL_LOTS)
    pe_entry_pnl = calculate_leg_pnl('PE', 'INITIAL', INITIAL_LOTS)
    ce_pnl = calculate_leg_pnl('CE', 'BUY_BACK', BUY_BACK_LOTS)
    pe_pnl = calculate_leg_pnl('PE', 'BUY_BACK', BUY_BACK_LOTS)
    ce_re_entry_pnl = calculate_leg_pnl('CE', 'RE_ENTRY', INITIAL_LOTS)
    pe_re_entry_pnl = calculate_leg_pnl('CE', 'RE_ENTRY', INITIAL_LOTS)
    return ce_pnl + pe_pnl + ce_entry_pnl + pe_entry_pnl + ce_re_entry_pnl + pe_re_entry_pnl  

def check_unsold_lots(id):
    fill = float(ORDER_STATUS[id]['flqty'])
    qty = float(ORDER_STATUS[id]['qty'])
    return float(qty)-float(fill)



# Monitor individual leg logic (CE/PE)
def monitor_leg(option_type, sell_price, strike_price, stop_event):
    global strategy_running, ORDER_STATUS, PRICE_DATA, exited_strategy
    leg_entry = False
    buy_back_lots = BUY_BACK_LOTS * ONE_LOT_QUANTITY
    print('monitor '+option_type)
    while strategy_running and not leg_entry:
        # print('while check monitor')
        ltp = fetch_last_trade_price(option_type)  # Fetch LTP for the option leg
        if exited_strategy or stop_event.is_set():
            break
        if ltp <= (float(sell_price) * float(SAFETY_STOP_LOSS_PERCENTAGE)):
            leg_entry = True

            print(f"{option_type} reached 76% of sell price, exiting...")
            # safety_sell_order_id = place_market_order(api, LEG_TOKEN, option_type, 'B', lots, 'end')

            # while not wait_for_orders_to_complete(safety_sell_order_id, 100):
            #     time.sleep(0.5)

            PRICE_DATA[option_type+'_PRICE_DATA']['INITIAL_BUY_'+option_type] = sell_price

            # CURRENT_STRATEGY_ORDERS.append(safety_sell_order_id)
            # important need to check for order execution if not succeded then retry with modify 
            buy_back_price = round_to_nearest_0_05(float(sell_price) * float(BUY_BACK_PERCENTAGE))
            buy_back_order_id = place_limit_order(api, LEG_TOKEN, option_type, 'B', buy_back_lots, limit_price=buy_back_price, leg_type='start')
            logger_entry(ORDER_STATUS[buy_back_order_id]['tsym'],buy_back_order_id,option_type,'B',buy_back_lots,buy_back_price, 'LMT', 0, 0, 'placed')
            CURRENT_STRATEGY_ORDERS.append(buy_back_order_id)

            while not is_order_complete(buy_back_order_id, ORDER_STATUS):
                time.sleep(0.25)
            buy_back_avg_price = ORDER_STATUS[buy_back_order_id]['avgprc']
            PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_BUY_'+option_type] = buy_back_avg_price
            sell_target_price = round_to_nearest_0_05(float(buy_back_avg_price) * float(1 + SELL_TARGET_PERCENTAGE))
            sell_target_order_id = place_limit_order(api, LEG_TOKEN, option_type, 'S', buy_back_lots, limit_price=sell_target_price, leg_type='end')
            logger_entry(ORDER_STATUS[sell_target_order_id]['tsym'],sell_target_order_id,option_type,'S',buy_back_lots,sell_target_price, 'LMT',   0,0,  'placed')
            print(f'OUTSIDE sell_target_order_id {sell_target_order_id}')
            CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)

            while not is_order_complete(sell_target_order_id, ORDER_STATUS): #static instead check weather ltp > selltarget_price
                if exited_strategy or stop_event.is_set():
                    break
                ltp = fetch_last_trade_price(option_type)  # Fetch LTP for the option leg
                legpnl = calculate_leg_pnl(option_type, 'BUY_BACK', BUY_BACK_LOTS)
                if legpnl <= -MAX_LOSS_PER_LEG or ltp <=  (float(ORDER_STATUS[buy_back_order_id]['avgprc']) * BUY_BACK_LOSS_PERCENTAGE):
                    print(f"{option_type} reached 10% loss, exiting remaining orders.")
                    unsold_lots = check_unsold_lots(sell_target_order_id)
                    api.cancel_order(sell_target_order_id)
                    sell_target_order_id = place_market_order(api, LEG_TOKEN, option_type, 'S', unsold_lots, 'end')
                    print(f'INSIDE sell_order_id :{sell_target_order_id}')
                    print(f'ORDER_STATUS[sell_target_order_id]: {ORDER_STATUS[sell_target_order_id]}')
                    break
                time.sleep(1)

 
            if exited_strategy or stop_event.is_set():
                    break
            if wait_for_orders_to_complete(sell_target_order_id, 40):
                CURRENT_STRATEGY_ORDERS.append(sell_target_order_id)
                PRICE_DATA[option_type+'_PRICE_DATA']['BUY_BACK_SELL_'+option_type] = ORDER_STATUS[sell_target_order_id]['avgprc']
                # re_sell_order_id = place_market_order(api, LEG_TOKEN, option_type, 'S', lots, 'start')
                # wait_for_orders_to_complete(re_sell_order_id, 100)
                # CURRENT_STRATEGY_ORDERS.append(re_sell_order_id)
                # PRICE_DATA[option_type+'_PRICE_DATA']['RE_ENTRY_SELL_'+option_type] = ORDER_STATUS[re_sell_order_id]['avgprc']

    return True



# Function to monitor the strategy
def monitor_strategy(stop_event):
    global strategy_running, exited_strategy
    print('monitor_strategy ')
    while strategy_running:
        if exited_strategy or stop_event.is_set():
            break
        pnl = calculate_total_pnl()  # Fetch the PNL
        if pnl >= TARGET_PROFIT and not exited_strategy:
            print(f"Target profit of ₹{TARGET_PROFIT} reached. Exiting strategy.")
            # strategy_running = False
            exit_strategy()
        elif pnl <= -MAX_LOSS and not exited_strategy:
            print(f"Max loss of ₹{MAX_LOSS} reached. Exiting strategy.")
            # strategy_running = False
            exit_strategy()
            print('checking pnl')
        time.sleep(5)  # Check PNL every 5 seconds


# Retry logic with a maximum number of attempts to avoid an infinite loop
def wait_for_orders_to_complete(order_ids, max_retries=100):
    global ORDER_STATUS
    attempts = 0

    # Ensure order_ids is always treated as a list
    if isinstance(order_ids, str):
        order_ids = [order_ids]

    # Loop until all orders are complete or max_retries is reached
    while not all(is_order_complete(order_id, ORDER_STATUS) for order_id in order_ids):
        # Sleep for 0.25 seconds
        time.sleep(0.25)
        attempts += 1

        # Check if maximum retries reached
        if attempts >= max_retries:
            print(f"Max retries reached. Orders may not be complete: {', '.join(order_ids)}")
            raise ValueError(f"Max retries reached. Orders may not be complete: {', '.join(order_ids)}")

    # If all orders are complete
    print("All orders are complete.")
    return True

# Function to exit the strategy
def exit_strategy():
    global strategy_running, exited_strategy 
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
            wait_for_orders_to_complete(order_id, 100)

    return True



    
    # Implement logic to close all open orders and exit strategy
    print("Strategy exited.")

def run_strategy(stop_event):
    global strategy_running, sell_price_ce, sell_price_pe, ORDER_STATUS, PRICE_DATA, BUY_BACK_LOTS
    start_time = ist_datatime.replace(hour=ENTRY_TIME['hours'], minute=ENTRY_TIME['minutes'], second=ENTRY_TIME['seconds'], microsecond=0).time()
    end_time = ist_datatime.replace(hour=EXIT_TIME['hours'], minute=EXIT_TIME['minutes'], second=EXIT_TIME['seconds'], microsecond=0).time()
    lots = INITIAL_LOTS * ONE_LOT_QUANTITY

    atm_strike = fetch_atm_strike()
    while not strategy_running:
        current_time = datetime.now(ist).time()
        if current_time >= end_time:
            break
        if start_time <= current_time <= end_time:
            if not strategy_running:
                atm_strike = fetch_atm_strike()
                print('passed atm strike')
                sell_price_ce = fetch_last_trade_price('CE')
                sell_price_pe = fetch_last_trade_price('PE')
                print(f'sell_price_ce{sell_price_ce}:sell_price_pe:{sell_price_pe}')

                if(not BUY_BACK_STATIC):
                    ce_lot = int(AVAILABLE_MARGIN/(ONE_LOT_QUANTITY * sell_price_ce))
                    pe_lot = int(AVAILABLE_MARGIN/(ONE_LOT_QUANTITY * sell_price_ce))
                    BUY_BACK_LOTS = min(ce_lot, pe_lot)
                
                logger_entry('CE','orderno','direction','CE',ONE_LOT_QUANTITY,sell_price_ce,'GET MKT',0,0,'start')
                logger_entry('PE','orderno','direction','PE',ONE_LOT_QUANTITY,sell_price_pe,'GET MKT',0,0,'start')
                
                PRICE_DATA['CE_PRICE_DATA']['INITIAL_SELL_CE'] = sell_price_ce
                PRICE_DATA['PE_PRICE_DATA']['INITIAL_SELL_PE'] = sell_price_pe

                strategy_running = True
                
                ce_thread = threading.Thread(target=monitor_leg, args=('CE', sell_price_ce, atm_strike + STRIKE_DIFFERENCE,stop_event))
                pe_thread = threading.Thread(target=monitor_leg, args=('PE', sell_price_pe, atm_strike - STRIKE_DIFFERENCE,stop_event))



                ce_thread.start()
                pe_thread.start()

                strategy_thread = threading.Thread(target=monitor_strategy, args=(stop_event,)) # static uncomment
                strategy_thread.start() # static uncomment

                ce_thread.join()
                pe_thread.join()
                # dynamic_data.join()
                strategy_thread.join() # static uncomment

        else:
            print("Outside trading hours, strategy paused.")
            time.sleep(1)
            
        
    return True


def start_the_strategy(even):
        global api
        """Cancel order logic."""
        try:
            api = getshoonyatradeapi()
            print(' data')
            run_strategy(even)
            return True
        except TypeError as e:
            print(f"Type error: {e}")
            return None
        except ZeroDivisionError as e:
            print(f"Math error: {e}")
            return None
        except ValueError as e:
            print(f"Value error: {e}")
            return None
        except Exception as e:
            # Catch all other exceptions
            print(f"An unexpected error occurred: {e}")
            return None


