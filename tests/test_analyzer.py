import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from s_media_proxy.models import Server, User


@pytest.fixture
def server_with_analyzer(auth_user):
    return Server.objects.create(
        user=auth_user,
        name='Test Server',
        url='http://service.test',
        analyzer_url='http://analyzer.test:8000',
        analyzer_api_key='secret-key',
    )


@pytest.fixture
def server_without_analyzer(auth_user):
    return Server.objects.create(
        user=auth_user,
        name='No Analyzer',
        url='http://service.test',
    )


def _proxy_url(server_id, analyzer_path='clusters'):
    return reverse(
        'analyzer_proxy',
        kwargs={'server_id': server_id, 'analyzer_path': analyzer_path},
    )


@pytest.mark.django_db
def test_analyzer_proxy_requires_auth(server_with_analyzer):
    client = APIClient()
    response = client.get(_proxy_url(server_with_analyzer.id))
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


@pytest.mark.django_db
def test_analyzer_proxy_server_not_found(authorized_client):
    response = authorized_client.get(_proxy_url(999999))
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_analyzer_proxy_other_user_server(authorized_client):
    other_user = User.objects.create_user('other', 'other@example.com', 'password')
    other_server = Server.objects.create(
        user=other_user,
        name='Other',
        url='http://other.test',
        analyzer_url='http://analyzer.test:8000',
    )
    response = authorized_client.get(_proxy_url(other_server.id))
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_analyzer_proxy_not_configured(authorized_client, server_without_analyzer):
    response = authorized_client.get(_proxy_url(server_without_analyzer.id))
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_analyzer_proxy_forwards_get(
    mock_request, authorized_client, auth_user, server_with_analyzer
):
    response = authorized_client.get(
        _proxy_url(server_with_analyzer.id), {'unassigned': 'true'}
    )
    assert response.status_code == status.HTTP_200_OK
    call = mock_request.call_args
    assert call[0][0] == 'GET'
    assert call[0][1] == 'http://analyzer.test:8000/clusters?unassigned=true'
    headers = call[1]['headers']
    assert headers['X-API-Key'] == 'secret-key'
    assert headers['X-USER-ID'] == str(auth_user.public_id)


@pytest.mark.django_db
def test_analyzer_proxy_forwards_post_json(
    mock_request, authorized_client, server_with_analyzer
):
    body = {
        'person_id': '00000000-0000-0000-0000-000000000001',
        'name': 'Alice',
        'promote': True,
    }
    response = authorized_client.post(
        _proxy_url(server_with_analyzer.id, 'clusters/1/assign'),
        data=body,
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK
    call = mock_request.call_args
    assert call[0][0] == 'POST'
    assert call[0][1] == 'http://analyzer.test:8000/clusters/1/assign'
    assert call[1]['json'] == body
    assert call[1]['headers']['X-API-Key'] == 'secret-key'


@pytest.mark.django_db
def test_analyzer_proxy_forwards_patch(
    mock_request, authorized_client, server_with_analyzer
):
    body = {'status': 'confirmed'}
    response = authorized_client.patch(
        _proxy_url(server_with_analyzer.id, 'faces/1'),
        data=body,
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK
    call = mock_request.call_args
    assert call[0][0] == 'PATCH'
    assert call[0][1] == 'http://analyzer.test:8000/faces/1'
    assert call[1]['json'] == body
