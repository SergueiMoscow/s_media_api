# pylint: disable=wildcard-import, unused-wildcard-import
import os

from .settings import *  # noqa: F403, F401

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(os.path.dirname(__file__), 'test_db.sqlite3'),
        'MIGRATE': True,
    }
}
# 'NAME': ':memory:',
