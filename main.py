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
    
    stop_event = threading.Event()
    thread = threading.Thread(target=start_the_strategy, args=(stop_event,))

    # Keep running the task periodically until 2:30 PM
    while True:
        current_time = datetime.now(ist).time()
        print("entered.")
        if(start_time <= current_time <= end_time) and not entry_happened_today:
            print("Starting strategy thread.")
            try:
                thread.start()
            except Exception as e:
                print(f"Error while starting the strategy: {e}")
            entry_happened_today = True
            print("Strategy has started.")
        else:
            print('already running')

        if current_time > end_time:
            print("Stopping strategy thread.")
            stop_event.set()  # Signal the thread to stop
            try:
                thread.join()
            except Exception as e:
                print(f"Error while starting the strategy: {e}")
            print("Strategy has stopped for today.")
            
            # Reset for the next day
            time.sleep(60 * 60 * 10)  # Sleep for 10 hours before re-checking
            entry_happened_today = False
            stop_event.clear()  # Clear the stop event flag
        time.sleep(60) 
    return True

main()