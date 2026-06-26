import React, { useState, useEffect, useRef, useCallback } from 'react';

const LEVEL_STYLES = {
  INFO:     { color: '#60a5fa', bg: 'rgba(96,165,250,0.12)',  label: 'INFO'  },
  WARNING:  { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  label: 'WARN'  },
  ERROR:    { color: '#f87171', bg: 'rgba(248,113,113,0.12)', label: 'ERROR' },
  CRITICAL: { color: '#ff4dff', bg: 'rgba(255,77,255,0.15)',  label: 'CRIT'  },
  DEBUG:    { color: '#6b7280', bg: 'rgba(107,114,128,0.10)', label: 'DEBUG' },
};

const FILTERS = ['ALL', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];
const LINE_LIMITS = [50, 100, 500, 1000, 5000];

function parseEntry(raw) {
  // raw.message is the JSON string from JSONFormatter; try to parse it
  try {
    const inner = JSON.parse(raw.message);
    return {
      timestamp: inner.timestamp || raw.timestamp,
      level: inner.level || raw.level || 'INFO',
      name: inner.name || raw.name || '',
      message: inner.message || raw.message,
      reason_code: inner.reason_code || '',
      symbol: inner.symbol || '',
    };
  } catch {
    return {
      timestamp: raw.timestamp,
      level: raw.level || 'INFO',
      name: raw.name || '',
      message: raw.message,
      reason_code: '',
      symbol: '',
    };
  }
}

