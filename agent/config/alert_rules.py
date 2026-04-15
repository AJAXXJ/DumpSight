import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class AlertRule:
    id:               str
    name:             str
    severity:         str           # critical | warning | info
    metric:           str           # 对应 _FEATURE_PATH_MAP 的键名
    condition:        str           # gt | lt | gte | lte | eq | ref_ratio | ref_delta
    threshold:        float
    cooldown_sec:     int
    description:      str
    escalate_to_fault: bool = False
    enabled:          bool  = True


def load_alert_rules(config_path: str = None) -> List[AlertRule]:
    """
    从 YAML 加载预警规则，metric 对应 log_feature 的 _FEATURE_PATH_MAP 键名。
    """
    if config_path is None:
        config_path = Path(__file__).parent / "alert_rules.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return [
        AlertRule(
            id                = r["id"],
            name              = r.get("name", ""),
            severity          = r.get("severity", "info"),
            metric            = r["metric"],
            condition         = r["condition"],
            threshold         = float(r["threshold"]),
            cooldown_sec      = int(r.get("cooldown_sec", 60)),
            description       = r.get("description", "").strip(),
            escalate_to_fault = bool(r.get("escalate_to_fault", False)),
            enabled           = bool(r.get("enabled", True)),
        )
        for r in data.get("rules", [])
    ]
