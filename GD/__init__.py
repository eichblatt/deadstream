import abc
import aiohttp
import asyncio
import logging
import requests
import json
import os
import pdb
import csv
import difflib
import datetime,time,math
import pkg_resources
import codecs
from operator import attrgetter,methodcaller
from mpv import MPV
from importlib import reload

logger = logging.getLogger(__name__)


class BaseTapeDownloader(abc.ABC):
    """Abstract base class for a Grateful Dead tape downloader.

    Use one of the subclasses: TapeDownloader or AsyncTapeDownloader.
    """

    def __init__(self, url="https://archive.org"):
        self.url = url
        self.api = f"{self.url}/services/search/v1/scrape"
        fields = ["identifier", "date", "avg_rating", "num_reviews",
                  "num_favorites", "stars", "downloads", "files_count",
                  "format", "collection", "source", "subject", "type"]
        sorts = ["date asc", "avg_rating desc",
                 "num_favorites desc", "downloads desc"]
        self.parms = {'debug': 'false',
                      'xvar': 'production',
                      'total_only': 'false',
                      'count': '10000',
                      'sorts': ",".join(sorts),
                      'fields': ",".join(fields)}

    @abc.abstractmethod
    def get_tapes(self, years):
        """Get a list of tapes."""
        pass


class TapeDownloader(BaseTapeDownloader):
    """Synchronous Grateful Dead Tape Downloader"""

    def get_tapes(self, years):
        """Get a list of tapes.

        Parameters:

            years: List of years to download tapes for

        Returns a list dictionaries of tape information
        """
        tapes = []

        for year in years:
            year_tapes = self._get_tapes_year(year)
            tapes.extend(year_tapes)

        return tapes

    def _get_tapes_year(self, year):
        """Get tape information for a year.

        Parameters:

            year: The year to download tape information for

        Returns a list of dictionaries of tape information
        """
        current_rows = 0
        tapes = []
        r = self._get_chunk(year)
        j = r.json()
        total = j['total']
        logger.debug(f"total rows {total}")
        current_rows += j['count']
        tapes = j['items']
        while current_rows < total:
            cursor = j['cursor']
            r = self._get_chunk(year, cursor)
            j = r.json()
            cursor = j['cursor']
            current_rows += j['count']
            tapes.extend(j['items'])
        return tapes

    def _get_chunk(self, year, cursor=None):
        """Get one chunk of a year's tape information.

        Parameters:

            year: The year to download tape information for
            cursor: Used to download a segment of a year of tapes

        Returns a list of dictionaries of tape information
        """
        parms = self.parms.copy()
        if cursor is not None:
            parms['cursor'] = cursor
        query = 'collection:GratefulDead AND year:'+str(year)
        parms['q'] = query
        r = requests.get(self.api, params=parms)
        logger.debug(f"url is {r.url}")
        if r.status_code != 200:
            logger.error(f"Error {r.status_code} collecting data")
            raise Exception(
                'Download', 'Error {} collection'.format(r.status_code))
        return r


class AsyncTapeDownloader(BaseTapeDownloader):
    """Asynchronous Grateful Dead Tape Downloader"""

    def get_tapes(self, years):
        """Get a list of tapes.

        Parameters:

            years: List of years to download tapes for

        Returns a list dictionaries of tape information
        """
        tapes = asyncio.run(self._get_tapes(years))
        return tapes

    async def _get_tapes(self, years):
        """Get a list of tapes.

        Parameters:

            years: List of years to download tapes for

        Returns a list dictionaries of tape information
        """
        # This is the asynchronous impl of get_tapes()
        logger.info("Loading tapes from the archive...")
        async with aiohttp.ClientSession() as session:
            tasks = [self._get_tapes_year(session, year) for year in years]
            tapes = await asyncio.gather(*tasks)
        tapes = [tape for sublist in tapes for tape in sublist]
        return tapes

    async def _get_chunk(self, session, year, cursor=None):
        """Get one chunk of a year's tape information.

        Parameters:

            session: The aiohttp.ClientSession to make requests through
            year: The year to download tape information for
            cursor: Used to download a segment of a year of tapes

        Returns a list of dictionaries of tape information
        """
        parms = {"q": f"collection:GratefulDead AND year:{year}"}

        if cursor is not None:
            parms['cursor'] = cursor

        async with session.get(self.api, params={**self.parms, **parms}) as r:
            logger.debug(f"Year {year} chunk {cursor} url: {r.url}")
            json = await r.json()
            return json

    async def _get_tapes_year(self, session, year):
        """Get tape information for a year.

        Parameters:

            session: The aiohttp.ClientSession to make requests through
            year: The year to download tape information for

        Returns a list of dictionaries of tape information
        """
        tapes = []
        cursor = None
        n = 0

        while True:
            chunk = await self._get_chunk(session, year, cursor=cursor)
            n += chunk["count"]
            tapes.extend(chunk['items'])

            if n >= chunk["total"]:
                break

            cursor = chunk["cursor"]

        return tapes


