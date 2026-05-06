# Materials Playground

A lightweight EvoMaster playground for computational materials tasks.

It is designed as a clean starter template for:

- crystal or molecular structure analysis
- VASP / ASE / pymatgen style workflow planning
- input-file drafting and job-script generation
- simulation result summarization
- literature-assisted materials research

## Structure

```text
playground/materials_playground/
├── core/
│   ├── __init__.py
│   └── playground.py
├── prompts/
│   ├── system_prompt.txt
│   └── user_prompt.txt
└── workspace/
```

## Run

```bash
python run.py --agent materials_playground --config configs/materials_playground/config.yaml --task "Analyze a CIF structure and propose a DFT relaxation workflow"
```

## Typical tasks

- Read a `POSCAR`, `CIF`, or `XYZ` file and summarize the structure
- Draft `INCAR`, `KPOINTS`, and `submit.sh` for a calculation
- Propose a high-throughput screening workflow for candidate materials
- Summarize adsorption, band structure, defect, or formation-energy tasks

## Notes

- This playground is intentionally simple and uses a single `general` agent.
- If you later want MCP tools or multi-agent planning, use this as the base and extend it.
