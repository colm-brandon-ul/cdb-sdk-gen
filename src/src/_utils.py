from minio import Minio # type: ignore
import os
import requests
import re
from pathlib import Path
import uuid
from ._config import Config as _Config #type: ignore
from collections import Counter


def _minio_healthcheck():
    # Ping the minio server, if it returns a status code of 200
    # the server is functioning correctly
    res = requests.get(f"http://{_Config._MINIO_HOST}:{_Config._MINIO_PORT}/minio/health/live")
    if res.status_code == 200:
        return True
    else:
        return False 
     
def get_minio_client(internal: bool = True) -> Minio:
    if _minio_healthcheck():
        if internal:

            client = Minio(
            endpoint=f"{_Config._MINIO_HOST}:{_Config._MINIO_PORT}",
            access_key=_Config._MINIO_ACCESS_KEY,
            secret_key=_Config._MINIO_SECRET_KEY,
            secure=False)
            return client
        else:
            client = Minio(
            endpoint=_Config._MINIO_EXTERNAL_HOST,
            access_key=_Config._MINIO_ACCESS_KEY,
            secret_key=_Config._MINIO_SECRET_KEY,
            secure=True if _Config._MINIO_EXTERNAL_SECURE == "True" else False)
            return client
    else:
        raise Exception("Minio server is not running")


def download_stacked_tiff_locally(url,dest="temp-files"):
    file_from_presigned_url = re.compile('/([^/]*)\?')
    matches = re.findall(file_from_presigned_url,url)
    assert len(matches) == 1, f'Regex found {len(matches)} in URL {url}'
     # Prepend UUID, so two workflows working on the same experimental data won't encounter race conditions
    local_filename = f"{str(uuid.uuid4())}_{matches[0]}"
    dest = Path(dest)
    try:
        os.mkdir(dest)
    except:
        pass
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest / local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): 
                # If you have chunk encoded response uncomment ifD
                # and set chunk_size parameter to None.
                #if chunk: 
                f.write(chunk)
                
   
    return dest / local_filename

def are_lists_equal(list1, list2):
    return Counter(list1) == Counter(list2)