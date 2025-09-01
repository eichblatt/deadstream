import json
import logging
import threading
from functools import lru_cache
from google.cloud import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAVE_TO_CLOUD = True
BUCKET_NAME = "spertilo-data"


@lru_cache(maxsize=3)
def get_bucket(bucket_name=BUCKET_NAME):
    global SAVE_TO_CLOUD
    if not SAVE_TO_CLOUD:
        return None, None
    try:
        storage_client = storage.Client(project="able-folio-397115")
        bucket = storage_client.bucket(bucket_name)
        return bucket
    except Exception as e:
        logger.error(f"could not connect to cloud storage: {e}")
        SAVE_TO_CLOUD = False
        return None


def write_json(data, filepath):
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


def list_bucket_contents(bucket_name=BUCKET_NAME, prefix=None, delimiter="/"):
    """Lists all the blobs in the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)

    blobs = bucket.list_blobs(prefix=prefix, delimiter=delimiter)

    files = []
    folders = []

    # Iterate through the results
    for blob in blobs:
        # These are the actual files at the first level of the prefix
        files.append(blob.name)

    for prefix_name in blobs.prefixes:
        # These are the 'subfolders' (common prefixes) at the first level
        folders.append(prefix_name)

    return files, folders


def read_file(bucket_name, file_name):
    """Reads a file from a Google Cloud Storage bucket and returns its content."""
    bucket = get_bucket(bucket_name)
    blob = bucket.blob(file_name)

    try:
        # Download the blob as a string
        contents = blob.download_as_text()
        return contents
    except Exception as e:
        logger.error(f"Error reading file '{file_name}' from bucket '{bucket_name}': {e}")
        return None


def read_json(bucket_name, file_name):
    """
    Reads a JSON file from a Google Cloud Storage bucket and returns its content
    as a Python dictionary (JSON object).
    """
    try:
        # Download the blob as a string
        json_string = read_file(bucket_name, file_name)
        # Parse the JSON string into a Python dictionary
        json_object = json.loads(json_string)
        logger.debug(f"Successfully read and parsed JSON from '{file_name}' in bucket '{bucket_name}'.")
        return json_object
    except json.JSONDecodeError as e:
        logger.error(f"Error: Could not decode JSON from '{file_name}'. Invalid JSON format: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while reading '{file_name}': {e}")
        return None
