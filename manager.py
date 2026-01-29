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
MODS_FILE = os.path.join(DATA_PATH, "cf_mods.txt")      # IDs only
MODS_DB_FILE = os.path.join(DATA_PATH, "mods_db.json")  # Metadata
SECRETS_FILE = os.path.join(DATA_PATH, "secrets.json")  # API Keys

# -----------------------------------------------------------------------------
# INIT & UTILS
# -----------------------------------------------------------------------------
def init_storage():
    if not os.path.exists(DATA_PATH):
        try: os.makedirs(DATA_PATH)
        except: pass
    
    for fpath in [MODS_FILE, MODS_DB_FILE, SECRETS_FILE]:
        if not os.path.exists(fpath):
            with open(fpath, 'w') as f:
                if fpath.endswith('.json'): json.dump({}, f)
                else: f.write("")

init_storage()

def get_container():
    try:
        return client.containers.get(CONTAINER_NAME)
    except docker.errors.NotFound:
        return None

def get_api_key():
    key = os.environ.get("HYTALE_CURSEFORGE_API_KEY")
    if key: return key
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r') as f:
                data = json.load(f)
                return data.get("cf_api_key", "")
        except: pass
    return ""

def save_api_key(key):
    data = {}
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r') as f: data = json.load(f)
        except: pass
    data["cf_api_key"] = key.strip()
    with open(SECRETS_FILE, 'w') as f: json.dump(data, f, indent=2)

def get_mod_name_db(mod_id):
    if os.path.exists(MODS_DB_FILE):
        try:
            with open(MODS_DB_FILE, 'r') as f:
                db = json.load(f)
            return db.get(str(mod_id))
        except: pass
    return None

def save_mod_name_db(mod_id, name):
    db = {}
    if os.path.exists(MODS_DB_FILE):
        try:
            with open(MODS_DB_FILE, 'r') as f: db = json.load(f)
        except: pass
    db[str(mod_id)] = name
    with open(MODS_DB_FILE, 'w') as f: json.dump(db, f, indent=2)

def get_mod_name_auto(mod_id):
    try:
        response = requests.get(f"https://api.cfwidget.com/{mod_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("title") or data.get("name")
    except: pass
    try:
        r = requests.head(f"https://minecraft.curseforge.com/projects/{mod_id}", allow_redirects=True, timeout=5)
        if r.status_code == 200:
            slug = r.url.split('/')[-1]
            return slug.replace('-', ' ').title()
    except: pass
    return None

def scan_mod_errors(container, mod_ids):
    """Scan container logs for specific failure patterns."""
    failed_ids = set()
    if not container: return failed_ids
    
    try:
        # Read logs (tail 2000 lines should cover startup)
        logs = container.logs(tail=2000).decode('utf-8', errors='ignore')
        
        # Regex to match: WARNING: failed to install mod 123456
        # Matches your exact log format
        error_pattern = re.compile(r"failed to install mod\s+(\d+)")
        
        found_errors = error_pattern.findall(logs)
        for err_id in found_errors:
            failed_ids.add(str(err_id))
            
    except:
        pass
    return failed_ids

# -----------------------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------------------
@app.route('/')
def index():
    container = get_container()
    status = "OFFLINE"
    stats = {"cpu": "0%", "ram": "0 MB / 0 MB"}
    failed_mods = set()
    
    mods_list = []
    # Read mods first to get IDs
    if os.path.exists(MODS_FILE):
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
            for line in lines:
                m_id = line.strip()
                if not m_id: continue
                mods_list.append(m_id)

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
            
            # Scan for errors
            failed_mods = scan_mod_errors(container, mods_list)
        except:
            stats = {"cpu": "0%", "ram": "Stats Error"}

    # Build final object
    mods_display = []
    for m_id in mods_list:
        name = get_mod_name_db(m_id)
        if not name:
            fetched = get_mod_name_auto(m_id)
            name = fetched if fetched else f"Mod {m_id}"
            save_mod_name_db(m_id, name)
        
        mods_display.append({
            "id": m_id,
            "name": name,
            "has_error": (m_id in failed_mods)
        })

    api_key_set = bool(get_api_key())
    return render_template('index.html', status=status, stats=stats, mods=mods_display, api_key_set=api_key_set)

@app.route('/logs')
def logs():
    container = get_container()
    if not container: return jsonify({"log": "Waiting for container..."})
    try:
        log_content = container.logs(tail=50).decode('utf-8')
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_log = ansi_escape.sub('', log_content)
        return jsonify({"log": clean_log})
    except: return jsonify({"log": "Error fetching logs"})

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
        with open(MODS_FILE, "r") as f:
            current = [l.strip() for l in f.readlines()]
        if mod_id not in current:
            with open(MODS_FILE, "a") as f: f.write(f"{mod_id}\n")
            name = get_mod_name_auto(mod_id) or f"Mod {mod_id}"
            save_mod_name_db(mod_id, name)
    return redirect(url_for('index'))

@app.route('/remove_mod/<mod_id>')
def remove_mod(mod_id):
    if os.path.exists(MODS_FILE):
        with open(MODS_FILE, "r") as f: lines = f.readlines()
        with open(MODS_FILE, "w") as f:
            for line in lines:
                if line.strip() != mod_id: f.write(line)
    return redirect(url_for('index'))

@app.route('/save_key', methods=['POST'])
def save_key():
    key = request.form.get('api_key', '').strip()
    if key: save_api_key(key)
    return redirect(url_for('index'))

if __name__ == '__main__':
    print(f"[*] Gil's Manager v2.4 - Active Data Path: {DATA_PATH}")
    app.run(host='0.0.0.0', port=5000, debug=True)
