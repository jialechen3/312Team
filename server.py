

from flask import Flask, render_template
from flask_socketio import SocketIO, send, emit, join_room
from util.auth import auth_bp
from util.database import user_collection
app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')
app.config['SECRET_KEY'] = 'secret!'  # Replace with a secure key in production


app.register_blueprint(auth_bp)
@app.route('/')
def index():
    user_collection.insert_one({"name": "Jiale Test"})
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
    emit('room_list', list(rooms))

@socketio.on('get_rooms')
def handle_get_rooms():
    emit('room_list', list(rooms))

@socketio.on('create_room')
def handle_create_room(room_name):
    rooms.add(room_name)
    print(f'Room created: {room_name}')
    emit('room_list', list(rooms), broadcast=True)

@socketio.on('join_room')
def handle_join_room(room_name):
    join_room(room_name)
    print(f'Client joined room: {room_name}')
    emit('message', f"A new player joined room '{room_name}'", room=room_name)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
