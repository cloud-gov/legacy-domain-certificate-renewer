#!/usr/bin/env bash

pkill -x pebble
pkill -x redis-server
pkill -f 'python -m smtpd'
pg_ctl stop 
