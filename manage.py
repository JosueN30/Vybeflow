
import importlib.util
import sys
import os

# Ensure current directory is in sys.path for local imports
sys.path.insert(0, os.path.dirname(__file__))

# Dynamically import 'Vybeflow-main' as a module
module_name = 'Vybeflow-main'
module_path = os.path.join(os.path.dirname(__file__), '__init__.py')
spec = importlib.util.spec_from_file_location(module_name, module_path)
vybeflow_main = importlib.util.module_from_spec(spec)
sys.modules[module_name] = vybeflow_main
spec.loader.exec_module(vybeflow_main)

# Use the main app factory (returns (app, socketio)); only need app for management tasks.
from app import create_app as _create_app
app, _ = _create_app()
