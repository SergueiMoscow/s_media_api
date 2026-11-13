import json
from unittest.mock import patch, Mock

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from s_media_proxy.models import Server

User = get_user_model()


class UploadFileTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # Сервер с возможностью загрузки
        self.server_with_upload = Server.objects.create(
            user=self.user,
            name='UploadServer',
            url='http://localhost:8001',
            can_add=True
        )

        # Сервер без возможности загрузки
        self.server_without_upload = Server.objects.create(
            user=self.user,
            name='ReadOnlyServer',
            url='http://localhost:8002',
            can_add=False
        )

        # Сервер другого пользователя
        self.other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123'
        )
        self.other_server = Server.objects.create(
            user=self.other_user,
            name='OtherServer',
            url='http://localhost:8003',
            can_add=True
        )

        self.upload_url = reverse('upload_file')
        self.test_file_content = b'test file content'

    def test_upload_missing_user_id_header(self):
        """Тест: отсутствует заголовок X-User-ID"""
        response = self.client.post(
            f'{self.upload_url}?server_id={self.server_with_upload.id}',
            data=self.test_file_content,
            content_type='application/octet-stream'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('X-User-ID', response.json()['error'])

    def test_upload_missing_server_id(self):
        """Тест: отсутствует параметр server_id"""
        response = self.client.post(
            self.upload_url,
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('server_id', response.json()['error'])

    def test_upload_server_not_found(self):
        """Тест: сервер не найден"""
        response = self.client.post(
            f'{self.upload_url}?server_id=99999',
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn('not found', response.json()['error'])

    def test_upload_access_denied_other_user_server(self):
        """Тест: доступ запрещен к серверу другого пользователя"""
        response = self.client.post(
            f'{self.upload_url}?server_id={self.other_server.id}',
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn('not found or access denied', response.json()['error'])

    def test_upload_server_does_not_allow_uploads(self):
        """Тест: сервер не разрешает загрузку"""
        response = self.client.post(
            f'{self.upload_url}?server_id={self.server_without_upload.id}',
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('does not allow', response.json()['error'])

    @patch('s_media_proxy.views.upload_view.requests.post')
    def test_upload_success(self, mock_post):
        """Тест: успешная загрузка файла"""
        # Мокируем ответ от сервиса
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.content = json.dumps({
            'id': 123,
            'filename': 'test.jpg',
            'url': '/media/test.jpg'
        }).encode()
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_post.return_value = mock_response

        response = self.client.post(
            f'{self.upload_url}?server_id={self.server_with_upload.id}'
            f'&original_filename=test.jpg&note=Test note&tags=tag1,tag2&is_public=true',
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 201)

        # Проверяем, что был сделан правильный запрос
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        self.assertEqual(
            call_args[0][0],
            'http://localhost:8001/upload'
        )
        self.assertEqual(call_args[1]['params']['original_filename'], 'test.jpg')
        self.assertEqual(call_args[1]['params']['note'], 'Test note')
        self.assertEqual(call_args[1]['params']['tags'], 'tag1,tag2')
        self.assertEqual(call_args[1]['params']['is_public'], 'true')
        self.assertEqual(call_args[1]['headers']['X-User-ID'], str(self.user.id))
        self.assertEqual(call_args[1]['data'], self.test_file_content)

    @patch('s_media_proxy.views.upload_view.requests.post')
    def test_upload_service_error(self, mock_post):
        """Тест: ошибка от сервиса"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.content = json.dumps({
            'error': 'Internal server error'
        }).encode()
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_post.return_value = mock_response

        response = self.client.post(
            f'{self.upload_url}?server_id={self.server_with_upload.id}',
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 500)

    @patch('s_media_proxy.views.upload_view.requests.post')
    def test_upload_connection_error(self, mock_post):
        """Тест: ошибка подключения к сервису"""
        mock_post.side_effect = requests.exceptions.ConnectionError('Connection refused')

        response = self.client.post(
            f'{self.upload_url}?server_id={self.server_with_upload.id}',
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn('Cannot connect', response.json()['error'])

    @patch('s_media_proxy.views.upload_view.requests.post')
    def test_upload_timeout(self, mock_post):
        """Тест: таймаут при загрузке"""
        mock_post.side_effect = requests.exceptions.Timeout('Timeout')

        response = self.client.post(
            f'{self.upload_url}?server_id={self.server_with_upload.id}',
            data=self.test_file_content,
            content_type='application/octet-stream',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 504)
        self.assertIn('timeout', response.json()['error'])

    def test_upload_get_method_not_allowed(self):
        """Тест: GET метод не разрешен"""
        response = self.client.get(
            f'{self.upload_url}?server_id={self.server_with_upload.id}',
            HTTP_X_USER_ID=str(self.user.id)
        )

        self.assertEqual(response.status_code, 405)
