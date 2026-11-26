import json
import os
import uuid
from unittest.mock import ANY, patch

import pytest
import requests
from rest_framework import status

from django_app.settings import BASE_DIR


@pytest.mark.django_db
def test_get_file_info_from_catalog(
    authorized_client, mock_created_server, mock_request
):
    server_id = 1
    storage_id = uuid.uuid4()
    data = {'folder': os.path.join(BASE_DIR, 'images')}
    url = f'/storage/fileinfo/{server_id}/{storage_id}/'
    response = authorized_client.post(url, data=data)
    assert response.status_code == status.HTTP_200_OK
    mock_request.assert_called_once_with(
        'POST',
        f'{mock_created_server.return_value.url}/storage/fileinfo',  # ?folder={folder}&filename={filename}
        data={**data, 'ip': '127.0.0.1', 'storage_id': str(storage_id)},
        files=ANY,
        json=None,
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


@pytest.mark.django_db
def test_main_page_server_not_found(client, mock_request):
    url = '/main/'
    response = client.get(url)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['errors'][0]['code'] == 'not_found'


@pytest.mark.django_db
def test_main_page_ok(created_multiple_servers, client, mock_request):
    url = '/main/'
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is not None


@pytest.mark.django_db
def test_fileinfo_inactive_clears_analyzer_link(
    authorized_client, mock_created_server, mock_request
):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    file_id = str(uuid.uuid4())

    mock_created_server.return_value.analyzer_url = 'http://analyzer.test:8000'
    mock_created_server.return_value.analyzer_api_key = 'analyzer-secret'
    mock_request.return_value.content = json.dumps(
        {'status_code': 200, 'result': {'id': file_id}}
    )
    mock_request.return_value.status_code = 200

    url = f'/storage/fileinfo/{server_id}/{storage_id}/'
    with patch('requests.delete') as mock_delete:
        mock_delete.return_value.status_code = 200
        mock_delete.return_value.content = b'{"unlinked": 1}'
        mock_delete.return_value.headers = {'Content-Type': 'application/json'}
        response = authorized_client.post(
            url, data={'id': file_id, 'status': 'inactive'}, format='json'
        )

    assert response.status_code == status.HTTP_200_OK
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][0] == (
        f'http://analyzer.test:8000/catalog-files/{file_id}/link'
    )
    assert mock_delete.call_args[1]['headers']['X-API-Key'] == 'analyzer-secret'


@pytest.mark.django_db
def test_fileinfo_inactive_analyzer_error_still_succeeds(
    authorized_client, mock_created_server, mock_request
):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    file_id = str(uuid.uuid4())

    mock_created_server.return_value.analyzer_url = 'http://analyzer.test:8000'
    mock_created_server.return_value.analyzer_api_key = 'analyzer-secret'
    mock_request.return_value.content = json.dumps(
        {'status_code': 200, 'result': {'id': file_id}}
    )
    mock_request.return_value.status_code = 200

    url = f'/storage/fileinfo/{server_id}/{storage_id}/'
    with patch(
        'requests.delete', side_effect=requests.exceptions.ConnectionError('down')
    ):
        response = authorized_client.post(
            url, data={'id': file_id, 'status': 'inactive'}, format='json'
        )

    # Файл уже скрыт: клиент получает успешный ответ сервиса, ошибка анализатора
    # лишь пишется в warning.
    assert response.status_code == status.HTTP_200_OK
