# onboarding/api/v1/serializers.py

from rest_framework import serializers
from onboarding.models import FormSubmission
from django.core.cache import cache
import json
import logging
import sys  # ← ADICIONE
from datetime import date

from .score_engine import calculate_score

logger = logging.getLogger(__name__)


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


class SubmissionWithScoreSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    Nome = serializers.CharField(allow_null=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    CPF = serializers.CharField(allow_null=True)
    Nascimento = serializers.DateField(allow_null=True)
    Criado_Em = serializers.DateTimeField()
    score = serializers.SerializerMethodField()
    is_complete = serializers.SerializerMethodField()
    missing_fields = serializers.SerializerMethodField()
    
    def get_score(self, instance):
        """Calcula e retorna o score do usuário"""
        try:
            # 🔥 LOG PARA DEBUG (vai aparecer nos logs do Render)
            print(f"\n🔍 Calculando score para usuário {instance.id} - {instance.Nome}", file=sys.stderr)
            print(f"   CPF: {instance.CPF}", file=sys.stderr)
            print(f"   Nascimento: {instance.Nascimento}", file=sys.stderr)
            
            # Cache key
            cache_key = f"score_user_{instance.id}_{instance.Criado_Em}"
            cached_score = cache.get(cache_key)
            if cached_score:
                print(f"   ✅ Score veio do cache", file=sys.stderr)
                return cached_score
            
            # Mesma lógica do endpoint /score/
            main_focus = instance.Objetivos
            if isinstance(main_focus, str):
                try:
                    main_focus = json.loads(main_focus)
                except json.JSONDecodeError:
                    main_focus = []
            
            form_data = {
                "financialAssets": instance.Patrimonio_Financeiro,
                "income": instance.Renda_Mensal,
                "incomeSource": instance.Fonte_Renda,
                "realEstateValue": instance.Patrimonio_Imobiliario,
                "succession": instance.Sucessao,
                "lifeInsurance": instance.Seguro,
                "disabilityInsurance": instance.Seguro_Invalidez,
                "corporateStructure": instance.Estrutura_Societaria,
                "risk": instance.Risco,
                "investFrequency": instance.Frequencia_Invest,
                "investPeriod": instance.Periodo_Invest,
                "preference": instance.Preferencia,
                "mainFocus": main_focus,
            }
            
            print(f"   Form data preparado", file=sys.stderr)
            
            # Chama a função de score
            score_data = calculate_score(form_data)
            
            print(f"   Score calculado: {score_data}", file=sys.stderr)
            
            if score_data:
                cache.set(cache_key, score_data, 3600)
                return score_data
            else:
                print(f"   ⚠️ score_data é None!", file=sys.stderr)
                return None
                
        except Exception as e:
            print(f"❌ ERRO: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return None
    
    def get_is_complete(self, instance):
        required_fields = ['Nome', 'CPF', 'Nascimento']
        for field in required_fields:
            if not getattr(instance, field, None):
                return False
        score = self.get_score(instance)
        return score is not None
    
    def get_missing_fields(self, instance):
        required_fields = ['Nome', 'CPF', 'Nascimento']
        missing = []
        for field in required_fields:
            if not getattr(instance, field, None):
                missing.append(field)
        return missing