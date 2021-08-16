#!/usr/bin/env bash

pkill -x pebble
pkill -x pebble-challtestsrv
pg_ctl stop 
