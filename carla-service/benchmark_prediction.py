"""Replay recorded input pairs through a motion-scale/displacement-cap sweep."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import time

from evaluate_trials import validate_alignment
from prediction import DEFAULT_RAFT_WEIGHTS, PredictionView, warp_flow


def load_sample(path):
    import numpy as np
    with np.load(path, allow_pickle=False) as saved:
        if 'previous' not in saved:
            raise ValueError('Missing previous image; record a new trial with Save raw aligned images enabled')
        alignment = json.loads(str(saved['alignment']))
        validate_alignment(alignment)
        interval = alignment['intervalMs'] / 1000
        horizon = alignment['horizonMs']
        if not 0 < interval <= 1 or not 0 < horizon <= 2000:
            raise ValueError('Replay needs a positive horizon and frame interval of at most 1 second')
        images = [saved[key].copy() for key in ('previous', 'delayed', 'reference')]
        if any(im.dtype != np.uint8 or im.ndim != 3 or im.shape[2] != 3 or
               im.shape != images[0].shape for im in images):
            raise ValueError('Expected matching uint8 BGR images')
    return (*images, interval, horizon)


def benchmark(paths, predictor, scales, caps):
    from comparison import image_metrics
    settings = [(scale, cap) for scale in scales for cap in caps]
    rows, skipped = [], []
    for path in paths:
        try:
            previous, delayed, target, interval, horizon = load_sample(path)
        except (ValueError, KeyError, OSError) as error:
            skipped.append({'file': str(path), 'reason': str(error)})
            continue
        # Target is used only for scoring. Compute flow once for the whole sweep.
        started = time.perf_counter()
        flow = predictor.flow(previous, delayed)
        flow_ms = (time.perf_counter() - started) * 1000
        baseline = image_metrics(delayed, target)
        candidates = [('delayed', None, None)] + [
            (f'scale={scale:g},cap={cap if cap is not None else "none"}', scale, cap)
            for scale, cap in settings]
        for name, scale, cap in candidates:
            if scale is None:
                score, capped, elapsed = baseline, 0.0, 0.0
            else:
                started = time.perf_counter()
                predicted, capped = warp_flow(delayed, flow, interval, horizon, scale, cap)
                elapsed = flow_ms + (time.perf_counter() - started) * 1000
                score = image_metrics(predicted, target)
            rows.append({'file': str(path), 'setting': name, 'scale': scale, 'cap': cap,
                         'horizonMs': horizon, **score, 'cappedPercent': capped * 100,
                         'predictionMs': elapsed, 'maeGain': baseline['mae'] - score['mae'],
                         'ssimGain': score['ssim'] - baseline['ssim']})
    summaries = []
    for name in dict.fromkeys(row['setting'] for row in rows):
        group = [row for row in rows if row['setting'] == name]
        summary = {'setting': name, 'scale': group[0]['scale'], 'cap': group[0]['cap'], 'samples': len(group)}
        for metric in ('mae', 'ssim', 'psnr', 'cappedPercent', 'predictionMs', 'maeGain', 'ssimGain'):
            values = [row[metric] for row in group if row[metric] is not None]
            summary[metric] = statistics.mean(values) if values else None
        summary['identicalSamples'] = sum(row['identical'] for row in group)
        summary['maeWinPercent'] = 100 * sum(row['maeGain'] > 1e-9 for row in group) / len(group)
        summary['maeTiePercent'] = 100 * sum(abs(row['maeGain']) <= 1e-9 for row in group) / len(group)
        summaries.append(summary)
    summaries.sort(key=lambda row: row['mae'])
    return rows, summaries, skipped


def cap_value(value):
    if value.lower() == 'none':
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('Use a positive cap or none')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trials', type=Path, nargs='+', help='Completed trial directories')
    parser.add_argument('--output', type=Path, required=True, help='New report directory')
    parser.add_argument('--method', choices=('raft', 'farneback'), default='raft')
    parser.add_argument('--weights', type=Path, default=DEFAULT_RAFT_WEIGHTS)
    parser.add_argument('--device', default='auto')
    parser.add_argument('--raft-iterations', type=int, default=12, help='Match the sender setting for comparable results')
    parser.add_argument('--scales', type=float, nargs='+', default=[0.7, 1.0])
    parser.add_argument('--caps', type=cap_value, nargs='+', default=[80, 160, None])
    args = parser.parse_args()
    if not 1 <= args.raft_iterations <= 32:
        parser.error('--raft-iterations must be between 1 and 32')
    if any(not math.isfinite(scale) or scale < 0 for scale in args.scales):
        parser.error('Scales must be finite and nonnegative')
    if args.output.exists():
        parser.error('Output directory already exists; choose a new report directory')
    if any(not (trial / 'manifest.json').is_file() for trial in args.trials):
        parser.error('Each trial must contain manifest.json')
    paths = sorted({path.resolve() for trial in args.trials for path in trial.glob('frames-*.npz')})
    if not paths:
        parser.error('No saved samples. Enable Save raw aligned images when recording.')
    predictor = PredictionView(args.method, weights=args.weights, device=args.device, iterations=args.raft_iterations)
    rows, summaries, skipped = benchmark(paths, predictor, list(dict.fromkeys(args.scales)), list(dict.fromkeys(args.caps)))
    args.output.mkdir(parents=True)
    report = {'method': args.method, 'raftIterations': args.raft_iterations if args.method == 'raft' else None,
              'weights': str(args.weights) if args.method == 'raft' else None,
              'trials': [str(trial.resolve()) for trial in args.trials],
              'ranking': summaries, 'skipped': skipped,
              'notes': ['Ranked by mean MAE on these samples only; not a validated deployment recommendation.',
                        'Positive gains mean better than unchanged delayed frames. Higher SSIM/PSNR and lower MAE are better.',
                        'Identical images have infinite PSNR, stored as null and excluded from the finite PSNR mean.',
                        'Timing includes shared flow inference plus per-setting warp, excludes scoring, startup and transport.',
                        'Adjacent samples are correlated. Confirm candidate settings on separate drives; image scores do not prove driving benefit.']}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    if rows:
        with (args.output / 'samples.csv').open('w', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = ['# Prediction sweep', '', *report['notes'], '',
             '| Setting | Samples | MAE ↓ | SSIM ↑ | MAE win % | Cap hit % | Prediction ms |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for row in summaries:
        lines.append(f'| {row["setting"]} | {row["samples"]} | {row["mae"]:.4f} | {row["ssim"]:.4f} | {row["maeWinPercent"]:.1f} | {row["cappedPercent"]:.2f} | {row["predictionMs"]:.2f} |')
    lines += ['', f'Skipped samples: {len(skipped)}. See report.json for reasons.']
    (args.output / 'report.md').write_text('\n'.join(lines) + '\n')
    print(f'Report: {args.output / "report.md"}; evaluated {len(paths) - len(skipped)}, skipped {len(skipped)} samples')
    if not rows:
        parser.exit(1, 'No replayable samples; inspect report.json and record new input pairs.\n')


if __name__ == '__main__':
    main()
