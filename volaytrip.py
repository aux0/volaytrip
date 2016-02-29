# -*- coding: utf-8 -*-

from functools import partial
from itertools import zip_longest
from volapi import Room
import youtube_dl
import requests
import time
import sys
import os
import traceback
import logging
import argparse


log = logging.getLogger()
log.setLevel(logging.DEBUG)

log_handler_vola = None
log_handler_local = logging.StreamHandler(stream=sys.stdout)
# log_handler_local = logging.FileHandler('volaytrip.log', mode='w')

log_fmt = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)s] '
            '[%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%H:%M:%S')

requests_log = logging.getLogger('requests')
requests_log.propagate = False

log_handler_local.setFormatter(log_fmt)
log.addHandler(log_handler_local)


def grouper(n, iterable, padvalue=None):
    return zip_longest(*[iter(iterable)] * n, fillvalue=padvalue)


class VolaHandler(logging.Handler):
    def __init__(self, room, chunk_size=100):
        super().__init__()

        self.room = room
        self.chunk_size = chunk_size

    def emit(self, record):
        msg = self.format(record)
        current_chunk = 1
        chunks = len(msg) // self.chunk_size

        if chunks * self.chunk_size < len(msg):
            chunks += 1

        for chunk in grouper(self.chunk_size, record.msg, ''):
            # TODO: remove
            print('({}/{}): {}'.format(current_chunk,
                                       chunks, ''.join(chunk)))
            self.room.post_chat('({}/{}): {}'.format(current_chunk,
                                                     chunks, ''.join(chunk)))
            current_chunk += 1


def upload_video(msg, room, threshold):
    try:
        tokens = msg.msg.split(' ')

        if not (tokens[0] == ':rip' and len(tokens) == 2):
            return

        video_url = tokens[1]

        log.debug('Got URL from \'{}\': {}'.format(msg.nick,
                                                   video_url))
        # TODO: remove
        print('got url: {}'.format(video_url))

        with youtube_dl.YoutubeDL() as ydl:
            res = ydl.extract_info(video_url, download=False)

        if not 'formats' in res or len(res['formats']) == 0:
            raise RuntimeError('Video unavailable.')

        formats = filter(lambda f: 'filesize' in f, res['formats'])
        formats = filter(lambda f: f['filesize'] <= threshold, formats)
        best_format = max(formats, key=lambda f: f.filesize)

        filename = 'video.{}'.format(best_format['ext'])

        with open(filename) as f:
            r = requests.get(best_format['url'], stream=True)

            if not r.ok:
                raise RuntimeError('Request error')

            for chunk in r.iter_content(1024):
                f.write(chunk)

        video = room.upload_file(filename) # does this shit block?
        time.sleep(0.5)
        room.post_chat('{}: @{}'.format(msg.nick, video))
        os.remove('./{}'.format(filename))
    except:
        msg = '{}: Video unavailable.'.format(msg.nick)

        log.debug(msg)
        # TODO: remove
        #room.post_chat(msg)

        tb = sys.exc_info()[2]

        log.debug(traceback.format_tb(tb))
        # TODO: remove
        print(traceback.format_tb(tb))


def testing(video_url):
    with youtube_dl.YoutubeDL() as ydl:
        res = ydl.extract_info(video_url, download=False)

        # print(res['formats'])

        # for k, v in res:
        #     print('{}: {}'.format(k, None))

        for i, f in enumerate(res['formats']):
            print(i)
            for k, v in f.items():
                print('\t{}: {}'.format(k, v))


def main():
    parser = argparse.ArgumentParser(prog='volaytripper')

    parser.add_argument('room_name')
    parser.add_argument('username')
    parser.add_argument('-p', '--password')
    parser.add_argument('-t', '--threshold', type=int, default=10*1024**2)
    parser.add_argument('--test')

    args = parser.parse_args()

    log.debug('Got arguments: {}'.format(sys.argv[1:]))
    log.debug('Parsed arguments: {}'.format(args))

    if args.test:
        test(args.test)
        return

    try:
        with Room(args.room_name, args.username) as room:
            log_handler_vola = VolaHandler(room)
            log_handler_vola.setFormatter(log_fmt)
            log.addHandler(log_handler_vola)

            if args.password:
                room.user.login(password)
                log.debug('Successful login.')

            log.debug('Ripper started')

            room.add_listener('chat', partial(upload_video,
                                              room=room,
                                              threshold=args.threshold))
            room.listen()

            # TODO: remove
            #print('Ripper started')
    except:
        log.debug('Died before I even got a chance. :^(')

        traceback.print_tb(sys.exc_info()[2])


if __name__ == '__main__':
    main()
