import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from s_media_proxy.file_views import BaseAPIView
from s_media_proxy.models import Server
from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import get_server_by_id, get_servers_by_user
from s_media_proxy.services import get_url_and_additional_data_for_request


class StorageListViewSet(APIView, ProxyViewMixin):
    timeout_proxy_request = 5

    def get(self, request: Request):
        results = []
        errors = []
        server_id = request.query_params.get('server_id')
        if server_id:
            try:
                server = get_server_by_id(int(server_id))
                data = self.fetch_storages(request, server)
                if data:
                    results.extend(data.get('results', []))
            except (ValueError, ObjectDoesNotExist, AttributeError):
                # Если хранилище не найдено, ошибку не возвращать
                return Response(
                    {'status': 'success', 'count': 0, 'results':  []}
                )
        else:
            servers = get_servers_by_user(request.user)
            for server in servers:
                try:
                    data = self.fetch_storages(request, server)
                    if data:
                        results.extend(data.get('results', []))
                except Exception as e:  # Ловим ошибки при получении стораджей с сервера
                    errors.append({'server_id': server.id, 'error': str(e)})

        return Response({'status': 'success', 'count': len(results), 'results': results, 'errors': errors})

    def fetch_storages(self, request, server: Server) -> dict:
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


class StorageContentViewSet(BaseAPIView, ProxyViewMixin):

    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        self.get_additional_data(server_id=server_id, storage_id=storage_id)
        url = f'{self.server.url}/storage/{storage_id}?folder={self.folder}&page={self.request.GET.get("page", "")}'
        response = self._proxy_request(request_url=url, request=request, method='GET')
        try:
            content = json.loads(response.content)
        except Exception as e:
            pass
        results = content['results']
        pagination = content['pagination']
        for folder in results['folders']:
            folder['server_id'] = server_id
            folder['storage_id'] = storage_id
        # Подставить owner
        server = get_server_by_id(server_id)
        for file in results['files']:
            file['user_id'] = server.user.id
            file['user_name'] = server.user.username
        return Response({'status': 'success', 'results': results, 'pagination': pagination})


class ServersContentViewSet(APIView, ProxyViewMixin):
    # Переделать наследоваться от BaseAPIView
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
    # Переделать как наследника от BaseAPIView
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


class BaseFileViewSet(BaseAPIView, ProxyViewMixin):

    action_path = ''

    def get(self, request: Request, server_id: int, storage_id: uuid.UUID):
        if request.GET.get('filename'):
            # Запрос на storage_id + folder + filename
            self.get_additional_data(server_id=server_id, storage_id=storage_id)
            url = f'{self.server.url}/storage/{self.action_path}/{storage_id}?folder={self.folder}&filename={self.filename}'
        else:
            # Запрос на catalog по file_id.
            file_id = storage_id
            self.get_additional_data(server_id=server_id)
            url = f'{self.server.url}/catalog/{self.action_path}/{file_id}'
        additional_data = {}
        response = self._proxy_request(
            request_url=url,
            request=request,
            method='GET',
            json_data=additional_data,
            data=additional_data,
        )
        return response


class FilePreviewViewSet(BaseFileViewSet):
    action_path = 'preview'


class FileViewSet(BaseFileViewSet):
    action_path = 'file'
