# -*- coding: utf-8 -*-
"""core/errors.py - 数据面异常分级（v4.2: 代理标记透传版）

设计目标：**代理层可以抛异常，但绝不允许主程序被卡死**。
三档处置：
    P0 BLOCK    -> 阻断出报：打印原因、退出码 4
    P1 DEGRADE  -> 降级：该指标取不到值，下沉为 UNKNOWN
    P2 WARN     -> 仅告警：打印告警，数值照常使用

v4.2 新增：
  - preflight(probe) 的 probe 可返回 series_used，用于标识别名/代理链
    （如 HY_OAS 通过 HY_SPREAD 代理读取）
  - ok 列表透出 series_used / proxy_used
  - print_preflight 显式打印代理条目，避免"前置体检 MISSING、下游 OK"的分裂
"""
import contextlib
from datetime import datetime, date

from core import units as _units

# ---------------------------------------------------------------- severity
P0 = 'P0'
P1 = 'P1'
P2 = 'P2'

SEVERITY_ACTION = {P0: 'BLOCK', P1: 'DEGRADE', P2: 'WARN'}
SEVERITY_LABEL = {
    P0: '⛔ P0 阻断出报',
    P1: '⚠️ P1 降级为 UNKNOWN',
    P2: 'ℹ️ P2 仅展示告警',
}

# ---------------------------------------------------------------- SLA
SLA_DAILY = 3
SLA_RATES = 2
SLA_WEEKLY = 8
SLA_MONTHLY = 45

SERIES_POLICY = {cid: (e['sla'], e['severity']) for cid, e in _units.REGISTRY.items()}
DEFAULT_POLICY = (_units.DEFAULT_ENTRY['sla'], _units.DEFAULT_ENTRY['severity'])


def policy_for(series_id):
    """任意叫法 -> (sla, severity)。别名会先归一成 canonical id。"""
    cid = _units.canonical_id(series_id)
    return SERIES_POLICY.get(cid, DEFAULT_POLICY)


def days_between(obs_date, asof=None):
    """obs_date -> asof 的自然日差。无法解析返回 None。"""
    return _units.days_lag(obs_date, asof)


