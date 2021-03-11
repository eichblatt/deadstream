import requests
import json
import os
import datetime
from importlib import reload

class GDTape:
  """ A Grateful Dead Tape from Archive.org """
  def __init__(self,raw_json):
    for k,v in raw_json.items():
       setattr(self,k,v)
    self.date = (datetime.datetime.strptime(raw_json['date'] ,'%Y-%m-%dT%H:%M:%SZ')).date() # there must be a better way!!!
    self.avg_rating = float(self.avg_rating)
    self.url_endpoint = 'https://archive.org/metadata/'+self.identifier
    self._playable_formats = ['Ogg Vorbis','VBR MP3','Shorten','Flac','MP3']
    self.tracks = []
 
  def __str__(self):
    retstr = 'ID {}\nDate {}'.format(self.identifier,self.date)
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
    self.tracks.append(GDTrack(tdict))

  def get_page_metadata(self):
    r = requests.get(self.url_endpoint)
    print("url is {}".format(r.url))
    if r.status_code != 200: print ("error pulling data for {}".format(self.identifier)); raise Exception('Download','Error {} url {}'.format(r.status_code,self.url_endpoint))
    self.page_meta = r.json()
    self.reviews = self.page_meta['reviews']
    for ifile in self.page_meta['files']:
       try:
         if ifile['format'] in self._playable_formats:
           handle_track(ifile)
       except:
         print("Error")
    return self.page_meta

class GDTrack:
  """ A track from a GDTape recording """
  def __init__(self,tdict):
    attribs = ['track','original','title']
    for k,v in tdict.items():
       if k in attribs: setattr(self,k,v)
    # if these don't exist, i'll throw an error!
    self.track = int(self.track)
    self.files = []
    self.add_file(tdict)
 
  def add_file(self,tdict):
    attribs = ['name','format','size','source']
    d = {k:v for (k,v) in tdict.items() if k in attribs}
    self.files.append(d)
  # method to play(), pause(). 
