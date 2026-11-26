import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from django.db import transaction
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from s_media_proxy.models import Server
from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import (
    get_all_servers,
    get_owned_server,
    get_server_by_id,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BaseAPIView(APIView):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server = None
        self.storage_id = None
        self.folder = ''
        self.filename = None
        self.ip = None

    def get_additional_data(self, **kwargs):
        check_owner = kwargs.pop('check_owner', True)
        server_id = kwargs.get('server_id')
        if server_id is not None:
            if check_owner:
                self.server = get_owned_server(self.request, server_id)
            else:
                self.server = get_server_by_id(server_id)
                if self.server is None:
                    raise NotFound(detail='Server not found')
        if kwargs.get('storage_id'):
            self.storage_id = kwargs['storage_id']
        folder = (
            self.request.data.get('folder') or self.request.GET.get('folder') or None
        )
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
            api_key=self.server.service_api_key or None,
        )

        # При удалении из каталога (status='inactive') дополнительно чистим связь
        # в анализаторе. Если анализатор недоступен или вернул ошибку — это не
        # повод ломать клиента: файл уже скрыт, связь исправит сверка.
        if (
            result.status_code < 400
            and (request.data or {}).get('status') == 'inactive'
            and self.server.analyzer_url
        ):
            self._clear_analyzer_link(result)
        return result

    def _clear_analyzer_link(self, response):
        try:
            payload = json.loads(response.content)
            file_id = payload['result']['id']
        except (ValueError, KeyError, TypeError):
            logger.warning(
                'fileinfo: cannot parse catalog file id for analyzer link cleanup'
            )
            return
        url = f'{self.server.analyzer_url.rstrip("/")}/catalog-files/{file_id}/link'
        headers = {'X-USER-ID': str(self.request.user.public_id)}
        if self.server.analyzer_api_key:
            headers['X-API-Key'] = self.server.analyzer_api_key
        try:
            resp = requests.delete(
                url, headers=headers, timeout=self.timeout_proxy_request
            )
            if resp.status_code >= 400:
                logger.warning(
                    f'fileinfo: analyzer link cleanup failed for {file_id}: HTTP {resp.status_code}'
                )
        except requests.RequestException as e:
            logger.warning(f'fileinfo: analyzer link cleanup failed for {file_id}: {e}')


class MainPageViewSet(APIView, ProxyViewMixin):

    # Главная доступна без JWT (её грузит лендинг).
    permission_classes = [permissions.AllowAny]

    @transaction.non_atomic_requests
    def get(self, request: Request):
        servers = self.get_distinct_servers()
        if not servers:
            raise NotFound(detail="No servers found")

        files = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            result = executor.map(self.fetch_data, servers)
        for res in result:
            files.extend(res)
        if len(files) == 0:
            raise NotFound(detail="No files found")
        # sorted_files = sorted(files, key=itemgetter('created_at'), reverse=True)  # сортировка по created_at
        files.sort(key=lambda file: file['created_at'], reverse=True)
        response = Response(
            {
                'status': 'success',
                'count': len(files),
                'results': {'files': files},
            }
        )
        return response

    def get_distinct_servers(self):
        all_servers = get_all_servers()
        # Сервера с одним `url` склеиваем: предпочитаем запись с заданным ключом.
        urls = {}
        for server in all_servers:
            existing = urls.get(server.url)
            if existing is None or (
                server.service_api_key and not existing.service_api_key
            ):
                urls[server.url] = server
        return list(urls.values())

    @transaction.non_atomic_requests
    def fetch_data(self, server: Server):
        request_url = urljoin(server.url, '/catalog/main')
        logger.info(f'file_views.py: fetching {server.url}')
        response = self._proxy_request(
            method='GET',
            request_url=request_url,
            request=self.request,
            api_key=server.service_api_key or None,
        )
        data = json.loads(response.content)
        counter = 0
        for file in data['files']:
            file['server_id'] = server.id
            counter += 1
            if counter > 10:
                pass
        logger.info(f'file_views.py: end fetching {server.url}')
        return data['files']


class BaseFileViewSet(BaseAPIView, ProxyViewMixin):

    # Фронт грузит preview/file через <img>/<video> без JWT.
    permission_classes = [permissions.AllowAny]

    action_path = ''

    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        if request.GET.get('filename'):
            # Запрос на storage_id + folder + filename
            self.get_additional_data(
                server_id=server_id, storage_id=storage_id, check_owner=False
            )
            url = f'{self.server.url}/storage/{self.action_path}/{storage_id}?folder={self.folder}&filename={self.filename}'
        else:
            # Запрос на catalog по file_id.
            file_id = storage_id
            self.get_additional_data(server_id=server_id, check_owner=False)
            url = f'{self.server.url}/catalog/{self.action_path}/{file_id}'
        additional_data = {}
        response = self._proxy_request(
            request_url=url,
            request=request,
            method='GET',
            json_data=additional_data,
            data=additional_data,
            api_key=self.server.service_api_key or None,
        )
        return response


class FilePreviewViewSet(BaseFileViewSet):
    action_path = 'preview'


class FileViewSet(BaseFileViewSet):
    action_path = 'file'
