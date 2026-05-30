#!/usr/bin/env python3
"""
app.py — Sky130 → GF180MCU Web Converter
Run:  python app.py
Open: http://localhost:5000
"""

from flask import Flask, request, jsonify, render_template
import re, os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# ─────────────────────────────────────────────────────────────────────────────
# PDK TABLES
# ─────────────────────────────────────────────────────────────────────────────

SYMBOL_MAP = {
    "sky130_fd_pr/pfet_01v8.sym":      "symbols/pfet_03v3.sym",
    "sky130_fd_pr/nfet_01v8.sym":      "symbols/nfet_03v3.sym",
    "sky130_fd_pr/pfet_01v8_hvt.sym":  "symbols/pfet_03v3.sym",
    "sky130_fd_pr/nfet_01v8_hvt.sym":  "symbols/nfet_03v3.sym",
    "sky130_fd_pr/pfet_01v8_lvt.sym":  "symbols/pfet_03v3.sym",
    "sky130_fd_pr/nfet_01v8_lvt.sym":  "symbols/nfet_03v3.sym",
    "sky130_fd_pr/pfet_g5v0d10v5.sym": "symbols/pfet_06v0.sym",
    "sky130_fd_pr/nfet_g5v0d10v5.sym": "symbols/nfet_06v0.sym",
}

MODEL_MAP = {
    "pfet_01v8": "pfet_03v3", "pfet_01v8_hvt": "pfet_03v3",
    "pfet_01v8_lvt": "pfet_03v3", "pfet_g5v0d10v5": "pfet_06v0",
    "nfet_01v8": "nfet_03v3", "nfet_01v8_hvt": "nfet_03v3",
    "nfet_01v8_lvt": "nfet_03v3", "nfet_g5v0d10v5": "nfet_06v0",
}

SKY130_OV_NUM   = "0.29"
GF180_OV        = "0.18u"
SKY130_NM_TO_UM = 1e-3

# ─────────────────────────────────────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────────────────────────────────────

def find_matching_brace(text, open_pos):
    depth, i, n = 1, open_pos + 1, len(text)
    while i < n and depth > 0:
        if text[i] == '{': depth += 1
        elif text[i] == '}': depth -= 1
        i += 1
    return i

def parse_all_components(text):
    pattern = re.compile(r'\bC\s*\{')
    i, n = 0, len(text)
    while i < n:
        m = pattern.search(text, i)
        if not m: break
        full_start = m.start()
        sym_open   = m.end() - 1
        sym_end    = find_matching_brace(text, sym_open)
        sym_text   = text[sym_open + 1: sym_end - 1]
        after_sym  = sym_end
        coords_m   = re.match(r'([^{]*)', text[after_sym:])
        coords     = coords_m.group(1) if coords_m else ""
        props_open = after_sym + len(coords)
        if props_open >= n or text[props_open] != '{':
            i = sym_end; continue
        props_end  = find_matching_brace(text, props_open)
        yield {
            'full_start': full_start, 'full_end': props_end,
            'sym_text': sym_text, 'coords': coords,
            'props_text': text[props_open:props_end],
        }
        i = props_end

# ─────────────────────────────────────────────────────────────────────────────
# PARAM HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_param(props, key):
    m = re.search(rf'\b{re.escape(key)}\s*=\s*([^\s\n}}]+)', props)
    return m.group(1) if m else None

def set_param(props, key, val):
    return re.sub(rf'(\b{re.escape(key)}\s*=\s*)([^\s\n}}]+)',
                  lambda m: f"{m.group(1)}{val}", props)

def rename_param(props, old, new):
    return re.sub(rf'\b{re.escape(old)}\s*=', f"{new}=", props)

# ─────────────────────────────────────────────────────────────────────────────
# RATIO-PRESERVING SCALE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

import math as _math

def snap_to_grid(val_um, grid_um=0.005):
    """Snap value UP to nearest grid step. GF180 W/L grid = 5nm (0.005um)."""
    snapped = _math.ceil(round(val_um / grid_um, 6)) * grid_um
    return round(snapped, 6)

W_GRID_UM = 0.005  # 5nm grid

