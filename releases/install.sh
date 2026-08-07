#!/usr/bin/env bash
# =============================================================================
# HushMonkey Install Script
# =============================================================================
# Directory layout after install:
#
#   ~/HushMonkey/
#   ├── install.sh               (this script)
#   ├── default_mic.txt			 (calibration data for microphone)
#   ├── limits.txt               (limits data for LAF alerts)
#   ├── hushbeat.py				 (Monitors the main application+soundcard and blinks the LED)
#   ├── current -> 0.1b          (symlink, always points to active version)
#   ├── venv/                    (shared virtualenv, created once)
#   └── 0.3b/
#       ├── main.py
#       ├── python_requirements.txt
#       ├── wrapper.sh           (wrapper-script. Handles restarts, shutdown and crash recovery)
#       ├── html/				 (Fontend HTML, CSS & JS)
#       └── preset_curves        (prest house curves as a startingpoint)
#
# Usage:
#   ./install.sh [version]       --> install/activate a version 
#   ./install.sh --rollback      --> reactivate the previously active version
#
# After install/upgrade/rollback please reboot and refresh browser to make sure backend and frontend are running the same version
#
# =============================================================================

set -euo pipefail

# --- Config ------------------------------------------------------------------
INSTALL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$INSTALL_ROOT/venv"
CURRENT_LINK="$INSTALL_ROOT/current"
PREVIOUS_VERSION_FILE="$INSTALL_ROOT/.previous_version"

# --- Colours -----------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[install]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}   $*"; }
error() { echo -e "${RED}[error]${NC}  $*"; exit 1; }

# --- Rollback ----------------------------------------------------------------
if [[ "${1:-}" == "--rollback" ]]; then
    [[ -f "$PREVIOUS_VERSION_FILE" ]] || error "No previous version recorded — cannot rollback"
    PREVIOUS="$(cat "$PREVIOUS_VERSION_FILE")"
    [[ -d "$INSTALL_ROOT/$PREVIOUS" ]] || error "Previous version directory not found: $INSTALL_ROOT/$PREVIOUS"
    CURRENT="$(readlink "$CURRENT_LINK" 2>/dev/null || echo "(none)")"
    warn "Rolling back: $CURRENT --> $PREVIOUS"
    echo "$CURRENT" > "$PREVIOUS_VERSION_FILE"
    ln -sfn "$PREVIOUS" "$CURRENT_LINK"
    info "✓ Rollback complete — active version is now: $PREVIOUS"
    exit 0
fi

