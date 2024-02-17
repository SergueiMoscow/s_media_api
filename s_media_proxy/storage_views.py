import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from s_media_proxy.models import Server
from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import get_server_by_id, get_servers_by_user
from s_media_proxy.services import get_url_and_additional_data_for_request


class StorageListViewSet(APIView, ProxyViewMixin):
    timeout_proxy_request = 5

    def get(self, request: Request):
        results = []
        server_id = request.query_params.get('server_id')
        # if server_id:
        try:
            server = get_server_by_id(int(server_id))
            data = self.fetch_storages(request, server)
        except (ValueError, ObjectDoesNotExist, AttributeError):
            return Response({'error': 'Invalid server ID'}, status=400)
        if data:
            results.extend(data.get('results', []))

        return Response(
            {'status': 'success', 'count': len(results), 'results': results}
        )

    def fetch_storages(self, request, server: Server) -> list:
        url = f'{server.url}/storages/'
        # try:
        response = self._proxy_request(request_url=url, request=request, method='GET')
        data = json.loads(response.content)
        for storage in data['results']:
            storage['server_id'] = server.id
            storage['server_name'] = server.name
            storage['server_url'] = server.url
        return data
        # except Exception as e:
        #     print(e)
        #     return None

    def post(self, request: Request):
        user = request.user
        server_id = request.data.get('server_id')
        server = get_server_by_id(server_id)
        url = f'{server.url}/storages/'
        additional_data = {
            'user_id': str(user.public_id),
            'created_by': str(user.public_id),
        }
        return self._proxy_request(
            request_url=url, request=request, method='POST', json_data=additional_data
        )


class StorageDetailViewSet(APIView, ProxyViewMixin):
    timeout_proxy_request = 5

    def patch(self, request: Request, storage_id: uuid.UUID):
        server = get_server_by_id(request.data.get('server_id'))
        url = f'{server.url}/storages/{storage_id}'
        additional_data = {'user_id': str(request.user.public_id)}
        if server is None:
            return NotFound(code='storage_not_found', detail='Storage not found')
        return self._proxy_request(
            request_url=url,
            request=request,
            method='PATCH',
            json_data=additional_data,
        )


class StorageViewSet(APIView, ProxyViewMixin):
    timeout_proxy_request = 5

    def patch(self, request: Request, server_id: int, storage_id: uuid.UUID):
        url, additional_data = get_url_and_additional_data_for_request(
            server_id, storage_id, request
        )
        return self._proxy_request(
            request_url=url, request=request, method='PATCH', json_data=additional_data
        )

    def delete(self, request: Request, server_id: int, storage_id: uuid.UUID):
        url, _ = get_url_and_additional_data_for_request(server_id, storage_id, request)
        return self._proxy_request(request_url=url, request=request, method='DELETE')


class StorageContentViewSet(APIView, ProxyViewMixin):
    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        url, _ = self.get_url_and_additional_data_for_request(server_id, storage_id)
        response = self._proxy_request(request_url=url, request=request, method='GET')
        # TO_DO: Здесь подставить server_id, storage_id
        content = json.loads(response.content)['results']
        for folder in content['folders']:
            folder['server_id'] = server_id
            folder['storage_id'] = storage_id
        return Response({'status': 'success', 'results': content})

    def get_url_and_additional_data_for_request(
        self,
        server_id: int,
        storage_id: uuid.UUID,
    ) -> tuple:
        server = get_server_by_id(server_id)
        folder = self.request.GET.get('folder', '')
        if server is None:
            raise NotFound(detail='Server not found')
        url = f'{server.url}/storage/{storage_id}?folder={folder}'
        additional_data = {'user_id': str(self.request.user.public_id)}
        return url, additional_data


class ServersContentViewSet(APIView, ProxyViewMixin):
    def get(self, request: Request):
        user = request.user
        servers = get_servers_by_user(user)
        results = []
        # Создаем `ThreadPoolExecutor` для асинхронных запросов к удаленным серверам
        with ThreadPoolExecutor() as executor:
            # Словарь для сопоставления 'future' с соответствующим URL сервера
            futures = {
                executor.submit(self.fetch_storages, request, server): server
                for server in servers
            }
            for future in as_completed(futures):
                server = futures[future]
                data = future.result()
                if data:
                    for item in data.get('results', []):
                        item['server_id'] = server.id
                        item['server_name'] = server.name
                        results.append(item)

        return Response(
            {
                'status': 'success',
                'count': len(results),
                'results': {'folders': results},
            }
        )

    def fetch_storages(self, request, server: Server) -> list:
        url = f'{server.url}/storage/?user_id={request.user.public_id}'
        # try:
        response = self._proxy_request(request_url=url, request=request, method='GET')
        data = json.loads(response.content)
        if not data.get('results'):
            raise NotFound(detail='Неверный путь')
        for storage in data['results']:
            storage['server_id'] = server.id
            storage['server_name'] = server.name
            storage['server_url'] = server.url
        return data
        # except Exception as e:
        #     print(e)
        #     return None


class CollageViewSet(APIView, ProxyViewMixin):
    permission_classes = [permissions.AllowAny]

    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        url, additional_data = self.get_url_and_additional_data_for_request(
            server_id, storage_id
        )

        return self._proxy_request(
            request_url=url,
            request=request,
            method='GET',
            json_data=additional_data,
            data=additional_data,
        )

    def get_url_and_additional_data_for_request(
        self,
        server_id: int,
        storage_id: uuid.UUID,
    ) -> tuple:
        server = get_server_by_id(server_id)
        if server is None:
            raise NotFound(detail='Server not found')
        folder = self.request.GET.get('folder', '')
        url = f'{server.url}/storage/collage/{storage_id}?folder={folder}'
        additional_data = {}
        return url, additional_data


class FilePreviewViewSet(APIView, ProxyViewMixin):
    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        url, additional_data = self.get_url_and_additional_data_for_request(
            server_id, storage_id
        )
        return self._proxy_request(
            request_url=url,
            request=request,
            method='GET',
            json_data=additional_data,
            data=additional_data,
        )

    def get_url_and_additional_data_for_request(
        self,
        server_id: int,
        storage_id: uuid.UUID,
    ) -> tuple:
        server = get_server_by_id(server_id)
        if server is None:
            raise NotFound(detail='Server not found')
        folder = self.request.GET.get('folder', '')
        filename = self.request.GET.get('filename', '')
        url = f'{server.url}/storage/file/{storage_id}?folder={folder}&filename={filename}'
        additional_data = {}
        return url, additional_data
