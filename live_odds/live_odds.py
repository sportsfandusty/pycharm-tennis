import requests
import json
import re
import pandas as pd
import time
from datetime import datetime
import os
import shutil

# Set Pandas display options to show all columns and prevent truncation
pd.set_option('display.max_columns', None)  # Show all columns
pd.set_option('display.width', None)        # Prevent wrapping of columns
pd.set_option('display.max_colwidth', None) # Show full content of each column

# Function to clean and convert odds to integers
def clean_odds(odds):
    if odds == "N/A":
        return "N/A"
    try:
        # Replace non-standard minus signs with standard hyphens
        odds = odds.replace('−', '-')
        # Remove any non-numeric characters (like '+', ',', etc.)
        odds = re.sub(r'[^0-9-]', '', odds)
        # Convert to integer
        return int(odds)
    except (ValueError, TypeError) as e:
        print(f"Error cleaning odds '{odds}': {e}")  # Debugging print
        return "N/A"

# Function to calculate implied win percentage from American odds
def calculate_iwp(odds):
    if odds == "N/A":
        return "N/A"
    try:
        odds = clean_odds(odds)  # Clean the odds before calculation
        if odds == "N/A":
            return "N/A"
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    except (ValueError, TypeError) as e:
        print(f"Error calculating IWP for odds '{odds}': {e}")  # Debugging print
        return "N/A"

# Function to normalize implied probabilities to account for rake
def normalize_iwp(p1_iwp, p2_iwp):
    if p1_iwp == "N/A" or p2_iwp == "N/A":
        return "N/A", "N/A"
    total = p1_iwp + p2_iwp
    p1_iwp_normalized = (p1_iwp / total)
    p2_iwp_normalized = (p2_iwp / total)
    return round(p1_iwp_normalized, 3), round(p2_iwp_normalized, 3)

