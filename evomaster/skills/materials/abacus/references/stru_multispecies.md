# ABACUS STRU — Multi-Species Examples

Concrete copy-paste examples for common multi-species systems.
**Always read any provided STRU first** — use its PP/orbital filenames verbatim.

---

## Binary Compound: GaAs (zinc blende, 2 species)

### STRU
```
ATOMIC_SPECIES
Ga 69.723 Ga.upf
As 74.922 As.upf

NUMERICAL_ORBITAL
Ga_gga_9au_100Ry_2s2p2d.orb
As_gga_9au_100Ry_2s2p1d.orb

LATTICE_CONSTANT
1.8897259886

LATTICE_VECTORS
5.653  0.000  0.000
0.000  5.653  0.000
0.000  0.000  5.653

ATOMIC_POSITIONS
Direct
Ga
0.0
4
0.000  0.000  0.000  1 1 1
0.000  0.500  0.500  1 1 1
0.500  0.000  0.500  1 1 1
0.500  0.500  0.000  1 1 1
As
0.0
4
0.250  0.250  0.250  1 1 1
0.250  0.750  0.750  1 1 1
0.750  0.250  0.750  1 1 1
0.750  0.750  0.250  1 1 1
```

### INPUT (key lines)
```
ntype                   2
ecutwfc                 100
basis_type              lcao
```

> **ntype = 2** (Ga + As). Must match ATOMIC_SPECIES count.

---

## Ternary Compound: BaTiO₃ (perovskite, 3 species)

### STRU
```
ATOMIC_SPECIES
Ba 137.327 Ba.upf
Ti 47.867  Ti.upf
O  15.999  O.upf

NUMERICAL_ORBITAL
Ba_gga_10au_100Ry_2s2p2d.orb
Ti_gga_9au_100Ry_2s2p2d1f.orb
O_gga_7au_100Ry_2s2p1d.orb

LATTICE_CONSTANT
1.8897259886

LATTICE_VECTORS
4.000  0.000  0.000
0.000  4.000  0.000
0.000  0.000  4.000

ATOMIC_POSITIONS
Direct
Ba
0.0
1
0.000  0.000  0.000  1 1 1
Ti
0.0
1
0.500  0.500  0.500  1 1 1
O
0.0
3
0.500  0.500  0.000  1 1 1
0.500  0.000  0.500  1 1 1
0.000  0.500  0.500  1 1 1
```

### INPUT (key lines)
```
ntype                   3
ecutwfc                 100
basis_type              lcao
```

> **ntype = 3** (Ba + Ti + O). Always count ALL species.

---

## Slab with Vacuum (e.g., Si(100))

### STRU snippet
```
LATTICE_VECTORS
5.431  0.000  0.000
0.000  5.431  0.000
0.000  0.000  25.000

ATOMIC_POSITIONS
Cartesian_angstrom
Si
0.0
8
0.000  0.000  5.000  1 1 1
...
```

### INPUT (key differences from bulk)
```
ntype                   1
kspacing                0.10 0.10 1.00
```
**Or** use a KPT file with vacuum direction = 1:
```
K_POINTS
0
Gamma
12 12 1 0 0 0
```

> Vacuum direction k = 1 (or `kspacing ... 1.00`). Never use dense k-mesh in vacuum.

---

## Spin-Polarized Magnetic System (e.g., Fe bulk)

### STRU snippet
```
ATOMIC_SPECIES
Fe 55.845 Fe.upf

NUMERICAL_ORBITAL
Fe_gga_9au_100Ry_4s2p2d1f.orb

...

ATOMIC_POSITIONS
Cartesian_angstrom
Fe
2.5
2
0.000  0.000  0.000  1 1 1
1.435  1.435  1.435  1 1 1
```

### INPUT additions
```
nspin                   2
mixing_beta             0.1
mixing_ndim             20
mixing_gg0              1.5
```

> Initial magnetic moment (2.5 μB) is set PER SPECIES in the STRU, not in INPUT.
> Tight mixing (`mixing_beta 0.1`) is essential for spin-polarized convergence.

---

## PP/Orbital Download Sequence

