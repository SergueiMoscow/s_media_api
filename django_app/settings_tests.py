# pylint: disable=wildcard-import, unused-wildcard-import
import os

from .settings import *  # noqa: F403, F401

# SQLite. Проблемы с многопоточностью, поэтому пока выключил
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(os.path.dirname(__file__), 'test_db.sqlite3'),
        'MIGRATE': True,
        'ATOMIC_REQUESTS': True,
    }
}
# DATABASE_TEST_SCHEMA = env("DATABASE_TEST_SCHEMA")
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql_psycopg2',
#         'NAME': env('DATABASE_NAME'),
#         'OPTIONS': {'options': f'-c search_path={DATABASE_TEST_SCHEMA}'},
#         'USER': env('DATABASE_USER'),
#         'PASSWORD': env('DATABASE_PASSWORD'),
#         'HOST': env('DATABASE_HOST'),
#         'PORT': env.int('DATABASE_PORT', 5432),
#     }
# }
# TEST_RUNNER = 'tests.runner.PostgresSchemaTestRunner'
