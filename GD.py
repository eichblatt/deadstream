import requests
import json
import os
import pdb
import datetime,time
from importlib import reload

class GDArchive:
  """ The Grateful Dead Collection on Archive.org """
  def __init__(self,dbpath,url='https://archive.org',force_reload=False):
    self.url = url
    self.dbpath = dbpath
    self.idpath = os.path.join(self.dbpath,'ids.json')
    
    self.url_scrape = self.url + '/services/search/v1/scrape'
    self.scrape_parms = {'debug':'false','xvar':'production','total_only':'false','count':'10000','sorts':'date asc,avg_rating desc,num_favorites desc,downloads desc','fields':'identifier,date,avg_rating,num_reviews,num_favorites,stars,downloads,files_count,format,collection,source,subject,type'}
    self.ids = self.load_ids(force_reload)

  def write_ids(self,ids):
    os.makedirs(os.path.dirname(self.idpath),exist_ok=True)
    json.dump(ids,open(self.idpath,'w'))

  def load_ids(self,force_reload=False):
    if (not force_reload) and os.path.exists(self.idpath):
      ids = json.load(open(self.idpath,'r'))
    else:
      ids = []
      for year in range(1965,1996,1):
        ids.extend(self.get_ids(year))
      self.write_ids(ids)
    return ids

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

class GDTape:
  """ A Grateful Dead Tape from Archive.org """
  def __init__(self,raw_json):
    self.raw_json = raw_json
    attribs = ['date','identifier','avg_rating','format']
    for k,v in raw_json.items():
       if k in attribs: setattr(self,k,v)
    self.date = (datetime.datetime.strptime(raw_json['date'] ,'%Y-%m-%dT%H:%M:%SZ')).date() # there must be a better way!!!
    if 'avg_rating' in raw_json.keys(): self.avg_rating = float(self.avg_rating)
    else: self.avg_rating = 2.0
    self.url_endpoint = 'https://archive.org/metadata/'+self.identifier
    self.url = 'https://archive.org/details/'+self.identifier
    self._playable_formats = ['Ogg Vorbis','VBR MP3','Shorten','Flac','MP3']
    self.tracks = []
    self.page_meta = self.get_page_metadata()
 
  def __str__(self):
    retstr = 'ID {}\nDate {}. {} tracks, URL {}\n'.format(self.identifier,self.date,len(self.tracks),self.url)
    return retstr

  def __repr__(self):
    retstr = 'ID {}\nDate {}. {} tracks, URL {}\n'.format(self.identifier,self.date,len(self.tracks),self.url)
    return retstr


  def stream_only(self):
    return 'stream_only' in self.collection 

  def contains_sound(self):
    return len(list(set(self._playable_formats) & set(self.format)))>0

  def handle_track(self,tdict):
    source = tdict['source']
    if source == 'original':
      orig = tdict['name']
    else:
      orig = tdict['original']
    trackindex = None
    for i,t in enumerate(self.tracks):
      if orig == t.original:  # add in alternate formats
        trackindex = i
        # make sure that this isn't a duplicate!!!
        t.add_file(tdict)
        return t
    self.tracks.append(GDTrack(tdict,self.identifier))

  def get_page_metadata(self):
    r = requests.get(self.url_endpoint)
    print("url is {}".format(r.url))
    if r.status_code != 200: print ("error pulling data for {}".format(self.identifier)); raise Exception('Download','Error {} url {}'.format(r.status_code,self.url_endpoint))
    page_meta = r.json()
    self.reviews = page_meta['reviews'] if 'reviews' in page_meta.keys() else []
    for ifile in page_meta['files']:
       try:
         if ifile['format'] in self._playable_formats:
           self.handle_track(ifile)
       except KeyError: pass
       except Exception as e:   # TODO handle this!!!
         raise (e)
    return page_meta

class GDTrack:
  """ A track from a GDTape recording """
  def __init__(self,tdict,parent_id):
    self.parent_id = parent_id
    attribs = ['track','original','title']
    for k,v in tdict.items():
       if k in attribs: setattr(self,k,v)
    # if these don't exist, i'll throw an error!
    if tdict['source'] == 'original': self.original = tdict['name']
    self.track = int(self.track) if 'track' in dir(self) else 0
    self.files = []
    self.add_file(tdict)

  def __str__(self):
    retstr = 'track {}. {}'.format(self.track,self.title)
    return retstr

  def __repr__(self):
    retstr = 'track {}. {}'.format(self.track,self.title)
    return retstr
      
  def add_file(self,tdict):
    attribs = ['name','format','size','source']
    d = {k:v for (k,v) in tdict.items() if k in attribs}
    d['size'] = int(d['size'])
    d['url'] = 'https://archive.org/download/'+self.parent_id+'/'+d['name']
    self.files.append(d)
  # method to play(), pause(). 

