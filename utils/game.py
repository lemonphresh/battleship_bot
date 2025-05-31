import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

# Constants
DATA_DIR = Path("data")
COOLDOWN_MINUTES = 10
SHIP_EMOJIS = {
    "carrier": "🟪",      # purple square
    "battleship": "🟥",   # red square
    "cruiser": "⬜",      # white square
    "submarine": "🟧",    # orange square
    "destroyer": "⬛"     # black square
}
WATER_EMOJI = "🟦"  # blue square for unplaced water tile

# Global cooldown tracker
last_shot_time = {}

# Utility Functions
def board_path(team):
    return os.path.join("data", f"board_{team}.json")

def load_board(team):
    path = board_path(team)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def load_tiles():
    with open(DATA_DIR / "base_tiles.json") as f:
        return json.load(f)["tiles"]

# Board Management Functions
def generate_board():
    tiles = load_tiles()
    assert len(tiles) >= 100, "Need at least 100 tiles"
    random.shuffle(tiles)
    board = {}
    rows = "ABCDEFGHIJ"

    for i in range(10):
        for j in range(10):
            coord = f"{rows[i]}{j+1}"
            board[coord] = tiles.pop()
    
    return {"tiles": board}

def all_ships_placed(board, required_ships):
    placed = set(board.get("ships", {}).keys())
    return placed == set(required_ships)

def lock_board(board, required_ships):
    if board.get("locked", False):
        return "❌ Board is already locked."
    
    if not all_ships_placed(board, required_ships):
        return "❌ Not all ships are placed yet."

    board["locked"] = True
    return "✅ Board is now locked. No further changes allowed."

def unlock_board(board):
    if not board.get("locked", False):
        return "❌ Board is not locked."
    board["locked"] = False
    return "✅ Board is now unlocked. Changes are allowed."

# Ship Placement and Removal Functions
def place_ship(board, ship_type, orientation, start_coord, ship_definitions):
    if board.get("locked", False):
        return "❌ Board is locked. Cannot place ships."
    rows = "ABCDEFGHIJ"
    orientation = orientation.lower()
    ship_type = ship_type.lower()

    if ship_type not in ship_definitions:
        return f"❌ Invalid ship type: {ship_type}"

    if ship_type in board.get("ships", {}):
        return f"❌ {ship_type.capitalize()} already placed."

    ship_tiles = ship_definitions[ship_type]
    length = len(ship_tiles)

    try:
        row_letter, col = start_coord[0].upper(), int(start_coord[1:])
        row_idx = rows.index(row_letter)
        col_idx = col - 1
    except Exception:
        return f"❌ Invalid coordinate format. Use format like A3."

    coords = []
    for i in range(length):
        r, c = row_idx, col_idx
        if orientation == "h":
            c += i
        elif orientation == "v":
            r += i
        else:
            return f"❌ Invalid orientation: {orientation}. Use 'h' for horizontal or 'v' for vertical."

        if r >= 10 or c >= 10:
            return f"❌ {ship_type.capitalize()} would go out of bounds."

        coord = f"{rows[r]}{c+1}"
        if board["tiles"].get(coord, {}).get("ship"):
            return f"❌ Overlaps another ship at {coord}."

        coords.append(coord)

    for i, coord in enumerate(coords):
        original_tile = board["tiles"][coord].copy()
        board["tiles"][coord] = {
            **ship_tiles[i],
            "ship": ship_type,
            "previous_tile": original_tile,
        }

    board.setdefault("ships", {})[ship_type] = coords
    direction = "horizontally" if orientation == "h" else "vertically"
    return f"✅ Placed {ship_type.capitalize()} starting at {coords[0]} going {direction}."

def remove_ship(board, ship_type):
    if board.get("locked", False):
        return "❌ Board is locked. Cannot remove ships."
    ship_type = ship_type.lower()
    if "ships" not in board or ship_type not in board["ships"]:
        return f"❌ {ship_type.capitalize()} is not placed."

    for coord in board["ships"][ship_type]:
        tile = board["tiles"].get(coord, {})
        prev = tile.get("previous_tile")
        if prev:
            board["tiles"][coord] = prev
        else:
            board["tiles"][coord]["ship"] = None
            board["tiles"][coord].pop("ship_tile_data", None)

    del board["ships"][ship_type]
    return f"✅ Removed {ship_type.capitalize()}."

# File Operations for Ship Placement and Removal
def place_ship_to_file(team_name, ship_type, orientation, start_coord, ship_definitions, board_dir="data"):
    file_path = os.path.join(board_dir, f"board_{team_name}.json")

    if not os.path.exists(file_path):
        return f"❌ Board file for team '{team_name}' not found."

    with open(file_path, "r") as f:
        board = json.load(f)

    result = place_ship(board, ship_type, orientation, start_coord, ship_definitions)

    if result.startswith("✅"):
        with open(file_path, "w") as f:
            json.dump(board, f, indent=2)

    return result

