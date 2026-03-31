# onboarding/api/v1/relatorio_weasyprint.py

import os
import logging
import math
from datetime import datetime, date
from pathlib import Path
from typing import Any
from weasyprint import HTML
from django.template import Template, Context
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import FuncFormatter, MaxNLocator
from matplotlib.gridspec import GridSpec
import tempfile
import uuid
import shutil

logger = logging.getLogger(__name__)

# ==================== CONSTANTES ====================
TAXA_JUROS_ANUAL = 0.06  # 6% ao ano (rentabilidade real acima da inflação)

# ==================== PALETA DE CORES ====================
COR_AZUL        = "#2c7da0"
COR_VERDE       = "#1e7f6e"
COR_VERMELHO    = "#e05a47"
COR_FUNDO       = "#ffffff"
COR_SUPERFICIE  = "#f7f9fc"
COR_BORDA       = "#e4eaf0"
COR_TEXTO_PRI   = "#0a2540"
COR_TEXTO_SEC   = "#6b7c93"
COR_CARD_AZUL   = "#eaf3fb"
COR_CARD_VERDE  = "#e4f5f1"

# ==================== NOVAS ALOCAÇÕES POR PERFIL ====================
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

def get_alocacao_sugerida(perfil: str) -> list:
    """Retorna a alocação sugerida em formato texto para o template"""
    alocacoes_dict = ALOCACOES_POR_PERFIL.get(perfil, ALOCACOES_POR_PERFIL["Moderado"])
    return [f"{item['nome']}: {item['percentual']}" for item in alocacoes_dict]

def processar_alocacao(alocacao_texto):
    """Processa alocação para facilitar no template"""
    alocacoes = []
    for item in alocacao_texto:
        if ': ' in item:
            nome, percentual = item.split(': ')
            alocacoes.append({
                'nome': nome,
                'percentual': percentual,
            })
    return alocacoes

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
            return float(value)
        return 0.0
    except (ValueError, TypeError, Exception):
        return 0.0

def determinar_perfil_investidor(form_data: dict) -> str:
    """Determina o perfil do investidor baseado nas respostas"""
    horizonte_map = {"HZ_SHORT": "A", "HZ_MEDIUM": "B", "HZ_LONG": "C"}
    risco_map = {"RISK_REDUCE": "A", "RISK_HOLD": "B", "RISK_BUY": "C"}
    preferencia_map = {"PREF_STABLE": "A", "PREF_GROWTH": "B"}

    horizonte  = form_data.get("horizon", "HZ_MEDIUM")
    risco      = form_data.get("risk", "RISK_HOLD")
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

    if capacidade_mensal <= 0:
        invest_frequency = form_data.get("investFrequency", "")
        if invest_frequency == "YES":
            invest_amount  = to_float(form_data.get("investAmount", 0))
            invest_period  = form_data.get("investPeriod", "")
            multiplicador  = {"PER_MONTH": 12, "PER_QUARTER": 4, "PER_SEM": 2, "PER_YEAR": 1}
            capacidade_anual  = invest_amount * multiplicador.get(invest_period, 0)
            capacidade_mensal = capacidade_anual / 12 if capacidade_anual > 0 else 0
            return {'mensal': capacidade_mensal, 'anual': capacidade_anual}

    capacidade_anual = capacidade_mensal * 12
    return {
        'mensal': max(0, capacidade_mensal),
        'anual':  max(0, capacidade_anual),
    }