export default function Logs() {
  const [entries, setEntries] = useState([]);
  const [filter, setFilter] = useState('ALL');
  const [maxLines, setMaxLines] = useState(100);
  const [search, setSearch] = useState('');
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);

  const bottomRef = useRef(null);
  const esRef = useRef(null);
  const pausedRef = useRef(false);
  pausedRef.current = paused;

  // SSE connection
  const connect = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    // Close existing
    if (esRef.current) esRef.current.close();

    const url = `/api/logs/stream`;
    // EventSource doesn't support custom headers — pass token as query param
    const es = new EventSource(`${url}?token=${token}&lines=${maxLines}`);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => {
      setConnected(false);
      // Reconnect after 3s
      setTimeout(connect, 3000);
    };

    es.onmessage = (e) => {
      if (pausedRef.current) return;
      try {
        const raw = JSON.parse(e.data);
        if (raw.type === 'heartbeat') return;
        const entry = parseEntry(raw);
        setEntries(prev => {
          const next = [...prev, entry];
          return next.length > maxLines ? next.slice(-maxLines) : next;
        });
      } catch { /* ignore parse errors */ }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (esRef.current) esRef.current.close();
    };
  }, [connect, maxLines]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && !paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [entries, autoScroll, paused]);

  // Filtered entries
  const visible = entries.filter(e => {
    if (filter !== 'ALL' && e.level !== filter) return false;
    if (search && !JSON.stringify(e).toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const clearLogs = () => setEntries([]);

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100vh',
      padding: '1.5rem', gap: '1rem', background: '#0a0a0f', color: '#e2e8f0',
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <h1 style={{ margin: 0, fontSize: '1.4rem', color: '#f1f5f9', fontFamily: 'inherit' }}>
            📋 Live Logs
          </h1>
          {/* Connection dot */}
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.2rem 0.6rem', borderRadius: '999px', fontSize: '0.75rem',
            background: connected ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
            color: connected ? '#4ade80' : '#f87171',
            border: `1px solid ${connected ? '#4ade8040' : '#f8717140'}`,
          }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: connected ? '#4ade80' : '#f87171',
              boxShadow: connected ? '0 0 6px #4ade80' : 'none',
              animation: connected ? 'pulse 2s infinite' : 'none',
            }} />
            {connected ? 'LIVE' : 'DISCONNECTED'}
          </span>
        </div>

        {/* Filter pills */}
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          {FILTERS.map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '0.25rem 0.75rem', borderRadius: '999px', fontSize: '0.75rem',
              fontFamily: 'inherit', cursor: 'pointer', fontWeight: 600,
              border: `1px solid ${filter === f ? '#6366f1' : '#2d2d3a'}`,
              background: filter === f ? 'rgba(99,102,241,0.25)' : 'rgba(30,30,46,0.8)',
              color: filter === f ? '#a5b4fc' : '#9ca3af',
              transition: 'all 0.15s',
            }}>
              {f}
            </button>
          ))}
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="🔍  Search logs..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            padding: '0.35rem 0.75rem', borderRadius: '8px', fontSize: '0.8rem',
            fontFamily: 'inherit', background: '#1e1e2e', color: '#e2e8f0',
            border: '1px solid #2d2d3a', outline: 'none', flex: '1', minWidth: 150,
          }}
        />

        {/* Limit Dropdown */}
        <select 
          value={maxLines} 
          onChange={e => {
            setMaxLines(Number(e.target.value));
            setEntries([]); // Clear so we don't get duplicates when reconnecting
          }}
          style={{
            padding: '0.35rem', borderRadius: '8px', fontSize: '0.8rem',
            fontFamily: 'inherit', background: '#1e1e2e', color: '#e2e8f0',
            border: '1px solid #2d2d3a', outline: 'none',
          }}
        >
          {LINE_LIMITS.map(limit => (
            <option key={limit} value={limit}>{limit} Lines</option>
          ))}
        </select>

        {/* Controls */}
        <div style={{ display: 'flex', gap: '0.5rem', marginLeft: 'auto' }}>
          <button onClick={() => setPaused(p => !p)} style={{
            padding: '0.35rem 0.9rem', borderRadius: '8px', fontSize: '0.8rem',
            fontFamily: 'inherit', cursor: 'pointer', fontWeight: 600,
            border: `1px solid ${paused ? '#fbbf24' : '#2d2d3a'}`,
            background: paused ? 'rgba(251,191,36,0.15)' : 'rgba(30,30,46,0.8)',
            color: paused ? '#fbbf24' : '#9ca3af',
          }}>
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button onClick={() => setAutoScroll(a => !a)} style={{
            padding: '0.35rem 0.9rem', borderRadius: '8px', fontSize: '0.8rem',
            fontFamily: 'inherit', cursor: 'pointer', fontWeight: 600,
            border: `1px solid ${autoScroll ? '#6366f1' : '#2d2d3a'}`,
            background: autoScroll ? 'rgba(99,102,241,0.15)' : 'rgba(30,30,46,0.8)',
            color: autoScroll ? '#a5b4fc' : '#9ca3af',
          }}>
            {autoScroll ? '↕ Auto' : '↕ Manual'}
          </button>
          <button onClick={clearLogs} style={{
            padding: '0.35rem 0.9rem', borderRadius: '8px', fontSize: '0.8rem',
            fontFamily: 'inherit', cursor: 'pointer', fontWeight: 600,
            border: '1px solid #2d2d3a', background: 'rgba(30,30,46,0.8)',
            color: '#9ca3af',
          }}>
            🗑 Clear
          </button>
        </div>
      </div>

      {/* Count bar */}
      <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
        Showing {visible.length} of {entries.length} entries
        {paused && <span style={{ color: '#fbbf24', marginLeft: 12 }}>⏸ Paused — new logs buffered</span>}
      </div>

      {/* Log area */}
      <div style={{
        flex: 1, overflowY: 'auto', overflowX: 'auto',
        background: '#0d0d17', borderRadius: '12px',
        border: '1px solid #1e1e2e', padding: '0.75rem 0',
      }}>
        {visible.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', height: '100%', color: '#4b5563', gap: '0.5rem',
          }}>
            <div style={{ fontSize: '2.5rem' }}>📭</div>
            <div style={{ fontSize: '0.9rem' }}>
              {connected ? 'Waiting for log entries...' : 'Connecting to log stream...'}
            </div>
          </div>
        ) : (
          visible.map((entry, i) => {
            const style = LEVEL_STYLES[entry.level] || LEVEL_STYLES.INFO;
            const ts = entry.timestamp ? entry.timestamp.substring(11, 23) : '';
            return (
              <div key={i} style={{
                display: 'flex', gap: '0.75rem', alignItems: 'flex-start',
                padding: '0.3rem 1rem',
                background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
                borderLeft: `3px solid ${i === visible.length - 1 ? style.color : 'transparent'}`,
                transition: 'background 0.1s',
              }}>
                {/* Timestamp */}
                <span style={{ color: '#4b5563', fontSize: '0.72rem', whiteSpace: 'nowrap', minWidth: 90 }}>
                  {ts}
                </span>
                {/* Level badge */}
                <span style={{
                  fontSize: '0.68rem', fontWeight: 700, padding: '0.1rem 0.45rem',
                  borderRadius: '4px', background: style.bg, color: style.color,
                  minWidth: 40, textAlign: 'center', whiteSpace: 'nowrap',
                }}>
                  {style.label}
                </span>
                {/* Logger name */}
                <span style={{ color: '#6b7280', fontSize: '0.72rem', whiteSpace: 'nowrap', minWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {entry.name?.split('.').slice(-2).join('.')}
                </span>
                {/* Message */}
                <span style={{ color: '#d1d5db', fontSize: '0.8rem', wordBreak: 'break-all', flex: 1 }}>
                  {entry.symbol && (
                    <span style={{ color: '#fbbf24', marginRight: '0.5rem', fontWeight: 700 }}>
                      [{entry.symbol}]
                    </span>
                  )}
                  {entry.message}
                  {entry.reason_code && (
                    <span style={{ color: '#6366f1', marginLeft: '0.5rem', fontSize: '0.7rem' }}>
                      #{entry.reason_code}
                    </span>
                  )}
                </span>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
