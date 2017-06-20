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
                print (q_out)
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
            return (fields[i+1], fields[i+2], fields[i+3])
def main():
    gages = gageman.get_gages()
    for gage in gages:
        if gage.gage_type == 'USGS':
            print ('*** working on USGS gage:' + str(gage))
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
