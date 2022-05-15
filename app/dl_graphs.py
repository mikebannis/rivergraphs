#!/usr/bin/python3
from __future__ import print_function

import shutil
import time
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime as dt
from datetime import timedelta
import matplotlib.dates as mdates
from matplotlib import pyplot as plt

import gageman


OUTPATH = '/var/www/rivergraphs/app/static/'

SLEEP = 5  # seconds between pulling gages


class URLError(Exception):
    pass

class FailedImageAddr(Exception):
    pass

def get_dwr_graph(gage, outfile=None):
    """
    Grabs default flow graph for Colorado DWR Gage 'gage'

    param: gage - string ('PLAGRAC' is south platte at grant, i.e. bailey gage)
    prarm: outfile - name of file to export
    """
    # API Doc: https://github.com/OpenCDSS/cdss-rest-services-examples
    gage_url = 'https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/' +\
                'telemetrytimeseriesraw/?format=jsonprettyprint&abbrev=' +\
                str(gage) + '&parameter=DISCHRG'

    response = requests.get(gage_url)
    if response.status_code != 200:
       raise URLError(response.status_code, response.text)

    # TODO - write all results to file, and make figure
    last_result = response.json()['ResultList'][-1]

    last_result = response.json()['ResultList'][-1]
    if last_result['measUnit'] != 'cfs':
        raise ValueError('Wrong unit type in last result: ' + str(last_result))

    q = last_result['measValue']
    timestamp = last_result['measDateTime']
    date = timestamp.split('T')[0]
    time = timestamp.split('T')[1]

    if outfile is None:
        outfile = gage+'.cfs'

    with open(outfile, 'wt') as out:
        out.write('{},{},{}\n'.format(q, date, time))

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

    i_outfile = outfile[:-4]+'.png'

    fmt = mdates.DateFormatter('%m-%d')
    plt.gca().xaxis.set_major_formatter(fmt)
    plt.grid(visible=True)
    plt.xticks(rotation=45)

    plt.plot(tss, qs)
    plt.savefig(i_outfile)
    plt.close()


def get_usgs_gage(gage, outfile=None):
    """
    Grabs default flow graph for USGS Gage 'gage' and write image to outfile.
    param: gage - string ('0671950' is clear creek at golden)
    prarm: outfile - name of file to export
    """
    gage_url = 'https://waterdata.usgs.gov/usa/nwis/uv?'+gage
    if outfile is None:
        outfile = gage+'.gif'

    response = requests.get(gage_url)

    # Verify we got good stuff back
    if response.status_code != 200:
        raise URLError(response.status_code, response.text)

#    # Grab the image url
#    img_addr = None
#    soup = BeautifulSoup(response.text, 'html.parser')
#    for img in soup.find_all('img'):
#        #print(img, img.get('alt'))
#
#        if img.get('alt') == "Graph of ":
#            img_addr =  img.get('src')
#            break
#    if img_addr is None:
#        raise FailedImageAddr('image address not found for '+gage)
#
#    # Grab and save the image
#    response = requests.get(img_addr, stream=True, cookies=response.cookies)
#    with open(outfile, 'wb') as out:
#        shutil.copyfileobj(response.raw, out)

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
                    raise FailedImageAddr('image address not found for '+gage)
                response = requests.get(img_addr, stream=True, cookies=response.cookies)
                with open(outfile, 'wb') as out:
                    shutil.copyfileobj(response.raw, out)

                # Grab the discharge and save it to a .cfs file
                _next = parent.next_sibling
                q = pull_val(_next)
                q_out = outfile[:-4]+'.cfs'  # TODO this is a bit of a hack
                #print (q_out)
                with open(q_out, 'wt') as out:
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
    verbose = False
    if len(sys.argv) > 1:
        verbose = True

    gages = gageman.get_gages()
    for gage in gages[::-1]:
        if verbose:
            print ('*** working on {} gage: {}'.format(gage.gage_type, gage))

        if gage.gage_type == 'USGS':
            outfile = OUTPATH + gage.image()
            try:
                get_usgs_gage(gage.gage_id, outfile)
            except FailedImageAddr:
                try:
                    if verbose:
                        print ('no image address, trying again...')
                    time.sleep(SLEEP)
                    get_usgs_gage(gage.gage_id, outfile)
                except FailedImageAddr:
                    if verbose:
                        print ('failed to download gage, skipping')
                    continue
            if verbose:
                print ('success')

        elif gage.gage_type == 'DWR':
            outfile = OUTPATH + gage.image()
            get_dwr_graph(gage.gage_id, outfile)
            if verbose:
                print ('success')

        else:
            raise AttributeError('gage was returned from get_gages() that is not USGS or DWR')
        time.sleep(SLEEP)


if __name__ == '__main__':
    main()
