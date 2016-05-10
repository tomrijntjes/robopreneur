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

SESSION_TYPE = 'mongodb'
SESSION_MONGODB = MongoClient(os.environ['MONGO_1_PORT_27017_TCP_ADDR'],27017)
app.config.from_object(__name__)
Session(app)

breeder = Breeder()



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
    if not 'sid' in session or not session['sid']:
        session['sid'] = str(uuid4())
    #load population
    POPULATION = len(breeder.population)
    instance_number = abs(hash(session['sid']))%POPULATION
    args = breeder.population[instance_number]['ids']
    sql='SELECT `id`, `name`, `price`, `image_small_url`,`image_medium_url`,`image_large_url`,`price_old` FROM gieters WHERE id IN (%s) AND `deleted_at` is NULL LIMIT 9' 
    in_p=', '.join(list(map(lambda x: '%s', args)))
    sql = sql % in_p
    cursor.execute(sql, args)
    products = [dict(zip(['id','name','price','image_small_url','image_medium_url','image_large_url','price_old'],_)) for _ in cursor.fetchall()]
    page = render_template('index.html',products=products,instance=instance_number,session=session['sid'])
    return page

@app.route('/population')
def overview():
    data = list(breeder.mongo.breeder.population.find())
    page = render_template('population.html',pop=data)
    return page
    
@app.route('/tracking/<product_id>')
def track(product_id):
    instance_number = abs(hash(session['sid']))%len(breeder.population)
    breeder.population[instance_number]['energy']+=1
    breeder.update_queue()
    breeder.write_population()
    outbound = "http://shopsaloon.com/product/visit/"+product_id
    return render_template('redirect.html',outbound = outbound)

@app.route("/purge/<pw>")
def purge_data(pw):
    if pw == os.environ['shopsaloon']:
        pass

@app.route("/newsession")
def new_session():
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
