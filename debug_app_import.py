import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Add project root to path
sys.path.append(os.getcwd())

try:
    from modelscope.pipelines import pipeline
    print("SUCCESS: modelscope.pipelines.pipeline imported")
except ImportError as e:
    print(f"ERROR: modelscope import failed: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"ERROR: modelscope import unexpected error: {e}")
    import traceback
    traceback.print_exc()

try:
    from backend.core.index_manager import IndexManager
    from backend.utils.config_loader import ConfigLoader
    
    config = ConfigLoader()
    im = IndexManager(config)
    print("IndexManager initialized successfully")
    
    if im.embedding_model:
        print("Embedding model loaded successfully")
    else:
        print("Embedding model failed to load")
        
except Exception as e:
    print(f"ERROR: IndexManager init failed: {e}")
    import traceback
    traceback.print_exc()
