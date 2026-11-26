import uuid

from rest_framework.request import Request

from s_media_proxy.repository import get_owned_server


def get_url_and_additional_data_for_request(
    server_id: int, storage_id: uuid.UUID, request: Request
) -> tuple:
    server = get_owned_server(request, server_id)
    url = f'{server.url}/storages/{storage_id}'
    additional_data = {'user_id': str(request.user.public_id)}
    return url, additional_data, server
