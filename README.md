# Document Chat + Embeddable Widget (Flask + React)

## 1) What this project 
This project is a **Document Chat** system.

- You (or your customers) **upload documents / connect Google Drive**.
- The system **reads those documents** and builds a searchable knowledge base.
- Users can then **ask questions** and get answers that are based on the uploaded documents.
- The project includes:
  - a **Web App (Admin + Chat UI)**
  - an **Embeddable Chat Widget** that can be placed on another website using a small script snippet.

In simple terms: **it turns your documents into a private “chatbot brain”**.

---

## 2) What we built
### 2.1 Web application
- **Register** a customer/user
- **Login**
- **Dashboard** to:
  - process a Google Drive folder
  - optionally monitor/sync it periodically
  - view vector/document stats
  - generate widget keys / embed code
- **Chat page** to ask questions against your uploaded docs

### 2.2 Embeddable widget
- A small chat bubble UI that can be embedded into a website.
- It calls the backend with:
  - `X-Widget-API-Key`
  - `X-Customer-ID`
  - `X-Parent-URL` (the website where the widget is running)
- The backend checks the widget is being used only on the **authorized domain**.

---

## 3) Tech stack (what we used)
### Backend
- **Python + Flask** (API server)
- **flask-cors** (CORS for browser calls)
- **OpenAI / OpenRouter** (LLM responses)
- **Google Drive API** libraries (to read Drive files/folders)
- **JWT + bcrypt** (authentication)
- **NumPy** (stores embeddings arrays)
- **PyPDF2, python-docx** (PDF / DOCX parsing)
- **apscheduler** (scheduled folder sync / monitoring)

See: `requirements.txt`

### Frontend
- **React (Create React App)**
- **react-router-dom** (routing)
- **axios** (API calls)
- **framer-motion** (widget animations)
- **concurrently** (run React + Flask together)

See: `frontend/package.json`

---

## 4) Repository structure (important folders)
At the project root:
- **`main.py`**
  - Starts the Flask server.
  - Adds `backend/` to Python path and imports `backend/app.py`.
- **`backend/`**
  - Flask app + all backend logic.
- **`frontend/`**
  - React application (Admin UI / Chat UI / Widget UI).

Key backend files:
- **`backend/app.py`**
  - Main Flask app.
  - API routes like `/backend/api/login`, `/backend/api/chat`, widget endpoints, admin endpoints.
  - Serves production React build from `frontend/build`.
- **`backend/auth.py`**
  - User registration/login.
  - JWT generation + refresh tokens.
  - Password hashing.
- **`backend/document_manager.py`**
  - Core “document → embeddings → retrieval → prompt” logic.
- **`backend/drive_monitor.py`**
  - Background monitoring/sync for Drive folders.
- **`backend/vector_store.py`**
  - Stores and retrieves embeddings + document metadata.

Key frontend files:
- **`frontend/src/App.js`**
  - Defines routes like `/admin/login`, `/admin/dashboard`, `/chat`, `/widget`.
- **`frontend/src/services/api.js`**
  - Axios instance configured with `baseURL: '/backend/api'` and `withCredentials: true`.
  - Handles token refresh automatically on expiry.
- **`frontend/src/pages/AdminDashboard.js`**
  - Dashboard logic (folders, monitoring, embed code, widget key generation).
- **`frontend/src/components/UiWidget.jsx`**
  - Main widget UI + `fetch()` calls to widget endpoints.

---

## 5) How the system works (big picture)
### Step A: Customer registers
- User registers from the frontend (`/register`).
- Backend creates a unique customer folder under:
  - `backend/data/customers/<customer_id>/`
- Also creates an empty vector store:
  - `backend/data/customers/<customer_id>/vector_store/`

### Step B: Customer adds documents (Drive)
- From dashboard, customer submits a Drive folder link.
- Backend downloads and processes docs.
- Text is extracted and converted into embeddings.
- Embeddings are saved in the customer’s vector store.

### Step C: Chat (web app)
- Frontend calls:
  - `POST /backend/api/chat`
- Backend:
  - fetches relevant document context from vector store
  - builds a prompt
  - calls the LLM
  - returns the response

### Step D: Chat (embedded widget)
- Widget calls:
  - `POST /backend/api/widget/chat`
- Backend:
  - verifies API key + customer id
  - verifies the widget is running on the authorized domain (`X-Parent-URL`)
  - retrieves context
  - calls selected LLM service
  - returns the response

---

## 6) API endpoints (high level)
These are the most important endpoints (the backend file contains the complete list).

