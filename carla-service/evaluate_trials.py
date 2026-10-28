"""Evaluate aligned raw images and sender-clock task events, without CARLA."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

ALIGNMENT = ('epoch', 'revision', 'referenceFrame', 'delayedFrame', 'previousFrame',
             'referenceTimestamp', 'delayedTimestamp', 'previousTimestamp', 'delayMs', 'horizonMs', 'intervalMs')


def validate_alignment(frame):
    def finite(key):
        value = frame.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('missing/invalid ' + key)
        return value
    target, source = finite('referenceTimestamp'), finite('delayedTimestamp')
    delay, horizon = finite('delayMs'), finite('horizonMs')
    if delay not in (0, 100, 200, 500, 800) or source > target - delay / 1000 + 1e-8:
        raise ValueError('delayed image is newer than the injected-delay cutoff')
    if abs((target - source) * 1000 - horizon) > 1e-5:
        raise ValueError('prediction horizon does not match source/target timestamps')
    if finite('delayedFrame') > finite('referenceFrame'):
        raise ValueError('future source frame')
    previous = frame.get('previousTimestamp')
    if previous is not None:
        previous = finite('previousTimestamp')
        if previous >= source or finite('previousFrame') >= frame['delayedFrame']:
            raise ValueError('prediction history is not strictly earlier')
        if abs((source - previous) * 1000 - finite('intervalMs')) > 1e-5:
            raise ValueError('frame-pair interval does not match timestamps')
    elif horizon > 1e-6 and frame.get('metrics', {}).get('predicted'):
        raise ValueError('prediction has no earlier observation')


def evaluate(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text())
    rows = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines()]
    # The evaluation worker samples independently of video delivery.
    frames = [r['data'] for r in rows if r.get('kind') == 'frame:evaluation']
    if not frames:
        frames = [r['data'] for r in rows if r.get('kind') == 'frame' and r['data'].get('metrics')]
    valid, paired, worse, errors = [], [], [], []
    for frame in frames:
        try:
            validate_alignment(frame)
            dm, pm = frame.get('metrics', {}).get('delayed'), frame.get('metrics', {}).get('predicted')
            sample = frame.get('sampleFile')
            if sample:
                if Path(sample).name != sample:
                    raise ValueError('sample path must stay inside the trial directory')
                import numpy as np
                from comparison import image_metrics
                with np.load(folder / sample, allow_pickle=False) as arrays:
                    alignment = json.loads(str(arrays['alignment']))
                    if any(alignment.get(key) != frame.get(key) for key in ALIGNMENT):
                        raise ValueError('raw image identifiers/timestamps do not match the logged frame')
                    dm = image_metrics(arrays['delayed'], arrays['reference'])
                    pm = image_metrics(arrays['predicted'], arrays['reference']) if 'predicted' in arrays else None
            if not dm:
                raise ValueError('no delayed metrics or raw images')
            validate_alignment({**frame, 'metrics': {'predicted': pm}})
            item = {'referenceFrame': frame.get('referenceFrame'), 'delayedFrame': frame.get('delayedFrame'),
                    'horizonMs': frame['horizonMs'], 'delayed': dm, 'predicted': pm}
            valid.append(item)
            if pm:
                paired.append(item)
                if pm['mae'] > dm['mae'] or pm['ssim'] < dm['ssim']:
                    worse.append(item)
        except (ValueError, KeyError, OSError) as error:
            errors.append({'referenceFrame': frame.get('referenceFrame'), 'reason': str(error)})

    def means(items, method):
        result = {}
        for key in ('mae', 'psnr', 'ssim'):
            values = [item[method][key] for item in items if item[method].get(key) is not None]
            result[key] = statistics.fmean(values) if values else None
        result['identicalImages'] = sum(item[method].get('identical', False) for item in items)
        return result

    kinds = ('takeover:trigger', 'takeover:notification-receipt', 'takeover:acknowledged',
             'takeover:first-manual-action', 'sensor:collision', 'sensor:lane', 'mode:acknowledged', 'trial:outcome')
    events = sorted((row for row in rows if row.get('kind') in kinds), key=lambda r: r['senderMonotonicNs'])
    timings = []
    for trigger in (row for row in events if row['kind'] == 'takeover:trigger'):
        data = trigger['data']
        start = data.get('triggerNs', trigger['senderMonotonicNs'])
        timing = {'triggerNs': start, 'source': data.get('source'), 'reason': data.get('reason')}
        for kind, key in [('takeover:notification-receipt', 'notificationReceiptMs'),
                          ('takeover:acknowledged', 'manualAcknowledgementMs'),
                          ('takeover:first-manual-action', 'firstManualActionMs')]:
            matching = [r for r in events if r['kind'] == kind and abs(r['data'].get('triggerNs', -1) - start) < 1000
                        and r['senderMonotonicNs'] >= start]
            timing[key] = (matching[0]['senderMonotonicNs'] - start) / 1e6 if matching else None
        timings.append(timing)
    return {'trialId': manifest.get('trialId'), 'label': manifest.get('label'), 'trialOrder': manifest.get('trialOrder'),
        'visualReconstruction': {'alignedSamples': len(valid), 'pairedSamples': len(paired),
            'delayedOnlySamples': len(valid) - len(paired), 'allDelayed': means(valid, 'delayed'),
            'pairedDelayed': means(paired, 'delayed'), 'pairedPredicted': means(paired, 'predicted'),
            'predictionWorseCases': len(worse), 'predictionWorseExamples': worse[:20], 'alignmentErrors': errors,
            'psnrNote': 'Identical images have infinite PSNR, represented as null and counted separately.'},
        'recording': {'dropped': max((r['data'].get('dropped', 0) for r in rows if r['kind'] == 'trial:stop'), default=0),
                      'receivedFrames': sum(r['kind'] == 'frame' for r in rows), 'evaluatedSamples': len(frames)},
        'taskPerformance': {'eventCount': len(events), 'takeovers': timings,
            'collisions': sum(r['kind'] == 'sensor:collision' for r in events),
            'laneEvents': sum(r['kind'] == 'sensor:lane' for r in events), 'events': events,
            'clockNote': 'Durations use only sender monotonic time. Notification receipt includes the network round trip, not exact browser display time.',
            'interpretation': 'Visual reconstruction and task outcomes are separate. Repeat/counterbalance operator trials before claiming driving benefit.'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial_directory', type=Path, nargs='+')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--csv', type=Path, help='One summary row per trial; paired image metrics use identical references')
    args = parser.parse_args()
    results = [evaluate(folder) for folder in args.trial_directory]
    encoded = json.dumps(results[0] if len(results) == 1 else results, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(encoded + '\n')
    if args.csv:
        with args.csv.open('w', newline='') as output:
            fields = ['trialId', 'label', 'trialOrder', 'pairedSamples', 'delayedOnlySamples', 'pairedDelayedMAE',
                      'pairedPredictedMAE', 'predictionWorseCases', 'alignmentErrors', 'collisions', 'dropped']
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for result in results:
                visual = result['visualReconstruction']
                writer.writerow({**{key: result[key] for key in ('trialId', 'label', 'trialOrder')},
                    **{key: visual[key] for key in ('pairedSamples', 'delayedOnlySamples', 'predictionWorseCases')},
                    'pairedDelayedMAE': visual['pairedDelayed']['mae'], 'pairedPredictedMAE': visual['pairedPredicted']['mae'],
                    'alignmentErrors': len(visual['alignmentErrors']), 'collisions': result['taskPerformance']['collisions'],
                    'dropped': result['recording']['dropped']})
    print(encoded)


if __name__ == '__main__':
    main()
