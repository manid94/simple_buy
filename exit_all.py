import time
from brokerapi import getshoonyatradeapi


def exit_all_positions(api):
    try:
        # Close the websocket and log out the current session
        api.close_websocket()
        api.logout()
        time.sleep(5)  # Wait before starting a new session

        # Start a new session to get live orders
        new_session = getshoonyatradeapi()  # Ensure this function is defined elsewhere
        live_orders = new_session.get_positions()

        # Iterate over live positions to close each
        for data in live_orders:
            # Skip positions with zero quantity
            if int(data['netqty']) == 0:
                continue

            # Determine the order type based on position quantity
            order_type = 'S' if int(data['netqty']) > 0 else 'B'
            prd = data.get('prd', 'I')  # Use 'I' as default if 'prd' is missing
            qty = abs(int(data['netqty']))  # Ensure quantity is positive
            tsym = data['tsym']
            exch = data['exch']

            # Place market order to exit the position
            order_response = api.place_order(
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

    except Exception as e:
        print(f"Error in exiting all positions: {e}")