def gerar_grafico_alocacao_colorido(perfil: str) -> str:
    """Gera gráfico colorido profissional com as novas alocações - VERSÃO COMPACTA"""
    dados = ALOCACOES_POR_PERFIL.get(perfil, ALOCACOES_POR_PERFIL["Moderado"])
    
    labels = [item["nome"] for item in dados]
    valores = [int(item["percentual"].replace("%", "")) for item in dados]
    cores = [item["cor"] for item in dados]

    plt.style.use('default')
    
    # Tamanho reduzido para não ocupar muito espaço
    fig, ax = plt.subplots(figsize=(5, 4))
    fig.patch.set_facecolor('white')
    
    # Ajuste de margens para otimizar espaço
    plt.subplots_adjust(left=0.05, right=0.95, top=0.85, bottom=0.05)

    # Criar o gráfico de pizza com tamanho de fonte menor
    wedges, texts, autotexts = ax.pie(
        valores,
        labels=labels,
        autopct='%1.0f%%',
        startangle=90,
        colors=cores,
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.2},
        textprops={'fontsize': 7},
        pctdistance=0.75,
        labeldistance=1.1,
    )

    # Ajustar os textos percentuais
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontsize(7)
        autotext.set_weight('bold')

    # Ajustar os labels
    for text in texts:
        text.set_fontsize(7)
        text.set_weight('medium')

    # Título menor
    ax.set_title(f'Alocação Sugerida - Perfil {perfil}', fontsize=9, fontweight='bold', pad=8)

    # Remover bordas desnecessárias
    ax.set_frame_on(False)
    
    # Garantir que o círculo seja redondo
    ax.set_aspect('equal')

    # Salvar com qualidade adequada
    img_path = tempfile.mktemp(suffix='.png')
    plt.savefig(img_path, dpi=120, bbox_inches='tight', facecolor='white')
    plt.close()

    return img_path

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
    valor_meta   = to_float(objetivo.get('valor', objetivo.get('value', 0)))
    prazo_meses  = int(objetivo.get('months', 12))
    aporte_nec   = calcular_aporte_mensal_necessario(valor_meta, prazo_meses, taxa_anual)

    if aporte_nec <= capacidade_mensal:
        folga_mensal = capacidade_mensal - aporte_nec
        if aporte_nec > 0 and capacidade_mensal > 0:
            tempo_meses = calcular_tempo_para_meta(valor_meta, capacidade_mensal, taxa_anual)
            if tempo_meses <= prazo_meses:
                return f"Alcançável em {prazo_meses} meses (folga de {formatar_br(folga_mensal)}/mês)"
            return f"Alcançável em {prazo_meses} meses (mas prazo original é {prazo_meses} meses)"
        return f"Alcançável (folga de {formatar_br(folga_mensal)}/mês)"

    gap_mensal = aporte_nec - capacidade_mensal
    return f"Gap de {formatar_br(gap_mensal)}/mês - Recomendamos revisar prazo ou valor"

def recomendar_seguros(form_data: dict, cliente: dict) -> list:
    """Recomenda seguros baseado no perfil do cliente"""
    recs = []
    if form_data.get("lifeInsurance") != "Sim":
        recs.append("Seguro de Vida")
    if form_data.get("disabilityInsurance") != "Sim":
        recs.append("Seguro de Invalidez")
    profissao = cliente.get("profissao", "").lower()
    if any(p in profissao for p in ["empresario", "socio", "empresário", "sócio", "investidor"]):
        recs.append("Seguro Empresarial para Sócios")
    elif any(p in profissao for p in ["executivo", "medico", "advogado", "médico"]):
        recs.append("DIT - Diária de Incapacidade Temporária")
    return recs if recs else ["Nenhum seguro prioritário identificado"]

def recomendar_eficiencia_fiscal(form_data: dict) -> list:
    """Recomenda estratégias de eficiência fiscal"""
    recs = []
    fontes_pgbl = ["Salario", "Salário", "Distribuição de lucro", "Aposentadoria",
                   "SRC_SALARY", "SRC_PROFIT", "SRC_RETIREMENT"]
    renda        = form_data.get("incomeSource", "")
    renda_mensal = to_float(form_data.get("income", 0))
    if renda in fontes_pgbl:
        limite = renda_mensal * 12 * 0.12
        if limite > 0:
            recs.append(f"PGBL - Redução de 12% da base do IRPF (até {formatar_br(limite)}/ano)")
    num_imoveis = int(form_data.get("realEstateCount", 0) or 0)
    if "Aluguel" in renda or num_imoveis >= 5:
        recs.append("Holding Imobiliária - Redução tributária de 27,5% para ~11%")
    return recs if recs else ["Nenhuma oportunidade fiscal identificada no momento"]

