import csv
import util
import os.path
import pandas as pd
# import matplotlib
from collections import defaultdict
#from pandas.plotting import register_matplotlib_converters

#register_matplotlib_converters()


class Gage(object):
    """
    Information pertaining to a DWR or USGS gage, and methods returning graph
    image and URL to the actual gage
    """
    def __init__(self, gage_id, gage_type, river, location, region):
        self.gage_id = gage_id  # id for gage (string), for usgs this looks
                                # like 06716500, for dwr this is PLAGRACO
        self.gage_type = gage_type  # either 'USGS' or 'DWR' (string)
        self.river = river  # name of river/creek (string)
        self.location = location  # location of gage (string)
        self.region = region  # region the gage is located in (FR, Ark, etc)

        self.q, self.q_date, self.q_time = self._get_q()

        gage_types = ['USGS', 'DWR', 'PRR', 'WYSEO', 'VIRTUAL']
        if gage_type not in gage_types:
            raise AttributeError(f'gage_type must be {", ".join(gage_types)} '
                                 f'passed {gage_type}')

    @property
    def series(self):
        """ Get all data as pd.Series indexed by datetime """
        q_file = os.path.join(util.static_dir(), self.data_file())
        df = pd.read_csv(q_file, names=['value', 'date', 'time'])
        df['dt'] = df.date + ' ' + df.time
        df.dt = pd.to_datetime(df.dt, format='%Y-%m-%d %H:%M:%S')
        df.index = df.dt
        return df.value

    @property
    def units(self):
        if self.gage_type == 'PRR':
            return 'feet'
        elif self.gage_id in [
                '13309220',  # Middle Fork
                ]:
            return 'feet'
        elif self.gage_id in [
                'BRKDAMCO'  # Button rock res, NSV
                ]:
            return 'ac-ft'
        else:
            return 'cfs'

    def image_file(self):
        """ Return file name for gage image"""
        if self.gage_type == 'USGS':
            img_file = self.gage_id + '.gif'
        else:
            img_file = self.gage_id + '.png'

        return img_file

    def data_file(self):
        """ Return file name for gage data """
        return f'{self.gage_id}.cfs'

    def image_exists(self):
        """ Returns true if the image exists"""
        path = os.path.dirname(os.path.abspath(__file__))
        return os.path.exists(os.path.join(path, 'static', self.image_file()))

    def data_url(self):
        """ Return data URL for gage"""
        if self.gage_type == 'USGS':
            return 'https://waterdata.usgs.gov/nwis/uv?site_no=' + self.gage_id
        elif self.gage_type == 'PRR':
            return 'http://www.poudrerockreport.com/'
        elif self.gage_type == 'DWR':
            # API Doc: https://github.com/OpenCDSS/cdss-rest-services-examples
            param = 'STORAGE' if self.gage_id == 'BRKDAMCO' else 'DISCHRG'
            return 'https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/' +\
                    'telemetrytimeseriesraw/?format=jsonprettyprint&abbrev=' +\
                    f'{self.gage_id}&parameter={param}'
        else:
            return f'Data URL not known for {self.gage_id} {self.gage_type}'

    def url(self):
        """ Return URL to human readable USGS or DWR gage page """
        if self.gage_type == 'USGS':
            return 'https://waterdata.usgs.gov/nwis/uv?site_no=' + self.gage_id
        elif self.gage_type == 'PRR':
            return 'http://www.poudrerockreport.com/'
        elif self.gage_type == 'WYSEO':
            return 'https://seoflow.wyo.gov/Data/DataSet/Chart/Location/014CWT/DataSet/Discharge/Tunnel/Interval/Monthly/'
        elif self.gage_type == 'DWR':
            return f'https://dwr.state.co.us/Tools/Stations/{self.gage_id}?params=DISCHRG'
        else:
            return f'Human URL not known for {self.gage_id} {self.gage_type}'

    def _get_q(self):
        """
        Pulls and returns most recent discharge from *.cfs file in static
        directory
        """
        q_file = os.path.join(util.static_dir(), self.data_file())
        if not os.path.isfile(q_file):
            print(f'Gage data file {q_file} not found')
            return 9999, 9999, 9999

        # Grab last line from gage data file
        with open(q_file, 'rt') as infile:
            for data in infile:
                pass

        try:
            fields = data.strip().split(',')
        except UnboundLocalError:
                return 666, 666, 666

        try:
            if self._is_float(fields[0]):
                q = self.round_val(float(fields[0]))
            else:
                q = 'Error'
            q_date = fields[1]
            q_time = fields[2]
        except IndexError:
            print('Error getting data for {}, fields: {}'.format(self.gage_id,
                                                                 fields))
            q = 9999
            q_date = 9999
            q_time = 9999

        return q, q_date, q_time

    def round_val(self, val):
        """
        Round stage or discharge appropriately
        """
        if self.gage_type != 'PRR' and self.gage_id != '13309220':
            return int(val)
        return val

    @staticmethod
    def _is_float(s):
        try:
            _ = float(s)
            return True
        except ValueError:
            return False

    def __str__(self):
        return self.gage_id + ',' + self.gage_type + ',' + self.river + ',' +\
                self.location + ',' + self.region


def get_gages():
    """
    Load gages from gage files

    @returns {list of Gage}
    """
    gages = []
    with open(util.gages_file(), 'rt') as infile:
        rdr = csv.DictReader(filter(lambda row: row[0] != '#', infile))
        for row in rdr:
            temp_gage = Gage(row['gage_id'], row['type'], row['river'],
                             row['location'], row['region'])
            gages.append(temp_gage)
    return gages


def get_gage(id, _type):
    """
    Load individual gage from file

    @returns {Gage}
    """
    gages = []
    with open(util.gages_file(), 'rt') as infile:
        rdr = csv.DictReader(filter(lambda row: row[0] != '#', infile))
        for row in rdr:
            if row['gage_id'] == id and row['type'] == _type:
                gage = Gage(row['gage_id'], row['type'], row['river'],
                            row['location'], row['region'])
                return gage
    raise ValueError('Gage not found')


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
