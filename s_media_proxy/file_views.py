import uuid

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import get_server_by_id


class BaseAPIView(APIView):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server = None
        self.storage_id = None
        self.folder = None
        self.filename = None
        self.ip = None

    def get_additional_data(self, **kwargs):
        if kwargs.get('server_id'):
            self.server = get_server_by_id(kwargs['server_id'])
        if kwargs.get('storage_id'):
            self.storage_id = kwargs['storage_id']
        if self.request.data.get('folder'):
            self.folder = self.request.data.get('folder')
        if self.request.data.get('filename'):
            self.folder = self.request.data.get('filename')
        self._get_client_ip()

    def _get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            self.ip = x_forwarded_for.split(',')[0]
        else:
            self.ip = self.request.META.get('REMOTE_ADDR')


class CatalogFileViewSet(BaseAPIView, ProxyViewMixin):
    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        self.get_additional_data(server_id=server_id, storage_id=storage_id)
        # TO_DO Не доделано, добавить request!!!
        return Response(
            {
                'status': 'success',
                'count': 0,
                'results': {'folders': []},
            }
        )

    def post(self, request: Request, server_id: int, storage_id: uuid.UUID):
        self.get_additional_data(server_id=server_id, storage_id=storage_id)
        url = f'{self.server.url}/storage/fileinfo'
        additional_data = {
            'ip': self.ip,
            'storage_id': str(self.storage_id),
        }
        result = self._proxy_request(
            method='POST',
            request_url=url,
            request=request,
            json_data=additional_data,
        )
        return result
