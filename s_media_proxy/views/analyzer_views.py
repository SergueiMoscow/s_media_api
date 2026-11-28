import json
import logging
from urllib.parse import unquote

from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.views import APIView

from s_media_proxy.proxy_view_mixin import ProxyViewMixin
from s_media_proxy.repository import get_owned_server

logger = logging.getLogger(__name__)

# Внутренние эндпоинты анализатора: их вызывает только сам API (оркестрация),
# фронт их не использует. Через generic-прокси они закрыты.
_INTERNAL_PATHS = {
    'persons/sync',
    'scanned-files/catalog-links',
}


def _normalize_analyzer_path(path: str) -> str:
    """Декодирует %2F, убирает ведущие/двойные слэши и приводит регистр."""
    decoded = unquote(path or '')
    segments = [seg for seg in decoded.split('/') if seg]
    return '/'.join(segments).lower()


def _is_internal_analyzer_path(normalized: str) -> bool:
    if normalized in _INTERNAL_PATHS:
        return True
    # catalog-files/<uuid>/link
    parts = normalized.split('/')
    return len(parts) == 3 and parts[0] == 'catalog-files' and parts[2] == 'link'


def _is_assign_path(normalized: str) -> bool:
    # clusters/<cluster_id>/assign
    parts = normalized.split('/')
    return len(parts) == 3 and parts[0] == 'clusters' and parts[2] == 'assign'


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
        normalized = _normalize_analyzer_path(analyzer_path)
        if _is_internal_analyzer_path(normalized):
            raise NotFound(detail='Not found')

        server = self._resolve_server(server_id)
        url = f'{server.analyzer_url.rstrip("/")}/{analyzer_path}'
        query_string = request.META.get('QUERY_STRING')
        if query_string:
            url = f'{url}?{query_string}'
        logger.debug('Analyzer proxy: %s %s', request.method, url)
        response = self._proxy_request(
            request_url=url,
            request=request,
            method=request.method,
            json_data={},
            api_key=server.analyzer_api_key or None,
        )

        # Эмбеддинги не должны уходить в браузер.
        if request.method == 'POST' and _is_assign_path(normalized):
            response = self._strip_reference_embedding(response)
        return response

    def _strip_reference_embedding(self, response):
        """Удаляет поле `reference_embedding` из JSON-ответа assign."""
        content_type = response.headers.get('Content-Type') or ''
        if 'json' not in content_type:
            return response
        try:
            payload = json.loads(response.content.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return response
        if isinstance(payload, dict) and 'reference_embedding' in payload:
            del payload['reference_embedding']
            response.content = json.dumps(payload).encode('utf-8')
            response['Content-Length'] = str(len(response.content))
        return response

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
