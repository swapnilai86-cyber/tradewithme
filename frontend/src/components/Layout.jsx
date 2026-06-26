import React from 'react';
import { NavLink, useNavigate, Outlet } from 'react-router-dom';
import { LayoutDashboard, LogOut, TrendingUp, AlertCircle, Eye, Settings, FileText } from 'lucide-react';
import { useAuth } from '../context/AuthContext';


function Layout() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  return (
    <div className="app-container">
      <div className="sidebar">
        <h2 style={{ padding: '0 1rem', marginBottom: '1rem', color: 'var(--accent-blue)' }}>Algo Swing</h2>
        
        {/* Admin and User see Dashboard */}
        {(user?.role === 'admin' || user?.role === 'user') && (
          <NavLink to="/dashboard" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <LayoutDashboard size={20} /> Dashboard
          </NavLink>
        )}
        
        {/* Everyone sees Watchlist and Alerts */}
        <NavLink to="/watchlist" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
          <Eye size={20} /> Watchlist
        </NavLink>
        <NavLink to="/alerts" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
          <AlertCircle size={20} /> Alerts History
        </NavLink>
        
        {/* Admin and User see Trades */}
        {(user?.role === 'admin' || user?.role === 'user') && (
          <NavLink to="/trades" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <TrendingUp size={20} /> Trades
          </NavLink>
        )}
        
        {/* Admin only sees Live Logs */}
        {user?.role === 'admin' && (
          <NavLink to="/logs" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <FileText size={20} /> Live Logs
          </NavLink>
        )}
        
        {/* Admin and User see Admin Panel (for TOTP) */}
        {(user?.role === 'admin' || user?.role === 'user') && (
          <NavLink to="/admin" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <Settings size={20} /> {user?.role === 'admin' ? 'Admin Panel' : 'Connect Broker'}
          </NavLink>
        )}

        
        <div style={{ marginTop: 'auto' }}>
          <button onClick={handleLogout} className="nav-item" style={{ background: 'transparent', border: 'none', width: '100%', cursor: 'pointer', textAlign: 'left' }}>
            <LogOut size={20} /> Logout
          </button>
        </div>
      </div>
      
      {/* This renders the child routes component */}
      <Outlet />
    </div>
  );
}

export default Layout;
