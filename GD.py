import requests
import json
import os
import pdb
import datetime,time,math
from importlib import reload
from operator import attrgetter,methodcaller

class GDArchive:
  """ The Grateful Dead Collection on Archive.org """
  def __init__(self,dbpath,url='https://archive.org',reload_ids=False):
    self.url = url
    self.dbpath = dbpath
    self.idpath = os.path.join(self.dbpath,'ids.json')
    
    self.url_scrape = self.url + '/services/search/v1/scrape'
    self.scrape_parms = {'debug':'false','xvar':'production','total_only':'false','count':'10000','sorts':'date asc,avg_rating desc,num_favorites desc,downloads desc','fields':'identifier,date,avg_rating,num_reviews,num_favorites,stars,downloads,files_count,format,collection,source,subject,type'}
    self.ids = self.load_ids(reload_ids)
    self.get_id_dates()

  def get_id_dates(self):
    id_dates = {}
    for id in self.ids:
      k = id.date
      if not k in id_dates.keys():
        id_dates[k] = [id]
      else:
        id_dates[k].append(id)
    # Now that we have all ids for a date, put them in the right order
    self.id_dates = {}
    for k,v in id_dates.items():
      self.id_dates[k] = sorted(v,key=methodcaller('compute_score'),reverse=True) 
    return self.id_dates


  def write_ids(self,ids):
    os.makedirs(os.path.dirname(self.idpath),exist_ok=True)
    json.dump(ids,open(self.idpath,'w'))

  def load_ids(self,reload_ids=False):
    if (not reload_ids) and os.path.exists(self.idpath):
      ids = json.load(open(self.idpath,'r'))
    else:
      ids = []
      for year in range(1965,1996,1):
        ids.extend(self.get_ids(year))
      self.write_ids(ids)
    return [GDItem(id) for id in ids]

  def get_ids(self,year):
    current_rows = 0
    ids = []
    r = self.get_chunk(year)
    j = r.json()
    total = j['total']
    print ("total rows {}".format(total))
    current_rows += j['count']
    ids=j['items']
    while current_rows < total:  
      cursor = j['cursor']
      r = self.get_chunk(year,cursor)
      j = r.json()
      cursor = j['cursor']
      current_rows += j['count']
      ids.extend(j['items'])
    return ids

  def get_chunk(self,year,cursor=None):
    parms = self.scrape_parms.copy()
    if cursor!=None: parms['cursor'] = cursor
    query = 'collection:GratefulDead AND year:'+str(year)
    parms['q'] = query
    r = requests.get(self.url_scrape,params=parms)
    print("url is {}".format(r.url))
    if r.status_code != 200: print ("error collecting data"); raise Exception('Download','Error {} collection'.format(r.status_code))
    return r

class GDItem:
  """ A Grateful Dead Identifier Item -- does not contain tracks """
  def __init__(self,raw_json):
    attribs = ['date','identifier','avg_rating','format','collection','num_reviews','downloads']
    for k,v in raw_json.items():
       if k in attribs: setattr(self,k,v)
    self.date = str((datetime.datetime.strptime(raw_json['date'] ,'%Y-%m-%dT%H:%M:%SZ')).date()) 
    if 'avg_rating' in raw_json.keys(): self.avg_rating = float(self.avg_rating)
    else: self.avg_rating = 2.0

  def __str__(self):
    return __repr__()

  def __repr__(self):
    tag = "SBD" if self.stream_only() else "aud"
    retstr = '{} - {} - {}\n'.format(self.date,tag,self.identifier)
    return retstr

  def stream_only(self):
    return 'stream_only' in self.collection 

  def compute_score(self):
    """ compute a score for sorting the tape. High score means it should be played first """    
    score = 0
    if self.stream_only(): score = score + 1000
    score = score + math.log(1+self.downloads)
    score = score + self.avg_rating * 10
    return score

