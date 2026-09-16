from rest_framework.generics import RetrieveAPIView, ListAPIView
from .models import Product
from .serializers import ProductDetailSerializer, ProductListSerializer


class ProductListView(ListAPIView):
    queryset = Product.objects.select_related("category", "brand").prefetch_related("cars", "images")
    serializer_class = ProductListSerializer


class ProductDetailView(RetrieveAPIView):
    queryset = Product.objects.select_related("category", "brand").prefetch_related("cars", "images")
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"



# --- QUERY OPTIMIZATION ---
# select_related → ForeignKey / OneToOne
# prefetch_related → ManyToMany / Reverse FK
