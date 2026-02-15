#!/usr/bin/env bash
set -euo pipefail

# Realtek WiFi7 USB (0bda:8912) DKMS installer for Ubuntu 24
# Repo: rtw89 (the one that contains rtw8922au.c with USB_DEVICE 0bda:8912)
#
# Usage:
#   bash install-rtw89-wifi7.sh
#
# Optional env vars:
#   REPO_URL="https://github.com/<your-repo>/rtw89.git"   # override repo
#   WORKDIR="$HOME/src"                                  # override clone dir

REPO_URL="${REPO_URL:-https://github.com/morrownr/rtw89.git}"  # default if you want; override as needed
WORKDIR="${WORKDIR:-$HOME/src}"
TARGET_USB_VID="0x0bda"
TARGET_USB_PID="0x8912"

log() { printf "\n[+] %s\n" "$*"; }
warn() { printf "\n[!] %s\n" "$*" >&2; }
die() { printf "\n[✗] %s\n" "$*" >&2; exit 1; }

# --- sanity checks ---
if [[ "${EUID}" -eq 0 ]]; then
  die "Do not run this script as root. Run as your user; it will use sudo when needed."
fi

log "Ubuntu release:"
. /etc/os-release || true
echo "  ID=${ID:-unknown} VERSION_ID=${VERSION_ID:-unknown} PRETTY_NAME=${PRETTY_NAME:-unknown}"

if [[ "${ID:-}" != "ubuntu" ]]; then
  warn "This script is intended for Ubuntu. Proceeding anyway."
fi

if [[ "${VERSION_ID:-}" != "24.04" && "${VERSION_ID:-}" != "24.10" && "${VERSION_ID:-}" != "24.01" && "${VERSION_ID:-}" != "24" ]]; then
  warn "This script targets Ubuntu 24.x. Your VERSION_ID=${VERSION_ID:-unknown}. Proceeding anyway."
fi

KVER="$(uname -r)"
log "Kernel: $KVER"

# --- prerequisites ---
log "Installing prerequisites (dkms, build-essential, linux-headers-$KVER, git, mokutil)..."
sudo apt update
sudo apt install -y dkms build-essential "linux-headers-$KVER" git mokutil usb-modeswitch

# --- clone/update repo ---
mkdir -p "$WORKDIR"
cd "$WORKDIR"

REPO_DIR="$WORKDIR/rtw89"

if [[ -d "$REPO_DIR/.git" ]]; then
  log "Repo already exists at $REPO_DIR — updating..."
  cd "$REPO_DIR"
  git fetch --all --tags
  git pull --ff-only || true
else
  log "Cloning repo into $REPO_DIR ..."
  git clone "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR"
fi

# --- verify it contains your USB ID ---
log "Verifying repo contains USB ID ${TARGET_USB_VID}:${TARGET_USB_PID} ..."
if ! grep -R "USB_DEVICE_AND_INTERFACE_INFO(${TARGET_USB_VID}, ${TARGET_USB_PID}" -n . >/dev/null 2>&1; then
  warn "Could not find an explicit USB ID match for ${TARGET_USB_VID}:${TARGET_USB_PID} in this repo."
  warn "This repo may not support your adapter. Look for the match in rtw8922au.c or usb tables."
  warn "Search results:"
  grep -R "${TARGET_USB_PID}" -n . | head -n 50 || true
  die "Aborting because support for your USB ID was not found."
fi
log "USB ID match found."

# --- read DKMS package name/version from dkms.conf ---
log "Reading DKMS package name/version from dkms.conf ..."
if [[ ! -f dkms.conf ]]; then
  die "dkms.conf not found in repo root. This does not look like a DKMS-ready repo."
fi

PKG_NAME="$(awk -F\" '/^PACKAGE_NAME=/{print $2}' dkms.conf | head -n1)"
PKG_VER="$(awk -F\" '/^PACKAGE_VERSION=/{print $2}' dkms.conf | head -n1)"

