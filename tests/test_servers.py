import uuid

import pytest
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from rest_framework.test import APIClient
from unittest.mock import patch, ANY
from s_media_proxy.models import User, Server


@pytest.fixture
def auth_user(db):
    user = User.objects.create_user('testuser', 'test@example.com', 'password')
    user.public_id = uuid.uuid4()
    user.save()
    return user


@pytest.mark.django_db
def test_post_endpoint(auth_user, get_fake_response):
    client = APIClient()
    client.force_authenticate(user=auth_user)
    data = {
        "server_id": '1',
        "key": "secret_key_test",
        "name": "test 1",
        "path": "/tmp"
    }

    with patch('s_media_proxy.views.get_server_by_id') as mock_get_server, \
         patch('requests.request') as mock_requests_request:
        server = Server(
            id=uuid.uuid4(),
            name='test server',
            url='http://test',
        )
        mock_get_server.return_value = server
        mock_requests_request.return_value = get_fake_response

        url = reverse('list-create-storage')
        response = client.post(url, data)

        # Проверяем статус ответа
        assert response.status_code == 200
        # Проверяем, что mock_requests_request был вызван с правильными параметрами
        mock_requests_request.assert_called_once_with(
            'POST',
            f'{server.url}/storages/',
            data=data,
            files=ANY,
            json=ANY,
            headers=ANY,
            timeout=ANY,
            verify=True,
        )
