import requests
import json
import os
import pdb
import datetime
from importlib import reload

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
    print ("handling track ")
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
    self.track = int(self.track)
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
