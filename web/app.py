#!/usr/bin/env python3
import os
import sys
import logging
import logging.handlers
from uuid import uuid4
import csv
import time
import random
import datetime

from flask import Flask, redirect, url_for, request, render_template,make_response,jsonify,session,Response
from pymongo import MongoClient
from flask.ext.session import Session
import pymysql.cursors

import json
from bson import json_util

from config import *
from gpsql.breeder import Breeder
from loggmail import TlsSMTPHandler




app = Flask(__name__)


logger = logging.getLogger()     
gm = TlsSMTPHandler(("smtp.gmail.com", 587), 'rijntjeslogging@gmail.com', ['tomrijntjes@gmail.com'], 'Error found!', ('rijntjeslogging@gmail.com', os.environ['MYSQL_ROOT_PASSWORD']))
gm.setLevel(logging.ERROR)
logger.addHandler(gm)

SESSION_TYPE = 'mongodb'
SESSION_MONGODB = MongoClient(os.environ['MONGO_1_PORT_27017_TCP_ADDR'],27017)
app.config.from_object(__name__)
Session(app)

breeder = Breeder()

random.seed(10)



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
        time.sleep(20)
        get_cursor(timeout-1)

cursor = get_cursor(3)



@app.route('/')
def home():
    new_session = False
    if not 'sid' in session or not session['sid']:
        session['sid'] = str(uuid4()) 
        new_session = True
    #load population
    pop_size = breeder.mongo.breeder.population.count()
    instance_number = abs(hash(session['sid']))%int(pop_size*1.25)
    #log session
    if instance_number<pop_size:
        if new_session:
            instance = breeder.instance(instance_number)
            instance['energy']-=0.025
            breeder.write(instance)
            if instance['energy']<=0:
                session['sid'] = None   
                return redirect(url_for('home'))
            SESSION_MONGODB.flask_session.events.insert_one(
                {
                'sid':session['sid'],
                'instance':abs(hash(session['sid']))%int(pop_size*1.25),
                'datetime':datetime.datetime.now(),
                'energy_change':-0.025
                }
            )
            breeder.write(instance)
        instance = breeder.instance(instance_number)
        args = instance['ids']
        query = instance['query']
    else:
        #create pseudorandom selection from the entire set
        SESSION_MONGODB.flask_session.events.insert_one(
                {
                'sid':session['sid'],
                'instance':'control',
                'datetime':datetime.datetime.now()
                }
            )
        query = None
        start = instance_number%len(breeder.all_ids)
        args = breeder.all_ids[start-9:start]
    if len(args)<1:
        return render_template('emptyset.html',instance=instance_number,sql=query)
    sql='SELECT `id`, `name`, `price`, `image_small_url`,`image_medium_url`,`image_large_url`,`price_old` FROM gieters WHERE id IN (%s) AND `deleted_at` is NULL' 
    in_p=', '.join(list(map(lambda x: '%s', args)))
    sql = sql % in_p
    cursor.execute(sql, args)
    products = list(cursor.fetchall())
    while len(products)>9:
        products.pop(instance_number%len(products))
    productset = [dict(zip(['id','name','price','image_small_url','image_medium_url','image_large_url','price_old'],_)) for _ in products]
    page = render_template('index.html',products=productset,instance=instance_number,sql=query,session=session['sid'],numberofproducts=len(products))
    return page

@app.route('/population')
def overview():
    pop = list(breeder.mongo.breeder.population.find().sort("_id", 1))
    click_events = list(breeder.mongo.breeder.click_events.find().sort("_id", -1).limit(10))
    pop_events = list(breeder.mongo.breeder.events.find().sort("_id", -1))
    sessions = list(SESSION_MONGODB.flask_session.events.find().sort("_id", -1).limit(10))
    page = render_template('population.html',pop=pop,click_events=click_events,pop_events=pop_events,sessions=sessions)
    return page

@app.route('/dump/<dataset>')
def dump_data(dataset):
    if dataset=='pop':
        data = list(breeder.mongo.breeder.population.find().sort("_id", 1))
    elif dataset=='sessions':
        data = list(SESSION_MONGODB.flask_session.events.find().sort("_id", -1))
    elif dataset=='clicks':
        data = list(breeder.mongo.breeder.click_events.find())
    elif dataset=='events':
        data = list(breeder.mongo.breeder.events.find())
    header = [';'.join(list(data[0].keys()))]
    values = [';'.join(str(v) for v in _.values()) for _ in data]
    data = header+values
    csv = '\r\n'.join(data)
    return Response(csv,
                    mimetype="text/csv",
                    headers={"Content-disposition":"attachment; filename={0}.csv".format(dataset)})
    
@app.route('/tracking/<product_id>/<price>/<instance>')
def track(product_id,price,instance):
    pop_size = breeder.mongo.breeder.population.count()
    instance_number = int(instance)
    if instance_number>pop_size:
        #random page led to conversion event
        start = instance_number%len(breeder.all_ids)
        args = breeder.all_ids[start-9:start]
        breeder.mongo.breeder.click_events.insert_one(  
                {
                'instance_number':'random',
                'datetime':datetime.datetime.now(),
                'product':product_id

                }
            )
    else:
        instance = breeder.instance(instance_number)
        instance['energy']+=0.0025*float(price)
        breeder.write(instance)
        #log click event
        breeder.mongo.breeder.click_events.insert_one(
            {
            'instance_number':instance_number,
            'datetime':datetime.datetime.now(),
            'energy_change':0.0025*float(price),
            'product':product_id
            }
        )   
    #update queue
    breeder.update_queue()
    outbound = "http://shopsaloon.com/product/visit/"+product_id
    return redirect(outbound,code=302)
    #return render_template('redirect.html',outbound = outbound)

@app.route("/purge/<pw>")
def purge_data(pw):
    if pw == os.environ['MYSQL_ROOT_PASSWORD']:
        breeder.mongo["breeder"].drop_collection('population')
        breeder.mongo["breeder"].drop_collection('click_events')
        breeder.mongo["breeder"].drop_collection('events')
        SESSION_MONGODB.flask_session.drop_collection('events')
        for i in range(20):
            breeder.create_individual() 
        return 'Fresh population. Have fun!'
    return 'Nothing happened'

@app.route("/newsession")
def new_session():
    session['sid'] = None   
    return redirect(url_for('home'))



def parse_record(record):
    sid = record[u'sid']
    refreshed = record[u'data'][u'refreshed']
    return "{0},{1}\n".format(sid,refreshed)
   

if __name__ == "__main__":
    #app.run(host='0.0.0.0', debug=os.environ['DEBUG'],port=80)
    app.run()
