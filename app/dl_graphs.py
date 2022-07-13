#!/usr/bin/env python3
from __future__ import print_function

import os
import sys
import time
import pytz
import shutil
import requests
from bs4 import BeautifulSoup
from datetime import timedelta
from datetime import datetime as dt
import matplotlib.dates as mdates
from matplotlib import pyplot as plt
from pandas.plotting import register_matplotlib_converters

import gageman
import util

register_matplotlib_converters()

SLEEP = 5  # seconds between pulling gages
PLOT_DAYS = 7  # Days to plot on graph


class URLError(Exception):
    pass


class FailedImageAddr(Exception):
    pass


def get_wyseo_gage(gage, outpath, verbose=False):
    """
    Grabs default flow graph for WY State Engineers Office
    e.g. https://seoflow.wyo.gov/Data/DataSet/Chart/Location/014CWT/DataSet/Discharge/Tunnel/Interval/Custom/2022/07/01/2022/08/01

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    assert gage.gage_id == '4578', 'This only works for blue grass...'

    utc = pytz.timezone('UTC')
    mtn = pytz.timezone('US/Mountain')
    date_f = '%Y-%m-%dT%H:%M:%SZ'

    start = (dt.now() - timedelta(days=PLOT_DAYS+1)).strftime('%Y-%m-%d')
    end = (dt.now() + timedelta(days=2)).strftime('%Y-%m-%d')
    if verbose:
        print(f'Getting data for {gage.gage_id} from {start} to {end}')

    data = {
        'sort': 'TimeStamp-asc',
        'date': start,
        'endDate': end,
    }
    response = requests.post(
        'https://seoflow.wyo.gov/Data/DatasetGrid?dataset=4578',
        data=data
    )

    if response.status_code != 200:
        raise URLError(response.status_code, response.text)
    results = response.json()['Data']

    outfile = os.path.join(outpath, gage.data_file())
    with open(outfile, 'wt') as out:
        for result in results:
            q = result['Value']
            timestamp = utc.localize(dt.strptime(result['TimeStamp'], date_f))
            timestamp = timestamp.astimezone(mtn)
            timestamp_str = timestamp.strftime('%Y-%m-%d,%H:%M:%S')
            data = f'{q},{timestamp_str}\n'
            out.write(data)

    if verbose:
        print(f'\tWrote {len(results)} results to {outfile}')
        print(f'\tLast result was {data}')

    # --- Plot and save the hydrograph
    raw_qs = [r['Value'] for r in results]
    raw_tss = [
        utc.localize(dt.strptime(r['TimeStamp'], date_f)).astimezone(mtn)
        for r in results
    ]
    make_graph(raw_qs, raw_tss, outpath, gage)


def get_dwr_graph(gage, outpath, verbose=False):
    """
    Grabs default flow graph for Colorado DWR Gage 'gage'

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    response = requests.get(gage.data_url())
    if response.status_code != 200:
        raise URLError(response.status_code, response.text)
    results = response.json()['ResultList']

    outfile = os.path.join(outpath, gage.data_file())
    with open(outfile, 'wt') as out:
        for result in results:
            q = result['measValue']
            timestamp = result['measDateTime']
            date = timestamp.split('T')[0]
            time = timestamp.split('T')[1]

            data = f'{q},{date},{time}'
            out.write(data+'\n')

    if verbose:
        print(f'\tWrote {len(results)} results to {outfile}')
        print(f'\tLast result was {data}')

    # --- Plot and save the hydrograph
    date_f = '%Y-%m-%dT%H:%M:%S'
    raw_qs = [r['measValue'] for r in results]
    raw_tss = [dt.strptime(r['measDateTime'], date_f) for r in results]
    make_graph(raw_qs, raw_tss, outpath, gage)


def make_graph(raw_qs, raw_tss, outpath, gage):
    """
    Make a hydro graph and save it

    @param {list of float} raw_qs - list of discharges or stages
    @param {list of Datetime} raw_tss - time stamps for readings
    @param {str} outpath - the static dir
    @param {gageman.Gage} gage - the gage the graph is for
    """
    # only show last 7 days
    qs = []
    tss = []
    delta = timedelta(days=PLOT_DAYS)
    for q, ts in zip(raw_qs, raw_tss):
        if raw_tss[-1] - ts > delta:
            continue
        qs.append(q)
        tss.append(ts)

    i_outfile = os.path.join(outpath, gage.image_file())

    fmt = mdates.DateFormatter('%b\n%d')  # May\n5
    fig, ax = plt.subplots(1, figsize=(5.76, 3.84), dpi=100)

    if len(qs) == 0 or len(tss) == 0:
        raise ValueError(f'No data to plot for {gage}')

    ax.plot(tss, qs)
    ax.set_ylim(ymin=0)
    ax.xaxis.set_major_formatter(fmt)
    plt.grid(visible=True)
    plt.savefig(i_outfile)
    plt.close()


def get_usgs_gage(gage, outpath, verbose=False):
    """
    Grabs default flow graph for USGS Gage 'gage' and write image to outfile.

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    param: {bool} verbose - print debug text if True
    """
    response = requests.get(gage.data_url())

    # Verify we got good stuff back
    if response.status_code != 200:
        raise URLError(response.status_code, response.text)

    soup = BeautifulSoup(response.text, 'html.parser')

    if gage.units == 'cfs':
        search = 'Discharge, cubic feet per second'
    elif gage.units == 'feet':
        search = 'Gage height, feet'
    else:
        raise ValueError('Units for USGS gage must be cfs or feet. Received '
                         f'{gage.units} for {gage}')

    if verbose:
        print(f'\tlooking for {search}')


    # Get the discharge
    for tag in soup.find_all('a'):
        if tag.get('name') == "gifno-99":
            if tag.getText().strip() == search:
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
                if verbose:
                    print(f'\tgot: {", ".join(q)}')

                q_outfile = os.path.join(outpath, gage.data_file())
                with open(q_outfile, 'wt') as out:
                    for val in q:
                        out.write(str(val) + ',')
                    out.write('\n')


