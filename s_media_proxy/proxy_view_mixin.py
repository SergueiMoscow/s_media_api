import logging
import uuid
from abc import ABC

import requests
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.http import HttpResponse
from rest_framework.request import Request

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # INFO, WARNING, ERROR или DEBUG

# Создаем обработчик логирования, который будет выводить сообщения в stderr
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG) # INFO, WARNING, ERROR или DEBUG

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class ProxyViewMixin(ABC):
    timeout_proxy_request: int = 60

    def _proxy_request(
        self,
        request_url: str,
        request: Request,
        method: str,
        data=None,
        json_data=None,
        timeout: int = None,
        verify: bool = True,
    ):
        # request_url = request.get_full_path()
        if data is None:
            data = {}
        if isinstance(request.user, AnonymousUser):
            user_id = ''
        else:
            user_id = str(request.user.public_id)
        request_header = {
            'X-USER-ID': user_id,
            'X-REQUEST-ID': str(uuid.uuid4()),
        }
        if data is None:
            data = {}
        if json_data is None:
            json_data = {}

        if 'multipart/form-data' in request.content_type:
            for key, value in request.data.items():
                if isinstance(value, (InMemoryUploadedFile, TemporaryUploadedFile)):
                    continue
                data[key] = value

        if 'application/json' in request.content_type and not request.FILES:
            json_data.update(request.data)

        # Логгируем детали запроса перед его выполнением
        logger.info(f'Proxy request: {method} {request_url}')
        # logger.info(f'Proxy request timeout: {self.timeout_proxy_request or timeout}')
        # logger.info(f'Proxy request verify: {verify}')
        if data:
            logger.debug(f'Proxy request data: {data}')
        if json_data:
            logger.debug(f'Proxy request json data: {json_data}')
        if request.FILES:
            logger.debug('Proxy request has files')

        proxy_response = requests.request(
            method,
            request_url,
            data=data,
            files=request.FILES,
            json=json_data,
            headers=request_header,
            timeout=self.timeout_proxy_request or timeout,
            verify=verify,
        )
        logger.info(f'Proxy response status code: {proxy_response.status_code}')

        response = HttpResponse(
            proxy_response.content,
            status=proxy_response.status_code,
            content_type=proxy_response.headers.get('Content-Type'),
        )

        return response
