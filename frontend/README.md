# Document Chat React Frontend

This is the React frontend for the Document Chat application. It communicates with the Flask backend API.

## Setup and Installation

1. Run the setup script from the root directory:
   ```
   setup.bat
   ```

2. This will install both Python and React dependencies.

## Running the Application

1. Navigate to the frontend directory:
   ```
   cd frontend
   ```

2. Start both the React frontend and Flask backend:
   ```
   npm start
   ```

This will automatically start:
- React development server on port 3000
- Flask backend on port 5000

The React app is configured to proxy API requests to the Flask backend.

## Building for Production

To create a production build:

```
npm run build
```

The Flask app is configured to serve the React build files from the `frontend/build` directory.