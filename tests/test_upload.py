import json
from unittest.mock import Mock, patch

import pytest
import requests
from rest_framework.test import APIClient

from s_media_proxy.models import Server, User

TEST_CONTENT = b'test file content'


@pytest.fixture
def upload_server(auth_user):
    return Server.objects.create(
        user=auth_user,
        name='UploadServer',
        url='http://localhost:8001',
        can_add=True,
        service_api_key='service-secret',
    )


@pytest.fixture
def read_only_server(auth_user):
    return Server.objects.create(
        user=auth_user,
        name='ReadOnlyServer',
        url='http://localhost:8002',
        can_add=False,
    )


def _post(
    client, server_id, original_filename='test.jpg', content=TEST_CONTENT, **extra
):
    url = f'/upload?server_id={server_id}&original_filename={original_filename}'
    return client.post(
        url, data=content, content_type='application/octet-stream', **extra
    )


@pytest.mark.django_db
def test_upload_requires_auth(upload_server):
    response = _post(APIClient(), upload_server.id)
    assert response.status_code == 401


@pytest.mark.django_db
def test_upload_missing_server_id(authorized_client):
    response = authorized_client.post(
        '/upload?original_filename=test.jpg',
        data=TEST_CONTENT,
        content_type='application/octet-stream',
    )
    assert response.status_code == 400
    assert 'server_id' in response.json()['error']


@pytest.mark.django_db
def test_upload_missing_original_filename(authorized_client, upload_server):
    response = authorized_client.post(
        f'/upload?server_id={upload_server.id}',
        data=TEST_CONTENT,
        content_type='application/octet-stream',
    )
    assert response.status_code == 400
    assert 'original_filename' in response.json()['error']


@pytest.mark.django_db
def test_upload_server_not_found(authorized_client):
    response = _post(authorized_client, 99999)
    assert response.status_code == 404


@pytest.mark.django_db
def test_upload_other_user_server(authorized_client, auth_user):
    other = User.objects.create_user('otheruser', 'other@example.com', 'otherpass123')
    other_server = Server.objects.create(
        user=other, name='OtherServer', url='http://localhost:8003', can_add=True
    )
    response = _post(authorized_client, other_server.id)
    assert response.status_code == 404


@pytest.mark.django_db
def test_upload_server_does_not_allow(authorized_client, read_only_server):
    response = _post(authorized_client, read_only_server.id)
    assert response.status_code == 403
    assert 'does not allow' in response.json()['error']


@pytest.mark.django_db
@patch('s_media_proxy.views.upload_view.requests.post')
def test_upload_success(mock_post, authorized_client, auth_user, upload_server):
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.content = json.dumps({'id': 123, 'filename': 'test.jpg'}).encode()
    mock_response.headers = {'Content-Type': 'application/json'}
    mock_post.return_value = mock_response

    response = authorized_client.post(
        f'/upload?server_id={upload_server.id}&original_filename=test.jpg'
        f'&note=Test%20note&tags=tag1,tag2&is_public=true',
        data=TEST_CONTENT,
        content_type='application/octet-stream',
    )

    assert response.status_code == 201
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == 'http://localhost:8001/upload'
    assert call_args[1]['params']['original_filename'] == 'test.jpg'
    # В сервис уходит UUID текущего пользователя и ключ сервиса.
    assert call_args[1]['headers']['X-USER-ID'] == str(auth_user.public_id)
    assert call_args[1]['headers']['X-API-Key'] == 'service-secret'


@pytest.mark.django_db
@patch('s_media_proxy.views.upload_view.requests.post')
def test_upload_forged_x_user_id_ignored(
    mock_post, authorized_client, auth_user, upload_server
):
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.content = b'{"id": 123}'
    mock_response.headers = {'Content-Type': 'application/json'}
    mock_post.return_value = mock_response

    response = authorized_client.post(
        f'/upload?server_id={upload_server.id}&original_filename=test.jpg',
        data=TEST_CONTENT,
        content_type='application/octet-stream',
        HTTP_X_USER_ID='1',  # подделанный X-User-ID игнорируется
    )

    assert response.status_code == 201
    call_args = mock_post.call_args
    assert call_args[1]['headers']['X-USER-ID'] == str(auth_user.public_id)
    assert call_args[1]['headers']['X-USER-ID'] != '1'


@pytest.mark.django_db
@patch('s_media_proxy.views.upload_view.requests.post')
def test_upload_5mb_body_passes(mock_post, authorized_client, upload_server):
    big_body = b'x' * (5 * 1024 * 1024)
    captured = {}

    def fake_post(url, **kwargs):
        captured['total'] = sum(len(chunk) for chunk in kwargs['data'])
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.content = b'{"id": 123}'
        mock_response.headers = {'Content-Type': 'application/json'}
        return mock_response

    mock_post.side_effect = fake_post

    response = authorized_client.post(
        f'/upload?server_id={upload_server.id}&original_filename=big.bin',
        data=big_body,
        content_type='application/octet-stream',
    )

    assert response.status_code == 201
    # Тело передано потоком целиком (лимит DATA_UPLOAD_MAX_MEMORY_SIZE не мешает).
    assert captured['total'] == len(big_body)


@pytest.mark.django_db
@patch('s_media_proxy.views.upload_view.requests.post')
def test_upload_connection_error(mock_post, authorized_client, upload_server):
    mock_post.side_effect = requests.exceptions.ConnectionError('Connection refused')
    response = _post(authorized_client, upload_server.id)
    assert response.status_code == 502
    assert 'Cannot connect' in response.json()['error']


@pytest.mark.django_db
@patch('s_media_proxy.views.upload_view.requests.post')
def test_upload_timeout(mock_post, authorized_client, upload_server):
    mock_post.side_effect = requests.exceptions.Timeout('Timeout')
    response = _post(authorized_client, upload_server.id)
    assert response.status_code == 504
    assert 'timeout' in response.json()['error']
