#!/usr/bin/env python3
import random
import operator
import itertools
import numpy
import re
import os
import pickle
import time
import datetime


from deap import algorithms
from deap import base
from deap import creator
from deap import tools
from deap import gp

from pymongo import MongoClient
from bson.binary import Binary
from bson.objectid import ObjectId

import pymysql.cursors

from gpsql.modifiedgrow import genGrow


class Breeder:
	"""
	Shelve class holding a population.
	"""
	def __init__(self,n=50,threshold=0.75,reproduction_cost=0.25):
		self.queue = list()
		self.threshold = threshold
		self.reproduction_cost = reproduction_cost
		self.pset = gp.PrimitiveSetTyped("main", [], bool)
		self.pset.addPrimitive(operator.and_, [bool, bool], bool)
		self.pset.addPrimitive(operator.or_, [bool, bool], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addEphemeralConstant("rand40", lambda: round(random.random() * 40,2), float)
		self.pset.addTerminal('price',float)
		self.pset.addTerminal('price_old',float)
		self.pset.addTerminal('volume',float)
		self.pset.addTerminal('colourfulness',float)
		self.creator = creator
		self.creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
		self.creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMin,
			   pset=self.pset)
		self.toolbox = base.Toolbox()
		self.toolbox.register("expr", genGrow, pset=self.pset, min_=0, max_=6,type_=bool)
		self.toolbox.register("individual", tools.initIterate, creator.Individual,
					self.toolbox.expr)
		self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
		self.toolbox.register("evaluate", self.fitness)
		self.toolbox.register("select", tools.selTournament, tournsize=3)
		self.toolbox.register("mate", gp.cxOnePoint)
		self.toolbox.register("expr_mut", genGrow, min_=0, max_=2)
		self.toolbox.register("mutate", gp.mutUniform, expr=self.toolbox.expr_mut, pset=self.pset)
		self.mongo = MongoClient(os.environ['MONGO_1_PORT_27017_TCP_ADDR'],27017)
		self.get_cursor(3)
		self.cursor.execute('SELECT id FROM gieters')
		self.all_ids = [value[0] for value in self.cursor.fetchall()]
		self.update_queue()

	def __iter__(self):
		return iter((self.parse_query(str(_['genome'])) for _ in self.population))

	def __enter__(self):
		return self

	def create_individual(self,parent1=None,parent2=None):
		highest_id_indi = self.mongo.breeder.population.find_one(sort=[("instance_number", -1)])
		if highest_id_indi is None:
			next_id = 0
		else:
			next_id = highest_id_indi['instance_number']+1
		if not parent1 and not parent2:
			genome1,genome2 = self.toolbox.population(n=2)
			self.mongo.breeder.events.insert_one(
					{
						'type':'birth',
						'datetime':datetime.datetime.now(),
						'instance_number':next_id,
						'parent1':None,
						'parent2':None
					}
			)
		else:
			#reduce energy of parents by reproduction costs
			parent1['energy']-=self.reproduction_cost
			parent2['energy']-=self.reproduction_cost
			self.write(parent1)
			self.write(parent2)
			genome1,genome2 = parent1['genome'],parent2['genome']
			self.mongo.breeder.events.insert_one(
					{
						'type':'birth',
						'datetime':datetime.datetime.now(),
						'instance_number':next_id,
						'parent1':parent1['instance_number'],
						'parent2':parent2['instance_number']
					}
			)
		genome = self.toolbox.mate(genome1,genome2)[0]
		query,ids=self.evaluate(genome)
		self.mongo.breeder.population.insert_one(
					{
						'energy':0.5,
						'genome': Binary(pickle.dumps(genome)),
						'query':query,
						'ids':ids,
						'instance_number':next_id
					}
					)

		return {'genome':genome,'energy':10,'query':query,'ids':ids,'instance_number':next_id}

	def __exit__( self, exc_type, exc_val, exc_tb):
		self.mongo.close()
		self.conn.close()

	def fitness(self,genome):
		return abs(len(self.evaluate(genome)[1])-10),


	def evaluate(self,genome):
		#parse query and get fenotype
		query = "SELECT id FROM gieters WHERE "+self.parse_query(str(genome))
		self.cursor.execute(query)
		ids = 	[value[0] for value in self.cursor.fetchall()]
		return query,ids

	def update_queue(self):
		individuals = [self.read(entry) for entry in self.mongo.breeder.population.find()]
		fertile = [i for i in individuals if i['energy']>self.threshold]
		while len(fertile)>=2:
			parent1,parent2,fertile=fertile[0],fertile[1],fertile[2:]
			self.create_individual(parent1,parent2)

	def write(self,p):
		self.mongo.breeder.population.update_one(
		{'_id':ObjectId(p['mongo_id'])},
			{
				"$set": {
				'energy':p['energy'],
				'genome': Binary(pickle.dumps(p['genome'])),
				'query':p['query'],
				'ids':p['ids'],
				'instance_number':p['instance_number']
				}
			},
			upsert=True
			)

	def read(self,p):
		genome=pickle.loads(p['genome'])
		return {
			'genome':genome,
			'energy':p['energy'],
			'query':p['query'],
			'ids':p['ids'],
			'instance_number':p['instance_number'],
			'mongo_id':p['_id']
			}
			
	def instance(self,instance_number):
		return self.read(self.mongo.breeder.population.find_one(
			{'instance_number':instance_number}))




	def parse_query(self,query):
		if query[:3] == 'or_':
			chunks = self.chunk(query[4:])
			return '('+self.parse_query(chunks[0]) +') OR (' +self.parse_query(chunks[1])+')'
		elif query[:4] == 'and_':
			chunks = self.chunk(query[5:])
			return '('+self.parse_query(chunks[0]) +') AND (' +self.parse_query(chunks[1])+')'
		elif query[:2] == 'lt':
			chunks = self.chunk(query[3:])
			return self.parse_query(chunks[0]) +' < ' +self.parse_query(chunks[1])
		elif query[:2] == 'eq':
			chunks = self.chunk(query[3:])
			return self.parse_query(chunks[0]) +' = ' +self.parse_query(chunks[1])
		return query.strip("'")


	def chunk(self,inputstr):
		closure = 0
		for i in range(len(inputstr)):
			if inputstr[i] == '(':
				closure +=1
			elif inputstr[i] == ')':
				closure -=1
			elif closure==0 and inputstr[i] == ',':
				return (inputstr[:i],inputstr[i+2:-1])

	def get_cursor(self,timeout=3):
	    if timeout <1:
	        raise Exception("SQL Connection timed out.")
	    try:
	        self.conn = pymysql.connect(host="robopreneur_mysql_1",
	                           user = "root",
	                           passwd = os.environ['MYSQL_ROOT_PASSWORD'],
	                           db = os.environ['DATABASE'])
	        self.cursor = self.conn.cursor()
	    except:
	        time.sleep(2)
	        self.get_cursor(timeout-1)