#!/usr/bin/python

import time
import binascii
from signal import pause
import signal
import subprocess
import serial
import colorama
import colors
import baker
import os
import sys
import traceback
import re
from datetime import datetime
from tendo import singleton
import RPi.GPIO as GPIO

GSM_PWR_PIN = 7                 # 31 on SIM7600X
GSM_SERIAL_DEV = "/dev/ttyUSB0" # /dev/ttyS0 on SIM7600X
GPIO_GATE_UP    = 36
GPIO_GATE_DOWN  = 38 # Not in use
GPIO_GATE_HOLD  = 40 # Not in use

MP3_PLAYER = 'mpg321'
curent_datetime_str = datetime.now().strftime("%Y%m%d_%I%M")
LOG_FILE_NAME = "ctl_%s.log" % curent_datetime_str
OPERATION_LOG = "operation_%s.log"
PING_INTERVAL = 60 * 2
MAX_FAILS_IN_A_ROW = 4

GATEUP_TRIGGER_FILE = 'GATEUP'
KILL_FILE = 'KILLAPP'

MUST_EXITS_USB = [b'148f:7601', b'0403:6001']

log_file = None
def logPrint(text, is_verbose=True):
    global log_file
    if not log_file:
        log_file_size = 0
        try:
            log_file_size = os.path.getsize(LOG_FILE_NAME)
        except OSError:
            log_file_size = 0
        if (1024 * 1024 * 100) < log_file_size:
            os.unlink(LOG_FILE_NAME)
        log_file = open(LOG_FILE_NAME, 'a')
    if is_verbose:
        print(text)
        log_file.write(time.ctime() + '\t' + text+"\n")
        log_file.flush()


class GateCtl(object):
    def __init__(self, up_gpio, down_gpio, hold_gpio, verbose=False):
        logPrint("Starting GateCtl")
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(up_gpio, GPIO.IN)
        GPIO.setup(down_gpio, GPIO.IN)
        GPIO.setup(hold_gpio, GPIO.IN)
        self.verbose = verbose
        self.up_gpio = up_gpio
        self.down_gpio = down_gpio
        self.hold_gpio = hold_gpio

    def close(self):
        GPIO.cleanup()

    def oprate_pin(self, pin_number, active_low=False):
        GPIO.setup(pin_number, GPIO.OUT)
        if active_low:
            GPIO.output(pin_number, GPIO.LOW)
        else:
            GPIO.output(pin_number, GPIO.HIGH)
        time.sleep(2)
        if active_low:
            GPIO.output(pin_number, GPIO.HIGH)
        else:
            GPIO.output(pin_number, GPIO.LOW)
        time.sleep(0.05)
        GPIO.setup(pin_number, GPIO.IN)

    def up(self):
        logPrint(colors.green("Gate up!"))
        self.oprate_pin(self.up_gpio, False)

    def down(self):
        logPrint(colors.red("Gate down!"))
        self.oprate_pin(self.down_gpio, False)

    def hold(self, t):
        logPrint(colors.yellow("Gate hold it!"))
        self.oprate_pin(self.hold_gpio, True)
        logPrint(colors.yellow("Release"))

