from abc import ABC as _ABC, ABCMeta as _ABCMeta, abstractmethod as _abstractmethod
from dataclasses import dataclass as _dataclass
from typing import Any as _Any, Callable as _Callable, Dict as _Dict, Tuple as _Tuple, Union, get_args, get_origin

from ._config import Config as _Config #type: ignore
from .data_utils import encode_dataclass as _encode_dataclass #type: ignore
from .data_utils import Prefix

import os as _os
import re as _re
# import pika as _pika #type: ignore
# from pika.exchange_type import ExchangeType as _ExchangeType #type: ignore
import logging as _logging
import json as _json
import requests as _requests
from pathlib import Path as _Path

from dacite import from_dict as _from_dict
from jinja2 import Environment as _Environment, FileSystemLoader as _FileSystemLoader #type: ignore
from datetime import datetime as _datetime


# Dataclasses
@_dataclass
class ProcessPayload:
    job_id: str
    args: _Dict


@_dataclass
class PrepareTemplatePayload:
    job_id: str
    base_url: str
    args: _Dict

def remove_optionals(tlist):
    def remove_optional(tp):
        if get_origin(tp) == Union and  type(None) in get_args(tp):
            return get_args(tp)[0]
        return tp
    
    tlist = list(tlist)
    return [remove_optional(tp) for tp in tlist]

# Metaclass for enforcing type constraints
class EnforceTypeMetaClass(_ABCMeta):
    def __new__(cls, name: str, bases: _Tuple[type, ...], namespace: _Dict[str, _Any]):
        # print(str((cls,name, bases, namespace)))
        new_cls = super().__new__(cls,name, bases, namespace)
        # print()
        
        for name,value in namespace.items():
            if callable(value) and not name.startswith("__"):
                abstract_method = getattr(new_cls,name,None)
                # print(new_cls,name)
                if abstract_method and callable(abstract_method) and not (name.startswith("__") or name.__contains__('deserialize')):
                    enforce_type_constraints(abstract_method,value)
        
        return new_cls
    
# Takes in two methods (the abstract method from the super class and it's concrete implementation)
def enforce_type_constraints(abstract_method: _Callable, concrete_method: _Callable):
    try:
        abstract_annotations = abstract_method.__annotations__
        concrete_annotations = concrete_method.__annotations__
    except:
        raise Exception
    # Check method input parameters
    # Iterate over the annotations of the abastract method
    for param_name, abstract_param_type in abstract_annotations.items():
        # get the type of the parameter from the concrete method
        concrete_param_type = concrete_annotations.get(param_name)
        # Check if the type of the concrete parameter is a subtype of the abstract parameter.
        # If it isn't raise a type error  

        if concrete_param_type != _Any and abstract_param_type != _Any and concrete_param_type:
            if (concrete_param_type and not issubclass(concrete_param_type,abstract_param_type)):
                raise TypeError(
                    f"Type hint mismatch for paramater '{param_name}' in {concrete_method.__qualname__}. "
                    f"Expected {abstract_param_type}, but got {concrete_param_type}"
                )
        
    # Check method Return Parameters
    abstract_return_type = abstract_annotations.get("return", None)
    concrete_return_type = concrete_annotations.get("return", None)
    
    # Check if there is a return type (both abstract and concrete) and if so, is the concrete return type a sub class of the abstract return type
     # If it isn't raise a type error 
    if concrete_return_type != _Any and abstract_return_type != _Any and concrete_return_type != _Tuple and abstract_return_type != _Tuple:
        if (abstract_return_type and concrete_return_type and not issubclass(concrete_return_type, abstract_return_type)):
            raise TypeError(
                    f"Type hint mismatch for return type in {concrete_method.__qualname__}. "
                    f"Expected {abstract_param_type}, but got {concrete_param_type}"
                ) 
        
