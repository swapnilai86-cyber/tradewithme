import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

function AlertsHistory() {
  const [alerts, setAlerts] = useState([]);
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({ total_pages: 1 });
  const { token } = useAuth();

  useEffect(() => {
    fetchAlerts();
  }, [date, page]);

  const fetchAlerts = async () => {
    try {
      const url = `/api/alerts?date=${date}&page=${page}&limit=50`;
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
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map(alert => (
              <tr key={alert.id}>
                <td>{new Date(alert.timestamp).toLocaleTimeString()}</td>
                <td><strong>{alert.symbol}</strong></td>
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
                <td>₹{alert.price?.toFixed(2)}</td>
                <td>{alert.message}</td>
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr>
                <td colSpan="5" style={{ textAlign: 'center', padding: '2rem' }}>
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
    </div>
  );
}

export default AlertsHistory;
