#!/bin/bash

sleep 10
cd /home/pi/src
python main.py run >> ./stdlog.txt 2>&1 &
