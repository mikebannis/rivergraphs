#!/usr/bin/python
import requests
from bs4 import BeautifulSoup
import shutil
import time
import gageman

OUTPATH = '/var/www/rivergraphs/app/static/'

SLEEP = 5  # seconds between pulling gages

class URLError(Exception):
    pass

class FailedImageAddr(Exception):
    pass

def get_dwr_graph(gage, outfile=None):
    """
    Grabs default flow graph for Colorado DWR Gage 'gage' and write image to outfile.
    param: gage - string ('PLAGRAC' is south platte at grant, i.e. bailey gage)
    prarm: outfile - name of file to export 
    """
    #TODO - check for .png at end of outfile
    gage_url = 'http://www.dwr.state.co.us/SurfaceWater/data/detail_graph.aspx?ID='+gage
    if outfile is None:
        outfile = gage+'.png'
    response = requests.get(gage_url)
    
    # Verify we got good stuff back
    if response.status_code != 200:
        raise URLError(response.status_code, response.text)

    # Grab the image url
    soup = BeautifulSoup(response.text, 'html.parser')
    for img in soup.find_all('img'):
        id = img.get('id')
        if id == 'ctl00_ContentPlaceHolder1_ctl00':
            img_addr = 'http://www.dwr.state.co.us' + img.get('src')

    # Get and save the image
    response = requests.get(img_addr, stream=True, cookies=response.cookies)
    with open(outfile, 'wb') as out:
        shutil.copyfileobj(response.raw, out)
    
    #print response.status_code
    #print response.text

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
    
    # Grab the image url
    img_addr = None
    soup = BeautifulSoup(response.text, 'html.parser')
    for img in soup.find_all('img'):
        #print(img, img.get('alt'))

        if img.get('alt') == "Graph of ":
            img_addr =  img.get('src')
            break
    if img_addr is None:
        raise FailedImageAddr('image address not found for '+gage)

    # Grab and save the image
    response = requests.get(img_addr, stream=True, cookies=response.cookies)
    with open(outfile, 'wb') as out:
        shutil.copyfileobj(response.raw, out)

def main():
    gages = gageman.get_gages()
    for gage in gages:
        if gage.gage_type == 'USGS':
            print ('working on USGS gage:' + str(gage))
            outfile = OUTPATH + gage.image()
            try:
                get_usgs_gage(gage.gage_id, outfile)
                print ('success')
            except FailedImageAddr:
                try:
                    print ('no image address, trying again...')
                    time.sleep(SLEEP)
                    get_usgs_gage(gage.gage_id, outfile)
                    print ('success')
                except FailedImageAddr:
                    print ('failed to download gage, skipping')
        elif gage.gage_type == 'DWR':
            print ('processing DWR gage:' + str(gage))
            outfile = OUTPATH + gage.image()
            get_dwr_graph(gage.gage_id, outfile)
            print ('success')
        else: 
            raise AttributeError('gage was returned from get_gages() that is not USGS or DWR')
        time.sleep(SLEEP)


if __name__ == '__main__':
    main()
