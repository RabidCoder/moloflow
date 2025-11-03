from django.db import models


class Invoice(models.Model):
    number = models.IntegerField()
    date = models.DateTimeField()
    file = models.FileField()

    class Meta():
        pass


class Unit(models.Model):
    name = models.CharField(max_length=20)
    symbol = models.CharField(max_length=10)
    aliases = models.JSONField()

    class Meta():
        pass


class InvoiceItem(models.Model):
    name = models.CharField(max_length=50)
    quantity = models.FloatField()
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL)

    class Meta():
        pass
