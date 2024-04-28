#!/usr/bin/python

import time
import os
import traceback
import multiprocessing as mp

import colors
from datetime import datetime
import RPi.GPIO as GPIO

from common import *

class GateMachine(object):
    def __init__(self, up_gpio, power_gpio):
        logPrint("Starting GateMachine")
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(up_gpio, GPIO.IN)
        GPIO.setup(power_gpio, GPIO.IN)
        self.up_gpio = up_gpio
        self.power_gpio = power_gpio

    def close(self):
        GPIO.cleanup()

    def triggerPin(self, pin_number, active_low=False, uptime=2):
        self.activatePin(pin_number, active_low)
        time.sleep(uptime)
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

    def up(self, uptime=2):
        logPrint(colors.green("Gate up! for %f sec" % float(uptime)))
        self.triggerPin(self.up_gpio, False, uptime=uptime)

    def resetGate(self, active_low=False):
        logPrint(colors.yellow("Reset gate control"))
        self.activatePin(self.power_gpio, active_low=active_low)
        logPrint("Gate power on")
        time.sleep(4)
        self.deactivatePin(self.power_gpio, active_low=active_low)
        logPrint("Gate power off")

def up(uptime=2):
    cfg = configLoad('config.py')
    uptime = float(uptime)
    gm = GateMachine(cfg['GPIO_GATE_UP'], cfg['GPIO_GATE_POWER'])
    gm.up(uptime)

def MachineLoopRun(cfg, cmdQueue):
    validate_single_instance('machine')
    logPrint("Gate machine started")
    gm = GateMachine(cfg['GPIO_GATE_UP'], cfg['GPIO_GATE_POWER'])
    while True:
        try:
            if cmdQueue.empty():
                time.sleep(0.02)
                continue
            cmd, args = cmdQueue.get()
            logPrint("Gate handle: %s %r" % (cmd, args))
            getattr(gm, cmd)(*args)
            if 'close' == cmd:
                return
        except:
            last_error = traceback.format_exc()
            logPrint(colors.bold(colors.red(last_error)))

colorama.init(strip=False)

