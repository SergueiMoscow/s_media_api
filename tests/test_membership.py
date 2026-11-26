"""Тесты оркестрации promote/unpromote (переключатель «в каталоге»)."""

import json
import uuid
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status

from s_media_proxy.models import Server


def _fake_response(content, status_code=200, content_type='application/json'):
    class FakeResponse:
        pass

    resp = FakeResponse()
    resp.content = json.dumps(content) if not isinstance(content, str) else content
    resp.status_code = status_code
    resp.headers = {'Content-Type': content_type}
    return resp


@pytest.fixture
def server_with_analyzer(auth_user):
    return Server.objects.create(
        user=auth_user,
        name='Test Server',
        url='http://service.test',
        analyzer_url='http://analyzer.test:8000',
        analyzer_api_key='secret-key',
    )


def _url(name, server_id, **kwargs):
    return reverse(name, kwargs={'server_id': server_id, **kwargs})


@pytest.mark.django_db
def test_cluster_promote(authorized_client, auth_user, server_with_analyzer):
    promotable = [
        {
            'scanned_file_id': 11,
            'storage_id': str(uuid.uuid4()),
            'folder_path': '2024/06',
            'filename': 'IMG_0001.jpg',
        },
        {
            'scanned_file_id': 22,
            'storage_id': str(uuid.uuid4()),
            'folder_path': '2024/07',
            'filename': 'IMG_0002.jpg',
        },
    ]
    catalog_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    calls = []

    def side_effect(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'GET' and '/promotable-files' in url:
            return _fake_response(promotable)
        if method == 'POST' and url.endswith('/storage/fileinfo'):
            idx = sum(1 for c in calls if c[1].endswith('/storage/fileinfo')) - 1
            return _fake_response(
                {'status_code': 200, 'result': {'id': catalog_ids[idx]}}
            )
        if method == 'PUT' and '/catalog-links' in url:
            return _fake_response({'linked': 2})
        raise AssertionError(f'Unexpected request: {method} {url}')

    with patch('requests.request', side_effect=side_effect):
        response = authorized_client.post(
            _url('cluster_promote', server_with_analyzer.id, cluster_id=5),
            data={'name': 'Alice'},
            format='json',
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok', 'promoted': 2}

    methods = [c[0] for c in calls]
    assert methods == ['GET', 'POST', 'POST', 'PUT']

    # GET promotable-files с X-API-Key
    assert calls[0][1] == 'http://analyzer.test:8000/clusters/5/promotable-files'
    assert calls[0][2]['headers']['X-API-Key'] == 'secret-key'

    # POST fileinfo с add_tags-именем, status='active' и ip
    first_fileinfo = calls[1][2]
    assert first_fileinfo['json']['storage_id'] == promotable[0]['storage_id']
    assert first_fileinfo['json']['folder_path'] == '2024/06'
    assert first_fileinfo['json']['filename'] == 'IMG_0001.jpg'
    assert first_fileinfo['json']['add_tags'] == ['Alice']
    assert first_fileinfo['json']['status'] == 'active'
    assert 'tags' not in first_fileinfo['json']
    assert first_fileinfo['json']['ip'] is not None
    assert first_fileinfo['headers']['X-USER-ID'] == str(auth_user.public_id)

    # PUT catalog-links со связями
    put_call = calls[-1][2]
    assert put_call['json'] == {
        'links': [
            {'scanned_file_id': 11, 'catalog_file_id': catalog_ids[0]},
            {'scanned_file_id': 22, 'catalog_file_id': catalog_ids[1]},
        ]
    }
    assert put_call['headers']['X-API-Key'] == 'secret-key'


@pytest.mark.django_db
def test_cluster_unpromote(authorized_client, server_with_analyzer):
    catalog_file_id_a = str(uuid.uuid4())
    catalog_file_id_b = str(uuid.uuid4())
    faces_page = {
        'items': [
            {'id': 1, 'scanned_file_id': 11, 'catalog_file_id': catalog_file_id_a},
            {'id': 2, 'scanned_file_id': 11, 'catalog_file_id': catalog_file_id_a},
            {'id': 3, 'scanned_file_id': 22, 'catalog_file_id': catalog_file_id_b},
            {'id': 4, 'scanned_file_id': 33, 'catalog_file_id': None},
        ],
        'total': 4,
        'limit': 1000,
        'offset': 0,
    }
    calls = []

    def side_effect(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'GET' and '/faces' in url:
            return _fake_response(faces_page)
        if method == 'POST' and url.endswith('/storage/fileinfo'):
            return _fake_response(
                {'status_code': 200, 'result': {'id': kwargs['json']['id']}}
            )
        if method == 'PUT' and '/catalog-links' in url:
            return _fake_response({'linked': len(kwargs['json']['links'])})
        raise AssertionError(f'Unexpected request: {method} {url}')

    with patch('requests.request', side_effect=side_effect):
        response = authorized_client.post(
            _url('cluster_unpromote', server_with_analyzer.id, cluster_id=5)
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok', 'unpromoted': 2}

    methods = [c[0] for c in calls]
    assert methods == ['GET', 'POST', 'POST', 'PUT']

    # GET faces с пагинацией
    assert calls[0][1].startswith('http://analyzer.test:8000/clusters/5/faces?')

    # POST fileinfo: status=inactive для уникальных catalog_file_id
    fileinfo_jsons = [c[2]['json'] for c in calls if c[1].endswith('/storage/fileinfo')]
    assert [j['status'] for j in fileinfo_jsons] == ['inactive', 'inactive']
    assert {j['id'] for j in fileinfo_jsons} == {catalog_file_id_a, catalog_file_id_b}

    # PUT catalog-links: очистка связи для уникальных scanned_file_id
    put_json = calls[-1][2]['json']
    assert put_json['links'] == [
        {'scanned_file_id': 11, 'catalog_file_id': None},
        {'scanned_file_id': 22, 'catalog_file_id': None},
    ]


@pytest.mark.django_db
def test_face_promote(authorized_client, server_with_analyzer):
    catalog_file_id = str(uuid.uuid4())
    face = {
        'id': 7,
        'scanned_file_id': 11,
        'catalog_file_id': None,
        'storage_id': str(uuid.uuid4()),
        'folder_path': '2024/06',
        'filename': 'IMG_0001.jpg',
    }
    calls = []

    def side_effect(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'GET' and '/faces/7' in url:
            return _fake_response(face)
        if method == 'POST' and url.endswith('/storage/fileinfo'):
            return _fake_response(
                {'status_code': 200, 'result': {'id': catalog_file_id}}
            )
        if method == 'PUT' and '/catalog-links' in url:
            return _fake_response({'linked': 1})
        raise AssertionError(f'Unexpected request: {method} {url}')

    with patch('requests.request', side_effect=side_effect):
        response = authorized_client.post(
            _url('face_promote', server_with_analyzer.id, face_id=7),
            data={'name': 'Alice'},
            format='json',
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok', 'promoted': 1}

    methods = [c[0] for c in calls]
    assert methods == ['GET', 'POST', 'PUT']
    assert calls[0][1] == 'http://analyzer.test:8000/faces/7'
    assert calls[1][2]['json']['add_tags'] == ['Alice']
    assert calls[1][2]['json']['status'] == 'active'
    assert 'tags' not in calls[1][2]['json']
    assert calls[2][2]['json'] == {
        'links': [{'scanned_file_id': 11, 'catalog_file_id': catalog_file_id}]
    }


@pytest.mark.django_db
def test_face_unpromote(authorized_client, server_with_analyzer):
    catalog_file_id = str(uuid.uuid4())
    face = {'id': 7, 'scanned_file_id': 11, 'catalog_file_id': catalog_file_id}
    calls = []

    def side_effect(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'GET' and '/faces/7' in url:
            return _fake_response(face)
        if method == 'POST' and url.endswith('/storage/fileinfo'):
            return _fake_response(
                {'status_code': 200, 'result': {'id': kwargs['json']['id']}}
            )
        if method == 'PUT' and '/catalog-links' in url:
            return _fake_response({'linked': 1})
        raise AssertionError(f'Unexpected request: {method} {url}')

    with patch('requests.request', side_effect=side_effect):
        response = authorized_client.post(
            _url('face_unpromote', server_with_analyzer.id, face_id=7)
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'status': 'ok', 'unpromoted': 1}

    methods = [c[0] for c in calls]
    assert methods == ['GET', 'POST', 'PUT']

    fileinfo_json = calls[1][2]['json']
    assert fileinfo_json['id'] == catalog_file_id
    assert fileinfo_json['status'] == 'inactive'

    assert calls[2][2]['json'] == {
        'links': [{'scanned_file_id': 11, 'catalog_file_id': None}]
    }


@pytest.mark.django_db
def test_face_promote_empty_name_sends_no_add_tags(
    authorized_client, server_with_analyzer
):
    face = {
        'id': 7,
        'scanned_file_id': 11,
        'catalog_file_id': None,
        'storage_id': str(uuid.uuid4()),
        'folder_path': '2024/06',
        'filename': 'IMG_0001.jpg',
    }
    calls = []

    def side_effect(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'GET' and '/faces/7' in url:
            return _fake_response(face)
        if method == 'POST' and url.endswith('/storage/fileinfo'):
            return _fake_response(
                {'status_code': 200, 'result': {'id': str(uuid.uuid4())}}
            )
        if method == 'PUT' and '/catalog-links' in url:
            return _fake_response({'linked': 1})
        raise AssertionError(f'Unexpected request: {method} {url}')

    with patch('requests.request', side_effect=side_effect):
        response = authorized_client.post(
            _url('face_promote', server_with_analyzer.id, face_id=7),
            data={'name': ''},
            format='json',
        )

    assert response.status_code == status.HTTP_200_OK
    fileinfo_json = calls[1][2]['json']
    assert 'add_tags' not in fileinfo_json
    assert fileinfo_json['status'] == 'active'


@pytest.mark.django_db
def test_face_promote_forbidden_from_fileinfo(authorized_client, server_with_analyzer):
    face = {
        'id': 7,
        'scanned_file_id': 11,
        'catalog_file_id': None,
        'storage_id': str(uuid.uuid4()),
        'folder_path': '2024/06',
        'filename': 'IMG_0001.jpg',
    }
    calls = []

    def side_effect(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == 'GET' and '/faces/7' in url:
            return _fake_response(face)
        if method == 'POST' and url.endswith('/storage/fileinfo'):
            return _fake_response(
                {'error': {'error_code': 'not_allowed', 'error_message': 'denied'}},
                status_code=403,
            )
        raise AssertionError(f'Unexpected request: {method} {url}')

    with patch('requests.request', side_effect=side_effect):
        response = authorized_client.post(
            _url('face_promote', server_with_analyzer.id, face_id=7),
            data={'name': 'Alice'},
            format='json',
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    # При отказе в правах от fileinfo связь catalog-links не вызывается.
    assert not any('catalog-links' in c[1] for c in calls)
