import logging
import os
from utils import ist
from datetime import datetime

log_directory = 'strategy_log_files'
def createLogger(name):
    os.makedirs(log_directory, exist_ok=True)
    # Initialize the logger
    logger_cust = logging.getLogger('my_logger1')
    logger_cust.setLevel(logging.INFO)

    # Create a file handler with a timestamped log file name
    log_filename = f'{log_directory}/strategy_{name}{datetime.now(ist).strftime("%Y_%m%d_%H%M%S")}.log'
    handler = logging.FileHandler(log_filename)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Add the handler to the logger
    if not logger_cust.handlers:  # Avoid adding multiple handlers if this setup code runs multiple times
        logger_cust.addHandler(handler)

    # Example logging
    logger_cust.info("Logger initialized and ready for use.")
    return logger_cust