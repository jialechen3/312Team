import uuid

from flask_socketio import emit, join_room
from flask import request
from util.auth import hash_token
from bson import ObjectId

def register_room_handlers(socketio, user_collection, room_collection):

    @socketio.on('create_room')
    def handle_create_room(room_name):
        room_id = str(uuid.uuid4())  # generate unique ID
        new_room = {
            "id": room_id,
            "room_name": room_name,
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

    @socketio.on('get_rooms')
    def handle_get_rooms():
        all_rooms = [
            {"id": str(room["id"]), "name": room["room_name"]}
            for room in room_collection.find()
        ]
        emit('room_list', all_rooms)

    @socketio.on('join_room')
    def handle_join_room(room_name):
        join_room(room_name)
        emit('message', f"A new player joined room '{room_name}'", room=room_name)

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
            room = room_collection.find_one({"id": room_id})
            if not room:
                print(f"Room {room_id} does not exist")
                return

            # avoid duplicates
            if username not in room["red_team"] + room["blue_team"] + room["no_team"]:
                room_collection.update_one(
                    {"id": room_id},
                    {"$push": {"no_team": username}}
                )

            updated = room_collection.find_one({"id": room_id})
            emit('team_red_list', updated["red_team"])
            emit('team_blue_list', updated["blue_team"])
            emit('no_team_list', updated["no_team"])

    @socketio.on('join_team')
    def handle_join_team(data):
        team = data.get('team')
        room_id = data.get('room_id')

        auth_token = request.cookies.get('auth_token')
        if not auth_token:
            print('Not logged in')
            return

        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            print('User not found')
            return

        username = user['username']
        room = room_collection.find_one({"id": room_id})
        if not room:
            print(f"Room {id} not found")
            return

        # Remove from all teams
        room_collection.update_one(
            {"id": room_id},
            {"$pull": {"red_team": username, "blue_team": username, "no_team": username}}
        )

        if team == "red":
            room_collection.update_one({"id": room_id}, {"$push": {"red_team": username}})
        elif team == "blue":
            room_collection.update_one({"id": room_id}, {"$push": {"blue_team": username}})
        else:
            room_collection.update_one({"id": room_id}, {"$push": {"no_team": username}})

        updated = room_collection.find_one({"id": room_id})
        emit('team_red_list', updated["red_team"])
        emit('team_blue_list', updated["blue_team"])
        emit('no_team_list', updated["no_team"])
