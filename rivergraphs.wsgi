#!/usr/bin/python3
import sys
import os
import logging

logging.basicConfig(stream=sys.stderr)
path = os.path.dirname(__file__)
sys.path.insert(0, path)
#sys.path.insert(0,"/home/mikebannister/code/rivergraphs/")

from app import app as application
