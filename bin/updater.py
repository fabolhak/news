#!/usr/bin/env python
"""
Updater script for the news app which allows multiple feeds to be updated at
once to speed up the update process. Built in cron has to be disabled in the 
news config, see the README.rst file in the top directory for more information.
"""

__author__ = 'Bernhard Posselt'
__copyright__ = 'Copyright 2012-2014, Bernhard Posselt'
__license__ = 'AGPL3+'
__maintainer__ = 'Bernhard Posselt'
__email__ = 'dev@bernhard-posselt.com'

import sys
import time
import json
import argparse
import threading
import socket
import urllib.request
import urllib.error
from http.client import HTTPException

def get_basic_auth_opener(url, user, password):
    auth = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    auth.add_password(None, url, user, password)
    auth_handler = urllib.request.HTTPBasicAuthHandler(auth)
    return urllib.request.build_opener(auth_handler)


class UpdateThread(threading.Thread):

    lock = threading.Lock()

    def __init__(self, feeds, update_url, user, password, timeout):
        super().__init__()
        self.feeds = feeds
        self.update_url = update_url
        self.user = user
        self.password = password
        self.timeout = timeout

    def run(self):
        while True:
            with UpdateThread.lock:
                if len(self.feeds) > 0:
                    feed = self.feeds.pop()
                else:
                    return

            feed['feedId'] = feed['id']
            del feed['id']

            # call the update method of one feed
            data = urllib.parse.urlencode(feed)
            headers = {
                'Content-type': 'application/json',
                'Accept': 'text/plain'
            }
            url = '%s?%s' % (self.update_url, data)

            try:
                opener = get_basic_auth_opener(url, self.user, self.password)
                opener.open(url, timeout=self.timeout)
            except (urllib.error.HTTPError, urllib.error.URLError, HTTPException,
                socket.timeout) as e:
                print('%s: %s' % (url, e))



class Updater:

    def __init__(self, base_url, thread_num, interval, user, password, timeout, 
                 run_once):
        self.thread_num = thread_num
        self.interval = interval
        self.base_url = base_url
        self.user = user
        self.password = password
        self.timeout = timeout
        self.run_once = run_once

        if self.base_url[-1] != '/':
            self.base_url += '/'
        self.base_url += 'index.php/apps/news/api/v1-2'

        self.before_cleanup_url = '%s/cleanup/before-update' % self.base_url
        self.after_cleanup_url = '%s/cleanup/after-update' % self.base_url
        self.all_feeds_url = '%s/feeds/all' % self.base_url
        self.update_url = '%s/feeds/update' % self.base_url


    def run(self):
        while True:
            try:
                opener = get_basic_auth_opener(self.base_url, self.user,
                    self.password)
                # run the cleanup request and get all the feeds to update
                opener.open(self.before_cleanup_url)
                feeds_response = opener.open(self.all_feeds_url)
                feeds_json = feeds_response.read().decode('utf-8')
                feeds = json.loads(feeds_json)['feeds']

                # start thread_num threads which update the feeds
                threads = []
                for num in range(0, self.thread_num):
                    thread = UpdateThread(feeds, self.update_url, self.user,
                        self.password, self.timeout)
                    thread.start()
                    threads.append(thread)

                for thread in threads:
                    thread.join()

                opener.open(self.after_cleanup_url)

                if self.run_once:
                    return
                
                # wait until the interval finished to run again
                time.sleep(self.interval)

            except (ValueError, urllib.error.HTTPError, HTTPException,
                urllib.error.URLError) as e:
                print('%s: %s' % (self.base_url, e))
                print('Trying again in 30 seconds')
                time.sleep(30)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--testrun',
        help='Run update only once, DO NOT use this in a cron job, only \
              recommended for testing', action='store_true')
    parser.add_argument('--threads',
        help='How many feeds should be fetched in paralell, defaults to 10',
        default=10,
        type=int)
    parser.add_argument('--timeout',
        help='Maximum number of seconds for updating a feed, \
              defaults to 5 minutes',
        default=5*60,
        type=int)
    parser.add_argument('--interval',
        help='Update interval between fetching the next round of \
            updates in minutes, defaults to 30 minutes',
        default=30,
        type=int)
    parser.add_argument('--user',
        help='Admin username to log into ownCloud', required=True)
    parser.add_argument('--password',
        help='Admin password to log into ownCloud', required=True)
    parser.add_argument('url',
        help='The URL where owncloud is installed')
    args = parser.parse_args()

    # create the updater and run the threads
    updater = Updater(args.url, args.threads, args.interval, args.user,
        args.password, args.timeout, args.testrun)
    updater.run()


if __name__ == '__main__':
    if sys.version_info < (3, 0):
        print('Python 3.0 or higher is required to run this script')
    else:
        main()


