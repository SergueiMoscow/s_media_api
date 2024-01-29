import io
import os
import random

from django.http import HttpResponse
from PIL import Image
from rest_framework.decorators import api_view

from django_app.settings import BASE_DIR


def get_image_position(
    image_width: int,
    image_height: int,
    canvas_width: int,
    canvas_height: int,
    min_percent: int,
) -> (int, int):
    # Вычисление минимального и максимального значения для left
    left_min = 0 - (min_percent / 2) / 100 * image_width
    left_max = canvas_width - ((100 - min_percent) / 2) / 100 * image_width

    # Вычисление минимального и максимального значения для top
    top_min = 0 - (min_percent / 2) / 100 * image_height
    top_max = canvas_height - ((100 - min_percent) / 2) / 100 * image_height

    # Генерация случайных значений для left и top в заданных диапазонах
    left = random.uniform(left_min, left_max)
    top = random.uniform(top_min, top_max)

    # Возвращение результата
    return int(left), int(top)


def get_image_size(
    image_width: int,
    image_height: int,
    canvas_width: int,
    canvas_height: int,
    min_percent: int,
) -> (int, int):
    """
    Возвращает новые размеры изображения, чтобы они были не более min_percent % от размера холста.
    """
    max_width = (canvas_width * min_percent) // 100
    max_height = (canvas_height * min_percent) // 100

    # Пропорционально уменьшаем изображение, если оно превышает максимально допустимые размеры
    if image_width > max_width or image_height > max_height:
        width_ratio = max_width / image_width
        height_ratio = max_height / image_height

        # Используем наименьшее из отношений, чтобы изображение умещалось по обеим осям
        scale_factor = min(width_ratio, height_ratio)

        # Получаем новые размеры, округляем их до целого числа
        new_width = int(image_width * scale_factor)
        new_height = int(image_height * scale_factor)
    else:
        # Размеры изображения уже удовлетворяют ограничениям, оставляем их без изменений
        new_width, new_height = image_width, image_height

    return round(new_width), round(new_height)


def generate_image(
    src_img_path: str,
    max_images: int,
    width: int,
    height: int,
    min_percent_visible: int,
) -> bytes:
    # Открытие исходного изображения
    with Image.open(src_img_path) as src_img:
        # Меняем размеры (если нужно)
        src_img = src_img.resize(
            (get_image_size(src_img.width, src_img.height, width, height, 50))
        )

        # Создание пустой канвы для результирующего изображения
        result_img = Image.new('RGB', (width, height), color=(255, 255, 255))

        for _ in range(max_images):
            # Поворот случайным образом
            angle = random.uniform(-70, 70)
            rotated = src_img.convert('RGBA').rotate(angle, expand=True)

            # Создаем маску для повернутого изображения
            mask = rotated.convert('RGBA')
            # Случайное положение
            x_pos, y_pos = get_image_position(
                image_width=rotated.width,
                image_height=rotated.height,
                canvas_width=width,
                canvas_height=height,
                min_percent=min_percent_visible,
            )
            result_img.paste(rotated, (x_pos, y_pos), mask)

        # Сохранение результата в байты
        img_byte_arr = io.BytesIO()
        result_img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

    return img_byte_arr


# # Для использования в FastAPI
# from fastapi import FastAPI
# from fastapi.responses import StreamingResponse
#
# app = FastAPI()
#
#
# @app.get("/generate_image")
# def get_image(folders: int):
#     # Замените 'path_to_image.webp' на путь к вашему файлу .webp
#     img_bytes = generate_image('path_to_image.webp', folders, 800, 600, 10)
#     return StreamingResponse(io.BytesIO(img_bytes), media_type="image/png")
#

# class FoldersImageGenerator(APIView):
#     def get(self):
#         return StreamingResponse(io.BytesIO(img_bytes), media_type="image/png")


@api_view(['GET'])
def generate_folders_image(request):
    folders = request.GET.get('folders')
    max_images = int(folders)
    width = 200
    height = 100
    min_percent_visible = 20
    source_image = os.path.join(BASE_DIR, 'images/folder.png')
    print(source_image)
    img_bytes = generate_image(
        src_img_path=source_image,
        max_images=max_images,
        width=width,
        height=height,
        min_percent_visible=min_percent_visible,
    )

    return HttpResponse(img_bytes, content_type='image/png')
