from enum import Enum
import os
import pathlib
from mypy import api
import ast
import numpy as np
from PIL import Image
import random
import pandas as pd
import jinja2

from ._data import Atomic, NonAtomic, StringMixin, OMETIFF, CSV
from .data import RegionOfInterest
from .data_utils import Prefix
from . import data as cm_data
from .__init__ import __library_name__

# Need to roll this code in cellmaps SDK / add cli entrypoint & finally perform mypy check from code

class _classDefinitionType(str, Enum):
    dataclass = 'dataclass'
    enum = 'enum'
    automated = 'automated'
    interactive = 'interactive'

class _ServiceType(str, Enum):
    automated = 'automated'
    interactive = 'interactive'

class ServiceParser:
    def __init__(self) -> None:
        self.node_hashes = set()
        self.root_dataclass_set = set()
        self.dataclass_schemas = {}
        self.fn_arguments = None
        self.servicename = None
        self.servicetype = None
        self.abstract_concept = None

        # Counters to ensure there's only one control & dataflow class definitions
        self.control = 0
        self.dataflow = 0

        # These are the valid class defintions for the data model
        self.syntactic_keys = ['CLASS_TYPE', 'FIELDS']
        self.valid_class_defintions = ['Control', 'ServiceParameters', 'Data', 'WorkflowParameters','SystemParameters', 'DataFlow']

    def validate_schema(self):
        # Find out which is input and which is output; then ensure dataflow and output keys match up

        dc_in, dc_out = None, None

        for k,v in self.dataclass_schemas.items():

            # Check that the tool developer hasn't added any dataclasses which aren't expected

            if 'SystemParameters' in v.keys():
                if 'DataFlow' in v['SystemParameters'].keys():
                    self.dataflow += 1
                    dc_in = k #k must be input

            if 'Control' in v.keys():
                dc_out = k #k must be output
                self.control += 1

        print(dc_in, dc_out)    

        if self.control != 1 or self.dataflow != 1:
            raise Exception('There must be exactly one Control and one DataFlow dataclasses')

        if dc_in == None or dc_out == None:
            raise Exception('Must have one input and one output dataclass')
        

        df_fields = [field['name'] for field in self.dataclass_schemas[dc_in]['SystemParameters']['DataFlow']['FIELDS']]
        out_fields = []
        if 'WorkflowParameters' in self.dataclass_schemas[dc_out].keys():
            # The data model may not have workflow parameters
            out_fields.extend([field['name'] for field in self.dataclass_schemas[dc_out]['WorkflowParameters']['FIELDS']])
        if 'Data' in self.dataclass_schemas[dc_out].keys():
            # The data model may not have data
            out_fields.extend([field['name'] for field in self.dataclass_schemas[dc_out]['Data']['FIELDS']])


        # In the context of forms (dataflow can be used to hide some inputs (and subsequently outputs))
        if set(df_fields) != set(out_fields):
            print(df_fields)
            print(out_fields)
            raise Exception('The dataflow and Data/Workflow Parameter output fields must match')
        
        if set(['process']) == set(self.fn_arguments.keys()):
            # This is an automated service / check if the dataclasses match the fn arguments
            if not (self.fn_arguments['process'][0] == dc_in and self.fn_arguments['process'][1] == dc_out):
                raise Exception('In an Automated service the process function arguments must match the input and output dataclasses')
        # If the service is interactive, then it must have both process and prepare_template / check if the dataclasses match the fn arguments
        elif set(['process', 'prepare_template']) == set(self.fn_arguments.keys()):
            if not(self.fn_arguments['prepare_template'][0] == dc_in and self.fn_arguments['process'][1] == dc_out):
                raise Exception('In an Interactive service the process function arguments must match the input and output dataclasses')
            
            # Assert prepare template schema output returns only html
            assert set([field['name'] for field in self.dataclass_schemas[self.fn_arguments['prepare_template'][1]]['FIELDS']]) == set(['html']), 'The prepare template function must return only a string with contains the html for the front end of the interactive application'
            



    def get_schema(self, file_name):    

        # run mypy to check the script
        report_code, error_msg, exit_code = api.run([file_name])


        if exit_code == 2:
            raise Exception('The script has failed the mypy check. Please fix the errors and try again. Error message: \n' + error_msg + '\n' + report_code)

        # read code file for parsing
        source_code = open(file_name, 'r').read()

        myast = ast.parse(source_code)
        # Set these values to 0, empty set and the global dataclass dict respectively.
        self.extract_dataclass_schema(myast, indent=0, parent_names = set(), ds_dict = self.dataclass_schemas)
        # print(self.fn_arguments)
        # need to check that the dataclass schemas are correct (i.e. first input has dataflow, and last output has control)
        # Make sure that the dataflow keys from the input are the same as keys for the output (data/workflow parameters)
        self.validate_schema()

        # SCHEMA NEEDS TO BE;

        return {
            'abstract_concept': self.abstract_concept,
            'service_type': self.servicetype,  
            'service_name': self.servicename, # This is the name of the service (i.e. the name of the class)
            'process_input': self.dataclass_schemas[self.fn_arguments['process'][0]],
            'process_output': self.dataclass_schemas[self.fn_arguments['process'][1]],
            'prepare_template_input': self.dataclass_schemas[self.fn_arguments['prepare_template'][0]] if 'prepare_template' in self.fn_arguments.keys() else None,
            'prepare_template_output': self.dataclass_schemas[self.fn_arguments['prepare_template'][1]] if 'prepare_template' in self.fn_arguments.keys() else None,
        }

        
    # This method is used resursively to extract to walk through the AST of the script and extract the dataclass schemas and 
    # also the function arguments for process or process and prepare_template
    def extract_dataclass_schema(self,myast, indent=0, parent_names = set(), ds_dict = None):
        def get_type(node):
            """ 
                extract the type of the node (i.e. the class name)
            """
            if isinstance(node, ast.Name):
                return node.id
            elif isinstance(node, ast.Attribute):
                return f"{get_type(node.value)}.{node.attr}"
            else:
                return 'unknown'
        # method for extracting the details from fields
            
        def get_annassign_details(node):
            """
                Extracts the variable name, annotation, default value and metadata from an AnnAssign node
            
            """
            if isinstance(node, ast.AnnAssign):
                variable_name = node.target.id if isinstance(node.target, ast.Name) else None
                optional = False
                annotation = None
                # For extracting the whether a field is optional and what type it is
                if isinstance(node.annotation, ast.Subscript):
                    if isinstance(node.annotation.value, ast.Name):
                        # perhaps could improve this
                        optional = node.annotation.value.id == 'Optional'
                        if optional:
                            annotation = ast.unparse(node.annotation.slice)

                if annotation == None:
                    annotation = ast.unparse(node.annotation)
                default_value = None
                # is_field = isinstance(node.target, ast.Name) and isinstance(node.target.ctx, ast.Store)
                metadata = None

                # Check if the value is a call to the field function
                if isinstance(node.value, ast.Call) and (node.value.func.id == 'field' or node.value.func.id == 'Field'):
                    # Extract the default value and metadata from the arguments of the call

                    if node.value.func.id == 'Field':
                        raise Exception('Use field instead of Field from the dataclass module')

                    for keyword in node.value.keywords:
                        if keyword.arg == 'default':
                            default_value = ast.unparse(keyword.value)
                        elif keyword.arg == 'metadata':
                            metadata = ast.literal_eval(ast.unparse(keyword.value))

                else: # The value is the default value
                    # Wrapped in try/catch because sometimes get a NoneType error
                    try:
                        # This is the enum default value case
                        default_value = ast.unparse(node.value)
                    except:
                        ...

                return {'name': variable_name, 'type': annotation, 'default_value': default_value, 'metadata': metadata, 'optional': optional}
            else:
                return {'name': None, 'type': None, 'default_value': None, 'metadata': None, 'optional': None}
            
        # Could bundle this into the above function, buf for now it'll dos
        def get_enum_assign_details(node):
            if isinstance(node, ast.Assign):
                variable_name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
                # ast.unparse returns the enum value as a string with single quotes ()
                value = ast.unparse(node.value).strip("'")
                return {'name': variable_name, 'value': value}


            
        for node in ast.walk(myast):
            # Check if the node is a class definition (and hasn't been visited before)
            if isinstance(node,ast.ClassDef) and node.__hash__() not in self.node_hashes:

                # This is to find out the inheritance and decorators for the classes in the script
                automated_base = any([get_type(base) ==  'Automated' for base in node.bases])
                interactive_base = any([get_type(base) ==  'Interactive' for base in node.bases])
                dataclass_base = any([get_type(n) == 'dataclass' for n in node.decorator_list])
                enum_base = any([get_type(base) ==  'Enum' for base in node.bases])

                # If there is a class defined which doesn't confirm to the above, raise an exception
                if not(dataclass_base or enum_base or automated_base or interactive_base):
                    raise Exception('For describing data models, class definitions must be decorated as @dataclasses or inherit from enum.\n In the context of service models, class definitions must inherit from Automated or Interactive.')
                
                # These are root class definitions
                if len(parent_names) == 0:

                    # Creating the set of dataclass root nodes
                    if dataclass_base:
                        self.root_dataclass_set.add(node.name)
                        # Creating dictionary of dataclass schemas and add this node
                        # print(f"{'  '*indent} {node.name} {automated_base} {interactive_base} {dataclass_base}")
                        
                        ds_dict[node.name] = {'CLASS_TYPE': _classDefinitionType.dataclass.name, 'FIELDS': []}

                    # Creating dictionary of function arguments for the Service Class defintion (depending on if it's automated or interactive)
                    if automated_base and not interactive_base:
                        if self.fn_arguments == None:
                            self.fn_arguments = {'process': None}
                        if self.servicetype == None:
                            self.servicetype = _ServiceType.automated.name
                        else :
                            raise Exception('More than one service class has been defined.')

                        if self.abstract_concept == None:
                            abs_bases = [n for n in node.bases if get_type(n) != 'Automated' and get_type(n) != 'Interactive']
                            assert len(abs_bases) == 1, 'There must be exactly one abstract concept'
                            self.abstract_concept = abs_bases[0].id
                        
                        if self.servicename == None:
                            self.servicename = node.name

                    elif interactive_base and not automated_base:
                        if self.fn_arguments == None:
                            self.fn_arguments = {'process': None, 'prepare_template': None}
                        if self.servicetype == None:
                            self.servicetype = _ServiceType.interactive.name
                        else:
                            raise Exception('More than one service class has been defined.')
                        
                        if self.abstract_concept == None:
                            abs_bases = [n for n in node.bases if get_type(n) != 'Automated' and get_type(n) != 'Interactive']
                            assert len(abs_bases) == 1, 'There must be exactly one abstract concept'
                            self.abstract_concept = abs_bases[0].id

                        if self.servicename == None:
                            self.servicename = node.name
                     

                else:
                    # # This is the child dataclass definitions
                    if dataclass_base and not enum_base:
                        ds_dict[node.name] = {'CLASS_TYPE': _classDefinitionType.dataclass.name, 'FIELDS': []}

                        # Check if child class definition is from the valid set (only for dataclasses)
                        # For service parameters enums can be defined
                        if node.name not in self.valid_class_defintions:
                            raise Exception(f'Class definition {node.name} is not a valid class definition for the data model')
                    # this is a enum for control (most likely)
                    elif enum_base and not dataclass_base:
                        ds_dict[node.name] = {'CLASS_TYPE': _classDefinitionType.enum.name, 'FIELDS': []}

                # added to avoid parsing twice (irrespective of the wether it's a root node or a child node)
                self.node_hashes.add(node.__hash__())
                    
                for child_node in node.body:
                    if isinstance(child_node,ast.ClassDef) and child_node.__hash__() not in self.node_hashes:
                        parent_names.add(node.name)
                        # if this a child dataclass definition the recurse
                        self.extract_dataclass_schema(child_node, indent + 1, parent_names=parent_names, ds_dict=ds_dict[node.name])

                    # For both the AnnAssign and the regular Assign, need to figure out a soln to print out the FQN.
                    # Typically for leaf dataclasses these are the only two types of that are present
                    elif (isinstance(child_node,ast.AnnAssign) or isinstance(child_node,ast.Assign))and child_node.__hash__() not in self.node_hashes:
                        # Need to sort out the type when uparsing;
                        # InitTMAProcessOutput.Control = InitTMAProcessOutput.Control.success 
                        # instead of Control = Control.success
                        if dataclass_base and not enum_base:
                            ds_dict[node.name]['FIELDS'].append(get_annassign_details(child_node))
                            # print('  '*(indent + 1),get_annassign_details(child_node), 'FIELD'*1)
                        
                        elif enum_base and not dataclass_base:
                            ds_dict[node.name]['FIELDS'].append(get_enum_assign_details(child_node))
                            # print('  '*(indent + 1),get_enum_assign_details(child_node), 'FIELD'*1)

                    elif isinstance(child_node,ast.FunctionDef):
                        argument_tuple = [None,None]
                        if child_node.name in ['prepare_template','process']:
                            # print('  '*(indent +1),f'Function: {child_node.name}')
                            # Extracting arguments and their annotations
                            for arg in child_node.args.args:
                                arg_name = arg.arg
                                if arg.annotation:
                                    arg_annotation = ast.unparse(arg.annotation)
                                else:
                                    arg_annotation = None
                                if arg_annotation in self.root_dataclass_set:
                                    # print('  '*(indent +1),f'Argument: {arg_name}, Annotation: {arg_annotation}')
                                    # THe dataclass object being input to the function
                                    if arg_name == 'input':
                                        argument_tuple[0] = arg_annotation
                            # Extracting return type annotation
                            if child_node.returns:
                                return_annotation = ast.unparse(child_node.returns)
                            else:
                                return_annotation = None
                            
                            if return_annotation in self.root_dataclass_set:
                                # print('  '*(indent +1),'Return Annotation:', return_annotation) 
                                argument_tuple[1] = return_annotation
                            self.fn_arguments[child_node.name] = tuple(argument_tuple)
                    
                    # Empty the parent_names set (for each root node)
                    if indent == 0:
                        parent_names = set()