def gerar_texto_atendimento(preferencia: str, perfil: str) -> str:
    """Gera texto personalizado para preferência de atendimento"""
    textos = {
        "digital":    f"Cliente prefere atendimento digital e ágil, com comunicação por WhatsApp e reuniões remotas. Perfil {perfil} com potencial para acompanhamento consultivo personalizado.",
        "presencial": f"Cliente prefere atendimento presencial personalizado, com reuniões no escritório ou local de preferência. Perfil {perfil} demanda atenção especial e relacionamento próximo.",
        "hibrido":    f"Cliente prefere atendimento híbrido, combinando encontros presenciais estratégicos com suporte digital contínuo. Modelo ideal para perfil {perfil}.",
    }
    return textos.get(preferencia, f"Cliente prefere atendimento personalizado, alinhado ao perfil {perfil} com foco em relacionamento consultivo de longo prazo.")

def calcular_idade_cliente(cliente: dict) -> int:
    """
    Calcula a idade do cliente baseado na data de nascimento ou ano de nascimento.
    
    Args:
        cliente: Dicionário com dados do cliente
    
    Returns:
        int: Idade calculada ou None se não for possível calcular
    """
    try:
        # Tenta obter data de nascimento completa
        if 'data_nascimento' in cliente and cliente['data_nascimento']:
            data_nasc = cliente['data_nascimento']
            
            # Converte string para date se necessário
            if isinstance(data_nasc, str):
                # Tenta diferentes formatos de data
                formatos = ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y']
                for fmt in formatos:
                    try:
                        data_nasc = datetime.strptime(data_nasc, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    # Se nenhum formato funcionar, tenta extrair apenas o ano
                    if len(data_nasc) >= 4:
                        ano = int(data_nasc[:4])
                        hoje = date.today()
                        return hoje.year - ano
                    return None
            
            # Se for datetime, converte para date
            elif isinstance(data_nasc, datetime):
                data_nasc = data_nasc.date()
            
            # Se for date, usa diretamente
            elif isinstance(data_nasc, date):
                pass
            else:
                return None
            
            # Calcula idade com data completa
            hoje = date.today()
            idade = hoje.year - data_nasc.year
            
            # Ajusta se ainda não fez aniversário este ano
            if (hoje.month, hoje.day) < (data_nasc.month, data_nasc.day):
                idade -= 1
            
            return idade
        
        # Se não tem data de nascimento, tenta usar apenas o ano
        elif 'ano_nascimento' in cliente and cliente['ano_nascimento']:
            ano_nasc = int(cliente['ano_nascimento'])
            hoje = date.today()
            return hoje.year - ano_nasc
        
        # Se tem idade diretamente no dicionário
        elif 'idade' in cliente and cliente['idade']:
            if isinstance(cliente['idade'], (int, float)):
                return int(cliente['idade'])
            elif isinstance(cliente['idade'], str) and cliente['idade'].isdigit():
                return int(cliente['idade'])
        
        return None
        
    except Exception as e:
        logger.error(f"Erro ao calcular idade: {e}")
        return None

# ==================== HELPER INTERNO DO GRÁFICO ====================

def _desenhar_card(ax, x, y, w, h, titulo, valor_str, cor_fundo, cor_titulo, cor_valor):
    """Desenha um mini card de métrica sobre o gráfico (coordenadas em ax.transAxes)."""
    fancy = mpatches.FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.01",
        facecolor=cor_fundo,
        edgecolor=COR_BORDA,
        linewidth=0.8,
        transform=ax.transAxes,
        clip_on=False,
        zorder=3,
    )
    ax.add_patch(fancy)
    ax.text(
        x + w / 2, y + h * 0.68, titulo,
        transform=ax.transAxes,
        ha="center", va="center",
        fontsize=6.5, color=cor_titulo,
    )
    ax.text(
        x + w / 2, y + h * 0.28, valor_str,
        transform=ax.transAxes,
        ha="center", va="center",
        fontsize=9, color=cor_valor, fontweight="bold",
    )


# ==================== GRÁFICO DE EVOLUÇÃO ====================

