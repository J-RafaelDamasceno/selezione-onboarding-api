# onboarding/api/v1/calculos_relatorio.py

import logging
import math
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# ==================== CONSTANTES ====================
TAXA_JUROS_ANUAL = 0.06  # 6% ao ano (rentabilidade real acima da inflação)

# ==================== ALOCAÇÕES POR PERFIL ====================
ALOCACOES_POR_PERFIL = {
    "Ultraconservador": [
        {"nome": "Pós-Fixado", "percentual": "75%", "cor": "#2E86AB"},
        {"nome": "Inflação", "percentual": "15%", "cor": "#117A65"},
        {"nome": "Prefixado", "percentual": "10%", "cor": "#F39C12"},
    ],
    "Conservador": [
        {"nome": "Pós-Fixado", "percentual": "40%", "cor": "#2E86AB"},
        {"nome": "Inflação", "percentual": "20%", "cor": "#117A65"},
        {"nome": "Prefixado", "percentual": "30%", "cor": "#F39C12"},
        {"nome": "RV Local", "percentual": "5%", "cor": "#E74C3C"},
        {"nome": "Internacional", "percentual": "5%", "cor": "#8E44AD"},
    ],
    "Moderado": [
        {"nome": "Pós-Fixado", "percentual": "15%", "cor": "#2E86AB"},
        {"nome": "Inflação", "percentual": "25%", "cor": "#117A65"},
        {"nome": "Prefixado", "percentual": "25%", "cor": "#F39C12"},
        {"nome": "RV Local", "percentual": "15%", "cor": "#E74C3C"},
        {"nome": "Internacional", "percentual": "15%", "cor": "#8E44AD"},
        {"nome": "Alternativo", "percentual": "5%", "cor": "#9B59B6"},
    ],
    "Agressivo": [
        {"nome": "Pós-Fixado", "percentual": "15%", "cor": "#2E86AB"},
        {"nome": "Inflação", "percentual": "20%", "cor": "#117A65"},
        {"nome": "Prefixado", "percentual": "20%", "cor": "#F39C12"},
        {"nome": "RV Local", "percentual": "20%", "cor": "#E74C3C"},
        {"nome": "Internacional", "percentual": "20%", "cor": "#8E44AD"},
        {"nome": "Alternativo", "percentual": "5%", "cor": "#9B59B6"},
    ],
}


def formatar_br(valor: float) -> str:
    """Formata valor para padrão brasileiro (R$ 1.234,56)"""
    if valor is None or valor == 0:
        return "R$ 0,00"
    inteiro = int(abs(valor))
    decimal = int(round((abs(valor) - inteiro) * 100))
    inteiro_str = f"{inteiro:,}".replace(",", ".")
    decimal_str = f"{decimal:02d}"
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {inteiro_str},{decimal_str}"


def to_float(value: Any) -> float:
    """Converte valor para float de forma segura"""
    try:
        if value is None or value == "":
            return 0.0
        if hasattr(value, '__class__') and value.__class__.__name__ == 'Decimal':
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            value = value.strip().replace('R$', '').strip()
            value = value.replace('.', '').replace(',', '.')
            return float(value) if value else 0.0
        return 0.0
    except (ValueError, TypeError, Exception):
        return 0.0


def determinar_perfil_investidor(form_data: dict) -> str:
    """Determina o perfil do investidor baseado nas respostas"""
    horizonte_map = {"HZ_SHORT": "A", "HZ_MEDIUM": "B", "HZ_LONG": "C"}
    risco_map = {"RISK_REDUCE": "A", "RISK_HOLD": "B", "RISK_BUY": "C"}
    preferencia_map = {"PREF_STABLE": "A", "PREF_GROWTH": "B"}

    horizonte = form_data.get("horizon", "HZ_MEDIUM")
    risco = form_data.get("risk", "RISK_HOLD")
    preferencia = form_data.get("preference", "PREF_STABLE")

    letra_h = horizonte_map.get(horizonte, "B")
    letra_r = risco_map.get(risco, "B")
    letra_p = preferencia_map.get(preferencia, "A")

    combinacao = f"{letra_h}+{letra_r}+{letra_p}"

    perfis = {
        "A+A+A": "Ultraconservador", "A+A+B": "Conservador", "A+B+A": "Conservador",
        "A+B+B": "Moderado", "B+A+A": "Moderado", "B+B+A": "Moderado",
        "B+A+B": "Moderado", "C+A+A": "Moderado", "C+B+A": "Moderado",
        "C+A+B": "Moderado", "A+C+A": "Moderado", "A+C+B": "Agressivo",
        "B+B+B": "Agressivo", "B+C+A": "Agressivo", "B+C+B": "Agressivo",
        "C+B+B": "Agressivo", "C+C+A": "Agressivo", "C+C+B": "Agressivo",
    }

    return perfis.get(combinacao, "Moderado")


