import discord
import config
import os
import json
from datetime import datetime, timedelta, timezone
from discord.ext import commands
from utils.game import (
    announce_to_spectators, apply_event_to_board, generate_board, generate_match_summary, get_last_shot, handle_tile_selection, current_task_command, load_active_skips, load_skip_tokens, render_board_preview,
    board_path, place_ship_to_file, last_shot_time, remove_ship_from_file, load_board, render_board_with_shots, resolve_event_on_board, save_active_skips, save_skip_tokens
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

async def send_to_team_channel(team_key, message):
    channel_id = config.TEAM_CHANNELS.get(team_key)
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(message)

async def announce_to_spectators(bot, message):
    channel = bot.get_channel(config.SPECTATOR_CHANNEL_ID)
    if channel:
        await channel.send(message)

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
async def skips(ctx):
    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("⚠️ Could not determine team from this channel.")
        return

    tokens = load_skip_tokens()
    count = tokens.get(team, 0)

    await ctx.send(f"🪙 **{config.TEAM_DISPLAY[team]}** has **{count}** skip token(s) remaining.")

@bot.command(name="view_enemy_board")
async def view_enemy_board(ctx):
    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("Could not detect your team.")
        return

    opponent = config.TEAM_DISPLAY[config.TEAM_PAIRS.get(team)]
    if not opponent:
        await ctx.send("No opponent defined for your team.")
        return

    board = load_or_generate_board(opponent)
    preview = render_board_with_shots(board, reveal_ships=False)

    await ctx.send(f"⚓ Behold the enemy waters of **{opponent.upper()}**! Prepare to chart your course and strike true!")
    await ctx.send(preview)

@bot.command()
async def team(ctx):
    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("No team.")
        return

    await ctx.send(f"You're on **{config.TEAM_DISPLAY[team]}**!")

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
    if team not in ["annebonny", "maryread"]:
        await ctx.send("❌ Invalid team. Use `anneBonny` or `maryRead`.")
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

@bot.command()
async def use_skip(ctx):
    global last_shot_time 

    team = get_team_from_channel(ctx.channel.id)
    if not team:
            await ctx.send("⚠️ Could not determine team from this channel.")
            return
    
    last = get_last_shot(team)
    if not last:
        await ctx.send(f"⚠️ No shot history found for {config.TEAM_DISPLAY[team]}.")
        return
    if last["hit"]:
        await ctx.send(f"⚠️ Your last shot at **{last['coord']}** was a hit — skips are only usable after misses.")
        return

    # Check and consume skip token
    tokens = load_skip_tokens()
    if tokens.get(team, 0) <= 0:
        await ctx.send(f"❌ {config.TEAM_DISPLAY[team]} has no skip tokens remaining.")
        return

    tokens[team] -= 1
    save_skip_tokens(tokens)

    # Clear cooldown
    if team in last_shot_time:
        del last_shot_time[team]

    await ctx.send(
        f"✅ {config.TEAM_DISPLAY[team]} has used a **skip** after missing at **{last['coord']}**.\n"
        f"You may now fire again immediately!\n\n"
        f"🪙 Remaining skip tokens: **{tokens[team]}**"
    )

@bot.command(name="current_task")
async def current_task(ctx):
    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("Could not detect your team.")
        return

    boards = {
        "anneBonny": load_board("anneBonny") if board_exists("anneBonny") else None,
        "maryRead": load_board("maryRead") if board_exists("maryRead") else None
    }

    await current_task_command(team, boards, ctx)

@bot.command()
async def select(ctx, coord: str):
    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("You're not on a team.")
        return

    boards = {
        "anneBonny": load_board("anneBonny") if board_exists("anneBonny") else None,
        "maryRead": load_board("maryRead") if board_exists("maryRead") else None
    }
    # normalize coordinate format
    coord = coord.upper().replace(",", "")
    result = handle_tile_selection(ctx.bot, team, coord, boards, config.TEAM_CHANNELS)

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
        "You are on **{config.TEAM_DISPLAY[get_team_from_channel(ctx.channel.id)]}**\n\n"
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
        "`!place [shiptype] [v/h] A,5` – Place a ship tile on your board, v for vertically and h for horizontally. Ships are placed left to right, or top to bottom.\n"
        "`!remove [shiptype]` – Remove a ship tile from your board\n"
        "`!view_board` – See your current board\n"
        "`!view_enemy_board` – See your enemy's board (without ships, of course!) \n"
        "`!shiptypes` – View ship types and their emoji markers\n"
        "`!battleship_commands` – View all battleship commands\n"
        "⚓ ⚓ ⚓"
    )

    shiptypes_description = "\n\n ## **🛳️ Ship Types:**\n\n" + "\n".join(
        [f"{ship.title()} ({size} tiles): {SHIP_EMOJIS.get(ship, '⬜') * size}" for ship, size in SHIP_TYPES.items()]
    ) + "\n⚓ ⚓ ⚓"

    boards = {
        "anneBonny": load_board("anneBonny") if board_exists("anneBonny") else None,
        "maryRead": load_board("maryRead") if board_exists("maryRead") else None
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
        "`!view_enemy_board` – See your enemy's board (without ships, of course!) \n"
        "`!battleship_commands` – View all battleship commands\n"
        "`!skips` – Check your skip tokens\n"
        "`!use_skip` – Use a skip token to fire again immediately after a miss\n"
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
    embed.add_field(name="!view_enemy_board", value="View your enemy's current board (without ships, of course!).", inline=False)
    embed.add_field(name="!team", value="Show your team name.", inline=False)
    embed.add_field(name="!place <ship> <h/v> <start>", value="Place a ship on your board. Example: `!place carrier h A3`", inline=False)
    embed.add_field(name="!remove <ship>", value="Remove a ship from your board.", inline=False)
    embed.add_field(name="!current_task", value="Show your team's current task.", inline=False)
    embed.add_field(name="!select <coord>", value="Select a coordinate to shoot at. Example: `!select B5`", inline=False)
    embed.add_field(name="!skips", value="Check your skip tokens.", inline=False)
    embed.add_field(name="!use_skip", value="Use a skip token to fire again immediately after a miss.", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="refs_battleship_commands")
async def refs_battleship_commands(ctx):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    embed = discord.Embed(title="Refs-Only Battleship Commands", color=0xe74c3c)
    
    embed.add_field(name="!lockboard [team]", value="Lock a team's board to prevent further changes.", inline=False)
    embed.add_field(name="!unlockboard [team]", value="Unlock a team's board to allow changes.", inline=False)
    embed.add_field(name="!board_status <team>", value="View the status of a team's board.", inline=False)
    embed.add_field(name="!team_progress", value="View progress of all teams.", inline=False)
    embed.add_field(name="!intro", value="Send the introductory message to all team channels.", inline=False)
    embed.add_field(name="!beginbattle", value="Once boards are locked, start the battle and send the battle instructions.", inline=False)
    embed.add_field(name="!eventstart <event_type>", value="Start a random event for all teams.", inline=False)
    embed.add_field(name="!eventend <event_type> <complete|fail>", value="End a random event for the current team.", inline=False)
    embed.add_field(name="!matchsummary", value="Send a match summary to the spectator channel.", inline=False)
    embed.add_field(name="!win <winner>", value="Declare a winner and send victory messages.", inline=False)

    await ctx.send(embed=embed)

# Random Event Handlers 
@bot.command(name="eventstart")
async def start_event(ctx, event_type: str):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    try:
        with open("data/random_events.json") as f:
            events_data = json.load(f)
    except Exception as e:
        await ctx.send("⚠️ Could not load event definitions.")
        return

    if event_type not in events_data:
        await ctx.send(f"❌ Unknown event: `{event_type}`.")
        return

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=events_data[event_type]["duration_hours"])
    unix_timestamp = int(deadline.timestamp()) 

    for team, channel_id in config.TEAM_CHANNELS.items():
        coord, err = apply_event_to_board(event_type, team, events_data)
        channel = bot.get_channel(int(channel_id))
        if err:
            await channel.send(f"⚠️ `{event_type.title()}` tried to strike, but no valid targets on your board!")
            continue

        await channel.send(
            f"## 🌊 **A strange disturbance stirs the seas...** 🌊\n\n"
            f"⚠️ All hands on deck! A new threat has surfaced: **{event_type.upper()}** {events_data[event_type]['emoji']}\n"
            f"Something is happening at **{coord}**!\n"
            f"{events_data[event_type]['details']}\n\n"
            f"⏳ You must complete your task <t:{unix_timestamp}:R>, or the sea shall claim that tile!"
        )

    await ctx.send(f"📣 `{event_type}` event has been launched across all teams.")

