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

LONG_SLEEP = 3  # seconds between pulling gages when called by cron
PLOT_DAYS = 7  # Days to plot on graph

# Extra room at top of custom hydrographs. 1.05 -> 5% extra room above max
GRAPH_TOP_BUFFER = 1.05

USGS_CODE = {
    'feet': '00065',
    'cfs': '00060',
}


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
    # only show last PLOT_DAYS days and drop other dirty data
    qs = []
    tss = []
    delta = timedelta(days=PLOT_DAYS)
    for q, ts in zip(raw_qs, raw_tss):
        if raw_tss[-1] - ts > delta:
            continue
        if not util.is_float(q):
            continue
        if q is None:
            continue
        qs.append(q)
        tss.append(ts)

    fmt = mdates.DateFormatter('%b\n%d')  # May\n5
    fig, ax = plt.subplots(1, figsize=(5.76, 3.84), dpi=100)

    if len(qs) == 0 or len(tss) == 0:
        print(f'No data to plot for {gage}')

    ax.plot(tss, qs)
    max_q = max(qs) if len(qs) > 0 else 0
    ax.set_ylim(ymin=0, ymax=max_q * GRAPH_TOP_BUFFER)
    ax.xaxis.set_major_formatter(fmt)
    plt.grid(visible=True)

    i_outfile = os.path.join(outpath, gage.image_file())
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
                    print(f'\tgot: {", ".join(q)} from website')

                q_outfile = os.path.join(outpath, gage.data_file())
                with open(q_outfile, 'wt') as out:
                    for val in q:
                        out.write(str(val) + ',')
                    out.write('\n')

    # Pull multiple values and write to file. URL builder at:
    # https://waterservices.usgs.gov/rest/IV-Test-Tool.html
    code = USGS_CODE[gage.units]
    url = (f'https://waterservices.usgs.gov/nwis/iv/?sites={gage.gage_id}&'
           f'parameterCd={code}&period=P{PLOT_DAYS}D&siteStatus=all&format=json')

    resp = requests.get(url)
    if resp.status_code != 200:
        raise ValueError(f'Bad respone ({resp.status_code}) from {url}, got: '
                         f'"{resp.text}"')

    results = resp.json()['value']['timeSeries'][0]['values'][0]['value']
    if verbose:
        print(f'\tGot {len(results)} results from API. Latest value is: {results[-1]}')

    outfile = os.path.join(outpath, gage.data_file())
    with open(outfile, 'wt') as out:
        for result in results:
            value = result['value']
            timestamp = result['dateTime']
            date = timestamp.split('T')[0]
            time = timestamp.split('T')[1].split('-')[0].split('.')[0]

            data = f'{value},{date},{time}'
            out.write(data+'\n')


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

def get_foxton_gage(gage, outpath, verbose=False):
    """
    Determine foxton gage as waterton - deckers
    """
    import pandas as pd

    waterton = gageman.get_gage('PLASPLCO', 'DWR').series
    deckers = gageman.get_gage('06701900', 'USGS').series
    foxton = (waterton - deckers).dropna()

    if foxton.size <= 0:
        raise ValueError('No data points calculated for foxton!')

    # clip to last 7 days
    mask = foxton.index > dt.today() - timedelta(days=PLOT_DAYS)
    foxton = foxton[mask]

    make_graph(foxton.values, foxton.index, outpath, gage)

    datafile = os.path.join(outpath, gage.data_file())
    with open(datafile, 'wt') as f:
        date = foxton.index[-1].strftime('%Y-%m-%d')
        time = foxton.index[-1].strftime('%H:%M:%S')
        f.write(f'{foxton[-1]},{date},{time}\n')


def get_wildcat_gage(gage, outpath, verbose=False):
    """
    Determine wildcat gage as above cheesman - tarryall
    """
    import pandas as pd

    cheesman = gageman.get_gage('06700000', 'USGS').series
    tarryall = gageman.get_gage('TARTARCO', 'DWR').series
    wildcat = (cheesman - tarryall).dropna()

    if wildcat.size <= 0:
        raise ValueError('No data points calculated for wildcat!')

    # clip to last 7 days
    mask = wildcat.index > dt.today() - timedelta(days=PLOT_DAYS)
    wildcat = wildcat[mask]

    make_graph(wildcat.values, wildcat.index, outpath, gage)

    datafile = os.path.join(outpath, gage.data_file())
    with open(datafile, 'wt') as f:
        date = wildcat.index[-1].strftime('%Y-%m-%d')
        time = wildcat.index[-1].strftime('%H:%M:%S')
        f.write(f'{wildcat[-1]},{date},{time}\n')

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
        stage = header.find('a').getText().split(' ')[2].replace('+', '').replace('-', '')
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
            if verbose:
                print(f'\tData received is same as in data file: {old_data.strip()}')
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
            try:
                raw_stages.append(float(fields[0]))
            except ValueError:
                print(f'\tCorrupt line found in {datafile}: "{line.strip()}"')
                continue
            ts = dt.strptime(f'{fields[1]} {fields[2]}', '%Y-%m-%d %H:%M:%S')
            raw_tss.append(ts)

    make_graph(raw_stages, raw_tss, outpath, gage)


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
        elif sys.argv[1].lower() == '--verbose':
            pass
        else:
            print(f'Unknown option: {sys.argv[1]}')
            sys.exit()
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
        if i > 0 and not verbose:
            time.sleep(LONG_SLEEP)

        if verbose:
            print ('*** working on {} gage: {}'.format(gage.gage_type, gage))

        # USGS is a little special, try twice for image
        if gage.gage_type == 'USGS':
            try:
                get_usgs_gage(gage, outpath, verbose=verbose)
            except FailedImageAddr:
                try:
                    if verbose:
                        print ('\tno image address, trying again...')
                    time.sleep(LONG_SLEEP)
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
            continue

        # Determine gage getter function
        if gage.gage_type == 'DWR':
            getter = get_dwr_graph
        elif gage.gage_type == 'PRR':
            getter = get_prr_gage
        elif gage.gage_type == 'WYSEO':
            getter = get_wyseo_gage
        elif gage.gage_type == 'VIRTUAL' and gage.gage_id == 'NSV':
            getter = get_nsv_gage
        elif gage.gage_type == 'VIRTUAL' and gage.gage_id == 'FOXTON':
            getter = get_foxton_gage
        elif gage.gage_type == 'VIRTUAL' and gage.gage_id == 'WILDCAT':
            getter = get_wildcat_gage
        else:
            print(f'ERROR: unknown gage: "{gage.gage_type}" "{gage.gage_id}"')
            continue

        # If verbose, we're running interactively. Allow exceptions to propagate
        if verbose:
            getter(gage, outpath, verbose=verbose)
            print ('\tsuccess')
            continue

        # Running from cron. Catch exceptions and move on
        try:
            getter(gage, outpath, verbose=verbose)
        except Exception as e:
            print(f'\tError getting {gage.gage_type} {gage.gage_id}:', e)
            continue


if __name__ == '__main__':
    main()
