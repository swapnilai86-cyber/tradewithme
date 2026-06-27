import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

function AdminPanel() {
  const [totp, setTotp] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState([]);
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', role: 'viewer' });
  const [createStatus, setCreateStatus] = useState('');
  const [syncStatus, setSyncStatus] = useState('');
  const [cmpFilter, setCmpFilter] = useState({ mode: 'none', min_val: 0, max_val: 0 });
  const [filterStatus, setFilterStatus] = useState('');
  const { token, user } = useAuth();

  useEffect(() => {
    if (user?.role === 'admin') {
      fetchUsers();
      fetchCmpFilter();
    }
  }, [user]);

  const fetchCmpFilter = async () => {
    try {
      const res = await fetch('/api/admin/cmp-filter', { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setCmpFilter(await res.json());
    } catch (err) {
      console.error(err);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await fetch('/api/admin/users', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        setUsers(await response.json());
      }
    } catch (err) {
      console.error("Failed to fetch users:", err);
    }
  };

  const handleUpdateExpiry = async (userId, newExpiry) => {
    try {
      const response = await fetch(`/api/admin/users/${userId}/expiry`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ expiry_date: new Date(newExpiry).toISOString() })
      });
      if (response.ok) {
        alert("Expiry updated successfully");
        fetchUsers();
      } else {
        alert("Failed to update expiry");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setCreateStatus('Creating...');
    try {
      const response = await fetch('/api/admin/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(newUser)
      });
      
      const data = await response.json();
      if (response.ok) {
        setCreateStatus('✅ User created successfully!');
        setNewUser({ username: '', email: '', password: '', role: 'viewer' });
        fetchUsers();
      } else {
        setCreateStatus(`❌ Error: ${data.detail || 'Failed to create user'}`);
      }
    } catch (err) {
      setCreateStatus(`❌ Network Error: ${err.message}`);
    }
  };

  const handleTriggerSync = async () => {
    setSyncStatus('Triggering download...');
    try {
      const response = await fetch('/api/admin/sync-offline-data', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      if (response.ok) {
        setSyncStatus('✅ Sync triggered! Check the Live Logs for progress.');
      } else {
        setSyncStatus(`❌ Error: ${data.detail || 'Failed to trigger sync'}`);
      }
    } catch (err) {
      setSyncStatus(`❌ Network error: ${err.message}`);
    }
  };

  const handleToggleOffline = async () => {
    try {
      const response = await fetch('/api/admin/toggle-offline', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      if (response.ok) {
        setSyncStatus(`✅ ${data.message}`);
      } else {
        setSyncStatus(`❌ Error: ${data.detail}`);
      }
    } catch (err) {
      setSyncStatus(`❌ Network error: ${err.message}`);
    }
  };

  const handleApplyFilter = async () => {
    setFilterStatus('Applying...');
    try {
      const response = await fetch('/api/admin/cmp-filter', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(cmpFilter)
      });
      const data = await response.json();
      if (response.ok) {
        setFilterStatus(`✅ ${data.message}`);
      } else {
        setFilterStatus(`❌ Error: ${data.detail}`);
      }
    } catch (err) {
      setFilterStatus(`❌ Network error: ${err.message}`);
    }
  };


  const handleConnect = async () => {
    if (!totp || totp.length !== 6) {
      setStatus('Please enter a valid 6-digit TOTP code.');
      return;
    }
    setLoading(true);
    setStatus('Connecting...');
    try {
      const response = await fetch('/api/admin/totp', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ totp_code: totp })
      });
      
      const data = await response.json();
      if (response.ok) {
        setStatus('✅ Successfully connected to m.Stock!');
        setTotp('');
      } else {
        setStatus(`❌ Error: ${data.detail || 'Failed to connect'}`);
      }
    } catch (error) {
      setStatus(`❌ Network Error: ${error.message}`);
    }
    setLoading(false);
  };

  if (user?.role !== 'admin' && user?.role !== 'user') {
    return (
      <div className="main-content" style={{ padding: '2rem' }}>
        <h1>Admin / User Panel</h1>
        <div className="glass-panel" style={{ color: '#FF4444' }}>
          <p>Access Denied. You do not have permission to view this page.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="main-content" style={{ padding: '2rem' }}>
      <h1>{user.role === 'admin' ? 'Admin Panel' : 'User Panel'}</h1>
      
      <div className="glass-panel" style={{ marginBottom: '2rem', maxWidth: '500px' }}>
        <h2>Broker Connection</h2>
        <p style={{ color: '#aaa', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Connect the Trading Engine to m.Stock manually for this session.
        </p>
        
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <input 
            type="text" 
            placeholder="6-Digit TOTP" 
            value={totp}
            onChange={(e) => setTotp(e.target.value)}
            maxLength={6}
            style={{ 
              padding: '0.75rem', 
              borderRadius: '8px', 
              border: '1px solid #333', 
              background: '#1a1a1a', 
              color: 'white',
              fontSize: '1rem',
              width: '150px',
              textAlign: 'center',
              letterSpacing: '2px'
            }}
          />
          <button 
            onClick={handleConnect} 
            disabled={loading}
            style={{
              padding: '0.75rem 1.5rem',
              borderRadius: '8px',
              border: 'none',
              background: loading ? '#444' : '#4f46e5',
              color: 'white',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontWeight: 'bold',
              transition: 'background 0.2s'
            }}
          >
            {loading ? '...' : 'Connect'}
          </button>
        </div>
        
        {status && (
          <div style={{ marginTop: '1rem', padding: '1rem', borderRadius: '8px', background: '#222', fontSize: '0.9rem' }}>
            {status}
          </div>
        )}
      </div>

      {user?.role === 'admin' && (
        <>
          <div className="glass-panel" style={{ marginBottom: '2rem' }}>
            <h2>Offline Data Settings</h2>
            <p style={{ color: '#9ca3af', marginBottom: '1rem', fontSize: '0.9rem' }}>
              The system automatically pulls Yahoo Finance data daily at 4:30 PM for offline use. You can also trigger it manually.
            </p>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <button onClick={handleTriggerSync} className="btn btn-primary">
                Manual Sync Yahoo Finance Data
              </button>
              <button onClick={handleToggleOffline} className="btn" style={{ background: 'transparent', border: '1px solid #3b82f6', color: '#3b82f6' }}>
                Toggle Offline Mode
              </button>
            </div>
            {syncStatus && (
              <div style={{ marginTop: '1rem', padding: '1rem', borderRadius: '8px', background: '#222', fontSize: '0.9rem', maxWidth: '600px' }}>
                {syncStatus}
              </div>
            )}
          </div>

          <div className="glass-panel" style={{ marginBottom: '2rem' }}>
            <h2>Scanner Price Filter (CMP)</h2>
            <p style={{ color: '#9ca3af', marginBottom: '1rem', fontSize: '0.9rem' }}>
              Filter which stocks are evaluated by the scanner based on their Current Market Price.
            </p>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.5rem', color: '#ccc' }}>Filter Mode</label>
                <select 
                  className="input-field" 
                  style={{ marginBottom: 0, width: '200px' }}
                  value={cmpFilter.mode} 
                  onChange={e => setCmpFilter({...cmpFilter, mode: e.target.value})}
                >
                  <option value="none">None (Scan All)</option>
                  <option value="less_than">Less Than or Equal (&lt;=)</option>
                  <option value="greater_than">Greater Than or Equal (&gt;=)</option>
                  <option value="between">Between</option>
                </select>
              </div>

              {(cmpFilter.mode === 'greater_than' || cmpFilter.mode === 'between') && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.5rem', color: '#ccc' }}>Min Price</label>
                  <input 
                    type="number" 
                    className="input-field" 
                    style={{ marginBottom: 0, width: '120px' }}
                    value={cmpFilter.min_val}
                    onChange={e => setCmpFilter({...cmpFilter, min_val: parseFloat(e.target.value) || 0})}
                  />
                </div>
              )}

              {(cmpFilter.mode === 'less_than' || cmpFilter.mode === 'between') && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.5rem', color: '#ccc' }}>Max Price</label>
                  <input 
                    type="number" 
                    className="input-field" 
                    style={{ marginBottom: 0, width: '120px' }}
                    value={cmpFilter.max_val}
                    onChange={e => setCmpFilter({...cmpFilter, max_val: parseFloat(e.target.value) || 0})}
                  />
                </div>
              )}

              <button onClick={handleApplyFilter} className="btn btn-primary" style={{ height: '42px' }}>
                Apply Filter
              </button>
            </div>
            {filterStatus && (
              <div style={{ marginTop: '1rem', padding: '1rem', borderRadius: '8px', background: '#222', fontSize: '0.9rem', maxWidth: '600px' }}>
                {filterStatus}
              </div>
            )}
          </div>

          <div className="glass-panel" style={{ marginBottom: '2rem' }}>
            <h2>Create New User</h2>
            <form onSubmit={handleCreateUser} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', maxWidth: '600px' }}>
              <input type="text" className="input-field" placeholder="Username" required value={newUser.username} onChange={e => setNewUser({...newUser, username: e.target.value})} />
              <input type="email" className="input-field" placeholder="Email" required value={newUser.email} onChange={e => setNewUser({...newUser, email: e.target.value})} />
              <input type="password" className="input-field" placeholder="Password" required value={newUser.password} onChange={e => setNewUser({...newUser, password: e.target.value})} />
              <select className="input-field" value={newUser.role} onChange={e => setNewUser({...newUser, role: e.target.value})}>
                <option value="admin">Admin</option>
                <option value="user">User</option>
                <option value="guest">Guest</option>
              </select>
              <button type="submit" className="btn btn-primary" style={{ gridColumn: '1 / -1' }}>Create User</button>
            </form>
            {createStatus && (
              <div style={{ marginTop: '1rem', padding: '1rem', borderRadius: '8px', background: '#222', fontSize: '0.9rem', maxWidth: '600px' }}>
                {createStatus}
              </div>
            )}
          </div>

          <div className="glass-panel">
        <h2>User Management</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Username</th>
              <th>Role</th>
              <th>Expiry Date</th>
              <th>Update Expiry</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td>{u.expiry_date ? new Date(u.expiry_date).toLocaleDateString() : 'Never'}</td>
                <td>
                  <input 
                    type="date" 
                    className="input-field"
                    style={{ marginBottom: 0, padding: '0.25rem', width: '150px' }}
                    onChange={(e) => handleUpdateExpiry(u.id, e.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </>
      )}
    </div>
  );
}

export default AdminPanel;
