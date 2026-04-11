#!/bin/bash
# PicoClaw Phase 2 - Termux Worker Installation Script
# Run this on your Android device with Termux

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

WORKER_DIR="$HOME/hax-mind-worker"
WINDOWS_HOST=""
SHARED_SECRET=""

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_termux() {
    if [ -z "$TERMUX_VERSION" ]; then
        log_error "This script must run on Termux (Android terminal emulator)"
        exit 1
    fi
    log_info "Termux version: $TERMUX_VERSION"
}

install_packages() {
    log_info "Updating packages..."
    pkg update -y
    pkg upgrade -y
    
    log_info "Installing required packages..."
    pkg install -y git python python-pip openssh
    
    log_info "Packages installed successfully"
}

setup_worker_directory() {
    log_info "Setting up worker directory at $WORKER_DIR"
    mkdir -p "$WORKER_DIR"
    mkdir -p "$WORKER_DIR/logs"
    mkdir -p "$WORKER_DIR/tmp"
    cd "$WORKER_DIR"
}

configure_environment() {
    log_info "Configuring worker environment"
    
    # Prompt for Windows host IP/hostname
    if [ -z "$WINDOWS_HOST" ]; then
        read -p "Enter Windows HAX-Mind host (IP or hostname): " WINDOWS_HOST
    fi
    
    # Prompt for shared secret
    if [ -z "$SHARED_SECRET" ]; then
        read -s -p "Enter PICOCLAW_SHARED_SECRET (from Windows .env): " SHARED_SECRET
        echo ""
    fi
    
    # Create worker config
    cat > "$WORKER_DIR/worker.conf" << EOF
# PicoClaw Worker Configuration
WORKER_ID=termux-main
PLATFORM=termux
WINDOWS_HOST=$WINDOWS_HOST
PICOCLAW_SHARED_SECRET=$SHARED_SECRET
HEARTBEAT_INTERVAL_SECONDS=60
CLAIM_INTERVAL_SECONDS=30
LOG_LEVEL=INFO
EOF
    
    chmod 600 "$WORKER_DIR/worker.conf"
    log_info "Worker configuration saved to $WORKER_DIR/worker.conf"
}