# Define the Jinja template as a docstring
test_template = """# Imports - all from standard library
import unittest
import subprocess
import os
import json
from uuid import uuid4
import shutil
from pathlib import Path
import logging

from cellmaps_sdk.data import *
from cellmaps_sdk._test_utils import validate_versus_schema, is_valid_html


#recursive function to check if all the files referenced in the json exist
def print_urls(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'url':
                print(value)
                assert os.path.exists(value) == True, f'{value} does not exist'
            else:
                print_urls(value)
    elif isinstance(data, list):
        for item in data:
            print_urls(item)

{%- macro printAutomated(InputData, OutputSchema) %}
class AutomatedTest(unittest.TestCase):
    def test_script_execution(self):
        # Copy existing environment variables
        env = os.environ.copy()
        # add the ones needed for the script
        env['CELLMAPS_DEBUG'] = 'True'
        env['CINCODEBIO_ROUTING_KEY'] = 'test.process'
        env['CINCODEBIO_JOB_ID'] = uuid4().hex
        env['CINCODEBIO_WORKFLOW_ID'] = uuid4().hex


        # This needs to be generated for the service from the schema
        env['CINCODEBIO_DATA_PAYLOAD'] = json.dumps({{ InputData }})

        # Run the script
        result = subprocess.run(['python3', 'app/main.py'], capture_output=True, text=True, env=env)

        # Check if the script ran without errors
        self.assertEqual(result.returncode, 0, msg=f"Script failed with the following error: {result.stderr} and {result.stdout}")

        # Check if the process-output.json file exists
        with open(f"{env['CINCODEBIO_JOB_ID']}/process-output.json") as json_file:
            po = json.load(json_file)  
        
        OutputSchema = {{ OutputSchema }}
        # assert it versus the output schema

        try: 
            validate_versus_schema(OutputSchema, po)
        except Exception as e:
            self.fail(f"The output file doesn't match the Output Schema {e}")

        # Check if all the files referenced in process-output.json exist
        try:
            if 'data' in po.keys():
                print_urls(po['data'])
        except Exception as e:
            self.fail(f"Atleast one file which referenced in process-output does not exist {e}")

        # Specify the directories to remove
        directories = [Path(os.getcwd()) / env['CINCODEBIO_JOB_ID'], Path(os.getcwd()) / env['CINCODEBIO_WORKFLOW_ID']]

        # Remove the directories
        for directory in directories:
            try:
                shutil.rmtree(directory)
            except Exception as e:
                ...

if __name__ == '__main__':
    unittest.main()
{%- endmacro %}


{%- macro printInteractive(PrepareTemplateInputData,PrepareTemplateOutputSchema,ProcessInputData,ProcessOutputSchema) %}
class InteractiveTest(unittest.TestCase):
    def test_script_execution(self):
        # Copy existing environment variables
        env = os.environ.copy()
        # add the ones needed for the script
        env['CELLMAPS_DEBUG'] = 'True'
        env['CINCODEBIO_JOB_ID'] = uuid4().hex
        env['CINCODEBIO_WORKFLOW_ID'] = uuid4().hex
        env['CINCODEBIO_BASE_URL'] = 'http://localhost:8000' # This is mock url


        # This needs to be generated for the service from the schema
        env['CINCODEBIO_DATA_PAYLOAD'] = json.dumps({{ PrepareTemplateInputData }})
        env['CINCODEBIO_ROUTING_KEY'] = 'test.prepare-template'

        # Run the script and test prepare-template
        result = subprocess.run(['python3', 'app/main.py'], capture_output=True, text=True, env=env)

        # Check if the script ran without errors
        self.assertEqual(result.returncode, 0, msg=f"Script failed with the following error: {result.stderr} and {result.stdout}")

        # Check if the process-output.json file exists
        with open(f"{env['CINCODEBIO_JOB_ID']}/prepare-template-output.json") as json_file:
            po = json.load(json_file)  
        
        # assert it versus the output schema - this is always a url? 
        PrepareTemplateOutputSchema = {{ PrepareTemplateOutputSchema }}

        # Check if all the files referenced in process-output.json exist
        try:
            frontend_url = po['url']
            # Check if the file is readable and if it is valid html
            is_valid_html(frontend_url)
        except Exception as e:
            self.fail(f"Error reading rendered front-end template {e}")

        # Specify the directories to remove
        directories = [Path(os.getcwd()) / env['CINCODEBIO_JOB_ID'], Path(os.getcwd()) / env['CINCODEBIO_WORKFLOW_ID']]

        # Remove the directories
        for directory in directories:
            try:
                shutil.rmtree(directory)
            except Exception as e:
                ...
           

        # Now test the process implementation

        # This needs to be generated for the service from the schema
        env['CINCODEBIO_DATA_PAYLOAD'] = json.dumps({{ ProcessInputData }})
        env['CINCODEBIO_ROUTING_KEY'] = 'test.process'

        # Run the script
        result = subprocess.run(['python3', 'app/main.py'], capture_output=True, text=True, env=env)

        # Check if the script ran without errors
        self.assertEqual(result.returncode, 0, msg=f"Script failed with the following error: {result.stderr} and {result.stdout}")

        # Check if the process-output.json file exists
        with open(f"{env['CINCODEBIO_JOB_ID']}/process-output.json") as json_file:
            po = json.load(json_file)  
        
        # assert it versus the output schema
        ProcessOutputSchema = {{ ProcessOutputSchema }}

        try: 
            validate_versus_schema(ProcessOutputSchema, po)
        except Exception as e:
            self.fail(f"The output file doesn't match the Output Schema {e}")

        # Check if all the files referenced in process-output.json exist
        try:
            if 'data' in po.keys():
                print_urls(po['data'])
        except Exception as e:
            self.fail(f"Atleast one file which referenced in process-output does not exist {e}")

        # Specify the directories to remove
        directories = [Path(os.getcwd()) / env['CINCODEBIO_JOB_ID'], Path(os.getcwd()) / env['CINCODEBIO_WORKFLOW_ID']]

        # Remove the directories
        for directory in directories:
            try:
                shutil.rmtree(directory)
            except Exception as e:
                ...
if __name__ == '__main__':
    unittest.main()

{%- endmacro %}

{% if isAutomated == True %}
{{-  printAutomated(InputData,OutputSchema) }}
{% else %}
{{-  printInteractive(PrepareTemplateInputData,PrepareTemplateOutputSchema,ProcessInputData,ProcessOutputSchema) }}
{% endif %}"""




