import discord
import config
import os
import json
from discord.ext import commands
from utils.game import (
    generate_board, handle_tile_selection, current_task_command, render_board_preview,
    board_path, place_ship_to_file, remove_ship_from_file, load_board, render_board_with_shots
)

required_ships = ["carrier", "battleship", "cruiser", "submarine", "destroyer"]

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

# Bot Initialization
bot = commands.Bot(command_prefix='!', intents=config.intents, case_insensitive=True)

# Utility Functions
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
    return refs_role in ctx.author.roles

# Commands
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

    result = remove_ship_from_file(team, ship_type)
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
    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("Could not detect your team.")
        return

    boards = {
        "teamA": load_board("teamA") if board_exists("teamA") else None,
        "teamB": load_board("teamB") if board_exists("teamB") else None
    }

    await current_task_command(team, boards, ctx)

@bot.command()
async def select(ctx, coord: str):
    team = get_team_from_channel(ctx.channel.id)
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


    refs_role = discord.utils.get(ctx.guild.roles, name="attn refs")
    if refs_role:
        role_mention = refs_role.mention
    else:
        role_mention = "@attn refs"  # fallback in case role not found

    # aaaand now send messages
    await team_channel.send(result["team_msg"] + f"\n\n ||{role_mention}||")
    await opponent_channel.send(result["opponent_msg"])

@bot.command(name="intro")
async def intro(ctx):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return
    
    intro_message = (
        "# 🦜 **Ahoy, Captains! Welcome to Battleship: EG Edition!** ⚓\n\n"
        "The high seas await, and war is brewing on the waves! Each team commands a mighty fleet, hidden away on secret boards. "
        "Your mission? Outsmart, outmaneuver, and out-blast your foes in a battle of brains and bravery.\n\n"
        "**Here’s how your voyage will unfold:**\n\n"
        "1. **Chart Your Waters:** Each team is assigned a hidden board — your home port. Your ships must be placed in secret across the 10x10 grid. "
        "Work with your crew to position them wisely. Sabotage awaits the sloppy! ~~and sloppy awaits the saboteurs~~\n\n"
        "2. **Ship Shape & Ready to Sail:** Use your team’s channel to place or remove ships using the proper commands. But beware — once the time for preparation ends, "
        "the board will be **locked**, and your fleet’s fate is sealed.\n\n"
        "3. **Fire in the Hole!** When battle begins, your team will take turns firing upon the enemy’s grid with `!select A5` "
        "(or whatever coordinate your gut says holds treasure). A mighty *BOOM* for a hit, a cold splash for a miss!\n\n"
        "4. **Complete Your Orders:** Each tile you hit reveals a mission — complete it, post your proof in your drops channel, and mark your team’s path toward victory.\n\n"
        "5. **Sink or Swim:** The first crew to sink all five enemy ships reigns supreme on the seas. But beware — clever opponents and cursed tiles can turn the tide at any moment!\n\n"
        "So rally your mates, strategize in secret, and may the sharpest crew claim the seas!\n"
        "🗺️🦑 Good luck... and don’t forget to watch the horizon.\n"
        "⚓ ⚓ ⚓"
    )

    command_guide = (
        "## **🛠️ Team Commands:**\n\n"
        "`!place [shiptype] [v/h] A,5` – Place a ship tile on your board, v for vertically and h for horizontally\n"
        "`!remove [shiptype]` – Remove a ship tile from your board\n"
        "`!view_board` – See your current board\n"
        "`!shiptypes` – View ship types and their emoji markers\n"
        "⚓ ⚓ ⚓"
    )

    shiptypes_description = "\n\n ## **🛳️ Ship Types:**\n\n" + "\n".join(
        [f"{ship.title()} ({size} tiles): {SHIP_EMOJIS.get(ship, '⬜') * size}" for ship, size in SHIP_TYPES.items()]
    ) + "\n⚓ ⚓ ⚓"

    boards = {
        "teamA": load_board("teamA") if board_exists("teamA") else None,
        "teamB": load_board("teamB") if board_exists("teamB") else None
    }

    for team, channel_id in config.TEAM_CHANNELS.items():
        channel = bot.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(intro_message)
                await channel.send(command_guide)
                await channel.send(shiptypes_description)
                preview = render_board_preview(boards[team], required_ships=required_ships)
                await channel.send("\n\n## **📡 Current Board Status:**\n\n")
                await channel.send(preview)
            except discord.Forbidden:
                print(f"Missing permission to send messages in channel {channel.name}")

@bot.command(name="beginbattle")
async def begin_battle(ctx):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    unlocked_teams = [team for team in config.TEAM_CHANNELS if not load_board(team).get("locked", False)]
    if unlocked_teams:
        team_list = ", ".join(unlocked_teams)
        await ctx.send(f"⚠️ The following teams still have unlocked boards: **{team_list}**.\n"
                       "Please make sure all boards are locked before beginning the battle.")
        return

    battle_message = (
        "# 🧭 **The Boards Are Set — Let Battle Commence!** 🚢\n\n"
        "The fog has lifted, and the fleets are in formation. There’s no turning back now — your board is locked, your ships are anchored, "
        "and the hunt begins.\n\n"
        "**Here’s your new battle routine:**\n\n"
        "1. **Survey Your Fleet:** Use `!view_board` to check the status of your ships and keep your strategy tight.\n\n"
        "2. **Choose Your Target:** With `!select A5` (or whatever coordinate calls to your gut), fire upon the enemy’s hidden grid. "
        "Your strike will echo across the waves — and across the channels.\n\n"
        "3. **Follow the Orders:** If your cannonball lands true, you'll reveal a task. Use `!current_task` to remind yourselves what the gods of war demand. "
        "Prove your mettle by completing the challenge and posting proof in your drops channel.\n\n"
        "4. **Stay Sharp:** You can always use `!view_board` to reassess your tactical position. The tide turns quickly, and only the most cunning will stay afloat.\n\n"
        "5. **Claim Victory:** Sink all five enemy ships, and your crew will be legends sung in every port. ⚓\n\n"
        "Raise the sails. Light the powder. Let the Battle of EG rage on!\n"
        "🔥🌊🦜 May the winds favor the bold."
    )

    command_guide = (
        "## **🎯 Battle Commands:**\n\n"
        "`!select [A1-J10]` – Fire upon an enemy tile\n"
        "`!current_task` – View your current task, if you've hit a tile\n"
        "`!view_board` – See your current board\n"
        "⚓ ⚓ ⚓"
    )

    for team, channel_id in config.TEAM_CHANNELS.items():
        channel = bot.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(battle_message)
                await channel.send(command_guide)
            except discord.Forbidden:
                print(f"Missing permission to send messages in channel {channel.name}")

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

# Event Handlers
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    for team in config.TEAMS_LIST:
        print(f"Board for {team} generating or loading...")
        load_or_generate_board(team)

# Load Ship Definitions
with open("data/ship_tiles.json") as f:
    SHIP_DEFINITIONS = json.load(f)

# Run Bot
bot.run(config.TOKEN)
