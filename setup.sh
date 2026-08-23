#!/bin/bash

################################################################################
# pisugar-fx Setup Script
# 
# Automates complete installation from fresh Raspberry Pi OS Lite to a fully
# functional flight tracking badge. Run with sudo.
#
# Usage: sudo bash setup.sh
#
# Author: ron (EcstaticTech)
# Date: 2026-06
################################################################################

set -e  # Exit on first error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${BLUE}==== $1 ====${NC}\n"
}

################################################################################
# PHASE 1: PRE-FLIGHT CHECKS
################################################################################

phase_preflight() {
    log_step "Phase 1: Pre-flight Checks"
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root (sudo)"
        exit 1
    fi
    log_info "Running as root ✓"
    
    # Check for Raspberry Pi
    if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        log_warn "Hardware does not appear to be a Raspberry Pi"
        log_warn "Continuing anyway, but some features may not work"
    else
        log_info "Detected Raspberry Pi ✓"
    fi
    
    # Check internet connectivity
    log_info "Checking internet connectivity..."
    if ! timeout 5 curl -s https://www.google.com -o /dev/null 2>/dev/null; then
        log_error "No internet connectivity. Cannot proceed."
        exit 1
    fi
    log_info "Internet connectivity verified ✓"
    
    # Check available disk space (need at least 2GB free)
    available_space=$(df /home | tail -1 | awk '{print $4}')
    if [ "$available_space" -lt 2097152 ]; then  # 2GB in KB
        log_warn "Less than 2GB available disk space (have ${available_space}KB)"
        log_warn "Build may fail. Consider freeing up space."
    else
        log_info "Sufficient disk space available ✓"
    fi
    
    log_info "All pre-flight checks passed"
}

################################################################################
# PHASE 2: SYSTEM DEPENDENCIES
################################################################################

phase_dependencies() {
    log_step "Phase 2: Installing System Dependencies"
    
    log_info "Updating package lists..."
    apt update
    
    log_info "Installing build tools..."
    apt install -y build-essential pkg-config git
    
    log_info "Installing RTL-SDR and dump1090 dependencies..."
    apt install -y librtlsdr-dev libusb-1.0-0-dev libncurses-dev
    
    log_info "Installing Python and pip..."
    apt install -y python3 python3-pip python3-venv
    
    log_info "Installing pisugar-fx application dependencies..."
    pip3 install requests pillow flask
    
    log_info "Installing avahi daemon for mDNS..."
    apt install -y avahi-daemon
    
    log_info "Installing NetworkManager for Wi-Fi AP configuration..."
    apt install -y network-manager
    
    log_info "All dependencies installed ✓"
}

################################################################################
# PHASE 3: RTL-SDR PERMISSIONS
################################################################################

phase_rtlsdr_permissions() {
    log_step "Phase 3: RTL-SDR Permissions & Kernel Driver Management"
    
    log_info "Creating udev rule for RTL-SDR..."
    cat > /etc/udev/rules.d/20-rtlsdr.rules << 'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", MODE="0666"
EOF
    
    log_info "Reloading udev rules..."
    udevadm control --reload-rules
    udevadm trigger
    
    log_info "Blacklisting kernel DVB driver..."
    if [ ! -f /etc/modprobe.d/rtlsdr.conf ]; then
        echo "blacklist dvb_usb_rtl28xxu" > /etc/modprobe.d/rtlsdr.conf
    fi
    
    log_warn "RTL-SDR permissions configured"
    log_warn "You may need to reboot or run: sudo rmmod dvb_usb_rtl28xxu"
    
    log_info "RTL-SDR configuration complete ✓"
}

################################################################################
# PHASE 4: CLONE/PULL PISUGAR-FX REPOSITORY
################################################################################

phase_pisugar_repo() {
    log_step "Phase 4: Clone/Pull pisugar-fx Repository"
    
    home_dir="/home/$(logname 2>/dev/null || echo 'pi')"
    repo_dir="$home_dir/pisugar-fx"
    
    if [ -d "$repo_dir" ]; then
        log_info "Repository already exists at $repo_dir"
        log_info "Pulling latest changes..."
        cd "$repo_dir"
        git pull origin master
    else
        log_info "Cloning pisugar-fx repository..."
        git clone https://github.com/EcstaticTech/pisugar-fx.git "$repo_dir"
        cd "$repo_dir"
    fi
    
    # Verify critical files
    if [ ! -f "flight_tracker.py" ] && [ ! -f "flight/app.py" ]; then
        log_error "Repository missing critical files"
        exit 1
    fi
    
    log_info "Repository ready at $repo_dir ✓"
}

