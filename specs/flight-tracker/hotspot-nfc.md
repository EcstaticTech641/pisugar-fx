# Specification: Wi-Fi Hotspot & NFC Tap-to-Connect

**Project**: PiSugar Flight Tracker  
**Date**: 2026-06-09  
**Status**: Implemented  
**Hardware**: Raspberry Pi Zero 2W + NTAG215/NTAG216 NFC sticker

## Overview

Enable smartphones to view the pisugar-fx web server display without being connected to a shared Wi-Fi network. The Pi broadcasts its own access point (`<device-name>-AP`) using a virtual interface alongside its existing Wi-Fi client connection. An NFC sticker attached to the badge automates network join and browser navigation on tap.

## User Stories

### US1: Off-Network Web Display Access (Priority: P1)
**As a** user in the field without shared Wi-Fi  
**I want to** connect my phone directly to the badge  
**So that** I can view the live radar map on my smartphone

**Acceptance Criteria:**
- Badge broadcasts a stable Wi-Fi AP at all times
- Phone can join AP and reach the web server at `http://<hostname>.local:<port>`
- Pi remains connected to known Wi-Fi networks simultaneously when available
- AP survives reboot without manual intervention

### US2: NFC Tap-to-Connect (Priority: P2)
**As a** user wanting a seamless experience  
**I want to** tap my phone to the badge  
**So that** the browser opens automatically pointed at the radar map

**Acceptance Criteria:**
- Single NFC tag write contains both Wi-Fi credentials and target URL
- Android: prompts to join AP, then opens URL automatically
- iOS: opens URL in Safari immediately; user joins AP manually from Settings
- Tag requires no app beyond the phone's built-in NFC reader

## Functional Requirements

### FR1: Dual-Mode Wi-Fi
- Pi must remain connected to known Wi-Fi client networks (`wlan0`) while simultaneously broadcasting an AP
- AP runs on a virtual interface (`uap0`) derived from `wlan0`
- The `brcmfmac` driver on Pi Zero 2W supports this on 2.4 GHz only; both connections must use 2.4 GHz band
- AP assigns connected clients IPs via NetworkManager's built-in DHCP (`ipv4.method shared`)
- Pi's AP interface holds a static IP of `192.168.4.1`

### FR2: Interface Persistence
- The `uap0` virtual interface does not survive reboot by default and must be created before NetworkManager starts
- A `systemd` oneshot service handles creation of `uap0` at boot, prior to NetworkManager
- NetworkManager then brings up the AP connection on `uap0` as a second step in the same service

### FR3: Web Server Binding
- The Flask web server (`app.py`) must bind to `0.0.0.0` to be reachable from the AP interface
- Binding to `localhost` or `127.0.0.1` will make the server unreachable to AP clients
- The `FlightWebServer` daemon thread in `controller.py` inherits the port from `settings.web_server_port` (default: `5000`)

### FR4: mDNS Name Resolution
- `avahi-daemon` must be installed and enabled to broadcast `<hostname>.local` on all interfaces including `uap0`
- The Pi's system hostname determines the `.local` address used in the NFC tag URL
- Changing the hostname after writing the NFC tag requires rewriting the tag

### FR5: NFC Tag Contents
- Tag type: NTAG215 or NTAG216 (NTAG215 sufficient; 504 bytes capacity)
- Two NDEF records written in order:
  1. **Wi-Fi Network** — SSID, password, security type WPA2
  2. **URL/URI** — `http://<hostname>.local:<port>`
- Record order is significant: Wi-Fi record must precede URL record for correct Android behavior

## Non-Functional Requirements

### NFR1: Reliability
- AP must be available within 30 seconds of boot
- AP must not drop when the Pi connects or reconnects to a home Wi-Fi network
- If home Wi-Fi is unavailable, AP continues broadcasting independently

### NFR2: Transparency
- The hotspot setup must not interfere with existing functionality: airplanes.live API calls, VNC/SSH access, or systemd service operation
- Home Wi-Fi connection retains priority over AP autoconnect

### NFR3: Platform Compatibility
- Android 10+: full tap-to-connect experience (Wi-Fi join prompt + URL auto-open)
- iOS 14+: URL opens in Safari on tap; Wi-Fi join is a manual step (Apple platform restriction)
- mDNS `.local` resolution works natively on both platforms without additional apps

## Implementation

### 1. Virtual Interface Service

Create `/etc/systemd/system/create-uap0.service`:

