import logging 
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse, HttpResponse
import json
import os
from datetime import date

from onboarding.models import FormSubmission
from onboarding.api.v1.serializers import FormSubmissionSerializer
from .score_engine import calculate_score

logger = logging.getLogger(__name__)
  
from onboarding.api.v1.relatorio_weasyprint import gerar_relatorio_pdf_weasyprint


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

    @action(detail=True, methods=["get"], url_path="relatorio")
    def relatorio(self, request, pk=None):
        try:
            submission = self.get_object()
            
            cliente = {
                "nome": submission.Nome,
                "idade": submission.Nascimento.year if submission.Nascimento else None,
                "profissao": submission.Profissao_Outro if submission.Profissao == "JOB_OTHER" else submission.get_Profissao_display() if submission.Profissao else "N/A",
                "estado_civil": submission.get_Estado_Civil_display() if submission.Estado_Civil else "N/A",
                "tem_filhos": submission.Filhos != "CH_NONE" if submission.Filhos else False,
            }
            
            objetivos = submission.Objetivos
            if isinstance(objetivos, str):
                try:
                    objetivos = json.loads(objetivos)
                except json.JSONDecodeError:
                    objetivos = []
            
            form_data = {
                "financialAssets": submission.Patrimonio_Financeiro,
                "income": submission.Renda_Mensal,
                "incomeSource": submission.get_Fonte_Renda_display() if submission.Fonte_Renda else "N/A",
                "realEstateValue": submission.Patrimonio_Imobiliario,
                "realEstateCount": submission.Qtd_Imoveis,
                "succession": submission.get_Sucessao_display() if submission.Sucessao else "N/A",
                "lifeInsurance": submission.get_Seguro_display() if submission.Seguro else "N/A",
                "disabilityInsurance": submission.get_Seguro_Invalidez_display() if submission.Seguro_Invalidez else "N/A",
                "corporateStructure": submission.get_Estrutura_Societaria_display() if submission.Estrutura_Societaria else "N/A",
                "risk": submission.Risco,
                "investFrequency": submission.Frequencia_Invest,
                "investPeriod": submission.Periodo_Invest,
                "preference": submission.Preferencia,
                "horizon": submission.Horizonte,
                "investAmount": submission.Valor_Investimento,
                "financialGoals": objetivos,
                "monthlyExpenses": submission.Custo_Vida,
                "atendimento_preferencia": submission.get_Contato_display() if submission.Contato else "N/A",
            }
            
            pdf_path = gerar_relatorio_pdf_weasyprint(cliente, form_data)
            
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            
            try:
                os.remove(pdf_path)
            except Exception:
                pass
            
            nome_cliente = submission.Nome or "cliente"
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="relatorio_{nome_cliente}.pdf"'
            response['Content-Length'] = len(pdf_content)
            return response
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="relatorio-data")
    def relatorio_data(self, request, pk=None):
        try:
            from onboarding.api.v1.relatorio_weasyprint import (
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
            seguros     = recomendar_seguros(form_data, cliente)
            eficiencias = recomendar_eficiencia_fiscal(form_data)
            seguro_vida = patrimonio * 0.2

            estado_civil = cliente.get("estado_civil", "")
            tem_filhos   = submission.Filhos != "CH_NONE" if submission.Filhos else False
            necessidade_sucessao = (
                estado_civil in ["Casado", "União Estável", "CASADO", "UNIAO_ESTAVEL"]
                or tem_filhos
            ) and submission.Sucessao != "YES"

            texto_atendimento = gerar_texto_atendimento(
                form_data.get("atendimento_preferencia", ""), perfil
            )

            return Response({
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
                "seguros":               seguros,
                "eficiencias":           eficiencias,
                "seguro_vida":           round(seguro_vida, 2),
                "seguro_vida_fmt":       formatar_br(seguro_vida),
                "necessidade_sucessao":  necessidade_sucessao,
                "texto_atendimento":     texto_atendimento,
                "taxa_juros":            f"{TAXA_JUROS_ANUAL * 100:.0f}%",
                "data_geracao":          date.today().strftime("%B %Y").upper(),
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