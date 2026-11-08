"""Balanced table-tennis draws with reproducible randomness and checked constraints."""

import argparse
import csv
import hashlib
import io
import json
import platform
import random
import secrets
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

ALGORITHM = "table-tennis-draw-v1"


def integer(value, field, allow_empty=False):
    text = str(value).strip()
    if allow_empty and not text:
        return None
    if not text.isascii() or not text.isdecimal() or int(text) < 1:
        raise ValueError(f"{field} 必须为正整数")
    return int(text)


def read_roster(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    columns = reader.fieldnames or []
    allowed = {"id", "name", "affiliation", "seed_rank", "fixed_group"}
    if not {"id", "name"} <= set(columns) or len(set(columns)) != len(columns):
        raise ValueError("CSV 需要无重复列名，且包含 id,name")
    if set(columns) - allowed:
        raise ValueError("存在未知列，请先规范为 id,name,affiliation,seed_rank,fixed_group")
    result = []
    for line, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"第 {line} 行列数不正确")
        if not any(v.strip() for v in row.values()):
            continue
        item = {"id": row["id"].strip(), "name": row["name"].strip(),
                "affiliation": row.get("affiliation", "").strip(),
                "seed_rank": integer(row.get("seed_rank", ""), "种子名次", True),
                "fixed_group": integer(row.get("fixed_group", ""), "固定组号", True)}
        if not item["id"] or not item["name"]:
            raise ValueError(f"第 {line} 行编号和姓名不能为空")
        result.append(item)
    if not result:
        raise ValueError("有效名单为空")
    return result


