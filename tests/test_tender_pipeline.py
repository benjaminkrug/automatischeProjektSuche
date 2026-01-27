"""Unit tests for tender pipeline components."""

import pytest
from datetime import datetime, timedelta

# CPV Filter tests
from app.sourcing.cpv_filter import (
    passes_cpv_filter,
    normalize_cpv_code,
    get_cpv_code_description,
)

# Tender Filter tests
from app.sourcing.tender_filter import (
    analyze_tech_requirements,
    detect_procedure_type,
    extract_award_criteria,
    check_accessibility_requirements,
    check_security_requirements,
    check_consortium_suitability,
    extract_revenue_requirement,
    check_eligibility,
    score_tender,
)

# Client DB tests
from app.sourcing.client_db import (
    normalize_client_name,
    detect_sector,
)


class TestCpvFilter:
    """Tests for CPV code filtering."""

    def test_normalize_cpv_code_standard(self):
        """Test normalizing standard 8-digit CPV code."""
        assert normalize_cpv_code("72200000") == "72200000"

    def test_normalize_cpv_code_with_check_digit(self):
        """Test normalizing CPV code with check digit."""
        assert normalize_cpv_code("72200000-7") == "72200000"

    def test_normalize_cpv_code_partial(self):
        """Test normalizing partial CPV code."""
        assert normalize_cpv_code("722") == "72200000"

    def test_passes_cpv_filter_relevant_code(self):
        """Test filter passes with relevant CPV code."""
        result = passes_cpv_filter(["72212900"])  # Webanwendungen
        assert result.passes is True
        assert result.bonus_score > 0

    def test_passes_cpv_filter_excluded_code(self):
        """Test filter rejects with only excluded CPV code."""
        result = passes_cpv_filter(["48000000"])  # Lizenzverkauf
        assert result.passes is False

    def test_passes_cpv_filter_no_codes(self):
        """Test filter passes through with no CPV codes."""
        result = passes_cpv_filter(None)
        assert result.passes is True
        assert result.bonus_score == 0

    def test_passes_cpv_filter_mixed_codes(self):
        """Test filter with both relevant and excluded codes."""
        result = passes_cpv_filter(["72212900", "48000000"])
        assert result.passes is True  # Relevant code takes precedence

    def test_get_cpv_code_description(self):
        """Test getting CPV code description."""
        desc = get_cpv_code_description("72200000")
        assert desc is not None
        assert "Software" in desc


