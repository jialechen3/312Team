from flask import Blueprint, render_template, request
from flask_socketio import emit, join_room
from util.auth import hash_token
import time
from util.rooms import choose_avatar

# Constants for map size
MAP_WIDTH = 100
MAP_HEIGHT = 100

terrain = [[0 for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]

# Global memory
room_player_data = {}  # { room_id: { player_name: {"x": int, "y": int, "team": str} } }
player_status = {}     # { room_id: { player_name: "alive" or "dead" } }

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
        player = data.get('player')
        direction = data.get('direction')

        if not room_id or not player or not direction:
            print("[❌] Missing move data")
            return

        room = room_collection.find_one({'id': room_id})
        if not room:
            print(f"[❌] Room {room_id} not found")
            return

        # find this player's data in the DB
        player_list = room.get('players', [])
        player_data = next((p for p in player_list if p['id'] == player), None)
        if not player_data:
            print(f"[❌] Player {player} not found in room {room_id}")
            return

        # Prevent dead players from moving
        if player_status.get(room_id, {}).get(player, {}).get('status') == "dead":
            print(f"[BLOCKED] {player} tried to move while dead")
            return

        # compute new position
        x, y = player_data['x'], player_data['y']
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

        # bounds & terrain check
        if not (0 <= new_x < MAP_WIDTH and 0 <= new_y < MAP_HEIGHT):
            print(f"[❌] Move out of bounds ({new_x}, {new_y})")
            return
        if terrain[new_y][new_x] == 1:
            print(f"[❌] Blocked by wall at ({new_x}, {new_y})")
            return

        # write move into MongoDB
        result = room_collection.update_one(
            {'id': room_id, 'players.id': player},
            {'$set': {'players.$.x': new_x, 'players.$.y': new_y}}
        )
        if result.matched_count == 0:
            print(f"[❌] Failed to update {player}'s position")
            return

        # refresh in-memory positions
        updated_room = room_collection.find_one({'id': room_id})
        updated_players = updated_room.get('players', [])
        room_player_data[room_id] = {
            p['id']: {'x': p['x'], 'y': p['y']}
            for p in updated_players
            if 'id' in p and p['id'] is not None
        }
        room_doc = room_collection.find_one({"id": room_id})
        for p in updated_players:
            user_doc = user_collection.find_one({"username": p["id"]})
            p["avatar"] = choose_avatar(p["id"], room_doc, user_doc)

        # ── COLLISION / TAGGING ──
        attacking_team = room.get('attacking_team')
        if not attacking_team:
            print(f"[❌] Attacking team not set for room {room_id}")
        else:
            for other_id, pos in room_player_data[room_id].items():
                if other_id == player:
                    continue

                if abs(pos['x'] - new_x) <= 1 and abs(pos['y'] - new_y) <= 1:
                    target_data = next((p for p in updated_players if p['id'] == other_id), None)
                    if not target_data:
                        continue

                    mover_team  = player_data.get('team')
                    target_team = target_data.get('team')

                    # ✅ Make tagging symmetric
                    if mover_team == target_team:
                        continue  # same team, no tagging

                    # 🚨 Either mover or target must be attacker
                    if mover_team == attacking_team:
                        victim = other_id
                        tagger = player
                    elif target_team == attacking_team:
                        victim = player
                        tagger = other_id
                    else:
                        continue  # Neither is attacker, no tagging

                    print(f"[TAG] {tagger} (attacker) tagged {victim} (defender)")

                    emit('player_tagged', {'tagger': tagger, 'target': victim}, room=room_id)

                    # mark victim dead
                    player_status.setdefault(room_id, {})[victim] = {
                        'status': 'dead',
                        'tagger': tagger
                    }
                    socketio.start_background_task(
                        respawn_player, socketio, room_collection, room_id, victim
                    )
                    break  # only allow 1 tag per move


        # broadcast the updated positions back to everyone
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
                {"$pull": {"players": {"id": username}}
            })

            updated = room_collection.find_one({"id": room_id})
            socketio.emit('player_positions', updated.get('players', []), room=room_id, namespace='/battlefield')

        print(f"[BATTLEFIELD DISCONNECT] {username} removed from battlefield players.")
    
    #gives latest player info after respawn
    @socketio.on('request_positions', namespace='/battlefield')
    def handle_request_positions():
        auth_token = request.cookies.get('auth_token')
        if not auth_token:
            print("[REQUEST POSITIONS] No auth token")
            return

        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            print("[REQUEST POSITIONS] User not found")
            return

        username = user['username']

        # Find which room they are in
        room = room_collection.find_one({"players.id": username})
        if not room:
            print("[REQUEST POSITIONS] Room not found for", username)
            return

        room_id = room['id']
        emit('player_positions', room.get('players', []), room=request.sid, namespace='/battlefield')


def respawn_player(socketio, room_collection, room_id, player):
    print(f"[WAITING] Respawn timer started for {player}")
    time.sleep(5)  # 5 seconds dead

    if room_id not in player_status or player not in player_status[room_id]:
        print(f"[RESPAWN ERROR] Player {player} status not found")
        return

    tagger = player_status[room_id][player].get('tagger')

    # Fetch the tagger's team
    room = room_collection.find_one({'id': room_id})
    if not room:
        print(f"[RESPAWN ERROR] Room {room_id} not found")
        return

    tagger_data = next((p for p in room.get('players', []) if p['id'] == tagger), None)
    if not tagger_data:
        print(f"[RESPAWN ERROR] Tagger {tagger} not found in room")
        return

    new_team = tagger_data['team']
    print(f"[RESPAWN] {player} will switch to team {new_team}")

    # Update the player's team in database
    room_collection.update_one(
        {"id": room_id, "players.id": player},
        {"$set": {"players.$.team": new_team}}
    )

    # Mark as alive
    player_status[room_id][player] = {
        "status": "alive"
    }

    # Tell clients
    socketio.emit('player_respawned', {"player": player}, room=room_id, namespace='/battlefield')


# Blueprint
battlefield_bp = Blueprint('battlefield', __name__)

@battlefield_bp.route('/battlefield')
def battlefield():
    room_id = request.args.get('room')
    if not room_id:
        return "Missing room ID", 400
    return render_template('battlefield.html', room_id=room_id)
