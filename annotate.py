"""
Web-based annotation tool for ASD speaking label correction.
Usage: uv run python annotate.py --videoFolder demo/20260625_161148
Then open http://localhost:5000

Controls:
  Space        Play / Pause
  R            Replay from beginning
  ← / →        Prev / Next frame  (+ Shift = ×10)
  [ / ]        Prev / Next track
  I            Mark selection start (in point)
  O            Mark selection end (out point)
  S            Mark selection as Speaking
  N            Mark selection as Not Speaking
  Escape       Clear selection
  Ctrl+S       Save
"""
import argparse, os
import pandas as pd
from flask import Flask, jsonify, request, send_file, render_template_string

app = Flask(__name__)
STATE = {}

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ASD Annotator</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #111827; color: #e5e7eb; font-family: monospace;
       display: flex; height: 100vh; overflow: hidden; }

/* Sidebar */
#sidebar { width: 210px; min-width: 210px; background: #1f2937;
           display: flex; flex-direction: column; border-right: 1px solid #374151; }
#sidebar h2 { padding: 8px 10px; font-size: 12px; color: #9ca3af;
              border-bottom: 1px solid #374151; letter-spacing: 1px; }
#track-list { overflow-y: auto; flex: 1; }
.ti { padding: 7px 10px; cursor: pointer; border-bottom: 1px solid #1f2937;
      font-size: 11px; display: flex; flex-direction: column; gap: 3px; }
.ti:hover { background: #374151; }
.ti.active { background: #1d4ed8; }
.ti-bar { height: 3px; background: #374151; border-radius: 2px; overflow: hidden; }
.ti-fill { height: 100%; background: #4ade80; transition: width .2s; }

/* Main */
#main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
#frame-area { flex: 1; display: flex; align-items: center; justify-content: center;
              background: #000; overflow: hidden; }
#fc { display: block; max-width: 100%; max-height: 100%; }

/* Controls bar */
#controls { padding: 6px 10px; background: #1f2937; border-top: 1px solid #374151;
            display: flex; align-items: center; gap: 6px; font-size: 12px; flex-shrink: 0; }
#controls button { background: #374151; color: #e5e7eb; border: none;
                   padding: 3px 9px; cursor: pointer; border-radius: 3px; font-size: 13px; }
#controls button:hover { background: #4b5563; }
#info { margin-left: auto; color: #9ca3af; font-size: 11px; }

/* Timeline */
#tl-area { height: 40px; flex-shrink: 0; background: #0f172a; border-top: 3px solid #374151;
           padding: 4px 10px; overflow: hidden; }
#tl { width: 100%; height: 32px; cursor: crosshair; display: block; }

/* Toolbar */
#toolbar { padding: 5px 10px; background: #1f2937; border-top: 1px solid #374151;
           display: flex; align-items: center; gap: 6px; font-size: 11px; flex-shrink: 0; }
#toolbar button { border: none; padding: 3px 9px; cursor: pointer;
                  border-radius: 3px; font-size: 11px; color: #e5e7eb; }
