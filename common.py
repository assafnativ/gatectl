import os
import subprocess
import time
import multiprocessing as mp
import multiprocessing_logging
import logging
import fcntl

import colors
import colorama
from past.builtins import execfile

def configLoad(cfgFileName, expectedConfigs=None):
    cfg = {}
    execfile(cfgFileName, cfg)
    if expectedConfigs:
        for config_name in expectedConfigs:
            assert config_name in cfg, "%s configuration is missing in config file" % config_name
    return cfg

logger = None
cfg = configLoad('config.py')
def getLogger():
    global logger
    if logger:
        return logger
    logger = mp.get_logger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s| %(levelname)s| %(processName)s] %(message)s')
    handler = logging.FileHandler(cfg['LOG_FILE_NAME'])
    handler.setFormatter(formatter)
    if not len(logger.handlers):
        logger.addHandler(handler)
    multiprocessing_logging.install_mp_handler()
    return logger

LOCK_FILE_HANDLE = None
def validate_single_instance(name):
    global LOCK_FILE_HANDLE
    if LOCK_FILE_HANDLE:
        print(f"File already locked")
        return False
    lock_file_path = cfg['LOCK_FILE'] + '_' + name
    LOCK_FILE_HANDLE = os.open(lock_file_path, os.O_WRONLY | os.O_CREAT)
    try:
        print(f"Locking {lock_file_path}")
        fcntl.lockf(LOCK_FILE_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except IOError:
        print(f"File is already locked {lock_file_path}")
        return False
    except PermissionError:
        print(f"File {lock_file_path} is opened by someone stronger")
        return False
    print("WTF! 12483749")
    return False

def logPrint(text):
    getLogger().info(text)

def safeOpenAppend(fileName):
    dirName = os.path.dirname(fileName)
    if dirName:
        os.makedirs(dirName, exist_ok=True)
    targetFileSize = 0
    try:
        targetFileSize = os.path.getsize(fileName)
    except OSError:
        targetFileSize = 0
    if cfg['MAX_LOG_FILE_SIZE'] < targetFileSize:
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