create_worker_script() {
    log_info "Creating worker scripts"
    
    # Create main worker script
    cat > "$WORKER_DIR/worker.py" << 'PYTHON_EOF'
#!/usr/bin/env python3
"""
PicoClaw Phase 2 - Termux Worker
Lightweight worker for remote execution bridge
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

WORKER_DIR = Path(__file__).resolve().parent
CONFIG_FILE = WORKER_DIR / "worker.conf"
LOG_FILE = WORKER_DIR / "logs" / "worker.log"

def log(msg: str):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_config() -> dict:
    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    config[key] = value
    # Also check environment
    for key in ["WORKER_ID", "PLATFORM", "WINDOWS_HOST", "PICOCLAW_SHARED_SECRET", 
                "HEARTBEAT_INTERVAL_SECONDS", "CLAIM_INTERVAL_SECONDS"]:
        if os.environ.get(key):
            config[key] = os.environ.get(key)
    return config

def send_heartbeat(config: dict) -> bool:
    """Send heartbeat to Windows HAX-Mind control plane"""
    host = config.get("WINDOWS_HOST", "")
    secret = config.get("PICOCLAW_SHARED_SECRET", "")
    worker_id = config.get("WORKER_ID", "termux-main")
    
    if not host or not secret:
        log("[ERROR] Missing WINDOWS_HOST or PICOCLAW_SHARED_SECRET")
        return False
    
    # For now, we use a simple HTTP POST (to be implemented on Windows side)
    # This is a placeholder for the actual implementation
    url = f"http://{host}:8080/api/v1/worker/heartbeat"
    payload = {
        "worker_id": worker_id,
        "platform": config.get("PLATFORM", "termux"),
        "timestamp": datetime.now().isoformat(),
        "capabilities": ["read_only_repo", "heartbeat"],
        "status": "online"
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Worker-Secret": secret
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log(f"[HEARTBEAT] Sent to {url}, status: {resp.status}")
            return True
    except urllib.error.URLError as e:
        log(f"[HEARTBEAT ERROR] {e}")
        return False
    except Exception as e:
        log(f"[HEARTBEAT ERROR] {e}")
        return False

def run_worker_loop(config: dict):
    """Main worker loop"""
    worker_id = config.get("WORKER_ID", "termux-main")
    heartbeat_interval = int(config.get("HEARTBEAT_INTERVAL_SECONDS", 60))
    
    log(f"[START] Worker {worker_id} started")
    log(f"[CONFIG] Heartbeat interval: {heartbeat_interval}s")
    
    while True:
        try:
            # Send heartbeat
            send_heartbeat(config)
            
            # TODO: Claim and execute jobs
            
            time.sleep(heartbeat_interval)
        except KeyboardInterrupt:
            log("[STOP] Worker stopped by user")
            break
        except Exception as e:
            log(f"[ERROR] {e}")
            time.sleep(5)

def main():
    parser = argparse.ArgumentParser(description="PicoClaw Termux Worker")
    parser.add_argument("command", choices=["run", "heartbeat", "config"], 
                       help="Command to execute")
    parser.add_argument("--worker-id", default=None, help="Worker ID")
    parser.add_argument("--secret", default=None, help="Shared secret")
    parser.add_argument("--host", default=None, help="Windows host")
    
    args = parser.parse_args()
    config = load_config()
    
    # Override config with CLI args
    if args.worker_id:
        config["WORKER_ID"] = args.worker_id
    if args.secret:
        config["PICOCLAW_SHARED_SECRET"] = args.secret
    if args.host:
        config["WINDOWS_HOST"] = args.host
    
    if args.command == "config":
        print("Current configuration:")
        for key, value in config.items():
            if "SECRET" in key:
                print(f"  {key}={'*' * 8}")
            else:
                print(f"  {key}={value}")
    elif args.command == "heartbeat":
        success = send_heartbeat(config)
        sys.exit(0 if success else 1)
    elif args.command == "run":
        run_worker_loop(config)

if __name__ == "__main__":
    main()
PYTHON_EOF

    chmod +x "$WORKER_DIR/worker.py"
    log_info "Worker script created at $WORKER_DIR/worker.py"
}

create_termux_boot_script() {
    log_info "Creating Termux:Boot auto-start script"
    
    mkdir -p "$HOME/.termux/boot"
    
    cat > "$HOME/.termux/boot/start-hax-mind-worker.sh" << EOF
#!/data/data/com.termux/files/usr/bin/sh
# Auto-start HAX-Mind worker on boot
termux-wake-lock
cd "$WORKER_DIR"
python3 "$WORKER_DIR/worker.py" run >> "$WORKER_DIR/logs/boot.log" 2>&1 &
EOF
    
    chmod +x "$HOME/.termux/boot/start-hax-mind-worker.sh"
    log_info "Boot script created at $HOME/.termux/boot/start-hax-mind-worker.sh"
    log_warn "Install Termux:Boot app from F-Droid for auto-start to work"
}

show_next_steps() {
    echo ""
    echo "=========================================="
    log_info "Installation Complete!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Review configuration: cat $WORKER_DIR/worker.conf"
    echo "2. Test heartbeat: python3 $WORKER_DIR/worker.py heartbeat"
    echo "3. Start worker: python3 $WORKER_DIR/worker.py run"
    echo "4. For auto-start on boot, install Termux:Boot from F-Droid"
    echo ""
    echo "Worker directory: $WORKER_DIR"
    echo "Logs: $WORKER_DIR/logs/worker.log"
    echo ""
}

# Main installation flow
main() {
    echo "=========================================="
    echo "  PicoClaw Phase 2 - Termux Worker Setup"
    echo "=========================================="
    echo ""
    
    check_termux
    install_packages
    setup_worker_directory
    configure_environment
    create_worker_script
    create_termux_boot_script
    show_next_steps
}

# Allow overriding via environment
while getopts "h:s:" opt; do
    case $opt in
        h) WINDOWS_HOST="$OPTARG" ;;
        s) SHARED_SECRET="$OPTARG" ;;
        *) echo "Usage: $0 [-h WINDOWS_HOST] [-s SHARED_SECRET]"; exit 1 ;;
    esac
done

main
