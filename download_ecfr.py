#! /usr/bin/env python

import json
import requests
import sqlite3
import time
import os
import hashlib
from datetime import datetime

# --- API Endpoint URLs ---
ECFR_BASE_URL = "https://api.ecfr.gov/api/v1"   # Main eCFR API base
TITLES_URL = f"{ECFR_BASE_URL}/titles"          # List of eCFR titles

# Admin endpoints for agencies and corrections
AGENCIES_URL = "https://api.ecfr.gov/api/admin/v1/agencies.json"
CORRECTIONS_URL_PATTERN = "https://api.ecfr.gov/api/admin/v1/corrections/title/{title}.json"

# Search API base URL
SEARCH_BASE_URL = "https://api.ecfr.gov/api/search/v1"

DB_FILE = "ecfr_full_data.db"

def create_db():
    # Remove old DB if it exists, then create fresh tables
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Table for CFR titles
    c.execute('''
        CREATE TABLE IF NOT EXISTS titles (
            title_number INTEGER PRIMARY KEY,
            title_name TEXT
        )
    ''')

    # Table for CFR parts
    c.execute('''
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_number INTEGER,
            chapter_number INTEGER,
            subchapter_letter TEXT,
            part_number TEXT,
            part_name TEXT,
            part_text TEXT
        )
    ''')

    # Table for agencies, with some metrics
    c.execute('''
        CREATE TABLE IF NOT EXISTS agencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agency_id TEXT UNIQUE,
            name TEXT,
            word_count INTEGER,
            avg_sentence_length REAL,
            checksum TEXT,
            historical_changes INTEGER,
            last_updated TEXT
        )
    ''')

    # Table for corrections to titles
    c.execute('''
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_number INTEGER,
            correction TEXT
        )
    ''')

    # Table for storing search API results
    c.execute('''
        CREATE TABLE IF NOT EXISTS search_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT,
            query TEXT,
            data TEXT,
            last_updated TEXT
        )
    ''')

    # Table for tracking agency history over time
    c.execute('''
        CREATE TABLE IF NOT EXISTS agency_history (
            agency_id TEXT,
            date TEXT,
            word_count INTEGER,
            checksum TEXT,
            PRIMARY KEY (agency_id, date)
        )
    ''')

    conn.commit()
    conn.close()

def get_json(url, headers=None):
    # Helper to fetch JSON from a URL with error handling
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 404:
            print(f"404 Not Found for URL: {url}")
            return None
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None

# --- Title and Part Fetching ---

def get_titles():
    # Get all CFR titles
    data = get_json(TITLES_URL)
    if data is None:
        return []
    return data

def get_title(title_number):
    # Get a specific title's metadata
    return get_json(f"{ECFR_BASE_URL}/title/{title_number}") or {}

def get_chapter(title_number, chapter_number):
    # Get a chapter within a title
    return get_json(f"{ECFR_BASE_URL}/title/{title_number}/chapter/{chapter_number}") or {}

def get_subchapter(title_number, chapter_number, subchapter_letter):
    # Get a subchapter within a chapter
    return get_json(f"{ECFR_BASE_URL}/title/{title_number}/chapter/{chapter_number}/subchapter/{subchapter_letter}") or {}

def get_part(title_number, chapter_number, subchapter_letter, part_number):
    # Get a specific part's data
    return get_json(f"{ECFR_BASE_URL}/title/{title_number}/chapter/{chapter_number}/subchapter/{subchapter_letter}/part/{part_number}") or {}

# --- Agency Fetching and Metrics ---

def fetch_agencies():
    # Download the list of agencies
    return get_json(AGENCIES_URL)

def calculate_metrics(content):
    # Simple word count and checksum for agency names
    words = content.split()
    word_count = len(words)
    checksum = str(hash(content))
    return word_count, checksum

def get_historical_changes(agency_name):
    # Query the search API for daily change counts for an agency
    SEARCH_BASE_URL = "https://api.ecfr.gov/api/search/v1"
    headers = {"User-Agent": "Mozilla/5.0"}
    params = {"query": agency_name}
    url = f"{SEARCH_BASE_URL}/counts/daily"
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        if "dates" in data and data["dates"]:
            return sum(data["dates"].values())
        return 0
    except Exception as e:
        print(f"Error fetching historical changes for {agency_name}: {e}")
        return 0

def save_agencies_to_db(agencies):
    # Store agencies and their metrics in the DB
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for agency in agencies.get("agencies", []):
        agency_id = agency.get("id")
        name = agency.get("name")
        content = name or ""
        word_count, checksum = calculate_metrics(content)
        # Fetch historical changes count for this agency
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

# --- Corrections Fetching ---

def get_corrections(title_number):
    # Download corrections for a given title
    url = CORRECTIONS_URL_PATTERN.format(title=title_number)
    data = get_json(url)
    if data is None:
        return []
    corrections = data.get("corrections", [])
    return corrections[:50]  # Limit to 50 for demo

def save_corrections(title_number, corrections):
    # Store corrections in the DB
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for corr in corrections:
        cursor.execute(
            "INSERT INTO corrections (title_number, correction) VALUES (?, ?)",
            (title_number, json.dumps(corr))
        )
    conn.commit()
    conn.close()

# --- Search API Fetching ---

