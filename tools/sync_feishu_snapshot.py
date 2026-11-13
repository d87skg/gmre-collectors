# -*- coding: utf-8 -*-
"""tools/sync_feishu_snapshot.py - v4.1 已 DISARM（第三条入站通道）

【历史行为（已废除）】
从 GitHub 拉 d87skg/gmre-collectors 的 feishu_snapshot.csv（该 CSV 本身由
"已推送文本 -> 正则反解析"生成），然后：

    df_new.to_sql('feishu_snapshot', conn, if_exists='replace')

**整表替换** feishu_snapshot，并把 bitget_btc_fr 缝合进
observations(BTC_FUNDING_RATE_1H, source='feishu_increment')。

危害：
  * `if_exists='replace'` 会连表结构一起换掉，列名/历史直接丢失；
  * 这是完全绕开本地采集的第二条"云端回流"通道，本地有没有采集到都不影响；
  * 缝合行同样没有真实 obs_date。

【现在】
不联网、不写库。任何调用直接 BLOCKED 返回非零退出码。
"""
REPULL_DISABLED = True
DISABLED_AT = '2026-11-11 (v4.1 phase 2)'
REASON = ('飞书 CSV 是「文本 -> 正则」的产物，且以 if_exists=replace 整表替换，'
          '构成绕开本地采集的云端回流通道')


def main() -> int:
    print('[BLOCKED] sync_feishu_snapshot 已在 v4.1 阶段 2 停用。')
    print(f'          停用时间: {DISABLED_AT}')
    print(f'          停用原因: {REASON}')
    print('          官方数值请走 data_correction（FRED / NYFed / Treasury）。')
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
