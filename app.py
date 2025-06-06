import requests
from flask import Flask, jsonify, render_template, request
from threading import Thread
from datetime import datetime
import sqlite3
import subprocess
import sys
import os

app = Flask(__name__)
DB_FILE = "ecfr_full_data.db"

def get_db_connection():
    # Open a connection to the SQLite database
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Calculate word count and checksum for a given string
def calculate_metrics(content):
    words = content.split()
    word_count = len(words)
    checksum = str(hash(content))
    return word_count, checksum

# Look up historical change counts for a given agency using the eCFR API
def get_historical_changes(agency_name):
    SEARCH_BASE_URL = "https://api.ecfr.gov/api/search/v1"
    headers = {"User-Agent": "Mozilla/5.0"}
    params = {"query": agency_name}
    url = f"{SEARCH_BASE_URL}/counts/daily"
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        # Add up all daily counts if available
        if "dates" in data:
            return sum(data["dates"].values())
        return 0
    except Exception as e:
        print(f"Error fetching historical changes for {agency_name}: {e}")
        return 0

# Store agency data in the database
def save_agencies_to_db(agencies):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for agency in agencies.get("agencies", []):
        agency_id = agency.get("id")
        name = agency.get("name")
        content = name or ""
        word_count, checksum = calculate_metrics(content)
        # Get historical change count for this agency
        historical_changes = get_historical_changes(name)
        cursor.execute(
            """
            INSERT OR REPLACE INTO agencies
            (agency_id, name, word_count, checksum, historical_changes, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (agency_id, name, word_count, checksum, historical_changes, current_time)
        )
    conn.commit()
    conn.close()

# Create a fresh database (deletes old one if it exists)
def create_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS agencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agency_id TEXT UNIQUE,
            name TEXT,
            word_count INTEGER,
            checksum TEXT,
            historical_changes INTEGER,
            last_updated TEXT
        )
    ''')
    conn.commit()
    conn.close()

# API endpoint: Get all agencies, sorted by last update
@app.route('/api/agencies')
def get_agencies():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM agencies ORDER BY last_updated DESC").fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

# API endpoint: Get details for a single agency by its ID
@app.route('/api/agency/<agency_id>')
def get_agency(agency_id):
    conn = get_db_connection()
    query = "SELECT * FROM agencies WHERE agency_id = ?"
    row = conn.execute(query, (agency_id,)).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "Agency not found"}), 404

# API endpoint: Start the eCFR data download in a background thread
@app.route('/api/download', methods=['POST'])
def download_data():
    def run_script():
        create_db()
        try:
            subprocess.run([sys.executable, 'download_ecfr.py'], check=True)
        except FileNotFoundError:
            print("Error: download_ecfr.py script not found.")
        except subprocess.CalledProcessError as e:
            print(f"Error: Script execution failed with return code {e.returncode}.")
    Thread(target=run_script).start()
    return jsonify({'status': 'Download started'})

# --- eCFR Search API Integration ---

SEARCH_BASE_URL = "https://api.ecfr.gov/api/search/v1"

# Helper to call eCFR search endpoints
def get_search_data(endpoint, params=None):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"{SEARCH_BASE_URL}/{endpoint}"
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

# API endpoint: Search results
@app.route('/api/search/results')
def search_results():
    query = request.args.get("query", "")
    params = {"query": query}
    data = get_search_data("results", params)
    return jsonify(data)

# API endpoint: Search count
@app.route('/api/search/count')
def search_count():
    query = request.args.get("query", "")
    params = {"query": query}
    data = get_search_data("count", params)
    return jsonify(data)

# API endpoint: Search summary
@app.route('/api/search/summary')
def search_summary():
    query = request.args.get("query", "")
    params = {"query": query}
    data = get_search_data("summary", params)
    return jsonify(data)

# API endpoint: Daily counts for a search query
@app.route('/api/search/counts/daily')
def search_counts_daily():
    query = request.args.get("query", "")
    params = {"query": query}
    data = get_search_data("counts/daily", params)
    return jsonify(data)

# API endpoint: Counts by title for a search query
@app.route('/api/search/counts/titles')
def search_counts_titles():
    query = request.args.get("query", "")
    params = {"query": query}
    data = get_search_data("counts/titles", params)
    return jsonify(data)

# API endpoint: Counts by hierarchy for a search query
@app.route('/api/search/counts/hierarchy')
def search_counts_hierarchy():
    query = request.args.get("query", "")
    params = {"query": query}
    data = get_search_data("counts/hierarchy", params)
    return jsonify(data)

# API endpoint: Search suggestions
@app.route('/api/search/suggestions')
def search_suggestions():
    query = request.args.get("query", "")
    params = {"query": query}
    data = get_search_data("suggestions", params)
    return jsonify(data)

# Home page route (renders index.html template)
@app.route('/')
def home():
    return render_template('index.html')

# Run the Flask app in debug mode if this file is executed directly
if __name__ == '__main__':
    app.run(debug=True)