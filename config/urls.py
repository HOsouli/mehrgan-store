from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls", namespace="accounts"),),
    path("api/cart/", include("apps.cart.urls", namespace="cart")),
    path("api/catalog/", include("apps.catalog.urls", namespace="catalog")),
    path("api/banners/", include("apps.banners.urls", namespace="banners")),
    path("api/orders/", include("apps.orders.urls", namespace="orders")),
    path("api/payments/", include("apps.payments.urls", namespace="payments")),
    path("api/shipments/", include("apps.shipments.urls", namespace="shipments")),
    
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(), name="swagger-ui"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
