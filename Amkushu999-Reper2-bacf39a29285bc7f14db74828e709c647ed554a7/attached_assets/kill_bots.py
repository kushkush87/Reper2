#!/usr/bin/env python3
import os
import signal
import subprocess
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def kill_bot_processes():
    """Kill all running instances of standalone_bot.py"""
    try:
        # Get all python processes
        proc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        output = proc.stdout
        
        # Check for bot processes
        bot_pids = []
        for line in output.split('\n'):
            if 'standalone_bot.py' in line and 'grep' not in line:
                parts = line.split()
                if len(parts) > 1:
                    pid = parts[1]
                    bot_pids.append(pid)
        
        # Kill any found processes
        if bot_pids:
            logger.info(f"Found {len(bot_pids)} bot processes to kill: {', '.join(bot_pids)}")
            for pid in bot_pids:
                try:
                    # Try to terminate gracefully first
                    os.kill(int(pid), signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to process {pid}")
                except ProcessLookupError:
                    logger.warning(f"Process {pid} not found")
                except Exception as e:
                    logger.error(f"Error killing process {pid}: {str(e)}")
            
            # Wait a moment to ensure processes terminate
            time.sleep(2)
            
            # Check if any processes are still alive and force kill them
            proc = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            output = proc.stdout
            
            for pid in bot_pids:
                if f" {pid} " in output:
                    try:
                        logger.warning(f"Process {pid} still alive, sending SIGKILL")
                        os.kill(int(pid), signal.SIGKILL)
                    except Exception as e:
                        logger.error(f"Error force killing process {pid}: {str(e)}")
            
            return True
        else:
            logger.info("No bot processes found")
            return False
    except Exception as e:
        logger.error(f"Error finding/killing bot processes: {str(e)}")
        return False

if __name__ == "__main__":
    kill_bot_processes()