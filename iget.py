#!/usr/bin/env python

""" iget, a simple tool to download the first ~n images (at a specified size)
    from google-images with a given query string.
"""
import concurrent.futures
import datetime
import glob
import imghdr
import logging
import logging.config
import optparse
import os
import re
import shutil
import sys
import time
from urllib.parse import quote, unquote, urlparse, urlunparse

import requests
from selenium import webdriver
from selenium.webdriver import DesiredCapabilities


ROOT = os.path.dirname(os.path.abspath(__file__))

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'summary',
            'stream': 'ext://sys.stdout',
        },
        'null': {
            'class': 'logging.NullHandler',
            'level': 'NOTSET',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': 'summary',
            'filename': 'iget.log',  # os.path.join(ROOT, 'iget.log'),
            'mode': 'a',
            'maxBytes': 10485760,
            'backupCount': 5,
        },
    },
    'formatters': {
        'summary': {
            'format': '%(asctime)s [%(levelname)-8s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'loggers': {
        '': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        }
    }
}

# Appear like a normal browser.
HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Proxy-Connection': 'keep-alive',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2840.99 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate, sdch',
    'Referer': 'https://images.google.com/',
}

# We are only interested in these formats.
FORMAT_EXT = {
    'jpg': '.jpg',
    'jpeg': '.jpg',
    'png': '.png',
    'svg': '.svg',
    'webp': '.webp',
    'bmp': '.bmp',
    'ico': '.ico',
}

SIZES = {
    '': '',
    'large': 'isz:l',
    'medium': 'isz:m',
    'icon': 'isz:i',
    '>400x300': 'isz:lt,islt:qsvga',
    '>640x480': 'isz:lt,islt:vga',
    '>800x600': 'isz:lt,islt:svga',
    '>1024x768': 'visz:lt,islt:xga',
    '>2mp': 'isz:lt,islt:2mp',
    '>4mp': 'isz:lt,islt:4mp',
    '>6mp': 'isz:lt,islt:6mp',
    '>8mp': 'isz:lt,islt:8mp',
    '>10mp': 'isz:lt,islt:10mp',
    '>12mp': 'isz:lt,islt:12mp',
    '>15mp': 'isz:lt,islt:15mp',
    '>20mp': 'isz:lt,islt:20mp',
    '>40mp': 'isz:lt,islt:40mp',
    '>70mp': 'isz:lt,islt:70mp',
}

TYPES = {
    '': '',
    'face': 'itp:face',
    'photo': 'itp:photo',
    'clipart': 'itp:clipart',
    'line-drawing': 'itp:lineart',
    'animated': 'itp:animated',
}

FILE_TYPES = {
    '': '',
    'gif': 'ift:gif',
    'bmp': 'ift:bmp',
    'ico': 'ift:ico',
    'jpg': 'ift:jpg',
    'png': 'ift:png',
    'webp': 'ift:webp',
    'svg': 'ift:svg',
}

RIGHTS = {
    '': '',
    'cc': 'sur:cl',
    'other': 'sur:ol',
}


def ensure_directory_exists(path, expand_user=True, file=False):
    """ Create a directory if it doesn't exists.

        Expanding '~' to the user's home directory on POSIX systems.
    """
    if expand_user:
        path = os.path.expanduser(path)

    if file:
        directory = os.path.dirname(path)
    else:
        directory = path

    if not os.path.exists(directory) and directory:
        try:
            os.makedirs(directory)
        except OSError as e:
            # A parallel process created the directory after the existence check.
            pass

    return path


def download(url, dst, prefix, logger, timeout=20, proxies=None):
    """ Download an URL, keep the image if its format is in FORMAT_EXT.
    """
    response = None
    path = os.path.join(dst, prefix)
    tries = 0
    while True:
        try:
            tries += 1
            response = requests.get(url, headers=HEADERS, timeout=timeout, proxies=proxies)
            with open(path, 'wb') as f:
                f.write(response.content)
            response.close()
            ext = FORMAT_EXT.get(imghdr.what(path).lower())
            logger.info('Identified file-extension: {}: {}'.format(imghdr.what(path), ext))
            if ext:
                shutil.move(path, path + ext)
                logger.info('Success: {url} -> {filename}'.format(url=url, filename=prefix + ext))
            else:
                os.remove(path)
                logger.error('Unsupported file format: {url}'.format(url=url))
            break
        except Exception as e:
            if tries < 3:
                continue
            if response:
                response.close()
            logger.error('Maximum download attemps: {url}'.format(url=url))
            break


def download_many(urls, dst, offset, prefix, logger, workers=50, timeout=20, proxies=None):
    """ Download multiple image urls.
    """
    ensure_directory_exists(dst)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for idx, url in enumerate(urls, offset):
            futures.append(executor.submit(
                download, url, dst, '{}_{:04d}'.format(prefix, idx), logger, timeout, proxies))
        concurrent.futures.wait(futures, timeout=180)


def google_url(query, size=None, type_=None, file_type=None, site=None, safe=None, rights=None):
    """ Build a Google search URL.

        Only support a subset of advanced search options.
    """
    cv = lambda x: ('', ',')[bool(x)] + x

    url = 'https://www.google.com/search?tbm=isch&hl=en'
    url += '&q=' + quote(query)

    tbs = ''
    tbs += SIZES.get(size, '')
    tbs += cv(TYPES.get(type_, ''))
    tbs += cv(FILE_TYPES.get(file_type, ''))
    tbs += cv(RIGHTS.get(rights, ''))

    url += '&tbs=' + tbs.lstrip(',')

    if site:
        url += '&as_sitesearch={}'.format(site)

    if safe:
        url += '&safe=active'

    return url


