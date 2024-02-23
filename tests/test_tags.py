from unittest.mock import ANY

import pytest


@pytest.mark.django_db
def test_user_tags(authorized_client, mock_created_server, mock_request):
    server_id = mock_created_server.return_value.id
    url = f'/catalog/tags/{server_id}/'
    mock_request.return_value.content = '{"results":[]}'
    response = authorized_client.get(url)
    assert response.status_code == 200
    mock_request.assert_called_once_with(
        'GET',
        f'{mock_created_server.return_value.url}/catalog/tags',
        data={},
        files=ANY,
        json={},
        headers=ANY,
        timeout=ANY,
        verify=True,
    )


