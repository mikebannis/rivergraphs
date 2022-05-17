import os

APP_PATH='/var/www/rivergraphs/app/'
GAGE_FILE= 'gages.csv'
STATIC_DIR='static'

def static_dir():
    """ Return static dir path """
    return os.path.join(APP_PATH, STATIC_DIR) if os.getcwd() == '/' else \
        STATIC_DIR

def gages_file():
    """ Return full path to gages file """
    return  os.path.join(APP_PATH, GAGE_FILE) if os.getcwd() == '/' else \
        GAGE_FILE


