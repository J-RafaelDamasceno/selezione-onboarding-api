import logging
import json
import os
from datetime import date

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from weasyprint import HTML, CSS

from onboarding.models import FormSubmission
from onboarding.api.v1.serializers import (
    FormSubmissionSerializer,
    SubmissionWithScoreSerializer,
)
from .score_engine import calculate_score
from onboarding.api.v1.calculos_relatorio import (
    determinar_perfil_investidor,
    calcular_capacidade_poupanca,
    recomendar_seguros,
    recomendar_eficiencia_fiscal,
    gerar_texto_atendimento,
    formatar_br,
    to_float,
    processar_objetivos,
    ALOCACOES_POR_PERFIL,
    TAXA_JUROS_ANUAL,
)

logger = logging.getLogger(__name__)


class FormSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = FormSubmissionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["Nome", "Profissao", "Contato"]
    ordering_fields = ["Criado_Em", "Nome", "Renda_Mensal"]
    ordering = ["-Criado_Em"]

    def get_queryset(self):
        return FormSubmission.objects.filter(user=self.request.user).order_by("-Criado_Em")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        data = request.data.copy()

        objetivos = data.get("Objetivos", [])
        if isinstance(objetivos, str):
            try:
                objetivos = json.loads(objetivos)
            except json.JSONDecodeError:
                objetivos = []

        data["Objetivos"] = objetivos
        serializer = self.get_serializer(data=data)

        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "errors": serializer.errors,
                    "received_data": {
                        k: str(v) for k, v in data.items() if k != "user"
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        return Response(calculate_score(form_data))

    @action(detail=False, methods=["get"], url_path="with-scores")
    def list_with_scores(self, request):
        try:
            submissions = self.get_queryset()
            serializer = SubmissionWithScoreSerializer(submissions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Erro em list_with_scores: {e}", exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"], url_path="relatorio-data")
    def relatorio_data(self, request, pk=None):
        try:
            submission = self.get_object()

            nascimento = submission.Nascimento
            if nascimento:
                hoje = date.today()
                idade = hoje.year - nascimento.year
                if (hoje.month, hoje.day) < (nascimento.month, nascimento.day):
                    idade -= 1
            else:
                idade = None

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

            objetivos_raw = submission.Objetivos
            if isinstance(objetivos_raw, str):
                try:
                    objetivos_raw = json.loads(objetivos_raw)
                except json.JSONDecodeError:
                    objetivos_raw = []

            form_data = {
                "financialAssets": submission.Patrimonio_Financeiro,
                "income": submission.Renda_Mensal,
                "incomeSource": submission.Fonte_Renda,
                "realEstateValue": submission.Patrimonio_Imobiliario,
                "realEstateCount": submission.Qtd_Imoveis,
                "succession": submission.Sucessao,
                "lifeInsurance": submission.Seguro,
                "disabilityInsurance": submission.Seguro_Invalidez,
                "corporateStructure": submission.Estrutura_Societaria,
                "risk": submission.Risco,
                "investFrequency": submission.Frequencia_Invest,
                "investPeriod": submission.Periodo_Invest,
                "preference": submission.Preferencia,
                "horizon": submission.Horizonte,
                "investAmount": submission.Valor_Investimento,
                "financialGoals": objetivos_raw,
                "monthlyExpenses": submission.Custo_Vida,
                "foreignInvestment": submission.Investimento_Exterior,
                "atendimento_preferencia": (
                    submission.get_Contato_display()
                    if submission.Contato
                    else "N/A"
                ),
            }

            perfil = determinar_perfil_investidor(form_data)
            capacidade = calcular_capacidade_poupanca(form_data)
            patrimonio = (
                to_float(form_data.get("financialAssets", 0))
                + to_float(form_data.get("realEstateValue", 0))
            )

            alocacoes = ALOCACOES_POR_PERFIL.get(
                perfil, ALOCACOES_POR_PERFIL["Moderado"]
            )

            # Processa objetivos
            objetivos_processados = processar_objetivos(
                objetivos_raw=objetivos_raw,
                capacidade_mensal=capacidade["mensal"],
                taxa_anual=TAXA_JUROS_ANUAL,
            )

            eficiencia_fiscal = recomendar_eficiencia_fiscal(form_data)

            # ============================================================
            # SEGUROS E PROTEÇÃO PATRIMONIAL - LÓGICA COMPLETA
            # ============================================================
            
            # 1. Mapeia seguros que o cliente JÁ POSSUI
            seguros_possui = {
                "seguro_vida": submission.Seguro == "YES",
                "seguro_invalidez": submission.Seguro_Invalidez == "YES",
                "planejamento_sucessorio": submission.Sucessao == "YES",
                "estrutura_societaria": submission.Estrutura_Societaria == "YES",
                "investimento_exterior": submission.Investimento_Exterior == "YES",
            }
            
            # 2. Lista de seguros contratados (para exibição)
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
            
            # 3. Calcula métricas de proteção
            total_seguros_contratados = len(seguros_contratados_lista)
            percentual_protecao = (total_seguros_contratados / 5) * 100
            
            # 4. Calcula patrimônio total e seguro de vida recomendado
            patrimonio_total = to_float(submission.Patrimonio_Financeiro) + to_float(submission.Patrimonio_Imobiliario)
            seguro_vida_recomendado_valor = patrimonio_total * 0.2
            renda_mensal = to_float(submission.Renda_Mensal)
            profissao = cliente.get("profissao", "").lower()
            
            # 5. Recomendações personalizadas de seguros (oportunidades)
            recomendacoes_personalizadas = []
            
            # 5.1 Seguro de Vida (sempre recomendado se não possui)
            if not seguros_possui["seguro_vida"]:
                recomendacoes_personalizadas.append({
                    "tipo": "Seguro de Vida",
                    "valor_recomendado": formatar_br(seguro_vida_recomendado_valor),
                    "motivo": f"Proteção financeira para sua família e patrimônio (20% do patrimônio total de {formatar_br(patrimonio_total)})",
                    "prioridade": "Alta",
                    "campo_model": "Seguro",
                })
            
            # 5.2 Seguro de Invalidez (se renda > R$ 10k)
            if not seguros_possui["seguro_invalidez"] and renda_mensal > 10000:
                recomendacoes_personalizadas.append({
                    "tipo": "Seguro de Invalidez",
                    "valor_recomendado": formatar_br(renda_mensal * 12 * 5),
                    "motivo": "Garantia de renda em caso de incapacidade para trabalhar",
                    "prioridade": "Alta",
                    "campo_model": "Seguro_Invalidez",
                })
            
            # 5.3 Seguro Empresarial para Sócios (se empresário ou investidor)
            eh_empresario = any(p in profissao for p in ["empresario", "socio", "empresário", "sócio", "investidor", "empreendedor", "business", "sócio"])
            
            if eh_empresario and not seguros_possui["estrutura_societaria"]:
                recomendacoes_personalizadas.append({
                    "tipo": "Seguro Empresarial para Sócios",
                    "valor_recomendado": "A ser calculado com base na participação societária",
                    "motivo": "Proteção da sua participação na empresa em caso de imprevistos",
                    "prioridade": "Média",
                    "campo_model": "Estrutura_Societaria",
                })
            
            # 5.4 DIT - Diária de Incapacidade Temporária (se profissional liberal/executivo)
            eh_profissional_liberal = any(p in profissao for p in ["executivo", "medico", "advogado", "médico", "engenheiro", "arquiteto", "dentista", "consultor", "gerente", "diretor", "procurador"])
            
            if eh_profissional_liberal and not seguros_possui["seguro_invalidez"]:
                recomendacoes_personalizadas.append({
                    "tipo": "DIT - Diária de Incapacidade Temporária",
                    "valor_recomendado": formatar_br(renda_mensal * 0.8),
                    "motivo": "Cobertura para períodos de incapacidade temporária, mantendo seu padrão de vida",
                    "prioridade": "Média",
                    "campo_model": "Seguro_Invalidez",
                })
            
            # 5.5 Planejamento Sucessório (se casado ou com filhos e não possui)
            estado_civil = cliente.get("estado_civil", "")
            tem_filhos = submission.Filhos != "CH_NONE" if submission.Filhos else False
            precisa_sucessao = (estado_civil in ["Casado", "União Estável", "CASADO", "UNIAO_ESTAVEL", "Casado(a)", "União Estável"] or tem_filhos)
            
            if precisa_sucessao and not seguros_possui["planejamento_sucessorio"]:
                recomendacoes_personalizadas.append({
                    "tipo": "Planejamento Sucessório",
                    "valor_recomendado": "Estrutura personalizada",
                    "motivo": "Proteção e transmissão eficiente do patrimônio para seus herdeiros, evitando inventário",
                    "prioridade": "Alta",
                    "campo_model": "Sucessao",
                })
            
            # 6. Flag de necessidade de sucessão (para alerta no relatório)
            necessidade_sucessao = precisa_sucessao and not seguros_possui["planejamento_sucessorio"]
            
            # 7. Seguros recomendados (backward compatibility)
            seguros_recomendados = recomendar_seguros(form_data, cliente)
            
            # 8. Texto de atendimento
            texto_atendimento = gerar_texto_atendimento(
                form_data.get("atendimento_preferencia", ""), perfil
            )

            # ============================================================
            # RESPONSE COMPLETO
            # ============================================================
            return Response({
                "cliente": cliente,
                "perfil": perfil,
                "capacidade_mensal": round(capacidade["mensal"], 2),
                "capacidade_mensal_fmt": formatar_br(capacidade["mensal"]),
                "capacidade_anual": round(capacidade["anual"], 2),
                "capacidade_anual_fmt": formatar_br(capacidade["anual"]),
                "patrimonio": round(patrimonio_total, 2),
                "patrimonio_fmt": formatar_br(patrimonio_total),
                "alocacoes": alocacoes,
                "objetivos": objetivos_processados,
                "seguros_recomendados": seguros_recomendados,
                "eficiencias": eficiencia_fiscal["recomendacoes"],
                "eficiencia_motivo": eficiencia_fiscal["motivo"],
                "seguro_vida": round(seguro_vida_recomendado_valor, 2),
                "seguro_vida_fmt": formatar_br(seguro_vida_recomendado_valor),
                "necessidade_sucessao": necessidade_sucessao,
                "texto_atendimento": texto_atendimento,
                "taxa_juros": f"{TAXA_JUROS_ANUAL * 100:.0f}%",
                "data_geracao": date.today().strftime("%B %Y").upper(),
                
                # Campos de seguros
                "seguros_contratados": seguros_possui,
                "seguros_contratados_lista": seguros_contratados_lista,
                "recomendacoes_seguros_personalizadas": recomendacoes_personalizadas,
                "total_seguros_contratados": total_seguros_contratados,
                "percentual_protecao": percentual_protecao,
                "possui_algum_seguro": total_seguros_contratados > 0,
                
                # Outros campos
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
                        "prazo_meses": int(obj.get("months", 12)),
                    }
                    for obj in objetivos_raw
                ],
                "expectativa": submission.Expectativa or "",  # O que você espera de um assessor?
                "nao_resolvido": submission.Nao_Resolvido or "",  
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
            return Response(
                {
                    "id": user.id,
                    "Nome": user.get_full_name() or user.username,
                    "email": user.email,
                },
                status=status.HTTP_200_OK,
            )
        return Response({"detail": "Não autenticado."}, status=status.HTTP_401_UNAUTHORIZED)


class RelatorioPDFViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="pdf/(?P<submission_id>[^/.]+)")
    def gerar_pdf(self, request, submission_id=None):
        try:
            submission = FormSubmission.objects.get(id=submission_id, user=request.user)

            view = FormSubmissionViewSet()
            view.request = request
            view.kwargs = {"pk": submission_id}
            response = view.relatorio_data(request, pk=submission_id)

            if response.status_code != 200:
                return Response(
                    {"error": "Erro ao gerar dados do relatório"},
                    status=response.status_code,
                )

            html_string = render_to_string(
                "relatorio_pdf.html",
                {
                    "data": response.data,
                    "STATIC_URL": settings.STATIC_URL,
                    "base_url": request.build_absolute_uri("/"),
                },
            )

            css_path = os.path.join(
                settings.BASE_DIR, "static", "css", "relatorio_pdf.css"
            )

            html = HTML(
                string=html_string,
                base_url=request.build_absolute_uri("/"),
            )

            if os.path.exists(css_path):
                with open(css_path, "r", encoding="utf-8") as css_file:
                    css_string = css_file.read()
                pdf_file = html.write_pdf(stylesheets=[CSS(string=css_string)])
            else:
                pdf_file = html.write_pdf()

            http_response = HttpResponse(pdf_file, content_type="application/pdf")
            http_response[
                "Content-Disposition"
            ] = f'attachment; filename="relatorio_{submission.Nome}_{submission.id}.pdf"'
            return http_response

        except FormSubmission.DoesNotExist:
            return Response(
                {"error": "Submission não encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Erro ao gerar PDF: {e}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )