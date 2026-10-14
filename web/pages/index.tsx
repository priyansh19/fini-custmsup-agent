import { useEffect, useMemo, useRef, useState } from 'react';
import Head from 'next/head';
import Link from 'next/link';
import s from '../styles/Support.module.css';
import { useChat } from '../lib/useChat';

type Txn = { id: string; merchant: string; amount: number; date: string; status: string; hint: string };
type Persona = { id: string; name: string; email: string; last4: string; status: string; transactions: Txn[] };
type Scenario = { id: string; title: string; emoji: string; persona: string | null; expect: string; message: string; rule?: string };
type Mode = 'expanded' | 'brief';
type Catalog = { mode?: Mode; personas: Persona[]; scenarios: Scenario[]; rules?: { id: string; rule: string }[]; omitted?: string[]; tools?: string[] };

// Fallback if /api/scenarios is unreachable (same data the API serves).
const FALLBACK: Catalog = {
  personas: [
    { id: 'PL-48213', name: 'Amara Okafor', email: 'amara.okafor@maplecrest.test', last4: '6417', status: 'active', transactions: [] },
    { id: 'PL-51907', name: 'Mateo Alvarez', email: 'mateo.alvarez@maplecrest.test', last4: '3058', status: 'frozen', transactions: [] },
    { id: 'PL-36642', name: 'Mei-Lin Tan', email: 'meilin.tan@maplecrest.test', last4: '9126', status: 'active', transactions: [] },
  ],
  scenarios: [
    { id: 'spotify', title: 'Refund a Spotify charge', emoji: '🎧', persona: 'PL-48213', expect: 'Refunded instantly', message: 'Hi, I was charged twice for Spotify (TXN-58214). Email amara.okafor@maplecrest.test, card ending 6417.' },
    { id: 'overlimit', title: 'Over-limit refund', emoji: '💸', persona: 'PL-48213', expect: 'Handed to a specialist', message: 'Please refund my $120 Zara order TXN-58241. amara.okafor@maplecrest.test, card 6417' },
    { id: 'frozen', title: 'My card is frozen', emoji: '🧊', persona: 'PL-51907', expect: 'Reason explained + specialist', message: 'Why is my card frozen? mateo.alvarez@maplecrest.test, card 3058' },
    { id: 'fraud', title: 'Report fraud', emoji: '🚨', persona: 'PL-36642', expect: 'Escalated, no auto-refund', message: "I didn't make the $50 Lyft charge TXN-73325. meilin.tan@maplecrest.test, card 9126" },
  ],
};

const AVATAR: Record<string, string> = { 'PL-48213': '👩🏾', 'PL-51907': '🧑🏽', 'PL-36642': '👩🏻‍💼' };

