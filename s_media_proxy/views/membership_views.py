"""Специальные вью для переключателя «в каталоге» (promote/unpromote).

Оркестрируют цепочку запросов: анализатор (список файлов/лиц) → сервис
(`POST /storage/fileinfo`) → анализатор (`PUT /scanned-files/catalog-links`).
В отличие от generic-прокси `AnalyzerProxyView`, здесь API сам собирает и
связывает данные между сервисом и анализатором.
"""

import json

from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import get_owned_server


class CatalogMembershipBaseView(APIView, ProxyViewMixin):
    """База для оркестрации промоушена/удаления файлов в/из каталога."""

    permission_classes = [permissions.IsAuthenticated]
    timeout_proxy_request = 60

    def _resolve_server(self, server_id: int):
        server = get_owned_server(self.request, server_id)
        if not server.analyzer_url:
            raise NotFound(detail='Analyzer not configured for this server')
        return server

    def _get_client_ip(self) -> str:
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return self.request.META.get('REMOTE_ADDR', '')

    def _proxy_json(
        self, server, method: str, path: str, body=None, use_api_key: bool = False
    ):
        """Проксирует запрос к узлу и возвращает (parsed_json, error_response).

        При статусе >=400 возвращает (None, HttpResponse) — для проброса ошибки
        узла наверх без изменений.
        """
        base_url = server.analyzer_url if use_api_key else server.url
        url = f'{base_url.rstrip("/")}/{path}'
        response = self._proxy_request(
            request_url=url,
            request=self.request,
            method=method,
            json_data=body,
            api_key=(
                (server.analyzer_api_key or None)
                if use_api_key
                else (server.service_api_key or None)
            ),
            forward_request_body=False,
        )
        if response.status_code >= 400:
            return None, response
        return json.loads(response.content), None

    def _promote_files(self, server, items, name: str):
        """Для списка элементов (PromoteItem/FaceOut) создаёт записи в каталоге.

        Возвращает (links, error) — список связей для `catalog-links`.
        """
        links = []
        for item in items:
            body = {
                'ip': self._get_client_ip(),
                'storage_id': item['storage_id'],
                'folder_path': item['folder_path'],
                'filename': item['filename'],
                'status': 'active',
            }
            if name:
                # add_tags добавляет тег, не стирая существующие; status='active'
                # возвращает ранее убранный из каталога файл.
                body['add_tags'] = [name]
            result, error = self._proxy_json(
                server, 'POST', 'storage/fileinfo', body=body
            )
            if error:
                return None, error
            links.append(
                {
                    'scanned_file_id': item['scanned_file_id'],
                    'catalog_file_id': result['result']['id'],
                }
            )
        return links, None

    def _write_catalog_links(self, server, links):
        """Записывает связи в анализаторе. Возвращает (data, error)."""
        if not links:
            return None, None
        return self._proxy_json(
            server,
            'PUT',
            'scanned-files/catalog-links',
            body={'links': links},
            use_api_key=True,
        )

    def _fetch_cluster_faces(self, server, cluster_id: int):
        """Возвращает (faces, error) — все лица кластера (с пагинацией)."""
        faces = []
        offset = 0
        limit = 1000
        while True:
            data, error = self._proxy_json(
                server,
                'GET',
                f'clusters/{cluster_id}/faces?limit={limit}&offset={offset}',
                use_api_key=True,
            )
            if error:
                return None, error
            items = data.get('items', [])
            faces.extend(items)
            offset += len(items)
            if not items or offset >= data.get('total', 0):
                break
        return faces, None


class ClusterPromoteView(CatalogMembershipBaseView):
    def post(self, request: Request, server_id: int, cluster_id: int):
        server = self._resolve_server(server_id)
        name = (request.data or {}).get('name') or ''

        items, error = self._proxy_json(
            server, 'GET', f'clusters/{cluster_id}/promotable-files', use_api_key=True
        )
        if error:
            return error

        links, error = self._promote_files(server, items, name)
        if error:
            return error

        _, error = self._write_catalog_links(server, links)
        if error:
            return error

        return Response({'status': 'ok', 'promoted': len(links)})


class ClusterUnpromoteView(CatalogMembershipBaseView):
    def post(self, request: Request, server_id: int, cluster_id: int):
        server = self._resolve_server(server_id)

        faces, error = self._fetch_cluster_faces(server, cluster_id)
        if error:
            return error

        links = []
        seen = set()
        for face in faces:
            catalog_file_id = face.get('catalog_file_id')
            if not catalog_file_id:
                continue
            scanned_file_id = face['scanned_file_id']
            if scanned_file_id in seen:
                continue
            seen.add(scanned_file_id)

            _, error = self._proxy_json(
                server,
                'POST',
                'storage/fileinfo',
                body={
                    'ip': self._get_client_ip(),
                    'id': catalog_file_id,
                    'status': 'inactive',
                },
            )
            if error:
                return error
            links.append({'scanned_file_id': scanned_file_id, 'catalog_file_id': None})

        _, error = self._write_catalog_links(server, links)
        if error:
            return error

        return Response({'status': 'ok', 'unpromoted': len(links)})


class FacePromoteView(CatalogMembershipBaseView):
    def post(self, request: Request, server_id: int, face_id: int):
        server = self._resolve_server(server_id)
        name = (request.data or {}).get('name') or ''

        face, error = self._proxy_json(
            server, 'GET', f'faces/{face_id}', use_api_key=True
        )
        if error:
            return error

        links, error = self._promote_files(server, [face], name)
        if error:
            return error

        _, error = self._write_catalog_links(server, links)
        if error:
            return error

        return Response({'status': 'ok', 'promoted': len(links)})


class FaceUnpromoteView(CatalogMembershipBaseView):
    def post(self, request: Request, server_id: int, face_id: int):
        server = self._resolve_server(server_id)

        face, error = self._proxy_json(
            server, 'GET', f'faces/{face_id}', use_api_key=True
        )
        if error:
            return error

        catalog_file_id = face.get('catalog_file_id')
        if not catalog_file_id:
            return Response({'status': 'ok', 'unpromoted': 0})

        _, error = self._proxy_json(
            server,
            'POST',
            'storage/fileinfo',
            body={
                'ip': self._get_client_ip(),
                'id': catalog_file_id,
                'status': 'inactive',
            },
        )
        if error:
            return error

        _, error = self._write_catalog_links(
            server,
            [{'scanned_file_id': face['scanned_file_id'], 'catalog_file_id': None}],
        )
        if error:
            return error

        return Response({'status': 'ok', 'unpromoted': 1})
