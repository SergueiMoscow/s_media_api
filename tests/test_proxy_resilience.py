"""Тесты устойчивости прокси (раунд 02, пункты 1–4)."""

import json
import logging
import uuid
from unittest.mock import patch

import pytest
import requests

from s_media_proxy.models import Server


def _json_response(content, status_code=200):
    class FakeResponse:
        pass

    resp = FakeResponse()
    resp.content = json.dumps(content)
    resp.status_code = status_code
    resp.headers = {'Content-Type': 'application/json'}
    return resp


# ---------------------------------------------------------------------------
# Пункт 1: некорректный server_id → 404, не 500
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize('server_id', ['abc', True])
def test_storages_create_invalid_server_id(authorized_client, server_id):
    data = {'server_id': server_id, 'name': 'x', 'path': '/tmp'}
    response = authorized_client.post('/storages/', data, format='json')
    assert response.status_code == 404


@pytest.mark.django_db
def test_storages_create_null_server_id(authorized_client):
    data = {'server_id': None, 'name': 'x', 'path': '/tmp'}
    response = authorized_client.post('/storages/', data, format='json')
    assert response.status_code == 404


@pytest.mark.django_db
def test_storages_create_missing_server_id(authorized_client):
    data = {'name': 'x', 'path': '/tmp'}
    response = authorized_client.post('/storages/', data, format='json')
    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('server_id', ['abc', True, None])
def test_storage_detail_invalid_server_id(authorized_client, server_id):
    storage_id = uuid.uuid4()
    data = {'server_id': server_id} if server_id is not None else {}
    response = authorized_client.patch(f'/storages/{storage_id}/', data, format='json')
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Пункт 2: серверные поля уходят, даже если тело не JSON и не multipart
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_form_urlencoded_body_sends_server_fields(
    authorized_client, auth_user, mock_created_server, mock_request
):
    server_id = mock_created_server.return_value.id
    storage_id = uuid.uuid4()
    authorized_client.patch(
        f'/storages/{server_id}/{storage_id}/',
        data={'name': 'renamed'},
        content_type='application/x-www-form-urlencoded',
    )

    assert mock_request.call_args[1]['json'] == {'user_id': str(auth_user.public_id)}


# ---------------------------------------------------------------------------
# Пункт 3: узел недоступен → понятная ошибка (502/504), без ключа в логе
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_proxy_timeout_returns_504(authorized_client, mock_created_server, caplog):
    mock_created_server.return_value.service_api_key = 'secret-key'
    server_id = mock_created_server.return_value.id
    with patch('requests.request', side_effect=requests.Timeout('timeout')):
        with caplog.at_level(logging.WARNING, logger='s_media_proxy.proxy_view_mixin'):
            response = authorized_client.get(f'/catalog/tags/{server_id}/')

    assert response.status_code == 504
    assert 'secret-key' not in caplog.text


@pytest.mark.django_db
def test_proxy_connection_error_returns_502(
    authorized_client, mock_created_server, caplog
):
    mock_created_server.return_value.service_api_key = 'secret-key'
    server_id = mock_created_server.return_value.id
    with patch('requests.request', side_effect=requests.ConnectionError('refused')):
        with caplog.at_level(logging.WARNING, logger='s_media_proxy.proxy_view_mixin'):
            response = authorized_client.get(f'/catalog/tags/{server_id}/')

    assert response.status_code == 502
    assert 'secret-key' not in caplog.text


# ---------------------------------------------------------------------------
# Пункт 4: главная не падает из-за одного узла
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_main_page_one_node_fails(authorized_client, auth_user):
    Server.objects.create(user=auth_user, name='s1', url='http://s1.test')
    s2 = Server.objects.create(user=auth_user, name='s2', url='http://s2.test')

    def side_effect(method, url, **kwargs):
        if 's1.test' in url:
            raise requests.ConnectionError('down')
        return _json_response({'files': [{'created_at': '2024-01-01'}]})

    with patch('requests.request', side_effect=side_effect):
        response = authorized_client.get('/main/')

    assert response.status_code == 200
    data = response.json()
    assert len(data['results']['files']) == 1
    assert data['results']['files'][0]['server_id'] == s2.id


@pytest.mark.django_db
def test_main_page_all_nodes_fail(authorized_client, auth_user):
    Server.objects.create(user=auth_user, name='s1', url='http://s1.test')
    Server.objects.create(user=auth_user, name='s2', url='http://s2.test')

    with patch('requests.request', side_effect=requests.ConnectionError('down')):
        response = authorized_client.get('/main/')

    assert response.status_code == 502
