# onboarding/api/v1/serializers.py

from rest_framework import serializers
from onboarding.models import FormSubmission
from django.core.cache import cache
import json
import logging  # ← ADICIONE ESTA LINHA
from datetime import date

from .score_engine import calculate_score

# 🔥 ADICIONE ESTE LOGGER
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
        except Exception as e:
            logger.error(f"Erro em _get_form_data_for_score: {e}")
            return None
    
    def get_score(self, instance):
        """Calcula e retorna o score do usuário com CACHE"""
        try:
            # Gera uma chave de cache única
            cache_key = f"score_user_{instance.id}_{instance.Criado_Em}"
            
            # Tenta pegar do cache primeiro
            cached_score = cache.get(cache_key)
            if cached_score:
                logger.info(f"Score do usuário {instance.id} veio do cache")
                return cached_score
            
            # 🔥 LOG: tentando calcular score
            logger.info(f"Calculando score para usuário {instance.id} - {instance.Nome}")
            
            form_data = self._get_form_data_for_score(instance)
            
            # 🔥 LOG: dados do formulário
            logger.debug(f"Form data: {form_data}")
            
            if form_data:
                score_data = calculate_score(form_data)
                
                # 🔥 LOG: resultado do cálculo
                logger.info(f"Score calculado para {instance.id}: {score_data}")
                
                if score_data:
                    result = {
                        'total': score_data.get('total', 0),
                        'profile': score_data.get('profile', 'Não definido'),
                        'breakdown': score_data.get('breakdown', {}),
                        'details': score_data.get('details', {}),
                    }
                    cache.set(cache_key, result, 3600)
                    return result
                else:
                    logger.warning(f"score_data é None para usuário {instance.id}")
            else:
                logger.warning(f"form_data é None para usuário {instance.id}")
                
        except Exception as e:
            # 🔥 LOG do erro completo
            logger.error(f"Erro ao calcular score para {instance.id}: {e}", exc_info=True)
        return None
    
    def get_is_complete(self, instance):
        """Verifica se o cadastro está completo"""
        required_fields = ['Nome', 'CPF', 'Nascimento']
        for field in required_fields:
            if not getattr(instance, field, None):
                return False
        
        return self.get_score(instance) is not None
    
    def get_missing_fields(self, instance):
        """Retorna lista de campos obrigatórios faltando"""
        required_fields = ['Nome', 'CPF', 'Nascimento']
        missing = []
        for field in required_fields:
            if not getattr(instance, field, None):
                missing.append(field)
        return missing