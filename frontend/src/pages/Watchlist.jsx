import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

function Watchlist() {
  const [watchlist, setWatchlist] = useState([]);
  const [symbol, setSymbol] = useState('');
  const [entryPrice, setEntryPrice] = useState('');
  const [exitPrice, setExitPrice] = useState('');
  const [loading, setLoading] = useState(false);
  const { token } = useAuth();

  useEffect(() => {
    fetchWatchlist();
  }, []);

  const fetchWatchlist = async () => {
    try {
      const response = await fetch('/api/watchlist/', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        setWatchlist(await response.json());
      }
    } catch (err) {
      console.error("Failed to fetch watchlist", err);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!symbol) return;
    
    setLoading(true);
    const payload = {
      symbol: symbol.toUpperCase(),
      entry_price: entryPrice ? parseFloat(entryPrice) : null,
      exit_price: exitPrice ? parseFloat(exitPrice) : null
    };

    try {
      const response = await fetch('/api/watchlist/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      if (response.ok) {
        setSymbol('');
        setEntryPrice('');
        setExitPrice('');
        fetchWatchlist();
      } else {
        const data = await response.json();
        alert(`Error: ${data.detail || 'Failed to add'}`);
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const handleDelete = async (sym) => {
    try {
      const response = await fetch(`/api/watchlist/${sym}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        fetchWatchlist();
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Calculate Cumulative PnL
  const cummPnl = watchlist.reduce((acc, item) => acc + (item.gross_pnl || 0), 0);

  return (
    <div className="main-content" style={{ padding: '2rem' }}>
      <h1>My Watchlist & Portfolio</h1>
      
      <div className="glass-panel" style={{ marginBottom: '2rem' }}>
        <h2>Add to Watchlist</h2>
        <form onSubmit={handleAdd} style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input 
            type="text" 
            className="input-field" 
            placeholder="Symbol (e.g., RELIANCE)" 
            value={symbol} 
            onChange={e => setSymbol(e.target.value)} 
            required 
            style={{ marginBottom: 0, width: '200px' }}
          />
          <input 
            type="number" 
            step="0.05"
            className="input-field" 
            placeholder="Entry Price (Optional)" 
            value={entryPrice} 
            onChange={e => setEntryPrice(e.target.value)} 
            style={{ marginBottom: 0, width: '200px' }}
          />
          <input 
            type="number" 
            step="0.05"
            className="input-field" 
            placeholder="Exit Price (Optional)" 
            value={exitPrice} 
            onChange={e => setExitPrice(e.target.value)} 
            style={{ marginBottom: 0, width: '200px' }}
          />
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Adding...' : 'Add'}
          </button>
        </form>
      </div>

      <div className="glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>Tracked Stocks</h2>
          <div style={{ padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}>
            <span style={{ marginRight: '0.5rem' }}>Cumulative PnL:</span>
            <strong style={{ color: cummPnl >= 0 ? '#00C851' : '#FF4444', fontSize: '1.2rem' }}>
              ₹{cummPnl.toFixed(2)}
            </strong>
          </div>
        </div>
        
        <table className="data-table">
          <thead>
            <tr>
              <th>Sr. No</th>
              <th>Stock Name</th>
              <th>CMP</th>
              <th>Entry Price</th>
              <th>Exit Price</th>
              <th>Gross PnL</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {watchlist.map((item, index) => (
              <tr key={item.id}>
                <td>{index + 1}</td>
                <td><strong>{item.symbol}</strong></td>
                <td>₹{item.current_price?.toFixed(2) || '0.00'}</td>
                <td>{item.entry_price ? `₹${item.entry_price.toFixed(2)}` : '-'}</td>
                <td>{item.exit_price ? `₹${item.exit_price.toFixed(2)}` : '-'}</td>
                <td style={{ color: (item.gross_pnl || 0) >= 0 ? '#00C851' : '#FF4444', fontWeight: 'bold' }}>
                  {item.gross_pnl ? `₹${item.gross_pnl.toFixed(2)}` : '-'}
                </td>
                <td>
                  <button onClick={() => handleDelete(item.symbol)} style={{ background: 'transparent', border: 'none', color: '#FF4444', cursor: 'pointer', padding: '4px' }}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {watchlist.length === 0 && (
              <tr>
                <td colSpan="7" style={{ textAlign: 'center', padding: '2rem' }}>
                  Your watchlist is empty.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Watchlist;
