import discord
import config
import os
import json
from discord.ext import commands
from utils.game import generate_board, handle_tile_selection, current_task_command, render_board_preview, board_path, place_ship_to_file, remove_ship_from_file, load_board, render_board_with_shots

required_ships = ["carrier", "battleship", "cruiser", "submarine", "destroyer"]

bot = commands.Bot(command_prefix='!', intents=config.intents, case_insensitive=True)

def board_exists(team):
    filename = board_path(team)
    return os.path.isfile(filename)

def get_team_from_channel(channel_id):
    for team, cid in config.TEAM_CHANNELS.items():
        if cid == channel_id:
            return team
    return None

def load_or_generate_board(team):
    filename = board_path(team)

    if os.path.isfile(filename):
        with open(filename) as f:
            board = json.load(f)
        print(f"Loaded existing board for {team}")
    else:
        board = generate_board()
        with open(filename, "w") as f:
            json.dump(board, f, indent=2)
        print(f"Generated and saved new board for {team}")

    return board

def save_board(team, board):
    filename = board_path(team)
    with open(filename, "w") as f:
        json.dump(board, f, indent=2)

def is_valid_coordinate(coord):
    if len(coord) < 2:
        return False
    col = coord[0].upper()
    row = coord[1:]
    return col in "ABCDEFGHIJ" and row.isdigit() and 1 <= int(row) <= 10

def lock_board(board, required_ships):
    if board.get("locked", False):
        return "❌ Board is already locked."

    # check all required ships are placed
    ships_placed = board.get("ships", {})
    missing = [ship for ship in required_ships if ship not in ships_placed or not ships_placed[ship]]

    if missing:
        return f"❌ Cannot lock board. Missing ships: {', '.join(missing)}."

    board["locked"] = True
    return "✅ Board has been locked. No further changes allowed."

def unlock_board(board):
    if not board.get("locked", False):
        return "❌ Board is not locked."

    board["locked"] = False
    return "✅ Board has been unlocked. Changes allowed."

def user_has_refs_role(ctx):
    refs_role = discord.utils.get(ctx.guild.roles, name="refs")
    if refs_role in ctx.author.roles:
        return True
    return False

SHIP_TYPES = {
    "carrier": 5,
    "battleship": 4,
    "cruiser": 3,
    "submarine": 3,
    "destroyer": 2
}

SHIP_EMOJIS = {
    "carrier": "🟪",      # purple square
    "battleship": "🟫",   # brown square
    "cruiser": "⬜",      # white square
    "submarine": "🟧",    # orange square
    "destroyer": "⬛"     # black square
}

@bot.command(name="shiptypes")
async def show_ship_types(ctx):
    embed = discord.Embed(title="Ship Types", color=0x3498db)

    for ship, size in SHIP_TYPES.items():
        emoji = SHIP_EMOJIS.get(ship, "⬜")
        visual = emoji * size
        embed.add_field(name=f"{ship.title()} ({size} tiles)", value=visual, inline=False)

    await ctx.send(embed=embed)

@bot.command(name="view_board")
async def preview_board(ctx):
    team = get_team_from_channel(ctx.channel.id)    
    board = load_or_generate_board(team)
    if board.get("locked", False):
        print("Board is locked, showing full board with ships.")
        preview = render_board_with_shots(board, reveal_ships=True)
    else:
        print("Board is not locked, showing preview with required ships.")
        preview = render_board_preview(board, required_ships)
    await ctx.send("Here is your board!")
    if not board.get("locked", False):
        await ctx.send("Please place your ships.")
    
    await ctx.send(preview)


@bot.command()
async def team(ctx):
    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("No team.")
        return

    await ctx.send(f"You're on **{team}**!")

@bot.command(name="place")
async def place_command(ctx, ship_type: str, orientation: str, start_coord: str):
    team = get_team_from_channel(ctx.channel.id) 

    # validate inputs
    ship_type = ship_type.lower()
    orientation = orientation.lower()
    start_coord = start_coord.upper().replace(",", "")

    if ship_type not in SHIP_DEFINITIONS:
        await ctx.send(f"❌ Invalid ship type: `{ship_type}`.")
        return

    if orientation not in ["h", "v"]:
        await ctx.send("❌ Orientation must be `h` or `v`.")
        return

    if not is_valid_coordinate(start_coord):
        await ctx.send("❌ Invalid starting coordinate. Use format like A3.")
        return

    # place the ship
    result = place_ship_to_file(team, ship_type, orientation, start_coord, SHIP_DEFINITIONS)
    updated_board = load_board(team)
    preview = render_board_preview(updated_board, required_ships)

    await ctx.send(f"{result}\n{preview}")

@bot.command(name="remove")
async def remove_command(ctx, ship_type: str):
    team = get_team_from_channel(ctx.channel.id) 
    ship_type = ship_type.lower()

    if ship_type not in SHIP_DEFINITIONS:
        await ctx.send(f"❌ Invalid ship type: `{ship_type}`.")
        return

    # remove the ship
    result = remove_ship_from_file(team, ship_type)

    # show updated board
    updated_board = load_board(team)
    preview = render_board_preview(updated_board, required_ships)

    await ctx.send(f"{result}\n{preview}")

@bot.command(name="lockboard")
async def lockboard(ctx, team: str = None):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    team = team or get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("❌ Could not determine team from this channel. Specify a team name.")
        return

    if not board_exists(team):
        await ctx.send(f"❌ No board found for team '{team}'.")
        return

    board = load_board(team)
    msg = lock_board(board, required_ships)
    if msg.startswith("✅"):
        save_board(team, board)
    await ctx.send(msg)

