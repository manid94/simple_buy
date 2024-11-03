import time
from datetime import datetime

from brokerapi import getshoonyatradeapi
from custom_threading import MyThread


def exit_all_positions(api):
    api.close_websocket()
    api.logout()
    time.sleep(5)
    new_session = getshoonyatradeapi()
    live_orders = new_session.get_positions()
    for data in live_orders:
        type = 
        prd = data['prd'] || 'I'
        qty = data['netqty']
        tsym = data['tsym']
        exch = data['exch']
        order_responce = api.place_order(buy_or_sell=type, product_type=prd,
                    exchange=exch, tradingsymbol=tsym, 
                    quantity=qty, discloseqty=0,price_type='MKT', price=0, trigger_price=None,
                    retention='DAY', remarks=('exit all position'))
    


