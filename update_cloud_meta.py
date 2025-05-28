import argparse
import logging
import json
import os
import requests
import tempfile
import time
from threading import Event

from google.cloud import storage

from timemachine import Archivary
from timemachine import config

config.load_options()

logging.basicConfig(
    format="%(asctime)s.%(msec)03d %(levelname)s: %(name)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


logging.getLogger("google.auth").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

storage_client = storage.Client(project="able-folio-397115")
BUCKET_NAME = "spertilo-data"
CLOUD_PATH = f"https://storage.googleapis.com/{BUCKET_NAME}"
bucket = storage_client.bucket(BUCKET_NAME)
SAVE_TO_CLOUD = True
#SAVE_TO_CLOUD = False

#ROOT_DIR = BUCKET_NAME if SAVE_TO_CLOUD else os.path.dirname(os.path.abspath(__file__))

def parse_args():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--collections", nargs="+", default=["TedeschiTrucksBand"], type=str)
    parser.add_argument("--venue", default=1, type=int, help="Refresh vcs file with venue, city, state information")
    parser.add_argument("--save_cloud", default=1, type=int, help="Save to cloud storage")
    parser.add_argument("--debug", default=0, type=int)
    args, unknown = parser.parse_known_args()
    return args


def json_dump(obj, path, **kwargs):
    print(f"in json_dump path is {path}")
    if SAVE_TO_CLOUD:
        path = path.replace(BUCKET_NAME + "/", "")
        logger.info(f"json dumping {path}")

        obj_string = json.dumps(obj, indent=1)
        if len(obj_string) == 0:
            return obj_string
        blob = bucket.blob(path)
        blob.upload_from_string(obj_string)
    else:
        try:
            tmpfile = tempfile.mkstemp(".json")[1]
            json.dump(obj, open(tmpfile, "w"), **kwargs)
            os.rename(tmpfile, path)
            logger.info(f"json dumping to local file {path}")
        except Exception:
            logger.debug(f"removing {tmpfile}")
            os.remove(tmpfile)

def refresh_vcs(collection):
    """ Refresh the venue, city, state information in the vcs file.
    """
    if collection == "Phish": # No need to refresh Phish vcs, it's already good.
        return {}
    vcs_path = f"vcs/{collection}_vcs.json"
    cloud_url = f"https://storage.googleapis.com/spertilo-data/{vcs_path}"
    archive_api = "https://archive.org/metadata"
    current_vcs = requests.get(cloud_url).json()
    local_vcs_path = os.path.join('/home/steve/projects/deadstream/timemachine',f"metadata/vcs/{collection}_vcs.json")
    if os.path.exists(local_vcs_path):
        local_vcs = json.load(open(local_vcs_path, "r"))
        current_vcs.update(local_vcs)   
    a = Archivary.Archivary(collection_list=[collection],with_latest=True)
    dates = a.tape_dates
    resp = None
    try:
        for date in dates:
            vcs = current_vcs.get(date, '')
            if len(vcs.split(',')) < 2:
                tapes = a.tape_dates[date]
                if len(tapes) == 0:
                    continue
                tape = tapes[0]
                tape_id = tape.identifier
                tape_meta_url = f"{archive_api}/{tape_id}"
                resp = requests.get(tape_meta_url)
                if resp.status_code != 200:
                    logger.error(f"Failed to get metadata for {tape_id} from {tape_meta_url}")
                    continue
                metadata = resp.json().get('metadata',{})
                venue = metadata.get("venue", "")
                city_state = metadata.get("coverage", " , ")
                vcs_new = f"{venue}, {city_state}"
                if len(vcs_new) > 4:
                    current_vcs[date] = vcs_new
                    logger.info(f"Updated vcs for {date} in {collection}: {vcs_new}")
                else:
                    logger.warning(f"No valid vcs found for {date} in {collection}")
    finally:
        json.dump(current_vcs, open(local_vcs_path, "w"), indent=1)
        if SAVE_TO_CLOUD:
            json_dump(current_vcs, vcs_path, indent=1)
        resp.close() if resp else None
    return current_vcs

def main(args):
    global SAVE_TO_CLOUD
    SAVE_TO_CLOUD = args.save_cloud

    for collection in args.collections:
        a = Archivary.Archivary(collection_list=[collection],with_latest=True)
        archive = a.archives[0]
        metadir = archive.idpath
        dbpath = os.path.dirname(archive.dbpath)
        if isinstance(metadir, list):
            metadir = metadir[0]
        local_path = [os.path.join(metadir, x) for x in sorted(os.listdir(metadir))][-1]  # latest only
        cloud_path = local_path.replace(f"{dbpath}/", "")
        logger.info(f"path: {local_path}, cloud_path: {cloud_path}")
        obj = json.load(open(local_path, "r"))
        obj_string = json.dumps(obj, indent=1)
        size = len(obj_string)
        if size == 0:
            continue
        blob = bucket.blob(cloud_path)
        logger.info(f"Saving {size} bytes to {CLOUD_PATH}/{cloud_path}")
        blob.upload_from_string(obj_string)
        if args.venue:
            logger.info(f"Refreshing vcs for {collection}")
            refresh_vcs(collection)
            logger.info(f"Done refreshing vcs for {collection}")


if __name__ == "__main__":
    args = parse_args()
    for k in args.__dict__.keys():
        logger.info(f"{k:20s} : {args.__dict__[k]!r}")
    logger.setLevel(logging.DEBUG if args.debug > 0 else logging.INFO)

    if args.debug == 0:
        main(args)
