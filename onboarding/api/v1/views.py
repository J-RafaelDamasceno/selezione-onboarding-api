# onboarding/api/v1/views.py
import logging 
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
import json
import os
from datetime import date

from onboarding.models import FormSubmission
from onboarding.api.v1.serializers import FormSubmissionSerializer, SubmissionWithScoreSerializer
from .score_engine import calculate_score

# ✅ NOVO IMPORT - funções de cálculo (sem dependências de PDF)
from onboarding.api.v1.calculos_relatorio import (
    determinar_perfil_investidor,
    calcular_capacidade_poupanca,
    calcular_aporte_mensal_necessario,
    calcular_tempo_para_meta,
    calcular_gap,
    recomendar_seguros,
    recomendar_eficiencia_fiscal,
    gerar_texto_atendimento,
    formatar_br,
    to_float,
    ALOCACOES_POR_PERFIL,
    TAXA_JUROS_ANUAL,
)

logger = logging.getLogger(__name__)


class FormSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = FormSubmissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FormSubmission.objects.filter(user=self.request.user).order_by("-Criado_Em")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["Nome", "Profissao", "Contato"]
    ordering_fields = ["Criado_Em", "Nome", "Renda_Mensal"]
    ordering = ["-Criado_Em"]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        print("\n" + "="*60)
        print("🔵 PAYLOAD RECEBIDO:")
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        print("="*60 + "\n")

        objetivos = data.get("Objetivos", [])
        if isinstance(objetivos, str):
            try:
                objetivos = json.loads(objetivos)
            except json.JSONDecodeError:
                objetivos = []
        data["Objetivos"] = objetivos

        serializer = self.get_serializer(data=data)
        
        if not serializer.is_valid():
            print("\n🔴 ERROS DE VALIDAÇÃO DO SERIALIZER:")
            print(json.dumps(serializer.errors, indent=2, ensure_ascii=False))
            return Response({
                'status': 'error',
                'errors': serializer.errors,
                'received_data': {k: str(v) for k, v in data.items() if k not in ['user']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def score(self, request, pk=None):
        submission = self.get_object()

        main_focus = submission.Objetivos
        if isinstance(main_focus, str):
            try:
                main_focus = json.loads(main_focus)
            except json.JSONDecodeError:
                main_focus = []

        form_data = {
            "financialAssets": submission.Patrimonio_Financeiro,
            "income": submission.Renda_Mensal,
            "incomeSource": submission.Fonte_Renda,
            "realEstateValue": submission.Patrimonio_Imobiliario,
            "succession": submission.Sucessao,
            "lifeInsurance": submission.Seguro,
            "disabilityInsurance": submission.Seguro_Invalidez,
            "corporateStructure": submission.Estrutura_Societaria,
            "risk": submission.Risco,
            "investFrequency": submission.Frequencia_Invest,
            "investPeriod": submission.Periodo_Invest,
            "preference": submission.Preferencia,
            "mainFocus": main_focus,
        }

        print("FORM DATA:", form_data)
        score = calculate_score(form_data)
        return Response(score)

    @action(detail=False, methods=["get"], url_path="with-scores")
    def list_with_scores(self, request):
        """
        Retorna todos os submissions do usuário com scores já calculados.
        Mais eficiente que fazer 1 + N chamadas separadas.
        """
        try:
            submissions = self.get_queryset()
            serializer = SubmissionWithScoreSerializer(submissions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Erro em list_with_scores: {e}", exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["get"], url_path="relatorio-data")
    def relatorio_data(self, request, pk=None):
        try:
            submission = self.get_object()

            # ── Idade ────────────────────────────────────────────
            nascimento = submission.Nascimento
            if nascimento:
                hoje = date.today()
                idade = hoje.year - nascimento.year
                if (hoje.month, hoje.day) < (nascimento.month, nascimento.day):
                    idade -= 1
            else:
                idade = None

            # ── Cliente ──────────────────────────────────────────
            cliente = {
                "nome": submission.Nome,
                "idade": idade,
                "profissao": (
                    submission.Profissao_Outro
                    if submission.Profissao == "JOB_OTHER"
                    else submission.get_Profissao_display()
                    if submission.Profissao
                    else "N/A"
                ),
                "estado_civil": (
                    submission.get_Estado_Civil_display()
                    if submission.Estado_Civil
                    else "N/A"
                ),
                "dependentes": submission.Dependentes or 0,
            }

            # ── Objetivos raw ────────────────────────────────────
            objetivos_raw = submission.Objetivos
            if isinstance(objetivos_raw, str):
                try:
                    objetivos_raw = json.loads(objetivos_raw)
                except json.JSONDecodeError:
                    objetivos_raw = []

            # ── Form data ────────────────────────────────────────
            form_data = {
                "financialAssets":     submission.Patrimonio_Financeiro,
                "income":              submission.Renda_Mensal,
                "incomeSource":        submission.Fonte_Renda,
                "realEstateValue":     submission.Patrimonio_Imobiliario,
                "realEstateCount":     submission.Qtd_Imoveis,
                "succession":          submission.Sucessao,
                "lifeInsurance":       submission.Seguro,
                "disabilityInsurance": submission.Seguro_Invalidez,
                "corporateStructure":  submission.Estrutura_Societaria,
                "risk":                submission.Risco,
                "investFrequency":     submission.Frequencia_Invest,
                "investPeriod":        submission.Periodo_Invest,
                "preference":          submission.Preferencia,
                "horizon":             submission.Horizonte,
                "investAmount":        submission.Valor_Investimento,
                "financialGoals":      objetivos_raw,
                "monthlyExpenses":     submission.Custo_Vida,
                "foreignInvestment":   submission.Investimento_Exterior,
                "atendimento_preferencia": (
                    submission.get_Contato_display()
                    if submission.Contato
                    else "N/A"
                ),
            }

            # ── Cálculos principais ──────────────────────────────
            perfil     = determinar_perfil_investidor(form_data)
            capacidade = calcular_capacidade_poupanca(form_data)
            patrimonio = (
                to_float(form_data.get("financialAssets", 0))
                + to_float(form_data.get("realEstateValue", 0))
            )

            # ── Alocações ────────────────────────────────────────
            alocacoes = ALOCACOES_POR_PERFIL.get(
                perfil, ALOCACOES_POR_PERFIL["Moderado"]
            )

            # ── Objetivos com séries para gráfico ────────────────
            taxa_mensal = (1 + TAXA_JUROS_ANUAL) ** (1 / 12) - 1
            objetivos_processados = []

            for obj in objetivos_raw:
                desc        = obj.get("name") or obj.get("nome", "Não informado")
                valor       = to_float(obj.get("valor", obj.get("value", 0)))
                prazo_meses = int(float(obj.get("months", 12)))

                if valor <= 0:
                    continue

                aporte_nec = calcular_aporte_mensal_necessario(valor, prazo_meses)
                tempo_real = calcular_tempo_para_meta(valor, capacidade["mensal"])
                gap        = calcular_gap(obj, capacidade["mensal"])

                # Série necessária
                serie_necessaria, acc = [], 0.0
                for _ in range(prazo_meses):
                    acc = acc * (1 + taxa_mensal) + aporte_nec
                    serie_necessaria.append(round(acc, 2))

                # Série real
                if capacidade["mensal"] > 0:
                    serie_real, acc = [], 0.0
                    for _ in range(prazo_meses):
                        acc = acc * (1 + taxa_mensal) + capacidade["mensal"]
                        serie_real.append(round(acc, 2))
                else:
                    serie_real = serie_necessaria.copy()

                objetivos_processados.append({
                    "desc":                     desc,
                    "valor":                    valor,
                    "valor_formatado":          formatar_br(valor),
                    "prazo_meses":              prazo_meses,
                    "aporte_mensal_necessario": round(aporte_nec, 2),
                    "aporte_mensal_formatado":  formatar_br(aporte_nec),
                    "tempo_real_meses":         tempo_real,
                    "gap":                      gap,
                    "alcancavel":               "Gap" not in gap,
                    "serie_necessaria":         serie_necessaria,
                    "serie_real":               serie_real,
                })

            # ── Proteção e fiscal ────────────────────────────────
            seguros_recomendados = recomendar_seguros(form_data, cliente)
            eficiencia_fiscal = recomendar_eficiencia_fiscal(form_data)
            seguro_vida = patrimonio * 0.2

            # ===== TODOS OS SEGUROS/PROTEÇÃO QUE O USUÁRIO POSSUI =====
            seguros_possui = {
                "seguro_vida": submission.Seguro == "YES",
                "seguro_invalidez": submission.Seguro_Invalidez == "YES",
                "planejamento_sucessorio": submission.Sucessao == "YES",
                "estrutura_societaria": submission.Estrutura_Societaria == "YES",
                "investimento_exterior": submission.Investimento_Exterior == "YES",
            }
            
            # ===== TEXTO PARA RELATÓRIO (mostrar o que ele já tem) =====
            seguros_contratados_lista = []
            if seguros_possui["seguro_vida"]:
                seguros_contratados_lista.append("Seguro de Vida")
            if seguros_possui["seguro_invalidez"]:
                seguros_contratados_lista.append("Seguro de Invalidez")
            if seguros_possui["planejamento_sucessorio"]:
                seguros_contratados_lista.append("Planejamento Sucessório")
            if seguros_possui["estrutura_societaria"]:
                seguros_contratados_lista.append("Estrutura Societária/Holding")
            if seguros_possui["investimento_exterior"]:
                seguros_contratados_lista.append("Investimento no Exterior")
            
            # ===== RECOMENDAÇÕES BASEADAS NO QUE ELE NÃO TEM =====
            recomendacoes_personalizadas = []
            
            # Recomendar seguro de vida
            if not seguros_possui["seguro_vida"] and to_float(submission.Patrimonio_Financeiro) > 500000:
                recomendacoes_personalizadas.append({
                    "tipo": "Seguro de Vida",
                    "motivo": "Proteção financeira para sua família e patrimônio",
                    "prioridade": "Alta",
                    "campo_model": "Seguro"
                })
            
            # Recomendar seguro invalidez
            if not seguros_possui["seguro_invalidez"] and to_float(submission.Renda_Mensal) > 10000:
                recomendacoes_personalizadas.append({
                    "tipo": "Seguro de Invalidez",
                    "motivo": "Garantia de renda em caso de incapacidade para trabalhar",
                    "prioridade": "Alta",
                    "campo_model": "Seguro_Invalidez"
                })
            
            # Recomendar planejamento sucessório
            if not seguros_possui["planejamento_sucessorio"] and to_float(submission.Patrimonio_Imobiliario) > 0:
                recomendacoes_personalizadas.append({
                    "tipo": "Planejamento Sucessório",
                    "motivo": "Evitar custos de inventário e proteger seus herdeiros",
                    "prioridade": "Média",
                    "campo_model": "Sucessao"
                })
            
            # Recomendar estrutura societária
            if not seguros_possui["estrutura_societaria"] and submission.Profissao == "JOB_ENTREPRENEUR":
                recomendacoes_personalizadas.append({
                    "tipo": "Estrutura Societária/Holding",
                    "motivo": "Separar patrimônio pessoal do negócio e reduzir riscos",
                    "prioridade": "Alta",
                    "campo_model": "Estrutura_Societaria"
                })
            
            # Recomendar investimento exterior
            if not seguros_possui["investimento_exterior"] and to_float(submission.Patrimonio_Financeiro) > 1000000:
                recomendacoes_personalizadas.append({
                    "tipo": "Investimento no Exterior",
                    "motivo": "Diversificação cambial e proteção jurídica internacional",
                    "prioridade": "Média",
                    "campo_model": "Investimento_Exterior"
                })

            estado_civil = cliente.get("estado_civil", "")
            tem_filhos = submission.Filhos != "CH_NONE" if submission.Filhos else False
            necessidade_sucessao = (
                estado_civil in ["Casado", "União Estável", "CASADO", "UNIAO_ESTAVEL"]
                or tem_filhos
            ) and submission.Sucessao != "YES"

            texto_atendimento = gerar_texto_atendimento(
                form_data.get("atendimento_preferencia", ""), perfil
            )

            # ── Resposta final COM TODOS OS CAMPOS DE SEGUROS ──
            return Response({
                # ===== CAMPOS EXISTENTES =====
                "cliente":               cliente,
                "perfil":                perfil,
                "capacidade_mensal":     round(capacidade["mensal"], 2),
                "capacidade_mensal_fmt": formatar_br(capacidade["mensal"]),
                "capacidade_anual":      round(capacidade["anual"], 2),
                "capacidade_anual_fmt":  formatar_br(capacidade["anual"]),
                "patrimonio":            round(patrimonio, 2),
                "patrimonio_fmt":        formatar_br(patrimonio),
                "alocacoes":             alocacoes,
                "objetivos":             objetivos_processados,
                "seguros_recomendados":  seguros_recomendados,
                "eficiencias":           eficiencia_fiscal["recomendacoes"],
                "eficiencia_motivo":     eficiencia_fiscal["motivo"],
                "seguro_vida":           round(seguro_vida, 2),
                "seguro_vida_fmt":       formatar_br(seguro_vida),
                "necessidade_sucessao":  necessidade_sucessao,
                "texto_atendimento":     texto_atendimento,
                "taxa_juros":            f"{TAXA_JUROS_ANUAL * 100:.0f}%",
                "data_geracao":          date.today().strftime("%B %Y").upper(),
                
                # ===== CAMPOS DO MODELO =====
                "tem_filhos": submission.Filhos != "CH_NONE" if submission.Filhos else False,
                "dependentes": submission.Dependentes,
                "patrimonio_investidor": formatar_br(to_float(submission.Patrimonio_Financeiro)),
                "patrimonio_imobiliario": formatar_br(to_float(submission.Patrimonio_Imobiliario)),
                "quantidade_imoveis": submission.Qtd_Imoveis or 0,
                
                "investe_mensal": formatar_br(to_float(submission.Valor_Investimento)) if submission.Frequencia_Invest == "YES" else "Não informado",
                "periodicidade_investimento": submission.get_Periodo_Invest_display() if submission.Periodo_Invest else "N/A",
                "horizonte_investimento": submission.get_Horizonte_display() if submission.Horizonte else "N/A",
                
                "preferencia_risco": submission.get_Risco_display() if submission.Risco else "N/A",
                "preferencia_alocacao": submission.get_Preferencia_display() if submission.Preferencia else "N/A",
                
                "objetivos_prazos": [
                    {
                        "desc": obj.get("name") or obj.get("nome", "Não informado"),
                        "prazo_meses": int(obj.get("months", 12))
                    }
                    for obj in objetivos_raw
                ],
                
                # ===== NOVOS CAMPOS DE SEGUROS E PROTEÇÃO =====
                "seguros_contratados": seguros_possui,
                "seguros_contratados_lista": seguros_contratados_lista,
                "recomendacoes_seguros_personalizadas": recomendacoes_personalizadas,
                "total_seguros_contratados": len(seguros_contratados_lista),
                "possui_algum_seguro": any(seguros_possui.values()),
                "percentual_protecao": round((len(seguros_contratados_lista) / 5) * 100, 0),
                
                # Detalhamento individual para o frontend usar como quiser
                "detalhes_seguros": {
                    "vida": {
                        "possui": seguros_possui["seguro_vida"],
                        "campo_model": "Seguro",
                        "recomendado": not seguros_possui["seguro_vida"] and to_float(submission.Patrimonio_Financeiro) > 500000,
                        "prioridade": "Alta" if not seguros_possui["seguro_vida"] and to_float(submission.Patrimonio_Financeiro) > 500000 else "Baixa"
                    },
                    "invalidez": {
                        "possui": seguros_possui["seguro_invalidez"],
                        "campo_model": "Seguro_Invalidez",
                        "recomendado": not seguros_possui["seguro_invalidez"] and to_float(submission.Renda_Mensal) > 10000,
                        "prioridade": "Alta" if not seguros_possui["seguro_invalidez"] and to_float(submission.Renda_Mensal) > 10000 else "Baixa"
                    },
                    "sucessao": {
                        "possui": seguros_possui["planejamento_sucessorio"],
                        "campo_model": "Sucessao",
                        "recomendado": not seguros_possui["planejamento_sucessorio"] and to_float(submission.Patrimonio_Imobiliario) > 0,
                        "prioridade": "Média" if not seguros_possui["planejamento_sucessorio"] and to_float(submission.Patrimonio_Imobiliario) > 0 else "Baixa"
                    },
                    "estrutura": {
                        "possui": seguros_possui["estrutura_societaria"],
                        "campo_model": "Estrutura_Societaria",
                        "recomendado": not seguros_possui["estrutura_societaria"] and submission.Profissao == "JOB_ENTREPRENEUR",
                        "prioridade": "Alta" if not seguros_possui["estrutura_societaria"] and submission.Profissao == "JOB_ENTREPRENEUR" else "Baixa"
                    },
                    "exterior": {
                        "possui": seguros_possui["investimento_exterior"],
                        "campo_model": "Investimento_Exterior",
                        "recomendado": not seguros_possui["investimento_exterior"] and to_float(submission.Patrimonio_Financeiro) > 1000000,
                        "prioridade": "Média" if not seguros_possui["investimento_exterior"] and to_float(submission.Patrimonio_Financeiro) > 1000000 else "Baixa"
                    }
                }
            })

        except Exception as e:
            logger.error(f"Erro ao gerar dados do relatório: {e}", exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        user = request.user
        if user.is_authenticated:
            data = {
                "id": user.id,
                "Nome": user.get_full_name() or user.username,
                "email": user.email,
            }
            return Response(data, status=status.HTTP_200_OK)
        return Response({"detail": "Não autenticado."}, status=status.HTTP_401_UNAUTHORIZED)


# =========================
# RELATÓRIO PDF VIEWSET
# =========================
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
from django.conf import settings
from pathlib import Path

class RelatorioPDFViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=["get"], url_path="pdf/(?P<submission_id>[^/.]+)")
    def gerar_pdf(self, request, submission_id=None):
        """
        Gera PDF do relatório usando WeasyPrint
        """
        try:
            # Buscar o submission
            submission = FormSubmission.objects.get(id=submission_id, user=request.user)
            
            # Reaproveitar a lógica do relatorio_data
            view = FormSubmissionViewSet()
            view.request = request
            view.kwargs = {'pk': submission_id}
            
            response = view.relatorio_data(request, pk=submission_id)
            
            if response.status_code != 200:
                return Response({"error": "Erro ao gerar dados do relatório"}, 
                              status=response.status_code)
            
            dados_relatorio = response.data
            
            # Renderizar o template HTML
            html_string = render_to_string('relatorio_pdf.html', {
                'data': dados_relatorio,
                'STATIC_URL': settings.STATIC_URL,
                'base_url': request.build_absolute_uri('/')
            })
            
            # Configurar CSS
            css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'relatorio_pdf.css')
            
            # Gerar PDF
            html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
            
            if os.path.exists(css_path):
                with open(css_path, 'r', encoding='utf-8') as css_file:
                    css_string = css_file.read()
                pdf_file = html.write_pdf(stylesheets=[CSS(string=css_string)])
            else:
                pdf_file = html.write_pdf()
            
            # Retornar PDF
            http_response = HttpResponse(pdf_file, content_type='application/pdf')
            http_response['Content-Disposition'] = f'attachment; filename="relatorio_{submission.Nome}_{submission.id}.pdf"'
            
            return http_response
            
        except FormSubmission.DoesNotExist:
            return Response({"error": "Submission não encontrado"}, 
                          status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Erro ao gerar PDF: {e}", exc_info=True)
            return Response({"error": str(e)}, 
                          status=status.HTTP_400_BAD_REQUEST)