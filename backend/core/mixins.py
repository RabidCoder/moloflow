class FullCleanSaveMixin:
    """Mixin to automatically call full_clean() before saving a model instance."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
