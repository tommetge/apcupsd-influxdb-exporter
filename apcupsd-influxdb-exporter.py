#!/usr/bin/python
"""This script fetches data from the specified apcupsd daemon and
uploads it to the configured influxdb instance."""

import os
import time

from apcaccess import status as apc
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

ORG = os.getenv('INFLUXDB_ORG')
BUCKET = os.getenv('INFLUXDB_BUCKET', 'apcupsd')
TOKEN = os.getenv('INFLUXDB_TOKEN')
PORT = os.getenv('INFLUXDB_PORT', '8086')
HOST = os.getenv('INFLUXDB_HOST')
APCUPSD_HOST = os.getenv('APCUPSD_HOST', HOST)

INTERVAL = int(os.getenv('INTERVAL', '10'))

VERBOSE = os.getenv('VERBOSE', 'false').lower() == 'true'

INVALID_APC_KEYS = ['DATE', 'STARTTIME', 'END APC','ALARMDEL']
VALID_TAG_KEYS = ['APC', 'HOSTNAME', 'UPSNAME', 'VERSION',
    'CABLE', 'MODEL', 'UPSMODE', 'DRIVER', 'APCMODEL']

WATTS_KEY = 'WATTS'
NOM_POWER_KEY = 'NOMPOWER'
LOAD_PCT_KEY = 'LOADPCT'
HOSTNAME_KEY = 'HOSTNAME'

def remove_irrelevant_data(data, keys_to_remove):
    """Remove values matching keys_to_remove from the dictionary"""
    for key in keys_to_remove:
        data.pop(key, None)

def move_tag_values_to_tag_dictionary(data, tags, keys):
    """Copies key/value pairs from data to tags"""
    for key in keys:
        if key in data:
            tags[key] = data[key]
            data.pop(key, None)

def convert_numerical_values_to_floats(ups):
    """Convert all ints to floats in the provided data"""
    for key in ups:
        if ups[key].replace('.', '', 1).isdigit():
            ups[key] = float(ups[key])

def run_exporter(sleep_interval):
    """Runs the exporter every INTERVAL seconds"""
    while True:
        with InfluxDBClient(f'{HOST}:{PORT}', token=TOKEN, org=ORG) as client:
            with client.write_api(write_options=SYNCHRONOUS) as write_api:

                ups = apc.parse(apc.get(host=APCUPSD_HOST), strip_units=True)

                remove_irrelevant_data(ups, INVALID_APC_KEYS)

                tags = {
                    'host': os.getenv(
                        HOSTNAME_KEY, ups.get(HOSTNAME_KEY, 'apcupsd-influxdb-exporter'))
                }
                move_tag_values_to_tag_dictionary(ups, tags, VALID_TAG_KEYS)

                convert_numerical_values_to_floats(ups)

                if WATTS_KEY not in os.environ and NOM_POWER_KEY not in ups:
                    raise ValueError(("Your UPS does not specify NOMPOWER, you must specify "
                        "the max watts your UPS can produce."))

                ups[WATTS_KEY] = float(os.getenv(
                    WATTS_KEY, ups.get(NOM_POWER_KEY))) * 0.01 * float(ups.get(LOAD_PCT_KEY, 0.0))

                json_body = {
                    'measurement': 'apcaccess_status',
                    'fields': ups,
                    'tags': tags
                }

                point = Point.from_dict(json_body)

                response = write_api.write(BUCKET, ORG, point)

                if VERBOSE:
                    print(json_body)
                    print(response)

        time.sleep(sleep_interval)


if __name__ == "__main__":
    run_exporter(INTERVAL)
