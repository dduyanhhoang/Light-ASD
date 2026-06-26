"""
Export pipeline tracks as a pre-annotated CSV for manual speaking label correction.

Output CSV columns:
  track_id   - face track index (unique continuous face clip)
  frame      - video frame number (0-indexed)
  x1,y1,x2,y2 - bounding box in original video coordinates
  model_score  - raw ASD score (positive = speaking)
  speaking     - suggested label from model (0/1), edit this column to correct

Usage:
  uv run python export_annotations.py --videoFolder demo/20260625_161148
  uv run python export_annotations.py --videoFolder demo/20260625_163703
"""

import argparse, pickle, numpy, csv, os

parser = argparse.ArgumentParser()
parser.add_argument('--videoFolder', type=str, required=True)
parser.add_argument('--output',      type=str, default=None, help='Output CSV path (default: <videoFolder>/annotations.csv)')
args = parser.parse_args()

pywork = os.path.join(args.videoFolder, 'pywork')
tracks = pickle.load(open(os.path.join(pywork, 'tracks.pckl'), 'rb'))
scores = pickle.load(open(os.path.join(pywork, 'scores.pckl'), 'rb'))

out_path = args.output or os.path.join(args.videoFolder, 'annotations.csv')

with open(out_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['track_id', 'frame', 'x1', 'y1', 'x2', 'y2', 'model_score', 'speaking'])

    for tid, (track, score) in enumerate(zip(tracks, scores)):
        frames = track['track']['frame'].tolist()
        bboxes = track['track']['bbox']
        sx     = track['proc_track']['x']
        sy     = track['proc_track']['y']
        ss     = track['proc_track']['s']

        for fidx, frame in enumerate(frames):
            # smoothed score (same averaging as visualization)
            window = score[max(fidx-2, 0): min(fidx+3, len(score))]
            s = float(numpy.mean(window)) if len(window) > 0 else 0.0

            x1 = int(sx[fidx] - ss[fidx])
            y1 = int(sy[fidx] - ss[fidx])
            x2 = int(sx[fidx] + ss[fidx])
            y2 = int(sy[fidx] + ss[fidx])

            writer.writerow([tid, frame, x1, y1, x2, y2, round(s, 2), int(s > 0)])

print(f"Exported {len(tracks)} tracks → {out_path}")
print(f"Open the CSV, review 'speaking' column (0/1), correct where wrong, save.")
