from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import(
    RequestOTPSerializer, VerifyOTPSerializer, OTPRequestResponseSerializer, VerifyOTPResponseSerializer, LogoutSerializer
)
from .services import OTPService, AuthService
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from rest_framework.permissions import AllowAny
from .throttles import OTPRequestThrottle, OTPRequestIPThrottle, OTPVerifyThrottle, OTPVerifyIPThrottle


@extend_schema(
    summary="Request OTP",
    description="Send a one-time verification code to the user's mobile number.",
    request=RequestOTPSerializer,
    responses={
        200: OTPRequestResponseSerializer,
        400: OpenApiResponse(
            description="Invalid phone number or request cooldown."
        ),
    },
)
class RequestOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle, OTPRequestIPThrottle]
    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data["phone_number"]
        OTPService.request_otp(phone_number=phone_number)
        return Response({
            "message": "کد تایید با موفقیت ارسال شد"
        })


GUEST_CART_TOKEN_PARAMETER = OpenApiParameter(
    name="X-Guest-Cart-Token",
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description="شناسه سبد خرید مهمان برای ادغام سبد پس از ورود",
)
@extend_schema(
    summary="Verify OTP",
    description="Verify the OTP code and return JWT access and refresh tokens.",
    request=VerifyOTPSerializer,
    parameters=[GUEST_CART_TOKEN_PARAMETER],
    responses={
        200: VerifyOTPResponseSerializer,
        400: OpenApiResponse(
            description="Invalid, expired, or blocked OTP."
        ),
    },
)
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle, OTPVerifyIPThrottle]
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data["phone_number"]
        code = serializer.validated_data["code"]
        guest_token = request.headers.get("X-Guest-Cart-Token")
        tokens = OTPService.verify_otp(phone_number=phone_number, code=code, guest_token=guest_token)
        return Response(tokens, status=status.HTTP_200_OK)


@extend_schema(
    summary="Logout",
    description="Blacklist the current refresh token and end the user's authenticated session.",
    request=LogoutSerializer,
    responses={
        200: OTPRequestResponseSerializer,
        400: OpenApiResponse(
            description="Invalid refresh token."
        ),
    },
)
class LogoutView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.logout(serializer.validated_data["refresh"])
        return Response({"message": "با موفقیت از حساب خارج شدید"})


