import docker
import os
import requests
import psutil
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)
client = docker.from_env()

# CONFIGURATION
CONTAINER_NAME = "hytale-server"  # <--- FIXED: Restored missing variable

# Determine where the data folder is.
# Priority:
# 1. Environment Variable HYTALE_DATA
# 2. Sibling directory "../data" (relative to this script) -> Matches your structure
# 3. Default "~/hytale_data"

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

MODS_FILE = os.path.join(DATA_PATH, "cf_mods.txt")

# Ensure file exists
if not os.path.exists(MODS_FILE):
    print(f"[*] Creating new mods file at: {MODS_FILE}")
    try:
        with open(MODS_FILE, "w") as f:
            f.write("")
    except PermissionError:
        print(f"[!] ERROR: Permission denied writing to {MODS_FILE}. Check folder permissions.")

def get_container():
    try:
        return client.containers.get(CONTAINER_NAME)
    except docker.errors.NotFound:
        return None

def get_mod_name_auto(mod_id):
    """
    Attempts to fetch the mod name automatically using public APIs.
    """
    # Method 1: CFWidget API
    try:
        response = requests.get(f"https://api.cfwidget.com/{mod_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("title") or data.get("name")
    except:
        pass

    # Method 2: Scrape redirection
    try:
        r = requests.head(f"https://minecraft.curseforge.com/projects/{mod_id}", allow_redirects=True, timeout=5)
        if r.status_code == 200:
            slug = r.url.split('/')[-1]
            return slug.replace('-', ' ').title()
    except:
        pass
        
    return None

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
            
            stats = {
                "cpu": f"{cpu:.1f}%",
                "ram": f"{int(ram_used)} MB / {int(mem_limit)} MB"
            }
        except Exception:
            stats = {"cpu": "0%", "ram": "Stats Error"}

    mods = []
    if os.path.exists(MODS_FILE):
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
            for line in lines:
                parts = line.strip().split('|')
                if not parts[0]: continue
                
                m_id = parts[0]
                m_name = parts[1] if len(parts) > 1 else f"Mod {m_id}"
                
                # Auto-resolve name if missing
                if len(parts) == 1 or m_name == f"Mod {m_id}":
                    fetched = get_mod_name_auto(m_id)
                    if fetched: m_name = fetched
                
                mods.append({"id": m_id, "name": m_name})

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
    if not container:
        return "Container not found", 404
    
    if action == "start":
        container.start()
    elif action == "restart":
        container.restart()
    
    return redirect(url_for('index'))

@app.route('/add_mod', methods=['POST'])
def add_mod():
    mod_id = request.form.get('mod_id').strip()
    
    if mod_id and os.path.exists(MODS_FILE):
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
        
        exists = any(line.split('|')[0] == mod_id for line in lines)
        
        if not exists:
            name = get_mod_name_auto(mod_id) or f"Mod {mod_id}"
            with open(MODS_FILE, "a") as f:
                f.write(f"{mod_id}|{name}\n")
    
    return redirect(url_for('index'))

@app.route('/remove_mod/<mod_id>')
def remove_mod(mod_id):
    if os.path.exists(MODS_FILE):
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
        
        with open(MODS_FILE, "w") as f:
            for line in lines:
                if line.split('|')[0] != mod_id:
                    f.write(line)
                
    return redirect(url_for('index'))

if __name__ == '__main__':
    print(f"[*] Gil's Manager v2.0 - Active Data Path: {DATA_PATH}")
    app.run(host='0.0.0.0', port=5000, debug=True)
