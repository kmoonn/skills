#!/usr/bin/env python3
"""
评委分配工具 — 学科匹配评分引擎

可作为独立脚本运行，也可作为 Skill 的参考实现被导入使用。
"""

import pandas as pd
from collections import defaultdict

# ============================================================
# 学科映射表（可扩展）
# ============================================================
DEPT_MAPPING = {
    "测绘": ["地球科学", "地理"],
    "经管": ["经济学", "管理学", "管理科学与工程"],
    "物理": ["力学", "工程"],
    "物理力学": ["力学", "物理", "工程"],
    "计算机": ["信息科学", "计算机", "集成电路", "人工智能", "AI"],
    "信息": ["信息科学", "集成电路", "计算机"],
    "化生": ["化学", "生命科学", "药学", "农学", "肿瘤学", "水产", "基础医学", "兽医"],
    "外国语": ["文学", "语言学"],
    "语言学": ["文学", "语言学", "社会学", "区域国别"],
    "法社": ["法学", "社会学", "政治学", "区域国别"],
    "马克思": ["社会学", "政治学", "科学技术与社会", "其他"],
    "管理": ["管理科学与工程", "管理学"],
    "艺设": ["设计学", "艺工融合", "基于学科交叉的艺工融合及应用"],
    "数学": ["数学"],
    "数统": ["数学"],
    "材料": ["材料科学与工程", "材料"],
    "自动化": ["自动化", "集成电路"],
    "经济": ["经济学"],
    "安全应急": ["工程", "能源", "工程与能源"],
    "船海能动": ["工程", "能源", "工程与能源"],
    "航运": ["工程", "能源", "工程与能源"],
    "交通物流": ["工程", "能源", "工程与能源"],
    "智能交通": ["工程", "能源", "工程与能源"],
    "汽车": ["工程", "能源", "工程与能源"],
}


def parse_group_disciplines(raw: str) -> list[str]:
    """从分组研究方向字符串中提取学科列表。支持逗号、顿号分隔，以及方括号包裹。"""
    text = str(raw).strip("[]' ")  # 处理 DataFrame 读取的列表格式
    # 按常见分隔符拆分
    import re
    parts = re.split(r"[、,，]+", text)
    return [p.strip(" '\"[]") for p in parts if p.strip(" '\"[]")]


def score_match(expert_dept: str, group_disciplines: list[str]) -> int:
    """
    计算专家学科与分组研究方向的匹配分数。

    返回：
    - 10: 完全匹配（专家学科名直接出现在分组方向中）
    - 5:  映射匹配（专家学科通过 DEPT_MAPPING 关联到分组方向）
    - 0:  无匹配
    """
    dept = str(expert_dept).strip()
    best = 0

    for discipline in group_disciplines:
        disc = str(discipline).strip().lower()
        dept_lower = dept.lower()

        # 完全匹配
        if dept_lower in disc or disc in dept_lower:
            return 10

        # 映射匹配
        mapped = DEPT_MAPPING.get(dept, []) + DEPT_MAPPING.get(dept_lower, [])
        for m in mapped:
            m_lower = m.lower()
            if m_lower in disc or disc in m_lower or any(
                w in disc for w in m_lower.replace("与", " ").split()
            ):
                best = max(best, 5)

    return best


def compute_match_matrix(
    experts_df: pd.DataFrame, groups_df: pd.DataFrame
) -> dict:
    """
    计算专家×分组的匹配分数矩阵。

    返回:
        {
            expert_name: {
                group_id: score,
                ...
            },
            ...
        }
    """
    matrix = {}
    for _, exp in experts_df.iterrows():
        name = exp["姓名"]
        dept = exp["学院/学科"]
        matrix[name] = {}
        for _, grp in groups_df.iterrows():
            gid = grp["分组"]
            disciplines = parse_group_disciplines(grp[" 项目研究方向"])
            s = score_match(dept, disciplines)
            if s > 0:
                matrix[name][gid] = s
    return matrix