[[ -n "$PKG_NAME" ]] || die "Could not parse PACKAGE_NAME from dkms.conf"
[[ -n "$PKG_VER"  ]] || die "Could not parse PACKAGE_VERSION from dkms.conf"

log "DKMS package: ${PKG_NAME} / ${PKG_VER}"

# --- remove older DKMS entries for same package/version (safe re-run) ---
log "Removing any existing DKMS installs of ${PKG_NAME}/${PKG_VER} (if present)..."
if sudo dkms status | grep -q "^${PKG_NAME}/${PKG_VER}"; then
  sudo dkms remove -m "$PKG_NAME" -v "$PKG_VER" --all || true
fi

# --- add source to DKMS ---
log "Adding source to DKMS..."
sudo dkms add "$PWD" || true

# DKMS add may have already created /usr/src/<name>-<ver>.
# Ensure it exists:
if [[ ! -d "/usr/src/${PKG_NAME}-${PKG_VER}" ]]; then
  # Some repos use dkms add to create it; if not, do it explicitly.
  warn "/usr/src/${PKG_NAME}-${PKG_VER} not found. Attempting to re-add..."
  sudo dkms add "$PWD" || true
fi

[[ -d "/usr/src/${PKG_NAME}-${PKG_VER}" ]] || die "Module source directory /usr/src/${PKG_NAME}-${PKG_VER} still not found."

# --- install DKMS module ---
log "Building + installing DKMS module ${PKG_NAME}/${PKG_VER} ..."
sudo dkms install -m "$PKG_NAME" -v "$PKG_VER"

# --- install modprobe configs shipped by repo (conflict prevention) ---
log "Installing modprobe config (rtw89.conf) to prevent conflicts..."
if [[ -f "rtw89.conf" ]]; then
  sudo cp -v "rtw89.conf" /etc/modprobe.d/
else
  warn "rtw89.conf not found in repo root; skipping."
fi

log "Installing usb_storage.conf (helps if device presents as storage/CDROM mode)..."
if [[ -f "usb_storage.conf" ]]; then
  sudo cp -v "usb_storage.conf" /etc/modprobe.d/
  sudo update-initramfs -u
else
  warn "usb_storage.conf not found; skipping."
fi

# --- Secure Boot note ---
SB_STATE="$(mokutil --sb-state 2>/dev/null || true)"
log "Secure Boot state: ${SB_STATE:-unknown}"
if echo "$SB_STATE" | grep -qi "enabled"; then
  warn "Secure Boot is ENABLED."
  warn "Ubuntu DKMS will try to sign modules with MOK. If the module refuses to load, you may need to enroll the MOK key."
  warn "To enroll (if needed): sudo mokutil --import /var/lib/shim-signed/mok/MOK.der  then reboot and enroll in the blue MOK screen."
fi

# --- try loading module (best effort; module name differs by build) ---
log "Attempting to load rtw89 modules (best effort)..."
sudo modprobe -a rtw89core rtw89pci rtw89usb 2>/dev/null || true
# Some builds name the USB module rtw89_8922au; try it too:
sudo modprobe -a rtw89_8922au 2>/dev/null || true

# --- final verification ---
log "Verification:"
echo "== lsusb grep 0bda:8912 =="
lsusb | grep -i "0bda:8912" || true

echo
echo "== lsmod grep rtw89 =="
lsmod | grep -i rtw89 || true

echo
echo "== ip link (look for wlan/wlp*) =="
ip link | sed -n '1,200p'

echo
echo "== nmcli device (look for wifi device) =="
nmcli device || true

echo
echo "== recent dmesg lines mentioning rtw/realtek/8912 =="
dmesg | grep -iE "rtw|realtek|8912" | tail -n 80 || true

log "Done."
log "If you do not see a Wi-Fi interface, paste: sudo dmesg | tail -n 200  and: sudo dkms status"
