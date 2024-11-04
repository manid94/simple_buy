import pytz
from datetime import datetime
import time
from logger import ThrottlingLogger


ist = pytz.timezone('Asia/Kolkata')
ist_datatime = datetime.now(ist)

def round_to_nearest_0_05(value):
    return round(float(value) * float(20)) / float(20)


# Function to place sell orders for both legs
def place_market_order(api, LEG_TOKEN, option_type, type, lots, leg_type):
    # tsym = SYMBOLDICT[LEG_TOKEN[option_type]]['ts']
    tsym = LEG_TOKEN[option_type+'_tsym']
    print('inside place_limit_order')
    order_responce = api.place_order(buy_or_sell=type, product_type='I',
                        exchange='NFO', tradingsymbol=tsym, 
                        quantity=lots, discloseqty=0,price_type='MKT', price=0, trigger_price=None,
                        retention='DAY', remarks=(option_type+' '+leg_type))
    if not ('norenordno' in  order_responce):
        raise ValueError('Error in Order placement')
    print('inside place_limit_order')
    order_id = order_responce['norenordno']
    return order_id


def place_limit_order(api, LEG_TOKEN, option_type, type, lots, limit_price, leg_type):
    # tsym = SYMBOLDICT[LEG_TOKEN[option_type]]['ts']
    print('inside place_limit_order')
    tsym = LEG_TOKEN[option_type+'_tsym']
    order_responce = api.place_order(buy_or_sell=type, product_type='I',
                        exchange='NFO', tradingsymbol=tsym, 
                        quantity=lots, discloseqty=0,price_type='LMT', price=limit_price, trigger_price=None,
                        retention='DAY', remarks=(option_type+' '+leg_type))
    print('outside place_limit_order')
    if not ('norenordno' in  order_responce):
        raise ValueError('Error in Order placement')
    order_id = order_responce['norenordno']
    print(order_responce)
    return order_id


def place_market_exit(api, tsym, type, lots):
    print('inside place_limit_order')
    order_responce = api.place_order(buy_or_sell=type, product_type='I',
                        exchange='NFO', tradingsymbol=tsym, 
                        quantity=lots, discloseqty=0,price_type='MKT', price=0, trigger_price=None,
                        retention='DAY', remarks='exit')
    print('inside place_limit_order')
    if not ('norenordno' in  order_responce):
        raise ValueError('Error in Order placement')
    order_id = order_responce['norenordno']
    return order_id


# Function to check if the order status is complete
def is_order_complete(order_id, ORDER_STATUS, log, strategy_log_class):
    # Check if the order exists in the ORDER_STATUS dictionary
    # print(f'throttle wait_for_orders_to_complete 3.1 {order_id}: {ORDER_STATUS} : {logger}')
    log.check_update_thread(strategy_log_class, ORDER_STATUS)
    if order_id in ORDER_STATUS:
        return ORDER_STATUS[order_id].get('status').lower() == 'complete'
    return False


# Function to check if the order status is complete
def is_order_cancelled(order_id, ORDER_STATUS):
    # Check if the order exists in the ORDER_STATUS dictionary
    if order_id in ORDER_STATUS:
        return ORDER_STATUS[order_id].get('status').lower() == 'cancelled'
    return False



def wait_for_orders_to_complete(order_ids, api_websocket, logger_entry, strategy_log_class, max_retries=100, sleep_interval=0.25):
    attempts = 0
    update_log = {}
    # Ensure order_ids is always treated as a list
    if isinstance(order_ids, str):
        order_ids = [order_ids]
    
    completed_orders = {order_id: False for order_id in order_ids}  # Track which orders are completed
    
    order_ids = set(order_ids)
    # Initialize logging for each order
    for order_id in order_ids:
        update_log[order_id] = ThrottlingLogger(order_id, logger_entry)

    # Retry loop until all orders are complete or max_retries is reached
    while not all(completed_orders.values()):
        ORDER_STATUS = api_websocket.get_latest_data()
        attempts += 1

        #print(f'throttle wait_for_orders_to_complete 3 {order_ids}: {completed_orders} : {update_log}')
        for order_id in order_ids:
            #print('throttle wait_for_orders_to_complete 4')
            if not completed_orders[order_id]:
                # Check the order status only if it's not already completed
                completed_orders[order_id] = is_order_complete(order_id, ORDER_STATUS, update_log[order_id], strategy_log_class)
        
        
        if all(completed_orders.values()):
            # If all orders are complete
            print("All orders are complete.")
            return True

        # Sleep before the next attempt
        time.sleep(sleep_interval)
        # Check if maximum retries reached
        if attempts >= max_retries:
            incomplete_orders = [order_id for order_id, is_complete in completed_orders.items() if not is_complete]
            print(f"Max retries reached. Orders may not be complete: {', '.join(incomplete_orders)}")
            raise ValueError(f"Max retries reached. Orders may not be complete: {', '.join(incomplete_orders)}")

        # Optionally increase the sleep interval exponentially to reduce API stress
        sleep_interval = min(sleep_interval * 1.5, 2)  # Increase the sleep interval with a cap at 2 seconds



def check_unsold_lots(id, api_websocket):
    fill = float(api_websocket.get_latest_data()[id]['flqty'])
    qty = float(api_websocket.get_latest_data()[id]['qty'])
    return float(qty)-float(fill)
