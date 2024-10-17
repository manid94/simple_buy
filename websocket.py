
# Common to all strategies
ORDER_STATUS = {}
# flag to tell us if the websocket is open
socket_opened = False
SYMBOLDICT = {}


#application callbacks
def event_handler_order_update(message):
    global ORDER_STATUS
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
            

    


def event_handler_quote_update(message):
    global SYMBOLDICT
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



def open_socket(api):
    if socket_opened != True:
        print(socket_opened)
        api.start_websocket(order_update_callback=event_handler_order_update, subscribe_callback=event_handler_quote_update, socket_open_callback=open_callback)
    #api.start_websocket(order_update_callback=event_handler_order_update, subscribe_callback=event_handler_quote_update, socket_open_callback=open_callback)
    print(socket_opened)
    return True

    #api.subscribe(['NSE|22', 'BSE|522032'])
def getSocketData():
    global ORDER_STATUS, SYMBOLDICT
    return { ORDER_STATUS, SYMBOLDICT }


