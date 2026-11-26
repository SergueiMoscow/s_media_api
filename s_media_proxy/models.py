import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)


class Server(models.Model):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    name = models.CharField(verbose_name='Title', max_length=20)
    url = models.URLField(verbose_name='URL', blank=False, max_length=128)
    can_add = models.BooleanField(verbose_name='Can add', default=False)
    analyzer_url = models.URLField(
        verbose_name='Analyzer URL', blank=True, null=True, max_length=128
    )
    analyzer_api_key = models.CharField(
        verbose_name='Analyzer API key', blank=True, default='', max_length=128
    )
    service_api_key = models.CharField(
        verbose_name='Service API key', blank=True, default='', max_length=128
    )
    created_at = models.DateField(verbose_name='Created', auto_now_add=True)

    objects = models.Manager()
