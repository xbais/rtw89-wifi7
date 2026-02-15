#!/usr/bin/env bash
set -euo pipefail

APPDIR="${APPDIR:-$HOME/wifi-multi-manager}"
VENV="$APPDIR/.venv"

echo "[+] Creating app dir: $APPDIR"
mkdir -p "$APPDIR"
cd "$APPDIR"

echo "[+] Installing system deps"
sudo apt update
sudo apt install -y python3 python3-venv python3-pip network-manager

echo "[+] Creating venv"
python3 -m venv "$VENV"
source "$VENV/bin/activate"

echo "[+] Upgrading pip"
pip install --upgrade pip

echo "[+] Installing PySide6"
pip install PySide6

echo "[+] Writing run.sh"
cat > run.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
APPDIR="$(cd "$(dirname "$0")" && pwd)"
source "$APPDIR/.venv/bin/activate"
python "$APPDIR/wifi_manager.py"
EOF
chmod +x run.sh

echo
echo "[✓] Install complete."
echo "Next:"
echo "  1) Copy wifi_manager.py into: $APPDIR/wifi_manager.py"
echo "  2) Run: $APPDIR/run.sh"
