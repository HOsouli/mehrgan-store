from rest_framework.generics import RetrieveAPIView, ListAPIView
from .models import Product
from .serializers import ProductDetailSerializer, ProductListSerializer
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter


class ProductPagination(PageNumberPagination):
    page_size = 24

class ProductListView(ListAPIView):
    permission_classes = [AllowAny]
    queryset = Product.objects.select_related("category", "brand").prefetch_related("cars", "images")
    serializer_class = ProductListSerializer
    pagination_class = ProductPagination
    filter_backends = [SearchFilter]
    search_fields = ["name", "model"]


class ProductDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Product.objects.select_related("category", "brand").prefetch_related("cars", "images")
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"




# --- QUERY OPTIMIZATION ---
# select_related → ForeignKey / OneToOne
# prefetch_related → ManyToMany / Reverse FK
