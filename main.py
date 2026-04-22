import os
import sys

# Fix for local development - allow HTTP for OAuth
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Add the backend directory to the path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_dir)

from app import app

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)