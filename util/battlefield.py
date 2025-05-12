from flask import Blueprint, render_template, request
from flask_socketio import emit, join_room
from util.auth import hash_token
from eventlet import sleep
from eventlet.semaphore import Semaphore
import math
from util.rooms import choose_avatar

# Constants for map size
MAP_WIDTH = 50
MAP_HEIGHT = 50

terrain = [[0 for _ in range(MAP_WIDTH)] for _ in range(MAP_HEIGHT)]

for y in range(MAP_HEIGHT):
    for x in range(MAP_WIDTH):
        if y < 4 and x >= MAP_WIDTH - 4:
            inside = (x >= MAP_WIDTH - 3 and x <= MAP_WIDTH - 2) and (y >= 1 and y <= 2)
            terrain[y][x] = 0 if inside else 3  # red base walls
        elif y >= MAP_HEIGHT - 4 and x < 4:
            terrain[y][x] = 2  # blue base walls
        elif (x + y) % 11 == 0 and 3 < x < MAP_WIDTH - 4 and 3 < y < MAP_HEIGHT - 4:
            terrain[y][x] = 1  # scattered maze walls


# Global memory
room_player_data = {}  # { room_id: { player_name: {"x": int, "y": int, "team": str} } }
player_status = {}     # { room_id: { player_name: "alive" or "dead", x: x coord, y: y coord } }
room_player_data_lock = Semaphore()
player_status_lock = Semaphore()

room_cache = {}        # { room_id: full_room_doc }
terrain_cache = {}     # { room_id: terrain 2D array }
room_cache_lock = Semaphore()

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
            room = get_room(room_id, room_collection)
            if not room:
                return

            players = room.get('players', [])
            updated_players = []

            for p in players:
                user_doc = user_collection.find_one({"username": p["id"]})
                p["avatar"] = choose_avatar(p["id"], room, user_doc)
                updated_players.append(p)

            refresh_room_player_data(room_id,room)
            emit('player_positions', updated_players, room=request.sid, namespace='/battlefield')
            terrain_data = terrain_cache.get(room_id)
            if terrain_data:
                emit('load_terrain', {'terrain': terrain_data}, room=request.sid, namespace='/battlefield')

    @socketio.on('move', namespace='/battlefield')
    def handle_move(data):
        room_id = data.get('roomId')
        player = data.get('player')
        keyPress = data.get('direction')

        if not room_id or not player or not keyPress:
            return

        room = get_room(room_id, room_collection)
        if not room:
            return

        # fetch once
        '''terrain = room.get('terrain', [[0] * MAP_WIDTH for _ in range(MAP_HEIGHT)])
        player_list = room.get('players', [])
        player_data = next((p for p in player_list if p['id'] == player), None)
        if not player_data:
            return'''

        with player_status_lock:
            if player_status.get(room_id, {}).get(player, {}).get('status') == "dead":
                return

        with room_player_data_lock:
            pdata = room_player_data.get(room_id, {}).get(player)
            if not pdata:
                return
            new_x, new_y = pdata['x'], pdata['y']


        # movement logic
        #new_x, new_y = player_data['x'], player_data['y']
        if keyPress['ArrowUp']:
            new_y = round((new_y - 0.1)*100)/100
        if keyPress['ArrowDown']:
            new_y = round((new_y + 0.1)*100)/100
        if keyPress['ArrowLeft']:
            new_x = round((new_x - 0.1)*100)/100
        if keyPress['ArrowRight']:
            new_x = round((new_x + 0.1)*100)/100

        x_check, y_check = False, False
        if not 0 <= new_x <= MAP_WIDTH-1:
            new_x = clamp(new_x, 0, MAP_WIDTH-1)
            x_check = True
        if not 0 <= new_y <= MAP_HEIGHT-1:
            new_y = clamp(new_y, 0, MAP_HEIGHT-1)
            y_check = True
        if x_check and y_check:
            return

        terrain = terrain_cache.get(room_id)
        if not terrain:
            return

        f_new_x = math.floor(new_x)
        c_new_x = math.ceil(new_x) if new_x % 1 != 0 else f_new_x
        f_new_y = math.floor(new_y)
        c_new_y = math.ceil(new_y) if new_y % 1 != 0 else f_new_y



        tileTL = terrain[f_new_y][f_new_x]
        tileTR = terrain[f_new_y][c_new_x]
        tileBL = terrain[c_new_y][f_new_x]
        tileBR = terrain[c_new_y][c_new_x]

        #old_x = new_x
        enemy_team_num = 3 if pdata.get('team') == 'blue' else 2

        if new_x != pdata['x'] and f_new_x != c_new_x:
            if new_x < pdata['x']:
                if (tileTL in (1, enemy_team_num)) or (tileBL in (1, enemy_team_num)):
                    new_x = pdata['x']
            elif new_x > pdata['x']:
                if (tileTR in (1, enemy_team_num)) or (tileBR in (1, enemy_team_num)):
                    new_x = pdata['x']

        if new_y != pdata['y'] and f_new_y != c_new_y:
            if new_y > pdata['y']:
                if (tileBL in (1, enemy_team_num)) or (tileBR in (1, enemy_team_num)):
                    new_y = pdata['y']
            elif new_y < pdata['y']:
                if (tileTL in (1, enemy_team_num)) or (tileTR in (1, enemy_team_num)):
                    new_y = pdata['y']

        if new_x != pdata['x'] or new_y != pdata['y']:
            room_collection.update_one(
                {'id': room_id, 'players.id': player},
                {'$set': {'players.$.x': new_x, 'players.$.y': new_y}}
            )
            invalidate_room_cache(room_id)
            updated_room = get_room(room_id, room_collection)
            refresh_room_player_data(room_id, updated_room)

            emit('player_moved', {'id': player, 'x': new_x, 'y': new_y}, room=room_id, namespace='/battlefield')

            # tagging logic
            attacking_team = updated_room.get('attacking_team')
            if attacking_team:
                for other_id, pos in room_player_data[room_id].items():
                    if other_id == player:
                        continue
                    if abs(pos['x'] - new_x) <= 1 and abs(pos['y'] - new_y) <= 1:
                        target = next((p for p in room['players'] if p['id'] == other_id), None)
                        if not target:
                            continue

                        if pdata['team'] == target['team']:
                            continue

                        if pdata['team'] == attacking_team:
                            victim, tagger = other_id, player
                        elif target['team'] == attacking_team:
                            victim, tagger = player, other_id
                        else:
                            continue

                        with player_status_lock:
                            if player_status.get(room_id, {}).get(victim, {}).get('status') == 'dead':
                                continue
                            player_status.setdefault(room_id, {})[victim] = {'status': 'dead', 'tagger': tagger}
                        emit('player_tagged', {'tagger': tagger, 'target': victim}, room=room_id)
                        socketio.start_background_task(respawn_player, socketio, room_collection, room_id, victim)
                        break


    @socketio.on('disconnect', namespace='/battlefield')
    def handle_battlefield_disconnect():
        auth_token = request.cookies.get('auth_token')
        if not auth_token:
            return

        user = user_collection.find_one({'auth_token': hash_token(auth_token)})
        if not user:
            return

        username = user['username']
        rooms = list(room_collection.find({"players.id": username}))

        for room_id, room in list(room_cache.items()):
            if any(p['id'] == username for p in room.get('players', [])):
                room_collection.update_one(
                    {"id": room_id},
                    {"$pull": {"players": {"id": username}}}
                )
                invalidate_room_cache(room_id)
                socketio.emit('player_left', {'id': username}, room=room_id, namespace='/battlefield')
                break

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
        for room_id, players in room_player_data.items():
            if username in players:
                room = get_room(room_id, room_collection)
                if room:
                    emit('player_positions', room.get('players', []), room=request.sid, namespace='/battlefield')
                break


