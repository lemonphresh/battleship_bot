from dotenv import load_dotenv
import os
import discord

load_dotenv()

TEAMS_LIST = [
    "teamA", 
    "teamB", 
    # "teamC",
    # "teamD"
    ]
TEAM_PAIRS = {
        "teamA": "teamB",
        "teamB": "teamA",
        # "teamC": "teamD",
        # "teamD": "teamC",
    }

TEAM_CHANNELS = {
    "teamA": 1377684385519898725,  # replace with actual channel IDs
    "teamB": 1377684420001005638
}

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
intents.message_content = True
