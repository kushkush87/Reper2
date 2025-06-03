#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import signal
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", None)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Application shutdown flag
shutdown_flag = False

# Initialize reposting flag - always true by default for immediate reposting
reposting_active = True

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
                    logger.warning("USER_SESSION not available. Running in bot-only mode with limited functionality.")
                    # Set a flag to indicate we're in bot-only mode for improved UI
                    bot.BOT_ONLY_MODE = True
                
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
                        
                        # Force reposting to be active
                        bot.reposting_active = True
                        logger.info("FORCED reposting_active to TRUE")
                        # Use try-except for the reposting state save
                        try:
                            if hasattr(bot, 'save_reposting_state'):
                                await bot.save_reposting_state()
                            else:
                                logger.info("No save_reposting_state function found, using direct save")
                                # Get the current bot config
                                current_config = {}
                                if 'BOT_CONFIG' in os.environ and os.environ['BOT_CONFIG']:
                                    try:
                                        current_config = json.loads(os.environ['BOT_CONFIG'])
                                    except:
                                        current_config = {}
                                    
                                # Update with new reposting state
                                current_config['reposting_active'] = True
                                
                                # Save back to environment
                                os.environ['BOT_CONFIG'] = json.dumps(current_config)
                                
                                # Update .env file
                                try:
                                    dotenv_file = '.env'
                                    if os.path.exists(dotenv_file):
                                        # Read the file
                                        with open(dotenv_file, 'r') as file:
                                            lines = file.readlines()
                                            
                                        # Find the BOT_CONFIG line and update it
                                        with open(dotenv_file, 'w') as file:
                                            for line in lines:
                                                if line.startswith('BOT_CONFIG='):
                                                    file.write(f"BOT_CONFIG='{json.dumps(current_config)}\n'")
                                                else:
                                                    file.write(line)
                                except Exception as e:
                                    logger.error(f"Error updating .env file: {e}")
                        except Exception as e:
                            logger.error(f"Error saving reposting state: {e}")
                            # Still ensure the variable is set
                            bot.reposting_active = True
                        
                        # Add debugging event handlers for monitoring message flow
                        from telethon import events
                        
                        # Debug handler for ALL messages
                        async def debug_all_messages(event):
                            logger.info(f"DEBUG-ALL: Received event: {event.__class__.__name__}")
                            if hasattr(event, 'message') and hasattr(event.message, 'text'):
                                text_preview = event.message.text[:50] + '...' if len(event.message.text) > 50 else event.message.text
                                logger.info(f"DEBUG-ALL: Message text: {text_preview}")
                            if hasattr(event, 'chat_id'):
                                logger.info(f"DEBUG-ALL: Chat ID: {event.chat_id}")
                                
                        # Add global handler for all messages
                        bot.user_client.add_event_handler(debug_all_messages, events.NewMessage())
                        logger.info("Added global debug handler for ALL messages")
                        
                        # Add specific handler for source channel if configured
                        if bot.active_channels["source"]:
                            source_channels = bot.active_channels["source"]
                            
                            # Debug handler specifically for source channel messages
                            async def debug_source_messages(event):
                                logger.info(f"DEBUG-SOURCE: Message in source channel {event.chat_id}")
                                if hasattr(event, 'message'):
                                    if hasattr(event.message, 'text') and event.message.text:
                                        text_preview = event.message.text[:50] + '...' if len(event.message.text) > 50 else event.message.text
                                        logger.info(f"DEBUG-SOURCE: Text: {text_preview}")
                                    media_type = 'unknown'
                                    if hasattr(event.message, 'photo') and event.message.photo:
                                        media_type = 'photo'
                                    elif hasattr(event.message, 'document') and event.message.document:
                                        media_type = 'document'
                                    elif hasattr(event.message, 'video') and event.message.video:
                                        media_type = 'video'
                                    logger.info(f"DEBUG-SOURCE: Media type: {media_type}")
                            
                            # Register source-specific handler
                            bot.user_client.add_event_handler(
                                debug_source_messages,
                                events.NewMessage(chats=source_channels)
                            )
                            logger.info(f"Added specific debug handler for source channels: {source_channels}")
                            
                            # Add a debug handler for this specific chat ID we're seeing in logs
                            debug_chat_id = -1002597966668
                            async def debug_specific_channel(event):
                                logger.info(f"DEBUG-SPECIFIC: Message in specific channel {event.chat_id}")
                                if hasattr(event, 'message'):
                                    if hasattr(event.message, 'text') and event.message.text:
                                        text_preview = event.message.text[:50] + '...' if len(event.message.text) > 50 else event.message.text
                                        logger.info(f"DEBUG-SPECIFIC: Text: {text_preview}")
                                    media_type = 'unknown'
                                    if hasattr(event.message, 'photo') and event.message.photo:
                                        media_type = 'photo'
                                    elif hasattr(event.message, 'document') and event.message.document:
                                        media_type = 'document'
                                    elif hasattr(event.message, 'video') and event.message.video:
                                        media_type = 'video'
                                    logger.info(f"DEBUG-SPECIFIC: Media type: {media_type}")
                                    
                                    # Try to forward this message to our destination channel
                                    logger.info(f"DEBUG: Attempting to forward message from {debug_chat_id} to destination channel")
                                    asyncio.create_task(bot.handle_new_message(event))
                            
                            # Register handler for the specific chat ID
                            bot.user_client.add_event_handler(
                                debug_specific_channel,
                                events.NewMessage(chats=[debug_chat_id])
                            )
                            logger.info(f"Added debug handler for specific chat ID: {debug_chat_id}")
                            
                            # Print a message showing the relationship between positive and negative IDs
                            logger.info(f"DEBUG: For reference, the relationship between IDs:")
                            logger.info(f"DEBUG: Negative ID format: {debug_chat_id}")
                            logger.info(f"DEBUG: Positive ID format (source_channels): {source_channels}")
                            logger.info(f"DEBUG: Math relationship: {debug_chat_id} vs {-debug_chat_id - 1000000000000}")
                            logger.info(f"DEBUG: This info helps understand Telegram's channel ID formats.")
                            
                            # Check if we need to add the negative format to our source channels
                            # This is critical if we're seeing messages from channels in negative format
                            neg_chat_id = debug_chat_id
                            pos_chat_id = int(-neg_chat_id - 1000000000000)
                            
                            # If the calculated positive ID is different from what's in our config
                            if pos_chat_id != source_channels[0]:
                                logger.info(f"DEBUG: Channel ID mismatch between negative and positive formats!")
                                logger.info(f"DEBUG: Adding negative format {neg_chat_id} to source channels list")
                                
                                # Add the negative format to our source channels
                                if neg_chat_id not in source_channels:
                                    source_channels.append(neg_chat_id)
                                    # Update the bot's active channels
                                    bot.active_channels["source"] = source_channels
                                    logger.info(f"DEBUG: Updated source channels: {source_channels}")
                                    
                                    # Force reposting to be active again
                                    bot.reposting_active = True
                                    logger.info("FORCED reposting_active to TRUE again after channel update")
                                    # Try to save the reposting state again with the same robust approach
                                    try:
                                        if hasattr(bot, 'save_reposting_state'):
                                            await bot.save_reposting_state()
                                        else:
                                            # Direct config update without await
                                            if hasattr(bot, 'save_config'):
                                                await bot.save_config()
                                    except Exception as e:
                                        logger.error(f"Error saving reposting state after channel update: {e}")
                                        # Ensure this doesn't block execution
                            
                            
                            # We also need to ensure the handle_new_message is properly registered
                            # Clear any existing handlers for this specific function first
                            if hasattr(bot.user_client, '_event_builders'):
                                builders = list(bot.user_client._event_builders) if bot.user_client._event_builders else []
                                for builder in builders:
                                    if builder[1].__name__ == 'handle_new_message':
                                        try:
                                            bot.user_client.remove_event_handler(builder[1], builder[0])
                                            logger.info("Removed existing handle_new_message handler")
                                        except Exception as e:
                                            logger.error(f"Error removing handler: {e}")
                                            
                            # Register our handler with fresh settings
                            bot.user_client.add_event_handler(
                                bot.handle_new_message,
                                events.NewMessage(chats=source_channels)
                            )
                            logger.info(f"Re-registered handle_new_message for source channels: {source_channels}")
                            
                            # Do the same for edited messages handler
                            for builder in builders:
                                if builder[1].__name__ == 'handle_edited_message':
                                    try:
                                        bot.user_client.remove_event_handler(builder[1], builder[0])
                                        logger.info("Removed existing handle_edited_message handler")
                                    except Exception as e:
                                        logger.error(f"Error removing handler: {e}")
                                        
                            # Register our edited message handler
                            bot.user_client.add_event_handler(
                                bot.handle_edited_message,
                                events.MessageEdited(chats=source_channels)
                            )
                            logger.info(f"Re-registered handle_edited_message for source channels: {source_channels}")
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
        try:
            # Try with various filter formats for compatibility
            if hasattr(filters, 'STICKER'):
                sticker_handler = MessageHandler(filters.STICKER, handle_sticker_input)
            elif hasattr(filters, 'Sticker') and hasattr(filters.Sticker, 'ALL'):
                sticker_handler = MessageHandler(filters.Sticker.ALL, handle_sticker_input)
            else:
                # Last resort, just use a general filter and check for stickers in the handler
                sticker_handler = MessageHandler(~filters.COMMAND, handle_sticker_input)
                logger.warning("Using fallback sticker handler with general filter")
        except Exception as e:
            logger.error(f"Error setting up sticker handler: {e}")
            # Create a simple fallback handler
            sticker_handler = MessageHandler(~filters.COMMAND, handle_sticker_input)
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