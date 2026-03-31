from rest_framework import serializers
from onboarding.models import FormSubmission

class FormSubmissionSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = FormSubmission
        fields = "__all__"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field in instance._meta.fields:
            if field.choices:
                method = f"get_{field.name}_display"
                if hasattr(instance, method):
                    data[f"{field.name}_label"] = getattr(instance, method)()
        return data