def respawn_player(socketio, room_collection, room_id, player):
    sleep(5)
    with player_status_lock:
        tagger = player_status.get(room_id, {}).get(player, {}).get('tagger')

    room = get_room(room_id, room_collection)
    if not room:
        return

    tagger_data = next((p for p in room.get('players', []) if p['id'] == tagger), None)
    if not tagger_data:
        return

    new_team = tagger_data['team']
    room_collection.update_one(
        {"id": room_id, "players.id": player},
        {"$set": {"players.$.team": new_team}}
    )
    invalidate_room_cache(room_id)
    updated_room = get_room(room_id, room_collection)
    refresh_room_player_data(room_id, updated_room)

    with player_status_lock:
        player_status[room_id][player] = {"status": "alive"}

    socketio.emit('player_positions', updated_room.get('players', []), room=room_id, namespace='/battlefield')
    socketio.emit('player_respawned', {"player": player}, room=room_id, namespace='/battlefield')


# Blueprint
battlefield_bp = Blueprint('battlefield', __name__)

@battlefield_bp.route('/battlefield')
def battlefield():
    room_id = request.args.get('room')
    if not room_id:
        return "Missing room ID", 400
    return render_template('battlefield.html', room_id=room_id)

def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))

def get_room(room_id, room_collection):
    with room_cache_lock:
        if room_id in room_cache:
            return room_cache[room_id]
        room = room_collection.find_one({"id": room_id})
        if room:
            room_cache[room_id] = room
            if "terrain" in room:
                terrain_cache[room_id] = room["terrain"]
        return room

def refresh_room_player_data(room_id, room):
    with room_player_data_lock:
        room_player_data[room_id] = {
            p['id']: {"x": p['x'], "y": p['y'], "team": p.get('team')} for p in room.get("players", [])
        }

def invalidate_room_cache(room_id):
    with room_cache_lock:
        if room_id in room_cache:
            del room_cache[room_id]
        if room_id in terrain_cache:
            del terrain_cache[room_id]