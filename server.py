import hashlib
import os
import logging
from datetime import datetime
from flask import request, jsonify, Blueprint
from flask import Flask, render_template
from flask_socketio import SocketIO, send, emit, join_room
from util.auth import auth_bp, hash_token
from util.battlefield import battlefield_bp, register_battlefield_handlers

from util.database import user_collection, room_collection
from util.rooms import register_room_handlers

app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')

from flask import g

@app.context_processor
def inject_user():
    # now every template rendered via app will get current_user
    return dict(current_user=g.user)

app.config['SECRET_KEY'] = 'secret!'  # Replace with a secure key in production

# Setup logging directory
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configure logging
logging.basicConfig(
    filename='logs/server.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Define log handler
def log_request_info():
    ip = request.remote_addr
    method = request.method
    path = request.path
    logging.info(f"{ip} - {method} {path}")
app.before_request(log_request_info)

app.register_blueprint(auth_bp)
register_room_handlers(socketio, user_collection, room_collection)
register_battlefield_handlers(socketio, user_collection, room_collection)

@app.route('/')
def index():
    return render_template('login.html')


@app.route('/lobby')
def lobby():
    return render_template('lobby.html')

@app.route('/lobby/<lobby_id>')
def lobby_by_id(lobby_id):
    room = room_collection.find_one({"id": lobby_id})
    if not room:
        return "Room not found", 404
    return render_template('lobby_by_id.html', lobby_id=lobby_id, room_name=room["room_name"])




app.register_blueprint(battlefield_bp)






if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True, debug=True)
