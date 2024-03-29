from datetime import datetime

GSM_PWR_PIN = 7
#GSM_PWR_PIN = 31 # SIM7600X
GSM_SERIAL_DEV = "/dev/ttyUSB0"
#GSM_SERIAL_DEV = "/dev/ttyS0" # SIM7600X
GPIO_GATE_UP    = 36
GPIO_GATE_POWER = 38
GPIO_GATE_HOLD  = 40 # Not in use

TEMPERATURE_CHECK_INTERVAL = 300

MP3_PLAYER = 'mpg321'
current_datetime_str = datetime.now().strftime("%Y%m%d")
LOG_FILE_NAME = "logs/ctl_" + current_datetime_str + ".log"
OPERATION_LOG = "logs/operation_%s.log"
PING_INTERVAL = 60 * 2
MAX_FAILS_IN_A_ROW = 4
MAX_USB_FAIL_COUNT = 20

GATEUP_TRIGGER_FILE = 'GATEUP'
KILL_FILE = 'KILLAPP'

MUST_EXISTS_USB = [b'148f:7601', b'0403:6001']

MAX_LOG_FILE_SIZE = 1024 * 1024 * 100

TELEGRAM_BOT_TOKEN = ''
TELEGRAM_LAST_MSG_FILE = 'telegram_last_msg_id.txt'
TELEGRAM_CHECK_INTERVAL = 1

OPEN_GATE_WORDS_LIST = {
        'up' : 'up',
        'Up' : 'up',
        'open' : 'up',
        'Open' : 'up',
        'let me in' : 'up',
        'Let me in' : 'up',
        'seasame' : 'up',
        'Seasame' : 'up',
        'open seasame' : 'up',
        'Open seasame' : 'up',
        'quack' : 'up',
        'Quack' : 'up',
        'reboot' : 'reboot',
        'Reboot' : 'reboot',
        'restart' : 'reboot',
        'Restart' : 'reboot',
        'lock' : 'lock',
        'unlock' : 'unlock',
        'gate reset' : 'gatereset',
        'Gate reset' : 'gatereset'}

RF_GPIO = 17
RF_PROTO = 1
RF_PULSELENGTH = (330, 340)
RF_CODE = (2040, 2050)

