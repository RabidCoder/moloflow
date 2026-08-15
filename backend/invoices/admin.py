from django.contrib import admin

from .models import (
    Invoice,
    InvoiceItem,
    InvoiceVersion,
    Unit,
    ReportMonth,
    InvoiceParsingError,
    WriteOffFact,
)


class InvoiceVersionAdmin(admin.ModelAdmin):
    pass


class InvoiceAdmin(admin.ModelAdmin):
    pass


class InvoiceItemAdmin(admin.ModelAdmin):
    pass


class UnitAdmin(admin.ModelAdmin):
    pass


class ReportMonthAdmin(admin.ModelAdmin):
    readonly_fields = ("year", "status", "closed_at", "end_date")


class InvoiceParsingErrorAdmin(admin.ModelAdmin):
    pass


class WriteOffFactAdmin(admin.ModelAdmin):
    pass


admin.site.register(InvoiceVersion, InvoiceVersionAdmin)
admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(InvoiceItem, InvoiceItemAdmin)
admin.site.register(Unit, UnitAdmin)
admin.site.register(ReportMonth, ReportMonthAdmin)
admin.site.register(InvoiceParsingError, InvoiceParsingErrorAdmin)
admin.site.register(WriteOffFact, WriteOffFactAdmin)
