def calculate_score(form_data: dict) -> dict:
    """
    Score baseado no onboarding estratégico (4 blocos) - versão corrigida
    """

    # =========================
    # HELPERS
    # =========================
    def to_float(value):
        try:
            return float(value)
        except:
            return 0.0

    # =========================
    # BLOCO 1 — POTENCIAL DE AUM (0–25)
    # =========================
    assets = to_float(form_data.get("financialAssets"))

    if assets <= 500_000:
        aum = 5
    elif assets <= 2_000_000:
        aum = 10
    elif assets <= 10_000_000:
        aum = 20
    else:
        aum = 25

    # =========================
    # BLOCO 2 — GERAÇÃO FUTURA (0–25)
    # =========================
    income = to_float(form_data.get("income"))

    if income <= 30_000:
        generation = 5
    elif income <= 80_000:
        generation = 10
    elif income <= 200_000:
        generation = 20
    else:
        generation = 25

    # bônus por fonte de renda
    income_source = form_data.get("incomeSource")
    if income_source in ["SRC_PROFIT", "SRC_RENT", "SRC_RETIREMENT"]:
        generation += 5

    generation = min(generation, 25)

    # =========================
    # BLOCO 3 — COMPLEXIDADE (0–25) ✅ CORRIGIDO
    # =========================
    criteria_count = 0

    real_estate_value = to_float(form_data.get("realEstateValue"))

    # 1) Patrimônio imobiliário > 1M
    if real_estate_value > 1_000_000:
        criteria_count += 1

    # 2) Planejamento sucessório
    if form_data.get("succession") == "YES":
        criteria_count += 1

    # 3) Seguros
    if form_data.get("lifeInsurance") == "YES" or form_data.get("disabilityInsurance") == "YES":
        criteria_count += 1

    # 4) Estrutura patrimonial organizada
    if form_data.get("corporateStructure") == "YES":
        criteria_count += 1

    # cálculo correto
    complexity = criteria_count * 5

    # 🔥 FIX: garantir teto real de 25
    if criteria_count == 4:
        complexity = 25

    # =========================
    # BLOCO 4 — MATURIDADE (0–25)
    # =========================
    maturity = 0

    risk = form_data.get("risk")
    if risk == "RISK_BUY":
        maturity += 25
    elif risk == "RISK_HOLD":
        maturity += 15
    elif risk == "RISK_REDUCE":
        maturity += 5

    # investe mensalmente → +5
    if form_data.get("investFrequency") == "YES" and form_data.get("investPeriod") == "PER_MONTH":
        maturity += 5

    # foco em crescimento → +5
    if form_data.get("preference") == "PREF_GROWTH":
        maturity += 5

    maturity = min(maturity, 25)

    # =========================
    # TOTAL
    # =========================
    total = aum + generation + complexity + maturity

    # =========================
    # CLASSIFICAÇÃO FINAL
    # =========================
    if total <= 40:
        profile = "Growth"
        description = [
            "Ainda acumulando",
            "Foco em educação financeira",
            "Ticket médio baixo",
            "Atendimento mais padronizado",
        ]
    elif total <= 65:
        profile = "Expansão"
        description = [
            "Começando a estruturar patrimônio",
            "Potencial de crescimento relevante",
            "Pode evoluir para Private em 2–3 anos",
        ]
    elif total <= 85:
        profile = "Private"
        description = [
            "Alta receita potencial",
            "Complexidade relevante",
            "Atendimento consultivo estruturado",
        ]
    else:
        profile = "Estruturado"
        description = [
            "Multi-estratégia",
            "Perfil empresarial sofisticado",
            "Demanda planejamento sucessório e tributário",
            "Atendimento altamente personalizado",
        ]

    # =========================
    # NÍVEIS TEXTUAIS
    # =========================
    if criteria_count >= 3:
        complexity_level = "Alta"
    elif criteria_count >= 1:
        complexity_level = "Moderada"
    else:
        complexity_level = "Baixa"

    if maturity >= 20:
        maturity_level = "Alta"
    elif maturity >= 10:
        maturity_level = "Moderada"
    else:
        maturity_level = "Baixa"

    # =========================
    # OUTPUT FINAL (FRONT READY)
    # =========================
    return {
        "total": total,
        "profile": profile,
        "description": description,
        "levels": {
            "complexity": complexity_level,
            "maturity": maturity_level,
        },
        "breakdown": {
            "aum": aum,
            "generation": generation,
            "complexity": complexity,
            "maturity": maturity,
        },
    }