class GDArchive:
  """ The Grateful Dead Collection on Archive.org """
  def __init__(self,dbpath,url='https://archive.org',reload_ids=False, sync=False):
    """Create a new GDArchive.

    Parameters:

      dbpath: Path to filesystem location where data are stored
      url: URL for the internet archive
      reload_ids: If True, force re-download of tape data
      sync: If True use the slower synchronous downloader
    """
    self.url = url
    self.dbpath = dbpath
    self.idpath = os.path.join(self.dbpath,'ids.json')
    self.set_data = GDSet()
    self.downloader = (TapeDownloader if sync else AsyncTapeDownloader)(url)
    self.tapes = self.load_tapes(reload_ids)
    self.tape_dates = self.get_tape_dates()
    self.dates = sorted(self.tape_dates.keys())

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    retstr = F"Grateful Dead Archive with {len(self.tapes)} tapes on {len(self.dates)} dates from {self.dates[0]} to {self.dates[-1]} "
    return retstr
  
  def best_tape(self,date):
    if not date in self.dates: 
      print ("No Tape for date {}".format(date))
      return None
    return self.tape_dates[date][0]
     
  def get_tape_dates(self):
    tape_dates = {}
    for tape in self.tapes:
      k = tape.date
      if not k in tape_dates.keys():
        tape_dates[k] = [tape]
      else:
        tape_dates[k].append(tape)
    # Now that we have all tape for a date, put them in the right order
    self.tape_dates = {}
    for k,v in tape_dates.items():
      self.tape_dates[k] = sorted(v,key=methodcaller('compute_score'),reverse=True) 
    return self.tape_dates

  def write_tapes(self,tapes):
    os.makedirs(os.path.dirname(self.idpath),exist_ok=True)
    json.dump(tapes,open(self.idpath,'w'))

  def load_tapes(self,reload_ids=False):
    if (not reload_ids) and os.path.exists(self.idpath):
      tapes = json.load(open(self.idpath,'r'))
    else:
      print ("Loading Tapes from the Archive...this will take a few minutes")
      tapes = self.downloader.get_tapes(list(range(1965, 1996, 1)))
      self.write_tapes(tapes)
    return [GDTape(self.dbpath,tape,self.set_data) for tape in tapes]


