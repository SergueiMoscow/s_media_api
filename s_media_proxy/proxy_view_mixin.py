import uuid
from abc import ABC

import requests
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.http import HttpResponse
from rest_framework.request import Request


class ProxyViewMixin(ABC):
    timeout_proxy_request: int = 5

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
        request_header = {
            'X-USER-ID': str(request.user.public_id),
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

        response = HttpResponse(
            proxy_response.content,
            status=proxy_response.status_code,
            content_type=proxy_response.headers.get('Content-Type'),
        )

        return response
