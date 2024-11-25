import time
from utils.brokerapi import getshoonyatradeapi # since code was executing from root directory we need to consider it

def place_market_order(new_session, order_type, data):
            prd = data.get('prd', 'I')  # Use 'I' as default if 'prd' is missing
            qty = abs(int(data['netqty']))  # Ensure quantity is positive
            tsym = data['tsym']
            exch = data['exch']

            # Place market order to exit the position
            order_response = new_session.place_order(
                buy_or_sell=order_type,
                product_type=prd,
                exchange=exch,
                tradingsymbol=tsym,
                quantity=qty,
                discloseqty=0,
                price_type='MKT',
                price=0,
                trigger_price=None,
                retention='DAY',
                remarks='exit all positions'
            )

            # Log or handle the response if needed
            print(f"Order response for {tsym}: {order_response}")

    


def exit_all_positions(api = {}):
    try:
        print('start')
        # Close the websocket and log out the current session
        if api:
            print('inside if')
            api.close_websocket()
            api.logout()
            time.sleep(5)  # Wait before starting a new session

        # Start a new session to get live orders
        new_session = getshoonyatradeapi()  # Ensure this function is defined elsewhere
        live_orders = new_session.get_positions()
        print('session')
        print(live_orders)

        # Iterate over live positions to close each sell quantity first
        for data in live_orders: 
            # Determine the order type based on position quantity
            if int(data['netqty']) > 0 :
                place_market_order(new_session, 'S', data)
            
        for data in live_orders: 
            if int(data['netqty']) < 0:
                place_market_order(new_session, 'B', data)
            continue
    except Exception as e:
        print(f"Error in exiting all positions: {e}")
        
        
        
#exit_all_positions()
