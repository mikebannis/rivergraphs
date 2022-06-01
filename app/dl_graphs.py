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
    make_graph(raw_qs, raw_tss, outpath, gage)


def make_graph(raw_qs, raw_tss, outpath, gage):
    """
    Make a hyrograph and save it

    @param {list of float} raw_qs - list of discharges or stages
    @param {list of Datetime} raw_tss - time stamps for readings
    @param {str} outpath - the static dir
    @param {gageman.Gage} gage - the gage the graph is for
    """
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

    fmt = mdates.DateFormatter('%b\n%d')  # May\n5
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


def pull_val(text):
    """ Pull gage values for USGS """
    fields = text.split()
    for i in range(len(fields)):
        if fields[i] == 'value:':
            try:
                return (fields[i+1], fields[i+2], fields[i+3])
            except IndexError:
                return ('N/A', 'Gauge appears to be offline', '')


def get_prr_gage(gage, outpath, verbose=False):
    """
    Grabs default flow graph for the Poudre rock report and write image to
    outfile.

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    response = requests.get(gage.data_url())

    # Verify we got good stuff back
    if response.status_code != 200:
        raise URLError(response.status_code, response.text)

    soup = BeautifulSoup(response.text, 'html.parser')

    try:
        # Get the stage and time from header text, e.g. 'Pine View 3.4 at 0700'
        header = soup.find(class_='entry-header')
        stage = header.find('a').getText().split(' ')[2]
        time = header.find('a').getText().split(' ')[4]
        # Get date, e.g. 'May 31, 2022 By Camp Falbo '
        meta = header.find('p').getText().split(',')
    except Exception as e:
        print(f'Error pulling PRR: {e}')
        return

    mmm_dd = meta[0]
    year = meta[1].strip().split(' ')[0]
    ts = dt.strptime(f'{mmm_dd} {year} {time}', '%b %d %Y %H%M')
    data = '{},{},{}'.format(stage, ts.date(), ts.time())

    # grab last line of data file
    datafile = os.path.join(outpath, gage.data_file())
    with open(datafile, 'rt') as f:
        for old_data in f:
            pass

    # If it's the same data point, don't do anything else
    if old_data.strip() == data.strip():
        return

    if verbose:
        print(f'\tWriting {data} to {datafile}')
    with open(datafile, 'at') as out:
        out.write(data+'\n')

    raw_stages = []
    raw_tss = []
    with open(datafile, 'rt') as f:
        for line in f:
            fields = line.strip().split(',')
            raw_stages.append(fields[0])
            ts = dt.strptime(f'{fields[1]} {fields[2]}', '%Y-%m-%d %H:%M:%S')
            raw_tss.append(ts)

    make_graph(raw_stages, raw_tss, outpath, gage)
#2.8,2022-05-25,07:00:00
#3.2,2022-05-27,07:00:00
#3.1,2022-05-28,07:00:00
#3.8,2022-05-30,07:00:00
#3.4,2022-05-31,07:00:00
#3.4,2022-05-31,07:00:00


def main():
    gages = gageman.get_gages()
    # print(f'Downloading {len(gages)} gages')
    # print(os.getcwd())

    verbose = False
    if len(sys.argv) > 1:
        verbose = True
        if sys.argv[1].lower() == 'dwr':
            gages = [g for g in gages if g.gage_type == 'DWR']
        elif sys.argv[1].lower() == 'usgs':
            gages = [g for g in gages if g.gage_type == 'USGS']
        elif sys.argv[1].lower() == 'prr':
            gages = [g for g in gages if g.gage_type == 'PRR']
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

        elif gage.gage_type == 'PRR':
            get_prr_gage(gage, outpath, verbose=verbose)
            if verbose:
                print ('\tsuccess')

        else:
            raise AttributeError('gage was returned from get_gages() that is '
                                 'unknown')
        time.sleep(SLEEP)


if __name__ == '__main__':
    main()
