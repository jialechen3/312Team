import random

def spawn_player(room_collection, room_id, player_name):
    room = room_collection.find_one({"id": room_id})
    if not room:
        print(f"[SPAWN] Room {room_id} not found!")
        return None  # important: caller must check this

    # Determine team
    team = None
    if player_name in room.get("red_team", []):
        team = "red_team"
    elif player_name in room.get("blue_team", []):
        team = "blue_team"
    else:
        team = "no_team"

    # Determine spawn coordinates based on team
    if team == "red_team":
        spawn_x = random.randint(97, 99)
        spawn_y = random.randint(0, 2)
    elif team == "blue_team":
        spawn_x = random.randint(0, 2)
        spawn_y = random.randint(97, 99)
    else:
        spawn_x = random.randint(10, 90)
        spawn_y = random.randint(10, 90)

    print(f"[SPAWN] {player_name} spawns at ({spawn_x},{spawn_y}) for {team}")

    # Update players array
    room_collection.update_one(
        {"id": room_id},
        {"$push": {"players": {"id": player_name, "x": spawn_x, "y": spawn_y}}}
    )

    return {"id": player_name, "x": spawn_x, "y": spawn_y}