# onboarding/api/v1/relatorio.py

import matplotlib
matplotlib.use('Agg')

from fpdf import FPDF
from datetime import datetime
import os
import matplotlib.pyplot as plt
import tempfile
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
import logging
from functools import lru_cache
import hashlib
import shutil
from pathlib import Path

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes para cache
CACHE_DIR = Path("media/graficos_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache em memória para evitar recriação de gráficos
_graph_cache = {}


class RelatorioClientePDF(FPDF):
    """Classe base para geração de relatório PDF com estilo profissional"""
    
    def __init__(self, cliente_data: dict):
        super().__init__()
        self.cliente = cliente_data
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=15, top=10, right=15)
        
    def header(self):
        """Cabeçalho profissional do relatório"""
        self.set_font('Arial', 'B', 9)
        self.set_text_color(80, 80, 80)
        self.cell(0, 4, 'SELEZIONE INVESTIMENTOS', 0, 1, 'C')
        
        self.set_font('Arial', 'B', 16)
        self.set_text_color(0, 0, 0)
        self.cell(0, 8, 'RELATÓRIO DE ONBOARDING', 0, 1, 'C')
        
        self.set_font('Arial', 'I', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, 'Documento confidencial - Análise completa do perfil financeiro', 0, 1, 'C')

    def footer(self):
        """Rodapé minimalista"""
        self.set_y(-15)
        self.set_font('Arial', 'I', 7)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, f'Página {self.page_no()}', 0, 0, 'C')
    
    def adicionar_secao(self, titulo: str):
        self.ln(5)
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, titulo, 0, 1)
        self.set_draw_color(200, 200, 200)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(4)
        self.set_font('Arial', '', 10)
    
    def adicionar_campo(self, label: str, valor: str):
        self.set_font('Arial', 'B', 10)
        largura_label = self.get_string_width(f'{label}:') + 2
        self.cell(largura_label, 6, f'{label}:', 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 6, valor, 0, 1)

    def adicionar_lista(self, items: list):
        for item in items:
            self.set_x(15)
            self.cell(0, 5, f'- {item}', 0, 1)


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


def calcular_capacidade_poupanca_anual(form_data: dict) -> float:
    """Calcula a capacidade de poupança anual do cliente"""
    invest_frequency = form_data.get("investFrequency", "")
    
    if invest_frequency != "YES":
        return 0.0
    
    invest_amount = to_float(form_data.get("investAmount", 0))
    invest_period = form_data.get("investPeriod", "")
    
    multiplicador = {"PER_MONTH": 12, "PER_QUARTER": 4, "PER_SEM": 2, "PER_YEAR": 1}
    resultado = invest_amount * multiplicador.get(invest_period, 0)
    
    return resultado


def get_alocacao_sugerida(perfil: str) -> list:
    """Retorna a alocação sugerida em formato texto"""
    alocacoes = {
        "Ultraconservador": ["Renda Fixa Pós-fixada: 50%", "Renda Fixa IPCA+: 35%", "Renda Fixa Pré-fixada: 15%"],
        "Conservador": ["Renda Fixa Pós-fixada: 40%", "Renda Fixa IPCA+: 30%", "Renda Fixa Pré-fixada: 20%", "Multimercados: 10%"],
        "Moderado": ["Renda Fixa Pós-fixada: 30%", "Renda Fixa IPCA+: 25%", "Renda Fixa Pré-fixada: 15%", "Multimercados: 15%", "Ações: 15%"],
        "Agressivo": ["Renda Fixa Pós-fixada: 15%", "Renda Fixa IPCA+: 15%", "Renda Fixa Pré-fixada: 10%", "Multimercados: 25%", "Ações: 35%"],
    }
    return alocacoes.get(perfil, alocacoes["Moderado"])


