import os
import sys
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path


def get_exe_dir() -> str:
    """Get the directory of the current executable or script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


EXE_DIR = get_exe_dir()


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
        config_path = os.path.join(EXE_DIR, "agent-config.yaml")

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
