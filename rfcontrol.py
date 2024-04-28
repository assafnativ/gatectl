from rpi_rf import RFDevice
import RPi.GPIO as GPIO
import traceback

from common import *

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
        GPIO.setmode(GPIO.BOARD)
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
        #logPrint("Got RF signal: code %d pulselength %d" % (code, pulselength))
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

def rf_test(gpio):
    gpio = int(gpio)
    rfCtl = RFControl(gpio, None, [(0, 1000)], [(0, 10000)])
    logPrint("Starting loop")
    while True:
        rfCtl.should_open_the_gate()
        time.sleep(0.1)

def RFCtlRun(cfg, cmdQueue):
    validate_single_instance('rfctl')
    rfCtl = RFControl(cfg['RF_GPIO'], cfg['RF_PROTO'], cfg['RF_CODE'], cfg['RF_PULSELENGTH'])
    while True:
        if os.path.isfile(cfg['KILL_FILE']):
            rfCtl.cleanup()
            logPrint(colors.magenta("rfCtl KTHXBYE"))
            return False
        while True:
            try:
                if rfCtl.should_open_the_gate():
                    cmdQueue.put(('RF', None, None))
                time.sleep(0.01)
            except:
                last_error = traceback.format_exc()
                logPrint(colors.bold(colors.red(last_error)))
                time.sleep(10)

colorama.init(strip=False)