@bot.command(name="unlockboard")
async def unlockboard(ctx, team: str = None):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    team = team or get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("❌ Could not determine team from this channel. Specify a team name.")
        return

    if not board_exists(team):
        await ctx.send(f"❌ No board found for team '{team}'.")
        return

    board = load_board(team)
    msg = unlock_board(board)
    if msg.startswith("✅"):
        save_board(team, board)
    await ctx.send(msg)

@bot.command(name="board_status")
async def board_status(ctx, team: str):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    team = team.lower()
    if team not in ["teama", "teamb"]:
        await ctx.send("❌ Invalid team. Use `teamA` or `teamB`.")
        return

    board = load_board(team) 
    if not board:
        await ctx.send(f"❌ No board found for team '{team}'.")
        return
    shots = board.get("shots", {})
    total_shots = len(shots)
    hits = sum(1 for s in shots.values() if s.get("hit"))
    misses = total_shots - hits

    await ctx.send(
        f"📊 **{team.upper()} Board Status**\n"
        f"> 🔫 Total shots: `{total_shots}`\n"
        f"> 🎯 Hits: `{hits}`\n"
        f"> 💨 Misses: `{misses}`"
    )

@bot.command(name="team_progress")
async def team_progress(ctx):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    progress_msgs = []
    for team in config.TEAMS_LIST:
        opponent = config.TEAM_PAIRS.get(team)
        if not opponent:
            progress_msgs.append(f"**{team.upper()}**\n> 🚫 No opponent defined.")
            continue

        opponent_board = load_board(opponent)
        if not opponent_board:
            progress_msgs.append(f"**{team.upper()}**\n> 🚫 No board found for opponent `{opponent}`.")
            continue

        # shots MADE BY this team are stored on opponent's board
        shots = opponent_board.get("shots", {})
        team_shots = {coord: data for coord, data in shots.items() if data.get("by") == team}

        total_shots = len(team_shots)
        hits = sum(1 for s in team_shots.values() if s.get("hit"))
        misses = total_shots - hits
        accuracy = (hits / total_shots) * 100 if total_shots else 0

        progress_msgs.append(
            f"**{team.upper()}** (shots on `{opponent}`)\n"
            f"> 🔫 Shots: `{total_shots}` | 🎯 Hits: `{hits}` | 💨 Misses: `{misses}`\n"
            f"> 🎯 Accuracy: `{accuracy:.1f}%`"
        )

    await ctx.send("📈 **Team Progress Report**\n" + "\n\n".join(progress_msgs))


@bot.command(name="current_task")
async def current_task(ctx):
    team = get_team_from_channel(ctx.channel.id)  # e.g., "teamA"
    if not team:
        await ctx.send("Could not detect your team.")
        return

    # Load boards from wherever you keep them, e.g. JSON files or memory
    boards = {
        "teamA": load_board("teamA") if board_exists("teamA") else None,
        "teamB": load_board("teamB") if board_exists("teamB") else None
    }

    await current_task_command(team, boards, ctx)

@bot.command()
async def select(ctx, coord: str):
    team = get_team_from_channel(ctx.channel.id)  # e.g., "teamA"
    if not team:
        await ctx.send("You're not on a team.")
        return

    boards = {
        "teamA": load_board("teamA") if board_exists("teamA") else None,
        "teamB": load_board("teamB") if board_exists("teamB") else None
    }
    # normalize coordinate format
    coord = coord.upper().replace(",", "")
    result = handle_tile_selection(team, coord, boards, config.TEAM_CHANNELS)

    if "error" in result:
        await ctx.send(result["error"])
        return

    # convert IDs to channel objects using bot.get_channel
    team_channel = bot.get_channel(result["team_channel"])  
    opponent_channel = bot.get_channel(result["opponent_channel"])

    # aaaand now send messages
    await team_channel.send(result["team_msg"])
    await opponent_channel.send(result["opponent_msg"])

@bot.command(name="battleship_commands")
async def battleship_commands(ctx):
    embed = discord.Embed(title="Battleship Commands", color=0x1abc9c)
    
    embed.add_field(name="!shiptypes", value="Show ship types and sizes.", inline=False)
    embed.add_field(name="!view_board", value="View your team's current board.", inline=False)
    embed.add_field(name="!team", value="Show your team name.", inline=False)
    embed.add_field(name="!place <ship> <h/v> <start>", value="Place a ship on your board. Example: `!place carrier h A3`", inline=False)
    embed.add_field(name="!remove <ship>", value="Remove a ship from your board.", inline=False)
    embed.add_field(name="!lockboard [team]", value="Lock the board to prevent changes. Refs role required.", inline=False)
    embed.add_field(name="!unlockboard [team]", value="Unlock the board to allow changes. Refs role required.", inline=False)
    embed.add_field(name="!team_progress", value="Show overall progress of teams. Refs role required.", inline=False)
    embed.add_field(name="!current_task", value="Show your team's current task.", inline=False)
    embed.add_field(name="!select <coord>", value="Select a coordinate to shoot at. Example: `!select B5`", inline=False)
    
    await ctx.send(embed=embed)


# load ship definitions
with open("data/ship_tiles.json") as f:
    SHIP_DEFINITIONS = json.load(f)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    for team in config.TEAMS_LIST:
        print(f"Board for {team} generating or loading...")
        load_or_generate_board(team)
    

bot.run(config.TOKEN)
