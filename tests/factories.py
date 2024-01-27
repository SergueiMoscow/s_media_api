import uuid

import factory

from s_media_proxy.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: 'user%d' % n)
    password = factory.PostGenerationMethodCall('set_password', 'defaultpassword')
    public_id = uuid.uuid4()
