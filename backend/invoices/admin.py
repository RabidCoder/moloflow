from django.contrib import admin

from .models import Invoice, InvoiceItem, InvoiceVersion, Unit


class InvoiceVersionAdmin(admin.ModelAdmin):
    pass


class InvoiceAdmin(admin.ModelAdmin):
    pass


class InvoiceItemAdmin(admin.ModelAdmin):
    pass


class UnitAdmin(admin.ModelAdmin):
    pass


admin.site.register(InvoiceVersion, InvoiceVersionAdmin)
admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(InvoiceItem, InvoiceItemAdmin)
admin.site.register(Unit, UnitAdmin)
