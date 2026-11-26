"""Тесты безопасности и проверки владельца узла (пункты 1–5 review)."""

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from s_media_proxy.models import Server, User


def _fake_response(content='{"results": []}', status_code=200):
    class FakeResponse:
        pass

    resp = FakeResponse()
    resp.content = content
    resp.status_code = status_code
    resp.headers = {'Content-Type': 'application/json'}
    return resp


@pytest.mark.django_db
def test_profile_route_removed(client):
    assert client.get('/profile/').status_code == 404


@pytest.mark.django_db
def test_anonymous_401_on_closed_routes(client):
    storage_id = uuid.uuid4()
    closed = [
        ('get', '/users/'),
        ('get', '/groups/'),
        ('get', '/servers/'),
        ('get', '/storages/'),
        ('get', f'/storages/{storage_id}/'),
        ('get', f'/storages/1/{storage_id}/'),
        ('get', '/servers_content/'),
        ('get', f'/storage/1/{storage_id}/'),
        ('get', f'/folder_collage/1/{storage_id}/'),
        ('get', f'/storage/fileinfo/1/{storage_id}/'),
        ('get', '/catalog/tags/1/'),
        ('get', f'/catalog_content/1/{storage_id}/'),
        ('get', '/analyzer/1/'),
    ]
    for method, path in closed:
        response = getattr(client, method)(path)
        assert (
            response.status_code == 401
        ), f'{method.upper()} {path} -> {response.status_code}'

    # /upload доступен только с JWT
    response = client.post('/upload', data=b'', content_type='application/octet-stream')
    assert response.status_code == 401


@pytest.mark.django_db
def test_open_routes_accessible_without_auth(
    client, created_user_and_server, mock_request
):
    server = created_user_and_server
    storage_id = uuid.uuid4()

    assert client.get('/main/').status_code == 200
    assert (
        client.get(
            f'/preview/{server.id}/{storage_id}/', {'filename': 'x.jpg'}
        ).status_code
        == 200
    )
    assert (
        client.get(
            f'/file/{server.id}/{storage_id}/', {'filename': 'x.jpg'}
        ).status_code
        == 200
    )
    assert client.get('/folders_image', {'folders': 2}).status_code == 200


@pytest.mark.django_db
def test_regular_user_cannot_access_users_and_groups(authorized_client):
    assert authorized_client.get('/users/').status_code == 403
    assert authorized_client.get('/groups/').status_code == 403


@pytest.mark.django_db
def test_foreign_server_404_on_all_owner_checked_routes(authorized_client):
    other = User.objects.create_user('other', 'other@example.com', 'password')
    foreign = Server.objects.create(
        user=other, name='Foreign', url='http://foreign.test'
    )
    storage_id = uuid.uuid4()
    sid = foreign.id

    cases = [
        ('get', '/storages/', {'data': {'server_id': sid}}),
        ('post', '/storages/', {'data': {'server_id': sid}, 'format': 'json'}),
        (
            'patch',
            f'/storages/{storage_id}/',
            {'data': {'server_id': sid}, 'format': 'json'},
        ),
        ('patch', f'/storages/{sid}/{storage_id}/', {'data': {}}),
        ('delete', f'/storages/{sid}/{storage_id}/', {}),
        ('get', f'/storage/{sid}/{storage_id}/', {}),
        ('get', f'/catalog_content/{sid}/{storage_id}/', {}),
        ('get', f'/catalog/tags/{sid}/', {}),
        ('get', f'/folder_collage/{sid}/{storage_id}/', {}),
        ('get', f'/storage/fileinfo/{sid}/{storage_id}/', {}),
        (
            'post',
            f'/storage/fileinfo/{sid}/{storage_id}/',
            {'data': {}, 'format': 'json'},
        ),
    ]
    for method, path, kwargs in cases:
        response = getattr(authorized_client, method)(path, **kwargs)
        assert (
            response.status_code == 404
        ), f'{method.upper()} {path} -> {response.status_code}'


@pytest.mark.django_db
def test_spoof_json_fields_do_not_override(
    authorized_client, auth_user, mock_created_server, mock_request
):
    server_id = mock_created_server.return_value.id
    data = {
        'server_id': str(server_id),
        'user_id': 'attacker-user',
        'created_by': 'attacker-user',
        'name': 'x',
        'path': '/tmp',
    }
    authorized_client.post('/storages/', data=data, format='json')

    json_body = mock_request.call_args[1]['json']
    assert json_body['user_id'] == str(auth_user.public_id)
    assert json_body['created_by'] == str(auth_user.public_id)


@pytest.mark.django_db
def test_spoof_multipart_fields_do_not_override(
    authorized_client, auth_user, mock_created_server, mock_request
):
    server_id = mock_created_server.return_value.id
    data = {
        'server_id': str(server_id),
        'user_id': 'attacker-user',
        'created_by': 'attacker-user',
        'name': 'x',
        'path': '/tmp',
    }
    authorized_client.post('/storages/', data=data)

    form_data = mock_request.call_args[1]['data']
    assert form_data['user_id'] == str(auth_user.public_id)
    assert form_data['created_by'] == str(auth_user.public_id)
    assert mock_request.call_args[1]['json'] is None


@pytest.mark.django_db
def test_spoof_storage_id_and_ip_do_not_override(
    authorized_client, mock_created_server, mock_request
):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    data = {
        'ip': '1.2.3.4',
        'storage_id': 'forged-storage',
        'folder_path': 'x',
        'filename': 'y.jpg',
    }
    authorized_client.post(
        f'/storage/fileinfo/{server_id}/{storage_id}/', data=data, format='json'
    )

    json_body = mock_request.call_args[1]['json']
    assert json_body['storage_id'] == str(storage_id)
    assert json_body['ip'] == '127.0.0.1'


@pytest.mark.django_db
def test_service_and_analyzer_keys_differ(authorized_client, auth_user):
    server = Server.objects.create(
        user=auth_user,
        name='S',
        url='http://service.test',
        analyzer_url='http://analyzer.test',
        service_api_key='svc-key',
        analyzer_api_key='ana-key',
    )

    with patch('requests.request', return_value=_fake_response()) as service_req:
        authorized_client.get('/storages/', {'server_id': server.id})
        assert service_req.call_args[1]['headers']['X-API-Key'] == 'svc-key'

    with patch('requests.request', return_value=_fake_response()) as analyzer_req:
        authorized_client.get(f'/analyzer/{server.id}/clusters')
        assert analyzer_req.call_args[1]['headers']['X-API-Key'] == 'ana-key'


@pytest.mark.django_db
def test_main_page_prefers_server_with_key(authorized_client, auth_user):
    # Два сервера с одним url: один с ключом, другой без.
    Server.objects.create(
        user=auth_user, name='NoKey', url='http://dup.test', service_api_key=''
    )
    Server.objects.create(
        user=auth_user, name='WithKey', url='http://dup.test', service_api_key='svc-key'
    )

    with patch(
        'requests.request',
        return_value=_fake_response('{"files": [{"created_at": "2024-01-01"}]}'),
    ) as req:
        authorized_client.get('/main/')
        # Главная склеивает серверы по url и берёт запись с заданным ключом.
        assert req.call_args[1]['headers']['X-API-Key'] == 'svc-key'
