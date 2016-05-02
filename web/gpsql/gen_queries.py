"""
OR use bitstring GA instead to allow for modularity: the goal is to prove any and all aspects of an enterprise can be encoded. Bitstring genomes might be most generic/effective at capturing different aspects. 

Idea: maybe encode the parameters of the GP algorithm in a bitstring, and run the GP every time a new instance is bred? A GP inside a GA. Might be overly complicated.

The simplest and fastest option is creating a number of queries beforehand that roughly split the dataset in half. How to find these queries? 

GP where the fitness is the closeness to splitting the dataset in half. 

OR Select these queries by hand/visual inspection.




select * from product_merchant where (a < b) AND () OR () AND NOT

can't return less than 9 results
shouldn't return much more than 9 results/should terminate within the minute (because caching is an option and so is asynchronous spawning)

use GP framework? --> got my own system for selection, but I need something for recombination

Publicly available framework for generating syntactically correct SQL queries?
Write my own? Not that complicated

1.Represent SQL queries as a tree

F= AND OR

(('id', 'int(10) unsigned', 'NO', 'PRI', None, 'auto_increment'), ('merchant_id', 'int(11) unsigned', 'NO', 'MUL', None, ''), ('product_id', 'int(11) unsigned', 'NO', 'MUL', None, ''), ('sheetrecord_delta_id', 'int(11) unsigned', 'YES', 'MUL', None, ''), ('code', 'varchar(64)', 'YES', 'MUL', '', ''), ('name', 'text', 'YES', '', None, ''), ('price', 'decimal(8,2)', 'NO', '', None, ''), ('description_short', 'text', 'YES', '', None, ''), ('description_long', 'text', 'YES', '', None, ''), ('category', 'text', 'YES', '', None, ''), ('image_small_url', 'text', 'YES', '', None, ''), ('image_medium_url', 'text', 'YES', '', None, ''), ('image_large_url', 'text', 'YES', '', None, ''), ('brand', 'text', 'YES', 'MUL', None, ''), ('affiliate_link', 'text', 'NO', '', None, ''), ('color', 'text', 'YES', '', None, ''), ('created_at', 'timestamp', 'NO', '', '0000-00-00 00:00:00', ''), ('updated_at', 'timestamp', 'NO', '', '0000-00-00 00:00:00', ''), ('deleted_at', 'timestamp', 'YES', 'MUL', None, ''), ('price_old', 'decimal(8,2)', 'YES', '', None, ''), ('gender', 'varchar(255)', 'YES', '', None, ''), ('size', 'varchar(255)', 'YES', '', None, ''), ('shipping_time', 'varchar(255)', 'YES', '', None, ''), ('price_shipping', 'decimal(8,2)', 'YES', '', None, ''), ('merchant_sheetprovider_id', 'int(10) unsigned', 'YES', 'MUL', None, ''))

id
merchant_id
product_id
sheetrecord_delta_id
code
name
price
description_short
description_long
category
image_small_url
image_medium_url
image_large_url
brand
affiliate_link
color
created_at
updated_at
deleted_at
price_old
gender
size
shipping_time
price_shipping
merchant_sheetprovider_id
"""

import random
import operator
import itertools
import numpy
import re
import os

from deap import algorithms
from deap import base
from deap import creator
from deap import tools
from deap import gp

from modifiedgrow import genGrow

import pymysql.cursors

conn = pymysql.connect(host="localhost",
                           user = "root",
                           passwd = "1234",
                           db = "shopsaloon")

def evalQuery(individual):
	func = "SELECT COUNT(*) FROM sample WHERE DELETED_AT is NULL AND "+parse_query(str(individual))
	#print(func)
	c.execute(func)
	result = c.fetchall()[0][0]
	#fitness is the inverse squared distance to splitting the dataset in half
	return abs(result-countstar/2),

def parse_query(query):
	if query[:3] == 'or_':
		chunks = chunk(query[4:])
		return '('+parse_query(chunks[0]) +') OR (' +parse_query(chunks[1])+')'
	elif query[:4] == 'and_':
		chunks = chunk(query[5:])
		return '('+parse_query(chunks[0]) +') AND (' +parse_query(chunks[1])+')'
#	elif query[:4] == 'not_':
#		return 'NOT ('+ parse_query(query[5:-1])+')'
	elif query[:2] == 'lt':
		chunks = chunk(query[3:])
		return parse_query(chunks[0]) +' < ' +parse_query(chunks[1])
	elif query[:2] == 'eq':
		chunks = chunk(query[3:])
		return parse_query(chunks[0]) +' = ' +parse_query(chunks[1])
	return query.strip("'")


def chunk(inputstr):
	closure = 0
	for i in range(len(inputstr)):
		if inputstr[i] == '(':
			closure +=1
		elif inputstr[i] == ')':
			closure -=1
		elif closure==0 and inputstr[i] == ',':
			return (inputstr[:i],inputstr[i+2:-1])


def main():
	#create primitiveset
	pset = gp.PrimitiveSetTyped("main", [], bool)
	pset.addPrimitive(operator.and_, [bool, bool], bool)
	pset.addPrimitive(operator.or_, [bool, bool], bool)
	#pset.addPrimitive(operator.not_, [bool], bool)
	pset.addPrimitive(operator.lt, [float, float], bool)
	pset.addPrimitive(operator.lt, [float, float], bool)
	pset.addPrimitive(operator.lt, [float, float], bool)
	pset.addPrimitive(operator.lt, [float, float], bool)
	pset.addEphemeralConstant("rand100", lambda: round(random.random() * 100,2), float) #0-100. Constant within tree, different between trees
	pset.addTerminal('price',float)
	creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
	creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMin,
		   pset=pset)
	toolbox = base.Toolbox()
	toolbox.register("expr", genGrow, pset=pset, min_=0, max_=6,type_=bool)
	toolbox.register("individual", tools.initIterate, creator.Individual,
				toolbox.expr)
	toolbox.register("population", tools.initRepeat, list, toolbox.individual)
	toolbox.register("evaluate", evalQuery)
	toolbox.register("select", tools.selTournament, tournsize=3)
	toolbox.register("mate", gp.cxOnePoint)
	toolbox.register("expr_mut", genGrow, min_=0, max_=2)
	toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr_mut, pset=pset)
	#random.seed(11)
	pop = toolbox.population(n=500)
	hof = tools.HallOfFame(1)
	stats = tools.Statistics(lambda ind: ind.fitness.values)
	stats.register("avg", numpy.mean)
	stats.register("std", numpy.std)
	stats.register("min", numpy.min)
	stats.register("max", numpy.max)
	algorithms.eaSimple(pop, toolbox, 0.5, 0.2, 40, stats, halloffame=hof)
	return pop, stats, hof
	

with conn.cursor() as c:
	c.execute("SELECT COUNT(*) FROM sample WHERE DELETED_AT is NULL")
	global countstar
	countstar = c.fetchall()[0][0]
	print(countstar)
	pop,stats,hof = main()
	print(parse_query(str(hof[0])))

conn.close()