class GeradorGraficoCache:
    """Gerencia cache de gráficos para melhor performance"""
    
    @staticmethod
    def _get_cache_key(perfil: str) -> str:
        """Gera chave única para o cache"""
        return f"grafico_alocacao_{perfil}"
    
    @staticmethod
    def _get_cache_path(perfil: str) -> Path:
        """Retorna caminho do arquivo de cache"""
        return CACHE_DIR / f"alocacao_{perfil.lower()}.png"
    
    @classmethod
    def obter_grafico(cls, perfil: str, force_regen: bool = False) -> Optional[str]:
        """Obtém gráfico do cache ou gera novo"""
        cache_key = cls._get_cache_key(perfil)
        cache_path = cls._get_cache_path(perfil)
        
        # Verificar cache em memória
        if not force_regen and cache_key in _graph_cache:
            cached_path = _graph_cache[cache_key]
            if os.path.exists(cached_path):
                logger.info(f"Usando gráfico em cache (memória) para perfil {perfil}")
                return cached_path
        
        # Verificar cache em disco
        if not force_regen and cache_path.exists():
            logger.info(f"Usando gráfico em cache (disco) para perfil {perfil}")
            _graph_cache[cache_key] = str(cache_path)
            return str(cache_path)
        
        return None
    
    @classmethod
    def salvar_grafico(cls, perfil: str, img_path: str) -> str:
        """Salva gráfico no cache"""
        cache_key = cls._get_cache_key(perfil)
        cache_path = cls._get_cache_path(perfil)
        
        # Copiar para cache permanente
        shutil.copy2(img_path, cache_path)
        
        # Atualizar cache em memória
        _graph_cache[cache_key] = str(cache_path)
        
        # Remover arquivo temporário
        try:
            os.remove(img_path)
        except:
            pass
        
        logger.info(f"Gráfico salvo em cache para perfil {perfil}")
        return str(cache_path)


