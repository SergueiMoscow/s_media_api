import pytest
from rest_framework.reverse import reverse
from rest_framework import status

from django.conf import settings
from s_media_proxy.models import Server
from s_media_proxy.serializers import ServerSerializer

from s_media_proxy.models import User

# settings.configure()


@pytest.fixture
def server(auth_user):
    return Server.objects.create(user=auth_user, name='Test Server', url='http://test.com')


@pytest.mark.django_db
def test_get_servers(authorized_client, server, auth_user):
    response = authorized_client.get(reverse('server-list'))
    expected_data = ServerSerializer(server).data
    assert response.status_code == status.HTTP_200_OK
    assert 'results' in response.data
    assert response.data['results'] == [expected_data]


@pytest.mark.django_db
def test_create_server(authorized_client):
    data = {'name': 'New Server', 'url': 'http://new.com'}
    response = authorized_client.post(reverse('server-list'), data=data)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['name'] == data['name']
    assert response.data['url'] == data['url']


@pytest.mark.django_db
def test_update_server(authorized_client, server):
    data = {'name': 'Updated Server', 'url': 'http://updated.com'}
    response = authorized_client.put(reverse('server-detail', kwargs={'pk': str(server.id)}), data=data)

    server.refresh_from_db()
    assert response.status_code == status.HTTP_200_OK
    assert server.name == data['name']
    assert server.url == data['url']


@pytest.mark.django_db
def test_delete_server(authorized_client, server):
    response = authorized_client.delete(reverse('server-detail', kwargs={'pk': str(server.id)}))

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Server.objects.filter(pk=server.pk).exists()


@pytest.mark.django_db
def test_delete_server_by_another_user(authorized_client, auth_user):
    another_user = User.objects.create_user('testuser2', 'test2@example.com', 'password')
    another_server = Server.objects.create(user=another_user, name='Another Server', url='http://another.com')
    response = authorized_client.delete(reverse('server-detail', kwargs={'pk': str(another_server.id)}))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Server.objects.filter(pk=another_server.pk).exists()
