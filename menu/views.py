"""
Public menu & config API.

Mijoz mini app uchun yagona dinamik manba:
  /api/config/           — barcha sozlamalar (nom, narx, ish vaqti ...)
  /api/menu/categories/  — kategoriyalar + bannerlar
  /api/menu/items/       — mahsulotlar (qidiruv, kategoriya, mashhur)
"""
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts import settings_service
from .models import Category, MenuItem, Banner


@require_GET
def config(request):
    """
    GET /api/config/
    Ilovaning barcha dinamik sozlamalari. Frontend shuni birinchi chaqiradi.
    """
    return JsonResponse({
        'config': settings_service.public_config(),
        'version': settings_service.CACHE_KEY,
    })


@require_GET
def categories_list(request):
    """GET /api/menu/categories/ — faol kategoriyalar va bannerlar."""
    cats = Category.objects.filter(is_active=True).order_by('order', 'name')

    cats_list = [{
        'id': c.id,
        'name': c.name,
        'icon': c.icon,
        'image_url': c.image.url if c.image else None,
        'order': c.order,
    } for c in cats]

    default_interval = settings_service.banner_interval()
    banners = [
        b.to_dict(default_interval=default_interval)
        for b in Banner.objects.filter(is_active=True).order_by('order', '-created_at')
    ]

    return JsonResponse({
        'categories': cats_list,
        'banners': banners,
        'config': settings_service.public_config(),
    })


@require_GET
def items_list(request):
    """
    GET /api/menu/items/
    ?category=<id>  — kategoriya bo'yicha
    ?popular=1      — faqat mashhur
    ?q=<matn>       — nom va tavsif bo'yicha qidiruv
    ?max=<son>      — natijalar soni (default 200)
    """
    queryset = MenuItem.objects.filter(is_available=True).select_related('category')

    category_id = request.GET.get('category')
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    if request.GET.get('popular'):
        queryset = queryset.filter(is_popular=True)

    query = (request.GET.get('q') or '').strip()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    try:
        limit = min(500, max(1, int(request.GET.get('max', 200))))
    except (TypeError, ValueError):
        limit = 200

    items = [item.to_dict() for item in queryset[:limit]]
    return JsonResponse({'items': items, 'count': len(items), 'query': query})


@require_GET
def item_detail(request, item_id):
    """GET /api/menu/items/<id>/ — bitta mahsulot."""
    try:
        item = MenuItem.objects.select_related('category').get(
            id=item_id, is_available=True
        )
        related = MenuItem.objects.filter(
            category=item.category, is_available=True
        ).exclude(id=item.id)[:6]

        return JsonResponse({
            'item': item.to_dict(),
            'related': [r.to_dict() for r in related],
        })
    except MenuItem.DoesNotExist:
        return JsonResponse({'error': 'Mahsulot topilmadi'}, status=404)