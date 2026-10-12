import { useState, useEffect, useCallback, useMemo } from 'react';
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
  const [showConfig, setShowConfig] = useState(true);
  const [showDemoInfo, setShowDemoInfo] = useState(true);
  const [showToolCalls, setShowToolCalls] = useState(false);
  const [config, setConfig] = useState<Config>({
    model: 'openai/gpt-4o-mini',
    provider: 'OpenRouter',
    temperature: 0,
    maxTokens: 4096,
  });
  const [testResults, setTestResults] = useState<any>(null);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMessage = input;
    setInput('');
    
    // Immediately show user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
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
          { role: 'assistant', content: `Error: ${data.error}` }
        ]);
      } else {
        // Update with full conversation from server
        setMessages(data.messages || []);
        setChatState(data.state || null);
        setToolCalls(data.tool_calls || []);
        setDemoMode(data.demo_mode || false);
      }
    } catch (err) {
      setMessages(prev => [...prev,
        { role: 'assistant', content: `Error: ${err instanceof Error ? err.message : 'Network error'}` }
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, chatState, config]);

  const resetChat = useCallback(() => {
    setMessages([]);
    setToolCalls([]);
    setChatState(null);
    setDemoMode(false);
  }, []);

  const setExampleMessage = useCallback((message: string) => {
    setInput(message);
  }, []);

  const runQuickTest = useCallback(async () => {
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
  }, [config]);

  return (
    <div className={styles.container}>
      <Head>
        <title>Paylane Support Agent - Demo</title>
        <link rel="icon" href="/favicon.ico" />
      </Head>

      {/* Left Sidebar - Configuration */}
      <aside className={styles.leftSidebar}>
        <div className={styles.sidebarHeader}>
          <h2>⚙️ Model Settings</h2>
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

        <div className={styles.debugSection}>
          <label>
            <input 
              type="checkbox" 
              checked={showToolCalls} 
              onChange={(e) => setShowToolCalls(e.target.checked)} 
            />
            Show Internal Tool Calls
          </label>
          <small>For testing/debugging only</small>
        </div>

        <div className={styles.sidebarStats}>
          <h3>📊 Session Stats</h3>
          <div><span>Messages:</span> <strong>{messages.length}</strong></div>
          <div><span>Tool Calls:</span> <strong>{toolCalls.length}</strong></div>
          <div><span>Mode:</span> <strong>{demoMode ? '🎭 Demo' : '🔴 Live'}</strong></div>
          <div><span>Model:</span> <strong>{config.model.split('/').pop()}</strong></div>
        </div>
      </aside>

      {/* Right Sidebar - Demo Info */}
      <aside className={styles.rightSidebar}>
        <div className={styles.sidebarHeader}>
          <h2>💡 Demo Information</h2>
          <button onClick={() => setShowDemoInfo(!showDemoInfo)}>
            {showDemoInfo ? '−' : '+'}
          </button>
        </div>

        {showDemoInfo && (
          <>
            <div className={styles.demoSection}>
              <h3>📝 What This Is</h3>
              <p>Interactive demo of an AI-powered customer support agent for Paylane (fintech).</p>
              <p><strong>Features:</strong></p>
              <ul>
                <li>Automated refund processing</li>
                <li>Policy enforcement ($75 limit, 30 days)</li>
                <li>Fraud detection & escalation</li>
                <li>Multi-turn conversation memory</li>
              </ul>
            </div>

            <div className={styles.demoSection}>
              <h3>🧪 Try These Examples</h3>
              <div className={styles.exampleButtons}>
                <button onClick={() => setExampleMessage('Hi, I was charged for Spotify twice. Transaction T100. Email aisha@example.com, card 4242')}>
                  ✅ Simple Refund
                </button>
                <button onClick={() => setExampleMessage('Refund my Zara purchase T102. aisha@example.com 4242')}>
                  ❌ Over Limit ($120)
                </button>
                <button onClick={() => setExampleMessage('Refund T200 please. ben@example.com 1881')}>
                  🔒 Frozen Card
                </button>
                <button onClick={() => setExampleMessage('T301 is fraud! I never made it. chen@example.com 0007')}>
                  ⚠️ Fraud Claim
                </button>
                <button onClick={() => setExampleMessage('I want a refund')}>
                  ❓ Vague Request
                </button>
              </div>
            </div>

            <div className={styles.demoSection}>
              <h3>👥 Test Accounts</h3>
              <div className={styles.account}>
                <strong>Aisha Khan</strong><br/>
                Email: aisha@example.com<br/>
                Card: ending 4242<br/>
                Status: Active ✅
              </div>
              <div className={styles.account}>
                <strong>Ben Ortiz</strong><br/>
                Email: ben@example.com<br/>
                Card: ending 1881<br/>
                Status: Frozen 🔒
              </div>
              <div className={styles.account}>
                <strong>Chen Wei</strong><br/>
                Email: chen@example.com<br/>
                Card: ending 0007<br/>
                Status: Active ✅
              </div>
            </div>

            <div className={styles.demoSection}>
              <h3>💳 Sample Transactions</h3>
              <div className={styles.transaction}>
                <strong>T100</strong>: Spotify $42.50 (Oct 1)<br/>
                <small>✅ Eligible for refund</small>
              </div>
              <div className={styles.transaction}>
                <strong>T102</strong>: Zara $120.00 (Oct 3)<br/>
                <small>❌ Over $75 limit</small>
              </div>
              <div className={styles.transaction}>
                <strong>T103</strong>: Netflix $30.00 (Aug 20)<br/>
                <small>❌ Over 30 days old</small>
              </div>
              <div className={styles.transaction}>
                <strong>T200</strong>: Steam $60.00 (Oct 4)<br/>
                <small>🔒 Ben's frozen card</small>
              </div>
            </div>

            <div className={styles.demoSection}>
              <h3>📚 Learn More</h3>
              <a href="/evals" target="_blank">View Eval Results →</a><br/>
              <a href="https://github.com/priyansh19/fini-custmsup-agent" target="_blank">GitHub Repo →</a>
            </div>
          </>
        )}
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <h1>💬 Paylane Support Agent</h1>
          <div className={styles.headerRight}>
            {demoMode && <span className={styles.demoBanner}>🎭 Demo Mode</span>}
            <button onClick={resetChat} className={styles.newChatBtn}>New Chat</button>
          </div>
        </header>

        <div className={styles.chat}>
          {messages.length === 0 && (
            <div className={styles.welcomeMessage}>
              <h2>👋 Welcome to Paylane Support</h2>
              <p>I'm here to help with refunds, account questions, and transaction issues.</p>
              <p className={styles.welcomeHint}>
                <strong>Tip:</strong> Click an example on the right to get started →
              </p>
            </div>
          )}
          {messages.map((msg, idx) => (
            <div key={idx} className={`${styles.message} ${styles[msg.role]}`}>
              <div className={styles.messageMeta}>
                {msg.role === 'user' ? '👤 You' : '🤖 Support Agent'}
              </div>
              <div className={styles.messageContent}>
                {msg.content}
              </div>
            </div>
          ))}
          {loading && (
            <div className={`${styles.message} ${styles.assistant}`}>
              <div className={styles.messageMeta}>🤖 Support Agent</div>
              <div className={styles.messageContent}>
                <span className={styles.loading}>Typing...</span>
              </div>
            </div>
          )}
        </div>

        {showToolCalls && toolCalls.length > 0 && (
          <details className={styles.toolCalls}>
            <summary>🔧 Internal Tool Calls ({toolCalls.length}) - Debug View</summary>
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
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Type your message..."
            disabled={loading}
            autoFocus
          />
          <button onClick={sendMessage} disabled={loading || !input.trim()}>
            Send
          </button>
        </div>
      </main>
    </div>
  );
}
