import sys
import os
import json
from unittest.mock import MagicMock

# 1. Mock the missing dependency 'channel_model_38901'
# This allows importing the app without the actual ChannelEngine library
sys.modules['channel_model_38901'] = MagicMock()
sys.modules['channel_model_38901.simulator'] = MagicMock()

# 2. Set environment variable to bypass check
# We point to an existing directory so os.path.exists passes
os.environ['CHANNEL_ENGINE_PATH'] = os.getcwd()

# 3. Add service path
sys.path.insert(0, os.path.abspath("channel-engine-service"))

# 4. Import the app
try:
    from app.main import app
    from fastapi.openapi.utils import get_openapi
    
    # 5. Generate OpenAPI Schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    
    # 6. Save to file
    output_path = "gui/src/types/channel-engine-schema.json"
    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)
        
    print(f"✅ Successfully generated OpenAPI schema at {output_path}")

except Exception as e:
    print(f"❌ Failed to generate schema: {e}")
    import traceback
    traceback.print_exc()
