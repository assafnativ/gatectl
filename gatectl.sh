#!/bin/bash

sleep 10
cd /home/pi/src
python gatectl.py run True >> ./stdlog.txt 2>&1 &
