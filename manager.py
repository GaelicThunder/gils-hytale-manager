import docker
import os
import requests
import psutil
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)
client = docker.from_env()

# CONFIGURATION
CONTAINER_NAME = "hytale-server"
DATA_PATH = os.path.expanduser("~/hytale_data")
MODS_FILE = os.path.join(DATA_PATH, "cf_mods.txt")

if not os.path.exists(MODS_FILE):
    with open(MODS_FILE, "w") as f:
        f.write("")

def get_container():
    try:
        return client.containers.get(CONTAINER_NAME)
    except docker.errors.NotFound:
        return None

def get_mod_name_auto(mod_id):
    """
    Attempts to fetch the mod name automatically using public APIs.
    """
    # Method 1: CFWidget API (Public, no key required for basic info)
    try:
        response = requests.get(f"https://api.cfwidget.com/{mod_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("title") or data.get("name")
    except:
        pass

    # Method 2: Scrape redirection from legacy ID URL
    try:
        # Curseforge legacy project URL redirects to the new slug-based URL
        # We can extract a readable name from the URL slug
        r = requests.head(f"https://minecraft.curseforge.com/projects/{mod_id}", allow_redirects=True, timeout=5)
        if r.status_code == 200:
            # URL format: .../minecraft/mc-mods/mod-name-slug
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
            # Use PSUTIL for accurate stats via PID
            # Docker stats API is slow and hard to parse for single snapshots
            pid = container.attrs['State']['Pid']
            proc = psutil.Process(pid)
            
            # CPU (interval=None is non-blocking)
            cpu = proc.cpu_percent(interval=None)
            
            # RAM
            mem = proc.memory_info()
            ram_used = mem.rss / (1024 * 1024) # MB
            
            # Limit (from docker attrs)
            mem_limit = container.attrs['HostConfig']['Memory'] / (1024 * 1024)
            if mem_limit == 0: mem_limit = 16384 # Fallback 16GB if unconstrained
            
            stats = {
                "cpu": f"{cpu:.1f}%",
                "ram": f"{int(ram_used)} MB / {int(mem_limit)} MB"
            }
        except Exception as e:
            stats = {"cpu": "0%", "ram": "Stats Error"}

    # Read mods
    mods = []
    with open(MODS_FILE, "r") as f:
        lines = f.readlines()
        for line in lines:
            parts = line.strip().split('|')
            m_id = parts[0]
            m_name = parts[1] if len(parts) > 1 else "Unknown Mod"
            
            # If name is missing/unknown, try to fetch it now and update file
            if len(parts) == 1 or m_name == "Unknown Mod" or m_name == f"Mod {m_id}":
                fetched_name = get_mod_name_auto(m_id)
                if fetched_name:
                    m_name = fetched_name
                    # Note: We aren't writing back to file here to avoid blocking page load
                    # Ideally we would update the file, but let's keep it simple for now
            
            if m_id:
                mods.append({"id": m_id, "name": m_name})

    return render_template('index.html', status=status, stats=stats, mods=mods)

@app.route('/logs')
def logs():
    container = get_container()
    if not container:
        return jsonify({"log": "Waiting for container..."})
    try:
        # Fetch last 50 lines
        log_content = container.logs(tail=50).decode('utf-8')
        # Remove ANSI color codes for clean display if needed, but modern browsers might handle them 
        # or we display raw. Let's strip for safety in basic textarea
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
    
    if mod_id:
        # Check duplicates
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
        
        # Check if ID exists
        exists = any(line.split('|')[0] == mod_id for line in lines)
        
        if not exists:
            # Fetch name
            name = get_mod_name_auto(mod_id) or f"Mod {mod_id}"
            
            with open(MODS_FILE, "a") as f:
                f.write(f"{mod_id}|{name}\n")
    
    return redirect(url_for('index'))

@app.route('/remove_mod/<mod_id>')
def remove_mod(mod_id):
    with open(MODS_FILE, "r") as f:
        lines = f.readlines()
    
    with open(MODS_FILE, "w") as f:
        for line in lines:
            if line.split('|')[0] != mod_id:
                f.write(line)
                
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
