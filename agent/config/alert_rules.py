import yaml
from typing import List
from pathlib import Path
from dataclasses import dataclass


@dataclass
class AlertRule:
    id: str
    name: str
    severity: str
    metric: str
    source: str
    condition: str
    threshold: float
    cooldown_sec: int
    description: str
    enabled: bool = True


def load_alert_rules(config_path: str = None) -> List[AlertRule]:
    """
    Load alert rules from YAML config file.

    Args:
        config_path: alert_rules.yaml path

    Returns:
        List[AlertRule]
    """
    if config_path is None:
        config_path = Path(__file__).parent / "alert_rules.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    rules_data = data.get("rules", [])
    rules: List[AlertRule] = []

    for r in rules_data:
        rule = AlertRule(
            id=r["id"],
            name=r.get("name", ""),
            severity=r.get("severity", "info"),
            metric=r["metric"],
            source=r.get("source", "1s"),
            condition=r["condition"],
            threshold=float(r["threshold"]),
            cooldown_sec=int(r.get("cooldown_sec", 60)),
            description=r.get("description", "").strip(),
            enabled=bool(r.get("enabled", True)),
        )

        rules.append(rule)

    return rules
