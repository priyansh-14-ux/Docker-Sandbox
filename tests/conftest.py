# Pytest configuration and shared fixtures
from medicode.models.content import TestCase

# Instruct pytest not to collect the SQLAlchemy model 'TestCase' as a pytest test suite
TestCase.__test__ = False
