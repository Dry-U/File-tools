#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to check web API initialization without full startup
"""
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent  # Go up one more level to project root
sys.path.insert(0, str(project_root))

print("Testing web API initialization...")

try:
    # Test basic imports first
    from backend.utils.config_loader import ConfigLoader
    print("[OK] ConfigLoader import successful")

    from backend.utils.logger import get_logger
    logger = get_logger(__name__)
    print("[OK] Logger import and initialization successful")

    # Now test the web API module import
    import backend.api.api
    print("[OK] Web API module import successful")

    # Import the app after the modules have been loaded
    from backend.api.api import app
    print("[OK] App import successful")

    print("\nAll components loaded successfully!")
    print("You can now run: python -m uvicorn backend.api.api:app --host 127.0.0.1 --port 8000")

except ImportError as e:
    print(f"[ERROR] Import error: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"[ERROR] Other error: {e}")
    import traceback
    traceback.print_exc()