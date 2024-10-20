import pytz
from datetime import date, datetime
import time


ist = pytz.timezone('Asia/Kolkata')
ist_datatime = datetime.now(ist)

def round_to_nearest_0_05(value):
    return round(value * 20) / 20


# Function to place sell orders for both legs
def place_market_order(api, LEG_TOKEN, option_type, type, lots, leg_type):
    # tsym = SYMBOLDICT[LEG_TOKEN[option_type]]['ts']
    tsym = LEG_TOKEN[option_type+'_tsym']
    order_responce = api.place_order(buy_or_sell=type, product_type='I',
                        exchange='NFO', tradingsymbol=tsym, 
                        quantity=lots, discloseqty=0,price_type='MKT', price=0, trigger_price=None,
                        retention='DAY', remarks=(option_type+' '+leg_type))
    if not ('norenordno' in  order_responce):
        raise ValueError('Error in Order placement')
    order_id = order_responce['norenordno']
    return order_id


def place_limit_order(api, LEG_TOKEN, option_type, type, lots, limit_price, leg_type):
    # tsym = SYMBOLDICT[LEG_TOKEN[option_type]]['ts']
    tsym = LEG_TOKEN[option_type+'_tsym']
    order_responce = api.place_order(buy_or_sell=type, product_type='I',
                        exchange='NFO', tradingsymbol=tsym, 
                        quantity=lots, discloseqty=0,price_type='LMT', price=limit_price, trigger_price=None,
                        retention='DAY', remarks=(option_type+' '+leg_type))

    if not ('norenordno' in  order_responce):
        raise ValueError('Error in Order placement')
    order_id = order_responce['norenordno']
    return order_id


def place_market_exit(api, tsym, type, lots):
    order_responce = api.place_order(buy_or_sell=type, product_type='I',
                        exchange='NFO', tradingsymbol=tsym, 
                        quantity=lots, discloseqty=0,price_type='MKT', price=0, trigger_price=None,
                        retention='DAY', remarks='exit')
    if not ('norenordno' in  order_responce):
        raise ValueError('Error in Order placement')
    order_id = order_responce['norenordno']
    return order_id


# Function to check if the order status is complete
def is_order_complete(order_id, ORDER_STATUS, logger):
    # Check if the order exists in the ORDER_STATUS dictionary
    logger(ORDER_STATUS)
    if order_id in ORDER_STATUS:
        return ORDER_STATUS[order_id].get('status').lower() == 'complete'
    return False


# Function to check if the order status is complete
def is_order_cancelled(order_id, ORDER_STATUS):
    # Check if the order exists in the ORDER_STATUS dictionary
    if order_id in ORDER_STATUS:
        return ORDER_STATUS[order_id].get('status').lower() == 'cancelled'
    return False