def remove_ship_from_file(team_name, ship_type, board_dir="data"):
    file_path = os.path.join(board_dir, f"board_{team_name}.json")

    if not os.path.exists(file_path):
        return f"❌ Board file for team '{team_name}' not found."

    with open(file_path, "r") as f:
        board = json.load(f)

    result = remove_ship(board, ship_type)

    if result.startswith("✅"):
        with open(file_path, "w") as f:
            json.dump(board, f, indent=2)

    return result

# Shooting Functions
def can_shoot(team):
    now = datetime.now(timezone.utc)
    last = last_shot_time.get(team)
    if last and now - last < timedelta(minutes=COOLDOWN_MINUTES):
        remaining = timedelta(minutes=COOLDOWN_MINUTES) - (now - last)
        mins = remaining.seconds // 60
        secs = remaining.seconds % 60
        return False, f"🚢 Hold position! You must complete your task before unleashing another volley."
    return True, None

def already_shot(board, coord):
    return coord.upper() in board.get("shots", {})

def handle_tile_selection(selecting_team, target_coord, boards, team_channels):
    opposing_team = config.TEAM_PAIRS.get(selecting_team)
    target_board = boards[opposing_team]
    target_coord = target_coord.upper()
     
    can_shoot_result, cooldown_msg = can_shoot(selecting_team)
    if not can_shoot_result:
        return {"error": cooldown_msg}

    tile = target_board["tiles"].get(target_coord)
    if not tile:
        return {
            "error": f"❌ **{target_coord}** is impossible to hit — there's nothing there to strike, Captain! Check the map and strike between A1 and J10."
        }

    if already_shot(target_board, target_coord):
        return {
            "error": f"⚠️ **{target_coord}** has already felt the cannon's wrath! Choose a new target, sailor."
        }

    is_hit = "ship" in tile
    timestamp = datetime.now(timezone.utc).isoformat()

    target_board.setdefault("shots", {})[target_coord] = {
        "by": selecting_team,
        "hit": is_hit,
        "timestamp": timestamp,
    }
    
    last_shot_time[selecting_team] = datetime.now(timezone.utc)
    
    file_path = board_path(opposing_team)
    with open(file_path, "w") as f:
        json.dump(target_board, f, indent=2)
    
    team_selecting_channel = team_channels[selecting_team]
    team_target_channel = team_channels[opposing_team]

    print(tile)
    if is_hit:
        ship_name = tile["ship"].capitalize()
        tile_name = tile["name"]
        tile_details = tile["details"]
        tile_count = tile.get("count", 0)

        result_to_team = (
            f"💥 **Direct hit, Captain!** The enemy’s **{ship_name}** took a blow at **{target_coord}**!\n"
            f"The sea trembles with your precision. ⚓"
            f"\n\n You must vanquish **{tile_count}** **{tile_name}** to successfully damage their {ship_name}!"
        )
        if tile_details:
            result_to_team += f"\n\n📜 **Additional Details:**\n\n{tile_details}"
        result_to_opponent = (
            f"🚨 **Incoming fire from {selecting_team.upper()}!**\n"
            f"📍 Impact at **{target_coord}** — your **{ship_name}** has been struck!\n"
            f"The hull shudders under the blast... ⚠️"
        )
    else:
        tile_name = tile.get("name", "Water")
        tile_details = tile.get("details", "")
        tile_count = tile.get("count", 0)
        result_to_team = (
            f"💨 **Splashdown!** Your shot landed at **{target_coord}**, but struck only the water... "
            f"No sign of enemy steel... just the ocean’s secrets. 🌊"
            f"\n\n You must vanquish **{tile_count}** **{tile_name}** in order to be able to take another shot."
        )
        if tile_details:
            result_to_team += f"\n\n📜 **Additional Details:**\n\n{tile_details}"
        result_to_opponent = (
            f"🛡️ **{selecting_team.upper()}** opened fire at **{target_coord}**...\n"
            f"💦 The cannonball vanished beneath the waves — a clean **MISS**."
        )

    board_preview_for_selecting = render_board_with_shots(target_board, reveal_ships=False)
    board_preview_for_opponent = render_board_with_shots(boards[opposing_team], reveal_ships=True)

    return {
        "team_msg": result_to_team + "\n\n 🏴‍☠️ Avast, this is what we see through the spyglass... their waters await: \n\n" + board_preview_for_selecting,
        "opponent_msg": result_to_opponent + "\n\n 🧭 Your waters, crew — here’s how they look: \n\n" + board_preview_for_opponent,
        "team_channel": team_selecting_channel,
        "opponent_channel": team_target_channel,
    }

