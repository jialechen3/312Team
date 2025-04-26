import uuid
import random

from flask_socketio import emit, join_room
from flask import request
from util.auth import hash_token
from bson import ObjectId
from util.spawn_helper import spawn_player

connected_users = {}

def register_room_handlers(socketio, user_collection, room_collection):

    @socketio.on('create_room')
    def handle_create_room(room_name):
        room_id = str(uuid.uuid4())
        auth_token = request.cookies.get('auth_token')
        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        creator_username = user['username'] if user else "unknown"
        new_room = {
        "id": room_id,
        "room_name": room_name,
        "owner": creator_username, 
        "red_team": [],
        "blue_team": [],
        "no_team": []
    }
        room_collection.insert_one(new_room)

        all_rooms = [
            {"id": str(room["id"]), "name": room["room_name"]}
            for room in room_collection.find()
        ]
        emit('room_list', all_rooms, broadcast=True)

    @socketio.on('get_rooms')
    def handle_get_rooms():
        all_rooms = [
            {"id": str(room["id"]), "name": room["room_name"]}
            for room in room_collection.find()
        ]
        emit('room_list', all_rooms)

    @socketio.on('join_room')
    def handle_join_room(data):
        room_id = data.get('room_id')
        join_room(room_id)

    @socketio.on('page_ready')
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

            for sid, name in list(connected_users.items()):
                if name == username:
                    connected_users.pop(sid)

            connected_users[request.sid] = username
            join_room(room_id)

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

    @socketio.on('join_team')
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

        room_collection.update_one(
            {"id": room_id},
            {"$pull": {
                "red_team": username,
                "blue_team": username,
                "no_team": username
            }}
        )

        if team == "red":
            room_collection.update_one({"id": room_id}, {"$push": {"red_team": username}})
        elif team == "blue":
            room_collection.update_one({"id": room_id}, {"$push": {"blue_team": username}})
        else:
            room_collection.update_one({"id": room_id}, {"$push": {"no_team": username}})

        join_room(room_id)

        # ✅ Assign spawn location
        if team == "red":
            spawn_x = random.randint(97, 99)
            spawn_y = random.randint(0, 2)
        elif team == "blue":
            spawn_x = random.randint(0, 2)
            spawn_y = random.randint(97, 99)
        else:
            spawn_x = random.randint(10, 90)
            spawn_y = random.randint(10, 90)

        player_in_room = any(p['id'] == username for p in room.get('players', []))
        if not player_in_room:
            room_collection.update_one(
                {"id": room_id},
                {"$push": {"players": {"id": username, "x": spawn_x, "y": spawn_y}}}
            )

        updated = room_collection.find_one({"id": room_id})
        emit('team_red_list', updated["red_team"], room=room_id)
        emit('team_blue_list', updated["blue_team"], room=room_id)
        emit('no_team_list', updated["no_team"], room=room_id)
        emit('player_positions', updated['players'], room=room_id)
        emit('joined_team', {'room_id': room_id, 'team': team}, to=request.sid)

    @socketio.on('start_game')
    def handle_start_game(data):
        room_id = data.get('room_id')
        player = data.get('player')
        print('Room id', room_id)
        print('Player list', player)
        if not room_id or not player:
            print("[ERROR] Missing room_id or player in start_game")
            return

        room = room_collection.find_one({'id': room_id})
        if not room:
            print(f"[ERROR] Room '{room_id}' not found")
            return

        # 🔥🔥 KEY CHANGE: Spawn player properly if they don't exist yet
        player_exists = any(p['id'] == player for p in room.get('players', []))
        if not player_exists:
            spawn_player(room_collection, room_id, player)

        join_room(room_id)
        updated = room_collection.find_one({'id': room_id})
        print("[DEBUG] Emitting player_positions:", updated['players'])
        emit('player_positions', updated['players'], room=room_id)

    @socketio.on('disconnect')
    def handle_disconnect():
        sid = request.sid
        username = connected_users.pop(sid, None)

        if not username:
            print(f"[DISCONNECT] SID {sid} not found in connected_users")
            return

        print(f"[DISCONNECT] Cleaning up user {username}")

        rooms = list(room_collection.find({
            "$or": [
                {"red_team": username},
                {"blue_team": username},
                {"no_team": username},
            ]
        }))

        room_collection.update_many(
            {"id": {"$in": [r["id"] for r in rooms]}},
            {"$pull": {
                "red_team": username,
                "blue_team": username,
                "no_team": username,
            }}
        )

        for room in rooms:
            room_id = room["id"]
            updated = room_collection.find_one({"id": room_id})
            print(f"[DISCONNECT] Emitting team updates for room {room_id}")
            socketio.emit('team_red_list', updated["red_team"], room=room_id)
            socketio.emit('team_blue_list', updated["blue_team"], room=room_id)
            socketio.emit('no_team_list', updated["no_team"], room=room_id)

        print(f"[DISCONNECT] {username} removed from all rooms.")

    @socketio.on('connect')
    def handle_connect():
        page = request.args.get('page')
        room_id = request.args.get('room_id')
        print(f"[CONNECT] {request.sid} connected from page: {page}, room: {room_id}")

