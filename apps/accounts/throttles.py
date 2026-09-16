from rest_framework.throttling import SimpleRateThrottle


class OTPRequestThrottle(SimpleRateThrottle):
    scope = "otp_request"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class OTPVerifyThrottle(SimpleRateThrottle):
    scope = "otp_verify"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}



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
