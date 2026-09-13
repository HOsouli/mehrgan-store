from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE invoices_invoice_number_seq
                START WITH 1000
                INCREMENT BY 1;
            """,
            reverse_sql="""
                DROP SEQUENCE IF EXISTS invoices_invoice_number_seq;
            """,
        ),
    ]