@bot.command(name="eventend")
async def end_event(ctx, event_type: str, result: str):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    if result not in ["complete", "fail"]:
        await ctx.send("⚠️ Usage: `!eventend [event_type] complete|fail`")
        return

    team = get_team_from_channel(ctx.channel.id)
    if not team:
        await ctx.send("⚠️ Could not determine team from this channel.")
        return

    # Load event data
    try:
        with open("data/random_events.json") as f:
            events_data = json.load(f)
    except Exception:
        await ctx.send("❌ Could not load events config.")
        return

    event_def = events_data.get(event_type)
    if not event_def:
        await ctx.send(f"❌ Unknown event type: `{event_type}`")
        return

    reward = event_def.get("reward")

    # Resolve the event
    success = resolve_event_on_board(event_type, team, result, events_data=events_data)
    if not success:
        await ctx.send(f"⚠️ No active `{event_type}` event found to resolve for `{team}`.")
        return

    # Messaging logic
    if result == "complete":
        if reward == "skip":
            await ctx.send(
                f"✅ **{event_type.title()} Complete!**\n\n"
                f"You conquered the challenge and bested the seas! 🌊\n"
                f"The targeted tile is now considered **complete** and will no longer obstruct your journey.\n\n"
                f"As a reward, your crew has earned **1 skip token**. Use it wisely on any future missed shot! 🪙"
            )
        else:
            await ctx.send(
                f"✅ **{event_type.title()} Event Complete!**\n\n"
                f"Your crew faced the tide and triumphed. The menace has been repelled — your ship remains afloat! ⛵"
            )
    else:  # result == "fail"
        if reward == "skip":
            await ctx.send(
                f"💀 **{event_type.title()} Prevails, and You Failed...**\n\n"
                f"The winds howled and chaos ensued. The targeted tile remains **unresolved**. Stay wary! ⚠️"
            )
        else:
            await ctx.send(
                f"💀 **{event_type.title()} Event Failed...**\n\n"
                f"A dark fate befalls your fleet. The ocean has claimed its toll... a ship tile is lost to the deep. ⚓"
            )

    ctx.send(f"{event_type} event resolved for {team}: {result}")

