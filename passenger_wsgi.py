import sys
import os

# Insert application root directory to sys.path
sys.path.insert(0, os.path.dirname(__file__))

from run import app as application