class GSMHat(object):
    def __init__(self, verbose=False):
        logPrint("Starting GSMHat")
        GPIO.setup(GSM_PWR_PIN, GPIO.OUT)
        self.verbose = verbose
        self.serial = serial.Serial(GSM_SERIAL_DEV, 115200, timeout=1)
        self.pwrOnIfNeeded()
        logPrint("Connected to GSM hat")
        self.recv()

    def pwrOnIfNeeded(self):
        if self.pingDevice():
            return False
        # Try to power up the GSM Hat
        logPrint("Need to startup GSM hat")
        self.pwrSwitch()
        logPrint("Done - trying to ping GSM hat")
        if not self.pingDevice():
            raise Exception("GSM board error")
        logPrint("GSM hat is now on!")
        return True

    def configure(self):
        logPrint(colors.blue("Reconfiguring SMS format"))
        self.sendCmd(b'AT+CSCS="UCS2"')
        data = self.recv()
        assert b"OK" in data, "Cant setup SMS to UCS2"
        self.sendCmd(b"AT+CMGF=1")
        data = self.recv()
        assert b"OK" in data, "Cant setup SMS to TEXT mode"

    def pwrSwitch(self):
        GPIO.output(GSM_PWR_PIN, GPIO.LOW)
        time.sleep(4)
        GPIO.output(GSM_PWR_PIN, GPIO.HIGH)
        logPrint("GSM hat power on")
        time.sleep(20)

    def pingDevice(self):
        self.sendCmd(b"AT")
        recv = self.recv(quiet=True)
        if 10 < len(recv) and self.verbose:
            logPrint("Got extra data: " + colors.red(recv.decode('utf8')))
        return b"OK" in recv[-10:]

    def readSMS(self):
        self.configure()
        messages = []
        self.sendCmd(b'AT+CMGL="REC UNREAD"')
        smsData = self.normalizedRecv()
        logPrint("SMS data: " + colors.green(smsData))
        for l in smsData:
            if l.startswith(b'OK'):
                break
            if l.startswith(b'ERROR'):
                break
            if l.startswith(b'+CMGL: '):
                smsInfo = l[len(b'+CMGL: '):].split(b',')
                smsId = int(smsInfo[0])
                smsSender = smsInfo[2].replace(b'"', b'')
                smsSender = binascii.unhexlify(smsSender).decode('utf-16be')
                continue
            try:
                msg = binascii.unhexlify(l).decode('utf-16be')
            except:
                continue
            logPrint("%d: %s sent: %s (%s)" % (smsId, smsSender, l, msg))
            messages.append((smsId, smsSender, msg))
        # Delete all stored SMS
        self.sendCmd(b'AT+CMGDA="DEL ALL"')
        deleteResult = self.recv()
        if self.verbose:
            logPrint(colors.blue(deleteResult.decode('utf8')))
        return messages

    def normalizedRecv(self):
        return [x.strip() for x in self.recv().replace(b'\r\n', b'\n').split(b'\n') if x.strip()]

    def recv(self, quiet=False):
        data = self.serial.read(self.serial.inWaiting())
        clearData = data.decode('utf8').strip()
        if clearData and self.verbose and not quiet:
            logPrint(colors.faint(colors.red(clearData)))
        return data

    def sendCmd(self, cmd):
        self.send(cmd + b'\r\n')
        time.sleep(0.1)

    def send(self, data):
        self.serial.write(data)

    def close(self):
        self.serial.close()

def runInBackground(cmd):
    logPrint("Executing: " + colors.blue(cmd))
    _ = subprocess.Popen(
            cmd,
            shell=True,
            stdin=None, close_fds=True)

def playMusic(fname):
    # Clean current playing music
    kill_process_by_name(MP3_PLAYER)
    cmd = "%s %s/%s &" % (MP3_PLAYER, os.path.abspath('.'), fname)
    if 0 == os.geteuid():
        runInBackground('runuser -l pi -c "%s"' % cmd)
    else:
        runInBackground(cmd)

