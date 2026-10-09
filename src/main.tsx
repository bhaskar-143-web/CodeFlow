import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ChevronLeft, ChevronRight, CircleHelp, Code2, FastForward, Pause, Play, RotateCcw, Terminal, Waves } from 'lucide-react';
import './style.css';

type Change = { name: string; before: unknown; after: unknown };
// Each language adapter should normalize its runtime events into this shared scene contract.
type TraceEvent = {
  type: string;
  line: number | null;
  function: string;
  changes: Change[];
  focus?: { collection: string; index: number };
  state: Record<string, unknown>;
  output: string;
  narration: string;
};
type TraceResult = { events: TraceEvent[]; output: string; error: string | null };

const sample = `numbers = [10, 20, 30]
total = 0

for num in numbers:
    total = total + num
    print(total)

print("Done")`;

// This is a hand-authored preview timeline, not the result of executing the editor contents.
const demo: TraceResult = {
  error: null,
  output: '10\n30\n60\nDone\n',
  events: [
    { type: 'setup', line: 1, function: '<module>', changes: [{ name: 'numbers', before: undefined, after: [10, 20, 30] }], state: { numbers: [10, 20, 30] }, output: '', narration: 'The list [10, 20, 30] appears.' },
    { type: 'setup', line: 2, function: '<module>', changes: [{ name: 'total', before: undefined, after: 0 }], state: { numbers: [10, 20, 30], total: 0 }, output: '', narration: 'A running total starts at zero.' },
    { type: 'iteration', line: 4, function: '<module>', changes: [{ name: 'num', before: undefined, after: 10 }], state: { numbers: [10, 20, 30], total: 0, num: 10 }, output: '', narration: 'Iteration 1 selects 10.', focus: { collection: 'numbers', index: 0 } },
    { type: 'assignment', line: 5, function: '<module>', changes: [{ name: 'total', before: 0, after: 10 }], state: { numbers: [10, 20, 30], total: 10, num: 10 }, output: '', narration: 'The active value is added to total.' },
    { type: 'output', line: 6, function: '<module>', changes: [], state: { numbers: [10, 20, 30], total: 10, num: 10 }, output: '10\n', narration: '10 is printed to the console.' },
    { type: 'iteration', line: 4, function: '<module>', changes: [{ name: 'num', before: 10, after: 20 }], state: { numbers: [10, 20, 30], total: 10, num: 20 }, output: '10\n', narration: 'Iteration 2 selects 20.', focus: { collection: 'numbers', index: 1 } },
    { type: 'assignment', line: 5, function: '<module>', changes: [{ name: 'total', before: 10, after: 30 }], state: { numbers: [10, 20, 30], total: 30, num: 20 }, output: '10\n', narration: '10 + 20 changes total to 30.' },
    { type: 'output', line: 6, function: '<module>', changes: [], state: { numbers: [10, 20, 30], total: 30, num: 20 }, output: '10\n30\n', narration: '30 is printed to the console.' },
    { type: 'iteration', line: 4, function: '<module>', changes: [{ name: 'num', before: 20, after: 30 }], state: { numbers: [10, 20, 30], total: 30, num: 30 }, output: '10\n30\n', narration: 'Iteration 3 selects 30.', focus: { collection: 'numbers', index: 2 } },
    { type: 'assignment', line: 5, function: '<module>', changes: [{ name: 'total', before: 30, after: 60 }], state: { numbers: [10, 20, 30], total: 60, num: 30 }, output: '10\n30\n', narration: '30 + 30 changes total to 60.' },
    { type: 'output', line: 6, function: '<module>', changes: [], state: { numbers: [10, 20, 30], total: 60, num: 30 }, output: '10\n30\n60\n', narration: '60 is printed to the console.' },
    { type: 'loop_end', line: 4, function: '<module>', changes: [], state: { numbers: [10, 20, 30], total: 60, num: 30 }, output: '10\n30\n60\n', narration: 'The list is finished. The loop ends.' },
    { type: 'output', line: 8, function: '<module>', changes: [], state: { numbers: [10, 20, 30], total: 60, num: 30 }, output: '10\n30\n60\nDone\n', narration: 'Done is printed. The program is complete.' },
  ],
};

