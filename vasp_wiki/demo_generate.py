"""
Demo: Agent 生成 VASP 输入文件的完整流程

模拟用户请求: "帮我对 bulk MoS2 做结构优化，需要考虑范德华作用"
演示 Agent 如何:
  1. 解析用户意图 → 匹配计算类型
  2. 根据体系信息选赝势、定参数
  3. 生成 INCAR / POSCAR / KPOINTS / POTCAR 指引
  4. 用 validator 校验
"""

import json
import os
import sys

KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "demo_output")


def load_knowledge(name: str) -> dict:
    with open(os.path.join(KNOWLEDGE_DIR, name)) as f:
        return json.load(f)


# ════════════════════════════════════════════════════════════
# Step 0: 用户请求 & 体系信息
# ════════════════════════════════════════════════════════════

USER_REQUEST = "帮我对 bulk MoS2 做结构优化，需要考虑范德华作用"

SYSTEM_INFO = {
    "formula": "MoS2",
    "elements": ["Mo", "S"],
    "n_atoms": 6,           # 2H-MoS2 conventional cell: 2 Mo + 4 S
    "is_metal": False,       # 半导体
    "has_magnetic": False,
    "is_layered": True,      # 层状材料 → 需要 vdW
    "space_group": "P6_3/mmc",
    # 2H-MoS2 实验晶格参数
    "lattice": {
        "a": 3.160, "b": 3.160, "c": 12.295,
        "alpha": 90, "beta": 90, "gamma": 120
    },
    "atoms_fractional": [
        {"element": "Mo", "coords": [1/3, 2/3, 1/4]},
        {"element": "Mo", "coords": [2/3, 1/3, 3/4]},
        {"element": "S",  "coords": [1/3, 2/3, 0.621]},
        {"element": "S",  "coords": [2/3, 1/3, 0.121]},
        {"element": "S",  "coords": [1/3, 2/3, 0.879]},
        {"element": "S",  "coords": [2/3, 1/3, 0.379]},
    ],
}


def step_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# ════════════════════════════════════════════════════════════
# Step 1: 意图识别 → 计算类型 + 特殊需求
# ════════════════════════════════════════════════════════════

def step1_parse_intent(request: str, sys_info: dict) -> dict:
    step_separator("Step 1: 意图识别")
    print(f"用户请求: {request}")

    # Agent 解析逻辑 (实际中由 LLM 完成)
    intent = {
        "task_type": "relax",
        "reasons": [
            "用户说'结构优化' → relax",
        ],
        "modifiers": [],
    }

    # 检测特殊需求
    if "范德华" in request or "vdw" in request.lower() or sys_info.get("is_layered"):
        intent["modifiers"].append("vdw")
        intent["reasons"].append("用户要求考虑范德华 / 层状材料 → 开启 vdW 校正")

    if sys_info.get("has_magnetic"):
        intent["modifiers"].append("magnetic")

    if not sys_info.get("is_metal"):
        intent["modifiers"].append("semiconductor")

    print(f"识别结果: task_type={intent['task_type']}, modifiers={intent['modifiers']}")
    for r in intent["reasons"]:
        print(f"  → {r}")

    return intent


# ════════════════════════════════════════════════════════════
# Step 2: 选择赝势 (POTCAR)
# ════════════════════════════════════════════════════════════

def step2_select_potcar(sys_info: dict) -> dict:
    step_separator("Step 2: 选择赝势 (POTCAR)")

    potcar_db = load_knowledge("potcar_recommend.json")
    recs = potcar_db["recommendations"]

    selected = {}
    max_enmax = 0
    for elem in sys_info["elements"]:
        rec = recs.get(elem, {})
        pot_name = rec.get("default", elem)
        enmax = rec.get("enmax", 300)
        max_enmax = max(max_enmax, enmax)
        selected[elem] = {"potcar": pot_name, "enmax": enmax}
        note = rec.get("note", "")
        print(f"  {elem:3s} → {pot_name:12s}  (ENMAX={enmax} eV) {note}")

    result = {"potcars": selected, "max_enmax": max_enmax}
    print(f"\n  Max ENMAX = {max_enmax} eV")
    print(f"  建议 ENCUT = {int(1.3 * max_enmax)} eV (1.3x for volume relaxation)")
    return result


# ════════════════════════════════════════════════════════════
# Step 3: 生成 INCAR
# ════════════════════════════════════════════════════════════

