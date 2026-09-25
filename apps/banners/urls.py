from django.urls import path
from .views import BannerListView


app_name = "banners"


urlpatterns = [
    path("", BannerListView.as_view(), name="banner-list"),
]
