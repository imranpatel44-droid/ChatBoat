import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../services/api';
import '../styles/AdminDashboard.css';

const AdminDashboard = () => {
  const [stats, setStats] = useState({
    documentCount: 0,
    vectorCount: 0,
    folderCount: 0
  });
  const [folders, setFolders] = useState([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [monitorInterval, setMonitorInterval] = useState(30);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [embedCode, setEmbedCode] = useState('');
  const [showEmbedCode, setShowEmbedCode] = useState(false);
  const [websiteUrl, setWebsiteUrl] = useState('');

  const [isGoogleConnected, setIsGoogleConnected] = useState(false);
  const [googleConfigured, setGoogleConfigured] = useState(true);
  const [driveFolders, setDriveFolders] = useState([]);
  const [selectedFolder, setSelectedFolder] = useState(null);
  const [showFolderModal, setShowFolderModal] = useState(false);
  const [isLoadingFolders, setIsLoadingFolders] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    fetchStats();
    fetchFolders();
    fetchEmbedCode();
    checkGoogleAuth();
    
    const params = new URLSearchParams(window.location.search);
    if (params.get('google_auth') === 'success') {
      setError('');
      window.history.replaceState({}, document.title);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLogout = async () => {
    try {
      await api.post('/logout', {});
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      navigate('/admin/login');
    }
  };

  const checkGoogleAuth = async () => {
    try {
      const customerId = localStorage.getItem('customer_id');
      if (!customerId) return;
      
      // Check if Google OAuth is configured
      const settingsRes = await api.get('/settings/google');
      setGoogleConfigured(settingsRes.data.configured);
      
      const res = await api.get('/auth/google/status', {
        headers: { 'X-Customer-ID': customerId }
      });
      setIsGoogleConnected(res.data.connected);
    } catch (err) {
      console.error('Google auth check failed:', err);
    }
  };

  const handleGoogleLogin = async () => {
    try {
      const response = await api.get('/auth/google/login');
      if (response.data.authorization_url) {
        window.location.href = response.data.authorization_url;
      }
    } catch (err) {
      if (err.response?.data?.error) {
        setError(err.response.data.error);
      } else {
        setError('Failed to initiate Google login');
      }
    }
  };

  const handleSelectDriveFolder = async () => {
    setShowFolderModal(true);
    setIsLoadingFolders(true);
    
    try {
      const customerId = localStorage.getItem('customer_id');
      const res = await api.get('/auth/google/folders', {
        headers: { 'X-Customer-ID': customerId }
      });
      setDriveFolders(res.data.folders || []);
    } catch (err) {
      setError('Failed to load Google Drive folders');
      setShowFolderModal(false);
    } finally {
      setIsLoadingFolders(false);
    }
  };

  const handleSaveSelectedFolder = async () => {
    if (!selectedFolder) return;
    
    setIsLoading(true);
    try {
      const customerId = localStorage.getItem('customer_id');
      await api.post('/auth/google/select-folder', {
        customer_id: customerId,
        folder_id: selectedFolder.id,
        folder_name: selectedFolder.name
      });

      setShowFolderModal(false);
      
      const folderLink = `https://drive.google.com/drive/folders/${selectedFolder.id}`;
      
      const endpoint = isMonitoring ? '/admin/monitor-drive-folder' : '/admin/process-drive-folder';
      const payload = { folder_link: folderLink };
      if (isMonitoring) {
        payload.interval_minutes = monitorInterval;
      }
      
      const response = await api.post(endpoint, payload);

      setSelectedFolder(null);
      fetchStats();
      fetchFolders();
      alert(response.data.message || 'Folder processed successfully');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to process folder');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisconnectGoogle = async () => {
    if (!window.confirm('Are you sure you want to disconnect your Google account?')) {
      return;
    }
    
    try {
      const customerId = localStorage.getItem('customer_id');
      await api.post('/auth/google/disconnect', { customer_id: customerId });
      setIsGoogleConnected(false);
    } catch (err) {
      setError('Failed to disconnect Google account');
    }
  };

  const fetchStats = async () => {
    try {
      const vectorResponse = await api.get('/admin/vector-store-stats');
      
      setStats({
        documentCount: vectorResponse.data.document_count || 0,
        folderCount: vectorResponse.data.folderCount || 0,
        vectorCount: vectorResponse.data.vector_count || 0
      });
    } catch (err) {
      if (err.response && err.response.status === 401) {
        navigate('/admin/login');
      } else {
        setError('Failed to fetch stats');
      }
    }
  };

  const fetchFolders = async () => {
    try {
      const response = await api.get('/admin/list-monitored-folders');
      setFolders(response.data.folders || []);
    } catch (err) {
      if (err.response && err.response.status === 401) {
        navigate('/admin/login');
      } else {
        setError('Failed to fetch monitored folders');
      }
    }
  };

  const handleClearVectorStore = async () => {
    if (!window.confirm('Are you sure you want to clear the vector store? This action cannot be undone.')) {
      return;
    }
    
    setIsLoading(true);
    setError('');
    
    try {
      await api.post('/admin/clear-vector-store', {});
      fetchStats();
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to clear vector store');
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleSyncAllFolders = async () => {
    setIsLoading(true);
    setError('');
    
    try {
      const response = await api.post('/admin/sync-all-folders-now', {});
      
      fetchFolders();
      fetchStats();
      
      if (response.data.success) {
        const { folder_count, total_processed_count } = response.data;
        alert(`Synced ${folder_count} folders. Processed: ${total_processed_count}`);
      } else {
        setError(response.data.message || 'Failed to sync all folders');
        alert(response.data.message || 'Failed to sync all folders');
      }
    } catch (err) {
      const errorMessage = err.response?.data?.message || err.response?.data?.error || 'Failed to sync all folders';
      setError(errorMessage);
      alert(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleSyncFolder = async (folderId) => {
    setIsLoading(true);
    setError('');
    
    try {
      const response = await api.post('/admin/sync-folder-now', { folder_id: folderId });
      
      fetchFolders();
      fetchStats();
      
      if (response.data.success) {
        const { documents_processed, documents_updated } = response.data;
        alert(`Folder synced successfully. Processed: ${documents_processed}, Updated: ${documents_updated}`);
      } else {
        setError(response.data.message || 'Failed to sync folder');
      }
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.error || 'Failed to sync folder');
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleStopMonitoring = async (folderId) => {
    if (!window.confirm('Are you sure you want to stop monitoring this folder?')) {
      return;
    }
    
    setIsLoading(true);
    setError('');
    
    try {
      const response = await api.post('/admin/stop-monitoring-folder', { folder_id: folderId });
      
      setFolders(prevFolders => prevFolders.filter(folder => folder.folder_id !== folderId));
      fetchStats();
      
      alert(response.data.message || 'Folder monitoring stopped successfully');
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.error || 'Failed to stop monitoring folder');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGenerateWidgetKey = async () => {
    setIsLoading(true);
    setError('');
    
    try {
      const response = await api.post('/admin/generate-widget-key', {});
      
      if (response.data.success) {
        fetchEmbedCode();
        alert('Widget API key generated successfully!');
      } else {
        setError('Failed to generate widget key');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to generate widget key');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchEmbedCode = async () => {
    try {
      const response = await api.get('/admin/get-widget-code');
      
      if (response.data.success) {
        setEmbedCode(response.data.embed_code);
        setWebsiteUrl(response.data.website_url || '');
        setShowEmbedCode(true);
      }
    } catch (err) {
      if (err.response && err.response.status === 404) {
        setShowEmbedCode(false);
      }
    }
  };

  const handleCopyEmbedCode = () => {
    navigator.clipboard.writeText(embedCode);
    alert('Embed code copied to clipboard!');
  };

  return (
    <div className="admin-dashboard">
      <header className="admin-header">
        <h1 className="admin-title">Admin Dashboard</h1>
        <div className="header-buttons">
          <button className="start-chat-button" onClick={() => navigate('/chat')}>Start Chatting with AI</button>
          <button className="settings-button" onClick={() => navigate('/admin/settings')}>Settings</button>
          <button className="logout-button" onClick={handleLogout}>Logout</button>
        </div>
      </header>
      
      <div className="admin-content">
        {error && <div className="error-message">{error}</div>}

        <section className="dashboard-section">
          <h2 className="section-title">Google Drive</h2>
          
          {!googleConfigured ? (
            <div className="google-connect-section">
              <p className="section-description">
                Google OAuth needs to be configured first. Please go to Settings to configure your Google credentials.
              </p>
              <button 
                className="action-button primary-button"
                onClick={() => navigate('/admin/settings')}
              >
                Go to Settings
              </button>
            </div>
          ) : !isGoogleConnected ? (
            <div className="google-connect-section">
              <p className="section-description">
                Connect your Google Drive to process and monitor folders automatically.
              </p>
              <button 
                className="google-connect-button"
                onClick={handleGoogleLogin}
                disabled={isLoading}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
                Connect Google Drive
              </button>
            </div>
          ) : (
            <div className="google-connected-section">
              <div className="connected-status">
                <span className="connected-icon">✓</span>
                <span>Connected to Google Drive</span>
              </div>
              
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={isMonitoring}
                    onChange={(e) => setIsMonitoring(e.target.checked)}
                    disabled={isLoading}
                  />
                  Monitor for changes
                </label>
                <span className="helper-text">
                  Check this box to automatically sync folders at regular intervals
                </span>
              </div>
              
              {isMonitoring && (
                <div className="form-group">
                  <label htmlFor="interval">Monitor interval (minutes):</label>
                  <input
                    type="number"
                    id="interval"
                    value={monitorInterval}
                    onChange={(e) => setMonitorInterval(parseInt(e.target.value) || 30)}
                    min="1"
                    max="1440"
                    disabled={isLoading}
                  />
                </div>
              )}
              
              <button 
                className="action-button primary-button"
                onClick={handleSelectDriveFolder}
                disabled={isLoading}
              >
                {isLoading ? 'Loading...' : '+ Add Folder from Google Drive'}
              </button>
              
              <button 
                className="action-button secondary-button"
                onClick={handleDisconnectGoogle}
                style={{ marginTop: '10px' }}
              >
                Disconnect
              </button>
            </div>
          )}
        </section>

        {showFolderModal && (
          <div className="modal-overlay" onClick={() => setShowFolderModal(false)}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <h3 className="modal-title">Select Google Drive Folder</h3>
              
              {isLoadingFolders ? (
                <p>Loading folders...</p>
              ) : driveFolders.length === 0 ? (
                <p>No folders found in your Google Drive.</p>
              ) : (
                <ul className="folder-select-list">
                  {driveFolders.map((folder) => (
                    <li 
                      key={folder.id}
                      className={`folder-select-item ${selectedFolder?.id === folder.id ? 'selected' : ''}`}
                      onClick={() => setSelectedFolder(folder)}
                    >
                      📁 {folder.name}
                    </li>
                  ))}
                </ul>
              )}
              
              <div className="modal-buttons">
                <button 
                  className="action-button secondary-button"
                  onClick={() => setShowFolderModal(false)}
                >
                  Cancel
                </button>
                <button 
                  className="action-button primary-button"
                  onClick={handleSaveSelectedFolder}
                  disabled={!selectedFolder || isLoading}
                >
                  {isLoading ? 'Processing...' : 'Process Folder'}
                </button>
              </div>
            </div>
          </div>
        )}

        <section className="dashboard-section">
          <h2 className="section-title">Vector Store Statistics</h2>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-icon">📄</div>
              <div className="stat-value">{stats.documentCount}</div>
              <div className="stat-label">Documents</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">🔢</div>
              <div className="stat-value">{stats.vectorCount}</div>
              <div className="stat-label">Vectors</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">📁</div>
              <div className="stat-value">{stats.folderCount}</div>
              <div className="stat-label">Monitored Folders</div>
            </div>
          </div>
        </section>

        <section className="dashboard-section">
          <h2 className="section-title">Monitored Folders</h2>
          {folders.length > 0 && (
            <button 
              className="action-button primary-button"
              onClick={handleSyncAllFolders}
              disabled={isLoading}
            >
              Sync All Folders
            </button>
          )}
          {folders.length === 0 ? (
            <p>No folders are currently being monitored.</p>
          ) : (
            <ul className="folder-list">
              {folders.map((folder, index) => (
                <li key={index} className="folder-item">
                  <div>
                    <strong>Folder Link:</strong> {folder.folder_link}
                    <div className="folder-actions">
                      <button 
                        className="action-button small-button"
                        onClick={() => handleSyncFolder(folder.folder_id)}
                        disabled={isLoading}
                      >
                        Sync Now
                      </button>
                      <button 
                        className="action-button small-button danger-button"
                        onClick={() => handleStopMonitoring(folder.folder_id)}
                        disabled={isLoading}
                      >
                        Stop Monitoring
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="dashboard-section">
          <h2 className="section-title">Widget Embed Code</h2>
          
          {!showEmbedCode ? (
            <button 
              className="action-button primary-button"
              onClick={handleGenerateWidgetKey}
              disabled={isLoading}
            >
              Generate Widget Key
            </button>
          ) : (
            <div className="embed-code-container">
              <p className="section-description">
                Copy and paste the code below into your website to embed the chat widget:
              </p>
              <pre className="embed-code">{embedCode}</pre>
              <button 
                className="action-button secondary-button"
                onClick={handleCopyEmbedCode}
              >
                Copy to Clipboard
              </button>
            </div>
          )}
        </section>

        <section className="dashboard-section">
          <h2 className="section-title">Danger Zone</h2>
          <p className="section-description">
            Clear all documents and vectors from the store. This action cannot be undone.
          </p>
          <button 
            className="action-button danger-button"
            onClick={handleClearVectorStore}
            disabled={isLoading}
          >
            Clear Vector Store
          </button>
        </section>

      </div>
    </div>
  );
};

export default AdminDashboard;