# Base Class for all services
class Service(_ABC, metaclass=EnforceTypeMetaClass):
    # Same for all classes
    _ROUTING_KEY: str

    def __init__(self) -> None:
        # self.ROUTING_KEY: str = ROUTING_KEY
        if not _Config.DEBUG():
            # These need to be set as they are in the k8s pods
            self.JMS_ADDRESS = _Config._JMS_ADDRESS
            
        if not self._ROUTING_KEY:
            raise TypeError('Please settign _ROUTING_KEY to a value != None in your concrete class (This is the Abstract Idea (i.e. task.initialise.*))')
        self._enforce_process_concept()
    
    # Method for enforcing that the concrete class implemented by a tool builder conforms to the Process Taxonomy
    def _enforce_process_concept(self):
        # Also need to enforce input.system_parameters.data_flow.keys() == Union(return.data.keys(), return.workflow_parameters.keys())
        _input = set()
        _output = set()
        _dataflow_in = set()
        _dataflow_out = set()
        if issubclass(self.__class__,Automated):
            # enforce that the dataflow from process input matches the keys output by data in process
            try:
                _input.update(set(remove_optionals(getattr(self,'process').
                                __annotations__.get('input').
                                __annotations__.get('data').
                                __annotations__.values())))
            except:
                ...

            try:
                _input.update(set(remove_optionals(getattr(self,'process').
                                __annotations__.get('input').
                                __annotations__.get('workflow_parameters').
                                __annotations__.values())))
            except:
                ...

            try:
                _dataflow_in.update(set(getattr(self,'process').
                                __annotations__.get('input').
                                __annotations__.get('system_parameters').
                                __annotations__.get('data_flow').
                                __annotations__.keys()))
            except:
                ...
            
            try:
                _output.update(set(remove_optionals(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('data').
                                __annotations__.values())))
                
                _dataflow_out.update(set(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('data').
                                __annotations__.keys()))

            except:
                ...

            try:
                _output.update(set(remove_optionals(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('workflow_parameters').
                                __annotations__.values())))
                
                _dataflow_out.update(set(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('workflow_parameters').
                                __annotations__.keys()))
            except:
                ...

            # Compare to any of the I/O for the segmentation tool
        elif issubclass(self.__class__,Interactive):
            try:
                _input.update(set(remove_optionals(getattr(self,'prepare_template').
                                __annotations__.get('input').
                                __annotations__.get('data').
                                __annotations__.values())))
            except:
                ...

            try:
                _input.update(set(remove_optionals(getattr(self,'prepare_template').
                                __annotations__.get('input').
                                __annotations__.get('workflow_parameters').
                                __annotations__.values())))
            except:
                ...

            try:
                _dataflow_in.update(set(getattr(self,'prepare_template').
                                __annotations__.get('input').
                                __annotations__.get('system_parameters').
                                __annotations__.get('data_flow').
                                __annotations__.keys()))
            except:
                ...


            try:
                _output.update(set(remove_optionals(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('data').
                                __annotations__.values())))
                
                _dataflow_out.update(set(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('data').
                                __annotations__.keys()))

            except:
                ...

            try:
                _output.update(set(remove_optionals(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('workflow_parameters').
                                __annotations__.values())))
                
                _dataflow_out.update(set(getattr(self,'process').
                                __annotations__.get('return').
                                __annotations__.get('workflow_parameters').
                                __annotations__.keys()))

            except:
                ...
        else:
            raise TypeError('The Concrete class does not inherit from the Automated or Interactive Abstract classes from the process library.')
        
        model_conforms = False
        for model in self.models:
            i,o = model

            if i == _input and o == _output:
                model_conforms = True

        # Make the error message clearer here -> print the eorro
        if not model_conforms:
            raise TypeError(f'\n\tThe Input: {_input} and \n\tOutput: {_output} \n\tdoes not conform to the abstract process I/O requirements;')

        if not _dataflow_in == _dataflow_out:
            raise TypeError('The Dataflow keys in the Input do not match the Workflow Parameters / Data being returned')


    
    def _get_root_prefix(self,workflow_id: str) -> Prefix:
        """
            Get's the route prefix for the service which is comprised of the workflow-id
            # the service-name prepended with a timestamp.
        """
        return Prefix(f'{workflow_id}/{_datetime.now().strftime(r"%Y-%m-%d-%H-%M-%S")}-{self._ROUTING_KEY}/')



    # PIKA Method for when Production (i.e. when being used as a part of CdB)
    # Launched in a new thread
    @_abstractmethod # make this type safe by adding annotations
    def _do_work(self):
        pass

    @_abstractmethod # Make this type safe also
    def _do_work_debug(self):
        pass

    
    def _update_jms(self, job_id: str, json_dict : _Dict) -> _Dict:
        """
            Updates to Job Object and returns the new job object -> useful for getting the workflow ID
        """
        res = _requests.put(
                f"http://{self.JMS_ADDRESS}/update-job/{job_id}", 
                json=json_dict)
        _logging.info(f"{res.content.decode()}")
        return _json.loads(res.content.decode())

    def run(self):


        # Read the environment variables - routing key, job_id, data_payload & base_url (if interactive)
        routing_key = _os.environ.get('CINCODEBIO_ROUTING_KEY')
        if _os.environ.get('CINCODEBIO_BASE_URL') == None:
            body = _json.dumps({
                'job_id': _os.environ.get('CINCODEBIO_JOB_ID'),
                'args': _json.loads(_os.environ.get('CINCODEBIO_DATA_PAYLOAD'))
            })
        else:
            # Must be interactive
            body = _json.dumps({
                'job_id': _os.environ.get('CINCODEBIO_JOB_ID'),
                'args': _json.loads(_os.environ.get('CINCODEBIO_DATA_PAYLOAD')),
                'base_url': _os.environ.get('CINCODEBIO_BASE_URL')
            })
        if _Config.DEBUG():
             # Read test contract from file
            workflow_id = _os.environ.get('CINCODEBIO_WORKFLOW_ID')
            
            try:
                self._do_work_debug(
                    routing_key,
                    body,
                    workflow_id)
            except Exception as e:
                _logging.error(e)
        else:
            # Read the environment variables
            try:
                self._do_work(
                    routing_key,
                    body)
            except Exception as e:
                # Log the error
                _logging.error(e)
                # Update the job status to failed
                # k8s will not try to re-run the job.
                self._update_jms(
                    job_id=_os.environ.get('CINCODEBIO_JOB_ID'),
                    json_dict={'job_status': 'failed'})

