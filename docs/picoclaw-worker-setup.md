# PicoClaw Phase 2 - Worker Setup Guide

## Overview

This guide walks you through setting up a PicoClaw worker on Termux (Android) to connect with your Windows HAX-Mind control plane.

## Prerequisites

- Android device with Termux installed
- Windows HAX-Mind running on the same network (or accessible via internet)
- Shared secret configured in Windows `.env` file

## Architecture

```
┌─────────────────┐     heartbeat/job queue     ┌──────────────────┐
│  Windows PC     │  ═══════════════════════►   │  Android/Termux  │
│  HAX-Mind       │                             │  PicoClaw Worker │
│  (Control Plane)│  ◄═══════════════════════   │                  │
└─────────────────┘        results/logs         └──────────────────┘
```

## Step 1: Prepare Windows Control Plane

1. Ensure your Windows HAX-Mind has the shared secret configured in `.env`:

```bash
# In .env or .env.txt
PICOCLAW_SHARED_SECRET=your_long_random_secret_here
PICOCLAW_WORKER_ID=termux-main
```

2. Get your Windows IP address:

```powershell
# PowerShell
Get-NetIPAddress | Where-Object {$_.AddressFamily -eq "IPv4" -and $_.IPAddress -notlike "127.*"} | Select-Object IPAddress
```

3. Note down the IP address (e.g., `192.168.1.100`)

## Step 2: Install Worker on Termux

### Option A: Automatic Installation

1. Transfer the install script to your Android device:

```bash
# On Windows (adjust path as needed)
adb push scripts/install-termux-worker.sh /sdcard/Download/
```

2. On Termux, run:

```bash
cp /sdcard/Download/install-termux-worker.sh ~
cd ~
chmod +x install-termux-worker.sh
./install-termux-worker.sh
```

3. Enter your Windows host IP and shared secret when prompted.

### Option B: Manual Installation

1. Update and install packages:

```bash
pkg update && pkg upgrade -y
pkg install git python -y
```

2. Create worker directory:

```bash
mkdir -p ~/hax-mind-worker/logs
cd ~/hax-mind-worker
```

3. Create configuration file:

```bash
cat > worker.conf << 'EOF'
WORKER_ID=termux-main
PLATFORM=termux
WINDOWS_HOST=192.168.1.100:8080
PICOCLAW_SHARED_SECRET=your_secret_here
HEARTBEAT_INTERVAL_SECONDS=60
CLAIM_INTERVAL_SECONDS=30
EOF

chmod 600 worker.conf
```

4. Copy the worker.py script from `scripts/install-termux-worker.sh` (extract the Python code between `cat > "$WORKER_DIR/worker.py" << 'PYTHON_EOF'` and `PYTHON_EOF`).

## Step 3: Test Connection

### Test from Termux

```bash
cd ~/hax-mind-worker
python3 worker.py heartbeat
```

Expected output on success:
```
[2026-04-11T...] [HEARTBEAT] Sent to http://192.168.1.100:8080/api/v1/worker/heartbeat, status: 200
```

### Test from Windows

```powershell
# PowerShell
$env:PICOCLAW_SHARED_SECRET="your_secret_here"
.\.venv\Scripts\python.exe jobs\picoclaw_worker.py heartbeat --worker-id termux-test --platform termux
```

## Step 4: Start Worker

### Manual Start

```bash
cd ~/hax-mind-worker
python3 worker.py run
```

The worker will run continuously, sending heartbeats every 60 seconds.

### Auto-Start on Boot

1. Install Termux:Boot from F-Droid
2. The install script already created `~/.termux/boot/start-hax-mind-worker.sh`
3. Open Termux:Boot app once to grant permissions
4. The worker will auto-start on device boot

## Step 5: Verify Connection

On Windows, check the status:

```powershell
.\.venv\Scripts\python.exe -c "from engine.picoclaw_manager import picoclaw_status; import json; print(json.dumps(picoclaw_status(), indent=2))"
```

You should see:
- `status`: `worker_connected`
- `readiness.termux_worker_installed`: `true`
- `readiness.heartbeat_endpoint`: `true`

## Troubleshooting

### Connection Refused

1. Check Windows firewall - allow port 8080 (or your configured port)
2. Verify Windows IP address hasn't changed
3. Ensure both devices are on the same network

### Authentication Failed

1. Verify `PICOCLAW_SHARED_SECRET` matches exactly on both sides
2. Check for extra whitespace or newline characters
3. Regenerate secret if needed and update both `.env` and `worker.conf`

### Worker Not Auto-Starting

1. Check Termux:Boot is installed from F-Droid (not Play Store)
2. Run the boot script manually to see errors:
   ```bash
   bash ~/.termux/boot/start-hax-mind-worker.sh
   ```
3. Check logs: `cat ~/hax-mind-worker/logs/boot.log`

## Security Notes

- Keep `PICOCLAW_SHARED_SECRET` secure and outside git
- Use a strong, random secret (48+ characters recommended)
- Consider using a VPN if accessing over the internet
- The worker runs with read-only permissions initially
- Enable write operations only after thorough testing

## Next Steps

After successful worker connection:

1. Test job queue with dry-run jobs
2. Enable read-only remote commands
3. Implement rollback policy verification
4. Gradually enable write operations

See `docs/picoclaw-phase2.md` for the complete Phase 2 roadmap.
