#!/usr/bin/env python3
import random
import operator
import itertools
import numpy
import re
import os
import pickle
import time


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
	def __init__(self,n=1,threshold=1,reproduction_cost=1,purge=False):
		self.queue = list()
		self.threshold = threshold
		self.reproduction_cost = 1
		self.pset = gp.PrimitiveSetTyped("main", [], bool)
		self.pset.addPrimitive(operator.and_, [bool, bool], bool)
		self.pset.addPrimitive(operator.or_, [bool, bool], bool)
		#pset.addPrimitive(operator.not_, [bool], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addPrimitive(operator.lt, [float, float], bool)
		self.pset.addEphemeralConstant("rand40", lambda: round(random.random() * 40,2), float)
		self.pset.addTerminal('price',float)
		self.pset.addTerminal('volume',float)
		#self.pset.addTerminal('color',float)
		self.creator = creator
		self.creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
		self.creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMin,
			   pset=self.pset)
		self.toolbox = base.Toolbox()
		self.toolbox.register("expr", genGrow, pset=self.pset, min_=0, max_=6,type_=bool)
		self.toolbox.register("individual", tools.initIterate, creator.Individual,
					self.toolbox.expr)
		self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
		self.mongo = MongoClient(os.environ['MONGO_1_PORT_27017_TCP_ADDR'],27017)
		self.get_cursor(3)
		if "breeder" in self.mongo.database_names():
			self.population=list()
			for indi in self.mongo.breeder.population.find():
				self.add_pickled(indi['individual'],indi['_id'],indi['energy'])
		if purge or "breeder" not in self.mongo.database_names():
			self.population=list()
			for genome in self.toolbox.population(n=n):
				self.population.append(self.create_individual())
	def __iter__(self):
		return iter((self.parse_query(str(_['genome'])) for _ in self.population))

	def __enter__(self):
		return self

	def create_individual(self):
		#rerolls when yielding less then 9 results --> needs a more sophisticated approach
		ids = list()
		while len(ids)<9:
			genome = self.toolbox.individual()
			query,ids=self.evaluate(genome)
		energy=0
		return {'genome':genome,'energy':0,'query':query,'ids':ids}
		

	def __exit__( self, exc_type, exc_val, exc_tb):
		self.write_population()
		#self.mongo.drop_database('breeder')
		self.mongo.close()
		self.conn.close()


	def evaluate(self,genome):
		#parse query and get fenotype
		query = "SELECT id FROM gieters WHERE "+self.parse_query(str(genome))
		self.cursor.execute(query)
		ids = list(self.cursor.fetchall())
		return query,ids

	def mate(self,i_one,i_two):
		offspring_one,offspring_two = gp.cxOnePoint(i_one,i_two)
		self.population.append({'genome':offspring_one,'energy':0})
		self.population.append({'genome':offspring_two,'energy':0})
		return offspring_one,offspring_two

	def update_queue(self):
		for individual in self.population:
			if individual['energy']>=self.threshold and individual not in self.queue:
				self.queue.append(individual)
		self.queue.sort(key=lambda x: x['energy'], reverse=True)
		print(self.queue)
		while len(self.queue)>1:
			self.queue[0]['energy']-=self.reproduction_cost
			self.queue[1]['energy']-=self.reproduction_cost
			self.mate(self.queue.pop(0)['genome'],self.queue.pop(0)['genome'])

	def write_population(self):
		for p in self.population:
			if 'id' in p:
				self.mongo.breeder.population.update_one(
					{'_id':ObjectId(p['id'])},
					{
						"$set": {
						'energy':p['energy'],
						'individual': Binary(pickle.dumps(p['genome']))
						}
					},
					upsert=True
					)
			else:
				self.mongo.breeder.population.insert_one(
					{
						'energy':p['energy'],
						'individual': Binary(pickle.dumps(p['genome']))
					}
				)


	def parse_query(self,query):
		if query[:3] == 'or_':
			chunks = self.chunk(query[4:])
			return '('+self.parse_query(chunks[0]) +') OR (' +self.parse_query(chunks[1])+')'
		elif query[:4] == 'and_':
			chunks = self.chunk(query[5:])
			return '('+self.parse_query(chunks[0]) +') AND (' +self.parse_query(chunks[1])+')'
	#	elif query[:4] == 'not_':
	#		return 'NOT ('+ parse_query(query[5:-1])+')'
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


	def add_pickled(self,raw,_id,energy):	
		self.population.append({'genome':pickle.loads(raw),'id':_id,'energy':energy})

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


if __name__ == "__main__":
	with Breeder(5) as b:
		while True:
			b.population[0]['energy']+=1
			#b.population[-1]['energy']+=1
			#b.population[-2]['energy']+=1
			b.update_queue()
			print(len(b.population))
			input()



