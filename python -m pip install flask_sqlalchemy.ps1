python -m pip install flask_sqlalchemy

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('VYBEFLOW_DB_URI', 'sqlite:///vybeflow.db')