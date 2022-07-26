import json
import sys, os
from collections import defaultdict
from flask import render_template, url_for, make_response, request
sys.path.append(os.path.dirname(__file__))

import gageman
from app import app

DEFAULT_FAVORITES = {
    'version':  0.02,
    'gages': [
        { 'type': 'DWR', 'id': 'PLABAICO'},  # Bailey
        { 'type': 'DWR', 'id': 'BTBLESCO'},  # Big Thompson
        { 'type': 'USGS', 'id': '09128000'},  # Black canyon
        { 'type': 'USGS', 'id': '06719505'},  # Black Rock

        { 'type': 'VIRTUAL', 'id': 'WILDCAT'},
        { 'type': 'WYSEO', 'id': '4578'},  # Blue grass
        { 'type': 'USGS', 'id': '09352900'},  # Vallecito
        { 'type': 'USGS', 'id': '09058000'},  # Gore
    ]
}

CURRENT_FAVS_VER = 0.02

def get_favorite_gages():
    """
    Get users favorite gages from cookie. See DEFAULT_FAVORITES for cookie
    format.

    @returns {list of Gage, bool} gages, bad_cookie - List of favorite gages,
        True if cookie is missing or out of date
    """
    bad_cookie = False
    if 'favorites' in request.cookies:
        favs = json.loads(request.cookies['favorites'])
    else:
        favs = DEFAULT_FAVORITES
        bad_cookie = True

    if 'version' not in favs or float(favs['version']) != CURRENT_FAVS_VER:
        favs = DEFAULT_FAVORITES
        bad_cookie = True

    try:
        gages = [gageman.get_gage(_type=f['type'], _id=f['id']) for f in favs['gages']]
    except ValueError:
        bad_cookie = True
        favs = DEFAULT_FAVORITES
        gages = [gageman.get_gage(_type=f['type'], _id=f['id']) for f in favs['gages']]

    return gages, bad_cookie


@app.route('/snotel')
def snotel():
    return render_template('snotel.html')

@app.route('/flows')
@app.route('/')
@app.route('/index')
def flows():
    gages, bad_cookie = get_favorite_gages()
    rivers = gageman.get_rivers(gages)

    resp = make_response(render_template('favorite_flows.html', rivers=rivers))

    if bad_cookie:
        resp.set_cookie('favorites', json.dumps(DEFAULT_FAVORITES))
    return resp

@app.route('/arkansas')
def arkansas():
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == 'Ark']
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)

@app.route('/front_range')
def front_range():
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == 'FR']
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)

@app.route('/durango')
def durango():
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == 'Durango']
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)

@app.route('/multiday')
def multiday():
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == 'Multi']
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)

@app.route('/central')
def central():
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == 'Central']
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)

@app.route('/west_virginia')
def wv():
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == 'WV']
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)

@app.route('/wyoming')
def wyoming():
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == 'WY']
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)
