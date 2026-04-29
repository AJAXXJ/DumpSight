from html import escape


def build_crash_mail_payload(data: dict):
    """
  构建崩溃告警邮件内容。
    """
    if not data:
        raise ValueError("data is required")

    crash_type = data.get("crash_type") or "crash"

    if crash_type == "crash":
        return _build_crash_type_mail_payload(data)

    raise ValueError(f"unsupported crash_type: {crash_type}")


def _severity_meta(severity: str):
    """
  告警级别样式信息。
    """
    severity = (severity or "critical").lower()

    if severity == "critical":
        return {
            "label": "CRITICAL",
            "color": "#d93025",
            "bg": "#fce8e6",
            "border": "#f4b8b3",
        }

    if severity == "warning":
        return {
            "label": "WARNING",
            "color": "#b06000",
            "bg": "#fff4e5",
            "border": "#ffd699",
        }

    return {
        "label": "INFO",
        "color": "#1677ff",
        "bg": "#e6f4ff",
        "border": "#91caff",
    }


def _build_crash_type_mail_payload(data: dict):
    """
  crash_type=crash 的邮件构建逻辑（中文版本）。
    """
    rule = data.get("rule") or {}
    crash_info = data.get("crash_info") or {}

    client_id = escape(str(crash_info.get("client_id") or "未知客户端"))
    pid = escape(str(crash_info.get("pid") or "未知进程"))
    crash_time = escape(str(crash_info.get("crash_time") or "未知时间"))
    description = escape(str(crash_info.get("description") or "暂无崩溃描述"))
    root_cause = escape(str(crash_info.get("root_cause") or "暂无根因分析"))

    rule_id = escape(str(rule.get("id") or ""))
    rule_name = escape(str(rule.get("name") or "崩溃告警规则"))
    severity = str(rule.get("severity") or "critical").lower()
    meta = _severity_meta(severity)

    subject_prefix = data.get("subject_prefix") or "【DumpSight】崩溃告警"
    subject = f"{subject_prefix} [{meta['label']}] 客户端={client_id} 进程={pid}"

    body = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="margin:0; padding:0; background:#f5f7fa; font-family:Arial,'Microsoft YaHei',sans-serif; color:#1f2937;">
  <div style="max-width:760px; margin:0 auto; padding:24px 12px;">
    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:10px; overflow:hidden;">
      
      <div style="background:#111827; padding:22px 28px;">
        <div style="font-size:13px; color:#9ca3af; letter-spacing:0.08em;">DUMPSIGHT 告警系统</div>
        <div style="margin-top:8px; font-size:24px; font-weight:700; color:#ffffff;">
          崩溃告警通知
        </div>
      </div>

      <div style="padding:24px 28px;">
        <div style="margin-bottom:22px; padding:14px 16px; background:{meta['bg']}; border:1px solid {meta['border']}; border-radius:8px;">
          <span style="display:inline-block; padding:4px 10px; border-radius:999px; background:{meta['color']}; color:#ffffff; font-size:12px; font-weight:700;">
            {meta['label']}
          </span>
          <span style="margin-left:10px; font-size:14px; color:{meta['color']}; font-weight:600;">
            检测到进程崩溃
          </span>
        </div>

        <table style="width:100%; border-collapse:collapse; margin-bottom:22px;">
          <tr>
            <td style="width:34%; padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">规则 ID</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{rule_id}</td>
          </tr>
          <tr>
            <td style="padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">规则名称</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{rule_name}</td>
          </tr>
          <tr>
            <td style="padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">客户端 ID</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{client_id}</td>
          </tr>
          <tr>
            <td style="padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">进程 PID</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{pid}</td>
          </tr>
          <tr>
            <td style="padding:10px 12px; background:#f9fafb; border:1px solid #e5e7eb; color:#6b7280;">崩溃时间</td>
            <td style="padding:10px 12px; border:1px solid #e5e7eb;">{crash_time}</td>
          </tr>
        </table>

        <div style="margin-bottom:18px;">
          <div style="font-size:16px; font-weight:700; margin-bottom:8px;">崩溃描述</div>
          <div style="padding:14px 16px; background:#f9fafb; border:1px solid #e5e7eb; border-radius:8px; line-height:1.7;">
            {description}
          </div>
        </div>

        <div style="margin-bottom:22px;">
          <div style="font-size:16px; font-weight:700; margin-bottom:8px;">根因分析</div>
          <div style="padding:14px 16px; background:#fff7ed; border:1px solid #fed7aa; border-radius:8px; line-height:1.7; color:#7c2d12;">
            {root_cause}
          </div>
        </div>

        <div style="padding:14px 16px; background:#f0f7ff; border-left:4px solid #1677ff; border-radius:6px; font-size:13px; line-height:1.7; color:#1d4ed8;">
          建议操作：请检查崩溃进程状态，排查最近变更，重点关注 DPDK 内存管理与队列使用情况。
        </div>
      </div>

      <div style="padding:16px 28px; background:#f9fafb; border-top:1px solid #e5e7eb; color:#9ca3af; font-size:12px; line-height:1.6;">
        本邮件由 DumpSight 自动生成，请勿直接回复。
      </div>
    </div>
  </div>
</body>
</html>
""".strip()

    return {
        "to_addrs": data.get("to_addrs") or [],
        "cc_addrs": data.get("cc_addrs") or [],
        "subject": subject,
        "body": body,
        "content_type": "html",
    }
