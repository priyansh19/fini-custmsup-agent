import { useState, useEffect } from 'react';
import Head from 'next/head';
import styles from '../styles/Evals.module.css';

interface Check {
  pass: boolean;
  check: string;
}

interface EvalResult {
  scenario: string;
  why: string;
  messages: any[];
  tool_calls: any[];
  checks: Check[];
}

export default function Evals() {
  const [results, setResults] = useState<EvalResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/evals')
      .then(res => res.json())
      .then(data => {
        setResults(data.results || []);
        setLoading(false);
      })
      .catch(error => {
        console.error('Failed to load evals:', error);
        setLoading(false);
      });
  }, []);

  const passed = results.filter(r => r.checks.every(c => c.pass)).length;
  const total = results.length;

  return (
    <div className={styles.container}>
      <Head>
        <title>Eval Results - Paylane Agent</title>
      </Head>

      <main className={styles.main}>
        <div className={styles.header}>
          <h1>Evaluation Results</h1>
          <div className={styles.score}>
            Score: <strong>{passed}/{total}</strong>
          </div>
          <a href="/" className={styles.backLink}>← Back to Chat</a>
        </div>

        {loading ? (
          <div className={styles.loading}>Loading results...</div>
        ) : (
          <div className={styles.grid}>
            {results.map((result, i) => {
              const allPass = result.checks.every(c => c.pass);
              return (
                <div
                  key={i}
                  className={`${styles.card} ${allPass ? styles.pass : styles.fail}`}
                  onClick={() => setSelected(selected === result.scenario ? null : result.scenario)}
                >
                  <div className={styles.cardHeader}>
                    <span className={styles.status}>{allPass ? '✓' : '✗'}</span>
                    <h3>{result.scenario}</h3>
                  </div>
                  <p className={styles.why}>{result.why}</p>
                  
                  <div className={styles.checks}>
                    {result.checks.map((check, j) => (
                      <div key={j} className={`${styles.check} ${check.pass ? styles.checkPass : styles.checkFail}`}>
                        {check.pass ? '✓' : '✗'} {check.check}
                      </div>
                    ))}
                  </div>

                  {selected === result.scenario && (
                    <details open className={styles.transcript}>
                      <summary>View Transcript</summary>
                      <div className={styles.messages}>
                        {result.messages.map((msg, k) => (
                          <div key={k} className={`${styles.message} ${styles[msg.role]}`}>
                            <strong>{msg.role}:</strong>
                            {msg.content && <div>{msg.content}</div>}
                            {msg.tool_calls && msg.tool_calls.length > 0 && (
                              <div className={styles.tools}>
                                {msg.tool_calls.map((call, l) => (
                                  <div key={l}>🔧 {call.name}({JSON.stringify(call.arguments)})</div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
