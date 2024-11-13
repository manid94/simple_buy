import logging
from datetime import datetime
import os
import pytz
from utils import ist

log_directory = 'strategy_log_files'
IST = pytz.timezone('Asia/Kolkata')

class ISTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # Convert record's creation time to IST
        record_time = datetime.fromtimestamp(record.created, IST)
        return record_time.strftime('%Y-%m-%d %H:%M:%S')

def createLogger(name):
    os.makedirs(log_directory, exist_ok=True)
    # Initialize the logger
    logger_cust = logging.getLogger(name)
    logger_cust.setLevel(logging.INFO)

    # Create a file handler with a timestamped log file name
    log_filename = f'{log_directory}/strategy_{name}{datetime.now(ist).strftime("%Y_%m%d_%H%M%S")}.log'
    handler = logging.FileHandler(log_filename)
    formatter = ISTFormatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Add the handler to the logger
    if not logger_cust.handlers:  # Avoid adding multiple handlers if this setup code runs multiple times
        logger_cust.addHandler(handler)

    # Example logging
    logger_cust.info("Logger initialized and ready for use.")
    return logger_cust