def pull_val(text):
    """ Pull gage values for USGS """
    fields = text.split()
    for i in range(len(fields)):
        if fields[i] == 'value:':
            try:
                return (fields[i+1], fields[i+2], fields[i+3])
            except IndexError:
                return ('N/A', 'Gauge appears to be offline', '')

def get_nsv_gage(gage, outpath, verbose=False):
    """
    Determine NSV flow above button rock by determining rate of change of
    volume in button rock and adding to discharge downstream. Assume 1 cfs ==
    1/12 ac-ft/hr
    """
    import pandas as pd

    # Proving grounds q - find average flow per hour
    pgq_g = gageman.get_gage('NSVBBRCO', 'DWR')
    pgq = pgq_g.series.groupby(pd.Grouper(freq='H')).mean()

    # Button rock dam af-ft
    braf_g = gageman.get_gage('BRKDAMCO', 'DWR')
    # This probably doesn't need to be averaged, but doesn't really hurt either
    braf = braf_g.series.groupby(pd.Grouper(freq='H')).mean()

    # Calculate approx inflow
    nsvq = braf.diff()*12 + pgq

    # clip to last 7 days and chop off fake peaks
    mask = nsvq.index > dt.today() - timedelta(days=PLOT_DAYS)
    nsvq = nsvq[mask]
    nsvq = nsvq[nsvq < nsvq.median() * 4]

    make_graph(nsvq.values, nsvq.index, outpath, gage)

    datafile = os.path.join(outpath, gage.data_file())
    with open(datafile, 'wt') as f:
        date = nsvq.index[-1].strftime('%Y-%m-%d')
        time = nsvq.index[-1].strftime('%H:%M:%S')
        f.write(f'{nsvq[-1]},{date},{time}\n')


def get_prr_gage(gage, outpath, verbose=False):
    """
    Grabs default flow graph for the Poudre rock report and write image to
    outfile.

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    # TODO - look for urllib3.exceptions.NewConnectionError
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
    ts = dt.strptime(f'{mmm_dd} {year} {time}', '%B %d %Y %H%M')
    data = '{},{},{}'.format(stage, ts.date(), ts.time())

    # grab last line of data file if it exists
    datafile = os.path.join(outpath, gage.data_file())
    if os.path.exists(datafile):
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
            raw_stages.append(float(fields[0]))
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
    verbose = False

    if len(sys.argv) == 1:
        gages = gageman.get_gages()
    elif len(sys.argv) == 2:
        verbose = True
        gages = gageman.get_gages()
        if sys.argv[1].lower() == 'dwr':
            gages = [g for g in gages if g.gage_type == 'DWR']
        elif sys.argv[1].lower() == 'usgs':
            gages = [g for g in gages if g.gage_type == 'USGS']
        elif sys.argv[1].lower() == 'prr':
            gages = [g for g in gages if g.gage_type == 'PRR']
        elif sys.argv[1].lower() == 'reverse':
            gages = gages[::-1]
    elif len(sys.argv) == 3:
        verbose = True
        if sys.argv[1].lower() == '--id':
            gages = gageman.get_gages()
            gages = [g for g in gages if g.gage_id == sys.argv[2]]
        else:
            print('This isn\'t valid:', sys.argv)
            sys.exit()
    else:
        print('This isn\'t valid:', sys.argv)
        sys.exit()

    if len(gages) == 0:
        print('No matching gages found!!!')
        sys.exit()

    outpath = util.static_dir()

    for i, gage in enumerate(gages):
        if verbose:
            print ('*** working on {} gage: {}'.format(gage.gage_type, gage))

        if gage.gage_type == 'USGS':
            try:
                get_usgs_gage(gage, outpath, verbose=verbose)
            except FailedImageAddr:
                try:
                    if verbose:
                        print ('\tno image address, trying again...')
                    time.sleep(SLEEP)
                    get_usgs_gage(gage, outpath, verbose=verbose)
                except FailedImageAddr:
                    if verbose:
                        print ('\tfailed to download gage, skipping')
                    continue
            except Exception as e:
                print(f'\tError getting gage {gage}: {e}')
                continue

            if verbose:
                print ('\tsuccess')

        elif gage.gage_type == 'DWR':
            try:
                get_dwr_graph(gage, outpath, verbose=verbose)
            except Exception as e:
                print(f'\tError getting gage {gage}: {e}')
                continue

            if verbose:
                print ('\tsuccess')

        elif gage.gage_type == 'PRR':
            try:
                get_prr_gage(gage, outpath, verbose=verbose)
            except Exception as e:
                print(f'\tError getting gage {gage}: {e}')
                continue

            if verbose:
                print ('\tsuccess')

        elif gage.gage_type == 'WYSEO':
            try:
                get_wyseo_gage(gage, outpath, verbose=verbose)
            except Exception as e:
                print(f'\tError getting gage {gage}: {e}')
                continue

            if verbose:
                print ('\tsuccess')

        elif gage.gage_type == 'VIRTUAL' and gage.gage_id =='NSV':
            try:
                get_nsv_gage(gage, outpath, verbose=verbose)
            except Exception as e:
                print('\tError getting nsv gage:', e)
                continue

            if verbose:
                print ('\tsuccess')

        else:
            print(f'ERROR: unknown gage: "{gage.gage_type}" "{gage.gage_id}"')

        if i + 1 < len(gages):
            time.sleep(SLEEP)


if __name__ == '__main__':
    main()
