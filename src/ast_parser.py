import ast
from typing import List, Optional

def get_classes_from_file(file_path: str) -> List[dict]:
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

# Example usage
if __name__ == "__main__":
    # '_write_local', '_read_local', '_buffer_write', '_process_remote_content'

    file_path = "/Users/colmbrandon/cdb-ontology-parser/src/_data.py"
    classes = get_classes_from_file(file_path)
    
    for class_info in classes:
        if 'File' in class_info['base_classes']:
            print(f"Class: {class_info['name']}")
            print(class_info['methods'])
            print()