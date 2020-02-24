#!/usr/bin/env python3
from __future__ import print_function

from sys import argv
from multiprocessing import Pool
from sqlalchemy.exc import IntegrityError

import json
import requests
import argparse

import os, sys
# Insert parent dir to sys.path to import db_access and cern_sso
sys.path.insert(1, os.path.realpath(os.path.pardir))
import db_access
from cern_sso import get_cookies

CERT='../api/private/usercert.pem'
KEY='../api/private/userkey.pem'
CACERT='../api/etc/cern_cacert.pem'
PREMADE_COOKIE='../api/etc/rr_sso_cookie.txt'

def fetch(update):
  db_access.setup_db()

  min_run = 0
  max_run = 0

  session = db_access.get_session()
  try:
    print('Getting min and max runs...')
    minmax = list(session.execute('SELECT MIN(run), MAX(run) FROM oms_data_cache;'))
    min_run = minmax[0][0]
    max_run = minmax[0][1]
  finally:
    session.close()

  print('Run range: %s-%s' % (min_run, max_run))

  fetch_runs(min_run, max_run)


def fetch_runs(min_run, max_run):
  url = 'https://cmsrunregistry.web.cern.ch/api/runs_filtered_ordered'

  request = '''
  { 
    "page": 0,
    "page_size": 100000,
    "sortings":[],
    "filter": {
      "run_number": {
          "and": [
            {">=": %s},
            {"<=": %s}
          ]
      },
      "rr_attributes.significant": true
    }
  }
  ''' % (min_run, max_run)
  
  try:
    cookies = get_sso_cookie(url)
    text = requests.post(url, json=json.loads(request), cookies=cookies, verify=CACERT).text
    result_json = json.loads(text)
    runs = [x['run_number'] for x in result_json['runs']]

    sql = db_access.returning_id_crossdb('UPDATE oms_data_cache SET significant=%s WHERE run = :run_nr;' % db_access.true_crossdb())
    for run in runs:
      session = db_access.get_session()
      try:
        result = session.execute(sql, {'run_nr': run})
        if result.returns_rows:
          result = list(result)
          if len(result) == 0:
            print('Run not present in OMS cache: %s' % run)
        session.commit()
      except Exception as e:
        print(e)
        session.rollback()
      finally:
        session.close()
  except Exception as e:
    print(e)


def get_sso_cookie(url):
  if os.path.isfile(CERT) and os.path.isfile(KEY) and os.path.isfile(CACERT):
    return get_cookies(url, usercert=CERT, userkey=KEY, verify=CACERT)
  elif os.path.isfile(PREMADE_COOKIE):
    cookies = {}
    with open(PREMADE_COOKIE, 'r') as file:
      for line in file:
        fields = line.strip().split('\t')
        if len(fields) == 7:
          cookies[fields[5]] = fields[6]
    return cookies
  return None


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='DCS data extraction from the RR API.')
  parser.add_argument('-u', dest='update', type=bool, default=False, help='If True, all runs will be updated. Otherwise only missing runs will be fetched.')
  args = parser.parse_args()

  update = args.update
  fetch(update)