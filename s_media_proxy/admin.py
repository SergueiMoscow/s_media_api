from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    model = User
    fieldsets = UserAdmin.fieldsets + (
        (
            None,
            {'fields': ('public_id',)},
        ),  # Добавьте public_id в секцию, где вы хотите его видеть
    )
    readonly_fields = (
        'public_id',
    )  # Если вы хотите, чтобы public_id был только для чтения


admin.site.register(User, CustomUserAdmin)
