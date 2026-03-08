from typing import Dict, Any

def build_evidence_pack(site_name: str, event_type: str, lost_energy_kwh: float, revenue_loss_gbp: float) -> Dict[str, Any]:
    """Builds the JSON evidence pack to be sent to the LLM."""
    return {
        "site": site_name,
        "event_type": event_type,
        "estimated_loss_kwh": lost_energy_kwh,
        "estimated_revenue_loss_gbp": revenue_loss_gbp,
        "confidence": 0.90
    }
