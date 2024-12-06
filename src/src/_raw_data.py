from abc import ABC as _ABC
import re
from typing import List as _List, Any as _Any, Dict as _Dict
from ._utils import get_minio_client as _get_minio_client, are_lists_equal
from ._config import Config as _Config
import logging

# These files denote the raw data files that are associated with the experiment (that the user will upload to cdb)

# File Transformation fn's
def retrieve_txt_as_list(obj: _Any) -> _List[str]:
    """
    Retrieve text data from a MinIO object and return it as a list of strings. Done for the ChannelMarkers files, but can be used for any text file with a similar format.

    Args:
        obj (Any): The object to retrieve the text data from.

    Returns:
        List[str]: A list of strings containing the text data.

    Raises:
        Any exceptions raised by the underlying operations.

    """
    client = _get_minio_client()
    try:
        response = client.get_object(_Config._MINIO_EXPERIMENT_BUCKET, object_name=obj.object_name)
        
        data = [l.rstrip() for l in response.data.decode().split('\n') if l.rstrip() != '']
        # Read data from response.
    finally:
        response.close()
        response.release_conn()

    return data

# this on the object level
class _File:
    """
    Represents a file with its regular expression and CDB file tag.

    Attributes:
        file_regex (str): The regular expression used to match the file.
        cdb_file_tag (str): The CDB file tag associated with the file.
    """

    def __init__(self, file_regex, cdb_file_tag,transformation_fn=None):
        self.file_regex: str = file_regex
        self.cdb_file_tag: str = cdb_file_tag
        self.transformation_fn = transformation_fn

class _RAW(_ABC):
    """
    Represents a base class for RAW data.

    Attributes:
        experiment_tag (str): The experiment tag associated with the RAW data.
        files (List[File]): A list of File objects representing the RAW data files.
    """

    experiment_tag: str
    files: _List[_File]

    def __init__(self):
        self.check_variables()

    @classmethod
    def check_variables(cls):
        """
        Check if all required variables are present in the child class.

        Raises:
            Exception: If any required variables are missing.
        """
        super_set = set(_RAW.__dict__['__annotations__'].keys())
        sub_set = set({k:v for k,v in cls.__dict__.items() if not k.startswith('__') and not k.startswith('_')}.keys())
        
        diff = super_set.difference(sub_set)

        if diff:
            raise Exception(f"Missing required variables: {', '.join(diff)}")
        
class RAW_TMA(_RAW):
    """
    A class representing RAW data for TMA experiments.
    
    Attributes:
        experiment_tag (str): The experiment tag for TMA.
        files (list): A list of File objects representing the files associated with TMA experiments.
    """
    experiment_tag = 'TMA'
    files = [_File(file_regex = r'^[\w,\s-]+(?:\.tiff|\.tif|\.ome.tiff|\.qptiff)', cdb_file_tag = 'tiff_name'),
            _File(file_regex = r"\S*.txt", cdb_file_tag= 'channel_markers',transformation_fn=retrieve_txt_as_list)]


class RAW_WSI(_RAW):
    """
    Represents a Whole Slide Image (WSI) in the RAW format.

    Attributes:
        experiment_tag (str): The experiment tag for the WSI.
        files (list): A list of File objects representing the files associated with the WSI.
    """
    experiment_tag = 'WSI'
    files = [_File(file_regex = r'^[\w,\s-]+(?:\.tiff|\.tif|\.ome.tiff|\.qptiff)', cdb_file_tag = 'tiff_name'),
            _File(file_regex = r"\S*.txt", cdb_file_tag= 'channel_markers',transformation_fn=retrieve_txt_as_list)]
    



