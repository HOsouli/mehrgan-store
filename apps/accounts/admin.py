from django.contrib import admin
from .models import CustomUser, OTP

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "is_verified", "is_active", "is_staff", "date_joined",)
    search_fields = ("phone_number",)
    list_filter = ("is_verified", "is_active", "is_staff",)
    ordering = ("-date_joined",)
    readonly_fields = ("id", "date_joined")


