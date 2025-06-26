## Battleship Discord Bot

This is a bot I've built to support my OSRS clan events. To get started, you'll want to make a new Discord application [here](https://discord.com/developers/applications), and get the **token** to add to your `.env`.

First, in your console, `touch .env` in the root of this directory. Check the `.env.example` to see the variable(s) you'll want to add to your `.env`. Then, `cd data && touch base_tiles.json && touch ship_tiles.json`.

In this `data` directory, you'll find some example files. One (`example-base_tiles.json`) is the format you'll use for your new `base_tiles.json`, where you'll populate all of the data for the tiles with which you will randomly assign to the boards used for each team. One (`example-ship_tiles.json`) is the format that you'll want to use for your new `ship_tiles.json`, which determines the tiles that make up the five ships. Finally, there's an example (`example-board_teamA.json`) of what the data will look like when the bot tracks a team's board. This will automatically be created as the gameplay carries out.

You'll need to add the bot to your Discord server. Create at least two (2) team channels in your server, right click the channels and grab the channel IDs from each and replace the values found in `config.py` in the `TEAM_CHANNELS` constant. (You'll need to enable developer view in your Discord account settings to see those IDs!) You'll also want to add a `#spectators-channel` and grab that ID to replace the `SPECTATOR_CHANNEL_ID` value in `config.py`. This will allow non-participating clan members to enjoy the game as well!

Next, add a "refs" role to your Discord server. Assign those you want to have admin powers to that role. Then, simply populate the team channels with the respective participants.

You're ready to go!

### The gameplay loop is as follows:

1. Run the bot with `python bot.py`. This will automatically randomly generate (or load, if files have already been created!) boards for each team listed in `TEAMS_LIST` in `config.py` -- make sure you've appropriately paired up the teams against each other in the `TEAM_PAIRS` dictionary. You'll also want to fill out the `TEAM_COLORS` and `TEAM_DISPLAY` dicts.

2. Boards are, by default, **unlocked**, meaning anyone on a team can add or remove boats on the boards using the `!place` and `!remove` commands. (See below for a more in-depth guide on the bot commands.) Those with admin powers / the "refs" role can `!lockboard` and `!unlockboard` in the team channels to lock or unlock that team's board. Run `!intro` to broadcast the introductory details to all team channels and introduce the players to their ship-placing commands.

3. Once all five boats have been placed for each team and whatever amount of time you've allotted the players to strategize and place boats has passed, run the `!lockboard` commands in each channel.

4. Run `!taskrules` and then `!beginbattle` once all boards are locked. This will send out the task rules and gameplay commands to the teams.

5. Now, teams can start selecting where to strike on their opponent's board with `!select [coordinates]`. There will be a 10 minute cooldown after selecting a tile to prevent people from griefing. This will post in both the selecting team's channel and the opposing team's channel to communicate whether there was a hit on a boat or a miss, and it will also explain what the tile entails.

   5.a. Random events are supported, but optional, in this game. Check `example-random_events.json` to see some examples...

   ###### Note: Events that have `reward: skip` occur in the ocean and, if completed, "reveal" the tile they're on and give the successful team a "skip token", which allows them to skip a "miss" selection (ship hit tiles cannot be skipped). If they fail, then the tile that the event took over is restored and still "incomplete/unrevealed".

   ###### Events that are `reward: no damage` occur on a random, non-wrecked ship tile. If the team successfully completes the event challenge, their ship tile is restored. If they fail, that ship tile is destroyed.

   If you would like to begin an event, use `!eventstart [eventtype]` and it'll engage the event for all teams and announce the details in their respective channels. When the event should conclude, you must run `!eventend [eventtype] [complete/fail]` in the respective team channels to determine whether they completed or failed to complete the challenge.

6. The teams will have to complete the tiles' tasks and post proof in their respective drops channels to carry on.

7. When the game comes to an end, run `!win [teamSlug]` to send the game conclusion messages.

### Commands

- **!shiptypes**: Show ship types and sizes.
- **!view_board**: View your team's current board.
- **!view_enemy_board**: See your enemy's board (without ships, of course!).
- **!place [shiptype] [h/v] [starting coord]**: Place a ship on your board. Example: `!place carrier h A3`.
- **!remove [shiptype]**: Remove a ship from your board.
- **!current_task**: Show your team's current task.
- **!select [coord]**: Select a coordinate to shoot at. Example: `!select B5`.
- **!skips**: Check the number of skip tokens available to your team.
- **!use_skip**: Use a skip after a _missed_ shot, if you have a skip token available to your team.
- **!battleship_commands**: View all battleship commands

#### Requires the "Refs" role

- **!intro**: Broadcast the introductory details to all team channels.
- **!taskrules**: Broadcast the task rules.
- **!beginbattle**: Broadcast that the battle has begun. Includes battle commands.
- **!lockboard**: Lock the board to prevent changes.
- **!unlockboard**: Unlock the board to allow changes.
- **!team_progress**: Show overall progress of teams.
- **!eventstart [eventtype]**: Start an event across all team channels.
- **!eventend [eventtype] [complete/fail]**: Ends an event with either a success message or failure message in _specific_ team channels.
- **!refs_battleship_commands**: View all ref-specific battleship commands
- **!win [teamSlug]**: Complete the game, send the win/loss/overview messages to winning team, losing team, and spectators channel respectively.
