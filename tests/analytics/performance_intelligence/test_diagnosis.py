from src.solar_platform.analytics.performance_intelligence.diagnosis import build_evidence_pack

def test_build_evidence_pack():
    pack = build_evidence_pack(
        site_name="Newfold Farm",
        event_type="curtailment_candidate",
        lost_energy_kwh=30.0,
        revenue_loss_gbp=4.50
    )
    assert pack["site"] == "Newfold Farm"
    assert "curtailment" in pack["event_type"]
    assert pack["estimated_loss_kwh"] == 30.0