################################################################################
# PHASE 5: BUILD DUMP1090 FROM SOURCE
################################################################################

phase_dump1090() {
    log_step "Phase 5: Build dump1090 from Source"
    
    home_dir="/home/$(logname 2>/dev/null || echo 'pi')"
    dump1090_dir="$home_dir/dump1090"
    
    if [ ! -d "$dump1090_dir" ]; then
        log_info "Cloning dump1090 repository..."
        git clone https://github.com/flightaware/dump1090.git "$dump1090_dir"
    fi
    
    cd "$dump1090_dir"
    log_info "Building dump1090 (this may take 2-3 minutes)..."
    make BLADERF=no HACKRF=no LIMESDR=no SOAPYSDR=no
    
    if [ ! -f "./dump1090" ]; then
        log_error "dump1090 build failed"
        exit 1
    fi
    
    log_info "dump1090 build complete ✓"
}

################################################################################
# PHASE 6: CONFIGURE READSB
################################################################################

phase_readsb() {
    log_step "Phase 6: Install and Configure readsb"
    
    log_info "Installing readsb package..."
    apt install -y readsb
    
    log_info "Configuring readsb for antenna mode (device-type none)..."
    
    # Backup existing config if it exists
    if [ -f "/etc/default/readsb" ]; then
        cp /etc/default/readsb /etc/default/readsb.backup
        log_info "Backed up existing config to /etc/default/readsb.backup"
    fi
    
    # Create readsb configuration
    cat > /etc/default/readsb << 'EOF'
# readsb configuration for pisugar-fx
# Device type: none (receives data from dump1090 via Beast protocol)
# Port: 31005 (dump1090 Beast output)

RECEIVER_OPTIONS="--device-type none --net-connector localhost,31005,beast_in"
DECODER_OPTIONS="--max-range 450 --write-json-every 1"
NET_OPTIONS="--net --net-heartbeat 60 --net-ro-size 1250 --net-ro-interval 0.05 --net-ri-port 30001 --net-ro-port 30002 --net-sbs-port 30003 --net-bi-port 30004,30104 --net-bo-port 30005"
JSON_OPTIONS="--json-location-accuracy 2 --range-outline-hours 24"
EOF
    
    log_info "Restarting readsb service..."
    systemctl restart readsb
    sleep 2
    
    if systemctl is-active --quiet readsb; then
        log_info "readsb service is running ✓"
    else
        log_warn "readsb service did not start immediately (waiting for Beast input from dump1090 is normal)"
    fi
    
    log_info "readsb configuration complete ✓"
}

################################################################################
# PHASE 7: CREATE SYSTEMD SERVICE FILES
################################################################################

phase_systemd_services() {
    log_step "Phase 7: Create Systemd Service Files"
    
    username="$(logname 2>/dev/null || echo 'pi')"
    home_dir="/home/$username"
    
    # dump1090 service
    log_info "Creating dump1090.service..."
    cat > /etc/systemd/system/dump1090.service << EOF
[Unit]
Description=dump1090 ADS-B Radio Decoder
Documentation=https://github.com/flightaware/dump1090
After=network.target

[Service]
Type=simple
User=$username
WorkingDirectory=$home_dir/dump1090
ExecStart=$home_dir/dump1090/dump1090 --net --quiet --net-ro-port 31002 --net-bo-port 31005 --net-sbs-port 31003 --net-ri-port 31001 --net-bi-port 31004
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Create uap0 interface service
    log_info "Creating create-uap0.service..."
    cat > /etc/systemd/system/create-uap0.service << EOF
[Unit]
Description=Create uap0 virtual WiFi interface for AP mode
After=sys-subsystem-net-devices-wlan0.device network.target
Wants=NetworkManager.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/iw dev wlan0 interface add uap0 type __ap
ExecStartPost=/bin/sleep 3
ExecStartPost=/usr/bin/nmcli con up pisugar-ap
ExecStop=/sbin/iw dev uap0 del

[Install]
WantedBy=multi-user.target
EOF
    
    # pisugar-fx app service
    log_info "Creating pisugar-fx.service..."
    cat > /etc/systemd/system/pisugar-fx.service << EOF
[Unit]
Description=pisugar-fx ADS-B Flight Tracker Badge
Documentation=https://github.com/EcstaticTech/pisugar-fx
After=readsb.service
Wants=dump1090.service

[Service]
Type=simple
User=$username
WorkingDirectory=$home_dir/pisugar-fx
ExecStart=/usr/bin/python3 $home_dir/pisugar-fx/flight/flight_tracker.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    log_info "Reloading systemd daemon..."
    systemctl daemon-reload
    
    log_info "Enabling services for auto-start..."
    systemctl enable dump1090.service
    systemctl enable create-uap0.service
    systemctl enable pisugar-fx.service
    
    log_info "Systemd services created and enabled ✓"
}

