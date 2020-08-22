import glob
import baker
import datetime
import time
import colorama
import colors


def to_bool(x):
    return x.strip().lower() == 'true'

def parse_single_file(fname):
    result = []
    with open(fname, 'r', encoding='utf8') as data:
        for l in data.readlines():
            if len(l) < 3:
                continue
            entry = {}
            items = l.split('\t')
            timestamp = items[0]
            entry['datetime'] = datetime.datetime.fromtimestamp(time.mktime(time.strptime(timestamp)))
            entry['action'] = items[1]
            entry['sender'] = items[2]
            if 4 < len(items):
                entry['msg'] = items[3]
                entry['gate_access'] = to_bool(items[4])
                entry['play_music'] = to_bool(items[5])
            else:
                entry['gate_access'] = to_bool(items[3])
            result.append(entry)
    return result

@baker.command
def parse(log_files):
    data = []
    for fname in glob.glob(log_files):
        data.extend(parse_single_file(fname))
    return data

def normalize_sender_name(x, phonebook):
    if x.startswith('+972'):
        x = '0' + x[4:]
    if phonebook:
        return phonebook.get(x, x)
    return x

@baker.command
def csv(log_files, output_file, phonebook=None):
    data = parse(log_files)
    if phonebook:
        with open(phonebook, 'r') as phonebook_file:
            phonebook_data = phonebook_file.readlines()
            phonebook_data = [x.split(':') for x in phonebook_data]
            phonebook = {x[0].strip():x[1].strip() for x in phonebook_data}

    with open(output_file, 'w') as writter:
        lasttime = datetime.datetime.fromtimestamp(0)
        for item in [x for x in data if x['gate_access']]:
            date = item['datetime']
            delta = lasttime - date
            delta = abs(delta.seconds + (delta.days * 24 * 60 * 60))
            lasttime = date
            if delta < 180:
                continue
            sender = normalize_sender_name(item['sender'], phonebook)
            writter.write('%s,%s\n' % (date.strftime('%Y/%m/%d,%H:%M'), sender))

if __name__ == '__main__':
    colorama.init(strip=False)
    baker.run()
