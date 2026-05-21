#!/usr/bin/env bash
# wrapper.sh : Runs main.py and acts on its return code.
#   RC=0	restart main.py
#   RC=170	reboot the machine
#   RC=171	power off the machine
#	RC=172	Exit wrapper
#   other	log RC and restart the application
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/venv/bin/python"
MAIN="$SCRIPT_DIR/current/main.py"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
while true; do
    log "Starting main.py ..."
    "$PYTHON" "$MAIN"
    RC=$?
    log "main.py exited with RC=$RC"
    case $RC in
        0)
            log "RC=0 - restarting"
            ;;
        170)
            log "RC=170 - rebooting machine"
            sudo /sbin/reboot
            exit 0
            ;;
        171)
            log "RC=171 - powering off machine"
            sudo /sbin/poweroff
            exit 0
            ;;
		172)
            log "RC=172 - exit wrapper"
            exit 0
            ;;

        *)
            log "RC=$RC - unhandled, restarting application"
            ;;
    esac
done
