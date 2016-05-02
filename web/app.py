#!/usr/bin/env python3
import os
from uuid import uuid4
import csv
import time

from flask import Flask, redirect, url_for, request, render_template,make_response,jsonify,session,Response
from pymongo import MongoClient
from flask.ext.session import Session
import pymysql.cursors

import json
from bson import json_util

from config import *
from gpsql.breeder import Breeder





app = Flask(__name__)
breeder = Breeder()

SESSION_TYPE = 'mongodb'
SESSION_MONGODB = MongoClient(os.environ['MONGO_1_PORT_27017_TCP_ADDR'],27017)
app.config.from_object(__name__)
Session(app)



def get_cursor(timeout=3):
    if timeout <1:
        raise Exception("SQL Connection timed out.")
    try:
        conn = pymysql.connect(host="robopreneur_mysql_1",
                           user = "root",
                           passwd = os.environ['MYSQL_ROOT_PASSWORD'],
                           db = os.environ['DATABASE'])
        cursor = conn.cursor()
        return cursor
    except:
        time.sleep(2)
        get_cursor(timeout-1)

cursor = get_cursor(3)



@app.route('/')
def home():
    return make_response(jsonify({'success': 'DNS records check out. Version: 0.10'}), 200)
    """
    if not 'sid' in session or not session['sid']:
        session['sid'] = str(uuid4())
    instance_number = abs(hash(session['sid']))%POPULATION
    #collect products from db with id and parse data
    args = list(range(3531843,3531852))
    sql='SELECT `id`, `name`, `price`, `image_medium_url`,`price_old` FROM merchant_product WHERE id IN (%s)' 
    in_p=', '.join(list(map(lambda x: '%s', args)))
    sql = sql % in_p
    cursor.execute(sql, args)
    products = [dict(zip(['id','name','price','image_medium_url','price_old'],_)) for _ in cursor.fetchall()]
    #raise Exception(products)
    page = render_template('index.html',products=products)
    return page
    """

@app.route('/redirect')
def redirect():
    outbound="http://www.geenstijl.nl"
    return render_template('redirect.html',outbound = outbound)

@app.route("/new_session")
def new_session():
    #raise Exception(dir(session))
    session['sid'] = None
    return redirect(url_for('home'))

@app.route('/dump')
def dump_data():
    #dump all data from mongodb to csv and ship to user
    db = SESSION_MONGODB
    list_sessions = [parse_record(doc) for doc in db.session_tracker.sessions.find()]
    csv = ''.join(list_sessions)
    return Response(csv,
                    mimetype="text/csv",
                    headers={"Content-disposition":"attachment; filename=logs.csv"})

def parse_record(record):
    sid = record[u'sid']
    refreshed = record[u'data'][u'refreshed']
    return "{0},{1}\n".format(sid,refreshed)
   

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True,port=80)
