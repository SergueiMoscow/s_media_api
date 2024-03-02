import json
import os
import uuid
from operator import itemgetter
from urllib.parse import urljoin

from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from concurrent.futures import ThreadPoolExecutor, as_completed

from s_media_proxy.models import Server
from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import get_server_by_id, get_all_servers, get_distinct_server_urls, get_server_by_url


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
        folder = self.request.data.get('folder') or self.request.GET.get('folder') or None
        if folder:
            self.folder = folder
        filename = self.request.data.get('filename') or self.request.GET.get('filename')
        if filename:
            self.filename = filename
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


class MainPageViewSet(APIView, ProxyViewMixin):
    def get(self, request: Request):
        servers_urls = get_distinct_server_urls()
        if len(servers_urls) == 0:
            raise NotFound(detail="No servers found")

        files = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            result = executor.map(self.fetch_data, servers_urls)
        for res in result:
            files.extend(res)
        if len(files) == 0:
            raise NotFound(detail="No files found")
        sorted_files = sorted(files, key=itemgetter('created_at'), reverse=True)  # сортировка по created_at
        return Response(
            {
                'status': 'success',
                'count': len(files),
                'results': {'files': sorted_files},
            }
        )

    def fetch_data(self, server_url: str):
        request_url = urljoin(server_url, '/catalog/main')
        response = self._proxy_request(
            method='GET',
            request_url=request_url,
            request=self.request,
        )
        data = json.loads(response.content)
        server = get_server_by_url(server_url)
        for file in data['files']:
            file['server_id'] = server.id
        return data['files']
