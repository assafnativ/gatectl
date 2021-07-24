import os
import subprocess
import time

import colors
import colorama
from past.builtins import execfile

class myDict(dict):
    def __getattr__(self, item):
        return self[item]

def configLoad(cfgFileName, expectedConfigs=None):
    cfg = myDict()
    execfile(cfgFileName, cfg)
    if expectedConfigs:
        for config_name in expectedConfigs:
            assert config_name in cfg, "%s configuration is missing in config file" % config_name
    return cfg

cfg = configLoad('config.py')
log_file = None
def logPrint(text):
    global log_file
    if not log_file:
        log_file = safeOpenAppend(cfg.LOG_FILE_NAME % os.getpid())
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
    if cfg.MAX_LOG_FILE_SIZE < targetFileSize:
        os.unlink(fileName)
    return open(fileName, 'a')

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