def gerar_grafico_evolucao_objetivo(
    objetivo: dict,
    capacidade_mensal: float,
    objetivo_index: int,
    pasta_temp: str,
) -> str:
    """
    Gera gráfico de evolução patrimonial para um objetivo financeiro.
    Versão minimalista e elegante - sem grades, apenas números e curvas.
    """
    try:
        nome_objetivo = objetivo.get('name', objetivo.get('nome', f'Objetivo_{objetivo_index}'))
        valor_meta    = to_float(objetivo.get('valor', objetivo.get('value', 0)))
        prazo_meses   = int(objetivo.get('months', 12))

        print(f"📊 Gerando gráfico {objetivo_index}: {nome_objetivo}")

        if valor_meta <= 0:
            print("   ⚠️  Valor meta = 0, ignorando")
            return None

        taxa_mensal = (1 + TAXA_JUROS_ANUAL) ** (1 / 12) - 1
        aporte_nec  = calcular_aporte_mensal_necessario(valor_meta, prazo_meses)
        meses       = list(range(1, prazo_meses + 1))

        # Série necessária
        patrimonio_nec, acc = [], 0.0
        for _ in range(prazo_meses):
            acc = acc * (1 + taxa_mensal) + aporte_nec
            patrimonio_nec.append(acc)

        # Série real
        if capacidade_mensal > 0:
            patrimonio_real, acc = [], 0.0
            for _ in range(prazo_meses):
                acc = acc * (1 + taxa_mensal) + capacidade_mensal
                patrimonio_real.append(acc)
            meses_para_meta = calcular_tempo_para_meta(valor_meta, capacidade_mensal)
        else:
            patrimonio_real = patrimonio_nec.copy()
            meses_para_meta = prazo_meses

        # ── Layout minimalista e elegante ──────────────────────────────────────
        plt.rcParams.update({
            "font.family": "DejaVu Sans",
            "font.size": 9,
        })

        # Figura com fundo branco puro
        fig, ax = plt.subplots(figsize=(8, 3.2), facecolor='white')
        ax.set_facecolor('white')

        # ==================== REMOVE TODAS AS LINHAS ====================
        # Remove todas as bordas
        for spine in ['top', 'right', 'left', 'bottom']:
            ax.spines[spine].set_visible(False)
        
        # Remove grades completamente
        ax.grid(False)
        
        # Remove ticks e suas linhas
        ax.tick_params(axis='both', which='both', length=0)
        
        # ==================== LINHA DA META (horizontal) ====================
        # Cor suave que combina com a paleta clara
        ax.axhline(y=valor_meta, color='#c26858', linestyle='--', 
                   linewidth=1.2, alpha=0.7, zorder=2)
        
        # Texto da meta com cor combinando
        ax.text(prazo_meses * 0.98, valor_meta * 1.02,
                formatar_br(valor_meta), fontsize=8, 
                color='#c26858', ha="right", va="bottom", alpha=0.9)

        # ==================== CURVA NECESSÁRIA ====================
        ax.plot(meses, patrimonio_nec,
                color='#4a6f8f', linewidth=2.2,
                solid_capstyle="round", zorder=3,
                label=f'Aporte necessário ({formatar_br(round(aporte_nec))}/mês)')

        # ==================== CURVA REAL ====================
        if capacidade_mensal > 0:
            ax.plot(meses, patrimonio_real,
                    color='#3b7b6e', linewidth=2.2,
                    linestyle='-', zorder=3,
                    label=f'Seu aporte ({formatar_br(capacidade_mensal)}/mês)')

        # ==================== PONTO DE ATINGIMENTO ====================
        if capacidade_mensal > 0 and meses_para_meta <= prazo_meses:
            acc = 0.0
            for _ in range(meses_para_meta):
                acc = acc * (1 + taxa_mensal) + capacidade_mensal
            pat_ponto = acc

            ax.scatter(meses_para_meta, pat_ponto, s=70, 
                      color='#3b7b6e', edgecolors='white', 
                      linewidth=1.8, zorder=5, alpha=0.9)
            
            ax.annotate(f'{meses_para_meta} meses',
                       xy=(meses_para_meta, pat_ponto),
                       xytext=(meses_para_meta + prazo_meses*0.03, pat_ponto * 0.92),
                       fontsize=7, fontweight='medium', 
                       color='#3b7b6e', ha='left')

        # ==================== FORMATAÇÃO DOS NÚMEROS ====================
        def fmt_y(valor, _):
            if valor == 0:          return "R$ 0"
            if valor >= 1_000_000:  return f"R$ {valor/1_000_000:.1f}M"
            if valor >= 1_000:      return f"R$ {valor/1_000:.0f}K"
            return f"R$ {valor:.0f}"

        from matplotlib.ticker import FuncFormatter, MaxNLocator
        
        # Apenas os números, sem linhas
        ax.yaxis.set_major_formatter(FuncFormatter(fmt_y))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))

        # Cores dos números - suaves e elegantes
        ax.tick_params(axis="both", labelsize=8, colors='#9aa6b5')
        
        # Rótulo do eixo X - discreto
        ax.set_xlabel("Meses", fontsize=8, color='#9aa6b5', labelpad=6, alpha=0.8)

        # Limites dos eixos
        max_val = max(max(patrimonio_nec), max(patrimonio_real), valor_meta)
        ax.set_xlim(1, prazo_meses)
        ax.set_ylim(0, max_val * 1.12)

        # ==================== LEGENDA ELEGANTE ====================
        handles = ax.get_legend_handles_labels()[0]
        if handles:
            ax.legend(
            handles=handles,
            loc='lower right',
            fontsize=7,
            frameon=False,
            handlelength=1.5,
            labelspacing=0.3
        )

        # Ajuste final das margens
        plt.subplots_adjust(left=0.1, right=0.95, top=0.92, bottom=0.12)

        # ==================== SALVAR ====================
        nome_arquivo = f"objetivo_{objetivo_index}_{uuid.uuid4().hex[:8]}.png"
        img_path = os.path.join(pasta_temp, nome_arquivo)
        plt.savefig(img_path, dpi=140, facecolor='white', bbox_inches='tight')
        plt.close(fig)

        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            print(f"   ✅ Gráfico salvo: {img_path}")
            return img_path

        print("   ❌ Arquivo não foi criado ou está vazio")
        return None

    except Exception as e:
        print(f"   ❌ Erro ao gerar gráfico {objetivo_index}: {e}")
        import traceback
        traceback.print_exc()
        return None
    
