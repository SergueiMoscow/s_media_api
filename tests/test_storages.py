import uuid
from unittest.mock import ANY

import pytest


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
def test_delete_storage_ok(authorized_client, mock_created_server, mock_request):
    server_id = mock_created_server.return_value.id
    storage_id = str(uuid.uuid4())
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