class GateCtlOverGSM(object):
    def __init__(self, verbose=False):
        print("Starting GateCtlOverGSM")
        self.verbose = verbose
        self.gateCtl = GateCtl(GPIO_GATE_UP, GPIO_GATE_DOWN, GPIO_GATE_HOLD, verbose=verbose)
        self.gsm = GSMHat(verbose=verbose)
        self.lastPing = time.time()

    def __enter__(self):
        return self

    def __exit__(self, t, value, tb):
        print('__exit__ %r %r %r' % (t, value, tb))
        self.gsm.close()
        self.gsm = None
        self.gateCtl.close()
        self.gateCtl = None
        if tb or value or t:
            trace = traceback.format_exc()
            logPrint(colors.red(trace))
        return

    def writeToOperationLog(self, msg):
        operationLog = OPERATION_LOG % datetime.now().strftime("%Y%m%d")
        with open(operationLog, "ab") as log:
            log.write(time.ctime().encode('utf8') + msg)

    def answerCall(self, data):
        call_details = data.split()
        callerInfo = call_details[1]
        if callerInfo.count(b',') < 1:
            return False
        callerId = callerInfo.split(b',')[0].replace(b'"', b'')
        logPrint("%r is calling" % callerId)
        whitelist = open('whitelist.txt', 'rb').read()
        whitelist = whitelist.split()
        isAllowedIn = False
        if callerId in whitelist or (b'+972' + callerId[1:]) in whitelist:
            isAllowedIn = True
            self.gateUp()
        self.writeToOperationLog(b'\tCall:\t' + callerId + b'\t%r\n' % isAllowedIn)
        return isAllowedIn

    def gateUp(self):
        self.gateCtl.up()

    def handleSMS(self, msgs):
        for _, smsSender, msg in msgs:
            self.writeToOperationLog( \
                b'\tSMS:\t' + smsSender.encode('utf8') + \
                b'\t%s\n' % msg.encode('utf8', errors='ignore'))
            for fname in os.listdir('./mp3/'):
                if not fname.endswith('.mp3'):
                    continue
                if fname.startswith(msg) or msg.startswith(fname[:-4]):
                    playMusic('./mp3/%s' % fname)
                    break

    def resetIfNeeded(self):
        if self.gsm.pwrOnIfNeeded():
            self.handleSMS(self.gsm.readSMS())

    def mainLoop(self):
        while True:
            time.sleep(0.1)
            data = self.gsm.recv()
            lines = data.replace(b'\r\n', b'\n').split(b'\n')
            for l in lines:
                l = l.strip()
                if l.startswith(b'+CLIP:'):
                    self.answerCall(l)
                if l.startswith(b'+CMTI:'):
                    self.handleSMS(self.gsm.readSMS())
                if b"POWER DOWN" in l:
                    time.sleep(4)
                    self.resetIfNeeded()
            if os.path.isfile(GATEUP_TRIGGER_FILE):
                os.unlink(GATEUP_TRIGGER_FILE)
                self.gateUp()
            if os.path.isfile(KILL_FILE):
                os.unlink(KILL_FILE)
                logPrint(colors.magenta("KTHXBYE"))
                return False
            if PING_INTERVAL < (time.time() - self.lastPing):
                logPrint("Pi temperature is %f" % get_pi_temperature())
                self.resetIfNeeded()
                self.lastPing = time.time()
                validate_usb()

@baker.command
def kill_process_by_name(target):
    stdout, stderr = subprocess.Popen(['ps', '-A'], stdout=subprocess.PIPE).communicate()
    if isinstance(target, str):
        target = target.encode('utf8')
    for l in stdout.splitlines():
        if target not in l:
            continue
        pid = int(l.split()[0])
        logPrint(colors.red("Killing %d with command line: '%s'" % (pid, l.split()[3])))
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
        logPrint(colors.red("Killed %d" % pid))

@baker.command
def get_pi_temperature():
    stdout, _ = subprocess.Popen(['vcgencmd', 'measure_temp'], stdout=subprocess.PIPE).communicate()
    result = re.findall(b"([0-9\\.]*)'C", stdout)
    if 1 != len(result):
        return 0.0
    return float(result[0])

@baker.command
def validate_usb():
    stdout, _ = subprocess.Popen(['lsusb'], stdout=subprocess.PIPE).communicate()
    for usb_id in MUST_EXITS_USB:
        if usb_id not in stdout:
            logPrint(colors.red("USB failure!"))
            reboot_system()
            return True
    return False

@baker.command
def reboot_system():
    print(colors.red("Rebooting!!!"))
    runInBackground("reboot")

@baker.command
def run(verbose=False):
    me = singleton.SingleInstance()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    logPrint("My PID is %d" % os.getpid())
    playMusic('ping.mp3')
    logPrint(colors.blue("Starting!"))
    lastFail = 0
    failCount = 0
    keepRunning = True
    while keepRunning:
        try:
            with GateCtlOverGSM(verbose=verbose) as gateCtlOverGSM:
                keepRunning = gateCtlOverGSM.mainLoop()
        except:
            traceback.print_exc(file=log_file)
            time.sleep(5)
            if 60 < (time.time() - lastFail):
                failCount = 1
            else:
                failCount += 1
            print("System error %d" % failCount)
            lastFail = time.time()
            if MAX_FAILS_IN_A_ROW < failCount:
                reboot_system()

if __name__ == '__main__':
    colorama.init(strip=False)
    baker.run()

