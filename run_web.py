"""
Script to run the web interface for file-tools
This can be packaged as an executable using PyInstaller or similar tools
"""
import sys
import os
import threading
import time
import webbrowser
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def run_web_interface():
    """Run the FastAPI web interface"""
    from backend.api.api import app
    import uvicorn

    # Run the Uvicorn server
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

def open_browser():
    """Open the default browser to the application after a delay"""
    # Wait for the server to start
    time.sleep(3)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    # Start the web server in a separate thread
    server_thread = threading.Thread(target=run_web_interface)
    server_thread.daemon = True
    server_thread.start()

    # Open the browser in another thread
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)