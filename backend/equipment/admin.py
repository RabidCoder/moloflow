from django.contrib import admin

from .models import Company, Equipment, SparePart


class CompanyAdmin(admin.ModelAdmin):
    pass


class EquipmentAdmin(admin.ModelAdmin):
    pass


class SparePartAdmin(admin.ModelAdmin):
    pass


admin.site.register(Company, CompanyAdmin)
admin.site.register(Equipment, EquipmentAdmin)
admin.site.register(SparePart, SparePartAdmin)
