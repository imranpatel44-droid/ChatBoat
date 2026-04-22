import React from 'react';
import ReactDOM from 'react-dom/client';
import UiWidget from '../UiWidget';

// Create a container for the widget
const widgetContainer = document.createElement('div');
widgetContainer.id = 'chat-widget-root';
document.body.appendChild(widgetContainer);

// Render the widget
const root = ReactDOM.createRoot(widgetContainer);
root.render(
  <React.StrictMode>
    <UiWidget />
  </React.StrictMode>
);
