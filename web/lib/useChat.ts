import { useCallback, useRef, useState } from 'react';

export interface Message { role: 'user' | 'assistant'; content: string; }
export interface ToolCall { name: string; arguments: any; result: any; }

/** Chat client for POST /api/chat. Conversation state is an opaque signed blob held here.
 *  Reliability: retries transient failures (network, 429, 5xx) with backoff, re-sending
 *  the SAME state, so a flaky turn never loses the conversation. */
export function useChat(config?: Record<string, any>) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [loading, setLoading] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [lastLatency, setLastLatency] = useState<number | null>(null);
  const stateRef = useRef<string | null>(null);
  const busy = useRef(false);

  const send = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || busy.current) return;
    busy.current = true; setLoading(true);
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    const t0 = performance.now();
    let attempt = 0, done = false;
    while (!done) {
      try {
        const r = await fetch('/api/chat', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg, state: stateRef.current, config }),
        });
        const data = await r.json().catch(() => ({ error: 'Bad response' }));
        if (r.ok && !data.error) {
          stateRef.current = data.state || null;
          setMessages((data.messages || []).filter((m: any) => (m.role === 'user' || m.role === 'assistant') && (m.content || '').trim()));
          setToolCalls(data.tool_calls || []);
          setDemoMode(!!data.demo_mode);
          done = true;
        } else if ((r.status === 429 || r.status >= 500) && attempt < 2) {
          attempt++; await new Promise(res => setTimeout(res, 1200 * attempt));
        } else {
          if (r.status === 400 && /state/i.test(data.error || '')) stateRef.current = null;
          setMessages(prev => [...prev, { role: 'assistant', content: r.status >= 500 ? "Sorry, I'm having trouble connecting right now. Please try sending that again." : (data.error || 'Something went wrong.') }]);
          done = true;
        }
      } catch {
        if (attempt < 2) { attempt++; await new Promise(res => setTimeout(res, 1200 * attempt)); }
        else { setMessages(prev => [...prev, { role: 'assistant', content: "You seem to be offline. Please check your connection and try again." }]); done = true; }
      }
    }
    setLastLatency(Math.round(performance.now() - t0));
    busy.current = false; setLoading(false);
  }, [config]);

  const reset = useCallback(() => { stateRef.current = null; setMessages([]); setToolCalls([]); setDemoMode(false); }, []);
  return { messages, toolCalls, loading, demoMode, lastLatency, send, reset };
}
