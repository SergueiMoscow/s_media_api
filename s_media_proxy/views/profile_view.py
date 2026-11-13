from rest_framework import viewsets
from s_media_proxy.profile_serializer import UserProfileSerializer
from s_media_proxy import models


class UserProfileViewSet(viewsets.ModelViewSet):
    """Handlers creating, creating and update profiles"""

    serializer_class = UserProfileSerializer
    queryset = models.User.objects.all()

