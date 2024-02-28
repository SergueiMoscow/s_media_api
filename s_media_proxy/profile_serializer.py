from rest_framework import serializers
from .models import User
from . import models


class UserProfileSerializer(serializers.ModelSerializer):
    """A serializer for user profile objects"""

    class Meta:
        model = models.User
        fields = (
            'id',
            'email',
            'username',
            'password'
        )
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        """Create and return new user"""

        user = models.User(

            email=validated_data['email'],
            username=validated_data['username'],
        )
        user.set_password(validated_data['password'])
        user.save()
        return user
