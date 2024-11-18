import time
import logging
from utils.utils import ist
from brokerapi import getshoonyatradeapi
from datetime import datetime
from api_websocket import OpenWebSocket
from utils.custom_threading import MyThread
from seperate_strategy import NewStrategy
from utils.exit_all import exit_all_positions





logging.basicConfig(filename=f'strategy_log_files/strategy__{datetime.now(ist).strftime("%Y_%m%d_%H %M %S")}.log', level=logging.INFO)

def trace_execution(str= 'no data', data=datetime.now(ist).strftime("%Y %m %d - %H /%M/ %S")):
    print(f'{str} at {data}')
    logging.info(f'{str} at {data}')
# flag to tell us if the api_websocket is open updated and running


# Constants Configs
SYMBOL = 'NiftyBank'
BUY_BACK_STATIC = True
INITIAL_LOTS = 1  # Start with 1 lot
STRIKE_DIFFERENCE = 0
ONE_LOT_QUANTITY = 15  # Number of units per lot in Bank Nifty
TARGET_PROFIT = 500
MAX_LOSS = 300
MAX_LOSS_PER_LEG = 200
SAFETY_STOP_LOSS_PERCENTAGE = 0.83 # 0.985 #0.83
BUY_BACK_PERCENTAGE = 0.82 #0.98 #0.82
SELL_TARGET_PERCENTAGE = 0.02 #0.01 # 0.025
BUY_BACK_LOSS_PERCENTAGE = 0.90
AVAILABLE_MARGIN = 5000
ENTRY_TIME = {
    'hours': 9,
    'minutes': 22,
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







def start_the_strategy(stop_event):
    global api
    try:
        trace_execution(f'Starting WebSocket data connection...{datetime.now(ist).strftime("%Y %m %d - %H /%M/ %S")}')
        api = getshoonyatradeapi()
        api_websocket = OpenWebSocket(api)
        
        while not api_websocket.is_socket_opened():
            time.sleep(0.1)



        nifty_data = {
                        # API & WebSocket initialization
            'api': api,
            'api_websocket':api_websocket,

            # Strategy parameters
            'SYMBOL':"NIFTY",
            'token' : '26000',
            'BUY_BACK_STATIC':BUY_BACK_STATIC,
            'INITIAL_LOTS':INITIAL_LOTS,
            'STRIKE_DIFFERENCE':STRIKE_DIFFERENCE,
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
            #'stop_event':stop_event,

            # Dynamic configuration
            'BUY_BACK_LOTS':BUY_BACK_LOTS,
            # Trail Profit and stoploss
            'ENABLE_TRAILING': True,
            'Trail_config' : {
                'profit_trail_start_at' : 1600,
                'profit_lock_after_start': 300,
                'on_profit_increase_from_trail': 100,
                'increase_profit_lock_by': 95
            }
        }

        bank_nifty_data = {
            'api': api,
            'api_websocket':api_websocket,

            # Strategy parameters
            'SYMBOL':"BANK_NIFTY",
            'token' : '26009',
            'BUY_BACK_STATIC':BUY_BACK_STATIC,
            'INITIAL_LOTS':INITIAL_LOTS,
            'STRIKE_DIFFERENCE': 1000,
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
            #'stop_event':stop_event,

            # Dynamic configuration
            'BUY_BACK_LOTS':BUY_BACK_LOTS,
            # Trail Profit and stoploss
            'ENABLE_TRAILING': True,
            'Trail_config' : {
                'profit_trail_start_at' : 1600,
                'profit_lock_after_start': 300,
                'on_profit_increase_from_trail': 100,
                'increase_profit_lock_by': 95
            }
        }

        nifty_strategy = NewStrategy(nifty_data)
        nifty_thread = MyThread(target=nifty_strategy.run_strategy, args=(), daemon=True)
        nifty_thread.start()

        bank_nifty_strategy = NewStrategy(bank_nifty_data)
        bank_nifty_thread = MyThread(target=bank_nifty_strategy.run_strategy, args=(), daemon=True)
        bank_nifty_thread.start()
        #run_strategy(stop_event, api_websocket)

        nifty_thread.join()
        bank_nifty_thread.join()
        api.close_websocket()
        return True
    except TypeError as e:
        trace_execution(f"Type error occurred: {e}")
        exit_all_positions(api)
        raise ValueError('Error on exit start_the_strategy')
    except ZeroDivisionError as e:
        trace_execution(f"Math error occurred: {e}")
        exit_all_positions(api)
        raise ValueError('Error on exit start_the_strategy')
    except ValueError as e:
        trace_execution(f"Value error occurred: {e}")
        exit_all_positions(api)
        raise ValueError('Error on exit start_the_strategy')
    except Exception as e:
        trace_execution(f"An unexpected error occurred: {e}")
        exit_all_positions(api)
        raise ValueError('Error on exit start_the_strategy')