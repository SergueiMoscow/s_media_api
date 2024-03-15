from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    model = User
    fieldsets = UserAdmin.fieldsets + (
        (
            None,
            {'fields': ('public_id',)},
        ),
    )
    readonly_fields = (
        'public_id',
    )


admin.site.register(User, CustomUserAdmin)
