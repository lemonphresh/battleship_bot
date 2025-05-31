# run python assign_bosses_to_base_tiles.py to replace tile names in base_tiles.json with OSRS bosses

import json
import random

OSRS_BOSSES = [
    "Zulrah", "Vorkath", "Hunllef (Corrupted Gauntlet only)", "Sarachnis", "Kree'arra", "Moons of Peril",
    "Commander Zilyana", "General Graardor", "Kraken", "Cerberus", "Scorpia", "Callisto", "Vet'ion",
    "Venenatis", "King Black Dragon", "Chaos Fanatic", "Crazy Archaeologist", "Chaos Elemental",
    "Kalphite Queen", "Dagannoth Rex", "Dagannoth Supreme", "Dagannoth Prime", "Thermonuclear Smoke Devil",
    "The Nightmare", "Phantom Muspah", "Obor", "Bryophyta", "Barrows", "Tempoross", "Wintertodt",
    "TzTok-Jad", "TzKal-Zuk", "Duke Sucellus", "Whisperer", "Leviathan", "Vardorvis", "Nex",
    "Royal Titans", "Yama", "Hueycoatl", "The Great Olm", "Corporeal Beast", "Grotesque Guardians",
    "Verzik Vitur", "Wardens", "Zalcano", "Giant Mole", "Kril Tsutsaroth", "Alchemical Hydra"
]

def replace_tile_names(input_path="data/base_tiles.json", output_path="data/base_tiles_bosses.json"):
    with open(input_path, "r") as f:
        data = json.load(f)

    used_bosses = set()
    tiles = data.get("tiles", [])

    for tile in tiles:
        # pick a random unused boss name (fallback to reuse if we run out)
        available_bosses = list(set(OSRS_BOSSES) - used_bosses)
        if not available_bosses:
            available_bosses = OSRS_BOSSES  # allow repeats if we run out
            used_bosses.clear()
        boss = random.choice(available_bosses)
        tile["name"] = boss
        used_bosses.add(boss)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Replaced tile names with OSRS bosses and saved to {output_path}")

if __name__ == "__main__":
    replace_tile_names()