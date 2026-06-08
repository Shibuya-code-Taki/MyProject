"""Stems Pro — Server entry point.

Usage:
    python run.py              # dev mode, port 8000
    uvicorn run:app --host 0.0.0.0 --port 8000
"""

import sys
import os

# Ensure the server dir is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("run:app", host="0.0.0.0", port=8000, reload=True)
