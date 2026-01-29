# Gil's Hytale Manager

Lightweight Python Flask panel to manage Hytale Sanasol Docker server with CurseForge mod integration.

## Features

- Real-time server status monitoring (CPU/RAM)
- Live Console Logs streaming
- Start/Restart Docker container controls
- CurseForge mod injection via Project ID (Auto-name detection)
- Modern "Glassmorphism" Dark UI
- Data separation: Clean ID lists for Docker, metadata for UI

## Installation

### 1. Folder Structure
Ensure you have this structure:
```
project_root/
├── data/                  # Where cf_mods.txt lives
│   └── cf_mods.txt
└── gils-hytale-manager/   # This repo
    └── manager.py
```

### 2. Setup Manager
```bash
cd gils-hytale-manager
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install psutil
```

### 3. Run Docker Server
Run this from your project root (parent of `data` folder):

```bash
sudo docker run -d \
  --name hytale-server \
  -p 25565:5520/udp \
  -v ./data:/data \
  -v ./data/cf_mods.txt:/data/cf_mods.txt \
  --restart unless-stopped \
  -e HYTALE_EULA=true \
  -e HYTALE_AUTH_BACKEND="sanasol" \
  -e HYTALE_ONLINE_MODE=false \
  -e CF_MODS_FILE="/data/cf_mods.txt" \
  -e JVM_OPTS="-Xms12G -Xmx12G -XX:+UseG1GC -XX:MaxGCPauseMillis=50 -XX:+AlwaysPreTouch" \
  --memory="14g" \
  ghcr.io/sanasol/hytale-server-docker:latest
```

### 4. Launch Manager
```bash
cd gils-hytale-manager
python manager.py
```
Access at: `http://YOUR_RADXA_IP:5000`

## Usage

1. Find mods on [CurseForge](https://www.curseforge.com/minecraft/mc-mods)
2. Copy the Project ID
3. Paste into the manager and click "INJECT"
4. Click "REBOOT" to apply changes. The server will download mods on startup.

## License
MIT