def get_search_data(endpoint, params=None):
    # Helper to call search API endpoints
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"{SEARCH_BASE_URL}/{endpoint}"
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching search endpoint {endpoint}: {e}")
        return {"error": str(e)}

def save_search_data(endpoint, query, data):
    # Store search API results in the DB
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO search_data (endpoint, query, data, last_updated)
        VALUES (?, ?, ?, ?)
        """,
        (endpoint, query, json.dumps(data), current_time)
    )
    conn.commit()
    conn.close()

# --- Miscellaneous Helpers ---

def get_chapters_for_agency(agency_name):
    # Find chapters that mention a given agency (not used in main)
    chapters = []
    for title_num in range(1, 51):  # CFR Titles 1-50
        url = f"https://api.ecfr.gov/api/v1/title/{title_num}"
        data = requests.get(url).json()
        for node in data.get("children", []):
            if agency_name.lower() in node.get("node_label", "").lower():
                chapters.append({
                    "title": title_num,
                    "chapter": node.get("node_number"),
                    "label": node.get("node_label")
                })
    return chapters

def get_word_count_for_chapter(title, chapter):
    # Calculate total word count for all sections in a chapter (not used in main)
    url = f"https://api.ecfr.gov/api/v1/title/{title}/chapter/{chapter}"
    data = requests.get(url).json()
    word_count = 0
    for part in data.get("children", []):
        for section in part.get("children", []):
            section_url = f"https://api.ecfr.gov/api/v1/title/{title}/part/{part['node_number']}/section/{section['node_number']}"
            section_data = requests.get(section_url).json()
            text = section_data.get("attributes", {}).get("text", "")
            word_count += len(text.split())
    return word_count

def get_section_versions(title, part, section):
    # Get all versions for a section (not used in main)
    url = f"https://api.ecfr.gov/api/v1/title/{title}/part/{part}/section/{section}/versions"
    return requests.get(url).json().get("versions", [])

def get_section_text_by_version(title, part, section, version_date):
    # Get section text for a specific version (not used in main)
    url = f"https://api.ecfr.gov/api/v1/title/{title}/part/{part}/section/{section}/version/{version_date}"
    return requests.get(url).json().get("attributes", {}).get("text", "")

def get_wordcount_and_checksum(text):
    # Calculate word count and SHA256 checksum for a text
    word_count = len(text.split())
    checksum = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return word_count, checksum

def get_agency_checksum(section_texts):
    # Combine all section texts and hash them (not used in main)
    combined = " ".join(section_texts)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

# --- Main Download Routine ---

def main():
    create_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    print("Fetching titles...")
    titles = get_titles()
    print(f"Found {len(titles)} titles")
    for title in titles:
        title_number = title.get("titleNumber")
        title_name = title.get("titleName")
        print(f"\nProcessing Title {title_number}: {title_name}")
        c.execute("INSERT OR IGNORE INTO titles (title_number, title_name) VALUES (?, ?)",
                  (title_number, title_name))
        conn.commit()

        # Download corrections for this title
        corrections = get_corrections(title_number)
        print(f"  Found {len(corrections)} corrections for Title {title_number}")
        save_corrections(title_number, corrections)

        # Example: only fetch chapter 1, subchapter 'A' for demo
        chapter_number = 1
        subchapter_letter = 'A'
        chapter_data = get_chapter(title_number, chapter_number)
        print(f"  Fetched chapter data: {chapter_data.get('chapterName', 'N/A')}")
        parts = get_json(f"{ECFR_BASE_URL}/title/{title_number}/chapter/{chapter_number}/subchapter/{subchapter_letter}/parts") or []
        print(f"  Found {len(parts)} parts in Chapter {chapter_number}, Subchapter {subchapter_letter}")
        for part in parts:
            part_number = part.get("partNumber")
            part_name = part.get("name", "")
            print(f"    Fetching Part {part_number} - {part_name}")
            part_data = get_part(title_number, chapter_number, subchapter_letter, part_number)
            part_text = part_data.get("text", "")
            c.execute('''
                INSERT INTO parts (title_number, chapter_number, subchapter_letter, part_number, part_name, part_text)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title_number, chapter_number, subchapter_letter, part_number, part_name, part_text))
            conn.commit()
            time.sleep(0.1)  # Be polite to the API
        time.sleep(0.3)

    print("\nFetching agencies...")
    agencies_data = fetch_agencies()
    if agencies_data:
        num_agencies = len(agencies_data.get("agencies", []))
        print(f"Fetched {num_agencies} agencies.")
        save_agencies_to_db(agencies_data)
        print(f"Saved {num_agencies} agencies to the database.")

    # --- Fetch and store some search API endpoints for demo purposes ---
    search_endpoints = [
        "results",
        "count",
        "summary",
        "counts/daily",
        "counts/titles",
        "counts/hierarchy",
        "suggestions"
    ]
    # Use an empty query for demonstration
    for endpoint in search_endpoints:
        params = {"query": ""}
        search_data = get_search_data(endpoint, params)
        print(f"Fetched search data for {endpoint}: {str(search_data)[:100]}...")
        save_search_data(endpoint, params.get("query", ""), search_data)
        time.sleep(0.2)

    conn.close()
    print("\n✅ Data download and storage complete.")

if __name__ == "__main__":
    main()