import logging

# Create two different loggers
logger1 = logging.getLogger('my_logger1')
logger2 = logging.getLogger('my_logger2')

# Set logging level
logger1.setLevel(logging.DEBUG)
logger2.setLevel(logging.INFO)

# Create file handlers for each logger
handler1 = logging.FileHandler('log1.log')
handler2 = logging.FileHandler('log2.log')

# Create formatters for each handler
formatter1 = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
formatter2 = logging.Formatter('%(asctime)s - %(message)s')

# Add formatters to handlers
handler1.setFormatter(formatter1)
handler2.setFormatter(formatter2)

# Add handlers to loggers
logger1.addHandler(handler1)
logger2.addHandler(handler2)

test = 'pp'
# Log some messages
logger1.debug('This is a debug message for log1')
logger1.info('This is an info message for log1')
logger2.info(f'This is an  {test} info message for log2')