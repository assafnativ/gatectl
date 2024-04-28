import os

import telepot
import traceback

from common import *
from urllib3.exceptions import ReadTimeoutError

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
            messages = self.bot.getUpdates(self.lastMsgId, timeout=1.1)
        except ReadTimeoutError as e:
            logPrint('Got timeout error, will try again later')
            time.sleep(20)
            return []
        except Exception as e:
            last_error = traceback.format_exc()
            logPrint('Got exception in getMessage: \n' + colors.bold(colors.red(last_error)))
            time.sleep(20)
            raise e
        result = []
        lastId = self.lastMsgId
        for msg in messages:
            lastId = max(lastId, int(msg['update_id'])+1)
            if 'message' not in msg:
                logPrint("Got telegram event that is not a message %r" % msg)
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

def read_telegram_messages():
    cfg = configLoad('config.py')
    telegramBot = TelegramBot(cfg['TELEGRAM_BOT_TOKEN'], cfg['TELEGRAM_LAST_MSG_FILE'])
    for sender, text in telegramBot.getMessages():
        logPrint("%s sent: %s" % (sender, text))

def TelegramBotRun(cfg, cmdQueue):
    assert validate_single_instance('telegrambot'), "Already running!"
    logPrint("Telegram Bot main loop")
    telegramBot = TelegramBot(cfg['TELEGRAM_BOT_TOKEN'], cfg['TELEGRAM_LAST_MSG_FILE'])
    while True:
        if os.path.isfile(cfg['KILL_FILE']):
            logPrint(colors.magenta("TelegramBot KTHXBYE"))
            return False
        try:
            messages = telegramBot.getMessages()
            for sender, text in messages:
                cmdQueue.put(('TelegramBot', sender, text))
            time.sleep(cfg['TELEGRAM_CHECK_INTERVAL'])
        except Exception as e:
            last_error = traceback.format_exc()
            logPrint(colors.bold(colors.red(last_error)))
            time.sleep(4)
            raise e

colorama.init(strip=False)