class GDTape:
  """ A Grateful Dead Identifier Item -- does not contain tracks """
  def __init__(self,dbpath,raw_json,set_data):
    self.dbpath = dbpath
    self._playable_formats = ['Ogg Vorbis','VBR MP3','Shorten','MP3']  # had to remove Flac because mpv can't play them!!!
    self._breaks_added = False
    self.meta_loaded = False
    attribs = ['date','identifier','avg_rating','format','collection','num_reviews','downloads']
    for k,v in raw_json.items():
       if k in attribs: setattr(self,k,v)
    self.url_metadata = 'https://archive.org/metadata/'+self.identifier
    self.url_details = 'https://archive.org/details/'+self.identifier
    self.date = str((datetime.datetime.strptime(raw_json['date'] ,'%Y-%m-%dT%H:%M:%SZ')).date()) 
    self.set_data = set_data.get(self.date)
    if 'avg_rating' in raw_json.keys(): self.avg_rating = float(self.avg_rating)
    else: self.avg_rating = 2.0

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    tag = "SBD" if self.stream_only() else "aud"
    retstr = '{} - {} - {:5.2f} - {}\n'.format(self.date,tag,self.avg_rating,self.identifier)
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

  def contains_sound(self):
    return len(list(set(self._playable_formats) & set(self.format)))>0

  def tracks(self):
    self.get_metadata()
    return self._tracks

  def tracklist(self):
    for i,t in enumerate(self._tracks):
      print(i)
    
  def track(self,n):
    if not self.meta_loaded: self.get_metadata()
    return self._tracks[n-1]
 
  def get_metadata(self):
    if self.meta_loaded: return
    self._tracks = []
    date = datetime.datetime.strptime(self.date,'%Y-%m-%d').date() 
    meta_path = os.path.join(self.dbpath,str(date.year),str(date.month),self.identifier+'.json')
    if os.path.exists(meta_path): 
      page_meta = json.load(open(meta_path,'r'))
    else:
      r = requests.get(self.url_metadata)
      print("url is {}".format(r.url))
      if r.status_code != 200: print ("error pulling data for {}".format(self.identifier)); raise Exception('Download','Error {} url {}'.format(r.status_code,self.url_metadata))
      try:
        page_meta = r.json()
      except ValueError:
        print ("Json Error {}".format(r.url))
        return None
      except:
        print ("Json Error, probably")
        return None

    # self.reviews = page_meta['reviews'] if 'reviews' in page_meta.keys() else []
    for ifile in page_meta['files']:
       try:
         if ifile['format'] in self._playable_formats:
           self.append_track(ifile)
       except KeyError: pass
       except Exception as e:   # TODO handle this!!!
         raise (e)
    os.makedirs(os.path.dirname(meta_path),exist_ok=True)
    json.dump(page_meta,open(meta_path,'w'))
    self.meta_loaded = True
    #return page_meta
    self.insert_breaks()
    return 

  def append_track(self,tdict):
    source = tdict['source']
    if source == 'original':
      orig = tdict['name']
    else:
      orig = tdict['original']
    trackindex = None
    for i,t in enumerate(self._tracks):
      if orig == t.original:  # add in alternate formats
        trackindex = i
        # make sure that this isn't a duplicate!!!
        t.add_file(tdict)
        return t
    self._tracks.append(GDTrack(tdict,self.identifier))

  def venue(self,tracknum=0):
    """return the venue, city, state"""
    # Note, if tracknum > 0, this could be a second show...check after running insert_breaks 
    # 1970-02-14 is an example with 2 shows.
    self.get_metadata()
    sd = self.set_data
    if sd == None: return self.identifier
    breaks = self._compute_breaks()
    venue_string = ""
    if not sd == None:
      l = sd['location']
      if (len(breaks['location'])>0) and (tracknum > breaks['location'][0]): l = sd['location2']
      venue_string = F"{l[0]}, {l[1]}, {l[2]}"
    return venue_string 

  def _compute_breaks(self):
    if not self.meta_loaded: self.get_metadata()
    tlist = [x.title for x in self._tracks]
    sd = self.set_data
    lb = sd['longbreaks'] if 'longbreaks' in sd.keys() else []
    sb = sd['shortbreaks'] if 'shortbreaks' in sd.keys() else []
    locb = sd['locationbreak'] if 'locationbreak' in sd.keys() else []
    long_breaks = []; short_breaks = []; location_breaks = []
    try:
      long_breaks = [difflib.get_close_matches(x,tlist)[0] for x in lb]
      short_breaks = [difflib.get_close_matches(x,tlist)[0] for x in sb]
      location_breaks = [difflib.get_close_matches(x,tlist)[0] for x in locb]
    except:
      pass
    lb_locations = []; sb_locations = []; locb_locations = [];
    lb_locations = [j+1 for j,t in enumerate(tlist) if t in long_breaks] 
    sb_locations = [j+1 for j,t in enumerate(tlist) if t in short_breaks]
    locb_locations = [j+1 for j,t in enumerate(tlist) if t in location_breaks]
    # At this point, i need to add "longbreak" and "shortbreak" tracks to the tape.
    # This will require creating special GDTracks, I guess.
    # for now, return the location indices.
    return {'long':lb_locations,'short':sb_locations,'location':locb_locations}


  def insert_breaks(self):
    if not self.meta_loaded: self.get_metadata()
    if self._breaks_added: return
    breaks = self._compute_breaks()
    breakd = {'track':-1,'original':'setbreak','title':'Set Break','format':'Ogg Vorbis','size':1,'source':'original','path':self.dbpath}
    lbreakd =dict(list(breakd.items()) + [('title','Set Break'),('name','silence600.ogg')])
    sbreakd =dict(list(breakd.items()) + [('title','Encore Break'),('name','silence300.ogg')])
    locbreakd =dict(list(breakd.items()) + [('title','Location Break'),('name','silence600.ogg')])
    
    # make the tracks
    newtracks = []
    for i,t in enumerate(self._tracks):
       for j in breaks['long']:
         if i==j: newtracks.append(GDTrack(lbreakd,'',True))
       for j in breaks['short']:
         if i==j: newtracks.append(GDTrack(sbreakd,'',True))
       for j in breaks['location']:
         if i==j: newtracks.append(GDTrack(locbreakd,'',True))
       newtracks.append(t)
    self._breaks_added = True
    self._tracks = newtracks.copy()

