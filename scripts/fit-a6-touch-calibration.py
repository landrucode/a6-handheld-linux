#!/usr/bin/env python3
"""Fit raw normalized evdev coordinates to five physical screen targets."""
import argparse
import json
import math
import os
from pathlib import Path


def solve(rows, values):
    m = [[sum(r[i]*r[j] for r in rows) for j in range(3)] +
         [sum(r[i]*v for r, v in zip(rows, values))] for i in range(3)]
    for i in range(3):
        pivot = max(range(i, 3), key=lambda k: abs(m[k][i]))
        m[i], m[pivot] = m[pivot], m[i]
        if abs(m[i][i]) < 1e-10:
            raise ValueError('Degenerate touch points; repeat the five targets')
        scale = m[i][i]
        m[i] = [v/scale for v in m[i]]
        for j in range(3):
            if j != i:
                scale = m[j][i]
                m[j] = [a-scale*b for a, b in zip(m[j], m[i])]
    return [r[3] for r in m]


def fit(samples):
    if len(samples) != 5 or [s['point'] for s in samples] != list(range(5)):
        raise ValueError('Need exactly five ordered point samples')
    screen = samples[0]['screen']
    if any(s['screen'] != screen for s in samples):
        raise ValueError('Display dimensions changed during capture')
    rows = [s['raw']+[1] for s in samples]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for r in rows for v in r):
        raise ValueError('Invalid normalized raw input')
    matrix = solve(rows, [s['target'][0] for s in samples]) + solve(rows, [s['target'][1] for s in samples])
    errors = [math.hypot((sum(a*b for a,b in zip(matrix[:3],r))-s['target'][0])*screen[0],
                         (sum(a*b for a,b in zip(matrix[3:],r))-s['target'][1])*screen[1]) for r,s in zip(rows,samples)]
    if max(errors) > 20:
        raise ValueError(f'Five-point residual {max(errors):.1f}px exceeds 20px; repeat calibration')
    if abs(matrix[0]*matrix[4]-matrix[1]*matrix[3]) < .1:
        raise ValueError('Implausible calibration scale')
    return {'matrix': matrix, 'residual_pixels': errors, 'screen': screen,
            'hyprland_touch_transform': -1,
            'limits': 'Five-point affine fit; physical edge validation still required'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('samples', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    result = fit([json.loads(line) for line in args.samples.read_text().splitlines() if line.strip()])
    with os.fdopen(os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('LIBINPUT_CALIBRATION_MATRIX='+' '.join(f'{x:.9f}' for x in result['matrix']))
    print(f"Maximum fit residual: {max(result['residual_pixels']):.1f}px")


if __name__ == '__main__':
    main()
