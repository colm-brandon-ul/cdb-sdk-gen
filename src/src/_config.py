import os

# config.py
class Config:
    # Update the following to k8s FQDNs (as dps will be running in a seperate k8s namespace)
    _DEBUG = False
    # <service-name>.<namespace>.svc.<cluster-domain>
    # Service Discovery
    _MINIO_HOST = os.getenv('MINIO_SERVICE_HOST')
    _MINIO_PORT = os.getenv('MINIO_SERVICE_PORT')
    _JMS_ADDRESS = f"{os.getenv('JOBS_API_SERVICE_HOST')}:{os.getenv('JOBS_API_SERVICE_PORT')}"
    _MINIO_EXTERNAL_HOST = os.getenv('MINIO_EXTERNAL_HOST')
    _MINIO_EXTERNAL_SECURE = os.getenv('MINIO_EXTERNAL_SECURE')

    # Minio Config
    _MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY')
    _MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY')
    _MINIO_WORKFLOW_BUCKET = os.getenv('MINIO_WORKFLOW_BUCKET')
    _MINIO_EXPERIMENT_BUCKET = os.getenv('MINIO_EXPERIMENT_BUCKET')
    # This is only added for interactive services
    _MINIO_PRESIGNED_INGRESS_PATH = os.getenv('MINIO_PRESIGNED_INGRESS_PATH') 
    try:
        # This will throw an error if the env var is not set (i.e. in Debug mode)
        _MINIO_NUM_PARALLEL_UPLOADS = int(os.getenv('MINIO_NUM_PARALLEL_UPLOADS'))
    except:
        # Default to 1 for Debug (variable isn't used anyway in Debug mode)
        _MINIO_NUM_PARALLEL_UPLOADS = 1

    # # Cinco de Bio Config
    # _CINCODEBIO_ROUTING_KEY = os.getenv('CINCODEBIO_ROUTING_KEY')
    # _CINCODEBIO_BASE_URL = os.getenv('CINCODEBIO_BASE_URL') # equals none of it doesn't exist
    # _CINCODEBIO_DATA_PAYLOAD = os.getenv('CINCODEBIO_DATA_PAYLOAD')
    # _CINCODEBIO_JOB_ID = os.getenv('CINCODEBIO_JOB_ID')

    

    @staticmethod
    def DEBUG():
        return Config._DEBUG


 # ONTOLOGYNAME_DEBUG (convention for this env var name)
try:
    # ONTOLOGYNAME_DEBUG (convention for this env var name)
    if os.getenv('CELLMAPS_DEBUG') == 'True':
        Config._DEBUG = True #type: ignore
except:
    # perhaps it doesn't exist
    ...