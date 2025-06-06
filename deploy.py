import requests
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from threading import Thread
from datetime import datetime
import sqlite3
import subprocess
import sys
import os

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Needed for session management
DB_FILE = "ecfr_full_data.db"

def get_db_connection():
    # Open a connection to the SQLite database
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# --- User Table and Auth Helpers ---

def create_user_table():
    # Create a simple users table if it doesn't exist
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_user(username, password):
    # Add a new user (password should be hashed in production)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Username already exists
    conn.close()

def verify_user(username, password):
    # Check if user credentials are valid
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = c.fetchone()
    conn.close()
    return user is not None

# --- User Routes ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        add_user(username, password)
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if verify_user(username, password):
            session['username'] = username
            return redirect(url_for('home'))
        else:
            return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# --- Existing code continues below ---

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
    create_user_table()  # Ensure user table exists

# ...existing code for API endpoints and search integration...