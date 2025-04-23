import hashlib
import os
import logging
import uuid
from flask import request, jsonify
import bcrypt
from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room
from util.auth import auth_bp, hash_token

from util.database import user_collection, room_collection

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
@app.route('/')
def index():
    return render_template('login.html')


@app.route('/api/hello')
def hello():
    return 'Hello from the MMO backend!'

@app.route('/lobby')
def lobby():
    return render_template('lobby.html')

rooms = set()  # in-memory; you can later store in MongoDB

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    rooms = [r['name'] for r in room_collection.find()]
    emit('room_list', rooms)

@socketio.on('get_rooms')
def handle_get_rooms():
    emit('room_list', [{'id': r['id'], 'name': r['name']} for r in room_collection.find()])


@socketio.on('create_room')
def handle_create_room(room_name):
    existing = room_collection.find_one({'name': room_name})
    if not existing:
        room_id = str(uuid.uuid4())
        room_collection.insert_one({'id': room_id, 'name': room_name, 'players': []})
    emit('room_list', [{'id': r['id'], 'name': r['name']} for r in room_collection.find()], broadcast=True)

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data.get('roomId') or data.get('room')
    player_id = data['player']

    room = room_collection.find_one({'id': room_id})
    if not room:
        emit('error', {'message': 'Room not found'}, to=request.sid)
        return

    room_name = room['name']
    join_room(room_id)

    room_collection.update_one(
        {'id': room_id},
        {'$addToSet': {'players': {'id': player_id, 'x': 0, 'y': 0}}}
    )

    emit('message', f"{player_id} joined {room_name}", room=room_id)
    emit('player_joined', {'player': player_id}, to=request.sid)


@socketio.on('move')
def handle_move(data):
    room_id = data.get('roomId') or data.get('room')
    player = data['player']
    new_x = data['x']
    new_y = data['y']

    room_collection.update_one(
        {'id': room_id, 'players.id': player},
        {'$set': {'players.$.x': new_x, 'players.$.y': new_y}}
    )

    updated_room = room_collection.find_one({'id': room_id})
    if not updated_room:
        print(f"[ERROR] Room with id '{room_id}' not found")
        return

    emit('player_positions', updated_room['players'], room=room_id)

@app.route('/battlefield')
def battlefield():
    return render_template('battlefield.html')



@app.route('/api/whoami')
def whoami():
    token = request.cookies.get('auth_token')
    hashed_token = hashlib.sha256(token.encode()).hexdigest()

    user = user_collection.find_one({'auth_token': hashed_token})
    if user:
        return jsonify({'username': user['username']})
    return jsonify({'username': None})



if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
