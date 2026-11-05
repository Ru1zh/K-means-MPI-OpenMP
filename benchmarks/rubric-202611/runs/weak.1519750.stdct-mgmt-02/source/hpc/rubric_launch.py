#!/usr/bin/env python3
"""Open MPI launcher using the actual verified PBS allocation (no oversubscription)."""
import argparse
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def launch_command(allocation, p, t, command, spread=False):
    layout = json.loads(allocation.read_text())
    c = layout['cores_per_node']
    hosts = list(layout['hosts'])
    if p < 1 or t < 1 or t > c or c % t:
        raise ValueError('Invalid rank/thread layout')
    ranks_per_node = 1 if spread else min(p, c // t)
    nodes = math.ceil(p / ranks_per_node)
    if nodes > len(hosts):
        raise ValueError('Insufficient distinct allocated nodes')
    hostspec = ','.join('%s:%d' % (h, c) for h in hosts[:nodes])
    return ['mpiexec', '--host', hostspec, '--map-by', 'ppr:%d:node' % ranks_per_node,
            '--rank-by', 'slot', '--bind-to', 'none', '-n', str(p),
            sys.executable, str(ROOT / 'hpc/rubric_placement.py'),
            '--allocation', str(allocation.resolve()), '--threads', str(t), '--'] + command


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allocation', type=Path, required=True)
    p.add_argument('--p', type=int, required=True)
    p.add_argument('--t', type=int, required=True)
    p.add_argument('--spread', action='store_true', help='correctness probe: one rank per node')
    p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    command = a.command[1:] if a.command[:1] == ['--'] else a.command
    if not command:
        p.error('missing executable after --')
    argv = launch_command(a.allocation, a.p, a.t, command, a.spread)
    os.execvp(argv[0], argv)


if __name__ == '__main__':
    main()
