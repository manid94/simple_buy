import pandas as pd
import copy
import time

GLOBAL_ORDER_STATUS = {}

class OpenWebSocket:
    def __init__(self, api):
        print('entered')
        self.SYMBOLDICT = {}
        self.ORDER_STATUS = []
        self.api = api
        self.socket_opened = False
        #self.event_handler_order_update = order_updates
        searchData = api.searchscrip(exchange='NFO', searchtext='SBI')
        if 'stat' in searchData:
            self.open_socket()
        
    #application callbacks
    def event_handler_order_update(self, message):
        global GLOBAL_ORDER_STATUS
        # self.ORDER_STATUS
        #print('print("order event: " + str(message))')
        # print("order event: " + str(message['norenordno']))
        # order event: {
        #       't': 'om', 'norenordno': '24101600226847', 'uid': 'FT053455', 'actid': 'FT053455', 'exch': 'NFO', 'tsym': 'BANKNIFTY16OCT24P50500',
        #        'trantype': 'B', 'qty': '30', 'prc': '5.25', 'pcode': 'I', 'remarks': 'my_order_002', 'rejreason': ' ', 'status': 'COMPLETE',
        #        'reporttype': 'Fill', 'flqty': '30', 'flprc': '2.85', 'flid': '380225664', 'fltm': '16-10-2024 11:15:20', 'prctyp': 'LMT',
        #         'ret': 'DAY', 'exchordid': '1500000079566637', 'fillshares': '30', 'dscqty': '0', 'avgprc': '2.85', 'exch_tm': '16-10-2024 11:15:20'
        # }
        #print("order event: " + str(message))
        
        if 'norenordno' in message:
            GLOBAL_ORDER_STATUS[message['norenordno']] = {}
            GLOBAL_ORDER_STATUS[message['norenordno']]['status'] = message['status']
            GLOBAL_ORDER_STATUS[message['norenordno']]['flqty'] =  message.get('flqty', 0)
            GLOBAL_ORDER_STATUS[message['norenordno']]['qty'] =  message.get('qty', 0)
            GLOBAL_ORDER_STATUS[message['norenordno']]['tsym'] =  message.get('tsym', 0)
            GLOBAL_ORDER_STATUS[message['norenordno']]['prc'] =  message.get('prc', 0)
            GLOBAL_ORDER_STATUS[message['norenordno']]['prctyp'] =  message.get('prctyp', 0)
            GLOBAL_ORDER_STATUS[message['norenordno']]['trantype'] =  message.get('trantype', 'S')
            GLOBAL_ORDER_STATUS[message['norenordno']]['option_type'] =  message.get('remarks', 'exit')
            GLOBAL_ORDER_STATUS[message['norenordno']]['remarks'] =  message.get('remarks', 'exit')

            # print('norenordno')
            # print(message['status'].lower())
            if message['status'].lower() == 'complete':
                GLOBAL_ORDER_STATUS[message['norenordno']]['avgprc'] =  message.get('avgprc', 0)
            # logger_entry(message.get('tsym', 0),message['norenordno'],message.get('trantype', 'U'),message.get('remarks', 'exit'),message.get('qty', 0),message.get('prc', 0),message.get('prctyp', 'LMT'),  message.get('flqty', 0),message.get('avgprc', 0),  message.get('status', 'S'))
                    

    


    def event_handler_quote_update(self,message):
        # global self.SYMBOLDICT
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
        if key in self.SYMBOLDICT:
            symbol_info =  self.SYMBOLDICT[key]
            symbol_info.update(message)
            self.SYMBOLDICT[key] = symbol_info
        else:
            self.SYMBOLDICT[key] = message

        # print(self.SYMBOLDICT[key])

    def open_callback(self):
        #global socket_opened
        self.socket_opened = True
        print('app is connected')

        #api.subscribe(['NSE|22', 'BSE|522032'])

    #end of callbacks
    def open_socket(self):
        if self.socket_opened != True:
            print(self.socket_opened)
            self.api.start_websocket(order_update_callback=self.event_handler_order_update, subscribe_callback=self.event_handler_quote_update, socket_open_callback=self.open_callback)
        #api.start_websocket(order_update_callback=event_handler_order_update, subscribe_callback=event_handler_quote_update, socket_open_callback=open_callback)
        print(self.socket_opened)
        return True
    
    def fetch_last_trade_price(self, option_type, LEG_TOKEN):
        # print('Deepak')
        # print(SYMBOLDICT)
        
        # Check if the option_type exists in LEG_TOKEN
        if option_type not in LEG_TOKEN:
            raise ValueError(f"Invalid option_type: {option_type}")
        
        # Get the token for the given option_type
        leg_token = LEG_TOKEN[option_type]
        
        # Check if the leg_token exists in SYMBOLDICT
        if leg_token not in self.SYMBOLDICT:
            raise KeyError(f"Token {leg_token} not found in SYMBOLDICT")
        
        # Fetch the last trade price
        temp_data = self.SYMBOLDICT[leg_token].get('lp', None)
        
        # Validate if the last trade price (temp_data) exists and is not None
        if temp_data is None:
            raise ValueError(f"No last trade price available for {option_type} (token: {leg_token})")
        
        # Return the last trade price as a float
        return float(temp_data)
    
    def get_latest_data(self):
        return GLOBAL_ORDER_STATUS
    
    def is_socket_opened(self):
        if self.socket_opened:
            return True
        return False
