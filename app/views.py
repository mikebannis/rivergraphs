from flask import render_template, url_for
from collections import defaultdict
from app import app
import sys, os
sys.path.append(os.path.dirname(__file__))
import gageman


#@app.route('/')
#@app.route('/index')
#def index():
#    return render_template('index.html')

@app.route('/snotel')
def snotel():
    return render_template('snotel.html')

@app.route('/flows')
@app.route('/')
@app.route('/index')
def flows():
    gages = gageman.get_gages()
    rivers = gageman.get_rivers(gages)
    return render_template('flows.html', rivers=rivers)
    # print( url_for('static', filename='06716500.gif'))
    # return '<img src="'+url_for('static', filename='06716500.gif')+'">'

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
