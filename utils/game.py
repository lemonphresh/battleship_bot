import json
import os
import random
import asyncio
import discord
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
MARY_READ_COLOR = 0xFFA500  # orange
ANNE_BONNY_COLOR = 0x1ABC9C  # teal

COOLDOWN_DISABLED = False # set to True to disable cooldown for testing

# Global cooldown tracker
last_shot_time = {}

def generate_match_summary(boards):
    """
    Accepts a dict of boards where keys are team slugs and values are their board data.
    Generates a summary for each team.
    """
    def summarize(board, team_display_name):
        shots = board.get("shots", {})
        hits = [s for s in shots.values() if s["hit"]]
        total = len(shots)
        sunk = sum(
            1 for coords in board.get("ships", {}).values()
            if all(shots.get(c, {}).get("hit") for c in coords)
        )
        accuracy = (len(hits) / total * 100) if total else 0
        return (
            f"**{team_display_name}**\n"
            f"> 🔫 Shots Fired: `{total}`\n"
            f"> 🎯 Hits: `{len(hits)}`\n"
            f"> 🚢 Ships Sunk: `{sunk}`\n"
            f"> 🎯 Accuracy: `{accuracy:.1f}%`\n"
        )

    lines = ["🏁 **Final Match Summary:**\n"]
    for team_slug in config.TEAMS_LIST:
        board = boards.get(team_slug)
        if not board:
            lines.append(f"⚠️ No board found for `{team_slug}`.")
            continue
        team_display = config.TEAM_DISPLAY.get(team_slug, team_slug)
        lines.append(summarize(board, team_display))

    return "\n".join(lines)

async def announce_to_spectators(bot, message, color=None, title=None, image=None):
    """
    Sends a message to the spectator channel. If a color is provided, sends an embed. 
    Otherwise, sends plain text. Optionally attaches an image.
    """
    channel = bot.get_channel(config.SPECTATOR_CHANNEL_ID)
    if channel:
        if color is not None:
            embed = discord.Embed(
                title=title if title else "Spectator Announcement",
                description=message,
                color=color
            )
            if image:
                embed.set_image(url=image) if isinstance(image, str) else None
            await channel.send(embed=embed)
        else:
            if image and isinstance(image, str):
                await channel.send(content=message, embed=discord.Embed().set_image(url=image))
            else:
                await channel.send(message)

def is_ship_sunk(board, ship_type):
    ship_coords = board.get("ships", {}).get(ship_type, [])
    shots = board.get("shots", {})

    for coord in ship_coords:
        if not shots.get(coord, {}).get("hit"):
            return False
    return True

def all_enemy_ships_sunk(board):
    ships = board.get("ships", {})
    shots = board.get("shots", {})

    for ship_coords in ships.values():
        for coord in ship_coords:
            shot = shots.get(coord)
            if not shot or not shot["hit"]:
                return False  # at least one tile is not hit
    return True

def get_last_shot(team):
    opponent = config.TEAM_PAIRS.get(team)
    if not opponent:
        return None

    board = load_board(opponent)
    shots = board.get("shots", {})
    if not shots:
        return None

    def parse_ts(ts_str):
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    recent = sorted(
        shots.items(),
        key=lambda item: parse_ts(item[1]["timestamp"]),
        reverse=True
    )

    for coord, shot in recent:
        if shot.get("by", "").lower() == team.lower():
            return {
                "coord": coord,
                "hit": shot["hit"],
                "timestamp": parse_ts(shot["timestamp"])
            }

    return None



SKIP_FILE = DATA_DIR / "skip_tokens.json"

def load_skip_tokens():
    if not SKIP_FILE.exists():
        return {team: 0 for team in config.TEAMS_LIST}
    with open(SKIP_FILE) as f:
        data = json.load(f)

    # ensure all teams from config.TEAMS_LIST are present
    for team in config.TEAMS_LIST:
        if team not in data:
            data[team] = 0
    return data

