import { useEffect, useRef, useState } from 'react';
import Head from 'next/head';
import Link from 'next/link';
import s from '../styles/Support.module.css';
import { useChat } from '../lib/useChat';

type Txn = { id: string; merchant: string; amount: number; date: string; status: string; hint: string };
type Persona = { id: string; name: string; email: string; last4: string; status: string; transactions: Txn[] };
type Scenario = { id: string; title: string; emoji: string; persona: string | null; expect: string; message: string };

// Fallback if /api/scenarios is unreachable (same data the API serves).
const FALLBACK: { personas: Persona[]; scenarios: Scenario[] } = {
  personas: [
    { id: 'C001', name: 'Aisha Khan', email: 'aisha@example.com', last4: '4242', status: 'active', transactions: [] },
    { id: 'C002', name: 'Ben Ortiz', email: 'ben@example.com', last4: '1881', status: 'frozen', transactions: [] },
    { id: 'C003', name: 'Chen Wei', email: 'chen@example.com', last4: '0007', status: 'active', transactions: [] },
  ],
  scenarios: [
    { id: 'spotify', title: 'Refund a Spotify charge', emoji: '🎧', persona: 'C001', expect: 'Refunded instantly', message: 'Hi, I was charged twice for Spotify (T100). Email aisha@example.com, card ending 4242.' },
    { id: 'overlimit', title: 'Over-limit refund', emoji: '💸', persona: 'C001', expect: 'Handed to a specialist', message: 'Please refund my $120 Zara order T102. aisha@example.com, card 4242' },
    { id: 'frozen', title: 'My card is frozen', emoji: '🧊', persona: 'C002', expect: 'Reason explained + specialist', message: 'Why is my card frozen? ben@example.com, card 1881' },
    { id: 'fraud', title: 'Report fraud', emoji: '🚨', persona: 'C003', expect: 'Escalated, no auto-refund', message: "I didn't make the $50 Lyft charge T301. chen@example.com, card 0007" },
  ],
};

const AVATAR: Record<string, string> = { C001: '🧕', C002: '🧔', C003: '👨‍💻' };

export default function Support() {
  const chat = useChat();
  const [cat, setCat] = useState(FALLBACK);
  const [persona, setPersona] = useState<string>('C001');
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [copied, setCopied] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { fetch('/api/scenarios').then(r => r.json()).then(d => d?.personas && setCat(d)).catch(() => {}); }, []);
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
        <Link href="/admin" className={s.devLink}>Developer view ⚙</Link>
      </nav>

      <header className={s.hero}>
        <div className={s.badge}>● Support is online · avg reply in seconds</div>
        <h1>Hi there, how can we <em>help?</em></h1>
        <p>Refunds, card freezes and suspicious charges, sorted in one chat. Pick a topic or start a conversation.</p>
        <button className={s.cta} onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 50); }}>💬 Chat with support</button>
      </header>

      <main className={s.grid}>
        <section className={s.topics}>
          <h2>Popular topics <small>tap to try it live</small></h2>
          <div className={s.cards}>
            {cat.scenarios.map((sc, i) => (
              <button key={sc.id} className={s.card} style={{ animationDelay: `${i * 50}ms` }} onClick={() => runScenario(sc)} disabled={chat.loading}>
                <span className={s.emoji}>{sc.emoji}</span>
                <b>{sc.title}</b>
                <span className={s.expect}>{sc.expect}</span>
                <span className={s.go}>Ask now →</span>
              </button>
            ))}
          </div>
        </section>

        <aside className={s.personaBox}>
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
                  <em className={/specialist/.test(t.hint) ? s.hintBad : s.hintOk}>{t.hint}</em>
                </div>
              ))}
            </div>
          )}
        </aside>
      </main>

      <footer className={s.footer}>Demo for the Fini take-home · mock data only · <Link href="/admin">Developer / evaluator view</Link></footer>

      {/* Messenger widget */}
      {!open && <button className={s.launcher} onClick={() => setOpen(true)} aria-label="Open chat">💬<span className={s.ping} /></button>}
      <div className={`${s.widget} ${open ? s.widgetOpen : ''}`} role="dialog" aria-label="Paylane support chat">
        <div className={s.wHead}>
          <div className={s.agentAv}>P<span className={s.online} /></div>
          <div><b>Paylane Support</b><small>{chat.loading ? 'typing…' : chat.demoMode ? 'Demo mode' : 'Online · AI assistant'}</small></div>
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
          {chat.loading && <div className={`${s.row} ${s.agent}`}><div className={`${s.bubble} ${s.typing}`}><i /><i /><i /></div></div>}
          <div ref={endRef} />
        </div>
        <div className={s.composer}>
          <button className={s.idBtn} onClick={useMyDetails} title={`Insert ${p.name}'s details`}>{AVATAR[p.id] || '🙂'}</button>
          <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} placeholder="Write a message…"
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); send(); } }} disabled={chat.loading} />
          <button className={s.send} onClick={send} disabled={chat.loading || !input.trim()} aria-label="Send">➤</button>
        </div>
        <div className={s.powered}>Secured by guardrails · refunds ≤ $75 within 30 days</div>
      </div>
    </div>
  );
}
