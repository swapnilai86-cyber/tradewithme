import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function Dashboard() {
  const { token } = useAuth();
  const [summary, setSummary] = useState({
    watchlist_count: 0,
    open_trades_count: 0,
    total_pnl: 0,
    win_rate: 0
  });
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [dashRes, alertsRes] = await Promise.all([
          fetch('/api/dashboard/', { headers: { 'Authorization': `Bearer ${token}` } }),
          fetch('/api/alerts/?limit=5', { headers: { 'Authorization': `Bearer ${token}` } })
        ]);
        
        if (dashRes.ok) {
          const dashData = await dashRes.json();
          setSummary(dashData);
        }
        if (alertsRes.ok) {
          const alertsData = await alertsRes.json();
          setAlerts(alertsData.data || []);
        }
      } catch (err) {
        console.error("Error fetching dashboard data:", err);
      } finally {
        setLoading(false);
      }
    };
    if (token) {
      fetchDashboardData();
    }
  }, [token]);

  const getBadgeColor = (type) => {
    if (!type) return 'gray';
    const t = type.toUpperCase();
    if (t.includes('EARLY_RADAR')) return 'yellow';
    if (t.includes('ENTRY') || t.includes('TP_HIT')) return 'green';
    if (t.includes('RETEST')) return 'cyan';
    if (t.includes('EXIT') || t.includes('SL_HIT') || t.includes('KILL')) return 'red';
    return 'gray';
  };

  if (loading) {
    return <div className="main-content" style={{ padding: '2rem' }}>Loading dashboard...</div>;
  }

  return (
    <div className="main-content">
      <h1>Dashboard</h1>
      
      <div className="stats-grid">
        <Link to="/trades" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
          <div className="glass-panel stat-card" style={{ cursor: 'pointer', height: '100%' }}>
            <h3>Total PnL</h3>
            <div className={`value ${summary.total_pnl >= 0 ? 'text-green' : 'text-red'}`}>
              {summary.total_pnl > 0 ? '+' : ''}₹{summary.total_pnl.toFixed(2)}
            </div>
          </div>
        </Link>
        <Link to="/trades" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
          <div className="glass-panel stat-card" style={{ cursor: 'pointer', height: '100%' }}>
            <h3>Win Rate</h3>
            <div className="value text-green">{summary.win_rate.toFixed(1)}%</div>
          </div>
        </Link>
        <Link to="/trades" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
          <div className="glass-panel stat-card" style={{ cursor: 'pointer', height: '100%' }}>
            <h3>Open Trades</h3>
            <div className="value">{summary.open_trades_count}</div>
          </div>
        </Link>
        <Link to="/watchlist" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
          <div className="glass-panel stat-card" style={{ cursor: 'pointer', height: '100%' }}>
            <h3>Watchlist Symbols</h3>
            <div className="value">{summary.watchlist_count}</div>
          </div>
        </Link>
      </div>

      <div className="glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>Recent Alerts</h2>
          <Link to="/alerts" style={{ color: '#3b82f6', textDecoration: 'none', fontSize: '0.9rem' }}>View All →</Link>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Type</th>
              <th>Price</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {alerts.length > 0 ? alerts.map(alert => (
              <tr key={alert.id}>
                <td><strong>{alert.symbol}</strong></td>
                <td>
                  <span className={`badge badge-${getBadgeColor(alert.alert_type)}`}>
                    {alert.alert_type.replace('_', ' ')}
                  </span>
                </td>
                <td>₹{alert.price?.toFixed(2)}</td>
                <td style={{ maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={alert.message}>
                  {alert.message}
                </td>
              </tr>
            )) : (
              <tr><td colSpan="4" style={{textAlign: 'center'}}>No recent alerts found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Dashboard;