```ini
[Unit]
Description=Create uap0 virtual WiFi interface for AP mode
After=sys-subsystem-net-devices-wlan0.device network.target
Wants=NetworkManager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/iw dev wlan0 interface add uap0 type __ap
ExecStartPost=/bin/sleep 3
ExecStartPost=/usr/bin/nmcli con up <ap-connection-name>
ExecStop=/sbin/iw dev uap0 del

[Install]
WantedBy=multi-user.target
```

Enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable create-uap0.service
sudo systemctl start create-uap0.service
```

The 3-second sleep in `ExecStartPost` is required to allow `uap0` to fully register with NetworkManager before the connection activation is attempted. Without it, the AP connection attempt races against interface readiness and fails silently.

### 2. NetworkManager AP Connection

Create the AP connection on `uap0`:

```bash
sudo nmcli con add type wifi ifname uap0 con-name "<ap-connection-name>" autoconnect no ssid "<device-name>-AP"
sudo nmcli con modify "<ap-connection-name>" 802-11-wireless.mode ap
sudo nmcli con modify "<ap-connection-name>" 802-11-wireless.band bg
sudo nmcli con modify "<ap-connection-name>" ipv4.method shared
sudo nmcli con modify "<ap-connection-name>" wifi-sec.key-mgmt wpa-psk
sudo nmcli con modify "<ap-connection-name>" wifi-sec.psk "<password>"
```

Set autoconnect off on the connection itself since the systemd service manages activation:

```bash
sudo nmcli con modify "<ap-connection-name>" connection.autoconnect no
```

Set home Wi-Fi priority higher than AP:

```bash
sudo nmcli con modify "<home-wifi-connection-name>" connection.autoconnect yes
sudo nmcli con modify "<home-wifi-connection-name>" connection.autoconnect-priority 10
```

### 3. Flask Web Server Binding

In `app.py`, confirm the `__main__` entry point binds to all interfaces:

```python
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
```

When running as a daemon thread via `FlightWebServer` in `controller.py`, confirm the internal `_run` method also uses `host="0.0.0.0"` and not `localhost`. The port is sourced from `settings.web_server_port`.

### 4. mDNS via Avahi

```bash
sudo apt install avahi-daemon -y
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon
```

Verify the hostname matches the intended `.local` address:

```bash
hostname
```

To change it:

```bash
sudo hostnamectl set-hostname <hostname>
sudo systemctl restart avahi-daemon
```

### 5. NFC Tag Writing

**Required hardware:** NTAG215 or NTAG216 sticker  
**Recommended app:** NFC Tools (Android or iOS, free tier sufficient)

Steps:

1. Confirm AP is broadcasting and web server is reachable at `http://<hostname>.local:<port>` from a phone connected to the AP
2. Open NFC Tools → **Write** tab
3. **Add a record** → **Wi-Fi Network** → enter SSID, password, security: WPA2
4. **Add a record** → **URL/URI** → enter `http://<hostname>.local:<port>`
5. Tap **Write** → hold blank NFC sticker to phone's NFC area until confirmed
6. Test the tag before affixing it to the badge

## Verification

After full setup and reboot, confirm each layer independently:

```bash
# Interface and connection state
nmcli device status
# Expected: wlan0 connected to home wifi, uap0 connected to AP

# AP IP assignment
ip addr show uap0
# Expected: inet 192.168.4.1/24

# mDNS broadcast
avahi-browse -a
# Expected: service entries on uap0 interface

# Web server reachability (from a phone on the AP)
# Browse to: http://<hostname>.local:<port>
```

## Limitations

- **iOS Wi-Fi join**: iOS does not auto-join Wi-Fi networks from NFC tags. The browser opens automatically but the page fails until the user manually joins the AP in Settings → Wi-Fi. This is an Apple platform restriction with no workaround.
- **2.4 GHz only**: Pi Zero 2W's `brcmfmac` chip is 2.4 GHz. Both the AP and home Wi-Fi client connections must operate on 2.4 GHz. If the home router is 5 GHz only, the Pi will not connect to it while the AP is active.
- **Single radio**: Dual-mode works via a virtual interface but shares the single physical radio. Throughput on both connections is reduced compared to dedicated hardware.
- **mDNS on Android**: Android 12+ resolves `.local` natively. Older Android versions may fail to resolve the hostname; use `http://192.168.4.1:<port>` as a fallback URL.
- **Tag is write-locked after use**: Changing the hostname or port after writing requires a new tag write. The URL record is not editable in place.
