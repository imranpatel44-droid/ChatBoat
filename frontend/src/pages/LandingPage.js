import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/LandingPage.css';

const LandingPage = () => {
  return (
    <div className="landing-page">
      <header className="landing-header">
        <h1 className="landing-title">Document Chat Assistant</h1>
      </header>
      
      <main className="landing-main">
        <p className="landing-description">Upload Google Drive documents and ask questions about their content</p>
        
        <div className="landing-buttons">
          <Link to="/chat" className="landing-button primary-button">Start Chatting</Link>
          <Link to="/admin/login" className="landing-button secondary-button">Admin Login</Link>
        </div>
      </main>
    </div>
  );
};

export default LandingPage;