################################################################################
# PHASE 8: WI-FI AP CONFIGURATION (NETWORKMANAGER)
################################################################################

phase_wifi_ap() {
    log_step "Phase 8: Configure Wi-Fi AP (NetworkManager)"
    
    log_info "Creating Wi-Fi AP connection on uap0..."
    
    # Check if connection already exists
    if nmcli con show pisugar-ap &>/dev/null; then
        log_info "AP connection 'pisugar-ap' already exists"
        log_info "Skipping creation (modify manually if needed)"
    else
        # Create AP connection
        nmcli con add type wifi ifname uap0 con-name pisugar-ap autoconnect no ssid "ronPi-AP"
        nmcli con modify pisugar-ap 802-11-wireless.mode ap
        nmcli con modify pisugar-ap 802-11-wireless.band bg
        nmcli con modify pisugar-ap ipv4.method shared
        nmcli con modify pisugar-ap wifi-sec.key-mgmt wpa-psk
        
        # Prompt for AP password
        read -p "Enter Wi-Fi AP password (or press Enter for default): " ap_password
        if [ -z "$ap_password" ]; then
            ap_password="pisugarfx2026"
            log_warn "Using default password: $ap_password"
        fi
        
        nmcli con modify pisugar-ap wifi-sec.psk "$ap_password"
        log_info "AP connection created with SSID 'ronPi-AP' ✓"
    fi
    
    # Set home Wi-Fi autoconnect priority if it exists
    home_connection=$(nmcli con show | grep "wifi" | head -1 | awk '{print $1}')
    if [ -n "$home_connection" ] && [ "$home_connection" != "pisugar-ap" ]; then
        log_info "Setting home Wi-Fi connection priority..."
        nmcli con modify "$home_connection" connection.autoconnect yes
        nmcli con modify "$home_connection" connection.autoconnect-priority 10
        log_info "Home Wi-Fi will connect with higher priority than AP ✓"
    fi
    
    log_info "Wi-Fi AP configuration complete ✓"
}

################################################################################
# PHASE 9: AVAHI MDNS CONFIGURATION
################################################################################

phase_avahi() {
    log_step "Phase 9: Configure Avahi mDNS Discovery"
    
    log_info "Checking current hostname..."
    current_hostname=$(hostname)
    log_info "Current hostname: $current_hostname"
    
    if [ "$current_hostname" != "ronPi" ]; then
        log_warn "Hostname is not 'ronPi' (found: '$current_hostname')"
        read -p "Change hostname to 'ronPi'? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            hostnamectl set-hostname ronPi
            log_info "Hostname changed to ronPi ✓"
        fi
    else
        log_info "Hostname is correct (ronPi) ✓"
    fi
    
    log_info "Enabling avahi-daemon..."
    systemctl enable avahi-daemon
    systemctl restart avahi-daemon
    
    log_info "mDNS discovery configured (ronPi.local) ✓"
}

################################################################################
# PHASE 10: PISUGAR-FX CONFIGURATION
################################################################################

phase_pisugar_config() {
    log_step "Phase 10: pisugar-fx Configuration"
    
    home_dir="/home/$(logname 2>/dev/null || echo 'pi')"
    repo_dir="$home_dir/pisugar-fx"
    config_file="$repo_dir/config/flight_locations.json"
    
    if [ ! -d "$repo_dir/config" ]; then
        mkdir -p "$repo_dir/config"
    fi
    
    if [ ! -f "$config_file" ]; then
        log_info "Creating default flight_locations.json..."
        cat > "$config_file" << 'EOF'
{
  "locations": [],
  "settings": {
    "source": "local",
    "display_duration_seconds": 3600,
    "refresh_interval_seconds": 5,
    "brightness": 100,
    "rotation": 0,
    "random_location_enabled": false,
    "web_server_port": 5000
  }
}
EOF
        chmod 644 "$config_file"
        log_info "Configuration created (antenna mode with auto-location) ✓"
    else
        log_info "Configuration file already exists"
        log_info "Verify settings in: $config_file"
    fi
    
    log_info "pisugar-fx configuration complete ✓"
}

