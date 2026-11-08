"""Create numbered single round-robin pairings from an existing draw, without redrawing."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

ALGORITHM = "table-tennis-round-robin-v1"


def make_schedule(draw):
    if not isinstance(draw, dict):
        raise ValueError("分组结果必须为 JSON 对象")
    groups = draw.get("groups", [])
    if not isinstance(groups, list) or not groups:
        raise ValueError("分组结果必须含非空 groups")
    all_ids, group_numbers, matches, byes, clean_groups = [], [], [], [], []
    for group in groups:
        number, players = group.get("group"), group.get("players")
        if type(number) is not int or number < 1 or not isinstance(players, list) or not players:
            raise ValueError("组号必须为正整数，每组至少有一个参赛单位")
        if "size" in group and group["size"] != len(players):
            raise ValueError(f"第{number}组人数与 size 不一致")
        for p in players:
            if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not p["id"].strip() or not isinstance(p.get("name"), str) or not p["name"].strip():
                raise ValueError("参赛编号与姓名不能为空")
        group_numbers.append(number)
        all_ids.extend(p["id"] for p in players)
        # Keep only public identity fields; never export seed labels in pairing lists.
        public = [{"id": p["id"], "name": p["name"], "affiliation": p.get("affiliation", "")}
                  for p in players]
        clean_groups.append({"group": number, "size": len(players), "players": public})
        if len(players) == 1:
            continue
        ring = public[:]
        if len(ring) % 2:
            ring.append(None)
        sequence = 0
        for round_number in range(1, len(ring)):
            for i in range(len(ring) // 2):
                a, b = ring[i], ring[-1 - i]
                if a is None or b is None:
                    p = a or b
                    byes.append({"group": number, "round": round_number,
                                 "player_id": p["id"], "player_name": p["name"]})
                    continue
                sequence += 1
                matches.append({"match_id": f"G{number:02}-M{sequence:02}", "group": number,
                                "round": round_number, "player_a_id": a["id"], "player_a_name": a["name"],
                                "player_b_id": b["id"], "player_b_name": b["name"]})
            ring = [ring[0], ring[-1], *ring[1:-1]]
    if len(set(group_numbers)) != len(group_numbers) or len(set(all_ids)) != len(all_ids):
        raise ValueError("组号或参赛编号重复")
    for group in clean_groups:
        n, number = group["size"], group["group"]
        selected = [m for m in matches if m["group"] == number]
        expected = {frozenset((a["id"], b["id"])) for a, b in combinations(group["players"], 2)}
        actual = [frozenset((m["player_a_id"], m["player_b_id"])) for m in selected]
        if len(selected) != n * (n - 1) // 2 or set(actual) != expected or len(actual) != len(set(actual)):
            raise RuntimeError("单循环对阵覆盖校验失败")
        round_count = 0 if n == 1 else (n - 1 if n % 2 == 0 else n)
        for round_number in range(1, round_count + 1):
            ids = [pid for m in selected if m["round"] == round_number
                   for pid in (m["player_a_id"], m["player_b_id"])]
            resting = [b["player_id"] for b in byes if b["group"] == number and b["round"] == round_number]
            if len(ids) != len(set(ids)) or Counter(ids + resting) != Counter(p["id"] for p in group["players"]):
                raise RuntimeError("同轮撞人或轮空校验失败")
        if n > 1 and n % 2 and Counter(b["player_id"] for b in byes if b["group"] == number) != Counter(p["id"] for p in group["players"]):
            raise RuntimeError("奇数小组轮空次数校验失败")
    return {"algorithm": ALGORITHM, "groups": clean_groups, "match_count": len(matches),
            "matches": matches, "byes": byes,
            "checks": {"all_pairs_once": True, "one_match_per_player_per_round": True,
                       "bye_coverage": True, "original_group_order_preserved": True}}


def text_for_excel(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def main():
    parser = argparse.ArgumentParser(description="从已有分组生成组内单循环分轮对战表")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("输出目录已存在，请另存新版本")
        raw = args.input.read_bytes()
        result = make_schedule(json.loads(raw.decode("utf-8-sig")))
        result["source_draw_sha256"] = hashlib.sha256(raw).hexdigest()
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "组内循环对阵.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with (args.output / "组内循环对阵.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["比赛编号", "组别", "轮次", "甲编号", "甲姓名", "乙编号", "乙姓名", "甲局数", "乙局数"])
            for m in result["matches"]:
                writer.writerow([text_for_excel(m["match_id"]), m["group"], m["round"], text_for_excel(m["player_a_id"]),
                                 text_for_excel(m["player_a_name"]), text_for_excel(m["player_b_id"]), text_for_excel(m["player_b_name"]), "", ""])
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as error:
        parser.exit(2, f"循环表未生成：{error}\n")
    print(json.dumps({"matches": result["match_count"], "byes": len(result["byes"]), "checks": result["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
