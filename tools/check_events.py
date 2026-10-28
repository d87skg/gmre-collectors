# -*- coding: utf-8 -*-
# tools/check_events.py
import yaml
import os
from datetime import datetime, date
import logging

logger = logging.getLogger("EventCalendar")

def check_upcoming_events(config_path: str = "config/events_calendar.yaml", warning_threshold: int = 3) -> list:
    if not os.path.exists(config_path):
        # 兜底：尝试用绝对路径
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'events_calendar.yaml')
        if not os.path.exists(config_path):
            return []

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception:
        return []

    events = data.get("events", [])
    today = date.today()
    triggered_warnings = []

    for event in events:
        event_name = event.get("name")
        event_date_str = event.get("date")
        
        try:
            event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        delta_days = (event_date - today).days
        if 0 <= delta_days <= warning_threshold:
            warning_msg = f"⚠️ 宏观事件倒计时: 距离 {event_name} ({event_date_str}) 还有 {delta_days} 天，建议降低杠杆。"
            print(warning_msg)
            triggered_warnings.append(warning_msg)

    return triggered_warnings

if __name__ == "__main__":
    check_upcoming_events()