import uuid

from flask_socketio import emit, join_room
from flask import request
from util.auth import hash_token
from bson import ObjectId

connected_users = {}

def get_sid(username):
    for sid, name in connected_users.items():
        if name == username:
            return sid
    return None

def register_room_handlers(socketio, user_collection, room_collection):

    @socketio.on('create_room', namespace='/lobby')
    def handle_create_room(room_name):
        auth_token = request.cookies.get('auth_token')
        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            print("[CREATE_ROOM] User not found!")
            return

        username = user['username']
        room_id = str(uuid.uuid4())  # generate unique ID
        new_room = {
            "id": room_id,
            "room_name": room_name,
            "owner": username,   # ADD OWNER
            "red_team": [],
            "blue_team": [],
            "no_team": []
        }
        room_collection.insert_one(new_room)

        # emit all rooms with id + name
        all_rooms = [
            {"id": str(room["id"]), "name": room["room_name"]}
            for room in room_collection.find()
        ]
        emit('room_list', all_rooms, broadcast=True)

    @socketio.on('get_rooms', namespace='/lobby')
    def handle_get_rooms():
        all_rooms = [
            {"id": str(room["id"]), "name": room["room_name"]}
            for room in room_collection.find()
        ]
        emit('room_list', all_rooms)

    @socketio.on('join_room', namespace='/lobby')
    def handle_join_room(data):
        room_id = data.get('room_id')  # or 'roomId' depending on your frontend

        join_room(room_id)

    @socketio.on('page_ready', namespace='/lobby')
    def handle_page_ready(data):
        room_id = data.get('room_id')
        page = data.get('page')
        if page == 'create_lobby':
            handle_get_rooms()
            return

        if page == 'team_select' and room_id:
            auth_token = request.cookies.get('auth_token')
            user = user_collection.find_one({'auth_token': hash_token(auth_token)})
            if not user:
                print('User not found or not logged in')
                return

            username = user['username']

            # 🔥 Disconnect cleanup for the same user (see next section)
            for sid, name in list(connected_users.items()):
                if name == username:
                    connected_users.pop(sid)

            connected_users[request.sid] = username
            join_room(room_id)  # <-- 🔥 this is the missing key!

            room = room_collection.find_one({"id": room_id})
            if not room:
                print(f"Room {room_id} does not exist")
                return

            if username not in room["red_team"] + room["blue_team"] + room["no_team"]:
                room_collection.update_one(
                    {"id": room_id},
                    {"$push": {"no_team": username}}
                )

            updated = room_collection.find_one({"id": room_id})
            emit('team_red_list', updated["red_team"], room=room_id)
            emit('team_blue_list', updated["blue_team"], room=room_id)
            emit('no_team_list', updated["no_team"], room=room_id)

    @socketio.on('join_team', namespace='/lobby')
    def handle_join_team(data):
        team = data.get('team')
        room_id = data.get('room_id')

        auth_token = request.cookies.get('auth_token')
        if not auth_token:
            print('[JOIN_TEAM] Not logged in, no auth_token')
            return

        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            print('[JOIN_TEAM] User not found')
            return

        username = user['username']
        room = room_collection.find_one({"id": room_id})
        if not room:
            print(f"[JOIN_TEAM] Room {room_id} not found")
            return

        print(f"[JOIN_TEAM] {username} joining {team} in room {room_id}")

        # Remove from all teams
        room_collection.update_one(
            {"id": room_id},
            {"$pull": {
                "red_team": username,
                "blue_team": username,
                "no_team": username
            }}
        )

        # Add to selected team
        if team == "red":
            room_collection.update_one({"id": room_id}, {"$push": {"red_team": username}})
        elif team == "blue":
            room_collection.update_one({"id": room_id}, {"$push": {"blue_team": username}})
        else:
            room_collection.update_one({"id": room_id}, {"$push": {"no_team": username}})

        # Ensure socket joins the room
        join_room(room_id)

        # Emit updated teams
        updated = room_collection.find_one({"id": room_id})
        emit('team_red_list', updated["red_team"], room=room_id)
        emit('team_blue_list', updated["blue_team"], room=room_id)
        emit('no_team_list', updated["no_team"], room=room_id)
        emit('joined_team', {'room_id': room_id, 'team': team}, to=request.sid)

    @socketio.on('start_game', namespace='/lobby')
    def handle_start_game(data):
        room_id = data.get('room_id')
        player = data.get('player')

        print('Room id', room_id)
        print('Player:', player)

        if not room_id or not player:
            print("[ERROR] Missing room_id or player in start_game")
            return

        room = room_collection.find_one({'id': room_id})
        if not room:
            print(f"[ERROR] Room '{room_id}' not found")
            return

        if room.get('owner') != player:
            print(f"[ERROR] {player} is not the owner and cannot start the game")
            return
        
        no_team_players = room.get('no_team', [])

        if no_team_players:
            print(f"[KICK] Removing players with no team: {no_team_players}")
            room_collection.update_one(
                {'id': room_id},
                {'$set': {'no_team': []}}  # clear the no_team list
            )
            updated = room_collection.find_one({"id": room_id})
            emit('team_red_list', updated["red_team"], room=room_id)
            emit('team_blue_list', updated["blue_team"], room=room_id)
            emit('no_team_list', updated["no_team"], room=room_id)

        print(f"[START_GAME] {player} is the owner. Adding all players...")

        all_players = room.get('red_team', []) + room.get('blue_team', []) 

        for username in all_players:
            player_exists = any(p['id'] == username for p in room.get('players', []))

            if not player_exists:
                if username in room.get('red_team', []):
                    spawn_x, spawn_y = 97, 2
                    team = 'red'
                elif username in room.get('blue_team', []):
                    spawn_x, spawn_y = 2, 97
                    team = 'blue'
                else:
                    spawn_x, spawn_y = 50, 50
                    team = 'no_team'

                print(f"[START_GAME] Adding {username} ({team}) to battlefield.")

                room_collection.update_one(
                    {'id': room_id},
                    {'$push': {'players': {
                        'id': username,
                        'x': spawn_x,
                        'y': spawn_y,
                        'team': team
                    }}}
                )
            else:
                print(f"[START_GAME] {username} already exists.")

        join_room(room_id)

        updated_room = room_collection.find_one({'id': room_id})
        emit('player_positions', updated_room['players'], room=room_id)
        # ✅ Now only emit 'game_started' to players actually in the battlefield
        for player in updated_room['players']:
            sid = get_sid(player['id'])
            if sid:
                socketio.emit('game_started', {'msg': 'The game has started!'}, to=sid)

    @socketio.on('disconnect', namespace='/lobby')
    def handle_disconnect():
        sid = request.sid
        username = connected_users.pop(sid, None)

        if not username:
            print(f"[DISCONNECT] SID {sid} not found in connected_users")
            return

        print(f"[DISCONNECT] Cleaning up user {username}")

        # ✅ 1. First, find rooms BEFORE you modify the DB
        rooms = list(room_collection.find({
            "$or": [
                {"red_team": username},
                {"blue_team": username},
                {"no_team": username},
            ]
        }))

        # ✅ 2. Then remove the user
        room_collection.update_many(
            {"id": {"$in": [r["id"] for r in rooms]}},
            {"$pull": {
                "red_team": username,
                "blue_team": username,
                "no_team": username,
            }}
        )

        # ✅ 3. Emit to all rooms the user was in
        for room in rooms:
            room_id = room["id"]
            updated = room_collection.find_one({"id": room_id})
            print(f"[DISCONNECT] Emitting team updates for room {room_id}")
            socketio.emit('team_red_list', updated["red_team"], room=room_id)
            socketio.emit('team_blue_list', updated["blue_team"], room=room_id)
            socketio.emit('no_team_list', updated["no_team"], room=room_id)

        print(f"[DISCONNECT] {username} removed from all rooms.")

    @socketio.on('connect', namespace='/lobby')
    def handle_connect():
        page = request.args.get('page')
        room_id = request.args.get('room_id')
        print(f"[CONNECT] {request.sid} connected from page: {page}, room: {room_id}")