from rest_framework import serializers
from .models import Banner


class BannerSerializer(serializers.ModelSerializer):
    alt_text = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = ("id", "title", "alt_text", "image", "mobile_image", "link", "open_in_new_tab", "position", "sort_order")

    def get_alt_text(self, obj):
        return obj.alt_text or obj.title
