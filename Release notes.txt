0.1
+ Lets welcome the Chill Chimpanzee - The Hush Monkey
+ Initial version that works

0.1b
+ JS cleanup: functions rewritten to use a more robust try/catch-logic in web-calls and nonoverlapping requests on auto refresh of page items.
	* about.html - AS IS
	* cal.html DONE
	* index.html DONE
	* limits.html DONE
	* reboot.html DONE
	* restart.html DONE
	* shutdown.html DONE

+ added http-endpoint /exit to exit the wrapper for debugging purposes.

+ added hushbeat.sh = heartbeat-LED showing status on GPIO17 (  GPIO17 o---##R##------>led|---o GND  )
	State				Pattern
	-------------------------------------------------
	All good			Slow single blink
	HushMonkey down, USB audio OK	Fast single blink 
	HushMonkey OK, no USB audio	Slow double-blink
	HushMonkey down + no USB audio	Fast double-blink

+ added systemd service-scripts to start/stop wapper.sh and hushbeat.sh

+ Problem in main.py: High CPU usage + sluggish UI-responce

	Main culprits:
	Problem		Before					After
	--------------------------------------------------------------------------------
	buf_1m mean	Iterate 2.88M floats every 21ms		O(1) running sum
	buf_10m mean	Iterate 28.8M floats every 21ms		O(1) running sum
	Memory		~46 MB just for buffers			~37 KB for chunk sums
	
	Nice to have:
	+ make sure flask is running threaded
	+ Make sure cache-control=no on /data
	+ change index.html to update every 300ms (500ms before)
	+ sligthly tighter sleep in AudioLoop for faster exit responce

	Result: Went from ~98% CPU to ~8% on Raspberry Pi 3+

0.1c:
+ comment cleanup in main.py
+ version info passed to about.html via http-request
+ removed version-number from name in index.html
+ changed logo to webp-filetype for smaller size while keeping quality
+ adjusted timeouts for retrys in restart/reboot/shutdown.html
+ updated install.sh to allow HTTP on port 80
+ changed main.py to use port 80 for HTTP
+ added audio input-device info on calibration-page and restart-option to update device.

0.1d:
+ Changed exit RC in main.py to avoid boot-loop if wrapper can't launch main.py (ask me how I know...)
+ Updated wrapper.sh to reflect new RC values
+ Updated install.sh to take care of apt-dependensies, sudo-rights and add log-rotation on /var/log/hushmonkey.log

0.2a:
+ changed buffer size (buf_1m & buf_10m) to reduce memory footprint
+ draft implementation of 1/3oct spectrum analyzer with peaks, Y-axis zoom, slow/fast decay.

0.2b:
+ Fixed rare occations where spectrum graph would resize to about 25%
+ Analyzer settings synced from server and across multiple device if more is connected (CSS and JS)
+ updated naming of sub-pages for consistency
+ removed startup-script for Windows - was only used during initial development on windows, moved dev to RaspPi3.
+ This is the last in the Chill Chimpanzee series. Consider this the lightweight alternative. Functions absolutely brillantly.

0.3a:
+ Say hello to the Grumpy Gorilla, a new release series with new goodies and features.
+ Complete restructured frontend and redesign of GUI to SinglePageApplication
+ Backend mostly the same with improvements and new features.
+ Moved GUI<->backend communication to sockets where data is streamed in big volumes.
+ Waterfall analyses on main-page
+ Web-call to pass info from frontend to backend-log file if needed.
+ Dark/Light theme on main page to show alerts in two different ways. Stores selection on device. Follows device dark-setting in operating system.
+ L10 & L90 calculations
+ LAF trend. Is the soundlevel increasing or decreasing over the last 10 minutes and how fast.
+ Time to limit prediction.: For how long we can keep the current soundlevel before we breach the LAeq10-limit
+ Delay and phase analyses.
+ Added pink noise generator for delay and phase analyses.
+ Exit-method to quit Gunicorn and pass a "returncode" to the wrapper.sh
+ Still around 60% CPU on a Pi3 with delay-analasys running