import requests
import json
import re
import sqlite3
import time
import datetime

# --- Configuration Section ---
DB_FILE = "tennis_odds.db"
SLEEP_INTERVAL = 10  # Minutes between runs
RUN_LOOP = True
# RUN_LOOP = False

# List of league IDs
league_ids = ["112632", "90349"]

# Mapping of league IDs to tour (ATP/WTA)  <-- MOVED TO GLOBAL SCOPE
league_tour_map = {
    "112632": "WTA",
    "90349": "ATP"
}

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

# Tournament Surface Mapping
tournament_surface_map = {
    "Indian Wells": "Hard",
    "Miami Open": "Hard",
    "French Open": "Clay",
    "Wimbledon": "Grass",
    "US Open": "Hard",
    # Add more tournaments and surfaces here
}


def create_tables(conn):
    """Creates the necessary tables."""
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                tournament_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_name TEXT UNIQUE NOT NULL,
                surface TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                tournament_id INTEGER,
                event_name TEXT,
                start_event_date TEXT,
                status TEXT,
                league_id TEXT,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                participant_name TEXT,
                FOREIGN KEY (event_id) REFERENCES events(event_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS selections (
                selection_id TEXT,
                event_id TEXT,
                participant_name TEXT,
                odds_american TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                bet_status TEXT,
                PRIMARY KEY (selection_id, timestamp),
                FOREIGN KEY (event_id) REFERENCES events(event_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS surfaces (
                surface_id INTEGER PRIMARY KEY AUTOINCREMENT,
                surface_type TEXT UNIQUE NOT NULL
            )
        """)

        cursor.execute("INSERT OR IGNORE INTO surfaces (surface_type) VALUES (?)", ("Hard",))
        cursor.execute("INSERT OR IGNORE INTO surfaces (surface_type) VALUES (?)", ("Clay",))
        cursor.execute("INSERT OR IGNORE INTO surfaces (surface_type) VALUES (?)", ("Grass",))
        cursor.execute("INSERT OR IGNORE INTO surfaces (surface_type) VALUES (?)", ("Unknown Surface",))
        conn.commit()


def get_or_create_tournament(conn, tournament_name, surface):
    """Gets/creates tournament ID."""
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tournament_id FROM tournaments WHERE tournament_name = ?", (tournament_name,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            cursor.execute("INSERT INTO tournaments (tournament_name, surface) VALUES (?, ?)",
                           (tournament_name, surface))
            return cursor.lastrowid


def insert_event(conn, event_id, tournament_id, event_name, start_event_date, status, league_id):
    """Inserts event, handles duplicates."""
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO events (event_id, tournament_id, event_name, start_event_date, status, league_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event_id, tournament_id, event_name, start_event_date, status, league_id))


def insert_participant(conn, event_id, participant_name):
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO participants (event_id, participant_name)
            VALUES (?, ?)
        """, (event_id, participant_name))


def insert_selection(conn, selection_id, event_id, participant_name, odds_american, timestamp, bet_status):
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO selections (selection_id, event_id, participant_name, odds_american, timestamp, bet_status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (selection_id, event_id, participant_name, odds_american, timestamp, bet_status))

def get_previous_odds(conn, selection_id):
    """Retrieves the previous odds."""
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT odds_american
            FROM selections
            WHERE selection_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (selection_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None

def selection_exists(conn, selection_id):
    """Checks if a selection_id already exists."""
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM selections WHERE selection_id = ?", (selection_id,))
        return cursor.fetchone() is not None


def fetch_and_store_data():
    """Fetches data, stores it, and reports changes."""
    try:
        conn = sqlite3.connect(DB_FILE)
        print(f"Connected to SQLite database: {DB_FILE}")

        create_tables(conn)

        total_matches_inserted = 0
        line_changes = []

        for league_id in league_ids:
            tour = league_tour_map.get(league_id, "Unknown Tour")  # Correctly uses global league_tour_map
            url = f"https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/{league_id}"
            print(f"\nFetching {tour} data...")

            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                leagues = data.get('leagues', [])
                tournament_name = "Unknown Tournament"
                if leagues:
                    first_league = leagues[0]
                    full_name = first_league.get('name', '')
                    match = re.search(r"(?:ATP|WTA)\s*-\s*(.*)", full_name)
                    if match:
                        tournament_name = match.group(1).strip()
                    else:
                        tournament_name = full_name.strip()

                surface = tournament_surface_map.get(tournament_name, "Unknown Surface")
                if surface == "Unknown Surface":
                    print(f"WARNING: Tournament '{tournament_name}' needs surface mapping.")
                tournament_id = get_or_create_tournament(conn, tournament_name, surface)

                events = data.get('events', [])
                selections = data.get('selections', [])

                total_matches = 0
                in_progress_matches = 0
                upcoming_matches = 0
                completed_matches = 0

                if not events:
                    print("No events found.")
                else:
                    for event in events:
                        total_matches += 1
                        event_id = event.get('id')
                        event_name = event.get('name', 'Unnamed Event')
                        start_event_date = event.get('startEventDate')
                        event_status = event.get('status', 'UNKNOWN')

                        if event_status == "STARTED":
                            in_progress_matches += 1
                        elif event_status == "NOT_STARTED":
                            upcoming_matches += 1
                        elif event_status == "COMPLETED" or event_status == "ENDED":
                            completed_matches += 1

                        if not event_id:
                            print(f"Skipping event due to missing ID: {event_name}")
                            continue

                        insert_event(conn, event_id, tournament_id, event_name, start_event_date, event_status, league_id)
                        participants = event.get('participants', [])

                        for participant in participants:
                            participant_name = participant.get('name', 'Unknown Participant')
                            insert_participant(conn, event_id, participant_name)

                        for selection in selections:
                            selection_id = selection.get('id')
                            selection_label = selection.get('label')
                            selection_participants = selection.get('participants', [])
                            display_odds = selection.get('displayOdds', {})
                            american_odds = display_odds.get('american', 'N/A')
                            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

                            for sel_participant in selection_participants:
                                if selection_label == participant.get('name'):

                                    if not selection_exists(conn, selection_id):
                                        bet_status = "OPEN"
                                    elif event_status == "NOT_STARTED":
                                        bet_status = "LIVE"
                                    else:
                                        bet_status = "LIVE"

                                    if event_status == "NOT_STARTED":
                                        previous_odds = get_previous_odds(conn, selection_id)
                                        if previous_odds is not None and previous_odds != american_odds:
                                            line_changes.append({
                                                'player': selection_label,
                                                'event': event_name,
                                                'previous_odds': previous_odds,
                                                'current_odds': american_odds
                                            })

                                    insert_selection(conn, selection_id, event_id, selection_label, american_odds, timestamp, bet_status)
                                    total_matches_inserted += 1
                                    break

                print(f"  Found {total_matches} matches ({in_progress_matches} in progress, {upcoming_matches} upcoming, {completed_matches} completed).")

            except requests.exceptions.RequestException as err:
                print(f"Request Error: {err}")
            except json.JSONDecodeError as jerr:
                print(f"JSON Decode Error: {jerr}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")

        conn.commit()
        conn.close()
        print("Database connection closed.")

        print(f"\n--- Run Summary ---")
        print(f"Total matches with data inserted: {total_matches_inserted}")

        if line_changes:
            print(f"Line Changes Detected ({len(line_changes)}):")
            for change in line_changes:
                print(
                    f"  - {change['player']}: {change['previous_odds']} -> {change['current_odds']} ({change['event']})"
                )
        else:
            print("No Line Changes Detected (upcoming matches).")

    except sqlite3.Error as e:
        print(f"Database error: {e}")


if __name__ == "__main__":
    print("Initializing odds update...")
    if RUN_LOOP:
        while True:
            fetch_and_store_data()
            print(f"Sleeping for {SLEEP_INTERVAL} minutes...")
            time.sleep(SLEEP_INTERVAL * 60)
    else:
        fetch_and_store_data()