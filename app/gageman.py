import csv
from collections import defaultdict

GAGEFILE= '/var/www/rivergraphs/app/gages.csv'

class Gage(object):
    """
    Information pertaining to a DWR or USGS gage, and methods returning graph image
    and URL to the actual gage
    """
    def __init__(self, gage_id, gage_type, river, location):
        self.gage_id = gage_id  # id for gage (string), for usgs this looks like 06716500, for dwr 
                                # this is PLAGRACO
        self.gage_type = gage_type # either 'USGS' or 'DWR' (string)
        self.river = river  # name of river/creek (string)
        self.location = location  # location of gage (string)
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
            return 'http://www.dwr.state.co.us/SurfaceWater/data/detail_graph.aspx?ID=' + \
                    self.gage_id + '&MTYPE=DISCHRG'

    def __str__(self):
        return self.gage_id + ',' + self.gage_type + ',' + self.river + ',' + self.location

def get_gages(filename=GAGEFILE):
    gages = []
    with open(filename, 'rt') as infile:
        rdr = csv.DictReader(filter(lambda row: row[0]!='#', infile))
        for row in rdr:
            temp_gage = Gage(row['gage_id'], row['type'], row['river'], row['location'])
            gages.append(temp_gage)
    return gages

def get_rivers(filename=GAGEFILE):
    gages = get_gages(filename)
    rivers = defaultdict(list)
    for gage in gages:
        rivers[gage.river].append(gage)
    return rivers

if __name__ == '__main__':
    get_graphs_new()