def make_draw(players, group_count, protect_top_k, random_seed):
    if type(group_count) is not int or group_count < 1 or group_count > len(players):
        raise ValueError("组数必须为1至参赛人数之间的整数")
    if type(protect_top_k) is not int or protect_top_k < 0:
        raise ValueError("保护名次上限必须为非负整数")
    ids = [p["id"] for p in players]
    ranks = [p["seed_rank"] for p in players if p["seed_rank"] is not None]
    if len(ids) != len(set(ids)):
        raise ValueError("参赛编号重复，请先核对报名记录")
    if len(ranks) != len(set(ranks)):
        raise ValueError("种子名次重复，请先确认种子排序")
    for p in players:
        if p["fixed_group"] is not None and not 1 <= p["fixed_group"] <= group_count:
            raise ValueError(f"{p['id']} 的固定组号超出范围")
    protected = [p for p in players if p["seed_rank"] is not None
                 and p["seed_rank"] <= protect_top_k]
    if len(protected) > group_count:
        raise ValueError("受保护种子人数超过组数，无法保证各在不同组")
    protected_ids = {p["id"] for p in protected}
    rng = random.Random(random_seed)
    groups = [[] for _ in range(group_count)]
    for p in players:
        if p["fixed_group"] is not None:
            groups[p["fixed_group"] - 1].append(p)
    seeded_groups = {i for i, g in enumerate(groups)
                     if any(p["id"] in protected_ids for p in g)}
    for group in groups:
        if sum(p["id"] in protected_ids for p in group) > 1:
            raise ValueError("多个受保护种子被固定在同一组")

    base, extra = divmod(len(players), group_count)
    counts = list(map(len, groups))
    mandatory_big = {i for i, count in enumerate(counts) if count > base}
    if any(c > base + bool(extra) for c in counts) or len(mandatory_big) > extra:
        raise ValueError("固定分组人数与均衡人数规则冲突")
    unplaced_seeds = [p for p in protected if p["fixed_group"] is None]
    free_at_base = [i for i, c in enumerate(counts) if c < base and i not in seeded_groups]
    eligible_big = [i for i, c in enumerate(counts) if c == base and i not in seeded_groups]
    need_big = max(0, len(unplaced_seeds) - len(free_at_base))
    remaining_extra = extra - len(mandatory_big)
    if need_big > remaining_extra or need_big > len(eligible_big):
        raise ValueError("固定分组占满可用名额，无法同时满足种子分散和均衡人数")
    rng.shuffle(eligible_big)
    big = mandatory_big | set(eligible_big[:need_big])
    candidates = [i for i in range(group_count) if i not in big]
    rng.shuffle(candidates)
    big.update(candidates[:extra - len(big)])
    capacities = [base + (i in big) for i in range(group_count)]

    eligible = [i for i, g in enumerate(groups)
                if len(g) < capacities[i] and i not in seeded_groups]
    rng.shuffle(eligible)
    rng.shuffle(unplaced_seeds)
    for p, target in zip(unplaced_seeds, eligible):
        groups[target].append(p)
    ordinary = [p for p in players if p["fixed_group"] is None
                and p["id"] not in protected_ids]
    slots = [i for i, group in enumerate(groups) for _ in range(capacities[i] - len(group))]
    rng.shuffle(slots)
    rng.shuffle(ordinary)
    if len(slots) != len(ordinary):
        raise RuntimeError("内部名额校验失败")
    for p, target in zip(ordinary, slots):
        groups[target].append(p)
    for group in groups:
        rng.shuffle(group)

    actual_ids = [p["id"] for group in groups for p in group]
    checks = {
        "same_participants": Counter(actual_ids) == Counter(ids),
        "no_duplicates": len(actual_ids) == len(set(actual_ids)),
        "balanced_sizes": max(map(len, groups)) - min(map(len, groups)) <= 1,
        "planned_capacities": list(map(len, groups)) == capacities,
        "seeds_separated": all(sum(p["id"] in protected_ids for p in g) <= 1 for g in groups),
        "fixed_groups_preserved": all(p["fixed_group"] in (None, i + 1)
                                      for i, g in enumerate(groups) for p in g),
    }
    if not all(checks.values()):
        raise RuntimeError(f"分组校验失败: {checks}")
    duplicate_names = sorted(name for name, n in Counter(p["name"] for p in players).items() if n > 1)
    warnings = []
    if duplicate_names:
        warnings.append("同名参赛者按不同编号保留，请确认身份：" + "、".join(duplicate_names))
    if ranks and protect_top_k == 0:
        warnings.append("名单含种子名次，本次按明确参数不实施种子保护")
    result_groups = [{"group": i + 1, "size": len(g), "players": g} for i, g in enumerate(groups)]
    matches = [{"group": i + 1, "player_a_id": a["id"], "player_b_id": b["id"]}
               for i, group in enumerate(groups) for a, b in combinations(group, 2)]
    return {"algorithm": ALGORITHM, "python_version": platform.python_version(),
            "random_seed": str(random_seed),
            "rules": {"group_count": group_count, "protect_top_k": protect_top_k,
                      "balanced": True, "shuffle_within_group": True},
            "participant_count": len(players), "protected_count": len(protected),
            "group_sizes": list(map(len, groups)), "checks": checks, "warnings": warnings,
            "groups": result_groups, "match_count": len(matches), "matches": matches}


def excel_text(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def write_result(result, output):
    output.mkdir(parents=True, exist_ok=False)
    (output / "抽签核验.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "分组名单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["组别", "组内序号", "参赛编号", "姓名或搭档", "班级或单位"])
        for group in result["groups"]:
            for order, p in enumerate(group["players"], 1):
                writer.writerow([group["group"], order, excel_text(p["id"]), excel_text(p["name"]), excel_text(p["affiliation"])])


def main():
    parser = argparse.ArgumentParser(description="乒乓球均衡分组，支持前K名种子分散与固定组号")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--groups", type=int, required=True)
    parser.add_argument("--protect-top-k", type=int, required=True)
    parser.add_argument("--random-seed", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("输出目录已存在，请保留旧结果并选择新目录")
        raw = args.input.read_bytes()
        seed = args.random_seed if args.random_seed is not None else secrets.randbits(64)
        result = make_draw(read_roster(raw), args.groups, args.protect_top_k, seed)
        result["source_sha256"] = hashlib.sha256(raw).hexdigest()
        result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_result(result, args.output)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(2, f"分组未完成：{error}\n")
    print(json.dumps({"output": str(args.output.resolve()), "participants": result["participant_count"],
                      "group_sizes": result["group_sizes"], "checks": result["checks"],
                      "warnings": result["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
