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
* Update the system and install packages:
```
sudo apt update
sudo apt upgrade -y
sudo apt install espeak mpg321 python3-pip vim -y
sudo rm `which python`
sudo ln -s `which python3` /usr/bin/python
sudo python -m pip install --upgrade pip
sudo python -m pip install tendo ansicolors colorama baker future telepot pyserial rpi-rf
```
* Over FTP/SFTP
    * copy all mp3 to `/home/pi/src/mp3`
    * copy `ping.mp3`, `gatectl.py`, `gatectl.sh` and `whitelist.txt` to `/home/pi/src`
* Add gate control script to startup by editing `/etc/rc.local` and `/home/pi/.bashrc` - Add before the `exit 0`
```
/home/pi/src/gatectl.sh &
```
* More configurations tweaks
    * `alsamixer` to set headphone volume to max
    * Edit `/boot/config.txt`
        * Disable Bluetooth to reduce noise by adding ```dtoverlay=disable-bt```
        * If using external WiFi dongle add ```dtoverlay=disable-wifi```
    * Set the timezone to make logs more readable
    * Execute:
```
sudo systemctl disable hciuart.service
sudo systemctl disable bluealsa.service
sudo systemctl disable bluetooth.service
````

