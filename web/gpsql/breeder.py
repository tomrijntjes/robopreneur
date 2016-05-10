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
	def __init__(self,n=2,threshold=1,reproduction_cost=10,purge=False):
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
		self.pset.addTerminal('price_old',float)
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
		self.toolbox.register("evaluate", self.fitness)
		self.toolbox.register("select", tools.selTournament, tournsize=3)
		self.toolbox.register("mate", gp.cxOnePoint)
		self.toolbox.register("expr_mut", genGrow, min_=0, max_=2)
		self.toolbox.register("mutate", gp.mutUniform, expr=self.toolbox.expr_mut, pset=self.pset)
		self.mongo = MongoClient(os.environ['MONGO_1_PORT_27017_TCP_ADDR'],27017)
		self.get_cursor(3)
		if "breeder" in self.mongo.database_names():
			self.population=list()
			for indi in self.mongo.breeder.population.find():
				genome=pickle.loads(indi['genome'])
				self.population.append({'genome':genome,'energy':indi['energy'],'query':indi['query'],'ids':indi['ids'],'mongo_id':indi['_id']})
		if purge or "breeder" not in self.mongo.database_names():
			self.population=list()
			for genome in [self.create_individual for i in range(n)]:
				self.population.append(self.create_individual())
	def __iter__(self):
		return iter((self.parse_query(str(_['genome'])) for _ in self.population))

	def __enter__(self):
		return self

	def create_individual(self,parent1=None,parent2=None):
		if not parent1 and not parent2:
			pop = self.toolbox.population(n=20)
		else:
			pop=[parent1,parent2]
		hof = tools.HallOfFame(1)
		stats = tools.Statistics(lambda ind: ind.fitness.values)
		stats.register("avg", numpy.mean)
		stats.register("std", numpy.std)
		stats.register("min", numpy.min)
		stats.register("max", numpy.max)
		algorithms.eaSimple(pop, self.toolbox, 0.5, 0.2, 40, stats, halloffame=hof)
		genome = hof[0]
		query,ids=self.evaluate(genome)
		energy=0
		return {'genome':genome,'energy':0,'query':query,'ids':ids}
		

	def __exit__( self, exc_type, exc_val, exc_tb):
		self.write_population()
		self.mongo.close()
		self.conn.close()

	def fitness(self,genome):
		return abs(len(self.evaluate(genome)[1])-10),


	def evaluate(self,genome):
		#parse query and get fenotype
		query = "SELECT id FROM gieters WHERE "+self.parse_query(str(genome))
		self.cursor.execute(query)
		ids = list(self.cursor.fetchall())
		return query,ids

	def update_queue(self):
		for individual in self.population:
			if individual['energy']>=self.threshold and individual not in self.queue:
				self.queue.append(individual)
		self.queue.sort(key=lambda x: x['energy'], reverse=True)
		while len(self.queue)>1:
			self.queue[0]['energy']-=self.reproduction_cost
			self.queue[1]['energy']-=self.reproduction_cost
			self.population.append(self.create_individual(self.queue.pop(0)['genome'],self.queue.pop(0)['genome']))

	def write_population(self):
		for p in self.population:
			if 'mongo_id' in p:
				self.mongo.breeder.population.update_one(
					{'_id':ObjectId(p['mongo_id'])},
					{
						"$set": {
						'energy':p['energy'],
						'genome': Binary(pickle.dumps(p['genome'])),
						'query':p['query'],
						'ids':p['ids']
						}
					},
					upsert=True
					)
			else:
				self.mongo.breeder.population.insert_one(
					{
						'energy':p['energy'],
						'genome': Binary(pickle.dumps(p['genome'])),
						'query':p['query'],
						'ids':p['ids']
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


