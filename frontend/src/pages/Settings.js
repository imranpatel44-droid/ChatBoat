import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import '../styles/AdminDashboard.css';

const Settings = () => {
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [googleSettings, setGoogleSettings] = useState({ configured: false, client_id: '' });
  
  const navigate = useNavigate();

  useEffect(() => {
    fetchGoogleSettings();
  }, []);

  const fetchGoogleSettings = async () => {
    try {
      const res = await api.get('/settings/google');
      setGoogleSettings(res.data);
      if (res.data.client_id) {
        setClientId(res.data.client_id);
      }
    } catch (err) {
      console.error('Failed to fetch settings:', err);
    }
  };

  const handleSaveGoogleSettings = async (e) => {
    e.preventDefault();
    
    if (!clientId.trim() || !clientSecret.trim()) {
      setMessage({ type: 'error', text: 'Both Client ID and Client Secret are required' });
      return;
    }

    setIsLoading(true);
    setMessage({ type: '', text: '' });

    try {
      const res = await api.post('/settings/google', {
        client_id: clientId.trim(),
        client_secret: clientSecret.trim()
      });
      
      if (res.data.success) {
        setMessage({ type: 'success', text: 'Google OAuth settings saved successfully!' });
        setClientSecret('');
        fetchGoogleSettings();
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.error || 'Failed to save settings' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await api.post('/logout', {});
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      navigate('/admin/login');
    }
  };

  return (
    <div className="admin-dashboard">
      <header className="admin-header">
        <h1 className="admin-title">Settings</h1>
        <div className="header-buttons">
          <button className="start-chat-button" onClick={() => navigate('/admin/dashboard')}>Dashboard</button>
          <button className="logout-button" onClick={handleLogout}>Logout</button>
        </div>
      </header>
      
      <div className="admin-content">
        {message.text && (
          <div className={`${message.type}-message`}>
            {message.text}
          </div>
        )}

        <section className="dashboard-section">
          <h2 className="section-title">Google OAuth Configuration</h2>
          <p className="section-description">
            To enable Google Drive integration, you need to create a project in Google Cloud Console 
            and configure OAuth credentials. Follow these steps:
          </p>
          
          <div className="widget-instructions">
            <ol>
              <li>Go to <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer">Google Cloud Console</a></li>
              <li>Create a new project or select an existing one</li>
              <li>Navigate to <strong>APIs & Services → Library</strong></li>
              <li>Enable <strong>Google Drive API</strong></li>
              <li>Go to <strong>APIs & Services → Credentials</strong></li>
              <li>Click <strong>Create Credentials → OAuth client ID</strong></li>
              <li>Configure the consent screen (if prompted)</li>
              <li>Select <strong>Web application</strong> as the application type</li>
              <li>Add authorized redirect URI: <code>http://localhost:5000/backend/api/auth/google/callback</code></li>
              <li>Copy the <strong>Client ID</strong> and <strong>Client Secret</strong></li>
              <li>Paste them below and save</li>
            </ol>
          </div>

          <form onSubmit={handleSaveGoogleSettings}>
            <div className="form-group">
              <label htmlFor="clientId">Google Client ID</label>
              <input
                type="text"
                id="clientId"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Enter your Google Client ID"
                disabled={isLoading}
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="clientSecret">Google Client Secret</label>
              <input
                type="password"
                id="clientSecret"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder="Enter your Google Client Secret"
                disabled={isLoading}
              />
            </div>
            
            <button 
              type="submit" 
              className="action-button primary-button"
              disabled={isLoading}
            >
              {isLoading ? 'Saving...' : 'Save Google OAuth Settings'}
            </button>
          </form>

          {googleSettings.configured && (
            <div style={{ marginTop: '1rem', color: '#059669', fontWeight: '600' }}>
              ✓ Google OAuth is configured
            </div>
          )}
        </section>

      </div>
    </div>
  );
};

export default Settings;