def calcular_capacidade_poupanca(form_data: dict) -> dict:
    """Calcula a capacidade de poupança mensal e anual do cliente"""
    renda_mensal = to_float(form_data.get("income", 0))
    custo_mensal = to_float(form_data.get("monthlyExpenses", 0))
    capacidade_mensal = renda_mensal - custo_mensal

    # Se capacidade for negativa ou zero, tenta usar investimento declarado
    if capacidade_mensal <= 0:
        invest_frequency = form_data.get("investFrequency", "")
        if invest_frequency == "YES":
            invest_amount = to_float(form_data.get("investAmount", 0))
            invest_period = form_data.get("investPeriod", "")
            multiplicador = {"PER_MONTH": 12, "PER_QUARTER": 4, "PER_SEM": 2, "PER_YEAR": 1}
            capacidade_anual = invest_amount * multiplicador.get(invest_period, 0)
            capacidade_mensal = capacidade_anual / 12 if capacidade_anual > 0 else 0
            return {'mensal': max(0, capacidade_mensal), 'anual': max(0, capacidade_anual)}

    capacidade_anual = capacidade_mensal * 12
    return {
        'mensal': max(0, capacidade_mensal),
        'anual': max(0, capacidade_anual),
    }


def calcular_aporte_mensal_necessario(valor_meta: float, prazo_meses: int, taxa_anual: float = TAXA_JUROS_ANUAL) -> float:
    """Calcula o aporte mensal necessário para atingir um objetivo considerando juros compostos."""
    if prazo_meses <= 0 or valor_meta <= 0:
        return 0.0
    taxa_mensal = (1 + taxa_anual) ** (1 / 12) - 1
    if taxa_mensal > 0:
        return valor_meta * taxa_mensal / ((1 + taxa_mensal) ** prazo_meses - 1)
    return valor_meta / prazo_meses


def calcular_tempo_para_meta(valor_meta: float, aporte_mensal: float, taxa_anual: float = TAXA_JUROS_ANUAL) -> int:
    """Calcula quantos meses são necessários para atingir a meta com um aporte mensal fixo."""
    if aporte_mensal <= 0 or valor_meta <= 0:
        return 999
    taxa_mensal = (1 + taxa_anual) ** (1 / 12) - 1
    if taxa_mensal > 0:
        n = math.log((valor_meta * taxa_mensal / aporte_mensal) + 1) / math.log(1 + taxa_mensal)
        return int(math.ceil(n))
    return int(math.ceil(valor_meta / aporte_mensal))


def calcular_gap(objetivo: dict, capacidade_mensal: float, taxa_anual: float = TAXA_JUROS_ANUAL) -> str:
    """Calcula o gap entre necessidade e capacidade de poupança com juros compostos"""
    valor_meta = to_float(objetivo.get('valor', objetivo.get('value', 0)))
    prazo_meses = int(objetivo.get('months', 12))
    
    if valor_meta <= 0:
        return "Valor do objetivo não informado"
    
    aporte_nec = calcular_aporte_mensal_necessario(valor_meta, prazo_meses, taxa_anual)

    if capacidade_mensal <= 0:
        return f"Sem capacidade de poupança. Aporte necessário: {formatar_br(aporte_nec)}/mês"

    if aporte_nec <= capacidade_mensal:
        folga_mensal = capacidade_mensal - aporte_nec
        if aporte_nec > 0 and capacidade_mensal > 0:
            tempo_meses = calcular_tempo_para_meta(valor_meta, capacidade_mensal, taxa_anual)
            if tempo_meses <= prazo_meses:
                return f"Alcançável em {tempo_meses} meses (folga de {formatar_br(folga_mensal)}/mês)"
            return f"Alcançável em {tempo_meses} meses (prazo original: {prazo_meses} meses)"
        return f"Alcançável (folga de {formatar_br(folga_mensal)}/mês)"

    gap_mensal = aporte_nec - capacidade_mensal
    return f"Gap de {formatar_br(gap_mensal)}/mês - Recomendamos revisar prazo ou valor"