class TestGenerator:

    def __init__(self, dataclass_schemas: dict) -> None:
        self.dataclass_schemas = dataclass_schemas
        self.NUM_OF_CELLS = 1000
        self.WIDTH_OF_IMAGE = 5000
        self.HEIGHT_OF_IMAGE = 5000
        self.data_type_set = [cm for cm in dir(cm_data) if not cm.startswith('_')]

    @staticmethod
    def max_image_8bit(w=5000,h=5000):
        return Image.fromarray(np.ones((w,h),dtype=np.uint8)*255)

    # Falty Image
    @staticmethod
    def min_image_bit(w=5000,h=5000):
        return Image.fromarray(np.zeros((w,h),dtype=np.uint8))

    # Closest to real image
    @staticmethod
    def random_image_8bit(w=5000,h=5000):
        return Image.fromarray(np.random.randint(0,255,(w,h),dtype=np.uint8))
    
    @staticmethod
    def random_bool():
        return np.random.choice([True,False])

    @staticmethod
    def random_float(mnv = 0, mxv=1.0):
        return np.random.uniform(mnv,mxv)

    @staticmethod
    def random_int(mnv = 0, mxv=100):
        return np.random.randint(mnv,mxv)
    
    @staticmethod
    def random_str(lenght=10):
        import string
        alphanumeric_list = list(string.ascii_letters + string.digits)
        return ''.join(random.choices(alphanumeric_list, k=lenght))
    
    @staticmethod
    def random_str_set(qty=10):
        return [TestGenerator.random_str(TestGenerator.random_int(3,10)) for _ in range(qty)]

    @staticmethod
    def generate_dataframe(schema,WIDTH_OF_IMAGE, num_rows=100,N=1):
        data = {}
        for column, data_type in schema.items():
            if column == '*':
                for i in range(N):
                    if data_type == int:
                        data[f'A{i}'] = [random.randint(1, WIDTH_OF_IMAGE) for _ in range(num_rows)]
                    elif data_type == float:
                        data[f'A{i}'] = [random.uniform(0, 1000) for _ in range(num_rows)]
                    elif data_type == str:
                        data[f'A{i}'] = [''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=10)) for _ in range(num_rows)]
                    elif data_type == bool:
                        data[f'A{i}'] = [random.choice([True, False]) for _ in range(num_rows)]
                    else:
                        data[f'A{i}'] = [None] * num_rows

                continue

            if data_type == int:
                data[column] = [random.randint(1, 20) for _ in range(num_rows)]
            elif data_type == float:
                data[column] = [random.uniform(0, 1) for _ in range(num_rows)]
            elif data_type == str:
                data[column] = [''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=10)) for _ in range(num_rows)]
            elif data_type == bool:
                data[column] = [random.choice([True, False]) for _ in range(num_rows)]
            else:
                data[column] = [None] * num_rows
        
        df = pd.DataFrame(data)
        return df

    @staticmethod
    def generate_roi(WIDTH_OF_IMAGE, HEIGHT_OF_IMAGE):
        
        img_w = TestGenerator.random_int(1000,WIDTH_OF_IMAGE)
        img_h = TestGenerator.random_int(1000,HEIGHT_OF_IMAGE)
        x1 = TestGenerator.random_int(0,img_w-100)
        y1 = TestGenerator.random_int(0,img_h-100)
        x2 = TestGenerator.random_int(x1,img_w)
        y2 = TestGenerator.random_int(y1,img_h)
        return {
        'x1': x1,
        'y1': y1,
        'x2': x2,
        'y2': y2,
        'img_w': img_w,
        'img_h': img_h
        }

    # Fuction for extracting the schema for service fcn, so test data can be generated
    def recurse_schema(self,js, depth=0):
        dct = {}
    
        for v in js['FIELDS']:
            # must be an enum
            if 'type' not in v.keys():
                ...

            elif v['type'] in js.keys():
                if js[v['type']]['CLASS_TYPE'] == 'enum':
                    dct[v['name']]=js[v['type']]
                else:
                    dct[v['name']] = self.recurse_schema(js[v['type']], depth+1)

            else:
                if 'metadata' in v.keys():
                    if v['metadata'] != None:
                        dct[v['name']] = (v['type'], v['metadata'])
                    else:
                        dct[v['name']] = v['type']
                else:
                    dct[v['name']] = v['type']

        return dct


    # If image or csv generate the file and write to disk
    def generate_test_data(self,schema,indent=0, N = 1, j=0, prefix=Prefix('')):
        # string mixin;
        master = None

        if type(prefix) == tuple:
            j = prefix[1]
            prefix = Prefix('')


        try:
            if 'data' in schema.__annotations__.keys():

                if schema.__annotations__['data'].__origin__ == dict:
                        if schema.__annotations__['data'].__args__[0] == str:
                            # print(indent*'  ',schema)
                            master = {f'A{i}': self.generate_test_data(schema.__annotations__['data'].__args__[1], indent=indent+1, N=N,j=i, prefix=prefix.add_level(f'A{j}') if type(j) == int else prefix.add_level(j)) for i in range(N)}
                elif schema.__annotations__['data'].__origin__ == list:
                    # print(indent*'  ',schema)

                    master = [self.generate_test_data(schema.__annotations__['data'].__args__[0], indent=indent+1, N=N, j=i, prefix=prefix.add_level(f'A{j}') if type(j) == int else prefix.add_level(j)) for i in range(N)]

            else:
                
                if issubclass(schema, Atomic):
                    # This is the case when there is no recursion (i.e. the dataclass contains atomic types)
                    if indent == 0:
                        prefix = Prefix(j)
                        j = 0
                    
                    if issubclass(schema, OMETIFF):
                        
                        master = schema.write(img=self.random_image_8bit(self.WIDTH_OF_IMAGE,self.HEIGHT_OF_IMAGE),image_name=f'A{j}',prefix=prefix.add_level(f'{j}') if prefix == '' else prefix)
                    
                    elif issubclass(schema, CSV):
                        print(prefix,j)
                        master = schema.write(df=self.generate_dataframe(schema._SCHEMA, self.WIDTH_OF_IMAGE, num_rows=self.NUM_OF_CELLS,N=N),filename=f'A{j}',prefix=prefix.add_level(f'{j}') if prefix == '' else prefix)

                    # this is the RegionOfInterest case
                    elif issubclass(schema, RegionOfInterest):
                        master = self.generate_roi(self.WIDTH_OF_IMAGE, self.HEIGHT_OF_IMAGE)

                    # master = schema
                elif issubclass(schema, NonAtomic):
                    # print(indent*'  ',schema)
                    master = {k:self.generate_test_data(v, indent=indent+1,N=N, j=k,prefix=prefix.add_level(f'{j}') if prefix == '' else prefix.add_level(f'A{j}')) for k,v in schema.__annotations__.items()}
                        

        except Exception as e:
            if issubclass(schema, StringMixin):
                master = random.choice([f'A{k}' for k in range(N)])
            elif schema == int:
                master = self.random_int(mnv=1)
            elif schema == float:
                master = self.random_float()
            elif schema == str:
                master = self.random_str()
            elif schema == bool:
                master = self.random_bool()
            else:  
                raise e

        return master

    def recursive_iterate(self,dictionary, N=1,base_dir = '/tests/data'):
        temp = {}
        for key, value in dictionary.items():
            if isinstance(value, dict):
                # Enum case
                if 'CLASS_TYPE' in value.keys():
                    temp[key]= random.choice(value['FIELDS'])['value'].replace("'","")
                # Nested Dict Case
                else:
                    temp[key] = self.recursive_iterate(value, N=N, base_dir=base_dir)
            else:
                # Semantic Type Case
                if value in self.data_type_set:
                    temp[key] = self.generate_test_data(eval(f'cm_data.{value}'),N=N, prefix=(None,f'{base_dir}/{key}'))
                # Field with metadata (case)
                elif type(value) == tuple:
                    if value[0] == 'int':
                        temp[key] = self.random_int(mnv=value[1]['min'],mxv=value[1]['max'])
                    elif value[0] == 'float':
                        temp[key] = self.random_float(mnv=value[1]['min'],mxv=value[1]['max'])
                    # could be more cases here (i.e. metadata for strings, bools etc., but for now just do the int and float case)
                else:
                    if value == 'int':
                        temp[key] = self.random_int(mnv=1)
                    elif value == 'float':
                        temp[key] = self.random_float()
                    elif value == 'str':
                        temp[key] = self.random_str()
                    elif value == 'bool':
                        temp[key] = self.random_bool()
                    else:  
                        # this doesn't work correcty for fields with metadata
                        temp[key]= value
        
        return temp
    


    def generate_tests(self):

        og_cwd = os.getcwd()
       

        try:
            os.makedirs('tests/scripts')
            os.makedirs('tests/data')
        except:
            ...
        # Create a Jinja environment
        env = jinja2.Environment()
        # Load the template from the docstring
        template = env.from_string(test_template)

        # 
        if self.dataclass_schemas['service_type'] == 'interactive':
            # Render the template with variables
            i1 = self.recurse_schema(self.dataclass_schemas['prepare_template_input'])
            # generate data and create mock input
            if1 = self.recursive_iterate(i1)

            # this isn't actually used in the template? - but generate anyways
            o1 = self.recurse_schema(self.dataclass_schemas['prepare_template_output'])

            i2 = self.recurse_schema(self.dataclass_schemas['process_input'])
            # generate data and create mock input
            if2 = self.recursive_iterate(i2)

            o2 = self.recurse_schema(self.dataclass_schemas['process_output'])


            rendered_template = template.render(
                PrepareTemplateInputData=if1, 
                PrepareTemplateOutputSchema=o1,
                ProcessInputData=if2,
                ProcessOutputSchema=o2,
                isAutomated=False)
            
            f = open('tests/scripts/__init__.py', 'w')
            f = open('tests/scripts/test_1.py', 'w')
            f.write(rendered_template)


        else:

            # generate data base dir = 
            # os.chdir(og_cwd + '/tests/data')
            i1= self.recurse_schema(self.dataclass_schemas['process_input'])
            # generate data and create mock input
            if1 = self.recursive_iterate(i1)

            o1 = self.recurse_schema(self.dataclass_schemas['process_output'])
            
            # os.chdir(og_cwd + '/tests/scripts')
            rendered_template = template.render(InputData=if1, OutputSchema=o1,isAutomated=True)
            f = open('tests/scripts/__init__.py', 'w')
            f = open('tests/scripts/test_1.py', 'w')
            f.write(rendered_template)



        # Render the template with variables
       

        # Print the rendered template
        # print(rendered_template)



