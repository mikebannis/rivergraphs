#!/usr/bin/env python3
from __future__ import print_function

import os
import sys
import time
import pytz
import json
import math
import requests
from bs4 import BeautifulSoup
from datetime import timedelta
from datetime import datetime as dt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib import pyplot as plt
from pandas.plotting import register_matplotlib_converters
from dotenv import load_dotenv
import click

load_dotenv()

import gageman
import util
import traceback

register_matplotlib_converters()

LONG_SLEEP = 3  # seconds between pulling gages when called by cron
PLOT_DAYS = 7  # Days to plot on graph

# Extra room at top of custom hydrographs. 1.05 -> 5% extra room above max
GRAPH_TOP_BUFFER = 1.05

USGS_CODE = {
    "feet": "00065",
    "cfs": "00060",
}

USGS_MISSING_VALUE = -999999  # USGS's own "no data" sentinel value

TIMEOUT = 30  # timeout for get requests, in seconds

MEDIAN_CACHE_FILE = "usgs_medians.json"
MEDIAN_CACHE_MAX_AGE = timedelta(days=7)
# Confirmed live: the stat service hard-caps requests at 10 site numbers
# ("the number of siteNo elements input by the user exceeds the maximum
# limit for this web service [max=[10]]" on an 11-site request).
MEDIAN_CHUNK_SIZE = 10

# Some upstream sites block the default python-requests User-Agent, so
# identify as a browser on every request.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 riverproject.co"
    )
}


class URLError(Exception):
    pass


