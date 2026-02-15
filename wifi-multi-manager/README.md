# Multi-WiFi Manager (Ubuntu 24)

A lightweight **PySide6 GUI application** for managing multiple Wi-Fi adapters simultaneously on Ubuntu 24 using NetworkManager (`nmcli`).

This tool is designed for users running **multiple Wi-Fi interfaces** (e.g. built-in Intel + USB Wi-Fi 7) who need precise control over:

* Connecting specific adapters to specific networks
* Disconnecting individual Wi-Fi chips without disabling all Wi-Fi
* Fixing NetworkManager profile binding issues
* Testing network speed per adapter
* Managing autoconnect behavior

---

## ✨ Features

✅ View all Wi-Fi adapters
✅ View all saved Wi-Fi profiles
✅ Disconnect a single Wi-Fi adapter
✅ Connect a profile to a specific adapter
✅ Remove profile interface binding (`connection.interface-name`)
✅ Bind a profile to a specific adapter
✅ Toggle autoconnect per adapter
✅ Delete saved profiles
✅ Live auto-refresh
✅ Built specifically for Ubuntu 24

---

## 🖥 Example Use Case

You have:

* `wlp0s20f3` → Intel built-in Wi-Fi
* `wlx80afcabcf77b` → USB Wi-Fi 7 adapter

You want to:

* Disconnect only the Intel adapter
* Connect the USB adapter to the same SSID
* Prevent Ubuntu from auto-reconnecting the Intel device
* Fix the issue where the GUI refuses to connect a saved network on another adapter

This app handles all of that cleanly.

---

## 🧰 Requirements

* Ubuntu 24.x
* NetworkManager
* Python 3
* PySide6

---

## 🚀 Installation (Ubuntu 24)

Clone your repository or download the files, then run:

```bash
chmod +x install.sh
./install.sh
```

This will:

* Install system dependencies
* Create a Python virtual environment
* Install PySide6
* Generate a `run.sh` launcher script

---

## ▶ Running the App

```bash
cd ~/wifi-multi-manager
./run.sh
```

If PolicyKit blocks certain operations:

```bash
pkexec env DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY ./run.sh
```

---

## 🔧 What Problem This Fixes

Ubuntu's default Settings app:

* Cannot disconnect Wi-Fi per adapter
* Turns off all Wi-Fi radios at once
* Binds Wi-Fi profiles to the adapter that created them
* Fails silently when trying to connect the same SSID on another Wi-Fi card

This application exposes full `nmcli` control in a clean GUI.

---

## 🧠 Technical Details

This app is a GUI wrapper around:

```bash
nmcli device disconnect <iface>
nmcli connection up <profile> ifname <iface>
nmcli connection modify <profile> connection.interface-name ""
nmcli device set <iface> autoconnect yes|no
```

It does not modify NetworkManager internals.

No background services. No root daemons.

---

## 📦 Project Structure

```
wifi-multi-manager/
├── install.sh
├── run.sh
├── wifi_manager.py
└── .venv/
```

---

## 🔐 Secure Boot

This app does not install drivers or kernel modules.

If you're using external Wi-Fi drivers (e.g., RTL8912 Wi-Fi 7), ensure they are properly installed via DKMS beforehand.

---

## 🧪 Tested On

* Ubuntu 24.04
* Ubuntu 24.10
* Kernel 6.6+
* Intel Wi-Fi
* Realtek Wi-Fi 7 (RTL8912 USB)

---

## 📋 Roadmap Ideas

* Per-adapter routing metrics editor
* Link speed display (MCS, channel width)
* Traffic monitoring per adapter
* Speedtest integration
* .deb packaging
* Snap package
* System tray mode

---

## 🤝 Contributing

Pull requests welcome.

---

## ⚖ License

MIT License (or your preferred license)

---

If you'd like, I can also generate:

* A clean MIT LICENSE file
* A .desktop launcher file
* A deb packaging script
* A GitHub Actions workflow for building releases
* A more enterprise-grade README with badges and screenshots
* A version with screenshots mockup markdown

Just tell me the level of polish you want.
