from rest_framework.throttling import SimpleRateThrottle


class PhoneBasedThrottle(SimpleRateThrottle):

    def get_phone_number(self, request):
        data = getattr(request, "data", None)

        if isinstance(data, dict):
            phone = data.get("phone_number")

            if isinstance(phone, str) and phone.strip():
                return phone.strip()

        return None

    def get_cache_key(self, request, view):
        phone = self.get_phone_number(request)

        if phone is None:
            return self.cache_format % {
                "scope": self.scope,
                "ident": f"invalid:{self.get_ident(request)}",
            }

        return self.cache_format % {
            "scope": self.scope,
            "ident": f"phone:{phone}",
        }


class IPBasedThrottle(SimpleRateThrottle):

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class OTPRequestThrottle(PhoneBasedThrottle):
    """OTP request — limit per mobile number."""
    scope = "otp_request"


class OTPRequestIPThrottle(IPBasedThrottle):
    """OTP request — secondary limit per IP address."""
    scope = "otp_request_ip"


class OTPVerifyThrottle(PhoneBasedThrottle):
    """OTP verification — limit per mobile number."""
    scope = "otp_verify"


class OTPVerifyIPThrottle(IPBasedThrottle):
    """OTP verification — secondary limit per IP address."""
    scope = "otp_verify_ip"




# IP
#  ↓
# 5 request/min
#  ↓
# request-otp
#  ↓
# phone_number
#  ↓
# Cooldown = 120 sec



# IP
#  ↓
# 10 request/min
#  ↓
# verify-otp
#  ↓
# OTP
#  ↓
# MAX_ATTEMPTS = 6
#  ↓
# BLOCK = 5 min
