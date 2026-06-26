import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

function Trades() {
  const [trades, setTrades] = useState([]);
  const { token, user } = useAuth();

  useEffect(() => {
    fetchTrades();
  }, []);

  const fetchTrades = async () => {
    try {
      const response = await fetch('/api/trades/', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setTrades(data);
      } else {
        console.error("Failed to fetch trades or unauthorized.");
      }
    } catch (err) {
      console.error("Error fetching trades:", err);
    }
  };

  if (user?.role !== 'admin') {
    return (
      <div className="main-content" style={{ padding: '2rem' }}>
        <h1>Paper Trades</h1>
        <div className="glass-panel" style={{ color: '#FF4444' }}>
          <p>Access Denied. Paper trading is restricted to administrators.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="main-content" style={{ padding: '2rem' }}>
      <h1>Paper Trades</h1>
      
      <div className="glass-panel" style={{ marginTop: '1rem' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Sr.No</th>
              <th>Symbol</th>
              <th>Entry Time</th>
              <th>Entry Price</th>
              <th>CMP</th>
              <th>Stop Loss</th>
              <th>Target</th>
              <th>Current PnL</th>
              <th>Cumulative PnL</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade, index) => {
              const pnlColor = trade.pnl >= 0 ? '#00C851' : '#FF4444';
              const cumPnlColor = trade.cumulative_pnl >= 0 ? '#00C851' : '#FF4444';
              return (
                <tr key={trade.id}>
                  <td>{index + 1}</td>
                  <td><strong>{trade.symbol}</strong></td>
                  <td>{new Date(trade.entry_time).toLocaleString()}</td>
                  <td>₹{trade.entry_price.toFixed(2)}</td>
                  <td>{trade.cmp ? `₹${trade.cmp.toFixed(2)}` : '—'}</td>
                  <td>₹{trade.sl.toFixed(2)}</td>
                  <td>₹{trade.target.toFixed(2)}</td>
                  <td style={{ color: pnlColor, fontWeight: 'bold' }}>
                    {trade.pnl ? `${trade.pnl > 0 ? '+' : ''}₹${trade.pnl.toFixed(2)} (${trade.pnl_pct.toFixed(2)}%)` : '—'}
                  </td>
                  <td style={{ color: cumPnlColor, fontWeight: 'bold' }}>
                    {trade.cumulative_pnl ? `${trade.cumulative_pnl > 0 ? '+' : ''}₹${trade.cumulative_pnl.toFixed(2)}` : '—'}
                  </td>
                </tr>
              );
            })}
            {trades.length === 0 && (
              <tr>
                <td colSpan="9" style={{ textAlign: 'center', padding: '2rem' }}>
                  No paper trades found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Trades;