def gerar_grafico_alocacao_colorido(perfil: str, use_cache: bool = True) -> str:
    """
    Gera gráfico colorido profissional de alocação com sistema de cache.
    
    Args:
        perfil: Perfil do investidor
        use_cache: Se deve usar cache (True = mais rápido)
    
    Returns:
        Caminho da imagem do gráfico
    """
    
    # Tentar obter do cache primeiro
    if use_cache:
        cached_img = GeradorGraficoCache.obter_grafico(perfil)
        if cached_img:
            return cached_img
    
    # Configurações de alocação por perfil
    alocacoes = {
        "Ultraconservador": {
            "labels": ["CDI/Selic", "IPCA+", "Pré-fixada"],
            "valores": [50, 35, 15],
            "cores": ['#2E86AB', '#117A65', '#F39C12'],
            "explicacoes": [
                "Maior segurança e liquidez imediata",
                "Proteção contra inflação de longo prazo",
                "Retorno prefixado garantido"
            ]
        },
        "Conservador": {
            "labels": ["CDI/Selic", "IPCA+", "Pré-fixada", "Multimercados"],
            "valores": [40, 30, 20, 10],
            "cores": ['#2E86AB', '#117A65', '#F39C12', '#8E44AD'],
            "explicacoes": [
                "Liquidez imediata para oportunidades",
                "Proteção contra variações inflacionárias",
                "Exposição controlada a juros",
                "Diversificação com gestão ativa"
            ]
        },
        "Moderado": {
            "labels": ["CDI/Selic", "IPCA+", "Pré-fixada", "Multimercados", "Ações"],
            "valores": [30, 25, 15, 15, 15],
            "cores": ['#2E86AB', '#117A65', '#F39C12', '#8E44AD', '#E74C3C'],
            "explicacoes": [
                "Base conservadora para segurança",
                "Proteção contra inflação de longo prazo",
                "Exposição moderada a juros",
                "Gestão ativa para retornos superiores",
                "Potencial de valorização com controle"
            ]
        },
        "Agressivo": {
            "labels": ["CDI/Selic", "IPCA+", "Pré-fixada", "Multimercados", "Ações"],
            "valores": [15, 15, 10, 25, 35],
            "cores": ['#2E86AB', '#117A65', '#F39C12', '#8E44AD', '#E74C3C'],
            "explicacoes": [
                "Liquidez estratégica para oportunidades",
                "Proteção parcial contra inflação",
                "Baixa exposição a juros prefixados",
                "Gestão ativa com maior risco/retorno",
                "Alta exposição a ativos variáveis"
            ]
        }
    }
    
    dados = alocacoes.get(perfil, alocacoes["Moderado"])
    labels = dados["labels"]
    valores = dados["valores"]
    cores = dados["cores"]
    explicacoes = dados["explicacoes"]
    
    try:
        # Configurar estilo profissional
        plt.style.use('default')
        
        # Criar figura com tamanho otimizado
        fig = plt.figure(figsize=(12, 6))  # Reduzido de 14x7 para melhor performance
        fig.patch.set_facecolor('white')
        
        # Título centralizado
        fig.suptitle(
            f'Alocação de Ativos - Perfil {perfil}',
            fontsize=18,
            fontweight='bold',
            color='#2C3E50',
            y=0.98
        )
        
        # Criar áreas para pizza e legenda
        ax1 = fig.add_axes([0.05, 0.12, 0.4, 0.75])
        ax2 = fig.add_axes([0.52, 0.12, 0.43, 0.75])
        
        # ========== GRÁFICO DE PIZZA ==========
        wedges, texts, autotexts = ax1.pie(
            valores,
            labels=labels,
            autopct=lambda pct: f'{pct:.1f}%',
            startangle=90,
            colors=cores,
            textprops={'color': 'black', 'fontsize': 10},
            wedgeprops={'edgecolor': 'white', 'linewidth': 1.5},
            pctdistance=0.82,
            labeldistance=1.1
        )
        
        # Estilizar textos
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(10)
            autotext.set_weight('bold')
        
        for text in texts:
            text.set_fontsize(9)
        
        ax1.set_title('')
        ax1.axis('equal')
        
        # ========== LEGENDA EXPLICATIVA ==========
        ax2.axis('off')
        
        # Título da legenda
        ax2.text(
            0, 0.94,
            'ESTRATÉGIA DE ALOCAÇÃO',
            fontsize=12,
            fontweight='bold',
            color='#2C3E50',
            transform=ax2.transAxes,
            verticalalignment='top'
        )
        
        # Subtítulo
        ax2.text(
            0, 0.89,
            'Por classe de ativo e objetivo estratégico',
            fontsize=8,
            color='#7F8C8D',
            transform=ax2.transAxes,
            verticalalignment='top',
            style='italic'
        )
        
        # Linha separadora
        ax2.plot([0, 1], [0.86, 0.86], color='#BDC3C7', linewidth=0.8, transform=ax2.transAxes)
        
        # Adicionar itens da legenda
        y_start = 0.80
        step = 0.135
        
        for i, (label, valor, cor, explicacao) in enumerate(zip(labels, valores, cores, explicacoes)):
            y_pos = y_start - (i * step)
            if y_pos < 0.05:  # Evitar overflow
                break
            
            # Marcador colorido
            ax2.add_patch(plt.Rectangle(
                (0.02, y_pos - 0.02), 0.03, 0.03,
                facecolor=cor, edgecolor='white', linewidth=1,
                transform=ax2.transAxes
            ))
            
            # Nome da classe e percentual
            ax2.text(
                0.08, y_pos,
                f'{label} - {valor}%',
                fontsize=10,
                fontweight='bold',
                color=cor,
                transform=ax2.transAxes,
                verticalalignment='center'
            )
            
            # Explicação
            ax2.text(
                0.08, y_pos - 0.04,
                explicacao,
                fontsize=7.5,
                color='#7F8C8D',
                transform=ax2.transAxes,
                verticalalignment='center',
                style='italic'
            )
        
        # Nota de rodapé
        ax2.text(
            0, 0.02,
            'Recomendação baseada no perfil de risco, horizonte de investimento e objetivos.',
            fontsize=7,
            color='#95A5A6',
            transform=ax2.transAxes,
            style='italic',
            verticalalignment='bottom'
        )
        
        # Salvar imagem com DPI otimizado
        img_path = tempfile.mktemp(suffix='.png')
        plt.savefig(
            img_path, 
            dpi=150,  # Reduzido de 180 para melhor performance
            bbox_inches='tight', 
            facecolor='white',
            edgecolor='none'
        )
        plt.close()
        
        logger.info(f"Gráfico colorido gerado para perfil {perfil}")
        
        # Salvar no cache
        if use_cache:
            return GeradorGraficoCache.salvar_grafico(perfil, img_path)
        
        return img_path
        
    except Exception as e:
        logger.error(f"Erro ao gerar gráfico colorido: {e}")
        return gerar_grafico_alocacao_fallback(perfil)


