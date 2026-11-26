from django.contrib.auth.models import Group
from rest_framework import serializers

from .models import Server, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'url',
            'username',
            'email',
            'public_id',
            'groups',
        )  # И другие поля, которые вы хотите включить


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ['url', 'name']


class ServerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Server
        fields = (
            'id',
            'name',
            'url',
            'can_add',
            'analyzer_url',
            'analyzer_api_key',
            'service_api_key',
        )
        extra_kwargs = {
            'analyzer_api_key': {'write_only': True},
            'service_api_key': {'write_only': True},
        }