# Base class for all automated services

class Automated(Service, metaclass=EnforceTypeMetaClass):
    # Concrete implemetation of the do-work method from the Service ABC
    _a :str = 'process'
    
    def __init__(self):
        super().__init__()
        
        if not self._a:
            raise TypeError('Please set _a to a value != None in your concrete class (this is your service name)')
    
    # Need to revise this method for k8s
    def _do_work(self,routing_key, body):
        
        
        # Handle Sumbision
        if _re.match(fr"\S*\.{self._a}\b$",routing_key):
            
            # Reads the message from the queue and deserializes it as a Payload object
            body = _from_dict(
                    data_class=ProcessPayload,
                    data=_json.loads(body)
                    )
            
            # Read the input file from the message Queue
            args = self.deserialize_process_input(
                body=body.args)
            
            job_obj = self._update_jms(
                job_id=body.job_id,
                json_dict={'job_status': 'processing'})
            

            root_prefix = self._get_root_prefix(workflow_id=job_obj['workflow'])
            
            # Do Work
            # args = segarray_tma(args)
            args = self.process(
                prefix=root_prefix,
                input=args)
            # Call to Jobs API to update to Completed

            # Args needs to be serialized here to a dictionary
            job_obj = self._update_jms(
                    job_id=body.job_id,
                    json_dict={
                        'job_status': 'completed',
                        'root_prefix': str(root_prefix),
                        'data': _encode_dataclass(args)})
            
    
    # THIS IS AN AUTOMATED SERVICE
    def _do_work_debug(self,routing_key, body,  workflow_id):

        # Handle Sumbision
        if _re.match(fr"\S*\.{self._a}\b$",routing_key):

       
            # Read the input json file from disk
            _logging.debug('job_status: processing')

            # deserializes it as a Payload object
            body = _from_dict(
                        data_class=ProcessPayload,
                        data=_json.loads(body)
                        )
            
            args = self.deserialize_process_input(body=body.args)

            args = _encode_dataclass(self.process(
                prefix=self._get_root_prefix(
                    workflow_id),
                input=args))
            
            # get cwd for python script
            # base_path = _Path(_os.getcwd())
            prefix_path = _Path(body.job_id)
            try:
                _os.makedirs(prefix_path)
            except FileExistsError:
                # Write the dictionary to the JSON file
                ...
            with open( prefix_path / 'process-output.json', 'w') as json_file:
                _json.dump(args, json_file, indent=4)
            _logging.debug(_json.dumps(args, indent=4))

            _logging.info('job_status: completed')
        
        

    # Needs to be an abstract method, this is what the use implements
    @_abstractmethod
    def process(self, prefix: Prefix, input: _Any) -> _Any:
        ...
    
    @_abstractmethod
    def deserialize_process_input(self, body: _Dict[_Any,_Any]) -> _Any:
        pass

