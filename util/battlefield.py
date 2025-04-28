from flask import Blueprint, render_template, request
from flask_socketio import emit, join_room
from util.auth import hash_token
import time
from util.rooms import choose_avatar

# Constants for map size
MAP_WIDTH = 100
MAP_HEIGHT = 100

terrain = [[0 for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]

for y in range(MAP_HEIGHT):
    for x in range(MAP_WIDTH):
        if y < 5 and x >= MAP_WIDTH - 5:
            inside = (x >= MAP_WIDTH - 4 and x <= MAP_WIDTH - 2) and (y >= 1 and y <= 3)
            terrain[y][x] = 0 if inside else 3  # red base walls
        elif y >= MAP_HEIGHT - 5 and x < 5:
            terrain[y][x] = 2  # blue base walls
        elif (x + y) % 17 == 0 and 5 < x < MAP_WIDTH - 6 and 5 < y < MAP_HEIGHT - 6:
            terrain[y][x] = 1  # scattered maze walls

# Global memory
room_player_data = {}  # { room_id: { player_name: {"x": int, "y": int, "team": str} } }
player_status = {}     # { room_id: { player_name: "alive" or "dead" } }

def register_battlefield_handlers(socketio, user_collection, room_collection):

    @socketio.on('connect', namespace='/battlefield')
    def handle_battlefield_connect():
        print('Client connected to battlefield')

    @socketio.on('join_room', namespace='/battlefield')
    def handle_battlefield_join_room(data):
        room_id = data.get('room_id')
        player_id = data.get('player')

        if room_id:
            join_room(room_id)

            # 🔥 Immediately emit the current player positions after joining
            room = room_collection.find_one({"id": room_id})
            if not room:
                return

            players = room.get('players', [])
            updated_players = []

            room_doc = room_collection.find_one({"id": room_id})

            for p in players:
                user_doc = user_collection.find_one({"username": p["id"]})
                p["avatar"] = choose_avatar(p["id"], room_doc, user_doc)
                updated_players.append(p)

            emit('player_positions', updated_players, room=request.sid, namespace='/battlefield')
            terrain_data = room.get('terrain')
            if terrain_data:
                emit('load_terrain', {'terrain': terrain_data}, room=request.sid, namespace='/battlefield')


    @socketio.on('move', namespace='/battlefield')
    def handle_move(data):
        room_id = data.get('roomId')
        player = data.get('player')
        direction = data.get('direction')

        if not room_id or not player or not direction:
            return

        room = room_collection.find_one({'id': room_id})
        if not room:
            return

        # find this player's data in the DB
        player_list = room.get('players', [])
        player_data = next((p for p in player_list if p['id'] == player), None)
        if not player_data:
            return

        # Prevent dead players from moving
        if player_status.get(room_id, {}).get(player, {}).get('status') == "dead":
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
            return

        # bounds & terrain check
        if not (0 <= new_x < MAP_WIDTH and 0 <= new_y < MAP_HEIGHT):
            return

        room = room_collection.find_one({'id': room_id})
        terrain = room.get('terrain', [[0] * 100 for _ in range(100)])  # fallback if missing
        tile = terrain[new_y][new_x]
        emit('terrain_data', terrain, room=room_id, namespace='/battlefield')
        if tile == 1:
            return
        elif tile == 2 and player_data.get('team') != 'blue':
            return
        elif tile == 3 and player_data.get('team') != 'red':
            return

        # write move into MongoDB
        result = room_collection.update_one(
            {'id': room_id, 'players.id': player},
            {'$set': {'players.$.x': new_x, 'players.$.y': new_y}}
        )
        if result.matched_count == 0:
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
            print()
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

                    if player_status.get(room_id, {}).get(victim, {}).get('status') == 'dead':
                        continue
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

        auth_token = request.cookies.get('auth_token')
        if not auth_token:
            return

        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            return

        username = user['username']


        rooms = list(room_collection.find({"players.id": username}))

        for room in rooms:
            room_id = room["id"]
            room_collection.update_one(
                {"id": room_id},
                {"$pull": {"players": {"id": username}}
            })

            updated = room_collection.find_one({"id": room_id})
            socketio.emit('player_positions', updated.get('players', []), room=room_id, namespace='/battlefield')


    #gives latest player info after respawn
    @socketio.on('request_positions', namespace='/battlefield')
    def handle_request_positions():
        auth_token = request.cookies.get('auth_token')
        if not auth_token:
            return

        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            return

        username = user['username']

        # Find which room they are in
        room = room_collection.find_one({"players.id": username})
        if not room:
            return

        room_id = room['id']
        emit('player_positions', room.get('players', []), room=request.sid, namespace='/battlefield')


def respawn_player(socketio, room_collection, room_id, player):
    time.sleep(5)  # 5 seconds dead

    if room_id not in player_status or player not in player_status[room_id]:
        return

    tagger = player_status[room_id][player].get('tagger')

    # Fetch the tagger's team
    room = room_collection.find_one({'id': room_id})
    if not room:
        return

    tagger_data = next((p for p in room.get('players', []) if p['id'] == tagger), None)
    if not tagger_data:
        return

    new_team = tagger_data['team']

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
