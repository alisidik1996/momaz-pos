import sys
from pathlib import Path

# Ensure root repository directory is added to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.main import app

# Export ASGI app instance for Vercel Serverless Functions
app = app
