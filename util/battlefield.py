from flask import Blueprint, render_template, request
from flask_socketio import emit


def register_battlefield_handlers(socketio, user_collection, room_collection):



    @socketio.on('move')
    def handle_move(data):
        print("[SOCKET] move event received:", data)
        room_id = data.get('roomId')
        player = data.get('player')
        new_x = data['x']
        new_y = data['y']

        print(f"[MOVE] {player} -> ({new_x}, {new_y})")

        result = room_collection.update_one(
            {'id': room_id, 'players.id': player},
            {'$set': {'players.$.x': new_x, 'players.$.y': new_y}}
        )

        if result.matched_count == 0:
            print(f"[❌] No match found for {player} in room {room_id} — not updating")

        updated = room_collection.find_one({'id': room_id})
        print(f"[🧍 Updated players]: {updated.get('players', [])}")

        emit('player_positions', updated['players'], room=room_id)


battlefield_bp = Blueprint('battlefield', __name__)

@battlefield_bp.route('/battlefield')
def battlefield():
    room_id = request.args.get('room')
    if not room_id:
        return "Missing room ID", 400
    return render_template('battlefield.html', room_id=room_id)

