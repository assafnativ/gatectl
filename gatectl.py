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
import telepot
from past.builtins import execfile
import RPi.GPIO as GPIO
from rpi_rf import RFDevice

os.chdir(os.path.dirname(os.path.abspath(__file__)))
configs = {}
execfile('config.py', configs)
EXPECTED_CONFIGURATIONS = [
        'GSM_PWR_PIN',
        'GSM_SERIAL_DEV',
        'GPIO_GATE_UP',
        'GPIO_GATE_POWER',
        'MP3_PLAYER',
        'LOG_FILE_NAME',
        'OPERATION_LOG',
        'PING_INTERVAL',
        'MAX_FAILS_IN_A_ROW',
        'GATEUP_TRIGGER_FILE',
        'KILL_FILE',
        'MUST_EXISTS_USB',
        'MAX_USB_FAIL_COUNT',
        'MAX_LOG_FILE_SIZE',
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_LAST_MSG_FILE',
        'TELEGRAM_CHECK_INTERVAL',
        'OPEN_GATE_WORDS_LIST',
        'RF_GPIO',
        'RF_PROTO',
        'RF_PULSELENGTH',
        'RF_CODE']
for config_name in EXPECTED_CONFIGURATIONS:
    assert config_name in configs, "%s configuration is missing in config file" % config_name
    globals()[config_name] = configs[config_name]

log_file = None
def logPrint(text, is_verbose=True):
    global log_file
    if not log_file:
        log_file = safeOpenAppend(LOG_FILE_NAME)
    if is_verbose:
        print(text)
        log_file.write(time.ctime() + '\t' + text+"\n")
        log_file.flush()

def safeOpenAppend(fileName):
    dirName = os.path.dirname(fileName)
    if dirName:
        os.makedirs(dirName, exist_ok=True)
    targetFileSize = 0
    try:
        targetFileSize = os.path.getsize(fileName)
    except OSError:
        targetFileSize = 0
    if MAX_LOG_FILE_SIZE < targetFileSize:
        os.unlink(fileName)
    return open(fileName, 'a')


class GateMachine(object):
    def __init__(self, up_gpio, power_gpio, verbose=False):
        logPrint("Starting GateMachine")
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(up_gpio, GPIO.IN)
        GPIO.setup(power_gpio, GPIO.IN)
        self.verbose = verbose
        self.up_gpio = up_gpio
        self.power_gpio = power_gpio

    def close(self):
        GPIO.cleanup()

    def triggerPin(self, pin_number, active_low=False):
        self.activatePin(pin_number, active_low)
        time.sleep(2)
        self.deactivatePin(pin_number, active_low)

    def activatePin(self, pin_number, active_low=False):
        GPIO.setup(pin_number, GPIO.OUT)
        if active_low:
            GPIO.output(pin_number, GPIO.LOW)
        else:
            GPIO.output(pin_number, GPIO.HIGH)

    def deactivatePin(self, pin_number, active_low=False):
        if active_low:
            GPIO.output(pin_number, GPIO.HIGH)
        else:
            GPIO.output(pin_number, GPIO.LOW)
        time.sleep(0.05)
        GPIO.setup(pin_number, GPIO.IN)

    def up(self):
        logPrint(colors.green("Gate up!"))
        self.triggerPin(self.up_gpio, False)

    def holdDown(self, active_low=False):
        logPrint(colors.red("Gate power off lock!"))
        self.activatePin(self.power_gpio, active_low=active_low)

    def releaseDown(self, active_low=False):
        logPrint(colors.yellow("Gate power unlock!"))
        self.deactivatePin(self.power_gpio, active_low=active_low)

    def resetGate(self, active_low=False):
        logPrint(colors.yellow("Reset gate control"))
        self.activatePin(self.power_gpio, active_low=active_low)
        logPrint("Gate power on")
        time.sleep(4)
        self.deactivatePin(self.power_gpio, active_low=active_low)
        logPrint("Gate power off")

