# ABACUS Output Control Parameters

Canonical reference for which **INPUT keywords** produce which **output files**, and for **manual grep** on logs. For scripted extraction and plots after a run, see `matmaster/skills/playground-skills/result-analysis` (`parse_abacus.py`, `plot_publication.py`).

Include in INPUT as needed. Results written to `OUT.ABACUS/`.

| Parameter | Values | Default | Purpose |
|-----------|--------|---------|---------|
| `out_chg` | `0`/`1` | `0` | Charge density → `SPIN1_CHG.cube`. **Required for SCF→NSCF.** |
| `out_band` | `0`/`1` | `0` | Band eigenvalues → `BANDS_1.dat`. For NSCF band structure. |
| `out_dos` | `0`/`1` | `0` | DOS → `DOS1_smearing.dat`. For NSCF DOS. |
| `out_pot` | `0`/`1`/`2` | `0` | Electrostatic potential. `2` → `ElecStaticPot.cube`. |
| `out_stru` | `0`/`1` | `0` | Relaxed structures (`STRU_ION*_D`). For relax/cell-relax. |
| `out_wfc_lcao` | `0`/`1` | `0` | LCAO wavefunction coefficients. For PyATB, Wannier. |
| `cal_force` | `0`/`1` | `0` | Atomic forces. Set `1` for relax or force analysis. |
| `cal_stress` | `0`/`1` | `0` | Stress tensor. Set `1` for cell-relax or EOS. |
| `init_chg` | `atomic`/`file` | `atomic` | Charge init. `file` = read prior SCF. **Required for NSCF.** |
| `nbands` | integer | auto | Number of bands. Must be explicit for NSCF (> occupied). |
| `symmetry` | `0`/`1` | `1` | `0` = disable. **Mandatory for NSCF line-mode k-paths.** |

## ABACUS Output Files

| File | Produced by | Contains |
|------|-------------|----------|
| `running_scf.log` | SCF | Total energy, Fermi energy, convergence, forces, stress |
| `running_nscf.log` | NSCF | Fermi energy, eigenvalue info |
| `SPIN1_CHG.cube` | SCF + `out_chg 1` | Charge density (cube format) |
| `BANDS_1.dat` | NSCF + `out_band 1` | Band eigenvalues along k-path |
| `DOS1_smearing.dat` | NSCF + `out_dos 1` | Density of states |
| `ElecStaticPot.cube` | `out_pot 2` | Electrostatic potential (work function) |
| `STRU_ION*_D` | Relax | Relaxed structure at each ionic step |

## Key grep patterns
- Total energy: `!FINAL_ETOT_IS <energy> eV`
- Fermi energy: `EFERMI = <energy> eV`
- Convergence: `charge density convergence is achieved`
- Forces: lines after `TOTAL-FORCE (eV/Angstrom)`
- Stress: lines after `TOTAL-STRESS (KBAR)`

## Common mistakes
- Forgetting `out_chg 1` in SCF → NSCF with `init_chg file` fails or recomputes SCF
- Leaving `symmetry 1` in NSCF band structure → k-path folded, wrong band plot
