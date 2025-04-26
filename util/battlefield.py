from flask import Blueprint, render_template, request
from flask_socketio import emit, join_room
from util.auth import hash_token

# Constants for map size
MAP_WIDTH = 100
MAP_HEIGHT = 100

terrain = [[0 for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]

def register_battlefield_handlers(socketio, user_collection, room_collection):

    @socketio.on('connect', namespace='/battlefield')
    def handle_battlefield_connect():
        print(f"[BATTLEFIELD CONNECT] SID {request.sid} connected to battlefield")

    @socketio.on('join_room', namespace='/battlefield')
    def handle_battlefield_join_room(data):
        room_id = data.get('room_id')
        player_id = data.get('player')

        if room_id:
            print(f"[BATTLEFIELD JOIN] {player_id} joining room {room_id}")
            join_room(room_id)


    @socketio.on('move', namespace='/battlefield')
    def handle_move(data):
        print("[BATTLEFIELD SOCKET] move event received:", data)
        room_id = data.get('roomId')
        player_id = data.get('player')
        direction = data.get('direction')

        if not room_id or not player_id or not direction:
            print("[❌] Missing move data")
            return

        room = room_collection.find_one({'id': room_id})
        if not room:
            print(f"[❌] Room {room_id} not found")
            return

        player_list = room.get('players', [])
        player = next((p for p in player_list if p['id'] == player_id), None)
        if not player:
            print(f"[❌] Player {player_id} not found in room {room_id}")
            return

        x, y = player['x'], player['y']

        if direction == 'up':
            new_x, new_y = x, y - 1
        elif direction == 'down':
            new_x, new_y = x, y + 1
        elif direction == 'left':
            new_x, new_y = x - 1, y
        elif direction == 'right':
            new_x, new_y = x + 1, y
        else:
            print(f"[❌] Invalid direction {direction}")
            return

        if not (0 <= new_x < MAP_WIDTH and 0 <= new_y < MAP_HEIGHT):
            print(f"[❌] Move out of bounds ({new_x}, {new_y})")
            return

        if terrain[new_y][new_x] == 1:
            print(f"[❌] Blocked by wall at ({new_x}, {new_y})")
            return

        result = room_collection.update_one(
            {'id': room_id, 'players.id': player_id},
            {'$set': {'players.$.x': new_x, 'players.$.y': new_y}}
        )

        if result.matched_count == 0:
            print(f"[❌] Failed to update {player_id}'s position")
            return

        updated_room = room_collection.find_one({'id': room_id})
        updated_players = updated_room.get('players', [])
        print(f"[🧍 Updated players]: {updated_players}")

        emit('player_positions', updated_players, room=room_id, namespace='/battlefield')

    @socketio.on('disconnect', namespace='/battlefield')
    def handle_battlefield_disconnect():
        sid = request.sid
        print(f"[BATTLEFIELD DISCONNECT] SID {sid} disconnected")

        auth_token = request.cookies.get('auth_token')
        if not auth_token:
            print("[BATTLEFIELD DISCONNECT] No auth token, skipping")
            return

        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            print("[BATTLEFIELD DISCONNECT] User not found from auth token")
            return

        username = user['username']

        print(f"[BATTLEFIELD DISCONNECT] Cleaning up player {username}")

        rooms = list(room_collection.find({"players.id": username}))

        for room in rooms:
            room_id = room["id"]
            room_collection.update_one(
                {"id": room_id},
                {"$pull": {"players": {"id": username}}}
            )

            updated = room_collection.find_one({"id": room_id})
            socketio.emit('player_positions', updated.get('players', []), room=room_id, namespace='/battlefield')

        print(f"[BATTLEFIELD DISCONNECT] {username} removed from battlefield players.")

battlefield_bp = Blueprint('battlefield', __name__)

@battlefield_bp.route('/battlefield')
def battlefield():
    room_id = request.args.get('room')
    if not room_id:
        return "Missing room ID", 400
    return render_template('battlefield.html', room_id=room_id)
