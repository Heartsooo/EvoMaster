# manuscript-scribe: computational_report profile

**Profile-specific writing rules for `computational_report`.**
These supplement (do not replace) the shared rules in `SKILL.md`.

---

## Overview

The `computational_report` profile is for lean write-ups of computational studies (DFT, MD, phonons, band structure, formation energy, elastic constants, etc.). Three sections only: **Methods**, **Results and Discussion**, **References**. Strict profile — no extra sections.

---

## Content and expression rules

### No raw input keywords
Never use software input keywords, variable names, or file names in prose:

| Do NOT write | Write instead |
|---|---|
| `RUN_TYPE ENERGY`, `CUTOFF 600` | "single-point total-energy calculation", "plane-wave cutoff of 600 Ry" |
| `EPS_SCF 1e-6` | "self-consistent convergence threshold of 10^{−6} Ha" |
| `&DFT ... &END DFT` | "DFT calculation block" |
| `cp2k.inp`, `output.log`, `*.pdos` | "the input file", "the output log", "the projected DOS data" |
| `HOCO_CUBE.cube`, `LUCO_CUBE.cube` | "the HOCO orbital cube file", "the LUCO orbital cube file" |

### Mechanism-oriented narrative (mandatory)
Build toward physical interpretation — do not just list numbers:
- PDOS decomposition → orbital character assignment → charge-transfer mechanism → spectroscopic prediction.
- Example: "The PDOS analysis shows dominant Cu-3d character at the HOCO energy, indicating a metal-centered HOMO analog. The spatial overlap with the ligand π* orbital supports an MLCT assignment for the lowest excited state."
- Do not write: "The Cu d-band is at −2.3 eV. The N p-band is at −1.8 eV."

---

## Terminology rules for periodic systems

- **Use HOCO / LUCO** (highest occupied / lowest unoccupied crystal orbital), NOT HOMO / LUMO. At first use, add: "In periodic systems, these correspond to crystal orbitals denoted HOCO and LUCO."
- **Use VBM / CBM** (valence-band maximum / conduction-band minimum) for band-edge terminology, NOT "HOMO energy" / "LUMO energy".
- Define every abbreviation at first use: DFT, PDOS, PBE, PAW, etc.

---

## Formula requirements for DFT methods

When describing the computational method, include the relevant formulas where they clarify the approach:

- **Exchange-correlation functional**: cite the XC functional (PBE, HSE06, etc.) with the original paper and provide the form if non-standard.
- **Hubbard U correction**: if used, write the formula *E*_{DFT+U} = *E*_{DFT} + (*U* − *J*)/2 Σ_{σ,i} [*n*^{σ}_{i} − (*n*^{σ}_{i})^{2}], where *U* is the on-site Coulomb parameter, *J* the exchange parameter, and *n*^{σ}_{i} the orbital occupancy.
- **Dispersion correction**: if vdW-D3 or similar is used, state the correction form and cite the method paper.
- **Convergence criteria**: express as equations or thresholds: "until |*F*_{max}| < 0.02 eV/Å and energy difference < 10^{−5} eV".
- **Key observables**: formation energy Δ*E*_{f} = (*E*_{compound} − Σ *n*_{i} *E*_{i,ref}) / *N*_{atoms} — write explicitly with symbol definitions.

Every symbol explained on first appearance in the text.

---

## Typographic conventions (DFT-specific)

- Italic physical quantities: *U*_{eff}, *E*_{F}, *E*_{g}, *k*_{B}.
- **Descriptive subscripts roman** (not italic): *E*_{F} ("F" roman for Fermi), *U*_{eff} ("eff" roman).
- En-dash for ranges: 1.88–1.89 Å, not 1.88-1.89 Å.
- Minus sign "−" (U+2212) for negatives: −0.5 eV, not -0.5 eV.
- Significant figures: bond lengths 2 decimals (1.89 Å), band gaps 2 decimals (2.34 eV), lattice parameters 3-4 decimals.

---

## De-AIGC rules (mandatory — full apply)

Full guide: `Skill action=get_reference reference_name="de_aigc_style_guide.md"` (in `skills/_common/reference/`).

**Key rules for computational reports:**
1. Replace "The results demonstrate the superior performance of..." → state what the results show numerically.
2. Replace mechanism adjectives ("strong bonding", "significant overlap") with measurable evidence.
3. Calibrate: `indicate`, `support`, `constrain` — not `prove`, `establish`, `confirm beyond doubt`.
4. Remove `Notably,`, `Remarkably,`, `Interestingly,` — let the data carry the weight.
5. Gap Analysis (if included): order by impact, cite specific evidence for each gap.

After drafting each section, apply the 5-pass De-AIGC checklist: claim calibration → specificity upgrade → compression → redundancy removal → tone scan.
