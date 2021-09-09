#!/usr/bin/env bash

pkill -x pebble
pkill -x redis-server
pg_ctl stop 
