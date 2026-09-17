# Mobile access

How to reach a dev-cockpit machine from a phone or tablet over SSH, using the persistent dev-cockpit Herdr session. This follows your existing SSH policy and does not alter it. See [security](security.md) and [feasibility](feasibility.md) for the underlying guarantees.

## Enable SSH on the laptop

Turn on Remote Login for your account (macOS): System Settings > General > Sharing > Remote Login, and allow your user. Existing SSH authentication, host-key checks and YubiKey touch/PIN requirements stay in force. Do not disable touch or host-key verification, add agent forwarding, or set up an unattended identity.

Native Windows is not a supported Herdr remote API target; use a Linux/WSL host for this documented path.

## Reach the machine

Connect the phone and laptop on the same LAN, or on a private VPN such as Tailscale. A VPN avoids router and firewall discovery. The laptop must stay awake and on the network for the session to remain reachable.

## Connect from the phone

In the phone's SSH client, connect as your laptop account to the laptop's LAN address or VPN name, then run:

```sh
herdr --session dev-cockpit
```

This attaches to the persistent dev-cockpit session.

## Keep work running

Detach with `Ctrl+B` then `Q`. Do not stop the server if work should continue; the session stays alive on the laptop and you can reattach from the phone later.
