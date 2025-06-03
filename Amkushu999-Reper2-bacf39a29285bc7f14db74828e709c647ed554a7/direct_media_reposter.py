#!/usr/bin/env python3
"""
Direct media reposter that uses hardcoded values for quick testing
"""

import os
import sys
import logging
import asyncio
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Hardcode the correct channel values
os.environ["SOURCE_CHANNELS"] = "[2580593874]"
os.environ["DESTINATION_CHANNELS"] = "[2510014428]"

# Run the reposter
async def main():
    try:
        # Import and run the media reposter
        import simple_media_reposter
        return await simple_media_reposter.main()
    except Exception as e:
        logger.error(f"Error running media reposter: {e}")
        return 1

if __name__ == "__main__":
    # Create and run the event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        exit_code = loop.run_until_complete(main())
    finally:
        loop.close()
        
    sys.exit(exit_code)
