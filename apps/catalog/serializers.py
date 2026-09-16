from rest_framework import serializers
from .models import Brand, Car, Category, Product, ProductImage


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description"]


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "description"]


class CarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = ["id", "name", "description"]


class ProductImageSerializer(serializers.ModelSerializer):
    thumbnail = serializers.ImageField(source="image_thumbnail", read_only=True)

    class Meta:
        model = ProductImage
        fields = ["id", "image", "thumbnail"]


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    cars = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    price = serializers.DecimalField(max_digits=12, decimal_places=0, coerce_to_string=False)
    stock = serializers.SerializerMethodField()
    img = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "slug", "model", "price", "stock", "category", "brand", "cars", "img"]

    def get_stock(self, obj):
        return obj.stock > 0

    def get_img(self, obj):
        image = obj.images.first()
        if not image or not image.image:
            return None
        return image.image_thumbnail.url


class ProductDetailSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", read_only=True)
    brand = serializers.CharField(source="brand.name", read_only=True)
    cars = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    price = serializers.DecimalField(max_digits=12, decimal_places=0, coerce_to_string=False)
    stock = serializers.SerializerMethodField()
    img = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "model", "description", "price", "stock", "category",
            "brand", "cars", "img", "images", "created_at", "updated_at"
        ]

    def get_stock(self, obj):
        return obj.stock > 0

    def get_img(self, obj):
        image = obj.images.first()
        if not image or not image.image:
            return None
        return image.image_thumbnail.url
