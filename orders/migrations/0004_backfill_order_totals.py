from django.db import migrations


def backfill_totals(apps, schema_editor):
    """
    Eski buyurtmalarda subtotal va delivery_fee bo'sh edi.
    Ularni OrderItem dan qayta hisoblaymiz.
    """
    Order = apps.get_model('orders', 'Order')
    OrderItem = apps.get_model('orders', 'OrderItem')

    for order in Order.objects.filter(subtotal=0).iterator():
        subtotal = sum(
            (item.price or 0) * (item.quantity or 0)
            for item in OrderItem.objects.filter(order=order)
        )
        if subtotal:
            order.subtotal = subtotal
            order.total_price = subtotal + (order.delivery_fee or 0)
            order.save(update_fields=['subtotal', 'total_price'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_order_cancel_reason_order_cancelled_at_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_totals, noop),
    ]