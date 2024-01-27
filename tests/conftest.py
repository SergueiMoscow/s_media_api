import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from s_media_proxy.models import User, Server


@pytest.fixture
def auth_user():
    user = User.objects.create_user('testuser', 'test@example.com', 'password')
    user.public_id = uuid.uuid4()
    user.save()
    return user


@pytest.fixture
def get_fake_response(faker):
    class FakeResponse:
        content = faker.word()
        status_code = 200
        headers = {'Content-Type': 'application/json'}
    return FakeResponse


@pytest.fixture
def authorized_client(auth_user):
    client = APIClient()
    client.force_authenticate(user=auth_user)
    yield client


@pytest.fixture
def mock_created_server(faker):
    with patch('s_media_proxy.views.get_server_by_id') as mock:
        server = Server(
            id=faker.random_int(),
            name='test server',
            url='http://test',
        )
        mock.return_value = server
        yield mock


@pytest.fixture
def mock_request(get_fake_response):
    with patch('requests.request') as mock:
        mock.return_value = get_fake_response
        yield mock