.btn-spk  { background: #166534; } .btn-spk:hover  { background: #15803d; }
.btn-nspk { background: #7f1d1d; } .btn-nspk:hover { background: #991b1b; }
.btn-clr  { background: #374151; } .btn-clr:hover  { background: #4b5563; }
.btn-save { background: #1e40af; } .btn-save:hover { background: #2563eb; }
#status { margin-left: auto; color: #6b7280; }
kbd { background:#374151; padding:0 4px; border-radius:2px; }
</style>
</head>
<body>

<div id="sidebar">
  <h2>TRACKS ({{ num_tracks }})</h2>
  <div id="track-list"></div>
</div>

<div id="main">
  <div id="frame-area"><canvas id="fc"></canvas></div>

  <audio id="aud" src="/audio" preload="auto"></audio>

  <div id="controls">
    <button onclick="seekTo(0)">⏮</button>
    <button onclick="seekTo(fi-1)">⏪</button>
    <button id="btn-play" onclick="togglePlay()">▶</button>
    <button onclick="seekTo(fi+1)">⏩</button>
    <button onclick="seekTo(ct&&ct.frames.length-1)">⏭</button>
    <button id="btn-mute" onclick="toggleMute()" title="Mute">🔊</button>
    <input id="vol" type="range" min="0" max="1" step="0.05" value="1"
           style="width:70px;cursor:pointer" oninput="aud.volume=this.value">
    <span id="info">No track selected</span>
  </div>

  <div id="tl-area">
    <canvas id="tl"></canvas>
  </div>

  <div id="toolbar">
    <button class="btn-clr"  onclick="selA=fi;drawTimeline();hlTimeline()">In <kbd>I</kbd></button>
    <button class="btn-clr"  onclick="selB=fi;drawTimeline();hlTimeline()">Out <kbd>O</kbd></button>
    <span style="color:#374151">│</span>
    <button class="btn-spk"  onclick="setLbl(1)">Speaking <kbd>S</kbd></button>
    <button class="btn-nspk" onclick="setLbl(0)">Not Speaking <kbd>N</kbd></button>
    <button class="btn-clr"  onclick="clearSel()">Clear <kbd>Esc</kbd></button>
    <span style="color:#374151">│</span>
    <button class="btn-save" onclick="saveAll()">Save <kbd>Ctrl+S</kbd></button>
    <span id="status">Ready</span>
  </div>
</div>

<script>
let summary = [], loaded = {}, ct = null, fi = 0;
let playing = false, timer = null;
let selA = -1, selB = -1, dragging = false;
let dirty = new Set();

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  summary = await (await fetch('/api/summary')).json();
  buildSidebar();
  if (summary.length) loadTrack(summary[0].id);
}

function buildSidebar() {
  document.getElementById('track-list').innerHTML = summary.map(t =>
    `<div class="ti" id="ti${t.id}" onclick="loadTrack(${t.id})">
       <div id="tt${t.id}">#${String(t.id).padStart(3,'0')} &nbsp; ${t.length}f &nbsp; ${t.spk}%spk</div>
       <div class="ti-bar"><div class="ti-fill" id="tf${t.id}" style="width:${t.spk}%"></div></div>
     </div>`).join('');
}

// ── Track loading ─────────────────────────────────────────────────────────────
async function loadTrack(id) {
  if (ct && ct.id !== id && dirty.has(ct.id)) {
    const ok = confirm(`Track #${String(ct.id).padStart(3,'0')} has unsaved changes.\nLeave without saving?`);
    if (!ok) return;
  }
  stopPlay(); selA = selB = -1;
  if (!loaded[id]) loaded[id] = await (await fetch(`/api/track/${id}`)).json();
  ct = loaded[id]; ct.id = id; fi = 0;
  document.querySelectorAll('.ti').forEach(e => e.classList.remove('active'));
  const el = document.getElementById(`ti${id}`);
  if (el) { el.classList.add('active'); el.scrollIntoView({block:'nearest'}); }
  await drawFrame(); drawTimeline();
}

// ── Frame rendering ───────────────────────────────────────────────────────────
async function drawFrame() {
  if (!ct) return;
  fi = Math.max(0, Math.min(fi, ct.frames.length - 1));
  const [x1,y1,x2,y2] = ct.bboxes[fi];
  const score = ct.scores[fi], lbl = ct.labels[fi];
  const fnum = String(ct.frames[fi] + 1).padStart(6,'0');

  document.getElementById('info').textContent =
    `#${ct.id} | ${fi+1}/${ct.frames.length} | score:${score.toFixed(2)} | ${lbl?'🟢 speaking':'🔴 not'}`;

  await new Promise(res => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.getElementById('fc');
      const area = document.getElementById('frame-area');
      const sc = Math.min(area.clientWidth/img.width, area.clientHeight/img.height);
      canvas.width  = img.width  * sc;
      canvas.height = img.height * sc;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = lbl ? '#4ade80' : '#f87171';
      ctx.lineWidth = 3;
      ctx.strokeRect(x1*sc, y1*sc, (x2-x1)*sc, (y2-y1)*sc);
      ctx.fillStyle = lbl ? '#4ade80' : '#f87171';
      ctx.font = `bold ${Math.max(14, 18*sc)}px monospace`;
      ctx.fillText(score.toFixed(1), x1*sc+3, y1*sc - 4);
      res();
    };
    img.src = `/frame/${fnum}.jpg`;
  });
  hlTimeline();
}

// ── Playback ──────────────────────────────────────────────────────────────────
const aud = document.getElementById('aud');
function toggleMute() {
  aud.muted = !aud.muted;
  document.getElementById('btn-mute').textContent = aud.muted ? '🔇' : '🔊';
}

function togglePlay() { playing ? stopPlay() : startPlay(); }
function startPlay() {
  if (!ct) return; playing = true;
  document.getElementById('btn-play').textContent = '⏸';
  aud.currentTime = ct.frames[fi] / 25;
  aud.play();
  timer = setInterval(async () => {
    if (fi >= ct.frames.length - 1) { stopPlay(); return; }
    fi++; await drawFrame();
  }, 40);
}
function stopPlay() {
  playing = false; clearInterval(timer); timer = null;
  document.getElementById('btn-play').textContent = '▶';
  aud.pause();
}
async function seekTo(idx) {
  stopPlay();
  fi = ct ? Math.max(0, Math.min(idx, ct.frames.length - 1)) : Math.max(0, idx);
  if (ct) aud.currentTime = ct.frames[fi] / 25;
  await drawFrame();
}

// ── Timeline ──────────────────────────────────────────────────────────────────
function drawTimeline() {
  if (!ct) return;
  const cv = document.getElementById('tl');
  const ctx = cv.getContext('2d');
  const W = document.getElementById('tl-area').clientWidth - 20;
  const H = cv.offsetHeight || 32;
  cv.width = W; cv.height = H;
  const n = ct.frames.length, fw = W / n;

  // Background
  ctx.fillStyle = '#0f172a'; ctx.fillRect(0, 0, W, H);

  // Green/red bars per frame
  for (let i = 0; i < n; i++) {
    ctx.fillStyle = ct.labels[i] ? '#166534' : '#7f1d1d';
    ctx.fillRect(i * fw, 0, Math.max(fw, 1), H);
  }

  // Selection overlay
  if (selA >= 0 && selB >= 0) {
    const s = Math.min(selA, selB), e = Math.max(selA, selB);
    ctx.fillStyle = 'rgba(59,130,246,0.6)';
    ctx.fillRect(s * fw, 0, (e - s + 1) * fw, H);
  }
}
function hlTimeline() {
  drawTimeline();
  if (!ct) return;
  const cv = document.getElementById('tl');
  const ctx = cv.getContext('2d'), W = cv.width, H = cv.height;
  const fw = W / ct.frames.length;
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.fillRect(fi * fw, 0, Math.max(fw, 2), H);
}

// Timeline mouse
const tlc = document.getElementById('tl');
function xToFrame(e) {
  if (!ct) return 0;
  const r = tlc.getBoundingClientRect();
  return Math.max(0, Math.min(ct.frames.length-1,
    Math.floor((e.clientX-r.left)/r.width * ct.frames.length)));
}
tlc.addEventListener('mousedown', e => {
  dragging = true; selA = selB = xToFrame(e); drawTimeline(); hlTimeline();
});
tlc.addEventListener('mousemove', e => {
  if (!dragging) return; selB = xToFrame(e); drawTimeline(); hlTimeline();
});
tlc.addEventListener('mouseup', async e => {
  dragging = false; selB = xToFrame(e);
  fi = Math.min(selA, selB);
  if (ct) aud.currentTime = ct.frames[fi] / 25;
  await drawFrame(); drawTimeline(); hlTimeline();
});

// ── Label editing ─────────────────────────────────────────────────────────────
async function setLbl(val) {
  if (!ct) return;
  const s = selA>=0&&selB>=0 ? Math.min(selA,selB) : fi;
  const e = selA>=0&&selB>=0 ? Math.max(selA,selB) : fi;
  for (let i=s; i<=e; i++) ct.labels[i] = val;
  dirty.add(ct.id);
  // Update sidebar bar
  const spk = Math.round(100 * ct.labels.filter(x=>x).length / ct.labels.length);
  const bar = document.getElementById(`tf${ct.id}`);
  if (bar) bar.style.width = spk + '%';
  const txt = document.getElementById(`tt${ct.id}`);
  if (txt) txt.textContent = `#${String(ct.id).padStart(3,'0')}   ${ct.frames.length}f   ${spk}%spk`;
  const sm = summary.find(x=>x.id===ct.id); if(sm) sm.spk=spk;
  status(`${e-s+1} frame(s) → ${val?'speaking':'not speaking'}`);
  selA = selB = -1;
  await drawFrame(); drawTimeline(); hlTimeline();
}
function clearSel() { selA = selB = -1; drawTimeline(); hlTimeline(); }

// ── Save ──────────────────────────────────────────────────────────────────────
async function saveAll() {
  if (!dirty.size) { status('Nothing to save'); return; }
  status('Saving...');
  const payload = {};
  for (const id of dirty) if (loaded[id]) payload[id] = loaded[id].labels;
  const r = await fetch('/api/save', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });
  const res = await r.json();
  if (res.ok) { dirty.clear(); status('Saved ✓'); }
  else status('Save failed!');
}

let _stTimer;
function status(msg) {
  document.getElementById('status').textContent = msg;
  clearTimeout(_stTimer);
  _stTimer = setTimeout(()=>document.getElementById('status').textContent='', 3000);
}

// ── Track navigation ──────────────────────────────────────────────────────────
async function navigateTrack(delta) {
  if (!ct) return;
  const idx = summary.findIndex(t => t.id === ct.id);
  const next = summary[idx + delta];
  if (!next) return;
  if (dirty.has(ct.id)) {
    const ok = confirm(`Track #${String(ct.id).padStart(3,'0')} has unsaved changes.\nLeave without saving?`);
    if (!ok) return;
  }
  await loadTrack(next.id);
}

// ── Keyboard ──────────────────────────────────────────────────────────────────
document.addEventListener('keydown', async e => {
  if (e.target.tagName==='INPUT') return;
  const sh = e.shiftKey ? 10 : 1;
  if (e.code==='Space')     { e.preventDefault(); togglePlay(); }
  else if (e.code==='KeyR') { e.preventDefault(); await seekTo(0); startPlay(); }
  else if (e.code==='ArrowRight') { e.preventDefault(); await seekTo(fi+sh); }
  else if (e.code==='ArrowLeft')  { e.preventDefault(); await seekTo(fi-sh); }
  else if (e.code==='BracketLeft')  { e.preventDefault(); await navigateTrack(-1); }
  else if (e.code==='BracketRight') { e.preventDefault(); await navigateTrack(+1); }
  else if (e.code==='KeyI')       { selA = fi; drawTimeline(); hlTimeline(); }
  else if (e.code==='KeyO')       { selB = fi; drawTimeline(); hlTimeline(); }
  else if (e.code==='KeyS' && !e.ctrlKey && !e.metaKey) await setLbl(1);
  else if (e.code==='KeyN')       await setLbl(0);
  else if (e.code==='Escape')     clearSel();
  else if ((e.ctrlKey||e.metaKey) && e.code==='KeyS') { e.preventDefault(); saveAll(); }
});

new ResizeObserver(() => {
  if (ct) hlTimeline();
}).observe(document.getElementById('tl-area'));

init();
</script>
</body>
</html>
"""

# ── Flask routes ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(HTML, num_tracks=len(STATE['tracks']))

@app.route('/frame/<path:filename>')
def serve_frame(filename):
    return send_file(os.path.join(STATE['frames_path'], filename), mimetype='image/jpeg')

@app.route('/audio')
def serve_audio():
    path = os.path.join(STATE['video_folder'], 'pyavi', 'audio.wav')
    return send_file(path, mimetype='audio/wav', conditional=True)

@app.route('/api/summary')
def api_summary():
    out = []
    for tid, t in STATE['tracks'].items():
        n = len(t['labels'])
        out.append({'id': tid, 'length': n,
                    'spk': round(100 * sum(t['labels']) / n) if n else 0})
    return jsonify(sorted(out, key=lambda x: x['id']))

@app.route('/api/track/<int:tid>')
def api_track(tid):
    return jsonify(STATE['tracks'].get(tid, {}))

@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    df = STATE['df']
    for tid_str, labels in data.items():
        tid = int(tid_str)
        idx = df[df['track_id'] == tid].index
        df.loc[idx, 'speaking'] = labels
        STATE['tracks'][tid]['labels'] = labels
    df.to_csv(STATE['csv_path'], index=False)
    return jsonify({'ok': True})

# ── Startup ───────────────────────────────────────────────────────────────────
def load_data(video_folder):
    csv_path    = os.path.join(video_folder, 'annotations.csv')
    frames_path = os.path.join(video_folder, 'pyframes')
    df = pd.read_csv(csv_path)
    tracks = {}
    for tid, g in df.groupby('track_id'):
        tracks[int(tid)] = {
            'frames': g['frame'].tolist(),
            'bboxes': g[['x1','y1','x2','y2']].values.tolist(),
            'scores': g['model_score'].tolist(),
            'labels': g['speaking'].tolist(),
        }
    STATE.update(df=df, tracks=tracks, csv_path=csv_path,
                 frames_path=frames_path, video_folder=video_folder)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--videoFolder', required=True)
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    load_data(args.videoFolder)
    print(f"Loaded {len(STATE['tracks'])} tracks · {len(STATE['df'])} frames")
    print(f"Open http://localhost:{args.port}")
    app.run(debug=False, port=args.port)
