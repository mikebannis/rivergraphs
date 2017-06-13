from flask import render_template, url_for
from collections import defaultdict
from app import app
import sys, os
sys.path.append(os.path.dirname(__file__))
import gageman

@app.route('/')
@app.route('/index')
def index():
    rivers = gageman.get_rivers()
    return render_template('index.html', rivers=rivers)
    # print( url_for('static', filename='06716500.gif'))
    # return '<img src="'+url_for('static', filename='06716500.gif')+'">'
