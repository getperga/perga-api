import json
import os

# Set required environment variables for testing before importing app
os.environ["SECRET_KEY"] = 'test-secret-key'
os.environ["CORS_ORIGINS"] = json.dumps(['http://localhost:5173', 'http://localhost:3000'])
os.environ["IS_SIGNUP_DISABLED"] = "False"

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("POSTGRES_DB", "test_db")


pytest_plugins = [
    'app.tests.fixtures.auth',
    'app.tests.fixtures.database',
]