def gerar_grafico_alocacao_fallback(perfil: str) -> str:
    """Versão de fallback otimizada do gráfico"""
    
    alocacoes = {
        "Ultraconservador": {"labels": ["CDI/Selic", "IPCA+", "Pré-fixada"], "valores": [50, 35, 15]},
        "Conservador": {"labels": ["CDI/Selic", "IPCA+", "Pré-fixada", "Multimercados"], "valores": [40, 30, 20, 10]},
        "Moderado": {"labels": ["CDI/Selic", "IPCA+", "Pré-fixada", "Multimercados", "Ações"], "valores": [30, 25, 15, 15, 15]},
        "Agressivo": {"labels": ["CDI/Selic", "IPCA+", "Pré-fixada", "Multimercados", "Ações"], "valores": [15, 15, 10, 25, 35]},
    }
    
    cores_padrao = ['#2E86AB', '#117A65', '#F39C12', '#8E44AD', '#E74C3C']
    
    dados = alocacoes.get(perfil, alocacoes["Moderado"])
    labels = dados["labels"]
    valores = dados["valores"]
    cores = cores_padrao[:len(valores)]
    
    # Configuração mais simples e rápida
    plt.style.use('default')
    fig, ax = plt.subplots(figsize=(8, 6))  # Tamanho reduzido
    fig.patch.set_facecolor('white')
    
    wedges, texts, autotexts = ax.pie(
        valores,
        labels=labels,
        autopct='%1.0f%%',
        startangle=90,
        colors=cores,
        textprops={'color': 'black', 'fontsize': 9},
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.5}
    )
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontsize(9)
        autotext.set_weight('bold')
    
    ax.set_title(f'Alocação Sugerida - Perfil {perfil}', fontsize=12, fontweight='bold', pad=15)
    
    img_path = tempfile.mktemp(suffix='.png')
    plt.savefig(img_path, dpi=100, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return img_path


# ==================== FUNÇÕES AUXILIARES ====================

def to_float(value: Any) -> float:
    """
    Converte valor para float de forma segura
    """
    try:
        logger.debug(f"to_float recebeu: '{value}' (tipo: {type(value).__name__})")
        
        if value is None or value == "":
            logger.debug("Valor vazio, retornando 0")
            return 0.0
        
        if isinstance(value, (int, float)):
            result = float(value)
            logger.debug(f"Valor já é número: {result}")
            return result
        
        if isinstance(value, str):
            # Remove espaços
            original = value
            value = value.strip()
            logger.debug(f"Após strip: '{value}'")
            
            # Remove R$ se existir
            if 'R$' in value:
                value = value.replace('R$', '').strip()
                logger.debug(f"Após remover R$: '{value}'")
            
            # Tenta converter diretamente
            try:
                result = float(value)
                logger.debug(f"Conversão direta bem-sucedida: {result}")
                return result
            except ValueError as e:
                logger.warning(f"Falha na conversão direta: {e}")
                
                # Se falhar, tenta tratar formato brasileiro
                if ',' in value:
                    # Troca vírgula por ponto
                    value = value.replace(',', '.')
                    logger.debug(f"Após trocar vírgula: '{value}'")
                    try:
                        result = float(value)
                        logger.debug(f"Conversão após trocar vírgula: {result}")
                        return result
                    except ValueError:
                        pass
                
                # Se ainda falhar, tenta remover tudo que não é número
                import re
                cleaned = re.sub(r'[^\d.]', '', value)
                logger.debug(f"Após limpeza regex: '{cleaned}'")
                if cleaned:
                    result = float(cleaned)
                    logger.debug(f"Conversão após regex: {result}")
                    return result
        
        logger.warning(f"Não foi possível converter, retornando 0")
        return 0.0
        
    except Exception as e:
        logger.error(f"Erro inesperado em to_float: {e}")
        return 0.0
    
def calcular_aporte_necessario(objetivo: dict) -> float:
    """Calcula o aporte anual necessário para atingir o objetivo"""
    valor_raw = objetivo.get("value", 0)
    if valor_raw == 0:
        valor_raw = objetivo.get("valor", 0)
    
    valor = to_float(valor_raw)
    
    meses_raw = objetivo.get("months", 12)
    if isinstance(meses_raw, str):
        meses_raw = to_float(meses_raw)
    
    prazo_anos = meses_raw / 12 if meses_raw > 0 else 1
    
    return valor / prazo_anos if prazo_anos > 0 else 0


def calcular_gap(objetivo: dict, capacidade_anual: float) -> str:
    """Calcula o gap entre necessidade e capacidade de poupança"""
    necessario = calcular_aporte_necessario(objetivo)
    
    if necessario <= capacidade_anual:
        folga = capacidade_anual - necessario
        return f"Alcançável (+ R$ {folga:,.2f} de folga anual)"
    
    gap = necessario - capacidade_anual
    return f"Gap de R$ {gap:,.2f}/ano - Recomendamos revisar prazo ou valor"


def recomendar_seguros(form_data: dict, cliente: dict) -> list:
    """Recomenda seguros baseado no perfil do cliente"""
    recs = []
    
    if form_data.get("lifeInsurance") != "Sim":
        recs.append("Seguro de Vida")
    
    if form_data.get("disabilityInsurance") != "Sim":
        recs.append("Seguro de Invalidez")
    
    profissao = cliente.get("profissao", "").lower()
    
    if any(p in profissao for p in ["empresario", "socio", "empresário", "sócio"]):
        recs.append("Seguro Empresarial para Sócios")
    elif any(p in profissao for p in ["executivo", "medico", "advogado", "médico"]):
        recs.append("DIT - Diária de Incapacidade Temporária")
    
    return recs if recs else ["Nenhum seguro prioritário identificado"]


def recomendar_eficiencia_fiscal(form_data: dict) -> list:
    """
    Recomenda estratégias de eficiência fiscal
    """
    recs = []
    
    # Mapeamento de fontes para PGBL
    fontes_pgbl = [
        "Salario", "Salário", "SALARIO", "SALÁRIO",
        "Distribuicao de lucro", "Distribuição de lucro", "DISTRIBUICAO_LUCRO",
        "Aposentadoria", "APOSENTADORIA",
        "SRC_SALARY", "SRC_PROFIT", "SRC_RETIREMENT",
        "pro-labore", "Pro-labore", "PRO_LABORE",
        "Pensao", "Pensão", "PENSAO"
    ]
    
    renda = form_data.get("incomeSource", "")
    renda_mensal_raw = form_data.get("income", 0)
    
    # 🔥 LOG ANTES DA CONVERSÃO
    logger.info(f"ANTES to_float - renda_mensal_raw: '{renda_mensal_raw}' tipo: {type(renda_mensal_raw).__name__}")
    
    # Converte renda mensal para float
    renda_mensal = to_float(renda_mensal_raw)
    
    # Log para debug
    logger.info(f"incomeSource recebido: '{renda}'")
    logger.info(f"income recebido: '{renda_mensal_raw}'")
    logger.info(f"income convertido: R$ {renda_mensal:.2f}")
    
    # ==================== PGBL ====================
    if renda in fontes_pgbl:
        logger.info(f"Fonte de renda '{renda}' é elegível para PGBL")
        limite = renda_mensal * 12 * 0.12
        logger.info(f"Limite calculado: {limite}")
        if limite > 0:
            recs.append(
                f"PGBL - Redução de 12% da base do IRPF (até R$ {limite:,.2f}/ano)"
            )
            logger.info(f"PGBL recomendado com limite: R$ {limite:,.2f}")
        else:
            logger.warning(f"Renda mensal zerada ou inválida: {renda_mensal}")
    else:
        logger.info(f"Fonte de renda '{renda}' não se enquadra em PGBL")
    
    # ==================== HOLDING IMOBILIÁRIA ====================
    fontes_holding = [
        "Aluguel", "ALUGUEL", "aluguel",
        "SRC_RENT", "Rent", "Renda de aluguel"
    ]
    
    num_imoveis_raw = form_data.get("realEstateCount", 0)
    try:
        num_imoveis = int(num_imoveis_raw) if num_imoveis_raw else 0
    except (ValueError, TypeError):
        num_imoveis = 0
    
    logger.info(f"Número de imóveis: {num_imoveis}")
    
    condicao_aluguel = renda in fontes_holding
    condicao_imoveis = num_imoveis >= 5
    
    if condicao_aluguel or condicao_imoveis:
        if condicao_aluguel:
            motivo = "Renda proveniente de aluguel"
        elif condicao_imoveis:
            motivo = f"Possui {num_imoveis} imóveis (acima de 5)"
        else:
            motivo = "Renda de aluguel e alta quantidade de imóveis"
        
        recs.append(
            f"Holding Imobiliária - Redução tributária de 27,5% para ~11% "
            f"({motivo})"
        )
        logger.info(f"Holding imobiliária recomendada: {motivo}")
    
    # ==================== RESULTADO ====================
    if not recs:
        recs = ["Nenhuma oportunidade fiscal identificada no momento"]
        logger.info("Nenhuma recomendação fiscal gerada")
    else:
        logger.info(f"Recomendações fiscais geradas: {len(recs)}")
    
    return recs
 
def to_float(value: Any) -> float:
    """
    Converte valor para float de forma segura
    """
    try:
        if value is None or value == "":
            return 0.0
        
        # 🔥 SE FOR DECIMAL (do Django), converte diretamente
        if hasattr(value, '__class__') and value.__class__.__name__ == 'Decimal':
            # É um Decimal do Django
            result = float(value)
            logger.debug(f"Convertendo Decimal {value} -> {result}")
            return result
        
        if isinstance(value, (int, float)):
            result = float(value)
            logger.debug(f"Valor numérico: {result}")
            return result
        
        if isinstance(value, str):
            # Remove espaços
            value = value.strip()
            
            # Remove R$ se existir
            value = value.replace('R$', '').strip()
            
            # Remove pontos de milhar e troca vírgula por ponto
            value = value.replace('.', '').replace(',', '.')
            
            # Converte para float
            result = float(value)
            logger.debug(f"String convertida: {value} -> {result}")
            return result
        
        # Se for outro tipo, tenta converter
        logger.warning(f"Tipo não reconhecido: {type(value)} - {value}")
        return float(value)
        
    except (ValueError, TypeError, Exception) as e:
        logger.warning(f"Erro ao converter '{value}' para float: {e}")
        return 0.0

def gerar_texto_atendimento(preferencia: str, perfil: str) -> str:
    """Gera texto personalizado para preferência de atendimento"""
    textos = {
        "digital": f"Cliente prefere atendimento digital e ágil, com comunicação por WhatsApp e reuniões remotas. Perfil {perfil} com potencial para acompanhamento consultivo personalizado.",
        "presencial": f"Cliente prefere atendimento presencial personalizado, com reuniões no escritório ou local de preferência. Perfil {perfil} demanda atenção especial e relacionamento próximo.",
        "hibrido": f"Cliente prefere atendimento híbrido, combinando encontros presenciais estratégicos com suporte digital contínuo. Modelo ideal para perfil {perfil}."
    }
    return textos.get(preferencia, f"Cliente prefere atendimento personalizado, alinhado ao perfil {perfil} com foco em relacionamento consultivo de longo prazo.")


def limpar_cache_graficos(perfil: Optional[str] = None):
    """Limpa o cache de gráficos"""
    if perfil:
        cache_path = GeradorGraficoCache._get_cache_path(perfil)
        if cache_path.exists():
            cache_path.unlink()
        cache_key = GeradorGraficoCache._get_cache_key(perfil)
        _graph_cache.pop(cache_key, None)
        logger.info(f"Cache limpo para perfil {perfil}")
    else:
        # Limpar tudo
        for file in CACHE_DIR.glob("*.png"):
            file.unlink()
        _graph_cache.clear()
        logger.info("Cache completo de gráficos limpo")


# ==================== FUNÇÃO PRINCIPAL ====================

def gerar_relatorio_pdf(cliente: dict, form_data: dict, output_path: str = None, use_cache: bool = True) -> str:
    """
    Gera relatório PDF completo com gráfico colorido profissional.
    
    Args:
        cliente: Dados cadastrais do cliente
        form_data: Respostas do formulário de onboarding
        output_path: Caminho opcional para salvar o PDF
        use_cache: Se deve usar cache de gráficos (recomendado=True)
    
    Returns:
        Caminho do arquivo PDF gerado
    """
    try:

        # LOG PARA DEBUG
        logger.info("=" * 50)
        logger.info("DADOS RECEBIDOS NO FORM_DATA:")
        logger.info(f"incomeSource: '{form_data.get('incomeSource')}'")
        logger.info(f"income: '{form_data.get('income')}'")
        logger.info(f"realEstateCount: '{form_data.get('realEstateCount')}'")
        logger.info("=" * 50)
        logger.info(f"Iniciando geração de relatório para cliente: {cliente.get('nome', 'Desconhecido')}")
        
        # Processar dados
        perfil = determinar_perfil_investidor(form_data)
        capacidade = calcular_capacidade_poupanca_anual(form_data)
        patrimonio = to_float(form_data.get("financialAssets", 0)) + to_float(form_data.get("realEstateValue", 0))
        
        # Criar PDF
        pdf = RelatorioClientePDF(cliente)
        pdf.add_page()
        
        # =========================================================
        # 1. DADOS PESSOAIS
        # =========================================================
        pdf.adicionar_secao('DADOS PESSOAIS')
        
        pdf.adicionar_campo('Nome', cliente.get('nome', 'Não informado'))
        
        idade = cliente.get('idade', '')
        pdf.adicionar_campo('Idade', f'{idade} anos' if idade else 'Não informado')
        
        pdf.adicionar_campo('Profissão', cliente.get('profissao', 'Não informado'))
        pdf.adicionar_campo('Estado civil', cliente.get('estado_civil', 'Não informado'))
        
        pdf.ln(5)
        
        # =========================================================
        # 2. RAIO-X FINANCEIRO
        # =========================================================
        pdf.adicionar_secao('RAIO-X FINANCEIRO')
        
        pdf.adicionar_campo('Capacidade de poupança anual', f'R$ {capacidade:,.2f}')
        pdf.adicionar_campo('Patrimônio total', f'R$ {patrimonio:,.2f}')
        pdf.adicionar_campo('Perfil do investidor', perfil)
        
        pdf.ln(5)
        
        # =========================================================
        # ALOCAÇÃO SUGERIDA E GRÁFICO
        # =========================================================
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 5, 'Alocacao sugerida:', 0, 1)

        pdf.set_font('Arial', '', 10)

        for item in get_alocacao_sugerida(perfil):
            pdf.set_x(15)
            pdf.cell(0, 5, f'- {item}', 0, 1)

        pdf.ln(10)
        
        # Gráfico de alocação colorido (com cache)
        try:
            img_path = gerar_grafico_alocacao_colorido(perfil, use_cache=use_cache)
            largura_imagem = 170
            largura_pagina = 210
            x_central = (largura_pagina - largura_imagem) / 2
            pdf.image(img_path, x=x_central, w=largura_imagem)
            
            # Só remove se não for do cache
            if not use_cache or not CACHE_DIR.joinpath(f"alocacao_{perfil.lower()}.png").exists():
                try:
                    os.remove(img_path)
                except:
                    pass
                    
            pdf.ln(12)
        except Exception as e:
            logger.error(f"Erro ao adicionar gráfico ao PDF: {e}")
            pdf.set_font('Arial', 'I', 9)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 10, 'Não foi possível gerar o gráfico de alocação', 0, 1, 'C')
            pdf.ln(5)
        
        # =========================================================
        # 3. OBJETIVOS
        # =========================================================
        pdf.add_page()
        pdf.adicionar_secao('OBJETIVOS')
        
        objetivos = form_data.get("financialGoals", [])
        if objetivos:
            for obj in objetivos[:5]:
                desc = obj.get("name") or obj.get("nome", "Não informado")
                valor = to_float(obj.get("valor", obj.get("value", 0)))
                
                prazo_meses = obj.get("months", 12)
                if isinstance(prazo_meses, str):
                    prazo_meses = to_float(prazo_meses)
                
                aporte = calcular_aporte_necessario(obj)
                gap = calcular_gap(obj, capacidade)
                
                pdf.adicionar_campo('Objetivo', desc)
                pdf.adicionar_campo('Valor', f'R$ {valor:,.2f}')
                pdf.adicionar_campo('Prazo', f'{prazo_meses:.0f} meses')
                pdf.adicionar_campo('Necessário/ano', f'R$ {aporte:,.2f}')
                pdf.adicionar_campo('Status', gap)
                pdf.ln(3)
        else:
            pdf.cell(0, 6, 'Nenhum objetivo cadastrado', 0, 1)
        
        pdf.ln(5)
        
        # =========================================================
        # 4. PROTEÇÃO PATRIMONIAL
        # =========================================================
        pdf.adicionar_secao('PROTEÇÃO PATRIMONIAL')
        
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, 'Oportunidades identificadas:', 0, 1)
        pdf.set_font('Arial', '', 10)
        
        seguros = recomendar_seguros(form_data, cliente)
        for seguro in seguros:
            pdf.set_x(15)
            pdf.cell(0, 5, f'- {seguro}', 0, 1)
        
        pdf.ln(3)
        
        seguro_vida = patrimonio * 0.2
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, 'Seguro de vida recomendado:', 0, 1)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 5, f'20% do patrimônio total = R$ {seguro_vida:,.2f}', 0, 1)
        
        estado_civil = cliente.get("estado_civil", "")
        tem_filhos = cliente.get("tem_filhos", False)
        
        if estado_civil in ["Casado", "União Estável", "CASADO", "UNIAO_ESTAVEL"] or tem_filhos:
            if form_data.get("succession") != "Sim":
                pdf.ln(3)
                pdf.set_text_color(200, 0, 0)
                pdf.set_font('Arial', 'B', 10)
                largura_label = pdf.get_string_width('Importante:') + 2
                pdf.cell(largura_label, 6, 'Importante:', 0, 0)
                pdf.set_font('Arial', '', 10)
                pdf.cell(0, 6, 'Planejamento sucessório necessário', 0, 1)
                pdf.set_text_color(0, 0, 0)
        
        # =========================================================
        # 5. EFICIÊNCIA FISCAL
        # =========================================================
        pdf.adicionar_secao('EFICIENCIA FISCAL')

        eficiencias = recomendar_eficiencia_fiscal(form_data)
        pdf.adicionar_lista(eficiencias)

        pdf.ln(5)
        
        # =========================================================
        # 6. PREFERÊNCIAS DE ATENDIMENTO
        # =========================================================
        pdf.adicionar_secao('PREFERÊNCIAS DE ATENDIMENTO')
        
        pref = form_data.get("atendimento_preferencia", "padronizado")
        texto = gerar_texto_atendimento(pref, perfil)
        pdf.multi_cell(0, 5, texto)
        
        # =========================================================
        # SALVAR PDF
        # =========================================================
        if output_path is None:
            os.makedirs("media/relatorios", exist_ok=True)
            nome_cliente = cliente.get('nome', 'cliente').replace(' ', '_')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"media/relatorios/relatorio_{nome_cliente}_{timestamp}.pdf"
        
        pdf.output(output_path)
        logger.info(f"Relatório gerado com sucesso: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Erro ao gerar relatório: {e}", exc_info=True)
        raise RuntimeError(f"Falha na geração do relatório: {str(e)}")