def assign_judges(
    experts_df: pd.DataFrame,
    groups_df: pd.DataFrame,
    judges_per_group: int = 3,
    target_internal: int = 2,
    target_external: int = 1,
) -> list[tuple]:
    """
    执行评委分配。

    参数：
    - experts_df: 专家信息 DataFrame (columns: 校内/校外, 工号, 姓名, 学院/学科)
    - groups_df: 项目分组 DataFrame (columns: 分组, 项目研究方向)
    - judges_per_group: 每组评委数 (默认 3)
    - target_internal: 每组目标校内评委数 (默认 2)
    - target_external: 每组目标校外评委数 (默认 1)

    返回：
        [(分组, 研究方向, [(类型, 姓名, 工号, 学院), ...]), ...]
    """
    matrix = compute_match_matrix(experts_df, groups_df)

    # 分类专家
    internal = experts_df[experts_df["校内/校外"].str.contains("校内", na=False)]
    external = experts_df[experts_df["校内/校外"].str.contains("校外", na=False)]

    # 初始化组
    group_slots = {}
    for _, grp in groups_df.iterrows():
        gid = grp["分组"]
        group_slots[gid] = {
            "direction": grp[" 项目研究方向"],
            "internal": [],
            "external": [],
            "target_internal": target_internal,
            "target_external": target_external,
        }

    assigned = set()

    def _assign(exp_row, gid):
        typ = "校内" if "校内" in str(exp_row["校内/校外"]) else "校外"
        slot_key = "internal" if typ == "校内" else "external"
        group_slots[gid][slot_key].append(
            (typ, exp_row["姓名"], str(exp_row["工号"]), exp_row["学院/学科"])
        )
        assigned.add(exp_row["姓名"])

    def _can_assign(exp_row, gid):
        typ = "校内" if "校内" in str(exp_row["校内/校外"]) else "校外"
        slot_key = "internal" if typ == "校内" else "external"
        return len(group_slots[gid][slot_key]) < group_slots[gid][f"target_{slot_key}"]

    # Phase 1: 校外专家优先匹配
    for _, exp in external.iterrows():
        if exp["姓名"] in assigned:
            continue
        name = exp["姓名"]
        candidates = []
        for gid in group_slots:
            if _can_assign(exp, gid):
                s = matrix.get(name, {}).get(gid, 0)
                candidates.append((s, gid))
        candidates.sort(key=lambda x: -x[0])
        if candidates:
            # 选分数最高的组
            best_score, best_gid = candidates[0]
            # 如果有多个同分，选当前填充数最少的
            same_score = [c for c in candidates if c[0] == best_score]
            if len(same_score) > 1:
                best_gid = min(
                    same_score,
                    key=lambda c: len(group_slots[c[1]]["external"]),
                )[1]
            _assign(exp, best_gid)

    # Phase 2: 校内专家匹配
    for _, exp in internal.iterrows():
        if exp["姓名"] in assigned:
            continue
        name = exp["姓名"]
        candidates = []
        for gid in group_slots:
            if _can_assign(exp, gid):
                s = matrix.get(name, {}).get(gid, 0)
                candidates.append((s, gid))
        candidates.sort(key=lambda x: -x[0])
        if candidates:
            best_score, best_gid = candidates[0]
            same_score = [c for c in candidates if c[0] == best_score]
            if len(same_score) > 1:
                best_gid = min(
                    same_score,
                    key=lambda c: len(group_slots[c[1]]["internal"]),
                )[1]
            _assign(exp, best_gid)

    # Phase 3: 跨学科兜底 — 把未分配专家填入还有空位的组
    for _, exp in external.iterrows():
        if exp["姓名"] in assigned:
            continue
        for gid in group_slots:
            if _can_assign(exp, gid):
                _assign(exp, gid)
                break

    for _, exp in internal.iterrows():
        if exp["姓名"] in assigned:
            continue
        for gid in group_slots:
            if _can_assign(exp, gid):
                _assign(exp, gid)
                break

    # 组装结果
    result = []
    for gid in sorted(group_slots.keys()):
        slots = group_slots[gid]
        judges = slots["internal"] + slots["external"]
        result.append((gid, slots["direction"], judges))

    return result


def validate_assignment(
    assignment: list[tuple], experts_df: pd.DataFrame
) -> dict:
    """验证分配结果，返回统计信息。"""
    all_judges = []
    for gid, _, judges in assignment:
        for typ, name, wid, dept in judges:
            all_judges.append((name, wid, gid, typ))

    errors = []
    names = [n for n, _, _, _ in all_judges]
    if len(names) != len(set(names)):
        from collections import Counter

        dupes = [n for n, c in Counter(names).items() if c > 1]
        errors.append(f"重复分配: {dupes}")

    groups_per_judge = set(gid for _, _, gid, _ in all_judges)

    stats = {
        "total_assigned": len(all_judges),
        "total_internal": sum(1 for _, _, _, t in all_judges if t == "校内"),
        "total_external": sum(1 for _, _, _, t in all_judges if t == "校外"),
        "groups_count": len(groups_per_judge),
        "errors": errors,
        "unassigned": set(experts_df["姓名"].tolist()) - set(names),
    }
    return stats