function formatTraceValue(value: unknown): string {
  if (value === undefined) return 'not set';
  if (typeof value === 'string') return value;
  if (typeof value === 'object' && value !== null) return JSON.stringify(value);
  return String(value);
}
function App() {
  const [code, setCode] = useState(sample);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const current = result?.events[Math.min(step, Math.max(0, (result?.events.length ?? 1) - 1))];
  const visibleState = current?.state ?? {};
  const variables = Object.entries(visibleState).filter(([key]) => !key.startsWith('__'));
  const collectionVariables = variables.filter(([, value]) => Array.isArray(value));
  const scalarVariables = variables.filter(([, value]) => !Array.isArray(value));
  const changedVariableNames = new Set(current?.changes.map(change => change.name) ?? []);
  const progress = result?.events.length ? ((step + 1) / result.events.length) * 100 : 0;
  const changed = code !== sample;
  const eventLabel = !current ? 'READY TO PLAY' : current.type === 'iteration' ? 'ITEM SELECTED' : current.type === 'assignment' ? 'VARIABLE UPDATED' : current.type === 'output' ? 'OUTPUT SHOWN' : current.type === 'loop_end' ? 'LOOP FINISHED' : 'STARTING STATE';

  useEffect(() => {
    if (!playing || !result) return;
    if (step >= result.events.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setStep(step + 1), 2200 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, result, step, speed]);

  const scene = useMemo(() => {
    if (!current) return { eyebrow: 'TRACE PREVIEW', title: 'Your program, in motion.', detail: 'Play the sample to watch values and variables change.' };
    if (current.type === 'setup') return { eyebrow: 'INITIAL VALUES', title: current.narration, detail: 'The program state is being prepared.' };
    if (current.type === 'iteration') return { eyebrow: 'VALUE SELECTED', title: current.narration, detail: 'Follow the selected value through the program state.' };
    if (current.type === 'assignment') {
      const change = current.changes[0];
      return { eyebrow: 'STATE CHANGED', title: current.narration, detail: change ? change.name + ' changed from ' + formatTraceValue(change.before) + ' to ' + formatTraceValue(change.after) + '.' : 'The program state was updated.' };
    }
    if (current.type === 'output') return { eyebrow: 'OUTPUT', title: current.narration, detail: 'The latest printed result appears in the output panel.' };
    if (current.type === 'loop_end') return { eyebrow: 'STEP COMPLETE', title: current.narration, detail: 'The current sequence has finished.' };
    return { eyebrow: 'TRACE STEP', title: current.narration, detail: current.line ? 'Program is at line ' + current.line + '.' : 'Program state at this step.' };
  }, [current]);

  function playSample() {
    setError('');
    if (changed) {
      setPlaying(false);
      setResult(null);
      setError('This preview uses a fixed sample trace. Restore the sample code to play it; edited code is not executed.');
      return;
    }
    setResult(demo);
    setStep(0);
    setPlaying(true);
  }

  function togglePlayback() {
    if (!result || step >= result.events.length - 1) {
      playSample();
      return;
    }
    setPlaying(!playing);
  }

  function restoreSample() {
    setCode(sample);
    setError('');
    setResult(null);
    setStep(0);
    setPlaying(false);
  }

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><Waves size={19} /></div><span>codeflow</span><span className="tag">LEARN BY WATCHING</span></div>
      <div className="top-center"><span className="demo-dot" /> SAMPLE LESSON <span className="divider">/</span> LOOP + TOTAL</div>
      <button className="run-button" onClick={togglePlayback}>{playing ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" />} {playing ? 'Pause scene' : result && step < result.events.length - 1 ? 'Resume scene' : 'Play scene'}</button>
    </header>

    <section className="lesson-intro" aria-label="Lesson overview">
      <div className="lesson-point lesson-goal"><span>GOAL</span><p>Add 10, 20 and 30 together.</p></div>
      <div className="lesson-point lesson-logic"><span>HOW THE LOGIC WORKS</span><p>Start total at 0. Each loop adds the current number, then prints the total.</p></div>
      <div className="lesson-point lesson-question"><span>QUICK QUESTION</span><p>What will be printed after the second number?</p></div>
    </section>

    <section className="workspace">
      <div className="panel editor-panel">
        <div className="panel-head"><div className="panel-title"><Code2 size={15} /> <span>Code editor</span></div><div className="editor-actions">{changed && <button className="reset-sample" onClick={restoreSample}>Restore sample</button>}<span className="file-pill">main.py</span></div></div>
        <div className="editor-wrap"><div className="line-numbers">{code.split('\n').map((_, i) => <div key={i} className={current?.line === i + 1 ? 'active' : ''}>{String(i + 1).padStart(2, '0')}</div>)}</div><textarea spellCheck={false} value={code} onChange={e => { setCode(e.target.value); setResult(null); setPlaying(false); setError(''); }} aria-label="Python source code" /></div>
        <div className="editor-foot"><span><i className="demo-dot" /> Sample preview Â· code is not executed</span><span>Python</span></div>
      </div>

      <div className="panel scene-panel">
        <div className="panel-head"><div className="panel-title"><Activity size={15} /> <span>Execution scene</span></div><span className="scene-count">{result ? `${step + 1} / ${result.events.length}` : 'SAMPLE'}</span></div>
        <div className="scene-canvas">
          <div className="ambient ambient-one" /><div className="ambient ambient-two" />
          <div className="scene-content">
            <div className="scene-copy" key={step}><div className="eyebrow">{scene.eyebrow}</div>
            <h1>{scene.title}</h1><p>{scene.detail}</p></div>
            <div className="visual-stage">
              <div className="stage-kicker"><span>PROGRAM DATA</span><span>{result ? 'STEP ' + (step + 1) + ' OF ' + result.events.length : 'READY'}</span></div>
              {collectionVariables.length ? <div className="collection-list">{collectionVariables.map(([name, value]) => Array.isArray(value) && <div className="collection-block" key={name}>
                <div className="collection-title"><strong>{name}</strong><span>{value.length} {value.length === 1 ? 'item' : 'items'}</span></div>
                <div className="list-track">{value.map((item, index) => {
                  const focusedIndex = current?.focus?.collection === name
                    ? current.focus.index
                    : current?.type === 'iteration'
                      ? value.findIndex(entry => Object.is(entry, current.changes[0]?.after))
                      : -1;
                  const isCurrent = index === focusedIndex;
                  const isPast = focusedIndex >= 0 && index < focusedIndex;
                  return <div key={index} className={'list-cell' + (isCurrent ? ' is-current' : '') + (isPast ? ' is-done' : '')}><span>{index + 1}</span><b>{formatTraceValue(item)}</b></div>;
                })}</div>
              </div>)}</div> : <div className="empty-collection">No collection values in this step</div>}
              <div className="state-machine">{scalarVariables.length ? scalarVariables.map(([name, value]) => <div key={name} className={changedVariableNames.has(name) ? 'state-card is-changed' : 'state-card'}><span>{name}</span><strong>{formatTraceValue(value)}</strong></div>) : <div className="empty-collection">No scalar values in this step</div>}</div>
              <div className="transition-list">{current?.changes.length ? current.changes.slice(0, 2).map((change, index) => <div className="transition-row" key={change.name + index}><span>{change.name}</span><strong>{change.before === undefined ? 'created' : formatTraceValue(change.before)} <i>&rarr;</i> {formatTraceValue(change.after)}</strong></div>) : <div className="no-transition">No stored value changed in this step.</div>}</div>
            </div>
          </div>
        </div>
        <div className="scene-caption"><span><i className="demo-dot" /> {current ? eventLabel : 'READY TO PLAY'}</span><span>{current?.function ?? 'Sample preview'}</span></div>
      </div>

      <aside className="right-rail">
        <div className="panel state-panel"><div className="panel-head"><div className="panel-title"><span className="braces">{ }</span><span>Program state</span></div><CircleHelp size={15} className="muted-icon" /></div>
          <div className="state-body">{variables.length ? variables.map(([name, value]) => <div className="state-item" key={name}><div><span className="state-name">{name}</span><span className="state-type">{Array.isArray(value) ? 'list' : typeof value}</span></div><strong>{JSON.stringify(value)}</strong></div>) : <div className="empty-state">{result ? 'No tracked variables at this step.' : 'Sample variables appear here during replay.'}</div>}
            {current?.changes?.slice(0, 3).map((change, i) => <div className="why-card" key={`${change.name}-${i}`}><span>WHY IT CHANGED</span><b>{change.name}: {String(change.before ?? 'â€”')} â†’ {String(change.after)}</b><small>Sample event at line {current.line}.</small></div>)}
          </div>
        </div>
        <div className="panel guide-panel"><div className="panel-head"><div className="panel-title"><Waves size={15} /><span>Scene guide</span></div></div><div className="guide-body"><div className="guide-row"><span className="guide-swatch selected-swatch" /><span>Highlighted tile = focused item</span></div><div className="guide-row"><span className="guide-swatch total-swatch" /><span>Accent card = value changed in this step</span></div></div></div>
      </aside>
    </section>

    <section className="bottom-area">
      <div className="timeline-bar"><div className="timeline-title"><span className="timeline-pulse" /> SAMPLE TIMELINE</div><div className="timeline-track"><div className="track-fill" style={{ width: `${progress}%` }} />{result?.events.map((event, i) => <button key={i} aria-label={`Go to sample event ${i + 1}`} title={`${event.type} Â· line ${event.line ?? 'â€”'}`} className={`event-dot ${i === step ? 'selected' : ''}`} style={{ left: `${result.events.length < 2 ? 0 : (i / (result.events.length - 1)) * 100}%` }} onClick={() => { setPlaying(false); setStep(i); }} />)}</div><div className="timeline-end">{result?.events.length ? `${result.events.length} EVENTS` : 'END'}</div></div>
      <div className="transport"><div className="transport-controls"><button title="Restart" onClick={() => setStep(0)} disabled={!result}><RotateCcw size={15} /></button><button title="Previous event" onClick={() => setStep(Math.max(0, step - 1))} disabled={!result || step === 0}><ChevronLeft size={18} /></button><button className="play-control" title="Next event" onClick={() => setStep(Math.min((result?.events.length ?? 1) - 1, step + 1))} disabled={!result}><ChevronRight size={18} /></button><button title="Next event" onClick={() => setStep(Math.min((result?.events.length ?? 1) - 1, step + 1))} disabled={!result}><FastForward size={15} /></button></div><div className="step-label">{current ? `SAMPLE LINE ${String(current.line ?? 'â€”').padStart(2, '0')}  Â·  ${current.type.toUpperCase()}` : 'PLAY THE FIXED SAMPLE TRACE'}</div><label className="speed-control">SPEED <select value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value={0.65}>0.65?</option><option value={1}>1?</option><option value={1.5}>1.5?</option></select></label></div>
      <div className="console-panel"><div className="console-head"><div className="panel-title"><Terminal size={15} /><span>Sample console</span></div><span className="console-status">{error ? 'INFO' : result ? 'DEMO' : 'READY'}</span></div><div className="console-content">{error ? <span className="console-error">{error}</span> : current?.output ? current.output.split('\n').filter((line, i, all) => !(i === all.length - 1 && line === '')).map((line, i) => <div className="console-line" key={i}><span>â€º</span>{line}</div>) : <span className="console-placeholder">Sample output appears as the replay advances.</span>}</div></div>
    </section>
    <footer><span>CODEFLOW <i>Â·</i> SAMPLE REPLAY</span><span>Fixed demo events Â· edited Python is not executed</span></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);




