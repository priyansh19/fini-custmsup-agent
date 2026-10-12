import { useState } from 'react';
import Head from 'next/head';
import styles from '../styles/Home.module.css';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  tool_calls?: Array<{ name: string; arguments: any; id: string }>;
}

interface ToolCall {
  name: string;
  arguments: any;
  result: any;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [demoMode, setDemoMode] = useState(false);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input;
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage }),
      });

      const data = await response.json();
      
      if (data.error) {
        setMessages(prev => [...prev, 
          { role: 'user', content: userMessage },
          { role: 'assistant', content: `Error: ${data.error}` }
        ]);
      } else {
        setMessages(data.messages || []);
        setToolCalls(data.tool_calls || []);
        setDemoMode(data.demo_mode || false);
      }
    } catch (error) {
      setMessages(prev => [...prev, 
        { role: 'user', content: userMessage },
        { role: 'assistant', content: `Error: ${error.message}` }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const resetChat = async () => {
    try {
      await fetch('/api/chat', { method: 'DELETE' });
      setMessages([]);
      setToolCalls([]);
      setDemoMode(false);
    } catch (error) {
      console.error('Reset error:', error);
    }
  };

  return (
    <div className={styles.container}>
      <Head>
        <title>Paylane Support Agent</title>
        <meta name="description" content="AI support agent for Paylane" />
      </Head>

      <main className={styles.main}>
        <div className={styles.header}>
          <h1>Paylane Support Agent</h1>
          {demoMode && <div className={styles.demoTag}>DEMO MODE (No API Key)</div>}
          <button onClick={resetChat} className={styles.resetButton}>New Chat</button>
        </div>

        <div className={styles.chatContainer}>
          {messages.length === 0 ? (
            <div className={styles.welcome}>
              <p>👋 Hi! I'm Paylane's support assistant.</p>
              <p>I can help with refunds, transaction questions, and account issues.</p>
              <p className={styles.hint}>To get started, provide your email and card's last 4 digits.</p>
            </div>
          ) : (
            <div className={styles.messages}>
              {messages.map((msg, i) => (
                <div key={i} className={`${styles.message} ${styles[msg.role]}`}>
                  <div className={styles.messageContent}>{msg.content}</div>
                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <details className={styles.toolCallsDetail}>
                      <summary>🔧 Tool Calls ({msg.tool_calls.length})</summary>
                      {msg.tool_calls.map((call, j) => (
                        <div key={j} className={styles.toolCall}>
                          <strong>{call.name}</strong>
                          <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
                        </div>
                      ))}
                    </details>
                  )}
                </div>
              ))}
              {loading && <div className={styles.loading}>Thinking...</div>}
            </div>
          )}
        </div>

        <div className={styles.inputContainer}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Type your message..."
            disabled={loading}
            className={styles.input}
          />
          <button onClick={sendMessage} disabled={loading || !input.trim()} className={styles.sendButton}>
            Send
          </button>
        </div>

        <div className={styles.links}>
          <a href="/evals">View Eval Results →</a>
        </div>
      </main>
    </div>
  );
}
