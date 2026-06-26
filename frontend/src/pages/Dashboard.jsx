import React from 'react';

function Dashboard() {
  return (
    <div className="main-content">
      <h1>Dashboard</h1>
      
      <div className="stats-grid">
        <div className="glass-panel stat-card">
          <h3>Total PnL</h3>
          <div className="value text-green">+15.2%</div>
        </div>
        <div className="glass-panel stat-card">
          <h3>Win Rate</h3>
          <div className="value text-green">68%</div>
        </div>
        <div className="glass-panel stat-card">
          <h3>Open Trades</h3>
          <div className="value">4</div>
        </div>
        <div className="glass-panel stat-card">
          <h3>Watchlist Symbols</h3>
          <div className="value">25</div>
        </div>
      </div>

      <div className="glass-panel">
        <h2 style={{ marginBottom: '1rem' }}>Recent Alerts</h2>
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
            <tr>
              <td><strong>RELIANCE</strong></td>
              <td><span className="badge badge-yellow">EARLY RADAR</span></td>
              <td>₹2,850.50</td>
              <td>Waiting Breakout</td>
            </tr>
            <tr>
              <td><strong>TCS</strong></td>
              <td><span className="badge badge-green">ENTRY TRIGGER</span></td>
              <td>₹3,920.00</td>
              <td>Order Placed</td>
            </tr>
            <tr>
              <td><strong>INFY</strong></td>
              <td><span className="badge badge-red">EXIT</span></td>
              <td>₹1,450.00</td>
              <td>SL Hit (-3%)</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Dashboard;
