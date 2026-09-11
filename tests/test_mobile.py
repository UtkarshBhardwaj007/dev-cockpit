"""Read-only mobile connection-guidance coverage (dev_cockpit.mobile)."""
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dev_cockpit import mobile  # noqa: E402


class MobileTests(unittest.TestCase):
    @patch("dev_cockpit.mobile.getpass.getuser", return_value="alice")
    @patch("dev_cockpit.mobile.socket.gethostname", return_value="laptop")
    @patch("dev_cockpit.mobile.platform.system", return_value="Darwin")
    @patch("dev_cockpit.mobile.shutil.which", side_effect=lambda name: "/usr/bin/" + name if name == "ssh" else None)
    def test_no_tailscale_omits_vpn(self, *_):
        info = mobile.connection_info()
        self.assertEqual(info["user"], "alice")
        self.assertEqual(info["hostname"], "laptop")
        self.assertEqual(info["ssh_client"], "/usr/bin/ssh")
        self.assertNotIn("vpn_name", info)

    @patch("dev_cockpit.mobile.getpass.getuser", return_value="alice")
    @patch("dev_cockpit.mobile.socket.gethostname", return_value="laptop")
    @patch("dev_cockpit.mobile.platform.system", return_value="Linux")
    @patch("dev_cockpit.mobile.shutil.which", side_effect=lambda n: "/usr/bin/tailscale" if n == "tailscale" else "/usr/bin/ssh")
    def test_tailscale_success_populates_vpn(self, *_):
        status = {"Self": {"DNSName": "laptop.tailnet.ts.net.", "TailscaleIPs": ["100.1.2.3"]}}
        with patch("dev_cockpit.mobile.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(status)
            info = mobile.connection_info()
        self.assertEqual(info["vpn_name"], "laptop.tailnet.ts.net")
        self.assertEqual(info["vpn_addresses"], ["100.1.2.3"])

    @patch("dev_cockpit.mobile.getpass.getuser", return_value="alice")
    @patch("dev_cockpit.mobile.socket.gethostname", return_value="laptop")
    @patch("dev_cockpit.mobile.platform.system", return_value="Linux")
    @patch("dev_cockpit.mobile.shutil.which", side_effect=lambda n: "/usr/bin/tailscale" if n == "tailscale" else "/usr/bin/ssh")
    def test_tailscale_failure_reports_unavailable(self, *_):
        with patch("dev_cockpit.mobile.subprocess.run") as run:
            run.return_value.returncode = 1
            info = mobile.connection_info()
        # A nonzero tailscale exit is skipped gracefully, not reported as a VPN.
        self.assertNotIn("vpn_name", info)
        self.assertNotIn("vpn_status", info)


if __name__ == "__main__":
    unittest.main()
