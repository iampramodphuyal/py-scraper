import logging
import os

"""
Just a simple custom logger with timestamps
"""
def create_logger(name: str, log_file: str = "") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG) 
    if not logger.handlers:
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        if log_file:
            check_file_path("crawlLog.txt")
            file_handler = logging.FileHandler(log_file, mode='w')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger


"""
Create Directory for logfile if not exists
"""
def check_file_path(path:str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True) 
