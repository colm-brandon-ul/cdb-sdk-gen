class DependencyManager:
    def __init__(self):
        self._modules = {}
    
    def require(self, *module_specs):
        """
        Import and return one or multiple modules/submodules
        
        Args:
            *module_specs: Tuples or strings of module specifications
            - For full module: 'numpy'
            - For submodule: ('numpy', 'random')
        
        Returns:
            Single imported module or tuple of imported modules
        """
        results = []
        
        for spec in module_specs:
            # Handle different input formats
            if isinstance(spec, str):
                # Full module import
                module_path = spec
                submodule = None
            elif isinstance(spec, tuple):
                # Submodule import
                if len(spec) == 2:
                    module_path, submodule = spec
                else:
                    raise ValueError(f"Invalid module specification: {spec}")
            else:
                raise TypeError(f"Invalid module specification type: {type(spec)}")
            
            # Normalize the module key
            module_key = f"{module_path}.{submodule}" if submodule else module_path
            
            # Check if the module is already imported
            if module_key not in self._modules:
                try:
                    # If a specific submodule is requested
                    if submodule:
                        # Import the parent module first
                        parent_module = __import__(module_path, fromlist=[submodule])
                        # Get the specific submodule
                        imported_module = getattr(parent_module, submodule)
                    else:
                        # Import the full module
                        imported_module = __import__(module_path)
                    
                    # Store the imported module
                    self._modules[module_key] = imported_module
                
                except (ImportError, AttributeError) as e:
                    if submodule:
                        raise ImportError(f"Could not import submodule {submodule} from {module_path}: {e}")
                    else:
                        raise ImportError(f"Could not import module {module_path}: {e}")
            
            results.append(self._modules[module_key])
        
        # Return single module or tuple based on number of imports
        return results[0] if len(results) == 1 else tuple(results)

class HasDependencies:
    """Mixin class that provides dependency management"""
    _deps = DependencyManager()  # Shared across all instances
    
    @classmethod
    def deps(cls):
        """Access dependencies in class methods"""
        return cls._deps
    
    @property
    def dep(self):
        """Access dependencies in instance methods"""
        return self._deps
    

def requires_dependencies(*dependencies):
    def class_decorator(cls):
        def check_dependencies():
            for dependency in dependencies:
                try:
                    __import__(dependency)
                except ImportError:
                    raise ImportError(f"This class requires {dependency} to be installed")
        
        # Check dependencies when the class is first accessed
        check_dependencies()
        return cls
    return class_decorator