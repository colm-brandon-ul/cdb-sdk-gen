from io import BytesIO
import requests

def get_data_from_url(url: str) -> BytesIO:
    # read the file and return the bytes
    request = requests.get(url)
    return BytesIO(request.content)


