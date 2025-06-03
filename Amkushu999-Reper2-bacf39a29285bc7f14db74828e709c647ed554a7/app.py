import os
import sys
import logging
import subprocess
import threading
import time
import signal

from flask import Flask, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Bot process tracking
bot_process = None
process_lock = threading.Lock()

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    logger.info("Stopping the bot due to signal...")
    stop_bot_process()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def start_bot_process():
    """Start the bot in a separate process"""
    global bot_process
    
    # First, make sure we don't have any zombie bot processes
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

def stop_bot_process():
    """Stop the bot process"""
    global bot_process
    
    # First use the kill_bots.py script to ensure all bot processes are stopped
    try:
        # Kill any existing standalone_bot.py processes
        subprocess.run(["python", "kill_bots.py"], check=True)
        logger.info("Killed any existing bot processes")
    except Exception as e:
        logger.error(f"Error killing existing bot processes: {e}")
    
    with process_lock:
        if bot_process is not None and bot_process.poll() is None:
            try:
                logger.info(f"Stopping bot process (PID: {bot_process.pid})...")
                # First try graceful termination
                bot_process.terminate()
                # Give it some time to terminate gracefully
                for _ in range(5):
                    if bot_process.poll() is not None:
                        break
                    time.sleep(0.5)
                    
                # If still running, force kill
                if bot_process.poll() is None:
                    logger.info("Bot did not terminate gracefully, forcing kill...")
                    bot_process.kill()
                    
                bot_process.wait()
                logger.info("Bot process stopped")
                return True
            except Exception as e:
                logger.error(f"Error stopping bot process: {e}")
                return False
        else:
            logger.info("No running bot process to stop")
            return False

@app.route('/health')
def health_check():
    """Health check endpoint"""
    # Check if bot is running
    is_running = bot_process is not None and bot_process.poll() is None
    return jsonify({"status": "ok", "bot_running": is_running})

# Auto-start the bot when the app starts
if __name__ != "__main__":
    # Only auto-start in production (when imported by a WSGI server)
    logger.info("Automatically starting the bot...")
    start_bot_process()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
