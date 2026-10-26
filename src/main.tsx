import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ChevronLeft, ChevronRight, CircleHelp, Code2, FastForward, LogOut, Pause, Play, RotateCcw, Terminal, Waves } from 'lucide-react';
import './style.css';
import { concepts, lessons, type Lesson } from './lessons';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');

type Change = { name: string; before?: unknown; after: unknown };
// Each language adapter should normalize its runtime events into this shared scene contract.
type TraceEvent = {
  type: string;
  line: number | null;
  function: string;
  callStack?: string[];
  changes: Change[];
  focus?: { collection: string; index: number };
  state: Record<string, unknown>;
  valueTypes?: Record<string, string>;
  output: string;
  narration: string;
};
type TraceResult = { events: TraceEvent[]; output: string; error: string | null };
type SavedWorkspace = { selectedLessonId: string; code: string; programInput: string };
const WORKSPACE_STORAGE_KEY = 'codeflow.workspace.v1';

function readSavedWorkspace(): SavedWorkspace {
  const firstLesson = lessons[0];
  const fallback = { selectedLessonId: firstLesson.id, code: firstLesson.code, programInput: firstLesson.input ?? '' };
  try {
    const saved = JSON.parse(window.localStorage.getItem(WORKSPACE_STORAGE_KEY) ?? 'null') as Partial<SavedWorkspace> | null;
    if (!saved) return fallback;
    const lesson = lessons.find(item => item.id === saved.selectedLessonId) ?? firstLesson;
    return {
      selectedLessonId: lesson.id,
      code: typeof saved.code === 'string' && saved.code.length <= 20_000 ? saved.code : lesson.code,
      programInput: typeof saved.programInput === 'string' && saved.programInput.length <= 5_000 ? saved.programInput : lesson.input ?? '',
    };
  } catch {
    return fallback;
  }
}

