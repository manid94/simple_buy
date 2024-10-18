import threading
import time
from datetime import datetime
from strategy import start_the_strategy
from utils import ist

# Create an Event object to signal the thread

ist_datatime = datetime.now(ist)


TOKENGENERATION_TIME = {
    'hours': 8,
    'minutes': 8,
    'seconds': 0
}

STRATEGY_CLOSE_TIME = {
    'hours': 16,
    'minutes': 0,
    'seconds': 0
}

def main():
    # Define the end time as 2:30 PM
    start_time = ist_datatime.replace(hour=TOKENGENERATION_TIME['hours'], minute=TOKENGENERATION_TIME['minutes'], second=TOKENGENERATION_TIME['seconds'], microsecond=0).time()
    end_time = ist_datatime.replace(hour=STRATEGY_CLOSE_TIME['hours'], minute=STRATEGY_CLOSE_TIME['minutes'], second=STRATEGY_CLOSE_TIME['seconds'], microsecond=0).time()
    entry_happened_today = False
    current_time = datetime.now(ist).time()
    stop_event = threading.Event()


    # Keep running the task periodically until 2:30 PM
    while True:
        if(start_time <= current_time) and not entry_happened_today:
            thread = threading.Thread(target=start_the_strategy, args=(stop_event,0))
            thread.start()
            entry_happened_today = True
            print("Main program has finished.")

        if(end_time <= current_time):
            stop_event.set()
            # Wait for the thread to finish
            thread.join()
            time.sleep(36000)
            entry_happened_today = False
            stop_event.clear()

    return True

main()