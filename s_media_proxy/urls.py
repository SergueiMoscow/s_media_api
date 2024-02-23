from django.urls import include, path
from rest_framework import routers
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from s_media_proxy.file_views import CatalogFileViewSet
from s_media_proxy.image_generator import generate_folders_image
from s_media_proxy.servers_views import ServerViewSet
from s_media_proxy.storage_views import (
    CollageViewSet,
    FilePreviewViewSet,
    ServersContentViewSet,
    StorageContentViewSet,
    StorageDetailViewSet,
    StorageListViewSet,
    StorageViewSet,
)
from s_media_proxy.tag_views import ServerTags

router = routers.DefaultRouter()
router.register(r'servers', ServerViewSet, basename='server')

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    # Token
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    # Servers
    path('', include(router.urls)),
    # Storages
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
    path(
        'folder_collage/<int:server_id>/<uuid:storage_id>/',
        CollageViewSet.as_view(),
        name='folder_collage',
    ),
    path(
        'preview/<int:server_id>/<uuid:storage_id>/',
        FilePreviewViewSet.as_view(),
        name='file_preview',
    ),
    path(
        'storage/fileinfo/<int:server_id>/<uuid:storage_id>/',
        CatalogFileViewSet.as_view(),
        name='catalog_file',
    ),
    # Tags
    path(
        'catalog/tags/<int:server_id>/',
        ServerTags.as_view(),
        name='server_tags',
    ),
]