class GDTrack:
  """ A track from a GDTape recording """
  def __init__(self,tdict,parent_id,break_track=False):
    self.parent_id = parent_id
    attribs = ['track','original','title']
    for k,v in tdict.items():
       if k in attribs: setattr(self,k,v)
    # if these don't exist, i'll throw an error!
    if tdict['source'] == 'original': self.original = tdict['name']
    try:
      self.track = int(self.track) if 'track' in dir(self) else None
    except ValueError:
      self.track = None 
    self.files = []
    self.add_file(tdict,break_track)

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    retstr = 'track {}. {}'.format(self.track,self.title)
    return retstr
      
  def add_file(self,tdict,break_track=False):
    attribs = ['name','format','size','source','path']
    d = {k:v for (k,v) in tdict.items() if k in attribs}
    d['size'] = int(d['size'])
    if not break_track: d['url'] = 'https://archive.org/download/'+self.parent_id+'/'+d['name']
    else :              d['url'] = 'file://'+os.path.join(d['path'],d['name'])
    self.files.append(d)
  # method to play(), pause(). 

class GDSet:
  """ Set Information from a Grateful Dead date """
  def __init__(self):
    set_data = {}
    prevsong = None;
    set_breaks = pkg_resources.resource_stream(__name__,"set_breaks.csv")
    utf8_reader = codecs.getreader("utf-8")
    r = [r for r in  csv.reader(utf8_reader(set_breaks))]                                                                                                                                         
    headers = r[0] 
    for row in r[1:]:
      d = dict(zip(headers,row))
      date = d['date']; song = d['song'];
      if not date in set_data.keys(): set_data[date] = {}
      if int(d['ievent'])==1: set_data[date]['location'] = (d['venue'],d['city'],d['state']); prevsong = song;
      if int(d['ievent'])==2: set_data[date]['location2'] = (d['venue'],d['city'],d['state']); set_data[date]['locationbreak'] = [prevsong]
      if d['break_length']=='long':
         try: set_data[date]['longbreaks'].append(song)
         except KeyError: set_data[date]['longbreaks'] = [song]
      if d['break_length']=='short':
         try: set_data[date]['shortbreaks'].append(song)
         except KeyError: set_data[date]['shortbreaks'] = [song]
     
    self.set_data = set_data
    """
    for k,v in set_data.items():
       setattr(self,k,v)
    """ 
  def get(self,date):
    return self.set_data[date] if date in self.set_data.keys() else None

  def multi_location(self,date):
    d = self.get(date)
    return 'location2' in d.keys()
    
  def location(self,date):
    d = self.get(date)
    return d['location']

  def shortbreaks(self,date):
    d = self.get(date)
    return d['shortbreaks'] 

  def longbreaks(self,date):
    d = self.get(date)
    return d['longbreaks'] 

  def location2(self,date):
    d = self.get(date)
    if self.multi_location(date): return d['location2']
    else: return None

  def locationbreaks(self,date):
    d = self.get(date)
    if self.multi_location(date): return d['locationbreak'] 
    else: return None

  def __str__(self):
    return self.__repr__()

  def __repr__(self):
    retstr = F"Grateful Dead set data"
    return retstr
  
class GDPlayer(MPV):
  """ A media player to play a GDTape """
  def __init__(self,tape):
    super().__init__()
    self._set_property('audio-buffer',10.0)  ## This allows to play directly from the html without a gap!
    self.tape = tape
    self.create_playlist()

  def __str__(self):
    return self.__repr__()
    
  def __repr__(self):
    retstr = str(self.playlist)
    return retstr
    
  def extract_urls(self,tape):  ## NOTE this should also give a list of backup URL's.
    tape.get_metadata()
    urls = [] 
    for y in [x.files for x in tape.tracks()]: 
      for f in y: 
        if f['format'] in tape._playable_formats: urls.append(f['url']); break 
    return urls
  
  def create_playlist(self):
    urls = self.extract_urls(self.tape);
    _ = [self.command('loadfile',x,'append') for x in urls]
    self.playlist_pos = 0 
    self.pause()
    print (F"Playlist {self.playlist}")
    return

  def play(self): 
    self._set_property('pause',False)
    self.wait_until_playing()

  def pause(self):
    self._set_property('pause',True)
    self.wait_until_paused()

  def stop(self): 
    self.playlist_pos = 0
    self.pause()

  def next(self): self.command('playlist-next'); self.wait_until_playing() # jump to next track
  def prev(self): self.command('playlist-prev'); self.wait_until_playing() # jump to previous track

  def track_status(self):
    if self.playlist_pos == None: print (F"Playlist not started"); return None
    print (F"Playlist at track {self.playlist[self.playlist_pos]}")
    if self.raw.time_pos == None: print (F"Track not started"); return None
    print(F"time: {datetime.timedelta(seconds=int(self.raw.time_pos))}, time remaining: {datetime.timedelta(seconds=int(self.raw.time_remaining))}")

  def close(self): self.terminate()

