from dotenv import load_dotenv
import os
import discord

load_dotenv()

TEAMS_LIST = [
    "anneBonny", 
    "maryRead", 
    # "teamC",
    # "teamD"
    ]
TEAM_PAIRS = {
        "anneBonny": "maryRead",
        "maryRead": "anneBonny",
        # "teamC": "teamD",
        # "teamD": "teamC",
    }

TEAM_DISPLAY = {
    "anneBonny": "Anne Bonny’s Crew",
    "maryRead": "Mary Read’s Crew"
}

TEAM_CHANNELS = {
    "anneBonny": ,  # replace with actual channel IDs
    "maryRead": 
}

SPECTATOR_CHANNEL_ID =   # your #spectator-channel ID

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
intents.message_content = True