```bash
# 1. Download the universal archive
wget -q "https://store.aissquare.com/datasets/dc875646-a526-41f1-a180-d54b218fc80a/ABACUS-APNS-PPORBs-v1.zip" \
  && unzip -qo ABACUS-APNS-PPORBs-v1.zip

# 2. Copy files for EACH element in ATOMIC_SPECIES
#    Use exact filenames from the STRU if one was provided.
cp apns-pseudopotentials-v1/Ba.upf .
cp apns-pseudopotentials-v1/Ti.upf .
cp apns-pseudopotentials-v1/O.upf .
cp apns-orbitals-efficiency-v1/Ba_gga_10au_100Ry_2s2p2d.orb .
cp apns-orbitals-efficiency-v1/Ti_gga_9au_100Ry_2s2p2d1f.orb .
cp apns-orbitals-efficiency-v1/O_gga_7au_100Ry_2s2p1d.orb .

# 3. Verify all files present
ls *.upf *.orb
```

> **Critical**: If a STRU names `Fe_ONCV_PBE-1.0.upf`, you MUST use that exact
> file. Do NOT rename or substitute.

---

### APNS Archive Structure

The downloaded archive has two directories:

- `apns-pseudopotentials-v1/` — PP files named `<Element>.upf` (e.g., `Si.upf`, `Fe.upf`, `Mo.upf`)
- `apns-orbitals-efficiency-v1/` — Orbital files named `<Element>_gga_<radius>au_100Ry_<config>.orb`

**Common orbital filenames** (efficiency basis; use when STRU doesn't specify):

| Element | Orbital file |
|---------|-------------|
| H  | `H_gga_6au_100Ry_2s1p.orb` |
| C  | `C_gga_7au_100Ry_2s2p1d.orb` |
| N  | `N_gga_7au_100Ry_2s2p1d.orb` |
| O  | `O_gga_7au_100Ry_2s2p1d.orb` |
| Si | `Si_gga_8au_100Ry_2s2p1d.orb` |
| Fe | `Fe_gga_9au_100Ry_4s2p2d1f.orb` |
| Cu | `Cu_gga_9au_100Ry_4s2p2d1f.orb` |
| Mo | `Mo_gga_9au_100Ry_4s2p2d1f.orb` |
| Ti | `Ti_gga_9au_100Ry_2s2p2d1f.orb` |
| Ba | `Ba_gga_10au_100Ry_2s2p2d.orb` |
| Ga | `Ga_gga_9au_100Ry_2s2p2d.orb` |
| As | `As_gga_9au_100Ry_2s2p1d.orb` |
| Zn | `Zn_gga_9au_100Ry_4s2p2d1f.orb` |
| S  | `S_gga_8au_100Ry_2s2p1d.orb` |
| Al | `Al_gga_9au_100Ry_2s2p1d.orb` |

> **If your element is not listed**: run `ls apns-orbitals-efficiency-v1/<Element>_gga_*` to discover the exact filename. Pattern: `<Element>_gga_<R>au_100Ry_<config>.orb`.

---

## CIF → STRU Conversion

When starting from CIF/POSCAR, convert first — do NOT hand-write STRU:
```bash
uv run python ${STRUCTURE_MANAGER}/scripts/convert_format.py \
  --input structure.cif --output STRU --output-fmt abacus/stru
```
Then **read the generated STRU** to verify:
1. ntype matches element count
2. PP filenames are reasonable (you may need to rename to match downloaded files)
3. LATTICE_CONSTANT = 1.8897259886

---

## Cross-Check Checklist (After All Files Ready)

```bash
# Count species in STRU
grep -c "\.upf" STRU   # → must equal ntype in INPUT

# Verify file references in INPUT
grep "stru_file\|kpoint_file" INPUT

# Verify all referenced files exist
ls STRU KPT INPUT *.upf *.orb
```

| Check                              | How to verify                        |
|------------------------------------|--------------------------------------|
| ntype = ATOMIC_SPECIES count       | `grep -c ".upf" STRU` vs INPUT      |
| PP files exist                     | `ls *.upf`                           |
| Orbital files exist (LCAO)         | `ls *.orb`                           |
| stru_file points to actual STRU    | `grep stru_file INPUT`               |
| kpoint_file points to actual KPT   | `grep kpoint_file INPUT`             |
| ecutwfc = 100 (LCAO baseline)      | `grep ecutwfc INPUT`                 |
| smearing_sigma = 0.01              | `grep smearing_sigma INPUT`          |
| scf_thr = 1.0e-7                   | `grep scf_thr INPUT`                 |

> If you switch to `basis_type pw`, use `ecutwfc 50` as the default starting point, then tune by convergence tests when needed.
