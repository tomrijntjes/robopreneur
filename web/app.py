#!/usr/bin/env python3
import os
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





app = Flask(__name__)

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
        time.sleep(10)
        get_cursor(timeout-1)

cursor = get_cursor(3)



@app.route('/')
def home():
    if not 'sid' in session or not session['sid']:
        session['sid'] = str(uuid4())
    #load population
    pop_size = breeder.mongo.breeder.population.count()
    if pop_size < 10:
        for i in range(10):
            breeder.create_individual() 
        return "Initiating a new population. Have fun."
    instance_number = abs(hash(session['sid']))%int(pop_size*1.25)
    if instance_number<pop_size:
        instance = breeder.instance(instance_number)
        args = instance['ids']
        query = instance['query']
    else:
        #create pseudorandom selection from the entire set
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
    pop = list(breeder.mongo.breeder.population.find())
    click_events = list(breeder.mongo.breeder.click_events.find())
    pop_events = list(breeder.mongo.breeder.events.find())
    page = render_template('population.html',pop=pop,click_events=click_events,pop_events=pop_events)
    return page

@app.route('/dump/<dataset>')
def dump_data(dataset):
    if dataset=='pop':
        data = list(breeder.mongo.breeder.population.find())
    elif dataset=='clicks':
        data = list(breeder.mongo.breeder.click_events.find())
    elif dataset=='events':
        data = list(breeder.mongo.breeder.events.find())



    raise Exception(data)

    csv = ''.join(data)
    return Response(csv,
                    mimetype="text/csv",
                    headers={"Content-disposition":"attachment; filename=logs.csv"})
    
@app.route('/tracking/<product_id>')
def track(product_id):
    pop_size = breeder.mongo.breeder.population.count()
    instance_number = abs(hash(session['sid']))%int(pop_size*1.25)
    if instance_number>pop_size:
        #random page led to conversion event
        start = instance_number%len(breeder.all_ids)
        args = breeder.all_ids[start-9:start]
        breeder.mongo.breeder.click_events.insert_one(  
                {
                'instance_number':'random',
                'datetime':datetime.datetime.now()
                }
            )
    else:
        instance = breeder.instance(instance_number)
        instance['energy']+=1
        breeder.write(instance)
        #log click event
        breeder.mongo.breeder.click_events.insert_one(
            {
            'instance_number':instance_number,
            'datetime':datetime.datetime.now()
            }
        )   
    #update queue
    breeder.update_queue()
    outbound = "http://shopsaloon.com/product/visit/"+product_id
    return render_template('redirect.html',outbound = outbound)

@app.route("/purge/<pw>")
def purge_data(pw):
    if pw == os.environ['DATABASE']:
        breeder.mongo["breeder"].drop_collection('population')
        breeder.mongo["breeder"].drop_collection('click_events')
        breeder.mongo["breeder"].drop_collection('events')
        return 'dropped table'
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
