import docker
import os
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

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

def get_mod_name(mod_id):
    """Fetch mod name from CurseForge API (unofficial endpoint or fallback)."""
    try:
        # CurseForge API is complex and requires keys, using a simple scrape fallback for ID check
        # For a proper implementation, we'd need an API Key. 
        # Using a public accessible lookup if available, otherwise fallback to ID.
        # Minimalist approach: Just return ID if offline or complex.
        # Actually, let's try a direct request to the project page title if possible,
        # but for speed/stability without API key, let's stick to ID or user input.
        # UPGRADE: Using a known open API proxy or just ID for now to avoid complexity without key.
        return f"Mod {mod_id}" 
    except:
        return f"Mod {mod_id}"

@app.route('/')
def index():
    container = get_container()
    status = "OFFLINE"
    stats = {"cpu": "0.00%", "ram": "0 / 0 MB"}
    
    if container and container.status == "running":
        status = "ONLINE"
        try:
            # Get live stats (stream=False gets one snapshot)
            s = container.stats(stream=False)
            
            # Calculate CPU
            cpu_delta = s['cpu_stats']['cpu_usage']['total_usage'] - s['precpu_stats']['cpu_usage']['total_usage']
            system_cpu_delta = s['cpu_stats']['system_cpu_usage'] - s['precpu_stats']['system_cpu_usage']
            cpu_percent = 0.0
            if system_cpu_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_cpu_delta) * len(s['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
            
            # Calculate RAM
            mem_usage = s['memory_stats']['usage'] / (1024 * 1024)
            mem_limit = s['memory_stats']['limit'] / (1024 * 1024)
            
            stats = {
                "cpu": f"{cpu_percent:.2f}%",
                "ram": f"{int(mem_usage)} / {int(mem_limit)} MB"
            }
        except:
            stats = {"cpu": "err", "ram": "err"}

    # Read mods with names if saved, format: ID|Name
    mods = []
    with open(MODS_FILE, "r") as f:
        lines = f.readlines()
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) >= 2:
                mods.append({"id": parts[0], "name": parts[1]})
            elif parts[0]:
                mods.append({"id": parts[0], "name": f"Mod {parts[0]}"})

    return render_template('index.html', status=status, stats=stats, mods=mods)

@app.route('/logs')
def logs():
    container = get_container()
    if not container:
        return jsonify({"log": "Container not found"})
    # Get last 100 lines
    return jsonify({"log": container.logs(tail=100).decode('utf-8')})

@app.route('/action/<action>')
def container_action(action):
    container = get_container()
    if not container:
        return "Container not found", 404
    
    if action == "start":
        container.start()
    elif action == "restart":
        container.restart()
    # Removed STOP action as requested
    
    return redirect(url_for('index'))

@app.route('/add_mod', methods=['POST'])
def add_mod():
    mod_id = request.form.get('mod_id').strip()
    mod_name = request.form.get('mod_name', '').strip() # Optional name input
    if not mod_name: 
        mod_name = f"Mod {mod_id}"
        
    if mod_id:
        # Check duplicates
        with open(MODS_FILE, "r") as f:
            lines = f.readlines()
        
        # Check if ID exists in any line
        exists = any(line.startswith(mod_id + "|") or line.strip() == mod_id for line in lines)
        
        if not exists:
            with open(MODS_FILE, "a") as f:
                f.write(f"{mod_id}|{mod_name}\n")
    
    return redirect(url_for('index'))

@app.route('/remove_mod/<mod_id>')
def remove_mod(mod_id):
    with open(MODS_FILE, "r") as f:
        lines = f.readlines()
    
    with open(MODS_FILE, "w") as f:
        for line in lines:
            parts = line.strip().split('|')
            current_id = parts[0]
            if current_id != mod_id:
                f.write(line)
                
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