def recomendar_seguros(form_data: dict, cliente: dict) -> list:
    """Recomenda seguros baseado no perfil do cliente"""
    recs = []
    
    # Seguros que ele NÃO possui (oportunidades)
    life_insurance = form_data.get("lifeInsurance", "")
    disability_insurance = form_data.get("disabilityInsurance", "")
    
    if life_insurance != "Sim" and life_insurance != "YES":
        recs.append("Seguro de Vida")
    if disability_insurance != "Sim" and disability_insurance != "YES":
        recs.append("Seguro de Invalidez")
    
    # Seguro baseado na profissão
    profissao = cliente.get("profissao", "").lower()
    if any(p in profissao for p in ["empresario", "socio", "empresário", "sócio", "investidor"]):
        recs.append("Seguro Empresarial para Sócios")
    elif any(p in profissao for p in ["executivo", "medico", "advogado", "médico", "engenheiro", "arquiteto"]):
        recs.append("DIT - Diária de Incapacidade Temporária")
    
    return recs if recs else ["Nenhum seguro prioritário identificado"]


def recomendar_eficiencia_fiscal(form_data: dict) -> dict:
    """Recomenda estratégias de eficiência fiscal com motivo"""
    recomendacoes = []
    motivo = ""
    
    fontes_pgbl = ["Salario", "Salário", "Distribuição de lucro", "Aposentadoria",
                   "SRC_SALARY", "SRC_PROFIT", "SRC_RETIREMENT", "salario", "salário"]
    renda = form_data.get("incomeSource", "")
    renda_mensal = to_float(form_data.get("income", 0))
    
    if renda in fontes_pgbl:
        limite = renda_mensal * 12 * 0.12
        if limite > 0:
            recomendacoes.append(f"PGBL - Redução de 12% da base do IRPF (até {formatar_br(limite)}/ano)")
            motivo = "Sua renda é proveniente de pró-labore/salário, o que permite dedução fiscal via PGBL"
    
    num_imoveis = int(form_data.get("realEstateCount", 0) or 0)
    if "Aluguel" in renda or num_imoveis >= 5:
        recomendacoes.append("Holding Imobiliária - Redução tributária de 27,5% para ~11%")
        motivo = "Você possui renda de aluguel ou mais de 5 imóveis, ideal para estruturação via holding"
    
    if not recomendacoes:
        recomendacoes = ["Nenhuma oportunidade fiscal identificada no momento"]
        motivo = "Com base na sua fonte de renda atual, não identificamos oportunidades fiscais imediatas"
    
    return {
        "recomendacoes": recomendacoes,
        "motivo": motivo
    }


def gerar_texto_atendimento(preferencia: str, perfil: str) -> str:
    """Gera texto personalizado para preferência de atendimento"""
    textos = {
        "digital": f"Cliente prefere atendimento digital e ágil, com comunicação por WhatsApp e reuniões remotas. Perfil {perfil} com potencial para acompanhamento consultivo personalizado.",
        "presencial": f"Cliente prefere atendimento presencial personalizado, com reuniões no escritório ou local de preferência. Perfil {perfil} demanda atenção especial e relacionamento próximo.",
        "hibrido": f"Cliente prefere atendimento híbrido, combinando encontros presenciais estratégicos com suporte digital contínuo. Modelo ideal para perfil {perfil}.",
    }
    return textos.get(preferencia, f"Cliente prefere atendimento personalizado, alinhado ao perfil {perfil} com foco em relacionamento consultivo de longo prazo.")