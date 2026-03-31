# onboarding/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.exceptions import ValidationError  # 🔥 ADICIONE

# =========================
# CUSTOM USER
# =========================
class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username


# =========================
# CHOICES - MOVA TODOS PARA CIMA DA CLASSE FormSubmission
# =========================
class Profissao(models.TextChoices):
    ENTREPRENEUR = "JOB_ENTREPRENEUR", "Empresário"
    EXECUTIVE = "JOB_EXECUTIVE", "Executivo"
    PROFESSIONAL = "JOB_PROFESSIONAL", "Profissional liberal"
    CLT = "JOB_CLT", "Funcionário CLT"
    INVESTOR = "JOB_INVESTOR", "Investidor"
    RETIRED = "JOB_RETIRED", "Aposentado"
    OTHER = "JOB_OTHER", "Outro"


class EstadoCivil(models.TextChoices):
    SINGLE = "MS_SINGLE", "Solteiro"
    MARRIED = "MS_MARRIED", "Casado"
    DIVORCED = "MS_DIVORCED", "Divorciado"


class Filhos(models.TextChoices):
    NONE = "CH_NONE", "Sem filhos"
    DEP = "CH_DEP", "Dependentes"
    NODEP = "CH_NODEP", "Independentes"


class FonteRenda(models.TextChoices):
    PROFIT = "SRC_PROFIT", "Distribuição de lucro"
    SALARY = "SRC_SALARY", "Salário"
    RENT = "SRC_RENT", "Aluguéis"
    INVEST = "SRC_INVEST", "Investimentos"
    RETIREMENT = "SRC_RETIREMENT", "Aposentadoria"


class SimNao(models.TextChoices):
    YES = "YES", "Sim"
    NO = "NO", "Não"


class InvestPeriod(models.TextChoices):
    MONTH = "PER_MONTH", "Mensal"
    QUARTER = "PER_QUARTER", "Trimestral"
    SEM = "PER_SEM", "Semestral"
    YEAR = "PER_YEAR", "Anual"


class Horizonte(models.TextChoices):
    SHORT = "HZ_SHORT", "Curto prazo"
    MEDIUM = "HZ_MEDIUM", "Médio prazo"
    LONG = "HZ_LONG", "Longo prazo"


class Risco(models.TextChoices):
    REDUCE = "RISK_REDUCE", "Reduziria"
    HOLD = "RISK_HOLD", "Manteria"
    BUY = "RISK_BUY", "Compraria mais"


class Preferencia(models.TextChoices):
    STABLE = "PREF_STABLE", "Rendimento estável"
    GROWTH = "PREF_GROWTH", "Crescimento"


class Contato(models.TextChoices):
    CLOSE = "CONTACT_CLOSE", "Próximo"
    PERIODIC = "CONTACT_PERIODIC", "Periódico"
    STRATEGIC = "CONTACT_STRATEGIC", "Estratégico"
    ONDEMAND = "CONTACT_ONDEMAND", "Sob demanda"


# =========================
# FORM SUBMISSION
# =========================
class FormSubmission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Visão geral
    Nome = models.CharField(max_length=255, blank=False, null=False)
    CPF = models.CharField(max_length=20, blank=True, null=True)
    Nascimento = models.DateField(blank=True, null=True)
    Profissao = models.CharField(max_length=30, choices=Profissao.choices, blank=True, null=True)
    Profissao_Outro = models.CharField(max_length=255, blank=True, null=True)
    Estado_Civil = models.CharField(max_length=20, choices=EstadoCivil.choices, blank=True, null=True)
    Filhos = models.CharField(max_length=20, choices=Filhos.choices, blank=True, null=True)
    Dependentes = models.IntegerField(blank=True, null=True)

    # Financeiro
    Patrimonio_Financeiro = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    Patrimonio_Imobiliario = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    Qtd_Imoveis = models.IntegerField(blank=True, null=True)
    Renda_Mensal = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    Fonte_Renda = models.CharField(max_length=20, choices=FonteRenda.choices, blank=True, null=True)
    Custo_Vida = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    Frequencia_Invest = models.CharField(max_length=5, choices=SimNao.choices, blank=True, null=True)
    Valor_Investimento = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    Periodo_Invest = models.CharField(max_length=20, choices=InvestPeriod.choices, blank=True, null=True)

    # Dívidas
    Dividas = models.CharField(max_length=5, choices=SimNao.choices, blank=True, null=True)
    Tipo_Divida = models.JSONField(blank=True, null=True)
    Valor_Dividas = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    # Objetivos
    Objetivos = models.JSONField(blank=True, null=True)
    Horizonte = models.CharField(max_length=20, choices=Horizonte.choices, blank=True, null=True)
    Risco = models.CharField(max_length=20, choices=Risco.choices, blank=True, null=True)
    Preferencia = models.CharField(max_length=20, choices=Preferencia.choices, blank=True, null=True)

    # Proteção
    Seguro = models.CharField(max_length=5, choices=SimNao.choices, blank=True, null=True)
    Seguro_Invalidez = models.CharField(max_length=5, choices=SimNao.choices, blank=True, null=True)
    Sucessao = models.CharField(max_length=5, choices=SimNao.choices, blank=True, null=True)
    Estrutura_Societaria = models.CharField(max_length=5, choices=SimNao.choices, blank=True, null=True)
    Investimento_Exterior = models.CharField(max_length=5, choices=SimNao.choices, blank=True, null=True)

    # Relacionamento
    Contato = models.CharField(max_length=20, choices=Contato.choices, blank=True, null=True)
    Expectativa = models.TextField(blank=True, null=True)
    Nao_Resolvido = models.TextField(blank=True, null=True)

    # Sistema
    Criado_Em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.Nome