# Electric Field, Dipole Correction, and Electrostatic Potential

## Dipole Correction Only (no finite field)
```
INPUT_PARAMETERS
efield_flag 1
dip_cor_flag 1
efield_dir 2
efield_pos_max 0.0
efield_pos_dec 0.1
efield_amp 0.0
```
- `efield_flag 1` + `dip_cor_flag 1` + `efield_amp 0.0` = pure dipole correction.
- `efield_dir`: 0=x, 1=y, 2=z. Set to vacuum direction.
- `efield_pos_max`, `efield_pos_dec`: position and decay (fractional coords) of sawtooth correction in vacuum.

## Finite External Electric Field
```
INPUT_PARAMETERS
efield_flag 1
efield_dir 2
efield_amp 0.0019440124
efield_pos_max 0.95
efield_pos_dec 0.10
```
- `efield_amp`: field in a.u. (1 a.u. = 51.4 V/A). Typical: ~1e-3 a.u.
- Combine with `dip_cor_flag 1` for dipole correction under finite field.

## Gate Field

Complete gate-field INPUT (write all in one file):
```
INPUT_PARAMETERS
calculation scf
basis_type lcao
ecutwfc 100
scf_thr 1.0e-7
scf_nmax 200
smearing_method gauss
smearing_sigma 0.01
mixing_type broyden
mixing_beta 0.4
out_pot 2
efield_flag 1
dip_cor_flag 1
efield_dir 2
efield_pos_max 0.95
efield_pos_dec 0.10
efield_amp 0.0
gate_flag 1
zgate 0.7
nelec 8
block 1
block_down 0.45
block_up 0.55
block_height 0.1
```
For `basis_type pw`, use `ecutwfc 50` as the recommended default and increase only if convergence checks indicate it is necessary.
- `out_pot 2`: output electrostatic potential (essential for gate analysis)
- `mixing_type broyden` + `mixing_beta 0.4`: recommended for slab/surface SCF convergence
- `gate_flag 1`: compensating charge at `zgate` (fractional z, in vacuum)
- `nelec`: **count electrons from your system first**. Set to neutral count by default.
- `block 1` + `block_down/up/height`: potential barrier preventing electron spillage
- `zgate`, `block_down/up`: fractional z — **adjust for your slab geometry**

## Electrostatic Potential Output

```
INPUT_PARAMETERS
out_pot 2
```
- `out_pot 0`: no output (default)
- `out_pot 1`: local ionic potential
- `out_pot 2`: total Hartree+local → `ElecStaticPot.cube`. Needed for work function (average along normal, compare vacuum to Fermi energy).
