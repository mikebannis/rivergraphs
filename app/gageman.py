import csv
from collections import defaultdict
import os.path

GAGEFILE= '/var/www/rivergraphs/app/gages.csv'
STATIC='/var/www/rivergraphs/app/static'

class Gage(object):
    """
    Information pertaining to a DWR or USGS gage, and methods returning graph image
    and URL to the actual gage
    """
    def __init__(self, gage_id, gage_type, river, location, region):
        self.gage_id = gage_id  # id for gage (string), for usgs this looks like 06716500, for dwr 
                                # this is PLAGRACO
        self.gage_type = gage_type # either 'USGS' or 'DWR' (string)
        self.river = river  # name of river/creek (string)
        self.location = location  # location of gage (string)
        self.region = region  # region the gage is located in (FR, Ark, Central, etc)
        
        self.q = None  # most recent discharge
        self.q_date = None  # date of most recent discharge
        self.q_time = None  # tiem of most recent discharge
        self._get_q()  # Get values for q, q_date, & q_time

        if gage_type != 'USGS' and gage_type != 'DWR':
            raise AttributeError('gage_type must be USGS or DWR, was passed ' + gage_type)
    
    def image(self):
        if self.gage_type == 'USGS':
            return self.gage_id + '.gif'
        else:
            return self.gage_id + '.png'

    def url(self):
        """ Return URL to USGS or DWR gage page """
        if self.gage_type == 'USGS':
            return 'https://waterdata.usgs.gov/nwis/uv?site_no=' + self.gage_id
        else:
            return 'https://dwr.state.co.us/Tools/Stations/' + self.gage_id
            # return 'http://www.dwr.state.co.us/SurfaceWater/data/detail_graph.aspx?ID=' + \
             #       self.gage_id + '&MTYPE=DISCHRG'

    def _get_q(self):
        """ Pulls and returns most recent discharge from *.cfs file in static directory """
        q_file = os.path.join(STATIC, self.gage_id + '.cfs')
        if os.path.isfile(q_file):
            with open(q_file, 'rt') as infile:
                data = infile.readline()
            fields = data.strip().split(',')
            self.q = fields[0]  # First field is discharge
            self.q_date = fields[1] 
            self.q_time = fields[2] 

    def __str__(self):
        return self.gage_id + ',' + self.gage_type + ',' + self.river + ',' + self.location + \
                ',' + self.region

def get_gages(filename=GAGEFILE):
    gages = []
    with open(filename, 'rt') as infile:
        rdr = csv.DictReader(filter(lambda row: row[0]!='#', infile))
        for row in rdr:
            temp_gage = Gage(row['gage_id'], row['type'], row['river'], row['location'], row['region'])
            gages.append(temp_gage)
    return gages

def get_rivers(gages):
    """
    Organizes gages by river
    :param gages: dict from get_gages()
    :returns: dict of gages organized by river
    """
    rivers = defaultdict(list)
    for gage in gages:
        rivers[gage.river].append(gage)
    return rivers

if __name__ == '__main__':
    get_graphs_new()
