import hashlib
import os
import logging
from datetime import datetime
from flask import request, jsonify, Blueprint, g
from flask import Flask, render_template
from flask_socketio import SocketIO

from util.auth import auth_bp, hash_token
from util.battlefield import battlefield_bp, register_battlefield_handlers
from util.database import user_collection, room_collection
from util.rooms import register_room_handlers

app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')

@app.context_processor
def inject_user():
    return dict(current_user=g.user)

app.config['SECRET_KEY'] = 'secret!'  # Replace with a secure key in production

# Setup logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    filename='logs/server.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log_request_info():
    ip = request.remote_addr
    method = request.method
    path = request.path
    logging.info(f"{ip} - {method} {path}")
app.before_request(log_request_info)

# Blueprints and socketio event registration
app.register_blueprint(auth_bp)
app.register_blueprint(battlefield_bp)
register_room_handlers(socketio, user_collection, room_collection)
register_battlefield_handlers(socketio, user_collection, room_collection)

# Routes
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

# 🆕 New API route to check if user is lobby owner
@app.route('/api/roominfo')
def room_info():
    auth_token = request.cookies.get('auth_token')
    if not auth_token:
        return {"error": "Not authenticated"}, 401

    user = user_collection.find_one({'auth_token': hash_token(auth_token)})
    if not user:
        return {"error": "User not found"}, 404

    username = user['username']

    room_id = request.args.get('room_id')
    if not room_id:
        return {"error": "Room ID required"}, 400

    room = room_collection.find_one({"id": room_id})
    if not room:
        return {"error": "Room not found"}, 404

    return {
        "username": username,
        "owner": room.get("owner")  # assuming 'owner' field exists in your room doc
    }

# kick no team players
@app.route('/api/players_in_room')
def api_players_in_room():
    room_id = request.args.get('room_id')
    if not room_id:
        return {'error': 'Missing room_id'}, 400

    room = room_collection.find_one({'id': room_id})
    if not room:
        return {'error': 'Room not found'}, 404

    return room.get('players', [])


# SocketIO Server run
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True, debug=False)

