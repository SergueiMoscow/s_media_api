import uuid
from unittest.mock import ANY, patch

import pytest
from django.http import StreamingHttpResponse
from django.urls import reverse
from rest_framework.status import HTTP_200_OK
from rest_framework.test import APIClient

from s_media_proxy.models import Server, User


@pytest.mark.django_db
def test_patch_storage_ok(
    authorized_client, auth_user, mock_created_server, mock_request
):
    server_id = mock_created_server.return_value.id
    data = {
        "server_id": str(server_id),
        "key": "secret_key_test",
        "name": "test 1",
        "path": "/tmp",
    }
    storage_id = str(uuid.uuid4())
    authorized_client.patch(f'/storages/{storage_id}/', data)
    mock_request.assert_called_once_with(
        'PATCH',
        f'{mock_created_server.return_value.url}/storages/{storage_id}',
        data={**data, 'user_id': str(auth_user.public_id)},
        files=ANY,
        json=None,
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


@pytest.mark.django_db
def test_delete_storage_ok(authorized_client, mock_request, created_user_and_server):
    storage_id = str(uuid.uuid4())
    server = created_user_and_server
    result = authorized_client.delete(f'/storages/{server.id}/{storage_id}/')
    assert result.status_code == HTTP_200_OK
    mock_request.assert_called_once_with(
        'DELETE',
        f'{server.url}/storages/{storage_id}',
        data={},
        files=ANY,
        json=None,
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
        "path": "/tmp",
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

        assert response.status_code == 200
        mock_requests_request.assert_called_once_with(
            'POST',
            f'{server.url}/storages/',
            data={
                **data,
                'user_id': str(auth_user.public_id),
                'created_by': str(auth_user.public_id),
            },
            files=ANY,
            json=None,
            headers=ANY,
            timeout=ANY,
            verify=True,
        )


@pytest.mark.django_db
def test_get_storages_ok(authorized_client, mock_created_server, mock_request):
    server_id = mock_created_server.return_value.id
    url = f'/storages/'
    mock_request.return_value.content = '{"results":[{}]}'
    response = authorized_client.get(url, {'server_id': server_id}, format='json')
    assert response.status_code == 200
    mock_request.assert_called_once_with(
        'GET',
        f'{mock_created_server.return_value.url}/storages/',
        data=ANY,
        files=ANY,
        json=ANY,
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


@pytest.mark.django_db
def test_get_storage_content_ok(authorized_client, mock_created_server, mock_request):
    # Фиктивные IDs для сервера и хранилища
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()

    url = f'/storage/{server_id}/{storage_id}/'

    # Создаем пример ответа, который будет возвращать наш объект ответа
    mock_request.return_value.content = (
        '{"results":{"folders": [], "files":{}}, "pagination":{}}'
    )

    response = authorized_client.get(url, format='json')

    # Проверяем, что ответ содержит статус 200
    assert response.status_code == 200

    # Проверяем, что был вызван mock_request с ожидаемыми параметрами
    mock_request.assert_called_once_with(
        'GET',
        f'{mock_created_server.return_value.url}/storage/{storage_id}?folder=&page=',
        data=ANY,
        files=ANY,
        json=ANY,
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


@pytest.mark.django_db
def test_get_servers_content_ok(
    authorized_client, created_user_and_server, mock_request
):
    url = f'/servers_content/'
    mock_request.return_value.content = '{"results":[{}]}'
    response = authorized_client.get(url, format='json')

    assert response.status_code == 200
    mock_request.assert_called_once_with(
        'GET',
        f'{created_user_and_server.url}/storage/?user_id={created_user_and_server.user.public_id}',
        data=ANY,
        files=ANY,
        json=ANY,
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


@pytest.mark.django_db
def test_get_folder_collage_ok(authorized_client, mock_created_server, mock_request):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    folder = 'test_folder'
    url = f'/folder_collage/{server_id}/{storage_id}/'
    params = {'folder': folder}
    mock_request.return_value.content = '{"results":[{}]}'
    response = authorized_client.get(url, params, format='json')

    assert response.status_code == 200
    mock_request.assert_called_once_with(
        'GET',
        f'{mock_created_server.return_value.url}/storage/collage/{storage_id}?folder={folder}',
        data={},
        files=ANY,
        json=None,
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


@pytest.mark.django_db
def test_get_file_preview_by_storage_folder_and_filename_ok(
    authorized_client, mock_created_server, node_stream_factory
):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    folder = 'test_folder'
    filename = 'test_file'
    url = f'/preview/{server_id}/{storage_id}/'
    params = {'folder': folder, 'filename': filename}

    node = node_stream_factory(
        status_code=200, headers={'Content-Type': 'image/jpeg'}, body=b'abc'
    )
    with patch('requests.get', return_value=node) as mock_get:
        response = authorized_client.get(url, params)

    assert response.status_code == 200
    assert isinstance(response, StreamingHttpResponse)
    assert response['Content-Type'] == 'image/jpeg'
    assert b''.join(response.streaming_content) == b'abc'
    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == (
        f'{mock_created_server.return_value.url}/storage/preview/{storage_id}'
        f'?folder={folder}&filename={filename}'
    )
    assert mock_get.call_args[1]['stream'] is True
    assert mock_get.call_args[1]['timeout'] == (5, 60)


@pytest.mark.django_db
def test_get_file_preview_by_file_id_ok(
    authorized_client, mock_created_server, node_stream_factory
):
    server_id = mock_created_server.return_value.id
    file_id = uuid.uuid4()
    url = f'/preview/{server_id}/{file_id}/'

    node = node_stream_factory(
        status_code=200, headers={'Content-Type': 'image/jpeg'}, body=b'abc'
    )
    with patch('requests.get', return_value=node) as mock_get:
        response = authorized_client.get(url)

    assert response.status_code == 200
    assert isinstance(response, StreamingHttpResponse)
    assert b''.join(response.streaming_content) == b'abc'
    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == (
        f'{mock_created_server.return_value.url}/catalog/preview/{file_id}'
    )


@pytest.mark.django_db
def test_file_range_storage_variant(
    authorized_client, mock_created_server, node_stream_factory
):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    url = f'/file/{server_id}/{storage_id}/'
    body = b'0123456789' * 10  # 100 байт

    node = node_stream_factory(
        status_code=206,
        headers={
            'Content-Type': 'video/mp4',
            'Content-Range': 'bytes 0-99/1000',
            'Accept-Ranges': 'bytes',
        },
        body=body,
    )
    with patch('requests.get', return_value=node) as mock_get:
        response = authorized_client.get(
            url, {'filename': 'x.mp4'}, HTTP_RANGE='bytes=0-99'
        )

    assert response.status_code == 206
    assert response['Content-Range'] == 'bytes 0-99/1000'
    assert response['Accept-Ranges'] == 'bytes'
    assert b''.join(response.streaming_content) == body
    # Range уходит в узел
    assert mock_get.call_args[1]['headers']['Range'] == 'bytes=0-99'


@pytest.mark.django_db
def test_file_range_catalog_variant(
    authorized_client, mock_created_server, node_stream_factory
):
    server_id = mock_created_server.return_value.id
    file_id = uuid.uuid4()
    url = f'/file/{server_id}/{file_id}/'
    body = b'0123456789' * 10

    node = node_stream_factory(
        status_code=206,
        headers={
            'Content-Type': 'video/mp4',
            'Content-Range': 'bytes 0-99/1000',
        },
        body=body,
    )
    with patch('requests.get', return_value=node) as mock_get:
        response = authorized_client.get(url, HTTP_RANGE='bytes=0-99')

    assert response.status_code == 206
    assert response['Content-Range'] == 'bytes 0-99/1000'
    assert b''.join(response.streaming_content) == body
    assert mock_get.call_args[1]['headers']['Range'] == 'bytes=0-99'


@pytest.mark.django_db
def test_file_without_range(
    authorized_client, mock_created_server, node_stream_factory
):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    url = f'/file/{server_id}/{storage_id}/'
    body = b'full-content'

    node = node_stream_factory(
        status_code=200, headers={'Content-Type': 'video/mp4'}, body=body
    )
    with patch('requests.get', return_value=node) as mock_get:
        response = authorized_client.get(url, {'filename': 'x.mp4'})

    assert response.status_code == 200
    assert b''.join(response.streaming_content) == body
    assert 'Range' not in mock_get.call_args[1]['headers']