def save_skip_tokens(tokens):
    with open(SKIP_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

ACTIVE_SKIP_FILE = DATA_DIR / "active_skips.json"

def load_active_skips():
    if not ACTIVE_SKIP_FILE.exists():
        return {team: False for team in config.TEAMS_LIST}
    with open(ACTIVE_SKIP_FILE) as f:
        data = json.load(f)

    # ensure all teams from config.TEAMS_LIST are present
    for team in config.TEAMS_LIST:
        if team not in data:
            data[team] = False
    return data

def save_active_skips(data):
    with open(ACTIVE_SKIP_FILE, "w") as f:
        json.dump(data, f, indent=2)

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
    if COOLDOWN_DISABLED:
        return True, None
    
    now = datetime.now(timezone.utc)
    last = last_shot_time.get(team)
    if last and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    if last and now - last < timedelta(minutes=COOLDOWN_MINUTES):
        remaining = timedelta(minutes=COOLDOWN_MINUTES) - (now - last)
        mins = remaining.seconds // 60
        secs = remaining.seconds % 60
        return False, f"🚢 Hold position! You must complete your task before unleashing another volley."
    return True, None

def already_shot(board, coord):
    return coord.upper() in board.get("shots", {})

def handle_tile_selection(bot, selecting_team, target_coord, boards, team_channels):
    opposing_team = config.TEAM_PAIRS.get(selecting_team)
    target_board = boards[opposing_team]
    target_coord = target_coord.upper()
    team_img = None
    opponent_img = None

    tokens = load_skip_tokens()
    active_skips = load_active_skips()
    skip_used = False

    can_shoot_result, cooldown_msg = can_shoot(selecting_team)
    if not can_shoot_result:
        return {"error": cooldown_msg}

    tile = target_board["tiles"].get(target_coord)

    if not tile:
        return {"error": f"❌ **{target_coord}** is impossible to hit — there's nothing there to strike, Captain!"}

    if already_shot(target_board, target_coord):
        return {"error": f"⚠️ **{target_coord}** has already been struck. Choose another target."}

    if tile.get("name") == "Wreckage":
        # reveal it visually
        board_preview = render_board_with_shots(target_board, reveal_ships=False)

        return {
            "team_msg": (
                f"💀 That tile (**{target_coord}**) is already a wreck — nothing left to target there.\n"
                f"Select another coordinate, Captain.\n\n"
                f"🧭 Here's your current spyglass view:\n\n{board_preview}"
            ),
            "opponent_msg": None,
            "team_channel": team_channels[selecting_team],
            "opponent_channel": None
        }

    is_hit = "ship" in tile
    timestamp = datetime.now(timezone.utc).isoformat()

    target_board.setdefault("shots", {})[target_coord] = {
        "by": selecting_team,
        "hit": is_hit,
        "timestamp": timestamp,
    }

    if not is_hit:
        if active_skips.get(selecting_team) and tokens.get(selecting_team, 0) > 0:
            tokens[selecting_team] -= 1
            active_skips[selecting_team] = False
            save_skip_tokens(tokens)
            save_active_skips(active_skips)
            skip_used = True
        else:
            last_shot_time[selecting_team] = datetime.now(timezone.utc)
    else:
        last_shot_time[selecting_team] = datetime.now(timezone.utc)

    with open(board_path(opposing_team), "w") as f:
        json.dump(target_board, f, indent=2)

    team_selecting_channel = team_channels[selecting_team]
    team_target_channel = team_channels[opposing_team]

    if is_hit:
        ship_type = tile.get("ship")
        ship_name = ship_type.capitalize() if ship_type else "Unknown"
        tile_name = tile["name"]
        tile_details = tile.get("details", "")
        tile_count = tile.get("count", 0)

        result_to_team = (
            f"## 💥 **Direct hit, Captain!** The enemy’s **{ship_name}** took a blow at **{target_coord}**!\n\n"
            f"\nYou must acquire **{tile_count}** **{tile_name}** to complete the strike!"
        )
        if tile_details:
            result_to_team += f"\n\n📜 **Additional Details:**\n{tile_details}"

        result_to_opponent = (
            f"## 🚨 **{config.TEAM_DISPLAY[selecting_team]}** struck your **{ship_name}** at **{target_coord}**!\n\n"
            f"Hold fast, crew! ⚠️"
        )

        # SPECTATOR ANNOUNCEMENT: SHOT HIT
        asyncio.create_task(announce_to_spectators(
            bot,
            f"**{config.TEAM_DISPLAY[selecting_team]}** landed a hit at **{target_coord}** on **{config.TEAM_DISPLAY[opposing_team]}**'s waters!",
            color=config.TEAM_COLORS[selecting_team],
            title="🎯 Direct Hit!",
            image="https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExdnY1ZDByNWJ1YmplbXBxOXNiZmh1cWY2M3NpbHVqazNibDd5a2I3MSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/c41Vg6E0tqOuxk32rH/giphy.gif"
        ))
        # check if this sunk the ship
        if ship_type and is_ship_sunk(target_board, ship_type):
            result_to_team += f"\n\n🔥 **You sunk the enemy’s {ship_name}!** 💥"
            result_to_opponent += f"\n\n💥 **Your {ship_name} has been sunk!** Prepare to patch the hull!"

            # SPECTATOR ANNOUNCEMENT: SHIP SUNK
            asyncio.create_task(announce_to_spectators(
                bot,
                f"💀 **{config.TEAM_DISPLAY[selecting_team]}** has sunk **{config.TEAM_DISPLAY[opposing_team]}**'s **{ship_name}!**",
                color=config.TEAM_COLORS[selecting_team],
                title="🏴‍☠️ Final Blow Landed!",
                image="https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExa2c5NzR2dHYxYTI0YXRsOGttdDVmNW84eDBiZGh1NnRwZno4ejJsMSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/JlR1TxQqjVLna/giphy.gif"
            ))

        if all_enemy_ships_sunk(target_board):
            result_to_team += "\n\n## 🏁 **Victory is near!** Complete this task to claim the seas!"
            result_to_opponent += "\n\n## 💀 **Critical hit!** Your final ship tile has been struck! You still have a chance to claim the seas, the game isn't over until they complete their task!"

            # SPECTATOR ANNOUNCEMENT: FINAL STRIKE
            asyncio.create_task(announce_to_spectators(
                bot,
                f"**{config.TEAM_DISPLAY[selecting_team]}** has struck the final ship tile of **{config.TEAM_DISPLAY[opposing_team]}**! If they complete the task, the game is theirs!",
                color=0xFFD700,
                title="🏴‍☠️ Final Blow Landed!",
                image="https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExMW80MXQ0YWF2YWcwYWg2c2YwODBseTBsdzQ5dmgycThlenFjenlubyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Vq6XlTmAK66P80BUU8/giphy.gif"
            ))
    else:
        tile_name = tile.get("name", "Water")
        tile_details = tile.get("details", "")
        tile_count = tile.get("count", 0)

        result_to_team = (
            f"💨 **Splashdown!** Your shot landed at **{target_coord}**, but hit only water.\n\n"
            f"You must acquire **{tile_count}** **{tile_name}** to shoot again."
        )
        if skip_used:
            result_to_team += "\n\n🎁 **Skip used!** You may fire again immediately."
        if tile_details and tile_details.strip():
            result_to_team += f"\n\n 📜 **Additional Details:**\n{tile_details}"

        result_to_opponent = (
            f"🛡️ **{config.TEAM_DISPLAY[selecting_team]}** fired at **{target_coord}**, but missed."
        )

        # SPECTATOR ANNOUNCEMENT: SHOT MISSED
        asyncio.create_task(announce_to_spectators(
            bot,
            f"**{config.TEAM_DISPLAY[selecting_team]}** fired at **{config.TEAM_DISPLAY[opposing_team]}**'s waters — but missed at **{target_coord}**.",
            color=config.TEAM_COLORS[selecting_team],
            title="🌊 Missed Shot",
            image="https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExeHNtMDV1ZDdycXE4d3F3bHRseTNzbW1zd3BsNDc0cXRxNmptY3hteSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3og0ITfxYUkLNVawrm/giphy.gif"
        ))

    board_preview_for_selecting = render_board_with_shots(target_board, reveal_ships=False)
    board_preview_for_opponent = render_board_with_shots(target_board, reveal_ships=True)

    if is_hit: 
        asyncio.create_task(announce_to_spectators(
            bot,
            board_preview_for_selecting,
            color=config.TEAM_COLORS[selecting_team],
            title="🗺️ Current Status of " + config.TEAM_DISPLAY[opposing_team] + "'s Waters"
        ))
        team_img = "bs_hit.png"  

    return {
        "team_msg": result_to_team + "\n\n🏴‍☠️ Spyglass view:\n" + board_preview_for_selecting,
        "opponent_msg": result_to_opponent + "\n\n🧭 Your waters:\n" + board_preview_for_opponent,
        "team_channel": team_selecting_channel,
        "opponent_channel": team_target_channel,
        "team_img": team_img,
        "opponent_img": opponent_img
    }

# rendering functions
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
            elif tile.get("event"):
                line += tile.get("emoji", "❓") + " "
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
                elif shot.get("by") == "event-complete":
                    line += "🛡️ "  # completed event tile
                else:
                    line += "⚫ "  # miss marker
            elif tile.get("name") == "Wreckage":
                line += "💥 " 
            elif tile.get("event") and reveal_ships:
                line += tile.get("emoji", "❓") + " "
            elif reveal_ships and tile.get("ship"):
                emoji = SHIP_EMOJIS.get(tile["ship"], "❓")
                line += emoji + " "
            else:
                line += WATER_EMOJI + " "
        preview += line + "\n"
    return preview

# miscellaneous functions
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

## event functions
def apply_event_to_board(event_type, team, events_data):
    board = load_board(team)
    reward = events_data[event_type].get("reward")

    if reward == "skip":
        # get non-ship, non-shot, non-event tiles
        opponent_team = team  # the team whose board the event is applied to
        tile_candidates = [
            coord for coord, tile in board["tiles"].items()
            if "ship" not in tile and not tile.get("event") and coord not in board.get("shots", {})
        ]
    else:
        # default: pick a ship tile with no active event
        tile_candidates = [
            coord for coord, tile in board["tiles"].items()
            if "ship" in tile and not tile.get("event")
        ]

    if not tile_candidates:
        return None, "No valid tiles available to apply this event."

    target_coord = random.choice(tile_candidates)
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


def resolve_event_on_board(event_type, team, result, events_data=None):
    board = load_board(team)

    for coord, tile in board["tiles"].items():
        if tile.get("event") == event_type:
            reward = events_data.get(event_type, {}).get("reward") if events_data else None

            if result == "complete":
                if reward == "skip":
                    # mark it as a resolved virtual miss (log it as a shot)
                    board.setdefault("shots", {})[coord] = {
                        "by": "event-complete",
                        "hit": False,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                else:
                    # default restoration for ship-based events
                    board["tiles"][coord] = tile.get("original_tile", {
                        "name": "Unknown Waters",
                        "details": "Restored after mysterious event.",
                    })

                # apply skip token if applicable
                if reward == "skip":
                    tokens = load_skip_tokens()
                    tokens[team] = tokens.get(team, 0) + 1
                    save_skip_tokens(tokens)

            elif result == "fail":
                # ship piece is marked as wreckage
                board["tiles"][coord] = {
                    "name": "Wreckage",
                    "details": f"This piece of your ship was destroyed by the {event_type}!",
                }

                board.setdefault("shots", {})[coord] = {
                    "by": "event",
                    "hit": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return False

            with open(board_path(team), "w") as f:
                json.dump(board, f, indent=2)

            return True

    return False

