import abc
import aiohttp
import asyncio
import logging
import requests

logger = logging.getLogger(__name__)


class BaseTapeDownloader(abc.ABC):
    """Abstract base class for a Grateful Dead tape downloader.

    Use one of the base classes: TapeDownloader or AsyncTapeDownloader.
    """

    def __init__(self, url="https://archive.org"):
        self.url = url
        self.url_scrape = f"{self.url}/services/search/v1/scrape"
        self.scrape_parms = {'debug': 'false',
                             'xvar': 'production',
                             'total_only': 'false',
                             'count': '10000',
                             'sorts': 'date asc,avg_rating desc,num_favorites desc,downloads desc',
                             'fields': 'identifier,date,avg_rating,num_reviews,num_favorites,stars,downloads,files_count,format,collection,source,subject,type'}

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
        parms = self.scrape_parms.copy()
        if cursor is not None:
            parms['cursor'] = cursor
        query = 'collection:GratefulDead AND year:'+str(year)
        parms['q'] = query
        r = requests.get(self.url_scrape, params=parms)
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
        loop = asyncio.get_event_loop()
        tapes = loop.run_until_complete(self._get_tapes(years))
        loop.close()
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

        async with session.get(self.url_scrape, params={**self.scrape_parms, **parms}) as r:
            logger.debug(f"Chunk url: {r.url}")
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
