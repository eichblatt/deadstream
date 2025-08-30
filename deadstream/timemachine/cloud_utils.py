import json
import logging
import threading
from functools import lru_cache
from google.cloud import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAVE_TO_CLOUD = True


def write_json_in_cloud(data, filepath):
    if not SAVE_TO_CLOUD:
        return ""

    def _save_to_cloud():
        try:
            bucket = get_bucket()
            if not bucket:
                logger.error("Failed to get bucket")
                return

            tids_string = json.dumps(data, indent=1)
            if len(tids_string) == 0:
                return tids_string
            tids_blob_name = filepath
            tids_blob = bucket.blob(tids_blob_name)
            tids_blob.upload_from_string(tids_string)
            logger.info(f"Successfully saved tape IDs for {filepath}")
        except Exception as e:
            logger.error(f"Error saving tape IDs to cloud: {str(e)}", exc_info=True)

    thread = threading.Thread(target=_save_to_cloud)
    thread.daemon = True
    thread.start()
    return ""


@lru_cache(maxsize=1)
def get_bucket():
    global SAVE_TO_CLOUD
    if not SAVE_TO_CLOUD:
        return None, None
    try:
        storage_client = storage.Client(project="able-folio-397115")
        bucket = storage_client.bucket("spertilo-data")
        return bucket
    except Exception as e:
        logger.error(f"could not connect to cloud storage: {e}")
        SAVE_TO_CLOUD = False
        return None


def list_bucket_contents(bucket_name):
    """Lists all the blobs in the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)

    blobs = bucket.list_blobs()

    return [b.name for b in blobs]
