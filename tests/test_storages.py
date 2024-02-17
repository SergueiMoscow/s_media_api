import uuid
from unittest.mock import ANY, patch

import pytest
from django.urls import reverse
from rest_framework.status import HTTP_200_OK
from rest_framework.test import APIClient

from s_media_proxy.models import Server


@pytest.mark.django_db
def test_patch_storage_ok(authorized_client, mock_created_server, mock_request):
    server_id = mock_created_server.return_value.id
    data = {
        "server_id": str(server_id),
        "key": "secret_key_test",
        "name": "test 1",
        "path": "/tmp"
    }
    storage_id = str(uuid.uuid4())
    authorized_client.patch(f'/storages/{storage_id}/', data)
    mock_request.assert_called_once_with(
        'PATCH',
        f'{mock_created_server.return_value.url}/storages/{storage_id}',
        data=data,
        files=ANY,
        json=ANY,
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


@pytest.mark.django_db
def test_delete_storage_ok(authorized_client, mock_request, faker):
    storage_id = str(uuid.uuid4())
    with patch('s_media_proxy.services.get_server_by_id') as mock_created_server:
        server = Server(
            id=faker.random_int(),
            name='test server',
            url='http://test',
        )
        mock_created_server.return_value = server
        server_id = mock_created_server.return_value.id

        result = authorized_client.delete(f'/storages/{server_id}/{storage_id}/')
        assert result.status_code == HTTP_200_OK
        mock_request.assert_called_once_with(
            'DELETE',
            f'{mock_created_server.return_value.url}/storages/{storage_id}',
            data=ANY,
            files=ANY,
            json=ANY,
            headers=ANY,
            timeout=ANY,
            verify=True,
        )


@pytest.mark.django_db
def test_create_storage(auth_user, get_fake_response, mock_created_server):
    client = APIClient()
    client.force_authenticate(user=auth_user)
    data = {
        "server_id": '1',
        "key": "secret_key_test",
        "name": "test 1",
        "path": "/tmp"
    }

    with patch('requests.request') as mock_requests_request:
        server = Server(
            id=uuid.uuid4(),
            name='test server',
            url='http://test',
        )
        mock_created_server.return_value = server
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
