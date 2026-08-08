## Prerequisites:


- A Raspberry Pi with Raspberry Pi OS installed and networking & SSH configured and connected to the internet* (*internet only required for downloading dependencies during install)
- Make sure your Pi OS is updated.
- Make sure to use a 2.5A powersupply (or better) to make sure you have enough power for the sound interface.
- A USB sound interface that suits you needs (I have tested with a Focusrite Solo and a Behringer U-Phoria UMC22)
- A measurement microphone (I'm using a Superlux ECM-999 condenser microphone - cheap and works well)
- A sound pressure calibrator to calibrate HushMonkey to the microphone (I'm using a Digital Sound 8930B)

> If you have the Pi, and a microphone-cable, then interface, mic and calibrator should cost about 1200 Kr / 160 EUR / 190 USD @ Thomann

## How to install:

1.	Create the user `hush` (can be setup during install of Raspberry Pi OS)
	Login to the Pi with the hush-user.

2.	Make a dir for HushMonkey and enter the dir
	```bash
	hush@hush:~ $ cd ~
	hush@hush:~ $ mkdir HushMonkey
	hush@hush:~ $ cd HushMonkey
	```
	
3.	Download the version you want from /Releases on GitHub and udzip it into HushMonkey/  (ie. 0.1d)\
    together with install.sh
	```bash
	hush@hush:~/HushMonkey $ ls -la
	total 24
	drwxrwxr-x  3 hush hush 4096 May  9 16:01 .
	drwx------ 14 hush hush 4096 May  9 15:59 ..
	drwxrwxr-x  3 hush hush 4096 May  9 16:01 0.1d
 	-rw-rw-rw- 63 hush hush 4096 May  9 install.sh
	```

5.	Copy install.sh to Hushmonkey/
	```bash
 	hush@hush:~/HushMonkey $
 	``` 

6.	Make sure install.sh is executable.
	```bash
	hush@hush:~/HushMonkey $ chmod +x install.sh
	```
	
7.	Run installer. Replace 0.1d with what ever version you want to install.
	```bash
	hush@hush:~/HushMonkey $ ./install.sh 0.1d
	```
	
	First time installing, it will take a few minutes to install the venv-enviroment and the python denpendencies.
	Next time takes only a few seconds unless new denpendencies needs to be downloaded.
	During the install you will be prompted for password for the hush-user when sudo-rights is assigned.

8.	HushMonkey should now be running and accessable on what ever IP-addr. you have assigned to your Pi.

 \
 \
$\color{Orange}\Huge{\textbf{No internet access needed beyond this point}}$ \
 \
 <br/>
 


9.	HushMonkey is set to start on reboot, so reboot your Pi to verify that every thing works.

10.	If a LED is connected to GPIO17 you should see the following pattern : ( `GPIO17 o---[Resistor / R1]----->LED|---o GND` \
Red/Green LED R1=100 Ω  /  Blue LED R1=24 Ω )

| State | Pattern |
| :--- | :--- |
| **All good** | Slow single blink |
| **HushMonkey down, USB audio OK** | Fast single blink |
| **HushMonkey OK, no USB audio** | Slow double-blink |
| **HushMonkey down + no USB audio** | Fast double-blink |

## Calibration: v0.2 and below

1.	Make sure HushMonky is running, USB-soundcard and microphone connected.

2.	Turn on your sound calibrator device and adjust the gain on the soundcard to make sure the signal does not clip (leave some headroom)

3.	Mount your microphone in the calibrator.

4.	In HushMonkey, click Calibrate.
	Click the button that matches your calibrator (ie. if using a 94dB calibrator, click "Start 94 dB")
	Wait for calibration to finish
	Click save
	Click Return to main page.

5.	You should now see the calibrated sound pressure here and on the main display.

## Calibration: v0.3 and above:

1.	Make sure HushMonky is running, USB-soundcard and microphone connected.

2.	Turn on your sound calibrator device and adjust the gain on the soundcard to make sure the signal does not clip (leave some headroom)

3.	Mount your microphone in the calibrator.

4.	Click on the "Setup"-tab

5.	Click the button that matches your calibrator (ie. if using a 94dB calibrator, click "Start 94 dB")
	Wait for calibration to finish
	Click save

5.	You should now see the calibrated sound pressure here as well as on the "LAF Meter"-tab

## Upgrading and Rollback:

install.sh takes care of dependencies, deployment of software and creation of services.

#### Usage:
	Install/activate a version  : ```./install.sh [version]```  
	Reactivate the previously active version : ```./install.sh --rollback```

 > **After install/upgrade/rollback please reboot and refresh browser to make sure backend and frontend are running the same version**

#### Examples:

- Install version, ie. 0.2b
	```bash
	hush@hush:~/HushMonkey $ ./install.sh 0.2b
	hush@hush:~/HushMonkey $ sudo reboot
	```

- Upgrade to version ie. 0.3a
	```bash
	hush@hush:~/HushMonkey $ ./install.sh 0.3a
	hush@hush:~/HushMonkey $ sudo reboot
	```

- Rollback to previous version
	```bash
	hush@hush:~/HushMonkey $ ./install.sh --rollback
	hush@hush:~/HushMonkey $ sudo reboot
	```
