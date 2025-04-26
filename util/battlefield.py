from flask import Blueprint, render_template, request
from flask_socketio import emit
import time
# Global memory for tracking players for improved speed without hitting the database everytime
room_player_data = {}  # { room_id: { player_name: {"x": int, "y": int} } }
player_status = {} # { room_id: { player_name: "alive" or "dead" } }

def register_battlefield_handlers(socketio, user_collection, room_collection):

    @socketio.on('move')
    def handle_move(data):
        print("[SOCKET] move event received:", data)
        room_id = data.get('roomId')
        player = data.get('player')
        new_x = data['x']
        new_y = data['y']

        print(f"[MOVE] {player} -> ({new_x}, {new_y})")

        # --- Block movement if player is dead ---
        if room_id in player_status and player in player_status[room_id]:
            if player_status[room_id][player] == "dead":
                print(f"[BLOCKED] {player} tried to move while dead")
                return

        # --- Update in-memory player position tracking ---
        if room_id not in room_player_data:
            room_player_data[room_id] = {}

        room_player_data[room_id][player] = {"x": new_x, "y": new_y}

        # --- Check for collisions and possible tagging ---
        for other_player, pos in room_player_data[room_id].items():
            if other_player == player:
                continue  # Skip checking yourself
            if abs(pos["x"] - new_x) <= 1 and abs(pos["y"] - new_y) <= 1:
                print(f"[TAG] {player} tagged {other_player}!")
                emit('player_tagged', {
                    "tagger": player,
                    "target": other_player
                }, room=room_id)

                # Mark as dead
                if room_id not in player_status:
                    player_status[room_id] = {}
                player_status[room_id][other_player] = "dead"

                # Start a background task to respawn after 5 seconds
                socketio.start_background_task(respawn_player, socketio, room_id, other_player)
                break  # Only one tag per move

        # --- Update MongoDB ---
        result = room_collection.update_one(
            {'id': room_id, 'players.id': player},
            {'$set': {'players.$.x': new_x, 'players.$.y': new_y}}
        )

        if result.matched_count == 0:
            print(f"[❌] No match found for {player} in room {room_id} — not updating")

        # --- Broadcast updated positions to everyone in room ---
        updated = room_collection.find_one({'id': room_id})
        print(f"[🧍 Updated players]: {updated.get('players', [])}")

        emit('player_positions', updated['players'], room=room_id)

    def respawn_player(socketio, room_id, player):
        print(f"[WAITING] Respawn timer started for {player}")
        time.sleep(5)  # Wait for 5 seconds
        if room_id in player_status and player in player_status[room_id]:
            player_status[room_id][player] = "alive"
            print(f"[RESPAWN] {player} is now alive again!")
            # Optionally, you can notify the client:
            socketio.emit('player_respawned', {"player": player}, room=room_id)


battlefield_bp = Blueprint('battlefield', __name__)

@battlefield_bp.route('/battlefield')
def battlefield():
    room_id = request.args.get('room')
    if not room_id:
        return "Missing room ID", 400
    return render_template('battlefield.html', room_id=room_id)

