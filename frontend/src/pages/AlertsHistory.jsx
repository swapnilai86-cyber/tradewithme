import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

function AlertsHistory() {
  const [alerts, setAlerts] = useState([]);
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({ total_pages: 1 });
  const [selectedAlert, setSelectedAlert] = useState(null);
  const { token } = useAuth();

  useEffect(() => {
    fetchAlerts();
  }, [date, page]);

  const fetchAlerts = async () => {
    try {
      const url = `/api/alerts/?date=${date}&page=${page}&limit=50`;
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setAlerts(data.data);
        setPagination(data.pagination);
      }
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
    }
  };

  const getTypeColor = (type) => {
    switch(type) {
      case 'EARLY_RADAR': return '#FFD700'; // Yellow
      case 'ENTRY_TRIGGER': return '#00C851'; // Green
      case 'SL_HIT': return '#FF4444'; // Red
      case 'TP_HIT': return '#00C851'; // Green
      default: return '#9E9E9E'; // Gray
    }
  };

  const handleRowClick = (alert) => {
    // Open the standalone chart page in a new resizable window
    window.open(`/chart/${alert.symbol}`, `Chart_${alert.symbol}`, 'width=1200,height=800,resizable=yes');
  };

  return (
    <div className="main-content" style={{ padding: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Alerts History</h1>
        <div>
          <input 
            type="date" 
            className="input-field" 
            value={date} 
            onChange={(e) => { setDate(e.target.value); setPage(1); }} 
            style={{ marginBottom: 0, width: '200px' }}
          />
        </div>
      </div>
      
      <div className="glass-panel" style={{ marginTop: '1rem' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Type</th>
              <th>Price</th>
              <th>CMP</th>
              <th>Gross PnL</th>
              <th>Cum. PnL</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map(alert => {
              const pnlColor = alert.gross_pnl >= 0 ? '#00C851' : '#FF4444';
              const cumPnlColor = alert.cumulative_pnl >= 0 ? '#00C851' : '#FF4444';
              return (
              <tr key={alert.id}>
                <td>
                  <span 
                    onClick={() => setSelectedAlert(alert)}
                    style={{ color: '#3b82f6', textDecoration: 'underline', cursor: 'pointer' }}
                    title="View Discord Embed"
                  >
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </span>
                </td>
                <td>
                  <span 
                    onClick={() => handleRowClick(alert)}
                    style={{ color: '#00C851', textDecoration: 'underline', cursor: 'pointer' }}
                    title="View 15-Minute Chart"
                  >
                    <strong>{alert.symbol}</strong>
                  </span>
                </td>
                <td>
                  <span style={{ 
                    color: getTypeColor(alert.alert_type), 
                    fontWeight: 'bold',
                    backgroundColor: 'rgba(255,255,255,0.1)',
                    padding: '2px 8px',
                    borderRadius: '4px'
                  }}>
                    {alert.alert_type}
                  </span>
                </td>
                <td>₹{alert.price?.toFixed(2) || '—'}</td>
                <td>{alert.cmp ? `₹${alert.cmp.toFixed(2)}` : '—'}</td>
                <td style={{ color: pnlColor, fontWeight: 'bold' }}>
                  {alert.gross_pnl ? `${alert.gross_pnl > 0 ? '+' : ''}₹${alert.gross_pnl.toFixed(2)}` : '—'}
                </td>
                <td style={{ color: cumPnlColor, fontWeight: 'bold' }}>
                  {alert.cumulative_pnl ? `${alert.cumulative_pnl > 0 ? '+' : ''}₹${alert.cumulative_pnl.toFixed(2)}` : '—'}
                </td>
                <td>{alert.message}</td>
              </tr>
              );
            })}
            {alerts.length === 0 && (
              <tr>
                <td colSpan="8" style={{ textAlign: 'center', padding: '2rem' }}>
                  No alerts found for this date.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {pagination.total_pages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}>
            <button 
              className="btn btn-outline" 
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
            >
              Previous
            </button>
            <span>Page {page} of {pagination.total_pages}</span>
            <button 
              className="btn btn-outline" 
              disabled={page === pagination.total_pages}
              onClick={() => setPage(p => p + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Discord Embed Style Modal */}
      {selectedAlert && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
          backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', 
          justifyContent: 'center', alignItems: 'center', zIndex: 1000
        }} onClick={() => setSelectedAlert(null)}>
          <div style={{
            background: '#1a1a1a', 
            borderLeft: `4px solid ${getTypeColor(selectedAlert.alert_type)}`,
            borderRadius: '8px',
            padding: '1.5rem',
            maxWidth: '500px',
            width: '100%',
            boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
            maxHeight: '90vh',
            overflowY: 'auto'
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.1rem' }}>
                {selectedAlert.alert_type === 'EARLY_RADAR' ? '🟡' : 
                 selectedAlert.alert_type === 'ENTRY_TRIGGER' ? '🟢' : 
                 selectedAlert.alert_type === 'TP_HIT' ? '🎯' : '🔴'} 
                {selectedAlert.alert_type.replace(/_/g, ' ')} — {selectedAlert.symbol}
              </h3>
              <button onClick={() => setSelectedAlert(null)} style={{ background: 'transparent', border: 'none', color: '#ccc', cursor: 'pointer', fontSize: '1.2rem' }}>×</button>
            </div>
            
            <p style={{ color: '#ccc', marginBottom: '1.5rem', fontSize: '0.95rem' }}>
              {selectedAlert.message.replace(/\*\*/g, '')}
            </p>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              {selectedAlert.data && Object.entries(selectedAlert.data).map(([key, value]) => {
                // Skip non-metric fields
                if (['timestamp', 'symbol', 'reason_code', 'sector', 'date'].includes(key)) return null;
                
                // Format values intelligently
                let displayValue = String(value);
                if (typeof value === 'number') {
                  if (key.includes('pct') || key.includes('rsi') || key.includes('ratio') || key.includes('rr')) {
                    displayValue = value.toFixed(2);
                  } else {
                    displayValue = `₹${value.toFixed(2)}`;
                  }
                }
                
                return (
                  <div key={key}>
                    <div style={{ color: '#888', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '4px' }}>
                      {key.replace(/_/g, ' ')}
                    </div>
                    <div style={{ fontWeight: 'bold', fontSize: '0.95rem' }}>
                      {displayValue}
                    </div>
                  </div>
                );
              })}
            </div>
            
            <div style={{ marginTop: '1.5rem', fontSize: '0.75rem', color: '#666', borderTop: '1px solid #333', paddingTop: '0.5rem' }}>
              ⏱ {new Date(selectedAlert.timestamp).toLocaleString()} UTC | reason: {selectedAlert.data?.reason_code || 'N/A'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AlertsHistory;
