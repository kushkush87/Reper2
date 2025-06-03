#!/usr/bin/env python3
"""
A simplified bot runner that properly handles Telethon's event loop issues
"""
import os
import sys
import asyncio
import logging
import signal
import nest_asyncio
from dotenv import load_dotenv

# Apply nest_asyncio to handle nested event loops
nest_asyncio.apply()

# Load environment variables
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", None)
API_ID = os.environ.get("API_ID", None)
API_HASH = os.environ.get("API_HASH", None)
USER_SESSION = os.environ.get("USER_SESSION", None)

# Set up logging with a clear format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Application shutdown flag
shutdown_flag = False

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    global shutdown_flag
    logger.info(f"Received signal {sig}, initiating shutdown...")
    shutdown_flag = True

async def run_bot():
    """Run the Telegram bot with proper event loop handling"""
    logger.info("Starting bot with clean event loop...")
    
    try:
        # Import telegram libraries after event loop setup
        from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
        
        # Import custom bot module
        import bot
        from bot import start, button_callback, handle_text_input, handle_sticker_input
        
        # Ensure required environment variables are available to the bot module
        bot.BOT_TOKEN = BOT_TOKEN
        bot.API_ID = API_ID
        bot.API_HASH = API_HASH
        bot.USER_SESSION = USER_SESSION
        
        # Initialize client if needed
        if USER_SESSION and API_ID and API_HASH:
            try:
                # Import telethon here to avoid early initialization issues
                from telethon import TelegramClient
                from telethon.sessions import StringSession
                
                # Safely disconnect any existing client
                if hasattr(bot, 'user_client') and bot.user_client:
                    try:
                        if bot.user_client.is_connected():
                            logger.info("Disconnecting existing client...")
                            await bot.user_client.disconnect()
                    except Exception as e:
                        logger.warning(f"Error disconnecting client: {e}")
                
                # Create a new client instance
                logger.info("Creating new Telethon client...")
                bot.user_client = TelegramClient(
                    StringSession(USER_SESSION),
                    int(API_ID),
                    API_HASH,
                    connection_retries=None,  # Infinite retries
                    retry_delay=1  # 1 second delay between retries
                )
                
                # Connect the client
                logger.info("Connecting to Telegram servers...")
                await bot.user_client.connect()
                
                # Check authorization
                if await bot.user_client.is_user_authorized():
                    logger.info("✅ User client connected and authorized successfully")
                    await bot.save_config()
                else:
                    logger.warning("⚠️ User client connected but not authorized")
            except Exception as e:
                logger.error(f"❌ Error setting up Telethon client: {e}")
        else:
            logger.warning("⚠️ Missing API credentials - some functionality will be limited")
        
        # Initialize the Telegram bot
        logger.info("Building Telegram bot application...")
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Set up command handlers
        logger.info("Registering bot handlers...")
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", start))
        application.add_handler(CommandHandler("go", start))
        
        # Add callback handler for buttons
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Add message handlers
        logger.info("Registering sticker handler...")
        sticker_handler = MessageHandler(filters.STICKER, handle_sticker_input)
        application.add_handler(sticker_handler, 0)  # Priority 0 (highest)
        
        logger.info("Registering text handler...")
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        
        # Start the bot
        logger.info("Initializing application...")
        await application.initialize()
        
        logger.info("Starting application...")
        await application.start()
        
        logger.info("Starting updater...")
        await application.updater.start_polling(poll_interval=0.5)
        
        logger.info("✅ Bot is now running and ready to receive messages")
        
        # Keep the bot running
        while not shutdown_flag:
            await asyncio.sleep(1)
        
        # Clean shutdown
        logger.info("Initiating clean shutdown...")
        
        # Disconnect client
        if hasattr(bot, 'user_client') and bot.user_client:
            try:
                if bot.user_client.is_connected():
                    logger.info("Disconnecting user client...")
                    await bot.user_client.disconnect()
            except Exception as e:
                logger.warning(f"Error during client disconnect: {e}")
        
        # Stop the bot
        logger.info("Stopping bot updater...")
        await application.updater.stop()
        
        logger.info("Stopping application...")
        await application.stop()
        
        logger.info("Shutting down application...")
        await application.shutdown()
        
        logger.info("✅ Bot has been shut down successfully")
        
    except Exception as e:
        logger.error(f"❌ Critical error in bot: {e}", exc_info=True)
        return 1
    
    return 0

def main():
    """Main entry point with proper signal handling"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🚀 Starting Telegram bot with improved event loop handling...")
    
    # Set up the event loop
    try:
        # Create a fresh event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the bot
        exit_code = loop.run_until_complete(run_bot())
        
        # Clean up
        loop.close()
        
        return exit_code
    except Exception as e:
        logger.error(f"❌ Error in main function: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())