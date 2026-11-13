# -*- coding: utf-8 -*-
"""core/errors.py - 数据面异常分级（v4.1 阶段 3 第一步）

设计目标：**代理层可以抛异常，但绝不允许主程序被卡死**。
所有数据面异常都带 severity，入口处按三档处置：

    P0 BLOCK    -> 阻断出报：打印原因、退出码 4，绝不生成 Gate / 晨报
    P1 DEGRADE  -> 降级：该指标取不到值，下沉为 UNKNOWN，其余流程继续
    P2 WARN     -> 仅展示：打印告警，数值照常使用，Gate 照常计算

分层原则（对应决策⑤的 SLA）：
    * P0 = 防线直接依赖、且没有可替代官方源的序列
           （TGA / SOFR / EFFR / RRP 的 NYFed 官方源）
    * P1 = 有替代源、或可降级为 UNKNOWN 的序列（FRED 侧 RRPONTSYD、HY、YC* 等）
    * P2 = 参考性/低频序列（调查类 MICH 等），以及任何未登记的序列

本模块不碰数据库：DB 读取由 `probe` 回调注入。阶段 3 第二步建好
`core/data_proxy.py` 后，probe 由代理层提供，policy 层保持不变。
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

# ---------------------------------------------------------------- SLA（决策⑤）
SLA_DAILY = 3          # 日频 3 天
SLA_RATES = 2          # SOFR / EFFR / RRP 2 天
SLA_WEEKLY = 8         # 周频 8 天
SLA_MONTHLY = 45       # 月频 45 天

# 序列 -> (SLA 天数, severity)
# v4.1 阶段 3 第二步起，这张表**不再手写**：统一由 core/units.py 的 REGISTRY 派生，
# 避免 SLA/别名/量纲三处各写一份、彼此漂移。
SERIES_POLICY = {cid: (e['sla'], e['severity']) for cid, e in _units.REGISTRY.items()}
DEFAULT_POLICY = (_units.DEFAULT_ENTRY['sla'], _units.DEFAULT_ENTRY['severity'])


def policy_for(series_id):
    """任意叫法 -> (sla, severity)。别名会先归一成 canonical id。"""
    cid = _units.canonical_id(series_id)
    return SERIES_POLICY.get(cid, DEFAULT_POLICY)


def days_between(obs_date, asof=None):
    """obs_date -> asof 的自然日差。无法解析返回 None。（与 units 同口径）"""
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
    """量纲/值域异常：数值超出该序列 canonical 单位的合理区间。

    典型：RRPONTSYD 历史遗留的百万级脏值（399200 十亿 = 约 40 万亿美元，不可能）。
    这类异常**永不降级使用**，直接隔离并抛出。
    """

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
    """序列完全无数据（表内不存在该 series_id）。"""

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
    """入口级处置。返回进程退出码。

    P0 -> 打印阻断横幅 + 退出码 4（拒绝出报，不写 daily_summary / predictions_log）
    P1 -> 打印降级提示 + 退出码 0（调用方已兜底）
    P2 -> 打印告警    + 退出码 0
    """
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
    """在某个计算段内兜住数据异常。

    P0   -> 继续向上抛，交给入口阻断出报
    其它 -> 就地吞掉并按 severity 打印，调用方拿到 None 自行兜底
    """
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

    probe(series_id) -> {'obs_date': 'YYYY-MM-DD', 'source': ..., 'value': ...} | None

    返回 {'block': [...], 'degrade': [...], 'warn': [...], 'ok': [...], 'verdict': ...}
    其中 block 非空时调用方必须拒绝出报。
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
            result['ok'].append({'series_id': sid, 'obs_date': info['obs_date'],
                                 'days_lag': lag, 'sla_days': sla})

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
    out('└' + '─' * width + '┘')
