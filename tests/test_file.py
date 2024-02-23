import os
import uuid
from unittest.mock import ANY

import pytest

from django_app.settings import BASE_DIR


@pytest.mark.django_db
def test_get_file_info_from_catalog(authorized_client, mock_created_server, mock_request):
    server_id = 1
    storage_id = uuid.uuid4()
    data = {
        'folder': os.path.join(BASE_DIR, 'images')
    }
    url = f'/storage/fileinfo/{server_id}/{storage_id}/'
    response = authorized_client.post(url, data=data)
    assert response.status_code == 200
    mock_request.assert_called_once_with(
        'POST',
        f'{mock_created_server.return_value.url}/storage/fileinfo',  # ?folder={folder}&filename={filename}
        data=data,
        files=ANY,
        json={'ip': '127.0.0.1', 'storage_id': str(storage_id)},
        headers=ANY,
        timeout=ANY,
        verify=True,
    )
