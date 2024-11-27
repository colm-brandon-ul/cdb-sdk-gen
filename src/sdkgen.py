import hashlib
import os
from ontparse import OWLParser
import ast
from typing import List, Tuple
import rdflib
import enum
from jinja2 import Environment, FileSystemLoader
import black
import pathlib
import shutil
import argparse
import _config

class DataModelType(str, enum.Enum):
    DataStructure = 'DataStructure'
    Primitive = 'Primitive'
    AtomicFile = 'AtomicFile'
    ClassWithAttributes = 'ClassWithAttributes'


class SdkCodeGen:
    def __init__(self,ontology_path, template_path = './templates', only_descendants_of = None):
        self.parser = OWLParser()
        self.sdk_name = None
        self.parser.load_ontology(ontology_path,only_descendants_of)
        self.env = Environment(loader=FileSystemLoader(template_path))
        self.data_template = self.env.get_template('semantic_data_classes.py.j2')
        self.processor_template = self.env.get_template('semantic_process_classes.py.j2')
        self.pyproject_template = self.env.get_template('pyproject.toml.j2')
        self.init_template = self.env.get_template('__init__.py.j2')
        self.base_source_path = f'{_config.BASE_DIR}/src'
        self.cdb_filehandlers_path = f'{_config.BASE_DIR}/src/_data.py'
        self.service_concept_class = rdflib.URIRef('http://www.cincodebio.org/cdbontology#ServiceConcept')
        self.data_class = rdflib.URIRef('http://www.cincodebio.org/cdbontology#Data')
        self.file_class = rdflib.URIRef('http://www.cincodebio.org/cdbontology#File')
        self.data_structure_class = rdflib.URIRef('http://www.cincodebio.org/cdbontology#DataStructure')
        self.primitive_class = rdflib.URIRef('http://www.cincodebio.org/cdbontology#Primitive')
        self.map2type = {
            'HashMap' : 'Dict',
            'List' : 'List',
            'Set' : 'Set',
            'String' : 'str',
            'Integer' : 'int',
            'Float' : 'float',
            'Double' : 'float',
        }
        self.data_imports = set()
        self.sc_data_imports = set()

    def strip_namespace(self,uri):
        return uri.split('#')[-1]
      
    def _check_import(self,node):
        return self.parser.is_descendant_of(rdflib.URIRef(node),self.primitive_class) or self.parser.is_descendant_of(rdflib.URIRef(node),self.data_structure_class)
    
    def serialize_type(self, py_type):
        type_map = {
            str: 'str',
            int: 'int',
            float: 'float',
            bool: 'bool',
            list: 'List',
            dict: 'Dict',
            set: 'Set',
            tuple: 'Tuple',
            None: 'NoneType'
        }
        return type_map.get(py_type, str(py_type))
    

    
    def get_models(self):
        pn = self.parser.get_primary_namespace()
        data_models,service_concept_models = [],[]
        # iterate over the topologically sorted nodes
        for node in self.parser.topo_sort_nodes_inheritance_and_attributes_graph:
            # check if node is a descendant of the primary namespace and not cdbontology
            if node.startswith(str(pn)):
                if self.parser.is_descendant_of(rdflib.URIRef(node),self.service_concept_class):
                    temp = {}
                    temp.setdefault('name',self.strip_namespace(node))
                    node_details = self.parser.inheritance_only_graph.__dict__.get('_node').get(node)
                    models = []

                    if 'attributes' in node_details.keys():
                        for atr in node_details.get('attributes'):
                            local_temp = {}
                            for k,v in atr.items():
                                if type(v) == dict:
                                    local_temp.setdefault('hasInput',[])
                                    local_temp.setdefault('hasOutput',[])
                                    for k1,v1 in v.items():
                                        if type(v1) == list:
                                            local_temp.get(self.strip_namespace(k1)).extend([self.strip_namespace(i) for i in v1])
                                        else: 
                                            local_temp.get(self.strip_namespace(k1)).append(self.strip_namespace(v1))
                                        
                                else:
                                    raise ValueError('Attribute value must be a dict')
                            [self.sc_data_imports.add(di) for di in  local_temp.get('hasInput')]
                            [self.sc_data_imports.add(di) for di in  local_temp.get('hasOutput')]
                            models.append(local_temp)
                    temp.setdefault('models',models)
                    service_concept_models.append(temp)
                elif self.parser.is_descendant_of(rdflib.URIRef(node),self.data_class):
                    temp = {}
                    temp.setdefault('name',self.strip_namespace(node))
                    # get node details from nx graph
                    node_details = self.parser.inheritance_only_graph.__dict__.get('_node').get(node)

                    temp.setdefault('super_classes',[self.strip_namespace(sc) for sc in node_details.get('super_class_edges')])
                    # get import for data classes

                    # need to check if they're a mixin or not..

                    for sc in node_details.get('super_class_edges'):
                        if sc.startswith(str(self.parser.cdb_nspace)):
                            
                            if self._check_import(sc):
                                self.data_imports.add(f'{self.strip_namespace(sc)}Mixin')
                            else:
                                self.data_imports.add(self.strip_namespace(sc))

                    temp.setdefault('docs',node_details.get('comment'))
                    # check if is a data structure or a primitive type, else file or normal class
                    is_file = any(self.parser.is_descendant_of(rdflib.URIRef(sc),self.file_class) for sc in node_details.get('super_class_edges'))
                    is_data_structure = any(self.parser.is_descendant_of(rdflib.URIRef(sc),self.data_structure_class) for sc in node_details.get('super_class_edges'))
                    is_primitive = any(self.parser.is_descendant_of(rdflib.URIRef(sc),self.primitive_class) for sc in node_details.get('super_class_edges'))
                    # if not a file, data structure or primitive type, then it is a class with attributes
                    is_class_with_attributes = not any([is_file,is_data_structure,is_primitive])
                    # if is a class with attributes, then add attributes key to temp
                    if is_class_with_attributes:
                        temp.setdefault('attributes',[])

                    # if node has attributes, then iterate over them
                    if 'attributes' in node_details.keys():
                        for attribute in node_details['attributes']:
                            for k,v in attribute.items():
                                # if attribute value is a list, then iterate over it, 
                                if type(v) == list:
                                    for i in v:
                                        if is_data_structure:
                                            temp.setdefault(
                                                'typeParameters',[]).append(
                                                    self.map2type.get(
                                                        self.strip_namespace(i),
                                                        self.strip_namespace(i)))
                                        else:
                                            raise ValueError('Only DataStruct value should be a list')
                                elif type(v) == dict:
                                    local_temp = {'decode_encode':True} # flag to indicate if attribute should be decoded or encoded
                                    # iterate over the key value pairs of the attribute
                                    for k1,v1 in v.items():
                                        if is_data_structure:
                                            raise ValueError('DataStruct Attribute value must be a list')
                                        elif is_file:
                                            # need to handle Schema properties here..
                                            temp.setdefault('schema',[])
                                            if type(v1) == type:
                                                
                                                local_temp[self.strip_namespace(k1)] = self.serialize_type(v1)
                                            else:
                                                
                                                local_temp[self.strip_namespace(k1)] = v1.strip()
                                        # Class with attributes
                                        else:
                                            if type(v1) == type:
                                                local_temp[self.strip_namespace(k1)] = self.serialize_type(v1)
                                                local_temp['decode_encode'] = False
                                            else:
                                                local_temp[self.strip_namespace(k1)] = self.strip_namespace(v1).strip()
                                    # temporary fix for now -> need to handle schema properties
                                    if is_class_with_attributes:    
                                        temp.get('attributes').append(local_temp)
                                    if is_file and 'schema' in temp.keys():
                                        temp.get('schema').append(local_temp)

                                else:
                                    raise ValueError('Attribute value must be a list or dict')

                        # print()
                    
                    # check if is a data structure or a primitive type, else file or normal class
                    if is_file:
                        temp.setdefault('type', DataModelType.AtomicFile.value)
                    elif is_data_structure:
                        temp.setdefault('type', DataModelType.DataStructure.value)
                        # filter out super classes that are not data structures
                        ds_sc = [sc for sc in node_details.get('super_class_edges') if self.parser.is_descendant_of(rdflib.URIRef(sc),self.data_structure_class)]
                        assert len(ds_sc) == 1, 'Data Structure must have exactly one super class that is a data structure'
                        temp.setdefault('data_structure_superclass',self.strip_namespace(ds_sc[0]))
                    elif is_primitive:
                        temp.setdefault('type', DataModelType.Primitive.value)
                        # filter out super classes that are not primitives
                        p_sc = [sc for sc in node_details.get('super_class_edges') if self.parser.is_descendant_of(rdflib.URIRef(sc),self.primitive_class)]
                        assert len(p_sc) == 1, 'Primitive must have exactly one super class that is a primitive'
                        temp.setdefault('primitiveType',self.map2type.get(self.strip_namespace(p_sc[0])))
                    
                    elif is_class_with_attributes:
                        temp.setdefault('type', DataModelType.ClassWithAttributes.value)
                    else:
                        raise ValueError('Unknown data model type')
                    
                    data_models.append(temp)

        return data_models, service_concept_models
    
    def get_version_info(self) -> Tuple[str,str]:
        query = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?s ?version ?label
        WHERE {
            ?s a owl:Ontology .
            OPTIONAL { ?s owl:versionInfo ?version }
            OPTIONAL { ?s rdfs:label ?label }
        }
        """
        
        # Execute the query
        results = self.parser.graph.query(query)
        
        ds = None
        cdb = None
        # Collect results
        version_info = []
        results = list(results)

        assert len(results) == 2, 'There should be exactly two version info properties in the ontology'


        for row in results:
            if 'cincodebio' in str(row.label):
                cdb = str(row.version)

            else:
                ds_ontology_name = str(row.label)
                ds = str(row.version)
            
        assert ds is not None and cdb is not None, 'Both version info properties must be present in the ontology'
        
        return ds,cdb, ds_ontology_name
        
    

    def check_available_file_handlers(self,file_path) -> List[dict]:
        """
        Parse a Python file and extract information about its classes.
        
        Args:
            file_path (str): Path to the Python file to parse
            
        Returns:
            List[dict]: List of dictionaries containing class information
        """
        try:
            with open(file_path, 'r') as file:
                tree = ast.parse(file.read())
                
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = {
                        'name': node.name,
                        'line_number': node.lineno,
                        'methods': [],
                        'base_classes': [base.id for base in node.bases if isinstance(base, ast.Name)]
                    }
                    
                    # Get methods in the class
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_info = {
                                'name': item.name,
                                'line_number': item.lineno,
                                'decorators': [
                                    decorator.id if isinstance(decorator, ast.Name) else None
                                    for decorator in item.decorator_list
                                ]
                            }
                            class_info['methods'].append(method_info)
                    
                    classes.append(class_info)
                    
            return classes
            
        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found.")
            return []
        except SyntaxError as e:
            print(f"Error: Invalid Python syntax in file: {e}")
            return []

    def copy_core_sdk_to_output(self, gen_path: pathlib.Path ):
        files = [f for f in os.listdir(self.base_source_path) if f.endswith('.py')]
        for f in files:
            try:
                shutil.copy(pathlib.Path(self.base_source_path) / f, gen_path /  f)
            except Exception as e:
                print(f'Error copying file {f} {e}')

    def generate_sdk(self):
        ds_version,cdb_version,ds_onto_name = self.get_version_info()

        base_path = pathlib.Path(os.getcwd()) / pathlib.Path("gen")
        src_path = pathlib.Path(_config.BASE_DIR) / pathlib.Path("src")
        gen_src_path = base_path / 'src' / f"cdb_{ds_onto_name.lower()}"
        os.makedirs(gen_src_path,exist_ok=True)

        with open(gen_src_path / '__init__.py','w') as f:
            f.write('')

        self.copy_core_sdk_to_output(gen_src_path)
        available_file_handlers = self.check_available_file_handlers(self.cdb_filehandlers_path)
        dms,scms = self.get_models()
        filtered_dms = []
        print(scms)
        # to do : resolve classes which are not in the available_file_handlers (and any class which depends on them)

        self.data_template.stream(data_imports=list(self.data_imports),data_models=dms).dump(str(gen_src_path / 'data.py'))
        #format/lint the generated code
        with open(gen_src_path / 'data.py','r') as f:
            code = f.read()
            code = black.format_file_contents(code, fast=True,mode=black.FileMode())

        with open(gen_src_path / 'data.py','w') as f:
            f.write(code)

        print(self.sc_data_imports)

        self.processor_template.stream(service_concepts=scms,data_imports=self.sc_data_imports).dump(str(gen_src_path / 'process.py'))
        #format/lint the generated code
        with open(gen_src_path / 'process.py','r') as f:
            code = f.read()
            code = black.format_file_contents(code, fast=True,mode=black.FileMode())
        
        with open(gen_src_path / 'process.py','w') as f:
            f.write(code)

        from rdflib import Graph, OWL, DC
        # Define common version properties
        hash_input = f"{cdb_version}+ds.{ds_version}.{_config.__version__}"
        vhash = hashlib.md5(hash_input.encode()).hexdigest()
        

        self.pyproject_template.stream(cdb_ontology_version=cdb_version,domain_specic_ontology_version=ds_version,code_gen_version=_config.__version__,Ontology_name=ds_onto_name,version_hash = vhash).dump(str(base_path / 'pyproject.toml'))
        self.init_template.stream(cdb_ontology_version=cdb_version,domain_specic_ontology_version=ds_version,code_gen_version=_config.__version__,Ontology_name=ds_onto_name,version_hash = vhash).dump(str(gen_src_path / '__init__.py'))

        with open(base_path / 'LICENSE.txt','w') as f:
            f.write('')


        
if __name__ == '__main__':
    def parse_args():
        parser = argparse.ArgumentParser(description='Generate SDK from OWL ontology.')
        parser.add_argument('ontology_path', type=str, help='Path to the OWL ontology file')
        parser.add_argument('--template_path', type=str, default=f'{_config.BASE_DIR}/templates', help='Path to the Jinja2 templates directory')
        parser.add_argument('--only_descendants_of', type=str, default=None, help='Only include descendants of this class in the ontology')
        return parser.parse_args()

    
    args = parse_args()
    sdk = SdkCodeGen(args.ontology_path, args.template_path, args.only_descendants_of)
    sdk.generate_sdk()
