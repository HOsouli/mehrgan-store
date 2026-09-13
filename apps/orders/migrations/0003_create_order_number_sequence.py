from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_orderaddress_recipient_name_alter_order_order_number_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE orders_order_number_seq
                START WITH 100
                INCREMENT BY 1;
            """,
            reverse_sql="""
                DROP SEQUENCE IF EXISTS orders_order_number_seq;
            """,
        ),
    ]
