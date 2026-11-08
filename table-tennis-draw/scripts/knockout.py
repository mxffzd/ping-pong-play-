"""Plan group-winner seeded knockouts and optional opposite-half runner-up draws."""
import argparse
import csv
import hashlib
import json
import random
import secrets
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

ALGORITHM = 'table-tennis-knockout-v1'


def seed_order(size):
    if size == 1:
        return [1]
    previous = seed_order(size // 2)
    return [x for i, rank in enumerate(previous)
            for x in ([rank, size + 1 - rank] if i % 2 == 0 else [size + 1 - rank, rank])]


def meeting_round(a, b, size):
    for r in range(1, size.bit_length()):
        if (a - 1) // (2 ** r) == (b - 1) // (2 ** r):
            return r
    raise ValueError('invalid bracket positions')


def read_qualifiers(filename):
    with Path(filename).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['group', 'rank', 'id']:
            raise ValueError('名次文件列必须按 group,rank,id 排列')
        result = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('名次文件列数不正确')
            result.append({'group': int(row['group']), 'rank': int(row['rank']), 'id': row['id'].strip()})
        return result


def make_plan(draw, random_seed, ranked_seeds=False, draw_runners=False, qualifiers=None, preset=None):
    if not isinstance(draw, dict) or not isinstance(draw.get('groups'), list):
        raise ValueError('需要含 groups 的分组核验 JSON')
    if preset is not None and not isinstance(preset, dict):
        raise ValueError('旧签表必须为 JSON 对象')
    groups = draw['groups']
    g = len(groups)
    if g < 1 or g > 32 or g & (g - 1):
        raise ValueError('当前模式要求1、2、4、8、16或32组，每组前2名出线；其他模式需另定规则')
    group_map, all_players = {}, {}
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('分组记录必须为 JSON 对象')
        number, players = group.get('group'), group.get('players')
        if type(number) is not int or number < 1 or number in group_map or not isinstance(players, list) or len(players) < 2:
            raise ValueError('组号应唯一且为正整数，每组至少2名选手')
        group_map[number] = group
        for p in players:
            if not isinstance(p, dict) or not isinstance(p.get('id'), str) or not p['id'] or not isinstance(p.get('name'), str) or not p['name'] or p['id'] in all_players:
                raise ValueError('选手编号和姓名必须有效，编号不得重复')
            all_players[p['id']] = (number, p)
    k = draw.get('rules', {}).get('protect_top_k', 0)
    if type(k) is not int or k < 0:
        raise ValueError('保护名次上限无效')
    seeded = []
    for group in groups:
        protected = []
        for p in group['players']:
            rank = p.get('seed_rank')
            if rank is not None and (type(rank) is not int or rank < 1):
                raise ValueError('种子名次必须为正整数或空')
            if rank is not None and rank <= k:
                protected.append((rank, group['group'], p['id']))
        if len(protected) > 1:
            raise ValueError('同组多名受保护种子不能同时按组第一预设签位')
        seeded.extend(protected)
    seeded.sort()
    if len({s[0] for s in seeded}) != len(seeded):
        raise ValueError('种子名次重复')
    if seeded and not ranked_seeds:
        raise ValueError('先确认种子强弱顺序，再传 --ranked-seeds；不得把普通列举顺序当成实力排名')
    rng = random.Random(random_seed)
    n = 2 * g
    order = seed_order(n)
    rank_position = {rank: i + 1 for i, rank in enumerate(order)}
    group_positions = {group: rank_position[i + 1] for i, (_, group, _) in enumerate(seeded)}
    remaining_groups = sorted(set(group_map) - set(group_positions))
    rng.shuffle(remaining_groups)
    for rank, group in enumerate(remaining_groups, len(seeded) + 1):
        group_positions[group] = rank_position[rank]
    preset_drawn = preset is not None and preset.get('draw_status') in ('drawn_actual', 'drawn_placeholders')
    if preset_drawn and draw_runners:
        raise ValueError('旧签表已完成第二名抽签；补录姓名时使用 --preset，不再加 --draw-runners-up')
    if preset is not None:
        if preset.get('bracket_size') != n:
            raise ValueError('预设签表规模与当前分组不同')
        old = {s.get('group'): s.get('position') for s in preset.get('slots', []) if s.get('rank') == 1}
        if set(old) != set(group_map) or len(set(old.values())) != g or any(p not in set(rank_position[r] for r in range(1, g + 1)) for p in old.values()):
            raise ValueError('预设的组第一签位无效')
        if any(old[group] != rank_position[i + 1] for i, (_, group, _) in enumerate(seeded)):
            raise ValueError('预设种子签位与当前种子顺序不同，请明确规则变更后另行处理')
        group_positions = old

    actual = {}
    if qualifiers is not None:
        for q in qualifiers:
            number, rank, pid = q.get('group'), q.get('rank'), q.get('id')
            key = (number, rank)
            if type(number) is not int or type(rank) is not int or number not in group_map or rank not in (1, 2) or key in actual or pid not in all_players or all_players[pid][0] != number:
                raise ValueError('出线名次不完整、重复或选手不属于该组')
            actual[key] = all_players[pid][1]
        expected = {(number, rank) for number in group_map for rank in (1, 2)}
        if set(actual) != expected or len({p['id'] for p in actual.values()}) != n:
            raise ValueError('每组须明确第一、第二各一人，且所有出线人选互不重复')

    upper_first = sorted(number for number, p in group_positions.items() if p <= n // 2)
    lower_first = sorted(set(group_map) - set(upper_first))
    position_group = {p: number for number, p in group_positions.items()}
    slots = []
    for p in range(1, n + 1):
        number = position_group.get(p)
        slots.append({'position': p, 'group': number, 'rank': 1 if number is not None else 2,
                      'half': 'upper' if p <= n // 2 else 'lower',
                      'label': f'第{number}组第一' if number is not None else '小组第二（待抽签）',
                      'participant': None})
    pools = []
    for half, allowed in [('upper', lower_first), ('lower', upper_first)]:
        open_slots = [s for s in slots if s['half'] == half and s['rank'] == 2]
        if len(open_slots) != len(allowed):
            raise RuntimeError('相反半区抽签名额不匹配')
        pools.append({'half': half, 'groups': allowed, 'positions': [s['position'] for s in open_slots]})
        if draw_runners or preset_drawn:
            if preset_drawn:
                prior = {s['position']: s.get('group') for s in preset.get('slots', []) if s.get('rank') == 2}
                assigned = [prior.get(s['position']) for s in open_slots]
                if sorted(assigned, key=str) != sorted(allowed, key=str):
                    raise ValueError('旧第二名签位不满足相反半区抽签规则')
            else:
                assigned = allowed[:]
                rng.shuffle(assigned)
            for s, number in zip(open_slots, assigned):
                s['group'], s['label'] = number, f'第{number}组第二'
    for s in slots:
        if s['group'] is not None and actual:
            p = actual[(s['group'], s['rank'])]
            s['participant'] = {'id': p['id'], 'name': p['name']}

    for i in range(0, n, 2):
        if sorted([slots[i]['rank'], slots[i + 1]['rank']]) != [1, 2]:
            raise RuntimeError('首轮未满足第一对第二')
    if draw_runners or preset_drawn:
        for number in group_map:
            selected = [s for s in slots if s['group'] == number]
            if len(selected) != 2 or selected[0]['half'] == selected[1]['half']:
                raise RuntimeError('同组回避或出线席位完整性校验失败')
    tier_checks = []
    for tier in (2, 4, 8, 16, 32):
        if len(seeded) >= tier:
            positions = [group_positions[s[1]] for s in seeded[:tier]]
            earliest = min(meeting_round(a, b, n) for a, b in combinations(positions, 2))
            required = n.bit_length() - (tier.bit_length() - 1)
            if earliest < required:
                raise RuntimeError('种子分级分区校验失败')
            tier_checks.append({'top': tier, 'earliest_meeting_round': earliest})
    warnings = []
    if actual:
        for _, number, pid in seeded:
            if actual[(number, 1)]['id'] != pid:
                warnings.append(f'{pid}未获组第一，原种子分区保护不再保证')
    return {'algorithm': ALGORITHM, 'group_count': g, 'bracket_size': n, 'qualifiers_per_group': 2,
            'random_seed': str(random_seed), 'draw_status': ('drawn_actual' if actual else 'drawn_placeholders') if (draw_runners or preset_drawn) else 'runners_pending',
            'slots': slots, 'runner_pools': pools, 'match_count': n - 1,
            'seed_basis': [{'source_rank': rank, 'group': number, 'id': pid} for rank, number, pid in seeded],
            'tier_checks': tier_checks, 'warnings': warnings,
            'checks': {'one_first_place_per_group': True, 'first_round_first_vs_second': True,
                       'opposite_half_runner_pools': True, 'ranked_seed_tiers': True,
                       'same_group_opposite_halves': True if (draw_runners or preset_drawn) else 'pending draw'}}


def csv_text(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def main():
    parser = argparse.ArgumentParser(description='每组前2名出线的分区淘汰赛编排')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ranked-seeds', action='store_true')
    parser.add_argument('--draw-runners-up', action='store_true')
    parser.add_argument('--qualifiers', type=Path)
    parser.add_argument('--preset', type=Path)
    parser.add_argument('--random-seed', type=int)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('输出目录已存在，请另存新版本')
        raw = args.input.read_bytes()
        seed = args.random_seed if args.random_seed is not None else secrets.randbits(64)
        preset = json.loads(args.preset.read_text(encoding='utf-8-sig')) if args.preset else None
        if preset is not None and preset.get('source_draw_sha256') != hashlib.sha256(raw).hexdigest():
            raise ValueError('旧签表对应的分组文件与本次不同，不能套用旧预设签位')
        result = make_plan(json.loads(raw.decode('utf-8-sig')), seed, args.ranked_seeds, args.draw_runners_up,
                           read_qualifiers(args.qualifiers) if args.qualifiers else None, preset)
        result['source_draw_sha256'] = hashlib.sha256(raw).hexdigest()
        result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        result['created_at_utc'] = datetime.now(timezone.utc).isoformat()
        if args.qualifiers:
            result['qualifiers_sha256'] = hashlib.sha256(args.qualifiers.read_bytes()).hexdigest()
        if args.preset:
            result['preset_sha256'] = hashlib.sha256(args.preset.read_bytes()).hexdigest()
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / '淘汰赛编排.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        with (args.output / '淘汰赛签位.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['签位', '半区', '出线名次', '参赛编号', '姓名'])
            for s in result['slots']:
                p = s['participant'] or {}
                writer.writerow([s['position'], '上半区' if s['half'] == 'upper' else '下半区', s['label'],
                                 csv_text(p.get('id', '')), csv_text(p.get('name', ''))])
    except (ValueError, TypeError, KeyError, OSError, UnicodeError) as error:
        parser.exit(2, f'淘汰赛未生成：{error}\n')
    print(json.dumps({'output': str(args.output.resolve()), 'bracket_size': result['bracket_size'],
                      'status': result['draw_status'], 'checks': result['checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
