#!/usr/bin/env bash
# wrapper.sh : Runs main.py and acts on status in panic_file because Gunicorn gives no returncodes we can use.
#-----------------------------------------------------------------------------
# Copyright (C) 2026 Brian J. Andersen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#-----------------------------------------------------------------------------

# -- Setting paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/venv/bin/python"
MAIN="$SCRIPT_DIR/current/main.py"
PANIC_FILE="/tmp/hushmonkey_panic"

# --- CRASH LOOP CONFIG ---
CRASH_COUNT=0
MAX_CRASHES=3
TIME_WINDOW=40 # sekunder
LOOP_START_TIME=$(date +%s)

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

while true; do
	#rm -f "$PANIC_FILE"
	
	# ==============================================================================
	# UNIVERSAL ALSA USB-AUDIO CONFIGURATOR (Med Navne-Detektering)
	# ==============================================================================
	log "Looking for USB Sound device..."

	# Get the first USB sound device from ALSA
	USB_LINE=$(grep -i "usb" /proc/asound/cards | head -n 1)

	if [ -n "$USB_LINE" ]; then
		# Get index, Shotname/ID & description
		USB_CARD_NUM=$(echo "$USB_LINE" | awk '{print $1}')
		USB_CARD_ID=$(echo "$USB_LINE" | cut -d '[' -f2 | cut -d ']' -f1 | xargs)
		USB_CARD_DESC=$(echo "$USB_LINE" | cut -d ':' -f2- | xargs)
		
		log "-> Found: $USB_CARD_DESC"
		log "-> ALSA-Setup: Using device-index $USB_CARD_NUM [$USB_CARD_ID]"
		
		# Find the first volume-controll element (scontrol)
		SCONTROL=$(amixer -c "$USB_CARD_NUM" scontrols | head -n 1 | cut -d"'" -f2)
		
		if [ -n "$SCONTROL" ]; then
			log "-> Adjust volumen-control '$SCONTROL' to 100%..."
			amixer -c "$USB_CARD_NUM" sset "$SCONTROL" 100% unmute > /dev/null 2>&1
			log "-> USB-sounddevice in configured and unmuted!"
		else
			log "-> WARNING: USB-device found, but no mixer-control."
		fi
	else
		log "-> INFO: No USB sound device found in ALSA. Using system defaults (This might go wrong)"
	fi
	# ==============================================================================
	
    log "Starting main.py ..."
    #"$PYTHON" "$MAIN"
	cd "$SCRIPT_DIR/current"
	
	# --- AUTOMATISK WORKER DETEKTERING ---
	# Check for gevent-websocket in venv
	if "$PYTHON" -c "import geventwebsocket" >/dev/null 2>&1; then
		WORKER_CLASS="geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
		log "Gevent-WebSocket found: Using WebSocket Worker."
	else
		WORKER_CLASS="gevent"
		log "Gevent-WebSocket NOT found fundet: Fallback to standard gevent worker."
	fi

	"$SCRIPT_DIR/venv/bin/gunicorn" --worker-class "$WORKER_CLASS" --workers 1 --timeout 0 --graceful-timeout 0 --worker-tmp-dir /dev/shm --bind 0.0.0.0:80 main:app

	#"$SCRIPT_DIR/venv/bin/gunicorn" --worker-class gevent --workers 1 --timeout 0 --graceful-timeout 0 --worker-tmp-dir /dev/shm --bind 0.0.0.0:80 main:app
	#"$SCRIPT_DIR/venv/bin/gunicorn" --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --timeout 0 --graceful-timeout 0 --worker-tmp-dir /dev/shm --bind 0.0.0.0:80 main:app
	if [ -f "$PANIC_FILE" ]; then
		RC_ACTION=$(cat "$PANIC_FILE")
		log "Panic-file found: command = $RC_ACTION"
		
		#rm -f "$PANIC_FILE" # Ryd op
		
		RC=$?
		END_RUN=$(date +%s)
		RUNTIME=$((END_RUN - START_RUN))
		log "main.py exited with RC=$RC (Runtime: ${RUNTIME}s)"
		
		# If program crashes (RC != 143)
		if [ $RC -ne 143 ]; then
			CURRENT_TIME=$(date +%s)
			ELAPSED=$((CURRENT_TIME - LOOP_START_TIME))
			
			# Everything ok for langer time than our window, reset counter
			if [ $ELAPSED -gt $TIME_WINDOW ]; then
				CRASH_COUNT=1
				LOOP_START_TIME=$CURRENT_TIME
			else
				CRASH_COUNT=$((CRASH_COUNT + 1))
			fi
			
			log "Unscheduled crash detected. Crash count: $CRASH_COUNT/$MAX_CRASHES in ${ELAPSED}s"
			
			# Crash limit in time windows - Bail out!
			if [ $CRASH_COUNT -ge $MAX_CRASHES ]; then
				log "CRITICAL: Application is stuck in a crash loop! No more restarts."
				exit 0
			fi
		else
			# clean exit reset counter
			CRASH_COUNT=0
		fi
		
		case $RC_ACTION in
			"reboot")
				log "RC_ACTION=$RC_ACTION - rebooting machine"
				sudo /sbin/reboot
				sleep 10
				;;
			"shutdown")
				log "RC_ACTION=$RC_ACTION - shutdown machine"
				sudo /sbin/poweroff
				sleep 10
				;;
			"exit")
				log "RC_ACTION=$RC_ACTION - Exiting app"
				sleep 10
				exit 0
				;;
			*)
				log "RC_ACTION=$RC_ACTION - unhandled, restarting application"
				sleep 10
				;;
		esac
	else
		log "Gunicorn stopped abnormaly with no specific panic-instruction."
	fi
done