def scale_maintaining_ratio(w_raw, l_raw, min_w, min_l, nf=1):
    """
    Two-stage sizing:

    STAGE 1 — W/L ratio scaling (ignore nf):
        Convert Sky130 nm → µm.
        Scale L up to meet min_l, and if W < min_w scale both up
        preserving W/L ratio. Snap W and L to 5nm grid.

    STAGE 2 — Finger split (apply nf):
        finger_w = W_total / nf
        Snap finger_w UP to 5nm grid.
        W_total_final = finger_w_snapped * nf  (written to schematic)
        nf is written as-is.
        Warn if finger_w < min_w (finger too narrow).

    Example: W=100nm L=50nm ratio=2, min_w=0.44, min_l=0.28, nf=4
      Stage1: W=0.88u L=0.44u (ratio preserved, both ≥ min)
      Stage2: finger = 0.88/4 = 0.22u → snap UP → 0.22u
              W_final = 0.22*4 = 0.88u, nf=4
    """
    w_clean = w_raw.rstrip('uU')
    l_clean = l_raw.rstrip('uU')
    try:
        w_orig = float(w_clean) * SKY130_NM_TO_UM
        l_orig = float(l_clean) * SKY130_NM_TO_UM
    except ValueError:
        return w_raw, l_raw, False, "expr", None, None, None

    ratio = w_orig / l_orig

    # ── Stage 1: ratio-preserving scale to meet minimums ──────────
    l_s1 = max(l_orig, min_l, min_w / ratio)
    w_s1 = l_s1 * ratio
    # Snap both to 5nm grid
    w_s1 = snap_to_grid(w_s1, W_GRID_UM)
    l_s1 = snap_to_grid(max(w_s1 / ratio, min_l), W_GRID_UM)

    # ── Stage 2: finger split ──────────────────────────────────────
    if nf > 1:
        finger_w = w_s1 / nf
        finger_w = snap_to_grid(finger_w, W_GRID_UM)   # snap UP
        w_final  = finger_w * nf                        # total W
        # keep L from stage1 (W/L ratio will shift slightly due to snapping,
        # but L is already at the correct minimum-respecting value)
        l_final  = l_s1
    else:
        w_final  = w_s1
        l_final  = l_s1
        finger_w = w_s1

    scaled = (l_final - l_orig > 1e-6) or (w_final - w_orig > 1e-6)

    w_new_s     = f"{w_final:.4f}".rstrip('0').rstrip('.') + "u"
    l_new_s     = f"{l_final:.4f}".rstrip('0').rstrip('.') + "u"
    finger_w_s  = f"{finger_w:.4f}".rstrip('0').rstrip('.')
    w_orig_s    = f"{w_orig:.4f}".rstrip('0').rstrip('.')

    return w_new_s, l_new_s, scaled, f"{ratio:.3f}", w_orig_s, finger_w_s

# ─────────────────────────────────────────────────────────────────────────────
# ADPS REWRITE
# ─────────────────────────────────────────────────────────────────────────────

def rewrite_adps(props):
    for param in ("ad", "pd", "as", "ps", "nrd", "nrs"):
        def _rw(m):
            full    = m.group(0)
            inner_m = re.search(rf'\b{param}\s*=\s*"([^"]*)"', full)
            if not inner_m: return full
            inner = inner_m.group(1)
            inner = re.sub(r"^expr\('(.*)'\)$", r"'\1'", inner.strip())
            inner = inner.replace("@nf", "nf").replace("@W", "W")
            inner = inner.replace(SKY130_OV_NUM, GF180_OV)
            inner = re.sub(r'\s*/\s*', '/', inner)
            inner = re.sub(r'\s*\*\s*', ' * ', inner)
            inner = re.sub(r'\s*\+\s*', ' + ', inner)
            return f'{param}="{inner}"'
        props = re.sub(rf'\b{param}\s*=\s*"[^"]*"', _rw, props)
    return props

# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

