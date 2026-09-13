from django.urls import path
from .views import RequestOTPView, VerifyOTPView, LogoutView
from rest_framework_simplejwt.views import TokenRefreshView



app_name = "accounts"

urlpatterns = [
    path("auth/request-otp/", RequestOTPView.as_view(), name="request_otp"),
    path("auth/verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh-token"),
    path("auth/logout/", LogoutView.as_view(), name="logout",),
]