def google_extract_urls(driver, n, logger):
    """ Scroll down webpage, click thumbnails, extract image URLs.
    """
    thumbs = []
    thumbs_prev = []
    while True:
        try:
            thumbs = driver.find_elements_by_class_name("rg_i")
            logger.info('Found {} images.'.format(len(thumbs)))
            if len(thumbs) >= n:
                break
            if len(thumbs) == len(thumbs_prev):
                break
            thumbs_prev = thumbs
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            time.sleep(2)
            show_more = driver.find_elements_by_class_name('mye4qd')
            if len(show_more) == 1 and show_more[0].is_displayed() and show_more[0].is_enabled():
                logger.info('Click show_more button.')
                show_more[0].click()
            time.sleep(3)
        except Exception as e:
            logger.exception('Error')

    if not thumbs:
        return []

    retry = []
    for idx, elem in enumerate(thumbs):
        try:
            if not elem.is_displayed() or not elem.is_enabled():
                retry.append(elem)
                continue
            elem.click()
        except Exception as e:
            retry.append(elem)

    if retry:
        for elem in retry:
            try:
                if elem.is_displayed() and elem.is_enabled():
                    elem.click()
            except Exception as e:
                logger.exception('Error')

    images = driver.find_elements_by_class_name("islib")
    urls = []
    pattern = r'imgurl=\S*&amp;imgrefurl'

    for image in images[:n]:
        outer_html = image.get_attribute('outerHTML')
        re_group = re.search(pattern, outer_html)
        if re_group is not None:
            url = unquote(re_group.group()[7:-14])
            urls.append(url)
    return urls


if __name__ == '__main__':

    now = datetime.datetime.now()

    parser = optparse.OptionParser()

    parser.add_option('-q',
                      '--query',
                      dest='query',
                      action='store',
                      type='string',
                      default='',
                      help='search query')

    parser.add_option('-n',
                      '',
                      dest='n',
                      action='store',
                      type='int',
                      default=10,
                      help='number of images to download [%default]')

    parser.add_option('-p',
                      '--prefix',
                      dest='prefix',
                      action='store',
                      type='string',
                      default='img',
                      help='filename prefix [%default]')

    parser.add_option('-d',
                      '--dst',
                      dest='dst',
                      action='store',
                      type='string',
                      default='.',
                      help='destination folder [%default]')

    parser.add_option('-f',
                      '--file-type',
                      dest='file_type',
                      action='store',
                      type='choice',
                      choices=list(FILE_TYPES),
                      default='',
                      help='image file-type')

    parser.add_option('-s',
                      '--size',
                      dest='size',
                      action='store',
                      type='choice',
                      choices=list(SIZES),
                      default='',
                      help='image size')

    parser.add_option('-t',
                      '--type',
                      dest='type',
                      action='store',
                      type='choice',
                      choices=list(TYPES),
                      default='',
                      help='image type')

    parser.add_option('-x',
                      '--safe',
                      dest='safe',
                      action='store_true',
                      default=False,
                      help='safe content')

    parser.add_option('-i',
                      '--site',
                      dest='site',
                      action='store',
                      type='string',
                      default='',
                      help='site or domain to search')

    parser.add_option('-r',
                      '--rights',
                      dest='rights',
                      action='store',
                      type='choice',
                      choices=list(RIGHTS),
                      default='',
                      help='image usage rights')

    parser.add_option('',
                      '--proxy',
                      dest='proxy',
                      action='store',
                      type='string',
                      default='',
                      help='proxy string in the form: https://username:password@host:port/')

    parser.add_option('-v',
                      '--verbose',
                      dest='verbose',
                      action='store_true',
                      default=False,
                      help='verbose output')

    options, args = parser.parse_args()

    if not (options.query):
        parser.print_help()
        sys.exit()

    if options.proxy:
        scheme, netloc, path, params, query, fragment = urlparse(options.proxy)
        proxies = {
            'http': urlunparse(('http', netloc, path, params, query, fragment)),
            'https': urlunparse(('https', netloc, path, params, query, fragment)),
        }
    else:
        proxies = None

    # Dereference.
    query = options.query
    n = options.n
    prefix = options.prefix
    dst = options.dst
    file_type = options.file_type
    size = options.size
    type_ = options.type
    safe = options.safe
    site = options.site
    rights = options.rights
    verbose = options.verbose

    if verbose:
        LOGGING_CONFIG['loggers']['']['handlers'] = ['console', 'file']

    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger()
    logger.info('Application Start: {cmd}'.format(cmd=' '.join(sys.argv)))

    url = google_url(query, size=size, type_=type_, file_type=file_type, site=site, safe=safe, rights=rights)


    try:
        chrome_path = shutil.which('chromedriver')
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('headless')
        # What about http proxies?
        if proxies:
            chrome_options.add_argument('--proxy-server={url}'.format(url=proxies['https']))
        driver = webdriver.Chrome(chrome_path, options=chrome_options)
        driver.set_window_size(1920, 1080)
        driver.get(url)
        logger.info('Google: {url}'.format(url=url))
        urls = google_extract_urls(driver, options.n, logger)

        ensure_directory_exists(dst)
        filenames = sorted([filename for filename in os.listdir(dst) if filename.startswith(prefix)])
        if filenames:
            offset = int(os.path.splitext(filenames[-1])[0][len(prefix)+1:]) + 1
        else:
            offset = 1

        download_many(urls, dst, offset, prefix, logger, proxies=proxies)

    finally:
        driver.close()

