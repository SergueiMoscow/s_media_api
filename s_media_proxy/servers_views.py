from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from s_media_proxy.repository import get_servers_by_user
from s_media_proxy.serializers import ServerSerializer


class ServerViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ServerSerializer

    def get_queryset(self):
        servers = get_servers_by_user(self.request.user)
        return servers

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if (
            request.user != instance.user
        ):  # Предполагается, что у объекта есть атрибут `user`
            raise PermissionDenied('У вас нет разрешения на выполнение этой операции.')

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
