import docker
import os
import requests
import psutil
import re
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)
client = docker.from_env()

# CONFIGURATION
CONTAINER_NAME = "hytale-server"

# PATH SETUP
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIBLING_DATA = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
HOME_DATA = os.path.expanduser("~/hytale_data")

if os.environ.get("HYTALE_DATA"):
    DATA_PATH = os.environ.get("HYTALE_DATA")
    print(f"[*] Configuration: Using env var path: {DATA_PATH}")
elif os.path.exists(SIBLING_DATA):
    DATA_PATH = SIBLING_DATA
    print(f"[*] Configuration: Found sibling data folder: {DATA_PATH}")
else:
    DATA_PATH = HOME_DATA
    print(f"[*] Configuration: Defaulting to home path: {DATA_PATH}")

# FILES
MODS_FILE = os.path.join(DATA_PATH, "cf_mods.txt")      # Only IDs for the Server
MODS_DB_FILE = os.path.join(DATA_PATH, "mods_db.json")  # ID:Name mapping for UI

# -----------------------------------------------------------------------------
# MIGRATION & INIT
# -----------------------------------------------------------------------------
def init_storage():
    """
    Ensures files exist and fixes the format if 'ID|Name' pollution is found.
    """
    if not os.path.exists(DATA_PATH):
        try:
            os.makedirs(DATA_PATH)
        except:
            pass

    # Load existing DB or create empty
    db = {}
    if os.path.exists(MODS_DB_FILE):
        try:
            with open(MODS_DB_FILE, 'r') as f:
                db = json.load(f)
        except:
            db = {}

    clean_ids = []
    dirty_found = False

    # Check MODS_FILE for corruption (IDs containing '|')
    if os.path.exists(MODS_FILE):
        with open(MODS_FILE, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if '|' in line:
                # Found a dirty line from previous version
                dirty_found = True
                parts = line.split('|')
                m_id = parts[0].strip()
                m_name = parts[1].strip()
                
                if m_id:
                    clean_ids.append(m_id)
                    # Update DB with the recovered name
                    if m_id not in db:
                        db[m_id] = m_name
            else:
                # Clean line
                clean_ids.append(line)

        # If we found dirty lines, rewrite the file cleanly
        if dirty_found:
            print("[*] MIGRATION: Cleaning mod file format...")
            with open(MODS_FILE, 'w') as f:
                for mid in clean_ids:
                    f.write(mid + "\n")
            
            # Save the recovered names to DB
            with open(MODS_DB_FILE, 'w') as f:
                json.dump(db, f, indent=2)
            print("[*] MIGRATION: Complete. Names saved to mods_db.json")

    else:
        # Create empty file
        with open(MODS_FILE, 'w') as f:
            f.write("")
        with open(MODS_DB_FILE, 'w') as f:
            json.dump({}, f)

# Run init immediately
init_storage()

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def get_container():
    try:
        return client.containers.get(CONTAINER_NAME)
    except docker.errors.NotFound:
        return None

def get_mod_name_db(mod_id):
    """Get name from local DB, return None if missing"""
    if os.path.exists(MODS_DB_FILE):
        try:
            with open(MODS_DB_FILE, 'r') as f:
                db = json.load(f)
            return db.get(str(mod_id))
        except:
            return None
    return None

def save_mod_name_db(mod_id, name):
    """Save name to local DB"""
    db = {}
    if os.path.exists(MODS_DB_FILE):
        try:
            with open(MODS_DB_FILE, 'r') as f:
                db = json.load(f)
        except:
            pass
    
    db[str(mod_id)] = name
    with open(MODS_DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

def get_mod_name_auto(mod_id):
    """Fetch from API"""
    try:
        response = requests.get(f"https://api.cfwidget.com/{mod_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("title") or data.get("name")
    except:
        pass
    
    try:
        r = requests.head(f"https://minecraft.curseforge.com/projects/{mod_id}", allow_redirects=True, timeout=5)
        if r.status_code == 200:
            slug = r.url.split('/')[-1]
            return slug.replace('-', ' ').title()
    except:
        pass
    return None

# -----------------------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------------------
@app.route('/')
def index():
    container = get_container()
    status = "OFFLINE"
    stats = {"cpu": "0%", "ram": "0 MB / 0 MB"}
    
    if container and container.status == "running":
        status = "ONLINE"
        try:
            pid = container.attrs['State']['Pid']
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=None)
            mem = proc.memory_info()
            ram_used = mem.rss / (1024 * 1024)
            mem_limit = container.attrs['HostConfig']['Memory'] / (1024 * 1024)
            if mem_limit == 0: mem_limit = 16384 
            stats = {"cpu": f"{cpu:.1f}%", "ram": f"{int(ram_used)} MB / {int(mem_limit)} MB"}
        except:
            stats = {"cpu": "0%", "ram": "Stats Error"}

    mods = []
    if os.path.exists(MODS_FILE):
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
            for line in lines:
                m_id = line.strip()
                if not m_id: continue
                
                # Look in DB first
                name = get_mod_name_db(m_id)
                
                # If missing, fetch and save
                if not name:
                    fetched = get_mod_name_auto(m_id)
                    name = fetched if fetched else f"Mod {m_id}"
                    save_mod_name_db(m_id, name)
                
                mods.append({"id": m_id, "name": name})

    return render_template('index.html', status=status, stats=stats, mods=mods)

@app.route('/logs')
def logs():
    container = get_container()
    if not container:
        return jsonify({"log": "Waiting for container..."})
    try:
        log_content = container.logs(tail=50).decode('utf-8')
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_log = ansi_escape.sub('', log_content)
        return jsonify({"log": clean_log})
    except:
        return jsonify({"log": "Error fetching logs"})

@app.route('/action/<action>')
def container_action(action):
    container = get_container()
    if container:
        if action == "start": container.start()
        elif action == "restart": container.restart()
    return redirect(url_for('index'))

@app.route('/add_mod', methods=['POST'])
def add_mod():
    mod_id = request.form.get('mod_id').strip()
    
    if mod_id and os.path.exists(MODS_FILE):
        # Check duplicates
        with open(MODS_FILE, "r") as f:
            current_ids = [line.strip() for line in f.readlines()]
        
        if mod_id not in current_ids:
            # 1. Add to Server File (ID ONLY)
            with open(MODS_FILE, "a") as f:
                f.write(f"{mod_id}\n")
            
            # 2. Add to Metadata DB (Name)
            name = get_mod_name_auto(mod_id) or f"Mod {mod_id}"
            save_mod_name_db(mod_id, name)
    
    return redirect(url_for('index'))

@app.route('/remove_mod/<mod_id>')
def remove_mod(mod_id):
    if os.path.exists(MODS_FILE):
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
        
        # Rewrite Server File excluding ID
        with open(MODS_FILE, "w") as f:
            for line in lines:
                if line.strip() != mod_id:
                    f.write(line)
    
    # Optional: We don't necessarily need to remove from JSON, 
    # keeping cache is fine, or we could delete it to be clean.
    # Let's keep it simple and leave it in JSON as cache.
                
    return redirect(url_for('index'))

if __name__ == '__main__':
    print(f"[*] Gil's Manager v2.1 - Active Data Path: {DATA_PATH}")
    app.run(host='0.0.0.0', port=5000, debug=True)
