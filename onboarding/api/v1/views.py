import logging 
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
import json
import os

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
            
            # Lê o conteúdo do arquivo antes do cleanup deletar
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            
            # Deleta o arquivo após ler
            try:
                os.remove(pdf_path)
            except Exception:
                pass
            
            from django.http import HttpResponse
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