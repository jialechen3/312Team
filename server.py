import os
import logging
from datetime import datetime
from flask import request
from flask import Flask, render_template
from flask_socketio import SocketIO, send, emit, join_room
from util.auth import auth_bp, hash_token

from util.database import user_collection
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
    user_collection.insert_one({"name": "Jiale Test"})
    return render_template('login.html')

@app.route('/api/hello')
def hello():
    return 'Hello from the MMO backend!'

@app.route('/lobby')
def lobby():
    return render_template('lobby.html')

@app.route('/lobby/<lobby_id>')
def lobby_by_id(lobby_id):
    return render_template('lobby_by_id.html', lobby_id=lobby_id)

rooms = set()  # in-memory; you can later store in MongoDB
red_team = set()  # Im following the same way rooms are made for now in-memory; will need to save in DB to specify which lobbies team were joining -- Aaron
blue_team = set()  # Im following the same way rooms are made for now in-memory; will need to save in DB to specify which lobbies team were joining -- Aaron
no_team = set()  # Im following the same way rooms are made for now in-memory; will need to save in DB to specify which lobbies team were joining -- Aaron

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('page_ready')
def handle_page_ready(data):
    page = data.get('page')
    if page == 'create_lobby':
        emit('room_list', list(rooms))
    elif page == 'team_select':
        red_team.add('shun')
        red_team.add('wei')
        blue_team.add('nadia')
        blue_team.add('tess')
        no_team.add('aaron')
        no_team.add('jiale')
        #adding user to no team
        auth_token = request.cookies.get('auth_token')
        if auth_token:
            user = user_collection.find_one({'auth_token': hash_token(auth_token)})
            if user:
                username = user['username']
                no_team.add(username)
            else:
                print(f'User does not exist')
        else:
            print(f'Not logged in')

        emit('team_red_list', list(red_team))
        emit('team_blue_list', list(blue_team))
        emit('no_team_list', list(no_team))

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

######## Lobby WS #########

@socketio.on('connect_lobby')
def handle_connect_lobby():
    print('Client connected to lobby')

    emit('team_red_list', list(red_team))
    emit('team_blue_list', list(blue_team))
    emit('no_team_list', list(no_team))

@socketio.on('get_teams')
def handle_get_teams():
    emit('team_red_list', list(red_team))
    emit('team_blue_list', list(blue_team))
    emit('no_team_list', list(no_team))

'''@socketio.on('join_team')
def handle_join_team(team):
'''

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
