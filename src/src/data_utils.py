
from typing import Any, Optional, TypeVar, Type, Mapping, Union


_T = TypeVar("_T")

def decode_dict(data: Mapping[str, Any], data_class: Type[_T], indent = 0):
    # prevent circular import
    from ._data import NonAtomic, Atomic
    args = {}
    for k,v in data_class.__annotations__.items():
        # for handling Optional typescle
        if k == '_SCHEMA':
            # This is the case for the schemas in Dataframes (should be skipped), could generalise this to?
            continue
        if hasattr(v, '__origin__'):
            if v.__origin__ == Union or v.__origin__ == Optional:
                v = v.__args__[0]
                print(f'Optional type {v}')
                if k not in data:
                    args[k] = None
                    continue
        if not issubclass(v,NonAtomic) and type(data[k]) == dict:
            args[k] = decode_dict(data[k],v,indent=indent+1)
        elif issubclass(v,NonAtomic):
            args[k]=v.decode(data[k])
        elif issubclass(v,Atomic):
            args[k] = v.decode(data[k])
        else:
            # for primitive types -> Assert the type
            assert v == type(data[k]), f'Expected {v} but got {type(data[k])}'
            args[k] = data[k]
    
    
    return data_class(**args)


def encode_dataclass(data_class: Any,indent=0):
    # ISSUE: Need to prevent encode being called on strings ->
    # prevent circular import
    from ._data import NonAtomic, Atomic
    """
        To make a more straightword API for developers; the SDK uses objects that cannot 
        be represented in the OpenAPI format. This converts to the dataclass to an OpenAPI compliant format.
        Each non-atomic data class has a encode (and decode) method implemented which facilitates this.

        Note[12.02.24] -> now that the fastapi models are using RootModel, this is no longer neccessary to a certain extent
            other than the fact the all models which are hashmap or list-mixins use a dict or list internally to store the data and this
            returns the data as if that is not the case 


        And so on (it's recursive through all the layers of Non-Atomic data classes)!
    """
    args = {}
    for k,v in data_class.__annotations__.items():
        
        if k == '_SCHEMA':
            continue
        # For encoding optional classes
        if hasattr(v, '__origin__'):
            if v.__origin__ == Union or v.__origin__ == Optional:
                v = v.__args__[0]
                # This is the case for the optional types that haven't been set
                if data_class.__getattribute__(k) == None:
                    continue

        
        if not issubclass(v,NonAtomic):
            try:
                # This is the case for the atomic classes and dataclasses (such a WorkflowParameters, etc.)
                args[k] = encode_dataclass(data_class.__getattribute__(k),indent+1)
            except AttributeError:
                try :
                    # This is the case for enums?
                    args[k] = data_class.__getattribute__(k).name
                except AttributeError:
                    # Atomic Classes
                    if issubclass(v,Atomic): 
                        args[k] = data_class.__getattribute__(k).encode()
                    # Primitive types/enums
                    else: 
                        args[k] = data_class.__getattribute__(k)

        else:
            # This is the case for the non-atomic classes
            if type(data_class.__getattribute__(k)) == str:
                args[k] = data_class.__getattribute__(k)
            else:
                args[k] = data_class.__getattribute__(k).encode()

    return args



# System Parameters - move this from data (as it's not a data class per se, more of a utility class for writing data to the object store)
class Prefix(str):
    """
        This is a semantic wrapper for a prefix
    """
    # rather than using the string mixin as it leads to circular import
    def append(self, text):
        # Custom method to append text to the string
        return self.__class__(self + text)

    def reverse(self):
        # Custom method to reverse the string
        return self.__class__(self[::-1])

    def __new__(cls, value):
        return super().__new__(cls, value)
    
    def add_level(self, level: str) -> "Prefix":

        return Prefix(f'{self}{level}/')