DOCKERFILE_TEMPLATE = """FROM {{ DockerImage }} as builder

COPY requirements.txt .
COPY app/ app/
COPY tests/ tests/
RUN pip install -r requirements.txt --no-cache-dir
# Run the tests
RUN python -m unittest discover -s tests/scripts/ -p 'test_*.py' 


# Second stage: build the final image without test data
FROM {{ DockerImage }}

COPY --from=builder /app /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

WORKDIR /app

CMD ["python", "main.py"]
"""

REQURIEMENTS_TEMPLATE = f"""{__library_name__}
"""

SERVICE_TEMPLATE = """# required imports
from dataclasses import dataclass
from enum import Enum
from {{ sdk_name }}.data import * # change this to the correct import (i.e. exact data classes that are needed)
from {{ sdk_name }} import data_utils
from {{ sdk_name }}.process import {{ process_type }}, {% if is_automated == True %}Automated{% else %}Interactive{% endif %}

# add additional imports below here:

{%- macro generateInteractiveBlueprint(serviceName,processType) %}
# What comes from the execution environment (SIB input)
@dataclass
class {{ serviceName }}PrepareTemplateInput:
    @dataclass
    class SystemParameters:
        @dataclass
        class DataFlow:
            #key: bool - the keys need to match the keys for Data & WorkflowParameters in the {{ serviceName }}ProcessOutput
            #e.g.: whole_slide_image: bool
            ...
        data_flow: DataFlow

    # add the dataclass(es) that are needed for the input, e.g. Data, WorkflowParameters
    #@dataclass
    #class Data:
    #    data_name: data_type
    
    #data: Data
    #workflow_parameters: WorkflowParameters
    system_parameters: SystemParameters

# The HTML Front end (Do not change this class)
@dataclass
class {{ serviceName }}PrepareTemplateOutput:
    html: str

# What the user submits from the Interaction via the front end
@dataclass
class {{ serviceName }}ProcessInput:
    @dataclass
    class WorkflowParameters:
        ...

    workflow_parameters: WorkflowParameters

# What is returned to the Execution Environment (SIB Output)
@dataclass
class {{ serviceName }}ProcessOutput:
    # add the dataclass(es) that are needed for the output, e.g. Data, WorkflowParameters
    #@dataclass
    #class Data:
    #    data_name: data_type
    
    class Control(str, Enum):
        # add the possible values for control flow here.
        success = 'success'

    #data: Data
    #workflow_parameters: WorkflowParameters
    # If there is no decision made in the Control set default to success
    control: Control = Control.success
    


class {{ serviceName }}({{ processType }},Interactive):
    _ROUTING_KEY = '{{ serviceName }}'
    _a = 'prepare-template'
    _b = 'process'

    def __init__(self) -> None:
        super().__init__()

    def deserialize_prepare_template_input(self, body) -> {{ serviceName }}PrepareTemplateInput:
        # Can this be abstract away?
        return data_utils.decode_dict(data_class={{ serviceName }}PrepareTemplateInput,data=body)


    def prepare_template(self, prefix, submit_url, input: {{ serviceName }}PrepareTemplateInput) -> {{ serviceName }}PrepareTemplateOutput:
        # Logic for populating the front end template (using input ({{ serviceName }}PrepareTemplateInput Object))
        
        template = self.env.get_template('your-template.html.j2')
        return {{ serviceName }}PrepareTemplateOutput(
            html=template.render(endpoint=submit_url, # add additional kwargs here
            ))

    def deserialize_process_input(self,body) -> {{ serviceName }}ProcessInput:
        return data_utils.decode_dict(data_class={{ serviceName }}ProcessInput,data=body)

    def process(self, prefix, input: {{ serviceName }}ProcessInput) -> {{ serviceName }}ProcessOutput:
        # Logic for processing the user input (using input ({{ serviceName }}ProcessInput Object))
        
        # Instantiate the Output dataclass you have defined above.
        return {{ serviceName }}ProcessOutput()

{%- endmacro %}

{%- macro generateAutomatedBlueprint(serviceName,processType) %}
# What comes from the execution environment (SIB input)
@dataclass
class {{ serviceName }}ProcessInput:
    @dataclass
    class SystemParameters:
        @dataclass
        class DataFlow:
            #key: bool - the keys need to match the keys for Data & WorkflowParameters in the {{ serviceName }}ProcessOutput
            #e.g.: whole_slide_image: bool
            ...
        data_flow: DataFlow

    # add the dataclass(es) that are needed for the input, e.g. Data, WorkflowParameters
    #@dataclass
    #class Data:
        #whole_slide_image: WholeSlideImage


    system_parameters: SystemParameters
    #data: Data
    #workflow_parameters: WorkflowParameters

# What is returned to the Execution Environment (SIB Output)
@dataclass
class {{ serviceName }}ProcessOutput:

    class Control(str, Enum):
        # add the possible values for control flow here.
        success = 'success'

    # add the dataclass(es) that are needed for the output, e.g. Data, WorkflowParameters
    #@dataclass
    #class Data:
        #whole_slide_image: WholeSlideImage
    
    
    # If there is no decision made in the Control set default to success
    control: Control = Control.success
    #data: Data
    #workflow_parameters: WorkflowParameters
    


class {{ serviceName }}({{ processType }},Automated):
    _ROUTING_KEY = '{{ serviceName }}'

    def __init__(self) -> None:
        super().__init__()

    def deserialize_process_input(self,body) -> {{ serviceName }}ProcessInput:
        return data_utils.decode_dict(data_class={{ serviceName }}ProcessInput,data=body)

        
    def process(self, prefix, input: {{ serviceName }}ProcessInput) -> {{ serviceName }}ProcessOutput:
        # Logic for processing the input (using input ({{ serviceName }}ProcessInput Object))
        # I.e. main logic of your service
        
        
        # Instantiate the Output dataclass you have defined above.
        return {{serviceName }}ProcessOutput()
        
{%- endmacro %}


{% if is_automated == True %}
{{-  generateAutomatedBlueprint(service_name,process_type) }}
{% else %}
{{-  generateInteractiveBlueprint(service_name,process_type) }}
{% endif %}
if __name__ == "__main__":
    {{ service_name }}().run()
"""