function formatTraceValue(value: unknown): string {
  if (value === undefined) return 'not set';
  if (typeof value === 'string') return value;
  if (typeof value === 'object' && value !== null) return JSON.stringify(value);
  return String(value);
}
function isDictionary(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
type AuthUser = { id: string; name: string; email: string; picture?: string | null };
type GoogleCredential = { credential: string };
type GoogleIdentityApi = {
  initialize: (options: { client_id: string; auto_select: false; callback: (response: GoogleCredential) => void }) => void;
  renderButton: (target: HTMLElement, options: { theme: 'outline'; size: 'large'; shape: 'pill'; text: 'continue_with'; width: number; logo_alignment: 'left' }) => void;
  disableAutoSelect: () => void;
};
declare global {
  interface Window { google?: { accounts?: { id?: GoogleIdentityApi } } }
  interface ImportMetaEnv { readonly VITE_GOOGLE_CLIENT_ID?: string }
}
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim() ?? '';
let googleInitializedFor = '';

function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState('');
  const googleButtonRef = useRef<HTMLDivElement>(null);
  const credentialHandler = useRef<(credential: string) => void>(() => undefined);

  useEffect(() => {
    let active = true;
    fetch(`${API_BASE_URL}/api/auth/session`, { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error('Could not check your saved login. Make sure the CodeFlow API is running.');
        return response.json() as Promise<{ user: AuthUser | null }>;
      })
      .then(session => { if (active) setUser(session.user); })
      .catch(cause => { if (active) setAuthError(cause instanceof Error ? cause.message : 'Could not connect to the login service.'); })
      .finally(() => { if (active) setAuthLoading(false); });
    return () => { active = false; };
  }, []);

  async function signInWithCredential(credential: string) {
    setAuthError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/google`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential }),
      });
      const result = await response.json() as { user?: AuthUser; detail?: string };
      if (!response.ok || !result.user) throw new Error(result.detail ?? 'Google sign-in could not be completed.');
      setUser(result.user);
    } catch (cause) {
      setAuthError(cause instanceof Error ? cause.message : 'Google sign-in could not be completed.');
    }
  }
  credentialHandler.current = credential => { void signInWithCredential(credential); };

  useEffect(() => {
    if (authLoading || user || !GOOGLE_CLIENT_ID || !googleButtonRef.current) return;
    const script = document.getElementById('google-identity') as HTMLScriptElement | null;
    let attempts = 0;
    const renderButton = () => {
      const google = window.google?.accounts?.id;
      const target = googleButtonRef.current;
      if (!google || !target) return;
      if (googleInitializedFor !== GOOGLE_CLIENT_ID) {
        google.initialize({ client_id: GOOGLE_CLIENT_ID, auto_select: false, callback: response => credentialHandler.current(response.credential) });
        googleInitializedFor = GOOGLE_CLIENT_ID;
      }
      if (target.dataset.ready === 'true') return;
      google.renderButton(target, { theme: 'outline', size: 'large', shape: 'pill', text: 'continue_with', width: Math.min(320, target.clientWidth || 320), logo_alignment: 'left' });
      target.dataset.ready = 'true';
    };
    const timer = window.setInterval(() => {
      renderButton();
      attempts += 1;
      if (attempts >= 80 || googleButtonRef.current?.dataset.ready === 'true') window.clearInterval(timer);
    }, 150);
    script?.addEventListener('load', renderButton);
    renderButton();
    return () => {
      window.clearInterval(timer);
      script?.removeEventListener('load', renderButton);
    };
  }, [authLoading, user]);

  async function logout() {
    setAuthError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' });
      if (!response.ok) throw new Error('Could not sign out. Please try again.');
      window.google?.accounts?.id?.disableAutoSelect();
      window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
      setUser(null);
    } catch (cause) {
      setAuthError(cause instanceof Error ? cause.message : 'Could not sign out. Please try again.');
    }
  }

  if (authLoading) return <main className="auth-shell"><section className="auth-card"><div className="auth-brand"><span className="brand-mark"><Waves size={19} /></span><b>codeflow</b></div><p>Checking your sign-in…</p></section></main>;
  if (user) return <CodeFlowWorkspace key={user.id} user={user} onLogout={logout} />;
  return <main className="auth-shell"><section className="auth-card">
    <div className="auth-brand"><span className="brand-mark"><Waves size={19} /></span><b>codeflow</b></div>
    <span className="auth-eyebrow">PYTHON, MADE VISUAL</span>
    <h1>Welcome back</h1>
    <p className="auth-description">Sign in with Google to open your visual coding workspace. You’ll stay signed in on this device until you log out.</p>
    {authError && <div className="auth-error" role="alert">{authError}</div>}
    {GOOGLE_CLIENT_ID ? <div className="google-button-slot" ref={googleButtonRef} /> : <div className="auth-setup"><strong>Google login needs setup</strong><span>Add <code>VITE_GOOGLE_CLIENT_ID</code> for the web app and <code>GOOGLE_CLIENT_ID</code> for the API, then restart both.</span></div>}
    <small className="auth-footnote">Your session stays saved for one year, or until you log out.</small>
  </section></main>;
}
function CodeFlowWorkspace({ user, onLogout }: { user: AuthUser; onLogout: () => Promise<void> }) {
  const [savedWorkspace] = useState(readSavedWorkspace);
  const [selectedLessonId, setSelectedLessonId] = useState(savedWorkspace.selectedLessonId);
  const [code, setCode] = useState(savedWorkspace.code);
  const [programInput, setProgramInput] = useState(savedWorkspace.programInput);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [speed, setSpeed] = useState(1);
  const current = result?.events[Math.min(step, Math.max(0, (result?.events.length ?? 1) - 1))];
  const activeSourceLine = current?.line ? code.split('\n')[current.line - 1] : undefined;
  const currentLesson = lessons.find(lesson => lesson.id === selectedLessonId) ?? lessons[0];
  const conceptLessons = lessons.filter(lesson => lesson.concept === currentLesson.concept);
  const conceptSubtopics = [...new Set(conceptLessons.map(lesson => lesson.subtopic))];
  const subtopicLessons = conceptLessons.filter(lesson => lesson.subtopic === currentLesson.subtopic);
  const exampleNumber = subtopicLessons.findIndex(lesson => lesson.id === currentLesson.id) + 1;
  const visibleState = current?.state ?? {};
  const variables = Object.entries(visibleState).filter(([key]) => !key.startsWith('__'));
  const collectionVariables = variables.filter(([, value]) => Array.isArray(value) || isDictionary(value));
  const scalarVariables = variables.filter(([, value]) => !Array.isArray(value) && !isDictionary(value));
  const changedVariableNames = new Set(current?.changes.map(change => change.name) ?? []);
  const progress = result?.events.length ? ((step + 1) / result.events.length) * 100 : 0;
  const changed = code !== currentLesson.code;
  const eventLabel = !current ? 'READY TO PLAY' : current.type === 'branch' ? 'CONDITION CHECKED' : current.type === 'iteration' ? 'ITEM SELECTED' : current.type === 'loop_control' ? 'LOOP CONTROL' : current.type === 'input' ? 'INPUT RECEIVED' : current.type === 'exception' ? 'ERROR CAUGHT' : current.type === 'class_def' ? 'CLASS DEFINED' : current.type === 'assignment' ? 'VARIABLE UPDATED' : current.type === 'output' ? 'OUTPUT SHOWN' : current.type === 'loop_end' ? 'LOOP FINISHED' : current.type === 'function_def' ? 'FUNCTION DEFINED' : current.type === 'call' ? 'FUNCTION CALLED' : current.type === 'return' ? 'VALUE RETURNED' : current.type === 'module' ? 'MODULE USED' : current.type === 'file' ? 'FILE STEP' : current.type === 'decorator' ? 'DECORATOR APPLIED' : current.type === 'generator_yield' ? 'VALUE YIELDED' : current.type === 'await' ? 'ASYNC STEP' : 'STARTING STATE';

  useEffect(() => {
    if (!playing || !result) return;
    if (step >= result.events.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setStep(step + 1), 2200 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, result, step, speed]);

  useEffect(() => {
    try {
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ selectedLessonId, code, programInput }));
    } catch {
      // Keep the editor usable if browser storage is unavailable or full.
    }
  }, [selectedLessonId, code, programInput]);

  const scene = useMemo(() => {
    if (!current) return { eyebrow: 'TRACE PREVIEW', title: 'Your program, in motion.', detail: 'Run code to watch values and variables change.' };
    if (current.type === 'setup') return { eyebrow: 'INITIAL VALUES', title: current.narration, detail: 'The program state is being prepared.' };
    if (current.type === 'branch') return { eyebrow: 'CONDITION CHECKED', title: current.narration, detail: 'The highlighted source line chooses which block runs next.' }
    if (current.type === 'iteration') return { eyebrow: 'VALUE SELECTED', title: current.narration, detail: 'Follow the selected value through the program state.' };
    if (current.type === 'class_def') return { eyebrow: 'CLASS DEFINED', title: current.narration, detail: 'The class is a blueprint. Creating an instance runs its initializer.' };
    if (current.type === 'module') return { eyebrow: 'MODULE TOOL', title: current.narration, detail: 'This lesson uses a small allowlist of safe math and statistics helpers.' };
    if (current.type === 'file') return { eyebrow: 'IN-MEMORY FILE', title: current.narration, detail: 'The lesson file exists only in the visualizer memory; it does not read or write your device.' };
    if (current.type === 'decorator') return { eyebrow: 'DECORATOR APPLIED', title: current.narration, detail: 'The decorator is evaluated when Python defines the function.' };
    if (current.type === 'generator_yield') return { eyebrow: 'GENERATOR VALUE', title: current.narration, detail: 'Follow this yielded value into the loop that consumes it.' };
    if (current.type === 'await') return { eyebrow: 'ASYNC STEP', title: current.narration, detail: 'This teaching trace models awaited steps in order, without real delays or parallel tasks.' };
    if (current.type === 'exception') return { eyebrow: 'ERROR CAUGHT', title: current.narration, detail: 'The matching except block takes control, so the program can continue.' };
    if (current.type === 'input') return { eyebrow: 'INPUT RECEIVED', title: current.narration, detail: 'The value from Program input is passed into input() as text.' };
    if (current.type === 'loop_control') return { eyebrow: 'LOOP CONTROL', title: current.narration, detail: 'The loop changes direction at this line.' };
    if (current.type === 'function_def') return { eyebrow: 'FUNCTION READY', title: current.narration, detail: 'The function is defined. Its body runs when the program calls it.' };
    if (current.type === 'call') return { eyebrow: 'FUNCTION CALLED', title: current.narration, detail: 'Step into the function and follow its inputs and work.' };
    if (current.type === 'return') return { eyebrow: 'FUNCTION RESULT', title: current.narration, detail: 'This result goes back to the line that called the function.' };
    if (current.type === 'assignment') {
      const change = current.changes[0];
      return { eyebrow: 'STATE CHANGED', title: current.narration, detail: change ? change.name + ' changed from ' + formatTraceValue(change.before) + ' to ' + formatTraceValue(change.after) + '.' : 'The program state was updated.' };
    }
    if (current.type === 'output') return { eyebrow: 'OUTPUT', title: current.narration, detail: 'The latest printed result appears in the output panel.' };
    if (current.type === 'loop_end') return { eyebrow: 'STEP COMPLETE', title: current.narration, detail: 'The current sequence has finished.' };
    return { eyebrow: 'TRACE STEP', title: current.narration, detail: current.line ? 'Program is at line ' + current.line + '.' : 'Program state at this step.' };
  }, [current]);

  function chooseLesson(lesson: Lesson) {
    setSelectedLessonId(lesson.id);
    setCode(lesson.code);
    setProgramInput(lesson.input ?? '');
    setResult(null);
    setStep(0);
    setError('');
    setPlaying(false);
  }
  async function runTrace() {
    if (!code.trim()) {
      setResult(null);
      setError('Enter some Python code first.');
      return;
    }
    setLoading(true);
    setPlaying(false);
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/trace`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, inputs: programInput ? programInput.split(/\r?\n/) : [] }),
      });
      const trace = await response.json() as TraceResult;
      if (!response.ok) {
        throw new Error((trace as unknown as { detail?: string }).detail ?? 'The trace service could not process this code.');
      }
      setResult(trace);
      setStep(0);
      if (trace.error) setError(trace.error);
      setPlaying(trace.events.length > 0);
    } catch (cause) {
      setResult(null);
      setError(cause instanceof Error && cause.message.includes('Failed to fetch')
        ? 'Cannot reach the Python tracer. Start the backend in a second terminal, then try again.'
        : cause instanceof Error ? cause.message : 'Could not create a trace.');
    } finally {
      setLoading(false);
    }
  }
  function togglePlayback() {
    if (loading) return;
    if (!result || !result.events.length || step >= result.events.length - 1) {
      void runTrace();
      return;
    }
    setPlaying(!playing);
  }
  function restoreLesson() {
    setCode(currentLesson.code);
    setProgramInput(currentLesson.input ?? '');
    setError('');
    setResult(null);
    setStep(0);
    setPlaying(false);
  }

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><Waves size={19} /></div><span>codeflow</span><span className="tag">LEARN BY WATCHING</span></div>
      <label className="top-center language-picker"><span className="demo-dot" /><span className="language-label">LANGUAGE</span><select aria-label="Programming language" defaultValue="python"><option value="python">Python</option><option value="javascript" disabled>JavaScript — coming soon</option><option value="java" disabled>Java — coming soon</option><option value="cpp" disabled>C++ — coming soon</option></select></label>
      <div className="topbar-actions"><div className="signed-in-user"><strong>{user.name}</strong><span>{user.email}</span></div><button className="logout-button" onClick={() => { void onLogout(); }}><LogOut size={14} /><span>Log out</span></button><button className="run-button" onClick={togglePlayback} disabled={loading}>{loading ? <Activity size={15} /> : playing ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" />} {loading ? 'Running…' : playing ? 'Pause' : result && step < result.events.length - 1 ? 'Continue' : 'Run code'}</button></div>
    </header>

    <section className="lesson-picker" aria-label="Choose a concept, type, and example">
      <label><span>CONCEPT</span><select value={currentLesson.concept} disabled={loading} onChange={event => {
        const firstLesson = lessons.find(lesson => lesson.concept === event.target.value);
        if (firstLesson) chooseLesson(firstLesson);
      }}>{concepts.map(concept => <option key={concept} value={concept}>{concept}</option>)}</select></label>
      <label><span>TYPE</span><select value={currentLesson.subtopic} disabled={loading} onChange={event => {
        const firstLesson = conceptLessons.find(lesson => lesson.subtopic === event.target.value);
        if (firstLesson) chooseLesson(firstLesson);
      }}>{conceptSubtopics.map(subtopic => <option key={subtopic} value={subtopic}>{subtopic}</option>)}</select></label>
      <label><span>EXAMPLE</span><select value={currentLesson.id} disabled={loading} onChange={event => chooseLesson(subtopicLessons.find(lesson => lesson.id === event.target.value) ?? subtopicLessons[0])}>{subtopicLessons.map(lesson => <option key={lesson.id} value={lesson.id}>{lesson.title}</option>)}</select></label>
      <div className="lesson-picker-hint"><strong>{currentLesson.title}</strong><span>Example {exampleNumber} of {subtopicLessons.length}</span></div>
    </section>
    <section className="lesson-intro" aria-label="Lesson overview">
      <div className="lesson-point lesson-goal"><span>GOAL</span><p>{currentLesson.goal}</p></div>
      <div className="lesson-point lesson-logic"><span>THE IDEA</span><p>{currentLesson.logic}</p></div>
      <div className="lesson-point lesson-question"><span>THINK ABOUT IT</span><p>{currentLesson.question}</p></div>
    </section>

    <section className="workspace">
      <div className="panel editor-panel">
        <div className="panel-head"><div className="panel-title"><Code2 size={15} /> <span>Your code</span></div><div className="editor-actions">{changed && <button className="reset-sample" onClick={restoreLesson}>Reset example</button>}<span className="file-pill">main.py</span></div></div>
        <div className="editor-wrap"><div className="line-numbers">{code.split('\n').map((_, i) => <div key={i} className={current?.line === i + 1 ? 'active' : ''}>{String(i + 1).padStart(2, '0')}</div>)}</div><textarea spellCheck={false} value={code} onChange={e => { setCode(e.target.value); setResult(null); setPlaying(false); setError(''); }} aria-label="Python source code" /></div>
        <label className="program-input"><span>PROGRAM INPUT</span><textarea value={programInput} onChange={e => { setProgramInput(e.target.value); setResult(null); setPlaying(false); }} aria-label="Program input values, one per line" placeholder="Enter one value for each input() call" /><small>One value per line. input() reads them in order.</small></label>
        <div className="editor-foot"><span><i className="demo-dot" /> Python · safe mode</span><span>Python</span></div>
      </div>

      <div className="panel scene-panel">
        <div className="panel-head"><div className="panel-title"><Activity size={15} /> <span>Visual walkthrough</span></div><span className="scene-count">{result ? `${step + 1} / ${result.events.length}` : 'READY'}</span></div>
        <div className="scene-canvas">
          <div className="ambient ambient-one" /><div className="ambient ambient-two" />
          <div className="scene-content">
            <div className="scene-copy" key={step}><div className="eyebrow">{scene.eyebrow}</div>
            <h1>{scene.title}</h1><p>{scene.detail}</p></div>
            <div className="scene-source-line" aria-live="polite" aria-label={current?.line ? `Current code line ${current.line}${current.function !== '<module>' ? ` in ${current.function}` : ''}` : 'Current code line'}>
              {current?.line && activeSourceLine !== undefined
                ? <><span>{current.function !== '<module>' ? `${current.function} · ` : ''}LINE {String(current.line).padStart(2, '0')}</span><code>{activeSourceLine || '(blank line)'}</code></>
                : <span className="scene-source-placeholder">Run code to see the current line here</span>}
            </div>
            <div className="visual-stage">
              <div className="stage-kicker"><span>PROGRAM DATA</span><span>{result ? 'STEP ' + (step + 1) + ' OF ' + result.events.length : 'READY'}</span></div>
              {current?.callStack?.length ? <div className="call-stack" aria-label="Function call stack"><div className="call-stack-title">CALL STACK <span>{current.callStack.length} active {current.callStack.length === 1 ? 'call' : 'calls'}</span></div><div className="call-stack-frames">{current.callStack.map((name, index) => <div key={index} className={index === current.callStack!.length - 1 ? 'call-frame is-active' : 'call-frame'}><span>{String(index + 1).padStart(2, '0')}</span><strong>{name}()</strong></div>)}</div></div> : null}
              {collectionVariables.length ? <div className="collection-list">{collectionVariables.map(([name, value]) => {
                const entries: [string, unknown][] = Array.isArray(value)
                  ? value.map((item, index) => [String(index + 1), item])
                  : Object.entries(value as Record<string, unknown>);
                return <div className="collection-block" key={name}>
                  <div className="collection-title"><strong>{name}</strong><span>{entries.length} {current?.valueTypes?.[name] === 'set' ? 'members' : current?.valueTypes?.[name] === 'object' ? 'attributes' : isDictionary(value) ? 'keys' : entries.length === 1 ? 'item' : 'items'}</span></div>
                  <div className="list-track">{entries.map(([key, item], index) => {
                    const focusedIndex = current?.focus?.collection === name
                      ? current.focus.index
                      : current?.type === 'iteration'
                        ? entries.findIndex(([, entry]) => Object.is(entry, current.changes[0]?.after))
                        : -1;
                    const isCurrent = index === focusedIndex;
                    const isPast = focusedIndex >= 0 && index < focusedIndex;
                    return <div key={key} className={'list-cell' + (isCurrent ? ' is-current' : '') + (isPast ? ' is-done' : '')}><span>{key}</span><b>{formatTraceValue(item)}</b></div>;
                  })}</div>
                </div>;
              })}</div> : <div className="empty-collection">No collection values in this step</div>}
              <div className="state-machine">{scalarVariables.length ? scalarVariables.map(([name, value]) => <div key={name} className={changedVariableNames.has(name) ? 'state-card is-changed' : 'state-card'}><span>{name}</span><strong>{formatTraceValue(value)}</strong></div>) : <div className="empty-collection">No scalar values in this step</div>}</div>
              <div className="transition-list">{current?.changes.length ? current.changes.slice(0, 2).map((change, index) => <div className="transition-row" key={change.name + index}><span>{change.name}</span><strong>{change.before === undefined ? 'created' : formatTraceValue(change.before)} <i>&rarr;</i> {formatTraceValue(change.after)}</strong></div>) : <div className="no-transition">No stored value changed in this step.</div>}</div>
            </div>
          </div>
        </div>
        <div className="scene-caption"><span><i className="demo-dot" /> {current ? eventLabel : 'READY TO PLAY'}</span><span>{current ? 'CodeFlow trace' : 'Waiting for code'}</span></div>
      </div>

      <aside className="right-rail">
        <div className="panel state-panel"><div className="panel-head"><div className="panel-title"><span className="braces">{ }</span><span>Values right now</span></div><CircleHelp size={15} className="muted-icon" /></div>
          <div className="state-body">{variables.length ? variables.map(([name, value]) => <div className="state-item" key={name}><div><span className="state-name">{name}</span><span className="state-type">{current?.valueTypes?.[name] ?? (Array.isArray(value) ? 'list' : isDictionary(value) ? 'dictionary' : typeof value)}</span></div><strong>{JSON.stringify(value)}</strong></div>) : <div className="empty-state">{result ? 'No tracked variables at this step.' : 'Variables appear here while code runs.'}</div>}
            {current?.changes?.slice(0, 3).map((change, i) => <div className="why-card" key={`${change.name}-${i}`}><span>WHY IT CHANGED</span><b>{change.name}: {change.before === undefined ? 'created' : formatTraceValue(change.before)} &rarr; {formatTraceValue(change.after)}</b><small>Changed on line {current.line}.</small></div>)}
          </div>
        </div>
        <div className="panel guide-panel"><div className="panel-head"><div className="panel-title"><Waves size={15} /><span>How to read this</span></div></div><div className="guide-body"><div className="guide-row"><span className="guide-swatch selected-swatch" /><span>Bright tile = item being used</span></div><div className="guide-row"><span className="guide-swatch total-swatch" /><span>Highlighted value = changed now</span></div></div></div>
      </aside>
    </section>

    <section className="bottom-area">
      <div className="timeline-bar"><div className="timeline-title"><span className="timeline-pulse" /> PROGRAM STEPS</div><div className="timeline-track"><div className="track-fill" style={{ width: `${progress}%` }} />{result?.events.map((event, i) => <button key={i} aria-label={`Go to step ${i + 1}`} title={`${event.type} · line ${event.line ?? '—'}`} className={`event-dot ${i === step ? 'selected' : ''}`} style={{ left: `${result.events.length < 2 ? 0 : (i / (result.events.length - 1)) * 100}%` }} onClick={() => { setPlaying(false); setStep(i); }} />)}</div><div className="timeline-end">{result?.events.length ? `${result.events.length} STEPS` : 'READY'}</div></div>
      <div className="transport"><div className="transport-controls"><button title="Restart" onClick={() => setStep(0)} disabled={!result}><RotateCcw size={15} /></button><button title="Previous event" onClick={() => setStep(Math.max(0, step - 1))} disabled={!result || step === 0}><ChevronLeft size={18} /></button><button className="play-control" title="Next event" onClick={() => setStep(Math.min((result?.events.length ?? 1) - 1, step + 1))} disabled={!result}><ChevronRight size={18} /></button><button title="Next event" onClick={() => setStep(Math.min((result?.events.length ?? 1) - 1, step + 1))} disabled={!result}><FastForward size={15} /></button></div><div className="step-label">{current ? `LINE ${String(current.line ?? 'â€”').padStart(2, '0')}  Â·  ${current.type.toUpperCase()}` : 'RUN PYTHON CODE'}</div><label className="speed-control">SPEED <select value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value={0.65}>0.65?</option><option value={1}>1?</option><option value={1.5}>1.5?</option></select></label></div>
      <div className="console-panel"><div className="console-head"><div className="panel-title"><Terminal size={15} /><span>Output</span></div><span className="console-status">{error ? 'INFO' : result ? 'TRACE' : 'READY'}</span></div><div className="console-content">{error ? <span className="console-error">{error}</span> : current?.output ? current.output.split('\n').filter((line, i, all) => !(i === all.length - 1 && line === '')).map((line, i) => <div className="console-line" key={i}><span>â€º</span>{line}</div>) : <span className="console-placeholder">Program output appears here as the trace advances.</span>}</div></div>
    </section>
    <footer><span>CODEFLOW <i>Â·</i> SAFE PYTHON TRACE</span><span>Restricted Python subset Â· unsupported syntax is not run</span></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);




