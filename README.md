# gatectl
Control car gate at my building

# setup
* Flash `2020-05-27-raspios-buster-full-armhf.zip`
* create ssh empty file on the SDCard
* First boot
* SSH to IP, pi/raspberry
* sudo rasp-config
* update tool
* Change password
* Setup WiFi
* Boot option set to Console Autologin
* Interface option - Serial - Disable login over serial, Enable serial
* Make sure SSH interface is enabled
* Advance - Audio - Headphones
* Reboot
* `sudo apt update`
* `sudo apt upgrade -y`
* `sudo apt install espeak mpg321 python3-pip vim -y`
* ```sudo rm `python` ```
* ```sudo ln -s `python3` /usr/bin/python```
* connect over winscp
* `copy all mp3 to /home/pi/src/mp3`
* `copy ping.mp3 gatectl.py gatectl.sh whitelist.txt to /home/pi/src`
* `alsamixer` to set headphone volume to max
* `python -m pip install --upgrade pip`
* `python -m pip install tendo ansicolors colorama baker`
* `sudo vim /etc/rc.local and /home/pi/.bashrc` - Add before the `exit 0`
```/home/pi/src/gatectl.sh &```
* Set the timezone
