# onboarding/api/v1/serializers.py

from rest_framework import serializers
from onboarding.models import FormSubmission
from django.core.cache import cache  # ← ADICIONE ESTA LINHA
import json
from datetime import date

# Importe sua função de score
from .score_engine import calculate_score


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
    """
    Serializer que retorna os dados do FormSubmission com score embutido.
    Mais eficiente que fazer chamadas separadas.
    """
    id = serializers.IntegerField()
    Nome = serializers.CharField(allow_null=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    CPF = serializers.CharField(allow_null=True)
    Nascimento = serializers.DateField(allow_null=True)
    Criado_Em = serializers.DateTimeField()
    score = serializers.SerializerMethodField()
    is_complete = serializers.SerializerMethodField()
    missing_fields = serializers.SerializerMethodField()
    
    def _get_form_data_for_score(self, instance):
        """Prepara os dados do formulário para o cálculo do score"""
        try:
            # Processa os objetivos
            main_focus = instance.Objetivos
            if isinstance(main_focus, str):
                try:
                    main_focus = json.loads(main_focus)
                except json.JSONDecodeError:
                    main_focus = []
            
            return {
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
        except Exception:
            return None
    
    def get_score(self, instance):
        """Calcula e retorna o score do usuário com CACHE"""
        try:
            # Gera uma chave de cache única baseada no ID e data de modificação
            cache_key = f"score_user_{instance.id}_{instance.Criado_Em}"
            
            # 🔥 Tenta pegar do cache primeiro
            cached_score = cache.get(cache_key)
            if cached_score:
                return cached_score
            
            # Se não tiver cache, calcula o score
            form_data = self._get_form_data_for_score(instance)
            if form_data:
                score_data = calculate_score(form_data)
                if score_data:
                    result = {
                        'total': score_data.get('total', 0),
                        'profile': score_data.get('profile', 'Não definido'),
                        'breakdown': score_data.get('breakdown', {}),
                        'details': score_data.get('details', {}),
                    }
                    # 💾 Salva no cache por 1 hora (3600 segundos)
                    cache.set(cache_key, result, 3600)
                    return result
        except Exception as e:
            # Log do erro silencioso, não falha o serializer
            pass
        return None
    
    def get_is_complete(self, instance):
        """Verifica se o cadastro está completo"""
        # Campos obrigatórios
        required_fields = ['Nome', 'CPF', 'Nascimento']
        for field in required_fields:
            if not getattr(instance, field, None):
                return False
        
        # Verifica se tem score calculado
        return self.get_score(instance) is not None
    
    def get_missing_fields(self, instance):
        """Retorna lista de campos obrigatórios faltando"""
        required_fields = ['Nome', 'CPF', 'Nascimento']
        missing = []
        for field in required_fields:
            if not getattr(instance, field, None):
                missing.append(field)
        return missing