@bot.command()
async def matchsummary(ctx):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    try:
        boardA = load_board("anneBonny")
        boardB = load_board("maryRead")
    except Exception:
        await ctx.send("❌ Failed to load one or both boards.")
        return

    summary = generate_match_summary(boardA, boardB)
    await announce_to_spectators(ctx.bot, summary)

    await ctx.send("📣 Match summary sent to the spectator channel!")



@bot.command()
async def win(ctx, winner: str):
    if not user_has_refs_role(ctx):
        await ctx.send("❌ You need the `refs` role to use this command.")
        return

    loser = config.TEAM_PAIRS.get(winner)
    if not winner or not loser:
        await ctx.send("⚠️ Invalid team. Usage: `!win anneBonny` or `!win maryRead`")
        return

    try:
        board_winner = load_board(winner)
        board_loser = load_board(loser)
    except Exception:
        await ctx.send("❌ Error loading boards. Are they complete?")
        return

    summary = generate_match_summary(board_winner, board_loser)
    winner_name = config.TEAM_DISPLAY[winner]
    loser_name = config.TEAM_DISPLAY[loser]

    # 🏴‍☠️ Pirate GIFs
    WIN_GIF = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExMWlqdmpzMHg1ZW0wZWo2NDh6NzkzMHA2M280ZDhrdHN0YTgybHd3diZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/10X22vzgNamaiI/giphy.gif"
    LOSE_GIF = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExNjdramN2cHZzdmMzZDZ6Z2NnaXNhdXc4d250YTd2YnV0cjF4Z3RpeiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/KdkAUTLT0TJBofZDOc/giphy.gif"
    SPECTATOR_GIF = "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExYnVjY3pjNDk1YTg5ZGpvcGJ0bDFjeHR3YzZ0aHFybHF5cWFsanIybSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/dCM60S7zcatpm8lTvB/giphy.gif"

    # 🏆 Winning message
    win_embed = discord.Embed(
        title="🏴‍☠️ Victory, me hearties!",
        description=(
            f"The salty winds were with ye, and the enemy fleet lies in tatters on the ocean floor.\n"
            f"Your name shall be etched into the map — **{winner_name} reigns supreme!**"
        ),
        color=0xFFD700
    )
    win_embed.set_image(url=WIN_GIF)

    # 💔 Losing message
    lose_embed = discord.Embed(
        title="💧 A noble fight, sailors.",
        description=(
            f"Though the tide turned against ye, your cannons thundered with valor.\n"
            f"The sea remembers courage — and **{loser_name}** shall rise again!"
        ),
        color=0x4682B4
    )
    lose_embed.set_image(url=LOSE_GIF)

    # 📣 Spectator message
    spec_embed = discord.Embed(
        title="🎙️ THE BATTLE IS OVER!",
        description=(
            f"🏆 **{winner_name}** has claimed the sea!\n"
            f"📉 **{loser_name}** fought fiercely, but the tide was cruel.\n\n"
            f"📊 **Match Summary:**\n\n{summary}"
        ),
        color=0x1E90FF
    )
    spec_embed.set_image(url=SPECTATOR_GIF)

    await ctx.send("📣 Sending post-match messages...")

    # Send messages
    winner_channel = bot.get_channel(config.TEAM_CHANNELS[winner])
    loser_channel = bot.get_channel(config.TEAM_CHANNELS[loser])
    spec_channel = bot.get_channel(config.SPECTATOR_CHANNEL_ID)

    if winner_channel:
        await winner_channel.send(embed=win_embed)
    if loser_channel:
        await loser_channel.send(embed=lose_embed)
    if spec_channel:
        await spec_channel.send(embed=spec_embed)


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
