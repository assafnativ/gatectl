#!/usr/bin/python

import time
import traceback

import colors
from datetime import datetime
from tendo import singleton
import RPi.GPIO as GPIO

from common import *

cfg = configLoad('config.py')
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
        logPrint(colors.green("Gate up!"))
        self.triggerPin(self.up_gpio, False, uptime=uptime)

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

