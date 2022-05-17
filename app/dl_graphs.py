#!/usr/bin/env python3
from __future__ import print_function

import os
import sys
import time
import shutil
import requests
from bs4 import BeautifulSoup
from datetime import datetime as dt
from datetime import timedelta
import matplotlib.dates as mdates
from matplotlib import pyplot as plt

import gageman
import util


SLEEP = 5  # seconds between pulling gages


class URLError(Exception):
    pass


class FailedImageAddr(Exception):
    pass


def get_dwr_graph(gage, outpath, verbose=False):
    """
    Grabs default flow graph for Colorado DWR Gage 'gage'

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    response = requests.get(gage.data_url())
    if response.status_code != 200:
       raise URLError(response.status_code, response.text)

    last_result = response.json()['ResultList'][-1]
    if last_result['measUnit'] != 'cfs':
        raise ValueError('Wrong unit type in last result: ' + str(last_result))

    q = last_result['measValue']
    timestamp = last_result['measDateTime']
    date = timestamp.split('T')[0]
    time = timestamp.split('T')[1]

    outfile = os.path.join(outpath, gage.data_file())
    with open(outfile, 'wt') as out:
        data = '{},{},{}'.format(q, date, time)
        if verbose:
            print(f'\tWriting {data} to {outfile}')
        out.write(data+'\n')

    # --- Plot and save the hydrograph
    date_f = '%Y-%m-%dT%H:%M:%S'
    raw_qs = [r['measValue'] for r in response.json()['ResultList']]
    raw_tss = [dt.strptime(r['measDateTime'], date_f) for r in
                  response.json()['ResultList']]

    # only show last 7 days
    qs = []
    tss = []
    delta = timedelta(days=7)
    for q, ts in zip(raw_qs, raw_tss):
        if raw_tss[-1] - ts > delta:
            continue
        qs.append(q)
        tss.append(ts)

    i_outfile = os.path.join(outpath, gage.image_file())

    fmt = mdates.DateFormatter('%b\n%d') # May\n5
    #fig, ax = plt.subplots(1, figsize=(6.4, 4.1), dpi=100)
    fig, ax = plt.subplots(1, figsize=(5.76, 3.84), dpi=100)
    ax.plot(tss, qs)
    ax.set_ylim(ymin=0)
    ax.xaxis.set_major_formatter(fmt)
    plt.grid(visible=True)
    plt.savefig(i_outfile)
    plt.close()


def get_usgs_gage(gage, outpath):
    """
    Grabs default flow graph for USGS Gage 'gage' and write image to outfile.

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    response = requests.get(gage.data_url())

    # Verify we got good stuff back
    if response.status_code != 200:
        raise URLError(response.status_code, response.text)

    soup = BeautifulSoup(response.text, 'html.parser')

    # Get the discharge
    for tag in soup.find_all('a'):
        if tag.get('name') == "gifno-99":
            if tag.getText().strip() == 'Discharge, cubic feet per second':
                parent = tag.parent

                # Grab the graph and save it
                img = parent.parent.find_next('img')
                if img.get('alt') == "Graph of ":
                    img_addr = img.get('src')
                else:
                    raise FailedImageAddr('image address not found for '+gage.gage_id)
                response = requests.get(img_addr, stream=True, cookies=response.cookies)

                outfile = os.path.join(outpath, gage.image_file())
                with open(outfile, 'wb') as out:
                    shutil.copyfileobj(response.raw, out)

                # Grab the discharge and save it to a .cfs file
                _next = parent.next_sibling
                q = pull_val(_next)
                q_outfile = os.path.join(outpath, gage.data_file())
                #print (q_out)
                with open(q_outfile, 'wt') as out:
                    for val in q:
                        out.write(str(val) + ',')
            #if tag.getText().strip() == 'Gage height, feet':
                #parent = tag.parent
                #_next = parent.next_sibling
                #stage =  pull_val(_next)


def pull_val(text):
    fields = text.split()
    for i in range(len(fields)):
        if fields[i] == 'value:':
            try:
                return (fields[i+1], fields[i+2], fields[i+3])
            except IndexError as e:
                return ('N/A', 'Gauge appears to be offline', '')


def main():
    gages = gageman.get_gages()
    verbose = False
    if len(sys.argv) > 1:
        verbose = True
        if sys.argv[1].lower() == 'dwr':
            gages = [g for g in gages if g.gage_type == 'DWR']
        elif sys.argv[1].lower() == 'usgs':
            gages = [g for g in gages if g.gage_type == 'USGS']
        elif sys.argv[1].lower() == 'reverse':
            gages = gages[::-1]

    outpath = util.static_dir()

    for gage in gages:
        if verbose:
            print ('*** working on {} gage: {}'.format(gage.gage_type, gage))

        if gage.gage_type == 'USGS':
            try:
                get_usgs_gage(gage, outpath)
            except FailedImageAddr:
                try:
                    if verbose:
                        print ('\tno image address, trying again...')
                    time.sleep(SLEEP)
                    get_usgs_gage(gage, outpath)
                except FailedImageAddr:
                    if verbose:
                        print ('\tfailed to download gage, skipping')
                    continue
            if verbose:
                print ('\tsuccess')

        elif gage.gage_type == 'DWR':
            get_dwr_graph(gage, outpath, verbose=verbose)
            if verbose:
                print ('\tsuccess')

        else:
            raise AttributeError('gage was returned from get_gages() that is not USGS or DWR')
        time.sleep(SLEEP)


if __name__ == '__main__':
    main()
