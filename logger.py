import json
import datetime
import random
import os
import threading
import copy
from deepdiff import DeepDiff


class LocalJsonLogger:
    def __init__(self):
        self.log_file_name = f'logger_files/trading_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json'
        self.log_data = []

        # Ensure the directory exists
        self.ensure_directory_exists()

        # Create a new log file locally
        self.create_new_log_file()

    def ensure_directory_exists(self):
        """Ensure the directory for the log file exists."""
        directory = os.path.dirname(self.log_file_name)
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Directory '{directory}' created.")

    def create_new_log_file(self):
        """Create an empty JSON log file locally."""
        # Check if the log file already exists, and if not, create it
        if not os.path.exists(self.log_file_name):
            with open(self.log_file_name, 'w') as file:
                json.dump([], file, indent=4)
            print(f"New log file '{self.log_file_name}' created.")
        else:
            print(f"Log file '{self.log_file_name}' already exists. Appending to it.")

    def append_log(self, new_entry):
        """Append new log entry and update the file locally."""
        # Add new entry to local log data
        self.log_data.append(new_entry)
        
        # Update the log file locally
        with open(self.log_file_name, 'w') as file:
            json.dump(self.log_data, file, indent=4)
        print(f"Appended new entry to '{self.log_file_name}'.")
                      
    def generate_log_entry(self, datas):
        # Extracting individual values from the datas dictionary
        tsymbol = datas.get("symbol")
        orderno = datas.get("order_number")
        direction = datas.get("direction")
        order_type = datas.get("order_type")
        qty = datas.get("quantity")
        ordered_price = datas.get("ordered_price")
        order_method = datas.get("order_method")
        fillqty = datas.get("filled_quantity")
        avg_price = datas.get("average_price")
        status = datas.get("status")
    
        print(f'inside generate_log_entry {datas}')
        """Generate a new log entry with random data (simulating a trading strategy)."""
        return {
            "time": str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "tsymbol": str(tsymbol),
            "orderno": str(orderno),
            "direction": str(direction),
            "type": str(type),
            "quantity": str(qty),
            "ordered_price": str(ordered_price),
            "executed_price": str(avg_price),
            "executed_quantity": str(fillqty),
            "order_type": str(order_type),
            "order_method": str(order_method),
            "status": str(status)   
        }
        return {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tsymbol": f"BANKNIFTY23OCT24C{random.randint(50000, 60000)}",
            "orderno": f"{random.randint(10000000000000, 99999999999999)}",
            "type": random.choice(["B", "S"]),
            "quantity": str(random.randint(10, 100)),
            "ordered_price": round(random.uniform(100.0, 300.0), 2),
            "executed_price": round(random.uniform(100.0, 300.0), 2),
            "executed_quantity": str(random.randint(10, 100)),
            "order_type": random.choice(["MKT", "LMT", "update"]),
            "status": random.choice(["placed", "open", "pending", "completed"])
        }

# if __name__ == "__main__":
#     # Configuration
#     log_file_name = f"logger_files/trading_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

#     # Initialize the local JSON logger
#     logger = LocalJsonLogger(log_file_name)

#     # Simulate logging dynamic data during strategy execution
#     for _ in range(10):  # Simulate 10 log entries
#         new_entry = logger.generate_log_entry()
#         logger.append_log(new_entry)


class ThrottlingLogger:
    def __init__(self, orderid, logger):
        self.orderno = orderid
        self.logger = logger
        self.previousLogger = {}
        self.lock = threading.Lock()  # Lock to ensure thread safety
    
    def loggerentry(self, ORDER_STATUS):
        # Start a new thread for each logger entry
        initialize_threading = threading.Thread(target=self.check_update_thread, args=(ORDER_STATUS,))
        initialize_threading.start()  # Start the thread

    def check_update_thread(self, ORDER_STATUS):
        with self.lock:  # Ensure thread safety when accessing shared data
            # If the order ID hasn't been logged yet, initialize it
            if self.orderno not in self.previousLogger:
                self.previousLogger[self.orderno] = {}

            # Perform deep comparison to see if there are any differences
            diff = DeepDiff(self.previousLogger[self.orderno], ORDER_STATUS.get(self.orderno, {}))
            
            if not diff:
                # Update the previous logger with a deep copy of the current state
                self.previousLogger[self.orderno] = copy.deepcopy(ORDER_STATUS[self.orderno])
            else:
                # If there's a difference, log the new status and update the previous logger
                message = ORDER_STATUS[self.orderno]
                self.logger(
                    message.get('tsym', 0),
                    message.get('norenordno'),
                    message.get('trantype', 'U'),
                    message.get('remarks', 'exit'),
                    message.get('qty', 0),
                    message.get('prc', 0),
                    message.get('prctyp', 'LMT'),
                    message.get('flqty', 0),
                    message.get('avgprc', 0),
                    message.get('status', 'S')
                )





def generate_and_update_file(data, logger_class):
    # Generate log entry and append to log
    new_entry = logger_class.generate_log_entry(data)
    logger_class.append_log(new_entry)
    return True

