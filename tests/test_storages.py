import uuid
from unittest.mock import ANY, patch

import pytest

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
