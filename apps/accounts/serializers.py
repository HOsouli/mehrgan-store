from rest_framework import serializers
from .models import mobile_validate


class RequestOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=11, min_length=11, validators=[mobile_validate])


class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=11, min_length=11, validators=[mobile_validate])
    code = serializers.RegexField(regex=r"^\d{6}$")


class OTPRequestResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class VerifyOTPResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