import re

def camel_to_snake(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def init_service_directory(service_name: str, process_type, aut_int: bool, python_ver: str = None, _docker_image : str = None):
    """
        aut_int: True if the service is automated, False if the service is interactive
    """
    if python_ver:
        docker_image = f"python:{python_ver}-slim"
    elif _docker_image:
        docker_image = _docker_image

    # Create a Jinja environment
    env = jinja2.Environment()
    # Load the template from the docstring
    dfile_temp = env.from_string(DOCKERFILE_TEMPLATE)
    # Load the service template from the docstring
    sfile_temp = env.from_string(SERVICE_TEMPLATE)



    cwd = os.getcwd()
    # Create a new directory with the service name
    base_dir = pathlib.Path(cwd) / camel_to_snake(service_name)
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(base_dir / 'app', exist_ok=True)

    # Create the requirements.txt file
    with open(base_dir / 'requirements.txt', 'w') as f:
        f.write(REQURIEMENTS_TEMPLATE)
    
    # Create the Dockerfile
    rendered_dfile = dfile_temp.render(
        DockerImage=docker_image)
    
    with open(base_dir / 'Dockerfile', 'w') as f:
        f.write(rendered_dfile)

    # Create the main.py file
    rendered_sfile = sfile_temp.render(
        service_name=service_name, 
        process_type= process_type, 
        is_automated=not aut_int, 
        sdk_name= __library_name__)
    
    with open(base_dir / 'app' / 'main.py', 'w') as f:
        f.write(rendered_sfile)

    if aut_int:
        os.makedirs(base_dir / 'app' / 'templates', exist_ok=True)
        with open(base_dir / 'app' / 'templates' / 'your-template.html.j2', 'w') as f:
            f.write('')

def delete_cdb_labaels_with_regex(input_file):
    """
    Delete lines from a file that match a specific regex pattern.
    
    Args:
    input_file (str): Path to the input file
    output_file (str): Path to the output file
    pattern (str): Regex pattern to match lines for deletion
    """

    pattern = r"""(\n)*LABEL cincodebio[a-zA-Z0-9\(\)\.='{\"_: ,[}\] ]* \\ 
 cincodebio.ontology_version='[a-zA-Z0-9~\+_\.]*'"""
    
    try:
        # Read the input file
        with open(input_file, 'r') as file:
            file_txt = file.read()
        
        # Filter out lines that match the pattern
        

        # Write the filtered lines to the output file
        with open(input_file, 'w') as file:
            file.write(re.sub(pattern, '', file_txt))
        
        print(f"Lines matching '{pattern}' have been deleted.")
    
    except FileNotFoundError:
        print(f"Error: File {input_file} not found.")
    except Exception as e:
        print(f"An error occurred: {e}")