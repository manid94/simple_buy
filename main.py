import threading
import multiprocessing
import time
from datetime import datetime
from strategy import start_the_strategy
from utils.utils import ist
from trailsAndSampleResponceFiles.temp.server.server import start_server

ist_datatime = datetime.now(ist)



TOKENGENERATION_TIME = {
    'hours': 8,
    'minutes': 22,
    'seconds': 0
}

STRATEGY_CLOSE_TIME = {
    'hours': 15,
    'minutes': 22,
    'seconds': 0
}

def main():
    # Define the start and end times
    start_time = ist_datatime.replace(hour=TOKENGENERATION_TIME['hours'], minute=TOKENGENERATION_TIME['minutes'], second=TOKENGENERATION_TIME['seconds'], microsecond=0).time()
    end_time = ist_datatime.replace(hour=STRATEGY_CLOSE_TIME['hours'], minute=STRATEGY_CLOSE_TIME['minutes'], second=STRATEGY_CLOSE_TIME['seconds'], microsecond=0).time()
    entry_happened_today = False
    
    stop_event = threading.Event()
    strategy_thread = threading.Thread(target=start_the_strategy, args=(stop_event,))

    # Start Flask server in a separate process
    server_process = multiprocessing.Process(target=start_server)
    server_process.start()

    try:
        while True:
            current_time = datetime.now(ist).time()
            if start_time <= current_time <= end_time and not entry_happened_today:
                print("Starting strategy thread.")
                try:
                    strategy_thread.start()
                except Exception as e:
                    print(f"Error while starting the strategy: {e}")
                entry_happened_today = True
                print("Strategy has started.")
            elif current_time > end_time:
                print("Stopping strategy thread.")
                stop_event.set()  # Signal the thread to stop
                # strategy_thread.join()  # Wait for the thread to finish
                print("Strategy has stopped for today.")
                
                # Reset for the next day
                time.sleep(60 * 60 * 10)  # Sleep for 10 hours before re-checking
                entry_happened_today = False
                stop_event.clear()  # Clear the stop event flag
            time.sleep(20)
    except KeyboardInterrupt:
        print("Shutting down server and strategy...")
    finally:
        if server_process.is_alive():
            server_process.terminate()  # Ensure the server process stops
        print("Server process terminated.")
    return True

# Add this block for Windows compatibility
if __name__ == '__main__':
    main()
