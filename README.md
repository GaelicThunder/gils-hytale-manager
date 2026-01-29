# Gil's Hytale Manager

Lightweight Python Flask panel to manage Hytale Sanasol Docker server with CurseForge mod integration.

## Features

- Real-time server status monitoring
- Start/Stop/Restart Docker container controls
- CurseForge mod injection via Project ID
- Cyberpunk terminal-style UI

## Installation

### 1. Setup Environment

```bash
mkdir ~/hytale-manager
cd ~/hytale-manager
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Prepare Data Directory

```bash
mkdir -p ~/hytale_data
touch ~/hytale_data/cf_mods.txt
```

### 3. Configure Docker Container

Stop and remove existing container:

```bash
docker stop hytale-server && docker rm hytale-server
```

Run with proper volume mapping:

```bash
docker run -d \
  --name hytale-server \
  -p 25565:5520/udp \
  -v ~/hytale_data:/data \
  -v ~/hytale_data/cf_mods.txt:/data/cf_mods.txt \
  --restart unless-stopped \
  -e HYTALE_EULA=true \
  -e HYTALE_AUTH_BACKEND="sanasol" \
  -e CF_MODS_FILE="/data/cf_mods.txt" \
  -e JVM_OPTS="-Xms12G -Xmx12G -XX:+UseG1GC" \
  --memory="14g" \
  ghcr.io/sanasol/hytale-server-docker:latest
```

### 4. Launch Manager

```bash
sudo python3 manager.py
```

Access at: `http://YOUR_RADXA_IP:5000`

## Usage

1. Find mods on [CurseForge](https://www.curseforge.com/minecraft/mc-mods)
2. Copy the Project ID (number in the right sidebar)
3. Paste into the manager and click "INJECT"
4. Click "REBOOT" to apply changes
5. Sanasol will download the mod automatically

## Requirements

- Python 3.8+
- Docker
- Radxa or similar SBC with 16GB+ RAM
- Docker permissions (add user to docker group or run with sudo)

## License

MIT