### Auth
- `POST /backend/api/register`
- `POST /backend/api/login`
- `POST /backend/api/logout`
- `POST /backend/api/refresh`
- `GET  /backend/api/auth/status`

### Chat
- `POST /backend/api/chat` (protected)

### Admin (dashboard)
- `GET  /backend/api/admin/vector-store-stats`
- `GET  /backend/api/admin/list-monitored-folders`
- `POST /backend/api/admin/process-drive-folder`
- `POST /backend/api/admin/monitor-drive-folder`
- `POST /backend/api/admin/sync-all-folders-now`
- `POST /backend/api/admin/sync-folder-now`
- `POST /backend/api/admin/stop-monitoring-folder`
- `POST /backend/api/admin/clear-vector-store`

### Widget
- `POST /backend/api/widget/chat`
- `POST /backend/api/widget/context`

---

## 7) How to run the project (development)
### Prerequisites
- Python 3.x
- Node.js 16+ (recommended)

### Backend setup
1. Create and activate a Python virtual environment
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure environment variables:
  - Copy `backend/.env.example` to `backend/.env`
  - Fill in real keys and secrets

### Frontend setup
1. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```

### Run both servers together
From `frontend/`:
```bash
npm start
```
This runs:
- React dev server: http://localhost:3000
- Flask server: http://localhost:5000

---

## 8) Production build (single server)
1. Build React:
   ```bash
   cd frontend
   npm run build
   ```
2. Run Flask:
   ```bash
   python main.py
   ```
Flask serves the React build from `frontend/build` via the catch-all route.

---

## 9) Configuration you must change for a real product
### 9.1 Secrets and API keys
**Never commit real keys to Git.**

Backend environment variables live in:
- `backend/.env` (local)
- `backend/.env.production` (production)

Important variables:
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `JWT_REFRESH_SECRET_KEY`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `CORS_ALLOWED_ORIGINS`

### 9.2 Allowed domains for widget
- When widget keys are generated, a `widget_config.json` is stored per customer.
- Widget calls include `X-Parent-URL` so backend can validate the domain.

---

## 10) How to embed the widget (for customers)
The dashboard can generate an embed snippet.

Conceptually, embedding requires:
- **Customer ID**
- **Widget API Key**
- **Backend URL** (where Flask is hosted)

The widget UI lives in:
- `frontend/src/components/UiWidget.jsx`

The widget API calls look like:
```js
fetch(`${apiUrl}/backend/api/widget/chat`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Widget-API-Key': apiKey,
    'X-Customer-ID': customerId,
    'X-Parent-URL': detectedParentUrl,
  },
  body: JSON.stringify({ message, service })
})
```

---

## 11) “Where do I change X?” (handover guide)
### Change UI pages
- Admin login page: `frontend/src/pages/AdminLogin.js`
- Register page: `frontend/src/pages/Register.js`
- Dashboard: `frontend/src/pages/AdminDashboard.js`
- Chat page: `frontend/src/pages/ChatPage.js`
- Widget page (full screen): `frontend/src/pages/WidgetPage.js`

### Change API base paths
- Browser → backend API for app: `frontend/src/services/api.js`
  - uses `baseURL: '/backend/api'` and CRA proxy.

### Change widget backend URL
- Widget component: `frontend/src/components/UiWidget.jsx`
  - prop: `apiUrl` (defaults to `http://localhost:5000`)

### Change backend routes / business logic
- Main API: `backend/app.py`
- Auth logic: `backend/auth.py`
- Document processing / embeddings: `backend/document_manager.py`, `backend/document_processor.py`, `backend/embeddings_generator.py`

---

## 12) Common problems & fixes
- **CORS errors**
  - Update `CORS_ALLOWED_ORIGINS` in backend `.env`.
- **Widget says unauthorized**
  - The widget is being embedded on a domain that doesn’t match the registered domain.
  - Check `widget_config.json` under the customer folder.
- **Drive processing fails**
  - Ensure Google credentials are correctly configured.

---

## 13) Notes / limitations
- This repository includes both frontend and backend in one project.
- Authentication is JWT-based; frontend uses cookies (`withCredentials`).
- Documents and embeddings are stored on disk under `backend/data/customers/`.

---

## 14) Quick start 
1. Install Python + Node
2. Put keys into `backend/.env`
3. Run:
   - `pip install -r requirements.txt`
   - `cd frontend && npm install`
   - `npm start`
4. Open:
   - http://localhost:3000

---

