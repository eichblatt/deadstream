# Adding an Archive

How to add an archive to the Arhchivary. An archive is something like the Internet Archive's Live Music Archive, or Phish.in's Phish archive.

## Classes to Implement

### TapeDownloader

The TapeDownloader class inherits from the BaseTapeDownloder class.

#### TapeDownloader Data Members

- url
- api -- root URL of the api
- apikey -- Required for some subclasses.
- parms  -- used in requests. Varies by subclass
- headers -- used in requests.

#### Required Methods for TapeDownloaders

- get_all_tapes
  - calls r = requests.get(self.api, headers=self.headers, params=parms) to get data
- get_all_collection_names

### Archive

the Archive class inherits from the BaseArchive class

#### Archive Data Members

- archive_type = "Base Archive"
- url - passed into constructor
- dbpath  - passed into constructor
- collection_list - passed in constructor
- tapes = []
- date_range = date_range
- collection_list = collection_list if isinstance(collection_list, (list, tuple)) else [collection_list]
- idpath = [os.path.join(self.dbpath, f"{collection_list[0]}_ids")]
- downloader - TapeDownloader object
- set_data = None

#### Required Methods for Archives

- load_archive
- best_tape
- year_artists

### Tape

The Tape class inherits from the BaseTape class

#### Tape Data Members

- dbpath path to home of databse
- playable_formats ["Flac", "Shorten", "Ogg Vorbis", "VBR MP3", "MP3"]
- _breaks_added = False
- meta_loaded = False
- format = None
- collection = None
- artist = None
- meta_path = None
- _tracks = []
- _remove_from_archive = False

### Required Methods for Tapes

- stream_only
- compute_score
- venue

### Other Methods for Tapes

- get_metadata
  - this calls requests.get(self.url_metadata, headers=self.headers)
