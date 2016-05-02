#!/bin/bash
sleep 5
PASS="$MYSQL_ROOT_PASSWORD"
mysql -u root -p"$PASS" -e "CREATE DATABASE IF NOT EXISTS shopsaloon"
mysql -u root -p"$PASS" shopsaloon < /sql/tom.sql
