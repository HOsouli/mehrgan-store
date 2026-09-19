from rest_framework import serializers


class PaymentRequestSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()


class PaymentRequestResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    pay_url = serializers.CharField()
