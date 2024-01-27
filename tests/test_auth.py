import pytest
from rest_framework.test import APIClient

from tests.factories import UserFactory


@pytest.mark.django_db
def test_jwt_auth():
    user = UserFactory()
    client = APIClient()

    response = client.post('/api/token/', {'username': user.username, 'password': 'defaultpassword'}, format='json')
    assert response.status_code == 200

    access_token = response.data['access']
    refresh_token = response.data['refresh']

    # Проверяем, что токен доступа можно использовать для аутентификации
    # response = client.get('/some-protected-view/', HTTP_AUTHORIZATION=f'Bearer {access_token}')
    # assert response.status_code == 200

    response = client.post('/api/token/refresh/', {'refresh': refresh_token}, format='json')
    assert response.status_code == 200
    new_access_token = response.data['access']

    assert isinstance(new_access_token, str) and new_access_token
    assert new_access_token != access_token  # Новый токен отличается от старого

    # Проверяем, что новый токен доступа также работает
    # response = client.get('/some-protected-view/', HTTP_AUTHORIZATION=f'Bearer {new_access_token}')
    # assert response.status_code == 200