def print_score_matrix(
    experts_df: pd.DataFrame, groups_df: pd.DataFrame
) -> None:
    """打印每位专家与各分组的匹配分数，供 AI 参考决策。"""
    matrix = compute_match_matrix(experts_df, groups_df)

    # 按校内/校外分组
    internal_names = set(
        experts_df[experts_df["校内/校外"].str.contains("校内", na=False)]["姓名"]
    )
    external_names = set(
        experts_df[experts_df["校内/校外"].str.contains("校外", na=False)]["姓名"]
    )

    group_ids = sorted(groups_df["分组"].tolist())

    def _print_section(title, names):
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
        print(f"{'专家(学科)':<22}", end="")
        for gid in group_ids:
            print(f"G{gid:>2} ", end="")
        print("  最佳匹配")
        print("-" * 60)
        for name in sorted(names):
            row = experts_df[experts_df["姓名"] == name].iloc[0]
            dept = row["学院/学科"]
            label = f"{name}({dept})"
            scores = [matrix.get(name, {}).get(gid, 0) for gid in group_ids]
            print(f"{label:<22}", end="")
            for s in scores:
                marker = "██" if s >= 10 else ("█ " if s >= 5 else "· ")
                print(f"{marker:>3}", end="")
            # 最佳匹配组
            best = [(gid, s) for gid, s in zip(group_ids, scores) if s > 0]
            best.sort(key=lambda x: -x[1])
            best_str = ", ".join(f"G{gid}({s})" for gid, s in best[:3])
            if best_str:
                print(f"  → {best_str}", end="")
            print()

    _print_section("校外专家匹配矩阵", external_names)
    _print_section("校内专家匹配矩阵", internal_names)


# ============================================================
# CLI 入口
# ============================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(
            "用法: python3 assign_judges.py <专家信息.xlsx> <项目分组.xlsx> "
            "[每组评委数=3] [目标校内=2] [目标校外=1]"
        )
        print("      python3 assign_judges.py --mode score <专家信息.xlsx> <项目分组.xlsx>")
        sys.exit(1)

    mode = "assign"
    args = sys.argv[1:]
    if args[0] == "--mode":
        mode = args[1]
        args = args[2:]

    experts_file = args[0]
    groups_file = args[1]

    experts = pd.read_excel(experts_file)
    groups = pd.read_excel(groups_file)

    if mode == "score":
        print(f"专家总数: {len(experts)} (校内: {sum(experts['校内/校外'].str.contains('校内', na=False))}, "
              f"校外: {sum(experts['校内/校外'].str.contains('校外', na=False))})")
        print(f"项目分组数: {len(groups)}")
        print_score_matrix(experts, groups)
        sys.exit(0)

    # assign mode
    judges_per = int(args[2]) if len(args) > 2 else 3
    target_in = int(args[3]) if len(args) > 3 else 2
    target_out = int(args[4]) if len(args) > 4 else 1

    experts = pd.read_excel(experts_file)
    groups = pd.read_excel(groups_file)

    print(f"专家总数: {len(experts)} (校内: {sum(experts['校内/校外'].str.contains('校内', na=False))}, "
          f"校外: {sum(experts['校内/校外'].str.contains('校外', na=False))})")
    print(f"项目分组数: {len(groups)}")
    print(f"每组评委数: {judges_per} (目标: {target_in}校内 + {target_out}校外)")
    print()

    # 检查约束
    slots = len(groups) * judges_per
    if slots > len(experts):
        print(f"⚠️  警告：需要 {slots} 个评委名额，但只有 {len(experts)} 位专家！")
    if target_out * len(groups) > sum(
        experts["校内/校外"].str.contains("校外", na=False)
    ):
        max_ext_groups = sum(
            experts["校内/校外"].str.contains("校外", na=False)
        ) // target_out
        print(
            f"⚠️  校外专家不足以覆盖所有组：最多 {max_ext_groups} 组有校外评委，"
            f"{len(groups) - max_ext_groups} 组将为纯校内组"
        )

    result = assign_judges(experts, groups, judges_per, target_in, target_out)
    stats = validate_assignment(result, experts)

    print("=" * 40)
    print("分配结果：")
    for gid, direction, judges in result:
        n_in = sum(1 for t, _, _, _ in judges if t == "校内")
        n_out = sum(1 for t, _, _, _ in judges if t == "校外")
        print(f"\n第{gid}组 ({n_in}内+{n_out}外): {direction[:60]}")
        for typ, name, wid, dept in judges:
            print(f"  [{typ}] {name} ({dept}) 工号:{wid}")

    print(f"\n统计: 已分配 {stats['total_assigned']} 人, "
          f"校内 {stats['total_internal']}, 校外 {stats['total_external']}")
    if stats["unassigned"]:
        print(f"未分配: {stats['unassigned']}")
    if stats["errors"]:
        print(f"错误: {stats['errors']}")
    else:
        print("✓ 验证通过")