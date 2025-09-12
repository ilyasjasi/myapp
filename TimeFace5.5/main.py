
from app import app, socketio, db
from websocket_events import start_device_monitor
import os
import logging

if __name__ == '__main__':
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Start device status monitoring (only if not in debug mode to avoid double start)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        start_device_monitor()
        logging.info("Device monitoring started")

    print(f"Starting Flask application on port {port}")
    print("Note: Scheduler runs as a separate service. Use 'python start_scheduler.py start' to start it.")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
