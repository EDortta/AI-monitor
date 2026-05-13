#!/usr/bin/env bash
# install.sh — create venv, install deps, register autostart
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
PYTHON="${PYTHON:-python3}"

echo "[agent-monitor] Creating venv at $VENV ..."
"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$DIR/requirements.txt" -q
echo "[agent-monitor] Dependencies installed."

OS="$(uname -s)"

if [ "$OS" = "Linux" ]; then
    AUTOSTART="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART"
    cat > "$AUTOSTART/agent-monitor.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Agent Monitor
Comment=AI agent activity — tray icon
Exec=env PYSTRAY_BACKEND=xorg $VENV/bin/python $DIR/monitor.py
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF
    echo "[agent-monitor] Autostart → $AUTOSTART/agent-monitor.desktop"

elif [ "$OS" = "Darwin" ]; then
    AGENTS_DIR="$HOME/Library/LaunchAgents"
    mkdir -p "$AGENTS_DIR"
    PLIST="$AGENTS_DIR/com.local.agent-monitor.plist"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.local.agent-monitor</string>
  <key>ProgramArguments</key><array>
    <string>$VENV/bin/python</string>
    <string>$DIR/monitor.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardErrorPath</key>
  <string>$HOME/Sync/agent-monitor-error.log</string>
</dict></plist>
EOF
    launchctl load "$PLIST" 2>/dev/null || true
    echo "[agent-monitor] LaunchAgent → $PLIST"
fi

echo ""
echo "[agent-monitor] Done. Run now with:"
echo "  $VENV/bin/python $DIR/monitor.py"
