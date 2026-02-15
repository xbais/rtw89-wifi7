#!/usr/bin/env python3
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QGroupBox, QFormLayout, QLineEdit, QCheckBox
)


# --------------------------
# Helpers: nmcli wrappers
# --------------------------

def run_cmd(cmd: List[str], timeout: int = 15) -> Tuple[int, str, str]:
    """Run a command and return (rc, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy()
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout running: {' '.join(map(shlex.quote, cmd))}"
    except Exception as e:
        return 1, "", str(e)


def nmcli(args: List[str]) -> Tuple[int, str, str]:
    return run_cmd(["nmcli"] + args)


@dataclass
class WifiDevice:
    name: str
    state: str
    connection: str
    wifi_enabled: Optional[str] = None


@dataclass
class WifiProfile:
    name: str
    uuid: str
    iface: str  # connection.interface-name (may be empty)
    ssid: str   # 802-11-wireless.ssid (may be empty)


def parse_table(output: str) -> List[List[str]]:
    """
    nmcli -t gives ':' separated output; we use -t for reliability.
    This parser is for lines already split by ':'.
    """
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        rows.append(line.split(":"))
    return rows


def get_wifi_devices() -> List[WifiDevice]:
    # DEVICE:TYPE:STATE:CONNECTION
    rc, out, err = nmcli(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
    if rc != 0:
        raise RuntimeError(err or out or "nmcli device failed")

    devices: List[WifiDevice] = []
    for cols in parse_table(out):
        if len(cols) < 4:
            continue
        dev, typ, state, conn = cols[0], cols[1], cols[2], cols[3]
        if typ == "wifi":
            devices.append(WifiDevice(name=dev, state=state, connection=conn))
    return devices


def get_wifi_profiles() -> List[WifiProfile]:
    # NAME:UUID:TYPE
    rc, out, err = nmcli(["-t", "-f", "NAME,UUID,TYPE", "connection", "show"])
    if rc != 0:
        raise RuntimeError(err or out or "nmcli connection show failed")

    wifi_profiles: List[WifiProfile] = []
    for cols in parse_table(out):
        if len(cols) < 3:
            continue
        name, uuid, typ = cols[0], cols[1], cols[2]
        if typ != "802-11-wireless":
            continue

        # Pull interface-name and SSID (some profiles may not have SSID in plain form)
        rc2, out2, err2 = nmcli(["-g", "connection.interface-name,802-11-wireless.ssid", "connection", "show", uuid])
        iface = ""
        ssid = ""
        if rc2 == 0 and out2:
            # two lines, may be empty
            lines = out2.splitlines()
            if len(lines) >= 1:
                iface = lines[0].strip()
            if len(lines) >= 2:
                ssid = lines[1].strip()

        wifi_profiles.append(WifiProfile(name=name, uuid=uuid, iface=iface, ssid=ssid))
    return wifi_profiles


def disconnect_device(dev: str) -> None:
    rc, out, err = nmcli(["device", "disconnect", dev])
    if rc != 0:
        raise RuntimeError(err or out or f"Failed to disconnect {dev}")


def connect_profile_on_device(profile_uuid_or_name: str, dev: str) -> None:
    # nmcli connection up <profile> ifname <dev>
    rc, out, err = nmcli(["connection", "up", profile_uuid_or_name, "ifname", dev])
    if rc != 0:
        raise RuntimeError(err or out or f"Failed to connect profile on {dev}")


def set_device_autoconnect(dev: str, enabled: bool) -> None:
    rc, out, err = nmcli(["device", "set", dev, "autoconnect", "yes" if enabled else "no"])
    if rc != 0:
        raise RuntimeError(err or out or "Failed to set device autoconnect")


def unbind_profile_interface(profile_uuid_or_name: str) -> None:
    # Clear connection.interface-name so it can be used by any adapter
    rc, out, err = nmcli(["connection", "modify", profile_uuid_or_name, "connection.interface-name", ""])
    if rc != 0:
        raise RuntimeError(err or out or "Failed to clear connection.interface-name")


def bind_profile_interface(profile_uuid_or_name: str, dev: str) -> None:
    rc, out, err = nmcli(["connection", "modify", profile_uuid_or_name, "connection.interface-name", dev])
    if rc != 0:
        raise RuntimeError(err or out or "Failed to set connection.interface-name")


def delete_profile(profile_uuid_or_name: str) -> None:
    rc, out, err = nmcli(["connection", "delete", profile_uuid_or_name])
    if rc != 0:
        raise RuntimeError(err or out or "Failed to delete profile")


def wifi_radio_status() -> bool:
    rc, out, err = nmcli(["-t", "-f", "WIFI", "radio"])
    if rc != 0:
        return True
    # WIFI:enabled/disabled
    # With -t it usually prints "enabled" or "disabled" (without key)
    val = out.strip().lower()
    return val == "enabled"


# --------------------------
# GUI
# --------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-WiFi Manager (NetworkManager / nmcli)")

        self.devices: List[WifiDevice] = []
        self.profiles: List[WifiProfile] = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Top: status + refresh
        top = QHBoxLayout()
        self.radio_label = QLabel()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_all)
        top.addWidget(self.radio_label)
        top.addStretch(1)
        top.addWidget(self.refresh_btn)
        root.addLayout(top)

        # Devices box
        dev_box = QGroupBox("Wi-Fi adapters")
        dev_layout = QVBoxLayout(dev_box)

        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.on_device_selected)

        self.dev_state = QLabel("State: —")
        self.dev_conn = QLabel("Active connection: —")

        dev_layout.addWidget(self.device_combo)
        dev_layout.addWidget(self.dev_state)
        dev_layout.addWidget(self.dev_conn)

        dev_btns = QHBoxLayout()
        self.btn_disconnect = QPushButton("Disconnect this adapter")
        self.btn_disconnect.clicked.connect(self.ui_disconnect_device)
        self.btn_autoconnect_off = QPushButton("Autoconnect OFF")
        self.btn_autoconnect_off.clicked.connect(lambda: self.ui_set_autoconnect(False))
        self.btn_autoconnect_on = QPushButton("Autoconnect ON")
        self.btn_autoconnect_on.clicked.connect(lambda: self.ui_set_autoconnect(True))
        dev_btns.addWidget(self.btn_disconnect)
        dev_btns.addWidget(self.btn_autoconnect_off)
        dev_btns.addWidget(self.btn_autoconnect_on)
        dev_layout.addLayout(dev_btns)

        root.addWidget(dev_box)

        # Profiles box
        prof_box = QGroupBox("Saved Wi-Fi profiles")
        prof_layout = QVBoxLayout(prof_box)

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self.on_profile_selected)

        prof_layout.addWidget(self.profile_list)

        prof_actions = QHBoxLayout()
        self.btn_connect_profile = QPushButton("Connect selected profile on selected adapter")
        self.btn_connect_profile.clicked.connect(self.ui_connect_profile)
        self.btn_unbind_profile = QPushButton("Unbind profile from adapter (fix GUI issue)")
        self.btn_unbind_profile.clicked.connect(self.ui_unbind_profile)
        prof_actions.addWidget(self.btn_connect_profile)
        prof_actions.addWidget(self.btn_unbind_profile)
        prof_layout.addLayout(prof_actions)

        prof_actions2 = QHBoxLayout()
        self.btn_bind_profile = QPushButton("Bind profile to selected adapter")
        self.btn_bind_profile.clicked.connect(self.ui_bind_profile)
        self.btn_delete_profile = QPushButton("Delete selected profile")
        self.btn_delete_profile.clicked.connect(self.ui_delete_profile)
        prof_actions2.addWidget(self.btn_bind_profile)
        prof_actions2.addWidget(self.btn_delete_profile)
        prof_layout.addLayout(prof_actions2)

        root.addWidget(prof_box)

        # Info box
        info_box = QGroupBox("Quick commands")
        info_layout = QFormLayout(info_box)
        self.cmd_disconnect = QLineEdit()
        self.cmd_disconnect.setReadOnly(True)
        self.cmd_connect = QLineEdit()
        self.cmd_connect.setReadOnly(True)
        self.cmd_unbind = QLineEdit()
        self.cmd_unbind.setReadOnly(True)
        info_layout.addRow("Disconnect adapter:", self.cmd_disconnect)
        info_layout.addRow("Connect profile on adapter:", self.cmd_connect)
        info_layout.addRow("Unbind profile from adapter:", self.cmd_unbind)
        root.addWidget(info_box)

        # Menu
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.close)
        self.menuBar().addAction(act_quit)

        # Auto-refresh timer
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start()

        self.refresh_all()

    def show_error(self, title: str, msg: str) -> None:
        QMessageBox.critical(self, title, msg)

    def show_info(self, title: str, msg: str) -> None:
        QMessageBox.information(self, title, msg)

    def refresh_all(self) -> None:
        try:
            radio = wifi_radio_status()
            self.radio_label.setText(f"Wi-Fi radio: {'ENABLED' if radio else 'DISABLED'}")
        except Exception:
            self.radio_label.setText("Wi-Fi radio: ?")

        try:
            self.devices = get_wifi_devices()
        except Exception as e:
            self.show_error("Error", f"Could not list Wi-Fi devices.\n\n{e}")
            self.devices = []

        try:
            self.profiles = get_wifi_profiles()
        except Exception as e:
            self.show_error("Error", f"Could not list Wi-Fi profiles.\n\n{e}")
            self.profiles = []

        self._render_devices()
        self._render_profiles()
        self._update_selected_details()

    def _render_devices(self) -> None:
        current = self.device_combo.currentText()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for d in self.devices:
            self.device_combo.addItem(d.name)
        # restore selection if possible
        if current:
            idx = self.device_combo.findText(current)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
        self.device_combo.blockSignals(False)

    def _render_profiles(self) -> None:
        current_uuid = None
        item = self.profile_list.currentItem()
        if item is not None:
            current_uuid = item.data(Qt.UserRole)

        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for p in sorted(self.profiles, key=lambda x: (x.ssid or x.name).lower()):
            label = f"{p.ssid or p.name}  |  {p.name}"
            if p.iface:
                label += f"  |  bound→ {p.iface}"
            li = QListWidgetItem(label)
            li.setData(Qt.UserRole, p.uuid)
            self.profile_list.addItem(li)

        # restore selection
        if current_uuid:
            for i in range(self.profile_list.count()):
                it = self.profile_list.item(i)
                if it.data(Qt.UserRole) == current_uuid:
                    self.profile_list.setCurrentItem(it)
                    break

        self.profile_list.blockSignals(False)

    def _selected_device(self) -> Optional[WifiDevice]:
        name = self.device_combo.currentText().strip()
        for d in self.devices:
            if d.name == name:
                return d
        return None

    def _selected_profile(self) -> Optional[WifiProfile]:
        it = self.profile_list.currentItem()
        if it is None:
            return None
        uuid = it.data(Qt.UserRole)
        for p in self.profiles:
            if p.uuid == uuid:
                return p
        return None

    def _update_selected_details(self) -> None:
        d = self._selected_device()
        if d:
            self.dev_state.setText(f"State: {d.state}")
            self.dev_conn.setText(f"Active connection: {d.connection}")
            self.cmd_disconnect.setText(f"nmcli device disconnect {d.name}")
        else:
            self.dev_state.setText("State: —")
            self.dev_conn.setText("Active connection: —")
            self.cmd_disconnect.setText("")

        p = self._selected_profile()
        if p and d:
            self.cmd_connect.setText(f"nmcli connection up {shlex.quote(p.uuid)} ifname {d.name}")
            self.cmd_unbind.setText(f"nmcli connection modify {shlex.quote(p.uuid)} connection.interface-name ''")
        else:
            self.cmd_connect.setText("")
            self.cmd_unbind.setText("")

    def on_device_selected(self) -> None:
        self._update_selected_details()

    def on_profile_selected(self) -> None:
        self._update_selected_details()

    # ---- UI Actions ----

    def ui_disconnect_device(self) -> None:
        d = self._selected_device()
        if not d:
            return
        try:
            disconnect_device(d.name)
            self.refresh_all()
        except Exception as e:
            self.show_error("Disconnect failed", str(e))

    def ui_set_autoconnect(self, enabled: bool) -> None:
        d = self._selected_device()
        if not d:
            return
        try:
            set_device_autoconnect(d.name, enabled)
            self.show_info("OK", f"Autoconnect for {d.name} set to {'ON' if enabled else 'OFF'}.")
            self.refresh_all()
        except Exception as e:
            self.show_error("Autoconnect failed", str(e))

    def ui_connect_profile(self) -> None:
        d = self._selected_device()
        p = self._selected_profile()
        if not d or not p:
            return

        try:
            # If profile is bound to another interface, offer to unbind
            if p.iface and p.iface != d.name:
                res = QMessageBox.question(
                    self,
                    "Profile is bound to another adapter",
                    f"This profile is bound to '{p.iface}'.\n"
                    f"Unbind it so it can be used on '{d.name}'?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if res == QMessageBox.Yes:
                    unbind_profile_interface(p.uuid)

            connect_profile_on_device(p.uuid, d.name)
            self.refresh_all()
        except Exception as e:
            self.show_error("Connect failed", str(e))

    def ui_unbind_profile(self) -> None:
        p = self._selected_profile()
        if not p:
            return
        try:
            unbind_profile_interface(p.uuid)
            self.show_info("OK", "Profile unbound (connection.interface-name cleared).")
            self.refresh_all()
        except Exception as e:
            self.show_error("Unbind failed", str(e))

    def ui_bind_profile(self) -> None:
        d = self._selected_device()
        p = self._selected_profile()
        if not d or not p:
            return
        try:
            bind_profile_interface(p.uuid, d.name)
            self.show_info("OK", f"Profile bound to {d.name}.")
            self.refresh_all()
        except Exception as e:
            self.show_error("Bind failed", str(e))

    def ui_delete_profile(self) -> None:
        p = self._selected_profile()
        if not p:
            return
        res = QMessageBox.question(
            self,
            "Delete profile?",
            f"Delete saved Wi-Fi profile:\n\n{p.ssid or p.name}\n({p.name})",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return
        try:
            delete_profile(p.uuid)
            self.refresh_all()
        except Exception as e:
            self.show_error("Delete failed", str(e))


def main() -> int:
    app = QApplication([])
    w = MainWindow()
    w.resize(980, 640)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
