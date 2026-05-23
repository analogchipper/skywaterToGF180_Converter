# Sky130 → GF180MCU Xschem Converter

A web-based tool that converts Xschem `.sch` schematics from the **Skywater 130nm (Sky130)** PDK to the **GlobalFoundries 180nm (GF180MCU)** PDK.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![Flask](https://img.shields.io/badge/Flask-3.1-green) ![PDK](https://img.shields.io/badge/PDK-GF180MCU--D-orange)

---

## What it converts

| Property | Sky130 | GF180MCU |
|---|---|---|
| Symbol path | `sky130_fd_pr/pfet_01v8.sym` | `symbols/pfet_03v3.sym` |
| Model name | `pfet_01v8` / `nfet_01v8` | `pfet_03v3` / `nfet_03v3` |
| W/L units | nm integer (e.g. `70`) | µm with `u` suffix (e.g. `0.44u`) |
| W/L scaling | — | Ratio-preserved scale-up to GF180 minimums |
| Overlap constant | `0.29` | `0.18u` |
| Expression format | `expr('...')` | `'...'` |
| Multiplier param | `mult=` | `m=` |

> **W/L ratio preservation**: If a dimension is below GF180 minimums, both W and L are scaled up together so the W/L ratio stays exactly the same. This keeps the bias point and gm/Id characteristics intact.

---

## Run locally

```bash
git clone <your-repo-url>
cd sky130_converter
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

## Deploy to Railway (public URL)

See DEPLOY.md for step-by-step instructions.

---

## Usage

1. Open the app in your browser
2. Drag and drop your Sky130 `.sch` file
3. Set GF180MCU minimum W and L for NMOS and PMOS
4. Click **Convert Schematic**
5. Review the change log and device summary
6. Download the converted `.sch` and open in Xschem

---

## Supported Sky130 devices

| Sky130 Symbol | → | GF180 Symbol |
|---|---|---|
| `pfet_01v8` | → | `pfet_03v3` |
| `nfet_01v8` | → | `nfet_03v3` |
| `pfet_01v8_hvt` | → | `pfet_03v3` |
| `nfet_01v8_hvt` | → | `nfet_03v3` |
| `pfet_g5v0d10v5` | → | `pfet_06v0` |
| `nfet_g5v0d10v5` | → | `nfet_06v0` |

---

## After conversion

1. Open the output `.sch` in Xschem
2. Verify `PDK_ROOT` / `.xschemrc` points to your GF180MCU install
3. Re-run NGspice and compare DC operating points
4. Any device marked **Scaled** had its W/L adjusted — verify bias current

---

Built for the GF180MCU-D PDK (gf180mcu_fd_pr). Symbol paths verified against real GF180 Xschem schematics.
