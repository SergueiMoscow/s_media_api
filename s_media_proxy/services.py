import uuid

from rest_framework.exceptions import NotFound
from rest_framework.request import Request

from s_media_proxy.repository import get_server_by_id


def get_url_and_additional_data_for_request(
        server_id: int, storage_id: uuid.UUID, request: Request
) -> tuple:
    server = get_server_by_id(server_id)
    if server is None:
        raise NotFound(detail='Server not found')
    url = f'{server.url}/storages/{storage_id}'
    additional_data = {'user_id': str(request.user.public_id)}
    return url, additional_data
