# custom_fields.py

from django_elasticsearch_dsl.fields import Field

class DenseVectorField(Field):
    field_type = "dense_vector"

    def __init__(self, dims=None, **kwargs):
        # Force preparation method usage
        kwargs['attr'] = None  # Critical for triggering prepare_<field_name>
        super().__init__(**kwargs)
        self._dims = dims

    def get_value_from_instance(self, instance):
        # Explicitly use the field name to trigger preparation
        return getattr(instance, self._path, [0.0] * self._dims)

    def to_dict(self):
        return {
            "type": self.field_type,
            "dims": self._dims,
        }