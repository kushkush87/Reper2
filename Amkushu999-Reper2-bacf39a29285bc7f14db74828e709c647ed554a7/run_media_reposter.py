#!/usr/bin/env python3
"""
Simple script to run the media reposter.
This extracts active channels from standalone_bot.py configuration and runs the simplified media reposter.
"""

import os
import sys
import json
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

def setup_env_variables():
    """Set up environment variables for the media reposter"""
    # Get the channel configuration from the environment
    try:
        from config import CHANNEL_CONFIG
        
        # Extract source and destination channels
        source_channels = CHANNEL_CONFIG.get("source_channels", [])
        destination_channels = CHANNEL_CONFIG.get("destination_channels", [])
        
        # If no destination channels array, try single destination
        if not destination_channels and CHANNEL_CONFIG.get("destination_channel"):
            destination_channels = [CHANNEL_CONFIG.get("destination_channel")]
        
        # Log the configuration
        logger.info(f"Source channels: {source_channels}")
        logger.info(f"Destination channels: {destination_channels}")
        
        # Set the environment variables for the media reposter
        os.environ["SOURCE_CHANNELS"] = str(source_channels)
        os.environ["DESTINATION_CHANNELS"] = str(destination_channels)
        
        return True
    except Exception as e:
        logger.error(f"Error setting up environment variables: {e}")
        return False

def main():
    """Main function to run the media reposter"""
    logger.info("Starting media reposter setup")
    
    # Make sure essential environment variables are available
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH") or not os.environ.get("USER_SESSION"):
        logger.error("API_ID, API_HASH, and USER_SESSION must be set in the .env file")
        return 1
    
    # Set up environment variables
    if not setup_env_variables():
        logger.error("Failed to set up environment variables")
        return 1
    
    # Log the configuration
    logger.info("Configuration loaded successfully")
    
    # Run the media reposter
    try:
        logger.info("Starting media reposter...")
        import simple_media_reposter
        
        # Create and run the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            exit_code = loop.run_until_complete(simple_media_reposter.main())
        finally:
            loop.close()
            
        return exit_code
    except Exception as e:
        logger.error(f"Error running media reposter: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
