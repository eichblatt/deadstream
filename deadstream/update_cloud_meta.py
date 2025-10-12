import argparse
import logging
import json
import os
import requests
import tempfile
import time

from google.cloud import storage

from deadstream.timemachine import MetaAPI
from timemachine import Archivary
from timemachine import config
from timemachine import cloud_utils

config.load_options()

logging.basicConfig(
    format="%(asctime)s.%(msec)03d %(levelname)s: %(name)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


logging.getLogger("google.auth").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

# storage_client = storage.Client(project="able-folio-397115")
# BUCKET_NAME = "spertilo-data"
# CLOUD_PATH = f"https://storage.googleapis.com/{BUCKET_NAME}"
# bucket = storage_client.bucket(BUCKET_NAME)
# SAVE_TO_CLOUD = True
# SAVE_TO_CLOUD = False
cloud_utils.SAVE_TO_CLOUD = False

# ROOT_DIR = BUCKET_NAME if SAVE_TO_CLOUD else os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--collections", nargs="+", default=["TedeschiTrucksBand"], type=str)
    parser.add_argument("--venue", default=1, type=int, help="Refresh vcs file with venue, city, state information")
    parser.add_argument("--save_cloud", default=1, type=int, help="Save to cloud storage")
    parser.add_argument("--clobber", default=0, type=int)
    parser.add_argument("--debug", default=0, type=int)
    args, unknown = parser.parse_known_args()
    return args


def get_existing_collections():
    """Get a list of all existing collections from *_vcs.json files"""
    collections = cloud_utils.list_bucket_contents(prefix="vcs/")[0]
    collections = [c.replace("vcs/", "").replace("_vcs.json", "") for c in collections]
    return collections


def main(args):
    cloud_utils.SAVE_TO_CLOUD = args.save_cloud

    # Handle "existing" collections special case
    if len(args.collections) == 1 and args.collections[0].lower() == "existing":
        collections = get_existing_collections()
        logger.info(f"Found existing collections: {collections}")
    else:
        collections = args.collections

    for collection in collections:
        mapi = MetaAPI.MetaAPI(collection, save_to_cloud=cloud_utils.SAVE_TO_CLOUD)
        vcs_dict = mapi.get_collection_vcs(with_venue=True, clobber=args.clobber)


def main_cli():
    """Entry point for the command-line interface."""
    args = parse_args()
    for k in args.__dict__.keys():
        logger.info(f"{k:20s} : {args.__dict__[k]!r}")
    logger.setLevel(logging.DEBUG if args.debug > 0 else logging.INFO)

    main(args)


if __name__ == "__main__":
    args = parse_args()
    for k in args.__dict__.keys():
        logger.info(f"{k:20s} : {args.__dict__[k]!r}")
    logger.setLevel(logging.DEBUG if args.debug > 0 else logging.INFO)

    if args.debug == 0:
        main(args)
