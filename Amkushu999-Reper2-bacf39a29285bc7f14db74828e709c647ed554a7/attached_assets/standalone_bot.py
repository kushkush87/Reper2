#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import signal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", None)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Application shutdown flag
shutdown_flag = False

# Initialize reposting flag
reposting_active = False

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    global shutdown_flag
    logger.info("Shutdown signal received")
    shutdown_flag = True

async def start_bot():
    """Start the Telegram bot"""
    try:
        from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
        import bot
        from bot import start, button_callback, handle_text_input, handle_sticker_input
        import nest_asyncio
        
        # Apply nest_asyncio to allow nested event loops
        nest_asyncio.apply()
        
        # Set the reposting_active variable in bot module to use the same state
        bot.reposting_active = reposting_active
        
        # Initialize the telegram bot
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Set up client for channel operations
        # Make sure user_client is initialized
        try:
            # Initialize client if not already done
            if not hasattr(bot, 'user_client') or not bot.user_client or not bot.user_client.is_connected():
                # Define the setup_client function in case it's not available
                if not hasattr(bot, 'API_ID') or not bot.API_ID:
                    logger.warning("API_ID not available. Functionality will be limited.")
                    
                if not hasattr(bot, 'API_HASH') or not bot.API_HASH:
                    logger.warning("API_HASH not available. Functionality will be limited.")
                    
                if not hasattr(bot, 'USER_SESSION') or not bot.USER_SESSION:
                    logger.warning("USER_SESSION not available. Functionality will be limited.")
                
                # If we have credentials, try to connect client
                if (hasattr(bot, 'API_ID') and bot.API_ID and 
                    hasattr(bot, 'API_HASH') and bot.API_HASH and 
                    hasattr(bot, 'USER_SESSION') and bot.USER_SESSION):
                    
                    # Create and connect client
                    from telethon import TelegramClient
                    from telethon.sessions import StringSession
                    
                    if hasattr(bot, 'user_client') and bot.user_client:
                        try:
                            await bot.user_client.disconnect()
                        except Exception as e:
                            logger.warning(f"Error disconnecting existing client: {e}")
                    
                    # Create new client with a unique session name
                    bot.user_client = TelegramClient(
                        StringSession(bot.USER_SESSION),
                        bot.API_ID,
                        bot.API_HASH,
                        connection_retries=None,  # Infinite retries
                        retry_delay=1  # 1 second delay between retries
                    )
                    
                    # Connect client
                    await bot.user_client.connect()
                    
                    if await bot.user_client.is_user_authorized():
                        logger.info("User client connected and authorized successfully")
                        
                        # Initialize event handlers for the client based on current configuration
                        await bot.save_config()
                    else:
                        logger.warning("User client connected but not authorized")
            else:
                logger.info("User client already initialized")
        except Exception as client_error:
            logger.error(f"Error setting up user client: {client_error}")
        
        # Add standard handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", start))
        application.add_handler(CommandHandler("go", start))
        
        # Add the callback handler for buttons
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Add sticker handler with highest priority (0)
        # This ensures sticker messages are processed before any other handlers
        print("==== STANDALONE: REGISTERING STICKER HANDLER WITH PRIORITY 0 =====")
        sticker_handler = MessageHandler(filters.STICKER, handle_sticker_input)
        application.add_handler(sticker_handler, 0)
        print(f"==== STANDALONE: STICKER HANDLER REGISTERED: {sticker_handler} =====")
        
        # Add text message handler with normal priority
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        
        # Start the application
        await application.initialize()
        await application.start()
        # Start polling with faster interval for quicker response
        await application.updater.start_polling(
            poll_interval=0.5  # Poll more frequently (default is 1.0)
        )
        
        logger.info("Bot is now running")
        
        # Keep running until shutdown flag is set
        while not shutdown_flag:
            await asyncio.sleep(1)
            
        # Handle shutdown
        logger.info("Shutting down bot...")
        
        # Close the user client
        if hasattr(bot, 'user_client') and bot.user_client and bot.user_client.is_connected():
            await bot.user_client.disconnect()
            logger.info("User client disconnected")
        
        # Stop the application
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Bot has been shut down")
        
    except Exception as e:
        logger.error(f"Error in bot: {e}")
        return 1
    
    return 0

def main():
    """Entry point for the bot"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting Telegram bot...")
    
    # Create and run event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        exit_code = loop.run_until_complete(start_bot())
    finally:
        # Ensure the loop is closed properly
        loop.close()
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())