################################################################################
# PHASE 11: VALIDATION AND TESTING
################################################################################

phase_validation() {
    log_step "Phase 11: Validation and Component Testing"
    
    log_info "Checking dump1090 binary..."
    home_dir="/home/$(logname 2>/dev/null || echo 'pi')"
    if [ -f "$home_dir/dump1090/dump1090" ] && [ -x "$home_dir/dump1090/dump1090" ]; then
        log_info "dump1090 binary found and executable ✓"
    else
        log_error "dump1090 binary not found or not executable"
    fi
    
    log_info "Checking readsb service..."
    if systemctl is-enabled readsb &>/dev/null; then
        log_info "readsb service is enabled ✓"
    fi
    
    log_info "Checking pisugar-fx Python syntax..."
    if python3 -m py_compile "$home_dir/pisugar-fx/flight/flight_tracker.py" 2>/dev/null; then
        log_info "pisugar-fx Python files have valid syntax ✓"
    else
        log_warn "Python syntax check failed - check flight_tracker.py for errors"
    fi
    
    log_info "Checking systemd services..."
    for service in dump1090 create-uap0 pisugar-fx; do
        if systemctl is-enabled "$service.service" &>/dev/null; then
            log_info "  $service.service is enabled ✓"
        else
            log_error "  $service.service is NOT enabled"
        fi
    done
    
    log_info "Checking avahi-daemon..."
    if systemctl is-active --quiet avahi-daemon; then
        log_info "avahi-daemon is running ✓"
    else
        log_warn "avahi-daemon is not running - will start on boot"
    fi
    
    log_info "Validation complete ✓"
}

################################################################################
# PHASE 12: SUMMARY AND REBOOT PROMPT
################################################################################

phase_summary() {
    log_step "Phase 12: Summary and Final Steps"
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}pisugar-fx Installation Complete${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    echo "Services installed and enabled:"
    echo "  - dump1090 (ADS-B decoder, port 31005)"
    echo "  - create-uap0 (virtual Wi-Fi interface setup)"
    echo "  - readsb (aircraft aggregator)"
    echo "  - pisugar-fx (display application)"
    echo ""
    
    echo "Network configuration:"
    echo "  - Home Wi-Fi: client mode on wlan0"
    echo "  - Access Point: ronPi-AP on uap0 (WPA2)"
    echo "  - mDNS: ronPi.local:5000"
    echo ""
    
    echo "Next steps:"
    echo "  1. Reboot to start all services:"
    echo "     sudo reboot"
    echo ""
    echo "  2. After boot, check service status:"
    echo "     systemctl status pisugar-fx"
    echo "     journalctl -u pisugar-fx -f"
    echo ""
    echo "  3. Connect to ronPi-AP from your phone and visit:"
    echo "     http://ronPi.local:5000"
    echo ""
    echo "  4. Plug in your RTL-SDR dongle and verify aircraft are received"
    echo ""
    
    echo -e "${YELLOW}Important Notes:${NC}"
    echo "  - RTL-SDR udev rules are active; you may need to:"
    echo "    sudo rmmod dvb_usb_rtl28xxu"
    echo "  - dump1090 runs on ports 31001-31005 (not 30001-30005)"
    echo "  - readsb reads from dump1090 via Beast protocol on port 31005"
    echo ""
    
    read -p "Reboot now to start services? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rebooting in 10 seconds... press Ctrl+C to cancel"
        sleep 10
        reboot
    else
        log_info "Setup complete. Remember to reboot when ready."
        log_info "  sudo reboot"
    fi
}

################################################################################
# MAIN SCRIPT EXECUTION
################################################################################

main() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║      pisugar-fx Setup Script           ║${NC}"
    echo -e "${BLUE}║      Raspberry Pi Flight Tracker       ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
    
    # Run all phases
    phase_preflight
    phase_dependencies
    phase_rtlsdr_permissions
    phase_pisugar_repo
    phase_dump1090
    phase_readsb
    phase_systemd_services
    phase_wifi_ap
    phase_avahi
    phase_pisugar_config
    phase_validation
    phase_summary
}

# Run main function
main