class TestTenderFilter:
    """Tests for tender scoring and filtering."""

    def test_analyze_tech_requirements_webapp(self):
        """Test detection of web application requirement."""
        description = "Entwicklung einer Webanwendung für das Bürgerportal"
        result = analyze_tech_requirements(description)
        assert result.requires_webapp is True
        assert result.webapp_evidence is not None

    def test_analyze_tech_requirements_mobile(self):
        """Test detection of mobile app requirement."""
        description = "Entwicklung einer iOS und Android App für Bürgerservice"
        result = analyze_tech_requirements(description)
        assert result.requires_mobile is True
        assert result.mobile_evidence is not None

    def test_analyze_tech_requirements_tech_stack(self):
        """Test detection of tech stack keywords."""
        description = "React Frontend mit Node.js Backend und PostgreSQL Datenbank"
        result = analyze_tech_requirements(description)
        assert "react" in result.tech_stack_matches
        assert "node.js" in result.tech_stack_matches
        assert "postgresql" in result.tech_stack_matches

    def test_analyze_tech_requirements_no_match(self):
        """Test no match when irrelevant description."""
        description = "Lieferung von Büromaterialien und Schreibwaren"
        result = analyze_tech_requirements(description)
        assert result.requires_webapp is False
        assert result.requires_mobile is False

    def test_detect_procedure_verhandlungsverfahren(self):
        """Test detection of Verhandlungsverfahren."""
        description = "Das Verhandlungsverfahren mit Teilnahmewettbewerb wird durchgeführt."
        result = detect_procedure_type(description)
        assert result == "verhandlungsverfahren"

    def test_detect_procedure_offenes_verfahren(self):
        """Test detection of offenes Verfahren."""
        description = "Es wird ein offenes Verfahren nach § 15 VgV durchgeführt."
        result = detect_procedure_type(description)
        assert result == "offenes_verfahren"

    def test_detect_procedure_unknown(self):
        """Test unknown procedure type."""
        description = "Ausschreibung für Softwareentwicklung"
        result = detect_procedure_type(description)
        assert result == "unknown"

    def test_extract_award_criteria_quality_focused(self):
        """Test extraction of quality-focused award criteria."""
        text = "Zuschlagskriterien: Preis 30%, Qualität 70%"
        result = extract_award_criteria(text)
        assert result.price_weight == 30
        assert result.quality_weight == 70
        assert result.favors_quality is True

    def test_extract_award_criteria_price_focused(self):
        """Test extraction of price-focused award criteria."""
        text = "Zuschlagskriterien: Preis 80%, Konzept 20%"
        result = extract_award_criteria(text)
        assert result.price_weight == 80
        assert result.favors_quality is False

    def test_check_accessibility_wcag(self):
        """Test detection of WCAG requirements."""
        description = "Die Anwendung muss WCAG 2.1 AA konform sein."
        result = check_accessibility_requirements(description)
        assert "wcag_2.1_aa" in result.required
        assert result.can_deliver is True

    def test_check_accessibility_bitv(self):
        """Test detection of BITV requirements."""
        description = "Barrierefreiheit nach BITV 2.0 ist erforderlich."
        result = check_accessibility_requirements(description)
        assert "bitv_2.0" in result.required

    def test_check_security_iso27001(self):
        """Test detection of ISO 27001 requirement."""
        description = "Der Auftragnehmer muss ISO 27001 zertifiziert sein."
        result = check_security_requirements(description)
        assert "iso_27001" in result.required
        assert "iso_27001" in result.blockers
        assert result.can_deliver is False

    def test_check_security_dsgvo(self):
        """Test detection of DSGVO requirement."""
        description = "Verarbeitung personenbezogener Daten nach DSGVO."
        result = check_security_requirements(description)
        assert "dsgvo_konform" in result.required
        assert result.can_deliver is True

    def test_check_consortium_allowed(self):
        """Test consortium is allowed by default."""
        description = "Ausschreibung für Softwareentwicklung"
        result = check_consortium_suitability(description)
        assert result.consortium_allowed is True

    def test_check_consortium_not_allowed(self):
        """Test detection of consortium prohibition."""
        description = "Bietergemeinschaften sind nicht zugelassen."
        result = check_consortium_suitability(description)
        assert result.consortium_allowed is False

    def test_check_consortium_sme_friendly(self):
        """Test detection of SME-friendly tender."""
        description = "Losaufteilung zur Förderung von KMU."
        result = check_consortium_suitability(description)
        assert result.sme_friendly is True

    def test_extract_revenue_requirement_millions(self):
        """Test extraction of revenue requirement in millions."""
        text = "Mindestumsatz: 2 Mio EUR"
        result = extract_revenue_requirement(text)
        assert result == 2_000_000

    def test_extract_revenue_requirement_thousands(self):
        """Test extraction of revenue requirement in thousands."""
        text = "Jahresumsatz mindestens 500 Tsd EUR"
        result = extract_revenue_requirement(text)
        assert result == 500_000

    def test_check_eligibility_pass(self):
        """Test eligibility check passes for simple tender."""
        description = "Entwicklung einer Webanwendung"
        status, notes = check_eligibility(description)
        assert status == "pass"

    def test_check_eligibility_fail_iso(self):
        """Test eligibility fails for ISO 27001 requirement."""
        description = "Der Bieter muss eine ISO 27001 Zertifizierung nachweisen."
        status, notes = check_eligibility(description)
        assert status == "fail"
        assert "ISO 27001" in notes

    def test_check_eligibility_unclear(self):
        """Test eligibility unclear for generic certification mention."""
        description = "Nachweis entsprechender Zertifizierungen erforderlich."
        status, notes = check_eligibility(description)
        assert status == "unclear"

    def test_score_tender_webapp(self):
        """Test scoring a web application tender."""
        description = "Entwicklung einer Webanwendung für das Bürgerportal mit React."
        score = score_tender(
            description=description,
            budget_max=100000,
            tender_deadline=datetime.now() + timedelta(days=30),
        )
        assert score.skip is False
        assert score.tech_score >= 20  # Webapp found
        assert score.normalized > 0

    def test_score_tender_no_tech(self):
        """Test scoring skips tender without tech requirements."""
        description = "Lieferung von Büromaterialien"
        score = score_tender(description=description)
        assert score.skip is True
        assert "Web/Mobile" in score.skip_reason

    def test_score_tender_budget_optimal(self):
        """Test budget scoring in optimal range."""
        description = "Entwicklung einer Webanwendung"
        score = score_tender(
            description=description,
            budget_max=100000,  # In optimal range 50k-250k
        )
        assert score.volume_score == 15

    def test_score_tender_deadline_sufficient(self):
        """Test deadline scoring with sufficient time."""
        description = "Entwicklung einer Webanwendung"
        score = score_tender(
            description=description,
            tender_deadline=datetime.now() + timedelta(days=30),
        )
        assert score.deadline_score == 10


