from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from .models import Banner
from .serializers import BannerSerializer


class BannerListView(ListAPIView):
    serializer_class = BannerSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        queryset = Banner.objects.currently_visible()

        position = self.request.query_params.get("position")
        if position:
            queryset = queryset.filter(position=position)

        return queryset