def get_wyseo_gage(gage, outpath, verbose=False):
    """
    Grabs default flow graph for WY State Engineers Office
    e.g. https://seoflow.wyo.gov/Data/DataSet/Chart/Location/014CWT/DataSet/Discharge/Tunnel/Interval/Custom/2022/07/01/2022/08/01

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    assert gage.gage_id == "4578", "This only works for blue grass..."

    utc = pytz.timezone("UTC")
    mtn = pytz.timezone("US/Mountain")
    date_f = "%Y-%m-%dT%H:%M:%SZ"

    start = (dt.now() - timedelta(days=PLOT_DAYS + 1)).strftime("%Y-%m-%d")
    end = (dt.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    if verbose:
        print(f"Getting data for {gage.gage_id} from {start} to {end}")

    data = {
        "sort": "TimeStamp-asc",
        "date": start,
        "endDate": end,
    }
    response = requests.post(
        "https://seoflow.wyo.gov/Data/DatasetGrid?dataset=4578",
        data=data,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    if response.status_code != 200:
        raise URLError(response.status_code, response.text)
    results = response.json()["Data"]

    outfile = os.path.join(outpath, gage.data_file())
    data = ""
    with open(outfile, "wt") as out:
        for result in results:
            q = result["Value"]
            if not util.is_float(q):
                continue

            timestamp = utc.localize(dt.strptime(result["TimeStamp"], date_f))
            timestamp = timestamp.astimezone(mtn)
            timestamp_str = timestamp.strftime("%Y-%m-%d,%H:%M:%S")
            data = f"{q},{timestamp_str}\n"
            out.write(data)

    if verbose:
        print(f"\tWrote {len(results)} results to {outfile}")
        print(f"\tLast result was {data}")

    # --- Plot and save the hydrograph
    raw_qs = [r["Value"] for r in results]
    raw_tss = [utc.localize(dt.strptime(r["TimeStamp"], date_f)).astimezone(mtn) for r in results]
    make_graph(raw_qs, raw_tss, outpath, gage)


def get_dwr_graph(gage: gageman.Gage, outpath: str, verbose=False):
    """
    Grabs default flow graph for Colorado DWR Gage 'gage'

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    response = requests.get(
        gage.data_url(),
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    if response.status_code == 404:
        if response.text == "This URL is properly formatted, but returns zero records from CDSS.":
            print("\tNo records returned from CDSS.")
            return
        else:
            raise URLError(response.status_code, response.text)
    elif response.status_code != 200:
        raise URLError(response.status_code, response.text)
    results = response.json()["ResultList"]

    outfile = os.path.join(outpath, gage.data_file())
    data = ""
    with open(outfile, "wt") as out:
        for result in results:
            q = result["measValue"]
            if not util.is_float(q):
                continue

            timestamp = result["measDateTime"]
            if not "T" in timestamp:
                continue
            date = timestamp.split("T")[0]
            time_part = timestamp.split("T")[1]

            data = f"{q},{date},{time_part}"
            out.write(data + "\n")

    if verbose:
        print(f"\tWrote {len(results)} results to {outfile}")
        print(f"\tLast result was {data}")

    # --- Plot and save the hydrograph
    date_f = "%Y-%m-%dT%H:%M:%S"
    raw_qs = [r["measValue"] for r in results]
    raw_tss = [dt.strptime(r["measDateTime"], date_f) for r in results]
    make_graph(raw_qs, raw_tss, outpath, gage)


def _next_log_tick(value: float, subs) -> float:
    """
    Smallest "sub x 10^n" (n an integer, sub drawn from `subs`) that is
    strictly greater than `value`. Used to guarantee a labeled gridline
    always appears above the highest plotted point on a log-scaled graph,
    rather than letting the peak land flush against the top edge.
    """
    exponent = math.floor(math.log10(value))
    candidates = [s * (10**e) for e in (exponent, exponent + 1) for s in subs]
    above = [c for c in candidates if c > value]
    return min(above) if above else value * 1.1


def make_graph(raw_qs, raw_tss, outpath, gage, medians=None):
    """
    Make a hydro graph and save it

    @param {list of float} raw_qs - list of discharges or stages
    @param {list of Datetime} raw_tss - time stamps for readings
    @param {str} outpath - the static dir
    @param {gageman.Gage} gage - the gage the graph is for
    @param {dict | None} medians - optional {"years": int, "values": {"M-D":
        float}} historical daily-median overlay (USGS cfs gages only)
    """
    # only show last PLOT_DAYS days and drop other dirty data
    qs = []
    tss = []
    delta = timedelta(days=PLOT_DAYS)
    for q, ts in zip(raw_qs, raw_tss):
        # Filter by date
        if raw_tss[-1] - ts > delta:
            continue

        # Ensure it's not None
        if q is None:
            continue

        # Convert to float and filter out NaNs or invalid strings
        try:
            val = float(q)
            if not math.isnan(val):
                qs.append(val)
                tss.append(ts)
        except (TypeError, ValueError):
            pass

    fmt = mdates.DateFormatter("%b\n%d")  # May\n5
    _, ax = plt.subplots(1, figsize=(5.76, 3.84), dpi=100)

    if len(qs) == 0 or len(tss) == 0:
        print(f"No data to plot for {gage}")

    ax.plot(tss, qs, label="Discharge")

    overlay_vals = []
    if medians and medians.get("values") and len(tss) > 0:
        values = medians["values"]
        overlay_dates = []
        day = tss[0].date()
        last_day = tss[-1].date()
        while day <= last_day:
            key = f"{day.month}-{day.day}"
            if key in values:
                # match type with tss (datetime, not date) so both series
                # share the same x-axis unit conversion
                overlay_dates.append(dt.combine(day, dt.min.time()))
                overlay_vals.append(values[key])
            day += timedelta(days=1)

        if overlay_dates:
            ax.plot(
                overlay_dates,
                overlay_vals,
                marker="^",
                markersize=6,
                markerfacecolor="none",
                markeredgecolor="tan",
                markeredgewidth=1.2,
                linestyle="none",
                zorder=3,
                label=f"Median daily statistic ({medians['years']} years)",
            )
            ax.legend(loc="best", fontsize="small")

    # Setting ymax to 0 throws a warning, use 1 instead
    max_q = max(qs) if len(qs) > 0 else 1
    if overlay_vals:
        max_q = max(max_q, max(overlay_vals))

    # USGS cfs gages (the ones with a median overlay) get a log y-axis,
    # matching the old USGS-scraped graph's style. A log axis can't show
    # zero/negative values, so the lower bound comes from the smallest
    # positive value instead of 0, with the same GRAPH_TOP_BUFFER ratio
    # applied as padding below it (dividing, not subtracting, since equal
    # visual padding on a log scale means equal ratios, not equal amounts).
    # min_q/max_q are derived only from positive values here -- a reading
    # can carry USGS's -999999 "no data" sentinel (or similar garbage) that
    # slipped past upstream filtering, and log10() of a non-positive number
    # crashes outright, so if there's no positive data at all, fall back to
    # the ordinary linear axis below instead.
    positive_vals = [v for v in qs + overlay_vals if v > 0]
    if medians and medians.get("values") and positive_vals:
        ax.set_yscale("log")
        min_q = min(positive_vals)
        max_q = max(positive_vals)

        # matplotlib's default log-axis ticks are sparse and use scientific
        # notation (e.g. "6x10^2"). USGS's own graphs instead show plain,
        # human-readable numbers with a gridline at each. Tick density
        # adapts to how many decades the data spans, so a narrow range
        # (e.g. 200-600) gets every 1-9 x 10^n (dense, still readable) while
        # a wide range (e.g. 50-2000+) falls back to a coarser "nice number"
        # set -- forcing full 1-9 density regardless of range overlaps
        # labels (e.g. "90" and "100" on top of each other) on wide-range
        # gages.
        decades = math.log10(max_q / min_q) if min_q > 0 else 1
        if decades <= 1.2:
            subs = range(1, 10)
        elif decades <= 2.5:
            subs = (1, 2, 3, 5, 7)
        else:
            subs = (1, 2, 5)

        # Always leave a labeled gridline visible above the highest plotted
        # point (discharge or median marker, whichever is taller) -- the
        # flat GRAPH_TOP_BUFFER headroom alone doesn't guarantee the next
        # "nice" tick actually falls within it, which left the peak flush
        # against the top edge with nothing labeled above it.
        top_tick = _next_log_tick(max_q, subs)
        ymax = max(max_q, top_tick) * GRAPH_TOP_BUFFER
        ax.set_ylim(ymin=min_q / GRAPH_TOP_BUFFER, ymax=ymax)

        ax.yaxis.set_major_locator(mticker.LogLocator(base=10, subs=subs))
        ax.yaxis.set_minor_locator(mticker.NullLocator())
        ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    else:
        ax.set_ylim(ymin=0, ymax=max_q * GRAPH_TOP_BUFFER)
    ax.xaxis.set_major_formatter(fmt)
    plt.grid(visible=True)

    i_outfile = os.path.join(outpath, gage.image_file())
    plt.savefig(i_outfile)
    plt.close()


def get_usgs_gages(gages: list, outpath: str, verbose: bool = False) -> None:
    """
    Grabs flow data for a batch of USGS Gage objects in a single HTTP
    request, then writes each gage's .cfs file and renders its hydrograph.

    USGS's legacy IV webservice discourages one-request-per-site use, so
    this fetches every site + the union of parameter codes they need in one
    call. Documented caps: 100 sites, 100 parameterCd values. URL builder:
    https://waterservices.usgs.gov/rest/IV-Test-Tool.html

    param: gages - list of gageman.Gage instances, all gage_type == "USGS"
    param: outpath - path to output dir
    param: {bool} verbose - print debug text if True
    """
    if not gages:
        return

    # USGS caps this request at 100 sites; warn loudly well before that so
    # it's never discovered via silently-dropped sites in production.
    if len(gages) > 90:
        click.echo(
            f"\tWARNING: {len(gages)} USGS gages in this batch, approaching "
            "USGS's 100-site-per-request cap. Sites beyond the cap are "
            "silently dropped from the response, not errored -- add "
            "chunking before this reaches 100.",
            err=True,
        )

    # str() is required: gages.yaml parses some unquoted numeric gage_ids
    # (e.g. 13181000) as Python int, but the API's siteCode is always a
    # string -- an int key here would silently make that gage unmatchable.
    site_ids = [str(g.gage_id) for g in gages]
    codes = sorted({USGS_CODE[g.units] for g in gages})

    url = (
        f"https://waterservices.usgs.gov/nwis/iv/?sites={','.join(site_ids)}&"
        f"parameterCd={','.join(codes)}&period=P{PLOT_DAYS}D&siteStatus=all&format=json"
    )
    if verbose:
        print(f"Getting batched USGS data for {len(gages)} gages (codes={codes})")

    resp = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise ValueError(f"Bad response ({resp.status_code}) from {url}, got: " f'"{resp.text}"')

    # Index by (site_id, parameter_code) -> list of {"value", "dateTime", ...}
    lookup = {}
    for ts in resp.json()["value"]["timeSeries"]:
        site = ts["sourceInfo"]["siteCode"][0]["value"]
        code = ts["variable"]["variableCode"][0]["value"]
        lookup[(site, code)] = ts["values"][0]["value"]

    # Historical daily-median overlay data (cfs gages only); cached on disk,
    # so this is a no-op most runs. Isolated in its own try/except so any
    # unexpected failure here can never take down the primary USGS batch
    # (verbose mode otherwise lets exceptions from this function propagate).
    try:
        medians_lookup = _load_usgs_medians(gages, outpath, verbose=verbose)
    except Exception as e:
        click.echo(
            f"\tWARNING: failed to load USGS medians, continuing without overlay: {e}", err=True
        )
        medians_lookup = {}

    date_f = "%Y-%m-%dT%H:%M:%S"

    # Per-gage error isolation: one gage missing/malformed from the batch
    # response must not abort the rest. USGS silently omits unknown/offline
    # sites from the response instead of erroring, so this is required, not
    # just defensive.
    for gage in gages:
        try:
            site_id = str(gage.gage_id)
            code = USGS_CODE[gage.units]
            results = lookup.get((site_id, code))
            if not results:
                click.echo(
                    f"\tWARNING: no data for USGS {site_id} (param {code}) in batch, skipping",
                    err=True,
                )
                continue

            if verbose:
                print(f"\tGot {len(results)} results for {site_id}. Latest: {results[-1]}")

            raw_qs = []
            raw_tss = []
            outfile = os.path.join(outpath, gage.data_file())
            with open(outfile, "wt") as out:
                for result in results:
                    value = result["value"]
                    timestamp = result["dateTime"]
                    date = timestamp.split("T")[0]
                    time_part = timestamp.split("T")[1].split("-")[0].split(".")[0]
                    out.write(f"{value},{date},{time_part}\n")

                    # -999999 is USGS's own "no data" sentinel (seen paired
                    # with a "Ssn" qualifier on seasonally-operated gages);
                    # it's a valid float so util.is_float() alone won't
                    # catch it, and left in it wrecks both the y-axis scale
                    # and the log-scale math below.
                    if util.is_float(value) and float(value) != USGS_MISSING_VALUE:
                        raw_qs.append(float(value))
                        raw_tss.append(dt.strptime(f"{date}T{time_part}", date_f))

            # --- Plot and save the hydrograph
            gage_medians = medians_lookup.get(site_id) if gage.units == "cfs" else None
            make_graph(raw_qs, raw_tss, outpath, gage, medians=gage_medians)
        except Exception as e:
            click.echo(f"\tError processing USGS gage {gage.gage_id} from batch: {e}", err=True)
            if verbose:
                traceback.print_exc()
            continue


def _load_usgs_medians(gages: list, outpath: str, verbose: bool = False) -> dict:
    """
    Load (or refresh) cached long-term daily median discharge statistics for
    USGS cfs gages, for use as a historical-reference overlay on their
    hydrographs.

    USGS only computes long-term daily statistics for discharge (parameterCd
    00060), not stage/gage-height, so this intentionally only covers the
    subset of USGS gages with units == "cfs" -- feet-unit gages are filtered
    out here, not just left to return empty by the API.

    This data represents decades of record and does not meaningfully change
    day-to-day, so it is cached to disk in outpath and only refreshed every
    MEDIAN_CACHE_MAX_AGE; most cron runs do zero network calls for this.

    @param gages - list of gageman.Gage, any gage_type/units mix (non-USGS
        and non-cfs gages are filtered out internally)
    @param outpath - static dir to read/write the cache file
    @param verbose - print debug text if True
    @returns {site_id (str): {"years": int, "values": {"M-D": float}}}
             keyed only by sites that actually have long-term record data
    """
    cfs_gages = [g for g in gages if g.gage_type == "USGS" and g.units == "cfs"]
    if not cfs_gages:
        return {}

    cache_file = os.path.join(outpath, MEDIAN_CACHE_FILE)
    if os.path.exists(cache_file):
        age = dt.now() - dt.fromtimestamp(os.path.getmtime(cache_file))
        if age < MEDIAN_CACHE_MAX_AGE:
            try:
                with open(cache_file, "rt") as f:
                    cached = json.load(f)
                if verbose:
                    print(f"\tUsing cached USGS medians ({cache_file}, age {age})")
                return cached
            except (ValueError, OSError) as e:
                click.echo(
                    f"\tWARNING: could not read median cache {cache_file}: {e}, refetching",
                    err=True,
                )
        elif verbose:
            print(f"\tUSGS median cache is stale (age {age}), refreshing")

    # str() required: gages.yaml parses some numeric gage_ids (e.g.
    # 13181000) as Python int -- same gotcha as get_usgs_gages.
    site_ids = [str(g.gage_id) for g in cfs_gages]

    medians: dict = {}
    for i in range(0, len(site_ids), MEDIAN_CHUNK_SIZE):
        chunk = site_ids[i : i + MEDIAN_CHUNK_SIZE]
        if i > 0:
            time.sleep(LONG_SLEEP)

        url = (
            "https://waterservices.usgs.gov/nwis/stat/?sites="
            + ",".join(chunk)
            + "&statReportType=daily&statTypeCd=median&parameterCd=00060&format=rdb"
        )
        if verbose:
            print(f"\tFetching USGS medians for {len(chunk)} sites")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                click.echo(
                    f"\tWARNING: bad response ({resp.status_code}) fetching USGS "
                    f"medians for {chunk}, skipping this chunk",
                    err=True,
                )
                continue
            _parse_median_rdb(resp.text, medians)
        except Exception as e:
            click.echo(f"\tWARNING: error fetching USGS medians for {chunk}: {e}", err=True)
            continue

    # Only persist (and thus only start the 7-day clock) if we actually got
    # something -- a transient total outage must not poison the cache with
    # an empty result and silently disable the overlay for a week.
    if medians:
        try:
            with open(cache_file, "wt") as f:
                json.dump(medians, f)
            if verbose:
                print(f"\tWrote medians for {len(medians)} sites to {cache_file}")
        except OSError as e:
            click.echo(f"\tWARNING: could not write median cache {cache_file}: {e}", err=True)
    else:
        click.echo("\tWARNING: got zero USGS median data this run, not caching", err=True)

    return medians


def _parse_median_rdb(text: str, medians: dict) -> None:
    """
    Parse one RDB response from the USGS stat (daily median) service and
    merge its rows into `medians` in place:
      {site_id: {"years": int, "values": {"M-D": float}}}

    Data rows are tab-delimited and start with literal "USGS"; everything
    else (comments starting with '#', the header row, the field-type-code
    row) is skipped by checking fields[0] == "USGS", regardless of exact
    line count/order. Field order (0-indexed): agency_cd, site_no,
    parameter_cd, ts_id, loc_web_ds, month_nu, day_nu, begin_yr, end_yr,
    count_nu, p50_va.
    """
    for line in text.splitlines():
        fields = line.split("\t")
        if not fields or fields[0] != "USGS":
            continue
        try:
            site_id = fields[1]
            month_nu = int(fields[5])
            day_nu = int(fields[6])
            begin_yr = int(fields[7])
            end_yr = int(fields[8])
            p50_va = fields[10]
        except (IndexError, ValueError):
            continue
        if not util.is_float(p50_va):
            continue

        entry = medians.setdefault(site_id, {"years": 0, "values": {}})
        # begin_yr/end_yr vary slightly row-to-row for the same site (gaps
        # in the record) -- use the longest span seen as the more
        # representative "years of record" for this site's legend label.
        entry["years"] = max(entry["years"], end_yr - begin_yr + 1)
        entry["values"][f"{month_nu}-{day_nu}"] = float(p50_va)


def get_nsv_gage(gage, outpath, verbose=False):
    """
    Determine NSV flow above button rock by determining rate of change of
    volume in button rock and adding to discharge downstream. Assume 1 cfs ==
    1/12 ac-ft/hr
    """
    import pandas as pd

    # Proving grounds q - find average flow per hour
    pgq_g = gageman.get_gage("NSVBBRCO", "DWR")
    pgq = pgq_g.series.groupby(pd.Grouper(freq=pd.Timedelta(hours=1))).mean()

    # Button rock dam af-ft
    braf_g = gageman.get_gage("BRKDAMCO", "DWR")
    # This probably doesn't need to be averaged, but doesn't really hurt either
    braf = braf_g.series.groupby(pd.Grouper(freq=pd.Timedelta(hours=1))).mean()

    # Calculate approx inflow
    nsvq = braf.diff() * 12 + pgq

    # clip to last 7 days and chop off fake peaks
    mask = nsvq.index > dt.today() - timedelta(days=PLOT_DAYS)
    nsvq = nsvq[mask]
    nsvq = nsvq[nsvq < nsvq.median() * 4]

    make_graph(nsvq.values, nsvq.index, outpath, gage)

    datafile = os.path.join(outpath, gage.data_file())
    with open(datafile, "wt") as f:
        date = nsvq.index[-1].strftime("%Y-%m-%d")
        time_part = nsvq.index[-1].strftime("%H:%M:%S")
        f.write(f"{nsvq.iloc[-1]},{date},{time_part}\n")


def get_foxton_gage(gage, outpath, verbose=False):
    """
    Determine foxton gage as waterton - deckers
    """
    import pandas as pd

    waterton = gageman.get_gage("PLASPLCO", "DWR").series
    deckers = gageman.get_gage("06701900", "USGS").series
    foxton = (waterton - deckers).dropna()

    if foxton.size <= 0:
        raise ValueError("No data points calculated for foxton!")

    # clip to last 7 days
    mask = foxton.index > dt.today() - timedelta(days=PLOT_DAYS)
    foxton = foxton[mask]

    make_graph(foxton.values, foxton.index, outpath, gage)

    datafile = os.path.join(outpath, gage.data_file())
    with open(datafile, "wt") as f:
        date = foxton.index[-1].strftime("%Y-%m-%d")
        time_part = foxton.index[-1].strftime("%H:%M:%S")
        f.write(f"{foxton.iloc[-1]},{date},{time_part}\n")


def get_wildcat_gage(gage, outpath, verbose=False):
    """
    Determine wildcat gage as above cheesman - tarryall
    """
    import pandas as pd

    cheesman = gageman.get_gage("06700000", "USGS").series
    tarryall = gageman.get_gage("TARTARCO", "DWR").series
    wildcat = (cheesman - tarryall).dropna()

    if wildcat.size <= 0:
        raise ValueError("No data points calculated for wildcat!")

    # clip to last 7 days
    mask = wildcat.index > dt.today() - timedelta(days=PLOT_DAYS)
    wildcat = wildcat[mask]

    make_graph(wildcat.values, wildcat.index, outpath, gage)

    datafile = os.path.join(outpath, gage.data_file())
    with open(datafile, "wt") as f:
        date = wildcat.index[-1].strftime("%Y-%m-%d")
        time_part = wildcat.index[-1].strftime("%H:%M:%S")
        f.write(f"{wildcat.iloc[-1]},{date},{time_part}\n")


def get_prr_gage(gage, outpath, verbose=False):
    """
    Grabs default flow graph for the Poudre rock report and write image to
    outfile.

    param: gage - gageman.Gage instance
    prarm: outpath - path to output dir
    """
    # TODO - look for urllib3.exceptions.NewConnectionError
    response = requests.get(
        gage.data_url(),
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    # Verify we got good stuff back
    if response.status_code != 200:
        raise URLError(response.status_code, response.text)

    soup = BeautifulSoup(response.text, "html.parser")
    headers = soup.find_all(class_="entry-header")

    # Hazard or accident headers won't match the rock report format, try all headers
    meta, time_part = None, None
    for header in headers:
        try:
            # Get the stage and time from header text, e.g. 'Pine View 3.4 at 0700'
            stage = header.find("a").getText().split(" ")[2].replace("+", "").replace("-", "")
            time_part = header.find("a").getText().split(" ")[4]

            # Get date, e.g. 'May 31, 2022 By Camp Falbo '
            meta = header.find("p").getText().split(",")
            mmm_dd = meta[0]
            year = meta[1].strip().split(" ")[0]
            ts = dt.strptime(f"{mmm_dd} {year} {time_part}", "%B %d %Y %H%M")
            break
        except (IndexError, ValueError):
            pass

    if meta is None or time_part is None:
        print(f"Error pulling PRR: meta={meta}, time_part={time_part}")
        return

    data = "{},{},{}".format(stage, ts.date(), ts.time())

    # grab last line of data file if it exists
    datafile = os.path.join(outpath, gage.data_file())
    if os.path.exists(datafile):
        old_data = ""
        with open(datafile, "rt") as f:
            for old_data in f:
                pass

        # If it's the same data point, don't do anything else
        if old_data.strip() == data.strip():
            if verbose:
                print(f"\tData received is same as in data file: {old_data.strip()}")
            return

    if verbose:
        print(f"\tWriting {data} to {datafile}")
    with open(datafile, "at") as out:
        out.write(data + "\n")

    raw_stages = []
    raw_tss = []
    with open(datafile, "rt") as f:
        for line in f:
            fields = line.strip().split(",")
            try:
                raw_stages.append(float(fields[0]))
            except ValueError:
                print(f'\tCorrupt line found in {datafile}: "{line.strip()}"')
                continue
            ts = dt.strptime(f"{fields[1]} {fields[2]}", "%Y-%m-%d %H:%M:%S")
            raw_tss.append(ts)

    make_graph(raw_stages, raw_tss, outpath, gage)


def _process_gages(gages: list, outpath: str, verbose: bool) -> None:
    """Process a list of gages and download their data.

    :param gages: List of Gage objects to process
    :param outpath: Output directory path
    :param verbose: Whether to print verbose output
    """
    if len(gages) == 0:
        click.echo("No matching gages found!!!")
        sys.exit(1)

    usgs_gages = [g for g in gages if g.gage_type == "USGS"]
    other_gages = [g for g in gages if g.gage_type != "USGS"]

    # Batch-fetch USGS first so VIRTUAL gages below (which read already-
    # on-disk USGS .cfs files) see freshly updated data from this run.
    if usgs_gages:
        if verbose:
            click.echo(f"*** working on {len(usgs_gages)} USGS gages (batched)")
            get_usgs_gages(usgs_gages, outpath, verbose=verbose)
            click.echo("\tsuccess")
        else:
            try:
                get_usgs_gages(usgs_gages, outpath, verbose=verbose)
            except Exception as e:
                click.echo(f"\tError getting batched USGS data: {e}", err=True)
                traceback.print_exc()

    for i, gage in enumerate(other_gages):
        if i > 0 and not verbose:
            time.sleep(LONG_SLEEP)

        if verbose:
            click.echo(f"*** working on {gage.gage_type} gage: {gage}")

        # Determine gage getter function
        if gage.gage_type == "DWR":
            getter = get_dwr_graph
        elif gage.gage_type == "PRR":
            getter = get_prr_gage
        elif gage.gage_type == "WYSEO":
            getter = get_wyseo_gage
        elif gage.gage_type == "VIRTUAL" and gage.gage_id == "NSV":
            getter = get_nsv_gage
        elif gage.gage_type == "VIRTUAL" and gage.gage_id == "FOXTON":
            getter = get_foxton_gage
        elif gage.gage_type == "VIRTUAL" and gage.gage_id == "WILDCAT":
            getter = get_wildcat_gage
        else:
            click.echo(f'ERROR: unknown gage: "{gage.gage_type}" "{gage.gage_id}"')
            continue

        # If verbose, we're running interactively. Allow exceptions to propagate
        if verbose:
            getter(gage, outpath, verbose=verbose)
            click.echo("\tsuccess")
            continue

        # Running from cron. Catch exceptions and move on
        try:
            getter(gage, outpath, verbose=verbose)
        except Exception as e:
            click.echo(f"\tError getting {gage.gage_type} {gage.gage_id}: {e}", err=True)
            traceback.print_exc()
            continue


@click.command()
@click.option(
    "--type",
    type=click.Choice(["dwr", "usgs", "prr", "wyseo", "virtual"], case_sensitive=False),
    help="Filter gages by type",
)
@click.option(
    "-i",
    "--id",
    multiple=True,
    help="Download data for specific gage ID(s). Can be used multiple times.",
)
@click.option("--reverse", is_flag=True, help="Process gages in reverse order")
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose output",
)
def main(type: str, id: tuple, reverse: bool, verbose: bool) -> None:
    """Download gage data and generate graphs."""
    if type and id:
        raise click.UsageError("Cannot use --type and --id together")

    gages = gageman.get_gages()

    if type:
        gages = [g for g in gages if g.gage_type.lower() == type.lower()]
        verbose = True
    elif id:
        gages = [g for g in gages if str(g.gage_id) in id]
        verbose = True
    elif reverse:
        gages = gages[::-1]
        verbose = True

    outpath = util.static_dir()
    _process_gages(gages, outpath, verbose)


if __name__ == "__main__":
    main()
