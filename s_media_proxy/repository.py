from typing import List

from rest_framework.exceptions import NotFound

from s_media_proxy.models import Server, User


def get_servers_by_user(user: User) -> list[Server]:
    servers = Server.objects.filter(user=user)
    return servers


def get_server_by_id(server_id: int) -> Server:
    server = Server.objects.filter(id=server_id).first()
    return server


def get_owned_server(request, server_id: int) -> Server:
    """Сервер текущего пользователя, иначе 404.

    Единая точка проверки владельца узла: если сервера нет или он принадлежит
    другому пользователю, поднимается NotFound (404) — так клиент не может
    отличить «нет такого сервера» от «сервер чужой».
    """
    server = Server.objects.filter(id=server_id, user_id=request.user.id).first()
    if server is None:
        raise NotFound(detail='Server not found')
    return server


def delete_server(server_id: int) -> bool:
    return Server.objects.delete(id=server_id)


def get_all_servers(max_count: int = 10) -> List[Server]:
    return Server.objects.all()[:max_count]


def get_distinct_server_urls(max_count: int = 10) -> List[str]:
    distinct_urls = Server.objects.values_list('url', flat=True).distinct()[:max_count]
    return list(distinct_urls)


def get_server_by_url(url: str) -> Server:
    return Server.objects.filter(url=url).first()