# --- No argument: show status and usage --------------------------------------
if [[ $# -eq 0 ]]; then
    echo ""
    if [[ -L "$CURRENT_LINK" ]]; then
        ACTIVE="$(readlink "$CURRENT_LINK")"
        echo -e "  ${GREEN}●${NC} Active version : $ACTIVE"
    else
        echo -e "  ${RED}●${NC} No active version — 'current' symlink does not exist"
    fi
    if [[ -f "$PREVIOUS_VERSION_FILE" ]]; then
        echo -e "  ${YELLOW}●${NC} Previous version: $(cat "$PREVIOUS_VERSION_FILE")"
    fi
    echo ""
    echo "  Usage:"
    echo "    ./install.sh <version>     — install and activate a version"
    echo "    ./install.sh --rollback    — reactivate the previous version"
    echo ""
    exit 0
fi

VERSION="${1}"
VERSION_DIR="$INSTALL_ROOT/$VERSION"
REQUIREMENTS="$VERSION_DIR/python_requirements.txt"

# --- Checks ------------------------------------------------------------------
info "Installing HushMonkey version $VERSION"
info "Install root: $INSTALL_ROOT"

[[ -d "$VERSION_DIR" ]] || error "Version directory not found: $VERSION_DIR"
[[ -f "$REQUIREMENTS" ]] || warn  "No python_requirements.txt found in $VERSION_DIR — skipping pip install"

command -v python3 &>/dev/null || error "python3 not found. Please install Python 3 first."

# --- Record previous version for rollback ------------------------------------
if [[ -L "$CURRENT_LINK" ]]; then
    OLD_VERSION="$(readlink "$CURRENT_LINK")"
    if [[ "$OLD_VERSION" != "$VERSION" ]]; then
        info "Recording previous version for rollback: $OLD_VERSION"
        echo "$OLD_VERSION" > "$PREVIOUS_VERSION_FILE"
    fi
fi

# --- Optionally add hush to sudoers (passwordless for required commands) -----
echo ""
read -r -p "$(echo -e "${GREEN}[install]${NC} Grant passwordless sudo for reboot/poweroff/setcap? [y/N] ")" ADD_SUDOERS
if [[ "${ADD_SUDOERS,,}" == "y" ]]; then
    SUDOERS_FILE="/etc/sudoers.d/hushmonkey"
    CURRENT_USER="${SUDO_USER:-$(whoami)}"
    info "Writing $SUDOERS_FILE for user: $CURRENT_USER"
    sudo tee "$SUDOERS_FILE" > /dev/null << SUDOERS
# HushMonkey — passwordless sudo for required commands only
$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/reboot, /sbin/poweroff, /sbin/setcap
SUDOERS
    sudo chmod 0440 "$SUDOERS_FILE"
    # Validate the file — if visudo check fails, remove it to avoid locking out sudo
    if sudo visudo -cf "$SUDOERS_FILE" &>/dev/null; then
        info "Sudoers file validated and installed"
    else
        warn "Sudoers file failed validation — removing to be safe"
        sudo rm "$SUDOERS_FILE"
    fi
else
    info "Skipping sudoers — you may be prompted for a password on reboot/poweroff"
fi

# --- Updating apt, just in case we need it.
sudo apt-get update -qq

# --- System dependencies (PortAudio) -----------------------------------------
PORTAUDIO_PKG=$(apt-cache search portaudio | grep -i 'dev' | awk '{print $1}' | head -1)
if [[ -z "$PORTAUDIO_PKG" ]]; then
    warn "No PortAudio dev package found in apt — sounddevice may not work"
elif dpkg -s "$PORTAUDIO_PKG" &>/dev/null 2>&1; then
    info "PortAudio ($PORTAUDIO_PKG) already installed — skipping"
else
    info "Installing PortAudio ($PORTAUDIO_PKG, required for sounddevice)"
    sudo apt-get install -y "$PORTAUDIO_PKG"
fi

# --- Shared venv (create only if it doesn't exist yet) -----------------------
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating shared virtualenv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    info "Shared virtualenv already exists — reusing it"
fi

# --- Install / update Python requirements ------------------------------------
# Always runs: ensures new version's packages are installed even on version switch
if [[ -f "$REQUIREMENTS" ]]; then
    info "Installing Python requirements from $REQUIREMENTS"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS"
    info "Python packages installed successfully"
fi

# --- Update the 'current' symlink --------------------------------------------
if [[ -L "$CURRENT_LINK" ]]; then
    OLD_TARGET="$(readlink "$CURRENT_LINK")"
    if [[ "$OLD_TARGET" == "$VERSION" ]]; then
        info "'current' already points to $VERSION — nothing to change"
    else
        warn "Updating 'current': $OLD_TARGET --> $VERSION"
        ln -sfn "$VERSION" "$CURRENT_LINK"
    fi
elif [[ -e "$CURRENT_LINK" ]]; then
    error "'current' exists but is not a symlink. Please remove it manually: $CURRENT_LINK"
else
    info "Creating symlink: current --> $VERSION"
    ln -s "$VERSION" "$CURRENT_LINK"
fi

# --- Link root wrapper.sh -> current/wrapper.sh ------------------------------
info "Updating wrapper symlink: wrapper.sh --> current/wrapper.sh"
ln -sfn "current/wrapper.sh" "$INSTALL_ROOT/wrapper.sh"

#--- Move wrapper.sh from version dir if present ---------------------------
# VERSION_WRAPPER="$VERSION_DIR/wrapper.sh"
# if [[ -f "$VERSION_WRAPPER" ]]; then
    # warn "Moving wrapper.sh from version dir (it lives at root level now)"
    # mv "$VERSION_WRAPPER" $INSTALL_ROOT
# fi

# --- Grant permission to bind port 80 without root ---------------------------
VENV_PYTHON="$VENV_DIR/bin/python3"
if command -v setcap &>/dev/null; then
    REAL_PYTHON="$(readlink -f "$VENV_PYTHON")"
    info "Granting port 80 binding capability to $REAL_PYTHON"
    sudo setcap 'cap_net_bind_service=+ep' "$REAL_PYTHON"
else
    warn "setcap not found — installing libcap2-bin"
    sudo apt-get install -y libcap2-bin &>/dev/null
    REAL_PYTHON="$(readlink -f "$VENV_PYTHON")"
    sudo setcap 'cap_net_bind_service=+ep' "$REAL_PYTHON"
fi

# --- Log rotation -----------------------------------------------------------
LOGROTATE_FILE="/etc/logrotate.d/hushmonkey"
info "Installing logrotate config --> $LOGROTATE_FILE"
sudo tee "$LOGROTATE_FILE" > /dev/null << 'LOGROTATE'
/var/log/hushmonkey.log {
    size 10M
    rotate 5
    compress
    missingok
    notifempty
    copytruncate
}
LOGROTATE
info "Log rotation configured (10MB max, 5 files kept, compressed)"

# --- Install systemd service files ------------------------------------------
SERVICE_SRC="$VERSION_DIR"
SYSTEMD_DIR="/etc/systemd/system"

for SERVICE in hushmonkey.service hushbeat.service; do
    if [[ -f "$SERVICE_SRC/$SERVICE" ]]; then
        info "Installing $SERVICE --> $SYSTEMD_DIR/$SERVICE"
        sudo cp "$SERVICE_SRC/$SERVICE" "$SYSTEMD_DIR/$SERVICE"
    else
        warn "$SERVICE not found in $SERVICE_SRC — skipping"
    fi
done

# Override.conf for hushmonkey.service
OVERRIDE_SRC="$SERVICE_SRC/override.conf"
OVERRIDE_DIR="$SYSTEMD_DIR/hushmonkey.service.d"
if [[ -f "$OVERRIDE_SRC" ]]; then
    info "Installing override.conf --> $OVERRIDE_DIR/override.conf"
    sudo mkdir -p "$OVERRIDE_DIR"
    sudo cp "$OVERRIDE_SRC" "$OVERRIDE_DIR/override.conf"
else
    warn "override.conf not found in $SERVICE_SRC — skipping"
fi

# # Move hushbeat.py to the HushMonkey root dir
# if [[ -f "$SERVICE_SRC/hushbeat.py" ]]; then
    # info "Moving hushbeat.sh -> $INSTALL_ROOT/hushbeat.sh"
    # cp "$SERVICE_SRC/hushbeat.py" "$INSTALL_ROOT/hushbeat.py"
    # chmod +x "$INSTALL_ROOT/hushbeat.py"
# else
    # warn "hushbeat.py not found in $SERVICE_SRC — skipping"
# fi

# --- Link hushbeat.py --> current/hushbeat.py ----------------------------------
VERSION_HUSHBEAT="$VERSION_DIR/hushbeat.py"
ROOT_HUSHBEAT="$INSTALL_ROOT/hushbeat.py"

if [[ -f "$VERSION_HUSHBEAT" ]]; then
    chmod +x "$VERSION_HUSHBEAT"
    info "Updating hushbeat symlink: hushbeat.py --> current/hushbeat.py"
    ln -sfn "current/hushbeat.py" "$ROOT_HUSHBEAT"
else
    warn "hushbeat.py not found in $VERSION_DIR — skipping"
fi


# Reload systemd and enable both services
info "Reloading systemd daemon"
sudo systemctl daemon-reload
for SERVICE in hushmonkey.service hushbeat.service; do
    info "Enabling $SERVICE"
    sudo systemctl enable "$SERVICE"
done

# --- Ensure version wrapper.sh is executable and link it ---------------------
VERSION_WRAPPER="$VERSION_DIR/wrapper.sh"
ROOT_WRAPPER="$INSTALL_ROOT/wrapper.sh"

if [[ -f "$VERSION_WRAPPER" ]]; then
    # Gør den faktiske fil eksekverbar inde i versionsmappen
    chmod +x "$VERSION_WRAPPER"
    
    # Opret/opdater symlinket fra roden -> current/wrapper.sh
    info "Updating wrapper symlink: wrapper.sh -> current/wrapper.sh"
    ln -sfn "current/wrapper.sh" "$ROOT_WRAPPER"
else
    warn "wrapper.sh not found in $VERSION_DIR"
fi

# --- Optionally start services -----------------------------------------------
echo ""
read -r -p "$(echo -e "${GREEN}[install]${NC} Start hushmonkey and hushbeat services now? [y/N] ")" START_SERVICES
if [[ "${START_SERVICES,,}" == "y" ]]; then
    for SERVICE in hushmonkey.service hushbeat.service; do
        info "Starting $SERVICE"
        sudo systemctl start "$SERVICE" && info "$SERVICE started" || warn "$SERVICE failed to start — check: journalctl -u $SERVICE"
    done
else
    info "Services not started. Start manually with:"
    echo "      sudo systemctl start hushmonkey.service hushbeat.service"
fi

# --- Check service status ----------------------------------------------------
echo ""
info "Service status:"
for SERVICE in hushmonkey.service hushbeat.service; do
    STATUS="$(systemctl is-active "$SERVICE" 2>/dev/null)"
    if [[ "$STATUS" == "active" ]]; then
        echo -e "  ${GREEN}●${NC} $SERVICE — running"
    else
        echo -e "  ${RED}●${NC} $SERVICE — $STATUS"
        echo "      Check logs with: journalctl -u $SERVICE -n 20"
    fi
done

# --- Done --------------------------------------------------------------------
echo ""
info "✓ Installation complete"
info "  Active version : $VERSION"
info "  Shared venv    : $VENV_DIR"
info "  Symlink        : $CURRENT_LINK --> $VERSION"
if [[ -f "$PREVIOUS_VERSION_FILE" ]]; then
    info "  Previous version: $(cat "$PREVIOUS_VERSION_FILE") (rollback: ./install.sh --rollback)"
fi
echo ""
info "Run the program with:"
echo "      $CURRENT_LINK/wrapper.sh"
echo ""
info "To switch to a different version later:"
echo "      $INSTALL_ROOT/install.sh <new-version>"
echo ""