class TestClientDb:
    """Tests for client database functions."""

    def test_normalize_client_name_basic(self):
        """Test basic client name normalization."""
        result = normalize_client_name("Bundesamt für Sicherheit GmbH")
        assert "bundesamt" in result
        assert "sicherheit" in result
        assert "gmbh" not in result

    def test_normalize_client_name_whitespace(self):
        """Test whitespace handling in normalization."""
        result = normalize_client_name("  Stadt   München  ")
        assert result == "münchen"

    def test_detect_sector_bund(self):
        """Test detection of federal sector."""
        result = detect_sector("Bundesministerium für Digitales")
        assert result == "bund"

    def test_detect_sector_land(self):
        """Test detection of state sector."""
        result = detect_sector("Landesamt für Geoinformation Bayern")
        assert result == "land"

    def test_detect_sector_kommune(self):
        """Test detection of municipal sector."""
        result = detect_sector("Stadt München")
        assert result == "kommune"

    def test_detect_sector_eu(self):
        """Test detection of EU sector."""
        result = detect_sector("Europäische Kommission")
        assert result == "eu"

    def test_detect_sector_unknown(self):
        """Test unknown sector detection."""
        result = detect_sector("ACME Corp")
        assert result == "unknown"


class TestIntegration:
    """Integration tests for tender pipeline."""

    def test_full_scoring_workflow(self):
        """Test complete scoring workflow for a realistic tender."""
        description = """
        Ausschreibung: Entwicklung eines Bürgerportals

        Gegenstand: Entwicklung einer modernen Webanwendung für Bürgerservices.
        Die Anwendung soll mit React im Frontend und einer REST-API im Backend
        entwickelt werden. Mobile Nutzung über responsive Design erforderlich.

        Vergabeart: Verhandlungsverfahren mit Teilnahmewettbewerb

        Zuschlagskriterien: Preis 40%, Konzept 60%

        Barrierefreiheit: Die Anwendung muss BITV 2.0 konform sein.

        Angebotsfrist: 30 Tage
        """

        score = score_tender(
            description=description,
            budget_max=150000,
            tender_deadline=datetime.now() + timedelta(days=30),
        )

        # Should score well
        assert score.skip is False
        assert score.tech_score >= 20  # Webapp detected
        assert score.procedure_score > 0  # Verhandlungsverfahren
        assert score.award_criteria_score > 0  # Quality focused
        assert score.accessibility_score > 0  # BITV can be delivered
        assert score.normalized >= 50  # Should be above reject threshold

    def test_blocking_security_requirement(self):
        """Test that blocking security requirements are detected."""
        description = """
        Entwicklung einer Webanwendung.
        Der Bieter muss nach ISO 27001 zertifiziert sein.
        """

        score = score_tender(description=description)

        # Should be blocked
        assert score.skip is True
        assert "Sicherheitsanforderung" in score.skip_reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
