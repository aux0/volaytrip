# -*- coding: utf-8 -*-

from functools import partial
from itertools import zip_longest
from volapi import Room
import math
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
        chunks = math.ceil(len(msg) / self.chunk_size)

        for chunk in grouper(self.chunk_size, msg, ''):
            # TODO: remove
            print('({}/{}): {}'.format(current_chunk,
                                       chunks, ''.join(chunk)))
            self.room.post_chat('({}/{}): {}'.format(current_chunk,
                                                     chunks, ''.join(chunk)))
            current_chunk += 1


class VideoUnavailable(RuntimeError):
    pass


def get_best_format(video_url, threshold, video=True, audio=True):
    with youtube_dl.YoutubeDL() as ydl:
        res = ydl.extract_info(video_url, download=False)

    if not 'formats' in res or len(res['formats']) == 0:
        raise VideoUnavailable('No formats found')

    def check_fields(f):
        return ('filesize' in f and
                ('vcodec' in f if video else True) and
                ('acodec' in f if audio else True))

    def check_threshold(f):
        return f['filesize'] <= threshold

    def check_audio_video(f):
        (video and f['vcodec'] != 'none')

        return ((f['vcodec'] != 'none' if video else True) and
                (f['acodec'] != 'none' if audio else True))

    def by_filesize(f):
        return f['filesize']

    # some formats have no filesize field
    formats = list(filter(check_fields, res['formats']))

    # print(list(map(check_threshold, formats)))
    formats = list(filter(check_threshold, formats))

    # remove those which have no video/audio
    formats = list(filter(check_audio_video, formats))

    if not formats:
        raise VideoUnavailable('No formats found')

    # get the one with the biggest size
    best_format = max(formats, key=by_filesize)

    return best_format


def upload_video(msg, room, threshold):
    try:
        tokens = msg.msg.split(' ')

        if len(tokens) < 2 or tokens[0] != ':rip':
            return

        video_url = tokens[1]

        log.debug('Got URL from \'{}\': {}'.format(msg.nick,
                                                   video_url))

        av = tokens[2] if len(tokens) == 3 else None

        video = 'v' in av if av else True
        audio = 'a' in av if av else True

        log.debug('Video: {}, Audio: {}'.format(
            'Y' if video else 'N', 'Y' if audio else 'N'))

        best_format = get_best_format(video_url, threshold, video, audio)
        filename = './video.{}'.format(best_format['ext'])

        print('Best format: {}'.format(best_format))
        log.debug('Saving to {}'.format(filename))

        with open(filename, 'wb') as f:
            r = requests.get(best_format['url'], stream=True)

            if not r.ok:
                raise VideoUnavailable('Request error: {}'.format(r.status_code))

            for chunk in r.iter_content(1024**2):
                f.write(chunk)

        log.debug('Video saved')

        video = room.upload_file(filename) # blocks until done
        time.sleep(0.5)
        room.post_chat('{}: @{}'.format(msg.nick, video))
        os.remove('./{}'.format(filename))
    except VideoUnavailable as e:
        log.debug('{}: Video unavailable: {}'.format(msg.nick, e.args[0]))
    except:
        log.debug(traceback.format_tb(sys.exc_info()[2]))
        log.debug(traceback.format_exc())


def test(video_url):
    with youtube_dl.YoutubeDL() as ydl:
        res = ydl.extract_info(video_url, download=False)

        # Full enumeration
        #
        # for i, f in enumerate(res['formats']):
        #     print(i)
        #     for k, v in f.items():
        #         print('\t{}: {}'.format(k, v))

        # Filesizes
        #
        for i, f in enumerate(res['formats']):
            if 'filesize' in f:
                print('{}: {} MB'.format(i, f['filesize'] / 1024**2))


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
                log.debug('Successful login')

            log.debug('Ripper started')

            room.add_listener('chat', partial(upload_video,
                                              room=room,
                                              threshold=args.threshold))
            room.listen()

            # TODO: remove
            #print('Ripper started')
    except:
        log.debug('Ripper died :^(')

        traceback.print_tb(sys.exc_info()[2])
        traceback.print_exc()


if __name__ == '__main__':
    main()
