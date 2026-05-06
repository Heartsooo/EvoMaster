# ABACUS STRU File Format (Detailed)

The STRU file has five sections, in order:

## ATOMIC_SPECIES
```
ATOMIC_SPECIES
<Label> <Mass> <PseudopotentialFile>
```
One line per species. For ghost/empty atoms, create a separate species entry (e.g. `X_empty` where X is the element) with the same PP and orbital files but treat it as a distinct `ntype`.

## NUMERICAL_ORBITAL (LCAO only)
```
NUMERICAL_ORBITAL
<OrbitalFile_for_species1>
<OrbitalFile_for_species2>
```
One `.orb` file per species, same order as ATOMIC_SPECIES. Required for `basis_type lcao`. Omit for `basis_type pw`.

## LATTICE_CONSTANT and LATTICE_VECTORS
```
LATTICE_CONSTANT
1.8897259886  // 1 Angstrom in Bohr

LATTICE_VECTORS
a1x  a1y  a1z
a2x  a2y  a2z
a3x  a3y  a3z
```
Using `1.8897259886` means vectors are in Angstrom.

## ATOMIC_POSITIONS
```
ATOMIC_POSITIONS
<CoordinateType>
<Label>
<InitialMagneticMoment>
<NumberOfAtoms>
x1 y1 z1  m mx my mz
```
- `CoordinateType`: `Direct` (fractional), `Cartesian_angstrom`, `Cartesian_au`, `Cartesian`
- `m mx my mz`: mobility; `1 1 1` = free, `0 0 0` = frozen
- `InitialMagneticMoment`: Bohr magnetons. `0.0` for non-magnetic.
- For multiple species: repeat label/moment/count/coords block per species, same order as ATOMIC_SPECIES.

**Multi-species example** (real atoms + ghost atoms for BSSE):
```
ATOMIC_POSITIONS
Cartesian_angstrom
X
2.0
4
0.000  0.000  0.000  1 1 1
1.435  1.435  1.435  1 1 1
0.000  2.870  0.000  1 1 1
2.870  0.000  0.000  1 1 1
X_empty
0.0
2
0.000  0.000  4.300  0 0 0
1.435  1.435  5.735  0 0 0
```
Replace `X` / `X_empty` with the actual element name (e.g. Fe, Mo, Cu).

---

## Ghost/Empty Atoms for BSSE Correction (LCAO)

LCAO numerical orbitals are atom-centered. Removing an atom (vacancy) or surface boundary removes basis functions → **BSSE**.

**Fix**: ghost atoms contribute basis functions but zero valence charge and zero magnetic moment:
1. `ATOMIC_SPECIES`: add ghost species (e.g. `X_empty`) with **same** `.upf` and `.orb` as the real species
2. `NUMERICAL_ORBITAL`: add same `.orb` for ghost species
3. `INPUT`: set `ntype` = total species count (real + ghost)
4. `ATOMIC_POSITIONS`: ghost atoms with moment `0.0`, mobility `0 0 0`

**Example** (generic element X with vacancy):
```
ATOMIC_SPECIES
X       <mass>  X.upf
X_empty <mass>  X.upf

NUMERICAL_ORBITAL
X_orb.orb
X_orb.orb
```
INPUT: `ntype 2`. For magnetic elements, add `nspin 2`.

**Surface slab**: place empty atoms ~2.0 A from outermost real atoms, in vacuum on both sides.
