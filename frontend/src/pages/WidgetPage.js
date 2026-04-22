import React from 'react';
import { useSearchParams } from 'react-router-dom';
import UiWidget from '../components/UiWidget';

const WidgetPage = () => {
  const [searchParams] = useSearchParams();
  
  const apiKey = searchParams.get('apiKey');
  const customerId = searchParams.get('customerId');
  const apiUrl = searchParams.get('apiUrl') || 'http://localhost:5000';
  const parentUrl = searchParams.get('parentUrl') || ''; // Get parent URL from query param

  if (!apiKey || !customerId) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <h2>Invalid Widget Configuration</h2>
        <p>Missing API key or customer ID</p>
      </div>
    );
  }

  return (
    <div style={{ width: '100vw', height: '100vh', overflow: 'hidden', background: 'transparent' }}>
      <UiWidget 
        apiKey={apiKey}
        customerId={customerId}
        apiUrl={apiUrl}
        parentUrl={parentUrl}
      />
    </div>
  );
};

export default WidgetPage;