# ==================== FUNÇÃO PRINCIPAL ====================

def calcular_idade_cliente(cliente: dict) -> int:
    """
    Calcula a idade do cliente baseado na data de nascimento ou ano de nascimento.
    
    Args:
        cliente: Dicionário com dados do cliente
    
    Returns:
        int: Idade calculada ou None se não for possível calcular
    """
    from datetime import date, datetime
    
    try:
        # ==================== VERIFICA CAMPOS ====================
        
        # 1. Tenta obter data de nascimento completa
        if 'data_nascimento' in cliente and cliente['data_nascimento']:
            data_nasc = cliente['data_nascimento']
            
            # Converte string para date se necessário
            if isinstance(data_nasc, str):
                # Tenta diferentes formatos de data
                formatos = ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y']
                for fmt in formatos:
                    try:
                        data_nasc = datetime.strptime(data_nasc, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    # Se nenhum formato funcionar, tenta extrair apenas o ano
                    if len(data_nasc) >= 4:
                        ano = int(data_nasc[:4])
                        hoje = date.today()
                        return hoje.year - ano
                    return None
            
            # Se for datetime, converte para date
            elif isinstance(data_nasc, datetime):
                data_nasc = data_nasc.date()
            
            # Se for date, usa diretamente
            elif isinstance(data_nasc, date):
                pass
            else:
                return None
            
            # Calcula idade com data completa
            hoje = date.today()
            idade = hoje.year - data_nasc.year
            
            # Ajusta se ainda não fez aniversário este ano
            if (hoje.month, hoje.day) < (data_nasc.month, data_nasc.day):
                idade -= 1
            
            return idade
        
        # 2. Tenta usar o campo 'ano_nascimento'
        elif 'ano_nascimento' in cliente and cliente['ano_nascimento']:
            try:
                ano_nasc = int(cliente['ano_nascimento'])
                hoje = date.today()
                return hoje.year - ano_nasc
            except (ValueError, TypeError):
                pass
        
        # 3. Tenta usar o campo 'idade' (pode ser ano de nascimento ou idade real)
        elif 'idade' in cliente and cliente['idade']:
            valor = cliente['idade']
            
            # Tenta converter para número
            try:
                num = int(valor)
                
                # Se for um número entre 1900 e 2026, provavelmente é ANO DE NASCIMENTO
                if 1900 <= num <= 2026:
                    hoje = date.today()
                    idade = hoje.year - num
                    # Verifica se a idade é plausível (0 a 120 anos)
                    if 0 <= idade <= 120:
                        return idade
                    else:
                        return None
                
                # Se for um número entre 0 e 120, provavelmente já é IDADE
                elif 0 <= num <= 120:
                    return num
                
                # Outros valores
                else:
                    return None
                    
            except (ValueError, TypeError):
                # Se não for número, retorna como está
                return None
        
        return None
        
    except Exception as e:
        logger.error(f"Erro ao calcular idade: {e}")
        return None


def gerar_relatorio_pdf_weasyprint(cliente: dict, form_data: dict, output_path: str = None) -> str:
    """Gera relatório PDF usando weasyprint"""
    temp_dir = tempfile.mkdtemp(prefix='relatorio_')
    graficos_gerados = []
    
    # ==================== CALCULAR IDADE DO CLIENTE ====================
    # Cria uma cópia do cliente para não modificar o original
    cliente_com_idade = cliente.copy()
    
    # Tenta calcular a idade
    idade_calculada = calcular_idade_cliente(cliente_com_idade)
    
    # Log para debug
    logger.info(f"Valor original do campo idade: {cliente_com_idade.get('idade')}")
    logger.info(f"Idade calculada: {idade_calculada}")
    
    # Atualiza o campo idade
    if idade_calculada is not None:
        cliente_com_idade['idade'] = idade_calculada
    else:
        # Se não conseguiu calcular, mantém o valor original ou coloca 'Não informada'
        if 'idade' not in cliente_com_idade or not cliente_com_idade['idade']:
            cliente_com_idade['idade'] = 'Não informada'
        else:
            # Se o valor original for um ano de nascimento, converte
            try:
                valor_original = int(cliente_com_idade['idade'])
                if 1900 <= valor_original <= 2026:
                    from datetime import date
                    hoje = date.today()
                    idade = hoje.year - valor_original
                    if 0 <= idade <= 120:
                        cliente_com_idade['idade'] = idade
                    else:
                        cliente_com_idade['idade'] = 'Não informada'
            except:
                cliente_com_idade['idade'] = 'Não informada'
        
        logger.warning(f"Não foi possível calcular a idade para o cliente: {cliente.get('nome', 'Desconhecido')}")
    
    # Log final
    logger.info(f"Idade final para o cliente {cliente_com_idade.get('nome')}: {cliente_com_idade.get('idade')}")
    
    # ==================== CONTINUA COM O RESTO DO CÓDIGO ====================
    
    try:
        perfil     = determinar_perfil_investidor(form_data)
        capacidade = calcular_capacidade_poupanca(form_data)
        patrimonio = to_float(form_data.get("financialAssets", 0)) + to_float(form_data.get("realEstateValue", 0))

        # Gráfico de alocação
        grafico_alocacao = None
        try:
            grafico_alocacao = gerar_grafico_alocacao_colorido(perfil)
            if grafico_alocacao:
                grafico_alocacao = os.path.abspath(grafico_alocacao)
        except Exception as e:
            logger.error(f"Erro no gráfico de alocação: {e}")

        # Gráficos individuais de objetivos
        objetivos_raw = form_data.get("financialGoals", [])

        for idx, obj in enumerate(objetivos_raw):
            try:
                nome  = obj.get("name") or obj.get("nome", f"Objetivo {idx+1}")
                valor = to_float(obj.get("valor", obj.get("value", 0)))
                if valor > 0:
                    grafico_path = gerar_grafico_evolucao_objetivo(
                        obj, capacidade['mensal'], idx, temp_dir
                    )
                    if grafico_path:
                        graficos_gerados.append({'idx': idx, 'nome': nome, 'path': grafico_path})
            except Exception as e:
                logger.error(f"Erro ao gerar gráfico {idx}: {e}")

        # Montar lista de objetivos para o template
        objetivos = []
        for idx, obj in enumerate(objetivos_raw):
            desc        = obj.get("name") or obj.get("nome", "Não informado")
            valor       = to_float(obj.get("valor", obj.get("value", 0)))
            prazo_meses = obj.get("months", 12)
            prazo_meses = int(float(prazo_meses)) if isinstance(prazo_meses, str) else int(prazo_meses)

            aporte_mensal_necessario = calcular_aporte_mensal_necessario(valor, prazo_meses)
            aporte_anual_necessario  = aporte_mensal_necessario * 12
            gap        = calcular_gap(obj, capacidade['mensal'])
            tempo_real = calcular_tempo_para_meta(valor, capacidade['mensal'])

            grafico_objetivo = next(
                (g['path'] for g in graficos_gerados if g['idx'] == idx), None
            )
            if grafico_objetivo:
                grafico_objetivo = os.path.abspath(grafico_objetivo)

            objetivos.append({
                'desc':                      desc,
                'valor':                     formatar_br(valor),
                'prazo_meses':               f"{prazo_meses} meses",
                'aporte_mensal_necessario':  f"{formatar_br(aporte_mensal_necessario)}/mês",
                'aporte_anual_necessario':   f"{formatar_br(aporte_anual_necessario)}/ano",
                'capacidade_mensal':         f"{formatar_br(capacidade['mensal'])}/mês",
                'tempo_real':                f"{tempo_real} meses",
                'gap':                       gap,
                'grafico_path':              grafico_objetivo,
            })

        # Copiar gráficos para pasta permanente
        pasta_permanente = Path("media/graficos_temp")
        pasta_permanente.mkdir(parents=True, exist_ok=True)

        for idx, obj in enumerate(objetivos):
            if obj['grafico_path'] and os.path.exists(obj['grafico_path']):
                nome_arquivo = f"grafico_{idx}_{uuid.uuid4().hex[:8]}.png"
                novo_caminho = pasta_permanente / nome_arquivo
                shutil.copy2(obj['grafico_path'], novo_caminho)
                obj['grafico_path'] = str(novo_caminho.absolute())

        if grafico_alocacao and os.path.exists(grafico_alocacao):
            nome_arquivo_aloc         = f"alocacao_{uuid.uuid4().hex[:8]}.png"
            caminho_aloc_permanente   = pasta_permanente / nome_arquivo_aloc
            shutil.copy2(grafico_alocacao, caminho_aloc_permanente)
            grafico_alocacao = str(caminho_aloc_permanente.absolute())

        seguros          = recomendar_seguros(form_data, cliente_com_idade)
        eficiencias      = recomendar_eficiencia_fiscal(form_data)
        seguro_vida      = patrimonio * 0.2
        texto_atendimento = gerar_texto_atendimento(
            form_data.get("atendimento_preferencia", "padronizado"), perfil
        )

        estado_civil       = cliente_com_idade.get("estado_civil", "")
        tem_filhos         = cliente_com_idade.get("tem_filhos", False)
        necessidade_sucessao = (
            estado_civil in ["Casado", "União Estável", "CASADO", "UNIAO_ESTAVEL"] or tem_filhos
        ) and form_data.get("succession") != "Sim"

        template_path = Path(__file__).parent.parent.parent / "templates" / "relatorio.html"
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        template     = Template(template_content)
        html_content = template.render(Context({
            'cliente':            cliente_com_idade,
            'perfil':             perfil,
            'capacidade_mensal':  formatar_br(capacidade['mensal']),
            'capacidade_anual':   formatar_br(capacidade['anual']),
            'renda_mensal':       formatar_br(to_float(form_data.get("income", 0))),
            'custo_mensal':       formatar_br(to_float(form_data.get("monthlyExpenses", 0))),
            'patrimonio':         formatar_br(patrimonio),
            'alocacao_texto':     get_alocacao_sugerida(perfil),
            'alocacoes':          processar_alocacao(get_alocacao_sugerida(perfil)),
            'grafico_path':       grafico_alocacao if grafico_alocacao else '',
            'objetivos':          objetivos,
            'seguros':            seguros,
            'eficiencias':        eficiencias,
            'seguro_vida':        formatar_br(seguro_vida),
            'necessidade_sucessao': necessidade_sucessao,
            'texto_atendimento':  texto_atendimento,
            'taxa_juros':         f"{TAXA_JUROS_ANUAL * 100:.0f}%",
        }))

        if output_path is None:
            os.makedirs("media/relatorios", exist_ok=True)
            nome_cliente = cliente_com_idade.get('nome', 'cliente').replace(' ', '_')
            timestamp    = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path  = f"media/relatorios/relatorio_{nome_cliente}_{timestamp}.pdf"

        HTML(string=html_content, base_url='.').write_pdf(output_path)
        return output_path

    except Exception as e:
        logger.error(f"Erro ao gerar relatório: {e}", exc_info=True)
        raise RuntimeError(f"Falha na geração do relatório: {str(e)}")

    finally:
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception:
            pass