class GSMHat(object):
    def __init__(self, verbose=False):
        logPrint("Starting GSMHat")
        self.initPwrPin()
        self.verbose = verbose
        self.serial = serial.Serial(GSM_SERIAL_DEV, 115200, timeout=1)
        self.pwrOnIfNeeded()
        self.deviceId = self.getDeviceId()[0]
        logPrint("Connected to GSM hat")
        self.recv()

    def initPwrPin(self):
        if not GSM_PWR_PIN:
            return
        GPIO.setup(GSM_PWR_PIN, GPIO.OUT)
        GPIO.output(GSM_PWR_PIN, GPIO.HIGH)

    def getDeviceId(self):
        self.sendCmd(b"ATI")
        id_data = self.normalizedRecv()
        return id_data[:3]

    def pwrOnIfNeeded(self):
        if self.pingDevice():
            return False
        # Try to power up the GSM Hat
        logPrint("Need to power up GSM hat")
        if None == GSM_PWR_PIN:
            return False
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
        if not GSM_PWR_PIN:
            logPrint("No power pin")
            return
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
                # +CMGL: 6,"REC UNREAD","002B003900370032003500300035003200330037003800300039",,"" 0054006500730074
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
            messages.append((smsSender, msg))
        # Delete all stored SMS
        self.sendCmd(b'AT+CMGDA="DEL ALL"')
        self.sendCmd(b'AT+CMGD=0,4')
        deleteResult = self.recv()
        if self.verbose:
            logPrint(colors.blue(deleteResult.decode('utf8')))
        return messages

    def hangUpCall(self):
        self.sendCmd(b'AT+CHUP')

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

class TelegramBot(object):
    def __init__(self, token, lastMsgFileName):
        self.lastMsgId = 0
        self.lastMsgFileName = lastMsgFileName
        if os.path.isfile(lastMsgFileName):
            with open(lastMsgFileName, 'r') as lastMsgFile:
                self.lastMsgId = int(lastMsgFile.read())
        self.bot = telepot.Bot(token)
        try:
            myDetails = self.bot.getMe()
            logPrint(colors.blue(repr(myDetails)))
        except:
            logPrint('No internet / Telegram is down')

    def getMessages(self):
        messages = None
        try:
            messages = self.bot.getUpdates(self.lastMsgId, timeout=1)
        except:
            return []
        result = []
        lastId = self.lastMsgId
        for msg in messages:
            lastId = max(lastId, int(msg['update_id'])+1)
            if 'message' not in msg:
                continue
            content = msg['message']
            sender = content.get('from', {}).get('username', None)
            text = content.get('text', None)
            if text:
                text = text[:100]
            if sender and text:
                result.append((sender, text))
                logPrint("%s sent telegram message: %s" % (colors.yellow(sender), colors.yellow(text)))
        if self.lastMsgId < lastId:
            self.lastMsgId = lastId
            with open(self.lastMsgFileName, 'w') as lastMsgFile:
                lastMsgFile.write(str(lastId))
        return result

@baker.command
def read_telegram_messages():
    telegramBot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_LAST_MSG_FILE)
    for sender, text in telegramBot.getMessages():
        logPrint("%s sent: %s" % (sender, text))

class RFControl(object):
    def __init__(self, rf_gpio, proto, code, pulselength):
        self.rf_gpio = rf_gpio
        self.dev = None
        if not rf_gpio:
            logPrint("RF control is disabled")
            return
        self.proto = proto
        self.code_ranges = code
        self.pulse_ranges = pulselength
        self.last_timestamp = None
        self.dev = RFDevice(self.rf_gpio)
        self.dev.enable_rx()
        if self.proto:
            logPrint("RF control ready - Waiting for protcol %x Code (%r) Pulse length(%r)" %
                    (self.proto, self.code_ranges, self.pulse_ranges))

    def cleanup(self):
        if self.dev:
            logPrint("RF cleanup")
            self.dev.cleanup()
            self.dev = None

    def should_open_the_gate(self):
        if not self.dev:
            return False
        if self.last_timestamp == self.dev.rx_code_timestamp:
            return False
        self.last_timestamp = self.dev.rx_code_timestamp
        proto       = self.dev.rx_proto
        code        = self.dev.rx_code
        pulselength = self.dev.rx_pulselength
        if None != self.proto and proto != self.proto:
            return False
        logPrint("Got RF signal: code %d pulselength %d" % (code, pulselength))
        for pulse_min, pulse_max in self.pulse_ranges:
            if pulse_min <= pulselength <= pulse_max:
                break
        else:
            return False
        for code_min, code_max in self.code_ranges:
            if code_min <= code <= code_max:
                break
        else:
            return False
        return True

