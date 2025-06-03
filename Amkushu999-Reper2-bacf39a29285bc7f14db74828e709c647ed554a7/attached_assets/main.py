from flask import Flask, render_template_string, redirect, url_for, request
import subprocess
import signal
import os
import sys
import logging
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Bot process tracking
bot_process = None
process_lock = threading.Lock()

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

# HTML template for the home page
HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Channel Reposter Bot</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <style>
        body {
            padding: 20px;
            background-color: #1c1e29;
            color: #f5f5f5;
        }
        .container {
            max-width: 800px;
        }
        .card {
            background-color: #2b2d3a;
            border: none;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        }
        .card-header {
            background-color: #3b3d4a;
            border-bottom: 1px solid #494b5a;
            border-radius: 8px 8px 0 0 !important;
        }
        .btn-primary {
            background-color: #0d6efd;
            border: none;
        }
        .btn-danger {
            background-color: #dc3545;
            border: none;
        }
        .btn-success {
            background-color: #198754;
            border: none;
        }
        .status-badge {
            font-size: 1rem;
            padding: 8px 16px;
        }
        .instructions {
            background-color: #2b2d3a;
            border-left: 4px solid #0d6efd;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 0 8px 8px 0;
        }
        h1, h2, h3 {
            color: #f5f5f5;
        }
        pre {
            background-color: #1c1e29;
            color: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
        }
        code {
            color: #0dcaf0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mt-4 mb-4">🤖 Telegram Channel Reposter Bot</h1>
        
        <div class="card mb-4">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h2 class="mb-0">Bot Status</h2>
                {% if is_running %}
                <span class="badge bg-success status-badge">Running</span>
                {% else %}
                <span class="badge bg-danger status-badge">Stopped</span>
                {% endif %}
            </div>
            <div class="card-body">
                <div class="d-flex justify-content-center gap-3">
                    <form method="post" action="{{ url_for('start_bot') }}">
                        <button type="submit" class="btn btn-success" {% if is_running %}disabled{% endif %}>
                            <i class="bi bi-play-fill"></i> Start Bot
                        </button>
                    </form>
                    <form method="post" action="{{ url_for('stop_bot') }}">
                        <button type="submit" class="btn btn-danger" {% if not is_running %}disabled{% endif %}>
                            <i class="bi bi-stop-fill"></i> Stop Bot
                        </button>
                    </form>
                    <form method="post" action="{{ url_for('restart_bot') }}">
                        <button type="submit" class="btn btn-primary">
                            <i class="bi bi-arrow-clockwise"></i> Restart Bot
                        </button>
                    </form>
                </div>
            </div>
        </div>

        <div class="instructions p-4 rounded">
            <h3>📋 Instructions</h3>
            <p>This web interface allows you to control the Telegram Channel Reposter Bot. The bot will:</p>
            <ul>
                <li>Monitor source channels for new messages</li>
                <li>Repost messages to a destination channel without the forward tag</li>
                <li>Replace channel tags to make content appear as if it originated from the destination channel</li>
            </ul>
            
            <h4 class="mt-4">🔧 Bot Setup</h4>
            <p>To use the bot, you need to:</p>
            <ol>
                <li>Start the bot using the button above</li>
                <li>Interact with the bot on Telegram to configure it</li>
                <li>Set API credentials and configure channel IDs</li>
            </ol>
            
            <h4 class="mt-4">💻 Advanced Configuration</h4>
            <p>For advanced users:</p>
            <pre><code>python gen_session.py # Generate a new user session
python standalone_bot.py # Run the bot directly in a terminal</code></pre>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    """Home route"""
    # Check if bot is running
    is_running = bot_process is not None and bot_process.poll() is None
    return render_template_string(HOME_TEMPLATE, is_running=is_running)

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

@app.route('/start_bot', methods=['POST'])
def start_bot():
    """Start the bot process"""
    start_bot_process()
    return redirect(url_for('home'))

@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    """Stop the bot process"""
    stop_bot_process()
    return redirect(url_for('home'))

@app.route('/restart_bot', methods=['POST'])
def restart_bot():
    """Restart the bot process"""
    stop_bot_process()
    start_bot_process()
    return redirect(url_for('home'))

# Auto-start the bot when the app starts
if __name__ != "__main__":
    # Only auto-start in production (when imported by a WSGI server)
    logger.info("Automatically starting the bot...")
    start_bot_process()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)