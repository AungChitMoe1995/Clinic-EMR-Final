import sys
import os

# Insert application root directory to sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Default to production configuration under Passenger WSGI
os.environ.setdefault('FLASK_ENV', 'production')

from run import app as application
