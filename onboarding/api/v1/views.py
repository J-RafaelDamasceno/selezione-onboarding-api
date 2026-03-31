import logging 
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import json

from onboarding.models import FormSubmission
from onboarding.api.v1.serializers import FormSubmissionSerializer
from .score_engine import calculate_score

logger = logging.getLogger(__name__)
  
from onboarding.api.v1.relatorio_weasyprint import gerar_relatorio_pdf_weasyprint


class FormSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = FormSubmissionSerializer
    permission_classes = [IsAuthenticated]

    # ==============================
    # QUERYSET
    # ==============================
    def get_queryset(self):
        return FormSubmission.objects.filter(user=self.request.user).order_by("-Criado_Em")

    # ==============================
    # SALVAR FORMULÁRIO
    # ==============================
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # ==============================
    # FILTROS
    # ==============================
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["Nome", "Profissao", "Contato"]
    ordering_fields = ["Criado_Em", "Nome", "Renda_Mensal"]
    ordering = ["-Criado_Em"]

    # ==============================
    # CRIAR FORMULÁRIO
    # ==============================
    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        print("\n" + "="*60)
        print("🔵 PAYLOAD RECEBIDO:")
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        print("="*60 + "\n")

        # converter objetivos para lista
        objetivos = data.get("Objetivos", [])
        if isinstance(objetivos, str):
            try:
                objetivos = json.loads(objetivos)
                print(f"✅ Objetivos convertido de string para: {objetivos}")
            except json.JSONDecodeError as e:
                print(f"❌ Erro ao converter Objetivos: {e}")
                objetivos = []
        data["Objetivos"] = objetivos

        # 🔥 ADICIONE: Log de todos os campos e seus tipos
        print("\n📋 CAMPOS E SEUS TIPOS:")
        for key, value in data.items():
            print(f"  {key}: {type(value).__name__} = {value}")

        serializer = self.get_serializer(data=data)
        
        # 🔥 ADICIONE: Validação manual para ver erros específicos
        if not serializer.is_valid():
            print("\n🔴 ERROS DE VALIDAÇÃO DO SERIALIZER:")
            print(json.dumps(serializer.errors, indent=2, ensure_ascii=False))
            print("="*60)
            
            # 🔥 RETORNE OS ERROS DETALHADOS NA RESPOSTA
            return Response({
                'status': 'error',
                'errors': serializer.errors,
                'received_data': {k: str(v) for k, v in data.items() if k not in ['user']}
            }, status=status.HTTP_400_BAD_REQUEST)
        
        print("\n✅ SERIALIZER VÁLIDO! Salvando...")
        self.perform_create(serializer)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ==============================
    # CALCULAR SCORE
    # ==============================
    @action(detail=True, methods=["get"])
    def score(self, request, pk=None):
        submission = self.get_object()

        # converter objetivos de string para lista
        main_focus = submission.Objetivos
        if isinstance(main_focus, str):
            try:
                main_focus = json.loads(main_focus)
            except json.JSONDecodeError:
                main_focus = []

        # preparar dados para a engine
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

    # ==============================
    # GERAR RELATÓRIO PDF (VERSÃO OTIMIZADA)
    # ==============================
    @action(detail=True, methods=["get"], url_path="relatorio")
    def relatorio(self, request, pk=None):
        """
        Gera o relatório PDF do cliente usando weasyprint (mais rápido)
        URL: /api/onboarding/{id}/relatorio/
        """
        try:
            submission = self.get_object()
            
            # Prepara os dados do cliente com LABELS
            cliente = {
                "nome": submission.Nome,
                "idade": submission.Nascimento.year if submission.Nascimento else None,
                "profissao": submission.Profissao_Outro if submission.Profissao == "JOB_OTHER" else submission.get_Profissao_display() if submission.Profissao else "N/A",
                "estado_civil": submission.get_Estado_Civil_display() if submission.Estado_Civil else "N/A",
                "tem_filhos": submission.Filhos != "CH_NONE" if submission.Filhos else False,
            }
            
            # Prepara os dados do formulário
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
            
            # 🔥 USAR A VERSÃO COM WEASYPRINT
            pdf_path = gerar_relatorio_pdf_weasyprint(cliente, form_data)
            
            return Response({
                'success': True,
                'pdf_path': pdf_path,
                'message': 'Relatório gerado com sucesso (weasyprint)'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    # ==============================
    # RETORNAR USUÁRIO LOGADO
    # ==============================
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