def _parse_date(s):
    s = str(s).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d', '%Y%m%d'):
        try:
            return datetime.strptime(s[:len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


# ---------------------------------------------------------------- 异常类型
class DataError(Exception):
    """所有数据面异常的基类。severity 由所属序列的 policy 决定。"""

    severity = P1
    kind = 'DATA'

    def __init__(self, series_id, message='', *, severity=None, obs_date=None,
                 days_lag=None, sla_days=None, source=None, context=None):
        self.series_id = series_id
        self.obs_date = obs_date
        self.days_lag = days_lag
        self.sla_days = sla_days
        self.source = source
        self.context = context or {}
        if severity is not None:
            self.severity = severity
        super().__init__(message or self.describe())

    @property
    def action(self):
        return SEVERITY_ACTION.get(self.severity, 'DEGRADE')

    def describe(self):
        return f'[{self.kind}] {self.series_id}'

    def to_dict(self):
        return {
            'kind': self.kind, 'series_id': self.series_id,
            'severity': self.severity, 'action': self.action,
            'obs_date': self.obs_date, 'days_lag': self.days_lag,
            'sla_days': self.sla_days, 'source': self.source,
            'message': str(self), 'context': self.context,
        }


class DataStaleError(DataError):
    """数据陈旧：days_lag > SLA。"""

    kind = 'STALE'

    def __init__(self, series_id, days_lag, sla_days, *, obs_date=None,
                 source=None, severity=None, context=None):
        sla, sev = policy_for(series_id)
        super().__init__(
            series_id,
            f'{series_id} 数据陈旧：最新观测日 {obs_date}，滞后 {days_lag} 天 > SLA {sla_days} 天',
            severity=severity or sev, obs_date=obs_date, days_lag=days_lag,
            sla_days=sla_days, source=source, context=context)


class DataUnitError(DataError):
    """量纲/值域异常：数值超出该序列 canonical 单位的合理区间。"""

    kind = 'UNIT'
    severity = P1

    def __init__(self, series_id, value, lo, hi, *, unit=None, source=None,
                 obs_date=None, severity=None, context=None):
        super().__init__(
            series_id,
            f'{series_id} 量纲异常：value={value} 超出 {unit or "canonical"} 合理区间 [{lo}, {hi}]',
            severity=severity or self.severity, obs_date=obs_date, source=source,
            context=dict(context or {}, value=value, lo=lo, hi=hi, unit=unit))


class DataMissingError(DataError):
    """序列完全无数据（表内不存在该 series_id，且别名链亦无）。"""

    kind = 'MISSING'

    def __init__(self, series_id, *, severity=None, context=None):
        sla, sev = policy_for(series_id)
        super().__init__(series_id, f'{series_id} 库内无任何数据',
                         severity=severity or sev, sla_days=sla, context=context)


class DataQualityError(DataError):
    """其它质量问题（观测日无法解析、schema 不符等）。"""

    kind = 'QUALITY'
    severity = P1


# ---------------------------------------------------------------- 三档处置
def triage(exc):
    """把一个异常判定成处置动作。非 DataError 一律视为 P1。"""
    if not isinstance(exc, DataError):
        return {'action': 'DEGRADE', 'severity': P1, 'kind': 'UNKNOWN',
                'series_id': None, 'message': str(exc), 'exc': exc,
                'obs_date': None, 'days_lag': None, 'sla_days': None}
    d = exc.to_dict()
    d['exc'] = exc
    return d


def format_error(exc, width=64):
    d = triage(exc)
    icon = SEVERITY_LABEL.get(d['severity'], '⚠️')
    lines = [
        '┌' + '─' * width + '┐',
        f'│  {icon}',
        f'│  series : {d["series_id"]}',
        f'│  kind   : {d["kind"]}    severity: {d["severity"]}    action: {d["action"]}',
        f'│  detail : {d["message"]}',
    ]
    if d.get('obs_date'):
        lines.append(f'│  obs    : {d["obs_date"]}   lag={d.get("days_lag")}d'
                     f'  SLA={d.get("sla_days")}d')
    lines.append('└' + '─' * width + '┘')
    return '\n'.join(lines)


def handle(exc, out=print):
    """入口级处置。返回进程退出码。"""
    d = triage(exc)
    out('')
    out(format_error(exc))
    if d['action'] == 'BLOCK':
        out('')
        out('⛔ 数据面 P0 异常：本次不出报。')
        out('   Gate 未生成，晨报未推送，预测日志未归档。')
        out('   处理建议：先恢复官方源（data_correction / NYFed / Treasury），再重跑。')
        return 4
    if d['action'] == 'DEGRADE':
        out(f'   ↳ 已降级：{d["series_id"] or "该指标"} 本次按 UNKNOWN 参与计算。')
        return 0
    out(f'   ↳ 仅告警：{d["series_id"] or "该指标"} 数值照常使用，请人工留意。')
    return 0


@contextlib.contextmanager
def capture(out=print):
    """在某个计算段内兜住数据异常。"""
    try:
        yield
    except DataError as e:
        if e.severity == P0:
            raise
        out(format_error(e))
        out(f'   ↳ {SEVERITY_LABEL.get(e.severity, "")}：本段继续执行。')


# ---------------------------------------------------------------- preflight
def preflight(probe, asof=None, series=None):
    """出报前的数据面体检。

    probe(series_id) -> {
        'obs_date': 'YYYY-MM-DD',
        'series_used': 'xxx',        # 可选；别名/代理链实际命中的 series_id
        'source': '...',             # 可选
        'value': ...                 # 可选
    } | None

    返回 {
        'asof': ..., 'block': [...], 'degrade': [...], 'warn': [...], 'ok': [...],
        'verdict': 'BLOCK' | 'DEGRADED' | 'WARN' | 'OK'
    }
    ok 列表每条包含 series_used / proxy_used，用于区分"直接命中"与"代理命中"。
    """
    asof = asof or datetime.now().strftime('%Y-%m-%d')
    series = series or list(SERIES_POLICY)
    result = {'asof': asof, 'block': [], 'degrade': [], 'warn': [], 'ok': []}

    for sid in series:
        sla, _sev = policy_for(sid)
        try:
            info = probe(sid)
            if not info or not info.get('obs_date'):
                raise DataMissingError(sid)
            lag = days_between(info['obs_date'], asof)
            if lag is None:
                raise DataQualityError(
                    sid, f'{sid} 观测日无法解析: {info.get("obs_date")}')
            if lag > sla:
                raise DataStaleError(sid, lag, sla, obs_date=info['obs_date'],
                                     source=info.get('source'))
        except DataError as e:
            bucket = {P0: 'block', P1: 'degrade', P2: 'warn'}[e.severity]
            result[bucket].append(e.to_dict())
        else:
            used = info.get('series_used', sid)
            result['ok'].append({
                'series_id': sid,
                'obs_date': info['obs_date'],
                'days_lag': lag,
                'sla_days': sla,
                'series_used': used,
                'proxy_used': used != sid,
            })

    result['verdict'] = ('BLOCK' if result['block'] else
                         'DEGRADED' if result['degrade'] else
                         'WARN' if result['warn'] else 'OK')
    return result


def _lag_text(item):
    """block/degrade/warn 条目的 lag 文案。缺失序列没有 lag，显示 MISSING。"""
    lag = item.get('days_lag')
    return 'MISSING' if lag is None else f'lag={lag}d'


def print_preflight(result, out=print, width=64):
    out('┌' + '─' * width + '┐')
    out(f'│  🩺 数据面前置体检  asof={result["asof"]}   verdict={result["verdict"]}')
    out(f'│  ok={len(result["ok"])}  degrade={len(result["degrade"])}  '
        f'warn={len(result["warn"])}  block={len(result["block"])}')
    for i in result['block']:
        out(f'│  ⛔ P0 {i["series_id"]:18s} {_lag_text(i):>8s} > SLA {i["sla_days"]}d'
            f'  obs={i["obs_date"]}')
    for i in result['degrade']:
        out(f'│  ⚠️ P1 {i["series_id"]:18s} {_lag_text(i):>8s} > SLA {i["sla_days"]}d'
            f'  -> 降级 UNKNOWN')
    for i in result['warn']:
        out(f'│  ℹ️ P2 {i["series_id"]:18s} {_lag_text(i):>8s} > SLA {i["sla_days"]}d'
            f'  -> 仅告警')
    # 显式列出代理命中，避免体检"看似 MISSING"与下游"读取 OK"的分裂
    proxies = [i for i in result['ok'] if i.get('proxy_used')]
    for i in proxies:
        out(f'│  🔗 {i["series_id"]:18s} 通过代理 {i["series_used"]} 读取'
            f'  lag={i["days_lag"]}d  -> OK')
    out('└' + '─' * width + '┘')