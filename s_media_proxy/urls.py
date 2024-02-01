from django.urls import include, path
from rest_framework import routers
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from s_media_proxy.image_generator import generate_folders_image
from s_media_proxy.views import (
    ServersContentViewSet,
    ServerViewSet,
    StorageContentViewSet,
    StorageDetailViewSet,
    StorageListViewSet,
    StorageViewSet, CollageViewSet,
)

router = routers.DefaultRouter()
router.register(r'servers', ServerViewSet, basename='server')

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    # Token
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('', include(router.urls)),
    path('storages/', StorageListViewSet.as_view(), name='list-create-storage'),
    path(
        'storages/<uuid:storage_id>/',
        StorageDetailViewSet.as_view(),
        name='storage-detail',
    ),
    path(
        'storages/<int:server_id>/<uuid:storage_id>/',
        StorageViewSet.as_view(),
        name='storage-edit-delete',
    ),
    # storage content
    path(
        'servers_content/',
        ServersContentViewSet.as_view(),
        name='get-storage-content',
    ),
    path(
        'storage/<int:server_id>/<uuid:storage_id>/',
        StorageContentViewSet.as_view(),
        name='get-storage-content',
    ),
    path('folders_image', generate_folders_image, name='generate_folders_image'),
    path('folder_collage/<int:server_id>/<uuid:storage_id>/', CollageViewSet.as_view(), name='folder_collage'),
]