def step3_generate_incar(intent: dict, sys_info: dict, potcar_info: dict) -> str:
    step_separator("Step 3: 生成 INCAR")

    # 加载模板
    template = load_knowledge(f"task_templates/{intent['task_type']}.json")
    tags_db = load_knowledge("tags_index.json")

    max_enmax = potcar_info["max_enmax"]
    encut = int(1.3 * max_enmax)
    is_metal = sys_info.get("is_metal", False)

    # ── 基础参数 (从模板 required 字段) ──
    incar_tags = {
        "SYSTEM":  sys_info["formula"] + " structure optimization",
        "IBRION":  2,           # CG, robust default
        "NSW":     200,
        "ISIF":    3,           # full cell relaxation (bulk)
        "EDIFFG":  -0.01,       # force criterion eV/Å
        "ENCUT":   encut,
        "EDIFF":   1e-6,
        "PREC":    "Accurate",  # required for ISIF>=3
        "ALGO":    "Fast",
        "POTIM":   0.5,
    }

    # ── 根据金属/半导体设置 smearing ──
    if is_metal:
        incar_tags["ISMEAR"] = 1
        incar_tags["SIGMA"] = 0.2
    else:
        incar_tags["ISMEAR"] = 0
        incar_tags["SIGMA"] = 0.05

    # ── 根据原子数设置 LREAL ──
    if sys_info.get("n_atoms", 0) >= 20:
        incar_tags["LREAL"] = "Auto"
    else:
        incar_tags["LREAL"] = ".FALSE."

    # ── 处理 modifiers ──
    if "vdw" in intent.get("modifiers", []):
        incar_tags["IVDW"] = 12  # DFT-D3(BJ)
        print("  [vdW] 启用 DFT-D3(BJ) 校正 (IVDW=12)")

    if "magnetic" in intent.get("modifiers", []):
        incar_tags["ISPIN"] = 2
        incar_tags["MAGMOM"] = "需根据元素设置"
        print("  [磁性] ISPIN=2")

    # ── 输出控制 ──
    incar_tags["LWAVE"]  = ".FALSE."
    incar_tags["LCHARG"] = ".FALSE."

    # ── 格式化 INCAR ──
    lines = []
    # 分组输出
    groups = {
        "System": ["SYSTEM"],
        "Electronic": ["ALGO", "PREC", "ENCUT", "EDIFF", "ISMEAR", "SIGMA", "LREAL"],
        "Ionic": ["IBRION", "NSW", "ISIF", "EDIFFG", "POTIM"],
        "vdW": ["IVDW"],
        "Magnetism": ["ISPIN", "MAGMOM"],
        "Output": ["LWAVE", "LCHARG"],
    }

    for group_name, group_tags in groups.items():
        group_lines = []
        for tag in group_tags:
            if tag in incar_tags:
                val = incar_tags[tag]
                # 查 tags_db 获取注释
                tag_info = tags_db.get(tag, {})
                brief = tag_info.get("brief", "")
                comment = f"  # {brief}" if brief else ""
                group_lines.append(f"  {tag:20s} = {val}{comment}")
        if group_lines:
            lines.append(f"# ── {group_name} ──")
            lines.extend(group_lines)
            lines.append("")

    incar_text = "\n".join(lines)
    print("生成的 INCAR:\n")
    print(incar_text)
    return incar_text


# ════════════════════════════════════════════════════════════
# Step 4: 生成 POSCAR
# ════════════════════════════════════════════════════════════

def step4_generate_poscar(sys_info: dict) -> str:
    step_separator("Step 4: 生成 POSCAR")

    lat = sys_info["lattice"]
    a, c = lat["a"], lat["c"]

    # 六方晶格的笛卡尔向量
    import math
    ax, ay = a, 0.0
    bx, by = -a * 0.5, a * math.sqrt(3) / 2
    cx, cy, cz = 0.0, 0.0, c

    # 按元素分组
    from collections import OrderedDict
    elem_order = list(OrderedDict.fromkeys(
        atom["element"] for atom in sys_info["atoms_fractional"]
    ))
    elem_counts = {}
    sorted_atoms = []
    for elem in elem_order:
        atoms = [a for a in sys_info["atoms_fractional"] if a["element"] == elem]
        elem_counts[elem] = len(atoms)
        sorted_atoms.extend(atoms)

    lines = [
        f"{sys_info['formula']} bulk ({sys_info.get('space_group', '')})",
        "1.0",
        f"  {ax:12.8f}  {ay:12.8f}  {0.0:12.8f}",
        f"  {bx:12.8f}  {by:12.8f}  {0.0:12.8f}",
        f"  {cx:12.8f}  {cy:12.8f}  {cz:12.8f}",
        "  " + "  ".join(elem_order),
        "  " + "  ".join(str(elem_counts[e]) for e in elem_order),
        "Direct",
    ]
    for atom in sorted_atoms:
        x, y, z = atom["coords"]
        lines.append(f"  {x:.6f}  {y:.6f}  {z:.6f}")

    poscar_text = "\n".join(lines)
    print("生成的 POSCAR:\n")
    print(poscar_text)
    return poscar_text


# ════════════════════════════════════════════════════════════
# Step 5: 生成 KPOINTS
# ════════════════════════════════════════════════════════════