# Raw UTILS
# perhaps should also include an exclusion list form transformation functions (if the developer wants to do something more bespoke)
def read_raw_data(ExperimentClass: _RAW, id: str = "", use_transformations: bool = True) -> _List[_Dict]:
    """
    Reads raw data based on the provided ExperimentClass.

    Args:
        ExperimentClass (Any): The class representing the experiment.
        id (str, optional): The experiment id. Defaults to "". This is the base prefix for the bucket (containing all experiment ids/names)
        use_transformations (bool, optional): Whether to use the transformation functions for the files which have them. Defaults to True.

    Returns:
        List[Dict]: A list of dictionaries containing the raw data for each experiment. Schema for the dictionary is as follows:
            {
                "experiment_name": str, (also the prefix)
                ** k:v (where k is the cdb_file_tag (from ExperimentClass) and v is the corresponding file name (or the transformed file if use_transformations is True and the file has a transformation function))
            }

    """
    client = _get_minio_client()
    all_experiments = {}

    # Read prefixes only (these are the experiment ids)
    # prefixes cannot be tagged, so we need to read all prefixes and then filter out the ones that don't match the experiment tag
    for obj in client.list_objects(_Config._MINIO_EXPERIMENT_BUCKET,prefix=id):
        if obj.is_dir:
            # Remove slashed from prefix
            all_experiments[obj.object_name.replace("/","")] = {}
    
    # Recursively read all objects in the bucket 
    for obj in client.list_objects(_Config._MINIO_EXPERIMENT_BUCKET,recursive=True, include_user_meta=True):
        # exclude directories 
        logging.warning(f'Object: {obj.object_name}')
        if not obj.is_dir:
            # check if the experiment tag matches the experiment tag of the class
            obj_tag = client.get_object_tags(_Config._MINIO_EXPERIMENT_BUCKET, obj.object_name)
            if obj_tag['cdb_experiment_type'] == ExperimentClass.experiment_tag:
                # split the prefix and the file name (prefix is the experiment id)
                prefix, file = obj.object_name.split('/')
                # iterate over the files in the ExperimentClass (these are the files which should be present in the experiment prefix)
                for f in ExperimentClass.files:
                    logging.warning(f'Object: {obj_tag["cdb_file_tag"]}, FILE TAG{f.cdb_file_tag}, REGEX: {f.file_regex}')
                    # prevent files with same regex to be overwritten
                    if f.cdb_file_tag not in all_experiments[prefix].keys():
                        # check if the regex matches the file and the filetype matches the cdb_file_tag
                        if re.match(f.file_regex, file) and obj_tag['cdb_file_tag'] == f.cdb_file_tag:
                            # add the file to the experiment dictionary for that prefix
                            if f.transformation_fn != None and use_transformations:
                                # apply the transformation function to the file (typically reading the file and transforming it to a different format, as opposed to simply retrieving the file name)
                                all_experiments[prefix][f.cdb_file_tag] = f.transformation_fn(obj)
                            else:
                                all_experiments[prefix][f.cdb_file_tag] = file
                            break

    logging.warning(f'All Experiments: {all_experiments}' )
    # remove experiments that don't have all the required files
    valid_file_tags = [f.cdb_file_tag for f in ExperimentClass.files] # get all the cdb_file_tags for the experiment class

    # remove empty dictionaries (i.e. ones that have no file matches and also ones that don't have all the required files)
    # Shouldn't be required as the experiment tag should filter out the experiments that don't match the class / but just in case
    
    # Need to fix this, as list order matters in the comparison ()
    all_experiments = [{'experiment_name': k , **v} for k, v in all_experiments.items() if v and  are_lists_equal(list(v.keys()), valid_file_tags)]
                            
    return all_experiments


#  this also needs to be updated to use the new config
def get_experiment_data_urls(ExperimentClass: _RAW, prefix_name: str) -> _Dict:
    """
    Retrieves the URLs of experiment data files from a Minio bucket.

    Args:
        ExperimentClass (RAW): The experiment class containing the file information.
        prefix_name (str): The prefix name used to filter the objects in the Minio bucket.

    Returns:
        Dict: A dictionary containing the URLs of the experiment data files.

    Raises:
        Exception: If the experiment data is incomplete and some files are missing.

    """
    client = _get_minio_client()
    urls = {}
    # iterate over the objects for a given experiment prefix
    for obj in client.list_objects(_Config._MINIO_EXPERIMENT_BUCKET,prefix_name,include_user_meta=True):
        # iterate over the files in the ExperimentClass
        obj_tag = client.get_object_tags(_Config._MINIO_EXPERIMENT_BUCKET, obj.object_name)
        for f in ExperimentClass.files:
            # check if the regex matches the file and the filetype matches the cdb_file_tag
            if f.cdb_file_tag == obj_tag['cdb_file_tag'] and re.match(f.file_regex, obj.object_name.split('/')[-1]):
                urls[f.cdb_file_tag] = client.get_presigned_url('GET', bucket_name=_Config._MINIO_EXPERIMENT_BUCKET,object_name=obj.object_name)
                break
    
    valid_file_tags = [f.cdb_file_tag for f in ExperimentClass.files] # get all the cdb_file_tags for the experiment class
    # check if all the required files are present (i.e. the experiment data is complete)
    if are_lists_equal(list(urls.keys()), valid_file_tags):
        return urls
    # if not raise an error
    else:
        raise Exception(f'The experiment data is incomplete, some files are missing. Please check the experiment data and try again.\n Expected files: {valid_file_tags} \n Found files: {list(urls.keys())}')