# Base class for all interactive services
class Interactive(Service, metaclass=EnforceTypeMetaClass):
    _a: str  = 'prepare-template'
    _b: str  = 'process'
    # temporary fix as when testing the work directory is not app but the root directory
    if not _Config.DEBUG():
        env = _Environment(loader=_FileSystemLoader("./templates")) #type: ignore
    else:
        env = _Environment(loader=_FileSystemLoader("./app/templates"))
    def __init__(self):
        super().__init__()
        
        if not self._a:
            raise TypeError('Please set _a to a value != None in your concrete class (this is your template service name)')
        
        if not self._b:
            raise TypeError('Please set _b to a value != None in your concrete class (this is your processing service name)')

    
    def _do_work(self,routing_key, body):

        
        if _re.match(fr"\S*\.{self._a}\b$",routing_key):
            # Call to Jobs API to update to Processing
            body = _from_dict(
                    data_class=PrepareTemplatePayload,
                    data=_json.loads(body)
                    )

            args = self.deserialize_prepare_template_input(body = body.args)
            
            job_obj = self._update_jms(
                job_id=body.job_id,
                json_dict={'job_status': 'processing'})
            

            root_prefix = self._get_root_prefix(workflow_id=job_obj['workflow'])
            

            # Needs to pass in variables appropriately **a?
            html = self.prepare_template(
                prefix=root_prefix,
                submit_url=self._get_submit_url(
                    base_url = body.base_url,
                    job_id = body.job_id),
                input=args).html
            
            job_obj = self._update_jms(
                job_id=body.job_id,
                json_dict={'job_status': 'awaiting_interaction',                            
                           'frontend': html, 
                           'url' : self._get_front_end_url(
                               body.base_url,
                               body.job_id)})
        

        # Handle Sumbision
        elif _re.match(fr"\S*\.{self._b}\b$",routing_key):
            body = _from_dict(
                    data_class=ProcessPayload,
                    data=_json.loads(body)
                    )

            args = self.deserialize_process_input(body=body.args)

            job_obj = self._update_jms(
                job_id=body.job_id,
                json_dict={'job_status': 'processing'})
            

            root_prefix = self._get_root_prefix(workflow_id=job_obj['workflow'])
            
            
            # Do Work
            args = self.process(
                prefix=root_prefix,
                input = args)
            # Call to Jobs API to update to Completed
            # Args needs to be serialized here to a dictionary
            job_obj = self._update_jms(
                    job_id=body.job_id,
                    json_dict={
                        'job_status': 'completed', 
                        'root_prefix': str(root_prefix),
                        'data': _encode_dataclass(args)})

    # THIS IS AN INTERACTIVE SERVICE
    def _do_work_debug(self,routing_key, body, workflow_id):
        # Read test contract from file

        if _re.match(fr"\S*\.{self._a}\b$",routing_key):
            # Call to Jobs API to update to Processing
            body = _from_dict(
                    data_class=PrepareTemplatePayload,
                    data=_json.loads(body)
                    )

            args = self.deserialize_prepare_template_input(body = body.args)

            _logging.debug('job_status: processing')

            # Needs to pass in variables appropriately **a?
            html = self.prepare_template(
                prefix=self._get_root_prefix(
                    workflow_id=workflow_id
                ),
                submit_url=self._get_submit_url(
                    base_url = body.base_url,
                    job_id = body.job_id),
                input=args).html
            
            # base_path = _Path(_os.getcwd())
            prefix_path = _Path(body.job_id)
            try:
                _os.makedirs( prefix_path)
            except FileExistsError:
                # Write the dictionary to the JSON file
                ...
            
            # Write the rendered front-end to disk as html file for evaluation
            with open( prefix_path / 'frontend.html', 'w') as html_file:
                html_file.write(html)
            
            _logging.debug('job_status: processing')
            
             # get cwd for python script
           
            # write the preparee-template-output.json file with the url to the front-end
            with open( prefix_path / 'prepare-template-output.json', 'w') as json_file:
                _json.dump({'url' : str( prefix_path / 'frontend.html')}, json_file, indent=4)


            _logging.info('job_status: awaiting_interaction')



        elif _re.match(fr"\S*\.{self._b}\b$",routing_key):

       
            # Read the input json file from disk
            _logging.debug('job_status: processing')

            # deserializes it as a Payload object
            body = _from_dict(
                        data_class=ProcessPayload,
                        data=_json.loads(body)
                        )
            
            args = self.deserialize_process_input(body=body.args)

            args = _encode_dataclass(self.process(
                prefix=self._get_root_prefix(
                    workflow_id),
                input=args))
            
            # get cwd for python script
            # base_path = _Path(_os.getcwd())
            prefix_path = _Path(body.job_id)
            try:
                _os.makedirs( prefix_path)
            except FileExistsError:
                # Write the dictionary to the JSON file
                ...

            with open(prefix_path / 'process-output.json', 'w') as json_file:
                _json.dump(args, json_file, indent=4)
            _logging.debug(_json.dumps(args, indent=4))
            

            _logging.info('job_status: completed')
    
    def _to_kebab_case(self, string: str) -> str:
        splitted = _re.sub('([A-Z][a-z]+)', r' \1', _re.sub('([A-Z]+)', r' \1', string)).split()
        return "-".join(splitted).lower()

    # Generate the submission URL -> base_url & job_id is sent from the serviceAPI
    def _get_submit_url(self, base_url: str, job_id: str) -> str:
        base = ''
        # This gets all the classes that the implemented service inherits from, selects the AD Concept & translates 
        # from Camel Case to url slug (kebab-case) format
        for b in self.__class__.__bases__:
            if b != Interactive:
                base = b.__qualname__
                break
       
        return f'{base_url}/ext/{self._to_kebab_case(base)}/{self._to_kebab_case(self._ROUTING_KEY)}/submit/{job_id}'
    
    def _get_front_end_url(self, base_url: str, job_id: str) -> str:
        base = ''
        # This gets all the classes that the implemented service inherits from, selects the AD Concept & translates 
        # from Camel Case to url slug (kebab-case) format
        for b in self.__class__.__bases__:
            if b != Interactive:
                base = b.__qualname__
                break
        # This converts the abstract concept name and the service name to lower camel case for the urls


        return f'{base_url}/ext/{self._to_kebab_case(base)}/{self._to_kebab_case(self._ROUTING_KEY)}/frontend/{job_id}'

    @_abstractmethod
    def prepare_template(self, prefix: Prefix, submit_url: str, input) -> _Any:
        ...
    
    @_abstractmethod
    def deserialize_prepare_template_input(self,body: _Dict[_Any,_Any]) -> _Any:
        ...
    
    @_abstractmethod
    def process(self,prefix: Prefix, input) -> _Any:
        ...

    @_abstractmethod
    def deserialize_process_input(self,body: _Dict[_Any,_Any]) -> _Any:
        ...

# Base class for all domain specific service concepts (i.e. input/output models)
class ServiceConcept:
    ...