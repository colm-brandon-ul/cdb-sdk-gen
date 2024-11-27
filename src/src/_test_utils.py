import string
from . import data as cm_data
import xml.etree.ElementTree as ET

all_data_types = [cm for cm in dir(cm_data) if not cm.startswith('_')]
# this is temporary due to the encoding issue with the enum values (which will be fixed)
table = str.maketrans('', '', string.punctuation)
primitive = (int, str, float, bool)

def validate_versus_schema(o_s,out):
    # sort the dictionaries by key so they are in the same order
    for (schema_key, schema_value), (output_key, output_value) in zip(dict(sorted(o_s.items())).items(), dict(sorted(out.items())).items()):
        assert schema_key == output_key, f'{schema_key} != {output_key}'
        if type(schema_value) == dict and type(output_value) == dict:
            validate_versus_schema(schema_value, output_value)
        # Could make this completely recursive and have a top level check for list vs dict
        elif type(schema_value) == list and type(output_value) == list:
            assert len(schema_value) == 1, f'SCHEMA LIST CAN ONLY HAVE ONE ITEM'
            assert len(output_value) > 0,  f'{schema_key} is empty'
            # Checks that every item in the output list confoms to the schema
            if eval(schema_value[0]) in primitive:
                for i in range(len(output_value)):
                    assert type(output_value[i]) == eval(schema_value[0]), f'{output_value[i]} is not of type {schema_value[0]}'

            elif schema_value in all_data_types:
                for i in range(len(output_value)):
                    res = eval(f'cm_data.{schema_value[0]}').decode(output_value[i])
        else:
            if schema_value in all_data_types:
                assert output_value != {}, f'{schema_key} is empty'
                res = eval(f'cm_data.{schema_value}').decode(output_value)
            elif type(schema_value) == dict and schema_value['CLASS_TYPE'] == 'enum':
                # currently stripping punctuation from the enum values as they are being encoded with single quotes incorrectly 
                assert output_value in set([x['value'].translate(table) for x in schema_value['FIELDS']]), f'{output_value} not in {schema_value["FIELDS"]}'
            else:
                # if the schema value is a primitive type, then check if the output value is of that type
                if eval(schema_value) in primitive:
                    assert type(output_value) == eval(schema_value), f'{output_value} is not of type {schema_value}'

                else:
                    print((schema_key, schema_value), (output_key, output_value))




def is_valid_html(file_path):
    #    need to come up with a solution for this.
    return True