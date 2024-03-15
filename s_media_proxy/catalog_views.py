import json
import urllib.parse
import uuid

from rest_framework.request import Request
from rest_framework.response import Response

from s_media_proxy.file_views import BaseAPIView
from s_media_proxy.proxy_view_mixin import ProxyViewMixin


class CatalogContentViewSet(BaseAPIView, ProxyViewMixin):
    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        self.get_additional_data(server_id=server_id, storage_id=storage_id)
        url = f'{self.server.url}/catalog/content?storage_id={storage_id}&{self.get_url()}'
        additional_data = {
            'ip': self.ip,
            'storage_id': str(self.storage_id),
        }
        response = self._proxy_request(
            method='GET',
            request_url=url,
            request=request,
        )
        # Добавить данные о storage и server
        content = json.loads(response.content)
        for file in content.get('files'):
            file['storage_id'] = storage_id
            file['server_id'] = server_id
        return Response(content)

    def get_url(self):
        url = ''
        params = {key: value for key, value in self.request.query_params.items() if value}
        if params:
            url += urllib.parse.urlencode(params)
        return url


