import json
import sys, os
from collections import defaultdict
from flask import render_template, url_for, make_response, request
sys.path.append(os.path.dirname(__file__))

import gageman
from app import app

CURRENT_FAVS_VER = 0.04
DEFAULT_FAVORITES = {
    'version':  CURRENT_FAVS_VER,
    'gages': [
        { 'type': 'DWR', 'id': 'BTBLESCO'},  # Big Thompson
        { 'type': 'USGS', 'id': '09128000'},  # Black canyon
        { 'type': 'VIRTUAL', 'id': 'WILDCAT'},
        { 'type': 'WYSEO', 'id': '4578'},  # Blue grass
        { 'type': 'USGS', 'id': '09352900'},  # Vallecito
        { 'type': 'PRR', 'id': 'PRR'},  # Vallecito

        { 'type': 'USGS', 'id': '06719505'},  # Black Rock
        { 'type': 'DWR', 'id': 'PLABAICO'},  # Bailey
        { 'type': 'USGS', 'id': '09058000'},  # Gore
    ]
}


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
    return render_template('snotel.html.j2')

@app.route('/flows')
@app.route('/')
@app.route('/index')
def flows():
    gages, bad_cookie = get_favorite_gages()
    rivers = gageman.get_rivers(gages)

    resp = make_response(render_template('favorite_flows.html.j2', rivers=rivers))

    if bad_cookie:
        resp.set_cookie('favorites', json.dumps(DEFAULT_FAVORITES))
    return resp

@app.route('/arkansas')
def arkansas():
    return template_for_region('Ark')

@app.route('/front_range')
def front_range():
    return template_for_region('FR')

@app.route('/durango')
def durango():
    return template_for_region('Durango')

@app.route('/multiday')
def multiday():
    return template_for_region('Multi')

@app.route('/central')
def central():
    return template_for_region('Central')

@app.route('/west_virginia')
def wv():
    return template_for_region('WV')

@app.route('/wyoming')
def wyoming():
    return template_for_region('WY')

def template_for_region(region):
    """
    Returned rendered flows template for all rivers in a region

    @param {String} region - region of interest
    @returns {rendered template}
    """
    gages = gageman.get_gages()
    gages = [g for g in gages if g.region == region]
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html.j2', rivers=rivers)
