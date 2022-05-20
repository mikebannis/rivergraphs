import os

APP_PATH='/var/www/rivergraphs/app/'
GAGE_FILE= 'gages.csv'
STATIC_DIR='static'

def static_dir():
    """ Return static dir path """
    if os.getcwd() == '/':
        return os.path.join(APP_PATH, STATIC_DIR) 
    elif os.getcwd() == '/home/mikebannister':
        return os.path.join(APP_PATH, STATIC_DIR) 
    elif os.path.exists(STATIC_DIR):
        return STATIC_DIR
    else:
        return os.path.join(APP_PATH, STATIC_DIR) 


def gages_file():
    """ Return full path to gages file """
    if os.getcwd() == '/':
        return os.path.join(APP_PATH, GAGE_FILE) 
    elif os.getcwd() == '/home/mikebannister':
        return os.path.join(APP_PATH, GAGE_FILE) 
    elif os.path.exists(GAGE_FILE):
        return GAGE_FILE
    else:
        return os.path.join(APP_PATH, GAGE_FILE) 


