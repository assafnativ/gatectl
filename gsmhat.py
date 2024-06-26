import binascii
import time
import traceback

import RPi.GPIO as GPIO
import serial

from common import *

class GSMHat(object):
    def __init__(self, cfg, cmdQueue):
        logPrint("Starting GSMHat")
        GPIO.setmode(GPIO.BOARD)
        self.cfg = cfg
        self.cmdQueue = cmdQueue
        self.initPwrPin()
        self.serial = serial.Serial(self.cfg['GSM_SERIAL_DEV'], 115200, timeout=1.5)
        self.pwrOnIfNeeded()
        self.deviceId = self.getDeviceId()
        self.lastPing = time.time()
        logPrint("Connected to GSM hat")
        self.recv()

    def initPwrPin(self):
        if not self.cfg['GSM_PWR_PIN']:
            return
        GPIO.setup(self.cfg['GSM_PWR_PIN'], GPIO.OUT)
        GPIO.output(self.cfg['GSM_PWR_PIN'], GPIO.HIGH)

    def getDeviceId(self):
        self.sendCmd(b"ATI")
        id_data = self.normalizedRecv()
        logPrint("ATI answer: %r" % id_data)
        if len(id_data) < 3:
            return None
        return id_data[2]

    def pwrOnIfNeeded(self):
        if self.pingDevice():
            return False
        # Try to power up the GSM Hat
        logPrint("Need to power up GSM hat")
        if None == self.cfg['GSM_PWR_PIN']:
            logPrint(colors.red("Power pin for GSM hat is not configured!"))
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
        if not self.cfg['GSM_PWR_PIN']:
            logPrint("No power pin")
            return
        GPIO.output(self.cfg['GSM_PWR_PIN'], GPIO.LOW)
        time.sleep(3)
        GPIO.output(self.cfg['GSM_PWR_PIN'], GPIO.HIGH)
        logPrint("GSM hat power on")
        time.sleep(10)

    def pingDevice(self):
        self.sendCmd(b"AT")
        recv = self.recv(quiet=True)
        if 10 < len(recv):
            logPrint("Got extra data: " + colors.red(recv.decode('utf8')))
        if b"OK" in recv[-10:]:
            return True
        logPrint(colors.bold(colors.yellow('Ping result in: %r' % recv)))
        return False

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
        logPrint(colors.blue(deleteResult.decode('utf8')))
        return messages

    def hangUpCall(self):
        self.sendCmd(b'AT+CHUP')

    def normalizedRecv(self):
        return [x.strip() for x in self.recv().replace(b'\r\n', b'\n').split(b'\n') if x.strip()]

    def recv(self, quiet=False):
        data = self.serial.read(1048576)
        clearData = data.decode('utf8', errors='ignore').strip()
        if clearData and not quiet:
            logPrint(colors.faint(colors.red(clearData)))
        return data

    def sendCmd(self, cmd):
        self.send(cmd + b'\r\n')

    def send(self, data):
        self.serial.write(data)
        self.serial.flush()

    def close(self):
        self.serial.close()
        GPIO.cleanup()

    def resetIfNeeded(self):
        if self.pwrOnIfNeeded():
            self.readAndHandleSMS()

    def getCallingNumber(self):
        self.sendCmd(b'AT+CLCC')
        lines = self.normalizedRecv()
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
        logPrint(colors.yellow("%r is calling" % callerId))
        self.cmdQueue.put(('GSM Call', callerId, None))
        # We do not answer calls, just using the caller id
        self.hangUpCall()

    def mainLoop(self):
        while not os.path.isfile(self.cfg['KILL_FILE']):
            lines = self.normalizedRecv()
            for l in lines:
                l = l.strip()
                if l.startswith(b'+CLIP:'):
                    self.answerCallClip(l)
                if l.startswith(b'RING'):
                    callingNumber = self.getCallingNumber()
                    if callingNumber:
                        self.answerCall(callingNumber)
                if l.startswith(b'+CMTI:'):
                    msgs = self.readSMS()
                    for sender, msg in msgs:
                        self.cmdQueue.put(('SMS', sender, msg))
                if b"POWER DOWN" in l:
                    time.sleep(4)
                    self.resetIfNeeded()
            if self.cfg['PING_INTERVAL'] < (time.time() - self.lastPing):
                self.lastPing = time.time()
                self.resetIfNeeded()

def GSMHatRun(cfg, cmdQueue):
    validate_single_instance('gsmhat')
    gsm = None
    try:
        gsm = GSMHat(cfg, cmdQueue)
        gsm.mainLoop()
    except:
        last_error = traceback.format_exc()
        logPrint(colors.bold(colors.red(last_error)))
        time.sleep(10)
    finally:
        if None != gsm:
            gsm.close()
            gsm = None


colorama.init(strip=False)


