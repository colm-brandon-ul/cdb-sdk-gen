class DependencyManager:
    def __init__(self):
        self._modules = {}

    def require(self, *packages):
        """Import and return one or more packages"""
        results = []
        for package in packages:
            if package not in self._modules:
                try:
                    self._modules[package] = __import__(package)
                except ImportError:
                    raise ImportError(f"Required dependency {package} not installed")
            results.append(self._modules[package])
        return results[0] if len(results) == 1 else results

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