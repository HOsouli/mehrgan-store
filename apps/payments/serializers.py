from rest_framework import serializers


class PaymentRequestSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()


class PaymentRequestResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=("pending", "success", "review"))
    pay_url = serializers.CharField(allow_null=True,required=False)