# Rendering Functions
def render_board_preview(board, required_ships=None):
    rows = "ABCDEFGHIJ"
    emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    emoji_letters = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]

    preview = "\n🧭 " + " ".join(emoji_numbers[:10]) + "\n"
    for i, r in enumerate(rows):
        line = f"{emoji_letters[i]} "
        for c in range(1, 11):
            coord = f"{r}{c}"
            tile = board["tiles"].get(coord, {})
            if tile.get("name") == "Wreckage":
                line += "💥 " 
            elif tile.get("event") == "kraken":
                line += "🐙 "  
            elif tile.get("ship"):
                ship_type = tile["ship"]
                emoji = SHIP_EMOJIS.get(ship_type, "❓")
                line += emoji + " "
            else:
                line += WATER_EMOJI + " "
        preview += line + "\n"

    if not board.get("locked", False) and required_ships:
        placed_ships = set(board.get("ships", {}).keys())
        remaining_ships = set(required_ships) - placed_ships
        if remaining_ships:
            preview += "\nRemaining ships to place: **" + ", ".join(remaining_ships) + "**"

    return preview

def render_board_with_shots(board, reveal_ships=False):
    rows = "ABCDEFGHIJ"
    emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    emoji_letters = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]
    shots = board.get("shots", {})

    preview = "\n🧭 " + " ".join(emoji_numbers[:10]) + "\n"
    for i, r in enumerate(rows):
        line = f"{emoji_letters[i]} "
        for c in range(1, 11):
            coord = f"{r}{c}"
            tile = board["tiles"].get(coord, {})
            shot = shots.get(coord)

            if shot:
                if shot["hit"]:
                    line += "💥 "  # hit marker
                else:
                    line += "⚫ "  # miss marker
            else:
                if tile.get("name") == "Wreckage":
                    line += "💥 " 
                elif tile.get("event") == "kraken":
                    line += "🐙 "  
                elif reveal_ships and tile.get("ship"):
                    emoji = SHIP_EMOJIS.get(tile["ship"], "❓")
                    line += emoji + " "
                else:
                    line += WATER_EMOJI + " "
        preview += line + "\n"
    return preview

# Miscellaneous Functions
def get_tile_details(board, coord):
    coord = coord.upper()
    tile = board["tiles"].get(coord)
    if not tile:
        return f"❌ No tile data found for {coord}."

    details = {k: v for k, v in tile.items() if k != "previous_tile"}
    detail_lines = [f"{k.capitalize()}: {v}" for k, v in details.items()]
    return f"Details for {coord}:\n" + "\n".join(detail_lines)

async def current_task_command(team, boards, ctx):
    opponent_team = config.TEAM_PAIRS.get(team)
    if not opponent_team:
        await ctx.send(f"❌ Invalid team: {team}.")
        return
    
    opponent_board = boards[opponent_team]

    last_coord = get_last_shot_coord(opponent_board)
    if not last_coord:
        await ctx.send("Yer cannons be silent — no shots fired yet, captain!")
        return

    details_msg = get_tile_details(opponent_board, last_coord)
    await ctx.send(details_msg)

def get_last_shot_coord(board):
    shots = board.get("shots", {})
    if not shots:
        return None
    sorted_shots = sorted(
        shots.items(),
        key=lambda item: datetime.fromisoformat(item[1]["timestamp"]),
        reverse=True,
    )
    return sorted_shots[0][0]

def get_shots_against_team(team):
    board = load_board(team)
    return board.get("shots", {})

def get_move_history_for_team(team_name, boards):
    moves = []
    for opponent_team, board in boards.items():
        for coord, shot in board.get("shots", {}).items():
            if shot["by"] == team_name:
                moves.append({
                    "target_team": opponent_team,
                    "coord": coord,
                    "hit": shot["hit"],
                    "timestamp": shot["timestamp"]
                })
    moves.sort(key=lambda x: x["timestamp"])
    return moves

## Event Functions
def apply_event_to_board(event_type, team, events_data):
    board = load_board(team)
    ship_tiles = [coord for coord, tile in board["tiles"].items() if "ship" in tile and not tile.get("event")]

    if not ship_tiles:
        return None, "No available ship tiles to target."

    target_coord = random.choice(ship_tiles)
    original = board["tiles"][target_coord]

    board["tiles"][target_coord] = {
        "name": f"{event_type.title()} Event",
        "details": events_data[event_type]["details"],
        "event": event_type,
        "emoji": events_data[event_type]["emoji"],
        "original_tile": original,
        "event_timestamp": datetime.utcnow().isoformat()
    }

    file_path = board_path(team)
    with open(file_path, "w") as f:
        json.dump(board, f, indent=2)
    
    return target_coord, None

def resolve_event_on_board(event_type, team, result):
    board = load_board(team)

    for coord, tile in board["tiles"].items():

        event = tile.get("event")
        if event == event_type:
            if result == "complete":
                board["tiles"][coord] = tile.get("original_tile", {
                    "name": "Unknown Waters",
                    "details": "Restored after mysterious event.",
                })
            elif result == "fail":
                board["tiles"][coord] = {
                    "name": "Wreckage",
                    "details": f"This piece of your ship was destroyed by the {event_type}!",
                }
            else:
                return False  

            with open(board_path(team), "w") as f:
                json.dump(board, f, indent=2)
            return True

    return False  