# Function to fetch and process match elo
def fetch_and_process_data():
    # List of league IDs to cycle through
    league_ids = ["112632", "90349"]

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Sec-GPC": "1",
        "Priority": "u=4",
        "Referer": "https://sportsbook.draftkings.com/",
    }

    # Tournament Surface Mapping (Add more as needed)
    tournament_surface_map = {
        "Indian Wells": "Hard",
        "Miami Open": "Hard",
        "French Open": "Clay",
        "Wimbledon": "Grass",
        "US Open": "Hard",
        # Add more tournaments and surfaces here
    }

    all_matches = []  # List to store match elo

    for league_id in league_ids:
        url = f"https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/{league_id}"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            # --- Extract Tournament Name ---
            leagues = data.get('leagues', [])
            tournament_name = "Unknown Tournament"  # Default value
            if leagues:
                first_league = leagues[0]
                full_name = first_league.get('name', '')
                match = re.search(r"(?:ATP|WTA)\s*-\s*(.*)", full_name)
                if match:
                    tournament_name = match.group(1).strip()
                else:
                    tournament_name = full_name.strip()

            # --- Tournament Surface Lookup ---
            surface = tournament_surface_map.get(tournament_name, "Unknown Surface")  # Lookup, default to "Unknown"
            if surface == "Unknown Surface":
                print(f"WARNING: Tournament '{tournament_name}' not found in surface map.  Please add it.")

            events = data.get('events', [])
            selections = data.get('selections', [])

            # Create a dictionary to map selection IDs to odds (more efficient)
            selection_odds = {}
            for selection in selections:
                selection_id = selection.get('id')
                if selection_id:
                    selection_odds[selection_id] = selection.get('displayOdds', {}).get('american', 'N/A')

            if events:
                for event in events:
                    event_name = event.get('name', 'Unnamed Event')
                    participants = event.get('participants', [])

                    if len(participants) == 2:  # Assuming 2 players per match
                        player1_name = participants[0].get('name', 'Unknown')
                        player2_name = participants[1].get('name', 'Unknown')
                        player1_odds = "N/A"
                        player2_odds = "N/A"

                        # Get odds for player 1
                        for selection in selections:
                            if selection.get('label') == player1_name:
                                player1_odds = selection.get('displayOdds', {}).get('american', 'N/A')
                                break

                        # Get odds for player 2
                        for selection in selections:
                            if selection.get('label') == player2_name:
                                player2_odds = selection.get('displayOdds', {}).get('american', 'N/A')
                                break

                        # Calculate implied win percentages
                        p1_iwp = calculate_iwp(player1_odds)
                        p2_iwp = calculate_iwp(player2_odds)

                        # Normalize implied probabilities to account for rake
                        p1_iwp_normalized, p2_iwp_normalized = normalize_iwp(p1_iwp, p2_iwp)

                        # Add timestamp
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        all_matches.append({
                            'Tmnt': tournament_name,  # Renamed column
                            'sfc': surface,           # Renamed column
                            'p1': player1_name,      # Renamed column
                            'p1_ml': player1_odds,   # Renamed column
                            'p1_iwp': p1_iwp_normalized,  # Normalized implied win percentage
                            'p2': player2_name,      # Renamed column
                            'p2_ml': player2_odds,   # Renamed column
                            'p2_iwp': p2_iwp_normalized,  # Normalized implied win percentage
                            'timestamp': timestamp,  # Added timestamp
                        })

        except requests.exceptions.HTTPError as errh:
            print(f"HTTP Error: {errh}")
        except requests.exceptions.ConnectionError as errc:
            print(f"Error Connecting: {errc}")
        except requests.exceptions.Timeout as errt:
            print(f"Timeout Error: {errt}")
        except requests.exceptions.RequestException as err:
            print(f"Something went wrong: {err}")
        except json.JSONDecodeError as jerr:
            print(f"JSON Decode Error: {jerr}")

    # Create DataFrame
    df = pd.DataFrame(all_matches)

    # Reorder columns for a clean display
    df = df[['Tmnt', 'sfc', 'p1', 'p1_ml', 'p1_iwp', 'p2', 'p2_ml', 'p2_iwp', 'timestamp']]

    # Save the new results and archive the old file
    save_results(df)

# Function to save results and archive old file
def save_results(df):
    # Create the 'previous' directory if it doesn't exist
    if not os.path.exists('previous'):
        os.makedirs('previous')

    # Archive the existing 'upcoming_matches.csv' if it exists in the current directory
    if os.path.exists('upcoming_matches.csv'):
        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        archive_filename = f"previous/upcoming_matches_{timestamp}.csv"
        shutil.move('upcoming_matches.csv', archive_filename)
        print(f"Archived previous results to: {archive_filename}")

    # Save the new results as 'upcoming_matches.csv' in the current directory
    df.to_csv('upcoming_matches.csv', index=False)
    print("Saved new results to: upcoming_matches.csv (current directory)")

    # Save the new results as 'upcoming_matches.csv' in the 'elo' directory
    elo_directory = '../elo'
    if not os.path.exists(elo_directory):
        os.makedirs(elo_directory)

    # Archive the existing 'upcoming_matches.csv' in the 'elo' directory if it exists
    elo_file_path = os.path.join(elo_directory, 'upcoming_matches.csv')
    if os.path.exists(elo_file_path):
        # Generate a timestamp for the filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        archive_filename = f"previous/upcoming_matches_{timestamp}.csv"
        shutil.move(elo_file_path, archive_filename)
        print(f"Archived previous results in 'elo' directory to: {archive_filename}")

    # Save the new results in the 'elo' directory
    df.to_csv(elo_file_path, index=False)
    print(f"Saved new results to: {elo_file_path}")

# Run the script every 10 minutes
while True:
    print("\nInitializing live odds update...")
    fetch_and_process_data()
    print("\nOdds successfully updated.  Sleeping for 10 minutes...")
    time.sleep(600)  # 600 seconds = 10 minutes
