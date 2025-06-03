import os
import sys
import logging
import subprocess
import threading
import time
import signal
from dotenv import load_dotenv
from flask import Flask, jsonify

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask app - minimal configuration just to keep the gunicorn running
app = Flask(__name__)

# Bot process tracking
bot_process = None
process_lock = threading.Lock()

def run_bot():
    """Run the standalone Telegram bot"""
    try:
        # First, try to kill any existing bot processes to prevent conflicts
        import subprocess
        try:
            subprocess.run(["python", "kill_bots.py"], check=True)
            logger.info("Killed any existing bot processes")
        except Exception as e:
            logger.error(f"Error killing existing bot processes: {e}")
            
        # Import and run the standalone bot
        logger.info("Starting standalone Telegram bot...")
        import standalone_bot
        standalone_bot.main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise

# Create routes for the Flask app
@app.route('/')
def index():
    """Main index page"""
    is_running = bot_process is not None and bot_process.poll() is None
    return f"""
    <html>
        <head>
            <title>Telegram Channel Reposter Bot</title>
            <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
        </head>
        <body class="container mt-4">
            <div class="card">
                <div class="card-header bg-dark text-white">
                    <h2>Telegram Channel Reposter Bot</h2>
                </div>
                <div class="card-body">
                    <h5 class="card-title">Bot Status: {'Running' if is_running else 'Stopped'}</h5>
                    <p class="card-text">This is a Telegram bot that forwards messages from source channels to destination channels.</p>
                    <p>To test the bot:</p>
                    <ol>
                        <li>Send messages to the source channel</li>
                        <li>They will be automatically forwarded to the destination channel</li>
                        <li>Media forwarding has been fixed and should work correctly</li>
                    </ol>
                    <a href="/health" class="btn btn-primary">Check Bot Health</a>
                </div>
            </div>
        </body>
    </html>
    """

@app.route('/health')
def health_check():
    """Health check endpoint"""
    is_running = bot_process is not None and bot_process.poll() is None
    return jsonify({"status": "ok", "bot_running": is_running})

# Bot starter function using a subprocess
def start_bot_process():
    """Start the bot in a separate process"""
    global bot_process
    
    try:
        # Kill any existing standalone_bot.py processes
        subprocess.run(["python", "kill_bots.py"], check=True)
        logger.info("Killed any existing bot processes")
    except Exception as e:
        logger.error(f"Error killing existing bot processes: {e}")
    
    with process_lock:
        if bot_process is None or bot_process.poll() is not None:
            logger.info("Starting Telegram bot process...")
            # Start the bot using subprocess
            bot_process = subprocess.Popen(["python", "standalone_bot.py"], 
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT,
                                         text=True)
            logger.info(f"Bot process started with PID: {bot_process.pid}")
            
            # Start a thread to log output from the bot process
            def log_output():
                for line in bot_process.stdout:
                    logger.info(f"BOT: {line.strip()}")
            
            threading.Thread(target=log_output, daemon=True).start()
            return True
        else:
            logger.info(f"Bot process already running (PID: {bot_process.pid})")
            return False

# Auto-start the bot when the app starts
if __name__ != "__main__":
    # Only auto-start in production (when imported by a WSGI server)
    logger.info("Automatically starting the bot...")
    start_bot_process()

# Main entrypoint when running directly
if __name__ == "__main__":
    logger.info("Starting Telegram Channel Reposter Bot...")
    run_bot()