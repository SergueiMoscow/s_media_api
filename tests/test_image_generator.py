import io

import pytest
from PIL import Image

from s_media_proxy.image_generator import get_image_position, get_image_size


def test_get_image_position():
    left, top = get_image_position(200, 100, 1000, 800, 50)
    assert -50 <= left <= 900
    assert -25 <= top <= 725


def test_get_image_size():
    # Если изображение больше канвы
    new_width, new_height = get_image_size(1000, 800, 500, 400, 50)
    assert new_width == 250
    assert new_height == 200

    # Если изображение уже помещается в канву
    new_width, new_height = get_image_size(200, 150, 500, 400, 50)
    assert new_width == 200
    assert new_height == 150


@pytest.mark.parametrize('num_folders', (2, 3, 5, 10))
def test_generate_folders_image(client, num_folders):
    response = client.get(f'/folders_image?folders={num_folders}')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'image/png'
    # Попытка открыть результат как изображение
    img = Image.open(io.BytesIO(response.content))
    assert img.width == 200
    assert img.height == 100