def step5_generate_kpoints(sys_info: dict, intent: dict) -> str:
    step_separator("Step 5: 生成 KPOINTS")

    lat = sys_info["lattice"]
    a, b, c = lat["a"], lat["b"], lat["c"]

    # 对半导体/绝缘体: k_i ~ 20/a_i; 金属: 30/a_i
    factor = 30 if sys_info.get("is_metal") else 20
    ka = max(1, round(factor / a))
    kb = max(1, round(factor / b))
    kc = max(1, round(factor / c))

    # 确保为偶数或奇数统一 (取偶数更常见)
    def round_even(n):
        return n if n % 2 == 0 else n + 1
    ka, kb, kc = round_even(ka), round_even(kb), round_even(kc)

    print(f"  晶格参数: a={a:.3f}, b={b:.3f}, c={c:.3f} Å")
    print(f"  密度因子: {factor}/a_i")
    print(f"  k-mesh: {ka} x {kb} x {kc}")

    kpoints_text = f"""Automatic mesh
0
Gamma
  {ka}  {kb}  {kc}
  0  0  0"""

    print(f"\n生成的 KPOINTS:\n")
    print(kpoints_text)
    return kpoints_text


# ════════════════════════════════════════════════════════════
# Step 6: POTCAR 指引
# ════════════════════════════════════════════════════════════

def step6_potcar_instruction(potcar_info: dict) -> str:
    step_separator("Step 6: POTCAR 生成指引")

    lines = ["# 按以下顺序拼接 POTCAR (与 POSCAR 元素顺序一致):"]
    for elem, info in potcar_info["potcars"].items():
        pot = info["potcar"]
        lines.append(f"#   cat $VASP_PP_PATH/PBE/{pot}/POTCAR >> POTCAR")

    cmd = "\n".join([
        "cat " + " \\\n    ".join(
            f"$VASP_PP_PATH/PBE/{info['potcar']}/POTCAR"
            for info in potcar_info["potcars"].values()
        ) + " > POTCAR"
    ])

    instruction = "\n".join(lines) + "\n\n# 一行命令:\n" + cmd
    print(instruction)
    return instruction


# ════════════════════════════════════════════════════════════
# Step 7: 校验
# ════════════════════════════════════════════════════════════

def step7_validate(incar_text: str, intent: dict, sys_info: dict, potcar_info: dict):
    step_separator("Step 7: 校验 INCAR")

    # 导入 validator
    sys.path.insert(0, KNOWLEDGE_DIR)
    from validator import parse_incar, validate_incar

    tags = parse_incar(incar_text)
    errors, warnings = validate_incar(
        tags,
        task_type=intent["task_type"],
        system_info={
            "is_metal": sys_info.get("is_metal", False),
            "has_magnetic": sys_info.get("has_magnetic", False),
            "elements": sys_info.get("elements", []),
            "n_atoms": sys_info.get("n_atoms", 0),
            "enmax": potcar_info["max_enmax"],
        }
    )

    if errors:
        print("❌ 错误:")
        for e in errors:
            print(f"   ✗ {e}")
    if warnings:
        print("⚠️  警告:")
        for w in warnings:
            print(f"   ⚠ {w}")
    if not errors and not warnings:
        print("✅ 校验通过，无错误无警告！")

    return errors, warnings


# ════════════════════════════════════════════════════════════
# Step 8: 写出文件
# ════════════════════════════════════════════════════════════

def step8_write_files(incar: str, poscar: str, kpoints: str, potcar_cmd: str):
    step_separator("Step 8: 写出文件")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = {
        "INCAR": incar,
        "POSCAR": poscar,
        "KPOINTS": kpoints,
        "POTCAR_README.sh": potcar_cmd,
    }
    for name, content in files.items():
        path = os.path.join(OUTPUT_DIR, name)
        with open(path, "w") as f:
            f.write(content + "\n")
        print(f"  ✓ {path}")

    print(f"\n所有文件已写入 {OUTPUT_DIR}/")
    print("将 POTCAR 按 POTCAR_README.sh 中的指引生成后即可提交计算。")


# ════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════

def main():
    print("╔════════════════════════════════════════════════════════╗")
    print("║   VASP Input Generator Demo                           ║")
    print("║   用户请求: 对 bulk MoS2 做结构优化 + 范德华校正       ║")
    print("╚════════════════════════════════════════════════════════╝")

    # 1. 意图识别
    intent = step1_parse_intent(USER_REQUEST, SYSTEM_INFO)

    # 2. 选赝势
    potcar_info = step2_select_potcar(SYSTEM_INFO)

    # 3. 生成 INCAR
    incar_text = step3_generate_incar(intent, SYSTEM_INFO, potcar_info)

    # 4. 生成 POSCAR
    poscar_text = step4_generate_poscar(SYSTEM_INFO)

    # 5. 生成 KPOINTS
    kpoints_text = step5_generate_kpoints(SYSTEM_INFO, intent)

    # 6. POTCAR 指引
    potcar_cmd = step6_potcar_instruction(potcar_info)

    # 7. 校验
    errors, warnings = step7_validate(incar_text, intent, SYSTEM_INFO, potcar_info)

    # 8. 写出
    step8_write_files(incar_text, poscar_text, kpoints_text, potcar_cmd)


if __name__ == "__main__":
    main()
