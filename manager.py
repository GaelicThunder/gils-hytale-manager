import docker
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)
client = docker.from_env()

# CONFIGURAZIONE
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

@app.route('/')
def index():
    container = get_container()
    status = "OFFLINE"
    stats = {"cpu": 0, "ram": "0MB"}
    
    if container and container.status == "running":
        status = "ONLINE"
    
    with open(MODS_FILE, "r") as f:
        mods = [line.strip() for line in f.readlines() if line.strip()]

    return render_template('index.html', status=status, mods=mods)

@app.route('/action/<action>')
def container_action(action):
    container = get_container()
    if not container:
        return "Container not found", 404
    
    if action == "start":
        container.start()
    elif action == "stop":
        container.stop()
    elif action == "restart":
        container.restart()
    
    return redirect(url_for('index'))

@app.route('/add_mod', methods=['POST'])
def add_mod():
    mod_id = request.form.get('mod_id').strip()
    if mod_id:
        with open(MODS_FILE, "r") as f:
            current_mods = f.read().splitlines()
        
        if mod_id not in current_mods:
            with open(MODS_FILE, "a") as f:
                f.write(mod_id + "\n")
    
    return redirect(url_for('index'))

@app.route('/remove_mod/<mod_id>')
def remove_mod(mod_id):
    with open(MODS_FILE, "r") as f:
        lines = f.readlines()
    
    with open(MODS_FILE, "w") as f:
        for line in lines:
            if line.strip() != mod_id:
                f.write(line)
                
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
