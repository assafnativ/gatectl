import time
import os
import sys
import subprocess
import multiprocessing as mp
import traceback

import baker
import re

from common import *
from gatectl import *
from gsmhat import *
from telegram_bot import *
from rfcontrol import *

os.chdir(os.path.dirname(os.path.abspath(__file__)))
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
cfg = configLoad('config.py', EXPECTED_CONFIGURATIONS)

def runInBackground(cmd):
    logPrint("Executing: " + colors.blue(cmd))
    _ = subprocess.Popen(
            cmd,
            shell=True,
            stdin=None, close_fds=True)

def playMusic(fname):
    # Clean current playing music
    kill_process_by_name(cfg['MP3_PLAYER'])
    cmd = "%s %s/%s &" % (cfg['MP3_PLAYER'], os.path.abspath('.'), fname)
    if 0 == os.geteuid():
        runInBackground('runuser -l pi -c "%s"' % cmd)
    else:
        runInBackground(cmd)

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
    for usb_id in cfg['MUST_EXISTS_USB']:
        if usb_id not in stdout:
            logPrint(colors.red("USB failure!- %r is missing" % usb_id))
            return False
    return True

@baker.command
def reboot_system():
    logPrint(colors.red("Rebooting!!!"))
    runInBackground("reboot")

@baker.command
def run():
    me = singleton.SingleInstance()
    logPrint("My PID is %d" % os.getpid())
    playMusic('ping.mp3')
    logPrint(colors.blue("Starting!"))
    lastFail = 0
    failCount = 0
    keepRunning = True
    while keepRunning:
        time.sleep(1)
        try:
            with GateControl(cfg) as gateControl:
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
            if cfg['MAX_FAILS_IN_A_ROW'] < failCount:
                reboot_system()

class GateControl(object):
    def __init__(self, cfg):
        logPrint("Starting GateControl")
        self.globalCtx = mp.get_context('spawn')
        self.cmdQueue = self.globalCtx.Queue()
        self.gateQueue = self.globalCtx.Queue()
        self.gateModules = [
                (MachineLoopRun, 'gateMachine', 'gateMachineProcess', (cfg, self.gateQueue,)),
                (TelegramBotRun, 'TelegramBot', 'telegramBotProcess', (cfg, self.cmdQueue,)),
                (GSMHatRun, 'GSM', 'GSMHatProcess', (cfg, self.cmdQueue,)),
                (RFCtlRun, 'RF', 'RFCtlProcess', (cfg, self.cmdQueue,))]
        self.modulesRestart = 0
        for _, _, var, _ in self.gateModules:
            setattr(self, var, None)
        self.lastPing = time.time()
        self.lastTempCheck = time.time()
        self.usbFailCount = 0
        self.isLocked = False

    def __enter__(self):
        return self

    def __exit__(self, t, value, tb):
        self.isLocked = False
        self.gateQueue.put(('close', ()))
        if tb or value or t:
            trace = traceback.format_exc()
            logPrint(colors.red(trace))
        return

    def writeToOperationLog(self, msg):
        operationLog = cfg['OPERATION_LOG'] % datetime.now().strftime("%Y%m%d")
        with open(operationLog, "ab") as log:
            log.write(time.ctime().encode('utf8') + b'\t' + msg)

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

    def gateUp(self, uptime=2):
        if self.isLocked:
            return
        self.gateQueue.put(('up', (uptime,)))

    def gateLock(self):
        self.isLocked = True

    def gateUnlock(self):
        self.isLocked = False

    def handleMessage(self, msg, whitelist, isPhone):
        sender, msg = msg
        msg = msg.strip()
        sender_utf8 = sender.encode('utf8')
        got_access = False
        played = False
        command = cfg['OPEN_GATE_WORDS_LIST'].get(msg, None)
        uptime = 2
        if msg.isnumeric():
            command = 'up'
            try:
                uptime = int(msg)
            except:
                pass
        uptime = min(uptime, 300)
        if command:
            logPrint("Got %s command" % command)
        if 'up' == command:
            if self.hasGateAccess(sender_utf8, whitelist, isPhone):
                got_access = True
                self.gateUp(uptime=uptime)
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
                self.gateQueue.put(('resetGate', ()))
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
            b'Msg:\t%s\t%s\t%r\n' % (sender_utf8, msg.encode('utf8', errors='ignore'), got_access))

    def handleCall(self, callerId):
        isAllowedIn = self.hasGateAccess(callerId, 'whitelist.txt', True)
        if isAllowedIn:
            self.gateUp()
        else:
            logPrint(colors.red("No access to %r" % callerId))
        self.writeToOperationLog(b'Call:\t' + callerId + b'\t%r\n' % isAllowedIn)

    def readMessagesFromFile(self, inFileName):
        lines = []
        with open(inFileName, 'r') as cmdFile:
            lines = cmdFile.readlines()
        os.unlink(inFileName)
        messages = []
        for line in lines:
            sender, data = line.split('|')
            data = binascii.unhexlify(data).decode('utf8')
            messages.append((sender, data))
        return messages

    def createSubProcessesSafe(self):
        for entryPoint, name, var, args in self.gateModules:
            process = getattr(self, var)
            if None == process or None != process.exitcode:
                self.modulesRestart += 1
                logPrint("Creating %s" % name)
                process = self.globalCtx.Process(target=entryPoint, args=args, name=name)
                setattr(self, var, process)
                process.start()

    def killProcesses(self):
        for _, _, var, _ in self.gateModules:
            process = getattr(self, var)
            if process and None == process.exitcode:
                process.terminate()
                setattr(self, var, None)

    def mainLoop(self):
        logPrint("--- MainLoop ---")
        while True:
            self.createSubProcessesSafe()
            if os.path.isfile(cfg['GATEUP_TRIGGER_FILE']):
                self.writeToOperationLog(b'LocalTrigger')
                os.unlink(cfg['GATEUP_TRIGGER_FILE'])
                self.gateUp()
            if os.path.isfile(cfg['KILL_FILE']):
                logPrint(colors.magenta("KTHXBYE"))
                time.sleep(2)
                self.killProcesses()
                os.unlink(cfg['KILL_FILE'])
                return False
            if not self.cmdQueue.empty():
                moduleName, sender, msg = self.cmdQueue.get()
                if 'RF' == moduleName:
                    self.writeToOperationLog('RF cmd')
                    gatectl.gateUp()
                elif 'TelegramBot' == moduleName:
                    self.handleMessage((sender, msg), 'telegram_whitelist.txt', True)
                elif 'GSM Call' == moduleName:
                    self.handleCall(sender)
                elif 'SMS' == moduleName:
                    self.handleMessage((sender, msg), 'whitelist.txt', True)

            if 60 < (time.time() - self.lastTempCheck):
                self.lastTempCheck = time.time()
                logPrint("Pi temperature is %f" % get_pi_temperature())
            if cfg['PING_INTERVAL'] < (time.time() - self.lastPing):
                if 100 < self.modulesRestart:
                    reboot_system()
                if not validate_usb():
                    self.usbFailCount += 1
                    if cfg['MAX_USB_FAIL_COUNT'] < self.usbFailCount:
                        logPrint(colors.red("Too many USB failures, rebooting!"))
                        time.sleep(20)
                        reboot_system()
                else:
                    self.usbFailCount = 0
                self.lastPing = time.time()
            time.sleep(0.01)

if __name__ == '__main__':
    colorama.init(strip=False)
    baker.run()

