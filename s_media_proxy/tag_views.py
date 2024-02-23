from rest_framework.request import Request

from s_media_proxy.file_views import BaseAPIView
from s_media_proxy.proxy_view_mixin import ProxyViewMixin


class ServerTags(BaseAPIView, ProxyViewMixin):
    def get(self, request: Request, server_id: int):
        self.get_additional_data(server_id=server_id)
        url = f'{self.server.url}/storage/tags'
        result = self._proxy_request(
            method='GET',
            request_url=url,
            request=request,
        )
        return result
