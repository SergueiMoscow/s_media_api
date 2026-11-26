import logging

from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.views import APIView

from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import get_owned_server

logger = logging.getLogger(__name__)


class AnalyzerProxyView(APIView, ProxyViewMixin):
    """Проксирует запросы к s_media_analyzer выбранного узла.

    Маршрут: /analyzer/<server_id>/<path:analyzer_path>.
    Пробрасывает заголовки X-USER-ID (текущий пользователь) и
    X-API-Key (ключ анализатора узла).
    """

    permission_classes = [permissions.IsAuthenticated]
    timeout_proxy_request = 60

    def _resolve_server(self, server_id: int):
        server = get_owned_server(self.request, server_id)
        if not server.analyzer_url:
            raise NotFound(detail='Analyzer not configured for this server')
        return server

    def _handle(self, request: Request, server_id: int, analyzer_path: str = ''):
        server = self._resolve_server(server_id)
        url = f'{server.analyzer_url.rstrip("/")}/{analyzer_path}'
        query_string = request.META.get('QUERY_STRING')
        if query_string:
            url = f'{url}?{query_string}'
        logger.debug('Analyzer proxy: %s %s', request.method, url)
        return self._proxy_request(
            request_url=url,
            request=request,
            method=request.method,
            json_data={},
            api_key=server.analyzer_api_key or None,
        )

    def get(self, request: Request, server_id: int, analyzer_path: str = ''):
        return self._handle(request, server_id, analyzer_path)

    def post(self, request: Request, server_id: int, analyzer_path: str = ''):
        return self._handle(request, server_id, analyzer_path)

    def put(self, request: Request, server_id: int, analyzer_path: str = ''):
        return self._handle(request, server_id, analyzer_path)

    def patch(self, request: Request, server_id: int, analyzer_path: str = ''):
        return self._handle(request, server_id, analyzer_path)

    def delete(self, request: Request, server_id: int, analyzer_path: str = ''):
        return self._handle(request, server_id, analyzer_path)