export default function Support() {
  const [mode, setMode] = useState<Mode>('expanded');
  const config = useMemo(() => ({ policy_mode: mode }), [mode]);
  const chat = useChat(config);
  const [cat, setCat] = useState<Catalog>(FALLBACK);
  const brief = mode === 'brief';
  const [persona, setPersona] = useState<string>('PL-48213');
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [copied, setCopied] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { const q = new URLSearchParams(window.location.search).get('mode'); if (q === 'brief' || q === 'expanded') setMode(q); }, []);
  useEffect(() => { fetch(`/api/scenarios?mode=${mode}`).then(r => r.json()).then(d => d?.personas && setCat(d)).catch(() => {}); }, [mode]);
  const switchMode = (m: Mode) => {
    if (m === mode) return;
    chat.reset(); setMode(m);
    const u = new URL(window.location.href); u.searchParams.set('mode', m); window.history.replaceState(null, '', u.toString());
  };
  useEffect(() => { if (window.innerWidth >= 900) setOpen(true); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chat.messages, chat.loading]);

  const p = cat.personas.find(x => x.id === persona) || cat.personas[0];
  const runScenario = (sc: Scenario) => { if (sc.persona) setPersona(sc.persona); setOpen(true); chat.send(sc.message); };
  const send = () => { const t = input.trim(); if (!t || chat.loading) return; setInput(''); chat.send(t); };
  const useMyDetails = () => { setOpen(true); setInput(`Hi, my email is ${p.email} and my card ends in ${p.last4}.`); setTimeout(() => inputRef.current?.focus(), 50); };
  const copy = (v: string) => { navigator.clipboard?.writeText(v); setCopied(v); setTimeout(() => setCopied(''), 1200); };

  return (
    <div className={`${s.page} ${open ? s.withWidget : ''}`}>
      <Head>
        <title>Paylane Help Center</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <div className={s.bg} aria-hidden />

      <nav className={s.nav}>
        <div className={s.logo}><span>P</span>Paylane</div>
        <div className={s.navLinks}>
          <a>Cards</a><a>Payments</a><a className={s.active}>Help</a>
        </div>
        <span className={`${s.modePill} ${brief ? s.modePillBrief : ''}`}>{brief ? '◆ Brief-only mode' : '◇ Expanded mode'}</span>
        <Link href="/admin" className={s.devLink}>Developer view ⚙</Link>
      </nav>

      <header className={s.hero}>
        <div className={s.badge}>● Support is online · avg reply in seconds</div>
        <h1>Hi there, how can we <em>help?</em></h1>
        <p>Refunds, card freezes and suspicious charges, sorted in one chat. Pick a topic or start a conversation.</p>
        <div className={s.modeSwitch} role="tablist" aria-label="Policy mode">
          <button role="tab" aria-selected={brief} className={brief ? s.modeOn : ''} onClick={() => switchMode('brief')}>
            <b>Brief-only</b><small>Deepak's brief, exactly · 4 spec tools</small></button>
          <button role="tab" aria-selected={!brief} className={!brief ? s.modeOn : ''} onClick={() => switchMode('expanded')}>
            <b>Expanded</b><small>Submitted version · resolution-first extras</small></button>
          <span className={`${s.modeGlider} ${brief ? '' : s.modeGliderRight}`} aria-hidden />
        </div>
        <button className={s.cta} onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 50); }}>💬 Chat with support</button>
      </header>

      <main className={s.grid}>
        <section className={s.topics}>
          <h2>{brief ? 'Every rule in the brief' : 'Popular topics'} <small>tap to try it live</small></h2>
          <div className={s.cards}>
            {cat.scenarios.map((sc, i) => (
              <button key={sc.id} className={s.card} style={{ animationDelay: `${i * 50}ms` }} onClick={() => runScenario(sc)} disabled={chat.loading}>
                <span className={s.emoji}>{sc.emoji}</span>
                <b>{sc.title}</b>
                {sc.rule && <span className={s.ruleTag}>{sc.rule}</span>}
                <span className={s.expect}>{sc.expect}</span>
                <span className={s.go}>Ask now →</span>
              </button>
            ))}
          </div>
        </section>

        <aside className={s.sideCol}>
        {brief && cat.rules && (
          <div className={s.rulesPanel}>
            <h2>Brief policy <span className={s.rulesBadge}>active</span></h2>
            <ol>{cat.rules.map(r => <li key={r.id}>{r.rule}</li>)}</ol>
            <div className={s.toolsRow}>{(cat.tools || []).map(t => <code key={t}>{t}</code>)}</div>
            {cat.omitted && <div className={s.omitted}><span>Not in this mode:</span> {cat.omitted.join(' · ')}</div>}
          </div>
        )}
        <div className={s.personaBox}>
          <h2>Demo customer</h2>
          <div className={s.personaTabs}>
            {cat.personas.map(x => (
              <button key={x.id} className={`${s.ptab} ${x.id === persona ? s.ptabOn : ''}`} onClick={() => setPersona(x.id)}>
                <span>{AVATAR[x.id] || '🙂'}</span>{x.name.split(' ')[0]}
              </button>
            ))}
          </div>
          <div className={s.idCard}>
            <div className={s.idTop}>
              <div><div className={s.idName}>{p.name}</div><div className={`${s.status} ${p.status === 'frozen' ? s.frozen : ''}`}>{p.status === 'frozen' ? '🧊 Card frozen' : '● Active'}</div></div>
              <div className={s.chipArt} />
            </div>
            <div className={s.cred} onClick={() => copy(p.email)}><span>Email</span><code>{p.email}</code><i>{copied === p.email ? '✓' : 'copy'}</i></div>
            <div className={s.cred} onClick={() => copy(p.last4)}><span>Card</span><code>•••• •••• •••• {p.last4}</code><i>{copied === p.last4 ? '✓' : 'copy'}</i></div>
            <button className={s.useBtn} onClick={useMyDetails}>Use these details in chat</button>
          </div>
          {p.transactions.length > 0 && (
            <div className={s.txns}>
              <h3>Recent activity</h3>
              {p.transactions.map(t => (
                <div key={t.id} className={s.txn}>
                  <code>{t.id}</code><span className={s.merchant}>{t.merchant}<small>{t.date.slice(5)}{t.status === 'pending' ? ' · pending' : ''}</small></span>
                  <b>${t.amount.toFixed(2)}</b>
                  <em className={/specialist|not refundable/.test(t.hint) ? s.hintBad : s.hintOk}>{t.hint}</em>
                </div>
              ))}
            </div>
          )}
        </div>
        </aside>
      </main>

      <footer className={s.footer}>Demo for the Fini take-home · mock data only · <Link href="/admin">Developer / evaluator view</Link></footer>

      {/* Messenger widget */}
      {!open && <button className={s.launcher} onClick={() => setOpen(true)} aria-label="Open chat">💬<span className={s.ping} /></button>}
      <div className={`${s.widget} ${open ? s.widgetOpen : ''}`} role="dialog" aria-label="Paylane support chat">
        <div className={s.wHead}>
          <div className={s.agentAv}>P<span className={s.online} /></div>
          <div><b>Paylane Support</b><small>{chat.loading ? 'typing…' : chat.demoMode ? 'Demo mode' : 'Online · AI assistant'} · <span className={s.wMode}>{brief ? 'Brief-only' : 'Expanded'}</span></small></div>
          <button onClick={chat.reset} title="New conversation" className={s.wBtn}>↺</button>
          <button onClick={() => setOpen(false)} title="Minimise" className={s.wBtn}>—</button>
        </div>
        <div className={s.thread}>
          <div className={`${s.row} ${s.agent}`}><div className={s.bubble}>Hi! 👋 I'm Paylane's support assistant. I can help with refunds, frozen cards and charges you don't recognise. To get started, share your <b>email</b> and your card's <b>last 4 digits</b>.</div></div>
          {chat.messages.length === 0 && (
            <div className={s.quick}>
              {cat.scenarios.slice(0, 4).map(sc => <button key={sc.id} onClick={() => runScenario(sc)}>{sc.emoji} {sc.title}</button>)}
            </div>
          )}
          {chat.messages.map((m, i) => (
            <div key={i} className={`${s.row} ${m.role === 'user' ? s.user : s.agent}`}><div className={s.bubble}>{m.content}</div></div>
          ))}
          {brief && chat.toolCalls.length > 0 && (
            <details className={s.trace} open>
              <summary>🛠 Tool calls · {chat.toolCalls.length}</summary>
              {chat.toolCalls.map((t, i) => {
                const r = t.result || {};
                const bad = r.ok === false || r.error || r.verified === false || r.refund_check?.eligible === false;
                const good = r.ok === true || r.verified === true || r.ticket_id || r.refund_check?.eligible === true;
                const note = r.refund_id ? `refund ${r.refund_id}` : r.ticket_id ? `ticket ${r.ticket_id}` : r.reason ? String(r.reason).replace('blocked_by_policy:', 'blocked: ')
                  : r.refund_check ? `${r.merchant} $${r.amount} · ${r.status} · ${r.refund_check.reason}` : r.error ? r.error : r.verified ? `verified · ${r.status}` : r.verified === false ? 'not verified' : '';
                return (<div key={i} className={`${s.tcall} ${bad ? s.tcBad : good ? s.tcGood : ''}`}>
                  <code>{t.name}{t.arguments?.auto ? ' (auto)' : ''}</code><span>{note}</span></div>);
              })}
            </details>
          )}
          {chat.loading && <div className={`${s.row} ${s.agent}`}><div className={`${s.bubble} ${s.typing}`}><i /><i /><i /></div></div>}
          <div ref={endRef} />
        </div>
        <div className={s.composer}>
          <button className={s.idBtn} onClick={useMyDetails} title={`Insert ${p.name}'s details`}>{AVATAR[p.id] || '🙂'}</button>
          <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} placeholder="Write a message…"
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); send(); } }} disabled={chat.loading} />
          <button className={s.send} onClick={send} disabled={chat.loading || !input.trim()} aria-label="Send">➤</button>
        </div>
        <div className={s.powered}>{brief ? "Brief-only mode · full refunds ≤ $75, under 30 days, settled charges" : 'Secured by guardrails · refunds ≤ $75 within 30 days'}</div>
      </div>
    </div>
  );
}
