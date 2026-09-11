"""Read-only mobile connection guidance; no implicit SSH/firewall changes."""
import getpass
import json
import platform
import shutil
import socket
import subprocess


def connection_info():
    result = {"user": getpass.getuser(), "hostname": socket.gethostname(),
              "platform": platform.system(), "session": "dev-cockpit", "ssh_client": shutil.which("ssh")}
    tailscale = shutil.which("tailscale")
    if tailscale:
        try:
            status = subprocess.run([tailscale, "status", "--json"], capture_output=True, text=True, timeout=5)
            if status.returncode == 0:
                own = json.loads(status.stdout).get("Self", {})
                result["vpn_name"] = own.get("DNSName", "").rstrip(".")
                result["vpn_addresses"] = own.get("TailscaleIPs", [])
        except (OSError, ValueError, subprocess.TimeoutExpired):
            result["vpn_status"] = "unavailable"
    return result


def show():
    info = connection_info()
    host = info.get("vpn_name") or info["hostname"]
    print("Mobile access uses your existing SSH policy and the persistent dev-cockpit session.")
    print("Laptop account:", info["user"], "| host:", host)
    if info["platform"] == "Windows":
        print("Native Windows is not a supported Herdr remote API target. Use a Linux/WSL host for the documented mobile path.")
    print("1. Enable SSH for this account on the laptop (Remote Login on macOS).")
    print("2. Connect phone and laptop on the same LAN or private VPN; keep the laptop awake.")
    print("3. In the phone's SSH client, connect as", info["user"], "to", host)
    print("4. Run: herdr --session dev-cockpit")
    print("Detach with Ctrl+B then Q; do not stop the server if work should continue.")
    print("Keep host-key verification and YubiKey touch/PIN requirements. See docs/mobile-access.md for the complete setup.")
    return 0