@baker.command
def rf_test(gpio):
    gpio = int(gpio)
    rfCtl = RFControl(gpio, None, [(0, 1000)], [(0, 10000)])
    logPrint("Starting loop")
    while True:
        rfCtl.should_open_the_gate()
        time.sleep(0.1)

class GateControl(object):
    def __init__(self, verbose=False):
        logPrint("Starting GateControl")
        self.verbose = verbose
        self.gateMachine = GateMachine(GPIO_GATE_UP, GPIO_GATE_POWER, verbose=verbose)
        self.gsm = GSMHat(verbose=verbose)
        self.telegramBot = None
        if TELEGRAM_BOT_TOKEN:
            self.telegramBot = TelegramBot(TELEGRAM_BOT_TOKEN, TELEGRAM_LAST_MSG_FILE)
        self.lastPing = time.time()
        self.lastTelegramCheck = time.time()
        self.rfCtl = RFControl(RF_GPIO, RF_PROTO, RF_CODE, RF_PULSELENGTH)
        self.usbFailCount = 0
        self.isLocked = False

    def __enter__(self):
        return self

    def __exit__(self, t, value, tb):
        if self.isLocked:
            self.GateMachine.releaseDown()
        self.isLocked = False
        self.gsm.close()
        self.gsm = None
        self.gateMachine.close()
        self.gateMachine = None
        if tb or value or t:
            trace = traceback.format_exc()
            logPrint(colors.red(trace))
        return

    def writeToOperationLog(self, msg):
        operationLog = OPERATION_LOG % datetime.now().strftime("%Y%m%d")
        with open(operationLog, "ab") as log:
            log.write(time.ctime().encode('utf8') + msg)

    def hasGateAccess(self, userId, whiteListFileName, isPhone):
        logPrint("Validating %r with whitelist %s (Is phone: %r)" % (userId, whiteListFileName, isPhone))
        whitelist = []
        userId = userId.strip()
        if isPhone:
            userId = userId.replace(b'-', b'').replace(b' ', b'').replace(b'.', b'')
        with open(whiteListFileName, 'rb') as whiteListFile:
            whitelist.extend(whiteListFile.read().split())
        if userId in whitelist:
            return True
        if isPhone:
            if (b'+972' + userId[1:]) in whitelist:
                return True
            if (b'972' + userId[1:]) in whitelist:
                return True
            if userId.startswith(b'+972') and (b'0' + userId[4:]) in whitelist:
                return True
            if userId.startswith(b'972') and (b'0' + userId[3:]) in whitelist:
                return True
        return False

    def answerCallClip(self, data):
        call_details = data.split()
        callerInfo = call_details[1]
        if callerInfo.count(b',') < 1:
            return False
        callerId = callerInfo.split(b',')[0].replace(b'"', b'')
        if len(callerId) < 3:
            return False
        return self.answerCall(callerId)

    def answerCall(self, callerId):
        logPrint("%r is calling" % callerId)
        isAllowedIn = self.hasGateAccess(callerId, 'whitelist.txt', True)
        if isAllowedIn:
            self.gateUp()
        else:
            logPrint(colors.red("No access to %r" % callerId))
        self.writeToOperationLog(b'\tCall:\t' + callerId + b'\t%r\n' % isAllowedIn)
        # We do not answer calls, just using the caller id
        self.gsm.hangUpCall()
        return isAllowedIn

    def gateUp(self):
        if self.isLocked:
            return
        self.gateMachine.up()

    def gateLock(self):
        self.isLocked = True
        self.gateMachine.holdDown()

    def gateUnlock(self):
        self.isLocked = False
        self.gateMachine.releaseDown()

    def readAndHandleSMS(self):
        self.handleMessages(self.gsm.readSMS(), 'whitelist.txt', True)

    def handleMessages(self, msgs, whitelist, isPhone):
        for sender, msg in msgs:
            msg = msg.strip()
            sender_utf8 = sender.encode('utf8')
            got_access = False
            played = False
            command = OPEN_GATE_WORDS_LIST.get(msg, None)
            if command:
                logPrint("Got %s command" % command)
            if 'up' == command:
                if self.hasGateAccess(sender_utf8, whitelist, isPhone):
                    got_access = True
                    self.gateUp()
                else:
                    logPrint(colors.red("No access to %r" % sender_utf8))
            elif 'reboot' == command:
                reboot_system()
            elif 'lock' == command:
                if self.hasGateAccess(sender_utf8, whitelist, isPhone):
                    self.gateLock()
            elif 'unlock' == command:
                if self.hasGateAccess(sender_utf8, whitelist, isPhone):
                    self.gateUnlock()
            elif 'gatereset' == command:
                if self.hasGateAccess(sender_utf8, whitelist, isPhone):
                    self.gateMachine.resetGate()
            elif None != command:
                logPrint("Unknown command %s" % command)
            else:
                for fname in os.listdir('./mp3/'):
                    if not fname.endswith('.mp3'):
                        continue
                    if fname.startswith(msg) or msg.startswith(fname[:-4]):
                        playMusic('./mp3/%s' % fname)
                        played = True
                        break
            self.writeToOperationLog( \
                b'\tMsg:\t%s\t%s\t%r\t%r\n' % (sender_utf8, msg.encode('utf8', errors='ignore'), got_access, played))

    def resetIfNeeded(self):
        if self.gsm.pwrOnIfNeeded():
            self.readAndHandleSMS()

    def getCallingNumber(self):
        self.gsm.sendCmd(b'AT+CLCC')
        lines = self.gsm.normalizedRecv()
        for l in lines:
            if len(l) < 10:
                continue
            info = l[len('+CLCC: '):].split(b',')
            if 0 != int(info[3]):
                # Not a voice call
                continue
            number = info[5].replace(b'"', b'')
            if 4 < len(number):
                return number
            else:
                logPrint("Parsing error: %r" % l)
        return None

    def mainLoop(self):
        while True:
            time.sleep(0.05)
            lines = self.gsm.normalizedRecv()
            for l in lines:
                l = l.strip()
                if l.startswith(b'+CLIP:'):
                    self.answerCallClip(l)
                if l.startswith(b'RING'):
                    callingNumber = self.getCallingNumber()
                    if callingNumber:
                        self.answerCall(callingNumber)
                if l.startswith(b'+CMTI:'):
                    self.readAndHandleSMS()
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
            if self.telegramBot and (TELEGRAM_CHECK_INTERVAL < (time.time() - self.lastTelegramCheck)):
                self.lastTelegramCheck = time.time()
                self.handleMessages(self.telegramBot.getMessages(), 'telegram_whitelist.txt', False)
            if PING_INTERVAL < (time.time() - self.lastPing):
                logPrint("Pi temperature is %f" % get_pi_temperature())
                self.resetIfNeeded()
                if not validate_usb():
                    self.usbFailCount += 1
                    if MAX_USB_FAIL_COUNT < self.usbFailCount:
                        logPrint(colors.red("Too many USB failures, rebooting!"))
                        time.sleep(20)
                        reboot_system()
                else:
                    self.usbFailCount = 0
                self.lastPing = time.time()

            if self.rfCtl.should_open_the_gate():
                logPrint(colors.green("Gate up by RF remote control"))
                self.gateUp()

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
        time.sleep(0.1)
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
    for usb_id in MUST_EXISTS_USB:
        if usb_id not in stdout:
            logPrint(colors.red("USB failure!- %r is missing" % usb_id))
            return False
    return True

@baker.command
def reboot_system():
    logPrint(colors.red("Rebooting!!!"))
    runInBackground("reboot")

@baker.command
def run(verbose=False):
    me = singleton.SingleInstance()
    logPrint("My PID is %d" % os.getpid())
    playMusic('ping.mp3')
    logPrint(colors.blue("Starting!"))
    lastFail = 0
    failCount = 0
    keepRunning = True
    while keepRunning:
        try:
            with GateControl(verbose=verbose) as gateControl:
                keepRunning = gateControl.mainLoop()
        except:
            last_error = traceback.format_exc()
            logPrint(colors.bold(colors.red(last_error)))
            time.sleep(2)
            if 60 < (time.time() - lastFail):
                failCount = 1
            else:
                failCount += 1
            logPrint("System error %d" % failCount)
            lastFail = time.time()
            if MAX_FAILS_IN_A_ROW < failCount:
                reboot_system()

if __name__ == '__main__':
    colorama.init(strip=False)
    baker.run()

