import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)


class Server(models.Model):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    name = models.CharField(verbose_name='Title', max_length=20)
    url = models.URLField(verbose_name='URL', blank=False, max_length=128)
    created_at = models.DateField(verbose_name='Created', auto_now_add=True)

    objects = models.Manager()