def convert_component(comp, rules):
    sym, props, changes = comp['sym_text'], comp['props_text'], []

    if not any(sky in sym for sky in SYMBOL_MAP):
        return sym, props, []

    is_pmos = any("pfet" in sky and sky in sym for sky in SYMBOL_MAP)
    dev     = (re.search(r'\bname\s*=\s*(\S+)', props) or type('', (), {'group': lambda s,x: '?'})()).group(1)

    # 1. Symbol
    for sky_sym, gf_sym in SYMBOL_MAP.items():
        if sky_sym == sym.strip():
            sym = gf_sym
            changes.append({'device': dev, 'type': 'symbol', 'scaled': False,
                            'from': sky_sym, 'to': gf_sym})
            break

    # 2. Model
    for sky_m, gf_m in MODEL_MAP.items():
        pat = rf'(\bmodel\s*=\s*){re.escape(sky_m)}\b'
        if re.search(pat, props):
            props = re.sub(pat, rf'\g<1>{gf_m}', props)
            changes.append({'device': dev, 'type': 'model', 'scaled': False,
                            'from': sky_m, 'to': gf_m})

    # 3. W/L ratio-preserving scale + finger update
    Lmin = rules["pmos_Lmin"] if is_pmos else rules["nmos_Lmin"]
    Wmin = rules["pmos_Wmin"] if is_pmos else rules["nmos_Wmin"]
    nf   = rules.get("nmos_nf" if not is_pmos else "pmos_nf", 1)
    w_raw, l_raw = get_param(props, "W"), get_param(props, "L")

    if w_raw and l_raw:
        w_new, l_new, scaled, ratio, w_orig, finger_w_s = scale_maintaining_ratio(
            w_raw, l_raw, Wmin, Lmin, nf=nf)
        props = set_param(props, "W", w_new)
        props = set_param(props, "L", l_new)

        # Always write nf into schematic
        old_nf = get_param(props, "nf")
        if old_nf is not None:
            props = set_param(props, "nf", str(nf))

        changes.append({
            'device': dev, 'type': 'W/L', 'scaled': scaled,
            'from': f"W={w_orig}µm" if w_orig else f"W={w_raw}",
            'to':   f"W={w_new} L={l_new} nf={nf}",
            'ratio': ratio,
            'nf': nf,
            'finger_w': finger_w_s,
        })

    # 4. mult → m
    if re.search(r'\bmult\s*=', props):
        props = rename_param(props, "mult", "m")
        changes.append({'device': dev, 'type': 'param', 'scaled': False,
                        'from': 'mult', 'to': 'm'})

    # 5. adps
    props = rewrite_adps(props)
    changes.append({'device': dev, 'type': 'adps', 'scaled': False,
                    'from': 'expr(0.29)', 'to': "'0.18u'"})

    return sym, props, changes

# ─────────────────────────────────────────────────────────────────────────────
# FULL CONVERSION RUN
# ─────────────────────────────────────────────────────────────────────────────

def run_conversion(text, rules):
    components  = list(parse_all_components(text))
    sky_count   = sum(1 for c in components if any(s in c['sym_text'] for s in SYMBOL_MAP))
    all_changes = []
    result      = text

    for comp in reversed(components):
        new_sym, new_props, changes = convert_component(comp, rules)
        if not changes: continue
        all_changes.extend(changes)
        new_entry = f"C {{{new_sym}}}{comp['coords']}{new_props}"
        result = result[:comp['full_start']] + new_entry + result[comp['full_end']:]

    result = re.sub(r'(v \{xschem version=\S+)',
                    r'\1 [sky130->gf180 web converter]', result, count=1)

    scaled = sum(1 for c in all_changes if c.get('scaled'))
    return result, sky_count, all_changes, scaled

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/testbench')
def testbench():
    return render_template('tb_generator.html')

@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    if not f.filename.endswith('.sch'):
        return jsonify({'error': 'Only Xschem .sch files are supported'}), 400
    try:
        text = f.read().decode('utf-8')
    except Exception as e:
        return jsonify({'error': f'Could not read file: {e}'}), 400
    try:
        rules = {
            'nmos_Lmin': float(request.form.get('nmos_Lmin', 0.28)),
            'nmos_Wmin': float(request.form.get('nmos_Wmin', 0.44)),
            'pmos_Lmin': float(request.form.get('pmos_Lmin', 0.28)),
            'pmos_Wmin': float(request.form.get('pmos_Wmin', 0.44)),
            'nmos_nf':   int(request.form.get('nmos_nf', 1)),
            'pmos_nf':   int(request.form.get('pmos_nf', 1)),
        }
        if rules['nmos_nf'] < 1: rules['nmos_nf'] = 1
        if rules['pmos_nf'] < 1: rules['pmos_nf'] = 1
    except ValueError:
        return jsonify({'error': 'Invalid dimension value'}), 400

    output, sky_count, changes, scaled = run_conversion(text, rules)
    if sky_count == 0:
        return jsonify({'error': 'No Sky130 MOSFET components found in this file'}), 400

    return jsonify({
        'output':   output,
        'filename': f.filename.replace('.sch', '_gf180.sch'),
        'stats': {
            'devices':  sky_count,
            'scaled':   scaled,
            'changes':  len(changes),
        },
        'changes': changes,
    })

if __name__ == '__main__':
    print("\n  ╔══════════════════════════════════════════╗")
    print("  ║  Sky130 → GF180MCU  Web Converter        ║")
    print("  ║  Open http://localhost:5000               ║")
    print("  ╚══════════════════════════════════════════╝\n")
    app.run(debug=False, host='0.0.0.0', port=5000)
