import { useState, useEffect } from 'react';
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

interface Config {
  model: string;
  provider: string;
  temperature: number;
  maxTokens: number;
}

const MODELS = {
  'OpenRouter': [
    { id: 'openai/gpt-4o-mini', name: 'GPT-4o Mini (Production)', cost: 'Low' },
    { id: 'openai/gpt-4o', name: 'GPT-4o', cost: 'Medium' },
    { id: 'anthropic/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', cost: 'High' },
    { id: 'anthropic/claude-3-haiku', name: 'Claude 3 Haiku', cost: 'Low' },
    { id: 'nvidia/nemotron-3-super-120b-a12b:free', name: 'Nemotron Super 120B (Free)', cost: 'Free' },
    { id: 'nvidia/nemotron-3.5-lightning:free', name: 'Nemotron Lightning (Free)', cost: 'Free' },
    { id: 'google/gemini-2.0-flash-exp:free', name: 'Gemini 2.0 Flash (Free)', cost: 'Free' },
    { id: 'meta-llama/llama-3.3-70b-instruct', name: 'Llama 3.3 70B', cost: 'Low' },
  ],
  'OpenAI': [
    { id: 'gpt-4o-mini', name: 'GPT-4o Mini', cost: 'Low' },
    { id: 'gpt-4o', name: 'GPT-4o', cost: 'Medium' },
    { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', cost: 'High' },
  ],
  'Anthropic': [
    { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', cost: 'High' },
    { id: 'claude-3-haiku-20240307', name: 'Claude 3 Haiku', cost: 'Low' },
  ],
  'Ollama (Local)': [
    { id: 'qwen2.5:0.5b', name: 'Qwen 2.5 0.5B', cost: 'Free' },
    { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B', cost: 'Free' },
    { id: 'qwen2.5:3b', name: 'Qwen 2.5 3B', cost: 'Free' },
    { id: 'qwen2.5:7b', name: 'Qwen 2.5 7B', cost: 'Free' },
  ],
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [demoMode, setDemoMode] = useState(false);
  const [chatState, setChatState] = useState<string | null>(null);
  
  // Configuration state
  const [showConfig, setShowConfig] = useState(false);
  const [config, setConfig] = useState<Config>({
    model: 'openai/gpt-4o-mini',
    provider: 'OpenRouter',
    temperature: 0,
    maxTokens: 4096,
  });
  const [testResults, setTestResults] = useState<any>(null);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input;
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: userMessage, 
          state: chatState,
          config: config,
        }),
      });

      const data = await response.json();
      
      if (data.error) {
        setMessages(prev => [...prev, 
          { role: 'user', content: userMessage },
          { role: 'assistant', content: `Error: ${data.error}` }
        ]);
      } else {
        setMessages(data.messages || []);
        setChatState(data.state || null);
        setToolCalls(data.tool_calls || []);
        setDemoMode(data.demo_mode || false);
      }
    } catch (err) {
      setMessages(prev => [...prev,
        { role: 'user', content: userMessage },
        { role: 'assistant', content: `Error: ${err instanceof Error ? err.message : 'Network error'}` }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const resetChat = () => {
    setMessages([]);
    setToolCalls([]);
    setChatState(null);
    setDemoMode(false);
  };

  const runQuickTest = async () => {
    setLoading(true);
    setTestResults(null);
    try {
      const testCases = [
        { message: 'Refund T100. aisha@example.com 4242', expected: 'refunded' },
        { message: 'Refund T102. aisha@example.com 4242', expected: 'escalated' },
        { message: 'Refund T300. aisha@example.com 4242', expected: 'blocked' },
      ];

      const results = [];
      for (const test of testCases) {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: test.message, state: null, config: config }),
        });
        const data = await response.json();
        results.push({
          test: test.message,
          expected: test.expected,
          response: data.messages?.[data.messages.length - 1]?.content || 'error',
          tool_calls: data.tool_calls || [],
        });
      }
      setTestResults(results);
    } catch (err) {
      alert('Test failed: ' + (err instanceof Error ? err.message : 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <Head>
        <title>Paylane Support Agent</title>
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h2>Configuration</h2>
          <button onClick={() => setShowConfig(!showConfig)}>
            {showConfig ? '−' : '+'}
          </button>
        </div>

        {showConfig && (
          <div className={styles.configPanel}>
            <div className={styles.configSection}>
              <label>Provider</label>
              <select 
                value={config.provider} 
                onChange={(e) => {
                  const provider = e.target.value;
                  const firstModel = MODELS[provider as keyof typeof MODELS][0].id;
                  setConfig({ ...config, provider, model: firstModel });
                }}
              >
                {Object.keys(MODELS).map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            <div className={styles.configSection}>
              <label>Model</label>
              <select 
                value={config.model} 
                onChange={(e) => setConfig({ ...config, model: e.target.value })}
              >
                {MODELS[config.provider as keyof typeof MODELS]?.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.cost})
                  </option>
                ))}
              </select>
            </div>

            <div className={styles.configSection}>
              <label>Temperature: {config.temperature}</label>
              <input 
                type="range" 
                min="0" 
                max="1" 
                step="0.1" 
                value={config.temperature}
                onChange={(e) => setConfig({ ...config, temperature: parseFloat(e.target.value) })}
              />
              <small>Lower = more consistent, Higher = more creative</small>
            </div>

            <div className={styles.configSection}>
              <label>Max Tokens</label>
              <input 
                type="number" 
                value={config.maxTokens} 
                onChange={(e) => setConfig({ ...config, maxTokens: parseInt(e.target.value) })}
                min="256"
                max="32768"
              />
            </div>

            <div className={styles.configActions}>
              <button onClick={runQuickTest} disabled={loading}>
                Quick Test
              </button>
              <button onClick={resetChat}>Reset Chat</button>
            </div>

            {testResults && (
              <div className={styles.testResults}>
                <h3>Test Results</h3>
                {testResults.map((r: any, i: number) => (
                  <div key={i} className={styles.testResult}>
                    <div><strong>Test:</strong> {r.test}</div>
                    <div><strong>Expected:</strong> {r.expected}</div>
                    <div><strong>Tools:</strong> {r.tool_calls.length} calls</div>
                    <div className={styles.testResponse}>{r.response.substring(0, 100)}...</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className={styles.sidebarStats}>
          <h3>Session Stats</h3>
          <div>Messages: {messages.length}</div>
          <div>Tool Calls: {toolCalls.length}</div>
          <div>Mode: {demoMode ? 'Demo' : 'Live'}</div>
          <div>Model: {config.model.split('/').pop()}</div>
        </div>

        <div className={styles.sidebarInfo}>
          <h3>Testing Tips</h3>
          <ul>
            <li>Try: "Refund T100. aisha@example.com 4242"</li>
            <li>Over limit: "Refund T102. aisha@example.com 4242"</li>
            <li>Frozen card: "Refund T200. ben@example.com 1881"</li>
            <li>Fraud: "T301 is fraud! chen@example.com 0007"</li>
          </ul>
        </div>
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <h1>Paylane Support Agent</h1>
          {demoMode && <span className={styles.demoBanner}>Demo Mode (No API Key)</span>}
        </header>

        <div className={styles.chat}>
          {messages.map((msg, idx) => (
            <div key={idx} className={`${styles.message} ${styles[msg.role]}`}>
              <div className={styles.messageMeta}>
                {msg.role === 'user' ? '👤 You' : '🤖 Agent'}
              </div>
              <div className={styles.messageContent}>
                {msg.content}
                {msg.tool_calls && msg.tool_calls.length > 0 && (
                  <div className={styles.toolCallsIndicator}>
                    🔧 {msg.tool_calls.length} tool call(s)
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className={`${styles.message} ${styles.assistant}`}>
              <div className={styles.messageMeta}>🤖 Agent</div>
              <div className={styles.messageContent}>
                <span className={styles.loading}>Thinking...</span>
              </div>
            </div>
          )}
        </div>

        {toolCalls.length > 0 && (
          <details className={styles.toolCalls}>
            <summary>Tool Calls ({toolCalls.length})</summary>
            {toolCalls.map((call, idx) => (
              <div key={idx} className={styles.toolCall}>
                <div className={styles.toolName}>{call.name}</div>
                <div className={styles.toolArgs}>
                  {JSON.stringify(call.arguments, null, 2)}
                </div>
                <div className={styles.toolResult}>
                  → {JSON.stringify(call.result, null, 2)}
                </div>
              </div>
            ))}
          </details>
        )}

        <div className={styles.inputArea}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Type your message..."
            disabled={loading}
          />
          <button onClick={sendMessage} disabled={loading || !input.trim()}>
            Send
          </button>
        </div>
      </main>
    </div>
  );
}
