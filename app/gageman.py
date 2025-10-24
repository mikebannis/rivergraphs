import time
import util
import yaml
import os.path
from collections import defaultdict
from datetime import datetime as dt
from typing import Union

import pandas as pd

GAGE_TYPES = ["USGS", "DWR", "PRR", "WYSEO", "VIRTUAL"]

# Age of data in hours before old data warning is displayed
OLD_DATA_HOURS = 6


class Gage:
    """
    Information pertaining to a DWR or USGS gage, and methods returning graph
    image and URL to the actual gage
    """

    def __init__(self, gage_id, gage_type, river, location, region, menu={}, units=None):
        self.gage_id = gage_id  # id for gage (string), for usgs this looks
        # like 06716500, for dwr this is PLAGRACO
        self.gage_type = gage_type  # either 'USGS' or 'DWR' (string)
        self.river = river  # name of river/creek (string)
        self.location = location  # location of gage (string)
        self.region = region  # region the gage is located in (FR, Ark, etc)
        if units is None:
            units = "cfs"
        self.units = units  # cfs, feet, or ac-ft

        self.menu = menu

        self.q, self.q_date, self.q_time = self._get_q()

        if gage_type not in GAGE_TYPES:
            raise AttributeError(
                f'gage_type must be {", ".join(GAGE_TYPES)} ' f"passed {gage_type}"
            )

    @property
    def series(self):
        """Get all data as pd.Series indexed by datetime"""
        q_file = os.path.join(util.static_dir(), self.data_file())
        df = pd.read_csv(q_file, names=["value", "date", "time"])
        df["dt"] = df.date + " " + df.time
        df.dt = pd.to_datetime(df.dt, format="%Y-%m-%d %H:%M:%S")
        df.index = df.dt
        return df.value

    @property
    def q_unix_time(self) -> Union[str, int]:
        try:
            q_dt = dt.strptime(f"{self.q_date},{self.q_time}", "%Y-%m-%d,%H:%M:%S")
            _dt = round(time.mktime(q_dt.timetuple()))
        except ValueError as e:
            msg = f"Error converting q_date: '{self.q_date}', q_time: '{self.q_time}' for {self.gage_id}"
            print(msg, e)
            return msg

        return _dt

    @property
    def old_date_warning(self) -> str:
        """
        Display a warning if the gage timestamp is old

        @returns HTML of the warning
        """
        ts = self.q_unix_time
        if isinstance(ts, str):
            # Bad timestamp
            tooltip = "Gage timestamp does not appear to be valid"
            return f"""
                <i class="fa-solid fa-warning text-danger" data-bs-toggle="tooltip"
                   title="{tooltip}">
                </i>
            """

        current_ts = time.time()
        diff = current_ts - ts

        if diff < OLD_DATA_HOURS * 3600:
            return ""

        tooltip = f"Gage data is {round(diff/3600, 1)} hours old"
        if diff / 3600 > 24:
            tooltip = f"Gage data is {int(diff/3600/24)} days old"

        return f"""
            <i class="fa-solid fa-warning text-danger" data-bs-toggle="tooltip"
                title="{tooltip}">
            </i>
        """

    def image_file(self):
        """Return file name for gage image"""
        if self.gage_type == "USGS":
            img_file = f"{self.gage_id}.gif"
        else:
            img_file = f"{self.gage_id}.png"

        return img_file

    def data_file(self):
        """Return file name for gage data"""
        return f"{self.gage_id}.cfs"

    def image_exists(self):
        """Returns true if the image exists"""
        path = os.path.dirname(os.path.abspath(__file__))
        return os.path.exists(os.path.join(path, "static", self.image_file()))

    def data_url(self):
        """Return data API URL for gage"""
        if self.gage_type == "USGS":
            return f"https://waterdata.usgs.gov/nwis/uv?site_no={self.gage_id}"
        elif self.gage_type == "PRR":
            return "http://www.poudrerockreport.com/"
        elif self.gage_type == "DWR":
            # API Doc: https://github.com/OpenCDSS/cdss-rest-services-examples
            param = "STORAGE" if self.gage_id == "BRKDAMCO" else "DISCHRG"
            return (
                "https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/"
                "telemetrytimeseriesraw/?format=json&abbrev="
                f"{self.gage_id}&parameter={param}"
            )
        else:
            return f"Data URL not known for {self.gage_id} {self.gage_type}"

    def url(self):
        """Return URL to human readable USGS or DWR gage page"""
        if self.gage_type == "USGS":
            return f"https://waterdata.usgs.gov/nwis/uv?site_no={self.gage_id}"
        elif self.gage_type == "PRR":
            return "http://www.poudrerockreport.com/"
        elif self.gage_type == "WYSEO":
            return "https://seoflow.wyo.gov/Data/DataSet/Chart/Location/014CWT/DataSet/Discharge/Tunnel/Interval/Monthly/"
        elif self.gage_type == "DWR":
            return f"https://dwr.state.co.us/Tools/Stations/{self.gage_id}?params=DISCHRG"
        else:
            return None
            # return f'Human URL not known for {self.gage_id} {self.gage_type}'

    def _get_q(self):
        """
        Pulls and returns most recent discharge from *.cfs file in static
        directory
        """
        q_file = os.path.join(util.static_dir(), self.data_file())
        if not os.path.isfile(q_file):
            print(f"Gage data file {q_file} not found")
            return 9999, 9999, 9999

        # Grab last line from gage data file
        with open(q_file, "rt") as infile:
            for data in infile:
                pass

        try:
            fields = data.strip().split(",")
        except UnboundLocalError:
            return 666, 666, 666

        try:
            if util.is_float(fields[0]):
                q = self.round_val(float(fields[0]))
            else:
                q = "Error"
            q_date = fields[1]
            q_time = fields[2]
        except IndexError:
            print("Error getting data for {}, fields: {}".format(self.gage_id, fields))
            q = 9999
            q_date = 9999
            q_time = 9999

        return q, q_date, q_time

    def round_val(self, val):
        """
        Round stage or discharge appropriately
        """
        if self.units == "cfs" or self.units == "ac-ft":
            return int(val)
        return val

    def __str__(self):
        """
        This format may be getting used for export to CSV files, not sure.
        Don't change w/o checking!!!
        """
        return f"{self.gage_id},{self.gage_type},{self.river},{self.location},{self.region}"

    def __repr__(self):
        return (
            f"gage_id={self.gage_id}, gage_type={self.gage_type}, river={self.river}, "
            f"location={self.location}, region={self.region}, units={self.units}, menu={self.menu}"
        )


def get_gages():
    """
    Load gages from gage files

    @returns {list of Gage}
    """
    gages = []
    with open(util.gages_file(), "rt") as infile:
        raw_gages = yaml.safe_load(infile)
        for row in raw_gages:
            temp_gage = Gage(
                row["gage_id"],
                row["type"],
                row["river"],
                row["location"],
                row["region"],
                row.get("menu", {}),
                units=row["units"],
            )
            gages.append(temp_gage)
    return gages


def get_gage(_id=None, _type=None) -> Gage:
    """
    Load individual gage from file

    @param {str} _id - id of gage
    @param {str} _type - type of gage, e.g. 'USGS', 'DWR', etc
    @returns {Gage}
    """
    if _id is None or _type is None:
        raise AttributeError("Both _id and _type must be set")

    with open(util.gages_file(), "rt") as infile:
        raw_gages = yaml.safe_load(infile)
        for row in raw_gages:
            if row["gage_id"] == _id and row["type"] == _type:
                gage = Gage(
                    row["gage_id"],
                    row["type"],
                    row["river"],
                    row["location"],
                    row["region"],
                    row.get("menu", {}),
                    units=row["units"],
                )
                return gage
    raise ValueError(f"Gage {_type} {_id} not found")


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
